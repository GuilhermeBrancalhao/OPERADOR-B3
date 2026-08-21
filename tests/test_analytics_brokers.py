from __future__ import annotations

from fluxopro.analytics.brokers import ConfigRankingCorretoras, RankingCorretoras
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(
    ts_ns: int,
    price: int,
    qty: int,
    buyer_broker: str,
    seller_broker: str,
    trade_id: str,
) -> Trade:
    return Trade(
        timestamp_ns=ts_ns,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=AgressorSide.BUY,
        trade_id=trade_id,
        buyer_broker=buyer_broker,
        seller_broker=seller_broker,
    )


def test_agregacao_por_corretora_volume_saldo_e_preco_medio() -> None:
    barramento = Barramento()
    ranking = RankingCorretoras(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))
    barramento.publicar(_trade(1, 102, 5, "XP", "ITAU", "T2"))
    barramento.publicar(_trade(2, 101, 8, "BTG", "XP", "T3"))

    xp = ranking.estatistica("XP")
    assert xp is not None
    assert xp.volume_compra == 15  # 10 (T1) + 5 (T2)
    assert xp.volume_venda == 8  # T3
    assert xp.volume_total == 23
    assert xp.saldo_liquido == 7
    assert xp.n_negocios_compra == 2
    assert xp.n_negocios_venda == 1
    assert xp.n_negocios == 3
    # (100*10 + 102*5) / 15 = 1510/15
    assert xp.preco_medio_compra == 1510 / 15
    assert xp.preco_medio_venda == 101.0
    assert xp.preco_medio == (1510 + 808) / 23

    btg = ranking.estatistica("BTG")
    assert btg is not None
    assert btg.volume_venda == 10  # T1
    assert btg.volume_compra == 8  # T3
    assert btg.saldo_liquido == -2

    itau = ranking.estatistica("ITAU")
    assert itau is not None
    assert itau.volume_venda == 5
    assert itau.saldo_liquido == -5


def test_ranking_por_volume_e_por_saldo() -> None:
    barramento = Barramento()
    ranking = RankingCorretoras(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))
    barramento.publicar(_trade(1, 102, 5, "XP", "ITAU", "T2"))
    barramento.publicar(_trade(2, 101, 8, "BTG", "XP", "T3"))

    por_volume = [nome for nome, _ in ranking.ranking_por_volume()]
    assert por_volume == ["XP", "BTG", "ITAU"]  # 23, 18, 5

    por_saldo = [nome for nome, _ in ranking.ranking_por_saldo()]
    assert por_saldo == ["XP", "BTG", "ITAU"]  # +7, -2, -5

    top1 = ranking.ranking_por_volume(top_n=1)
    assert [nome for nome, _ in top1] == ["XP"]


def test_janela_de_tempo_expira_negocios_antigos() -> None:
    barramento = Barramento()
    config = ConfigRankingCorretoras(janela_ns=10)
    ranking = RankingCorretoras(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))
    # 15 - 0 = 15 > janela_ns(10) -> T1 expira ao processar este trade
    barramento.publicar(_trade(15, 100, 5, "XP", "BTG", "T2"))

    xp = ranking.estatistica("XP")
    assert xp is not None
    assert xp.volume_compra == 5
