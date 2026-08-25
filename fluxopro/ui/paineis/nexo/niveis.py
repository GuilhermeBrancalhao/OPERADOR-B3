"""Regiao FAIXA DE NIVEIS (x 0,02-0,40 · y 0,55-0,65).

Esqueleto extraido da fileira de cotacoes de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. A faixa avanca um centesimo
do quadro sobre CONTEXTO/ESCADA de proposito: e a costura horizontal que amarra
a coluna da esquerda, e nao um cartao separado.

Os chips sao **capsulas de leitura**. Nao existe estado de foco/clique e nao ha
callback: nenhum nivel aqui pode ser acionado.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

VAO_CHIP = 4
ALTURA_CHIP_MAX = 46


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 24 or rect.width() < 80:
        return
    contexto = getattr(estado.snapshot, "contexto_bruto", None)
    cotacoes: list[tuple[str, int, object]] = []
    if contexto is not None:
        if contexto.bids:
            cotacoes.append(("BID", contexto.bids[0].preco, tema_asg.NEXO_VERDE))
        if contexto.ultimo_preco is not None:
            cotacoes.append(("ULT", int(contexto.ultimo_preco), tema_asg.NEXO_CIANO))
        if contexto.asks:
            cotacoes.append(("ASK", contexto.asks[0].preco, tema_asg.NEXO_ROSA))
    if not cotacoes:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "SEM NIVEIS OBSERVADOS")
        return
    largura = max(48, (rect.width() + VAO_CHIP) // len(cotacoes) - VAO_CHIP)
    altura = min(rect.height(), ALTURA_CHIP_MAX)
    topo = rect.bottom() - altura
    for indice, (nome, preco, cor) in enumerate(cotacoes):
        caixa = QRect(rect.left() + indice * (largura + VAO_CHIP), topo, largura, altura)
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        painter.fillRect(QRect(caixa.left(), caixa.top(), 2, caixa.height()), cor)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(6, 2, -4, -caixa.height() + 13),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{indice + 1}  {nome}")
        formatado = formato.formatar_preco(estado.grid, preco)
        painter.setFont(tokens.fonte_numero(11, QFont.Weight.Bold))
        painter.setPen(cor)
        painter.drawText(caixa.adjusted(6, 11, -4, -2),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{formatado[0]}{formatado[1]}")
