"""Regiao PLACAR ESTATISTICO (x 0,00-0,40 · y 0,79-1,00).

Esqueleto extraido da fileira de leituras derivadas de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. Ancorado no canto inferior
esquerdo do quadro, sangrando ate as duas bordas.

Ladrilhos BUY/SELL, medalhao e tira de barras densas sao trabalho da parte 5;
aqui ficam as quatro leituras ja existentes, com procedencia declarada e sem
nenhuma acao associada.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

VAO_LADRILHO = 4
ALTURA_TITULO = 14


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return
    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 8, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "PLACAR ESTATISTICO  ·  LEITURAS DERIVADAS")

    leituras = estado.leituras
    if not leituras:
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM LEITURA DERIVADA")
        return
    corpo = QRect(rect.left(), rect.top() + ALTURA_TITULO + 2, rect.width(),
                  max(20, rect.height() - ALTURA_TITULO - 2))
    largura = max(40, (corpo.width() + VAO_LADRILHO) // len(leituras) - VAO_LADRILHO)
    for indice, (nome, linha) in enumerate(leituras):
        caixa = QRect(corpo.left() + indice * (largura + VAO_LADRILHO), corpo.top(),
                      largura, corpo.height())
        cor = _asg._cor_nexo_direcao(linha.direcao)
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        painter.fillRect(QRect(caixa.left(), caixa.top(), 2, caixa.height()), cor)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(7, 5, -5, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, nome)
        painter.setFont(tokens.fonte_numero(max(13, min(24, caixa.height() // 4)),
                                            QFont.Weight.Bold))
        painter.setPen(cor)
        painter.drawText(caixa.adjusted(7, 0, -5, -14), Qt.AlignmentFlag.AlignCenter,
                         f"{linha.forca * 100:+.0f}%")
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(7, 0, -5, -3),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         linha.valor[:12])
