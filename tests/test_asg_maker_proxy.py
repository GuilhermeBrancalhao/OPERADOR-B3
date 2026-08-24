from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from fluxopro.asg import (
    ComponenteMaker,
    ConfigMakerProxy,
    EstadoMaker,
    MakerEvidence,
    MakerProxy,
    ProcedenciaASG,
)
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao


SYMBOL = "WDOV26"


def _trade(ts: int, side: AgressorSide, qty: int = 100, price: int = 10_000) -> Trade:
    return Trade(ts, SYMBOL, price, qty, side, f"t{ts}")


def _deteccao(
    ts: int,
    tipo: TipoDeteccao,
    side: Side,
    *,
    confianca: float = 1.0,
    procedencia: str = "OBSERVADA",
) -> Deteccao:
    return Deteccao(
        timestamp_ns=ts,
        symbol=SYMBOL,
        tipo=tipo,
        side=side,
        price=10_000,
        confianca=confianca,
        evidencia={"procedencia": procedencia, "fonte": "MBO", "n": 3},
    )


def _evidencia(
    ts: int,
    componente: ComponenteMaker,
    score: float,
    procedencia: ProcedenciaASG = ProcedenciaASG.OBSERVADA,
) -> MakerEvidence:
    return MakerEvidence(
        timestamp_ns=ts,
        symbol=SYMBOL,
        componente=componente,
        pontuacao=score,
        confianca=1.0,
        procedencia=procedencia,
        fonte="TESTE",
        tipo_evento="TESTE",
        preco_ticks=10_000,
        detalhes={"id": ts},
    )


def test_modelos_e_snapshot_sao_imutaveis_inclusive_evidencia_aninhada():
    detalhes = {"lista": [1, {"x": 2}]}
    evidencia = MakerEvidence(
        1,
        SYMBOL,
        ComponenteMaker.ABSORCAO,
        1.0,
        0.8,
        ProcedenciaASG.OBSERVADA,
        "MBO",
        "ABSORCAO",
        10_000,
        detalhes,  # type: ignore[arg-type]
    )
    detalhes["lista"].append(3)
    assert evidencia.detalhes["lista"][1]["x"] == 2
    with pytest.raises(TypeError):
        evidencia.detalhes["outra"] = 3  # type: ignore[index]
    with pytest.raises(TypeError):
        evidencia.detalhes["lista"][1]["x"] = 9  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        evidencia.pontuacao = 0.0  # type: ignore[misc]

    snapshot = MakerProxy(SYMBOL).snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.cobertura = 1.0  # type: ignore[misc]
    assert isinstance(snapshot.componentes, tuple)


def test_agressao_usa_volume_atribuido_e_expoe_desconhecido_na_confianca():
    proxy = MakerProxy(
        SYMBOL,
        ConfigMakerProxy(volume_referencia_agressao=100, limiar_direcional=0.1),
    )
    proxy.ao_trade(_trade(1, AgressorSide.BUY, 75))
    snapshot = proxy.ao_trade(_trade(2, AgressorSide.UNKNOWN, 25))
    assert snapshot is not None
    agressao = snapshot.componente(ComponenteMaker.AGRESSAO)
    assert agressao.pontuacao == 1.0
    assert agressao.confianca == pytest.approx(0.75 * 0.75)
    assert snapshot.estado is EstadoMaker.COMPRADOR
    assert snapshot.direcao is Side.BUY


def test_pesos_sao_renormalizados_somente_entre_componentes_cobertos():
    cfg = ConfigMakerProxy(
        peso_agressao=0.1,
        peso_absorcao=0.3,
        peso_reposicao=0.2,
        peso_divergencia=0.2,
        peso_clips=0.2,
    )
    proxy = MakerProxy(SYMBOL, cfg)
    primeiro = proxy.registrar_evidencia(_evidencia(1, ComponenteMaker.ABSORCAO, 1.0))
    assert primeiro is not None
    assert primeiro.cobertura == pytest.approx(0.3)
    assert primeiro.componente(ComponenteMaker.ABSORCAO).peso_efetivo == 1.0

    segundo = proxy.registrar_evidencia(_evidencia(2, ComponenteMaker.REPOSICAO, -1.0))
    assert segundo is not None
    assert segundo.cobertura == pytest.approx(0.5)
    assert segundo.componente(ComponenteMaker.ABSORCAO).peso_efetivo == pytest.approx(0.6)
    assert segundo.componente(ComponenteMaker.REPOSICAO).peso_efetivo == pytest.approx(0.4)
    assert segundo.pontuacao == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("tipo", "componente", "side", "score"),
    [
        (TipoDeteccao.ABSORCAO, ComponenteMaker.ABSORCAO, Side.BUY, 1.0),
        (TipoDeteccao.ESCORA, ComponenteMaker.REPOSICAO, Side.SELL, -1.0),
        (TipoDeteccao.ICEBERG, ComponenteMaker.REPOSICAO, Side.BUY, 1.0),
        (TipoDeteccao.CLIP_INSTITUCIONAL, ComponenteMaker.CLIPS, Side.SELL, -1.0),
        # Exaustao do comprador e hipotese divergente vendedora no proxy.
        (TipoDeteccao.EXAUSTAO, ComponenteMaker.DIVERGENCIA, Side.BUY, -1.0),
        (TipoDeteccao.LIQUIDEZ_FANTASMA, ComponenteMaker.DIVERGENCIA, Side.SELL, 1.0),
    ],
)
def test_adaptacao_de_todos_os_detectores_existentes(tipo, componente, side, score):
    snapshot = MakerProxy(SYMBOL).ao_deteccao(_deteccao(1, tipo, side))
    assert snapshot is not None
    item = snapshot.componente(componente)
    assert item.pontuacao == score
    assert item.evidencias[-1].tipo_evento == tipo.value
    assert item.evidencias[-1].preco_ticks == 10_000


