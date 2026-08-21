"""Testes de PROPRIEDADE DE MERCADO do `SimuladorWDO`.

`simulador.py` é a fonte de todo número de qualidade já produzido pelo
projeto (todo benchmark, toda medição de detector/motor roda em cima dele).
Três rodadas de auditoria (R2/R3/R4) apontaram que as dinâmicas de preço
podiam ser invertidas sem quebrar um único teste -- ou seja, nenhum teste
prendia o que o simulador PROMETE gerar (ver docstring do módulo: "o book se
move com o preço, agressões consomem a liquidez do topo, players grandes
aparecem com clipes fora do padrão, ocasionalmente muita agressão não
desloca o preço"). Este arquivo prende cada promessa.
"""

from __future__ import annotations

import fluxopro.dados.simulador as simulador_mod
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookSnapshot, Trade
from fluxopro.dados.simulador import SimuladorWDO


def _rodar(seed: int, n_eventos: int = 200, **kwargs) -> list[Trade | BookSnapshot]:
    barramento = Barramento()
    coletados: list[Trade | BookSnapshot] = []
    barramento.assinar(Trade, coletados.append)
    barramento.assinar(BookSnapshot, coletados.append)
    simulador = SimuladorWDO(barramento, seed=seed, n_eventos=n_eventos, **kwargs)
    simulador.iniciar()
    return coletados


def test_book_nunca_cruzado_em_nenhum_snapshot() -> None:
    """Promessa: "o book se move com o preço" -- e nunca de um jeito que
    cruze bid e ask. Verifica TODOS os níveis, não só o topo, e a ordenação
    correta (bids decrescentes, asks crescentes)."""
    sequencia = _rodar(seed=21, n_eventos=500)
    snapshots = [e for e in sequencia if isinstance(e, BookSnapshot)]
    assert snapshots
    for s in snapshots:
        precos_bid = [nivel.price for nivel in s.bids]
        precos_ask = [nivel.price for nivel in s.asks]
        assert precos_bid == sorted(precos_bid, reverse=True)
        assert precos_ask == sorted(precos_ask)
        assert max(precos_bid) < min(precos_ask), "book cruzado: bid >= ask"


def test_preco_desloca_na_direcao_do_agressor_nunca_ao_contrario() -> None:
    """Mata N04: agressão de COMPRA empurra o preço para CIMA (nunca para
    baixo) e agressão de VENDA empurra para BAIXO (nunca para cima). O preço
    de um trade só muda em relação ao trade anterior quando o agressor
    anterior zerou o topo e não houve absorção -- e a direção da mudança tem
    de ser a do lado que agrediu."""
    sequencia = _rodar(seed=99, n_eventos=3000)
    trades = [e for e in sequencia if isinstance(e, Trade)]

    deslocamentos_compra = 0
    deslocamentos_venda = 0
    for anterior, atual in zip(trades, trades[1:]):
        if atual.price > anterior.price:
            assert anterior.side_agressor is AgressorSide.BUY, (
                "preco subiu mas o trade anterior NAO foi agressao de compra"
            )
            deslocamentos_compra += 1
        elif atual.price < anterior.price:
            assert anterior.side_agressor is AgressorSide.SELL, (
                "preco desceu mas o trade anterior NAO foi agressao de venda"
            )
            deslocamentos_venda += 1

    # com 3000 eventos e prob. de zeragem do topo alta o bastante, os dois
    # tipos de deslocamento têm de ter ocorrido -- senão o teste não exerce
    # as duas direções.
    assert deslocamentos_compra > 0
    assert deslocamentos_venda > 0


def test_absorcao_forcada_a_100_por_cento_impede_qualquer_deslocamento_de_preco() -> None:
    """Mata N05 (regime de absorção desligado): com `_PROB_ABSORCAO` forçado
    a 1.0, TODO topo que zera é absorvido -- o preço não pode se mover em
    hipótese alguma, mesmo com muitos eventos e muita agressão."""
    original = simulador_mod._PROB_ABSORCAO
    try:
        simulador_mod._PROB_ABSORCAO = 1.0
        sequencia = _rodar(seed=55, n_eventos=1000)
    finally:
        simulador_mod._PROB_ABSORCAO = original

    trades = [e for e in sequencia if isinstance(e, Trade)]
    precos = {t.price for t in trades}
    assert len(precos) == 1, f"preco se moveu com absorcao=100%: {precos}"


