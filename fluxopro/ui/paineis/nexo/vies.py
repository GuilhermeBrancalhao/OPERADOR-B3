"""Regiao IDENTIDADE / VIES (x 0,42-0,62 · y 0,62-1,00).

Esqueleto extraido do bloco de marca de
``PainelNexoMercadoASG._desenhar_nucleo_nexo``. Ocupa o pe da coluna central,
sangrando ate a borda inferior do quadro.

Duas responsabilidades convivem aqui e a parte 10 e quem as separa:

1. o **bloco de identidade** do produto — geometria autoral do NEXO/FluxoPro,
   nenhum logotipo, rosto, marca ou asset de terceiro e reproduzido;
2. o **resolvedor de paleta por vies** que fara o quadro inteiro comutar
   coerentemente entre leitura de alta e de baixa. ``cor_vies`` abaixo e o
   ponto de entrada previsto para isso; hoje ele apenas repassa a resolucao ja
   existente, sem inventar regra nova.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

RAIO_MIN = 20
RAIO_MAX = 48


def cor_vies(estado: EstadoNexo) -> QColor:
    """Cor dominante do quadro, derivada da direcao ja publicada no snapshot.

    Ponto unico de resolucao para a parte 10 propagar o vies as demais
    regioes. Nao infere direcao: le a que o snapshot trouxe.
    """

    return _asg._cor_nexo_direcao(estado.snapshot.decisao.direcao)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 70 or rect.height() < 70:
        return
    cor = cor_vies(estado)
    cx = rect.center().x()
    cy = rect.top() + max(38, (rect.height() - 34) // 2)
    raio = max(RAIO_MIN, min(RAIO_MAX, rect.width() // 3))

    painter.setPen(QPen(tema_asg.NEXO_CIANO, 1))
    painter.drawEllipse(QPoint(cx, cy), raio + 12, raio + 12)
    gradiente = QLinearGradient(cx - raio, cy - raio, cx + raio, cy + raio)
    gradiente.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
    gradiente.setColorAt(1.0, tema_asg.NEXO_CIANO)
    painter.setBrush(gradiente)
    painter.drawEllipse(QPoint(cx, cy - 5), raio, raio + 8)
    painter.setBrush(cor)
    painter.drawPolygon(QPolygon([QPoint(cx - raio + 6, cy + raio),
                                  QPoint(cx, cy + raio // 3),
                                  QPoint(cx + raio - 6, cy + raio)]))
    painter.setBrush(tema_asg.NEXO_FUNDO)
    painter.drawEllipse(QPoint(cx - raio // 3, cy - 6), 3, 3)
    painter.drawEllipse(QPoint(cx + raio // 3, cy - 6), 3, 3)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.setFont(tokens.fonte_numero(max(13, min(24, rect.width() // 9)),
                                        QFont.Weight.Bold))
    painter.drawText(QRect(rect.left(), rect.bottom() - 30, rect.width(), 18),
                     Qt.AlignmentFlag.AlignCenter, "NEXO")
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left(), rect.bottom() - 13, rect.width(), 13),
                     Qt.AlignmentFlag.AlignCenter, "FLOW INTELLIGENCE · PROXY PROPRIO")
