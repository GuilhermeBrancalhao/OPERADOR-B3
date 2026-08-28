from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import fluxopro.gravacao.gravador as gravador_mod
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
from fluxopro.gravacao import formato
from fluxopro.gravacao.gravador import Gravador

_DIA_1_TS = 1_700_000_000_000_000_000  # bem no meio de um dia UTC qualquer
_UM_DIA_NS = 24 * 60 * 60 * 1_000_000_000


def _trade(ts_ns: int, symbol: str = "WDOV26", trade_id: str = "T1") -> Trade:
    return Trade(
        timestamp_ns=ts_ns, symbol=symbol, price=10000, qty=5,
        side_agressor=AgressorSide.BUY, trade_id=trade_id,
    )


def test_gravador_escreve_trade_e_cabecalho(tmp_path: Path):
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()

    barramento.publicar(_trade(_DIA_1_TS))
    gravador.parar()

    dia = date.fromtimestamp(_DIA_1_TS / 1e9).__class__  # sanity: date importable
    diretorio = next((tmp_path / "WDOV26").iterdir())
    caminho = diretorio / "trades.csv.gz"
    assert caminho.exists()
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        linhas = f.read().splitlines()
    assert linhas[0].startswith("timestamp_ns,symbol,price,qty,side_agressor")
    assert len(linhas) == 2  # cabecalho + 1 trade


def test_gravador_rotaciona_por_dia_e_fecha_arquivo_anterior(tmp_path: Path):
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()

    barramento.publicar(_trade(_DIA_1_TS, trade_id="D1"))
    barramento.publicar(_trade(_DIA_1_TS + _UM_DIA_NS, trade_id="D2"))  # dia seguinte
    gravador.parar()

    dias = sorted(p.name for p in (tmp_path / "WDOV26").iterdir())
    assert len(dias) == 2

    for dia in dias:
        meta = json.loads((tmp_path / "WDOV26" / dia / "meta.json").read_text(encoding="utf-8"))
        assert meta["contagens"]["Trade"] == 1
        assert meta["n_eventos_total"] == 1
        assert "trades.csv" in meta["hashes_sha256"]


def test_gravador_grava_falha_captura_com_fsync_imediato(tmp_path: Path):
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()

    falha = FalhaCaptura(
        timestamp_ns=_DIA_1_TS, symbol="WDOV26",
        tipo=TipoFalha.GAP_TICKS, detalhe="teste",
    )
    barramento.publicar(falha)
    gravador.parar()

    diretorio = next((tmp_path / "WDOV26").iterdir())
    with gzip.open(diretorio / "falhas.csv.gz", "rt", encoding="utf-8") as f:
        linhas = f.read().splitlines()
    assert "GAP_TICKS" in linhas[1]
    assert "teste" in linhas[1]


def test_gravador_persiste_snapshot_com_niveis_codificados(tmp_path: Path):
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()

    snap = BookSnapshot(
        timestamp_ns=_DIA_1_TS, symbol="WDOV26",
        bids=(BookLevel(9999, 10, 1), BookLevel(9998, 5, 2)),
        asks=(BookLevel(10001, 8, 1),),
    )
    barramento.publicar(snap)
    gravador.parar()

    diretorio = next((tmp_path / "WDOV26").iterdir())
    meta = json.loads((diretorio / "meta.json").read_text(encoding="utf-8"))
    assert meta["contagens"]["BookSnapshot"] == 1


def test_gravador_meta_hash_muda_se_conteudo_diferente(tmp_path: Path):
    barramento1 = Barramento()
    g1 = Gravador(barramento1, tmp_path / "a")
    g1.iniciar()
    barramento1.publicar(_trade(_DIA_1_TS, trade_id="X"))
    g1.parar()

    barramento2 = Barramento()
    g2 = Gravador(barramento2, tmp_path / "b")
    g2.iniciar()
    barramento2.publicar(_trade(_DIA_1_TS, trade_id="Y"))
    g2.parar()

    meta1 = json.loads(next((tmp_path / "a" / "WDOV26").glob("*/meta.json")).read_text())
    meta2 = json.loads(next((tmp_path / "b" / "WDOV26").glob("*/meta.json")).read_text())
    assert meta1["hashes_sha256"]["trades.csv"] != meta2["hashes_sha256"]["trades.csv"]


