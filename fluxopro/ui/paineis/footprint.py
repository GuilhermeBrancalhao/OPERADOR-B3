"""Footprint — o candle aberto por dentro. `direcao_visual.md` §5, Momento 3.

O candle normal entrega OHLC: quatro numeros para milhares de negocios. O
footprint abre cada candle num histograma **por nivel de preco**, com duas
colunas — quanto foi negociado por agressao vendedora e quanto por agressao
compradora naquele preco, dentro daquele candle. E a unica peca do produto
que responde *onde dentro do candle* a forca comprou ou vendeu.

## Tres eixos de decisao, e o que cada um custou

### 1. Volume de nivel varre ordens de magnitude — entao ele NAO e comprimento

A licao mais cara deste ciclo, encontrada tres vezes em `paineis/hud.py`:
**uma grandeza de variacao enorme desenhada como comprimento, com um rotulo
pequeno encarregado de desfazer a confusao que sobra.** Dentro de um candle,
o nivel do POC pode ter 800 lotes e o nivel da sombra 1 — 800x. Uma barra por
nivel arredondaria a sombra para zero, que e exatamente o defeito 3 do
ranking de players.

Aqui a magnitude e **numero**: `qty` alinhada a direita, unidade fixa
(lotes), algarismos tabulares. O que a celula tem de geometria e uma
**intensidade de 9 degraus numa escada ABSOLUTA de meias-decadas**
(`DEGRAUS_QTY`): 1, 3, 10, 30, 100, 300, 1.000, 3.000. Absoluta e a palavra
que importa — o degrau 5 significa a mesma coisa neste quadro e no quadro de
vinte minutos atras, entao **nao existe eixo movel para o canal apagar nem
para o operador comparar errado com a lembranca**. E uma intensidade nao
arredonda para zero: o degrau 0 continua sendo um pixel pintado.

A escada e ordinal de proposito. Ela nao afirma proporcao ("este e o dobro
daquele"); afirma ordem de grandeza. Quem quer a proporcao le o numero, que
esta na mesma celula, no mesmo corpo — que e a lei do canal aplicada ao
caso: o portador da conclusao e o portador da ressalva sao o mesmo glifo.

### 2. Os dois retangulos do candle usam as DUAS formas do vocabulario

`hud.py` fixou o vocabulario de forma do produto, e ele nao admite invencao:

| Forma | Significa |
|---|---|
| bidirecional a partir de um zero desenhado | saldo assinado |
| particionada, sempre cheia | proporcao entre partes |
| unidirecional do canto | magnitude sem sinal |

O rodape de cada candle usa as duas primeiras, e nenhuma delas tem escala:

* **SALDO** — bidirecional a partir do zero desenhado no centro, extensao
  `delta / volume_total`. E uma **fracao assinada em [-1, +1]**, limitada por
  natureza. O saldo em lotes vai ao lado, como numero com sinal explicito.
* **VOLUME** — particionada e sempre cheia: compra | venda | **sem lado**,
  nesta ordem, com o sem-lado ancorado na borda direita. O total em lotes vai
  como numero.

Os dois retangulos partilham o mesmo denominador (o volume TOTAL do candle,
sem-lado incluido) de proposito: assim a ponta do saldo e exatamente a
diferenca entre os dois primeiros segmentos da particao, e as duas leituras
nunca podem se contradizer. Um candle com 40% de volume sem agressor
divulgado nao consegue mostrar saldo de 100% — e nao deve.

O RLP anonimiza ate 15% do volume de WDO/WIN. O segmento `sem lado` e
desenhado **sempre, inclusive em zero**, pela razao que `matriz.py` ja pagou:
uma faixa que some ensina o olho a nao procurar por ela justamente no dia em
que ela importa.

### 3. Imbalance e DIAGONAL, e o caso que a fonte nao sabe medir

`analytics/footprint.py` compara o volume comprador em P contra o vendedor em
P+1 tick — diagonal, porque num book em movimento uma agressao de compra em P
so "vence" a oferta que estava um tick acima. Marcamos com **borda**, nunca
com mais uma cor (§5, Momento 3): a cor da celula ja carrega direcao e
intensidade.

Mas ha um caso em que a razao nao existe: quando o nivel vizinho tem
**zero** do outro lado, a funcao devolve o preco assim mesmo (razao infinita).
Publicar `venceu 3:1` e `venceu o vazio` com a mesma marca seria entregar o
veredito sem a ressalva. Entao a borda do caso nao medido sai em
`--absorption` em vez da cor do lado: **mesma forma, mesma espessura, mesmo
lugar, mesmo retangulo sujo** — se o canal comer uma, come as duas juntas, que
e a unica garantia que a lei do canal aceita. Ambar e o vocabulario que este
projeto ja usa para "o produto nao conseguiu medir isto" (`PASSA SEM MEDIR`,
`S/ REGISTRO` em `matriz.py`), e sobrevive a `PALETA_SEM_COR` porque nao
pertence ao eixo direcional.

## Procedencia: nada disto e regra do metodo, e a tela diz

`metodologia/regras.py` nao tem familia `footprint.*`, `volume_profile.*` nem
`delta.*`, e nenhum campo de `ConfigFootprint` aparece em `PARAMETROS`. Ou
seja: footprint, imbalance diagonal, POC e delta acumulado sao **componentes
genericos de order flow, de origem interna do projeto** — nao leituras do
metodo. O chip do cabecalho diz isso derivando do registro, e a lista de
botoes e derivada de `dataclasses.fields`, nunca digitada. Um `dict` escrito
aqui seria uma segunda fonte de procedencia, que e o defeito que `matriz.py`
documenta ter cometido e corrigido.

## Estrutura e desempenho

`_colunas` e um vetor de **slots de tela**, com o tamanho que cabe na largura
— nao um historico. Candle novo entra pela direita, o backing rola uma coluna
e o mais velho cai pela esquerda (§2, Achado 1: 1,79 ms contra 75 ms). O eixo
de preco recentraliza por rolagem vertical, como o DOM, e nunca por salto.

E o painel **nunca chama `footprints_fechados`** no caminho de quadro: essa
propriedade constroi uma tupla do historico inteiro da sessao a cada chamada,
que e custo O(sessao) por quadro. `derivar_footprint` le o candle VIVO todo
quadro (O(niveis do candle)) e so toca no historico na virada do candle —
uma vez por minuto.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, fields, replace
from functools import lru_cache

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.analytics.footprint import ConfigFootprint
from fluxopro.core.eventos import PriceGrid
from fluxopro.metodologia.confianca import Confianca
from fluxopro.metodologia.regras import PARAMETROS, REGRAS
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

# --------------------------------------------------------------------------
# Metricas de fonte memoizadas — mesma razao dos `QColor` de `tokens.py`.
# --------------------------------------------------------------------------
_metricas: dict[tuple, QFontMetrics] = {}


def metrica(fonte: QFont) -> QFontMetrics:
    """`QFontMetrics` memoizada.

    Medir texto e barato uma vez e caro por celula por quadro: construir um
    `QFontMetrics` atravessa a fronteira Python<->C++ e consulta o mecanismo
    de fontes. A chave vem dos parametros da fonte, e os pontos de chamada
    usam um punhado fixo de combinacoes — nao ha entrada nova por celula.
    """
    chave = (
        tuple(fonte.families()),
        fonte.pixelSize(),
        int(fonte.weight()),
        fonte.capitalization().name,
    )
    m = _metricas.get(chave)
    if m is None:
        m = QFontMetrics(fonte)
        _metricas[chave] = m
    return m


# --------------------------------------------------------------------------
# Procedencia metodologica — DERIVADA do registro, nunca digitada
# --------------------------------------------------------------------------
MARCA_REGRA = "§"
"""Prefixo do chip de procedencia. Marca o chip como sendo sobre a REGRA e
nao sobre o mercado — a mesma colisao que `matriz.py` desfez quando
`CONFIRMADO` aparecia como estagio do motor e como rotulo de confianca a
poucos pixels de distancia."""

ROTULO_CONFIANCA: dict[Confianca | None, str] = {
    Confianca.CONFIRMADO: "CONFIRMADO",
    Confianca.IMPRECISO: "IMPRECISO",
    Confianca.INFERIDO: "INFERIDO",
    Confianca.AUSENTE_NA_FONTE: "S/ FONTE",
    None: "S/ REGISTRO",
}
"""Traducao dos rotulos do registro. Nao e uma segunda fonte de procedencia:
a procedencia sai de `REGRAS`/`PARAMETROS`, isto sao so as palavras.

