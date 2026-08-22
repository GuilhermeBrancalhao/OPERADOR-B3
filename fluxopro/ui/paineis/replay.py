"""Replay — a tarja que impede a confusao, e o transporte que a controla.

`design/direcao_visual.md` §6 fase 5, item 14, e §3.5, linha "Replay ativo":

> Faixa `--alert` de 3px no topo + `▶ REPLAY 06/12 10:35 · 2,0×` fixo.
> Copiamos a tarja amarela do Profit (`08_replay_a.png`) — essa ele acerta.
> **Impossivel confundir replay com ao vivo.**

Duas frases dessa linha sao contrato, e as duas moldaram este modulo.

## "da JANELA inteira", e nao do painel

§3.5 escreve a mesma regra duas vezes, no estado Desconectado e aqui:
*"Faixa de 3px no topo da janela **inteira** (nao do painel)"*, com a
justificativa *"estado global merece sinal global"*. Um painel com moldura
amarela diz "este painel esta em replay"; o operador tem oito paineis e olha
um de cada vez. O que ele precisa saber e que **a mesa toda** esta em replay.

Por isso `TarjaReplay` nao e um painel do layout: e um sobreposto da janela,
instalado por `instalar_em(janela)`, que se mantem no topo, com a largura da
janela, acima de tudo, por filtro de evento. Ela nao entra em nenhum
`QDockWidget`, nao pode ser fechada, e nao depende de nenhum workspace estar
com o painel de replay aberto.

## "Impossivel confundir" — e a lei do canal

Esta e a peca em que a lei do canal deste projeto deixa de ser sobre estetica
e vira sobre dano. `scripts/transmissao.py` degrada um retrato (0,72 + JPEG
q40) e `scripts/retencao.py` mede quanto de cada traco sobrevive; a lei
medida e:

> **o canal preserva o veredito e apaga a ressalva.**

A tarja de replay e o caso extremo: o "veredito" e a tela inteira de numeros
de pregao, e a "ressalva" e a informacao de que nada daquilo esta acontecendo
agora. Se a ressalva morre no canal, o espectador de uma transmissao ve um
pregao ao vivo que nao existe. Nenhum outro elemento deste produto tem esse
modo de falha.

O que isso obrigou, ponto por ponto:

1. **Bloco preenchido, nao linha nem texto solto.** `PainelMatriz._chip`
   mediu que compressao com perdas ataca borda fina de alto contraste e poupa
   area chapada. A tarja e `--alert` chapado com texto `--bg-base` por cima:
   12,34:1, o par de maior contraste da tela, na forma que menos sofre.
2. **A faixa de 3px de §3.5 continua la, mas nao sozinha.** Ela e a assinatura
   visual que o `08_replay_a.png` acerta; o corpo chapado de 21px embaixo dela
   e o que sobrevive a reescala. Manter so os 3px seria manter exatamente a
   forma que o canal come primeiro.
3. **A tarja NAO trunca.** `_maior_que_cabe` encolhe a fonte ate caber, com
   piso de 10px. Ressalva truncada e o pior modo de falha que existe: a frase
   que sobra continua parecendo completa e o leitor nunca sabe que faltou
   pedaco (a mesma regra de `scripts/retrato_hud.py`).
4. **Redundancia de portador.** `▶`/`⏸` (glifo), `REPLAY` (palavra), data e
   hora do PASSADO (dado), e a velocidade. Perder um deles nao apaga a
   ressalva. Em escala de cinza a tarja continua sendo o bloco mais claro da
   janela, porque `--alert` tem a maior luminancia de todos os tokens.

Esta tarja e o objeto que `scripts/retrato_hud.py` previu: *"Se um dia virar
peca de produto (a faixa de REPLAY de §3.5 e o mesmo objeto), ela migra para
`ui/paineis/` com relogio e regiao suja."* Migrou.

## Velocidade e busca — duas grandezas, duas formas

A velocidade varia 64x entre a ponta lenta e a rapida. §3 deste projeto ja
pagou quatro vezes pela forma errada disso: **grandeza de variacao enorme
desenhada como comprimento** — um slider de velocidade seria a quinta. Entao
velocidade e um **conjunto declarado de degraus com o numero escrito em cada
um** (`VELOCIDADES`), e o degrau em uso e um chip preenchido. Nao ha
comprimento a comparar, e o valor esta escrito.

A posicao no pregao e o contrario: e **proporcao**, tem eixo absoluto de 0 a
100%, e por isso pode ser uma trilha de largura fixa — a mesma forma da barra
particionada do HUD. Sem escala, nao ha escala para o canal apagar.

## Estruturas

Nada aqui cresce. `TarjaReplay` e `ControlesReplay` guardam **um**
`EstadoReplay` (o corrente, nunca um historico) e nenhuma colecao indexada
por tempo. `VELOCIDADES` e uma constante de modulo com sete itens.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

VELOCIDADES: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
"""Degraus declarados de velocidade. Sete, em potencias de 2 a partir de 1/4.

