from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields

import pytest

from fluxopro.asg import (
    ComponenteMaker, ConfigMakerProxy, EstadoMaker, MakerEvidence, MakerProxy,
    LeituraASG, MotorDecisaoASG, NivelDecisao, ProcedenciaASG,
    RegiaoOperacional,
)
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.dados.qualidade import (
    AggressorQuality, BookKind, FeedQualitySnapshot, FeedSource, FeedState,
)
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao

SYMBOL = "WDOV26"
S = 1_000_000_000


def _trade(ts: int, side: AgressorSide, qty: int = 300, trade_id: str | None = None) -> Trade:
    return Trade(ts, SYMBOL, 10_000, qty, side, trade_id or f"t{ts}-{side.value}")


def _feed(
    ts: int | None,
    *,
    book: BookKind = BookKind.MBO,
    state: FeedState = FeedState.CONNECTED,
    latency: int | None = 0,
    aggressor: AggressorQuality = AggressorQuality.NATIVE,
    source: FeedSource = FeedSource.MT5,
    received: int = 0,
    accepted: int = 0,
    anomalies: int = 0,
    ingress_ts: int | None = None,
) -> FeedQualitySnapshot:
    dados = {
        "symbol": SYMBOL, "state": state, "source": source,
        "book_kind": book, "depth": 20 if book is not BookKind.NONE else 0,
        "aggressor_quality": aggressor, "latency_ns": latency,
        "received_events": received, "accepted_events": accepted,
    }
    nomes = {campo.name for campo in fields(FeedQualitySnapshot)}
    if "anomalies" in nomes:
        dados["anomalies"] = anomalies
    if "ingress_timestamp_ns" in nomes:
        dados.update(
            market_timestamp_ns=ts,
            ingress_timestamp_ns=ts if ingress_ts is None else ingress_ts,
        )
    else:
        dados["timestamp_ns"] = ts if ts is not None else (ingress_ts or 0)
    return FeedQualitySnapshot(**dados)


def _evidencia(
    ts: int,
    componente: ComponenteMaker,
    score: float,
    *,
    confianca: float = 1.0,
    procedencia: ProcedenciaASG = ProcedenciaASG.OBSERVADA,
) -> MakerEvidence:
    return MakerEvidence(
        timestamp_ns=ts, symbol=SYMBOL, componente=componente,
        pontuacao=score, confianca=confianca, procedencia=procedencia,
        fonte="MBO" if procedencia is ProcedenciaASG.OBSERVADA else "MBP_INFERIDO",
        tipo_evento="TESTE", preco_ticks=10_000,
        detalhes={"nested": {"ids": [1, 2]}},
    )


def _alimentar_componentes(proxy: MakerProxy, ts: int, scores: dict[ComponenteMaker, float]) -> None:
    if ComponenteMaker.AGRESSAO in scores:
        lado = AgressorSide.BUY if scores[ComponenteMaker.AGRESSAO] >= 0 else AgressorSide.SELL
        proxy.ao_trade(_trade(ts, lado, trade_id=f"tape-{ts}"))
    for componente, score in scores.items():
        if componente is not ComponenteMaker.AGRESSAO:
            proxy.registrar_evidencia(_evidencia(ts, componente, score))


def _maker_estavel(
    *,
    book: BookKind = BookKind.MBO,
    scores: dict[ComponenteMaker, float] | None = None,
) -> tuple[MakerProxy, object]:
    scores = scores or {componente: 1.0 for componente in ComponenteMaker}
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0, book=book))
    _alimentar_componentes(proxy, 0, scores)
    proxy.ao_feed_quality(_feed(3 * S, book=book))
    _alimentar_componentes(proxy, 3 * S, scores)
    return proxy, proxy.snapshot()


def test_defaults_exatos_do_briefing():
    cfg = ConfigMakerProxy()
    assert (cfg.janela_curta_ns, cfg.janela_micro_ns, cfg.janela_contexto_ns) == (S, 5 * S, 30 * S)
    assert cfg.persistencia_minima_ns == 3 * S
    assert cfg.intervalo_persistencia_ns == 1_000_000
    assert cfg.relevancia_minima == 0.07
    assert cfg.confianca_minima == 0.60
    assert dict(cfg.pesos) == {
        ComponenteMaker.ABSORCAO: 0.30,
        ComponenteMaker.REPOSICAO: 0.30,
        ComponenteMaker.DIVERGENCIA: 0.20,
        ComponenteMaker.CLIPS: 0.10,
        ComponenteMaker.AGRESSAO: 0.10,
    }
    assert cfg.janela_agressao_ns == cfg.janela_micro_ns
    assert cfg.janela_evidencia_ns == cfg.janela_contexto_ns


