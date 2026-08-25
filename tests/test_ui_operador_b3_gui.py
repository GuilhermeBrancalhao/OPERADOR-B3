"""Contratos da superfície OPERADOR B3: causalidade, limites e texto acessível."""

from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.grafico import AgregadorCandles
from fluxopro.ui.ponte import ItemTape


def tape(ts: int, price: int, qty: int, side: int) -> ItemTape:
    return ItemTape(ts, price, qty, side)


def test_agregador_preserva_ohlc_delta_e_volume_desconhecido() -> None:
    agregador = AgregadorCandles(WDO_GRID, timeframe_ns=10)
    agregador.aplicar((
        tape(1, 100, 3, 1),
        tape(2, 98, 2, -1),
        tape(3, 101, 4, 0),
        tape(11, 99, 5, -1),
    ))
    fechadas = agregador.velas()
    assert len(fechadas) == 2
    assert fechadas[0].open == 100
    assert fechadas[0].high == 101
    assert fechadas[0].low == 98
    assert fechadas[0].close == 101
    assert fechadas[0].volume == 9
    assert fechadas[0].delta == 1
    assert fechadas[0].volume_nao_atribuido == 4


def test_agregador_rejeita_timestamp_regressivo_e_tem_teto() -> None:
    agregador = AgregadorCandles(WDO_GRID, timeframe_ns=1, MAX_CANDLES=3)
    agregador.aplicar(tuple(tape(i, 100 + i, 1, 1) for i in range(8)))
    ultimo = agregador.vela_corrente()
    agregador.aplicar((tape(0, 777, 99, -1),))
    assert agregador.vela_corrente() == ultimo
    assert len(agregador._velas) <= 3


def test_nome_publico_mantem_id_persistido_e_alias() -> None:
    from fluxopro.ui.workspace import por_nome

    sala = por_nome("OPERADOR B3")
    assert sala is not None
    assert sala.nome == "ASG-like"
    assert sala.nome_exibicao == "OPERADOR B3"
    assert por_nome("ASG-like") is sala
