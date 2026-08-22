# -*- coding: utf-8 -*-
"""Numeros ANTES/DEPOIS da correcao da 6a casa e do seu gemeo.

O "antes" nao e mutacao do codigo de producao: e a implementacao antiga
reconstruida aqui, lado a lado com a nova, medida no MESMO processo, com a
MESMA carga e o MESMO instrumento. Assim os dois numeros sao comparaveis, e a
arvore de producao fica intacta enquanto a sonda roda (a R5 registrou que ler
o disco durante mutacao em voo e o erro que o registro em voo existe para
tornar detectavel).

Rodar com a arvore restaurada: `.mut/r6_em_voo_gravacao.json` == [].
"""
from __future__ import annotations

import csv
import gc
import gzip
import json
import os
import shutil
import sys
import tempfile
import time
import tracemalloc

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fluxopro.core.barramento import Barramento                     # noqa: E402
from fluxopro.core.eventos import AgressorSide, BookDelta, BookSnapshot, Trade  # noqa: E402
from fluxopro.dados.eventos_captura import FalhaCaptura             # noqa: E402
from fluxopro.dados.leitor_gravacao import (                        # noqa: E402
    AdaptadorLeitorGravacao, _ler_arquivo, _ORDEM_TIPO,
)
from fluxopro.gravacao import formato                               # noqa: E402
from fluxopro.gravacao.catalogo import Catalogo                     # noqa: E402
from fluxopro.gravacao.gravador import Gravador                     # noqa: E402

TS = 1_700_000_000_000_000_000
MS = 1_000_000
SYMBOL = "WDOV26"

# Regimes da barra do projeto (bar/barra_profit_pro.md): pregao de 6 h.
PREGAO_6H_5K = 6 * 3600 * 5_000       # 108.000.000 eventos
PREGAO_6H_10K = 6 * 3600 * 10_000     # 216.000.000 eventos


def tamanho_profundo(obj, vistos=None) -> int:
    if vistos is None:
        vistos = set()
    if id(obj) in vistos:
        return 0
    vistos.add(id(obj))
    total = sys.getsizeof(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            total += tamanho_profundo(k, vistos) + tamanho_profundo(v, vistos)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for i in obj:
            total += tamanho_profundo(i, vistos)
    return total


def trade(i: int) -> Trade:
    return Trade(timestamp_ns=TS + i * MS, symbol=SYMBOL, price=10000 + (i % 7),
                 qty=5, side_agressor=AgressorSide.BUY, trade_id="T%d" % i)


# =====================================================================
print("=" * 74)
print("1) GRAVADOR — retencao por evento (objeto de producao vivo)")
print("=" * 74)
print("  %10s | %-28s | %-28s" % ("eventos", "ANTES (_horarios: list[int])", "DEPOIS (min/max incrementais)"))
print("  %10s-+-%-28s-+-%-28s" % ("-" * 10, "-" * 28, "-" * 28))

antes_b_ev = depois_b_ev = 0.0
for n in (10_000, 40_000, 80_000):
    destino = tempfile.mkdtemp()
    b = Barramento()
    g = Gravador(b, destino, fsync_a_cada=10 ** 9, meta_a_cada=0)
    g.iniciar()
    for i in range(n):
        b.publicar(trade(i))
    # DEPOIS: o que o objeto de producao retem hoje, por dia aberto
    depois = tamanho_profundo(g._hora_inicio_ns) + tamanho_profundo(g._hora_fim_ns)
    # ANTES: a estrutura que estava ali ate a R5, com a MESMA carga
    horarios = {(SYMBOL, "dia"): [TS + i * MS for i in range(n)]}
    antes = tamanho_profundo(horarios)
    print("  {:>10} | {:>13,} B {:>7.2f} B/ev | {:>13,} B {:>7.4f} B/ev".format(
        n, antes, antes / n, depois, depois / n))
    antes_b_ev, depois_b_ev = antes / n, depois / n
    del horarios
    for arq in list(g._arquivos.values()):
        arq.handle.close()
    shutil.rmtree(destino, ignore_errors=True)

print()
for rotulo, n_ev in (("6 h a  5.000 ev/s", PREGAO_6H_5K), ("6 h a 10.000 ev/s", PREGAO_6H_10K)):
    print("  pregao {} -> {:>12,} eventos:  ANTES {:>6.2f} GB   DEPOIS {} B (constante)".format(
        rotulo, n_ev, antes_b_ev * n_ev / 2 ** 30, int(depois_b_ev * 80_000)))

# =====================================================================
print()
print("=" * 74)
print("2) GRAVADOR — vazao (a correcao nao pode custar desempenho)")
print("=" * 74)
for n in (20_000, 60_000):
    destino = tempfile.mkdtemp()
    b = Barramento()
    g = Gravador(b, destino, fsync_a_cada=200)  # fsync e meta de fabrica
    g.iniciar()
    t0 = time.perf_counter()
    for i in range(n):
        b.publicar(trade(i))
    dt = time.perf_counter() - t0
    g.parar()
    print("  {:>9,} eventos  {:>6.2f}s  {:>9,} ev/s  {:>5.1f} us/ev".format(
        n, dt, int(n / dt), dt / n * 1e6))
    shutil.rmtree(destino, ignore_errors=True)

# =====================================================================
print()
print("=" * 74)
print("3) LEITOR — pico de memoria para RELER (tracemalloc, mesma gravacao)")
print("=" * 74)


def eventos_ordenados_ANTES(entrada, ts_ini=None, ts_fim=None):
    """A implementacao que estava em `leitor_gravacao.py:139-146` ate a R5."""
    combinados = []
    for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura):
        caminho = entrada.arquivo(formato.NOMES_ARQUIVO[tipo])
        for indice, evento in enumerate(_ler_arquivo(caminho, tipo)):
            combinados.append((evento.timestamp_ns, _ORDEM_TIPO[tipo], indice, evento))
    combinados.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in combinados]