`S/ REGISTRO` nao e o mesmo que `S/ FONTE`. O segundo significa "olhamos a
fonte, o conceito nao esta la, e o registro diz isso por escrito"; o primeiro
significa "ninguem olhou ainda". O primeiro e um buraco na auditoria e por
isso e o PIOR de todos."""

_GRAVIDADE: dict[Confianca | None, int] = {
    Confianca.CONFIRMADO: 0,
    Confianca.INFERIDO: 1,
    Confianca.IMPRECISO: 2,
    Confianca.AUSENTE_NA_FONTE: 3,
    None: 4,
}


@lru_cache(maxsize=None)
def regras_do_campo(qualificado: str) -> tuple[str, ...]:
    """Regras do registro que respondem por um botao QUALIFICADO.

    Qualificado — `ConfigFootprint.limiar_imbalance`, e nao
    `limiar_imbalance`. A qualificacao nao e capricho: `janela_ns` existe em
    tres configuracoes diferentes deste projeto, e casar pelo nome curto faria
    a UI reivindicar um aval dado a outro componente.

    Devolve tupla vazia quando o registro nao cobre o botao — e e assim que o
    limiar vivo que ninguem registrou aparece na tela em vez de sumir.

    Memoizada porque o registro e imutavel depois do import e isto e lido no
    caminho de DESENHO.
    """
    achadas = {p.regra_id for p in PARAMETROS if p.nome == qualificado}
    achadas.update(i for i, r in REGRAS.items() if qualificado in r.nota)
    return tuple(sorted(achadas))


def procedencia_de_config(tipo: type) -> tuple[str, QColor]:
    """`(rotulo, cor)` da procedencia de TODOS os botoes de uma configuracao.

    A lista de campos e derivada de `dataclasses.fields`, entao um botao novo
    entra na conta sozinho e nao ha nome morto a envelhecer. A conta e do
    **pior elo**, nunca da media: uma leitura sustentada por uma regra
    `CONFIRMADO` e uma `IMPRECISO` e imprecisa.

    A cobertura `k/n` viaja junto com o rotulo, na mesma string, porque
    separa-las deixaria o canal entregar uma sem a outra. Com o registro de
    hoje as tres configuracoes desta fase leem `§ S/ REGISTRO 0/n`: nenhum
    botao do footprint, do perfil de volume ou do delta tem regra no
    registro. Esse zero e um achado do produto, nao um defeito do painel — o
    numerador e recalculado do registro a cada desenho, entao ele sobe
    sozinho no dia em que alguem registrar uma dessas regras.
    """
    campos = tuple(f.name for f in fields(tipo))
    if not campos:
        raise ValueError(f"{tipo.__name__} nao tem campo nenhum")
    pior: Confianca | None = Confianca.CONFIRMADO
    cobertos = 0
    for campo in campos:
        ids = regras_do_campo(tipo.__name__ + "." + campo)
        if not ids:
            if _GRAVIDADE[None] > _GRAVIDADE[pior]:
                pior = None
            continue
        cobertos += 1
        for identificador in ids:
            confianca = REGRAS[identificador].confianca
            if _GRAVIDADE[confianca] > _GRAVIDADE[pior]:
                pior = confianca
    rotulo = "%s %s %d/%d" % (
        MARCA_REGRA,
        ROTULO_CONFIANCA[pior],
        cobertos,
        len(campos),
    )
    if pior is Confianca.CONFIRMADO:
        return rotulo, tokens.OK
    if pior is None or pior is Confianca.AUSENTE_NA_FONTE:
        return rotulo, tokens.ABSORPTION
    return rotulo, tokens.ALERT


CORPO_CHIP = 11
"""Corpo do texto do chip. Onze, e nao os dez de `fonte_rotulo()`.

Medido com `scripts/retencao.py` sobre `design/retrato_footprint.png`: a 10px
o chip `§ S/ REGISTRO 0/4` retinha **36,9%** da energia de traco contra
**47,4%** do numero grande que ele qualifica — a lei do canal violada por 10,5
pontos. A causa nao e o contraste (o chip ja usa o par de maior contraste da
tela); e a densidade de borda: caixa alta de 10px com `letter-spacing` produz
hastes finas e vaos estreitos, exatamente o que a quantizacao come primeiro.
Um ponto a mais de corpo engrossa a haste sem mudar a forma."""

ALTURA_CHIP_MINIMA = 16


def chip(painter: QPainter, rect: QRect, texto: str, fundo: QColor) -> None:
    """Bloco PREENCHIDO com texto escuro dentro — a forma que atravessa o canal.

    Medido em `scripts/retencao.py`: a transmissao preserva o veredito e apaga
    a ressalva, porque veredito e grande e saturado e ressalva e pequena e
    apagada. Texto de 10px em `--text-muted` some a 72% de escala com JPEG 40;
    um retangulo cheio nao some, porque compressao com perdas ataca borda fina
    de alto contraste, nao area chapada. Entao toda ressalva que precisa
    sobreviver vira chip, e nunca legenda ao lado.
    """
    painter.fillRect(rect, fundo)
    painter.setFont(tokens.fonte_rotulo(CORPO_CHIP))
    painter.setPen(tokens.BG_BASE)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)


def texto_que_cabe(fm, largura: int, longo: str, curto: str) -> str:
    """O numero que CABE, nunca um numero truncado.

    `1.216` cortado pela largura da celula em `1.2` nao e um numero menor: e
    um numero **errado**, e e o pior modo de falha de uma grade densa, porque
    o que sobra continua parecendo um numero inteiro e o leitor nao tem como
    saber que faltou pedaco. §1 cobra isso da referencia em F8 (`Qtd Co…`,
    `Classifi…`, `22:rrelevant`) — la o truncamento pelo menos deixa
    reticencias; num numero, nao deixa nada.

    §3.4 pede unidade fixa por coluna, e a unidade abreviada e pior que a
    fixa. Mas a alternativa nao e "unidade fixa", e "unidade fixa cortada".
    Entao a ordem de preferencia e: inteiro, abreviado, nada — e o `k` do
    abreviado avisa o leitor de que a unidade mudou naquela celula, que e
    justamente o que o corte nao faz.
    """
    if fm.horizontalAdvance(longo) <= largura:
        return longo
    if fm.horizontalAdvance(curto) <= largura:
        return curto
    return ""


# --------------------------------------------------------------------------
# Intensidade — escada ABSOLUTA de meias-decadas
# --------------------------------------------------------------------------
DEGRAUS_QTY: tuple[int, ...] = (1, 3, 10, 30, 100, 300, 1_000, 3_000)
"""Cortes da escada de intensidade da celula. Oito cortes, nove degraus —
exatamente `tokens.N_DEGRAUS_INTENSIDADE`.

**Absolutos**, e essa e a decisao inteira. Uma intensidade relativa ao maximo
do candle (ou da janela) seria um eixo movel: a mesma celula de 40 lotes
sairia escura num candle magro e apagada num candle gordo, e o operador que
varre a tela compararia a lembranca de um quadro com o outro. E o defeito da
catraca de `hud.py`, deslocado do comprimento para a saturacao.

