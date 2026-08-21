"""Benchmark PySide6 (QPainter imediato, QGraphicsScene retido, pyqtgraph).

Roda: C:/bv/Scripts/python.exe bench_qt.py
"""

import sys
import time

import numpy as np
from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

from workload import (
    CELL_H,
    CELL_W,
    DOM_COLS,
    DOM_ROWS,
    FP_COLS,
    FP_ROWS,
    gerar_footprint,
    gerar_heatmap,
    linha,
    rolar_heatmap,
    stats,
)

QUADROS = 400

BID, ASK, DN = gerar_footprint()
# paleta pre-alocada: 32 tons compra->venda. Alocar QColor por celula por quadro
# e' o erro classico que derruba o FPS, entao medimos a versao correta.
PALETA = [QColor(int(20 + 200 * t), int(40 + 60 * abs(0.5 - t)), int(220 - 190 * t)) for t in np.linspace(0, 1, 32)]
TXT = QColor("#e6edf3")
FONTE = QFont("Consolas", 8)

# strings pre-formatadas (o motor real formata so o que mudou; formatar 4.800
# floats por quadro em Python seria trapaca ao contrario)
S_BID = [[str(int(v)) for v in row] for row in BID]
S_ASK = [[str(int(v)) for v in row] for row in ASK]
IDX = (DN * 31).astype(np.int32)


def pintar_footprint(p: QPainter, desloc: int):
    """Um quadro completo de footprint: 2.400 rects + 4.800 textos."""
    p.setFont(FONTE)
    for c in range(FP_COLS):
        x = c * CELL_W
        cc = (c + desloc) % FP_COLS
        for r in range(FP_ROWS):
            y = r * CELL_H
            p.fillRect(x, y, CELL_W - 1, CELL_H - 1, PALETA[IDX[r, cc]])
            p.setPen(TXT)
            p.drawText(x + 2, y + CELL_H - 3, S_BID[r][cc])
            p.drawText(x + 24, y + CELL_H - 3, S_ASK[r][cc])


def pintar_dom(p: QPainter, desloc: int):
    p.setFont(FONTE)
    for r in range(DOM_ROWS):
        y = r * 16
        q = int(BID[r % FP_ROWS, desloc % FP_COLS])
        p.fillRect(0, y, 4 + q // 4, 15, PALETA[IDX[r % FP_ROWS, desloc % FP_COLS]])
        p.setPen(TXT)
        for c in range(DOM_COLS):
            p.drawText(120 * c + 4, y + 12, S_BID[r % FP_ROWS][(desloc + c) % FP_COLS])


# ---------------------------------------------------------------- offscreen
def bench_offscreen(fn, w, h, quadros=QUADROS):
    """Custo puro de rasterizacao, sem vsync e sem compositor."""
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    fn(p, 0)  # aquecimento (cache de glifos)
    p.end()
    ts = []
    for i in range(quadros):
        p = QPainter(img)
        t0 = time.perf_counter()
        fn(p, i)
        p.end()
        ts.append((time.perf_counter() - t0) * 1000)
    return stats(ts)


# ---------------------------------------------------------------- janela real
class JanelaFootprint(QWidget):
    """Widget real na tela, repintando o quadro inteiro o mais rapido possivel."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(FP_COLS * CELL_W, FP_ROWS * CELL_H)
        self.i = 0
        self.ts = []
        self.et = QElapsedTimer()
        self.et.start()
        self.t = QTimer(self)
        self.t.setInterval(0)
        self.t.timeout.connect(self.update)
        self.t.start()

    def paintEvent(self, _):
        t0 = time.perf_counter()
        p = QPainter(self)
        pintar_footprint(p, self.i)
        p.end()
        dt = (time.perf_counter() - t0) * 1000
        if self.i > 20:  # descarta aquecimento
            self.ts.append(dt)
        self.i += 1
        if len(self.ts) >= QUADROS:
            self.t.stop()
            self.wall = self.et.elapsed()
            QApplication.instance().quit()


def bench_janela():
    w = JanelaFootprint()
    w.show()
    QApplication.instance().exec()
    s = stats(w.ts)
    # FPS REAL entregue (inclui compositor/vsync/entrega ao DWM)
    s["fps_entregue"] = w.i / (w.wall / 1000.0)
    return s


# ------------------------------------------------------- QGraphicsScene (retido)
def bench_scene():
    """Modo retido: 2.400 celulas viram 4.800 QGraphicsItem de texto.
    E' o caminho 'facil' — medimos para provar que e' o errado."""
    scn = QGraphicsScene(0, 0, FP_COLS * CELL_W, FP_ROWS * CELL_H)
    itens = []
    for c in range(FP_COLS):
        for r in range(FP_ROWS):
            it = QGraphicsSimpleTextItem(S_BID[r][c])
            it.setFont(FONTE)
            it.setBrush(TXT)
            it.setPos(c * CELL_W + 2, r * CELL_H - 2)
            scn.addItem(it)
            itens.append(it)
    view = QGraphicsView(scn)
    view.setFixedSize(FP_COLS * CELL_W, FP_ROWS * CELL_H)
    view.show()
    QApplication.processEvents()
    img = QImage(FP_COLS * CELL_W, FP_ROWS * CELL_H, QImage.Format_RGB32)
    ts = []
    for i in range(120):  # menos quadros: e' lento
        t0 = time.perf_counter()
        for k, it in enumerate(itens):  # atualizar todos os valores
            it.setText(S_BID[k % FP_ROWS][(k + i) % FP_COLS])
        p = QPainter(img)
        scn.render(p)
        p.end()
        ts.append((time.perf_counter() - t0) * 1000)
    view.close()
    return stats(ts)


# ------------------------------------------------------------------- heatmap
def bench_heatmap():
    import pyqtgraph as pg

    hm = gerar_heatmap()
    rng = np.random.default_rng(3)
    plot = pg.PlotWidget()
    img = pg.ImageItem(hm)
    img.setLookupTable(np.stack([np.linspace(10, 255, 256)] * 3, axis=1).astype(np.uint8))
    plot.addItem(img)
    plot.setFixedSize(1200, 400)
    plot.show()
    QApplication.processEvents()
    ts = []
    for _ in range(300):
        rolar_heatmap(hm, rng)
        t0 = time.perf_counter()
        img.setImage(hm, autoLevels=False)
        QApplication.processEvents()
        ts.append((time.perf_counter() - t0) * 1000)
    plot.close()
    return stats(ts)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    print(f"# PySide6 {__import__('PySide6').__version__}  python {sys.version.split()[0]}")
    print(f"# footprint {FP_ROWS}x{FP_COLS} = {FP_ROWS * FP_COLS} celulas / 4800 textos por quadro")
    print(linha("QPainter offscreen FOOTPRINT", bench_offscreen(pintar_footprint, FP_COLS * CELL_W, FP_ROWS * CELL_H)))
    print(linha("QPainter offscreen DOM", bench_offscreen(pintar_dom, 800, DOM_ROWS * 16)))
    s = bench_janela()
    print(linha("QWidget JANELA REAL footprint", s) + f"   fps_entregue={s['fps_entregue']:.1f}")
    print(linha("QGraphicsScene (retido) footprint", bench_scene()))
    print(linha("pyqtgraph ImageItem heatmap 200x600", bench_heatmap()))
