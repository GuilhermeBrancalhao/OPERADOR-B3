# -*- coding: utf-8 -*-
"""Sonda R6 — o GRAVADOR na escala do produto.

Nenhuma das cinco rodadas anteriores mediu o Gravador sob carga. Esta sonda
mede as duas coisas que faltam:

  1. VAZAO do gravador contra a barra de 10.000 ev/s (ele esta no MESMO
     barramento do pipeline: `scripts/operar.py:238`, entao o custo dele
     entra direto no orcamento por evento).
  2. CRESCIMENTO REAL de `_horarios` medido no objeto vivo, para confirmar a
     extrapolacao sintetica da Parte A com o codigo de producao.

Uso: PYTHONPATH=. python .mut/sonda_r6_gravador.py
"""
from __future__ import annotations
import os, shutil, sys, tempfile, time, tracemalloc

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.gravacao.gravador import Gravador

LINHA = "=" * 78
SYMBOL = "WDOV26"
T0 = 1_770_000_000_000_000_000   # dentro de um dia util


def tape(n, com_book=True):
    """n eventos: alterna Trade e BookSnapshot, 200 us entre eventos (5.000 ev/s)."""
    for i in range(n):
        ts = T0 + i * 200_000
        if com_book and i % 2:
            yield BookSnapshot(
                timestamp_ns=ts, symbol=SYMBOL,
                bids=tuple(BookLevel(5000 - k, 10 + k, 2) for k in range(5)),
                asks=tuple(BookLevel(5001 + k, 10 + k, 2) for k in range(5)),
            )
        else:
            yield Trade(ts, SYMBOL, 5000 + (i % 40), 5,
                        AgressorSide.BUY if i % 3 else AgressorSide.SELL, f"t{i}")


print(LINHA)
print("1) VAZAO do Gravador (barra do projeto: 10.000 ev/s)")
print(LINHA)
print(f"{'eventos':>10} {'segundos':>10} {'ev/s':>12} {'us/ev':>9}  veredito")
for n in (20_000, 60_000):
    tmp = tempfile.mkdtemp(prefix="r6_gv_")
    try:
        bar = Barramento()
        g = Gravador(bar, tmp, fsync_a_cada=200)   # default de fabrica
        g.iniciar()
        eventos = list(tape(n))
        t0 = time.perf_counter()
        for e in eventos:
            bar.publicar(e)
        dt = time.perf_counter() - t0
        g.parar()
        taxa = n / dt
        print(f"{n:>10,} {dt:>10.2f} {taxa:>12,.0f} {dt/n*1e6:>9.1f}  "
              f"{'PASSA' if taxa >= 10_000 else '*** NAO PASSA ***'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print()
print(LINHA)
print("2) `_horarios` no objeto VIVO: cresce com o numero de eventos?")
print(LINHA)
tmp = tempfile.mkdtemp(prefix="r6_gh_")
try:
    bar = Barramento()
    g = Gravador(bar, tmp, fsync_a_cada=100_000)
    g.iniciar()
    print(f"{'eventos publicados':>20} {'len(_horarios)':>16} {'bytes da lista':>16} {'B/evento':>10}")
    publicados = 0
    tracemalloc.start()
    for alvo in (10_000, 40_000, 80_000):
        for e in tape(alvo - publicados):
            bar.publicar(e)
        publicados = alvo
        chave = next(iter(g._horarios))
        lista = g._horarios[chave]
        bytes_lista = sys.getsizeof(lista) + sum(sys.getsizeof(x) for x in lista)
        print(f"{publicados:>20,} {len(lista):>16,} {bytes_lista:>16,} "
              f"{bytes_lista/len(lista):>10.1f}")
    tracemalloc.stop()
    por_ev = bytes_lista / len(lista)
    print()
    print("  extrapolacao com o valor MEDIDO no objeto vivo:")
    for taxa, horas in ((5_000, 6), (10_000, 6)):
        n = taxa * 3600 * horas
        print(f"    pregao {horas}h a {taxa:>6,} ev/s -> {n:>13,} eventos -> "
              f"{n*por_ev/1e9:>6.2f} GB so em _horarios")
    print()
    print("  para que serve a lista inteira (gravador.py:185-186):")
    print('     "hora_inicio_ns": min(horarios)   "hora_fim_ns": max(horarios)')
    print("  => DOIS ESCALARES. O necessario e' O(1); o gasto e' O(eventos).")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
