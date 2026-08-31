"""Regressoes de escala: gesto monotono, janela estavel e contexto temporal."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect

from fluxopro.analytics.candle_temporal import CandleTemporal, ConfigCandleTemporal
from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import EstadoNexo, candles


@pytest.mark.parametrize("timeframe", [5, 15])
def test_zoom_out_de_preco_na_abertura_de_quatro_ticks_e_monotono(qapp, timeframe):
    painel = PainelNexoMercadoASG()
    painel.resize(1920, 1080)
    painel._timeframe_candles_min = timeframe
    painel._registrar_amostra(0, 100_000, 0.0, 1)
    painel._registrar_amostra(1_000_000_000, 100_004, 0.0, 1)
    caixa = painel._retangulo_candles()
    original = painel._estado_nexo()
    faixa_inicial = candles.faixa_de_precos(caixa, original)
    minimo, maximo = faixa_inicial
    escala = candles.px_por_tick(caixa, original)
    assert maximo - minimo >= candles.AMPLITUDE_MINIMA_AUTO_TICKS

    for zoom in (1 / 1.15, 0.5, 0.2):
        painel._aplicar_zoom_preco(zoom / painel._candles_zoom_preco)
        estado = painel._estado_nexo()
        novo_minimo, novo_maximo = candles.faixa_de_precos(caixa, estado)
        nova_escala = candles.px_por_tick(caixa, estado)
        assert novo_minimo <= minimo and novo_maximo >= maximo
        assert novo_maximo - novo_minimo > maximo - minimo
        assert nova_escala < escala
        assert candles.velas_fora_da_escala(caixa, estado) == 0
        assert estado.candles_m15 == original.candles_m15
        minimo, maximo, escala = novo_minimo, novo_maximo, nova_escala

    painel._aplicar_zoom_preco(1 / painel._candles_zoom_preco)
    assert candles.faixa_de_precos(caixa, painel._estado_nexo()) == faixa_inicial


@pytest.mark.parametrize("timeframe,total", [(5, 106), (15, 34)])
def test_nova_vela_nao_muda_slots_manuais_nem_largura(qapp, timeframe, total):
    """106 -> 107 em M5 (34 -> 35 em M15) cruzava o corte e ampliava tudo."""
    painel = PainelNexoMercadoASG()
    painel._timeframe_candles_min = timeframe
    caixa = QRect(0, 0, 1600, 600)
    passo = timeframe * 60_000_000_000
    for i in range(total):
        painel._registrar_amostra(i * passo, 100_000 + i % 4, 0.0, 1)
    painel._aplicar_zoom_tempo(1 / 0.85, caixa)
    antes = painel._estado_nexo()
    assert antes.candles_velas_visiveis is not None
    slots = candles.janela_do_estado(caixa, antes)
    largura = candles.largura_slot_px(caixa.width(), timeframe,
                                      antes.candles_velas_visiveis, total)

    painel._registrar_amostra(total * passo, 100_002, 0.0, 1)
    depois = painel._estado_nexo()
    assert len(depois.candles_m15) == total + 1
    assert depois.candles_velas_visiveis == antes.candles_velas_visiveis
    assert candles.janela_do_estado(caixa, depois) == slots
    assert candles.largura_slot_px(caixa.width(), timeframe,
                                   depois.candles_velas_visiveis, total + 1) == largura
    visiveis = candles.velas_no_quadro(caixa, depois)
    assert visiveis == depois.candles_m15
    assert visiveis[0].timestamp_ns == antes.candles_m15[0].timestamp_ns


@pytest.mark.parametrize("timeframe", [5, 15])
def test_slots_manuais_permanecem_fixos_quando_feed_ultrapassa_horizonte(timeframe):
    slots = candles.slots_da_janela(1600, timeframe)
    for total in range(1, slots + 20):
        assert candles.slots_da_janela(1600, timeframe, slots, total) == slots
    assert candles.slots_da_janela(1600, timeframe, 1, 1) == candles.VELAS_MIN
    # Redimensionar continua sujeito ao piso fisico de 3px por slot.
    estreita = candles.slots_da_janela(200, timeframe, slots, 200)
    assert candles.VELAS_MIN <= estreita < slots
    assert candles.largura_slot_px(200, timeframe, slots, 200) >= candles.LARGURA_MIN_SLOT


@pytest.mark.parametrize("timeframe", [5, 15])
@pytest.mark.parametrize("offset", [0, 5])
@pytest.mark.parametrize("manual", [None, 24])
def test_contexto_do_buffer_respeita_intervalo_visivel(timeframe, offset, manual):
    """Inclui inicio/fim-1; exclui inicio-1/fim, inclusive no pan com zoom."""
    passo = timeframe * 60_000_000_000
    agregador = CandleTemporal(ConfigCandleTemporal(timeframe_ns=passo))
    for i in range(30):
        agregador.registrar((i + 1) * passo, 100_000 + i % 5, 1)
    estado = EstadoNexo(
        snapshot=None, serie=(), grid=WDO_GRID, paleta=None, maker=None,
        leituras=(), largura=1600, altura=600,
        candles_m15=agregador.candles_fechados + (agregador.candle_atual,),
        candles_timeframe_min=timeframe, candles_offset=offset,
        candles_velas_visiveis=manual,
    )
    caixa = QRect(0, 0, 1600, 600)
    visiveis = candles.velas_no_quadro(caixa, estado)
    inicio = visiveis[0].timestamp_ns
    fim = visiveis[-1].timestamp_ns + passo
    # Precos distintos do OHLC tornam observavel qual parte do buffer entrou.
    dentro = ((inicio, 99_920, 0.0, 1), (fim - 1, 100_090, 0.0, 1))
    fora = ((inicio - 1, 90_000, 0.0, 1), (fim, 110_000, 0.0, 1))
    filtrado = replace(estado, serie=dentro)
    completo = replace(estado, serie=(fora[0], *dentro, fora[1]))
    faixa = candles.faixa_de_precos(caixa, completo)
    assert faixa == candles.faixa_de_precos(caixa, filtrado)
    assert 90_000 < faixa[0] <= 99_920
    assert 100_090 <= faixa[1] < 110_000
    # O mesmo recorte deve ser a base antes de aplicar zoom vertical.
    zoom = replace(completo, candles_zoom_preco=0.5)
    assert candles.faixa_de_precos(caixa, zoom) == candles.faixa_de_precos(
        caixa, replace(filtrado, candles_zoom_preco=0.5))
    assert candles.faixa_de_precos(caixa, zoom)[1] - candles.faixa_de_precos(
        caixa, zoom)[0] > faixa[1] - faixa[0]


@pytest.mark.parametrize("manual", [None, 24])
def test_sem_timestamp_nao_inventa_intervalo_para_buffer(manual):
    estado = EstadoNexo(
        snapshot=None, serie=((1, 120_000, 0.0, 1),), grid=WDO_GRID,
        paleta=None, maker=None, leituras=(), largura=900, altura=600,
        candles_m15=(SimpleNamespace(low=100_000, high=100_004),),
        candles_velas_visiveis=manual,
    )
    caixa = QRect(0, 0, 900, 600)
    faixa = candles.faixa_de_precos(caixa, estado)
    assert faixa == candles.faixa_de_precos(caixa, replace(estado, serie=()))
    assert faixa[1] - faixa[0] >= candles.AMPLITUDE_MINIMA_AUTO_TICKS
