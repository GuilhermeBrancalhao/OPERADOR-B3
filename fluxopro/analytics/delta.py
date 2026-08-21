"""Cumulative Delta — agressão líquida acumulada ao longo do tempo.

Conceito de leitura de fluxo: delta é volume_comprador - volume_vendedor
(por agressor) num intervalo. Delta *acumulado* soma isso continuamente
desde o início da sessão — é o "placar" de quem está vencendo o cabo de
guerra da agressão. A leitura clássica é comparar a série de delta acumulado
com a série de preço:

- Preço sobe e delta acumulado sobe junto: alta confirmada por agressão real.
- Preço sobe mas delta acumulado cai (ou não acompanha): **divergência** —
  o preço está subindo "sem lastro" de agressão compradora, sinal clássico
  de exaustão de tendência.

Dentro de cada candle também guardamos o delta *máximo* e *mínimo* atingidos
durante sua formação (delta high/delta low) — não só o delta final. Um
candle pode fechar com delta levemente positivo mas ter chegado a -400 no
meio do caminho: isso é uma reversão intra-candle que o delta final sozinho
esconde.

Tudo incremental: cada trade atualiza o delta da sessão e do candle corrente
em O(1); a checagem de divergência olha só os últimos `janela_divergencia`
candles já fechados (não o histórico inteiro).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade

NS_POR_MINUTO = 60_000_000_000


@dataclass(frozen=True, slots=True)
class ConfigDelta:
    timeframe_ns: int = NS_POR_MINUTO
    """Tamanho do bucket de candle usado para as séries de delta por candle."""

    janela_divergencia: int = 5
    """Quantos candles fechados entram na checagem de delta divergente vs. preço."""

    limiar_variacao_preco: int = 0
    """Variação mínima de preço (em ticks) dentro da janela para considerar a
    checagem de divergência válida (evita disparo em ruído de preço parado)."""

    limiar_variacao_delta: int = 0
    """Variação mínima de delta acumulado (em contratos) dentro da janela para
    considerar a checagem de divergência válida."""


@dataclass(slots=True)
class CandleDelta:
    """Delta de um candle fechado: final, extremos intra-candle e o delta
    acumulado da sessão no instante em que o candle fechou."""

    timestamp_inicio_ns: int
    preco_fechamento: int
    delta: int
    delta_maximo: int
    delta_minimo: int
    delta_acumulado_no_fechamento: int


@dataclass(slots=True)
class _CandleDeltaEmFormacao:
    timestamp_inicio_ns: int
    delta: int = 0
    delta_maximo: int = 0
    delta_minimo: int = 0
    preco_fechamento: int = 0

    def congelar(self, delta_acumulado_sessao: int) -> CandleDelta:
        return CandleDelta(
            timestamp_inicio_ns=self.timestamp_inicio_ns,
            preco_fechamento=self.preco_fechamento,
            delta=self.delta,
            delta_maximo=self.delta_maximo,
            delta_minimo=self.delta_minimo,
            delta_acumulado_no_fechamento=delta_acumulado_sessao,
        )


class CumulativeDelta:
    """Assina o `Barramento` e mantém delta acumulado de sessão + por candle."""

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        config: ConfigDelta | None = None,
    ) -> None:
        self._symbol = symbol
        self.config = config or ConfigDelta()
        self.delta_sessao: int = 0
        self._candle_atual: _CandleDeltaEmFormacao | None = None
        self._historico: list[CandleDelta] = []

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return

        bucket = (trade.timestamp_ns // self.config.timeframe_ns) * self.config.timeframe_ns
        candle = self._candle_atual
        if candle is None or candle.timestamp_inicio_ns != bucket:
            if candle is not None:
                self._historico.append(candle.congelar(self.delta_sessao))
            candle = _CandleDeltaEmFormacao(timestamp_inicio_ns=bucket)
            self._candle_atual = candle

        if trade.side_agressor is AgressorSide.BUY:
            incremento = trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            incremento = -trade.qty
        else:
            incremento = 0

        self.delta_sessao += incremento
        candle.delta += incremento
        candle.delta_maximo = max(candle.delta_maximo, candle.delta)
        candle.delta_minimo = min(candle.delta_minimo, candle.delta)
        candle.preco_fechamento = trade.price

    @property
    def candle_atual(self) -> CandleDelta | None:
        if self._candle_atual is None:
            return None
        return self._candle_atual.congelar(self.delta_sessao)

    @property
    def historico(self) -> tuple[CandleDelta, ...]:
        return tuple(self._historico)

    def delta_divergente(self) -> bool:
        """Compara início e fim da janela de candles fechados: preço fez um
        movimento numa direção enquanto o delta acumulado moveu na direção
        oposta (ou ficou estagnado abaixo do limiar configurado).
        """
        janela = self.config.janela_divergencia
        if len(self._historico) < janela:
            return False

        recorte = self._historico[-janela:]
        inicio, fim = recorte[0], recorte[-1]

        variacao_preco = fim.preco_fechamento - inicio.preco_fechamento
        variacao_delta = fim.delta_acumulado_no_fechamento - inicio.delta_acumulado_no_fechamento

        if abs(variacao_preco) < self.config.limiar_variacao_preco:
            return False
        if abs(variacao_delta) < self.config.limiar_variacao_delta:
            return False

        return (variacao_preco > 0 and variacao_delta < 0) or (
            variacao_preco < 0 and variacao_delta > 0
        )
