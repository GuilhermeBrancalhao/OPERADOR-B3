# -*- coding: utf-8 -*-
"""Sonda R6 do MOTOR — ATAQUE. As 4 variantes que os builders da onda 8
NAO testaram. A varredura deles (0/1k/5k/9k/20k/50k laterais, sempre no
mesmo formato pico->laterais->repique) e re-executada antes, como controle.

Uso: PYTHONPATH=. python .mut/sonda_r6_motor.py
"""
from __future__ import annotations
from dataclasses import replace
from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, MotorSinais

SYMBOL = "WDOV26"
S = 1_000_000_000


def _trade(ts, price, qty, lado, tid="t"):
    return Trade(ts, SYMBOL, price, qty, lado, tid)


def _encher(vp, centro=5000, n=40):
    for i in range(n):
        vp.registrar_trade(_trade(i, centro - n // 2 + i, 10, AgressorSide.BUY, f"e{i}"))


CFG = ConfigMotorSinais(
    dominancia_minima=0.70, janela_dominancia_ns=60 * S, margem_regiao_ticks=0,
    janela_micro_ns=5 * S, magnitude_relativa_minima=0.60,
    persistencia_minima_trades=3, persistencia_minima_ns=S // 2,
    rebaixamento_minimo_trades=3, rebaixamento_minimo_ns=S // 2)


def novo(c=CFG):
    vp = VolumeProfile()
    _encher(vp)
    return MotorSinais(SYMBOL, vp, c), vp


def fase(m, ts, n, qty, dominante, passo=100_000_000, tag="x"):
    """Fase direcional: 90% no lado `dominante`."""
    contra = Side.SELL if dominante is AgressorSide.BUY else AgressorSide.BUY
    sinais = []
    for i in range(n):
        lado = (AgressorSide.SELL if dominante is AgressorSide.BUY else AgressorSide.BUY) \
            if i % 10 == 0 else dominante
        sinais.append(m.ao_trade(_trade(ts, 5000, qty, lado, f"{tag}{i}")))
        ts += passo
    return ts, sinais


def lateral(m, ts, n, qty=2, passo=100_000_000, tag="L"):
    for i in range(n):
        lado = AgressorSide.BUY if i % 2 == 0 else AgressorSide.SELL
        m.ao_trade(_trade(ts, 5000, qty, lado, f"{tag}{i}"))
        ts += passo
    return ts


def conta(sinais, direcao):
    return len([s for s in sinais if s and s.estagio is EstagioSinal.CONFIRMADO
                and s.direcao is direcao])


# ---------------------------------------------------------------- CONTROLE
print("=" * 78)
print("CONTROLE — a varredura EXATA que a onda 8 publica (deve dar 0 e mag_rel 0,450)")
print("=" * 78)
print(f"{'laterais':>10} {'CONF compra':>12} {'mag_rel':>9} {'referencia':>12} {'n_visto':>9}  veredito")
for n_lat in (0, 1_000, 5_000, 20_000, 50_000):
    m, _ = novo()
    ts, _ = fase(m, 0, 900, 20, AgressorSide.SELL, tag="a")
    ts = lateral(m, ts, n_lat)
    ts, sig = fase(m, ts, 900, 9, AgressorSide.BUY, tag="c")
    e = sig[-1].evidencia
    n = conta(sig, Side.BUY)
    print(f"{n_lat:>10,} {n:>12,} {e['magnitude_relativa']:>9.3f} "
          f"{e['magnitude_referencia'] or 0:>12,.0f} {m._n_visto:>9,}  "
          f"{'gate segurou' if n == 0 else '*** FUROU ***'}")

# ---------------------------------------------------------------- ATAQUE A
print()
print("=" * 78)
print("ATAQUE A — DOIS PICOS separados por laterais (a onda 8 so testou UM pico)")
print("  pico vendedor qty 20 -> laterais -> pico COMPRADOR qty 20 -> laterais -> repique qty 9")
print("=" * 78)
print(f"{'laterais/etapa':>15} {'CONF compra repique':>20} {'mag_rel':>9} {'referencia':>12}  veredito")
for n_lat in (0, 5_000, 20_000):
    m, _ = novo()
    ts, _ = fase(m, 0, 900, 20, AgressorSide.SELL, tag="a")
    ts = lateral(m, ts, n_lat, tag="L1")
    ts, _ = fase(m, ts, 900, 20, AgressorSide.BUY, tag="b")      # 2o pico, LEGITIMO
    ts = lateral(m, ts, n_lat, tag="L2")
    ts, sig = fase(m, ts, 900, 9, AgressorSide.BUY, tag="c")     # repique pequeno
    e = sig[-1].evidencia
    n = conta(sig, Side.BUY)
    print(f"{n_lat:>15,} {n:>20,} {e['magnitude_relativa']:>9.3f} "
          f"{e['magnitude_referencia'] or 0:>12,.0f}  "
          f"{'gate segurou' if n == 0 else '*** FUROU ***'}")

# ---------------------------------------------------------------- ATAQUE B
print()
print("=" * 78)
print("ATAQUE B — PICO GIGANTE NO FIM DO DIA (a varredura sempre poe o pico no comeco)")
print("  o pico gigante chega DEPOIS; o que ele faz com o movimento LEGITIMO seguinte?")
print("=" * 78)
print(f"{'qty do pico':>12} {'CONF do mov. legitimo':>22} {'mag_rel':>9} {'referencia':>12}  veredito")
for qty_pico in (20, 200, 2_000):
    m, _ = novo()
    ts = lateral(m, 0, 2_000, tag="L0")
    ts, _ = fase(m, ts, 900, qty_pico, AgressorSide.SELL, tag="p")   # pico gigante
    ts = lateral(m, ts, 2_000, tag="L1")
    ts, sig = fase(m, ts, 900, 20, AgressorSide.BUY, tag="m")        # movimento NORMAL
    e = sig[-1].evidencia
    n = conta(sig, Side.BUY)
    print(f"{qty_pico:>12,} {n:>22,} {e['magnitude_relativa']:>9.3f} "
          f"{e['magnitude_referencia'] or 0:>12,.0f}  "
          f"{'confirma' if n else '*** MUDO o resto do dia ***'}")

# ---------------------------------------------------------------- ATAQUE C
print()
print("=" * 78)
print("ATAQUE C — laterais com magnitude LOGO ABAIXO do filtro de negocio unico")
print("  o filtro exige magnitude > fator_dominio_trade_unico x maior_negocio da janela.")
print("  Regime de POUCOS negocios GRANDES: a magnitude da janela nunca passa 2x o")
print("  maior negocio => `_n_visto` fica em 0 => `_magnitude_referencia` devolve None")
print("  ou o max da sessao => o gate normaliza por si mesmo e fica ABERTO.")
print("=" * 78)
print(f"{'qty/negocio':>12} {'trades/janela':>14} {'n_visto':>9} {'referencia':>12} "
      f"{'mag_rel':>9} {'CONF compra':>12}  veredito")
for qty, passo_s in ((1_000, 6.0), (1_000, 3.0), (500, 6.0), (5, 0.1)):
    m, _ = novo()
    passo = int(passo_s * S)
    # dia inteiro em regime de negocio grande e esparso, dominancia vendedora
    ts, _ = fase(m, 0, 400, qty, AgressorSide.SELL, passo=passo, tag="g")
    # depois: repique comprador do MESMO tamanho (seria o modo de falha WINFUT
    # se o gate estivesse valendo)
    ts, sig = fase(m, ts, 400, qty, AgressorSide.BUY, passo=passo, tag="r")
    e = sig[-1].evidencia
    n = conta(sig, Side.BUY)
    por_janela = int(60 / passo_s)
    ref = e['magnitude_referencia']
    print(f"{qty:>12,} {por_janela:>14,} {m._n_visto:>9,} "
          f"{(ref if ref is not None else -1):>12,.0f} "
          f"{e['magnitude_relativa']:>9.3f} {n:>12,}  "
          f"{'gate ATIVO' if m._n_visto >= CFG.minimo_amostras_referencia else '*** GATE INERTE (n_visto < 32) ***'}")

# ---------------------------------------------------------------- ATAQUE D
print()
print("=" * 78)
print("ATAQUE D — SESSAO QUE VIRA NO MEIO")
print("  dia 1 com pico gigante -> iniciar_nova_sessao() -> dia 2 com movimento normal")
print("=" * 78)
m, _ = novo()
ts, _ = fase(m, 0, 900, 2_000, AgressorSide.SELL, tag="d1")
ref_antes = m._magnitude_referencia(ts)
nv_antes, max_antes, res_antes = m._n_visto, m._max_sessao, len(m._reservatorio)
m.iniciar_nova_sessao()
ref_depois = m._magnitude_referencia(ts)
print(f"  dia 1: n_visto={nv_antes:,}  max_sessao={max_antes:,}  "
      f"len(_reservatorio)={res_antes}  referencia={ref_antes}")
print(f"  apos iniciar_nova_sessao(): n_visto={m._n_visto}  max_sessao={m._max_sessao}  "
      f"len(_reservatorio)={len(m._reservatorio)}  referencia={ref_depois}")
print(f"  janela_dominancia={len(m._janela_dominancia)}  maiores_qty={len(m._maiores_qty)}  "
      f"micro={len(m._micro_antiga)}/{len(m._micro_recente)}  estagio={m._estagio_atual.value}")
zerou = (m._n_visto == 0 and m._max_sessao == 0 and not m._reservatorio
         and not m._janela_dominancia and not m._maiores_qty)
print(f"  => {'ZEROU TUDO' if zerou else '*** SOBROU ESTADO DO DIA ANTERIOR ***'}")
ts2, sig2 = fase(m, ts + 10 * S, 900, 20, AgressorSide.BUY, tag="d2")
n2 = conta(sig2, Side.BUY)
print(f"  dia 2, movimento normal (qty 20): {n2:,} CONFIRMADO de compra, "
      f"mag_rel={sig2[-1].evidencia['magnitude_relativa']:.3f}")
