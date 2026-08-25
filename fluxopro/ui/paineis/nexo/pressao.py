"""Regiao PRESSAO + INSTRUMENTO (x 0,63-1,00 · y 0,86-1,00).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_estatistica_nexo``.
Fecha o canto inferior direito do quadro, encostando nas duas bordas.

O par de leituras percentuais e um **proxy de pressao declarado**, derivado da
mesma linha MAKERPROXY do snapshot; nao e execucao, nao e posicao e nao ha
botao. O medalhao do instrumento, a amplitude em pontos e o lado do operador
sao trabalho da parte 9.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

ALTURA_SUBLINHADO = 4
MARGEM_INTERNA = 8


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 24 or rect.width() < 100:
        return
    maker = estado.maker
    score = maker.forca if maker is not None else 0.0
    compra = int(max(0.0, min(100.0, 50.0 + score * 50.0)))
    venda = 100 - compra

    # A regiao encosta na borda direita do quadro: o texto precisa da propria
    # margem interna, senao o glifo final e cortado pelo limite da janela.
    interno = rect.adjusted(MARGEM_INTERNA, 0, -MARGEM_INTERNA, 0)
    metade = interno.width() // 2
    tamanho = max(12, min(24, rect.height() // 4))
    painter.setFont(tokens.fonte_numero(tamanho, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_VERDE)
    painter.drawText(QRect(interno.left(), rect.top(), metade, rect.height() - 22),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     f"{compra:02d}%")
    painter.setPen(tema_asg.NEXO_ROSA)
    painter.drawText(QRect(interno.left() + metade, rect.top(), metade, rect.height() - 22),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     f"{venda:02d}%")

    trilho = QRect(interno.left(), rect.bottom() - 18, interno.width(), ALTURA_SUBLINHADO)
    painter.fillRect(trilho, tema_asg.NEXO_PAINEL_ALTO)
    largura_compra = int(trilho.width() * compra / 100)
    painter.fillRect(QRect(trilho.left(), trilho.top(), largura_compra, trilho.height()),
                     tema_asg.NEXO_VERDE)
    painter.fillRect(QRect(trilho.left() + largura_compra, trilho.top(),
                           trilho.width() - largura_compra, trilho.height()),
                     tema_asg.NEXO_ROSA)

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    rodape = QRect(interno.left(), rect.bottom() - 13, interno.width(), 13)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "COMPRA")
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter,
                     "PROXY DE PRESSAO · NAO E EXECUCAO")
    painter.drawText(rodape, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     "VENDA")
