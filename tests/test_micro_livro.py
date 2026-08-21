"""Contrato direto do `LivroMBO`.

Até esta suíte existir, o arquivo mais intrincado do projeto era exercitado
apenas como *fixture* dos testes de detector: nenhum teste afirmava nada sobre
o comportamento dele. A auditoria adversarial mostrou o custo disso — inverter
a fila FIFO, devolver o PIOR bid ou somar o consumo em `qty_a_frente` passava
verde.

A prioridade preço-tempo É o diferencial do produto: `qty_a_frente`,
`DetectorEscora` e toda leitura de "quem está na frente" saem dela. Por isso
os testes daqui verificam QUAL `order_id` foi tocado e em QUE posição a ordem
ficou, nunca só a quantidade agregada — quantidade agregada é idêntica em fila
FIFO e LIFO, e foi exatamente por isso que a mutação sobreviveu.
"""

from __future__ import annotations

from collections import deque

import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import Side
from fluxopro.microestrutura.eventos_mbo import (
    FonteMicro,
    OrdemEvento,
    TipoEventoOrdem,
)
from fluxopro.microestrutura.livro_mbo import (
    UM_SEGUNDO_NS,
    ConfigLivroMBO,
    CruzamentoLivro,
    LivroMBO,
)

SYM = "WDOV26"
BID = 5000
ASK = 5001


def _livro(config: ConfigLivroMBO | None = None) -> LivroMBO:
    return LivroMBO(SYM, config)


def _coletor(livro: LivroMBO) -> list[OrdemEvento]:
    eventos: list[OrdemEvento] = []
    livro.assinar_evento(eventos.append)
    return eventos


def _fila_abc(livro: LivroMBO, side: Side = Side.BUY, price: int = BID) -> None:
    """Três ordens de 100 no mesmo nível, entrando em A -> B -> C."""
    livro.adicionar("A", side, price, 100, 1_000)
    livro.adicionar("B", side, price, 100, 2_000)
    livro.adicionar("C", side, price, 100, 3_000)


def _ids_da_fila(livro: LivroMBO, side: Side = Side.BUY, price: int = BID) -> list[str]:
    detalhe = livro.nivel(side, price)
    return [] if detalhe is None else [o.order_id for o in detalhe.ordens]


# ===========================================================================
# Prioridade FIFO — o coração do produto
# ===========================================================================


def test_execucao_parcial_consome_a_ordem_da_frente_e_nao_a_do_fim():
    """MATA a mutação FIFO->LIFO (`fila[0]` -> `fila[-1]`).

    A asserção que importa é o `order_id`: com LIFO a quantidade consumida e o
    `qty_total` do nível ficam IDÊNTICOS — só o dono do preenchimento muda.
    """
    livro = _livro()
    _fila_abc(livro)

    eventos = livro.executar(Side.BUY, BID, 40, 10_000)

    assert len(eventos) == 1
    assert eventos[0].order_id == "A"  # <- a frente, jamais "C"
    assert eventos[0].tipo is TipoEventoOrdem.TRADE
    assert eventos[0].qty == 40
    assert eventos[0].qty_restante == 60

    a = livro.ordem("A")
    b = livro.ordem("B")
    c = livro.ordem("C")
    assert a is not None and b is not None and c is not None
    assert (a.qty_restante, b.qty_restante, c.qty_restante) == (60, 100, 100)
    assert (a.qty_executada, b.qty_executada, c.qty_executada) == (40, 0, 0)
    assert livro.qty_total(Side.BUY, BID) == 260


def test_execucao_atravessa_tres_ordens_na_ordem_de_prioridade():
    """MATA FIFO->LIFO e `popleft`->`pop` ao zerar a ordem.

    Com `pop()` no zeramento, zerar A descarta C da deque (C fica órfã: ativa,
    somando em `qty_total`, e nunca mais consumível) — sobram 2 eventos e o
    nível fica com 100 pendurados.
    """
    livro = _livro()
    _fila_abc(livro)

    eventos = livro.executar(Side.BUY, BID, 250, 10_000)

    assert [e.order_id for e in eventos] == ["A", "B", "C"]
    assert [e.qty for e in eventos] == [100, 100, 50]
    assert [e.qty_restante for e in eventos] == [0, 0, 50]
    assert [e.evidencia["zerou_ordem"] for e in eventos] == [True, True, False]
    assert livro.qty_total(Side.BUY, BID) == 50
    assert _ids_da_fila(livro) == ["C"]


def test_varrer_o_nivel_inteiro_consome_todas_as_ordens_e_zera_o_total():
    """MATA `popleft`->`pop` ao zerar: nenhuma ordem pode ficar órfã na deque."""
    livro = _livro()
    _fila_abc(livro)

    eventos = livro.executar(Side.BUY, BID, 300, 10_000)

    assert [e.order_id for e in eventos] == ["A", "B", "C"]
    assert livro.qty_total(Side.BUY, BID) == 0
    assert livro.nivel(Side.BUY, BID) == livro.nivel(Side.BUY, BID)
    detalhe = livro.nivel(Side.BUY, BID)
    assert detalhe is not None and detalhe.n_ordens == 0
    for oid in ("A", "B", "C"):
        ordem = livro.ordem(oid)
        assert ordem is not None
        assert not ordem.ativa
        assert ordem.qty_restante == 0
        assert ordem.timestamp_saida_ns == 10_000


def test_execucao_maior_que_o_nivel_para_quando_a_fila_acaba():
    livro = _livro()
    _fila_abc(livro)
    eventos = livro.executar(Side.BUY, BID, 10_000, 10_000)
    assert [e.order_id for e in eventos] == ["A", "B", "C"]
    assert sum(e.qty for e in eventos) == 300
    assert livro.qty_total(Side.BUY, BID) == 0


def test_execucao_em_nivel_inexistente_ou_qty_nao_positiva_nao_faz_nada():
    livro = _livro()
    _fila_abc(livro)
    assert livro.executar(Side.BUY, 9999, 10, 10_000) == ()
    assert livro.executar(Side.SELL, BID, 10, 10_000) == ()
    assert livro.executar(Side.BUY, BID, 0, 10_000) == ()
    assert livro.executar(Side.BUY, BID, -5, 10_000) == ()
    assert livro.qty_total(Side.BUY, BID) == 300


def test_ordem_nova_entra_no_fim_da_fila():
    livro = _livro()
    _fila_abc(livro)
    livro.adicionar("D", Side.BUY, BID, 10, 4_000)
    assert _ids_da_fila(livro) == ["A", "B", "C", "D"]


def test_ultima_ordem_ativa_e_a_do_fim_da_fila():
    livro = _livro()
    _fila_abc(livro)
    ultima = livro.ultima_ordem_ativa(Side.BUY, BID)
    assert ultima is not None and ultima.order_id == "C"
    livro.cancelar("C", 5_000)
    ultima = livro.ultima_ordem_ativa(Side.BUY, BID)
    assert ultima is not None and ultima.order_id == "B"
    assert livro.ultima_ordem_ativa(Side.SELL, BID) is None


