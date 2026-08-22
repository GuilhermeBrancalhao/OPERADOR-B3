"""Matriz de estado — o que o motor CONCLUIU, num lugar so.

`design/direcao_visual.md` §4.3 mostra a tela de fluxo; §6 fase 4 pede o
farol de 5 estagios. Este painel e a peca que junta as duas coisas e vai
alem delas: DOM, tape e footprint mostram **o que aconteceu**; a matriz
mostra **o estado intermediario que o motor derivou** a partir disso, que e
a informacao que hoje so existe dentro de `Sinal.evidencia` e morre la.

A tese e simples: entre o dado cru e a decisao existe uma camada de
conclusoes — dominancia, faixa de conviccao, magnitude relativa, virada da
micro, procedencia da deteccao, estagio da confluencia — e essa camada e a
unica coisa que o operador nao consegue reconstruir olhando a tela. Um
`CONFIRMADO` que aparece sem que se veja **por que** e um oraculo; e oraculo
em pregao e o jeito mais caro de perder dinheiro.

Entao aqui todo veredito vem acompanhado do numero que o sustenta e do
limiar contra o qual ele foi julgado. `magnitude_relativa 0,84 · gate 0,60 ·
PASSA` e uma frase completa; `PASSA` sozinho nao e.

## O que a barra de referencia faz e o que fazemos diferente

`09_tape_reading_a.png` e `09_tape_reading_b.png` sao as telas de leitura de
fluxo do Profit Pro. As duas sofrem do mesmo mal: **sao tabelas de fatos, e
nenhuma coluna e uma conclusao.** `Qtd Co…`, `Qtd Ve…`, `Saldo`,
`Classifi…` — o produto entrega os ingredientes e deixa a sintese com o
operador, no meio do pregao. A unica coluna que tenta concluir alguma coisa
(`Classifi…`) esta **truncada e colidindo com o numero do saldo**
(`22:rrelevant`), o que e uma boa metafora do lugar que a conclusao ocupa
naquele desenho. Alem disso `09_tape_reading_b.png` e tema CLARO dentro de
uma plataforma escura (fraqueza F7) e `01_times_trades_a.png` gasta metade
da janela numa pizza 3D com legenda duplicada (F4).

Contra isso, tres escolhas:

1. **Nenhum numero sem seu limiar.** Toda faixa desenha a regua contra a
   qual o valor esta sendo lido — as faixas de conviccao (50 / 65 / 70 / 80)
   e o gate de magnitude ficam DESENHADOS no eixo, nao escondidos na
   documentacao. O operador ve a distancia ate o proximo estado.
2. **Procedencia junto do dado.** Deteccao vinda de livro inferido nao se
   parece com deteccao vinda de MBO observado: carrega a confianca e o
   rotulo da fonte na mesma linha. Foi caro conquistar essa distincao no
   nucleo (`microestrutura/detectores.py` propaga o minimo da cadeia); joga-
   la fora na tela seria desperdicio.
3. **Volume sem lado sempre visivel.** O RLP anonimiza ate 15% do volume de
   WDO/WIN. Uma tela que mostra dominancia e delta sem dizer quanto do
   volume nao tem lado esta afirmando mais do que sabe. A linha existe
   mesmo quando o valor e zero — some-la quando zera ensinaria o olho a
   nao procurar por ela justamente no dia em que ela importa.

## Estrutura: bandas fixas, e por que isso e a decisao de desempenho

O painel e uma pilha de SETE bandas de altura fixa (cabecalho, estagio,
dominancia, regua, magnitude, medidas, deteccoes). Cada banda e um `QRect`
calculado no redimensionamento, e `aplicar` compara o estado novo com o
velho **campo a campo, agrupado por banda**: dominancia mudou, suja a banda
da dominancia — 1 retangulo, 40px de altura, nao a tela.

A **regua** e banda separada da dominancia por essa mesma regra levada ao
limite: ela desenha os cortes 50/65/70/80, que dependem so da configuracao
do motor e nao mudam entre dois trades. Enquanto ela dividia retangulo com o
eixo, cada mudanca de dominancia repintava tambem os nove rotulos da regua —
e so isso ja punha a razao cheio/incremental abaixo do portao de 5x. O que
nao muda nao compartilha retangulo sujo com o que muda.

E a mesma regra do `PainelDenso` aplicada a um painel que nao e grade. Sem
isso a matriz seria o pior painel do produto: ela le a evidencia de TODO
trade, entao repintar por mudanca seria repintar o quadro inteiro a 500 Hz.

As deteccoes vivem num vetor de **slots de tela**, nao num historico:
`_deteccoes` tem exatamente o tamanho que cabe na banda, indexado por linha.
Deteccao nova entra pelo topo, o backing rola uma linha e a mais velha cai
do fim. Este projeto ja encontrou oito vezes a estrutura que cresce com o
estado acumulado; a nona nao vai ser esta.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from dataclasses import dataclass, fields, replace

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import PriceGrid
from fluxopro.metodologia.confianca import Confianca
from fluxopro.metodologia.regras import PARAMETROS, REGRAS
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, FaixaConviccao
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

# --------------------------------------------------------------------------
# Vocabulario — em portugues, do proprio projeto.
# --------------------------------------------------------------------------
ROTULO_ESTAGIO: dict[EstagioSinal, str] = {
    EstagioSinal.NENHUM: "NENHUM",
    EstagioSinal.DIRECAO_CONFIRMADA: "DIREÇÃO",
    EstagioSinal.NA_REGIAO: "REGIÃO",
    EstagioSinal.PRE_SINAL: "PRÉ-SINAL",
    EstagioSinal.CONFIRMADO: "CONFIRMADO",
}
"""A ordem do dict e a ordem do trilho — e a mesma de `_RANK` no motor."""

ROTULO_FAIXA: dict[FaixaConviccao, str] = {
    FaixaConviccao.LATERAL: "LATERAL",
    FaixaConviccao.PRE_DIRECIONAL: "PRÉ-DIRECIONAL",
    FaixaConviccao.ZONA_CINZA: "ZONA CINZA",
    FaixaConviccao.DIRECIONAL: "DIRECIONAL",
    FaixaConviccao.MAXIMA_CONVICCAO: "CONVICÇÃO MÁXIMA",
}

ROTULO_DETECCAO: dict[str, str] = {
    "ABSORCAO": "ABSORÇÃO",
    "ESCORA": "ESCORA",
    "ICEBERG": "ICEBERG",
    "LIQUIDEZ_FANTASMA": "LIQ. FANTASMA",
    "EXAUSTAO": "EXAUSTÃO",
    "CLIP_INSTITUCIONAL": "CLIP INSTIT.",
}

def procedencia_metodologica(nome_tipo: str) -> tuple[bool, str]:
    """`("EXAUSTAO")` -> `(False, "exaustao.conceito")`. DERIVADA do registro.

    A familia de regras de um detector e o proprio nome do tipo em minusculas
    (`EXAUSTAO` -> `exaustao.*`), e `fluxopro/metodologia/regras.py` responde
    o resto: se alguma regra da familia esta `implementada=True`, a deteccao
    e leitura do METODO; se a familia existe e nenhuma esta implementada, o
    registro ja decidiu que ela nao e (`exaustao.conceito` e `escora.formula`
    sao `AUSENTE_NA_FONTE`); se a familia nao existe, o registro nao sustenta
    nada — e a docstring de `regras.py` e explicita: "uma regra ausente do
    registro e uma regra que o produto nao sustenta".

    Derivar em vez de manter um `dict` aqui e a decisao que importa. Um mapa
    escrito na UI seria uma SEGUNDA fonte de procedencia, que envelhece em
    silencio no dia em que alguem implementar `absorcao.*` no pacote de
    metodologia — e o painel continuaria dizendo "generico" sobre uma regra
    do metodo. O registro valida no import; este painel apenas o le.
    """
    familia = nome_tipo.lower() + "."
    ids = tuple(i for i in REGRAS if i.startswith(familia))
    do_metodo = any(REGRAS[i].implementada for i in ids)
    return do_metodo, ids[0] if ids else ""


ROTULO_FONTE_MAGNITUDE: dict[str, str] = {
    "janela": "janela",
    "max_sessao": "pico sessão",
    "nenhuma": "sem referência",
}

MARCA_REGRA = "§"
"""Prefixo dos chips de procedencia de banda.

Existe para desfazer uma colisao que o retrato expos: `CONFIRMADO` e ao
mesmo tempo o ultimo ESTAGIO do `EstagioSinal` e o rotulo de maior confianca
do registro — e os dois apareciam na mesma banda, com o mesmo tamanho, a
poucos pixels de distancia. O `§` marca o chip como sendo sobre a REGRA e
nao sobre o mercado, e de quebra agrupa os quatro chips numa familia visual
que desce pela lateral do painel.

Renomear os rotulos seria a alternativa, e e pior: eles sao o vocabulario
literal de `metodologia/confianca.py`, e traduzi-los na tela quebraria a
unica ponte que o operador tem entre o que le e o registro que pode
auditar."""

ROTULO_CONFIANCA: dict[Confianca | None, str] = {
    Confianca.CONFIRMADO: "CONFIRMADO",
    Confianca.IMPRECISO: "IMPRECISO",
    Confianca.INFERIDO: "INFERIDO",
    Confianca.AUSENTE_NA_FONTE: "S/ FONTE",
    None: "S/ REGISTRO",
}
"""Nao ha regra nenhuma no registro cobrindo esta leitura.

Nao e o mesmo que `S/ FONTE`, e a diferenca importa: `S/ FONTE` significa
"olhamos a fonte, o conceito nao esta la, e o registro diz isso por escrito";
`S/ REGISTRO` significa "ninguem olhou ainda". O primeiro e auditavel, o
segundo e um buraco na auditoria."""

#: Ordem de gravidade. O chip de uma banda mostra a PIOR procedencia entre as
#: regras que a sustentam — a media esconderia exatamente o elo fraco.
#:
#: `SEM_REGISTRO` e o PIOR de todos, e nao o melhor, e a razao e a diferenca
#: entre "olhamos e o registro diz por escrito que a fonte nao tem isso"
#: (`AUSENTE_NA_FONTE`, auditavel) e "ninguem olhou" (um buraco na
#: auditoria). Um limiar vivo e calibravel que nao esta em `PARAMETROS` nao
#: pode contar como aval; e por isso que um unico parametro descoberto rebaixa
#: a banda inteira.
_GRAVIDADE: dict[Confianca | None, int] = {
    Confianca.CONFIRMADO: 0,
    Confianca.INFERIDO: 1,
    Confianca.IMPRECISO: 2,
    Confianca.AUSENTE_NA_FONTE: 3,
    None: 4,
}

SETA_COMPRA = "▲"
SETA_VENDA = "▼"
SEM_LADO = "·"

MAX_SLOTS_DETECCAO = 10
"""Teto de slots de deteccao, independente da altura da janela.

