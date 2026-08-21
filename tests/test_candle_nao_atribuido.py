"""Invariante do candle: volume == delta atribuido + volume nao atribuido.

Fecha a pendencia herdada da onda 4: `candle.volume` contava trades
`AgressorSide.UNKNOWN` (leilao, RLP) mas `candle.delta` nao, e a diferenca
era invisivel para quem lia o candle.
"""

from __future__ import annotations

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.core.estado_mercado import EstadoMercado

NS_POR_MINUTO = 60_000_000_000


def _trade(ts, price, qty, agressor, symbol="WDOV26"):
    return Trade(
        timestamp_ns=ts, symbol=symbol, price=price, qty=qty,
        side_agressor=agressor, trade_id=f"t{ts}",
    )


def _estado():
    barramento = Barramento()
    return barramento, EstadoMercado(barramento, "WDOV26")


def test_candle_separa_volume_sem_agressor_conhecido():
    barramento, estado = _estado()
    barramento.publicar(_trade(0, 5000, 10, AgressorSide.BUY))
    barramento.publicar(_trade(1, 5000, 4, AgressorSide.SELL))
    barramento.publicar(_trade(2, 5000, 7, AgressorSide.UNKNOWN))

    candle = estado.candle_atual
    assert candle.volume == 21          # todo trade conta no volume
    assert candle.delta == 6            # 10 - 4, o UNKNOWN nao entra
    assert candle.volume_nao_atribuido == 7


def test_invariante_volume_igual_atribuido_mais_nao_atribuido():
    barramento, estado = _estado()
    sequencia = [
        (5000, 10, AgressorSide.BUY),
        (5001, 3, AgressorSide.UNKNOWN),
        (5000, 8, AgressorSide.SELL),
        (4999, 5, AgressorSide.UNKNOWN),
        (5000, 2, AgressorSide.BUY),
    ]
    for i, (preco, qty, agressor) in enumerate(sequencia):
        barramento.publicar(_trade(i, preco, qty, agressor))

    candle = estado.candle_atual
    comprador = 12  # 10 + 2
    vendedor = 8
    nao_atribuido = 8  # 3 + 5
    assert candle.volume == comprador + vendedor + nao_atribuido
    assert candle.delta == comprador - vendedor
    assert candle.volume_nao_atribuido == nao_atribuido


def test_candle_sem_trade_anonimo_tem_nao_atribuido_zero():
    barramento, estado = _estado()
    barramento.publicar(_trade(0, 5000, 10, AgressorSide.BUY))
    barramento.publicar(_trade(1, 5000, 4, AgressorSide.SELL))

    candle = estado.candle_atual
    assert candle.volume_nao_atribuido == 0
    assert candle.volume == 14


def test_candle_fechado_preserva_volume_nao_atribuido():
    """O campo tem que sobreviver ao `congelar()`, nao so existir no vivo."""
    barramento, estado = _estado()
    barramento.publicar(_trade(0, 5000, 9, AgressorSide.UNKNOWN))
    # trade no minuto seguinte fecha o candle anterior
    barramento.publicar(_trade(NS_POR_MINUTO, 5000, 1, AgressorSide.BUY))

    fechados = estado.candles_fechados
    assert len(fechados) == 1
    assert fechados[0].volume_nao_atribuido == 9
    assert fechados[0].volume == 9
    assert fechados[0].delta == 0
