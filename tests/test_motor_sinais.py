from __future__ import annotations

from dataclasses import replace

import pytest

from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.motor.sinais import (
    ConfigMotorSinais,
    EstagioSinal,
    FaixaConviccao,
    MotorSinais,
)

S = 1_000_000_000  # um segundo em ns


def _trade(ts, price, qty, agressor, symbol="WDOV26"):
    return Trade(
        timestamp_ns=ts, symbol=symbol, price=price, qty=qty,
        side_agressor=agressor, trade_id=f"t{ts}",
    )


def _motor(**overrides):
    """Motor com as DUAS travas de estado desligadas (histerese e magnitude).

    Os testes de lógica pura isolam UMA condição de cada vez; histerese e
    normalização por magnitude têm testes dedicados abaixo
    (`test_histerese_*`, `test_winfut_*`, `test_magnitude_*`). Os defaults de
    fábrica têm testes próprios (`test_default_*`) — a crítica R2 apontou que
    nenhum teste os exercia, e por isso `dominancia_minima` podia ir a 0.0 e a
    janela da "micro" virar um dia inteiro com a suíte verde.
    """
    cfg = ConfigMotorSinais(
        dominancia_minima=0.70,
        janela_dominancia_ns=10 * S,
        margem_regiao_ticks=0,
        janela_micro_ns=5 * S,
        pre_sinal_fracao_janela_micro=0.5,
        persistencia_minima_trades=1,
        persistencia_minima_ns=0,
        rebaixamento_minimo_trades=1,
        rebaixamento_minimo_ns=0,
        magnitude_relativa_minima=0.0,
    )
    if overrides:
        cfg = replace(cfg, **overrides)
    vp = VolumeProfile()
    return MotorSinais("WDOV26", vp, cfg), vp


def _encher_perfil(vp, preco=5000, n=20, qty=50):
    for i in range(n):
        vp.registrar_trade(_trade(i, preco, qty, AgressorSide.BUY))


# ---------------------------------------------------------------------------
# Confluência básica (as 6 asserções originais, preservadas)
# ---------------------------------------------------------------------------


def test_sem_dominancia_fica_em_nenhum():
    motor, _ = _motor()
    motor.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY))
    sinal = motor.ao_trade(_trade(1, 5000, 10, AgressorSide.SELL))
    assert sinal.estagio is EstagioSinal.NENHUM


def test_dominancia_confirmada_mas_fora_da_regiao_fica_em_direcao_confirmada():
    motor, vp = _motor()
    # constroi um perfil de volume concentrado em 4900 (regiao)
    _encher_perfil(vp, preco=4900)
    # dominancia compradora forte, mas preco atual (5000) fora da regiao 4900
    sinal = None
    for i in range(5):
        sinal = motor.ao_trade(_trade(100 + i, 5000, 100, AgressorSide.BUY))
    assert sinal.estagio is EstagioSinal.DIRECAO_CONFIRMADA
    assert sinal.direcao is Side.BUY


def test_confluencia_completa_gera_confirmado():
    motor, vp = _motor()
    _encher_perfil(vp)
    # dominancia compradora forte no preco 5000 (dentro da regiao)
    ts = 1000
    sinal = None
    for _ in range(4):
        sinal = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += S // 2
    assert sinal.estagio is EstagioSinal.CONFIRMADO
    assert sinal.direcao is Side.BUY
    assert sinal.evidencia["micro_virou"] is True


def test_estagio_atual_reflete_ultimo_sinal():
    motor, vp = _motor()
    _encher_perfil(vp)
    ts = 1000
    for _ in range(4):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += S // 2
    assert motor.estagio_atual is EstagioSinal.CONFIRMADO


def test_trade_de_outro_symbol_e_ignorado():
    motor, _ = _motor()
    sinal = motor.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, symbol="WINV26"))
    assert sinal.estagio is EstagioSinal.NENHUM


# ---------------------------------------------------------------------------
# DEFEITO 2 — `PRE_SINAL` só quando a micro MELHORA na direção do alvo
# ---------------------------------------------------------------------------
#
# Cenário comum aos três: alvo BUY, preço na região, primeira metade da janela
# micro com delta -100 (contra o alvo). Só muda a segunda metade. A crítica R2
# mediu que os três produziam `PRE_SINAL` — inclusive a micro piorando 4x
# contra a posição.


