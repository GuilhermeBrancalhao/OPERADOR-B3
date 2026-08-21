from __future__ import annotations

from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.microestrutura.perfil_player import PerfilPlayer

NS_POR_HORA = 3_600_000_000_000


def _trade(ts, price, qty, agressor, buyer="", seller=""):
    return Trade(
        timestamp_ns=ts, symbol="WDOV26", price=price, qty=qty,
        side_agressor=agressor, trade_id=f"t{ts}",
        buyer_broker=buyer, seller_broker=seller,
    )


def test_saldo_liquido_e_volume_total():
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 100, AgressorSide.BUY, buyer="XP", seller="BTG"))
    perfil.ao_trade(_trade(1, 5000, 40, AgressorSide.SELL, buyer="XP", seller="BTG"))

    snap_xp = perfil.snapshot("XP")
    assert snap_xp.volume_total == 140
    assert snap_xp.saldo_liquido == 140  # só comprou nos dois trades


def test_agressividade_conta_so_quando_o_broker_e_o_lado_agressor():
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 100, AgressorSide.BUY, buyer="XP", seller="BTG"))
    perfil.ao_trade(_trade(1, 5000, 100, AgressorSide.SELL, buyer="XP", seller="BTG"))

    snap_xp = perfil.snapshot("XP")
    # trade 1: XP comprou e agrediu -> agressor
    # trade 2: XP comprou mas vendedor agrediu -> passivo
    assert snap_xp.agressividade == 0.5

    snap_btg = perfil.snapshot("BTG")
    # trade 1: BTG vendeu, comprador agrediu -> passivo
    # trade 2: BTG vendeu e agrediu -> agressor
    assert snap_btg.agressividade == 0.5


def test_persistencia_conta_periodos_distintos():
    perfil = PerfilPlayer("WDOV26", janela_periodo_ns=NS_POR_HORA)
    perfil.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, buyer="XP"))
    perfil.ao_trade(_trade(NS_POR_HORA, 5000, 10, AgressorSide.BUY, buyer="XP"))
    perfil.ao_trade(_trade(2 * NS_POR_HORA, 5000, 10, AgressorSide.BUY, buyer="XP"))

    assert perfil.snapshot("XP").persistencia == 3


def test_ranking_por_volume_ordena_decrescente():
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 1000, AgressorSide.BUY, buyer="GRANDE"))
    perfil.ao_trade(_trade(1, 5000, 10, AgressorSide.BUY, buyer="PEQUENO"))

    ranking = perfil.ranking_por_volume(top_n=2)
    assert ranking[0].broker == "GRANDE"
    assert ranking[1].broker == "PEQUENO"


def test_ignora_trade_de_outro_symbol():
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(Trade(
        timestamp_ns=0, symbol="WINV26", price=100000, qty=5,
        side_agressor=AgressorSide.BUY, trade_id="t0", buyer_broker="XP",
    ))
    assert perfil.snapshot("XP") is None
