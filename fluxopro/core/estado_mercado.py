"""Estado corrente do mercado, reconstruído a partir dos eventos publicados.

Uma instância de `EstadoMercado` acompanha um único símbolo (quem precisa de
vários símbolos instancia um `EstadoMercado` por symbol e assina todos no
mesmo `Barramento`). Mantém: último trade, book (via deltas incrementais ou
snapshots completos), candles OHLCV+delta por timeframe e a sessão
(high/low/vwap acumulado).

## Ciclo de vida de sessão

`Sessao.high/low/vwap` são, por definição, "desde o início da sessão" — mas
nada aqui sabia dizer quando uma sessão termina, então eles acumulavam para
sempre (dia 2 lia números que incluíam o dia 1). `EstadoMercado.iniciar_nova_sessao`
resolve isso.

**Política escolhida: virada EXPLÍCITA pelo chamador**, não detecção
automática por data. Motivo: este módulo só vê `timestamp_ns` de negociação,
não o calendário de pregão do instrumento. O pregão do WDO/WIN na B3 não
vira à meia-noite UTC — tem sessão regular, after-market, feriado e
vencimento mensal — então qualquer heurística de "mudou o dia" embutida
aqui adivinharia errado em algum desses casos. Quem alimenta os eventos
(adaptador de dados ao vivo, ou o player de replay) é quem sabe, de fato,
quando a sessão anterior fechou — então ele é quem deve chamar
`iniciar_nova_sessao()` no instante certo.

Para quem ainda assim quiser uma detecção automática por data (aceitando a
simplificação), `sessao_mudou()` neste módulo compara dois timestamps com um
corte de dia configurável (não cravado em meia-noite UTC) — mas quem decide
*quando* chamar `iniciar_nova_sessao()` continua sendo o chamador, nunca
este módulo sozinho.
"""

from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Candle,
    Side,
    Trade,
)

NS_POR_MINUTO = 60_000_000_000
NS_POR_DIA = 86_400_000_000_000


def sessao_mudou(
    timestamp_anterior_ns: int | None,
    timestamp_atual_ns: int,
    corte_ns_utc: int = 0,
) -> bool:
    """Helper OPCIONAL de detecção automática de virada de sessão por data.

    Compara o "dia de pregão" de dois timestamps (ns desde epoch, UTC),
    deslocando ambos por `corte_ns_utc` antes de dividir por dia — isso
    permite configurar onde cai a fronteira do dia em vez de assumir
    meia-noite UTC (que não corresponde ao fechamento real do WDO/WIN).
    Ex.: se o after-market fecha às 18:00 (BRT) / 21:00 UTC, passe
    `corte_ns_utc = 21 * 3_600_000_000_000` para que a virada seja
    detectada logo após o fechamento, não à meia-noite.

    `timestamp_anterior_ns=None` (primeiro evento visto) devolve `False` —
    não há sessão anterior para virar.

    Isto é só o predicado "virou?"; quem chama decide o que fazer com a
    resposta (tipicamente: `if sessao_mudou(...): estado.iniciar_nova_sessao()`).
    Continua sendo uma simplificação — não trata leilão, feriado nem
    vencimento — então prefira o sinal explícito do adaptador de dados
    sempre que ele estiver disponível.
    """
    if timestamp_anterior_ns is None:
        return False
    dia_anterior = (timestamp_anterior_ns - corte_ns_utc) // NS_POR_DIA
    dia_atual = (timestamp_atual_ns - corte_ns_utc) // NS_POR_DIA
    return dia_atual != dia_anterior


@dataclass(slots=True)
class _CandleEmFormacao:
    timestamp_inicio_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int = 0
    delta: int = 0
    volume_nao_atribuido: int = 0

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


