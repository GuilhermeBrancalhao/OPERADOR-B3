"""Regiao BANNER DE ESTADO (x 0,00-0,40 · y 0,65-0,78).

Esqueleto extraido do bloco de decisao consultiva de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. Ocupa a faixa inteira, da
borda esquerda ate 0,40 do quadro, sem cartao ao redor.

A palavra de estado e **leitura**, nunca comando: AGUARDAR/COMPRA/VENDA aqui
descrevem o que foi observado e nao existe superficie clicavel que execute
qualquer coisa. A cunha diagonal de alerta e o acabamento tipografico ficam com
a parte 4.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

LIMITE_MOTIVO = 96


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return
    decisao = estado.snapshot.decisao
    cor = _asg._cor_nexo_direcao(decisao.direcao)

    painter.setFont(tokens.fonte_ui(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 8, 14),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     decisao.motivo[:LIMITE_MOTIVO].upper())

    titulo = ("AGUARDAR" if decisao.direcao is _asg.DirecaoASG.AGUARDAR
              else decisao.direcao.value)
    tamanho = max(14, min(30, rect.height() // 3))
    painter.setFont(tokens.fonte_numero(tamanho, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(QRect(rect.left() + 4, rect.top() + 14, rect.width() - 8,
                           max(18, rect.height() - 30)),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_CIANO)
    painter.drawText(QRect(rect.left() + 4, rect.bottom() - 14, rect.width() - 8, 14),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     f"CONFIANCA · {decisao.confianca.value}  ·  LEITURA CONSULTIVA")
