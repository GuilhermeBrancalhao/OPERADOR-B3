"""Bookmap — a liquidez do book ao longo do tempo, com os negocios por cima.

`design/direcao_visual.md` §6 fase 5, item 13. O eixo vertical e preco, o
horizontal e tempo, e a intensidade de cada celula e a quantidade ofertada
naquele preco naquele instante. E a peca mais cara do produto e a que
concentra tres armadilhas que este projeto ja pagou caro em outros lugares.

## Armadilha 1 — a estrutura que cresce com o pregao (a NONA CASA)

Um heatmap de liquidez e, na forma ingenua, um `dict[(tempo, preco)] -> qty`
que so aumenta enquanto o pregao anda. E exatamente o defeito que este
projeto encontrou em **oito arquivos** ao longo de cinco auditorias, e o
criterio de reconhecimento esta escrito no docstring de
`fluxopro/gravacao/gravador.py`:

> *"qual grandeza limita o `len` disto, e ela para de crescer enquanto o
> pregao continua?"*  Se a resposta contiver "numero de eventos", e a mesma
> casa.

Aqui a resposta e **a geometria da janela visivel, e nada mais**:

| estrutura | `len` | limitada por |
|---|---|---|
| `_plano` | `n_niveis * _stride` | altura x largura da area de heatmap |
| `_mid`, `_pico_qty`, `_pico_ticks`, `_neg_compra`, `_neg_venda` | `n_cols` | largura da area |
| `_negocios_coluna` | <= `n_niveis` | altura da area |

Todas sao realocadas em `ao_redimensionar` e **nenhuma tem chave derivada de
preco ou de timestamp** — indexar por preco faria o `len` crescer com o range
do dia, indexar por tempo faria crescer com a duracao do pregao. Sao as duas
formas do mesmo erro. `tests/test_ui_bookmap.py` roda 1.000 e 100.000 eventos
e exige o mesmo `len` em toda colecao de instancia, **descendo nos objetos
aninhados**, porque o defeito classico deste projeto era um `dict -> list`
cujo `len` de topo valia 1 com um milhao de itens dentro.

Sai historia pela esquerda em vez de acumular: quando um balde de tempo
fecha, o plano inteiro anda uma coluna (uma unica `memmove` — ver
`_fechar_coluna`) e a coluna mais antiga **e esquecida**. O produto nao
guarda o pregao; guarda a janela. Quem quiser o pregao inteiro tem
`fluxopro/gravacao/`, que e onde essa responsabilidade mora.

## Armadilha 2 — a escala de intensidade

§3 deste projeto tem uma lei medida: *"escala que desaparece e perda; escala
que sobrevive errada e mentira"*, e uma correcao que ja teve de ser aplicada
quatro vezes no HUD: **grandeza de variacao enorme desenhada como comprimento
(ou como cor) — tire a grandeza da geometria em vez de procurar uma escala
melhor.** Liquidez de book varre ordens de magnitude: 1 lote e 4.000 lotes
convivem na mesma tela.

O modo de falha que interessa e o **temporal**, que foi o mais teimoso no
HUD: um heatmap com auto-escala (o `autoLevels` de qualquer biblioteca de
imagem) faz o eixo se mover enquanto o valor fica parado. A mesma parede de
800 lotes fica escura as 10h e clara as 15h porque o maximo da janela mudou —
e nao ha na tela nenhuma segunda barra que denuncie. **Isto aqui nao tem
auto-escala e nao pode passar a ter**: `degrau_de` e uma funcao de modulo,
pura, sem acesso a estado nenhum, e `PISOS_LIQUIDEZ` e uma escada absoluta em
lotes. Uma cor significa hoje o que significava ontem e o que vai significar
no print que circular amanha.

O que sobra da grandeza fora da cor, que e a parte "tire da geometria":

* a **escada carimbada** na banda de escala — nove blocos PREENCHIDOS (a
  forma que atravessa o canal, ver `PainelMatriz._chip`) com os pisos
  ancorados em tres rotulos grandes, e nao nove rotulos pequenos;
* o **pico da janela** como NUMERO alinhado a direita com unidade fixa — a
  forma que §3.4 declara para grandeza sem teto;
* o **leitor de celula** (`leitura_da_celula`), que devolve a faixa
  `[piso, teto)` lida do proprio byte desenhado. Ele nao pode contradizer o
  pixel porque le a mesma fonte que o pixel.

## Armadilha 3 — o modo sem cor

Num heatmap isso e dificil e obrigatorio. Em `tokens.PALETA_SEM_COR` o eixo
direcional colapsa numa cor so, entao **a cor deixa de dizer bid ou ask** — e
a rampa cinza continua dizendo a intensidade, que e a informacao que o
heatmap existe para dar.

O lado passa a viver na **posicao**, e a posicao so e um portador de verdade
se a referencia estiver DESENHADA: por isso a trilha do meio (`_desenhar_meio`)
e uma linha real atravessando a janela, com contorno escuro por baixo para ter
borda contra qualquer degrau da rampa. Bid fica abaixo dela, ask acima, por
definicao de book — e `test_ui_bookmap.py` prova isso pela geometria
compartilhada (`GeometriaBookmap.y_do_meio`), nao por inspecao de pixel.

## Por que NAO `pyqtgraph.ImageItem`

§2 mediu `ImageItem` a 5,12 ms / 195 fps para 200x600 e §6 escreveu o nome
dele no plano. Medido de novo aqui, o numero de §2 e o do **quadro cheio**:
`setImage` reenvia as 120.000 celulas a cada quadro porque a `QGraphicsScene`
nao tem repintura parcial util para este caso — e §2 tambem mediu que
`QGraphicsScene` custa 39,79 ms no footprint pelo mesmo motivo.

O Achado 1 de §2 e explicito: *"o toolkit quase nao importa; a estrategia de
desenho importa 40x"*. Medido nesta maquina, com a mesma carga:

| caminho | p50 | p95 |
|---|---|---|
| `QPainter.drawImage` do plano inteiro (600 colunas) | 4,23 ms | 6,25 ms |
| **`QPainter.drawImage` de UMA coluna (o caminho real)** | **0,137 ms** | **0,159 ms** |
| `memmove` do plano ao fechar o balde (4x/s, nao por quadro) | 0,127 ms | 0,287 ms |

O caminho que este painel realmente roda e o de 0,137 ms, **31x mais barato
que o numero de §2** — e o quadro cheio so acontece em redimensionamento. A
`QImage` de `Format_Indexed8` embrulha a memoria do proprio `bytearray` sem
copia (verificado: mutar o `bytearray` muda a imagem), entao um quadro custa
UMA travessia Python->C++, que e a metrica do Achado 2.

O custo de adotar `pyqtgraph` seria: uma dependencia nova, **mais `numpy`**
(que hoje nao aparece em uma unica linha de `fluxopro/`), e brigar com o
`PainelDenso` — que §6 chama de "o ativo mais valioso do projeto de UI" e
cujo contrato de backing store + regiao suja e pre-requisito de merge. Trocar
um caminho 31x mais barato por duas dependencias novas para violar o contrato
da casa nao se justifica. `requirements.txt` fica como esta, com o comentario
que diz que listar dependencia que ninguem usa e mentir sobre o que o projeto
precisa — e agora ele continua verdadeiro.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import BookSnapshot, PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

# --------------------------------------------------------------------------
# A escada de intensidade — ABSOLUTA, em lotes.
# --------------------------------------------------------------------------
PISOS_LIQUIDEZ: tuple[int, ...] = (1, 2, 5, 10, 20, 50, 100, 200, 500)
"""Pisos dos nove degraus da rampa, em lotes. Escada 1-2-5, tres decadas.

