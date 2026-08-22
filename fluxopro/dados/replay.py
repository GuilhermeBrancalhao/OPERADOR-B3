"""Adaptador de replay: lê trades (+ deltas de book, opcional) de CSV.

Formato escolhido: CSV puro, não Parquet. O núcleo determinístico não precisa
de pandas/pyarrow — dependências pesadas — apenas de leitura sequencial de
linhas. Quem tiver dados em Parquet converte para CSV uma vez (ou estende
este módulo com um leitor próprio); `requirements.txt` fica mínimo.

## Critério de crescimento (a razão de este módulo ser STREAMING)

*"Qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão
continua?"* — o critério do docstring de `_registrar_preco`
(`microestrutura/inferencia_mbp.py`), aplicado ao ordenador deste módulo.

Até a onda 8, `_eventos_ordenados` devolvia uma **lista**: montava
`[(ts, origem, indice, evento), ...]` com o arquivo inteiro, ordenava e
devolvia uma segunda lista com os eventos — as duas vivas ao mesmo tempo,
antes de o primeiro evento ser publicado. A resposta ao critério era "o
número de eventos do pregão", e ela não para de crescer. Medido nesta forma
(`.mut/sonda_r6b_crescimento.py`, `tracemalloc`, linear em 25 k/50 k/100 k):

    347 B/evento  ->  pregao 6 h a  5.000 ev/s = 108 M eventos =  37,3 GB
                      pregao 6 h a 10.000 ev/s = 216 M eventos =  74,6 GB

É o mesmo defeito que `criticas/nucleo_r5.md` §A.4.3 achou em
`dados/leitor_gravacao.py` — a mesma forma, no outro leitor. Aqui está
consertado do mesmo jeito: `heapq.merge` sobre os iteradores, memória O(1) no
número de eventos (O(nº de arquivos) itens no heap). A saída é **a mesma
sequência, evento por evento**; o que muda é não existir mais um instante em
que o pregão inteiro está na RAM.

## Duas consequências do streaming, e o que se fez com cada uma

**(a) A ordem total tem de vir da CHAVE, não da estabilidade do `sort`.** A
versão em lista se apoiava, sem dizer, num acidente: os trades eram anexados
antes dos deltas e `list.sort` é estável, então ordenar só por `ts` já
produzia "trade antes de delta" no empate. Ou seja, `_ORIGEM_TRADE` /
`_ORIGEM_DELTA` estavam na chave sem serem load-bearing — e uma mutação que
os removesse da chave não mudava saída nenhuma (é a mutação `N01` de
`criticas/nucleo_r2.md`, viva por cinco rodadas justamente por ser
equivalente). Aqui os iteradores entram no `heapq.merge` na ordem
**deltas, trades**, contrária ao contrato de propósito: o desempate passa a
depender só de `_ORIGEM_TRADE < _ORIGEM_DELTA`. Enfraquecer a chave inverte a
saída, e o teste de empate pega.

**O terceiro componente da chave (`indice`) é, e continua sendo,
INALCANÇÁVEL por teste — e isso é uma propriedade, não um buraco.**
`heapq.merge` mantém **uma** entrada por iterável no heap: o item *k+1* de um
fluxo só entra depois que o item *k* saiu. Logo a ordem dentro de um mesmo
arquivo é sempre a de leitura, com ou sem `indice` na chave. Medido, não
suposto: 2.000 entradas aleatórias com timestamps repetidos dão saída
byte-a-byte idêntica nas duas versões (a mutação `N01b` do lote desta onda
sobrevive, e é a única — é um mutante **equivalente**, provado). O `indice`
fica escrito porque a chave declara a ordem total pretendida e porque a
redundância deixa de existir no minuto em que alguém trocar o merge por
outra coisa; quem for auditar isto de novo pode parar aqui.

**(b) `heapq.merge` exige entrada ordenada.** O `sort` global mascarava
arquivo fora de ordem; o merge não. Política, alinhada com
`RelogioReplay.avancar_para`: **recusar explicitamente**, com
`ReplayForaDeOrdemError`, dizendo arquivo, linha e os dois timestamps — em
vez de embaralhar em silêncio um replay que o usuário vai usar como gabarito.
Reordenar o arquivo antes é responsabilidade de quem o produziu.
"""

from __future__ import annotations

import csv
import heapq
import time
from pathlib import Path
from typing import Iterable, Iterator

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookAction, BookDelta, Side, Trade
from fluxopro.dados.adaptador import AdaptadorDados

_ORIGEM_TRADE = 0
_ORIGEM_DELTA = 1


class ReplayForaDeOrdemError(ValueError):
    """Um arquivo de replay tem `timestamp_ns` regredindo entre linhas."""


def _monotonico(
    eventos: Iterable[Trade | BookDelta], caminho: Path
) -> Iterator[Trade | BookDelta]:
    """Repassa os eventos exigindo `timestamp_ns` não-decrescente.

    Mesma política de `core/relogio.py`: retrocesso é erro de DADO, e quem
    alimenta o replay é quem reordena. A mensagem cita arquivo, número da
    linha de dados e os dois timestamps, porque um replay embaralhado só
    apareceria rio abaixo como sinal errado, sem relação óbvia com a causa.
    """
    anterior: int | None = None
    for indice, evento in enumerate(eventos):
        if anterior is not None and evento.timestamp_ns < anterior:
            raise ReplayForaDeOrdemError(
                f"{caminho}: timestamp regride na linha de dados {indice + 1} "
                f"({anterior} -> {evento.timestamp_ns}); reordene o arquivo "
                f"antes do replay"
            )
        anterior = evento.timestamp_ns
        yield evento


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

    def _eventos_ordenados(self) -> Iterator[Trade | BookDelta]:
        """Sequência ordenada por `(timestamp_ns, origem, índice no arquivo)`,
        produzida em STREAMING — memória O(nº de arquivos), não O(nº de
        eventos). Ver "Critério de crescimento" no topo do módulo.

        Os iteradores entram no merge na ordem **deltas, trades**: contrária
        ao contrato de propósito, para que o desempate saia da chave e não da
        ordem dos argumentos (ver nota (a) no topo do módulo).
        """
        fluxos: list[Iterator[tuple[tuple[int, int, int], Trade | BookDelta]]] = []
        if self._deltas_path is not None:
            fluxos.append(self._chaveado(_ORIGEM_DELTA, self._deltas_path))
        fluxos.append(self._chaveado(_ORIGEM_TRADE, self._trades_path))
        for _chave, evento in heapq.merge(*fluxos, key=lambda item: item[0]):
            yield evento

    def _chaveado(
        self, origem: int, caminho: Path
    ) -> Iterator[tuple[tuple[int, int, int], Trade | BookDelta]]:
        leitor = _ler_trades if origem == _ORIGEM_TRADE else _ler_deltas
        for indice, evento in enumerate(_monotonico(leitor(caminho), caminho)):
            yield (evento.timestamp_ns, origem, indice), evento
