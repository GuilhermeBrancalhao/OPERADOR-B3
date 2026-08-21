"""Benchmark do PIPELINE MONTADO — o que `bench_carga.py` e `.mut/bench_r2.py`
não medem: `fluxopro.app` com `InferidorMBP` e `LivroMBO` no caminho.

    python bench_app.py [--n 30000] [--repeticoes 3]

Barra do projeto: **10.000 eventos de mercado por segundo** (pico do WDO em
dia agitado).

## Duas convenções de contagem, e por que as duas aparecem

`SimuladorWDO` publica DOIS eventos por passo (um `Trade` e um
`BookSnapshot`). `.mut/bench_r2.py` passa `n_eventos=n` e divide `n` pelo
tempo — ou seja, mede **passos/s**, não eventos publicados/s, apesar do
cabeçalho dizer "N eventos (metade trades, metade book)". Este script imprime
as duas colunas para que a comparação com a tabela da R2 não precise de
tradução mental:

* **ev/s (barramento)** — eventos realmente publicados. É a definição que
  bate com "pico de 5-10 mil eventos/s do WDO" e é a que vale contra a barra.
* **passos/s** — a mesma medida na convenção da R2 (= metade do anterior).

## Por que o estágio 6 é o caro, e o que isso quer dizer

Os estágios 1-5 reproduzem a escada da R2. O 6 acrescenta o que nunca havia
sido medido: a ponte MBP->MBO. Ela não custa por evento de mercado — custa por
**evento de ORDEM inferido**, e o tape do simulador é adversarial nisso: o
`SimuladorWDO._publicar_book` **regenera os 4 níveis de profundidade de cada
lado com `randint(10, 100)` a cada passo**, então quase todo nível do book
muda de quantidade a cada evento. Um DOM real não se comporta assim (a
profundidade é relativamente estável entre polls de 50 ms). Por isso a coluna
`ord/ev` está na tabela: sem ela, um número baixo de ev/s pareceria custo do
pipeline quando é volume de trabalho gerado pela fonte.

A linha `microestrutura isolada` divide o custo pelo que ele de fato processa
(eventos de ordem/s), que é a medida comparável com os ~330.000 neg/s e
~120.000 ev/s que o autor do `InferidorMBP` mediu.
"""

from __future__ import annotations

import argparse
import gc
import random
import sys
import time

from fluxopro.app.config import ConfigOperacao, ConfigSimulador
from fluxopro.app.montagem import montar
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade

SYMBOL = "WDOFUT"
SEED = 7
BARRA_EV_S = 10_000

ESTAGIOS: list[tuple[str, dict]] = [
    ("1. barramento + EstadoMercado", dict(ligar_analytics=False, ligar_microestrutura=False,
                                           ligar_detectores_tape=False, ligar_motor=False)),
    ("2. + analytics (6 modulos)", dict(ligar_microestrutura=False,
                                        ligar_detectores_tape=False, ligar_motor=False)),
    ("3. + detectores de tape (3)", dict(ligar_microestrutura=False, ligar_motor=False)),
    ("4. + MotorSinais", dict(ligar_microestrutura=False)),
    ("5. + microestrutura  <<< PIPELINE COMPLETO", dict()),
]


def rodar(n: int, ligados: dict) -> tuple[float, int, int]:
    cfg = ConfigOperacao(
        symbol=SYMBOL,
        simulador=ConfigSimulador(seed=SEED, n_eventos=n),
        **ligados,
    )
    montagem = montar(cfg)
    gc.collect()
    t0 = time.perf_counter()
    montagem.fonte.iniciar()
    dt = time.perf_counter() - t0
    c = montagem.sessao.contadores
    return dt, c.n_eventos_bus, c.n_ordem_eventos


def melhor(n: int, ligados: dict, repeticoes: int) -> tuple[float, int, int]:
    """Melhor de N: a máquina do dono roda outras coisas, e a mediana de
    execuções ruidosas mede a carga do sistema, não o pipeline. O piso de
    tempo é o único valor cuja interpretação não depende do que mais estava
    rodando — e ele é conservador no sentido certo (nunca superestima)."""
    resultados = [rodar(n, ligados) for _ in range(repeticoes)]
    return min(resultados, key=lambda r: r[0])


