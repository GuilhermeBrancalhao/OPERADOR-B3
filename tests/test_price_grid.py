from __future__ import annotations

import pytest

from fluxopro.core.eventos import WDO_GRID, WIN_GRID, PriceGrid


def test_wdo_roundtrip_exato() -> None:
    ticks = WDO_GRID.to_ticks(5000.5)
    assert ticks == 10001
    assert WDO_GRID.to_price(ticks) == 5000.5


def test_win_roundtrip_exato() -> None:
    ticks = WIN_GRID.to_ticks(130000.0)
    assert ticks == 26000
    assert WIN_GRID.to_price(ticks) == 130000.0


def test_precos_negativos_e_zero() -> None:
    grid = PriceGrid(tick_size=0.25, decimals=2)
    assert grid.to_ticks(0.0) == 0
    assert grid.to_ticks(-1.25) == -5
    assert grid.to_price(-5) == -1.25


def test_preco_desalinhado_levanta_erro() -> None:
    with pytest.raises(ValueError):
        WDO_GRID.to_ticks(5000.3)


def test_muitos_precos_wdo_fazem_roundtrip_exato() -> None:
    for i in range(-200, 200):
        preco = 5000.0 + i * 0.5
        assert WDO_GRID.to_price(WDO_GRID.to_ticks(preco)) == preco
