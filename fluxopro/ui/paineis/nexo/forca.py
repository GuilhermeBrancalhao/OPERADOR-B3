"""Região GRAFICO DE FORCA / "4R" (x 0,63-1,00 · y 0,00-0,33).

Renko de 4 pontos — blocos por deslocamento de preço, nunca por tempo. Ver
`fluxopro/analytics/renko.py` para os rótulos de confiança
(CONFIRMADO/IMPRECISO/AUSENTE NA FONTE) de cada regra desenhada aqui:

- os tijolos em si (verde=alta, vermelho/rosa=baixa);
- a "cor interna" (fase): rótulo TENDÊNCIA (verde) / PERDENDO FORÇA (cinza) /
  POSSÍVEL INVERSÃO (vermelho) — alerta antecipado, nunca um sinal de entrada;
- os alvos A1/A2/A3 de cada lado, como linhas de referência tracejadas —
  nunca clicáveis, nunca uma ordem: a região do alvo positivo é o pior preço
  para vender a favor do movimento, a do alvo negativo o pior para comprar
  (regra de disciplina do autor, replicada como leitura, não como recomendação
  automática de entrada).

O trilho de eixo de preço à direita é o mesmo de antes: formatação de um
preço que já existe no snapshot, nunca um preço novo ou inferido.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPen

from fluxopro.analytics.renko import FaseRenko
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

# Densidade do grid de fundo.
FRACOES_GRADE = (0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875)

# Largura reservada ao trilho de preco a direita. Degrada para uma fracao da
# largura disponivel quando o quadro e pequeno demais para o valor cheio.
RAIL_LARGURA_PX = 78
RAIL_ALTURA_LINHA_PX = 21
RAIL_NIVEIS_MIN = 5
RAIL_NIVEIS_MAX = 17

# Quantos tijolos, no maximo, cabem visiveis de uma vez — mais que isso e
# cada tijolo vira uma coluna fina demais para ler a direcao. Poucos tijolos
# largos, com vao real entre eles, leem melhor que muitos colados.
MAX_TIJOLOS_VISIVEIS = 16
LARGURA_MIN_TIJOLO_PX = 18
VAO_ENTRE_TIJOLOS_PX = 6

_ROTULO_FASE = {
    FaseRenko.TENDENCIA: "TENDENCIA",
    FaseRenko.PERDENDO_FORCA: "PERDENDO FORCA",
    FaseRenko.POSSIVEL_INVERSAO: "POSSIVEL INVERSAO",
    FaseRenko.INDEFINIDA: "AGUARDANDO TIJOLOS",
}


def _cor_fase(fase: FaseRenko) -> object:
    if fase is FaseRenko.TENDENCIA:
        return tema_asg.NEXO_VERDE
    if fase is FaseRenko.POSSIVEL_INVERSAO:
        return tema_asg.NEXO_ROSA
    if fase is FaseRenko.PERDENDO_FORCA:
        return tema_asg.NEXO_MUTED
    return tema_asg.NEXO_MUTED


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 60:
        return
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)

    tijolos = estado.tijolos_renko
    if len(tijolos) < 1:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "4R · AGUARDANDO DESLOCAMENTO DE PRECO")
        return

    rail_largura = min(RAIL_LARGURA_PX, max(0, rect.width() // 3))
    area = QRect(rect.left(), rect.top(), rect.width() - rail_largura, rect.height())
    rail = QRect(area.right(), rect.top(), rail_largura, rect.height())

    painter.setPen(tema_asg.NEXO_GRADE)
    for fracao in FRACOES_GRADE:
        y = rect.top() + round(rect.height() * fracao)
        painter.drawLine(area.left(), y, area.right(), y)

    visiveis = tijolos[-MAX_TIJOLOS_VISIVEIS:]
    precos = [t.abertura for t in visiveis] + [t.fechamento for t in visiveis]
    preco_min, preco_max = min(precos), max(precos)
    if preco_max == preco_min:
        preco_min -= 1
        preco_max += 1
    amplitude = preco_max - preco_min

    topo_reservado = 18
    base_reservada = 20
    zona_util = max(1, area.height() - topo_reservado - base_reservada)

    def y_de_preco(preco: float) -> int:
        fracao = (preco - preco_min) / amplitude
        return area.bottom() - base_reservada - round(fracao * zona_util)

    largura_tijolo = max(LARGURA_MIN_TIJOLO_PX, area.width() // max(1, len(visiveis)))
    x = area.right() - largura_tijolo * len(visiveis)
    for tijolo in visiveis:
        y_abertura = y_de_preco(tijolo.abertura)
        y_fechamento = y_de_preco(tijolo.fechamento)
        topo = min(y_abertura, y_fechamento)
        altura = max(2, abs(y_fechamento - y_abertura))
        cor = tema_asg.NEXO_VERDE if tijolo.direcao > 0 else tema_asg.NEXO_ROSA
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cor)
        painter.drawRect(QRect(x + VAO_ENTRE_TIJOLOS_PX // 2, topo,
                               max(1, largura_tijolo - VAO_ENTRE_TIJOLOS_PX), altura))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x += largura_tijolo

    alvos = estado.alvos_renko
    if alvos is not None:
        caneta_alvo = QPen(tema_asg.NEXO_AMARELO, 1, Qt.PenStyle.DashLine)
        painter.setFont(tokens.fonte_rotulo(7))
        for indice, preco_alvo in enumerate(alvos.positivos, start=1):
            y = y_de_preco(preco_alvo)
            if area.top() <= y <= area.bottom():
                painter.setPen(caneta_alvo)
                painter.drawLine(area.left(), y, area.right(), y)
                painter.setPen(tema_asg.NEXO_AMARELO)
                painter.drawText(area.left() + 3, y - 2, f"A{indice}+")
        for indice, preco_alvo in enumerate(alvos.negativos, start=1):
            y = y_de_preco(preco_alvo)
            if area.top() <= y <= area.bottom():
                painter.setPen(caneta_alvo)
                painter.drawLine(area.left(), y, area.right(), y)
                painter.setPen(tema_asg.NEXO_CIANO)
                painter.drawText(area.left() + 3, y + 9, f"A{indice}-")

    fase = estado.fase_renko if isinstance(estado.fase_renko, FaseRenko) else FaseRenko.INDEFINIDA
    cor_fase = _cor_fase(fase)
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.setPen(cor_fase)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     "4R")
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                     "RENKO · 4 PTS")
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(cor_fase)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     _ROTULO_FASE[fase])
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                     f"{len(tijolos)} TIJOLOS")

    if rail.width() >= 24:
        _desenhar_rail_preco(painter, rail, estado, preco_min, preco_max, tijolos[-1].fechamento)


def _desenhar_rail_preco(painter: QPainter, rail: QRect, estado: EstadoNexo,
                          preco_min: int, preco_max: int, preco_atual: int) -> None:
    """Trilho de eixo de preco: niveis reais (ja em ticks) mais a capsula do
    ultimo fechamento de tijolo. Nenhum preco e inventado aqui."""

    grid = estado.grid
    if preco_max == preco_min:
        preco_min -= 1
        preco_max += 1
    amplitude_preco = preco_max - preco_min

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(rail.left(), rail.top(), rail.left(), rail.bottom())

    zona_util = max(1, rail.height() - 16)

    def y_de_preco(preco: float) -> int:
        fracao = (preco - preco_min) / amplitude_preco
        return rail.bottom() - 8 - round(fracao * zona_util)

    niveis = max(RAIL_NIVEIS_MIN, min(RAIL_NIVEIS_MAX, rail.height() // RAIL_ALTURA_LINHA_PX))
    limiar_destaque = amplitude_preco * 0.06
    painter.setFont(tokens.fonte_numero(7))
    for indice in range(niveis):
        preco_nivel = preco_min + amplitude_preco * indice / max(1, niveis - 1)
        y = y_de_preco(preco_nivel)
        texto = formato.preco_completo(grid, round(preco_nivel))
        proximo_do_atual = abs(preco_nivel - preco_atual) <= limiar_destaque
        cor_nivel = (tema_asg.NEXO_TEXTO if proximo_do_atual
                     else tema_asg.NEXO_CIANO if indice % 2 == 0 else tema_asg.NEXO_MUTED)
        painter.setPen(cor_nivel)
        painter.drawText(QRect(rail.left() + 4, y - 7, rail.width() - 8, 14),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         texto)

    texto_atual = formato.preco_completo(grid, preco_atual)
    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    largura_texto = painter.fontMetrics().horizontalAdvance(texto_atual) + 12
    largura_texto = min(largura_texto, rail.width() - 4)
    y_atual = max(rail.top() + 8, min(rail.bottom() - 8, y_de_preco(preco_atual)))
    capsula = QRect(rail.right() - largura_texto - 2, y_atual - 8, largura_texto, 16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
    painter.drawRoundedRect(capsula, 3, 3)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(tema_asg.NEXO_AMARELO, 1))
    painter.drawRoundedRect(capsula, 3, 3)
    painter.drawText(capsula, Qt.AlignmentFlag.AlignCenter, texto_atual)
