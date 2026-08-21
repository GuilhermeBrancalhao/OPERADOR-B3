"""Ranking de Corretoras — quem está negociando o ativo.

Conceito de leitura de fluxo: cada `Trade` carrega a corretora do comprador
(`buyer_broker`) e do vendedor (`seller_broker`). Agregando isso por
corretora dá o equivalente ao "Ranking de Corretoras" do Profit Pro: volume
total, saldo líquido (comprou mais do que vendeu, ou o contrário), número de
negócios e preço médio praticado. É a base para responder "quem está
dominando o book hoje" — uma corretora com saldo líquido grande e crescente
é candidata a estar acumulando ou distribuindo posição.

Agregação incremental (O(1) por trade); janela de tempo opcional expira
trades antigos de uma deque, com o mesmo padrão de bucketing/expiração dos
outros módulos de analytics.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import Trade


@dataclass(frozen=True, slots=True)
class ConfigRankingCorretoras:
    janela_ns: int | None = None
    """Janela de tempo (ns) para a agregação. `None` = acumula sem expirar
    (ex.: a sessão inteira)."""


@dataclass(slots=True)
class EstatisticaCorretora:
    """Agregado de uma corretora nos dois lados (comprador e vendedor)."""

    volume_compra: int = 0
    volume_venda: int = 0
    n_negocios_compra: int = 0
    n_negocios_venda: int = 0
    soma_preco_qty_compra: int = 0
    soma_preco_qty_venda: int = 0

    @property
    def volume_total(self) -> int:
        return self.volume_compra + self.volume_venda

    @property
    def saldo_liquido(self) -> int:
        return self.volume_compra - self.volume_venda

    @property
    def n_negocios(self) -> int:
        return self.n_negocios_compra + self.n_negocios_venda

    @property
    def preco_medio_compra(self) -> float:
        return self.soma_preco_qty_compra / self.volume_compra if self.volume_compra else 0.0

    @property
    def preco_medio_venda(self) -> float:
        return self.soma_preco_qty_venda / self.volume_venda if self.volume_venda else 0.0

    @property
    def preco_medio(self) -> float:
        volume = self.volume_total
        if volume == 0:
            return 0.0
        return (self.soma_preco_qty_compra + self.soma_preco_qty_venda) / volume


class RankingCorretoras:
    """Assina o `Barramento` e agrega estatísticas por corretora."""

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        config: ConfigRankingCorretoras | None = None,
    ) -> None:
        self._symbol = symbol
        self.config = config or ConfigRankingCorretoras()
        self._estatisticas: dict[str, EstatisticaCorretora] = {}
        self._janela: deque[Trade] = deque()

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return

        if trade.buyer_broker:
            est = self._estatisticas.setdefault(trade.buyer_broker, EstatisticaCorretora())
            est.volume_compra += trade.qty
            est.n_negocios_compra += 1
            est.soma_preco_qty_compra += trade.price * trade.qty

        if trade.seller_broker:
            est = self._estatisticas.setdefault(trade.seller_broker, EstatisticaCorretora())
            est.volume_venda += trade.qty
            est.n_negocios_venda += 1
            est.soma_preco_qty_venda += trade.price * trade.qty

        if self.config.janela_ns is not None:
            self._janela.append(trade)
            self._expirar(trade.timestamp_ns)

    def _expirar(self, agora_ns: int) -> None:
        janela_ns = self.config.janela_ns
        assert janela_ns is not None
        while self._janela and agora_ns - self._janela[0].timestamp_ns > janela_ns:
            antigo = self._janela.popleft()
            if antigo.buyer_broker and antigo.buyer_broker in self._estatisticas:
                est = self._estatisticas[antigo.buyer_broker]
                est.volume_compra -= antigo.qty
                est.n_negocios_compra -= 1
                est.soma_preco_qty_compra -= antigo.price * antigo.qty
            if antigo.seller_broker and antigo.seller_broker in self._estatisticas:
                est = self._estatisticas[antigo.seller_broker]
                est.volume_venda -= antigo.qty
                est.n_negocios_venda -= 1
                est.soma_preco_qty_venda -= antigo.price * antigo.qty

    def estatistica(self, corretora: str) -> EstatisticaCorretora | None:
        return self._estatisticas.get(corretora)

    def ranking_por_volume(
        self, top_n: int | None = None
    ) -> list[tuple[str, EstatisticaCorretora]]:
        itens = sorted(
            self._estatisticas.items(), key=lambda kv: kv[1].volume_total, reverse=True
        )
        return itens[:top_n] if top_n is not None else itens

    def ranking_por_saldo(
        self, top_n: int | None = None
    ) -> list[tuple[str, EstatisticaCorretora]]:
        """Ordenado do saldo mais comprador para o mais vendedor. Para ver o
        lado vendedor no topo, leia a lista de trás para frente."""
        itens = sorted(
            self._estatisticas.items(), key=lambda kv: kv[1].saldo_liquido, reverse=True
        )
        return itens[:top_n] if top_n is not None else itens
