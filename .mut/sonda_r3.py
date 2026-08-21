"""Sondas adversariais R3. Uso: python .mut/sonda_r3.py <letra>"""
from __future__ import annotations
import cProfile, gc, io, pstats, random, sys, time

from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import (AgressorSide, BookLevel, BookSnapshot, Side, Trade, PriceGrid)
from fluxopro.microestrutura.inferencia_mbp import InferidorMBP
from fluxopro.microestrutura.livro_mbo import LivroMBO

SYMBOL = "WDOFUT"
BASE = 1_700_000_000_000_000_000


# ---------------------------------------------------------------- A
def sonda_a():
    """Tape REALISTA: bid caindo no topo + tape 50/50 no mesmo preco.
    Metade casa (agressor SELL consome o bid), metade nao (agressor BUY)."""
    print("A. InferidorMBP — tape realista 50/50 no MESMO preco (spread de 1 tick)")
    print(f"{'taxa':>8} {'passos/s':>12} {'pend':>7} {'buf':>7}  veredito")
    for taxa in (500, 1_000, 2_000, 5_000, 10_000):
        livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
        ts = BASE; iv = max(1, int(1e9 / taxa)); n = 20_000
        rng = random.Random(4)
        inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (BookLevel(10_000, 10**9, 1),),
                                     (BookLevel(10_001, 10**9, 1),)))
        qty = 10**9
        gc.collect(); t0 = time.perf_counter()
        for i in range(n):
            ts += iv; qty -= 2
            inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (BookLevel(10_000, qty, 1),),
                                         (BookLevel(10_001, 10**9, 1),)))
            ag = AgressorSide.SELL if rng.random() < 0.5 else AgressorSide.BUY
            inf.ao_trade(Trade(ts, SYMBOL, 10_000, 1, ag, f"r{i}"))
        dt = time.perf_counter() - t0
        eps = n / dt
        print(f"{taxa:>8,} {eps:>12,.0f} {len(inf._pendentes):>7,} {len(inf._trades):>7,}  "
              f"{'PASSA' if eps >= 10_000 else '*** NAO PASSA ***'}")


# ---------------------------------------------------------------- B
def sonda_b():
    """cProfile do caso patologico para atribuir o custo."""
    livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
    ts = [BASE]; iv = int(1e9 / 5_000); n = 6_000
    inf.ao_snapshot(BookSnapshot(ts[0], SYMBOL, (BookLevel(10_000, 10**9, 1),),
                                 (BookLevel(10_001, 10**9, 1),)))
    qty = [10**9]

    def carga():
        for i in range(n):
            ts[0] += iv; qty[0] -= 1
            inf.ao_snapshot(BookSnapshot(ts[0], SYMBOL, (BookLevel(10_000, qty[0], 1),),
                                         (BookLevel(10_001, 10**9, 1),)))
            inf.ao_trade(Trade(ts[0], SYMBOL, 10_000, 1, AgressorSide.BUY, f"p{i}"))

    pr = cProfile.Profile(); pr.enable(); carga(); pr.disable()
    s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
    print(f"cProfile — {n:,} passos no caso patologico do InferidorMBP\n")
    print(s.getvalue()[:2600])


# ---------------------------------------------------------------- C
def sonda_c():
    """MT5: o feed trava permanentemente em qualquer segundo com >1000 ticks."""
    import types
    from fluxopro.dados.mt5 import AdaptadorMT5

    class _T(dict):
        class _DT:
            names = ("time_msc", "last", "bid", "ask", "volume", "volume_real", "flags")
        dtype = _DT()

    def tick(msc, preco, flags=1 << 5):
        t = _T(time_msc=msc, last=preco, bid=preco - 0.5, ask=preco,
               volume=1, volume_real=1.0, flags=flags)
        return t

    # segundo 1000 tem 3000 ticks (WDO a 3.000 negocios/s — abaixo do pico de 5-10k)
    TODOS = [tick(1_000_000 + i, 5000.0) for i in range(3000)]

    class FakeMT5(types.SimpleNamespace):
        COPY_TICKS_ALL = 1
        TICK_FLAG_BUY = 1 << 5
        TICK_FLAG_SELL = 1 << 6
        def copy_ticks_from(self, symbol, de_seg, quantos, flags):
            # contrato real do MetaTrader5: devolve os PRIMEIROS `quantos`
            # ticks a partir de `de_seg` (segundos), NAO os ultimos.
            return [t for t in TODOS if t["time_msc"] >= de_seg * 1000][:quantos]

    fake = FakeMT5()
    ad = AdaptadorMT5(Barramento(), SYMBOL, PriceGrid(0.5, 1), mt5_module=fake)
    ultimo = 0
    print("C. AdaptadorMT5._puxar_ticks — 3.000 ticks dentro do segundo 1000")
    print(f"   copy_ticks_from limitado a 1000 por poll; de = ultimo_time_msc // 1000\n")
    print(f"{'poll':>5} {'ticks novos':>12} {'ultimo_time_msc':>17} {'de(seg)':>9}")
    total = 0
    for p in range(1, 9):
        trades, ultimo = ad._puxar_ticks(fake, ultimo)
        total += len(trades)
        print(f"{p:>5} {len(trades):>12,} {ultimo:>17,} {ultimo//1000 if ultimo else 0:>9,}")
    print(f"\n   ticks entregues: {total:,} de {len(TODOS):,}. "
          f"PERDIDOS PARA SEMPRE: {len(TODOS)-total:,}")
    print("   `de` congelou no segundo 1000 e copy_ticks_from devolve sempre os")
    print("   MESMOS 1000 primeiros -> o feed nao avanca mais. Nenhuma FalhaCaptura")
    print("   e emitida: o gap detector mede intervalo de POLL, nao de DADO.")


