from __future__ import annotations

from dataclasses import FrozenInstanceError
from threading import Event, Thread

import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.dados.feed_observavel import (
    BoundedEventDeduplicator,
    FeedEnvelope,
    FeedQualityConfig,
    FeedQualityMonitor,
    FeedQualityObserver,
    ObservableFeedAdapter,
    ReconnectPolicy,
)
from fluxopro.dados.qualidade import (
    AggressorQuality,
    BookKind,
    FeedQualitySnapshot,
    FeedSource,
    FeedState,
    SequenceAvailability,
)


def trade(ts: int, trade_id: str, side: AgressorSide = AgressorSide.BUY) -> Trade:
    return Trade(ts, "WDOV26", 10_000, 5, side, trade_id)


def monitor(**kwargs) -> FeedQualityMonitor:
    return FeedQualityMonitor(
        source=FeedSource.MT5,
        book_kind=BookKind.MBP,
        depth=20,
        aggressor_quality=AggressorQuality.INFERRED,
        clock_ns=lambda: 10_000,
        **kwargs,
    )


def test_snapshot_imutavel_declara_procedencia_e_sequencia_indisponivel() -> None:
    snap = monitor(symbol="WDOV26").snapshot()

    assert snap == FeedQualitySnapshot(
        timestamp_ns=10_000,
        symbol="WDOV26",
        state=FeedState.STOPPED,
        source=FeedSource.MT5,
        book_kind=BookKind.MBP,
        depth=20,
        aggressor_quality=AggressorQuality.INFERRED,
    )
    assert snap.sequence_availability is SequenceAvailability.UNAVAILABLE
    assert snap.sequence_gaps is None
    assert snap.missing_events is None
    assert snap.sequence_regressions is None
    with pytest.raises(FrozenInstanceError):
        snap.depth = 99  # type: ignore[misc]


def test_monitor_detecta_duplicata_sem_filtrar_e_com_memoria_limitada() -> None:
    m = monitor(config=FeedQualityConfig(max_delay_ns=1_000, dedup_capacity=2))
    m.connected()

    snapshots = [
        m.observe(trade(100, "T1"), received_ns=100),
        m.observe(trade(101, "T1"), received_ns=101),
        m.observe(trade(102, "T2"), received_ns=102),
        m.observe(trade(103, "T3"), received_ns=103),
        m.observe(trade(104, "T1"), received_ns=104),
    ]

    assert all(isinstance(snap, FeedQualitySnapshot) for snap in snapshots)
    assert snapshots[-1].received_events == 5
    assert snapshots[-1].accepted_events == 5
    assert snapshots[-1].duplicates == 1
    assert m.dedup_size == 2


def test_sequencia_disponivel_detecta_lacuna_e_regressao_sem_recusar() -> None:
    m = monitor()
    m.connected()

    m.observe(trade(100, "T1"), sequence=10, received_ns=100)
    m.observe(trade(101, "T2"), sequence=13, received_ns=101)
    snap = m.observe(trade(102, "T3"), sequence=12, received_ns=102)

    assert snap.state is FeedState.DEGRADED
    assert snap.sequence_availability is SequenceAvailability.AVAILABLE
    assert snap.sequence_gaps == 1
    assert snap.missing_events == 2
    assert snap.sequence_regressions == 1
    assert snap.last_sequence == 12
    assert snap.accepted_events == 3


def test_sequencia_parcial_e_explicita_quando_metadado_some() -> None:
    m = monitor()

    m.observe(trade(100, "T1"), received_ns=100)
    snap = m.observe(trade(101, "T2"), sequence=7, received_ns=101)

    assert snap.sequence_availability is SequenceAvailability.PARTIAL
    assert snap.events_without_sequence == 1
    assert snap.sequence_gaps == 0


