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
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from fluxopro.analytics.renko import FaseRenko
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

# Quantas colunas o rotulo de alvo pode tentar antes de desistir. Alvos
# proximos deixam de brigar pelo mesmo canto: o segundo vai para a coluna
# seguinte, em vez de apagar o primeiro com a placa de fundo.
COLUNAS_ROTULO_ALVO = 3

# Largura reservada ao trilho de preco a direita. Degrada para uma fracao da
# largura disponivel quando o quadro e pequeno demais para o valor cheio.
RAIL_LARGURA_PX = 78
RAIL_ALTURA_LINHA_PX = 21
RAIL_NIVEIS_MIN = 5
RAIL_NIVEIS_MAX = 17

# Geometria do tijolo. Achado do operador (28/08/2026): "os renkos precisam
# ficar em tamanhos proporcionais aos candles abaixo". O desenho antigo
# esticava CADA tijolo para 1/16 da largura e reescalava a altura para a
# amplitude dos visiveis — resultado: 16 blocos gigantes, sem relacao alguma
# com a escala do candle logo abaixo, e a leitura de escada some.
#
# Num Renko de verdade todo tijolo tem o MESMO tamanho, entao ele tem de ter
# a mesma altura em pixels: e a janela de preco que se ajusta ao quadro, nao
# o tijolo que se ajusta a janela. Fixa-se a altura alvo do tijolo em pixels
# (da mesma ordem do slot de vela em `nexo/candles.py`, LARGURA_MIN_SLOT=5,
# de onde vem a proporcao pedida) e deriva-se dela a largura, a quantidade de
# tijolos visiveis e a amplitude de preco enquadrada.
ALTURA_TIJOLO_ALVO_PX = 10
ALTURA_TIJOLO_MIN_PX = 5
FATOR_ESCALA_VS_CANDLE = 1.0
"""DECLARADO: 1 tick vale os MESMOS pixels aqui e no grafico de velas.

Nao e um numero de ajuste fino — e o contrato de proporcao entre as duas
regioes, e existe como constante nomeada justamente para poder ser medido e
travado por teste (`tests/test_ui_nexo_forca_escala.py`). Mudar isto muda o
significado visual do painel inteiro: qualquer valor diferente de 1,0 faz o
Renko exagerar (ou achatar) amplitude em relacao ao vizinho."""

ALTURA_TIJOLO_MAX_PX = 16
"""Teto da altura do tijolo. Existe para o caso de mercado parado (poucos
niveis ocupados): sem ele a regra de ocupacao inflaria o tijolo ate virar o
bloco gigante que o operador chamou de distorcido."""
FATORES_DECLARAVEIS = (2,)
"""Fatores de escala admitidos acima do 1:1, todos redondos. Quantizado de
proposito: um fator continuo daria o enquadramento perfeito e um rotulo
("ESCALA 2,37x") que ninguem le, alem de tremer a cada quadro.

TETO BAIXADO DE (2,3,4,6,8) PARA (2,) EM 31/08/2026 — operador: "AUMENTE
NUMERO DE RENKO, PRECISO VER UM PERIODO MAIOR, PARA CONSEGUIR TRACAR OS
ALVOS".

O fator existe para preencher a altura quando a micro percorre pouco preco,
mas ele infla o TIJOLO — e tijolo mais alto e, pelo `ASPECTO_TIJOLO`, mais
LARGO, o que reduz quantos cabem na largura fixa da regiao. Medido na tela
(regiao de 568px, escala do candle ~5 px/tick):

    fator 3x -> tijolo 8x15px -> ~53 tijolos visiveis
    fator 2x -> tijolo 5x10px -> ~93 tijolos visiveis
    fator 1x -> tijolo 3x5px  -> ~140, mas volta a virar "cerca de listras"

Ou seja: o fator alto estava comprando altura preenchida ao preco do
HISTORICO, que e exatamente o que o operador precisa para tracar alvo. Com
teto 2 o periodo visivel quase dobra e o tijolo continua legivel. A altura
que sobrar e preenchida do jeito legitimo — mais tijolos percorrendo mais
preco (ver `TIJOLOS_VISIVEIS_MAX`), nunca esticando o bloco."""

