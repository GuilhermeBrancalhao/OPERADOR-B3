"""Prende o achado do critico de 28/08/2026: a janela padrao era um TETO de
relogio (`MINUTOS_PREGAO // tf` = 108 slots de 5M) e o dia real tem 116
velas — as 8 primeiras, as da ABERTURA que originaram a queixa do operador,
ficavam fora e so apareciam arrastando, com o cabecalho ainda prometendo
"JANELA DO PREGAO".

O que os testes exigem:
  - a PRIMEIRA vela do tape esta dentro da janela padrao, sem arrasto;
  - o rotulo so promete "JANELA DO PREGAO" quando isso e verdade;
  - o zoom-out vai ate a primeira vela e para la;
  - e o remedio nao ressuscita o defeito da rodada 1: com o dia mal
    comecado, a vela NAO vira um bloco.
"""

from PySide6.QtCore import QRect

from fluxopro.core.eventos import AgressorSide
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import candles as modulo_candles


def _painel(qapp, minutos, passo_s=20, largura=1920, altura=1080):
    painel = PainelNexoMercadoASG()
    painel.resize(largura, altura)
    for i in range(int(minutos * 60 / passo_s)):
        painel._registrar_amostra(
            i * passo_s * 1_000_000_000, 100_000 + (i % 30), 0.0, 1, AgressorSide.BUY,
        )
    return painel


def _velas_do_dia(painel):
    agregador = painel._agregador_candles_atual()
    return agregador.candles_fechados + (
        (agregador.candle_atual,) if agregador.candle_atual else ())


def test_a_primeira_vela_do_dia_esta_na_janela_padrao(qapp):
    """580 minutos de tape = 116 velas de 5M, mais que os 108 slots do teto
    antigo. Sem tocar em nada, a primeira vela tem de estar na tela."""
    painel = _painel(qapp, minutos=580)
    todas = _velas_do_dia(painel)
    assert len(todas) > modulo_candles.MINUTOS_PREGAO // 5, len(todas)

    caixa = painel._retangulo_candles()
    estado = painel._estado_nexo()
    assert estado.candles_offset == 0
    assert estado.candles_velas_visiveis is None

    visiveis = modulo_candles.velas_no_quadro(caixa, estado)
    assert len(visiveis) == len(todas), (len(visiveis), len(todas))
    assert visiveis[0].timestamp_ns == todas[0].timestamp_ns


def test_o_mesmo_vale_no_timeframe_de_15_minutos(qapp):
    painel = _painel(qapp, minutos=580)
    painel._timeframe_candles_min = 15
    todas = _velas_do_dia(painel)
    assert len(todas) > modulo_candles.MINUTOS_PREGAO // 15
    caixa = painel._retangulo_candles()
    visiveis = modulo_candles.velas_no_quadro(caixa, painel._estado_nexo())
    assert visiveis[0].timestamp_ns == todas[0].timestamp_ns


def test_o_rotulo_so_promete_o_pregao_quando_o_dia_cabe(qapp):
    painel = _painel(qapp, minutos=580)
    caixa = painel._retangulo_candles()
    estado = painel._estado_nexo()
    n_slots = modulo_candles.janela_do_estado(caixa, estado)
    assert modulo_candles._rotulo_janela(estado, n_slots) == "JANELA DO PREGAO"

    # Janela apertada a mao: a promessa TEM de mudar de nome.
    estreita = modulo_candles._rotulo_janela(estado, modulo_candles.VELAS_MIN)
    assert estreita == "ESCALA MANUAL" or estreita.startswith("JANELA PARCIAL")


def test_zoom_out_alcanca_a_primeira_vela_e_para_nela(qapp):
    painel = _painel(qapp, minutos=580)
    caixa = painel._retangulo_candles()
    total = len(_velas_do_dia(painel))

    for _ in range(30):  # zoom in ate o fim
        painel._aplicar_zoom_tempo(0.85, caixa)
    assert painel._candles_velas_visiveis == modulo_candles.VELAS_MIN
    for _ in range(60):  # e zoom out ate o fim
        painel._aplicar_zoom_tempo(1 / 0.85, caixa)

    visiveis = modulo_candles.velas_no_quadro(caixa, painel._estado_nexo())
    assert len(visiveis) == total
    # E nao passa disso: nao ha sessao alem da primeira vela.
    assert painel._candles_velas_visiveis <= total + modulo_candles.MARGEM_SLOTS


