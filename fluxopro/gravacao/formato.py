"""Schema de arquivo do gravador — compartilhado entre `Gravador` (escreve) e
`fluxopro.dados.leitor_gravacao` (lê), para as duas pontas nunca divergirem.

Decisão de formato: CSV, igual ao `fluxopro/dados/replay.py` já usa para o
replay determinístico do núcleo — mesma leitura sequencial simples, sem
puxar pandas/pyarrow para dentro do projeto (ver benchmark e justificativa
completa no relatório final / docstring de `gravador.py`). O arquivo do dia
fica aberto como CSV puro enquanto a captura está ocorrendo (append barato,
seguro contra crash); na rotação diária o arquivo fechado é comprimido para
`.csv.gz` — assim a escrita ao vivo nunca paga o custo de CPU da compressão,
e o arquivo em repouso ocupa ~4x menos disco.

`SCHEMA_VERSAO` sobe sempre que uma coluna for adicionada/removida/renomeada
— o leitor e o `Catalogo` usam isso para recusar ler um formato que não
entendem, em vez de interpretar campos errados silenciosamente.
"""

from __future__ import annotations

from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha

SCHEMA_VERSAO = 1

CABECALHO_TRADES = [
    "timestamp_ns", "symbol", "price", "qty", "side_agressor",
    "trade_id", "buyer_broker", "seller_broker",
]
CABECALHO_SNAPSHOTS = ["timestamp_ns", "symbol", "bids", "asks"]
CABECALHO_DELTAS = [
    "timestamp_ns", "symbol", "side", "action", "price", "qty", "position",
]
CABECALHO_FALHAS = ["timestamp_ns", "symbol", "tipo", "detalhe"]

_SEP_NIVEL = "|"
_SEP_CAMPO = ":"


def codificar_niveis(niveis: tuple[BookLevel, ...]) -> str:
    return _SEP_NIVEL.join(
        f"{n.price}{_SEP_CAMPO}{n.qty}{_SEP_CAMPO}{n.n_orders}" for n in niveis
    )


def decodificar_niveis(texto: str) -> tuple[BookLevel, ...]:
    if not texto:
        return ()
    niveis = []
    for parte in texto.split(_SEP_NIVEL):
        preco_s, qty_s, n_s = parte.split(_SEP_CAMPO)
        niveis.append(BookLevel(price=int(preco_s), qty=int(qty_s), n_orders=int(n_s)))
    return tuple(niveis)


def trade_para_linha(t: Trade) -> list[str]:
    return [
        str(t.timestamp_ns), t.symbol, str(t.price), str(t.qty),
        t.side_agressor.value, t.trade_id, t.buyer_broker, t.seller_broker,
    ]


def linha_para_trade(linha: dict[str, str]) -> Trade:
    return Trade(
        timestamp_ns=int(linha["timestamp_ns"]),
        symbol=linha["symbol"],
        price=int(linha["price"]),
        qty=int(linha["qty"]),
        side_agressor=AgressorSide(linha["side_agressor"]),
        trade_id=linha["trade_id"],
        buyer_broker=linha.get("buyer_broker") or "",
        seller_broker=linha.get("seller_broker") or "",
    )


def snapshot_para_linha(s: BookSnapshot) -> list[str]:
    return [
        str(s.timestamp_ns), s.symbol,
        codificar_niveis(s.bids), codificar_niveis(s.asks),
    ]


def linha_para_snapshot(linha: dict[str, str]) -> BookSnapshot:
    return BookSnapshot(
        timestamp_ns=int(linha["timestamp_ns"]),
        symbol=linha["symbol"],
        bids=decodificar_niveis(linha["bids"]),
        asks=decodificar_niveis(linha["asks"]),
    )


def delta_para_linha(d: BookDelta) -> list[str]:
    return [
        str(d.timestamp_ns), d.symbol, d.side.value, d.action.value,
        str(d.price), str(d.qty), str(d.position),
    ]


def linha_para_delta(linha: dict[str, str]) -> BookDelta:
    return BookDelta(
        timestamp_ns=int(linha["timestamp_ns"]),
        symbol=linha["symbol"],
        side=Side(linha["side"]),
        action=BookAction(linha["action"]),
        price=int(linha["price"]),
        qty=int(linha["qty"]),
        position=int(linha["position"]),
    )


def falha_para_linha(f: FalhaCaptura) -> list[str]:
    return [str(f.timestamp_ns), f.symbol, f.tipo.value, f.detalhe]


def linha_para_falha(linha: dict[str, str]) -> FalhaCaptura:
    return FalhaCaptura(
        timestamp_ns=int(linha["timestamp_ns"]),
        symbol=linha["symbol"],
        tipo=TipoFalha(linha["tipo"]),
        detalhe=linha["detalhe"],
    )


NOMES_ARQUIVO = {
    Trade: "trades.csv",
    BookSnapshot: "book_snapshots.csv",
    BookDelta: "book_deltas.csv",
    FalhaCaptura: "falhas.csv",
}
