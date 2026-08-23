"""Tipos de domínio imutáveis do núcleo de fluxo.

Preços trafegam sempre como `int` de ticks (nunca `float`) para que soma,
comparação e chave de dicionário sejam exatas — sem os erros de
arredondamento binário que `float` introduz em aritmética monetária.
`PriceGrid` é a única fronteira que converte entre o preço "humano" (float,
ex.: 5000.5) e o inteiro de ticks usado internamente.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum, unique


@unique
class Side(StrEnum):
    """Lado do LIVRO (quem está parado na fila), não lado da agressão.

    ## Por que `StrEnum` e não `Enum` — medido, não estilo

    `Side` é o enum mais hasheado do projeto: um censo de `Enum.__hash__` no
    pipeline completo (`InferidorMBP` + `LivroMBO` + detectores de livro)
    atribuiu **72% de todos os hashes de enum** a este tipo, ~34 por evento de
    mercado. Ele entra como elemento de chave em `_qty_por_nivel`
    (`(side, price)`), nas chaves do `_MapaProcedencia` dos detectores e nos
    `set` de nível de `ao_snapshot` — e hashear uma tupla hasheia cada
    elemento.

    `Enum.__hash__` é um método escrito em Python (`hash(self._name_)`): cada
    busca em dicionário com chave `Side` paga uma chamada de interpretador.
    Na MRO de `StrEnum` (`Side -> StrEnum -> str -> ReprEnum -> Enum`),
    `str.__hash__` vem ANTES de `Enum.__hash__`, então o hash passa a ser
    nível C — e `str` ainda cacheia o próprio hash, de modo que da segunda vez
    em diante é uma leitura de campo. É a mesma correção que a onda 7 fez à
    mão em `inferencia_mbp._cod_lado`, aqui generalizada para todos os pontos
    de uma vez, sem tocar em nenhum call site.

    ## Por que `StrEnum` e não `IntEnum`

    `IntEnum` hasheia igualmente rápido (medido: indistinguível), mas exigiria
    trocar os valores `"BUY"`/`"SELL"` por inteiros — e `.value` é o que vai
    para o DISCO em `gravacao/formato.py`, lido de volta por `Side(linha[...])`.
    Isso quebraria o formato gravado e toda gravação já existente. Com
    `StrEnum` o `.value` continua sendo exatamente `"BUY"`/`"SELL"`: o arquivo
    em disco sai byte a byte igual e o round-trip não muda.

    ## O que se paga por isto

    Um membro passa a ser um `str`: `Side.BUY == "BUY"` é verdadeiro e
    `str(Side.BUY)` vira `"BUY"` (era `"Side.BUY"`). O vazamento é para `str`,
    não para `int` — um `Side` não pode mais ser confundido com um preço em
    ticks, uma quantidade ou um índice, que é onde um vazamento silencioso
    doeria neste projeto. O `repr` (`<Side.BUY: 'BUY'>`) não muda.
    """

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