def test_timestamp_regressivo_e_atraso_sao_observados_sem_filtrar() -> None:
    m = monitor(config=FeedQualityConfig(max_delay_ns=10, dedup_capacity=8))
    m.connected()

    first = m.observe(trade(100, "T1"), received_ns=111)
    second = m.observe(trade(99, "T2"), received_ns=112)

    assert first.delayed_events == 1
    assert second.latency_ns == 13
    assert second.regressive_timestamps == 1
    assert second.received_events == second.accepted_events == 2


def test_snapshot_atualiza_profundidade_e_qualidade_do_agressor() -> None:
    m = monitor()
    book = BookSnapshot(
        100,
        "WDOV26",
        tuple(BookLevel(10_000 - i, 10, 1) for i in range(3)),
        tuple(BookLevel(10_001 + i, 10, 1) for i in range(4)),
    )

    m.observe(book, received_ns=100)
    snap = m.observe(trade(101, "T1", AgressorSide.UNKNOWN), received_ns=101)

    assert snap.depth == 4
    assert snap.aggressor_quality is AggressorQuality.PARTIAL
    assert snap.unknown_aggressors == 1


def test_tres_tipos_existentes_sao_observados_sem_adaptar_dominio() -> None:
    m = monitor()
    events = (
        trade(100, "T1"),
        BookSnapshot(101, "WDOV26", (), ()),
        BookDelta(102, "WDOV26", Side.BUY, BookAction.ADD, 9_999, 7, 0),
    )

    snapshots = [
        m.observe(event, received_ns=event.timestamp_ns) for event in events
    ]

    assert [snap.accepted_events for snap in snapshots] == [1, 2, 3]


def test_adaptador_padrao_preserva_sequencia_canonica_inclusive_repeticoes() -> None:
    bus = Barramento()
    events: list[Trade] = []
    quality: list[FeedQualitySnapshot] = []
    bus.assinar(Trade, events.append)
    bus.assinar(FeedQualitySnapshot, quality.append)
    source = [
        FeedEnvelope(trade(100, "T1"), sequence=1, received_ns=100),
        FeedEnvelope(trade(100, "T1"), sequence=1, received_ns=100),
        FeedEnvelope(trade(99, "T0"), sequence=0, received_ns=100),
    ]

    ObservableFeedAdapter(bus, lambda: source, monitor()).iniciar()

    assert [event.trade_id for event in events] == ["T1", "T1", "T0"]
    assert quality[-1].state is FeedState.CLOSED
    assert quality[-1].duplicates == 1
    assert quality[-1].sequence_regressions == 1
    assert quality[-1].regressive_timestamps == 1


def test_evento_sem_envelope_publica_com_sequencia_indisponivel() -> None:
    bus = Barramento()
    quality: list[FeedQualitySnapshot] = []
    bus.assinar(FeedQualitySnapshot, quality.append)

    ObservableFeedAdapter(bus, lambda: [trade(100, "T1")], monitor()).iniciar()

    assert quality[-1].sequence_availability is SequenceAvailability.UNAVAILABLE
    assert quality[-1].sequence_gaps is None


def test_observador_do_barramento_nao_muda_eventos_das_fontes_existentes() -> None:
    bus = Barramento()
    observed_events: list[Trade] = []
    quality: list[FeedQualitySnapshot] = []
    observer = FeedQualityObserver(bus, monitor())
    observer.iniciar()
    bus.assinar(Trade, observed_events.append, prioridade=10)
    bus.assinar(FeedQualitySnapshot, quality.append)
    canonical = [trade(100, "T1"), trade(100, "T1"), trade(99, "T0")]

    for event in canonical:
        bus.publicar(event)
    observer.parar()

    assert observed_events == canonical
    assert quality[-2].sequence_availability is SequenceAvailability.UNAVAILABLE
    assert quality[-2].duplicates == 1
    assert quality[-2].regressive_timestamps == 1
    count_after_stop = observer.monitor.snapshot().received_events
    bus.publicar(trade(101, "T2"))
    assert observer.monitor.snapshot().received_events == count_after_stop


