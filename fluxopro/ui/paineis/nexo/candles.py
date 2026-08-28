"""Regiao GRAFICO DE CANDLES · M5 (x 0,63-0,98 · y 0,34-0,85).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_candles_nexo``. E a
maior area do quadro, como no material de referencia: a evidencia decisoria
mora no grafico.

Candles vem de ``estado.candles_m15`` — OHLCV real de 5 minutos (o nome do
campo ficou de uma versao anterior; ver `fluxopro/ui/paineis/asg.py` onde o
timeframe e configurado), agregado por `fluxopro/analytics/candle_temporal.py`
a partir dos MESMOS negocios que alimentam `estado.serie`. Nao ha OHLC
externo, nao ha lookahead e nao ha liquidez sintetizada. Preco chega em
``int`` de ticks e vira pixel apenas aqui, na fronteira de desenho
(``y_preco`` e ``formato.preco_completo``); nada volta a ser gravado no
snapshot.

O candle em formacao aparece desde o PRIMEIRO negocio da sessao — o operador
tem que ver o pavio se formando ao vivo, nunca esperar o timeframe fechar
para o grafico existir.

Etiquetas de preco na borda esquerda, faixa tracejada e anotacao junto aos
candles: os niveis consultivos (STOP/A1/A2/A3) sao ancorados na altura real
do preco quando o campo chega como inteiro de ticks; se chegar apenas como
texto ja formatado (compat com uma fonte antiga do modelo), a etiqueta ainda
aparece — em pilula, na borda esquerda — so que sem a ancoragem por altura.
Sao ETIQUETAS DE LEITURA: nenhuma delas e clicavel, nenhuma delas dispara
ordem.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

VELAS_MIN = 24
VELAS_MAX = 64
LARGURA_EIXO = 58

# PISO da janela de tempo, em minutos de pregao (nao teto — ver
# `slots_da_janela`). IMPRECISO: 540 minutos = 09:00-18:00 e um proxy
# honesto da sessao regular do WDO; nenhuma fonte em `pesquisa/*.md` fixa o
# horario de pregao, entao isto NAO e metodologia do autor. Serve para uma
# coisa so: com a sessao recem-aberta, segurar a largura da vela CONSTANTE
# em vez de deixar 3 candles ocuparem a tela inteira. Passado esse piso,
# quem define o tamanho da janela e o DADO — a janela sempre alcanca a
# primeira vela do tape.
MINUTOS_PREGAO = 540
# Largura minima de um slot. 3px (corpo de 2px + respiro) e o piso fisico:
# abaixo disso vela vira ruido. Era 5px, e num monitor mais estreito esse
# limite sozinho ja cortava as velas da abertura — o teto de pixel tem de
# ceder ate onde ainda da para desenhar, e so entao a janela vira PARCIAL.
LARGURA_MIN_SLOT = 3
FRACAO_CORPO = 0.62
# Slots de respiro entre a ultima vela e a escala de preco.
MARGEM_SLOTS = 2
ZOOM_PRECO_MIN = 0.2
ZOOM_PRECO_MAX = 8.0
LARGURA_ROTULO_NIVEL = 64
LINHAS_GRADE = 6

ALTURA_BARRA_CONTROLES = 16
LARGURA_CHIP_TIMEFRAME = 62
LARGURA_CHIP_AGORA = 54


def escala_fora_do_automatico(estado: EstadoNexo) -> bool:
    """A vista esta em algum ajuste MANUAL do operador? Funcao PURA.

    Tres coisas tiram o grafico do automatico: arrastar para o passado
    (`candles_offset`), mudar quantas velas cabem na janela
    (`candles_velas_visiveis`) e ampliar/achatar o eixo de preco
    (`candles_zoom_preco`). Era so a PRIMEIRA que acendia o chip de volta ao
    automatico, e o handler so desfazia essa — com o eixo ampliado em 4x,
    clicar no chip nao mudava nada e 85 das 116 velas do pregao ficavam fora
    da vista sem nenhum caminho de volta que nao fosse tentativa e erro no
    arrasto (medido em 28/08/2026). Quem decide se o afordance aparece e
    quem decide o que o clique desfaz leem esta MESMA funcao.
    """

    return (estado.candles_offset > 0
            or estado.candles_velas_visiveis is not None
            or abs(float(estado.candles_zoom_preco or 1.0) - 1.0) > 1e-9)


def retangulos_controles(rect: QRect) -> dict[str, QRect]:
    """Retangulos dos dois controles clicaveis do topo — chip "5M/15M" (troca
    de timeframe) e chip de volta ao AUTOMATICO (presente + escala neutra),
    desenhado sempre que a vista esta em ajuste manual.

    Funcao PURA e reaproveitada tanto por `desenhar` (pra pintar) quanto por
    quem trata o clique do mouse (`PainelNexoMercadoASG` em asg.py, ja que
    nenhuma regiao do NEXO e um QWidget proprio) — os dois lados usam
    exatamente a mesma conta, entao clique e desenho nunca divergem.
    """

    y = rect.top() + 1
    chip_timeframe = QRect(rect.left() + LARGURA_ROTULO_NIVEL + 4, y,
                           LARGURA_CHIP_TIMEFRAME, ALTURA_BARRA_CONTROLES)
    chip_agora = QRect(rect.right() - LARGURA_CHIP_AGORA - 4, y,
                       LARGURA_CHIP_AGORA, ALTURA_BARRA_CONTROLES)
    return {"timeframe": chip_timeframe, "agora": chip_agora}


def slots_da_janela(largura_regiao: int, timeframe_min: int,
                    velas_visiveis: int | None = None,
                    total_velas: int | None = None) -> int:
    """Quantas velas cabem na janela — o ZOOM DE TEMPO do grafico.

    `velas_visiveis=None` e o padrao: a janela cobre a SESSAO INTEIRA
    disponivel (`total_velas`, quantas velas o dia realmente tem), nunca um
    teto de relogio. Qualquer outro valor vem do operador (roda do mouse ou
    arrasto na escala de tempo) e e limitado entre `VELAS_MIN` e esse mesmo
    padrao — abaixo de `VELAS_MIN` a leitura vira lupa sem contexto; acima,
    nao ha mais sessao para mostrar. O zoom-out, portanto, para exatamente
    na primeira vela do tape, e nao antes dela.

    Funcao PURA, compartilhada com `asg.py` para que o clique/arrasto e o
    desenho concordem sobre onde cada vela esta.
    """
    largura_plot = max(80, largura_regiao - LARGURA_EIXO - LARGURA_ROTULO_NIVEL)
    tf = max(1, int(timeframe_min or 5))
    # DEFEITO CORRIGIDO (28/08/2026): a janela era o TETO fixo
    # `MINUTOS_PREGAO // tf` (108 slots de 5M) enquanto o dia real tem 116
    # velas — as 8 primeiras, justamente as da ABERTURA que originaram a
    # queixa do operador, ficavam fora e so apareciam arrastando, com o
    # rotulo ainda prometendo "JANELA DO PREGAO". Agora quem manda e o DADO:
    # a janela cresce ate caber a primeira vela do tape.
    #
    # `MINUTOS_PREGAO` sobra como PISO, nao como teto, e e por isso que ele
    # continua util mesmo sendo IMPRECISO (nenhuma fonte em `pesquisa/*.md`
    # fixa o horario de sessao): com 3 velas na abertura, uma janela colada
    # no dado daria velas gigantes que encolheriam o dia inteiro — que foi o
    # defeito da primeira rodada. O piso segura a largura da vela constante
    # desde o primeiro negocio; o dado so empurra a janela para CIMA.
    piso_pregao = max(VELAS_MIN, MINUTOS_PREGAO // tf)
    exigido_pelo_dado = int(total_velas or 0) + MARGEM_SLOTS
    teto_por_pixel = max(VELAS_MIN, largura_plot // LARGURA_MIN_SLOT)
    padrao = max(VELAS_MIN, min(max(piso_pregao, exigido_pelo_dado), teto_por_pixel))
    if velas_visiveis is None:
        return padrao
    return max(VELAS_MIN, min(padrao, int(velas_visiveis)))


def total_disponivel(estado: EstadoNexo) -> int:
    """Quantas velas o dia tem ATE onde o operador arrastou (o pan corta o
    presente, nao o passado). E este numero, e nao um relogio, que define o
    tamanho da janela padrao. Funcao PURA."""

    total = len(estado.candles_m15 or ())
    if total == 0:
        return 0
    return max(1, total - max(0, estado.candles_offset))


def janela_do_estado(rect: QRect, estado: EstadoNexo) -> int:
    """`slots_da_janela` alimentado pelo estado do quadro — o unico caminho
    que o desenho e os handlers usam, para que ninguem esqueca o total de
    velas e volte a cravar um teto de relogio. Funcao PURA."""

    return slots_da_janela(rect.width(), estado.candles_timeframe_min,
                           estado.candles_velas_visiveis, total_disponivel(estado))


def retangulo_eixo_preco(rect: QRect) -> QRect:
    """Calha da escala de PRECO (direita). Arrastar aqui na vertical
    comprime/expande a escala de preco — e onde o operador espera pegar,
    igual ao eixo do Profit. Mesma conta do `gutter_eixo` de `desenhar`."""
    topo = rect.top() + 14 + ALTURA_BARRA_CONTROLES
    return QRect(rect.right() - LARGURA_EIXO, topo, LARGURA_EIXO,
                 max(20, rect.bottom() - topo))


def retangulo_eixo_tempo(rect: QRect) -> QRect:
    """Faixa da escala de TEMPO (rodape). Arrastar aqui na horizontal
    comprime/expande quantas velas cabem na janela."""
    return QRect(rect.left() + LARGURA_ROTULO_NIVEL, rect.bottom() - 16,
                 max(20, rect.width() - LARGURA_EIXO - LARGURA_ROTULO_NIVEL), 16)


def largura_slot_px(largura_regiao: int, timeframe_min: int,
                    velas_visiveis: int | None = None,
                    total_velas: int | None = None) -> float:
    """Largura de UM slot de tempo em pixels, para uma regiao desta largura.

    Mesma conta que `desenhar` usa para posicionar as velas — exposta porque
    o arrasto (tratado em `asg.py`, ja que nenhuma regiao do NEXO e widget)
    precisa converter pixels arrastados em CANDLES deslocados. Se as duas
    contas divergissem, arrastar 100px moveria o grafico uma distancia
    diferente da que o dedo percorreu. Funcao PURA.
    """
    largura_plot = max(80, largura_regiao - LARGURA_EIXO - LARGURA_ROTULO_NIVEL)
    return largura_plot / slots_da_janela(largura_regiao, timeframe_min,
                                          velas_visiveis, total_velas)


def retangulo_plot(rect: QRect) -> QRect:
    """Area util do grafico (sem controles, sem eixos). Funcao PURA.

    Exposta pelo MESMO motivo de `largura_slot_px`: outra regiao precisa da
    conta exata, e duas copias da formula divergem. Aqui quem precisa e o
    Renko (`nexo/forca.py`), que tem de desenhar na MESMA escala vertical
    deste grafico — ver `px_por_tick`.
    """

    return QRect(rect.left() + LARGURA_ROTULO_NIVEL,
                 rect.top() + 14 + ALTURA_BARRA_CONTROLES,
                 max(80, rect.width() - LARGURA_EIXO - LARGURA_ROTULO_NIVEL),
                 max(60, rect.height() - 46 - ALTURA_BARRA_CONTROLES))


def velas_no_quadro(rect: QRect, estado: EstadoNexo) -> tuple:
    """As velas que este quadro realmente mostra. Funcao PURA."""

    candles_completos = tuple(estado.candles_m15 or ())
    if not candles_completos:
        return ()
    fim = max(1, len(candles_completos) - max(0, estado.candles_offset))
    candles = candles_completos[:fim]
    # A janela respeita o ZOOM DE TEMPO do operador (slots_da_janela), senao
    # o Renko (que le esta funcao) enquadraria um trecho diferente do que o
    # candle esta mostrando depois de um zoom.
    n_slots = janela_do_estado(rect, estado)
    return tuple(candles[-(n_slots - MARGEM_SLOTS):])


def slot_da_ultima_vela(rect: QRect, estado: EstadoNexo) -> int:
    """Em que slot da janela a ULTIMA vela desenhada mora. Funcao PURA.

    Enquanto a sessao nao encheu a janela, o slot 0 e a primeira vela do dia
    (o grafico cresce da esquerda); depois a janela desliza e a ultima vela
    fica fixa perto da borda direita. Exposta porque o crosshair precisa
    fazer o caminho inverso (pixel -> vela) com a MESMA conta do desenho.
    """

    velas = velas_no_quadro(rect, estado)
    if not velas:
        return 0
    n_slots = janela_do_estado(rect, estado)
    disponivel = total_disponivel(estado)
    if len(velas) <= n_slots - MARGEM_SLOTS and disponivel <= n_slots - MARGEM_SLOTS:
        return len(velas) - 1
    return n_slots - 1 - MARGEM_SLOTS


def indice_vela_em(rect: QRect, estado: EstadoNexo, x: int) -> int | None:
    """Indice (dentro de `velas_no_quadro`) da vela sob a coluna `x`, ou None
    quando o ponto cai fora do plot ou num slot de tempo ainda sem vela.
    Funcao PURA — e o inverso exato do `x_vela` que `desenhar` usa.
    """

    velas = velas_no_quadro(rect, estado)
    if not velas:
        return None
    area_plot = retangulo_plot(rect)
    if not (area_plot.left() <= x <= area_plot.right()):
        return None
    n_slots = janela_do_estado(rect, estado)
    largura_slot = area_plot.width() / n_slots
    slot = int((x - area_plot.left()) / largura_slot)
    indice = len(velas) - 1 - (slot_da_ultima_vela(rect, estado) - slot)
    if 0 <= indice < len(velas):
        return indice
    return None


def velas_fora_da_escala(rect: QRect, estado: EstadoNexo) -> int:
    """Quantas velas visiveis nao cabem no eixo COMO ELE ESTA. Funcao PURA.

    Com a escala em automatico isto e sempre 0, por construcao: o eixo
    enquadra o dado observado inteiro, maxima e minima do pregao incluidas.
    Passa de 0 so quando o proprio operador amplia a escala de preco
    (`candles_zoom_preco > 1`) e empurra vela para fora do recorte. E ai o
    numero e declarado no cabecalho — o que sai da vista sai DECLARADO, e
    quem tirou foi o operador, com um controle que ele desfaz.

    Uma versao anterior (28/08/2026) enquadrava por percentil p05-p95 para
    se defender de um "print aberrante" que eu tinha medido errado — o
    patamar estranho vinha do MEU harness de captura, que aplicava a fixture
    de livro sem desligar `_registrar_amostra`, e nao do tape (158.440
    negocios reais entre 10.291 e 10.359 ticks, nenhum fora disso). Recorte
    por percentil descarta extremo legitimo POR CONSTRUCAO: seria o eixo
    amputando a maxima e a minima do dia, que sao justamente os precos que o
    operador mais olha. Nao voltar a fazer isso.
    """

    velas = velas_no_quadro(rect, estado)
    faixa = faixa_de_precos(rect, estado)
    if not velas or faixa is None:
        return 0
    minimo, maximo = faixa
    return sum(1 for c in velas if c.low < minimo or c.high > maximo)


def faixa_de_precos(rect: QRect, estado: EstadoNexo) -> tuple[int, int] | None:
    """(minimo, maximo) em ticks que o eixo de preco enquadra. Funcao PURA.

    Enquadra o DADO OBSERVADO: a minima e a maxima de todas as velas
    visiveis, mais uma margem de respiro. Sem recorte estatistico, sem
    descarte de extremo — ver `velas_fora_da_escala`.
    """

    velas = velas_no_quadro(rect, estado)
    if not velas:
        return None
    precos = [c.high for c in velas] + [c.low for c in velas]
    minimo, maximo = min(precos), max(precos)
    margem = max(1, (maximo - minimo) // 12)
    minimo -= margem
    maximo += margem
    # ZOOM DE PRECO do operador entra AQUI, e nao so no desenho: quem copia a
    # escala (o Renko) tem de acompanhar o zoom junto, senao as duas regioes
    # descolam de novo no primeiro arrasto do eixo.
    zoom_preco = max(0.2, min(8.0, float(estado.candles_zoom_preco or 1.0)))
    if abs(zoom_preco - 1.0) > 1e-9:
        centro = (maximo + minimo) / 2
        meia = max(1.0, (maximo - minimo) / 2 / zoom_preco)
        minimo, maximo = int(centro - meia), int(centro + meia) + 1
    return minimo, maximo


def px_por_tick(rect: QRect, estado: EstadoNexo) -> float:
    """Pixels por TICK do eixo vertical deste grafico. Funcao PURA.

    Este e o numero que o Renko copia para nao mentir sobre amplitude. Sem
    ele as duas regioes usavam escalas independentes (medido em 28/08/2026:
    ~44,6 px/pt no Renko contra ~13,7 px/pt no candle, 3,3x de diferenca) e o
    olho comparava amplitudes falsas entre uma regiao e a vizinha. Devolve
    0.0 quando ainda nao ha vela — quem chama decide o que fazer sem escala.
    """

    faixa = faixa_de_precos(rect, estado)
    if faixa is None:
        return 0.0
    minimo, maximo = faixa
    escala = max(1, maximo - minimo)
    return max(1, retangulo_plot(rect).height() - 1) / escala


def _rotulo_janela(estado: EstadoNexo, n_slots: int) -> str:
    """O que o cabecalho pode HONESTAMENTE prometer sobre a janela.

    "JANELA DO PREGAO" so quando a janela cabe TODAS as velas disponiveis do
    dia — era exatamente aqui que a versao anterior mentia: prometia o
    pregao inteiro com um teto de 108 slots enquanto o dia tinha 116 velas,
    e as 8 da abertura so apareciam arrastando. Quando o dia nao cabe
    (janela limitada pela largura em pixels), o rotulo diz PARCIAL e informa
    quantas velas ficaram fora.
    """

    total = total_disponivel(estado)
    if estado.candles_velas_visiveis is not None:
        return "ESCALA MANUAL"
    if n_slots - MARGEM_SLOTS >= total:
        return "JANELA DO PREGAO"
    return f"JANELA PARCIAL · {total - (n_slots - MARGEM_SLOTS)} VELAS ATRAS"


def _desenhar_chip(painter: QPainter, caixa: QRect, texto: str, cor, *, preenchido: bool) -> None:
    painter.setPen(Qt.PenStyle.NoPen if preenchido else QPen(cor, 1))
    painter.setBrush(cor if preenchido else Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(caixa, 3, 3)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_FUNDO if preenchido else cor)
    painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, texto)


def _pilula_preco(
    painter: QPainter,
    x_ancora: int,
    y_centro: int,
    texto: str,
    cor,
    *,
    alinhar_direita: bool,
    largura_max: int,
) -> None:
    """Pilula (capsula arredondada) com fundo colorido e texto centralizado.

    Usada para toda etiqueta de preco ancorada num ponto do grafico — borda
    esquerda dos niveis consultivos, limites da faixa observada e o preco
    corrente na borda direita. Um unico desenho para as tres, para nao
    divergirem em raio, fonte ou contraste de texto.
    """
    metrica: QFontMetrics = painter.fontMetrics()
    largura = min(largura_max, metrica.horizontalAdvance(texto) + 12)
    altura = metrica.height() + 4
    if alinhar_direita:
        area = QRect(x_ancora - largura, y_centro - altura // 2, largura, altura)
    else:
        area = QRect(x_ancora, y_centro - altura // 2, largura, altura)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    painter.drawRoundedRect(area, altura / 2, altura / 2)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(tema_asg.NEXO_FUNDO)
    painter.drawText(area, Qt.AlignmentFlag.AlignCenter, texto)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 60 or rect.width() < 120:
        return
    candles_completos = estado.candles_m15
    painter.fillRect(rect, tema_asg.NEXO_PAINEL)
    if len(candles_completos) < 1:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "AGUARDANDO PRIMEIRO NEGOCIO DA SESSAO")
        return

    # Arrastar o grafico (pedido do operador, 27/08/2026): `candles_offset`
    # e quantos candles mais recentes ficam fora da janela — 0 e o presente.
    # Fatiar aqui, ANTES de calcular a escala de preco, para o eixo Y
    # tambem refletir a janela historica visivel, nunca o dia inteiro
    # comprimido atras dela.
    fim = max(1, len(candles_completos) - max(0, estado.candles_offset))
    candles = candles_completos[:fim]
    arrastado = estado.candles_offset > 0
    manual = escala_fora_do_automatico(estado)

    area_plot = retangulo_plot(rect)
    area_volume = QRect(area_plot.left(), area_plot.bottom() + 4, area_plot.width(),
                        max(12, rect.bottom() - area_plot.bottom() - 18))

    # DEFEITO CORRIGIDO (27/08/2026): a vela mudava de tamanho o pregao
    # inteiro. A largura vinha de `area_plot.width() // (len(velas) * 2)`,
    # ou seja, era funcao de QUANTAS velas existiam — com 2 candles na
    # abertura cada corpo tinha ~170px (o "retangulo verde gigante") e ia
    # encolhendo a cada candle novo. Agora a grade de tempo e FIXA: o eixo X
    # e dividido em `n_slots` fatias do tamanho de um candle do timeframe
    # corrente, cobrindo a janela do pregao. A vela ocupa sempre a mesma
    # fracao de um slot, do primeiro negocio da sessao ao ultimo.
    tf_min = max(1, int(estado.candles_timeframe_min or 5))
    # ZOOM DE TEMPO: `candles_velas_visiveis` e None enquanto o operador nao
    # mexeu na escala (janela do pregao inteiro). A conta vive em
    # `slots_da_janela`, compartilhada com os handlers de mouse.
    n_slots = janela_do_estado(rect, estado)
    largura_slot = area_plot.width() / n_slots
    margem_slots = MARGEM_SLOTS
    velas = list(velas_no_quadro(rect, estado))
    # Ancoragem da janela: enquanto a sessao nao encheu a janela do pregao,
    # o slot 0 e o PRIMEIRO candle do dia e o grafico cresce da esquerda
    # para a direita — o vazio a direita e o tempo de pregao que ainda nao
    # aconteceu, e a escala de tempo abaixo o rotula como tal. Quando a
    # sessao passa da janela, ela desliza e a ultima vela fica fixa perto da
    # borda direita. Nos dois casos a LARGURA da vela e a mesma.
    slot_da_ultima = slot_da_ultima_vela(rect, estado)

    def x_slot(slot: float) -> int:
        return area_plot.left() + int((slot + 0.5) * largura_slot)

    def x_vela(indice: int) -> int:
        return x_slot(slot_da_ultima - (len(velas) - 1 - indice))

    # Faixa de preco (com margem e com o ZOOM DE PRECO do operador ja
    # aplicado) vem da funcao pura — a MESMA que o Renko consulta para copiar
    # a escala vertical. Duas copias da formula divergiriam no primeiro
    # arrasto do eixo.
    minimo, maximo = faixa_de_precos(rect, estado)
    escala = max(1, maximo - minimo)
    # Quantas velas o eixo nao enquadra — declarado no cabecalho logo abaixo.
    # Nada sai da vista em silencio (mesma convencao do VAP).
    fora_da_escala = velas_fora_da_escala(rect, estado)

    controles = retangulos_controles(QRect(rect.left(), rect.top() + 14,
                                           rect.width(), ALTURA_BARRA_CONTROLES))
    rotulo_tf = f"{estado.candles_timeframe_min}M"
    _desenhar_chip(painter, controles["timeframe"], f"⇄ {rotulo_tf}",
                  tema_asg.NEXO_CIANO, preenchido=False)
    if manual:
        # O chip aparece em QUALQUER ajuste manual, nao so no arrasto: com o
        # eixo ampliado e sem chip, o operador nao tinha por onde voltar.
        # "AGORA" quando ele so andou no tempo; "AUTO" quando a escala
        # tambem esta fora do neutro, porque e isso que o clique devolve.
        _desenhar_chip(painter, controles["agora"],
                      "› AGORA" if arrastado and estado.candles_velas_visiveis is None
                      and abs(float(estado.candles_zoom_preco or 1.0) - 1.0) <= 1e-9
                      else "› AUTO",
                      tema_asg.NEXO_AMARELO, preenchido=True)
    # Diz explicitamente o que a janela cobre e quanto dela a sessao ja
    # preencheu — sem isto, uma sessao recem-aberta (poucas velas num eixo de
    # pregao inteiro) parece grafico quebrado, quando e so tempo que ainda
    # nao passou.
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        QRect(controles["timeframe"].right() + 8, controles["timeframe"].top(),
              max(10, controles["agora"].left() - controles["timeframe"].right() - 16),
              ALTURA_BARRA_CONTROLES),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        (f"{_rotulo_janela(estado, n_slots)}"
         + (f" · {fora_da_escala} VELAS FORA DA ESCALA" if fora_da_escala else "")
         + f" · {n_slots} VELAS DE {tf_min}M · {len(velas)} FORMADAS"
         f" · PRECO x{max(0.2, min(8.0, float(estado.candles_zoom_preco or 1.0))):.2f}"
         "  ⇔ ARRASTE O RODAPE · ⇕ ARRASTE A ESCALA · RODA = ZOOM"))

    painter.fillRect(area_plot, tema_asg.NEXO_PAINEL_ALTO)

    def y_preco(valor: int) -> int:
        return area_plot.bottom() - round(
            (valor - minimo) * max(1, area_plot.height() - 1) / escala)

    ultimo_valor = candles[-1].close
    # Preso ao plot pelo mesmo motivo da faixa: com zoom de preco o ultimo
    # negocio pode cair fora do recorte, e a capsula nao pode vazar da regiao.
    y_ultimo = max(area_plot.top() + 9, min(area_plot.bottom() - 9, y_preco(ultimo_valor)))
    altura_capsula_ultimo = 18
    exclusao_topo = y_ultimo - altura_capsula_ultimo // 2 - 2
    exclusao_base = y_ultimo + altura_capsula_ultimo // 2 + 2

    # A calha do eixo (faixa a direita do plot onde os ticks moram) usa o
    # MESMO fundo escuro do plot — nunca fica transparente, nunca herda a
    # cor de um vizinho. E os valores da escada vem da faixa REAL de precos
    # (min..max em ticks inteiros), nunca de uma fracao fixa de altura: com
    # a amostra quase parada, 6 linhas por fracao de altura repetiam o
    # MESMO preco formatado em ate 4 ticks seguidos. Aqui o numero de linhas
    # se adapta a quantos ticks distintos a faixa realmente comporta, e cada
    # linha nasce do proprio valor (y_preco), nunca o inverso — garante
    # escada monotonica, sem repeticao.
    gutter_eixo = QRect(area_plot.right(), area_plot.top(), LARGURA_EIXO,
                        area_volume.bottom() - area_plot.top())
    painter.fillRect(gutter_eixo, tema_asg.NEXO_PAINEL_ALTO)
    n_linhas = max(2, min(LINHAS_GRADE, escala + 1))
    valor_anterior: int | None = None
    for indice in range(n_linhas):
        valor = maximo - round(indice * escala / max(1, n_linhas - 1))
        if valor_anterior is not None and valor == valor_anterior:
            continue
        valor_anterior = valor
        y = y_preco(valor)
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawLine(area_plot.left(), y, area_plot.right(), y)
        if exclusao_topo <= y <= exclusao_base:
            # A pilula do ultimo preco (desenhada mais abaixo, na borda
            # direita) ja mostra este mesmo valor — nao empilhar o rotulo
            # do tick por baixo dela, ou ele fica ilegivel sob a pilula
            # opaca (era assim que um tick da escada "sumia").
            continue
        texto = formato.formatar_preco(estado.grid, valor)
        painter.setFont(tokens.fonte_numero(7))
        painter.setPen(tema_asg.NEXO_TEXTO)
        painter.drawText(QRect(area_plot.right() + 4, y - 7, LARGURA_EIXO - 6, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{texto[0]}{texto[1]}")
    # Escala de TEMPO: as verticais nascem dos proprios slots de tempo (nao
    # de uma fracao arbitraria da largura), entao cada linha cai exatamente
    # sobre uma vela e vira uma marca de hora legivel no rodape — que e o
    # que a escala horizontal do Profit faz. Passo escolhido para dar ~7
    # divisoes independentemente do timeframe.
    passo_marcas = max(1, n_slots // 8)
    tf_ns = tf_min * 60 * 1_000_000_000
    t_ultima = velas[-1].timestamp_ns
    marcas: list[tuple[int, str]] = []
    painter.setPen(tema_asg.NEXO_GRADE)
    for slot in range(0, n_slots, passo_marcas):
        x = x_slot(slot)
        painter.drawLine(x, area_plot.top(), x, area_volume.bottom())
        # Hora do slot projetada do timeframe — o eixo cobre a janela toda,
        # inclusive os slots que a sessao ainda nao preencheu. E aritmetica
        # de calendario do proprio timeframe, nao previsao de preco nenhuma.
        instante = t_ultima + (slot - slot_da_ultima) * tf_ns
        if instante < 0:
            continue
        marcas.append((x, formato.formatar_hora_ns(instante)[:5]))

    # Faixa observada: intervalo das amostras recentes. Alem do preenchimento
    # (ja existia), a borda tracejada e as pilulas de limite na borda
    # esquerda deixam a REGIAO explicita — nao so uma mancha de cor.
    recentes_candles = candles[-max(8, len(candles) // 5):]
    recentes = [c.high for c in recentes_candles] + [c.low for c in recentes_candles]
    faixa_min, faixa_max = min(recentes), max(recentes)
    # Com o eixo ampliado pelo operador, a faixa observada pode ficar maior
    # que a janela visivel: prender aos limites do plot para que nem a
    # mancha, nem a borda tracejada, nem as pilulas de limite vazem por cima
    # da regiao vizinha (foi o que aconteceu com zoom de preco 2,5x).
    y_topo = max(area_plot.top(), min(area_plot.bottom(), y_preco(faixa_max)))
    y_base = max(area_plot.top(), min(area_plot.bottom(), y_preco(faixa_min)))
    if faixa_max > faixa_min and y_base > y_topo:
        # A faixa termina onde a sessao terminou: pintar ate a borda direita
        # alegaria observacao sobre slots de tempo que ainda nao existem — e,
        # com poucas velas, transformava o grafico inteiro num bloco de cor.
        direita_dados = min(area_plot.right(),
                           x_vela(len(velas) - 1) + max(2, int(largura_slot)))
        faixa = QRect(area_plot.left(), y_topo,
                      max(8, direita_dados - area_plot.left()), max(2, y_base - y_topo))
        painter.fillRect(faixa, tema_asg.NEXO_CIANO_FAIXA)
        # Mesma correcao de ancoragem dos niveis: a pilula de limite da
        # faixa mora em rect.left() (gutter reservado), entao a borda
        # tracejada tem que nascer dali tambem — senao a pilula fica
        # boiando a alguns pixels do proprio traco que ela rotula. A borda
        # da base so estica ate a pilula quando a pilula da base de fato
        # vai aparecer (mesma condicao de espaco usada mais abaixo).
        mostra_pilula_base = faixa.bottom() - faixa.top() > 16
        painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
        painter.drawLine(rect.left(), faixa.top(), faixa.right(), faixa.top())
        x_base = rect.left() if mostra_pilula_base else faixa.left()
        painter.drawLine(x_base, faixa.bottom(), faixa.right(), faixa.bottom())
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(faixa.adjusted(5, 1, -5, -1),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         "FAIXA OBSERVADA")
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        _pilula_preco(painter, rect.left(), faixa.top(),
                     formato.preco_completo(estado.grid, faixa_max), tema_asg.NEXO_CIANO,
                     alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)
        if mostra_pilula_base:
            painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
            _pilula_preco(painter, rect.left(), faixa.bottom(),
                         formato.preco_completo(estado.grid, faixa_min), tema_asg.NEXO_CIANO,
                         alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)

    # Com zoom de preco a faixa visivel fica menor que a amplitude das velas:
    # sem recorte, pavio e corpo vazariam para fora do plot e por cima da
    # escala. O recorte e so de PINTURA — nenhuma vela e descartada do dado.
    painter.save()
    painter.setClipRect(QRect(area_plot.left(), area_plot.top(), area_plot.width(),
                              area_volume.bottom() - area_plot.top() + 1))
    max_volume = max(1, max(candle.volume for candle in velas))
    # Largura CONSTANTE: fracao fixa do slot de tempo, nunca funcao da
    # quantidade de velas ja formadas.
    largura = max(2, int(largura_slot * FRACAO_CORPO))
    fechamentos: list[QPoint] = []
    for indice, candle in enumerate(velas):
        abertura, fechamento = candle.open, candle.close
        maxima, minima = candle.high, candle.low
        x = x_vela(indice)
        cor = tema_asg.NEXO_VERDE if fechamento >= abertura else tema_asg.NEXO_ROSA
        painter.setPen(QPen(cor, 1))
        painter.drawLine(x, y_preco(maxima), x, y_preco(minima))
        y_abertura, y_fechamento = y_preco(abertura), y_preco(fechamento)
        # Corpo com contorno: doji (abertura == fechamento) vira um traco de
        # 1px, como no Profit — nunca um bloco de 2px que finge corpo.
        topo_corpo = min(y_abertura, y_fechamento)
        altura_corpo = abs(y_fechamento - y_abertura)
        if altura_corpo < 1:
            painter.setPen(QPen(cor, 1))
            painter.drawLine(x - largura // 2, topo_corpo, x + largura // 2, topo_corpo)
        else:
            painter.fillRect(QRect(x - largura // 2, topo_corpo, largura, altura_corpo), cor)
        volume = candle.volume
        altura_volume = max(2, round(volume * max(1, area_volume.height() - 2) / max_volume))
        painter.fillRect(QRect(x - largura // 2, area_volume.bottom() - altura_volume,
                               largura, altura_volume), cor)
        fechamentos.append(QPoint(x, y_fechamento))
    painter.restore()

    # Anotacao junto ao ultimo negocio realmente observado — nao e um alvo
    # nem uma leitura preditiva, so identifica onde o ultimo preco recebido
    # ficou no grafico (mesmo dado do rodape "OHLC CAUSAL").
    if fechamentos:
        ultimo_ponto = fechamentos[-1]
        # Arrastado, este NAO e o ultimo negocio do pregao — e so o ultimo
        # candle dentro da janela historica que o operador escolheu ver.
        # Chamar de "ultimo negocio observado" enquanto arrastado alegaria
        # atualidade que a tela nao tem.
        texto_tag = "FECHAMENTO DESTA VELA" if arrastado else "ULTIMO NEGOCIO OBSERVADO"
        painter.setFont(tokens.fonte_rotulo(6))
        metrica_tag = painter.fontMetrics()
        largura_tag = metrica_tag.horizontalAdvance(texto_tag) + 10
        altura_tag = metrica_tag.height() + 4
        if ultimo_ponto.y() - area_plot.top() > altura_tag + 6:
            y_tag = ultimo_ponto.y() - altura_tag - 6
        else:
            y_tag = min(area_plot.bottom() - altura_tag, ultimo_ponto.y() + 6)
        x_tag = min(area_plot.right() - largura_tag,
                   max(area_plot.left(), ultimo_ponto.x() - largura_tag // 2))
        tag = QRect(x_tag, y_tag, largura_tag, altura_tag)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
        painter.drawRoundedRect(tag, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, texto_tag)

    # ultimo_valor/y_ultimo ja foram calculados acima (mesma fronteira
    # y_preco), reaproveitados aqui para a linha tracejada + pilula.
    painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DashLine))
    painter.drawLine(area_plot.left(), y_ultimo, area_plot.right(), y_ultimo)
    ultimo = formato.formatar_preco(estado.grid, ultimo_valor)
    capsula = QRect(area_plot.right() + 2, y_ultimo - 9, LARGURA_EIXO - 4, 18)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_CIANO)
    painter.drawRoundedRect(capsula, 9, 9)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    painter.setPen(tema_asg.NEXO_FUNDO)
    painter.drawText(capsula, Qt.AlignmentFlag.AlignCenter, f"{ultimo[0]}{ultimo[1]}")

    # Niveis consultivos so aparecem quando a decisao os publicou. Sao
    # ETIQUETAS DE LEITURA: nao ha acao, ordem ou clique associado a elas.
    # Ancoragem: quando o nivel chega como INTEIRO de ticks, a linha e a
    # pilula da borda esquerda vao para a altura real do preco (y_preco) —
    # a mesma fronteira de conversao usada no resto do grafico, preco nunca
    # deixa de ser int antes disso. Se chegar como texto ja formatado
    # (fonte de decisao antiga), cai no layout empilhado anterior em vez de
    # sumir ou quebrar.
    decisao = estado.snapshot.decisao
    niveis = (("STOP", decisao.stop, tema_asg.NEXO_ROSA),
              ("A1", decisao.alvo_1, tema_asg.NEXO_VERDE),
              ("A2", decisao.alvo_2, tema_asg.NEXO_VERDE),
              ("A3", decisao.alvo_3, tema_asg.NEXO_VERDE))
    for indice, (nome, valor, cor) in enumerate(niveis):
        if valor == "—":
            continue
        ticks: int | None
        try:
            ticks = int(valor)
        except (TypeError, ValueError):
            ticks = None
        if ticks is not None:
            y = max(area_plot.top(), min(area_plot.bottom(), y_preco(ticks)))
            texto_nivel = f"{nome} {formato.preco_completo(estado.grid, ticks)}"
        else:
            y = area_plot.top() + 14 + indice * 14
            texto_nivel = f"{nome} {valor}"
        # A linha nasce na MESMA borda esquerda onde a pilula e ancorada
        # (rect.left(), nao area_plot.left()) — sem isso a pilula fica
        # boiando no gutter reservado a ela, a distancia do plot, sem
        # nenhum traco a ligando ao proprio nivel que ela rotula.
        painter.setPen(QPen(cor, 1, Qt.PenStyle.DotLine))
        painter.drawLine(rect.left(), y, area_plot.right(), y)
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        _pilula_preco(painter, rect.left(), y, texto_nivel, cor,
                     alinhar_direita=False, largura_max=LARGURA_ROTULO_NIVEL - 4)

    # Escala de tempo no rodape, uma marca por vertical da grade — mesma
    # coordenada, entao rotulo e linha nunca divergem. As marcas sao
    # desenhadas primeiro e o rotulo da regiao vai a direita, no canto que
    # sobra, para nao colidir com hora nenhuma.
    rodape = QRect(area_plot.left(), rect.bottom() - 13, area_plot.width(), 13)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    metrica_hora = painter.fontMetrics()
    x_ocupado = area_plot.left() - 999
    for x_marca, texto_hora in marcas:
        largura_hora = metrica_hora.horizontalAdvance(texto_hora)
        x_texto = x_marca - largura_hora // 2
        if x_texto < x_ocupado + 6 or x_texto + largura_hora > area_plot.right():
            continue
        painter.drawText(QRect(x_texto, rodape.top(), largura_hora, rodape.height()),
                         Qt.AlignmentFlag.AlignCenter, texto_hora)
        x_ocupado = x_texto + largura_hora
    painter.drawText(QRect(area_plot.right() + 2, rodape.top(),
                           LARGURA_EIXO - 2, rodape.height()),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo_tf)

    # ------------------------------------------------------------------
    # CROSSHAIR e LEITURA DA VELA (achado de 28/08/2026: depois do zoom o
    # operador via a forma da vela mas nao conseguia LER o preco dela).
    #
    # Duas coisas, uma so fonte de dado — a vela apontada, ou a ULTIMA
    # quando o cursor esta fora: (1) a linha-cruz, com o preco na altura do
    # cursor e a hora na coluna dele; (2) o readout O/H/L/C + variacao, que
    # fica SEMPRE visivel, como o cabecalho do grafico de referencia.
    # Variacao = (fechamento - abertura) / abertura da PROPRIA vela: e
    # aritmetica do candle exibido, nao indicador nem projecao.
    # ------------------------------------------------------------------
    cursor = estado.candles_cursor
    indice_lido = None
    if cursor is not None:
        indice_lido = indice_vela_em(rect, estado, cursor[0])
    vela_lida = velas[indice_lido] if indice_lido is not None else velas[-1]
    apontada = indice_lido is not None

    if cursor is not None and area_plot.left() <= cursor[0] <= area_plot.right():
        y_cursor = max(area_plot.top(), min(area_plot.bottom(), cursor[1]))
        x_cursor = x_vela(indice_lido) if apontada else cursor[0]
        painter.setPen(QPen(tema_asg.NEXO_TEXTO, 1, Qt.PenStyle.DotLine))
        painter.drawLine(x_cursor, area_plot.top(), x_cursor, area_volume.bottom())
        painter.drawLine(area_plot.left(), y_cursor, area_plot.right(), y_cursor)
        # Preco na altura do cursor: converte pixel de volta para TICK
        # inteiro pela inversa exata de `y_preco` — nao existe preco
        # fracionario nem aqui, na leitura.
        tick_cursor = minimo + round(
            (area_plot.bottom() - y_cursor) * escala / max(1, area_plot.height() - 1))
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        _pilula_preco(painter, area_plot.right() + 2, y_cursor,
                     formato.preco_completo(estado.grid, int(tick_cursor)),
                     tema_asg.NEXO_TEXTO, alinhar_direita=False,
                     largura_max=LARGURA_EIXO - 4)
        if apontada:
            painter.setFont(tokens.fonte_rotulo(7))
            hora = formato.formatar_hora_ns(vela_lida.timestamp_ns)[:5]
            metrica_cursor = painter.fontMetrics()
            largura_hora = metrica_cursor.horizontalAdvance(hora) + 10
            caixa_hora = QRect(
                max(area_plot.left(),
                    min(area_plot.right() - largura_hora, x_cursor - largura_hora // 2)),
                rodape.top() - 1, largura_hora, rodape.height() + 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tema_asg.NEXO_TEXTO)
            painter.drawRoundedRect(caixa_hora, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(tema_asg.NEXO_FUNDO)
            painter.drawText(caixa_hora, Qt.AlignmentFlag.AlignCenter, hora)

    abertura_lida = vela_lida.open
    variacao = ((vela_lida.close - abertura_lida) / abertura_lida * 100.0
                if abertura_lida else 0.0)
    cor_variacao = (tema_asg.NEXO_VERDE if vela_lida.close >= abertura_lida
                    else tema_asg.NEXO_ROSA)
    campos = (
        ("ABR", formato.preco_completo(estado.grid, vela_lida.open), tema_asg.NEXO_TEXTO),
        ("MAX", formato.preco_completo(estado.grid, vela_lida.high), tema_asg.NEXO_VERDE),
        ("MIN", formato.preco_completo(estado.grid, vela_lida.low), tema_asg.NEXO_ROSA),
        ("FCH", formato.preco_completo(estado.grid, vela_lida.close), tema_asg.NEXO_TEXTO),
        ("VAR", f"{variacao:+.2f}%", cor_variacao),
        ("VOL", f"{vela_lida.volume:,}".replace(",", "."), tema_asg.NEXO_TEXTO),
    )
    faixa_leitura = QRect(area_plot.left(), area_plot.top() + 1, area_plot.width(), 13)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(tema_asg.NEXO_PAINEL)
    painter.drawRect(faixa_leitura)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    x_campo = faixa_leitura.left() + 4
    painter.setFont(tokens.fonte_rotulo(6))
    metrica_campo = painter.fontMetrics()
    # Diz de QUAL vela e a leitura: sem isto o operador nao sabe se esta
    # lendo a vela que apontou ou a ultima do pregao.
    prefixo = (f"{formato.formatar_hora_ns(vela_lida.timestamp_ns)[:5]} · "
               + ("VELA APONTADA" if apontada else "ULTIMA VELA"))
    painter.setPen(tema_asg.NEXO_CIANO if apontada else tema_asg.NEXO_MUTED)
    painter.drawText(QRect(x_campo, faixa_leitura.top(),
                           metrica_campo.horizontalAdvance(prefixo) + 2,
                           faixa_leitura.height()),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, prefixo)
    x_campo += metrica_campo.horizontalAdvance(prefixo) + 10
    # Larguras medidas com a fonte de CADA parte (rotulo pequeno, numero
    # maior): medir tudo com a fonte do rotulo encavalava o numero no
    # rotulo seguinte ("5.177,0MAX").
    metrica_numero = QFontMetrics(tokens.fonte_numero(7, QFont.Weight.Bold))
    for rotulo, texto_campo, cor_campo in campos:
        largura_campo = (metrica_campo.horizontalAdvance(rotulo) + 4
                         + metrica_numero.horizontalAdvance(texto_campo) + 12)
        if x_campo + largura_campo > faixa_leitura.right():
            break
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(QRect(x_campo, faixa_leitura.top(),
                               metrica_campo.horizontalAdvance(rotulo) + 2,
                               faixa_leitura.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo)
        deslocamento = metrica_campo.horizontalAdvance(rotulo) + 4
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        painter.setPen(cor_campo)
        painter.drawText(QRect(x_campo + deslocamento, faixa_leitura.top(),
                               largura_campo - deslocamento,
                               faixa_leitura.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         texto_campo)
        x_campo += largura_campo
