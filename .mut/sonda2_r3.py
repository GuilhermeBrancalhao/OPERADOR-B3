"""Sondas de SISTEMA R3 (juncoes, nao unidades). Uso: python .mut/sonda2_r3.py <letra>"""
from __future__ import annotations
import gc, random, sys, tempfile, time
from dataclasses import replace
from pathlib import Path

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import ConfigFootprint, Footprint, FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfile, VolumeProfilePorPeriodo
from fluxopro.analytics.vwap import VWAP
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import AgressorSide, BookSnapshot, Side, Trade
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.microestrutura.detectores import (
    DetectorAbsorcao, DetectorClipInstitucional, DetectorExaustao)
from fluxopro.microestrutura.perfil_player import PerfilPlayer
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, MotorSinais

SYMBOL = "WDOV26"
S = 1_000_000_000


def _trade(ts, price, qty, lado, tid="t"):
    return Trade(ts, SYMBOL, price, qty, lado, tid)


def _encher(vp, centro=5000, n=40):
    for i in range(n):
        vp.registrar_trade(_trade(i, centro - n // 2 + i, 10, AgressorSide.BUY, f"e{i}"))


# ---------------------------------------------------------------- E
def sonda_e():
    """WINFUT que ATRAVESSA o gate de magnitude: basta o pico extremo ser
    uma fracao pequena do dia — que e exatamente o caso do relato."""
    cfg = ConfigMotorSinais(
        dominancia_minima=0.70, janela_dominancia_ns=60 * S, margem_regiao_ticks=0,
        janela_micro_ns=5 * S, magnitude_relativa_minima=0.60,
        percentil_magnitude_referencia=0.95, persistencia_minima_trades=3,
        persistencia_minima_ns=S // 2, rebaixamento_minimo_trades=3,
        rebaixamento_minimo_ns=S // 2)

    def rodar(n_lateral):
        vp = VolumeProfile(); _encher(vp)
        m = MotorSinais(SYMBOL, vp, cfg)
        ts = 0; sinais = []
        # fase 1: pico vendedor de magnitude ALTA (o -1925 do relato)
        for i in range(900):
            lado = AgressorSide.BUY if i % 10 == 0 else AgressorSide.SELL
            sinais.append(m.ao_trade(_trade(ts, 5000, 20, lado, f"a{i}"))); ts += 100_000_000
        # fase 2: o RESTO DO DIA lateral e miudo (equilibrado -> magnitude baixa)
        for i in range(n_lateral):
            lado = AgressorSide.BUY if i % 2 == 0 else AgressorSide.SELL
            m.ao_trade(_trade(ts, 5000, 2, lado, f"b{i}")); ts += 100_000_000
        # fase 3: o repique comprador de magnitude MENOR (o +915 do relato)
        for i in range(900):
            lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
            sinais.append(m.ao_trade(_trade(ts, 5000, 9, lado, f"c{i}"))); ts += 100_000_000
        compras = [s for s in sinais if s.estagio is EstagioSinal.CONFIRMADO and s.direcao is Side.BUY]
        return len(compras), sinais[-1]

    print("E. Variante do WINFUT que PASSA pelo gate de magnitude")
    print("   (fase 1 pico vendedor qty20; fase 2 lateral qty2; fase 3 repique comprador qty9)")
    print(f"\n{'trades laterais':>16} {'CONFIRMADO de COMPRA':>22} {'magnitude_rel final':>21}  veredito")
    for n_lat in (0, 900, 3_000, 9_000, 20_000):
        n, fim = rodar(n_lat)
        mr = fim.evidencia.get("magnitude_relativa")
        mrs = f"{mr:.3f}" if isinstance(mr, (int, float)) else str(mr)
        print(f"{n_lat:>16,} {n:>22,} {mrs:>21}  "
              f"{'gate segurou' if n == 0 else '*** MODO DE FALHA WINFUT ***'}")
    print("\n   O teste do repo usa n_lateral=0 — o unico ponto da curva em que o")
    print("   gate segura. A referencia e o p95 de uma amostra de reservoir do DIA:")
    print("   se o pico extremo for <5% do dia (que e o caso de um pico de abertura),")
    print("   o p95 desce ate o regime lateral e o repique passa.")


# ---------------------------------------------------------------- F
def sonda_f():
    """Virar a sessao zera TUDO? Quem guarda estado que sobrevive indevidamente?"""
    print("F. Virada de sessao — quem tem `iniciar_nova_sessao` e quem nao tem\n")
    bar = Barramento()
    alvos = {
        "EstadoMercado": EstadoMercado(bar, SYMBOL),
        "VolumeProfilePorPeriodo": VolumeProfilePorPeriodo(bar, SYMBOL, period_ns=3_600 * S),
        "CumulativeDelta": CumulativeDelta(bar, SYMBOL),
        "MedidorAgressao": MedidorAgressao(bar, SYMBOL),
        "VWAP": VWAP(bar, SYMBOL),
        "FootprintPorTimeframe": FootprintPorTimeframe(bar, SYMBOL),
        "RankingCorretoras": RankingCorretoras(bar, SYMBOL),
        "PerfilPlayer": PerfilPlayer(SYMBOL),
        "DetectorAbsorcao": DetectorAbsorcao(SYMBOL),
        "DetectorExaustao": DetectorExaustao(SYMBOL),
        "DetectorClipInstitucional": DetectorClipInstitucional(SYMBOL),
        "MotorSinais": MotorSinais(SYMBOL, VolumeProfile()),
    }
    tem, nao = [], []
    for nome, obj in alvos.items():
        (tem if hasattr(obj, "iniciar_nova_sessao") else nao).append(nome)
    print("   TEM iniciar_nova_sessao:")
    for n in tem:
        print(f"      OK   {n}")
    print("   NAO TEM (estado do dia 1 sobrevive ao dia 2):")
    for n in nao:
        print(f"      X    {n}")

    # prova concreta: o reservatorio de magnitude do MotorSinais e "do dia"
    vp = VolumeProfile(); _encher(vp)
    m = MotorSinais(SYMBOL, vp)
    for i in range(2000):
        m.ao_trade(_trade(i * 100_000, 5000, 500, AgressorSide.SELL, f"d1-{i}"))
    ref_d1 = m._magnitude_referencia(10**15)
    # "dia 2": um salto de 24h no timestamp, que e o que o mercado faz
    s = m.ao_trade(_trade(86_400 * S, 5000, 1, AgressorSide.BUY, "d2-0"))
    ref_d2 = m._magnitude_referencia(86_400 * S + 1)
    print(f"\n   MotorSinais: p95 da magnitude ao fim do 'dia 1' = {ref_d1:,.0f}")
    print(f"                p95 apos salto de 24h no timestamp  = {ref_d2:,.0f}")
    print(f"                -> a referencia do dia 2 e a do dia 1. O gate de magnitude")
    print(f"                   do dia 2 esta calibrado por um dia que ja acabou.")
    print(f"   PerfilPlayer/RankingCorretoras: acumulam desde a criacao, sem janela")
    print(f"   default (RankingCorretoras.janela_ns e None de fabrica).")
    print(f"   DetectorEscora/IcebergPorRecarga: `_ja_sinalizado` nunca e limpo ->")
    print(f"   nivel sinalizado no dia 1 fica mudo para sempre.")


# ---------------------------------------------------------------- G
def _pipeline(bar):
    vp = VolumeProfile()
    motor = MotorSinais(SYMBOL, vp, ConfigMotorSinais())
    det = DetectorAbsorcao(SYMBOL)
    saida = []
    def _t(t):
        vp.registrar_trade(t)
        s = motor.ao_trade(t)
        d = det.ao_trade(t)
        saida.append((t.timestamp_ns, s.estagio.name, s.direcao.name if s.direcao else "-",
                      round(s.evidencia.get("dominancia", 0.0), 6),
                      "D" if d else "."))
    bar.assinar(Trade, _t)
    return saida, [vp, motor, det, _t]


def sonda_g():
    """Reprodutibilidade: o replay de um arquivo gravado devolve os MESMOS
    sinais que a passagem ao vivo? E a base de qualquer backtest."""
    from fluxopro.gravacao.gravador import Gravador
    from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao

    print("G. Replay de gravacao x passagem ao vivo — mesmos sinais?\n")
    N = 4_000
    tmp = Path(tempfile.mkdtemp(prefix="r3_repro_"))

    # 1) ao vivo, gravando
    bar = Barramento()
    saida_vivo, vivos = _pipeline(bar)
    grav = Gravador(bar, saida_dir=tmp)
    grav.iniciar()
    sim = SimuladorWDO(bar, seed=99, taxa_eventos_s=5000, n_eventos=N, symbol=SYMBOL)
    sim.iniciar()
    grav.parar()
    print(f"   ao vivo:  {len(saida_vivo):,} trades processados")

    dias = sorted(p for p in (tmp / SYMBOL).iterdir()) if (tmp / SYMBOL).is_dir() else []
    if not dias:
        print("   !! nada gravado — abortando"); return
    print(f"   gravado em: {dias[0]}")
    print(f"   arquivos: {sorted(p.name for p in dias[0].iterdir())}")

    # 2) replay do que foi gravado
    from fluxopro.gravacao.catalogo import Catalogo
    cat = Catalogo(tmp); cat.escanear()
    entrada = cat.listar()[0]
    bar2 = Barramento()
    saida_replay, vivos2 = _pipeline(bar2)
    leitor = AdaptadorLeitorGravacao(bar2, entrada, catalogo=cat)
    leitor.iniciar()
    print(f"   replay:   {len(saida_replay):,} trades processados")

    if len(saida_vivo) != len(saida_replay):
        print(f"\n   *** CONTAGEM DIFERE: vivo={len(saida_vivo):,} replay={len(saida_replay):,}")
    n = min(len(saida_vivo), len(saida_replay))
    difs = [i for i in range(n) if saida_vivo[i] != saida_replay[i]]
    print(f"\n   linhas comparadas: {n:,}   DIVERGENCIAS: {len(difs):,}")
    for i in difs[:5]:
        print(f"      idx {i}: vivo={saida_vivo[i]}")
        print(f"              replay={saida_replay[i]}")
    if not difs and len(saida_vivo) == len(saida_replay):
        print("   -> replay reproduz o vivo neste cenario.")


# ---------------------------------------------------------------- H
def sonda_h():
    """Determinismo sob carga: 2 execucoes de 500k eventos, resultado identico?"""
    print("H. Determinismo sob carga — 500.000 eventos, duas execucoes\n")
    def uma():
        bar = Barramento()
        saida, vivos = _pipeline(bar)
        sim = SimuladorWDO(bar, seed=2026, taxa_eventos_s=5000, n_eventos=250_000, symbol=SYMBOL)
        t0 = time.perf_counter(); sim.iniciar(); dt = time.perf_counter() - t0
        return saida, dt
    a, dta = uma()
    b, dtb = uma()
    print(f"   execucao 1: {len(a):,} trades em {dta:6.2f}s ({500_000/dta:,.0f} ev/s)")
    print(f"   execucao 2: {len(b):,} trades em {dtb:6.2f}s ({500_000/dtb:,.0f} ev/s)")
    if a == b:
        print("   -> IDENTICAS (deterministico)")
    else:
        d = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
        print(f"   -> DIVERGEM em {len(d):,} pontos; 1o em idx {d[0] if d else '?'}")


# ---------------------------------------------------------------- I
def sonda_i():
    """qty_minima_imbalance = 0 de fabrica: quantos niveis o footprint marca?"""
    print("I. Footprint — taxa de marcacao do imbalance diagonal com o default\n")
    rng = random.Random(5)
    for cfg, rot in ((ConfigFootprint(), "default (qty_minima_imbalance=0)"),
                     (ConfigFootprint(qty_minima_imbalance=20), "com piso de 20 lotes")):
        fp = Footprint(cfg)
        precos = set()
        for i in range(4_000):
            p = 5000 + rng.randint(-40, 40)
            precos.add(p)
            fp.registrar_trade(_trade(i * 10**6, p, rng.randint(1, 5),
                                      AgressorSide.BUY if rng.random() < 0.5 else AgressorSide.SELL,
                                      f"f{i}"))
        c = fp.niveis_imbalance_compra(); v = fp.niveis_imbalance_venda()
        print(f"   {rot:34} niveis={len(precos):>3}  "
              f"imb_compra={len(c):>3} ({100*len(c)/len(precos):5.1f}%)  "
              f"imb_venda={len(v):>3} ({100*len(v)/len(precos):5.1f}%)")
    print("\n   Num candle esparso (o caso comum de 1 min de WDO num tick fino) quase")
    print("   todo nivel sem vizinho diagonal e marcado: `qty_vizinho == 0` -> append")
    print("   incondicional (footprint.py:165-166 e :181-182). O piso que existiria")
    print("   para barrar isso (`qty_minima_imbalance`) vem 0 de fabrica.")


if __name__ == "__main__":
    {"e": sonda_e, "f": sonda_f, "g": sonda_g, "h": sonda_h, "i": sonda_i}[sys.argv[1]]()
