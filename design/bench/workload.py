"""Carga sintetica COMUM aos benchmarks de UI. Descartavel.

Define exatamente o mesmo trabalho para todos os toolkits, para que os numeros
sejam comparaveis:

  FOOTPRINT : 60 niveis de preco x 40 barras = 2.400 celulas.
              Cada celula = 1 retangulo preenchido + 2 numeros ("bidxask").
              => 2.400 rects + 4.800 desenhos de texto por quadro.

  DOM       : 40 niveis x 6 colunas numericas = 240 textos + 80 barras por quadro.

  HEATMAP   : 200 niveis de preco x 600 colunas de tempo = 120.000 celulas,
              atualizadas como imagem inteira (bookmap rolando).

Nada aqui depende de toolkit.
"""

import numpy as np

FP_ROWS, FP_COLS = 60, 40
FP_CELLS = FP_ROWS * FP_COLS

DOM_ROWS, DOM_COLS = 40, 6

HM_ROWS, HM_COLS = 200, 600

CELL_W, CELL_H = 46, 13


def gerar_footprint(seed: int = 7):
    """Retorna (bid, ask, delta_norm) inteiros — o quadro base do footprint."""
    rng = np.random.default_rng(seed)
    bid = rng.integers(0, 999, size=(FP_ROWS, FP_COLS), dtype=np.int32)
    ask = rng.integers(0, 999, size=(FP_ROWS, FP_COLS), dtype=np.int32)
    d = (ask - bid).astype(np.float32)
    dn = (d - d.min()) / max(1.0, float(d.max() - d.min()))
    return bid, ask, dn


def gerar_heatmap(seed: int = 11):
    rng = np.random.default_rng(seed)
    return rng.random((HM_ROWS, HM_COLS), dtype=np.float32)


def rolar_heatmap(hm, rng):
    """Uma coluna nova por tick (bookmap real rola 1 coluna por atualizacao)."""
    hm[:, :-1] = hm[:, 1:]
    hm[:, -1] = rng.random(HM_ROWS, dtype=np.float32)
    return hm


def stats(tempos_ms):
    a = np.asarray(tempos_ms, dtype=np.float64)
    a.sort()
    return {
        "n": int(a.size),
        "media_ms": float(a.mean()),
        "p50_ms": float(np.percentile(a, 50)),
        "p95_ms": float(np.percentile(a, 95)),
        "p99_ms": float(np.percentile(a, 99)),
        "fps_p50": 1000.0 / float(np.percentile(a, 50)),
        "fps_p95": 1000.0 / float(np.percentile(a, 95)),
    }


def linha(nome, s):
    return (
        f"{nome:<34} n={s['n']:>5}  p50={s['p50_ms']:7.3f}ms  "
        f"p95={s['p95_ms']:7.3f}ms  p99={s['p99_ms']:7.3f}ms  "
        f"fps(p50)={s['fps_p50']:7.1f}  fps(p95)={s['fps_p95']:6.1f}"
    )
