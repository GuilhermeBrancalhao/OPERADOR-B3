"""Observabilidade não intrusiva para eventos de mercado existentes.

O monitor recebe eventos que a fonte já aceitou e mantém o último snapshot
em memória. Ele nunca publica ``FeedQualitySnapshot`` no barramento: fazê-lo
dentro do callback de ``Trade`` criaria publicação aninhada e permitiria que
um assinante de saúde impedisse a entrega do evento de domínio. A sessão lê
``monitor.snapshot()`` diretamente.

Deduplicação de entrega e reconexão genérica permanecem políticas separadas
e opt-in. O MT5 já tem ciclo próprio de reconexão e só é observado por seus
``FalhaCaptura``; ele não deve ser envolvido pela reconexão genérica daqui.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeAlias

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookDelta, BookSnapshot, Trade
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
from fluxopro.dados.qualidade import (
    AggressorQuality,
    BookKind,
    FeedQualitySnapshot,
    FeedSource,
    FeedState,
    SequenceAvailability,
)

MarketEvent: TypeAlias = Trade | BookSnapshot | BookDelta
ObservedEvent: TypeAlias = MarketEvent | FalhaCaptura

_DROPPED_PATTERN = re.compile(r"(?:^|[ ;])dropped_events=(\d+)(?:[ ;]|$)")


@dataclass(frozen=True, slots=True)
class FeedEnvelope:
    """Evento validado acompanhado de metadados opcionais da fonte."""

    event: MarketEvent
    sequence: int | None = None
    ingress_timestamp_ns: int | None = None
    # Nome antigo mantido para consumidores da rodada anterior.
    received_ns: int | None = None

    def ingress_ns(self) -> int | None:
        if self.ingress_timestamp_ns is not None and self.received_ns is not None:
            raise ValueError(
                "use ingress_timestamp_ns ou received_ns, nunca os dois"
            )
        return (
            self.ingress_timestamp_ns
            if self.ingress_timestamp_ns is not None
            else self.received_ns
        )


@dataclass(frozen=True, slots=True)
class FeedQualityConfig:
    """Limites explícitos para o observador; nenhum cresce com o pregão."""

    max_delay_ns: int = 1_000_000_000
    dedup_capacity: int = 4_096
    max_sequence_streams: int = 64
    latency_comparable: bool | None = None

    def __post_init__(self) -> None:
        if self.max_delay_ns < 0:
            raise ValueError("max_delay_ns deve ser >= 0")
        if self.dedup_capacity < 1:
            raise ValueError("dedup_capacity deve ser >= 1")
        if self.max_sequence_streams < 1:
            raise ValueError("max_sequence_streams deve ser >= 1")


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


class _BoundedSeenKeys:
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


def _event_key(event: MarketEvent) -> tuple[object, ...]:
    if isinstance(event, Trade) and event.trade_id:
        return (Trade, event.symbol, event.trade_id)
    return (type(event), event)


class BoundedEventDeduplicator:
    """Filtro separado e opt-in; o monitor observador nunca o aplica."""

    def __init__(self, capacity: int = 4_096) -> None:
        self._seen = _BoundedSeenKeys(capacity)
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._seen.keys)

    def accept(
        self,
        event: MarketEvent,
        *,
        source: FeedSource = FeedSource.OTHER,
        sequence: int | None = None,
    ) -> bool:
        if not isinstance(event, (Trade, BookSnapshot, BookDelta)):
            raise TypeError("deduplicador aceita Trade, BookSnapshot e BookDelta")
        key = (
            (FeedSource(source), event.symbol, sequence)
            if sequence is not None
            else _event_key(event)
        )
        with self._lock:
            return not self._seen.remember(key)


class FeedQualityMonitor:
    """Observa qualidade sem filtrar, publicar ou reconectar a fonte."""

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
        self._lock = threading.RLock()
        self._latency_comparable = (
            self._source is FeedSource.MT5
            if self._config.latency_comparable is None
            else self._config.latency_comparable
        )

        self._state = FeedState.STOPPED
        self._received_events = 0
        self._anomalies = 0
        self._dropped_events = 0
        self._duplicates = 0
        self._sequence_gaps = 0
        self._missing_events = 0
        self._sequence_regressions = 0
        self._events_with_sequence = 0
        self._events_without_sequence = 0
        self._regressive_timestamps = 0
        self._delayed_events = 0
        self._unknown_aggressors = 0
        self._capture_gaps = 0
        self._source_errors = 0
        self._disconnects = 0
        self._reconnections = 0
        self._clock_regressions = 0
        self._reconnect_attempts = 0
        self._market_timestamp_ns: int | None = None
        self._ingress_timestamp_ns = self._clock_ns()
        self._latency_ns: int | None = None
        self._scheduler_delay_ns: int | None = None
        self._last_event_timestamp_ns: int | None = None
        self._last_sequence: int | None = None
        self._next_backoff_ns = 0
        self._detail = ""
        self._seen_sequences = _BoundedSeenKeys(self._config.dedup_capacity)
        self._high_watermarks: OrderedDict[tuple[FeedSource, str], int] = (
            OrderedDict()
        )

    @property
    def source(self) -> FeedSource:
        return self._source

    @property
    def sequence_window_size(self) -> int:
        with self._lock:
            return len(self._seen_sequences.keys)

    @property
    def sequence_streams(self) -> int:
        with self._lock:
            return len(self._high_watermarks)

    def snapshot(self, ingress_timestamp_ns: int | None = None) -> FeedQualitySnapshot:
        with self._lock:
            if ingress_timestamp_ns is not None:
                self._ingress_timestamp_ns = ingress_timestamp_ns
            return self._snapshot_locked()

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
        event: ObservedEvent,
        *,
        sequence: int | None = None,
        ingress_timestamp_ns: int | None = None,
        received_ns: int | None = None,
    ) -> FeedQualitySnapshot:
        """Observa um evento aceito e devolve o snapshot, sem efeitos externos."""
        if not isinstance(event, (Trade, BookSnapshot, BookDelta, FalhaCaptura)):
            raise TypeError(
                "feed aceita Trade, BookSnapshot, BookDelta e FalhaCaptura"
            )
        if sequence is not None and sequence < 0:
            raise ValueError("sequence deve ser >= 0")
        if ingress_timestamp_ns is not None and received_ns is not None:
            raise ValueError(
                "use ingress_timestamp_ns ou received_ns, nunca os dois"
            )
        supplied_ingress = (
            ingress_timestamp_ns
            if ingress_timestamp_ns is not None
            else received_ns
        )
        observed_ns = self._clock_ns()
        ingress_ns = observed_ns if supplied_ingress is None else supplied_ingress

        with self._lock:
            self._symbol = event.symbol
            self._market_timestamp_ns = event.timestamp_ns
            self._ingress_timestamp_ns = ingress_ns
            self._scheduler_delay_ns = (
                None
                if supplied_ingress is None
                else max(0, observed_ns - supplied_ingress)
            )
            if isinstance(event, FalhaCaptura):
                self._observe_failure_locked(event)
            else:
                self._observe_market_locked(event, sequence, ingress_ns)
            return self._snapshot_locked()

    observar = observe

    def _observe_market_locked(
        self, event: MarketEvent, sequence: int | None, ingress_ns: int
    ) -> None:
        self._received_events += 1
        issues: list[str] = []

        if sequence is None:
            self._events_without_sequence += 1
        else:
            self._events_with_sequence += 1
            stream = (self._source, event.symbol)
            key = (self._source, event.symbol, sequence)
            duplicate = self._seen_sequences.remember(key)
            high = self._touch_high_watermark_locked(stream)
            if duplicate:
                self._duplicates += 1
                self._anomalies += 1
                issues.append("sequencia duplicada")
                if high is None or sequence > high:
                    self._high_watermarks[stream] = sequence
            else:
                if high is not None and sequence > high + 1:
                    self._sequence_gaps += 1
                    self._missing_events += sequence - high - 1
                    self._anomalies += 1
                    issues.append("lacuna de sequencia")
                elif high is not None and sequence < high:
                    self._sequence_regressions += 1
                    self._anomalies += 1
                    issues.append("sequencia regressiva")
                if high is None or sequence > high:
                    self._high_watermarks[stream] = sequence
            self._last_sequence = sequence

        if (
            self._last_event_timestamp_ns is not None
            and event.timestamp_ns < self._last_event_timestamp_ns
        ):
            self._regressive_timestamps += 1
            self._anomalies += 1
            issues.append("timestamp regressivo")
        self._last_event_timestamp_ns = event.timestamp_ns

        self._latency_ns = (
            max(0, ingress_ns - event.timestamp_ns)
            if self._latency_comparable
            else None
        )
        if (
            self._latency_ns is not None
            and self._latency_ns > self._config.max_delay_ns
        ):
            self._delayed_events += 1
            self._anomalies += 1
            issues.append("evento atrasado")

        self._observe_payload_locked(event)
        if issues:
            self._degrade_locked(", ".join(issues))

    def _touch_high_watermark_locked(
        self, stream: tuple[FeedSource, str]
    ) -> int | None:
        high = self._high_watermarks.get(stream)
        if high is not None:
            self._high_watermarks.move_to_end(stream)
            return high
        if len(self._high_watermarks) == self._config.max_sequence_streams:
            self._high_watermarks.popitem(last=False)
        self._high_watermarks[stream] = -1
        return None

    def _observe_failure_locked(self, failure: FalhaCaptura) -> None:
        self._latency_ns = (
            max(0, self._ingress_timestamp_ns - failure.timestamp_ns)
            if self._latency_comparable
            else None
        )
        dropped = _dropped_from_detail(failure.detalhe)
        if dropped:
            self._dropped_events += dropped

        tipo = failure.tipo
        if tipo in (TipoFalha.GAP_TICKS, TipoFalha.GAP_BOOK):
            self._capture_gaps += 1
            self._anomalies += 1
            self._degrade_locked(failure.detalhe)
        elif tipo is TipoFalha.DESCONEXAO:
            self._disconnects += 1
            self._anomalies += 1
            self._degrade_locked(failure.detalhe)
        elif tipo is TipoFalha.ERRO_FONTE:
            self._source_errors += 1
            self._anomalies += 1
            self._degrade_locked(failure.detalhe)
        elif tipo is TipoFalha.RELOGIO_REGREDIU:
            self._clock_regressions += 1
            self._anomalies += 1
            self._degrade_locked(failure.detalhe)
        elif tipo is TipoFalha.RECONEXAO:
            self._reconnections += 1
            self._state = FeedState.CONNECTED
            self._detail = failure.detalhe

    def _observe_payload_locked(self, event: MarketEvent) -> None:
        if isinstance(event, BookSnapshot):
            if self._book_kind is BookKind.NONE:
                self._book_kind = BookKind.MBP
            self._depth = max(len(event.bids), len(event.asks))
        elif isinstance(event, BookDelta) and self._book_kind is BookKind.NONE:
            self._book_kind = BookKind.MBP
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

    def _current_high_watermark_locked(self) -> int | None:
        return self._high_watermarks.get((self._source, self._symbol))

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
        with self._lock:
            self._ingress_timestamp_ns = self._clock_ns()
            self._state = state
            self._detail = detail
            if reconnect_attempts is not None:
                self._reconnect_attempts = reconnect_attempts
            if next_backoff_ns is not None:
                self._next_backoff_ns = next_backoff_ns
            return self._snapshot_locked()

    def _snapshot_locked(self) -> FeedQualitySnapshot:
        availability = self._sequence_availability_locked()
        sequence_known = availability is not SequenceAvailability.UNAVAILABLE
        return FeedQualitySnapshot(
            market_timestamp_ns=self._market_timestamp_ns,
            ingress_timestamp_ns=self._ingress_timestamp_ns,
            symbol=self._symbol,
            state=self._state,
            source=self._source,
            book_kind=self._book_kind,
            depth=self._depth,
            aggressor_quality=self._aggressor_quality,
            sequence_availability=availability,
            received_events=self._received_events,
            accepted_events=self._received_events,
            anomalies=self._anomalies,
            dropped_events=self._dropped_events,
            duplicates=self._duplicates,
            sequence_gaps=self._sequence_gaps if sequence_known else None,
            missing_events=self._missing_events if sequence_known else None,
            sequence_regressions=(
                self._sequence_regressions if sequence_known else None
            ),
            events_without_sequence=self._events_without_sequence,
            sequence_high_watermark=self._current_high_watermark_locked(),
            regressive_timestamps=self._regressive_timestamps,
            delayed_events=self._delayed_events,
            unknown_aggressors=self._unknown_aggressors,
            capture_gaps=self._capture_gaps,
            source_errors=self._source_errors,
            disconnects=self._disconnects,
            reconnections=self._reconnections,
            clock_regressions=self._clock_regressions,
            reconnect_attempts=self._reconnect_attempts,
            latency_ns=self._latency_ns,
            scheduler_delay_ns=self._scheduler_delay_ns,
            last_event_timestamp_ns=self._last_event_timestamp_ns,
            last_sequence=self._last_sequence,
            next_backoff_ns=self._next_backoff_ns,
            detail=self._detail,
        )


def _dropped_from_detail(detail: str) -> int:
    match = _DROPPED_PATTERN.search(detail)
    return int(match.group(1)) if match is not None else 0


FeedItem: TypeAlias = MarketEvent | FeedEnvelope
Connector: TypeAlias = Callable[[], Iterable[FeedItem]]


class FeedQualityObserver:
    """Assina eventos aceitos e atualiza o monitor sem publicar nada."""

    _EVENT_TYPES = (Trade, BookSnapshot, BookDelta, FalhaCaptura)

    def __init__(
        self,
        barramento: Barramento,
        monitor: FeedQualityMonitor,
        *,
        priority: int = 0,
    ) -> None:
        self._barramento = barramento
        self.monitor = monitor
        self._priority = priority
        self._started = False

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

    def _observe(self, event: ObservedEvent) -> None:
        self.monitor.observe(event)


class ObservableFeedAdapter(AdaptadorDados):
    """Observa e repassa uma fonte iterável sem mudar sua sequência padrão."""

    def __init__(
        self,
        barramento: Barramento,
        connector: Connector,
        monitor: FeedQualityMonitor,
        *,
        deduplicator: BoundedEventDeduplicator | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
        wait: Callable[[float], object] | None = None,
    ) -> None:
        super().__init__(barramento)
        self._connector = connector
        self.monitor = monitor
        self._deduplicator = deduplicator
        self._reconnect_policy = reconnect_policy
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait
        self._active: Iterator[FeedItem] | None = None
        self._active_lock = threading.Lock()
        self.last_error: Exception | None = None

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
                        # ``parar`` pode ocorrer enquanto ``next`` está
                        # bloqueado. Checar de novo impede evento tardio.
                        if self._stop.is_set():
                            break
                        envelope = (
                            item if isinstance(item, FeedEnvelope) else FeedEnvelope(item)
                        )
                        ingress_ns = envelope.ingress_ns()
                        self.monitor.observe(
                            envelope.event,
                            sequence=envelope.sequence,
                            ingress_timestamp_ns=ingress_ns,
                        )
                        if (
                            self._deduplicator is None
                            or self._deduplicator.accept(
                                envelope.event,
                                source=self.monitor.source,
                                sequence=envelope.sequence,
                            )
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
    "ObservedEvent",
    "ObservadorQualidadeFeed",
    "PoliticaReconexao",
    "ReconnectPolicy",
]
