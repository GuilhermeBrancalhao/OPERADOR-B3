from __future__ import annotations

from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import NS_POR_MINUTO, EstadoMercado
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(
    ts_ns: int, price: int, qty: int, agressor: AgressorSide, trade_id: str
) -> Trade:
    return Trade(
        timestamp_ns=ts_ns,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=agressor,
        trade_id=trade_id,
    )


def test_candle_ohlcv_e_delta() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 10000, 5, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1_000_000_000, 10010, 3, AgressorSide.SELL, "T2"))
    barramento.publicar(_trade(2_000_000_000, 9990, 7, AgressorSide.BUY, "T3"))
    barramento.publicar(_trade(3_000_000_000, 10005, 2, AgressorSide.SELL, "T4"))

    candle = estado.candle_atual
    assert candle is not None
    assert candle.open == 10000
    assert candle.high == 10010
    assert candle.low == 9990
    assert candle.close == 10005
    assert candle.volume == 17
    assert candle.delta == 5 - 3 + 7 - 2


def test_candle_fecha_ao_cruzar_timeframe() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 10000, 1, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(NS_POR_MINUTO, 10050, 1, AgressorSide.BUY, "T2"))

    fechados = estado.candles_fechados
    assert len(fechados) == 1
    assert fechados[0].close == 10000
    assert estado.candle_atual is not None
    assert estado.candle_atual.open == 10050


def test_vwap_e_high_low_de_sessao() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 10000, 2, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 10010, 3, AgressorSide.SELL, "T2"))
    barramento.publicar(_trade(2, 9990, 5, AgressorSide.BUY, "T3"))

    esperado_vwap = (10000 * 2 + 10010 * 3 + 9990 * 5) / (2 + 3 + 5)
    assert estado.sessao.vwap == esperado_vwap
    assert estado.sessao.high == 10010
    assert estado.sessao.low == 9990
    assert estado.sessao.volume_total == 10


def test_sessao_vazia_tem_vwap_zero() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")
    assert estado.sessao.vwap == 0.0
    assert estado.candle_atual is None


def test_sessao_separa_volume_por_agressor_incluindo_desconhecido() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 10000, 5, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 10000, 3, AgressorSide.SELL, "T2"))
    # leilao/RLP: agressor desconhecido - entra no volume, nao no lado comprador/vendedor
    barramento.publicar(_trade(2, 10000, 7, AgressorSide.UNKNOWN, "T3"))

    sessao = estado.sessao
    assert sessao.volume_comprador == 5
    assert sessao.volume_vendedor == 3
    assert sessao.volume_nao_atribuido == 7
    assert sessao.volume_total == 15
    # invariante: nada conta no total sem cair em algum dos tres baldes
    assert sessao.volume_total == (
        sessao.volume_comprador + sessao.volume_vendedor + sessao.volume_nao_atribuido
    )


def test_iniciar_nova_sessao_zera_sessao_e_candle_em_formacao() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 10000, 5, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 10050, 3, AgressorSide.SELL, "T2"))
    assert estado.sessao.volume_total == 8
    assert estado.candle_atual is not None

    estado.iniciar_nova_sessao(timestamp_ns=2)

    assert estado.sessao.high is None
    assert estado.sessao.low is None
    assert estado.sessao.volume_comprador == 0
    assert estado.sessao.volume_vendedor == 0
    assert estado.sessao.volume_nao_atribuido == 0
    assert estado.sessao.volume_total == 0
    assert estado.sessao.vwap == 0.0
    assert estado.candle_atual is None

    # a sessao nova nao herda nada da anterior
    barramento.publicar(_trade(3, 9000, 2, AgressorSide.BUY, "T3"))
    assert estado.sessao.volume_total == 2
    assert estado.sessao.high == 9000
    assert estado.sessao.low == 9000
    assert estado.candle_atual is not None
    assert estado.candle_atual.open == 9000
    assert estado.candle_atual.volume == 2
