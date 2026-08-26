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

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPen

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

    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 90, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "PLACAR ESTATISTICO  ·  LEITURAS DERIVADAS")
    painter.drawText(QRect(rect.right() - 86, rect.top(), 82, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     f"N={total}")

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
    largura = max(40, (rect.width() - VAO_LADRILHO) // 2)
    caixa_compra = QRect(rect.left(), rect.top(), largura, rect.height())
    caixa_venda = QRect(caixa_compra.right() + VAO_LADRILHO, rect.top(),
                        max(40, rect.width() - largura - VAO_LADRILHO), rect.height())
    _desenhar_placar(painter, caixa_compra, "COMPRA", n_compra, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA))
    _desenhar_placar(painter, caixa_venda, "VENDA", n_venda, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA))


def _desenhar_placar(painter: QPainter, caixa: QRect, rotulo: str, contagem: int,
                     total: int, cor) -> None:
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
                     str(contagem))

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(6, 0, -6, -3),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     f"{contagem} DE {total} LEITURAS")


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
    faixa_grafico = QRect(rect.left(), rect.top() + ALTURA_ROTULO_BARRAS, rect.width(),
                          max(10, rect.height() - ALTURA_ROTULO_BARRAS - ALTURA_LEGENDA_BARRAS))
    area = faixa_grafico.adjusted(3, 1, -3, -1)
    vao = 2
    n = max(1, len(amostras))
    largura_barra = max(2, (area.width() - (n - 1) * vao) // n)
    meio_y = area.center().y()
    metade = max(4, area.height() // 2 - 2)

    x = area.left()
    for _, _, forca, _ in amostras:
        cor = _cor_forca(forca)
        altura = max(2, round(min(1.0, abs(forca)) * metade))
        if forca >= 0:
            barra = QRect(x, meio_y - altura, largura_barra, altura)
        else:
            barra = QRect(x, meio_y, largura_barra, altura)
        painter.fillRect(barra, cor)
        x += largura_barra + vao

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
