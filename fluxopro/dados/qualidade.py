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


class BookState(StrEnum):
    """Disponibilidade temporal do livro, independente do feed de trades."""

    UNAVAILABLE = "unavailable"
    LIVE = "live"
    DELAYED = "delayed"

    INDISPONIVEL = UNAVAILABLE
    AO_VIVO = LIVE
    ATRASADO = DELAYED


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
    observador nunca reduz esse total. ``anomalies`` conta sinais de qualidade
    (gap, repetição, regressão ou falha da fonte), enquanto ``dropped_events``
    conta somente descarte local confirmado. Replay não tem latência de rede:
    nesse caso ``latency_ns`` é ``None``, não um número gigantesco.
    """

    market_timestamp_ns: int | None
    ingress_timestamp_ns: int
    symbol: str
    state: FeedState
    source: FeedSource
    book_kind: BookKind
    depth: int
    aggressor_quality: AggressorQuality
    sequence_availability: SequenceAvailability = SequenceAvailability.UNAVAILABLE
    received_events: int = 0
    accepted_events: int = 0
    anomalies: int = 0
    dropped_events: int = 0
    duplicates: int = 0
    sequence_gaps: int | None = None
    missing_events: int | None = None
    sequence_regressions: int | None = None
    events_without_sequence: int = 0
    sequence_high_watermark: int | None = None
    regressive_timestamps: int = 0
    delayed_events: int = 0
    unknown_aggressors: int = 0
    capture_gaps: int = 0
    source_errors: int = 0
    disconnects: int = 0
    reconnections: int = 0
    clock_regressions: int = 0
    reconnect_attempts: int = 0
    latency_ns: int | None = None
    scheduler_delay_ns: int | None = None
    last_event_timestamp_ns: int | None = None
    last_sequence: int | None = None
    next_backoff_ns: int = 0
    detail: str = ""
    # Campos anexados no fim preservam a construção posicional legada.
    # O timestamp de mercado identifica o book; o de ingresso permite medir
    # sua idade mesmo quando trades continuam chegando.
    book_market_timestamp_ns: int | None = None
    book_ingress_timestamp_ns: int | None = None
    book_age_ns: int | None = None
    book_state: BookState = BookState.UNAVAILABLE

    @property
    def timestamp_ns(self) -> int:
        """Compatibilidade: snapshot é carimbado no ingresso, não no mercado."""
        return self.ingress_timestamp_ns

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
EstadoBook = BookState
QualidadeAgressor = AggressorQuality
DisponibilidadeSequencia = SequenceAvailability


__all__ = [
    "AggressorQuality",
    "BookKind",
    "BookState",
    "DisponibilidadeSequencia",
    "EstadoFeed",
    "EstadoBook",
    "FeedQualitySnapshot",
    "FeedSource",
    "FeedState",
    "FonteFeed",
    "QualidadeAgressor",
    "SequenceAvailability",
    "TipoBook",
]
