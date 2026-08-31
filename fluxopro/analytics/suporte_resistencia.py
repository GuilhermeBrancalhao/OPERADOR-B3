"""Motor determinístico de Suporte e Resistência — DTO v1, cálculo explicável,
histerese e máquina de saúde de feed.

Fonte: ``INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md`` (pasta Codex/outputs,
trazido pelo operador). Este módulo porta o CONTRATO daquele documento
(schema, fórmulas, limiares de histerese, estados de saúde/alerta,
sequenciamento/idempotência) para Python puro e testável — a mesma divisão
"engine puro / apresentação" que o documento pede na seção 2, e que este
projeto já pratica em ``fluxopro/analytics/renko.py``/``candle_temporal.py``.

## Divergências deliberadas em relação ao documento (nunca escondidas — ver
também seção 12 do irmão deste módulo, ``velocidade_dual.py``, e o
"relatório curto" pedido na seção 12 do guia do gauge):

1. **Clustering de candidatos de zona.** O documento pede
   ``clusterPriceEvidence`` a partir de evidência de preço bruta (livro +
   tape) — este projeto não tem hoje uma janela de replay de livro L2
   dedicada a clustering de zona. Os candidatos vêm de níveis QUE O PROJETO
   JÁ CALCULA e que são, por construção, preços de interesse estatístico:
   POC/VAL/VAH do Volume Profile (``fluxopro/analytics`` VAP, nós de maior
   volume negociado) e a Linha Azul (``fluxopro/metodologia/linha_azul.py``,
   nível de cruzamento 50% comprador/vendedor). Nenhum dos dois é
   "suporte/resistência clássico" por si só — a CLASSIFICAÇÃO (`classificar_
   lado`) é que decide, a partir do contexto MICRO/MACRO e da força da
   zona, se aquele nível está funcionando como suporte, resistência ou
   nenhum dos dois neste instante.
2. **Os 8 componentes (A/B/R/J/P/D/E/T).** O documento não define como
   calculá-los — são entradas do "engine" dele. Aqui cada um é mapeado a um
   sinal que o projeto JÁ calcula, com o rótulo CONFIRMADO/IMPRECISO de
   sempre (ver ``fluxopro/ui/paineis/nexo/suporte_resistencia.py`` para o
   mapeamento e a justificativa de cada um).
3. **Replay byte-a-byte com hash sobre fixture JSONL.** Implementado aqui é
   a PROPRIEDADE (mesma entrada -> mesma saída, sequência determinística) —
   testada chamando o motor duas vezes com o mesmo evento. Não existe neste
   projeto uma infraestrutura de gravação/replay de fixture dedicada a este
   motor; construí-la do zero é trabalho de tooling, não de engine, e fica
   como pendência registrada, não como ausência silenciosa.
4. **``idade_ms``/relógio.** Nunca lê relógio de parede internamente (regra
   do projeto): quem chama ``classificar_saude``/``MotorSuporteResistencia.
   processar`` passa ``agora_ns`` explicitamente — mesmo padrão de
   dependência explícita de tempo que ``nucleo.py`` usa para o pulso do
   selo Ultra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Mapping

__all__ = [
    "AlertaSR",
    "ContraGiro",
    "EstadoFeed",
    "EstadoZona",
    "HorizonteScore",
    "LadoZona",
    "MotorSuporteResistencia",
    "Saude",
    "SuporteResistenciaSnapshot",
    "Zona",
    "calcular_contexto",
    "calcular_forca_zona",
    "calcular_macro",
    "calcular_micro",
    "classificar_lado",
    "classificar_saude",
    "clamp",
    "confianca_ajustada",
    "confianca_zona",
    "contragiro_de",
    "e_divergente",
    "pode_entrar",
    "pode_manter",
    "e_watch",
    "deve_invalidar",
    "winsorizar",
]

# --------------------------------------------------------------------------
# Enums do DTO — seção 19-49 do documento
# --------------------------------------------------------------------------


@unique
class LadoZona(Enum):
    SUPORTE = "SUPPORT"
    RESISTENCIA = "RESISTANCE"
    NEUTRO = "NEUTRAL"


@unique
class EstadoFeed(Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    GAP = "GAP"
    UNAVAILABLE = "UNAVAILABLE"
    RECOVERING = "RECOVERING"


@unique
class AlertaSR(Enum):
    NENHUM = "NONE"
    OBSERVAR_SUPORTE = "WATCH_SUPPORT"
    OBSERVAR_RESISTENCIA = "WATCH_RESISTANCE"
    NO_SUPORTE = "AT_SUPPORT"
    NA_RESISTENCIA = "AT_RESISTANCE"
    DIVERGENCIA = "DIVERGENCE"
    BAIXA_CONFIANCA = "LOW_CONFIDENCE"


@unique
class EstadoZona(Enum):
    ATIVA = "ACTIVE"
    OBSERVACAO = "WATCH"
    INVALIDADA = "INVALIDATED"
    EXPIRADA = "EXPIRED"


# --------------------------------------------------------------------------
# Limiares — versionados por constante nomeada, nunca número solto no meio
# da fórmula (mesmo contrato de `fluxopro/asg/sinal_ultra.py`).
# --------------------------------------------------------------------------
VERSAO_CALCULO = "sr-v1.0.0"

PESO_MICRO_A, PESO_MICRO_B, PESO_MICRO_R, PESO_MICRO_J = 0.34, 0.24, 0.24, 0.18
PESO_MACRO_P, PESO_MACRO_D, PESO_MACRO_E, PESO_MACRO_T = 0.31, 0.27, 0.24, 0.18
PESO_CONTEXTO_MICRO, PESO_CONTEXTO_MACRO = 0.55, 0.45
PESO_FORCA_R, PESO_FORCA_J, PESO_FORCA_B, PESO_FORCA_TOQUES = 0.35, 0.25, 0.20, 0.20
TOQUES_REFERENCIA = 5

LIMIAR_CONTEXTO_SUPORTE = 0.12
LIMIAR_CONTEXTO_RESISTENCIA = -0.12
LIMIAR_FORCA_ZONA = 0.55

LIMIAR_DIVERGENCIA_PRODUTO = 0  # micro*macro < 0 (produto negativo = sinais opostos)
LIMIAR_DIVERGENCIA_DISTANCIA = 0.35
FATOR_CONFIANCA_DIVERGENTE = 0.70

# Histerese — seção "Limiar, permanência e histerese".
ENTRADA_SCORE_MIN = 0.55
ENTRADA_PROXIMIDADE_MAX = 1.0  # x largura da zona
ENTRADA_CONFIANCA_MIN = 0.80

MANUTENCAO_SCORE_MIN = 0.45
MANUTENCAO_PROXIMIDADE_MAX = 1.25
MANUTENCAO_CONFIANCA_MIN = 0.75

WATCH_SCORE_MIN, WATCH_SCORE_MAX = 0.45, 0.55
WATCH_PROXIMIDADE_MAX = 1.75

INVALIDACAO_PROXIMIDADE_MIN = 1.5
AMOSTRAS_SAIDA_CONSECUTIVAS = 2

# Saúde de feed — seção "Estados, transições e falhas".
IDADE_LIVE_MAX_MS = 750.0
IDADE_STALE_MAX_MS = 3000.0
QUALIDADE_LIVE_MIN = 0.80
QUALIDADE_STALE_MIN = 0.0  # abaixo de QUALIDADE_LIVE_MIN mas idade ok -> STALE
AMOSTRAS_RECUPERACAO_MIN = 50
TEMPO_RECUPERACAO_SEM_GAP_NS = 1_000_000_000


# --------------------------------------------------------------------------
# Matemática pura
# --------------------------------------------------------------------------
def clamp(valor: float, minimo: float = -1.0, maximo: float = 1.0) -> float:
    """`NaN`/não numérico vira `0.0` — nunca propaga um valor inválido."""

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if numero != numero:  # NaN
        return 0.0
    return max(minimo, min(maximo, numero))


def winsorizar(valor: float, quantil_95: float) -> float:
    """``clip(x/q95, -1, 1)`` — winsorização por quantil da própria sessão
    (seção "Cálculo explicável"), nunca um teto cravado. `quantil_95 <= 0`
    (amostra insuficiente para medir o quantil) devolve `0.0`: sem escala
    para normalizar, o valor não pode fingir ter sido comparado a nada.
    """

    if quantil_95 is None or quantil_95 <= 0:
        return 0.0
    return clamp(valor / quantil_95)


def calcular_micro(agressao: float, desequilibrio_livro: float,
                   reposicao: float, rejeicao: float) -> float:
    """``micro = clamp(0.34A + 0.24B + 0.24R + 0.18J, -1, 1)``."""

    return clamp(
        PESO_MICRO_A * clamp(agressao) + PESO_MICRO_B * clamp(desequilibrio_livro)
        + PESO_MICRO_R * clamp(reposicao) + PESO_MICRO_J * clamp(rejeicao)
    )


def calcular_macro(persistencia: float, delta_acumulado: float,
                   estrutura: float, estabilidade: float) -> float:
    """``macro = clamp(0.31P + 0.27D + 0.24E + 0.18T, -1, 1)``."""

    return clamp(
        PESO_MACRO_P * clamp(persistencia) + PESO_MACRO_D * clamp(delta_acumulado)
        + PESO_MACRO_E * clamp(estrutura) + PESO_MACRO_T * clamp(estabilidade)
    )


def calcular_contexto(micro: float, macro: float) -> float:
    """``contexto = clamp(0.55*micro + 0.45*macro, -1, 1)``."""

    return clamp(PESO_CONTEXTO_MICRO * clamp(micro) + PESO_CONTEXTO_MACRO * clamp(macro))


def calcular_forca_zona(reposicao: float, rejeicao: float,
                        desequilibrio_livro: float, toques: int) -> float:
    """``força_zona = clamp(0.35|R| + 0.25|J| + 0.20|B| + 0.20*min(toques/5,1), 0, 1)``.

    **Magnitude, nunca sinal** (corrigido em 31/08/2026). O documento
    escreve ``0.35R + 0.25J``, mas força de zona é uma grandeza clampada
    em ``[0, 1]``: quem dá o LADO é `classificar_lado`, a partir do
    CONTEXTO — nunca esta função. Deixar R entrar com sinal fazia uma zona
    fortemente defendida por VENDEDORES (reposição negativa) pontuar como
    zona fraca, e a própria fórmula já denunciava a intenção ao usar
    ``|B|`` na mesma linha.

    Efeito medido no app real (replay de 2026-08-28, dia de queda): com R
    negativo o score das zonas ficava em 0,00-0,22 contra o
    `LIMIAR_FORCA_ZONA` de 0,55 — **nenhuma zona era confirmada em nenhum
    quadro do pregão**, mesmo com 6 testes contados na região.
    """

    contribuicao_toques = min(max(0, toques) / TOQUES_REFERENCIA, 1.0)
    bruto = (
        PESO_FORCA_R * abs(clamp(reposicao)) + PESO_FORCA_J * abs(clamp(rejeicao))
        + PESO_FORCA_B * abs(clamp(desequilibrio_livro))
        + PESO_FORCA_TOQUES * contribuicao_toques
    )
    return clamp(bruto, 0.0, 1.0)


def confianca_zona(qualidade_micro: float, qualidade_macro: float, amostras: int) -> float:
    """``confiança = min(qualidade_micro, qualidade_macro) * min(1, amostras/50)``."""

    qualidade = min(clamp(qualidade_micro, 0.0, 1.0), clamp(qualidade_macro, 0.0, 1.0))
    fator_amostras = min(1.0, max(0, amostras) / 50.0)
    return qualidade * fator_amostras


def classificar_lado(contexto: float, forca_zona: float) -> LadoZona:
    """``SUPPORT`` exige contexto>=+0.12 e força>=0.55; ``RESISTANCE`` exige
    contexto<=-0.12 e força>=0.55; senão ``NEUTRAL``."""

    if contexto >= LIMIAR_CONTEXTO_SUPORTE and forca_zona >= LIMIAR_FORCA_ZONA:
        return LadoZona.SUPORTE
    if contexto <= LIMIAR_CONTEXTO_RESISTENCIA and forca_zona >= LIMIAR_FORCA_ZONA:
        return LadoZona.RESISTENCIA
    return LadoZona.NEUTRO


def e_divergente(micro: float, macro: float) -> bool:
    """``micro*macro < 0`` e ``|micro-macro| >= 0.35``."""

    return (micro * macro) < LIMIAR_DIVERGENCIA_PRODUTO and abs(micro - macro) >= LIMIAR_DIVERGENCIA_DISTANCIA


def confianca_ajustada(confianca: float, divergente: bool) -> float:
    """Divergência rebaixa a confiança para 70% — nunca troca o lado da zona."""

    return confianca * FATOR_CONFIANCA_DIVERGENTE if divergente else confianca


@dataclass(frozen=True, slots=True)
class ContraGiro:
    micro: float | None
    macro: float | None
    divergente: bool


def contragiro_de(micro_score: float | None, macro_score: float | None) -> ContraGiro:
    """``contra_giro.micro = -micro.score``, ``contra_giro.macro =
    -macro.score`` — SÓ transformação de desenho/diagnóstico, nunca dado
    bruto novo (seção "Micro e macro continuam independentes")."""

    divergente = (micro_score is not None and macro_score is not None
                 and e_divergente(micro_score, macro_score))
    return ContraGiro(
        micro=None if micro_score is None else -clamp(micro_score),
        macro=None if macro_score is None else -clamp(macro_score),
        divergente=divergente,
    )


# --------------------------------------------------------------------------
# Histerese — entrada / manutenção / watch / invalidação
# --------------------------------------------------------------------------
def pode_entrar(score: float, proximidade_em_larguras: float, confianca: float) -> bool:
    return (score >= ENTRADA_SCORE_MIN
            and proximidade_em_larguras <= ENTRADA_PROXIMIDADE_MAX
            and confianca >= ENTRADA_CONFIANCA_MIN)


def pode_manter(score: float, proximidade_em_larguras: float, confianca: float) -> bool:
    return (score >= MANUTENCAO_SCORE_MIN
            and proximidade_em_larguras <= MANUTENCAO_PROXIMIDADE_MAX
            and confianca >= MANUTENCAO_CONFIANCA_MIN)


def e_watch(score: float, proximidade_em_larguras: float) -> bool:
    """`WATCH_*` — score 0,45-0,55 OU proximidade até 1,75x a largura;
    nunca aciona `AT_*`."""

    return (WATCH_SCORE_MIN <= score < WATCH_SCORE_MAX
            or proximidade_em_larguras <= WATCH_PROXIMIDADE_MAX)


def deve_invalidar(preco_fechamento: float, zona_inferior: float, zona_superior: float,
                   largura: float, lado: LadoZona, macro_concordante: bool) -> bool:
    """Fecha além de `1.5 * largura` pelo lado OPOSTO ao da zona, com macro
    concordando com a invalidação (nunca um único candle isolado sem apoio
    do horizonte mais lento)."""

    if largura <= 0 or not macro_concordante:
        return False
    limite = INVALIDACAO_PROXIMIDADE_MIN * largura
    if lado is LadoZona.SUPORTE:
        return preco_fechamento < zona_inferior - limite
    if lado is LadoZona.RESISTENCIA:
        return preco_fechamento > zona_superior + limite
    return False


# --------------------------------------------------------------------------
# Saúde do feed
# --------------------------------------------------------------------------
def classificar_saude(idade_ms: float, qualidade: float) -> EstadoFeed:
    """`LIVE`/`STALE`/`UNAVAILABLE` a partir de idade+qualidade — GAP e
    RECOVERING são de SEQUÊNCIA (ver `MotorSuporteResistencia`), não deste
    par isolado."""

    if idade_ms > IDADE_STALE_MAX_MS:
        return EstadoFeed.UNAVAILABLE
    if idade_ms <= IDADE_LIVE_MAX_MS and qualidade >= QUALIDADE_LIVE_MIN:
        return EstadoFeed.LIVE
    return EstadoFeed.STALE


# --------------------------------------------------------------------------
# DTO
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class HorizonteScore:
    score: float
    qualidade: float
    janela_ms: int
    amostras: int
    componentes: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Zona:
    id: str
    lado: LadoZona
    preco: int
    inferior: int
    superior: int
    score: float
    confianca: float
    toques: int
    fontes: tuple[str, ...]
    status: EstadoZona


@dataclass(frozen=True, slots=True)
class Saude:
    estado: EstadoFeed
    idade_ms: float
    gap_de: int | None
    gap_ate: int | None
    motivo: str | None
    versao_calculo: str = VERSAO_CALCULO


@dataclass(frozen=True, slots=True)
class SuporteResistenciaSnapshot:
    schema_version: int
    stream_id: str
    event_id: str
    sequencia: int
    timestamp_ns: int
    instrumento: str
    tick_size: float
    ultimo_preco: int | None
    micro: HorizonteScore | None
    macro: HorizonteScore | None
    contra_giro: ContraGiro
    zonas: tuple[Zona, ...]
    dominante: Zona | None
    alerta: AlertaSR
    saude: Saude


def _snapshot_indisponivel(stream_id: str, event_id: str, sequencia: int,
                           timestamp_ns: int, instrumento: str, tick_size: float,
                           motivo: str, idade_ms: float = 0.0) -> SuporteResistenciaSnapshot:
    return SuporteResistenciaSnapshot(
        schema_version=1, stream_id=stream_id, event_id=event_id, sequencia=sequencia,
        timestamp_ns=timestamp_ns, instrumento=instrumento, tick_size=tick_size,
        ultimo_preco=None, micro=None, macro=None,
        contra_giro=ContraGiro(None, None, False), zonas=(), dominante=None,
        alerta=AlertaSR.NENHUM,
        saude=Saude(EstadoFeed.UNAVAILABLE, idade_ms, None, None, motivo),
    )


def dominante_de(zonas: tuple[Zona, ...]) -> Zona | None:
    """``deterministicMax(zones, by=[confidence, score, touches, priceTieBreak])``
    — desempate por MENOR preço em suporte, MAIOR preço em resistência,
    depois por `id` lexicográfico (seção "Cálculo explicável")."""

    ativas = tuple(z for z in zonas if z.status in (EstadoZona.ATIVA, EstadoZona.OBSERVACAO))
    if not ativas:
        return None

    def chave(zona: Zona) -> tuple:
        # max() escolhe o MAIOR: para suporte o desempate favorece MENOR
        # preco, entao a chave inverte o sinal (menor preco -> chave maior).
        desempate_preco = -zona.preco if zona.lado is LadoZona.SUPORTE else zona.preco
        return (zona.confianca, zona.score, zona.toques, desempate_preco, zona.id)

    return max(ativas, key=chave)


def alerta_de(dominante: Zona | None, micro: HorizonteScore | None,
             macro: HorizonteScore | None, proximidade_em_larguras: float | None) -> AlertaSR:
    """Resolve o alerta na MESMA prioridade da tabela "Estados, transições e
    falhas": divergência e baixa confiança são leitura de qualidade, sempre
    checadas primeiro; `AT_*`/`WATCH_*` vêm da zona dominante."""

    if micro is not None and macro is not None and e_divergente(micro.score, macro.score):
        return AlertaSR.DIVERGENCIA
    if dominante is None or proximidade_em_larguras is None:
        return AlertaSR.NENHUM
    if dominante.confianca < ENTRADA_CONFIANCA_MIN and dominante.status is EstadoZona.ATIVA:
        return AlertaSR.BAIXA_CONFIANCA
    if dominante.status is EstadoZona.ATIVA:
        return (AlertaSR.NO_SUPORTE if dominante.lado is LadoZona.SUPORTE
                else AlertaSR.NA_RESISTENCIA if dominante.lado is LadoZona.RESISTENCIA
                else AlertaSR.NENHUM)
    if dominante.status is EstadoZona.OBSERVACAO:
        return (AlertaSR.OBSERVAR_SUPORTE if dominante.lado is LadoZona.SUPORTE
                else AlertaSR.OBSERVAR_RESISTENCIA if dominante.lado is LadoZona.RESISTENCIA
                else AlertaSR.NENHUM)
    return AlertaSR.NENHUM


# --------------------------------------------------------------------------
# Motor com sequenciamento, idempotência e recuperação
# --------------------------------------------------------------------------
class MotorSuporteResistencia:
    """Aceita eventos em ORDEM, publica snapshots imutáveis. Pura o
    suficiente para ser testada sem QPainter/UI: `processar` recebe todos os
    números já calculados (o "engine" de componentes vive fora, em
    `fluxopro/ui/paineis/nexo/suporte_resistencia.py`, que sabe ler
    `EstadoNexo`) — este motor só garante sequência, idempotência,
    congelamento em falha e a matemática de zona/alerta acima.
    """

    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id
        self._ultima_sequencia = -1
        self._ultimo_timestamp_ns = -1
        self._cache: dict[str, SuporteResistenciaSnapshot] = {}
        self._ultimo_valido: SuporteResistenciaSnapshot | None = None
        self._recuperando = False
        self._amostras_desde_gap = 0
        self._inicio_recuperacao_ns: int | None = None

    def processar(
        self, *, event_id: str, sequencia: int, timestamp_ns: int, instrumento: str,
        tick_size: float, ultimo_preco: int | None,
        micro: HorizonteScore | None, macro: HorizonteScore | None,
        zonas_candidatas: tuple[Zona, ...], agora_ns: int,
    ) -> SuporteResistenciaSnapshot:
        if event_id in self._cache:
            return self._cache[event_id]

        if sequencia <= self._ultima_sequencia or timestamp_ns < self._ultimo_timestamp_ns:
            # Rejeitado: devolve o ULTIMO snapshot valido, nunca aplica o evento.
            if self._ultimo_valido is not None:
                return self._ultimo_valido
            return _snapshot_indisponivel(self.stream_id, event_id, sequencia, timestamp_ns,
                                          instrumento, tick_size, "sequencia_ou_timestamp_regressivo")

        if self._ultima_sequencia >= 0 and sequencia > self._ultima_sequencia + 1:
            gap_de, gap_ate = self._ultima_sequencia + 1, sequencia - 1
            self._ultima_sequencia = sequencia
            self._ultimo_timestamp_ns = timestamp_ns
            self._recuperando = True
            self._amostras_desde_gap = 0
            self._inicio_recuperacao_ns = timestamp_ns
            snapshot = SuporteResistenciaSnapshot(
                schema_version=1, stream_id=self.stream_id, event_id=event_id,
                sequencia=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento,
                tick_size=tick_size,
                ultimo_preco=(self._ultimo_valido.ultimo_preco if self._ultimo_valido else None),
                micro=(self._ultimo_valido.micro if self._ultimo_valido else None),
                macro=(self._ultimo_valido.macro if self._ultimo_valido else None),
                contra_giro=(self._ultimo_valido.contra_giro if self._ultimo_valido
                            else ContraGiro(None, None, False)),
                zonas=(self._ultimo_valido.zonas if self._ultimo_valido else ()),
                dominante=(self._ultimo_valido.dominante if self._ultimo_valido else None),
                alerta=AlertaSR.BAIXA_CONFIANCA,
                saude=Saude(EstadoFeed.GAP, 0.0, gap_de, gap_ate, "sequencia_saltou"),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        self._ultima_sequencia = sequencia
        self._ultimo_timestamp_ns = timestamp_ns

        idade_ms = max(0.0, (agora_ns - timestamp_ns) / 1_000_000.0)
        qualidade = 0.0
        if micro is not None and macro is not None:
            qualidade = min(clamp(micro.qualidade, 0.0, 1.0), clamp(macro.qualidade, 0.0, 1.0))
        saude_bruta = classificar_saude(idade_ms, qualidade)

        if self._recuperando:
            self._amostras_desde_gap += 1
            tempo_ok = (self._inicio_recuperacao_ns is not None
                       and timestamp_ns - self._inicio_recuperacao_ns >= TEMPO_RECUPERACAO_SEM_GAP_NS)
            if saude_bruta is EstadoFeed.LIVE and self._amostras_desde_gap >= AMOSTRAS_RECUPERACAO_MIN and tempo_ok:
                self._recuperando = False
            else:
                estado_final = EstadoFeed.RECOVERING
                snapshot = SuporteResistenciaSnapshot(
                    schema_version=1, stream_id=self.stream_id, event_id=event_id,
                    sequencia=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento,
                    tick_size=tick_size, ultimo_preco=ultimo_preco, micro=micro, macro=macro,
                    contra_giro=contragiro_de(micro.score if micro else None,
                                              macro.score if macro else None),
                    zonas=zonas_candidatas, dominante=dominante_de(zonas_candidatas),
                    alerta=AlertaSR.BAIXA_CONFIANCA,
                    saude=Saude(estado_final, idade_ms, None, None, "recuperando_apos_gap"),
                )
                self._cache[event_id] = snapshot
                self._ultimo_valido = snapshot
                return snapshot

        if saude_bruta is EstadoFeed.UNAVAILABLE or micro is None or macro is None:
            snapshot = _snapshot_indisponivel(
                self.stream_id, event_id, sequencia, timestamp_ns, instrumento, tick_size,
                "feed_indisponivel_ou_horizonte_ausente", idade_ms,
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        if saude_bruta is EstadoFeed.STALE and self._ultimo_valido is not None:
            # STALE congela o ULTIMO snapshot valido — nunca recalcula, so
            # atualiza idade/estado (seção "Estados, transições e falhas").
            congelado = self._ultimo_valido
            snapshot = SuporteResistenciaSnapshot(
                schema_version=1, stream_id=self.stream_id, event_id=event_id,
                sequencia=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento,
                tick_size=tick_size, ultimo_preco=congelado.ultimo_preco,
                micro=congelado.micro, macro=congelado.macro,
                contra_giro=congelado.contra_giro, zonas=congelado.zonas,
                dominante=congelado.dominante, alerta=AlertaSR.BAIXA_CONFIANCA,
                saude=Saude(EstadoFeed.STALE, idade_ms, None, None, "idade_ou_qualidade_abaixo_do_minimo"),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        contexto = calcular_contexto(micro.score, macro.score)
        zonas_avaliadas = tuple(
            dataclasses_replace_status(z, contexto) for z in zonas_candidatas
        )
        dominante = dominante_de(zonas_avaliadas)
        proximidade = None
        if dominante is not None and ultimo_preco is not None:
            largura = max(1, dominante.superior - dominante.inferior)
            proximidade = abs(ultimo_preco - dominante.preco) / largura
        divergente = e_divergente(micro.score, macro.score)
        alerta = alerta_de(dominante, micro, macro, proximidade)

        snapshot = SuporteResistenciaSnapshot(
            schema_version=1, stream_id=self.stream_id, event_id=event_id,
            sequencia=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento,
            tick_size=tick_size, ultimo_preco=ultimo_preco, micro=micro, macro=macro,
            contra_giro=contragiro_de(micro.score, macro.score),
            zonas=zonas_avaliadas, dominante=dominante, alerta=alerta,
            saude=Saude(EstadoFeed.LIVE, idade_ms, None, None, None),
        )
        self._cache[event_id] = snapshot
        self._ultimo_valido = snapshot
        return snapshot


def dataclasses_replace_status(zona: Zona, contexto: float) -> Zona:
    """Reclassifica `zona.status` a partir do CONTEXTO corrente e da força
    já publicada nela — a zona candidata chega com `lado`/`score`/`força`
    já calculados por quem monta `zonas_candidatas`; aqui so decide ATIVA
    vs OBSERVACAO vs o que já estava (INVALIDADA/EXPIRADA não regridem)."""

    if zona.status in (EstadoZona.INVALIDADA, EstadoZona.EXPIRADA):
        return zona
    if zona.score >= LIMIAR_FORCA_ZONA:
        novo_status = EstadoZona.ATIVA
    elif zona.score >= WATCH_SCORE_MIN:
        novo_status = EstadoZona.OBSERVACAO
    else:
        novo_status = EstadoZona.EXPIRADA
    if novo_status is zona.status:
        return zona
    return Zona(
        id=zona.id, lado=zona.lado, preco=zona.preco, inferior=zona.inferior,
        superior=zona.superior, score=zona.score, confianca=zona.confianca,
        toques=zona.toques, fontes=zona.fontes, status=novo_status,
    )
