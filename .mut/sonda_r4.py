"""R4 - regimes que a onda 7 NAO testou."""
from __future__ import annotations
import gc, random, sys, time
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.microestrutura.livro_mbo import LivroMBO
from fluxopro.microestrutura.inferencia_mbp import InferidorMBP

SYM = "WDOFUT"; BASE = 1_700_000_000_000_000_000

def novo():
    liv = LivroMBO(SYM)
    return liv, InferidorMBP(SYM, liv)

def snap(ts, bids, asks):
    return BookSnapshot(symbol=SYM, timestamp_ns=ts,
        bids=[BookLevel(price=p, qty=q, n_orders=1) for p, q in bids],
        asks=[BookLevel(price=p, qty=q, n_orders=1) for p, q in asks])

# ---------------------------------------------------------------
# A) RECARGA sob topo estavel: heap de precos cresce sem teto?
# ---------------------------------------------------------------
def a_recarga(n=40_000, fundos=5):
    liv, inf = novo()
    ts = BASE
    passo_ns = 200_000  # 5.000 passos/s
    t0 = time.perf_counter()
    marcos = {}
    for i in range(n):
        ts += passo_ns
        # topo estavel em 10.000; fundos ciclam 0 -> qty -> 0
        cheio = (i % 2 == 0)
        bids = [(10_000, 500)]
        for k in range(1, fundos + 1):
            bids.append((10_000 - k, 300 if cheio else 0))
        bids = [(p, q) for p, q in bids if q > 0]
        inf.ao_snapshot(snap(ts, bids, [(10_001, 500)]))
        if i in (n // 10, n // 4, n // 2, n - 1):
            marcos[i + 1] = (len(inf._heap_bids), len(inf._heap_asks))
    dt = time.perf_counter() - t0
    print("\nA) RECARGA de niveis sob topo estavel (heap de precos com remocao preguicosa)")
    print(f"   {n} snapshots, {fundos} niveis de fundo ciclando 0->300->0")
    print(f"   {'snapshots':>12} {'heap_bids':>12} {'heap_asks':>12}")
    for k, (hb, ha) in marcos.items():
        print(f"   {k:>12,} {hb:>12,} {ha:>12,}")
    print(f"   tempo {dt:.2f}s  ->  {n/dt:,.0f} snapshots/s")
    print(f"   niveis vivos em _qty_por_nivel: {len(inf._qty_por_nivel)}")
    esperado = fundos * (n // 2)
    print(f"   crescimento do heap_bids por recarga: {marcos[n][0]/max(1,esperado):.2f} entrada/recarga")

# ---------------------------------------------------------------
# B) preco cravado + cancelamento massivo + recarga (o regime pedido)
# ---------------------------------------------------------------
def b_cravado_cancel(taxas=(500, 1_000, 2_000, 5_000, 10_000), dur_s=1.0):
    print("\nB) PRECO CRAVADO + CANCELAMENTO MASSIVO + RECARGA")
    print(f"   {'tape/s':>8} {'us/passo':>10} {'passos/s':>12} {'heap':>10} {'fila_livro':>12} {'fator':>8}")
    ref = None
    for taxa in taxas:
        liv, inf = novo()
        n = int(taxa * dur_s)
        passo_ns = int(1e9 / taxa)
        ts = BASE
        rnd = random.Random(7)
        gc.collect()
        t0 = time.perf_counter()
        for i in range(n):
            ts += passo_ns
            # o bid cravado em 10.000 esvazia e recarrega; nenhum negocio casa
            q = 400 if (i % 2 == 0) else 0
            bids = [(10_000, q)] if q else []
            inf.ao_snapshot(snap(ts, bids, [(10_001, 400)]))
            # tape do lado que NAO casa (agressor de compra, queda no bid)
            inf.ao_trade(Trade(symbol=SYM, timestamp_ns=ts, price=10_001, qty=1,
                               side_agressor=AgressorSide.BUY, trade_id=f"t{i}"))
        dt = time.perf_counter() - t0
        fila = len(inf._pendentes)
        us = dt / n * 1e6
        if ref is None:
            ref = us; fator = ""
        else:
            fator = f"{us/ref:.2f}x"
        print(f"   {taxa:>8,} {us:>10.2f} {n/dt:>12,.0f} {len(inf._heap_bids):>10,} {fila:>12,} {fator:>8}")

# ---------------------------------------------------------------
# C) alternancia rapida de topo
# ---------------------------------------------------------------
def c_alternancia(taxas=(500, 1_000, 2_000, 5_000, 10_000), dur_s=1.0):
    print("\nC) ALTERNANCIA RAPIDA DE TOPO (bid alterna entre 2 precos a cada passo)")
    print(f"   {'tape/s':>8} {'us/passo':>10} {'passos/s':>12} {'heap_bids':>10} {'fator':>8}")
    ref = None
    for taxa in taxas:
        liv, inf = novo()
        n = int(taxa * dur_s)
        passo_ns = int(1e9 / taxa)
        ts = BASE
        gc.collect()
        t0 = time.perf_counter()
        for i in range(n):
            ts += passo_ns
            if i % 2 == 0:
                bids = [(10_000, 300), (9_999, 200)]
            else:
                bids = [(9_999, 200)]
            inf.ao_snapshot(snap(ts, bids, [(10_001, 300)]))
            inf.ao_trade(Trade(symbol=SYM, timestamp_ns=ts, price=10_000, qty=2,
                               side_agressor=AgressorSide.SELL, trade_id=f"t{i}"))
        dt = time.perf_counter() - t0
        us = dt / n * 1e6
        if ref is None:
            ref = us; fator = ""
        else:
            fator = f"{us/ref:.2f}x"
        print(f"   {taxa:>8,} {us:>10.2f} {n/dt:>12,.0f} {len(inf._heap_bids):>10,} {fator:>8}")

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "abc"
    if "a" in which: a_recarga()
    if "b" in which: b_cravado_cancel()
    if "c" in which: c_alternancia()
