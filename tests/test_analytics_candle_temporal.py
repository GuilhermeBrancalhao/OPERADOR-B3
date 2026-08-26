from __future__ import annotations

from fluxopro.analytics.candle_temporal import CandleTemporal, ConfigCandleTemporal
from fluxopro.core.eventos import AgressorSide

NS_POR_MINUTO = 60_000_000_000
M15_NS = 15 * NS_POR_MINUTO


def test_sem_negocio_nenhum_candle_atual_e_none():
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=M15_NS))
    assert agregador.candle_atual is None
    assert agregador.candles_fechados == ()


def test_negocios_na_mesma_janela_formam_um_so_candle():
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=M15_NS))
    agregador.registrar(0, 100_000, qty=5, agressor=AgressorSide.BUY)
    agregador.registrar(60_000_000_000, 100_010, qty=3, agressor=AgressorSide.SELL)  # +1 min
    agregador.registrar(14 * NS_POR_MINUTO, 100_005, qty=2, agressor=AgressorSide.BUY)  # ainda dentro da janela de 15min

    candle = agregador.candle_atual
    assert candle is not None
    assert candle.open == 100_000
    assert candle.high == 100_010
    assert candle.low == 100_000
    assert candle.close == 100_005
    assert candle.volume == 10
    assert candle.delta == 5 - 3 + 2
    assert agregador.candles_fechados == ()  # ainda nao fechou


def test_negocio_na_proxima_janela_fecha_o_candle_anterior():
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=M15_NS))
    agregador.registrar(0, 100_000, qty=1, agressor=AgressorSide.BUY)
    agregador.registrar(M15_NS, 100_050, qty=1, agressor=AgressorSide.BUY)  # proxima janela de 15min

    fechados = agregador.candles_fechados
    assert len(fechados) == 1
    assert fechados[0].open == 100_000
    assert fechados[0].close == 100_000  # so um trade no primeiro candle

    atual = agregador.candle_atual
    assert atual is not None
    assert atual.timestamp_ns == M15_NS
    assert atual.open == 100_050


def test_volume_nao_atribuido_conta_no_volume_mas_nao_no_delta():
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=M15_NS))
    agregador.registrar(0, 100_000, qty=10, agressor=AgressorSide.UNKNOWN)
    candle = agregador.candle_atual
    assert candle is not None
    assert candle.volume == 10
    assert candle.delta == 0
    assert candle.volume_nao_atribuido == 10


def test_bucket_e_alinhado_ao_timeframe_nao_ao_primeiro_trade():
    """O bucket usa timestamp // timeframe, igual a estado_mercado.py — um
    trade as 15:00:03 e outro as 15:14:59 caem no MESMO candle de 15min."""
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=M15_NS))
    ts_a = 100 * M15_NS + 3 * NS_POR_MINUTO
    ts_b = 100 * M15_NS + 14 * NS_POR_MINUTO + 59_000_000_000
    agregador.registrar(ts_a, 100_000)
    agregador.registrar(ts_b, 100_100)
    assert agregador.candle_atual.timestamp_ns == 100 * M15_NS
    assert agregador.candles_fechados == ()


def test_retencao_nao_cresce_sem_teto_em_20_mil_candles():
    config = ConfigCandleTemporal(timeframe_ns=NS_POR_MINUTO, maxlen_fechados=50)

    def _rodar(n_eventos: int) -> int:
        agregador = CandleTemporal(config)
        for i in range(n_eventos):
            agregador.registrar(i * NS_POR_MINUTO, 100_000 + i, qty=1)
        return len(agregador.candles_fechados)

    tamanho_1k = _rodar(1_000)
    tamanho_20k = _rodar(20_000)
    assert tamanho_1k == config.maxlen_fechados
    assert tamanho_20k == config.maxlen_fechados