@dataclass(slots=True)
class Sessao:
    """High/low/volume/vwap acumulados desde o início da sessão corrente.

    Volume é separado por agressor: `volume_comprador`, `volume_vendedor` e
    `volume_nao_atribuido` (trades com `AgressorSide.UNKNOWN` — leilão de
    abertura/fechamento, RLP anonimizando parte do volume de WDO/WIN na B3).
    `volume_total` é sempre a soma dos três, nunca um contador à parte: antes,
    todo trade contava no volume mas só BUY/SELL contavam em algum lado,
    então `volume_total != comprador + vendedor` silenciosamente sempre que
    havia UNKNOWN. Agora não há como isso acontecer — o volume "some" do
    delta líquido mas nunca do total, e fica visível em qual balde caiu.

    Não decide sozinha quando a sessão vira; `resetar()` é chamado por
    `EstadoMercado.iniciar_nova_sessao` (ver docstring do módulo para a
    política de virada).
    """

    high: int | None = None
    low: int | None = None
    volume_comprador: int = 0
    volume_vendedor: int = 0
    volume_nao_atribuido: int = 0
    soma_preco_qty: int = 0

    def registrar_trade(self, preco: int, qty: int, agressor: AgressorSide) -> None:
        self.high = preco if self.high is None else max(self.high, preco)
        self.low = preco if self.low is None else min(self.low, preco)
        if agressor is AgressorSide.BUY:
            self.volume_comprador += qty
        elif agressor is AgressorSide.SELL:
            self.volume_vendedor += qty
        else:
            self.volume_nao_atribuido += qty
        self.soma_preco_qty += preco * qty

    @property
    def volume_total(self) -> int:
        return self.volume_comprador + self.volume_vendedor + self.volume_nao_atribuido

    @property
    def vwap(self) -> float:
        if self.volume_total == 0:
            return 0.0
        return self.soma_preco_qty / self.volume_total

    def resetar(self) -> None:
        """Zera todo acumulador da sessão (verificável: os 6 campos voltam
        ao estado inicial). Prefira `EstadoMercado.iniciar_nova_sessao()` —
        ele existe para orquestrar o reset do resto do estado junto."""
        self.high = None
        self.low = None
        self.volume_comprador = 0
        self.volume_vendedor = 0
        self.volume_nao_atribuido = 0
        self.soma_preco_qty = 0


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
        self.sessao.registrar_trade(trade.price, trade.qty, trade.side_agressor)
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
        if trade.side_agressor is AgressorSide.BUY:
            candle.delta += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            candle.delta -= trade.qty
        else:
            # UNKNOWN entra no volume mas nao no delta; sem este contador a
            # diferenca ficaria invisivel para quem le o candle.
            candle.volume_nao_atribuido += trade.qty

    @property
    def candle_atual(self) -> Candle | None:
        if self._candle_atual is None:
            return None
        return self._candle_atual.congelar()

    @property
    def candles_fechados(self) -> tuple[Candle, ...]:
        return tuple(self._candles_fechados)

    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Fecha a sessão corrente e zera todo acumulador *de sessão*.

        Ver docstring do módulo para a política de virada (explícita pelo
        chamador). `timestamp_ns` é opcional e não influencia o reset em si
        — o reset é sempre completo, incondicional; o parâmetro só existe
        para quem quiser logar/observar o instante em que a virada ocorreu.

        O que reseta: `sessao` (high/low/volume/vwap, os três baldes de
        agressor) e o candle em formação (`candle_atual` volta a `None`,
        igual a `VolumeProfilePorPeriodo.nova_sessao()` faz com o período
        corrente) — o próximo trade abre um candle novo em vez de esticar
        um candle que atravessa a virada.

        O que **não** reseta, de propósito: `candles_fechados` (histórico
        já fechado — mesmo padrão de `VolumeProfilePorPeriodo.periodos_fechados`,
        que também sobrevive à virada) e o book (`_bids`/`_asks`)/`ultimo_trade`
        — reconstrução de book, livro cruzado e estado "ainda não
        sincronizado" são defeitos distintos (achados 4.1/4.3 da auditoria),
        fora do escopo deste conserto.
        """
        self.sessao.resetar()
        self._candle_atual = None
