"""Contratos imutáveis para observar a saúde de um feed de mercado.

Os eventos de domínio continuam sendo ``Trade``, ``BookSnapshot`` e
``BookDelta``.  Metadados da borda (fonte, sequência e qualidade) vivem aqui
para que replay, simulador e feeds ao vivo não precisem alterar esses tipos.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FeedState(StrEnum):
    """Estado observável do ciclo de vida da fonte."""

    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSED = "closed"

    # Vocabulário equivalente para consumidores em português.
    PARADO = STOPPED
    CONECTANDO = CONNECTING
    CONECTADO = CONNECTED
    DEGRADADO = DEGRADED
    RECONECTANDO = RECONNECTING
    ERRO = ERROR
    ENCERRADO = CLOSED


class FeedSource(StrEnum):
    """Origem declarada dos eventos; nunca é inferida do conteúdo."""

    SIMULATOR = "simulator"
    REPLAY = "replay"
    MT5 = "mt5"
    OTHER = "other"

    SIMULADOR = SIMULATOR
    OUTRA = OTHER


class BookKind(StrEnum):
    """Semântica do livro exposto pela fonte."""

    NONE = "none"
    MBP = "mbp"
    MBO = "mbo"

    NENHUM = NONE


class AggressorQuality(StrEnum):
    """Procedência do lado agressor, separada do valor BUY/SELL/UNKNOWN."""

    NATIVE = "native"
    INFERRED = "inferred"
    PARTIAL = "partial"
    UNKNOWN = "unknown"

    NATIVO = NATIVE
    INFERIDO = INFERRED
    PARCIAL = PARTIAL
    DESCONHECIDO = UNKNOWN


class SequenceAvailability(StrEnum):
    """Diz se a fonte realmente forneceu sequência para os eventos."""

    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    PARTIAL = "partial"

    INDISPONIVEL = UNAVAILABLE
    DISPONIVEL = AVAILABLE
    PARCIAL = PARTIAL


@dataclass(frozen=True, slots=True)
class FeedQualitySnapshot:
    """Retrato pontual e imutável da saúde de uma fonte.

    Contadores são monotônicos durante a vida do monitor. Quando sequência
    não existe na fonte, ``sequence_gaps`` e os demais contadores associados
    são ``None`` — indisponibilidade nunca é representada como zero lacunas.
    Quando disponível, ``sequence_gaps`` conta ocorrências e
    ``missing_events`` conta quantos números faltaram.
    ``accepted_events`` conta eventos que já chegaram aceitos pela fonte; o
    observador nunca reduz esse total. ``latency_ns`` é o atraso do último
    evento e fica em zero quando o relógio da fonte está à frente do receptor.
    """

    timestamp_ns: int
    symbol: str
    state: FeedState
    source: FeedSource
    book_kind: BookKind
    depth: int
    aggressor_quality: AggressorQuality
    sequence_availability: SequenceAvailability = SequenceAvailability.UNAVAILABLE
    received_events: int = 0
    accepted_events: int = 0
    duplicates: int = 0
    sequence_gaps: int | None = None
    missing_events: int | None = None
    sequence_regressions: int | None = None
    events_without_sequence: int = 0
    regressive_timestamps: int = 0
    delayed_events: int = 0
    unknown_aggressors: int = 0
    reconnect_attempts: int = 0
    latency_ns: int = 0
    last_event_timestamp_ns: int | None = None
    last_sequence: int | None = None
    next_backoff_ns: int = 0
    detail: str = ""

    @property
    def healthy(self) -> bool:
        return self.state is FeedState.CONNECTED

    # Propriedades sem duplicar estado: facilitam consumo pela UI em português.
    @property
    def estado(self) -> FeedState:
        return self.state

    @property
    def fonte(self) -> FeedSource:
        return self.source

    @property
    def profundidade(self) -> int:
        return self.depth

    @property
    def qualidade_agressor(self) -> AggressorQuality:
        return self.aggressor_quality


# Aliases de tipo preservam um vocabulário natural nos módulos em português.
EstadoFeed = FeedState
FonteFeed = FeedSource
TipoBook = BookKind
QualidadeAgressor = AggressorQuality
DisponibilidadeSequencia = SequenceAvailability


__all__ = [
    "AggressorQuality",
    "BookKind",
    "DisponibilidadeSequencia",
    "EstadoFeed",
    "FeedQualitySnapshot",
    "FeedSource",
    "FeedState",
    "FonteFeed",
    "QualidadeAgressor",
    "SequenceAvailability",
    "TipoBook",
]
