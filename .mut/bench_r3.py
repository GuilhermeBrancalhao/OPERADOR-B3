"""Benchmark R3 — medicao independente. Nada aqui reutiliza numero de builder.

Estagio 6 = a configuracao REAL (MotorSinais + LivroMBO + InferidorMBP +
os 3 detectores de MBO), que nem bench_carga.py nem bench_motor.py montam.
"""
from __future__ import annotations
import gc, random, statistics, sys, time

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfile, VolumeProfilePorPeriodo
from fluxopro.analytics.vwap import VWAP
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Side, Trade
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.microestrutura.detectores import (
    DetectorAbsorcao, DetectorClipInstitucional, DetectorEscora,
    DetectorExaustao, DetectorIcebergPorRecarga, DetectorLiquidezFantasma,
)
from fluxopro.microestrutura.inferencia_mbp import InferidorMBP
from fluxopro.microestrutura.livro_mbo import LivroMBO
from fluxopro.microestrutura.perfil_player import PerfilPlayer
from fluxopro.motor.sinais import ConfigMotorSinais, MotorSinais

SYMBOL = "WDOFUT"
UMA_HORA_NS = 3_600_000_000_000
BARRA = 10_000


def v(eps):
    return "PASSA" if eps >= BARRA else "*** NAO PASSA ***"


def montar(bar, estagio):
    vivos = []
    if estagio >= 2:
        vivos.append(EstadoMercado(bar, SYMBOL))
    if estagio >= 3:
        vivos += [VolumeProfilePorPeriodo(bar, SYMBOL, period_ns=UMA_HORA_NS),
                  FootprintPorTimeframe(bar, SYMBOL), CumulativeDelta(bar, SYMBOL),
                  MedidorAgressao(bar, SYMBOL), RankingCorretoras(bar, SYMBOL),
                  VWAP(bar, SYMBOL)]
    if estagio >= 4:
        for d in (DetectorAbsorcao(SYMBOL), DetectorExaustao(SYMBOL), DetectorClipInstitucional(SYMBOL)):
            vivos.append(d); bar.assinar(Trade, d.ao_trade)
    if estagio >= 5:
        vp = VolumeProfile()
        motor = MotorSinais(SYMBOL, vp, ConfigMotorSinais())
        def _t(t, _vp=vp, _m=motor):
            _vp.registrar_trade(t); _m.ao_trade(t)
        vivos += [vp, motor, _t]; bar.assinar(Trade, _t)
    if estagio >= 6:
        # A configuracao REAL: sem MBO nativo, o caminho e MBP -> InferidorMBP -> LivroMBO
        # -> os 3 detectores que consomem OrdemEvento. Ninguem mediu isso.
        livro = LivroMBO(SYMBOL)
        inf = InferidorMBP(SYMBOL, livro)
        esc = DetectorEscora(); ice = DetectorIcebergPorRecarga(); fant = DetectorLiquidezFantasma(0.5)
        # Os 3 detectores de MBO expoem `verificar(...)` (API de PULL) e nao
        # tem chamador de producao no nucleo. A fiacao abaixo e MINHA, escrita
        # so para conseguir medir o custo — ela nao existe no repositorio.
        def _ao_evento(ev, _l=livro, _e=esc, _i=ice, _f=fant):
            _e.verificar(_l, ev.side, ev.price, ev.timestamp_ns)
            if ev.order_id:
                o = _l.ordem(ev.order_id)
                if o is not None:
                    _i.verificar(o, SYMBOL, ev.timestamp_ns)
                    oposto = _l.melhor_ask() if ev.side is Side.BUY else _l.melhor_bid()
                    _f.verificar(o, SYMBOL, oposto)
        livro.assinar_evento(_ao_evento)
        perfil = PerfilPlayer(SYMBOL)
        vivos += [livro, inf, esc, ice, fant, perfil]
        bar.assinar(Trade, inf.ao_trade)
        bar.assinar(Trade, perfil.ao_trade)
        bar.assinar(BookSnapshot, inf.ao_snapshot)
    return vivos


def rodar(n, estagio, taxa=5000.0):
    bar = Barramento()
    vivos = montar(bar, estagio)
    sim = SimuladorWDO(bar, seed=7, taxa_eventos_s=taxa, n_eventos=n, symbol=SYMBOL)
    gc.collect()
    t0 = time.perf_counter(); sim.iniciar(); dt = time.perf_counter() - t0
    del vivos
    return dt


def tape(n, taxa, ticks=2, seed=11):
    rng = random.Random(seed)
    iv = max(1, int(1e9 / taxa)); ts = 1_700_000_000_000_000_000; out = []
    for i in range(n):
        ts += iv
        out.append(Trade(ts, SYMBOL, 10_000 + rng.randint(0, ticks - 1), rng.randint(1, 10),
                         AgressorSide.BUY if rng.random() < 0.45 else AgressorSide.SELL, f"t{i}"))
    return out


