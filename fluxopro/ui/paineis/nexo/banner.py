"""Regiao BANNER DE ESTADO (x 0,00-0,40 · y 0,65-0,78).

Esqueleto extraido do bloco de decisao consultiva de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. Ocupa a faixa inteira, da
borda esquerda ate 0,40 do quadro, sem cartao ao redor: a geometria abaixo e
uma cunha e uma faixa com o canto cortado na diagonal, nunca um retangulo
fechado — isso e o que distingue "banner de estado" de "texto dentro de
cartao".

A palavra de estado e **leitura**, nunca comando: AGUARDAR/COMPRA/VENDA/NEUTRA
aqui descrevem o que foi observado (`asg.DirecaoASG`, valores substantivos,
nenhum verbo de execucao) e a funcao so pinta pixels num ``QPainter`` recebido
— nao ha widget, evento de clique ou callback aqui, entao nao existe
superficie clicavel que execute qualquer coisa. O rodape sempre fecha com
"LEITURA CONSULTIVA" para reforcar isso mesmo quando a confianca for alta.

Tres faixas horizontais dentro do `rect`:
  1. topo — linha de orientacao (motivo/contexto), pequena e apagada, NUNCA
     do mesmo peso que a palavra de estado (senao ela compete pela atencao);
  2. meio — cunha diagonal (seta solida) + faixa translucida com o canto
     direito cortado, com a palavra de estado grande e em negrito por cima;
  3. rodape — confianca + disclaimer, em ciano.

Cores e fontes vem inteiramente de ``tema_asg``/``tokens`` (nada de
``QColor``/``QFont`` literal aqui); as unicas constantes locais sao medidas de
layout (padding, largura da cunha, fracao de tamanho da palavra de estado) e
um fator numerico de escurecimento (``FATOR_PLACA_ESCURA``) aplicado via
``QColor.darker()`` sobre a cor do estado ja existente — nunca um ``QColor``
novo — no mesmo estilo que o resto do arquivo ja usava para ``+4``/``14``. A
placa do meio e a propria cor do estado escurecida (nao mais um cinza fixo) e
a palavra de estado e pintada em ``tema_asg.NEXO_TEXTO`` (branco quase-puro
ja existente no tema), medido para >= 7:1 de contraste nas 4 direcoes — ver
comentario junto de ``FATOR_PLACA_ESCURA`` abaixo.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

LIMITE_MOTIVO = 96

# Medidas de layout — nao sao cor nem fonte, entao ficam como constantes
# locais de modulo, no mesmo espirito de LIMITE_MOTIVO acima.
PAD_H = 4
ALTURA_LINHA_TOPO = 14
ALTURA_LINHA_RODAPE = 14
LARGURA_CUNHA = 16
CORTE_DIAGONAL = 12

# Tamanho-alvo da palavra de estado, como fracao da ALTURA DO RECT (nao da
# tela): a regiao do banner ocupa 0,13 da altura do quadro (y 0,65-0,78 do
# hint), e a meta de peso visual e cap-height ~5% do quadro inteiro — logo
# 0,05 / 0,13 ~= 0,385 da altura do rect e o piso; arredondado para cima
# (0,44) para cobrir a razao cap-height/tamanho-de-fonte tipica de uma fonte
# bold tabular (~0,87), que fica abaixo do tamanho de fonte em si. Antes
# disto o teto era um literal fixo (34px) que nao acompanhava a escala do
# rect e rendia cap-height ~3,3% do quadro — baixo demais para a palavra que
# carrega o estado.
TAMANHO_ALVO_FRACAO_RECT = 0.44

# A cor solida (`_cor_nexo_direcao`) ja existe em `asg.py`; a versao
# translucida ("faixa") para o fundo da banda usa APENAS constantes ja
# pre-alocadas em `tema_asg` — nenhum QColor novo e construido aqui.
_FAIXA_POR_DIRECAO = {
    _asg.DirecaoASG.COMPRA: tema_asg.NEXO_VERDE_FAIXA,
    _asg.DirecaoASG.VENDA: tema_asg.NEXO_ROSA_FAIXA,
    _asg.DirecaoASG.AGUARDAR: tema_asg.FUNDO_ALERTA,
    _asg.DirecaoASG.NEUTRA: tema_asg.NEXO_CIANO_FAIXA,
}

# Placa da faixa: fundo SOLIDO, mas nao mais um cinza neutro fixo — a critica
# da rodada anterior mediu a palavra de estado (cinza-escura, RGB (82,82,82),
# zero croma) contra uma placa cinza-clara neutra e achou contraste ~1,9-2,0:1,
# a coisa que o operador precisa achar mais rapido virando a de MENOR
# contraste da propria regiao. A placa cinza nao carregava a cor do estado
# nenhuma; so o texto (fraco) tentava.
#
# Fix: a placa agora e a PROPRIA cor do estado (`cor`, ja saturada, vinda de
# `_cor_nexo_direcao` — mesma fonte de sempre), so que escurecida com o
# metodo nativo do Qt (`QColor.darker`, nao um QColor literal novo) para
# sobrar espaco de luminancia por baixo de um texto claro. FATOR_PLACA_ESCURA
# abaixo e o unico numero novo — um fator de escurecimento, nao uma cor — e
# foi calibrado (ver calculo de contraste WCAG na rodada de fix) para o PIOR
# caso entre as 4 direcoes (COMPRA/verde, que perde luminancia mais devagar
# ao escurecer) ainda fechar >= 7:1 depois de somado o tingimento translucido
# da faixa por cima. A palavra de estado deixa de ser pintada na cor do
# estado (que effectively ficaria placa-sobre-placa, baixo contraste) e passa
# a ser `tema_asg.NEXO_TEXTO` — o branco quase-puro que o proprio tema ja usa
# como texto primario — um preenchimento solido e claro, nao uma nova cor.
# Resultado: a placa e identificavel por cor a distancia (verde/rosa/
# amarelo/ciano, nao mais um cinza que apaga a diferenca entre estados), e a
# palavra continua a coisa de MAIOR contraste da faixa, nao a de menor.
FATOR_PLACA_ESCURA = 480


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return
    decisao = estado.snapshot.decisao
    cor = _asg._cor_nexo_direcao(decisao.direcao)
    faixa = _FAIXA_POR_DIRECAO.get(decisao.direcao, tema_asg.NEXO_CIANO_FAIXA)
    # Placa solida derivada da propria cor do estado (nao um cinza fixo) —
    # ver nota longa acima de FATOR_PLACA_ESCURA.
    placa_estado = cor.darker(FATOR_PLACA_ESCURA)

    # --- 1. linha de orientacao (topo): contexto da leitura, pequena e apagada
    # de proposito para nao competir com a palavra de estado no meio ---
    painter.setFont(tokens.fonte_ui(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + PAD_H, rect.top(),
                           rect.width() - 2 * PAD_H, ALTURA_LINHA_TOPO),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     decisao.motivo[:LIMITE_MOTIVO].upper())

    # --- 2. cunha diagonal + faixa cortada + palavra de estado (meio) ---
    topo_meio = rect.top() + ALTURA_LINHA_TOPO
    base_meio = rect.bottom() - ALTURA_LINHA_RODAPE
    altura_meio = base_meio - topo_meio

    xa = rect.left() + PAD_H
    xb_cunha = xa + LARGURA_CUNHA
    xa_faixa = xb_cunha + CORTE_DIAGONAL + PAD_H
    xb_faixa = rect.right() - PAD_H

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Cunha: seta solida apontando a leitura — o corte diagonal que faltava
    # no texto plano. Geometria, nao decoracao: mesma funcao espacial do
    # aviso na referencia, com traco e cor proprios do FluxoPro/NEXO.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(cor))
    painter.drawPolygon(QPolygon([
        QPoint(xa, topo_meio),
        QPoint(xb_cunha, topo_meio),
        QPoint(xb_cunha + CORTE_DIAGONAL, (topo_meio + base_meio) // 2),
        QPoint(xb_cunha, base_meio),
        QPoint(xa, base_meio),
    ]))

    # Faixa: banda com o canto direito cortado na diagonal — nunca um
    # retangulo fechado, para continuar lendo como banner e nao como cartao.
    if xb_faixa > xa_faixa:
        pontos_faixa = QPolygon([
            QPoint(xa_faixa, topo_meio),
            QPoint(xb_faixa, topo_meio),
            QPoint(xb_faixa - CORTE_DIAGONAL, base_meio),
            QPoint(xa_faixa, base_meio),
        ])
        # 1) placa solida escura primeiro (agora tingida na cor do proprio
        # estado, ver FATOR_PLACA_ESCURA) — a palavra de estado sempre le
        # contra um fundo escuro, nao importa o que exista atras do rect.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(placa_estado))
        painter.drawPolygon(pontos_faixa)
        # 2) o tingimento translucido do estado por cima, so como reforco de
        # contexto — o alpha baixo garante que a placa continue escura.
        painter.setPen(QPen(cor, 1))
        painter.setBrush(QBrush(faixa))
        painter.drawPolygon(pontos_faixa)
        texto_x = xa_faixa + PAD_H + 2
    else:
        texto_x = xb_cunha + CORTE_DIAGONAL + PAD_H
    painter.restore()

    # Palavra de estado: leitura, nunca comando. `DirecaoASG` so tem
    # substantivos (COMPRA/VENDA/NEUTRA/AGUARDAR), nenhum verbo de execucao.
    # Pintada em `tema_asg.NEXO_TEXTO` (branco quase-puro, ja existente no
    # tema) em vez da propria `cor` do estado — a cor do estado ja foi para a
    # placa (`placa_estado`) que fica por baixo; repeti-la no texto seria
    # cor-sobre-cor tingida, de novo baixo contraste. Preenchimento solido e
    # claro por cima de placa escura e saturada e o que fecha >= 7:1 nas
    # 4 direcoes (ver FATOR_PLACA_ESCURA) sem depender do matiz de cada uma.
    titulo = decisao.direcao.value
    tamanho_alvo = round(rect.height() * TAMANHO_ALVO_FRACAO_RECT)
    tamanho = max(14, min(tamanho_alvo, altura_meio - 6))
    painter.setFont(tokens.fonte_numero(tamanho, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(QRect(texto_x, topo_meio, max(18, xb_faixa - texto_x), altura_meio),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)

    # --- 3. confianca + disclaimer (rodape) ---
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_CIANO)
    painter.drawText(QRect(rect.left() + PAD_H, rect.bottom() - ALTURA_LINHA_RODAPE,
                           rect.width() - 2 * PAD_H, ALTURA_LINHA_RODAPE),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     f"CONFIANCA · {decisao.confianca.value}  ·  LEITURA CONSULTIVA")
