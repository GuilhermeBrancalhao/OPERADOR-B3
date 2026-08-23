#!/usr/bin/env python
"""Gera o manifesto versionavel das gravacoes — sem publicar dado de mercado.

    python scripts/manifesto_dados.py --arquivo dados/ --saida dados_manifesto.json
    python scripts/manifesto_dados.py --arquivo dados/ --verificar

## O problema que ele resolve

`/dados/` esta no `.gitignore`, e tem de continuar: sao 26 MB de tick da B3,
dado licenciado da corretora, que nao vai para um repositorio.

O efeito colateral e serio. Os numeros publicados em `PROGRESSO.md` — 200.899
negocios em 21/08, exaustao caindo de 76,8% para 55,8%, a tabela dos 32
pregoes — sao verificaveis apenas por quem tem os arquivos. Quem le o
repositorio consegue auditar o CODIGO e a LOGICA do estudo, e nao consegue
conferir se os numeros vieram mesmo daqueles insumos.

Um resultado que so o autor consegue reproduzir e uma afirmacao, nao uma
medicao. Este projeto ja catalogou essa forma de defeito em outras roupas:
numero congelado sob selo de verificacao, portao que mede fora da imagem,
teste que passa por estar fora do cenario.

## O que o manifesto carrega — e o que ele deliberadamente NAO carrega

Carrega, por dia: simbolo, data, contagem de eventos por tipo, primeiro e
ultimo timestamp, versao de schema, e o **SHA-256 do arquivo gravado**.

Nao carrega preco, volume, VWAP, delta, nem qualquer estatistica derivada do
mercado. A fronteira e proposital: o manifesto responde *"quais insumos foram
usados, e eles estao integros?"*, e nao *"quanto o mercado andou?"*. A primeira
pergunta e sobre procedencia e cabe num repositorio publico; a segunda e o dado
licenciado.

## O que ele permite a um terceiro

1. Importar os mesmos pregoes com `scripts/importar_mt5.py` na propria conta.
2. Rodar `--verificar` e comparar os hashes linha a linha.
3. Se baterem, rodar `scripts/estudo_pregoes.py` e obter os MESMOS numeros.

Se nao baterem, o manifesto diz exatamente qual dia divergiu — o que ja e
informacao, porque historico de tick varia entre corretoras e datas de
download.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.gravacao.catalogo import Catalogo  # noqa: E402

VERSAO_MANIFESTO = 1

_UTC = dt.timezone.utc


def _iso(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=_UTC).isoformat()


def construir(base: Path) -> dict:
    """Le os `meta.json` da gravacao e monta o manifesto.

    Le o METADADO, e nao os arquivos de dados: o hash ja foi calculado pelo
    `Gravador` sobre o conteudo no momento da escrita, e recalcula-lo aqui
    abriria a porta para um manifesto que descreve o arquivo de hoje enquanto
    o `meta.json` descreve o de ontem. Uma fonte de verdade por numero.
    """
    catalogo = Catalogo(base)
    catalogo.escanear()

    dias = []
    for entrada in catalogo.listar():
        meta_path = base / entrada.symbol / entrada.data.isoformat() / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        dias.append(
            {
                "symbol": meta["symbol"],
                "data": meta["data"],
                "schema_versao": meta["schema_versao"],
                "contagens": meta["contagens"],
                "n_eventos_total": meta["n_eventos_total"],
                "inicio_utc": _iso(meta["hora_inicio_ns"]),
                "fim_utc": _iso(meta["hora_fim_ns"]),
                "parcial": meta["parcial"],
                "hashes_sha256": meta["hashes_sha256"],
                "n_linhas_hasheadas": meta["n_linhas_hasheadas"],
            }
        )

    dias.sort(key=lambda d: (d["symbol"], d["data"]))
    total = sum(d["n_eventos_total"] for d in dias)
    return {
        "versao_manifesto": VERSAO_MANIFESTO,
        "aviso": (
            "Metadados de integridade. NAO contem dado de mercado — nenhum "
            "preco, volume ou estatistica derivada. Os arquivos de tick ficam "
            "fora do repositorio por serem licenciados da corretora."
        ),
        "como_reproduzir": [
            "1. python scripts/importar_mt5.py --simbolo <sym> --data <AAAA-MM-DD> --saida dados/",
            "2. python scripts/manifesto_dados.py --arquivo dados/ --verificar",
            "3. se os hashes baterem: python scripts/estudo_pregoes.py --arquivo dados/ --simbolo <sym>",
        ],
        "n_dias": len(dias),
        "n_eventos_total": total,
        "dias": dias,
    }


def verificar(base: Path, manifesto: dict) -> list[str]:
    """Compara o manifesto com o que esta em disco. Devolve as divergencias.

    Devolve LISTA, e nao booleano: "nao bate" sem dizer onde obriga quem
    verifica a refazer o trabalho a mao, que e o oposto do que um manifesto
    existe para fazer.
    """
    atual = construir(base)
    por_chave = {(d["symbol"], d["data"]): d for d in atual["dias"]}
    divergencias: list[str] = []

    for esperado in manifesto["dias"]:
        chave = (esperado["symbol"], esperado["data"])
        encontrado = por_chave.pop(chave, None)
        if encontrado is None:
            divergencias.append(f"{chave[0]} {chave[1]}: AUSENTE em disco")
            continue
        for campo in ("n_eventos_total", "inicio_utc", "fim_utc", "hashes_sha256"):
            if encontrado[campo] != esperado[campo]:
                divergencias.append(
                    f"{chave[0]} {chave[1]}: {campo} diverge\n"
                    f"    manifesto: {esperado[campo]}\n"
                    f"    em disco : {encontrado[campo]}"
                )

    for chave in sorted(por_chave):
        divergencias.append(
            f"{chave[0]} {chave[1]}: em disco e NAO no manifesto "
            "(gravacao nova — regere o manifesto)"
        )
    return divergencias


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="manifesto de integridade das gravacoes")
    p.add_argument("--arquivo", required=True, help="diretorio base da gravacao")
    p.add_argument("--saida", default="dados_manifesto.json")
    p.add_argument(
        "--verificar",
        action="store_true",
        help="compara o manifesto existente com o disco em vez de regerar",
    )
    args = p.parse_args(argv)

    base = Path(args.arquivo)
    saida = Path(args.saida)

    if args.verificar:
        if not saida.exists():
            print(f"manifesto nao encontrado: {saida}")
            return 2
        manifesto = json.loads(saida.read_text(encoding="utf-8"))
        divergencias = verificar(base, manifesto)
        if divergencias:
            print(f"{len(divergencias)} divergencia(s):")
            for linha in divergencias:
                print(f"  {linha}")
            return 1
        print(
            f"OK — {manifesto['n_dias']} dias, "
            f"{manifesto['n_eventos_total']:,} eventos, hashes conferem"
        )
        return 0

    manifesto = construir(base)
    saida.write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"{saida}: {manifesto['n_dias']} dias, "
        f"{manifesto['n_eventos_total']:,} eventos"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