# ===========================================================================
# melhor_bid / melhor_ask
# ===========================================================================


def test_melhor_bid_e_o_maior_e_melhor_ask_e_o_menor():
    """MATA `melhor_bid()` devolvendo o PIOR bid (e o espelho no ask)."""
    livro = _livro()
    for i, price in enumerate((4998, 5000, 4999)):  # fora de ordem de propósito
        livro.adicionar(f"b{i}", Side.BUY, price, 10, 1_000 + i)
    for i, price in enumerate((5003, 5001, 5002)):
        livro.adicionar(f"a{i}", Side.SELL, price, 10, 2_000 + i)

    assert livro.melhor_bid() == 5000
    assert livro.melhor_ask() == 5001
    assert livro.melhor_ask() - livro.melhor_bid() == 1


def test_livro_vazio_nao_tem_topo():
    livro = _livro()
    assert livro.melhor_bid() is None
    assert livro.melhor_ask() is None


def test_topo_avanca_quando_o_melhor_nivel_e_consumido():
    """O heap tem remoção preguiçosa: o topo obsoleto precisa ser limpo."""
    livro = _livro()
    livro.adicionar("b1", Side.BUY, 5000, 10, 1_000)
    livro.adicionar("b2", Side.BUY, 4999, 10, 1_100)
    livro.adicionar("a1", Side.SELL, 5001, 10, 1_200)
    livro.adicionar("a2", Side.SELL, 5002, 10, 1_300)

    assert (livro.melhor_bid(), livro.melhor_ask()) == (5000, 5001)

    livro.executar(Side.BUY, 5000, 10, 2_000)
    livro.executar(Side.SELL, 5001, 10, 2_100)

    assert livro.melhor_bid() == 4999
    assert livro.melhor_ask() == 5002

    livro.executar(Side.BUY, 4999, 10, 2_200)
    livro.executar(Side.SELL, 5002, 10, 2_300)
    assert livro.melhor_bid() is None
    assert livro.melhor_ask() is None


def test_topo_recua_quando_o_melhor_nivel_e_cancelado():
    livro = _livro()
    livro.adicionar("b1", Side.BUY, 5000, 10, 1_000)
    livro.adicionar("b2", Side.BUY, 4999, 10, 1_100)
    livro.cancelar("b1", 2_000)
    assert livro.melhor_bid() == 4999


def test_nivel_esvaziado_e_repovoado_volta_a_ser_topo():
    """REGRESSÃO — preço sumia do topo de livro para sempre.

    A remoção do heap é preguiçosa: ler `melhor_bid()` enquanto o nível está
    zerado descarta o preço do heap. Mas o NÍVEL sobrevive no dicionário
    (guarda histórico de reposição e pico exibido), então `_obter_nivel` não o
    republicava, e o preço nunca mais voltava a ser topo — spread, proximidade
    e `esta_cruzado` saíam errados em silêncio, sem nenhum erro.

    Só depende de uma LEITURA no momento em que o nível está vazio: qualquer
    consumidor normal do topo de livro dispara.
    """
    livro = _livro()
    livro.adicionar("b1", Side.BUY, 5000, 10, 1_000)
    livro.adicionar("b2", Side.BUY, 4999, 10, 1_100)
    livro.executar(Side.BUY, 5000, 10, 2_000)
    assert livro.melhor_bid() == 4999  # <- a leitura que limpava o heap
    livro.adicionar("b3", Side.BUY, 5000, 7, 3_000)
    assert livro.melhor_bid() == 5000
    assert livro.qty_total(Side.BUY, 5000) == 7


def test_nivel_esvaziado_e_repovoado_volta_a_ser_topo_no_ask():
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 5001, 10, 1_000)
    livro.adicionar("a2", Side.SELL, 5002, 10, 1_100)
    livro.executar(Side.SELL, 5001, 10, 2_000)
    assert livro.melhor_ask() == 5002
    livro.adicionar("a3", Side.SELL, 5001, 7, 3_000)
    assert livro.melhor_ask() == 5001


def test_ciclos_repetidos_de_esvaziar_e_repovoar_nao_incham_o_heap():
    """A republicação não pode virar vazamento: uma entrada viva por preço."""
    livro = _livro()
    for i in range(200):
        livro.adicionar(f"b{i}", Side.BUY, 5000, 10, 1_000 + i)
        assert livro.melhor_bid() == 5000
        livro.executar(Side.BUY, 5000, 10, 1_500 + i)
        assert livro.melhor_bid() is None
    assert len(livro._heap_bids) <= 1


def test_niveis_ordenados_respeita_o_lado():
    livro = _livro()
    for i, price in enumerate((4998, 5000, 4999)):
        livro.adicionar(f"b{i}", Side.BUY, price, 10, 1_000 + i)
    for i, price in enumerate((5003, 5001, 5002)):
        livro.adicionar(f"a{i}", Side.SELL, price, 10, 2_000 + i)

    bids = livro.niveis_ordenados(Side.BUY)
    asks = livro.niveis_ordenados(Side.SELL)
    assert [n.price for n in bids] == [5000, 4999, 4998]
    assert [n.price for n in asks] == [5001, 5002, 5003]
    assert [n.price for n in livro.niveis_ordenados(Side.BUY, profundidade=2)] == [5000, 4999]


# ===========================================================================
# qty_a_frente — o SENTIDO da conta
# ===========================================================================


def test_qty_a_frente_na_entrada_reflete_a_posicao_na_fila():
    livro = _livro()
    _fila_abc(livro)
    assert livro.qty_a_frente("A") == 0
    assert livro.qty_a_frente("B") == 100
    assert livro.qty_a_frente("C") == 200


def test_qty_a_frente_DECRESCE_conforme_o_nivel_e_consumido():
    """MATA `qty_a_frente` que SOMA o consumo em vez de descontar.

    Com o sinal invertido a fila de C "cresceria" para 300 depois de 100
    contratos serem varridos — o oposto do fato econômico.
    """
    livro = _livro()
    _fila_abc(livro)
    assert livro.qty_a_frente("C") == 200

    livro.executar(Side.BUY, BID, 100, 10_000)  # varre A inteira
    assert livro.qty_a_frente("C") == 100
    assert livro.qty_a_frente("B") == 0

    livro.executar(Side.BUY, BID, 60, 11_000)  # come 60 de B
    assert livro.qty_a_frente("C") == 40

    livro.executar(Side.BUY, BID, 40, 12_000)  # zera B
    assert livro.qty_a_frente("C") == 0


