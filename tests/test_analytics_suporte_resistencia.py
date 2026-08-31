"""Suíte obrigatória (seção 10 de ``INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md``)
portada para o motor Python de ``fluxopro/analytics/suporte_resistencia.py``.

Cobre: matemática pura (clamp/winsorização/componentes/fórmulas/limiares),
histerese de entrada/manutenção/watch/invalidação, classificação de lado e
divergência, contra-giro, transições de saúde (LIVE/STALE/GAP/UNAVAILABLE/
RECOVERING) e sequenciamento (duplicata idempotente, regressivo, gap).

Não cobre replay byte-a-byte sobre fixture JSONL (não há harness de
gravação/replay dedicado a este motor no projeto — ver docstring do módulo
para a divergência declarada); em vez disso, `test_determinismo_*` prova a
PROPRIEDADE (mesma entrada, mesma saída) diretamente.
"""

import pytest

from fluxopro.analytics import suporte_resistencia as sr


# ============================================================== clamp/winsor
def test_clamp_satura_nos_dois_lados():
    assert sr.clamp(5) == 1.0
    assert sr.clamp(-5) == -1.0


def test_clamp_nan_vira_zero():
    assert sr.clamp(float("nan")) == 0.0


def test_clamp_nao_finito_vira_zero():
    assert sr.clamp(float("inf")) == 1.0  # satura, nao quebra
    assert sr.clamp(None) == 0.0


def test_winsorizar_divide_pelo_quantil():
    assert sr.winsorizar(0.5, 1.0) == pytest.approx(0.5)
    assert sr.winsorizar(2.0, 1.0) == 1.0


def test_winsorizar_quantil_zero_ou_ausente_e_zero():
    assert sr.winsorizar(0.5, 0.0) == 0.0
    assert sr.winsorizar(0.5, None) == 0.0


# ============================================================ formulas micro/macro
def test_formula_micro_pesos_034_024_024_018():
    micro = sr.calcular_micro(agressao=1.0, desequilibrio_livro=0.0, reposicao=0.0, rejeicao=0.0)
    assert micro == pytest.approx(0.34)


def test_formula_macro_pesos_031_027_024_018():
    macro = sr.calcular_macro(persistencia=1.0, delta_acumulado=0.0, estrutura=0.0, estabilidade=0.0)
    assert macro == pytest.approx(0.31)


def test_formula_contexto_055_045():
    assert sr.calcular_contexto(1.0, 0.0) == pytest.approx(0.55)
    assert sr.calcular_contexto(0.0, 1.0) == pytest.approx(0.45)


def test_componente_nao_finito_nao_propaga():
    micro = sr.calcular_micro(agressao=float("nan"), desequilibrio_livro=0.5,
                              reposicao=0.5, rejeicao=0.5)
    assert -1.0 <= micro <= 1.0
    assert micro == sr.calcular_micro(0.0, 0.5, 0.5, 0.5)


def test_forca_zona_pesos_e_teto_de_toques():
    forca = sr.calcular_forca_zona(reposicao=1.0, rejeicao=1.0, desequilibrio_livro=1.0, toques=100)
    assert forca == pytest.approx(1.0)  # 0.35+0.25+0.20+0.20 = 1.0, teto de toques em 5


def test_forca_zona_toques_zero_nao_contribui():
    com_toque = sr.calcular_forca_zona(0.0, 0.0, 0.0, toques=5)
    sem_toque = sr.calcular_forca_zona(0.0, 0.0, 0.0, toques=0)
    assert com_toque == pytest.approx(0.20)
    assert sem_toque == 0.0


def test_forca_zona_divisao_por_toques_nao_quebra_com_negativo():
    assert sr.calcular_forca_zona(0.0, 0.0, 0.0, toques=-3) == 0.0


def test_confianca_zona_produto_qualidade_e_amostras():
    assert sr.confianca_zona(0.9, 0.8, 100) == pytest.approx(0.8)  # min(q)=0.8, amostras satura
    assert sr.confianca_zona(0.9, 0.8, 25) == pytest.approx(0.8 * 0.5)


def test_confianca_zona_amostras_zero_e_zero():
    assert sr.confianca_zona(1.0, 1.0, 0) == 0.0


# ============================================================ classificacao
def test_classifica_suporte_nos_limiares_exatos():
    assert sr.classificar_lado(sr.LIMIAR_CONTEXTO_SUPORTE, sr.LIMIAR_FORCA_ZONA) is sr.LadoZona.SUPORTE


