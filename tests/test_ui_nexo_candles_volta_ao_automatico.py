"""Prende o achado do critico de 28/08/2026: NAO existia volta para a escala
automatica.

O chip "› AGORA" so era desenhado quando `candles_offset > 0`, e o handler so
zerava o offset — nunca `_candles_zoom_preco` nem `_candles_velas_visiveis`.
Medida dele: com zoom 4,0, clicar no retangulo do chip deixava zoom 4,0 e 85
das 116 velas do pregao fora da vista, PNG antes e depois identicos.

Os testes reproduzem exatamente essa verificacao pelo caminho do widget.
"""

from PySide6.QtCore import QPointF, QRect

from fluxopro.core.eventos import AgressorSide
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import candles as modulo_candles


class _EventoFake:
    def __init__(self, x, y):
        self._ponto = QPointF(x, y)
        self.aceito = False

    def position(self):
        return self._ponto

    def accept(self):
        self.aceito = True


def _painel(qapp, minutos=580, passo_s=20):
    painel = PainelNexoMercadoASG()
    painel.resize(1920, 1080)
    for i in range(int(minutos * 60 / passo_s)):
        painel._registrar_amostra(
            i * passo_s * 1_000_000_000, 100_000 + (i % 30), 0.0, 1, AgressorSide.BUY,
        )
    return painel


def _chip(painel):
    caixa = painel._retangulo_candles()
    barra = QRect(caixa.left(), caixa.top() + 14, caixa.width(),
                  modulo_candles.ALTURA_BARRA_CONTROLES)
    return modulo_candles.retangulos_controles(barra)["agora"]


def _clicar(painel, ponto):
    evento = _EventoFake(ponto.x(), ponto.y())
    painel.mousePressEvent(evento)
    return evento


def test_com_zoom_em_4_o_chip_devolve_a_escala_automatica(qapp):
    """A verificacao do critico, ao pe da letra."""
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    painel._candles_zoom_preco = 4.0

    antes = painel._estado_nexo()
    assert antes.candles_zoom_preco == 4.0
    assert modulo_candles.velas_fora_da_escala(caixa, antes) > 0

    evento = _clicar(painel, _chip(painel).center())
    assert evento.aceito

    depois = painel._estado_nexo()
    assert depois.candles_zoom_preco == 1.0
    assert modulo_candles.velas_fora_da_escala(caixa, depois) == 0
    # E a janela voltou a cobrir o dia: a primeira vela do tape na tela.
    agregador = painel._agregador_candles_atual()
    todas = agregador.candles_fechados + (
        (agregador.candle_atual,) if agregador.candle_atual else ())
    visiveis = modulo_candles.velas_no_quadro(caixa, depois)
    assert visiveis[0].timestamp_ns == todas[0].timestamp_ns
    assert len(visiveis) == len(todas)


def test_o_chip_aparece_quando_so_o_zoom_esta_fora_do_neutro(qapp):
    """O afordance tem de existir no estado em que e necessario — era este o
    buraco: sem arrasto, o chip nem era desenhado."""
    painel = _painel(qapp)
    assert not modulo_candles.escala_fora_do_automatico(painel._estado_nexo())

    painel._candles_zoom_preco = 4.0
    assert modulo_candles.escala_fora_do_automatico(painel._estado_nexo())

    painel._candles_zoom_preco = 1.0
    painel._candles_velas_visiveis = modulo_candles.VELAS_MIN
    assert modulo_candles.escala_fora_do_automatico(painel._estado_nexo())


def test_o_chip_desenhado_aparece_e_some_junto_com_o_ajuste_manual(qapp):
    """Prova pelo TEXTO pintado, nao pelo estado: o chip so existe na tela
    quando ha algo para desfazer."""
    from PySide6.QtGui import QImage, QPainter

    class _Espiao(QPainter):
        def __init__(self, dispositivo):
            super().__init__(dispositivo)
            self.textos: list[str] = []

        def drawText(self, *args):  # noqa: N802 — assinatura do Qt
            for arg in args:
                if isinstance(arg, str):
                    self.textos.append(arg)
            super().drawText(*args)

    painel = _painel(qapp)
    caixa = painel._retangulo_candles()

    def textos():
        imagem = QImage(caixa.right() + 2, caixa.bottom() + 2, QImage.Format.Format_ARGB32)
        espiao = _Espiao(imagem)
        modulo_candles.desenhar(espiao, caixa, painel._estado_nexo())
        espiao.end()
        return espiao.textos

    assert not [t for t in textos() if "AUTO" in t or "AGORA" in t]
    painel._candles_zoom_preco = 4.0
    assert [t for t in textos() if "AUTO" in t]
    _clicar(painel, _chip(painel).center())
    assert not [t for t in textos() if "AUTO" in t or "AGORA" in t]