def test_trade_id_duplicado_nao_dobra_volume_nem_persistencia():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    trade = _trade(0, AgressorSide.BUY, 300, "dup-1")
    primeiro = proxy.ao_trade(trade)
    segundo = proxy.ao_trade(trade)
    assert primeiro is not None and segundo is not None
    assert proxy.n_trades_retidos == 1
    assert proxy.n_trade_ids_retidos == 1
    assert segundo.discarded_duplicates == 1
    agressao = segundo.componente(ComponenteMaker.AGRESSAO)
    assert agressao.evidencias[0].detalhes["volume_total"] == 300
    assert segundo.persistence_ns == primeiro.persistence_ns


def test_hot_path_de_trade_materializa_persistencia_sem_snapshot_por_tick():
    """A sessão usa ``ingerir_trade``; esse caminho não pode zerar o Maker."""

    proxy = MakerProxy(SYMBOL)
    assert proxy.ingerir_feed_quality(_feed(0))
    assert proxy.ingerir_trade(_trade(0, AgressorSide.BUY, 300, "hot-0"))
    assert proxy.ingerir_feed_quality(_feed(3 * S))
    assert proxy.ingerir_trade(_trade(3 * S, AgressorSide.BUY, 300, "hot-3"))

    snapshot = proxy.snapshot()
    assert proxy.n_amostras_persistencia == 2
    assert snapshot.persistence_ns == 3 * S
    assert snapshot.stability == pytest.approx(1.0)


def test_timestamp_regressivo_e_rejeitado_sem_reter_evento_ou_evidencia():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(100))
    proxy.ao_trade(_trade(100, AgressorSide.BUY, trade_id="novo"))
    antes = proxy.n_trades_retidos
    regressivo = proxy.ao_trade(_trade(1, AgressorSide.SELL, trade_id="velho"))
    assert regressivo is not None
    assert proxy.n_trades_retidos == antes
    assert proxy.n_trade_ids_retidos == 1
    assert regressivo.discarded_regressive == 1
    proxy.registrar_evidencia(_evidencia(0, ComponenteMaker.ABSORCAO, -1))
    assert proxy.n_evidencias_retidas == 0


def test_feed_regressivo_nao_troca_relogio_causal_nem_produz_a3_saudavel():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(100 * S, ingress_ts=100 * S))
    _alimentar_componentes(proxy, 100 * S, {c: 1.0 for c in ComponenteMaker})
    proxy.ao_feed_quality(_feed(103 * S, ingress_ts=103 * S))
    _alimentar_componentes(proxy, 103 * S, {c: 1.0 for c in ComponenteMaker})
    saudavel = proxy.snapshot()
    assert saudavel.timestamp_ns == 103 * S
    assert saudavel.estado is EstadoMaker.COMPRADOR

    regressivo = proxy.ao_feed_quality(_feed(
        50 * S, ingress_ts=104 * S, source=FeedSource.SIMULATOR,
    ))
    assert regressivo is not None
    assert regressivo.timestamp_ns == 103 * S
    assert regressivo.discarded_regressive == 1
    assert regressivo.estado is EstadoMaker.SEM_BOOK
    assert regressivo.book_delayed is True
    assert regressivo.confidence == 0.0
    assert regressivo.source == "MT5"  # feed causal aceito nao foi substituido

    leitura = LeituraASG.do_maker(
        regressivo,
        placar={"timestamp_ns": 103 * S, "comprador": 4, "vendedor": 1},
        feed_quality={"timestamp_ns": 103 * S, "source": "MT5", "book_kind": "MBO"},
    )
    regiao = RegiaoOperacional(
        symbol=SYMBOL, timestamp_ns=103 * S, inicio_ticks=9_999,
        fim_ticks=10_001, confianca=1.0,
        procedencia=ProcedenciaASG.OBSERVADA, invalidacao_ticks=9_999,
    )
    decisao = MotorDecisaoASG().avaliar(leitura, regiao, 10_000)
    assert decisao.nivel is NivelDecisao.AGUARDAR
    assert decisao.confirmacao is False


def test_feed_sem_market_timestamp_atualiza_saude_sem_avancar_relogio():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(103 * S, ingress_ts=103 * S))
    _alimentar_componentes(proxy, 103 * S, {c: 1.0 for c in ComponenteMaker})

    sem_market = proxy.ao_feed_quality(_feed(
        None, ingress_ts=104 * S, state=FeedState.ERROR, book=BookKind.NONE,
    ))
    assert sem_market is not None
    assert sem_market.timestamp_ns == 103 * S
    assert sem_market.estado is EstadoMaker.SEM_BOOK
    assert sem_market.book_kind == "NONE"
    assert sem_market.feed_quality == 0.0
    assert sem_market.discarded_regressive == 0


