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

import math
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


def fase_do_filtro_de_sinal(ultra: object | None) -> str:
    """A mesma resolucao de `fase_do_filtro`, mas recebendo so o
    `SinalUltraSnapshot` — nao o `EstadoNexo` inteiro.

    Existe porque `asg.py` precisa desta fase para decidir quando a VOZ
    anuncia perda/retomada de alinhamento (achado de auditoria, 28/08/2026:
    "a voz nao anuncia a perda de alinhamento do Ultra"), e o painel nao tem
    um `EstadoNexo` pronto no momento em que processa cada quadro — so o
    snapshot do motor. Construir um `EstadoNexo` inteiro so para chamar esta
    funcao exigiria preencher 8 campos obrigatorios que nao tem relacao
    nenhuma com o Ultra. `fase_do_filtro` delega para aqui, entao continua
    havendo UM SO lugar que decide "armado" vs "segurando".
    """

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


def fase_do_filtro(estado: EstadoNexo) -> str:
    """Em que ponto da histerese o filtro esta neste quadro.

    Ponto unico de resolucao: selo, leitura, narracao e linha do tempo saem
    todos daqui, para nao existir a chance de uma faixa da regiao dizer
    "armado" enquanto a vizinha diz "segurando".
    """

    return fase_do_filtro_de_sinal(estado.sinal_ultra)


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
    """`True` quando a fase pede tratamento de AVISO na faixa de narracao,
    em vez do anuncio normal de "armado".

    ATE 28/08/2026 (auditoria pos-entrega) isto significava literalmente
    "a frase mostrada ficou velha": em ``SEGURANDO`` a regiao repetia a
    frase de ARMADO ("as fontes concordam"), que ja nao era verdade, e esta
    funcao So existia para acrescentar a ressalva por cima da mentira.

    Desde a correcao (`voz.texto_para_perda_de_alinhamento`, gatilho novo em
    `asg._atualizar_sinal_ultra`) o locutor passou a falar uma frase PROPRIA
    para ``SEGURANDO`` — nao mais a de ARMADO — e ``texto_narrado`` a segue.
    A frase mostrada deixou de ser antiga; continua sendo um AVISO
    (o selo pode encerrar a qualquer momento), e e por isso que a faixa
    ainda pede destaque — so que por ser importante agora, nao por estar
    desatualizada.
    """

    return fase_do_filtro(estado) == SEGURANDO


def texto_narrado(estado: EstadoNexo) -> str | None:
    """A frase EXATA que o locutor falou neste estado, ou ``None``.

    Sai de ``voz`` — as MESMAS funcoes que alimentam o ``LocutorASG``
    (`texto_para_transicao_ultra` para ARMADO/encerrado,
    `texto_para_perda_de_alinhamento` para SEGURANDO). Redigir uma segunda
    versao aqui faria a tela e o audio divergirem em silencio, que era
    justamente o defeito antes desta funcao existir.

    CORRIGIDO em 28/08/2026 (auditoria pos-entrega, "a voz nao anuncia a
    perda de alinhamento"): antes, em ``SEGURANDO``, esta funcao devolvia a
    MESMA frase de ARMADO ("as fontes concordam"), porque o locutor ainda
    nao tinha uma frase propria para esse estado — e a regiao cobria a
    mentira com a ressalva de ``narracao_desatualizada``. Agora o locutor
    realmente fala uma frase diferente ao ENTRAR em SEGURANDO, e esta funcao
    devolve ela — nao mais o texto de ARMADO reciclado.

    Sem filtro aceso nao houve anuncio, e a funcao devolve ``None`` em vez
    de inventar uma fala.
    """

    ultra = estado.sinal_ultra
    if ultra is None or ultra.direcao is DirecaoUltra.NENHUMA:
        return None
    if fase_do_filtro(estado) == SEGURANDO:
        return _voz.texto_para_perda_de_alinhamento(ultra.direcao)
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


PERIODO_ROTACAO_DIAL_NS = 24_000_000_000
"""Uma volta do dial (tracejado + escala radial) a cada 24s — mesmo periodo
do anel externo do ``jarvis_hud_demo.html`` de referencia (``.ring``,
``animation-duration``)."""
PERIODO_ROTACAO_TRACEJADO_NS = 34_000_000_000
"""O tracejado gira mais devagar e no sentido OPOSTO ao dial — mesma
contra-rotacao da referencia (``.ring.r2``, 34s, ``animation-direction:
reverse``); e o que separa visualmente as duas camadas em vez de girarem
juntas como um bloco so."""


