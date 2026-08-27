"""Smoke test do bloco OPERADOR IA / vies (fluxopro/ui/paineis/nexo/vies.py).

Cobre o retoque de profundidade/3D (26/08/2026, gradiente radial + sombra +
brilho especular): so precisa desenhar sem excecao para as 4 direcoes, e sem
depender de tela real (offscreen via `qapp`).
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.ui.paineis.asg import (
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    MatrizASGSnapshot,
    ProcessamentoASGSnapshot,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import vies
from fluxopro.ui import tokens


def _snapshot(direcao):
    return WorkspaceASGSnapshot(
        0,
        DadosASGSnapshot(0, estado=EstadoASG.AO_VIVO),
        ProcessamentoASGSnapshot(0, estado=EstadoASG.AO_VIVO),
        MatrizASGSnapshot(0, estado=EstadoASG.AO_VIVO),
        DecisaoASGSnapshot(0, estado=EstadoASG.AO_VIVO, direcao=direcao),
        TrilhaEvidenciasASGSnapshot(0, estado=EstadoASG.AO_VIVO),
        contexto_bruto=None,
    )


def _estado_com_direcao(direcao):
    snap = _snapshot(direcao)
    return EstadoNexo(
        snapshot=snap,
        serie=(),
        grid=None,
        paleta=tokens.PALETA_COR,
        maker=None,
        leituras=(),
        largura=200,
        altura=200,
    )


def _desenha_sem_excecao(direcao):
    pixmap = QPixmap(200, 200)
    painter = QPainter(pixmap)
    try:
        vies.desenhar(painter, QRect(0, 0, 200, 200), _estado_com_direcao(direcao))
    finally:
        painter.end()


def test_desenha_compra(qapp):
    _desenha_sem_excecao(DirecaoASG.COMPRA)


def test_desenha_venda(qapp):
    _desenha_sem_excecao(DirecaoASG.VENDA)


def test_desenha_aguardar(qapp):
    _desenha_sem_excecao(DirecaoASG.AGUARDAR)


def test_desenha_neutra(qapp):
    _desenha_sem_excecao(DirecaoASG.NEUTRA)