def _cenario_micro(segunda_metade_qty, segunda_metade_lado):
    motor, vp = _motor(
        janela_dominancia_ns=60 * S,
        janela_micro_ns=4 * S,
        pre_sinal_fracao_janela_micro=0.5,
    )
    _encher_perfil(vp)
    # base compradora larga: mantém a dominância do dia acima de 0.70 em todos
    # os três casos (inclusive quando a segunda metade despeja 400 vendedores),
    # e fica FORA da janela micro de 4s quando chegarmos aos 30s.
    ts = 0
    for _ in range(20):
        motor.ao_trade(_trade(ts, 5000, 500, AgressorSide.BUY))
        ts += 100_000_000
    # primeira metade da janela micro: -100
    motor.ao_trade(_trade(30 * S, 5000, 50, AgressorSide.SELL))
    motor.ao_trade(_trade(30 * S + 200_000_000, 5000, 50, AgressorSide.SELL))
    # segunda metade
    return motor.ao_trade(
        _trade(32 * S + 500_000_000, 5000, segunda_metade_qty, segunda_metade_lado)
    )


def test_pre_sinal_quando_micro_melhora_na_direcao_do_alvo():
    # -100 -> -20: o fluxo está virando a favor, mas ainda não cruzou.
    sinal = _cenario_micro(20, AgressorSide.SELL)
    assert sinal.evidencia["delta_micro_primeira_metade"] == -100
    assert sinal.evidencia["delta_micro_segunda_metade"] == -20
    assert sinal.evidencia["micro_virou"] is False
    assert sinal.estagio is EstagioSinal.PRE_SINAL


def test_micro_parada_nao_e_pre_sinal():
    # -100 -> -100: nada mudou. Farol amarelo aqui é rótulo falso.
    sinal = _cenario_micro(100, AgressorSide.SELL)
    assert sinal.evidencia["delta_micro_segunda_metade"] == -100
    assert sinal.evidencia["pre_sinal"] is False
    assert sinal.estagio is EstagioSinal.NA_REGIAO


def test_micro_piorando_contra_nao_e_pre_sinal():
    # -100 -> -400: acelerando CONTRA a direção pretendida.
    sinal = _cenario_micro(400, AgressorSide.SELL)
    assert sinal.evidencia["delta_micro_segunda_metade"] == -400
    assert sinal.evidencia["pre_sinal"] is False
    assert sinal.estagio is EstagioSinal.NA_REGIAO


def test_pre_sinal_exige_as_duas_metades_da_janela():
    """Com trades só na metade recente não há comparação possível — e sem
    comparação não há como afirmar que o fluxo "está virando"."""
    motor, vp = _motor(janela_dominancia_ns=60 * S, janela_micro_ns=4 * S)
    _encher_perfil(vp)
    ts = 0
    for _ in range(20):
        motor.ao_trade(_trade(ts, 5000, 500, AgressorSide.BUY))
        ts += 100_000_000
    # um único trade vendedor 30s depois: a janela micro tem só metade recente
    sinal = motor.ao_trade(_trade(30 * S, 5000, 50, AgressorSide.SELL))
    assert sinal.evidencia["delta_micro_primeira_metade"] == 0
    assert sinal.evidencia["pre_sinal"] is False
    assert sinal.estagio is EstagioSinal.NA_REGIAO


def test_micro_que_cruza_para_o_alvo_e_confirmado_nao_pre_sinal():
    sinal = _cenario_micro(400, AgressorSide.BUY)  # -100 + 400 = +300
    assert sinal.evidencia["micro_virou"] is True
    assert sinal.estagio is EstagioSinal.CONFIRMADO


# ---------------------------------------------------------------------------
# DEFEITO 3 (a) — magnitude relativa: o modo de falha do WINFUT
# ---------------------------------------------------------------------------


def _config_winfut(**overrides):
    cfg = ConfigMotorSinais(
        dominancia_minima=0.70,
        janela_dominancia_ns=60 * S,
        margem_regiao_ticks=0,
        janela_micro_ns=5 * S,
        magnitude_relativa_minima=0.60,
        persistencia_minima_trades=3,
        persistencia_minima_ns=S // 2,
        rebaixamento_minimo_trades=3,
        rebaixamento_minimo_ns=S // 2,
    )
    return replace(cfg, **overrides) if overrides else cfg


