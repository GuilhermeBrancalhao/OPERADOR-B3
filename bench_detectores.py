"""Micro-benchmark A/B do `DetectorAbsorcao` — implementacao antiga vs. nova.

Motivo: a critica R1 (`criticas/nucleo_r1.md`, secao "UNICO MAIOR GAP") mediu
42 trades/s no `DetectorAbsorcao` contra uma barra de 10.000 trades/s. O custo
era quadratico: a cada trade a implementacao antiga refazia a janela inteira
(uma list comprehension de expiracao + max + min + duas somas = 5 varreduras
completas). A 10.000 trades/s a janela de 5s guarda 50.000 trades.

Este script roda o MESMO tape sintetico pelas duas implementacoes. A antiga
esta copiada VERBATIM aqui embaixo (`DetectorAbsorcaoAntigo`) para que a
comparacao continue reproduzivel depois que o arquivo de producao mudou.

Tape do pior caso de proposito:
  - preco oscilando dentro de 1 tick  -> o teste de deslocamento NUNCA
    curto-circuita, entao as somas de volume sempre rodam;
  - 10.000 trades/s (100.000 ns entre trades) -> janela de 5s cheia com
    50.000 trades, exatamente o cenario de pico da barra.

Uso:
    python bench_detectores.py                 # padrao: 100k novo, 20k antigo
    python bench_detectores.py --n 100000 --n-antigo 20000
    python bench_detectores.py --escala        # tabela de escalonamento
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.detectores import ConfigAbsorcao, Deteccao, DetectorAbsorcao, TipoDeteccao

SYMBOL = "WDOFUT"
INTERVALO_NS = 100_000  # 10.000 trades/s
PRECO_BASE = 10_000


# ---------------------------------------------------------------------------
# Implementacao ANTIGA, copiada verbatim de detectores.py antes do conserto.
# Nao editar: existe so para o A/B continuar honesto.
# ---------------------------------------------------------------------------
class DetectorAbsorcaoAntigo:
    def __init__(self, symbol: str, config: ConfigAbsorcao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigAbsorcao()
        self._trades: list[Trade] = []

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        self._trades.append(trade)
        limite = trade.timestamp_ns - cfg.janela_ns
        self._trades = [t for t in self._trades if t.timestamp_ns >= limite]

        precos = [t.price for t in self._trades]
        deslocamento = max(precos) - min(precos)
        if deslocamento > cfg.deslocamento_maximo_ticks:
            return None

        volume_buy = sum(t.qty for t in self._trades if t.side_agressor.name == "BUY")
        volume_sell = sum(t.qty for t in self._trades if t.side_agressor.name == "SELL")

        if volume_sell >= cfg.volume_minimo and volume_sell > volume_buy:
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.ABSORCAO,
                side=Side.BUY,
                price=trade.price,
                confianca=1.0,
                evidencia={
                    "volume_agressao_dominante": volume_sell,
                    "volume_lado_oposto": volume_buy,
                    "deslocamento_ticks": deslocamento,
                    "n_trades_janela": len(self._trades),
                },
            )
        if volume_buy >= cfg.volume_minimo and volume_buy > volume_sell:
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.ABSORCAO,
                side=Side.SELL,
                price=trade.price,
                confianca=1.0,
                evidencia={
                    "volume_agressao_dominante": volume_buy,
                    "volume_lado_oposto": volume_sell,
                    "deslocamento_ticks": deslocamento,
                    "n_trades_janela": len(self._trades),
                },
            )
        return None


# ---------------------------------------------------------------------------
# Tape
# ---------------------------------------------------------------------------
def montar_tape(n: int, seed: int = 7) -> list[Trade]:
    """Tape lateral: preco preso em 2 ticks, vies vendedor leve, qty 1..10."""
    rng = random.Random(seed)
    tape: list[Trade] = []
    ts = 0
    for i in range(n):
        preco = PRECO_BASE + rng.randint(0, 1)
        lado = AgressorSide.SELL if rng.random() < 0.55 else AgressorSide.BUY
        tape.append(
            Trade(
                timestamp_ns=ts,
                symbol=SYMBOL,
                price=preco,
                qty=rng.randint(1, 10),
                side_agressor=lado,
                trade_id=f"t{i}",
            )
        )
        ts += INTERVALO_NS
    return tape


@dataclass
class Resultado:
    nome: str
    n: int
    segundos: float
    deteccoes: int

    @property
    def trades_s(self) -> float:
        return self.n / self.segundos if self.segundos else float("inf")

    @property
    def us_trade(self) -> float:
        return self.segundos * 1e6 / self.n if self.n else 0.0


def medir(nome: str, detector, tape: list[Trade]) -> Resultado:
    deteccoes = 0
    inicio = time.perf_counter()
    for trade in tape:
        if detector.ao_trade(trade) is not None:
            deteccoes += 1
    fim = time.perf_counter()
    return Resultado(nome, len(tape), fim - inicio, deteccoes)


def linha(r: Resultado) -> str:
    return (
        f"{r.nome:<26} n={r.n:>7,}  {r.segundos:>8.3f}s  "
        f"{r.trades_s:>12,.0f} trades/s  {r.us_trade:>9.2f} us/trade  "
        f"deteccoes={r.deteccoes:>7,} ({100.0 * r.deteccoes / r.n:5.1f}%)"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100_000, help="trades para a implementacao NOVA")
    ap.add_argument(
        "--n-antigo",
        type=int,
        default=20_000,
        help="trades para a implementacao ANTIGA (menor: e quadratica)",
    )
    ap.add_argument("--escala", action="store_true", help="tabela de escalonamento")
    args = ap.parse_args()

    cfg = ConfigAbsorcao()  # config de fabrica: janela 5s, volume_minimo 300
    print(
        f"janela={cfg.janela_ns / 1e9:.0f}s  taxa={1e9 / INTERVALO_NS:,.0f} trades/s  "
        f"-> janela cheia = {int(cfg.janela_ns / INTERVALO_NS):,} trades\n"
    )

    if args.escala:
        print("Escalonamento (mesmo tape, N crescente):")
        for n in (2_000, 5_000, 10_000, 20_000):
            tape = montar_tape(n)
            print("  " + linha(medir("ANTIGO", DetectorAbsorcaoAntigo(SYMBOL, cfg), tape)))
            print("  " + linha(medir("NOVO", DetectorAbsorcao(SYMBOL, cfg), tape)))
            print()
        return

    tape_antigo = montar_tape(args.n_antigo)
    print(linha(medir("ANTIGO (quadratico)", DetectorAbsorcaoAntigo(SYMBOL, cfg), tape_antigo)))

    tape_novo = montar_tape(args.n)
    print(linha(medir("NOVO (deque O(1))", DetectorAbsorcao(SYMBOL, cfg), tape_novo)))


if __name__ == "__main__":
    main()