def test_classifica_resistencia_nos_limiares_exatos():
    assert sr.classificar_lado(sr.LIMIAR_CONTEXTO_RESISTENCIA, sr.LIMIAR_FORCA_ZONA) is sr.LadoZona.RESISTENCIA


def test_contexto_forte_sem_forca_de_zona_e_neutro():
    assert sr.classificar_lado(0.9, 0.10) is sr.LadoZona.NEUTRO


def test_forca_forte_sem_contexto_e_neutro():
    assert sr.classificar_lado(0.01, 0.99) is sr.LadoZona.NEUTRO


def test_imediatamente_abaixo_do_limiar_de_suporte_e_neutro():
    assert sr.classificar_lado(sr.LIMIAR_CONTEXTO_SUPORTE - 1e-6, 0.9) is sr.LadoZona.NEUTRO


# ============================================================ divergencia/contragiro
def test_divergencia_sinais_opostos_e_distancia_suficiente():
    assert sr.e_divergente(0.5, -0.5) is True


def test_sem_divergencia_mesmo_sinal():
    assert sr.e_divergente(0.5, 0.4) is False


def test_sem_divergencia_distancia_insuficiente():
    assert sr.e_divergente(0.05, -0.05) is False  # produto<0 mas |diff|<0.35


def test_confianca_ajustada_por_divergencia_e_70_por_cento():
    assert sr.confianca_ajustada(1.0, True) == pytest.approx(0.70)
    assert sr.confianca_ajustada(1.0, False) == 1.0


def test_contragiro_preserva_modulo_inverte_sinal():
    cg = sr.contragiro_de(0.6, -0.3)
    assert cg.micro == pytest.approx(-0.6)
    assert cg.macro == pytest.approx(0.3)


def test_contragiro_com_ausencia_e_none():
    cg = sr.contragiro_de(None, -0.3)
    assert cg.micro is None
    assert cg.macro == pytest.approx(0.3)
    assert cg.divergente is False


def test_contragiro_marca_divergente_quando_aplicavel():
    cg = sr.contragiro_de(0.6, -0.3)
    assert cg.divergente is True


# ============================================================ histerese
def test_pode_entrar_nos_limiares_exatos():
    assert sr.pode_entrar(score=0.55, proximidade_em_larguras=1.0, confianca=0.80) is True


def test_pode_entrar_falha_por_proximidade():
    assert sr.pode_entrar(score=0.9, proximidade_em_larguras=1.01, confianca=0.9) is False


def test_pode_entrar_falha_por_confianca():
    assert sr.pode_entrar(score=0.9, proximidade_em_larguras=0.5, confianca=0.79) is False


def test_pode_manter_e_mais_tolerante_que_entrar():
    # Um score que NAO entraria (abaixo de 0.55) ainda mantem (>=0.45).
    assert sr.pode_entrar(score=0.5, proximidade_em_larguras=1.0, confianca=0.9) is False
    assert sr.pode_manter(score=0.5, proximidade_em_larguras=1.0, confianca=0.9) is True


def test_pode_manter_nos_limiares_exatos():
    assert sr.pode_manter(score=0.45, proximidade_em_larguras=1.25, confianca=0.75) is True


def test_watch_por_score_medio():
    assert sr.e_watch(score=0.50, proximidade_em_larguras=99) is True


def test_watch_por_proximidade_mesmo_com_score_baixo():
    assert sr.e_watch(score=0.0, proximidade_em_larguras=1.75) is True


def test_watch_nunca_aciona_fora_da_faixa():
    assert sr.e_watch(score=0.0, proximidade_em_larguras=2.0) is False


def test_deve_invalidar_exige_macro_concordante():
    assert sr.deve_invalidar(90, 100, 110, 10, sr.LadoZona.SUPORTE, macro_concordante=False) is False


def test_deve_invalidar_suporte_fecha_abaixo_do_limite():
    # zona [100,110], largura 10, limite = 1.5*10=15 => invalida abaixo de 100-15=85
    assert sr.deve_invalidar(80, 100, 110, 10, sr.LadoZona.SUPORTE, macro_concordante=True) is True
    assert sr.deve_invalidar(90, 100, 110, 10, sr.LadoZona.SUPORTE, macro_concordante=True) is False


