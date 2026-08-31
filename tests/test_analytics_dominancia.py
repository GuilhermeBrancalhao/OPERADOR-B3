"""Suíte obrigatória (seção 13.1-13.3 de
``INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md``) portada para
``fluxopro/analytics/dominancia.py``. Não cobre 13.4 (paridade TypeScript/
C++/C#, inaplicável — este projeto é Python puro) nem o harness de replay
gravado (ver docstring do módulo); a propriedade de determinismo é testada
diretamente.
"""

import pytest

from fluxopro.analytics import dominancia as dom


# ============================================================== Q6
def test_q6_half_away_from_zero_positivo():
    assert dom.quantizar_q6(0.1234565) == pytest.approx(0.123457)


def test_q6_half_away_from_zero_negativo():
    assert dom.quantizar_q6(-0.1234565) == pytest.approx(-0.123457)


def test_q6_nao_produz_menos_zero():
    assert dom.quantizar_q6(-0.0000001) == 0.0
    assert str(dom.quantizar_q6(-0.0000001)) != "-0.0"


def test_clamp_externo_e_aplicado():
    assert dom.clamp(5) == 1.0
    assert dom.clamp(-5) == -1.0


# ============================================================== micro/macro
def test_calcular_micro_pesos_034_024_020_012_010():
    micro = dom.calcular_micro({"A": 1.0, "B": 0, "R": 0, "W": 0, "M": 0})
    assert micro == pytest.approx(0.34)


def test_calcular_macro_pesos_028_016_018_008_030():
    macro = dom.calcular_macro({"A": 0, "B": 0, "R": 0, "W": 0, "M": 1.0})
    assert macro == pytest.approx(0.30)


def test_micro_macro_com_todos_componentes_maximos_satura_em_um():
    assert dom.calcular_micro({"A": 1, "B": 1, "R": 1, "W": 1, "M": 1}) == 1.0
    assert dom.calcular_macro({"A": 1, "B": 1, "R": 1, "W": 1, "M": 1}) == 1.0


def test_componente_ausente_no_dict_conta_como_zero():
    assert dom.calcular_micro({"A": 1.0}) == pytest.approx(0.34)


# ============================================================== confiabilidade/composto
def test_confiabilidade_produto_qualidade_confianca():
    assert dom.confiabilidade(0.9, 0.8) == pytest.approx(0.72)


def test_composto_pesos_058_042():
    composto = dom.calcular_composto(1.0, 0.0, 1.0, 1.0)
    assert composto == pytest.approx(dom.PESO_RELIABILITY_MICRO)


def test_composto_denominador_zero_e_none_nunca_zero():
    assert dom.calcular_composto(0.9, -0.9, 0.0, 0.0) is None


def test_composto_um_horizonte_indisponivel_usa_so_o_outro():
    composto = dom.calcular_composto(0.5, 0.99, 1.0, 0.0)
    assert composto == pytest.approx(0.5)


# ============================================================== placar
@pytest.mark.parametrize("composite,esperado_buy", [
    (-1.0, 0.0), (-0.0001, 49.99), (0.0, 50.0), (0.0001, 50.01), (1.0, 100.0),
])
def test_placar_nos_extremos_e_no_meio(composite, esperado_buy):
    buy, sell = dom.calcular_placar(composite)
    assert buy == pytest.approx(esperado_buy, abs=0.01)
    assert buy + sell == pytest.approx(100.0)


def test_placar_soma_sempre_100_no_meio_do_intervalo():
    for milesimo in range(-1000, 1001, 37):
        composite = milesimo / 1000.0
        buy, sell = dom.calcular_placar(composite)
        assert buy + sell == pytest.approx(100.0)


# ============================================================== wrap180/contragiro
@pytest.mark.parametrize("graus,esperado", [
    (-540, -180), (-180, -180), (0, 0), (180, -180), (540, -180),
])
def test_wrap180_pontos_da_especificacao(graus, esperado):
    from fluxopro.analytics.velocidade_dual import wrap180
    assert wrap180(graus) == pytest.approx(esperado)


def test_contragiro_sinais_iguais():
    cg = dom.contragiro_de(0.5, 0.5)
    assert cg.divergente is False


def test_contragiro_sinais_opostos_marca_divergente_quando_aplicavel():
    cg = dom.contragiro_de(0.6, -0.4)
    assert cg.divergente is True