def test_qty_a_frente_e_monotona_nao_crescente_sob_consumo():
    """Blindagem de sinal independente dos valores exatos."""
    livro = _livro()
    _fila_abc(livro)
    anterior = livro.qty_a_frente("C")
    assert anterior is not None
    for i in range(1, 5):
        livro.executar(Side.BUY, BID, 25, 10_000 + i)
        atual = livro.qty_a_frente("C")
        assert atual is not None
        assert atual <= anterior
        anterior = atual
    assert anterior == 100


def test_qty_a_frente_nunca_fica_negativa():
    livro = _livro()
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 280, 10_000)
    assert livro.qty_a_frente("C") == 0


def test_qty_a_frente_nao_conta_o_que_a_propria_ordem_executou():
    livro = _livro()
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 250, 10_000)  # C fica com 50 e já executou 50
    c = livro.ordem("C")
    assert c is not None and c.qty_executada == 50
    assert livro.qty_a_frente("C") == 0  # é a frente da fila agora


def test_qty_a_frente_e_none_para_ordem_desconhecida_ou_morta():
    livro = _livro()
    _fila_abc(livro)
    assert livro.qty_a_frente("ZZZ") is None
    livro.cancelar("B", 5_000)
    assert livro.qty_a_frente("B") is None


# ===========================================================================
# modificar — redução mantém prioridade, aumento perde
# ===========================================================================


def test_reducao_mantem_a_posicao_na_fila():
    livro = _livro()
    _fila_abc(livro)
    livro.modificar("A", 30, 5_000)

    assert _ids_da_fila(livro) == ["A", "B", "C"]  # A continua na FRENTE
    a = livro.ordem("A")
    assert a is not None and a.qty_restante == 30 and a.n_reducoes == 1
    assert livro.qty_total(Side.BUY, BID) == 230

    eventos = livro.executar(Side.BUY, BID, 30, 6_000)
    assert [e.order_id for e in eventos] == ["A"]


def test_aumento_perde_prioridade_e_vai_para_o_FIM_da_fila():
    livro = _livro()
    _fila_abc(livro)
    livro.modificar("A", 250, 5_000)

    assert _ids_da_fila(livro) == ["B", "C", "A"]  # A foi para o fim
    a = livro.ordem("A")
    assert a is not None and a.qty_restante == 250
    assert a.timestamp_entrada_ns == 5_000  # relógio de fila reiniciado
    assert livro.qty_total(Side.BUY, BID) == 450
    assert livro.qty_a_frente("A") == 200

    eventos = livro.executar(Side.BUY, BID, 100, 6_000)
    assert [e.order_id for e in eventos] == ["B"]  # B, não A


def test_evento_de_modificacao_carrega_delta_e_perda_de_prioridade():
    livro = _livro()
    eventos = _coletor(livro)
    _fila_abc(livro)
    eventos.clear()

    livro.modificar("A", 40, 5_000)
    livro.modificar("B", 400, 6_000)

    assert eventos[0].tipo is TipoEventoOrdem.REPLACE
    assert eventos[0].qty == 60 and eventos[0].qty_restante == 40
    assert eventos[0].evidencia["delta_qty"] == -60
    assert eventos[0].evidencia["perdeu_prioridade"] is False
    assert eventos[1].evidencia["delta_qty"] == 300
    assert eventos[1].evidencia["perdeu_prioridade"] is True


def test_modificar_para_qty_nao_positiva_cancela():
    livro = _livro()
    eventos = _coletor(livro)
    _fila_abc(livro)
    eventos.clear()

    resultado = livro.modificar("B", 0, 5_000)
    assert resultado is not None and not resultado.ativa
    assert eventos[0].tipo is TipoEventoOrdem.CANCEL
    assert livro.qty_total(Side.BUY, BID) == 200


def test_modificar_sem_mudanca_e_ordem_morta_sao_no_op():
    livro = _livro()
    _fila_abc(livro)
    eventos = _coletor(livro)

    assert livro.modificar("A", 100, 5_000) is livro.ordem("A")
    assert livro.modificar("ZZZ", 10, 5_000) is None
    livro.cancelar("C", 5_100)
    eventos.clear()
    assert livro.modificar("C", 10, 5_200) is None
    assert eventos == []


def test_aumento_preserva_historico_de_execucao_da_ordem():
    livro = _livro()
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 40, 5_000)  # A executa 40
    livro.modificar("A", 300, 6_000)
    a = livro.ordem("A")
    assert a is not None
    assert a.qty_executada == 40
    assert a.qty_restante == 300
    assert _ids_da_fila(livro) == ["B", "C", "A"]
    assert livro.qty_a_frente("A") == 200


# ===========================================================================
# cancelar — remoção preguiçosa não pode corromper a fila
# ===========================================================================


def test_ordem_cancelada_no_MEIO_nao_e_consumida_depois():
    livro = _livro()
    _fila_abc(livro)
    livro.cancelar("B", 5_000)
    assert livro.qty_total(Side.BUY, BID) == 200

    eventos = livro.executar(Side.BUY, BID, 200, 6_000)
    assert [e.order_id for e in eventos] == ["A", "C"]  # B pulada
    b = livro.ordem("B")
    assert b is not None and b.qty_executada == 0


def test_cancelar_a_FRENTE_nao_impede_o_consumo_da_seguinte():
    """MATA `popleft`->`pop` na limpeza da ordem inativa.

    Com `pop()` ali, descartar a A inativa arrancaria C, depois B, depois A —
    e o `executar` devolveria ZERO evento com a fila cheia de ordens vivas.
    """
    livro = _livro()
    _fila_abc(livro)
    livro.cancelar("A", 5_000)

    eventos = livro.executar(Side.BUY, BID, 100, 6_000)
    assert [e.order_id for e in eventos] == ["B"]
    assert _ids_da_fila(livro) == ["C"]
    assert livro.qty_total(Side.BUY, BID) == 100


def test_cancelar_todas_as_ordens_da_frente_ainda_permite_consumir_a_ultima():
    livro = _livro()
    _fila_abc(livro)
    livro.cancelar("A", 5_000)
    livro.cancelar("B", 5_100)
    eventos = livro.executar(Side.BUY, BID, 100, 6_000)
    assert [e.order_id for e in eventos] == ["C"]
    assert livro.qty_total(Side.BUY, BID) == 0


def test_cancelar_duas_vezes_ou_ordem_inexistente_devolve_none():
    livro = _livro()
    _fila_abc(livro)
    assert livro.cancelar("A", 5_000) is not None
    assert livro.cancelar("A", 5_100) is None
    assert livro.cancelar("ZZZ", 5_200) is None
    assert livro.qty_total(Side.BUY, BID) == 200