def test_deve_invalidar_resistencia_fecha_acima_do_limite():
    assert sr.deve_invalidar(130, 100, 110, 10, sr.LadoZona.RESISTENCIA, macro_concordante=True) is True
    assert sr.deve_invalidar(115, 100, 110, 10, sr.LadoZona.RESISTENCIA, macro_concordante=True) is False


# ============================================================ saude
def test_saude_live_dentro_dos_limiares():
    assert sr.classificar_saude(idade_ms=100, qualidade=0.9) is sr.EstadoFeed.LIVE


def test_saude_stale_por_idade():
    assert sr.classificar_saude(idade_ms=1000, qualidade=0.9) is sr.EstadoFeed.STALE


def test_saude_stale_por_qualidade_baixa():
    assert sr.classificar_saude(idade_ms=100, qualidade=0.5) is sr.EstadoFeed.STALE


def test_saude_unavailable_por_idade_extrema():
    assert sr.classificar_saude(idade_ms=5000, qualidade=1.0) is sr.EstadoFeed.UNAVAILABLE


# ============================================================ motor: sequencia/idempotencia
def _horizonte(score=0.6, qualidade=0.9, amostras=100):
    return sr.HorizonteScore(score=score, qualidade=qualidade, janela_ms=3000,
                             amostras=amostras, componentes={"aggression": score})


def _zona(id_="S-1", lado=sr.LadoZona.SUPORTE, preco=100, score=0.8, confianca=0.9, toques=5):
    return sr.Zona(id=id_, lado=lado, preco=preco, inferior=preco - 1, superior=preco + 1,
                   score=score, confianca=confianca, toques=toques, fontes=("vap-poc",),
                   status=sr.EstadoZona.ATIVA)


_S = 1_000_000_000


def test_evento_valido_publica_live():
    motor = sr.MotorSuporteResistencia("teste")
    snap = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=1 * _S,
    )
    assert snap.saude.estado is sr.EstadoFeed.LIVE
    assert snap.dominante is not None


def test_duplicata_e_idempotente():
    motor = sr.MotorSuporteResistencia("teste")
    primeiro = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=1 * _S,
    )
    segundo = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=999, micro=_horizonte(score=-0.9), macro=_horizonte(score=-0.9),
        zonas_candidatas=(), agora_ns=99 * _S,
    )
    assert segundo is primeiro  # mesmo objeto cacheado, nunca recalculado


def test_sequencia_regressiva_e_rejeitada_e_nao_altera_estado():
    motor = sr.MotorSuporteResistencia("teste")
    valido = motor.processar(
        event_id="e1", sequencia=5, timestamp_ns=5 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=5 * _S,
    )
    rejeitado = motor.processar(
        event_id="e-velho", sequencia=3, timestamp_ns=3 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=1, micro=_horizonte(score=0.99), macro=_horizonte(score=0.99),
        zonas_candidatas=(), agora_ns=5 * _S,
    )
    assert rejeitado is valido


def test_timestamp_regressivo_e_rejeitado():
    motor = sr.MotorSuporteResistencia("teste")
    valido = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=10 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=10 * _S,
    )
    rejeitado = motor.processar(
        event_id="e2", sequencia=2, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=1, micro=_horizonte(score=-0.9), macro=_horizonte(score=-0.9),
        zonas_candidatas=(), agora_ns=10 * _S,
    )
    assert rejeitado is valido


def test_salto_de_sequencia_publica_gap():
    motor = sr.MotorSuporteResistencia("teste")
    motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=1 * _S,
    )
    snap = motor.processar(
        event_id="e5", sequencia=5, timestamp_ns=5 * _S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=101, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=5 * _S,
    )
    assert snap.saude.estado is sr.EstadoFeed.GAP
    assert snap.saude.gap_de == 2
    assert snap.saude.gap_ate == 4


