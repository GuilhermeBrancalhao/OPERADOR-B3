"""O MÉTODO na tela — as cinco leituras vivas que o registro avaliza.

## O diagnóstico que este painel existe para desfazer

> *"a peça deu 60% da sua superfície ao único fluxo que o registro não
> avaliza, e 0% às 33 regras que ele avaliza."*

Era literalmente verdade e não havia como não ser: `fluxopro/metodologia/`
estava desligada do pipeline, então a única coisa que a coluna da DECISÃO
podia mostrar do registro era **a lista do registro** — famílias, cobertura,
limiares em vigor. Listagem é catálogo, não leitura. Um operador não decide
com o índice do manual aberto.

Agora existe `sessao.leitura_do_metodo()`, e este painel é a superfície dela.

## O que ele mostra, e por que cada forma é a que é

Cinco blocos, um por componente, na ordem em que o `LeitorMetodo` os alimenta
— porque essa ordem **é** a explicação: o velocímetro mede o contador que o
macro produz, e o placar é meta-leitura dos quatro acima. Ler de cima para
baixo é ler a cadeia interna do método.

1. **REGIME ESTRUTURAL** — palavra (`COMPRADOR`/`VENDEDOR`/`INDEFINIDO`),
   gatilho e as duas distâncias em *ticks*, com sinal explícito. Números, não
   geometria: a distância à máxima varia de 1 a centenas de ticks ao longo do
   dia, e desenhá-la como comprimento é a lei nº 3 deste projeto sendo
   quebrada pela quarta vez.

2. **VELOCÍMETRO** — estado, sentido, variação assinada, e a **persistência**
   como duração e amostras. A persistência é o que o construtor do
   velocímetro chamou de informação de estado que nenhum medidor de ponteiro
   carrega: *há quanto tempo* o sentido não muda. Um ponteiro mostraria o
   agora e apagaria isso.

3. **LINHA AZUL** — o nível (preço completo), o lado, a distância em ticks, e
   a **barra particionada cheia** de agressão acumulada (compra | venda | sem
   lado). Essa barra é proporção de um todo conhecido, que é exatamente a
   segunda forma do vocabulário de `hud.py` — nem saldo assinado, nem
   magnitude do canto. O `s/ lado` entra como terceiro segmento e não some:
   uma barra que só mostrasse compra e venda afirmaria 100% de atribuição num
   mercado onde a B3 não divulga o agressor de parte do volume (RLP).

4. **MACRO × MICRO** — dois números assinados e o veredito em palavra
   (`ALINHADOS`, `CONTRA-TENDÊNCIA`, quem comanda). **Sem geometria nenhuma**,
   e isto não é economia: `MedidaContexto` levanta `EscalasIncomparaveisError`
   quando alguém tenta comparar macro com micro, porque a janela do macro é a
   sessão e a do micro são 15 s. Duas barras lado a lado seriam essa
   comparação proibida desenhada — o leitor compararia comprimentos que o
   próprio domínio recusa comparar.

5. **PLACAR DE CONFLUÊNCIA** — `3×1` escrito, **barra particionada** sobre o
   total de fontes (proporção de um todo conhecido: `len(fontes_placar)`), e
   os qualificadores como *chips*: `GOLEADA`, `ESTÁVEL há 42 s`, `OSCILANDO`,
   `AQUECIMENTO`, `REVERSÃO`. Chip e não texto fino porque o placar é o
   veredito mais copiável da tela e as ressalvas dele são o que o canal come
   primeiro (`scripts/retencao.py`): bloco preenchido com texto escuro é a
   forma que a recompressão poupa.

## O RISCO não está aqui, e a ausência é o conteúdo

`risco.gatilho_de_tamanho` é **AUSENTE NA FONTE** e `GestorRisco.avaliar`
exige uma `QualidadeRegiao` informada por uma pessoa. Este painel **não**
chama `avaliar`, não infere qualidade de região de volatilidade nem de
spread, e não tem campo de risco — `LeituraMetodo` também não tem. O rodapé
diz isso com todas as letras, no lugar onde um painel menos honesto teria
posto um semáforo de risco calculado.

Dar superfície a uma decisão de risco derivada seria pôr na boca da fonte uma
regra que ela não tem — que é o defeito oposto, e pior, do que o crítico
apontou.

## Procedência: o registro qualifica cada bloco, no mesmo portador

Cada bloco carrega um chip `§N` com quantas regras respondem por ele, quantas
delas têm aval e quantas não têm, pintado pela **pior** — `§6 · 5 AVAL · 1 S/
AVAL`. É a regra do canal aplicada: o veredito (`COMPRADOR`) e a ressalva
viajam na mesma linha, no mesmo corpo, e nenhum dos dois pega carona no outro.

O cabeçalho publica a cobertura, com o **mesmo denominador** que `PainelRegras`
usa dois painéis abaixo (`33/42 regras`): `24 DE 33 REGRAS EM LEITURA VIVA`.
Dois painéis vizinhos com duas cardinalidades do mesmo conjunto obrigariam o
leitor a descobrir sozinho qual delas responde à pergunta que ele fez.

## Um relógio de dados

Este painel **não** assina barramento nem chama `ponte.ler()`. Ele recebe um
`LeituraMetodo | None` de `aplicar`, montado pela janela uma vez por quadro a
partir de `sessao.leitura_do_metodo()` — que não drena e é imutável, com os
cinco `timestamp_ns` iguais por construção.

## Estado — o critério do gravador

Nada aqui é indexado por evento: **um** `LeituraMetodo` (o corrente), uma
chave de repintura, e listas de geometria que têm o tamanho do número de
blocos, que é uma constante de módulo.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import PriceGrid, Side
from fluxopro.metodologia.confianca import Confianca, RegraDocumentada
from fluxopro.metodologia.estrutura import GatilhoEstrutural, RegimeEstrutural
from fluxopro.metodologia.leitura import REGRAS_DO_METODO_VIVO, LeituraMetodo
from fluxopro.metodologia.linha_azul import LadoDaLinha
from fluxopro.metodologia.regras import REGRAS
from fluxopro.metodologia.velocimetro import EstadoVelocimetro
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

MARCA_REGRA = "§"

# --------------------------------------------------------------------------
# Cobertura — lida do registro, nunca digitada
# --------------------------------------------------------------------------
AVALIZADAS_NO_REGISTRO: tuple[RegraDocumentada, ...] = tuple(
    r
    for r in (REGRAS.values() if isinstance(REGRAS, dict) else REGRAS)
    if r.implementada
)
"""As regras avalizadas — as que o registro dá por implementadas.

