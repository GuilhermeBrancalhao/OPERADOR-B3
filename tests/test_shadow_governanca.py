from __future__ import annotations

import pytest

from fluxopro.shadow.governanca import EvidenciaCandidata, avaliar_candidata


def evidencia_valida(**mudancas) -> EvidenciaCandidata:
    dados = {
        "pregoes": 20,
        "amostras": 10_000,
        "walk_forward_aprovado": True,
        "limite_inferior_ci": 1.01,
        "baseline": 1.0,
        "degradacao_guardrail": 0.05,
        "aprovacao_humana_id": "operador:guilherme:2026-08-24",
        "config_versao": "candidate-v3",
        "rollback_testado": True,
    }
    dados.update(mudancas)
    return EvidenciaCandidata(**dados)


@pytest.mark.parametrize(
    "mudanca,bloqueio",
    [
        ({"pregoes": 19}, "MIN_20_PREGOES"),
        ({"amostras": 9_999}, "MIN_10000_AMOSTRAS"),
        ({"walk_forward_aprovado": False}, "WALK_FORWARD"),
        ({"limite_inferior_ci": 1.0}, "CI_INFERIOR_NAO_SUPERA_BASELINE"),
        ({"degradacao_guardrail": 0.050001}, "GUARDRAIL_MAIOR_5_PCT"),
        ({"aprovacao_humana_id": None}, "APROVACAO_HUMANA"),
        ({"config_versao": ""}, "CONFIG_NAO_VERSIONADA"),
        ({"config_versao": "candidate"}, "CONFIG_NAO_VERSIONADA"),
        ({"rollback_testado": False}, "ROLLBACK_NAO_TESTADO"),
    ],
)
def test_cada_gate_bloqueia_sozinho(mudanca, bloqueio):
    avaliacao = avaliar_candidata(evidencia_valida(**mudanca))
    assert avaliacao.elegivel_para_revisao_humana is False
    assert bloqueio in avaliacao.bloqueios
    assert avaliacao.aplicacao_automatica is False


def test_todos_os_gates_apenas_liberam_revisao_humana():
    avaliacao = avaliar_candidata(evidencia_valida())
    assert avaliacao.elegivel_para_revisao_humana is True
    assert avaliacao.bloqueios == ()
    assert avaliacao.aplicacao_automatica is False


def test_evidencia_nao_aceita_nan_ou_infinito():
    with pytest.raises(ValueError, match="finito"):
        evidencia_valida(limite_inferior_ci=float("nan"))
    with pytest.raises(ValueError, match="finito"):
        evidencia_valida(degradacao_guardrail=float("inf"))


def test_modulo_nao_oferece_acao_de_aplicar_configuracao():
    import fluxopro.shadow.governanca as governanca

    proibidos = {"apply", "aplicar", "promote", "promover", "deploy", "ativar"}
    assert not (proibidos & set(dir(governanca)))
