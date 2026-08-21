from __future__ import annotations

from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import BookAction, BookDelta, BookLevel, BookSnapshot, Side


def test_snapshot_seguido_de_deltas_reconstroi_book_esperado() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    snapshot_inicial = BookSnapshot(
        timestamp_ns=100,
        symbol="WDOFUT",
        bids=(
            BookLevel(price=9999, qty=10, n_orders=2),
            BookLevel(price=9998, qty=5, n_orders=1),
        ),
        asks=(BookLevel(price=10000, qty=8, n_orders=3),),
    )
    barramento.publicar(snapshot_inicial)

    barramento.publicar(
        BookDelta(
            timestamp_ns=101,
            symbol="WDOFUT",
            side=Side.BUY,
            action=BookAction.ADD,
            price=9997,
            qty=20,
            position=2,
        )
    )
    barramento.publicar(
        BookDelta(
            timestamp_ns=102,
            symbol="WDOFUT",
            side=Side.BUY,
            action=BookAction.UPDATE,
            price=9999,
            qty=15,
            position=0,
        )
    )
    barramento.publicar(
        BookDelta(
            timestamp_ns=103,
            symbol="WDOFUT",
            side=Side.SELL,
            action=BookAction.DELETE,
            price=10000,
            qty=0,
            position=0,
        )
    )
    barramento.publicar(
        BookDelta(
            timestamp_ns=104,
            symbol="WDOFUT",
            side=Side.SELL,
            action=BookAction.ADD,
            price=10001,
            qty=12,
            position=0,
        )
    )

    book_final = estado.book_atual(timestamp_ns=104)

    assert book_final.bids == (
        BookLevel(price=9999, qty=15, n_orders=1),
        BookLevel(price=9998, qty=5, n_orders=1),
        BookLevel(price=9997, qty=20, n_orders=1),
    )
    assert book_final.asks == (BookLevel(price=10001, qty=12, n_orders=1),)


def test_eventos_de_outro_symbol_sao_ignorados() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(BookSnapshot(timestamp_ns=1, symbol="WINFUT", bids=(), asks=()))
    barramento.publicar(
        BookDelta(
            timestamp_ns=2,
            symbol="WINFUT",
            side=Side.BUY,
            action=BookAction.ADD,
            price=1,
            qty=1,
            position=0,
        )
    )

    book = estado.book_atual(timestamp_ns=3)
    assert book.bids == ()
    assert book.asks == ()


def test_segundo_snapshot_substitui_book_anterior_por_completo() -> None:
    barramento = Barramento()
    estado = EstadoMercado(barramento, symbol="WDOFUT")

    barramento.publicar(
        BookSnapshot(
            timestamp_ns=1,
            symbol="WDOFUT",
            bids=(BookLevel(price=100, qty=1, n_orders=1),),
            asks=(BookLevel(price=101, qty=1, n_orders=1),),
        )
    )
    barramento.publicar(
        BookSnapshot(
            timestamp_ns=2,
            symbol="WDOFUT",
            bids=(BookLevel(price=200, qty=2, n_orders=2),),
            asks=(BookLevel(price=201, qty=2, n_orders=2),),
        )
    )

    book = estado.book_atual(timestamp_ns=2)
    assert book.bids == (BookLevel(price=200, qty=2, n_orders=2),)
    assert book.asks == (BookLevel(price=201, qty=2, n_orders=2),)
