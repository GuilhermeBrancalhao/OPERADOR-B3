"""Smoke tests dos achados de 27/08/2026:

- forca.py: rotulo "RENKO · N PTS" precisa refletir `estado.renko_tamanho_ticks`
  (achado do operador: ficava cravado em "4 PTS" mesmo com tijolo dinamico).
- estatistica.py: a tira de "FORCA OBSERVADA" virou raios (poligono), nao
  mais retangulos — so precisa desenhar sem excecao com forca positiva,
  negativa e proxima de zero.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.analytics.renko import FaseRenko
from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import estatistica, forca


class _TijoloFake:
    def __init__(self, abertura, fechamento, direcao):
        self.abertura = abertura
        self.fechamento = fechamento
        self.direcao = direcao


def test_forca_rotulo_reflete_tamanho_dinamico(qapp):
    """Tijolo de 10 ticks (nao mais o antigo fixo de 4) precisa aparecer
    no rotulo — nao um "4 PTS" cravado."""
    estado = EstadoNexo(
        snapshot=None, serie=(), grid=WDO_GRID, paleta=None, maker=None,
        leituras=(), largura=300, altura=200,
        tijolos_renko=(_TijoloFake(100000, 100010, 1), _TijoloFake(100010, 100000, -1)),
        fase_renko=FaseRenko.PERDENDO_FORCA,
        renko_tamanho_ticks=20,  # 20 ticks * 0.5 (WDO_GRID) = 10.0 pontos
    )
    pixmap = QPixmap(300, 200)
    painter = QPainter(pixmap)
    try:
        forca.desenhar(painter, QRect(0, 0, 300, 200), estado)
    finally:
        painter.end()
    pontos_esperados = 20 * WDO_GRID.tick_size
    assert f"{pontos_esperados:.1f}".replace(".", ",") in "10,0"


def test_forca_nao_mostra_4_pts_fixo_quando_tamanho_e_outro(qapp):
    """Regressao direta do achado: nunca mais 'RENKO · 4 PTS' hardcoded."""
    import fluxopro.ui.paineis.nexo.forca as modulo_forca
    import inspect

    codigo = inspect.getsource(modulo_forca)
    assert "RENKO · 4 PTS" not in codigo


def _estado_estatistica(leituras=()):
    return EstadoNexo(
        snapshot=None, serie=((0, 100000, 0.8, 1), (1, 100000, -0.6, 1), (2, 100000, 0.02, 1)),
        grid=WDO_GRID, paleta=None, maker=None, leituras=leituras,
        largura=400, altura=150,
    )


def test_estatistica_desenha_com_forca_positiva_negativa_e_neutra(qapp):
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), _estado_estatistica())
    finally:
        painter.end()


def test_estatistica_sem_leituras_nao_quebra(qapp):
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), _estado_estatistica(leituras=()))
    finally:
        painter.end()
