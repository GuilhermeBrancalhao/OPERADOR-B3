from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
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