def rodar_book_sintetico(n: int, fundo_estavel: bool) -> tuple[float, int, int]:
    """Mesmo pipeline, mesmo tape, book gerado aqui — para separar o custo do
    PIPELINE do volume de trabalho que a FONTE gera.

    O tape de negócios é idêntico nos dois modos (mesma seed, mesma sequência
    de agressões e de deslocamento de preço). A única diferença é se os 4
    níveis de profundidade de cada lado recebem `randint(10, 100)` novo a cada
    tick — o que `SimuladorWDO._publicar_book` faz — ou se ficam parados,
    mexendo só o topo, que é o comportamento de um DOM entre dois polls.

    Cada nível cuja quantidade muda vira uma queda ou uma inserção para o
    `InferidorMBP`, ou seja: ~9 níveis mexidos por tick contra ~1.
    """
    cfg = ConfigOperacao(symbol=SYMBOL, simulador=ConfigSimulador(n_eventos=0))
    montagem = montar(cfg)
    bus = montagem.barramento
    rng = random.Random(SEED)
    ts, preco, qty_bid, qty_ask = 0, 10_000, 50, 50
    fundo = [rng.randint(10, 100) for _ in range(4)]

    gc.collect()
    t0 = time.perf_counter()
    for i in range(n):
        ts += 200_000_000
        agressor = AgressorSide.BUY if rng.random() < 0.5 else AgressorSide.SELL
        qty = rng.randint(1, 10)
        bus.publicar(Trade(ts, SYMBOL, preco, qty, agressor, f"t{i}"))
        if agressor is AgressorSide.BUY:
            qty_ask -= qty
        else:
            qty_bid -= qty
        if qty_ask <= 0 or qty_bid <= 0:
            preco += 1 if qty_ask <= 0 else -1
            qty_bid = rng.randint(20, 80)
            qty_ask = rng.randint(20, 80)
        if not fundo_estavel:
            fundo = [rng.randint(10, 100) for _ in range(4)]
        bids = tuple(
            BookLevel(preco - 1 - k, qty_bid if k == 0 else fundo[k - 1], 1)
            for k in range(5)
        )
        asks = tuple(
            BookLevel(preco + 1 + k, qty_ask if k == 0 else fundo[k - 1], 1)
            for k in range(5)
        )
        bus.publicar(BookSnapshot(ts, SYMBOL, bids, asks))
    dt = time.perf_counter() - t0
    c = montagem.sessao.contadores
    return dt, c.n_eventos_bus, c.n_ordem_eventos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30_000, help="passos do simulador")
    ap.add_argument("--repeticoes", type=int, default=3)
    args = ap.parse_args()

    print(f"BARRA = {BARRA_EV_S:,} ev/s de mercado.  "
          f"n={args.n:,} passos do simulador (= {2 * args.n:,} eventos publicados)")
    print(f"melhor de {args.repeticoes} execucoes por estagio\n")
    print("=" * 108)
    print(f"{'estagio':<44} {'ev/s (bus)':>13} {'passos/s':>11} "
          f"{'us/ev':>8} {'ord/ev':>8}  veredito")
    print("=" * 108)

    linha_completa = None
    for nome, ligados in ESTAGIOS:
        dt, n_bus, n_ord = melhor(args.n, ligados, args.repeticoes)
        ev_s = n_bus / dt
        veredito = "PASSA" if ev_s >= BARRA_EV_S else "*** NAO PASSA ***"
        print(f"{nome:<44} {ev_s:>13,.0f} {args.n / dt:>11,.0f} "
              f"{dt / n_bus * 1e6:>8.2f} {n_ord / n_bus:>8.2f}  {veredito}")
        if not ligados:
            linha_completa = (dt, n_bus, n_ord)

    if linha_completa is not None:
        dt, n_bus, n_ord = linha_completa
        # O que a microestrutura custa POR EVENTO DE ORDEM (a unidade em que
        # ela de fato trabalha), isolando o custo dos estagios anteriores.
        dt_sem, n_bus_sem, _ = melhor(args.n, dict(ligar_microestrutura=False), args.repeticoes)
        delta = dt - dt_sem * (n_bus / n_bus_sem)
        print()
        print("=" * 108)
        print("MICROESTRUTURA ISOLADA (InferidorMBP + LivroMBO + 3 detectores de livro)")
        print("=" * 108)
        print(f"  eventos de ordem inferidos : {n_ord:,}  ({n_ord / n_bus:.2f} por evento de mercado)")
        if delta > 0:
            print(f"  custo atribuido ao estagio : {delta:.3f}s  "
                  f"=> {n_ord / delta:,.0f} eventos de ordem/s  ({delta / n_ord * 1e6:.2f} us cada)")
        print("  NOTA: o book do SimuladorWDO regenera 8 dos 10 niveis com qty aleatoria")
        print("        a cada passo; um DOM real muda muito menos entre polls.")

    print()
    print("=" * 108)
    print("CONTROLE: A FONTE E' O GARGALO, OU O PIPELINE?")
    print("=" * 108)
    print("Mesmo pipeline completo, mesmo tape de trades, mesma taxa. Muda so o BOOK:")
    print("  (a) fundo do book com qty aleatoria a cada tick  -> e' o que SimuladorWDO faz")
    print("  (b) fundo do book estavel, so o topo se move     -> e' o que um DOM real faz")
    for rotulo, estavel in (
        ("(a) fundo aleatorio por tick (SimuladorWDO)", False),
        ("(b) fundo estavel (DOM realista)", True),
    ):
        dt, n_bus, n_ord = min(
            (rodar_book_sintetico(args.n, estavel) for _ in range(args.repeticoes)),
            key=lambda r: r[0],
        )
        ev_s = n_bus / dt
        veredito = "PASSA" if ev_s >= BARRA_EV_S else "*** NAO PASSA ***"
        print(f"  {rotulo:<46} {ev_s:>10,.0f} ev/s  "
              f"ord/ev={n_ord / n_bus:>5.2f}  {veredito}")

    print()
    print("ESCALONAMENTO DO PIPELINE COMPLETO (procurando custo nao-linear)")
    print("-" * 108)
    print(f"{'n passos':>10} {'seg':>9} {'ev/s (bus)':>13} {'us/ev':>9} {'x us/ev':>9}")
    anterior = None
    for n in (5_000, 10_000, 20_000, 40_000):
        dt, n_bus, _ = melhor(n, dict(), max(2, args.repeticoes - 1))
        us_ev = dt / n_bus * 1e6
        razao = "-" if anterior is None else f"x{us_ev / anterior:.2f}"
        print(f"{n:>10,} {dt:>9.3f} {n_bus / dt:>13,.0f} {us_ev:>9.2f} {razao:>9}")
        anterior = us_ev
    print("  (x us/ev ~ 1.00 ao dobrar n => custo linear; > 1 sistematicamente => nao-linear)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