Nao e um slider de proposito — ver o topo do modulo. E o alcance nao e
arbitrario: `AdaptadorLeitorGravacao` dorme entre eventos na proporcao
informada, entao 0,25x e 16x sao os extremos em que ainda ha o que ver
(abaixo o operador espera, acima o quadro de 16 ms nao acompanha)."""

GLIFO_TOCANDO = "▶"
GLIFO_PAUSADO = "⏸"

ALTURA_FAIXA = 3
"""Os 3px literais de §3.5 — a assinatura que a barra de referencia acerta."""

ALTURA_TARJA = 24
"""3px de faixa + 21px de corpo chapado. Total igual ao cabecalho de painel
(§3.4), para a tarja nao roubar altura util de uma janela de operacao."""

ALTURA_LINHA_CONTROLE = 24
ALTURA_TRILHA = 10
MARGEM = 8
ESPACO_CHIP = 4
LARGURA_ALCA = 3
PISO_FONTE = 10


def texto_velocidade(velocidade: float) -> str:
    """`2,0×` / `0,25×`. Virgula decimal, `×` tipografico e nao a letra x."""
    if velocidade >= 1.0:
        corpo = f"{velocidade:.1f}".replace(".", ",")
    else:
        corpo = f"{velocidade:.2f}".replace(".", ",")
    return corpo + "×"


def _hora_curta(timestamp_ns: int) -> str:
    """`10:35:12` — segundo, sem milissegundo.

    O milissegundo importa no tape (dois negocios no mesmo segundo sao a
    diferenca entre uma ordem fatiada e duas decisoes) e nao importa aqui: a
    tarja diz QUANDO foi o pregao, nao ordena eventos. Tres digitos a menos
    e tres digitos que nao competem com a palavra REPLAY pelo espaco."""
    return formato.formatar_hora_ns(timestamp_ns)[:8]


def _maior_que_cabe(texto: str, largura: int, base: int = 13) -> QFont:
    """A ressalva NAO pode truncar.

    Truncar e o pior modo de falha desta tarja: a frase que sobra continua
    parecendo completa e o leitor nunca sabe que faltou pedaco. Entao a
    fonte encolhe ate caber, com piso em `PISO_FONTE` porque abaixo disso
    nao adianta caber. Mesma funcao e mesmo motivo de `scripts/retrato_hud.py`.
    """
    for tamanho in range(base, PISO_FONTE - 1, -1):
        fonte = tokens.fonte_ui(tamanho, 700)
        if QFontMetrics(fonte).horizontalAdvance(texto) <= largura:
            return fonte
    return tokens.fonte_ui(PISO_FONTE, 700)


@dataclass(frozen=True, slots=True)
class EstadoReplay:
    """O que a janela sabe sobre o replay, num objeto so.

    `frozen` porque os dois widgets leem o MESMO objeto: se a tarja e os
    controles pudessem ver estados diferentes, existiria um quadro em que a
    tarja diz `2,0×` e o transporte mostra `4,0×` — e a tarja e justamente a
    peca que nao pode ser desmentida por outra parte da tela.
    """

    ativo: bool = False
    symbol: str = ""
    data: date | None = None
    inicio_ns: int = 0
    fim_ns: int = 0
    posicao_ns: int = 0
    velocidade: float = 1.0
    pausado: bool = False

    @property
    def duracao_ns(self) -> int:
        return max(0, self.fim_ns - self.inicio_ns)

    @property
    def progresso(self) -> float:
        """0..1. Duracao zero devolve 0, e nao levanta: uma gravacao de um
        evento so e degenerada, nao invalida, e derrubar o painel por causa
        dela seria trocar uma barra vazia por uma tela preta."""
        if self.duracao_ns <= 0:
            return 0.0
        bruto = (self.posicao_ns - self.inicio_ns) / self.duracao_ns
        return min(1.0, max(0.0, bruto))

    def em(self, fracao: float) -> int:
        """Timestamp da fracao — o par de `progresso`, para a busca."""
        fracao = min(1.0, max(0.0, fracao))
        return self.inicio_ns + int(round(self.duracao_ns * fracao))

    @property
    def texto_data(self) -> str:
        return self.data.strftime("%d/%m") if self.data is not None else "—"

    @property
    def texto_tarja(self) -> str:
        """`▶ REPLAY 06/12 10:35:12 · 2,0×` — o texto literal de §3.5.

        Quatro portadores independentes da mesma ressalva: o glifo, a
        palavra, a data (do passado) e a velocidade. O canal teria de comer
        os quatro para o espectador confundir isto com pregao ao vivo."""
        glifo = GLIFO_PAUSADO if self.pausado else GLIFO_TOCANDO
        partes = [glifo, "REPLAY", self.texto_data, _hora_curta(self.posicao_ns)]
        cabeca = " ".join(partes)
        cauda = texto_velocidade(self.velocidade)
        if self.pausado:
            cauda += " · PAUSADO"
        if self.symbol:
            cauda = self.symbol + " · " + cauda
        return cabeca + "  ·  " + cauda


def estado_de_entrada(
    entrada,
    posicao_ns: int | None = None,
    velocidade: float = 1.0,
    pausado: bool = False,
) -> EstadoReplay:
    """Monta o estado a partir de uma `EntradaCatalogo`.

    O intervalo vem de `hora_inicio_ns`/`hora_fim_ns` do proprio `meta.json`
    — os dois escalares que `Gravador` mantem incrementalmente. Nao ha
    varredura de arquivo para descobrir a duracao: quem gravou ja sabia.

    `hora_*` ausente (meta antigo) vira intervalo zero, e `progresso` devolve
    0 sem levantar: a tarja continua correta (a hora do evento e o que ela
    mostra) e so a trilha perde a informacao que nunca existiu.
    """
    inicio = entrada.hora_inicio_ns or 0
    fim = entrada.hora_fim_ns or 0
    return EstadoReplay(
        ativo=True,
        symbol=entrada.symbol,
        data=entrada.data,
        inicio_ns=inicio,
        fim_ns=fim,
        posicao_ns=inicio if posicao_ns is None else posicao_ns,
        velocidade=velocidade,
        pausado=pausado,
    )


class TarjaReplay(PainelDenso):
    """A faixa da JANELA inteira. Nao e painel de layout — e sobreposto."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tokens.ALERT)
        self._estado = EstadoReplay()
        self._hospedeiro: QWidget | None = None
        self.setFixedHeight(ALTURA_TARJA)
        # Sobreposto nao recebe clique: por baixo dela pode haver um menu, e
        # uma tarja que rouba clique seria um estorvo permanente para
        # informar um estado que ja e permanente enquanto dura.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ------------------------------------------------------------ instalacao
    def instalar_em(self, hospedeiro: QWidget) -> None:
        """Gruda a tarja no topo de `hospedeiro`, com a largura dele.

        Sobreposto e nao item de layout de proposito: entrar no layout faria
        a tarja depender de o workspace corrente ter reservado espaco para
        ela, e um workspace que esqueceu a tarja e um workspace que apresenta
        replay como pregao ao vivo. Sobreposto, ela aparece por cima de
        qualquer arranjo — inclusive de um que nao saiba que ela existe.
        """
        anterior = self.__dict__.get("_hospedeiro")
        if anterior is not None and anterior is not hospedeiro:
            anterior.removeEventFilter(self)
        self._hospedeiro = hospedeiro
        self.setParent(hospedeiro)
        hospedeiro.installEventFilter(self)
        self._reposicionar()
        self.setVisible(self._estado.ativo)
        self.raise_()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:  # noqa: N802
        # `__dict__.get` e nao `self._hospedeiro`: um filtro de evento
        # sobrevive ao desmonte do estado Python do widget, e durante a
        # destruicao da janela o Qt ainda entrega eventos para um objeto cujo
        # `__dict__` ja foi esvaziado. Com o acesso direto isso vira
        # `AttributeError` no meio do fechamento — barulho que esconde erro
        # de verdade no log de quem for depurar outra coisa.
        hospedeiro = self.__dict__.get("_hospedeiro")
        if hospedeiro is not None and objeto is hospedeiro and evento.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self._reposicionar()
            if self.isVisible():
                self.raise_()
        return False

    def _reposicionar(self) -> None:
        if self._hospedeiro is None:
            return
        self.setGeometry(0, 0, self._hospedeiro.width(), ALTURA_TARJA)

    # ----------------------------------------------------------------- dados
    def definir_estado(self, estado: EstadoReplay) -> None:
        if estado == self._estado:
            return
        self._estado = estado
        self.setVisible(estado.ativo)
        if estado.ativo:
            self.raise_()
        self.marcar_tudo_sujo()

    @property
    def estado(self) -> EstadoReplay:
        return self._estado

    def altura_natural(self) -> int:
        return ALTURA_TARJA

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        largura = self.width()
        painter.fillRect(QRect(0, 0, largura, ALTURA_TARJA), tokens.ALERT)
        # Os 3px de §3.5, em `BG_BASE`: e o que da BORDA a faixa contra um
        # cabecalho de janela que tambem pode ser claro. Sem a borda, a tarja
        # depende de contrastar com o que estiver por baixo dela.
        painter.fillRect(QRect(0, 0, largura, ALTURA_FAIXA), tokens.BG_BASE)
        if not self._estado.ativo:
            return
        texto = self._estado.texto_tarja
        util = largura - 2 * MARGEM
        painter.setFont(_maior_que_cabe(texto, util))
        painter.setPen(tokens.BG_BASE)
        painter.drawText(
            QRect(MARGEM, ALTURA_FAIXA, util, ALTURA_TARJA - ALTURA_FAIXA),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )


