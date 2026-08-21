"""Harness de auto-mutacao da rodada R5 (builder de perfil_player/brokers/
simulador/footprint). Para cada mutacao em mutacoes_r5.json:

1. Le o arquivo alvo, calcula sha256 do conteudo com CRLF normalizado p/ LF.
2. Grava a mutacao em r5_em_voo.json (registro ANTES de aplicar).
3. Aplica a substituicao literal (falha se `de` nao aparecer exatamente 1x).
4. Roda os testes declarados; captura passou/falhou.
5. try/finally: restaura o conteudo original.
6. Confere que o sha256 pos-restauracao bate com o pre-mutacao.
7. Remove a mutacao de r5_em_voo.json.

Resultado por mutacao: MORTA (algum teste falhou = mutante detectado) ou
SOBREVIVEU (todos os testes passaram mesmo com a mutacao aplicada).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MUT_DIR = RAIZ / ".mut"
TABELA = MUT_DIR / "mutacoes_r5.json"
# NOTA: `.mut/r5_em_voo.json` (nome pedido na tarefa) esta OCUPADO por outro
# builder em paralelo no momento em que este harness comecou a rodar
# (mutacao M08 de fluxopro/motor/sinais.py, fora do meu escopo). Sobrescreve-lo
# destruiria o rastreamento em voo de um processo irmao ativo. Uso um nome
# proprio para o meu lote (perfil_player/brokers/simulador/footprint) para
# nao colidir; ambos os arquivos co-existem em `.mut/` sem se pisar.
EM_VOO = MUT_DIR / "r5_em_voo_p4_analytics_micro.json"
RESULTADO = MUT_DIR / "r5_resultado.json"


def sha256_normalizado(caminho: Path) -> str:
    conteudo = caminho.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(conteudo).hexdigest()


def ler_em_voo() -> list:
    if EM_VOO.exists():
        return json.loads(EM_VOO.read_text(encoding="utf-8"))
    return []


def gravar_em_voo(lista: list) -> None:
    EM_VOO.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


def rodar_testes(testes: list[str]) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", *testes]
    proc = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True)
    saida = proc.stdout[-4000:] + proc.stderr[-2000:]
    return proc.returncode == 0, saida


def main() -> None:
    mutacoes = json.loads(TABELA.read_text(encoding="utf-8"))
    resultados = []

    for m in mutacoes:
        caminho = RAIZ / m["arquivo"]
        original = caminho.read_text(encoding="utf-8")
        sha_antes = sha256_normalizado(caminho)

        if m["de"] not in original:
            resultados.append({**m, "erro": "ANCORA_NAO_ENCONTRADA"})
            print(f"[{m['id']}] ANCORA NAO ENCONTRADA -- pulando")
            continue
        if original.count(m["de"]) != 1:
            resultados.append({**m, "erro": "ANCORA_NAO_UNICA"})
            print(f"[{m['id']}] ANCORA NAO UNICA ({original.count(m['de'])}x) -- pulando")
            continue

        em_voo = ler_em_voo()
        em_voo.append({
            "id": m["id"], "arquivo": m["arquivo"], "sha256_original_normalizado": sha_antes,
        })
        gravar_em_voo(em_voo)

        try:
            mutado = original.replace(m["de"], m["para"])
            caminho.write_text(mutado, encoding="utf-8")

            passou, saida = rodar_testes(m["testes"])
            veredito = "SOBREVIVEU" if passou else "MORTA"
            print(f"[{m['id']}] {veredito} -- {m['desc']}")
            resultados.append({
                "id": m["id"], "arquivo": m["arquivo"], "desc": m["desc"],
                "testes": m["testes"], "veredito": veredito,
            })
        finally:
            caminho.write_text(original, encoding="utf-8")
            sha_depois = sha256_normalizado(caminho)
            assert sha_depois == sha_antes, f"RESTAURACAO FALHOU em {m['arquivo']}"

            em_voo = ler_em_voo()
            em_voo = [e for e in em_voo if e["id"] != m["id"]]
            gravar_em_voo(em_voo)

    RESULTADO.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== RESUMO ===")
    for r in resultados:
        if "erro" in r:
            print(f"  {r['id']}: ERRO {r['erro']}")
        else:
            print(f"  {r['id']}: {r['veredito']}")

    assert not EM_VOO.exists() or json.loads(EM_VOO.read_text(encoding="utf-8")) == [], (
        "r5_em_voo.json nao ficou vazio ao final"
    )


if __name__ == "__main__":
    main()
