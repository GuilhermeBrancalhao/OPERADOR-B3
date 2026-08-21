"""Adaptador de replay: lê trades (+ deltas de book, opcional) de CSV.

Formato escolhido: CSV puro, não Parquet. O núcleo determinístico não precisa
de pandas/pyarrow — dependências pesadas — apenas de leitura sequencial de
linhas. Quem tiver dados em Parquet converte para CSV uma vez (ou estende
este módulo com um leitor próprio); `requirements.txt` fica mínimo.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Iterator

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookAction, BookDelta, Side, Trade
from fluxopro.dados.adaptador import AdaptadorDados

_ORIGEM_TRADE = 0
_ORIGEM_DELTA = 1


def _ler_trades(caminho: Path) -> Iterator[Trade]:
    with caminho.open("r", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            yield Trade(
                timestamp_ns=int(linha["timestamp_ns"]),
                symbol=linha["symbol"],
                price=int(linha["price"]),
                qty=int(linha["qty"]),
                side_agressor=AgressorSide(linha["side_agressor"]),
                trade_id=linha["trade_id"],
                buyer_broker=linha.get("buyer_broker") or "",
                seller_broker=linha.get("seller_broker") or "",
            )


def _ler_deltas(caminho: Path) -> Iterator[BookDelta]:
    with caminho.open("r", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            yield BookDelta(
                timestamp_ns=int(linha["timestamp_ns"]),
                symbol=linha["symbol"],
                side=Side(linha["side"]),
                action=BookAction(linha["action"]),
                price=int(linha["price"]),
                qty=int(linha["qty"]),
                position=int(linha["position"]),
            )


class AdaptadorReplay(AdaptadorDados):
    """Publica trades e deltas de book em ordem estrita de `timestamp_ns`.

    Em empate de timestamp: trades entregues antes de deltas, e dentro de
    cada arquivo a ordem original das linhas é preservada — a mesma entrada
    produz sempre a mesma sequência exata de eventos, em qualquer máquina.

    `velocidade`: "max" (padrão) entrega tudo sem pausa; um `float` (1.0,
    10.0, ...) faz o adaptador dormir entre eventos para simular a passagem
    real do tempo na proporção informada.
    """

    def __init__(
        self,
        barramento: Barramento,
        trades_path: str | Path,
        deltas_path: str | Path | None = None,
        velocidade: float | str = "max",
    ) -> None:
        super().__init__(barramento)
        self._trades_path = Path(trades_path)
        self._deltas_path = Path(deltas_path) if deltas_path is not None else None
        self._velocidade = velocidade
        self._parar = False

    def iniciar(self) -> None:
        self._parar = False
        primeiro_ts: int | None = None
        wall_inicio: float | None = None

        for evento in self._eventos_ordenados():
            if self._parar:
                break
            if self._velocidade != "max":
                if primeiro_ts is None:
                    primeiro_ts = evento.timestamp_ns
                    wall_inicio = time.monotonic()
                else:
                    fator = float(self._velocidade)
                    decorrido_evento_s = (evento.timestamp_ns - primeiro_ts) / 1e9 / fator
                    decorrido_wall_s = time.monotonic() - wall_inicio  # type: ignore[operator]
                    espera = decorrido_evento_s - decorrido_wall_s
                    if espera > 0:
                        time.sleep(espera)
            self._barramento.publicar(evento)

    def parar(self) -> None:
        self._parar = True

    def _eventos_ordenados(self) -> list[Trade | BookDelta]:
        combinados: list[tuple[int, int, int, Trade | BookDelta]] = []
        for indice, trade in enumerate(_ler_trades(self._trades_path)):
            combinados.append((trade.timestamp_ns, _ORIGEM_TRADE, indice, trade))
        if self._deltas_path is not None:
            for indice, delta in enumerate(_ler_deltas(self._deltas_path)):
                combinados.append((delta.timestamp_ns, _ORIGEM_DELTA, indice, delta))
        combinados.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in combinados]
