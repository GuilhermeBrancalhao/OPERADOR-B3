"""Motor determinístico de Dominância Compradora/Vendedora — DTO v1,
componentes A/B/R/W/M, ULTRA com histerese multi-condição, saúde de feed.

Fonte: ``INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md`` (pasta
Codex/outputs, trazido pelo operador). Mesma divisão engine-puro/apresentação
de ``fluxopro/analytics/suporte_resistencia.py`` e ``velocidade_dual.py`` —
este módulo reaproveita os dois em vez de duplicar (mesma amplitude de arco
278°/contra-giro de `velocidade_dual`, mesma máquina de saúde 750ms/3s/0,80
de `suporte_resistencia`).

## Divergências deliberadas em relação ao documento (nunca escondidas):

1. **Q6 fixo vs. float validado.** O documento aceita "float binário... se a
   implementação provar equivalência byte a byte com as fixtures" (§2).
   Este módulo usa `float` do Python com quantização explícita para 6 casas
   decimais por arredondamento half-away-from-zero (`quantizar_q6`) — a
   MESMA semântica numérica do Q6 inteiro, sem a complexidade de aritmética
   de ponto fixo inteira, que este projeto não usa em nenhum outro motor
   (`renko.py`, `sinal_ultra.py` também operam em float/int nativos).
2. **Cross-linguagem (TypeScript/C++/C#).** Este projeto é Python puro; a
   seção 13.4 do documento pede paridade byte-a-byte entre três
   linguagens que não existem aqui. Não aplicável — registrado, não
   ignorado silenciosamente.
3. **Golden JSONL / replay gravado.** Mesma divergência já declarada em
   `suporte_resistencia.py`: testada a PROPRIEDADE de determinismo
   (mesma entrada, mesma saída), sem harness de gravação/replay dedicado.
4. **Book de 5 níveis com decay.** Esta superfície não recebe profundidade
   de livro L2 estruturada (ver `nexo/indisponivel.py`, estado SEM_BOOK) —
   ``fluxopro/ui/paineis/nexo/dominancia.py`` mapeia B/W a partir de sinais
   que o projeto já calcula (mesmo tipo de proxy declarado de
   `suporte_resistencia`), nunca a partir de livro inventado.
5. **``ageMs`` no modo LIVE.** Só quem CHAMA este motor (o painel, que tem
   acesso ao relógio de parede legitimamente para medir staleness) calcula
   idade — o motor recebe ``idade_ms`` já pronta, nunca lê relógio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Mapping

from fluxopro.analytics.suporte_resistencia import EstadoFeed, classificar_saude
from fluxopro.analytics.velocidade_dual import (
    AMPLITUDE_ARCO_GRAUS,
    ANGULO_BASE_MACRO_GRAUS,
    ANGULO_BASE_MICRO_GRAUS,
    wrap180,
)

__all__ = [
    "AGREGADO_QUALIDADE_MIN_ULTRA",
    "ComponenteEvidencia",
    "ContraGiro",
    "DTO_SCHEMA",
    "DominanceHorizonte",
    "DominanciaSnapshot",
    "EstadoDominancia",
    "EstadoFeed",
    "MotorDominancia",
    "PESOS_MACRO",
    "PESOS_MICRO",
    "Saude",
    "calcular_macro",
    "calcular_micro",
    "calcular_placar",
    "classificar_estado_inicial",
    "clamp",
    "componentes_para_dto",
    "confiabilidade",
    "confianca_agregada_ajustada",
    "confluencia_de",
    "contragiro_de",
    "divergente_de",
    "quantizar_q6",
]

DTO_SCHEMA = "asg.buyer-seller-dominance/v1"
VERSAO_CALCULO = "dominance-v1.0.0"


@unique
class EstadoDominancia(Enum):
    BALANCEADO = "BALANCED"
    COMPRA = "BUY"
    VENDA = "SELL"
    ULTRA_COMPRA = "ULTRA_BUY"
    ULTRA_VENDA = "ULTRA_SELL"
    INDISPONIVEL = "UNAVAILABLE"


# --------------------------------------------------------------------------
# Pesos e limiares — cada um nomeado, nenhum solto no meio da fórmula.
# --------------------------------------------------------------------------
PESOS_MICRO = {"A": 0.34, "B": 0.24, "R": 0.20, "W": 0.12, "M": 0.10}
PESOS_MACRO = {"A": 0.28, "B": 0.16, "R": 0.18, "W": 0.08, "M": 0.30}
PESO_RELIABILITY_MICRO = 0.58
PESO_RELIABILITY_MACRO = 0.42

LIMIAR_COMPRA = 0.12
LIMIAR_VENDA = -0.12
LIMIAR_DIVERGENCIA_DISTANCIA = 0.35

# Entrada ULTRA — TODOS simultâneos, comparações inclusivas (§6.1).
ULTRA_ENTRADA_COMPOSITO = 0.78
ULTRA_ENTRADA_HORIZONTE = 0.65
ULTRA_ENTRADA_CONFLUENCIA = 0.65
ULTRA_ENTRADA_CONFIANCA = 0.88
ULTRA_ENTRADA_QUALIDADE = 0.90
ULTRA_ENTRADA_CONFIRMACOES = 2

# Manutenção ULTRA — mais tolerante que entrada, ainda assim exigente (§6.2).
ULTRA_MANUTENCAO_COMPOSITO = 0.68
ULTRA_MANUTENCAO_HORIZONTE = 0.55
ULTRA_MANUTENCAO_CONFIANCA = 0.82
ULTRA_MANUTENCAO_QUALIDADE = 0.85
ULTRA_SAIDA_FALHAS = 3

# BUY/SELL comum — manutenção mais frouxa que entrada, 2 amostras de saída.
COMUM_MANUTENCAO_COMPRA = 0.08
COMUM_MANUTENCAO_VENDA = -0.08
COMUM_SAIDA_AMOSTRAS = 2

AGREGADO_QUALIDADE_MIN_ULTRA = ULTRA_ENTRADA_QUALIDADE  # alias de leitura


# --------------------------------------------------------------------------
# Q6 — half-away-from-zero
# --------------------------------------------------------------------------
def quantizar_q6(valor: float) -> float:
    """Arredonda para 6 casas decimais, half-away-from-zero — `round()` do
    Python usa banker's rounding (arredonda para o par), que discorda do
    documento exatamente nos casos `.5` (`+0.1234565` tem de virar
    `+0.123457`, não `+0.123456`). `-0.0` normaliza para `0.0` (§2: "sem
    -0; qualquer zero é 0")."""

    if valor != valor:  # NaN nunca deveria chegar aqui — mas nunca propaga
        return 0.0
    escalado = valor * 1_000_000
    piso = int(escalado)
    resto = escalado - piso
    if resto >= 0.5:
        piso += 1
    elif resto <= -0.5:
        piso -= 1
    resultado = piso / 1_000_000
    return 0.0 if resultado == 0 else resultado


def clamp(valor: float, minimo: float = -1.0, maximo: float = 1.0) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if numero != numero:
        return 0.0
    return max(minimo, min(maximo, numero))


def normalizar_razao(x: float) -> float:
    return quantizar_q6(clamp(x))


# --------------------------------------------------------------------------
# Componentes -> micro/macro
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ComponenteEvidencia:
    id: str  # "A" | "B" | "R" | "W" | "M"
    normalizado: float
    peso: float

    @property
    def contribuicao(self) -> float:
        return quantizar_q6(self.normalizado * self.peso)


def _combinar(componentes: Mapping[str, float], pesos: Mapping[str, float]) -> float:
    total = sum(clamp(componentes.get(chave, 0.0)) * peso for chave, peso in pesos.items())
    return quantizar_q6(clamp(total))


def calcular_micro(componentes: Mapping[str, float]) -> float:
    """``micro = q6(clamp(0.34A+0.24B+0.20R+0.12W+0.10M, -1, 1))``."""

    return _combinar(componentes, PESOS_MICRO)


def calcular_macro(componentes: Mapping[str, float]) -> float:
    """``macro = q6(clamp(0.28A+0.16B+0.18R+0.08W+0.30M, -1, 1))``."""

    return _combinar(componentes, PESOS_MACRO)


def confiabilidade(qualidade: float, confianca: float) -> float:
    return quantizar_q6(clamp(qualidade, 0.0, 1.0) * clamp(confianca, 0.0, 1.0))


def calcular_composto(micro: float, macro: float, confiab_micro: float,
                      confiab_macro: float) -> float | None:
    """``composite`` — ``None`` (nunca `0`) quando os dois pesos de
    confiabilidade somam zero (§4: "nunca publicar score zero")."""

    wm = quantizar_q6(PESO_RELIABILITY_MICRO * confiab_micro)
    wM = quantizar_q6(PESO_RELIABILITY_MACRO * confiab_macro)
    soma = wm + wM
    if soma <= 0:
        return None
    return quantizar_q6(clamp((micro * wm + macro * wM) / soma))


def calcular_placar(composite: float) -> tuple[float, float]:
    """``(buyPercent, sellPercent)`` — sempre soma exatamente 100,0."""

    buy_tenths = _arredondar_half_away(( composite + 1) * 500)
    buy_tenths = max(0, min(1000, buy_tenths))
    sell_tenths = 1000 - buy_tenths
    return buy_tenths / 10.0, sell_tenths / 10.0


def _arredondar_half_away(valor: float) -> int:
    piso = int(valor)
    resto = valor - piso
    if resto >= 0.5:
        piso += 1
    elif resto <= -0.5:
        piso -= 1
    return piso


def componentes_para_dto(componentes: Mapping[str, float],
                         pesos: Mapping[str, float]) -> tuple[ComponenteEvidencia, ...]:
    """Ordem canônica ascendente A,B,M,R,W (§4: empate por
    `abs(weightedContribution)` desc, depois id lexicográfico — aqui a
    ORDEM DE PUBLICAÇÃO é sempre alfabética; o desempate por magnitude é
    responsabilidade de quem RANQUEIA para explicação, não da lista base)."""

    return tuple(
        ComponenteEvidencia(id=chave, normalizado=normalizar_razao(componentes.get(chave, 0.0)),
                           peso=pesos[chave])
        for chave in sorted(pesos.keys())
    )


def ranking_por_contribuicao(componentes: tuple[ComponenteEvidencia, ...]
                             ) -> tuple[ComponenteEvidencia, ...]:
    """Desempate exigido pelo §4: `abs(weightedContribution)` decrescente,
    depois id lexicográfico — para quem quiser "os componentes que mais
    pesaram", nunca para a lista base do DTO (essa é sempre alfabética)."""

    return tuple(sorted(componentes, key=lambda c: (-abs(c.contribuicao), c.id)))


# --------------------------------------------------------------------------
# Confluência / divergência / contra-giro — reaproveita `velocidade_dual`.
# --------------------------------------------------------------------------
def confluencia_de(micro: float, macro: float) -> float:
    mesmo_sinal = (micro > 0 and macro > 0) or (micro < 0 and macro < 0)
    if not mesmo_sinal:
        return 0.0
    return quantizar_q6(min(abs(micro), abs(macro)))


def divergente_de(micro: float, macro: float) -> bool:
    return (micro * macro) < 0 and abs(micro - macro) >= LIMIAR_DIVERGENCIA_DISTANCIA


@dataclass(frozen=True, slots=True)
class ContraGiro:
    theta_micro: float
    theta_macro: float
    delta_graus: float
    normalizado: float
    divergente: bool


def contragiro_de(micro: float, macro: float) -> ContraGiro:
    u_micro = (clamp(micro) + 1.0) / 2.0
    u_macro = (clamp(macro) + 1.0) / 2.0
    theta_micro = quantizar_q6(ANGULO_BASE_MICRO_GRAUS + AMPLITUDE_ARCO_GRAUS * u_micro)
    theta_macro = quantizar_q6(ANGULO_BASE_MACRO_GRAUS - AMPLITUDE_ARCO_GRAUS * u_macro)
    delta = quantizar_q6(wrap180(theta_micro - theta_macro))
    normalizado = quantizar_q6(clamp(delta / AMPLITUDE_ARCO_GRAUS))
    return ContraGiro(theta_micro, theta_macro, delta, normalizado,
                      divergente_de(micro, macro))


def confianca_agregada_ajustada(confianca_micro: float, confianca_macro: float,
                                divergente: bool) -> float:
    base = quantizar_q6(min(clamp(confianca_micro, 0.0, 1.0), clamp(confianca_macro, 0.0, 1.0)))
    return quantizar_q6(base * 0.70) if divergente else base


# --------------------------------------------------------------------------
# Classificação inicial (sem estado anterior) — §6.1, ordem de prioridade.
# --------------------------------------------------------------------------
def classificar_estado_inicial(
    composite: float, micro: float, macro: float, confluencia: float,
    aggregate_confidence: float, qualidade: float,
) -> EstadoDominancia:
    if (composite >= ULTRA_ENTRADA_COMPOSITO and micro >= ULTRA_ENTRADA_HORIZONTE
            and macro >= ULTRA_ENTRADA_HORIZONTE and confluencia >= ULTRA_ENTRADA_CONFLUENCIA
            and aggregate_confidence >= ULTRA_ENTRADA_CONFIANCA and qualidade >= ULTRA_ENTRADA_QUALIDADE):
        return EstadoDominancia.ULTRA_COMPRA
    if (composite <= -ULTRA_ENTRADA_COMPOSITO and micro <= -ULTRA_ENTRADA_HORIZONTE
            and macro <= -ULTRA_ENTRADA_HORIZONTE and confluencia >= ULTRA_ENTRADA_CONFLUENCIA
            and aggregate_confidence >= ULTRA_ENTRADA_CONFIANCA and qualidade >= ULTRA_ENTRADA_QUALIDADE):
        return EstadoDominancia.ULTRA_VENDA
    if composite >= LIMIAR_COMPRA:
        return EstadoDominancia.COMPRA
    if composite <= LIMIAR_VENDA:
        return EstadoDominancia.VENDA
    return EstadoDominancia.BALANCEADO


def _atende_entrada_ultra(lado: int, composite: float, micro: float, macro: float,
                          confluencia: float, aggregate_confidence: float, qualidade: float) -> bool:
    sinal = lado  # +1 compra, -1 venda
    return (
        sinal * composite >= ULTRA_ENTRADA_COMPOSITO
        and sinal * micro >= ULTRA_ENTRADA_HORIZONTE
        and sinal * macro >= ULTRA_ENTRADA_HORIZONTE
        and confluencia >= ULTRA_ENTRADA_CONFLUENCIA
        and aggregate_confidence >= ULTRA_ENTRADA_CONFIANCA
        and qualidade >= ULTRA_ENTRADA_QUALIDADE
    )


def _atende_manutencao_ultra(lado: int, composite: float, micro: float, macro: float,
                             aggregate_confidence: float, qualidade: float) -> bool:
    sinal = lado
    return (
        sinal * composite >= ULTRA_MANUTENCAO_COMPOSITO
        and sinal * micro >= ULTRA_MANUTENCAO_HORIZONTE
        and sinal * macro >= ULTRA_MANUTENCAO_HORIZONTE
        and aggregate_confidence >= ULTRA_MANUTENCAO_CONFIANCA
        and qualidade >= ULTRA_MANUTENCAO_QUALIDADE
    )


@dataclass
class _HisteresePersistente:
    """Contadores da máquina de estados direcional — §6.2. Mutável de
    proposito (vive dentro do motor, um por `streamId`); nunca exposta
    fora de `MotorDominancia`."""

    estado_anterior: EstadoDominancia = EstadoDominancia.BALANCEADO
    confirmacoes_ultra_compra: int = 0
    confirmacoes_ultra_venda: int = 0
    falhas_manutencao_ultra: int = 0
    amostras_saida_comum: int = 0

    def resetar(self) -> None:
        self.estado_anterior = EstadoDominancia.BALANCEADO
        self.confirmacoes_ultra_compra = 0
        self.confirmacoes_ultra_venda = 0
        self.falhas_manutencao_ultra = 0
        self.amostras_saida_comum = 0


def _proximo_estado(
    persistente: _HisteresePersistente, composite: float, micro: float, macro: float,
    confluencia: float, aggregate_confidence: float, qualidade: float,
) -> EstadoDominancia:
    """Ordem de desempate exigida pelo §6.2: (2) cruzamento forte de lado,
    (3) manutenção/saída do estado anterior, (4) confirmação ULTRA,
    (5) classificação inicial. (1) invalidez/freshness é responsabilidade
    de `MotorDominancia.processar`, antes de chamar esta função."""

    anterior = persistente.estado_anterior

    cruzou_para_venda_forte = composite <= LIMIAR_VENDA and anterior in (
        EstadoDominancia.COMPRA, EstadoDominancia.ULTRA_COMPRA)
    cruzou_para_compra_forte = composite >= LIMIAR_COMPRA and anterior in (
        EstadoDominancia.VENDA, EstadoDominancia.ULTRA_VENDA)
    if cruzou_para_venda_forte:
        persistente.confirmacoes_ultra_compra = 0
        anterior = EstadoDominancia.VENDA
    elif cruzou_para_compra_forte:
        persistente.confirmacoes_ultra_venda = 0
        anterior = EstadoDominancia.COMPRA

    if anterior in (EstadoDominancia.ULTRA_COMPRA, EstadoDominancia.ULTRA_VENDA):
        lado = 1 if anterior is EstadoDominancia.ULTRA_COMPRA else -1
        if _atende_manutencao_ultra(lado, composite, micro, macro, aggregate_confidence, qualidade):
            persistente.falhas_manutencao_ultra = 0
            return anterior
        persistente.falhas_manutencao_ultra += 1
        if persistente.falhas_manutencao_ultra >= ULTRA_SAIDA_FALHAS:
            persistente.falhas_manutencao_ultra = 0
            # Reclassifica no MESMO snapshot — nunca "congela" no ULTRA caído.
            anterior = EstadoDominancia.COMPRA if lado > 0 else EstadoDominancia.VENDA
        else:
            return anterior

    # Se a manutenção comum aceitar o composto atual, o "padrão" a devolver
    # (caso nenhuma promoção a ULTRA aconteça abaixo) é o proprio estado
    # MANTIDO — nunca a classificação do zero, que usa o limiar de ENTRADA
    # (0,12), mais estrito que o de manutenção (0,08). Foi exatamente essa
    # troca de limiar no fallback que fazia BUY cair para BALANCED num
    # composto de +0,08 (mantido por definição, mas abaixo de 0,12).
    resultado_padrao = None
    if anterior in (EstadoDominancia.COMPRA, EstadoDominancia.VENDA):
        limiar = COMUM_MANUTENCAO_COMPRA if anterior is EstadoDominancia.COMPRA else COMUM_MANUTENCAO_VENDA
        mantem = composite >= limiar if anterior is EstadoDominancia.COMPRA else composite <= limiar
        if mantem:
            persistente.amostras_saida_comum = 0
            resultado_padrao = anterior
        else:
            persistente.amostras_saida_comum += 1
            if persistente.amostras_saida_comum < COMUM_SAIDA_AMOSTRAS:
                return anterior
            persistente.amostras_saida_comum = 0
            anterior = EstadoDominancia.BALANCEADO

    if _atende_entrada_ultra(1, composite, micro, macro, confluencia, aggregate_confidence, qualidade):
        persistente.confirmacoes_ultra_compra += 1
        persistente.confirmacoes_ultra_venda = 0
        if persistente.confirmacoes_ultra_compra >= ULTRA_ENTRADA_CONFIRMACOES:
            persistente.confirmacoes_ultra_compra = 0
            return EstadoDominancia.ULTRA_COMPRA
        return EstadoDominancia.COMPRA
    persistente.confirmacoes_ultra_compra = 0

    if _atende_entrada_ultra(-1, composite, micro, macro, confluencia, aggregate_confidence, qualidade):
        persistente.confirmacoes_ultra_venda += 1
        if persistente.confirmacoes_ultra_venda >= ULTRA_ENTRADA_CONFIRMACOES:
            persistente.confirmacoes_ultra_venda = 0
            return EstadoDominancia.ULTRA_VENDA
        return EstadoDominancia.VENDA
    persistente.confirmacoes_ultra_venda = 0

    if resultado_padrao is not None:
        return resultado_padrao
    return classificar_estado_inicial(composite, micro, macro, confluencia,
                                      aggregate_confidence, qualidade)


# --------------------------------------------------------------------------
# DTO
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DominanceHorizonte:
    janela_ms: int
    score: float
    qualidade: float
    confianca: float
    amostras: int
    cobertura_ms: int
    componentes: tuple[ComponenteEvidencia, ...]


@dataclass(frozen=True, slots=True)
class Saude:
    estado: EstadoFeed
    idade_ms: float
    motivo: str | None
    gap_de: int | None = None
    gap_ate: int | None = None
    ultima_sequencia_valida: int | None = None


@dataclass(frozen=True, slots=True)
class DominanciaSnapshot:
    schema: str
    stream_id: str
    event_id: str
    state_seq: int
    timestamp_ns: int
    instrumento: str | None
    modo: str  # "LIVE" | "REPLAY"
    micro: DominanceHorizonte | None
    macro: DominanceHorizonte | None
    composite: float | None
    buy_percent: float | None
    sell_percent: float | None
    estado: EstadoDominancia
    qualidade_agregada: float | None
    confianca_agregada: float | None
    confluencia: float | None
    contra_giro: ContraGiro | None
    saude: Saude
    versao_calculo: str = VERSAO_CALCULO


def _snapshot_seguro(stream_id: str, event_id: str, state_seq: int, timestamp_ns: int,
                     instrumento: str | None, modo: str, saude: Saude) -> DominanciaSnapshot:
    return DominanciaSnapshot(
        schema=DTO_SCHEMA, stream_id=stream_id, event_id=event_id, state_seq=state_seq,
        timestamp_ns=timestamp_ns, instrumento=instrumento, modo=modo,
        micro=None, macro=None, composite=None, buy_percent=None, sell_percent=None,
        estado=EstadoDominancia.INDISPONIVEL, qualidade_agregada=None,
        confianca_agregada=None, confluencia=None, contra_giro=None, saude=saude,
    )


class MotorDominancia:
    """Sequenciamento + idempotência + histerese direcional. A entrada de
    componentes (A/B/R/W/M por horizonte) vem de fora — este motor não lê
    feed, book ou candle; só recebe números já normalizados (mesma
    fronteira de `MotorSuporteResistencia`)."""

    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id
        self._ultima_sequencia = -1
        self._ultimo_timestamp_ns = -1
        self._cache: dict[str, DominanciaSnapshot] = {}
        self._ultimo_valido: DominanciaSnapshot | None = None
        self._histerese = _HisteresePersistente()
        self._recuperando = False
        self._amostras_desde_gap = 0
        self._inicio_recuperacao_ns: int | None = None

    def processar(
        self, *, event_id: str, sequencia: int, timestamp_ns: int, instrumento: str | None,
        modo: str, idade_ms: float,
        componentes_micro: Mapping[str, float] | None, componentes_macro: Mapping[str, float] | None,
        qualidade_micro: float, qualidade_macro: float,
        confianca_micro: float, confianca_macro: float,
        amostras_micro: int, amostras_macro: int,
        cobertura_micro_ms: int, cobertura_macro_ms: int,
    ) -> DominanciaSnapshot:
        if event_id in self._cache:
            return self._cache[event_id]

        if sequencia <= self._ultima_sequencia or timestamp_ns < self._ultimo_timestamp_ns:
            if self._ultimo_valido is not None:
                return self._ultimo_valido
            return _snapshot_seguro(self.stream_id, event_id, sequencia, timestamp_ns,
                                    instrumento, modo,
                                    Saude(EstadoFeed.UNAVAILABLE, idade_ms,
                                         "sequencia_ou_timestamp_regressivo"))

        if self._ultima_sequencia >= 0 and sequencia > self._ultima_sequencia + 1:
            gap_de, gap_ate = self._ultima_sequencia + 1, sequencia - 1
            ultima_valida = self._ultimo_valido.state_seq if self._ultimo_valido else None
            self._ultima_sequencia = sequencia
            self._ultimo_timestamp_ns = timestamp_ns
            self._recuperando = True
            self._amostras_desde_gap = 0
            self._inicio_recuperacao_ns = timestamp_ns
            snapshot = _snapshot_seguro(
                self.stream_id, event_id, sequencia, timestamp_ns, instrumento, modo,
                Saude(EstadoFeed.GAP, idade_ms, "sequencia_saltou", gap_de, gap_ate, ultima_valida),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        self._ultima_sequencia = sequencia
        self._ultimo_timestamp_ns = timestamp_ns
        qualidade = min(clamp(qualidade_micro, 0.0, 1.0), clamp(qualidade_macro, 0.0, 1.0))
        saude_bruta = classificar_saude(idade_ms, qualidade) if modo != "REPLAY" else EstadoFeed.LIVE

        if self._recuperando:
            self._amostras_desde_gap += 1
            tempo_ok = (self._inicio_recuperacao_ns is not None
                       and timestamp_ns - self._inicio_recuperacao_ns >= 1_000_000_000)
            dados_ok = componentes_micro is not None and componentes_macro is not None
            if saude_bruta is EstadoFeed.LIVE and dados_ok and self._amostras_desde_gap >= 50 and tempo_ok:
                self._recuperando = False
            else:
                snapshot = _snapshot_seguro(
                    self.stream_id, event_id, sequencia, timestamp_ns, instrumento, modo,
                    Saude(EstadoFeed.RECOVERING, idade_ms, "recuperando_apos_gap"),
                )
                self._cache[event_id] = snapshot
                self._ultimo_valido = snapshot
                return snapshot

        if (saude_bruta is EstadoFeed.UNAVAILABLE or componentes_micro is None
                or componentes_macro is None):
            snapshot = _snapshot_seguro(
                self.stream_id, event_id, sequencia, timestamp_ns, instrumento, modo,
                Saude(EstadoFeed.UNAVAILABLE, idade_ms, "feed_indisponivel_ou_horizonte_ausente"),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        if saude_bruta is EstadoFeed.STALE and self._ultimo_valido is not None:
            congelado = self._ultimo_valido
            snapshot = DominanciaSnapshot(
                schema=DTO_SCHEMA, stream_id=self.stream_id, event_id=event_id,
                state_seq=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento,
                modo=modo, micro=None, macro=None, composite=None, buy_percent=None,
                sell_percent=None, estado=congelado.estado, qualidade_agregada=None,
                confianca_agregada=None, confluencia=None, contra_giro=None,
                saude=Saude(EstadoFeed.STALE, idade_ms, "idade_ou_qualidade_abaixo_do_minimo"),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        micro = calcular_micro(componentes_micro)
        macro = calcular_macro(componentes_macro)
        confiab_micro = confiabilidade(qualidade_micro, confianca_micro)
        confiab_macro = confiabilidade(qualidade_macro, confianca_macro)
        composite = calcular_composto(micro, macro, confiab_micro, confiab_macro)

        if composite is None:
            snapshot = _snapshot_seguro(
                self.stream_id, event_id, sequencia, timestamp_ns, instrumento, modo,
                Saude(EstadoFeed.UNAVAILABLE, idade_ms, "reliability_zero"),
            )
            self._cache[event_id] = snapshot
            self._ultimo_valido = snapshot
            return snapshot

        confluencia = confluencia_de(micro, macro)
        divergente = divergente_de(micro, macro)
        confianca_agregada = confianca_agregada_ajustada(confianca_micro, confianca_macro, divergente)
        qualidade_agregada = quantizar_q6(qualidade)

        estado = _proximo_estado(self._histerese, composite, micro, macro, confluencia,
                                 confianca_agregada, qualidade_agregada)
        self._histerese.estado_anterior = estado
        buy_pct, sell_pct = calcular_placar(composite)
        contra_giro = contragiro_de(micro, macro)

        snapshot = DominanciaSnapshot(
            schema=DTO_SCHEMA, stream_id=self.stream_id, event_id=event_id,
            state_seq=sequencia, timestamp_ns=timestamp_ns, instrumento=instrumento, modo=modo,
            micro=DominanceHorizonte(3000, micro, quantizar_q6(qualidade_micro),
                                     quantizar_q6(confianca_micro), amostras_micro,
                                     cobertura_micro_ms,
                                     componentes_para_dto(componentes_micro, PESOS_MICRO)),
            macro=DominanceHorizonte(60000, macro, quantizar_q6(qualidade_macro),
                                     quantizar_q6(confianca_macro), amostras_macro,
                                     cobertura_macro_ms,
                                     componentes_para_dto(componentes_macro, PESOS_MACRO)),
            composite=composite, buy_percent=buy_pct, sell_percent=sell_pct, estado=estado,
            qualidade_agregada=qualidade_agregada, confianca_agregada=confianca_agregada,
            confluencia=confluencia, contra_giro=contra_giro,
            saude=Saude(EstadoFeed.LIVE, idade_ms, None),
        )
        self._cache[event_id] = snapshot
        self._ultimo_valido = snapshot
        return snapshot

    def reiniciar(self, novo_stream_id: str) -> None:
        """Novo `streamId` zera sequência, histerese e caches (§6.2/§8.9)."""

        self.stream_id = novo_stream_id
        self._ultima_sequencia = -1
        self._ultimo_timestamp_ns = -1
        self._cache.clear()
        self._ultimo_valido = None
        self._histerese.resetar()
        self._recuperando = False
        self._amostras_desde_gap = 0
        self._inicio_recuperacao_ns = None
