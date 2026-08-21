"""Estado corrente do mercado, reconstruído a partir dos eventos publicados.

Uma instância de `EstadoMercado` acompanha um único símbolo (quem precisa de
vários símbolos instancia um `EstadoMercado` por symbol e assina todos no
mesmo `Barramento`). Mantém: último trade, book (via deltas incrementais ou
snapshots completos), candles OHLCV+delta por timeframe e a sessão
(high/low/vwap acumulado).
"""

from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Candle,
    Side,
    Trade,
)

NS_POR_MINUTO = 60_000_000_000


@dataclass(slots=True)
class _CandleEmFormacao:
    timestamp_inicio_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int = 0
    delta: int = 0

    def congelar(self) -> Candle:
        return Candle(
            timestamp_ns=self.timestamp_inicio_ns,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            delta=self.delta,
        )


@dataclass(slots=True)
class Sessao:
    """High/low/volume/vwap acumulados desde o início da sessão."""

    high: int | None = None
    low: int | None = None
    volume_total: int = 0
    soma_preco_qty: int = 0

    def registrar_trade(self, preco: int, qty: int) -> None:
        self.high = preco if self.high is None else max(self.high, preco)
        self.low = preco if self.low is None else min(self.low, preco)
        self.volume_total += qty
        self.soma_preco_qty += preco * qty

    @property
    def vwap(self) -> float:
        if self.volume_total == 0:
            return 0.0
        return self.soma_preco_qty / self.volume_total


class EstadoMercado:
    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        timeframe_ns: int = NS_POR_MINUTO,
    ) -> None:
        self._symbol = symbol
        self._timeframe_ns = timeframe_ns
        self.ultimo_trade: Trade | None = None
        self._bids: dict[int, BookLevel] = {}
        self._asks: dict[int, BookLevel] = {}
        self.sessao = Sessao()
        self._candles_fechados: list[Candle] = []
        self._candle_atual: _CandleEmFormacao | None = None

        barramento.assinar(Trade, self._ao_trade)
        barramento.assinar(BookDelta, self._ao_delta)
        barramento.assinar(BookSnapshot, self._ao_snapshot)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return
        self.ultimo_trade = trade
        self.sessao.registrar_trade(trade.price, trade.qty)
        self._atualizar_candle(trade)

    def _ao_delta(self, delta: BookDelta) -> None:
        if delta.symbol != self._symbol:
            return
        lado = self._bids if delta.side is Side.BUY else self._asks
        if delta.action is BookAction.DELETE:
            lado.pop(delta.price, None)
        else:
            lado[delta.price] = BookLevel(price=delta.price, qty=delta.qty, n_orders=1)

    def _ao_snapshot(self, snapshot: BookSnapshot) -> None:
        if snapshot.symbol != self._symbol:
            return
        self._bids = {nivel.price: nivel for nivel in snapshot.bids}
        self._asks = {nivel.price: nivel for nivel in snapshot.asks}

    def book_atual(self, timestamp_ns: int) -> BookSnapshot:
        bids = tuple(sorted(self._bids.values(), key=lambda n: n.price, reverse=True))
        asks = tuple(sorted(self._asks.values(), key=lambda n: n.price))
        return BookSnapshot(
            timestamp_ns=timestamp_ns, symbol=self._symbol, bids=bids, asks=asks
        )

    def _atualizar_candle(self, trade: Trade) -> None:
        inicio_bucket = (trade.timestamp_ns // self._timeframe_ns) * self._timeframe_ns
        candle = self._candle_atual
        if candle is None or candle.timestamp_inicio_ns != inicio_bucket:
            if candle is not None:
                self._candles_fechados.append(candle.congelar())
            candle = _CandleEmFormacao(
                timestamp_inicio_ns=inicio_bucket,
                open=trade.price,
                high=trade.price,
                low=trade.price,
                close=trade.price,
            )
            self._candle_atual = candle
        candle.high = max(candle.high, trade.price)
        candle.low = min(candle.low, trade.price)
        candle.close = trade.price
        candle.volume += trade.qty
        if trade.side_agressor.name == "BUY":
            candle.delta += trade.qty
        elif trade.side_agressor.name == "SELL":
            candle.delta -= trade.qty

    @property
    def candle_atual(self) -> Candle | None:
        if self._candle_atual is None:
            return None
        return self._candle_atual.congelar()

    @property
    def candles_fechados(self) -> tuple[Candle, ...]:
        return tuple(self._candles_fechados)
