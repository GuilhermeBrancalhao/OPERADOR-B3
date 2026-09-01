"""Cenografia local; independente do feed e dos indicadores."""
import math
import os
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage


class FundoOperador:
    def __init__(self):
        caminho = os.environ.get("FLUXOPRO_WALLPAPER")
        self.imagem = QImage(caminho if caminho is not None else str(
            Path(__file__).parent / "assets" / "wallpaper-original.jpg"))
        self.reduzido = os.environ.get("FLUXOPRO_REDUCED_MOTION", "0") == "1"
        self.inicio = time.monotonic()
        self.alvo = (0.0, 0.0)
        self.cursor = (0.0, 0.0)
        self.cache = QImage()
        self.tamanho = None

    def avancar(self):
        if not self.reduzido:
            self.cursor = tuple(a + (b-a)*0.12 for a,b in zip(self.cursor, self.alvo))

    def pintar(self, painter, viewport, segundos=None):
        if self.imagem.isNull():
            return
        tamanho = (viewport.width(), viewport.height())
        if tamanho != self.tamanho:
            self.cache = self.imagem.scaled(
                viewport.size() + QSize(40, 40),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            self.tamanho = tamanho
        t = time.monotonic() - self.inicio if segundos is None else segundos
        fase = 0 if self.reduzido else 2*math.pi*(t % 48)/48
        dx = 0 if self.reduzido else 7*math.sin(fase) + self.cursor[0]
        dy = 0 if self.reduzido else 5*math.cos(fase) + self.cursor[1]
        x = viewport.x() + (viewport.width()-self.cache.width())//2 + round(dx)
        y = viewport.y() + (viewport.height()-self.cache.height())//2 + round(dy)
        painter.save()
        painter.setClipRect(viewport, Qt.ClipOperation.IntersectClip)
        painter.setOpacity(0.55)
        painter.drawImage(x, y, self.cache)
        painter.restore()


def pintar_fundo_compartilhado(painter, widget, regiao):
    """Recorte do mesmo canvas global, somente quando NEXO esta visivel.

    Os paineis Qt possuem backing stores proprios. Coordenadas globais evitam
    reiniciar a textura em cada widget e preservam a composicao parcial.
    """
    janela = widget.window()
    nexo = getattr(getattr(janela, 'asg', None), 'nexo', None)
    if nexo is None or not nexo.isVisible():
        return False
    central = janela.centralWidget()
    pos = widget.mapTo(central, QPoint(0, 0))
    viewport = QRect(-pos.x(), -pos.y(), central.width(), central.height())
    painter.save()
    painter.setClipRect(regiao, Qt.ClipOperation.IntersectClip)
    painter.fillRect(regiao, QColor('#030609'))
    nexo._fundo_operador.pintar(painter, viewport)
    painter.restore()
    return True
