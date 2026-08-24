"""`montar()` — de uma `ConfigOperacao` a um pipeline pronto para rodar.

Uma função só, com um contrato só: devolve `(barramento, sessao, fonte)` já
ligados. Quem chama (o CLI, um teste, um benchmark, a UI amanhã) só precisa
chamar `fonte.iniciar()` e, ao terminar, `sessao.finalizar()`.

A escolha de fonte é dado, não código: `ConfigOperacao.fonte` decide entre
simulador sintético, replay (CSV do núcleo **ou** gravação do `Gravador`) e
MT5 ao vivo. O import do `AdaptadorMT5` é preguiçoso de propósito — ele
importa o pacote `MetaTrader5`, que não existe fora do Windows com terminal
instalado, e nada mais do produto pode depender disso para carregar. É o que
faz `--fonte simulador` rodar hoje, sem MT5 e sem corretora.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time as hora_do_dia
from pathlib import Path
from typing import Callable

from fluxopro.app.config import ConfigOperacao, FonteDados
from fluxopro.app.sessao_fluxo import DeteccaoAnotada, SessaoFluxo
from fluxopro.core.barramento import Barramento
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao
from fluxopro.dados.replay import AdaptadorReplay
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.motor.sinais import Sinal


class FonteIndisponivelError(RuntimeError):
    """A fonte pedida não pôde ser construída (arquivo ausente, MT5 fora)."""


@dataclass(frozen=True, slots=True)
class OpcoesReplay:
    """O que só o replay precisa saber, fora da `ConfigOperacao`.

    Está separado porque não é calibração do sistema — é o recorte de "qual
    pedaço de qual gravação". Misturar isso em `ConfigOperacao` faria uma
    config de operação ao vivo carregar campos que nunca são usados.
    """

    caminho: Path | None = None
    """Arquivo CSV de trades, ou o diretório base de uma gravação do `Gravador`."""

    caminho_deltas: Path | None = None
    """Só para o CSV do núcleo (`AdaptadorReplay`), que separa trades e deltas."""

    data: date | None = None
    """Dia da gravação. `None` = o dia mais recente do símbolo no catálogo."""

    de: hora_do_dia | None = None
    ate: hora_do_dia | None = None
    velocidade: float | str = "max"
    verificar_hash: bool = True


@dataclass(frozen=True, slots=True)
class Montagem:
    """O que `montar` devolve — nomeado para não virar tupla anônima."""

    barramento: Barramento
    sessao: SessaoFluxo
    fonte: AdaptadorDados


def criar_fonte(
    config: ConfigOperacao,
    barramento: Barramento,
    replay: OpcoesReplay | None = None,
) -> AdaptadorDados:
    if config.fonte is FonteDados.SIMULADOR:
        sim = config.simulador
        return SimuladorWDO(
            barramento,
            seed=sim.seed,
            volatilidade=sim.volatilidade,
            taxa_eventos_s=sim.taxa_eventos_s,
            preco_inicial=sim.preco_inicial,
            symbol=config.symbol,
            n_eventos=sim.n_eventos,
            tick_size=config.price_grid().tick_size,
        )

    if config.fonte is FonteDados.REPLAY:
        return _criar_replay(config, barramento, replay or OpcoesReplay())

    if config.fonte is FonteDados.MT5:
        # Preguiçoso: importar isto no topo quebraria o produto inteiro em
        # qualquer máquina sem o terminal MetaTrader5.
        from fluxopro.dados.mt5 import AdaptadorMT5

        return AdaptadorMT5(
            barramento, symbol=config.symbol, price_grid=config.price_grid()
        )

    raise FonteIndisponivelError(f"fonte desconhecida: {config.fonte!r}")


def _criar_replay(
    config: ConfigOperacao, barramento: Barramento, opcoes: OpcoesReplay
) -> AdaptadorDados:
    if opcoes.caminho is None:
        raise FonteIndisponivelError("replay exige um caminho (arquivo CSV ou diretorio de gravacao)")
    caminho = Path(opcoes.caminho)

    if caminho.is_file():
        if opcoes.de is not None or opcoes.ate is not None:
            # Falha FECHADA: o CSV do núcleo não tem recorte de horário, e
            # ignorar o filtro em silêncio entregaria o dia inteiro fingindo
            # ser a janela pedida.
            raise FonteIndisponivelError(
                "recorte de horario (--de/--ate) so existe no replay de gravacao "
                "(diretorio produzido por scripts/gravar.py); o CSV do nucleo nao "
                "tem indice de tempo"
            )
        return AdaptadorReplay(
            barramento,
            trades_path=caminho,
            deltas_path=opcoes.caminho_deltas,
            velocidade=opcoes.velocidade,
        )

    if not caminho.is_dir():
        raise FonteIndisponivelError(f"caminho de replay inexistente: {caminho}")

    catalogo = Catalogo(caminho)
    entradas = catalogo.escanear()
    disponiveis = [e for e in entradas if e.symbol == config.symbol]
    if not disponiveis:
        simbolos = sorted({e.symbol for e in entradas})
        raise FonteIndisponivelError(
            f"nenhuma gravacao de {config.symbol!r} em {caminho} "
            f"(simbolos gravados: {simbolos or 'nenhum'})"
        )
    dia = opcoes.data if opcoes.data is not None else max(e.data for e in disponiveis)
    entrada, ts_inicio, ts_fim = catalogo.consultar_intervalo(
        config.symbol, dia, opcoes.de, opcoes.ate
    )
    if entrada is None:
        dias = sorted(e.data.isoformat() for e in disponiveis)
        raise FonteIndisponivelError(
            f"{config.symbol} nao tem gravacao em {dia.isoformat()} (dias: {dias})"
        )
    return AdaptadorLeitorGravacao(
        barramento,
        entrada=entrada,
        ts_inicio_ns=ts_inicio,
        ts_fim_ns=ts_fim,
        velocidade=opcoes.velocidade,
        verificar_hash=opcoes.verificar_hash,
        catalogo=catalogo,
    )


def montar(
    config: ConfigOperacao | None = None,
    ao_sinal: Callable[[Sinal], None] | None = None,
    ao_deteccao: Callable[[DeteccaoAnotada], None] | None = None,
    replay: OpcoesReplay | None = None,
    barramento: Barramento | None = None,
) -> Montagem:
    """Instancia tudo, na ordem certa, e liga a fonte no mesmo barramento.

    A ordem importa e está justificada em `app/config.py`. Aqui ela aparece
    como duas linhas: **a `SessaoFluxo` é construída ANTES da fonte**. Não é
    estilo: o `SimuladorWDO` publica no barramento a partir de `iniciar()`, e
    qualquer assinante registrado depois disso perderia os eventos já
    entregues. Construir a fonte primeiro e a sessão depois é uma corrida que
    só não estoura porque `iniciar()` ainda não foi chamado — e "só não estoura
    porque ninguém chamou ainda" não é invariante.
    """
    cfg = config if config is not None else ConfigOperacao()
    bus = barramento if barramento is not None else Barramento()
    sessao = SessaoFluxo(bus, cfg, ao_sinal=ao_sinal, ao_deteccao=ao_deteccao)
    fonte = criar_fonte(cfg, bus, replay)
    if sessao.feed_monitor is not None:
        vincular_monitor = getattr(fonte, "vincular_monitor_feed", None)
        if vincular_monitor is not None:
            vincular_monitor(sessao.feed_monitor)
        else:
            # Simulador e replay são fontes locais: não têm sessão física a
            # autenticar. Mantemos o contrato histórico de prontidão sem
            # confundir a mera assinatura do observador com conexão MT5.
            sessao.feed_monitor.connected("fonte local pronta")
    return Montagem(barramento=bus, sessao=sessao, fonte=fonte)