# ---------------------------------------------------------------- D
def sonda_d():
    """Dois relogios: Trade vem do servidor MT5, BookSnapshot do relogio local."""
    print("D. Fronteira de relogio no AdaptadorMT5\n")
    print("   Trade.timestamp_ns      = time_msc * 1_000_000   (mt5.py:246)  -> relogio do SERVIDOR MT5")
    print("   BookSnapshot.timestamp_ns = time.time_ns()       (mt5.py:299)  -> relogio LOCAL (UTC)")
    print()
    print("   Servidor MetaQuotes tipico roda em GMT+2/+3. Efeito no InferidorMBP,")
    print("   cuja janela de reconciliacao e de 300 ms:\n")
    livro = LivroMBO(SYMBOL); inf = InferidorMBP(SYMBOL, livro)
    OFFSET = 3 * 3_600_000_000_000  # +3h no trade
    ts_local = BASE
    inf.ao_snapshot(BookSnapshot(ts_local, SYMBOL, (BookLevel(10_000, 100, 1),),
                                 (BookLevel(10_001, 100, 1),)))
    eventos = []
    livro.assinar_evento(lambda e: eventos.append(e))
    # o bid cai 40 (relogio local) e um negocio de 40 no mesmo preco imprime
    # 1 ms depois (relogio do servidor, +3h)
    inf.ao_snapshot(BookSnapshot(ts_local + 1_000_000, SYMBOL,
                                 (BookLevel(10_000, 60, 1),), (BookLevel(10_001, 100, 1),)))
    inf.ao_trade(Trade(ts_local + 2_000_000 + OFFSET, SYMBOL, 10_000, 40,
                       AgressorSide.SELL, "x1"))
    inf.drenar(ts_local + 3_000_000 + OFFSET)
    from collections import Counter
    c = Counter(e.tipo.name for e in eventos)
    print(f"   com offset de +3h no trade -> eventos gerados: {dict(c)}")
    # controle: mesmo relogio
    livro2 = LivroMBO(SYMBOL); inf2 = InferidorMBP(SYMBOL, livro2)
    ev2 = []
    inf2.ao_snapshot(BookSnapshot(ts_local, SYMBOL, (BookLevel(10_000, 100, 1),),
                                  (BookLevel(10_001, 100, 1),)))
    livro2.assinar_evento(lambda e: ev2.append(e))
    inf2.ao_snapshot(BookSnapshot(ts_local + 1_000_000, SYMBOL,
                                  (BookLevel(10_000, 60, 1),), (BookLevel(10_001, 100, 1),)))
    inf2.ao_trade(Trade(ts_local + 2_000_000, SYMBOL, 10_000, 40, AgressorSide.SELL, "x1"))
    inf2.drenar(ts_local + 3_000_000)
    c2 = Counter(e.tipo.name for e in ev2)
    print(f"   CONTROLE, um relogio so       -> eventos gerados: {dict(c2)}")
    print()
    print("   A MESMA sequencia de mercado produz microestrutura diferente so por")
    print("   causa do relogio. Nenhum teste cobre a fronteira: o mock injeta")
    print("   time_msc coerente com o relogio local da maquina de teste.")


if __name__ == "__main__":
    {"a": sonda_a, "b": sonda_b, "c": sonda_c, "d": sonda_d}[sys.argv[1]]()
