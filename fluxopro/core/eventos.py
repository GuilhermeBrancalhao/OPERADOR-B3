"""Tipos de domínio imutáveis do núcleo de fluxo.

Preços trafegam sempre como `int` de ticks (nunca `float`) para que soma,
comparação e chave de dicionário sejam exatas — sem os erros de
arredondamento binário que `float` introduz em aritmética monetária.
`PriceGrid` é a única fronteira que converte entre o preço "humano" (float,
ex.: 5000.5) e o inteiro de ticks usado internamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique


@unique
class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


@unique
class AgressorSide(Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


@unique
class BookAction(Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class PriceGrid:
    """Converte preço float <-> inteiro de ticks para um instrumento.

    `to_ticks` recusa preços que não caem exatamente na grade (tolerância de
    1e-6 para absorver erro de ponto flutuante da divisão), evitando que um
    preço mal alinhado vire silenciosamente um tick errado.
    """

    tick_size: float
    decimals: int

    def to_ticks(self, price: float) -> int:
        razao = price / self.tick_size
        ticks = round(razao)
        if abs(razao - ticks) > 1e-6:
            raise ValueError(
                f"preco {price} nao esta alinhado ao tick_size {self.tick_size}"
            )
        return ticks

    def to_price(self, ticks: int) -> float:
        return round(ticks * self.tick_size, self.decimals)


WDO_GRID = PriceGrid(tick_size=0.5, decimals=1)
WIN_GRID = PriceGrid(tick_size=5.0, decimals=0)


@dataclass(frozen=True, slots=True)
class Trade:
    timestamp_ns: int
    symbol: str
    price: int
    qty: int
    side_agressor: AgressorSide
    trade_id: str
    buyer_broker: str = ""
    seller_broker: str = ""


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: int
    qty: int
    n_orders: int


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    timestamp_ns: int
    symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]


@dataclass(frozen=True, slots=True)
class BookDelta:
    timestamp_ns: int
    symbol: str
    side: Side
    action: BookAction
    price: int
    qty: int
    position: int


@dataclass(frozen=True, slots=True)
class Candle:
    """OHLCV do período, com o delta líquido e o volume sem agressor conhecido.

    `volume` conta TODO trade do período; `delta` só soma BUY e subtrai SELL.
    Sem `volume_nao_atribuido`, trades `AgressorSide.UNKNOWN` (leilão de
    abertura/fechamento, e o RLP que anonimiza parte do volume de WDO/WIN na
    B3) entrariam no volume e sumiriam do delta em silêncio — quem lesse o
    candle não teria como saber que parte do volume não foi atribuída a lado
    nenhum. Com o campo, vale sempre:

        volume == volume_comprador + volume_vendedor + volume_nao_atribuido

    e `delta == volume_comprador - volume_vendedor` continua sendo o líquido
    só do volume atribuído.

    Default 0 para não quebrar quem constrói `Candle` sem o campo (o valor
    correto quando não há trade anônimo é justamente zero).
    """

    timestamp_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int
    delta: int
    volume_nao_atribuido: int = 0
