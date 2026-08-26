"""Regiao ESCADA DE PRECO (x 0,00-0,06 · y 0,00-0,56).

Escada de ticks CONTIGUA do livro observado, sangrando ate a borda esquerda
do quadro, sem moldura de cartao. Duas micro-colunas lado a lado dentro da
mesma faixa estreita:

* a lane esquerda e o numero do preco daquele tick;
* a lane direita e a barra de profundidade daquele tick MAIS o numeral da
  quantidade (`formato.abreviar`), alinhado a direita por cima da barra —
  a segunda micro-coluna que o esqueleto original nao tinha, e que o round
  anterior deixava como barra muda (sem ler o tamanho, so o comprimento).

Uma capsula solida (fundo `NEXO_AMARELO`, texto `CHIP_TEXTO` escuro por
cima) marca a linha do ultimo preco negociado — o mesmo par
fundo-claro/texto-escuro que `paineis/metodo.py` e `nexo/niveis.py` ja usam
para chip legivel, entao nao e uma regra nova.

A escada cobre a ALTURA INTEIRA da regiao, no passo continuo da grade de
tick do simbolo (`estado.grid`) centrado no preco corrente: o numero de
linhas sai so da altura disponivel dividido pelo passo alvo (nunca do
tamanho do livro recebido), porque a grade de precos existe
independentemente de quantos niveis o quadro capturou — parar a escada no
ultimo tick com dado e deixar o resto da coluna em preto era o defeito
(critico do round anterior: 11 linhas desenhadas, coluna com espaco para
o dobro).

Um tick com nivel explicito mostra bar + numeral de quantidade. Um tick
sem nivel — DENTRO ou FORA do alcance ``[menor tick recebido, maior tick
recebido]`` entre bids/asks/ultimo_preco — recebe o MESMO tratamento visual
neutro que ja existia para o gap dentro do alcance: preco em
`NEXO_MUTED`, sem barra, sem numeral. Isso nunca fabrica tamanho (nenhum
numero de quantidade aparece onde nao ha nivel), so estende a mesma régua
de precos que a grade do simbolo ja define objetivamente — nao e uma
alegacao sobre profundidade, e a mesma linha em branco que ja se desenhava
dentro do alcance (rank K salta rank K+1 = zero ali,
`fluxopro/ui/paineis/asg.py::ContextoBrutoASGSnapshot.de_instantaneo` corta
em 8 por lado mas preserva ordem por rank). Mesmo cuidado do estado "SEM
BOOK": honesto sobre o que falta, nunca sintetico.

Nao ha clique, callback nem campo: a coluna inteira e leitura.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

# Faixa de altura de linha aceitavel. Fora dela a coluna vira ou uma lista de
# tres numeros gigantes ou uma serrilha ilegivel.
ALTURA_LINHA_MIN = 9
ALTURA_LINHA_MAX = 20

# Altura que a coluna MIRA — sempre perto do extremo denso da faixa
# aceitavel, porque a leitura desta regiao e uma escada continua de
# dezenas de linhas (ver referencia do round: ~45 linhas a ~10px), nunca
# 3+3 melhores ofertas com folga em branco embaixo. O numero de linhas sai
# so de `altura_util // ALTURA_LINHA_ALVO`; nao ha teto pelo tamanho do
# livro recebido (ver docstring do modulo).
ALTURA_LINHA_ALVO = 10

# Fracao da largura da regiao dedicada ao numero do preco. O resto e a
# segunda micro-coluna: a barra de profundidade daquele tick.
FRACAO_LANE_PRECO = 0.50

LARGURA_MIN = 24
ALTURA_ROTULO = 12
ALTURA_MIN_PARA_ROTULO = 60


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < LARGURA_MIN or rect.height() < ALTURA_LINHA_MIN * 2:
        return

    contexto = getattr(estado.snapshot, "contexto_bruto", None)
    bids = tuple(contexto.bids) if contexto is not None else ()
    asks = tuple(contexto.asks) if contexto is not None else ()
    ultimo = (
        int(contexto.ultimo_preco)
        if contexto is not None and contexto.ultimo_preco is not None
        else None
    )

    if not bids and not asks:
        _desenhar_indisponivel(painter, rect, ultimo, estado)
        return

    # tick -> (quantidade, eh_bid). Ultima escrita vence num book cruzado
    # (nunca deveria acontecer, mas nao e este arquivo que valida a fonte).
    por_tick: dict[int, tuple[int, bool]] = {}
    for nivel in bids:
        por_tick[nivel.preco] = (nivel.quantidade, True)
    for nivel in asks:
        por_tick[nivel.preco] = (nivel.quantidade, False)

    ticks_conhecidos = list(por_tick.keys())
    if ultimo is not None:
        ticks_conhecidos.append(ultimo)
    tick_min, tick_max = min(ticks_conhecidos), max(ticks_conhecidos)

    reservar_rotulo = rect.height() >= ALTURA_MIN_PARA_ROTULO
    altura_util = rect.height() - (ALTURA_ROTULO if reservar_rotulo else 0)

    # Preenche a altura INTEIRA da regiao no passo continuo da grade — o
    # numero de linhas nunca e limitado pelo tamanho do livro recebido (essa
    # era a coluna truncada que o critico do round anterior pegou: 11
    # linhas desenhadas, resto da altura em preto).
    n_linhas = max(1, altura_util // ALTURA_LINHA_ALVO)
    altura = max(ALTURA_LINHA_MIN, min(ALTURA_LINHA_MAX, altura_util // n_linhas))

    if ultimo is not None:
        centro = ultimo
    elif bids and asks:
        centro = round((bids[0].preco + asks[0].preco) / 2)
    else:
        centro = ticks_conhecidos[0]
    centro = min(max(centro, tick_min), tick_max)

    # Janela CONTIGUA de `n_linhas` ticks centrada em `centro`, no passo
    # continuo de 1 tick por linha (a propria grade do simbolo — ver
    # docstring do modulo). Pode extrapolar [tick_min, tick_max]: no loop
    # abaixo, um tick sem nivel explicito — dentro ou fora desse alcance —
    # cai no mesmo ramo `else` (cor NEXO_MUTED, sem barra, sem numeral), so
    # estendendo a régua de precos, nunca afirmando tamanho onde nao ha
    # dado.
    topo = centro + n_linhas // 2
    ticks = list(range(topo, topo - n_linhas, -1))

    maior_qtd = max((por_tick.get(t, (0, False))[0] for t in ticks), default=0) or 1

    largura_preco = max(1, int(rect.width() * FRACAO_LANE_PRECO))
    x_barra = rect.left() + largura_preco
    largura_barra = rect.width() - largura_preco

    fonte_preco = tokens.fonte_numero(6, QFont.Weight.DemiBold)
    # Peso mais leve que o preco: o numeral de quantidade e uma leitura de
    # apoio (compete pela mesma lane estreita com a barra, ver
    # `formato.abreviar`), o preco continua sendo o dado primario da linha.
    fonte_qtd = tokens.fonte_numero(6, QFont.Weight.Normal)
    painter.setFont(fonte_preco)
    y_destaque: int | None = None
    for indice, tick in enumerate(ticks):
        y = rect.top() + indice * altura
        quantidade, eh_bid = por_tick.get(tick, (0, None))
        if eh_bid is True:
            cor, cor_barra = tema_asg.NEXO_VERDE, tema_asg.NEXO_VERDE_FAIXA
        elif eh_bid is False:
            cor, cor_barra = tema_asg.NEXO_ROSA, tema_asg.NEXO_ROSA_FAIXA
        else:
            cor, cor_barra = tema_asg.NEXO_MUTED, None

        if quantidade > 0 and cor_barra is not None and largura_barra > 2:
            comprimento = max(2, int(largura_barra * quantidade / maior_qtd))
            painter.fillRect(
                QRect(x_barra, y + 1, comprimento, max(2, altura - 2)), cor_barra
            )
            # Numeral legivel por cima da barra — sem isto a barra so da o
            # comprimento relativo, nunca o tamanho real que o operador lê.
            painter.setFont(fonte_qtd)
            painter.setPen(cor)
            painter.drawText(
                QRect(x_barra + 2, y, largura_barra - 4, altura),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                formato.abreviar(quantidade, com_sinal=False),
            )
            painter.setFont(fonte_preco)

        if tick == ultimo:
            # A capsula de destaque cobre esta linha inteira depois do loop;
            # nao pinta o numero duas vezes por cima dela.
            y_destaque = y
            continue

        painter.setPen(cor)
        preco = formato.formatar_preco(estado.grid, tick)
        painter.drawText(
            QRect(rect.left(), y, largura_preco - 3, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{preco[0]}{preco[1]}",
        )

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(x_barra, rect.top(), x_barra, rect.top() + n_linhas * altura)

    if y_destaque is not None and ultimo is not None:
        caixa = QRect(rect.left(), y_destaque, rect.width(), altura)
        painter.fillRect(caixa, tema_asg.NEXO_AMARELO)
        painter.setPen(tema_asg.CHIP_TEXTO)
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        painter.drawText(
            caixa, Qt.AlignmentFlag.AlignCenter, formato.preco_completo(estado.grid, ultimo)
        )

    if reservar_rotulo:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(
            QRect(rect.left(), rect.bottom() - ALTURA_ROTULO, rect.width(), ALTURA_ROTULO),
            Qt.AlignmentFlag.AlignCenter,
            "LIVRO",
        )


def _desenhar_indisponivel(
    painter: QPainter, rect: QRect, ultimo: int | None, estado: EstadoNexo
) -> None:
    """Estado honesto quando o quadro nao trouxe nivel nenhum de book.

    Nunca desenha barra aqui: sem nivel nao ha profundidade para medir, e uma
    barra de comprimento chutado seria liquidez sintetica — exatamente o que
    o contrato do replay sem historico de book proibe. Se ao menos o ultimo
    preco negociado chegou (tape vivo sem DOM), mostra so ele; sem nem isso,
    e so o rotulo.
    """
    if ultimo is not None:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        preco = formato.formatar_preco(estado.grid, ultimo)
        centro = QRect(rect.left(), rect.center().y() - 9, rect.width(), 14)
        painter.drawText(centro, Qt.AlignmentFlag.AlignCenter, f"{preco[0]}{preco[1]}")
        painter.setFont(tokens.fonte_rotulo(6))
        painter.drawText(
            QRect(rect.left(), centro.bottom(), rect.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            "SEM\nBOOK",
        )
    else:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM\nBOOK")
