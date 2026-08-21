from __future__ import annotations

import math

import pytest

from fluxopro.analytics.vwap import VWAP
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(ts_ns: int, price: int, qty: int, trade_id: str) -> Trade:
    return Trade(
        timestamp_ns=ts_ns,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=AgressorSide.BUY,
        trade_id=trade_id,
    )


def test_vwap_de_sessao_e_bandas() -> None:
    barramento = Barramento()
    vwap = VWAP(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 10, "T1"))
    barramento.publicar(_trade(1, 110, 10, "T2"))
    barramento.publicar(_trade(2, 90, 10, "T3"))

    # soma_qty=30 soma_preco_qty=3000 -> vwap=100.0
    assert vwap.vwap_sessao() == 100.0

    # media_preco2 = (10000+12100+8100)*10/30 = 302000/30 = 10066.666...
    # variancia = 10066.666... - 10000 = 66.666... = 200/3
    variancia_esperada = 200 / 3
    desvio_esperado = math.sqrt(variancia_esperada)

    inf2, inf1, centro, sup1, sup2 = vwap.bandas_sessao()
    assert centro == pytest.approx(100.0)
    assert sup1 == pytest.approx(100.0 + desvio_esperado)
    assert inf1 == pytest.approx(100.0 - desvio_esperado)
    assert sup2 == pytest.approx(100.0 + 2 * desvio_esperado)
    assert inf2 == pytest.approx(100.0 - 2 * desvio_esperado)


def test_vwap_ancorado_a_partir_de_um_trade_arbitrario() -> None:
    barramento = Barramento()
    vwap = VWAP(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 10, "T1"))
    vwap.ancorar("desde_T2")
    barramento.publicar(_trade(1, 110, 10, "T2"))
    barramento.publicar(_trade(2, 90, 10, "T3"))

    # a sessao inclui T1: soma_qty=30 soma_preco_qty=3000 -> vwap=100.0
    assert vwap.vwap_sessao() == 100.0

    # a ancora so ve T2 e T3: soma_qty=20 soma_preco_qty=1100+900=2000 -> vwap=100.0
    assert vwap.vwap_ancorado("desde_T2") == 100.0

    # media_preco2 = (12100+8100)*10/20 = 202000/20 = 10100 ; variancia=100 ; desvio=10
    inf2, inf1, centro, sup1, sup2 = vwap.bandas_ancorado("desde_T2")
    assert centro == pytest.approx(100.0)
    assert sup1 == pytest.approx(110.0)
    assert inf1 == pytest.approx(90.0)
    assert sup2 == pytest.approx(120.0)
    assert inf2 == pytest.approx(80.0)


def test_ancora_inexistente_retorna_none() -> None:
    barramento = Barramento()
    vwap = VWAP(barramento, symbol="WDOFUT")
    assert vwap.vwap_ancorado("nao existe") is None
    assert vwap.bandas_ancorado("nao existe") is None


def test_calculo_em_lote_bate_com_o_incremental_ancorado() -> None:
    trades = [
        _trade(1, 110, 10, "T2"),
        _trade(2, 90, 10, "T3"),
    ]
    inf2, inf1, centro, sup1, sup2 = VWAP.calcular_vwap_e_bandas(trades)
    assert centro == pytest.approx(100.0)
    assert sup1 == pytest.approx(110.0)
    assert inf1 == pytest.approx(90.0)
    assert sup2 == pytest.approx(120.0)
    assert inf2 == pytest.approx(80.0)


def test_sessao_vazia_tem_vwap_zero_e_bandas_zero() -> None:
    barramento = Barramento()
    vwap = VWAP(barramento, symbol="WDOFUT")
    assert vwap.vwap_sessao() == 0.0
    assert vwap.bandas_sessao() == (0.0, 0.0, 0.0, 0.0, 0.0)
