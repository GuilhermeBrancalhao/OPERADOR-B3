"""Candles OHLCV por timeframe fixo, para uso fora do barramento.

Mesma regra de bucketing de `fluxopro/core/estado_mercado.py::_atualizar_candle`
(um candle por janela de `timeframe_ns`), com duas diferenças deliberadas:

1. Alimentado por chamada direta (`registrar`), nunca por assinatura de
   barramento — um painel de UI nunca assina o barramento (invariante do
   projeto); esta classe existe para poder viver dentro de um painel,
   alimentada pelos mesmos negócios já entregues via snapshot/retrato.
2. Retenção **limitada** por `maxlen_fechados`. `EstadoMercado._candles_fechados`
   é uma `list` sem teto — o defeito de retenção que este projeto já pagou
   caro em oito arquivos (ver docstring de `fluxopro/gravacao/gravador.py`).
   Esta classe não repete: candles fechados vivem num `deque(maxlen=...)`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from fluxopro.core.eventos import AgressorSide, Candle

__all__ = ["CandleTemporal", "ConfigCandleTemporal"]

NS_POR_MINUTO = 60_000_000_000


@dataclass(frozen=True, slots=True)
class ConfigCandleTemporal:
    timeframe_ns: int = 15 * NS_POR_MINUTO
    maxlen_fechados: int = 200


class _CandleEmFormacao:
    __slots__ = (
        "timestamp_inicio_ns",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "delta",
        "volume_nao_atribuido",
    )

    def __init__(self, timestamp_inicio_ns: int, preco: int) -> None:
        self.timestamp_inicio_ns = timestamp_inicio_ns
        self.open = preco
        self.high = preco
        self.low = preco
        self.close = preco
        self.volume = 0
        self.delta = 0
        self.volume_nao_atribuido = 0

    def congelar(self) -> Candle:
        return Candle(
            timestamp_ns=self.timestamp_inicio_ns,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            delta=self.delta,
            volume_nao_atribuido=self.volume_nao_atribuido,
        )


class CandleTemporal:
    """Agregador puro de candles por tempo. Ver docstring do módulo."""

    def __init__(self, config: ConfigCandleTemporal | None = None) -> None:
        self._config = config or ConfigCandleTemporal()
        self._fechados: deque[Candle] = deque(maxlen=self._config.maxlen_fechados)
        self._atual: _CandleEmFormacao | None = None

    def registrar(
        self,
        timestamp_ns: int,
        preco: int,
        qty: int = 0,
        agressor: AgressorSide = AgressorSide.UNKNOWN,
    ) -> None:
        inicio_bucket = (timestamp_ns // self._config.timeframe_ns) * self._config.timeframe_ns
        candle = self._atual
        if candle is None or candle.timestamp_inicio_ns != inicio_bucket:
            if candle is not None:
                self._fechados.append(candle.congelar())
            candle = _CandleEmFormacao(inicio_bucket, preco)
            self._atual = candle

        candle.high = max(candle.high, preco)
        candle.low = min(candle.low, preco)
        candle.close = preco
        candle.volume += qty
        if agressor is AgressorSide.BUY:
            candle.delta += qty
        elif agressor is AgressorSide.SELL:
            candle.delta -= qty
        else:
            candle.volume_nao_atribuido += qty

    @property
    def candle_atual(self) -> Candle | None:
        if self._atual is None:
            return None
        return self._atual.congelar()

    @property
    def candles_fechados(self) -> tuple[Candle, ...]:
        return tuple(self._fechados)
