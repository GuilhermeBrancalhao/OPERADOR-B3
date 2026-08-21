"""Benchmark do `MotorSinais` — o modulo que a critica R2 mediu em 258 ev/s.

A barra e a mesma do resto do projeto: 10.000 eventos/s (pico do WDO).

Tres medicoes, nesta ordem:

  1. MOTOR ISOLADO      -> N trades direto em `MotorSinais.ao_trade`, com um
                           `VolumeProfile` realista (centenas de niveis de
                           preco, que e o que faz `value_area()` doer).
  2. ESCALONAMENTO      -> dobra N e mostra o us/ev. Custo O(1) por evento
                           mantem o us/ev PLANO; custo quadratico o DOBRA a
                           cada dobra de N (foi o que a R2 mediu: fatores de
                           x4,64 / x4,31 / x3,16 / x4,38 no tempo total).
  3. PIPELINE COMPLETO  -> barramento + EstadoMercado + 6 analytics + 3
                           detectores + MotorSinais. E o estagio que
                           `bench_carga.py` NAO mede (ele para nos detectores).

Uso:
    python bench_motor.py                    # completo
    python bench_motor.py --n 200000         # motor isolado com N trades
    python bench_motor.py --escala-base 2000 --escala-dobras 5
    python bench_motor.py --perfil           # + cProfile do motor isolado
    python bench_motor.py --so-escala        # so a tabela de escalonamento
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import io
import pstats
import random
import time

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfile, VolumeProfilePorPeriodo
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
from fluxopro.motor.sinais import ConfigMotorSinais, MotorSinais

SYMBOL = "WDOFUT"
UMA_HORA_NS = 3_600_000_000_000
BARRA_EV_S = 10_000

# Taxa de pico do WDO. Importa MUITO aqui: e ela que define quantos trades a
# janela de 5 minutos do motor guarda (a 5.000 trades/s sao 1.500.000).
TAXA_PICO_TRADES_S = 5_000.0


def _tape(n: int, seed: int = 7, taxa: float = TAXA_PICO_TRADES_S) -> list[Trade]:
    """Tape sintetico deterministico com CENTENAS de niveis de preco distintos.

    A quantidade de niveis e o que faz `value_area()` custar: a R2 mediu
    969,6 us/trade com 800 niveis. Um random walk de N passos com passo +-1
    tick cobre ~sqrt(N) niveis, o que da ~450 niveis em 200 mil trades — a
    ordem de grandeza de um pregao de WDO.
    """
    rng = random.Random(seed)
    passo_ns = int(1e9 / taxa)
    preco = 500_000
    trades: list[Trade] = []
    for i in range(n):
        preco += rng.choice((-1, 0, 0, 1))
        lado = AgressorSide.BUY if rng.random() < 0.55 else AgressorSide.SELL
        trades.append(
            Trade(
                timestamp_ns=i * passo_ns,
                symbol=SYMBOL,
                price=preco,
                qty=rng.randint(1, 20),
                side_agressor=lado,
                trade_id=str(i),
            )
        )
    return trades


def _motor_e_perfil() -> tuple[MotorSinais, VolumeProfile]:
    vp = VolumeProfile()
    return MotorSinais(SYMBOL, vp, ConfigMotorSinais()), vp


def _rodar_motor(trades: list[Trade]) -> float:
    """Alimenta motor + perfil (o chamador e quem alimenta o perfil, por
    contrato do `MotorSinais`). Devolve segundos."""
    motor, vp = _motor_e_perfil()
    gc.collect()
    t0 = time.perf_counter()
    for t in trades:
        vp.registrar_trade(t)
        motor.ao_trade(t)
    dt = time.perf_counter() - t0
    del motor, vp
    return dt


def _veredito(eps: float) -> str:
    return "PASSA" if eps >= BARRA_EV_S else "NAO PASSA"


def bench_isolado(n: int) -> None:
    print(f"\n{'=' * 92}")
    print(f"1. MOTOR ISOLADO — {n:,} trades por `MotorSinais.ao_trade`")
    print(f"{'=' * 92}")
    trades = _tape(n)
    niveis = len({t.price for t in trades})
    dt = _rodar_motor(trades)
    eps = n / dt
    print(
        f"  {n:>9,} trades  {dt:8.3f}s  {eps:12,.0f} ev/s  "
        f"{dt * 1e6 / n:8.2f} us/ev   {_veredito(eps)}"
        f"   ({niveis} niveis de preco distintos)"
    )


def bench_escalonamento(base: int, dobras: int) -> None:
    print(f"\n{'=' * 92}")
    print("2. ESCALONAMENTO — dobra N; us/ev PLANO = O(1)/evento, us/ev DOBRANDO = quadratico")
    print(f"{'=' * 92}")
    print(f"  {'N trades':>10}  {'seg':>9}  {'ev/s':>12}  {'us/ev':>9}  "
          f"{'fator tempo':>12}  {'fator us/ev':>12}")
    anterior_dt = None
    anterior_us = None
    for i in range(dobras):
        n = base * (2 ** i)
        dt = _rodar_motor(_tape(n))
        us = dt * 1e6 / n
        f_dt = f"x{dt / anterior_dt:.2f}" if anterior_dt else "—"
        f_us = f"x{us / anterior_us:.2f}" if anterior_us else "—"
        anterior_dt, anterior_us = dt, us
        print(f"  {n:>10,}  {dt:9.3f}  {n / dt:12,.0f}  {us:9.2f}  "
              f"{f_dt:>12}  {f_us:>12}   {_veredito(n / dt)}")
    print("\n  LINEAR: fator tempo ~x2,0 e fator us/ev ~x1,0 (custo por evento plano).")
    print("  QUADRATICO: fator tempo ~x4,0 e fator us/ev ~x2,0.")


def _montar_pipeline(barramento: Barramento, com_motor: bool) -> list[object]:
    vivos: list[object] = [
        EstadoMercado(barramento, SYMBOL),
        VolumeProfilePorPeriodo(barramento, SYMBOL, period_ns=UMA_HORA_NS),
        FootprintPorTimeframe(barramento, SYMBOL),
        CumulativeDelta(barramento, SYMBOL),
        MedidorAgressao(barramento, SYMBOL),
        RankingCorretoras(barramento, SYMBOL),
        VWAP(barramento, SYMBOL),
    ]
    det_abs = DetectorAbsorcao(SYMBOL)
    det_exa = DetectorExaustao(SYMBOL)
    det_clip = DetectorClipInstitucional(SYMBOL)
    vivos.extend([det_abs, det_exa, det_clip])
    barramento.assinar(Trade, det_abs.ao_trade)
    barramento.assinar(Trade, det_exa.ao_trade)
    barramento.assinar(Trade, det_clip.ao_trade)
    if com_motor:
        vp = VolumeProfile()
        motor = MotorSinais(SYMBOL, vp, ConfigMotorSinais())
        vivos.extend([vp, motor])

        def _ao_trade(trade: Trade) -> None:
            vp.registrar_trade(trade)
            motor.ao_trade(trade)

        vivos.append(_ao_trade)
        barramento.assinar(Trade, _ao_trade)
    return vivos


def bench_pipeline(n_passos: int, taxa: float) -> None:
    print(f"\n{'=' * 92}")
    print(f"3. PIPELINE COMPLETO — {n_passos * 2:,} eventos "
          f"({n_passos:,} trades + {n_passos:,} snapshots), taxa {taxa:,.0f} trades/s")
    print(f"{'=' * 92}")
    for rotulo, com_motor in (
        ("4. + 3 detectores (SEM motor)", False),
        ("5. + MotorSinais", True),
    ):
        barramento = Barramento()
        vivos = _montar_pipeline(barramento, com_motor)
        sim = SimuladorWDO(
            barramento, seed=7, taxa_eventos_s=taxa, n_eventos=n_passos, symbol=SYMBOL
        )
        gc.collect()
        t0 = time.perf_counter()
        sim.iniciar()
        dt = time.perf_counter() - t0
        del vivos
        n_ev = n_passos * 2
        eps = n_ev / dt
        print(f"  {rotulo:<32} {dt:8.2f}s {eps:12,.0f} ev/s "
              f"{dt * 1e6 / n_ev:8.2f} us/ev   {_veredito(eps)}")


def perfil(n: int) -> None:
    print(f"\n{'=' * 92}")
    print(f"cPROFILE — motor isolado, {n:,} trades, top 12 por tempo proprio")
    print(f"{'=' * 92}")
    trades = _tape(n)
    pr = cProfile.Profile()
    pr.enable()
    _rodar_motor(trades)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
    print("\n".join(s.getvalue().splitlines()[4:24]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200_000, help="trades no motor isolado")
    ap.add_argument("--escala-base", type=int, default=25_000)
    ap.add_argument("--escala-dobras", type=int, default=5)
    ap.add_argument("--pipeline-n", type=int, default=40_000, help="passos do simulador")
    ap.add_argument("--taxa", type=float, default=TAXA_PICO_TRADES_S)
    ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--so-escala", action="store_true")
    ap.add_argument("--so-isolado", action="store_true")
    args = ap.parse_args()

    print(f"BARRA: {BARRA_EV_S:,} eventos/s (pico do WDO).")
    if args.so_escala:
        bench_escalonamento(args.escala_base, args.escala_dobras)
        return
    if args.so_isolado:
        bench_isolado(args.n)
        return
    bench_isolado(args.n)
    bench_escalonamento(args.escala_base, args.escala_dobras)
    bench_pipeline(args.pipeline_n, args.taxa)
    if args.perfil:
        perfil(min(args.n, 50_000))


if __name__ == "__main__":
    main()
