"""Regiao CONTEXTO (x 0,06-0,34 · y 0,00-0,56).

Esqueleto extraido da metade superior de
``PainelNexoMercadoASG._desenhar_contexto_nexo``: arcos concentricos com a
leitura dominante, prisma de pressao e as quatro leituras derivadas. Sem
moldura de cartao — a cena sangra no fundo do quadro.

Prisma e arcos sao forma, nao asset: a direcao viaja em cor **e** em texto,
para sobreviver ao modo sem cor. Nada aqui e clicavel.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPolygon

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

FRACAO_CENTRO_X = 0.40
FRACAO_CENTRO_Y = 0.40
RAIO_MIN = 32
RAIO_MAX = 92
ARCO_INICIO_GRAUS = 25
ARCO_EXTENSAO_GRAUS = 238


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 80 or rect.height() < 80:
        return
    maker = estado.maker
    score = maker.forca if maker is not None else 0.0
    direcao = maker.direcao if maker is not None else _asg.DirecaoASG.NEUTRA
    cor = _asg._cor_nexo_direcao(direcao)

    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(4, 4, -4, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "CONTEXTO")

    centro = QPoint(rect.left() + int(rect.width() * FRACAO_CENTRO_X),
                    rect.top() + int(rect.height() * FRACAO_CENTRO_Y))
    raio = max(RAIO_MIN, min(RAIO_MAX, min(rect.width(), rect.height()) // 4))
    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawEllipse(centro, raio + 15, raio + 15)
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawArc(QRect(centro.x() - raio - 7, centro.y() - raio - 7,
                          2 * (raio + 7), 2 * (raio + 7)),
                    ARCO_INICIO_GRAUS * 16, ARCO_EXTENSAO_GRAUS * 16)
    painter.setPen(cor)
    painter.drawEllipse(centro, raio, raio)
    painter.setFont(tokens.fonte_numero(max(15, min(28, raio // 2)), QFont.Weight.Bold))
    painter.drawText(QRect(centro.x() - raio, centro.y() - 17, 2 * raio, 34),
                     Qt.AlignmentFlag.AlignCenter, f"{score * 100:+.0f}%")
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(QRect(centro.x() - raio - 20, centro.y() + raio + 7,
                           2 * (raio + 20), 16), Qt.AlignmentFlag.AlignCenter,
                     "COMPRA" if direcao is _asg.DirecaoASG.COMPRA else
                     "VENDA" if direcao is _asg.DirecaoASG.VENDA else "EQUILIBRIO")

    _prisma(painter, rect, score, cor)

    ultimo = estado.serie[-1][1] if estado.serie else None
    if ultimo is not None:
        preco = formato.formatar_preco(estado.grid, ultimo)
        painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(rect.adjusted(4, 4, -4, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         f"{preco[0]}{preco[1]}")

    # A coluna de leituras encosta na borda direita da regiao; o prisma fica a
    # esquerda dela, em faixa propria, para que os dois nao se sobreponham em
    # nenhuma largura de janela.
    largura_leituras = max(76, min(110, rect.width() // 4))
    _leituras(painter, QRect(rect.right() - largura_leituras,
                             rect.top() + int(rect.height() * 0.34),
                             largura_leituras,
                             min(120, rect.height() // 3)), estado)


def _prisma(painter: QPainter, rect: QRect, score: float, cor) -> None:
    """Volume isometrico da pressao observada — forma, nao logotipo."""

    largura = max(34, rect.width() // 9)
    altura = max(52, rect.height() // 5)
    x = rect.left() + int(rect.width() * 0.56)
    y = rect.top() + int(rect.height() * 0.56)
    frente = QPolygon([QPoint(x, y + 12), QPoint(x + largura, y),
                       QPoint(x + largura, y + altura), QPoint(x, y + altura + 12)])
    topo = QPolygon([QPoint(x, y + 12), QPoint(x + largura // 2, y - 5),
                     QPoint(x + largura, y), QPoint(x + largura // 2, y + 17)])
    lado = QPolygon([QPoint(x + largura, y), QPoint(x + largura + 17, y + 11),
                     QPoint(x + largura + 17, y + altura + 8),
                     QPoint(x + largura, y + altura)])
    painter.setPen(cor)
    painter.setBrush(tema_asg.NEXO_VERDE_FAIXA if score >= 0 else tema_asg.NEXO_ROSA_FAIXA)
    for poligono in (frente, topo, lado):
        painter.drawPolygon(poligono)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.drawText(QRect(x - 12, y + altura + 19, largura + 40, 16),
                     Qt.AlignmentFlag.AlignCenter, f"{score * 100:+.1f}%")
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(x - 18, y - 22, largura + 52, 14),
                     Qt.AlignmentFlag.AlignCenter, "MAKER PROXY")


def _leituras(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    linhas = estado.leituras
    if not linhas or rect.height() < 42:
        return
    altura = max(16, rect.height() // len(linhas))
    for indice, (nome, linha) in enumerate(linhas):
        y = rect.y() + indice * altura
        cor = _asg._cor_nexo_direcao(linha.direcao)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(QRect(rect.left(), y, rect.width() // 2, altura),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
        painter.setPen(cor)
        painter.drawText(QRect(rect.left() + rect.width() // 2, y, rect.width() // 2, altura),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         linha.valor)
