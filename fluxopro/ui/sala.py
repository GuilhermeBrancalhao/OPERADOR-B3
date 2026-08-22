"""Sala de Controle — §4.2, a tela inicial que responde três perguntas.

> Sem splash decorativo. Ao abrir: **Sala de Controle**, uma tela só, que
> responde três perguntas antes de qualquer gráfico: **Feed** (conectado?
> latência? gap de sequência?), **Instrumentos** (último, variação, volume,
> delta, hora do último tick) e **Workspace** (os 4 cartões, o último usado em
> destaque; `Enter` abre).
>
> Se o feed já está vivo e há workspace anterior, a Sala de Controle se
> auto-dispensa em 1,5 s (com barra de progresso cancelável por qualquer
> tecla). Ninguém quer um portal entre ele e o pregão.

## As três decisões que essa linha esconde

**1. A auto-dispensa é condicional, e a condição é dita.** Ela só arma quando
o feed está vivo *e* há workspace anterior. Fora disso a sala fica — e o
rodapé escreve por quê. Uma sala que sumisse sozinha com o feed morto poria o
operador diante de uma grade vazia sem ele ter lido que a fonte não respondeu.

**2. A barra de 1,5 s é proporção de um todo conhecido**, então é a **barra
particionada cheia** do vocabulário de `hud.py` (decorrido | restante) — não
uma terceira forma. E ela leva o número de segundos escrito dentro: a lei
medida deste projeto é que o canal preserva o veredito e apaga a ressalva, e
numa barra de contagem regressiva a escala *é* a informação.

**3. Cancelar é qualquer tecla, e o cancelamento é permanente na sessão.**
Rearmar depois de o operador ter pedido para parar seria a sala decidindo que
ele mudou de ideia.

## O que ela NÃO faz

Não abre fonte de dados, não escolhe símbolo, não valida credencial. Ela lê um
`EstadoSala` que já veio pronto e emite o nome do workspace escolhido. Uma
tela inicial que montasse a sessão passaria a ser um segundo caminho de
montagem ao lado de `app/montagem.py`, e dois caminhos de montagem é como um
produto começa a ter dois comportamentos.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.paineis.strips import rotulo_do_estado
from fluxopro.ui.ponte import EstadoFeed, Instantaneo
from fluxopro.ui.workspace import WORKSPACES_DE_FABRICA, Workspace

MS_AUTO_DISPENSA = 1500
"""§4.2, literal: 1,5 s."""

INTERVALO_TICK_MS = 50
MARGEM = 24
ALTURA_TITULO = 40
ALTURA_SECAO = 22
ALTURA_LINHA = 22
ALTURA_CARTAO = 92
VAO_CARTAO = 12
ALTURA_BARRA = 18
ALTURA_RODAPE = 28

MOTIVO_FEED = "o feed ainda não está vivo"
MOTIVO_SEM_ANTERIOR = "não há workspace anterior"
ROTULO_ABRIR = "ENTER ABRE  ·  ←/→ ESCOLHE  ·  1..4 VAI DIRETO  ·  QUALQUER TECLA CANCELA A CONTAGEM"


@dataclass(frozen=True, slots=True)
class Instrumento:
    """Uma linha da seção 2. Já vem calculada — a sala não deriva mercado."""

    simbolo: str
    ultimo: int | None
    primeiro: int | None
    volume: int
    delta: int
    ultimo_tick_ns: int


@dataclass(frozen=True, slots=True)
class EstadoSala:
    """As três respostas, num objeto só e imutável.

    Um objeto e não cinco parâmetros pelo mesmo motivo de `Instantaneo` e de
    `LeituraMetodo`: as respostas se explicam umas às outras. "Feed vivo" ao
    lado de um último tick de vinte minutos atrás é uma tela que se contradiz.
    """

    estado: EstadoFeed = EstadoFeed.AGUARDANDO
    latencia_p50_ms: float = 0.0
    latencia_p99_ms: float = 0.0
    gaps_mbo: int = 0
    instrumentos: tuple[Instrumento, ...] = ()
    workspaces: tuple[Workspace, ...] = WORKSPACES_DE_FABRICA
    anterior: str = ""
    """Nome do último workspace usado. Vazio = primeira vez."""

    @property
    def feed_vivo(self) -> bool:
        return self.estado is EstadoFeed.VIVO

    @property
    def pode_auto_dispensar(self) -> tuple[bool, str]:
        """`(pode, motivo)` — e o motivo vai para a tela, não para um log."""
        if not self.feed_vivo:
            return False, MOTIVO_FEED
        if not self.anterior:
            return False, MOTIVO_SEM_ANTERIOR
        return True, ""


def instrumento_de(retrato: Instantaneo, simbolo: str) -> Instrumento:
    """`Instantaneo` -> `Instrumento`. Puro, e o único adaptador da sala."""
    return Instrumento(
        simbolo=simbolo,
        ultimo=retrato.ultimo_preco,
        primeiro=retrato.primeiro_preco,
        volume=retrato.volume_sessao,
        delta=retrato.delta_sessao,
        ultimo_tick_ns=retrato.timestamp_ns if hasattr(retrato, "timestamp_ns") else 0,
    )


def particionar_contagem(largura: int, decorrido_ms: int, total_ms: int) -> int:
    """Pixels da parte DECORRIDA da barra. Uma conta, três usos (lei nº 6).

    Nunca devolve a largura inteira antes de a contagem acabar: uma barra que
    parecesse cheia com 80 ms restando convidaria o operador a acreditar que
    perdeu a janela de cancelamento que ele ainda tem.
    """
    if total_ms <= 0 or largura <= 0:
        return 0
    if decorrido_ms >= total_ms:
        return largura
    return min(largura - 1, max(0, (decorrido_ms * largura) // total_ms))


class SalaDeControle(PainelDenso):
    """A tela inicial. Emite o nome do workspace e some."""

    escolheu = Signal(str)
    """Nome do workspace escolhido — por `Enter`, por dígito ou por contagem."""

    def __init__(
        self,
        estado: EstadoSala,
        grid: PriceGrid,
        parent: QWidget | None = None,
        ms_auto_dispensa: int = MS_AUTO_DISPENSA,
    ) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_BASE)
        self.grid = grid
        self.ms_auto_dispensa = ms_auto_dispensa
        self._estado = estado
        self._selecionado = self._indice_inicial(estado)
        self._decorrido_ms = 0
        self._cancelada = False
        self._fm_rotulo = QFontMetrics(tokens.fonte_rotulo())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(760, 520)

        self._contagem = QTimer(self)
        self._contagem.setInterval(INTERVALO_TICK_MS)
        self._contagem.timeout.connect(self._passo)

    @staticmethod
    def _indice_inicial(estado: EstadoSala) -> int:
        for indice, w in enumerate(estado.workspaces):
            if w.nome == estado.anterior:
                return indice
        return 0

    # ------------------------------------------------------------- contagem
    @property
    def contando(self) -> bool:
        return self._contagem.isActive()

    @property
    def cancelada(self) -> bool:
        return self._cancelada

    @property
    def decorrido_ms(self) -> int:
        return self._decorrido_ms

    def armar(self) -> bool:
        """Liga a contagem se as duas condições de §4.2 valem. `False` senão."""
        pode, _ = self._estado.pode_auto_dispensar
        if not pode or self._cancelada:
            return False
        self._decorrido_ms = 0
        self._contagem.start()
        self.marcar_tudo_sujo()
        return True

    def cancelar(self) -> None:
        """Permanente na sessão: não há como rearmar sem construir outra sala."""
        if not self._cancelada:
            self._cancelada = True
            self._contagem.stop()
            self.marcar_tudo_sujo()

    def _passo(self) -> None:
        self._decorrido_ms += INTERVALO_TICK_MS
        self.marcar_tudo_sujo()
        if self._decorrido_ms >= self.ms_auto_dispensa:
            self._contagem.stop()
            self.confirmar()

    def confirmar(self) -> None:
        self._contagem.stop()
        self.escolheu.emit(self.selecionado.nome)

    @property
    def selecionado(self) -> Workspace:
        return self._estado.workspaces[self._selecionado]

    def selecionar(self, indice: int) -> None:
        n = len(self._estado.workspaces)
        novo = indice % n if n else 0
        if novo != self._selecionado:
            self._selecionado = novo
            self.marcar_tudo_sujo()

    def aplicar(self, estado: EstadoSala) -> None:
        if estado != self._estado:
            self._estado = estado
            self.marcar_tudo_sujo()

    # -------------------------------------------------------------- teclado
    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        tecla = evento.key()
        # QUALQUER tecla cancela a contagem — inclusive as que navegam. É o
        # que §4.2 pede, e é o comportamento seguro: o operador que encostou
        # numa seta demonstrou que quer decidir, não ser decidido.
        self.cancelar()
        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.confirmar()
            return
        if tecla == Qt.Key.Key_Left:
            self.selecionar(self._selecionado - 1)
            return
        if tecla == Qt.Key.Key_Right:
            self.selecionar(self._selecionado + 1)
            return
        if Qt.Key.Key_1 <= tecla <= Qt.Key.Key_9:
            digito = tecla - Qt.Key.Key_0
            for indice, w in enumerate(self._estado.workspaces):
                if w.atalho == digito:
                    self.selecionar(indice)
                    self.confirmar()
                    return
            return
        super().keyPressEvent(evento)

    # ------------------------------------------------------------- geometria
    def rect_titulo(self) -> QRect:
        return QRect(MARGEM, MARGEM, self.width() - 2 * MARGEM, ALTURA_TITULO)

    def rect_secao(self, indice: int) -> QRect:
        """As três perguntas de §4.2, empilhadas, na ordem em que ele as faz."""
        y = MARGEM + ALTURA_TITULO
        alturas = (
            ALTURA_SECAO + 2 * ALTURA_LINHA,
            ALTURA_SECAO + max(1, len(self._estado.instrumentos)) * ALTURA_LINHA,
            ALTURA_SECAO + ALTURA_CARTAO,
        )
        for i in range(indice):
            y += alturas[i] + MARGEM
        return QRect(MARGEM, y, self.width() - 2 * MARGEM, alturas[indice])

    def rect_cartao(self, indice: int) -> QRect:
        secao = self.rect_secao(2)
        n = max(1, len(self._estado.workspaces))
        util = secao.width() - (n - 1) * VAO_CARTAO
        largura = util // n
        return QRect(
            secao.left() + indice * (largura + VAO_CARTAO),
            secao.top() + ALTURA_SECAO,
            largura,
            ALTURA_CARTAO,
        )

    def rect_barra(self) -> QRect:
        return QRect(
            MARGEM,
            self.height() - ALTURA_RODAPE - ALTURA_BARRA - MARGEM,
            self.width() - 2 * MARGEM,
            ALTURA_BARRA,
        )

    def rect_decorrido(self) -> QRect:
        barra = self.rect_barra()
        return QRect(
            barra.left(),
            barra.top(),
            particionar_contagem(barra.width(), self._decorrido_ms, self.ms_auto_dispensa),
            barra.height(),
        )

    def rect_rodape(self) -> QRect:
        return QRect(
            MARGEM, self.height() - ALTURA_RODAPE - MARGEM // 2,
            self.width() - 2 * MARGEM, ALTURA_RODAPE,
        )

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self.marcar_tudo_sujo()

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setFont(tokens.fonte_ui(24, 600))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            self.rect_titulo(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "SALA DE CONTROLE",
        )
        self._desenhar_feed(painter)
        self._desenhar_instrumentos(painter)
        self._desenhar_workspaces(painter)
        self._desenhar_contagem(painter)

    def _titulo_secao(self, painter: QPainter, rect: QRect, texto: str) -> None:
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width(), ALTURA_SECAO),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )
        painter.setPen(tokens.BORDER)
        y = rect.top() + ALTURA_SECAO - 1
        painter.drawLine(rect.left(), y, rect.right(), y)

    def _desenhar_feed(self, painter: QPainter) -> None:
        rect = self.rect_secao(0)
        self._titulo_secao(painter, rect, "1 · FEED")
        # O MESMO rótulo das strips, pela mesma função: se a sala dissesse
        # `AO VIVO` num replay enquanto a strip diz `REPLAY`, a contradição
        # que este ciclo matou teria voltado por outra porta.
        rotulo, cor = rotulo_do_estado(self._estado.estado)
        painter.setFont(tokens.fonte_ui(16, 600))
        painter.setPen(cor)
        linha = QRect(rect.left(), rect.top() + ALTURA_SECAO, rect.width(), ALTURA_LINHA)
        painter.drawText(linha, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo)
        painter.setFont(tokens.fonte_numero(13))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            linha.translated(0, ALTURA_LINHA),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "latência p50 %s  ·  p99 %s  ·  %s gap(s) de sequência MBO"
            % (
                formato.formatar_latencia_ms(self._estado.latencia_p50_ms),
                formato.formatar_latencia_ms(self._estado.latencia_p99_ms),
                formato.formatar_inteiro(self._estado.gaps_mbo),
            ),
        )

    def _desenhar_instrumentos(self, painter: QPainter) -> None:
        rect = self.rect_secao(1)
        self._titulo_secao(painter, rect, "2 · INSTRUMENTOS")
        if not self._estado.instrumentos:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(rect.left(), rect.top() + ALTURA_SECAO, rect.width(), ALTURA_LINHA),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "NENHUM INSTRUMENTO COM DADO AINDA",
            )
            return
        painter.setFont(tokens.fonte_numero(13))
        for indice, item in enumerate(self._estado.instrumentos):
            linha = QRect(
                rect.left(), rect.top() + ALTURA_SECAO + indice * ALTURA_LINHA,
                rect.width(), ALTURA_LINHA,
            )
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                linha, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._texto_instrumento(item),
            )

    def _texto_instrumento(self, item: Instrumento) -> str:
        preco = "—" if item.ultimo is None else formato.preco_completo(self.grid, item.ultimo)
        variacao = "—"
        if item.ultimo is not None and item.primeiro:
            variacao = formato.formatar_percentual(
                (item.ultimo - item.primeiro) / item.primeiro
            )
        return "%-9s %s  %s  ·  vol %s  ·  Δdia %s  ·  último tick %s" % (
            item.simbolo,
            preco,
            variacao,
            formato.formatar_inteiro(item.volume),
            formato.formatar_sinalizado(item.delta),
            formato.formatar_hora_ns(item.ultimo_tick_ns) if item.ultimo_tick_ns else "—",
        )

    def _desenhar_workspaces(self, painter: QPainter) -> None:
        rect = self.rect_secao(2)
        self._titulo_secao(painter, rect, "3 · WORKSPACE")
        for indice, w in enumerate(self._estado.workspaces):
            cartao = self.rect_cartao(indice)
            escolhido = indice == self._selecionado
            painter.fillRect(cartao, tokens.BG_RAISED if escolhido else tokens.BG_SURFACE)
            painter.setPen(tokens.BORDER_STRONG if escolhido else tokens.BORDER)
            painter.drawRect(cartao.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_ui(15, 600))
            painter.setPen(tokens.TEXT_PRIMARY if escolhido else tokens.TEXT_SECONDARY)
            painter.drawText(
                cartao.adjusted(10, 6, -10, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                w.nome,
            )
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                cartao.adjusted(10, 28, -10, -26),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                | int(Qt.TextFlag.TextWordWrap),
                w.descricao,
            )
            self._chip(
                painter,
                QRect(cartao.left() + 10, cartao.bottom() - 22, 66, 15),
                "CTRL+%d" % w.atalho,
                tokens.NEUTRAL,
            )
            if w.nome == self._estado.anterior:
                self._chip(
                    painter,
                    QRect(cartao.left() + 82, cartao.bottom() - 22, 56, 15),
                    "ÚLTIMO",
                    tokens.OK,
                )

    def _chip(self, painter: QPainter, rect: QRect, texto: str, fundo: QColor) -> None:
        painter.fillRect(rect, fundo)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.BG_BASE)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)

    def _desenhar_contagem(self, painter: QPainter) -> None:
        barra = self.rect_barra()
        pode, motivo = self._estado.pode_auto_dispensar
        painter.setFont(tokens.fonte_rotulo())
        if self._cancelada or not pode:
            painter.setPen(tokens.TEXT_MUTED)
            razao = "cancelada por tecla" if self._cancelada else motivo
            painter.drawText(
                barra,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "SEM AUTO-DISPENSA · %s" % razao.upper(),
            )
        else:
            painter.fillRect(barra, tokens.BG_SURFACE)
            painter.fillRect(self.rect_decorrido(), tokens.ALERT)
            restante = max(0, self.ms_auto_dispensa - self._decorrido_ms) / 1000.0
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                barra.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "ABRE %s EM %s" % (self.selecionado.nome.upper(), formato.formatar_duracao_s(restante)),
            )
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            self.rect_rodape(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ROTULO_ABRIR,
        )