def test_dia_recem_aberto_nao_volta_a_ter_vela_gigante(qapp):
    """O remedio nao pode reabrir o defeito da rodada 1: com 4 velas, a
    janela nao encolhe ate o dado — o piso segura a largura."""
    painel = _painel(qapp, minutos=20)
    caixa = painel._retangulo_candles()
    largura_abertura = modulo_candles.largura_slot_px(
        caixa.width(), 5, None, len(_velas_do_dia(painel)))
    assert largura_abertura * modulo_candles.FRACAO_CORPO <= 20

    cheio = _painel(qapp, minutos=580)
    largura_cheio = modulo_candles.largura_slot_px(
        cheio._retangulo_candles().width(), 5, None, len(_velas_do_dia(cheio)))
    # A vela pode ficar mais fina quando o dia passa do piso, mas nunca
    # muda de ordem de grandeza como mudava antes (170px -> 4px).
    assert largura_abertura / largura_cheio <= 1.5


def test_o_eixo_enquadra_a_maxima_e_a_minima_DO_TAPE_REAL(qapp):
    """O eixo nao pode amputar extremo do dia.

    Uma versao anterior enquadrava por percentil p05-p95 para se defender de
    um "print aberrante" que nao existe: medido no tape de 27/08 (158.440
    negocios), a faixa e 10.291-10.359 ticks e nao ha nada fora. Recorte por
    percentil descarta extremo POR CONSTRUCAO — e maxima e minima do pregao
    sao justamente os precos que o operador mais olha. Este teste usa o tape
    REAL e exige os dois extremos dentro do eixo, sem arrasto e sem zoom.
    """
    import gzip
    import csv
    from pathlib import Path

    import pytest

    caminho = Path("dados/WDOU26/2026-08-27/trades.csv.gz")
    if not caminho.exists():
        pytest.skip(f"tape real ausente em {caminho}")

    painel = PainelNexoMercadoASG()
    painel.resize(1920, 1080)
    lados = {"BUY": AgressorSide.BUY, "SELL": AgressorSide.SELL}
    precos = []
    with gzip.open(caminho, "rt", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            preco = int(float(linha["price"]))
            precos.append(preco)
            painel._registrar_amostra(
                int(linha["timestamp_ns"]), preco, 0.0, int(float(linha["qty"])),
                lados.get(linha["side_agressor"], AgressorSide.UNKNOWN),
            )
    maxima_do_dia, minima_do_dia = max(precos), min(precos)

    caixa = painel._retangulo_candles()
    estado = painel._estado_nexo()
    assert estado.candles_offset == 0
    assert estado.candles_velas_visiveis is None
    assert estado.candles_zoom_preco == 1.0

    minimo, maximo = modulo_candles.faixa_de_precos(caixa, estado)
    assert minimo <= minima_do_dia, (minimo, minima_do_dia)
    assert maximo >= maxima_do_dia, (maximo, maxima_do_dia)
    # E, por consequencia, nenhuma vela fica fora da escala em automatico.
    assert modulo_candles.velas_fora_da_escala(caixa, estado) == 0


def test_fora_da_escala_so_existe_quando_o_operador_amplia(qapp):
    """A declaracao "N VELAS FORA DA ESCALA" e rede de protecao para o que o
    PROPRIO operador tira da vista com o zoom — nunca para o eixo descartar
    dado sozinho."""
    painel = _painel(qapp, minutos=580)
    caixa = painel._retangulo_candles()
    assert modulo_candles.velas_fora_da_escala(caixa, painel._estado_nexo()) == 0

    painel._candles_zoom_preco = 6.0  # amplia ate sobrar vela fora do recorte
    assert modulo_candles.velas_fora_da_escala(caixa, painel._estado_nexo()) > 0

    painel._candles_zoom_preco = 1.0  # e desfazer devolve tudo para dentro
    assert modulo_candles.velas_fora_da_escala(caixa, painel._estado_nexo()) == 0


def test_a_janela_nunca_estoura_o_limite_de_pixel_por_vela(qapp):
    """Se um dia tiver mais velas do que cabem em pixel, a janela para no
    limite fisico — e ai o rotulo nao pode prometer o pregao inteiro."""
    caixa = QRect(0, 0, 400, 300)
    n_slots = modulo_candles.slots_da_janela(caixa.width(), 5, None, 10_000)
    largura_plot = caixa.width() - modulo_candles.LARGURA_EIXO - modulo_candles.LARGURA_ROTULO_NIVEL
    assert n_slots <= max(modulo_candles.VELAS_MIN,
                          largura_plot // modulo_candles.LARGURA_MIN_SLOT)
