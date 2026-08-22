#!/usr/bin/env python
"""Abre o painel grafico do FluxoPro sobre o MESMO pipeline do CLI.

    python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42
    python scripts/painel.py --fonte replay --arquivo dados/ --simbolo WDOV26
    python scripts/painel.py --fonte mt5 --simbolo WDOFUT

Reaproveita `scripts/operar.py` inteiro para linha de comando e montagem: os
mesmos limiares de calibracao, a mesma fonte de dados, o mesmo barramento. O
painel e um CONSUMIDOR a mais no barramento, nao um segundo caminho — se ele
mostrasse numero diferente do CLI, um dos dois estaria mentindo.

Modo SINAIS e sempre: este programa nao envia ordem para lugar nenhum.

A fonte roda numa thread propria porque `fonte.iniciar()` bloqueia ate o fim
do pregao (ver `operar.py`). A thread do Qt nunca toca no dominio: ela le o
retrato que `ui/ponte.py` deixou pronto.
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fluxopro.app.config import FonteDados  # noqa: E402
from fluxopro.app.montagem import FonteIndisponivelError, montar  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.janela import JanelaFluxo  # noqa: E402
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402
from scripts.operar import (  # noqa: E402
    config_de_args,
    construir_parser,
    opcoes_replay_de_args,
)

_logger = logging.getLogger("scripts.painel")

_DENSIDADES = {d.nome.lower(): d for d in tokens.DENSIDADES}

GIL_SWITCH_PADRAO = 0.001
"""Intervalo de troca de GIL, em segundos, SO neste processo.

Achado que so apareceu rodando o painel sob carga de verdade — nenhum
benchmark isolado o mostrava. A fonte roda numa thread propria, e o
simulador (como o replay em `--velocidade max`) e um produtor **sem espera
nenhuma**: ele nao faz I/O, entao segura o GIL continuamente. Com o padrao
do CPython (5 ms), a thread do Qt esperava ~12 ms para conseguir o GIL a
cada quadro.

O que denunciou foi separar `time.thread_time()` de `time.perf_counter()`:
o custo de CPU do quadro do DOM e **sub-milissegundo**, e os 12 ms eram
espera pura. (Com `time.process_time()` a conta some, porque ele soma a CPU
de TODAS as threads e o produtor entra na medida — cheguei a ler o numero
errado assim antes de trocar o relogio.)

Medido, 6 s de simulador inundando, janela de 1280x800:

| troca  | ingestao   | quadros/6s | DOM p95 |
|--------|------------|-----------|---------|
| 5 ms (padrao CPython) | 2.462 ev/s | 90 (15 fps) | 34,5 ms |
| **1 ms**              | **1.320 ev/s** | **230 (38 fps)** | **15,7 ms** |
| 0,5 ms                | 938 ev/s   | 360 (60 fps) | 9,3 ms |

E um dial, nao uma correcao: fluidez de tela e vazao de ingestao disputam a
mesma CPU. 1 ms fica no meio porque 1.320 ev/s continua acima do pico de um
instrumento no WDO, e porque com feed REAL o produtor e I/O-bound (o MT5
dorme entre consultas) e devolve o GIL sozinho — a disputa so e severa com
produtor sintetico ou replay acelerado, que e justamente quando o operador
esta olhando a tela.

