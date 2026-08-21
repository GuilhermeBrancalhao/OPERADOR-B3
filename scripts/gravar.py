#!/usr/bin/env python
"""CLI de gravação contínua: liga uma fonte (MT5 ao vivo ou o simulador
sintético) e o `Gravador`, publica tudo no mesmo `Barramento` e persiste em
disco. Com `--fonte simulador` funciona sem MT5 instalado nem corretora
conectada — é como o dono testa o pipeline inteiro (fonte -> gravador ->
catálogo -> leitor) no mesmo dia em que pediu, sem depender de pregão ao
vivo nem de credenciais de corretora.

Uso:
    python scripts/gravar.py --simbolo WDOV26 --saida dados/ --fonte simulador
    python scripts/gravar.py --simbolo WDOV26 --saida dados/ --fonte mt5
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookDelta, BookSnapshot, PriceGrid, Trade, WDO_GRID, WIN_GRID
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.eventos_captura import FalhaCaptura
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.gravacao.gravador import Gravador

_logger = logging.getLogger("scripts.gravar")


def _grid_para_simbolo(symbol: str) -> PriceGrid:
    prefixo = symbol[:3].upper()
    if prefixo == "WIN":
        return WIN_GRID
    return WDO_GRID


class _Contadores:
    """Assina o mesmo barramento só para imprimir contadores ao vivo — não
    interfere na gravação, é puramente observacional."""

    def __init__(self) -> None:
        self.trades = 0
        self.snapshots = 0
        self.deltas = 0
        self.falhas = 0
        self._lock = threading.Lock()

    def ligar(self, barramento: Barramento) -> None:
        barramento.assinar(Trade, self._on_trade)
        barramento.assinar(BookSnapshot, self._on_snapshot)
        barramento.assinar(BookDelta, self._on_delta)
        barramento.assinar(FalhaCaptura, self._on_falha)

    def _on_trade(self, _evento) -> None:
        with self._lock:
            self.trades += 1

    def _on_snapshot(self, _evento) -> None:
        with self._lock:
            self.snapshots += 1

    def _on_delta(self, _evento) -> None:
        with self._lock:
            self.deltas += 1

    def _on_falha(self, evento: FalhaCaptura) -> None:
        with self._lock:
            self.falhas += 1
        _logger.warning("FALHA DE CAPTURA: %s — %s", evento.tipo.value, evento.detalhe)

    def linha_status(self) -> str:
        with self._lock:
            return (
                f"trades={self.trades} snapshots={self.snapshots} "
                f"deltas={self.deltas} falhas={self.falhas}"
            )


def _construir_fonte(
    fonte: str, barramento: Barramento, simbolo: str, args: argparse.Namespace
) -> AdaptadorDados:
    if fonte == "simulador":
        _logger.info("fonte = simulador (sem MT5, sem corretora) — seed=%d", args.seed)
        return SimuladorWDO(
            barramento,
            seed=args.seed,
            symbol=simbolo,
            n_eventos=args.n_eventos_simulador,
            taxa_eventos_s=args.taxa_eventos_s,
        )
    if fonte == "mt5":
        from fluxopro.dados.mt5 import AdaptadorMT5

        _logger.info("fonte = MT5 ao vivo — simbolo=%s", simbolo)
        return AdaptadorMT5(
            barramento,
            symbol=simbolo,
            price_grid=_grid_para_simbolo(simbolo),
        )
    raise ValueError(f"fonte desconhecida: {fonte!r} (use 'mt5' ou 'simulador')")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grava fluxo de mercado em disco.")
    parser.add_argument("--simbolo", required=True, help="ex.: WDOV26, WINZ26")
    parser.add_argument("--saida", required=True, help="diretorio base de gravacao")
    parser.add_argument("--fonte", choices=["mt5", "simulador"], default="simulador")
    parser.add_argument("--seed", type=int, default=42, help="(simulador) seed determinístico")
    parser.add_argument(
        "--n-eventos-simulador", type=int, default=0, dest="n_eventos_simulador",
        help="(simulador) 0 = roda indefinidamente ate Ctrl+C",
    )
    parser.add_argument("--taxa-eventos-s", type=float, default=5.0, dest="taxa_eventos_s")
    parser.add_argument("--fsync-a-cada", type=int, default=200, dest="fsync_a_cada")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.n_eventos_simulador == 0 and args.fonte == "simulador":
        # SimuladorWDO precisa de um n finito; "indefinido" = um numero
        # muito grande, interrompido de verdade por Ctrl+C via parar().
        args.n_eventos_simulador = 10**9

    barramento = Barramento()
    gravador = Gravador(barramento, args.saida, fsync_a_cada=args.fsync_a_cada)
    gravador.iniciar()

    contadores = _Contadores()
    contadores.ligar(barramento)

    fonte = _construir_fonte(args.fonte, barramento, args.simbolo, args)

    parar_evt = threading.Event()

    def _handler_sinal(signum, frame) -> None:
        _logger.info("Ctrl+C recebido — encerrando com flush do gravador...")
        parar_evt.set()
        fonte.parar()

    signal.signal(signal.SIGINT, _handler_sinal)
    try:
        signal.signal(signal.SIGTERM, _handler_sinal)
    except (ValueError, AttributeError):
        pass  # SIGTERM pode nao existir/ser configuravel em algumas plataformas

    def _status_periodico() -> None:
        while not parar_evt.is_set():
            time.sleep(5.0)
            if not parar_evt.is_set():
                _logger.info("status: %s", contadores.linha_status())

    thread_status = threading.Thread(target=_status_periodico, daemon=True)
    thread_status.start()

    _logger.info(
        "iniciando gravacao: simbolo=%s saida=%s fonte=%s",
        args.simbolo, args.saida, args.fonte,
    )
    try:
        fonte.iniciar()  # bloqueia ate fonte.parar() ser chamado
    finally:
        parar_evt.set()
        gravador.parar()
        _logger.info("gravacao encerrada. total: %s", contadores.linha_status())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
