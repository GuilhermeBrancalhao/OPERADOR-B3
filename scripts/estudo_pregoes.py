#!/usr/bin/env python
"""Roda o motor sobre TODOS os pregoes gravados e tabula o que ele viu.

    python scripts/estudo_pregoes.py --arquivo dados/ --simbolo WDOU26

Existe porque um pregao nao diz nada sozinho. `EXAUSTAO 7.421` num dia parece
muito ou pouco? Sem a serie ao lado, a resposta e opiniao. Com trinta e dois
dias, vira distribuicao — e distribuicao permite perguntar as coisas que
importam para o metodo:

* a taxa de deteccao por minuto e estavel, ou ela explode com o volume?
* quanto do volume chega SEM lado do agressor, e isso varia?
* o motor emite sinal todo dia, ou ha dias em que ele se cala?
* o dia liquido e o dia parado produzem a mesma leitura?

Nao decide nada. Este script MEDE, e a decisao de calibrar parametro fica com
quem le — que e a mesma disciplina de `fluxopro/metodologia/regras.py`, onde
`IMPRECISO` vira parametro configuravel e nunca constante cravada.

## Uma ressalva que muda a leitura da tabela

Contrato futuro tem VIDA. `WDOU26` so virou o contrato de referencia do dolar
em agosto — antes disso a liquidez estava no vencimento anterior. Na serie
abaixo isso aparece como um degrau: julho tem 8 a 20 mil negocios por dia,
agosto tem 145 a 270 mil. **Os dias de julho nao sao dias parados; sao dias em
que este contrato nao era o principal.** Misturar os dois na mesma media
produziria um numero que nao descreve nenhum dos dois regimes.

O script marca a virada sozinho, pela mediana, em vez de a data ser digitada.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.app.config import ConfigOperacao, FonteDados  # noqa: E402
from fluxopro.app.montagem import OpcoesReplay, montar  # noqa: E402
from fluxopro.core.eventos import Trade  # noqa: E402
from fluxopro.gravacao.catalogo import Catalogo  # noqa: E402


def _rodar_dia(caminho: Path, simbolo: str, dia) -> dict:
    """Um pregao inteiro pelo pipeline de verdade. Devolve o que se mediu."""
    sinais: Counter = Counter()
    deteccoes: Counter = Counter()

    cfg = ConfigOperacao(symbol=simbolo, fonte=FonteDados.REPLAY)
    montagem = montar(
        cfg,
        ao_sinal=lambda s: sinais.update([s.estagio.name]),
        ao_deteccao=lambda d: deteccoes.update([d.deteccao.tipo.name]),
        replay=OpcoesReplay(caminho=caminho, data=dia, velocidade="max"),
    )

    # TEMPO DE MERCADO, colhido do proprio tape — e nao o relogio de parede.
    #
    # A primeira versao usava `sessao.segundos_decorridos()`, que mede quanto o
    # PROCESSO levou. Com replay a velocidade maxima um pregao de 9,5 h passa em
    # 40 s, e `det/min` saiu 10.475 — cento e setenta e cinco deteccoes por
    # segundo, um numero que so nao e absurdo se ninguem parar para le-lo.
    # O valor certo e ~17/min.
    #
    # Fica como lembrete de que a unidade e parte da medida: uma taxa dividida
    # pelo relogio errado nao e uma taxa imprecisa, e outra grandeza.
    janela = {"primeiro": 0, "ultimo": 0}

    def _marcar(t: Trade) -> None:
        if not janela["primeiro"]:
            janela["primeiro"] = t.timestamp_ns
        janela["ultimo"] = t.timestamp_ns

    montagem.barramento.assinar(Trade, _marcar)

    inicio = time.perf_counter()
    montagem.fonte.iniciar()
    parede = time.perf_counter() - inicio

    sessao = montagem.sessao
    dia_mercado = sessao.estado.sessao
    perfil = sessao.perfil_sessao
    duracao_s = (janela["ultimo"] - janela["primeiro"]) / 1e9
    montagem.sessao.finalizar()

    volume = dia_mercado.volume_total
    sem_lado = dia_mercado.volume_nao_atribuido
    return {
        "dia": dia,
        "trades": sessao.contadores.n_trades_bus,
        "volume": volume,
        "sem_lado": sem_lado,
        "delta": dia_mercado.volume_comprador - dia_mercado.volume_vendedor,
        "max": dia_mercado.high,
        "min": dia_mercado.low,
        # em PRECO, e nao em ticks: a coluna mostrava 10.339 com o dolar a
        # 5.169, porque o modelo guarda tick inteiro e eu imprimia cru.
        "vwap": cfg.price_grid().to_price(int(dia_mercado.vwap))
        if dia_mercado.vwap
        else None,
        "poc": perfil.poc if perfil else None,
        "duracao_s": duracao_s,
        "parede_s": parede,
        "sinais": sum(sinais.values()),
        "confirmados": sinais.get("CONFIRMADO", 0),
        "deteccoes": sum(deteccoes.values()),
        "por_tipo": dict(deteccoes),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arquivo", required=True)
    p.add_argument("--simbolo", required=True)
    args = p.parse_args(argv)

    caminho = Path(args.arquivo)
    catalogo = Catalogo(caminho)
    catalogo.escanear()
    entradas = sorted(e.data for e in catalogo.listar(args.simbolo))
    if not entradas:
        print(f"nenhuma gravacao de {args.simbolo} em {caminho}")
        return 1

    print(f"{len(entradas)} pregoes de {args.simbolo}\n")
    cab = (
        f"{'dia':<11}{'trades':>9}{'volume':>11}{'s/lado':>8}"
        f"{'delta':>9}{'vwap':>9}{'det':>7}{'det/min':>9}{'sin':>5}{'conf':>6}"
    )
    print(cab)
    print("-" * len(cab))

    linhas = []
    for dia in entradas:
        r = _rodar_dia(caminho, args.simbolo, dia)
        minutos = max(r["duracao_s"] / 60.0, 1e-9)
        r["det_min"] = r["deteccoes"] / minutos
        r["pct_sem_lado"] = 100.0 * r["sem_lado"] / max(r["volume"], 1)
        linhas.append(r)
        print(
            f"{str(r['dia']):<11}{r['trades']:>9,}{r['volume']:>11,}"
            f"{r['pct_sem_lado']:>7.1f}%{r['delta']:>9,}"
            f"{(r['vwap'] or 0):>9.1f}{r['deteccoes']:>7,}{r['det_min']:>9.1f}"
            f"{r['sinais']:>5}{r['confirmados']:>6}"
        )

    # A virada de contrato sai da MEDIANA, e nao de uma data digitada: assim a
    # separacao continua valendo quando este estudo rodar sobre outro simbolo
    # ou outro periodo.
    mediana = statistics.median(r["trades"] for r in linhas)
    liquidos = [r for r in linhas if r["trades"] >= mediana]
    magros = [r for r in linhas if r["trades"] < mediana]

    print()
    for nome, grupo in (("LIQUIDOS", liquidos), ("MAGROS", magros)):
        if not grupo:
            continue
        det_min = [r["det_min"] for r in grupo]
        sem_lado = [r["pct_sem_lado"] for r in grupo]
        print(
            f"{nome:<9} n={len(grupo):<3} "
            f"trades med={statistics.median(r['trades'] for r in grupo):>9,.0f}  "
            f"det/min med={statistics.median(det_min):>6.1f} "
            f"(min {min(det_min):.1f} max {max(det_min):.1f})  "
            f"s/lado med={statistics.median(sem_lado):.1f}%"
        )

    tipos: Counter = Counter()
    for r in linhas:
        tipos.update(r["por_tipo"])
    total_det = sum(tipos.values())
    print()
    print("deteccoes por tipo, somando os", len(linhas), "pregoes:")
    for tipo, n in tipos.most_common():
        print(f"  {tipo:<22}{n:>9,}  {100.0 * n / max(total_det, 1):>5.1f}%")

    dias_sem_sinal = [r["dia"] for r in linhas if r["sinais"] == 0]
    dias_sem_conf = [r["dia"] for r in linhas if r["confirmados"] == 0]
    print()
    print(f"pregoes sem NENHUM sinal      : {len(dias_sem_sinal)} {dias_sem_sinal}")
    print(f"pregoes sem sinal CONFIRMADO  : {len(dias_sem_conf)} {dias_sem_conf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
