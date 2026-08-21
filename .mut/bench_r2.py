"""Benchmark R2 — pipeline REALMENTE completo, incluindo MotorSinais e LivroMBO.

`bench_carga.py` (do builder) para no estagio 4 com apenas 3 detectores e
NUNCA instancia `MotorSinais` — que e o produto. Este script fecha o buraco.
"""
from __future__ import annotations
import gc, sys, time, argparse, random

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
    DetectorAbsorcao, DetectorClipInstitucional, DetectorExaustao,
)
from fluxopro.motor.sinais import ConfigMotorSinais, MotorSinais

SYMBOL = "WDOFUT"
UMA_HORA_NS = 3_600_000_000_000
TAXA = 5_000.0


def montar(bar: Barramento, estagio: int):
    vivos = []
    if estagio >= 2:
        vivos.append(EstadoMercado(bar, SYMBOL))
    if estagio >= 3:
        vivos.append(VolumeProfilePorPeriodo(bar, SYMBOL, period_ns=UMA_HORA_NS))
        vivos.append(FootprintPorTimeframe(bar, SYMBOL))
        vivos.append(CumulativeDelta(bar, SYMBOL))
        vivos.append(MedidorAgressao(bar, SYMBOL))
        vivos.append(RankingCorretoras(bar, SYMBOL))
        vivos.append(VWAP(bar, SYMBOL))
    if estagio >= 4:
        for d in (DetectorAbsorcao(SYMBOL), DetectorExaustao(SYMBOL), DetectorClipInstitucional(SYMBOL)):
            vivos.append(d); bar.assinar(Trade, d.ao_trade)
    if estagio >= 5:
        # O PRODUTO. Perfil proprio alimentado pelo chamador, como manda a docstring.
        vp = VolumeProfile()
        motor = MotorSinais(SYMBOL, vp)
        def _ao_trade(t: Trade, _vp=vp, _m=motor):
            _vp.registrar_trade(t)
            _m.ao_trade(t)
        vivos.extend([vp, motor])
        bar.assinar(Trade, _ao_trade)
    return vivos


def rodar(n, estagio, taxa=TAXA):
    bar = Barramento()
    vivos = montar(bar, estagio)
    sim = SimuladorWDO(bar, seed=7, taxa_eventos_s=taxa, n_eventos=n, symbol=SYMBOL)
    gc.collect()
    t0 = time.perf_counter()
    sim.iniciar()
    dt = time.perf_counter() - t0
    del vivos
    return dt


def tape(n, taxa_trades_s, ticks=2, seed=11):
    rng = random.Random(seed)
    intervalo = int(1e9 / taxa_trades_s)
    base, ts, out = 10_000, 1_700_000_000_000_000_000, []
    for i in range(n):
        ts += intervalo
        out.append(Trade(ts, SYMBOL, base + rng.randint(0, ticks - 1), rng.randint(1, 10),
                         AgressorSide.BUY if rng.random() < 0.45 else AgressorSide.SELL, f"t{i}"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000)
    a = ap.parse_args()
    N = a.n
    print(f"BARRA = 10.000 ev/s.  N={N:,} eventos (metade trades, metade book)\n")
    print("=" * 92)
    print("ESTAGIOS CUMULATIVOS (o estagio 5 e o que bench_carga.py NAO mede)")
    print("=" * 92)
    nomes = {1: "1. barramento vazio", 2: "2. + EstadoMercado", 3: "3. + analytics (6)",
             4: "4. + 3 detectores", 5: "5. + MotorSinais  <<< PIPELINE COMPLETO"}
    for est in (1, 2, 3, 4, 5):
        n = N if est < 5 else min(N, 40_000)
        dt = rodar(n, est)
        evs = n / dt
        print(f"{nomes[est]:44} N={n:>7,}  {dt:7.2f}s  {evs:>12,.0f} ev/s  "
              f"{dt/n*1e6:7.2f} us/ev  {'PASSA' if evs >= 10_000 else '*** NAO PASSA ***'}")

    print()
    print("=" * 92)
    print("ESCALONAMENTO DO MotorSinais ISOLADO (procurando custo nao-linear)")
    print("=" * 92)
    print(f"{'N trades':>10} {'seg':>9} {'trades/s':>13} {'us/trade':>10} {'x tempo':>9}  veredito")
    ant = None
    for n in (2_000, 4_000, 8_000, 16_000, 32_000):
        trades = tape(n, 5_000)
        vp = VolumeProfile()
        m = MotorSinais(SYMBOL, vp)
        gc.collect()
        t0 = time.perf_counter()
        for t in trades:
            vp.registrar_trade(t)
            m.ao_trade(t)
        dt = time.perf_counter() - t0
        fator = f"x{dt/ant:.2f}" if ant else "-"
        ant = dt
        tps = n / dt
        print(f"{n:>10,} {dt:>9.3f} {tps:>13,.0f} {dt/n*1e6:>10.1f} {fator:>9}  "
              f"{'PASSA' if tps >= 10_000 else '*** NAO PASSA ***'}")
    print("  linear = x2.0 a cada N dobrado;  quadratico = x4.0")

    print()
    print("=" * 92)
    print("CUSTO DE value_area() SOZINHO — chamado 2x por trade em _na_regiao")
    print("=" * 92)
    for n_niveis in (50, 200, 800, 2000):
        vp = VolumeProfile()
        rng = random.Random(3)
        for i in range(n_niveis * 20):
            vp.registrar_trade(Trade(i, SYMBOL, 10_000 + rng.randrange(n_niveis), 5,
                                     AgressorSide.BUY, f"x{i}"))
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(2_000):
            vp.val(); vp.vah()
        dt = time.perf_counter() - t0
        us = dt / 2_000 * 1e6
        print(f"  {n_niveis:>5} niveis de preco -> {us:8.1f} us por trade "
              f"(so val()+vah())  => teto de {1e6/us:>10,.0f} trades/s")

    print()
    print("=" * 92)
    print("DOMINANCIA: efeito da JANELA de 5 MINUTOS (default de fabrica)")
    print("=" * 92)
    for taxa in (500, 2_000, 5_000):
        n = 20_000
        trades = tape(n, taxa)
        vp = VolumeProfile()
        m = MotorSinais(SYMBOL, vp)
        gc.collect()
        t0 = time.perf_counter()
        for t in trades:
            vp.registrar_trade(t)
            m.ao_trade(t)
        dt = time.perf_counter() - t0
        guarda = min(n, int(taxa * 300))
        print(f"  mercado a {taxa:>5,} trades/s -> janela de 5min guardaria {taxa*300:>9,} trades; "
              f"medido {n/dt:>10,.0f} trades/s  {'PASSA' if n/dt>=10_000 else '*** NAO PASSA ***'}")
    print("  (N=20k satura a janela so ate 20k; num pregao real ela chega a 1.500.000 trades)")


if __name__ == "__main__":
    main()