Era 24, e 24 davam **60% da superficie do painel** a esta banda. O numero
caiu por uma razao estrutural, nao estetica: `metodologia/regras.py` tem 42
regras, 33 implementadas, em 8 familias — e NENHUMA delas cobre os seis
membros de `TipoDeteccao`. `exaustao` e `escora` estao la como
`AUSENTE_NA_FONTE` com `implementada=False`; os outros quatro nao existem no
registro. Ou seja, a banda que ocupava a maior parte da tela era a unica cuja
procedencia o registro nao avaliza, enquanto as bandas de dominancia,
confluencia e micro — essas sim ancoradas em regras `CONFIRMADO` — dividiam o
resto.

Dez linhas continuam sendo estado (o que esta acontecendo agora) sem virar
log (o que aconteceu hoje) — para log existe a trilha de eventos do rodape,
e ela e consultavel."""

MIN_AMOSTRAS_RARIDADE = 30
"""Antes disto a fatia nao e publicada como veredito — sai `—`.

Aresta de aquecimento, e do mesmo tipo do `PASSA SEM MEDIR`: com
`fatia = n/total`, a PRIMEIRA deteccao da sessao sai 100% e nenhuma das cinco
primeiras consegue cruzar `FRACAO_RARA`. Um `CLIP_INSTITUCIONAL` isolado na
abertura — que e literalmente o evento mais raro que a tela pode receber —
aparecia como a coisa mais comum do painel, e um lote inicial de escoras
carimbava 68% num tipo que nao era excecao nenhuma.

Trinta amostras nao tornam a estimativa boa; tornam-na publicavel. Abaixo
disso o painel diz que ainda nao sabe, que e a mesma regra que ele aplica ao
gate de magnitude sem referencia."""

FRACAO_RARA = 0.20
"""Abaixo desta fatia da sessao, o tipo da linha e EXCECAO e a linha e marcada.

A banda tinha 24 linhas com a mesma caneta, o mesmo chip e a mesma barra de
32px: a unica linha anomala do retrato (`CLIP INSTIT.` no meio de 23
`EXAUSTÃO`) saia tipograficamente identica as outras. Numa superficie densa
isso e o defeito que mais custa, porque a pergunta que se faz varrendo uma
coluna e sempre "qual e a linha diferente?"."""

ESCALA_MAGNITUDE = 2.0
"""Fundo de escala da barra de magnitude relativa.

Fixo em 2,0 para que o MEIO da barra seja exatamente 1,0 — "a janela esta
tao desequilibrada quanto o pico de referencia do regime". Escala que se
adapta ao valor destruiria essa ancora: o operador leria a mesma posicao
significando coisas diferentes em dois momentos do dia."""


# --------------------------------------------------------------------------
# O que o painel consome
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LeituraMotor:
    """Estado derivado do motor num instante, ja reduzido ao que se desenha.

    Frozen e plano de proposito. O painel NAO segura `MotorSinais`,
    `MedidorAgressao` nem `CumulativeDelta`: se segurasse, cada quadro leria
    objetos vivos que a thread da fonte esta mutando, e a tela sairia
    costurada de dois instantes — o mesmo buraco que `ponte.Instantaneo`
    fecha para o DOM e o tape. Quem monta este retrato e `derivar`, uma vez
    por quadro, na thread do Qt.
    """

    estagio: EstagioSinal = EstagioSinal.NENHUM
    direcao: int = 0
    """+1 compra, -1 venda, 0 sem direcao. Inteiro e nao `Side` porque a
    comparacao acontece a cada quadro e `Enum.__hash__` e metodo Python —
    a mesma razao de `ponte._agressor_para_int`."""

    direcao_dominante: int = 0
    """O lado que DOMINA a janela, que nao e o mesmo que `direcao`.

    `direcao` e a direcao PUBLICADA — pos-histerese, so existe depois de o
    candidato persistir. `direcao_dominante` e a leitura instantanea do
    percentual. Enquanto o candidato acumula, o motor publica
    `NENHUM`/`None` e a janela ja esta 100% compradora: o farol tem de
    dizer "sem direcao" e o eixo de dominancia tem de apontar para a
    compra, ao mesmo tempo, porque as duas coisas sao verdade e sao
    diferentes.

    O primeiro retrato deste painel mostrou o custo de confundi-las: eixo
    em 100%, cursor colado na ponta da COMPRA e o numero grafado sem sinal,
    em cinza, como se o lado fosse desconhecido."""

    faixa: FaixaConviccao = FaixaConviccao.LATERAL
    dominancia: float = 0.5
    magnitude: int = 0
    magnitude_referencia: float | None = None
    magnitude_relativa: float = 1.0
    magnitude_fonte: str = "nenhuma"
    bloqueio: str = ""
    na_regiao: bool = False
    persistencia_trades: int = 0

    delta_sessao: int = 0
    delta_micro_antigo: int = 0
    delta_micro_recente: int = 0

    agressao_saldo: int = 0
    agressao_taxa_compra: float = 0.0
    agressao_trades_s: float = 0.0

    volume_sem_lado: int = 0
    volume_total: int = 0

    @property
    def delta_micro(self) -> int:
        return self.delta_micro_antigo + self.delta_micro_recente

    @property
    def lado_dominancia(self) -> int:
        """Lado a usar no eixo: o dominante, com a direcao publicada como rede.

        A evidencia so carrega `direcao_dominante` quando a faixa e
        direcional E o gate de magnitude passou; fora disso a dominancia e
        baixa e o cursor fica perto do centro de qualquer jeito."""
        return self.direcao_dominante or self.direcao


@dataclass(frozen=True, slots=True)
class ItemDeteccao:
    """Uma deteccao reduzida ao que a linha mostra — inclusive as DUAS duvidas.

    `inferida` responde "de onde veio o DADO" (livro MBO observado x MBP
    reconstruido). `do_metodo` responde "de onde veio a REGRA" (leitura do
    metodo x componente generico de order flow, de origem interna do
    projeto). Sao perguntas independentes e o painel gastava uma coluna
    inteira so na primeira: uma deteccao podia sair com dado 100% observado e
    a tela nao dizia que a REGRA que a produziu nao existe na fonte.
    """

    timestamp_ns: int
    rotulo: str
    price: int | None
    lado: int
    confianca: float
    inferida: bool
    do_metodo: bool = False
    regra_id: str = ""
    n_tipo: int = 0
    fracao_tipo: float = -1.0
    """Fatia da sessao que o tipo desta linha representava QUANDO ELA CHEGOU.

    Negativa quando a sessao ainda nao tinha `MIN_AMOSTRAS_RARIDADE`
    deteccoes: nesse caso a fatia nao e publicada, porque com tres eventos na
    sessao toda fatia e enorme e o mais raro dos tipos sai como o mais comum.

    Congelada na chegada, e nao recalculada a cada quadro, por duas razoes.
    A primeira e honestidade: cada linha e um fato de um instante, e o numero
    ao lado dela descreve aquele instante — recalcular faria a tela reescrever
    o passado. A segunda e estrutural: se a chegada de uma deteccao mudasse o
    numero de todas as outras, a banda inteira teria de ser repintada a cada
    evento, e o `rolar()` de uma linha — que e o que mantem esta peca dentro
    do portao de desempenho — deixaria de valer."""


def item_de_deteccao(objeto: object) -> ItemDeteccao | None:
    """Converte `Deteccao` ou `DeteccaoAnotada` num item de tela.

    Aceita os dois por getattr em vez de `isinstance` para nao arrastar
    `fluxopro.app` para dentro da camada de UI — `app` monta a sessao e
    conhece a UI; a UI conhecendo `app` de volta fecharia o ciclo. O que a
    funcao exige e o contrato minimo (`tipo`, `side`, `confianca`), e o que
    ela prefere quando existe e a versao ANOTADA: `confianca_efetiva` ja
    carrega o minimo da cadeia de procedencia, e e essa que vale.
    """
    deteccao = getattr(objeto, "deteccao", objeto)
    tipo = getattr(deteccao, "tipo", None)
    confianca_bruta = getattr(deteccao, "confianca", None)
    if tipo is None or confianca_bruta is None:
        return None

    confianca = float(getattr(objeto, "confianca_efetiva", confianca_bruta))
    inferida = getattr(objeto, "inferida", None)
    if inferida is None:
        fonte = getattr(objeto, "fonte", None)
        inferida = getattr(fonte, "name", "") == "MBP_INFERIDO" or confianca < 1.0
    nome_tipo = getattr(tipo, "value", str(tipo))
    do_metodo, regra_id = procedencia_metodologica(nome_tipo)
    lado = getattr(getattr(deteccao, "side", None), "name", "")
    return ItemDeteccao(
        timestamp_ns=int(getattr(deteccao, "timestamp_ns", 0)),
        rotulo=ROTULO_DETECCAO.get(nome_tipo, nome_tipo),
        price=getattr(deteccao, "price", None),
        lado=1 if lado == "BUY" else (-1 if lado == "SELL" else 0),
        confianca=confianca,
        inferida=bool(inferida),
        do_metodo=do_metodo,
        regra_id=regra_id,
    )


def derivar(
    sinal: object | None,
    agressao: object | None = None,
    delta: object | None = None,
    anterior: LeituraMotor | None = None,
) -> LeituraMotor:
    """Monta a `LeituraMotor` do quadro a partir das pecas vivas.

    `sinal` e o ultimo `Sinal` recebido; `agressao` e `delta` sao o
    `MedidorAgressao` e o `CumulativeDelta` da sessao, lidos por property.

    **`anterior` nao e conveniencia, e correcao.** `SessaoFluxo` emite
    `Sinal` so na MUDANCA de estagio (`emitir_apenas_mudanca_de_estagio`),
    entao entre duas mudancas nao chega sinal nenhum — e um quadro que
    zerasse a dominancia por falta de sinal mostraria "LATERAL 50%" no meio
    de um pregao direcional. Sem sinal novo, os campos do motor sao os do
    quadro anterior; os de analytics, esses, sao lidos sempre.
    """
    base = anterior if anterior is not None else LeituraMotor()
    campos: dict[str, object] = {
        "estagio": base.estagio,
        "direcao": base.direcao,
        "direcao_dominante": base.direcao_dominante,
        "faixa": base.faixa,
        "dominancia": base.dominancia,
        "magnitude": base.magnitude,
        "magnitude_referencia": base.magnitude_referencia,
        "magnitude_relativa": base.magnitude_relativa,
        "magnitude_fonte": base.magnitude_fonte,
        "bloqueio": base.bloqueio,
        "na_regiao": base.na_regiao,
        "persistencia_trades": base.persistencia_trades,
        "delta_micro_antigo": base.delta_micro_antigo,
        "delta_micro_recente": base.delta_micro_recente,
    }

    if sinal is not None:
        evidencia = getattr(sinal, "evidencia", None) or {}
        estagio = getattr(sinal, "estagio", None)
        if isinstance(estagio, EstagioSinal):
            campos["estagio"] = estagio
        nome_direcao = getattr(getattr(sinal, "direcao", None), "name", "")
        campos["direcao"] = 1 if nome_direcao == "BUY" else (-1 if nome_direcao == "SELL" else 0)
        campos["dominancia"] = float(evidencia.get("dominancia", base.dominancia))
        dominante = evidencia.get("direcao_dominante")
        if dominante is not None:
            campos["direcao_dominante"] = 1 if dominante == "BUY" else -1
        rotulo_faixa = evidencia.get("faixa")
        if rotulo_faixa is not None:
            campos["faixa"] = FaixaConviccao(rotulo_faixa)
        campos["magnitude"] = int(evidencia.get("magnitude", base.magnitude))
        campos["magnitude_referencia"] = evidencia.get(
            "magnitude_referencia", base.magnitude_referencia
        )
        campos["magnitude_relativa"] = float(
            evidencia.get("magnitude_relativa", base.magnitude_relativa)
        )
        campos["magnitude_fonte"] = str(
            evidencia.get("magnitude_referencia_fonte", base.magnitude_fonte)
        )
        # `bloqueio` so aparece na evidencia QUANDO bloqueia. Ausente
        # significa "nao bloqueou neste trade", nao "mantem o bloqueio de
        # antes" — herdar aqui deixaria o gate aceso depois de liberado.
        campos["bloqueio"] = str(evidencia.get("bloqueio", ""))
        campos["na_regiao"] = bool(evidencia.get("na_regiao", False))
        campos["persistencia_trades"] = int(evidencia.get("persistencia_trades", 0))
        campos["delta_micro_antigo"] = int(
            evidencia.get("delta_micro_primeira_metade", base.delta_micro_antigo)
        )
        campos["delta_micro_recente"] = int(
            evidencia.get("delta_micro_segunda_metade", base.delta_micro_recente)
        )

    if agressao is not None:
        campos["agressao_saldo"] = int(agressao.saldo_agressao)
        campos["agressao_taxa_compra"] = float(agressao.taxa_compra)
        campos["agressao_trades_s"] = float(agressao.velocidade_trades_por_segundo())
    else:
        campos["agressao_saldo"] = base.agressao_saldo
        campos["agressao_taxa_compra"] = base.agressao_taxa_compra
        campos["agressao_trades_s"] = base.agressao_trades_s

    if delta is not None:
        campos["delta_sessao"] = int(delta.delta_sessao)
        campos["volume_sem_lado"] = int(delta.volume_nao_atribuido_sessao)
        campos["volume_total"] = int(delta.volume_total_sessao)
    else:
        campos["delta_sessao"] = base.delta_sessao
        campos["volume_sem_lado"] = base.volume_sem_lado
        campos["volume_total"] = base.volume_total

    return LeituraMotor(**campos)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Bandas
# --------------------------------------------------------------------------
BANDA_CABECALHO = 0
BANDA_ESTAGIO = 1
BANDA_DOMINANCIA = 2
BANDA_REGUA = 3
BANDA_MAGNITUDE = 4
BANDA_MEDIDAS = 5
BANDA_DETECCOES = 6
N_BANDAS = 7

ALTURA_ESTAGIO = 40
ALTURA_DOMINANCIA = 40
ALTURA_REGUA = 16
ALTURA_MAGNITUDE = 36
ALTURA_ROTULO = 16
ALTURA_COLUNAS = 14
"""Faixa dos cabecalhos de coluna da banda de deteccoes.