def test_deduplicacao_de_entrega_exige_opt_in_em_componente_separado() -> None:
    bus = Barramento()
    events: list[Trade] = []
    bus.assinar(Trade, events.append)
    repeated = trade(100, "T1")
    deduplicator = BoundedEventDeduplicator(capacity=2)

    ObservableFeedAdapter(
        bus,
        lambda: [repeated, repeated],
        monitor(),
        deduplicator=deduplicator,
    ).iniciar()

    assert events == [repeated]
    assert deduplicator.size == 1


def test_reconexao_fica_desabilitada_por_padrao() -> None:
    calls = 0

    def unavailable():
        nonlocal calls
        calls += 1
        raise ConnectionError("offline")

    adapter = ObservableFeedAdapter(Barramento(), unavailable, monitor())
    adapter.iniciar()

    assert calls == 1
    assert adapter.monitor.snapshot().state is FeedState.ERROR


def test_reconexao_opt_in_tem_backoff_exponencial_limitado() -> None:
    waits: list[float] = []
    calls = 0

    def connect():
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise OSError(f"queda {calls}")
        return [FeedEnvelope(trade(100, "T1"), sequence=1, received_ns=100)]

    adapter = ObservableFeedAdapter(
        Barramento(),
        connect,
        monitor(),
        reconnect_policy=ReconnectPolicy(3, 0.5, 1.0),
        wait=waits.append,
    )
    adapter.iniciar()

    assert calls == 4
    assert waits == [0.5, 1.0, 1.0]
    snap = adapter.monitor.snapshot()
    assert snap.state is FeedState.CLOSED
    assert snap.reconnect_attempts == 3
    assert snap.next_backoff_ns == 0


def test_reconexao_esgotada_termina_sem_loop_infinito() -> None:
    waits: list[float] = []

    def unavailable():
        raise ConnectionError("offline")

    adapter = ObservableFeedAdapter(
        Barramento(),
        unavailable,
        monitor(),
        reconnect_policy=ReconnectPolicy(2, 0.1, 0.15),
        wait=waits.append,
    )
    adapter.iniciar()

    assert waits == [0.1, 0.15]
    assert adapter.monitor.snapshot().state is FeedState.ERROR
    assert isinstance(adapter.last_error, ConnectionError)


def test_falha_de_assinante_propaga_e_nao_e_tratada_como_reconexao() -> None:
    bus = Barramento()
    calls = 0

    def connect():
        nonlocal calls
        calls += 1
        return [trade(100, "T1")]

    def fail(_event: Trade) -> None:
        raise RuntimeError("assinante falhou")

    bus.assinar(Trade, fail)
    adapter = ObservableFeedAdapter(
        bus,
        connect,
        monitor(),
        reconnect_policy=ReconnectPolicy(3, 0.0, 0.0),
    )

    with pytest.raises(RuntimeError, match="assinante falhou"):
        adapter.iniciar()
    assert calls == 1


def test_parar_fecha_fonte_e_e_idempotente() -> None:
    closed: list[bool] = []

    class Source:
        def __iter__(self):
            return self

        def __next__(self):
            raise StopIteration

        def close(self) -> None:
            closed.append(True)

    adapter = ObservableFeedAdapter(Barramento(), Source, monitor())
    adapter.iniciar()
    adapter.parar()
    adapter.parar()

    assert closed == [True]
    assert adapter.monitor.snapshot().state is FeedState.CLOSED


def test_parar_enquanto_generator_esta_em_leitura_encerra_sem_corrida() -> None:
    entered = Event()
    release = Event()

    def source():
        entered.set()
        assert release.wait(timeout=2)
        yield trade(100, "T1")

    adapter = ObservableFeedAdapter(Barramento(), source, monitor())
    worker = Thread(target=adapter.iniciar)
    worker.start()
    assert entered.wait(timeout=2)

    adapter.parar()
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert adapter.monitor.snapshot().state is FeedState.CLOSED
