from __future__ import annotations

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookSnapshot, Trade
from fluxopro.dados.simulador import SimuladorWDO


def _rodar(seed: int, n_eventos: int = 200) -> list[Trade | BookSnapshot]:
    barramento = Barramento()
    coletados: list[Trade | BookSnapshot] = []
    barramento.assinar(Trade, coletados.append)
    barramento.assinar(BookSnapshot, coletados.append)
    simulador = SimuladorWDO(barramento, seed=seed, n_eventos=n_eventos)
    simulador.iniciar()
    return coletados


def test_mesma_seed_produz_sequencia_identica() -> None:
    sequencia_1 = _rodar(seed=42)
    sequencia_2 = _rodar(seed=42)
    assert sequencia_1 == sequencia_2
    assert hash(tuple(sequencia_1)) == hash(tuple(sequencia_2))


def test_seeds_diferentes_produzem_sequencias_diferentes() -> None:
    sequencia_a = _rodar(seed=1)
    sequencia_b = _rodar(seed=2)
    assert sequencia_a != sequencia_b


def test_gera_trades_e_snapshots_de_book_coerentes() -> None:
    sequencia = _rodar(seed=7, n_eventos=50)
    trades = [e for e in sequencia if isinstance(e, Trade)]
    snapshots = [e for e in sequencia if isinstance(e, BookSnapshot)]

    assert len(trades) == 50
    assert len(snapshots) == 50
    assert all(t.qty > 0 for t in trades)
    assert all(len(s.bids) == 5 and len(s.asks) == 5 for s in snapshots)
    assert all(s.bids[0].price < s.asks[0].price for s in snapshots)


def test_timestamps_sao_crescentes() -> None:
    sequencia = _rodar(seed=13, n_eventos=100)
    timestamps = [e.timestamp_ns for e in sequencia if isinstance(e, Trade)]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
