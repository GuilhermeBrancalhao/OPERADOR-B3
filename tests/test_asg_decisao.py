from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError
from dataclasses import dataclass

import pytest

import fluxopro.asg.decisao as modulo_decisao
from fluxopro.asg import (
    ConfigMotorDecisaoASG,
    DecisionSnapshot,
    EstadoMaker,
    LeituraASG,
    MakerProxySnapshot,
    MotorDecisaoASG,
    NivelDecisao,
    ProcedenciaASG,
    RegiaoOperacional,
)
from fluxopro.core.eventos import Side


SYMBOL = "WDOV26"


def _maker(
    score: float,
    confianca: float,
    cobertura: float,
    persistencia: float,
    *,
    side: Side = Side.BUY,
) -> MakerProxySnapshot:
    return MakerProxySnapshot(
        timestamp_ns=100,
        symbol=SYMBOL,
        estado=EstadoMaker.COMPRADOR if side is Side.BUY else EstadoMaker.VENDEDOR,
        direcao=side,
        pontuacao=score,
        confianca=confianca,
        cobertura=cobertura,
        persistencia=persistencia,
        componentes=(),
        procedencia=ProcedenciaASG.OBSERVADA,
    )


def _regiao() -> RegiaoOperacional:
    return RegiaoOperacional(
        symbol=SYMBOL,
        timestamp_ns=90,
        inicio_ticks=100,
        fim_ticks=102,
        nome="pullback",
        procedencia=ProcedenciaASG.OBSERVADA,
    )


def test_stop_um_tick_fora_da_regiao_e_alvos_r_para_compra():
    proposta = MotorDecisaoASG().propor_risco(Side.BUY, 102, _regiao())
    assert proposta.stop_ticks == 99
    assert proposta.risco_ticks == 3
    assert (proposta.a1_ticks, proposta.a2_ticks, proposta.a3_ticks) == (105, 108, 111)
    assert proposta.consultiva is True


def test_stop_um_tick_fora_da_regiao_e_alvos_r_para_venda():
    proposta = MotorDecisaoASG().propor_risco(Side.SELL, 100, _regiao())
    assert proposta.stop_ticks == 103
    assert proposta.risco_ticks == 3
    assert (proposta.a1_ticks, proposta.a2_ticks, proposta.a3_ticks) == (97, 94, 91)


@pytest.mark.parametrize(
    ("score", "conf", "cob", "pers", "esperado"),
    [
        (0.19, 1.0, 1.0, 1.0, NivelDecisao.AGUARDAR),
        (0.20, 0.35, 0.25, 0.40, NivelDecisao.A1),
        (0.40, 0.55, 0.50, 0.60, NivelDecisao.A2),
        (0.65, 0.75, 0.75, 0.80, NivelDecisao.A3),
    ],
)
def test_a1_a2_a3_respeitam_todos_os_cortes_inclusive_fronteira(
    score, conf, cob, pers, esperado
):
    decisao = MotorDecisaoASG().avaliar(_maker(score, conf, cob, pers), _regiao(), 102)
    assert decisao.nivel is esperado
    assert (decisao.proposta_risco is None) is (esperado is NivelDecisao.AGUARDAR)


def test_cobertura_baixa_nao_e_mascarada_por_score_e_confianca_altos():
    decisao = MotorDecisaoASG().avaliar(_maker(1.0, 1.0, 0.24, 1.0), _regiao(), 102)
    assert decisao.nivel is NivelDecisao.AGUARDAR
    assert "cobertura" in decisao.motivos[0]


def test_venda_usa_magnitude_do_score_para_classificacao():
    decisao = MotorDecisaoASG().decidir(
        _maker(-0.65, 0.75, 0.75, 0.8, side=Side.SELL), _regiao(), 100
    )
    assert decisao.nivel is NivelDecisao.A3
    assert decisao.direcao is Side.SELL
    assert decisao.proposta_risco is not None
    assert decisao.proposta_risco.stop_ticks == 103


@pytest.mark.parametrize("estado", [EstadoMaker.SEM_DADOS, EstadoMaker.NEUTRO, EstadoMaker.DIVERGENTE])
def test_estados_sem_direcao_ficam_em_aguardar(estado):
    maker = MakerProxySnapshot(
        timestamp_ns=100,
        symbol=SYMBOL,
        estado=estado,
        direcao=None,
        pontuacao=0.0,
        confianca=1.0,
        cobertura=1.0,
        persistencia=1.0,
        componentes=(),
        procedencia=ProcedenciaASG.OBSERVADA,
    )
    decisao = MotorDecisaoASG().avaliar(maker, _regiao(), 101)
    assert decisao.nivel is NivelDecisao.AGUARDAR
    assert decisao.proposta_risco is None


