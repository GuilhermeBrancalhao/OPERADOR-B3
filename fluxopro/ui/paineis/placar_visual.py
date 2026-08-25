"""Placar, pressão e marca própria do OPERADOR B3.

São painéis consultivos: toggles futuros devem apenas alterar camadas de
visualização. Nenhum método deste módulo conhece barramento, sessão, MT5 ou
qualquer API de ordem.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QFont

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso


class PainelPlacarVisual(PainelDenso):
    """Placar BUY/SELL com histórico limitado de votos."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)
        self._buy = 0
        self._sell = 0
        self._votos: deque[int] = deque(maxlen=128)

    def aplicar(self, snapshot: object) -> None:
        placar = getattr(snapshot, "placar", snapshot)
        self._buy = int(getattr(placar, "buy", getattr(placar, "compras", 0)) or 0)
        self._sell = int(getattr(placar, "sell", getattr(placar, "vendas", 0)) or 0)
        lado = getattr(snapshot, "lado_placar", 0)
        self._votos.append(1 if str(lado).upper().endswith("BUY") else -1 if str(lado).upper().endswith("SELL") else 0)
        self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        return ("PLACAR ESTATISTICO", "BUY", str(self._buy), "SELL", str(self._sell), "MICRO", "SUP/RES", "CHART")

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(regiao.adjusted(8, 5, -8, -regiao.height() + 20), Qt.AlignmentFlag.AlignCenter,
                         "PLACAR ESTATISTICO")
        meio = regiao.center().x()
        painter.setPen(tema_asg.NEXO_VERDE)
        painter.setFont(tokens.fonte_numero(18, QFont.Weight.Bold))
        painter.drawText(QRect(regiao.left() + 8, regiao.top() + 24, regiao.width() // 2 - 12, 30),
                         Qt.AlignmentFlag.AlignCenter, f"▲ BUY  {self._buy}")
        painter.setPen(tema_asg.NEXO_ROSA)
        painter.drawText(QRect(meio + 4, regiao.top() + 24, regiao.width() // 2 - 12, 30),
                         Qt.AlignmentFlag.AlignCenter, f"▼ SELL  {self._sell}")
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawLine(meio, regiao.top() + 22, meio, regiao.bottom() - 8)
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(regiao.adjusted(8, regiao.height() - 26, -8, -5), Qt.AlignmentFlag.AlignCenter,
                         "MICRO  ·  SUP/RES  ·  ▲▼  ·  CHART  ·  SEM ORDENS")


class PainelPressaoMercado(PainelDenso):
    """Percentuais de pressão com ressalva explícita para amostra pequena."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)
        self.compra = 50
        self.venda = 50
        self.amostra_suficiente = False

    def aplicar(self, compra: int, venda: int, amostra_suficiente: bool = True) -> None:
        total = max(1, int(compra) + int(venda))
        self.compra = int(100 * compra / total)
        self.venda = 100 - self.compra
        self.amostra_suficiente = bool(amostra_suficiente)
        self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        return (f"COMPRA {self.compra}%", f"VENDA {self.venda}%",
                "AMOSTRA INSUFICIENTE" if not self.amostra_suficiente else "AMOSTRA OK")

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setFont(tokens.fonte_numero(14, QFont.Weight.Bold))
        painter.setPen(tema_asg.NEXO_VERDE)
        painter.drawText(regiao.adjusted(8, 4, -regiao.width() // 2, -10), Qt.AlignmentFlag.AlignLeft,
                         f"▲ {self.compra}%")
        painter.setPen(tema_asg.NEXO_ROSA)
        painter.drawText(regiao.adjusted(regiao.width() // 2, 4, -8, -10), Qt.AlignmentFlag.AlignRight,
                         f"▼ {self.venda}%")
        barra = QRect(regiao.left() + 8, regiao.center().y(), regiao.width() - 16, 9)
        painter.fillRect(barra, tema_asg.NEXO_PAINEL_ALTO)
        painter.fillRect(QRect(barra.left(), barra.top(), barra.width() * self.compra // 100, barra.height()), tema_asg.NEXO_VERDE)
        painter.fillRect(QRect(barra.left() + barra.width() * self.compra // 100, barra.top(), barra.width() * self.venda // 100, barra.height()), tema_asg.NEXO_ROSA)
        if not self.amostra_suficiente:
            painter.setFont(tokens.fonte_rotulo(9))
            painter.setPen(tema_asg.NEXO_TEXTO)
            painter.drawText(regiao.adjusted(8, 0, -8, -5), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                             "AMOSTRA INSUFICIENTE")


class PainelMarcaOperador(PainelDenso):
    """Bloco de marca próprio, geométrico e sem raster de terceiro."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)

    def textos_visiveis(self) -> tuple[str, ...]:
        return ("OPERADOR B3", "MODO SINAIS", "NAO ENVIA ORDEM")

    def aplicar(self, snapshot: object | None = None) -> None:
        """Marca visualmente o quadro sem reter o snapshot mutável."""

        self.marcar_tudo_sujo()

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        cx, cy = regiao.center().x(), regiao.top() + max(24, regiao.height() // 3)
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawEllipse(cx, cy, 28, 28)
        painter.drawLine(cx + 14, cy + 28, cx, cy + 48)
        painter.drawLine(cx, cy + 48, cx - 14, cy + 28)
        painter.setFont(tokens.fonte_ui(16, QFont.Weight.Bold))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(regiao.adjusted(4, regiao.height() // 2, -4, -25), Qt.AlignmentFlag.AlignCenter,
                         "OPERADOR B3")
        painter.setFont(tokens.fonte_rotulo(9))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(regiao.adjusted(4, 0, -4, -6), Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                         "MODO SINAIS · NAO ENVIA ORDEM")


__all__ = ["PainelMarcaOperador", "PainelPlacarVisual", "PainelPressaoMercado"]