def test_absorcao_zerada_deixa_o_preco_livre_para_se_mover() -> None:
    """Espelho do teste acima: com `_PROB_ABSORCAO` forçado a 0.0, o preço
    tem de se mover ao longo de eventos suficientes -- confirma que o
    teste anterior não passa "por acidente" (ex.: preço nunca se moveria de
    qualquer forma)."""
    original = simulador_mod._PROB_ABSORCAO
    try:
        simulador_mod._PROB_ABSORCAO = 0.0
        sequencia = _rodar(seed=55, n_eventos=1000)
    finally:
        simulador_mod._PROB_ABSORCAO = original

    trades = [e for e in sequencia if isinstance(e, Trade)]
    precos = {t.price for t in trades}
    assert len(precos) > 1, "preco nunca se moveu mesmo com absorcao=0%"


def test_player_grande_forcado_gera_clips_fora_do_padrao_normal() -> None:
    """Mata a inversão "players grandes não movem nada": com
    `_PROB_PLAYER_GRANDE` forçado a 1.0, todo trade usa o multiplicador de
    clip grande -- qty tem de sair do intervalo normal (1-10) e cair no
    intervalo ampliado (8-80)."""
    original = simulador_mod._PROB_PLAYER_GRANDE
    try:
        simulador_mod._PROB_PLAYER_GRANDE = 1.0
        sequencia = _rodar(seed=3, n_eventos=300)
    finally:
        simulador_mod._PROB_PLAYER_GRANDE = original

    trades = [e for e in sequencia if isinstance(e, Trade)]
    qtys = [t.qty for t in trades]
    assert qtys
    assert all(8 <= q <= 80 for q in qtys), f"qty fora do intervalo de clip grande: {qtys}"
    assert any(q > 10 for q in qtys), "nenhum clip realmente maior que o normal apareceu"


def test_sem_player_grande_os_clips_ficam_no_intervalo_normal() -> None:
    """Espelho do teste acima: com `_PROB_PLAYER_GRANDE` forçado a 0.0,
    nenhum trade pode ultrapassar o intervalo normal de 1-10 lotes --
    confirma que o multiplicador realmente depende do sorteio, e não é
    aplicado incondicionalmente."""
    original = simulador_mod._PROB_PLAYER_GRANDE
    try:
        simulador_mod._PROB_PLAYER_GRANDE = 0.0
        sequencia = _rodar(seed=3, n_eventos=300)
    finally:
        simulador_mod._PROB_PLAYER_GRANDE = original

    trades = [e for e in sequencia if isinstance(e, Trade)]
    qtys = [t.qty for t in trades]
    assert qtys
    assert all(1 <= q <= 10 for q in qtys), f"clip grande vazou sem o sorteio: {qtys}"


def test_distribuicao_de_tamanho_de_trade_normal_tem_a_forma_configurada() -> None:
    """Promessa: qty normal é `randint(1, 10)` uniforme. Roda uma amostra
    grande (player grande desligado) e confere que o mínimo e o máximo
    observados cobrem o intervalo declarado -- não só que ficam dentro dele
    (o teste anterior já garante isso), mas que a distribuição realmente usa
    as pontas, e não um subconjunto estreito."""
    original = simulador_mod._PROB_PLAYER_GRANDE
    try:
        simulador_mod._PROB_PLAYER_GRANDE = 0.0
        sequencia = _rodar(seed=123, n_eventos=2000)
    finally:
        simulador_mod._PROB_PLAYER_GRANDE = original

    qtys = [t.qty for t in sequencia if isinstance(t, Trade)]
    assert min(qtys) == 1
    assert max(qtys) == 10


def test_agressao_de_compra_consome_o_topo_do_ask_nao_do_bid() -> None:
    """Promessa: "agressões consomem a liquidez do topo" -- do lado
    correto. Uma agressão de COMPRA tem de reduzir `_qty_topo_ask` (o book
    do lado vendedor, que é quem a compra atinge), nunca o bid."""
    barramento = Barramento()
    sim = SimuladorWDO(barramento, seed=1, n_eventos=1)
    ask_antes = sim._qty_topo_ask
    bid_antes = sim._qty_topo_bid

    # força determinismo do proximo sorteio: monkeypatch simples via
    # substituicao do rng por um que sempre devolve valores que NAO
    # disparam absorcao/player-grande e agressor de COMPRA (< 0.5).
    class _RngFixo:
        def __init__(self):
            self._chamadas = 0

        def expovariate(self, _lambd):
            return 0.001

        def random(self):
            self._chamadas += 1
            # 1a chamada: absorcao (quer False -> valor alto)
            # 2a chamada: player_grande (quer False -> valor alto)
            # 3a chamada: agressor (quer BUY -> valor baixo)
            return [0.99, 0.99, 0.01][self._chamadas - 1]

        def randint(self, a, b):
            return a

        def gauss(self, mu, sigma):
            return 0.0

    sim._rng = _RngFixo()
    sim.iniciar()

    assert sim._qty_topo_ask < ask_antes, "compra deveria consumir o topo do ASK"
    assert sim._qty_topo_bid == bid_antes, "compra nao deveria mexer no topo do BID"