O denominador é o MESMO de `PainelRegras`, que grafa `33/42 regras` a três
centímetros daqui: `implementada`. Escolher `confianca != AUSENTE_NA_FONTE`
(que dá 28) faria dois painéis vizinhos publicarem duas cardinalidades do
mesmo conjunto, e o leitor teria de descobrir sozinho qual das duas responde
à pergunta que ele fez. O número sai do registro e não de um literal: foi
assim que uma coluna passou uma onda inteira publicando contagem vencida."""

AVALIZADAS_VIVAS: tuple[RegraDocumentada, ...] = tuple(
    r for r in REGRAS_DO_METODO_VIVO if r.implementada
)
"""As avalizadas que ESTA tela mostra em leitura viva, e não em listagem."""


def cobertura() -> tuple[int, int]:
    """`(vivas, avalizadas)`. A conta que o cabeçalho publica."""
    return len(AVALIZADAS_VIVAS), len(AVALIZADAS_NO_REGISTRO)


# --------------------------------------------------------------------------
# Procedência
# --------------------------------------------------------------------------
_GRAVIDADE: dict[Confianca | None, int] = {
    Confianca.CONFIRMADO: 0,
    Confianca.INFERIDO: 1,
    Confianca.IMPRECISO: 2,
    Confianca.AUSENTE_NA_FONTE: 3,
    None: -1,
}

ROTULO_CONFIANCA: dict[Confianca | None, str] = {
    Confianca.CONFIRMADO: "CONFIRMADO",
    Confianca.INFERIDO: "INFERIDO",
    Confianca.IMPRECISO: "IMPRECISO",
    Confianca.AUSENTE_NA_FONTE: "SEM AVAL",
    None: "SEM REGISTRO",
}

_COR_CONFIANCA: dict[Confianca | None, QColor] = {
    Confianca.CONFIRMADO: tokens.OK,
    Confianca.INFERIDO: tokens.NEUTRAL,
    Confianca.IMPRECISO: tokens.ALERT,
    Confianca.AUSENTE_NA_FONTE: tokens.ABSORPTION,
    None: tokens.ABSORPTION,
}
"""A tabela de `ui/janela.py::_cor_da_confianca`, e não uma variação.

Este painel usou `DANGER` numa primeira versão e **o canal a reprovou**: o
chip `§3 · 1 SEM AVAL` reteve 33,2% contra 58,6% do `COMPRADOR` que ele
qualifica. A causa não era o corpo do texto — aumentá-lo de 11 para 16px
piorou o número três vezes seguidas —, era o TOKEN: `DANGER` tem 5,45:1, a
menor luminância de todos, e texto escuro sobre ele carrega o traço quase só
em CROMA. O JPEG subamostra croma 2×. `ALERT` (12,34:1) e `ABSORPTION`
(10,72:1) carregam o mesmo traço em LUMINÂNCIA, e atravessam — o chip
`§5 IMPRECISO`, em `ALERT`, reteve 89% na mesma imagem.

