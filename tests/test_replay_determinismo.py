from __future__ import annotations

from pathlib import Path

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookDelta, Trade
from fluxopro.dados.replay import AdaptadorReplay

_TRADES_CSV = """timestamp_ns,symbol,price,qty,side_agressor,trade_id,buyer_broker,seller_broker
100,WDOFUT,10000,5,BUY,T1,B1,S1
100,WDOFUT,10001,3,SELL,T2,B2,S2
250,WDOFUT,10002,1,BUY,T3,B1,S3
"""

_DELTAS_CSV = """timestamp_ns,symbol,side,action,price,qty,position
100,WDOFUT,BUY,ADD,9999,10,0
200,WDOFUT,SELL,UPDATE,10005,20,0
"""


def _rodar(trades_path: Path, deltas_path: Path) -> list[Trade | BookDelta]:
    barramento = Barramento()
    coletados: list[Trade | BookDelta] = []
    barramento.assinar(Trade, coletados.append)
    barramento.assinar(BookDelta, coletados.append)
    adaptador = AdaptadorReplay(barramento, trades_path, deltas_path, velocidade="max")
    adaptador.iniciar()
    return coletados


def test_replay_e_deterministico(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(_DELTAS_CSV, encoding="utf-8")

    sequencia_1 = _rodar(trades_path, deltas_path)
    sequencia_2 = _rodar(trades_path, deltas_path)

    assert sequencia_1 == sequencia_2
    assert hash(tuple(sequencia_1)) == hash(tuple(sequencia_2))
    assert len(sequencia_1) == 5


def test_replay_ordena_por_timestamp_trade_antes_de_delta_em_empate(
    tmp_path: Path,
) -> None:
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(_DELTAS_CSV, encoding="utf-8")

    sequencia = _rodar(trades_path, deltas_path)
    timestamps = [e.timestamp_ns for e in sequencia]

    assert timestamps == sorted(timestamps)
    assert isinstance(sequencia[0], Trade) and sequencia[0].trade_id == "T1"
    assert isinstance(sequencia[1], Trade) and sequencia[1].trade_id == "T2"
    assert isinstance(sequencia[2], BookDelta) and sequencia[2].price == 9999
    assert isinstance(sequencia[3], BookDelta) and sequencia[3].price == 10005
    assert isinstance(sequencia[4], Trade) and sequencia[4].trade_id == "T3"


def test_replay_sem_deltas_publica_so_trades(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    adaptador = AdaptadorReplay(barramento, trades_path, deltas_path=None, velocidade="max")
    adaptador.iniciar()

    assert len(coletados) == 3
