"""Montagem: configuração única, ordem de entrega no barramento e fontes.

A ordem de entrega é testada por INSPEÇÃO da lista de assinantes *e* por
comportamento. Só a inspeção não bastaria — ela prende a ordem de registro,
não a consequência dela; só o comportamento também não, porque um pipeline
pode dar o mesmo resultado por acaso num tape específico.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import replace
from datetime import time as hora_do_dia
from pathlib import Path

import pytest

from fluxopro.analytics.agressao import ConfigAgressao
from fluxopro.analytics.brokers import ConfigRankingCorretoras
from fluxopro.analytics.delta import ConfigDelta
from fluxopro.analytics.footprint import ConfigFootprint
from fluxopro.analytics.volume_profile import ConfigVolumeProfile
from fluxopro.analytics.vwap import ConfigVWAP
from fluxopro.app.config import (
    PRIORIDADE_MOTOR,
    ConfigOperacao,
    ConfigSimulador,
    FonteDados,
    grid_para_simbolo,
)
from fluxopro.app.montagem import (
    FonteIndisponivelError,
    OpcoesReplay,
    criar_fonte,
    montar,
)
from fluxopro.core.eventos import WDO_GRID, WIN_GRID, AgressorSide, Trade
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao
from fluxopro.dados.replay import AdaptadorReplay
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.microestrutura.detectores import (
    ConfigAbsorcao,
    ConfigClipInstitucional,
    ConfigEscora,
    ConfigExaustao,
    ConfigIceberg,
    ConfigLiquidezFantasma,
)
from fluxopro.microestrutura.inferencia_mbp import ConfigInferenciaMBP
from fluxopro.microestrutura.livro_mbo import ConfigLivroMBO
from fluxopro.motor.sinais import ConfigMotorSinais

SYMBOL = "WDOV26"


def config_curta(**kwargs) -> ConfigOperacao:
    base = dict(
        symbol=SYMBOL,
        simulador=ConfigSimulador(seed=42, n_eventos=300),
    )
    base.update(kwargs)
    return ConfigOperacao(**base)  # type: ignore[arg-type]


def donos(barramento, tipo) -> list[tuple[str, str]]:
    """(classe, método) de cada assinante, na ordem em que serão chamados."""
    saida = []
    for assinatura in barramento._assinantes[tipo]:
        cb = assinatura.callback
        dono = getattr(cb, "__self__", None)
        saida.append((type(dono).__name__ if dono is not None else "-", cb.__name__))
    return saida


# ---------------------------------------------------------------------------
# Ordem de entrega
# ---------------------------------------------------------------------------


def test_ordem_de_entrega_no_barramento_para_trade():
    """Prende a cadeia inteira: núcleo -> analytics -> perfil de sessão ->
    microestrutura -> motor -> contagem.

    Este teste existe porque a ordem das quatro primeiras peças NÃO pode ser
    declarada por prioridade: `EstadoMercado` e os analytics assinam a si
    mesmos no construtor sem parâmetro de prioridade (ver `app/config.py`,
    "LIMITAÇÃO REAL"). A única alavanca é a ordem de construção — e ordem de
    construção implícita é exatamente o tipo de invariante que se perde numa
    refatoração distraída. Aqui ela vira teste.
    """
    montagem = montar(config_curta())
    assert donos(montagem.barramento, Trade) == [
        ("EstadoMercado", "_ao_trade"),
        ("VolumeProfilePorPeriodo", "_ao_trade"),
        ("FootprintPorTimeframe", "_ao_trade"),
        ("CumulativeDelta", "_ao_trade"),
        ("MedidorAgressao", "_ao_trade"),
        ("VWAP", "_ao_trade"),
        ("RankingCorretoras", "_ao_trade"),
        ("SessaoFluxo", "_ao_trade_perfil_sessao"),
        ("SessaoFluxo", "_ao_trade_micro"),
        ("SessaoFluxo", "_ao_trade_detectores_tape"),
        ("SessaoFluxo", "_ao_trade_perfil_player"),
        ("SessaoFluxo", "_ao_trade_motor"),
        ("SessaoFluxo", "_contar_trade"),
    ]


def test_o_perfil_de_sessao_ja_inclui_o_trade_quando_o_motor_roda():
    """A seta load-bearing da condição 2, provada por comportamento.

    Se o motor rodasse antes do perfil, `_na_regiao` responderia sobre o
    mercado de um trade atrás. A sonda entra logo antes do motor (prioridade
    `PRIORIDADE_MOTOR - 1`) e exige que o volume do trade corrente JÁ esteja
    no perfil que o motor vai ler.
    """
    montagem = montar(config_curta())
    sessao = montagem.sessao
    visto: list[tuple[int, int]] = []

    def sonda(trade: Trade) -> None:
        visto.append((sessao.perfil_sessao.volume_total, trade.qty))

    montagem.barramento.assinar(Trade, sonda, prioridade=PRIORIDADE_MOTOR - 1)

    acumulado = 0
    for i, qty in enumerate((5, 7, 3), start=1):
        acumulado += qty
        montagem.barramento.publicar(
            Trade(i * 1_000_000, SYMBOL, 10_000, qty, AgressorSide.BUY, f"t{i}")
        )
        assert visto[-1] == (acumulado, qty)


def test_o_livro_ja_foi_alimentado_quando_o_motor_roda():
    """A segunda seta load-bearing: `InferidorMBP` (prioridade MICRO) roda
    antes do motor (prioridade MOTOR), então o livro que qualquer consumidor
    a jusante lê é o do evento corrente, não o do anterior."""
    montagem = montar(config_curta())
    ordem = [nome for _, nome in donos(montagem.barramento, Trade)]
    assert ordem.index("_ao_trade_micro") < ordem.index("_ao_trade_motor")


# ---------------------------------------------------------------------------
# ConfigOperacao
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, classe",
    [
        ("volume_profile", ConfigVolumeProfile),
        ("footprint", ConfigFootprint),
        ("delta", ConfigDelta),
        ("agressao", ConfigAgressao),
        ("vwap", ConfigVWAP),
        ("brokers", ConfigRankingCorretoras),
        ("livro", ConfigLivroMBO),
        ("inferencia", ConfigInferenciaMBP),
        ("absorcao", ConfigAbsorcao),
        ("escora", ConfigEscora),
        ("iceberg", ConfigIceberg),
        ("liquidez_fantasma", ConfigLiquidezFantasma),
        ("exaustao", ConfigExaustao),
        ("clip_institucional", ConfigClipInstitucional),
        ("motor", ConfigMotorSinais),
    ],
)
def test_config_operacao_nao_redigita_nenhum_default(campo, classe):
    """Cada sub-config tem de ser IGUAL ao default do módulo dono.

    Se alguém "documentasse" um limiar copiando o número para cá, o default do
    módulo poderia mudar e a montagem continuaria operando com o valor velho —
    em silêncio. Isto é a trava contra isso.
    """
    assert getattr(ConfigOperacao(), campo) == classe()


def test_config_operacao_e_sobrescrivel_em_qualquer_nivel():
    cfg = ConfigOperacao(
        symbol="WINZ26",
        motor=ConfigMotorSinais(dominancia_minima=0.75, janela_dominancia_ns=3_000_000_000),
    )
    assert cfg.motor.dominancia_minima == 0.75
    # o que não foi tocado continua vindo do módulo dono
    assert cfg.motor.magnitude_relativa_minima == ConfigMotorSinais().magnitude_relativa_minima
    assert cfg.price_grid() == WIN_GRID


def test_a_calibracao_chega_de_fato_aos_componentes():
    """Config não é decoração: o objeto configurado é o que a peça recebe."""
    cfg = config_curta(
        motor=ConfigMotorSinais(dominancia_minima=0.9),
        absorcao=ConfigAbsorcao(volume_minimo=7),
        livro=ConfigLivroMBO(janela_reposicao_ns=123),
        inferencia=ConfigInferenciaMBP(janela_reconciliacao_ns=456),
    )
    sessao = montar(cfg).sessao
    assert sessao.motor is not None and sessao.motor.config.dominancia_minima == 0.9
    assert sessao.det_absorcao is not None and sessao.det_absorcao.config.volume_minimo == 7
    assert sessao.livro is not None and sessao.livro.config.janela_reposicao_ns == 123
    assert sessao.inferidor is not None
    assert sessao.inferidor.config.janela_reconciliacao_ns == 456


def test_grid_deriva_do_simbolo_e_pode_ser_forcado():
    assert grid_para_simbolo("WDOV26") == WDO_GRID
    assert grid_para_simbolo("winz26") == WIN_GRID
    assert ConfigOperacao(symbol="WINZ26").price_grid() == WIN_GRID
    assert ConfigOperacao(symbol="WINZ26", grid=WDO_GRID).price_grid() == WDO_GRID


def test_estagios_desligados_nao_instanciam_a_peca():
    sessao = montar(
        config_curta(
            ligar_analytics=False,
            ligar_microestrutura=False,
            ligar_detectores_tape=False,
            ligar_motor=False,
        )
    ).sessao
    assert sessao.volume_profile is None
    assert sessao.vwap is None
    assert sessao.livro is None
    assert sessao.inferidor is None
    assert sessao.det_absorcao is None
    assert sessao.motor is None
    # o que NÃO é opcional continua de pé
    assert sessao.estado is not None
    assert sessao.perfil_sessao is not None


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------


def test_simulador_roda_sem_mt5_instalado():
    """O requisito do dono: ver o sistema funcionando hoje, sem corretora.

    A checagem é sobre `sys.modules`: montar a fonte de simulador não pode ter
    importado o pacote `MetaTrader5` nem sequer indiretamente — é isso que faz
    o produto abrir numa máquina sem terminal instalado.
    """
    montagem = montar(config_curta())
    assert isinstance(montagem.fonte, SimuladorWDO)
    assert "MetaTrader5" not in sys.modules
    montagem.fonte.iniciar()
    assert montagem.sessao.contadores.n_trades_bus == 300


def test_simulador_respeita_tick_size_do_simbolo():
    """WIN tem tick 5.0; passar o grid errado deslocaria todo o preço."""
    montagem = montar(
        ConfigOperacao(symbol="WINZ26", simulador=ConfigSimulador(n_eventos=50))
    )
    montagem.fonte.iniciar()
    ultimo = montagem.sessao.estado.ultimo_trade
    assert ultimo is not None
    # preco_inicial 5000.0 / tick 5.0 = 1000 ticks (e nao 10.000 do grid do WDO)
    assert abs(ultimo.price - 1000) < 200


def _escrever_csv_trades(caminho: Path, n: int = 5) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(
            ["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id"]
        )
        for i in range(n):
            w.writerow([i * 1_000_000, SYMBOL, 10_000 + i, 5, "BUY", f"t{i}"])


def test_replay_de_csv(tmp_path: Path):
    caminho = tmp_path / "trades.csv"
    _escrever_csv_trades(caminho)
    montagem = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=caminho),
    )
    assert isinstance(montagem.fonte, AdaptadorReplay)
    montagem.fonte.iniciar()
    assert montagem.sessao.contadores.n_trades_bus == 5


def test_recorte_de_horario_em_csv_falha_fechado(tmp_path: Path):
    """O CSV do núcleo não tem índice de tempo. Aceitar `--de/--ate` e
    entregar o arquivo inteiro seria mentir sobre o recorte."""
    caminho = tmp_path / "trades.csv"
    _escrever_csv_trades(caminho)
    with pytest.raises(FonteIndisponivelError, match="recorte de horario"):
        montar(
            config_curta(fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=caminho, de=hora_do_dia(9, 0)),
        )


def test_replay_sem_caminho_e_erro_explicito():
    with pytest.raises(FonteIndisponivelError, match="caminho"):
        montar(config_curta(fonte=FonteDados.REPLAY))


def test_replay_de_caminho_inexistente_e_erro_explicito(tmp_path: Path):
    with pytest.raises(FonteIndisponivelError, match="inexistente"):
        montar(
            config_curta(fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=tmp_path / "nao_existe"),
        )


def test_replay_de_gravacao_encontra_o_dia_e_o_recorte(tmp_path: Path):
    """Fecha o ciclo com o `Gravador`: grava com o pipeline ligado, relê a
    gravação pelo catálogo (com verificação de hash) e confere o recorte."""
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    montagem = montar(config_curta(simulador=ConfigSimulador(seed=1, n_eventos=200)))
    gravador = Gravador(montagem.barramento, gravacao)
    gravador.iniciar()
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    gravador.parar()

    lido = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao),
    )
    assert isinstance(lido.fonte, AdaptadorLeitorGravacao)
    lido.fonte.iniciar()
    assert lido.sessao.contadores.n_trades_bus == 200
    assert lido.sessao.contadores.n_snapshots_bus == 200


def test_replay_de_gravacao_sem_o_simbolo_diz_o_que_existe(tmp_path: Path):
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    montagem = montar(config_curta(simulador=ConfigSimulador(n_eventos=20)))
    gravador = Gravador(montagem.barramento, gravacao)
    gravador.iniciar()
    montagem.fonte.iniciar()
    gravador.parar()

    with pytest.raises(FonteIndisponivelError, match="OUTRO"):
        montar(
            config_curta(symbol="OUTRO", fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=gravacao),
        )


def test_fonte_desconhecida_e_erro():
    cfg = config_curta()
    quebrada = replace(cfg, fonte="nao_e_uma_fonte")  # type: ignore[arg-type]
    from fluxopro.core.barramento import Barramento

    with pytest.raises(FonteIndisponivelError):
        criar_fonte(quebrada, Barramento())