def test_feed_conectado_sem_market_timestamp_bloqueia_a3():
    proxy, saudavel = _maker_estavel()
    assert saudavel.estado is EstadoMaker.COMPRADOR

    sem_market = proxy.ao_feed_quality(_feed(
        None,
        ingress_ts=200 * S,
        state=FeedState.CONNECTED,
        book=BookKind.MBO,
    ))
    assert sem_market is not None
    assert sem_market.timestamp_ns == 3 * S
    assert sem_market.estado is EstadoMaker.SEM_BOOK
    assert sem_market.book_delayed is True
    assert sem_market.feed_quality == 0.0

    leitura = LeituraASG.do_maker(sem_market)
    regiao = RegiaoOperacional(
        SYMBOL, 3 * S, 9_999, 10_001,
        procedencia=ProcedenciaASG.OBSERVADA,
        invalidacao_ticks=9_999,
    )
    decisao = MotorDecisaoASG().avaliar(leitura, regiao, 10_000)
    assert decisao.nivel is NivelDecisao.AGUARDAR
    assert not decisao.confirmacao
    assert "BOOK_ATRASADO" in decisao.bloqueios


def test_ingress_e_snapshot_local_nao_avancam_expiracao_causal():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(103 * S, ingress_ts=103 * S))
    proxy.ao_trade(_trade(103 * S, AgressorSide.BUY, trade_id="causal"))

    proxy.ao_feed_quality(_feed(None, ingress_ts=200 * S))
    snapshot = proxy.snapshot(300 * S)
    assert snapshot.timestamp_ns == 103 * S
    assert proxy.n_trades_retidos == 1


def test_timestamp_igual_com_ids_distintos_e_aceito():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_trade(_trade(10, AgressorSide.BUY, trade_id="a"))
    proxy.ao_trade(_trade(10, AgressorSide.BUY, trade_id="b"))
    assert proxy.n_trades_retidos == 2


def test_um_componente_renormaliza_direcao_mas_nao_infla_confianca():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    proxy.registrar_evidencia(_evidencia(0, ComponenteMaker.ABSORCAO, 1))
    proxy.ao_feed_quality(_feed(3 * S))
    snapshot = proxy.registrar_evidencia(_evidencia(3 * S, ComponenteMaker.ABSORCAO, 1))
    assert snapshot is not None
    assert snapshot.componente(ComponenteMaker.ABSORCAO).peso_efetivo == 1.0
    assert snapshot.percent == pytest.approx(100.0)
    assert snapshot.component_coverage == pytest.approx(0.30)
    assert snapshot.confidence == pytest.approx(0.30)  # feed 1 × cobertura .30 × estabilidade 1
    assert snapshot.estado is EstadoMaker.AJUSTANDO


def test_mbo_observado_estavel_confirma_estado_comprador_e_aliases():
    _, snapshot = _maker_estavel()
    assert snapshot.state is EstadoMaker.COMPRADOR
    assert snapshot.side is Side.BUY
    assert snapshot.percent == pytest.approx(100.0)
    assert snapshot.persistence_ns >= 3 * S
    assert snapshot.source == "MT5"
    assert snapshot.book_kind == "MBO"
    assert snapshot.inferred is False
    assert snapshot.confidence == pytest.approx(1.0)
    assert snapshot.component_coverage == 1.0
    assert snapshot.evidence and isinstance(snapshot.evidence, tuple)
    assert snapshot.component_scores is snapshot.componentes
    assert snapshot.pontuacao == pytest.approx(1.0)
    assert snapshot.confianca == snapshot.confidence


def test_mbp_inferido_reduz_confianca_sem_apagar_direcao():
    _, snapshot = _maker_estavel(book=BookKind.MBP)
    assert snapshot.inferred is True
    assert snapshot.book_kind == "MBP"
    assert snapshot.side is Side.BUY
    assert snapshot.confidence == pytest.approx(0.75)
    assert snapshot.confidence < 1.0


def test_evidencia_inferida_reduz_qualidade_mesmo_se_feed_declara_mbo():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    proxy.registrar_evidencia(_evidencia(
        0, ComponenteMaker.ABSORCAO, 1, procedencia=ProcedenciaASG.INFERIDA
    ))
    proxy.ao_feed_quality(_feed(3 * S))
    snapshot = proxy.registrar_evidencia(_evidencia(
        3 * S, ComponenteMaker.ABSORCAO, 1, procedencia=ProcedenciaASG.INFERIDA
    ))
    assert snapshot is not None and snapshot.inferred
    assert snapshot.feed_quality == pytest.approx(0.75)
    assert snapshot.confidence == pytest.approx(0.75 * 0.30)


