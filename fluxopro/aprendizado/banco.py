"""Banco SQLite local com o historico de metricas por pregao.

E a base para "aprendizado de metricas constantes": cada dia grava uma linha
em `sessoes`; com N dias acumulados da pra calcular media/desvio por
detector e comparar o dia de hoje contra o padrao historico -- sem precisar
re-treinar nada, so consultar o proprio banco (ver `padroes.py`).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fluxopro.aprendizado.metricas_dia import MetricasDia

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simbolo TEXT NOT NULL,
    data TEXT NOT NULL,
    n_trades INTEGER NOT NULL,
    volume_total INTEGER NOT NULL,
    volume_compra INTEGER NOT NULL,
    volume_venda INTEGER NOT NULL,
    preco_abertura REAL,
    preco_fechamento REAL,
    preco_maximo REAL,
    preco_minimo REAL,
    contagem_deteccoes_json TEXT NOT NULL,
    contagem_deteccoes_por_direcao_json TEXT NOT NULL,
    analise_llm TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(simbolo, data)
);
"""


def conectar(caminho_banco: Path) -> sqlite3.Connection:
    caminho_banco.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho_banco)
    conexao.execute(_SCHEMA)
    conexao.commit()
    return conexao


def gravar_sessao(
    conexao: sqlite3.Connection, metricas: MetricasDia, analise_llm: str | None
) -> None:
    conexao.execute(
        """
        INSERT INTO sessoes (
            simbolo, data, n_trades, volume_total, volume_compra, volume_venda,
            preco_abertura, preco_fechamento, preco_maximo, preco_minimo,
            contagem_deteccoes_json, contagem_deteccoes_por_direcao_json, analise_llm
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(simbolo, data) DO UPDATE SET
            n_trades=excluded.n_trades,
            volume_total=excluded.volume_total,
            volume_compra=excluded.volume_compra,
            volume_venda=excluded.volume_venda,
            preco_abertura=excluded.preco_abertura,
            preco_fechamento=excluded.preco_fechamento,
            preco_maximo=excluded.preco_maximo,
            preco_minimo=excluded.preco_minimo,
            contagem_deteccoes_json=excluded.contagem_deteccoes_json,
            contagem_deteccoes_por_direcao_json=excluded.contagem_deteccoes_por_direcao_json,
            analise_llm=excluded.analise_llm
        """,
        (
            metricas.simbolo,
            metricas.data,
            metricas.n_trades,
            metricas.volume_total,
            metricas.volume_compra,
            metricas.volume_venda,
            metricas.preco_abertura,
            metricas.preco_fechamento,
            metricas.preco_maximo,
            metricas.preco_minimo,
            json.dumps(metricas.contagem_deteccoes, ensure_ascii=False),
            json.dumps(metricas.contagem_deteccoes_por_direcao, ensure_ascii=False),
            analise_llm,
        ),
    )
    conexao.commit()


def historico(conexao: sqlite3.Connection, simbolo: str, limite: int = 30) -> list[dict]:
    cursor = conexao.execute(
        "SELECT * FROM sessoes WHERE simbolo = ? ORDER BY data DESC LIMIT ?",
        (simbolo, limite),
    )
    colunas = [c[0] for c in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