Ou seja: a lei "ressalva em corpo não menor que o dado" tem uma segunda
metade que só a medição mostrou — **ressalva em token de luminância alta**.
`DANGER` continua certo para a faixa de 3px da janela inteira (§3.5), que é
área chapada e não carrega texto."""


def pior_confianca(regras: tuple[RegraDocumentada, ...]) -> Confianca | None:
    """A PIOR das regras do bloco. Um bloco não pega aval emprestado.

    Se sete regras confirmam e uma é imprecisa, o bloco é impreciso: o leitor
    que visse `CONFIRMADO` acreditaria no elo mais fraco pelo crédito do mais
    forte.
    """
    pior: Confianca | None = None
    for regra in regras:
        if _GRAVIDADE[regra.confianca] > _GRAVIDADE[pior]:
            pior = regra.confianca
    return pior


def texto_procedencia(regras: tuple[RegraDocumentada, ...]) -> tuple[str, QColor]:
    """O chip de procedência de um bloco: quantas, e de que qualidade.

    A primeira versão grafava só o pior rótulo, e quatro dos cinco blocos
    liam `SEM AVAL` — verdadeiro pela regra do elo mais fraco, e péssimo como
    informação: apagava da tela justamente as regras avalizadas que este
    painel existe para mostrar, que era o defeito diagnosticado, invertido.

    A saída **não** foi abrandar o rótulo. Foi publicar a composição: `§6 · 1
    SEM AVAL` — quantas regras respondem pelo bloco, quantas delas descontam,
    e a cor do PIOR. O crédito (`6`) e o desconto (`1`) no mesmo chip, e
    nenhum dos dois pega carona no outro; a contagem das avalizadas VIVAS vive
    no cabeçalho, com denominador.

    A primeira redação era `§6 · 5 AVAL · 1 S/ AVAL`, e **o canal a reprovou**:
    22 glifos finos num chip de 155px retiveram 38,8% contra 52,6% do veredito
    que eles qualificam. Retenção é razão, e razão pune detalhe fino — encher a
    ressalva de algarismos e separadores é o jeito mais rápido de fazê-la morrer
    na transmissão. O que sobrou é o mínimo que ainda responde "quantas, e
    quantas descontam".
    """
    if not regras:
        return ("SEM REGISTRO", _COR_CONFIANCA[None])
    pior = pior_confianca(regras)
    sem_aval = sum(1 for r in regras if r.confianca is Confianca.AUSENTE_NA_FONTE)
    if not sem_aval:
        texto = "%s%d %s" % (MARCA_REGRA, len(regras), ROTULO_CONFIANCA[pior])
    else:
        texto = "%s%d · %d %s" % (
            MARCA_REGRA, len(regras), sem_aval, ROTULO_CONFIANCA[pior]
        )
    return texto, _COR_CONFIANCA[pior]


# --------------------------------------------------------------------------
# Geometria — UMA conta, usada pelo desenho E pelo teste (lei nº 6)
# --------------------------------------------------------------------------
BLOCOS: tuple[str, ...] = (
    "REGIME ESTRUTURAL",
    "VELOCÍMETRO",
    "LINHA AZUL",
    "MACRO × MICRO",
    "PLACAR DE CONFLUÊNCIA",
)
N_BLOCOS = len(BLOCOS)

I_REGIME, I_VELOCIMETRO, I_LINHA, I_MACRO, I_PLACAR = range(N_BLOCOS)

ALTURA_TITULO = 18
ALTURA_VALOR = 22
ALTURA_FAIXA = 20
ALTURA_BLOCO = ALTURA_TITULO + ALTURA_VALOR + ALTURA_FAIXA + 4
"""Múltiplo de 4 (§3.4): 64. Uniforme entre os cinco de propósito — bloco de
altura variável faria a coluna respirar a cada mudança de estado, e movimento
periférico numa tela de pregão é custo de atenção sem informação.

**Eram 56, e o canal cobriu os outros 8.** Ver `CORPO_CHIP`."""

ALTURA_RODAPE = 34
MARGEM = 8
VAO_CHIP = 4
CORPO_CHIP = 13
"""Corpo do chip de ressalva — o MESMO do veredito que ele qualifica.

Eram 11px contra os 13px do veredito, e `scripts/retencao.py` reprovou a
peça com a lei do canal em número:

| caixa                              | retenção |
|---|---|
| `proc_placar` (`§5 IMPRECISO`)      | **33,5%** |
| `veredito_placar` (`4 a 0 · NÃO OPERÁVEL`) | 64,6% |

31,1 pontos de margem: a transmissão entregava a conclusão e comia a
ressalva. A composição já tinha essa regra escrita — *"nenhuma ressalva viaja
em corpo menor que o dado que ela qualifica"* — e este painel a violava em
dois pixels de corpo. Quem cedeu foi a altura do bloco, não o corpo da
ressalva."""
ALTURA_CHIP = 17
COSTURA = 1
"""Vão entre segmentos da barra particionada, em `BG_BASE`.

