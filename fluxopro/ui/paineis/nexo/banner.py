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
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon

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


LIMIAR_RISCO_VOLATILIDADE_ALERTA = 0.7
"""Mesmo IMPRECISO documentado em `asg.py::_risco_volatilidade` — o limiar
de exibicao e outro numero sem fonte, so o corte visual escolhido aqui."""


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return

    # Alerta de exaustao/volatilidade tem prioridade sobre a leitura normal
    # de estado — nunca os dois ao mesmo tempo. Regra de disciplina: fluxo
    # extremo e sustentado (>= 85% de dominancia macro) e o pior preco para
    # ir CONTRA o movimento (mesmo principio do 4R — evitar operar contra a
    # tendencia sem esperar enfraquecer/pullback). Volatilidade alta e um
    # aviso a parte, sem lado — so "cuidado", nunca uma leitura direcional.
    if estado.alerta_exaustao is not None:
        _desenhar_alerta_exaustao(painter, rect, estado.alerta_exaustao)
        return
    # Alerta de SUPORTE/RESISTENCIA (31/08/2026) — vem antes do aviso de
    # volatilidade porque tem LADO e regiao de preco: e leitura acionavel de
    # onde o mercado esta sendo defendido, enquanto volatilidade e so
    # "cuidado" sem lado.
    alerta_sr = alerta_suporte_resistencia(estado)
    if alerta_sr is not None:
        titulo_sr, subtitulo_sr, cor_sr, para_cima_sr = alerta_sr
        _desenhar_placa_alerta(painter, rect, cor_sr, "ALERTA", titulo_sr,
                               subtitulo_sr, seta_para_cima=para_cima_sr)
        return
    if estado.risco_volatilidade >= LIMIAR_RISCO_VOLATILIDADE_ALERTA:
        _desenhar_alerta_volatilidade(painter, rect, estado.risco_volatilidade)
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



def _desenhar_seta_sniper(painter: QPainter, cx: int, cy: int, raio: int, cor,
                          para_cima: bool) -> None:
    """Triangulo cheio do sinal do sniper — forma E cor, nunca so cor (a
    tela tem de sobreviver ao modo sem cor, como o resto do NEXO)."""

    sentido = 1 if para_cima else -1
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(cor))
    painter.drawPolygon(QPolygon([
        QPoint(cx, cy - sentido * raio),
        QPoint(cx + round(raio * 0.85), cy + round(sentido * raio * 0.65)),
        QPoint(cx - round(raio * 0.85), cy + round(sentido * raio * 0.65)),
    ]))
    painter.restore()


