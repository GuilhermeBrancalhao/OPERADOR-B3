"""Matemática pura do medidor duplo MICRO/MACRO ("Dual Market Velocity").

Fonte: especificação trazida pelo operador em
``CLAUDE_INTEGRATION_DUAL_MARKET_VELOCITY_GAUGE.md`` (pasta Codex,
outputs/), que por sua vez documenta o protótipo
``dual_market_velocity_gauge.html``. As fórmulas abaixo são as MESMAS da
seção 4/5 daquele documento — este módulo não inventa constante nova, só
porta a matemática (que lá é JavaScript) para Python puro, testável sem
QPainter.

Duas diferenças deliberadas em relação ao documento original (declaradas
aqui, não escondidas — ver seção 12 do guia, "divergências deliberadas"):

1. O DTO ``DualMarketGaugeStateV1`` do documento carrega ``confidence`` E
   ``quality`` como dois eixos [0,1] separados por horizonte. Este projeto
   não mede uma "qualidade" independente da confiança para MICRO/MACRO — a
   única leitura que já existe é ``LinhaMatrizASG.confianca``
   (``ConfiancaASG.ALTA/MEDIA/BAIXA/INDISPONIVEL``, mesma classificação de
   toda a matriz ASG). Este módulo trata ``quality`` como já embutida na
   confiança (fator único de confiabilidade), em vez de inventar uma
   segunda leitura sem fonte.
2. Sem heartbeat/IPC (este é um processo único, não um produtor e um
   consumidor separados) — ``freshness`` vem de ``estado_operacional`` do
   próprio snapshot ASG (``fluxopro/ui/paineis/nexo/indisponivel.py`` já
   usa a mesma fonte), não de um relógio de heartbeat de 500 ms.
"""

from __future__ import annotations

import math

__all__ = [
    "AMPLITUDE_ARCO_GRAUS",
    "ANGULO_BASE_MACRO_GRAUS",
    "ANGULO_BASE_MICRO_GRAUS",
    "LIMIAR_DIRECIONAL",
    "PESO_MACRO",
    "PESO_MICRO",
    "angulo_micro",
    "angulo_macro",
    "clamp",
    "composto_micro_macro",
    "comprimento_aceso",
    "contragiro",
    "rotulo_direcao",
    "wrap180",
]

PESO_MICRO = 0.58
PESO_MACRO = 0.42
LIMIAR_DIRECIONAL = 0.08
AMPLITUDE_ARCO_GRAUS = 278.0
"""``S`` na notação do documento de referência — a MESMA amplitude angular
para os dois arcos (sentidos opostos). Faz parte do contrato do
contra-giro (`contragiro`): mudar isto sem mudar lá descasaria a leitura
angular do valor normalizado."""
ANGULO_BASE_MICRO_GRAUS = -139.0
ANGULO_BASE_MACRO_GRAUS = 139.0
"""Extremos do vão angular de 278° (`AMPLITUDE_ARCO_GRAUS`) que os dois
arcos compartilham — MICRO cresce a partir do extremo negativo, MACRO a
partir do positivo, sentidos opostos dentro do MESMO vão (ver
`angulo_micro`/`angulo_macro`)."""


def clamp(valor: float, minimo: float = -1.0, maximo: float = 1.0) -> float:
    """`NaN`/`None`/não numérico vira `0.0` — nunca propaga um valor inválido
    para dentro de um ângulo ou de uma cor. Mesmo contrato do `clamp` do
    protótipo JS (`Number.isFinite` cai no `0`)."""

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if numero != numero:  # NaN
        return 0.0
    return max(minimo, min(maximo, numero))


def composto_micro_macro(
    normalizado_micro: float, confiabilidade_micro: float,
    normalizado_macro: float, confiabilidade_macro: float,
) -> float:
    """Composto ponderado de MICRO/MACRO — seção 4 do documento de referência.

        reliability_i = clamp(confiabilidade_i, 0, 1)
        weight_micro  = 0.58 * reliability_micro
        weight_macro  = 0.42 * reliability_macro
        composite     = clamp((n_micro*w_micro + n_macro*w_macro) / (w_micro+w_macro))

    Denominador zero (as duas confiabilidades são zero, ou seja, os dois
    horizontes estão INDISPONÍVEIS) devolve `0.0` — quem chama decide o
    rótulo (o documento é explícito: `0` aqui é código de "sem dado", não
    "mercado equilibrado", e a distinção fica para `EstadoContexto`/
    `Freshness`, não para este número)."""

    peso_micro = PESO_MICRO * clamp(confiabilidade_micro, 0.0, 1.0)
    peso_macro = PESO_MACRO * clamp(confiabilidade_macro, 0.0, 1.0)
    soma_pesos = peso_micro + peso_macro
    if soma_pesos <= 0:
        return 0.0
    numerador = clamp(normalizado_micro) * peso_micro + clamp(normalizado_macro) * peso_macro
    return clamp(numerador / soma_pesos)