Meias-decadas porque volume de nivel varre ordens de magnitude: uma escada
linear gastaria oito dos nove degraus na faixa de 1 a 100 lotes e empilharia
tudo acima disso no ultimo. Cobrem de 1 a 3.000+ lotes, que e a faixa util de
um nivel de WDO/WIN num candle de minuto.
"""


def degrau_qty(qty: int) -> int:
    """Indice na rampa de `tokens` para uma quantidade. `0` fica fora.

    Quantidade acima do ultimo corte satura no topo em vez de levantar: um
    nivel gigante e evento normal de pregao, e derrubar o painel por causa
    dele seria trocar um pixel errado por uma tela preta.
    """
    if qty <= 0:
        return -1
    return min(bisect_right(DEGRAUS_QTY, qty), tokens.N_DEGRAUS_INTENSIDADE - 1)


# --------------------------------------------------------------------------
# Eixos compartilhados — o que faz as tres pecas serem UMA composicao
# --------------------------------------------------------------------------
class EixoPreco:
    """Preco <-> linha de tela. **Um objeto so, lido por dois paineis.**

    §1 cobra da referencia (fraqueza F5) que a aba Profundidade ponha bid e
    ask em eixos de preco DIFERENTES lado a lado: a linha 5 da esquerda e a
    linha 5 da direita nao tem relacao nenhuma, e ler "quanto tem neste nivel"
    exige contar linhas. A correcao nao e "usar a mesma formula nos dois
    paineis" — formula copiada diverge na primeira mudanca. E **o mesmo
    objeto**: o footprint escreve, o perfil le, e um alinhamento errado passa
    a ser impossivel em vez de improvavel.

    `versao` incrementa a cada mudanca de geometria ou de centro. E como o
    perfil sabe que precisa se redesenhar sem que o footprint o conheca.
    """

    def __init__(self, altura_linha: int) -> None:
        self.altura_linha = max(1, altura_linha)
        self.y0 = 0
        self.n_linhas = 0
        self.centro: int | None = None
        self.versao = 0

    # -- geometria ---------------------------------------------------------
    def configurar(self, y0: int, n_linhas: int) -> bool:
        if (y0, n_linhas) == (self.y0, self.n_linhas):
            return False
        self.y0, self.n_linhas = y0, max(0, n_linhas)
        self.versao += 1
        return True

    def y_da_linha(self, linha: int) -> int:
        return self.y0 + linha * self.altura_linha

    def rect_linha(self, linha: int, x: int, largura: int) -> QRect:
        return QRect(x, self.y_da_linha(linha), largura, self.altura_linha)

    # -- conversao ---------------------------------------------------------
    def preco_da_linha(self, linha: int) -> int | None:
        """Linha 0 e a mais ALTA da tela = maior preco.

        Escada de preco cresce para cima, sempre; inverter isso e desorientar
        quem opera, e §1 cobra da referencia exatamente um eixo invertido
        (`09_tape_reading_a.png`, X de 100 a 0 da esquerda para a direita).
        """
        if self.centro is None:
            return None
        return self.centro + (self.n_linhas // 2) - linha

    def linha_do_preco(self, preco: int) -> int | None:
        if self.centro is None:
            return None
        linha = self.centro + (self.n_linhas // 2) - preco
        return linha if 0 <= linha < self.n_linhas else None

    @property
    def faixa_visivel(self) -> tuple[int, int] | None:
        """`(preco_minimo, preco_maximo)` da tela. O recorte que mantem as
        estruturas dos paineis limitadas pela TELA e nao pela sessao."""
        if self.centro is None or self.n_linhas <= 0:
            return None
        alto = self.preco_da_linha(0)
        baixo = self.preco_da_linha(self.n_linhas - 1)
        assert alto is not None and baixo is not None
        return baixo, alto

    # -- movimento ---------------------------------------------------------
    def recentralizar(self, preco: int, folga_fracao: float) -> int:
        """Move o centro se `preco` saiu da zona de conforto. Devolve o
        deslocamento em LINHAS (positivo = conteudo desce na tela).

        Zero enquanto o preco estiver na faixa central: uma escada que se
        recentraliza a cada tick e ilegivel, porque o olho perde a referencia
        espacial, que e a unica coisa que um eixo de preco oferece alem dos
        numeros.
        """
        if self.centro is None:
            self.centro = preco
            self.versao += 1
            return 0
        if self.n_linhas <= 0:
            return 0
        folga = max(1, int(self.n_linhas * folga_fracao))
        linha = self.centro + (self.n_linhas // 2) - preco
        if folga <= linha < self.n_linhas - folga:
            return 0
        deslocamento = preco - self.centro
        self.centro = preco
        self.versao += 1
        return deslocamento


class EixoTempo:
    """Coluna de tela <-> candle. **Um objeto so, lido por dois paineis.**

    O footprint e o dono: e ele que decide quantas colunas cabem e qual candle
    esta em cada uma. `inicios[i]` guarda o `timestamp` de inicio do candle da
    coluna `i`, e e por essa CHAVE — nao por indice, nao por contagem — que o
    painel de delta acumulado se posiciona.

    A diferenca importa. `CumulativeDelta` recebe o proprio
    `ConfigDelta.timeframe_ns`, que **nao e** o `ConfigOperacao.timeframe_ns`
    que alimenta o footprint: os dois batem por default e podem ser calibrados
    separadamente. Alinhar por indice faria os dois paineis mentirem juntos e
    em silencio no dia em que alguem mexesse num dos dois. Alinhando por
    chave, um candle sem coluna correspondente simplesmente **nao e desenhado**
    — e o buraco na tela e a denuncia.
    """

    def __init__(self, largura_coluna: int) -> None:
        self.largura_coluna = max(1, largura_coluna)
        self.x0 = 0
        self.n_colunas = 0
        self.timeframe_ns = 0
        self.inicios: list[int | None] = []
        self.versao = 0

    def configurar(self, x0: int, n_colunas: int) -> bool:
        if (x0, n_colunas) == (self.x0, self.n_colunas):
            return False
        self.x0 = x0
        n_colunas = max(0, n_colunas)
        antigos = self.inicios[-n_colunas:] if n_colunas else []
        self.inicios = [None] * (n_colunas - len(antigos)) + antigos
        self.n_colunas = n_colunas
        self.versao += 1
        return True

    def x_da_coluna(self, indice: int) -> int:
        return self.x0 + indice * self.largura_coluna

    def rect_coluna(self, indice: int, y: int, altura: int) -> QRect:
        return QRect(self.x_da_coluna(indice), y, self.largura_coluna, altura)

    def coluna_do_inicio(self, inicio_ns: int) -> int | None:
        try:
            return self.inicios.index(inicio_ns)
        except ValueError:
            return None

    def registrar(self, indice: int, inicio_ns: int | None) -> None:
        """`versao` so anda quando o valor MUDA.

        Sem essa guarda, o footprint bumparia a versao a cada quadro so por
        reafirmar o candle vivo, e todo painel que observa a versao para saber
        se precisa se redesenhar passaria a fazer quadro cheio a 62 Hz — o
        ganho da regiao suja indo embora pela porta dos fundos."""
        if 0 <= indice < self.n_colunas and self.inicios[indice] != inicio_ns:
            self.inicios[indice] = inicio_ns
            self.versao += 1

    def rolar_virada(self, inicio_fechada: int | None) -> None:
        """Candle novo nasce a direita; o mais velho cai pela esquerda.

        O candle que estava VIVO nao sai da tela: ele so anda uma coluna para
        a esquerda e passa a valer como fechado. Por isso a chave dele e
        gravada na penultima posicao e a ultima nasce vazia, esperando o
        proximo vivo."""
        if self.n_colunas <= 0:
            return
        self.inicios.pop(0)
        if self.inicios:
            self.inicios[-1] = inicio_fechada
        self.inicios.append(None)
        self.versao += 1


# --------------------------------------------------------------------------
# O que o painel consome — puro, sem Qt no caminho de construcao
# --------------------------------------------------------------------------
_MAX_NIVEIS_POR_COLUNA = 256
"""Teto de niveis guardados por candle.

