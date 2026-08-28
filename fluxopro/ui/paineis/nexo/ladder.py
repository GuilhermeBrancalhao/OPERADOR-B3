"""Regiao VAP — Volume At Price (x 0,00-0,11 · y 0,00-0,56).

Trocado de escada tipo DOM para VAP por pedido do operador: a fonte
(`pesquisa/ferramenta_componentes.md` §5, `f0hrhzhLDVM.txt`) descreve essa
regiao como "um vap, um volume profile, um volume at price" — mas
customizado, nao o perfil classico de plataforma de varejo.

Regras da fonte, com rotulo de confianca:

- **CONFIRMADO, numero exato** — "voce so vai dar importancia pra ela pra
  esses TRES precos que aparecem destacados... do contrario, voce esquece
  ela". So 3 niveis por vez sao "destacados"; o resto e "lixo" na
  linguagem do autor — mostrado apagado, NUNCA escondido (a fonte nunca
  fala em ocultar nivel, so em reduzir a importancia visual).
- **CONFIRMADO** — "quanto maior a barra, mais importancia ela tem": o
  comprimento da barra e o proprio volume negociado naquele preco.
- **CONFIRMADO** — zonas sem barra destacada ("lacunas") sao onde o preco
  "corre mais rapido" — o LVN classico, ja calculado por
  `VolumeProfile.lvn()`.
- **AUSENTE NA FONTE** — o criterio exato de SELECAO dos 3 destacados
  (o autor diz "eu filtrei do jeito que eu gosto" sem revelar a regra).
  Aqui o criterio e o volume total do nivel — maior proxy honesto
  disponivel, rotulado como tal, nunca apresentado como a formula do autor.
- **CONFIRMADO, decisao deliberada de design** — a fonte explicitamente NAO
  poe este painel do lado do grafico de candles ("nao vou por do lado do
  grafico... e para voces desfocarem do grafico"). Este painel continua
  isolado na lateral esquerda, longe do candle M5 — por design, nao por
  limitacao de espaco.

Reforma de 27/08/2026 (pedido literal do operador: "o VAP precisa ter um
visual mais moderno e completo, que mostre o volume diario, com destaques
para precos de maiores troca de lote e travamento do preco, e ter filtro
onde eu consiga avaliar nos 5 e 15M"). O que entrou, e de onde:

- **CONFIRMADO — `bar/volume_profile_text.txt` (Nelogica, Volume Profile)**
  "Barras por Agressao: representa em cores diferentes os volumes vindos de
  compra e venda". A barra de cada nivel deixa de ser um bloco de uma cor so
  e passa a ser dividida: o pedaco comprador em verde, o vendedor em rosa,
  na proporcao real do nivel. E a "maior troca de lote" do pedido.
- **CONFIRMADO — mesma fonte** "Destacar Maior Barra de Volume ... tambem e
  conhecida como POC (Point of Control)". O POC ganha linha propria marcada,
  com etiqueta, em vez do tracinho de 3px de antes.
- **CONFIRMADO — mesma fonte** "Exibir Volume Acumulado: o volume acumulado
  sera apresentado na parte esquerda do grafico". Dai a faixa de resumo com
  o volume total do perfil ativo (`estado.vap_volume_total`).
- **CONFIRMADO** — VAL/VAH vem de `VolumeProfile.value_area()` (70% do
  volume, padrao de mercado ja documentado no analytics); aqui viram uma
  faixa sombreada continua com as duas fronteiras rotuladas.
- **AUSENTE NA FONTE** — "travamento do preco" nao tem definicao na fonte.
  A leitura adotada, e rotulada como PROXY nesta docstring e no proprio
  rotulo da tela ("TRV"), e: nivel de volume alto (>= `PISO_TRAVAMENTO` do
  maior nivel visivel) cujo agressor esta EQUILIBRADO (|delta| / total <=
  `TETO_DESEQUILIBRIO_TRAVAMENTO`) — muito negocio sem vencedor, isto e,
  absorcao. Nao e a formula de ninguem; e a heuristica desta ferramenta.

Volume vem de `fluxopro.analytics.volume_profile.VolumeProfile`, alimentado
pelos MESMOS negocios que ja alimentam `estado.serie` — nunca um segundo
feed. Preco em `int` de ticks; a barra e so a fronteira de desenho.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

ALTURA_LINHA_MIN = 9
ALTURA_LINHA_MAX = 20
ALTURA_LINHA_ALVO = 14

FRACAO_LANE_PRECO = 0.30
FRACAO_LANE_PRECO_AGRUPADO = 0.46
"""Linha agrupada rotula a FAIXA de precos, que nao cabe na coluna de um
preco so — ver `rotulo_faixa`."""
LARGURA_MIN_LANE_PRECO = 34

LARGURA_MIN = 24
ALTURA_ROTULO = 12
ALTURA_MIN_PARA_ROTULO = 60

ALTURA_TITULO = 14
ALTURA_SELETOR = 17
ALTURA_RESUMO = 26
ALTURA_CABECALHO = ALTURA_TITULO + ALTURA_SELETOR + ALTURA_RESUMO
LARGURA_MIN_PARA_CROMO = 96
ALTURA_MIN_PARA_CROMO = 150

TIMEFRAMES: tuple[tuple[int, str], ...] = ((0, "SESSAO"), (5, "5M"), (15, "15M"))

PISO_TRAVAMENTO = 0.75
"""AUSENTE NA FONTE — fracao do maior nivel visivel a partir da qual um nivel
e candidato a "travamento". Heuristica desta ferramenta, nao do autor."""

FRACAO_VOLUME_NA_ESCALA = 0.995
"""AUSENTE NA FONTE — fracao do volume do perfil que a escada precisa cobrir.
Define a escala de preco pela MASSA de volume em vez dos extremos, para que um
print isolado longe do mercado nao arraste o eixo. Ver `faixa_por_volume`."""

LARGURA_LANE_VA = 26
"""Faixa a direita reservada ao rotulo VAH/VAL, para ele nunca dividir
coordenada com o numero de volume da linha — ver `retangulo_tag_va`."""

ALTURA_TAG_VA = 9

SALTO_MAX_TICKS = 10
"""AUSENTE NA FONTE — vao maximo, em ticks, que ainda conta como "colado" ao
juntar a cauda do perfil na escala (ver `faixa_por_volume`). WDO anda de 1 tick
em 1 tick; 10 ticks de vao vazio ja e outro mercado, nao a mesma sessao."""

TETO_DESEQUILIBRIO_TRAVAMENTO = 0.15
"""AUSENTE NA FONTE — |comprador - vendedor| / total maximo para o nivel
contar como absorcao (agressao equilibrada = ninguem venceu ali)."""


def retangulo_rotulo(rect: QRect) -> QRect:
    """Faixa inferior do rotulo — tambem o alvo de clique que CICLA o
    timeframe (SESSAO -> 5M -> 15M -> SESSAO). Funcao PURA, reaproveitada por
    `desenhar` (pintar) e por `PainelNexoMercadoASG.mousePressEvent`
    (hit-test), mesmo padrao de `candles.retangulos_controles`."""

    return QRect(rect.left(), rect.bottom() - ALTURA_ROTULO, rect.width(), ALTURA_ROTULO)


def retangulos_timeframe(rect: QRect) -> dict[int, QRect]:
    """Os tres segmentos do seletor SESSAO/5M/15M no topo da regiao.

    Selecao DIRETA (clicar em "15M" vai para 15M), diferente do rodape que
    so cicla. Devolve `{}` quando a regiao e pequena demais para o cromo —
    ai o rodape continua sendo o unico alvo, e nada e desenhado no vazio.
    """

    if rect.width() < LARGURA_MIN_PARA_CROMO or rect.height() < ALTURA_MIN_PARA_CROMO:
        return {}
    topo = rect.top() + ALTURA_TITULO
    largura = rect.width() - 4
    passo = largura / len(TIMEFRAMES)
    saida: dict[int, QRect] = {}
    for indice, (minutos, _) in enumerate(TIMEFRAMES):
        x0 = rect.left() + 2 + round(indice * passo)
        x1 = rect.left() + 2 + round((indice + 1) * passo)
        saida[minutos] = QRect(x0, topo, max(1, x1 - x0 - 1), ALTURA_SELETOR - 3)
    return saida


def _e_travamento(volume_total: int, comprador: int, vendedor: int, maior: int) -> bool:
    """PROXY de "travamento do preco" — ver docstring do modulo (AUSENTE NA FONTE)."""

    if volume_total <= 0 or maior <= 0:
        return False
    if volume_total < PISO_TRAVAMENTO * maior:
        return False
    atribuido = comprador + vendedor
    if atribuido <= 0:
        return False
    return abs(comprador - vendedor) / atribuido <= TETO_DESEQUILIBRIO_TRAVAMENTO


def faixa_por_volume(
    por_tick: dict[int, tuple[int, int, int, bool]],
    poc: int | None,
    fracao: float = FRACAO_VOLUME_NA_ESCALA,
) -> tuple[int, int, int, int] | None:
    """Faixa de preco que a escada vai cobrir, medida em VOLUME e nao em
    extremos. Devolve `(tick_min, tick_max, niveis_fora, volume_fora)`.

    DEFEITO CORRIGIDO em 28/08/2026 (achado do critico no pregao inteiro, com
    os 158.440 negocios reais): a escala vinha de `min`/`max` dos niveis, entao
    UM print isolado longe do mercado — contrato rolado, negocio direto, ou o
    estado de livro sintetico da fixture — arrastava o eixo de 5.182,0 ate
    2.605,5. Com 36 linhas, isso virava um passo de 147 ticks por linha: as 69
    faixas de preco onde o dia inteiro foi negociado caiam TODAS dentro de uma
    unica linha, e a coluna aparecia vazia, justo no modo SESSAO — o unico que
    representa o "volume diario" pedido pelo operador. 5M/15M escapavam so
    porque a janela curta nao alcancava o print aberrante.

    O algoritmo e a MESMA expansao gulosa da value area
    (`VolumeProfile.value_area`): parte do POC e cresce sempre para o vizinho
    de maior volume, ate cobrir `fracao` do volume. Niveis de volume
    desprezivel nas pontas sao os ultimos a entrar, entao ficam de fora — e o
    que sobra e contado e ANUNCIADO na tela (`_desenhar_rodape`), nunca
    silenciosamente descartado: a regra da fonte proibe esconder nivel sem
    dizer, e aqui o proprio numero de niveis fora da escala vira leitura.

    AUSENTE NA FONTE — `FRACAO_VOLUME_NA_ESCALA` e decisao de engenharia
    deste projeto, nao numero do autor.
    """

    if not por_tick:
        return None
    precos = sorted(por_tick)
    volume_total = sum(dados[0] for dados in por_tick.values())
    if volume_total <= 0:
        return precos[0], precos[-1], 0, 0

    ancora = poc if poc in por_tick else max(por_tick, key=lambda p: por_tick[p][0])
    indice = precos.index(ancora)
    baixo = alto = indice
    acumulado = por_tick[ancora][0]
    alvo = fracao * volume_total

    while acumulado < alvo and (baixo > 0 or alto < len(precos) - 1):
        vol_baixo = por_tick[precos[baixo - 1]][0] if baixo > 0 else -1
        vol_alto = por_tick[precos[alto + 1]][0] if alto < len(precos) - 1 else -1
        if vol_alto >= vol_baixo:
            alto += 1
            acumulado += por_tick[precos[alto]][0]
        else:
            baixo -= 1
            acumulado += por_tick[precos[baixo]][0]

    # A expansao por volume sozinha corta a cauda fina do proprio mercado (o
    # nivel de 500 lotes na ponta do dia). Depois dela, a faixa cresce de novo
    # enquanto o vizinho estiver COLADO (`SALTO_MAX_TICKS`): cauda legitima e
    # contigua, print aberrante fica a milhares de ticks. So o que estiver
    # separado por um vao grande fica fora da escala.
    while baixo > 0 and precos[baixo] - precos[baixo - 1] <= SALTO_MAX_TICKS:
        baixo -= 1
    while alto < len(precos) - 1 and precos[alto + 1] - precos[alto] <= SALTO_MAX_TICKS:
        alto += 1

    volume_dentro = sum(por_tick[preco][0] for preco in precos[baixo : alto + 1])
    niveis_fora = len(precos) - (alto - baixo + 1)
    return precos[baixo], precos[alto], niveis_fora, volume_total - volume_dentro


def fronteiras_va(
    linhas_perfil: tuple[tuple[int, int, int, int, int, bool], ...],
    val: int | None,
    vah: int | None,
    topo_corpo: int,
    altura: int,
    passo: int,
) -> tuple[tuple[str, int, bool], ...]:
    """`(nome, y, apoia_no_topo)` de cada fronteira da value area visivel.

    Funcao PURA e unica fonte da coordenada: a linha e o rotulo do VAH/VAL
    sao pintados em momentos diferentes do quadro (a linha antes das barras,
    o rotulo depois de tudo) e precisam concordar no pixel. Dentro de uma
    linha agrupada a fronteira e interpolada no tick, nunca arredondada para
    a borda do balde.
    """

    saida: list[tuple[str, int, bool]] = []
    for limite, nome, no_topo in ((vah, "VAH", True), (val, "VAL", False)):
        if limite is None:
            continue
        indice = next(
            (i for i, linha in enumerate(linhas_perfil) if linha[1] <= limite <= linha[0]), None
        )
        if indice is None:
            continue
        dentro = linhas_perfil[indice][0] - limite + (0 if no_topo else 1)
        saida.append((nome, topo_corpo + indice * altura + round(altura * dentro / max(1, passo)), no_topo))
    return tuple(saida)


def retangulo_tag_va(rect: QRect, y_limite: int, no_topo: bool) -> QRect:
    """Faixa reservada ao rotulo `VAH`/`VAL`, encostada na borda direita.

    DEFEITO CORRIGIDO em 28/08/2026: o rotulo da fronteira da value area e o
    numero de volume da linha eram os dois alinhados a direita, na mesma
    coordenada, e se destruiam quando a fronteira calhava numa linha com
    numero (visivel em `critico_p3_r4_s5.png`, linha 5.164,5 do 5M). Nao
    acontecia sempre — no 15M as bordas cairam em linhas vazias — o que faz
    disso uma colisao CONDICIONAL, do mesmo tipo do defeito de altura ja
    corrigido nesta regiao. Agora cada um tem faixa horizontal propria:
    `LARGURA_LANE_VA` a direita e do marcador de VA, e o numero termina antes
    dela (`retangulo_numero_volume`). Vale para VAH e VAL, que so diferem no
    lado vertical em que o rotulo se apoia.
    """

    largura = min(LARGURA_LANE_VA, max(1, rect.width() // 3))
    x = rect.right() - largura + 1
    y = y_limite - ALTURA_TAG_VA if no_topo else y_limite + 1
    return QRect(x, y, largura, ALTURA_TAG_VA)


def retangulo_numero_volume(x_barra: int, largura_barra: int, y: int, altura: int) -> QRect:
    """Faixa do numero de volume da linha — termina antes da lane do VA.

    Reserva CONSTANTE: a lane do VA e descontada em toda linha, com ou sem
    fronteira de value area ali. Descontar so na linha da fronteira faria o
    numero pular de posicao de um quadro para o outro conforme o VAL/VAH
    andasse, que e pior de ler do que perder alguns pixels sempre.
    """

    largura = max(1, largura_barra - 6 - LARGURA_LANE_VA)
    return QRect(x_barra + 3, y, largura, altura)


def rotulo_faixa(grid: object, tick_base: int, tick_topo: int) -> str:
    """Rotulo de preco de uma linha da escada — um preco so quando a linha e
    de um tick, a FAIXA quando ela agrega mais de um.

    DEFEITO CORRIGIDO em 28/08/2026, terceira aparicao da mesma familia nesta
    regiao: com `AGRUPADO 2 TICKS` a linha somava dois precos mas era rotulada
    so pelo de cima, entao a linha do POC dizia `5.166,5 · 134,0k` quando o
    tape tem 68.678 em 5.166,5 e 65.368 em 5.166,0 — o numero que o operador
    usaria para achar "onde esta o lote" vinha inflado por um fator 2. O aviso
    de agrupamento no cabecalho nao conserta isso: **declarar no cabecalho nao
    corrige o que o elemento individual afirma**. Nenhum rotulo de preco unico
    pode carregar volume de mais de um nivel.

    A parte estavel do preco (`formato.formatar_preco`) e escrita uma vez so —
    `5.166,0—6,5` em vez de `5.166,0—5.166,5` — porque a faixa da coluna nao
    comporta dois precos inteiros e repetir `5.16` nao acrescenta leitura.
    """

    if tick_base >= tick_topo:
        preco = formato.formatar_preco(grid, tick_topo)
        return f"{preco[0]}{preco[1]}"
    base = formato.formatar_preco(grid, tick_base)
    topo = formato.formatar_preco(grid, tick_topo)
    if base[0] == topo[0]:
        return f"{base[0]}{base[1]}—{topo[1]}"
    return f"{formato.preco_completo(grid, tick_base)}—{formato.preco_completo(grid, tick_topo)}"


def niveis_fora_da_escala(
    por_tick: dict[int, tuple[int, int, int, bool]], tick_min: int, tick_max: int
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """Os niveis que ficaram fora da escala, `(abaixo, acima)`, cada um como
    `(preco_em_ticks, volume)` ordenado do mais proximo da faixa para o mais
    distante.

    Existe por causa da critica de 28/08/2026: contar "2 niveis fora da
    escala" NAO cumpre a regra da fonte de nunca esconder nivel — sem o PRECO
    o nivel fica inlocalizavel, e "anunciar quantos" nao e "nao esconder".
    Com esta lista, `desenhar` reserva uma linha condensada em cada ponta,
    com preco e volume, apagada como manda a fonte para o que nao esta entre
    os destaques. O nivel continua na tela, localizavel, sem que um print a
    milhares de ticks dite a escala de todo o resto.
    """

    abaixo = tuple(
        (preco, por_tick[preco][0]) for preco in sorted((p for p in por_tick if p < tick_min), reverse=True)
    )
    acima = tuple((preco, por_tick[preco][0]) for preco in sorted(p for p in por_tick if p > tick_max))
    return abaixo, acima


def montar_linhas(
    por_tick: dict[int, tuple[int, int, int, bool]],
    tick_min: int,
    tick_max: int,
    ultimo: int | None,
    n_linhas: int,
) -> tuple[tuple[tuple[int, int, int, int, int, bool], ...], int]:
    """Traduz os niveis do perfil nas linhas que cabem na regiao.

    Devolve `(linhas, passo)`, onde cada linha e
    `(tick_topo, tick_base, volume_total, comprador, vendedor, destacado)` e
    `passo` e quantos ticks cada linha agrega.

    DEFEITO CORRIGIDO em 27/08/2026: a versao anterior desenhava uma janela
    fixa de `n_linhas` ticks centrada no ultimo negocio, e simplesmente NAO
    desenhava nivel nenhum fora dela — num perfil de sessao inteira (centenas
    de ticks) o proprio POC ficava invisivel, embora fosse a leitura principal
    da regiao. Agora, quando o perfil e mais alto que a regiao, os ticks sao
    AGRUPADOS (`passo` ticks por linha, somando volume) em vez de recortados:
    todo volume do perfil continua na tela, que e o que "mostrar o volume
    diario" exige. Agrupar e a mesma coisa que a plataforma de referencia faz
    ao mudar a escala do eixo de preco; recortar nao tem equivalente.
    """

    faixa = max(1, tick_max - tick_min + 1)
    passo = max(1, -(-faixa // max(1, n_linhas)))

    if passo == 1:
        # Cabe tick a tick: sobra vira folga acima/abaixo, com o ultimo
        # negocio garantidamente dentro.
        sobra = max(0, n_linhas - faixa)
        topo = tick_max + sobra // 2
        if ultimo is not None:
            topo = max(topo, ultimo)
            topo = min(topo, ultimo + n_linhas - 1)
    else:
        topo = tick_max

    linhas: list[tuple[int, int, int, int, int, bool]] = []
    for indice in range(n_linhas):
        tick_topo = topo - indice * passo
        tick_base = tick_topo - passo + 1
        volume = comprador = vendedor = 0
        destacado = False
        for tick in range(tick_base, tick_topo + 1):
            dados = por_tick.get(tick)
            if dados is None:
                continue
            volume += dados[0]
            comprador += dados[1]
            vendedor += dados[2]
            destacado = destacado or dados[3]
        linhas.append((tick_topo, tick_base, volume, comprador, vendedor, destacado))
    return tuple(linhas), passo


def _barra_3d(
    painter: QPainter, caixa: QRect, cor: QColor, intensidade: int
) -> None:
    """Um segmento de barra com leitura de volume extrudado.

    Nao e cor nova: e a MESMA cor de agressao, em degrade vertical (topo
    claro, base escura) mais um filete de luz na aresta superior — a mesma
    linguagem de "vidro com profundidade" ja usada no visor central
    (nucleo.py) e no disco do OPERADOR IA (vies.py).
    """

    if caixa.width() <= 0 or caixa.height() <= 0:
        return
    topo = QColor(cor)
    topo.setAlpha(intensidade)
    base = QColor(cor)
    base.setAlpha(max(18, intensidade // 3))
    gradiente = QLinearGradient(0, caixa.top(), 0, caixa.bottom())
    gradiente.setColorAt(0.0, topo.lighter(125))
    gradiente.setColorAt(0.55, topo)
    gradiente.setColorAt(1.0, base)
    painter.fillRect(caixa, gradiente)
    if caixa.height() >= 5:
        luz = QColor(cor)
        luz.setAlpha(min(255, intensidade + 60))
        painter.setPen(QPen(luz, 1))
        painter.drawLine(caixa.left(), caixa.top(), caixa.right(), caixa.top())


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < LARGURA_MIN or rect.height() < ALTURA_LINHA_MIN * 2:
        return

    niveis = estado.vap_niveis
    ultimo = estado.serie[-1][1] if estado.serie else None
    com_cromo = bool(retangulos_timeframe(rect))

    if not niveis:
        if com_cromo:
            _desenhar_cabecalho(painter, rect, estado, 1)
        _desenhar_indisponivel(painter, rect, ultimo, estado, com_cromo)
        return

    por_tick: dict[int, tuple[int, int, int, bool]] = {
        preco: (volume_total, volume_comprador, volume_vendedor, destacado)
        for preco, volume_total, volume_comprador, volume_vendedor, destacado in niveis
    }
    escala = faixa_por_volume(por_tick, estado.vap_poc)
    if escala is None:
        _desenhar_indisponivel(painter, rect, ultimo, estado, com_cromo)
        return
    tick_min, tick_max, niveis_fora, volume_fora = escala

    # Value area e ultimo negocio pertencem a escala por definicao de leitura:
    # se um deles caiu fora do recorte por volume, a escala estica ate ele.
    for obrigatorio in (estado.vap_val, estado.vap_vah, ultimo):
        if obrigatorio is None:
            continue
        tick_min = min(tick_min, obrigatorio)
        tick_max = max(tick_max, obrigatorio)

    reservar_rotulo = rect.height() >= ALTURA_MIN_PARA_ROTULO
    topo_corpo = rect.top() + (ALTURA_CABECALHO if com_cromo else 0)
    # O limite inferior do corpo e o TOPO do rodape, lido da mesma funcao que
    # desenha o rodape — antes era `bottom - ALTURA_ROTULO + 1`, que devolvia
    # um pixel a mais e deixava a ultima linha do corpo por baixo da primeira
    # linha do rodape.
    fim_util = retangulo_rotulo(rect).top() if reservar_rotulo else rect.bottom() + 1
    altura_util = fim_util - topo_corpo
    if altura_util < ALTURA_LINHA_MIN:
        return
    n_linhas = max(1, altura_util // ALTURA_LINHA_ALVO)
    altura = max(ALTURA_LINHA_MIN, min(ALTURA_LINHA_MAX, altura_util // n_linhas))
    # Uma linha em cada ponta e reservada para os niveis fora da escala, com
    # PRECO e volume (ver `niveis_fora_da_escala`). Sao os unicos casos em que
    # a escada mostra um preco que nao esta na sequencia — por isso vem com
    # seta, apagada, e nunca com barra proporcional (o comprimento seria
    # mentira: eles nao dividem a mesma escala).
    fora_abaixo, fora_acima = niveis_fora_da_escala(por_tick, tick_min, tick_max)
    mostrar_acima = bool(fora_acima) and n_linhas > 4
    mostrar_abaixo = bool(fora_abaixo) and n_linhas > 4
    pontas = int(mostrar_acima) + int(mostrar_abaixo)

    # As pontas entram no MESMO orcamento vertical do corpo. Contar so as
    # linhas do corpo (e ainda por cima com `altura` arredondada para cima de
    # `ALTURA_LINHA_ALVO`) empurrava a linha de "fora da escala" para baixo do
    # rodape: ela era desenhada, ficava invisivel, e o nivel voltava a estar
    # escondido — o defeito que essa linha existe para impedir.
    while n_linhas > 1 and (n_linhas + pontas) * altura > altura_util:
        n_linhas -= 1

    y_fora_acima = topo_corpo
    if mostrar_acima:
        topo_corpo += altura

    linhas_perfil, passo = montar_linhas(por_tick, tick_min, tick_max, ultimo, n_linhas)
    maior_volume = max((linha[2] for linha in linhas_perfil), default=0) or 1

    # Linha agrupada mostra FAIXA (`5.166,0—6,5`), que e mais larga que um
    # preco: a coluna de preco cresce e a fonte cede um ponto, em vez de o
    # rotulo ser truncado — rotulo cortado seria a mesma mentira de novo.
    fracao_lane = FRACAO_LANE_PRECO_AGRUPADO if passo > 1 else FRACAO_LANE_PRECO
    largura_preco = max(LARGURA_MIN_LANE_PRECO, int(rect.width() * fracao_lane))
    largura_preco = min(largura_preco, max(1, rect.width() - 20))
    x_barra = rect.left() + largura_preco
    largura_barra = rect.width() - largura_preco - 2

    val, vah = estado.vap_val, estado.vap_vah
    corpo_preco = 9 if com_cromo else 6
    if passo > 1:
        corpo_preco = max(6, corpo_preco - 1)
    fonte_preco = tokens.fonte_numero(corpo_preco, QFont.Weight.DemiBold)
    fonte_qtd = tokens.fonte_numero(7 if com_cromo else 6, QFont.Weight.Normal)
    fonte_tag = tokens.fonte_rotulo(6)

    fronteiras = fronteiras_va(linhas_perfil, val, vah, topo_corpo, altura, passo)
    # A linha da fronteira vem ANTES das barras e dos numeros: assim o numero
    # de volume fica por cima dela em vez de ser cortado por ela. Do lado do
    # preco so um traco curto no trilho, que marca a altura sem cobrir texto.
    for _, y_limite, _ in fronteiras:
        painter.setPen(QPen(tema_asg.NEXO_CIANO, 1, Qt.PenStyle.DotLine))
        painter.drawLine(x_barra, y_limite, rect.right(), y_limite)
        painter.setPen(QPen(tema_asg.NEXO_CIANO, 1))
        painter.drawLine(rect.left(), y_limite, rect.left() + 3, y_limite)

    y_destaque: int | None = None
    for indice, dados_linha in enumerate(linhas_perfil):
        tick, tick_base, volume_total, volume_comprador, volume_vendedor, destacado = dados_linha
        y = topo_corpo + indice * altura
        linha = QRect(rect.left(), y, rect.width(), altura)

        # Value area: faixa continua sombreada por tras da linha inteira. A
        # fonte trata VA como REGIAO, nao como duas linhas soltas.
        dentro_va = val is not None and vah is not None and val <= tick and vah >= tick_base
        if dentro_va:
            faixa = QColor(tema_asg.NEXO_CIANO)
            faixa.setAlpha(14)
            painter.fillRect(linha, faixa)

        e_poc = estado.vap_poc is not None and tick_base <= estado.vap_poc <= tick
        if e_poc:
            realce = QColor(tema_asg.NEXO_AMARELO)
            realce.setAlpha(26)
            painter.fillRect(linha, realce)

        travado = _e_travamento(volume_total, volume_comprador, volume_vendedor, maior_volume)

        if volume_total > 0 and largura_barra > 4:
            comprimento = max(2, int(largura_barra * volume_total / maior_volume))
            # Barra dividida por AGRESSAO (CONFIRMADO na fonte Nelogica).
            atribuido = volume_comprador + volume_vendedor
            if atribuido > 0:
                largura_compra = int(comprimento * volume_comprador / atribuido)
            else:
                largura_compra = comprimento // 2
            intensidade = 195 if destacado else 95
            altura_barra = max(3, altura - 3)
            y_barra = y + (altura - altura_barra) // 2
            _barra_3d(
                painter,
                QRect(x_barra, y_barra, largura_compra, altura_barra),
                tema_asg.NEXO_VERDE,
                intensidade,
            )
            _barra_3d(
                painter,
                QRect(x_barra + largura_compra, y_barra, comprimento - largura_compra, altura_barra),
                tema_asg.NEXO_ROSA,
                intensidade,
            )
            if destacado:
                painter.setPen(QPen(tema_asg.NEXO_TEXTO, 1))
                painter.setFont(fonte_qtd)
                painter.drawText(
                    retangulo_numero_volume(x_barra, largura_barra, y, altura),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    formato.abreviar(volume_total, com_sinal=False),
                )

        if ultimo is not None and tick_base <= ultimo <= tick:
            y_destaque = y
            continue

        # Lane de preco. Destacado = texto forte; o resto fica apagado
        # (NUNCA escondido) — regra literal da fonte.
        if e_poc:
            cor_preco = tema_asg.NEXO_AMARELO
        elif destacado:
            cor_preco = tema_asg.NEXO_TEXTO
        else:
            cor_preco = tema_asg.NEXO_MUTED
        painter.setPen(cor_preco)
        painter.setFont(fonte_preco)
        painter.drawText(
            QRect(rect.left() + 2, y, largura_preco - 6, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            rotulo_faixa(estado.grid, tick_base, tick),
        )

        if e_poc:
            painter.fillRect(QRect(rect.left(), y, 2, altura), tema_asg.NEXO_AMARELO)
            _etiqueta(painter, x_barra + 2, y, altura, "POC", tema_asg.NEXO_AMARELO, fonte_tag)
        elif travado:
            painter.fillRect(QRect(rect.left(), y, 2, altura), tema_asg.NEXO_CIANO)
            _etiqueta(painter, x_barra + 2, y, altura, "TRV", tema_asg.NEXO_CIANO, fonte_tag)

    fim_corpo = topo_corpo + n_linhas * altura
    if mostrar_acima:
        _desenhar_linha_fora(painter, rect, estado, y_fora_acima, altura, fora_acima, True)
    if mostrar_abaixo:
        _desenhar_linha_fora(painter, rect, estado, fim_corpo, altura, fora_abaixo, False)
    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(x_barra, topo_corpo, x_barra, fim_corpo)

    # Rotulos das fronteiras da value area. A LINHA ja foi pintada antes das
    # barras (para o numero de volume ficar por cima dela); o ROTULO vem
    # agora, por ultimo, na lane reservada da direita — assim nenhuma barra
    # longa o encobre e ele nunca divide coordenada com o numero.
    painter.setFont(fonte_tag)
    painter.setPen(tema_asg.NEXO_CIANO)
    for nome, y_limite, no_topo in fronteiras:
        painter.drawText(
            retangulo_tag_va(rect, y_limite, no_topo),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            nome,
        )

    if y_destaque is not None and ultimo is not None:
        caixa = QRect(rect.left(), y_destaque, rect.width(), altura)
        painter.fillRect(caixa, tema_asg.NEXO_AMARELO)
        painter.setPen(tema_asg.CHIP_TEXTO)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
        painter.drawText(
            caixa, Qt.AlignmentFlag.AlignCenter, formato.preco_completo(estado.grid, ultimo)
        )

    if com_cromo:
        _desenhar_cabecalho(painter, rect, estado, passo)

    if reservar_rotulo:
        # Quando as DUAS pontas ja estao desenhadas com preco e volume, o
        # rodape nao precisa repetir o total — volta a ser legenda de cor.
        exibidos = (not fora_acima or mostrar_acima) and (not fora_abaixo or mostrar_abaixo)
        _desenhar_rodape(
            painter,
            rect,
            estado,
            com_cromo,
            0 if exibidos else niveis_fora,
            0 if exibidos else volume_fora,
        )


def _desenhar_linha_fora(
    painter: QPainter,
    rect: QRect,
    estado: EstadoNexo,
    y: int,
    altura: int,
    niveis: tuple[tuple[int, int], ...],
    acima: bool,
) -> None:
    """Linha condensada de ponta com os niveis fora da escala.

    Mostra o PRECO do nivel mais proximo da faixa (com `+N` quando ha mais de
    um) e o volume somado — localizavel, que era a falha apontada em
    28/08/2026. Apagada (`NEXO_MUTED`) porque nao esta entre os destaques, e
    sem barra: o comprimento seria mentira, ja que estes ticks nao dividem a
    escala vertical com o resto.
    """

    if not niveis:
        return
    volume = sum(nivel[1] for nivel in niveis)
    # Mesma regra do corpo: o volume aqui e a SOMA dos niveis fora, entao o
    # rotulo tem de ser a FAIXA que ele cobre — `2.543,0—3,5` — e nunca um
    # preco unico com um `+1` colado, que atribuiria a um preco so o volume
    # de varios (defeito julgado em 28/08/2026).
    precos = [nivel[0] for nivel in niveis]
    rotulo = rotulo_faixa(estado.grid, min(precos), max(precos))
    seta = "▲" if acima else "▼"
    caixa = QRect(rect.left(), y, rect.width(), altura)
    fundo = QColor(tema_asg.NEXO_PAINEL_ALTO)
    painter.fillRect(caixa, fundo)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        caixa.adjusted(2, 0, -2, 0),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        f"{seta} {rotulo}",
    )
    painter.drawText(
        caixa.adjusted(2, 0, -2, 0),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        formato.abreviar(volume, com_sinal=False),
    )


def _etiqueta(
    painter: QPainter, x: int, y: int, altura: int, texto: str, cor: QColor, fonte: QFont
) -> None:
    """Etiqueta de 3 letras colada ao inicio da barra (POC/TRV)."""

    caixa = QRect(x, y + 1, 20, max(1, altura - 2))
    # Plate escuro por tras: a etiqueta cai EM CIMA da barra de agressao, e
    # sem ele "POC"/"TRV" some no verde/rosa.
    plate = QColor(tema_asg.NEXO_FUNDO)
    plate.setAlpha(210)
    painter.fillRect(caixa, plate)
    painter.setFont(fonte)
    painter.setPen(cor)
    painter.drawText(
        caixa, Qt.AlignmentFlag.AlignCenter, texto
    )


def _desenhar_cabecalho(
    painter: QPainter, rect: QRect, estado: EstadoNexo, passo: int
) -> None:
    """Titulo + seletor de timeframe + resumo (volume, POC, value area).

    O filtro 5M/15M ja existia mas so pelo clique no rodape, sem se anunciar
    (achado do operador). Aqui ele e um seletor de tres segmentos, com o
    ativo aceso.
    """

    # Fundo opaco: o cabecalho e pintado DEPOIS do corpo (precisa saber o
    # agrupamento), entao ele tem de cobrir o proprio espaco.
    painter.fillRect(
        QRect(rect.left(), rect.top(), rect.width(), ALTURA_CABECALHO - 1), tema_asg.NEXO_PAINEL
    )
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        QRect(rect.left() + 3, rect.top(), rect.width() - 6, ALTURA_TITULO),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "VAP · VOLUME AT PRICE" if passo <= 1 else f"VAP · AGRUPADO {passo} TICKS",
    )

    for minutos, caixa in retangulos_timeframe(rect).items():
        rotulo = dict(TIMEFRAMES)[minutos]
        ativo = estado.vap_timeframe_min == minutos
        if ativo:
            fundo = QColor(tema_asg.NEXO_CIANO)
            fundo.setAlpha(46)
            painter.fillRect(caixa, fundo)
            painter.setPen(QPen(tema_asg.NEXO_CIANO, 1))
            painter.drawRect(caixa.adjusted(0, 0, -1, -1))
            painter.setPen(tema_asg.NEXO_CIANO)
        else:
            painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
            painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, rotulo)

    y_resumo = rect.top() + ALTURA_TITULO + ALTURA_SELETOR
    janela = "SESSAO" if estado.vap_timeframe_min <= 0 else f"{estado.vap_timeframe_min}M"
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        QRect(rect.left() + 3, y_resumo, rect.width() - 6, 12),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        f"VOL {janela}",
    )
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(
        QRect(rect.left() + 3, y_resumo, rect.width() - 6, 12),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        formato.abreviar(estado.vap_volume_total, com_sinal=False),
    )

    if estado.vap_val is not None and estado.vap_vah is not None:
        val = formato.formatar_preco(estado.grid, estado.vap_val)
        vah = formato.formatar_preco(estado.grid, estado.vap_vah)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(
            QRect(rect.left() + 3, y_resumo + 12, rect.width() - 6, 12),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"VA {val[0]}{val[1]}—{vah[0]}{vah[1]}",
        )

    if estado.vap_poc is not None:
        poc = formato.formatar_preco(estado.grid, estado.vap_poc)
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_AMARELO)
        painter.drawText(
            QRect(rect.left() + 3, y_resumo + 12, rect.width() - 6, 12),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"POC {poc[0]}{poc[1]}",
        )

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(
        rect.left(), rect.top() + ALTURA_CABECALHO - 1, rect.right(), rect.top() + ALTURA_CABECALHO - 1
    )


def _desenhar_rodape(
    painter: QPainter,
    rect: QRect,
    estado: EstadoNexo,
    com_cromo: bool,
    niveis_fora: int = 0,
    volume_fora: int = 0,
) -> None:
    painter.setFont(tokens.fonte_rotulo(6))
    sufixo_tf = "SESSAO" if estado.vap_timeframe_min <= 0 else f"{estado.vap_timeframe_min}M"
    if niveis_fora > 0 and volume_fora > 0:
        # O nivel fora da escala agora aparece com PRECO na linha de ponta
        # (`_desenhar_linha_fora`); aqui fica so o total, para o operador saber
        # de quanto volume se trata sem ter de somar as duas pontas. Contagem
        # sozinha nao cumpre "nao esconder" — foi a critica de 28/08/2026.
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(
            retangulo_rotulo(rect),
            Qt.AlignmentFlag.AlignCenter,
            f"⇄ FORA DA ESCALA ▲▼ {formato.abreviar(volume_fora, com_sinal=False)}",
        )
        return
    if com_cromo:
        # O cabecalho ja diz o timeframe e o POC; aqui fica so a legenda das
        # cores e o convite ao ciclo, sem repetir numero.
        painter.setPen(tema_asg.NEXO_MUTED)
        texto = "⇄ COMPRA/VENDA · TRV=ABSORCAO"
    elif estado.vap_poc is not None:
        preco_poc = formato.formatar_preco(estado.grid, estado.vap_poc)
        painter.setPen(tema_asg.NEXO_AMARELO)
        texto = f"⇄ VAP {sufixo_tf} · POC {preco_poc[0]}{preco_poc[1]}"
    else:
        painter.setPen(tema_asg.NEXO_MUTED)
        texto = f"⇄ VAP {sufixo_tf}"
    painter.drawText(retangulo_rotulo(rect), Qt.AlignmentFlag.AlignCenter, texto)


def _desenhar_indisponivel(
    painter: QPainter, rect: QRect, ultimo: int | None, estado: EstadoNexo, com_cromo: bool
) -> None:
    """Estado honesto quando o VAP ainda nao tem negocio nenhum registrado.

    Nunca desenha barra aqui: sem volume nao ha o que medir, e uma barra de
    comprimento chutado seria volume sintetico.
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
            "SEM\nVAP",
        )
    else:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM\nVAP")