def test_procedencia_inferida_nao_e_promovida_e_mistura_fica_visivel():
    proxy = MakerProxy(SYMBOL)
    inferido = proxy.ao_deteccao(
        _deteccao(1, TipoDeteccao.ESCORA, Side.BUY, confianca=0.4, procedencia="INFERIDA")
    )
    assert inferido is not None
    assert inferido.procedencia is ProcedenciaASG.INFERIDA
    assert inferido.confianca == pytest.approx(0.4)
    assert inferido.componente(ComponenteMaker.REPOSICAO).procedencia is ProcedenciaASG.INFERIDA
    assert inferido.componente(ComponenteMaker.REPOSICAO).formula_version == inferido.formula_version

    misto = proxy.ao_deteccao(_deteccao(2, TipoDeteccao.ABSORCAO, Side.BUY))
    assert misto is not None
    assert misto.procedencia is ProcedenciaASG.MISTA


def test_conflito_equilibrado_publica_estado_divergente_sem_direcao():
    cfg = ConfigMakerProxy(
        peso_agressao=0,
        peso_absorcao=1,
        peso_reposicao=1,
        peso_divergencia=0,
        peso_clips=0,
    )
    proxy = MakerProxy(SYMBOL, cfg)
    proxy.registrar_evidencia(_evidencia(1, ComponenteMaker.ABSORCAO, 1.0))
    snapshot = proxy.registrar_evidencia(_evidencia(2, ComponenteMaker.REPOSICAO, -1.0))
    assert snapshot is not None
    assert snapshot.pontuacao == 0.0
    assert snapshot.estado is EstadoMaker.DIVERGENTE
    assert snapshot.direcao is None


def test_janelas_expiram_por_tempo_e_consulta_nao_infla_persistencia():
    cfg = ConfigMakerProxy(janela_agressao_ns=10, janela_evidencia_ns=20)
    proxy = MakerProxy(SYMBOL, cfg)
    proxy.ao_trade(_trade(1, AgressorSide.BUY))
    proxy.registrar_evidencia(_evidencia(2, ComponenteMaker.ABSORCAO, 1.0))
    n = proxy.n_amostras_persistencia
    proxy.snapshot()
    proxy.snapshot()
    assert proxy.n_amostras_persistencia == n

    expirado = proxy.snapshot(23)
    assert proxy.n_trades_retidos == 0
    assert proxy.n_evidencias_retidas == 0
    assert expirado.estado is EstadoMaker.SEM_DADOS
    assert expirado.cobertura == 0.0


def test_tetos_de_memoria_valem_mesmo_com_timestamp_congelado():
    cfg = ConfigMakerProxy(
        max_trades_retidos=3,
        max_evidencias_por_componente=2,
        max_amostras_persistencia=4,
    )
    proxy = MakerProxy(SYMBOL, cfg)
    for i in range(20):
        proxy.ao_trade(_trade(1, AgressorSide.BUY, price=10_000 + i))
        proxy.registrar_evidencia(_evidencia(1, ComponenteMaker.ABSORCAO, 1.0))
    assert proxy.n_trades_retidos == 3
    assert proxy.n_evidencias_retidas == 2
    assert proxy.n_amostras_persistencia == 4
    agressao = proxy.snapshot().componente(ComponenteMaker.AGRESSAO)
    assert agressao.evidencias[0].detalhes["n_trades"] == 3
    assert agressao.evidencias[0].detalhes["volume_total"] == 300


def test_stream_igual_produz_snapshot_serializado_identico():
    def executar() -> dict:
        proxy = MakerProxy(SYMBOL)
        proxy.ao_trade(_trade(1, AgressorSide.BUY, 30))
        proxy.ao_deteccao(_deteccao(2, TipoDeteccao.ABSORCAO, Side.BUY))
        proxy.ao_trade(_trade(3, AgressorSide.SELL, 10))
        return proxy.snapshot().como_dict()

    a = executar()
    b = executar()
    assert a == b
    assert json.loads(json.dumps(a, sort_keys=True))["formula_version"].startswith("maker-proxy")


def test_evento_de_outro_simbolo_nao_altera_estado():
    proxy = MakerProxy(SYMBOL)
    outro = Trade(1, "WINV26", 100, 10, AgressorSide.BUY, "outro")
    assert proxy.ao_trade(outro) is None
    assert proxy.snapshot().estado is EstadoMaker.SEM_DADOS


def test_config_recusa_pesos_invalidos_e_janelas_sem_teto():
    with pytest.raises(ValueError):
        ConfigMakerProxy(peso_agressao=-1)
    with pytest.raises(ValueError):
        ConfigMakerProxy(
            peso_agressao=0,
            peso_absorcao=0,
            peso_reposicao=0,
            peso_divergencia=0,
            peso_clips=0,
        )
    with pytest.raises(ValueError):
        ConfigMakerProxy(max_trades_retidos=0)