def _tape_winfut(n_lateral=0, qty_repique=9):
    """Fase vendedora de magnitude ALTA, `n_lateral` trades laterais e miúdos,
    e depois a fase compradora de magnitude MENOR — o análogo dos picos -1925
    e +915 de 11/02 (`pesquisa/ferramenta_componentes.md:97-105`).

    Nas duas fases direcionais a dominância percentual é IDÊNTICA (0.900): é
    exatamente isso que a razão percentual não distingue. O que difere é o
    tamanho do fluxo: qty 20 na fase vendedora contra qty 9 na compradora
    (0,45 — a mesma ordem do 915/1925 do relato).

    `n_lateral` é o eixo que as auditorias R3 e R4 usaram para furar o gate:
    o pico do dia continua o mesmo, só o TEMPO de tape morno entre as duas
    fases muda. Ver `.mut/sonda2_r3.py`, sonda E.
    """
    trades = []
    ts = 0
    for i in range(900):  # 90s de fase vendedora, 90% SELL, qty 20
        lado = AgressorSide.BUY if i % 10 == 0 else AgressorSide.SELL
        trades.append(_trade(ts, 5000, 20, lado))
        ts += 100_000_000
    for i in range(n_lateral):  # o resto do dia: lateral, equilibrado, miúdo
        lado = AgressorSide.BUY if i % 2 == 0 else AgressorSide.SELL
        trades.append(_trade(ts, 5000, 2, lado))
        ts += 100_000_000
    for i in range(900):  # 90s de fase compradora
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        trades.append(_trade(ts, 5000, qty_repique, lado))
        ts += 100_000_000
    return trades


def _rodar_winfut(cfg, n_lateral=0, qty_repique=9):
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    return [motor.ao_trade(t) for t in _tape_winfut(n_lateral, qty_repique)], motor


def _compras_confirmadas(sinais):
    return [
        s for s in sinais
        if s.estagio is EstagioSinal.CONFIRMADO and s.direcao is Side.BUY
    ]


def test_winfut_nao_emite_confirmado_de_compra_no_repique_de_magnitude_menor():
    sinais, motor = _rodar_winfut(_config_winfut())
    compras_confirmadas = [
        s for s in sinais
        if s.estagio is EstagioSinal.CONFIRMADO and s.direcao is Side.BUY
    ]
    assert compras_confirmadas == []
    # e a direção de compra não é dada nem como "direção do dia"
    assert [s for s in sinais if s.direcao is Side.BUY] == []

    fim = sinais[-1]
    assert fim.estagio is EstagioSinal.NENHUM
    assert fim.evidencia["bloqueio"] == "magnitude_relativa"
    # a dominância percentual do repique é ALTA — não é ela que barra
    assert fim.evidencia["dominancia"] >= 0.85
    assert fim.evidencia["faixa"] == FaixaConviccao.MAXIMA_CONVICCAO.value
    # o que barra é a magnitude: o repique é ~45% do fluxo da fase vendedora
    assert fim.evidencia["magnitude_relativa"] < 0.60
    assert motor.estagio_atual is EstagioSinal.NENHUM


def test_winfut_controle_sem_o_gate_de_magnitude_o_motor_cai_no_modo_de_falha():
    """Prova que o cenário é real e que é o gate — não outra coisa — que o
    barra: desligado o gate, o motor emite `CONFIRMADO` de COMPRA no repique,
    que é o sinal falso descrito pela fonte."""
    sinais, _ = _rodar_winfut(_config_winfut(magnitude_relativa_minima=0.0))
    compras_confirmadas = [
        s for s in sinais
        if s.estagio is EstagioSinal.CONFIRMADO and s.direcao is Side.BUY
    ]
    assert compras_confirmadas != []


def test_magnitude_relativa_alta_nao_barra_movimento_do_tamanho_do_dia():
    """O gate não pode ser um "sempre não": um movimento na magnitude do
    próprio dia passa."""
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, _config_winfut())
    sinal = None
    ts = 0
    for i in range(900):
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        sinal = motor.ao_trade(_trade(ts, 5000, 20, lado))
        ts += 100_000_000
    assert sinal.evidencia["magnitude_relativa"] >= 0.60
    assert sinal.estagio is EstagioSinal.CONFIRMADO
    assert sinal.direcao is Side.BUY


# ---------------------------------------------------------------------------
# DEFEITO R3/R4 — a variante do WINFUT com tape morno no meio
#
# O gate original normalizava pelo percentil 0,95 de um reservoir uniforme do
# dia. Com 20.000 trades laterais entre o pico e o repique, a massa da amostra
# vira lateral, o p95 desce e o repique — que continua sendo 45% do pico REAL
# do dia — passa. R3 mediu 480 `CONFIRMADO` de compra espúrios; R4 remediu o
# mesmo número, sem mudança. Os testes abaixo são o que faltava: o cenário da
# falha, o controle que prova que é o gate que barra, o "não é sempre não", o
# outlier de abertura e a varredura de N laterais.
# ---------------------------------------------------------------------------

N_LATERAIS_VARREDURA = (0, 1_000, 5_000, 20_000, 50_000)


