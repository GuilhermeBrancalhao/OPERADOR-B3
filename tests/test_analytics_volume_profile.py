from __future__ import annotations

from fluxopro.analytics.volume_profile import ConfigVolumeProfile, VolumeProfile
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(price: int, qty: int, agressor: AgressorSide, trade_id: str) -> Trade:
    return Trade(
        timestamp_ns=0,
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
