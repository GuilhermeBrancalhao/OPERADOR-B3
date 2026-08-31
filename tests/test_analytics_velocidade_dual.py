"""Matemática pura do Dual Market Velocity Gauge — seção 10 (\"Testes
obrigatórios\") do documento de referência (``CLAUDE_INTEGRATION_DUAL_
MARKET_VELOCITY_GAUGE.md``, pasta Codex/outputs), portada 1:1 para os casos
que fazem sentido em Python (clamp, composto, limiares, wrap180,
contra-giro). Não cobre a bateria de replay/IPC/golden-JSONL da seção 9/10 —
ver docstring de ``fluxopro/analytics/velocidade_dual.py`` para as
divergências deliberadas em relação ao documento original.
"""

import math

import pytest

from fluxopro.analytics import velocidade_dual as vd


# ---------------------------------------------------------------- clamp
def test_clamp_dentro_da_faixa_preserva_o_valor():
    assert vd.clamp(0.37) == 0.37


def test_clamp_acima_satura_em_um():
    assert vd.clamp(2) == 1.0


def test_clamp_abaixo_satura_em_menos_um():
    assert vd.clamp(-2) == -1.0


def test_clamp_nan_vira_zero():
    assert vd.clamp(float("nan")) == 0.0


def test_clamp_nao_numerico_vira_zero():
    assert vd.clamp(None) == 0.0
    assert vd.clamp("abacate") == 0.0


def test_clamp_faixa_customizada():
    assert vd.clamp(5, 0, 1) == 1.0
    assert vd.clamp(-5, 0, 1) == 0.0


# ---------------------------------------------------------- composto
def test_composto_com_confiabilidade_igual_pondera_058_042():
    # micro=+1, macro=-1, mesma confiabilidade -> pesos puros 0.58/0.42
    composto = vd.composto_micro_macro(1.0, 1.0, -1.0, 1.0)
    esperado = (1.0 * vd.PESO_MICRO + (-1.0) * vd.PESO_MACRO) / (vd.PESO_MICRO + vd.PESO_MACRO)
    assert composto == pytest.approx(esperado)


def test_composto_denominador_zero_devolve_zero():
    assert vd.composto_micro_macro(0.9, 0.0, -0.9, 0.0) == 0.0


def test_composto_so_micro_disponivel_ignora_macro():
    composto = vd.composto_micro_macro(0.5, 1.0, 0.99, 0.0)
    assert composto == pytest.approx(0.5)


def test_composto_nunca_estoura_um():
    composto = vd.composto_micro_macro(1.0, 1.0, 1.0, 1.0)
    assert composto <= 1.0


# ------------------------------------------------------- rotulo_direcao
def test_rotulo_limiar_exato_positivo_e_balanco():
    assert vd.rotulo_direcao(vd.LIMIAR_DIRECIONAL) == "BALANCO"


def test_rotulo_imediatamente_acima_do_limiar_e_alta():
    assert vd.rotulo_direcao(vd.LIMIAR_DIRECIONAL + 1e-9) == "ALTA"


def test_rotulo_limiar_exato_negativo_e_balanco():
    assert vd.rotulo_direcao(-vd.LIMIAR_DIRECIONAL) == "BALANCO"


def test_rotulo_imediatamente_abaixo_do_limiar_e_baixa():
    assert vd.rotulo_direcao(-vd.LIMIAR_DIRECIONAL - 1e-9) == "BAIXA"


def test_rotulo_zero_e_balanco():
    assert vd.rotulo_direcao(0.0) == "BALANCO"


# ------------------------------------------------------------- wrap180
@pytest.mark.parametrize("graus,esperado", [
    # Intervalo SEMI-ABERTO [-180, 180): +180 e +540 (=180+360) caem em
    # -180, nunca em +180 — mesma convencao do `wrap180` JS de referencia.
    (-540, -180), (-180, -180), (0, 0), (180, -180), (540, -180),
])
def test_wrap180_nos_pontos_da_especificacao(graus, esperado):
    assert vd.wrap180(graus) == pytest.approx(esperado)


def test_wrap180_devolve_sempre_no_intervalo_semiaberto():
    for graus in range(-1000, 1000, 37):
        valor = vd.wrap180(graus)
        assert -180.0 <= valor < 180.0


# ----------------------------------------------------------- contragiro
def test_contragiro_ambos_positivos_iguais_nao_e_zero_por_construcao():
    """Os dois arcos crescem em SENTIDOS OPOSTOS a partir de extremos
    opostos do mesmo vão — dois horizontes concordantes NÃO colapsam a
    theta_micro==theta_macro (ver seção 5): é a MESMA leitura da referência,
    não uma peculiaridade desta porta."""

    delta, normalizado = vd.contragiro(0.5, 0.5)
    assert delta == pytest.approx(vd.wrap180(
        vd.angulo_micro(0.5) - vd.angulo_macro(0.5)
    ))
    assert -1.0 <= normalizado <= 1.0


def test_contragiro_ambos_negativos():
    delta, normalizado = vd.contragiro(-0.5, -0.5)
    assert delta == pytest.approx(vd.wrap180(
        vd.angulo_micro(-0.5) - vd.angulo_macro(-0.5)
    ))
    assert -1.0 <= normalizado <= 1.0


def test_contragiro_sinais_opostos():
    delta, normalizado = vd.contragiro(0.8, -0.8)
    assert delta == pytest.approx(vd.wrap180(
        vd.angulo_micro(0.8) - vd.angulo_macro(-0.8)
    ))
    assert -1.0 <= normalizado <= 1.0


def test_contragiro_normalizado_e_delta_sobre_amplitude():
    delta, normalizado = vd.contragiro(0.3, -0.1)
    assert normalizado == pytest.approx(vd.clamp(delta / vd.AMPLITUDE_ARCO_GRAUS))


# --------------------------------------------------------- ângulos base
def test_angulo_micro_nos_extremos():
    assert vd.angulo_micro(-1.0) == pytest.approx(vd.ANGULO_BASE_MICRO_GRAUS)
    assert vd.angulo_micro(1.0) == pytest.approx(
        vd.ANGULO_BASE_MICRO_GRAUS + vd.AMPLITUDE_ARCO_GRAUS
    )


def test_angulo_macro_nos_extremos():
    assert vd.angulo_macro(-1.0) == pytest.approx(vd.ANGULO_BASE_MACRO_GRAUS)
    assert vd.angulo_macro(1.0) == pytest.approx(
        vd.ANGULO_BASE_MACRO_GRAUS - vd.AMPLITUDE_ARCO_GRAUS
    )


# -------------------------------------------------- comprimento_aceso
def test_comprimento_aceso_piso_de_3_por_cento_no_zero():
    assert vd.comprimento_aceso(0.0) == pytest.approx(0.03)


def test_comprimento_aceso_no_maximo_e_um():
    assert vd.comprimento_aceso(1.0) == pytest.approx(1.0)
    assert vd.comprimento_aceso(-1.0) == pytest.approx(1.0)


def test_comprimento_aceso_e_o_valor_absoluto():
    assert vd.comprimento_aceso(-0.4) == pytest.approx(0.4)