def test_winfut_com_20000_laterais_nao_emite_confirmado_de_compra():
    """O cenário exato de `criticas/nucleo_r3.md` §A.4 e `nucleo_r4.md` §C.2."""
    sinais, motor = _rodar_winfut(_config_winfut(), n_lateral=20_000)
    assert _compras_confirmadas(sinais) == []

    fim = sinais[-1]
    # a dominância percentual do repique é ALTA — não é ela que barra
    assert fim.evidencia["dominancia"] >= 0.85
    assert fim.evidencia["faixa"] == FaixaConviccao.MAXIMA_CONVICCAO.value
    # o que barra é a magnitude, medida contra o PICO do dia (não contra a
    # distribuição recente, que os 20.000 laterais tinham derrubado)
    assert fim.evidencia["bloqueio"] == "magnitude_relativa"
    assert fim.evidencia["magnitude_relativa"] < 0.60
    assert fim.estagio is EstagioSinal.NENHUM
    assert motor.estagio_atual is EstagioSinal.NENHUM
    # a referência continua na ordem do pico do dia, não na do tape morno
    assert fim.evidencia["magnitude_referencia"] >= 0.5 * fim.evidencia["magnitude_pico_sessao"]


def test_winfut_com_20000_laterais_controle_sem_o_gate_cai_no_modo_de_falha():
    """Controle do cenário da R3/R4: desligado o gate, o motor emite os
    `CONFIRMADO` de compra espúrios. Prova que o tape é mesmo um modo de falha
    e que é o gate — não outro efeito colateral dos 20.000 laterais — que o
    barra no teste acima."""
    sinais, _ = _rodar_winfut(
        _config_winfut(magnitude_relativa_minima=0.0), n_lateral=20_000
    )
    assert len(_compras_confirmadas(sinais)) > 100


@pytest.mark.parametrize("n_lateral", N_LATERAIS_VARREDURA)
def test_winfut_varredura_de_laterais_zero_confirmado_espurio(n_lateral):
    """Varredura do eixo que a R3 usou. O teste anterior do repositório vivia
    em `n_lateral=0` — o único ponto da curva em que o gate antigo segurava.
    Aqui todos os pontos têm de segurar, senão a correção é outra vez local a
    um ponto."""
    sinais, _ = _rodar_winfut(_config_winfut(), n_lateral=n_lateral)
    assert _compras_confirmadas(sinais) == []


@pytest.mark.parametrize("n_lateral", N_LATERAIS_VARREDURA)
def test_movimento_do_tamanho_do_dia_passa_em_qualquer_ponto_da_varredura(n_lateral):
    """O contrário do "sempre não": um movimento comprador da magnitude do
    próprio pico do dia (qty 20, a mesma da fase vendedora) tem de virar
    `CONFIRMADO` — inclusive depois de 50.000 trades laterais."""
    sinais, _ = _rodar_winfut(_config_winfut(), n_lateral=n_lateral, qty_repique=20)
    assert _compras_confirmadas(sinais) != []
    assert sinais[-1].evidencia["magnitude_relativa"] >= 0.60


def test_outlier_de_abertura_nao_trava_o_motor_pelo_resto_do_dia():
    """Um único negócio gigante na abertura (fat finger / leilão) não pode
    virar a referência de magnitude do dia inteiro.

    É o risco de usar `max` de sessão como referência, e ele é pior que o
    defeito original porque é silencioso: o motor simplesmente não confirma
    mais nada. Aqui o trade de 100.000 lotes entra, sai da janela, e o
    movimento legítimo que vem depois continua sendo confirmado.
    """
    cfg = _config_winfut()
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    ts = 0

    # dois negócios normais antes — o fat finger não é o primeiro print do
    # dia, e é isso que exige que `_maiores_qty` seja um deque MONOTÔNICO: se
    # ele guardasse o negócio mais antigo da janela em vez do maior, o filtro
    # de negócio único leria "2 lotes" e deixaria o fat finger entrar.
    for _ in range(2):
        motor.ao_trade(_trade(ts, 5000, 2, AgressorSide.BUY))
        ts += 100_000_000
    motor.ao_trade(_trade(ts, 5000, 100_000, AgressorSide.BUY))
    ts += 100_000_000
    for i in range(5_000):  # o resto da manhã: lateral e miúdo
        lado = AgressorSide.BUY if i % 2 == 0 else AgressorSide.SELL
        motor.ao_trade(_trade(ts, 5000, 2, lado))
        ts += 100_000_000

    sinais = []
    for i in range(900):  # movimento comprador legítimo, de tape normal
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        sinais.append(motor.ao_trade(_trade(ts, 5000, 20, lado)))
        ts += 100_000_000

    assert _compras_confirmadas(sinais) != []
    # e a referência NÃO é o fat finger
    assert sinais[-1].evidencia["magnitude_referencia"] < 100_000