def test_evento_de_cancelamento_carrega_o_saldo_que_saiu():
    livro = _livro()
    eventos = _coletor(livro)
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 30, 5_000)
    eventos.clear()

    livro.cancelar("A", 6_000)
    assert eventos[0].tipo is TipoEventoOrdem.CANCEL
    assert eventos[0].qty == 70  # o saldo, não a original
    assert eventos[0].qty_restante == 0
    assert eventos[0].order_id == "A"


def test_expirar_emite_EXPIRE_e_nao_CANCEL():
    livro = _livro()
    eventos = _coletor(livro)
    _fila_abc(livro)
    eventos.clear()

    livro.expirar("B", 6_000)
    assert eventos[0].tipo is TipoEventoOrdem.EXPIRE
    assert _ids_da_fila(livro) == ["A", "C"]


# ===========================================================================
# recarregar — assinatura de iceberg em feed MBO real
# ===========================================================================


def test_recarregar_mantem_order_id_e_prioridade_e_conta_a_recarga():
    livro = _livro()
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 100, 5_000)  # A some, B vira frente
    assert _ids_da_fila(livro) == ["B", "C"]

    ordem = livro.recarregar("B", 80, 6_000)
    assert ordem is not None
    assert ordem.order_id == "B"
    assert ordem.n_recargas == 1
    assert ordem.qty_restante == 180
    assert ordem.qty_original == 100  # a original NÃO é reescrita
    assert _ids_da_fila(livro) == ["B", "C"]  # continua na frente
    assert livro.qty_total(Side.BUY, BID) == 280

    eventos = livro.executar(Side.BUY, BID, 180, 7_000)
    assert [e.order_id for e in eventos] == ["B"]  # a recarga toda foi de B


def test_qty_a_frente_NAO_enxerga_recarga_a_frente_limitacao_conhecida():
    """Pino da limitação: aqui `qty_a_frente` deixa de ser cota superior.

    `qty_a_frente_na_entrada` é congelado na entrada da ordem, então volume que
    a ordem DA FRENTE ganha por `recarregar` (iceberg) fica invisível: C tem de
    fato 180 pela frente e o livro responde 100. Corrigir exigiria varrer a fila
    — O(n) no caminho quente — e a documentação do método promete cota superior,
    não exatidão. O teste existe para que a limitação seja uma DECISÃO visível e
    não uma surpresa: se algum dia o cálculo mudar, este teste avisa.
    """
    livro = _livro()
    _fila_abc(livro)
    livro.executar(Side.BUY, BID, 100, 5_000)  # varre A; C tem 100 pela frente
    assert livro.qty_a_frente("C") == 100

    livro.recarregar("B", 80, 6_000)  # B, à frente de C, engorda
    assert livro.qty_total(Side.BUY, BID) == 280
    assert livro.qty_a_frente("C") == 100  # verdade seria 180 — cota FUROU


def test_recarregar_atualiza_o_pico_exibido_e_o_evento():
    livro = _livro()
    eventos = _coletor(livro)
    livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    livro.executar(Side.BUY, BID, 60, 2_000)
    eventos.clear()

    livro.recarregar("A", 60, 3_000)
    assert eventos[0].tipo is TipoEventoOrdem.REPLACE
    assert eventos[0].qty == 60
    assert eventos[0].qty_restante == 100
    assert eventos[0].evidencia["recarga"] is True
    assert eventos[0].evidencia["n_recargas"] == 1
    assert eventos[0].evidencia["qty_executada"] == 60
    assert livro.qty_exibida_max(Side.BUY, BID) == 100


def test_recarregar_ordem_morta_ou_qty_nao_positiva_devolve_none():
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    assert livro.recarregar("A", 0, 2_000) is None
    assert livro.recarregar("A", -5, 2_000) is None
    assert livro.recarregar("ZZZ", 10, 2_000) is None
    livro.cancelar("A", 2_100)
    assert livro.recarregar("A", 10, 2_200) is None


def test_recargas_sucessivas_acumulam_o_contador():
    """Iceberg clássico: a ordem executa muito mais do que jamais exibiu."""
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    for i in range(3):
        livro.executar(Side.BUY, BID, 60, 2_000 + i)  # nunca zera a ordem
        livro.recarregar("A", 60, 2_500 + i)
    a = livro.ordem("A")
    assert a is not None
    assert a.ativa
    assert a.n_recargas == 3
    assert a.qty_executada == 180
    assert a.qty_original == 100  # exibiu 100, executou 180
    assert livro.qty_exibida_max(Side.BUY, BID) == 100


def test_ordem_zerada_nao_aceita_recarga():
    """Uma vez varrida, a ordem morreu — recarga tem de virar ordem NOVA."""
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    livro.executar(Side.BUY, BID, 100, 2_000)
    assert livro.recarregar("A", 100, 2_100) is None


# ===========================================================================
# Janela de reposição — os DOIS lados da fronteira
# ===========================================================================


def test_reposicao_dentro_da_janela_conta_e_FORA_da_janela_nao():
    """MATA a janela de reposição 1000x maior.

    Com a janela inflada, a ordem que entra MUITO depois da varrida ainda seria
    marcada como escora — e `DetectorEscora` passaria a disparar em qualquer
    ordem nova no preço, a qualquer tempo.
    """
    janela = 2 * UM_SEGUNDO_NS
    config = ConfigLivroMBO(janela_reposicao_ns=janela)

    # --- dentro: exatamente no limite da janela ---
    dentro = LivroMBO(SYM, config)
    dentro.adicionar("A", Side.BUY, BID, 100, 0)
    dentro.executar(Side.BUY, BID, 100, 1_000)  # varre o nível em t=1000
    ordem = dentro.adicionar("R", Side.BUY, BID, 100, 1_000 + janela)
    assert ordem.eh_reposicao is True
    assert dentro.n_reposicoes(Side.BUY, BID) == 1

    # --- fora: UM nanossegundo além ---
    fora = LivroMBO(SYM, config)
    fora.adicionar("A", Side.BUY, BID, 100, 0)
    fora.executar(Side.BUY, BID, 100, 1_000)
    ordem = fora.adicionar("R", Side.BUY, BID, 100, 1_000 + janela + 1)
    assert ordem.eh_reposicao is False
    assert fora.n_reposicoes(Side.BUY, BID) == 0


@pytest.mark.parametrize(
    ("atraso_ns", "esperado"),
    [(0, True), (1, True), (UM_SEGUNDO_NS, True), (UM_SEGUNDO_NS + 1, False),
     (10 * UM_SEGUNDO_NS, False)],
)
def test_fronteira_da_janela_de_reposicao_ponto_a_ponto(atraso_ns, esperado):
    """A janela é configurada em 1s; nada além dela pode contar como escora."""
    livro = LivroMBO(SYM, ConfigLivroMBO(janela_reposicao_ns=UM_SEGUNDO_NS))
    livro.adicionar("A", Side.BUY, BID, 100, 0)
    livro.executar(Side.BUY, BID, 100, 1_000)
    ordem = livro.adicionar("R", Side.BUY, BID, 50, 1_000 + atraso_ns)
    assert ordem.eh_reposicao is esperado
    assert livro.n_reposicoes(Side.BUY, BID) == (1 if esperado else 0)