Nove porque `tokens.N_DEGRAUS_INTENSIDADE` e nove: a rampa da casa ja existe,
ja foi medida em contraste, e inventar uma decima cor abriria a discussao de
token novo (que §3 exige recalcular). A escada 1-2-5 e a mesma de
`_degrau_1_2_5` no HUD e na matriz — o produto tem UMA quantizacao de
magnitude, nao tres.

**Este numero e absoluto e tem de continuar sendo.** No dia em que ele virar
`max(janela)`, a mesma parede muda de cor conforme o vizinho, e o print de
ontem passa a mentir sobre o de hoje. Quem recalibrar para outro instrumento
passa outra tupla no construtor: a banda de escala desenha a escada QUE ESTA
EM USO, entao a imagem continua dizendo a verdade sozinha."""


def degrau_de(qty: int, pisos: tuple[int, ...] = PISOS_LIQUIDEZ) -> int:
    """Indice do degrau de `qty`, ou -1 se abaixo do primeiro piso.

    Funcao de MODULO, sem `self`: nao existe estado que ela possa consultar,
    e e essa impossibilidade — nao um comentario — que garante que a escala e
    absoluta. Uma mutacao que a faca depender da janela nao tem por onde.
    """
    if qty < pisos[0]:
        return -1
    indice = 0
    for k, piso in enumerate(pisos):
        if qty >= piso:
            indice = k
        else:
            break
    return indice


def faixa_do_degrau(
    degrau: int, pisos: tuple[int, ...] = PISOS_LIQUIDEZ
) -> tuple[int, int | None]:
    """`[piso, teto)` do degrau. Teto `None` no ultimo — ele nao tem teto."""
    piso = pisos[degrau]
    teto = pisos[degrau + 1] if degrau + 1 < len(pisos) else None
    return piso, teto


def texto_da_faixa(degrau: int, pisos: tuple[int, ...] = PISOS_LIQUIDEZ) -> str:
    piso, teto = faixa_do_degrau(degrau, pisos)
    if teto is None:
        return formato.formatar_inteiro(piso) + "+"
    return "%s–%s" % (
        formato.formatar_inteiro(piso),
        formato.formatar_inteiro(teto - 1),
    )


# --------------------------------------------------------------------------
# Codificacao do plano. Um byte por celula, e o byte E o indice da tabela de
# cores da `QImage` — nao existe conversao entre "o que o dado diz" e "o que
# o pixel mostra", entao os dois nao tem como divergir.
# --------------------------------------------------------------------------
VAZIO = 0
BASE_BID = 1  # 1..9
BASE_ASK = 11  # 11..19
N_TABELA = BASE_ASK + 9  # vazio + 9 bid + 9 ask (o indice 10 fica vago)

# --------------------------------------------------------------------------
# O plano dos NEGOCIOS e SEPARADO do plano da liquidez, e isso e uma correcao.
#
# Na primeira versao os negocios eram gravados no MESMO byte da liquidez, com
# o comentario "o negocio ganha do livro no mesmo pixel". O primeiro retrato
# mostrou o preco que isso cobra: com o simulador a ~560 negocios/s, a marca
# de negocio apagava o livro justamente na faixa em que o livro interessa —
# o heatmap perdia a liquidez exatamente onde ela estava sendo COMIDA, que e
# a leitura que a peca existe para dar. E `leitura_da_celula` herdava a perda:
# um byte so nao tem como dizer as duas coisas.
#
# Agora sao duas camadas: liquidez opaca embaixo, negocios com ALFA por cima.
# A de cima e `Format_Indexed8` com o indice 0 transparente na tabela de
# cores, entao ela custa a mesma unica travessia Python->C++ e nao precisa de
# mascara nem de laco por celula.
# --------------------------------------------------------------------------
NEG_VAZIO = 0
NEG_COMPRA = 1
NEG_VENDA = 2
NEG_AMBOS = 3
N_TABELA_NEG = 4

_N = tokens.N_DEGRAUS_INTENSIDADE


def codigo_bid(degrau: int) -> int:
    return BASE_BID + degrau


def codigo_ask(degrau: int) -> int:
    return BASE_ASK + degrau


def codigo_negocio(saldo: int) -> int:
    """Codigo da marca de negocio a partir do SALDO do balde naquele preco.

    Mesma convencao de `tokens.Paleta.direcional`: zero e neutro, nao
    compra. Um balde que recebeu exatamente tanto de um lado quanto do outro
    e volume sem direcao, e nao uma compra marginal."""
    if saldo > 0:
        return NEG_COMPRA
    if saldo < 0:
        return NEG_VENDA
    return NEG_AMBOS


# --------------------------------------------------------------------------
# Geometria — a UNICA fonte de coordenadas, compartilhada por desenho e teste.
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GeometriaBookmap:
    """Onde cada celula fica. Desenho e teste leem daqui, os dois.

    §3 deste projeto: *"teste que mede contra marco que o desenho nao usa e
    teatro"*. Entao nao ha aritmetica de posicao no corpo de `desenhar`: tudo
    passa por aqui, e uma mutacao em qualquer metodo desta classe muda a tela
    E derruba o teste. E o que torna a prova por mutacao possivel.
    """

    x0: int
    y0: int
    n_cols: int
    n_niveis: int
    largura_coluna: int
    altura_nivel: int

    @property
    def largura(self) -> int:
        return self.n_cols * self.largura_coluna

    @property
    def altura(self) -> int:
        return self.n_niveis * self.altura_nivel

    def area(self) -> QRect:
        return QRect(self.x0, self.y0, self.largura, self.altura)

    def x_da_coluna(self, coluna: int) -> int:
        return self.x0 + coluna * self.largura_coluna

    def y_do_nivel(self, nivel: int) -> int:
        return self.y0 + nivel * self.altura_nivel

    def rect_celula(self, nivel: int, coluna: int) -> QRect:
        return QRect(
            self.x_da_coluna(coluna),
            self.y_do_nivel(nivel),
            self.largura_coluna,
            self.altura_nivel,
        )

    def rect_coluna(self, coluna: int) -> QRect:
        return QRect(
            self.x_da_coluna(coluna), self.y0, self.largura_coluna, self.altura
        )

    def coluna_em(self, x: int) -> int | None:
        if self.largura_coluna <= 0:
            return None
        coluna = (x - self.x0) // self.largura_coluna
        return coluna if 0 <= coluna < self.n_cols else None

    def nivel_em(self, y: int) -> int | None:
        if self.altura_nivel <= 0:
            return None
        nivel = (y - self.y0) // self.altura_nivel
        return nivel if 0 <= nivel < self.n_niveis else None

    def colunas_em(self, regiao: QRect) -> tuple[int, int]:
        """`[primeira, ultima]` coluna que a regiao toca, ja saturado."""
        if self.n_cols <= 0 or self.largura_coluna <= 0:
            return 0, -1
        primeira = max(0, (regiao.left() - self.x0) // self.largura_coluna)
        ultima = min(
            self.n_cols - 1, (regiao.right() - self.x0) // self.largura_coluna
        )
        return primeira, ultima

    def y_do_meio(self, topo_ticks: int, mid_meias: int) -> int:
        """Y do meio do book, com `mid_meias` = 2x o preco medio em ticks.

        Meias-unidades porque o meio de `bid=100 / ask=101` e 100,5 e um meio
        arredondado para tick cairia sobre uma das duas pontas — a linha
        passaria a encostar no lado que ela deveria separar, e a leitura por
        posicao (o unico portador de lado no modo sem cor) perderia o caso
        mais comum de todos, que e o book com spread de um tick.
        """
        return (
            self.y0
            + (self.altura_nivel * (2 * topo_ticks - mid_meias)) // 2
            + self.altura_nivel // 2
        )

    def nivel_fracionario_do_meio(self, topo_ticks: int, mid_meias: int) -> float:
        """O mesmo ponto, em unidade de NIVEL. E o que o teste compara com a
        linha de uma celula sem precisar reimplementar a conta acima."""
        return (2 * topo_ticks - mid_meias) / 2.0


# --------------------------------------------------------------------------
# Bandas e medidas — §3.4, unidade base 4px.
# --------------------------------------------------------------------------
ALTURA_NIVEL = 4
"""Altura de um nivel de preco. NAO e `densidade.altura_linha` (18px): o
bookmap nao e uma grade de texto, e uma imagem. A 18px caberiam 40 niveis
numa metade de monitor; a 4px cabem 180, que e a profundidade em que o
desenho comeca a mostrar parede e retirada de parede."""

LARGURA_COLUNA = 4
INTERVALO_COLUNA_NS = 500_000_000
"""Meio segundo por coluna. Com 4px por coluna, 900px de janela dao ~1h52 de
book — a ordem de grandeza em que "a parede ficou la a tarde inteira" e uma
leitura possivel. Mais fino gasta a janela em segundos; mais grosso apaga a
retirada rapida de liquidez, que e o evento que o painel existe para mostrar."""

ALTURA_ESCADA = 20
ALTURA_LANE = 12
ALTURA_GUTTER_LANE = 8
"""Faixa MORTA embaixo da lane, onde mora a referencia de 50%.