def test_referencia_ignora_magnitude_que_um_unico_negocio_explica():
    """O mecanismo do teste acima, isolado: enquanto a magnitude da janela for
    explicada por um só negócio, ela não entra na referência."""
    cfg = _config_winfut()
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    motor.ao_trade(_trade(0, 5000, 100_000, AgressorSide.BUY))
    assert motor._reservatorio == []
    assert motor._n_visto == 0
    assert motor._magnitude_referencia(0) is None


def test_com_amostra_curta_a_referencia_e_o_maximo_da_sessao():
    """Antes de `minimo_amostras_referencia` a referência é o MÁXIMO da sessão
    — a leitura conservadora — e não a K-ésima maior de uma amostra que ainda
    não é uma cauda. Se fosse a K-ésima maior de 3 amostras, a referência
    seria a MENOR delas e o gate nasceria escancarado."""
    cfg = _config_winfut(tamanho_topo_magnitude=8, minimo_amostras_referencia=8)
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    ts = 0
    # magnitude cresce 100, 200, 300... com o maior negócio isolado em 100:
    # da terceira em diante ela passa do filtro de negócio único e é amostrada
    for _ in range(6):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.SELL))
        ts += 100_000_000
    assert 0 < len(motor._reservatorio) < 8
    assert motor._magnitude_referencia(ts) == float(max(motor._reservatorio))
    assert motor._magnitude_referencia(ts) > float(min(motor._reservatorio))


def test_default_de_fabrica_protege_a_abertura_com_o_maximo_da_sessao():
    """O default de `minimo_amostras_referencia` (não o valor que um teste
    escolhe) é o que roda em produção. Com ele em 0 o gate nasceria calibrado
    pela PRIMEIRA amostra da sessão — a razão passaria de 1,0 e a abertura, o
    momento de maior magnitude do dia, ficaria sem filtro."""
    cfg_default = ConfigMotorSinais()
    assert cfg_default.minimo_amostras_referencia > 1
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg_default)
    ts = 0
    sinal = None
    for _ in range(10):  # magnitude estritamente crescente
        sinal = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.SELL))
        ts += 100_000_000
    assert 1 < len(motor._reservatorio) < cfg_default.minimo_amostras_referencia
    assert motor._magnitude_referencia(ts) == float(max(motor._reservatorio))
    assert sinal.evidencia["magnitude_relativa"] <= 1.0


def test_referencia_e_a_kesima_maior_e_nao_o_maximo_da_sessao():
    """Um estouro CURTO de magnitude não pode virar a referência do dia.

    É a diferença entre `max` de sessão e K-ésima maior: o estouro produz
    poucas amostras (menos que K), então ele entra no topo mas não chega ao
    `[0]` do heap. Com `max`, o fluxo NORMAL do resto do dia passaria a valer
    uma fração da referência e o motor não confirmaria mais nada.
    """
    cfg = _config_winfut(janela_dominancia_ns=1 * S)  # 10 trades por janela
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    ts = 0
    for i in range(300):  # tape normal
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        motor.ao_trade(_trade(ts, 5000, 20, lado))
        ts += 100_000_000
    for _ in range(3):  # estouro curto: 3 negócios de 500
        motor.ao_trade(_trade(ts, 5000, 500, AgressorSide.SELL))
        ts += 100_000_000
    pico = motor._max_sessao

    sinais = []
    for i in range(300):  # movimento comprador legítimo, de tamanho normal
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        sinais.append(motor.ao_trade(_trade(ts, 5000, 20, lado)))
        ts += 100_000_000

    ref = motor._magnitude_referencia(ts)
    assert ref < pico  # a referência NÃO é o máximo da sessão
    assert _compras_confirmadas(sinais) != []


def test_iniciar_nova_sessao_zera_a_referencia_de_magnitude():
    """`criticas/nucleo_r3.md` §C.4: o p95 do dia 2 era o do dia 1, e o motor
    não tinha API para virar o dia."""
    cfg = _config_winfut()
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp, cfg)
    ts = 0
    for i in range(900):
        lado = AgressorSide.BUY if i % 10 == 0 else AgressorSide.SELL
        motor.ao_trade(_trade(ts, 5000, 500, lado))
        ts += 100_000_000
    ref_dia1 = motor._magnitude_referencia(ts)
    assert ref_dia1 is not None and ref_dia1 > 0
    assert motor.estagio_atual is not EstagioSinal.NENHUM

    motor.iniciar_nova_sessao()

    assert motor._reservatorio == []
    assert motor._n_visto == 0
    assert motor._magnitude_referencia(ts) is None
    assert motor.estagio_atual is EstagioSinal.NENHUM
    assert motor.direcao_atual is None
    # e o dia 2 não herda a calibração do dia 1
    s = motor.ao_trade(_trade(86_400 * S, 5000, 1, AgressorSide.BUY))
    assert s.evidencia["magnitude_pico_sessao"] < ref_dia1


