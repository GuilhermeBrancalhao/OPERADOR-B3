"""Contrato da ponte MBP -> MBO (`inferencia_mbp.InferidorMBP`).

Até esta suíte existir, 476 linhas rodavam sem uma única asserção: a auditoria
R2 aplicou 4 mutações neste arquivo e as 4 sobreviveram. Entre elas, duas que
não podem passar despercebidas num produto que vende honestidade de leitura:

* **inverter o lado passivo** (uma agressão de compra passaria a consumir o
  BID) — toda atribuição execução×cancelamento sairia espelhada;
* **elevar a confiança de um cancelamento inferido a 1.0** — hipótese vira
  fato em silêncio, apagando a distinção observado×inferido que
  `eventos_mbo.py:12-20` declara ser inviolável.

Por isso os testes daqui afirmam sempre TRÊS coisas juntas sobre cada evento
produzido: o TIPO (execução ou cancelamento), a CONFIANÇA (o quanto aquilo é
chute) e a EVIDÊNCIA (em cima de quê a inferência foi feita). Verificar só o
tipo deixaria a mutação de confiança viva; verificar só a confiança deixaria a
inversão de lado viva.
"""

from __future__ import annotations

from collections import deque

import pytest

from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.microestrutura.eventos_mbo import (
    CONFIANCA_OBSERVADO,
    FonteMicro,
    OrdemEvento,
    TipoEventoOrdem,
)
from fluxopro.microestrutura.inferencia_mbp import (
    UM_MILISSEGUNDO_NS,
    ConfigInferenciaMBP,
    InferidorMBP,
)
from fluxopro.microestrutura.livro_mbo import LivroMBO

SYM = "WDOV26"
OUTRO_SYM = "WINV26"

# Ask de topo e um nível bem fundo, usado para separar "no topo" de "fora do
# topo" sem ambiguidade: 10 ticks de distância contra os 2 do default.
ASK = 5000
ASK_FUNDO = 5010
BID = 4999

JANELA = ConfigInferenciaMBP().janela_reconciliacao_ns
DEPOIS_DA_JANELA = JANELA + 1


# ----------------------------------------------------------------------
# infraestrutura
# ----------------------------------------------------------------------
def _montar(
    config: ConfigInferenciaMBP | None = None,
) -> tuple[InferidorMBP, LivroMBO, list[OrdemEvento]]:
    """Inferidor ligado a um livro limpo, com todos os eventos coletados."""
    livro = LivroMBO(SYM)
    eventos: list[OrdemEvento] = []
    livro.assinar_evento(eventos.append)
    return InferidorMBP(SYM, livro, config), livro, eventos


def _snapshot(
    ts: int,
    bids: list[tuple[int, int]] | None = None,
    asks: list[tuple[int, int]] | None = None,
    symbol: str = SYM,
) -> BookSnapshot:
    return BookSnapshot(
        timestamp_ns=ts,
        symbol=symbol,
        bids=tuple(BookLevel(p, q, 1) for p, q in (bids or [])),
        asks=tuple(BookLevel(p, q, 1) for p, q in (asks or [])),
    )


def _delta(
    ts: int,
    side: Side,
    price: int,
    qty: int,
    action: BookAction = BookAction.UPDATE,
    symbol: str = SYM,
) -> BookDelta:
    return BookDelta(ts, symbol, side, action, price, qty, 0)


def _trade(
    ts: int,
    price: int,
    qty: int,
    agressor: AgressorSide,
    trade_id: str = "T1",
    symbol: str = SYM,
) -> Trade:
    return Trade(ts, symbol, price, qty, agressor, trade_id)


def _tipos(eventos: list[OrdemEvento]) -> list[TipoEventoOrdem]:
    return [e.tipo for e in eventos]


def _so(eventos: list[OrdemEvento], tipo: TipoEventoOrdem) -> list[OrdemEvento]:
    return [e for e in eventos if e.tipo is tipo]


def _unico(eventos: list[OrdemEvento], tipo: TipoEventoOrdem) -> OrdemEvento:
    achados = _so(eventos, tipo)
    assert len(achados) == 1, f"esperava 1 evento {tipo.value}, veio {_tipos(eventos)}"
    return achados[0]


def _nivel_ask_de_150(
    config: ConfigInferenciaMBP | None = None,
) -> tuple[InferidorMBP, LivroMBO, list[OrdemEvento]]:
    """Cenário canônico da docstring do módulo: um nível de ASK com 150.

    Devolve com a lista de eventos já ESVAZIADA — a montagem do nível emite um
    NEW sintético que não interessa aos testes de queda.
    """
    inferidor, livro, eventos = _montar(config)
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    eventos.clear()
    return inferidor, livro, eventos


# ======================================================================
# 1. O CORAÇÃO DO MÓDULO: execução × cancelamento
# ======================================================================
def test_queda_com_negocio_no_mesmo_instante_e_execucao() -> None:
    """150 -> 120 COM trade de 30 no preço: execução, confiança alta.

    É o exemplo canônico das linhas 32-34 da docstring do módulo.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.TRADE)
    assert evento.side is Side.SELL
    assert evento.price == ASK
    assert evento.qty == 30
    assert evento.evidencia["inferido"] == "execucao"
    assert evento.confianca == ConfigInferenciaMBP().confianca_execucao_com_trade_exato
    # e NADA foi atribuído a cancelamento: a queda está inteiramente explicada
    assert _so(eventos, TipoEventoOrdem.CANCEL) == []


def test_queda_sem_negocio_nenhum_e_cancelamento() -> None:
    """A MESMA queda de 150 -> 120, sem trade: cancelamento, não execução.

    Este par de testes é o módulo inteiro. Se os dois passassem com o mesmo
    tipo de evento, a ponte não estaria distinguindo nada.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.side is Side.SELL
    assert evento.price == ASK
    assert evento.qty == 30
    assert evento.evidencia["inferido"] == "cancelamento"
    assert evento.confianca == ConfigInferenciaMBP().confianca_cancelamento_no_topo
    assert _so(eventos, TipoEventoOrdem.TRADE) == []


