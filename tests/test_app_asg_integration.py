"""Costura ASG-like: sessão, barramento, sidecar, workspace e janela.

Estes testes exercitam somente contratos públicos ou estado de apresentação
congelado. Nenhum deles substitui feed, Maker ou decisão por mocks: os quadros
nascem de ``BookSnapshot`` e ``Trade`` reais publicados no barramento do app.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path

from fluxopro.app.config import ConfigOperacao, FonteDados
from fluxopro.app.sessao_fluxo import RetratoASG, SessaoFluxo
from fluxopro.asg import EstadoMaker
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.dados.qualidade import FeedQualitySnapshot
from fluxopro.shadow import ConfigShadow


SYMBOL = "WDOV26"
T0 = 1_777_200_000_000_000_000
PRICE = 10_000


def _trade(timestamp_ns: int, *, suffix: str = "0", price: int = PRICE) -> Trade:
    return Trade(
        timestamp_ns=timestamp_ns,
        symbol=SYMBOL,
        price=price,
        qty=25,
        side_agressor=AgressorSide.BUY,
        trade_id=f"asg-{suffix}",
    )


def _book(timestamp_ns: int, *, price: int = PRICE) -> BookSnapshot:
    return BookSnapshot(
        timestamp_ns=timestamp_ns,
        symbol=SYMBOL,
        bids=(BookLevel(price - 1, 120, 3), BookLevel(price - 2, 80, 2)),
        asks=(BookLevel(price + 1, 110, 3), BookLevel(price + 2, 70, 2)),
    )


def _config_asg(**changes: object) -> ConfigOperacao:
    """Config pequena, mas com a cadeia motor/metodologia/ASG real ligada."""

    base = ConfigOperacao(
        symbol=SYMBOL,
        fonte=FonteDados.SIMULADOR,
        ligar_analytics=False,
        ligar_microestrutura=False,
        ligar_detectores_tape=False,
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
        ligar_leitura_asg=True,
    )
    return replace(base, **changes)


def _publicar_quadro(
    barramento: Barramento,
    timestamp_ns: int,
    *,
    suffix: str = "0",
    price: int = PRICE,
) -> None:
    barramento.publicar(_book(timestamp_ns, price=price))
    barramento.publicar(_trade(timestamp_ns, suffix=suffix, price=price))


def _assert_retrato_coerente(retrato: RetratoASG, timestamp_ns: int) -> None:
    assert retrato.timestamp_ns == timestamp_ns
    assert {
        retrato.timestamp_ns,
        retrato.feed_quality.market_timestamp_ns,
        retrato.maker.timestamp_ns,
        retrato.leitura.timestamp_ns,
        retrato.regiao.timestamp_ns,
        retrato.decisao.timestamp_ns,
    } == {timestamp_ns}
    assert {
        retrato.symbol,
        retrato.feed_quality.symbol,
        retrato.maker.symbol,
        retrato.leitura.symbol,
        retrato.regiao.symbol,
        retrato.decisao.symbol,
    } == {SYMBOL}


def test_defaults_asg_desligados_preservam_pipeline_historico() -> None:
    config = ConfigOperacao(symbol=SYMBOL)
    barramento = Barramento()
    sessao = SessaoFluxo(barramento, config)
    try:
        assert not config.ligar_feed_quality
        assert not config.ligar_maker_proxy
        assert not config.ligar_leitura_asg
        assert not config.ligar_shadow_learning
        assert sessao.feed_monitor is None
        assert sessao.feed_observer is None
        assert sessao.maker_proxy is None
        assert sessao.motor_decisao_asg is None
        assert sessao.shadow is None
        assert sessao.retrato_asg() is None

        # Os elos históricos continuam montados e processam o evento normal.
        assert sessao.estado is not None
        assert sessao.volume_profile is not None
        assert sessao.livro is not None
        assert sessao.motor is not None
        assert sessao.metodo is not None
        _publicar_quadro(barramento, T0)
        assert sessao.contadores.n_trades_bus == 1
        assert sessao.estado.ultimo_trade == _trade(T0)
        assert sessao.retrato_asg() is None
    finally:
        sessao.finalizar(T0)


def test_flags_explicitas_ligam_feed_maker_leitura_e_um_retrato_por_trade() -> None:
    barramento = Barramento()
    sessao = SessaoFluxo(barramento, _config_asg())
    try:
        assert sessao.feed_monitor is not None
        assert sessao.feed_observer is not None
        assert sessao.maker_proxy is not None
        assert sessao.motor_decisao_asg is not None

        _publicar_quadro(barramento, T0, suffix="primeiro")
        primeiro = sessao.retrato_asg()
        assert primeiro is not None
        _assert_retrato_coerente(primeiro, T0)

        _publicar_quadro(barramento, T0 + 1_000_000_000, suffix="segundo", price=PRICE + 1)
        segundo = sessao.retrato_asg()
        assert segundo is not None
        assert segundo is not primeiro
        _assert_retrato_coerente(segundo, T0 + 1_000_000_000)
        # O quadro anterior é imutável e não foi costurado com o trade novo.
        _assert_retrato_coerente(primeiro, T0)
    finally:
        sessao.finalizar(T0 + 1_000_000_000)


def test_feed_observer_e_lido_diretamente_sem_publicacao_aninhada() -> None:
    barramento = Barramento()
    snapshots_publicados: list[FeedQualitySnapshot] = []
    barramento.assinar(FeedQualitySnapshot, snapshots_publicados.append)
    sessao = SessaoFluxo(barramento, _config_asg())
    try:
        _publicar_quadro(barramento, T0)

        qualidade = sessao.feed_quality()
        assert qualidade is not None
        assert qualidade.market_timestamp_ns == T0
        assert qualidade.received_events == 2
        assert snapshots_publicados == []
    finally:
        sessao.finalizar(T0)


def test_trade_regressivo_nao_cria_retrato_asg_novo() -> None:
    barramento = Barramento()
    sessao = SessaoFluxo(barramento, _config_asg())
    try:
        _publicar_quadro(barramento, T0, suffix="causal")
        causal = sessao.retrato_asg()
        assert causal is not None

        barramento.publicar(_trade(T0 - 1, suffix="regressivo"))

        assert sessao.retrato_asg() is causal
        assert sessao.maker_proxy is not None
        assert sessao.maker_proxy.snapshot().timestamp_ns == T0
        assert sessao.maker_proxy.snapshot().discarded_regressive >= 1
        qualidade = sessao.feed_quality()
        assert qualidade is not None
        assert qualidade.regressive_timestamps >= 1
    finally:
        sessao.finalizar(T0)


def test_reset_limpa_retrato_e_estado_causal_do_maker() -> None:
    barramento = Barramento()
    sessao = SessaoFluxo(barramento, _config_asg())
    try:
        _publicar_quadro(barramento, T0)
        assert sessao.retrato_asg() is not None
        assert sessao.maker_proxy is not None
        assert sessao.maker_proxy.n_trades_retidos == 1

        sessao.iniciar_nova_sessao(T0 + 1)

        assert sessao.retrato_asg() is None
        assert sessao.maker_proxy.n_trades_retidos == 0
        maker = sessao.maker_proxy.snapshot()
        assert maker.timestamp_ns == 0
        assert maker.estado is EstadoMaker.SEM_DADOS
        assert maker.discarded_duplicates == 0
        assert maker.discarded_regressive == 0
    finally:
        sessao.finalizar(T0 + 1)


def test_shadow_so_grava_com_flag_e_diretorio(tmp_path: Path) -> None:
    desabilitado_dir = tmp_path / "desabilitado"
    bus_sem_flag = Barramento()
    sem_flag = SessaoFluxo(
        bus_sem_flag,
        _config_asg(ligar_shadow_learning=False, shadow_dir=str(desabilitado_dir)),
    )
    _publicar_quadro(bus_sem_flag, T0)
    sem_flag.finalizar(T0)
    assert sem_flag.shadow is None
    assert not desabilitado_dir.exists()

    bus_sem_dir = Barramento()
    sem_dir = SessaoFluxo(
        bus_sem_dir,
        _config_asg(ligar_shadow_learning=True, shadow_dir=None),
    )
    _publicar_quadro(bus_sem_dir, T0)
    sem_dir.finalizar(T0)
    assert sem_dir.shadow is None

    habilitado_dir = tmp_path / "habilitado"
    bus_habilitado = Barramento()
    habilitado = SessaoFluxo(
        bus_habilitado,
        _config_asg(
            ligar_shadow_learning=True,
            shadow_dir=str(habilitado_dir),
            shadow=ConfigShadow(horizontes_s=(1,)),
        ),
    )
    assert habilitado.shadow is not None
    _publicar_quadro(bus_habilitado, T0)
    habilitado.finalizar(T0)

    arquivos = list(habilitado_dir.rglob("features.jsonl.gz"))
    assert len(arquivos) == 1
    with gzip.open(arquivos[0], "rt", encoding="utf-8") as stream:
        registros = [json.loads(line) for line in stream if line.strip()]
    assert len(registros) == 1
    assert registros[0]["timestamp_ns"] == T0
    assert registros[0]["symbol"] == SYMBOL
    assert registros[0]["modo"] == "shadow"
    assert registros[0]["promocao_automatica"] is False


def test_workspace_ctrl_5_estende_sem_alterar_os_quatro_historicos() -> None:
    from fluxopro.ui.workspace import (
        NOMES_DE_FABRICA,
        WORKSPACE_ASG,
        WORKSPACES_DE_FABRICA,
        WORKSPACES_DISPONIVEIS,
        por_atalho,
    )

    assert NOMES_DE_FABRICA == ("Fluxo", "Book & Tape", "Bookmap", "Revisão")
    assert tuple((w.nome, w.atalho) for w in WORKSPACES_DE_FABRICA) == (
        ("Fluxo", 1),
        ("Book & Tape", 2),
        ("Bookmap", 3),
        ("Revisão", 4),
    )
    assert WORKSPACES_DISPONIVEIS[:4] == WORKSPACES_DE_FABRICA
    assert WORKSPACES_DISPONIVEIS[4] is WORKSPACE_ASG
    assert por_atalho(5) is WORKSPACE_ASG
    assert "asg" in WORKSPACE_ASG.docas


def test_janela_aplica_asg_somente_quando_workspace_esta_ativo(qapp) -> None:
    from PySide6.QtGui import QKeySequence

    from fluxopro.ui.janela import JanelaFluxo
    from fluxopro.ui.ponte import PonteFluxo
    from fluxopro.ui.workspace import WORKSPACE_ASG, WORKSPACES_DE_FABRICA

    barramento = Barramento()
    ponte = PonteFluxo(barramento)
    config = _config_asg()
    sessao = SessaoFluxo(barramento, config)
    janela = JanelaFluxo(
        ponte,
        SYMBOL,
        config.price_grid(),
        sessao=sessao,
        config=config,
        persistir=False,
    )
    try:
        assert janela.workspace is WORKSPACES_DE_FABRICA[0]
        assert any(
            atalho.key() == QKeySequence("Ctrl+5") for atalho in janela._atalhos
        )

        _publicar_quadro(barramento, T0, suffix="ui-oculto")
        janela._tick()
        assert janela.asg._snapshot is None

        assert janela.workspace_por_atalho(5)
        assert janela.workspace is WORKSPACE_ASG
        janela._tick()
        aplicado = janela.asg._snapshot
        assert aplicado is not None
        assert aplicado.timestamp_ns == T0

        assert janela.workspace_por_atalho(1)
        _publicar_quadro(
            barramento,
            T0 + 1_000_000_000,
            suffix="ui-oculto-de-novo",
            price=PRICE + 1,
        )
        janela._tick()
        assert janela.asg._snapshot is aplicado
    finally:
        janela.close()
        sessao.finalizar(T0 + 1_000_000_000)