Ela nao existia, e por isso `1,00`, `MBO`, o preco e a hora eram numeros sem
nome nem unidade — o leitor tinha de inferir o significado de cada coluna
pelo formato. E o mesmo defeito que §1 cobra da referencia em F6/F8, cometido
por omissao em vez de por truncamento."""
"""Multiplos de 4 (§3.4). Nada de 5, 7, 13."""

#: A REGUA e banda propria de proposito, e nao um pedaco da dominancia.
#: Ela depende so da configuracao do motor (50 / 65 / 70 / 80), entao nao
#: muda entre dois trades — e mobiliario, nao dado. Junta na mesma banda,
#: ela era repintada a cada mudanca de dominancia e sozinha respondia por
#: quase metade do custo do quadro incremental (a razao cheio/incremental
#: media 4,9x; separada, passa de 8x). A regra geral que isto instancia: o
#: que nao muda nao pode compartilhar retangulo sujo com o que muda.

CAMPOS_DA_BANDA: dict[int, tuple[str, ...]] = {
    # O FAROL depende de TODA a configuracao do motor, e por isso a sua lista
    # nao e escrita: e derivada. O estagio e a confluencia das tres condicoes
    # mais a histerese, entao qualquer botao que mova `MotorSinais` move o
    # farol — inclusive o cache da regiao, que decide se a condicao 2 e
    # reavaliada. Derivar em vez de listar tem uma consequencia que e o ponto:
    # o conjunto do farol e SUPERCONJUNTO do de qualquer outra banda, logo a
    # procedencia dele nunca pode ser melhor que a de nenhuma delas.
    #
    # Foi exatamente isso que a versao anterior errou. Ela pendurava o farol
    # numa unica regra `CONFIRMADO` escolhida a mao e pintava o chip de verde,
    # enquanto a banda MEDIDAS — movida pelo MESMO `janela_micro_ns` — exibia
    # ambar. Duas bandas, o mesmo parametro sem fonte, chips contraditorios na
    # mesma tela; e no canal degradado o que melhor sobrevivia era justamente
    # o verde falso.
    BANDA_ESTAGIO: tuple(f.name for f in fields(ConfigMotorSinais)),
    BANDA_DOMINANCIA: (
        "janela_dominancia_ns",
        "faixa_lateral_ate",
        "faixa_pre_direcional_ate",
        "dominancia_minima",
        "faixa_maxima_conviccao_desde",
    ),
    BANDA_MAGNITUDE: (
        "janela_dominancia_ns",
        "magnitude_relativa_minima",
        "tamanho_topo_magnitude",
        "fator_dominio_trade_unico",
        "minimo_amostras_referencia",
        "amostras_por_bloco_referencia",
        "blocos_referencia",
    ),
    BANDA_MEDIDAS: ("janela_micro_ns", "pre_sinal_fracao_janela_micro"),
}
"""Quais botoes de `ConfigMotorSinais` movem os numeros de cada banda.

Nao ha um unico id de regra escrito nesta camada, e isso e deliberado. A
versao anterior tinha um `dict` banda -> regra digitado a mao, sem validacao
e sem teste, 370 linhas abaixo da propria docstring que argumentava que "um
mapa escrito na UI seria uma SEGUNDA fonte de procedencia, que envelhece em
silencio". Envelheceu: trocar a regra do farol por `risco.mao_cheia` —
tamanho de posicao, nada a ver com confluencia — passava com a suite inteira
verde.

Agora a UI declara apenas PARAMETROS, que sao fatos sobre o CODIGO e nao
sobre a fonte, e tres coisas os constrangem:

* `_validar_campos()` roda no import e recusa nome que nao seja campo real de
  `ConfigMotorSinais`;
* `tests/test_ui_matriz.py` le `motor/sinais.py` com `ast` e exige que a
  uniao dos campos declarados seja EXATAMENTE o conjunto de botoes que o
  motor de fato consulta — botao novo sem procedencia reprova, nome morto
  reprova;
