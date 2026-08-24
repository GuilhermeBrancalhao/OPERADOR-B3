from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError

import pytest

import fluxopro.asg.decisao as modulo_decisao
from fluxopro.asg import (
    ConfigMotorDecisaoASG, DecisionSnapshot, EstadoMaker, FrozenMapping,
    LeituraASG, MakerProxySnapshot, MotorDecisaoASG, NivelDecisao,
    ProcedenciaASG, RegiaoOperacional,
)
from fluxopro.core.eventos import Side

SYMBOL = "WDOV26"
S = 1_000_000_000


def _maker(
    *,
    timestamp: int = 100 * S,
    estado: EstadoMaker = EstadoMaker.COMPRADOR,
    side: Side | None = Side.BUY,
    percent: float = 80.0,
    confidence: float = 0.90,
    coverage: float = 0.90,
    persistence_ns: int = 3 * S,
    source: str = "MT5",
    book_kind: str = "MBO",
    feed_quality: float = 1.0,
    book_delayed: bool = False,
) -> MakerProxySnapshot:
    score = percent / 100.0
    return MakerProxySnapshot(
        timestamp_ns=timestamp, symbol=SYMBOL, estado=estado, direcao=side,
        pontuacao=score, confianca=confidence, cobertura=coverage,
        persistencia=min(1.0, persistence_ns / (3 * S)), componentes=(),
        procedencia=ProcedenciaASG.OBSERVADA, percent=percent,
        persistence_ns=persistence_ns, source=source, book_kind=book_kind,
        inferred=book_kind == "MBP", component_coverage=coverage,
        feed_quality=feed_quality, stability=0.90, book_delayed=book_delayed,
    )


def _regiao(
    *,
    timestamp: int = 100 * S,
    confianca: float = 0.90,
    valida: bool = True,
    obstaculo: int | None = 108,
) -> RegiaoOperacional:
    return RegiaoOperacional(
        symbol=SYMBOL, timestamp_ns=timestamp, inicio_ticks=100, fim_ticks=102,
        nome="pullback", confianca=confianca,
        procedencia=ProcedenciaASG.OBSERVADA, qualidade="BOA", valida=valida,
        invalidacao_ticks=100, obstaculo_ticks=obstaculo,
    )


def _leitura(maker: MakerProxySnapshot | None = None, *, placar: object | None = None) -> LeituraASG:
    maker = maker or _maker()
    return LeituraASG.do_maker(
        maker,
        placar=placar or {"timestamp_ns": maker.timestamp_ns, "comprador": 4, "vendedor": 1},
        feed_quality={
            "timestamp_ns": maker.timestamp_ns, "symbol": SYMBOL,
            "source": maker.source, "book_kind": maker.book_kind,
        },
        macro={"timestamp_ns": maker.timestamp_ns, "lado": "BUY"},
        micro={"timestamp_ns": maker.timestamp_ns, "lado": "BUY"},
        linha_azul={"timestamp_ns": maker.timestamp_ns, "lado": "BUY"},
        regime={"timestamp_ns": maker.timestamp_ns, "nome": "ALTA"},
        velocimetro={"timestamp_ns": maker.timestamp_ns, "estado": "ACELERANDO"},
        divergencias=("maker_preco",) if maker.estado is EstadoMaker.DIVERGENTE else (),
        provenance=("teste",),
    )


def test_regiao_futura_nao_decide_reproducao_do_p0():
    maker = _maker(timestamp=100)
    regiao = _regiao(timestamp=101)
    decisao = MotorDecisaoASG().avaliar(_leitura(maker), regiao, 101)
    assert decisao.nivel is NivelDecisao.AGUARDAR
    assert decisao.confirmacao is False
    assert decisao.proposta_risco is None
    assert "REGIAO_FUTURA" in decisao.bloqueios


