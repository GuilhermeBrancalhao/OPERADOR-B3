"""Prende o CROSSHAIR e a leitura O/H/L/C da vela apontada (achado do
critico, 28/08/2026): "nao existe crosshair nem leitura por vela ... o
cabecalho nunca mostra Abertura/Maxima/Minima/Fechamento/variacao da vela sob
o mouse (nem da ultima)".

Prova pelo caminho REAL: um `QMouseEvent` de MouseMove SEM botao pressionado
(que so chega porque o painel liga `setMouseTracking`), e depois o texto
efetivamente PINTADO, capturado de um QPainter espiao. Mover o mouse para
outra vela tem de mudar os numeros lidos.
"""

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter

from fluxopro.core.eventos import AgressorSide
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import candles as modulo_candles


class _PainterEspiao(QPainter):
    """Guarda todo texto desenhado, na ordem."""

    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.textos: list[str] = []

    def drawText(self, *args):  # noqa: N802 — assinatura do Qt
        for arg in args:
            if isinstance(arg, str):
                self.textos.append(arg)
        super().drawText(*args)


def _painel(qapp, n=1700):
    # 1.700 amostras de 20s = ~9h de tape: a janela do pregao fica CHEIA de
    # velas de 5M. Com menos que isso, uma coluna a 75% da largura cai num
    # slot de tempo ainda sem vela e o teste mediria o vazio, nao a leitura.
    painel = PainelNexoMercadoASG()
    painel.resize(1600, 900)
    for i in range(n):
        # Rampa lenta: velas vizinhas tem OHLC diferente, entao mover o
        # cursor de uma para outra TEM de mudar a leitura.
        painel._registrar_amostra(
            i * 20_000_000_000, 100_000 + i // 7, 0.0, 1 + (i % 5), AgressorSide.BUY,
        )
    return painel


def _mover_mouse(painel, x, y):
    evento = QMouseEvent(
        QMouseEvent.Type.MouseMove, QPointF(x, y), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    painel.mouseMoveEvent(evento)


def _textos_do_grafico(painel, caixa):
    imagem = QImage(caixa.right() + 2, caixa.bottom() + 2, QImage.Format.Format_ARGB32)
    painter = _PainterEspiao(imagem)
    modulo_candles.desenhar(painter, caixa, painel._estado_nexo())
    painter.end()
    return painter.textos


def _leitura(textos):
    """Os quatro precos do readout, na ordem ABR/MAX/MIN/FCH."""
    saida = []
    for rotulo in ("ABR", "MAX", "MIN", "FCH", "VAR"):
        assert rotulo in textos, (rotulo, textos)
        saida.append(textos[textos.index(rotulo) + 1])
    return saida


def test_o_painel_rastreia_o_mouse_sem_botao(qapp):
    painel = _painel(qapp)
    assert painel.hasMouseTracking()
    caixa = painel._retangulo_candles()
    _mover_mouse(painel, caixa.center().x(), caixa.center().y())
    assert painel._cursor_candles is not None
    assert painel._arrasto_candles_ativo is False
    assert painel._arrasto_escala is None


def test_mouse_fora_da_regiao_de_candles_nao_vira_cursor(qapp):
    """setMouseTracking vale para o widget INTEIRO; passear sobre VAP, nucleo
    ou placar nao pode virar estado (nem quadro sujo) do grafico."""
    painel = _painel(qapp)
    _mover_mouse(painel, 5, 5)
    assert painel._cursor_candles is None
    caixa = painel._retangulo_candles()
    _mover_mouse(painel, caixa.center().x(), caixa.center().y())
    assert painel._cursor_candles is not None
    _mover_mouse(painel, 5, 5)
    assert painel._cursor_candles is None


def test_sem_cursor_o_readout_mostra_a_ULTIMA_vela(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    textos = _textos_do_grafico(painel, caixa)
    assert any("ULTIMA VELA" in t for t in textos), textos
    velas = modulo_candles.velas_no_quadro(caixa, painel._estado_nexo())
    from fluxopro.ui import formato
    esperado = formato.preco_completo(painel.grid, velas[-1].close)
    assert _leitura(textos)[3] == esperado


def test_mover_o_mouse_muda_os_valores_lidos(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    plot = modulo_candles.retangulo_plot(caixa)
    estado = painel._estado_nexo()
    velas = modulo_candles.velas_no_quadro(caixa, estado)
    assert len(velas) > 10

    # Duas colunas que apontam velas DIFERENTES, verificado pela funcao pura.
    x_a = plot.left() + int(plot.width() * 0.25)
    x_b = plot.left() + int(plot.width() * 0.75)
    indice_a = modulo_candles.indice_vela_em(caixa, estado, x_a)
    indice_b = modulo_candles.indice_vela_em(caixa, estado, x_b)
    assert indice_a is not None and indice_b is not None and indice_a != indice_b

    _mover_mouse(painel, x_a, plot.center().y())
    textos_a = _textos_do_grafico(painel, caixa)
    _mover_mouse(painel, x_b, plot.center().y())
    textos_b = _textos_do_grafico(painel, caixa)

    assert any("VELA APONTADA" in t for t in textos_a)
    leitura_a, leitura_b = _leitura(textos_a), _leitura(textos_b)
    assert leitura_a != leitura_b, (leitura_a, leitura_b)

    # E cada leitura e a da vela REALMENTE apontada, nao um numero qualquer.
    from fluxopro.ui import formato
    for indice, leitura in ((indice_a, leitura_a), (indice_b, leitura_b)):
        vela = velas[indice]
        assert leitura[0] == formato.preco_completo(painel.grid, vela.open)
        assert leitura[1] == formato.preco_completo(painel.grid, vela.high)
        assert leitura[2] == formato.preco_completo(painel.grid, vela.low)
        assert leitura[3] == formato.preco_completo(painel.grid, vela.close)


def test_variacao_lida_e_a_da_propria_vela(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    plot = modulo_candles.retangulo_plot(caixa)
    estado = painel._estado_nexo()
    x = plot.left() + int(plot.width() * 0.6)
    indice = modulo_candles.indice_vela_em(caixa, estado, x)
    vela = modulo_candles.velas_no_quadro(caixa, estado)[indice]

    _mover_mouse(painel, x, plot.center().y())
    var = _leitura(_textos_do_grafico(painel, caixa))[4]
    esperado = (vela.close - vela.open) / vela.open * 100.0
    assert var == f"{esperado:+.2f}%", (var, esperado)


def test_sair_do_widget_apaga_o_crosshair(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    _mover_mouse(painel, caixa.center().x(), caixa.center().y())
    assert painel._cursor_candles is not None
    from PySide6.QtCore import QEvent

    painel.leaveEvent(QEvent(QEvent.Type.Leave))
    assert painel._cursor_candles is None
    assert any("ULTIMA VELA" in t for t in _textos_do_grafico(painel, caixa))


def test_micro_movimento_na_mesma_vela_nao_suja_quadro(qapp):
    """Custo por quadro: varrer o grafico nao pode virar um repaint por
    pixel. Dentro da MESMA vela e com menos de 2px na vertical, nada muda."""
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    plot = modulo_candles.retangulo_plot(caixa)
    x = plot.left() + int(plot.width() * 0.5)
    _mover_mouse(painel, x, plot.center().y())
    antes = painel._cursor_candles

    sujou = []
    original = painel.marcar_tudo_sujo
    painel.marcar_tudo_sujo = lambda: (sujou.append(1), original())[1]
    _mover_mouse(painel, x + 1, plot.center().y() + 1)
    painel.marcar_tudo_sujo = original

    assert painel._cursor_candles == antes
    assert not sujou
