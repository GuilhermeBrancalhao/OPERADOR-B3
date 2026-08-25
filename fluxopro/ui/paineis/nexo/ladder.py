"""Regiao ESCADA DE PRECO (x 0,00-0,06 · y 0,00-0,56).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_ladder_nexo``. Pinta o
livro observado como coluna de niveis, sem moldura, sangrando ate a borda
esquerda do quadro. O conteudo fino da regiao (segunda micro-coluna, capsula do
preco corrente, marcador de nivel) e trabalho da parte 1 — aqui esta apenas a
costura para que ela exista como arquivo proprio.

Nao ha clique, callback nem campo: a coluna e leitura.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

# Faixa de altura de linha aceitavel. Fora dela a coluna vira ou uma lista de
# tres numeros gigantes ou uma serrilha ilegivel.
ALTURA_LINHA_MIN = 9
ALTURA_LINHA_MAX = 20
NIVEIS_POR_LADO = 3


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    contexto = getattr(estado.snapshot, "contexto_bruto", None)
    if contexto is None or rect.height() < ALTURA_LINHA_MIN * 2:
        return
    asks = tuple(contexto.asks[:NIVEIS_POR_LADO])
    bids = tuple(contexto.bids[:NIVEIS_POR_LADO])
    niveis = asks + bids
    if not niveis:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM\nBOOK")
        return
    maximo = max(1, max(nivel.quantidade for nivel in niveis))
    altura = max(ALTURA_LINHA_MIN,
                 min(ALTURA_LINHA_MAX, rect.height() // max(1, len(niveis))))
    painter.setFont(tokens.fonte_numero(7, QFont.Weight.DemiBold))
    for indice, nivel in enumerate(niveis):
        y = rect.y() + indice * altura
        eh_ask = indice < len(asks)
        cor = tema_asg.NEXO_ROSA if eh_ask else tema_asg.NEXO_VERDE
        largura = max(2, int(rect.width() * nivel.quantidade / maximo))
        x = rect.right() - largura if eh_ask else rect.left()
        painter.fillRect(QRect(x, y + 1, largura, max(2, altura - 3)),
                         tema_asg.NEXO_ROSA_FAIXA if eh_ask else tema_asg.NEXO_VERDE_FAIXA)
        painter.setPen(cor)
        preco = formato.formatar_preco(estado.grid, nivel.preco)
        painter.drawText(QRect(rect.left(), y, rect.width(), altura),
                         Qt.AlignmentFlag.AlignCenter,
                         f"{preco[0]}{preco[1]}")
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left(), rect.y() + len(niveis) * altura, rect.width(), 12),
                     Qt.AlignmentFlag.AlignCenter, "LIVRO")
