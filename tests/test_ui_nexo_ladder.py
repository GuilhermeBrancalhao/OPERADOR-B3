"""Smoke test do VAP (fluxopro/ui/paineis/nexo/ladder.py).

Cobre o retoque visual (26/08/2026, barras em gradiente + marcador de POC):
so precisa desenhar sem excecao, com e sem niveis, com e sem POC.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import ladder


def _estado(vap_niveis=(), vap_poc=None, serie=()):
    return EstadoNexo(
        snapshot=None,
        serie=serie,
        grid=WDO_GRID,
        paleta=None,
        maker=None,
        leituras=(),
        largura=200,
        altura=300,
        vap_niveis=vap_niveis,
        vap_poc=vap_poc,
    )


def _desenha_sem_excecao(estado):
    pixmap = QPixmap(200, 300)
    painter = QPainter(pixmap)
    try:
        ladder.desenhar(painter, QRect(0, 0, 200, 300), estado)
    finally:
        painter.end()


def test_desenha_sem_vap(qapp):
    _desenha_sem_excecao(_estado())


def test_desenha_com_niveis_e_poc(qapp):
    niveis = (
        (100000, 500, 300, 200, True),
        (100001, 900, 100, 800, True),
        (100002, 120, 60, 60, False),
        (100003, 750, 700, 50, True),
    )
    estado = _estado(vap_niveis=niveis, vap_poc=100001, serie=((0, 100001, 0.0, 1),))
    _desenha_sem_excecao(estado)


def test_desenha_com_niveis_sem_poc_destacado_visivel(qapp):
    niveis = ((100000, 500, 300, 200, True),)
    estado = _estado(vap_niveis=niveis, vap_poc=999999, serie=((0, 100000, 0.0, 1),))
    _desenha_sem_excecao(estado)