def test_janela_de_reposicao_PADRAO_e_de_dois_segundos():
    """Prende o DEFAULT de fábrica, não só a janela injetada por config.

    Os testes acima passam `ConfigLivroMBO` explícita — cegos a uma mutação no
    valor padrão. Quem usa `LivroMBO(symbol)` sem config usa este número, e é
    ele que decide se `DetectorEscora` dispara.
    """
    assert ConfigLivroMBO().janela_reposicao_ns == 2 * UM_SEGUNDO_NS

    dentro = LivroMBO(SYM)  # sem config: default de fábrica
    dentro.adicionar("A", Side.BUY, BID, 100, 0)
    dentro.executar(Side.BUY, BID, 100, 1_000)
    assert dentro.adicionar("R", Side.BUY, BID, 10, 1_000 + 2 * UM_SEGUNDO_NS).eh_reposicao

    fora = LivroMBO(SYM)
    fora.adicionar("A", Side.BUY, BID, 100, 0)
    fora.executar(Side.BUY, BID, 100, 1_000)
    assert not fora.adicionar(
        "R", Side.BUY, BID, 10, 1_000 + 2 * UM_SEGUNDO_NS + 1
    ).eh_reposicao


def test_sem_consumo_previo_nao_ha_reposicao():
    livro = _livro()
    ordem = livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    assert ordem.eh_reposicao is False
    assert livro.n_reposicoes(Side.BUY, BID) == 0


def test_reposicao_pode_exigir_o_MESMO_broker():
    config = ConfigLivroMBO(
        janela_reposicao_ns=UM_SEGUNDO_NS, exigir_mesmo_broker_para_reposicao=True
    )
    livro = LivroMBO(SYM, config)
    livro.adicionar("A", Side.BUY, BID, 100, 0, broker="XP")
    livro.executar(Side.BUY, BID, 100, 1_000)

    outro = livro.adicionar("R1", Side.BUY, BID, 50, 1_100, broker="BTG")
    assert outro.eh_reposicao is False
    mesmo = livro.adicionar("R2", Side.BUY, BID, 50, 1_200, broker="XP")
    assert mesmo.eh_reposicao is True
    anonimo = livro.adicionar("R3", Side.BUY, BID, 50, 1_300, broker="")
    assert anonimo.eh_reposicao is False
    assert livro.n_reposicoes(Side.BUY, BID) == 1


def test_evidencia_do_evento_NEW_carrega_eh_reposicao():
    livro = LivroMBO(SYM, ConfigLivroMBO(janela_reposicao_ns=UM_SEGUNDO_NS))
    eventos = _coletor(livro)
    livro.adicionar("A", Side.BUY, BID, 100, 0)
    livro.executar(Side.BUY, BID, 100, 1_000)
    eventos.clear()
    livro.adicionar("R", Side.BUY, BID, 100, 1_500, evidencia={"origem": "teste"})
    assert eventos[0].tipo is TipoEventoOrdem.NEW
    assert eventos[0].evidencia["eh_reposicao"] is True
    assert eventos[0].evidencia["origem"] == "teste"


# ===========================================================================
# adicionar — validação e metadados de nível
# ===========================================================================


def test_adicionar_qty_nao_positiva_levanta():
    livro = _livro()
    with pytest.raises(ValueError, match="qty deve ser positiva"):
        livro.adicionar("A", Side.BUY, BID, 0, 1_000)
    with pytest.raises(ValueError, match="qty deve ser positiva"):
        livro.adicionar("A", Side.BUY, BID, -3, 1_000)


def test_adicionar_order_id_ja_ativo_levanta():
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 10, 1_000)
    with pytest.raises(ValueError, match="ja ativo no livro"):
        livro.adicionar("A", Side.BUY, BID, 10, 1_100)


def test_order_id_pode_ser_reaproveitado_depois_de_morrer():
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 10, 1_000)
    livro.cancelar("A", 1_100)
    ordem = livro.adicionar("A", Side.BUY, BID, 20, 1_200)
    assert ordem.qty_restante == 20


def test_qty_exibida_max_guarda_o_pico_e_nao_o_atual():
    livro = _livro()
    _fila_abc(livro)
    assert livro.qty_exibida_max(Side.BUY, BID) == 300
    livro.executar(Side.BUY, BID, 300, 5_000)
    assert livro.qty_total(Side.BUY, BID) == 0
    assert livro.qty_exibida_max(Side.BUY, BID) == 300


def test_leituras_de_nivel_inexistente_sao_neutras():
    livro = _livro()
    assert livro.nivel(Side.BUY, 1) is None
    assert livro.qty_total(Side.BUY, 1) == 0
    assert livro.n_reposicoes(Side.BUY, 1) == 0
    assert livro.qty_exibida_max(Side.BUY, 1) == 0
    assert livro.ordem("ZZZ") is None
    assert livro.idade_ordem_ns("ZZZ", 10) is None


def test_idade_da_ordem_congela_na_saida():
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 10, 1_000)
    assert livro.idade_ordem_ns("A", 3_000) == 2_000
    livro.cancelar("A", 4_000)
    assert livro.idade_ordem_ns("A", 9_999) == 3_000


def test_evento_trade_carrega_a_evidencia_de_leitura_de_fluxo():
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 100, 1_000, broker="XP")
    eventos = livro.executar(
        Side.BUY, BID, 40, 5_000, broker_agressor="BTG", evidencia={"nota": "x"}
    )
    ev = eventos[0]
    assert ev.broker == "XP"
    assert ev.evidencia["broker_agressor"] == "BTG"
    assert ev.evidencia["idade_ordem_ns"] == 4_000
    assert ev.evidencia["qty_executada_acumulada"] == 40
    assert ev.evidencia["qty_original_ordem"] == 100
    assert ev.evidencia["n_recargas_ordem"] == 0
    assert ev.evidencia["zerou_ordem"] is False
    assert ev.evidencia["nota"] == "x"


def test_fonte_e_confianca_viajam_no_evento():
    livro = _livro()
    livro.adicionar(
        "A", Side.BUY, BID, 100, 1_000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.6
    )
    eventos = livro.executar(
        Side.BUY, BID, 10, 2_000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.42
    )
    assert eventos[0].fonte is FonteMicro.MBP_INFERIDO
    assert eventos[0].confianca == 0.42


def test_eventos_tambem_saem_pelo_barramento():
    barramento = Barramento()
    recebidos: list[OrdemEvento] = []
    barramento.assinar(OrdemEvento, recebidos.append)
    livro = LivroMBO(SYM, None, barramento)

    livro.adicionar("A", Side.BUY, BID, 100, 1_000)
    livro.executar(Side.BUY, BID, 100, 2_000)

    assert [e.tipo for e in recebidos] == [TipoEventoOrdem.NEW, TipoEventoOrdem.TRADE]


