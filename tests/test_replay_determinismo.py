from __future__ import annotations

import csv
import tracemalloc
from pathlib import Path

import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookDelta, Trade
from fluxopro.dados.replay import AdaptadorReplay, ReplayForaDeOrdemError

_TRADES_CSV = """timestamp_ns,symbol,price,qty,side_agressor,trade_id,buyer_broker,seller_broker
100,WDOFUT,10000,5,BUY,T1,B1,S1
100,WDOFUT,10001,3,SELL,T2,B2,S2
250,WDOFUT,10002,1,BUY,T3,B1,S3
"""

_DELTAS_CSV = """timestamp_ns,symbol,side,action,price,qty,position
100,WDOFUT,BUY,ADD,9999,10,0
200,WDOFUT,SELL,UPDATE,10005,20,0
"""


def _rodar(trades_path: Path, deltas_path: Path) -> list[Trade | BookDelta]:
    barramento = Barramento()
    coletados: list[Trade | BookDelta] = []
    barramento.assinar(Trade, coletados.append)
    barramento.assinar(BookDelta, coletados.append)
    adaptador = AdaptadorReplay(barramento, trades_path, deltas_path, velocidade="max")
    adaptador.iniciar()
    return coletados


def test_replay_e_deterministico(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(_DELTAS_CSV, encoding="utf-8")

    sequencia_1 = _rodar(trades_path, deltas_path)
    sequencia_2 = _rodar(trades_path, deltas_path)

    assert sequencia_1 == sequencia_2
    assert hash(tuple(sequencia_1)) == hash(tuple(sequencia_2))
    assert len(sequencia_1) == 5


def test_replay_ordena_por_timestamp_trade_antes_de_delta_em_empate(
    tmp_path: Path,
) -> None:
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(_DELTAS_CSV, encoding="utf-8")

    sequencia = _rodar(trades_path, deltas_path)
    timestamps = [e.timestamp_ns for e in sequencia]

    assert timestamps == sorted(timestamps)
    assert isinstance(sequencia[0], Trade) and sequencia[0].trade_id == "T1"
    assert isinstance(sequencia[1], Trade) and sequencia[1].trade_id == "T2"
    assert isinstance(sequencia[2], BookDelta) and sequencia[2].price == 9999
    assert isinstance(sequencia[3], BookDelta) and sequencia[3].price == 10005
    assert isinstance(sequencia[4], Trade) and sequencia[4].trade_id == "T3"


def test_replay_sem_deltas_publica_so_trades(tmp_path: Path) -> None:
    trades_path = tmp_path / "trades.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    adaptador = AdaptadorReplay(barramento, trades_path, deltas_path=None, velocidade="max")
    adaptador.iniciar()

    assert len(coletados) == 3


# ---------------------------------------------------------------------------
# Quem comprou e quem vendeu (`criticas/nucleo_r2.md` N03 — viva 5 rodadas)
#
# `N03` troca `buyer_broker` por `seller_broker` na volta do CSV. Nenhum dos
# 574 testes olhava esses dois campos, e a mesma inversão existe no outro
# leitor (`F02`, em `gravacao/formato.py`). Importa mais depois da onda 8,
# que ligou `RankingCorretoras` e `PerfilPlayer` — os dois módulos cuja
# pergunta inteira é "quem está fazendo o quê".
# ---------------------------------------------------------------------------


def test_replay_nao_troca_comprador_por_vendedor(tmp_path: Path) -> None:
    """Os dois campos são assimétricos no CSV de propósito (B* de um lado,
    S* do outro): trocá-los é detectável por qualquer leitura, e nenhuma
    permutação dos dois valores sobrevive às duas asserções."""
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(_DELTAS_CSV, encoding="utf-8")

    trades = [e for e in _rodar(trades_path, deltas_path) if isinstance(e, Trade)]
    por_id = {t.trade_id: t for t in trades}

    assert por_id["T1"].buyer_broker == "B1"
    assert por_id["T1"].seller_broker == "S1"
    assert por_id["T3"].buyer_broker == "B1"
    assert por_id["T3"].seller_broker == "S3"


def test_replay_le_todos_os_campos_do_trade_sem_permutar(tmp_path: Path) -> None:
    """Uma linha com TODOS os campos distintos entre si: qualquer troca de
    duas colunas na leitura muda pelo menos uma asserção."""
    trades_path = tmp_path / "trades.csv"
    with trades_path.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(
            ["timestamp_ns", "symbol", "price", "qty", "side_agressor",
             "trade_id", "buyer_broker", "seller_broker"]
        )
        w.writerow([777, "WDOV26", 10_101, 42, "SELL", "id-unico", "XP", "BTG"])

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    AdaptadorReplay(barramento, trades_path, None, velocidade="max").iniciar()

    (t,) = coletados
    assert t.timestamp_ns == 777
    assert t.symbol == "WDOV26"
    assert t.price == 10_101
    assert t.qty == 42
    assert t.side_agressor is AgressorSide.SELL
    assert t.trade_id == "id-unico"
    assert t.buyer_broker == "XP"
    assert t.seller_broker == "BTG"


def test_broker_ausente_no_csv_vira_string_vazia_e_nao_None(tmp_path: Path) -> None:
    """O CSV do núcleo pode não ter as colunas de corretora (é o que
    `tests/test_app_montagem.py` escreve). O contrato é string vazia — `None`
    ali estouraria no `RankingCorretoras` rio abaixo."""
    trades_path = tmp_path / "trades.csv"
    trades_path.write_text(
        "timestamp_ns,symbol,price,qty,side_agressor,trade_id\n"
        "1,WDOFUT,100,1,BUY,t0\n",
        encoding="utf-8",
    )
    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    AdaptadorReplay(barramento, trades_path, None, velocidade="max").iniciar()

    (t,) = coletados
    assert t.buyer_broker == ""
    assert t.seller_broker == ""


# ---------------------------------------------------------------------------
# Critério de crescimento: o replay é STREAMING
#
# `criticas/nucleo_r5.md` §A.4.3 achou, em `dados/leitor_gravacao.py`, uma
# lista que materializa o pregão inteiro antes do primeiro evento (37 GB para
# 6 h a 5.000 ev/s). `dados/replay.py` tinha a MESMA forma e não estava no
# inventário. Estes testes prendem os dois lados da correção: o primeiro
# evento sai antes de o arquivo acabar, e a memória não cresce com o arquivo.
# ---------------------------------------------------------------------------


def _csv_sintetico(caminho: Path, n: int) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(
            ["timestamp_ns", "symbol", "price", "qty", "side_agressor",
             "trade_id", "buyer_broker", "seller_broker"]
        )
        for i in range(n):
            w.writerow([i * 1000, "WDOV26", 10_000 + (i % 40), 1 + (i % 7),
                        "BUY" if i % 2 else "SELL", f"t{i}", f"B{i % 5}", f"S{i % 5}"])


def test_o_primeiro_evento_sai_antes_de_o_arquivo_acabar(tmp_path: Path) -> None:
    """A metade da correção que a memória sozinha não prova: a implementação
    em lista publicava o 1º evento só depois de ler, montar e ordenar o
    arquivo inteiro. Aqui o adaptador é PARADO no primeiro evento e ainda
    assim só um evento chega — se `_eventos_ordenados` materializasse tudo, a
    leitura do arquivo inteiro já teria acontecido antes desse `parar()`.
    """
    caminho = tmp_path / "trades.csv"
    _csv_sintetico(caminho, 20_000)

    barramento = Barramento()
    vistos: list[Trade] = []
    adaptador = AdaptadorReplay(barramento, caminho, None, velocidade="max")

    def ao_trade(t: Trade) -> None:
        vistos.append(t)
        adaptador.parar()

    barramento.assinar(Trade, ao_trade)
    adaptador.iniciar()

    assert len(vistos) == 1
    assert vistos[0].trade_id == "t0"

    # e a sequência é um ITERADOR preguiçoso, não uma coleção já pronta
    fluxo = adaptador._eventos_ordenados()
    assert not hasattr(fluxo, "__len__"), "_eventos_ordenados voltou a materializar"
    assert next(iter(fluxo)).trade_id == "t0"


@pytest.mark.parametrize("n_pequeno, n_grande", [(5_000, 40_000)])
def test_memoria_do_replay_nao_cresce_com_o_tamanho_do_arquivo(
    tmp_path: Path, n_pequeno: int, n_grande: int
) -> None:
    """Critério de crescimento, medido em vez de argumentado.

    "Qual grandeza limita o `len` disto?" A resposta certa é "o número de
    ARQUIVOS" (o heap do merge), não "o número de eventos do pregão". O teste
    consome os dois arquivos inteiros e compara o pico de memória: um arquivo
    8x maior não pode custar 8x mais memória.

    O gate é folgado de propósito (2x para 8x de dado) porque medir memória
    tem ruído; ele não precisa ser apertado para pegar o defeito, que é
    LINEAR — a implementação em lista dá ~8x aqui, muito acima do gate. É
    esta a asserção que faltava para `G01` em `gravacao/gravador.py`: sem um
    teste de crescimento, quem consertar não tem como provar que consertou, e
    quem reintroduzir não é pego.
    """

    def pico_consumindo(n: int) -> int:
        caminho = tmp_path / f"t{n}.csv"
        _csv_sintetico(caminho, n)
        barramento = Barramento()
        contagem = [0]

        def contar(_t: Trade) -> None:
            contagem[0] += 1

        barramento.assinar(Trade, contar)
        adaptador = AdaptadorReplay(barramento, caminho, None, velocidade="max")
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        adaptador.iniciar()
        pico = tracemalloc.get_traced_memory()[1] - base
        tracemalloc.stop()
        assert contagem[0] == n
        return pico

    pico_pequeno = pico_consumindo(n_pequeno)
    pico_grande = pico_consumindo(n_grande)

    fator_dado = n_grande / n_pequeno
    fator_memoria = pico_grande / max(pico_pequeno, 1)
    assert fator_memoria < 2.0, (
        f"memoria cresceu {fator_memoria:.1f}x para {fator_dado:.0f}x de dado "
        f"({pico_pequeno} -> {pico_grande} bytes): o replay voltou a "
        f"materializar o arquivo inteiro"
    )


# ---------------------------------------------------------------------------
# Entrada fora de ordem: falha FECHADA (mesma política de `RelogioReplay`)
# ---------------------------------------------------------------------------


def test_arquivo_com_timestamp_regredindo_e_recusado_com_o_ponto_exato(
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "trades.csv"
    caminho.write_text(
        "timestamp_ns,symbol,price,qty,side_agressor,trade_id\n"
        "100,WDOFUT,10000,1,BUY,t0\n"
        "300,WDOFUT,10001,1,BUY,t1\n"
        "200,WDOFUT,10002,1,BUY,t2\n",
        encoding="utf-8",
    )
    barramento = Barramento()
    vistos: list[Trade] = []
    barramento.assinar(Trade, vistos.append)

    with pytest.raises(ReplayForaDeOrdemError) as erro:
        AdaptadorReplay(barramento, caminho, None, velocidade="max").iniciar()

    mensagem = str(erro.value)
    assert "300" in mensagem and "200" in mensagem, "a mensagem nao diz quais timestamps"
    assert "3" in mensagem, "a mensagem nao diz em que linha"
    # os eventos ANTERIORES ao ponto ruim já saíram — o erro interrompe, não
    # desfaz. Dizer isso aqui é o que impede alguém de assumir atomicidade.
    assert [t.trade_id for t in vistos] == ["t0", "t1"]


def test_timestamp_repetido_nao_e_fora_de_ordem(tmp_path: Path) -> None:
    """Empate é comum (vários eventos no mesmo nanossegundo) e a política de
    `RelogioReplay` já o aceita explicitamente. Recusar aqui rejeitaria tape
    válido — é a metade que evita que a guarda vire uma guarda severa demais."""
    caminho = tmp_path / "trades.csv"
    caminho.write_text(
        "timestamp_ns,symbol,price,qty,side_agressor,trade_id\n"
        "100,WDOFUT,10000,1,BUY,t0\n"
        "100,WDOFUT,10001,1,BUY,t1\n"
        "100,WDOFUT,10002,1,BUY,t2\n",
        encoding="utf-8",
    )
    barramento = Barramento()
    vistos: list[Trade] = []
    barramento.assinar(Trade, vistos.append)
    AdaptadorReplay(barramento, caminho, None, velocidade="max").iniciar()

    assert [t.trade_id for t in vistos] == ["t0", "t1", "t2"]


def test_deltas_fora_de_ordem_tambem_sao_recusados(tmp_path: Path) -> None:
    """A guarda vale para os DOIS arquivos: proteger só o de trades deixaria
    metade do merge sem cobertura."""
    trades_path = tmp_path / "trades.csv"
    deltas_path = tmp_path / "deltas.csv"
    trades_path.write_text(_TRADES_CSV, encoding="utf-8")
    deltas_path.write_text(
        "timestamp_ns,symbol,side,action,price,qty,position\n"
        "500,WDOFUT,BUY,ADD,9999,10,0\n"
        "400,WDOFUT,SELL,UPDATE,10005,20,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ReplayForaDeOrdemError, match="deltas"):
        _rodar(trades_path, deltas_path)
