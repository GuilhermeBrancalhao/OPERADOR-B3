"""Contrato visual do ajuste automatico dos graficos do NEXO.

Os testes medem somente regras de enquadramento, nao tentam reproduzir uma
formula proprietaria. O objetivo e impedir que a primeira vela volte a
inflar ou que o Renko retorne a uma semente grosseira sem ser declarado.
"""

from fluxopro.ui.paineis.nexo import candles as modulo_candles


def test_auto_tem_folga_temporal_para_manter_candles_pequenos():
    base = modulo_candles.MINUTOS_PREGAO // 5
    auto = modulo_candles.slots_da_janela(1600, 5, None)

    assert auto > base
    assert auto == round(base * modulo_candles.HORIZONTE_AUTO_MULTIPLICADOR)


def test_zoom_manual_preserva_horizonte_ao_chegar_vela_depois_do_pregao():
    total = modulo_candles.MINUTOS_PREGAO // 5 + 8
    auto = modulo_candles.slots_da_janela(1600, 5, None, total)
    manual = modulo_candles.slots_da_janela(1600, 5, 10_000, total)

    assert auto >= total + modulo_candles.MARGEM_SLOTS
    # O contrato antigo exigia total+2, provocando um salto no tamanho ao
    # cruzar 108 slots. Espaco vazio nao e historico: preserve o horizonte
    # valido, com lugar para a primeira vela e sem reajuste a cada chegada.
    assert manual == auto
    assert manual >= total + modulo_candles.MARGEM_SLOTS
    assert modulo_candles.slots_da_janela(1600, 5, manual, total + 1) == manual


def test_abertura_tem_piso_de_amplitude_sem_alterar_o_candle():
    from types import SimpleNamespace

    from PySide6.QtCore import QRect
    from fluxopro.core.eventos import WDO_GRID
    from fluxopro.ui.paineis.nexo import EstadoNexo

    candle = SimpleNamespace(high=100_004, low=100_000)
    estado = EstadoNexo(
        snapshot=None, serie=((1, 100_002, 0.0, 1),), grid=WDO_GRID,
        paleta=None, maker=None, leituras=(), largura=900, altura=600,
        candles_m15=(candle,), candles_timeframe_min=5,
    )

    minimo, maximo = modulo_candles.faixa_de_precos(QRect(0, 0, 900, 600), estado)

    assert maximo - minimo >= modulo_candles.AMPLITUDE_MINIMA_AUTO_TICKS
    assert minimo <= candle.low
    assert maximo >= candle.high


def test_semente_do_renko_da_interface_e_fina_e_nao_altera_agregador_padrao():
    from fluxopro.analytics.renko import ConfigRenko
    from fluxopro.core.eventos import WDO_GRID
    from fluxopro.analytics.renko import Renko

    fino = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=2.0))
    padrao = Renko(WDO_GRID, ConfigRenko())

    assert fino.tamanho_tijolo_ticks < padrao.tamanho_tijolo_ticks
