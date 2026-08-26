"""Regiao GRAFICO DE CANDLES · M15 (x 0,63-0,98 · y 0,34-0,85).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_candles_nexo``. E a
maior area do quadro, como no material de referencia: a evidencia decisoria
mora no grafico.

Candles vem de ``estado.candles_m15`` — OHLCV real de 15 minutos, agregado
por ``fluxopro/analytics/candle_temporal.py`` a partir dos MESMOS negocios
que alimentam `estado.serie`. Nao ha OHLC externo, nao ha lookahead e nao ha
liquidez sintetizada. Preco chega em ``int`` de ticks e vira pixel apenas
aqui, na fronteira de desenho (``y_preco`` e ``formato.preco_completo``);
nada volta a ser gravado no snapshot.

Etiquetas de preco na borda esquerda, faixa tracejada e anotacao junto aos
candles: os niveis consultivos (STOP/A1/A2/A3) sao ancorados na altura real
do preco quando o campo chega como inteiro de ticks; se chegar apenas como
texto ja formatado (compat com uma fonte antiga do modelo), a etiqueta ainda
aparece — em pilula, na borda esquerda — so que sem a ancoragem por altura.
Sao ETIQUETAS DE LEITURA: nenhuma delas e clicavel, nenhuma delas dispara
ordem.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen, QPolygon

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

VELAS_MIN = 24
VELAS_MAX = 64
LARGURA_EIXO = 58
LARGURA_ROTULO_NIVEL = 64
LINHAS_GRADE = 6


def _pilula_preco(
    painter: QPainter,
    x_ancora: int,
    y_centro: int,
    texto: str,
    cor,
    *,
    alinhar_direita: bool,
    largura_max: int,
) -> None:
    """Pilula (capsula arredondada) com fundo colorido e texto centralizado.

    Usada para toda etiqueta de preco ancorada num ponto do grafico — borda
    esquerda dos niveis consultivos, limites da faixa observada e o preco
    corrente na borda direita. Um unico desenho para as tres, para nao
    divergirem em raio, fonte ou contraste de texto.
    """
    metrica: QFontMetrics = painter.fontMetrics()
    largura = min(largura_max, metrica.horizontalAdvance(texto) + 12)
    altura = metrica.height() + 4
    if alinhar_direita:
        area = QRect(x_ancora - largura, y_centro - altura // 2, largura, altura)
    else:
        area = QRect(x_ancora, y_centro - altura // 2, largura, altura)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    painter.drawRoundedRect(area, altura / 2, altura / 2)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(tema_asg.NEXO_FUNDO)
    painter.drawText(area, Qt.AlignmentFlag.AlignCenter, texto)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 60 or rect.width() < 120:
        return
    candles = estado.candles_m15
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)
    if len(candles) < 2:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "AGUARDANDO CANDLES M15")
        return

    precos = [c.high for c in candles] + [c.low for c in candles]
    minimo, maximo = min(precos), max(precos)
    margem = max(1, (maximo - minimo) // 12)
    minimo -= margem
    maximo += margem
    escala = max(1, maximo - minimo)

    area_plot = QRect(rect.left() + LARGURA_ROTULO_NIVEL, rect.top() + 14,
                      max(80, rect.width() - LARGURA_EIXO - LARGURA_ROTULO_NIVEL),
                      max(60, rect.height() - 46))
    area_volume = QRect(area_plot.left(), area_plot.bottom() + 4, area_plot.width(),
                        max(12, rect.bottom() - area_plot.bottom() - 18))

    # Densidade das velas segue a largura REAL do plot (nao a do quadro
    # inteiro) — um plot estreito nao pode herdar a mesma contagem de velas
    # de um plot largo, senao cada vela vira uma lasca. Cada vela ja e um
    # candle M15 fechado (ou o em formacao) — nao ha reagrupamento aqui.
    n_velas = min(VELAS_MAX, max(VELAS_MIN, area_plot.width() // 11))
    velas = list(candles[-n_velas:])

    painter.fillRect(area_plot, tema_asg.NEXO_PAINEL_ALTO)

    def y_preco(valor: int) -> int:
        return area_plot.bottom() - round(
            (valor - minimo) * max(1, area_plot.height() - 1) / escala)

    ultimo_valor = candles[-1].close
    y_ultimo = y_preco(ultimo_valor)
    altura_capsula_ultimo = 18
    exclusao_topo = y_ultimo - altura_capsula_ultimo // 2 - 2
    exclusao_base = y_ultimo + altura_capsula_ultimo // 2 + 2

    # A calha do eixo (faixa a direita do plot onde os ticks moram) usa o
    # MESMO fundo escuro do plot — nunca fica transparente, nunca herda a
    # cor de um vizinho. E os valores da escada vem da faixa REAL de precos
    # (min..max em ticks inteiros), nunca de uma fracao fixa de altura: com
    # a amostra quase parada, 6 linhas por fracao de altura repetiam o
    # MESMO preco formatado em ate 4 ticks seguidos. Aqui o numero de linhas
    # se adapta a quantos ticks distintos a faixa realmente comporta, e cada
    # linha nasce do proprio valor (y_preco), nunca o inverso — garante
    # escada monotonica, sem repeticao.
    gutter_eixo = QRect(area_plot.right(), area_plot.top(), LARGURA_EIXO,
                        area_volume.bottom() - area_plot.top())
    painter.fillRect(gutter_eixo, tema_asg.NEXO_PAINEL_ALTO)
    n_linhas = max(2, min(LINHAS_GRADE, escala + 1))
    valor_anterior: int | None = None
    for indice in range(n_linhas):
        valor = maximo - round(indice * escala / max(1, n_linhas - 1))
        if valor_anterior is not None and valor == valor_anterior:
            continue
        valor_anterior = valor
        y = y_preco(valor)
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawLine(area_plot.left(), y, area_plot.right(), y)
        if exclusao_topo <= y <= exclusao_base:
            # A pilula do ultimo preco (desenhada mais abaixo, na borda
            # direita) ja mostra este mesmo valor — nao empilhar o rotulo
            # do tick por baixo dela, ou ele fica ilegivel sob a pilula
            # opaca (era assim que um tick da escada "sumia").
            continue
        texto = formato.formatar_preco(estado.grid, valor)
        painter.setFont(tokens.fonte_numero(7))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(QRect(area_plot.right() + 4, y - 7, LARGURA_EIXO - 6, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{texto[0]}{texto[1]}")
    painter.setPen(tema_asg.NEXO_GRADE)
    for indice in range(1, 7):
        x = area_plot.left() + round(indice * area_plot.width() / 7)
        painter.drawLine(x, area_plot.top(), x, area_volume.bottom())

    # Faixa observada: intervalo das amostras recentes. Alem do preenchimento
    # (ja existia), a borda tracejada e as pilulas de limite na borda
    # esquerda deixam a REGIAO explicita — nao so uma mancha de cor.
    recentes_candles = candles[-max(8, len(candles) // 5):]
    recentes = [c.high for c in recentes_candles] + [c.low for c in recentes_candles]
    faixa_min, faixa_max = min(recentes), max(recentes)
    if faixa_max > faixa_min:
        y_topo, y_base = y_preco(faixa_max), y_preco(faixa_min)
        faixa = QRect(area_plot.left(), y_topo, area_plot.width(), max(2, y_base - y_topo))
        painter.fillRect(faixa, tema_asg.NEXO_CIANO_FAIXA)
        # Mesma correcao de ancoragem dos niveis: a pilula de limite da
        # faixa mora em rect.left() (gutter reservado), entao a borda
        # tracejada tem que nascer dali tambem — senao a pilula fica
        # boiando a alguns pixels do proprio traco que ela rotula. A borda
        # da base so estica ate a pilula quando a pilula da base de fato
        # vai aparecer (mesma condicao de espaco usada mais abaixo).
        mostra_pilula_base = faixa.bottom() - faixa.top() > 16
        painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), faixa.top(), faixa.right(), faixa.top())
        x_base = rect.left() if mostra_pilula_base else faixa.left()
        painter.drawLine(x_base, faixa.bottom(), faixa.right(), faixa.bottom())
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(faixa.adjusted(5, 1, -5, -1),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         "FAIXA OBSERVADA")
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        _pilula_preco(painter, rect.left(), faixa.top(),
                     formato.preco_completo(estado.grid, faixa_max), tema_asg.NEXO_CIANO,
                     alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)
        if mostra_pilula_base:
            painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
            _pilula_preco(painter, rect.left(), faixa.bottom(),
                         formato.preco_completo(estado.grid, faixa_min), tema_asg.NEXO_CIANO,
                         alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)

    max_volume = max(1, max(candle.volume for candle in velas))
    largura = max(3, area_plot.width() // max(1, len(velas) * 2))
    fechamentos: list[QPoint] = []
    medias: list[QPoint] = []
    historico: list[int] = []
    for indice, candle in enumerate(velas):
        abertura, fechamento = candle.open, candle.close
        maxima, minima = candle.high, candle.low
        x = area_plot.left() + 4 + round(
            indice * max(1, area_plot.width() - 9) / max(1, len(velas) - 1))
        cor = tema_asg.NEXO_VERDE if fechamento >= abertura else tema_asg.NEXO_ROSA
        painter.setPen(QPen(cor, 1))
        painter.drawLine(x, y_preco(maxima), x, y_preco(minima))
        y_abertura, y_fechamento = y_preco(abertura), y_preco(fechamento)
        painter.fillRect(QRect(x - largura // 2, min(y_abertura, y_fechamento), largura,
                               max(2, abs(y_fechamento - y_abertura))), cor)
        volume = candle.volume
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
                         "M15 · MEDIA 6")

    # Anotacao junto ao ultimo negocio realmente observado — nao e um alvo
    # nem uma leitura preditiva, so identifica onde o ultimo preco recebido
    # ficou no grafico (mesmo dado do rodape "OHLC CAUSAL").
    if fechamentos:
        ultimo_ponto = fechamentos[-1]
        texto_tag = "ULTIMO NEGOCIO OBSERVADO"
        painter.setFont(tokens.fonte_rotulo(6))
        metrica_tag = painter.fontMetrics()
        largura_tag = metrica_tag.horizontalAdvance(texto_tag) + 10
        altura_tag = metrica_tag.height() + 4
        if ultimo_ponto.y() - area_plot.top() > altura_tag + 6:
            y_tag = ultimo_ponto.y() - altura_tag - 6
        else:
            y_tag = min(area_plot.bottom() - altura_tag, ultimo_ponto.y() + 6)
        x_tag = min(area_plot.right() - largura_tag,
                   max(area_plot.left(), ultimo_ponto.x() - largura_tag // 2))
        tag = QRect(x_tag, y_tag, largura_tag, altura_tag)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
        painter.drawRoundedRect(tag, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, texto_tag)

    # ultimo_valor/y_ultimo ja foram calculados acima (mesma fronteira
    # y_preco), reaproveitados aqui para a linha tracejada + pilula.
    painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
    painter.drawLine(area_plot.left(), y_ultimo, area_plot.right(), y_ultimo)
    ultimo = formato.formatar_preco(estado.grid, ultimo_valor)
    capsula = QRect(area_plot.right() + 2, y_ultimo - 9, LARGURA_EIXO - 4, 18)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_CIANO)
    painter.drawRoundedRect(capsula, 9, 9)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_FUNDO)
    painter.drawText(capsula, Qt.AlignmentFlag.AlignCenter, f"{ultimo[0]}{ultimo[1]}")

    # Niveis consultivos so aparecem quando a decisao os publicou. Sao
    # ETIQUETAS DE LEITURA: nao ha acao, ordem ou clique associado a elas.
    # Ancoragem: quando o nivel chega como INTEIRO de ticks, a linha e a
    # pilula da borda esquerda vao para a altura real do preco (y_preco) —
    # a mesma fronteira de conversao usada no resto do grafico, preco nunca
    # deixa de ser int antes disso. Se chegar como texto ja formatado
    # (fonte de decisao antiga), cai no layout empilhado anterior em vez de
    # sumir ou quebrar.
    decisao = estado.snapshot.decisao
    niveis = (("STOP", decisao.stop, tema_asg.NEXO_ROSA),
              ("A1", decisao.alvo_1, tema_asg.NEXO_VERDE),
              ("A2", decisao.alvo_2, tema_asg.NEXO_VERDE),
              ("A3", decisao.alvo_3, tema_asg.NEXO_VERDE))
    for indice, (nome, valor, cor) in enumerate(niveis):
        if valor == "—":
            continue
        ticks: int | None
        try:
            ticks = int(valor)
        except (TypeError, ValueError):
            ticks = None
        if ticks is not None:
            y = max(area_plot.top(), min(area_plot.bottom(), y_preco(ticks)))
            texto_nivel = f"{nome} {formato.preco_completo(estado.grid, ticks)}"
        else:
            y = area_plot.top() + 14 + indice * 14
            texto_nivel = f"{nome} {valor}"
        # A linha nasce na MESMA borda esquerda onde a pilula e ancorada
        # (rect.left(), nao area_plot.left()) — sem isso a pilula fica
        # boiando no gutter reservado a ela, a distancia do plot, sem
        # nenhum traco a ligando ao proprio nivel que ela rotula.
        painter.setPen(QPen(cor, 1, Qt.PenStyle.DotLine))
        painter.drawLine(rect.left(), y, area_plot.right(), y)
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        _pilula_preco(painter, rect.left(), y, texto_nivel, cor,
                     alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)

    inicio = formato.formatar_hora_ns(velas[0].timestamp_ns)
    fim = formato.formatar_hora_ns(velas[-1].timestamp_ns)
    rodape = QRect(area_plot.left(), rect.bottom() - 13, area_plot.width(), 13)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, inicio)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fim)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter,
                     "VOLUME OBSERVADO · M15 CAUSAL")
