"""NEXO AI integrado: arte decorativa aprovada + leituras reais do quadro.

Não lê feed, relógio, sessão ou modelo mutável. Não calcula sinais. As
condições e a histerese reutilizam os diagnósticos do núcleo existente.
Confiança categórica permanece categórica: ALTA nunca vira 100%.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)

from fluxopro.ui import tema_asg
from fluxopro.ui.paineis.asg import ConfiancaASG, DirecaoASG, EstadoASG
from fluxopro.ui.paineis.nexo import EstadoNexo, retangulos
from fluxopro.ui.paineis.nexo import nucleo, vies

VERSAO = "nexo-ai-ui-v1"
CIANO = QColor("#39d5ff")
VIOLETA = QColor("#8b5cf6")
AMBAR = QColor("#ffc038")
TEXTO = QColor("#d9edf7")
SECUNDARIO = QColor("#a1b5c6")
BORDA = QColor("#293d4e")
FUNDO = QColor(6, 12, 18, 0)
NIVEIS_CONF = {ConfiancaASG.BAIXA: 1, ConfiancaASG.MEDIA: 2, ConfiancaASG.ALTA: 3}


@dataclass(frozen=True, slots=True)
class LeituraNexoAI:
    timestamp_ns: int
    fonte: str
    estado_feed: str
    saudavel: bool
    titulo: str
    fase: str
    motivo: str
    condicoes: tuple[tuple[str, str, bool, bool], ...]
    progresso: float | None
    confianca: str
    nivel_confianca: int | None
    confianca_feed: str
    cobertura: str
    niveis_componentes: tuple[tuple[str, int | None], ...]
    forca: float | None
    maker: float | None
    historico: tuple[float, ...]
    janela_s: float | None
    procedencia: str
    formula: str
    divergente: bool
    mercado: str = ""
    """Leitura de DIRECAO DE MERCADO do nucleo (`nexo/nucleo.py`) — o que o
    fluxo esta fazendo AGORA, mesmo sem o filtro decidir. Vazio quando nao ha
    leitura. Existe porque `titulo` responde outra pergunta: ele e a DECISAO
    do filtro, e cai em "AGUARDAR" na maior parte do pregao por construcao."""


def _finito(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (float, int)):
        return None
    return float(valor) if math.isfinite(valor) else None


def forca_publicada(snapshot) -> float | None:
    """Mesma fórmula para valor e histórico; ausência não vira zero."""
    if snapshot is None or snapshot.estado_operacional not in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}:
        return None
    contexto = snapshot.contexto_bruto
    if not contexto or not contexto.bids or not contexto.asks:
        return None
    valores = [l.forca for l in snapshot.matriz.linhas
               if l.componente != "MAKERPROXY"
               and l.confianca is not ConfiancaASG.INDISPONIVEL
               and _finito(l.forca) is not None]
    return max(-1.0, min(1.0, sum(valores) / len(valores))) if valores else None


def _rotulo_mercado(estado: EstadoNexo, direcao) -> str:
    """Texto da leitura do nucleo (MERCADO COMPRADOR/VENDEDOR/LATERAL,
    ALTO RISCO, ULTRA...) — a MESMA funcao pura do layout classico, para as
    duas telas nunca discordarem sobre o que o mercado esta fazendo."""

    leitura = nucleo.leitura_do_nucleo(estado, direcao)
    return nucleo._ROTULO_LEITURA.get(leitura, "")


def compor(estado: EstadoNexo) -> LeituraNexoAI:
    """Projeta o mesmo snapshot em três cards, sem promover Maker ao placar."""
    s = estado.snapshot
    if s is None:
        return LeituraNexoAI(
            timestamp_ns=0, fonte="SEM FONTE", estado_feed="SEM DADOS", saudavel=False,
            titulo="SEM DADOS", fase="CONFIRMAÇÃO BLOQUEADA", motivo="Nenhum snapshot recebido.",
            condicoes=(), progresso=None, confianca="—", nivel_confianca=None,
            confianca_feed="—", cobertura="SEM DADOS", niveis_componentes=(),
            forca=None, maker=None, historico=(), janela_s=None,
            procedencia="SEM FONTE", formula="—", divergente=False, mercado="",
        )
    dados, decisao = s.dados, s.decisao
    operacional = s.estado_operacional
    saudavel = operacional in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
    contexto = s.contexto_bruto
    tem_book = bool(contexto and contexto.bids and contexto.asks)
    estado_feed = operacional.value
    if saudavel and not tem_book:
        saudavel = False
        estado_feed = "SEM BOOK"
    fase_bruta = vies.fase_do_filtro(estado)
    if estado.sinal_ultra is not None and estado.sinal_ultra.timestamp_ns != s.timestamp_ns:
        fase_bruta = vies.AUSENTE
    fases = {vies.AUSENTE: "FILTRO SEM DADOS", vies.SEM_SINAL: "SEM CONFLUÊNCIA",
             vies.CONFIRMANDO: "CONFIRMANDO", vies.ARMADO: "FILTRO ATIVO",
             vies.SEGURANDO: "ALINHAMENTO PERDIDO"}
    fase = fases.get(fase_bruta, "SEM DADOS")
    titulo = (decisao.direcao.value if decisao.direcao in
              {DirecaoASG.COMPRA, DirecaoASG.VENDA} else "AGUARDAR")
    if not saudavel:
        titulo = estado_feed if estado_feed not in {"DESCONHECIDO", "AGUARDANDO"} else "SEM DADOS"
        fase = "CONFIRMAÇÃO BLOQUEADA"
    # 4o item: a condicao esta BLOQUEADA por um pre-requisito (nao foi nem
    # avaliada) — ver `nucleo._Condicao.bloqueada_por`. Os dois layouts leem
    # a MESMA funcao pura, entao a distincao aparece igual nas duas telas.
    condicoes = tuple((c.rotulo, c.medida, bool(c.atendida and saudavel),
                       c.bloqueada_por is not None)
                      for c in nucleo._condicoes_ultra(estado, decisao.direcao))
    motivo = decisao.motivo if saudavel else dados.detalhe
    if estado_feed == "SEM BOOK":
        motivo = "Livro indisponível; leituras dependentes não confirmam."
    ultra = estado.sinal_ultra
    progresso = None
    if (saudavel and ultra and ultra.timestamp_ns == s.timestamp_ns
            and fase_bruta in {vies.CONFIRMANDO, vies.SEGURANDO}
            and 0 < ultra.pendente_desde_ns <= s.timestamp_ns and ultra.janela_alvo_ns > 0):
        progresso = max(0.0, min(1.0, (s.timestamp_ns - ultra.pendente_desde_ns) / ultra.janela_alvo_ns))
    linhas = tuple(s.matriz.linhas)
    validas = tuple(l for l in linhas if l.componente != "MAKERPROXY"
                    and l.confianca is not ConfiancaASG.INDISPONIVEL
                    and _finito(l.forca) is not None)
    forca = forca_publicada(s)
    maker = (_finito(estado.maker.forca) if saudavel and estado.maker is not None
             and estado.maker.confianca is not ConfiancaASG.INDISPONIVEL else None)
    amostras = tuple(a for a in estado.serie_forca_ai[-48:]
                     if a[0] <= s.timestamp_ns and _finito(a[1]) is not None)
    historico = tuple(a[1] for a in amostras) if saudavel and validas else ()
    janela = (max(0, amostras[-1][0] - amostras[0][0]) / 1e9) if len(historico) > 1 else None
    confianca = decisao.confianca if saudavel else ConfiancaASG.INDISPONIVEL
    niveis = tuple((l.componente.replace("MAKERPROXY", "MAKER")[:7],
                    NIVEIS_CONF.get(l.confianca) if saudavel else None) for l in linhas[:6])
    return LeituraNexoAI(
        s.timestamp_ns, dados.fonte, estado_feed, saudavel, titulo, fase, motivo,
        condicoes, progresso, confianca.value.replace("CONF ", ""),
        NIVEIS_CONF.get(confianca), dados.confianca.value.replace("CONF ", ""),
        s.matriz.cobertura if saudavel else "SEM DADOS", niveis,
        None if forca is None else max(-1.0, min(1.0, forca)), maker,
        historico, janela, decisao.procedencia.value, s.processamento.versao,
        bool(forca is not None and maker is not None and forca * maker < 0),
        _rotulo_mercado(estado, decisao.direcao) if saudavel else "",
    )


def caixas_integradas(quadro: QRect) -> dict[str, QRect]:
    """Só a coluna central/esquerda muda; caixas dos gráficos são idênticas."""
    caixas = retangulos(quadro)
    x = quadro.left() + round(quadro.width() * .37)
    direita = caixas["forca"].left()
    caixas["assistente"] = QRect(x, quadro.top(), direita - x, quadro.height())
    caixas["contexto"].setRight(x - 1)
    caixas["banner"] = QRect(quadro.left(), quadro.top() + round(quadro.height() * .56),
                             x - quadro.left(), round(quadro.height() * .10))
    topo_est = quadro.top() + round(quadro.height() * .67)
    caixas["estatistica"] = QRect(quadro.left(), topo_est, x - quadro.left(),
                                  quadro.bottom() - topo_est + 1)
    return caixas


def retangulos_internos(rect: QRect) -> dict[str, QRect]:
    area = rect.adjusted(12, 8, -12, -12)
    cab = 34
    rodape = 26
    gap = 8
    altura_card = max(62, round((area.height() - cab - rodape) * .17))
    topo_cards = area.bottom() - rodape - altura_card * 3 - gap * 2 + 1

    # A ANALISE DE MERCADO (Claude) mora entre a arte do nucleo e os cards.
    # Ate 31/08/2026 este layout pulava as regioes `nucleo` e `vies`
    # (ver `asg.desenhar`), e com elas sumiam da tela as duas leituras que o
    # operador pediu: a analise do Claude e a DIRECAO DE MERCADO. As duas
    # continuavam calculadas e so apareciam no layout classico (F7).
    #
    # O espaco sai da arte, que e cenografia e escala sozinha: em 720p a
    # arte perde ~110px de lado e continua legivel; abaixo de 240px de
    # espaco a analise nao entra, para nao espremer o reator a nada.
    espaco_nucleo = max(10, topo_cards - area.top() - cab - gap)
    altura_analise = 112 if espaco_nucleo >= 250 else 0
    if altura_analise:
        espaco_nucleo -= altura_analise + gap

    caixas_extra = {}
    if altura_analise:
        caixas_extra["analise"] = QRect(
            area.left() + 8, area.top() + cab + espaco_nucleo + gap,
            area.width() - 16, altura_analise)

    return {
        **caixas_extra,
        "moldura": area,
        "titulo": QRect(area.left(), area.top(), area.width(), cab),
        "nucleo": QRect(area.left() + 8, area.top() + cab, area.width() - 16,
                        espaco_nucleo),
        "estado": QRect(area.left() + 8, topo_cards, area.width() - 16, altura_card),
        "confianca": QRect(area.left() + 8, topo_cards + altura_card + gap,
                            area.width() - 16, altura_card),
        "fluxo": QRect(area.left() + 8, topo_cards + 2 * (altura_card + gap),
                        area.width() - 16, altura_card),
        "detalhes": QRect(area.left() + 8, area.bottom() - rodape + 3, area.width() - 16, rodape - 4),
    }


def _fonte(px: int, bold: bool = False) -> QFont:
    fonte = QFont("Consolas")
    fonte.setPixelSize(px)
    fonte.setBold(bold)
    return fonte


def _texto(p: QPainter, r: QRect, texto: str, px: int = 11, cor=TEXTO,
           bold: bool = False, centro: bool = False,
           alinhamento_direita: bool = False) -> None:
    if r.width() < 2 or r.height() < 2:
        return
    p.setFont(_fonte(px, bold))
    p.setPen(cor)
    texto = p.fontMetrics().elidedText(texto, Qt.TextElideMode.ElideRight, r.width())
    if centro:
        horizontal = Qt.AlignmentFlag.AlignHCenter
    elif alinhamento_direita:
        horizontal = Qt.AlignmentFlag.AlignRight
    else:
        horizontal = Qt.AlignmentFlag.AlignLeft
    p.drawText(r, Qt.AlignmentFlag.AlignVCenter | horizontal, texto)


def _quadro(p: QPainter, rect: QRect, cor=CIANO) -> None:
    # Regioes de layout permanecem; a referencia aprovada nao tem molduras.
    pass


@lru_cache(maxsize=1)
def _arte() -> QImage:
    # A imagem inteira fica no pacote para rastreabilidade. Somente o recorte
    # do núcleo sem texto/valores é usado; nenhum dado do mockup é exibido.
    return QImage(str(Path(__file__).resolve().parents[2] / "assets" / "nexo_ai_reference.png"))


@lru_cache(maxsize=8)
def _arte_escalada(lado: int) -> QImage:
    # Pré-escalar evita que drawImage altere a interpolação conforme a
    # região suja/clip de Qt, além de retirar o resize do caminho por quadro.
    imagem = _arte().copy(QRect(624, 126, 354, 334)).scaled(
        lado, lado, Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if imagem.isNull():
        return imagem
    # Dissolve apenas a arte decorativa; dados e textos ficam fora da mascara.
    mascara = QRadialGradient(QPointF(lado / 2, lado / 2), lado * .50)
    mascara.setColorAt(0, QColor(255, 255, 255, 255))
    mascara.setColorAt(.58, QColor(255, 255, 255, 255))
    mascara.setColorAt(.85, QColor(255, 255, 255, 70))
    mascara.setColorAt(1, QColor(255, 255, 255, 0))
    p = QPainter(imagem)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.fillRect(imagem.rect(), mascara)
    p.end()
    return imagem


def _anel(p: QPainter, rect: QRect, cor, fracao: float | None, texto: str = "") -> None:
    p.setBrush(Qt.BrushStyle.NoBrush)
    for recuo in (0, 6, 12):
        p.setPen(QPen(BORDA, 1))
        p.drawEllipse(rect.adjusted(recuo, recuo, -recuo, -recuo))
    p.setPen(QPen(cor, 3))
    if fracao is not None:
        p.drawArc(rect.adjusted(5, 5, -5, -5), 90 * 16, -round(360 * 16 * fracao))
    else:
        p.drawArc(rect.adjusted(5, 5, -5, -5), 40 * 16, 100 * 16)
    interno = rect.adjusted(4, 4, -4, -4)
    conteudo = texto or "◇"
    tamanho = 15
    p.setFont(_fonte(tamanho, True))
    while p.fontMetrics().horizontalAdvance(conteudo) > interno.width() and tamanho > 10:
        tamanho -= 1
        p.setFont(_fonte(tamanho, True))
    _texto(p, interno, conteudo, tamanho, cor, True, True)


def desenhar(p: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """Raster local integral: um clip externo não muda glyphs/antialiasing.

    Qt pode rasterizar primitivas e texto de forma diferente quando o clip
    corta a geometria. Compor primeiro e copiar 1:1 garante equivalência
    exata entre repintura parcial e completa. Buffer temporário de um card
    composto, sem retenção por tick ou exposição de objeto mutável.
    """
    if rect.width() <= 0 or rect.height() <= 0:
        return
    camada = QImage(rect.size(), QImage.Format.Format_ARGB32_Premultiplied)
    camada.fill(FUNDO)
    local = QPainter(camada)
    try:
        _desenhar_conteudo(local, QRect(0, 0, rect.width(), rect.height()), estado)
    finally:
        local.end()
    p.save()
    try:
        p.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        # Preto da arte do nucleo nao cria um retangulo sobre o wallpaper.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.drawImage(rect.topLeft(), camada)
    finally:
        p.restore()


def _desenhar_conteudo(p: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < 160 or rect.height() < 350:
        _texto(p, rect, "OPERADOR B3 · AMPLIE O PAINEL", 11, centro=True)
        return
    p.save()
    try:
        p.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        p.fillRect(rect, FUNDO)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        caixas = retangulos_internos(rect)
        modelo = compor(estado)
        _quadro(p, caixas["moldura"])
        _texto(p, caixas["titulo"], "OPERADOR B3", 23, CIANO, True, True)

        # A arte aprovada é cenografia; o movimento adicional só usa o
        # timestamp congelado. Não há QTimer, thread ou chamada de modelo.
        core = caixas["nucleo"]
        lado = min(core.width(), max(1, core.height() - 20))
        destino = QRect(core.center().x() - lado // 2, core.top(), lado, lado)
        arte = _arte_escalada(lado)
        if not arte.isNull():
            p.setOpacity(1.0 if modelo.saudavel else .25)
            p.drawImage(destino.topLeft(), arte)
            p.setOpacity(1.0)
        else:
            _anel(p, destino.adjusted(15, 15, -15, -15), CIANO, None)
        if modelo.saudavel:
            angulo = (modelo.timestamp_ns % 12_000_000_000) / 12_000_000_000 * 360
            p.setPen(QPen(CIANO, 1))
            anel = destino.adjusted(lado // 6, lado // 6, -lado // 6, -lado // 6)
            p.drawArc(anel, int(angulo * 16), 20 * 16)
        status_rect = QRect(core.left(), core.bottom() - 17, core.width(), 18)
        _texto(p, status_rect, f"{modelo.fonte} · {modelo.estado_feed}", 11,
               CIANO if modelo.saudavel else AMBAR, centro=True)

        # ANALISE DE MERCADO (Claude) — trazida do layout classico em
        # 31/08/2026 (ver `retangulos_internos`). O desenho e o MESMO
        # modulo que o classico usa: uma leitura, um renderizador.
        caixa_analise = caixas.get("analise")
        if caixa_analise is not None:
            from fluxopro.ui.paineis.nexo import analise as _analise_ui

            _analise_ui.desenhar_analise(p, caixa_analise,
                                         getattr(estado, "analise_ia", None))

        compacto = rect.width() < 320 or rect.height() < 670
        cor_estado = (tema_asg.NEXO_VERDE if modelo.titulo == "COMPRA" else
                      tema_asg.NEXO_ROSA if modelo.titulo == "VENDA" else AMBAR)
        r = caixas["estado"]
        _quadro(p, r, cor_estado)
        # Os outros cards têm cabeçalho de 30px: o anel precisa caber
        # ABAIXO dele também em 720p, sem atravessar a borda inferior.
        raio = min(70, r.height() - 40, r.width() // 4)
        icon = QRect(r.left() + 12, r.center().y() - raio // 2, raio, raio)
        _anel(p, icon, cor_estado, modelo.progresso)
        direita = r.left() + raio + 24
        w = r.right() - direita - 10
        _texto(p, QRect(direita, r.top() + 7, w, 26), modelo.titulo,
               20 if compacto else 23, cor_estado, True)
        # A DIRECAO DE MERCADO ao lado da fase do filtro. Sao leituras
        # diferentes e o card precisava dizer as duas: `titulo` e a DECISAO
        # (que fica em AGUARDAR quase o pregao inteiro, por construcao do
        # filtro) e `mercado` e o que o fluxo esta fazendo AGORA. Ate
        # 31/08/2026 este layout mostrava so a primeira, e o operador via
        # "AGUARDAR" com o mercado claramente direcional.
        cor_mercado = (tema_asg.NEXO_VERDE if "COMPRADOR" in modelo.mercado else
                       tema_asg.NEXO_ROSA if "VENDEDOR" in modelo.mercado else
                       AMBAR if "RISCO" in modelo.mercado else SECUNDARIO)
        if modelo.mercado and modelo.mercado != modelo.titulo:
            _texto(p, QRect(direita, r.top() + 34, w, 16), modelo.fase, 10, SECUNDARIO)
            _texto(p, QRect(direita, r.top() + 34, w, 16), modelo.mercado, 10,
                   cor_mercado, alinhamento_direita=True)
        else:
            _texto(p, QRect(direita, r.top() + 34, w, 16), modelo.fase, 10, SECUNDARIO)
        if modelo.progresso is not None:
            p.fillRect(QRect(direita, r.top() + 52, w, 3), BORDA)
            p.fillRect(QRect(direita, r.top() + 52, round(w * modelo.progresso), 3), cor_estado)
        else:
            # As lampadas representam somente gates do ULTRA; Renko continua
            # no grafico/contexto, mas nao e condicao de acionamento.
            for i, (nome, _, passou, bloqueada) in enumerate(modelo.condicoes):
                quantidade = max(1, len(modelo.condicoes))
                cell = QRect(direita + i * w // quantidade, r.bottom() - 21,
                             w // quantidade, 14)
                # "·" = nem chegou a ser avaliada (pre-requisito apagado);
                # "−" = avaliada e nao atendida.
                marca = "+" if passou else ("·" if bloqueada else "−")
                _texto(p, cell, marca + nome[:3], 9,
                       CIANO if passou else SECUNDARIO)
        if not compacto and r.height() > 105:
            _texto(p, QRect(direita, r.top() + 59, w, 16), modelo.motivo, 10, SECUNDARIO)

        r = caixas["confianca"]
        _quadro(p, r)
        _texto(p, QRect(r.left() + 14, r.top() + 5, r.width() - 28, 19), "CONFIANÇA", 12, CIANO)
        icon = QRect(r.left() + 12, r.top() + 30, raio, raio)
        nivel = modelo.nivel_confianca
        _anel(p, icon, CIANO, nivel / 3 if nivel is not None else None,
              f"{nivel}/3" if nivel is not None else "—")
        direita = r.left() + raio + 24
        w = r.right() - direita - 10
        _texto(p, QRect(direita, r.top() + 26, w, 23),
               "SEM DADOS" if nivel is None else modelo.confianca, 18, TEXTO, True)
        _texto(p, QRect(direita, r.top() + 49, w, 15),
               f"FEED {modelo.confianca_feed} · COB. {modelo.cobertura}", 10, SECUNDARIO)
        if r.height() > 108 and modelo.niveis_componentes:
            n = len(modelo.niveis_componentes)
            for i, (nome, conf) in enumerate(modelo.niveis_componentes):
                x = direita + i * w // n
                bw = max(4, w // n - 8)
                altura = (conf or 0) * 7
                p.fillRect(QRect(x, r.bottom() - 22 - altura, bw, altura or 1), CIANO if conf else BORDA)
                _texto(p, QRect(x - 2, r.bottom() - 17, w // n, 13), nome[:3], 8, SECUNDARIO)
        else:
            _texto(p, QRect(direita, r.bottom() - 23, w, 17), modelo.procedencia, 10, CIANO)

        r = caixas["fluxo"]
        _quadro(p, r)
        _texto(p, QRect(r.left() + 14, r.top() + 5, r.width() - 28, 18), "FORÇA DO FLUXO", 12, CIANO)
        icon = QRect(r.left() + 12, r.top() + 29, raio, raio)
        forca = modelo.forca
        cor = (tema_asg.NEXO_VERDE if forca is not None and forca > 0 else
               tema_asg.NEXO_ROSA if forca is not None and forca < 0 else CIANO)
        _anel(p, icon, cor, abs(forca) if forca is not None else None,
              f"{forca * 100:+.0f}%" if forca is not None else "—")
        direita = r.left() + raio + 24
        w = r.right() - direita - 10
        _texto(p, QRect(direita, r.top() + 26, w, 17),
               "SEM DADOS" if forca is None else
               "COMPRADORA" if forca > 0 else "VENDEDORA" if forca < 0 else "EQUILÍBRIO", 11, cor)
        waveform = QRect(direita, r.top() + 47, w, max(9, r.height() - 77))
        p.setPen(QPen(BORDA, 1))
        p.drawLine(waveform.left(), waveform.center().y(), waveform.right(), waveform.center().y())
        if len(modelo.historico) > 1:
            path = QPainterPath()
            for i, valor in enumerate(modelo.historico):
                ponto = QPointF(waveform.left() + i * (w - 1) / (len(modelo.historico) - 1),
                                waveform.center().y() - valor * waveform.height() / 2)
                path.moveTo(ponto) if i == 0 else path.lineTo(ponto)
            p.setPen(QPen(CIANO, 1.2))
            p.drawPath(path)
        maker = "—" if modelo.maker is None else f"{modelo.maker * 100:+.0f}%"
        _texto(p, QRect(direita, r.bottom() - 23, w, 17),
               f"MAKER {maker}" + (" · DIVERGE" if modelo.divergente else " · AUXILIAR"),
               10, AMBAR if modelo.divergente else SECUNDARIO)
        _texto(p, caixas["detalhes"], "DETALHES F6 · CLÁSSICO F7", 10, SECUNDARIO, centro=True)
    finally:
        p.restore()


def desenhar_resumo(p: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    """A área do AGUARDAR duplicado passa a explicar bloqueios e alertas.

    DEFEITO CORRIGIDO EM 31/08/2026 (operador: "ainda esta faltando o alerta
    de suporte e resistencia, ATE AGORA NAO TEVE").

    O alerta de S/R foi escrito em `nexo/banner.py`, mas o layout integrado
    NÃO desenha o banner: `asg.desenhar` troca a região por esta função
    (`if self._nexo_ai_ativo and nome == "banner"`). Ou seja, o alerta
    existia, era calculado a cada quadro e **não tinha como aparecer na
    tela**. Agora esta faixa desenha a MESMA placa do clássico quando há
    alerta de suporte/resistência — um renderizador, dois layouts.
    """

    from fluxopro.ui.paineis.nexo import banner as _banner

    alerta_sr = _banner.alerta_suporte_resistencia_retido(estado)
    if alerta_sr is not None:
        titulo, subtitulo, cor, para_cima = alerta_sr
        p.save()
        try:
            p.setClipRect(rect, Qt.ClipOperation.IntersectClip)
            p.fillRect(rect, FUNDO)
            _banner._desenhar_placa_alerta(p, rect, cor, "ALERTA", titulo,
                                           subtitulo, seta_para_cima=para_cima)
        finally:
            p.restore()
        return

    p.save()
    try:
        p.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        p.fillRect(rect, FUNDO)
        modelo = compor(estado)
        _texto(p, QRect(rect.left() + 8, rect.top() + 2, rect.width() - 16, 18),
               modelo.motivo, 11, SECUNDARIO)
        alertas = []
        if estado.alerta_exaustao:
            alertas.append(f"EXAUSTÃO {estado.alerta_exaustao[0]}")
        if estado.risco_volatilidade >= nucleo.LIMIAR_ALTO_RISCO_VOL:
            alertas.append("VOLATILIDADE ALTA · PROXY")
        _texto(p, QRect(rect.left() + 8, rect.top() + 23, rect.width() - 16, 18),
               " · ".join(alertas) if alertas else "CONDIÇÕES DETALHADAS NO OPERADOR B3 [F6]", 10,
               AMBAR if alertas else CIANO)
        _texto(p, QRect(rect.left() + 8, rect.bottom() - 20, rect.width() - 16, 18),
               f"{modelo.procedencia} · {modelo.formula} · CONSULTIVO", 9, SECUNDARIO)
    finally:
        p.restore()


def texto_auditoria(estado: EstadoNexo) -> str:
    m = compor(estado)
    if estado.snapshot is None:
        return "OPERADOR B3 — SEM DADOS\nNenhum snapshot recebido. Sem confirmação e sem envio de ordens."
    linhas = ["OPERADOR B3 — SNAPSHOT CONGELADO", f"Versão visual: {VERSAO}",
              f"Timestamp: {m.timestamp_ns} ns", f"Fonte: {m.fonte}",
              f"Feed: {m.estado_feed} | confiança categórica: {m.confianca_feed}",
              f"Decisão: {m.titulo} | {m.fase}", f"Motivo: {m.motivo}",
              f"Confiança decisão: {m.confianca} (nível, não probabilidade)",
              f"Cobertura publicada: {m.cobertura}", f"Procedência: {m.procedencia}",
              f"Fórmula publicada: {m.formula}",
              "Força: média das linhas disponíveis da matriz, excluindo MakerProxy.",
              f"Força calculada [-1, +1]: {m.forca!r}",
              "Histórico: até 48 snapshots publicados, mesma fórmula da força; reinicia em falhas.",
              f"Janela do histórico: {m.janela_s} segundos | Maker auxiliar: {m.maker}",
              "", "CONDIÇÕES DO FILTRO (diagnóstico existente):"]
    linhas += [
        f"{'OK' if ok else ('AGUARDA PRE-REQUISITO' if bloq else 'PENDENTE')} · {nome}: {valor}"
        for nome, valor, ok, bloq in m.condicoes
    ]
    linhas += ["", "GATES DA DECISÃO:"]
    linhas += [f"{g.nome}: {g.resultado.value} · {g.motivo}" for g in estado.snapshot.decisao.gates]
    d = estado.snapshot.decisao
    linhas += ["", f"Stop informativo: {d.stop}", f"Alvos informativos: {d.alvo_1} / {d.alvo_2} / {d.alvo_3}",
               "", "MATRIZ:"]
    linhas += [f"{l.componente}: {l.valor} | força={l.forca!r} | {l.confianca.value} | {l.procedencia.value} | {l.detalhe}"
               for l in estado.snapshot.matriz.linhas]
    linhas += ["", "HISTÓRICO DA FORÇA (timestamp ns | valor [-1, +1]):"]
    linhas += [f"{ts} | {valor!r}" for ts, valor in estado.serie_forca_ai
               if ts <= m.timestamp_ns] if m.saudavel else ["INDISPONÍVEL"]
    linhas += ["", "EVIDÊNCIAS:"]
    linhas += [f"{e.timestamp_ns} | {e.origem} | {e.evento} | {e.leitura} | {e.procedencia.value}"
               for e in estado.snapshot.evidencias.itens]
    linhas += ["", "Arte holográfica decorativa. Sem processamento por LLM. Sem envio de ordens."]
    return "\n".join(linhas)