def _fase(timestamp_ns: int, periodo_ns: int) -> float:
    """Fracao 0..1 do ciclo em que ``timestamp_ns`` cai. Funcao PURA."""

    if periodo_ns <= 0 or timestamp_ns <= 0:
        return 0.0
    return (timestamp_ns % periodo_ns) / periodo_ns


EXTENSAO_ANEIS = 1.38
"""Quanto o casco de anéis avança ALÉM do raio do núcleo do avatar.

Público de propósito: quem faz o layout precisa reservar a extensão REAL
do desenho, não o raio do núcleo. Defeito medido em 31/08/2026 — o
cabeçalho reservava `raio` e posicionava o texto logo depois, mas o casco
ia até `raio * 1,38`: o anel cruzava por cima do "OPERADOR IA" e ainda
saía cortado em cima e embaixo, porque a altura também fora dimensionada
pelo núcleo."""


def _desenhar_aneis_reator(painter: QPainter, cx: int, cy: int, raio: int,
                           cor_anel: QColor, timestamp_ns: int) -> None:
    """Aneis concentricos do "reator" ao redor do nucleo — reforma de
    31/08/2026 a partir de referencia trazida pelo operador
    (``jarvis-operador-b3-3d-4k.png`` / ``jarvis_hud_demo.html``, pasta
    Codex): a esfera lisa ganhou casco de aneis, escala radial e o anel de
    estado com "glow" simulado, no espirito da referencia (nucleo brilhante
    cercado de aneis e marcacao de dial). Geometria propria do QPainter —
    nenhum pixel do PNG/HTML de referencia e usado como asset, mesma regra
    que ja valia para a esfera (ver docstring de `_desenhar_avatar`).

    Anima girando o dial e o tracejado (pedido explicito do operador,
    31/08/2026, revendo a decisao original de nao animar) — mas SEM QTimer
    novo: o angulo e uma funcao PURA de ``timestamp_ns``, o mesmo relogio de
    mercado que ja alimenta o pulso do selo Ultra em `nucleo.py`. O NEXO so
    redesenha quando a ponte entrega um retrato novo (ver docstring de
    `painel_denso.py`) — reaproveitar esse relogio anima em qualquer sessao
    com negocios fluindo (a cadencia normal, varias vezes por segundo) SEM
    adicionar um unico quadro que o painel nao fosse desenhar de qualquer
    jeito. O preco: a rotacao PARA se o feed parar (mercado fechado,
    replay pausado) — trade-off aceito porque o produto ja e "redesenha por
    evento", nunca por relogio de UI, e criar a excecao so para um enfeite
    contradiria essa regra em todo o resto do arquivo.

    O casco solido (aro liso) NAO gira: um circulo uniforme e simetrico por
    rotacao, entao girá-lo nao muda um pixel — so o tracejado e o dial (que
    tem padrao angular) mostram movimento de verdade.

    Cor: os aneis decorativos (casco solido, tracejado, dial) ficam em
    CROMO NEUTRO (`NEXO_IDENTIDADE_ANEL`/`NEXO_MUTED`) — a mesma regra que
    ja regia a esfera ("cromo neutro de proposito, o mesmo ciano/verde ja
    carrega outros papeis no quadro"). So o anel de ESTADO usa `cor_anel`:
    pintar o casco decorativo em azul/vermelho saturado (como a referencia)
    duplicaria um papel que `NEXO_CIANO`/`NEXO_ROSA` ja carregam em outras
    regioes — exatamente o defeito que o auditor de coerencia deste projeto
    ja flagrou uma vez, no disco de identidade (`tema_asg.py`, bloco
    "Round 2/3").
    """

    chrome = tema_asg.NEXO_IDENTIDADE_ANEL
    centro = QPointF(cx, cy)

    # Casco: aro solido de chrome — o "corpo" do reator, sempre visivel,
    # nunca rotacionado (ver docstring: simetrico, girar nao muda nada).
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(chrome, 2))
    painter.drawEllipse(centro, raio * EXTENSAO_ANEIS, raio * EXTENSAO_ANEIS)

    # Abaixo de ~24px de raio (avatar comprimido, console estreito) o dial e
    # o tracejado viram ruido de subpixel em vez de leitura — degrau honesto
    # e nao desenhar, nao um traco que so pisca ao redimensionar.
    if raio >= 24:
        painter.save()
        painter.translate(centro)
        painter.rotate(_fase(timestamp_ns, PERIODO_ROTACAO_TRACEJADO_NS) * -360.0)
        painter.setPen(QPen(chrome, 1, Qt.PenStyle.DashLine))
        painter.drawEllipse(QPointF(0, 0), raio * 1.22, raio * 1.22)
        painter.restore()

        # Escala radial (dial): a marcacao que a referencia poe nos trilhos
        # laterais, condensada num anel em volta do nucleo. A fase desloca o
        # angulo de PARTIDA de cada traco — gira o dial inteiro sem precisar
        # de uma segunda transformacao de matriz.
        painter.setPen(QPen(tema_asg.NEXO_MUTED, 1))
        n_tracos = 40
        raio_ext, raio_int = raio * 1.12, raio * 1.06
        fase_dial = _fase(timestamp_ns, PERIODO_ROTACAO_DIAL_NS) * 2 * math.pi
        for indice in range(n_tracos):
            angulo = 2 * math.pi * indice / n_tracos + fase_dial
            seno, cosseno = math.sin(angulo), math.cos(angulo)
            painter.drawLine(
                QPointF(cx + raio_ext * cosseno, cy + raio_ext * seno),
                QPointF(cx + raio_int * cosseno, cy + raio_int * seno),
            )

    # Anel de ESTADO com "glow": tracos concentricos decrescentes em
    # largura e crescentes em opacidade — o QPainter deste backing store
    # nao tem blur barato, entao o halo e simulado empilhando o mesmo
    # circulo em vez de desenhar um so traco chapado. Tambem simetrico:
    # nao gira, pelo mesmo motivo do casco.
    for largura, alpha in ((7, 40), (4, 95), (2, 255)):
        cor_halo = QColor(cor_anel.red(), cor_anel.green(), cor_anel.blue(), alpha)
        painter.setPen(QPen(cor_halo, largura))
        painter.drawEllipse(centro, raio + 4, raio + 4)


