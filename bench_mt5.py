"""Benchmark descartavel da borda MT5: quanto tape o adaptador sustenta.

Mede `AdaptadorMT5._puxar_ticks` — o caminho que o defeito da R3 travava —
contra um mock que honra `de` (em segundos) e `count` exatamente como a API
real, com o tape sendo revelado aos poucos como num pregao.

O numero que importa nao e "ticks/s de pico do processo": e o CUSTO DE CPU
por segundo de tape. `date_from` tem granularidade de segundo, entao todo
poll re-recebe o segundo corrente inteiro; se a varredura desse lote fosse
proporcional ao segundo em vez de ao que e novo, o custo cresceria com o
quadrado do volume e o adaptador comeria o nucleo no pico.

Uso:  python bench_mt5.py
"""
from __future__ import annotations

import time

import numpy as np

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import WDO_GRID
from fluxopro.dados.mt5 import AdaptadorMT5, _CursorTick, _RelogioServidor

ALVO_PICO_TICKS_S = 10_000  # WDO em dia agitado (barra do projeto)
POLLS_POR_S = 20            # intervalo_poll_s = 0.05 de fabrica

_TICK_DTYPE = [
    ("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"),
    ("volume", "i8"), ("time_msc", "i8"), ("flags", "i4"), ("volume_real", "f8"),
]


class _MockMT5:
    """`copy_ticks_from` fiel e BARATO — busca binaria, nao varredura, para
    que o custo medido seja o do adaptador e nao o do mock."""

    COPY_TICKS_ALL = 0
    TICK_FLAG_BUY = 1 << 5
    TICK_FLAG_SELL = 1 << 6

    def __init__(self, tape):
        self.tape = tape
        self.msc = tape["time_msc"]
        self.visivel = len(tape)
        self.chamadas = 0

    def copy_ticks_from(self, symbol, de, count, flags):
        self.chamadas += 1
        inicio = int(np.searchsorted(self.msc, de * 1000, side="left"))
        return self.tape[inicio : min(inicio + count, self.visivel)]

    def symbol_info_tick(self, symbol):
        return None


def _tape(n_seg: int, ticks_por_seg: int, base_msc: int = 1_000_000) -> np.ndarray:
    linhas = []
    for i in range(n_seg * ticks_por_seg):
        seg, dentro = divmod(i, ticks_por_seg)
        msc = base_msc + seg * 1000 + (dentro * 1000) // ticks_por_seg
        linhas.append((msc // 1000, 4999.5, 5000.5, 5000.5, 1, msc, 1 << 5, 0.0))
    return np.array(linhas, dtype=_TICK_DTYPE)


def medir(ticks_por_seg: int, n_seg: int = 5) -> tuple[int, float]:
    tape = _tape(n_seg, ticks_por_seg)
    mock = _MockMT5(tape)
    adaptador = AdaptadorMT5(
        Barramento(), "WDOV26", WDO_GRID, mt5_module=mock, intervalo_poll_s=0.05
    )
    cursor = _CursorTick()
    entregues = 0
    n_polls = n_seg * POLLS_POR_S

    t0 = time.perf_counter()
    for p in range(1, n_polls + 1):
        # o tape "chega" proporcional ao tempo simulado
        mock.visivel = (len(tape) * p) // n_polls
        trades, cursor, _falhas = adaptador._puxar_ticks(mock, cursor)
        entregues += len(trades)
    mock.visivel = len(tape)
    for _ in range(3):
        trades, cursor, _falhas = adaptador._puxar_ticks(mock, cursor)
        entregues += len(trades)
    return entregues, time.perf_counter() - t0



# ----------------------------------------------------------------------
# Estagio 2: o estimador de offset do relogio (R4 A.4)
# ----------------------------------------------------------------------
# O relogio de MAXIMO PURO da onda 7 era um `if` e uma atribuicao. O que o
# substituiu — maximo sobre janela deslizante + deteccao de regressao — e um
# deque monotonico com poda por idade. `observar` roda uma vez POR POLL (20x
# por segundo), nunca por tick, entao o custo absoluto e irrelevante para a
# vazao; mede-se assim mesmo porque "irrelevante" e uma afirmacao que tem de
# ter numero. `MaximoPuro` abaixo e o estimador ANTIGO, literal, para o
# antes/depois ficar na mesma maquina e na mesma execucao.


class _MaximoPuro:
    """O estimador da onda 7, para comparacao. NAO usar em producao: e a
    catraca do achado A.4 da R4 (uma regressao do servidor inflava o offset
    para sempre)."""

    __slots__ = ("_offset_ns", "_sincronizado", "_ultimo_ns")

    def __init__(self):
        self._offset_ns = 0
        self._sincronizado = False
        self._ultimo_ns = 0

    def observar(self, servidor_ns):
        estimativa = servidor_ns - time.time_ns()
        if not self._sincronizado or estimativa > self._offset_ns:
            self._offset_ns = estimativa
        self._sincronizado = True
        if servidor_ns > self._ultimo_ns:
            self._ultimo_ns = servidor_ns

    def agora_ns(self):
        derivado = time.time_ns() + self._offset_ns
        if derivado <= self._ultimo_ns:
            derivado = self._ultimo_ns + 1
        self._ultimo_ns = derivado
        return derivado


def _exercitar_relogio(relogio, n_polls, passo_ns, parados=0):
    """`n_polls` observacoes com o tape andando `passo_ns` por poll, e
    `parados` re-observacoes do mesmo tick (tape parado) intercaladas."""
    base = time.time_ns() + 3 * 3600 * 10**9
    t0 = time.perf_counter()
    servidor = base
    for i in range(n_polls):
        servidor += passo_ns
        relogio.observar(servidor)
        for _ in range(parados):
            relogio.observar(servidor)
        relogio.agora_ns()
    return time.perf_counter() - t0


def bench_relogio() -> None:
    print("\n\nRelogio de servidor — custo de `observar` + `agora_ns` por poll")
    print("(roda 1x por poll = 20x/s; NAO por tick)\n")
    n = 200_000
    print(f'{"estimador":>28}  {"regime":>22}  {"CPU":>9}  {"por poll":>10}')
    for rotulo, fabrica in (
        ("maximo puro (onda 7)", _MaximoPuro),
        ("janela + deteccao (atual)", _RelogioServidor),
    ):
        for regime, parados in (("tape andando", 0), ("tape parado 4:1", 4)):
            dt = _exercitar_relogio(fabrica(), n, 50_000_000, parados=parados)
            print(f"{rotulo:>28}  {regime:>22}  {dt:>8.3f}s  {dt / n * 1e9:>8.0f} ns")


def main() -> None:
    print("Borda MT5 — _puxar_ticks com mock honesto (de em segundos, count respeitado)")
    print(f"{POLLS_POR_S} polls/s, 5 s de tape por linha\n")
    print(f'{"tape":>8}  {"entregues":>10}  {"perdidos":>8}  {"CPU":>7}  '
          f'{"capacidade":>14}  {"custo/1s de tape":>16}')
    for tps in (1_000, 3_000, 5_000, 10_000, 20_000, 50_000):
        n_seg = 5
        entregues, dt = medir(tps, n_seg)
        total = tps * n_seg
        print(f"{tps:>8,}  {entregues:>10,}  {total-entregues:>8,}  {dt:>6.3f}s  "
              f"{entregues/dt:>12,.0f}/s  {dt/n_seg*100:>15.1f}%")
    print(f"\nbarra do projeto: {ALVO_PICO_TICKS_S:,} ticks/s de pico")
    bench_relogio()


if __name__ == "__main__":
    main()
