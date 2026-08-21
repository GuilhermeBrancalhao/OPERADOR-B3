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


def test_comprador_agride_conta_como_agressor_do_comprador_nao_do_vendedor():
    """Mata X06 (comprador<->vendedor invertido como agressor): quando o
    comprador agride, e' o BUYER que ganha n_trades_agressor, e o SELLER
    que ganha n_trades_passivo -- nunca o oposto."""
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, buyer="XP", seller="BTG"))

    snap_xp = perfil.snapshot("XP")
    snap_btg = perfil.snapshot("BTG")
    # XP e' o comprador e agrediu -> 100% agressor
    assert snap_xp.agressividade == 1.0
    # BTG e' o vendedor e foi passivo -> 0% agressor
    assert snap_btg.agressividade == 0.0


def test_vendedor_agride_conta_como_agressor_do_vendedor_nao_do_comprador():
    """Espelho do teste acima: quando o vendedor agride, e' o SELLER que
    ganha n_trades_agressor. Mata a mesma classe de inversao (X06) no ramo
    contrario."""
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 10, AgressorSide.SELL, buyer="XP", seller="BTG"))

    snap_xp = perfil.snapshot("XP")
    snap_btg = perfil.snapshot("BTG")
    # XP e' o comprador mas foi passivo (vendedor agrediu)
    assert snap_xp.agressividade == 0.0
    # BTG e' o vendedor e agrediu -> 100% agressor
    assert snap_btg.agressividade == 1.0


def test_agressividade_e_agressor_sobre_agressor_mais_passivo_nao_o_inverso():
    """Mata X10 (agressividade mede o lado passivo): 3 trades onde o broker
    agride 1 vez e e' passivo 2 vezes -> agressividade = 1/3, NAO 2/3."""
    perfil = PerfilPlayer("WDOV26")
    # XP compra e agride (1x agressor)
    perfil.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, buyer="XP", seller="BTG"))
    # XP compra mas vendedor agride (passivo)
    perfil.ao_trade(_trade(1, 5000, 10, AgressorSide.SELL, buyer="XP", seller="BTG"))
    # XP compra mas vendedor agride de novo (passivo)
    perfil.ao_trade(_trade(2, 5000, 10, AgressorSide.SELL, buyer="XP", seller="BTG"))

    snap_xp = perfil.snapshot("XP")
    assert snap_xp.agressividade == 1 / 3
    # se a formula fosse invertida (passivo/total), daria 2/3 -- garantir
    # explicitamente que NAO e' esse o valor
    assert snap_xp.agressividade != 2 / 3


def test_saldo_liquido_positivo_quando_compra_mais_que_vende_e_negativo_no_inverso():
    """Confere o sinal de `saldo_liquido`: comprou mais -> positivo; vendeu
    mais -> negativo. Mata uma inversao de sinal no saldo do broker."""
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 30, AgressorSide.BUY, buyer="XP", seller="BTG"))
    perfil.ao_trade(_trade(1, 5000, 10, AgressorSide.SELL, buyer="BTG", seller="XP"))

    snap_xp = perfil.snapshot("XP")
    # XP comprou 30 e vendeu 10 -> saldo +20 (mais comprador)
    assert snap_xp.saldo_liquido == 20
    assert snap_xp.saldo_liquido > 0

    snap_btg = perfil.snapshot("BTG")
    # BTG vendeu 30 e comprou 10 -> saldo -20 (mais vendedor)
    assert snap_btg.saldo_liquido == -20
    assert snap_btg.saldo_liquido < 0


def test_perna_vendedora_tambem_conta_no_clip_e_no_volume():
    """Mata X08 (perna vendedora nao conta clip): tamanho_medio_clip e
    volume_total do vendedor precisam refletir o trade tanto quanto do
    comprador -- ambas as pernas contam um clip cada."""
    perfil = PerfilPlayer("WDOV26")
    perfil.ao_trade(_trade(0, 5000, 40, AgressorSide.BUY, buyer="XP", seller="BTG"))

    snap_btg = perfil.snapshot("BTG")
    assert snap_btg is not None
    assert snap_btg.volume_total == 40
    assert snap_btg.tamanho_medio_clip == 40.0


def test_persistencia_nao_conta_trades_e_sim_periodos_distintos():
    """Mata uma mutacao que trocasse persistencia por contagem de trades:
    3 trades no MESMO periodo contam persistencia == 1, nao 3."""
    perfil = PerfilPlayer("WDOV26", janela_periodo_ns=NS_POR_HORA)
    perfil.ao_trade(_trade(0, 5000, 10, AgressorSide.BUY, buyer="XP"))
    perfil.ao_trade(_trade(1, 5000, 10, AgressorSide.BUY, buyer="XP"))
    perfil.ao_trade(_trade(2, 5000, 10, AgressorSide.BUY, buyer="XP"))

    assert perfil.snapshot("XP").persistencia == 1
    assert perfil.snapshot("XP").persistencia != 3


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