@pytest.mark.parametrize(
    ("regiao", "bloqueio"),
    [
        (_regiao(timestamp=60 * S), "REGIAO_EXPIRADA"),
        (_regiao(valida=False), "REGIAO_INVALIDA"),
        (_regiao(confianca=0.0), "QUALIDADE_REGIAO_BAIXA"),
    ],
)
def test_regiao_invalida_inconsistente_ou_sem_qualidade_nao_confirma(regiao, bloqueio):
    decisao = MotorDecisaoASG().avaliar(_leitura(), regiao, 101)
    assert not decisao.confirmacao
    assert bloqueio in decisao.bloqueios


def test_pre_sinal_sem_confirmacao_por_confianca_baixa():
    maker = _maker(estado=EstadoMaker.AJUSTANDO, confidence=0.50)
    decisao = MotorDecisaoASG().avaliar(_leitura(maker), _regiao(), 101)
    assert decisao.pre_sinal is True
    assert decisao.confirmacao is False
    assert "CONFIANCA_BAIXA" in decisao.bloqueios


@pytest.mark.parametrize(
    ("maker", "bloqueio"),
    [
        (_maker(estado=EstadoMaker.SEM_BOOK, book_kind="NONE", feed_quality=0), "SEM_BOOK"),
        (_maker(estado=EstadoMaker.SEM_BOOK, book_delayed=True, feed_quality=0), "BOOK_ATRASADO"),
        (_maker(feed_quality=0.50), "QUALIDADE_FEED_BAIXA"),
        (_maker(estado=EstadoMaker.AJUSTANDO, persistence_ns=2 * S), "PERSISTENCIA_INSUFICIENTE"),
        (_maker(estado=EstadoMaker.AJUSTANDO, percent=6), "EVIDENCIA_IRRELEVANTE"),
    ],
)
def test_confirmacao_bloqueada_por_feed_book_persistencia_ou_relevancia(maker, bloqueio):
    decisao = MotorDecisaoASG().avaliar(_leitura(maker), _regiao(), 101)
    assert decisao.confirmacao is False
    assert bloqueio in decisao.bloqueios


def test_confirmacao_completa_publica_placar_regiao_stop_alvos_obstaculo_e_procedencia():
    decisao = MotorDecisaoASG().avaliar(_leitura(), _regiao(), 102)
    assert decisao.confirmacao is True and decisao.pre_sinal is True
    assert decisao.nivel is NivelDecisao.A3
    assert decisao.direcao is Side.BUY
    assert decisao.placar["comprador"] == 4
    assert decisao.qualidade_regiao == "BOA"
    assert decisao.invalidacao_ticks == 100
    assert decisao.stop_proposto == 99
    assert (decisao.a1_ticks, decisao.a2_ticks, decisao.a3_ticks) == (105, 108, 111)
    assert decisao.obstaculo_ticks == 108
    assert decisao.bloqueios == ()
    assert decisao.confianca == pytest.approx(0.90)
    assert "REGRA DO OPERADOR B3" in decisao.razao
    assert any(item.startswith("feed:MT5/MBO") for item in decisao.procedencia)
    assert decisao.tem_proposta_informativa


def test_stop_venda_fica_um_tick_alem_da_invalidacao_e_alvos_descem():
    maker = _maker(estado=EstadoMaker.VENDEDOR, side=Side.SELL, percent=-80)
    regiao = RegiaoOperacional(
        SYMBOL, 100 * S, 100, 102, confianca=0.9,
        procedencia=ProcedenciaASG.OBSERVADA, invalidacao_ticks=102,
    )
    decisao = MotorDecisaoASG().avaliar(_leitura(maker), regiao, 100)
    assert decisao.confirmacao
    assert decisao.stop_proposto == 103
    assert (decisao.a1_ticks, decisao.a2_ticks, decisao.a3_ticks) == (97, 94, 91)