def rotulo_direcao(composto: float) -> str:
    """`ALTA`/`BAIXA`/`BALANCO` pelos limiares exatos da seção 4
    (``+0.08``/``-0.08``) — os MESMOS limiares numa função só, para que o
    texto e a cor nunca leiam de dois lugares diferentes."""

    if composto > LIMIAR_DIRECIONAL:
        return "ALTA"
    if composto < -LIMIAR_DIRECIONAL:
        return "BAIXA"
    return "BALANCO"


def wrap180(graus: float) -> float:
    """Equivalente em `[-180, +180)`. Mesma fórmula do `wrap180` do
    protótipo JS, em aritmética Python (`%` já devolve resultado não
    negativo para divisor positivo, ao contrário de C/JS — a soma de `360`
    extra antes do segundo módulo neutraliza a diferença de qualquer jeito
    e mantém o mesmo resultado nos dois lados)."""

    return ((graus + 180.0) % 360.0 + 360.0) % 360.0 - 180.0


def angulo_micro(normalizado_micro: float) -> float:
    """``theta_micro`` — cresce no sentido horário conforme MICRO sobe de
    -1 para +1 (seção 5)."""

    u = (clamp(normalizado_micro) + 1.0) / 2.0
    return ANGULO_BASE_MICRO_GRAUS + AMPLITUDE_ARCO_GRAUS * u


def angulo_macro(normalizado_macro: float) -> float:
    """``theta_macro`` — cresce no sentido ANTI-horário conforme MACRO sobe
    de -1 para +1 (seção 5); por isso o sinal do termo é invertido em
    relação a `angulo_micro`."""

    u = (clamp(normalizado_macro) + 1.0) / 2.0
    return ANGULO_BASE_MACRO_GRAUS - AMPLITUDE_ARCO_GRAUS * u


def contragiro(normalizado_micro: float, normalizado_macro: float) -> tuple[float, float]:
    """``(delta_graus, normalizado)`` — separação angular entre as duas
    PONTAS DESENHADAS, na cena de arcos contra-rotativos.

    ATENÇÃO ao que este número **não** é (defeito corrigido em
    31/08/2026): como o arco MACRO contra-rotaciona por construção, esta
    medida é máxima quando os horizontes CONCORDAM e vale ~0° quando eles
    se opõem. Medido: ``contragiro(+1, +1) = -82,0°`` e
    ``contragiro(+1, -1) = 0,0°``. É uma grandeza de LAYOUT (onde as duas
    pontas caem na tela), útil para desenhar, e foi exibida por engano
    como se fosse divergência — um operador lendo "CONTRA-GIRO +0,0°" com
    micro +1,00 e macro -1,00 entendia "horizontes alinhados" no exato
    momento da oposição máxima.

    Para a leitura de divergência use `divergencia_horizontes`.
    """

    delta = wrap180(angulo_micro(normalizado_micro) - angulo_macro(normalizado_macro))
    return delta, clamp(delta / AMPLITUDE_ARCO_GRAUS)


def divergencia_horizontes(normalizado_micro: float,
                           normalizado_macro: float) -> tuple[float, float]:
    """``(delta_graus, normalizado)`` — o quanto MICRO e MACRO discordam.

    Mede os dois horizontes na MESMA escala angular (a do micro), sem a
    contra-rotação de cena, então:

    * ``+1`` e ``+1`` (concordam)  -> ``0,0°``
    * ``+1`` e ``-1`` (opostos)    -> ``-278,0°`` (amplitude cheia)
    * o sinal diz QUEM está mais comprado: positivo = macro acima do
      micro, negativo = micro acima do macro.

    **Sem `wrap180` de propósito.** Divergência é uma grandeza LINEAR em
    ``[-2, +2]`` (a distância entre dois normalizados), não um ângulo
    circular. Como a amplitude da cena (278°) passa de 180°, envolver
    quebraria a monotonicidade justamente nos extremos: medido antes da
    correção, uma diferença de -1,0 dava -139° e a diferença MÁXIMA de
    -2,0 dava +82° — magnitude menor e sinal trocado no pior caso, que é
    exatamente o caso em que o operador mais precisa do número.

    É a grandeza que a tela imprime; `contragiro` continua sendo o que
    posiciona os desenhos.
    """

    diferenca = clamp(normalizado_macro, -1.0, 1.0) - clamp(normalizado_micro, -1.0, 1.0)
    delta = (AMPLITUDE_ARCO_GRAUS / 2.0) * diferenca
    return delta, clamp(diferenca / 2.0)


def comprimento_aceso(normalizado: float) -> float:
    """Fração [0.03, 1.0] do arco que fica "aceso" — piso de 3% (seção 5)
    para que o estado zero continue visível (um arco 100% apagado leria
    como instrumento quebrado, não como "score zero")."""

    return max(0.03, abs(clamp(normalizado)))
