#!/usr/bin/env python
"""Supervisiona `operar.py --gravar`: reconecta sozinho se ele cair cedo.

    python scripts/supervisionar_gravacao.py --simbolo WDOU26 --gravar dados\\ --fim 18:30

## O incidente que motivou isto

24/08/2026: a tarefa agendada subiu `operar.py --gravar` as 09:00:01 com
`--duracao 34200` (9h30, fim previsto 18:30). As 13:21:08 o processo morreu —
o log termina com `^C` e o codigo de saida (`-1073741510`, STATUS_CONTROL_C_EXIT
do Windows) e o mesmo de um Ctrl+C ou fechamento de janela. O terminal MT5
continuou de pe; so o `operar.py` caiu. A tarefa agendada nao tinha NENHUM
mecanismo para perceber isso e tentar de novo — o pregao seguiu sendo
negociado por mais quase 5 horas sem ninguem gravando.

Os dados ate ali estavam integros (`meta.json` com `"parcial": true`, hash
calculado, nada corrompido) porque `Gravador` ja escreve em modo append e
`_dia_ja_finalizado` so bloqueia reabertura quando existe `.csv.gz` — ou seja,
retomar um dia interrompido SEMPRE foi seguro no nivel do arquivo. Faltava
so quem, no nivel do PROCESSO, soubesse que precisava retomar.

## O que este script faz — e o que ele deliberadamente NAO faz

Roda `operar.py` em loop ate a hora de `--fim`. Se ele sair ANTES dessa hora,
relanca depois de um `--cooldown-s`, com o `--duracao` recalculado para o
tempo que ainda falta (nunca um `--duracao` fixo, que faria o segundo
lancamento ultrapassar o fechamento do pregao).

NAO tenta entender POR QUE o processo caiu — Ctrl+C externo, terminal MT5
fechado, deslogado, excecao no pipeline, todos looks iguais daqui de fora, e
tentar adivinhar seria a mesma armadilha do "codigo de saida mente" ja
catalogada neste projeto. Em vez disso, ele reage ao FATO observavel: "ainda
estou dentro da janela do pregao e o dia nao esta finalizado, entao devia
estar gravando — e nao estou".

Circuito de seguranca: se `operar.py` morre rapido (`< limiar-queda-rapida-s`)
varias vezes SEGUIDAS, e sinal de algo estrutural (MT5 fechado/deslogado,
config quebrada) e nao de um evento isolado — reconectar a cada 20s nesse
caso so spamaria o log e a maquina. Depois de `max-quedas-rapidas` seguidas,
desiste e avisa CLARAMENTE no log em vez de girar em silencio. Uma queda
depois de rodar bastante tempo (o caso real de hoje: 4h20 saudavel antes do
Ctrl+C) NAO conta para esse contador — reresetado a cada rodada longa.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import gzip
import sys
import threading
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.core.eventos import Trade  # noqa: E402
from fluxopro.gravacao import formato  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


# ============================================================ 03/09/2026
# Dois pregoes seguidos foram perdidos com a tarefa do Windows reportando
# sucesso (02/09: `mt5.initialize()` falhou as 09:00:03; 01/09: MT5 conectou e
# entregou 1 negocio o dia inteiro). O supervisor so olhava para o CODIGO DE
# SAIDA do processo — e processo vivo com fonte morta e indistinguivel de
# processo saudavel. As duas funcoes abaixo olham para o RESULTADO.

_NOME_TRADES = "trades.csv"


def caminho_trades(base: Path, symbol: str, dia: dt.date) -> Path:
    """CSV ao vivo do dia. O gravador so comprime para `.csv.gz` ao fechar
    (ver `gravador._fechar_dia`), entao durante o pregao e este que cresce."""

    return base / symbol / dia.isoformat() / _NOME_TRADES


def negocios_gravados(base: Path, symbol: str, dia: dt.date) -> int:
    """Quantos negocios existem no arquivo do dia — ao vivo ou ja fechado.

    Conta LINHAS DE DADOS (descontando o cabecalho). Nao carrega o arquivo
    inteiro em memoria: um pregao cheio passa de 30 mil linhas.
    """

    vivo = caminho_trades(base, symbol, dia)
    fechado = vivo.with_suffix(".csv.gz")
    if fechado.exists():
        abrir = lambda: gzip.open(fechado, "rt", encoding="utf-8", newline="")
    elif vivo.exists():
        abrir = lambda: vivo.open("r", encoding="utf-8", newline="")
    else:
        return 0
    try:
        with abrir() as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except OSError:
        # Arquivo em escrita concorrente pode falhar uma leitura isolada; a
        # vigia tenta de novo no proximo ciclo, e o portao de fim de dia roda
        # com o arquivo ja fechado.
        return 0


def fluxo_parado(
    amostras: "list[tuple[float, int]]", *, paciencia_s: float
) -> bool:
    """`True` quando a contagem de negocios NAO cresce ha `paciencia_s`.

    Funcao pura de proposito: a decisao de "o fluxo morreu" e testavel sem
    relogio, sem arquivo e sem subprocesso. `amostras` e uma lista de
    `(instante_monotonico, negocios)` em ordem cronologica.

    Nao dispara sem uma janela cheia de observacao: um pregao pode ter minutos
    legitimamente sem negocio (leilao, abertura lenta), e derrubar a fonte por
    causa disso trocaria um problema por outro.
    """

    if len(amostras) < 2:
        return False
    fim_t, fim_n = amostras[-1]
    for t, n in reversed(amostras):
        if fim_t - t < paciencia_s:
            continue
        return n == fim_n
    return False


_MARGEM_FIM_PADRAO_S = 5.0
"""Folga contra jitter do relogio: o `--duracao` do `operar.py` termina por
timer de parede, e uma leitura de `agora()` alguns ms depois da hora exata
nao pode virar uma "queda" fantasma que o supervisor tenta reconectar."""


def _hora_local(texto: str) -> dt.time:
    for formato_ in ("%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(texto, formato_).time()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"hora invalida: {texto!r} (use HH:MM ou HH:MM:SS)")


def dia_finalizado(base: Path, symbol: str, dia: dt.date) -> bool:
    """Mesma pergunta que `Gravador._dia_ja_finalizado` faz: existe `.gz`?

    Nao le `meta.json` pelo mesmo motivo do `Gravador`: o `.gz` E a marca.
    """
    nome = formato.NOMES_ARQUIVO[Trade]
    caminho = base / symbol / dia.isoformat() / nome
    return caminho.with_suffix(caminho.suffix + ".gz").exists()


def supervisionar(
    *,
    fim: dt.datetime,
    lancar: Callable[[float], "tuple[int, float]"],
    dia_ja_finalizado: Callable[[], bool],
    agora: Callable[[], dt.datetime] = dt.datetime.now,
    dormir: Callable[[float], None] = time.sleep,
    logar: Callable[[str], None] = print,
    cooldown_s: float = 20.0,
    limiar_queda_rapida_s: float = 60.0,
    max_quedas_rapidas: int = 60,
    margem_fim_s: float = _MARGEM_FIM_PADRAO_S,
) -> int:
    """O loop puro, sem `subprocess` nem relogio de verdade — por isso testavel.

    `lancar(duracao_s)` roda UMA passada e devolve `(codigo_saida, duracao_real_s)`;
    quem chama decide se isso e um `subprocess.call` de verdade ou um dublê de
    teste. Devolve quantas reconexoes aconteceram (0 = rodou do inicio ao fim
    sem cair nenhuma vez, que e o caminho feliz de todo dia sem incidente).
    """
    quedas_rapidas_seguidas = 0
    total_reconexoes = 0
    margem = dt.timedelta(seconds=margem_fim_s)

    while True:
        agora_ = agora()
        if agora_ >= fim:
            logar(f"[supervisor] {agora_:%H:%M:%S} janela encerrada — nao reconecta mais")
            break
        if dia_ja_finalizado():
            logar(f"[supervisor] {agora_:%H:%M:%S} dia ja finalizado (.gz existe) — nada a fazer")
            break

        restante_s = (fim - agora_).total_seconds()
        logar(
            f"[supervisor] {agora_:%H:%M:%S} iniciando operar.py "
            f"({restante_s:.0f}s ate {fim:%H:%M:%S}, reconexao #{total_reconexoes})"
        )
        codigo, duracao_s = lancar(restante_s)
        agora_ = agora()

        if agora_ >= fim - margem:
            logar(
                f"[supervisor] {agora_:%H:%M:%S} operar.py encerrou (codigo {codigo}) "
                "e a janela ja fechou — fim normal do dia"
            )
            break

        total_reconexoes += 1
        if duracao_s < limiar_queda_rapida_s:
            quedas_rapidas_seguidas += 1
        else:
            quedas_rapidas_seguidas = 0

        logar(
            f"[supervisor] {agora_:%H:%M:%S} operar.py caiu cedo "
            f"(codigo {codigo}, rodou {duracao_s:.0f}s) — reconectando em {cooldown_s:.0f}s "
            f"(queda rapida {quedas_rapidas_seguidas}/{max_quedas_rapidas})"
        )
        if quedas_rapidas_seguidas >= max_quedas_rapidas:
            logar(
                f"[supervisor] {agora_:%H:%M:%S} {max_quedas_rapidas} quedas rapidas "
                "seguidas — desistindo. Suspeita estrutural (MT5 fechado/deslogado, ou "
                "outro erro que se repete na hora de abrir a fonte), nao um evento isolado."
            )
            break

        dormir(cooldown_s)

    return total_reconexoes


def _lancar_de_verdade(
    *, symbol: str, saida: str, status_a_cada: float, fsync_a_cada: int,
    dia: dt.date, vigia_paciencia_s: float, vigia_intervalo_s: float,
    logar: Callable[[str], None] = print,
) -> Callable[[float], "tuple[int, float]"]:
    base = Path(saida)

    def _lancar(duracao_s: float) -> "tuple[int, float]":
        inicio = time.monotonic()
        processo = subprocess.Popen(
            [
                sys.executable,
                str(RAIZ / "scripts" / "operar.py"),
                "--fonte", "mt5",
                "--simbolo", symbol,
                "--gravar", saida,
                "--duracao", str(max(1, int(duracao_s))),
                "--status-a-cada", str(status_a_cada),
                "--fsync-a-cada", str(fsync_a_cada),
            ]
        )

        # VIGIA SILENCIOSA DE FLUXO (03/09/2026)
        # Codigo de saida nao detecta fonte morta com processo vivo — foi
        # assim que 01/09 gravou 1 negocio o dia inteiro e ninguem soube. Aqui
        # a contagem de negocios do proprio arquivo do dia e amostrada; se ela
        # nao cresce por `vigia_paciencia_s`, o processo e derrubado e o laco
        # do supervisor reconecta, que e o circuito que ja existe.
        #
        # Silenciosa: so escreve no log quando AGE. Um vigia que fala a cada
        # ciclo vira ruido e some no meio do log do pregao.
        parar = threading.Event()

        def _vigiar() -> None:
            amostras: list[tuple[float, int]] = []
            while not parar.wait(vigia_intervalo_s):
                amostras.append((time.monotonic(), negocios_gravados(base, symbol, dia)))
                # Mantem so a janela util de observacao.
                corte = time.monotonic() - (vigia_paciencia_s * 2)
                amostras = [a for a in amostras if a[0] >= corte] or amostras[-2:]
                if fluxo_parado(amostras, paciencia_s=vigia_paciencia_s):
                    logar(
                        f"[vigia] {dt.datetime.now():%H:%M:%S} nenhum negocio novo ha "
                        f"{vigia_paciencia_s:.0f}s (total {amostras[-1][1]}) — "
                        "derrubando operar.py para o supervisor reconectar"
                    )
                    processo.terminate()
                    return

        vigia = threading.Thread(target=_vigiar, name="vigia-fluxo", daemon=True)
        vigia.start()
        try:
            codigo = processo.wait()
        finally:
            parar.set()
        return codigo, time.monotonic() - inicio

    return _lancar


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--simbolo", required=True)
    p.add_argument("--gravar", required=True, help="diretorio base da gravacao")
    p.add_argument("--fim", type=_hora_local, default=dt.time(18, 30), help="hora local em que para de reconectar (default 18:30)")
    p.add_argument("--cooldown-s", type=float, default=20.0, dest="cooldown_s")
    p.add_argument("--limiar-queda-rapida-s", type=float, default=60.0, dest="limiar_queda_rapida_s")
    p.add_argument("--max-quedas-rapidas", type=int, default=60, dest="max_quedas_rapidas")
    p.add_argument("--status-a-cada", type=float, default=300.0, dest="status_a_cada")
    p.add_argument("--fsync-a-cada", type=int, default=200, dest="fsync_a_cada")
    p.add_argument(
        "--vigia-paciencia-s", type=float, default=600.0, dest="vigia_paciencia_s",
        help=(
            "quanto tempo sem NENHUM negocio novo antes de derrubar a fonte e "
            "reconectar (default 600 = 10 min). Um pregao tem minutos "
            "legitimamente parados (leilao, abertura lenta); 10 min e folgado o "
            "bastante para nao brigar com isso e curto o bastante para nao "
            "perder o dia. 0 desliga a vigia."
        ),
    )
    p.add_argument(
        "--vigia-intervalo-s", type=float, default=60.0, dest="vigia_intervalo_s",
        help="de quanto em quanto tempo a vigia conta os negocios (default 60)",
    )
    args = p.parse_args(argv)

    hoje = dt.date.today()
    fim = dt.datetime.combine(hoje, args.fim)
    base = Path(args.gravar)

    reconexoes = supervisionar(
        fim=fim,
        lancar=_lancar_de_verdade(
            symbol=args.simbolo,
            saida=args.gravar,
            status_a_cada=args.status_a_cada,
            fsync_a_cada=args.fsync_a_cada,
            dia=hoje,
            vigia_paciencia_s=args.vigia_paciencia_s,
            vigia_intervalo_s=args.vigia_intervalo_s,
        ),
        dia_ja_finalizado=lambda: dia_finalizado(base, args.simbolo, hoje),
        cooldown_s=args.cooldown_s,
        limiar_queda_rapida_s=args.limiar_queda_rapida_s,
        max_quedas_rapidas=args.max_quedas_rapidas,
    )
    print(f"[supervisor] encerrado — {reconexoes} reconexao(oes) nesta passada")

    # PORTAO DE FIM DE DIA (03/09/2026, criterio do operador: "falha se zero
    # negocios"). Ate aqui `main` devolvia 0 SEMPRE, e por isso a tarefa do
    # Windows marcou sucesso nos dois dias em que nao gravou nada. Um dia sem
    # um unico negocio nao e um dia gravado — e a unica forma de isso aparecer
    # e a rotina FALHAR.
    negocios = negocios_gravados(base, args.simbolo, hoje)
    if negocios <= 0:
        print(
            f"[supervisor] FALHA: {hoje} fechou com ZERO negocios gravados em "
            f"{caminho_trades(base, args.simbolo, hoje).parent}. "
            "O pregao NAO foi gravado. Conferir se o terminal MetaTrader 5 "
            "estava aberto e LOGADO (uma tarefa agendada nao digita senha) e "
            "o log do dia em logs/."
        )
        return 2
    print(f"[supervisor] {hoje}: {negocios} negocios gravados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