def secao(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


def main():
    N = 100_000
    secao(f"1. ESTAGIOS CUMULATIVOS  (N={N:,} passos = {N*2:,} eventos)  BARRA={BARRA:,} ev/s")
    nomes = {1: "1. barramento vazio", 2: "2. + EstadoMercado", 3: "3. + analytics (6)",
             4: "4. + 3 detectores de tape", 5: "5. + MotorSinais",
             6: "6. + LivroMBO+InferidorMBP+3 det MBO+PerfilPlayer  <<< CONFIG REAL"}
    for est in (1, 2, 3, 4, 5, 6):
        n = N if est < 5 else 40_000
        dt = rodar(n, est); eps = (n * 2) / dt
        print(f"{nomes[est]:56} N={n*2:>8,}ev {dt:7.2f}s {eps:>12,.0f} ev/s  {v(eps)}")

    secao("2. MotorSinais ISOLADO — escalonamento (linear=x2 ao dobrar N; quadratico=x4)")
    print(f"{'N trades':>10} {'seg':>9} {'trades/s':>13} {'us/trade':>10} {'x tempo':>9}  veredito")
    ant = None
    for n in (2_000, 8_000, 32_000, 128_000):
        tr = tape(n, 5_000); vp = VolumeProfile(); m = MotorSinais(SYMBOL, vp)
        gc.collect(); t0 = time.perf_counter()
        for t in tr:
            vp.registrar_trade(t); m.ao_trade(t)
        dt = time.perf_counter() - t0
        fator = f"x{dt/ant:.2f}" if ant else "-"; ant = dt
        print(f"{n:>10,} {dt:>9.3f} {n/dt:>13,.0f} {dt/n*1e6:>10.1f} {fator:>9}  {v(n/dt)}")
        ant = dt

    secao("3. InferidorMBP — o teste do builder (niveis PENDURADOS, negocio que nao casa)")
    for k in (50, 200, 800, 3000):
        livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
        ts = 1_700_000_000_000_000_000
        # pendura k niveis com queda pendente que nunca casa
        for i in range(k):
            inf.ao_delta_qty = None
        snap1 = BookSnapshot(ts, SYMBOL,
                             tuple(BookLevel(10_000 - i, 100, 1) for i in range(k)),
                             tuple(BookLevel(20_000 + i, 100, 1) for i in range(k)))
        inf.ao_snapshot(snap1)
        snap2 = BookSnapshot(ts + 1000, SYMBOL,
                             tuple(BookLevel(10_000 - i, 50, 1) for i in range(k)),
                             tuple(BookLevel(20_000 + i, 50, 1) for i in range(k)))
        inf.ao_snapshot(snap2)
        n = 20_000
        trades = [Trade(ts + 2000 + i, SYMBOL, 50_000 + i, 1, AgressorSide.BUY, f"n{i}") for i in range(n)]
        gc.collect(); t0 = time.perf_counter()
        for t in trades:
            inf.ao_trade(t)
        dt = time.perf_counter() - t0
        print(f"  {k:>5} niveis pendurados -> {n/dt:>12,.0f} neg/s  {v(n/dt)}")

    secao("4. InferidorMBP — o caso REAL do WDO: book ESTREITO, tudo no mesmo preco")
    print("  (o indice por preco protege book LARGO; o WDO negocia em 2-3 precos)")
    for taxa in (1_000, 5_000, 10_000):
        livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
        ts = 1_700_000_000_000_000_000
        iv = max(1, int(1e9 / taxa))
        n = 20_000
        gc.collect(); t0 = time.perf_counter()
        for i in range(n):
            ts += iv
            # negocio no MESMO preco, agressor BUY -> lado passivo SELL.
            # A queda pendente e do lado BUY: `_lado_casa` recusa -> item fica
            # no bucket e e re-varrido a cada nova queda.
            inf.ao_trade(Trade(ts, SYMBOL, 10_000, 1, AgressorSide.BUY, f"m{i}"))
        dt = time.perf_counter() - t0
        print(f"  tape a {taxa:>6,}/s, 1 preco so -> {n/dt:>12,.0f} neg/s  {v(n/dt)}  "
              f"(buffer final={len(inf._trades):,})")

    secao("5. InferidorMBP — quedas pendentes NO MESMO PRECO (patologia do indice)")
    for taxa in (1_000, 5_000, 10_000):
        livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
        ts = 1_700_000_000_000_000_000
        iv = max(1, int(1e9 / taxa)); n = 20_000
        inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (BookLevel(10_000, 10**9, 1),), (BookLevel(10_001, 10**9, 1),)))
        qty = 10**9
        gc.collect(); t0 = time.perf_counter()
        for i in range(n):
            ts += iv; qty -= 1
            # queda de 1 lote no bid + negocio de compra (lado passivo = SELL, nao casa com o bid)
            inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (BookLevel(10_000, qty, 1),), (BookLevel(10_001, 10**9, 1),)))
            inf.ao_trade(Trade(ts, SYMBOL, 10_000, 1, AgressorSide.BUY, f"p{i}"))
        dt = time.perf_counter() - t0
        print(f"  tape a {taxa:>6,}/s -> {n/dt:>12,.0f} passos/s  {v(n/dt)}  "
              f"(pendentes={len(inf._pendentes):,} buffer={len(inf._trades):,})")


if __name__ == "__main__":
    main()
