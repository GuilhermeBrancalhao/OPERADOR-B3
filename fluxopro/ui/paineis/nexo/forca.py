"""Regiao GRAFICO DE FORCA (x 0,63-1,00 · y 0,00-0,33).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_forca_nexo``. Ocupa o
topo direito inteiro, encostando na borda superior e na direita do quadro, sem
moldura.

A serie e exclusivamente visual e derivada dos negocios ja observados: sem
lookahead, sem fonte nova, sem alegar formula de terceiro. A serrilha, a linha
pontilhada e o trilho de eixo de preco sao trabalho da parte 7.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QLinearGradient, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

FRACOES_GRADE = (0.25, 0.50, 0.75)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 60:
        return
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)
    painter.setPen(tema_asg.NEXO_GRADE)
    for fracao in FRACOES_GRADE:
        y = rect.top() + round(rect.height() * fracao)
        painter.drawLine(rect.left(), y, rect.right(), y)

    amostras = estado.serie
    if len(amostras) < 2:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "AGUARDANDO DADOS DE MERCADO")
        return

    pontos = []
    for indice, (_, _, valor, _) in enumerate(amostras):
        x = rect.left() + round(indice * max(1, rect.width() - 1) / max(1, len(amostras) - 1))
        y = rect.bottom() - 8 - round((valor + 1.0) * max(1, rect.height() - 26) / 2.0)
        pontos.append(QPoint(x, y))
    ultimo = amostras[-1][2]
    cor = tema_asg.NEXO_VERDE if ultimo >= 0 else tema_asg.NEXO_ROSA
    area = QPolygon(pontos + [QPoint(rect.right(), rect.bottom() - 7),
                              QPoint(rect.left(), rect.bottom() - 7)])
    gradiente = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    gradiente.setColorAt(0.0, tema_asg.NEXO_VERDE_FAIXA if ultimo >= 0 else tema_asg.NEXO_ROSA_FAIXA)
    gradiente.setColorAt(1.0, tema_asg.NEXO_PAINEL)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradiente)
    painter.drawPolygon(area)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(cor, 2))
    painter.drawPolyline(QPolygon(pontos))

    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.drawText(rect.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     f"FORCA {ultimo * 100:+.0f}%")
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(rect.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                     "JANELA CAUSAL")
    media = sum(item[2] for item in amostras) / len(amostras)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(rect.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     f"MEDIA {media * 100:+.0f}%")
    painter.drawText(rect.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                     f"{len(amostras)} NEGOCIOS")