# ============================================================== divergencia
def test_divergencia_na_distancia_exata_035_e_verdadeira():
    assert dom.divergente_de(0.20, -0.15) is True  # produto<0, |diff|=0.35


def test_divergencia_com_distancia_imediatamente_abaixo_e_falsa():
    assert dom.divergente_de(0.19, -0.159999) is False  # |diff|=0.349999


def test_confianca_agregada_divergente_e_70_por_cento():
    ajustada = dom.confianca_agregada_ajustada(1.0, 1.0, True)
    assert ajustada == pytest.approx(0.70)


def test_confluencia_zero_com_sinais_opostos():
    assert dom.confluencia_de(0.5, -0.5) == 0.0


def test_confluencia_e_o_minimo_absoluto_com_mesmo_sinal():
    assert dom.confluencia_de(0.5, 0.8) == pytest.approx(0.5)


# ============================================================== limiares BUY/SELL
def test_buy_no_limiar_exato():
    assert dom.classificar_estado_inicial(0.120000, 0, 0, 0, 0, 0) is dom.EstadoDominancia.COMPRA


def test_buy_imediatamente_abaixo_e_balanced():
    assert dom.classificar_estado_inicial(0.119999, 0, 0, 0, 0, 0) is dom.EstadoDominancia.BALANCEADO


def test_sell_no_limiar_exato():
    assert dom.classificar_estado_inicial(-0.120000, 0, 0, 0, 0, 0) is dom.EstadoDominancia.VENDA


def test_sell_imediatamente_acima_e_balanced():
    assert dom.classificar_estado_inicial(-0.119999, 0, 0, 0, 0, 0) is dom.EstadoDominancia.BALANCEADO


# ============================================================== ULTRA entrada
_ULTRA_OK = dict(composite=0.78, micro=0.65, macro=0.65, confluencia=0.65,
                 aggregate_confidence=0.88, qualidade=0.90)


def test_ultra_compra_com_todos_os_requisitos_na_borda():
    assert dom.classificar_estado_inicial(**_ULTRA_OK) is dom.EstadoDominancia.ULTRA_COMPRA


def test_ultra_venda_com_todos_os_requisitos_na_borda():
    args = {k: -v if k in ("composite", "micro", "macro") else v for k, v in _ULTRA_OK.items()}
    assert dom.classificar_estado_inicial(**args) is dom.EstadoDominancia.ULTRA_VENDA


@pytest.mark.parametrize("campo,valor", [
    ("composite", 0.779999), ("micro", 0.649999),
    ("aggregate_confidence", 0.879999), ("qualidade", 0.899999),
])
def test_ultra_falha_se_qualquer_requisito_cair_uma_unidade_abaixo(campo, valor):
    args = dict(_ULTRA_OK)
    args[campo] = valor
    estado = dom.classificar_estado_inicial(**args)
    assert estado is not dom.EstadoDominancia.ULTRA_COMPRA
    assert estado is dom.EstadoDominancia.COMPRA  # degrada para BUY, nunca UNAVAILABLE


# ============================================================== histerese temporal (motor)
def _componentes(valor):
    return {"A": valor, "B": valor, "R": valor, "W": valor, "M": valor}


def _horizonte_forte(sinal, qualidade=0.95, confianca=0.95, amostras=200):
    return dict(componentes=_componentes(sinal), qualidade=qualidade, confianca=confianca,
               amostras=amostras)


def _processar(motor, seq, ts, sinal_micro, sinal_macro, qualidade=0.95, confianca=0.95,
               idade_ms=10.0, modo="LIVE"):
    return motor.processar(
        event_id=f"e{seq}", sequencia=seq, timestamp_ns=ts, instrumento="WDO", modo=modo,
        idade_ms=idade_ms,
        componentes_micro=_componentes(sinal_micro), componentes_macro=_componentes(sinal_macro),
        qualidade_micro=qualidade, qualidade_macro=qualidade,
        confianca_micro=confianca, confianca_macro=confianca,
        amostras_micro=200, amostras_macro=2000,
        cobertura_micro_ms=3000, cobertura_macro_ms=60000,
    )