def _desenhar_nucleo_reator(painter: QPainter, cx: int, cy: int, raio: int,
                            cor: QColor, timestamp_ns: int) -> None:
    """Miolo do avatar: núcleo de reator (referência do operador), no lugar
    do visor-com-fresta que havia até 31/08/2026.

    O pedido de 30/08 era "trocar essa imagem do OPERADOR B3" pela do
    reator (``jarvis-operador-b3-3d-4k.png``). A passada anterior só pôs
    ANÉIS em volta e manteve o miolo antigo — uma fresta horizontal com
    dois segmentos acesos que, do lado de fora, continuava lendo como um
    rosto. Aqui o centro passa a ser o que a referência mostra: um poço
    escuro, pás radiais girando, e um núcleo aceso com halo.

    Geometria autoral em QPainter — nenhum pixel do PNG de referência
    entra como asset, mesma regra do resto do arquivo. Gira pelo relógio
    de MERCADO (`timestamp_ns`), sem QTimer novo, igual a
    `_desenhar_aneis_reator`.
    """

    # Poço: cavidade escura onde o núcleo assenta — dá o degrau de
    # profundidade que faz o miolo parecer embutido, não colado por cima.
    poco = QRadialGradient(QPointF(cx, cy), raio * 0.72)
    poco.setColorAt(0.0, QColor(0, 0, 0, 210))
    poco.setColorAt(1.0, QColor(0, 0, 0, 90))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(poco)
    painter.drawEllipse(QPointF(cx, cy), raio * 0.72, raio * 0.72)

    # Pás radiais (a turbina do reator). Giram no sentido oposto ao dial
    # externo, que é o que dá a leitura de "mecanismo" em vez de enfeite.
    if raio >= 18:
        painter.save()
        painter.translate(QPointF(cx, cy))
        painter.rotate(_fase(timestamp_ns, PERIODO_ROTACAO_DIAL_NS) * 360.0)
        pa = QColor(cor)
        pa.setAlpha(70)
        painter.setPen(QPen(pa, max(1, raio // 14)))
        for indice in range(8):
            angulo = 2 * math.pi * indice / 8
            seno, cosseno = math.sin(angulo), math.cos(angulo)
            painter.drawLine(
                QPointF(raio * 0.30 * cosseno, raio * 0.30 * seno),
                QPointF(raio * 0.64 * cosseno, raio * 0.64 * seno),
            )
        painter.restore()

    # Anel interno de contencao.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    aro = QColor(cor)
    aro.setAlpha(150)
    painter.setPen(QPen(aro, max(1, raio // 18)))
    painter.drawEllipse(QPointF(cx, cy), raio * 0.30, raio * 0.30)

    # Nucleo aceso + halo: mesmo empilhamento de `_desenhar_aneis_reator`
    # (este backing store nao tem blur barato).
    for fracao, alpha in ((0.30, 45), (0.20, 95), (0.11, 220)):
        halo = QColor(cor.red(), cor.green(), cor.blue(), alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(cx, cy), raio * fracao, raio * fracao)
    nucleo = QColor(255, 255, 255, 210)
    painter.setBrush(nucleo)
    painter.drawEllipse(QPointF(cx, cy), raio * 0.05, raio * 0.05)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _desenhar_avatar(painter: QPainter, cx: int, cy: int, raio: int,
                     cor_anel: QColor, timestamp_ns: int = 0) -> None:
    """Avatar do OPERADOR IA — geometria autoral (nunca a foto/render de
    terceiro dos prints de referencia): reator com aneis (`_desenhar_aneis_
    reator`), esfera com luz fora de eixo, sombra projetada, especular,
    visor e brackets de mira.

    A profundidade da esfera vem de tres camadas empilhadas, nao de um
    gradiente linear chapado: sombra elíptica abaixo, gradiente RADIAL
    deslocado do centro (uma esfera iluminada de verdade tem o brilho fora
    do centro) e um especular translucido no ponto onde a luz bate.

    ``timestamp_ns`` e o relogio do QUADRO (`estado.snapshot.timestamp_ns`),
    nunca um relogio de UI proprio — e o que faz os aneis girarem (ver
    `_desenhar_aneis_reator`). Default `0` deixa os aneis parados (fase 0)
    para quem chama sem relogio disponivel (montagem antiga/teste).
    """

    sombra = QColor(tema_asg.NEXO_IDENTIDADE_ANEL)
    sombra.setAlpha(50)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(sombra)
    painter.drawEllipse(QPointF(cx, cy + raio * 0.75), raio * 0.8, raio * 0.22)

    _desenhar_aneis_reator(painter, cx, cy, raio, cor_anel, timestamp_ns)

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

    _desenhar_nucleo_reator(painter, cx, cy, raio, cor_anel, timestamp_ns)

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


def _numero_finito(valor: object) -> float | None:
    """Converte um valor publico do snapshot sem inventar dado ausente."""

    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _forca_do_objeto(objeto: object | None) -> float | None:
    if objeto is None:
        return None
    for nome in ("composite", "forca", "pontuacao", "score"):
        valor = _numero_finito(getattr(objeto, nome, None))
        if valor is not None:
            return max(-1.0, min(1.0, valor))
    return None


def _confianca_do_objeto(objeto: object | None) -> float | None:
    """Retorna confiança 0..1 de linha Maker/feed, quando disponível."""

    if objeto is None:
        return None
    valor = _numero_finito(getattr(objeto, "confianca", None))
    if valor is not None:
        return max(0.0, min(1.0, valor if valor <= 1.0 else valor / 100.0))
    rotulo = str(getattr(getattr(objeto, "confianca", None), "value", "")).upper()
    return {"CONF ALTA": 1.0, "CONF MEDIA": 0.65, "CONF BAIXA": 0.35}.get(rotulo)


def _metricas_reator(estado: EstadoNexo) -> tuple[tuple[str, float | None, QColor], ...]:
    """Métricas honestas para o HUD compacto do núcleo.

    A prioridade é: dominância composta, Maker, regime e confiança do feed.
    Cada valor continua vindo do snapshot imutável; quando a fonte não
    publica o campo, o HUD mostra ``—`` em vez de estimar ou reutilizar um
    número de outro painel.
    """

    dominancia = _forca_do_objeto(estado.dominancia_snapshot)
    maker = _forca_do_objeto(estado.maker)
    regime = _forca_do_objeto(estado.regime)
    forca = dominancia if dominancia is not None else maker
    if forca is None:
        forca = regime
    confianca = _confianca_do_objeto(estado.maker)
    if confianca is None:
        dados = getattr(estado.snapshot, "dados", None)
        confianca = _confianca_do_objeto(dados)
    cor_forca = estado.paleta.compra if (forca or 0.0) >= 0 else estado.paleta.venda
    cor_maker = estado.paleta.compra if (maker or 0.0) >= 0 else estado.paleta.venda
    return (
        ("FORÇA", forca, cor_forca),
        ("MAKER", maker, cor_maker),
        ("CONF", confianca, tema_asg.NEXO_CIANO),
    )


def _desenhar_barra_reator(painter: QPainter, area: QRect, rotulo: str,
                           valor: float | None, cor: QColor) -> None:
    """Barra pequena com valor textual: o HUD não depende apenas de cor."""

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(area.left(), area.top(), 42, area.height()),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     rotulo)
    trilho = QRect(area.left() + 44, area.top() + 4,
                   max(16, area.width() - 80), max(6, area.height() - 8))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_GRADE)
    painter.drawRoundedRect(trilho, 3, 3)
    if valor is not None:
        intensidade = abs(valor) if rotulo != "CONF" else valor
        preenchido = QRect(trilho.left(), trilho.top(),
                           max(2, int(round(trilho.width() * intensidade))),
                           trilho.height())
        preenchido.setLeft(trilho.right() - preenchido.width() + 1
                           if valor < 0 and rotulo != "CONF" else trilho.left())
        painter.setBrush(cor)
        painter.drawRoundedRect(preenchido, 3, 3)
        texto = (f"{valor:+.0%}" if rotulo != "CONF" else f"{valor:.0%}")
    else:
        texto = "—"
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(cor if valor is not None else tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    painter.drawText(QRect(area.right() - 34, area.top(), 34, area.height()),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     texto)


def _desenhar_hud_compacto(painter: QPainter, rect: QRect, estado: EstadoNexo,
                           cor_selo: QColor) -> None:
    """Versão compacta: o avatar passa a ser um HUD funcional, não ornamento."""

    _fundo_console(painter, rect)
    margem = 8
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.setFont(tokens.fonte_numero(10, QFont.Weight.Bold))
    painter.drawText(QRect(rect.left() + margem, rect.top() + 5,
                           rect.width() - 2 * margem, 14),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "NEXO AI")
    fase = fase_do_filtro(estado)
    fase_rotulo = {
        AUSENTE: "MOTOR AUSENTE", ARMADO: "ARMADO", SEGURANDO: "SEGURANDO",
        CONFIRMANDO: "CONFIRMANDO", SEM_SINAL: "AGUARDAR",
    }.get(fase, "AGUARDAR")
    painter.setPen(cor_selo)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(QRect(rect.left() + margem, rect.top() + 19,
                           rect.width() - 2 * margem, 12),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     fase_rotulo)

    raio = max(16, min(RAIO_MAX, int(min(rect.width() * 0.23, rect.height() * 0.20))))
    _desenhar_avatar(painter, rect.center().x(), rect.top() + 42, raio,
                     cor_selo, getattr(estado.snapshot, "timestamp_ns", 0))

    base = rect.top() + 58 + int(raio * EXTENSAO_ANEIS)
    altura_barra = 16
    for indice, (rotulo, valor, cor) in enumerate(_metricas_reator(estado)):
        topo = base + indice * altura_barra
        if topo + altura_barra > rect.bottom() - 22:
            break
        _desenhar_barra_reator(painter, QRect(rect.left() + margem, topo,
                                              rect.width() - 2 * margem,
                                              altura_barra), rotulo, valor, cor)

    painter.setPen(tema_asg.NEXO_MUTED)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.drawText(QRect(rect.left() + margem, rect.bottom() - 16,
                           rect.width() - 2 * margem, 12),
                     Qt.AlignmentFlag.AlignCenter,
                     "LEITURA CONSULTIVA · SEM ORDENS")


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

    CORRIGIDO em 28/08/2026: em ``SEGURANDO`` esta faixa reciclava a frase
    de ARMADO ("as fontes concordam", ja falsa) sob o rotulo "ANUNCIO
    ANTERIOR" — a unica forma de nao mentir era avisar que a propria frase
    mostrada estava desatualizada. Agora ``texto_narrado`` devolve a frase
    NOVA que o locutor realmente fala ao entrar em SEGURANDO
    (`voz.texto_para_perda_de_alinhamento`), que ja e o aviso em si — nao
    ha mais nada "anterior" para ressalvar. A faixa continua com destaque
    (`tokens.ALERT`) por ser importante, nao por estar velha.
    """

    frase = texto_narrado(estado)
    if frase is None:
        _desenhar_bloco_texto(
            painter, area, "NARRACAO",
            "Sem anuncio: o locutor so fala quando o filtro muda de estado, "
            "e ele nao esta aceso agora.",
            tema_asg.NEXO_MUTED, tema_asg.NEXO_MUTED, tamanho_corpo=9)
        return

    aviso = narracao_desatualizada(estado)
    canal = "FALADO" if _VOZ_LIGADA else "VOZ MUDA"
    titulo = f"NARRACAO · AVISO · {canal}" if aviso else f"NARRACAO · {canal}"
    corpo = f"“{frase}”"

    _desenhar_bloco_texto(painter, area, titulo, corpo,
                          tokens.ALERT if aviso else cor,
                          tema_asg.NEXO_TEXTO,
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
        # Mesmo em coluna estreita, o núcleo entrega estado e força resumidos;
        # ele deixa de ser uma esfera decorativa sem sacrificar a honestidade
        # do snapshot. O console completo continua sendo usado quando há área.
        _desenhar_hud_compacto(painter, rect, estado, cor_selo)
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
    # O raio do NUCLEO sai da altura disponivel ja descontando o casco de
    # aneis (`EXTENSAO_ANEIS`) — dimensionar pelo nucleo fazia o casco
    # estourar o cabecalho em cima/embaixo e invadir o texto a direita.
    raio_avatar = max(12, min(RAIO_MAX,
                              int((altura_cabecalho - 10) / (2 * EXTENSAO_ANEIS))))
    extensao_avatar = int(round(raio_avatar * EXTENSAO_ANEIS))
    _desenhar_avatar(painter, x + extensao_avatar + 12, y + altura_cabecalho // 2,
                     raio_avatar, cor_selo,
                     getattr(estado.snapshot, "timestamp_ns", 0))

    texto_x = x + 2 * extensao_avatar + 26
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

        # 31/08/2026 — "O QUE OBSERVAR AGORA" e a NARRACAO cederam o espaco
        # para a ANALISE DE MERCADO do Claude (pedido do operador: "uma
        # interpretacao geral do mercado e uma analise explicando conforme
        # os dados que a interface oferece").
        #
        # Os dois blocos aposentados diziam SEMPRE a mesma coisa enquanto o
        # filtro Ultra estivesse apagado — que e a maior parte do pregao,
        # por construcao do proprio filtro: "Nenhum alinhamento agora..." e
        # "Sem anuncio: o locutor so fala quando o filtro muda de estado".
        # Dois blocos de texto fixo ocupando 2/3 da altura util da regiao.
        #
        # "O QUE ESTE SINAL DIZ" fica: ele explica o FILTRO (por que o Ultra
        # esta ou nao aceso), que e uma pergunta diferente da leitura de
        # mercado e nao sai do lado esquerdo da tela.
        from fluxopro.ui.paineis.nexo import analise as _analise_ui

        altura_analise = alturas[1] + alturas[2] + VAO_BLOCO
        _desenhar_bloco_texto(
            painter, QRect(x, y, largura, alturas[0]),
            "O QUE ESTE SINAL DIZ", " ".join(leitura_do_sinal(estado)),
            cor_selo, tema_asg.NEXO_TEXTO,
        )
        y += alturas[0] + VAO_BLOCO

        _analise_ui.desenhar_analise(
            painter, QRect(x, y, largura, altura_analise),
            getattr(estado, "analise_ia", None),
        )

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
