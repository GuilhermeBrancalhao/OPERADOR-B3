"""Compara o dia atual contra a media/desvio-padrao do proprio historico.

Isso e o "auto-adaptativo": nao ha modelo pra re-treinar, os parametros
(media, desvio) vem sempre do banco (`banco.historico`), entao o padrao
de comparacao anda sozinho conforme mais pregoes sao gravados.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesvioMetrica:
    nome: str
    valor_hoje: float
    media_historica: float
    desvio_padrao_historico: float
    n_amostras: int

    @property
    def z_score(self) -> float | None:
        if self.desvio_padrao_historico <= 0 or self.n_amostras < 2:
            return None
        return (self.valor_hoje - self.media_historica) / self.desvio_padrao_historico

    @property
    def anomalo(self) -> bool:
        z = self.z_score
        return z is not None and abs(z) >= 2.0


def _serie(historico: list[dict], chave_extratora) -> list[float]:
    valores = []
    for linha in historico:
        valor = chave_extratora(linha)
        if valor is not None:
            valores.append(float(valor))
    return valores


def comparar_metrica(nome: str, valor_hoje: float, serie_historica: list[float]) -> DesvioMetrica:
    n = len(serie_historica)
    media = statistics.mean(serie_historica) if n else 0.0
    desvio = statistics.pstdev(serie_historica) if n >= 2 else 0.0
    return DesvioMetrica(
        nome=nome,
        valor_hoje=valor_hoje,
        media_historica=media,
        desvio_padrao_historico=desvio,
        n_amostras=n,
    )


def comparar_contra_historico(metricas_hoje, historico_sem_hoje: list[dict]) -> list[DesvioMetrica]:
    """`historico_sem_hoje` vem de `banco.historico(...)` -- ja exclui a linha
    de hoje porque ela so e gravada DEPOIS desta comparacao (ver fechar_pregao.py).
    """
    resultado = [
        comparar_metrica(
            "volume_total", metricas_hoje.volume_total,
            _serie(historico_sem_hoje, lambda l: l["volume_total"]),
        ),
        comparar_metrica(
            "delta_volume", metricas_hoje.delta_volume,
            _serie(historico_sem_hoje, lambda l: l["volume_compra"] - l["volume_venda"]),
        ),
    ]
    tipos = set(metricas_hoje.contagem_deteccoes) | {
        tipo
        for linha in historico_sem_hoje
        for tipo in _deteccoes_json(linha)
    }
    for tipo in sorted(tipos):
        resultado.append(
            comparar_metrica(
                f"deteccoes_{tipo}",
                metricas_hoje.contagem_deteccoes.get(tipo, 0),
                [_deteccoes_json(linha).get(tipo, 0) for linha in historico_sem_hoje],
            )
        )
    return resultado


def _deteccoes_json(linha: dict) -> dict:
    import json

    return json.loads(linha.get("contagem_deteccoes_json") or "{}")