def test_recuperacao_exige_50_amostras_e_1s_sem_gap():
    motor = sr.MotorSuporteResistencia("teste")
    motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=0, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=0,
    )
    motor.processar(
        event_id="e-gap", sequencia=10, timestamp_ns=10, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(),
        zonas_candidatas=(_zona(),), agora_ns=10,
    )
    # Poucas amostras e pouco tempo: ainda RECOVERING.
    snap_cedo = motor.processar(
        event_id="e11", sequencia=11, timestamp_ns=20, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(), macro=_horizonte(), zonas_candidatas=(_zona(),),
        agora_ns=20,
    )
    assert snap_cedo.saude.estado is sr.EstadoFeed.RECOVERING

    # 50 amostras saudaveis E pelo menos 1s (em ns) desde o inicio da
    # recuperacao (que comecou no timestamp do proprio evento de GAP, 10ns)
    # sao as DUAS condicoes exigidas antes de voltar a LIVE.
    ultimo_snapshot = snap_cedo
    sequencia = 11  # proximo processado sera 12 (sem pular numero, sem novo GAP)
    timestamp_ns = 20
    while True:
        sequencia += 1
        timestamp_ns += sr.TEMPO_RECUPERACAO_SEM_GAP_NS  # cada passo ja cobre a janela de 1s
        ultimo_snapshot = motor.processar(
            event_id=f"e{sequencia}", sequencia=sequencia, timestamp_ns=timestamp_ns,
            instrumento="WDO", tick_size=0.5, ultimo_preco=100,
            micro=_horizonte(), macro=_horizonte(), zonas_candidatas=(_zona(),),
            agora_ns=timestamp_ns,
        )
        if sequencia - 11 >= sr.AMOSTRAS_RECUPERACAO_MIN:
            break
    assert ultimo_snapshot.saude.estado is sr.EstadoFeed.LIVE


def test_stale_por_idade_alta_congela():
    motor = sr.MotorSuporteResistencia("teste")
    valido = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=0, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(score=0.7), macro=_horizonte(score=0.7),
        zonas_candidatas=(_zona(),), agora_ns=0,
    )
    congelado = motor.processar(
        event_id="e2", sequencia=2, timestamp_ns=_S, instrumento="WDO", tick_size=0.5,
        ultimo_preco=1, micro=_horizonte(score=-0.99), macro=_horizonte(score=-0.99),
        zonas_candidatas=(), agora_ns=_S + 1_500_000_000,  # 1,5s de idade
    )
    assert congelado.saude.estado is sr.EstadoFeed.STALE
    assert congelado.ultimo_preco == valido.ultimo_preco
    assert congelado.micro is valido.micro
    assert congelado.zonas == valido.zonas


def test_unavailable_por_idade_extrema_nao_mostra_zero():
    motor = sr.MotorSuporteResistencia("teste")
    snap = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=0, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=_horizonte(score=0.7), macro=_horizonte(score=0.7),
        zonas_candidatas=(_zona(),), agora_ns=10 * _S,  # 10s de idade
    )
    assert snap.saude.estado is sr.EstadoFeed.UNAVAILABLE
    assert snap.micro is None
    assert snap.macro is None
    assert snap.ultimo_preco is None  # nunca 0 sintetico


def test_horizonte_ausente_e_unavailable():
    motor = sr.MotorSuporteResistencia("teste")
    snap = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=0, instrumento="WDO", tick_size=0.5,
        ultimo_preco=100, micro=None, macro=_horizonte(), zonas_candidatas=(), agora_ns=0,
    )
    assert snap.saude.estado is sr.EstadoFeed.UNAVAILABLE


# ============================================================ determinismo
def test_determinismo_mesma_entrada_mesma_saida():
    """Prova a PROPRIEDADE que o replay byte-a-byte da especificacao exige —
    sem harness de fixture JSONL (ver docstring do modulo)."""

    def _rodar():
        motor = sr.MotorSuporteResistencia("teste-determinismo")
        return motor.processar(
            event_id="e1", sequencia=1, timestamp_ns=1 * _S, instrumento="WDO", tick_size=0.5,
            ultimo_preco=100, micro=_horizonte(0.6), macro=_horizonte(0.4),
            zonas_candidatas=(_zona(),), agora_ns=1 * _S,
        )

    primeiro, segundo = _rodar(), _rodar()
    assert primeiro == segundo


def test_determinismo_dominante_desempata_por_preco_e_id():
    zonas = (
        _zona(id_="S-A", preco=100, score=0.8, confianca=0.9, toques=5),
        _zona(id_="S-B", preco=95, score=0.8, confianca=0.9, toques=5),
    )
    dominante1 = sr.dominante_de(zonas)
    dominante2 = sr.dominante_de(tuple(reversed(zonas)))
    assert dominante1.id == dominante2.id == "S-B"  # suporte: MENOR preco desempata

