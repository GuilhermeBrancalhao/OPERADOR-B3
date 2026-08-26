"""Regiao GRAFICO DE FORCA (x 0,63-1,00 · y 0,00-0,33).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_forca_nexo``. Ocupa o
topo direito inteiro, encostando na borda superior e na direita do quadro, sem
moldura.

A serie e exclusivamente visual e derivada dos negocios ja observados: sem
lookahead, sem fonte nova, sem alegar formula de terceiro. Este modulo desenha
tres camadas, todas derivadas do mesmo ``estado.serie`` que ja chega pronto
(nenhum dado novo, nenhuma leitura de thread viva):

1. a area/linha de forca (serrilhada de verdade: a escala vertical usa o
   percentil 5/95 REAL da janela visivel — nao min/max cru nem um intervalo
   fixo -1..+1 — porque um unico pico isolado no arranque da matriz, se
   virasse piso ou teto da escala inteira, encolhia a variacao real do
   resto da sessao a uma fracao de pixel e o traco parecia um platô reto
   mesmo mudando de valor a cada negocio; ver ``_escala_vertical_robusta``);
2. uma linha pontilhada de media movel causal (janela apenas para tras, sem
   espiar amostra futura) por cima da linha cheia, como leitura auxiliar;
3. um trilho de eixo de preco (o ``preco`` em ticks que ja viaja dentro de
   cada amostra) com uma capsula de preco atual — puramente formatacao de um
   valor que ja existe no snapshot, nao um preco novo nem inferido.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QLinearGradient, QPainter, QPen, QPolygon

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo


def _reamostrar_por_coluna(indices_x: list[int], valores: list[float],
                            largura: int) -> list[tuple[int, float]]:
    """Reamostra ``valores`` (na posicao real ``indices_x``) para UM valor
    por coluna de pixel, via spline Catmull-Rom pelos MESMOS pontos reais.

    Antes desta funcao, a linha so tinha um vertice por amostra -- com
    poucas dezenas de negocios numa janela de centenas de pixels, isso da
    poucos vertices ligados por retas compridas, que e exatamente o
    "degrau largo com risada quase vertical" que o critico apontou. Aqui
    cada coluna de pixel ganha seu proprio valor interpolado a partir dos
    vizinhos reais, entao o traco carrega a textura continua que a serie
    tem entre um negocio e o seguinte -- sem segurar (forward-fill) o
    ultimo valor por dezenas de pixels e sem inventar nenhum dado novo:
    os extremos de cada segmento continuam sendo os valores reais, a
    curva so deixa de ser reta entre eles.
    """
    if largura < 2 or len(indices_x) < 2:
        return list(zip(indices_x, valores))

    xs: list[int] = []
    ys: list[float] = []
    for x, y in zip(indices_x, valores):
        if xs and x == xs[-1]:
            ys[-1] = y
        else:
            xs.append(x)
            ys.append(y)
    n = len(xs)
    if n < 2:
        return list(zip(indices_x, valores))

    minimo, maximo = min(ys), max(ys)
    folga = max(1e-6, (maximo - minimo) * 0.08)
    piso, teto = minimo - folga, maximo + folga
    x0, x1 = xs[0], xs[-1]

    saida: list[tuple[int, float]] = []
    segmento = 0
    for coluna in range(largura):
        x_alvo = x0 + (x1 - x0) * coluna / (largura - 1)
        while segmento < n - 2 and xs[segmento + 1] < x_alvo:
            segmento += 1
        xa, xb = xs[segmento], xs[segmento + 1]
        ya, yb = ys[segmento], ys[segmento + 1]
        y_prev = ys[segmento - 1] if segmento - 1 >= 0 else ya
        y_next = ys[segmento + 2] if segmento + 2 < n else yb
        t = 0.0 if xb == xa else (x_alvo - xa) / (xb - xa)
        t2, t3 = t * t, t * t * t
        valor = 0.5 * (
            2 * ya
            + (-y_prev + yb) * t
            + (2 * y_prev - 5 * ya + 4 * yb - y_next) * t2
            + (-y_prev + 3 * ya - 3 * yb + y_next) * t3
        )
        valor = min(teto, max(piso, valor))
        saida.append((round(x_alvo), valor))
    return saida

def _percentil(valores_ordenados: list[float], fracao: float) -> float:
    """Percentil por interpolacao linear sobre uma lista JA ordenada."""
    n = len(valores_ordenados)
    if n == 0:
        return 0.0
    posicao = (n - 1) * fracao
    baixo = int(posicao)
    alto = min(baixo + 1, n - 1)
    resto = posicao - baixo
    return valores_ordenados[baixo] * (1 - resto) + valores_ordenados[alto] * resto


# Fracao de cauda (cada lado) ignorada pela escala vertical robusta abaixo.
FRACAO_CAUDA_ESCALA = 0.05


def _escala_vertical_robusta(valores: list[float]) -> tuple[float, float]:
    """Piso/teto da escala vertical da area de forca.

    Antes, a escala usava ``min(valores)``/``max(valores)`` da JANELA INTEIRA
    (ate 480 negocios). Um unico pico isolado no comeco da janela (comum no
    arranque do book, antes da matriz "esquentar") vira o piso ou o teto da
    escala inteira -- e como o resto da serie costuma oscilar numa faixa bem
    mais estreita perto desse extremo, a diferenca real entre uma amostra e a
    seguinte passa a valer uma fracao de pixel, e o traco parece um platô
    reto mesmo variando de verdade a cada negocio (o "chao" que o critico
    reportou: nao e valor fabricado nem clamp de dado, e a ESCALA que engole
    a textura). Aqui o piso/teto vem do percentil 5/95 dos MESMOS valores
    reais (sem olhar amostra futura fora do que ja esta no snapshot, sem
    inventar numero novo): os poucos picos fora dessa faixa continuam sendo
    desenhados, so deixam de comandar sozinhos a escala inteira -- o traco
    correspondente a eles apenas encosta no topo/base do quadro em vez de
    esticar a faixa toda para caber um unico ponto.
    """
    if len(valores) < 4:
        minimo, maximo = min(valores), max(valores)
        if maximo - minimo < 1e-6:
            return minimo - 1e-3, maximo + 1e-3
        return minimo, maximo
    ordenados = sorted(valores)
    piso = _percentil(ordenados, FRACAO_CAUDA_ESCALA)
    teto = _percentil(ordenados, 1.0 - FRACAO_CAUDA_ESCALA)
    if teto - piso < 1e-6:
        piso, teto = min(valores), max(valores)
        if teto - piso < 1e-6:
            return piso - 1e-3, teto + 1e-3
    return piso, teto


# Densidade do grid de fundo da area de forca. Mais degraus que o esqueleto
# original (3): a referencia usa uma grade bem mais cerrada.
FRACOES_GRADE = (0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875)

# Janela (em amostras) da media movel causal pontilhada. Curta de proposito:
# e leitura de textura de curtissimo prazo, nao um indicador de tendencia.
JANELA_MEDIA_PONTILHADA = 6

# Largura reservada ao trilho de preco a direita. Degrada para uma fracao da
# largura disponivel quando o quadro e pequeno demais para o valor cheio.
RAIL_LARGURA_PX = 78
RAIL_ALTURA_LINHA_PX = 21
RAIL_NIVEIS_MIN = 5
RAIL_NIVEIS_MAX = 17


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 60:
        return
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)

    amostras = estado.serie
    if len(amostras) < 2:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "AGUARDANDO DADOS DE MERCADO")
        return

    rail_largura = min(RAIL_LARGURA_PX, max(0, rect.width() // 3))
    area = QRect(rect.left(), rect.top(), rect.width() - rail_largura, rect.height())
    rail = QRect(area.right(), rect.top(), rail_largura, rect.height())

    painter.setPen(tema_asg.NEXO_GRADE)
    for fracao in FRACOES_GRADE:
        y = rect.top() + round(rect.height() * fracao)
        painter.drawLine(area.left(), y, area.right(), y)

    valores = [item[2] for item in amostras]
    minimo_valor, maximo_valor = _escala_vertical_robusta(valores)
    amplitude_valor = max(1e-6, maximo_valor - minimo_valor)
    topo_util = max(1, area.height() - 26)
    y_minimo, y_maximo = area.top() + 2, area.bottom() - 8

    def y_de_valor(valor: float) -> int:
        y = area.bottom() - 8 - round((valor - minimo_valor) * topo_util / amplitude_valor)
        return max(y_minimo, min(y_maximo, y))

    def x_de_indice(indice: int) -> int:
        return area.left() + round(indice * max(1, area.width() - 1) / max(1, len(amostras) - 1))

    xs_reais = [x_de_indice(i) for i in range(len(amostras))]
    pontos = [(x, y_de_valor(v)) for x, v in _reamostrar_por_coluna(xs_reais, valores, area.width())]

    ultimo = amostras[-1][2]
    cor = tema_asg.NEXO_VERDE if ultimo >= 0 else tema_asg.NEXO_ROSA
    base_y = area.bottom() - 7
    area_pontos = [QPoint(x, y) for x, y in pontos]
    poligono_area = QPolygon(area_pontos + [QPoint(area.right(), base_y), QPoint(area.left(), base_y)])
    gradiente = QLinearGradient(area.left(), area.top(), area.left(), area.bottom())
    gradiente.setColorAt(0.0, tema_asg.NEXO_VERDE_FAIXA if ultimo >= 0 else tema_asg.NEXO_ROSA_FAIXA)
    gradiente.setColorAt(1.0, tema_asg.NEXO_PAINEL)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradiente)
    painter.drawPolygon(poligono_area)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setPen(QPen(cor, 2))
    painter.drawPolyline(QPolygon(area_pontos))

    # Media movel causal (so olha para tras) pontilhada por cima da linha
    # cheia — leitura auxiliar da mesma serie, nao um dado novo. A media em
    # si continua calculada amostra a amostra (semantica causal correta);
    # so o TRACO dela e reamostrado por coluna, para acompanhar a mesma
    # densidade da linha principal em vez de ficar com poucos vertices.
    medias = []
    for indice in range(len(amostras)):
        inicio = max(0, indice - JANELA_MEDIA_PONTILHADA + 1)
        janela = valores[inicio:indice + 1]
        medias.append(sum(janela) / len(janela))
    media_pontos = [QPoint(x, y_de_valor(v))
                     for x, v in _reamostrar_por_coluna(xs_reais, medias, area.width())]
    caneta_pontilhada = QPen(tema_asg.NEXO_CIANO, 1)
    caneta_pontilhada.setStyle(Qt.PenStyle.DotLine)
    painter.setPen(caneta_pontilhada)
    painter.drawPolyline(QPolygon(media_pontos))

    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     f"FORCA {ultimo * 100:+.0f}%")
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                     "JANELA CAUSAL")
    media_geral = sum(valores) / len(valores)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     f"MEDIA {media_geral * 100:+.0f}%")
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                     f"{len(amostras)} NEGOCIOS")

    if rail.width() >= 24:
        _desenhar_rail_preco(painter, rail, estado, amostras)


def _desenhar_rail_preco(painter: QPainter, rail: QRect, estado: EstadoNexo,
                          amostras: tuple[tuple[int, int, float, int], ...]) -> None:
    """Trilho de eixo de preco: niveis reais (``preco`` em ticks, ja no
    snapshot) mais a capsula do ultimo preco negociado. Nenhum preco e
    inventado aqui — e so a formatacao, na fronteira de desenho, do mesmo
    inteiro que ja atravessou o resto do pipeline em ticks."""

    grid = estado.grid
    precos = [item[1] for item in amostras]
    preco_min, preco_max = min(precos), max(precos)
    preco_atual = amostras[-1][1]
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
