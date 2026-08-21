"""Benchmark real: CSV puro vs CSV+gzip vs Parquet(snappy) para ~1M eventos
sinteticos de trade, no formato de campos que o Gravador vai persistir.

Roda uma vez, standalone, fora da suite de testes (nao e teste automatizado
-- e um experimento para decidir o formato de arquivo do gravador).
"""
import csv
import gzip
import io
import os
import random
import time
from pathlib import Path

N = 1_000_000
OUT = Path(__file__).parent

random.seed(42)

def gerar_linhas():
    ts = 0
    for i in range(N):
        ts += random.randint(1, 5_000_000)
        preco = 500000 + random.randint(-200, 200)
        qty = random.randint(1, 50)
        side = "BUY" if random.random() < 0.5 else "SELL"
        yield (ts, "WDOV26", preco, qty, side, f"T{i}", "B1", "S1")

HEADER = ["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id", "buyer_broker", "seller_broker"]

linhas = list(gerar_linhas())
print(f"gerados {len(linhas)} eventos sinteticos")

resultados = {}

# --- CSV puro ---
p_csv = OUT / "bench_trades.csv"
t0 = time.perf_counter()
with p_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    w.writerows(linhas)
t_write_csv = time.perf_counter() - t0
tam_csv = p_csv.stat().st_size

t0 = time.perf_counter()
with p_csv.open("r", newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    next(r)
    n = 0
    soma = 0
    for row in r:
        n += 1
        soma += int(row[2])
t_read_csv = time.perf_counter() - t0
resultados["csv"] = (tam_csv, t_write_csv, t_read_csv, n, soma)

# --- CSV + gzip ---
p_gz = OUT / "bench_trades.csv.gz"
t0 = time.perf_counter()
with gzip.open(p_gz, "wt", newline="", encoding="utf-8", compresslevel=6) as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    w.writerows(linhas)
t_write_gz = time.perf_counter() - t0
tam_gz = p_gz.stat().st_size

t0 = time.perf_counter()
with gzip.open(p_gz, "rt", newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    next(r)
    n = 0
    soma = 0
    for row in r:
        n += 1
        soma += int(row[2])
t_read_gz = time.perf_counter() - t0
resultados["csv_gzip"] = (tam_gz, t_write_gz, t_read_gz, n, soma)

# --- Parquet (pyarrow, snappy) ---
import pyarrow as pa
import pyarrow.parquet as pq

cols = list(zip(*linhas))
tabela = pa.table({
    "timestamp_ns": pa.array(cols[0], type=pa.int64()),
    "symbol": pa.array(cols[1], type=pa.string()),
    "price": pa.array(cols[2], type=pa.int64()),
    "qty": pa.array(cols[3], type=pa.int64()),
    "side_agressor": pa.array(cols[4], type=pa.string()),
    "trade_id": pa.array(cols[5], type=pa.string()),
    "buyer_broker": pa.array(cols[6], type=pa.string()),
    "seller_broker": pa.array(cols[7], type=pa.string()),
})

p_pq = OUT / "bench_trades.parquet"
t0 = time.perf_counter()
pq.write_table(tabela, p_pq, compression="snappy")
t_write_pq = time.perf_counter() - t0
tam_pq = p_pq.stat().st_size

t0 = time.perf_counter()
tab2 = pq.read_table(p_pq)
n = tab2.num_rows
soma = pa.compute.sum(tab2.column("price")).as_py()
t_read_pq = time.perf_counter() - t0
resultados["parquet_snappy"] = (tam_pq, t_write_pq, t_read_pq, n, soma)

print()
print(f"{'formato':<16} {'tamanho(MB)':>12} {'escrita(s)':>12} {'leitura(s)':>12} {'n':>10}")
for nome, (tam, tw, tr, n, soma) in resultados.items():
    print(f"{nome:<16} {tam/1024/1024:>12.2f} {tw:>12.3f} {tr:>12.3f} {n:>10}")

# limpeza
for p in (p_csv, p_gz, p_pq):
    p.unlink(missing_ok=True)
