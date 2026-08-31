"""Regiao CONTEXTO (x 0,06-0,34 · y 0,00-0,56) — Dual Market Velocity Gauge.

Reforma de 31/08/2026: o operador trouxe uma referência (print + guia de
integração ``CLAUDE_INTEGRATION_DUAL_MARKET_VELOCITY_GAUGE.md`` e o
protótipo ``dual_market_velocity_gauge.html``, pasta Codex/outputs) e
apontou que a cena anterior (um arco único com o score já suavizado do
MakerProxy) "não reflete como é feito na ASG, que mostra a macro e a
micro": a matriz ASG já calcula dois horizontes distintos — MACRO
(``estado.leituras`` apelido ``HORIZONTE``) e MICRO (apelido ``PULSO``,
ver ``asg._linhas_contexto_nexo``) — e a cena antiga só desenhava o score
do MakerProxy (um TERCEIRO sinal, ``PRESENCA``), nunca os dois horizontes.

O que esta regiao passa a mostrar:

1. **dois arcos em contra-rotação** (`_arco_duplo`) — MICRO e MACRO, cada
   um com seu próprio valor bruto, normalizado [-1,+1] e leitura de
   confiança, nunca uma média cega; a matemática (amplitude 278°, pesos
   0,58/0,42, contra-giro) é a MESMA do documento de referência — ver
   ``fluxopro/analytics/velocidade_dual.py``, que porta as fórmulas para
   Python puro e testável;
2. **candle prismático de contexto** (`_prisma`, mantido: já era um corpo
   único extrudado em 3 faces, sem costura, o que o documento de
   referência pede na seção 6) — agora com órbitas MICRO/MACRO e cor pelo
   COMPOSTO dos dois horizontes, não mais pelo MakerProxy isolado; o
   ranking "1o/2o/3o" do MakerProxy continua ao lado dele — é informação
   real que já existia e não tem por que sumir só porque o desenho central
   mudou de fonte;
3. **selo de frescor** (`frescor_do_quadro`) — ``LIVE``/``REPLAY``/
   ``STALE``/``UNAVAILABLE``, lido do MESMO ``estado_operacional`` que
   ``nexo/indisponivel.py`` já usa (nunca um heartbeat/IPC — este é um
   processo único, não um produtor e consumidor separados). ``GAP`` do
   documento de referência não é implementado: nenhum sinal deste projeto
   hoje distingue "buraco no feed" de "atrasado"/"indisponível", e inventar
   essa distinção sem fonte seria o mesmo defeito que este projeto existe
   para evitar.

As quatro leituras da matriz (`HORIZONTE`/`PULSO`/`PRESENCA`/`RITMO`)
continuam as MESMAS quatro de sempre — MACRO e MICRO só migraram de uma
lista de texto para os dois arcos; `PRESENCA`/`RITMO` continuam na coluna
lateral (`_leituras`).

Nada aqui e clicavel. Cor e forma andam sempre juntas (setas/rótulos de
sinal, nunca só o hue) para sobreviver ao modo sem cor.
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygon,
    QRadialGradient,
)

from fluxopro.analytics import velocidade_dual as _veldual
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo.estatistica import PESO_CONFIANCA

# O numero grande desta cena NAO e o score do instante: e a posicao do
# volante (`asg.VolanteGauge`), que tem inercia em tempo e escala relativa
# ao periodo. O custo disso e atraso — e atraso escondido e mentira, entao
# o rotulo da regiao carrega o aviso. E o mesmo aviso que o texto pequeno
# da leitura ja da com o sufixo `SUAV` (`asg._linha_com_forca`): uma so
# verdade, dita nos dois tamanhos de fonte.
ROTULO_REGIAO = "CONTEXTO · SUAVIZADO"

# SEGUNDOS_PARA_AVISAR_REPRESAMENTO — o atraso do volante tem DOIS regimes,
# e so um deles cabe num rotulo fixo (medido em 28/08/2026 sobre 4.361
# snapshots / 5.043 s de tape real, `.gauntlet_docx/rodadas/p8_cauda.py`):
#
#   - virada FORTE (o cru vence a zona morta): mediana 0,7 s, p90 4,5 s,
#     maximo 25,8 s. Esse custo o operador absorve sem precisar de aviso.
#   - virada FRACA (o cru troca de lado mas nunca fica grande para o
#     periodo): mediana 3,9 s, p90 41,4 s, maximo 225,8 s. Aqui o
#     mostrador fica em EQUILIBRIO por MINUTOS enquanto o cru ja esta do
#     outro lado — e um zero que nao quer dizer "nao ha fluxo", quer dizer
#     "ha fluxo, fraco para o periodo". Sao coisas diferentes na tela.
#
# ATENCAO ao que a medicao DESMENTIU aqui, porque a intuicao errava: os
# 225 s de cauda NAO sao "mostrador congelado no zero por 4 minutos". Nesse
# regime o ponteiro esta parado no LADO ANTERIOR, ou passeando perto do
# zero — o estado "preso no EQUILIBRIO com agressao de um lado so" foi
# medido separado (`VolanteGauge.segundos_represado`) e dura, na mesma
# janela de 5.043 s, mediana 3,6 s, p90 9,1 s e MAXIMO 22,2 s em 154
# episodios. Um limiar de 30 s ou de 1 minuto nunca acenderia: seria
# elemento de tela declarado e inexistente, que e a mesma familia de
# defeito que este aviso existe para nao cometer.
#
# 15 s: acima do p90 dos proprios episodios de represamento (9,1 s) e ~3x
# o p90 do regime FORTE (4,5 s). Medido nesta janela, acende em 5 dos 154
# episodios e em 0,5% dos quadros — raro o bastante para significar algo
# quando aparece. Rotulo: IMPRECISO, derivado da medicao acima.
SEGUNDOS_PARA_AVISAR_REPRESAMENTO = 15.0

# Geometria dos DOIS arcos (MICRO/MACRO) — seção 5 do documento de
# referência. MICRO fica maior e mais baixo (o horizonte primário, mesma
# hierarquia do protótipo); MACRO menor e mais alto. `FRACAO_CENTRO_*` são
# fração da REGIAO INTEIRA (não só da metade onde o arco mora), porque os
# dois centros dividem o mesmo espaço horizontal com o prisma.
FRACAO_CENTRO_MICRO_X = 0.30
FRACAO_CENTRO_MICRO_Y = 0.30
FRACAO_CENTRO_MACRO_X = 0.66
FRACAO_CENTRO_MACRO_Y = 0.20
RAIO_MICRO_MIN, RAIO_MICRO_MAX = 30, 60
RAIO_MACRO_MIN, RAIO_MACRO_MAX = 24, 50
LARGURA_TRACO_ARCO_DUAL = 5
RAIO_MARCADOR_ARCO_DUAL = 3

# Hierarquia tipografica explicita: todo par (numero, rotulo-que-o-legenda)
# mantem numero > rotulo, na ordem em que aparecem na cena. Nomeada em vez de
# literal solto para que a proxima edicao nao inverta a escala por descuido.
TAM_FONTE_NUMERO_ARCO_MIN = 12
TAM_FONTE_NUMERO_ARCO_MAX = 20
TAM_FONTE_ROTULO_ARCO = 7
TAM_FONTE_COMPOSTO = 20
TAM_FONTE_ROTULO_REGIAO = 8
TAM_FONTE_PRECO_TOPO = 10
TAM_FONTE_NUMERO_PRISMA = 11
TAM_FONTE_ROTULO_PRISMA = 7
TAM_FONTE_LEITURA_NOME = 7
TAM_FONTE_LEITURA_VALOR = 8

# Hierarquia de luminancia da lista de leituras: o rotulo (NOME) e o valor
# (VALOR) nao podem renderizar no mesmo tom. O valor sobe para perto do
# branco do proprio tema (mesmo alvo que ja usamos para preco/legenda em
# destaque); o rotulo desce um degrau abaixo do cinza neutro do painel. Sem
# essa distancia deliberada, olho nao sabe onde e dado e onde e etiqueta.
PESO_BRANCO_VALOR_LEITURA = 0.5
FATOR_ESCURO_ROTULO_LEITURA = 145

# Regua de linha: prende o rotulo ao valor da mesma leitura para que a
# hierarquia de brilho nao crie a impressao de dois blocos soltos.
FRACAO_COLUNA_ROTULO_LEITURA = 0.46
ESPACO_REGUA_LEITURA = 6
METADE_REGUA_LEITURA = 5

LARGURA_TRACO_MOLDURA = 1

# Sombreamento do prisma: mesma cor de direcao, tres luminancias + tres
# opacidades para simular tres faces solidas sob uma unica luz de cima —
# sem introduzir cor nova, so tom (lighter/darker) e opacidade. As tres
# faces precisam ficar distinguiveis MESMO sobre o fundo quase-preto do
# tema: alfa baixo demais (como na versao anterior, 40-96) faz as tres
# lerem como o mesmo maroom translucido. Por isso o alfa aqui e alto o
# bastante para o volume ler como material solido, e a distancia entre os
# tres fatores de tom e grande o bastante para nao depender so do alfa.
ALPHA_FACE_TOPO = 235
ALPHA_FACE_FRENTE = 205
ALPHA_FACE_LADO = 178
FATOR_CLARO_TOPO = 158
FATOR_CLARO_FRENTE = 112
FATOR_ESCURO_LADO = 190

# Geometria da extrusao isometrica: topo e lado sao a MESMA face de topo
# projetada por um deslocamento (profundidade_x, profundidade_y) na
# diagonal cima-direita — e essa projecao compartilhada, nao duas formas
# desenhadas por acaso, que fecha o volume sem costura visivel.
FATOR_PROFUNDIDADE_X = 0.45
FATOR_PROFUNDIDADE_Y = -0.32

# Altura do prisma e dado, nao decoracao: interpola entre um piso (o
# prisma nunca desaparece, mesmo com |score| ~ 0) e um teto, na mesma
# intensidade |score| que ja rege o anel 3. Sem essa interpolacao a caixa
# tem altura fixa e o operador so consegue ler a magnitude no texto abaixo
# dela — o que anula o proposito de desenhar um prisma.
FRACAO_ALTURA_PRISMA_MIN = 0.5

# Fundo com profundidade: gradiente radial dos tons de superficie do proprio
# tema NEXO (nunca uma cor literal nova), do centro da leitura para a borda
# da regiao.
RAIO_GRADIENTE_MARGEM = 1.35


_APELIDOS_ARCO = ("HORIZONTE", "PULSO")  # MACRO, MICRO — ver `asg._linhas_contexto_nexo`

_ESTADO_OPERACIONAL_PARA_FRESCOR = {
    "AO_VIVO": "LIVE",
    "REPLAY": "REPLAY",
    "ATRASADO": "STALE",
    # SEM_BOOK nao degrada ESTE medidor: MICRO/MACRO vem da leitura de fluxo
    # (`leitura.macro`/`leitura.micro`), nunca do livro L2 — a auséncia de
    # book e assunto de `pressao.py`/`ladder.py`, cobertos por
    # `nexo/indisponivel.py`.
    "SEM_BOOK": "LIVE",
    "ERRO": "UNAVAILABLE",
    "DESCONHECIDO": "UNAVAILABLE",
    "AGUARDANDO": "UNAVAILABLE",
}

_COR_POR_FRESCOR = {
    "LIVE": tema_asg.ESTADO_AO_VIVO,
    "REPLAY": tema_asg.ESTADO_REPLAY,
    "STALE": tema_asg.ESTADO_ATRASADO,
    "UNAVAILABLE": tema_asg.NEXO_MUTED,
}


def frescor_do_quadro(estado: EstadoNexo) -> str:
    """``LIVE``/``REPLAY``/``STALE``/``UNAVAILABLE`` — ver docstring do
    modulo sobre por que ``GAP`` nao existe aqui. Funcao pura, testavel sem
    QPainter: le so ``estado.snapshot.estado_operacional``, o MESMO campo
    que ``nexo/indisponivel.py`` ja consulta para a mesma finalidade (nunca
    uma segunda fonte de verdade sobre a saude do quadro).
    """

    operacional = getattr(getattr(estado, "snapshot", None), "estado_operacional", None)
    nome = getattr(operacional, "name", None)
    return _ESTADO_OPERACIONAL_PARA_FRESCOR.get(nome, "UNAVAILABLE")


def _linha_por_apelido(leituras: tuple[tuple[str, object], ...], apelido: str):
    for nome, linha in leituras:
        if nome == apelido:
            return linha
    return None


def _normalizado_de(linha) -> float:
    return 0.0 if linha is None else _veldual.clamp(getattr(linha, "forca", 0.0))


def _confiabilidade_de(linha) -> float:
    if linha is None:
        return 0.0
    return PESO_CONFIANCA.get(getattr(linha, "confianca", None), 0.0)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 80 or rect.height() < 80:
        return

    leituras = estado.leituras
    linha_macro = _linha_por_apelido(leituras, "HORIZONTE")
    linha_micro = _linha_por_apelido(leituras, "PULSO")
    normalizado_macro = _normalizado_de(linha_macro)
    normalizado_micro = _normalizado_de(linha_micro)
    confiab_macro = _confiabilidade_de(linha_macro)
    confiab_micro = _confiabilidade_de(linha_micro)
    disponivel = confiab_macro > 0.0 or confiab_micro > 0.0

    composto = _veldual.composto_micro_macro(
        normalizado_micro, confiab_micro, normalizado_macro, confiab_macro
    )
    rotulo_composto = _veldual.rotulo_direcao(composto) if disponivel else "SEM DADO"
    direcao_composta = {
        "ALTA": _asg.DirecaoASG.COMPRA,
        "BAIXA": _asg.DirecaoASG.VENDA,
    }.get(rotulo_composto, _asg.DirecaoASG.NEUTRA)
    cor = _asg._cor_nexo_direcao(direcao_composta)
    frescor = frescor_do_quadro(estado)

    centro_cena = rect.center()
    raio_fundo = max(RAIO_MICRO_MAX, RAIO_MACRO_MAX)
    _fundo_profundidade(painter, rect, centro_cena, raio_fundo)

    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_REGIAO))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(4, 4, -4, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     rotulo_regiao(getattr(estado, "represado_s", 0.0)))

    _desenhar_frescor(painter, rect, frescor)

    _arco_duplo(painter, rect, linha_micro, linha_macro, normalizado_micro,
               normalizado_macro, confiab_micro, confiab_macro,
               composto, rotulo_composto, cor, disponivel)

    ranking_maker = estado.maker.detalhe if estado.maker is not None else ""
    _prisma(painter, rect, composto, cor, ranking_maker,
           normalizado_micro, normalizado_macro, disponivel)

    ultimo = estado.serie[-1][1] if estado.serie else None
    if ultimo is not None:
        preco = formato.formatar_preco(estado.grid, ultimo)
        painter.setFont(tokens.fonte_numero(TAM_FONTE_PRECO_TOPO, QFont.Weight.DemiBold))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(rect.adjusted(4, 4, -4, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         f"{preco[0]}{preco[1]}")

    # A coluna de leituras encosta na borda direita da regiao; o prisma fica a
    # esquerda dela, em faixa propria, para que os dois nao se sobreponham em
    # nenhuma largura de janela. MACRO/PULSO saíram daqui — agora tem arco
    # próprio (`_arco_duplo`); a coluna mostra o que sobra (PRESENCA/RITMO).
    leituras_coluna = tuple((nome, linha) for nome, linha in leituras
                            if nome not in _APELIDOS_ARCO)
    largura_leituras = max(76, min(110, rect.width() // 4))
    _leituras(painter, QRect(rect.right() - largura_leituras,
                             rect.top() + int(rect.height() * 0.34),
                             largura_leituras,
                             min(120, rect.height() // 3)), leituras_coluna)


def _desenhar_frescor(painter: QPainter, rect: QRect, frescor: str) -> None:
    """Selo de frescor, canto superior esquerdo, sob o rotulo da regiao —
    texto SEMPRE presente (nunca so cor), como qualquer leitura de estado
    do NEXO."""

    cor = _COR_POR_FRESCOR.get(frescor, tema_asg.NEXO_MUTED)
    caixa = QRect(rect.left() + 4, rect.top() + 14, rect.width() - 8, 12)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(cor)
    painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, frescor)


def rotulo_regiao(represado_s: float) -> str:
    """Rotulo da regiao, com o aviso de represamento quando ele existe.

    Funcao separada e publica de proposito: e o unico texto desta cena que
    depende de um numero, entao ele tem de ser verificavel por teste sem
    abrir um QPainter.
    """

    if represado_s < SEGUNDOS_PARA_AVISAR_REPRESAMENTO:
        return ROTULO_REGIAO
    minutos, segundos = divmod(int(represado_s), 60)
    tempo = f"{minutos}M{segundos:02d}S" if minutos else f"{segundos}S"
    return f"{ROTULO_REGIAO} · AGRESSAO FRACA HA {tempo}"


_PERCENTUAL_NA_LINHA = re.compile(r"([+-]\d+)%")


def cor_da_linha_ranking(linha: str) -> QColor:
    """Cor de direcao para UMA linha do ranking "1o/2o/3o" do MakerProxy.

    Achado de 28/08/2026 (auditoria pos-entrega, item 24 do documento): as
    tres linhas saiam sempre em cinza/branco neutro — nenhuma cor de direcao
    — enquanto todo o resto da superficie e colorido por lado (verde/rosa).
    Era a mesma familia de "um numero, um sinal" quebrada numa QUARTA porta
    que o portao `asg.leitura_e_coerente` nao cobre, porque este texto e
    string livre (`LinhaMatrizASG.detalhe`), nunca vira uma leitura formal.

    Em vez de inventar um sinal novo, a cor e extraida do MESMO percentual
    ja impresso na linha (`asg._ranking_componentes_maker`) — nao ha como os
    dois divergirem, porque so existe uma fonte. Sinal ausente (linha sem
    percentual, ex. um formato futuro) cai em NEUTRO, nunca em erro.
    """

    achado = _PERCENTUAL_NA_LINHA.search(linha)
    if achado is None:
        return tema_asg.NEXO_MUTED
    return _asg._cor_nexo_direcao(_asg._direcao_de_score(float(achado.group(1))))


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


def _fundo_profundidade(painter: QPainter, rect: QRect, centro: QPoint, raio: int) -> None:
    """Gradiente radial nos tons do proprio tema — sem isso a cena e um
    retangulo chapado de ``NEXO_FUNDO`` (o preenchimento que o compositor ja
    fez para o quadro inteiro antes de nos chamar). Os tons continuam vindo
    de ``tema_asg``; so a distribuicao espacial e nova.
    """

    canto_x = max(centro.x() - rect.left(), rect.right() - centro.x())
    canto_y = max(centro.y() - rect.top(), rect.bottom() - centro.y())
    raio_gradiente = max(raio * 2, math.hypot(canto_x, canto_y) * RAIO_GRADIENTE_MARGEM)

    gradiente = QRadialGradient(centro, raio_gradiente)
    gradiente.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
    gradiente.setColorAt(0.45, tema_asg.NEXO_PAINEL)
    gradiente.setColorAt(1.0, tema_asg.NEXO_FUNDO)
    painter.fillRect(rect, QBrush(gradiente))


def _ponto_no_arco(centro: QPoint, raio: float, graus: float) -> QPoint:
    """Ponto na circunferencia de ``raio`` ao redor de ``centro``, na MESMA
    convencao angular do `QPainter.drawArc` (0°=leste, positivo=anti-
    horario NA TELA) — mesma formula de `nexo/nucleo.py::_ponto_elipse`."""

    rad = math.radians(graus)
    return QPoint(centro.x() + round(raio * math.cos(rad)),
                 centro.y() - round(raio * math.sin(rad)))


def _desenhar_um_arco(
    painter: QPainter, centro: QPoint, raio: int, *, angulo_base: float,
    theta: float, cor: QColor, cor_indisponivel: QColor,
    disponivel: bool, cresce_no_sentido_positivo: bool,
) -> None:
    """Um horizonte (MICRO ou MACRO): trilho apagado no vão inteiro de
    `AMPLITUDE_ARCO_GRAUS`, arco aceso do lado de ``angulo_base`` até
    ``theta``, marcador na ponta. ``cresce_no_sentido_positivo`` decide se o
    span do arco aceso é positivo (MICRO, sentido anti-horário no
    `drawArc`) ou negativo (MACRO, sentido horário) — ver
    `fluxopro.analytics.velocidade_dual.angulo_micro`/`angulo_macro`.
    """

    caixa = QRect(centro.x() - raio, centro.y() - raio, 2 * raio, 2 * raio)
    painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_ARCO_DUAL))
    painter.drawArc(caixa, round(angulo_base * 16),
                    round(_veldual.AMPLITUDE_ARCO_GRAUS * 16)
                    * (1 if cresce_no_sentido_positivo else -1))

    if not disponivel:
        return

    cor_arco = cor if disponivel else cor_indisponivel
    span = theta - angulo_base
    painter.setPen(QPen(cor_arco, LARGURA_TRACO_ARCO_DUAL))
    painter.drawArc(caixa, round(angulo_base * 16), round(span * 16))

    ponta = _ponto_no_arco(centro, raio, theta)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor_arco)
    painter.drawEllipse(ponta, RAIO_MARCADOR_ARCO_DUAL, RAIO_MARCADOR_ARCO_DUAL)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _texto_valor_horizonte(linha) -> str:
    if linha is None:
        return "—"
    valor = getattr(linha, "valor", "")
    return "—" if valor in ("", "SEM DADOS") else str(valor)


def _arco_duplo(
    painter: QPainter, rect: QRect, linha_micro, linha_macro,
    normalizado_micro: float, normalizado_macro: float,
    confiab_micro: float, confiab_macro: float,
    composto: float, rotulo_composto: str, cor: QColor, disponivel: bool,
) -> None:
    """Os dois arcos em contra-rotação (seção 5 do documento de referência)
    mais o composto no meio — a peça central da regiao. MICRO (maior, mais
    baixo) é o horizonte primário; MACRO (menor, mais alto) o secundário,
    mesma hierarquia visual do protótipo.

    Redundância não cromática exigida pelo documento: sinal (+/-) junto do
    normalizado, nome com seta (``↻ MICRO``/``↺ MACRO``), e o próprio arco
    percorrido/posição do marcador — a leitura nunca depende só da cor.
    """

    centro_micro = QPoint(rect.left() + int(rect.width() * FRACAO_CENTRO_MICRO_X),
                          rect.top() + int(rect.height() * FRACAO_CENTRO_MICRO_Y))
    centro_macro = QPoint(rect.left() + int(rect.width() * FRACAO_CENTRO_MACRO_X),
                          rect.top() + int(rect.height() * FRACAO_CENTRO_MACRO_Y))
    raio_micro = max(RAIO_MICRO_MIN, min(RAIO_MICRO_MAX, min(rect.width(), rect.height()) // 7))
    raio_macro = max(RAIO_MACRO_MIN, min(RAIO_MACRO_MAX, min(rect.width(), rect.height()) // 9))

    disponivel_micro = disponivel and confiab_micro > 0.0
    disponivel_macro = disponivel and confiab_macro > 0.0
    theta_micro = _veldual.angulo_micro(normalizado_micro)
    theta_macro = _veldual.angulo_macro(normalizado_macro)

    _desenhar_um_arco(
        painter, centro_micro, raio_micro,
        angulo_base=_veldual.ANGULO_BASE_MICRO_GRAUS, theta=theta_micro,
        cor=cor, cor_indisponivel=tema_asg.NEXO_MUTED,
        disponivel=disponivel_micro, cresce_no_sentido_positivo=True,
    )
    _desenhar_um_arco(
        painter, centro_macro, raio_macro,
        angulo_base=_veldual.ANGULO_BASE_MACRO_GRAUS, theta=theta_macro,
        cor=cor, cor_indisponivel=tema_asg.NEXO_MUTED,
        disponivel=disponivel_macro, cresce_no_sentido_positivo=False,
    )

    for centro, raio, linha, normalizado, ok, nome in (
        (centro_micro, raio_micro, linha_micro, normalizado_micro, disponivel_micro, "↻ MICRO"),
        (centro_macro, raio_macro, linha_macro, normalizado_macro, disponivel_macro, "↺ MACRO"),
    ):
        tam_numero = max(TAM_FONTE_NUMERO_ARCO_MIN,
                         min(TAM_FONTE_NUMERO_ARCO_MAX, raio // 2 + 4))
        # Hierarquia corrigida em 31/08/2026. O numero GRANDE era
        # `linha.valor` — o bruto da matriz, que no MACRO e o delta do dia
        # e chegava a "-31708" em cima de um arco cujo alcance e -1..+1.
        # Cinco digitos como titulo de um medidor de VELOCIDADE nao se
        # lê; e o normalizado, que e o que o arco realmente desenha,
        # ficava em corpo 6 embaixo. Agora o titulo e a velocidade e o
        # bruto continua na tela logo abaixo, como procedencia — nenhum
        # dado foi removido, so trocaram de posto.
        painter.setFont(tokens.fonte_numero(tam_numero, QFont.Weight.Bold))
        painter.setPen(cor if ok else tema_asg.NEXO_MUTED)
        texto_velocidade = "—" if not ok else f"{normalizado * 100:+.0f}%"
        painter.drawText(QRect(centro.x() - raio, centro.y() - 12, 2 * raio, 24),
                         Qt.AlignmentFlag.AlignCenter, texto_velocidade)
        painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_ARCO))
        painter.setPen(tema_asg.NEXO_TEXTO if ok else tema_asg.NEXO_MUTED)
        painter.drawText(QRect(centro.x() - raio, centro.y() + 10, 2 * raio, 12),
                         Qt.AlignmentFlag.AlignCenter, nome)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        bruto = _texto_valor_horizonte(linha)
        texto_sinal = "SEM DADO" if not ok else bruto
        painter.drawText(QRect(centro.x() - raio, centro.y() + 21, 2 * raio, 11),
                         Qt.AlignmentFlag.AlignCenter, texto_sinal)

    _desenhar_composto(painter, rect, centro_micro, centro_macro, composto,
                       rotulo_composto, cor, disponivel,
                       normalizado_micro, normalizado_macro,
                       max(raio_micro, raio_macro))


def _desenhar_composto(
    painter: QPainter, rect: QRect, centro_micro: QPoint, centro_macro: QPoint,
    composto: float, rotulo_composto: str, cor: QColor, disponivel: bool,
    normalizado_micro: float, normalizado_macro: float, raio_maximo: int = 0,
) -> None:
    """Percentual composto + rótulo ALTA/BAIXA/BALANCO + divergência — o
    painel de estado do meio, entre os dois arcos (seção 4/5)."""

    # 31/08/2026: a caixa nascia no X do centro mais a ESQUERDA e a apenas
    # 2px abaixo do centro mais baixo — ou seja, DENTRO do raio do arco
    # micro. Na tela real o "+16.0% MARKET / ALTA" saia escrito por cima
    # do proprio arco, ilegivel. Agora ela e centrada entre os dois
    # centros e comeca ABAIXO do maior raio, que e a unica posicao que nao
    # colide com nenhum dos dois arcos.
    largura = max(140, abs(centro_macro.x() - centro_micro.x()) + 120)
    meio_x = (centro_micro.x() + centro_macro.x()) // 2
    topo = max(centro_micro.y(), centro_macro.y()) + raio_maximo + 8
    caixa = QRect(meio_x - largura // 2, topo, largura, 46)
    caixa = caixa.intersected(rect)
    if caixa.height() < 30 or caixa.width() < 40:
        return

    texto_pct = "—" if not disponivel else f"{composto * 100:+.1f}%"
    painter.setFont(tokens.fonte_numero(TAM_FONTE_COMPOSTO, QFont.Weight.Bold))
    painter.setPen(cor if disponivel else tema_asg.NEXO_MUTED)
    painter.drawText(QRect(caixa.left(), caixa.top(), caixa.width(), 22),
                     Qt.AlignmentFlag.AlignCenter, texto_pct)

    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(cor if disponivel else tema_asg.NEXO_MUTED)
    painter.drawText(QRect(caixa.left(), caixa.top() + 20, caixa.width(), 12),
                     Qt.AlignmentFlag.AlignCenter, f"MARKET / {rotulo_composto}")

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    if disponivel:
        # `divergencia_horizontes`, NUNCA `contragiro`: o segundo mede a
        # separacao das pontas na cena contra-rotativa e vale ~0 justamente
        # quando micro e macro se OPOEM (ver a docstring dos dois). Ate
        # 31/08/2026 a tela imprimia o contragiro sob o rotulo
        # "CONTRA-GIRO", e com micro +1,00 / macro -1,00 mostrava +0,0°,
        # que o operador le como "horizontes alinhados" na oposicao maxima.
        delta, _ = _veldual.divergencia_horizontes(normalizado_micro, normalizado_macro)
        texto_giro = f"DIVERGÊNCIA {abs(delta):.0f}°" if abs(delta) >= 1 else "HORIZONTES ALINHADOS"
    else:
        texto_giro = "DIVERGÊNCIA —"
    painter.drawText(QRect(caixa.left(), caixa.top() + 32, caixa.width(), 11),
                     Qt.AlignmentFlag.AlignCenter, texto_giro)


def _prisma(painter: QPainter, rect: QRect, score: float, cor: QColor,
           ranking_maker: str = "", normalizado_micro: float = 0.0,
           normalizado_macro: float = 0.0, disponivel: bool = True) -> None:
    """Candle prismático de contexto — seção 6 do documento de referência.

    Caixa extrudada FECHADA, tres faces da MESMA cor de direcao: topo
    (a face de topo projetada na diagonal cima-direita — luz direta, a
    mais clara), frente (a face voltada para o operador — clara, mas um
    degrau abaixo do topo) e lado (a mesma projecao aplicada a aresta
    direita da frente — a mais escura, sombra propria). Topo e lado
    compartilham o vertice da frente com quem se encaixam, entao a caixa
    fecha sem costura: nao ha friso solto nem par de faces que se abrem a
    partir de uma dobra ambigua — exatamente o corpo continuo que a seção 6
    exige ("não empilhe cubos e não crie uma emenda larga no meio").

    A altura vem de |composto| (o MESMO score dos dois arcos — antes era o
    MakerProxy isolado), entre um piso (a caixa nunca murcha a zero) e um
    teto — e cresce a partir de uma LINHA DE BASE desenhada (o "chao"),
    para que a magnitude se leia no proprio volume, nao so no texto abaixo
    dele. Uma sombra de contato sob o rodape da caixa prende o volume ao
    chao (sem ela a caixa parece flutuar).

    Duas órbitas (`_orbita`) ao redor da base — MICRO por dentro, MACRO por
    fora, mesma hierarquia dos dois arcos — nomeiam de onde a altura do
    prisma vem, sem virar um terceiro número sem contrato (a seção 6 pede
    isso explicitamente: "não use a altura do cubo como número adicional
    sem contrato").
    """

    intensidade = max(0.0, min(1.0, abs(score))) if disponivel else 0.0

    largura = max(34, rect.width() // 9)
    prof_x = max(10, round(largura * FATOR_PROFUNDIDADE_X))
    prof_y = round(largura * FATOR_PROFUNDIDADE_Y)  # negativo: sobe e vai p/ direita

    altura_teto = max(48, rect.height() // 5)
    altura_piso = round(altura_teto * FRACAO_ALTURA_PRISMA_MIN)
    altura = round(altura_piso + (altura_teto - altura_piso) * intensidade)

    x = rect.left() + int(rect.width() * 0.56)
    chao_y = rect.top() + int(rect.height() * 0.56) + altura_teto
    topo_y = chao_y - altura

    if disponivel:
        centro_orbita = QPoint(x + (largura + prof_x) // 2, chao_y + 4)
        largura_base = largura + prof_x
        # MACRO por fora (mais larga, mais apagada) — mesma hierarquia dos
        # dois arcos (macro secundário). MICRO por dentro. Nenhuma das duas
        # e um numero adicional: e so a NOMEACAO de onde a altura do prisma
        # vem (seção 6 pede exatamente isto).
        painter.setPen(QPen(_com_alpha(cor, 90), 1))
        painter.drawEllipse(centro_orbita, round(largura_base * 0.62),
                            round(largura_base * 0.20))
        painter.setPen(QPen(_com_alpha(cor, 150), 1, Qt.PenStyle.DotLine))
        painter.drawEllipse(centro_orbita, round(largura_base * 0.46),
                            round(largura_base * 0.14))

    # Rodape (linha de base): o "zero" contra o qual a altura se mede. Sem
    # esta linha o operador nao tem de onde partir o olho para julgar
    # "caixa alta" vs "caixa baixa" — so o numero abaixo dela.
    painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_MOLDURA))
    painter.drawLine(x - 6, chao_y, x + largura + prof_x + 6, chao_y)

    # Sombra de contato: elipse achatada no mesmo tom escuro do fundo,
    # centrada no rodape da face frontal — ancora o volume ao chao.
    sombra = _com_alpha(tema_asg.NEXO_FUNDO.darker(120), 150)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(sombra)
    painter.drawEllipse(QPoint(x + largura // 2, chao_y + 2), largura // 2 + 6, 5)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    frente = QPolygon([QPoint(x, chao_y), QPoint(x + largura, chao_y),
                       QPoint(x + largura, topo_y), QPoint(x, topo_y)])
    topo = QPolygon([QPoint(x, topo_y), QPoint(x + largura, topo_y),
                     QPoint(x + largura + prof_x, topo_y + prof_y),
                     QPoint(x + prof_x, topo_y + prof_y)])
    lado = QPolygon([QPoint(x + largura, chao_y), QPoint(x + largura, topo_y),
                     QPoint(x + largura + prof_x, topo_y + prof_y),
                     QPoint(x + largura + prof_x, chao_y + prof_y)])

    cor_topo = _com_alpha(cor.lighter(FATOR_CLARO_TOPO), ALPHA_FACE_TOPO)
    cor_frente = _com_alpha(cor.lighter(FATOR_CLARO_FRENTE), ALPHA_FACE_FRENTE)
    cor_lado = _com_alpha(cor.darker(FATOR_ESCURO_LADO), ALPHA_FACE_LADO)

    painter.setPen(cor)
    for poligono, preenchimento in ((lado, cor_lado), (frente, cor_frente), (topo, cor_topo)):
        painter.setBrush(preenchimento)
        painter.drawPolygon(poligono)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setFont(tokens.fonte_numero(TAM_FONTE_NUMERO_PRISMA, QFont.Weight.Bold))
    painter.setPen(cor if disponivel else tema_asg.NEXO_MUTED)
    painter.drawText(QRect(x - 12, chao_y + 10, largura + prof_x + 40, 16),
                     # MESMO formato do numero do mostrador logo acima: e o
                     # MESMO composto, impresso duas vezes na mesma regiao.
                     # Com `+.1f` o prisma era o unico percentual da tela
                     # inteira com casa decimal — e com separador `.`, num
                     # quadro que escreve preco em `5.174,5`. Mesma leitura,
                     # mesma forma.
                     Qt.AlignmentFlag.AlignCenter,
                     "—" if not disponivel else f"{score * 100:+.0f}%")
    painter.setFont(tokens.fonte_rotulo(TAM_FONTE_ROTULO_PRISMA))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(x - 18, topo_y + prof_y - 15, largura + prof_x + 52, 14),
                     Qt.AlignmentFlag.AlignCenter, "CONTEXT / MARKET CORE")

    # Ranking dos componentes do MakerProxy por magnitude ("Maker 1o/2o/3o"
    # pedido pelo operador) — nunca uma entidade nova, so o mesmo sinal
    # agregado quebrado por componente. So desenha quando ha componente
    # real disponivel (nunca fabrica ranking vazio).
    #
    # UMA LINHA POR POSICAO, fonte legivel — achado ao vivo pelo operador
    # ("onde esta os makers?"): a versao anterior espremia as 3 posicoes
    # numa unica linha a ~5px, tecnicamente presente mas ilegivel na pratica.
    #
    # O rotulo "MAKER PROXY" migrou para AQUI (era o titulo do prisma
    # inteiro antes desta reforma): o cubo agora representa o COMPOSTO
    # MICRO/MACRO, e o ranking continua sendo especificamente do MakerProxy
    # — os dois sinais nao podem compartilhar um titulo so.
    if ranking_maker:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(QRect(x - 30, chao_y + 22, max(largura + prof_x + 70, 150), 10),
                         Qt.AlignmentFlag.AlignLeft, "MAKER PROXY · RANKING")
        linhas_ranking = ranking_maker.split("\n")
        altura_linha_ranking = 13
        largura_bloco = max(largura + prof_x + 70, 150)
        x_bloco = x - 30
        y_bloco = chao_y + 33
        # Nunca desenhar por cima da PROXIMA regiao: se a caixa nao tem
        # altura para as 3 linhas (janela pequena, cubo baixo na regiao),
        # corta as linhas de baixo em vez de invadir o vizinho — achado ao
        # vivo pelo operador (a 3a linha ficava por cima da faixa de niveis).
        linhas_que_cabem = max(0, (rect.bottom() - y_bloco) // altura_linha_ranking)
        linhas_ranking = linhas_ranking[:linhas_que_cabem]
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        for indice, linha in enumerate(linhas_ranking):
            cor_linha = cor_da_linha_ranking(linha)
            painter.setPen(cor_linha if indice == 0 else _com_alpha(cor_linha, 170))
            painter.drawText(
                QRect(x_bloco, y_bloco + indice * altura_linha_ranking,
                     largura_bloco, altura_linha_ranking),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                linha,
            )


def _tom_valor_leitura(cor: QColor) -> QColor:
    """Mistura a cor de direcao com o branco quase puro do tema (mesmo alvo
    usado em preco/legenda de destaque), garantindo que o VALOR sempre pouse
    num degrau de luminancia claramente acima do rotulo — independente de a
    cor de direcao, sozinha e num traco fino de 8pt, ser clara o bastante.
    """

    alvo = tema_asg.NEXO_TEXTO
    peso = PESO_BRANCO_VALOR_LEITURA
    return QColor(
        round(cor.red() * (1 - peso) + alvo.red() * peso),
        round(cor.green() * (1 - peso) + alvo.green() * peso),
        round(cor.blue() * (1 - peso) + alvo.blue() * peso),
    )


def _leituras(painter: QPainter, rect: QRect,
              linhas: tuple[tuple[str, object], ...]) -> None:
    """Coluna ROTULO -> VALOR com dois degraus de luminancia (valor perto do
    branco, rotulo abaixo do cinza neutro) e uma regua fina por linha que
    prende cada valor ao rotulo que o legenda — sem a regua, o degrau de
    brilho por si so faria rotulo e valor lerem como dois blocos soltos em
    vez de um par leitura->numero.

    Recebe as leituras já FILTRADAS por quem chama (`desenhar` remove
    HORIZONTE/PULSO, que migraram para `_arco_duplo`) — esta função não
    decide o que aparece na coluna, só desenha o que recebeu.
    """

    if not linhas or rect.height() < 42:
        return
    altura = max(16, rect.height() // len(linhas))
    coluna_rotulo = int(rect.width() * FRACAO_COLUNA_ROTULO_LEITURA)
    x_regua = rect.left() + coluna_rotulo
    rotulo_suprimido = tema_asg.NEXO_MUTED.darker(FATOR_ESCURO_ROTULO_LEITURA)
    for indice, (nome, linha) in enumerate(linhas):
        y = rect.y() + indice * altura
        cor = _asg._cor_nexo_direcao(linha.direcao)
        painter.setFont(tokens.fonte_rotulo(TAM_FONTE_LEITURA_NOME))
        painter.setPen(rotulo_suprimido)
        painter.drawText(QRect(rect.left(), y, coluna_rotulo - ESPACO_REGUA_LEITURA, altura),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)

        meio_y = y + altura // 2
        painter.setPen(QPen(tema_asg.NEXO_GRADE, LARGURA_TRACO_MOLDURA))
        painter.drawLine(x_regua, meio_y - METADE_REGUA_LEITURA,
                         x_regua, meio_y + METADE_REGUA_LEITURA)

        painter.setFont(tokens.fonte_numero(TAM_FONTE_LEITURA_VALOR, QFont.Weight.Bold))
        painter.setPen(_tom_valor_leitura(cor))
        painter.drawText(QRect(x_regua + ESPACO_REGUA_LEITURA, y,
                               rect.width() - coluna_rotulo - ESPACO_REGUA_LEITURA, altura),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         linha.valor)
