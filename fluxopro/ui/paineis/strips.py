"""Strips de topo e rodape — §4.3 e §3.5.

Existem para corrigir a fraqueza F3 de §1: no Profit Pro os medidores de
agressao moram numa JANELA propria, que o operador tem de manter aberta,
posicionar e olhar. Aqui o resumo do dia e o estado da conexao vivem numa
faixa permanente de 28px no topo e 22px no rodape — sempre visiveis, nunca
disputando espaco com o dado.

E a razao de o estado do feed ficar aqui, e nao num dialogo, esta em §3.5:
**num terminal de fluxo o estado da conexao e informacao de trading.** Um
dado atrasado que parece vivo e pior que uma tela preta, porque o operador
age sobre ele. Entao o atraso e permanente e discreto quando esta bom, e
grita quando nao esta — sem nunca virar modal, que num pregao e dano.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.ponte import EstadoFeed, Instantaneo

ALTURA_TOPO = 28
ALTURA_RODAPE = 22

_ROTULO_ESTADO = {
    EstadoFeed.AGUARDANDO: "AGUARDANDO",
    EstadoFeed.VIVO: "AO VIVO",
    EstadoFeed.ATRASADO: "ATRASADO",
    EstadoFeed.SEM_FEED: "SEM FEED",
    EstadoFeed.ENCERRADO: "ENCERRADO",
}

_COR_ESTADO = {
    EstadoFeed.AGUARDANDO: tokens.TEXT_MUTED,
    EstadoFeed.VIVO: tokens.OK,
    EstadoFeed.ATRASADO: tokens.ALERT,
    EstadoFeed.SEM_FEED: tokens.DANGER,
    EstadoFeed.ENCERRADO: tokens.TEXT_SECONDARY,
}


def cor_do_estado(estado: EstadoFeed) -> QColor:
    return _COR_ESTADO.get(estado, tokens.TEXT_SECONDARY)


class StripTopo(PainelDenso):
    """Simbolo, estado do feed, ultimo preco, variacao e delta do dia."""

    def __init__(
        self,
        simbolo: str,
        grid: PriceGrid,
        parent: QWidget | None = None,
        paleta: tokens.Paleta = tokens.PALETA_COR,
    ) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_RAISED)
        self.simbolo = simbolo
        self.grid = grid
        self.paleta = paleta
        self.setFixedHeight(ALTURA_TOPO)

        self._estado = EstadoFeed.AGUARDANDO
        self._ultimo: int | None = None
        self._primeiro: int | None = None
        self._delta = 0
        self._volume = 0
        self._nao_atribuido = 0
        self._atraso = 0.0
        self._modo = ""

    def definir_modo(self, texto: str) -> None:
        """`REPLAY 2,0x`, `SIMULADOR`, vazio para ao vivo."""
        if texto != self._modo:
            self._modo = texto
            self.marcar_tudo_sujo()

    def aplicar(self, retrato: Instantaneo) -> None:
        # So marca sujo quando algo VISIVEL muda. O atraso e arredondado a
        # decimo de segundo de proposito: sem isso o campo mudaria a cada
        # quadro e a strip repintaria 62 vezes por segundo para sempre.
        atraso = round(retrato.atraso_s, 1)
        mudou = (
            retrato.estado is not self._estado
            or retrato.ultimo_preco != self._ultimo
            or retrato.delta_sessao != self._delta
            or retrato.volume_sessao != self._volume
            or retrato.volume_nao_atribuido != self._nao_atribuido
            or atraso != self._atraso
        )
        self._estado = retrato.estado
        self._ultimo = retrato.ultimo_preco
        self._primeiro = retrato.primeiro_preco
        self._delta = retrato.delta_sessao
        self._volume = retrato.volume_sessao
        self._nao_atribuido = retrato.volume_nao_atribuido
        self._atraso = atraso
        if mudou:
            self.marcar_tudo_sujo()

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        altura = self.height()
        x = 8

        painter.setFont(tokens.fonte_ui(12, 600))
        painter.setPen(tokens.TEXT_PRIMARY)
        x = self._campo(painter, x, altura, "FluxoPro", tokens.TEXT_PRIMARY, tokens.fonte_ui(12, 600))
        x = self._separador(painter, x, altura)
        x = self._campo(painter, x, altura, self.simbolo, tokens.TEXT_PRIMARY, tokens.fonte_ui(12, 600))
        x = self._separador(painter, x, altura)

        cor_estado = cor_do_estado(self._estado)
        rotulo = "● " + _ROTULO_ESTADO[self._estado]
        if self._estado in (EstadoFeed.ATRASADO, EstadoFeed.SEM_FEED):
            rotulo += " " + formato.formatar_duracao_s(self._atraso)
        x = self._campo(painter, x, altura, rotulo, cor_estado, tokens.fonte_ui(11))
        x = self._separador(painter, x, altura)

        if self._ultimo is not None:
            estavel, vivo = formato.formatar_preco(self.grid, self._ultimo)
            metrica = QFontMetrics(tokens.fonte_numero(15, 600))
            painter.setFont(tokens.fonte_numero(15, 600))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(x, 0, metrica.horizontalAdvance(estavel), altura),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                estavel,
            )
            x += metrica.horizontalAdvance(estavel)
            painter.setPen(tokens.TEXT_PRIMARY)
            largura_vivo = metrica.horizontalAdvance(vivo)
            painter.drawText(
                QRect(x, 0, largura_vivo, altura),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                vivo,
            )
            x += largura_vivo + 8

            if self._primeiro:
                variacao = (self._ultimo - self._primeiro) / self._primeiro
                x = self._campo(
                    painter,
                    x,
                    altura,
                    formato.formatar_percentual(variacao),
                    self.paleta.direcional(variacao),
                    tokens.fonte_numero(12),
                )
            x = self._separador(painter, x, altura)

        x = self._campo(
            painter, x, altura,
            "Δdia " + formato.formatar_sinalizado(self._delta),
            self.paleta.direcional(self._delta),
            tokens.fonte_numero(13, 600),
        )
        x = self._separador(painter, x, altura)
        x = self._campo(
            painter, x, altura,
            "Vol " + formato.formatar_inteiro(self._volume),
            tokens.TEXT_SECONDARY,
            tokens.fonte_numero(12),
        )
        if self._nao_atribuido:
            # RLP: volume real cujo agressor a B3 nao divulga. Mostrar
            # explicitamente e o que impede o Δdia de parecer o retrato
            # completo do dia quando ele nao e.
            x = self._campo(
                painter, x, altura,
                "s/lado " + formato.formatar_inteiro(self._nao_atribuido),
                tokens.NEUTRAL,
                tokens.fonte_numero(11),
            )

        if self._modo:
            painter.setFont(tokens.fonte_ui(11, 600))
            painter.setPen(tokens.ALERT)
            painter.drawText(
                QRect(0, 0, self.width() - 8, altura),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._modo,
            )

    def _campo(self, painter: QPainter, x: int, altura: int, texto: str, cor, fonte) -> int:
        painter.setFont(fonte)
        painter.setPen(cor)
        largura = QFontMetrics(fonte).horizontalAdvance(texto)
        painter.drawText(
            QRect(x, 0, largura, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )
        return x + largura + 10

    def _separador(self, painter: QPainter, x: int, altura: int) -> int:
        painter.setPen(tokens.BORDER)
        painter.drawLine(x, 6, x, altura - 6)
        return x + 10


class StripRodape(PainelDenso):
    """Contadores de sessao e saude da propria interface.

    O `p95` do painel esta aqui de proposito, ao lado dos contadores de
    mercado: e o mesmo tipo de informacao. Se a interface comecar a gastar
    12 ms por quadro, o operador tem direito de ver isso antes de concluir
    que o mercado ficou lento.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_RAISED)
        self.setFixedHeight(ALTURA_RODAPE)
        self._texto_esquerda = ""
        self._texto_direita = ""
        self._cor_esquerda = tokens.TEXT_SECONDARY

    def aplicar(self, retrato: Instantaneo, p95_ms: float, n_eventos: int) -> None:
        contadores = retrato.contadores
        esquerda = "● " + _ROTULO_ESTADO[retrato.estado]
        direita = (
            f"{formato.formatar_inteiro(contadores.trades)} neg  ·  "
            f"{formato.formatar_inteiro(contadores.snapshots + contadores.deltas)} book  ·  "
            f"{n_eventos} eventos  ·  quadro p95 {p95_ms:.1f} ms".replace(".", ",")
        )
        descartados = contadores.descartados_tape + contadores.descartados_eventos
        if descartados:
            # Perda contada e perda dita. Um painel que engole dado em
            # silencio mente sobre a propria cobertura.
            direita += f"  ·  {formato.formatar_inteiro(descartados)} descartados"
        cor = cor_do_estado(retrato.estado)
        if (esquerda, direita, cor) != (self._texto_esquerda, self._texto_direita, self._cor_esquerda):
            self._texto_esquerda = esquerda
            self._texto_direita = direita
            self._cor_esquerda = cor
            self.marcar_tudo_sujo()

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, 0, self.width(), 0)
        interno = QRect(8, 0, self.width() - 16, self.height())
        painter.setFont(tokens.fonte_ui(11))
        painter.setPen(self._cor_esquerda)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._texto_esquerda
        )
        painter.setFont(tokens.fonte_numero(11))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._texto_direita
        )
