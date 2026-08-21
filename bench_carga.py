"""Benchmark de carga do nucleo: 500 mil eventos pelo pipeline completo.

A barra e o pico do WDO: 5.000-10.000 eventos/segundo, tick a tick, sem
acumular atraso. Este script mede o pipeline em ESTAGIOS CUMULATIVOS para
que o gargalo apareca sozinho, sem precisar de profiler:

  1. barramento vazio         -> teto teorico do despacho
  2. + EstadoMercado          -> nucleo (book, candle, sessao)
  3. + analytics (6 modulos)  -> volume profile, footprint, delta, agressao,
                                 brokers, vwap
  4. + detectores             -> absorcao, exaustao, clip institucional

O estagio 4 roda em N reduzido e com varredura de N, porque a suspeita e de
custo NAO-LINEAR (a janela do DetectorAbsorcao e reconstruida a cada trade).

Uso:
    python bench_carga.py                 # completo
    python bench_carga.py --perfil        # + cProfile top 10
    python bench_carga.py --n 100000      # menor
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import io
import pstats
import time
import tracemalloc

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfilePorPeriodo
from fluxopro.analytics.vwap import VWAP
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.microestrutura.detectores import (
    DetectorAbsorcao,
    DetectorClipInstitucional,
    DetectorExaustao,
)

SYMBOL = "WDOFUT"
UMA_HORA_NS = 3_600_000_000_000

# Taxa REALISTA de pico do WDO. O default do simulador (5 ev/s) esvazia as
# janelas deslizantes de 5s e esconde o custo real delas.
TAXA_PICO_TRADES_S = 5_000.0


def _montar(barramento: Barramento, estagio: int) -> list[object]:
    """Liga os assinantes ate `estagio`. Retorna refs para segurar da GC."""
    vivos: list[object] = []
    if estagio >= 2:
        vivos.append(EstadoMercado(barramento, SYMBOL))
    if estagio >= 3:
        vivos.append(VolumeProfilePorPeriodo(barramento, SYMBOL, period_ns=UMA_HORA_NS))
        vivos.append(FootprintPorTimeframe(barramento, SYMBOL))
        vivos.append(CumulativeDelta(barramento, SYMBOL))
        vivos.append(MedidorAgressao(barramento, SYMBOL))
        vivos.append(RankingCorretoras(barramento, SYMBOL))
        vivos.append(VWAP(barramento, SYMBOL))
    if estagio >= 4:
        det_abs = DetectorAbsorcao(SYMBOL)
        det_exa = DetectorExaustao(SYMBOL)
        det_clip = DetectorClipInstitucional(SYMBOL)
        vivos.extend([det_abs, det_exa, det_clip])
        barramento.assinar(Trade, det_abs.ao_trade)
        barramento.assinar(Trade, det_exa.ao_trade)
        barramento.assinar(Trade, det_clip.ao_trade)
    return vivos


def _rodar(n_passos: int, estagio: int, taxa: float) -> tuple[float, int]:
    """Roda o simulador. Devolve (segundos, n_eventos_publicados)."""
    barramento = Barramento()
    vivos = _montar(barramento, estagio)
    sim = SimuladorWDO(
        barramento, seed=7, taxa_eventos_s=taxa, n_eventos=n_passos, symbol=SYMBOL
    )
    gc.collect()
    t0 = time.perf_counter()
    sim.iniciar()
    dt = time.perf_counter() - t0
    del vivos
    # o simulador publica 1 Trade + 1 BookSnapshot por passo
    return dt, n_passos * 2


def _linha(nome: str, dt: float, n_ev: int) -> str:
    eps = n_ev / dt
    us = dt * 1e6 / n_ev
    veredito = "PASSA" if eps >= 10_000 else "NAO PASSA"
    return f"{nome:<34} {dt:7.2f}s {eps:12,.0f} ev/s {us:8.2f} us/ev   {veredito}"


def bench_estagios(n_passos: int, taxa: float) -> None:
    print(f"\n{'='*92}")
    print(f"ESTAGIOS CUMULATIVOS  ({n_passos*2:,} eventos = {n_passos:,} trades + "
          f"{n_passos:,} book snapshots, taxa {taxa:,.0f} trades/s simulados)")
    print(f"{'='*92}")
    nomes = {
        1: "1. barramento vazio",
        2: "2. + EstadoMercado",
        3: "3. + analytics (6 modulos)",
    }
    for estagio in (1, 2, 3):
        dt, n_ev = _rodar(n_passos, estagio, taxa)
        print(_linha(nomes[estagio], dt, n_ev))


def bench_detectores(taxa: float) -> None:
    print(f"\n{'='*92}")
    print("ESTAGIO 4 — DETECTORES: varredura de N para expor custo nao-linear")
    print(f"{'='*92}")
    anterior = None
    for n_passos in (2_500, 5_000, 10_000, 20_000):
        dt, n_ev = _rodar(n_passos, 4, taxa)
        eps = n_ev / dt
        us = dt * 1e6 / n_ev
        escala = ""
        if anterior is not None:
            escala = f"  (dobrou N -> tempo x{dt/anterior:.2f})"
        anterior = dt
        veredito = "PASSA" if eps >= 10_000 else "NAO PASSA"
        print(f"N={n_ev:>7,} ev  {dt:7.2f}s {eps:12,.0f} ev/s {us:9.2f} us/ev  "
              f"{veredito}{escala}")
    print("\n  Custo LINEAR dobraria o tempo (x2.0) a cada N dobrado.")
    print("  Custo QUADRATICO quadruplica (x4.0).")


def bench_memoria(n_passos: int, taxa: float) -> None:
    print(f"\n{'='*92}")
    print("MEMORIA (tracemalloc — o proprio tracemalloc custa ~2x no tempo)")
    print(f"{'='*92}")
    tracemalloc.start()
    _rodar(n_passos, 3, taxa)
    atual, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"pipeline completo (estagio 3), {n_passos*2:,} eventos:")
    print(f"  pico   = {pico/1024/1024:8.1f} MB")
    print(f"  final  = {atual/1024/1024:8.1f} MB")
    print(f"  por evento = {pico/(n_passos*2):8.1f} bytes")


def bench_brokers_reais(n_trades: int) -> None:
    """O simulador NAO preenche buyer_broker/seller_broker: RankingCorretoras
    sai pela porta de tras em toda chamada. Isto mede o custo escondido."""
    print(f"\n{'='*92}")
    print("CUSTO ESCONDIDO: RankingCorretoras com corretora preenchida")
    print(f"{'='*92}")
    corretoras = [f"C{i:02d}" for i in range(40)]
    for rotulo, comprador, vendedor in (
        ("broker VAZIO (como o simulador)", "", ""),
        ("broker PREENCHIDO (como a B3)", "X", "Y"),
    ):
        barramento = Barramento()
        rank = RankingCorretoras(barramento, SYMBOL)
        trades = [
            Trade(
                timestamp_ns=i * 200_000,
                symbol=SYMBOL,
                price=10_000 + (i % 40),
                qty=1 + (i % 9),
                side_agressor=AgressorSide.BUY if i % 2 else AgressorSide.SELL,
                trade_id=str(i),
                buyer_broker=corretoras[i % 40] if comprador else "",
                seller_broker=corretoras[(i * 7) % 40] if vendedor else "",
            )
            for i in range(n_trades)
        ]
        gc.collect()
        t0 = time.perf_counter()
        for t in trades:
            barramento.publicar(t)
        dt = time.perf_counter() - t0
        print(f"  {rotulo:<36} {dt*1e6/n_trades:7.2f} us/trade   "
              f"{n_trades/dt:12,.0f} trades/s")
        del rank


def perfil(n_passos: int, taxa: float) -> None:
    print(f"\n{'='*92}")
    print("cPROFILE — pipeline completo (estagio 4), top 10 por tempo proprio")
    print(f"{'='*92}")
    pr = cProfile.Profile()
    pr.enable()
    _rodar(n_passos, 4, taxa)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(10)
    print("\n".join(s.getvalue().splitlines()[4:22]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500_000, help="total de eventos")
    ap.add_argument("--taxa", type=float, default=TAXA_PICO_TRADES_S)
    ap.add_argument("--perfil", action="store_true")
    args = ap.parse_args()

    n_passos = args.n // 2
    print(f"BARRA: 10.000 eventos/s (pico do WDO). Alvo: {args.n:,} eventos.")
    bench_estagios(n_passos, args.taxa)
    bench_detectores(args.taxa)
    bench_memoria(n_passos, args.taxa)
    bench_brokers_reais(200_000)
    if args.perfil:
        perfil(10_000, args.taxa)


if __name__ == "__main__":
    main()
