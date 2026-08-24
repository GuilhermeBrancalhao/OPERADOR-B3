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
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
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

    assert snap.market_timestamp_ns is None
    assert snap.ingress_timestamp_ns == 10_000
    assert snap.timestamp_ns == snap.ingress_timestamp_ns
    assert snap.symbol == "WDOV26"
    assert snap.state is FeedState.STOPPED
    assert snap.source is FeedSource.MT5
    assert snap.book_kind is BookKind.MBP
    assert snap.depth == 20
    assert snap.aggressor_quality is AggressorQuality.INFERRED
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
        m.observe(trade(100, "T1"), sequence=1, received_ns=100),
        m.observe(trade(101, "T1b"), sequence=1, received_ns=101),
        m.observe(trade(102, "T2"), sequence=2, received_ns=102),
        m.observe(trade(103, "T3"), sequence=3, received_ns=103),
        m.observe(trade(104, "T1c"), sequence=1, received_ns=104),
    ]

    assert all(isinstance(snap, FeedQualitySnapshot) for snap in snapshots)
    assert snapshots[-1].received_events == 5
    assert snapshots[-1].accepted_events == 5
    assert snapshots[-1].duplicates == 1
    assert snapshots[-1].sequence_regressions == 1
    assert m.sequence_window_size == 2


def test_sequencia_disponivel_detecta_lacuna_e_regressao_sem_recusar() -> None:
    m = monitor()
    m.connected()

    m.observe(trade(100, "T1"), sequence=10, received_ns=100)
    m.observe(trade(101, "T2"), sequence=13, received_ns=101)
    m.observe(trade(102, "T3"), sequence=12, received_ns=102)
    m.observe(trade(103, "T4"), sequence=13, received_ns=103)
    snap = m.observe(trade(104, "T5"), sequence=14, received_ns=104)

    assert snap.state is FeedState.DEGRADED
    assert snap.sequence_availability is SequenceAvailability.AVAILABLE
    assert snap.sequence_gaps == 1
    assert snap.missing_events == 2
    assert snap.sequence_regressions == 1
    assert snap.duplicates == 1
    assert snap.sequence_high_watermark == 14
    assert snap.last_sequence == 14
    assert snap.accepted_events == 5


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


def test_replay_historico_separa_tempos_e_nao_inventa_latencia() -> None:
    m = FeedQualityMonitor(
        source=FeedSource.REPLAY,
        clock_ns=lambda: 9_000_000_000_000,
    )

    snap = m.observe(
        trade(100, "T1"),
        ingress_timestamp_ns=8_000_000_000_000,
    )

    assert snap.market_timestamp_ns == 100
    assert snap.ingress_timestamp_ns == 8_000_000_000_000
    assert snap.latency_ns is None
    assert snap.delayed_events == 0
    assert snap.scheduler_delay_ns == 1_000_000_000_000
    assert snap.state is FeedState.STOPPED


def test_dedup_de_sequencia_isola_fonte_e_simbolo() -> None:
    m = monitor()
    wdo = trade(100, "W1")
    win = Trade(101, "WINV26", 25_000, 1, AgressorSide.BUY, "N1")

    m.observe(wdo, sequence=7, received_ns=100)
    different_symbol = m.observe(win, sequence=7, received_ns=101)
    duplicate_wdo = m.observe(wdo, sequence=7, received_ns=102)

    assert different_symbol.duplicates == 0
    assert duplicate_wdo.duplicates == 1
    assert m.sequence_streams == 2


def test_high_watermarks_por_simbolo_tem_teto_de_memoria() -> None:
    m = monitor(config=FeedQualityConfig(max_sequence_streams=2))

    for index, symbol in enumerate(("A", "B", "C")):
        event = Trade(100 + index, symbol, 10_000, 1, AgressorSide.BUY, symbol)
        m.observe(event, sequence=1, received_ns=100 + index)

    assert m.sequence_streams == 2


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