Sem cor, é a ÚNICA coisa que separa um segmento do vizinho — a mesma decisão
de `footprint.LARGURA_COSTURA`, pelo mesmo motivo."""

GLIFO_COMPRA = "▲"
GLIFO_VENDA = "▼"
GLIFO_NEUTRO = "="
SEM_LEITURA = "SEM LEITURA DO MÉTODO"
TITULOS: tuple[str, ...] = ("MÉTODO · LEITURA VIVA", "MÉTODO · VIVO", "MÉTODO")
"""Do mais longo ao mais curto — F8: encolhe o vocabulário, nunca o texto."""


def altura_natural(densidade: tokens.Densidade = tokens.PADRAO) -> int:
    return densidade.altura_cabecalho + N_BLOCOS * ALTURA_BLOCO + ALTURA_RODAPE


def _fm(fonte) -> QFontMetrics:
    return QFontMetrics(fonte)


def maior_que_cabe(alternativas: tuple[str, ...], largura: int, fm: QFontMetrics) -> str:
    """A primeira alternativa que cabe INTEIRA. Nunca trunca (F8).

    O primeiro retrato saiu com o rodapé do risco cortado em *"...e o gestor
    exige"* — e a frase que sobrou continuava parecendo completa, que é
    exatamente o modo de falha que este projeto persegue. A tela encolhe o
    VOCABULÁRIO, nunca o texto.
    """
    for texto in alternativas:
        if fm.horizontalAdvance(texto) <= largura:
            return texto
    return alternativas[-1]


@dataclass(frozen=True, slots=True)
class Segmento:
    """Uma fatia da barra particionada: rótulo, valor e a cor que a pinta."""

    rotulo: str
    valor: int
    cor: QColor


def particionar(
    largura: int, valores: tuple[int, ...], costura: int = COSTURA
) -> tuple[int, ...]:
    """Reparte `largura` em fatias proporcionais, SEM perder pixel nem fatia.

    Duas propriedades, e as duas foram pagas antes neste projeto:

    * **a soma das fatias mais as costuras é exatamente `largura`** — o resto
      da divisão vai para a maior fatia, e não some. Uma barra "cheia" que
      terminasse dois pixels antes da borda afirmaria um resto que não existe;
    * **fatia de valor não-nulo nunca arredonda para zero** — recebe 1px. É o
      defeito nº 3 do ranking de players (`hud.py`): a parcela pequena
      desaparecer é perda, e perda silenciosa.

    Valor zero recebe zero: aí a ausência é o dado.
    """
    n = len(valores)
    total = sum(valores)
    vao = costura * max(0, n - 1)
    util = largura - vao
    if util <= 0 or total <= 0:
        return tuple(0 for _ in valores)
    fatias = [(v * util) // total for v in valores]
    for i, v in enumerate(valores):
        if v > 0 and fatias[i] == 0:
            fatias[i] = 1
    sobra = util - sum(fatias)
    if sobra:
        maior = max(range(n), key=lambda i: fatias[i])
        fatias[maior] = max(0, fatias[maior] + sobra)
    return tuple(fatias)


# --------------------------------------------------------------------------
# Redação de cada bloco — puro, sem Qt, compartilhado com o teste
# --------------------------------------------------------------------------
_ROTULO_REGIME = {
    RegimeEstrutural.COMPRADOR: "COMPRADOR",
    RegimeEstrutural.VENDEDOR: "VENDEDOR",
    RegimeEstrutural.INDEFINIDO: "INDEFINIDO",
}

_ROTULO_GATILHO = {
    GatilhoEstrutural.NENHUM: "",
    GatilhoEstrutural.ROMPEU_MAXIMA: "ROMPEU MÁXIMA",
    GatilhoEstrutural.PERDEU_MINIMA: "PERDEU MÍNIMA",
    GatilhoEstrutural.CRUZOU_ABERTURA: "CRUZOU ABERTURA",
}

_ROTULO_VELOCIMETRO = {
    EstadoVelocimetro.SEM_DADOS: "SEM DADOS",
    EstadoVelocimetro.PARADO: "PARADO",
    EstadoVelocimetro.ACELERANDO: "ACELERANDO",
    EstadoVelocimetro.MANTENDO: "MANTENDO",
    EstadoVelocimetro.DESACELERANDO: "DESACELERANDO",
    EstadoVelocimetro.VIROU: "VIROU",
}

_ROTULO_LADO_LINHA = {
    LadoDaLinha.ACIMA: "PREÇO ACIMA",
    LadoDaLinha.ABAIXO: "PREÇO ABAIXO",
    LadoDaLinha.NA_LINHA: "NA LINHA",
    LadoDaLinha.SEM_LINHA: "SEM LINHA",
}


def _ticks(valor: int | None) -> str:
    return "—" if valor is None else formato.formatar_sinalizado(valor) + " t"


def _duracao_ns(ns: int) -> str:
    return formato.formatar_duracao_s(ns / 1_000_000_000)


def _glifo(lado: Side | None) -> str:
    if lado is Side.BUY:
        return GLIFO_COMPRA
    if lado is Side.SELL:
        return GLIFO_VENDA
    return GLIFO_NEUTRO


def vereditos_do_bloco(
    indice: int, leitura: LeituraMetodo, grid: PriceGrid
) -> tuple[tuple[str, ...], Side | None]:
    """As redações do veredito, da mais longa à mais curta, e o lado.

    F8 outra vez: o primeiro retrato saiu com
    `MACRO +1.814 (sessão)  MICRO +1.814 (9,` — cortado no meio do número da
    janela, e a frase que sobrou continuava parecendo completa. A tela encolhe
    o VOCABULÁRIO (some a palavra `sessão`, some a duração da janela), nunca o
    texto. O bloco macro×micro é o pior caso porque carrega dois números
    assinados E as duas janelas que impedem a comparação indevida — e a janela
    é a última coisa a cair, porque é ela que qualifica.
    """
    longo, lado = veredito_do_bloco(indice, leitura, grid)
    if indice == I_MACRO:
        m = leitura.macro_micro
        return (
            (
                longo,
                "MACRO %s · MICRO %s (%s)"
                % (
                    formato.formatar_sinalizado(m.macro.valor),
                    formato.formatar_sinalizado(m.micro.valor),
                    _duracao_ns(m.micro.janela_ns),
                ),
                "M %s · m %s (%s)"
                % (
                    formato.abreviar(m.macro.valor),
                    formato.abreviar(m.micro.valor),
                    _duracao_ns(m.micro.janela_ns),
                ),
            ),
            lado,
        )
    if indice == I_LINHA and leitura.linha_azul.nivel is not None:
        a = leitura.linha_azul
        return (
            (
                longo,
                "%s · %s"
                % (formato.preco_completo(grid, a.nivel), _ticks(a.distancia_ticks)),
                formato.preco_completo(grid, a.nivel),
            ),
            lado,
        )
    return ((longo,), lado)


def veredito_do_bloco(
    indice: int, leitura: LeituraMetodo, grid: PriceGrid
) -> tuple[str, Side | None]:
    """A linha de VALOR de um bloco, e o lado que a colore. Puro.

    Uma função só para os cinco: desenho e teste leem a mesma frase, e uma
    mutação em qualquer ramo muda os dois juntos (lei nº 6).
    """
    if indice == I_REGIME:
        e = leitura.estrutura
        partes = [_ROTULO_REGIME[e.regime]]
        gatilho = _ROTULO_GATILHO[e.gatilho]
        if gatilho:
            partes.append(gatilho)
        return ("  ·  ".join(partes), e.lado)
    if indice == I_VELOCIMETRO:
        v = leitura.velocimetro
        return (
            "%s  ·  Δ %s  ·  %s"
            % (
                _ROTULO_VELOCIMETRO[v.estado],
                formato.formatar_sinalizado(v.variacao),
                _glifo(v.sentido),
            ),
            v.sentido,
        )
    if indice == I_LINHA:
        a = leitura.linha_azul
        if a.nivel is None:
            return (_ROTULO_LADO_LINHA[a.lado], None)
        return (
            "%s  ·  %s  ·  %s"
            % (
                formato.preco_completo(grid, a.nivel),
                _ROTULO_LADO_LINHA[a.lado],
                _ticks(a.distancia_ticks),
            ),
            a.lado.leitura_inferida,
        )
    if indice == I_MACRO:
        m = leitura.macro_micro
        # Os dois números, cada um com a JANELA dele escrita junto. Sem a
        # janela, dois inteiros lado a lado convidam exatamente à comparação
        # que `EscalasIncomparaveisError` recusa.
        return (
            "MACRO %s (sessão)   MICRO %s (%s)"
            % (
                formato.formatar_sinalizado(m.macro.valor),
                formato.formatar_sinalizado(m.micro.valor),
                _duracao_ns(m.micro.janela_ns),
            ),
            m.comanda,
        )
    p = leitura.placar
    return (
        "%s  ·  %s"
        % (p.placar, "OPERÁVEL" if p.operavel else "NÃO OPERÁVEL"),
        p.lado,
    )


def chips_do_bloco(indice: int, leitura: LeituraMetodo) -> tuple[tuple[str, QColor], ...]:
    """Os qualificadores, como chips. Puro.

    Chip e não texto fino: são as RESSALVAS, e a lei medida do canal é que
    ele preserva o veredito e apaga a ressalva.
    """
    if indice == I_REGIME:
        e = leitura.estrutura
        chips: list[tuple[str, QColor]] = []
        if e.ruido:
            chips.append(("RUÍDO", tokens.ALERT))
        if e.mudou_de_regime:
            chips.append(("MUDOU DE REGIME", tokens.ABSORPTION))
        chips.append(("MÁX %s" % _ticks(e.distancia_maxima_ticks), tokens.NEUTRAL))
        chips.append(("MÍN %s" % _ticks(e.distancia_minima_ticks), tokens.NEUTRAL))
        return tuple(chips)
    if indice == I_VELOCIMETRO:
        v = leitura.velocimetro
        chips = [
            (
                "PERSISTE %s · %s am."
                % (_duracao_ns(v.persistencia_ns), formato.formatar_inteiro(v.persistencia_amostras)),
                tokens.NEUTRAL,
            )
        ]
        if v.magnitude_relativa is None:
            # Ausência dita: sem referência de magnitude o velocímetro não
            # sabe se este movimento é grande PARA HOJE, e calar isso deixaria
            # o estado parecendo mais qualificado do que é.
            chips.append(("SEM REFERÊNCIA DE MAGNITUDE", tokens.ALERT))
        else:
            chips.append(
                (
                    "MAGNITUDE %s do pico"
                    % formato.formatar_percentual(v.magnitude_relativa, casas=0),
                    tokens.NEUTRAL,
                )
            )
        return tuple(chips)
    if indice == I_LINHA:
        a = leitura.linha_azul
        chips = [(ROTULO_CONFIANCA[a.confianca_lado], _COR_CONFIANCA[a.confianca_lado])]
        if a.cruzou_agora:
            chips.append(("CRUZOU AGORA", tokens.ABSORPTION))
        return tuple(chips)
    if indice == I_MACRO:
        m = leitura.macro_micro
        chips = []
        if m.contra_tendencia:
            chips.append(("CONTRA-TENDÊNCIA", tokens.ALERT))
        elif m.alinhados:
            chips.append(("ALINHADOS", tokens.OK))
        else:
            chips.append(("SEM COMANDO", tokens.NEUTRAL))
        if not m.comparavel_por_magnitude:
            chips.append(("ESCALAS NÃO COMPARÁVEIS", tokens.NEUTRAL))
        return tuple(chips)
    p = leitura.placar
    chips = []
    if p.em_aquecimento:
        chips.append(("AQUECIMENTO", tokens.ALERT))
    if p.goleada:
        chips.append(("GOLEADA", tokens.OK))
    if p.estavel:
        chips.append(("ESTÁVEL há %s" % _duracao_ns(p.estavel_ha_ns), tokens.OK))
    if p.oscilando:
        chips.append(("OSCILANDO %d×" % p.mudancas_na_janela, tokens.ALERT))
    if p.alerta_reversao:
        chips.append(("REVERSÃO", tokens.ABSORPTION))
    return tuple(chips)


def segmentos_do_bloco(
    indice: int, leitura: LeituraMetodo, paleta: tokens.Paleta
) -> tuple[Segmento, ...]:
    """A barra particionada de um bloco, ou `()` se ele não tem barra.

    Só os DOIS blocos cuja grandeza é proporção de um todo conhecido têm
    barra. Ver o topo do módulo.
    """
    if indice == I_LINHA:
        a = leitura.linha_azul
        return (
            Segmento("COMPRA", a.volume_comprador, paleta.compra),
            Segmento("VENDA", a.volume_vendedor, paleta.venda),
            Segmento("S/ LADO", a.volume_nao_atribuido, tokens.NEUTRAL),
        )
    if indice == I_PLACAR:
        p = leitura.placar
        return (
            Segmento("COMPRA", p.compra, paleta.compra),
            Segmento("VENDA", p.venda, paleta.venda),
            Segmento("NEUTRO", p.neutro, tokens.NEUTRAL),
        )
    return ()


def regras_do_bloco(indice: int) -> tuple[RegraDocumentada, ...]:
    """As regras do registro que respondem por um bloco.

    Lidas das tuplas dos próprios componentes, e não de um `dict` digitado
    aqui: uma segunda lista à mão é uma segunda procedência que envelhece em
    silêncio — o mesmo argumento de `leitura._uniao_das_regras`.
    """
    from fluxopro.metodologia.estrutura import _REGRAS as R_ESTRUTURA
    from fluxopro.metodologia.linha_azul import _REGRAS as R_LINHA
    from fluxopro.metodologia.macro_micro import _REGRAS as R_MACRO
    from fluxopro.metodologia.placar import _REGRAS as R_PLACAR
    from fluxopro.metodologia.velocimetro import _REGRAS as R_VELOCIMETRO

    return (R_ESTRUTURA, R_VELOCIMETRO, R_LINHA, R_MACRO, R_PLACAR)[indice]


# --------------------------------------------------------------------------
# O painel
# --------------------------------------------------------------------------
class PainelMetodo(PainelDenso):
    """Os cinco retratos vivos do método, um bloco cada."""

    def __init__(
        self,
        grid: PriceGrid,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
    ) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_SURFACE)
        self.grid = grid
        self.densidade = densidade
        self.paleta = paleta
        self._leitura: LeituraMetodo | None = None
        self._sequencia = -1
        self._fm_rotulo = _fm(tokens.fonte_rotulo())
        self._fm_chip = _fm(tokens.fonte_ui(CORPO_CHIP, 700))
        self._fm_valor = _fm(tokens.fonte_numero(13, 600))
        # A altura minima e a NATURAL, e nao um numero folgado. O primeiro
        # retrato saiu com o quinto bloco (o PLACAR, que e o veredito de
        # confluencia) e o rodape do risco CORTADOS pela altura da doca — um
        # painel que some pela metade afirma que o metodo tem quatro leituras.
        self.setMinimumSize(300, altura_natural(densidade))

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    def rect_cabecalho(self) -> QRect:
        return QRect(0, 0, self.width(), self.densidade.altura_cabecalho)

    def rect_bloco(self, indice: int) -> QRect:
        return QRect(0, self._y_corpo + indice * ALTURA_BLOCO, self.width(), ALTURA_BLOCO)

    def rect_titulo(self, indice: int) -> QRect:
        bloco = self.rect_bloco(indice)
        return QRect(bloco.left() + MARGEM, bloco.top() + 2, bloco.width() - 2 * MARGEM, ALTURA_TITULO)

    def rect_valor(self, indice: int) -> QRect:
        bloco = self.rect_bloco(indice)
        return QRect(
            bloco.left() + MARGEM,
            bloco.top() + 2 + ALTURA_TITULO,
            bloco.width() - 2 * MARGEM,
            ALTURA_VALOR,
        )

    def rect_faixa(self, indice: int) -> QRect:
        bloco = self.rect_bloco(indice)
        return QRect(
            bloco.left() + MARGEM,
            bloco.top() + 2 + ALTURA_TITULO + ALTURA_VALOR,
            bloco.width() - 2 * MARGEM,
            ALTURA_FAIXA,
        )

    def rect_rodape(self) -> QRect:
        return QRect(
            0, self._y_corpo + N_BLOCOS * ALTURA_BLOCO, self.width(), ALTURA_RODAPE
        )

    def texto_valor(self, indice: int) -> str:
        """A redação do veredito que CABE na largura atual. Uma conta, três usos."""
        if self._leitura is None:
            return ""
        alternativas, _ = vereditos_do_bloco(indice, self._leitura, self.grid)
        return maior_que_cabe(alternativas, self.rect_valor(indice).width(), self._fm_valor)

    def rect_texto_valor(self, indice: int) -> QRect:
        """A caixa APERTADA em volta do veredito desenhado — não a linha toda.

        É a caixa que `scripts/retencao.py` mede como VEREDITO, e a distinção
        não é detalhe: `rect_valor` tem a largura da coluna e a palavra
        `COMPRADOR` ocupa um terço dela. Medir a linha inteira compara um chip
        apertado contra dois terços de fundo chapado, e fundo chapado atravessa
        qualquer recompressão — o par sairia reprovado por geometria de
        medição, não por desenho. Precedente da casa:
        `delta_acumulado.rect_texto_valor`, criado pela mesma razão.
        """
        linha = self.rect_valor(indice)
        largura = self._fm_valor.horizontalAdvance(self.texto_valor(indice))
        return QRect(linha.left(), linha.top(), min(linha.width(), largura + 2), linha.height())

    def rect_chip_procedencia(self, indice: int) -> QRect:
        """A caixa do chip `§N ...` de um bloco.

        Publica de proposito: e a caixa que `scripts/retencao.py` mede como
        RESSALVA contra `rect_valor(indice)` como VEREDITO. Uma caixa medida a
        mao no PNG e uma das fontes de ruido que aquele script nomeia — aqui
        ela sai do MESMO `QRect` que o desenho usa.
        """
        titulo = self.rect_titulo(indice)
        largura = self._largura_chip(texto_procedencia(regras_do_bloco(indice))[0])
        return QRect(titulo.right() - largura, titulo.top(), largura, ALTURA_CHIP)

    def textos_chip_cobertura(self) -> tuple[str, ...]:
        """As redações da cobertura, da mais longa à mais curta.

        O DENOMINADOR nunca cai — é ele que impede a contagem de parecer
        completa. O que some é a explicação (`REGRAS EM LEITURA VIVA`), que o
        título ao lado já dá.
        """
        vivas, avalizadas = cobertura()
        return (
            "%d DE %d REGRAS EM LEITURA VIVA" % (vivas, avalizadas),
            "%d DE %d REGRAS VIVAS" % (vivas, avalizadas),
            "%d DE %d VIVAS" % (vivas, avalizadas),
            "%d/%d" % (vivas, avalizadas),
        )

    def texto_chip_cobertura(self) -> str:
        """A redação que cabe **deixando espaço para o título mais curto**.

        Sem essa reserva o chip come a largura inteira num painel estreito e o
        título vai desenhado por baixo dele: dois textos nos mesmos pixels, e o
        de baixo ilegível. Foi o que o primeiro retrato mostrou.
        """
        reserva = (
            2 * MARGEM
            + _fm(tokens.fonte_ui(12, 600)).horizontalAdvance(TITULOS[-1])
            + MARGEM
        )
        disponivel = max(0, self.width() - reserva)
        for texto in self.textos_chip_cobertura():
            if self._largura_chip(texto) <= disponivel:
                return texto
        return self.textos_chip_cobertura()[-1]

    def rect_chip_cobertura(self) -> QRect:
        cabecalho = self.rect_cabecalho()
        largura = self._largura_chip(self.texto_chip_cobertura())
        return QRect(
            cabecalho.right() - MARGEM - largura,
            cabecalho.top() + (cabecalho.height() - ALTURA_CHIP) // 2,
            largura,
            ALTURA_CHIP,
        )

    def rects_dos_segmentos(self, indice: int) -> tuple[QRect, ...]:
        """As fatias da barra particionada do bloco, em coordenadas do painel.

        Desenho e teste chamam ESTA função. Não há aritmética de largura em
        dois lugares — uma mutação aqui move o pixel e derruba o teste juntos.
        """
        leitura = self._leitura
        if leitura is None:
            return ()
        segmentos = segmentos_do_bloco(indice, leitura, self.paleta)
        if not segmentos:
            return ()
        faixa = self.rect_faixa(indice)
        larguras = particionar(faixa.width(), tuple(s.valor for s in segmentos))
        rects = []
        x = faixa.left()
        for largura in larguras:
            rects.append(QRect(x, faixa.top(), largura, faixa.height()))
            x += largura + COSTURA
        return tuple(rects)

    # ---------------------------------------------------------------- quadro
    def aplicar(self, leitura: LeituraMetodo | None) -> None:
        """Absorve o quadro. Chamado pela janela, uma vez por quadro.

        `sequencia` é o contador que `LeituraMetodo` publica exatamente para
        isto: comparar um inteiro em vez de cinco dataclasses.
        """
        if leitura is None:
            if self._leitura is not None:
                self._leitura = None
                self._sequencia = -1
                self.marcar_tudo_sujo()
            return
        if leitura.sequencia == self._sequencia:
            return
        self._leitura = leitura
        self._sequencia = leitura.sequencia
        self.marcar_tudo_sujo()

    @property
    def leitura(self) -> LeituraMetodo | None:
        return self._leitura

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self.marcar_tudo_sujo()

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        self._desenhar_cabecalho(painter)
        if self._leitura is None:
            self._desenhar_vazio(painter)
            return
        for indice in range(N_BLOCOS):
            self._desenhar_bloco(painter, indice)
        self._desenhar_rodape(painter)

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        cabecalho = self.rect_cabecalho()
        painter.fillRect(cabecalho, tokens.BG_RAISED)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, cabecalho.bottom(), self.width(), cabecalho.bottom())
        painter.setFont(tokens.fonte_ui(12, 600))
        painter.setPen(tokens.TEXT_PRIMARY)
        # O titulo para onde o chip comeca. Sem este corte o primeiro retrato
        # saiu com `MÉTODO · LEITUR` desaparecendo POR BAIXO da cobertura —
        # dois textos disputando os mesmos pixels, e o de baixo ilegivel.
        chip = self.rect_chip_cobertura()
        disponivel = QRect(
            cabecalho.left() + MARGEM,
            cabecalho.top(),
            max(0, chip.left() - MARGEM - (cabecalho.left() + MARGEM)),
            cabecalho.height(),
        )
        painter.drawText(
            disponivel,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            maior_que_cabe(
                TITULOS, disponivel.width(), _fm(tokens.fonte_ui(12, 600))
            ),
        )
        vivas, _ = cobertura()
        # A cobertura vai no MESMO portador do título, e com denominador: uma
        # contagem sem denominador é a forma mais barata de parecer completa.
        self._chip(
            painter,
            self.rect_chip_cobertura(),
            self.texto_chip_cobertura(),
            tokens.OK if vivas else tokens.ALERT,
        )

    def _desenhar_vazio(self, painter: QPainter) -> None:
        """§3.5, estado Vazio: a estrutura aparece, as células ficam vazias.

        Os cinco títulos continuam desenhados — o operador precisa reconhecer
        a coluna antes de haver dado nela.
        """
        for indice in range(N_BLOCOS):
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                self.rect_titulo(indice),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                BLOCOS[indice],
            )
            painter.setPen(tokens.BORDER)
            bloco = self.rect_bloco(indice)
            painter.drawLine(0, bloco.bottom(), self.width(), bloco.bottom())
        painter.setFont(tokens.fonte_ui(14))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(0, self._y_corpo, self.width(), N_BLOCOS * ALTURA_BLOCO),
            Qt.AlignmentFlag.AlignCenter,
            SEM_LEITURA,
        )
        self._desenhar_rodape(painter)

    def _largura_chip(self, texto: str) -> int:
        return self._fm_chip.horizontalAdvance(texto) + 2 * VAO_CHIP + 4

    def _chip(self, painter: QPainter, rect: QRect, texto: str, fundo: QColor) -> None:
        """Bloco preenchido, texto escuro e **traço grosso**.

        O peso 700 não é ênfase: é a terceira coisa que a medição de canal
        cobrou. Traço fino é alta frequência espacial, e alta frequência é o
        que a recompressão joga fora primeiro — com peso normal o chip do
        regime ficava 0,5 ponto abaixo do veredito que ele qualifica, e com
        peso 700 passa. As outras duas foram o corpo (não menor que o do
        dado) e o token (luminância alta; ver `_COR_CONFIANCA`).
        """
        painter.fillRect(rect, fundo)
        painter.setFont(tokens.fonte_ui(CORPO_CHIP, 700))
        painter.setPen(tokens.BG_BASE)
        painter.drawText(
            rect.adjusted(VAO_CHIP, 0, -VAO_CHIP, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            texto,
        )

    def _desenhar_bloco(self, painter: QPainter, indice: int) -> None:
        assert self._leitura is not None
        bloco = self.rect_bloco(indice)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, bloco.bottom(), self.width(), bloco.bottom())

        titulo = self.rect_titulo(indice)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            titulo,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            BLOCOS[indice],
        )
        # A procedência do bloco, na MESMA linha do título dele.
        texto, cor = texto_procedencia(regras_do_bloco(indice))
        self._chip(painter, self.rect_chip_procedencia(indice), texto, cor)

        _, lado = vereditos_do_bloco(indice, self._leitura, self.grid)
        valor = self.rect_valor(indice)
        frase = self.texto_valor(indice)
        painter.setFont(tokens.fonte_numero(13, 600))
        painter.setPen(
            self.paleta.compra
            if lado is Side.BUY
            else self.paleta.venda
            if lado is Side.SELL
            else tokens.TEXT_PRIMARY
        )
        painter.drawText(
            valor,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            frase,
        )

        rects = self.rects_dos_segmentos(indice)
        if rects:
            self._desenhar_barra(painter, indice, rects)
        else:
            self._desenhar_chips(painter, indice)

    def _desenhar_barra(
        self, painter: QPainter, indice: int, rects: tuple[QRect, ...]
    ) -> None:
        assert self._leitura is not None
        segmentos = segmentos_do_bloco(indice, self._leitura, self.paleta)
        faixa = self.rect_faixa(indice)
        painter.fillRect(faixa, tokens.BG_BASE)
        for segmento, rect in zip(segmentos, rects):
            if rect.width() <= 0:
                continue
            painter.fillRect(rect, segmento.cor)
        # O número dentro da barra, no mesmo corpo: quem quer a proporção lê a
        # fatia, quem quer o valor lê o algarismo — o portador é o mesmo, que
        # é a lei do canal aplicada ao caso.
        painter.setFont(tokens.fonte_ui(CORPO_CHIP, 700))
        for segmento, rect in zip(segmentos, rects):
            texto = "%s %s" % (segmento.rotulo, formato.formatar_inteiro(segmento.valor))
            if rect.width() < self._fm_chip.horizontalAdvance(texto) + 2 * VAO_CHIP:
                continue
            painter.setPen(tokens.BG_BASE)
            painter.drawText(
                rect.adjusted(VAO_CHIP, 0, -VAO_CHIP, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                texto,
            )

    def _desenhar_chips(self, painter: QPainter, indice: int) -> None:
        assert self._leitura is not None
        faixa = self.rect_faixa(indice)
        x = faixa.left()
        for texto, cor in chips_do_bloco(indice, self._leitura):
            largura = self._largura_chip(texto)
            if x + largura > faixa.right():
                # F8: o que não cabe não é desenhado pela metade. Chip cortado
                # continua parecendo uma palavra inteira.
                return
            self._chip(
                painter,
                QRect(x, faixa.top() + (faixa.height() - ALTURA_CHIP) // 2, largura, ALTURA_CHIP),
                texto,
                cor,
            )
            x += largura + VAO_CHIP

    def _desenhar_rodape(self, painter: QPainter) -> None:
        rodape = self.rect_rodape()
        painter.fillRect(rodape, tokens.BG_RAISED)
        painter.setPen(tokens.BORDER)
        painter.drawLine(rodape.left(), rodape.top(), rodape.right(), rodape.top())
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        interno = rodape.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            maior_que_cabe(RODAPE_RISCO, interno.width(), self._fm_rotulo),
        )


RODAPE_RISCO: tuple[str, ...] = (
    "RISCO NÃO É AUTOMÁTICO · a qualidade da região é AUSENTE NA FONTE e o "
    "gestor exige que uma pessoa a informe",
    "RISCO NÃO É AUTOMÁTICO · a qualidade da região é AUSENTE NA FONTE",
    "RISCO NÃO É AUTOMÁTICO · QUALIDADE DA REGIÃO AUSENTE NA FONTE",
    "RISCO NÃO É AUTOMÁTICO",
)
"""O rodapé do painel, e o único lugar da tela onde o risco aparece.

Uma TUPLA, do mais longo ao mais curto, e não uma frase: ver `maior_que_cabe`.

Não é aviso legal: é o resultado da leitura do registro. `risco.py` diz que
`gatilho_de_tamanho` é `AUSENTE_NA_FONTE`, `GestorRisco.avaliar` exige uma
`QualidadeRegiao` de quem chama, e `LeituraMetodo` não tem campo de risco.
Um semáforo verde-amarelo-vermelho aqui seria o produto inventando o
classificador que a fonte não tem."""
