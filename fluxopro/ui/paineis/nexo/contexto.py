"""Regiao CONTEXTO (x 0,06-0,34 · y 0,00-0,56).

Esqueleto extraido da metade superior de
``PainelNexoMercadoASG._desenhar_contexto_nexo``: arcos concentricos com a
leitura dominante, prisma de pressao e as quatro leituras derivadas. Sem
moldura de cartao — a cena sangra no fundo do quadro.

Prisma e arcos sao forma, nao asset: a direcao viaja em cor **e** em texto,
para sobreviver ao modo sem cor. Nada aqui e clicavel.

``arcos concentricos`` e o contrato do modulo, nao so o nome: nenhum anel
desta cena fecha 360 graus. O anel mais externo (moldura), o anel de direcao
e o anel de intensidade dividem o MESMO vao angular (`ARCO_INICIO_GRAUS` +
`ARCO_EXTENSAO_GRAUS`) em raios decrescentes — a leitura dominante fica no
centro, cercada por camadas, nunca por um disco fechado.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygon,
    QRadialGradient,
)

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

FRACAO_CENTRO_X = 0.40
FRACAO_CENTRO_Y = 0.40
RAIO_MIN = 32
RAIO_MAX = 92
ARCO_INICIO_GRAUS = 25
ARCO_EXTENSAO_GRAUS = 238

# Hierarquia tipografica explicita: todo par (numero, rotulo-que-o-legenda)
# mantem numero > rotulo, na ordem em que aparecem na cena. Nomeada em vez de
# literal solto para que a proxima edicao nao inverta a escala por descuido.
TAM_FONTE_NUMERO_DOMINANTE_MIN = 16
TAM_FONTE_NUMERO_DOMINANTE_MAX = 30
TAM_FONTE_ROTULO_DIRECAO = 9
TAM_FONTE_ROTULO_REGIAO = 8
TAM_FONTE_PRECO_TOPO = 10
TAM_FONTE_NUMERO_PRISMA = 11
TAM_FONTE_ROTULO_PRISMA = 7
TAM_FONTE_LEITURA_NOME = 7
TAM_FONTE_LEITURA_VALOR = 8

# Hierarquia de luminancia da lista de leituras: o rotulo (NOME) e o valor
# (VALOR) nao podem renderizar no mesmo tom. O valor sobe para perto do
# branco do proprio tema (mesmo alvo que ja usamos para preco/legenda em
# destaque); o rotulo desce um degrau abaixo do cinza neutro do painel. Sem
# essa distancia deliberada, olho nao sabe onde e dado e onde e etiqueta.
PESO_BRANCO_VALOR_LEITURA = 0.5
FATOR_ESCURO_ROTULO_LEITURA = 145

# Regua de linha: prende o rotulo ao valor da mesma leitura para que a
# hierarquia de brilho nao crie a impressao de dois blocos soltos.
FRACAO_COLUNA_ROTULO_LEITURA = 0.46
ESPACO_REGUA_LEITURA = 6
METADE_REGUA_LEITURA = 5

# Espessura dos tres aneis concentricos, moldura -> direcao -> intensidade.
# Crescente para dentro: o anel que carrega o dado mais quente (intensidade)
# e o mais grosso, a moldura decorativa e o mais fino.
LARGURA_TRACO_MOLDURA = 1
LARGURA_TRACO_DIRECAO = 2
LARGURA_TRACO_INTENSIDADE = 4
RAIO_TIP_INTENSIDADE = 3

# Sombreamento do prisma: mesma cor de direcao, tres luminancias + tres
# opacidades para simular tres faces solidas sob uma unica luz de cima —
# sem introduzir cor nova, so tom (lighter/darker) e opacidade. As tres
# faces precisam ficar distinguiveis MESMO sobre o fundo quase-preto do
# tema: alfa baixo demais (como na versao anterior, 40-96) faz as tres
# lerem como o mesmo maroom translucido. Por isso o alfa aqui e alto o
# bastante para o volume ler como material solido, e a distancia entre os
# tres fatores de tom e grande o bastante para nao depender so do alfa.
ALPHA_FACE_TOPO = 235
ALPHA_FACE_FRENTE = 205
ALPHA_FACE_LADO = 178
FATOR_CLARO_TOPO = 158
FATOR_CLARO_FRENTE = 112
FATOR_ESCURO_LADO = 190

# Geometria da extrusao isometrica: topo e lado sao a MESMA face de topo
# projetada por um deslocamento (profundidade_x, profundidade_y) na
# diagonal cima-direita — e essa projecao compartilhada, nao duas formas
# desenhadas por acaso, que fecha o volume sem costura visivel.
FATOR_PROFUNDIDADE_X = 0.45
FATOR_PROFUNDIDADE_Y = -0.32

# Altura do prisma e dado, nao decoracao: interpola entre um piso (o
# prisma nunca desaparece, mesmo com |score| ~ 0) e um teto, na mesma
# intensidade |score| que ja rege o anel 3. Sem essa interpolacao a caixa
# tem altura fixa e o operador so consegue ler a magnitude no texto abaixo
# dela — o que anula o proposito de desenhar um prisma.
FRACAO_ALTURA_PRISMA_MIN = 0.5

# Fundo com profundidade: gradiente radial dos tons de superficie do proprio
# tema NEXO (nunca uma cor literal nova), do centro da leitura para a borda
# da regiao.
RAIO_GRADIENTE_MARGEM = 1.35


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 80 or rect.height() < 80:
        return
    maker = estado.maker
    score = maker.forca if maker is not None else 0.0
    direcao = maker.direcao if maker is not None else _asg.DirecaoASG.NEUTRA
    cor = _asg._cor_nexo_direcao(direcao)

    centro = QPoint(rect.left() + int(rect.width() * FRACAO_CENTRO_X),
                    rect.top() + int(rect.height() * FRACAO_CENTRO_Y))
    raio = max(RAIO_MIN, min(RAIO_MAX, min(rect.width(), rect.height()) // 4))

    _fundo_profundidade(painter, rect, centro, raio)

    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_REGIAO))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(4, 4, -4, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "CONTEXTO")

    _aneis_leitura(painter, centro, raio, score, direcao, cor)

    ranking_maker = maker.detalhe if maker is not None else ""
    _prisma(painter, rect, score, cor, ranking_maker)

    ultimo = estado.serie[-1][1] if estado.serie else None
    if ultimo is not None:
        preco = formato.formatar_preco(estado.grid, ultimo)
        painter.setFont(tokens.fonte_numero(TAM_FONTE_PRECO_TOPO, QFont.Weight.DemiBold))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(rect.adjusted(4, 4, -4, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         f"{preco[0]}{preco[1]}")

    # A coluna de leituras encosta na borda direita da regiao; o prisma fica a
    # esquerda dela, em faixa propria, para que os dois nao se sobreponham em
    # nenhuma largura de janela.
    largura_leituras = max(76, min(110, rect.width() // 4))
    _leituras(painter, QRect(rect.right() - largura_leituras,
                             rect.top() + int(rect.height() * 0.34),
                             largura_leituras,
                             min(120, rect.height() // 3)), estado)


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


def _fundo_profundidade(painter: QPainter, rect: QRect, centro: QPoint, raio: int) -> None:
    """Gradiente radial nos tons do proprio tema — sem isso a cena e um
    retangulo chapado de ``NEXO_FUNDO`` (o preenchimento que o compositor ja
    fez para o quadro inteiro antes de nos chamar). Os tons continuam vindo
    de ``tema_asg``; so a distribuicao espacial e nova.
    """

    canto_x = max(centro.x() - rect.left(), rect.right() - centro.x())
    canto_y = max(centro.y() - rect.top(), rect.bottom() - centro.y())
    raio_gradiente = max(raio * 2, math.hypot(canto_x, canto_y) * RAIO_GRADIENTE_MARGEM)

    gradiente = QRadialGradient(centro, raio_gradiente)
    gradiente.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
    gradiente.setColorAt(0.45, tema_asg.NEXO_PAINEL)
    gradiente.setColorAt(1.0, tema_asg.NEXO_FUNDO)
    painter.fillRect(rect, QBrush(gradiente))


def _aneis_leitura(painter: QPainter, centro: QPoint, raio: int, score: float,
                   direcao, cor: QColor) -> None:
    """Tres aneis concentricos, todos parciais, do mais externo (moldura)
    ao mais interno (intensidade). Nenhum fecha 360 graus — e o que
    distingue um mostrador de um disco.
    """

    intensidade = max(0.0, min(1.0, abs(score)))

    # Anel 1 — moldura, sempre no mesmo vao angular, so decorativa.
    r1 = raio + 15
    painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_MOLDURA))
    painter.drawArc(QRect(centro.x() - r1, centro.y() - r1, 2 * r1, 2 * r1),
                    ARCO_INICIO_GRAUS * 16, ARCO_EXTENSAO_GRAUS * 16)

    # Anel 2 — direcao: vao angular fixo, cor do lado dominante. Carrega
    # "para onde", nao "quanto".
    r2 = raio + 7
    painter.setPen(QPen(cor, LARGURA_TRACO_DIRECAO))
    painter.drawArc(QRect(centro.x() - r2, centro.y() - r2, 2 * r2, 2 * r2),
                    ARCO_INICIO_GRAUS * 16, ARCO_EXTENSAO_GRAUS * 16)

    # Anel 3 — intensidade: trilho apagado no vao inteiro, preenchimento
    # colorido proporcional a |score|. Carrega "quanto".
    painter.setPen(QPen(tema_asg.NEXO_MUTED, LARGURA_TRACO_INTENSIDADE))
    painter.drawArc(QRect(centro.x() - raio, centro.y() - raio, 2 * raio, 2 * raio),
                    ARCO_INICIO_GRAUS * 16, ARCO_EXTENSAO_GRAUS * 16)
    extensao_valor = ARCO_EXTENSAO_GRAUS * intensidade
    if extensao_valor > 0.5:
        painter.setPen(QPen(cor, LARGURA_TRACO_INTENSIDADE))
        painter.drawArc(QRect(centro.x() - raio, centro.y() - raio, 2 * raio, 2 * raio),
                        ARCO_INICIO_GRAUS * 16, round(extensao_valor * 16))
        angulo_fim = math.radians(ARCO_INICIO_GRAUS + extensao_valor)
        ponta = QPoint(
            centro.x() + round(raio * math.cos(angulo_fim)),
            centro.y() - round(raio * math.sin(angulo_fim)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cor)
        painter.drawEllipse(ponta, RAIO_TIP_INTENSIDADE, RAIO_TIP_INTENSIDADE)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    # Numero dominante, centrado nos tres aneis.
    tam_numero = max(TAM_FONTE_NUMERO_DOMINANTE_MIN,
                     min(TAM_FONTE_NUMERO_DOMINANTE_MAX, raio // 2 + 4))
    painter.setPen(cor)
    painter.setFont(tokens.fonte_numero(tam_numero, QFont.Weight.Bold))
    painter.drawText(QRect(centro.x() - raio, centro.y() - 17, 2 * raio, 34),
                     Qt.AlignmentFlag.AlignCenter, f"{score * 100:+.0f}%")

    # Legenda da leitura dominante — sempre por fora do anel-moldura (r1),
    # nunca sobreposta a ele.
    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_DIRECAO))
    painter.setPen(tema_asg.NEXO_TEXTO)
    rotulo_direcao = ("COMPRA" if direcao is _asg.DirecaoASG.COMPRA else
                      "VENDA" if direcao is _asg.DirecaoASG.VENDA else "EQUILIBRIO")
    painter.drawText(QRect(centro.x() - r1 - 20, centro.y() + r1 + 4,
                           2 * (r1 + 20), 16), Qt.AlignmentFlag.AlignCenter,
                     rotulo_direcao)


def _prisma(painter: QPainter, rect: QRect, score: float, cor: QColor, ranking_maker: str = "") -> None:
    """Volume isometrico da pressao observada — forma, nao logotipo.

    Caixa extrudada FECHADA, tres faces da MESMA cor de direcao: topo
    (a face de topo projetada na diagonal cima-direita — luz direta, a
    mais clara), frente (a face voltada para o operador — clara, mas um
    degrau abaixo do topo) e lado (a mesma projecao aplicada a aresta
    direita da frente — a mais escura, sombra propria). Topo e lado
    compartilham o vertice da frente com quem se encaixam, entao a caixa
    fecha sem costura: nao ha friso solto nem par de faces que se abrem a
    partir de uma dobra ambigua.

    A altura vem de |score| (mesma intensidade do anel 3), entre um piso
    (a caixa nunca murcha a zero) e um teto — e cresce a partir de uma
    LINHA DE BASE desenhada (o "chao"), para que a magnitude se leia no
    proprio volume, nao so no texto abaixo dele. Uma sombra de contato sob
    o rodape da caixa prende o volume ao chao (sem ela a caixa parece
    flutuar).
    """

    intensidade = max(0.0, min(1.0, abs(score)))

    largura = max(34, rect.width() // 9)
    prof_x = max(10, round(largura * FATOR_PROFUNDIDADE_X))
    prof_y = round(largura * FATOR_PROFUNDIDADE_Y)  # negativo: sobe e vai p/ direita

    altura_teto = max(48, rect.height() // 5)
    altura_piso = round(altura_teto * FRACAO_ALTURA_PRISMA_MIN)
    altura = round(altura_piso + (altura_teto - altura_piso) * intensidade)

    x = rect.left() + int(rect.width() * 0.56)
    chao_y = rect.top() + int(rect.height() * 0.56) + altura_teto
    topo_y = chao_y - altura

    # Rodape (linha de base): o "zero" contra o qual a altura se mede. Sem
    # esta linha o operador nao tem de onde partir o olho para julgar
    # "caixa alta" vs "caixa baixa" — so o numero abaixo dela.
    painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_MOLDURA))
    painter.drawLine(x - 6, chao_y, x + largura + prof_x + 6, chao_y)

    # Sombra de contato: elipse achatada no mesmo tom escuro do fundo,
    # centrada no rodape da face frontal — ancora o volume ao chao.
    sombra = _com_alpha(tema_asg.NEXO_FUNDO.darker(120), 150)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(sombra)
    painter.drawEllipse(QPoint(x + largura // 2, chao_y + 2), largura // 2 + 6, 5)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    frente = QPolygon([QPoint(x, chao_y), QPoint(x + largura, chao_y),
                       QPoint(x + largura, topo_y), QPoint(x, topo_y)])
    topo = QPolygon([QPoint(x, topo_y), QPoint(x + largura, topo_y),
                     QPoint(x + largura + prof_x, topo_y + prof_y),
                     QPoint(x + prof_x, topo_y + prof_y)])
    lado = QPolygon([QPoint(x + largura, chao_y), QPoint(x + largura, topo_y),
                     QPoint(x + largura + prof_x, topo_y + prof_y),
                     QPoint(x + largura + prof_x, chao_y + prof_y)])

    cor_topo = _com_alpha(cor.lighter(FATOR_CLARO_TOPO), ALPHA_FACE_TOPO)
    cor_frente = _com_alpha(cor.lighter(FATOR_CLARO_FRENTE), ALPHA_FACE_FRENTE)
    cor_lado = _com_alpha(cor.darker(FATOR_ESCURO_LADO), ALPHA_FACE_LADO)

    painter.setPen(cor)
    for poligono, preenchimento in ((lado, cor_lado), (frente, cor_frente), (topo, cor_topo)):
        painter.setBrush(preenchimento)
        painter.drawPolygon(poligono)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setFont(tokens.fonte_numero(TAM_FONTE_NUMERO_PRISMA, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(QRect(x - 12, chao_y + 10, largura + prof_x + 40, 16),
                     # MESMO formato do numero do mostrador logo acima: e o
                     # MESMO score, impresso duas vezes na mesma regiao. Com
                     # `+.1f` o prisma era o unico percentual da tela inteira
                     # com casa decimal — e com separador `.`, num quadro que
                     # escreve preco em `5.174,5`. Mesma leitura, mesma forma.
                     Qt.AlignmentFlag.AlignCenter, f"{score * 100:+.0f}%")
    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_PRISMA))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(x - 18, topo_y + prof_y - 15, largura + prof_x + 52, 14),
                     Qt.AlignmentFlag.AlignCenter, "MAKER PROXY")

    # Ranking dos componentes do MakerProxy por magnitude ("Maker 1o/2o/3o"
    # pedido pelo operador) — nunca uma entidade nova, so o mesmo sinal
    # agregado quebrado por componente. So desenha quando ha componente
    # real disponivel (nunca fabrica ranking vazio).
    #
    # UMA LINHA POR POSICAO, fonte legivel — achado ao vivo pelo operador
    # ("onde esta os makers?"): a versao anterior espremia as 3 posicoes
    # numa unica linha a ~5px, tecnicamente presente mas ilegivel na pratica.
    if ranking_maker:
        linhas_ranking = ranking_maker.split("\n")
        altura_linha_ranking = 13
        largura_bloco = max(largura + prof_x + 70, 150)
        x_bloco = x - 30
        y_bloco = chao_y + 24
        # Nunca desenhar por cima da PROXIMA regiao: se a caixa nao tem
        # altura para as 3 linhas (janela pequena, cubo baixo na regiao),
        # corta as linhas de baixo em vez de invadir o vizinho — achado ao
        # vivo pelo operador (a 3a linha ficava por cima da faixa de niveis).
        linhas_que_cabem = max(0, (rect.bottom() - y_bloco) // altura_linha_ranking)
        linhas_ranking = linhas_ranking[:linhas_que_cabem]
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        for indice, linha in enumerate(linhas_ranking):
            painter.setPen(tema_asg.NEXO_TEXTO if indice == 0 else tema_asg.NEXO_MUTED)
            painter.drawText(
                QRect(x_bloco, y_bloco + indice * altura_linha_ranking,
                     largura_bloco, altura_linha_ranking),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                linha,
            )


def _tom_valor_leitura(cor: QColor) -> QColor:
    """Mistura a cor de direcao com o branco quase puro do tema (mesmo alvo
    usado em preco/legenda de destaque), garantindo que o VALOR sempre pouse
    num degrau de luminancia claramente acima do rotulo — independente de a
    cor de direcao, sozinha e num traco fino de 8pt, ser clara o bastante.
    """

    alvo = tema_asg.NEXO_TEXTO
    peso = PESO_BRANCO_VALOR_LEITURA
    return QColor(
        round(cor.red() * (1 - peso) + alvo.red() * peso),
        round(cor.green() * (1 - peso) + alvo.green() * peso),
        round(cor.blue() * (1 - peso) + alvo.blue() * peso),
    )


def _leituras(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """Coluna ROTULO -> VALOR com dois degraus de luminancia (valor perto do
    branco, rotulo abaixo do cinza neutro) e uma regua fina por linha que
    prende cada valor ao rotulo que o legenda — sem a regua, o degrau de
    brilho por si so faria rotulo e valor lerem como dois blocos soltos em
    vez de um par leitura->numero.
    """

    linhas = estado.leituras
    if not linhas or rect.height() < 42:
        return
    altura = max(16, rect.height() // len(linhas))
    coluna_rotulo = int(rect.width() * FRACAO_COLUNA_ROTULO_LEITURA)
    x_regua = rect.left() + coluna_rotulo
    rotulo_suprimido = tema_asg.NEXO_MUTED.darker(FATOR_ESCURO_ROTULO_LEITURA)
    for indice, (nome, linha) in enumerate(linhas):
        y = rect.y() + indice * altura
        cor = _asg._cor_nexo_direcao(linha.direcao)
        painter.setFont(tokens.fonte_rotulo(TAM_FONTE_LEITURA_NOME))
        painter.setPen(rotulo_suprimido)
        painter.drawText(QRect(rect.left(), y, coluna_rotulo - ESPACO_REGUA_LEITURA, altura),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)

        meio_y = y + altura // 2
        painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_MOLDURA))
        painter.drawLine(x_regua, meio_y - METADE_REGUA_LEITURA,
                         x_regua, meio_y + METADE_REGUA_LEITURA)

        painter.setFont(tokens.fonte_numero(TAM_FONTE_LEITURA_VALOR, QFont.Weight.Bold))
        painter.setPen(_tom_valor_leitura(cor))
        painter.drawText(QRect(x_regua + ESPACO_REGUA_LEITURA, y,
                               rect.width() - coluna_rotulo - ESPACO_REGUA_LEITURA, altura),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         linha.valor)