Fica aqui e nao no nucleo de proposito: `scripts/operar.py` e headless e
existe para vazao, entao mexer no relogio do interpretador dele seria
cobrar um preco por um beneficio que ele nao usa."""


def _parser():
    p = construir_parser()
    g = p.add_argument_group("painel")
    g.add_argument(
        "--densidade",
        choices=sorted(_DENSIDADES),
        default="padrao",
        help="altura de linha da grade (§3.4)",
    )
    g.add_argument(
        "--sem-cor",
        action="store_true",
        dest="sem_cor",
        help=(
            "desliga o eixo direcional de cor; a direcao passa a viver so no "
            "sinal explicito e na posicao. E o modo de acessibilidade, e "
            "tambem o teste de que a tela nao depende de cor para ser lida."
        ),
    )
    g.add_argument(
        "--filtro-tape",
        type=int,
        default=0,
        dest="filtro_tape",
        help="lote minimo exibido no tape (0 = tudo)",
    )
    g.add_argument(
        "--gil-switch",
        type=float,
        default=GIL_SWITCH_PADRAO,
        dest="gil_switch",
        help=(
            f"intervalo de troca de GIL em segundos (default {GIL_SWITCH_PADRAO}). "
            "Menor = tela mais fluida e ingestao mais lenta; ver o modulo."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = config_de_args(args)
    if args.gil_switch > 0:
        sys.setswitchinterval(args.gil_switch)

    aplicacao = QApplication(sys.argv[:1])

    ponte: PonteFluxo | None = None

    try:
        montagem = montar(
            config,
            # Lambda, e nao `ponte.registrar_evento`, porque a `SessaoFluxo`
            # precisa dos callbacks no construtor e a ponte precisa do
            # barramento que `montar` cria — o no se desfaz adiando a busca
            # do metodo para a hora da chamada, que so acontece depois de
            # `iniciar()`. A alternativa (construir o barramento aqui e
            # passar pronto) poria a ponte a assinar ANTES da sessao, e a
            # ordem de prioridade do barramento e declarada e testada la.
            ao_sinal=lambda evento: ponte.registrar_evento(evento),
            ao_deteccao=lambda evento: ponte.registrar_evento(evento),
            replay=opcoes_replay_de_args(args),
        )
    except FonteIndisponivelError as erro:
        _logger.error("nao foi possivel abrir a fonte: %s", erro)
        return 2

    # A ponte assina ANTES de a fonte comecar. `montar` nao chamou
    # `iniciar()` ainda, e o docstring dele explica por que isso importa: o
    # simulador publica a partir de `iniciar()`, e quem assinar depois perde
    # o que ja passou.
    ponte = PonteFluxo(montagem.barramento)

    modo = ""
    if config.fonte is FonteDados.SIMULADOR:
        modo = "SIMULADOR"
    elif config.fonte is FonteDados.REPLAY:
        velocidade = args.velocidade
        modo = "▶ REPLAY " + ("máx" if velocidade == "max" else f"{velocidade}×")

    parando = threading.Event()

    def _parar() -> None:
        if parando.is_set():
            return
        parando.set()
        montagem.fonte.parar()

    janela = JanelaFluxo(
        ponte,
        simbolo=config.symbol,
        grid=config.price_grid(),
        modo=modo,
        paleta=tokens.PALETA_SEM_COR if args.sem_cor else tokens.PALETA_COR,
        densidade=_DENSIDADES[args.densidade],
        ao_fechar=_parar,
    )
    janela.tape.definir_filtro(args.filtro_tape)
    janela.show()

    if args.duracao:
        # `--duracao` vem do parser de `operar.py`. Honra-la aqui e o que
        # impede a flag de existir na ajuda e nao fazer nada — e e o que
        # torna possivel rodar o painel sem ninguem olhando (fumaca, CI,
        # gravacao automatica). `QTimer` e nao `threading.Timer`: fechar
        # janela e operacao da thread do Qt.
        QTimer.singleShot(int(args.duracao * 1000), janela.close)

    def _rodar_fonte() -> None:
        try:
            montagem.fonte.iniciar()
        except Exception:  # noqa: BLE001 — a UI precisa saber, nao morrer
            _logger.exception("falha na fonte de dados")
        finally:
            ponte.marcar_encerrado()

    thread = threading.Thread(target=_rodar_fonte, name="fonte", daemon=True)
    thread.start()

    codigo = aplicacao.exec()
    _parar()
    thread.join(timeout=5.0)
    montagem.sessao.finalizar()

    # Resumo na saida, pelo mesmo motivo que `operar.py` avisa quando
    # processou zero eventos: uma passada que nao mostrou nada e um
    # resultado suspeito, nao um resultado. O p95 do quadro entra junto
    # porque saude da interface e informacao da sessao, nao curiosidade.
    contadores = montagem.sessao.contadores
    _logger.info(
        "encerrado: %d negocios, %d snapshots, %d deltas | quadro DOM p95 %.3f ms "
        "(%d desenhados, %d ociosos) | tape p95 %.3f ms",
        contadores.n_trades_bus,
        contadores.n_snapshots_bus,
        contadores.n_deltas_bus,
        janela.dom.p95_ms(),
        janela.dom.quadros_desenhados,
        janela.dom.quadros_vazios,
        janela.tape.p95_ms(),
    )
    if contadores.n_trades_bus == 0:
        _logger.warning(
            "NENHUM negocio chegou a tela. Se a fonte e replay com --de/--ate, "
            "note que o recorte e interpretado em UTC: a abertura do WDO "
            "(09:00 de Brasilia) e 12:00 UTC."
        )
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