@pytest.mark.parametrize(
    ("tipo", "field", "state"),
    [
        (TipoFalha.DESCONEXAO, "disconnects", FeedState.DEGRADED),
        (TipoFalha.ERRO_FONTE, "source_errors", FeedState.DEGRADED),
        (TipoFalha.GAP_TICKS, "capture_gaps", FeedState.DEGRADED),
        (TipoFalha.GAP_BOOK, "capture_gaps", FeedState.DEGRADED),
        (TipoFalha.RELOGIO_REGREDIU, "clock_regressions", FeedState.DEGRADED),
        (TipoFalha.RECONEXAO, "reconnections", FeedState.CONNECTED),
    ],
)
def test_observer_mapeia_falhas_mt5_sem_reconectar(
    tipo: TipoFalha, field: str, state: FeedState
) -> None:
    bus = Barramento()
    m = monitor()
    observer = FeedQualityObserver(bus, m)
    observer.iniciar()

    bus.publicar(FalhaCaptura(100, "WDOV26", tipo, "falha controlada"))

    snap = m.snapshot()
    assert getattr(snap, field) == 1
    assert snap.state is state
    assert snap.reconnect_attempts == 0


def test_dropped_events_confirmados_nao_se_confundem_com_anomalias() -> None:
    m = monitor()
    failure = FalhaCaptura(
        100,
        "WDOV26",
        TipoFalha.GAP_TICKS,
        "dropped_events=3; motivo=fila_saturada",
    )

    snap = m.observe(failure, received_ns=101)

    assert snap.dropped_events == 3
    assert snap.anomalies == 1
    assert snap.capture_gaps == 1


def test_adaptador_padrao_preserva_sequencia_canonica_inclusive_repeticoes() -> None:
    bus = Barramento()
    events: list[Trade] = []
    bus.assinar(Trade, events.append)
    m = monitor()
    source = [
        FeedEnvelope(trade(100, "T1"), sequence=1, received_ns=100),
        FeedEnvelope(trade(100, "T1"), sequence=1, received_ns=100),
        FeedEnvelope(trade(99, "T0"), sequence=0, received_ns=100),
    ]

    ObservableFeedAdapter(bus, lambda: source, m).iniciar()

    assert [event.trade_id for event in events] == ["T1", "T1", "T0"]
    snap = m.snapshot()
    assert snap.state is FeedState.CLOSED
    assert snap.duplicates == 1
    assert snap.sequence_regressions == 1
    assert snap.regressive_timestamps == 1


def test_evento_sem_envelope_publica_com_sequencia_indisponivel() -> None:
    bus = Barramento()
    m = monitor()

    ObservableFeedAdapter(bus, lambda: [trade(100, "T1")], m).iniciar()

    assert m.snapshot().sequence_availability is SequenceAvailability.UNAVAILABLE
    assert m.snapshot().sequence_gaps is None


def test_observer_nunca_publica_snapshot_aninhado_no_callback() -> None:
    bus = Barramento()
    observed_events: list[Trade] = []
    snapshots_publicados: list[FeedQualitySnapshot] = []
    m = monitor()
    observer = FeedQualityObserver(bus, m)
    observer.iniciar()
    bus.assinar(Trade, observed_events.append, prioridade=10)

    def snapshot_proibido(snapshot: FeedQualitySnapshot) -> None:
        snapshots_publicados.append(snapshot)
        raise RuntimeError("snapshot aninhado bloqueou dominio")

    bus.assinar(FeedQualitySnapshot, snapshot_proibido)
    canonical = [trade(100, "T1"), trade(100, "T1"), trade(99, "T0")]

    for event in canonical:
        bus.publicar(event)
    observer.parar()

    assert observed_events == canonical
    assert snapshots_publicados == []
    assert m.snapshot().sequence_availability is SequenceAvailability.UNAVAILABLE
    assert m.snapshot().regressive_timestamps == 1
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


def test_deduplicador_opt_in_isola_mesma_sequencia_por_fonte() -> None:
    event = trade(100, "T1")
    deduplicator = BoundedEventDeduplicator(capacity=3)

    assert deduplicator.accept(event, source=FeedSource.MT5, sequence=7)
    assert deduplicator.accept(event, source=FeedSource.REPLAY, sequence=7)
    assert not deduplicator.accept(event, source=FeedSource.MT5, sequence=7)


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
    bus = Barramento()
    published: list[Trade] = []
    bus.assinar(Trade, published.append)

    def source():
        entered.set()
        assert release.wait(timeout=2)
        yield trade(100, "T1")

    m = monitor()
    adapter = ObservableFeedAdapter(bus, source, m)
    worker = Thread(target=adapter.iniciar)
    worker.start()
    assert entered.wait(timeout=2)

    adapter.parar()
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert published == []
    assert m.snapshot().received_events == 0
    assert adapter.monitor.snapshot().state is FeedState.CLOSED
