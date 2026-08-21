from __future__ import annotations

from fluxopro.analytics.delta import ConfigDelta, CumulativeDelta
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import NS_POR_MINUTO
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


def test_delta_acumulado_de_sessao() -> None:
    barramento = Barramento()
    delta = CumulativeDelta(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 5, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 100, 3, AgressorSide.SELL, "T2"))
    barramento.publicar(_trade(2, 100, 7, AgressorSide.BUY, "T3"))

    assert delta.delta_sessao == 5 - 3 + 7


def test_delta_maximo_e_minimo_intra_candle_revelam_reversao() -> None:
    barramento = Barramento()
    delta = CumulativeDelta(barramento, symbol="WDOFUT")

    # caminho do delta dentro do candle: 0 -> 3 -> -2 -> 2
    barramento.publicar(_trade(0, 100, 3, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 100, 5, AgressorSide.SELL, "T2"))
    barramento.publicar(_trade(2, 100, 4, AgressorSide.BUY, "T3"))

    candle = delta.candle_atual
    assert candle is not None
    assert candle.delta == 2
    assert candle.delta_maximo == 3
    assert candle.delta_minimo == -2


def test_delta_divergente_preco_sobe_delta_acumulado_cai() -> None:
    barramento = Barramento()
    config = ConfigDelta(timeframe_ns=NS_POR_MINUTO, janela_divergencia=2)
    delta = CumulativeDelta(barramento, symbol="WDOFUT", config=config)

    # candle A: fecha 100, delta +10, cumulativo 10
    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    # candle B: fecha 105, delta -20, cumulativo -10
    barramento.publicar(_trade(NS_POR_MINUTO, 105, 20, AgressorSide.SELL, "T2"))
    # candle C: fecha 110, delta -5, cumulativo -15
    barramento.publicar(_trade(2 * NS_POR_MINUTO, 110, 5, AgressorSide.SELL, "T3"))
    # candle D (forca o fechamento de C, que entra no historico)
    barramento.publicar(_trade(3 * NS_POR_MINUTO, 115, 1, AgressorSide.BUY, "T4"))

    historico = delta.historico
    assert [c.preco_fechamento for c in historico] == [100, 105, 110]
    assert [c.delta_acumulado_no_fechamento for c in historico] == [10, -10, -15]

    # janela=2 -> compara candle B (preco 105, cum -10) com candle C (preco 110, cum -15)
    # preco subiu (+5) mas delta acumulado caiu (-5) -> divergente
    assert delta.delta_divergente() is True


def test_nao_diverge_quando_preco_e_delta_acumulado_concordam() -> None:
    barramento = Barramento()
    config = ConfigDelta(timeframe_ns=NS_POR_MINUTO, janela_divergencia=2)
    delta = CumulativeDelta(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(NS_POR_MINUTO, 105, 20, AgressorSide.BUY, "T2"))
    barramento.publicar(_trade(2 * NS_POR_MINUTO, 110, 5, AgressorSide.BUY, "T3"))
    barramento.publicar(_trade(3 * NS_POR_MINUTO, 115, 1, AgressorSide.BUY, "T4"))

    # preco e delta acumulado sobem juntos -> sem divergencia
    assert delta.delta_divergente() is False


def test_divergencia_exige_historico_minimo_da_janela() -> None:
    barramento = Barramento()
    config = ConfigDelta(timeframe_ns=NS_POR_MINUTO, janela_divergencia=5)
    delta = CumulativeDelta(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(NS_POR_MINUTO, 50, 20, AgressorSide.SELL, "T2"))

    # so 1 candle fechado, janela pede 5 -> nao ha dados suficientes
    assert delta.delta_divergente() is False


def test_volume_total_sessao_inclui_agressor_desconhecido() -> None:
    barramento = Barramento()
    delta = CumulativeDelta(barramento, symbol="WDOFUT")

    barramento.publicar(_trade(0, 100, 5, AgressorSide.BUY, "T1"))
    barramento.publicar(_trade(1, 100, 3, AgressorSide.SELL, "T2"))
    # leilao/RLP: agressor desconhecido - nao entra no delta, mas tem que
    # entrar em algum contador visivel de volume
    barramento.publicar(_trade(2, 100, 7, AgressorSide.UNKNOWN, "T3"))

    assert delta.delta_sessao == 5 - 3
    assert delta.volume_comprador_sessao == 5
    assert delta.volume_vendedor_sessao == 3
    assert delta.volume_nao_atribuido_sessao == 7
    assert delta.volume_total_sessao == 15
    # invariante: nada conta no total sem cair em algum dos tres baldes
    assert delta.volume_total_sessao == (
        delta.volume_comprador_sessao
        + delta.volume_vendedor_sessao
        + delta.volume_nao_atribuido_sessao
    )


def test_iniciar_nova_sessao_zera_delta_preserva_historico() -> None:
    barramento = Barramento()
    config = ConfigDelta(timeframe_ns=NS_POR_MINUTO)
    delta = CumulativeDelta(barramento, symbol="WDOFUT", config=config)

    barramento.publicar(_trade(0, 100, 10, AgressorSide.BUY, "T1"))
    # cruza para o proximo candle -> fecha o candle A no historico
    barramento.publicar(_trade(NS_POR_MINUTO, 105, 20, AgressorSide.SELL, "T2"))
    assert len(delta.historico) == 1
    historico_antes = delta.historico

    delta.iniciar_nova_sessao(timestamp_ns=2 * NS_POR_MINUTO)

    assert delta.delta_sessao == 0
    assert delta.volume_comprador_sessao == 0
    assert delta.volume_vendedor_sessao == 0
    assert delta.volume_nao_atribuido_sessao == 0
    assert delta.candle_atual is None
    # historico e log, nao acumulador de sessao -> sobrevive a virada
    assert delta.historico == historico_antes

    # a sessao nova nao herda nada da anterior
    barramento.publicar(_trade(2 * NS_POR_MINUTO, 200, 4, AgressorSide.BUY, "T3"))
    assert delta.delta_sessao == 4
    assert delta.candle_atual is not None
    assert delta.candle_atual.delta == 4