def test_gravador_meta_hora_inicio_e_hora_fim_nao_sao_trocados(tmp_path: Path):
    """`hora_inicio_ns` tem que ser o MENOR timestamp do dia e `hora_fim_ns`
    o MAIOR — não o contrário. Grava fora de ordem cronológica de chegada
    de propósito (o meio antes do fim, o início por último) para não deixar
    a ordem de publicação disfarçar min/max trocados."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()

    meio = _DIA_1_TS + 5_000_000_000
    fim = _DIA_1_TS + 9_000_000_000
    inicio = _DIA_1_TS + 1_000_000_000
    barramento.publicar(_trade(meio, trade_id="MEIO"))
    barramento.publicar(_trade(fim, trade_id="FIM"))
    barramento.publicar(_trade(inicio, trade_id="INICIO"))
    gravador.parar()

    diretorio = next((tmp_path / "WDOV26").iterdir())
    meta = json.loads((diretorio / "meta.json").read_text(encoding="utf-8"))
    assert meta["hora_inicio_ns"] == inicio
    assert meta["hora_fim_ns"] == fim
    assert meta["hora_inicio_ns"] < meta["hora_fim_ns"]


def test_gravador_forca_fsync_imediato_em_falha_captura(tmp_path: Path, monkeypatch):
    """Política documentada em `gravador.py`: `FalhaCaptura` força fsync
    IMEDIATO, sempre — é o registro mais barato e mais importante de não
    perder (prova que um buraco de captura existe). Mocka `os.fsync` para
    confirmar que ele é chamado no mesmo evento que grava a falha, mesmo
    com `fsync_a_cada` alto (nenhum dado normal teria acumulado o
    suficiente para disparar o fsync por contagem)."""
    chamadas: list[int] = []
    monkeypatch.setattr(
        gravador_mod.os, "fsync", lambda fd: chamadas.append(fd)
    )

    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=1000)
    gravador.iniciar()

    falha = FalhaCaptura(
        timestamp_ns=_DIA_1_TS, symbol="WDOV26",
        tipo=TipoFalha.GAP_TICKS, detalhe="teste",
    )
    barramento.publicar(falha)

    assert len(chamadas) == 1  # fsync chamado NA HORA, nao esperou fsync_a_cada
    gravador.parar()


def test_gravador_forca_fsync_apos_fsync_a_cada_linhas(tmp_path: Path, monkeypatch):
    chamadas: list[int] = []
    monkeypatch.setattr(
        gravador_mod.os, "fsync", lambda fd: chamadas.append(fd)
    )

    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=3)
    gravador.iniciar()

    for i in range(5):
        barramento.publicar(_trade(_DIA_1_TS + i, trade_id=f"T{i}"))

    # a cada 3 linhas dispara 1 fsync: apos a 3a linha (1 chamada); a 4a e
    # 5a ainda nao completaram outro lote de 3
    assert len(chamadas) == 1
    gravador.parar()


def test_formato_decodificar_niveis_preserva_ordem_e_valores():
    """A ordem dos níveis do book importa — `niveis[0]` é o topo (melhor
    bid/ask). Um round-trip que inverte a ordem devolveria o pior preço
    como se fosse o melhor, silenciosamente."""
    niveis = (
        BookLevel(price=9999, qty=10, n_orders=1),
        BookLevel(price=9998, qty=5, n_orders=2),
        BookLevel(price=9997, qty=3, n_orders=1),
    )
    texto = formato.codificar_niveis(niveis)
    decodificados = formato.decodificar_niveis(texto)
    assert decodificados == niveis
    assert decodificados[0].price == 9999  # topo continua sendo o topo


# ==========================================================================
# Dia ja finalizado — a guarda da tarefa agendada
# ==========================================================================
def test_evento_de_dia_ja_fechado_e_descartado_e_contado(tmp_path: Path):
    """O cenario de toda segunda-feira as 09:00.

    O adaptador MT5 republica o rabo da sessao anterior ao conectar. Medido num
    teste real da tarefa agendada: **141 negocios do ultimo minuto de sexta**,
    todos ja gravados e hasheados, chegaram numa execucao de domingo — e o
    gravador criou um `trades.csv` solto ao lado do `trades.csv.gz` finalizado.
    Dois arquivos com o mesmo nome-base, e o catalogo passando a ter de
    escolher entre eles.

    A guarda descarta e CONTA, em vez de recusar: recusar abortaria a captura
    do dia novo por causa de um minuto do dia velho.
    """
    bus1 = Barramento()
    g = Gravador(bus1, tmp_path)
    g.iniciar()
    bus1.publicar(_trade(_DIA_1_TS, trade_id="T1"))
    g.parar()  # fecha o dia: comprime e apaga o .csv

    dia = date.fromtimestamp(_DIA_1_TS / 1e9)
    pasta = tmp_path / "WDOV26" / dia.isoformat()
    assert (pasta / "trades.csv.gz").exists()
    assert not (pasta / "trades.csv").exists()

    # segunda execucao, mesmo dia — o rabo da sessao anterior
    bus2 = Barramento()
    g2 = Gravador(bus2, tmp_path)
    g2.iniciar()
    for i in range(5):
        bus2.publicar(_trade(_DIA_1_TS + i, trade_id=f"REPUB{i}"))
    g2.parar()

    assert not (pasta / "trades.csv").exists(), (
        "o dia fechado ganhou um .csv solto ao lado do .csv.gz"
    )
    assert g2.descartados_por_dia_fechado == {("WDOV26", dia): 5}


def test_rabo_de_dia_fechado_nao_pode_sobrescrever_o_meta_json_do_dia_seguinte(
    tmp_path: Path,
):
    """Achado ao vivo em 2026-08-26/27: o rabo de um dia JA finalizado, ao ser
    o PRIMEIRO evento de uma execucao nova, virava `_dia_aberto[symbol]`
    (nenhum dia estava aberto ainda nesta execucao) — e quando o primeiro
    evento de um dia REALMENTE novo chegava, `_fechar_dia` fechava aquele dia
    velho de novo, com zero eventos rastreados nesta execucao, e SOBRESCREVIA
    o `meta.json` real (hashes inclusos) por um vazio.

    Cenario: dia 1 fechado com 1 negocio real. Execucao nova recebe so o rabo
    do dia 1 (nenhum dia aberto ainda) e DEPOIS o primeiro negocio do dia 2.
    O `meta.json` do dia 1 tem de continuar intacto.
    """
    bus1 = Barramento()
    g1 = Gravador(bus1, tmp_path)
    g1.iniciar()
    bus1.publicar(_trade(_DIA_1_TS, trade_id="T1"))
    g1.parar()

    dia1 = date.fromtimestamp(_DIA_1_TS / 1e9)
    pasta_dia1 = tmp_path / "WDOV26" / dia1.isoformat()
    meta_original = json.loads((pasta_dia1 / "meta.json").read_text(encoding="utf-8"))
    assert meta_original["hashes_sha256"], "sanity: o dia 1 tem de ter hash real"

    # execucao nova: primeiro chega o rabo do dia 1 (ja fechado), DEPOIS o
    # primeiro negocio genuino do dia 2.
    bus2 = Barramento()
    g2 = Gravador(bus2, tmp_path)
    g2.iniciar()
    bus2.publicar(_trade(_DIA_1_TS + 1, trade_id="REPUB0"))
    bus2.publicar(_trade(_DIA_1_TS + _UM_DIA_NS, symbol="WDOV26", trade_id="D2T1"))
    g2.parar()

    meta_depois = json.loads((pasta_dia1 / "meta.json").read_text(encoding="utf-8"))
    assert meta_depois == meta_original, (
        "o rabo do dia fechado clobbrou o meta.json real com uma versao vazia"
    )
    assert g2.descartados_por_dia_fechado == {("WDOV26", dia1): 1}


def test_a_guarda_nao_atrapalha_a_retomada_apos_crash(tmp_path: Path):
    """O controle do teste acima, e ele e obrigatorio.

    Uma guarda que bloqueasse toda reabertura mataria a retomada apos crash —
    que e o motivo de `_abrir_arquivo` saber anexar e re-hashear. A diferenca
    e o `.gz`: dia interrompido nao tem, dia finalizado tem.

    Sem este teste, trocar o descarte por um `raise` passaria despercebido.
    """
    # UM BARRAMENTO POR EXECUCAO, e nao um compartilhado: o processo que
    # "morreu" nao desassina, e publicar no mesmo barramento entregaria o
    # evento ao gravador morto antes de chegar no novo. Foi o que aconteceu na
    # primeira versao deste teste — `I/O operation on closed file`, um erro do
    # ARREIO que parecia defeito do produto.
    bus1 = Barramento()
    g = Gravador(bus1, tmp_path)
    g.iniciar()
    bus1.publicar(_trade(_DIA_1_TS, trade_id="A"))
    # NAO chama parar(): simula o processo morto no meio do pregao
    for arq in list(g._arquivos.values()):
        arq.handle.close()

    dia = date.fromtimestamp(_DIA_1_TS / 1e9)
    pasta = tmp_path / "WDOV26" / dia.isoformat()
    assert (pasta / "trades.csv").exists()
    assert not (pasta / "trades.csv.gz").exists()

    bus2 = Barramento()
    g2 = Gravador(bus2, tmp_path)
    g2.iniciar()
    bus2.publicar(_trade(_DIA_1_TS + 1, trade_id="B"))
    g2.parar()

    assert g2.descartados_por_dia_fechado == {}
    with gzip.open(pasta / "trades.csv.gz", "rt", encoding="utf-8") as fh:
        linhas = fh.read().strip().splitlines()
    assert len(linhas) == 3, f"cabecalho + A + B, veio: {linhas}"
