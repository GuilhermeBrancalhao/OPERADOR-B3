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


def test_comprador_e_vendedor_nao_se_confundem() -> None:
    """Mata a mutacao que troca buyer/seller: comprador entra so no lado
    compra, vendedor so no lado venda -- nunca o oposto."""
    barramento = Barramento()
    ranking = RankingCorretoras(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))

    xp = ranking.estatistica("XP")
    btg = ranking.estatistica("BTG")
    assert xp.volume_compra == 10 and xp.volume_venda == 0
    assert btg.volume_venda == 10 and btg.volume_compra == 0


def test_saldo_liquido_tem_sinal_positivo_quando_compra_mais_que_vende() -> None:
    """Mata a mutacao que inverte o sinal do saldo (compra - venda vira
    venda - compra)."""
    barramento = Barramento()
    ranking = RankingCorretoras(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 30, "XP", "BTG", "T1"))
    barramento.publicar(_trade(1, 100, 10, "BTG", "XP", "T2"))

    xp = ranking.estatistica("XP")
    # XP comprou 30 e vendeu 10 -> mais comprador -> saldo POSITIVO
    assert xp.saldo_liquido == 20
    assert xp.saldo_liquido > 0

    btg = ranking.estatistica("BTG")
    # BTG vendeu 30 e comprou 10 -> mais vendedor -> saldo NEGATIVO
    assert btg.saldo_liquido == -20
    assert btg.saldo_liquido < 0


def test_janela_expira_estritamente_maior_trade_na_borda_exata_sobrevive() -> None:
    """Mata a mutacao que troca `>` por `>=` na expiracao: um trade
    EXATAMENTE na borda da janela nao pode expirar."""
    barramento = Barramento()
    config = ConfigRankingCorretoras(janela_ns=10)
    ranking = RankingCorretoras(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))
    # 10 - 0 = 10, exatamente igual a janela_ns -> NAO expira (regra e' >, nao >=)
    barramento.publicar(_trade(10, 100, 5, "XP", "BTG", "T2"))

    xp = ranking.estatistica("XP")
    assert xp.volume_compra == 15  # T1 ainda vivo


def test_trade_de_outro_symbol_e_ignorado() -> None:
    barramento = Barramento()
    ranking = RankingCorretoras(barramento, symbol="WDOFUT")

    barramento.publicar(Trade(
        timestamp_ns=0, symbol="WINFUT", price=100000, qty=5,
        side_agressor=AgressorSide.BUY, trade_id="t0",
        buyer_broker="XP", seller_broker="BTG",
    ))
    assert ranking.estatistica("XP") is None


def test_iniciar_nova_sessao_zera_estatisticas_e_janela() -> None:
    barramento = Barramento()
    config = ConfigRankingCorretoras(janela_ns=1_000)
    ranking = RankingCorretoras(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, "XP", "BTG", "T1"))
    assert ranking.estatistica("XP") is not None

    ranking.iniciar_nova_sessao()

    assert ranking.estatistica("XP") is None
    assert ranking.ranking_por_volume() == []
    # a janela deslizante tambem foi limpa: um trade novo na sessao seguinte
    # nao deve ser expirado por um trade antigo que ja tinha sido zerado
    barramento.publicar(_trade(5_000, 100, 7, "XP", "BTG", "T2"))
    xp = ranking.estatistica("XP")
    assert xp is not None
    assert xp.volume_compra == 7
