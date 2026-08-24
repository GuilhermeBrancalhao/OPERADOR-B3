"""Observabilidade não intrusiva para eventos de mercado existentes.

O monitor recebe apenas ``Trade``, ``BookSnapshot`` e ``BookDelta`` que a
fonte já aceitou. Ele mede e publica qualidade, mas nunca decide se o evento
segue: a sequência canônica de simulador, replay e MT5 permanece intocada.
Não há conversão de texto, imagem ou resposta de LLM em tick.

Deduplicação de entrega e reconexão genérica existem como políticas separadas
e opt-in. Em particular, o adaptador não deve envolver MT5 com reconexão: o
adaptador MT5 já possui seu próprio ciclo de conexão e sinalização de falhas.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeAlias

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookDelta, BookSnapshot, Trade
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.qualidade import (
    AggressorQuality,
    BookKind,
    FeedQualitySnapshot,
    FeedSource,
    FeedState,
    SequenceAvailability,
)

MarketEvent: TypeAlias = Trade | BookSnapshot | BookDelta
SnapshotSink: TypeAlias = Callable[[FeedQualitySnapshot], None]


@dataclass(frozen=True, slots=True)
class FeedEnvelope:
    """Evento validado acompanhado de metadados opcionais da fonte."""

    event: MarketEvent
    sequence: int | None = None
    received_ns: int | None = None


@dataclass(frozen=True, slots=True)
class FeedQualityConfig:
    """Limites explícitos e pequenos para o caminho quente do observador."""

    max_delay_ns: int = 1_000_000_000
    dedup_capacity: int = 4_096

    def __post_init__(self) -> None:
        if self.max_delay_ns < 0:
            raise ValueError("max_delay_ns deve ser >= 0")
        if self.dedup_capacity < 1:
            raise ValueError("dedup_capacity deve ser >= 1")


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Backoff limitado, usado somente quando o chamador opta por reconectar."""

    max_attempts: int = 3
    initial_backoff_s: float = 0.25
    max_backoff_s: float = 4.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1")
        if self.initial_backoff_s < 0 or self.max_backoff_s < 0:
            raise ValueError("backoff deve ser >= 0")
        if self.initial_backoff_s > self.max_backoff_s:
            raise ValueError("initial_backoff_s deve ser <= max_backoff_s")


def _event_key(event: MarketEvent) -> tuple[object, ...]:
    if isinstance(event, Trade) and event.trade_id:
        return (Trade, event.symbol, event.trade_id)
    return (type(event), event)


class _BoundedSeenEvents:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity deve ser >= 1")
        self.capacity = capacity
        self.order: deque[tuple[object, ...]] = deque()
        self.keys: set[tuple[object, ...]] = set()

    def remember(self, key: tuple[object, ...]) -> bool:
        """Registra ``key`` e diz se ela já estava na janela."""
        if key in self.keys:
            return True
        if len(self.order) == self.capacity:
            self.keys.remove(self.order.popleft())
        self.order.append(key)
        self.keys.add(key)
        return False


class BoundedEventDeduplicator:
    """Filtro separado e opt-in; não faz parte do monitor de qualidade."""

    def __init__(self, capacity: int = 4_096) -> None:
        self._seen = _BoundedSeenEvents(capacity)
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._seen.keys)

    def accept(self, event: MarketEvent) -> bool:
        if not isinstance(event, (Trade, BookSnapshot, BookDelta)):
            raise TypeError("deduplicador aceita Trade, BookSnapshot e BookDelta")
        with self._lock:
            return not self._seen.remember(_event_key(event))


