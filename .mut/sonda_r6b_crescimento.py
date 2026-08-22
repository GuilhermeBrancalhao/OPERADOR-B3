# -*- coding: utf-8 -*-
"""Criterio de crescimento aplicado as colecoes dos arquivos do builder core+app.

Pergunta (docstring de _registrar_preco em inferencia_mbp.py):
  "qual grandeza limita o len disto, e ela para de crescer enquanto o pregao
   continua?"
"""
from __future__ import annotations
import csv, os, sys, tracemalloc
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import WDO_GRID, AgressorSide, Side, BookAction, BookDelta, Trade
from fluxopro.dados.replay import AdaptadorReplay
from fluxopro.app.saida import ConsoleFluxo


def csv_sintetico(dst: Path, n: int) -> None:
    with dst.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_ns','symbol','price','qty','side_agressor','trade_id','buyer_broker','seller_broker'])
        for i in range(n):
            w.writerow([i*1000, 'WDOV26', 10000 + (i % 40), 1 + (i % 7), 'BUY' if i % 2 else 'SELL', 't%d' % i, 'B%d' % (i%5), 'S%d' % (i%5)])


def medir_replay(tmp: Path, n: int) -> tuple[int, float]:
    p = tmp / ('t%d.csv' % n)
    csv_sintetico(p, n)
    bus = Barramento()
    ad = AdaptadorReplay(bus, p, None, velocidade='max')
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    lista = ad._eventos_ordenados()
    pico = tracemalloc.get_traced_memory()[0] - base
    tracemalloc.stop()
    del lista
    return pico, pico / n


def medir_console(n: int) -> tuple[int, float]:
    """ConsoleFluxo.linhas com guardar_linhas=True (o default, e o que
    scripts/operar.py usa)."""
    import io as _io
    c = ConsoleFluxo(WDO_GRID, stream=_io.StringIO(), guardar_linhas=True)
    linha = ('12:34:56.789  DETECCAO  ABSORCAO            COMPRA @5000.5    '
             '[INF 0.55]  | vol_dom=812 vol_oposto=1904 desloc_t=0 n_janela=37')
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    for _ in range(n):
        c._escrever(linha)
    pico = tracemalloc.get_traced_memory()[0] - base
    tracemalloc.stop()
    return pico, pico / n


def main() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        print('== dados/replay.py :: AdaptadorReplay._eventos_ordenados (lista `combinados` + 2a lista) ==')
        for n in (25_000, 50_000, 100_000):
            b, por = medir_replay(tmp, n)
            print('   n=%9s  bytes=%14s  B/evento=%7.1f' % (format(n, ','), format(b, ','), por))
        _, por = medir_replay(tmp, 100_000)
        for taxa in (5_000, 10_000):
            ev = 6 * 3600 * taxa
            print('   pregao 6h a %6s ev/s -> %s eventos -> %.1f GB' % (format(taxa, ','), format(ev, ','), ev * por / 1e9))

    print()
    print('== app/saida.py :: ConsoleFluxo.linhas (guardar_linhas=True, o default do CLI) ==')
    for n in (25_000, 50_000, 100_000):
        b, por = medir_console(n)
        print('   n=%9s  bytes=%14s  B/linha=%7.1f' % (format(n, ','), format(b, ','), por))
    _, por = medir_console(100_000)
    # C.3 do R5: 11.054 deteccoes em 500.000 eventos = 2,21% ; sinais a parte
    for taxa in (5_000, 10_000):
        ev = 6 * 3600 * taxa
        linhas = int(ev * 11054 / 500_000)
        print('   pregao 6h a %6s ev/s -> %s eventos -> %s linhas -> %.2f GB' % (
            format(taxa, ','), format(ev, ','), format(linhas, ','), linhas * por / 1e9))


if __name__ == '__main__':
    main()
