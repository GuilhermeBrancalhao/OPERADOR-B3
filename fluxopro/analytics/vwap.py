"""VWAP — preço médio ponderado por volume, de sessão e ancorado.

Conceito de leitura de fluxo: VWAP é o preço "justo" do período, ponderado
pelo volume negociado em cada preço — diferente de uma média simples, um
preço com muito volume pesa mais que um preço só tocado de passagem. É
referência de institucionais (comparar execução própria contra o VWAP do
dia) e de suporte/resistência dinâmico.

**VWAP ancorado** começa a acumular a partir de um ponto de referência
arbitrário (não o início do pregão) — ex.: a partir de uma notícia, de uma
máxima/mínima relevante, ou de um horário específico. Neste módulo, ancorar
é `Trade`-driven: `ancorar(nome)` zera um acumulador que passa a somar a
partir do próximo trade recebido (uso ao vivo/replay); para VWAP ancorado
retroativo num range de trades já conhecido, use o método estático
`calcular_vwap_e_bandas`, que roda o mesmo acumulador sobre uma lista
qualquer de trades já filtrada.

**Bandas de desvio padrão** (1σ, 2σ) usam a variância ponderada por volume:
Var = E[preço²] − E[preço]², com E[X] = Σ(qty·X) / Σ(qty). As bandas marcam
até onde o preço se afastou "tipicamente" do VWAP — útil para mean-reversion
(preço muito longe da banda tende a puxar de volta) e para medir força de
tendência (preço colado na banda superior = tendência forte).

Tudo incremental: cada acumulador guarda só três somas (Σqty, Σpreço·qty,
Σpreço²·qty) — O(1) por trade, independente de quantos trades já passaram.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import Trade


@dataclass(frozen=True, slots=True)
class ConfigVWAP:
    multiplicador_banda_1: float = 1.0
    """Múltiplo de desvio padrão da banda interna (padrão de mercado: 1σ)."""

    multiplicador_banda_2: float = 2.0
    """Múltiplo de desvio padrão da banda externa (padrão de mercado: 2σ)."""


@dataclass(slots=True)
class _AcumuladorVWAP:
    soma_qty: int = 0
    soma_preco_qty: float = 0.0
    soma_preco2_qty: float = 0.0

    def registrar(self, preco: int, qty: int) -> None:
        self.soma_qty += qty
        self.soma_preco_qty += preco * qty
        self.soma_preco2_qty += (preco**2) * qty

    @property
    def vwap(self) -> float:
        return self.soma_preco_qty / self.soma_qty if self.soma_qty else 0.0

    @property
    def variancia(self) -> float:
        if self.soma_qty == 0:
            return 0.0
        media_preco2 = self.soma_preco2_qty / self.soma_qty
        media_preco = self.vwap
        # guarda contra ruído de ponto flutuante deixando a variância < 0
        # perto de zero (ex.: todos os trades no mesmo preço)
        return max(media_preco2 - media_preco**2, 0.0)

    @property
    def desvio_padrao(self) -> float:
        return math.sqrt(self.variancia)


def _bandas(vwap: float, desvio: float, config: ConfigVWAP) -> tuple[float, float, float, float, float]:
    return (
        vwap - config.multiplicador_banda_2 * desvio,
        vwap - config.multiplicador_banda_1 * desvio,
        vwap,
        vwap + config.multiplicador_banda_1 * desvio,
        vwap + config.multiplicador_banda_2 * desvio,
    )


class VWAP:
    """Assina o `Barramento` e mantém VWAP de sessão + VWAPs ancorados."""

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        config: ConfigVWAP | None = None,
    ) -> None:
        self._symbol = symbol
        self.config = config or ConfigVWAP()
        self._sessao = _AcumuladorVWAP()
        self._ancoras: dict[str, _AcumuladorVWAP] = {}

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return
        self._sessao.registrar(trade.price, trade.qty)
        for acumulador in self._ancoras.values():
            acumulador.registrar(trade.price, trade.qty)

    def ancorar(self, nome: str) -> None:
        """Cria (ou reinicia) uma âncora `nome`, zerada a partir do próximo
        trade recebido — chame antes do instante em que quer ancorar."""
        self._ancoras[nome] = _AcumuladorVWAP()

    def remover_ancora(self, nome: str) -> None:
        self._ancoras.pop(nome, None)

    @property
    def nomes_ancoras(self) -> tuple[str, ...]:
        return tuple(self._ancoras.keys())

    def vwap_sessao(self) -> float:
        return self._sessao.vwap

    def bandas_sessao(self) -> tuple[float, float, float, float, float]:
        """Retorna (banda_inf_2, banda_inf_1, vwap, banda_sup_1, banda_sup_2)."""
        return _bandas(self._sessao.vwap, self._sessao.desvio_padrao, self.config)

    def vwap_ancorado(self, nome: str) -> float | None:
        acumulador = self._ancoras.get(nome)
        return acumulador.vwap if acumulador is not None else None

    def bandas_ancorado(self, nome: str) -> tuple[float, float, float, float, float] | None:
        acumulador = self._ancoras.get(nome)
        if acumulador is None:
            return None
        return _bandas(acumulador.vwap, acumulador.desvio_padrao, self.config)

    @staticmethod
    def calcular_vwap_e_bandas(
        trades: Iterable[Trade], config: ConfigVWAP | None = None
    ) -> tuple[float, float, float, float, float]:
        """Constrói um VWAP a partir de um range de trades já filtrado (ex.:
        trades desde um timestamp arbitrário) — uso em lote/não incremental,
        mesmo acumulador usado ao vivo aplicado de uma vez a um conjunto fixo.
        """
        acumulador = _AcumuladorVWAP()
        for trade in trades:
            acumulador.registrar(trade.price, trade.qty)
        return _bandas(acumulador.vwap, acumulador.desvio_padrao, config or ConfigVWAP())
