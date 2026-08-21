"""Onde exatamente morre o footprint no Qt? E da' para consertar?

bench_qt.py mediu 20 fps no laco ingenuo (7.200 chamadas QPainter por quadro).
Este script isola a causa e mede as 3 saidas de engenharia:

  1. PISO DE PYTHON      : 7.200 chamadas a uma funcao vazia. Se isso ja' custa
                           caro, o culpado nao e' o Qt.
  2. RECTS EM LOTE       : drawRects() agrupado por cor (32 chamadas em vez de 2.400).
  3. MOSAICO NUMPY       : quadro inteiro montado por indexacao vetorizada de um
                           atlas de tiles pre-renderizados; ZERO laco Python.
                           Um unico QImage sobe para a tela.
  4. INCREMENTAL/SCROLL  : backing store + repinta so' a coluna nova (60 celulas)
                           e rola o resto. E' o que um footprint real precisa,
                           porque so' a ultima barra muda a cada tick.

Roda: C:/bv/Scripts/python.exe bench_qt2.py
"""

import sys
import time

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from workload import CELL_H, CELL_W, FP_COLS, FP_ROWS, gerar_footprint, linha, stats

QUADROS = 300
W, H = FP_COLS * CELL_W, FP_ROWS * CELL_H

BID, ASK, DN = gerar_footprint()
IDX = (DN * 31).astype(np.int32)
PALETA = [QColor(int(20 + 200 * t), int(40 + 60 * abs(0.5 - t)), int(220 - 190 * t)) for t in np.linspace(0, 1, 32)]
FONTE = QFont("Consolas", 8)
TXT = QColor("#e6edf3")
S_BID = [[str(int(v)) for v in row] for row in BID]
S_ASK = [[str(int(v)) for v in row] for row in ASK]


# ------------------------------------------------------------ 1. piso de Python
def bench_piso():
    def nada(a, b, c, d, e):
        return None

    ts = []
    for _ in range(QUADROS):
        t0 = time.perf_counter()
        for c in range(FP_COLS):
            for r in range(FP_ROWS):
                nada(c, r, 1, 2, 3)  # ~ fillRect
                nada(c, r, 1, 2, 3)  # ~ drawText bid
                nada(c, r, 1, 2, 3)  # ~ drawText ask
        ts.append((time.perf_counter() - t0) * 1000)
    return stats(ts)


# --------------------------------------------------------- 2. drawRects em lote
def bench_rects_lote():
    """So' os fundos, agrupados por cor: 32 chamadas em vez de 2.400."""
    grupos = [[] for _ in range(32)]
    for c in range(FP_COLS):
        for r in range(FP_ROWS):
            grupos[IDX[r, c]].append(QRect(c * CELL_W, r * CELL_H, CELL_W - 1, CELL_H - 1))
    img = QImage(W, H, QImage.Format_RGB32)
    ts = []
    for _ in range(QUADROS):
        p = QPainter(img)
        t0 = time.perf_counter()
        for k, g in enumerate(grupos):
            if g:
                p.setBrush(PALETA[k])
                p.setPen(PALETA[k])
                p.drawRects(g)
        ts.append((time.perf_counter() - t0) * 1000)
        p.end()
    return stats(ts)


# ------------------------------------------------------------- 3. mosaico numpy
def montar_atlas():
    """Pre-renderiza UMA vez cada tile possivel de celula.

    Chave do tile = (cor 0..31). O texto e' pre-renderizado como mascara por
    valor 0..999. No quadro, combina-se cor + mascara por indexacao vetorizada.
    """
    # atlas de cores: (32, CELL_H, CELL_W, 3)
    cores = np.zeros((32, CELL_H, CELL_W, 3), dtype=np.uint8)
    for k, qc in enumerate(PALETA):
        cores[k, :, :, 0] = qc.red()
        cores[k, :, :, 1] = qc.green()
        cores[k, :, :, 2] = qc.blue()

    # atlas de mascaras de texto: (1000, CELL_H, CELL_W) uint8 0/255
    pm = QImage(CELL_W, CELL_H, QImage.Format_Grayscale8)
    masc = np.zeros((1000, CELL_H, CELL_W), dtype=np.uint8)
    for v in range(1000):
        pm.fill(0)
        p = QPainter(pm)
        p.setFont(FONTE)
        p.setPen(QColor(255, 255, 255))
        p.drawText(2, CELL_H - 3, str(v))
        p.end()
        buf = np.frombuffer(pm.constBits(), dtype=np.uint8)
        masc[v] = buf.reshape(CELL_H, pm.bytesPerLine())[:, :CELL_W]
    return cores, masc


def bench_mosaico(cores, masc):
    """Monta o quadro inteiro sem UM laco Python sobre celulas."""
    quadro = np.empty((FP_ROWS, CELL_H, FP_COLS, CELL_W, 3), dtype=np.uint8)
    ts = []
    for i in range(QUADROS):
        rot = (np.arange(FP_COLS) + i) % FP_COLS
        idx = IDX[:, rot]
        bid = BID[:, rot]
        t0 = time.perf_counter()
        # fundos: (ROWS, COLS) -> (ROWS, CELL_H, COLS, CELL_W, 3) de uma vez
        quadro[:] = cores[idx].transpose(0, 2, 1, 3, 4)
        # texto: mascara por valor, aplicada vetorizada
        m = masc[bid].transpose(0, 2, 1, 3)[..., None]
        np.copyto(quadro, np.uint8(230), where=m > 127)
        plano = quadro.transpose(0, 1, 2, 3, 4).reshape(FP_ROWS * CELL_H, FP_COLS * CELL_W, 3)
        img = QImage(plano.tobytes(), FP_COLS * CELL_W, FP_ROWS * CELL_H, QImage.Format_RGB888)
        ts.append((time.perf_counter() - t0) * 1000)
    return stats(ts)


# ------------------------------------------------------- 4. incremental / scroll
def bench_incremental():
    """So' a ultima barra muda a cada tick: rola o pixmap e pinta 60 celulas."""
    pix = QPixmap(W, H)
    pix.fill(QColor("#0d1117"))
    ts = []
    for i in range(QUADROS):
        t0 = time.perf_counter()
        pix.scroll(-CELL_W, 0, pix.rect())  # rola o backing store 1 coluna
        p = QPainter(pix)
        p.setFont(FONTE)
        x = W - CELL_W
        cc = i % FP_COLS
        for r in range(FP_ROWS):  # 60 celulas, nao 2.400
            y = r * CELL_H
            p.fillRect(x, y, CELL_W - 1, CELL_H - 1, PALETA[IDX[r, cc]])
            p.setPen(TXT)
            p.drawText(x + 2, y + CELL_H - 3, S_BID[r][cc])
            p.drawText(x + 24, y + CELL_H - 3, S_ASK[r][cc])
        p.end()
        ts.append((time.perf_counter() - t0) * 1000)
    return stats(ts)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    print(f"# PySide6 {__import__('PySide6').__version__} / python {sys.version.split()[0]} / quadro {FP_ROWS}x{FP_COLS}")
    print(linha("1. PISO PYTHON (7200 no-op)", bench_piso()))
    print(linha("2. drawRects em lote (so fundos)", bench_rects_lote()))
    t0 = time.perf_counter()
    cores, masc = montar_atlas()
    print(f"   (atlas de 1000 tiles pre-renderizado em {(time.perf_counter() - t0):.2f}s, uma vez so)")
    print(linha("3. MOSAICO NUMPY quadro inteiro", bench_mosaico(cores, masc)))
    print(linha("4. INCREMENTAL scroll + 1 coluna", bench_incremental()))