class FeedQualityMonitor:
    """Observa perda, repetição, desordem, timestamp e atraso sem filtrar.

    A janela usada para reconhecer repetição tem tamanho fixo. ``observe``
    sempre contabiliza o evento como aceito porque este monitor fica depois
    da fronteira de aceitação da fonte; seu retorno é o snapshot produzido,
    jamais uma decisão de encaminhamento.
    """

    def __init__(
        self,
        *,
        source: FeedSource,
        book_kind: BookKind = BookKind.NONE,
        depth: int = 0,
        aggressor_quality: AggressorQuality = AggressorQuality.UNKNOWN,
        symbol: str = "",
        config: FeedQualityConfig | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
        sink: SnapshotSink | None = None,
    ) -> None:
        if depth < 0:
            raise ValueError("depth deve ser >= 0")
        self._source = FeedSource(source)
        self._book_kind = BookKind(book_kind)
        self._declared_aggressor_quality = AggressorQuality(aggressor_quality)
        self._aggressor_quality = self._declared_aggressor_quality
        self._symbol = symbol
        self._depth = depth
        self._config = config or FeedQualityConfig()
        self._clock_ns = clock_ns
        self._sink = sink
        self._lock = threading.RLock()

        self._state = FeedState.STOPPED
        self._received_events = 0
        self._duplicates = 0
        self._sequence_gaps = 0
        self._missing_events = 0
        self._sequence_regressions = 0
        self._events_with_sequence = 0
        self._events_without_sequence = 0
        self._regressive_timestamps = 0
        self._delayed_events = 0
        self._unknown_aggressors = 0
        self._reconnect_attempts = 0
        self._latency_ns = 0
        self._last_event_timestamp_ns: int | None = None
        self._last_sequence: int | None = None
        self._next_backoff_ns = 0
        self._detail = ""
        self._seen = _BoundedSeenEvents(self._config.dedup_capacity)

    @property
    def dedup_size(self) -> int:
        with self._lock:
            return len(self._seen.keys)

    @property
    def sink(self) -> SnapshotSink | None:
        with self._lock:
            return self._sink

    def set_sink(self, sink: SnapshotSink | None) -> None:
        with self._lock:
            self._sink = sink

    def snapshot(self, timestamp_ns: int | None = None) -> FeedQualitySnapshot:
        with self._lock:
            return self._snapshot_locked(
                self._clock_ns() if timestamp_ns is None else timestamp_ns
            )

    def connecting(self, detail: str = "") -> FeedQualitySnapshot:
        return self._transition(FeedState.CONNECTING, detail=detail)

    def connected(self, detail: str = "") -> FeedQualitySnapshot:
        return self._transition(
            FeedState.CONNECTED, detail=detail, next_backoff_ns=0
        )

    def disconnected(self, detail: str) -> FeedQualitySnapshot:
        return self._transition(FeedState.DEGRADED, detail=detail)

    def reconnecting(
        self, attempt: int, backoff_s: float, detail: str = ""
    ) -> FeedQualitySnapshot:
        if attempt < 1:
            raise ValueError("attempt deve ser >= 1")
        if backoff_s < 0:
            raise ValueError("backoff_s deve ser >= 0")
        return self._transition(
            FeedState.RECONNECTING,
            detail=detail,
            reconnect_attempts=attempt,
            next_backoff_ns=int(backoff_s * 1_000_000_000),
        )

    def failed(self, detail: str) -> FeedQualitySnapshot:
        return self._transition(FeedState.ERROR, detail=detail, next_backoff_ns=0)

    def close(self, detail: str = "") -> FeedQualitySnapshot:
        return self._transition(FeedState.CLOSED, detail=detail, next_backoff_ns=0)

    def observe(
        self,
        event: MarketEvent,
        *,
        sequence: int | None = None,
        received_ns: int | None = None,
    ) -> FeedQualitySnapshot:
        """Observa um evento já aceito e devolve seu retrato de qualidade."""
        if not isinstance(event, (Trade, BookSnapshot, BookDelta)):
            raise TypeError("feed aceita apenas Trade, BookSnapshot e BookDelta")
        if sequence is not None and sequence < 0:
            raise ValueError("sequence deve ser >= 0")
        received = self._clock_ns() if received_ns is None else received_ns

        with self._lock:
            self._received_events += 1
            self._symbol = event.symbol
            issues: list[str] = []

            duplicate_event = self._seen.remember(_event_key(event))
            duplicate_sequence = False
            if sequence is None:
                self._events_without_sequence += 1
            else:
                self._events_with_sequence += 1
                if self._last_sequence is not None:
                    if sequence == self._last_sequence:
                        duplicate_sequence = True
                    elif sequence < self._last_sequence:
                        self._sequence_regressions += 1
                        issues.append("sequencia regressiva")
                    elif sequence > self._last_sequence + 1:
                        self._sequence_gaps += 1
                        self._missing_events += sequence - self._last_sequence - 1
                        issues.append("lacuna de sequencia")
                self._last_sequence = sequence

            if duplicate_event or duplicate_sequence:
                self._duplicates += 1
                issues.append("evento duplicado")

            if (
                self._last_event_timestamp_ns is not None
                and event.timestamp_ns < self._last_event_timestamp_ns
            ):
                self._regressive_timestamps += 1
                issues.append("timestamp regressivo")
            self._last_event_timestamp_ns = event.timestamp_ns

            self._latency_ns = max(0, received - event.timestamp_ns)
            if self._latency_ns > self._config.max_delay_ns:
                self._delayed_events += 1
                issues.append("evento atrasado")

            self._observe_payload_locked(event)
            if issues:
                self._degrade_locked(", ".join(issues))
            snap = self._snapshot_locked(received)
            sink = self._sink

        if sink is not None:
            sink(snap)
        return snap

    observar = observe

    def _observe_payload_locked(self, event: MarketEvent) -> None:
        if isinstance(event, BookSnapshot):
            self._depth = max(len(event.bids), len(event.asks))
        if isinstance(event, Trade) and event.side_agressor is AgressorSide.UNKNOWN:
            self._unknown_aggressors += 1
            if self._declared_aggressor_quality not in (
                AggressorQuality.UNKNOWN,
                AggressorQuality.PARTIAL,
            ):
                self._aggressor_quality = AggressorQuality.PARTIAL

    def _sequence_availability_locked(self) -> SequenceAvailability:
        if self._events_with_sequence == 0:
            return SequenceAvailability.UNAVAILABLE
        if self._events_without_sequence == 0:
            return SequenceAvailability.AVAILABLE
        return SequenceAvailability.PARTIAL

    def _degrade_locked(self, detail: str) -> None:
        if self._state not in (FeedState.ERROR, FeedState.CLOSED):
            self._state = FeedState.DEGRADED
        self._detail = detail

    def _transition(
        self,
        state: FeedState,
        *,
        detail: str,
        reconnect_attempts: int | None = None,
        next_backoff_ns: int | None = None,
    ) -> FeedQualitySnapshot:
        now = self._clock_ns()
        with self._lock:
            self._state = state
            self._detail = detail
            if reconnect_attempts is not None:
                self._reconnect_attempts = reconnect_attempts
            if next_backoff_ns is not None:
                self._next_backoff_ns = next_backoff_ns
            snap = self._snapshot_locked(now)
            sink = self._sink
        if sink is not None:
            sink(snap)
        return snap

    def _snapshot_locked(self, timestamp_ns: int) -> FeedQualitySnapshot:
        availability = self._sequence_availability_locked()
        sequence_known = availability is not SequenceAvailability.UNAVAILABLE
        return FeedQualitySnapshot(
            timestamp_ns=timestamp_ns,
            symbol=self._symbol,
            state=self._state,
            source=self._source,
            book_kind=self._book_kind,
            depth=self._depth,
            aggressor_quality=self._aggressor_quality,
            sequence_availability=availability,
            received_events=self._received_events,
            accepted_events=self._received_events,
            duplicates=self._duplicates,
            sequence_gaps=self._sequence_gaps if sequence_known else None,
            missing_events=self._missing_events if sequence_known else None,
            sequence_regressions=(
                self._sequence_regressions if sequence_known else None
            ),
            events_without_sequence=self._events_without_sequence,
            regressive_timestamps=self._regressive_timestamps,
            delayed_events=self._delayed_events,
            unknown_aggressors=self._unknown_aggressors,
            reconnect_attempts=self._reconnect_attempts,
            latency_ns=self._latency_ns,
            last_event_timestamp_ns=self._last_event_timestamp_ns,
            last_sequence=self._last_sequence,
            next_backoff_ns=self._next_backoff_ns,
            detail=self._detail,
        )