def test_negocio_que_chega_depois_da_queda_tambem_explica_a_execucao() -> None:
    """A ordem de chegada entre book e tape não pode mudar a conclusão.

    O feed do MT5 é polling: a impressão do negócio pode vir antes ou depois
    da leitura do book que mostra a queda. Os dois caminhos de reconciliação
    (`_conciliar_pendentes_com` e `_conciliar_pendente_com_buffer`) existem
    justamente para isso, e têm de convergir.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_trade(_trade(2_100, ASK, 30, AgressorSide.BUY))
    inferidor.drenar(2_100 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.TRADE)
    assert evento.qty == 30
    assert evento.evidencia["inferido"] == "execucao"
    assert _so(eventos, TipoEventoOrdem.CANCEL) == []


def test_negocio_em_outro_preco_nao_explica_a_queda() -> None:
    """Um trade a 5001 não pode pagar uma queda a 5000.

    Sem esta asserção, a execução seria atribuída ao NÍVEL ERRADO em silêncio
    e o livro sintético divergiria do book agregado.
    """
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK + 1, 80)]))
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, ASK + 1, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.price == ASK
    assert evento.qty == 30
    assert _so(eventos, TipoEventoOrdem.TRADE) == []


def test_execucao_consome_a_frente_da_fila() -> None:
    """Execução respeita prioridade preço-tempo: sai da ordem mais ANTIGA."""
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 100)]))  # INF-1
    inferidor.ao_delta(_delta(1_500, Side.SELL, ASK, 150))  # +50 -> INF-2
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))

    evento = _unico(eventos, TipoEventoOrdem.TRADE)
    assert evento.order_id == "INF-1", "execução tem de consumir a frente da fila"
    detalhe = livro.nivel(Side.SELL, ASK)
    assert detalhe is not None
    assert [(o.order_id, o.qty_restante) for o in detalhe.ordens] == [
        ("INF-1", 70),
        ("INF-2", 50),
    ]


def test_cancelamento_tira_do_fim_da_fila() -> None:
    """Cancelamento inferido sai da ordem mais NOVA — convenção da docstring.

    Sem identidade de ordem, preservar a mais antiga preserva a única
    informação de permanência que o dado agregado oferece (linhas 46-48).
    """
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 100)]))  # INF-1
    inferidor.ao_delta(_delta(1_500, Side.SELL, ASK, 150))  # +50 -> INF-2
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.order_id == "INF-2", "cancelamento tem de sair do fim da fila"
    detalhe = livro.nivel(Side.SELL, ASK)
    assert detalhe is not None
    assert [(o.order_id, o.qty_restante) for o in detalhe.ordens] == [
        ("INF-1", 100),
        ("INF-2", 20),
    ]


def test_cancelamento_maior_que_a_ultima_ordem_percorre_a_fila_para_tras() -> None:
    """Queda que engole a última ordem inteira continua na anterior."""
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 100)]))  # INF-1
    inferidor.ao_delta(_delta(1_500, Side.SELL, ASK, 150))  # +50 -> INF-2
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 70))  # queda de 80
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    cancels = _so(eventos, TipoEventoOrdem.CANCEL)
    assert [(e.order_id, e.qty) for e in cancels] == [("INF-2", 50), ("INF-1", 30)]
    assert livro.qty_total(Side.SELL, ASK) == 70


# ======================================================================
# 2. LADO PASSIVO — a mutação N24, que inverteria toda a leitura
# ======================================================================
def test_lado_passivo_de_agressao_de_compra_e_o_lado_vendedor() -> None:
    """Quem compra a mercado consome ordens de VENDA. Regra mais básica."""
    assert InferidorMBP._lado_passivo(AgressorSide.BUY) is Side.SELL


def test_lado_passivo_de_agressao_de_venda_e_o_lado_comprador() -> None:
    assert InferidorMBP._lado_passivo(AgressorSide.SELL) is Side.BUY


def test_agressor_desconhecido_nao_determina_lado_passivo() -> None:
    """UNKNOWN (leilão, RLP) não diz de que lado a liquidez saiu."""
    assert InferidorMBP._lado_passivo(AgressorSide.UNKNOWN) is None


def test_agressao_de_compra_explica_queda_no_ask_e_nao_no_bid() -> None:
    """O teste que prende a inversão de lado, pelo comportamento observável.

    Duas quedas simultâneas de 30, uma em cada lado, e UM negócio de compra.
    Só a queda do ASK pode ser execução; a do BID tem de sair como
    cancelamento. Com o lado invertido, os dois vereditos trocam de lugar.
    """
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(BID, 150)], asks=[(ASK, 150)]))
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_trade(_trade(2_001, BID, 30, AgressorSide.BUY, "T2"))
    inferidor.ao_delta(_delta(2_001, Side.BUY, BID, 120))
    inferidor.drenar(2_001 + DEPOIS_DA_JANELA)

    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.side is Side.SELL
    assert execucao.price == ASK
    assert execucao.evidencia["agressor"] == "BUY"

    cancelamento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert cancelamento.side is Side.BUY
    assert cancelamento.price == BID


def test_agressao_de_venda_explica_queda_no_bid_e_nao_no_ask() -> None:
    """O espelho do teste anterior — inverter o lado quebra os dois."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(BID, 150)], asks=[(ASK, 150)]))
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, BID, 30, AgressorSide.SELL))
    inferidor.ao_delta(_delta(2_000, Side.BUY, BID, 120))
    inferidor.ao_trade(_trade(2_001, ASK, 30, AgressorSide.SELL, "T2"))
    inferidor.ao_delta(_delta(2_001, Side.SELL, ASK, 120))
    inferidor.drenar(2_001 + DEPOIS_DA_JANELA)

    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.side is Side.BUY
    assert execucao.price == BID
    assert execucao.evidencia["agressor"] == "SELL"

    cancelamento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert cancelamento.side is Side.SELL
    assert cancelamento.price == ASK