def _desenhar_placa_alerta(
    painter: QPainter, rect: QRect, cor, rotulo_chip: str, titulo: str, subtitulo: str,
    seta_para_cima: bool | None = None,
) -> None:
    """Geometria compartilhada dos dois alertas: cunha diagonal + chip
    "ALERTA"/rotulo a esquerda, titulo grande + subtitulo a direita — mesmo
    vocabulario de cunha/corte diagonal do banner normal, cores do proprio
    tema (nunca um vermelho/verde literal novo).
    """

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # `cor` pode ser um QColor ESTATICO compartilhado (`tema_asg.NEXO_VERDE`/
    # `NEXO_ROSA`/`tokens.ALERT` sao alocados uma vez no import — ver o
    # comentario grande em tema_asg.py acima de NEXO_VERDE). Mutar `cor`
    # diretamente com `setAlpha` corromperia essa instancia global para todo
    # consumidor futuro; `QColor(cor)` copia antes de mutar.
    faixa = QColor(cor)
    faixa.setAlpha(60)
    placa = cor.darker(FATOR_PLACA_ESCURA)

    largura_chip = min(90, max(60, rect.width() // 6))
    caixa_chip = QRect(rect.left() + PAD_H, rect.top(), largura_chip, rect.height())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(placa))
    painter.drawRect(caixa_chip)
    painter.setPen(QPen(cor, 2))
    painter.drawLine(caixa_chip.right(), caixa_chip.top(), caixa_chip.right(), caixa_chip.bottom())
    painter.setFont(tokens.fonte_ui(9, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(caixa_chip, Qt.AlignmentFlag.AlignCenter, rotulo_chip)

    # Setinha do "sniper" (aula `TPk39osWiKY`): para BAIXO no alerta de
    # resistencia, para CIMA no de suporte. Fica logo apos o chip, do lado
    # do titulo — e o mesmo lugar em que a referencia do operador a poe.
    # `None` = alerta sem lado (volatilidade), e ai nao ha seta.
    if seta_para_cima is not None:
        _desenhar_seta_sniper(painter, caixa_chip.right() + PAD_H + 8,
                              rect.center().y(), max(5, rect.height() // 6), cor,
                              seta_para_cima)

    caixa_texto = QRect(caixa_chip.right() + PAD_H * 2, rect.top(),
                        rect.width() - largura_chip - PAD_H * 3, rect.height())
    painter.setBrush(QBrush(faixa))
    painter.setPen(QPen(cor, 1))
    painter.drawRect(caixa_texto)
    painter.restore()

    # O titulo e uma FRASE (nao uma palavra curta como o banner normal
    # COMPRA/VENDA/AGUARDAR), entao a fonte tem que caber na LARGURA, nao so
    # numa fracao fixa da altura — um tamanho calibrado so por altura
    # (como o banner normal faz) estourava a largura da placa e as letras
    # ficavam empilhadas/ilegiveis (achado corrigindo esta mesma parte).
    largura_disponivel = caixa_texto.width() - 2 * PAD_H
    altura_max_titulo = round(caixa_texto.height() * 0.6)
    tamanho_titulo = max(10, min(altura_max_titulo, 22))
    fonte_titulo = tokens.fonte_numero(tamanho_titulo, QFont.Weight.Bold)
    painter.setFont(fonte_titulo)
    while tamanho_titulo > 8 and painter.fontMetrics().horizontalAdvance(titulo) > largura_disponivel:
        tamanho_titulo -= 1
        fonte_titulo = tokens.fonte_numero(tamanho_titulo, QFont.Weight.Bold)
        painter.setFont(fonte_titulo)
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(QRect(caixa_texto.left() + PAD_H, caixa_texto.top(),
                          largura_disponivel, round(caixa_texto.height() * 0.65)),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(cor)
    painter.drawText(QRect(caixa_texto.left() + PAD_H, caixa_texto.bottom() - ALTURA_LINHA_RODAPE,
                          caixa_texto.width() - 2 * PAD_H, ALTURA_LINHA_RODAPE),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, subtitulo)


INTENSIDADE_MIN_ALERTA_SR = 3
"""Abaixo de 3 raios (forca da zona < 40%) o alerta de suporte/resistencia
NAO toma a faixa.

Regra da aula (`pesquisa/legendas/TPk39osWiKY.txt`): "a gente so vai dar
enfase para esse sinal quando ele aparecer no NIVEL MAXIMO". Um alerta que
acende em qualquer zona fraca deixa de ser alerta — e o Sergio e explicito
que a sinalizacao NAO e constante ("existem epocas que nem aparece")."""


def alerta_suporte_resistencia(estado: EstadoNexo):
    """`(titulo, subtitulo, cor, para_cima)` do alerta de S/R, ou `None`.

    O alerta e de UM LADO SO — suporte OU resistencia — porque e isso que a
    fonte descreve: "alerta de resistencia maxima OU alerta de suporte
    maximo. O objetivo e o mesmo". Nunca os dois.

    Os textos de conduta vem direto da aula, e sao CONSULTIVOS (o que
    EVITAR, nunca o que fazer):
      - resistencia: "voce nunca vai fazer a compra em cima dessa
        sinalizacao";
      - suporte: "enquanto estiver o suporte detectado nesses niveis, voce
        vai evitar fazer a entrada de venda".
    """

    from fluxopro.ui.paineis.nexo import suporte_resistencia as _sr_ui

    snapshot = getattr(estado, "sr_snapshot", None)
    zona = _sr_ui.zona_de_referencia(snapshot)
    if zona is None:
        return None
    intensidade = _sr_ui.intensidade_da_zona(getattr(zona, "score", None))
    if intensidade < INTENSIDADE_MIN_ALERTA_SR:
        return None

    lado = getattr(zona, "lado", None)
    if lado is None or getattr(lado, "name", "") == "NEUTRO":
        lado = _sr_ui.lado_geometrico(zona.preco,
                                      getattr(snapshot, "ultimo_preco", None))
    e_suporte = getattr(lado, "name", "") == "SUPORTE"
    if not e_suporte and getattr(lado, "name", "") != "RESISTENCIA":
        return None

    maximo = intensidade >= _sr_ui.INTENSIDADE_MAXIMA
    tick = getattr(snapshot, "tick_size", 1.0) or 1.0
    preco = _sr_ui.texto_preco_regiao(zona.preco, tick)
    if e_suporte:
        cor = _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA)
        titulo = "ULTRA SUPORTE MAXIMO" if maximo else "SUPORTE DETECTADO"
        subtitulo = f"EVITE VENDER ENQUANTO SINALIZADO · REGIAO {preco}"
    else:
        cor = _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA)
        titulo = "ULTRA RESISTENCIA MAXIMA" if maximo else "RESISTENCIA DETECTADA"
        subtitulo = f"EVITE COMPRAR ENQUANTO SINALIZADO · REGIAO {preco}"
    return titulo, subtitulo, cor, e_suporte


def _desenhar_alerta_exaustao(painter: QPainter, rect: QRect, alerta: tuple[str, float]) -> None:
    """Fluxo extremo e sustentado num sentido — nomeia o ESTADO medido.

    Mesma regra de disciplina do 4R (`fluxopro/analytics/renko.py`), e a
    mesma leitura: um HORIZONTE saturado num lado e o pior lugar para ir
    contra ele. A ressalva vive em COMO_LER_OS_INDICADORES.md, secao 9,
    onde cabe a prosa.

    Ate 28/08 o titulo era "CUIDADO COM COMPRAS AGORA" / "CUIDADO COM
    VENDAS AGORA" — a maior frase desta metade da tela, imperativa e com
    "AGORA" dentro, ou seja: momento de operar. O rodape da mesma coluna
    carimba "NAO E ORDEM · NAO E RECOMENDACAO" e o documento do operador
    promete o mesmo. O nome do estado diz o que foi medido; o subtitulo ja
    carrega SUPORTE/RESISTENCIA MAXIMA e o numero do HORIZONTE.
    """

    direcao_extrema, magnitude = alerta
    if direcao_extrema == "COMPRA":
        cor = _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA)
        titulo = "FLUXO COMPRADOR EXTREMO"
        subtitulo = f"SUPORTE MAXIMO · HORIZONTE {magnitude * 100:+.0f}%"
    else:
        cor = _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA)
        titulo = "FLUXO VENDEDOR EXTREMO"
        subtitulo = f"RESISTENCIA MAXIMA · HORIZONTE {magnitude * 100:+.0f}%"
    _desenhar_placa_alerta(painter, rect, cor, "ALERTA", titulo, subtitulo)


def _desenhar_alerta_volatilidade(painter: QPainter, rect: QRect, risco: float) -> None:
    """Risco de volatilidade alto — aviso sem lado (nao e leitura direcional,
    ver `asg.py::_risco_volatilidade` para o rotulo IMPRECISO/proxy)."""

    _desenhar_placa_alerta(
        painter, rect, tokens.ALERT, "ALERTA",
        "RISCO DE VOLATILIDADE",
        f"DESVIO {risco * 100:.0f}% DA JANELA RECENTE · PROXY",
    )
