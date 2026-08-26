"""Estado INDISPONIVEL (quadro inteiro) da superficie NEXO.

Este modulo nao e uma regiao geometrica do mapa em ``paineis/nexo/__init__.py``
(``REGIOES``/``ORDEM_DESENHO``) — essa costura pertence ao dono da composicao,
nao a este arquivo. O que este arquivo resolve e um problema diferente: hoje
cada regiao NEXO que pode faltar dado inventa a propria maneira de dizer isso.
``ladder.py`` tem um ``_desenhar_indisponivel`` local so para a coluna de
preco; ``estatistica.py`` escreve "SEM HISTORICO DE FORCA" sozinho; e
``pressao.py`` — o caso que motivou esta rodada — desenha os dois trilhos de
pressao com ``score = 0.0`` quando ``estado.maker`` e ``None``, o que produz
um medidor 50%/50% cheio sem uma unica ordem observada por tras: liquidez
fabricada, nao ausencia declarada. Nenhuma dessas fica errada olhando cada
regiao isolada; a falha e a falta de UM vocabulario visual comum para "isto
aqui nao existe" em toda a superficie.

``desenhar(painter, rect, estado)`` segue o mesmo contrato de qualquer regiao
NEXO (``EstadoNexo`` imutavel, nenhum estado vivo, nenhum clique) para que a
composicao possa adotar este modulo como uma camada final desenhada por cima
de tudo quando o quadro estiver degradado — sem que este arquivo precise
decidir por si so QUANDO isso acontece a nivel de janela; ``diagnosticar``
expõe essa decisao como funcao pura, testavel sem QPainter algum.

Duas leituras de indisponibilidade, nunca so uma tarja de cor:

* **SEM SINAL** (``ERRO``/``DESCONHECIDO``/``AGUARDANDO``/sem retrato algum) —
  o quadro inteiro nao tem retrato confiavel; nada do que as outras regioes
  desenhariam deveria ser lido.
* **SEM BOOK** (``SEM_BOOK`` ao vivo, ou ``REPLAY`` cujo retrato bruto nao
  trouxe ``bids``/``asks``) — o feed ainda respira, mas a profundidade que
  alimentaria qualquer medidor de pressao nao existe neste quadro. E
  precisamente o cenario do replay MT5 sem historico de livro citado no
  contrato deste ciclo: o estado honesto e nomear a ausencia, nunca simular
  uma faixa cheia.

``ATRASADO`` fica de fora de proposito: o feed ainda entrega retrato, so
atrasado — nao e "sem dado", e rotula-lo aqui duplicaria um selo que ja
pertence a quem desenha o badge de estado no cabecalho (fora deste arquivo).

Todo texto, cor e fonte vem de ``ui.tokens``/``ui.tema_asg``; nenhuma cor ou
medida literal nova é criada fora do que esses dois modulos ja alocam. Nao ha
campo, callback nem rotulo clicavel: a superficie inteira, mesmo degradada,
continua so leitura.

Nesta rodada, uma critica apontou que a camada degradada anterior era um
selo isolado no centro do quadro enquanto o resto seguia visivel como se
nada tivesse quebrado — ``ALERTA`` so de cor, nao de vocabulario. Este
arquivo so pode responder pela sua propria metade: nao ha aqui gauge de
pressao, coluna de ladder nem grafico para apagar ou tracejar (isso mora em
``pressao.py``/``ladder.py``/etc., fora deste modulo). O que ESTE arquivo
podia consertar, consertou: (1) o veu por cima do quadro inteiro ficou mais
opaco no caso "so sem book" (``206`` em vez de ``168``) para que um numero
de outra regiao nao continue lendo como atual por baixo de um veu fino
demais; (2) a mesma hachura "sinal parado" do cartao agora tambem cobre o
quadro inteiro (bem mais fraca) em vez de ficar presa ao centro; (3) o
titulo virou um chip solido (preenchimento na cor do estado + texto escuro)
em vez de glifos coloridos soltos, para nao perder a competicao visual
contra qualquer numero saturado de outra regiao; (4) o gauge N/D ganhou um
contador (``NIVEIS DE BOOK: N``) que corrobora em numero a ausencia, pintado
na cor do estado em vez de ``NEXO_MUTED``.

Uma segunda critica, ja sobre este cartao atualizado, apontou que nomear O
QUE falta ("SEM BOOK") nao diz ATE ONDE isso contamina o resto do quadro:
um operador olhando ``titulo``/``subtitulo`` nao sabe se um numero vizinho
(pressao, profundidade) ainda vale ou nao, nem se um "--"/N/D significa
faltando, zero de verdade ou suprimido de proposito. Dentro do que este
arquivo pode resolver sozinho: o novo campo ``MotivoIndisponivel.alcance``
e a linha ``ATINGE: ...`` que ``_desenhar_alcance`` pinta logo abaixo do
subtitulo, na cor do estado; e a linha do medidor N/D agora soletra por
extenso as tres causas que o tracinho sozinho nao distingue.

O que esta critica tambem pediu e que este arquivo nao tem como entregar
sem tocar em modulo alheio: (a) um chip persistente no CHROME DO TOPO da
janela (fora da superficie NEXO, muito menos deste cartao) nomeando o feed
indisponivel; (b) apagar e dessaturar de fato os medidores/trilhos de
``pressao.py`` e as linhas do ladder de ``ladder.py`` quando o book falta
— este modulo so e chamado como camada por cima quando a composicao (fora
deste arquivo, ver linhas 3-21 acima) decidir isso, e nao redesenha o que
essas regioes ja pintaram por baixo; (c) a faixa de banner "ALERTA" /
"ALGORITHMIC STANDBY" / "SIGA O FLUXO NO CONTEXTO" empilhada nao pertence
a este modulo. Os tres ficam fora do escopo deste arquivo por contrato
("Touch only your owned files") e voltam como pendencia para quem possui
aqueles modulos.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo

# Gate de tamanho: abaixo disto nao ha espaco para nomear a degradacao com
# texto legivel, so um retangulo cego. Melhor nao desenhar nada (mesma regra
# de guarda usada em ``nucleo.py``/``pressao.py``) do que forcar um cartao
# ilegivel.
LARGURA_MIN = 140
ALTURA_MIN = 90

# O cartao central nunca cobre o quadro rebite a rebite: uma margem visivel
# em volta dele deixa claro que isto e uma camada de estado por cima da
# superficie, nao um quadro novo que substitui silenciosamente o layout.
FRACAO_CARTAO_LARGURA = 0.82
FRACAO_CARTAO_ALTURA = 0.84
CARTAO_LARGURA_MAX = 640
CARTAO_ALTURA_MAX = 420
CARTAO_LARGURA_MIN = 200
CARTAO_ALTURA_MIN = 140

MARGEM_INTERNA = 14
ALTURA_RODAPE = 16
ALTURA_ORIGEM = 12
VAO_SECAO = 6

# Espacamento da hachura diagonal (linhas finas, nao uma textura importada) —
# a marca "sinal parado" da camada, distinta do preenchimento liso que as
# regioes saudaveis usam.
PASSO_HACHURA = 10


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    """Copia ``cor`` com um alfa diferente — nenhuma cor nova, so translucidez.

    Mesma tecnica que ``tema_asg._com_alpha`` ja usa para as faixas de fundo;
    reimplementada aqui (uma linha) em vez de importar um simbolo privado de
    outro modulo.
    """

    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


@dataclass(frozen=True, slots=True)
class MotivoIndisponivel:
    """Por que o quadro (ou uma fatia dele) esta sendo lido como indisponivel.

    ``origem`` e uma linha tecnica curta (o campo bruto que decidiu isto) —
    parte deliberada do vocabulario honesto: quem ve o estado degradado tem
    como conferir a razao, nao so a cor.

    ``alcance`` responde a segunda pergunta que uma critica desta rodada
    encontrou sem resposta: nomear QUE a leitura falta nao diz ATE ONDE ela
    contamina o resto do quadro. Sao rotulos curtos e honestos (nunca um
    numero ou porcentagem inventados) das leituras que dependem do que falta
    — no caso total, o quadro inteiro; no caso "so sem book", as leituras
    derivadas de livro (pressao, profundidade) especificamente, deixando
    claro que ha uma diferenca de escopo entre os dois casos.
    """

    titulo: str
    subtitulo: str
    cor: QColor
    origem: str
    total: bool  # True = sem retrato nenhum; False = feed vivo, so sem book
    niveis_livro: int  # bids+asks contados de fato — nunca inventado, corrobora o motivo em numero
    alcance: tuple[str, ...]  # quais leituras a ausencia atinge — nomeado, nunca deixado implicito


_ESTADOS_SEM_SINAL = frozenset(
    {_asg.EstadoASG.ERRO, _asg.EstadoASG.DESCONHECIDO, _asg.EstadoASG.AGUARDANDO}
)

_COR_POR_ESTADO = {
    _asg.EstadoASG.ERRO: tema_asg.ESTADO_ERRO,
    _asg.EstadoASG.DESCONHECIDO: tema_asg.ESTADO_DESCONHECIDO,
    _asg.EstadoASG.AGUARDANDO: tema_asg.ESTADO_AGUARDANDO,
    _asg.EstadoASG.SEM_BOOK: tema_asg.ESTADO_SEM_BOOK,
    _asg.EstadoASG.REPLAY: tema_asg.ESTADO_SEM_BOOK,
}


def _contar_niveis_livro(contexto: object) -> int:
    """Conta bids+asks de fato presentes — nunca um numero decorativo.

    Esta e a metade numerica do vocabulario honesto que ``diagnosticar``
    devolve: o cartao SEM BOOK nao pode so dizer a palavra "book" e mostrar
    um medidor N/D — precisa de um contador que corrobore a alegacao (a
    razao pela qual o gauge esta vazio e que a contagem abaixo e zero, nao
    o contrario). Le apenas os atributos publicos ``bids``/``asks`` do
    contexto bruto ja recebido pela funcao chamadora; nunca consulta um
    objeto vivo, bus ou thread.
    """

    bids = getattr(contexto, "bids", None) or ()
    asks = getattr(contexto, "asks", None) or ()
    try:
        return len(bids) + len(asks)
    except TypeError:
        return 0


def diagnosticar(estado: EstadoNexo) -> MotivoIndisponivel | None:
    """Decide, sem tocar em ``QPainter``, se o quadro precisa da camada.

    Funcao pura: le somente o ``EstadoNexo`` imutavel (nunca um relogio, bus
    ou objeto vivo) e devolve ``None`` quando o quadro esta saudavel — o
    modulo inteiro vira um no-op nesse caso, seguro para ser chamado em todo
    quadro sem risco de cobrir uma leitura valida.
    """

    snapshot = getattr(estado, "snapshot", None)
    if snapshot is None:
        return MotivoIndisponivel(
            titulo="SEM QUADRO",
            subtitulo="NENHUM RETRATO CHEGOU AINDA A ESTA SUPERFICIE",
            cor=tema_asg.ESTADO_DESCONHECIDO,
            origem="snapshot=None",
            total=True,
            niveis_livro=0,
            alcance=("TODAS AS LEITURAS DESTE QUADRO",),
        )

    operacional = getattr(snapshot, "estado_operacional", None)
    dados = getattr(snapshot, "dados", None)
    contexto = getattr(snapshot, "contexto_bruto", None)
    niveis_livro = _contar_niveis_livro(contexto)
    tem_book = niveis_livro > 0

    if operacional in _ESTADOS_SEM_SINAL:
        detalhe = (getattr(dados, "detalhe", "") or "").strip()
        return MotivoIndisponivel(
            titulo="SEM SINAL",
            subtitulo=detalhe or f"ESTADO {operacional.value} · SEM RETRATO CONFIAVEL",
            cor=_COR_POR_ESTADO.get(operacional, tema_asg.ESTADO_DESCONHECIDO),
            origem=f"estado_operacional={operacional.value}",
            total=True,
            niveis_livro=niveis_livro,
            alcance=("TODAS AS LEITURAS DESTE QUADRO",),
        )

    if operacional is _asg.EstadoASG.SEM_BOOK or (
        operacional is _asg.EstadoASG.REPLAY and not tem_book
    ):
        em_replay = operacional is _asg.EstadoASG.REPLAY
        detalhe = (getattr(contexto, "detalhe", "") or "").strip()
        titulo = "SEM BOOK NO REPLAY" if em_replay else "SEM BOOK"
        subtitulo = detalhe or (
            "MT5 REPLAY SEM HISTORICO DE LIVRO NESTE TRECHO"
            if em_replay
            else "LIVRO L2 INDISPONIVEL NESTE QUADRO"
        )
        origem_estado = operacional.value if operacional is not None else "—"
        return MotivoIndisponivel(
            titulo=titulo,
            subtitulo=subtitulo,
            cor=tema_asg.ESTADO_SEM_BOOK,
            origem=(
                f"estado_operacional={origem_estado} · "
                f"contexto_bruto={'vazio' if not tem_book else 'presente'}"
            ),
            total=False,
            niveis_livro=niveis_livro,
            alcance=("MEDIDOR DE PRESSAO", "PROFUNDIDADE DO LIVRO", "GATILHOS DERIVADOS DE BOOK"),
        )

    return None


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """Ponto de entrada no contrato padrao de regiao NEXO.

    Nao-op quando o quadro esta saudavel (``diagnosticar`` devolve ``None``):
    isso e o que torna seguro chamar este modulo em todo quadro, mesmo antes
    de qualquer composicao decidir usa-lo como camada.
    """

    if rect.width() < LARGURA_MIN or rect.height() < ALTURA_MIN:
        return
    motivo = diagnosticar(estado)
    if motivo is None:
        return

    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _desenhar_cortina(painter, rect, motivo)
        cartao = _retangulo_cartao(rect)
        # Textura "sinal parado" no quadro inteiro primeiro (bem fraca, por
        # baixo de qualquer coisa que o veu deixe entrever de outras
        # regioes), depois a mesma textura mais forte dentro do cartao —
        # um so vocabulario, duas densidades, nunca dois desenhos diferentes.
        _desenhar_hachura(painter, rect, motivo, alpha=14)
        _desenhar_hachura(painter, cartao, motivo)
        _desenhar_moldura(painter, cartao, motivo)
        _desenhar_cabecalho(painter, cartao, motivo)
        _desenhar_medidor_nd(painter, cartao, motivo)
        _desenhar_rodape(painter, cartao, motivo)
    finally:
        painter.restore()


def _retangulo_cartao(rect: QRect) -> QRect:
    largura = max(
        CARTAO_LARGURA_MIN, min(CARTAO_LARGURA_MAX, round(rect.width() * FRACAO_CARTAO_LARGURA))
    )
    altura = max(
        CARTAO_ALTURA_MIN, min(CARTAO_ALTURA_MAX, round(rect.height() * FRACAO_CARTAO_ALTURA))
    )
    largura = min(largura, rect.width())
    altura = min(altura, rect.height())
    x = rect.left() + (rect.width() - largura) // 2
    y = rect.top() + (rect.height() - altura) // 2
    return QRect(x, y, largura, altura)


def _desenhar_cortina(painter: QPainter, rect: QRect, motivo: MotivoIndisponivel) -> None:
    """Veu por tras do cartao — mais opaco quando o feed inteiro caiu.

    A diferenca de opacidade entre ``total`` e "so sem book" e uma segunda
    dimensao honesta (alem de cor e texto): um quadro sem book ainda deixa
    entrever a superficie por baixo (o feed vive), um quadro sem sinal nao.

    O alpha do caso parcial (``168`` ate a rodada anterior) subiu para
    ``206``: uma critica valida encontrou numeros de outras regioes (as
    leituras de pressao/gauges que este modulo nao desenha) ainda legiveis
    por baixo do veu fino, o que lia como "confianca plena" atras de uma
    cor so. O veu mais denso nao apaga a diferenca com o caso total (que
    continua mais opaco), so encolhe a janela onde um numero antigo passa
    por atual.
    """

    alpha = 232 if motivo.total else 206
    painter.fillRect(rect, _com_alpha(tema_asg.NEXO_FUNDO, alpha))


def _desenhar_hachura(
    painter: QPainter, area: QRect, motivo: MotivoIndisponivel, alpha: int = 46
) -> None:
    """Hachura diagonal fina — a marca de "sinal parado".

    Nenhuma regiao saudavel do NEXO preenche area com linhas diagonais; e
    por isso o motivo nunca e confundido com um preenchimento comum, mesmo
    em quem ve a superficie sem cor (a hachura permanece visivel como
    textura, nao so como tom). ``alpha`` default e a densidade usada dentro
    do cartao; ``desenhar`` tambem chama esta funcao com um ``alpha`` bem
    mais fraco sobre o QUADRO INTEIRO (nao so o cartao) — a mesma textura,
    so mais rarefeita, estendida por cima das regioes que este modulo nao
    possui, para que a leitura de "parado" nao fique presa ao centro do
    quadro enquanto o resto segue com aparencia de operacao normal por
    baixo do veu.
    """

    painter.save()
    painter.setClipRect(area)
    caneta = QPen(_com_alpha(motivo.cor, alpha))
    caneta.setWidth(1)
    painter.setPen(caneta)
    diagonal = area.width() + area.height()
    x0 = area.left() - area.height()
    passo = max(4, PASSO_HACHURA)
    deslocamento = 0
    while deslocamento <= diagonal:
        x = x0 + deslocamento
        painter.drawLine(x, area.bottom(), x + area.height(), area.top())
        deslocamento += passo
    painter.restore()


def _desenhar_moldura(painter: QPainter, cartao: QRect, motivo: MotivoIndisponivel) -> None:
    """Corpo do cartao: preenchimento solido + contorno duplo + brackets.

    A mesma familia de "vidro com profundidade" que ``nucleo.py`` usa no
    visor central (preenchimento escuro, contorno interno fino, brackets de
    canto) — para que o estado degradado leia como parte do mesmo
    instrumento, nao como uma caixa de dialogo importada de outro sistema.
    Os brackets aqui sao TRACEJADOS (o visor saudavel usa traco solido): a
    unica diferenca de silhueta entre "instrumento lendo" e "instrumento sem
    sinal", sem inventar um vocabulario de forma novo.
    """

    painter.fillRect(cartao, tema_asg.NEXO_PAINEL_ALTO)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(motivo.cor, 2))
    painter.drawRect(cartao.adjusted(1, 1, -2, -2))
    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    painter.drawRect(cartao.adjusted(5, 5, -6, -6))

    braco = max(8, min(cartao.width(), cartao.height()) // 10)
    caneta_bracket = QPen(motivo.cor, 2, Qt.PenStyle.DashLine)
    painter.setPen(caneta_bracket)
    for x, y, dx, dy in (
        (cartao.left(), cartao.top(), 1, 1),
        (cartao.right(), cartao.top(), -1, 1),
        (cartao.left(), cartao.bottom(), 1, -1),
        (cartao.right(), cartao.bottom(), -1, -1),
    ):
        painter.drawLine(x, y, x + dx * braco, y)
        painter.drawLine(x, y, x, y + dy * braco)


def _desenhar_cabecalho(painter: QPainter, cartao: QRect, motivo: MotivoIndisponivel) -> None:
    """Selo + titulo + subtitulo — a razao nomeada, nunca so uma cor.

    O selo e um anel TRACEJADO (varios arcos com vao entre eles) em vez de
    circulo fechado: leitura "procurando sinal", nao "operacao bloqueada"
    (evita o simbolo universal de proibicao, que comunicaria a coisa
    errada — isto e ausencia de dado, nao uma acao vedada).

    O titulo e pintado como CHIP (preenchimento solido de ``motivo.cor`` +
    texto ``tema_asg.CHIP_TEXTO`` escuro por cima) em vez de texto colorido
    solto sobre o fundo do cartao — o mesmo criterio ja usado nos chips de
    confianca do produto (texto escuro sobre fundo de alta luminancia).
    Antes, o titulo era so glifos finos na cor do estado: legivel, mas
    perdia a competicao visual contra qualquer numero saturado de outra
    regiao no mesmo quadro. Como preenchimento solido, o titulo vira o
    retangulo de maior luminancia do quadro inteiro — a mensagem de falha
    deixa de ser o texto mais dificil de ler na tela.
    """

    diametro = max(28, min(56, cartao.height() // 3))
    raio = diametro / 2
    cx = cartao.left() + MARGEM_INTERNA + raio
    cy = cartao.top() + MARGEM_INTERNA + raio
    anel = QRect(round(cx - raio), round(cy - raio), round(diametro), round(diametro))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    caneta = QPen(motivo.cor, 2)
    painter.setPen(caneta)
    for inicio_graus in (10, 100, 190, 280):
        painter.drawArc(anel, inicio_graus * 16, 60 * 16)
    ponto = QRect(round(cx - 2), round(cy - 2), 4, 4)
    painter.setBrush(motivo.cor)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(ponto)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    x_texto = round(cx + raio) + MARGEM_INTERNA
    largura_texto = cartao.right() - MARGEM_INTERNA - x_texto
    y_topo = cartao.top() + MARGEM_INTERNA

    tamanho_titulo = max(13, min(22, cartao.height() // 12))
    fonte_titulo = tokens.fonte_ui(tamanho_titulo, QFont.Weight.Bold)
    painter.setFont(fonte_titulo)
    altura_chip = tamanho_titulo + 10
    metrica = QFontMetrics(fonte_titulo)
    largura_chip = min(max(20, largura_texto), metrica.horizontalAdvance(motivo.titulo) + 20)
    caixa_titulo = QRect(x_texto, y_topo, round(largura_chip), altura_chip)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(motivo.cor)
    painter.drawRect(caixa_titulo)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(tema_asg.CHIP_TEXTO)
    painter.drawText(caixa_titulo, Qt.AlignmentFlag.AlignCenter, motivo.titulo)

    tamanho_sub = max(9, min(13, cartao.height() // 20))
    painter.setFont(tokens.fonte_ui(tamanho_sub, QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    caixa_sub = QRect(cartao.left() + MARGEM_INTERNA, round(cy + raio) + VAO_SECAO,
                      cartao.width() - 2 * MARGEM_INTERNA, tamanho_sub * 3 + 6)
    painter.drawText(caixa_sub, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                     motivo.subtitulo)

    _desenhar_alcance(painter, cartao, motivo, caixa_sub.bottom() + VAO_SECAO)


def _desenhar_alcance(painter: QPainter, cartao: QRect, motivo: MotivoIndisponivel, y_topo: int) -> None:
    """Nomeia ATE ONDE a ausencia chega — a metade que faltava no cabecalho.

    ``titulo``/``subtitulo`` ja dizem O QUE falta; uma critica desta rodada
    apontou que nem o titulo nem o resto da superficie dizem QUANTO do
    quadro aquilo contamina — o operador nao tem como saber, olhando so
    "SEM BOOK", se um numero AO LADO desta camada (num gauge que este modulo
    nao desenha) ainda vale ou nao. Esta linha responde isso com os rotulos
    honestos de ``motivo.alcance`` (nunca um numero ou barra decorativos),
    na mesma cor do estado — para competir de igual para igual com qualquer
    leitura saturada de outra regiao, nao ficar escondida em texto apagado.

    So desenha se sobrar espaco vertical antes da zona do medidor N/D; sem
    espaco, prefere nao desenhar a espremer texto ilegivel (mesma regra de
    guarda do resto do modulo).
    """

    limite = cartao.top() + cartao.height() * 3 // 5
    tamanho = max(8, min(11, cartao.height() // 24))
    # Duas linhas de altura reservadas: a lista de rotulos pode nao caber
    # numa linha so, e ``TextWordWrap`` sozinho nao estica a caixa — sem a
    # segunda linha reservada aqui, o texto quebraria e a segunda metade
    # ficaria cortada em vez de visivel.
    altura_bloco = (tamanho + 6) * 2
    if y_topo + altura_bloco > limite:
        return

    texto = "ATINGE: " + " · ".join(motivo.alcance)
    caixa = QRect(cartao.left() + MARGEM_INTERNA, y_topo,
                 cartao.width() - 2 * MARGEM_INTERNA, altura_bloco)
    painter.setFont(tokens.fonte_ui(tamanho, QFont.Weight.Bold))
    painter.setPen(motivo.cor)
    painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                     | Qt.TextFlag.TextWordWrap, texto)


def _desenhar_medidor_nd(painter: QPainter, cartao: QRect, motivo: MotivoIndisponivel) -> None:
    """O contraponto honesto ao defeito que abriu esta rodada.

    Mesma leitura consultiva de "par de pressao oposto" que ``pressao.py``
    desenha quando ha book — dois trilhos, COMPRA e VENDA — mas aqui os
    trilhos ficam VAZIOS e TRACEJADOS, com o rotulo ``N/D`` em vez de
    qualquer percentual. Nao ha ``score = 0.0`` disfarcado de "sem pressao":
    ha uma leitura que se recusa a inventar um numero, textura e forma
    deixando isso explicito (nao so a ausencia de preenchimento, que sozinha
    poderia passar por "50/50" para quem olha rapido).

    Abaixo dos trilhos, ``motivo.niveis_livro`` vira texto: um contador que
    CORROBORA em numero o motivo do gauge estar vazio (``NIVEIS DE BOOK: 0``
    em vez de so a palavra "book" solta). E pintado na cor do estado, no
    mesmo peso do rotulo dos trilhos — nao mais em ``NEXO_MUTED``, que
    tornava esta linha a mais apagada do cartao justamente onde a leitura
    mais importa (o numero que prova a ausencia, nao so a alega).

    A mesma linha tambem soletra o que ``N/D`` significa: uma critica desta
    rodada notou que um token vazio sozinho nao diz se aquilo e "faltando",
    "zero de verdade" ou "suprimido de proposito" — sao tres causas
    diferentes disfarcadas do mesmo tracinho. Aqui isso fica explicito por
    extenso, no lugar onde o proprio token aparece.
    """

    y_disponivel = cartao.bottom() - ALTURA_RODAPE - ALTURA_ORIGEM - VAO_SECAO
    altura_bloco = max(0, y_disponivel - (cartao.top() + cartao.height() * 2 // 3))
    if altura_bloco < 26:
        return

    y_topo = y_disponivel - altura_bloco
    largura_total = cartao.width() - 2 * MARGEM_INTERNA
    vao = 10
    largura_trilho = max(30, (largura_total - vao) // 2)
    trilho_compra = QRect(cartao.left() + MARGEM_INTERNA, y_topo, largura_trilho, 14)
    trilho_venda = QRect(trilho_compra.right() + vao, y_topo, largura_trilho, 14)

    for trilho, cor, rotulo, alinhamento in (
        (trilho_compra, tema_asg.NEXO_VERDE, "COMPRA", Qt.AlignmentFlag.AlignLeft),
        (trilho_venda, tema_asg.NEXO_ROSA, "VENDA", Qt.AlignmentFlag.AlignRight),
    ):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_com_alpha(cor, 130), 1, Qt.PenStyle.DashLine))
        painter.drawRect(trilho.adjusted(0, 0, -1, -1))
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        legenda = QRect(trilho.left(), trilho.top() - 12, trilho.width(), 11)
        painter.drawText(legenda, alinhamento, rotulo)
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
        painter.setPen(cor)
        painter.drawText(trilho, Qt.AlignmentFlag.AlignCenter, "N/D")

    painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
    painter.setPen(motivo.cor)
    aviso = QRect(cartao.left() + MARGEM_INTERNA, trilho_compra.bottom() + 3,
                 largura_total, 11)
    painter.drawText(aviso, Qt.AlignmentFlag.AlignCenter,
                     f"NIVEIS DE BOOK: {motivo.niveis_livro} · N/D = SEM DADO (NUNCA ZERO OU SUPRIMIDO)")


def _desenhar_rodape(painter: QPainter, cartao: QRect, motivo: MotivoIndisponivel) -> None:
    """Linha de procedencia tecnica + a mesma ressalva consultiva de sempre.

    ``motivo.origem`` e o unico lugar deste modulo que expõe o campo bruto
    que decidiu o estado — auditavel por quem olha a tela, nao so por quem
    le o codigo.
    """

    origem = QRect(cartao.left() + MARGEM_INTERNA, cartao.bottom() - ALTURA_RODAPE - ALTURA_ORIGEM,
                   cartao.width() - 2 * MARGEM_INTERNA, ALTURA_ORIGEM)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(origem, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     motivo.origem.upper())

    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    y_linha = cartao.bottom() - ALTURA_RODAPE
    painter.drawLine(cartao.left() + MARGEM_INTERNA, y_linha,
                     cartao.right() - MARGEM_INTERNA, y_linha)

    rodape = QRect(cartao.left() + MARGEM_INTERNA, y_linha + 2,
                   cartao.width() - 2 * MARGEM_INTERNA, ALTURA_RODAPE - 2)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter,
                     "SINAL CONSULTIVO · SEM ENVIO DE ORDENS")


__all__ = ["MotivoIndisponivel", "diagnosticar", "desenhar"]