Nao e politica de crescimento: e rede contra um candle patologico (gap de
abertura, feed com preco corrompido). Um candle de minuto de WDO percorre
tipicamente 5 a 30 ticks. A estrutura do painel e limitada pelo produto
`colunas na tela x niveis do candle`, nunca pela sessao."""


@dataclass(frozen=True, slots=True)
class Celula:
    """Um nivel de preco dentro de um candle, ja reduzido ao que se desenha.

    `imbalance_medido` responde a pergunta que a marca sozinha nao responde:
    o nivel venceu o vizinho numa razao que da para calcular, ou venceu um
    vizinho VAZIO? `analytics/footprint.py` devolve os dois casos na mesma
    lista (`if qty_vendedor_vizinho == 0: resultado.append(preco)`), e o
    segundo tem razao indefinida. Publicar os dois com a mesma marca seria
    entregar o veredito sem a ressalva.
    """

    qty_venda: int
    qty_compra: int
    qty_sem_lado: int
    imbalance: int = 0
    """`+1` compra domina a diagonal, `-1` venda domina, `0` nenhum."""
    imbalance_medido: bool = True


@dataclass(frozen=True, slots=True)
class Coluna:
    """Um candle inteiro, ja reduzido. Imutavel: o painel guarda slots destes."""

    inicio_ns: int
    viva: bool
    niveis: tuple[tuple[int, Celula], ...]
    volume_total: int
    volume_compra: int
    volume_venda: int
    volume_sem_lado: int
    delta: int
    preco_maximo: int | None = None
    preco_minimo: int | None = None
    absorcao_topo: bool = False
    absorcao_fundo: bool = False
    delta_divergente: bool = False

    @property
    def fracao_saldo(self) -> float:
        """`delta / volume_total` — a fracao ASSINADA em [-1, +1].

        Denominador e o volume TOTAL, sem-lado incluido, e nao o atribuido.
        Assim um candle com 40% do volume sem agressor divulgado nao consegue
        desenhar saldo de 100% — e nao deve: ele nao sabe o lado de 40% do que
        passou. E a ponta desta barra passa a ser exatamente a diferenca entre
        os dois primeiros segmentos da barra de volume, que e o que impede as
        duas de se contradizerem.
        """
        if self.volume_total <= 0:
            return 0.0
        return max(-1.0, min(1.0, self.delta / self.volume_total))


@dataclass(frozen=True, slots=True)
class LeituraFootprint:
    """O que muda entre dois quadros: o candle vivo, e — na virada — o que
    acabou de fechar.

    Nunca o historico. `FootprintPorTimeframe.footprints_fechados` constroi
    uma tupla da sessao INTEIRA a cada chamada; le-la por quadro seria custo
    O(sessao) a 62 Hz. Aqui ela e tocada uma vez por candle.
    """

    viva: Coluna | None = None
    fechada: Coluna | None = None
    historico: tuple[Coluna, ...] = ()
    """So na PRIMEIRA leitura, quando o painel acorda no meio da sessao.

    Existe para que o footprint e o delta acumulado semeiem os MESMOS candles:
    se so um dos dois recuperasse o passado, os dois eixos nasceriam
    desalinhados e o `EIXOS ≠` do painel de baixo acenderia na abertura, todo
    dia, sem que nada estivesse errado."""


def _coluna_de(footprint, inicio_ns: int, viva: bool) -> Coluna:
    """`analytics.footprint.Footprint` -> `Coluna`. Puro, sem Qt."""
    imb_compra = set(footprint.niveis_imbalance_compra())
    imb_venda = set(footprint.niveis_imbalance_venda())
    niveis: list[tuple[int, Celula]] = []
    compra = venda = sem_lado = 0
    ordenados = footprint.niveis_ordenados()
    if len(ordenados) > _MAX_NIVEIS_POR_COLUNA:
        # Recorte pelo centro do candle, nao pelas pontas: as pontas sao
        # sombra e o centro e onde o negocio aconteceu.
        meio = len(ordenados) // 2
        metade = _MAX_NIVEIS_POR_COLUNA // 2
        ordenados = ordenados[max(0, meio - metade) : meio + metade]
    for preco, nivel in ordenados:
        compra += nivel.qty_comprador
        venda += nivel.qty_vendedor
        sem_lado += nivel.qty_nao_atribuida
        imbalance = 0
        medido = True
        if preco in imb_compra:
            imbalance = 1
            # Vizinho DIAGONAL: a compra em P e comparada com a venda em P+1.
            vizinho = footprint.nivel(preco + 1)
            medido = bool(vizinho and vizinho.qty_vendedor)
        elif preco in imb_venda:
            imbalance = -1
            vizinho = footprint.nivel(preco - 1)
            medido = bool(vizinho and vizinho.qty_comprador)
        niveis.append(
            (
                preco,
                Celula(
                    qty_venda=nivel.qty_vendedor,
                    qty_compra=nivel.qty_comprador,
                    qty_sem_lado=nivel.qty_nao_atribuida,
                    imbalance=imbalance,
                    imbalance_medido=medido,
                ),
            )
        )
    return Coluna(
        inicio_ns=inicio_ns,
        viva=viva,
        niveis=tuple(niveis),
        volume_total=footprint.volume_total,
        volume_compra=compra,
        volume_venda=venda,
        volume_sem_lado=footprint.volume_nao_atribuido,
        delta=footprint.delta,
        preco_maximo=footprint.preco_maximo,
        preco_minimo=footprint.preco_minimo,
        absorcao_topo=footprint.absorcao_topo(),
        absorcao_fundo=footprint.absorcao_fundo(),
        delta_divergente=footprint.delta_divergente(),
    )


def derivar_footprint(
    fonte, inicio_conhecido_ns: int | None, n_colunas: int = 0
) -> LeituraFootprint:
    """`FootprintPorTimeframe` -> `LeituraFootprint`, uma vez por quadro.

    `inicio_conhecido_ns` e o inicio do candle que o painel ja tem como vivo.
    Quando ele muda, houve virada: so ai o historico e consultado, e so o
    ULTIMO fechado. Fora da virada, o custo e O(niveis do candle corrente).
    """
    if fonte is None:
        return LeituraFootprint()
    atual = fonte.footprint_atual
    inicio = getattr(fonte, "_inicio_atual_ns", None)
    if atual is None or inicio is None:
        return LeituraFootprint()
    fechada: Coluna | None = None
    historico: tuple[Coluna, ...] = ()
    if inicio_conhecido_ns is None:
        if n_colunas > 1:
            anteriores = fonte.footprints_fechados[-(n_colunas - 1) :]
            historico = tuple(
                _coluna_de(f.footprint, f.timestamp_inicio_ns, viva=False)
                for f in anteriores
            )
    elif inicio_conhecido_ns != inicio:
        anteriores = fonte.footprints_fechados
        if anteriores:
            ultimo = anteriores[-1]
            fechada = _coluna_de(ultimo.footprint, ultimo.timestamp_inicio_ns, viva=False)
    return LeituraFootprint(
        viva=_coluna_de(atual, inicio, viva=True), fechada=fechada, historico=historico
    )


# --------------------------------------------------------------------------
# Geometria do painel
# --------------------------------------------------------------------------
MARGEM = 8
MARGEM_RECENTRALIZAR = 0.25
"""Fracao do eixo, em cada ponta, que funciona como zona de conforto — o
mesmo numero do DOM, pela mesma razao: menor que isso e o eixo se mexe demais;
maior e o preco encosta na borda justo quando importa."""

ALTURA_NUMERO = 12
ALTURA_BARRA = 8
ALTURA_MARCAS = 12
ALTURA_RODAPE = 2 * ALTURA_NUMERO + 2 * ALTURA_BARRA + ALTURA_MARCAS + 4
"""Multiplos de 4 (§3.4). Nada de 5, 7, 13."""

LARGURA_COSTURA = 2
"""Costura entre segmentos da barra particionada, em `BG_BASE`.

Com cor, ela separa azul de vermelho; **sem** cor, e a UNICA coisa que marca
onde um segmento acaba e o outro comeca, porque `PALETA_SEM_COR` colapsa o
eixo direcional num pixel so. Dois pixels para sobreviver a reescala de 0,72
do canal (viram 1,4) — um pixel seria apagado pela interpolacao justamente na
peca que carrega a leitura."""

ESCALA_SALDO = 0.10
"""Fundo de escala da barra de saldo, em fracao do volume do candle.

O saldo de um candle e `delta / volume_total`, limitado por natureza a
[-1, +1] — mas a faixa UTIL nao e essa. Medido no retrato: candles reais
ficam entre 0,1% e 11% do proprio volume, e um eixo de 0 a 100% desenhava
zero pixel em quase todos eles. Um candle cujo saldo liquido chega a um
decimo do proprio volume ja e fortemente direcional — e esse e o argumento
para o numero, que nao veio do dado e sim da leitura. Uma barra que e sempre zero nao e uma barra
honesta, e uma peca morta.

Dez por cento e **constante do produto**, e essa e a propriedade que
importa: nao acompanha o dado, nao tem catraca, nao muda entre dois quadros
e nao ha rotulo de escala para o canal apagar. O rotulo da calha diz
`Δ SALDO ±30%` porque a escala e furniture, nao dado.

O que se perde e a distincao entre 40% e 90%, que saturam no mesmo pixel. Nao
se perde em silencio: a ponta saturada ganha uma tampa `--absorption`, a mesma
convencao de "isto o produto nao conseguiu medir" que o imbalance sem razao e
o POC empatado usam. E o numero em lotes esta na linha de cima, no mesmo
retangulo sujo."""

ESPESSURA_IMBALANCE = 2
ESPESSURA_VIVA = 2
VAO_CELULA = 1

MOLDE_PRECO = "5.086,5"
"""So para MEDIR a calha de preco. Medir e melhor que cravar por dois
motivos: a fonte muda entre maquinas (Iosevka, JetBrains, Consolas tem
avancos diferentes) e a densidade muda o corpo. Um numero cravado esta certo
numa combinacao e errado nas outras — foi assim que a coluna de saldo do
ranking de players passou a pintar glifos por cima da barra do vizinho."""

ROTULOS_RODAPE = ("Σ VOL", "Δ SALDO ±%d%%" % round(ESCALA_SALDO * 100), "MARCA")
"""Rotulo de cada faixa do rodape, na calha.