OCUPACAO_MINIMA = 0.45
"""Abaixo desta fracao da caixa a serie e considerada ilegivel de tao
comprimida, e o fator sobe. Acima dela o 1:1 prevalece — a proporcao literal
com o candle vale mais que preencher o ultimo pixel."""

OCUPACAO_VERTICAL_ALVO = 0.82
"""Fracao da altura util que a escada visivel deve ocupar. A altura do tijolo
sai daqui, nao de um numero de pixels cravado: e o que mantem o Renko na
mesma ordem de grandeza do candle logo abaixo em vez de virar um bloco
gigante (ou uma linha fina) conforme o dia esta agitado ou parado."""
ASPECTO_TIJOLO = 0.55
"""largura / altura do tijolo. Era 0,9 (quase quadrado); a referencia visual
trazida pelo operador (31/08/2026) mostra uma escada bem mais densa — muito
mais pontos de Renko cabendo na mesma largura do que candles no grafico logo
abaixo, o oposto da nossa proporcao antiga. 0,62 e o MESMO fator de corpo que
`nexo/candles.py` usa (`FRACAO_CORPO`), entao o tijolo fica esguio como a
vela, e mais tijolo cabe por pixel sem esticar a escala vertical (que
continua travada 1:1 ao candle, ver `FATOR_ESCALA_VS_CANDLE`)."""
LARGURA_MIN_TIJOLO_PX = 3  # mesmo piso fisico do slot de vela (candles.LARGURA_MIN_SLOT)
LARGURA_MAX_TIJOLO_PX = 22
"""Teto da LARGURA do tijolo.

REVERTIDO EM 31/08/2026 (operador: "o grafico de renko esta desproporcional
as candle, fora da logica que ja mandei").

O teto foi a 8px mais cedo NESTA MESMA sessao, com o argumento de que o eixo
horizontal do Renko "nao deve nada a escala do candle" e que valia trocar
proporcao por historico. Medido na tela depois: com a escala vertical
travada no candle, a altura do tijolo chega a ~30px, e o aspecto pedia
`30 * 0,62 = 18px` de largura — o teto de 8 cortava pela METADE e a escada
virava uma cerca de listras verticais, com ~68 tijolos espremidos onde a
referencia do operador mostra blocos nitidos.

O pedido original era proporcao COM AS VELAS, e um tijolo 4x mais alto que
largo nao guarda proporcao com nada. 22px deixa o `ASPECTO_TIJOLO` governar
de fato na faixa de alturas que a amarracao 1:1 produz (ate ~35px de altura),
e o teto so volta a agir em dias de escala muito esticada. Menos tijolos e
o custo aceito, e ele e explicito: a legenda ja imprime quantos de quantos
estao na tela."""
TIJOLOS_VISIVEIS_MAX = 240
"""Teto de tijolos na tela. Com o eixo vertical amarrado ao candle (ver
`FATOR_ESCALA_VS_CANDLE`) a altura do tijolo deixou de ser negociavel, e a
UNICA forma legitima de aproveitar o quadro passou a ser mostrar mais
HISTORICO — o que tambem faz a escada percorrer mais preco e ocupar mais da
vertical. Esticar o tijolo para preencher espaco seria voltar a mentir sobre
amplitude."""
ALFA_CORPO_TIJOLO = 140
"""Corpo translucido + borda solida (mesmo tratamento das velas). Subido de
105 (31/08/2026): com o tijolo mais esguio (`ASPECTO_TIJOLO`) o preenchimento
fraco lia como trilho fino cinza; a referencia do operador mostra blocos bem
saturados. Ainda translucido — a grade de preco por tras continua visivel —
so mais cheio."""

