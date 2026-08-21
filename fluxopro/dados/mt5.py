"""Adaptador de dados ao vivo via terminal MetaTrader5.

Import do pacote `MetaTrader5` é preguiçoso e protegido: o módulo Python
deste arquivo importa e é testável em qualquer máquina (Linux/CI/sem MT5
instalado); o erro só aparece — com mensagem clara — quando `iniciar()` é
chamado de fato. Para teste, injete um módulo falso via `mt5_module=`.

Fronteira de concorrência: o pacote `MetaTrader5` não tem streaming nativo,
só polling (ver `pesquisa/fontes_de_dados.md`). Uma *thread de borda*
(`_thread_borda`) faz esse polling contra o terminal MT5 e só enfileira
objetos já traduzidos para os tipos de `fluxopro.core.eventos` — nunca
toca o barramento. A thread principal (dentro de `iniciar()`, que bloqueia
até `parar()`) drena a fila e publica no `Barramento`, respeitando a regra
do núcleo de que `publicar()` só é chamado de um único lugar serializado.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from types import ModuleType
from typing import Optional

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    PriceGrid,
    Side,
    Trade,
)
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha

_logger = logging.getLogger("fluxopro.dados.mt5")

# Limite de "atraso aceitável" entre um poll e o outro antes de considerar
# que pode ter havido perda de tick/book (a máquina travou, o terminal MT5
# travou, rede caiu etc.). Empírico, não documentado pela MetaQuotes.
_LIMIAR_GAP_S = 2.0

EventoBruto = Trade | BookSnapshot | BookDelta | FalhaCaptura


def _importar_mt5() -> ModuleType:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as erro:
        raise RuntimeError(
            "pacote 'MetaTrader5' nao esta instalado (pip install MetaTrader5). "
            "So funciona em Windows com o terminal MT5 instalado e logado. "
            "Use AdaptadorMT5(mt5_module=<mock>) para testar sem a dependencia real."
        ) from erro
    return mt5


class AdaptadorMT5(AdaptadorDados):
    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        price_grid: PriceGrid,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        intervalo_poll_s: float = 0.05,
        profundidade_maxima: int = 10,
        mt5_module: ModuleType | None = None,
    ) -> None:
        super().__init__(barramento)
        self._symbol = symbol
        self._grid = price_grid
        self._login = login
        self._password = password
        self._server = server
        self._intervalo_poll_s = intervalo_poll_s
        self._profundidade_maxima = profundidade_maxima
        self._mt5_injetado = mt5_module

        self._fila: "queue.Queue[EventoBruto]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._parar_evt = threading.Event()
        self._book_habilitado = False
        self._mt5: ModuleType | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        mt5 = self._mt5_injetado if self._mt5_injetado is not None else _importar_mt5()
        self._mt5 = mt5

        kwargs = {}
        if self._login is not None:
            kwargs["login"] = self._login
        if self._password is not None:
            kwargs["password"] = self._password
        if self._server is not None:
            kwargs["server"] = self._server
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"mt5.initialize() falhou: {mt5.last_error()}")

        if not mt5.symbol_select(self._symbol, True):
            mt5.shutdown()
            raise RuntimeError(
                f"mt5.symbol_select({self._symbol!r}) falhou: {mt5.last_error()}"
            )

        self._book_habilitado = bool(mt5.market_book_add(self._symbol))
        if not self._book_habilitado:
            _logger.warning(
                "market_book_add(%s) falhou (%s) — corretora pode nao expor DOM "
                "para este simbolo; seguindo so com trades.",
                self._symbol,
                mt5.last_error(),
            )

        self._parar_evt.clear()
        self._thread = threading.Thread(
            target=self._loop_borda, name="mt5-borda", daemon=True
        )
        self._thread.start()

        self._loop_consumo()

    def parar(self) -> None:
        self._parar_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._mt5 is not None:
            if self._book_habilitado:
                self._mt5.market_book_release(self._symbol)
            self._mt5.shutdown()

    # ------------------------------------------------------------------
    # Thread de borda: só MT5 + fila. Nunca toca o barramento.
    # ------------------------------------------------------------------

    def _loop_borda(self) -> None:
        mt5 = self._mt5
        assert mt5 is not None
        ultimo_tick_time_msc = 0
        snapshot_anterior: BookSnapshot | None = None
        ultimo_poll_ok = time.monotonic()
        conectado = True

        while not self._parar_evt.is_set():
            agora = time.monotonic()
            try:
                novos_ticks, ultimo_tick_time_msc = self._puxar_ticks(
                    mt5, ultimo_tick_time_msc
                )
                for trade in novos_ticks:
                    self._fila.put(trade)

                if self._book_habilitado:
                    snapshot = self._puxar_book(mt5)
                    if snapshot is not None:
                        self._fila.put(snapshot)
                        if snapshot_anterior is not None:
                            for delta in derivar_deltas(snapshot_anterior, snapshot):
                                self._fila.put(delta)
                        snapshot_anterior = snapshot

                if not conectado:
                    self._fila.put(
                        FalhaCaptura(
                            timestamp_ns=time.time_ns(),
                            symbol=self._symbol,
                            tipo=TipoFalha.RECONEXAO,
                            detalhe="polling voltou a responder",
                        )
                    )
                    conectado = True

                gap_s = agora - ultimo_poll_ok
                if gap_s > _LIMIAR_GAP_S:
                    self._fila.put(
                        FalhaCaptura(
                            timestamp_ns=time.time_ns(),
                            symbol=self._symbol,
                            tipo=TipoFalha.GAP_TICKS,
                            detalhe=(
                                f"intervalo entre polls de {gap_s:.2f}s excedeu o "
                                f"limiar de {_LIMIAR_GAP_S:.2f}s — ticks/book podem "
                                "ter sido perdidos nessa janela"
                            ),
                        )
                    )
                ultimo_poll_ok = agora
            except Exception as erro:  # defesa: nunca deixar a thread morrer muda
                conectado = False
                self._fila.put(
                    FalhaCaptura(
                        timestamp_ns=time.time_ns(),
                        symbol=self._symbol,
                        tipo=TipoFalha.ERRO_FONTE,
                        detalhe=f"{type(erro).__name__}: {erro}",
                    )
                )
                _logger.exception("erro no polling do MT5")

            time.sleep(self._intervalo_poll_s)

    def _puxar_ticks(
        self, mt5: ModuleType, ultimo_tick_time_msc: int
    ) -> tuple[list[Trade], int]:
        de = ultimo_tick_time_msc // 1000 if ultimo_tick_time_msc else 0
        ticks = mt5.copy_ticks_from(self._symbol, de, 1000, mt5.COPY_TICKS_ALL)
        if ticks is None:
            return [], ultimo_tick_time_msc
        if getattr(ticks, "ndim", 1) == 0:
            # numpy retorna um registro estruturado 0-d (escalar) quando o
            # array tem exatamente 1 tick — normaliza para sequência antes
            # de iterar, senão `for tick in ticks` percorre os CAMPOS do
            # registro em vez do registro inteiro.
            ticks = [ticks]
        if len(ticks) == 0:
            return [], ultimo_tick_time_msc

        trades: list[Trade] = []
        novo_ultimo = ultimo_tick_time_msc
        for tick in ticks:
            time_msc = int(tick["time_msc"])
            if time_msc <= ultimo_tick_time_msc:
                continue  # já processado — janela sobreposta do copy_ticks_from
            novo_ultimo = max(novo_ultimo, time_msc)

            preco_bruto = float(tick["last"]) if tick["last"] else float(tick["bid"])
            if preco_bruto <= 0:
                continue
            try:
                preco_ticks = self._grid.to_ticks(preco_bruto)
            except ValueError:
                continue

            agressor = self._inferir_agressor(mt5, tick)
            trades.append(
                Trade(
                    timestamp_ns=time_msc * 1_000_000,
                    symbol=self._symbol,
                    price=preco_ticks,
                    qty=int(tick["volume"]) if tick["volume"] else int(tick["volume_real"]),
                    side_agressor=agressor,
                    trade_id=f"MT5-{time_msc}-{int(tick['flags'])}",
                )
            )
        return trades, novo_ultimo

    def _inferir_agressor(self, mt5: ModuleType, tick) -> AgressorSide:
        flags = int(tick["flags"]) if "flags" in tick.dtype.names else 0
        flag_buy = getattr(mt5, "TICK_FLAG_BUY", 1 << 5)
        flag_sell = getattr(mt5, "TICK_FLAG_SELL", 1 << 6)
        tem_buy = bool(flags & flag_buy)
        tem_sell = bool(flags & flag_sell)
        if tem_buy and not tem_sell:
            return AgressorSide.BUY
        if tem_sell and not tem_buy:
            return AgressorSide.SELL

        # Sem flag conclusiva: compara preço do trade com bid/ask vigentes.
        preco = float(tick["last"]) if tick["last"] else None
        bid = float(tick["bid"]) if tick["bid"] else None
        ask = float(tick["ask"]) if tick["ask"] else None
        if preco is not None and ask is not None and preco >= ask:
            return AgressorSide.BUY
        if preco is not None and bid is not None and preco <= bid:
            return AgressorSide.SELL
        return AgressorSide.UNKNOWN

    def _puxar_book(self, mt5: ModuleType) -> BookSnapshot | None:
        book = mt5.market_book_get(self._symbol)
        if not book:
            return None

        bids_brutos = [item for item in book if item.type in (0, getattr(mt5, "BOOK_TYPE_BUY", 0))]
        asks_brutos = [item for item in book if item.type in (1, getattr(mt5, "BOOK_TYPE_SELL", 1))]
        bids_brutos.sort(key=lambda i: -i.price)
        asks_brutos.sort(key=lambda i: i.price)

        def _para_niveis(itens) -> tuple[BookLevel, ...]:
            niveis = []
            for item in itens[: self._profundidade_maxima]:
                try:
                    preco_ticks = self._grid.to_ticks(float(item.price))
                except ValueError:
                    continue
                qty = int(item.volume) if item.volume else int(item.volume_dbl)
                niveis.append(BookLevel(price=preco_ticks, qty=qty, n_orders=1))
            return tuple(niveis)

        return BookSnapshot(
            timestamp_ns=time.time_ns(),
            symbol=self._symbol,
            bids=_para_niveis(bids_brutos),
            asks=_para_niveis(asks_brutos),
        )

    # ------------------------------------------------------------------
    # Thread principal: só ela chama `Barramento.publicar`.
    # ------------------------------------------------------------------

    def _loop_consumo(self) -> None:
        while not (self._parar_evt.is_set() and self._fila.empty()):
            try:
                evento = self._fila.get(timeout=0.1)
            except queue.Empty:
                continue
            self._barramento.publicar(evento)


def derivar_deltas(anterior: BookSnapshot, atual: BookSnapshot) -> list[BookDelta]:
    """Compara dois snapshots consecutivos do mesmo símbolo e produz os
    `BookDelta` que levam de um ao outro — ADD (nível novo), DELETE (nível
    que sumiu) ou UPDATE (quantidade mudou na mesma posição). É o que
    alimenta a camada de microestrutura sem que ela precise conhecer MT5.
    """
    deltas: list[BookDelta] = []
    deltas.extend(_diff_lado(anterior.bids, atual.bids, Side.BUY, atual.timestamp_ns, atual.symbol))
    deltas.extend(_diff_lado(anterior.asks, atual.asks, Side.SELL, atual.timestamp_ns, atual.symbol))
    return deltas


def _diff_lado(
    antes: tuple[BookLevel, ...],
    depois: tuple[BookLevel, ...],
    side: Side,
    timestamp_ns: int,
    symbol: str,
) -> list[BookDelta]:
    antes_por_preco = {nivel.price: nivel for nivel in antes}
    depois_por_preco = {nivel.price: nivel for nivel in depois}
    deltas: list[BookDelta] = []

    for posicao, nivel in enumerate(depois):
        anterior_nivel = antes_por_preco.get(nivel.price)
        if anterior_nivel is None:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.ADD,
                    price=nivel.price,
                    qty=nivel.qty,
                    position=posicao,
                )
            )
        elif anterior_nivel.qty != nivel.qty:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.UPDATE,
                    price=nivel.price,
                    qty=nivel.qty,
                    position=posicao,
                )
            )

    for nivel in antes:
        if nivel.price not in depois_por_preco:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.DELETE,
                    price=nivel.price,
                    qty=0,
                    position=-1,
                )
            )

    return deltas