* e a regra vem do registro, por `regras_do_campo`. Nao ha o que digitar
  errado."""


def _validar_campos() -> None:
    reais = {f.name for f in fields(ConfigMotorSinais)}
    for banda, campos in CAMPOS_DA_BANDA.items():
        if not campos:
            raise ValueError(f"banda {banda} sem parametro declarado")
        desconhecidos = set(campos) - reais
        if desconhecidos:
            raise ValueError(
                f"banda {banda}: {sorted(desconhecidos)} nao sao campos de "
                "ConfigMotorSinais"
            )


_validar_campos()


@lru_cache(maxsize=None)
def regras_do_campo(campo: str) -> tuple[str, ...]:
    """Regras do registro que respondem por `ConfigMotorSinais.<campo>`.

    Procura o nome QUALIFICADO — `ConfigMotorSinais.dominancia_minima`, e nao
    `dominancia_minima` — em `PARAMETROS` e nas notas de `REGRAS`. A
    qualificacao nao e capricho: `janela_micro_ns` existe em
    `ConfigMotorSinais` e em `ConfigMacroMicro`, e `macro_micro.janela_micro`
    responde pelo segundo. Casar pelo nome curto faria a UI reivindicar um
    aval dado a outro componente — a mesma falha que a recusa da banda
    MAGNITUDE evita do lado oposto.

    Devolve tupla vazia quando o registro nao cobre o botao, e e assim que o
    limiar vivo que ninguem registrou aparece na tela em vez de sumir.

    Memoizada porque o registro e imutavel depois do import e isto roda no
    caminho de DESENHO: sem o cache, cada quadro cheio varria as 42 notas
    de `REGRAS` uma vez por botao de cada banda — 34 varreduras por quadro,
    medidas em 31 ms de quadro cheio contra os 16 ms do orcamento de 60 Hz.
    """
    alvo = "ConfigMotorSinais." + campo
    achadas = {p.regra_id for p in PARAMETROS if p.nome == alvo}
    achadas.update(i for i, r in REGRAS.items() if alvo in r.nota)
    return tuple(sorted(achadas))


MARGEM = 8

_MAX_TIPOS = 32
"""Teto de chaves da contagem por tipo. `TipoDeteccao` tem seis membros; o
teto e rede contra fonte que invente rotulo, nao politica de crescimento."""

#: Posicoes das colunas da banda de deteccoes, em pixels a partir da borda.
#: Uma tupla so, usada pelo CABECALHO e pela LINHA — se as duas calculassem
#: por conta propria, a primeira mudanca de largura desalinharia o rotulo do
#: dado, que e a forma mais barata de mentir numa tabela.
COL_REGRA, COL_TIPO, COL_PRECO, COL_LADO = 8, 70, 160, 226
COL_CONF_BARRA, COL_CONF_NUM, COL_DADO, COL_RARIDADE = 258, 294, 330, 410
LARGURA_RARIDADE = 64
#: O vao entre `COL_LADO` e `COL_CONF_BARRA` e maior do que a seta de 14px
#: precisa. Nao e folga: e o espaco de que o ROTULO `LD` precisa para caber
#: inteiro. Coluna cujo cabecalho nao cabe teria de sair pela regra F8, e uma
#: coluna direcional sem nome e exatamente o tipo de omissao que este painel
#: cobra da referencia.

ROTULOS_COLUNA: tuple[tuple[int, str], ...] = (
    (COL_REGRA, "REGRA"),
    (COL_TIPO, "TIPO"),
    (COL_PRECO, "PREÇO"),
    (COL_LADO, "LD"),
    (COL_CONF_BARRA, "CONF"),
    (COL_DADO, "DADO"),
    (COL_RARIDADE, "FATIA À CHEGADA"),
)


class PainelMatriz(PainelDenso):
    """A superficie densa do estado derivado."""

    def __init__(
        self,
        grid: PriceGrid,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        config: ConfigMotorSinais | None = None,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.densidade = densidade
        self.paleta = paleta
        # Os limiares vem do MOTOR, nunca cravados aqui. Quem calibrar o
        # `dominancia_minima` para 0,75 ve a regua andar na tela junto — e
        # uma regua que mente sobre o corte e pior que regua nenhuma.
        self.config = config if config is not None else ConfigMotorSinais()

        self._leitura: LeituraMotor | None = None
        self._n_slots = 0
        self._deteccoes: list[ItemDeteccao | None] = []
        self._n_deteccoes = 0
        self._n_metodo = 0
        # Contagem por TIPO. Limitada por construcao: as chaves possiveis sao
        # os membros de `TipoDeteccao`, seis hoje. O teto de `_MAX_TIPOS` e
        # rede contra uma fonte que invente rotulo — nao e uma estrutura que
        # cresce com o numero de eventos, e sim com o numero de tipos.
        self._por_tipo: dict[str, int] = {}
        self._escala_medidas = 1

        self._bandas: list[QRect] = [QRect() for _ in range(N_BANDAS)]
        self._fm_grade = QFontMetrics(tokens.fonte_numero(densidade.fonte_grade))
        self._fm_rotulo = QFontMetrics(tokens.fonte_rotulo())

        self.setMinimumSize(360, 260)

    # ------------------------------------------------------------- geometria
    def ao_redimensionar(self, largura: int, altura: int) -> None:
        y = 0
        alturas = (
            self.densidade.altura_cabecalho,
            ALTURA_ESTAGIO,
            ALTURA_DOMINANCIA,
            ALTURA_REGUA,
            ALTURA_MAGNITUDE,
            ALTURA_ROTULO + 4 * self.densidade.altura_linha,
        )
        for indice, h in enumerate(alturas):
            self._bandas[indice] = QRect(0, y, largura, h)
            y += h
        self._bandas[BANDA_DETECCOES] = QRect(0, y, largura, max(0, altura - y))

        util = max(0, self._bandas[BANDA_DETECCOES].height() - ALTURA_ROTULO - ALTURA_COLUNAS)
        n = min(MAX_SLOTS_DETECCAO, util // self.densidade.altura_linha)
        if n != self._n_slots:
            self._redimensionar_slots(n)

    def _redimensionar_slots(self, n: int) -> None:
        """Vetor indexado por LINHA DA TELA, com o tamanho da tela.

        Encolher DESCARTA o excedente em vez de guardar "para quando a
        janela crescer de novo": guardar seria exatamente a estrutura que
        cresce com o estado acumulado, so que com nome de cache."""
        antigos = self._deteccoes[:n]
        self._deteccoes = antigos + [None] * (n - len(antigos))
        self._n_slots = n

    @property
    def _area_slots(self) -> QRect:
        banda = self._bandas[BANDA_DETECCOES]
        return QRect(
            0,
            banda.top() + ALTURA_ROTULO + ALTURA_COLUNAS,
            banda.width(),
            self._n_slots * self.densidade.altura_linha,
        )

    def _sujar_banda(self, indice: int) -> None:
        self.marcar_sujo(self._bandas[indice])

    # ---------------------------------------------------------------- dados
    def aplicar(
        self,
        leitura: LeituraMotor | None = None,
        eventos: Sequence[object] = (),
    ) -> None:
        """Absorve o quadro. Chamado pela janela, uma vez por quadro."""
        if leitura is not None:
            self._aplicar_leitura(leitura)
        if eventos:
            self._aplicar_eventos(eventos)

    def _aplicar_leitura(self, nova: LeituraMotor) -> None:
        velha = self._leitura
        self._leitura = nova
        if velha is None:
            self.marcar_tudo_sujo()
            self._ajustar_escala_medidas(nova)
            return

        # Uma banda por grupo de campos. E o que faz uma dominancia que muda
        # a cada trade custar ~50px de repintura em vez da tela inteira.
        if (velha.estagio, velha.direcao, velha.persistencia_trades, velha.na_regiao) != (
            nova.estagio,
            nova.direcao,
            nova.persistencia_trades,
            nova.na_regiao,
        ):
            self._sujar_banda(BANDA_ESTAGIO)
        if (velha.dominancia, velha.faixa, velha.lado_dominancia) != (
            nova.dominancia,
            nova.faixa,
            nova.lado_dominancia,
        ):
            self._sujar_banda(BANDA_DOMINANCIA)
        if (
            velha.magnitude,
            velha.magnitude_referencia,
            velha.magnitude_relativa,
            velha.magnitude_fonte,
            velha.bloqueio,
        ) != (
            nova.magnitude,
            nova.magnitude_referencia,
            nova.magnitude_relativa,
            nova.magnitude_fonte,
            nova.bloqueio,
        ):
            self._sujar_banda(BANDA_MAGNITUDE)
        if (
            velha.delta_sessao,
            velha.delta_micro_antigo,
            velha.delta_micro_recente,
            velha.agressao_saldo,
            round(velha.agressao_taxa_compra, 3),
            round(velha.agressao_trades_s, 0),
            velha.volume_sem_lado,
            velha.volume_total,
        ) != (
            nova.delta_sessao,
            nova.delta_micro_antigo,
            nova.delta_micro_recente,
            nova.agressao_saldo,
            round(nova.agressao_taxa_compra, 3),
            round(nova.agressao_trades_s, 0),
            nova.volume_sem_lado,
            nova.volume_total,
        ):
            self._sujar_banda(BANDA_MEDIDAS)
        self._ajustar_escala_medidas(nova)

    def _ajustar_escala_medidas(self, leitura: LeituraMotor) -> None:
        """Escala das barras bipolares — quantizada 1-2-5, com histerese.

        Mesma licao do DOM: seguir o maximo exato obrigaria a redesenhar a
        banda a cada trade so porque o fundo de escala andou um contrato, e
        o ganho da regiao suja iria embora pela porta dos fundos."""
        pico = max(
            abs(leitura.delta_sessao),
            abs(leitura.agressao_saldo),
            abs(leitura.delta_micro),
            1,
        )
        alvo = _degrau_1_2_5(pico)
        if alvo > self._escala_medidas or pico * 4 < self._escala_medidas:
            self._escala_medidas = max(1, alvo)
            self._sujar_banda(BANDA_MEDIDAS)

    def _aplicar_eventos(self, eventos: Sequence[object]) -> None:
        novos: list[ItemDeteccao] = []
        for evento in eventos:
            item = item_de_deteccao(evento)
            if item is not None:
                novos.append(item)
        if not novos or self._n_slots <= 0:
            return
        self._n_metodo += sum(1 for i in novos if i.do_metodo)
        # UM DE CADA VEZ, e nao o lote inteiro contra o total final. A
        # primeira versao somava `len(novos)` ao total antes de carimbar, e
        # a primeira linha de um lote de dez saia com 1/10 = 10% — marcada
        # como excecao mesmo quando as dez eram do mesmo tipo. A fatia de uma
        # linha e a fatia que existia no instante EM QUE ELA CHEGOU.
        novos = [self._com_raridade(item) for item in novos]

        # Chegou mais do que cabe? So os ultimos importam — rolar seria mover
        # pixels que vao ser todos sobrescritos.
        if len(novos) >= self._n_slots:
            novos = novos[-self._n_slots :]
            self._deteccoes = list(reversed(novos))
            self.marcar_tudo_sujo()
            return

        n = len(novos)
        for item in novos:
            self._deteccoes.insert(0, item)
        del self._deteccoes[self._n_slots :]
        self.rolar(0, n * self.densidade.altura_linha, self._area_slots)
        # O contador do cabecalho da banda tambem mudou. Duas faixas sujas
        # no total, nunca a tela.
        self.marcar_sujo(
            QRect(0, self._bandas[BANDA_DETECCOES].top(), self.width(), ALTURA_ROTULO)
        )

    def _com_raridade(self, item: ItemDeteccao) -> ItemDeteccao:
        """Carimba a fatia do tipo na sessao, no instante da chegada."""
        contagem = self._por_tipo
        if item.rotulo not in contagem and len(contagem) >= _MAX_TIPOS:
            self._n_deteccoes += 1
            return item
        self._n_deteccoes += 1
        n = contagem.get(item.rotulo, 0) + 1
        contagem[item.rotulo] = n
        if self._n_deteccoes < MIN_AMOSTRAS_RARIDADE:
            # Sem amostra bastante a fatia nao e publicada. `fracao_tipo`
            # negativa e o sinalizador, e nao um valor a desenhar.
            return replace(item, n_tipo=n, fracao_tipo=-1.0)
        return replace(item, n_tipo=n, fracao_tipo=n / self._n_deteccoes)

    @property
    def n_deteccoes(self) -> int:
        """Total recebido na sessao — o contador, nao a retencao."""
        return self._n_deteccoes

    @property
    def n_deteccoes_do_metodo(self) -> int:
        """Quantas das recebidas sao leitura do metodo (e nao componente
        generico). Hoje, com o registro atual, e sempre ZERO — e esse zero e
        um achado do produto, nao um bug do painel."""
        return self._n_metodo

    @property
    def deteccoes_visiveis(self) -> tuple[ItemDeteccao | None, ...]:
        return tuple(self._deteccoes)

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        # SO as bandas que cruzam a regiao suja — e cada banda recebe a
        # regiao para poder afinar mais ainda. Sem esse segundo nivel, uma
        # deteccao nova (1 linha de 18px) faria a banda inteira redesenhar
        # as suas 20 linhas: o clip do Qt jogaria fora os pixels, mas o laco
        # Python teria rodado, e §2 mediu que o laco E o custo.
        for indice, banda in enumerate(self._bandas):
            if banda.isValid() and banda.intersects(regiao):
                _DESENHOS[indice](self, painter, banda, regiao)

    # ------------------------------------------------------------ procedencia
    def _chip_regras(self, painter: QPainter, x: int, linha: QRect, banda: int) -> int:
        """Desenha a procedencia da BANDA e devolve o x seguinte.

        Esta e a resposta a uma pergunta que a rodada anterior deixou meio
        respondida. O painel passou a dizer, deteccao por deteccao, que a
        regra e generica — e ficou parecendo que o produto inteiro nao tem
        lastro. Nao e o caso: `dominancia.faixas`, `dominancia.nao_e_gatilho`
        e `macro_micro.micro` sao `CONFIRMADO` no registro, com citacao e
        video. O que faltava era a tela DIZER isso onde a leitura acontece.

        Entao toda banda declara a sua procedencia, pelo mesmo mecanismo e no
        mesmo vocabulario das deteccoes — e a assimetria fica legivel de uma
        varredura so: o topo do painel e metodo, a banda de baixo nao e.

        A conta e do PIOR elo, nunca da media: uma banda sustentada por uma
        regra `CONFIRMADO` e uma `IMPRECISO` e imprecisa.
        """
        rotulo, cor = self._procedencia_de(CAMPOS_DA_BANDA[banda])
        largura = self._fm_rotulo.horizontalAdvance(rotulo) + 12
        if x + largura > linha.right():
            return x
        altura = max(10, linha.height() - 6)
        self._chip(
            painter,
            QRect(x, linha.top() + (linha.height() - altura) // 2, largura, altura),
            rotulo,
            cor,
        )
        return x + largura + 8

    def _procedencia_de(self, campos: tuple[str, ...]) -> tuple[str, QColor]:
        """`(rotulo, cor)` da procedencia de um conjunto de botoes do motor.

        Duas grandezas numa string so, porque separa-las deixaria o canal
        entregar uma sem a outra:

        * **a pior procedencia** entre as regras ligadas aos botoes, com botao
          NAO COBERTO contando como o pior de todos;
        * **a cobertura** `k/n` — de quantos dos botoes que movem esta leitura
          o registro de fato responde.

        Com o registro de hoje isso da `§ S/ REGISTRO 1/5` na dominancia e
        `§ S/ REGISTRO 1/20` no farol: o unico botao de `ConfigMotorSinais`
        que o registro cobre e `dominancia_minima`, por
        `dominancia.limiar_direcional`. O numero e chato de ler e e a verdade;
        a versao anterior lia `§ CONFIRMADO` em verde e era mentira.
        """
        pior: Confianca | None = Confianca.CONFIRMADO
        cobertos = 0
        for campo in campos:
            ids = regras_do_campo(campo)
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

    # ------------------------------------------------------------------ chip
    def _chip(self, painter: QPainter, rect: QRect, texto: str, fundo) -> None:
        """Bloco PREENCHIDO com texto escuro dentro — a forma que atravessa o canal.

        A lei desta rodada saiu de uma medicao: a transmissao **preserva o
        veredito e apaga a ressalva**, porque veredito e grande e saturado e
        ressalva e pequena e apagada. Texto de 10px em `--text-muted` some a
        72% de escala com JPEG 40; um retangulo cheio de 60x12 nao some,
        porque compressao com perdas ataca borda fina de alto contraste, nao
        area chapada.

        Entao toda ressalva que precisa sobreviver vira chip, e nunca legenda
        ao lado. Contrastes do texto escuro (`--bg-base`) sobre os fundos
        usados aqui: 5,37:1 no `--neutral`, 9,57:1 no `--ok`, 12,34:1 no
        `--alert` — todos AA ou melhor, recalculados por `test_ui_tokens`.
        """
        painter.fillRect(rect, fundo)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.BG_BASE)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)

    # ------------------------------------------------------------- cabecalho
    def _desenhar_cabecalho(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        painter.fillRect(banda, tokens.BG_RAISED)
        interno = banda.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "MATRIZ DE ESTADO",
        )
        # As JANELAS do motor, e nao um slogan: sem elas "dominancia" e
        # "delta micro" sao numeros sem unidade de tempo, e o operador nao
        # tem como saber se esta lendo cinco minutos ou o dia inteiro.
        painter.setPen(tokens.TEXT_MUTED)
        painter.setFont(tokens.fonte_numero(10))
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "janela %s · micro %s"
            % (
                _duracao(self.config.janela_dominancia_ns),
                _duracao(self.config.janela_micro_ns),
            ),
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, banda.bottom(), banda.width(), banda.bottom())

    # --------------------------------------------------------------- estagio
    def _desenhar_estagio(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        painter.fillRect(banda, self.cor_fundo)
        leitura = self._leitura
        rotulo = QRect(MARGEM, banda.top(), banda.width() - 2 * MARGEM, ALTURA_ROTULO)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            rotulo,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "CONFLUÊNCIA",
        )
        self._chip_regras(painter, MARGEM + 88, rotulo, BANDA_ESTAGIO)
        if leitura is not None:
            self._desenhar_direcao(painter, rotulo, leitura)

        trilho = QRect(
            MARGEM,
            banda.top() + ALTURA_ROTULO,
            banda.width() - 2 * MARGEM,
            banda.height() - ALTURA_ROTULO - 4,
        )
        estagios = list(ROTULO_ESTAGIO)
        atual = leitura.estagio if leitura is not None else EstagioSinal.NENHUM
        rank_atual = estagios.index(atual)
        largura = (trilho.width() - 4 * 4) // len(estagios)
        for i, estagio in enumerate(estagios):
            caixa = QRect(trilho.left() + i * (largura + 4), trilho.top(), largura, trilho.height())
            if i == rank_atual:
                fundo = self._cor_estagio(estagio)
                texto = tokens.BG_BASE
            elif i < rank_atual:
                fundo = tokens.BG_RAISED
                texto = tokens.TEXT_SECONDARY
            else:
                fundo = self.cor_fundo
                texto = tokens.TEXT_MUTED
            painter.fillRect(caixa, fundo)
            if i > rank_atual:
                painter.setPen(tokens.BORDER)
                painter.drawRect(caixa.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(texto)
            painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, ROTULO_ESTAGIO[estagio])

    def _desenhar_direcao(self, painter: QPainter, rotulo: QRect, leitura: LeituraMotor) -> None:
        """Direcao com os TRES portadores de §3.2: seta, palavra e cor.

        A palavra e o que sobrevive a `PALETA_SEM_COR`; a seta e o que
        sobrevive a um print de baixa resolucao; a cor e o que o olho pega
        sem ler. Nenhum dos tres sozinho e o dado."""
        if leitura.direcao > 0:
            texto = SETA_COMPRA + " COMPRA"
        elif leitura.direcao < 0:
            texto = SETA_VENDA + " VENDA"
        else:
            texto = SEM_LADO + " SEM DIREÇÃO"
        if leitura.persistencia_trades:
            texto += f"  ({leitura.persistencia_trades} neg)"
        painter.setFont(tokens.fonte_ui(11, 600))
        painter.setPen(self.paleta.direcional(leitura.direcao))
        painter.drawText(
            rotulo, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto
        )

    def _cor_estagio(self, estagio: EstagioSinal) -> QColor:
        """§3.1: o estagio e SEGUNDO canal (estado do sistema), nunca direcao.

        Por isso amarelo/roxo/verde e nao azul/vermelho — o eixo direcional
        ja esta ocupado dizendo "para onde", e este diz "e dai"."""
        if estagio is EstagioSinal.CONFIRMADO:
            return tokens.SIGNAL
        if estagio is EstagioSinal.PRE_SINAL:
            return tokens.ALERT
        if estagio is EstagioSinal.NENHUM:
            return tokens.NEUTRAL
        return tokens.OK

    # ------------------------------------------------------------ dominancia
    def _desenhar_dominancia(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        painter.fillRect(banda, self.cor_fundo)
        leitura = self._leitura
        largura = banda.width() - 2 * MARGEM
        rotulo = QRect(MARGEM, banda.top(), largura, 20)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            rotulo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "DOMINÂNCIA"
        )
        x_faixa = self._chip_regras(
            painter, MARGEM + 76, rotulo, BANDA_DOMINANCIA
        )
        if leitura is not None:
            lado = leitura.lado_dominancia
            texto = self._leitura_de_dominancia(leitura)
            fonte_valor = tokens.fonte_numero(14, 600)
            painter.setFont(fonte_valor)
            painter.setPen(self.paleta.direcional(lado))
            # UM `drawText`, UMA fonte, UMA caneta. A ressalva nao e um campo
            # ao lado do numero — ela E o final da mesma string, e por isso
            # nenhuma reescala, nenhuma quantizacao e nenhum recorte de
            # coluna consegue entregar o numero sem ela.
            painter.drawText(
                rotulo,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                texto,
            )
            # A faixa so entra se couber INTEIRA, com o seu limiar junto. Meia
            # faixa ("DIRECIONAL", sem o >=70% e sem o aviso de divergencia)
            # seria a ressalva morrendo por falta de espaco, que e exatamente
            # o defeito desta rodada.
            faixa = self._rotulo_faixa(leitura.faixa)
            fonte_faixa = tokens.fonte_ui(11, 500)
            largura_valor = QFontMetrics(fonte_valor).horizontalAdvance(texto)
            largura_faixa = QFontMetrics(fonte_faixa).horizontalAdvance(faixa)
            espaco = rotulo.right() - largura_valor - 16 - x_faixa
            if largura_faixa <= espaco:
                painter.setFont(fonte_faixa)
                painter.setPen(tokens.TEXT_SECONDARY)
                painter.drawText(
                    QRect(x_faixa, rotulo.top(), espaco, rotulo.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    faixa,
                )

        self._desenhar_eixo_dominancia(painter, self._eixo_dominancia(), leitura)

    def _leitura_de_dominancia(self, leitura: LeituraMotor) -> str:
        """O percentual E a sua ressalva, numa string so.

        Duas ressalvas competem pelo lugar, e a ordem entre elas nao e
        arbitraria:

        1. **`NÃO CONFIRMADO`** — a janela ja esta 100% de um lado e o motor
           ainda NAO publicou direcao (histerese acumulando). O retrato
           degradado da rodada 1 entregava `+100,0%` e `CONVICÇÃO MÁXIMA` em
           corpo grande e perdia o `(1 neg)` que os desmentia: convicao
           maxima sobre uma leitura que o proprio motor ainda nao assinou.
        2. **`· N% S/ LADO`** — o RLP anonimiza ate 15% do volume de WDO/WIN,
           e um percentual calculado sobre 92% do tape nao e um percentual do
           tape. So aparece a partir de 1%, porque abaixo disso a ressalva
           custaria mais atencao do que corrige, e a linha `S/ LADO` da banda
           de medidas ja carrega o numero exato.

        Uma de cada vez, e nunca as duas: a string tem de caber ao lado do
        rotulo da faixa, e uma ressalva que empurra a outra para fora nao
        protege ninguem.
        """
        lado = leitura.lado_dominancia
        if lado == 0:
            base = formato.formatar_percentual(leitura.dominancia, casas=1).lstrip(
                formato.MAIS
            )
        else:
            assinado = leitura.dominancia if lado > 0 else -leitura.dominancia
            base = formato.formatar_percentual(assinado, casas=1)

        if lado != 0 and leitura.direcao == 0:
            return base + " NÃO CONFIRMADO"
        if leitura.volume_total:
            fracao = leitura.volume_sem_lado / leitura.volume_total
            if fracao >= 0.01:
                return (
                    base
                    + " · "
                    + formato.formatar_percentual(fracao, casas=0).lstrip(formato.MAIS)
                    + " S/ LADO"
                )
        return base

    def _rotulo_faixa(self, faixa: FaixaConviccao) -> str:
        """A faixa com o LIMIAR que a define, e o aviso de divergencia da fonte.

        Os cortes moravam so na regua, em 10px `--text-muted` — e a regua e a
        primeira coisa que o canal apaga. Sem ela, `CONVICÇÃO MÁXIMA` vira um
        adjetivo sem numero. Aqui o limiar viaja dentro do proprio rotulo, no
        mesmo corpo.

        `FONTE DIVERGE` nao e opiniao deste painel: sai de
        `metodologia/regras.py`, onde `dominancia.limiar_direcional` esta
        rotulada `IMPRECISO` porque um video diz 70% e outro 75% para o mesmo
        conceito. As duas faixas que esse corte define — ZONA_CINZA e
        DIRECIONAL — carregam o aviso; as outras nao, porque inventar
        divergencia onde o registro nao registra seria o mesmo pecado ao
        contrario.
        """
        cfg = self.config
        pct = _percentual_inteiro
        if faixa is FaixaConviccao.LATERAL:
            return "LATERAL ≤" + pct(cfg.faixa_lateral_ate)
        if faixa is FaixaConviccao.PRE_DIRECIONAL:
            return (
                "PRÉ-DIRECIONAL "
                + pct(cfg.faixa_lateral_ate)
                + "–"
                + pct(cfg.faixa_pre_direcional_ate)
            )
        # Derivado do BOTAO, nao de um id digitado: o corte de
        # `DIRECIONAL` e `ConfigMotorSinais.dominancia_minima`, e quem diz
        # se a fonte diverge sobre ele e o registro, via `vira_parametro`
        # (que e `IMPRECISO`). Um id escrito aqui seria a mesma segunda
        # fonte de procedencia que `CAMPOS_DA_BANDA` existe para eliminar.
        divergente = any(
            REGRAS[i].vira_parametro for i in regras_do_campo("dominancia_minima")
        )
        aviso = " · FONTE DIVERGE" if divergente else ""
        if faixa is FaixaConviccao.ZONA_CINZA:
            return (
                "ZONA CINZA "
                + pct(cfg.faixa_pre_direcional_ate)
                + "–"
                + pct(cfg.dominancia_minima)
                + " · SEM RÓTULO NA FONTE"
            )
        if faixa is FaixaConviccao.DIRECIONAL:
            return "DIRECIONAL ≥" + pct(cfg.dominancia_minima) + aviso
        return "CONVICÇÃO MÁXIMA ≥" + pct(cfg.faixa_maxima_conviccao_desde)

    def _eixo_dominancia(self) -> QRect:
        banda = self._bandas[BANDA_DOMINANCIA]
        return QRect(MARGEM, banda.top() + 20, banda.width() - 2 * MARGEM, 18)

    def _desenhar_regua(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        """Mobiliario: so muda quando a JANELA ou a CONFIGURACAO mudam."""
        painter.fillRect(banda, self.cor_fundo)
        self._desenhar_regua_dominancia(
            painter,
            self._eixo_dominancia(),
            QRect(MARGEM, banda.top(), banda.width() - 2 * MARGEM, banda.height()),
        )

    def _cortes_dominancia(self) -> tuple[float, ...]:
        cfg = self.config
        return (
            0.5,
            cfg.faixa_pre_direcional_ate,
            cfg.dominancia_minima,
            cfg.faixa_maxima_conviccao_desde,
            1.0,
        )

    def _x_de(self, eixo: QRect, dominancia: float, sentido: int) -> int:
        """Posicao de uma dominancia no eixo bipolar.

        Centro = 50% (empate); direita = compra; esquerda = venda. Ter os
        dois lados no MESMO eixo, partindo do mesmo centro, e o que torna a
        comparacao honesta — e o oposto do que a aba Profundidade do Profit
        faz com bid e ask (fraqueza F5)."""
        centro = eixo.left() + eixo.width() // 2
        meia = eixo.width() // 2 - 1
        fracao = max(0.0, min(1.0, (dominancia - 0.5) / 0.5))
        return centro + sentido * int(fracao * meia)

    def _desenhar_eixo_dominancia(
        self, painter: QPainter, eixo: QRect, leitura: LeituraMotor | None
    ) -> None:
        painter.fillRect(eixo, tokens.BG_RAISED)
        cortes = self._cortes_dominancia()
        for sentido in (-1, 1):
            if sentido > 0:
                rampa = tokens.RAMPA_COMPRA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA
            else:
                rampa = tokens.RAMPA_VENDA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA
            for i in range(len(cortes) - 1):
                x0 = self._x_de(eixo, cortes[i], sentido)
                x1 = self._x_de(eixo, cortes[i + 1], sentido)
                esquerda, direita = min(x0, x1), max(x0, x1)
                # Intensidade cresce com a faixa: o degrau e a segunda
                # leitura, para quem so bate o olho e nao le a regua.
                cor = rampa[tokens.degrau((i + 1) / (len(cortes) - 1) * 0.9)]
                painter.fillRect(
                    QRect(esquerda, eixo.top() + 2, max(1, direita - esquerda), eixo.height() - 4),
                    cor,
                )
        centro = eixo.left() + eixo.width() // 2
        painter.fillRect(QRect(centro, eixo.top(), 1, eixo.height()), tokens.BORDER_STRONG)
        if leitura is None:
            return
        sentido = 1 if leitura.lado_dominancia >= 0 else -1
        x = self._x_de(eixo, leitura.dominancia, sentido)
        # O cursor e `--text-primary` e nao a cor do lado: a direcao ja esta
        # na POSICAO (esquerda/direita do centro) e no sinal do numero; usar
        # a cor aqui seria o quarto portador da mesma coisa, pago com a
        # visibilidade do cursor contra a propria faixa colorida.
        painter.fillRect(QRect(x - 1, eixo.top(), 3, eixo.height()), tokens.TEXT_PRIMARY)

    def _desenhar_regua_dominancia(
        self, painter: QPainter, eixo: QRect, regua: QRect
    ) -> None:
        # As duas pontas primeiro, e o espaco delas fica RESERVADO: os
        # rotulos numericos que colidirem com "« VENDA"/"COMPRA »" nao sao
        # desenhados por cima, eles simplesmente nao entram (F8 — coluna que
        # nao cabe sai; ela nunca trunca nem se sobrepoe).
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            regua, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "« VENDA"
        )
        painter.drawText(
            regua, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, "COMPRA »"
        )
        largura_venda = self._fm_rotulo.horizontalAdvance("« VENDA") + 6
        largura_compra = self._fm_rotulo.horizontalAdvance("COMPRA »") + 6
        ocupado: list[tuple[int, int]] = [
            (regua.left(), regua.left() + largura_venda),
            (regua.right() - largura_compra, regua.right()),
        ]

        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_MUTED)
        for sentido in (-1, 1):
            for corte in self._cortes_dominancia():
                if corte >= 1.0:
                    continue  # a ponta ja diz COMPRA/VENDA; o `100` seria ruido
                if corte == 0.5 and sentido < 0:
                    continue  # o centro e um so
                x = self._x_de(eixo, corte, sentido)
                texto = str(int(round(corte * 100)))
                meia = self._fm_grade.horizontalAdvance(texto) // 2 + 3
                if any(x - meia <= fim and x + meia >= ini for ini, fim in ocupado):
                    continue
                ocupado.append((x - meia, x + meia))
                painter.drawText(
                    QRect(x - 16, regua.top(), 32, regua.height()),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    texto,
                )

    # -------------------------------------------------------------- magnitude
    def _desenhar_magnitude(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        painter.fillRect(banda, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(MARGEM, banda.top(), banda.width() - MARGEM, banda.top())
        leitura = self._leitura
        largura = banda.width() - 2 * MARGEM
        rotulo = QRect(MARGEM, banda.top() + 1, largura, 18)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            rotulo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "MAGNITUDE REL."
        )
        if leitura is None:
            self._chip_regras(
                painter, MARGEM + 96, rotulo, BANDA_MAGNITUDE
            )
            return

        bloqueado = leitura.bloqueio == "magnitude_relativa"
        # Sem referencia o motor ASSUME 1,0 e deixa passar. Publicar `1,00` e
        # `PASSA` em verde, com a ressalva numa legenda de 10px logo abaixo,
        # e exatamente o que a transmissao degradada entregou como veredito
        # limpo. Entao o valor NAO e publicado nessa forma: onde iria o
        # numero vai `SEM REFERÊNCIA`, no mesmo corpo, e a ressalva entra
        # DENTRO da palavra do veredito — `PASSA SEM MEDIR` nao pode ser lido
        # pela metade.
        assumido = leitura.magnitude_referencia is None
        if assumido:
            texto = "SEM REFERÊNCIA"
            veredito, cor_veredito = "PASSA SEM MEDIR", tokens.ABSORPTION
        else:
            # Veredito COM o numero e COM o limiar: `0,84 · gate 0,60 · PASSA`.
            # "PASSA" sozinho seria um oraculo, e oraculo em pregao e caro.
            texto = (
                formato.formatar_sinalizado(leitura.magnitude_relativa, casas=2).lstrip(
                    formato.MAIS
                )
                + "  gate "
                + f"{self.config.magnitude_relativa_minima:.2f}".replace(".", ",")
            )
            if bloqueado:
                veredito, cor_veredito = "BLOQUEIA", tokens.ALERT
            else:
                veredito, cor_veredito = "PASSA", tokens.OK

        fonte_valor = tokens.fonte_numero(12, 500)
        painter.setFont(fonte_valor)
        painter.setPen(tokens.TEXT_SECONDARY if assumido else tokens.TEXT_PRIMARY)
        largura_texto = QFontMetrics(fonte_valor).horizontalAdvance(texto)
        painter.drawText(
            QRect(rotulo.right() - largura_texto, rotulo.top(), largura_texto, rotulo.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )
        # Ordem de prioridade quando o espaco aperta: o VALOR primeiro, o
        # VEREDITO depois, e so entao a procedencia da banda. Deixar o chip de
        # procedencia empurrar `PASSA SEM MEDIR` para fora seria trocar uma
        # ressalva por outra — e a ressalva que nao pode faltar e a que esta
        # colada no numero desta linha.
        x = MARGEM + 96
        largura_chip = self._fm_rotulo.horizontalAdvance(veredito) + 12
        limite = rotulo.right() - largura_texto - 8
        if limite - x >= largura_chip:
            self._chip(
                painter,
                QRect(x, rotulo.top() + 2, largura_chip, rotulo.height() - 4),
                veredito,
                cor_veredito,
            )
            x += largura_chip + 8
        self._chip_regras(
            painter,
            x,
            QRect(rotulo.left(), rotulo.top(), limite - rotulo.left(), rotulo.height()),
            BANDA_MAGNITUDE,
        )

        barra = QRect(MARGEM, rotulo.bottom() + 1, largura, 10)
        painter.fillRect(barra, tokens.BG_RAISED)
        if not assumido:
            fracao = max(0.0, min(1.0, leitura.magnitude_relativa / ESCALA_MAGNITUDE))
            preenchida = max(1, int(fracao * barra.width()))
            rampa = tokens.RAMPA_NEUTRA
            lado = leitura.lado_dominancia
            if self.paleta.tem_cor and lado:
                rampa = tokens.RAMPA_COMPRA if lado > 0 else tokens.RAMPA_VENDA
            painter.fillRect(
                QRect(barra.left(), barra.top() + 1, preenchida, barra.height() - 2),
                rampa[tokens.degrau(fracao * 1.6)],
            )
        # O gate DESENHADO no eixo: o operador ve a distancia ate o proximo
        # estado sem fazer conta. Fica mesmo quando nao ha o que medir — e a
        # calha vazia ao lado dele que diz que nada foi medido.
        x_gate = barra.left() + int(
            min(1.0, self.config.magnitude_relativa_minima / ESCALA_MAGNITUDE) * barra.width()
        )
        painter.fillRect(QRect(x_gate, barra.top() - 1, 1, barra.height() + 2), tokens.ALERT)
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_MUTED)
        referencia = leitura.magnitude_referencia
        fonte = ROTULO_FONTE_MAGNITUDE.get(leitura.magnitude_fonte, leitura.magnitude_fonte)
        if referencia is None:
            detalhe = formato.formatar_inteiro(leitura.magnitude) + "  " + fonte
        else:
            detalhe = (
                formato.formatar_inteiro(leitura.magnitude)
                + " / "
                + formato.formatar_inteiro(int(referencia))
                + "  "
                + fonte
            )
        painter.drawText(
            QRect(MARGEM, barra.top(), largura, barra.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            detalhe,
        )

    # --------------------------------------------------------------- medidas
    def _desenhar_medidas(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        painter.fillRect(banda, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(MARGEM, banda.top(), banda.width() - MARGEM, banda.top())
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        cabecalho = QRect(MARGEM, banda.top() + 1, banda.width() - 2 * MARGEM, ALTURA_ROTULO)
        painter.drawText(
            cabecalho,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "MEDIDAS",
        )
        self._chip_regras(painter, MARGEM + 66, cabecalho, BANDA_MEDIDAS)
        leitura = self._leitura
        if leitura is None:
            return
        altura = self.densidade.altura_linha
        y = banda.top() + ALTURA_ROTULO
        escala = self._escala_medidas
        self._linha_medida(
            painter, QRect(0, y, banda.width(), altura), "Δ SESSÃO",
            leitura.delta_sessao, escala,
            formato.formatar_inteiro(leitura.volume_total) + " vol",
        )
        y += altura
        micro = leitura.delta_micro
        # As DUAS metades da janela micro, lado a lado: e a comparacao que o
        # motor faz para decidir "virou" (`_micro_virou`), e ver so o total
        # esconde exatamente a informacao que produz o estagio.
        self._linha_medida(
            painter, QRect(0, y, banda.width(), altura), "Δ MICRO",
            micro, escala,
            "1ª " + formato.formatar_sinalizado(leitura.delta_micro_antigo)
            + "  2ª " + formato.formatar_sinalizado(leitura.delta_micro_recente),
        )
        y += altura
        self._linha_medida(
            painter, QRect(0, y, banda.width(), altura), "AGRESSÃO",
            leitura.agressao_saldo, escala,
            formato.formatar_percentual(leitura.agressao_taxa_compra, casas=0).lstrip(
                formato.MAIS
            )
            + " compra  ·  "
            + f"{leitura.agressao_trades_s:.0f}".replace(".", ",")
            + " neg/s",
        )
        y += altura
        self._linha_sem_lado(painter, QRect(0, y, banda.width(), altura), leitura)

    def _linha_medida(
        self,
        painter: QPainter,
        linha: QRect,
        rotulo: str,
        valor: int,
        escala: int,
        extra: str,
    ) -> None:
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, linha.top(), 76, linha.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            rotulo,
        )
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 600))
        painter.setPen(self.paleta.direcional(valor))
        painter.drawText(
            QRect(MARGEM + 76, linha.top(), 84, linha.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_sinalizado(valor),
        )
        barra = QRect(MARGEM + 168, linha.top() + 3, 104, linha.height() - 6)
        if barra.right() < linha.width() - MARGEM:
            self._barra_bipolar(painter, barra, valor, escala)
            resto = QRect(
                barra.right() + 8,
                linha.top(),
                linha.width() - barra.right() - 8 - MARGEM,
                linha.height(),
            )
            if resto.width() > 40:
                painter.setFont(tokens.fonte_numero(10))
                painter.setPen(tokens.TEXT_SECONDARY)
                painter.drawText(
                    resto,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    extra,
                )

    def _barra_bipolar(self, painter: QPainter, rect: QRect, valor: int, escala: int) -> None:
        """Cresce do CENTRO para o lado do sinal — posicao como portador."""
        centro = rect.left() + rect.width() // 2
        painter.fillRect(QRect(centro, rect.top(), 1, rect.height()), tokens.BORDER_STRONG)
        if valor == 0 or escala <= 0:
            return
        fracao = min(1.0, abs(valor) / escala)
        comprimento = max(1, int(fracao * (rect.width() // 2 - 2)))
        if self.paleta.tem_cor:
            rampa = tokens.RAMPA_COMPRA if valor > 0 else tokens.RAMPA_VENDA
        else:
            rampa = tokens.RAMPA_NEUTRA
        cor = rampa[tokens.degrau(fracao)]
        x = centro + 1 if valor > 0 else centro - comprimento
        painter.fillRect(QRect(x, rect.top(), comprimento, rect.height()), cor)

    def _linha_sem_lado(self, painter: QPainter, linha: QRect, leitura: LeituraMotor) -> None:
        """RLP — desenhada SEMPRE, inclusive em zero.

        §1 do documento cobra do Profit que a cor seja o unico portador; o
        pecado equivalente aqui seria fazer o volume sem lado aparecer so
        quando incomoda. Uma linha que some ensina o olho a nao procurar por
        ela — e ai ela some justamente no dia em que 15% do volume nao tem
        agressor divulgado e a dominancia acima esta falando de 85% do
        mercado como se fosse o mercado."""
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, linha.top(), 76, linha.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "S/ LADO",
        )
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        painter.setPen(tokens.NEUTRAL)
        painter.drawText(
            QRect(MARGEM + 76, linha.top(), 84, linha.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_inteiro(leitura.volume_sem_lado),
        )
        barra = QRect(MARGEM + 168, linha.top() + 3, 104, linha.height() - 6)
        if barra.right() >= linha.width() - MARGEM:
            return
        painter.fillRect(barra, tokens.BG_RAISED)
        fracao = (
            leitura.volume_sem_lado / leitura.volume_total if leitura.volume_total else 0.0
        )
        if fracao > 0:
            painter.fillRect(
                QRect(barra.left(), barra.top(), max(1, int(fracao * barra.width())), barra.height()),
                tokens.RAMPA_NEUTRA[tokens.degrau(min(1.0, fracao * 4))],
            )
        resto = QRect(
            barra.right() + 8,
            linha.top(),
            linha.width() - barra.right() - 8 - MARGEM,
            linha.height(),
        )
        if resto.width() > 40:
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                resto,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                formato.formatar_percentual(fracao, casas=1).lstrip(formato.MAIS)
                + " sem agressor",
            )

    # ------------------------------------------------------------- deteccoes
    def _desenhar_deteccoes(self, painter: QPainter, banda: QRect, regiao: QRect) -> None:
        cabecalho = QRect(0, banda.top(), banda.width(), ALTURA_ROTULO)
        if cabecalho.intersects(regiao):
            painter.fillRect(cabecalho, self.cor_fundo)
            painter.setPen(tokens.BORDER)
            painter.drawLine(MARGEM, banda.top(), banda.width() - MARGEM, banda.top())
            interno = cabecalho.adjusted(MARGEM, 1, -MARGEM, 0)
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                interno,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "DETECÇÕES",
            )
            # O placar de PROCEDENCIA DA REGRA, no corpo do titulo da banda e
            # na cor do segundo canal — nao numa legenda muda de 10px. Com o
            # registro de hoje ele le "0 MÉTODO · 320 GENÉRICAS", que e o
            # achado: nenhum dos seis membros de `TipoDeteccao` corresponde a
            # uma regra implementada de `metodologia/regras.py`.
            genericas = self._n_deteccoes - self._n_metodo
            painter.setPen(tokens.ABSORPTION if genericas else tokens.TEXT_SECONDARY)
            painter.drawText(
                interno,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "%s MÉTODO · %s GENÉRICAS"
                % (
                    formato.formatar_inteiro(self._n_metodo),
                    formato.formatar_inteiro(genericas),
                ),
            )

        colunas = QRect(0, banda.top() + ALTURA_ROTULO, banda.width(), ALTURA_COLUNAS)
        if colunas.intersects(regiao):
            self._desenhar_colunas(painter, colunas)

        # O corpo INTEIRO da banda e fundo do painel — inclusive a sobra
        # abaixo do ultimo slot, quando a janela e mais alta que o teto de
        # slots. Sem isso ali aparece o backing anterior.
        topo_corpo = banda.top() + ALTURA_ROTULO + ALTURA_COLUNAS
        corpo = QRect(
            0, topo_corpo, banda.width(), banda.bottom() - topo_corpo + 1
        ).intersected(regiao)
        if corpo.isValid():
            painter.fillRect(corpo, self.cor_fundo)
        if self._n_slots <= 0:
            return
        area = self._area_slots
        alvo = area.intersected(regiao)
        if not alvo.isValid():
            return
        if self._n_deteccoes == 0:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "SEM DETECÇÕES AINDA")
            return
        # SO os slots que cruzam a regiao. Uma deteccao nova desenha UMA
        # linha; e o mesmo calculo que o DOM faz com as suas linhas de preco.
        altura = self.densidade.altura_linha
        primeiro = max(0, (alvo.top() - area.top()) // altura)
        ultimo = min(self._n_slots - 1, (alvo.bottom() - area.top()) // altura)
        for slot in range(primeiro, ultimo + 1):
            item = self._deteccoes[slot]
            if item is None:
                continue
            self._desenhar_deteccao(
                painter,
                QRect(0, area.top() + slot * altura, banda.width(), altura),
                item,
            )

    def _desenhar_colunas(self, painter: QPainter, faixa: QRect) -> None:
        """Cabecalho de coluna — a banda nao tinha nenhum.

        `1,00`, `MBO`, o preco e a hora saiam sem nome e sem unidade: o
        leitor tinha de inferir o significado de cada coluna pelo formato do
        valor. §1 cobra da referencia rotulo truncado (F8); rotulo AUSENTE e
        a mesma falha sem o alibi do espaco.

        O `▼` na hora nao e enfeite: a banda tambem nao dizia por que ordem
        estava ordenada, e "mais recente no topo" e uma convencao, nao um
        fato evidente — o tape do mesmo produto usa a mesma, o livro nao.
        """
        painter.fillRect(faixa, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_MUTED)
        largura_hora = self._fm_rotulo.horizontalAdvance("HORA ▼") + 8
        fim = faixa.width() - MARGEM - largura_hora
        painter.drawText(
            faixa.adjusted(0, 0, -MARGEM, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "HORA ▼",
        )
        for i, (x, rotulo) in enumerate(ROTULOS_COLUNA):
            # O limite de cada rotulo e o inicio do PROXIMO — nunca uma
            # largura fixa. Caixa fixa com rotulo maior que ela seria
            # truncamento silencioso, que e a fraqueza F8 da referencia
            # (`Qtd Co…`, `Classifi…`) cometida por dentro.
            seguinte = ROTULOS_COLUNA[i + 1][0] if i + 1 < len(ROTULOS_COLUNA) else fim
            espaco = min(seguinte, fim) - x - 4
            if espaco < self._fm_rotulo.horizontalAdvance(rotulo):
                continue  # F8: coluna que nao cabe sai; nunca trunca
            painter.drawText(
                QRect(x, faixa.top(), espaco, faixa.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                rotulo,
            )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, faixa.bottom(), faixa.width(), faixa.bottom())

    def _desenhar_deteccao(self, painter: QPainter, linha: QRect, item: ItemDeteccao) -> None:
        """Uma linha com as duas procedencias, o tipo subordinado a elas, e a
        RARIDADE — que e o eixo de excecao que faltava.

        A banda tinha 24 linhas com a mesma caneta, o mesmo chip e a mesma
        barra de 32px, e a unica linha anomala do retrato (`CLIP INSTIT.` no
        meio de 23 `EXAUSTÃO`) saia tipograficamente identica as outras.
        Numa coluna densa, a pergunta que se faz varrendo e "qual e a linha
        diferente?", e a peca nao respondia.

        Agora responde por tres portadores independentes, na melhor tradicao
        de §3.2: a **posicao** (uma regua de 3px na borda esquerda, area
        chapada que atravessa o canal), o **numero** (a fatia do tipo na
        sessao) e a **cor** (ambar na fatia rara). Tire qualquer um e a
        excecao continua achavel.
        """
        largura = linha.width()
        altura_chip = max(10, linha.height() - 6)
        topo_chip = linha.top() + (linha.height() - altura_chip) // 2
        raro = 0.0 <= item.fracao_tipo < FRACAO_RARA

        if raro:
            # Regua de excecao. Nao e "destaque": e o unico elemento da linha
            # cuja PRESENCA (e nao o valor) carrega informacao, e por isso
            # sobrevive a uma varredura periferica que nao le nada.
            painter.fillRect(
                QRect(0, linha.top(), 3, linha.height()), tokens.ABSORPTION
            )

        self._chip(
            painter,
            QRect(COL_REGRA, topo_chip, 58, altura_chip),
            "MÉTODO" if item.do_metodo else "GENÉRICO",
            tokens.OK if item.do_metodo else tokens.NEUTRAL,
        )

        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_PRIMARY if item.do_metodo else tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(COL_TIPO, linha.top(), COL_PRECO - COL_TIPO - 2, linha.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            item.rotulo,
        )

        if item.price is not None:
            estavel, vivo = formato.formatar_preco(self.grid, item.price)
            painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
            caixa = QRect(COL_PRECO, linha.top(), COL_LADO - COL_PRECO - 4, linha.height())
            largura_vivo = self._fm_grade.horizontalAdvance(vivo)
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                QRect(caixa.right() - largura_vivo, caixa.top(), largura_vivo, caixa.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                vivo,
            )
            # Digitos estaveis apagados (§3.2, F6): a parte repetida em todas
            # as linhas nao pode competir com a que muda.
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(caixa.left(), caixa.top(), caixa.width() - largura_vivo, caixa.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                estavel,
            )

        seta = SETA_COMPRA if item.lado > 0 else (SETA_VENDA if item.lado < 0 else SEM_LADO)
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        painter.setPen(self.paleta.direcional(item.lado))
        painter.drawText(
            QRect(COL_LADO, linha.top(), 14, linha.height()),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            seta,
        )

        # Procedencia do DADO. Salienca invertida: MBO observado e a norma e
        # sai em cinza discreto; livro inferido e a excecao e vira chip ambar.
        barra = QRect(COL_CONF_BARRA, topo_chip + 2, 32, max(6, altura_chip - 4))
        if barra.right() < largura - MARGEM:
            painter.fillRect(barra, tokens.BG_RAISED)
            cheio = max(1, int(max(0.0, min(1.0, item.confianca)) * barra.width()))
            painter.fillRect(
                QRect(barra.left(), barra.top(), cheio, barra.height()),
                tokens.ALERT if item.inferida else tokens.NEUTRAL,
            )
        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(COL_CONF_NUM, linha.top(), 32, linha.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{item.confianca:.2f}".replace(".", ","),
        )

        if item.inferida:
            chip_dado = QRect(COL_DADO, topo_chip, 76, altura_chip)
            if chip_dado.right() < largura - MARGEM:
                self._chip(painter, chip_dado, "MBP INFERIDO", tokens.ALERT)
        else:
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(COL_DADO, linha.top(), 76, linha.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "MBO",
            )

        self._desenhar_raridade(painter, linha, item, raro)

        if item.timestamp_ns:
            hora = formato.formatar_hora_ns(item.timestamp_ns)
            largura_hora = self._fm_grade.horizontalAdvance(hora)
            # F8: se a hora nao cabe INTEIRA, ela nao entra. Coluna truncada
            # e pior que coluna ausente — `22:rrelevant` nao informa nada.
            if COL_RARIDADE + LARGURA_RARIDADE + largura_hora + MARGEM <= largura:
                painter.setFont(tokens.fonte_numero(10))
                painter.setPen(tokens.TEXT_MUTED)
                painter.drawText(
                    QRect(largura - MARGEM - largura_hora, linha.top(), largura_hora, linha.height()),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    hora,
                )

    def _desenhar_raridade(
        self, painter: QPainter, linha: QRect, item: ItemDeteccao, raro: bool
    ) -> None:
        """A fatia da sessao que o tipo desta linha representava ao chegar.

        **So a linha RARA ganha tinta.** A primeira versao pintava a barra
        proporcional a fatia, e o resultado era o oposto do que a coluna
        existe para fazer: a linha com MAIS tinta era a do tipo mais comum, e
        a excecao ficava com o tracinho mais curto da coluna. Aqui a magnitude
        vive no numero e a tinta significa uma coisa so — "esta e a diferente"
        —, que e a mesma salienca invertida do par MBO x MBP inferido.
        """
        if COL_RARIDADE + LARGURA_RARIDADE > linha.width() - MARGEM:
            return
        altura = max(6, linha.height() - 10)
        trilho = QRect(COL_RARIDADE, linha.top() + (linha.height() - altura) // 2, 28, altura)
        painter.fillRect(trilho, tokens.BG_RAISED)
        if raro:
            painter.fillRect(trilho, tokens.ABSORPTION)
        painter.setFont(tokens.fonte_numero(10))
        if item.fracao_tipo < 0.0:
            # Aquecimento: a fatia existe, mas nao sustenta veredito nenhum.
            painter.setPen(tokens.TEXT_MUTED)
            texto = "—"
        else:
            painter.setPen(tokens.ABSORPTION if raro else tokens.TEXT_SECONDARY)
            texto = formato.formatar_percentual(item.fracao_tipo, casas=0).lstrip(
                formato.MAIS
            )
        painter.drawText(
            QRect(trilho.right() + 4, linha.top(), 30, linha.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )


_DESENHOS = (
    PainelMatriz._desenhar_cabecalho,
    PainelMatriz._desenhar_estagio,
    PainelMatriz._desenhar_dominancia,
    PainelMatriz._desenhar_regua,
    PainelMatriz._desenhar_magnitude,
    PainelMatriz._desenhar_medidas,
    PainelMatriz._desenhar_deteccoes,
)
"""Despacho por INDICE de banda, resolvido no import.