print("  %9s | %-26s | %-26s" % ("eventos", "ANTES (sort global em lista)", "DEPOIS (heapq.merge)"))
print("  %9s-+-%-26s-+-%-26s" % ("-" * 9, "-" * 26, "-" * 26))
antes_pico_ev = depois_pico_ev = 0.0
for n in (10_000, 40_000):
    destino = tempfile.mkdtemp()
    b = Barramento()
    g = Gravador(b, destino, fsync_a_cada=10 ** 9)
    g.iniciar()
    for i in range(n):
        b.publicar(trade(i))
    g.parar()
    catalogo = Catalogo(destino)
    entrada = catalogo.escanear()[0]

    gc.collect(); tracemalloc.start()
    lista = eventos_ordenados_ANTES(entrada)
    _, pico_antes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(lista) == n
    del lista

    b2 = Barramento()
    vistos = [0]
    b2.assinar(Trade, lambda _e: vistos.__setitem__(0, vistos[0] + 1))
    leitor = AdaptadorLeitorGravacao(b2, entrada, catalogo=catalogo, verificar_hash=False)
    gc.collect(); tracemalloc.start()
    leitor.iniciar()
    _, pico_depois = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert vistos[0] == n

    print("  {:>9,} | {:>12,} B {:>7.1f} B/ev | {:>12,} B {:>6.2f} B/ev".format(
        n, pico_antes, pico_antes / n, pico_depois, pico_depois / n))
    antes_pico_ev, depois_pico_ev = pico_antes / n, pico_depois / n
    shutil.rmtree(destino, ignore_errors=True)

print()
for rotulo, n_ev in (("6 h a  5.000 ev/s", PREGAO_6H_5K), ("6 h a 10.000 ev/s", PREGAO_6H_10K)):
    print("  pregao {} -> {:>12,} eventos:  ANTES {:>6.1f} GB   DEPOIS ~{} KB (constante)".format(
        rotulo, n_ev, antes_pico_ev * n_ev / 2 ** 30, int(depois_pico_ev * 40_000 / 1024)))
