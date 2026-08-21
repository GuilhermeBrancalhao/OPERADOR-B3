from __future__ import annotations

from fluxopro.analytics.footprint import ConfigFootprint, Footprint
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(price: int, qty: int, agressor: AgressorSide, ts: int, trade_id: str) -> Trade:
    return Trade(
        timestamp_ns=ts,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=agressor,
        trade_id=trade_id,
    )


def test_imbalance_diagonal_no_limiar_exato_e_abaixo_dele() -> None:
    fp = Footprint()
    # limiar padrao = 3.0
    # comp(100)/vend(101) = 6/2 = 3.0 -> imbalance de compra (no limiar exato)
    fp.registrar_trade(_trade(100, 6, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(101, 2, AgressorSide.SELL, 1, "T2"))
    # comp(102)/vend(103) = 5/2 = 2.5 -> abaixo do limiar, NAO deve marcar
    fp.registrar_trade(_trade(102, 5, AgressorSide.BUY, 2, "T3"))
    fp.registrar_trade(_trade(103, 2, AgressorSide.SELL, 3, "T4"))
    # vend(200)/comp(199) = 9/3 = 3.0 -> imbalance de venda (no limiar exato)
    fp.registrar_trade(_trade(199, 3, AgressorSide.BUY, 4, "T5"))
    fp.registrar_trade(_trade(200, 9, AgressorSide.SELL, 5, "T6"))
    # vend(202)/comp(201) = 4/2 = 2.0 -> abaixo do limiar, NAO deve marcar
    fp.registrar_trade(_trade(201, 2, AgressorSide.BUY, 6, "T7"))
    fp.registrar_trade(_trade(202, 4, AgressorSide.SELL, 7, "T8"))

    assert fp.niveis_imbalance_compra() == [100]
    assert fp.niveis_imbalance_venda() == [200]


def test_delta_divergente_preco_sobe_delta_negativo() -> None:
    fp = Footprint()
    fp.registrar_trade(_trade(100, 6, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(101, 2, AgressorSide.SELL, 1, "T2"))
    fp.registrar_trade(_trade(102, 5, AgressorSide.BUY, 2, "T3"))
    fp.registrar_trade(_trade(103, 2, AgressorSide.SELL, 3, "T4"))
    fp.registrar_trade(_trade(199, 3, AgressorSide.BUY, 4, "T5"))
    fp.registrar_trade(_trade(200, 9, AgressorSide.SELL, 5, "T6"))
    fp.registrar_trade(_trade(201, 2, AgressorSide.BUY, 6, "T7"))
    fp.registrar_trade(_trade(202, 4, AgressorSide.SELL, 7, "T8"))

    # abertura=100 fechamento=202 (subiu); delta total = (6+5+3+2) - (2+2+9+4) = 16-17 = -1
    assert fp.preco_abertura == 100
    assert fp.preco_fechamento == 202
    assert fp.delta == -1
    assert fp.delta_divergente() is True


def test_nao_diverge_quando_preco_e_delta_concordam() -> None:
    fp = Footprint()
    fp.registrar_trade(_trade(100, 10, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(101, 5, AgressorSide.BUY, 1, "T2"))
    # fechamento(101) > abertura(100) e delta = +15 > 0 -> concorda, sem divergencia
    assert fp.delta_divergente() is False


def test_absorcao_no_topo_no_limiar_exato() -> None:
    fp = Footprint(config=ConfigFootprint(multiplo_absorcao=2.0, reversao_ticks_absorcao=1))
    fp.registrar_trade(_trade(100, 5, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(101, 3, AgressorSide.BUY, 1, "T2"))
    fp.registrar_trade(_trade(102, 20, AgressorSide.SELL, 2, "T3"))
    fp.registrar_trade(_trade(101, 2, AgressorSide.SELL, 3, "T4"))
    # niveis: 100(5) 101(3+2=5) 102(20) ; volume_total=30, media=30/3=10
    # limiar = 2.0*10 = 20 ; volume no topo(102) = 20 >= 20 -> volume alto
    # reversao = 102 - 101(fechamento) = 1 >= 1 -> confirmada
    assert fp.preco_maximo == 102
    assert fp.preco_fechamento == 101
    assert fp.absorcao_topo() is True
    assert fp.absorcao_fundo() is False


def test_absorcao_no_fundo_no_limiar_exato() -> None:
    fp = Footprint(config=ConfigFootprint(multiplo_absorcao=2.0, reversao_ticks_absorcao=1))
    fp.registrar_trade(_trade(105, 5, AgressorSide.SELL, 0, "T1"))
    fp.registrar_trade(_trade(104, 3, AgressorSide.SELL, 1, "T2"))
    fp.registrar_trade(_trade(103, 20, AgressorSide.BUY, 2, "T3"))
    fp.registrar_trade(_trade(104, 2, AgressorSide.BUY, 3, "T4"))
    # niveis: 105(5) 104(3+2=5) 103(20) ; volume_total=30, media=10, limiar=20
    # volume no fundo(103)=20 >= 20 ; reversao = 104(fechamento) - 103 = 1 >= 1
    assert fp.preco_minimo == 103
    assert fp.preco_fechamento == 104
    assert fp.absorcao_fundo() is True
    assert fp.absorcao_topo() is False


def test_volume_total_inclui_agressor_desconhecido() -> None:
    fp = Footprint()
    fp.registrar_trade(_trade(100, 5, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(100, 3, AgressorSide.SELL, 1, "T2"))
    # leilao/RLP: agressor desconhecido - some do delta, nao pode sumir do total
    fp.registrar_trade(_trade(100, 7, AgressorSide.UNKNOWN, 2, "T3"))

    nivel = fp.nivel(100)
    assert nivel is not None
    assert nivel.qty_comprador == 5
    assert nivel.qty_vendedor == 3
    assert nivel.qty_nao_atribuida == 7
    assert nivel.volume_total == 15

    assert fp.volume_total == 15
    assert fp.volume_nao_atribuido == 7
    # delta ignora o nao atribuido (correto: nao ha lado pra somar)
    assert fp.delta == 5 - 3
    # invariante: nada conta no total sem cair em algum dos tres baldes
    assert fp.volume_total == (
        nivel.qty_comprador + nivel.qty_vendedor + fp.volume_nao_atribuido
    )


def test_absorcao_nao_confirma_sem_reversao_suficiente() -> None:
    fp = Footprint(config=ConfigFootprint(multiplo_absorcao=2.0, reversao_ticks_absorcao=2))
    fp.registrar_trade(_trade(100, 5, AgressorSide.BUY, 0, "T1"))
    fp.registrar_trade(_trade(101, 3, AgressorSide.BUY, 1, "T2"))
    fp.registrar_trade(_trade(102, 20, AgressorSide.SELL, 2, "T3"))
    fp.registrar_trade(_trade(101, 2, AgressorSide.SELL, 3, "T4"))
    # mesmo cenario do teste de absorcao no topo, mas agora exige reversao de 2
    # ticks; so recuou 1 tick (102->101) -> nao confirma
    assert fp.absorcao_topo() is False
