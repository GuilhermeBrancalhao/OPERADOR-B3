"""Prende a ESCALA do grafico de candles (achado do critico, 28/08/2026):
"o arrasto so faz PAN horizontal, nao existe nenhum controle de ESCALA".

Cobre os dois zooms que o operador pediu ("eu podendo mexer no grafico na
escala arrastando"):
  - TEMPO  — quantas velas cabem na janela (arrasto no rodape / roda no plot);
  - PRECO  — quantos ticks o eixo vertical enquadra (arrasto na calha do eixo
             de preco / roda sobre ela).

Mede o EFEITO verificavel, nao a existencia do handler: numero de velas
visiveis, pixels por tick, e a reversibilidade do gesto.
"""

from PySide6.QtCore import QPoint, QPointF, QRect

from fluxopro.core.eventos import AgressorSide
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import candles as modulo_candles


class _EventoFake:
    def __init__(self, x, y, delta=0):
        self._ponto = QPointF(x, y)
        self._delta = delta
        self.aceito = False

    def position(self):
        return self._ponto

    def angleDelta(self):  # noqa: N802 — assinatura do Qt
        return QPoint(0, self._delta)

    def accept(self):
        self.aceito = True


def _painel(qapp, n_negocios=800):
    painel = PainelNexoMercadoASG()
    painel.resize(1600, 900)
    for i in range(n_negocios):
        painel._registrar_amostra(
            i * 20_000_000_000, 100_000 + (i % 40), 0.0, 1, AgressorSide.BUY,
        )
    return painel


def _velas_visiveis(painel):
    caixa = painel._retangulo_candles()
    return modulo_candles.slots_da_janela(
        caixa.width(), painel._timeframe_candles_min, painel._candles_velas_visiveis)


def _px_por_tick(painel):
    caixa = painel._retangulo_candles()
    return modulo_candles.px_por_tick(caixa, painel._estado_nexo())


def test_padrao_e_a_janela_do_pregao_inteiro(qapp):
    painel = _painel(qapp)
    assert painel._candles_velas_visiveis is None
    caixa = painel._retangulo_candles()
    assert _velas_visiveis(painel) == modulo_candles.slots_da_janela(
        caixa.width(), 5, None)


def test_arrastar_a_escala_de_tempo_muda_o_numero_de_velas_visiveis(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    eixo = modulo_candles.retangulo_eixo_tempo(caixa)
    antes = _velas_visiveis(painel)

    painel.mousePressEvent(_EventoFake(eixo.center().x(), eixo.center().y()))
    assert painel._arrasto_escala == "tempo"
    # Arrastar pra DIREITA expande: menos velas na mesma largura.
    painel.mouseMoveEvent(_EventoFake(eixo.center().x() + 200, eixo.center().y()))
    depois = _velas_visiveis(painel)
    painel.mouseReleaseEvent(_EventoFake(eixo.center().x() + 200, eixo.center().y()))

    assert painel._arrasto_escala is None
    assert depois < antes, (antes, depois)
    assert depois >= modulo_candles.VELAS_MIN


def test_zoom_de_tempo_alarga_a_vela(qapp):
    """Menos velas na janela => cada vela ocupa mais pixels. E a leitura que
    o operador nao conseguia abrir com o pan."""
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    largura_antes = modulo_candles.largura_slot_px(caixa.width(), 5, None)
    painel._aplicar_zoom_tempo(0.4, caixa)
    largura_depois = modulo_candles.largura_slot_px(
        caixa.width(), 5, painel._candles_velas_visiveis)
    assert largura_depois > largura_antes * 1.5


def test_arrastar_a_escala_de_preco_muda_os_pixels_por_tick(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    eixo = modulo_candles.retangulo_eixo_preco(caixa)
    antes = _px_por_tick(painel)
    assert antes > 0

    painel.mousePressEvent(_EventoFake(eixo.center().x(), eixo.center().y()))
    assert painel._arrasto_escala == "preco"
    # Arrastar pra CIMA amplia a escala: menos ticks na tela, mais px por tick.
    painel.mouseMoveEvent(_EventoFake(eixo.center().x(), eixo.center().y() - 120))
    depois = _px_por_tick(painel)
    painel.mouseReleaseEvent(_EventoFake(eixo.center().x(), eixo.center().y() - 120))

    assert painel._candles_zoom_preco > 1.0
    assert depois > antes * 1.4, (antes, depois)


def test_arrasto_no_meio_do_grafico_continua_sendo_pan_e_nao_escala(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    centro = caixa.center()
    painel.mousePressEvent(_EventoFake(centro.x(), centro.y()))
    assert painel._arrasto_escala is None
    assert painel._arrasto_candles_ativo
    painel.mouseMoveEvent(_EventoFake(centro.x() + 150, centro.y()))
    assert painel._candles_offset > 0
    assert painel._candles_velas_visiveis is None
    assert painel._candles_zoom_preco == 1.0


def test_roda_sobre_o_plot_e_sobre_o_eixo_atuam_em_escalas_diferentes(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    plot = modulo_candles.retangulo_plot(caixa)
    eixo = modulo_candles.retangulo_eixo_preco(caixa)

    painel.wheelEvent(_EventoFake(plot.center().x(), plot.center().y(), delta=120))
    assert painel._candles_velas_visiveis is not None
    assert painel._candles_velas_visiveis < modulo_candles.slots_da_janela(
        caixa.width(), 5, None)
    assert painel._candles_zoom_preco == 1.0

    painel.wheelEvent(_EventoFake(eixo.center().x(), eixo.center().y(), delta=120))
    assert painel._candles_zoom_preco > 1.0


def test_zoom_e_reversivel_e_limitado(qapp):
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    for _ in range(40):
        painel._aplicar_zoom_preco(1.15)
    assert painel._candles_zoom_preco <= modulo_candles.ZOOM_PRECO_MAX
    for _ in range(80):
        painel._aplicar_zoom_preco(1 / 1.15)
    assert painel._candles_zoom_preco >= modulo_candles.ZOOM_PRECO_MIN

    for _ in range(40):
        painel._aplicar_zoom_tempo(0.85, caixa)
    assert painel._candles_velas_visiveis == modulo_candles.VELAS_MIN
    for _ in range(80):
        painel._aplicar_zoom_tempo(1 / 0.85, caixa)
    assert painel._candles_velas_visiveis == modulo_candles.slots_da_janela(
        caixa.width(), painel._timeframe_candles_min, None)


def test_a_janela_com_zoom_recorta_as_velas_desenhadas(qapp):
    """O zoom de tempo tem de mudar o DADO enquadrado, nao so o rotulo."""
    painel = _painel(qapp)
    caixa = painel._retangulo_candles()
    antes = len(modulo_candles.velas_no_quadro(caixa, painel._estado_nexo()))
    painel._aplicar_zoom_tempo(0.3, caixa)
    depois = len(modulo_candles.velas_no_quadro(caixa, painel._estado_nexo()))
    assert depois < antes, (antes, depois)
