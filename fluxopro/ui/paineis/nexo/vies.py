"""Regiao OPERADOR IA / VIES (x 0,40-0,63 · y 0,42-1,00).

Console consultivo do **Sinal Ultra**. Ate 28/08/2026 esta regiao ocupava
~20% da largura do quadro (≈384x410 px em 1920x1080) para entregar uma
esfera decorativa e duas linhas de texto — densidade de informacao por pixel
proxima de zero, contra vizinhas que entregam dezenas de leituras no mesmo
espaco (`estatistica`, `nucleo`, `ladder`). Achado do operador (item 5 do
documento de mudancas): "esta feio visualmente, muito simples (...) e nao
esta funcional, pois nunca apareceu nada".

O "nunca apareceu nada" tinha causa concreta: a regiao **nao lia
``estado.sinal_ultra``**. O Ultra podia estar armado que este bloco continuava
mostrando o mesmo disco.

## Divisao de escopo com o visor central (decisao de coordenacao, 28/08/2026)

O visor central (``nexo/nucleo.py``) e dono do **mecanismo**: as condicoes do
filtro Ultra, uma a uma, com o valor medido de cada. Esta regiao e dona da
**leitura e da narracao**: o que aquele sinal significa, o que observar
agora, e o que o painel fala em voz alta.

Uma versao intermediaria desta regiao desenhou um placar de portoes proprio,
e as duas regioes passaram a dizer a mesma coisa em vocabulario diferente no
mesmo quadro — pior que qualquer uma das duas sozinha. O placar saiu daqui.
Quando esta regiao precisa se referir a uma condicao especifica, ela **aponta
para o visor** em vez de reimprimir o numero: uma unica fonte na tela para
cada fato.

As faixas de hoje:

1. **cabecalho** — avatar do OPERADOR IA (geometria autoral, nunca asset de
   terceiro) com anel de estado, titulo e o chip de VOZ;
2. **selo de estado do Ultra** — ARMADO / SEGURANDO / CONFIRMANDO / SEM
   SINAL / MOTOR AUSENTE, com o tempo decorrido desde que acendeu;
3. **ciclo do filtro** — o trilho da histerese (confirma / aceso / segura),
   que e a leitura do filtro no TEMPO. O visor central mostra as condicoes
   no instante; nenhuma outra regiao conta o ciclo;
4. **leitura** — o que este sinal esta dizendo, e o que observar agora;
5. **narracao** — a frase EXATA que o locutor falou, em texto.

## A regiao cresceu (28/08/2026)

Era (0,42 · 0,62 · 0,62 · 1,00) e virou (0,40 · 0,42 · 0,63 · 1,00): ela
agora cola no rodape do visor central e assume a coluna central inteira.
Motivo em ``nexo/__init__.py``, no comentario do mapa — havia um vao de
~440x216 px sem dono nenhum entre as duas regioes do par, o maior campo
morto da tela, e o proprio contrato de composicao afirmava (falsamente) que
nao havia vao. O retangulo de ``nucleo`` nao foi tocado.

## SEGURANDO: o selo aceso que ja nao afirma alinhamento

``fase_do_filtro`` separa **aceso com as condicoes alinhadas agora**
(``ARMADO``) de **aceso apenas porque a histerese ainda nao desarmou**
(``SEGURANDO``). Antes disso a regiao dizia "as fontes estao alinhadas ao
mesmo tempo" enquanto o visor ao lado ja imprimia a condicao caida — duas
regioes afirmando coisas incompativeis sobre o mesmo instante. Em
``SEGURANDO`` mudam o selo (cor de atencao, nao a do lado), a leitura e a
faixa de narracao, que passa a marcar a frase como ANUNCIO ANTERIOR e a
dizer explicitamente que o alinhamento que ela afirma ja caiu.

## Narracao: a tela e o audio saem da mesma funcao

A faixa de NARRACAO nao redige frase propria: ela chama
``fluxopro.audio.voz.texto_para_transicao_ultra``, a MESMA funcao que
alimenta o ``LocutorASG``. Duas redacoes paralelas divergiriam em silencio —
o operador ouviria uma coisa e leria outra. Como efeito colateral util, quem
esta com a voz desligada (o padrao) le na tela exatamente o que teria
ouvido.

A voz continua **desligada por padrao** e liga so com ``FLUXOPRO_VOZ=1``;
esta regiao nunca instancia locutor nem sobe thread — so le e exibe texto.

## O que "instrucao" significa aqui (limite duro)

O produto e consultivo e nunca envia ordem. A faixa de LEITURA descreve
**o que o sinal esta dizendo** e **o que observar agora**; nunca preco de
entrada, alvo, stop, tamanho ou momento de operar. Se um dia uma frase daqui
puder ser lida como conselho de execucao, a frase esta errada, nao o limite.

## Estado honesto

Sem ``sinal_ultra`` no estado, o selo diz MOTOR AUSENTE em vez de "sem
sinal" — as duas coisas sao diferentes e confundi-las e mentir. Sem anuncio
a narrar, a faixa diz que nao houve anuncio, nunca inventa uma frase.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)

from fluxopro.asg.sinal_ultra import ConfigSinalUltra, DirecaoUltra
from fluxopro.audio import voz as _voz
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

RAIO_MIN = 20
RAIO_MAX = 48

# Config de referencia. Esta regiao NAO exibe valor medido de condicao
# nenhuma (isso e do visor central); a unica coisa que ela le daqui e a
# DURACAO da janela de confirmacao, para a frase "ainda dentro da janela de
# 5s" nao trazer um numero digitado a mao.
# CONFIRMADO (no proprio codigo): `MotorSinalUltra.__init__` usa
# `ConfigSinalUltra()` quando `asg.py` nao passa outra — e hoje nao passa.
_CONFIG_REFERENCIA = ConfigSinalUltra()

# Chip de VOZ. Le a MESMA variavel de ambiente que `asg.py` le para decidir
# se instancia o locutor (`_VOZ_ATIVA_POR_PADRAO`), com a mesma normalizacao,
# no import — nunca liga nada, so relata. A voz continua DESLIGADA por
# padrao por contrato do projeto (ver docstring de `fluxopro/audio/voz.py`);
# este chip existe porque o operador nao tinha como saber, olhando a tela,
# se o anuncio falado ia sair ou nao.
_VOZ_LIGADA = os.environ.get("FLUXOPRO_VOZ", "").strip().lower() in {"1", "true", "sim"}

# Alturas das faixas do console, em pixels. Sao geometria desta regiao (o
# mesmo criterio pelo qual ALTURA_CARTAO mora em `nucleo.py`), nao estilo.
ALTURA_CABECALHO = 42
ALTURA_SELO = 54
ALTURA_RODAPE = 26
MARGEM = 9

# Cabecalho de cada bloco de texto (o rotulo "O QUE ESTE SINAL DIZ" e sua
# linha divisoria) e a folga entre blocos.
ALTURA_TITULO_BLOCO = 16
VAO_BLOCO = 8

# Os tres blocos de texto dividem TODA a folga vertical restante da regiao,
# em vez de terem altura fixa: uma versao anterior fixou as alturas e sobrou
# ~110px de campo preto morto entre o ultimo bloco e o rodape, exatamente o
# defeito que esta regiao existe para corrigir. Os pesos abaixo repartem
# essa folga — a narracao leva o maior porque a frase falada e a mais longa
# das tres e e a unica que nao pode ser truncada sem perder sentido.
PESOS_BLOCOS = (0.30, 0.32, 0.38)

# Faixa do ciclo da histerese (trilho de tres etapas). So aparece quando a
# regiao tem altura para ela sem espremer os blocos de texto — abaixo disso
# as duas frases de leitura ja contam a mesma histerese em palavras.
ALTURA_CICLO = 52
ALTURA_MIN_LINHA_DO_TEMPO = 420

# Teto de quanto o cabecalho pode crescer com a folga que os blocos de texto
# nao usaram. Existe teto porque a folga vira TAMANHO DE AVATAR, e avatar e
# a parte decorativa da regiao: acima disso a regiao voltaria a ser a esfera
# grande num campo vazio que o operador reprovou. 110px leva o raio ao
# RAIO_MAX (48) e para por ai.
FOLGA_MAX_CABECALHO = 110

# Abaixo destas medidas o console nao cabe sem sobreposicao e a regiao cai
# para o modo compacto (so avatar + selo) ou para nada. Medido no quadro de
# 1920x1080, onde a regiao recebe ~384x410.
LARGURA_MIN_CONSOLE = 210
ALTURA_MIN_CONSOLE = 250


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
       protanopia;
    2. ``estado.paleta`` e quem sabe se o quadro esta em ``--sem-cor``
       (``tokens.PALETA_SEM_COR`` colapsa compra/venda/neutro no mesmo
       ``QColor``).

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


# --------------------------------------------------------------------------
# Leitura do estado (puro, sem Qt) — testavel sem tela.
# --------------------------------------------------------------------------


# Fases do filtro, do ponto de vista do TEMPO — que e o que esta regiao
# narra. O visor central e dono das condicoes instantaneas; aqui interessa
# em que ponto da histerese o filtro esta.
#
# `SEGURANDO` foi o achado da rodada de 28/08/2026: com o selo aceso e a
# confluencia ja quebrada, o visor ao lado imprimia "SEGURANDO" e mostrava
# a condicao caida, enquanto esta regiao continuava afirmando, sem ressalva,
# que "as fontes estao alinhadas ao mesmo tempo". Duas regioes dizendo
# coisas incompativeis sobre o MESMO instante — o filtro se sustentava por
# histerese e a narracao vendia isso como alinhamento vivo.
AUSENTE = "ausente"
ARMADO = "armado"
SEGURANDO = "segurando"
CONFIRMANDO = "confirmando"
SEM_SINAL = "sem_sinal"


def fase_do_filtro(estado: EstadoNexo) -> str:
    """Em que ponto da histerese o filtro esta neste quadro.

    Ponto unico de resolucao: selo, leitura, narracao e linha do tempo saem
    todos daqui, para nao existir a chance de uma faixa da regiao dizer
    "armado" enquanto a vizinha diz "segurando".
    """

    ultra = estado.sinal_ultra
    if ultra is None:
        return AUSENTE
    if ultra.direcao is not DirecaoUltra.NENHUMA:
        # Aceso E a confluencia crua ainda concorda = alinhamento vivo.
        # Aceso mas a confluencia crua ja NAO concorda = so a histerese
        # segurando o selo. Sao coisas diferentes e a tela tem de separar.
        if ultra.confluencia_no_instante is ultra.direcao:
            return ARMADO
        return SEGURANDO
    if ultra.confluencia_no_instante is not DirecaoUltra.NENHUMA:
        return CONFIRMANDO
    return SEM_SINAL


def _lado(direcao: DirecaoUltra, feminino: bool = False) -> str:
    if direcao is DirecaoUltra.COMPRA:
        return "compradora" if feminino else "compra"
    return "vendedora" if feminino else "venda"


def leitura_do_sinal(estado: EstadoNexo) -> tuple[str, ...]:
    """O que este sinal esta DIZENDO — leitura, nunca conselho.

    Limite duro (ver docstring do modulo): descreve o significado do estado;
    nunca entrada, alvo, stop, tamanho ou momento de operar.

    Nao reimprime o valor medido de nenhuma condicao: quem e dono do
    mecanismo e o visor central. Quando o operador precisa do numero, a
    frase aponta para la em vez de criar uma segunda copia na tela.
    """

    fase = fase_do_filtro(estado)
    if fase is AUSENTE or fase == AUSENTE:
        return ("O motor do Sinal Ultra nao esta alimentando este quadro.",
                "Sem estado de filtro para interpretar.")

    ultra = estado.sinal_ultra
    if fase == ARMADO:
        return (
            f"Confluencia {_lado(ultra.direcao, feminino=True)} confirmada: as "
            "fontes que o filtro exige estao alinhadas ao mesmo tempo, e nao "
            "uma leitura isolada.",
        )

    if fase == SEGURANDO:
        segundos = _CONFIG_REFERENCIA.tempo_para_desligar_ns / 1e9
        return (
            f"O selo de {_lado(ultra.direcao)} segue aceso por HISTERESE, nao "
            "por alinhamento: neste instante as condicoes ja nao concordam.",
            f"O filtro so desarma apos {segundos:.0f}s continuos com a "
            "confluencia quebrada, para nao piscar a cada negocio.",
        )

    if fase == CONFIRMANDO:
        segundos = _CONFIG_REFERENCIA.persistencia_minima_ns / 1e9
        return (
            f"Alinhamento de {_lado(ultra.confluencia_no_instante)} neste "
            f"instante, ainda dentro da janela de confirmacao de "
            f"{segundos:.0f}s — o filtro ainda nao armou.",
        )

    return (
        "Nenhum alinhamento agora. O filtro exige as condicoes juntas, "
        "por isso ele fica calado na maior parte do pregao.",
    )


def observar_agora(estado: EstadoNexo) -> tuple[str, ...]:
    """O que ACOMPANHAR daqui pra frente neste estado.

    Continua sendo leitura: aponta o que faria o estado mudar, nunca o que
    o operador deveria fazer a respeito.
    """

    fase = fase_do_filtro(estado)
    if fase == AUSENTE:
        return ("Verificar se o painel esta recebendo o motor do filtro.",)

    if fase == ARMADO:
        return (
            "O alinhamento se desfaz quando qualquer condicao do filtro cai; "
            "as condicoes e os valores medidos estao no visor central.",
            "O filtro so desarma apos a confluencia ficar quebrada por um "
            "tempo continuo — ele nao pisca a cada negocio.",
        )

    if fase == SEGURANDO:
        return (
            "Qual condicao caiu esta no visor central, que mostra a mesma "
            "quebra neste instante.",
            "Dois desfechos daqui: as condicoes voltam a concordar e o selo "
            "volta a ser alinhamento, ou a janela se esgota e ele apaga.",
        )

    if fase == CONFIRMANDO:
        return (
            "Se qualquer condicao cair antes do fim da janela, o filtro nao "
            "arma e a contagem recomeca do zero.",
        )

    return (
        "Acompanhar as condicoes no visor central: o filtro so acende com "
        "todas elas simultaneas.",
    )


def narracao_desatualizada(estado: EstadoNexo) -> bool:
    """`True` quando a ultima frase anunciada ja nao descreve o instante.

    Existe por causa do estado ``SEGURANDO``: a frase dita no momento em que
    o filtro armou afirma alinhamento das fontes, e enquanto a histerese
    segura o selo essa afirmacao ficou para tras. Repetir a frase sem esta
    ressalva faria a regiao afirmar, pelo canal da narracao, exatamente o
    alinhamento que a faixa de leitura acabou de negar.
    """

    return fase_do_filtro(estado) == SEGURANDO


def texto_narrado(estado: EstadoNexo) -> str | None:
    """A frase EXATA que o locutor falou neste estado, ou ``None``.

    Sai de ``voz.texto_para_transicao_ultra`` — a MESMA funcao que alimenta
    o ``LocutorASG``. Redigir uma segunda versao aqui faria a tela e o audio
    divergirem em silencio.

    Como o locutor so fala em TRANSICAO, o que existe para narrar e a frase
    da transicao que trouxe o quadro ao estado atual: entrar em COMPRA/VENDA
    produz o mesmo texto qualquer que fosse o estado anterior (ver
    ``voz.texto_para_transicao_ultra``), entao a frase abaixo e literalmente
    a que foi dita quando o filtro armou. Sem filtro aceso nao houve
    anuncio, e a funcao devolve ``None`` em vez de inventar uma fala.

    Em ``SEGURANDO`` a frase continua sendo a que foi dita — o que muda e
    que ela deixa de valer para o instante, e ``narracao_desatualizada``
    manda a faixa dizer isso.
    """

    ultra = estado.sinal_ultra
    if ultra is None or ultra.direcao is DirecaoUltra.NENHUMA:
        return None
    return _voz.texto_para_transicao_ultra(DirecaoUltra.NENHUMA, ultra.direcao)


def _tempo_aceso(estado: EstadoNexo) -> str | None:
    """"HA 42S" desde que o filtro acendeu, ou ``None`` sem base para medir."""

    ultra = estado.sinal_ultra
    if ultra is None or not ultra.ligado_desde_ns:
        return None
    agora = getattr(estado.snapshot, "timestamp_ns", 0)
    if not agora or agora < ultra.ligado_desde_ns:
        return None
    return f"HA {(agora - ultra.ligado_desde_ns) / 1e9:.0f}S"


def _texto_selo(estado: EstadoNexo) -> tuple[str, str, QColor]:
    """(titulo, subtitulo, cor) do selo de estado do Ultra."""

    fase = fase_do_filtro(estado)
    if fase == AUSENTE:
        return ("MOTOR AUSENTE", "SINAL ULTRA NAO ALIMENTADO NESTE QUADRO",
                tema_asg.NEXO_MUTED)

    ultra = estado.sinal_ultra
    if ultra.direcao is DirecaoUltra.COMPRA:
        cor = estado.paleta.compra
    elif ultra.direcao is DirecaoUltra.VENDA:
        cor = estado.paleta.venda
    else:
        cor = tema_asg.NEXO_MUTED

    if fase == ARMADO:
        aceso = _tempo_aceso(estado)
        sub = (f"ACESO {aceso} · CONDICOES ALINHADAS AGORA" if aceso
               else "CONDICOES ALINHADAS AGORA")
        return (f"⚡ ULTRA {ultra.direcao.value.upper()} ARMADO", sub, cor)

    if fase == SEGURANDO:
        # Cor de ATENCAO, nao a do lado: o selo aceso sem alinhamento nao
        # pode ter a mesma aparencia do selo aceso COM alinhamento — era
        # justamente isso que fazia a regiao parecer confirmar o que ja
        # tinha caido.
        aceso = _tempo_aceso(estado)
        sub = (f"ACESO {aceso} · SEM ALINHAMENTO NO INSTANTE" if aceso
               else "SEM ALINHAMENTO NO INSTANTE")
        return (f"ULTRA {ultra.direcao.value.upper()} SEGURANDO", sub,
                tokens.ALERT)

    if fase == CONFIRMANDO:
        lado = ultra.confluencia_no_instante.value.upper()
        return (f"CONFIRMANDO {lado}", "CONFLUENCIA CRUA · AINDA NAO ARMOU",
                tokens.ALERT)

    return ("SEM SINAL ULTRA", "NENHUMA CONFLUENCIA NO INSTANTE",
            tema_asg.NEXO_MUTED)


# --------------------------------------------------------------------------
# Pintura
# --------------------------------------------------------------------------


def _fundo_console(painter: QPainter, area: QRect) -> None:
    """Profundidade da faixa inteira: gradiente vertical + realce de topo +
    sombra de base. Sem isso a regiao le como buraco preto no meio do quadro
    (era exatamente o defeito relatado)."""

    grad = QLinearGradient(QPointF(area.left(), area.top()),
                           QPointF(area.left(), area.bottom()))
    grad.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
    grad.setColorAt(1.0, tema_asg.NEXO_FUNDO)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(area)

    realce = QColor(tema_asg.NEXO_TEXTO)
    realce.setAlpha(28)
    painter.setPen(QPen(realce, 1))
    painter.drawLine(area.left(), area.top(), area.right(), area.top())


def _desenhar_avatar(painter: QPainter, cx: int, cy: int, raio: int,
                     cor_anel: QColor) -> None:
    """Avatar do OPERADOR IA — geometria autoral (nunca a foto/render de
    terceiro dos prints de referencia): esfera com luz fora de eixo, sombra
    projetada, especular, visor e brackets de mira.

    A profundidade vem de tres camadas empilhadas, nao de um gradiente
    linear chapado: sombra elíptica abaixo, gradiente RADIAL deslocado do
    centro (uma esfera iluminada de verdade tem o brilho fora do centro) e
    um especular translucido no ponto onde a luz bate.
    """

    sombra = QColor(tema_asg.NEXO_IDENTIDADE_ANEL)
    sombra.setAlpha(50)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(sombra)
    painter.drawEllipse(QPointF(cx, cy + raio * 0.75), raio * 0.8, raio * 0.22)

    esfera = QRadialGradient(QPointF(cx - raio * 0.35, cy - raio * 0.45), raio * 1.7)
    esfera.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO.lighter(170))
    esfera.setColorAt(0.55, tema_asg.NEXO_PAINEL_ALTO)
    esfera.setColorAt(1.0, tema_asg.NEXO_IDENTIDADE_NUCLEO)
    painter.setBrush(esfera)
    painter.drawEllipse(QPoint(cx, cy), raio, raio)

    brilho = QRadialGradient(QPointF(cx - raio * 0.4, cy - raio * 0.5), raio * 0.55)
    inicio = QColor(255, 255, 255)
    inicio.setAlpha(80)
    fim = QColor(255, 255, 255)
    fim.setAlpha(0)
    brilho.setColorAt(0.0, inicio)
    brilho.setColorAt(1.0, fim)
    painter.setBrush(brilho)
    painter.drawEllipse(QPointF(cx - raio * 0.4, cy - raio * 0.5),
                        raio * 0.5, raio * 0.34)

    # Anel de ESTADO: e a unica parte colorida do avatar. A esfera continua
    # cromo neutro de proposito (o mesmo ciano/verde ja carrega outros
    # papeis no quadro); o anel e quem diz em que estado o Ultra esta.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(cor_anel, 2))
    painter.drawEllipse(QPoint(cx, cy), raio + 4, raio + 4)

    # Visor: uma FRESTA horizontal com dois segmentos acesos, no mesmo
    # vocabulario do visor HUD central (nucleo.py).
    #
    # Nao ha olhos redondos nem boca: a versao anterior desenhava dois
    # circulos e um arco, e no tamanho grande (a regiao passou a 612px de
    # altura em 28/08/2026) aquilo lia como um SMILEY — simpatico e
    # completamente fora do registro de um terminal de leitura de fluxo.
    # Fresta + segmentos le como instrumento em qualquer tamanho.
    meia = max(2, raio // 12)
    fresta = QRect(cx - raio // 2, cy - raio // 6 - meia, raio, 2 * meia)
    fundo_fresta = QColor(tema_asg.NEXO_FUNDO)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fundo_fresta)
    painter.drawRoundedRect(fresta, meia, meia)

    painter.setBrush(cor_anel)
    largura_seg = max(3, raio // 5)
    for deslocamento in (-raio // 3, raio // 3):
        painter.drawRoundedRect(
            QRect(cx + deslocamento - largura_seg // 2, fresta.top() + 1,
                  largura_seg, fresta.height() - 2),
            meia // 2 or 1, meia // 2 or 1)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Barra de atividade sob a fresta: tres tracos curtos, decrescentes.
    # E cromo de instrumento, nao leitura de dado — por isso fica no cinza
    # de identidade e nunca na cor de direcao.
    painter.setPen(QPen(tema_asg.NEXO_IDENTIDADE_ANEL, 1))
    base = cy + raio // 4
    for indice, fracao in enumerate((0.42, 0.30, 0.18)):
        meia_barra = max(2, int(raio * fracao / 2))
        painter.drawLine(cx - meia_barra, base + indice * 4,
                         cx + meia_barra, base + indice * 4)

    braco = max(4, raio // 3)
    painter.setPen(QPen(tema_asg.NEXO_IDENTIDADE_ANEL, 1))
    for px, py, dx, dy in (
        (cx - raio - 7, cy - raio - 7, 1, 1),
        (cx + raio + 7, cy - raio - 7, -1, 1),
        (cx - raio - 7, cy + raio + 7, 1, -1),
        (cx + raio + 7, cy + raio + 7, -1, -1),
    ):
        painter.drawLine(px, py, px + dx * braco, py)
        painter.drawLine(px, py, px, py + dy * braco)


def _desenhar_selo(painter: QPainter, area: QRect, titulo: str, sub: str,
                   cor: QColor) -> None:
    """Selo de estado: chapa com gradiente na cor do estado, barra de acento
    a esquerda e o rotulo em duas linhas. Volume vem do gradiente horizontal
    + linha de realce no topo, nao de sombra falsa."""

    faixa = QColor(cor)
    faixa.setAlpha(46)
    grad = QLinearGradient(QPointF(area.left(), area.top()),
                           QPointF(area.right(), area.top()))
    grad.setColorAt(0.0, faixa)
    transparente = QColor(cor)
    transparente.setAlpha(6)
    grad.setColorAt(1.0, transparente)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(area)

    painter.setBrush(cor)
    painter.drawRect(QRect(area.left(), area.top(), 3, area.height()))

    realce = QColor(cor)
    realce.setAlpha(90)
    painter.setPen(QPen(realce, 1))
    painter.drawLine(area.left(), area.top(), area.right(), area.top())

    texto = QRect(area.left() + 14, area.top() + 6, area.width() - 18, 22)
    painter.setPen(cor)
    painter.setFont(tokens.fonte_numero(17, QFont.Weight.Bold))
    painter.drawText(texto, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     titulo)
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(QRect(area.left() + 14, area.top() + 30, area.width() - 18, 16),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub)


def _altura_natural(painter: QPainter, largura: int, corpo: str,
                     tamanho_corpo: int) -> int:
    """Altura que o bloco precisa para caber o texto INTEIRO, medida com a
    mesma fonte e a mesma largura com que ele sera pintado.

    Existe porque a regiao passou a ter 612px de altura (28/08/2026): pesos
    fixos numa regiao alta esticam tres paragrafos curtos em tres campos
    esparsos, que e o mesmo defeito de campo morto so que fatiado. Cada
    bloco passa a pedir o que precisa, e a folga vai para o avatar.
    """

    painter.setFont(tokens.fonte_ui(tamanho_corpo))
    caixa = painter.fontMetrics().boundingRect(
        QRect(0, 0, largura, 10_000),
        int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            | Qt.TextFlag.TextWordWrap),
        corpo,
    )
    return ALTURA_TITULO_BLOCO + caixa.height() + 6


def _desenhar_bloco_texto(painter: QPainter, area: QRect, titulo: str,
                          corpo: str, cor_titulo: QColor,
                          cor_corpo: QColor, tamanho_corpo: int = 10) -> None:
    """Um bloco de leitura: rotulo, filete e o texto com quebra de linha.

    O filete sob o rotulo e o que impede os tres blocos de lerem como um
    paragrafo unico solto no preto — e o mesmo recurso das faixas rotuladas
    das regioes vizinhas.
    """

    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    painter.drawLine(area.left(), area.top(), area.right(), area.top())
    painter.setPen(cor_titulo)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(QRect(area.left(), area.top() + 2, area.width(), 13),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     titulo)

    corpo_rect = QRect(area.left(), area.top() + ALTURA_TITULO_BLOCO,
                       area.width(), area.height() - ALTURA_TITULO_BLOCO)
    if corpo_rect.height() <= 6:
        return
    painter.setPen(cor_corpo)
    painter.setFont(tokens.fonte_ui(tamanho_corpo))
    painter.drawText(
        corpo_rect,
        int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            | Qt.TextFlag.TextWordWrap),
        corpo,
    )


def _desenhar_narracao(painter: QPainter, area: QRect, estado: EstadoNexo,
                       cor: QColor) -> None:
    """Faixa de NARRACAO — a frase que o locutor falou, em texto.

    O rotulo diz o estado do canal de audio (FALADO/VOZ MUDA) porque a mesma
    frase significa coisas diferentes conforme a voz esteja ligada: com
    ``FLUXOPRO_VOZ=1`` ela foi dita em voz alta; sem, ela e o que teria
    sido dito. Nunca afirma que falou quando o canal esta mudo.

    Em ``SEGURANDO`` a frase e marcada como ANUNCIO ANTERIOR e ganha uma
    ressalva explicita: ela afirma alinhamento das fontes, e o alinhamento
    ja caiu. Sem isso a regiao negaria o alinhamento na faixa de leitura e o
    reafirmaria duas faixas abaixo, pela voz.
    """

    frase = texto_narrado(estado)
    if frase is None:
        _desenhar_bloco_texto(
            painter, area, "NARRACAO",
            "Sem anuncio: o locutor so fala quando o filtro muda de estado, "
            "e ele nao esta aceso agora.",
            tema_asg.NEXO_MUTED, tema_asg.NEXO_MUTED, tamanho_corpo=9)
        return

    velha = narracao_desatualizada(estado)
    canal = "FALADO" if _VOZ_LIGADA else "VOZ MUDA"
    titulo = (f"NARRACAO · ANUNCIO ANTERIOR · {canal}" if velha
              else f"NARRACAO · {canal}")
    corpo = f"“{frase}”"
    if velha:
        corpo += ("\n\nEsta frase e do momento em que o filtro acendeu. As "
                  "condicoes mudaram desde entao — vale a leitura acima, nao "
                  "o alinhamento que ela afirma.")

    _desenhar_bloco_texto(painter, area, titulo, corpo,
                          tokens.ALERT if velha else cor,
                          tema_asg.NEXO_MUTED if velha else tema_asg.NEXO_TEXTO,
                          tamanho_corpo=9)


def _desenhar_linha_do_tempo(painter: QPainter, area: QRect,
                             estado: EstadoNexo, cor: QColor) -> None:
    """Trilho da histerese — a leitura do filtro no TEMPO.

    Divisao de escopo: o visor central mostra as condicoes NO INSTANTE; esta
    faixa mostra em que ponto do ciclo o filtro esta, que e a parte que
    nenhuma outra regiao conta e que explica o estado ``SEGURANDO``.

    Os dois numeros do trilho (janela de confirmacao e janela de desarme)
    saem de ``ConfigSinalUltra``, nunca digitados.

    NAO ha contagem regressiva: ``SinalUltraSnapshot`` nao publica o
    cronometro interno do motor (``_pendente_desde_ns``), entao qualquer
    "faltam 3s" aqui seria invencao. O trilho mostra a REGRA e a fase atual,
    que e o que o quadro realmente sabe.
    """

    fase = fase_do_filtro(estado)
    confirma = _CONFIG_REFERENCIA.persistencia_minima_ns / 1e9
    desarma = _CONFIG_REFERENCIA.tempo_para_desligar_ns / 1e9

    etapas = (
        (CONFIRMANDO, f"CONFIRMA {confirma:.0f}S"),
        (ARMADO, "ACESO"),
        (SEGURANDO, f"SEGURA ATE {desarma:.0f}S"),
    )

    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    painter.drawLine(area.left(), area.top(), area.right(), area.top())
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(QRect(area.left(), area.top() + 2, area.width(), 13),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "CICLO DO FILTRO")
    aceso = _tempo_aceso(estado)
    if aceso:
        painter.setPen(cor)
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
        painter.drawText(QRect(area.left(), area.top() + 2, area.width(), 13),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"ACESO {aceso}")

    trilho = QRect(area.left(), area.top() + 20, area.width(),
                   max(18, area.height() - 26))
    largura_etapa = trilho.width() // len(etapas)
    for indice, (nome, rotulo) in enumerate(etapas):
        celula = QRect(trilho.left() + indice * largura_etapa, trilho.top(),
                       largura_etapa - 4, trilho.height())
        ativa = nome == fase
        if ativa:
            fundo = QColor(cor)
            fundo.setAlpha(52)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fundo)
            painter.drawRect(celula)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(cor, 1))
            painter.drawRect(celula)
        else:
            painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(celula)
        # A etapa ativa nao se distingue so pela cor: leva um marcador de
        # forma, para sobreviver a `--sem-cor` e a impressao em cinza.
        painter.setPen(cor if ativa else tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(celula, Qt.AlignmentFlag.AlignCenter,
                         f"▶ {rotulo}" if ativa else rotulo)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """Console consultivo do OPERADOR IA — ver docstring do modulo."""

    if rect.width() < 70 or rect.height() < 70:
        return

    cor = cor_vies(estado)
    titulo_selo, sub_selo, cor_selo = _texto_selo(estado)

    compacto = (rect.width() < LARGURA_MIN_CONSOLE
                or rect.height() < ALTURA_MIN_CONSOLE)
    if compacto:
        # Sem espaco para o console: entrega o avatar e a leitura de vies,
        # que e o minimo honesto. Nunca versao "meio desenhada" com texto
        # sobreposto.
        raio = max(RAIO_MIN, min(RAIO_MAX, rect.width() // 4))
        _desenhar_avatar(painter, rect.center().x(),
                         rect.top() + raio + 14, raio, cor_selo)
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.setFont(tokens.fonte_numero(11, QFont.Weight.Bold))
        painter.drawText(QRect(rect.left(), rect.bottom() - 30, rect.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, "OPERADOR IA")
        painter.setPen(cor)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(QRect(rect.left(), rect.bottom() - 14, rect.width(), 13),
                         Qt.AlignmentFlag.AlignCenter,
                         _asg.rotulo_direcao(estado.snapshot.decisao.direcao))
        return

    _fundo_console(painter, rect)

    x = rect.left() + MARGEM
    largura = rect.width() - 2 * MARGEM
    y = rect.top() + 4

    # Medicao ANTES de pintar qualquer coisa: quanto os tres blocos de texto
    # realmente precisam, e quanta folga sobra para o cabecalho crescer.
    # O texto e medido com a largura util final, entao o que se mede aqui e
    # exatamente o que sera pintado depois.
    corpo_narracao = texto_narrado(estado)
    if corpo_narracao is None:
        corpo_narracao = ("Sem anuncio: o locutor so fala quando o filtro muda "
                          "de estado, e ele nao esta aceso agora.")
    naturais = (
        _altura_natural(painter, largura, " ".join(leitura_do_sinal(estado)), 10),
        _altura_natural(painter, largura, " ".join(observar_agora(estado)), 10),
        _altura_natural(painter, largura, corpo_narracao, 9) + (
            34 if narracao_desatualizada(estado) else 0),
    )
    altura_ciclo = (ALTURA_CICLO + VAO_BLOCO
                    if rect.height() >= ALTURA_MIN_LINHA_DO_TEMPO else 0)
    fixo = (4 + ALTURA_CABECALHO + 6 + ALTURA_SELO + 8 + altura_ciclo
            + 2 * VAO_BLOCO + ALTURA_RODAPE)
    folga_cabecalho = max(0, min(FOLGA_MAX_CABECALHO,
                                 rect.height() - fixo - sum(naturais)))

    # 1. Cabecalho — avatar + titulo + chip de voz.
    #
    # A altura do cabecalho e ELASTICA: ela recebe a folga que os blocos de
    # texto nao usaram (ver `_altura_natural`). Numa regiao alta isso vira o
    # avatar grande que o operador pediu ("um robo moderno") em vez de tres
    # paragrafos esticados com campo morto entre eles.
    altura_cabecalho = ALTURA_CABECALHO + folga_cabecalho
    raio_avatar = max(16, min(RAIO_MAX, (altura_cabecalho - 10) // 2))
    _desenhar_avatar(painter, x + raio_avatar + 12, y + altura_cabecalho // 2,
                     raio_avatar, cor_selo)

    texto_x = x + 2 * raio_avatar + 30
    centro = y + altura_cabecalho // 2
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.setFont(tokens.fonte_numero(15, QFont.Weight.Bold))
    painter.drawText(QRect(texto_x, centro - 17, largura - (texto_x - x) - 62, 18),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     "OPERADOR IA")
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.drawText(QRect(texto_x, centro + 2, largura - (texto_x - x) - 62, 13),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     "LEITURA CONSULTIVA · PROXY PROPRIO")

    chip = QRect(rect.right() - MARGEM - 58, y + 8, 58, 15)
    cor_chip = tokens.OK if _VOZ_LIGADA else tema_asg.NEXO_MUTED
    fundo_chip = QColor(cor_chip)
    fundo_chip.setAlpha(38)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fundo_chip)
    painter.drawRect(chip)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(cor_chip)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(chip, Qt.AlignmentFlag.AlignCenter,
                     "VOZ ATIVA" if _VOZ_LIGADA else "VOZ MUDA")

    y += altura_cabecalho + 6

    # 2. Selo de estado do Ultra.
    _desenhar_selo(painter, QRect(x, y, largura, ALTURA_SELO),
                   titulo_selo, sub_selo, cor_selo)
    y += ALTURA_SELO + 8

    # 3. Ciclo do filtro no tempo — so cabe na regiao alta (a partir de
    # 28/08/2026, quando `vies` passou a colar no rodape do visor). Se a
    # regiao encolher, esta faixa e a primeira a sair: ela e a que menos
    # perde por estar ausente, porque as duas frases de leitura abaixo ja
    # descrevem a histerese em texto.
    if rect.height() >= ALTURA_MIN_LINHA_DO_TEMPO:
        _desenhar_linha_do_tempo(painter, QRect(x, y, largura, ALTURA_CICLO),
                                 estado, cor_selo)
        y += ALTURA_CICLO + VAO_BLOCO

    # 4-6. Os tres blocos de texto. Cada um pede a altura que o SEU texto
    # precisa (`_altura_natural`); o que sobrar depois disso ja foi para o
    # cabecalho la em cima, entao nao ha campo morto nem paragrafo esticado.
    topo_rodape = rect.bottom() - ALTURA_RODAPE
    disponivel = topo_rodape - y - 2 * VAO_BLOCO
    if disponivel > 3 * (ALTURA_TITULO_BLOCO + 8):
        alturas = list(naturais)
        # Se o texto pedir mais do que cabe (regiao curta, fonte grande),
        # os blocos encolhem proporcionalmente em vez de o ultimo ser
        # empurrado para fora do quadro.
        excesso = sum(alturas) - disponivel
        if excesso > 0:
            for indice in range(3):
                alturas[indice] = max(
                    ALTURA_TITULO_BLOCO + 12,
                    alturas[indice] - round(excesso * PESOS_BLOCOS[indice]),
                )
        else:
            # A folga que sobrou depois do teto do cabecalho vira respiro
            # igual entre os blocos.
            for indice in range(3):
                alturas[indice] += (-excesso) // 3

        _desenhar_bloco_texto(
            painter, QRect(x, y, largura, alturas[0]),
            "O QUE ESTE SINAL DIZ", " ".join(leitura_do_sinal(estado)),
            cor_selo, tema_asg.NEXO_TEXTO,
        )
        y += alturas[0] + VAO_BLOCO

        _desenhar_bloco_texto(
            painter, QRect(x, y, largura, alturas[1]),
            "O QUE OBSERVAR AGORA", " ".join(observar_agora(estado)),
            tema_asg.NEXO_MUTED, tema_asg.NEXO_TEXTO,
        )
        y += alturas[1] + VAO_BLOCO

        _desenhar_narracao(painter, QRect(x, y, largura, alturas[2]),
                           estado, cor_selo)

    # 5. Rodape — vies do quadro em texto+glifo (a leitura nao pode depender
    # so do canal de cor) e a ressalva permanente de que nada aqui e ordem.
    rodape = rect.bottom() - ALTURA_RODAPE
    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    painter.drawLine(x, rodape, x + largura, rodape)
    painter.setPen(cor)
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
    painter.drawText(QRect(x, rodape + 3, largura, 12),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     _asg.rotulo_direcao(estado.snapshot.decisao.direcao))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(QRect(x, rodape + 3, largura, 12),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     "NAO E ORDEM · NAO E RECOMENDACAO")