def test_duplo_clique_no_eixo_de_preco_volta_ao_automatico(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    painel._candles_zoom_preco = 4.0
    painel._candles_velas_visiveis = modulo_candles.VELAS_MIN

    eixo = modulo_candles.retangulo_eixo_preco(caixa)
    evento = _EventoFake(eixo.center().x(), eixo.center().y())
    painel.mouseDoubleClickEvent(evento)

    assert evento.aceito
    assert painel._candles_zoom_preco == 1.0
    assert painel._candles_velas_visiveis is None


def test_o_chip_tambem_desfaz_o_arrasto_lateral(qapp):
    """O que ele ja fazia continua funcionando (pan + escala, de uma vez)."""
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    centro = caixa.center()
    painel.mousePressEvent(_EventoFake(centro.x(), centro.y()))
    painel.mouseMoveEvent(_EventoFake(centro.x() + 300, centro.y()))
    painel.mouseReleaseEvent(_EventoFake(centro.x() + 300, centro.y()))
    assert painel._candles_offset > 0

    painel._candles_zoom_preco = 2.0
    _clicar(painel, _chip(painel).center())
    assert painel._candles_offset == 0
    assert painel._candles_zoom_preco == 1.0
    assert painel._candles_velas_visiveis is None


def test_rotulo_do_chip_no_estado_combinado_pan_e_zoom(qapp):
    """Achado de auditoria (28/08/2026): nenhum critico havia verificado o
    rotulo do chip com PAN e ZOOM ativos ao mesmo tempo — so os dois casos
    isolados tinham prova. Prova pelo TEXTO pintado, nao pelo estado: com os
    dois ajustes juntos, o clique desfaz mais do que "voltar ao presente"
    (tambem restaura a escala de preco), entao o rotulo tem de dizer "AUTO",
    nunca "AGORA" — palavra que prometeria so posicao."""

    from PySide6.QtGui import QImage, QPainter

    class _Espiao(QPainter):
        def __init__(self, dispositivo):
            super().__init__(dispositivo)
            self.textos: list[str] = []

        def drawText(self, *args):  # noqa: N802 — assinatura do Qt
            for arg in args:
                if isinstance(arg, str):
                    self.textos.append(arg)
            super().drawText(*args)

    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    centro = caixa.center()
    painel.mousePressEvent(_EventoFake(centro.x(), centro.y()))
    painel.mouseMoveEvent(_EventoFake(centro.x() + 300, centro.y()))
    painel.mouseReleaseEvent(_EventoFake(centro.x() + 300, centro.y()))
    painel._candles_zoom_preco = 3.0
    assert painel._candles_offset > 0
    assert painel._candles_zoom_preco == 3.0

    def textos():
        imagem = QImage(caixa.right() + 2, caixa.bottom() + 2, QImage.Format.Format_ARGB32)
        espiao = _Espiao(imagem)
        modulo_candles.desenhar(espiao, caixa, painel._estado_nexo())
        espiao.end()
        return espiao.textos

    pintado = textos()
    assert any("AUTO" in t for t in pintado), pintado
    assert not any("AGORA" in t for t in pintado), pintado

    _clicar(painel, _chip(painel).center())
    assert painel._candles_offset == 0
    assert painel._candles_zoom_preco == 1.0
    assert not any("AUTO" in t or "AGORA" in t for t in textos())


def test_clique_no_chip_sem_nada_para_desfazer_nao_e_consumido(qapp):
    """Sem ajuste manual o chip nao esta na tela; o clique naquela area nao
    pode virar um controle invisivel — cai no comportamento normal (pan)."""
    painel = _painel(qapp)
    evento = _clicar(painel, _chip(painel).center())
    assert painel._arrasto_candles_ativo
    assert evento.aceito
