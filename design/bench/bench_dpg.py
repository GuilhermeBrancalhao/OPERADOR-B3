"""Benchmark Dear PyGui 2.x sob a MESMA carga (60x40 = 2.400 celulas).

DPG e' modo RETIDO: cada retangulo e cada numero e' um item persistente.
Atualizar o quadro = 7.200 chamadas configure_item(). Nao ha' equivalente ao
truque de scroll do backing store do Qt: a drawlist nao rola, so' se
reposiciona item a item.

Tambem mede o ponto forte do DPG: textura dinamica (heatmap), que e' upload
direto de buffer para a GPU.

Roda: C:/bv/Scripts/python.exe bench_dpg.py
"""

import sys
import time

import numpy as np
import dearpygui.dearpygui as dpg

from workload import (
    CELL_H,
    CELL_W,
    FP_COLS,
    FP_ROWS,
    HM_COLS,
    HM_ROWS,
    gerar_footprint,
    gerar_heatmap,
    linha,
    rolar_heatmap,
    stats,
)

QUADROS = 200
BID, ASK, DN = gerar_footprint()
IDX = (DN * 31).astype(np.int32)
PALETA = [(int(20 + 200 * t), int(40 + 60 * abs(0.5 - t)), int(220 - 190 * t), 255) for t in np.linspace(0, 1, 32)]
S_BID = [[str(int(v)) for v in row] for row in BID]
S_ASK = [[str(int(v)) for v in row] for row in ASK]

dpg.create_context()
dpg.create_viewport(title="bench", width=FP_COLS * CELL_W + 20, height=FP_ROWS * CELL_H + 60, vsync=False)
dpg.setup_dearpygui()

rects, txt_b, txt_a = [], [], []
with dpg.window(tag="w"):
    with dpg.drawlist(width=FP_COLS * CELL_W, height=FP_ROWS * CELL_H):
        for c in range(FP_COLS):
            for r in range(FP_ROWS):
                x, y = c * CELL_W, r * CELL_H
                rects.append(
                    dpg.draw_rectangle(
                        (x, y), (x + CELL_W - 1, y + CELL_H - 1), fill=PALETA[IDX[r, c]], color=PALETA[IDX[r, c]]
                    )
                )
                txt_b.append(dpg.draw_text((x + 2, y), S_BID[r][c], size=11))
                txt_a.append(dpg.draw_text((x + 24, y), S_ASK[r][c], size=11))

dpg.show_viewport()
try:
    dpg.set_viewport_vsync(False)
except Exception:
    pass

# ------------------------------------------------------- custo de render puro
for _ in range(20):
    dpg.render_dearpygui_frame()

ts_render = []
for _ in range(QUADROS):
    t0 = time.perf_counter()
    dpg.render_dearpygui_frame()
    ts_render.append((time.perf_counter() - t0) * 1000)

# ------------------------------- custo de ATUALIZAR o quadro (7.200 configure)
ts_full = []
n = len(rects)
for i in range(QUADROS):
    t0 = time.perf_counter()
    for k in range(n):
        r, c = k % FP_ROWS, (k // FP_ROWS + i) % FP_COLS
        dpg.configure_item(rects[k], fill=PALETA[IDX[r, c]])
        dpg.configure_item(txt_b[k], text=S_BID[r][c])
        dpg.configure_item(txt_a[k], text=S_ASK[r][c])
    dpg.render_dearpygui_frame()
    ts_full.append((time.perf_counter() - t0) * 1000)

# --------------------------------- so' a coluna nova (60 celulas) — melhor caso
ts_inc = []
for i in range(QUADROS):
    t0 = time.perf_counter()
    for r in range(FP_ROWS):
        k = r  # primeira coluna de itens
        c = i % FP_COLS
        dpg.configure_item(rects[k], fill=PALETA[IDX[r, c]])
        dpg.configure_item(txt_b[k], text=S_BID[r][c])
        dpg.configure_item(txt_a[k], text=S_ASK[r][c])
    dpg.render_dearpygui_frame()
    ts_inc.append((time.perf_counter() - t0) * 1000)

print(f"# Dear PyGui {dpg.get_dearpygui_version()} / python {sys.version.split()[0]} / quadro {FP_ROWS}x{FP_COLS}")
print(linha("DPG render sem atualizar nada", stats(ts_render)))
print(linha("DPG quadro cheio (7200 configure)", stats(ts_full)))
print(linha("DPG so coluna nova (180 configure)", stats(ts_inc)))

# ------------------------------------------------------------ textura dinamica
hm = gerar_heatmap()
rng = np.random.default_rng(3)
buf = np.zeros(HM_ROWS * HM_COLS * 4, dtype=np.float32)
with dpg.texture_registry():
    tex = dpg.add_raw_texture(width=HM_COLS, height=HM_ROWS, default_value=buf, format=dpg.mvFormat_Float_rgba)
with dpg.window(tag="w2"):
    dpg.add_image(tex)

ts_hm = []
for _ in range(200):
    rolar_heatmap(hm, rng)
    t0 = time.perf_counter()
    rgba = np.repeat(hm.reshape(-1, 1), 4, axis=1)
    rgba[:, 3] = 1.0
    buf[:] = rgba.ravel()
    dpg.render_dearpygui_frame()
    ts_hm.append((time.perf_counter() - t0) * 1000)
print(linha(f"DPG textura dinamica {HM_ROWS}x{HM_COLS}", stats(ts_hm)))

dpg.destroy_context()
