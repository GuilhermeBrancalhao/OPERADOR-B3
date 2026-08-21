"""Gerador sintético de fluxo de WDO, determinístico por seed.

Usa um `random.Random(seed)` próprio (nunca o módulo global `random`) para
que a mesma seed produza sempre a mesma sequência de eventos, em qualquer
processo. Comportamento buscado: o book se move com o preço, agressões
consomem a liquidez do topo, players grandes aparecem com clipes fora do
padrão, e ocasionalmente muita agressão não desloca o preço (absorção).
"""

from __future__ import annotations

import random

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.dados.adaptador import AdaptadorDados

_PROFUNDIDADE_PADRAO = 5
_CLIP_GRANDE_MULTIPLICADOR = 8
_PROB_PLAYER_GRANDE = 0.03
_PROB_ABSORCAO = 0.08
_QTY_TOPO_MIN = 20
_QTY_TOPO_MAX = 80


class SimuladorWDO(AdaptadorDados):
    def __init__(
        self,
        barramento: Barramento,
        seed: int,
        volatilidade: float = 1.0,
        taxa_eventos_s: float = 5.0,
        preco_inicial: float = 5000.0,
        symbol: str = "WDOFUT",
        n_eventos: int = 1000,
        tick_size: float = 0.5,
    ) -> None:
        super().__init__(barramento)
        self._rng = random.Random(seed)
        self._volatilidade = volatilidade
        self._taxa_eventos_s = taxa_eventos_s
        self._symbol = symbol
        self._n_eventos = n_eventos
        self._preco_ticks = round(preco_inicial / tick_size)
        self._timestamp_ns = 0
        self._trade_seq = 0
        self._qty_topo_bid = 50
        self._qty_topo_ask = 50
        self._parar = False

    def iniciar(self) -> None:
        self._parar = False
        for _ in range(self._n_eventos):
            if self._parar:
                break
            self._passo()

    def parar(self) -> None:
        self._parar = True

    def _passo(self) -> None:
        intervalo_s = self._rng.expovariate(self._taxa_eventos_s)
        self._timestamp_ns += max(1, int(intervalo_s * 1e9))

        absorcao = self._rng.random() < _PROB_ABSORCAO
        player_grande = self._rng.random() < _PROB_PLAYER_GRANDE
        agressor = AgressorSide.BUY if self._rng.random() < 0.5 else AgressorSide.SELL

        qty = self._rng.randint(1, 10)
        if player_grande:
            qty *= _CLIP_GRANDE_MULTIPLICADOR

        self._trade_seq += 1
        trade = Trade(
            timestamp_ns=self._timestamp_ns,
            symbol=self._symbol,
            price=self._preco_ticks,
            qty=qty,
            side_agressor=agressor,
            trade_id=f"SIM-{self._trade_seq}",
        )
        self._barramento.publicar(trade)

        if agressor is AgressorSide.BUY:
            self._qty_topo_ask -= qty
        else:
            self._qty_topo_bid -= qty

        topo_zerou = (
            agressor is AgressorSide.BUY and self._qty_topo_ask <= 0
        ) or (agressor is AgressorSide.SELL and self._qty_topo_bid <= 0)
        desloca_preco = topo_zerou and not absorcao

        if desloca_preco:
            passo_ticks = max(1, round(abs(self._rng.gauss(0, self._volatilidade))))
            if agressor is AgressorSide.BUY:
                self._preco_ticks += passo_ticks
            else:
                self._preco_ticks -= passo_ticks
            self._qty_topo_bid = self._rng.randint(_QTY_TOPO_MIN, _QTY_TOPO_MAX)
            self._qty_topo_ask = self._rng.randint(_QTY_TOPO_MIN, _QTY_TOPO_MAX)
        else:
            if self._qty_topo_ask <= 0:
                self._qty_topo_ask = self._rng.randint(_QTY_TOPO_MIN, _QTY_TOPO_MAX)
            if self._qty_topo_bid <= 0:
                self._qty_topo_bid = self._rng.randint(_QTY_TOPO_MIN, _QTY_TOPO_MAX)

        self._publicar_book()

    def _publicar_book(self) -> None:
        bids = tuple(
            BookLevel(
                price=self._preco_ticks - 1 - nivel,
                qty=self._qty_topo_bid if nivel == 0 else self._rng.randint(10, 100),
                n_orders=self._rng.randint(1, 15),
            )
            for nivel in range(_PROFUNDIDADE_PADRAO)
        )
        asks = tuple(
            BookLevel(
                price=self._preco_ticks + 1 + nivel,
                qty=self._qty_topo_ask if nivel == 0 else self._rng.randint(10, 100),
                n_orders=self._rng.randint(1, 15),
            )
            for nivel in range(_PROFUNDIDADE_PADRAO)
        )
        self._barramento.publicar(
            BookSnapshot(
                timestamp_ns=self._timestamp_ns,
                symbol=self._symbol,
                bids=bids,
                asks=asks,
            )
        )