def test_modo_replay_chega_ao_snapshot_vivo_sem_excecao():
    """Regressao: `Saude(EstadoFeed.REPLAY, ...)` nao existe no enum
    compartilhado (`suporte_resistencia.EstadoFeed` so tem LIVE/STALE/GAP/
    UNAVAILABLE/RECOVERING) e derrubava toda leitura ao vivo no app real,
    porque nenhum teste ate aqui chamava `_processar(..., modo="REPLAY")`
    passando pelo caminho de sucesso (linha `saude=Saude(...)` no fim de
    `processar`)."""

    motor = dom.MotorDominancia("t")
    snap = _processar(motor, 1, 1, 0.5, 0.5, modo="REPLAY")
    assert snap.saude.estado is dom.EstadoFeed.LIVE
    assert snap.composite is not None


def test_buy_mantem_no_limiar_de_manutencao_exato():
    motor = dom.MotorDominancia("t")
    # Primeiro leva o estado a BUY (composite bem acima de 0.12).
    _processar(motor, 1, 1, 0.5, 0.5)
    # Precisa reduzir para exatamente composite=+0.08. Como micro==macro e
    # reliability e simetrica, compor micro=macro=+0.08 da composite=+0.08.
    snap = _processar(motor, 2, 2, 0.08, 0.08)
    assert snap.composite == pytest.approx(0.08, abs=1e-6)
    assert snap.estado is dom.EstadoDominancia.COMPRA


def test_buy_sai_apos_duas_amostras_abaixo_do_limiar():
    motor = dom.MotorDominancia("t")
    _processar(motor, 1, 1, 0.5, 0.5)
    s2 = _processar(motor, 2, 2, 0.05, 0.05)  # abaixo de 0.08, 1a falha
    assert s2.estado is dom.EstadoDominancia.COMPRA  # ainda mantem (so 1 falha)
    s3 = _processar(motor, 3, 3, 0.05, 0.05)  # 2a falha consecutiva
    assert s3.estado is dom.EstadoDominancia.BALANCEADO


def test_cruzamento_forte_troca_lado_comum_imediatamente():
    motor = dom.MotorDominancia("t")
    _processar(motor, 1, 1, 0.5, 0.5)  # BUY
    snap = _processar(motor, 2, 2, -0.5, -0.5)  # cruza direto para negativo forte
    assert snap.estado is dom.EstadoDominancia.VENDA  # nunca ULTRA sem 2 confirmacoes


def test_ultra_exige_duas_confirmacoes_consecutivas():
    motor = dom.MotorDominancia("t")
    sinal = 0.9  # bem acima de todos os limiares ULTRA com qualidade/confianca altas
    s1 = _processar(motor, 1, 1, sinal, sinal)
    assert s1.estado is dom.EstadoDominancia.COMPRA  # 1a confirmacao, ainda nao ULTRA
    s2 = _processar(motor, 2, 2, sinal, sinal)
    assert s2.estado is dom.EstadoDominancia.ULTRA_COMPRA  # 2a confirmacao


def test_ultra_um_snapshot_fora_do_requisito_zera_contador():
    motor = dom.MotorDominancia("t")
    sinal = 0.9
    _processar(motor, 1, 1, sinal, sinal)  # 1a confirmacao
    _processar(motor, 2, 2, 0.3, 0.3)  # fora do requisito -> zera
    s3 = _processar(motor, 3, 3, sinal, sinal)  # teria que ser a 1a de novo
    assert s3.estado is dom.EstadoDominancia.COMPRA  # nao virou ULTRA ainda


def test_tres_falhas_consecutivas_retiram_ultra():
    motor = dom.MotorDominancia("t")
    sinal = 0.9
    _processar(motor, 1, 1, sinal, sinal)
    _processar(motor, 2, 2, sinal, sinal)  # agora ULTRA_COMPRA
    _processar(motor, 3, 3, 0.5, 0.5)  # falha 1 (abaixo de 0.68 mantem)
    _processar(motor, 4, 4, 0.5, 0.5)  # falha 2
    s5 = _processar(motor, 5, 5, 0.5, 0.5)  # falha 3 -> retira ULTRA, reclassifica
    assert s5.estado is dom.EstadoDominancia.COMPRA


def test_duas_falhas_seguidas_de_manutencao_zeram_o_contador():
    motor = dom.MotorDominancia("t")
    sinal = 0.9
    _processar(motor, 1, 1, sinal, sinal)
    _processar(motor, 2, 2, sinal, sinal)  # ULTRA_COMPRA
    _processar(motor, 3, 3, 0.5, 0.5)  # falha 1
    _processar(motor, 4, 4, 0.5, 0.5)  # falha 2
    s5 = _processar(motor, 5, 5, sinal, sinal)  # volta a manter -> zera falhas
    assert s5.estado is dom.EstadoDominancia.ULTRA_COMPRA
    s6 = _processar(motor, 6, 6, 0.5, 0.5)  # falha 1 de novo (nao terceira)
    assert s6.estado is dom.EstadoDominancia.ULTRA_COMPRA


