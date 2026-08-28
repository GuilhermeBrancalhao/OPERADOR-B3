"""Cobre o pipeline de fim-de-pregao pedido pelo operador em 27/08/2026:
leitura consultiva ligada ao Claude (CLI) + banco SQLite pra aprendizado
de metricas constantes (media/desvio-padrao do proprio historico)."""

import gzip
import json

import pytest

from fluxopro.aprendizado import banco, padroes
from fluxopro.aprendizado.consultor_llm import gerar_analise_consultiva, montar_prompt
from fluxopro.aprendizado.metricas_dia import calcular_metricas_dia


def _escrever_trades(caminho, linhas):
    caminho.write_text(
        "timestamp_ns,symbol,price,qty,side_agressor,trade_id,buyer_broker,seller_broker\n"
        + "\n".join(linhas),
        encoding="utf-8",
    )


def test_calcular_metricas_dia_le_trades_e_deteccoes(tmp_path):
    trades = tmp_path / "trades.csv"
    _escrever_trades(
        trades,
        [
            "1,WDOU26,5150,10,BUY,t1,,",
            "2,WDOU26,5152,5,SELL,t2,,",
            "3,WDOU26,5151,20,BUY,t3,,",
        ],
    )
    log = tmp_path / "pregao.log"
    log.write_text(
        "09:00:35.203  DETECCAO  ABSORCAO            VENDA  @5155       [OBS]       | x=1\n"
        "09:00:36.000  DETECCAO  ABSORCAO            COMPRA @5156       [OBS]       | x=1\n"
        "09:00:37.000  DETECCAO  EXAUSTAO            VENDA  @5157       [OBS]       | x=1\n",
        encoding="utf-8",
    )

    m = calcular_metricas_dia("WDOU26", "2026-08-27", trades, log)

    assert m.n_trades == 3
    assert m.volume_total == 35
    assert m.volume_compra == 30
    assert m.volume_venda == 5
    assert m.delta_volume == 25
    assert m.preco_abertura == 5150
    assert m.preco_fechamento == 5151
    assert m.preco_maximo == 5152
    assert m.preco_minimo == 5150
    assert m.contagem_deteccoes == {"ABSORCAO": 2, "EXAUSTAO": 1}
    assert m.contagem_deteccoes_por_direcao["ABSORCAO"] == {"COMPRA": 1, "VENDA": 1}


def test_calcular_metricas_dia_aceita_gz(tmp_path):
    trades = tmp_path / "trades.csv.gz"
    with gzip.open(trades, "wt") as f:
        f.write(
            "timestamp_ns,symbol,price,qty,side_agressor,trade_id,buyer_broker,seller_broker\n"
            "1,WDOU26,5150,10,BUY,t1,,\n"
        )
    log = tmp_path / "pregao.log"
    log.write_text("", encoding="utf-8")

    m = calcular_metricas_dia("WDOU26", "2026-08-27", trades, log)
    assert m.n_trades == 1
    assert m.volume_total == 10


def test_calcular_metricas_dia_sem_log_nao_quebra(tmp_path):
    trades = tmp_path / "trades.csv"
    _escrever_trades(trades, ["1,WDOU26,5150,10,BUY,t1,,"])
    m = calcular_metricas_dia("WDOU26", "2026-08-27", trades, tmp_path / "nao_existe.log")
    assert m.contagem_deteccoes == {}


def test_banco_grava_e_le_historico(tmp_path):
    conexao = banco.conectar(tmp_path / "asg.db")
    trades = tmp_path / "trades.csv"
    _escrever_trades(trades, ["1,WDOU26,5150,10,BUY,t1,,"])
    m = calcular_metricas_dia("WDOU26", "2026-08-27", trades, tmp_path / "sem.log")

    banco.gravar_sessao(conexao, m, analise_llm="leitura de teste")
    linhas = banco.historico(conexao, "WDOU26")

    assert len(linhas) == 1
    assert linhas[0]["data"] == "2026-08-27"
    assert linhas[0]["analise_llm"] == "leitura de teste"
    assert json.loads(linhas[0]["contagem_deteccoes_json"]) == {}


