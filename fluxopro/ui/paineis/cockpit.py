"""Peças do cockpit OPERADOR B3: prisma, gauges e radar de decisão.

As classes deste módulo são superfícies finas. A regra de negócio continua
no motor e na metodologia; o cockpit só recebe snapshots imutáveis e mostra
estado, procedência e direção com texto mais glifo. Isso evita que a cor verde
ou vermelha seja o único canal de uma decisão.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso


@dataclass(frozen=True, slots=True)
class EstadoCockpit:
    """DTO visual; nenhum acumulador ou objeto da thread de mercado."""

    direcao: str = "NEUTRO"
    estagio: str = "AGUARDAR"
    macro: int = 0
    micro: int = 0
    variacao: str = "—"
    confianca: str = "CONF —"
    estado: str = "AGUARDANDO"


def _cor_direcao(texto: str):
    alto = texto.upper()
    if "COMPRA" in alto or "BUY" in alto:
        return tema_asg.NEXO_VERDE
    if "VENDA" in alto or "SELL" in alto:
        return tema_asg.NEXO_ROSA
    return tema_asg.NEXO_AMARELO


class PainelCockpit(PainelDenso):
    """Composição testável dos quatro sinais visuais principais."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)
        self.estado = EstadoCockpit()

    def aplicar(self, estado: EstadoCockpit | object) -> None:
        if isinstance(estado, EstadoCockpit):
            self.estado = estado
        else:
            decisao = getattr(estado, "decisao", estado)
            self.estado = EstadoCockpit(
                direcao=str(getattr(decisao, "direcao", "NEUTRO")),
                estagio=str(getattr(decisao, "titulo", "AGUARDAR")),
                confianca=str(getattr(decisao, "confianca", "CONF —")),
                estado=str(getattr(estado, "estado_operacional", "AGUARDANDO")),
            )
        self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self.estado
        return ("COCKPIT", "PRISMA 3D", "CONTEXTO", "RADAR DE DECISAO", s.direcao,
                s.estagio, s.confianca, s.estado)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, tema_asg.NEXO_FUNDO)
        s = self.estado
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(regiao.adjusted(8, 5, -8, -regiao.height() + 20),
                         Qt.AlignmentFlag.AlignLeft, "COCKPIT · CONTEXTO · RADAR")
        centro = QPoint(regiao.center().x(), regiao.center().y())
        raio = max(22, min(regiao.width(), regiao.height()) // 5)
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawEllipse(centro, raio + 10, raio + 10)
        painter.setPen(_cor_direcao(s.direcao))
        painter.drawEllipse(centro, raio, raio)
        painter.setFont(tokens.fonte_numero(14, QFont.Weight.Bold))
        painter.drawText(QRect(centro.x() - raio, centro.y() - 10, 2 * raio, 20),
                         Qt.AlignmentFlag.AlignCenter, s.direcao[:8].upper())
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(regiao.adjusted(8, 0, -8, -8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         f"PRISMA 3D · MACRO {s.macro:+d} · MICRO {s.micro:+d}")


__all__ = ["EstadoCockpit", "PainelCockpit"]
