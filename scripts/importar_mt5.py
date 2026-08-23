#!/usr/bin/env python
"""Importa o TAPE de um pregao ja fechado do MetaTrader 5 para uma gravacao.

    python scripts/importar_mt5.py --simbolo WDOU26 --data 2026-08-21 --saida dados/

Modo SINAIS e sempre: este programa so LE. Ver `tests/test_sem_execucao.py`,
que enumera tudo o que o repositorio toca do pacote `MetaTrader5` e reprova o
que nao estiver na lista de leitura declarada.

## Por que ele existe

O adaptador ao vivo (`fluxopro/dados/mt5.py`) e um streamer: ele le do AGORA em
diante. Isso significa que so da para gravar mercado real durante o pregao, com
alguem na frente da maquina — e fora do pregao o projeto ficava restrito ao
simulador, cujo passeio aleatorio nao tem estrutura de mercado nenhuma.

Mas o terminal guarda historico de tick. Medido nesta maquina, num domingo:
`copy_ticks_from` devolveu **90.459 negocios** do pregao de sexta em WDOU26,
com **86,8%** deles carregando o lado do agressor. Isso e o insumo principal do
produto — delta, agressao, footprint, exaustao, absorcao saem dai.

## O que ele NAO importa, e por que isso importa saber

**Livro.** `market_book_get` so existe com o mercado aberto; num pregao fechado
ele devolve zero niveis, medido. Nao ha historico de book no MT5, e nao ha como
inventar um: DOM, bookmap e tudo que depende de liquidez parada ficam VAZIOS
numa gravacao importada.

A gravacao resultante e honesta sobre isso — ela simplesmente nao tem
`snapshots.csv`. O painel abre, o tape roda, o DOM fica em branco. Uma
gravacao que fabricasse um livro plausivel a partir de bid/ask seria pior que
livro nenhum: pareceria leitura de fluxo e seria desenho.

Para ter as duas metades, o caminho continua sendo o pregao ao vivo:

    python scripts/operar.py --fonte mt5 --simbolo WDOU26 --gravar dados/

## Formato

Nao inventa formato: publica `Trade` no `Barramento` com o `Gravador` assinado,
exatamente como o pipeline ao vivo. O resultado e lido por
`--fonte replay --arquivo dados/` sem nenhum caminho especial, e o hash de
integridade e o mesmo.

A conversao de tick para `Trade` vem de `dados.mt5.trade_de_tick`, a MESMA que
o adaptador ao vivo usa. Se cada um convertesse do seu jeito, a gravacao ao
vivo e a importada do mesmo pregao divergiriam — e a divergencia so apareceria
ao comparar as duas, que e quando ninguem espera diferenca.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fluxopro.app.config import ConfigOperacao  # noqa: E402
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.dados.mt5 import _importar_mt5, trade_de_tick  # noqa: E402
from fluxopro.gravacao.gravador import Gravador  # noqa: E402

_logger = logging.getLogger("scripts.importar_mt5")

PAGINA = 100_000
"""Ticks por chamada de `copy_ticks_from`.

Medido: o terminal satura em 100.000 por chamada — pedir 200.000 devolve
100.000 e nada avisa. Por isso a pagina e explicita e o laco compara o
devolvido com o pedido para saber se ha mais.
"""

PASSO_MINIMO_MS = 1
"""Avanco forcado quando uma pagina inteira cai no mesmo milissegundo.

