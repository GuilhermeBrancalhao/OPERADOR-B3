"""Sondas R3 — parte 3. Uso: python .mut/sonda3_r3.py <letra>"""
from __future__ import annotations
import random, sys, tempfile
from pathlib import Path

from fluxopro.analytics.footprint import ConfigFootprint, Footprint
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.gravacao.gravador import Gravador
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao

SYMBOL = "WDOV26"
DIA_NS = 1_755_000_000_000_000_000  # 2025-08-12, um dia util qualquer


def sonda_j():
    """Corolario do defeito de relogio: uma GRAVACAO feita pelo AdaptadorMT5
    e IMPOSSIVEL de reproduzir na ordem certa, porque trade e book foram
    carimbados por relogios diferentes e o leitor ordena pelo carimbo."""
    print("J. Gravacao com os dois relogios do AdaptadorMT5 -> replay reordenado\n")
    tmp = Path(tempfile.mkdtemp(prefix="r3_skew_"))
    bar = Barramento()
    grav = Gravador(bar, saida_dir=tmp); grav.iniciar()
    OFFSET = 3 * 3_600_000_000_000  # servidor MT5 em GMT+3
    ordem_vivo = []
    ts = DIA_NS
    for i in range(20):
        # ordem REAL de chegada na fila da thread de borda: trade, depois book
        t = Trade(ts + OFFSET, SYMBOL, 5000 + i, 1, AgressorSide.BUY, f"t{i}")
        b = BookSnapshot(ts, SYMBOL, (BookLevel(4999 + i, 10, 1),), (BookLevel(5001 + i, 10, 1),))
        bar.publicar(t); ordem_vivo.append(("T", i))
        bar.publicar(b); ordem_vivo.append(("B", i))
        ts += 100_000_000
    grav.parar()

    cat = Catalogo(tmp); cat.escanear()
    entradas = cat.listar()
    print(f"   dias gravados pelo Gravador: {[e.data.isoformat() for e in entradas]}")
    print("   (o mesmo minuto de mercado virou DOIS dias no disco: o trade caiu no")
    print("    dia do relogio do servidor, o book no dia do relogio local)\n")

    ordem_replay = []
    bar2 = Barramento()
    bar2.assinar(Trade, lambda e: ordem_replay.append(("T", e.price - 5000)))
    bar2.assinar(BookSnapshot, lambda e: ordem_replay.append(("B", e.bids[0].price - 4999)))
    for ent in entradas:
        AdaptadorLeitorGravacao(bar2, ent, catalogo=cat).iniciar()

    print(f"   ordem ao vivo   (10 primeiros): {ordem_vivo[:10]}")
    print(f"   ordem no replay (10 primeiros): {ordem_replay[:10]}")
    print(f"\n   iguais? {'SIM' if ordem_vivo == ordem_replay else 'NAO — o replay NAO reproduz o vivo'}")
    if ordem_vivo != ordem_replay:
        i = next(k for k in range(min(len(ordem_vivo), len(ordem_replay)))
                 if ordem_vivo[k] != ordem_replay[k])
        print(f"   1a divergencia no indice {i}: vivo={ordem_vivo[i]} replay={ordem_replay[i]}")


def sonda_i2():
    """Footprint: taxa de marcacao do imbalance por DENSIDADE do candle."""
    print("I2. Footprint — imbalance diagonal por densidade do candle\n")
    print(f"{'trades':>8} {'niveis':>7} {'imb_compra':>12} {'imb_venda':>11} {'% dos niveis':>13}")
    rng = random.Random(5)
    for n_trades, faixa in ((40, 20), (100, 20), (300, 20), (1000, 20), (60, 40), (200, 40)):
        fp = Footprint(ConfigFootprint())
        precos = set()
        for i in range(n_trades):
            p = 5000 + rng.randint(-faixa // 2, faixa // 2)
            precos.add(p)
            fp.registrar_trade(Trade(i * 10**6, SYMBOL, p, rng.randint(1, 5),
                                     AgressorSide.BUY if rng.random() < 0.5 else AgressorSide.SELL,
                                     f"f{i}"))
        c = fp.niveis_imbalance_compra(); v = fp.niveis_imbalance_venda()
        pct = 100 * len(set(c) | set(v)) / max(1, len(precos))
        print(f"{n_trades:>8,} {len(precos):>7} {len(c):>12} {len(v):>11} {pct:>12.1f}%")
    print("\n   O default `qty_minima_imbalance=0` (footprint.py:57) nao filtra nada:")
    print("   `nivel.qty_comprador < 0` e sempre falso. Sobra so o `== 0`, e o ramo")
    print("   `qty_vizinho == 0 -> append` (linha 165) marca imbalance de razao")
    print("   INFINITA a partir de 1 lote contra 0. Quanto mais esparso o candle,")
    print("   mais a lista vira 'todo nivel que negociou'.")


if __name__ == "__main__":
    {"j": sonda_j, "i2": sonda_i2}[sys.argv[1]]()