class ControlesReplay(PainelDenso):
    """Transporte: velocidade em degraus declarados e trilha de busca.

    Emite INTENCAO e nao executa nada: quem troca a fonte de dados e a
    janela. Um widget que instanciasse `AdaptadorLeitorGravacao` sozinho
    passaria a decidir integridade de hash, catalogo e thread — tres coisas
    que ja tem dono em `app/` e que nao melhoram por morar num `paintEvent`.
    """

    buscou = Signal("qlonglong")
    """Timestamp em ns para onde o operador arrastou.

    `qlonglong` e nao `int`: o `int` do Qt tem 32 bits e um timestamp de
    epoch em nanossegundos vale ~1,7e18. Declarado como `int`, o valor sai
    do outro lado TRUNCADO — e o teste de arrastar pegou isso emitindo
    `836683744` no meio de uma sequencia decrescente. Um `seek` para um
    instante que nao existe seria um replay que "nao acha" o momento que o
    operador viu com o proprio olho, sem erro nenhum no caminho."""

    velocidade_mudou = Signal(float)
    pausa_alternada = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        velocidades: tuple[float, ...] = VELOCIDADES,
    ) -> None:
        super().__init__(parent)
        self.densidade = densidade
        self.velocidades = velocidades
        self._estado = EstadoReplay()
        self._arrastando = False
        self._fm_rotulo = QFontMetrics(tokens.fonte_rotulo())
        self._fm_grade = QFontMetrics(tokens.fonte_numero(densidade.fonte_grade))
        self._largura_chip = max(
            40, self._fm_rotulo.horizontalAdvance("00,00×") + 2 * ESPACO_CHIP + 8
        )
        self.setMouseTracking(True)
        self.setMinimumSize(360, self.altura_natural())

    # ------------------------------------------------------------- geometria
    #
    # Toda coordenada desta secao e usada por TRES caminhos: o desenho, o
    # teste e o acerto do clique. Nao ha aritmetica de posicao nos tres
    # lugares — ha uma, aqui. Uma mutacao em `rect_chip` move o pixel, muda
    # onde o clique acerta e derruba o teste, os tres juntos.
    def altura_natural(self) -> int:
        return (
            self.densidade.altura_cabecalho
            + ALTURA_LINHA_CONTROLE
            + ALTURA_LINHA_CONTROLE
        )

    @property
    def rect_cabecalho(self) -> QRect:
        return QRect(0, 0, self.width(), self.densidade.altura_cabecalho)

    @property
    def rect_linha_velocidade(self) -> QRect:
        return QRect(
            0, self.densidade.altura_cabecalho, self.width(), ALTURA_LINHA_CONTROLE
        )

    @property
    def rect_linha_trilha(self) -> QRect:
        return QRect(
            0,
            self.densidade.altura_cabecalho + ALTURA_LINHA_CONTROLE,
            self.width(),
            ALTURA_LINHA_CONTROLE,
        )

    def rect_pausa(self) -> QRect:
        linha = self.rect_linha_velocidade
        largura = self._fm_rotulo.horizontalAdvance("PAUSAR") + 24
        return QRect(
            max(0, linha.right() - MARGEM - largura),
            linha.top() + 4,
            largura,
            linha.height() - 8,
        )

    def rect_chip(self, indice: int) -> QRect:
        linha = self.rect_linha_velocidade
        return QRect(
            MARGEM + indice * (self._largura_chip + ESPACO_CHIP),
            linha.top() + 4,
            self._largura_chip,
            linha.height() - 8,
        )

    def chip_em(self, x: int, y: int) -> int | None:
        for indice in range(len(self.velocidades)):
            if self.rect_chip(indice).contains(x, y):
                return indice
        return None

    def rect_trilha(self) -> QRect:
        linha = self.rect_linha_trilha
        largura_hora = self._fm_grade.horizontalAdvance("88:88:88") + MARGEM
        return QRect(
            MARGEM + largura_hora,
            linha.top() + (linha.height() - ALTURA_TRILHA) // 2,
            max(1, self.width() - 2 * (MARGEM + largura_hora)),
            ALTURA_TRILHA,
        )

    def x_do_progresso(self, fracao: float) -> int:
        trilha = self.rect_trilha()
        fracao = min(1.0, max(0.0, fracao))
        return trilha.left() + int(round(trilha.width() * fracao))

    def fracao_em(self, x: int) -> float:
        trilha = self.rect_trilha()
        if trilha.width() <= 0:
            return 0.0
        return min(1.0, max(0.0, (x - trilha.left()) / trilha.width()))

    # ----------------------------------------------------------------- dados
    def definir_estado(self, estado: EstadoReplay) -> None:
        anterior = self._estado
        if estado == anterior:
            return
        self._estado = estado
        if (anterior.velocidade, anterior.pausado, anterior.ativo) != (
            estado.velocidade,
            estado.pausado,
            estado.ativo,
        ):
            self.marcar_sujo(self.rect_linha_velocidade)
        if (anterior.posicao_ns, anterior.inicio_ns, anterior.fim_ns) != (
            estado.posicao_ns,
            estado.inicio_ns,
            estado.fim_ns,
        ):
            self.marcar_sujo(self.rect_linha_trilha)
            self.marcar_sujo(self.rect_cabecalho)
        if (anterior.symbol, anterior.data) != (estado.symbol, estado.data):
            self.marcar_sujo(self.rect_cabecalho)

    @property
    def estado(self) -> EstadoReplay:
        return self._estado

    # ----------------------------------------------------------------- mouse
    def mousePressEvent(self, evento) -> None:  # noqa: N802
        posicao = evento.position().toPoint()
        if self.rect_pausa().contains(posicao):
            self.pausa_alternada.emit(not self._estado.pausado)
            return
        indice = self.chip_em(posicao.x(), posicao.y())
        if indice is not None:
            self.velocidade_mudou.emit(self.velocidades[indice])
            return
        if self.rect_linha_trilha.contains(posicao):
            self._arrastando = True
            self.buscou.emit(self._estado.em(self.fracao_em(posicao.x())))

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802
        # Arrastar-para-voltar: o `buscou` sai a cada movimento, e nao so ao
        # soltar. Voltar num replay e uma busca EXPLORATORIA ("onde foi que
        # aquilo aconteceu?"), e ela precisa do retorno enquanto o dedo anda
        # — soltar para descobrir que passou do ponto e ter de arrastar de
        # novo transforma uma leitura em tentativa e erro.
        if self._arrastando:
            self.buscou.emit(
                self._estado.em(self.fracao_em(evento.position().toPoint().x()))
            )

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802
        self._arrastando = False

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        if self.rect_cabecalho.intersects(regiao):
            self._desenhar_cabecalho(painter)
        if self.rect_linha_velocidade.intersects(regiao):
            self._desenhar_velocidades(painter)
        if self.rect_linha_trilha.intersects(regiao):
            self._desenhar_trilha(painter)

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        banda = self.rect_cabecalho
        painter.fillRect(banda, tokens.BG_RAISED)
        interno = banda.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        rotulo = "REPLAY"
        if self._estado.symbol:
            rotulo += " · " + self._estado.symbol
        if self._estado.data is not None:
            rotulo += " · " + self._estado.texto_data
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo
        )
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 600))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_hora_ns(self._estado.posicao_ns),
        )

    def _desenhar_velocidades(self, painter: QPainter) -> None:
        linha = self.rect_linha_velocidade
        painter.fillRect(linha, tokens.BG_SURFACE)
        for indice, velocidade in enumerate(self.velocidades):
            chip = self.rect_chip(indice)
            if chip.right() > linha.right() - MARGEM:
                break
            ativo = abs(velocidade - self._estado.velocidade) < 1e-9
            fundo = tokens.ALERT if ativo else tokens.BG_RAISED
            painter.fillRect(chip, fundo)
            painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 600))
            painter.setPen(tokens.BG_BASE if ativo else tokens.TEXT_SECONDARY)
            painter.drawText(
                chip, Qt.AlignmentFlag.AlignCenter, texto_velocidade(velocidade)
            )
        botao = self.rect_pausa()
        painter.fillRect(botao, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            botao,
            Qt.AlignmentFlag.AlignCenter,
            (GLIFO_TOCANDO + " TOCAR") if self._estado.pausado else (GLIFO_PAUSADO + " PAUSAR"),
        )

    def _desenhar_trilha(self, painter: QPainter) -> None:
        """Trilha de largura FIXA: proporcao, eixo absoluto, sem escala.

        Mesma forma da barra particionada do HUD e pelo mesmo motivo — nao ha
        escala para o canal apagar, e nao ha dois comprimentos com eixos
        diferentes para o leitor comparar errado.
        """
        linha = self.rect_linha_trilha
        painter.fillRect(linha, tokens.BG_SURFACE)
        trilha = self.rect_trilha()
        painter.fillRect(trilha, tokens.BG_RAISED)
        corte = self.x_do_progresso(self._estado.progresso)
        percorrido = corte - trilha.left()
        if percorrido > 0:
            painter.fillRect(
                QRect(trilha.left(), trilha.top(), percorrido, trilha.height()),
                tokens.ALERT,
            )
        # A alca, com contorno escuro: a mesma solucao da trilha do meio do
        # bookmap. Ela cruza `--alert` de um lado e `--bg-raised` do outro, e
        # nenhuma cor unica tem borda contra as duas.
        painter.fillRect(
            QRect(corte - 1, trilha.top() - 2, LARGURA_ALCA + 2, trilha.height() + 4),
            tokens.BG_BASE,
        )
        painter.fillRect(
            QRect(corte, trilha.top() - 1, LARGURA_ALCA, trilha.height() + 2),
            tokens.TEXT_PRIMARY,
        )

        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(MARGEM, linha.top(), trilha.left() - 2 * MARGEM, linha.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _hora_curta(self._estado.inicio_ns) if self._estado.duracao_ns else "—",
        )
        painter.drawText(
            QRect(
                trilha.right() + MARGEM,
                linha.top(),
                max(0, linha.right() - trilha.right() - 2 * MARGEM),
                linha.height(),
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            _hora_curta(self._estado.fim_ns) if self._estado.duracao_ns else "—",
        )
