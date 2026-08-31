"""Regiao PRESSAO + INSTRUMENTO (x 0,63-1,00 · y 0,86-1,00).

Esqueleto extraido de ``PainelNexoMercadoASG._desenhar_estatistica_nexo``.
Fecha o canto inferior direito do quadro, encostando nas duas bordas.

Duas leituras vivem lado a lado, as duas so consultivas:

* **Par de pressao oposto** — UM trilho continuo cobrindo a largura
  inteira do bloco, preenchido verde da borda esquerda ate o ponto real
  do corte (a fracao de compra) e vermelho do corte ate a borda direita
  (o resto, sempre a fracao de venda). Como as duas fracoes somam 100, as
  duas cores sempre tocam as duas pontas do trilho — nunca sobra vao vazio
  numa ponta enquanto a outra fica cheia. Os dois percentuais ficam nas
  pontas externas do trilho (COMPRA a esquerda, VENDA a direita), com o
  rotulo de cada lado logo acima, e nada e desenhado entre os dois
  numeros: o par de pressao e um objeto so, nao dois numeros que o
  operador precisa juntar de cabeca.
* **Bloco do instrumento** — um selo circular (agulha propria, sem logotipo
  ou rosto de terceiros) cujo angulo espelha a mesma forca que preenche os
  trilhos, mais o rotulo do ativo corrente e a amplitude observada da serie,
  ambos com unidade explicita.

O par percentual e um **proxy de pressao declarado**; nao e execucao, nao e
posicao e nao ha botao. O rotulo do ativo vem da grade de precos
(``EstadoNexo.grid``) — a unica pista de instrumento que atravessa a
fronteira ate esta regiao — e a amplitude vem inteiramente da serie de
precos ja congelada no snapshot (nunca inventada quando a serie ainda nao
tem dois pontos).

Achado do operador (27/08/2026, MUDANCAS E IMPLEMENTACOES.docx): "revise a
logica dos players... na vdd esse indicador tem intuito de mostrar a
posicao em percentual baseado em estatistica de quanto aquele maior player
que esta mandando no mercado esta propenso a positivo ou negativo". Ate
26/08/2026 este numero era LITERALMENTE `50 + MakerProxy.forca*50` — o
MESMO score do gauge EQUILIBRIO (nucleo/contexto.py) e do ladrilho
PRESENCA, so reescalado de [-100%,+100%] pra [0,100]. Nao havia calculo de
"player dominante" nenhum por tras — era o mesmo numero em tres lugares
fingindo ser tres leituras.

IMPRECISO — nao ha, em nenhuma fonte deste projeto (pesquisa/*.md), uma
formula de "player dominante" pra reproduzir; nao existe dado de
identidade de contraparte no feed (a B3 nao publica isso pro tape
publico). O que muda aqui e uma composicao HONESTA de duas leituras
JA EXISTENTES e INDEPENDENTES entre si — nunca fingida como identificacao
de player real:

  pressao = PESO_MAKER_PRESSAO * MakerProxy.forca
          + PESO_RITMO_PRESSAO * Velocimetro.forca (linha "RITMO")

MakerProxy (absorcao/reposicao/divergencia/clips/agressao) capta
COMPOSICAO do livro; Velocimetro capta MAGNITUDE/MANUTENCAO do movimento
de preco — duas fontes que podem divergir (ex.: livro absorvendo compra
mas preco ainda caindo), o que o numero antigo (so Maker) nunca conseguia
expressar. Pesos (0,70/0,30) sao defaults de engenharia deste projeto,
nao da ASG — dao mais peso ao MakerProxy por ele ja ser, em si, um
agregado de 5 componentes (ver `fluxopro/asg/sinal_ultra.py` pro mesmo
padrao de composicao declarada).
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF, QPixmap

from fluxopro.core.eventos import WDO_GRID, WIN_GRID
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.asg import ConfiancaASG
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import dominancia as _dominancia_ui

PESO_MAKER_PRESSAO = 0.70
PESO_RITMO_PRESSAO = 0.30
"""IMPRECISO — proxy de engenharia deste projeto (ver docstring do modulo).
Somam 1.0 de proposito: `pressao` fica na mesma escala [-1, 1] de cada
componente sem precisar renormalizar."""

MARGEM_INTERNA = 8
GAP_COLUNAS = 14
ALTURA_SUBLINHADO = 4
ALTURA_RODAPE = 13
ALTURA_LEGENDA = 11
RESERVA_INFERIOR = ALTURA_RODAPE + ALTURA_SUBLINHADO + ALTURA_LEGENDA
FRACAO_INSTRUMENTO = 0.40
ESPESSURA_ANEL = 1.6
FRACAO_AGULHA = 0.34
EXTENSAO_EIXO = 2
LARGURA_EIXO = 2
OPACIDADE_ANIMAL_ATIVO = 235
OPACIDADE_ANIMAL_SECUNDARIO = 82
OPACIDADE_ANIMAL_NEUTRO = 64

_COR_CONFIANCA = {
    ConfiancaASG.ALTA: tema_asg.CONFIANCA_ALTA,
    ConfiancaASG.MEDIA: tema_asg.CONFIANCA_MEDIA,
    ConfiancaASG.BAIXA: tema_asg.CONFIANCA_BAIXA,
    ConfiancaASG.INDISPONIVEL: tema_asg.CONFIANCA_INDISPONIVEL,
}


def _rotulo_instrumento(grid: object) -> str:
    """Deriva o rotulo do ativo da propria grade de precos do quadro.

    Nao ha campo de simbolo na fronteira que chega ate esta regiao — o unico
    dado por-instrumento que ``EstadoNexo`` carrega e a grade de conversao de
    ticks. WDO e WIN sao as duas grades conhecidas do projeto (ver
    ``fluxopro.core.eventos``); qualquer outra grade cai num rotulo honesto
    derivado do proprio tamanho de tick, em vez de um ticker fixo chutado.
    """

    tick = getattr(grid, "tick_size", None)
    decimais = getattr(grid, "decimals", None)
    if tick == WDO_GRID.tick_size and decimais == WDO_GRID.decimals:
        return "WDO · B3"
    if tick == WIN_GRID.tick_size and decimais == WIN_GRID.decimals:
        return "WIN · B3"
    if tick is None:
        return "ATIVO INDISPONIVEL"
    return f"TICK {tick:g}"


def _formatar_pontos(valor: float, casas: int) -> str:
    if casas <= 0:
        return str(int(round(valor)))
    texto = f"{valor:.{casas}f}"
    inteiro, _, decimal = texto.partition(".")
    return f"{inteiro},{decimal}"


def _texto_amplitude(estado: EstadoNexo) -> str:
    """Amplitude observada da propria serie do quadro — nunca inventada.

    Com menos de dois pontos a serie ainda nao tem uma faixa: o estado
    honesto e declarar indisponivel, nao fabricar um numero.
    """

    precos = [preco for _, preco, _, _ in estado.serie]
    if len(precos) < 2:
        return "AMPLITUDE INDISPONIVEL"
    diferenca_ticks = max(precos) - min(precos)
    pontos = estado.grid.to_price(diferenca_ticks)
    return f"{_formatar_pontos(pontos, estado.grid.decimals)} PTS"


def _forca_ritmo(estado: EstadoNexo) -> float:
    """Forca da leitura RITMO (Velocimetro) — `0.0` se ainda indisponivel.

    `estado.leituras` e a MESMA tupla (nome, LinhaMatrizASG) que alimenta
    os 4 ladrilhos do Placar Estatistico (estatistica.py) — nenhum dado
    novo e lido aqui, so uma leitura que ja atravessa a fronteira.
    """

    for nome, linha in estado.leituras:
        if nome == "RITMO":
            return max(-1.0, min(1.0, float(getattr(linha, "forca", 0.0))))
    return 0.0


LIMIAR_COERENCIA = 0.10
"""IMPRECISO — limiar de engenharia. So carimbamos divergencia entre a
PRESSAO (livro: maker+ritmo) e o SALDO do PLACAR (as 4 leituras derivadas)
quando os dois passam desta magnitude com sinais opostos. Abaixo disso,
sinal oposto e ruido em torno do zero, nao discordancia de leitura."""


def rotulo_coerencia(score_pressao: float, saldo_placar: float) -> str:
    """Reconcilia, na propria tela, os dois numeros que o operador via
    lado a lado sem relacao declarada.

    Ate 27/08/2026 o quadro podia mostrar a barra de pressao em VENDA e o
    placar logo abaixo em COMPRA sem UMA palavra explicando por que. Eles
    medem coisas diferentes de propria construcao (pressao = livro agora;
    placar = 4 leituras derivadas, uma delas desde a abertura), entao
    discordar e legitimo — o que nao e legitimo e discordar em silencio.
    Este rotulo nomeia o estado: ``CONFIRMA``, ``DIVERGE`` ou ``NEUTRO``.
    Nenhum dado novo: e so o sinal dos dois numeros que ja estao na tela.
    """

    if abs(score_pressao) < LIMIAR_COERENCIA or abs(saldo_placar) < LIMIAR_COERENCIA:
        return "NEUTRO VS PLACAR"
    if (score_pressao > 0) == (saldo_placar > 0):
        return "CONFIRMA O PLACAR"
    return "DIVERGE DO PLACAR"


def pressao_composta(maker_forca: float, ritmo_forca: float) -> float:
    """`score` em [-1, 1] — ver docstring do modulo pra formula e pesos."""

    bruta = PESO_MAKER_PRESSAO * maker_forca + PESO_RITMO_PRESSAO * ritmo_forca
    return max(-1.0, min(1.0, bruta))


def intensidades_animais(score: float, tem_leitura: bool) -> tuple[int, int]:
    """Retorna opacidade de touro e urso a partir da MESMA pressão exibida.

    Os animais não são uma segunda fórmula e não emitem ordem: são só uma
    redundância visual acessível do par COMPRA/VENDA. Sem leitura publicável,
    ambos ficam neutros para não sugerir uma direção inventada.
    """

    if not tem_leitura:
        return (OPACIDADE_ANIMAL_NEUTRO, OPACIDADE_ANIMAL_NEUTRO)
    score = max(-1.0, min(1.0, score))
    compra = (score + 1.0) / 2.0
    touro = round(OPACIDADE_ANIMAL_SECUNDARIO + (OPACIDADE_ANIMAL_ATIVO - OPACIDADE_ANIMAL_SECUNDARIO) * compra)
    urso = round(OPACIDADE_ANIMAL_SECUNDARIO + (OPACIDADE_ANIMAL_ATIVO - OPACIDADE_ANIMAL_SECUNDARIO) * (1.0 - compra))
    return (touro, urso)


def _desenhar_animal_contorno(
    painter: QPainter, rect: QRect, *, touro: bool, opacidade: int
) -> None:
    """Desenha um touro/urso geométrico original, leve e independente.

    O traço é propositalmente feito em QPainter: não há imagem, avatar nem
    ativo de terceiro para copiar, carregar ou animar fora do snapshot.
    """

    if rect.width() < 14 or rect.height() < 10:
        return
    cor_base = tema_asg.NEXO_VERDE if touro else tema_asg.NEXO_ROSA
    cor = QColor(cor_base)
    cor.setAlpha(max(0, min(255, opacidade)))
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()

    def ponto(fx: float, fy: float) -> QPointF:
        return QPointF(x + w * fx, y + h * fy)

    # Silhuetas lineares próprias. O contorno ocupa quase toda a caixa para
    # continuar reconhecível no quadro denso: antes o desenho usava poucas
    # linhas e a leitura acabava parecendo um ícone genérico comprimido.
    # Não tenta reproduzir ilustração, marca ou logotipo de terceiros.
    if touro:
        contorno = ((.02, .66), (.12, .43), (.30, .23), (.53, .24), (.69, .35), (.80, .19),
                    (.76, .48), (.98, .56), (.86, .68), (.76, .70), (.70, .94), (.57, .94),
                    (.53, .70), (.31, .72), (.25, .96), (.12, .96), (.15, .69), (.02, .66))
        detalhes = (
            ((.12, .43), (.31, .52), (.53, .24)),
            ((.31, .23), (.40, .67), (.69, .35)),
            ((.40, .67), (.53, .70), (.63, .47)),
            ((.70, .48), (.86, .68)),
            ((.06, .50), (.01, .35), (.15, .38)),
        )
    else:
        contorno = ((.02, .66), (.10, .42), (.25, .31), (.34, .08), (.45, .30), (.64, .27),
                    (.79, .39), (.96, .58), (.84, .69), (.76, .70), (.71, .95), (.58, .95),
                    (.53, .70), (.33, .72), (.27, .96), (.14, .96), (.16, .69), (.02, .66))
        detalhes = (
            ((.10, .42), (.31, .55), (.45, .30)),
            ((.25, .31), (.39, .68), (.64, .27)),
            ((.39, .68), (.53, .70), (.61, .46)),
            ((.61, .46), (.84, .69)),
            ((.17, .39), (.09, .22), (.29, .26)),
        )

    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Halo curto, seguido pelo traço nítido: cria presença sem transformar
    # o ícone em decoração independente ou poluir a leitura numérica.
    halo = QColor(cor)
    halo.setAlpha(max(18, cor.alpha() // 4))
    painter.setPen(QPen(halo, 3.2))
    painter.drawPolyline(QPolygonF([ponto(px, py) for px, py in contorno]))
    painter.setPen(QPen(cor, 1.55))
    painter.drawPolyline(QPolygonF([ponto(px, py) for px, py in contorno]))
    painter.setPen(QPen(cor, 1.0))
    for linha in detalhes:
        painter.drawPolyline(QPolygonF([ponto(px, py) for px, py in linha]))
    painter.restore()


@lru_cache(maxsize=1)
def _referencia_animais() -> QPixmap:
    """Atlas aprovado, carregado uma vez na thread de UI, sem I/O por quadro."""
    return QPixmap(str(Path(__file__).resolve().parents[2] / "assets" / "pressao_reference.png"))


@lru_cache(maxsize=2)
def _sprite_animal(touro: bool) -> QPixmap:
    """Chave de cor nativa do Qt remove apenas o fundo neutro do atlas.

    Processa ~6 mil pixels uma vez por animal; nunca durante cada tick.
    A imagem aprovada fica intacta em disco para auditoria.
    """
    atlas = _referencia_animais()
    if atlas.isNull():
        return atlas
    fonte = QRect(1080, 831, 94, 67) if touro else QRect(1289, 836, 69, 58)
    imagem = atlas.copy(fonte).toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(imagem.height()):
        for x in range(imagem.width()):
            cor = imagem.pixelColor(x, y)
            contraste = (cor.green() - max(cor.red(), cor.blue())) if touro else (cor.red() - max(cor.green(), cor.blue()))
            cor.setAlpha(min(255, max(0, contraste - 4) * 25))
            imagem.setPixelColor(x, y, cor)
    return QPixmap.fromImage(imagem)


def _desenhar_animal_dominancia(
    painter: QPainter, rect: QRect, *, touro: bool, opacidade: int
) -> None:
    """Usa apenas o animal do atlas aprovado; números continuam dados reais.

    As coordenadas apontam para ilustrações sem texto. A chave de cor integra
    a referência ao painel sem inserir números/candles do mockup.
    """
    atlas = _sprite_animal(touro)
    if atlas.isNull():
        _desenhar_animal_contorno(painter, rect, touro=touro, opacidade=opacidade)
        return
    fonte = QRectF(atlas.rect())
    escala = min(rect.width() / fonte.width(), rect.height() / fonte.height())
    largura, altura = fonte.width() * escala, fonte.height() * escala
    destino = QRectF(rect.x() + (rect.width() - largura) / 2,
                     rect.y() + (rect.height() - altura) / 2, largura, altura)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setOpacity(min(1.0, max(0.0, opacidade / 210.0)))
    painter.drawPixmap(destino, atlas, fonte)
    painter.restore()


def _desenhar_trilho_pressao(
    painter: QPainter, trilho: QRect, compra: int, venda: int, cor_compra: object, cor_venda: object
) -> None:
    """Trilho UNICO, continuo, cobrindo a largura inteira do bloco.

    Nao sao dois medidores separados por um vao: e um so retangulo dividido
    no ponto real do corte — a fracao de compra, contada a partir da borda
    esquerda. Verde preenche da borda esquerda ate o corte, vermelho do
    corte ate a borda direita; como as duas fracoes somam sempre 100
    (``venda = 100 - compra``), as duas cores sempre tocam as duas pontas
    do trilho, sem vao morto numa ponta enquanto a outra fica cheia — o
    defeito antigo de dois cotos que nao alcancavam as bordas. O marcador
    do corte fica exatamente onde a cor muda, nunca num centro fixo, e e
    desenhado por cima dos preenchimentos para continuar visivel mesmo
    quando um lado chega a 0% ou 100%.
    """
    compra_travada = max(0, min(100, compra))
    corte_x = trilho.left() + int(round(trilho.width() * compra_travada / 100.0))
    limite_direito = trilho.right() + 1
    if corte_x > trilho.left():
        painter.fillRect(
            QRect(trilho.left(), trilho.top(), corte_x - trilho.left(), trilho.height()),
            cor_compra,
        )
    if corte_x < limite_direito:
        painter.fillRect(
            QRect(corte_x, trilho.top(), limite_direito - corte_x, trilho.height()),
            cor_venda,
        )
    eixo = QRect(
        corte_x - LARGURA_EIXO // 2,
        trilho.top() - EXTENSAO_EIXO,
        LARGURA_EIXO,
        trilho.height() + 2 * EXTENSAO_EIXO,
    )
    painter.fillRect(eixo, tema_asg.NEXO_MUTED)


def _desenhar_selo_instrumento(
    painter: QPainter, centro: QPointF, diametro: float, score: float, cor_status: object
) -> None:
    """Selo circular original (sem logotipo/rosto de terceiros).

    A agulha reflete o mesmo ``score`` que preenche os trilhos de pressao —
    o selo nao e decoracao solta, e a mesma leitura consultiva num segundo
    formato. O ponto de status no canto usa a confianca do MAKERPROXY.
    """

    raio = diametro / 2.0
    anel = QRect(
        int(centro.x() - raio), int(centro.y() - raio), int(diametro), int(diametro)
    )
    painter.setPen(QPen(tema_asg.NEXO_CIANO, ESPESSURA_ANEL))
    painter.setBrush(tema_asg.NEXO_PAINEL_ALTO)
    painter.drawEllipse(anel)

    score_travado = max(-1.0, min(1.0, score))
    angulo = math.radians(-90.0 - 45.0 * score_travado)
    raio_agulha = raio * FRACAO_AGULHA
    ponta = QPointF(
        centro.x() + raio_agulha * math.cos(angulo),
        centro.y() + raio_agulha * math.sin(angulo),
    )
    painter.setPen(QPen(tema_asg.NEXO_TEXTO, ESPESSURA_ANEL))
    painter.drawLine(centro, ponta)

    raio_status = max(2.0, diametro * 0.16)
    centro_status = QPointF(centro.x() + raio * 0.62, centro.y() + raio * 0.62)
    painter.setPen(QPen(tema_asg.NEXO_PAINEL_ALTO, 1.0))
    painter.setBrush(cor_status)
    painter.drawEllipse(centro_status, raio_status, raio_status)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 24 or rect.width() < 140:
        return
    maker = estado.maker
    forca_maker = maker.forca if maker is not None else 0.0
    forca_ritmo = _forca_ritmo(estado)

    # Dominância Comprador/Vendedor (31/08/2026,
    # INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md, pasta Codex):
    # quando o motor determinístico publica um composto válido (LIVE ou
    # REPLAY), o placar BUY/SELL vem DELE — Q6, arredondamento half-away-
    # from-zero, histerese ULTRA — em vez do blend simples 70/30 antigo.
    # Sem leitura válida (STALE/GAP/RECOVERING/UNAVAILABLE), a região
    # degrada para o proxy antigo em vez de travar — mesma regra de
    # honestidade do resto do NEXO: nunca mostrar um placar quebrado, mas
    # também nunca sumir com o único número que a região sempre teve.
    snapshot_dominancia = estado.dominancia_snapshot
    if snapshot_dominancia is not None and snapshot_dominancia.composite is not None:
        score = snapshot_dominancia.composite
        compra = int(round(snapshot_dominancia.buy_percent))
        venda = 100 - compra
        estado_dominancia_txt = _dominancia_ui.rotulo_estado(snapshot_dominancia.estado)
    else:
        score = pressao_composta(forca_maker, forca_ritmo)
        compra = int(max(0.0, min(100.0, 50.0 + score * 50.0)))
        venda = 100 - compra
        estado_dominancia_txt = None
    tem_ritmo = any(nome == "RITMO" for nome, _ in estado.leituras)
    tem_leitura_animais = (
        snapshot_dominancia is not None and snapshot_dominancia.composite is not None
    ) or maker is not None or tem_ritmo
    confianca = getattr(maker, "confianca", None) if maker is not None else None
    cor_status = _COR_CONFIANCA.get(confianca, tema_asg.CONFIANCA_INDISPONIVEL)

    # A regiao encosta na borda direita do quadro: o texto precisa da propria
    # margem interna, senao o glifo final e cortado pelo limite da janela.
    interno = rect.adjusted(MARGEM_INTERNA, 0, -MARGEM_INTERNA, 0)
    largura_instrumento = max(120, int(interno.width() * FRACAO_INSTRUMENTO))
    largura_pressao = max(0, interno.width() - largura_instrumento - GAP_COLUNAS)
    coluna_pressao = QRect(interno.left(), interno.top(), largura_pressao, interno.height())
    coluna_instrumento = QRect(
        coluna_pressao.right() + GAP_COLUNAS, interno.top(),
        interno.right() - (coluna_pressao.right() + GAP_COLUNAS), interno.height(),
    )

    # --- par de pressao oposto -------------------------------------------
    altura_percentual = max(0, rect.height() - RESERVA_INFERIOR)
    metade = coluna_pressao.width() // 2
    tamanho = max(12, min(24, rect.height() // 4))
    painter.setFont(tokens.fonte_numero(tamanho, QFont.Weight.Bold))
    largura_numero = painter.fontMetrics().horizontalAdvance("100%") + 4
    altura_animal = max(12, min(56, altura_percentual - 2))
    largura_animal = max(0, min(80, metade - largura_numero - 4))
    inicio_venda = coluna_pressao.right() + 1 - largura_numero - largura_animal
    painter.setPen(tema_asg.NEXO_VERDE)
    painter.drawText(
        QRect(coluna_pressao.left(), rect.top(), metade, altura_percentual),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        f"{compra:02d}%",
    )
    painter.setPen(tema_asg.NEXO_ROSA)
    painter.drawText(
        QRect(inicio_venda, rect.top(), largura_numero, altura_percentual),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        f"{venda:02d}%",
    )

    # Os dois animais são uma segunda forma de ler EXATAMENTE o mesmo score
    # dos percentuais/trilho. O lado mais forte ganha intensidade, mas os dois
    # permanecem visíveis para comunicar que se trata de balanço relativo,
    # nunca de uma chamada operacional. Com dados ausentes, os dois degradam
    # juntos para o tom neutro e o rodapé continua declarando a procedência.
    opacidade_touro, opacidade_urso = intensidades_animais(score, tem_leitura_animais)
    # O painel é baixo, mas há largura entre percentuais e selo do ativo.
    # Reservar altura e largura reais aqui dá aos animais peso semelhante ao
    # dos números, em vez de deixá-los como glifos acessórios.
    y_animal = rect.top() + max(1, (altura_percentual - altura_animal) // 2)
    area_touro = QRect(
        coluna_pressao.left() + largura_numero, y_animal, largura_animal, altura_animal
    )
    area_urso = QRect(
        inicio_venda + largura_numero,
        y_animal, largura_animal, altura_animal,
    )
    _desenhar_animal_dominancia(
        painter, area_touro, touro=True, opacidade=opacidade_touro
    )
    _desenhar_animal_dominancia(
        painter, area_urso, touro=False, opacidade=opacidade_urso
    )

    legenda = QRect(
        coluna_pressao.left(), rect.bottom() - RESERVA_INFERIOR,
        coluna_pressao.width(), ALTURA_LEGENDA,
    )
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(legenda, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "COMPRA")
    painter.drawText(legenda, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "VENDA")

    y_trilho = rect.bottom() - ALTURA_RODAPE - ALTURA_SUBLINHADO
    trilho = QRect(coluna_pressao.left(), y_trilho, coluna_pressao.width(), ALTURA_SUBLINHADO)
    _desenhar_trilho_pressao(painter, trilho, compra, venda, tema_asg.NEXO_VERDE, tema_asg.NEXO_ROSA)

    rodape = QRect(coluna_pressao.left(), rect.bottom() - ALTURA_RODAPE, coluna_pressao.width(), ALTURA_RODAPE)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    # Import tardio: `estatistica` importa o pacote `nexo`, e este modulo
    # tambem e importado por ele durante a montagem do pacote — resolver a
    # dependencia aqui dentro evita ciclo na carga.
    from fluxopro.ui.paineis.nexo.estatistica import pesos_por_lado

    compra_placar, venda_placar = pesos_por_lado(estado.leituras)
    coerencia = rotulo_coerencia(score, compra_placar - venda_placar)
    if estado_dominancia_txt is not None:
        rotulo_rodape = f"DOMINÂNCIA {estado_dominancia_txt} · {coerencia} · PROXY"
    else:
        rotulo_rodape = (
            f"MAKER {PESO_MAKER_PRESSAO*100:.0f}% + RITMO {PESO_RITMO_PRESSAO*100:.0f}%"
            f" · {coerencia} · {snapshot_dominancia.saude.estado.value if snapshot_dominancia else 'PROXY'}"
        )
    painter.drawText(rodape, Qt.AlignmentFlag.AlignCenter, rotulo_rodape)

    # --- bloco do instrumento ----------------------------------------------
    banda_superior = QRect(
        coluna_instrumento.left(), rect.top(),
        coluna_instrumento.width(), max(0, rect.height() - RESERVA_INFERIOR),
    )
    diametro_selo = max(14.0, min(float(banda_superior.height()), 30.0))
    centro_selo = QPointF(
        banda_superior.left() + diametro_selo / 2.0, banda_superior.center().y()
    )
    _desenhar_selo_instrumento(painter, centro_selo, diametro_selo, score, cor_status)

    x_texto = int(centro_selo.x() + diametro_selo / 2.0 + 8)
    largura_texto = max(0, banda_superior.right() - x_texto)
    faixa_ativo = QRect(x_texto, banda_superior.top(), largura_texto, banda_superior.height())
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        faixa_ativo.adjusted(0, 0, 0, -faixa_ativo.height() // 2),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        "ATIVO",
    )
    painter.setFont(tokens.fonte_numero(max(11, tamanho - 4), QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_CIANO)
    painter.drawText(
        faixa_ativo.adjusted(0, faixa_ativo.height() // 2, 0, 0),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        _rotulo_instrumento(estado.grid),
    )

    banda_inferior = QRect(
        coluna_instrumento.left(), rect.bottom() - RESERVA_INFERIOR,
        coluna_instrumento.width(), RESERVA_INFERIOR,
    )
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(
        banda_inferior, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "AMPLITUDE"
    )
    painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(
        banda_inferior, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        _texto_amplitude(estado),
    )
