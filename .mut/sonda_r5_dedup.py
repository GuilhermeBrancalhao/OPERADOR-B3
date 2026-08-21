# -*- coding: utf-8 -*-
"""Sondas do conserto R5 da dedup (criticas/nucleo_r4.md, secao A.5).

  a) curva de re-emissao indevida 1.000..50.000 chaves, politica NOVA x FIFO
  b) custo por evento dos tres detectores de livro contra a barra de 10.000/s
  c) rotatividade de chave: order_id sintetico x (side, price)
  d) retencao: tamanho do mapa ao longo de um pregao de 6h

Uso: PYTHONPATH=. python .mut/sonda_r5.py [a|b|c|d]
"""
from __future__ import annotations

import sys
import time
from collections import OrderedDict

from fluxopro.core.eventos import Side
from fluxopro.microestrutura.detectores import (
    ConfigIceberg,
    ConfigLiquidezFantasma,
    DetectorEscora,
    DetectorIcebergPorRecarga,
    DetectorLiquidezFantasma,
    JANELA_EPISODIO_NS,
    LIMITE_CHAVES_RASTREADAS,
    _MapaProcedencia,
)
from fluxopro.microestrutura.eventos_mbo import FonteMicro, OrdemEvento, TipoEventoOrdem
from fluxopro.microestrutura.livro_mbo import LivroMBO

NS = [1000, 2000, 4000, 4096, 4500, 5000, 6000, 8000, 12000, 20000, 35000, 50000]


class FIFOOnda7:
    """A politica da onda 7, copiada verbatim para o A/B continuar honesto."""

    def __init__(self, limite=4096, janela_ns=0):
        self.c = limite
        self.d = OrderedDict()

    def obter(self, k):
        return self.d.get(k)

    def de(self, k, ts=None):
        v = self.d.get(k)
        if v is None:
            self.d[k] = v = object()
            while len(self.d) > self.c:
                self.d.popitem(last=False)
        else:
            self.d.move_to_end(k)
        return v

    def __len__(self):
        return len(self.d)


def taxa(cls, n, limite, voltas=3, janela_ns=JANELA_EPISODIO_NS, passo_ns=1):
    m = cls(limite, janela_ns)
    ts = 0
    re = vis = 0
    for volta in range(voltas):
        for k in range(n):
            ts += passo_ns
            conhecida = m.obter(k) is not None
            if volta:
                vis += 1
                if not conhecida:
                    re += 1
            m.de(k, ts)
    return 100.0 * re / max(1, vis), len(m)