Sem isto o cursor congela e o laco gira para sempre. Com isto perde-se o resto
daquele ms — e o laco AVISA, porque perder negocio em silencio e o defeito que
este projeto passou cinco auditorias caçando.
"""


def _data(texto: str) -> dt.date:
    return dt.datetime.strptime(texto, "%Y-%m-%d").date()


def _hora(texto: str) -> dt.time:
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"hora invalida: {texto!r} (use HH:MM ou HH:MM:SS)")


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="importa o tape de um pregao fechado do MT5 para uma gravacao",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--simbolo", required=True, help="ex.: WDOU26 (o contrato LIQUIDO)")
    p.add_argument("--data", type=_data, required=True, help="dia do pregao, YYYY-MM-DD")
    p.add_argument("--saida", required=True, help="diretorio da gravacao")
    # O DIA INTEIRO por padrao, e nao 09:00-18:30.
    #
    # O primeiro import deste script pegou 90.459 dos 200.914 ticks da sexta —
    # 45% do pregao — e nao avisou nada. O relogio dos ticks do MT5 esta no
    # referencial do SERVIDOR da corretora, nao no de Brasilia: medido nesta
    # conta, os cinco pregoes de 17 a 21/08 comecam entre 03:00 e 04:07 e
    # terminam 15:29:59. Uma janela "09:00-18:30" escrita pensando no horario
    # da B3 recorta o meio da sessao.
    #
    # Ninguem deveria ter de saber o fuso do servidor para importar um dia. Os
    # dois parametros continuam existindo para recorte deliberado.
    p.add_argument("--de", type=_hora, default=dt.time(0, 0), help="inicio (default 00:00)")
    p.add_argument("--ate", type=_hora, default=dt.time(23, 59, 59), help="fim (default 23:59:59)")
    p.add_argument("--fsync-a-cada", type=int, default=200, dest="fsync_a_cada")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def importar(
    simbolo: str,
    dia: dt.date,
    saida: str,
    de: dt.time,
    ate: dt.time,
    fsync_a_cada: int = 200,
) -> dict[str, int]:
    """Le o tape do dia e grava. Devolve os contadores medidos."""
    mt5 = _importar_mt5()
    if not mt5.initialize():
        raise RuntimeError(
            "MT5 nao inicializou: %r. O terminal precisa estar ABERTO e LOGADO."
            % (mt5.last_error(),)
        )
    try:
        if not mt5.symbol_select(simbolo, True):
            raise RuntimeError(
                f"simbolo {simbolo!r} nao pode ser selecionado: {mt5.last_error()!r}"
            )

        grid = ConfigOperacao(symbol=simbolo).price_grid()
        barramento = Barramento()
        gravador = Gravador(barramento, saida, fsync_a_cada=fsync_a_cada)
        gravador.iniciar()

        # UM RELOGIO SO: UTC, que e o que `Gravador._timestamp_para_data` usa
        # para decidir em qual pasta de dia o evento cai.
        #
        # A versao anterior misturava dois. Ela pedia ticks a partir de um
        # `datetime` ingenuo (que o MT5 le no fuso do SERVIDOR), filtrava por
        # um fim calculado em hora LOCAL, e relatava cobertura numa terceira
        # conversao. Resultado medido: importou 06:00:38 -> 15:29:59 de um
        # pregao que comeca 03:00:07, e disse que estava tudo bem.
        #
        # Agora a pergunta e uma so e nao depende de fuso nenhum: **este tick
        # cai no dia UTC pedido?** A varredura comeca um dia antes e para um
        # dia depois, margem suficiente para qualquer deslocamento de servidor
        # plausivel, e o filtro decide o que entra.
        inicio = dt.datetime.combine(dia, de) - dt.timedelta(days=1)
        limite = dia + dt.timedelta(days=1)

        contadores = {
            "ticks_lidos": 0,
            "trades": 0,
            "descartados": 0,
            "paginas": 0,
            "ms_perdidos": 0,
            # A COBERTURA, em ms. Existe porque a primeira versao deste script
            # importou 45% de um pregao em silencio: ela contava trades, e
            # 90.459 trades parecem muitos ate voce descobrir que eram 200.914.
            # Contagem sem intervalo nao diz se faltou pedaco.
            "primeiro_ms": 0,
            "ultimo_ms": 0,
        }
        cursor = inicio
        visto_ate_ms = 0
        try:
            while True:
                lote = mt5.copy_ticks_from(simbolo, cursor, PAGINA, mt5.COPY_TICKS_ALL)
                if lote is None or len(lote) == 0:
                    break
                contadores["paginas"] += 1
                contadores["ticks_lidos"] += len(lote)

                ultimo_ms = int(lote[len(lote) - 1]["time_msc"])
                ordem_no_ms = 0
                ms_anterior = -1
                passou_do_fim = False
                for i in range(len(lote)):
                    tick = lote[i]
                    ms = int(tick["time_msc"])
                    dia_do_tick = dt.datetime.fromtimestamp(
                        ms / 1000.0, tz=dt.timezone.utc
                    ).date()
                    if dia_do_tick >= limite:
                        passou_do_fim = True
                        break
                    if dia_do_tick != dia:
                        # antes do dia pedido: o cursor avanca, o evento nao sai
                        continue
                    if ms <= visto_ate_ms:
                        # ja publicado numa pagina anterior; `copy_ticks_from`
                        # devolve o segundo inteiro e as paginas se sobrepoem.
                        continue
                    ordem_no_ms = ordem_no_ms + 1 if ms == ms_anterior else 0
                    ms_anterior = ms
                    trade = trade_de_tick(mt5, tick, simbolo, grid, ordem_no_ms)
                    if trade is None:
                        contadores["descartados"] += 1
                        continue
                    barramento.publicar(trade)
                    contadores["trades"] += 1
                    if not contadores["primeiro_ms"]:
                        contadores["primeiro_ms"] = ms
                    contadores["ultimo_ms"] = ms

                if passou_do_fim:
                    break
                if ultimo_ms <= visto_ate_ms:
                    # A pagina inteira caiu num ms ja visto: o cursor nao tem
                    # como avancar sozinho. Empurra 1 ms e CONTA a perda.
                    contadores["ms_perdidos"] += 1
                    visto_ate_ms += PASSO_MINIMO_MS
                    _logger.warning(
                        "pagina cheia dentro do ms %d — pulando 1 ms; ha um "
                        "buraco de ticks aqui",
                        visto_ate_ms,
                    )
                else:
                    visto_ate_ms = ultimo_ms
                if len(lote) < PAGINA:
                    break
                cursor = dt.datetime.fromtimestamp(visto_ate_ms / 1000.0)
        finally:
            gravador.parar()
        return contadores
    finally:
        mt5.shutdown()


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    contadores = importar(
        args.simbolo, args.data, args.saida, args.de, args.ate, args.fsync_a_cada
    )
    _logger.info(
        "%s %s: %d ticks lidos em %d paginas -> %d trades gravados "
        "(%d descartados, %d ms perdidos)",
        args.simbolo,
        args.data,
        contadores["ticks_lidos"],
        contadores["paginas"],
        contadores["trades"],
        contadores["descartados"],
        contadores["ms_perdidos"],
    )
    if contadores["primeiro_ms"]:
        utc = dt.timezone.utc
        primeiro = dt.datetime.fromtimestamp(contadores["primeiro_ms"] / 1000, tz=utc)
        ultimo = dt.datetime.fromtimestamp(contadores["ultimo_ms"] / 1000, tz=utc)
        horas = (contadores["ultimo_ms"] - contadores["primeiro_ms"]) / 3_600_000
        _logger.info(
            "COBERTURA: %s -> %s UTC (%.2f h). E o mesmo relogio que nomeia a "
            "pasta do dia na gravacao.",
            primeiro.strftime("%H:%M:%S"),
            ultimo.strftime("%H:%M:%S"),
            horas,
        )
    if contadores["trades"] == 0:
        _logger.error(
            "nenhum trade gravado — o dia pedido tem pregao? o simbolo esta certo? "
            "(contratos com '$' e '@' sao sinteticos da corretora)"
        )
        return 1
    _logger.info(
        "SEM LIVRO nesta gravacao: o MT5 nao guarda historico de book. "
        "DOM e bookmap ficam vazios no replay — ver o docstring deste script."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
