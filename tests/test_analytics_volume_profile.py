from __future__ import annotations

from fluxopro.analytics.volume_profile import (
    ConfigVolumeProfile,
    VolumeProfile,
    VolumeProfilePorPeriodo,
)
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(
    price: int, qty: int, agressor: AgressorSide, trade_id: str, ts_ns: int = 0
) -> Trade:
    return Trade(
        timestamp_ns=ts_ns,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=agressor,
        trade_id=trade_id,
    )


def _perfil_exemplo() -> VolumeProfile:
    # niveis: 99(vend3) 100(comp10,vend2=12) 101(comp5,vend5=10) 102(comp20=20) 103(comp1=1)
    trades = [
        _trade(99, 3, AgressorSide.SELL, "T1"),
        _trade(100, 10, AgressorSide.BUY, "T2"),
        _trade(100, 2, AgressorSide.SELL, "T3"),
        _trade(101, 5, AgressorSide.BUY, "T4"),
        _trade(101, 5, AgressorSide.SELL, "T5"),
        _trade(102, 20, AgressorSide.BUY, "T6"),
        _trade(103, 1, AgressorSide.BUY, "T7"),
    ]
    return VolumeProfile.de_trades(trades)


def test_volume_total_e_niveis_separados_por_agressor() -> None:
    perfil = _perfil_exemplo()
    assert perfil.volume_total == 46
    nivel_100 = perfil.nivel(100)
    assert nivel_100 is not None
    assert nivel_100.volume_comprador == 10
    assert nivel_100.volume_vendedor == 2
    assert nivel_100.delta == 8


def test_poc_e_o_nivel_de_maior_volume() -> None:
    perfil = _perfil_exemplo()
    assert perfil.poc == 102


def test_value_area_70_por_cento_calculada_a_mao() -> None:
    perfil = _perfil_exemplo()
    # alvo = 0.7 * 46 = 32.2
    # POC=102 (20) -> +101(10)=30 -> +100(12)=42 >= 32.2 -> VAL=100, VAH=102
    assert perfil.value_area() == (100, 102)
    assert perfil.val() == 100
    assert perfil.vah() == 102


def test_hvn_e_lvn_por_multiplo_da_media() -> None:
    perfil = _perfil_exemplo()
    # media = 46/5 = 9.2 ; hvn (>=1.5*9.2=13.8): so 102(20) ; lvn (<=0.5*9.2=4.6): 99(3),103(1)
    assert perfil.hvn() == [102]
    assert perfil.lvn() == [99, 103]


def test_hvn_lvn_limiares_configuraveis() -> None:
    perfil = _perfil_exemplo()
    config_permissivo = ConfigVolumeProfile(hvn_multiplo_media=1.0, lvn_multiplo_media=1.0)
    perfil2 = VolumeProfile(config=config_permissivo)
    for preco, nivel in perfil.niveis_ordenados():
        for _ in range(nivel.volume_comprador):
            perfil2.registrar_trade(_trade(preco, 1, AgressorSide.BUY, "x"))
        for _ in range(nivel.volume_vendedor):
            perfil2.registrar_trade(_trade(preco, 1, AgressorSide.SELL, "y"))
    # media = 9.2 ; com multiplo 1.0 tanto 100 quanto 101 (>=9.2) viram HVN,
    # e tanto 99 quanto 103 (<=9.2) continuam LVN
    assert 100 in perfil2.hvn()
    assert 101 in perfil2.hvn()
    assert perfil2.lvn() == [99, 103]


def test_perfil_vazio() -> None:
    perfil = VolumeProfile()
    assert perfil.poc is None
    assert perfil.value_area() is None
    assert perfil.volume_total == 0


def test_volume_total_inclui_agressor_desconhecido() -> None:
    # leilao/RLP: agressor desconhecido - some do delta/lado, mas nao pode
    # desaparecer do volume total do nivel nem do perfil
    trades = [
        _trade(100, 5, AgressorSide.BUY, "T1"),
        _trade(100, 3, AgressorSide.SELL, "T2"),
        _trade(100, 7, AgressorSide.UNKNOWN, "T3"),
    ]
    perfil = VolumeProfile.de_trades(trades)

    nivel = perfil.nivel(100)
    assert nivel is not None
    assert nivel.volume_comprador == 5
    assert nivel.volume_vendedor == 3
    assert nivel.volume_nao_atribuido == 7
    assert nivel.volume_total == 15

    assert perfil.volume_comprador == 5
    assert perfil.volume_vendedor == 3
    assert perfil.volume_nao_atribuido == 7
    assert perfil.volume_total == 15
    # invariante: nada conta no total sem cair em algum dos tres baldes
    assert perfil.volume_total == (
        perfil.volume_comprador + perfil.volume_vendedor + perfil.volume_nao_atribuido
    )


def test_hvn_no_limiar_exato_nao_fica_de_fora() -> None:
    # 5 niveis: 100(15) 101(10) 102(10) 103(10) 104(5) -> total=50, media=10
    # hvn_multiplo_media padrao=1.5 -> limiar=15 ; nivel 100 tem volume
    # EXATAMENTE igual ao limiar (fronteira, nao "acima" dele)
    trades = [
        _trade(100, 15, AgressorSide.BUY, "T1"),
        _trade(101, 10, AgressorSide.BUY, "T2"),
        _trade(102, 10, AgressorSide.BUY, "T3"),
        _trade(103, 10, AgressorSide.BUY, "T4"),
        _trade(104, 5, AgressorSide.BUY, "T5"),
    ]
    perfil = VolumeProfile.de_trades(trades)
    # se o limiar fosse checado com ">" em vez de ">=", o nivel 100 (no
    # limiar exato) ficaria de fora e hvn() voltaria vazio
    assert perfil.hvn() == [100]


def test_nova_sessao_zera_periodo_atual_preserva_periodos_fechados() -> None:
    barramento = Barramento()
    perfil_periodo = VolumeProfilePorPeriodo(barramento, symbol="WDOFUT", period_ns=100)

    barramento.publicar(_trade(100, 5, AgressorSide.BUY, "T1", ts_ns=0))
    # cruza a fronteira do periodo (100ns) -> fecha o periodo anterior
    barramento.publicar(_trade(200, 3, AgressorSide.BUY, "T2", ts_ns=100))
    assert len(perfil_periodo.periodos_fechados) == 1
    fechados_antes = perfil_periodo.periodos_fechados
    assert perfil_periodo.periodo_atual is not None

    perfil_periodo.nova_sessao()

    assert perfil_periodo.periodo_atual is None
    # historico de periodos fechados sobrevive a virada
    assert perfil_periodo.periodos_fechados == fechados_antes

    # a sessao nova nao herda nada da anterior
    barramento.publicar(_trade(300, 1, AgressorSide.BUY, "T3", ts_ns=150))
    assert perfil_periodo.periodo_atual is not None
    assert perfil_periodo.periodo_atual.volume_total == 1