O `±10%` e conteudo **redundante**, e nao ressalva — a distincao decide se ele
pode viver em corpo 10. `scripts/retencao.py` mede 32,3% de retencao para ele
contra 39,9% do numero de saldo, o que reprovaria a lei do canal SE ele fosse
uma ressalva. Nao e, por tres razoes que se somam: o fundo de escala e
constante do produto (nao ha catraca, o eixo nao se move entre dois quadros);
a comparacao entre candles e espacial e simultanea, nunca contra a memoria; e
o saldo em lotes esta no MESMO corpo, uma linha acima da barra. Perde-lo custa
a unidade do eixo, nunca a leitura — que e exatamente a condicao de §3.2 para
conteudo redundante, e exatamente o argumento que `hud.py` mostrou ser FALSO
para o caso temporal e verdadeiro para o espacial."""
"""Rotulo de cada faixa do rodape, na calha. §1 cobra da referencia rotulo
TRUNCADO (F8); rotulo AUSENTE e a mesma falha sem o alibi do espaco — foi o
que a banda de deteccoes da matriz cometeu por omissao."""

GLIFO_ABSORCAO_TOPO = "ABS▲"
GLIFO_ABSORCAO_FUNDO = "ABS▼"
GLIFO_DIVERGENCIA = "DIV"


class PainelFootprint(PainelDenso):
    """A grade densa do candle aberto por dentro."""

    def __init__(
        self,
        grid: PriceGrid,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        config: ConfigFootprint | None = None,
        simbolo: str = "",
        timeframe_ns: int = 0,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.densidade = densidade
        self.paleta = paleta
        # Os limiares vem da CONFIGURACAO, nunca cravados aqui. Quem calibrar
        # `limiar_imbalance` para 4,0 ve o cabecalho dizer 4,0 junto — um
        # rotulo que mente sobre o corte e pior que rotulo nenhum.
        self.config = config if config is not None else ConfigFootprint()
        self.simbolo = simbolo

        self.eixo_preco = EixoPreco(densidade.celula_footprint_h)
        self.eixo_tempo = EixoTempo(densidade.celula_footprint_w)
        self.eixo_tempo.timeframe_ns = timeframe_ns

        # Vetor de SLOTS DE TELA, indexado por coluna. Nao e historico: tem
        # exatamente o tamanho que cabe na largura, e o mais velho cai fora
        # quando um candle novo nasce.
        self._colunas: list[Coluna | None] = []
        self._inicio_vivo_ns: int | None = None

        self._rect_chip_limiar = QRect()
        self._medir(densidade)
        self.setMinimumSize(320, 240)

    def _medir(self, densidade: tokens.Densidade) -> None:
        """Tudo que a densidade define. **Uma funcao so, dois chamadores.**

        O construtor e `aplicar_densidade` chamam ESTA — nao duas copias da
        mesma conta. Este modulo ja registrou por que (`MOLDE_PRECO`): formula
        copiada diverge na primeira mudanca, e o sintoma seria geometria
        medida com a fonte antiga desenhada com a nova, sem erro nenhum em
        lugar nenhum.
        """
        self._fm_celula = metrica(tokens.fonte_numero(10))
        self._fm_preco = metrica(tokens.fonte_numero(densidade.fonte_grade, 500))
        self._fm_rotulo = metrica(tokens.fonte_rotulo())
        self._fm_chip = metrica(tokens.fonte_rotulo(CORPO_CHIP))
        # A calha e medida contra o preco E contra o mais largo dos rotulos do
        # rodape. Medir so o preco custou um defeito: `Δ SALDO ±10%` nao cabia,
        # a regra F8 o descartava, e a faixa de barras do saldo ficava sem
        # nome nenhum — uma linha de geometria que o leitor teria de adivinhar.
        self._largura_calha = max(
            56,
            self._fm_preco.horizontalAdvance(MOLDE_PRECO) + 2 * MARGEM,
            max(self._fm_rotulo.horizontalAdvance(r) for r in ROTULOS_RODAPE)
            + 2 * MARGEM,
        )

    def aplicar_densidade(self, nova: tokens.Densidade) -> None:
        """Troca a densidade A QUENTE, sem perder o historico de tela.

        Reconstruir o painel era o que a janela fazia, e custava as colunas ja
        absorvidas mais as chaves do `EixoTempo` — ou seja, o operador trocava
        a densidade e o dia recomecava na tela.

        Mutar so `self.densidade` seria pior que reconstruir: as quatro
        `QFontMetrics` e a largura da calha sao MEDIDAS no construtor a partir
        de `densidade.fonte_grade`, e a geometria ficaria calculada com a
        fonte antiga enquanto o texto sai na nova — calha estreita, rotulo do
        rodape descartado por F8, e nenhum erro em lugar nenhum. Por isso aqui
        se remede tudo (`_medir`) e se refaz a geometria dependente.

        Os eixos sao MUTADOS, nunca trocados: `PainelPerfil` e
        `PainelDeltaAcumulado` seguram estes mesmos objetos por identidade
        (ver a docstring de `EixoPreco`), e substitui-los quebraria em
        silencio o alinhamento que a identidade existe para tornar
        impossivel de errar.
        """
        if nova is self.densidade:
            return
        self.densidade = nova
        self.eixo_preco.altura_linha = max(1, nova.celula_footprint_h)
        self.eixo_preco.versao += 1
        self.eixo_tempo.largura_coluna = max(1, nova.celula_footprint_w)
        self.eixo_tempo.versao += 1
        self._medir(nova)
        # `ao_redimensionar` reconfigura os eixos com a geometria nova e
        # reaproveita os slots pela DIREITA (`_redimensionar_slots`): cabendo
        # menos colunas, cai o mais velho, que e a mesma politica da rolagem.
        self.ao_redimensionar(self.width(), self.height())
        self.marcar_tudo_sujo()

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    @property
    def largura_calha(self) -> int:
        return self._largura_calha

    @property
    def area_grade(self) -> QRect:
        """A grade de celulas, sem a calha e sem o rodape. **Publica porque o
        teste recorta exatamente esta faixa**: se a conta do recorte fosse
        escrita a parte, ela poderia divergir do desenho e o teste passaria a
        medir outra coisa sem avisar."""
        return QRect(
            self._largura_calha,
            self._y_corpo,
            max(0, self.width() - self._largura_calha),
            self.eixo_preco.n_linhas * self.eixo_preco.altura_linha,
        )

    @property
    def area_linhas(self) -> QRect:
        """Grade + calha. E a area que ROLA na vertical: o rotulo de preco
        anda junto com a linha a que ele pertence."""
        return QRect(
            0,
            self._y_corpo,
            self.width(),
            self.eixo_preco.n_linhas * self.eixo_preco.altura_linha,
        )

    @property
    def area_rolagem_tempo(self) -> QRect:
        """Grade + rodape, SEM a calha. E a area que rola na horizontal.

        A calha fica de fora de proposito: rolar o backing inteiro arrastaria
        os rotulos de preco para dentro da grade e depois redesenharia a faixa
        errada — os pixels ficariam certos so por acidente, quando a area
        exposta calhasse de cobrir o estrago."""
        grade = self.area_grade
        return QRect(
            grade.left(),
            grade.top(),
            grade.width(),
            grade.height() + ALTURA_RODAPE,
        )

    @property
    def area_rodape(self) -> QRect:
        grade = self.area_grade
        return QRect(0, grade.bottom() + 1, self.width(), ALTURA_RODAPE)

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        util = max(0, altura - self._y_corpo - ALTURA_RODAPE)
        n_linhas = max(0, util // self.eixo_preco.altura_linha)
        n_colunas = max(
            0, (largura - self._largura_calha) // self.eixo_tempo.largura_coluna
        )
        self.eixo_preco.configurar(self._y_corpo, n_linhas)
        if self.eixo_tempo.configurar(self._largura_calha, n_colunas):
            self._redimensionar_slots(n_colunas)

    def _redimensionar_slots(self, n: int) -> None:
        """Encolher DESCARTA o excedente, e nao guarda "para quando a janela
        crescer de novo": guardar seria exatamente a estrutura que cresce com
        o estado acumulado, so que com nome de cache."""
        antigos = self._colunas[-n:] if n else []
        self._colunas = [None] * (n - len(antigos)) + list(antigos)

    def rect_celula(self, linha: int, coluna: int) -> QRect:
        """A celula (linha, coluna). Compartilhada por desenho e teste."""
        return QRect(
            self.eixo_tempo.x_da_coluna(coluna),
            self.eixo_preco.y_da_linha(linha),
            self.eixo_tempo.largura_coluna,
            self.eixo_preco.altura_linha,
        )

    def rect_coluna_inteira(self, coluna: int) -> QRect:
        """A faixa vertical de um candle — grade e rodape juntos.

        E o retangulo sujo do caso comum: o candle vivo mudou, e o painel
        repinta UMA coluna em vez das vinte. Um retangulo so, e nao dois,
        porque o rodape e a continuacao logica da coluna e separa-los custaria
        uma troca de clip a mais por quadro."""
        grade = self.area_grade
        return QRect(
            self.eixo_tempo.x_da_coluna(coluna),
            grade.top(),
            self.eixo_tempo.largura_coluna,
            grade.height() + ALTURA_RODAPE,
        )

    def _y_rodape(self, faixa: int) -> int:
        """Topo de cada faixa do rodape: 0=Σ num, 1=Σ barra, 2=Δ num,
        3=Δ barra, 4=marcas."""
        base = self.area_rodape.top() + 2
        alturas = (ALTURA_NUMERO, ALTURA_BARRA, ALTURA_NUMERO, ALTURA_BARRA)
        return base + sum(alturas[:faixa])

    def rect_barra_volume(self, coluna: int) -> QRect:
        return QRect(
            self.eixo_tempo.x_da_coluna(coluna) + 1,
            self._y_rodape(1),
            max(2, self.eixo_tempo.largura_coluna - 2),
            ALTURA_BARRA,
        )

    def rect_barra_saldo(self, coluna: int) -> QRect:
        return QRect(
            self.eixo_tempo.x_da_coluna(coluna) + 1,
            self._y_rodape(3),
            max(2, self.eixo_tempo.largura_coluna - 2),
            ALTURA_BARRA,
        )

    def x_zero_saldo(self, coluna: int) -> int:
        """O zero DESENHADO da barra de saldo — o marco contra o qual a ponta
        e lida.

        Publica, e usada TANTO pelo desenho QUANTO pela medicao do teste. A
        razao esta escrita em sangue no ranking de players: a primeira versao
        do teste media o desvio contra `rect.center().x()` — `left + (w-1)//2`
        — que e um marco que o desenho **nao usa**. O off-by-one de um pixel
        fazia a assercao anti-piso passar raspando, e o guarda deixava passar
        exatamente o piso que existia no produto. Marco de teste e marco de
        desenho tem de ser a mesma funcao."""
        barra = self.rect_barra_saldo(coluna)
        return barra.left() + self._meia_saldo(barra)

    def x_ponta_saldo(self, coluna: int, fracao: float) -> int:
        """Onde a barra de saldo termina, para uma fracao assinada do volume.

        Compartilhada por desenho e teste, de proposito: teste que mede contra
        um marco que o desenho nao usa e teatro."""
        barra = self.rect_barra_saldo(coluna)
        zero = self.x_zero_saldo(coluna)
        normalizada = max(-1.0, min(1.0, fracao / ESCALA_SALDO))
        return zero + int(round(normalizada * self._meia_saldo(barra)))

    @staticmethod
    def _meia_saldo(barra: QRect) -> int:
        """Meia largura util da barra bipolar.

        `(w - 1) // 2` e nao `w // 2`: com o zero em `left + w//2`, a ponta
        saturada positiva caia em `left + w`, um pixel FORA da barra — e o
        pixel de maior saldo da tela era o unico que o painel nao desenhava.
        Achado pelo teste que mede a ponta no backing contra a saturacao."""
        return max(1, (barra.width() - 1) // 2)

    @property
    def rect_chip_limiar(self) -> QRect:
        """A caixa do chip `IMBALANCE ≥ 3:1 · MÍN 5`, para `retencao.py`."""
        return QRect(self._rect_chip_limiar)

    def rect_rotulo_rodape(self, faixa: int) -> QRect:
        """A caixa de um rotulo da calha do rodape (`Σ VOL`, `Δ SALDO ±10%`,
        `MARCA`). Publica porque `scripts/retencao.py` mede exatamente ela — e
        uma caixa desenhada a mao poderia medir outra coisa."""
        indice = (0, 2, 4).index(faixa) if faixa in (0, 2, 4) else 0
        altura = ALTURA_NUMERO + (ALTURA_BARRA if indice < 2 else 0)
        return QRect(
            MARGEM, self._y_rodape(faixa), self._largura_calha - 2 * MARGEM, altura
        )

    def rect_numero_saldo(self, coluna: int) -> QRect:
        """A caixa do numero de saldo de um candle — o veredito que a escala
        `±10%` qualifica."""
        return QRect(
            self.eixo_tempo.x_da_coluna(coluna) + 1,
            self._y_rodape(2),
            self.eixo_tempo.largura_coluna - 3,
            ALTURA_NUMERO,
        )

    def x_costura_volume(self, coluna: int, fracao: float) -> int:
        """Onde a barra de volume se parte, para uma fracao acumulada."""
        barra = self.rect_barra_volume(coluna)
        corte = barra.left() + int(round(max(0.0, min(1.0, fracao)) * barra.width()))
        return min(max(corte, barra.left()), barra.right() + 1)

    # ---------------------------------------------------------------- dados
    @property
    def inicio_vivo_ns(self) -> int | None:
        """O que `derivar_footprint` precisa saber para detectar a virada."""
        return self._inicio_vivo_ns

    @property
    def colunas_visiveis(self) -> tuple[Coluna | None, ...]:
        return tuple(self._colunas)

    @property
    def faixa_visivel(self) -> tuple[int, int] | None:
        return self.eixo_preco.faixa_visivel

    def aplicar(self, leitura: LeituraFootprint) -> None:
        """Absorve o quadro. Chamado pela janela, uma vez por quadro."""
        if leitura.historico:
            self._semear(leitura.historico)
        if leitura.fechada is not None:
            self._virar_candle(leitura.fechada)
        if leitura.viva is not None:
            self._aplicar_viva(leitura.viva)

    def _semear(self, historico: tuple[Coluna, ...]) -> None:
        """Preenche a tela com o que a sessao ja tem, uma vez.

        A ultima posicao nasce vazia, esperando o candle vivo — a mesma forma
        que a virada produz, para que os dois caminhos deixem o painel no
        mesmo estado."""
        n = len(self._colunas)
        if n <= 1:
            return
        recorte = list(historico[-(n - 1) :])
        vazios = n - 1 - len(recorte)
        self._colunas = [None] * vazios + recorte + [None]
        self.eixo_tempo.inicios = (
            [None] * vazios + [c.inicio_ns for c in recorte] + [None]
        )
        self.eixo_tempo.versao += 1
        for coluna_semeada in recorte:
            self._talvez_recentralizar(coluna_semeada)
        self.marcar_tudo_sujo()

    def _virar_candle(self, fechada: Coluna) -> None:
        """Candle novo nasce a direita; o backing rola uma coluna.

        E o mecanismo de §2, Achado 1: em vez de redesenhar as vinte colunas,
        move as dezenove que continuam validas e desenha uma."""
        if len(self._colunas) < 2:
            return
        # A coluna que estava viva anda uma posicao para a esquerda e recebe o
        # estado FINAL que o analytics congelou — e nao o ultimo retrato que a
        # UI calhou de ler 16 ms antes do fim do candle. A ultima posicao nasce
        # vazia, esperando o proximo candle vivo; e por isso que `_aplicar_viva`
        # logo a seguir NAO rola de novo.
        self._colunas.pop(0)
        self._colunas[-1] = fechada
        self._colunas.append(None)
        self.eixo_tempo.rolar_virada(fechada.inicio_ns)
        self.rolar(-self.eixo_tempo.largura_coluna, 0, self.area_rolagem_tempo)
        # A penultima coluna perdeu a decoracao de "viva" e tem de ser
        # repintada; a ultima e a faixa que acabou de entrar.
        self.marcar_sujo(self.rect_coluna_inteira(len(self._colunas) - 2))

    def _aplicar_viva(self, viva: Coluna) -> None:
        if not self._colunas:
            self._inicio_vivo_ns = viva.inicio_ns
            return
        ultimo = len(self._colunas) - 1
        anterior = self._colunas[ultimo]
        if anterior is not None and anterior.inicio_ns != viva.inicio_ns:
            # Virada sem `fechada` na leitura (painel aberto no meio do
            # candle, ou historico ainda vazio): rola do mesmo jeito, com o
            # ultimo retrato que a UI tem. Perder a rolagem seria pior — as
            # colunas passariam a mentir sobre qual candle e qual.
            if len(self._colunas) < 2:
                self._colunas[ultimo] = None
                anterior = None
            else:
                self._colunas.pop(0)
                self._colunas[-1] = _fechar(anterior)
                self._colunas.append(None)
                self.eixo_tempo.rolar_virada(anterior.inicio_ns)
                self.rolar(-self.eixo_tempo.largura_coluna, 0, self.area_rolagem_tempo)
                self.marcar_sujo(self.rect_coluna_inteira(len(self._colunas) - 2))
                anterior = None
        self._inicio_vivo_ns = viva.inicio_ns
        self.eixo_tempo.registrar(ultimo, viva.inicio_ns)
        if anterior == viva:
            return
        self._colunas[ultimo] = viva
        self._talvez_recentralizar(viva)
        self.marcar_sujo(self.rect_coluna_inteira(ultimo))

    def _talvez_recentralizar(self, viva: Coluna) -> None:
        referencia = viva.preco_maximo
        if referencia is None or viva.preco_minimo is None:
            return
        # O MEIO do candle corrente, e nao o ultimo preco: o footprint mostra
        # a faixa que o candle percorreu, e ancorar num extremo deixaria
        # metade do candle fora da tela a cada nova maxima.
        alvo = (viva.preco_maximo + viva.preco_minimo) // 2
        if self.eixo_preco.centro is None:
            self.eixo_preco.recentralizar(alvo, MARGEM_RECENTRALIZAR)
            self.marcar_tudo_sujo()
            return
        deslocamento = self.eixo_preco.recentralizar(alvo, MARGEM_RECENTRALIZAR)
        if deslocamento == 0:
            return
        if abs(deslocamento) >= self.eixo_preco.n_linhas:
            self.marcar_tudo_sujo()
            return
        # Preco SUBINDO desloca o conteudo para BAIXO na tela.
        self.rolar(0, deslocamento * self.eixo_preco.altura_linha, self.area_linhas)

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            self._desenhar_cabecalho(painter)
        grade = self.area_grade
        if grade.isValid() and grade.intersects(regiao):
            self._desenhar_calha(painter, regiao)
            self._desenhar_grade(painter, regiao)
        rodape = self.area_rodape
        if rodape.isValid() and rodape.intersects(regiao):
            self._desenhar_rodape(painter, regiao)

    # -- cabecalho ---------------------------------------------------------
    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        rect = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        titulo = "FOOTPRINT"
        if self.simbolo:
            titulo += " · " + self.simbolo
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo
        )
        x = MARGEM + self._fm_rotulo.horizontalAdvance(titulo) + 12
        x = self._chip_procedencia(painter, x, rect)
        # O LIMIAR do imbalance, em CHIP e junto da peca que ele governa.
        #
        # Era texto de 10px em `--text-muted`, e a transmissao degradada o
        # entregou como borrao enquanto as marcas de imbalance — 2px de area
        # chapada — atravessavam intactas. Isso e a lei do canal violada na sua
        # forma mais pura: o veredito (a marca) sobrevive e a regua que o
        # define (`≥ 3:1`, `mín 5`) morre. E aqui a marca **nao tem numero
        # companheiro na propria celula** que a socorra, ao contrario do que
        # acontece com a barra de saldo. Entao a regua vira bloco preenchido.
        rotulo_limiar = "IMBALANCE ≥ %s:1 · MÍN %d" % (
            f"{self.config.limiar_imbalance:g}".replace(".", ","),
            self.config.qty_minima_imbalance,
        )
        largura = self._fm_chip.horizontalAdvance(rotulo_limiar) + 12
        altura = max(ALTURA_CHIP_MINIMA, rect.height() - 6)
        self._rect_chip_limiar = QRect(
            x, rect.top() + (rect.height() - altura) // 2, largura, altura
        )
        if x + largura <= rect.right() - MARGEM:
            chip(painter, self._rect_chip_limiar, rotulo_limiar, tokens.NEUTRAL)
            x += largura + 12
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(x, rect.top(), max(0, rect.width() - x - MARGEM), rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "candle %s" % _duracao(self.eixo_tempo.timeframe_ns),
        )
        self._desenhar_escada(painter, rect)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, rect.bottom(), rect.width(), rect.bottom())

    def _chip_procedencia(self, painter: QPainter, x: int, linha: QRect) -> int:
        rotulo, cor = procedencia_de_config(type(self.config))
        largura = self._fm_chip.horizontalAdvance(rotulo) + 12
        if x + largura > linha.right():
            return x
        altura = max(ALTURA_CHIP_MINIMA, linha.height() - 6)
        chip(
            painter,
            QRect(x, linha.top() + (linha.height() - altura) // 2, largura, altura),
            rotulo,
            cor,
        )
        return x + largura + 12

    def _desenhar_escada(self, painter: QPainter, rect: QRect) -> None:
        """A escada de intensidade, desenhada. Nove blocos e as duas pontas.

        E legenda, e legenda morre no canal — mas perde-la nao produz leitura
        errada nenhuma, porque a quantidade esta escrita dentro de cada
        celula. E a condicao de §3.2 para usar `--text-muted`: conteudo
        redundante."""
        largura_bloco = 6
        total = tokens.N_DEGRAUS_INTENSIDADE * largura_bloco
        fim = rect.right() - MARGEM
        texto_fim = "3k+"
        largura_fim = self._fm_celula.horizontalAdvance(texto_fim)
        x = fim - largura_fim - 2 - total - 2 - self._fm_celula.horizontalAdvance("1")
        if x < rect.left() + rect.width() // 2:
            return  # F8: o que nao cabe INTEIRO nao entra
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(x, rect.top(), self._fm_celula.horizontalAdvance("1"), rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "1",
        )
        x += self._fm_celula.horizontalAdvance("1") + 2
        rampa = tokens.RAMPA_NEUTRA
        y = rect.top() + (rect.height() - 8) // 2
        for i in range(tokens.N_DEGRAUS_INTENSIDADE):
            painter.fillRect(QRect(x + i * largura_bloco, y, largura_bloco - 1, 8), rampa[i])
        painter.drawText(
            QRect(x + total + 2, rect.top(), largura_fim, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texto_fim,
        )

    # -- calha de preco ----------------------------------------------------
    def _desenhar_calha(self, painter: QPainter, regiao: QRect) -> None:
        eixo = self.eixo_preco
        if eixo.centro is None:
            return
        calha = QRect(0, eixo.y0, self._largura_calha, self.area_grade.height())
        alvo = calha.intersected(regiao)
        if not alvo.isValid():
            return
        painter.fillRect(alvo, self.cor_fundo)
        primeira = max(0, (alvo.top() - eixo.y0) // eixo.altura_linha)
        ultima = min(eixo.n_linhas - 1, (alvo.bottom() - eixo.y0) // eixo.altura_linha)
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 500))
        for linha in range(primeira, ultima + 1):
            preco = eixo.preco_da_linha(linha)
            if preco is None:
                continue
            estavel, vivo = formato.formatar_preco(self.grid, preco)
            caixa = QRect(0, eixo.y_da_linha(linha), self._largura_calha - 4, eixo.altura_linha)
            largura_vivo = self._fm_preco.horizontalAdvance(vivo)
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                QRect(caixa.right() - largura_vivo, caixa.top(), largura_vivo, caixa.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                vivo,
            )
            # Digitos estaveis apagados (§3.2, F6): a parte repetida em todas
            # as linhas nao pode competir com a que muda. Em `5.086,5`, seis
            # dos oito caracteres sao ruido repetido quarenta vezes.
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(caixa.left(), caixa.top(), caixa.width() - largura_vivo, caixa.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                estavel,
            )
        painter.setPen(tokens.BORDER)
        painter.drawLine(
            self._largura_calha - 1, alvo.top(), self._largura_calha - 1, alvo.bottom()
        )

    # -- grade -------------------------------------------------------------
    def _desenhar_grade(self, painter: QPainter, regiao: QRect) -> None:
        eixo = self.eixo_preco
        grade = self.area_grade
        alvo = grade.intersected(regiao)
        if not alvo.isValid() or eixo.centro is None or eixo.n_linhas <= 0:
            self._desenhar_vazio(painter, grade.intersected(regiao))
            return
        largura_coluna = self.eixo_tempo.largura_coluna
        # SO as colunas que cruzam a regiao suja. E aqui que o fator 40 mora:
        # o candle vivo desenha uma coluna, nao vinte.
        primeira = max(0, (alvo.left() - grade.left()) // largura_coluna)
        ultima = min(
            len(self._colunas) - 1, (alvo.right() - grade.left()) // largura_coluna
        )
        for indice in range(primeira, ultima + 1):
            self._desenhar_coluna(painter, indice, alvo)

    def _desenhar_vazio(self, painter: QPainter, regiao: QRect) -> None:
        if not regiao.isValid():
            return
        painter.setFont(tokens.fonte_ui(14))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO ABERTURA")

    def _desenhar_coluna(self, painter: QPainter, indice: int, alvo: QRect) -> None:
        eixo = self.eixo_preco
        coluna = self._colunas[indice]
        x = self.eixo_tempo.x_da_coluna(indice)
        largura = self.eixo_tempo.largura_coluna
        faixa = QRect(x, self.area_grade.top(), largura, self.area_grade.height())
        painter.fillRect(faixa, self.cor_fundo)
        # O divisor central da coluna: uma linha continua por coluna em vez de
        # um `×` por celula. Sao 20 `drawLine` por quadro cheio contra 1.200
        # glifos, e o traco vertical atravessa o canal muito melhor que um
        # glifo de 10px — e ele E a afirmacao de que ha DUAS colunas neste
        # eixo de preco, que e a correcao de F5.
        meio = x + largura // 2
        painter.setPen(tokens.BORDER)
        painter.drawLine(meio, faixa.top(), meio, faixa.bottom())
        if coluna is None:
            return
        if coluna.viva:
            # §5, Momento 3: o operador nunca pode confundir candle em
            # formacao com candle fechado — erro caro e comum.
            painter.fillRect(
                QRect(x, faixa.top(), ESPESSURA_VIVA, faixa.height()),
                tokens.TEXT_SECONDARY,
            )
        painter.setFont(tokens.fonte_numero(10))
        for preco, celula in coluna.niveis:
            linha = eixo.linha_do_preco(preco)
            if linha is None:
                continue
            y = eixo.y_da_linha(linha)
            if y + eixo.altura_linha < alvo.top() or y > alvo.bottom():
                continue
            self._desenhar_celula(painter, x, y, largura, celula)

    def _desenhar_celula(
        self, painter: QPainter, x: int, y: int, largura: int, celula: Celula
    ) -> None:
        eixo = self.eixo_preco
        altura = eixo.altura_linha
        meia = largura // 2
        rampa_venda = tokens.RAMPA_VENDA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA
        rampa_compra = tokens.RAMPA_COMPRA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA

        grau_venda = degrau_qty(celula.qty_venda)
        if grau_venda >= 0:
            painter.fillRect(
                QRect(x + VAO_CELULA, y + 1, meia - VAO_CELULA - 1, altura - 2),
                rampa_venda[grau_venda],
            )
        grau_compra = degrau_qty(celula.qty_compra)
        if grau_compra >= 0:
            painter.fillRect(
                QRect(x + meia + 1, y + 1, largura - meia - VAO_CELULA - 1, altura - 2),
                rampa_compra[grau_compra],
            )

        # A borda do imbalance, no lado dominante. FORMA, e nao mais uma cor:
        # a cor da celula ja carrega direcao e intensidade, e uma quarta
        # dimensao precisa de outro canal (§5, Momento 3).
        if celula.imbalance:
            # Ambar quando a razao NAO existe (o vizinho diagonal esta vazio).
            # Mesma forma, mesma espessura, mesmo retangulo sujo do caso
            # medido: se o canal comer uma marca, come as duas juntas.
            if not celula.imbalance_medido:
                cor = tokens.ABSORPTION
            elif celula.imbalance > 0:
                cor = self.paleta.compra
            else:
                cor = self.paleta.venda
            if celula.imbalance > 0:
                marca = QRect(x + largura - ESPESSURA_IMBALANCE, y + 1, ESPESSURA_IMBALANCE, altura - 2)
            else:
                marca = QRect(x, y + 1, ESPESSURA_IMBALANCE, altura - 2)
            painter.fillRect(marca, cor)

        painter.setPen(tokens.TEXT_PRIMARY)
        if celula.qty_venda:
            caixa = QRect(x + 2, y, meia - 4, altura)
            painter.drawText(
                caixa,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._texto_qty(celula.qty_venda, caixa.width()),
            )
        if celula.qty_compra:
            caixa = QRect(x + meia + 3, y, largura - meia - 5, altura)
            painter.drawText(
                caixa,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._texto_qty(celula.qty_compra, caixa.width()),
            )
        if celula.qty_sem_lado:
            # Volume sem agressor divulgado (RLP). Nao pertence a nenhuma das
            # duas colunas e enfia-lo numa delas seria INVENTAR agressor —
            # entao ele ocupa a faixa de baixo da propria celula, em
            # `--neutral`, no mesmo retangulo do numero que ele qualifica.
            painter.fillRect(
                QRect(x + VAO_CELULA, y + altura - 2, largura - 2 * VAO_CELULA, 1),
                tokens.NEUTRAL,
            )

    def _texto_qty(self, qty: int, largura: int) -> str:
        return texto_que_cabe(
            self._fm_celula,
            largura,
            formato.formatar_inteiro(qty),
            formato.abreviar(qty, com_sinal=False),
        )

    # -- rodape ------------------------------------------------------------
    def _desenhar_rodape(self, painter: QPainter, regiao: QRect) -> None:
        rodape = self.area_rodape
        alvo = rodape.intersected(regiao)
        if not alvo.isValid():
            return
        painter.fillRect(alvo, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(alvo.left(), rodape.top(), alvo.right(), rodape.top())
        if alvo.left() < self._largura_calha:
            self._desenhar_rotulos_rodape(painter)
        largura_coluna = self.eixo_tempo.largura_coluna
        grade = self.area_grade
        primeira = max(0, (alvo.left() - grade.left()) // largura_coluna)
        ultima = min(len(self._colunas) - 1, (alvo.right() - grade.left()) // largura_coluna)
        for indice in range(primeira, ultima + 1):
            coluna = self._colunas[indice]
            if coluna is not None:
                self._desenhar_rodape_coluna(painter, indice, coluna)

    def _desenhar_rotulos_rodape(self, painter: QPainter) -> None:
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        for i, rotulo in enumerate(ROTULOS_RODAPE):
            caixa = self.rect_rotulo_rodape((0, 2, 4)[i])
            if self._fm_rotulo.horizontalAdvance(rotulo) > caixa.width():
                continue  # F8: rotulo nunca trunca; se nao cabe, nao entra
            painter.drawText(
                caixa,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                rotulo,
            )

    def _desenhar_rodape_coluna(self, painter: QPainter, indice: int, coluna: Coluna) -> None:
        x = self.eixo_tempo.x_da_coluna(indice)
        largura = self.eixo_tempo.largura_coluna
        if coluna.viva:
            painter.fillRect(
                QRect(x, self.area_rodape.top() + 1, largura, ALTURA_RODAPE - 1),
                tokens.BG_RAISED,
            )
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(x + 1, self._y_rodape(0), largura - 3, ALTURA_NUMERO),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._texto_qty(coluna.volume_total, largura - 3),
        )
        self._desenhar_barra_volume(painter, indice, coluna)
        painter.setFont(tokens.fonte_numero(10, 600))
        painter.setPen(self.paleta.direcional(coluna.delta))
        painter.drawText(
            self.rect_numero_saldo(indice),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            texto_que_cabe(
                self._fm_celula,
                largura - 3,
                formato.formatar_sinalizado(coluna.delta),
                formato.abreviar(coluna.delta),
            ),
        )
        self._desenhar_barra_saldo(painter, indice, coluna)
        self._desenhar_marcas(painter, indice, coluna)

    def _desenhar_barra_volume(self, painter: QPainter, indice: int, coluna: Coluna) -> None:
        """Particionada e SEMPRE cheia — proporcao, sem escala.

        Tres segmentos em ordem fixa: compra da borda esquerda, venda no meio,
        **sem lado ancorado na borda direita**. Ordem fixa e ancoragem nas
        duas bordas sao o que permite ler cada fatia contra um marco imovel;
        segmentos que flutuam entre dois vizinhos moveis nao se leem.

        O segmento sem-lado e desenhado **sempre, inclusive em zero** — uma
        faixa que some ensina o olho a nao procurar por ela justamente no dia
        em que 15% do volume nao tem agressor divulgado."""
        barra = self.rect_barra_volume(indice)
        painter.fillRect(barra, tokens.BG_RAISED)
        total = coluna.volume_total
        if total <= 0:
            return
        fracao_compra = coluna.volume_compra / total
        fracao_venda = coluna.volume_venda / total
        corte1 = self.x_costura_volume(indice, fracao_compra)
        corte2 = self.x_costura_volume(indice, fracao_compra + fracao_venda)
        if corte1 > barra.left():
            painter.fillRect(
                QRect(barra.left(), barra.top(), corte1 - barra.left(), barra.height()),
                self.paleta.compra,
            )
        if corte2 > corte1:
            painter.fillRect(
                QRect(corte1, barra.top(), corte2 - corte1, barra.height()),
                self.paleta.venda,
            )
        if corte2 <= barra.right():
            painter.fillRect(
                QRect(corte2, barra.top(), barra.right() + 1 - corte2, barra.height()),
                tokens.NEUTRAL,
            )
        # As costuras. Com cor, separam os segmentos; SEM cor, sao a UNICA
        # coisa que marca onde um acaba e o outro comeca.
        for corte in (corte1, corte2):
            painter.fillRect(
                QRect(corte - LARGURA_COSTURA // 2, barra.top(), LARGURA_COSTURA, barra.height()),
                tokens.BG_BASE,
            )

    def _desenhar_barra_saldo(self, painter: QPainter, indice: int, coluna: Coluna) -> None:
        """Bidirecional a partir de um zero DESENHADO — saldo assinado.

        A extensao e `delta / volume_total`, uma fracao limitada por natureza:
        nao ha escala, nao ha catraca, nao ha rotulo de 10px encarregado de
        dizer qual e o fundo de escala. O saldo em lotes vive na linha de cima,
        como numero com sinal explicito."""
        barra = self.rect_barra_saldo(indice)
        painter.fillRect(barra, tokens.BG_RAISED)
        zero = self.x_zero_saldo(indice)
        # O zero, desenhado, e desenhado ANTES da barra. Depois, ele cobriria o
        # primeiro pixel de todo saldo positivo — e um saldo de um pixel
        # desapareceria inteiro debaixo da propria referencia que deveria
        # torna-lo legivel.
        painter.fillRect(
            QRect(zero, barra.top() - 1, 1, barra.height() + 2), tokens.BORDER_STRONG
        )
        fracao = coluna.fracao_saldo
        if not fracao:
            return
        ponta = self.x_ponta_saldo(indice, fracao)
        if fracao > 0:
            corpo = QRect(zero + 1, barra.top(), max(0, ponta - zero), barra.height())
        else:
            corpo = QRect(ponta, barra.top(), max(0, zero - ponta), barra.height())
        if corpo.width() > 0:
            if self.paleta.tem_cor:
                rampa = tokens.RAMPA_COMPRA if fracao > 0 else tokens.RAMPA_VENDA
            else:
                rampa = tokens.RAMPA_NEUTRA
            painter.fillRect(corpo, rampa[tokens.degrau(abs(fracao) / ESCALA_SALDO)])
        if abs(fracao) >= ESCALA_SALDO:
            # Tampa de SATURACAO: o valor passou do fundo de escala e o
            # comprimento parou de crescer. Sem ela, um candle a 12% e outro a
            # 60% sairiam com o mesmo pixel e nada na tela denunciaria.
            painter.fillRect(
                QRect(ponta - 1 if fracao > 0 else ponta, barra.top(), 2, barra.height()),
                tokens.ABSORPTION,
            )

    def _desenhar_marcas(self, painter: QPainter, indice: int, coluna: Coluna) -> None:
        """As CONCLUSOES do candle: absorcao no extremo e delta divergente.

        §1 cobra da referencia que ela entregue os ingredientes e deixe a
        sintese com o operador no meio do pregao. `analytics/footprint.py`
        calcula as duas e elas morreriam no codigo se a tela nao as mostrasse.
        Chips, e nao texto solto, porque sao veredito e veredito tem de
        atravessar o canal."""
        x = self.eixo_tempo.x_da_coluna(indice)
        largura = self.eixo_tempo.largura_coluna
        caixa = QRect(x + 1, self._y_rodape(4), largura - 2, ALTURA_MARCAS)
        if coluna.absorcao_topo:
            texto, cor = GLIFO_ABSORCAO_TOPO, tokens.ABSORPTION
        elif coluna.absorcao_fundo:
            texto, cor = GLIFO_ABSORCAO_FUNDO, tokens.ABSORPTION
        elif coluna.delta_divergente:
            texto, cor = GLIFO_DIVERGENCIA, tokens.ALERT
        else:
            return
        if self._fm_chip.horizontalAdvance(texto) + 6 > caixa.width():
            return  # F8
        chip(painter, caixa, texto, cor)


def _fechar(coluna: Coluna) -> Coluna:
    """A mesma coluna, sem a decoracao de candle vivo."""
    return replace(coluna, viva=False)


def _duracao(ns: int) -> str:
    """`60000000000` -> `1min`. So para o rotulo de janela do cabecalho."""
    if ns <= 0:
        return "—"
    segundos = ns / 1_000_000_000
    if segundos >= 60:
        return f"{segundos / 60:g}min".replace(".", ",")
    return f"{segundos:g}s".replace(".", ",")
