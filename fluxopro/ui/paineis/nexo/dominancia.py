"""Mapeamento EstadoNexo -> motor de Dominância Comprador/Vendedor.

Fonte do contrato: ``INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md``
(pasta Codex/outputs). O motor determinístico (Q6, histerese multi-
condição ULTRA, saúde/sequência) mora em
``fluxopro/analytics/dominancia.py`` — puro, com suíte própria. Este
módulo só monta a entrada a partir do que o projeto já calcula, com a
MESMA disciplina CONFIRMADO/IMPRECISO de
``fluxopro/ui/paineis/nexo/suporte_resistencia.py`` (vários componentes
são literalmente as MESMAS fontes, porque os dois motores descrevem o
mesmo mercado por ângulos vizinhos — agressão, reposição, movimento):

- **A (agressão)** — componente numérico canônico do Maker, sem arredondar.
  O ranking textual é apenas compatibilidade com estados legados.
- **B (livro ponderado)** — cinco níveis reais do contexto, pesos próprios
  1/rank. Sem profundidade válida, mantém o proxy delta/volume legado.
- **R (reposição)** — igual a `suporte_resistencia`.
- **W (retirada de liquidez)** — AUSENTE NA FONTE: sem contagem de
  cancelamento/retirada por lado nesta superfície. Proxy declarado:
  inverso do desequilíbrio (`-B`). É uma aproximação de engenharia, não
  uma medição de retirada/cancelamento nem intenção institucional.
- **M (resposta de preço)** — CONFIRMADO: `(P1-P0)/moveScale`, o
  movimento real da janela de candles sobre uma escala calibrada no
  próprio histórico observado (nunca no intervalo avaliado).

Read-only: nenhuma função aqui aceita ordem, credencial ou parâmetro de
execução. A base é M5 fixa: selecionar M15 ou ampliar o gráfico não muda
o horizonte analítico. Janela nominal e cobertura observada são separadas.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.analytics import dominancia as dom
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo, candles_de_analise
from fluxopro.ui.paineis.nexo.suporte_resistencia import (
    componente_agressao,
    componente_reposicao,
    desequilibrio_de_candles,
    desequilibrio_de_book,
)

__all__ = [
    "JANELA_MOVIMENTO_MICRO",
    "JANELA_MOVIMENTO_MACRO",
    "componentes_micro",
    "componentes_macro",
    "construir_entrada_dominancia",
    "desenhar_estado",
    "rotulo_estado",
]

JANELA_MOVIMENTO_MICRO = 2
JANELA_MOVIMENTO_MACRO = 8
ESCALA_MOVIMENTO_TICKS_PADRAO = 20
"""IMPRECISO — `moveScale` do documento vem de um percentil 95 histórico
calibrado fora do intervalo avaliado; esta superfície não mantém esse
histórico calibrado hoje. 20 ticks é um piso de engenharia declarado
(equivalente a 10 pontos no WDO), não a fórmula da fonte."""

_COR_POR_ESTADO = {
    dom.EstadoDominancia.COMPRA: tema_asg.NEXO_VERDE,
    dom.EstadoDominancia.ULTRA_COMPRA: tema_asg.NEXO_VERDE,
    dom.EstadoDominancia.VENDA: tema_asg.NEXO_ROSA,
    dom.EstadoDominancia.ULTRA_VENDA: tema_asg.NEXO_ROSA,
    dom.EstadoDominancia.BALANCEADO: tema_asg.NEXO_MUTED,
    dom.EstadoDominancia.INDISPONIVEL: tema_asg.NEXO_MUTED,
}
_ROTULO_POR_ESTADO = {
    dom.EstadoDominancia.COMPRA: "BUY",
    dom.EstadoDominancia.ULTRA_COMPRA: "ULTRA BUY",
    dom.EstadoDominancia.VENDA: "SELL",
    dom.EstadoDominancia.ULTRA_VENDA: "ULTRA SELL",
    dom.EstadoDominancia.BALANCEADO: "BALANÇO",
    dom.EstadoDominancia.INDISPONIVEL: "UNAVAILABLE",
}


def _movimento(candles: tuple, janela: int) -> float:
    """``M = clamp(rawMove/moveScale, -1, 1)`` — P0/P1 são o primeiro e o
    último fechamento dos últimos `janela` candles."""

    recentes = candles[-janela:]
    if len(recentes) < 2:
        return 0.0
    p0, p1 = recentes[0].close, recentes[-1].close
    return dom.clamp((p1 - p0) / ESCALA_MOVIMENTO_TICKS_PADRAO)


def componentes_micro(estado: EstadoNexo) -> dict[str, float]:
    candles = candles_de_analise(estado)
    maker = estado.maker
    agressao = componente_agressao(maker)
    reposicao = componente_reposicao(maker)
    desequilibrio = desequilibrio_de_book(estado)
    if desequilibrio is None:
        desequilibrio = desequilibrio_de_candles(candles)
    return {
        "A": agressao, "B": desequilibrio, "R": reposicao,
        "W": dom.clamp(-desequilibrio), "M": _movimento(candles, JANELA_MOVIMENTO_MICRO),
    }


def componentes_macro(estado: EstadoNexo) -> dict[str, float]:
    candles = candles_de_analise(estado)
    maker = estado.maker
    agressao = componente_agressao(maker)
    reposicao = componente_reposicao(maker)
    desequilibrio = desequilibrio_de_book(estado)
    if desequilibrio is None:
        desequilibrio = desequilibrio_de_candles(candles)
    return {
        "A": agressao, "B": desequilibrio, "R": reposicao,
        "W": dom.clamp(-desequilibrio), "M": _movimento(candles, JANELA_MOVIMENTO_MACRO),
    }


def construir_entrada_dominancia(estado: EstadoNexo) -> dict:
    """Monta os argumentos de ``MotorDominancia.processar`` a partir de
    ``EstadoNexo`` — função pura, testável sem motor nem QPainter."""

    candles = candles_de_analise(estado)
    tem_dados = len(candles) >= 2
    qualidade = dom.clamp(min(1.0, len(candles) / 12.0), 0.0, 1.0) if tem_dados else 0.0
    confianca = dom.clamp(min(1.0, len(candles) / 12.0), 0.0, 1.0) if tem_dados else 0.0

    return {
        "componentes_micro": componentes_micro(estado) if tem_dados else None,
        "componentes_macro": componentes_macro(estado) if tem_dados else None,
        "qualidade_micro": qualidade, "qualidade_macro": qualidade,
        "confianca_micro": confianca, "confianca_macro": confianca,
        "amostras_micro": len(candles), "amostras_macro": len(candles),
        "cobertura_micro_ms": _cobertura(candles[-JANELA_MOVIMENTO_MICRO:]),
        "cobertura_macro_ms": _cobertura(candles[-JANELA_MOVIMENTO_MACRO:]),
        "janela_micro_ms": JANELA_MOVIMENTO_MICRO*5*60_000,
        "janela_macro_ms": JANELA_MOVIMENTO_MACRO*5*60_000,
    }


def _cobertura(candles):
    if len(candles)<2:
        return 0
    primeiro = getattr(candles[0],'timestamp_ns',0)
    ultimo = getattr(candles[-1],'timestamp_ns',0)
    return max(0,(ultimo-primeiro)//1_000_000)


def rotulo_estado(estado: "dom.EstadoDominancia") -> str:
    """Texto público do estado (``BUY``/``ULTRA BUY``/...) — para regiões
    vizinhas (ex. `nexo/pressao.py`) que precisam do rótulo sem acoplar no
    dicionário privado deste módulo."""

    return _ROTULO_POR_ESTADO.get(estado, "UNAVAILABLE")


def desenhar_estado(painter: QPainter, rect: QRect, snapshot) -> None:
    """Selo de estado (BUY/SELL/ULTRA/BALANÇO/UNAVAILABLE) — uma leitura
    compacta para caber ao lado do trilho de pressão já existente em
    `nexo/pressao.py`. Texto sempre presente, nunca só cor."""

    if rect.height() < 10 or rect.width() < 40:
        return
    if snapshot is None:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "DOMINÂNCIA · UNAVAILABLE")
        return

    cor = _COR_POR_ESTADO.get(snapshot.estado, tema_asg.NEXO_MUTED)
    rotulo = _ROTULO_POR_ESTADO.get(snapshot.estado, "UNAVAILABLE")
    painter.setFont(tokens.fonte_ui(8, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"DOMINÂNCIA {rotulo}")