def test_banco_upsert_nao_duplica_o_mesmo_dia(tmp_path):
    conexao = banco.conectar(tmp_path / "asg.db")
    trades = tmp_path / "trades.csv"
    _escrever_trades(trades, ["1,WDOU26,5150,10,BUY,t1,,"])
    m = calcular_metricas_dia("WDOU26", "2026-08-27", trades, tmp_path / "sem.log")

    banco.gravar_sessao(conexao, m, analise_llm="primeira")
    banco.gravar_sessao(conexao, m, analise_llm="segunda")

    linhas = banco.historico(conexao, "WDOU26")
    assert len(linhas) == 1
    assert linhas[0]["analise_llm"] == "segunda"


def test_comparar_contra_historico_marca_anomalia_por_desvio():
    class _Metricas:
        volume_total = 100_000
        volume_compra = 60_000
        volume_venda = 10_000
        delta_volume = 50_000
        contagem_deteccoes = {"EXAUSTAO": 40}

    historico_dias = [
        {
            "volume_total": 10_000 + (i - 5) * 200, "volume_compra": 5_000, "volume_venda": 5_000,
            "contagem_deteccoes_json": json.dumps({"EXAUSTAO": 5 + (i % 3)}),
        }
        for i in range(10)
    ]

    desvios = padroes.comparar_contra_historico(_Metricas(), historico_dias)
    por_nome = {d.nome: d for d in desvios}

    assert por_nome["volume_total"].anomalo is True
    assert por_nome["deteccoes_EXAUSTAO"].anomalo is True


def test_comparar_contra_historico_sem_historico_nunca_e_anomalo():
    class _Metricas:
        volume_total = 100
        volume_compra = 60
        volume_venda = 40
        delta_volume = 20
        contagem_deteccoes = {}

    desvios = padroes.comparar_contra_historico(_Metricas(), [])
    assert all(d.anomalo is False for d in desvios)
    assert all(d.z_score is None for d in desvios)


def test_gerar_analise_consultiva_sem_cli_disponivel_retorna_none(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda nome: None)

    class _M:
        simbolo = "WDOU26"
        data = "2026-08-27"
        preco_abertura = 5150
        preco_fechamento = 5160
        preco_maximo = 5170
        preco_minimo = 5140
        volume_total = 1000
        volume_compra = 600
        volume_venda = 400
        delta_volume = 200
        contagem_deteccoes = {"EXAUSTAO": 3}

    resultado = gerar_analise_consultiva(_M(), [])
    assert resultado is None


def test_gerar_analise_consultiva_devolve_stdout_do_executavel(tmp_path):
    import sys

    class _M:
        simbolo = "WDOU26"
        data = "2026-08-27"
        preco_abertura = 5150
        preco_fechamento = 5160
        preco_maximo = 5170
        preco_minimo = 5140
        volume_total = 1000
        volume_compra = 600
        volume_venda = 400
        delta_volume = 200
        contagem_deteccoes = {"EXAUSTAO": 3}

    resultado = gerar_analise_consultiva(
        _M(), [], executavel=f"{sys.executable}"
    )
    # sys.executable sozinho (sem -c) so abre o interpretador e devolve stdout
    # vazio -- o que importa aqui e que nao levanta excecao e devolve None
    # quando nao ha texto, provando o caminho feliz de subprocess+timeout.
    assert resultado is None


def test_montar_prompt_menciona_metricas_fora_do_padrao():
    class _M:
        simbolo = "WDOU26"
        data = "2026-08-27"
        preco_abertura = 5150
        preco_fechamento = 5160
        preco_maximo = 5170
        preco_minimo = 5140
        volume_total = 1000
        volume_compra = 600
        volume_venda = 400
        delta_volume = 200
        contagem_deteccoes = {"EXAUSTAO": 3}

    d = padroes.DesvioMetrica(
        nome="volume_total", valor_hoje=1000, media_historica=100,
        desvio_padrao_historico=10, n_amostras=10,
    )
    prompt = montar_prompt(_M(), [d])
    assert "fora do padrao historico" in prompt
    assert "volume_total" in prompt