# ===========================================================================
# Determinismo
# ===========================================================================


def _roteiro(livro: LivroMBO) -> None:
    livro.adicionar("A", Side.BUY, 5000, 100, 1_000, broker="XP")
    livro.adicionar("B", Side.BUY, 5000, 50, 1_100, broker="BTG")
    livro.adicionar("C", Side.BUY, 4999, 70, 1_200)
    livro.adicionar("D", Side.SELL, 5001, 90, 1_300)
    livro.adicionar("E", Side.SELL, 5002, 30, 1_400)
    livro.modificar("A", 60, 2_000)
    livro.modificar("B", 200, 2_100)
    livro.recarregar("C", 30, 2_200)
    livro.executar(Side.BUY, 5000, 120, 3_000, broker_agressor="ITAU")
    livro.cancelar("D", 3_100)
    livro.expirar("E", 3_200)
    livro.adicionar("F", Side.BUY, 5000, 40, 3_300)
    livro.executar(Side.BUY, 5000, 500, 4_000)


def test_a_mesma_sequencia_produz_a_mesma_sequencia_de_eventos():
    livro_a = _livro()
    eventos_a = _coletor(livro_a)
    _roteiro(livro_a)

    livro_b = _livro()
    eventos_b = _coletor(livro_b)
    _roteiro(livro_b)

    assert len(eventos_a) == len(eventos_b)
    for ea, eb in zip(eventos_a, eventos_b, strict=True):
        assert ea == eb


def test_a_mesma_sequencia_produz_o_mesmo_estado_final():
    livro_a, livro_b = _livro(), _livro()
    _roteiro(livro_a)
    _roteiro(livro_b)

    for side, price in ((Side.BUY, 5000), (Side.BUY, 4999), (Side.SELL, 5001)):
        assert livro_a.qty_total(side, price) == livro_b.qty_total(side, price)
        assert livro_a.qty_exibida_max(side, price) == livro_b.qty_exibida_max(side, price)
        assert livro_a.n_reposicoes(side, price) == livro_b.n_reposicoes(side, price)
        assert _ids_da_fila(livro_a, side, price) == _ids_da_fila(livro_b, side, price)
    assert livro_a.melhor_bid() == livro_b.melhor_bid()
    assert livro_a.melhor_ask() == livro_b.melhor_ask()
    assert livro_a.n_cruzamentos_detectados == livro_b.n_cruzamentos_detectados


def test_ordem_de_insercao_das_ordens_nao_depende_de_hash():
    """Ids escolhidos para embaralhar o hash — a fila é por TEMPO, não por id."""
    livro = _livro()
    for oid in ("zzz", "aaa", "mmm", "000"):
        livro.adicionar(oid, Side.BUY, BID, 10, 1_000)
    assert _ids_da_fila(livro) == ["zzz", "aaa", "mmm", "000"]


# ===========================================================================
# TAREFA 2 — livro cruzado
# ===========================================================================


def test_livro_normal_nao_acusa_cruzamento():
    livro = _livro()
    livro.adicionar("b1", Side.BUY, 5000, 10, 1_000)
    livro.adicionar("a1", Side.SELL, 5001, 10, 1_100)
    assert livro.esta_cruzado is False
    assert livro.n_cruzamentos_detectados == 0


def test_livro_de_um_lado_so_nunca_esta_cruzado():
    livro = _livro()
    assert livro.esta_cruzado is False
    livro.adicionar("b1", Side.BUY, 5000, 10, 1_000)
    assert livro.esta_cruzado is False
    livro.cancelar("b1", 1_100)
    livro.adicionar("a1", Side.SELL, 4000, 10, 1_200)  # ask MUITO abaixo
    assert livro.esta_cruzado is False  # não há bid para cruzar


def test_livro_cruzado_acusa_conta_e_alerta():
    """bid 10005 com ask 10001 — dado corrompido, não pode passar em silêncio."""
    livro = _livro()
    alertas: list[CruzamentoLivro] = []
    livro.assinar_cruzamento(alertas.append)

    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    assert livro.esta_cruzado is False

    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)

    assert livro.esta_cruzado is True
    assert livro.n_cruzamentos_detectados == 1
    assert len(alertas) == 1
    assert alertas[0].melhor_bid == 10005
    assert alertas[0].melhor_ask == 10001
    assert alertas[0].timestamp_ns == 2_000
    assert alertas[0].symbol == SYM
    assert alertas[0].n_cruzamentos == 1


def test_livro_TRAVADO_bid_igual_ask_tambem_acusa():
    """Spread zero é negócio não reportado — conta como cruzamento."""
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 5000, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 5000, 10, 2_000)
    assert livro.esta_cruzado is True
    assert livro.n_cruzamentos_detectados == 1


def test_cruzamento_NAO_levanta_excecao_e_o_livro_segue_utilizavel():
    """A política é sinalizar, não derrubar a ingestão."""
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)  # não levanta

    eventos = livro.executar(Side.SELL, 10001, 10, 3_000)
    assert [e.order_id for e in eventos] == ["a1"]
    assert livro.melhor_bid() == 10005


def test_contador_e_por_TRANSICAO_nao_por_evento():
    livro = _livro()
    alertas: list[CruzamentoLivro] = []
    livro.assinar_cruzamento(alertas.append)

    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)  # cruza
    livro.adicionar("b2", Side.BUY, 10005, 10, 2_100)  # segue cruzado
    livro.adicionar("b3", Side.BUY, 10006, 10, 2_200)  # segue cruzado, pior ainda

    assert livro.n_cruzamentos_detectados == 1
    assert len(alertas) == 1


def test_descruzar_e_cruzar_de_novo_conta_duas_vezes():
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)
    assert livro.n_cruzamentos_detectados == 1

    livro.cancelar("b1", 3_000)  # descruza
    assert livro.esta_cruzado is False
    assert livro.n_cruzamentos_detectados == 1

    livro.adicionar("b2", Side.BUY, 10007, 10, 4_000)  # cruza de novo
    assert livro.esta_cruzado is True
    assert livro.n_cruzamentos_detectados == 2


# ---------------------------------------------------------------------------
# TAREFA 2b — cruzamento TRANSITÓRIO DE RECONCILIAÇÃO não é feed corrompido
# ---------------------------------------------------------------------------
# `n_cruzamentos_detectados` sempre foi documentado como "dado corrompido,
# evento perdido ou reordenação do feed". Em modo MBP isso era falso: o
# `InferidorMBP` só aplica uma queda de quantidade quando a janela de
# reconciliação expira, enquanto as inserções do lado oposto entram na hora, e
# o livro reconstruído fica cruzado POR CONSTRUÇÃO DA PONTE. O contador estava
# medindo a ponte e chamando aquilo de feed ruim.
#
# A atribuição agora é pela CAUSA: quem alimenta o livro declara, em
# `registrar_liquidez_nao_aplicada`, se ainda deve liquidez ao nível que está
# cruzando.


