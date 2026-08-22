# -*- coding: utf-8 -*-
"""Sonda R6: mede o crescimento REAL das colecoes de instancia sob carga.
Nao muta nada; so instrumenta e mede."""
from __future__ import annotations
import gc, os, sys, tracemalloc
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

def tam_lista_ints(n: int) -> int:
    """Mede bytes reais de uma lista com n timestamps_ns distintos."""
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    L = []
    t0 = 1_700_000_000_000_000_000
    for i in range(n):
        L.append(t0 + i * 200_000)
    atual = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    return atual - base, len(L)

print("=== A) custo real de Gravador._horarios (1 int por evento) ===")
for n in (100_000, 1_000_000):
    b, ln = tam_lista_ints(n)
    print(f"  n={n:>9,}  bytes={b:>13,}  bytes/evento={b/n:6.2f}")
    del b
gc.collect()

# extrapolacao
_, _ = 0, 0
b1m, _ = tam_lista_ints(1_000_000)
por_ev = b1m / 1_000_000
for taxa, horas in ((5_000, 6), (10_000, 6), (5_000, 8)):
    n = taxa * 3600 * horas
    print(f"  pregao {horas}h a {taxa:,} ev/s -> {n:,} eventos -> {n*por_ev/1e9:6.2f} GB so em _horarios")
