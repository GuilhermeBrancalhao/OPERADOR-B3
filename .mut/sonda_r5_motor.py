"""Sonda R5 do MOTOR — a sonda E da R3/R4 re-executada contra o gate novo,
ampliada com o controle, a varredura e o "nao e' sempre nao".
Uso: PYTHONPATH=. python .mut/sonda_r5_motor.py"""
from __future__ import annotations
from dataclasses import replace
from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, MotorSinais

SYMBOL = "WDOV26"; S = 1_000_000_000

def _trade(ts, price, qty, lado, tid="t"):
    return Trade(ts, SYMBOL, price, qty, lado, tid)

def _encher(vp, centro=5000, n=40):
    for i in range(n):
        vp.registrar_trade(_trade(i, centro - n // 2 + i, 10, AgressorSide.BUY, f"e{i}"))

cfg = ConfigMotorSinais(
    dominancia_minima=0.70, janela_dominancia_ns=60 * S, margem_regiao_ticks=0,
    janela_micro_ns=5 * S, magnitude_relativa_minima=0.60,
    persistencia_minima_trades=3, persistencia_minima_ns=S // 2,
    rebaixamento_minimo_trades=3, rebaixamento_minimo_ns=S // 2)

def rodar(n_lateral, qty_repique=9, c=cfg):
    vp = VolumeProfile(); _encher(vp)
    m = MotorSinais(SYMBOL, vp, c); ts = 0; sinais = []
    for i in range(900):  # fase 1: pico vendedor (o -1925 do relato)
        lado = AgressorSide.BUY if i % 10 == 0 else AgressorSide.SELL
        sinais.append(m.ao_trade(_trade(ts, 5000, 20, lado, f"a{i}"))); ts += 100_000_000
    for i in range(n_lateral):  # fase 2: o resto do dia, lateral e miudo
        lado = AgressorSide.BUY if i % 2 == 0 else AgressorSide.SELL
        m.ao_trade(_trade(ts, 5000, 2, lado, f"b{i}")); ts += 100_000_000
    for i in range(900):  # fase 3: o repique comprador (o +915 do relato)
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        sinais.append(m.ao_trade(_trade(ts, 5000, qty_repique, lado, f"c{i}"))); ts += 100_000_000
    n = len([s for s in sinais if s.estagio is EstagioSinal.CONFIRMADO and s.direcao is Side.BUY])
    return n, sinais[-1]

print("VARREDURA - repique de 45% do pico do dia (o modo de falha R3/R4)")
print(f"{'laterais':>10} {'CONFIRMADO compra':>18} {'mag_rel':>9} {'referencia':>11} {'pico dia':>10}  veredito")
for n_lat in (0, 1_000, 3_000, 5_000, 9_000, 20_000, 50_000):
    n, fim = rodar(n_lat); e = fim.evidencia
    print(f"{n_lat:>10,} {n:>18,} {e['magnitude_relativa']:>9.3f} "
          f"{e['magnitude_referencia']:>11,.0f} {e['magnitude_pico_sessao']:>10,}  "
          f"{'gate segurou' if n == 0 else '*** MODO DE FALHA ***'}")

print("\nCONTROLE - mesmo tape, gate desligado (magnitude_relativa_minima=0.0)")
sem = replace(cfg, magnitude_relativa_minima=0.0)
for n_lat in (0, 20_000, 50_000):
    n, _ = rodar(n_lat, c=sem)
    print(f"{n_lat:>10,} laterais -> {n:,} CONFIRMADO de compra espurios")

print("\nNAO E 'SEMPRE NAO' - repique da MAGNITUDE DO DIA (qty 20)")
for n_lat in (0, 1_000, 5_000, 20_000, 50_000):
    n, fim = rodar(n_lat, qty_repique=20)
    print(f"{n_lat:>10,} laterais -> {n:,} CONFIRMADO de compra (mag_rel="
          f"{fim.evidencia['magnitude_relativa']:.3f})")
