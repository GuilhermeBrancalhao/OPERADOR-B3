from fluxopro.analytics.renko import FaseRenko
from fluxopro.asg.sinal_ultra import (
    ConfigSinalUltra,
    DirecaoUltra,
    EntradaSinalUltra,
    MotorSinalUltra,
)

CONFIG_RAPIDA = ConfigSinalUltra(persistencia_minima_ns=1_000, tempo_para_desligar_ns=2_000)
CONFIG_RAPIDA_ESTRITA = ConfigSinalUltra(
    persistencia_minima_ns=1_000,
    tempo_para_desligar_ns=2_000,
    exigir_maker_como_gate=True,
)


def test_limiar_de_confianca_nao_e_inalcancavel_em_mbp_inferido():
    """MBP/inferido chega a 0,6375 no contrato do Maker; 0,75 tornava o
    portao do ULTRA impossível mesmo com os demais requisitos."""
    assert ConfigSinalUltra().confianca_maker_alta_minima == 0.60
    assert 0.60 <= 0.75 * 0.85


def _entrada(
    t_ns,
    direcao=DirecaoUltra.COMPRA,
    fase=FaseRenko.TENDENCIA,
    direcao_renko=DirecaoUltra.COMPRA,
    forca_maker=0.9,
    confianca_alta=True,
):
    return EntradaSinalUltra(
        timestamp_ns=t_ns,
        direcao_decisao_confirmada=direcao,
        fase_renko=fase,
        direcao_renko=direcao_renko,
        forca_maker=forca_maker,
        confianca_maker_alta=confianca_alta,
    )


def test_nao_liga_sem_persistencia_minima():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    snap = motor.atualizar(_entrada(0))
    assert snap.direcao is DirecaoUltra.NENHUMA
    assert snap.confluencia_no_instante is DirecaoUltra.COMPRA


def test_liga_depois_da_persistencia_minima():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0))
    snap = motor.atualizar(_entrada(1_500))
    assert snap.direcao is DirecaoUltra.COMPRA
    assert snap.ligado_desde_ns == 1_500


def test_nao_liga_se_decisao_principal_nao_confirmou():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0, direcao=DirecaoUltra.NENHUMA))
    snap = motor.atualizar(_entrada(5_000, direcao=DirecaoUltra.NENHUMA))
    assert snap.direcao is DirecaoUltra.NENHUMA


def test_liga_sem_renko_em_tendencia():
    """Renko e contexto visual, nao gate do ULTRA."""
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0, fase=FaseRenko.PERDENDO_FORCA))
    snap = motor.atualizar(_entrada(5_000, fase=FaseRenko.PERDENDO_FORCA))
    assert snap.direcao is DirecaoUltra.COMPRA


def test_liga_mesmo_com_renko_contrario():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0, direcao_renko=DirecaoUltra.VENDA))
    snap = motor.atualizar(_entrada(5_000, direcao_renko=DirecaoUltra.VENDA))
    assert snap.direcao is DirecaoUltra.COMPRA


def test_nao_liga_se_maker_fraco():
    motor = MotorSinalUltra(CONFIG_RAPIDA_ESTRITA)
    motor.atualizar(_entrada(0, forca_maker=0.2))
    snap = motor.atualizar(_entrada(5_000, forca_maker=0.2))
    assert snap.direcao is DirecaoUltra.NENHUMA


def test_nao_liga_se_maker_forte_na_direcao_errada():
    motor = MotorSinalUltra(CONFIG_RAPIDA_ESTRITA)
    motor.atualizar(_entrada(0, forca_maker=-0.9))
    snap = motor.atualizar(_entrada(5_000, forca_maker=-0.9))
    assert snap.direcao is DirecaoUltra.NENHUMA


def test_venda_e_simetrica():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9))
    snap = motor.atualizar(
        _entrada(1_500, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9)
    )
    assert snap.direcao is DirecaoUltra.VENDA


def test_flicker_de_um_trade_nao_desliga_por_histerese():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0))
    motor.atualizar(_entrada(1_500))  # liga
    # um unico instante de confluencia quebrada, bem antes do tempo_para_desligar_ns
    snap = motor.atualizar(_entrada(1_600, forca_maker=0.1))
    assert snap.direcao is DirecaoUltra.COMPRA, "nao deve desligar no primeiro trade fora de linha"


def test_desliga_apos_quebra_sustentada():
    motor = MotorSinalUltra(CONFIG_RAPIDA_ESTRITA)
    motor.atualizar(_entrada(0))
    motor.atualizar(_entrada(1_500))  # liga
    motor.atualizar(_entrada(1_600, forca_maker=0.1))  # quebra comeca aqui
    snap = motor.atualizar(_entrada(4_000, forca_maker=0.1))  # >= tempo_para_desligar_ns depois
    assert snap.direcao is DirecaoUltra.NENHUMA


def test_reversao_direta_de_direcao_exige_nova_persistencia():
    """Achado do revisor: COMPRA->VENDA sem passar por NENHUMA nao pode
    reaproveitar o cronometro do desligamento para ja satisfazer a
    persistencia minima da nova direcao."""
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0))
    motor.atualizar(_entrada(1_500))  # liga COMPRA
    motor.atualizar(_entrada(1_600, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9))
    snap_desligando = motor.atualizar(
        _entrada(3_600, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9)
    )
    assert snap_desligando.direcao is DirecaoUltra.NENHUMA
    snap_logo_depois = motor.atualizar(
        _entrada(3_601, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9)
    )
    assert snap_logo_depois.direcao is DirecaoUltra.NENHUMA, (
        "nao pode ligar VENDA imediatamente apos desligar COMPRA — precisa da propria janela de persistencia"
    )
    snap_religado = motor.atualizar(
        _entrada(4_700, direcao=DirecaoUltra.VENDA, direcao_renko=DirecaoUltra.VENDA, forca_maker=-0.9)
    )
    assert snap_religado.direcao is DirecaoUltra.VENDA


def test_relegar_apos_desligar_exige_nova_persistencia():
    motor = MotorSinalUltra(CONFIG_RAPIDA_ESTRITA)
    motor.atualizar(_entrada(0))
    motor.atualizar(_entrada(1_500))  # liga
    motor.atualizar(_entrada(1_600, forca_maker=0.1))
    motor.atualizar(_entrada(4_000, forca_maker=0.1))  # desliga
    snap_imediato = motor.atualizar(_entrada(4_050))
    assert snap_imediato.direcao is DirecaoUltra.NENHUMA, "religar exige nova janela de persistencia"
    snap_religado = motor.atualizar(_entrada(5_600))
    assert snap_religado.direcao is DirecaoUltra.COMPRA


def test_maker_fraco_e_auxiliar_no_modo_padrao():
    motor = MotorSinalUltra(CONFIG_RAPIDA)
    motor.atualizar(_entrada(0, forca_maker=0.1, confianca_alta=False))
    snap = motor.atualizar(_entrada(1_500, forca_maker=0.1, confianca_alta=False))
    assert snap.direcao is DirecaoUltra.COMPRA