Um `if/elif` de seis ramos por banda por quadro custaria pouco, mas a tupla
custa zero e torna impossivel uma banda existir na geometria sem existir no
desenho — os indices sao os mesmos."""


def _percentual_inteiro(fracao: float) -> str:
    """`0.7` -> `70%`. So para limiar de faixa, que e sempre redondo."""
    return f"{round(fracao * 100)}%"


def _duracao(ns: int) -> str:
    """`300000000000` -> `5min`. So para o rotulo de janela do cabecalho."""
    segundos = ns / 1_000_000_000
    if segundos >= 60:
        return f"{segundos / 60:g}min".replace(".", ",")
    return f"{segundos:g}s".replace(".", ",")


def _degrau_1_2_5(valor: int) -> int:
    """Menor 1/2/5 x 10^k que cobre `valor` — mesma serie do DOM.

    Duplicada de `paineis/dom.py` de proposito nao seria bom; mas extrair
    para um modulo comum por UMA funcao de quatro linhas criaria um modulo
    `utilidades` que atrai tudo. Se aparecer um terceiro uso, sobe."""
    if valor <= 1:
        return 1
    escala = 1
    while escala < valor:
        for m in (2, 5, 10):
            if m * escala >= valor:
                return m * escala
        escala *= 10
    return escala
