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
