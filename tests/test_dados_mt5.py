from __future__ import annotations

import threading
import time
from collections import namedtuple
from types import SimpleNamespace

import numpy as np
import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
    WDO_GRID,
)
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
from fluxopro.dados.mt5 import AdaptadorMT5, _importar_mt5, derivar_deltas

_TICK_DTYPE = [
    ("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"),
    ("volume", "i8"), ("time_msc", "i8"), ("flags", "i4"), ("volume_real", "f8"),
]

BookInfo = namedtuple("BookInfo", ["type", "price", "volume", "volume_dbl"])

TICK_FLAG_BUY = 1 << 5
TICK_FLAG_SELL = 1 << 6


def _tick(time_msc, bid, ask, last, volume, flags=0, volume_real=0.0):
    return np.array(
        [(time_msc // 1000, bid, ask, last, volume, time_msc, flags, volume_real)],
        dtype=_TICK_DTYPE,
    )[0]


class _FakeMT5:
    """Mock minimo do pacote MetaTrader5 — so o que AdaptadorMT5 usa."""

    COPY_TICKS_ALL = 0
    TICK_FLAG_BUY = TICK_FLAG_BUY
    TICK_FLAG_SELL = TICK_FLAG_SELL
    BOOK_TYPE_BUY = 0
    BOOK_TYPE_SELL = 1

    def __init__(self, ticks_por_chamada=None, books_por_chamada=None):
        self._ticks_por_chamada = list(ticks_por_chamada or [])
        self._books_por_chamada = list(books_por_chamada or [])
        self.encerrado = False
        self.book_liberado = False

    def initialize(self, **kwargs):
        return True

    def symbol_select(self, symbol, enable):
        return True

    def market_book_add(self, symbol):
        return True

    def market_book_release(self, symbol):
        self.book_liberado = True

    def market_book_get(self, symbol):
        if self._books_por_chamada:
            return self._books_por_chamada.pop(0)
        return None

    def copy_ticks_from(self, symbol, de, count, flags):
        if self._ticks_por_chamada:
            return self._ticks_por_chamada.pop(0)
        return np.array([], dtype=_TICK_DTYPE)

    def last_error(self):
        return (0, "ok")

    def shutdown(self):
        self.encerrado = True


def test_importar_mt5_sem_pacote_instalado_da_erro_claro():
    with pytest.raises(RuntimeError, match="MetaTrader5"):
        _importar_mt5()


def test_derivar_deltas_add_update_delete():
    anterior = BookSnapshot(
        timestamp_ns=100, symbol="WDOV26",
        bids=(BookLevel(9999, 10, 1), BookLevel(9998, 20, 2)),
        asks=(BookLevel(10001, 15, 1),),
    )
    atual = BookSnapshot(
        timestamp_ns=200, symbol="WDOV26",
        bids=(BookLevel(9999, 30, 1), BookLevel(9997, 5, 1)),  # 9999 update, 9998 delete, 9997 add
        asks=(BookLevel(10001, 15, 1),),  # sem mudanca
    )
    deltas = derivar_deltas(anterior, atual)
    por_preco = {(d.side, d.price): d for d in deltas}

    assert por_preco[(Side.BUY, 9999)].action == BookAction.UPDATE
    assert por_preco[(Side.BUY, 9999)].qty == 30
    assert por_preco[(Side.BUY, 9998)].action == BookAction.DELETE
    assert por_preco[(Side.BUY, 9997)].action == BookAction.ADD
    assert por_preco[(Side.BUY, 9997)].qty == 5
    # ask nao mudou -> nenhum delta do lado SELL
    assert not any(d.side == Side.SELL for d in deltas)


def test_derivar_deltas_snapshot_identico_nao_gera_delta():
    snap = BookSnapshot(
        timestamp_ns=100, symbol="WDOV26",
        bids=(BookLevel(9999, 10, 1),), asks=(BookLevel(10001, 15, 1),),
    )
    assert derivar_deltas(snap, snap) == []


def test_inferir_agressor_via_flags_buy():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.5, volume=1, flags=TICK_FLAG_BUY)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.BUY


def test_inferir_agressor_via_flags_sell():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=4999.5, volume=1, flags=TICK_FLAG_SELL)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.SELL


def test_inferir_agressor_sem_flags_por_preco_no_ask_e_compra():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.5, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.BUY


def test_inferir_agressor_sem_flags_por_preco_no_bid_e_venda():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=4999.5, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.SELL


def test_inferir_agressor_ambiguo_e_unknown():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.0, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.UNKNOWN


def test_adaptador_mt5_publica_trades_via_fila_ate_thread_principal():
    ticks_msc = 1_000
    fake = _FakeMT5(
        ticks_por_chamada=[
            _tick(ticks_msc, 4999.5, 5000.5, 5000.5, 3, flags=TICK_FLAG_BUY),
        ],
    )
    barramento = Barramento()
    trades: list[Trade] = []
    barramento.assinar(Trade, trades.append)

    adaptador = AdaptadorMT5(
        barramento, "WDOV26", WDO_GRID, mt5_module=fake, intervalo_poll_s=0.01
    )
    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.2)
    adaptador.parar()
    thread.join(timeout=2.0)

    assert len(trades) == 1
    assert trades[0].symbol == "WDOV26"
    assert trades[0].side_agressor is AgressorSide.BUY
    assert trades[0].qty == 3
    assert fake.encerrado is True


def test_adaptador_mt5_deriva_book_delta_entre_polls_consecutivos():
    book_1 = [BookInfo(0, 4999.5, 10, 10.0), BookInfo(1, 5000.5, 15, 15.0)]
    book_2 = [BookInfo(0, 4999.5, 25, 25.0), BookInfo(1, 5000.5, 15, 15.0)]
    fake = _FakeMT5(books_por_chamada=[book_1, book_2, book_2])

    barramento = Barramento()
    snapshots: list[BookSnapshot] = []
    deltas = []
    barramento.assinar(BookSnapshot, snapshots.append)
    from fluxopro.core.eventos import BookDelta
    barramento.assinar(BookDelta, deltas.append)

    adaptador = AdaptadorMT5(
        barramento, "WDOV26", WDO_GRID, mt5_module=fake, intervalo_poll_s=0.01
    )
    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.2)
    adaptador.parar()
    thread.join(timeout=2.0)

    assert len(snapshots) >= 2
    # a segunda leitura de book (qty 10->25 no bid) deve ter gerado UPDATE
    assert any(d.action == BookAction.UPDATE and d.qty == 25 for d in deltas)
