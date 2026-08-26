"""Regiao FAIXA DE NIVEIS (x 0,02-0,40 · y 0,55-0,65).

Esqueleto extraido da fileira de cotacoes de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. A faixa avanca um centesimo
do quadro sobre CONTEXTO/ESCADA de proposito: e a costura horizontal que amarra
a coluna da esquerda, e nao um cartao separado.

A faixa e uma trilha de leitura, nao um livro de ofertas clicavel: cinco
capsulas **fixas**, cada uma amarrada por contrato (`_NIVEIS` abaixo) a um
nivel semantico proprio -- a capsula de indice 2 e sempre "melhor bid",
quadro apos quadro, nunca "o segundo item que sobrou depois de filtrar os
vazios". Isso fecha o defeito de "indice nao pareado a valor": o numero
pintado no canto de cada capsula e a posicao dela na lista `_NIVEIS`, nunca
um `enumerate()` sobre o que calhou de vir preenchido neste quadro. Quando um
nivel some do book (profundidade menor que o esperado), a capsula continua no
lugar dela e vira estado VAZIA -- ela nunca desliza para a esquerda para
"preencher o buraco", o que trocaria o indice pareado por outro valor.

Estados de cada capsula, em ordem de forca visual:

* ATIVA -- melhor bid, ultimo negociado e melhor ask: preenchimento solido
  na cor de acento, texto escuro por cima (``tema_asg.CHIP_TEXTO``, o mesmo
  criterio de contraste texto-escuro-sobre-fundo-claro de ``paineis/
  metodo.py``).
* ECOA -- segundo nivel de cada lado (o "eco" mais profundo do topo do
  livro): base ``NEXO_PAINEL_ALTO`` com uma tintura de baixa alfa por cima
  (``tema_asg.NEXO_*_FAIXA`` -- os mesmos tokens da faixa de profundidade
  do produto) e uma lasca solida na cor de acento para nao perder a
  identidade de lado (compra/venda).
* VAZIA -- nao ha leitura para aquele nivel neste quadro (profundidade
  insuficiente, ou o proprio ``contexto_bruto`` ausente): a capsula nunca
  inventa preco. Fica sem tintura de acento, borda e texto em
  ``NEXO_MUTED``, rotulo "--". Esta e a leitura honesta exigida quando o
  MT5 em replay nao tem historico de livro -- uma capsula VAZIA e um dado
  ausente declarado, nao um zero disfarcado.

Os chips sao **capsulas de leitura**. Nao existe estado de foco/clique e nao
ha callback: nenhum nivel aqui pode ser acionado, e este modulo nunca
registra um handler de mouse -- ``desenhar`` recebe um ``QPainter`` e um
``EstadoNexo`` imutavel, e mais nada.

O cabecalho de cada capsula tem DOIS papeis que nao podem colapsar num so
texto do mesmo tamanho: o INDICE (posicao fixa 1-5, o locator) e o ROTULO
(o papel semantico -- BID, ULT, ASK, ou o par lado+profundidade "BID 2" /
"ASK 2"). Um auditor que olha a faixa sem ter decorado a ordem precisa
identificar o papel de cada capsula so pelo rotulo, sem contar posicoes.
Por isso o rotulo e desenhado maior e na cor de papel da capsula (a mesma
usada no preco -- ``cor_texto``), enquanto o indice fica pequeno e discreto
ao lado dele (``cor_indice``): o rotulo e a informacao, o indice e so a
prova de que a posicao e fixa. Encolher o rotulo de volta ao tamanho do
indice reabre o defeito "capsula ilegivel sem decorar a ordem".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

VAO_CHIP = 4
ALTURA_CHIP_MAX = 46
FAIXA_INDICE_ALTURA = 14
ESPESSURA_LASCA = 2
TAM_FONTE_INDICE = 6
TAM_FONTE_ROTULO = 8
VAO_INDICE_ROTULO = 3

_LeitorPreco = Callable[[object], "int | None"]


@dataclass(frozen=True)
class _Nivel:
    """Uma posicao fixa da trilha. ``indice`` e o contrato de exibicao."""

    indice: int
    rotulo: str
    ler: _LeitorPreco
    cor: QColor
    cor_ecoa: QColor
    ativo: bool


def _leitor_bid(profundidade: int) -> _LeitorPreco:
    def _ler(contexto: object) -> "int | None":
        bids = getattr(contexto, "bids", None) or ()
        if profundidade < len(bids):
            return int(bids[profundidade].preco)
        return None

    return _ler


def _leitor_ask(profundidade: int) -> _LeitorPreco:
    def _ler(contexto: object) -> "int | None":
        asks = getattr(contexto, "asks", None) or ()
        if profundidade < len(asks):
            return int(asks[profundidade].preco)
        return None

    return _ler


def _leitor_ultimo(contexto: object) -> "int | None":
    preco = getattr(contexto, "ultimo_preco", None)
    return int(preco) if preco is not None else None


# Contrato fixo de 5 capsulas. A ORDEM e a POSICAO aqui sao o pareamento
# indice<->valor: mexer na ordem desta tupla e o unico jeito valido de mudar
# o que uma capsula significa, e mexe-la ao mesmo tempo em toda leitura desta
# docstring.
_NIVEIS: tuple[_Nivel, ...] = (
    _Nivel(1, "BID 2", _leitor_bid(1), tema_asg.NEXO_VERDE, tema_asg.NEXO_VERDE_FAIXA, False),
    _Nivel(2, "BID", _leitor_bid(0), tema_asg.NEXO_VERDE, tema_asg.NEXO_VERDE_FAIXA, True),
    _Nivel(3, "ULT", _leitor_ultimo, tema_asg.NEXO_CIANO, tema_asg.NEXO_CIANO_FAIXA, True),
    _Nivel(4, "ASK", _leitor_ask(0), tema_asg.NEXO_ROSA, tema_asg.NEXO_ROSA_FAIXA, True),
    _Nivel(5, "ASK 2", _leitor_ask(1), tema_asg.NEXO_ROSA, tema_asg.NEXO_ROSA_FAIXA, False),
)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 24 or rect.width() < 80:
        return
    contexto = getattr(estado.snapshot, "contexto_bruto", None)
    leituras = [(nivel, nivel.ler(contexto) if contexto is not None else None) for nivel in _NIVEIS]
    if contexto is None or all(preco is None for _, preco in leituras):
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "SEM NIVEIS OBSERVADOS")
        return

    n = len(_NIVEIS)
    largura = max(48, (rect.width() + VAO_CHIP) // n - VAO_CHIP)
    altura = min(rect.height(), ALTURA_CHIP_MAX)
    topo = rect.bottom() - altura

    for nivel, preco in leituras:
        posicao = nivel.indice - 1
        caixa = QRect(rect.left() + posicao * (largura + VAO_CHIP), topo, largura, altura)
        _desenhar_capsula(painter, caixa, estado, nivel, preco)


def _desenhar_capsula(painter: QPainter, caixa: QRect, estado: EstadoNexo,
                       nivel: _Nivel, preco: "int | None") -> None:
    vazia = preco is None
    if vazia:
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL)
        cor_lasca = tema_asg.NEXO_MUTED
        cor_indice = tema_asg.NEXO_MUTED
        cor_texto = tema_asg.NEXO_MUTED
    elif nivel.ativo:
        painter.fillRect(caixa, nivel.cor)
        cor_lasca = nivel.cor
        cor_indice = tema_asg.CHIP_TEXTO
        cor_texto = tema_asg.CHIP_TEXTO
    else:
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        painter.fillRect(caixa, nivel.cor_ecoa)
        cor_lasca = nivel.cor
        cor_indice = tema_asg.NEXO_MUTED
        cor_texto = nivel.cor

    painter.fillRect(QRect(caixa.left(), caixa.top(), ESPESSURA_LASCA, caixa.height()), cor_lasca)

    # O indice e o ROTULO nao competem pelo mesmo tamanho: o rotulo (o papel
    # semantico -- "BID", "ASK 2"...) e o que um operador precisa ler sem
    # decorar a ordem, entao ele ganha a fonte maior e a cor de papel da
    # capsula (``cor_texto``, a mesma do preco). O indice e so o locator
    # fixo por tras dele -- pequeno, na cor discreta ``cor_indice``.
    faixa_cabecalho = QRect(caixa.left() + 6, caixa.top() + 1, caixa.width() - 8, FAIXA_INDICE_ALTURA)
    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_INDICE))
    painter.setPen(cor_indice)
    texto_indice = str(nivel.indice)
    painter.drawText(faixa_cabecalho, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     texto_indice)
    largura_indice = painter.fontMetrics().horizontalAdvance(texto_indice)

    faixa_rotulo = QRect(faixa_cabecalho.left() + largura_indice + VAO_INDICE_ROTULO, faixa_cabecalho.top(),
                          max(0, faixa_cabecalho.width() - largura_indice - VAO_INDICE_ROTULO),
                          faixa_cabecalho.height())
    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO))
    painter.setPen(cor_texto)
    painter.drawText(faixa_rotulo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     nivel.rotulo)

    faixa_valor = QRect(caixa.left() + 6, caixa.top() + FAIXA_INDICE_ALTURA + 1,
                         caixa.width() - 8, caixa.height() - FAIXA_INDICE_ALTURA - 3)
    painter.setPen(cor_texto)
    if vazia:
        painter.setFont(tokens.fonte_numero(11, QFont.Weight.Normal))
        painter.drawText(faixa_valor, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "--")
    else:
        formatado = formato.formatar_preco(estado.grid, preco)
        painter.setFont(tokens.fonte_numero(11, QFont.Weight.Bold))
        painter.drawText(faixa_valor, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{formatado[0]}{formatado[1]}")