_ROTULO_FASE = {
    FaseRenko.TENDENCIA: "TENDENCIA",
    FaseRenko.PERDENDO_FORCA: "PERDENDO FORCA",
    FaseRenko.POSSIVEL_INVERSAO: "POSSIVEL INVERSAO",
    FaseRenko.INDEFINIDA: "AGUARDANDO TIJOLOS",
}


def escala_do_renko(escala_candle_px_por_tick: float, tam_ticks: int,
                    zona_util: int, faixa_visivel_ticks: int) -> tuple[float, int]:
    """Devolve `(px_por_tick, fator)` do eixo vertical do Renko.

    Funcao PURA, exposta para poder ser medida por teste — o contrato de
    proporcao entre o Renko e o grafico de velas nao pode depender de alguem
    olhar o retrato e achar que esta parecido.

    A tensao, encarada de frente: amarrar o px/tick ao candle e preencher a
    caixa BRIGAM quando a amplitude da micro e muito menor que a do dia. Na
    medicao de 28/08/2026, 1:1 deixava a serie inteira em 63px de 320 — 80%
    de vazio, tijolo de 9px. Vazio nao e solucao, e custo empurrado para o
    operador; e esticar em silencio era o defeito original.

    Entao a regra e, nesta ordem:

    1. **1:1 com o candle sempre que couber** — `fator = 1`, e a comparacao
       de amplitude entre as duas regioes e literal.
    2. Se a serie ocupar menos que `OCUPACAO_MINIMA` da caixa, sobe pelo
       menor fator de `FATORES_DECLARAVEIS` que a leve perto de
       `OCUPACAO_VERTICAL_ALVO`. Fator quantizado, nunca continuo: numero
       redondo e declaravel ("ESCALA 2x DO CANDLE") e nao fica tremendo de um
       quadro para o outro.
    3. Nunca passa de `ALTURA_TIJOLO_MAX_PX` por tijolo — o teto que impede
       o "bloco gigante" que o operador chamou de distorcido.

    `fator` volta para quem desenha justamente para virar rotulo. Fator > 1
    sem o rotulo seria a distorcao silenciosa de novo. `fator = 0` significa
    "sem escala do vizinho para copiar" (ainda nao ha vela): o eixo cai na
    regra propria e o rotulo tem de dizer ESCALA PROPRIA.
    """

    if escala_candle_px_por_tick <= 0.0:
        # Sem escala do vizinho: regra propria, ocupar a altura util. Nunca
        # inventa um px/tick para o candle.
        niveis = max(1, faixa_visivel_ticks // max(1, tam_ticks))
        altura = round(zona_util * OCUPACAO_VERTICAL_ALVO / (niveis + 2))
        altura = max(ALTURA_TIJOLO_MIN_PX, min(ALTURA_TIJOLO_MAX_PX, altura))
        return altura / max(1, tam_ticks), 0

    faixa = max(tam_ticks, faixa_visivel_ticks)
    ocupado_1x = faixa * escala_candle_px_por_tick
    escolhido = 1
    if zona_util > 0 and ocupado_1x < zona_util * OCUPACAO_MINIMA:
        for fator in FATORES_DECLARAVEIS:
            if fator * tam_ticks * escala_candle_px_por_tick > ALTURA_TIJOLO_MAX_PX:
                break
            escolhido = fator
            if ocupado_1x * fator >= zona_util * OCUPACAO_VERTICAL_ALVO:
                break
    return escala_candle_px_por_tick * escolhido, escolhido


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
    # RECORTE. Desde que o eixo virou o do candle, o ZOOM DE PRECO do
    # operador (`estado.candles_zoom_preco`, arrasto/roda sobre o eixo das
    # velas) mexe tambem neste eixo — e com zoom alto o tijolo cresce ate
    # transbordar a caixa e pintar por cima da regiao vizinha. Nenhuma regiao
    # do NEXO pode desenhar fora do retangulo que recebeu; a composicao
    # inteira depende disso. `asg.py` ja envolve cada regiao em
    # save()/restore(), entao o recorte morre com o quadro.
    painter.setClipRect(rect)
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

    topo_reservado = 18
    base_reservada = 20
    zona_util = max(1, area.height() - topo_reservado - base_reservada)

    # Tamanho do tijolo em ticks: o valor REAL vindo do agregador. Se o estado
    # ainda nao trouxe (quadro antes do primeiro registro), infere do proprio
    # tijolo desenhado — nunca de um numero cravado aqui.
    tam_ticks = estado.renko_tamanho_ticks
    if tam_ticks < 1:
        tam_ticks = max(1, abs(tijolos[-1].fechamento - tijolos[-1].abertura))

    def _largura_de(altura: int) -> int:
        return max(LARGURA_MIN_TIJOLO_PX,
                   min(LARGURA_MAX_TIJOLO_PX, round(altura * ASPECTO_TIJOLO)))

    def _vao_de(largura: int) -> int:
        # Tijolo estreito com vao de 2px vira tracejado; com 1px continua
        # lendo como escada de blocos separados.
        return 1 if largura <= 8 else 2

    def _cabem(altura: int) -> int:
        largura = _largura_de(altura)
        passo = largura + _vao_de(largura)
        return max(1, min(TIJOLOS_VISIVEIS_MAX, (area.width() - 8) // passo))

    # ALTURA DO TIJOLO — amarrada a escala do grafico de velas.
    #
    # O pedido do operador nao e "Renko bonito", e "tijolos proporcionais aos
    # candles abaixo". Entao a altura nao pode sair de um alvo estetico desta
    # regiao: ela e o tamanho do tijolo em ticks vezes os pixels-por-tick que
    # a regiao de VELAS esta usando neste mesmo quadro
    # (`estado.escala_candle_px_por_tick`, medido por `candles.px_por_tick`).
    # Um tijolo de 0,5 pt fica, na tela, exatamente metade de uma vela de
    # 1 pt do grafico de baixo — a comparacao a olho passa a ser verdadeira.
    candidatos = tijolos[-_cabem(ALTURA_TIJOLO_ALVO_PX):]
    extremos = [t.abertura for t in candidatos] + [t.fechamento for t in candidatos]
    faixa_candidatos = max(tam_ticks, max(extremos) - min(extremos))
    escala_px_por_tick, fator_escala = escala_do_renko(
        float(estado.escala_candle_px_por_tick or 0.0), tam_ticks,
        zona_util, faixa_candidatos)
    altura_tijolo = max(ALTURA_TIJOLO_MIN_PX, round(tam_ticks * escala_px_por_tick))
    largura_tijolo = _largura_de(altura_tijolo)
    passo_x = largura_tijolo + _vao_de(largura_tijolo)
    visiveis = tijolos[-_cabem(altura_tijolo):]

    # EIXO DE PRECO. O px/tick e o do candle, em ponto flutuante — nao a
    # altura JA ARREDONDADA do tijolo. Arredondar antes de virar escala
    # deixava o eixo do Renko ~2% esticado em relacao ao vizinho (0,5 pt
    # virava 7 px inteiros onde a conta exata pedia 6,86), e 2% de erro num
    # eixo e exatamente o tipo de divergencia que ninguem percebe olhando e
    # que falseia a comparacao de amplitude. Cada tijolo passa a ser desenhado
    # pelo proprio par abertura/fechamento atraves deste eixo: a altura pode
    # variar 1px entre um tijolo e outro, mas a ESCALA e identica a do candle.
    linhas_verticais = max(2, round(zona_util / max(1.0, escala_px_por_tick * tam_ticks)))
    # Janela centrada no MEIO da escada visivel (nao no ultimo fechamento) —
    # assim nenhum tijolo desenhado cai fora do quadro quando o preco anda
    # para uma ponta.
    meia_janela = max(tam_ticks, zona_util / (2 * escala_px_por_tick))
    extremos = [t.abertura for t in visiveis] + [t.fechamento for t in visiveis]
    centro_janela = (max(extremos) + min(extremos)) // 2
    centro = tijolos[-1].fechamento  # referencia do preco atual, nao da janela
    preco_min = centro_janela - meia_janela
    preco_max = centro_janela + meia_janela

    def y_de_preco(preco: float) -> int:
        return area.bottom() - base_reservada - round(
            (preco - preco_min) * escala_px_por_tick)

    # Grade na escala do PRECO: uma linha a cada tijolo, ancorada no
    # fechamento do ultimo. A antiga era em fracoes fixas da altura do quadro,
    # sem relacao nenhuma com o preco — decorativa, e ainda reforcava a
    # sensacao de area vazia. Agora a grade e a propria regua do Renko.
    painter.setPen(tema_asg.NEXO_GRADE)
    nivel = centro_janela - (linhas_verticais // 2 + 1) * tam_ticks
    while nivel <= preco_max:
        y = y_de_preco(nivel)
        if area.top() + topo_reservado <= y <= area.bottom() - base_reservada:
            painter.drawLine(area.left(), y, area.right(), y)
        nivel += tam_ticks

    # Referencia do fechamento do ultimo tijolo, atravessando o quadro — o
    # mesmo recurso da regiao de velas, e o que liga a escada ao trilho.
    painter.setPen(QPen(tema_asg.NEXO_AMARELO, 1, Qt.PenStyle.DotLine))
    y_centro = y_de_preco(centro)
    painter.drawLine(area.left(), y_centro, area.right(), y_centro)

    x = area.right() - passo_x * len(visiveis)
    for tijolo in visiveis:
        y_abertura = y_de_preco(tijolo.abertura)
        y_fechamento = y_de_preco(tijolo.fechamento)
        topo = min(y_abertura, y_fechamento)
        altura = max(2, abs(y_fechamento - y_abertura))
        alta = tijolo.direcao > 0
        cor = tema_asg.NEXO_VERDE if alta else tema_asg.NEXO_ROSA
        corpo = QRect(x, topo, largura_tijolo, altura)
        if corpo.bottom() < area.top() or corpo.top() > area.bottom():
            x += passo_x
            continue
        # Corpo translucido com borda solida: o mesmo tratamento das velas —
        # a direcao continua legivel quando os tijolos ficam pequenos, e a
        # escada nao vira um bloco macico de cor.
        painter.setPen(Qt.PenStyle.NoPen)
        preenchimento = QColor(cor)
        preenchimento.setAlpha(ALFA_CORPO_TIJOLO)
        painter.setBrush(preenchimento)
        painter.drawRect(corpo)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(cor, 1))
        painter.drawRect(corpo)
        x += passo_x
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # "ALVO DO COMPRADOR"/"ALVO DO VENDEDOR": nomeia a ZONA, CONFIRMADO na
    # fonte (ijsZl8EzeH8.txt) — a faixa acima e onde o COMPRADOR realiza, a
    # de baixo onde o VENDEDOR realiza. So no A1 (o alvo mais proximo, onde
    # a zona comeca) para nao empilhar o mesmo aviso tres vezes.
    #
    # Ate 28/08 estas duas placas diziam "EVITAR COMPRAS" e "EVITAR VENDAS".
    # A frase e imperativa: le-se como instrucao de entrada, na unica regiao
    # da tela que fazia isso — o rodape do NEXO carimba "NAO E ORDEM · NAO E
    # RECOMENDACAO" a dois palmos dali, e o documento do operador promete, na
    # secao 9, que o painel nao indica entrada, saida, alvo ou stop. O nome
    # da zona diz a mesma coisa sem mandar em ninguem, e usa o vocabulario
    # que a regiao do candle ja usa para os mesmos niveis (A1/A2/A3 = alvo).
    # A leitura de disciplina que a fonte carrega ("comprar no alvo do
    # comprador e comprar caro") esta escrita em COMO_LER_OS_INDICADORES.md,
    # onde cabe a prosa com a ressalva junto.
    alvos = estado.alvos_renko
    if alvos is not None:
        caneta_alvo = QPen(tema_asg.NEXO_AMARELO, 1, Qt.PenStyle.DashLine)
        painter.setFont(tokens.fonte_rotulo(7))
        # De-crowding: quando a amplitude da janela e curta, A1/A2/A3 caem a
        # poucos pixels um do outro e os rotulos se sobrepoem, virando borrao.
        # Desenha so os alvos que ficam separados o suficiente para serem
        # lidos — nunca reposiciona um alvo (seria mentir sobre o preco dele).
        # NIVEL MARCADO E NIVEL ROTULADO. A versao anterior desenhava as seis
        # guias e rotulava quatro: as placas de fundo de um rotulo apagavam o
        # texto do vizinho de cima, e A2+/A2- sumiam sem deixar rastro. Guia
        # muda e pior que guia nenhuma — o operador ve a linha e nao sabe que
        # nivel e. Agora o rotulo procura COLUNA livre antes de desistir, e se
        # nao houver lugar para o texto a LINHA tambem nao e desenhada.
        candidatos_alvo = []
        for precos_lado, cor, sufixo, aviso, desloca in (
            (alvos.positivos, tema_asg.NEXO_AMARELO, "+", "  ALVO DO COMPRADOR", -3),
            (alvos.negativos, tema_asg.NEXO_CIANO, "-", "  ALVO DO VENDEDOR", 10),
        ):
            for indice, preco_alvo in enumerate(precos_lado, start=1):
                y = y_de_preco(preco_alvo)
                if not (area.top() + topo_reservado <= y <= area.bottom() - base_reservada):
                    continue
                candidatos_alvo.append(
                    (y, f"A{indice}{sufixo}" + (aviso if indice == 1 else ""),
                     cor, desloca))

        ocupadas: list[QRect] = []
        for y, rotulo, cor, desloca in sorted(candidatos_alvo):
            largura_rotulo = painter.fontMetrics().horizontalAdvance(rotulo) + 5
            placa = None
            for coluna in range(COLUNAS_ROTULO_ALVO):
                tentativa = QRect(area.left() + 1 + coluna * (largura_rotulo + 6),
                                  y + desloca - 8, largura_rotulo, 11)
                if tentativa.right() > area.right() - 4:
                    break
                if not any(tentativa.intersects(o) for o in ocupadas):
                    placa = tentativa
                    break
            if placa is None:
                continue  # sem lugar para o texto: nao desenha a guia muda
            ocupadas.append(placa)

            painter.setPen(caneta_alvo if sufixo == "+"
                           else QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
            painter.drawLine(area.left(), y, area.right(), y)
            # Placa de fundo: com a escada cheia o rotulo cai por cima de
            # um tijolo e nenhum dos dois se le.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tema_asg.NEXO_PAINEL)
            painter.drawRect(placa)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(cor)
            painter.drawText(placa.left() + 2, y + desloca, rotulo)

    fase = estado.fase_renko if isinstance(estado.fase_renko, FaseRenko) else FaseRenko.INDEFINIDA
    cor_fase = _cor_fase(fase)
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.setPen(cor_fase)
    # O titulo era "4R", cravado — e passou a CONTRADIZER o proprio rotulo de
    # tamanho ("RENKO · 0,5 PTS") assim que o tijolo virou dinamico. O titulo
    # agora e o tamanho corrente, na mesma convencao do Profit ("<n>R").
    pontos_tijolo = estado.renko_tamanho_ticks * estado.grid.tick_size
    if pontos_tijolo <= 0:
        pontos_tijolo = tam_ticks * estado.grid.tick_size
    titulo = f"{pontos_tijolo:g}R".replace(".", ",")
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     titulo)
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    # Achado do operador (27/08/2026): isto ficava cravado em "4 PTS" mesmo
    # depois do tijolo virar dinamico (Fase 1, ConfigRenko.tijolo_dinamico) —
    # rotulo mentiroso. Calcula o tamanho REAL a partir de
    # `estado.renko_tamanho_ticks` (populado a cada quadro em asg.py a
    # partir de `Renko.tamanho_tijolo_ticks`), nunca um numero fixo aqui.
    rotulo_tamanho = f"RENKO · {pontos_tijolo:.1f} PTS".replace(".", ",")
    # A RELACAO COM O VIZINHO VAI ESCRITA, SEMPRE. Fator 1 e a proporcao
    # literal; fator maior e legitimo (a micro nao encheria a caixa a 1:1) mas
    # so enquanto estiver DECLARADO — fator escondido e exatamente a
    # distorcao silenciosa que abriu este ciclo. Fator 0 e "nao ha vela para
    # comparar", e nao pode se passar por proporcao nenhuma.
    if fator_escala == 0:
        rotulo_tamanho += " · ESCALA PROPRIA"
    elif fator_escala == 1:
        rotulo_tamanho += " · 1:1 COM CANDLE"
    else:
        rotulo_tamanho += f" · ESCALA {fator_escala}x DO CANDLE"
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                     rotulo_tamanho)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(cor_fase)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     _ROTULO_FASE[fase])
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(area.adjusted(5, 2, -5, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                     # Contava o acervo inteiro ("300 TIJOLOS") com ~34 na
                     # tela — numero que nao descreve nada do que se ve.
                     # Agora diz quantos estao DESENHADOS, e so cita o total
                     # quando ha mais alem da borda esquerda.
                     (f"{len(visiveis)} DE {len(tijolos)} TIJOLOS"
                      if len(visiveis) < len(tijolos)
                      else f"{len(visiveis)} TIJOLOS"))

    if rail.width() >= 24:
        _desenhar_rail_preco(painter, rail, estado, y_de_preco, centro_janela,
                             tam_ticks, linhas_verticais, tijolos[-1].fechamento)


def _desenhar_rail_preco(painter: QPainter, rail: QRect, estado: EstadoNexo,
                          y_de_preco, centro_janela: int, tam_ticks: int,
                          linhas_verticais: int, preco_atual: int) -> None:
    """Trilho de eixo de preco: niveis reais (ja em ticks) mais a capsula do
    ultimo fechamento de tijolo. Nenhum preco e inventado aqui.

    Usa o MESMO `y_de_preco` da area do grafico e os MESMOS niveis da grade
    (multiplos do tamanho do tijolo). Antes o trilho tinha escala propria
    (`rail.height() - 16`) e niveis por contagem: cada numero do eixo caia a
    alguns pixels da linha de grade correspondente, e o eixo lia como se
    fosse de outro grafico.
    """

    grid = estado.grid

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(rail.left(), rail.top(), rail.left(), rail.bottom())

    # Rotula um nivel a cada N tijolos, o suficiente para os textos nao se
    # tocarem — o passo e sempre um multiplo inteiro do tijolo, para o numero
    # cair exatamente em cima de uma linha de grade.
    alvo_niveis = max(RAIL_NIVEIS_MIN, min(RAIL_NIVEIS_MAX,
                                           rail.height() // RAIL_ALTURA_LINHA_PX))
    passo_niveis = max(1, round(linhas_verticais / max(1, alvo_niveis)))
    limiar_destaque = max(tam_ticks, (linhas_verticais * tam_ticks) // 16)
    painter.setFont(tokens.fonte_numero(7))
    inicio = -(linhas_verticais // 2)
    for indice in range(inicio, linhas_verticais // 2 + 1):
        if indice % passo_niveis:
            continue
        preco_nivel = centro_janela + indice * tam_ticks
        y = y_de_preco(preco_nivel)
        if not (rail.top() + 7 <= y <= rail.bottom() - 7):
            continue
        texto = formato.preco_completo(grid, preco_nivel)
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
