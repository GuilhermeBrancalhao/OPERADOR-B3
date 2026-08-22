"""A janela — monta os paineis e e a UNICA dona do relogio de dados.

`design/direcao_visual.md` §6, fase 1: "uma janela, tres paineis, feed ao
vivo. Ja e utilizavel."

A responsabilidade que justifica a classe existir e uma so: **um relogio de
dados**. `PonteFluxo.ler()` esvazia o buffer, entao se cada painel chamasse
por conta propria o segundo a ler receberia tape vazio. Aqui a janela le uma
vez por quadro e distribui o MESMO retrato para todos — o que tambem garante
que DOM, tape e strips mostrem o mesmo instante, em vez de uma tela costurada
de tres momentos diferentes.

Nao ha docking nem workspace ainda: sao a fase 3, e a ordem e deliberada —
`docking sem painel bom e moldura vazia`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QCloseEvent, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from fluxopro.core.eventos import PriceGrid
from fluxopro.ui import tokens
from fluxopro.ui.base.painel_denso import INTERVALO_QUADRO_MS
from fluxopro.ui.paineis.dom import PainelDOM
from fluxopro.ui.paineis.strips import StripRodape, StripTopo, cor_do_estado
from fluxopro.ui.paineis.tape import PainelTape
from fluxopro.ui.ponte import EstadoFeed, PonteFluxo

ALTURA_FAIXA = 3
"""§3.5: "estado global merece sinal global". A faixa e da JANELA, nao do
painel — desconexao nao e problema do DOM, e de todo mundo."""


class JanelaFluxo(QMainWindow):
    def __init__(
        self,
        ponte: PonteFluxo,
        simbolo: str,
        grid: PriceGrid,
        modo: str = "",
        paleta: tokens.Paleta = tokens.PALETA_COR,
        densidade: tokens.Densidade = tokens.PADRAO,
        ao_fechar=None,
    ) -> None:
        super().__init__()
        self.ponte = ponte
        self.paleta = paleta
        self._ao_fechar = ao_fechar
        self._n_eventos = 0
        self._estado_faixa: EstadoFeed | None = None

        self.setWindowTitle(f"FluxoPro — {simbolo}")
        self.resize(1280, 800)
        self._pintar_fundo()

        self.faixa = QFrame()
        self.faixa.setFixedHeight(ALTURA_FAIXA)
        self.faixa.setAutoFillBackground(True)

        self.topo = StripTopo(simbolo, grid, paleta=paleta)
        self.topo.definir_modo(modo)
        self.dom = PainelDOM(grid, paleta=paleta, densidade=densidade)
        self.tape = PainelTape(grid, paleta=paleta, densidade=densidade)
        self.rodape = StripRodape()

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(self.dom)
        divisor.addWidget(self.tape)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        divisor.setHandleWidth(1)

        corpo = QWidget()
        linha = QHBoxLayout(corpo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        linha.addWidget(divisor)

        central = QWidget()
        coluna = QVBoxLayout(central)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self.faixa)
        coluna.addWidget(self.topo)
        coluna.addWidget(corpo, 1)
        coluna.addWidget(self.rodape)
        self.setCentralWidget(central)

        self._atualizar_faixa(EstadoFeed.AGUARDANDO)
        self.dom.setFocus()

        # UM relogio de dados. Os paineis tem os seus proprios relogios de
        # DESENHO (`PainelDenso`), e sao coisas diferentes de proposito: o de
        # dados decide o que a tela sabe, o de desenho decide quanto custa
        # mostrar. Juntar os dois traria de volta o repaint por tick.
        self._relogio = QTimer(self)
        self._relogio.setInterval(INTERVALO_QUADRO_MS)
        self._relogio.setTimerType(Qt.TimerType.PreciseTimer)
        self._relogio.timeout.connect(self._tick)
        self._relogio.start()

    def _pintar_fundo(self) -> None:
        paleta_qt = self.palette()
        paleta_qt.setColor(QPalette.ColorRole.Window, tokens.BG_BASE)
        paleta_qt.setColor(QPalette.ColorRole.Base, tokens.BG_SURFACE)
        paleta_qt.setColor(QPalette.ColorRole.WindowText, tokens.TEXT_PRIMARY)
        self.setPalette(paleta_qt)
        self.setAutoFillBackground(True)

    def _tick(self) -> None:
        retrato = self.ponte.ler()
        self._n_eventos += len(self.ponte.drenar_eventos())

        self.topo.aplicar(retrato)
        self.dom.aplicar(retrato.livro, retrato.ultimo_preco)
        self.tape.aplicar(retrato.novos_trades)
        # O p95 relatado e o do DOM: e o painel mais denso da fase 1, entao e
        # o que primeiro acusaria uma regressao de desenho.
        self.rodape.aplicar(retrato, self.dom.p95_ms(), self._n_eventos)
        self._atualizar_faixa(retrato.estado)

    def _atualizar_faixa(self, estado: EstadoFeed) -> None:
        if estado is self._estado_faixa:
            return
        self._estado_faixa = estado
        if estado in (EstadoFeed.VIVO, EstadoFeed.AGUARDANDO):
            cor = QColor(tokens.BG_BASE)  # discreta: sem noticia e boa noticia
        else:
            cor = cor_do_estado(estado)
        paleta_qt = self.faixa.palette()
        paleta_qt.setColor(QPalette.ColorRole.Window, cor)
        self.faixa.setPalette(paleta_qt)

    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802
        self._relogio.stop()
        self.dom.parar_relogio()
        self.tape.parar_relogio()
        self.topo.parar_relogio()
        self.rodape.parar_relogio()
        # Solta as assinaturas ANTES de deixar a janela morrer: sem isso o
        # barramento continuaria entregando o pregao inteiro a callbacks de
        # widgets destruidos, que no Qt e falha de segmentacao, nao excecao.
        self.ponte.desligar()
        if self._ao_fechar is not None:
            self._ao_fechar()
        super().closeEvent(evento)
