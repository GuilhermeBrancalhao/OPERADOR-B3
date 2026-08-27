"""Regiao VISOR HUD (x 0,40-0,63 · y 0,02-0,42).

Visor central da superficie NEXO: moldura assimetrica tipo posto de leitura
(bisel largo no topo, quase reto na base), carimbo de tempo do quadro, glifo
direcional em escala cheia e os tres cartoes curtos de regime/confianca/
evidencias.

O visor **nao e um botao**: nao tem estado de hover, pressed nem callback —
apenas ``desenhar(painter, rect, estado)`` chamado uma vez por quadro com o
``EstadoNexo`` imutavel. O glifo central tem tres leituras distintas, nunca
uma so "seta ou nada":

* ``COMPRA``/``VENDA`` — seta solida cheia, cor do eixo neon da direcao;
* ``AGUARDAR`` — losango vazado (duas cunhas se tocando no meio), a leitura
  "aguardando confirmacao" antes de qualquer direcao ser assumida;
* ``NEUTRA`` — laco de equilibrio (dois arcos com ponta), a leitura "sem
  vies, mercado em equilibrio".

Nenhum dos tres estados e uma seta-padrao disfarcada: cada um tem silhueta
propria, entao o visor nunca fica com o desenho de "COMPRA" quando na
verdade nao ha sinal algum.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygon

from fluxopro.asg.sinal_ultra import DirecaoUltra
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

RAIO_MIN = 30
RAIO_MAX = 96

# O glifo de AGUARDAR/NEUTRA (losango/laco) e desenhado com um semi-eixo por
# direcao (rx horizontal, ry vertical) em vez de um raio unico: o bisel do
# visor e bem mais largo que alto (assimetria de proposito, ver
# ``_silhueta_visor``), entao um raio uniforme ou fica curto na largura ou
# estoura a altura. As fracoes abaixo sao aplicadas cada uma sobre a
# dimensao correspondente do miolo do bisel (largura util / altura util, ja
# descontado o carimbo de tempo), mantendo o glifo entre 55% e 75% de cada
# eixo — a faixa que evita tanto o glifo perdido num bisel vazio quanto um
# glifo que atropela a moldura. A seta de COMPRA/VENDA NAO usa estas duas
# fracoes — ver ``FRACAO_SETA_LARGURA``/``_dimensoes_seta`` abaixo, onde a
# altura decorre da largura por um angulo de apice fixo em vez de um
# segundo raio livre.
FRACAO_GLIFO_LARGURA = 0.65
FRACAO_GLIFO_ALTURA = 0.75

# Seta de COMPRA/VENDA: largura como fracao da largura util do bisel,
# independente de ``FRACAO_GLIFO_LARGURA``/``_ALTURA`` acima. A seta e um
# triangulo de angulo de apice fixo (``ANGULO_APICE_SETA_GRAUS``) e nao um
# glifo com dois semi-eixos livres como o losango/equilibrio — a altura
# decorre da largura pelo angulo, nunca e calibrada a parte. Com 60% a seta
# ocupa a mesma faixa 50%-60% da largura util cobrada pelo bisel de
# referencia, sobrando ~20% de vao de cada lado antes do chanfro; um valor
# menor (a versao anterior efetivamente caia bem abaixo disso) deixa a seta
# como uma marca perdida no meio de um campo escuro vazio.
FRACAO_SETA_LARGURA = 0.60
ANGULO_APICE_SETA_GRAUS = 51.0

ALTURA_CARTAO = 28
VAO_CARTAO = 3

# Faixa reservada, no topo da moldura, para o carimbo de tempo do quadro.
ALTURA_CARIMBO = 13

# Espessuras de traco: uma para o contorno fino (grade/hairline), outra para
# o glifo e os brackets de canto, que precisam ler como instrumento e nao
# como fio de tabela.
TRACO_FINO = 1
TRACO_GLIFO = 2

# Bisel do topo e da base da moldura, como fracao do lado menor: o topo e
# bem mais fundo que a base de proposito — e essa assimetria (posto de
# leitura, nao octogono regular) que distingue o visor de um botao.
BISEL_TOPO_DIV = 3
BISEL_BASE_DIV = 8

# Comprimento dos brackets de canto (mira tipo visor de camera), como fracao
# do lado menor da moldura.
BRACO_CANTO_DIV = 8

# Recuo do contorno interno (linha fina duplicada), reforcando profundidade
# de vidro em vez de preenchimento chapado de botao.
RECUO_CONTORNO = 4

# Fundo do glow por direcao: apenas tokens ja pre-alocados em ``tema_asg``
# (nenhum QColor novo e construido aqui).
_FAIXA_POR_DIRECAO = {
    _asg.DirecaoASG.COMPRA: tema_asg.NEXO_VERDE_FAIXA,
    _asg.DirecaoASG.VENDA: tema_asg.NEXO_ROSA_FAIXA,
    _asg.DirecaoASG.AGUARDAR: tema_asg.FUNDO_ALERTA,
    _asg.DirecaoASG.NEUTRA: tema_asg.NEXO_CIANO_FAIXA,
}

# Selo do Sinal Ultra (fluxopro/asg/sinal_ultra.py — filtro adicional,
# construido do zero por este projeto, ver docstring do modulo). Achado do
# operador sobre o visor antigo: "nunca aparece nada" — antes deste selo o
# visor nao tinha NENHUM estado visual distinto para quando o Ultra confirma
# confluencia; agora um anel pulsante e um rotulo proprio marcam esse
# instante, sem reciclar a cor de COMPRA/VENDA (para nao confundir "decisao
# principal confirmada" com "confluencia Ultra confirmada" — sao leituras
# diferentes, mesmo quando concordam).
PERIODO_PULSO_ULTRA_NS = 1_200_000_000  # 1,2s por ciclo — visivel, nao estroboscopico
ALPHA_PULSO_ULTRA_MIN = 90
ALPHA_PULSO_ULTRA_MAX = 235


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 90 or rect.height() < 90:
        return
    decisao = estado.snapshot.decisao
    direcao = decisao.direcao
    cor = _asg._cor_nexo_direcao(direcao)

    moldura = QRect(rect.left(), rect.top(), rect.width(),
                    max(60, rect.height() - ALTURA_CARTAO - 34))

    # AA ja vem ligado do chamador (``PainelNexoMercadoASG.desenhar``); o
    # `painter.save()`/`restore()` que envolve cada regiao cobre qualquer
    # estado que este bloco mude, entao nao ha necessidade de desligar de
    # volta aqui. Reforcar explicitamente so garante o glifo liso mesmo se
    # algum dia este modulo for chamado fora daquele laco.
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _desenhar_moldura(painter, moldura, direcao, cor)
    _desenhar_carimbo_tempo(painter, moldura, estado.snapshot.timestamp_ns)
    _desenhar_glifo(painter, moldura, direcao, cor)

    direcao_ultra = getattr(estado.sinal_ultra, "direcao", None)
    ultra_ativo = direcao_ultra is not None and direcao_ultra is not DirecaoUltra.NENHUMA
    if ultra_ativo:
        _desenhar_selo_ultra(painter, moldura, direcao_ultra, estado.snapshot.timestamp_ns)

    painter.setFont(tokens.fonte_ui(8, QFont.Weight.DemiBold))
    painter.setPen(cor)
    painter.drawText(QRect(rect.left(), moldura.bottom() + 2, rect.width(), 15),
                     Qt.AlignmentFlag.AlignCenter, decisao.titulo.upper())
    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_AMARELO if ultra_ativo else tema_asg.NEXO_MUTED)
    rotulo_consultivo = (
        f"⚡ ULTRA {direcao_ultra.value.upper()} · FILTRO ADICIONAL"
        if ultra_ativo else "SINAL CONSULTIVO"
    )
    painter.drawText(QRect(rect.left(), moldura.bottom() + 16, rect.width(), 14),
                     Qt.AlignmentFlag.AlignCenter, rotulo_consultivo)

    regime = next((linha for linha in estado.snapshot.matriz.linhas
                   if linha.componente == "REGIME"), None)
    cartoes = (
        ("REGIME", "—" if regime is None else regime.valor, tema_asg.NEXO_CIANO),
        ("CONFIANCA", decisao.confianca.value.replace("CONF ", ""), cor),
        ("EVID.", str(estado.snapshot.evidencias.retidos), tema_asg.NEXO_AMARELO),
    )
    largura = max(32, (rect.width() + VAO_CARTAO) // len(cartoes) - VAO_CARTAO)
    y = rect.bottom() - ALTURA_CARTAO
    for indice, (nome, valor, cor_cartao) in enumerate(cartoes):
        caixa = QRect(rect.left() + indice * (largura + VAO_CARTAO), y,
                      largura, ALTURA_CARTAO)
        painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(3, 1, -3, -14), Qt.AlignmentFlag.AlignCenter, nome)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
        painter.setPen(cor_cartao)
        painter.drawText(caixa.adjusted(3, 12, -3, -1), Qt.AlignmentFlag.AlignCenter,
                         valor[:12])


def _desenhar_moldura(painter: QPainter, moldura: QRect,
                       direcao: "_asg.DirecaoASG", cor) -> None:
    """Corpo do visor: silhueta assimetrica + contorno duplo + brackets.

    Tres camadas, nenhuma delas um retangulo/octogono chapado com uma unica
    borda (a assinatura visual de "botao"):

    1. preenchimento escuro com o traco externo em ``faixa`` (translucido,
       largo) fazendo as vezes de glow sem inventar cor nova;
    2. um segundo contorno, fino e recuado, em ``NEXO_GRADE`` — a leitura de
       "vidro com profundidade" em vez de fundo liso com uma borda so;
    3. brackets de canto tipo mira de visor, na cor da direcao — o detalhe
       que marca "instrumento" e nunca aparece num botao convencional.
    """

    faixa = _FAIXA_POR_DIRECAO.get(direcao, tema_asg.NEXO_CIANO_FAIXA)

    painter.setPen(QPen(faixa, TRACO_GLIFO + 1))
    painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
    painter.drawPolygon(_silhueta_visor(moldura))

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(tema_asg.NEXO_GRADE, TRACO_FINO))
    interna = moldura.adjusted(RECUO_CONTORNO, RECUO_CONTORNO,
                               -RECUO_CONTORNO, -RECUO_CONTORNO)
    painter.drawPolygon(_silhueta_visor(interna))

    _brackets_canto(painter, moldura, cor)


def _silhueta_visor(rect: QRect) -> QPolygon:
    """Moldura em bisel assimetrico: topo fundo, base quase reta.

    Um octogono regular (mesmo corte nos quatro cantos) le como um botao
    hexagonal generico. Aqui o bisel do topo e proporcionalmente bem mais
    fundo que o da base — silhueta de posto de leitura, nao de tecla.
    """

    lado = min(rect.width(), rect.height())
    bisel_topo = max(10, lado // BISEL_TOPO_DIV)
    bisel_base = max(4, lado // BISEL_BASE_DIV)
    return QPolygon([
        QPoint(rect.left() + bisel_topo, rect.top()),
        QPoint(rect.right() - bisel_topo, rect.top()),
        QPoint(rect.right(), rect.top() + bisel_topo),
        QPoint(rect.right(), rect.bottom() - bisel_base),
        QPoint(rect.right() - bisel_base, rect.bottom()),
        QPoint(rect.left() + bisel_base, rect.bottom()),
        QPoint(rect.left(), rect.bottom() - bisel_base),
        QPoint(rect.left(), rect.top() + bisel_topo),
    ])


def _brackets_canto(painter: QPainter, rect: QRect, cor) -> None:
    """Quatro brackets em L, tipo mira de visor, nos cantos de ``rect``."""

    lado = min(rect.width(), rect.height())
    braco = max(6, lado // BRACO_CANTO_DIV)
    painter.setPen(QPen(cor, TRACO_GLIFO))
    for x, y, dx, dy in (
        (rect.left(), rect.top(), 1, 1),
        (rect.right(), rect.top(), -1, 1),
        (rect.left(), rect.bottom(), 1, -1),
        (rect.right(), rect.bottom(), -1, -1),
    ):
        painter.drawLine(x, y, x + dx * braco, y)
        painter.drawLine(x, y, x, y + dy * braco)


def _desenhar_selo_ultra(painter: QPainter, moldura: QRect,
                          direcao_ultra: DirecaoUltra, timestamp_ns: int) -> None:
    """Anel pulsante em torno do visor quando o Sinal Ultra esta ativo.

    A pulsacao usa `timestamp_ns` (o mesmo relogio do quadro, nunca um
    relogio de UI separado) — o anel respira em fase com o feed, nao com o
    framerate de repintura da janela. Onda cosseno (nunca linear/dente de
    serra) para a transicao de alpha nunca "cortar" abruptamente nos extremos
    do ciclo — o mesmo defeito de mudanca abrupta que motivou suavizar o
    gauge EQUILIBRIO (ver `fluxopro/ui/paineis/asg.py`), aqui evitado de
    saida em vez de corrigido depois.
    """

    fase = (timestamp_ns % PERIODO_PULSO_ULTRA_NS) / PERIODO_PULSO_ULTRA_NS
    onda = (1 - math.cos(2 * math.pi * fase)) / 2.0
    alpha = round(ALPHA_PULSO_ULTRA_MIN + (ALPHA_PULSO_ULTRA_MAX - ALPHA_PULSO_ULTRA_MIN) * onda)

    # Redesenha a MESMA silhueta da moldura (nunca expandida para fora dela —
    # as regioes do NEXO encostam borda a borda sem vao, ver docstring do
    # pacote; expandir o anel para fora sangraria na regiao vizinha), so que
    # por cima, com o traco mais grosso e a cor pulsante — um brilho que
    # "respira" sobre o proprio contorno em vez de um anel novo ao redor.
    cor_anel = QColor(tema_asg.NEXO_AMARELO)
    cor_anel.setAlpha(alpha)
    painter.setPen(QPen(cor_anel, TRACO_GLIFO + 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(_silhueta_visor(moldura.adjusted(1, 1, -1, -1)))


def _desenhar_carimbo_tempo(painter: QPainter, moldura: QRect, timestamp_ns: int) -> None:
    """Carimbo de tempo do quadro, no bisel do topo do visor.

    ``timestamp_ns`` vem do ``WorkspaceASGSnapshot`` (um so por quadro, sob
    lock, pelo relogio unico da janela) — nunca de um relogio proprio do
    visor. Sem isso o visor era uma leitura sem hora, a mesma imagem parada
    servindo para qualquer instante.
    """

    painter.setFont(tokens.fonte_numero(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    caixa = QRect(moldura.left(), moldura.top() + 3, moldura.width(), ALTURA_CARIMBO)
    texto = formato.formatar_hora_ns(timestamp_ns) if timestamp_ns > 0 else "— SEM RELOGIO —"
    painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, texto)


def _desenhar_glifo(painter: QPainter, moldura: QRect,
                     direcao: "_asg.DirecaoASG", cor) -> None:
    """Glifo central, escalado para ocupar o visor (nao um icone perdido nele).

    ``rx``/``ry`` sao semi-eixos independentes — nao um raio unico — porque o
    bisel e bem mais largo que alto. Um raio uniforme calibrado pela altura
    (o eixo mais curto) deixava larguras inteiras de campo escuro vazias dos
    dois lados do glifo; calibrando cada eixo pela sua propria dimensao util
    o glifo ocupa a mesma fracao (55%-75%) tanto da largura quanto da altura
    internas do bisel.
    """

    cx = moldura.center().x()
    disponivel_h = moldura.height() - ALTURA_CARIMBO
    cy = moldura.top() + ALTURA_CARIMBO + disponivel_h // 2

    largura_util = moldura.width() - 2 * RECUO_CONTORNO
    altura_util = disponivel_h - 2 * RECUO_CONTORNO

    if direcao is _asg.DirecaoASG.COMPRA:
        rx, ry = _dimensoes_seta(largura_util, altura_util)
        _glifo_seta(painter, cx, cy, rx, ry, cor, para_cima=True)
    elif direcao is _asg.DirecaoASG.VENDA:
        rx, ry = _dimensoes_seta(largura_util, altura_util)
        _glifo_seta(painter, cx, cy, rx, ry, cor, para_cima=False)
    elif direcao is _asg.DirecaoASG.AGUARDAR:
        rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
        ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
        _glifo_losango(painter, cx, cy, rx, ry, cor)
    else:
        rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
        ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
        _glifo_equilibrio(painter, cx, cy, rx, ry, cor)


def _semi_eixo(dimensao_util: int, fracao: float) -> int:
    """Semi-eixo do glifo num unico eixo: ``fracao`` da dimensao util do bisel.

    ``dimensao_util`` e a largura ou a altura internas do bisel (ja com a
    faixa do carimbo e o recuo do contorno descontados). O resultado ainda
    passa pelo piso/teto absolutos (``RAIO_MIN``/``RAIO_MAX``) para nao
    colapsar em biseis minusculos nem explodir em biseis gigantes.
    """

    return max(RAIO_MIN, min(RAIO_MAX, round(dimensao_util * fracao / 2)))


def _dimensoes_seta(largura_util: int, altura_util: int) -> tuple[int, int]:
    """Semi-eixos (rx, ry) da seta de COMPRA/VENDA, derivados um do outro.

    Ao contrario de ``_semi_eixo`` (usado por AGUARDAR/NEUTRA, onde largura e
    altura sao dois raios calibrados de forma independente), a seta e um
    triangulo isosceles de angulo de apice fixo: a metade da base (``rx``)
    vem direto de ``FRACAO_SETA_LARGURA`` sobre a largura util do bisel, e a
    altura decorre dela por ``ANGULO_APICE_SETA_GRAUS`` — nunca um segundo
    raio calibrado a parte, que deixaria a ponta ora gorda ora fina conforme
    a proporcao do bisel muda. Sem teto absoluto (``RAIO_MAX``) sobre ``rx``:
    um teto em pixels fixos e o que faz a seta encolher, em fracao do bisel,
    justamente nos biseis maiores — o efeito que este ajuste existe para
    eliminar. Se o resultado nao couber na altura util (bisel baixo demais),
    os dois eixos sao escalados pelo mesmo fator, preservando o angulo e a
    proporcao base:altura, em vez de espremer so a altura.
    """

    rx = max(RAIO_MIN, round(largura_util * FRACAO_SETA_LARGURA / 2))
    meio_angulo = math.radians(ANGULO_APICE_SETA_GRAUS / 2)
    altura_total = rx / math.tan(meio_angulo)
    ry = max(1, round(altura_total / 1.5))

    altura_ocupada = ry + ry // 2
    if altura_util > 0 and altura_ocupada > altura_util:
        fator = altura_util / altura_ocupada
        rx = max(RAIO_MIN, round(rx * fator))
        ry = max(RAIO_MIN, round(ry * fator))
    return rx, ry


def _glifo_seta(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor,
                 *, para_cima: bool) -> None:
    """Seta solida cheia — unica leitura confirmada de direcao (COMPRA/VENDA)."""

    if para_cima:
        pontos = [QPoint(cx, cy - ry), QPoint(cx - rx, cy + ry // 2),
                  QPoint(cx + rx, cy + ry // 2)]
    else:
        pontos = [QPoint(cx, cy + ry), QPoint(cx - rx, cy - ry // 2),
                  QPoint(cx + rx, cy - ry // 2)]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    painter.drawPolygon(QPolygon(pontos))
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _glifo_losango(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Losango vazado (duas cunhas encostadas) — leitura "aguardando confirmacao".

    Vazado e nunca preenchido: e o segundo estado do visor, distinto da seta
    solida da direcao confirmada, para que o visor nunca finja saber uma
    direcao que ainda nao existe.
    """

    topo = QPoint(cx, cy - ry)
    base = QPoint(cx, cy + ry)
    esquerda = QPoint(cx - rx, cy)
    direita = QPoint(cx + rx, cy)
    painter.setPen(QPen(cor, TRACO_GLIFO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(QPolygon([topo, direita, base, esquerda]))
    painter.drawLine(esquerda, direita)


def _glifo_equilibrio(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Laco de equilibrio (dois arcos com ponta) — leitura "sem vies, NEUTRA".

    Terceiro estado do visor: nem seta cheia nem losango de espera, e sim um
    circuito fechado — a mesma leitura de "balanco de preco" sem direcao
    assumida, sem reciclar a silhueta da seta.
    """

    caixa = QRect(cx - rx, cy - ry, rx * 2, ry * 2)
    painter.setPen(QPen(cor, TRACO_GLIFO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(caixa, 20 * 16, 140 * 16)
    painter.drawArc(caixa, 200 * 16, 140 * 16)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    raio_ponta = min(rx, ry)
    for ponta_graus in (20, 200):
        ponta = _ponto_elipse(cx, cy, rx, ry, ponta_graus)
        painter.save()
        painter.translate(ponta)
        painter.rotate(-ponta_graus + 90)
        seta = QPolygon([QPoint(0, -raio_ponta // 3), QPoint(-raio_ponta // 4, raio_ponta // 6),
                         QPoint(raio_ponta // 4, raio_ponta // 6)])
        painter.drawPolygon(seta)
        painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _ponto_elipse(cx: int, cy: int, rx: float, ry: float, graus: float) -> QPoint:
    """Ponto na elipse de semi-eixos ``rx``/``ry`` (0 deg = leste, anti-horario)."""

    rad = math.radians(graus)
    return QPoint(round(cx + rx * math.cos(rad)), round(cy - ry * math.sin(rad)))
