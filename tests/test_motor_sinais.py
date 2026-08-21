from __future__ import annotations

from dataclasses import replace

from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, MotorSinais


def _trade(ts, price, qty, agressor, symbol="WDOV26"):
    return Trade(
        timestamp_ns=ts, symbol=symbol, price=price, qty=qty,
        side_agressor=agressor, trade_id=f"t{ts}",
    )


def _motor(**overrides):
    cfg = ConfigMotorSinais(
        dominancia_minima=0.70,
        janela_dominancia_ns=10_000_000_000,
        margem_regiao_ticks=0,
        janela_micro_ns=5_000_000_000,
        pre_sinal_fracao_janela_micro=0.5,
    )
    if overrides:
        cfg = replace(cfg, **overrides)
    vp = VolumeProfile()
    return MotorSinais("WDOV26", vp, cfg), vp


def test_sem_dominancia_fica_em_nenhum():
    motor, _ = _motor()
    sinal = motor.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY))
    sinal = motor.ao_trade(_trade(1, 5000, 10, AgressorSide.SELL))
    assert sinal.estagio is EstagioSinal.NENHUM


def test_dominancia_confirmada_mas_fora_da_regiao_fica_em_direcao_confirmada():
    motor, vp = _motor()
    # constroi um perfil de volume concentrado em 4900 (regiao)
    for i in range(20):
        vp.registrar_trade(_trade(i, 4900, 50, AgressorSide.BUY))
    # dominancia compradora forte, mas preco atual (5000) fora da regiao 4900
    sinal = None
    for i in range(5):
        sinal = motor.ao_trade(_trade(100 + i, 5000, 100, AgressorSide.BUY))
    assert sinal.estagio is EstagioSinal.DIRECAO_CONFIRMADA
    assert sinal.direcao is Side.BUY


def test_confluencia_completa_gera_confirmado():
    motor, vp = _motor()
    for i in range(20):
        vp.registrar_trade(_trade(i, 5000, 50, AgressorSide.BUY))
    # dominancia compradora forte no preco 5000 (dentro da regiao)
    ts = 1000
    sinal = None
    for _ in range(4):
        sinal = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 500_000_000
    assert sinal.estagio is EstagioSinal.CONFIRMADO
    assert sinal.direcao is Side.BUY
    assert sinal.evidencia["micro_virou"] is True


def test_pre_sinal_quando_micro_comeca_a_virar_mas_nao_completa():
    # janela de dominancia larga (60s) e janela de micro curta (4s) — assim
    # da pra manter a dominancia geral compradora enquanto isolamos, dentro
    # da janela micro, uma sequencia que comeca vendedora (contra o alvo) e
    # so parcialmente reverte, sem cruzar para positivo.
    motor, vp = _motor(
        janela_dominancia_ns=60_000_000_000,
        janela_micro_ns=4_000_000_000,
        pre_sinal_fracao_janela_micro=0.5,
    )
    for i in range(20):
        vp.registrar_trade(_trade(i, 5000, 50, AgressorSide.BUY))

    # base de dominancia compradora, fora da janela micro quando chegarmos em 30s
    ts = 0
    for _ in range(10):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 100_000_000

    ts = 30_000_000_000
    motor.ao_trade(_trade(ts, 5000, 50, AgressorSide.SELL))
    ts += 100_000_000
    motor.ao_trade(_trade(ts, 5000, 50, AgressorSide.SELL))
    ts += 100_000_000
    # reversao parcial: delta da janela micro segue negativo (-100+30), nao
    # cruza para positivo — e exatamente o "farol amarelo", nao confirmacao.
    sinal = motor.ao_trade(_trade(ts, 5000, 30, AgressorSide.BUY))

    assert sinal.evidencia["micro_virou"] is False
    assert sinal.estagio is EstagioSinal.PRE_SINAL


def test_estagio_atual_reflete_ultimo_sinal():
    motor, vp = _motor()
    for i in range(20):
        vp.registrar_trade(_trade(i, 5000, 50, AgressorSide.BUY))
    ts = 1000
    for _ in range(4):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 500_000_000
    assert motor.estagio_atual is EstagioSinal.CONFIRMADO


def test_trade_de_outro_symbol_e_ignorado():
    motor, _ = _motor()
    sinal = motor.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, symbol="WINV26"))
    assert sinal.estagio is EstagioSinal.NENHUM
