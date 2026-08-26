#!/usr/bin/env python
"""CLI de operação: liga o pipeline INTEIRO e imprime o que está acontecendo.

    python scripts/operar.py --fonte simulador --simbolo WDOV26 --seed 42 --duracao 60
    python scripts/operar.py --fonte replay --arquivo dados/ --simbolo WDOV26 --de 12:00 --ate 13:30 --velocidade 10
    python scripts/operar.py --fonte replay --arquivo dados/trades.csv --simbolo WDOV26
    python scripts/operar.py --fonte mt5 --simbolo WDOV26

ATENCAO ao fuso de `--de/--ate`: o recorte e resolvido em **UTC** por
`gravacao/catalogo.py`, e nada no caminho converte de horario de Brasilia.
O exemplo acima pede 12:00-13:30 UTC = 09:00-10:30 BRT, que e a primeira hora
e meia do WDO. Escrever `--de 09:00` pediria 06:00 BRT, uma janela inteira
ANTES da abertura, e o replay devolveria zero eventos. (Este exemplo dizia
`--de 09:00` ate a onda 9; `criticas/nucleo_r5.md` §B.2 mostrou que a
documentacao e a convencao se contradiziam e nenhuma das duas podia notar.
A convencao em si — UTC ou BRT — e decisao de `catalogo.py`, nao deste CLI;
o que se corrigiu aqui foi o exemplo mentiroso e o silencio no fim da
passada.)

`--fonte simulador` roda **sem MT5 instalado e sem corretora conectada** — é
como o dono vê o sistema funcionando hoje, sem depender de pregão ao vivo nem
de credencial.

Modo SINAIS por padrão e sempre: este programa não envia ordem para lugar
nenhum. `MotorSinais` emite `Sinal`; execução real não existe no código.

Encerramento com Ctrl+C é limpo: para o adaptador, drena o `InferidorMBP`
(senão as quedas de quantidade pendentes ficariam sem resolver) e imprime o
resumo da sessão.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, time as hora_do_dia
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.app.config import (
    NS_POR_SEGUNDO,
    ConfigOperacao,
    ConfigSimulador,
    FonteDados,
)
from fluxopro.app.montagem import FonteIndisponivelError, OpcoesReplay, montar
from fluxopro.app.saida import ConsoleFluxo
from fluxopro.gravacao.gravador import Gravador
from fluxopro.motor.sinais import ConfigMotorSinais

_logger = logging.getLogger("scripts.operar")

_N_EVENTOS_SEM_LIMITE = 10**9
"""`SimuladorWDO` precisa de um `n_eventos` finito; "sem limite" é um número
grande interrompido de verdade por `parar()` (Ctrl+C ou `--duracao`)."""


def _hora(texto: str) -> hora_do_dia:
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"hora invalida: {texto!r} (use HH:MM ou HH:MM:SS)")


def _data(texto: str) -> date:
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"data invalida: {texto!r} (use AAAA-MM-DD)") from erro


def _velocidade(texto: str) -> float | str:
    if texto.lower() in ("max", "maxima"):
        return "max"
    try:
        valor = float(texto)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"velocidade invalida: {texto!r}") from erro
    if valor <= 0:
        raise argparse.ArgumentTypeError("velocidade deve ser > 0 (ou 'max')")
    return valor


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="FLUXO PRO - leitura de fluxo ao vivo, em replay ou simulada.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--simbolo", default="WDOFUT", help="ex.: WDOV26, WINZ26")
    p.add_argument(
        "--fonte",
        choices=[f.value for f in FonteDados],
        default=FonteDados.MT5.value,
    )

    g_sim = p.add_argument_group("simulador")
    g_sim.add_argument("--seed", type=int, default=42, help="seed deterministica")
    g_sim.add_argument(
        "--n-eventos", type=int, default=0, dest="n_eventos",
        help="0 = sem limite (encerra por --duracao ou Ctrl+C)",
    )
    g_sim.add_argument("--taxa-eventos-s", type=float, default=5.0, dest="taxa_eventos_s")
    g_sim.add_argument("--volatilidade", type=float, default=1.0)
    g_sim.add_argument("--preco-inicial", type=float, default=5000.0, dest="preco_inicial")

    g_rep = p.add_argument_group("replay")
    g_rep.add_argument(
        "--arquivo",
        help="CSV de trades, ou o DIRETORIO base de uma gravacao de scripts/gravar.py",
    )
    g_rep.add_argument("--arquivo-deltas", dest="arquivo_deltas", help="(CSV) deltas de book")
    g_rep.add_argument("--data", type=_data, help="(gravacao) dia; padrao = o mais recente")
    g_rep.add_argument(
        "--de", type=_hora,
        help="(gravacao) inicio do recorte, HH:MM em UTC (WDO abre 12:00 UTC)",
    )
    g_rep.add_argument(
        "--ate", type=_hora,
        help="(gravacao) fim do recorte, HH:MM em UTC (WDO fecha 21:00 UTC)",
    )
    g_rep.add_argument("--velocidade", type=_velocidade, default="max")
    g_rep.add_argument(
        "--sem-verificar-hash", action="store_true", dest="sem_verificar_hash",
        help="(gravacao) pula a checagem de integridade; use so para diagnostico",
    )

    g_cal = p.add_argument_group("calibracao do motor de sinais")
    g_cal.add_argument(
        "--dominancia-minima", type=float, dest="dominancia_minima",
        help=(
            "corte de 'direcional' "
            f"(default {ConfigMotorSinais().dominancia_minima})"
        ),
    )
    g_cal.add_argument(
        "--janela-dominancia-s", type=float, dest="janela_dominancia_s",
        help="janela de dominancia em segundos (default 300)",
    )
    g_cal.add_argument(
        "--janela-micro-s", type=float, dest="janela_micro_s",
        help="janela da micro em segundos (default 15)",
    )
    g_cal.add_argument(
        "--magnitude-relativa-minima", type=float, dest="magnitude_relativa_minima",
        help="gate do caso WINFUT (default 0.60)",
    )

    g_out = p.add_argument_group("execucao e saida")
    g_out.add_argument(
        "--duracao", type=float,
        help="segundos de relogio de parede ate parar sozinho (default: sem limite)",
    )
    g_out.add_argument("--gravar", help="liga o Gravador no mesmo pipeline; diretorio de saida")
    g_out.add_argument("--fsync-a-cada", type=int, default=200, dest="fsync_a_cada")
    g_out.add_argument(
        "--status-a-cada", type=float, default=5.0, dest="status_a_cada",
        help="intervalo (s) da linha de contadores ao vivo; 0 desliga",
    )
    g_out.add_argument(
        "--mostrar-nenhum", action="store_true", dest="mostrar_nenhum",
        help="imprime tambem a volta do motor para o estagio NENHUM",
    )
    g_out.add_argument("--sem-analytics", action="store_true", dest="sem_analytics")
    g_out.add_argument("--sem-microestrutura", action="store_true", dest="sem_microestrutura")
    g_out.add_argument("--sem-detectores-tape", action="store_true", dest="sem_detectores_tape")
    g_out.add_argument("--sem-motor", action="store_true", dest="sem_motor")
    g_out.add_argument("-v", "--verbose", action="store_true")
    return p


def config_de_args(args: argparse.Namespace) -> ConfigOperacao:
    """Traduz a linha de comando em `ConfigOperacao` — sem limiar redigitado.

    Cada `--flag` de calibração só sobrescreve o campo correspondente; o que
    não foi passado continua com o default do módulo dono, e não com uma cópia
    do default que envelheceria em silêncio.
    """
    motor = ConfigMotorSinais()
    trocas: dict[str, object] = {}
    if args.dominancia_minima is not None:
        trocas["dominancia_minima"] = args.dominancia_minima
    if args.janela_dominancia_s is not None:
        trocas["janela_dominancia_ns"] = int(args.janela_dominancia_s * NS_POR_SEGUNDO)
    if args.janela_micro_s is not None:
        trocas["janela_micro_ns"] = int(args.janela_micro_s * NS_POR_SEGUNDO)
    if args.magnitude_relativa_minima is not None:
        trocas["magnitude_relativa_minima"] = args.magnitude_relativa_minima
    if trocas:
        motor = replace(motor, **trocas)  # type: ignore[arg-type]

    n_eventos = args.n_eventos if args.n_eventos > 0 else _N_EVENTOS_SEM_LIMITE
    return ConfigOperacao(
        symbol=args.simbolo,
        fonte=FonteDados(args.fonte),
        motor=motor,
        simulador=ConfigSimulador(
            seed=args.seed,
            volatilidade=args.volatilidade,
            taxa_eventos_s=args.taxa_eventos_s,
            preco_inicial=args.preco_inicial,
            n_eventos=n_eventos,
        ),
        ligar_analytics=not args.sem_analytics,
        ligar_microestrutura=not args.sem_microestrutura,
        ligar_detectores_tape=not args.sem_detectores_tape,
        ligar_motor=not args.sem_motor,
    )


def opcoes_replay_de_args(args: argparse.Namespace) -> OpcoesReplay:
    return OpcoesReplay(
        caminho=Path(args.arquivo) if args.arquivo else None,
        caminho_deltas=Path(args.arquivo_deltas) if args.arquivo_deltas else None,
        data=args.data,
        de=args.de,
        ate=args.ate,
        velocidade=args.velocidade,
        verificar_hash=not args.sem_verificar_hash,
    )


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = config_de_args(args)
    console = ConsoleFluxo(
        config.price_grid(),
        mostrar_estagio_nenhum=args.mostrar_nenhum,
        # O CLI nunca lê `console.linhas` — o consumidor aqui é o stdout.
        # Guardar era reter uma cópia do pregão inteiro em RAM para ninguém:
        # 0,44 GB num pregão de 6 h a 5.000 ev/s (medido; ver "Critério de
        # crescimento" em `fluxopro/app/saida.py`).
        guardar_linhas=False,
    )

    try:
        montagem = montar(
            config,
            ao_sinal=console.ao_sinal,
            ao_deteccao=console.ao_deteccao,
            replay=opcoes_replay_de_args(args),
        )
    except FonteIndisponivelError as erro:
        _logger.error("nao foi possivel abrir a fonte: %s", erro)
        return 2

    gravador: Gravador | None = None
    if args.gravar:
        # No MESMO barramento: o gravador vê exatamente os eventos que o
        # pipeline consumiu, então a gravação e a análise nunca divergem.
        gravador = Gravador(montagem.barramento, args.gravar, fsync_a_cada=args.fsync_a_cada)
        gravador.iniciar()
        _logger.info("gravando em %s", args.gravar)

    console.cabecalho(montagem.sessao)
    sys.stdout.flush()

    parar_evt = threading.Event()
    encerrando = threading.Event()

    def _parar(motivo: str) -> None:
        if encerrando.is_set():
            return
        encerrando.set()
        _logger.info("encerrando (%s)...", motivo)
        parar_evt.set()
        montagem.fonte.parar()

    def _handler_sinal(_signum, _frame) -> None:
        _parar("Ctrl+C")

    signal.signal(signal.SIGINT, _handler_sinal)
    try:
        signal.signal(signal.SIGTERM, _handler_sinal)
    except (ValueError, AttributeError):
        pass  # SIGTERM pode nao existir/ser configuravel em algumas plataformas

    if args.duracao:
        threading.Timer(args.duracao, lambda: _parar(f"--duracao {args.duracao}s")).start()

    if args.status_a_cada > 0:
        def _status() -> None:
            while not parar_evt.wait(args.status_a_cada):
                _logger.info("status: %s", console.linha_status(montagem.sessao))

        threading.Thread(target=_status, daemon=True).start()

    _logger.info(
        "iniciando: simbolo=%s fonte=%s (modo SINAIS: nenhuma ordem e enviada)",
        config.symbol, config.fonte.value,
    )
    inicio = time.perf_counter()
    codigo = 0
    try:
        montagem.fonte.iniciar()  # bloqueia ate a fonte acabar ou parar()
    except KeyboardInterrupt:
        # Ctrl+C entre o handler e o retorno da fonte; nao e erro.
        _parar("Ctrl+C")
    except Exception:  # noqa: BLE001 — precisa fechar o gravador de qualquer forma
        _logger.exception("falha na fonte de dados")
        codigo = 1
    finally:
        parar_evt.set()
        montagem.sessao.finalizar()
        if gravador is not None:
            gravador.parar()
        # Passada que não processou NADA é um resultado suspeito, não um
        # resultado. `criticas/nucleo_r5.md` §B.2: o exemplo publicado no
        # cabeçalho deste módulo (`--de 09:00 --ate 10:30`) devolve zero
        # eventos, porque o recorte é interpretado em UTC e a janela cai
        # inteira antes da abertura do WDO — "sem erro, sem aviso, sem log".
        # O aviso não conserta a convenção (isso é decisão de `catalogo.py`),
        # mas troca um silêncio por uma pergunta, que é o que faz o dono
        # olhar em vez de concluir que o pregão foi parado.
        if montagem.sessao.contadores.n_eventos_bus == 0 and codigo == 0:
            _logger.warning(
                "NENHUM evento foi processado. Se a fonte e replay com "
                "--de/--ate, note que o recorte e interpretado em UTC: a "
                "abertura do WDO (09:00 de Brasilia) e 12:00 UTC."
            )
        console.resumo(montagem.sessao)
        _logger.info("encerrado em %.2fs de relogio de parede", time.perf_counter() - inicio)
        sys.stdout.flush()

    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