# ---------------------------------------------------------------------------
# DEFEITO 3 (b) — histerese
# ---------------------------------------------------------------------------


def _motor_com_histerese():
    return _motor(
        persistencia_minima_trades=3,
        persistencia_minima_ns=S // 2,
        rebaixamento_minimo_trades=3,
        rebaixamento_minimo_ns=S // 2,
    )


def test_histerese_promocao_exige_sustentacao():
    motor, vp = _motor_com_histerese()
    _encher_perfil(vp)
    ts = 0
    estagios = []
    for _ in range(3):
        estagios.append(motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY)).estagio)
        ts += 300_000_000
    # 1º e 2º trades já satisfazem a condição, mas não sustentaram ainda
    assert estagios[0] is EstagioSinal.NENHUM
    assert estagios[1] is EstagioSinal.NENHUM
    assert estagios[2] is EstagioSinal.CONFIRMADO


def test_histerese_um_unico_trade_contrario_nao_derruba_confirmado():
    """A R2 mediu: `70 BUY + 30 SELL` -> CONFIRMADO; +1 trade SELL -> NENHUM.
    Um trade isolado não pode desfazer a confluência."""
    motor, vp = _motor_com_histerese()
    _encher_perfil(vp)
    ts = 0
    for _ in range(4):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 300_000_000
    assert motor.estagio_atual is EstagioSinal.CONFIRMADO

    # três trades vendedores que derrubam a dominância abaixo de 0.70
    estagios = []
    for _ in range(3):
        s = motor.ao_trade(_trade(ts, 5000, 200, AgressorSide.SELL))
        estagios.append(s.estagio)
        assert s.evidencia["estagio_bruto"] == EstagioSinal.NENHUM.value
        ts += 300_000_000
    assert estagios[0] is EstagioSinal.CONFIRMADO   # 1 trade não derruba
    assert estagios[1] is EstagioSinal.CONFIRMADO   # 2 também não
    assert estagios[2] is EstagioSinal.NENHUM       # sustentou a falha: cai


def test_histerese_falha_intermitente_nao_derruba():
    """Condição falhando e voltando não acumula: o contador de sustentação
    reinicia a cada troca de candidato."""
    motor, vp = _motor_com_histerese()
    _encher_perfil(vp)
    ts = 0
    for _ in range(4):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 300_000_000
    assert motor.estagio_atual is EstagioSinal.CONFIRMADO
    for _ in range(6):
        # falha (preço sai da região de interesse) ...
        s = motor.ao_trade(_trade(ts, 9000, 100, AgressorSide.BUY))
        assert s.evidencia["estagio_bruto"] == EstagioSinal.DIRECAO_CONFIRMADA.value
        ts += 300_000_000
        # ... e volta antes de completar a sustentação da falha
        s = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        assert s.evidencia["estagio_bruto"] == EstagioSinal.CONFIRMADO.value
        ts += 300_000_000
        assert motor.estagio_atual is EstagioSinal.CONFIRMADO


# ---------------------------------------------------------------------------
# DEFEITO 4 — faixas de convicção
# ---------------------------------------------------------------------------


def _faixa_para(vol_buy, vol_sell):
    motor, vp = _motor()
    _encher_perfil(vp)
    motor.ao_trade(_trade(0, 5000, vol_buy, AgressorSide.BUY))
    sinal = motor.ao_trade(_trade(1, 5000, vol_sell, AgressorSide.SELL))
    return sinal, motor


def test_faixa_50_e_lateral():
    sinal, motor = _faixa_para(100, 100)
    assert sinal.evidencia["dominancia"] == 0.50
    assert motor.faixa_atual is FaixaConviccao.LATERAL
    assert sinal.estagio is EstagioSinal.NENHUM


def test_faixa_65_e_pre_direcional():
    sinal, motor = _faixa_para(65, 35)
    assert sinal.evidencia["dominancia"] == 0.65
    assert motor.faixa_atual is FaixaConviccao.PRE_DIRECIONAL
    assert sinal.estagio is EstagioSinal.NENHUM


def test_faixa_entre_65_e_70_e_zona_cinza_sem_rotulo_na_fonte():
    sinal, motor = _faixa_para(68, 32)
    assert motor.faixa_atual is FaixaConviccao.ZONA_CINZA
    assert sinal.estagio is EstagioSinal.NENHUM


def test_faixa_70_exata_ja_e_direcional():
    sinal, motor = _faixa_para(70, 30)
    assert sinal.evidencia["dominancia"] == 0.70
    assert motor.faixa_atual is FaixaConviccao.DIRECIONAL
    assert sinal.estagio is not EstagioSinal.NENHUM


