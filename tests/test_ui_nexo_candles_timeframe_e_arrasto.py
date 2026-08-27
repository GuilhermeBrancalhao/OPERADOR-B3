"""Cobre os achados de 27/08/2026 do candle: timeframe 5M/15M editavel e
arrastar a janela do grafico pra tras.

Usa `PainelNexoMercadoASG` de verdade (nao so `EstadoNexo` fabricado) porque
o clique/arrasto e tratado pelos handlers de mouse do WIDGET, nao pela
funcao pura `candles.desenhar`.
"""

from PySide6.QtCore import QPointF, QRect

from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import candles as modulo_candles
from fluxopro.core.eventos import AgressorSide


class _EventoFake:
    def __init__(self, x, y):
        self._ponto = QPointF(x, y)
        self.aceito = False

    def position(self):
        return self._ponto

    def accept(self):
        self.aceito = True


def _alimentar_negocios(painel, n, passo_ns=15_000_000_000, preco_inicial=100_000):
    for i in range(n):
        painel._registrar_amostra(
            i * passo_ns, preco_inicial + (i % 7), 0.0, 1, AgressorSide.BUY,
        )


def _painel_pronto(qapp, n_negocios=400):
    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)
    _alimentar_negocios(painel, n_negocios)
    return painel


def test_timeframe_comeca_em_5_minutos(qapp):
    painel = _painel_pronto(qapp)
    assert painel._timeframe_candles_min == 5
    assert painel._agregador_candles_atual() is painel._candles_m15


def test_clique_no_chip_troca_para_15_minutos(qapp):
    painel = _painel_pronto(qapp)
    caixa = painel._retangulo_candles()
    assert caixa is not None
    barra = QRect(
        caixa.left(), caixa.top() + 14, caixa.width(), modulo_candles.ALTURA_BARRA_CONTROLES
    )
    alvo = modulo_candles.retangulos_controles(barra)["timeframe"].center()
    evento = _EventoFake(alvo.x(), alvo.y())
    painel.mousePressEvent(evento)
    assert painel._timeframe_candles_min == 15
    assert painel._agregador_candles_atual() is painel._candles_15m
    assert evento.aceito


def test_segundo_clique_no_chip_volta_para_5_minutos(qapp):
    painel = _painel_pronto(qapp)
    caixa = painel._retangulo_candles()
    barra = QRect(
        caixa.left(), caixa.top() + 14, caixa.width(), modulo_candles.ALTURA_BARRA_CONTROLES
    )
    alvo = modulo_candles.retangulos_controles(barra)["timeframe"].center()
    painel.mousePressEvent(_EventoFake(alvo.x(), alvo.y()))
    painel.mousePressEvent(_EventoFake(alvo.x(), alvo.y()))
    assert painel._timeframe_candles_min == 5


def test_arrastar_para_direita_aumenta_offset(qapp):
    painel = _painel_pronto(qapp, n_negocios=800)
    caixa = painel._retangulo_candles()
    assert caixa is not None
    x0 = caixa.center().x()
    y0 = caixa.center().y()
    painel.mousePressEvent(_EventoFake(x0, y0))
    assert painel._arrasto_candles_ativo
    painel.mouseMoveEvent(_EventoFake(x0 + 200, y0))
    assert painel._candles_offset > 0
    painel.mouseReleaseEvent(_EventoFake(x0 + 200, y0))
    assert painel._arrasto_candles_ativo is False


def test_offset_nunca_ultrapassa_o_maximo_disponivel(qapp):
    painel = _painel_pronto(qapp, n_negocios=200)
    caixa = painel._retangulo_candles()
    x0, y0 = caixa.center().x(), caixa.center().y()
    painel.mousePressEvent(_EventoFake(x0, y0))
    painel.mouseMoveEvent(_EventoFake(x0 + 100_000, y0))  # arrasto absurdo
    total = len(painel._candles_m15.candles_fechados) + (
        1 if painel._candles_m15.candle_atual else 0
    )
    assert painel._candles_offset <= max(0, total - modulo_candles.VELAS_MIN)


def test_clique_fora_da_regiao_candles_nao_ativa_arrasto(qapp):
    """Clique fora da regiao "candles" cai no `super().mousePressEvent` —
    usa um QMouseEvent de verdade aqui (o unico teste que precisa, ja que
    e o unico caminho que realmente chama a base do Qt)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt as QtNS

    painel = _painel_pronto(qapp)
    ponto = QPointF(5, 5)  # canto superior esquerdo, fora do candle
    evento = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, ponto, QtNS.MouseButton.LeftButton,
        QtNS.MouseButton.LeftButton, QtNS.KeyboardModifier.NoModifier,
    )
    painel.mousePressEvent(evento)
    assert painel._arrasto_candles_ativo is False


def test_chip_agora_reseta_offset(qapp):
    painel = _painel_pronto(qapp, n_negocios=800)
    caixa = painel._retangulo_candles()
    x0, y0 = caixa.center().x(), caixa.center().y()
    painel.mousePressEvent(_EventoFake(x0, y0))
    painel.mouseMoveEvent(_EventoFake(x0 + 300, y0))
    painel.mouseReleaseEvent(_EventoFake(x0 + 300, y0))
    assert painel._candles_offset > 0

    barra = QRect(
        caixa.left(), caixa.top() + 14, caixa.width(), modulo_candles.ALTURA_BARRA_CONTROLES
    )
    alvo_agora = modulo_candles.retangulos_controles(barra)["agora"].center()
    painel.mousePressEvent(_EventoFake(alvo_agora.x(), alvo_agora.y()))
    assert painel._candles_offset == 0