def test_agressao_de_compra_sozinha_nao_explica_queda_no_bid() -> None:
    """Caso negativo isolado: mesmo preço, lado errado, sem outra queda por perto."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(BID, 150)]))
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, BID, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.BUY, BID, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.side is Side.BUY
    assert _so(eventos, TipoEventoOrdem.TRADE) == []


# ======================================================================
# 3. CONFIANÇA — hipótese não pode virar fato
# ======================================================================
_CAMPOS_DE_CONFIANCA = (
    "confianca_execucao_com_trade_exato",
    "confianca_execucao_parcial",
    "confianca_execucao_lado_nao_confirmado",
    "confianca_cancelamento_no_topo",
    "confianca_cancelamento_fora_topo",
    "confianca_insercao",
)


@pytest.mark.parametrize("campo", _CAMPOS_DE_CONFIANCA)
def test_nenhuma_confianca_de_fabrica_alcanca_a_de_um_fato_observado(campo: str) -> None:
    """Toda confiança configurável da ponte tem de ficar ABAIXO de 1.0.

    Este é o teste que falha se alguém elevar qualquer uma delas a 1.0. Não é
    preciosismo numérico: `CONFIANCA_OBSERVADO == 1.0` é reservado a evento
    lido de feed MBO real (`eventos_mbo.py:33-34`). Um evento desta ponte com
    confiança 1.0 seria uma hipótese vendida como leitura — exatamente o que
    a docstring do módulo (linha 26) promete nunca fazer.
    """
    valor = getattr(ConfigInferenciaMBP(), campo)
    assert 0.0 < valor < CONFIANCA_OBSERVADO, (
        f"{campo}={valor}: confiança de evento INFERIDO não pode alcançar "
        f"CONFIANCA_OBSERVADO ({CONFIANCA_OBSERVADO})"
    )


def test_escala_de_confianca_respeita_a_ordem_declarada_na_docstring() -> None:
    """A ordem entre as confianças É o modelo, e tem de ser a documentada.

    * casamento exato vale mais que casamento parcial (menos ambiguidade);
    * cancelamento FORA do topo vale mais que no topo — longe do melhor preço
      nenhum negócio poderia ter ocorrido, então "sem trade" é prova quase
      direta (linhas 35-40 da docstring).
    """
    config = ConfigInferenciaMBP()
    assert config.confianca_execucao_com_trade_exato > config.confianca_execucao_parcial
    assert config.confianca_cancelamento_fora_topo > config.confianca_cancelamento_no_topo
    assert (
        config.confianca_execucao_lado_nao_confirmado < config.confianca_execucao_parcial
    ), "execução sem lado passivo confirmado não pode valer o mesmo que uma com lado"


def test_todo_evento_da_ponte_sai_marcado_como_inferido_e_sem_certeza() -> None:
    """Varredura de fim a fim: nenhum evento escapa marcado como fato.

    Uma sessão com inserção, aumento, execução exata, execução parcial,
    cancelamento no topo e cancelamento fora do topo — todos os caminhos que
    emitem evento — e a mesma asserção sobre cada um.
    """
    inferidor, _, eventos = _montar()
    ts = 1_000
    inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, 100)], asks=[(ASK, 10), (ASK_FUNDO, 150)]))
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_delta(_delta(ts, Side.SELL, ASK_FUNDO, 200))  # aumento
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_trade(_trade(ts, ASK, 10, AgressorSide.BUY, "T1"))
    inferidor.ao_delta(_delta(ts, Side.SELL, ASK, 0, BookAction.DELETE))  # execução exata
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_trade(_trade(ts, BID, 10, AgressorSide.SELL, "T2"))
    inferidor.ao_delta(_delta(ts, Side.BUY, BID, 60))  # execução parcial (queda 40)
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_delta(_delta(ts, Side.SELL, ASK_FUNDO, 150))  # cancelamento fora do topo
    inferidor.drenar(ts + DEPOIS_DA_JANELA)

    assert len(eventos) >= 6, f"esperava a sessão inteira, veio {_tipos(eventos)}"
    for evento in eventos:
        assert evento.fonte is FonteMicro.MBP_INFERIDO, (
            f"evento {evento.tipo.value} saiu com fonte {evento.fonte.value}: "
            "dado agregado NUNCA produz evento observado"
        )
        assert evento.confianca < CONFIANCA_OBSERVADO, (
            f"evento {evento.tipo.value} saiu com confianca={evento.confianca}: "
            "hipótese apresentada como fato"
        )
        assert evento.evidencia, "evento inferido sem evidência é inauditável"

    # e os quatro vereditos distintos apareceram de verdade nesta sessão
    config = ConfigInferenciaMBP()
    confiancas = {e.confianca for e in eventos}
    assert config.confianca_insercao in confiancas
    assert config.confianca_execucao_com_trade_exato in confiancas
    assert config.confianca_execucao_parcial in confiancas
    assert config.confianca_cancelamento_fora_topo in confiancas


def test_cancelamento_fora_do_topo_vale_mais_que_no_topo() -> None:
    """A distância do topo muda o veredito de confiança, e é auditável.

    Duas quedas idênticas de 30, uma no melhor ask e outra 10 ticks acima.
    """
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK_FUNDO, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK_FUNDO, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    config = ConfigInferenciaMBP()
    por_preco = {e.price: e for e in _so(eventos, TipoEventoOrdem.CANCEL)}
    assert set(por_preco) == {ASK, ASK_FUNDO}

    no_topo = por_preco[ASK]
    assert no_topo.confianca == config.confianca_cancelamento_no_topo
    assert no_topo.evidencia["nivel_negociavel"] is True
    assert no_topo.evidencia["distancia_do_topo_ticks"] == 0

    fora = por_preco[ASK_FUNDO]
    assert fora.confianca == config.confianca_cancelamento_fora_topo
    assert fora.evidencia["nivel_negociavel"] is False
    assert fora.evidencia["distancia_do_topo_ticks"] == ASK_FUNDO - ASK
    assert fora.confianca > no_topo.confianca


def test_distancia_do_topo_e_medida_antes_de_aplicar_a_queda() -> None:
    """O nível que ERA o topo e zerou continua sendo julgado como topo.

    Medir depois o faria parecer afastado do (novo) melhor preço e inflaria a
    confiança do cancelamento — o comentário das linhas 272-274 do módulo.
    """
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK_FUNDO, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 0, BookAction.DELETE))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.evidencia["distancia_do_topo_ticks"] == 0
    assert evento.confianca == ConfigInferenciaMBP().confianca_cancelamento_no_topo


def test_confianca_configurada_e_a_que_chega_no_evento() -> None:
    """Os limiares não estão cravados no código: config própria manda."""
    config = ConfigInferenciaMBP(
        confianca_execucao_com_trade_exato=0.42,
        confianca_cancelamento_no_topo=0.11,
        confianca_insercao=0.33,
    )
    inferidor, _, eventos = _montar(config)
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    assert _unico(eventos, TipoEventoOrdem.NEW).confianca == 0.33
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    assert _unico(eventos, TipoEventoOrdem.TRADE).confianca == 0.42
    eventos.clear()

    inferidor.ao_delta(_delta(3_000, Side.SELL, ASK, 100))
    inferidor.drenar(3_000 + DEPOIS_DA_JANELA)
    assert _unico(eventos, TipoEventoOrdem.CANCEL).confianca == 0.11


def test_execucao_com_agressor_desconhecido_vale_menos_que_com_lado_confirmado() -> None:
    """DEFEITO CORRIGIDO — agressor `UNKNOWN` recebia a confiança MÁXIMA.

    A reconciliação tem duas pernas: mesmo preço e mesmo lado passivo. Com
    `AgressorSide.UNKNOWN` (leilão de abertura/fechamento, e o RLP que
    anonimiza parte do volume de WDO/WIN na B3) a segunda perna simplesmente
    não acontece — `_casa` deixa passar só pelo preço. Antes da correção esse
    casamento saía com 0.90, exatamente a mesma confiança de uma execução com
    o lado do agressor confirmado. Duas hipóteses de força diferente com o
    mesmo rótulo é o começo de vender inferência como leitura.
    """
    config = ConfigInferenciaMBP()

    inferidor, _, eventos = _nivel_ask_de_150()
    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.UNKNOWN))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    anonimo = _unico(eventos, TipoEventoOrdem.TRADE)

    inferidor2, _, eventos2 = _nivel_ask_de_150()
    inferidor2.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor2.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    confirmado = _unico(eventos2, TipoEventoOrdem.TRADE)

    # a queda continua sendo atribuída a execução — o preço é evidência forte
    assert anonimo.qty == confirmado.qty == 30
    assert anonimo.evidencia["inferido"] == "execucao"
    # ...mas não com a mesma força
    assert anonimo.confianca == config.confianca_execucao_lado_nao_confirmado
    assert anonimo.confianca < confirmado.confianca
    assert anonimo.evidencia["lado_passivo_confirmado"] is False
    assert confirmado.evidencia["lado_passivo_confirmado"] is True


def test_lado_nao_confirmado_e_teto_e_nunca_eleva_a_confianca() -> None:
    """O ajuste é `min`, não atribuição: configuração frouxa não pode inflar.

    Se o campo fosse aplicado como valor fixo, configurá-lo acima da confiança
    de casamento parcial faria um casamento AMBÍGUO E SEM LADO valer mais que
    um casamento ambíguo com lado — o inverso do que se quer.
    """
    config = ConfigInferenciaMBP(confianca_execucao_lado_nao_confirmado=0.99)
    inferidor, _, eventos = _nivel_ask_de_150(config)

    inferidor.ao_trade(_trade(2_000, ASK, 10, AgressorSide.UNKNOWN))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))  # queda 30 > trade 10

    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.confianca == config.confianca_execucao_parcial
    assert execucao.confianca < 0.99


def test_cancelamento_de_queda_que_negociou_nao_alega_que_negocio_era_impossivel() -> None:
    """DEFEITO CORRIGIDO — evidência que os próprios dados do módulo desmentiam.

    Nível 10 ticks acima do melhor ask (portanto "fora do topo"), queda de 30,
    com um negócio de 10 impresso NAQUELE MESMO PREÇO. O saldo de 20 saía como
    cancelamento com confiança 0.90 e a ressalva "fora do topo nao havia como
    negociar" — enquanto o próprio módulo acabara de atribuir 10 contratos a
    uma execução ali. A premissa que sustenta a confiança alta estava
    falsificada pela evidência do evento anterior.
    """
    config = ConfigInferenciaMBP()
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 10), (ASK_FUNDO, 150)]))
    eventos.clear()

    inferidor.ao_trade(_trade(2_000, ASK_FUNDO, 10, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK_FUNDO, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.price == ASK_FUNDO and execucao.qty == 10

    cancelamento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert cancelamento.qty == 20
    assert cancelamento.evidencia["distancia_do_topo_ticks"] == ASK_FUNDO - ASK
    assert cancelamento.evidencia["negocio_observado_no_preco"] is True
    assert cancelamento.evidencia["qty_ja_atribuida_a_execucao"] == 10
    assert cancelamento.evidencia["nivel_negociavel"] is True
    assert "nao havia como negociar" not in str(cancelamento.evidencia["ressalva"])
    assert cancelamento.confianca == config.confianca_cancelamento_no_topo
    assert cancelamento.confianca < config.confianca_cancelamento_fora_topo


def test_queda_fora_do_topo_que_nunca_negociou_mantem_a_confianca_alta() -> None:
    """O contraponto: a correção acima não pode apagar o ramo legítimo."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 10), (ASK_FUNDO, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK_FUNDO, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    cancelamento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert cancelamento.evidencia["negocio_observado_no_preco"] is False
    assert cancelamento.evidencia["qty_ja_atribuida_a_execucao"] == 0
    assert cancelamento.confianca == ConfigInferenciaMBP().confianca_cancelamento_fora_topo