def test_faixa_79_ainda_e_direcional_e_nao_maxima():
    _, motor = _faixa_para(79, 21)
    assert motor.faixa_atual is FaixaConviccao.DIRECIONAL


def test_faixa_80_exata_e_maxima_conviccao():
    """Limiar INCLUSIVO: a fonte diz "acima de 80%, 85, não tem nem o que
    pensar". 0.80 cravado já é máxima convicção."""
    sinal, motor = _faixa_para(80, 20)
    assert sinal.evidencia["dominancia"] == 0.80
    assert motor.faixa_atual is FaixaConviccao.MAXIMA_CONVICCAO
    assert sinal.evidencia["faixa"] == "MAXIMA_CONVICCAO"


def test_faixas_sao_parametrizaveis():
    motor, vp = _motor(faixa_maxima_conviccao_desde=0.85, dominancia_minima=0.75)
    _encher_perfil(vp)
    motor.ao_trade(_trade(0, 5000, 80, AgressorSide.BUY))
    motor.ao_trade(_trade(1, 5000, 20, AgressorSide.SELL))
    assert motor.faixa_atual is FaixaConviccao.DIRECIONAL  # 0.80 < 0.85


# ---------------------------------------------------------------------------
# DEFEITO 1 — janelas incrementais e cache de VAL/VAH
# ---------------------------------------------------------------------------


def test_dominancia_expira_por_tempo():
    """Os contadores incrementais precisam DEVOLVER o volume ao expirar —
    senão a janela vira acumulador do dia inteiro."""
    motor, vp = _motor(janela_dominancia_ns=1 * S)
    _encher_perfil(vp)
    ts = 0
    for _ in range(10):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 100_000_000
    # 5s depois: todos os compradores já saíram da janela de 1s
    sinal = motor.ao_trade(_trade(5 * S, 5000, 100, AgressorSide.SELL))
    assert sinal.evidencia["dominancia"] == 1.0
    assert sinal.evidencia["direcao_dominante"] == Side.SELL.value
    assert sinal.evidencia["magnitude"] == 100


def test_micro_expira_por_tempo():
    motor, vp = _motor(janela_dominancia_ns=60 * S, janela_micro_ns=2 * S)
    _encher_perfil(vp)
    ts = 0
    for _ in range(10):
        motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 100_000_000
    # 30s depois a janela micro está vazia: um vendedor solitário não pode
    # deixar o delta da micro positivo por herança dos compradores antigos
    sinal = motor.ao_trade(_trade(30 * S, 5000, 10, AgressorSide.SELL))
    assert sinal.evidencia["micro_virou"] is False
    assert sinal.evidencia["delta_micro_primeira_metade"] == 0
    assert sinal.evidencia["delta_micro_segunda_metade"] == -10


def test_cache_da_regiao_e_reusado_e_depois_invalidado_por_contagem():
    motor, vp = _motor(cache_regiao_max_trades=3, cache_regiao_max_ns=10 ** 15)
    _encher_perfil(vp, preco=4000)  # região longe do preço negociado
    ts = 0
    sinal = None
    for _ in range(4):
        sinal = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 1000
    assert sinal.estagio is EstagioSinal.DIRECAO_CONFIRMADA

    # o perfil muda: a value area passa a ser 5000
    for i in range(40):
        vp.registrar_trade(_trade(i, 5000, 100, AgressorSide.BUY))
    assert vp.value_area() == (5000, 5000)

    # o trade seguinte ainda enxerga a região CACHEADA (o cache é real)
    sinal = motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
    ts += 1000
    assert sinal.evidencia["na_regiao"] is False

    # e o cache é invalidado por contagem: em poucos trades a região nova entra
    vistos = []
    for _ in range(6):
        vistos.append(motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY)))
        ts += 1000
    assert any(s.evidencia["na_regiao"] is True for s in vistos)


def test_cache_da_regiao_e_invalidado_por_tempo():
    motor, vp = _motor(cache_regiao_max_trades=10 ** 9, cache_regiao_max_ns=1 * S)
    _encher_perfil(vp, preco=4000)
    ts = 0
    motor.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
    for i in range(40):
        vp.registrar_trade(_trade(i, 5000, 100, AgressorSide.BUY))
    # sem avançar o relógio o suficiente: cache mantido
    sinal = motor.ao_trade(_trade(ts + 1000, 5000, 100, AgressorSide.BUY))
    assert sinal.evidencia["na_regiao"] is False
    # 2s depois: recalcula
    sinal = motor.ao_trade(_trade(ts + 2 * S, 5000, 100, AgressorSide.BUY))
    assert sinal.evidencia["na_regiao"] is True