def test_book_ausente_e_book_atrasado_impedem_confirmacao_do_maker():
    proxy, _ = _maker_estavel()
    sem_book = proxy.ao_feed_quality(_feed(4 * S, book=BookKind.NONE))
    assert sem_book is not None
    assert sem_book.estado is EstadoMaker.SEM_BOOK
    assert sem_book.confidence == 0.0
    atrasado = proxy.ao_feed_quality(_feed(5 * S, latency=2 * S))
    assert atrasado is not None
    assert atrasado.estado is EstadoMaker.SEM_BOOK
    assert atrasado.book_delayed is True
    assert atrasado.confidence == 0.0
    desconhecida = proxy.ao_feed_quality(_feed(6 * S, latency=None))
    assert desconhecida is not None
    assert desconhecida.book_delayed and desconhecida.confidence == 0.0


def test_replay_sem_latencia_de_rede_nao_e_rotulado_como_book_atrasado():
    proxy = MakerProxy(SYMBOL)
    snapshot = proxy.ao_feed_quality(_feed(
        0, latency=None, source=FeedSource.REPLAY
    ))
    assert snapshot is not None
    assert snapshot.source == "REPLAY"
    assert snapshot.book_delayed is False


def test_estado_ajustando_ate_tres_segundos_de_persistencia():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    _alimentar_componentes(proxy, 0, {c: 1.0 for c in ComponenteMaker})
    snapshot = proxy.snapshot()
    assert snapshot.estado is EstadoMaker.AJUSTANDO
    assert snapshot.persistence_ns == 0


def test_estado_neutro_com_componentes_cobertos_e_estaveis():
    scores = {c: 0.0 for c in ComponenteMaker if c is not ComponenteMaker.AGRESSAO}
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    _alimentar_componentes(proxy, 0, scores)
    proxy.ao_feed_quality(_feed(3 * S))
    _alimentar_componentes(proxy, 3 * S, scores)
    snapshot = proxy.snapshot()
    assert snapshot.component_coverage == pytest.approx(0.90)
    assert snapshot.estado is EstadoMaker.NEUTRO
    assert snapshot.side is None and snapshot.percent == 0.0


def test_maker_divergente_preserva_lado_liquido_como_alerta():
    scores = {
        ComponenteMaker.ABSORCAO: 1.0,
        ComponenteMaker.REPOSICAO: -1.0,
        ComponenteMaker.DIVERGENCIA: 1.0,
        ComponenteMaker.CLIPS: 1.0,
        ComponenteMaker.AGRESSAO: 1.0,
    }
    _, snapshot = _maker_estavel(scores=scores)
    assert snapshot.estado is EstadoMaker.DIVERGENTE
    assert snapshot.side is Side.BUY
    assert snapshot.percent > 0


def test_absorcao_vendedora_estavel_publica_vendedor():
    _, snapshot = _maker_estavel(scores={c: -1.0 for c in ComponenteMaker})
    assert snapshot.estado is EstadoMaker.VENDEDOR
    assert snapshot.side is Side.SELL and snapshot.percent == pytest.approx(-100.0)


def test_oscilacao_de_lado_reduz_estabilidade_e_confianca():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    for i, score in enumerate((1.0, -1.0, 1.0, -1.0, 1.0)):
        ts = i * S
        proxy.registrar_evidencia(_evidencia(ts, ComponenteMaker.ABSORCAO, score))
    snapshot = proxy.snapshot()
    assert snapshot.stability < 1.0
    assert snapshot.confidence == pytest.approx(
        snapshot.feed_quality * snapshot.component_coverage * snapshot.stability
    )
    assert snapshot.estado is EstadoMaker.AJUSTANDO


def test_reposicao_que_desaparece_expira_na_janela_de_contexto():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    proxy.registrar_evidencia(_evidencia(0, ComponenteMaker.REPOSICAO, 1))
    assert proxy.snapshot().componente(ComponenteMaker.REPOSICAO).disponivel
    proxy.ao_feed_quality(_feed(31 * S))
    expirado = proxy.snapshot()
    assert not expirado.componente(ComponenteMaker.REPOSICAO).disponivel
    assert expirado.persistence_ns == 0