# ======================================================================
# 4. EVIDÊNCIA — a inferência tem de ser auditável
# ======================================================================
def test_evidencia_de_execucao_diz_em_cima_de_que_negocio_foi_decidida() -> None:
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY, "T-XYZ"))
    inferidor.ao_delta(_delta(2_500, Side.SELL, ASK, 120))

    evidencia = _unico(eventos, TipoEventoOrdem.TRADE).evidencia
    assert evidencia["observado"] == "queda_de_qty_no_nivel_e_negocio_no_mesmo_preco"
    assert evidencia["inferido"] == "execucao"
    assert evidencia["queda_qty"] == 30
    assert evidencia["trade_id"] == "T-XYZ"
    assert evidencia["trade_qty_usada"] == 30
    assert evidencia["agressor"] == AgressorSide.BUY.value
    assert evidencia["lado_passivo_confirmado"] is True
    assert evidencia["casamento_exato"] is True
    assert evidencia["atraso_ns"] == 500
    assert evidencia["janela_ns"] == JANELA


def test_evidencia_de_cancelamento_registra_a_ressalva_certa_de_cada_regiao() -> None:
    """A ressalva não pode ser genérica: ela é o argumento da confiança."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK_FUNDO, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK_FUNDO, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    por_preco = {e.price: e.evidencia for e in _so(eventos, TipoEventoOrdem.CANCEL)}
    for evidencia in por_preco.values():
        assert evidencia["observado"] == "queda_de_qty_no_nivel_sem_negocio_no_preco"
        assert evidencia["inferido"] == "cancelamento"
        assert evidencia["queda_qty"] == 30
        assert evidencia["qty_atribuida"] == 30
        assert evidencia["janela_ns"] == JANELA

    assert "atraso de impressao" in str(por_preco[ASK]["ressalva"])
    assert "nao havia como negociar" in str(por_preco[ASK_FUNDO]["ressalva"])


def test_evidencia_de_insercao_admite_que_a_decomposicao_e_desconhecida() -> None:
    """150 pode ser uma ordem ou dez — a ponte modela uma e DIZ que modelou."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))

    evento = _unico(eventos, TipoEventoOrdem.NEW)
    assert evento.qty == 150
    assert evento.evidencia["observado"] == "aumento_de_qty_no_nivel"
    assert evento.evidencia["qty_anterior"] == 0
    assert evento.evidencia["qty_nova"] == 150
    assert evento.evidencia["inferido"] == "uma_ordem_nova_sintetica"
    assert "decomposicao e desconhecida" in str(evento.evidencia["ressalva"])


def test_evidencia_de_aumento_preserva_a_qty_anterior_do_nivel() -> None:
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 200))

    evento = _unico(eventos, TipoEventoOrdem.NEW)
    assert evento.qty == 50
    assert evento.evidencia["qty_anterior"] == 150
    assert evento.evidencia["qty_nova"] == 200


def test_evidencia_e_so_de_primitivos_e_portanto_serializavel() -> None:
    """`OrdemEvento` promete evidência serializável e comparável em teste."""
    inferidor, _, eventos = _montar()
    ts = 1_000
    inferidor.ao_snapshot(_snapshot(ts, asks=[(ASK, 150), (ASK_FUNDO, 150)]))
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_trade(_trade(ts, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(ts, Side.SELL, ASK, 120))
    ts += UM_MILISSEGUNDO_NS
    inferidor.ao_delta(_delta(ts, Side.SELL, ASK_FUNDO, 100))
    inferidor.drenar(ts + DEPOIS_DA_JANELA)

    assert eventos
    for evento in eventos:
        for chave, valor in evento.evidencia.items():
            assert isinstance(chave, str)
            assert isinstance(valor, (int, float, str, bool)), (
                f"evidencia[{chave!r}] = {valor!r} não é primitivo"
            )


# ======================================================================
# 5. CASOS AMBÍGUOS — o que a ponte faz quando o dado não decide
# ======================================================================
def test_queda_maior_que_o_negocio_divide_execucao_e_cancelamento() -> None:
    """Queda de 30 com trade de 10: 10 de execução + 20 de cancelamento.

    É a regra das linhas 30-31 da docstring — "execução até o volume
    negociado; o que sobra é cancelamento" — e a confiança da parte executada
    CAI para a de casamento parcial, porque a queda não ficou explicada.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 10, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    config = ConfigInferenciaMBP()
    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.qty == 10
    assert execucao.confianca == config.confianca_execucao_parcial
    assert execucao.confianca < config.confianca_execucao_com_trade_exato
    assert execucao.evidencia["casamento_exato"] is False
    assert execucao.evidencia["queda_qty"] == 30

    cancelamento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert cancelamento.qty == 20
    assert cancelamento.evidencia["queda_qty"] == 30
    assert cancelamento.evidencia["qty_atribuida"] == 20


def test_negocio_maior_que_a_queda_nao_e_casamento_exato() -> None:
    """Trade de 30 contra queda de 10: sobra volume sem explicação no book.

    Pode ser iceberg, pode ser reposição instantânea, pode ser leitura de
    book perdida entre dois pollings. A ponte não sabe — e por não saber, a
    execução sai com a confiança de casamento PARCIAL, não a de exato.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 140))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    execucao = _unico(eventos, TipoEventoOrdem.TRADE)
    assert execucao.qty == 10
    assert execucao.confianca == ConfigInferenciaMBP().confianca_execucao_parcial
    assert execucao.evidencia["casamento_exato"] is False
    # os 20 restantes do negócio não inventam cancelamento nenhum
    assert _so(eventos, TipoEventoOrdem.CANCEL) == []


def test_o_mesmo_negocio_nao_paga_duas_quedas_alem_do_seu_tamanho() -> None:
    """Volume só pode ser consumido uma vez — senão a ponte fabrica execução."""
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_100, Side.SELL, ASK, 130))  # queda 20
    inferidor.ao_delta(_delta(2_200, Side.SELL, ASK, 110))  # queda 20
    inferidor.drenar(2_200 + DEPOIS_DA_JANELA)

    execucoes = _so(eventos, TipoEventoOrdem.TRADE)
    assert sum(e.qty for e in execucoes) == 30, "o negócio de 30 virou mais de 30"
    cancelamentos = _so(eventos, TipoEventoOrdem.CANCEL)
    assert sum(e.qty for e in cancelamentos) == 10
    assert sum(e.qty for e in execucoes) + sum(e.qty for e in cancelamentos) == 40


def test_dois_negocios_somam_para_explicar_uma_queda_so() -> None:
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 10, AgressorSide.BUY, "T1"))
    inferidor.ao_trade(_trade(2_100, ASK, 20, AgressorSide.BUY, "T2"))
    inferidor.ao_delta(_delta(2_200, Side.SELL, ASK, 120))
    inferidor.drenar(2_200 + DEPOIS_DA_JANELA)

    execucoes = _so(eventos, TipoEventoOrdem.TRADE)
    assert [e.qty for e in execucoes] == [10, 20]
    assert [e.evidencia["trade_id"] for e in execucoes] == ["T1", "T2"]
    assert _so(eventos, TipoEventoOrdem.CANCEL) == []


