"""Delta acumulado — o saldo da sessao no MESMO eixo de tempo do footprint.

`bar/05_cumulative_delta_b.png` e a referencia, e ela erra tres coisas de uma
vez na mesma janela de 600px:

1. **Tres vocabularios direcionais empilhados** (fraqueza F1): candle branco/
   preto em cima, barra verde/vermelha embaixo, e o livro da mesma plataforma
   usa azul/vermelho. O trader troca de dicionario tres vezes ao varrer a
   tela. Aqui ha **um par so** — azul = compra, vermelho = venda — e ele vale
   no footprint, no perfil e aqui.
2. **Duas codificacoes na mesma marca.** Naquela tela a POSICAO de cada barra
   e o delta ACUMULADO e a COR e o delta DAQUELE candle: duas grandezas
   diferentes no mesmo retangulo, e nada na tela diz isso. Aqui posicao e cor
   dizem a mesma coisa — o sinal do acumulado — e o delta do candle vive no
   rodape do footprint, que e o painel do candle.
3. **Um eixo que nao contem o zero.** As marcas do eixo vao de `-1,04M` a
   `-1,51M`. Sem o zero desenhado, a altura de uma barra bidirecional deixa de
   significar qualquer coisa: o que se ve e a variacao dentro de uma janela
   arbitraria, apresentada com a forma de um saldo. **Aqui o zero e sempre
   desenhado e sempre esta no eixo**, por construcao — a escala e simetrica em
   torno dele.

## A escala, que e o ponto delicado

Delta acumulado e grandeza sem teto: ele varre ordens de magnitude ao longo de
uma sessao. O vocabulario de `hud.py` diz que grandeza assim vira **numero**,
e ela vira: o acumulado corrente esta escrito no cabecalho, com sinal
explicito, em corpo grande. Mas a *forma da trajetoria* — que e a unica coisa
que este painel oferece e que nenhum numero substitui — precisa de um eixo.

Entao a escala existe, e o cuidado esta em tornar a mudanca dela **visivel
como geometria**, e nao confiada a um rotulo de 10px (o defeito 4 de
`hud.py`: o unico portador da mudanca era um `±2,5k` que o canal apaga):

* a escala e quantizada em degraus **1-2-5**, entao ela muda poucas vezes por
  sessao e nunca por um contrato a mais;
* ela **so encolhe** quando o pico cai abaixo de um quarto do degrau, o que
  impede o vaivem entre dois degraus vizinhos;
* as linhas de grade ficam em **incrementos redondos absolutos** (1k, 2k, 5k,
  10k...). Quando a escala dobra, o NUMERO DE LINHAS na tela muda — e contar
  linhas e uma leitura geometrica, que sobrevive a reescala e a quantizacao. O
  eixo passa a denunciar o proprio movimento sem depender de ler nada;
* o valor do incremento viaja em **chip** na calha, e nao em texto solto:
  bloco preenchido com texto escuro e a forma que `scripts/retencao.py` mediu
  como a ultima a morrer no canal.

A forma da barra e a primeira do vocabulario de `hud.py`: **bidirecional a
partir de um zero desenhado = saldo assinado**. Nao ha piso; um acumulado que
arredonda para zero pixel esta, de fato, em cima da linha do zero.

## Alinhamento com o footprint: verificado, nao presumido

`CumulativeDelta` recebe `ConfigDelta.timeframe_ns`, que **nao e** o
`ConfigOperacao.timeframe_ns` que alimenta o footprint — os dois batem por
default e sao calibraveis em separado. Um painel que presumisse o alinhamento
mentiria em silencio no dia em que alguem mexesse num dos dois.

Entao o painel desenha na sua propria fileira de colunas e **confere** cada
candle contra `EixoTempo.inicios`, que e o objeto que o footprint escreve. Se
algum candle nao cair na coluna que o footprint diz, a tela ganha um chip
ambar `EIXOS ≠` — a mesma convencao de "o produto nao conseguiu casar isto"
que o footprint usa no imbalance sem razao e o perfil no POC empatado.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.analytics.delta import ConfigDelta
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.paineis.footprint import (
    ALTURA_CHIP_MINIMA,
    CORPO_CHIP,
    MARGEM,
    EixoTempo,
    chip,
    metrica,
    procedencia_de_config,
)

ALTURA_EIXO_TEMPO = 14
ESPESSURA_ZERO = 2
"""Dois pixels, e nao um. O zero e o marco contra o qual toda a coluna e lida;
a reescala de 0,72 do canal transforma 2px em 1,4 e 1px em nada."""

MOLDE_VALOR = "−999.999 · 99% S/ LADO"
"""So para MEDIR a faixa do numero do cabecalho.

