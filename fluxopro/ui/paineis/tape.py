"""Tape — o fluxo de negocios, linha a linha. §4.3 e §6 fase 1.

Segundo painel de proposito: e o que valida o caminho de ALTO VOLUME de
eventos. O DOM prova a escada; o tape prova que 5.000 negocios por segundo
entram sem que a interface tente desenhar 5.000 linhas.

Duas coisas fazem isso funcionar:

* **Rolagem em vez de redesenho.** Chegaram 3 negocios? O corpo do painel
  rola 3 linhas dentro do proprio backing e desenha 3 — nao 40. E o mesmo
  mecanismo do footprint, na sua forma mais simples.

* **Anel com teto.** O tape guarda um numero fixo de linhas. Ele nao e um
  historico: e uma janela. Historico e o que `gravacao/` faz, com fsync e
  hash, e um `deque` sem teto na interface seria a nona casa do defeito de
  crescimento que este projeto ja encontrou em oito arquivos.

O filtro por lote (`>= 50` no wireframe) nao e enfeite: a leitura do tape e
sobre encontrar o negocio GRANDE no meio do ruido de 5 contratos, e a tela
mais rapida do mundo nao ajuda se o que importa passou entre dois quadros.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.ponte import ItemTape

CAPACIDADE_ANEL = 512
"""Linhas retidas. Bem acima do que cabe na tela (~40) para o painel
sobreviver a um redimensionamento sem ficar em branco, e bem abaixo de
qualquer coisa que se pareca com historico."""

SETA_COMPRA = "▲"   # ▲
SETA_VENDA = "▼"    # ▼
SEM_LADO = "·"      # · — RLP: negocio real, agressor nao divulgado


class PainelTape(PainelDenso):
    """Lista de negocios, mais recente no topo."""

    def __init__(
        self,
        grid: PriceGrid,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        qty_minima: int = 0,
        qty_destaque: int = 100,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.densidade = densidade
        self.paleta = paleta
        self.qty_minima = qty_minima
        self.qty_destaque = qty_destaque

        self._linhas: deque[ItemTape] = deque(maxlen=CAPACIDADE_ANEL)
        self._filtrados = 0
        self._n_visiveis = 1
        self._fm = QFontMetrics(tokens.fonte_numero(densidade.fonte_grade))

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 120)

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    @property
    def _area_corpo(self) -> QRect:
        return QRect(0, self._y_corpo, self.width(), max(0, self.height() - self._y_corpo))

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        util = max(0, altura - self._y_corpo)
        self._n_visiveis = max(1, util // self.densidade.altura_linha)

    # ---------------------------------------------------------------- dados
    def aplicar(self, novos: tuple[ItemTape, ...]) -> None:
        """Absorve os negocios do quadro. Chamado pela janela."""
        if not novos:
            return
        aceitos = [t for t in novos if t.qty >= self.qty_minima]
        self._filtrados += len(novos) - len(aceitos)
        if not aceitos:
            return

        # O anel guarda do mais NOVO para o mais velho, entao a linha 0 e
        # sempre o topo da tela e nao ha aritmetica de indice no desenho.
        for item in aceitos:
            self._linhas.appendleft(item)

        n = len(aceitos)
        if n >= self._n_visiveis:
            # Chegou mais do que cabe: rolar seria mover pixels que vao ser
            # todos sobrescritos.
            self.marcar_tudo_sujo()
            return
        altura = self.densidade.altura_linha
        self.rolar(0, n * altura, self._area_corpo)

    def definir_filtro(self, qty_minima: int) -> None:
        if qty_minima == self.qty_minima:
            return
        self.qty_minima = max(0, qty_minima)
        # O filtro nao reescreve o passado: as linhas ja aceitas continuam
        # la. Reprocessar o anel daria uma tela que muda sozinha ao mexer no
        # filtro, escondendo negocios que o operador VIU acontecer.
        self.marcar_tudo_sujo()

    # --------------------------------------------------------------- teclado
    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        tecla = evento.key()
        if tecla in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.definir_filtro(_proximo_degrau(self.qty_minima, +1))
            evento.accept()
            return
        if tecla in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.definir_filtro(_proximo_degrau(self.qty_minima, -1))
            evento.accept()
            return
        super().keyPressEvent(evento)

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            self._desenhar_cabecalho(painter)
        if not self._linhas:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "SEM NEGOCIOS")
            return

        altura = self.densidade.altura_linha
        primeira = max(0, (regiao.top() - self._y_corpo) // altura)
        ultima = min(
            min(self._n_visiveis, len(self._linhas)) - 1,
            (regiao.bottom() - self._y_corpo) // altura,
        )
        for indice in range(primeira, ultima + 1):
            self._desenhar_linha(painter, indice, self._linhas[indice])

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        rect = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(4, 0, -4, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Tape"
        )
        if self.qty_minima > 0:
            painter.setPen(tokens.ALERT)
            painter.drawText(
                interno,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"≥ {self.qty_minima}",
            )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self._y_corpo - 1, self.width(), self._y_corpo - 1)

    def _desenhar_linha(self, painter: QPainter, indice: int, item: ItemTape) -> None:
        y = self._y_corpo + indice * self.densidade.altura_linha
        altura = self.densidade.altura_linha
        largura = self.width()
        cor = self.paleta.direcional(item.agressor)

        grande = item.qty >= self.qty_destaque
        if grande:
            # Lote grande ganha fundo, nao so peso: e o evento que o painel
            # existe para nao deixar passar, e peso de fonte sozinho some na
            # rolagem rapida.
            rampa = tokens.RAMPA_NEUTRA
            if self.paleta.tem_cor:
                rampa = tokens.RAMPA_COMPRA if item.agressor > 0 else (
                    tokens.RAMPA_VENDA if item.agressor < 0 else tokens.RAMPA_NEUTRA
                )
            painter.fillRect(QRect(0, y, largura, altura), rampa[2])

        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(4, y, largura, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_hora_ns(item.timestamp_ns),
        )

        largura_seta = self._fm.horizontalAdvance(SETA_COMPRA) + 6
        largura_qty = self._fm.horizontalAdvance("000.000") + 8
        x_seta = largura - largura_seta - 4
        x_qty = x_seta - largura_qty

        painter.setPen(cor)
        painter.drawText(
            QRect(x_qty, y, largura_qty, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_inteiro(item.qty),
        )
        # A seta e o portador REDUNDANTE da direcao: e o que mantem a coluna
        # legivel no modo sem cor e num print em escala de cinza.
        painter.drawText(
            QRect(x_seta, y, largura_seta, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            SETA_COMPRA if item.agressor > 0 else (SETA_VENDA if item.agressor < 0 else SEM_LADO),
        )

        estavel, vivo = formato.formatar_preco(self.grid, item.price)
        largura_vivo = self._fm.horizontalAdvance(vivo)
        largura_estavel = self._fm.horizontalAdvance(estavel)
        x_preco = x_qty - largura_vivo - largura_estavel - 10
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(x_preco, y, largura_estavel, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            estavel,
        )
        painter.setPen(tokens.TEXT_PRIMARY if not grande else cor)
        painter.drawText(
            QRect(x_preco + largura_estavel, y, largura_vivo + 2, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            vivo,
        )


_DEGRAUS_FILTRO = (0, 5, 10, 25, 50, 100, 250, 500, 1000)
"""Degraus fixos em vez de incremento livre. Filtro de tape e uma decisao
grossa ("quero ver so lote institucional"), nao um dial fino, e degraus
tornam a tecla previsivel."""


def _proximo_degrau(atual: int, direcao: int) -> int:
    if atual in _DEGRAUS_FILTRO:
        indice = _DEGRAUS_FILTRO.index(atual) + direcao
    else:
        indice = 0
        for i, valor in enumerate(_DEGRAUS_FILTRO):
            if valor > atual:
                indice = i - 1 + direcao if direcao < 0 else i
                break
        else:
            indice = len(_DEGRAUS_FILTRO) - 1
    return _DEGRAUS_FILTRO[max(0, min(len(_DEGRAUS_FILTRO) - 1, indice))]