def test_maker_divergente_e_alerta_e_nao_veto_automatico():
    maker = _maker(estado=EstadoMaker.DIVERGENTE, side=Side.BUY, percent=40)
    decisao = MotorDecisaoASG().avaliar(_leitura(maker), _regiao(), 101)
    assert decisao.confirmacao is True
    assert not any("DIVERG" in bloqueio for bloqueio in decisao.bloqueios)
    assert any("ALERTA" in motivo for motivo in decisao.motivos)


def test_placar_antigo_sem_maker_permanece_visivel_sem_confirmar():
    maker = _maker(
        estado=EstadoMaker.SEM_DADOS, side=None, percent=0, confidence=0,
        coverage=0, persistence_ns=0, source="UNKNOWN", book_kind="NONE",
        feed_quality=0,
    )
    leitura = _leitura(maker, placar={"timestamp_ns": maker.timestamp_ns, "legado": "3x1"})
    decisao = MotorDecisaoASG().avaliar(leitura, _regiao(), 101)
    assert decisao.placar["legado"] == "3x1"
    assert not decisao.confirmacao
    assert "SEM_DADOS" in decisao.bloqueios


def test_placar_futuro_com_maker_habilitado_confirma_quando_snapshot_e_consistente():
    leitura = _leitura(placar={"timestamp_ns": 100 * S, "inclui_maker": True, "saldo": 5})
    decisao = MotorDecisaoASG().avaliar(leitura, _regiao(), 101)
    assert decisao.placar["inclui_maker"] is True
    assert decisao.confirmacao


def test_preco_fora_da_regiao_nao_confirma():
    decisao = MotorDecisaoASG().avaliar(_leitura(), _regiao(), 110)
    assert not decisao.confirmacao
    assert "PRECO_FORA_DA_REGIAO" in decisao.bloqueios


def test_leitura_asg_compoe_toda_matriz_em_mappings_e_tuplas_imutaveis():
    leitura = _leitura()
    assert leitura.maker_proxy is leitura.maker
    for nome in ("macro", "micro", "linha_azul", "regime", "velocimetro", "placar", "feed_quality"):
        assert isinstance(getattr(leitura, nome), FrozenMapping)
    assert isinstance(leitura.divergencias, tuple)
    with pytest.raises(TypeError):
        leitura.placar["x"] = 1  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        leitura.symbol = "X"  # type: ignore[misc]


def test_leitura_recusa_parte_de_outro_instante_ou_simbolo():
    maker = _maker()
    with pytest.raises(ValueError):
        LeituraASG.do_maker(maker, macro={"timestamp_ns": maker.timestamp_ns + 1})
    with pytest.raises(ValueError):
        LeituraASG.do_maker(
            maker, feed_quality={"timestamp_ns": maker.timestamp_ns, "symbol": "WINV26"}
        )


def test_decision_snapshot_completo_e_serializavel():
    decisao = MotorDecisaoASG().avaliar(_leitura(), _regiao(), 101)
    assert isinstance(decisao, DecisionSnapshot)
    bruto = json.dumps(decisao.como_dict(), sort_keys=True)
    for campo in (
        "placar", "qualidade_regiao", "pre_sinal", "confirmacao", "invalidacao_ticks",
        "stop_proposto", "a1_ticks", "a2_ticks", "a3_ticks", "obstaculo_ticks",
        "razao", "bloqueios", "confianca", "procedencia",
    ):
        assert f'"{campo}"' in bruto


def test_ticks_float_e_config_invalida_sao_recusados():
    with pytest.raises(TypeError):
        RegiaoOperacional(SYMBOL, 1, 100.0, 102)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MotorDecisaoASG().propor_risco(Side.BUY, 101.0, _regiao())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ConfigMotorDecisaoASG(score_a1=0.8, score_a2=0.4)


def test_motor_preserva_ausencia_de_api_de_ordem():
    motor = MotorDecisaoASG()
    nomes = set(dir(motor))
    assert not {"enviar_ordem", "executar_ordem", "order_send"} & nomes
    fonte = inspect.getsource(modulo_decisao).lower()
    assert "order_send" not in fonte and "metatrader5" not in fonte