def test_regiao_vazia_nao_e_cacheada():
    """Perfil vazio devolve `None`; se isso fosse cacheado, um perfil que
    acabou de ser alimentado ficaria invisível por centenas de trades."""
    motor, vp = _motor(cache_regiao_max_trades=10 ** 9, cache_regiao_max_ns=10 ** 15)
    sinal = motor.ao_trade(_trade(0, 5000, 100, AgressorSide.BUY))
    assert sinal.evidencia["na_regiao"] is False
    _encher_perfil(vp)
    sinal = motor.ao_trade(_trade(1000, 5000, 100, AgressorSide.BUY))
    assert sinal.evidencia["na_regiao"] is True


# ---------------------------------------------------------------------------
# Volume não atribuído (`AgressorSide.UNKNOWN`) e janela vazia
# ---------------------------------------------------------------------------


def test_volume_desconhecido_aparece_na_evidencia_e_nao_vira_dominancia():
    motor, vp = _motor()
    _encher_perfil(vp)
    motor.ao_trade(_trade(0, 5000, 100, AgressorSide.BUY))
    sinal = motor.ao_trade(_trade(1000, 5000, 900, AgressorSide.UNKNOWN))
    assert sinal.evidencia["volume_nao_atribuido"] == 900
    assert sinal.evidencia["dominancia"] == 1.0  # UNKNOWN não conta em lado nenhum


def test_so_volume_desconhecido_nao_produz_direcao():
    motor, vp = _motor()
    _encher_perfil(vp)
    sinal = motor.ao_trade(_trade(0, 5000, 100, AgressorSide.UNKNOWN))
    assert sinal.evidencia["dominancia"] == 0.5
    assert sinal.evidencia["volume_nao_atribuido"] == 100
    assert sinal.estagio is EstagioSinal.NENHUM
    assert sinal.direcao is None


# ---------------------------------------------------------------------------
# Defaults de fábrica (nenhum teste os exercia — N18 e N22 da crítica R2)
# ---------------------------------------------------------------------------


def test_default_de_fabrica_valores():
    cfg = ConfigMotorSinais()
    assert cfg.dominancia_minima == 0.70
    assert cfg.faixa_lateral_ate == 0.50
    assert cfg.faixa_pre_direcional_ate == 0.65
    assert cfg.faixa_maxima_conviccao_desde == 0.80
    assert cfg.janela_dominancia_ns == 5 * 60 * S
    # a "micro" precisa ser MICRO: menor que a janela de dominância
    assert cfg.janela_micro_ns == 15 * S
    assert cfg.janela_micro_ns < cfg.janela_dominancia_ns
    # as duas travas do caso WINFUT vêm ARMADAS de fábrica
    assert cfg.magnitude_relativa_minima > 0.0
    assert cfg.persistencia_minima_trades >= 2
    assert cfg.persistencia_minima_ns > 0
    assert cfg.rebaixamento_minimo_trades >= 2
    assert cfg.rebaixamento_minimo_ns > 0


def test_default_de_fabrica_barra_dominancia_da_zona_cinza():
    """Com a config de fábrica, 0.68 de dominância NÃO opera."""
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp)  # sem config: fábrica
    ts = 0
    sinal = None
    estagios = []
    dominancias = []
    for i in range(200):
        # 17 compradores a cada 25, distribuídos (não em bloco): a razão
        # converge para 0.68 — dentro da ZONA_CINZA, acima do "pré-direcional"
        # da fonte (0.65) e abaixo do "direcional" (0.70).
        lado = AgressorSide.BUY if (i * 17) % 25 < 17 else AgressorSide.SELL
        sinal = motor.ao_trade(_trade(ts, 5000, 4, lado))
        ts += 100_000_000
        estagios.append(sinal.estagio)
        dominancias.append(sinal.evidencia["dominancia"])
    assert abs(sinal.evidencia["dominancia"] - 0.68) < 0.02
    assert max(dominancias[50:]) < 0.70
    assert set(estagios[50:]) == {EstagioSinal.NENHUM}
    assert motor.faixa_atual is FaixaConviccao.ZONA_CINZA


def test_default_de_fabrica_confirma_movimento_direcional():
    """Contraprova do teste acima: com a MESMA config de fábrica, um fluxo
    90% comprador na região chega a CONFIRMADO."""
    vp = VolumeProfile()
    _encher_perfil(vp)
    motor = MotorSinais("WDOV26", vp)
    ts = 0
    sinal = None
    for i in range(100):
        lado = AgressorSide.SELL if i % 10 == 0 else AgressorSide.BUY
        sinal = motor.ao_trade(_trade(ts, 5000, 10, lado))
        ts += 100_000_000
    assert sinal.estagio is EstagioSinal.CONFIRMADO
    assert sinal.direcao is Side.BUY