FeedItem: TypeAlias = MarketEvent | FeedEnvelope
Connector: TypeAlias = Callable[[], Iterable[FeedItem]]


class FeedQualityObserver:
    """Assina o barramento depois da aceitação, sem envolver a fonte.

    É o encaixe indicado para simulador, replay e MT5 existentes. Como esses
    eventos não carregam sequência, o snapshot declara ``UNAVAILABLE``. Uma
    integração de borda que realmente possua sequência pode chamar o monitor
    com ``FeedEnvelope`` antes de publicar, sem alterar o evento de domínio.
    """

    _EVENT_TYPES = (Trade, BookSnapshot, BookDelta)

    def __init__(
        self,
        barramento: Barramento,
        monitor: FeedQualityMonitor,
        *,
        priority: int = 0,
        publish_quality: bool = True,
    ) -> None:
        self._barramento = barramento
        self.monitor = monitor
        self._priority = priority
        self._started = False
        previous_sink = monitor.sink

        def sink(snapshot: FeedQualitySnapshot) -> None:
            if previous_sink is not None:
                previous_sink(snapshot)
            if publish_quality:
                barramento.publicar(snapshot)

        monitor.set_sink(sink)

    def iniciar(self) -> None:
        if self._started:
            return
        self.monitor.connecting("anexando observador ao barramento")
        for event_type in self._EVENT_TYPES:
            self._barramento.assinar(
                event_type, self._observe, prioridade=self._priority
            )
        self._started = True
        self.monitor.connected("observador anexado ao barramento")

    def parar(self) -> None:
        if not self._started and self.monitor.snapshot().state is FeedState.CLOSED:
            return
        if self._started:
            for event_type in self._EVENT_TYPES:
                self._barramento.desassinar(event_type, self._observe)
            self._started = False
        self.monitor.close("observador removido do barramento")

    def _observe(self, event: MarketEvent) -> None:
        self.monitor.observe(event)