def test_toda_queda_e_integralmente_atribuida_a_execucao_ou_cancelamento() -> None:
    """Invariante de conservação: nada de liquidez some sem veredito.

    Uma queda parcialmente explicada por negócio é o caso onde um rateio mal
    feito esconderia contratos — aqui a soma dos dois vereditos tem de bater
    com a queda observada, evento a evento.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 7, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 111))  # queda de 39
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    atribuido = sum(e.qty for e in eventos if e.tipo in (TipoEventoOrdem.TRADE, TipoEventoOrdem.CANCEL))
    assert atribuido == 39


# ======================================================================
# 6. NÍVEL NOVO / NÍVEL QUE SOME
# ======================================================================
def test_preco_que_aparece_do_nada_vira_ordem_sintetica() -> None:
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK + 5, 40, BookAction.ADD))

    evento = _unico(eventos, TipoEventoOrdem.NEW)
    assert evento.price == ASK + 5
    assert evento.qty == 40
    assert livro.qty_total(Side.SELL, ASK + 5) == 40


def test_preco_que_some_do_snapshot_e_tratado_como_ida_a_zero() -> None:
    """Snapshot é o book COMPLETO: nível ausente significa nível zerado."""
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK_FUNDO, 80)]))
    eventos.clear()

    inferidor.ao_snapshot(_snapshot(2_000, asks=[(ASK, 150)]))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.price == ASK_FUNDO
    assert evento.qty == 80
    assert livro.qty_total(Side.SELL, ASK_FUNDO) == 0


def test_delta_delete_zera_o_nivel_qualquer_que_seja_a_qty_do_evento() -> None:
    """DELETE manda mais que o campo `qty` — o nível vai a zero, ponto."""
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    eventos.clear()

    inferidor.ao_delta(BookDelta(2_000, SYM, Side.SELL, BookAction.DELETE, ASK, 999, 0))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.qty == 150
    assert livro.qty_total(Side.SELL, ASK) == 0
    assert inferidor.melhor_ask() is None


def test_nivel_esvaziado_e_repovoado_volta_a_ser_topo() -> None:
    """Remoção preguiçosa do heap não pode exilar um preço para sempre."""
    inferidor, _, _ = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(BID - 1, 50), (BID, 200)]))
    assert inferidor.melhor_bid() == BID

    inferidor.ao_delta(_delta(2_000, Side.BUY, BID, 0, BookAction.DELETE))
    assert inferidor.melhor_bid() == BID - 1

    inferidor.ao_delta(_delta(3_000, Side.BUY, BID, 70, BookAction.ADD))
    assert inferidor.melhor_bid() == BID


def test_leitura_repetida_do_mesmo_nivel_nao_produz_evento() -> None:
    """Polling do MT5 repete o book o tempo todo; repetição não é evento."""
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    eventos.clear()

    for ts in (2_000, 3_000, 4_000):
        inferidor.ao_snapshot(_snapshot(ts, asks=[(ASK, 150)]))
    inferidor.drenar(4_000 + DEPOIS_DA_JANELA)

    assert eventos == []


def test_melhor_bid_e_ask_saem_do_dado_agregado() -> None:
    inferidor, _, _ = _montar()
    assert inferidor.melhor_bid() is None
    assert inferidor.melhor_ask() is None

    inferidor.ao_snapshot(
        _snapshot(1_000, bids=[(BID - 2, 10), (BID, 200)], asks=[(ASK, 150), (ASK_FUNDO, 80)])
    )
    assert inferidor.melhor_bid() == BID
    assert inferidor.melhor_ask() == ASK


# ======================================================================
# 7. FLUXOS DESCASADOS: trade sem book, book sem trade
# ======================================================================
def test_negocio_sem_book_correspondente_nao_inventa_evento() -> None:
    """Tape sem book (ou preço que a ponte nunca viu) não fabrica ordem."""
    inferidor, livro, eventos = _montar()

    inferidor.ao_trade(_trade(1_000, ASK, 30, AgressorSide.BUY))
    inferidor.drenar(1_000 + DEPOIS_DA_JANELA)

    assert eventos == []
    assert livro.qty_total(Side.SELL, ASK) == 0


def test_negocio_nao_conciliado_expira_em_silencio() -> None:
    """Depois da janela o negócio sai do buffer e não explica queda futura."""
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)
    assert eventos == []

    # a queda vem TARDE demais: o negócio já expirou, então é cancelamento
    tarde = 2_000 + DEPOIS_DA_JANELA
    inferidor.ao_delta(_delta(tarde, Side.SELL, ASK, 120))
    inferidor.drenar(tarde + DEPOIS_DA_JANELA)

    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.qty == 30


def test_mudanca_de_book_sem_negocio_nenhum_vira_cancelamento_e_insercao() -> None:
    """Book que respira sozinho: só inserção e cancelamento, zero execução."""
    inferidor, _, eventos = _montar()
    ts = 1_000
    inferidor.ao_snapshot(_snapshot(ts, asks=[(ASK, 100)]))
    for nova_qty in (150, 90, 200, 40):
        ts += UM_MILISSEGUNDO_NS
        inferidor.ao_delta(_delta(ts, Side.SELL, ASK, nova_qty))
    inferidor.drenar(ts + DEPOIS_DA_JANELA)

    assert _so(eventos, TipoEventoOrdem.TRADE) == []
    assert _tipos(eventos).count(TipoEventoOrdem.NEW) == 3  # 100, +50, +110
    assert _so(eventos, TipoEventoOrdem.CANCEL) != []


# ======================================================================
# 8. JANELA DE RECONCILIAÇÃO E RELÓGIO
# ======================================================================
def test_pendencia_nao_e_resolvida_enquanto_a_janela_nao_expira() -> None:
    """A resolução no topo é DIFERIDA — é o que a docstring promete (l. 38-40).

    Resolver na hora transformaria em cancelamento todo negócio cuja
    impressão chegou alguns milissegundos depois do book.
    """
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + JANELA)  # exatamente na janela: ainda não

    assert eventos == []


def test_pendencia_vira_cancelamento_assim_que_a_janela_expira() -> None:
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + JANELA)
    assert eventos == []

    inferidor.drenar(2_000 + JANELA + 1)
    evento = _unico(eventos, TipoEventoOrdem.CANCEL)
    assert evento.qty == 30
    assert evento.timestamp_ns == 2_000, "o cancelamento é datado na QUEDA, não na expiração"


def test_negocio_dentro_da_janela_ainda_salva_a_queda_de_virar_cancelamento() -> None:
    """O ponto exato do trade-off descrito no `ConfigInferenciaMBP`."""
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_trade(_trade(2_000 + JANELA - 1, ASK, 30, AgressorSide.BUY))
    inferidor.drenar(2_000 + 10 * JANELA)

    assert _tipos(eventos) == [TipoEventoOrdem.TRADE]


def test_janela_curta_demais_transforma_execucao_em_cancelamento() -> None:
    """O aviso do `ConfigInferenciaMBP` é real e observável, não decorativo."""
    inferidor, _, eventos = _nivel_ask_de_150(ConfigInferenciaMBP(janela_reconciliacao_ns=1))

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.ao_trade(_trade(2_100, ASK, 30, AgressorSide.BUY))

    assert _tipos(eventos) == [TipoEventoOrdem.CANCEL]


def test_evento_atrasado_nao_faz_o_relogio_retroceder() -> None:
    """Feed fora de ordem não pode ressuscitar a janela de reconciliação.

    Com o relógio já em 5 s, uma queda datada em 1 s está morta na chegada: a
    próxima leitura (1,1 s) tem de resolvê-la. Se o relógio andasse para trás,
    a pendência ficaria viva e o cancelamento sumiria.
    """
    um_segundo = 1_000_000_000
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150), (ASK_FUNDO, 80)]))
    inferidor.drenar(5 * um_segundo)
    eventos.clear()

    inferidor.ao_delta(_delta(um_segundo, Side.SELL, ASK, 120))
    inferidor.ao_delta(_delta(um_segundo + um_segundo // 10, Side.SELL, ASK_FUNDO, 70))

    cancelamentos = _so(eventos, TipoEventoOrdem.CANCEL)
    assert [e.price for e in cancelamentos] == [ASK]
    assert cancelamentos[0].qty == 30


def test_drenar_nao_inventa_evento_quando_nao_ha_pendencia() -> None:
    inferidor, _, eventos = _nivel_ask_de_150()
    for ts in (10**9, 10**10, 10**11):
        inferidor.drenar(ts)
    assert eventos == []


# ======================================================================
# 9. SÍMBOLO, DETERMINISMO E INVARIANTES DE ESTADO
# ======================================================================
def test_evento_de_outro_simbolo_e_ignorado_nas_tres_entradas() -> None:
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)], symbol=OUTRO_SYM))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120, symbol=OUTRO_SYM))
    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY, symbol=OUTRO_SYM))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    assert eventos == []
    assert livro.qty_total(Side.SELL, ASK) == 0
    assert inferidor.melhor_ask() is None


def test_negocio_de_outro_simbolo_nao_explica_queda_do_nosso() -> None:
    """O filtro de símbolo é o que impede o tape do WIN de pagar book do WDO."""
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY, symbol=OUTRO_SYM))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)

    assert _tipos(eventos) == [TipoEventoOrdem.CANCEL]


def _sessao_sintetica() -> list[tuple[object, ...]]:
    """Sessão longa e variada, reduzida a uma assinatura comparável."""
    inferidor, _, eventos = _montar()
    ts = 1_000
    inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, 120)], asks=[(ASK, 150), (ASK_FUNDO, 90)]))
    for i in range(120):
        ts += 7 * UM_MILISSEGUNDO_NS
        qty_ask = 150 - (i % 9) * 15
        qty_bid = 120 + (i % 5) * 20
        inferidor.ao_snapshot(
            _snapshot(ts, bids=[(BID, qty_bid)], asks=[(ASK, qty_ask), (ASK_FUNDO, 90)])
        )
        if i % 3 == 0:
            inferidor.ao_trade(_trade(ts, ASK, 10 + i % 4, AgressorSide.BUY, f"TB{i}"))
        if i % 4 == 0:
            inferidor.ao_trade(_trade(ts, BID, 5 + i % 3, AgressorSide.SELL, f"TS{i}"))
        if i % 11 == 0:
            inferidor.ao_delta(_delta(ts, Side.SELL, ASK_FUNDO, 60 + i % 7))
        if i % 13 == 0:
            inferidor.ao_trade(_trade(ts, ASK, 8, AgressorSide.UNKNOWN, f"TU{i}"))
    inferidor.drenar(ts + 10 * JANELA)

    return [
        (
            e.timestamp_ns,
            e.tipo.value,
            e.side.value,
            e.price,
            e.qty,
            e.order_id,
            e.fonte.value,
            e.confianca,
            tuple(sorted((k, str(v)) for k, v in e.evidencia.items())),
        )
        for e in eventos
    ]


def test_mesma_sequencia_de_snapshots_produz_a_mesma_sequencia_de_eventos() -> None:
    """Determinismo total: nenhum `set`, `hash` ou relógio de parede no meio.

    A varredura de níveis que sumiram do snapshot passa por um `set` de
    níveis vistos; se a ORDEM dela dependesse desse `set`, a sequência de
    `order_id` sintéticos mudaria entre execuções e nenhum replay seria
    reproduzível.
    """
    primeira = _sessao_sintetica()
    segunda = _sessao_sintetica()

    assert primeira, "a sessão sintética não produziu evento nenhum"
    assert primeira == segunda


def test_sessao_longa_nunca_publica_evento_com_cara_de_fato() -> None:
    """A mesma sessão do teste de determinismo, olhada pela lente da honestidade."""
    for evento in _sessao_sintetica():
        fonte, confianca = evento[6], evento[7]
        assert fonte == FonteMicro.MBP_INFERIDO.value
        assert isinstance(confianca, float) and confianca < CONFIANCA_OBSERVADO


def test_quantidade_do_livro_sintetico_segue_o_book_agregado() -> None:
    """Invariante de fechamento: o livro reconstruído não pode derivar do MBP.

    Se execução e cancelamento não fossem atribuídos exatamente à queda
    observada, este total divergiria em silêncio — e todo detector a jusante
    passaria a ler um livro que não existe.
    """
    inferidor, livro, _ = _montar()
    ts = 1_000
    inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, 120)], asks=[(ASK, 150)]))
    for i in range(60):
        # passo maior que a janela: cada leitura chega com o veredito da
        # anterior já fechado, que é a condição em que o livro tem de bater
        ts += 2 * JANELA
        qty_ask = 150 - (i % 7) * 20
        qty_bid = 120 - (i % 4) * 25
        inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, qty_bid)], asks=[(ASK, qty_ask)]))
        if i % 2 == 0:
            inferidor.ao_trade(_trade(ts, ASK, 10, AgressorSide.BUY, f"T{i}"))
        inferidor.drenar(ts + DEPOIS_DA_JANELA)

        assert livro.qty_total(Side.SELL, ASK) == qty_ask, f"divergiu no passo {i}"
        assert livro.qty_total(Side.BUY, BID) == qty_bid, f"divergiu no passo {i}"


def test_livro_sintetico_so_absorve_a_queda_depois_do_veredito() -> None:
    """Contrapartida honesta do teste acima: o livro ATRASA de propósito.

    Enquanto a queda está pendente de reconciliação, a liquidez continua no
    livro sintético — não há evento a emitir porque ainda não se sabe SE foi
    execução ou cancelamento, e emitir o veredito errado para depois corrigir
    seria pior que atrasar. Quem lê o livro dentro da janela vê o estado
    anterior à queda.
    """
    inferidor, livro, eventos = _nivel_ask_de_150()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    assert livro.qty_total(Side.SELL, ASK) == 150, "veredito ainda não saiu"
    assert eventos == []

    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)
    assert livro.qty_total(Side.SELL, ASK) == 120
    assert _tipos(eventos) == [TipoEventoOrdem.CANCEL]


def test_indice_por_nivel_nao_acumula_lixo_ao_longo_da_sessao() -> None:
    """O índice de reconciliação tem de ser podado, não só consultado.

    `_pendentes_por_nivel` e `_trades_por_nivel` são o que faz o casamento
    custar o nível em vez da janela inteira. Um bucket que nunca é esvaziado
    reintroduz a varredura que eles eliminam — e num pregão de WDO, que cobre
    centenas de ticks, viraria vazamento de memória proporcional à sessão.
    """
    inferidor, _, _ = _montar()
    ts = 1_000
    # 300 preços distintos, cada um nascendo, caindo sem negócio e sumindo
    for i in range(300):
        preco = ASK + i
        ts += UM_MILISSEGUNDO_NS
        inferidor.ao_delta(_delta(ts, Side.SELL, preco, 100, BookAction.ADD))
        ts += UM_MILISSEGUNDO_NS
        inferidor.ao_delta(_delta(ts, Side.SELL, preco, 40))
        inferidor.ao_trade(_trade(ts, preco, 5, AgressorSide.BUY, f"T{i}"))

    # dentro da janela o índice guarda só o que ainda pode casar
    assert len(inferidor._pendentes_por_nivel) <= len(inferidor._pendentes) + 1
    assert len(inferidor._trades_por_nivel) <= len(inferidor._trades) + 1

    inferidor.drenar(ts + DEPOIS_DA_JANELA)
    assert inferidor._pendentes_por_nivel == {}, "bucket de queda ficou pendurado"
    assert inferidor._trades_por_nivel == {}, "bucket de negócio ficou pendurado"
    assert list(inferidor._pendentes) == []


def test_ponte_alimenta_o_livro_que_os_detectores_leem() -> None:
    """A promessa da classe: detectores consomem o MESMO `OrdemEvento`.

    A diferença entre mundo MBO e mundo MBP aparece em `fonte`/`confianca`,
    nunca na FORMA do dado — é isso que permite ao resto do sistema ignorar
    de que feed veio.
    """
    inferidor, livro, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, asks=[(ASK, 150)]))
    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))

    assert all(isinstance(e, OrdemEvento) for e in eventos)
    assert livro.melhor_ask() == ASK
    assert livro.qty_total(Side.SELL, ASK) == 120
    detalhe = livro.nivel(Side.SELL, ASK)
    assert detalhe is not None and detalhe.n_ordens == 1


# ======================================================================
# 11. CUSTO NO EIXO QUE DOMINA — a taxa do tape com preço cravado
# ======================================================================
# O mesmo defeito quadrático já mudou de casa três vezes (`detectores.py`,
# `motor/sinais.py`, e daqui). Na terceira, a correção anterior mediu o eixo
# ERRADO — a largura do book — e publicou uma curva plana, o que desarmou a
# revisão seguinte. Estes testes prendem o eixo certo: a TAXA do tape com
# preço concentrado, que é o regime real do WDO (spread de 1 tick, tudo no
# mesmo bucket).
#
# A grandeza medida é CONTAGEM DE CANDIDATOS PERCORRIDOS, não relógio. Tempo
# de parede varia 4x entre execuções idênticas numa máquina compartilhada e
# não serve de portão; a contagem é determinística e é exatamente o que o
# defeito faz crescer.


class _DequeContada(deque):
    """Bucket do índice que conta cada item percorrido na reconciliação."""

    def __init__(self, contador: list[int]) -> None:
        super().__init__()
        self._contador = contador

    def __iter__(self):
        contador = self._contador
        for item in super().__iter__():
            contador[0] += 1
            yield item


class _IndiceContado(dict):
    """Índice que fabrica buckets contados. `setdefault` é o único ponto de criação."""

    def __init__(self, contador: list[int]) -> None:
        super().__init__()
        self._contador = contador

    def setdefault(self, chave, _padrao):
        bucket = dict.get(self, chave)
        if bucket is None:
            bucket = _DequeContada(self._contador)
            self[chave] = bucket
        return bucket


# Ordem 50/50 fixa (não sorteada): metade dos negócios pode explicar a queda
# no bid, metade não. Determinismo importa mais que realismo estatístico aqui.
_METADE_CASA = (AgressorSide.SELL, AgressorSide.BUY)
_NENHUM_CASA = (AgressorSide.BUY,)


# Teto absoluto de candidatos percorridos por passo. A reconciliação é O(1)
# amortizado: o que ela precisa visitar é o item que vai casar, mais o
# eventual prefixo morto que a poda remove em seguida. Qualquer coisa acima de
# um punhado significa varredura.
_TETO_VISITAS_POR_PASSO = 8

# Passos por medição. Fixo e igual para todas as taxas de propósito: se
# variasse junto com a taxa, uma degradação que cresce com o TAMANHO DA SESSÃO
# (em vez de com a taxa) apareceria diluída e a comparação entre taxas ficaria
# comparando cenários diferentes.
_PASSOS_DA_MEDICAO = 4_000


def _visitas_por_passo(
    taxa_por_s: int,
    agressores: tuple[AgressorSide, ...],
    n_passos: int = _PASSOS_DA_MEDICAO,
) -> float:
    """Candidatos percorridos por passo, em regime de preço cravado.

    Um passo = uma leitura de book em que o bid do topo perde 2 contratos, mais
    um negócio de 1 contrato NO MESMO PREÇO. `taxa_por_s` controla quantos
    passos cabem dentro de `janela_reconciliacao_ns` — ou seja, quantos itens
    ficam vivos no bucket daquele nível.
    """
    inferidor, _, _ = _montar()
    contador: list[int] = [0]
    inferidor._trades_por_nivel = _IndiceContado(contador)
    inferidor._pendentes_por_nivel = _IndiceContado(contador)

    ts = 1_000_000_000_000
    intervalo = max(1, 10**9 // taxa_por_s)
    qty = 10**8 + 2 * n_passos
    inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, qty)], asks=[(ASK, qty)]))

    contador[0] = 0
    for i in range(n_passos):
        ts += intervalo
        qty -= 2
        inferidor.ao_snapshot(_snapshot(ts, bids=[(BID, qty)], asks=[(ASK, 10**8)]))
        inferidor.ao_trade(_trade(ts, BID, 1, agressores[i % len(agressores)], f"c{i}"))
    return contador[0] / n_passos


@pytest.mark.parametrize(
    "agressores, rotulo",
    [(_METADE_CASA, "metade casa"), (_NENHUM_CASA, "nenhum casa")],
)
def test_custo_do_casamento_nao_cresce_com_a_taxa_do_tape(agressores, rotulo) -> None:
    """20x mais tape no MESMO preço não pode custar mais POR EVENTO.

    Este é o teste que faltava nas três rodadas. Sem ele, indexar por preço e
    deixar a perna do LADO para um teste dentro do laço parece correção — e
    parece medida, se a medição variar a largura do book em vez da taxa.

    Se ele morrer, a leitura correspondente é: o custo por evento voltou a
    depender de quantos itens couberam na janela de reconciliação, logo o
    custo total voltou a ser O(n × taxa) e o módulo deixa de sustentar o pico
    de 10.000 eventos/s do WDO exatamente quando o mercado acelera.
    """
    devagar = _visitas_por_passo(500, agressores)
    rapido = _visitas_por_passo(10_000, agressores)

    # Duas asserções, e as duas são necessárias. A FORMA sozinha deixa passar
    # uma degradação que não depende da taxa (medido: a poda pelo fim do
    # bucket em vez do início leva a 927 visitas/passo com a razão entre as
    # taxas ainda abaixo de 1). O NÍVEL sozinho deixa passar um crescimento
    # lento que só se manifesta acima da faixa medida.
    assert rapido <= 2 * devagar + 2, (
        f"custo por passo cresceu com a taxa ({rotulo}): "
        f"{devagar:.1f} visitas/passo a 500/s contra {rapido:.1f} a 10.000/s. "
        "O casamento voltou a varrer o bucket em vez de indexá-lo."
    )
    assert max(devagar, rapido) <= _TETO_VISITAS_POR_PASSO, (
        f"custo por passo alto em termos absolutos ({rotulo}): "
        f"{devagar:.1f} a 500/s e {rapido:.1f} a 10.000/s, teto "
        f"{_TETO_VISITAS_POR_PASSO}. A reconciliação é O(1) amortizado."
    )


@pytest.mark.parametrize(
    "agressores, rotulo",
    [(_METADE_CASA, "metade casa"), (_NENHUM_CASA, "nenhum casa")],
)
def test_custo_do_casamento_nao_cresce_com_a_duracao_do_pregao(agressores, rotulo) -> None:
    """Nem com a taxa, nem com o tempo que o pregão já durou.

    O caso que a razão entre taxas não pega: uma poda que deixa item morto no
    bucket faz o custo crescer com o NÚMERO DE EVENTOS JÁ VISTOS, não com a
    taxa. Num pregão de WDO isso é a mesma catástrofe uma hora depois — e é
    pior, porque piora sozinho enquanto o operador olha a tela.
    """
    curto = _visitas_por_passo(10_000, agressores, n_passos=3_000)
    longo = _visitas_por_passo(10_000, agressores, n_passos=12_000)

    assert longo <= 2 * curto + 2, (
        f"custo por passo cresceu com a duração da sessão ({rotulo}): "
        f"{curto:.1f} visitas/passo em 3.000 passos contra {longo:.1f} em 12.000. "
        "Sobrou item morto no bucket — a poda deixou de ser amortizada."
    )
    assert longo <= _TETO_VISITAS_POR_PASSO


def test_bucket_de_um_nivel_nao_guarda_o_lado_oposto() -> None:
    """As DUAS pernas da reconciliação são estruturais, não testadas no laço.

    Um negócio agredido na compra só pode ter consumido o ASK. Ele não pode
    sequer aparecer como candidato de uma queda no BID do mesmo preço — se
    aparecer, existe varredura sendo paga para descobrir o que a chave já
    sabia.
    """
    inferidor, _, _ = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(BID, 100)], asks=[(BID + 5, 100)]))
    inferidor.ao_trade(_trade(2_000, BID, 40, AgressorSide.BUY))  # passivo = SELL

    chaves = set(inferidor._trades_por_nivel)
    assert len(chaves) == 1
    (preco, cod_lado), = chaves
    assert preco == BID
    # a queda no BID procura o bucket do lado COMPRADOR daquele preço
    from fluxopro.microestrutura.inferencia_mbp import _COD_COMPRA

    assert cod_lado != _COD_COMPRA, "negócio do lado errado ficou visível para a queda"


# ======================================================================
# 12. INTEGRIDADE DO LIVRO RECONSTRUÍDO — cruzar não é corromper
# ======================================================================
# `LivroMBO.n_cruzamentos_detectados` é documentado como "dado corrompido,
# evento perdido ou reordenação do feed". Em modo MBP, antes desta correção,
# ele contava principalmente OUTRA coisa: a defasagem desta ponte. A queda de
# quantidade só vira `livro.cancelar` quando a janela de reconciliação expira
# — porque até lá ela ainda pode ser explicada por um negócio cuja impressão
# não chegou — enquanto as inserções do lado oposto entram na hora. Nesse
# intervalo o livro reconstruído exibe um bid que o feed já apagou, e cruza.
#
# Um contador de integridade que dispara por construção do próprio produtor é
# pior que contador nenhum: ensina a ignorá-lo.


def _feed_mbp_limpo(inferidor: InferidorMBP, n_passos: int = 120) -> int:
    """Preço andando 1 tick por vez, book de 3 níveis, FONTE nunca cruzada.

    Determinístico de propósito: o passo do preço é uma sequência fixa, não
    sorteio. Devolve quantos eventos foram publicados.
    """
    ts = 1_000_000
    meio = 5_000
    eventos = 0
    for i in range(n_passos):
        ts += 20 * UM_MILISSEGUNDO_NS
        meio += 1 if (i // 3) % 2 == 0 else -1
        bid, ask = meio, meio + 1
        assert bid < ask, "a FONTE nunca cruza — o que cruzar é obra da ponte"
        inferidor.ao_snapshot(
            _snapshot(
                ts,
                bids=[(bid - k, 40 + 7 * k) for k in range(3)],
                asks=[(ask + k, 40 + 5 * k) for k in range(3)],
            )
        )
        eventos += 1
        ts += 5 * UM_MILISSEGUNDO_NS
        comprador = i % 2 == 0
        inferidor.ao_trade(
            _trade(
                ts,
                ask if comprador else bid,
                5 + (i % 11),
                AgressorSide.BUY if comprador else AgressorSide.SELL,
                f"lm{i}",
            )
        )
        eventos += 1
    inferidor.drenar(ts + DEPOIS_DA_JANELA)
    return eventos


def test_feed_mbp_limpo_nao_acusa_um_unico_cruzamento_de_feed() -> None:
    """O teste que define o defeito: fonte impecável, contador zerado.

    Se este teste morrer, a leitura é: o produto voltou a chamar a própria
    defasagem de "feed corrompido", e o operador que confiar no contador vai
    desligar a leitura de fluxo num pregão em que nada de errado aconteceu.
    """
    inferidor, livro, _ = _montar()
    alertas: list[object] = []
    livro.assinar_cruzamento(alertas.append)

    eventos = _feed_mbp_limpo(inferidor)

    assert eventos >= 240, "cenário pequeno demais para valer como prova"
    assert livro.n_cruzamentos_detectados == 0
    assert alertas == []


def test_o_livro_realmente_cruzou_e_isso_ficou_registrado() -> None:
    """Contrapartida obrigatória: zerar o contador não pode ser cegueira.

    Sem esta asserção, apagar `_verificar_cruzamento` inteiro faria o teste
    anterior passar. O cruzamento transitório ACONTECE, é real, e fica contado
    onde diz a verdade sobre o que é.
    """
    inferidor, livro, _ = _montar()
    _feed_mbp_limpo(inferidor)

    assert livro.n_cruzamentos_por_reconciliacao > 0, (
        "o cenário deixou de exercitar a defasagem da ponte — sem cruzamento"
        " transitório nenhum, o teste-irmão não prova nada"
    )


def test_feed_mbp_genuinamente_corrompido_continua_acusando() -> None:
    """A fonte manda bid ACIMA do ask. Isso não é defasagem, é feed quebrado.

    A ponte está ligada e declarada; mesmo assim o contador tem de acusar,
    porque nenhum dos dois topos que cruzam exibe liquidez que a fonte tenha
    tirado — os dois estão no book exatamente como o feed os publicou.
    """
    inferidor, livro, _ = _montar()
    alertas: list[object] = []
    livro.assinar_cruzamento(alertas.append)

    inferidor.ao_snapshot(_snapshot(1_000, bids=[(5_000, 50)], asks=[(5_001, 50)]))
    inferidor.ao_snapshot(
        _snapshot(
            2_000,
            bids=[(5_005, 50), (5_000, 50)],
            asks=[(5_001, 50), (5_002, 50)],
        )
    )

    assert livro.esta_cruzado is True
    assert livro.cruzamento_e_transitorio is False
    assert livro.n_cruzamentos_detectados == 1
    assert len(alertas) == 1
    assert alertas[0].melhor_bid == 5_005
    assert alertas[0].melhor_ask == 5_001


def test_liquidez_nao_aplicada_e_a_diferenca_entre_o_feed_e_o_livro() -> None:
    """A pergunta é respondida por comparação de estado, não por contador.

    Um contador paralelo de "quanto ainda devo ao livro" pode dessincronizar e
    passar a mentir — e mentira de contador de integridade é exatamente o
    defeito que está sendo corrigido. Aqui a resposta sai da diferença entre
    o que o feed diz que existe e o que o livro ainda exibe.
    """
    inferidor, livro, _ = _nivel_ask_de_150()
    assert inferidor.tem_liquidez_nao_aplicada(Side.SELL, ASK) is False

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))
    assert livro.qty_total(Side.SELL, ASK) == 150, "veredito ainda não saiu"
    assert inferidor.tem_liquidez_nao_aplicada(Side.SELL, ASK) is True

    inferidor.drenar(2_000 + DEPOIS_DA_JANELA)
    assert livro.qty_total(Side.SELL, ASK) == 120
    assert inferidor.tem_liquidez_nao_aplicada(Side.SELL, ASK) is False


def test_queda_explicada_por_negocio_nao_deixa_defasagem() -> None:
    """Execução é aplicada na hora: não há defasagem para explicar cruzamento."""
    inferidor, livro, _ = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.BUY))
    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 120))

    assert livro.qty_total(Side.SELL, ASK) == 120
    assert inferidor.tem_liquidez_nao_aplicada(Side.SELL, ASK) is False


# ======================================================================
# 13. ORDEM DE CASAMENTO COM AGRESSOR DESCONHECIDO
# ======================================================================
# O índice é por `(preço, lado)`. O agressor desconhecido é o único item que
# não pode morar num bucket de lado — ele é candidato dos dois. Mora num
# bucket próprio, e os dois candidatos são percorridos INTERCALADOS por ordem
# de chegada. Sem isso, partir o índice por lado mudaria em silêncio quem paga
# quem: um evento recente do lado certo passaria à frente de um desconhecido
# mais antigo, e a atribuição de execução sairia diferente sem que nada
# acusasse.


def test_negocio_desconhecido_mais_antigo_paga_antes_do_conhecido_mais_novo() -> None:
    """Fila é fila: o bucket do lado não tem preferência sobre o do desconhecido."""
    inferidor, _, eventos = _nivel_ask_de_150()

    inferidor.ao_trade(_trade(2_000, ASK, 30, AgressorSide.UNKNOWN, "velho"))
    inferidor.ao_trade(_trade(2_100, ASK, 30, AgressorSide.BUY, "novo"))
    inferidor.ao_delta(_delta(2_200, Side.SELL, ASK, 120))  # queda de 30

    evento = _unico(eventos, TipoEventoOrdem.TRADE)
    assert evento.evidencia["trade_id"] == "velho", "o bucket do lado furou a fila"
    # e a consequência que o operador vê: lado não confirmado vale menos
    assert evento.confianca == ConfigInferenciaMBP().confianca_execucao_lado_nao_confirmado


def test_queda_mais_antiga_paga_primeiro_mesmo_sendo_do_outro_lado() -> None:
    """O mesmo, na direção oposta: um negócio desconhecido escolhendo a queda.

    Livro travado (bid e ask no mesmo preço) é o único jeito de existirem
    quedas pendentes dos DOIS lados num preço só — e é justamente o estado em
    que um negócio de agressor desconhecido não tem como decidir o lado.
    """
    inferidor, _, eventos = _montar()
    inferidor.ao_snapshot(_snapshot(1_000, bids=[(ASK, 100)], asks=[(ASK, 100)]))
    eventos.clear()

    inferidor.ao_delta(_delta(2_000, Side.SELL, ASK, 70))  # queda de 30, mais ANTIGA
    inferidor.ao_delta(_delta(2_100, Side.BUY, ASK, 60))  # queda de 40, mais nova
    inferidor.ao_trade(_trade(2_200, ASK, 30, AgressorSide.UNKNOWN))

    evento = _unico(eventos, TipoEventoOrdem.TRADE)
    assert evento.side is Side.SELL, "a queda mais nova do outro lado furou a fila"
    assert evento.qty == 30
