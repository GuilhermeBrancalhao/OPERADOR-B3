"""Perfil de player por corretora — base do "Ranking de Corretoras/Players" da barra.

Acumula, por `broker`, agressividade, direção líquida, tamanho médio de clip,
horário de atuação e persistência (em quantos períodos distintos apareceu).
Tudo incremental: nenhum método varre o histórico completo por trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fluxopro.core.eventos import Trade

NS_POR_HORA = 3_600_000_000_000


@dataclass(slots=True)
class _AcumuladorBroker:
    n_trades_agressor: int = 0
    n_trades_passivo: int = 0
    volume_comprado: int = 0
    volume_vendido: int = 0
    soma_qty: int = 0
    n_clips: int = 0
    periodos: set[int] = field(default_factory=set)

    @property
    def volume_total(self) -> int:
        return self.volume_comprado + self.volume_vendido

    @property
    def saldo_liquido(self) -> int:
        return self.volume_comprado - self.volume_vendido

    @property
    def agressividade(self) -> float:
        total = self.n_trades_agressor + self.n_trades_passivo
        return 0.0 if total == 0 else self.n_trades_agressor / total

    @property
    def tamanho_medio_clip(self) -> float:
        return 0.0 if self.n_clips == 0 else self.soma_qty / self.n_clips

    @property
    def persistencia(self) -> int:
        return len(self.periodos)


@dataclass(frozen=True, slots=True)
class SnapshotBroker:
    broker: str
    volume_total: int
    saldo_liquido: int
    agressividade: float
    tamanho_medio_clip: float
    persistencia: int


class PerfilPlayer:
    """Agrega comportamento por corretora a partir de `Trade.buyer_broker`/`seller_broker`.

    `janela_periodo_ns` define o "período" usado para persistência (padrão 1h):
    um broker que aparece em N períodos distintos é mais persistente que um
    que concentrou tudo num único período curto.
    """

    def __init__(self, symbol: str, janela_periodo_ns: int = NS_POR_HORA) -> None:
        self._symbol = symbol
        self._janela_periodo_ns = janela_periodo_ns
        self._brokers: dict[str, _AcumuladorBroker] = {}

    def _acumulador(self, broker: str) -> _AcumuladorBroker:
        acc = self._brokers.get(broker)
        if acc is None:
            acc = _AcumuladorBroker()
            self._brokers[broker] = acc
        return acc

    def ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return
        periodo = trade.timestamp_ns // self._janela_periodo_ns
        lado_comprador_agrediu = trade.side_agressor.name == "BUY"
        lado_vendedor_agrediu = trade.side_agressor.name == "SELL"

        if trade.buyer_broker:
            acc = self._acumulador(trade.buyer_broker)
            acc.volume_comprado += trade.qty
            acc.soma_qty += trade.qty
            acc.n_clips += 1
            acc.periodos.add(periodo)
            if lado_comprador_agrediu:
                acc.n_trades_agressor += 1
            elif lado_vendedor_agrediu:
                acc.n_trades_passivo += 1

        if trade.seller_broker:
            acc = self._acumulador(trade.seller_broker)
            acc.volume_vendido += trade.qty
            acc.soma_qty += trade.qty
            acc.n_clips += 1
            acc.periodos.add(periodo)
            if lado_vendedor_agrediu:
                acc.n_trades_agressor += 1
            elif lado_comprador_agrediu:
                acc.n_trades_passivo += 1

    def snapshot(self, broker: str) -> SnapshotBroker | None:
        acc = self._brokers.get(broker)
        if acc is None:
            return None
        return SnapshotBroker(
            broker=broker,
            volume_total=acc.volume_total,
            saldo_liquido=acc.saldo_liquido,
            agressividade=acc.agressividade,
            tamanho_medio_clip=acc.tamanho_medio_clip,
            persistencia=acc.persistencia,
        )

    def ranking_por_volume(self, top_n: int = 10) -> tuple[SnapshotBroker, ...]:
        snaps = [self.snapshot(b) for b in self._brokers]
        snaps = [s for s in snaps if s is not None]
        snaps.sort(key=lambda s: s.volume_total, reverse=True)
        return tuple(snaps[:top_n])
