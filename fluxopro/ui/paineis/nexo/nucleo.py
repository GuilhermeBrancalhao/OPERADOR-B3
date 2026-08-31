"""Regiao NUCLEO — visor central + painel do filtro ULTRA (x 0,40-0,63 · y 0,02-0,42).

Achado do operador (26/08/2026, MUDANCAS E IMPLEMENTACOES.docx, item 1): o
visor estava "feio, muito simples, longe do padrao" e sobretudo "nao esta
funcional, pois nunca apareceu nada" a respeito do Sinal Ultra.

O diagnostico, olhando o retrato: a regiao e a MAIOR da tela e era a que menos
informava — um octogono vazio com um losango de contorno, a hora, tres cartoes
curtos e a legenda "SEM DECISAO". O Ultra so tinha DOIS estados visuais
(aceso / apagado), entao enquanto ele nao disparava — que e quase sempre, por
construcao — a regiao nao dizia nada sobre ele. "Nunca apareceu nada" era
literalmente verdade: nao havia o que aparecer.

O que esta regiao passa a mostrar, sem tocar na semantica do motor:

1. **O visor** — mesma silhueta assimetrica, agora com profundidade real
   (sombra projetada, corpo em degrade vertical, brilho de bisel no topo,
   halo interno na cor da direcao) e o glifo EXTRUDADO em tres camadas, a
   mesma linguagem do prisma 3D do MakerProxy na regiao vizinha.
2. **O painel de CONDICOES do filtro ULTRA** — as quatro condicoes de
   `fluxopro.asg.sinal_ultra` (decisao confirmada, Renko em TENDENCIA na
   mesma direcao, MakerProxy forte, confianca do Maker ALTA), cada uma com
   sua lampada e o valor medido ao lado. Sao os "padroes bem definidos" que
   o operador pediu, tornados visiveis: quando o Ultra nao acende, a tela
   diz QUAL condicao faltou.
3. **A faixa de estado do ULTRA** — tres leituras distintas, nunca duas:
   ``ULTRA <direcao>`` (ligado, apos a histerese), ``CONFLUENCIA 4/4 ·
   CONFIRMANDO`` (a confluencia crua fecha agora mas ainda nao cumpriu a
   janela de persistencia) e ``ULTRA INATIVO · k/4``. A distincao entre a
   segunda e a primeira e exatamente a histerese que existe para o Ultra
   "nao acender toda hora" — mostra-la e o que faz a raridade parecer
   projeto em vez de defeito.

Honestidade de estado: nada aqui inventa sinal para preencher espaco. Sem
decisao, o visor diz "SEM DECISAO" e as lampadas ficam apagadas; sem
``estado.sinal_ultra`` (montagem antiga/teste), a faixa diz "ULTRA
INDISPONIVEL" em vez de fingir "inativo".

O visor **nao e um botao**: sem hover, sem pressed, sem callback — apenas
``desenhar(painter, rect, estado)``, funcao pura, uma vez por quadro. O glifo
tem tres leituras com silhuetas proprias (seta solida = direcao confirmada,
losango vazado = aguardando, laco = equilibrio), entao o visor nunca fica com
o desenho de "COMPRA" quando nao ha sinal algum.

Produto CONSULTIVO: nem o selo do Ultra nem o painel de condicoes e convite a
operar — a ressalva do rodape do quadro continua valendo e o rotulo do Ultra
diz "FILTRO ADICIONAL", nao "entrada".
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygon,
    QRadialGradient,
)

from fluxopro.analytics.renko import FaseRenko
from fluxopro.asg.sinal_ultra import ConfigSinalUltra, DirecaoUltra
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import vies as _vies

# Configuracao de ULTIMO RECURSO, usada so quando nao ha snapshot do motor
# neste quadro (`estado.sinal_ultra is None`: montagem antiga ou teste).
#
# Havendo snapshot, todo numero exibido — limiar do Maker e janela da
# histerese — vem de `SinalUltraSnapshot.config`/`janela_alvo_ns`, isto e, da
# instancia do motor que de fato decidiu. Uma `ConfigSinalUltra()` construida
# aqui acerta por COINCIDENCIA enquanto ninguem passar configuracao
# customizada ao motor, e passa a mentir em silencio no dia em que alguem
# passar; e o mesmo defeito de procedencia que
# `tests/test_ui_footprint.py::TestProcedencia` existe para tornar impossivel
# em outra fase, e ele esta amarrado por teste de mutacao em
# `tests/test_ui_nexo_nucleo.py`.
#
# Rotulo: IMPRECISO — os limiares em si sao proxy de engenharia deste projeto
# (o "Sinal Ultra" da fonte original e AUSENTE_NA_FONTE, ver docstring de
# `fluxopro/asg/sinal_ultra.py`). O que e CONFIRMADO e apenas que o numero
# mostrado e o mesmo que o motor aplicou.
_CONFIG_PADRAO = ConfigSinalUltra()


def _config_do_quadro(ultra) -> ConfigSinalUltra:
    """A configuracao que o motor usou neste quadro, ou o padrao se nao houver."""

    config = getattr(ultra, "config", None)
    return config if config is not None else _CONFIG_PADRAO


# Barra de confirmacao/histerese: altura do trilho e recuo lateral, dentro da
# faixa de estado do Ultra.
ALTURA_BARRA_JANELA = 3

RAIO_MIN = 24
RAIO_MAX = 96

# Glifo de AGUARDAR/NEUTRA (losango/laco): um semi-eixo por direcao, porque o
# bisel do visor e bem mais largo que alto (assimetria de proposito, ver
# `_silhueta_visor`) e um raio unico ou fica curto na largura ou estoura a
# altura. Faixa 55%-75% de cada eixo util — nem glifo perdido no vazio nem
# glifo atropelando a moldura.
FRACAO_GLIFO_LARGURA = 0.62
FRACAO_GLIFO_ALTURA = 0.70

# Seta de COMPRA/VENDA: triangulo de angulo de apice FIXO, largura como fracao
# da largura util. A altura decorre da largura pelo angulo — nunca um segundo
# raio calibrado a parte, que deixaria a ponta ora gorda ora fina conforme a
# proporcao do bisel muda.
FRACAO_SETA_LARGURA = 0.46
# 78 graus, e nao os 51 da primeira passada: com apice estreito a seta fica
# ALTA (altura ~2,1x a meia-base) e, num bisel cujo topo e cortado em chanfro
# fundo, a unica forma de faze-la caber e encolher a largura — sobrava campo
# escuro dos dois lados e a ponta ainda encostava na moldura. Um apice largo da
# uma cunha baixa e larga, que e a forma que casa com a silhueta do visor e
# com a leitura de "direcao" de um terminal de fluxo.
ANGULO_APICE_SETA_GRAUS = 78.0

# Profundidade do glifo extrudado, em pixels de deslocamento por camada. Tres
# camadas (sombra, corpo escurecido, face) e a menor contagem que ainda le
# como volume; duas leem como contorno mal alinhado.
CAMADAS_EXTRUSAO = 3
PASSO_EXTRUSAO = 2

# Deslocamento da sombra projetada da moldura (luz vinda de cima).
SOMBRA_DY = 3

# Cartoes de rodape: tres linhas cada (rotulo / valor / o que o campo E).
# A terceira linha nao e enfeite — os tres rotulos eram siglas mudas
# ("REGIME", "CONFIANCA", "EVID.") sem explicacao em lugar nenhum da tela.
ALTURA_CARTAO = 38
VAO_CARTAO = 3

# Faixa do cabecalho (titulo da regiao + carimbo de tempo do quadro).
ALTURA_CABECALHO = 14

# Painel de condicoes do Ultra: uma linha por condicao, mais o cabecalho.
LINHAS_CONDICAO = 4
ALTURA_LINHA_CONDICAO = 20
ALTURA_TITULO_CONDICOES = 16

# Faixa de estado do Ultra (a leitura grande: ATIVO / CONFIRMANDO / INATIVO).
ALTURA_FAIXA_ULTRA = 30

TRACO_FINO = 1
TRACO_GLIFO = 2

# Bisel do topo e da base, como fracao do lado menor: o topo e bem mais fundo
# que a base de proposito — silhueta de posto de leitura, nao de tecla.
BISEL_TOPO_DIV = 3
BISEL_BASE_DIV = 8

BRACO_CANTO_DIV = 8
RECUO_CONTORNO = 4

_FAIXA_POR_DIRECAO = {
    _asg.DirecaoASG.COMPRA: tema_asg.NEXO_VERDE_FAIXA,
    _asg.DirecaoASG.VENDA: tema_asg.NEXO_ROSA_FAIXA,
    _asg.DirecaoASG.AGUARDAR: tema_asg.FUNDO_ALERTA,
    _asg.DirecaoASG.NEUTRA: tema_asg.NEXO_CIANO_FAIXA,
}

# ==========================================================================
# Leitura do glifo central — 31/08/2026
# ==========================================================================
# Achado do operador: o visor so distinguia COMPRA/VENDA/NEUTRA/AGUARDAR (a
# direcao "crua" da decisao). Faltavam duas leituras que o resto do motor JA
# calcula mas o glifo nunca mostrava: (1) o Sinal Ultra armado — a leitura de
# MAIOR confianca do produto, hoje so um anel fino sobre a mesma seta — e (2)
# um alerta de ALTO RISCO para "o mercado bateu de lado agora, sem direcao" —
# que ate aqui nao tinha visual nenhum, so lateralizava como AGUARDAR/NEUTRA
# igual a um dia calmo.
LIMIAR_ALTO_RISCO_VOL = 0.70
"""Acima disto `estado.risco_volatilidade` acende ALTO RISCO quando não há
decisão. IMPRECISO — limiar de engenharia deste projeto: o próprio
`risco_volatilidade` já é um proxy declarado (desvio-padrão dos preços
sobre 6 ticks), então não existe "0,70 da fonte" a citar. Escolhido no
topo da faixa para o aviso ser raro: um alerta que acende o tempo todo
deixa de ser alerta."""

GLIFO_ULTRA_COMPRA = "ultra_compra"
GLIFO_ULTRA_VENDA = "ultra_venda"
GLIFO_ALTO_RISCO = "alto_risco"
GLIFO_COMPRA = "compra"
GLIFO_VENDA = "venda"
GLIFO_NEUTRA = "neutra"
GLIFO_AGUARDAR = "aguardar"

GLIFO_MERCADO_COMPRA = "mercado_compra"
GLIFO_MERCADO_VENDA = "mercado_venda"
"""Direcao OBSERVADA do mercado sem decisao do filtro. Desenham o mesmo
glifo direcional de `GLIFO_COMPRA`/`GLIFO_VENDA`, mas com rotulo proprio:
"o mercado esta subindo" e "o filtro decidiu comprar" sao afirmacoes
diferentes, e o visor nao pode escrever a segunda quando so mediu a
primeira."""

_ROTULO_LEITURA = {
    GLIFO_ULTRA_COMPRA: "ULTRA COMPRA",
    GLIFO_ULTRA_VENDA: "ULTRA VENDA",
    GLIFO_ALTO_RISCO: "ALTO RISCO",
    GLIFO_MERCADO_COMPRA: "MERCADO COMPRADOR",
    GLIFO_MERCADO_VENDA: "MERCADO VENDEDOR",
    GLIFO_NEUTRA: "MERCADO LATERAL",
}


def leitura_do_nucleo(estado: EstadoNexo, direcao: "_asg.DirecaoASG") -> str:
    """Classifica o glifo central. Funcao PURA, testavel sem QPainter.

    Prioridade, da leitura mais confirmada para a mais generica:

    1. **Sinal Ultra ARMADO** — nao "aceso" (que inclui SEGURANDO, so
       histerese sem alinhamento vivo, ver `vies.fase_do_filtro_de_sinal`):
       especificamente as condicoes fechando AGORA. Mostrar o raio tambem em
       SEGURANDO repetiria o defeito que `vies.py` ja corrigiu uma vez (selo
       aceso sem alinhamento parecendo igual ao aceso COM alinhamento) — em
       SEGURANDO o glifo cai para a leitura de decisao normal, e quem conta a
       histerese e a faixa do Ultra logo abaixo (`_desenhar_faixa_ultra`).
    2. **ALTO RISCO** — sem decisao confirmada (AGUARDAR ou NEUTRA) e o Renko
       acabou de INVERTER uma sequencia de 2+ tijolos
       (`FaseRenko.POSSIVEL_INVERSAO`, ja calculada por
       `fluxopro/analytics/renko.py`) — o mercado bateu de lado agora, nao
       apenas "sem sinal ainda". IMPRECISO: e o mesmo proxy de engenharia que
       ja vale para `FaseRenko` inteiro (ver docstring de `renko.py`), nao
       formula da fonte original.
    3. **COMPRA/VENDA** — decisao confirmada, Ultra nao armado agora.
    4. **NEUTRA** — balanco sem vies (`DirecaoASG.NEUTRA`).
    5. **AGUARDAR** — default, nenhuma leitura.
    """

    ultra = estado.sinal_ultra
    if _vies.fase_do_filtro_de_sinal(ultra) == _vies.ARMADO:
        return (GLIFO_ULTRA_COMPRA if ultra.direcao is DirecaoUltra.COMPRA
                else GLIFO_ULTRA_VENDA)

    decidido = direcao in (_asg.DirecaoASG.COMPRA, _asg.DirecaoASG.VENDA)
    if not decidido:
        # "avisar momentos de alta volatilidade que o mercado esta sem
        # direcional" (pedido do operador, 30/08/2026). Ate 31/08 isto
        # olhava SO `FaseRenko.POSSIVEL_INVERSAO`, que e inversao de
        # tijolo — parente da volatilidade, mas nao a mesma coisa, e o
        # pedido dizia volatilidade com todas as letras. Agora o gatilho
        # principal e `estado.risco_volatilidade` (desvio-padrao real dos
        # precos observados, ver `asg._risco_volatilidade`), e a inversao
        # de Renko continua valendo como segundo gatilho.
        if float(getattr(estado, "risco_volatilidade", 0.0) or 0.0) >= LIMIAR_ALTO_RISCO_VOL:
            return GLIFO_ALTO_RISCO
        if estado.fase_renko is FaseRenko.POSSIVEL_INVERSAO:
            return GLIFO_ALTO_RISCO

    if direcao is _asg.DirecaoASG.COMPRA:
        return GLIFO_COMPRA
    if direcao is _asg.DirecaoASG.VENDA:
        return GLIFO_VENDA

    # Sem decisao do filtro, o visor ainda deve dizer PARA ONDE O MERCADO
    # esta indo — "mostra a direcao do mercado mesmo que sem ultra" era
    # metade do pedido, e ate 31/08/2026 o nucleo simplesmente escrevia
    # "SEM DECISAO" com o mercado comprador a olho nu (regime COMPRADOR,
    # maker +0,84, dominancia 51/49). A fonte e o motor de Dominancia, que
    # e justamente quem mede direcao de mercado neste produto.
    mercado = direcao_de_mercado(estado)
    if mercado is not None:
        return mercado
    if direcao is _asg.DirecaoASG.NEUTRA:
        return GLIFO_NEUTRA
    return GLIFO_AGUARDAR


def direcao_de_mercado(estado: EstadoNexo) -> str | None:
    """Glifo da direção OBSERVADA do mercado, do motor de Dominância.

    `None` quando não há leitura de dominância publicada (aí o núcleo cai
    para NEUTRA/AGUARDAR, que é o comportamento honesto de "não sei"). É
    função pura e separada de `leitura_do_nucleo` para poder ser testada
    sem montar um `EstadoNexo` inteiro de decisão.
    """

    snapshot = getattr(estado, "dominancia_snapshot", None)
    if snapshot is None:
        return None
    from fluxopro.analytics.dominancia import EstadoDominancia

    estado_dom = getattr(snapshot, "estado", None)
    if estado_dom in (EstadoDominancia.COMPRA, EstadoDominancia.ULTRA_COMPRA):
        return GLIFO_MERCADO_COMPRA
    if estado_dom in (EstadoDominancia.VENDA, EstadoDominancia.ULTRA_VENDA):
        return GLIFO_MERCADO_VENDA
    if estado_dom is EstadoDominancia.BALANCEADO:
        return GLIFO_NEUTRA
    return None


def _cor_da_leitura(leitura: str, direcao: "_asg.DirecaoASG"):
    """Cor do glifo/moldura para a leitura do nucleo.

    ULTRA usa a MESMA cor direcional do resto do produto (verde/rosa) — e a
    mesma decisao, so que confirmada com confianca maxima, nunca um terceiro
    hue. ALTO RISCO usa `tokens.ABSORPTION` (laranja de "evento de
    microestrutura detectado", ja usado no produto para absorcao) — nao o
    amarelo de AGUARDAR (`NEXO_AMARELO`/`FUNDO_ALERTA`), porque o risco tem
    de se distinguir a olho de "so esperando", nao repetir o mesmo tom.
    """

    if leitura in (GLIFO_ULTRA_COMPRA, GLIFO_MERCADO_COMPRA):
        return tema_asg.NEXO_VERDE
    if leitura in (GLIFO_ULTRA_VENDA, GLIFO_MERCADO_VENDA):
        return tema_asg.NEXO_ROSA
    if leitura == GLIFO_ALTO_RISCO:
        return tokens.ABSORPTION
    if leitura == GLIFO_NEUTRA:
        return _asg._cor_nexo_direcao(_asg.DirecaoASG.NEUTRA)
    return _asg._cor_nexo_direcao(direcao)


def _faixa_da_leitura(leitura: str, direcao: "_asg.DirecaoASG") -> QColor:
    """Cor de contorno/halo do visor — mesma logica de `_cor_da_leitura`, em
    versao translucida para a moldura (que ja tinha `_FAIXA_POR_DIRECAO` para
    os quatro estados de decisao)."""

    if leitura in (GLIFO_ULTRA_COMPRA, GLIFO_ULTRA_VENDA, GLIFO_ALTO_RISCO):
        cor = QColor(_cor_da_leitura(leitura, direcao))
        cor.setAlpha(60)
        return cor
    return _FAIXA_POR_DIRECAO.get(direcao, tema_asg.NEXO_CIANO_FAIXA)


# Selo do Sinal Ultra: anel pulsante. Periodo longo o bastante para ler como
# "respiracao" e nao como estroboscopio.
PERIODO_PULSO_ULTRA_NS = 1_200_000_000
ALPHA_PULSO_ULTRA_MIN = 90
ALPHA_PULSO_ULTRA_MAX = 235

# Alturas minimas abaixo das quais uma faixa e omitida em vez de desenhada
# esmagada. A regiao encolhe em telas pequenas; melhor perder a faixa inteira
# do que entregar texto cortado que o operador leria errado.
ALTURA_MIN_VISOR = 90
ALTURA_MIN_REGIAO = 90
LARGURA_MIN_REGIAO = 90


class _Condicao:
    """Uma condicao do filtro Ultra, ja avaliada para ESTE quadro.

    Objeto local e efemero (nao atravessa fronteira, nao e cacheado): existe
    so para o desenho nao virar quatro blocos copiados.
    """

    __slots__ = ("rotulo", "medida", "atendida")

    def __init__(self, rotulo: str, medida: str, atendida: bool) -> None:
        self.rotulo = rotulo
        self.medida = medida
        self.atendida = atendida


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < LARGURA_MIN_REGIAO or rect.height() < ALTURA_MIN_REGIAO:
        return

    decisao = estado.snapshot.decisao
    direcao = decisao.direcao
    leitura = leitura_do_nucleo(estado, direcao)
    cor = _cor_da_leitura(leitura, direcao)
    ultra = estado.sinal_ultra
    direcao_ultra = getattr(ultra, "direcao", None)
    ultra_ativo = direcao_ultra is not None and direcao_ultra is not DirecaoUltra.NENHUMA

    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # ---- reparticao vertical -------------------------------------------
    # De baixo para cima: cartoes, condicoes, faixa do Ultra, e o que sobra
    # e do visor. Ordem deliberada — o visor e a peca elastica, as leituras
    # numericas tem altura fixa porque texto esmagado nao e leitura.
    y_cartoes = rect.bottom() - ALTURA_CARTAO
    altura_condicoes = ALTURA_TITULO_CONDICOES + LINHAS_CONDICAO * ALTURA_LINHA_CONDICAO
    y_condicoes = y_cartoes - 3 - altura_condicoes
    y_faixa = y_condicoes - 2 - ALTURA_FAIXA_ULTRA
    altura_visor = y_faixa - 3 - rect.top()

    if altura_visor >= ALTURA_MIN_VISOR:
        moldura = QRect(rect.left(), rect.top(), rect.width(), altura_visor)
        _desenhar_cabecalho(painter, moldura, estado.snapshot.timestamp_ns)
        corpo = QRect(moldura.left(), moldura.top() + ALTURA_CABECALHO,
                      moldura.width(), moldura.height() - ALTURA_CABECALHO)
        _desenhar_moldura(painter, corpo, leitura, direcao, cor)
        _desenhar_glifo(painter, corpo, leitura, direcao, cor)
        _desenhar_titulo_decisao(painter, corpo, decisao, leitura, cor)
        if ultra_ativo:
            _desenhar_selo_ultra(painter, corpo, estado.snapshot.timestamp_ns)

    condicoes = _condicoes_ultra(estado, direcao)
    atendidas = sum(1 for item in condicoes if item.atendida)

    _desenhar_faixa_ultra(
        painter,
        QRect(rect.left(), y_faixa, rect.width(), ALTURA_FAIXA_ULTRA),
        ultra,
        atendidas,
        len(condicoes),
        estado.snapshot.timestamp_ns,
    )
    _desenhar_condicoes(
        painter,
        QRect(rect.left(), y_condicoes, rect.width(), altura_condicoes),
        condicoes,
    )
    _desenhar_cartoes(painter, QRect(rect.left(), y_cartoes, rect.width(), ALTURA_CARTAO),
                      estado, decisao, cor)


# ==========================================================================
# Condicoes do filtro Ultra
# ==========================================================================
def _condicoes_ultra(estado: EstadoNexo, direcao: "_asg.DirecaoASG") -> tuple[_Condicao, ...]:
    """As quatro condicoes de `sinal_ultra._confluencia`, avaliadas do MESMO
    estado que alimenta o motor.

    Nao e uma reimplementacao paralela do motor: a decisao oficial de ligar
    continua sendo `SinalUltraSnapshot.direcao` (com histerese), e e ela que a
    faixa exibe. Isto aqui e leitura de DIAGNOSTICO — "o que falta agora" —
    derivada dos mesmos campos de `EstadoNexo` que `asg.py` empacota em
    `EntradaSinalUltra`. Sao os mesmos numeros porque sao os mesmos objetos
    (`estado.maker` e literalmente a linha que o motor recebeu, ja suavizada).

    Rotulo: IMPRECISO — os limiares vem de `ConfigSinalUltra`, que e proxy
    proprio deste projeto e nao regra da fonte.
    """

    alvo = _direcao_ultra_de(direcao)
    confirmada = alvo is not DirecaoUltra.NENHUMA

    fase = estado.fase_renko
    tijolos = estado.tijolos_renko
    direcao_renko = DirecaoUltra.NENHUMA
    if tijolos:
        ultimo = getattr(tijolos[-1], "direcao", 0)
        direcao_renko = DirecaoUltra.COMPRA if ultimo > 0 else DirecaoUltra.VENDA
    renko_ok = (
        fase is FaseRenko.TENDENCIA
        and confirmada
        and direcao_renko is alvo
    )
    if fase is None:
        texto_renko = "—"
    elif fase is FaseRenko.TENDENCIA:
        texto_renko = "TENDENCIA " + _sigla_ultra(direcao_renko)
    else:
        texto_renko = str(getattr(fase, "value", fase)).upper().replace("_", " ")

    maker = estado.maker
    forca = float(getattr(maker, "forca", 0.0) or 0.0)
    confianca = getattr(maker, "confianca", None)
    conf_alta = confianca is _asg.ConfiancaASG.ALTA
    limiar = _config_do_quadro(estado.sinal_ultra).forca_maker_minima
    if alvo is DirecaoUltra.VENDA:
        forca_ok = forca <= -limiar
    elif alvo is DirecaoUltra.COMPRA:
        forca_ok = forca >= limiar
    else:
        forca_ok = abs(forca) >= limiar

    return (
        _Condicao("DECISAO", direcao.value if confirmada else "SEM DIRECAO", confirmada),
        _Condicao("RENKO", texto_renko, renko_ok),
        _Condicao(
            "MAKER",
            "%s / %s" % (formato.formatar_sinalizado(forca, 2),
                         formato.formatar_sinalizado(limiar, 2)),
            forca_ok,
        ),
        _Condicao(
            "CONFIANCA",
            "—" if confianca is None else confianca.value.replace("CONF ", ""),
            conf_alta,
        ),
    )


def _direcao_ultra_de(direcao: "_asg.DirecaoASG") -> DirecaoUltra:
    """Mesma traducao de `asg._direcao_ultra_de` — AGUARDAR/NEUTRA nao sao
    direcao confirmada e viram NENHUMA."""

    if direcao is _asg.DirecaoASG.COMPRA:
        return DirecaoUltra.COMPRA
    if direcao is _asg.DirecaoASG.VENDA:
        return DirecaoUltra.VENDA
    return DirecaoUltra.NENHUMA


def _sigla_ultra(direcao: DirecaoUltra) -> str:
    if direcao is DirecaoUltra.COMPRA:
        return "COMPRA"
    if direcao is DirecaoUltra.VENDA:
        return "VENDA"
    return "—"


def _desenhar_condicoes(painter: QPainter, rect: QRect,
                        condicoes: tuple[_Condicao, ...]) -> None:
    """Painel "padroes bem definidos": uma linha por condicao, lampada + medida.

    A lampada e um losango pequeno, cheio quando a condicao esta atendida e
    apenas contornado quando nao esta — a direcao nunca depende so da cor
    (mesmo invariante de "sem cor e canal" das outras fases da interface).
    """

    if rect.height() < ALTURA_TITULO_CONDICOES + ALTURA_LINHA_CONDICAO:
        return

    painter.fillRect(rect, tema_asg.NEXO_PAINEL)
    painter.setPen(QPen(tema_asg.NEXO_GRADE, TRACO_FINO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(8, 1, -8, 0), Qt.AlignmentFlag.AlignLeft,
                     "CONDICOES DO FILTRO ULTRA · TODAS AO MESMO TEMPO")

    y = rect.top() + ALTURA_TITULO_CONDICOES
    for item in condicoes:
        if y + ALTURA_LINHA_CONDICAO > rect.bottom() + 1:
            break
        linha = QRect(rect.left(), y, rect.width(), ALTURA_LINHA_CONDICAO)
        cor = tema_asg.NEXO_VERDE if item.atendida else tema_asg.NEXO_MUTED
        _lampada(painter, QPoint(linha.left() + 12, linha.center().y()), 4,
                 cor, item.atendida)
        painter.setFont(tokens.fonte_ui(8, QFont.Weight.DemiBold))
        painter.setPen(tema_asg.NEXO_TEXTO if item.atendida else tema_asg.NEXO_MUTED)
        painter.drawText(linha.adjusted(22, 0, -8, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         item.rotulo)
        painter.setFont(tokens.fonte_numero(8))
        painter.setPen(cor)
        painter.drawText(linha.adjusted(22, 0, -8, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                         item.medida[:22])
        y += ALTURA_LINHA_CONDICAO


def _lampada(painter: QPainter, centro: QPoint, raio: int, cor, cheia: bool) -> None:
    losango = QPolygon([
        QPoint(centro.x(), centro.y() - raio),
        QPoint(centro.x() + raio, centro.y()),
        QPoint(centro.x(), centro.y() + raio),
        QPoint(centro.x() - raio, centro.y()),
    ])
    if cheia:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cor)
    else:
        painter.setPen(QPen(cor, TRACO_FINO))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(losango)
    painter.setBrush(Qt.BrushStyle.NoBrush)


# ==========================================================================
# Faixa de estado do Ultra
# ==========================================================================
def _desenhar_faixa_ultra(painter: QPainter, rect: QRect, ultra,
                          atendidas: int, total: int, timestamp_ns: int) -> None:
    """A leitura grande do Ultra, com QUATRO estados distintos.

    Antes havia dois (aceso/apagado) e por isso "nunca aparecia nada": o
    apagado nao distinguia "faltam tres condicoes" de "as quatro fecharam
    agora e falta so a janela de persistencia". Sao situacoes muito
    diferentes para o operador e agora tem leituras diferentes.

    ``CONFIRMANDO`` sai da confluencia CRUA (`confluencia_no_instante`) e e
    rotulada como tal — nunca apresentada como sinal oficial, que continua
    sendo `direcao` (pos-histerese). Mostrar a janela e o que faz a raridade
    do Ultra ler como projeto (histerese assimetrica deliberada) em vez de
    defeito.
    """

    if rect.height() < 12:
        return

    if ultra is None:
        _faixa_texto(painter, rect, tema_asg.NEXO_MUTED,
                     "ULTRA INDISPONIVEL", "SEM MOTOR NESTE QUADRO", pulso=None)
        return

    direcao = getattr(ultra, "direcao", DirecaoUltra.NENHUMA)
    crua = getattr(ultra, "confluencia_no_instante", DirecaoUltra.NENHUMA)

    # Progresso da janela de histerese que estiver correndo AGORA. Os dois
    # numeros sao lidos do motor: o decorrido de `pendente_desde_ns` (o
    # cronometro que ele ja mantinha) e o alvo de `janela_alvo_ns` (a metade
    # da histerese que ele mesmo escolheu). A UI nao decide qual janela se
    # aplica nem quanto ela vale — so divide um pelo outro.
    janela_ns = int(getattr(ultra, "janela_alvo_ns", 0) or 0)
    pendente_desde = int(getattr(ultra, "pendente_desde_ns", 0) or 0)
    decorrido_ns = max(0, timestamp_ns - pendente_desde) if pendente_desde else 0
    progresso = min(1.0, decorrido_ns / janela_ns) if janela_ns > 0 else None
    relogio = "%s / %s" % (
        formato.formatar_duracao_s(decorrido_ns / 1e9),
        formato.formatar_duracao_s(janela_ns / 1e9),
    )

    if direcao is not DirecaoUltra.NENHUMA:
        if janela_ns > 0:
            # Aceso, mas a confluencia quebrou: o que corre agora e a janela
            # de DESLIGAMENTO. Dizer isso e o oposto de esconder — o operador
            # ve que o selo esta se sustentando por histerese, nao por
            # confluencia viva.
            detalhe = "SEGURANDO · " + relogio
        else:
            ligado_desde = getattr(ultra, "ligado_desde_ns", None)
            detalhe = "FILTRO ADICIONAL · CONSULTIVO"
            if ligado_desde and timestamp_ns > ligado_desde:
                detalhe += " · HA " + formato.formatar_duracao_s(
                    (timestamp_ns - ligado_desde) / 1e9)
        _faixa_texto(painter, rect, tema_asg.NEXO_AMARELO,
                     "ULTRA " + _sigla_ultra(direcao), detalhe,
                     pulso=timestamp_ns, progresso=progresso)
        return

    if crua is not DirecaoUltra.NENHUMA:
        _faixa_texto(
            painter, rect, tema_asg.NEXO_CIANO,
            "CONFIRMANDO " + _sigla_ultra(crua),
            "%d/%d CONDICOES · %s" % (atendidas, total, relogio),
            pulso=None, progresso=progresso,
        )
        return

    _faixa_texto(painter, rect, tema_asg.NEXO_MUTED, "ULTRA INATIVO",
                 "%d/%d CONDICOES" % (atendidas, total), pulso=None,
                 progresso=None)


def _faixa_texto(painter: QPainter, rect: QRect, cor, titulo: str,
                 detalhe: str, *, pulso: int | None,
                 progresso: float | None = None) -> None:
    """Faixa com fundo em degrade horizontal a partir da esquerda.

    O degrade (e nao um preenchimento chapado) existe para a faixa nao ler
    como cartao: a intensidade nasce na lampada da esquerda e se dissolve, o
    mesmo gesto do bisel do visor logo acima.
    """

    alpha_base = 46
    if pulso is not None:
        fase = (pulso % PERIODO_PULSO_ULTRA_NS) / PERIODO_PULSO_ULTRA_NS
        onda = (1 - math.cos(2 * math.pi * fase)) / 2.0
        alpha_base = round(ALPHA_PULSO_ULTRA_MIN
                           + (ALPHA_PULSO_ULTRA_MAX - ALPHA_PULSO_ULTRA_MIN) * onda) // 2

    esquerda = QColor(cor)
    esquerda.setAlpha(alpha_base)
    direita = QColor(cor)
    direita.setAlpha(0)
    degrade = QLinearGradient(rect.left(), 0, rect.right(), 0)
    degrade.setColorAt(0.0, esquerda)
    degrade.setColorAt(1.0, direita)
    painter.fillRect(rect, tema_asg.NEXO_PAINEL_ALTO)
    painter.fillRect(rect, degrade)

    painter.setPen(QPen(cor, TRACO_GLIFO))
    painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())

    painter.setFont(tokens.fonte_ui(9, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(rect.adjusted(8, 0, -8, -rect.height() // 2),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     titulo)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rect.adjusted(8, rect.height() // 2, -8, -ALTURA_BARRA_JANELA),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     detalhe)

    if progresso is None:
        return
    # Trilho da janela de histerese, rente a base da faixa. Fundo de escala
    # ABSOLUTO — a janela inteira, sempre — entao a barra pela metade quer
    # dizer metade do tempo, e nunca "metade do maior que ja vi". Sem piso:
    # comprimento zero significa "o cronometro acabou de zerar", que e
    # informacao, e um piso apagaria justamente o instante em que a
    # confluencia se refez.
    trilho = QRect(rect.left(), rect.bottom() - ALTURA_BARRA_JANELA + 1,
                   rect.width(), ALTURA_BARRA_JANELA)
    painter.fillRect(trilho, tema_asg.NEXO_GRADE)
    cheio = int(trilho.width() * max(0.0, min(1.0, progresso)))
    if cheio > 0:
        painter.fillRect(QRect(trilho.left(), trilho.top(), cheio, trilho.height()),
                         cor)


# ==========================================================================
# Visor
# ==========================================================================
def _desenhar_cabecalho(painter: QPainter, rect: QRect, timestamp_ns: int) -> None:
    """Titulo da regiao a esquerda, carimbo de tempo do quadro a direita.

    ``timestamp_ns`` vem do `WorkspaceASGSnapshot` (um so por quadro, sob
    lock, pelo relogio unico da janela) — nunca de um relogio proprio do
    visor. Sem ele o visor era uma leitura sem hora, a mesma imagem parada
    servindo para qualquer instante.
    """

    caixa = QRect(rect.left(), rect.top(), rect.width(), ALTURA_CABECALHO)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(8, 0, -8, 0),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     "NUCLEO DE LEITURA")
    painter.setFont(tokens.fonte_numero(7))
    texto = formato.formatar_hora_ns(timestamp_ns) if timestamp_ns > 0 else "— SEM RELOGIO —"
    painter.drawText(caixa.adjusted(8, 0, -8, 0),
                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     texto)


def _desenhar_moldura(painter: QPainter, moldura: QRect, leitura: str,
                      direcao: "_asg.DirecaoASG", cor) -> None:
    """Corpo do visor em cinco camadas — a profundidade que o operador pediu.

    Nenhuma delas e um poligono chapado com uma borda so (a assinatura visual
    de "botao"):

    1. **sombra projetada** — a mesma silhueta em quase-preto, deslocada
       ``SOMBRA_DY`` para baixo: firma a luz vindo de cima e descola o visor
       do fundo da superficie;
    2. **corpo em degrade vertical** — claro no topo, escuro na base, que e o
       que um objeto solido faz sob luz de cima;
    3. **halo interno radial** na cor da direcao, denso no centro e nulo na
       borda — brilho vindo de DENTRO do vidro, nao uma borda colorida;
    4. **brilho de bisel** — as duas arestas superiores em branco translucido
       fino, o realce de quina que separa "chanfro" de "contorno";
    5. **brackets de canto** tipo mira, na cor da direcao — o detalhe de
       instrumento que nunca aparece num botao convencional.
    """

    faixa = _faixa_da_leitura(leitura, direcao)
    silhueta = _silhueta_visor(moldura)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_FUNDO)
    painter.drawPolygon(_silhueta_visor(moldura.translated(0, SOMBRA_DY)))

    corpo = QLinearGradient(0, moldura.top(), 0, moldura.bottom())
    corpo.setColorAt(0.0, tema_asg.NEXO_GRADE)
    corpo.setColorAt(0.35, tema_asg.NEXO_PAINEL_ALTO)
    corpo.setColorAt(1.0, tema_asg.NEXO_PAINEL)
    painter.setBrush(corpo)
    painter.drawPolygon(silhueta)

    centro = moldura.center()
    raio = max(moldura.width(), moldura.height()) / 2.0
    halo = QRadialGradient(centro.x(), centro.y(), raio)
    dentro = QColor(cor)
    dentro.setAlpha(38)
    fora = QColor(cor)
    fora.setAlpha(0)
    halo.setColorAt(0.0, dentro)
    halo.setColorAt(1.0, fora)
    painter.setBrush(halo)
    painter.drawPolygon(silhueta)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(faixa, TRACO_GLIFO + 1))
    painter.drawPolygon(silhueta)

    _linhas_de_varredura(painter, moldura)
    _brilho_bisel(painter, moldura)

    painter.setPen(QPen(tema_asg.NEXO_GRADE, TRACO_FINO))
    interna = moldura.adjusted(RECUO_CONTORNO, RECUO_CONTORNO,
                               -RECUO_CONTORNO, -RECUO_CONTORNO)
    painter.drawPolygon(_silhueta_visor(interna))

    _brackets_canto(painter, moldura, cor)


def _linhas_de_varredura(painter: QPainter, rect: QRect) -> None:
    """Quatro hairlines horizontais no miolo do visor, alpha muito baixo.

    Nao sao dado e nao pretendem ser: sao TEXTURA. O campo do visor era uma
    chapa preta uniforme, e uma chapa uniforme nao tem profundidade nenhuma —
    o olho nao tem em que se apoiar para ler o vidro como plano a frente do
    fundo. Quatro linhas (nao vinte) bastam para dar o plano sem competir com
    o glifo nem sugerir escala. Recuadas do chanfro para nunca vazar da
    silhueta.
    """

    lado = min(rect.width(), rect.height())
    bisel = max(10, lado // BISEL_TOPO_DIV)
    linha = QColor(tema_asg.NEXO_GRADE)
    linha.setAlpha(90)
    painter.setPen(QPen(linha, TRACO_FINO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    passo = rect.height() // 5
    if passo <= 0:
        return
    for k in range(1, 5):
        y = rect.top() + k * passo
        painter.drawLine(rect.left() + bisel // 2, y, rect.right() - bisel // 2, y)


def _brilho_bisel(painter: QPainter, rect: QRect) -> None:
    """Realce de quina nas duas arestas superiores do chanfro.

    Um contorno inteiro em branco leria como segunda borda; so as arestas que
    ficam de frente para a luz recebem o realce, que e o que torna o chanfro
    legivel como chanfro.
    """

    lado = min(rect.width(), rect.height())
    bisel = max(10, lado // BISEL_TOPO_DIV)
    realce = QColor(tema_asg.NEXO_TEXTO)
    realce.setAlpha(46)
    painter.setPen(QPen(realce, TRACO_FINO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(rect.left() + bisel, rect.top() + 1,
                     rect.right() - bisel, rect.top() + 1)
    painter.drawLine(rect.left() + 1, rect.top() + bisel,
                     rect.left() + bisel, rect.top() + 1)
    painter.drawLine(rect.right() - 1, rect.top() + bisel,
                     rect.right() - bisel, rect.top() + 1)


def _silhueta_visor(rect: QRect) -> QPolygon:
    """Moldura em bisel assimetrico: topo fundo, base quase reta.

    Um octogono regular (mesmo corte nos quatro cantos) le como botao
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
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for x, y, dx, dy in (
        (rect.left(), rect.top(), 1, 1),
        (rect.right(), rect.top(), -1, 1),
        (rect.left(), rect.bottom(), 1, -1),
        (rect.right(), rect.bottom(), -1, -1),
    ):
        painter.drawLine(x, y, x + dx * braco, y)
        painter.drawLine(x, y, x, y + dy * braco)


def _desenhar_titulo_decisao(painter: QPainter, moldura: QRect, decisao,
                             leitura: str, cor) -> None:
    """Titulo da decisao DENTRO do visor, na base do bisel.

    Estava fora da moldura, num vao morto entre o visor e o resto — e o vao
    existia so por causa dele. Trazido para dentro, o texto pertence ao
    instrumento e a regiao recupera a altura.

    O texto segue a MESMA `leitura` que escolheu o glifo (`_ROTULO_LEITURA`
    para ULTRA/ALTO RISCO, o titulo da decisao nos demais casos) — nunca o
    titulo cru quando o glifo esta mostrando outra coisa. Rotulo e glifo
    discordando e exatamente o padrao de defeito que mais se repetiu neste
    projeto (declaracao nao conferindo com o elemento).
    """

    rotulo = _ROTULO_LEITURA.get(leitura, decisao.titulo.upper())
    lado = min(moldura.width(), moldura.height())
    base = max(4, lado // BISEL_BASE_DIV)
    caixa = QRect(moldura.left(), moldura.bottom() - base - 26, moldura.width(), 16)
    painter.setFont(tokens.fonte_ui(11, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, rotulo)

    # A ressalva consultiva mora DENTRO do instrumento, e nao so na linha do
    # rodape do quadro: o glifo grande e colorido e a peca mais parecida com
    # "sinal de entrada" da tela inteira, e e junto dele que a negativa precisa
    # estar para ser lida por quem olha so para o centro.
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(moldura.left(), caixa.bottom(), moldura.width(), 12),
                     Qt.AlignmentFlag.AlignCenter,
                     "LEITURA CONSULTIVA · NAO E ORDEM")


def _desenhar_selo_ultra(painter: QPainter, moldura: QRect, timestamp_ns: int) -> None:
    """Anel pulsante sobre o contorno do visor quando o Sinal Ultra esta ativo.

    A pulsacao usa `timestamp_ns` (o mesmo relogio do quadro, nunca um relogio
    de UI separado) — o anel respira em fase com o feed, nao com o framerate de
    repintura da janela. Onda cosseno (nunca linear/dente de serra) para a
    transicao de alpha nao "cortar" nos extremos do ciclo — o mesmo defeito de
    mudanca abrupta que motivou suavizar o gauge EQUILIBRIO, aqui evitado de
    saida.

    Redesenha a MESMA silhueta, nunca uma expandida para fora dela: as regioes
    do NEXO encostam borda a borda sem vao (ver docstring do pacote) e um anel
    externo sangraria na regiao vizinha.
    """

    fase = (timestamp_ns % PERIODO_PULSO_ULTRA_NS) / PERIODO_PULSO_ULTRA_NS
    onda = (1 - math.cos(2 * math.pi * fase)) / 2.0
    alpha = round(ALPHA_PULSO_ULTRA_MIN
                  + (ALPHA_PULSO_ULTRA_MAX - ALPHA_PULSO_ULTRA_MIN) * onda)

    cor_anel = QColor(tema_asg.NEXO_AMARELO)
    cor_anel.setAlpha(alpha)
    painter.setPen(QPen(cor_anel, TRACO_GLIFO + 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(_silhueta_visor(moldura.adjusted(1, 1, -1, -1)))


# ==========================================================================
# Glifo
# ==========================================================================
def _desenhar_glifo(painter: QPainter, moldura: QRect, leitura: str,
                    direcao: "_asg.DirecaoASG", cor) -> None:
    """Glifo central, escalado para ocupar o visor (nao um icone perdido nele).

    ``rx``/``ry`` sao semi-eixos independentes — nao um raio unico — porque o
    bisel e bem mais largo que alto. Um raio uniforme calibrado pela altura (o
    eixo mais curto) deixava larguras inteiras de campo escuro vazias dos dois
    lados do glifo.

    A faixa inferior do visor esta reservada ao titulo da decisao, entao a
    altura util e descontada aqui — sem isso o glifo cresceria por cima do
    texto exatamente nos biseis mais altos.
    """

    lado = min(moldura.width(), moldura.height())
    # Chanfro da base + as DUAS linhas do bloco de titulo (decisao + ressalva
    # consultiva) — ver `_desenhar_titulo_decisao`. Sem reservar as duas, o
    # glifo cresce por cima do texto justamente nos biseis mais altos.
    reserva_titulo = max(4, lado // BISEL_BASE_DIV) + 28
    disponivel_h = moldura.height() - reserva_titulo
    if disponivel_h <= 2 * RECUO_CONTORNO:
        return
    cx = moldura.center().x()
    cy = moldura.top() + disponivel_h // 2

    largura_util = moldura.width() - 2 * RECUO_CONTORNO
    # O chanfro do topo e FUNDO (`BISEL_TOPO_DIV`), entao a caixa da moldura
    # NAO e a area util: perto do topo a silhueta ja se estreitou e um glifo
    # dimensionado pelo retangulo fura o bisel pelo lado longo. Metade do
    # chanfro sai da altura util — a metade, e nao ele inteiro, porque o glifo
    # e centrado e so a ponta chega perto da aresta.
    bisel_topo = max(10, min(moldura.width(), moldura.height()) // BISEL_TOPO_DIV)
    altura_util = disponivel_h - 2 * RECUO_CONTORNO - bisel_topo // 2
    if altura_util <= 0:
        return

    if leitura in (GLIFO_ULTRA_COMPRA, GLIFO_ULTRA_VENDA):
        # Raio extrudado — a leitura de MAIOR confianca do visor, nunca
        # confundida com a seta simples de decisao sem Ultra armado.
        rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
        ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
        _glifo_raio(painter, cx, cy, rx, ry, cor)
        return

    if leitura == GLIFO_ALTO_RISCO:
        # Alerta de risco — mercado bateu de lado agora, nao apenas "sem
        # sinal ainda" (ver docstring de `leitura_do_nucleo`).
        rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
        ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
        _glifo_alerta(painter, cx, cy, rx, ry, cor)
        return

    # A direcao OBSERVADA do mercado (sem decisao do filtro) desenha a
    # MESMA seta da decisao direcional — quem separa as duas leituras e o
    # rotulo ("MERCADO COMPRADOR" x o titulo da decisao), nao a forma.
    # Este ramo tem de vir antes do teste por `direcao`, que aqui ainda e
    # AGUARDAR e cairia no losango.
    if leitura in (GLIFO_MERCADO_COMPRA, GLIFO_MERCADO_VENDA):
        rx, ry = _dimensoes_seta(largura_util, altura_util)
        para_cima = leitura == GLIFO_MERCADO_COMPRA
        recuo = ry // 4
        _glifo_seta(painter, cx, cy + (recuo if para_cima else -recuo), rx, ry,
                    cor, para_cima=para_cima)
        return

    if leitura == GLIFO_NEUTRA:
        rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
        ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
        _glifo_equilibrio(painter, cx, cy, rx, ry, cor)
        return

    if direcao in (_asg.DirecaoASG.COMPRA, _asg.DirecaoASG.VENDA):
        rx, ry = _dimensoes_seta(largura_util, altura_util)
        # A seta NAO e simetrica em torno de ``cy``: ela ocupa ``ry`` de um
        # lado e ``ry//2`` do outro. Passar ``cy`` cru (o centro da banda util)
        # centraria o APICE em vez da silhueta, e a ponta furava a moldura pelo
        # lado longo — foi exatamente o que aconteceu na primeira passada, com
        # o triangulo sangrando para fora do bisel. Deslocar meio-vao do lado
        # longo centra a CAIXA da seta na banda.
        para_cima = direcao is _asg.DirecaoASG.COMPRA
        recuo = ry // 4
        _glifo_seta(painter, cx, cy + (recuo if para_cima else -recuo), rx, ry,
                    cor, para_cima=para_cima)
        return

    rx = _semi_eixo(largura_util, FRACAO_GLIFO_LARGURA)
    ry = _semi_eixo(altura_util, FRACAO_GLIFO_ALTURA)
    if direcao is _asg.DirecaoASG.AGUARDAR:
        _glifo_losango(painter, cx, cy, rx, ry, cor)
    else:
        _glifo_equilibrio(painter, cx, cy, rx, ry, cor)


def _semi_eixo(dimensao_util: int, fracao: float) -> int:
    """Semi-eixo do glifo num unico eixo: ``fracao`` da dimensao util do bisel,
    depois o piso/teto absolutos para nao colapsar nem explodir."""

    return max(RAIO_MIN, min(RAIO_MAX, round(dimensao_util * fracao / 2)))


def _dimensoes_seta(largura_util: int, altura_util: int) -> tuple[int, int]:
    """Semi-eixos (rx, ry) da seta, derivados um do outro.

    Ao contrario de ``_semi_eixo`` (dois raios independentes), a seta e um
    triangulo isosceles de angulo de apice FIXO: a metade da base vem de
    ``FRACAO_SETA_LARGURA`` e a altura decorre dela pelo angulo — nunca um
    segundo raio calibrado a parte, que deixaria a ponta ora gorda ora fina
    conforme a proporcao do bisel muda. Sem teto em pixels sobre ``rx``: um
    teto absoluto e o que faz a seta encolher, EM FRACAO do bisel, justamente
    nos biseis maiores. Se nao couber na altura util, os dois eixos sao
    escalados pelo mesmo fator, preservando o angulo.
    """

    rx = max(RAIO_MIN, round(largura_util * FRACAO_SETA_LARGURA / 2))
    meio_angulo = math.radians(ANGULO_APICE_SETA_GRAUS / 2)
    ry = max(1, round((rx / math.tan(meio_angulo)) / 1.5))

    altura_ocupada = ry + ry // 2
    if altura_util > 0 and altura_ocupada > altura_util:
        fator = altura_util / altura_ocupada
        rx = max(RAIO_MIN, round(rx * fator))
        ry = max(RAIO_MIN, round(ry * fator))
    return rx, ry


def _pontos_seta(cx: int, cy: int, rx: int, ry: int, *, para_cima: bool) -> QPolygon:
    if para_cima:
        return QPolygon([QPoint(cx, cy - ry), QPoint(cx - rx, cy + ry // 2),
                         QPoint(cx + rx, cy + ry // 2)])
    return QPolygon([QPoint(cx, cy + ry), QPoint(cx - rx, cy - ry // 2),
                     QPoint(cx + rx, cy - ry // 2)])


def _glifo_seta(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor,
                *, para_cima: bool) -> None:
    """Seta EXTRUDADA — unica leitura confirmada de direcao (COMPRA/VENDA).

    Tres camadas deslocadas no eixo da propria seta (para baixo quando ela
    aponta para cima, e vice-versa): as de tras escurecidas, a da frente na
    cor cheia, mais a face superior em realce. E a mesma linguagem do prisma
    3D do MakerProxy na regiao vizinha — o volume vem de camadas de cor, nunca
    de um contorno duplicado, que leria como erro de registro.
    """

    # Deslocamento DIAGONAL (para baixo e para a direita), nunca so vertical:
    # com deslocamento puro no eixo da seta as camadas ficam escondidas atras
    # da face e so aparecem como uma tarja na aresta reta — leu como erro de
    # registro na primeira passada, nao como volume. Na diagonal as camadas
    # aparecem nas DUAS arestas inclinadas, que e o que da o corpo do prisma.
    painter.setPen(Qt.PenStyle.NoPen)
    for camada in range(CAMADAS_EXTRUSAO, 0, -1):
        sombra = QColor(cor).darker(150 + 40 * camada)
        painter.setBrush(sombra)
        painter.drawPolygon(_pontos_seta(cx + camada * PASSO_EXTRUSAO,
                                         cy + camada * PASSO_EXTRUSAO,
                                         rx, ry, para_cima=para_cima))

    painter.setBrush(cor)
    face = _pontos_seta(cx, cy, rx, ry, para_cima=para_cima)
    painter.drawPolygon(face)

    realce = QColor(tema_asg.NEXO_TEXTO)
    realce.setAlpha(120)
    painter.setPen(QPen(realce, TRACO_FINO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    apice = face[0]
    painter.drawLine(apice, face[1])
    painter.drawLine(apice, face[2])


def _pontos_raio(cx: int, cy: int, rx: int, ry: int) -> QPolygon:
    """Raio (relampago) de 6 vertices, geometria autoral — nunca o desenho
    do PNG/SVG de referencia, mesma regra de todo glifo deste modulo."""

    return QPolygon([
        QPoint(cx + round(rx * 0.15), cy - ry),
        QPoint(cx - round(rx * 0.55), cy + round(ry * 0.15)),
        QPoint(cx - round(rx * 0.05), cy + round(ry * 0.15)),
        QPoint(cx - round(rx * 0.25), cy + ry),
        QPoint(cx + round(rx * 0.55), cy - round(ry * 0.15)),
        QPoint(cx + round(rx * 0.05), cy - round(ry * 0.15)),
    ])


def _glifo_raio(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Raio extrudado — leitura "Sinal Ultra ARMADO agora" (ver
    `leitura_do_nucleo`). E a unica leitura de confianca MAXIMA que o visor
    tem, entao precisa ser inconfundivel com a seta simples de decisao: a
    mesma linguagem de extrusao em tres camadas (`_glifo_seta`), silhueta
    diferente, para o operador reconhecer o estado pela FORMA, nao so pela
    cor — mesmo invariante de "cor nunca e o unico canal" do resto do
    produto.
    """

    painter.setPen(Qt.PenStyle.NoPen)
    for camada in range(CAMADAS_EXTRUSAO, 0, -1):
        sombra = QColor(cor).darker(150 + 40 * camada)
        painter.setBrush(sombra)
        painter.drawPolygon(_pontos_raio(cx + camada * PASSO_EXTRUSAO,
                                         cy + camada * PASSO_EXTRUSAO, rx, ry))

    painter.setBrush(cor)
    face = _pontos_raio(cx, cy, rx, ry)
    painter.drawPolygon(face)

    realce = QColor(tema_asg.NEXO_TEXTO)
    realce.setAlpha(150)
    painter.setPen(QPen(realce, TRACO_FINO))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolyline(face)


def _glifo_alerta(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Triangulo de alerta com "!" — leitura ALTO RISCO (mercado bateu de
    lado agora, ver `leitura_do_nucleo`). Preenchido e solido, ao contrario
    do losango vazado de AGUARDAR: alto risco nao e "esperando calmo", e
    "algo aconteceu e precisa de atencao", e o preenchimento solido carrega
    esse peso visual — o mesmo principio de "forma tambem le o estado", nao
    so a cor, que rege `_glifo_raio`.
    """

    topo = QPoint(cx, cy - ry)
    base_esq = QPoint(cx - rx, cy + ry)
    base_dir = QPoint(cx + rx, cy + ry)
    triangulo = QPolygon([topo, base_dir, base_esq])

    painter.setPen(QPen(tema_asg.NEXO_FUNDO, TRACO_GLIFO + 1))
    painter.setBrush(cor)
    painter.drawPolygon(triangulo)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    painter.setFont(tokens.fonte_ui(max(10, int(ry * 0.9)), QFont.Weight.Black))
    painter.setPen(tema_asg.NEXO_FUNDO)
    caixa_ponto = QRect(cx - rx, cy - ry // 5, rx * 2, ry + ry // 5)
    painter.drawText(caixa_ponto, Qt.AlignmentFlag.AlignCenter, "!")


def _glifo_losango(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Losango vazado (duas cunhas encostadas) — leitura "aguardando confirmacao".

    Vazado e nunca preenchido: e o segundo estado do visor, distinto da seta
    solida da direcao confirmada, para que o visor nunca finja saber uma
    direcao que ainda nao existe. O preenchimento translucido interno da
    profundidade sem transformar o vazado em solido.
    """

    topo = QPoint(cx, cy - ry)
    base = QPoint(cx, cy + ry)
    esquerda = QPoint(cx - rx, cy)
    direita = QPoint(cx + rx, cy)
    poligono = QPolygon([topo, direita, base, esquerda])

    interior = QLinearGradient(0, cy - ry, 0, cy + ry)
    topo_cor = QColor(cor)
    topo_cor.setAlpha(52)
    base_cor = QColor(cor)
    base_cor.setAlpha(8)
    interior.setColorAt(0.0, topo_cor)
    interior.setColorAt(1.0, base_cor)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(interior)
    painter.drawPolygon(poligono)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(cor, TRACO_GLIFO))
    painter.drawPolygon(poligono)
    painter.drawLine(esquerda, direita)


def _glifo_equilibrio(painter: QPainter, cx: int, cy: int, rx: int, ry: int, cor) -> None:
    """Laco de equilibrio (dois arcos com ponta) — leitura "sem vies, NEUTRA".

    Terceiro estado: nem seta cheia nem losango de espera, e sim um circuito
    fechado — "balanco de preco" sem direcao assumida, sem reciclar a silhueta
    da seta.
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
        seta = QPolygon([QPoint(0, -raio_ponta // 3),
                         QPoint(-raio_ponta // 4, raio_ponta // 6),
                         QPoint(raio_ponta // 4, raio_ponta // 6)])
        painter.drawPolygon(seta)
        painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _ponto_elipse(cx: int, cy: int, rx: float, ry: float, graus: float) -> QPoint:
    """Ponto na elipse de semi-eixos ``rx``/``ry`` (0 deg = leste, anti-horario)."""

    rad = math.radians(graus)
    return QPoint(round(cx + rx * math.cos(rad)), round(cy - ry * math.sin(rad)))


# ==========================================================================
# Cartoes de rodape
# ==========================================================================
def _desenhar_cartoes(painter: QPainter, rect: QRect, estado: EstadoNexo,
                      decisao, cor) -> None:
    """Tres leituras curtas de rodape, cada uma com o que ela E escrito embaixo.

    **Um numero, um sinal.** A cor do cartao REGIME sai de
    ``_asg._cor_nexo_direcao(estado.regime.direcao)`` — a direcao ja resolvida
    e conferida como coerente do outro lado da fronteira (ver
    `EstadoNexo.regime` e `asg._linha_regime`), nunca de um token escolhido
    aqui. Ate 28/08/2026 este cartao pintava COMPRADOR/VENDEDOR em ciano fixo:
    a palavra direcional mais destacada da tela fora do eixo de cor do quadro,
    e o mesmo ciano servindo para os dois lados. Essa recombinacao local de
    cor+rotulo e exatamente o defeito que ja reincidiu em RITMO e PRESENCA.

    **Discordancia explicada, nunca muda.** O REGIME pode legitimamente
    apontar para o lado oposto do PLACAR do rodape sem que nenhum dos dois
    esteja errado: sao janelas diferentes. A terceira linha do cartao publica
    a procedencia que a propria leitura carrega (`regime.detalhe`, hoje
    "ESTRUTURA DO DIA") — entao a tela diz de que prazo cada palavra fala em
    vez de exibir duas palavras brigando sem legenda.

    Quando `estado.regime` e None (montagem antiga/teste), o cartao cai para a
    linha REGIME do snapshot e sai em cor NEUTRA — jamais numa cor direcional
    que ele nao pode justificar.
    """

    regime = estado.regime
    if regime is None:
        regime = next((linha for linha in estado.snapshot.matriz.linhas
                       if linha.componente == "REGIME"), None)
        cor_regime = tema_asg.NEXO_MUTED
    else:
        cor_regime = _asg._cor_nexo_direcao(regime.direcao)

    nota_regime = getattr(regime, "detalhe", "") or "ESTRUTURA DO DIA"
    cartoes = (
        ("REGIME", "—" if regime is None else regime.valor, cor_regime, nota_regime),
        ("CONFIANCA", decisao.confianca.value.replace("CONF ", ""), cor,
         "DA DECISAO ACIMA"),
        ("EVIDENCIAS", str(estado.snapshot.evidencias.retidos),
         tema_asg.NEXO_AMARELO, "ITENS RETIDOS NA TRILHA"),
    )
    largura = max(32, (rect.width() + VAO_CARTAO) // len(cartoes) - VAO_CARTAO)
    for indice, (nome, valor, cor_cartao, nota) in enumerate(cartoes):
        caixa = QRect(rect.left() + indice * (largura + VAO_CARTAO), rect.top(),
                      largura, rect.height())
        # Degrade vertical (claro em cima) e uma linha de acento no topo: o
        # mesmo vocabulario de luz do visor, para os cartoes lerem como parte
        # do instrumento e nao como tres retangulos avulsos.
        fundo = QLinearGradient(0, caixa.top(), 0, caixa.bottom())
        fundo.setColorAt(0.0, tema_asg.NEXO_PAINEL_ALTO)
        fundo.setColorAt(1.0, tema_asg.NEXO_PAINEL)
        painter.fillRect(caixa, fundo)
        acento = QColor(cor_cartao)
        acento.setAlpha(150)
        painter.setPen(QPen(acento, TRACO_FINO))
        painter.drawLine(caixa.left(), caixa.top(), caixa.right(), caixa.top())

        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(3, 2, -3, -24),
                         Qt.AlignmentFlag.AlignCenter, nome)
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.Bold))
        painter.setPen(cor_cartao)
        painter.drawText(caixa.adjusted(3, 11, -3, -11),
                         Qt.AlignmentFlag.AlignCenter, valor[:12])
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(caixa.adjusted(2, 24, -2, -1),
                         Qt.AlignmentFlag.AlignCenter, nota[:24])
