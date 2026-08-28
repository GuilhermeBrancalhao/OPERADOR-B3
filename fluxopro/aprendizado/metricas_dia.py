"""Resume um pregao gravado em metricas numericas simples.

Duas fontes, ambas ja existentes e nunca alteradas por este modulo:
- trades.csv(.gz) do gravador (fluxopro.gravacao) -- preco/qty/lado por negocio.
- logs/pregao_AAAA-MM-DD.log do scripts/operar.py -- uma linha por deteccao
  (ABSORCAO, EXAUSTAO, ESCORA, CLIP_INSTITUCIONAL, DIVERGENCIA, ...).

Nao chama LLM nem grava nada -- funcao pura, testavel sem rede.
"""

from __future__ import annotations

import csv
import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path

_LINHA_DETECCAO = re.compile(
    r"DETECCAO\s+(?P<tipo>\S+)\s+(?P<direcao>COMPRA|VENDA)\s+@(?P<preco>[\d.]+)"
)


@dataclass(frozen=True, slots=True)
class MetricasDia:
    simbolo: str
    data: str
    n_trades: int
    volume_total: int
    volume_compra: int
    volume_venda: int
    preco_abertura: float | None
    preco_fechamento: float | None
    preco_maximo: float | None
    preco_minimo: float | None
    contagem_deteccoes: dict[str, int] = field(default_factory=dict)
    contagem_deteccoes_por_direcao: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def delta_volume(self) -> int:
        return self.volume_compra - self.volume_venda


def _abrir_texto(caminho: Path):
    if caminho.suffix == ".gz":
        return gzip.open(caminho, "rt", newline="")
    return open(caminho, "rt", newline="")


def _lado_e_direcional(side: str) -> str | None:
    if side == "BUY":
        return "compra"
    if side == "SELL":
        return "venda"
    return None


def calcular_metricas_trades(caminho_trades: Path) -> dict:
    n_trades = 0
    volume_total = 0
    volume_compra = 0
    volume_venda = 0
    preco_abertura: float | None = None
    preco_fechamento: float | None = None
    preco_maximo: float | None = None
    preco_minimo: float | None = None

    with _abrir_texto(caminho_trades) as arquivo:
        leitor = csv.DictReader(arquivo)
        for linha in leitor:
            n_trades += 1
            qty = int(linha["qty"])
            preco = float(linha["price"])
            volume_total += qty
            lado = _lado_e_direcional(linha.get("side_agressor", ""))
            if lado == "compra":
                volume_compra += qty
            elif lado == "venda":
                volume_venda += qty
            if preco_abertura is None:
                preco_abertura = preco
            preco_fechamento = preco
            preco_maximo = preco if preco_maximo is None else max(preco_maximo, preco)
            preco_minimo = preco if preco_minimo is None else min(preco_minimo, preco)

    return {
        "n_trades": n_trades,
        "volume_total": volume_total,
        "volume_compra": volume_compra,
        "volume_venda": volume_venda,
        "preco_abertura": preco_abertura,
        "preco_fechamento": preco_fechamento,
        "preco_maximo": preco_maximo,
        "preco_minimo": preco_minimo,
    }


def calcular_contagem_deteccoes(caminho_log: Path) -> dict:
    contagem: dict[str, int] = {}
    por_direcao: dict[str, dict[str, int]] = {}
    if not caminho_log.exists():
        return {"contagem_deteccoes": contagem, "contagem_deteccoes_por_direcao": por_direcao}

    with open(caminho_log, "rt", encoding="utf-8", errors="replace") as arquivo:
        for linha in arquivo:
            achado = _LINHA_DETECCAO.search(linha)
            if not achado:
                continue
            tipo = achado.group("tipo")
            direcao = achado.group("direcao")
            contagem[tipo] = contagem.get(tipo, 0) + 1
            por_direcao.setdefault(tipo, {"COMPRA": 0, "VENDA": 0})
            por_direcao[tipo][direcao] += 1

    return {"contagem_deteccoes": contagem, "contagem_deteccoes_por_direcao": por_direcao}


def calcular_metricas_dia(
    simbolo: str, data: str, caminho_trades: Path, caminho_log: Path
) -> MetricasDia:
    metricas_trades = calcular_metricas_trades(caminho_trades)
    metricas_deteccoes = calcular_contagem_deteccoes(caminho_log)
    return MetricasDia(
        simbolo=simbolo,
        data=data,
        **metricas_trades,
        **metricas_deteccoes,
    )