Medir e melhor que cravar: a fonte muda entre maquinas (Iosevka, JetBrains,
Consolas tem avancos diferentes) e a densidade muda o corpo. Um numero cravado
esta certo numa combinacao e errado nas outras — foi assim que a coluna de
saldo do ranking de players passou a pintar glifos por cima da barra do
vizinho."""

VAO_BARRA = 1
INTERVALO_ROTULO_TEMPO = 4
"""Uma marca de hora a cada N colunas. Rotulo em toda coluna colidiria e
§1 (F8) e explicito: o que nao cabe INTEIRO nao entra, e nada e rotacionado."""


@dataclass(frozen=True, slots=True)
class CandleDeltaTela:
    """Um candle de delta, ja reduzido ao que a tela usa."""

    inicio_ns: int
    delta: int
    acumulado: int
    preco_fechamento: int
    viva: bool = False


@dataclass(frozen=True, slots=True)
class LeituraDelta:
    """O que muda entre dois quadros. Nunca o historico inteiro.

    `CumulativeDelta.historico` constroi uma tupla da sessao a cada chamada —
    custo O(sessao) por quadro a 62 Hz. `historico` so vem preenchido na
    PRIMEIRA leitura (quando o painel acorda no meio da sessao); depois disso
    o painel recebe o candle vivo e, na virada, o que acabou de fechar.
    """

    viva: CandleDeltaTela | None = None
    fechada: CandleDeltaTela | None = None
    historico: tuple[CandleDeltaTela, ...] = ()
    acumulado_sessao: int = 0
    volume_total: int = 0
    volume_sem_lado: int = 0
    divergente: bool = False
    janela_divergencia: int = 0
    timeframe_ns: int = 0

    @property
    def fracao_sem_lado(self) -> float:
        if self.volume_total <= 0:
            return 0.0
        return self.volume_sem_lado / self.volume_total


def _tela(candle, viva: bool) -> CandleDeltaTela:
    return CandleDeltaTela(
        inicio_ns=candle.timestamp_inicio_ns,
        delta=candle.delta,
        acumulado=candle.delta_acumulado_no_fechamento,
        preco_fechamento=candle.preco_fechamento,
        viva=viva,
    )


def derivar_delta(fonte, inicio_conhecido_ns: int | None, n_colunas: int) -> LeituraDelta:
    """`analytics.delta.CumulativeDelta` -> `LeituraDelta`. Puro, sem Qt.

    Toca `historico` em dois momentos e so neles: no bootstrap
    (`inicio_conhecido_ns is None`) e na virada do candle, para pegar o estado
    FINAL do que fechou em vez do ultimo retrato que a UI calhou de ler 16 ms
    antes do fim.
    """
    if fonte is None:
        return LeituraDelta()
    atual = fonte.candle_atual
    if atual is None:
        return LeituraDelta()
    config = fonte.config
    historico: tuple[CandleDeltaTela, ...] = ()
    fechada: CandleDeltaTela | None = None
    if inicio_conhecido_ns is None:
        anteriores = fonte.historico
        recorte = anteriores[-max(0, n_colunas - 1):] if n_colunas > 1 else ()
        historico = tuple(_tela(c, viva=False) for c in recorte)
    elif inicio_conhecido_ns != atual.timestamp_inicio_ns:
        anteriores = fonte.historico
        if anteriores:
            fechada = _tela(anteriores[-1], viva=False)
    return LeituraDelta(
        viva=_tela(atual, viva=True),
        fechada=fechada,
        historico=historico,
        acumulado_sessao=fonte.delta_sessao,
        volume_total=fonte.volume_total_sessao,
        volume_sem_lado=fonte.volume_nao_atribuido_sessao,
        divergente=fonte.delta_divergente(),
        janela_divergencia=config.janela_divergencia,
        timeframe_ns=config.timeframe_ns,
    )


class PainelDeltaAcumulado(PainelDenso):
    """A trajetoria do saldo da sessao, coluna a coluna."""

    def __init__(
        self,
        eixo: EixoTempo,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        config: ConfigDelta | None = None,
    ) -> None:
        super().__init__(parent)
        # O eixo de TEMPO e do footprint. Este painel nao cria um: ele desenha
        # na propria fileira e CONFERE contra o do footprint (ver `alinhado`).
        self.eixo = eixo
        self.densidade = densidade
        self.paleta = paleta
        self.config = config if config is not None else ConfigDelta()

        self._leitura = LeituraDelta()
        # Slots de TELA, indexado por coluna — reconstruidos a cada quadro a
        # partir das chaves do `EixoTempo`, nunca mantidos em paralelo.
        self._colunas: list[CandleDeltaTela | None] = []
        # Os candles que este painel recebeu, em ordem de tempo, com teto de
        # TELA. E a unica coisa que ele guarda.
        self._recentes: list[CandleDeltaTela] = []
        self._inicios_vistos: tuple[int | None, ...] = ()
        self._inicio_vivo_ns: int | None = None
        self._escala = 1
        self._chave_cabecalho: tuple | None = None
        self._medir(densidade)
        self.setMinimumSize(320, 120)

    def _medir(self, densidade: tokens.Densidade) -> None:
        """O que a densidade define. Construtor e `aplicar_densidade` chamam
        ESTA, para que as duas nao possam divergir."""
        self._fm_rotulo = metrica(tokens.fonte_rotulo())
        self._fm_chip = metrica(tokens.fonte_rotulo(CORPO_CHIP))
        self._fm_numero = metrica(tokens.fonte_numero(10))

    def aplicar_densidade(self, nova: tokens.Densidade) -> None:
        """Troca a densidade a quente. `_recentes` — o unico estado que este
        painel guarda — sobrevive.

        O `EixoTempo` NAO e tocado aqui: o dono e o `PainelFootprint`, e este
        painel apenas confere o alinhamento contra ele. `_chave_cabecalho` e
        zerada porque o cabecalho e memoizado por uma chave que nao inclui a
        densidade — sem isso, a faixa do titulo continuaria com os pixels
        medidos na fonte anterior ate o proximo dado mudar.
        """
        if nova is self.densidade:
            return
        self.densidade = nova
        self._medir(nova)
        self._chave_cabecalho = None
        self._inicios_vistos = ()
        self.marcar_tudo_sujo()

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    @property
    def area_plot(self) -> QRect:
        """A area util do grafico. **Publica porque o teste recorta
        exatamente esta faixa** — recorte escrito a parte pode divergir do
        desenho e o teste passa a medir outra coisa sem avisar."""
        return QRect(
            self.eixo.x0,
            self._y_corpo,
            max(0, self.width() - self.eixo.x0),
            max(0, self.height() - self._y_corpo - ALTURA_EIXO_TEMPO),
        )

    @property
    def rect_valor(self) -> QRect:
        """A faixa do numero grande do cabecalho.

        Faixa PROPRIA, e nao um pedaco do cabecalho inteiro, pela regra que
        `matriz.py` pagou para aprender: **o que nao muda nao compartilha
        retangulo sujo com o que muda.** O acumulado anda a cada negocio; os
        chips de procedencia, de divergencia e de alinhamento passam minutos
        parados. Juntos num retangulo so, cada tick repintava os chips
        tambem — e o quadro incremental deste painel media 0,33 ms contra
        0,70 ms do quadro cheio, razao 2,1x, abaixo do portao de 5x."""
        largura = min(
            self.width(),
            metrica(tokens.fonte_numero(13, 600)).horizontalAdvance(MOLDE_VALOR)
            + 2 * MARGEM,
        )
        return QRect(self.width() - largura, 0, largura, self._y_corpo)

    @property
    def rect_texto_valor(self) -> QRect:
        """A caixa que o NUMERO de fato ocupa, medida no texto corrente.

        Publica, e usada tanto pelo `drawText` quanto pela caixa que
        `scripts/retencao.py` mede. Medir a faixa inteira em vez do texto
        inflava a retencao do veredito: area chapada tem energia de borda
        quase nula antes e ganha o zumbido da quantizacao depois, entao a
        razao subia sem que um traco a mais tivesse sobrevivido. Comparar
        ressalva com veredito exige que as duas caixas contenham TINTA, e nao
        fundo."""
        rect = self.rect_valor
        texto = self.texto_acumulado()
        fm = metrica(tokens.fonte_numero(13, 600))
        largura = min(rect.width() - MARGEM, fm.horizontalAdvance(texto))
        altura = fm.height()
        return QRect(
            rect.right() - MARGEM - largura + 1,
            rect.top() + (rect.height() - altura) // 2,
            largura,
            altura,
        )

    @property
    def rect_chips(self) -> QRect:
        return QRect(0, 0, max(0, self.rect_valor.left()), self._y_corpo)

    @property
    def rect_chip_procedencia(self) -> QRect:
        """A caixa do chip `§ S/ REGISTRO k/n`.

        Publica porque `scripts/retencao.py` mede exatamente ela contra o
        numero grande que ela qualifica — a lei do canal so vira numero se as
        duas caixas sairem da MESMA geometria que o desenho usa."""
        rect = self.rect_chips
        rotulo, _ = procedencia_de_config(type(self.config))
        x = MARGEM + self._fm_rotulo.horizontalAdvance("Δ ACUMULADO · SESSÃO") + 12
        largura = self._fm_chip.horizontalAdvance(rotulo) + 12
        altura = max(ALTURA_CHIP_MINIMA, rect.height() - 6)
        return QRect(x, rect.top() + (rect.height() - altura) // 2, largura, altura)

    @property
    def area_rolagem(self) -> QRect:
        """A area que ROLA quando um candle nasce: o grafico **e** a faixa de
        horas embaixo.

        Deixar a faixa de horas fora custou um defeito que so o retrato pegou.
        `PainelDenso.rolar` translada os retangulos sujos que estao CONTIDOS na
        area rolada e deixa os de fora onde estavam — e o retangulo de "esta
        coluna perdeu a marca de candle vivo" cobre grafico e horas. Fora da
        area, ele parava de acompanhar os pixels: quando varios candles nasciam
        entre dois quadros, a marca branca de 2px do candle vivo ficava
        impressa no backing em todas as colunas por onde ela passou. A tela
        mostrava cinco candles vivos ao mesmo tempo.

        E as horas TEM de rolar junto: elas pertencem a coluna, nao a moldura.
        """
        plot = self.area_plot
        return QRect(
            plot.left(), plot.top(), plot.width(), plot.height() + ALTURA_EIXO_TEMPO
        )

    @property
    def escala(self) -> int:
        """Fundo de escala corrente, em lotes. Simetrico: o eixo vai de
        `-escala` a `+escala`, e o zero fica exatamente no meio."""
        return self._escala

    @property
    def incremento(self) -> int:
        """Passo das linhas de grade, sempre um valor REDONDO.

        E a peca que torna a mudanca de escala visivel como geometria: quando
        a escala dobra, o numero de linhas na tela muda, e contar linhas nao
        depende de ler rotulo nenhum."""
        return _incremento_de(self._escala)

    def y_zero(self) -> int:
        plot = self.area_plot
        return plot.top() + plot.height() // 2

    def y_de(self, valor: int) -> int:
        """Y de um acumulado. Compartilhada por desenho e teste, de proposito.

        Teste que mede contra um marco que o desenho nao usa e teatro: foi
        assim que o guarda anti-piso do ranking de players deixou passar
        exatamente o piso que existia no produto."""
        plot = self.area_plot
        meia = max(1, plot.height() // 2 - 1)
        if self._escala <= 0:
            return self.y_zero()
        fracao = max(-1.0, min(1.0, valor / self._escala))
        return self.y_zero() - int(round(fracao * meia))

    def rect_barra(self, indice: int) -> QRect:
        """A barra de uma coluna, do zero ate o acumulado."""
        candle = self._colunas[indice] if 0 <= indice < len(self._colunas) else None
        zero = self.y_zero()
        if candle is None:
            return QRect(self.eixo.x_da_coluna(indice) + VAO_BARRA, zero, 0, 0)
        y = self.y_de(candle.acumulado)
        return QRect(
            self.eixo.x_da_coluna(indice) + VAO_BARRA,
            min(zero, y),
            max(1, self.eixo.largura_coluna - 2 * VAO_BARRA),
            abs(y - zero),
        )

    def rect_coluna_inteira(self, indice: int) -> QRect:
        plot = self.area_plot
        return QRect(
            self.eixo.x_da_coluna(indice),
            plot.top(),
            self.eixo.largura_coluna,
            plot.height() + ALTURA_EIXO_TEMPO,
        )

    # ---------------------------------------------------------------- dados
    @property
    def inicio_vivo_ns(self) -> int | None:
        return self._inicio_vivo_ns

    @property
    def colunas_visiveis(self) -> tuple[CandleDeltaTela | None, ...]:
        return tuple(self._colunas)

    @property
    def alinhado(self) -> bool:
        """Algum candle deste painel cai na fileira que o FOOTPRINT desenhou?

        Conferido contra `EixoTempo.inicios`, o objeto que o footprint
        escreve — nunca presumido. `CumulativeDelta` recebe o proprio
        `ConfigDelta.timeframe_ns`, que NAO e o `ConfigOperacao.timeframe_ns`
        do footprint: os dois batem por default e sao calibraveis em separado.

        A conta e "algum", e nao "todos", e a diferenca foi paga: as duas
        pecas leem objetos VIVOS que a thread da fonte esta mutando, entao
        entre o `derivar_footprint` e o `derivar_delta` do mesmo quadro pode
        nascer um candle. Exigir que TODOS casassem acendia `EIXOS ≠` por essa
        corrida de um quadro — um alarme falso sobre a peca que existe para dar
        alarme verdadeiro. Com timeframes de fato diferentes, nenhum candle
        casa e o chip acende e fica."""
        if not self._recentes or not any(i is not None for i in self.eixo.inicios):
            return True
        return any(
            self.eixo.coluna_do_inicio(c.inicio_ns) is not None for c in self._recentes
        )

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        n = self.eixo.n_colunas
        self._colunas = [None] * n
        self._inicios_vistos = ()
        del self._recentes[: max(0, len(self._recentes) - max(1, n) - 1)]

    def aplicar(self, leitura: LeituraDelta) -> None:
        """Absorve o quadro.

        O painel **nao mantem uma fileira paralela** a do footprint: ele guarda
        os candles que recebeu e se posiciona pela CHAVE de tempo em
        `EixoTempo.inicios`. A primeira versao rolava por conta propria, ao
        detectar a virada na sua propria fonte — e as duas pecas leem objetos
        vivos em instantes ligeiramente diferentes, entao bastava um candle
        nascer entre o `derivar_footprint` e o `derivar_delta` do mesmo quadro
        para esta fileira rolar uma vez a mais e ficar **permanentemente**
        deslocada. Deslocamento por corrida nao se corrige sozinho: ele
        sobrevive a todas as viradas seguintes.

        Posicionando por chave, a fileira do footprint e a unica fonte de
        verdade sobre qual coluna e qual candle, e a corrida custa no maximo
        um candle nao desenhado por um quadro."""
        self._leitura = leitura
        if not self.eixo.n_colunas:
            self._inicio_vivo_ns = leitura.viva.inicio_ns if leitura.viva else None
            return
        for candle in leitura.historico:
            self._registrar(candle)
        if leitura.fechada is not None:
            self._registrar(leitura.fechada)
        if leitura.viva is not None:
            self._registrar(leitura.viva)
            self._inicio_vivo_ns = leitura.viva.inicio_ns
        self._sincronizar_eixo()
        self._recolocar()
        self._ajustar_escala()
        self._sujar_cabecalho(leitura)

    def _registrar(self, candle: CandleDeltaTela) -> None:
        """Guarda o candle. Ring de tamanho de TELA, nunca historico.

        Este projeto ja encontrou oito vezes a estrutura que cresce com o
        estado acumulado; a nona nao vai ser esta."""
        if self._recentes and self._recentes[-1].inicio_ns == candle.inicio_ns:
            self._recentes[-1] = candle
        elif self._recentes and candle.inicio_ns < self._recentes[-1].inicio_ns:
            return  # candle mais velho que o ultimo: chegou fora de ordem
        else:
            self._recentes.append(candle)
        # Teto de tela MAIS UM. O "mais um" e o candle que ja nasceu deste lado
        # e que o footprint ainda nao registrou no eixo — a corrida de um
        # quadro. Sem essa folga, guardar o recem-nascido custava descartar o
        # mais antigo, e a coluna da esquerda apagava por um quadro sem que
        # nada tivesse mudado nela.
        teto = max(1, self.eixo.n_colunas) + 1
        del self._recentes[: max(0, len(self._recentes) - teto)]

    def _sincronizar_eixo(self) -> None:
        """Acompanha a rolagem do FOOTPRINT movendo os proprios pixels.

        Uma rolagem de exatamente uma coluna e reconhecida pela forma da
        fileira (`novos[:-1] == antigos[1:]`) e vira um `scroll` do backing —
        que e o mecanismo de §2, Achado 1. Qualquer outra mudanca (janela
        redimensionada, semeadura, salto de varios candles) e quadro cheio, e
        deve ser: nao ha como mover pixels para posicoes que ninguem sabe."""
        atuais = tuple(self.eixo.inicios)
        if atuais == self._inicios_vistos:
            return
        antigos = self._inicios_vistos
        self._inicios_vistos = atuais
        if (
            antigos
            and len(atuais) == len(antigos)
            and len(atuais) >= 2
            and atuais[:-1] == antigos[1:]
        ):
            self.rolar(-self.eixo.largura_coluna, 0, self.area_rolagem)
        else:
            self.marcar_tudo_sujo()

    def _recolocar(self) -> None:
        """Reconstroi a fileira de tela a partir das CHAVES do eixo."""
        n = self.eixo.n_colunas
        if len(self._colunas) != n:
            self._colunas = [None] * n
            self.marcar_tudo_sujo()
        novos: list[CandleDeltaTela | None] = [None] * n
        for candle in self._recentes:
            indice = self.eixo.coluna_do_inicio(candle.inicio_ns)
            if indice is not None:
                novos[indice] = candle
        if not self._tudo_sujo:
            for indice, (velho, novo) in enumerate(zip(self._colunas, novos)):
                if velho != novo:
                    self.marcar_sujo(self.rect_coluna_inteira(indice))
        self._colunas = novos

    def _sujar_cabecalho(self, leitura: LeituraDelta) -> None:
        # O cabecalho e DUAS faixas: o numero, que anda a cada negocio, e os
        # chips, que passam minutos parados. Juntos num retangulo so, cada tick
        # repintava os chips tambem — e a razao cheio/incremental caia para
        # 2,1x, abaixo do portao de 5x. O que nao muda nao compartilha
        # retangulo sujo com o que muda.
        texto = self.texto_acumulado()
        chips = (leitura.divergente, leitura.janela_divergencia, self.alinhado)
        if self._chave_cabecalho is None:
            self.marcar_tudo_sujo()
        else:
            if texto != self._chave_cabecalho[0]:
                self.marcar_sujo(self.rect_valor)
            if chips != self._chave_cabecalho[1]:
                self.marcar_sujo(self.rect_chips)
        self._chave_cabecalho = (texto, chips)

    def _ajustar_escala(self) -> None:
        """Degraus 1-2-5 com histerese — a mesma serie do DOM e da matriz.

        Seguir o pico exato obrigaria a redesenhar o painel inteiro a cada
        candle so porque o fundo de escala andou um contrato, e o ganho da
        regiao suja iria embora pela porta dos fundos. Encolher so abaixo de um
        quarto impede o vaivem entre dois degraus vizinhos.
        """
        pico = 1
        for candle in self._colunas:
            if candle is not None:
                pico = max(pico, abs(candle.acumulado))
        alvo = _degrau_1_2_5(pico)
        if alvo > self._escala or pico * 4 < self._escala:
            self._escala = max(1, alvo)
            self.marcar_tudo_sujo()

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            if regiao.intersects(self.rect_chips):
                self._desenhar_chips(painter)
            if regiao.intersects(self.rect_valor):
                self._desenhar_valor(painter)
        plot = self.area_plot
        if not plot.isValid():
            return
        self._desenhar_grade(painter, regiao)
        alvo = plot.intersected(regiao)
        if not alvo.isValid():
            return
        largura = self.eixo.largura_coluna
        primeira = max(0, (alvo.left() - plot.left()) // largura)
        ultima = min(len(self._colunas) - 1, (alvo.right() - plot.left()) // largura)
        for indice in range(primeira, ultima + 1):
            self._desenhar_coluna(painter, indice)

    def _desenhar_chips(self, painter: QPainter) -> None:
        """Titulo e chips — a metade do cabecalho que passa minutos parada."""
        rect = self.rect_chips
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        titulo = "Δ ACUMULADO · SESSÃO"
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo
        )
        caixa = self.rect_chip_procedencia
        altura, topo = caixa.height(), caixa.top()
        x = caixa.left()
        rotulo, cor = procedencia_de_config(type(self.config))
        if caixa.right() <= rect.right():
            chip(painter, caixa, rotulo, cor)
            x = caixa.right() + 9
        if self._leitura.divergente:
            # Veredito do proprio `analytics/delta.py`, COM a janela que o
            # define. `DIVERGÊNCIA` sozinho seria um oraculo, e oraculo em
            # pregao e o jeito mais caro de perder dinheiro.
            texto = "DIVERGÊNCIA %d CANDLES" % self._leitura.janela_divergencia
            largura = self._fm_chip.horizontalAdvance(texto) + 12
            if x + largura <= rect.right():
                chip(painter, QRect(x, topo, largura, altura), texto, tokens.ALERT)
                x += largura + 8
        if not self.alinhado:
            texto = "EIXOS ≠"
            largura = self._fm_chip.horizontalAdvance(texto) + 12
            if x + largura <= rect.right():
                chip(painter, QRect(x, topo, largura, altura), texto, tokens.ABSORPTION)
        painter.setPen(tokens.BORDER)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

    def _desenhar_valor(self, painter: QPainter) -> None:
        """O acumulado E a sua ressalva, numa string so, num `drawText` so, com
        uma fonte so.

        A ressalva nao e um campo ao lado do numero — ela E o final da mesma
        string, e por isso nenhuma reescala, nenhuma quantizacao e nenhum
        recorte de coluna consegue entregar o numero sem ela. `CumulativeDelta`
        ignora o volume cujo agressor a B3 nao divulga: um delta calculado
        sobre 88% do tape nao e o delta do tape."""
        rect = self.rect_valor
        painter.fillRect(rect, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_numero(13, 600))
        painter.setPen(self.paleta.direcional(self._leitura.acumulado_sessao))
        painter.drawText(
            self.rect_texto_valor,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.texto_acumulado(),
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

    def texto_acumulado(self) -> str:
        """`+12.480 · 6% S/ LADO`. Publica para o teste afirmar a lei do canal
        sem abrir `QApplication`: se um dia o numero voltar a sair sozinho, e
        aqui que se ve."""
        base = formato.formatar_sinalizado(self._leitura.acumulado_sessao)
        fracao = self._leitura.fracao_sem_lado
        # A partir de 1%: abaixo disso a ressalva custaria mais atencao do que
        # corrige, e o numero exato continua no perfil.
        if fracao >= 0.01:
            return base + " · " + f"{round(fracao * 100)}%" + " S/ LADO"
        return base

    def _desenhar_grade(self, painter: QPainter, regiao: QRect) -> None:
        """Grade, calha e zero — recortados pela regiao suja em X e em Y.

        Nao basta o clip do Qt. §2, Achado 2: o custo esta em atravessar a
        fronteira Python<->C++, nao em rasterizar — uma linha de grade
        descartada pelo clip ja custou a chamada. Com a coluna do candle vivo
        como unica faixa suja, redesenhar as oito linhas na largura inteira
        mais os rotulos da calha respondia por quase todo o quadro incremental
        e derrubava a razao cheio/incremental para 1,6x.
        """
        plot = self.area_plot
        esquerda = max(plot.left(), regiao.left())
        direita = min(plot.right(), regiao.right())
        largura = direita - esquerda + 1
        na_calha = regiao.left() < self.eixo.x0
        incremento = self.incremento
        valor = incremento
        while valor < self._escala:
            for sinal in (1, -1):
                y = self.y_de(sinal * valor)
                if not (regiao.top() - 1 <= y <= regiao.bottom() + 1):
                    continue
                if largura > 0:
                    painter.fillRect(QRect(esquerda, y, largura, 1), tokens.BORDER)
                if na_calha:
                    painter.setFont(tokens.fonte_numero(10))
                    painter.setPen(tokens.TEXT_MUTED)
                    painter.drawText(
                        QRect(0, y - 6, self.eixo.x0 - 4, 12),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                        formato.formatar_sinalizado(sinal * valor),
                    )
            valor += incremento
        # As pontas do eixo em CHIP, e nao em texto de 10px: o defeito 4 de
        # `hud.py` foi um `±2,5k` que o canal apagava sendo o unico portador do
        # fundo de escala. Bloco preenchido com texto escuro nao some.
        if na_calha and self.eixo.x0 >= 40:
            for sinal in (1, -1):
                texto = formato.formatar_sinalizado(sinal * self._escala)
                largura_chip = min(
                    self.eixo.x0 - 4, self._fm_chip.horizontalAdvance(texto) + 10
                )
                y = plot.top() if sinal > 0 else plot.bottom() - ALTURA_CHIP_MINIMA
                caixa = QRect(
                    self.eixo.x0 - 4 - largura_chip, y, largura_chip, ALTURA_CHIP_MINIMA
                )
                if caixa.intersects(regiao):
                    chip(painter, caixa, texto, tokens.BG_RAISED)
        zero = self.y_zero()
        if regiao.top() - ESPESSURA_ZERO <= zero <= regiao.bottom() + ESPESSURA_ZERO:
            # O zero DESENHADO. Sem ele a barra bidirecional deixa de ser
            # bidirecional, e e exatamente o que falta em `05_cumulative_delta_b`.
            if largura > 0:
                painter.fillRect(
                    QRect(esquerda, zero, largura, ESPESSURA_ZERO), tokens.BORDER_STRONG
                )
            if na_calha:
                painter.setFont(tokens.fonte_numero(10))
                painter.setPen(tokens.TEXT_SECONDARY)
                painter.drawText(
                    QRect(0, zero - 6, self.eixo.x0 - 4, 12),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    "0",
                )

    def _desenhar_coluna(self, painter: QPainter, indice: int) -> None:
        candle = self._colunas[indice]
        if candle is None:
            return
        barra = self.rect_barra(indice)
        if candle.viva:
            # §5, Momento 3: candle em formacao nunca se confunde com candle
            # fechado. A mesma marca do footprint, para que as duas pecas
            # digam a mesma coisa do mesmo jeito.
            plot = self.area_plot
            painter.fillRect(
                QRect(self.eixo.x_da_coluna(indice), plot.top(), 2, plot.height()),
                tokens.TEXT_SECONDARY,
            )
        if barra.height() > 0:
            if self.paleta.tem_cor:
                rampa = (
                    tokens.RAMPA_COMPRA if candle.acumulado > 0 else tokens.RAMPA_VENDA
                )
            else:
                rampa = tokens.RAMPA_NEUTRA
            fracao = min(1.0, abs(candle.acumulado) / max(1, self._escala))
            painter.fillRect(barra, rampa[tokens.degrau(fracao)])
        if self._tem_rotulo(candle):
            self._desenhar_hora(painter, indice, candle)

    def _tem_rotulo(self, candle: CandleDeltaTela) -> bool:
        """Quem ganha marca de hora e o CANDLE, nao a coluna da tela.

        A primeira versao decidia por `indice % N == 0`, e o resultado era uma
        faixa de horas quase vazia — porque uma coluna e pintada UMA vez, no
        instante em que ela e o candle vivo (indice `n-1`), e dali em diante
        ela so ROLA: os pixels andam para a esquerda e nunca sao redesenhados.
        Se `n-1` nao satisfazia a condicao, aquela coluna jamais recebia
        rotulo, por mais que passasse por posicoes que satisfaziam.

        Decidido pelo carimbo de tempo, o rotulo e propriedade do candle e
        viaja com ele. Estavel entre quadros, e o mesmo candle sempre.
        """
        if not candle.inicio_ns or self._leitura.timeframe_ns <= 0:
            return False
        bucket = candle.inicio_ns // self._leitura.timeframe_ns
        return bucket % INTERVALO_ROTULO_TEMPO == 0

    def texto_da_hora(self, candle: CandleDeltaTela) -> str:
        """`21:01` ou `21:01:20` — a granularidade sai do TIMEFRAME.

        Com candle de minuto, o segundo e sempre zero e escreve-lo seria ruido
        repetido em toda marca (a fraqueza F6 da referencia: seis de oito
        caracteres iguais, quarenta vezes). Com candle mais curto, tres marcas
        seguidas leriam `21:01`, `21:01`, `21:01` — o eixo passaria a nomear
        instantes diferentes com o mesmo nome, que e pior que nao nomear."""
        hora = formato.formatar_hora_ns(candle.inicio_ns)
        if 0 < self._leitura.timeframe_ns < 60_000_000_000:
            return hora[:8]
        return hora[:5]

    def _desenhar_hora(self, painter: QPainter, indice: int, candle: CandleDeltaTela) -> None:
        texto = self.texto_da_hora(candle)
        largura = self._fm_numero.horizontalAdvance(texto) + 4
        # Ancorado na PROPRIA coluna, e nao centrado sobre a borda dela: o
        # rotulo tem de caber inteiro dentro da area que rola, senao os pixels
        # que sobram para fora ficam parados enquanto o resto anda.
        caixa = QRect(
            self.eixo.x_da_coluna(indice),
            self.area_plot.bottom() + 1,
            largura,
            ALTURA_EIXO_TEMPO - 1,
        )
        if caixa.right() > self.area_plot.right():
            return  # F8: o que nao cabe INTEIRO nao entra, e nada e rotacionado
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, texto)


def _degrau_1_2_5(valor: int) -> int:
    """Menor 1/2/5 x 10^k que cobre `valor` — a mesma serie do DOM e da matriz.

    Duplicada de proposito: extrair quatro linhas para um modulo comum criaria
    um `utilidades` que atrai tudo. Se aparecer um quarto uso, sobe.
    """
    if valor <= 1:
        return 1
    escala = 1
    while escala < valor:
        for m in (2, 5, 10):
            if m * escala >= valor:
                return m * escala
        escala *= 10
    return escala


def _incremento_de(escala: int) -> int:
    """Passo redondo das linhas de grade, derivado da escala 1-2-5.

    Sempre um 1 x 10^k ou 5 x 10^k — nunca 2,5 nem 3,33. Um incremento
    "quebrado" obrigaria a ler o rotulo para saber onde se esta, que e
    exatamente o que este eixo existe para evitar.
    """
    if escala <= 1:
        return 1
    passo = 1
    while passo * 10 <= escala:
        passo *= 10
    # `escala` e sempre 1, 2 ou 5 vezes uma potencia de dez (`_degrau_1_2_5`).
    # Mantissa 2 ou 5 -> o incremento e a propria potencia; mantissa 1 -> e
    # metade dela, que continua sendo 5 x 10^(k-1).
    if escala // passo >= 2:
        return passo
    return max(1, passo // 2)
