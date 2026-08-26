"""Regiao IDENTIDADE / VIES (x 0,42-0,62 · y 0,62-1,00).

Esqueleto extraido do bloco de marca de
``PainelNexoMercadoASG._desenhar_nucleo_nexo``. Ocupa o pe da coluna central,
sangrando ate a borda inferior do quadro.

Duas responsabilidades convivem aqui e a parte 10 e quem as separa:

1. o **bloco de identidade** do produto — geometria autoral do NEXO/FluxoPro,
   nenhum logotipo, rosto, marca ou asset de terceiro e reproduzido;
2. o **resolvedor de paleta por vies** que fara o quadro inteiro comutar
   coerentemente entre leitura de alta e de baixa. ``cor_vies`` abaixo e o
   ponto de entrada previsto para isso; hoje ele apenas repassa a resolucao ja
   existente, sem inventar regra nova.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

RAIO_MIN = 20
RAIO_MAX = 48


def cor_vies(estado: EstadoNexo) -> QColor:
    """Cor dominante do quadro, derivada da direcao ja publicada no snapshot.

    Ponto unico de resolucao para a parte 10 propagar o vies as demais
    regioes. Nao infere direcao: le a que o snapshot trouxe.

    Resolve pela ``estado.paleta`` (o mesmo ``tokens.Paleta`` que todo painel
    correto do produto consulta), e nao pelo eixo neon verde/rosa da
    superficie NEXO (``tema_asg.NEXO_VERDE``/``NEXO_ROSA``, reservado para
    ESTADO do sistema — ao vivo, atrasado, erro — nunca para a leitura de
    direcao). Duas razoes:

    1. ``tokens.py`` §2 fixa UM eixo direcional para o produto inteiro —
       azul compra / vermelho venda — porque sobrevive a deuteranopia e
       protanopia; o verde/rosa neon e uma segunda paleta competindo pelo
       mesmo papel, e e por isso que verde e vermelho apareciam lado a lado
       sem hierarquia clara entre "direcao" e "estado".
    2. ``estado.paleta`` e quem sabe se o quadro esta em ``--sem-cor``
       (``tokens.PALETA_SEM_COR`` colapsa compra/venda/neutro no mesmo
       ``QColor``). O eixo neon fixo nunca colapsava — o vies continuava
       verde ou rosa mesmo com o eixo direcional desligado no resto do
       quadro.

    ``AGUARDAR`` fica fora do eixo (e leitura de ESTADO — "sem decisao ainda"
    — nao de lado), entao mantem ``tokens.ALERT`` mesmo sem cor, no mesmo
    criterio que ``paineis.asg._cor_direcao`` ja usa para os demais paineis.
    """

    direcao = estado.snapshot.decisao.direcao
    paleta = estado.paleta
    if direcao is _asg.DirecaoASG.COMPRA:
        return paleta.compra
    if direcao is _asg.DirecaoASG.VENDA:
        return paleta.venda
    if direcao is _asg.DirecaoASG.AGUARDAR:
        return tokens.ALERT
    return paleta.neutro


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """Desenha o disco/anel de marca e o rotulo NEXO no rodape da coluna.

    Round 2 (coerencia-vies-e-identidade): o disco/anel deixou de usar
    ``tema_asg.NEXO_CIANO`` e passou a usar ``NEXO_IDENTIDADE_ANEL``/
    ``NEXO_IDENTIDADE_NUCLEO`` (cromo neutro). Motivo: o mesmo ciano ja e
    "ULT/preco" e "ticker" em outras regioes do quadro (``niveis.py``,
    ``candles.py``) — um disco de marca ciano seria um quarto papel para o
    mesmo hue. A UNICA cor com significado de direcao neste bloco continua
    sendo o triangulo, resolvido por ``cor_vies`` (eixo ``tokens.BUY``/
    ``tokens.SELL``, o mesmo que colapsa em ``--sem-cor``); o disco/anel e
    puramente decorativo e por isso e neutro.

    Fora de escopo desta parte (arquivos que este builder nao possui):
    ``fluxopro/ui/paineis/nexo/nucleo.py`` linha ``("REGIME", ...,
    tema_asg.NEXO_CIANO)`` pinta o VALOR do regime (COMPRADOR/VENDEDOR) — uma
    leitura direcional — sempre em ciano fixo, independente da direcao. Isso
    faz o mesmo ciano significar tambem "regime vendedor", que e o defeito
    relatado pelo critico desta rodada. A correcao (amarrar essa celula ao
    mesmo token direcional do gauge/rotulo VENDA) precisa ser feita em
    ``nucleo.py``, que este builder nao possui — reportado como pendente.

    Round 3 (coerencia-vies-e-identidade), mesmo motivo, escopo mais largo:
    o critico apontou verde carregando dois papeis no quadro inteiro — leitura
    de alta E cromo estrutural (moldura, anel, coluna, eixo) — o que e
    exatamente a razao pela qual o disco/anel acima ja e neutro desde a
    rodada 2. O contrato foi reforcado em ``tema_asg.py`` (ver o bloco de
    comentario acima de ``NEXO_VERDE``), mas repintar os consumidores que
    ainda usam ``NEXO_VERDE``/``NEXO_ROSA``/cinza fixo como cromo —
    ``nucleo.py`` (aneis 2184/703), ``ladder.py`` (moldura dos chips),
    ``niveis.py`` (coluna de preco a esquerda), ``grafico.py``/``cockpit.py``
    (moldura de painel e eixo) — e trocar o chip ALERTA / faixa ALGORITHMIC
    STANDBY de ``banner.py`` para ``tokens.ALERT`` (ambar de estado, nao
    cinza metalico) exige editar arquivos que este builder nao possui.
    Reportado como pendente, nao tentado por adivinhacao aqui.
    """
    if rect.width() < 70 or rect.height() < 70:
        return
    cor = cor_vies(estado)
    cx = rect.center().x()
    cy = rect.top() + max(38, (rect.height() - 34) // 2)
    raio = max(RAIO_MIN, min(RAIO_MAX, rect.width() // 3))

    painter.setPen(QPen(tema_asg.NEXO_IDENTIDADE_ANEL, 1))
    painter.drawEllipse(QPoint(cx, cy), raio + 12, raio + 12)
    gradiente = QLinearGradient(cx - raio, cy - raio, cx + raio, cy + raio)
    gradiente.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
    gradiente.setColorAt(1.0, tema_asg.NEXO_IDENTIDADE_NUCLEO)
    painter.setBrush(gradiente)
    painter.drawEllipse(QPoint(cx, cy - 5), raio, raio + 8)
    painter.setBrush(cor)
    painter.drawPolygon(QPolygon([QPoint(cx - raio + 6, cy + raio),
                                  QPoint(cx, cy + raio // 3),
                                  QPoint(cx + raio - 6, cy + raio)]))
    painter.setBrush(tema_asg.NEXO_FUNDO)
    painter.drawEllipse(QPoint(cx - raio // 3, cy - 6), 3, 3)
    painter.drawEllipse(QPoint(cx + raio // 3, cy - 6), 3, 3)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # O triangulo acima carrega o vies SO em cor. Por contrato (nenhuma
    # leitura pode depender so do canal de cor) o rotulo abaixo repete a
    # mesma leitura em texto+glifo (``▲ COMPRA``/``▼ VENDA``/...) — a forma
    # do glifo muda por direcao, entao a leitura sobrevive tanto a
    # ``--sem-cor`` quanto a uma impressao em escala de cinza.
    rotulo_vies = _asg.rotulo_direcao(estado.snapshot.decisao.direcao)
    altura_rotulo = 12 if rect.height() >= 96 else 0
    if altura_rotulo:
        painter.setPen(cor)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(QRect(rect.left(), rect.bottom() - 46, rect.width(),
                                altura_rotulo),
                         Qt.AlignmentFlag.AlignCenter, rotulo_vies)

    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.setFont(tokens.fonte_numero(max(13, min(24, rect.width() // 9)),
                                        QFont.Weight.Bold))
    painter.drawText(QRect(rect.left(), rect.bottom() - 30, rect.width(), 18),
                     Qt.AlignmentFlag.AlignCenter, "NEXO")
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left(), rect.bottom() - 13, rect.width(), 13),
                     Qt.AlignmentFlag.AlignCenter, "FLOW INTELLIGENCE · PROXY PROPRIO")