def test_novo_stream_id_limpa_histerese():
    motor = dom.MotorDominancia("t")
    _processar(motor, 1, 1, 0.9, 0.9)
    _processar(motor, 2, 2, 0.9, 0.9)  # ULTRA_COMPRA
    motor.reiniciar("outro-stream")
    s = _processar(motor, 1, 1, 0.9, 0.9)
    assert s.estado is dom.EstadoDominancia.COMPRA  # 1a confirmacao de novo, nao ULTRA


# ============================================================== sequencia/saude
def test_duplicata_e_idempotente():
    motor = dom.MotorDominancia("t")
    primeiro = _processar(motor, 1, 1, 0.5, 0.5)
    segundo = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1, instrumento="WDO", modo="LIVE",
        idade_ms=999, componentes_micro=_componentes(-0.9), componentes_macro=_componentes(-0.9),
        qualidade_micro=0.1, qualidade_macro=0.1, confianca_micro=0.1, confianca_macro=0.1,
        amostras_micro=1, amostras_macro=1, cobertura_micro_ms=1, cobertura_macro_ms=1,
    )
    assert segundo is primeiro


def test_sequencia_atrasada_nao_altera_estado():
    motor = dom.MotorDominancia("t")
    valido = _processar(motor, 5, 5, 0.5, 0.5)
    atrasado = _processar(motor, 3, 3, -0.9, -0.9)
    assert atrasado is valido


def test_timestamp_regressivo_nao_altera_estado():
    motor = dom.MotorDominancia("t")
    valido = _processar(motor, 1, 100, 0.5, 0.5)
    regressivo = _processar(motor, 2, 1, -0.9, -0.9)
    assert regressivo is valido


def test_salto_de_sequencia_produz_gap_com_derivados_nulos():
    motor = dom.MotorDominancia("t")
    _processar(motor, 1, 1, 0.5, 0.5)
    snap = _processar(motor, 5, 5, 0.5, 0.5)
    assert snap.saude.estado is dom.EstadoFeed.GAP
    assert snap.saude.gap_de == 2 and snap.saude.gap_ate == 4
    assert snap.micro is None and snap.macro is None and snap.composite is None


def test_idade_nas_bordas_750_751_3000_3001():
    assert dom.classificar_saude(750, 0.95) is dom.EstadoFeed.LIVE
    assert dom.classificar_saude(751, 0.95) is dom.EstadoFeed.STALE
    assert dom.classificar_saude(3000, 0.95) is dom.EstadoFeed.STALE
    assert dom.classificar_saude(3001, 0.95) is dom.EstadoFeed.UNAVAILABLE


def test_qualidade_nas_bordas_08_exatas():
    assert dom.classificar_saude(100, 0.800000) is dom.EstadoFeed.LIVE
    assert dom.classificar_saude(100, 0.799999) is dom.EstadoFeed.STALE


def test_stale_congela_e_deriva_nulo_mas_preserva_estado_anterior():
    motor = dom.MotorDominancia("t")
    valido = _processar(motor, 1, 1, 0.5, 0.5)
    congelado = _processar(motor, 2, 2, -0.9, -0.9, idade_ms=1000)
    assert congelado.saude.estado is dom.EstadoFeed.STALE
    assert congelado.micro is None and congelado.composite is None
    assert congelado.estado == valido.estado  # nao inventa novo estado direcional


def test_unavailable_nunca_publica_score_zero():
    motor = dom.MotorDominancia("t")
    snap = _processar(motor, 1, 1, 0.5, 0.5, idade_ms=5000)
    assert snap.saude.estado is dom.EstadoFeed.UNAVAILABLE
    assert snap.composite is None
    assert snap.micro is None


# ============================================================== determinismo
def test_determinismo_mesma_entrada_mesma_saida():
    def rodar():
        motor = dom.MotorDominancia("t-determinismo")
        return _processar(motor, 1, 1, 0.42, 0.31)

    a, b = rodar(), rodar()
    assert a == b