class ObservableFeedAdapter(AdaptadorDados):
    """Observa e repassa uma fonte iterável sem mudar sua sequência padrão.

    ``deduplicator=None`` mantém cada evento, inclusive repetidos. Da mesma
    forma, ``reconnect_policy=None`` não cria um segundo ciclo de reconexão.
    As duas mudanças de comportamento exigem opt-in explícito do integrador.
    """

    def __init__(
        self,
        barramento: Barramento,
        connector: Connector,
        monitor: FeedQualityMonitor,
        *,
        deduplicator: BoundedEventDeduplicator | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
        wait: Callable[[float], object] | None = None,
        publish_quality: bool = True,
    ) -> None:
        super().__init__(barramento)
        self._connector = connector
        self.monitor = monitor
        self._deduplicator = deduplicator
        self._reconnect_policy = reconnect_policy
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait
        self._publish_quality = publish_quality
        self._active: Iterator[FeedItem] | None = None
        self._active_lock = threading.Lock()
        self.last_error: Exception | None = None

        previous_sink = monitor.sink

        def sink(snapshot: FeedQualitySnapshot) -> None:
            if previous_sink is not None:
                previous_sink(snapshot)
            if self._publish_quality:
                self._barramento.publicar(snapshot)

        monitor.set_sink(sink)

    def iniciar(self) -> None:
        self._stop.clear()
        self.last_error = None
        self.monitor.connecting("abrindo fonte")
        attempts = 0
        backoff = (
            self._reconnect_policy.initial_backoff_s
            if self._reconnect_policy is not None
            else 0.0
        )
        ended_normally = False

        while not self._stop.is_set():
            source_error: Exception | None = None
            try:
                active = iter(self._connector())
            except Exception as error:
                source_error = error
            else:
                with self._active_lock:
                    self._active = active
                try:
                    self.monitor.connected(
                        "fonte conectada" if attempts == 0 else "fonte reconectada"
                    )
                    while not self._stop.is_set():
                        try:
                            item = next(active)
                        except StopIteration:
                            ended_normally = True
                            break
                        except Exception as error:
                            source_error = error
                            break
                        envelope = (
                            item if isinstance(item, FeedEnvelope) else FeedEnvelope(item)
                        )
                        self.monitor.observe(
                            envelope.event,
                            sequence=envelope.sequence,
                            received_ns=envelope.received_ns,
                        )
                        if (
                            self._deduplicator is None
                            or self._deduplicator.accept(envelope.event)
                        ):
                            self._barramento.publicar(envelope.event)
                finally:
                    self._close_active()

            if ended_normally or self._stop.is_set():
                break
            assert source_error is not None
            self.last_error = source_error
            self.monitor.disconnected(
                f"{type(source_error).__name__}: {source_error}"
            )
            policy = self._reconnect_policy
            if policy is None or attempts >= policy.max_attempts:
                prefix = (
                    "reconexao desabilitada"
                    if policy is None
                    else "reconexao esgotada"
                )
                self.monitor.failed(
                    f"{prefix}: {type(source_error).__name__}: {source_error}"
                )
                break
            attempts += 1
            delay = min(backoff, policy.max_backoff_s)
            self.monitor.reconnecting(attempts, delay, "aguardando reconexao")
            self._wait(delay)
            backoff = min(
                max(backoff * 2, policy.initial_backoff_s), policy.max_backoff_s
            )

        if self._stop.is_set():
            self.monitor.close("encerrado pelo operador")
        elif ended_normally:
            self.monitor.close("fonte esgotada")

    executar = iniciar

    def parar(self) -> None:
        self._stop.set()
        self._close_active()
        if self.monitor.snapshot().state not in (FeedState.ERROR, FeedState.CLOSED):
            self.monitor.close("encerrado pelo operador")

    def _close_active(self) -> None:
        with self._active_lock:
            active, self._active = self._active, None
        close = getattr(active, "close", None)
        if close is not None:
            try:
                close()
            except ValueError as error:
                if "generator already executing" not in str(error):
                    raise
                with self._active_lock:
                    if self._active is None:
                        self._active = active


MonitorQualidadeFeed = FeedQualityMonitor
ObservadorQualidadeFeed = FeedQualityObserver
AdaptadorFeedObservavel = ObservableFeedAdapter
EnvelopeFeed = FeedEnvelope
ConfigQualidadeFeed = FeedQualityConfig
PoliticaReconexao = ReconnectPolicy
DeduplicadorEventosLimitado = BoundedEventDeduplicator


__all__ = [
    "AdaptadorFeedObservavel",
    "BoundedEventDeduplicator",
    "ConfigQualidadeFeed",
    "DeduplicadorEventosLimitado",
    "EnvelopeFeed",
    "FeedEnvelope",
    "FeedQualityConfig",
    "FeedQualityMonitor",
    "FeedQualityObserver",
    "MarketEvent",
    "MonitorQualidadeFeed",
    "ObservableFeedAdapter",
    "ObservadorQualidadeFeed",
    "PoliticaReconexao",
    "ReconnectPolicy",
]
