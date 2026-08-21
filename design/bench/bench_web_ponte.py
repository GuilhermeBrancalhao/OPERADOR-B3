"""Custo da PONTE Python -> navegador (a opcao web).

Na opcao web o desenho nao custa nada em Python: quem pinta e' o canvas do
navegador. O custo migra para a ponte. Este script mede a ponte REAL
(websocket em localhost), nao um palpite:

  - quadro de DOM   : 40 niveis x 6 campos, enviado a cada tick
  - quadro de footprint (delta) : 60 celulas da barra corrente
  - snapshot cheio de footprint : 2.400 celulas (so' no (re)conectar)

Mede, para cada um: bytes por mensagem, mensagens/s sustentadas e latencia
ida-e-volta (round-trip) em localhost — o piso de latencia que qualquer
arquitetura web paga por atualizacao.

Roda: C:/bv/Scripts/python.exe bench_web_ponte.py
"""

import asyncio
import struct
import time

import numpy as np
import orjson
import websockets

from workload import FP_COLS, FP_ROWS, gerar_footprint, linha, stats

BID, ASK, DN = gerar_footprint()
N_MSG = 3000
PORTA = 8799


def quadro_dom_json(i):
    return orjson.dumps(
        {
            "t": "dom",
            "ts": i,
            "l": [
                {
                    "p": 5432.5 + n * 0.5,
                    "bq": int(BID[n % FP_ROWS, i % FP_COLS]),
                    "aq": int(ASK[n % FP_ROWS, i % FP_COLS]),
                    "bo": n,
                    "ao": n,
                    "d": int(BID[n % FP_ROWS, i % FP_COLS]) - int(ASK[n % FP_ROWS, i % FP_COLS]),
                }
                for n in range(40)
            ],
        }
    )


def quadro_dom_bin(i):
    """Mesmo conteudo, layout binario: header + 40 x (float32 + 5 x int32)."""
    col = i % FP_COLS
    b = BID[:40, col].astype(np.int32)
    a = ASK[:40, col].astype(np.int32)
    corpo = np.empty((40, 6), dtype=np.int32)
    corpo[:, 0] = (np.arange(40) * 5 + 54325).astype(np.int32)
    corpo[:, 1] = b
    corpo[:, 2] = a
    corpo[:, 3] = np.arange(40)
    corpo[:, 4] = np.arange(40)
    corpo[:, 5] = b - a
    return struct.pack("<BI", 1, i) + corpo.tobytes()


def quadro_fp_delta_bin(i):
    col = i % FP_COLS
    corpo = np.empty((FP_ROWS, 2), dtype=np.int32)
    corpo[:, 0] = BID[:, col]
    corpo[:, 1] = ASK[:, col]
    return struct.pack("<BI", 2, i) + corpo.tobytes()


def snapshot_fp_bin():
    return struct.pack("<BI", 3, 0) + np.stack([BID, ASK], axis=-1).astype(np.int32).tobytes()


async def rodar(gerar, nome, n=N_MSG):
    recebidas = []
    rt = []

    async def handler(ws):
        async for msg in ws:
            recebidas.append(len(msg))
            await ws.send(b"a")  # ack, para medir ida-e-volta

    async with websockets.serve(handler, "127.0.0.1", PORTA):
        async with websockets.connect(f"ws://127.0.0.1:{PORTA}") as cli:
            await cli.send(gerar(0))
            await cli.recv()
            t_ini = time.perf_counter()
            for i in range(n):
                t0 = time.perf_counter()
                await cli.send(gerar(i))
                await cli.recv()
                rt.append((time.perf_counter() - t0) * 1000)
            wall = time.perf_counter() - t_ini
    s = stats(rt)
    tam = recebidas[-1]
    print(linha(nome, s) + f"   {tam:>7} B/msg   {n / wall:8.0f} msg/s")
    return s


async def main():
    print(f"# ponte websocket localhost / websockets {websockets.__version__}")
    print("# 'p50' aqui e' LATENCIA ida-e-volta por atualizacao, nao tempo de quadro")
    await rodar(quadro_dom_json, "DOM 40x6 JSON")
    await rodar(quadro_dom_bin, "DOM 40x6 binario")
    await rodar(quadro_fp_delta_bin, "footprint delta (60 cel) bin")
    await rodar(lambda i: snapshot_fp_bin(), "footprint snapshot 2400 cel", n=500)

    # custo de SERIALIZAR sozinho (sem rede) — o que o motor paga por tick
    for nome, fn in (("serializar DOM JSON", quadro_dom_json), ("serializar DOM binario", quadro_dom_bin)):
        ts = []
        for i in range(5000):
            t0 = time.perf_counter()
            fn(i)
            ts.append((time.perf_counter() - t0) * 1000)
        print(linha(nome, stats(ts)))


asyncio.run(main())