def _com_defasagem(livro: LivroMBO, defasados: set[tuple[Side, int]]) -> None:
    """Declara ao livro que estes níveis exibem liquidez que a fonte já tirou."""
    livro.registrar_liquidez_nao_aplicada(lambda side, price: (side, price) in defasados)


def test_sem_declaracao_de_defasagem_todo_cruzamento_e_da_fonte():
    """O padrão tem de ser o rigoroso: feed MBO real não cruza.

    Um livro que não sabe de defasagem nenhuma não pode inventar desculpa para
    o que vê — senão a correção do modo MBP viraria uma anistia geral.
    """
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)

    assert livro.esta_cruzado is True
    assert livro.cruzamento_e_transitorio is False
    assert livro.n_cruzamentos_detectados == 1
    assert livro.n_cruzamentos_por_reconciliacao == 0


def test_cruzamento_explicado_por_defasagem_nao_conta_como_feed_corrompido():
    """O caso do modo MBP: o bid que cruza é liquidez que a fonte já tirou."""
    livro = _livro()
    alertas: list[CruzamentoLivro] = []
    livro.assinar_cruzamento(alertas.append)
    # a ponte ainda não aplicou a saída do bid 10005
    _com_defasagem(livro, {(Side.BUY, 10005)})

    livro.adicionar("b1", Side.BUY, 10005, 10, 1_000)
    livro.adicionar("a1", Side.SELL, 10001, 10, 2_000)

    assert livro.esta_cruzado is True, "o fato geométrico continua sendo verdade"
    assert livro.cruzamento_e_transitorio is True
    assert livro.n_cruzamentos_detectados == 0, "isto não é feed corrompido"
    assert alertas == [], "alertar por algo que a ponte desfaz sozinha é ruído"
    # mas NÃO em silêncio: fica registrado no contador que diz a verdade
    assert livro.n_cruzamentos_por_reconciliacao == 1


def test_defasagem_no_lado_errado_nao_explica_o_cruzamento():
    """A pergunta é feita sobre os DOIS topos que cruzam, não sobre o livro todo.

    Sem isto, qualquer defasagem em qualquer nível viraria desculpa para
    qualquer cruzamento — que é a forma preguiçosa de fazer o contador mentir
    na direção oposta.
    """
    livro = _livro()
    _com_defasagem(livro, {(Side.BUY, 9000)})  # nível que não participa do cruzamento

    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)

    assert livro.cruzamento_e_transitorio is False
    assert livro.n_cruzamentos_detectados == 1
    assert livro.n_cruzamentos_por_reconciliacao == 0


def test_cruzamento_que_persiste_depois_da_explicacao_passa_a_acusar():
    """Feed que corrompe DURANTE uma reconciliação não pode ficar escondido.

    É o buraco óbvio de qualquer anistia: se a desculpa da ponte valesse para
    o episódio inteiro, bastaria haver uma queda pendente para o livro parar
    de acusar. Quando a explicação some e o livro continua cruzado, o mesmo
    episódio passa a contar como problema da fonte.
    """
    livro = _livro()
    alertas: list[CruzamentoLivro] = []
    livro.assinar_cruzamento(alertas.append)
    defasados = {(Side.BUY, 10005)}
    _com_defasagem(livro, defasados)

    livro.adicionar("b1", Side.BUY, 10005, 10, 1_000)
    livro.adicionar("a1", Side.SELL, 10001, 10, 2_000)
    assert livro.n_cruzamentos_detectados == 0
    assert livro.n_cruzamentos_por_reconciliacao == 1

    # a ponte resolveu o que devia — e o livro CONTINUA cruzado
    defasados.clear()
    livro.adicionar("a2", Side.SELL, 10001, 5, 3_000)

    assert livro.esta_cruzado is True
    assert livro.cruzamento_e_transitorio is False
    assert livro.n_cruzamentos_detectados == 1
    assert len(alertas) == 1
    assert alertas[0].melhor_bid == 10005 and alertas[0].melhor_ask == 10001


def test_livro_nao_cruzado_nunca_e_transitorio():
    """`cruzamento_e_transitorio` fala do cruzamento ATUAL, não do livro."""
    livro = _livro()
    _com_defasagem(livro, {(Side.BUY, BID), (Side.SELL, ASK)})
    assert livro.cruzamento_e_transitorio is False
    livro.adicionar("b1", Side.BUY, BID, 10, 1_000)
    livro.adicionar("a1", Side.SELL, ASK, 10, 1_100)
    assert livro.esta_cruzado is False
    assert livro.cruzamento_e_transitorio is False


def test_episodio_transitorio_conta_uma_vez_so():
    """O contador de reconciliação é por episódio, como o da fonte."""
    livro = _livro()
    _com_defasagem(livro, {(Side.BUY, 10005), (Side.BUY, 10006)})

    livro.adicionar("b1", Side.BUY, 10005, 10, 1_000)
    livro.adicionar("a1", Side.SELL, 10001, 10, 2_000)
    livro.adicionar("b2", Side.BUY, 10005, 10, 2_100)
    livro.adicionar("b3", Side.BUY, 10006, 10, 2_200)

    assert livro.n_cruzamentos_por_reconciliacao == 1
    assert livro.n_cruzamentos_detectados == 0


def test_execucao_que_resolve_o_cruzamento_reabre_o_latch():
    livro = _livro()
    livro.adicionar("a1", Side.SELL, 10001, 10, 1_000)
    livro.adicionar("b1", Side.BUY, 10005, 10, 2_000)
    assert livro.n_cruzamentos_detectados == 1

    livro.executar(Side.BUY, 10005, 10, 3_000)  # varre o bid cruzado
    assert livro.esta_cruzado is False

    livro.adicionar("b2", Side.BUY, 10009, 10, 4_000)
    assert livro.n_cruzamentos_detectados == 2