def a():
    print("A) CURVA DE RE-EMISSAO INDEVIDA (rotacao ciclica, 3 voltas)\n")
    print("A1) teto de FABRICA: onda 7 = 4.096 FIFO  x  agora = %d + TTL %ds"
          % (LIMITE_CHAVES_RASTREADAS, JANELA_EPISODIO_NS // 10**9))
    print("  %8s | %10s | %10s" % ("chaves", "FIFO 4096", "NOVA"))
    for n in NS:
        t_velho, _ = taxa(FIFOOnda7, n, 4096)
        t_novo, tam = taxa(_MapaProcedencia, n, LIMITE_CHAVES_RASTREADAS)
        print("  %8d | %9.1f%% | %9.1f%%  (mapa=%d)" % (n, t_velho, t_novo, tam))

    print("\nA2) MESMO teto (512) nas duas politicas: e aqui que o penhasco aparece")
    print("  %8s | %10s | %10s | %s" % ("chaves", "FIFO 512", "NOVA 512", "degrau NOVA"))
    ant = None
    for n in [400, 512, 560, 640, 768, 1024, 1536, 2048, 4096, 8192, 20000, 50000]:
        tv, _ = taxa(FIFOOnda7, n, 512)
        tn, _ = taxa(_MapaProcedencia, n, 512)
        deg = "-" if ant is None else "%+6.1f pp" % (tn - ant)
        ant = tn
        print("  %8d | %9.1f%% | %9.1f%% | %s" % (n, tv, tn, deg))


def _ev(oid, side, price, ts):
    return OrdemEvento(
        timestamp_ns=ts, symbol="WDOV26", tipo=TipoEventoOrdem.NEW, side=side,
        price=price, qty=10, order_id=oid, fonte=FonteMicro.MBP_INFERIDO,
        confianca=0.6,
    )


def b():
    print("B) CUSTO POR EVENTO — barra do pacote: 10.000/s por detector\n")
    N = 300_000
    for nome, det in (
        ("Escora", DetectorEscora()),
        ("Iceberg", DetectorIcebergPorRecarga()),
        ("Fantasma", DetectorLiquidezFantasma(0.5)),
    ):
        evs = [_ev("s%d" % i, Side.BUY if i % 2 else Side.SELL, 4800 + (i % 401),
                   i * 15_384) for i in range(N)]
        t0 = time.perf_counter()
        for e in evs:
            det.observar(e)
        dt = time.perf_counter() - t0
        print("  %-9s observar: %9.0f ev/s  (%.2f us/ev)  mapa=%d  -> %.0fx a barra"
              % (nome, N / dt, dt / N * 1e6, det.n_chaves_rastreadas, N / dt / 10_000))

    # caminho completo do Escora (verificar + observar)
    livro = LivroMBO("WDOV26")
    det = DetectorEscora()
    det.acompanhar(livro)
    M = 60_000
    ts = 0
    t0 = time.perf_counter()
    for i in range(M):
        ts += 100_000
        p = 4900 + (i % 200)
        livro.adicionar("o%d" % i, Side.BUY, p, 100, ts)
        livro.executar(Side.BUY, p, 100, ts + 1)
        det.verificar(livro, Side.BUY, p, ts)
    dt = time.perf_counter() - t0
    print("  %-9s livro+verificar: %8.0f ciclos/s  mapa=%d"
          % ("Escora", M / dt, det.n_chaves_rastreadas))


def c():
    print("C) ROTATIVIDADE DA CHAVE (5 s de tape a 65.000 ordens sinteticas/s)\n")
    ids = set()
    niveis = set()
    ts = 0
    for j in range(325_000):
        ts += 15_384
        ids.add("sint%d" % j)
        niveis.add((Side.BUY if j % 2 else Side.SELL, 4800 + (j % 401)))
    print("  chaves distintas por order_id ....... %d" % len(ids))
    print("  chaves distintas por (side, price) .. %d" % len(niveis))
    print("  razao ............................... %.0fx" % (len(ids) / len(niveis)))
    print("  memoria coberta pelo teto 4.096 (onda 7), chave order_id: %.0f ms"
          % (4096 / 65_000 * 1000))
    print("  memoria coberta pela janela de %ds, chave (side, price): %d s"
          % (JANELA_EPISODIO_NS // 10**9, JANELA_EPISODIO_NS // 10**9))


def d():
    print("D) RETENCAO — 6 h de pregao a 65.000 eventos/s de ordem\n")
    det = DetectorLiquidezFantasma(0.5)
    ts = 0
    pico = 0
    marcos = []
    total = 6 * 3600 * 65_000 // 300  # amostra 1/300 do volume, mesmo dt
    for j in range(total):
        ts += 15_384 * 300
        det.observar(_ev("s%d" % j, Side.BUY if j % 2 else Side.SELL,
                         4800 + (j % 401), ts))
        pico = max(pico, det.n_chaves_rastreadas)
        if j % (total // 6) == 0:
            marcos.append((ts / 1e9 / 3600, det.n_chaves_rastreadas))
    for h, n in marcos:
        print("  t=%4.1f h  chaves=%d" % (h, n))
    print("  pico=%d   teto=%d   (a chave viva e o NIVEL, ~800)"
          % (pico, LIMITE_CHAVES_RASTREADAS))


if __name__ == "__main__":
    for arg in (sys.argv[1:] or ["a", "b", "c", "d"]):
        {"a": a, "b": b, "c": c, "d": d}[arg]()
        print()
