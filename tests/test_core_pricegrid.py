"""Testes de `PriceGrid.to_ticks`/`to_price` — mata a mutação M06
(`round()` -> `int()` em `to_ticks`), viva desde a R1.

`int()` trunca em direção a zero; `round()` arredonda para o inteiro mais
próximo. A divisão `price / tick_size` quase sempre carrega um erro de
ponto flutuante minúsculo (por isso a tolerância de 1e-6 existe), e esse
erro pode empurrar a razão para o lado "de baixo" de um inteiro (positivo)
ou "de cima" de um inteiro negativo — exatamente onde truncar e arredondar
divergem. Os casos abaixo são divisões REAIS (não epsilons fabricados) que
produzem esse erro em Python: `10000.4 / 0.2` e `0.3 / 0.1`.
"""

from __future__ import annotations

import pytest

from fluxopro.core.eventos import PriceGrid, WDO_GRID, WIN_GRID


def test_to_ticks_alinhado_simples():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    assert grid.to_ticks(5000.5) == 10001
    assert grid.to_ticks(5000.0) == 10000


def test_to_ticks_erro_flutuante_positivo_deve_arredondar_nao_truncar():
    """10000.4 / 0.2 == 50001.99999999999 em Python (erro de ~7e-12).
    round() -> 50002 (correto). int() trunca para 50001 (errado — e o
    proprio erro, ~1.0, estoura a tolerancia de 1e-6, entao a mutacao
    faz um preco legitimamente alinhado ser REJEITADO por engano)."""
    grid = PriceGrid(tick_size=0.2, decimals=1)
    razao = 10000.4 / 0.2
    assert razao != 50002  # confirma que o erro de ponto flutuante existe
    assert grid.to_ticks(10000.4) == 50002


def test_to_ticks_erro_flutuante_negativo_deve_arredondar_nao_truncar():
    """Espelho do caso acima para preco negativo: -10000.4 / 0.2 ==
    -50001.99999999999. round() -> -50002 (correto). int() trunca em
    direcao a zero -> -50001 (errado)."""
    grid = PriceGrid(tick_size=0.2, decimals=1)
    assert grid.to_ticks(-10000.4) == -50002


def test_to_ticks_erro_flutuante_pequeno_positivo():
    """0.3 / 0.1 == 2.9999999999999996 em Python. round() -> 3 (correto,
    diff ~4e-16). int() trunca -> 2 (errado)."""
    grid = PriceGrid(tick_size=0.1, decimals=1)
    assert grid.to_ticks(0.3) == 3


def test_to_ticks_erro_flutuante_pequeno_negativo():
    grid = PriceGrid(tick_size=0.1, decimals=1)
    assert grid.to_ticks(-0.3) == -3


def test_to_ticks_negativo_alinhado():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    assert grid.to_ticks(-5000.5) == -10001
    assert grid.to_ticks(-5000.0) == -10000


def test_to_ticks_meio_tick_e_rejeitado():
    """Preco exatamente no meio de dois ticks nao esta na grade — tem que
    ser rejeitado (nao existe tick 'certo' para arredondar), tanto com
    round() quanto com int(); prova que a rejeicao por desalinhamento real
    nao e o mesmo defeito que a truncagem por erro de ponto flutuante."""
    grid = PriceGrid(tick_size=0.1, decimals=1)
    with pytest.raises(ValueError):
        grid.to_ticks(100.05)


def test_to_ticks_dentro_da_tolerancia_passa():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    # 10000 + 9e-7 ticks -> diff de 9e-7, dentro da tolerancia de 1e-6
    preco = (10000 + 9e-7) * 0.5
    assert grid.to_ticks(preco) == 10000


def test_to_ticks_fora_da_tolerancia_e_rejeitado():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    # 10000 + 2e-6 ticks -> diff de 2e-6, fora da tolerancia de 1e-6
    preco = (10000 + 2e-6) * 0.5
    with pytest.raises(ValueError):
        grid.to_ticks(preco)


def test_to_ticks_desalinhado_grosseiramente_levanta_valueerror():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    with pytest.raises(ValueError):
        grid.to_ticks(5000.3)


def test_to_price_e_inverso_de_to_ticks_incluindo_negativos():
    grid = PriceGrid(tick_size=0.5, decimals=1)
    for preco in (5000.5, -5000.5, 0.0, 10000.0, -10000.0):
        ticks = grid.to_ticks(preco)
        assert grid.to_price(ticks) == preco


def test_wdo_e_win_grid_tick_sizes():
    assert WDO_GRID.to_ticks(5000.5) == 10001
    assert WIN_GRID.to_ticks(130005.0) == 26001
