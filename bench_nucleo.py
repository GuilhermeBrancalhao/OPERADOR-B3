"""Benchmark descartavel do nucleo: Simulador -> Barramento -> EstadoMercado.

Mede vazao (eventos/s), custo medio por evento (us) e memoria retida,
comparando com o necessario para WDO em tempo real (picos 5-10k ev/s).

Uso:  python bench_nucleo.py [n_passos]
"""
from __future__ import annotations

import gc
import sys
import time
import tracemalloc

from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import BookSnapshot, Trade
from fluxopro.dados.simulador import SimuladorWDO

ALVO_PICO_EV_S = 10_000  # WDO em dia agitado


def _contar(n_passos: int) -> tuple[int, int]:
    """Quantos eventos o simulador realmente emite em n_passos."""
    barramento = Barramento()
    n = [0, 0]
    barramento.assinar(Trade, lambda e: n.__setitem__(0, n[0] + 1))
    barramento.assinar(BookSnapshot, lambda e: n.__setitem__(1, n[1] + 1))
    SimuladorWDO(barramento, seed=1, n_eventos=n_passos).iniciar()
    return n[0], n[1]


def cenario(nome: str, n_passos: int, com_estado: bool) -> dict:
    gc.collect()
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT") if com_estado else None
    sim = SimuladorWDO(barramento, seed=1, n_eventos=n_passos)

    tracemalloc.start()
    base_mem = tracemalloc.get_traced_memory()[0]
    t0 = time.perf_counter()
    sim.iniciar()
    dt = time.perf_counter() - t0
    atual, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    n_ev = n_passos * 2  # 1 trade + 1 snapshot por passo
    r = {
        "cenario": nome,
        "eventos": n_ev,
        "segundos": dt,
        "ev_por_s": n_ev / dt,
        "us_por_evento": dt / n_ev * 1e6,
        "mem_retida_mb": (atual - base_mem) / 1e6,
        "mem_pico_mb": (pico - base_mem) / 1e6,
    }
    if estado is not None:
        r["candles_fechados"] = len(estado.candles_fechados)
        r["niveis_book"] = len(estado.book_atual(0).bids) + len(estado.book_atual(0).asks)
    return r


def main() -> None:
    n_passos = int(sys.argv[1]) if len(sys.argv) > 1 else 250_000
    t, s = _contar(1_000)
    print(f"forma do fluxo: {t} trades + {s} snapshots por 1000 passos "
          f"=> {(t+s)/1000:.0f} eventos/passo\n")

    linhas = [
        cenario("simulador sozinho (piso: custo do gerador)", n_passos, com_estado=False),
        cenario("simulador -> barramento -> EstadoMercado", n_passos, com_estado=True),
    ]

    for r in linhas:
        print(f"--- {r['cenario']}")
        print(f"    eventos          : {r['eventos']:,}")
        print(f"    tempo            : {r['segundos']:.3f} s")
        print(f"    vazao            : {r['ev_por_s']:,.0f} eventos/s")
        print(f"    custo/evento     : {r['us_por_evento']:.3f} us")
        print(f"    memoria retida   : {r['mem_retida_mb']:.2f} MB")
        print(f"    memoria pico     : {r['mem_pico_mb']:.2f} MB")
        if "candles_fechados" in r:
            print(f"    candles fechados : {r['candles_fechados']:,}")
            print(f"    niveis no book   : {r['niveis_book']}")
        folga = r["ev_por_s"] / ALVO_PICO_EV_S
        print(f"    folga vs pico {ALVO_PICO_EV_S:,} ev/s: {folga:.1f}x "
              f"=> {'PASSA' if folga >= 1 else 'NAO PASSA'}")
        print()

    # custo isolado do EstadoMercado
    piso, cheio = linhas[0], linhas[1]
    delta_us = cheio["us_por_evento"] - piso["us_por_evento"]
    print(f"custo atribuivel ao Barramento+EstadoMercado: {delta_us:.3f} us/evento "
          f"({delta_us/cheio['us_por_evento']*100:.0f}% do total)")
    print(f"memoria por candle fechado: "
          f"{cheio['mem_retida_mb']*1e6/max(1,cheio['candles_fechados']):.0f} bytes "
          f"(lista NUNCA e podada -> cresce sem limite)")


if __name__ == "__main__":
    main()
