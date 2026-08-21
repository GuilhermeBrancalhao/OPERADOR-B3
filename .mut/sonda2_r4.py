"""R4 - vazamento do heap de precos do InferidorMBP (5a casa)."""
from __future__ import annotations
import sys, time, gc
from fluxopro.core.eventos import BookLevel, BookSnapshot
from fluxopro.microestrutura.livro_mbo import LivroMBO
from fluxopro.microestrutura.inferencia_mbp import InferidorMBP

SYM="WDOFUT"; BASE=1_700_000_000_000_000_000
def novo():
    liv=LivroMBO(SYM); return liv, InferidorMBP(SYM, liv)
def snap(ts,bids,asks):
    return BookSnapshot(symbol=SYM,timestamp_ns=ts,
        bids=[BookLevel(price=p,qty=q,n_orders=1) for p,q in bids],
        asks=[BookLevel(price=p,qty=q,n_orders=1) for p,q in asks])

def d_duracao():
    """Eixo DURACAO DE PREGAO a taxa FIXA de 5.000 ev/s. O que a onda 7 nao mediu."""
    print("\nD) EIXO DURACAO: taxa fixa 5.000 snapshots/s, sessao crescente")
    print(f"   {'minutos':>9} {'snapshots':>12} {'heap_bids':>12} {'niveis_vivos':>13} {'MB_heap':>9} {'us/passo':>10} {'fator':>7}")
    ref=None
    liv,inf=novo(); ts=BASE
    total=0
    for minutos in (1,2,4,8,16):
        alvo=minutos*60*5000
        n=alvo-total
        gc.collect(); t0=time.perf_counter()
        for i in range(n):
            ts+=200_000
            # topo cravado em 10.000; nivel de fundo 9.999 pisca (recarga tipica)
            cheio=(total+i)%2==0
            bids=[(10_000,500)]+([(9_999,300)] if cheio else [])
            inf.ao_snapshot(snap(ts,bids,[(10_001,500)]))
        dt=time.perf_counter()-t0
        total=alvo
        us=dt/n*1e6
        if ref is None: ref=us; fator=""
        else: fator=f"{us/ref:.2f}x"
        mb=len(inf._heap_bids)*28/1e6
        print(f"   {minutos:>9} {total:>12,} {len(inf._heap_bids):>12,} {len(inf._qty_por_nivel):>13} {mb:>9.1f} {us:>10.2f} {fator:>7}")
    print(f"   -> extrapolando para 6h de pregao a 5.000 ev/s: {int(6*3600*5000/2):,} entradas de heap para 2 niveis vivos")

def e_pico():
    """Latencia do UNICO evento que finalmente esvazia o preco acumulado."""
    print("\nE) PICO DE LATENCIA: um evento paga a divida inteira do heap")
    for n_ciclos in (10_000, 50_000, 200_000, 800_000):
        liv,inf=novo(); ts=BASE
        # acumula duplicatas do preco 9.999 (fundo), topo 10.000 fixo
        for i in range(n_ciclos):
            ts+=200_000
            cheio=i%2==0
            bids=[(10_000,500)]+([(9_999,300)] if cheio else [])
            inf.ao_snapshot(snap(ts,bids,[(10_001,500)]))
        # agora o TOPO some: melhor_bid tem de descer ate 9.999 e podar tudo
        ts+=200_000
        inf.ao_snapshot(snap(ts,[(9_999,300)],[(10_001,500)]))
        h_antes=len(inf._heap_bids)
        gc.collect(); t0=time.perf_counter()
        # o proximo evento que consulta o topo com 10.000 ja vazio
        ts+=200_000
        inf.ao_snapshot(snap(ts,[],[(10_001,500)]))
        b=inf.melhor_bid()
        dt=(time.perf_counter()-t0)*1e6
        print(f"   ciclos={n_ciclos:>9,}  heap_antes={h_antes:>9,}  latencia_do_evento={dt:>12,.1f} us  melhor_bid={b}")
    print("   (a barra: 5.000-10.000 ev/s => orcamento de 100-200 us POR EVENTO)")

if __name__=="__main__":
    w=sys.argv[1] if len(sys.argv)>1 else "de"
    if "d" in w: d_duracao()
    if "e" in w: e_pico()
