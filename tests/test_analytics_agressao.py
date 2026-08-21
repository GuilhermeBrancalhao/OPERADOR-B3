from __future__ import annotations

from fluxopro.analytics.agressao import ConfigAgressao, MedidorAgressao
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


def _trade(ts_ns: int, price: int, qty: int, agressor: AgressorSide, trade_id: str) -> Trade:
    return Trade(
        timestamp_ns=ts_ns,
        symbol="WDOFUT",
        price=price,
        qty=qty,
        side_agressor=agressor,
        trade_id=trade_id,
    )


def test_saldo_taxa_e_velocidade_sem_expiracao() -> None:
    barramento = Barramento()
    config = ConfigAgressao(janela_ns=None, janela_n_trades=None)
    medidor = MedidorAgressao(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1_000_000_000, 100, 4, AgressorSide.SELL, "T2"))
    barramento.publicar(_trade(2_000_000_000, 100, 6, AgressorSide.BUY, "T3"))

    assert medidor.saldo_agressao == (10 + 6) - 4
    assert medidor.taxa_compra == 16 / 20
    assert medidor.taxa_venda == 4 / 20
    # 3 trades em 2s -> 1.5 trades/s ; 20 contratos em 2s -> 10.0 contratos/s
    assert medidor.velocidade_trades_por_segundo() == 1.5
    assert medidor.velocidade_contratos_por_segundo() == 10.0


def test_janela_por_numero_de_trades_expira_o_mais_antigo() -> None:
    barramento = Barramento()
    config = ConfigAgressao(janela_ns=None, janela_n_trades=2)
    medidor = MedidorAgressao(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1_000_000_000, 100, 4, AgressorSide.SELL, "T2"))
    # este 3o trade expulsa o T1 (BUY 10) da janela de tamanho 2
    barramento.publicar(_trade(2_000_000_000, 100, 6, AgressorSide.BUY, "T3"))

    assert medidor.saldo_agressao == 6 - 4


def test_janela_por_tempo_expira_trades_antigos() -> None:
    barramento = Barramento()
    config = ConfigAgressao(janela_ns=10, janela_n_trades=None)
    medidor = MedidorAgressao(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    # 15 - 0 = 15 > janela_ns(10) -> T1 expira ao processar este trade
    barramento.publicar(_trade(15, 100, 5, AgressorSide.BUY, "T2"))

    assert medidor.saldo_agressao == 5


def test_percentil_e_clip_grande_no_limiar_exato() -> None:
    barramento = Barramento()
    # reservatorio grande o bastante para caber todos os trades sem amostragem
    config = ConfigAgressao(tamanho_reservatorio=10, percentil_clip_grande=0.95)
    medidor = MedidorAgressao(barramento, symbol="WDOFUT", config=config)

    for i, qty in enumerate([1, 2, 3, 4, 5]):
        barramento.publicar(_trade(i, 100, qty, AgressorSide.BUY, f"T{i}"))

    # dados ordenados [1,2,3,4,5] ; posicao = 0.95*(5-1) = 3.8
    # indice_baixo=3(valor4) indice_alto=4(valor5) fracao=0.8
    # percentil = 4 + (5-4)*0.8 = 4.8
    assert medidor.limiar_clip_grande() == 4.8
    assert medidor.is_clip_grande(5) is True
    assert medidor.is_clip_grande(4) is False


def test_sem_trades_nao_ha_clip_grande() -> None:
    barramento = Barramento()
    medidor = MedidorAgressao(barramento, symbol="WDOFUT")
    assert medidor.limiar_clip_grande() is None
    assert medidor.is_clip_grande(100) is False