class _DictContado(dict):
    """Dicionário de nível que conta os acessos — sonda de complexidade."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n_get = 0
        self.n_varreduras = 0

    def get(self, chave, default=None):
        self.n_get += 1
        return super().get(chave, default)

    def __iter__(self):
        self.n_varreduras += 1
        return super().__iter__()

    def items(self):
        self.n_varreduras += 1
        return super().items()

    def values(self):
        self.n_varreduras += 1
        return super().values()

    def keys(self):
        self.n_varreduras += 1
        return super().keys()


class _DequeQueGrita(list):
    """Fila que denuncia qualquer varredura. Não deve ser tocada por O(1)."""


def _sondar_custo(n_niveis: int) -> tuple[int, int]:
    """Monta um livro com `n_niveis` de cada lado e mede o custo de `esta_cruzado`."""
    livro = _livro()
    for i in range(n_niveis):
        livro.adicionar(f"b{i}", Side.BUY, 5000 - i, 10, 1_000 + i)
        livro.adicionar(f"a{i}", Side.SELL, 5001 + i, 10, 2_000 + i)

    bids = _DictContado(livro._bids)
    asks = _DictContado(livro._asks)
    livro._bids = bids
    livro._asks = asks

    assert livro.esta_cruzado is False
    return bids.n_get + asks.n_get, bids.n_varreduras + asks.n_varreduras


def test_esta_cruzado_nao_e_O_de_n():
    """O custo não pode crescer com a profundidade do livro.

    Sonda determinística (não cronômetro): conta os acessos ao dicionário de
    níveis. 10 níveis por lado e 500 níveis por lado têm de custar o MESMO
    número de acessos, e nenhuma varredura (`items`/`values`/iteração).
    """
    gets_raso, varreduras_raso = _sondar_custo(10)
    gets_fundo, varreduras_fundo = _sondar_custo(500)

    assert varreduras_raso == 0
    assert varreduras_fundo == 0
    assert gets_raso == gets_fundo
    assert gets_fundo <= 4  # dois peeks de heap, um dict.get por lado


def test_esta_cruzado_nao_varre_a_fila_do_nivel():
    """Mesmo com uma fila enorme num nível, a checagem não a percorre."""
    livro = _livro()
    for i in range(2_000):
        livro.adicionar(f"b{i}", Side.BUY, 5000, 1, 1_000 + i)
    livro.adicionar("a1", Side.SELL, 5001, 1, 9_000)

    nivel = livro._bids[5000]
    fila_original = nivel.fila
    nivel.fila = _DequeQueGrita()  # se a checagem varresse, veria uma fila vazia
    try:
        assert livro.esta_cruzado is False
        assert livro.melhor_bid() == 5000
    finally:
        nivel.fila = fila_original


# ---------------------------------------------------------------------------
# `ultima_ordem_ativa` é CAMINHO QUENTE, não inspeção
# ---------------------------------------------------------------------------
# Todo cancelamento inferido pelo `InferidorMBP` sai por aqui, e sai pelo FIM
# da fila. Com remoção preguiçosa só pela frente, o sufixo de mortos crescia a
# cada cancelamento e era revarrido no cancelamento seguinte — O(n²) por nível
# ao longo do pregão. É a MESMA forma do defeito quadrático que a auditoria
# perseguiu em `detectores.py`, `motor/sinais.py` e `inferencia_mbp.py`.


class _FilaContada(deque):
    """Deque que conta quantos itens foram olhados por índice ou iteração."""

    def __init__(self, itens, contador: list[int]) -> None:
        super().__init__(itens)
        self._contador = contador

    def __getitem__(self, i):
        self._contador[0] += 1
        return super().__getitem__(i)

    def __iter__(self):
        contador = self._contador
        for item in super().__iter__():
            contador[0] += 1
            yield item

    def __reversed__(self):
        contador = self._contador
        for item in super().__reversed__():
            contador[0] += 1
            yield item


def _custo_de_cancelar_do_fim(n_ordens: int) -> float:
    """Itens da fila olhados por cancelamento, cancelando sempre o último vivo."""
    livro = _livro()
    ts = 1_000
    for i in range(n_ordens):
        ts += 1
        livro.adicionar(f"o{i}", Side.BUY, BID, 10, ts)

    nivel = livro._bids[BID]
    contador = [0]
    nivel.fila = _FilaContada(nivel.fila, contador)

    for _ in range(n_ordens):
        ts += 1
        ordem = livro.ultima_ordem_ativa(Side.BUY, BID)
        assert ordem is not None
        livro.cancelar(ordem.order_id, ts)
    assert livro.ultima_ordem_ativa(Side.BUY, BID) is None
    return contador[0] / n_ordens


def test_cancelar_pelo_fim_da_fila_e_O_1_amortizado():
    """Esvaziar um nível pelo fim não pode custar o quadrado do tamanho dele.

    Um nível de WDO acumula centenas de ordens sintéticas ao longo do dia. Se
    este teste morrer, a leitura é: a fila voltou a ser podada por uma ponta
    só, e cada cancelamento inferido passou a repassar por cima de todos os
    cancelamentos anteriores daquele preço.
    """
    pequeno = _custo_de_cancelar_do_fim(50)
    grande = _custo_de_cancelar_do_fim(800)

    assert grande <= 2 * pequeno + 2, (
        f"custo por cancelamento cresceu com o tamanho da fila: "
        f"{pequeno:.1f} itens olhados com 50 ordens contra {grande:.1f} com 800. "
        "O sufixo de ordens mortas voltou a ser revarrido."
    )
    assert grande <= 8, f"{grande:.1f} itens olhados por cancelamento — há varredura"


def test_poda_pelo_fim_nao_perde_ordem_viva_nem_muda_a_prioridade():
    """A poda é remoção de morto, não atalho: quem está vivo continua na fila."""
    livro = _livro()
    for i, oid in enumerate(("A", "B", "C")):
        livro.adicionar(oid, Side.BUY, BID, 10, 1_000 + i)

    assert livro.ultima_ordem_ativa(Side.BUY, BID).order_id == "C"
    livro.cancelar("C", 2_000)
    assert livro.ultima_ordem_ativa(Side.BUY, BID).order_id == "B"
    # A e B seguem inteiros, na ordem, com a fila e o total coerentes
    assert _ids_da_fila(livro) == ["A", "B"]
    assert livro.qty_total(Side.BUY, BID) == 20
    # e a frente continua sendo consumida por prioridade, não pela poda
    eventos = livro.executar(Side.BUY, BID, 10, 3_000)
    assert [e.order_id for e in eventos] == ["A"]
    assert _ids_da_fila(livro) == ["B"]


def test_poda_pelo_fim_respeita_ordem_que_perdeu_prioridade_por_aumento():
    """`modificar` com aumento mata a entrada antiga e appenda outra.

    A entrada antiga fica inativa NO MEIO da fila; a nova vai para o fim. A
    poda pelo fim não pode confundir as duas nem devolver a morta.
    """
    livro = _livro()
    livro.adicionar("A", Side.BUY, BID, 10, 1_000)
    livro.adicionar("B", Side.BUY, BID, 10, 1_100)

    livro.modificar("A", 30, 1_200)  # A perde prioridade e vai para o fim

    ultima = livro.ultima_ordem_ativa(Side.BUY, BID)
    assert ultima is not None
    assert ultima.order_id == "A" and ultima.qty_restante == 30
    assert _ids_da_fila(livro) == ["B", "A"]
