"""Regiao PLACAR ESTATISTICO (x 0,00-0,40 · y 0,79-1,00).

Esqueleto extraido da fileira de leituras derivadas de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. Ancorado no canto inferior
esquerdo do quadro, sangrando ate as duas bordas.

Estrutura (rodada 1 desta regiao):

* uma faixa de contagem COMPRA/VENDA — cada lado conta quantas das
  ``leituras`` atuais apontam naquela direcao, com a legenda declarando o
  denominador (``N DE M LEITURAS``) para que a contagem nunca apareca sem a
  procedencia de onde saiu;
* uma tira de barras a direita da contagem, construida a partir de
  ``estado.serie`` (a mesma serie de forca ja congelada no snapshot — nenhum
  dado novo e inferido aqui). Sem amostra, a tira declara o estado
  indisponivel em vez de desenhar barras falsas;
* os quatro ladrilhos de leitura (HORIZONTE/PULSO/PRESENCA/RITMO), agora com
  moldura inteira colorida pela direcao (nao so uma lasca na borda esquerda)
  e um chip de confianca no canto, lido de ``linha.confianca``.

Nada aqui e clicavel nem envia ordem: e leitura consultiva, com a mesma
regra das demais regioes do NEXO.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

VAO_LADRILHO = 4
VAO_LINHA = 4
ALTURA_TITULO = 14
ALTURA_ROTULO_BARRAS = 9
ALTURA_LEGENDA_BARRAS = 10

# Cor do chip de confianca, por nivel declarado em ``LinhaMatrizASG.confianca``.
# Vem inteiramente de ``tema_asg`` — nenhuma cor literal nova.
_MAPA_CONFIANCA = {
    _asg.ConfiancaASG.ALTA: tema_asg.CONFIANCA_ALTA,
    _asg.ConfiancaASG.MEDIA: tema_asg.CONFIANCA_MEDIA,
    _asg.ConfiancaASG.BAIXA: tema_asg.CONFIANCA_BAIXA,
    _asg.ConfiancaASG.INDISPONIVEL: tema_asg.CONFIANCA_INDISPONIVEL,
}

# Achado do operador (27/08/2026): "por que mudancas tao abruptas sempre,
# precisa ser algo mais tecnico". Ate 26/08/2026 o placar contava 1-a-1
# quantas das 4 leituras (HORIZONTE/PULSO/PRESENCA/RITMO) cruzavam
# direcao=COMPRA/VENDA — uma leitura de confianca BAIXA valia exatamente o
# mesmo que uma de confianca ALTA, e cada cruzamento de zero saltava a
# contagem inteira em 1 (0->1->2->3->4), nunca gradual.
#
# IMPRECISO — pesos de engenharia deste projeto, sem formula de fonte pra
# "quanto uma leitura de baixa confianca deve contar menos". O que muda:
# a contagem 1-a-1 continua existindo (e a legenda "N DE M LEITURAS"
# continua o denominador honesto, nunca removido), mas o NUMERO GRANDE em
# cada caixa passa a ser um placar PONDERADO por confianca — continuo, nao
# discreto — em vez do inteiro 0-4.
_PESO_CONFIANCA_PLACAR = {
    _asg.ConfiancaASG.ALTA: 1.0,
    _asg.ConfiancaASG.MEDIA: 0.6,
    _asg.ConfiancaASG.BAIXA: 0.3,
    _asg.ConfiancaASG.INDISPONIVEL: 0.0,
}


def placar_ponderado(leituras: tuple[tuple[str, object], ...]) -> float:
    """Score em [-1, 1]: media das `forca` das leituras, ponderada pela
    confianca de cada uma. `0.0` quando nenhuma leitura tem confianca > 0
    (nunca divide por zero, nunca inventa direcao de leitura indisponivel).
    """

    pesos = [
        (float(getattr(linha, "forca", 0.0)), _PESO_CONFIANCA_PLACAR.get(linha.confianca, 0.0))
        for _, linha in leituras
    ]
    soma_pesos = sum(peso for _, peso in pesos)
    if soma_pesos <= 0:
        return 0.0
    bruto = sum(forca * peso for forca, peso in pesos) / soma_pesos
    return max(-1.0, min(1.0, bruto))


def pesos_por_lado(leituras: tuple[tuple[str, object], ...]) -> tuple[float, float]:
    """Convicção de CADA lado, medida separadamente, em [0, 1] cada uma.

    Achado do operador (27/08/2026: "mudancas tao abruptas sempre"). Ate
    aqui as duas caixas nasciam de UM unico score assinado
    (``max(0, score)`` / ``max(0, -score)``): um dos dois lados era
    **sempre exatamente 0%** e, ao cruzar o zero, os dois numeros trocavam
    de lugar de uma vez. Nao era o mercado virando de uma vez — era a
    formula.

    Agora cada lado soma as SUAS proprias leituras:

        compra = Σ w_i · max(0, f_i) / Σ w_i
        venda  = Σ w_i · max(0, -f_i) / Σ w_i

    com ``w_i`` o peso de confianca de ``_PESO_CONFIANCA_PLACAR``. Duas
    propriedades que o operador pode conferir na tela:

    * **discordancia fica visivel**: com HORIZONTE comprador e RITMO
      vendedor os dois numeros ficam positivos ao mesmo tempo — antes o
      painel era obrigado a esconder um dos dois;
    * **reconciliacao exata**: ``compra - venda == placar_ponderado(...)``
      ao float. O saldo impresso no titulo do placar E o mesmo score, nao
      um segundo numero de outra fonte;
    * ``compra + venda <= 1``; o que falta para 1 e leitura sem conviccao
      (forca perto de zero ou confianca baixa) — nunca renormalizamos para
      100%, porque isso fabricaria conviccao que ninguem mediu.

    CONFIRMADO quanto a origem dos dados (as `forca`/`confianca` sao as
    mesmas ja congeladas no snapshot); IMPRECISO quanto aos pesos de
    confianca, que sao de engenharia deste projeto.

    Custo: nenhum atraso. A continuidade vem da formula ser continua nas
    forcas, nao de media movel — uma virada real de HORIZONTE aparece no
    mesmo quadro em que acontece.
    """

    pares = [
        (float(getattr(linha, "forca", 0.0)), _PESO_CONFIANCA_PLACAR.get(linha.confianca, 0.0))
        for _, linha in leituras
    ]
    soma_pesos = sum(peso for _, peso in pares)
    if soma_pesos <= 0:
        return 0.0, 0.0
    compra = sum(max(0.0, forca) * peso for forca, peso in pares) / soma_pesos
    venda = sum(max(0.0, -forca) * peso for forca, peso in pares) / soma_pesos
    return min(1.0, compra), min(1.0, venda)


LIMIAR_DIVERGENCIA = 0.15
"""IMPRECISO — limiar de engenharia. Acima disso nos DOIS lados ao mesmo
tempo, o placar carimba DIVERGENTES no titulo: as leituras discordam de
verdade e o operador precisa saber que o saldo pequeno nao e calmaria, e
puxao dos dois lados. 0,15 e ~1 leitura de confianca ALTA a meia forca
entre 4."""


JANELA_SUAVIZACAO_FORCA = 5
"""Media movel causal (so olha pra tras) sobre a forca bruta de cada
amostra. Pedido do operador: a tira de barras crua alternava sinal a cada
negocio (a forca por-trade e genuinamente ruidosa) e nao dava pra ler
tendencia nenhuma nisso — cada barra so descrevia UM negocio, nao "quanto
de forca o mercado tem agora". Suavizar nao fabrica dado novo: a media e
sobre os MESMOS valores reais de `estado.serie`, nunca lookahead (a janela
so inclui amostras ja observadas ate aquele ponto)."""


def _suavizar_forca(
    amostras: tuple[tuple[int, int, float, int], ...], janela: int = JANELA_SUAVIZACAO_FORCA
) -> tuple[float, ...]:
    valores = [item[2] for item in amostras]
    suavizados = []
    for indice in range(len(valores)):
        inicio = max(0, indice - janela + 1)
        recorte = valores[inicio : indice + 1]
        suavizados.append(sum(recorte) / len(recorte))
    return tuple(suavizados)


def _cor_forca(forca: float):
    """Mapeia o sinal da forca observada para o eixo de cor do NEXO.

    Usa o mesmo par verde/rosa das demais regioes (``_cor_nexo_direcao``);
    nao inventa paleta nova para a tira de barras.
    """

    if forca > 0.05:
        return _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA)
    if forca < -0.05:
        return _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA)
    return _asg._cor_nexo_direcao(_asg.DirecaoASG.NEUTRA)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return

    leituras = estado.leituras
    total = len(leituras)

    compra_peso, venda_peso = pesos_por_lado(leituras)
    saldo = compra_peso - venda_peso

    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    titulo = "PLACAR ESTATISTICO  ·  4 LEITURAS PONDERADAS POR CONFIANCA"
    if min(compra_peso, venda_peso) >= LIMIAR_DIVERGENCIA:
        titulo += "  ·  LEITURAS DIVERGENTES"
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 110, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     titulo)
    # O SALDO impresso aqui e, por construcao, o mesmo `placar_ponderado`
    # (compra - venda). E a ponte explicita entre as duas caixas grandes e
    # o score unico que o resto do quadro usa — nunca um terceiro numero.
    painter.drawText(QRect(rect.right() - 106, rect.top(), 102, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     f"SALDO {saldo * 100:+.0f}%  ·  N={total}")

    corpo = QRect(rect.left(), rect.top() + ALTURA_TITULO + 2, rect.width(),
                  max(20, rect.height() - ALTURA_TITULO - 2))

    if not leituras:
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawRect(corpo.adjusted(1, 1, -2, -2))
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(corpo, Qt.AlignmentFlag.AlignCenter,
                         "SEM LEITURA DERIVADA · AGUARDANDO SNAPSHOT")
        return

    altura_resumo = max(46, round(corpo.height() * 0.60))
    linha_resumo = QRect(corpo.left(), corpo.top(), corpo.width(), altura_resumo)
    linha_ladrilhos = QRect(corpo.left(), linha_resumo.bottom() + VAO_LINHA, corpo.width(),
                            max(20, corpo.height() - altura_resumo - VAO_LINHA))

    largura_contagem = max(120, round(linha_resumo.width() * 0.44))
    bloco_contagem = QRect(linha_resumo.left(), linha_resumo.top(), largura_contagem,
                           linha_resumo.height())
    bloco_barras = QRect(bloco_contagem.right() + VAO_LADRILHO, linha_resumo.top(),
                         max(30, linha_resumo.width() - largura_contagem - VAO_LADRILHO),
                         linha_resumo.height())

    _desenhar_contagem(painter, bloco_contagem, leituras, total)
    _desenhar_barras(painter, bloco_barras, estado.serie)
    _desenhar_ladrilhos(painter, linha_ladrilhos, leituras)


def _desenhar_contagem(painter: QPainter, rect: QRect,
                       leituras: tuple[tuple[str, object], ...], total: int) -> None:
    """Duas caixas com moldura de estado: quantas leituras apontam pra cada lado.

    A contagem nasce de ``leituras`` (o mesmo tanto passado para os
    ladrilhos abaixo) — nunca um numero solto: a legenda de cada caixa
    declara o denominador de onde ela saiu.
    """

    n_compra = sum(1 for _, linha in leituras if linha.direcao is _asg.DirecaoASG.COMPRA)
    n_venda = sum(1 for _, linha in leituras if linha.direcao is _asg.DirecaoASG.VENDA)
    # Cada lado sai da SUA propria soma (ver `pesos_por_lado`), nao de um
    # score assinado unico — por isso os dois podem ser >0 ao mesmo tempo e
    # nenhum dos dois salta ao cruzar o zero.
    peso_compra, peso_venda = pesos_por_lado(leituras)
    largura = max(40, (rect.width() - VAO_LADRILHO) // 2)
    caixa_compra = QRect(rect.left(), rect.top(), largura, rect.height())
    caixa_venda = QRect(caixa_compra.right() + VAO_LADRILHO, rect.top(),
                        max(40, rect.width() - largura - VAO_LADRILHO), rect.height())
    _desenhar_placar(painter, caixa_compra, "COMPRA", peso_compra, n_compra, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA))
    _desenhar_placar(painter, caixa_venda, "VENDA", peso_venda, n_venda, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA))


def _desenhar_placar(painter: QPainter, caixa: QRect, rotulo: str, peso: float,
                     contagem: int, total: int, cor) -> None:
    """`peso` (0-1, ja isolado por lado — ver `placar_ponderado`) e o NUMERO
    GRANDE agora; `contagem`/`total` continuam so na legenda de baixo, como
    o denominador honesto de sempre — nunca removidos, so deixaram de ser
    o numero principal."""

    painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
    caneta = QPen(cor)
    caneta.setWidth(2)
    painter.setPen(caneta)
    painter.drawRect(caixa.adjusted(1, 1, -2, -2))

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(6, 4, -6, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, rotulo)

    painter.setFont(tokens.fonte_numero(max(16, min(30, caixa.height() // 2)),
                                        QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(caixa.adjusted(6, 12, -6, -14), Qt.AlignmentFlag.AlignCenter,
                     f"{round(peso * 100)}%")

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(6, 0, -6, -3),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     f"{contagem} DE {total} LEITURAS · CONVICCAO PONDERADA")


# Silhueta de raio/relampago (pedido do operador, 27/08/2026: "deve ser
# representados por raios, verde quando e positivo e vermelho para
# negativos" — substitui a barra retangular lisa). Pontos em coordenadas
# UNITARIAS (0..1 em x e y), sentido "caindo" de cima pra baixo (y=0 topo,
# y=1 base) — a forma natural de um relampago aponta pra baixo. Barras
# NEGATIVAS (que ja crescem do eixo pra baixo neste grafico) usam a forma
# direto; POSITIVAS espelham verticalmente, porque aqui "positivo" cresce
# pra cima como qualquer outra barra do produto — o raio come continua
# apontando "para fora" do eixo em vez de de cabeca para baixo.
_PONTOS_RAIO_UNITARIOS = (
    (0.55, 0.00), (0.15, 0.55), (0.42, 0.55),
    (0.05, 1.00), (0.62, 0.42), (0.35, 0.42),
)


def _poligono_raio(caixa: QRect, invertido: bool) -> QPolygon:
    largura = max(1, caixa.width())
    altura = max(1, caixa.height())
    pontos = []
    for ux, uy in _PONTOS_RAIO_UNITARIOS:
        y = (1.0 - uy) if invertido else uy
        pontos.append(QPoint(caixa.left() + round(ux * largura), caixa.top() + round(y * altura)))
    return QPolygon(pontos)


def _desenhar_barras(painter: QPainter, rect: QRect,
                     serie: tuple[tuple[int, int, float, int], ...]) -> None:
    """Tira de barras da forca observada, direto de ``estado.serie``.

    Sem amostra o bloco declara ``SEM HISTORICO DE FORCA`` em vez de
    desenhar barras inventadas — a mesma regra de estado honesto que vale
    para book ausente no replay MT5.

    Correcao desta rodada: a legenda ("N AMOSTRAS · FORCA OBSERVADA") vivia
    na MESMA faixa vertical onde as barras podem crescer ate a base do
    bloco — com ``forca`` perto de 1.0 (o caso comum, ver evidencia desta
    rodada) o preenchimento rosa/verde cobre o texto cinza por cima dele,
    ou o deixa ilegivel por falta de contraste. Agora o rotulo (o "titulo"
    que faltava, no mesmo lugar onde os placares COMPRA/VENDA tem o deles)
    e a legenda de contagem ficam em faixas reservadas, fora da area onde
    as barras desenham — nunca mais por baixo de uma barra.
    """

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawRect(rect.adjusted(0, 0, -1, -1))

    if not serie:
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM HISTORICO DE FORCA")
        return

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(6, 3, -6, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     "FORCA OBSERVADA")

    amostras = serie[-24:]
    # Suavizado sobre a serie INTEIRA (nunca so a janela visivel), pra a
    # primeira barra visivel nao comecar sem historico — so entao recorta
    # as ultimas 24. Mesmo criterio causal do resto do projeto.
    forcas_suavizadas = _suavizar_forca(serie)[-len(amostras):]
    faixa_grafico = QRect(rect.left(), rect.top() + ALTURA_ROTULO_BARRAS, rect.width(),
                          max(10, rect.height() - ALTURA_ROTULO_BARRAS - ALTURA_LEGENDA_BARRAS))
    area = faixa_grafico.adjusted(3, 1, -3, -1)
    vao = 2
    n = max(1, len(amostras))
    largura_barra = max(2, (area.width() - (n - 1) * vao) // n)
    meio_y = area.center().y()
    metade = max(4, area.height() // 2 - 2)

    painter.setPen(Qt.PenStyle.NoPen)
    x = area.left()
    for forca in forcas_suavizadas:
        cor = _cor_forca(forca)
        altura = max(4, round(min(1.0, abs(forca)) * metade))
        if forca >= 0:
            caixa_raio = QRect(x, meio_y - altura, largura_barra, altura)
            invertido = True
        else:
            caixa_raio = QRect(x, meio_y, largura_barra, altura)
            invertido = False
        painter.setBrush(cor)
        painter.drawPolygon(_poligono_raio(caixa_raio, invertido))
        x += largura_barra + vao
    painter.setBrush(Qt.BrushStyle.NoBrush)

    caneta_eixo = QPen(tema_asg.NEXO_MUTED)
    caneta_eixo.setWidth(2)
    painter.setPen(caneta_eixo)
    painter.drawLine(area.left(), meio_y, area.right(), meio_y)

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left(), faixa_grafico.bottom(), rect.width() - 6,
                          ALTURA_LEGENDA_BARRAS),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     f"{len(amostras)} AMOSTRAS · FORCA OBSERVADA")


def _desenhar_ladrilhos(painter: QPainter, corpo: QRect,
                        leituras: tuple[tuple[str, object], ...]) -> None:
    largura = max(40, (corpo.width() + VAO_LADRILHO) // len(leituras) - VAO_LADRILHO)
    for indice, (nome, linha) in enumerate(leituras):
        caixa = QRect(corpo.left() + indice * (largura + VAO_LADRILHO), corpo.top(),
                      largura, corpo.height())
        cor = _asg._cor_nexo_direcao(linha.direcao)

        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        caneta = QPen(cor)
        caneta.setWidth(1)
        painter.setPen(caneta)
        painter.drawRect(caixa.adjusted(0, 0, -1, -1))

        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(6, 4, -5, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, nome)

        painter.setFont(tokens.fonte_numero(max(12, min(20, caixa.height() // 4)),
                                            QFont.Weight.Bold))
        painter.setPen(cor)
        painter.drawText(caixa.adjusted(6, 0, -5, -16), Qt.AlignmentFlag.AlignCenter,
                         f"{linha.forca * 100:+.0f}%")

        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(6, 0, -5, -3),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         linha.valor[:12])

        _desenhar_chip_confianca(painter, caixa, linha.confianca)


def _desenhar_chip_confianca(painter: QPainter, caixa: QRect, confianca) -> None:
    """Chip de status no canto do ladrilho, lido de ``linha.confianca``.

    Cor e texto vem do enum ``ConfiancaASG`` ja existente na matriz — nao e
    rotulo novo, e a mesma classificacao que os outros paineis ASG usam.
    """

    cor = _MAPA_CONFIANCA.get(confianca, tema_asg.CONFIANCA_INDISPONIVEL)
    texto = confianca.value.replace("CONF ", "").replace("—", "SEM CONF")
    largura_chip = min(max(20, caixa.width() - 8), 8 + 5 * len(texto))
    chip = QRect(caixa.right() - largura_chip - 4, caixa.top() + 3, largura_chip, 10)
    painter.fillRect(chip, cor)
    painter.setFont(tokens.fonte_rotulo(5))
    painter.setPen(tema_asg.CHIP_TEXTO)
    painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, texto)
