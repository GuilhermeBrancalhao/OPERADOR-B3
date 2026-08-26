"""Regiao PRESSAO + INSTRUMENTO (x 0,63-1,00 · y 0,86-1,00).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_estatistica_nexo``.
Fecha o canto inferior direito do quadro, encostando nas duas bordas.

Duas leituras vivem lado a lado, as duas so consultivas:

* **Par de pressao oposto** — UM trilho continuo cobrindo a largura
  inteira do bloco, preenchido verde da borda esquerda ate o ponto real
  do corte (a fracao de compra) e vermelho do corte ate a borda direita
  (o resto, sempre a fracao de venda). Como as duas fracoes somam 100, as
  duas cores sempre tocam as duas pontas do trilho — nunca sobra vao vazio
  numa ponta enquanto a outra fica cheia. Os dois percentuais ficam nas
  pontas externas do trilho (COMPRA a esquerda, VENDA a direita), com o
  rotulo de cada lado logo acima, e nada e desenhado entre os dois
  numeros: o par de pressao e um objeto so, nao dois numeros que o
  operador precisa juntar de cabeca.
* **Bloco do instrumento** — um selo circular (agulha propria, sem logotipo
  ou rosto de terceiros) cujo angulo espelha a mesma forca que preenche os
  trilhos, mais o rotulo do ativo corrente e a amplitude observada da serie,
  ambos com unidade explicita.

O par percentual e um **proxy de pressao declarado**, derivado da mesma linha
MAKERPROXY do snapshot; nao e execucao, nao e posicao e nao ha botao. O
rotulo do ativo vem da grade de precos (``EstadoNexo.grid``) — a unica pista
de instrumento que atravessa a fronteira ate esta regiao — e a amplitude vem
inteiramente da serie de precos ja congelada no snapshot (nunca inventada
quando a serie ainda nao tem dois pontos).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QFont, QPainter, QPen

from fluxopro.core.eventos import WDO_GRID, WIN_GRID
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.asg import ConfiancaASG
from fluxopro.ui.paineis.nexo import EstadoNexo

MARGEM_INTERNA = 8
GAP_COLUNAS = 14
ALTURA_SUBLINHADO = 4
ALTURA_RODAPE = 13
ALTURA_LEGENDA = 11
RESERVA_INFERIOR = ALTURA_RODAPE + ALTURA_SUBLINHADO + ALTURA_LEGENDA
FRACAO_INSTRUMENTO = 0.40
ESPESSURA_ANEL = 1.6
FRACAO_AGULHA = 0.34
EXTENSAO_EIXO = 2
LARGURA_EIXO = 2

_COR_CONFIANCA = {
    ConfiancaASG.ALTA: tema_asg.CONFIANCA_ALTA,
    ConfiancaASG.MEDIA: tema_asg.CONFIANCA_MEDIA,
    ConfiancaASG.BAIXA: tema_asg.CONFIANCA_BAIXA,
    ConfiancaASG.INDISPONIVEL: tema_asg.CONFIANCA_INDISPONIVEL,
}


def _rotulo_instrumento(grid: object) -> str:
    """Deriva o rotulo do ativo da propria grade de precos do quadro.

    Nao ha campo de simbolo na fronteira que chega ate esta regiao — o unico
    dado por-instrumento que ``EstadoNexo`` carrega e a grade de conversao de
    ticks. WDO e WIN sao as duas grades conhecidas do projeto (ver
    ``fluxopro.core.eventos``); qualquer outra grade cai num rotulo honesto
    derivado do proprio tamanho de tick, em vez de um ticker fixo chutado.
    """

    tick = getattr(grid, "tick_size", None)
    decimais = getattr(grid, "decimals", None)
    if tick == WDO_GRID.tick_size and decimais == WDO_GRID.decimals:
        return "WDO · B3"
    if tick == WIN_GRID.tick_size and decimais == WIN_GRID.decimals:
        return "WIN · B3"
    if tick is None:
        return "ATIVO INDISPONIVEL"
    return f"TICK {tick:g}"


def _formatar_pontos(valor: float, casas: int) -> str:
    if casas <= 0:
        return str(int(round(valor)))
    texto = f"{valor:.{casas}f}"
    inteiro, _, decimal = texto.partition(".")
    return f"{inteiro},{decimal}"


def _texto_amplitude(estado: EstadoNexo) -> str:
    """Amplitude observada da propria serie do quadro — nunca inventada.

    Com menos de dois pontos a serie ainda nao tem uma faixa: o estado
    honesto e declarar indisponivel, nao fabricar um numero.
    """

    precos = [preco for _, preco, _, _ in estado.serie]
    if len(precos) < 2:
        return "AMPLITUDE INDISPONIVEL"
    diferenca_ticks = max(precos) - min(precos)
    pontos = estado.grid.to_price(diferenca_ticks)
    return f"{_formatar_pontos(pontos, estado.grid.decimals)} PTS"


def _desenhar_trilho_pressao(
    painter: QPainter, trilho: QRect, compra: int, venda: int, cor_compra: object, cor_venda: object
) -> None:
    """Trilho UNICO, continuo, cobrindo a largura inteira do bloco.

    Nao sao dois medidores separados por um vao: e um so retangulo dividido
    no ponto real do corte — a fracao de compra, contada a partir da borda
    esquerda. Verde preenche da borda esquerda ate o corte, vermelho do
    corte ate a borda direita; como as duas fracoes somam sempre 100
    (``venda = 100 - compra``), as duas cores sempre tocam as duas pontas
    do trilho, sem vao morto numa ponta enquanto a outra fica cheia — o
    defeito antigo de dois cotos que nao alcancavam as bordas. O marcador
    do corte fica exatamente onde a cor muda, nunca num centro fixo, e e
    desenhado por cima dos preenchimentos para continuar visivel mesmo
    quando um lado chega a 0% ou 100%.
    """
    compra_travada = max(0, min(100, compra))
    corte_x = trilho.left() + int(round(trilho.width() * compra_travada / 100.0))
    limite_direito = trilho.right() + 1
    if corte_x > trilho.left():
        painter.fillRect(
            QRect(trilho.left(), trilho.top(), corte_x - trilho.left(), trilho.height()),
            cor_compra,
        )
    if corte_x < limite_direito:
        painter.fillRect(
            QRect(corte_x, trilho.top(), limite_direito - corte_x, trilho.height()),
            cor_venda,
        )
    eixo = QRect(
        corte_x - LARGURA_EIXO // 2,
        trilho.top() - EXTENSAO_EIXO,
        LARGURA_EIXO,
        trilho.height() + 2 * EXTENSAO_EIXO,
    )
    painter.fillRect(eixo, tema_asg.NEXO_MUTED)


def _desenhar_selo_instrumento(
    painter: QPainter, centro: QPointF, diametro: float, score: float, cor_status: object
) -> None:
    """Selo circular original (sem logotipo/rosto de terceiros).

    A agulha reflete o mesmo ``score`` que preenche os trilhos de pressao —
    o selo nao e decoracao solta, e a mesma leitura consultiva num segundo
    formato. O ponto de status no canto usa a confianca do MAKERPROXY.
    """

    raio = diametro / 2.0
    anel = QRect(
        int(centro.x() - raio), int(centro.y() - raio), int(diametro), int(diametro)
    )
    painter.setPen(QPen(tema_asg.NEXO_CIANO, ESPESSURA_ANEL))
    painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
    painter.drawEllipse(anel)

    score_travado = max(-1.0, min(1.0, score))
    angulo = math.radians(-90.0 - 45.0 * score_travado)
    raio_agulha = raio * FRACAO_AGULHA
    ponta = QPointF(
        centro.x() + raio_agulha * math.cos(angulo),
        centro.y() + raio_agulha * math.sin(angulo),
    )
    painter.setPen(QPen(tema_asg.NEXO_TEXTO, ESPESSURA_ANEL))
    painter.drawLine(centro, ponta)

    raio_status = max(2.0, diametro * 0.16)
    centro_status = QPointF(centro.x() + raio * 0.62, centro.y() + raio * 0.62)
    painter.setPen(QPen(tema_asg.NEXO_PAINEL_ALTO, 1.0))
    painter.setBrush(cor_status)
    painter.drawEllipse(centro_status, raio_status, raio_status)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 24 or rect.width() < 140:
        return
    maker = estado.maker
    score = maker.forca if maker is not None else 0.0
    compra = int(max(0.0, min(100.0, 50.0 + score * 50.0)))
    venda = 100 - compra
    confianca = getattr(maker, "confianca", None) if maker is not None else None
    cor_status = _COR_CONFIANCA.get(confianca, tema_asg.CONFIANCA_INDISPONIVEL)

    # A regiao encosta na borda direita do quadro: o texto precisa da propria
    # margem interna, senao o glifo final e cortado pelo limite da janela.
    interno = rect.adjusted(MARGEM_INTERNA, 0, -MARGEM_INTERNA, 0)
    largura_instrumento = max(120, int(interno.width() * FRACAO_INSTRUMENTO))
    largura_pressao = max(0, interno.width() - largura_instrumento - GAP_COLUNAS)
    coluna_pressao = QRect(interno.left(), interno.top(), largura_pressao, interno.height())
    coluna_instrumento = QRect(
        coluna_pressao.right() + GAP_COLUNAS, interno.top(),
        interno.right() - (coluna_pressao.right() + GAP_COLUNAS), interno.height(),
    )

    # --- par de pressao oposto -------------------------------------------
    altura_percentual = max(0, rect.height() - RESERVA_INFERIOR)
    metade = coluna_pressao.width() // 2
    tamanho = max(12, min(24, rect.height() // 4))
    painter.setFont(tokens.fonte_numero(tamanho, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_VERDE)
    painter.drawText(
        QRect(coluna_pressao.left(), rect.top(), metade, altura_percentual),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        f"{compra:02d}%",
    )
    painter.setPen(tema_asg.NEXO_ROSA)
    painter.drawText(
        QRect(coluna_pressao.left() + metade, rect.top(), coluna_pressao.width() - metade, altura_percentual),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        f"{venda:02d}%",
    )

    legenda = QRect(
        coluna_pressao.left(), rect.bottom() - RESERVA_INFERIOR,
        coluna_pressao.width(), ALTURA_LEGENDA,
    )
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(legenda, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "COMPRA")
    painter.drawText(legenda, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "VENDA")

    y_trilho = rect.bottom() - ALTURA_RODAPE - ALTURA_SUBLINHADO
    trilho = QRect(coluna_pressao.left(), y_trilho, coluna_pressao.width(), ALTURA_SUBLINHADO)
    _desenhar_trilho_pressao(painter, trilho, compra, venda, tema_asg.NEXO_VERDE, tema_asg.NEXO_ROSA)

    rodape = QRect(coluna_pressao.left(), rect.bottom() - ALTURA_RODAPE, coluna_pressao.width(), ALTURA_RODAPE)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter, "PROXY DE PRESSAO · NAO E EXECUCAO")

    # --- bloco do instrumento ----------------------------------------------
    banda_superior = QRect(
        coluna_instrumento.left(), rect.top(),
        coluna_instrumento.width(), max(0, rect.height() - RESERVA_INFERIOR),
    )
    diametro_selo = max(14.0, min(float(banda_superior.height()), 30.0))
    centro_selo = QPointF(
        banda_superior.left() + diametro_selo / 2.0, banda_superior.center().y()
    )
    _desenhar_selo_instrumento(painter, centro_selo, diametro_selo, score, cor_status)

    x_texto = int(centro_selo.x() + diametro_selo / 2.0 + 8)
    largura_texto = max(0, banda_superior.right() - x_texto)
    faixa_ativo = QRect(x_texto, banda_superior.top(), largura_texto, banda_superior.height())
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        faixa_ativo.adjusted(0, 0, 0, -faixa_ativo.height() // 2),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        "ATIVO",
    )
    painter.setFont(tokens.fonte_numero(max(11, tamanho - 4), QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_CIANO)
    painter.drawText(
        faixa_ativo.adjusted(0, faixa_ativo.height() // 2, 0, 0),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        _rotulo_instrumento(estado.grid),
    )

    banda_inferior = QRect(
        coluna_instrumento.left(), rect.bottom() - RESERVA_INFERIOR,
        coluna_instrumento.width(), RESERVA_INFERIOR,
    )
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        banda_inferior, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "AMPLITUDE"
    )
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(
        banda_inferior, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        _texto_amplitude(estado),
    )
