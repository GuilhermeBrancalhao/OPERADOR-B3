"""Regiao GRAFICO DE CANDLES (x 0,63-0,98 · y 0,34-0,85).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_candles_nexo``. E a
maior area do quadro, como no material de referencia: a evidencia decisoria
mora no grafico.

Os candles agregam **somente negocios ja recebidos** — nao ha OHLC externo,
nao ha lookahead e nao ha liquidez sintetizada. Preco chega em ``int`` de ticks
e vira pixel apenas aqui. Etiquetas de preco na borda esquerda, faixa tracejada
e anotacao junto aos candles sao trabalho da parte 8.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPen, QPolygon

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

AMOSTRAS_MAX = 360
VELAS_MIN = 18
VELAS_MAX = 42
LARGURA_EIXO = 58
LINHAS_GRADE = 6


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 60 or rect.width() < 120:
        return
    amostras = estado.serie[-AMOSTRAS_MAX:]
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)
    if len(amostras) < 2:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "AGUARDANDO NEGOCIOS OBSERVADOS")
        return

    n_velas = min(VELAS_MAX, max(VELAS_MIN, rect.width() // 17))
    passo = max(1, (len(amostras) + n_velas - 1) // n_velas)
    velas = [amostras[inicio:inicio + passo] for inicio in range(0, len(amostras), passo)]
    velas = [grupo for grupo in velas if grupo]
    precos = [item[1] for item in amostras]
    minimo, maximo = min(precos), max(precos)
    margem = max(1, (maximo - minimo) // 12)
    minimo -= margem
    maximo += margem
    escala = max(1, maximo - minimo)

    area_plot = QRect(rect.left(), rect.top() + 14,
                      max(80, rect.width() - LARGURA_EIXO), max(60, rect.height() - 46))
    area_volume = QRect(area_plot.left(), area_plot.bottom() + 4, area_plot.width(),
                        max(12, rect.bottom() - area_plot.bottom() - 18))

    painter.fillRect(area_plot, tema_asg.NEXO_PAINEL_ALTO)
    for indice in range(LINHAS_GRADE):
        y = area_plot.top() + round(indice * max(1, area_plot.height() - 1) / (LINHAS_GRADE - 1))
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawLine(area_plot.left(), y, area_plot.right(), y)
        valor = maximo - round(indice * escala / (LINHAS_GRADE - 1))
        texto = formato.formatar_preco(estado.grid, valor)
        painter.setFont(tokens.fonte_numero(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(QRect(area_plot.right() + 4, y - 7, LARGURA_EIXO - 6, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{texto[0]}{texto[1]}")
    painter.setPen(tema_asg.NEXO_GRADE)
    for indice in range(1, 7):
        x = area_plot.left() + round(indice * area_plot.width() / 7)
        painter.drawLine(x, area_plot.top(), x, area_volume.bottom())

    def y_preco(valor: int) -> int:
        return area_plot.bottom() - round(
            (valor - minimo) * max(1, area_plot.height() - 1) / escala)

    recentes = [item[1] for item in amostras[-max(8, len(amostras) // 5):]]
    faixa_min, faixa_max = min(recentes), max(recentes)
    if faixa_max > faixa_min:
        faixa = QRect(area_plot.left(), y_preco(faixa_max), area_plot.width(),
                      max(2, y_preco(faixa_min) - y_preco(faixa_max)))
        painter.fillRect(faixa, tema_asg.NEXO_CIANO_FAIXA)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(faixa.adjusted(5, 1, -5, -1),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         "FAIXA OBSERVADA")

    max_volume = max(1, max(sum(item[3] for item in grupo) for grupo in velas))
    largura = max(3, area_plot.width() // max(1, len(velas) * 2))
    fechamentos: list[QPoint] = []
    medias: list[QPoint] = []
    historico: list[int] = []
    for indice, grupo in enumerate(velas):
        abertura, fechamento = grupo[0][1], grupo[-1][1]
        maxima = max(item[1] for item in grupo)
        minima = min(item[1] for item in grupo)
        x = area_plot.left() + 4 + round(
            indice * max(1, area_plot.width() - 9) / max(1, len(velas) - 1))
        cor = tema_asg.NEXO_VERDE if fechamento >= abertura else tema_asg.NEXO_ROSA
        painter.setPen(QPen(cor, 1))
        painter.drawLine(x, y_preco(maxima), x, y_preco(minima))
        y_abertura, y_fechamento = y_preco(abertura), y_preco(fechamento)
        painter.fillRect(QRect(x - largura // 2, min(y_abertura, y_fechamento), largura,
                               max(2, abs(y_fechamento - y_abertura))), cor)
        volume = sum(item[3] for item in grupo)
        altura_volume = max(2, round(volume * max(1, area_volume.height() - 2) / max_volume))
        painter.fillRect(QRect(x - largura // 2, area_volume.bottom() - altura_volume,
                               largura, altura_volume), cor)
        fechamentos.append(QPoint(x, y_fechamento))
        historico.append(fechamento)
        janela = historico[-min(6, len(historico)):]
        medias.append(QPoint(x, y_preco(round(sum(janela) / len(janela)))))

    if len(fechamentos) >= 2:
        painter.setPen(QPen(tema_asg.NEXO_CIANO, 1))
        painter.drawPolyline(QPolygon(fechamentos))
        painter.setPen(QPen(tema_asg.NEXO_AMARELO, 1, Qt.PenStyle.DotLine))
        painter.drawPolyline(QPolygon(medias))
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_AMARELO)
        painter.drawText(QRect(area_plot.left() + 5, area_plot.top() + 3, 110, 12),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "MEDIA OBS. 6")

    ultimo_valor = amostras[-1][1]
    y_ultimo = y_preco(ultimo_valor)
    painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
    painter.drawLine(area_plot.left(), y_ultimo, area_plot.right(), y_ultimo)
    ultimo = formato.formatar_preco(estado.grid, ultimo_valor)
    capsula = QRect(area_plot.right() + 2, y_ultimo - 9, LARGURA_EIXO - 4, 18)
    painter.fillRect(capsula, tema_asg.NEXO_CIANO)
    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_FUNDO)
    painter.drawText(capsula, Qt.AlignmentFlag.AlignCenter, f"{ultimo[0]}{ultimo[1]}")

    # Niveis consultivos so aparecem quando a decisao os publicou. Sao
    # ETIQUETAS DE LEITURA: nao ha acao, ordem ou clique associado a elas.
    decisao = estado.snapshot.decisao
    niveis = (("STOP", decisao.stop, tema_asg.NEXO_ROSA),
              ("A1", decisao.alvo_1, tema_asg.NEXO_VERDE),
              ("A2", decisao.alvo_2, tema_asg.NEXO_VERDE),
              ("A3", decisao.alvo_3, tema_asg.NEXO_VERDE))
    for indice, (nome, valor, cor) in enumerate(niveis):
        if valor == "—":
            continue
        y = area_plot.top() + 14 + indice * 14
        painter.setPen(QPen(cor, 1, Qt.PenStyle.DotLine))
        painter.drawLine(area_plot.left(), y, area_plot.right() - 70, y)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(cor)
        painter.drawText(QRect(area_plot.right() - 67, y - 7, 65, 14),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"{nome} {valor}")

    inicio = formato.formatar_hora_ns(amostras[0][0])
    fim = formato.formatar_hora_ns(amostras[-1][0])
    rodape = QRect(area_plot.left(), rect.bottom() - 13, area_plot.width(), 13)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, inicio)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fim)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter,
                     "VOLUME OBSERVADO · OHLC CAUSAL")