def test_decisao_carrega_procedencia_e_versoes_sem_alegar_formula_proprietaria():
    decisao = MotorDecisaoASG().avaliar(_maker(1, 1, 1, 1), _regiao(), 102)
    assert "maker:OBSERVADA" in decisao.procedencia
    assert any(item.startswith("maker_formula:maker-proxy-independent") for item in decisao.procedencia)
    assert decisao.formula_version == "decision-consultive-v1"
    serializado = json.dumps(decisao.como_dict(), sort_keys=True)
    assert '"consultiva": true' in serializado
    assert '"nivel": "A3"' in serializado


def test_leitura_regiao_proposta_e_decisao_sao_imutaveis():
    leitura = LeituraASG.do_maker(_maker(1, 1, 1, 1))
    regiao = _regiao()
    decisao = MotorDecisaoASG().avaliar(leitura, regiao, 102)
    assert isinstance(decisao, DecisionSnapshot)
    assert isinstance(decisao.motivos, tuple)
    with pytest.raises(FrozenInstanceError):
        regiao.inicio_ticks = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        leitura.symbol = "X"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        decisao.nivel = NivelDecisao.A1  # type: ignore[misc]


def test_leitura_compoe_metodo_sinal_e_feed_quality_sem_reter_mappings_mutaveis():
    @dataclass(frozen=True)
    class Retrato:
        timestamp_ns: int
        symbol: str
        evidencia: dict[str, object]

    evidencia = {"profundidade": {"book": 5}}
    retrato = Retrato(100, SYMBOL, evidencia)
    leitura = LeituraASG.do_maker(
        _maker(1, 1, 1, 1),
        metodo={"timestamp_ns": 100, "placar": 4},
        sinal=retrato,
        feed_quality={"timestamp_ns": 100, "symbol": SYMBOL, "healthy": True},
    )
    evidencia["profundidade"]["book"] = 0
    assert leitura.metodo["placar"] == 4
    assert leitura.sinal["evidencia"]["profundidade"]["book"] == 5
    assert leitura.feed_quality["healthy"] is True
    with pytest.raises(TypeError):
        leitura.metodo["placar"] = 0  # type: ignore[index]


def test_leitura_recusa_retratos_de_outro_instante_ou_simbolo():
    maker = _maker(1, 1, 1, 1)
    with pytest.raises(ValueError):
        LeituraASG.do_maker(maker, metodo={"timestamp_ns": 99})
    with pytest.raises(ValueError):
        LeituraASG.do_maker(maker, feed_quality={"timestamp_ns": 100, "symbol": "WINV26"})


def test_ticks_float_sao_recusados_em_todas_as_fronteiras_de_preco():
    with pytest.raises(TypeError):
        RegiaoOperacional(SYMBOL, 1, 100.0, 102)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MotorDecisaoASG().propor_risco(Side.BUY, 102.0, _regiao())  # type: ignore[arg-type]


def test_symbol_inconsistente_e_risco_geometricamente_invalido_sao_recusados():
    outra = RegiaoOperacional("WINV26", 90, 100, 102)
    with pytest.raises(ValueError):
        MotorDecisaoASG().avaliar(_maker(1, 1, 1, 1), outra, 102)
    with pytest.raises(ValueError):
        MotorDecisaoASG().propor_risco(Side.BUY, 98, _regiao())


def test_config_exige_cortes_ordenados_e_alvos_crescentes():
    with pytest.raises(ValueError):
        ConfigMotorDecisaoASG(score_a1=0.8, score_a2=0.4)
    with pytest.raises(ValueError):
        ConfigMotorDecisaoASG(alvo_a1_r=2, alvo_a2_r=2)


def test_motor_nao_expoe_api_de_ordem_nem_contem_chamada_de_execucao():
    motor = MotorDecisaoASG()
    nomes = set(dir(motor))
    assert not {"enviar_ordem", "executar_ordem", "order_send"} & nomes
    fonte = inspect.getsource(modulo_decisao).lower()
    assert "order_send" not in fonte
    assert "mt5" not in fonte


def test_decision_snapshot_expoe_apenas_proposta_informativa():
    decisao = MotorDecisaoASG().avaliar(_maker(1, 1, 1, 1), _regiao(), 102)
    assert decisao.tem_proposta_informativa is True