def test_cada_componente_expira_na_janela_curta_micro_ou_contexto():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    for componente in (
        ComponenteMaker.CLIPS, ComponenteMaker.ABSORCAO, ComponenteMaker.REPOSICAO
    ):
        proxy.registrar_evidencia(_evidencia(0, componente, 1))
    proxy.ao_feed_quality(_feed(2 * S))
    s2 = proxy.snapshot()
    assert not s2.componente(ComponenteMaker.CLIPS).disponivel
    assert s2.componente(ComponenteMaker.ABSORCAO).disponivel
    assert s2.componente(ComponenteMaker.REPOSICAO).disponivel
    proxy.ao_feed_quality(_feed(6 * S))
    s6 = proxy.snapshot()
    assert not s6.componente(ComponenteMaker.ABSORCAO).disponivel
    assert s6.componente(ComponenteMaker.REPOSICAO).disponivel


def test_evidencia_abaixo_de_confianca_minima_nao_cobre_componente():
    proxy = MakerProxy(SYMBOL)
    proxy.ao_feed_quality(_feed(0))
    snapshot = proxy.registrar_evidencia(_evidencia(
        0, ComponenteMaker.ABSORCAO, 1, confianca=0.59
    ))
    assert snapshot is not None
    assert snapshot.component_coverage == 0.0
    assert not snapshot.componente(ComponenteMaker.ABSORCAO).disponivel


def test_detectores_existentes_mapeiam_componentes_e_procedencia():
    proxy = MakerProxy(SYMBOL)
    deteccao = Deteccao(
        0, SYMBOL, TipoDeteccao.EXAUSTAO, Side.BUY, 10_000, 0.7,
        {"procedencia": "INFERIDA", "fonte": "MBP_INFERIDO"},
    )
    snapshot = proxy.ao_deteccao(deteccao)
    assert snapshot is not None
    item = snapshot.componente(ComponenteMaker.DIVERGENCIA)
    assert item.pontuacao == pytest.approx(-1.0)
    assert item.procedencia is ProcedenciaASG.INFERIDA


def test_sem_evidencia_e_virada_de_sessao_zeram_tudo():
    proxy, _ = _maker_estavel()
    proxy.iniciar_nova_sessao()
    snapshot = proxy.snapshot()
    assert snapshot.estado is EstadoMaker.SEM_DADOS
    assert snapshot.component_coverage == 0.0
    assert snapshot.persistence_ns == 0
    assert proxy.n_trades_retidos == proxy.n_evidencias_retidas == proxy.n_trade_ids_retidos == 0


def test_memoria_limitada_com_timestamp_congelado_e_ids_limitados():
    cfg = ConfigMakerProxy(
        max_trades_retidos=3, max_trade_ids_retidos=4,
        max_evidencias_por_componente=2, max_amostras_persistencia=5,
    )
    proxy = MakerProxy(SYMBOL, cfg)
    for i in range(20):
        proxy.ao_trade(_trade(1, AgressorSide.BUY, trade_id=f"id-{i}"))
        proxy.registrar_evidencia(_evidencia(1, ComponenteMaker.ABSORCAO, 1))
    assert proxy.n_trades_retidos == 3
    assert proxy.n_trade_ids_retidos == 4
    assert proxy.n_evidencias_retidas == 2
    assert proxy.n_amostras_persistencia == 5


def test_mappings_e_tuplas_sao_profundamente_imutaveis_e_serializaveis():
    original = {"nested": {"lista": [1, 2]}}
    evidence = MakerEvidence(
        0, SYMBOL, ComponenteMaker.ABSORCAO, 1, 1,
        ProcedenciaASG.OBSERVADA, "MBO", "X", detalhes=original,
    )
    original["nested"]["lista"].append(3)
    assert evidence.detalhes["nested"]["lista"] == (1, 2)
    with pytest.raises(TypeError):
        evidence.detalhes["x"] = 1  # type: ignore[index]
    _, snapshot = _maker_estavel()
    with pytest.raises(FrozenInstanceError):
        snapshot.percent = 0  # type: ignore[misc]
    json.dumps(snapshot.como_dict(), sort_keys=True)


def test_replay_deterministico_do_proxy():
    def executar() -> dict:
        _, snapshot = _maker_estavel()
        return snapshot.como_dict()
    assert executar() == executar()


def test_config_invalida_e_rejeitada():
    with pytest.raises(ValueError):
        ConfigMakerProxy(peso_absorcao=-1)
    with pytest.raises(ValueError):
        ConfigMakerProxy(max_trade_ids_retidos=0)
    with pytest.raises(ValueError):
        ConfigMakerProxy(relevancia_minima=1.1)
