"""Regiao VISOR HUD (x 0,40-0,63 · y 0,02-0,42).

Esqueleto extraido da metade superior de
``PainelNexoMercadoASG._desenhar_nucleo_nexo``: moldura do visor, glifo
direcional e os tres cartoes curtos de regime/confianca/evidencias.

O visor **nao e um botao**: nao tem estado de hover, pressed nem callback. O
chanfro octogonal, o carimbo de tempo e o segundo estado do visor sao trabalho
da parte 6.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

RAIO_MIN = 26
RAIO_MAX = 62
ALTURA_CARTAO = 28
VAO_CARTAO = 3


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 90 or rect.height() < 90:
        return
    decisao = estado.snapshot.decisao
    cor = _asg._cor_nexo_direcao(decisao.direcao)

    moldura = QRect(rect.left(), rect.top(), rect.width(),
                    max(60, rect.height() - ALTURA_CARTAO - 34))
    painter.setPen(tema_asg.NEXO_GRADE)
    painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
    painter.drawPolygon(_octogono(moldura))
    painter.setBrush(Qt.BrushStyle.NoBrush)

    cx, cy = moldura.center().x(), moldura.center().y()
    raio = max(RAIO_MIN, min(RAIO_MAX, min(moldura.width(), moldura.height()) // 3))
    painter.setBrush(cor)
    simbolo = QPolygon([QPoint(cx, cy - raio), QPoint(cx - raio, cy + raio // 2),
                        QPoint(cx + raio, cy + raio // 2)])
    if decisao.direcao is _asg.DirecaoASG.VENDA:
        simbolo = QPolygon([QPoint(cx - raio, cy - raio // 2),
                            QPoint(cx + raio, cy - raio // 2), QPoint(cx, cy + raio)])
    painter.drawPolygon(simbolo)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setFont(tokens.fonte_ui(8, QFont.Weight.DemiBold))
    painter.setPen(cor)
    painter.drawText(QRect(rect.left(), moldura.bottom() + 2, rect.width(), 15),
                     Qt.AlignmentFlag.AlignCenter, decisao.titulo.upper())
    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left(), moldura.bottom() + 16, rect.width(), 14),
                     Qt.AlignmentFlag.AlignCenter, "SINAL CONSULTIVO")

    regime = next((linha for linha in estado.snapshot.matriz.linhas
                   if linha.componente == "REGIME"), None)
    cartoes = (
        ("REGIME", "—" if regime is None else regime.valor, tema_asg.NEXO_CIANO),
        ("CONFIANCA", decisao.confianca.value.replace("CONF ", ""), cor),
        ("EVID.", str(estado.snapshot.evidencias.retidos), tema_asg.NEXO_AMARELO),
    )
    largura = max(32, (rect.width() + VAO_CARTAO) // len(cartoes) - VAO_CARTAO)
    y = rect.bottom() - ALTURA_CARTAO
    for indice, (nome, valor, cor_cartao) in enumerate(cartoes):
        caixa = QRect(rect.left() + indice * (largura + VAO_CARTAO), y,
                      largura, ALTURA_CARTAO)
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(3, 1, -3, -14), Qt.AlignmentFlag.AlignCenter, nome)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
        painter.setPen(cor_cartao)
        painter.drawText(caixa.adjusted(3, 12, -3, -1), Qt.AlignmentFlag.AlignCenter,
                         valor[:12])


def _octogono(rect: QRect) -> QPolygon:
    """Moldura com cantos chanfrados, proporcional ao lado menor."""

    chanfro = max(8, min(rect.width(), rect.height()) // 6)
    return QPolygon([
        QPoint(rect.left() + chanfro, rect.top()),
        QPoint(rect.right() - chanfro, rect.top()),
        QPoint(rect.right(), rect.top() + chanfro),
        QPoint(rect.right(), rect.bottom() - chanfro),
        QPoint(rect.right() - chanfro, rect.bottom()),
        QPoint(rect.left() + chanfro, rect.bottom()),
        QPoint(rect.left(), rect.bottom() - chanfro),
        QPoint(rect.left(), rect.top() + chanfro),
    ])