Fora da barra, e nao dentro — a mesma licao de `PainelHUD.
_desenhar_barra_particionada`: uma referencia desenhada dentro da barra e
pintada por cima por um dos dois lados exatamente quando a costura esta perto
dela, que e quando ela importa."""

MARGEM = 8
ESPESSURA_COSTURA = 1
MARGEM_RECENTRALIZAR = 0.25
"""Fracao da janela, em cada ponta, que funciona como zona de conforto antes
de o eixo de preco andar. Mesmo valor e mesmo motivo do `PainelDOM`."""

BANDA_CABECALHO = 0
BANDA_ESCADA = 1
BANDA_HEATMAP = 2
BANDA_LANE = 3
N_BANDAS = 4

SEM_MID = 0
"""Sentinela de "esta coluna nao teve book". Preco em ticks e sempre positivo
num instrumento de bolsa, entao zero nao colide com dado."""

MOLDE_PRECO = "888.888,8"
GLIFO_COMPRA = "▲"
GLIFO_VENDA = "▼"


def _luminancia(cor: QColor) -> float:
    """Luminancia relativa WCAG 2.1. Usada so para escolher, entre dois
    tokens de texto que ja existem, qual deles contrasta com um degrau da
    rampa — nao para inventar cor nova."""
    canais = []
    for bruto in (cor.redF(), cor.greenF(), cor.blueF()):
        canais.append(
            bruto / 12.92 if bruto <= 0.04045 else ((bruto + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def contraste(a: QColor, b: QColor) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def texto_sobre(fundo: QColor) -> QColor:
    """O token de texto que le melhor sobre `fundo`.

    Sem isto, a etiqueta do primeiro degrau da rampa (8% de alfa, quase
    `BG_SURFACE`) sairia em `BG_BASE` — texto quase preto sobre fundo quase
    preto. O par certo depende do degrau, entao ele e escolhido, nao fixado.
    """
    if contraste(tokens.TEXT_PRIMARY, fundo) >= contraste(tokens.BG_BASE, fundo):
        return tokens.TEXT_PRIMARY
    return tokens.BG_BASE


@dataclass(frozen=True, slots=True)
class LeituraCelula:
    """O que uma celula do plano diz, lido do MESMO byte que virou pixel."""

    tipo: str  # "vazio" | "bid" | "ask"
    lado: int  # +1 bid, -1 ask, 0 nenhum
    degrau: int  # -1 quando nao ha liquidez
    piso: int
    teto: int | None
    negocio: int = 0  # NEG_VAZIO | NEG_COMPRA | NEG_VENDA | NEG_AMBOS

    @property
    def texto_liquidez(self) -> str:
        if self.tipo == "vazio":
            return "—"
        rotulo = "BID" if self.lado > 0 else "ASK"
        return rotulo + " " + texto_da_faixa(self.degrau) + " lotes"

    @property
    def texto_negocio(self) -> str:
        if self.negocio == NEG_COMPRA:
            return GLIFO_COMPRA + " negócio agressor comprador"
        if self.negocio == NEG_VENDA:
            return GLIFO_VENDA + " negócio agressor vendedor"
        if self.negocio == NEG_AMBOS:
            return "negócio sem saldo de lado"
        return ""

    @property
    def texto(self) -> str:
        """As DUAS camadas na mesma frase.

        Antes isto era impossivel por construcao: o byte guardava uma ou
        outra, e o readout herdava a perda do desenho."""
        partes = [self.texto_liquidez]
        if self.texto_negocio:
            partes.append(self.texto_negocio)
        return "  ·  ".join(partes)


VAZIA = LeituraCelula("vazio", 0, -1, 0, None)


def ler_liquidez(codigo: int, negocio: int = 0) -> LeituraCelula:
    """Decodifica um byte do plano de liquidez, com o byte do plano de cima.

    Existe como funcao livre para que o teste possa provar a ida-e-volta sem
    montar painel — e para que o leitor de celula do painel nao tenha uma
    SEGUNDA tabela de significado, que e como um readout passa a contradizer
    o pixel que ele descreve.
    """
    if BASE_BID <= codigo < BASE_BID + _N:
        degrau = codigo - BASE_BID
        piso, teto = faixa_do_degrau(degrau)
        return LeituraCelula("bid", 1, degrau, piso, teto, negocio)
    if BASE_ASK <= codigo < BASE_ASK + _N:
        degrau = codigo - BASE_ASK
        piso, teto = faixa_do_degrau(degrau)
        return LeituraCelula("ask", -1, degrau, piso, teto, negocio)
    return LeituraCelula("vazio", 0, -1, 0, None, negocio)


class PainelBookmap(PainelDenso):
    """Heatmap de liquidez + negocios, limitado por construcao a janela visivel."""

    def __init__(
        self,
        grid: PriceGrid,
        symbol: str = "",
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        intervalo_coluna_ns: int = INTERVALO_COLUNA_NS,
        pisos: tuple[int, ...] = PISOS_LIQUIDEZ,
        altura_nivel: int = ALTURA_NIVEL,
        largura_coluna: int = LARGURA_COLUNA,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.symbol = symbol
        self.densidade = densidade
        self.paleta = paleta
        self.intervalo_coluna_ns = max(1, intervalo_coluna_ns)
        self.pisos = pisos
        if len(pisos) != _N:
            raise ValueError(
                "a escada precisa de %d pisos, um por degrau da rampa" % _N
            )

        self._medir(densidade)

        self.geometria = GeometriaBookmap(0, 0, 0, 0, largura_coluna, altura_nivel)
        #: Ligado SO durante `aplicar_densidade`. Um parametro em
        #: `ao_redimensionar` mudaria a assinatura que `PainelDenso` chama por
        #: evento de resize; uma flag de escopo curto mantem o caminho quente
        #: intacto e o reprojeto explicitamente excepcional.
        self._reprojetar = False
        self._bandas: list[QRect] = [QRect() for _ in range(N_BANDAS)]

        # --- o plano. Um byte por celula, `n_niveis` linhas de `_stride`.
        # Linha 0 = preco MAIS ALTO, coluna `n_cols-1` = agora. `_stride` e
        # arredondado para multiplo de 4 porque a `QImage` exige scanline
        # alinhada; os bytes de sobra nunca sao desenhados.
        self._plano = bytearray()
        self._plano_neg = bytearray()
        self._stride = 0
        self._imagem: QImage | None = None
        self._imagem_neg: QImage | None = None

        # --- vetores por coluna. `len` = numero de colunas visiveis, ponto.
        self._mid: list[int] = []
        self._pico_qty: list[int] = []
        self._pico_ticks: list[int] = []
        self._neg_compra: list[int] = []
        self._neg_venda: list[int] = []

        # --- estado do balde corrente. `len` <= n_niveis: a coluna corrente
        # e reescrita do book a cada quadro, e os negocios que ja cairam nela
        # precisam sobreviver a essa reescrita.
        self._negocios_coluna: dict[int, int] = {}
        self._t_coluna_ns: int | None = None

        self._topo_ticks: int | None = None
        self._pico_janela = 0
        self._pico_janela_ticks = 0
        self._colunas_fechadas = 0

        self._cursor: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 220)
        self._montar_tabela()

    # -------------------------------------------------------- densidade
    def _medir(self, densidade: tokens.Densidade) -> None:
        """O que a densidade define. Construtor e `aplicar_densidade` chamam
        ESTA — a largura do eixo sai da metrica, e duas copias da conta
        divergiriam na primeira mudanca do molde."""
        self._fm_grade = QFontMetrics(tokens.fonte_numero(densidade.fonte_grade))
        self._fm_rotulo = QFontMetrics(tokens.fonte_rotulo())
        self._largura_eixo = self._fm_grade.horizontalAdvance(MOLDE_PRECO) + 2 * MARGEM

    def aplicar_densidade(self, nova: tokens.Densidade) -> None:
        """Troca a densidade a quente. O PLANO sobrevive.

        Reconstruir o painel jogava fora o heatmap inteiro — que aqui e o
        produto, nao um detalhe: e o unico lugar da tela onde a liquidez tem
        historia. Mutar so `self.densidade` deixaria `_largura_eixo`, medido
        no construtor com a fonte antiga, recortando a calha de precos
        desenhados com a fonte nova.

        `ao_redimensionar` e chamado em seguida porque a banda do cabecalho e
        a largura util saem dos dois valores que acabaram de mudar
        (`altura_cabecalho` e `_largura_eixo`); ele reflui o plano pela mesma
        rotina que uma janela redimensionada usa.
        """
        if nova is self.densidade:
            return
        self.densidade = nova
        self._medir(nova)
        self._reprojetar = True
        try:
            self.ao_redimensionar(self.width(), self.height())
        finally:
            self._reprojetar = False
        self.marcar_tudo_sujo()

    # ------------------------------------------------------------ paleta
    def _montar_tabela(self) -> None:
        """Tabela de cores da `QImage`, montada UMA vez.

        Em `PALETA_SEM_COR` os dois lados recebem `RAMPA_NEUTRA` — a mesma
        rampa cinza para bid e para ask. Nao e descuido: e o que o modo sem
        cor significa. A intensidade (que e a informacao do heatmap)
        sobrevive inteira; o lado migra para a posicao contra a trilha do
        meio, que e desenhada justamente para poder receber essa carga.
        """
        if self.paleta.tem_cor:
            rampa_bid, rampa_ask = tokens.RAMPA_COMPRA, tokens.RAMPA_VENDA
        else:
            rampa_bid = rampa_ask = tokens.RAMPA_NEUTRA
        self.rampa_bid = rampa_bid
        self.rampa_ask = rampa_ask

        tabela = [tokens.BG_SURFACE.rgb()] * N_TABELA
        for k in range(_N):
            tabela[codigo_bid(k)] = rampa_bid[k].rgb()
            tabela[codigo_ask(k)] = rampa_ask[k].rgb()
        self._tabela = tabela

        # Camada de cima. O indice 0 tem ALFA ZERO — e o que faz a liquidez
        # continuar visivel em toda celula que nao teve negocio, com uma
        # unica `drawImage` e sem mascara nem laco por celula.
        #
        # As cores sao as CHEIAS, mais saturadas que qualquer degrau da rampa
        # (que para em 0,60 de alfa): o negocio "estoura" acima da escada de
        # proposito, porque o que ACONTECEU vale mais que o que estava
        # ofertado. E `--neutral` e o token de "volume sem direcao, imbalance
        # nulo" (§3.2) — que e exatamente o que um balde empatado e. NAO
        # `TEXT_PRIMARY`: ele e a cor da trilha do meio, e duas coisas
        # diferentes com a mesma cor no mesmo pixel foi o defeito que o
        # primeiro retrato mostrou.
        tabela_neg = [0] * N_TABELA_NEG
        tabela_neg[NEG_COMPRA] = self.paleta.compra.rgba()
        tabela_neg[NEG_VENDA] = self.paleta.venda.rgba()
        tabela_neg[NEG_AMBOS] = self.paleta.neutro.rgba()
        self._tabela_neg = tabela_neg

        if self._imagem is not None:
            self._imagem.setColorTable(tabela)
        if self._imagem_neg is not None:
            self._imagem_neg.setColorTable(tabela_neg)

    # --------------------------------------------------------- geometria
    def ao_redimensionar(self, largura: int, altura: int) -> None:
        y = 0
        for indice, h in (
            (BANDA_CABECALHO, self.densidade.altura_cabecalho),
            (BANDA_ESCADA, ALTURA_ESCADA),
        ):
            self._bandas[indice] = QRect(0, y, largura, h)
            y += h

        util_altura = max(0, altura - y - ALTURA_LANE - ALTURA_GUTTER_LANE)
        util_largura = max(0, largura - self._largura_eixo)
        n_niveis = util_altura // self.geometria.altura_nivel
        n_cols = util_largura // self.geometria.largura_coluna

        self._bandas[BANDA_HEATMAP] = QRect(
            0, y, util_largura, n_niveis * self.geometria.altura_nivel
        )
        self._bandas[BANDA_LANE] = QRect(
            0,
            y + n_niveis * self.geometria.altura_nivel,
            util_largura,
            ALTURA_LANE + ALTURA_GUTTER_LANE,
        )

        nova = GeometriaBookmap(
            0,
            y,
            n_cols,
            n_niveis,
            self.geometria.largura_coluna,
            self.geometria.altura_nivel,
        )
        if (nova.n_cols, nova.n_niveis) != (
            self.geometria.n_cols,
            self.geometria.n_niveis,
        ):
            self.geometria = nova
            self._realocar(preservar=self._reprojetar)
        else:
            self.geometria = nova

    def _realocar(self, preservar: bool = False) -> None:
        """Realoca TODA estrutura para a janela nova, e descarta o resto.

        Encolher joga fora o excedente em vez de guardar "para quando a
        janela crescer de novo" — guardar seria exatamente a estrutura que
        cresce com o passado, so que com nome de cache. E a mesma decisao de
        `PainelMatriz._redimensionar_slots`, pelo mesmo motivo.

        `preservar` REPROJETA o que ja estava desenhado em vez de zerar, e e
        usado por um chamador so: `aplicar_densidade`. A distincao nao e
        preciosismo. Redimensionar a janela e o operador dizendo quanto de
        tela quer; trocar a densidade e ele dizendo com que corpo quer LER O
        MESMO periodo, e apagar o heatmap ai e responder outra pergunta.

        O reprojeto e ancorado como o painel ja e: linha 0 e sempre
        `_topo_ticks` (o preco mais alto) e a ultima coluna e sempre agora,
        entao as linhas casam pelo TOPO e as colunas pela DIREITA. O que nao
        cabe cai — pela mesma regra de sempre, e nao ha "cache" nenhum
        guardado fora da tela.
        """
        n_niveis_antes = (
            len(self._plano) // self._stride if self._stride > 0 else 0
        )
        plano_antes, neg_antes, stride_antes = (
            self._plano,
            self._plano_neg,
            self._stride,
        )
        cols_antes = len(self._mid)
        vetores_antes = (
            self._mid,
            self._pico_qty,
            self._pico_ticks,
            self._neg_compra,
            self._neg_venda,
        )
        g = self.geometria
        self._stride = (g.n_cols + 3) // 4 * 4
        self._plano = bytearray(self._stride * g.n_niveis)
        self._plano_neg = bytearray(self._stride * g.n_niveis)
        self._imagem = self._imagem_neg = None
        if g.n_cols > 0 and g.n_niveis > 0:
            for atributo, plano, tabela in (
                ("_imagem", self._plano, self._tabela),
                ("_imagem_neg", self._plano_neg, self._tabela_neg),
            ):
                imagem = QImage(
                    plano, g.n_cols, g.n_niveis, self._stride, QImage.Format.Format_Indexed8
                )
                imagem.setColorTable(tabela)
                setattr(self, atributo, imagem)
        self._mid = [SEM_MID] * g.n_cols
        self._pico_qty = [0] * g.n_cols
        self._pico_ticks = [0] * g.n_cols
        self._neg_compra = [0] * g.n_cols
        self._neg_venda = [0] * g.n_cols
        self._negocios_coluna = {}
        self._pico_janela = 0
        self._pico_janela_ticks = 0
        self._cursor = None

        if not preservar:
            return
        linhas = min(n_niveis_antes, g.n_niveis)
        colunas = min(cols_antes, g.n_cols)
        if linhas <= 0 or colunas <= 0:
            return
        for linha in range(linhas):
            o = linha * stride_antes + (cols_antes - colunas)
            d = linha * self._stride + (g.n_cols - colunas)
            self._plano[d : d + colunas] = plano_antes[o : o + colunas]
            self._plano_neg[d : d + colunas] = neg_antes[o : o + colunas]
        for destino, origem in zip(
            (
                self._mid,
                self._pico_qty,
                self._pico_ticks,
                self._neg_compra,
                self._neg_venda,
            ),
            vetores_antes,
        ):
            destino[g.n_cols - colunas :] = origem[cols_antes - colunas :]

    @property
    def _coluna_atual(self) -> int:
        return self.geometria.n_cols - 1

    def _nivel_do_tick(self, ticks: int) -> int | None:
        if self._topo_ticks is None:
            return None
        nivel = self._topo_ticks - ticks
        return nivel if 0 <= nivel < self.geometria.n_niveis else None

    def _tick_do_nivel(self, nivel: int) -> int | None:
        if self._topo_ticks is None:
            return None
        return self._topo_ticks - nivel

    # ------------------------------------------------------------- dados
    def aplicar(
        self,
        livro: BookSnapshot | None = None,
        ultimo_preco: int | None = None,
        novos_trades=(),
        agora_ns: int | None = None,
    ) -> None:
        """Absorve o quadro. Chamado pela janela, uma vez por quadro.

        `novos_trades` sao itens com `price`, `qty` e `agressor` (+1/-1/0) —
        o formato de `ui/ponte.ItemTape`. O painel nao assina o barramento:
        quem le o barramento e a ponte, e o painel le a ponte no seu proprio
        relogio (§6 fase 0, item 3).
        """
        if self.geometria.n_cols <= 0 or self.geometria.n_niveis <= 0:
            return

        referencia = ultimo_preco
        if referencia is None and livro is not None:
            referencia = _referencia_do_livro(livro)
        if self._topo_ticks is None:
            if referencia is None:
                return
            self._topo_ticks = referencia + self.geometria.n_niveis // 2
            self.marcar_tudo_sujo()

        if agora_ns is None:
            agora_ns = livro.timestamp_ns if livro is not None else None
        if agora_ns is not None:
            if self._t_coluna_ns is None:
                self._t_coluna_ns = agora_ns
            while agora_ns - self._t_coluna_ns >= self.intervalo_coluna_ns:
                self._fechar_coluna()
                self._t_coluna_ns += self.intervalo_coluna_ns

        if referencia is not None:
            self._talvez_recentralizar(referencia)
        if novos_trades:
            self._absorver_trades(novos_trades)
        if livro is not None:
            self._absorver_livro(livro)
        self._sujar_coluna_atual()

    def _marcar_unico(self, rect: QRect) -> None:
        """Marca `rect` a menos que ele JA esteja marcado neste quadro.

        Sem esta deduplicacao o painel se auto-sabota. `aplicar` suja sempre
        a MESMA coluna (a corrente), e a janela pode chama-lo mais de uma vez
        entre dois quadros — o relogio do painel e de 16 ms e o barramento
        nao espera por ele. Dezesseis chamadas viram 32 retangulos, 32 e o
        `MAX_RETANGULOS_SUJOS` do `PainelDenso`, e a partir dai a base
        colapsa tudo em `marcar_tudo_sujo` e o painel volta ao **quadro
        cheio**. Ou seja: o ganho de 40x da regiao suja iria embora por
        marcar dezesseis vezes o mesmo retangulo.

        Medido: com a marcacao ingenua, o p95 do retrato foi 8,4 ms; com a
        deduplicacao, 1,4 ms.
        """
        if rect in self._sujos:
            return
        self.marcar_sujo(rect)

    def _sujar_coluna_atual(self) -> None:
        coluna = self.geometria.rect_coluna(self._coluna_atual)
        self._marcar_unico(coluna)
        self._marcar_unico(
            QRect(
                coluna.left(),
                self._bandas[BANDA_LANE].top(),
                coluna.width(),
                ALTURA_LANE,
            )
        )

    def _fechar_coluna(self) -> None:
        """Fecha o balde: o plano anda uma coluna e o passado mais velho some.

        UMA `memmove` por linha e nada mais — 0,127 ms medidos para 200
        linhas, quatro vezes por segundo. E o unico lugar do modulo onde
        historia e descartada, e ele descarta por CONSTRUCAO: nao ha
        condicao, nao ha limite configuravel, nao ha "guarda se couber". A
        coluna que sai da janela deixa de existir.
        """
        g = self.geometria
        if g.n_cols <= 0:
            return
        largura = g.n_cols
        for plano in (self._plano, self._plano_neg):
            for linha in range(g.n_niveis):
                base = linha * self._stride
                plano[base : base + largura - 1] = plano[base + 1 : base + largura]
                plano[base + largura - 1] = 0
        for vetor, vazio in (
            (self._mid, SEM_MID),
            (self._pico_qty, 0),
            (self._pico_ticks, 0),
            (self._neg_compra, 0),
            (self._neg_venda, 0),
        ):
            del vetor[0]
            vetor.append(vazio)
        self._negocios_coluna = {}
        self._colunas_fechadas += 1
        self._recalcular_pico()
        self.rolar(-g.largura_coluna, 0, g.area())
        self.marcar_sujo(self._bandas[BANDA_CABECALHO])
        self.marcar_sujo(self._bandas[BANDA_LANE])
        self._cursor = None

    def _recalcular_pico(self) -> None:
        """O pico da JANELA, recalculado quando a janela anda.

        O(n_cols) quatro vezes por segundo, e nao O(celulas) por quadro. E o
        recalculo tem de existir: guardar so o maximo corrente faria o numero
        subir e nunca descer, que e uma catraca — o defeito 4 do HUD, o mais
        teimoso deles, so que na banda de cima em vez de na barra.
        """
        pico, ticks = 0, 0
        for k, valor in enumerate(self._pico_qty):
            # `_nivel_do_tick` e o mesmo gate do desenho: uma parede que o
            # eixo de preco deixou para tras nao volta a ser anunciada so
            # porque continua dentro da janela de TEMPO.
            #
            # E ela e ZERADA, nao apenas ignorada. Filtrar na leitura
            # deixava o valor velho no vetor, e o `>` de `_absorver_livro`
            # entao recusava todo pico novo daquela coluna: depois de um
            # salto de preco o cabecalho ficava em branco ate a coluna
            # rolar para fora — um campo vazio com dado disponivel.
            if valor and self._nivel_do_tick(self._pico_ticks[k]) is None:
                self._pico_qty[k] = 0
                self._pico_ticks[k] = 0
                continue
            if valor > pico:
                pico, ticks = valor, self._pico_ticks[k]
        self._pico_janela = pico
        self._pico_janela_ticks = ticks

    def _talvez_recentralizar(self, preco: int) -> None:
        g = self.geometria
        assert self._topo_ticks is not None
        nivel = self._topo_ticks - preco
        margem = int(g.n_niveis * MARGEM_RECENTRALIZAR)
        if margem <= 0 or margem <= nivel < g.n_niveis - margem:
            return
        novo_topo = preco + g.n_niveis // 2
        delta = novo_topo - self._topo_ticks
        # O eixo muda ANTES da purga: `_recalcular_pico` pergunta ao
        # `_nivel_do_tick` quem ainda esta visivel, e a resposta tem de ser
        # a do eixo NOVO.
        self._topo_ticks = novo_topo
        self._deslocar_precos(delta)
        anterior = self._pico_janela
        self._recalcular_pico()
        if self._pico_janela != anterior:
            self.marcar_sujo(self._bandas[BANDA_CABECALHO])

    def _deslocar_precos(self, delta_niveis: int) -> None:
        """Move o plano inteiro `delta_niveis` para BAIXO (preco subindo).

        Linha-maior deixa isto ser uma unica fatia contigua: as linhas sao
        blocos vizinhos na memoria, entao deslocar N linhas e um `memmove` so.
        Foi por isso que o plano ficou linha-maior e nao coluna-maior — a
        rolagem VERTICAL e a operacao cara, e ela acontece com preco andando,
        que num pregao rapido e frequente.
        """
        g = self.geometria
        if delta_niveis == 0 or g.n_niveis <= 0:
            return
        if abs(delta_niveis) >= g.n_niveis:
            for plano in (self._plano, self._plano_neg):
                plano[:] = bytes(len(plano))
            self.marcar_tudo_sujo()
            return
        corte = abs(delta_niveis) * self._stride
        for plano in (self._plano, self._plano_neg):
            if delta_niveis > 0:
                plano[corte:] = plano[: len(plano) - corte]
                plano[:corte] = bytes(corte)
            else:
                plano[: len(plano) - corte] = plano[corte:]
                plano[len(plano) - corte :] = bytes(corte)
        self._negocios_coluna = {
            nivel + delta_niveis: saldo
            for nivel, saldo in self._negocios_coluna.items()
            if 0 <= nivel + delta_niveis < g.n_niveis
        }
        self.rolar(0, delta_niveis * g.altura_nivel, g.area())

    def _absorver_livro(self, livro: BookSnapshot) -> None:
        g = self.geometria
        coluna = self._coluna_atual
        if coluna < 0:
            return
        # Limpa a coluna corrente e reescreve do book: a coluna mostra o
        # livro como ele estava no fim do balde, e nao a soma do balde. Somar
        # contaria a mesma oferta parada varias vezes e faria liquidez PARADA
        # parecer liquidez CHEGANDO, que e o contrario do que o painel diz.
        for linha in range(g.n_niveis):
            self._plano[linha * self._stride + coluna] = VAZIO

        pico, pico_ticks = 0, 0
        for niveis, codificar in ((livro.bids, codigo_bid), (livro.asks, codigo_ask)):
            for nivel in niveis:
                linha = self._nivel_do_tick(nivel.price)
                if linha is None:
                    # Fora da faixa de preco visivel. Nao entra no plano E
                    # nao entra no pico: o cabecalho chegou a anunciar
                    # `PICO 2.310 @ 5.110,0` com o eixo indo so ate 5.038 —
                    # um numero verdadeiro sobre uma parede que o leitor nao
                    # tinha como achar na tela. Readout que cita o que nao
                    # esta desenhado e a mesma falha do readout que
                    # contradiz o pixel, com o sinal trocado.
                    continue
                degrau = degrau_de(nivel.qty, self.pisos)
                if degrau < 0:
                    continue
                self._plano[linha * self._stride + coluna] = codificar(degrau)
                if nivel.qty > pico:
                    pico, pico_ticks = nivel.qty, nivel.price

        if pico > self._pico_qty[coluna]:
            self._pico_qty[coluna] = pico
            self._pico_ticks[coluna] = pico_ticks
            if pico > self._pico_janela:
                self._pico_janela = pico
                self._pico_janela_ticks = pico_ticks
                self.marcar_sujo(self._bandas[BANDA_CABECALHO])
        if livro.bids and livro.asks:
            self._mid[coluna] = livro.bids[0].price + livro.asks[0].price
        elif livro.bids:
            self._mid[coluna] = 2 * livro.bids[0].price
        elif livro.asks:
            self._mid[coluna] = 2 * livro.asks[0].price

    def _absorver_trades(self, trades) -> None:
        g = self.geometria
        coluna = self._coluna_atual
        if coluna < 0:
            return
        for trade in trades:
            linha = self._nivel_do_tick(trade.price)
            agressor = getattr(trade, "agressor", 0)
            if agressor > 0:
                self._neg_compra[coluna] += trade.qty
            elif agressor < 0:
                self._neg_venda[coluna] += trade.qty
            if linha is None:
                continue
            # SALDO do balde naquele preco, e nao "houve dos dois lados".
            # A primeira versao guardava o codigo e promovia para AMBOS
            # assim que chegasse um do outro lado — e o retrato mostrou o
            # resultado: num balde de meio segundo quase todo preco recebe
            # os dois lados, entao a marca ficava BRANCA em quase toda parte
            # e a direcao da agressao, que e a informacao, sumia. Pior, a
            # marca branca virou indistinguivel da trilha do meio, que
            # tambem e branca. Com o saldo, a marca diz de que lado o balde
            # pendeu, e so o empate exato — que e raro e significa mesmo
            # "volume sem direcao" — fica neutro.
            self._negocios_coluna[linha] = self._negocios_coluna.get(linha, 0) + (
                trade.qty * (1 if agressor > 0 else -1 if agressor < 0 else 0)
            )
            self._plano_neg[linha * self._stride + coluna] = codigo_negocio(
                self._negocios_coluna[linha]
            )

    # ---------------------------------------------------------- consultas
    def leitura_da_celula(self, nivel: int, coluna: int) -> LeituraCelula:
        """O que o pixel `(nivel, coluna)` esta dizendo — do proprio byte."""
        g = self.geometria
        if not (0 <= nivel < g.n_niveis and 0 <= coluna < g.n_cols):
            return VAZIA
        endereco = nivel * self._stride + coluna
        return ler_liquidez(self._plano[endereco], self._plano_neg[endereco])

    @property
    def pico_janela(self) -> tuple[int, int]:
        """`(lotes, ticks)` do maior nivel ofertado ainda visivel."""
        return self._pico_janela, self._pico_janela_ticks

    @property
    def colunas_fechadas(self) -> int:
        """Contador de baldes fechados na sessao — o CONTADOR, nao a
        retencao. Um `int` que anda nao e uma colecao que cresce."""
        return self._colunas_fechadas

    def horizonte_ns(self) -> int:
        return self.geometria.n_cols * self.intervalo_coluna_ns

    # ----------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        for indice, banda in enumerate(self._bandas):
            if banda.isValid() and banda.intersects(regiao):
                _DESENHOS[indice](self, painter, banda, regiao)
        eixo = QRect(
            self.geometria.largura,
            self._bandas[BANDA_HEATMAP].top(),
            self.width() - self.geometria.largura,
            self.height() - self._bandas[BANDA_HEATMAP].top(),
        )
        if eixo.isValid() and eixo.intersects(regiao):
            self._desenhar_eixo(painter, eixo, regiao)

    # -- cabecalho ---------------------------------------------------------
    def _desenhar_cabecalho(
        self, painter: QPainter, banda: QRect, regiao: QRect
    ) -> None:
        painter.fillRect(banda, tokens.BG_RAISED)
        interno = banda.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        titulo = "BOOKMAP" + (" · " + self.symbol if self.symbol else "")
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            titulo,
        )
        # O pico como NUMERO, alinhado a direita, unidade fixa — a forma que
        # §3.4 declara para grandeza sem teto. E o que continua legivel
        # quando a rampa satura: a cor diz "500+", o numero diz 4.120.
        if self._pico_janela > 0:
            painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 600))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                interno,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "PICO %s @ %s"
                % (
                    formato.formatar_inteiro(self._pico_janela),
                    formato.preco_completo(self.grid, self._pico_janela_ticks),
                ),
            )

    # -- escada ------------------------------------------------------------
    def _desenhar_escada(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        """A escada de intensidade, CARIMBADA na propria imagem.

        Nove blocos preenchidos, e nao nove rotulos: `PainelMatriz._chip`
        mediu que compressao com perdas ataca borda fina de alto contraste e
        poupa area chapada, entao um bloco de 34x12 sobrevive onde um `500`
        de 10px vira borrao.

        Os pisos vao em TRES ancoras grandes (primeiro, meio, ultimo) e nao
        em nove pequenas. Uma escada 1-2-5 fica determinada por tres pontos —
        e tres rotulos legiveis valem mais que nove ilegiveis, que e a mesma
        troca que o HUD fez ao remover a escala em vez de engordar o rotulo.
        """
        painter.fillRect(banda, tokens.BG_SURFACE)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        rotulo = "LIQUIDEZ"
        largura_rotulo = self._fm_rotulo.horizontalAdvance(rotulo) + MARGEM
        painter.drawText(
            QRect(MARGEM, banda.top(), largura_rotulo, banda.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            rotulo,
        )

        x = MARGEM + largura_rotulo
        altura = banda.height() - 6
        y = banda.top() + 3
        largura_chip = max(24, min(44, (banda.width() - x - 160) // _N))
        ancoras = (0, _N // 2, _N - 1)
        for k in range(_N):
            cor = self.rampa_bid[k]
            chip = QRect(x + k * largura_chip, y, largura_chip - 1, altura)
            painter.fillRect(chip, cor)
            if k in ancoras:
                painter.setFont(tokens.fonte_numero(12, 700))
                painter.setPen(texto_sobre(cor))
                painter.drawText(
                    chip,
                    Qt.AlignmentFlag.AlignCenter,
                    formato.formatar_inteiro(self.pisos[k]),
                )
        fim = x + _N * largura_chip + MARGEM
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(fim, banda.top(), max(0, banda.right() - fim), banda.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "LOTES · ESCADA ABSOLUTA",
        )

    def rects_da_escada(self) -> tuple[QRect, ...]:
        """Os nove chips, para o retrato medir retencao caixa a caixa.

        O script de retencao precisa das coordenadas exatas; digitar as
        coordenadas no script seria medir uma caixa que o desenho nao usa —
        o mesmo teatro que §3 proibe para teste."""
        banda = self._bandas[BANDA_ESCADA]
        if not banda.isValid():
            return ()
        largura_rotulo = self._fm_rotulo.horizontalAdvance("LIQUIDEZ") + MARGEM
        x = MARGEM + largura_rotulo
        largura_chip = max(24, min(44, (banda.width() - x - 160) // _N))
        altura = banda.height() - 6
        y = banda.top() + 3
        return tuple(
            QRect(x + k * largura_chip, y, largura_chip - 1, altura) for k in range(_N)
        )

    # -- heatmap -----------------------------------------------------------
    def _desenhar_heatmap(
        self, painter: QPainter, banda: QRect, regiao: QRect
    ) -> None:
        g = self.geometria
        if self._imagem is None or self._topo_ticks is None:
            self._desenhar_vazio(painter, banda)
            return
        primeira, ultima = g.colunas_em(regiao)
        if ultima < primeira:
            return
        # UMA travessia Python->C++ para todas as colunas sujas: a `QImage`
        # embrulha a memoria do `bytearray` sem copia, entao nao existe passo
        # de "montar a imagem" — o plano JA e a imagem.
        alvo = QRect(
            g.x_da_coluna(primeira),
            g.y0,
            (ultima - primeira + 1) * g.largura_coluna,
            g.altura,
        )
        fonte = QRect(primeira, 0, ultima - primeira + 1, g.n_niveis)
        painter.drawImage(alvo, self._imagem, fonte)
        if self._imagem_neg is not None:
            painter.drawImage(alvo, self._imagem_neg, fonte)
        self._desenhar_meio(painter, primeira, ultima)
        self._desenhar_cursor(painter, primeira, ultima)

    def _desenhar_vazio(self, painter: QPainter, banda: QRect) -> None:
        """§3.5 estado Vazio: a GRADE aparece, nunca um retangulo em branco.

        O trader precisa reconhecer o painel antes de o pregao abrir; um
        retangulo liso e indistinguivel de um painel quebrado."""
        g = self.geometria
        painter.fillRect(banda, tokens.BG_SURFACE)
        painter.setPen(tokens.BORDER)
        passo = max(1, g.n_niveis // 8)
        for nivel in range(0, g.n_niveis, passo):
            y = g.y_do_nivel(nivel)
            painter.drawLine(banda.left(), y, banda.right(), y)
        painter.setFont(tokens.fonte_ui(14))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            banda,
            Qt.AlignmentFlag.AlignCenter,
            "AGUARDANDO ABERTURA" + (" · " + self.symbol if self.symbol else ""),
        )

    def _desenhar_meio(self, painter: QPainter, primeira: int, ultima: int) -> None:
        """A trilha do meio do book — a referencia que carrega o LADO.

        Contorno escuro dos DOIS lados de um nucleo claro. O contorno nao e
        enfeite e os dois lados nao sao simetria: a linha atravessa celulas
        que vao de `BG_SURFACE` ate a marca de negocio em cor cheia, e
        nenhuma cor unica tem borda contra as duas pontas.

        O primeiro retrato em `PALETA_SEM_COR` mostrou por que UM lado nao
        basta. La a marca de negocio tambem e `TEXT_PRIMARY`, entao numa
        faixa de negocio denso o nucleo claro da trilha ficava branco sobre
        branco e sobrava so o traco escuro de baixo — meia linha, e meia
        linha nao e uma referencia que o olho siga. Com os dois lados, contra
        branco aparecem duas molduras escuras e contra o fundo aparece o
        nucleo claro; nao ha vizinhanca em que os tres sumam juntos.

        Isto importa mais no modo sem cor que no colorido, porque e la que a
        trilha e o UNICO portador do lado (bid abaixo, ask acima).
        """
        g = self.geometria
        assert self._topo_ticks is not None
        # UMA coluna a mais de cada lado: sem isso os segmentos verticais que
        # ligam a coluna suja as vizinhas nao seriam redesenhados, e a trilha
        # sairia picotada exatamente na fronteira da regiao suja.
        pontos: list[QPoint] = []
        for coluna in range(max(0, primeira - 1), min(g.n_cols - 1, ultima + 1) + 1):
            mid = self._mid[coluna]
            if mid == SEM_MID:
                continue
            y = g.y_do_meio(self._topo_ticks, mid)
            if not (g.y0 <= y < g.y0 + g.altura):
                continue
            # TRES pontos por coluna: o salto vertical no x da coluna, e so
            # depois o trecho horizontal. A trilha e um DEGRAU, nao uma reta
            # interpolada — interpolar diria que o meio passou por precos por
            # onde ele nao passou. E o salto tem de ser vertical de verdade:
            # ligado em diagonal de uma coluna a outra, ele espalha os pixels
            # por dois x e some quando so uma das duas colunas e redesenhada.
            x = g.x_da_coluna(coluna)
            if pontos:
                pontos.append(QPoint(x, pontos[-1].y()))
            pontos.append(QPoint(x, y))
            pontos.append(QPoint(x + g.largura_coluna - 1, y))
        if len(pontos) < 2:
            return
        # POLILINHA e nao tracinhos soltos. A primeira versao desenhava um
        # segmento horizontal por coluna e deixava os saltos verticais em
        # aberto: com o meio andando alguns ticks entre baldes, o retrato
        # mostrou pontilhado espalhado em vez de linha, e uma referencia que
        # o olho nao consegue seguir nao serve de referencia — que e o unico
        # trabalho dela no modo sem cor.
        for deslocamento, cor in (
            (-1, tokens.BG_BASE),
            (1, tokens.BG_BASE),
            (0, tokens.TEXT_PRIMARY),
        ):
            painter.setPen(cor)
            painter.drawPolyline([QPoint(p.x(), p.y() + deslocamento) for p in pontos])

    def _desenhar_cursor(self, painter: QPainter, primeira: int, ultima: int) -> None:
        if self._cursor is None:
            return
        nivel, coluna = self._cursor
        if not (primeira <= coluna <= ultima):
            return
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawRect(self.geometria.rect_celula(nivel, coluna).adjusted(0, 0, -1, -1))

    # -- lane de agressao --------------------------------------------------
    def _desenhar_lane(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        """Quanto do que foi negociado em cada balde foi agressao compradora.

        Barra particionada de altura FIXA, nunca uma barra com escala: a
        pergunta e proporcional ("de tudo que passou neste balde, quanto foi
        comprador") e proporcao tem eixo absoluto, 0 a 100%. Sem escala nao
        ha escala para o canal apagar nem comprimento para o leitor comparar
        errado. E a mesma forma de `PainelHUD._desenhar_barra_particionada`,
        de pe em vez de deitada — o produto tem duas formas de barra, e esta
        e uma delas.

        O VOLUME de cada balde nao esta aqui de proposito: e grandeza sem
        teto, e grandeza sem teto vira numero (o `PICO` do cabecalho e o
        leitor de celula), nunca comprimento.
        """
        g = self.geometria
        y = banda.top()
        faixa = QRect(banda.left(), y, banda.width(), ALTURA_LANE)
        painter.fillRect(faixa, tokens.BG_SURFACE)
        painter.fillRect(
            QRect(banda.left(), y + ALTURA_LANE, banda.width(), ALTURA_GUTTER_LANE),
            tokens.BG_SURFACE,
        )
        primeira, ultima = g.colunas_em(regiao)
        for coluna in range(primeira, ultima + 1):
            compra, venda = self._neg_compra[coluna], self._neg_venda[coluna]
            total = compra + venda
            if total <= 0:
                continue
            x = g.x_da_coluna(coluna)
            largura = g.largura_coluna
            altura_compra = int(round(ALTURA_LANE * compra / total))
            altura_compra = min(max(altura_compra, 0), ALTURA_LANE)
            corte = y + ALTURA_LANE - altura_compra
            if ALTURA_LANE - altura_compra > 0:
                painter.fillRect(
                    QRect(x, y, largura, ALTURA_LANE - altura_compra),
                    self.paleta.venda,
                )
            if altura_compra > 0:
                painter.fillRect(
                    QRect(x, corte, largura, altura_compra), self.paleta.compra
                )
            # A costura — o que mantem a particao visivel quando as duas
            # cores colapsam numa so. Mesmo papel do `LARGURA_COSTURA` do HUD.
            painter.fillRect(
                QRect(x, corte - ESPESSURA_COSTURA // 2, largura, ESPESSURA_COSTURA),
                tokens.BG_BASE,
            )

    # -- eixo de preco -----------------------------------------------------
    def _desenhar_eixo(self, painter: QPainter, eixo: QRect, regiao: QRect) -> None:
        g = self.geometria
        painter.fillRect(eixo, tokens.BG_SURFACE)
        painter.setPen(tokens.BORDER)
        painter.drawLine(eixo.left(), eixo.top(), eixo.left(), eixo.bottom())

        # A referencia de 50% da lane, FORA da lane (ver `ALTURA_GUTTER_LANE`).
        y_meio_lane = self._bandas[BANDA_LANE].top() + ALTURA_LANE // 2
        painter.setPen(tokens.BORDER_STRONG)
        painter.drawLine(eixo.left() + 1, y_meio_lane, eixo.left() + 5, y_meio_lane)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(eixo.left() + 8, y_meio_lane - 8, eixo.width() - 8, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "50%",
        )

        if self._topo_ticks is None or g.n_niveis <= 0:
            return
        passo = max(1, -(-16 // max(1, g.altura_nivel)))
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        for nivel in range(0, g.n_niveis, passo):
            ticks = self._tick_do_nivel(nivel)
            if ticks is None:
                continue
            y = g.y_do_nivel(nivel)
            estavel, vivo = formato.formatar_preco(self.grid, ticks)
            largura_vivo = self._fm_grade.horizontalAdvance(vivo)
            caixa = QRect(eixo.left() + MARGEM, y - 1, eixo.width() - 2 * MARGEM, 12)
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(caixa.left(), caixa.top(), caixa.width() - largura_vivo, caixa.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                estavel,
            )
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                caixa,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                vivo,
            )

    # ------------------------------------------------------------- cursor
    def mouseMoveEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        g = self.geometria
        posicao = evento.position().toPoint()
        nivel = g.nivel_em(posicao.y())
        coluna = g.coluna_em(posicao.x())
        novo = (nivel, coluna) if nivel is not None and coluna is not None else None
        if novo != self._cursor:
            for alvo in (self._cursor, novo):
                if alvo is not None:
                    self.marcar_sujo(g.rect_celula(*alvo).adjusted(-1, -1, 1, 1))
            self._cursor = novo
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento) -> None:  # noqa: N802
        if self._cursor is not None:
            self.marcar_sujo(self.geometria.rect_celula(*self._cursor).adjusted(-1, -1, 1, 1))
            self._cursor = None
        super().leaveEvent(evento)

    @property
    def leitura_do_cursor(self) -> LeituraCelula:
        if self._cursor is None:
            return VAZIA
        return self.leitura_da_celula(*self._cursor)


_DESENHOS = (
    PainelBookmap._desenhar_cabecalho,
    PainelBookmap._desenhar_escada,
    PainelBookmap._desenhar_heatmap,
    PainelBookmap._desenhar_lane,
)


def _referencia_do_livro(livro: BookSnapshot) -> int | None:
    if livro.bids and livro.asks:
        return (livro.bids[0].price + livro.asks[0].price) // 2
    if livro.bids:
        return livro.bids[0].price
    if livro.asks:
        return livro.asks[0].price
    return None
