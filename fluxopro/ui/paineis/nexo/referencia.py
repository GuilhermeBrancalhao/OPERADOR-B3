"""Reconstrução visual dos frames ASG em uma prancheta de 640 × 270.

Geometria observada em .gauntlet/2026-08-25-asg-real-b/bar/frame_038.jpg.
Todos os valores vêm do EstadoNexo. A arte de identidade pertence ao projeto.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QGradient, QImage, QLinearGradient, QPainterPath, QPen, QRadialGradient
from fluxopro.ui import formato
from . import analitica, assistente, estatistica, pressao

LARGURA, ALTURA = 640, 270
PRETO = QColor('#010203')
BRANCO = QColor('#e3e7e7')
CINZA = QColor('#67716f')
GRADE = QColor('#17201e')
VERDE = QColor('#00ee63')
ROSA = QColor('#f42b59')
AMARELO = QColor('#d5c645')
AZUL = QColor('#39bcd8')
# Material dos gráficos é independente do verde/rosa dos instrumentos do HUD.
# Os frames mostram reflexos menta e rosa mais claros, com laterais profundas.
GRAFICO_ALTA = QColor('#20b77c')
GRAFICO_BAIXA = QColor('#bb496a')
GRAFICO_AMBAR = QColor('#e6cf4b')
GRAFICO_CIANO = QColor('#50c5ef')
GRAFICO_VERDE_NIVEL = QColor('#08e77c')
REGIOES = {
    'ladder': (0, 0, 49, 164),
    'contexto': (49, 0, 198, 165),
    'niveis': (0, 165, 247, 19),
    'banner': (0, 187, 247, 31),
    'estatistica': (0, 226, 247, 44),
    'assistente': (252, 0, 146, 270),
    'nucleo': (252, 0, 146, 100),
    'vies': (252, 100, 146, 170),
    'forca': (399, 0, 241, 101),
    'candles': (399, 102, 241, 130),
    'pressao': (394, 235, 246, 35),
    'detalhes': (520, 239, 120, 31),
}


def viewport(quadro):
    escala = min(quadro.width() / LARGURA, quadro.height() / ALTURA)
    w, h = LARGURA * escala, ALTURA * escala
    return QRectF(quadro.left() + (quadro.width() - w) / 2,
                  quadro.top() + (quadro.height() - h) / 2, w, h), escala


def retangulos(quadro):
    v, escala = viewport(quadro)
    return {nome: QRect(round(v.x() + x * escala), round(v.y() + y * escala),
                        round(w * escala), round(h * escala))
            for nome, (x, y, w, h) in REGIOES.items()}


def texto_tooltip(pos,quadro,estado):
    caixas = retangulos(quadro)
    if caixas['detalhes'].contains(pos):
        return 'F6 ou clique: origens, saúde, fases e níveis do snapshot congelado.'
    if caixas['estatistica'].contains(pos):
        return ('FORÇA OBSERVADA\nCompra e venda são forças independentes, ponderadas pela confiança; '
                'não precisam somar 100% e não são probabilidades.\n'
                f'Histórico: {len(estado.serie_forca_ai)} snapshots, sem Maker na composição.\n'
                'Barras: intensidade da força publicada, não volume de negócios.\nF6: decomposição e procedência.')
    if caixas['pressao'].contains(pos):
        leitura = analitica.pressao_do_snapshot(estado)
        return f'{leitura.origem} · {leitura.estado}\n{leitura.motivo}\nBalanço relativo, não probabilidade de lucro.'
    return None


def _fonte(tamanho, forte=False, italico=False):
    f = QFont('Arial')
    f.setPixelSize(max(1, round(tamanho)))
    f.setBold(forte)
    f.setItalic(italico)
    return f


@lru_cache(maxsize=1024)
def _fonte_texto(tamanho,forte,italico,texto,largura):
    fonte = _fonte(tamanho,forte,italico)
    medida = QFontMetricsF(fonte).horizontalAdvance(texto)
    if medida>largura and medida>0:
        fonte.setStretch(max(50,round(100*largura/medida)))
    return fonte


def _texto(p, x, y, w, h, texto, tamanho=5, cor=CINZA, forte=False,
           centro=False, italico=False):
    fonte = _fonte_texto(tamanho,forte,italico,str(texto),w)
    p.setFont(fonte)
    p.setPen(cor)
    alinhamento = Qt.AlignmentFlag.AlignVCenter
    alinhamento |= Qt.AlignmentFlag.AlignHCenter if centro else Qt.AlignmentFlag.AlignLeft
    p.drawText(QRectF(x, y, w, h), alinhamento, str(texto))


def _alpha(cor, alfa):
    c = QColor(cor)
    c.setAlpha(alfa)
    return c


def _misturar(cor, outra, peso):
    return QColor(*(round(a*(1-peso)+b*peso) for a,b in zip(
        (cor.red(),cor.green(),cor.blue()),
        (outra.red(),outra.green(),outra.blue()))))


def _cor_grafico(e, direcao):
    if not e.paleta.tem_cor:
        return QColor('#b6c2be') if direcao>=0 else QColor('#75817c')
    return GRAFICO_ALTA if direcao>0 else GRAFICO_BAIXA if direcao<0 else CINZA


@lru_cache(maxsize=12)
def _material_3d(rgba,renko):
    """Pincéis normalizados: mesmos reflexos, sem recriá-los por tijolo/tick."""
    cor = QColor.fromRgba(rgba)
    reflexo = (QColor('#8dffd1') if cor.green()>cor.red()*1.3 else
               QColor('#ff98b4') if cor.red()>cor.green()*1.3 else
               _misturar(cor,BRANCO,.55))
    face = QLinearGradient(0,0,1,0)
    face.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    pontos = ([(0,cor.darker(210)),(.12,cor.lighter(105)),
               (.20,_misturar(reflexo,cor,.35)),(.70,cor),
               (.80,cor.darker(150)),(1,cor.darker(270))] if renko else
              [(0,cor.darker(210)),(.12,cor.darker(120)),
               (.29,reflexo),(.40,cor.lighter(115)),
               (.64,cor),(.83,cor.darker(160)),(1,cor.darker(270))])
    for pos,tinta in pontos:
        face.setColorAt(pos,tinta)
    halo = QLinearGradient(0,0,1,0)
    halo.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    halo.setColorAt(0,_alpha(cor,0))
    halo.setColorAt(.5,_alpha(cor,24 if renko else 18))
    halo.setColorAt(1,_alpha(cor,0))
    return (QBrush(face),QBrush(halo),QBrush(_alpha(cor.darker(270),145)),
            QBrush(_alpha(_misturar(reflexo,cor,.2),210)),
            QPen(_alpha(_misturar(reflexo,BRANCO,.2),190),.22),
            QPen(_alpha(cor.darker(280),220),.24),QPen(_alpha(cor,180),.18))


@lru_cache(maxsize=6)
def _material_pavio(rgba):
    cor = QColor.fromRgba(rgba)
    return (QPen(_alpha(cor,17),1.2),QPen(_alpha(cor.darker(125),220),.42),
            QPen(_alpha(_misturar(cor,BRANCO,.45),165),.16))


def _corpo_3d(p, rect, cor, renko=False):
    """Relevo dentro do corpo: não muda abertura, fechamento nem escala.

    Luz superior esquerda, reflexo fino, face lateral escura e oclusão de
    contato. O volume é material, não uma extrusão da geometria de preço.
    """
    if rect.width()<=0 or rect.height()<=0:
        return
    p.save()
    try:
        face,halo,lateral,chanfro,luz_topo,sombra_base,borda = _material_3d(cor.rgba(),renko)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(rect.translated(.35,.32),QColor(0,0,0,135))
        p.fillRect(rect.adjusted(-.65,-.15,.65,.15),halo)
        p.fillRect(rect,face)
        # Reflexos não atravessam um corpo muito curto/doji.
        if rect.height()>=1.15 and rect.width()>=.9:
            d = min(.55 if renko else .38,rect.width()*.17,rect.height()*.2)
            if renko:
                # Chanfro angular, distinto do reflexo quase cilíndrico da vela.
                p.setBrush(chanfro)
                p.drawPath(_caminho([(rect.left(),rect.top()+d),
                                    (rect.left()+d,rect.top()),(rect.right(),rect.top()),
                                    (rect.right()-d,rect.top()+d)],True))
            p.setBrush(lateral)
            p.drawPath(_caminho([(rect.right()-d,rect.top()+d),
                                (rect.right(),rect.top()),(rect.right(),rect.bottom()),
                                (rect.right()-d,rect.bottom()-d)],True))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(luz_topo)
            p.drawLine(QPointF(rect.left()+d,rect.top()+.12),
                       QPointF(rect.right()-d,rect.top()+.12))
            p.setPen(sombra_base)
            p.drawLine(QPointF(rect.left()+d,rect.bottom()-.12),
                       QPointF(rect.right()-.1,rect.bottom()-.12))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(borda)
        p.drawRect(rect)
    finally:
        p.restore()


def _pavio_3d(p,x,alto,baixo,cor):
    p.save()
    try:
        halo,centro,reflexo = _material_pavio(cor.rgba())
        p.setPen(halo)
        p.drawLine(QPointF(x,alto),QPointF(x,baixo))
        p.setPen(centro)
        p.drawLine(QPointF(x,alto),QPointF(x,baixo))
        p.setPen(reflexo)
        p.drawLine(QPointF(x-.08,alto),QPointF(x-.08,baixo))
    finally:
        p.restore()


def _regiao_preco(p,y,cor,forte=False):
    """Região luminosa rasa, centrada no preço verdadeiro da linha."""
    p.save()
    try:
        faixa = QLinearGradient(0,y-1.9,0,y+1.9)
        faixa.setColorAt(0,_alpha(cor,0))
        faixa.setColorAt(.4,_alpha(cor,12 if forte else 7))
        faixa.setColorAt(.5,_alpha(cor,30 if forte else 17))
        faixa.setColorAt(.7,_alpha(cor,9))
        faixa.setColorAt(1,_alpha(cor,0))
        p.fillRect(QRectF(400,y-1.9,216,3.8),faixa)
        pen = QPen(_alpha(cor,135 if forte else 100),.32)
        pen.setDashPattern([9,5,2,5])
        p.setPen(pen)
        p.drawLine(QPointF(400,y),QPointF(616,y))
        p.setPen(QPen(_alpha(cor.darker(250),100),.23))
        p.drawLine(QPointF(400,y+.5),QPointF(616,y+.5))
    finally:
        p.restore()


def _preco(e, ticks):
    return '—' if ticks is None else formato.preco_completo(e.grid, int(ticks))


def _cor(e, valor):
    return (VERDE if valor > 0 else ROSA if valor < 0 else CINZA) if e.paleta.tem_cor else BRANCO


def _linha(e, nome):
    return next((l for n, l in e.leituras if n == nome), None)


def _caminho(pontos, fechado=False):
    path = QPainterPath(QPointF(*pontos[0]))
    for pt in pontos[1:]:
        path.lineTo(QPointF(*pt))
    if fechado:
        path.closeSubpath()
    return path


def _fundo(p):
    p.fillRect(QRectF(0, 0, 640, 270), PRETO)
    # Carcaça de espessura variável: a borda se afunila na parte inferior.
    halo = QRadialGradient(QPointF(102, 67), 94)
    halo.setColorAt(0, QColor(2, 3, 3))
    halo.setColorAt(.52, QColor(5, 6, 5))
    halo.setColorAt(.72, QColor(10, 9, 8))
    halo.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(QRectF(35, 0, 170, 153), halo)
    armadura = QPainterPath(QPointF(42, 116))
    armadura.cubicTo(43, 73, 47, 46, 70, 27)
    armadura.cubicTo(90, 10, 108, 11, 128, 18)
    armadura.cubicTo(144, 24, 157, 22, 171, 12)
    armadura.cubicTo(156, 30, 142, 33, 127, 27)
    armadura.cubicTo(108, 20, 91, 27, 78, 42)
    armadura.cubicTo(63, 61, 63, 88, 71, 106)
    armadura.cubicTo(59, 110, 48, 115, 42, 116)
    armadura.closeSubpath()
    grad = QLinearGradient(48, 18, 125, 114)
    grad.setColorAt(0, QColor('#050505'))
    grad.setColorAt(.32, QColor('#15120f'))
    grad.setColorAt(.55, QColor('#090a08'))
    grad.setColorAt(1, QColor('#020404'))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(armadura)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for recuo, alfa in [(0, 62), (2.3, 40), (7, 18)]:
        costura = QPainterPath(QPointF(65-recuo*.7, 108))
        costura.cubicTo(51-recuo*.45, 82, 63-recuo*.45, 44-recuo*.3, 85, 31-recuo*.45)
        costura.cubicTo(106, 17-recuo*.45, 128, 34-recuo*.25, 145, 35-recuo*.3)
        p.setPen(QPen(QColor(88, 75, 62, alfa), .45))
        p.drawPath(costura)
    # A névoa cobre o limite externo; não há faixa sólida na borda superior.
    nevoa = QRadialGradient(QPointF(78, 52), 59)
    nevoa.setColorAt(0, QColor(44, 33, 25, 21))
    nevoa.setColorAt(.7, QColor(19, 15, 12, 12))
    nevoa.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(QRectF(30, 0, 150, 137), nevoa)
    # Pontos de luz assimétricos quebram a superfície lisa sem ruído temporal.
    for x,y,r,alfa in [(61,43,23,15),(78,22,21,11),(111,19,18,7),(50,82,26,9)]:
        manchas = QRadialGradient(QPointF(x,y),r)
        manchas.setColorAt(0,QColor(48,34,23,alfa))
        manchas.setColorAt(1,QColor(0,0,0,0))
        p.fillRect(QRectF(x-r,y-r,r*2,r*2),manchas)
    for ang in range(105, 189, 3):
        rad = math.radians(ang)
        p.setPen(QPen(QColor(70, 60, 49, 35), .3))
        p.drawLine(QPointF(108+math.cos(rad)*63,81-math.sin(rad)*63),
                   QPointF(108+math.cos(rad)*69,81-math.sin(rad)*69))
    p.setPen(QPen(QColor(24, 62, 65, 30), .3))
    for i in range(12):
        curva = QPainterPath(QPointF(432+i*9,270))
        curva.cubicTo(482+i*9,231,550+i*8,184,640,162+i*7)
        p.drawPath(curva)


def _vap(p, e):
    niveis = sorted(e.vap_niveis, reverse=True)
    ultimo = getattr(e.snapshot.contexto_bruto, 'ultimo_preco', None)
    if not niveis:
        _texto(p, 2, 6, 45, 10, 'SEM VOLUME', 4)
        return
    maximo = max(n[1] for n in niveis) or 1
    minimo, max_preco = min(n[0] for n in niveis), max(n[0] for n in niveis)
    margem = max(6, round((max_preco-minimo)*.12))
    minimo -= margem; max_preco += margem
    passo = 147/max(1,max_preco-minimo)
    # Eixo por preço: níveis sem negócios ficam sem barra, nunca têm volume inventado.
    stride = max(1, math.ceil(3/max(.01,passo)))
    for preco in range(minimo,max_preco+1,stride):
        y = 5+(max_preco-preco)*passo
        _texto(p,1,y-1,22,4,_preco(e,preco),2.5,_alpha(CINZA,190))
    for preco, volume, compra, venda, destaque in niveis:
        y = 5+(max_preco-preco)*passo
        p.fillRect(QRectF(24, y, 23 * volume / maximo, max(.45, passo * .65)),
                   QColor(99, 104, 100, 130 if destaque else 78))
        if destaque:
            _texto(p, 1, y - .6, 23, 4, _preco(e, preco), 3, BRANCO)
        if preco == ultimo:
            p.fillRect(QRectF(1, y, 29, max(4, passo)), AMARELO)
            _texto(p, 2, y, 27, max(4, passo), _preco(e, preco), 4, PRETO, True)
        if destaque:
            p.fillRect(QRectF(31, y, 12, 1.1), _cor(e, compra - venda))
    _texto(p, 3, 154, 42, 7, 'VAP · SESSÃO' if e.vap_timeframe_min==0 else f'VAP · {e.vap_timeframe_min}M', 3)


def _medidor(p, e, x, y, r, linha, nome):
    if not analitica.leitura_disponivel(linha) or analitica.motivo_bloqueio(e):
        linha = None
    valor = getattr(linha, 'forca', 0.0) if linha is not None else 0
    cor = _cor(e, valor)
    p.setBrush(PRETO)
    p.setPen(QPen(QColor('#0c1710'), .55))
    p.drawEllipse(QPointF(x, y), r, r)
    brilho = QRadialGradient(QPointF(x, y), r + 3.5)
    brilho.setColorAt(.68, QColor(0, 0, 0, 0))
    brilho.setColorAt(.82, _alpha(cor, 42))
    brilho.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(brilho)
    p.drawEllipse(QPointF(x, y), r + 3.5, r + 3.5)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_alpha(cor, 210), 1.0))
    p.drawArc(QRectF(x-r, y-r, 2*r, 2*r), -36*16, round((182+min(1,abs(valor))*110)*16))
    numero = getattr(linha, 'valor', '—') if linha is not None else '—'
    tamanho = (8 if r>=14 else 7) if len(str(numero))<=4 else (7 if r>=14 else 6)
    _texto(p, x-r, y-6, 2*r, 12, numero, tamanho, BRANCO, True, True)
    _texto(p, x-r-3, y+r-3, 2*r+6, 4, nome, 2.5, _alpha(CINZA,120), centro=True)


def _contexto(p, e):
    micro, macro = _linha(e, 'PULSO'), _linha(e, 'HORIZONTE')
    bloqueado = bool(analitica.motivo_bloqueio(e))
    micro = micro if not bloqueado and analitica.leitura_disponivel(micro) else None
    macro = macro if not bloqueado and analitica.leitura_disponivel(macro) else None
    _texto(p, 151, 36, 36, 6, 'CONTEXTO', 4)
    _medidor(p, e, 171, 70, 14, micro, 'MICRO')
    _medidor(p, e, 216, 27, 12, macro, 'MACRO')
    # Ponteiro do volante: o próprio micro publicado, com marca legível.
    forca = getattr(micro, 'forca', 0.0) if micro is not None else 0.0
    ang = math.radians(137 - max(-1., min(1., forca)) * 108)
    ponta = QPointF(112 + math.cos(ang)*47, 88 - math.sin(ang)*47)
    p.setPen(QPen(QColor('#d6dad4'), 1))
    p.drawLine(ponta, QPointF(ponta.x()+1.8, ponta.y()+2.4))
    maker = e.maker if analitica.leitura_disponivel(e.maker) and not analitica.motivo_bloqueio(e) else None
    score = getattr(maker, 'forca', 0.0) if maker is not None else 0.0
    cor = _cor(e, score)
    x, y, w, h = 180, 89, 16, 36
    glow = QRadialGradient(QPointF(194, 104), 33)
    glow.setColorAt(0, _alpha(cor, 84))
    glow.setColorAt(.43, _alpha(cor, 34))
    glow.setColorAt(.8, _alpha(cor, 4))
    glow.setColorAt(1, _alpha(cor, 0))
    p.fillRect(QRectF(153, 64, 79, 88), glow)
    # Luz volumétrica localizada e faces com contornos finos.
    faces = [([(x,y),(x+w,y+5),(x+w,y+h+5),(x,y+h-1)], 35),
             ([(x+w,y+5),(x+w+10,y-1),(x+w+10,y+h-2),(x+w,y+h+5)], 30),
             ([(x,y),(x+10,y-6),(x+w+10,y-1),(x+w,y+5)], 54)]
    for pts, alpha in faces:
        p.setBrush(_alpha(cor, alpha))
        p.setPen(QPen(_alpha(cor, 155), .4))
        p.drawPath(_caminho(pts, True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for dy in range(4, round(h), 2):
        p.setPen(QPen(_alpha(cor, 34), .23))
        p.drawPath(_caminho([(x+1,y+dy),(x+w,y+dy+5),(x+w+9,y+dy-1)]))
    base = QRadialGradient(QPointF(193, 125), 18)
    base.setColorAt(0, _alpha(cor, 51))
    base.setColorAt(.45, _alpha(cor, 18))
    base.setColorAt(1, _alpha(cor, 0))
    p.fillRect(QRectF(174, 107, 39, 38), base)
    filamento = QPainterPath(QPointF(192, 76))
    filamento.cubicTo(198, 82, 190, 87, 196, 94)
    filamento.cubicTo(199, 108, 190, 120, 194, 138)
    p.setPen(QPen(_alpha(cor, 28), 2))
    p.drawPath(filamento)
    p.setPen(QPen(_alpha(cor, 135), .45))
    p.drawPath(filamento)
    for i in range(12):
        px, py = 181+i*2.7, 151-i*1.45
        p.setPen(QPen(_alpha(cor, 150-i*8), .7))
        p.drawPoint(QPointF(px,py))
    p.setPen(QPen(_alpha(cor, 65), .3))
    p.drawLine(QPointF(149, 134), QPointF(261, 134))
    _texto(p, 219, 118, 34, 10, f'{score*100:+.1f}%' if maker is not None else '—',
           6, cor, True, True, True)
    _texto(p, 216, 130, 39, 4, 'MAKER PROXY', 3, cor, True, True)
    livro = e.snapshot.contexto_bruto
    bids, asks = getattr(livro,'bids',()), getattr(livro,'asks',())
    for x, valor in [(53, bids[0].preco if bids else None),
                     (88, asks[0].preco if asks else None)]:
        p.setPen(QPen(QColor('#404543'), .35))
        p.setBrush(QColor('#0b0e0d'))
        p.drawRoundedRect(QRectF(x, 140, 32, 8), 1, 1)
        _texto(p, x, 140, 32, 8, _preco(e, valor), 3, BRANCO, True, True)


def _niveis(p, e):
    livro = e.snapshot.contexto_bruto
    bids, asks = getattr(livro,'bids',()), getattr(livro,'asks',())
    nivel_publicado = analitica.preco_ticks_publicado
    decisao = e.snapshot.decisao
    vals = [e.vap_vah,e.vap_val,nivel_publicado(decisao.stop),
            nivel_publicado(decisao.alvo_1),asks[0].preco if asks else None,
            bids[0].preco if bids else None]
    cores = [AMARELO,VERDE,CINZA,CINZA,AMARELO,VERDE]
    if getattr(e.maker,'forca',0)<0:
        cores = [ROSA,AMARELO,CINZA,CINZA,ROSA,AMARELO]
    caixas = [(8,34),(49,36),(98,28),(132,29),(170,34),(212,33)]
    for (x,w), valor, cor in zip(caixas,vals,cores):
        g = QLinearGradient(0, 169, 0, 180)
        g.setColorAt(0, cor.darker(155))
        g.setColorAt(.3, cor.darker(195))
        g.setColorAt(1, cor.darker(235))
        p.setBrush(g)
        p.setPen(QPen(_alpha(cor, 85), .4))
        p.drawRoundedRect(QRectF(x, 169, w, 11), 2, 2)
        _texto(p, x, 169, w, 11, _preco(e,valor) if valor is not None else '/',
               6,BRANCO,True,True,True)
    _texto(p, 8, 182, 237, 5, 'VAH / VAL       ·       STOP / A1       ·       ASK / BID', 3, _alpha(CINZA,100), centro=True)


def _banner_placar(p, e, modelo):
    # Amostras do frame: y196≈83, y202≈90, y212≈89 (luminância 0..255).
    metal = QLinearGradient(0,196,0,216)
    metal.setColorAt(0,QColor('#535353'))
    metal.setColorAt(.3,QColor('#5a5a5a'))
    metal.setColorAt(1,QColor('#585858'))
    p.setBrush(metal)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(0,196,247,20))
    p.setBrush(QColor('#292929'))
    p.drawPath(_caminho([(0,194),(54,194),(61,197),(47,215),(0,215)], True))
    fonte_alerta = _fonte(8, True, True)
    fonte_alerta.setStretch(155)
    p.setFont(fonte_alerta)
    p.setPen(BRANCO)
    p.drawText(QRectF(1,198,47,12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, 'ALERTA')
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor('#b4b7b0'), .45))
    p.drawPath(_caminho([(80,189),(85,198),(75,198)],True))
    _texto(p,77,190,6,8,'!',5,BRANCO,True,True)
    fase = 'ALGORITHMIC STANDBY' if modelo.fase == 'SEM CONFLUÊNCIA' else modelo.fase
    fonte_fase = _fonte(9, True, True)
    comprimento = QFontMetricsF(fonte_fase).horizontalAdvance(fase)
    fonte_fase.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                               max(0,(171-comprimento)/max(1,len(fase)-1)))
    p.setFont(fonte_fase)
    p.setPen(QColor('#242925'))
    p.drawText(QRectF(67,201,176,12), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, fase)
    _texto(p, 91, 188, 154, 7, 'LEITURA DE FLUXO · CONSULTIVO', 4, QColor('#242424'), True, True)
    _texto(p, 21, 227, 96, 5, 'PLACAR ESTATÍSTICO', 4, QColor('#a9b6a5'), True, True, True)
    leituras = tuple((n,l) for n,l in e.leituras if analitica.leitura_disponivel(l))
    if analitica.motivo_bloqueio(e):
        leituras = ()
    compra, venda = estatistica.pesos_por_lado(leituras)
    for x, valor, cor, nome in [(7, compra, VERDE, 'COMPRA'), (62, venda, ROSA, 'VENDA')]:
        p.setBrush(QColor('#060a08'))
        p.setPen(QPen(_alpha(cor, 82), .45))
        p.drawRoundedRect(QRectF(x,235,50,18), 2,2)
        _texto(p, x, 234, 50, 5, nome, 3, cor, True, True)
        _texto(p, x, 239, 50, 13, f'{valor*100:.0f}%' if leituras else '—', 8, _alpha(cor,185), True, True)
        for i in range(3):
            p.fillRect(QRectF(x+i*16,255,14,4), _alpha(cor, 75 if valor>i/3 else 12))
    # Indicadores compactos de disponibilidade e horizonte, sem simular controles.
    p.setPen(QPen(QColor('#647269'), .5))
    p.setBrush(QColor('#151d18'))
    p.drawEllipse(QPointF(10, 260), 5, 5)
    p.setPen(QPen(_alpha(VERDE if e.leituras else CINZA, 145), .5))
    p.drawArc(QRectF(6.5,256.5,7,7), -55*16, 250*16)
    for x, w, texto in [(22,27,f'{len(e.leituras)} LEIT.'),
                        (54,26,'SESSÃO' if e.vap_timeframe_min==0 else f'{e.vap_timeframe_min} MIN'),
                        (85,28,'VAP')]:
        p.fillRect(QRectF(x,258,w,3.5), QColor('#142319'))
        _texto(p,x,258,w,3.5,texto,2.5,_alpha(VERDE,145),centro=True)
    amostras = analitica.historico_forca(e)
    historico = tuple(float(a[1]) for a in amostras)
    periodo = (amostras[-1][0]-amostras[0][0])/1e9 if len(amostras)>1 else 0
    _texto(p,122,227,122,5,f'FORÇA · {periodo:.0f}s · N={len(amostras)}',3,CINZA,centro=True)
    for i in range(23):
        v = min(1,abs(historico[i])) if i<len(historico) else 0
        x = 122+i*5.2
        p.setPen(Qt.PenStyle.NoPen)
        # A atividade real modula a intensidade da barra inteira, sem degrau horizontal.
        p.setBrush(QColor(104, 107, 100, round(90+v*145)))
        p.drawPath(_caminho([(x+2,233),(x+5.2,233),(x+3.2,257),(x,257)],True))
    if historico:
        # Terminador decorativo magenta; não codifica direção nem ordem.
        p.fillRect(QRectF(239,233,1.5,24), _alpha(ROSA,150))


def glifo_nucleo(modelo):
    """Confirmação pendente não recebe a seta de uma decisão confirmada."""
    if not modelo.saudavel:
        return 'bloqueado'
    if modelo.fase == 'CONFIRMANDO':
        return 'confirmacao'
    return {'COMPRA':'compra','VENDA':'venda'}.get(modelo.titulo,'equilibrio')


def _central(p, e, modelo):
    pontos = [(276,11),(366,11),(396,32),(396,73),(368,92),(275,92),(254,74),(254,31)]
    metal = QLinearGradient(253,10,396,91)
    metal.setColorAt(0,QColor('#080b09'))
    metal.setColorAt(.4,QColor('#010202'))
    metal.setColorAt(1,QColor('#030504'))
    p.setBrush(metal)
    p.setPen(QPen(QColor('#222620'), .45))
    p.drawPath(_caminho(pontos, True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor('#1c211b'), .35))
    p.drawPath(_caminho([(257,22),(275,9),(365,9),(388,25)]))
    p.setPen(QPen(QColor('#080e0b'),.4))
    p.drawPath(_caminho([(257,32),(277,13),(365,13),(392,33)]))
    for pts in [[(254,17),(259,22)],[(389,22),(394,17)]]:
        p.setPen(QPen(QColor('#25372f'),.45)); p.drawPath(_caminho(pts))
    momento = datetime.fromtimestamp(e.snapshot.timestamp_ns/1e9,timezone.utc).astimezone()
    _texto(p, 279, 16, 91, 5, momento.strftime('%Y-%m-%d %H:%M:%S'), 3,
           QColor('#4b504c'), centro=True)
    glifo = glifo_nucleo(modelo)
    lado = 1 if glifo=='compra' else -1 if glifo=='venda' else 0
    cor = _cor(e,lado) if lado else CINZA
    if lado:
        tri = [(323,41),(333,63),(313,63)] if lado>0 else [(313,46),(333,46),(323,69)]
        brilho = QRadialGradient(QPointF(323,55),14)
        brilho.setColorAt(0,_alpha(cor,23)); brilho.setColorAt(1,_alpha(cor,0))
        p.setBrush(brilho); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(323,55),14,14)
        grad = QLinearGradient(313,41,333,69)
        grad.setColorAt(0,cor.lighter(120)); grad.setColorAt(.5,cor)
        grad.setColorAt(1,cor.darker(240))
        p.setBrush(grad); p.setPen(QPen(cor.lighter(120),.35))
        p.drawPath(_caminho(tri,True))
    elif glifo == 'confirmacao':
        for pts in [[(323,35),(332,53),(314,53)],[(314,56),(332,56),(323,74)]]:
            relevo = QLinearGradient(314,35,332,74)
            relevo.setColorAt(0,QColor('#b7bab4')); relevo.setColorAt(1,QColor('#515550'))
            p.setBrush(relevo); p.setPen(QPen(QColor('#868b84'),.25))
            p.drawPath(_caminho(pts,True))
    else:
        p.setPen(QPen(CINZA,1.3)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(317,47,12,12),35*16,300*16)
        rotulo = modelo.mercado or 'BALANÇO DE PREÇO'
        if glifo == 'bloqueado':
            rotulo = modelo.estado_feed
        _texto(p,277,67,94,7,rotulo,4,CINZA,centro=True)
    # Identidade própria: única região deliberadamente diferente da ASG.
    arte = assistente._arte_escalada(240)
    if not arte.isNull():
        p.setOpacity(.8)
        p.drawImage(QRectF(279,151,83,82),arte)
        p.setOpacity(1)
    _texto(p,270,235,105,17,'OPERADOR B3',15,BRANCO,True,True)
    p.fillRect(QRectF(274,254,100,6), QColor('#125884'))
    _texto(p,274,254,100,6,'LEITURA INSTITUCIONAL',4,BRANCO,centro=True)


def _etiqueta(p, x, y, texto, cor, direita=False):
    w = 25
    rect = QRectF(x-w if direita else x,y-2.5,w,5)
    p.save()
    try:
        if direita:
            # O último preço da referência é uma placa escura com aro iluminado.
            g = QLinearGradient(0,rect.top(),0,rect.bottom())
            g.setColorAt(0,QColor('#151b18')); g.setColorAt(.5,QColor('#030605'))
            g.setColorAt(1,QColor('#0b100c'))
            p.setBrush(g); p.setPen(QPen(_alpha(cor,190),.42))
            p.drawRect(rect.adjusted(.2,.2,-.2,-.2))
            tinta = _misturar(cor,BRANCO,.35)
        else:
            g = QLinearGradient(0,rect.top(),0,rect.bottom())
            g.setColorAt(0,_misturar(cor,BRANCO,.28))
            g.setColorAt(.25,cor); g.setColorAt(.8,cor)
            g.setColorAt(1,cor.darker(150))
            p.fillRect(rect,g)
            p.setPen(QPen(_alpha(_misturar(cor,BRANCO,.6),140),.2))
            p.drawLine(rect.topLeft(),rect.topRight())
            tinta = PRETO
        _texto(p,rect.x(),rect.y(),w,5,texto,3.5,tinta,True,True)
    finally:
        p.restore()


def posicoes_etiquetas(ordenadas, topo=106, base=226, separacao=5.7):
    """Layout de legendas, sem mudar o preço ancorado de nenhuma linha."""
    if not ordenadas:
        return ()
    separacao = min(separacao,(base-topo)/max(1,len(ordenadas)-1))
    saida = []
    for y in ordenadas:
        saida.append(max(topo,y,saida[-1]+separacao if saida else topo))
    saida[-1] = min(base,saida[-1])
    for i in range(len(saida)-2,-1,-1):
        saida[i] = min(saida[i],saida[i+1]-separacao)
    return tuple(saida)


def legendas_em_colunas(ordenadas,topo=106,base=226):
    """Níveis próximos compartilham a mesma altura em colunas distintas.

    A referência usa plaquetas lado a lado. Só uma legenda é deslocada;
    sua linha e sua âncora continuam no preço original.
    """
    colunas = [[],[],[]]
    for indice,y in enumerate(ordenadas):
        livre = next((i for i,c in enumerate(colunas)
                      if not c or y-c[-1][1]>=5.7),None)
        if livre is None:
            livre = min(range(3),key=lambda i:colunas[i][-1][1])
        colunas[livre].append((indice,y))
    saida = [None]*len(ordenadas)
    for coluna,itens in enumerate(colunas):
        ys = posicoes_etiquetas([y for _,y in itens],topo,base)
        for (indice,_),y in zip(itens,ys):
            saida[indice] = (399+coluna*27,y)
    return tuple(saida)


def _eixo(p,e,lo,hi,yp,quantidade,escuro=False):
    p.save()
    ys = sorted((yp(lo),yp(hi)))
    p.fillRect(QRectF(617,ys[0]-3,23,ys[1]-ys[0]+6),QColor(0,5,5,90))
    p.setPen(QPen(QColor(39,66,58,80),.3))
    p.drawLine(QPointF(617,ys[0]-3),QPointF(617,ys[1]+3))
    vistos = set()
    for i in range(quantidade):
        valor = round(lo+(hi-lo)*i/(quantidade-1))
        if valor in vistos:
            continue
        vistos.add(valor)
        y = yp(valor)
        p.setPen(QPen(QColor('#090f0c') if escuro else QColor('#101813'),.23))
        p.drawLine(QPointF(400,y),QPointF(616,y))
        p.setPen(QPen(QColor('#30443d'),.25))
        p.drawLine(QPointF(616,y),QPointF(618,y))
        _texto(p,619,y-2,21,5,_preco(e,valor),3,QColor('#65736c'))
    p.restore()


def geometria_renko(e):
    """Corpos fechados reais; altura proporcional ao preço, sem série substituta."""
    tijolos = e.tijolos_renko[-48:]
    if not tijolos:
        return (), None
    precos = [v for b in tijolos for v in (b.abertura,b.fechamento)]
    if e.alvos_renko is not None:
        precos.extend(e.alvos_renko.positivos + e.alvos_renko.negativos)
    lo,hi = min(precos),max(precos)
    pad = max(2,(hi-lo)*.12)
    lo -= pad; hi += pad
    yp = lambda v: 92-(v-lo)*77/(hi-lo)
    passo = 200/48
    inicio = 601-len(tijolos)*passo
    corpos = tuple((b,QRectF(inicio+i*passo,
                            min(yp(b.abertura),yp(b.fechamento)),passo*.78,
                            abs(yp(b.abertura)-yp(b.fechamento))))
                   for i,b in enumerate(tijolos))
    return corpos,(lo,hi,yp)


def _renko(p,e):
    corpos, escala = geometria_renko(e)
    _texto(p,401,8,150,6,f'RENKO · {e.renko_tamanho_ticks} TICKS',2.5,QColor('#343e35'))
    if not corpos:
        _texto(p,415,43,186,12,'AGUARDANDO TIJOLOS RENKO',5,CINZA,centro=True)
        return
    lo,hi,yp = escala
    # Luz difusa sob os próprios fechamentos Renko, sem série de preço paralela.
    banho = QPainterPath(QPointF(corpos[0][1].left(),100))
    for b,r in corpos:
        banho.lineTo(r.left(),yp(b.fechamento))
        banho.lineTo(r.right(),yp(b.fechamento))
    banho.lineTo(corpos[-1][1].right(),100); banho.closeSubpath()
    cor_atual = _cor_grafico(e,corpos[-1][0].direcao)
    luz = QLinearGradient(0,15,0,100)
    luz.setColorAt(0,_alpha(cor_atual,9)); luz.setColorAt(.5,_alpha(cor_atual,6))
    luz.setColorAt(1,_alpha(cor_atual,0))
    p.fillPath(banho,luz)
    for b,r in corpos:
        y = yp(b.fechamento)
        local = QLinearGradient(0,y,0,y+29)
        local.setColorAt(0,_alpha(cor_atual,46))
        local.setColorAt(.35,_alpha(cor_atual,14))
        local.setColorAt(1,_alpha(cor_atual,0))
        p.fillRect(QRectF(r.left(),y,r.width()+.9,min(29,100-y)),local)
    _eixo(p,e,lo,hi,yp,16,escuro=True)
    rotulos = []
    if e.alvos_renko is not None:
        for valores,cor,sinal in [(e.alvos_renko.positivos,GRAFICO_AMBAR,'+'),
                                  (e.alvos_renko.negativos,GRAFICO_CIANO,'−')]:
            for i,valor in enumerate(valores,1):
                y = yp(valor)
                _regiao_preco(p,y,cor)
                rotulos.append((y,f'A{i}{sinal} {_preco(e,valor)}',cor))
    # Cada corpo/limite continua sendo o mesmo tijolo real. Só muda o material.
    p.save()
    p.setClipRect(QRectF(399,14,218,87),Qt.ClipOperation.IntersectClip)
    for b,rect in corpos:
        _corpo_3d(p,rect,_cor_grafico(e,b.direcao),renko=True)
    p.restore()
    rotulos.sort(key=lambda a:a[0])
    for (origem,texto,cor),y_legenda in zip(rotulos,posicoes_etiquetas(
            [r[0] for r in rotulos],17,94,4.5)):
        if abs(origem-y_legenda)>.5:
            p.setPen(QPen(_alpha(cor,120),.25))
            p.drawLine(QPointF(444,y_legenda),QPointF(448,origem))
        _texto(p,401,y_legenda-2.5,43,5,texto,3,_alpha(cor,165))
    ultimo = corpos[-1][0].fechamento
    y = yp(ultimo)
    p.setPen(QPen(_alpha(GRAFICO_AMBAR,150),.35,Qt.PenStyle.DotLine))
    p.drawLine(QPointF(602,y),QPointF(616,y))
    _etiqueta(p,639,y,_preco(e,ultimo),GRAFICO_AMBAR,True)
    _texto(p,401,96,212,5,f'{analitica.fase_renko(e)} · ALVOS RENKO PROXY',3,CINZA)


def _candles(p, e):
    todos = e.candles_m15
    fim = max(0,len(todos)-e.candles_offset)
    qtd = e.candles_velas_visiveis or 36
    velas = todos[max(0,fim-qtd):fim]
    if not velas:
        _texto(p,420,156,180,12,'AGUARDANDO NEGÓCIOS',5,CINZA,centro=True)
        return
    lo, hi = min(c.low for c in velas), max(c.high for c in velas)
    margem = max(2,(hi-lo)*.15)
    centro = (lo+hi)/2
    faixa = (hi-lo+2*margem)/max(.2,e.candles_zoom_preco)
    lo, hi = centro-faixa/2, centro+faixa/2
    yp = lambda v: 225-(v-lo)*115/(hi-lo)
    _eixo(p,e,lo,hi,yp,22)
    passo = 156/max(24,qtd)
    inicio = 558-len(velas)*passo
    p.save(); p.setClipRect(QRectF(399,103,218,128),Qt.ClipOperation.IntersectClip)
    ultimo = velas[-1].close
    publicados = analitica.niveis_do_snapshot(e)
    cores = {'STOP':ROSA,'ALVO':GRAFICO_AMBAR,'SUPORTE':GRAFICO_VERDE_NIVEL,
             'RESISTÊNCIA':ROSA,'OBSERVAÇÃO':CINZA,'POC':GRAFICO_AMBAR,
             'VAL':GRAFICO_CIANO,'VAH':GRAFICO_AMBAR}
    niveis = [(n.preco,cores[n.classe]) for n in publicados]
    # Limites de zona são os do motor; nunca uma largura decorativa arbitrária.
    for n in publicados:
        if n.inferior is None or n.superior is None:
            continue
        t,b = sorted((yp(n.inferior),yp(n.superior)))
        cor = cores[n.classe]
        p.fillRect(QRectF(400,t,216,b-t),_alpha(cor,13 if n.confirmado else 6))
        p.setPen(QPen(_alpha(cor,55),.25,Qt.PenStyle.DotLine))
        p.drawLine(QPointF(400,t),QPointF(616,t))
        p.drawLine(QPointF(400,b),QPointF(616,b))
    etiquetas = []
    vistos = set()
    for v,cor in niveis:
        if v in vistos:
            continue
        vistos.add(v)
        y = yp(v)
        if 107<=y<=225:
            _regiao_preco(p,y,cor,forte=True)
            etiquetas.append((y,v,cor))
    # Regiões ficam atrás do preço: não cortam o reflexo dos corpos.
    for i,c in enumerate(velas):
        x = inicio+i*passo
        cor = _cor_grafico(e,c.close-c.open)
        _pavio_3d(p,x,yp(c.high),yp(c.low),cor)
        topo = min(yp(c.open),yp(c.close))
        h = abs(yp(c.close)-yp(c.open))
        w = max(.75,passo*.60)
        if h<.35:
            p.setPen(QPen(_misturar(cor,BRANCO,.3),.35))
            p.drawLine(QPointF(x-w/2,yp(c.close)),QPointF(x+w/2,yp(c.close)))
        else:
            _corpo_3d(p,QRectF(x-w/2,topo,w,h),cor)
    # Se os níveis convergem, desloca só a legenda, nunca a linha de preço.
    etiquetas.sort(key=lambda a:a[0])
    posicoes = legendas_em_colunas([a[0] for a in etiquetas])
    for (y,v,cor),(x_legenda,legenda) in zip(etiquetas,posicoes):
        if legenda!=y:
            p.setPen(QPen(_alpha(cor,180),.35))
            p.drawLine(QPointF(x_legenda+27,y),QPointF(x_legenda+25,legenda))
        _etiqueta(p,x_legenda,legenda,_preco(e,v),cor)
    y = yp(ultimo)
    p.setPen(QPen(CINZA,.4,Qt.PenStyle.DotLine)); p.drawLine(QPointF(400,y),QPointF(616,y))
    p.restore()
    if 103<=y<=230:
        _etiqueta(p,639,y,_preco(e,ultimo),CINZA,True)
    _texto(p,564,228,50,5,f'{e.candles_timeframe_min}M · {formato.formatar_hora_ns(velas[-1].timestamp_ns)[:5]}',3,CINZA)
    _texto(p,401,228,158,5,'NÍVEIS DO SNAPSHOT · F6 ORIGEM' if publicados else 'SEM NÍVEIS VÁLIDOS',2.5,CINZA)
    if e.candles_cursor is not None:
        v, escala = viewport(QRect(0,0,e.largura,e.altura))
        cx = (e.candles_cursor[0]-v.x())/escala
        cy = (e.candles_cursor[1]-v.y())/escala
        if 399<=cx<=616 and 103<=cy<=225:
            p.setPen(QPen(_alpha(BRANCO,150),.4,Qt.PenStyle.DotLine))
            p.drawLine(QPointF(cx,103),QPointF(cx,225))
            p.drawLine(QPointF(399,cy),QPointF(616,cy))
            tick = round(lo+(225-cy)*(hi-lo)/115)
            _etiqueta(p,639,cy,_preco(e,tick),BRANCO,True)
            indice = max(0,min(len(velas)-1,round((cx-inicio)/passo)))
            c = velas[indice]
            _texto(p,401,103,212,6,
                   f'{formato.formatar_hora_ns(c.timestamp_ns)[:5]}  '
                   f'O {_preco(e,c.open)}  H {_preco(e,c.high)}  '
                   f'L {_preco(e,c.low)}  C {_preco(e,c.close)}',3,BRANCO)
            nivel = min(publicados,key=lambda n:abs(yp(n.preco)-cy),default=None)
            if nivel is not None and abs(yp(nivel.preco)-cy)<=3:
                detalhe = f'{nivel.rotulo} · {nivel.origem}'
                if nivel.toques is not None:
                    detalhe += f' · {nivel.toques} TESTES · {"CONF." if nivel.confirmado else "OBS."}'
                _texto(p,401,109,212,5,detalhe,3,cores[nivel.classe])


@lru_cache(maxsize=2)
def _animal_cinza(touro):
    imagem = pressao._sprite_animal(touro).toImage()
    for y in range(imagem.height()):
        for x in range(imagem.width()):
            cor = imagem.pixelColor(x,y)
            cinza = round(.299*cor.red()+.587*cor.green()+.114*cor.blue())
            imagem.setPixelColor(x,y,QColor(cinza,cinza,cinza,cor.alpha()))
    return imagem


@lru_cache(maxsize=1)
def _relevo_pressao():
    imagem = QImage(str(Path(__file__).resolve().parents[2]/'assets'/'pressao_relevo_v2.png'))
    return imagem.scaledToWidth(384,Qt.TransformationMode.SmoothTransformation)


def _pressao(p,e,simbolo):
    leitura = analitica.pressao_do_snapshot(e)
    compra,venda = leitura.compra,leitura.venda
    def percentual(v):
        return '—' if v is None else (f'{v:g}%'.replace('.',','))
    _texto(p,394,241,26,11,percentual(compra),7,VERDE if leitura.disponivel else CINZA,True)
    _texto(p,484,241,29,11,percentual(venda),7,ROSA if leitura.disponivel else CINZA,True)
    imagem = _relevo_pressao()
    if not imagem.isNull():
        p.setOpacity(.53)
        p.drawImage(QRectF(421,232,62,30),imagem)
        p.setOpacity(1)
    else:
        for r,touro in [(QRect(422,232,34,29),True),(QRect(451,232,33,29),False)]:
            p.setOpacity(.24)
            p.drawImage(QRectF(r),_animal_cinza(touro))
        p.setOpacity(1)
    p.setPen(QPen(QColor('#1a4943'),.6)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(535,252),6,6)
    p.drawEllipse(QPointF(535,252),7.2,7.2)
    _texto(p,528,246,14,12,'AI',4,AZUL,centro=True)
    _texto(p,521,260,29,4,'LEITURA DE FLUXO',2,CINZA,centro=True)
    p.setPen(QPen(QColor('#19221b'),.25)); p.drawLine(QPointF(397,257),QPointF(509,257))
    if leitura.disponivel:
        corte = 397+112*compra/100
        p.fillRect(QRectF(397,256.5,corte-397,.7),_alpha(VERDE,135))
        p.fillRect(QRectF(corte,256.5,509-corte,.7),_alpha(ROSA,135))
        p.fillRect(QRectF(corte-.6,255,1.2,5),BRANCO)
        angulo = math.radians(-90+45*leitura.score)
        p.setPen(QPen(BRANCO,.4))
        p.drawLine(QPointF(535,252),QPointF(535+math.cos(angulo)*4,252+math.sin(angulo)*4))
    _texto(p,394,263,118,5,leitura.origem if leitura.disponivel else 'DOMINÂNCIA · N/D · F6 MOTIVO',2.5,CINZA)
    _texto(p,552,244,83,6,f'{simbolo}    MACRO · MICRO',2.5,CINZA)
    fonte = str(e.snapshot.dados.fonte)
    _texto(p,551,251,87,6,f'{fonte} · {e.snapshot.dados.estado.value}',3,AZUL)
    _texto(p,551,260,88,5,'CONSULTIVO · F6 DETALHES',3,CINZA)


def desenhar(p, quadro, estado, aviso='', simbolo=''):
    v, escala = viewport(quadro)
    p.save()
    try:
        p.fillRect(quadro,PRETO)
        p.translate(v.x(),v.y()); p.scale(escala,escala)
        p.setClipRect(QRectF(0,0,640,270),Qt.ClipOperation.IntersectClip)
        p.setRenderHint(p.RenderHint.Antialiasing,True)
        if estado.snapshot is None:
            _fundo(p)
            _texto(p,200,118,240,24,'SEM DADOS',12,CINZA,centro=True)
            return
        modelo = assistente.compor(estado)
        _fundo(p); _vap(p,estado); _contexto(p,estado); _niveis(p,estado)
        _banner_placar(p,estado,modelo); _central(p,estado,modelo)
        _renko(p,estado); _candles(p,estado); _pressao(p,estado,simbolo)
        if 'CONTROLADO' in aviso.upper():
            _texto(p,401,1,208,6,'CENÁRIO CONTROLADO · DADOS SINTÉTICOS',4,AMARELO)
        elif 'SIM' in str(estado.snapshot.dados.fonte).upper():
            _texto(p,401,1,208,6,'SIMULADOR · DADOS SINTÉTICOS',4,AMARELO)
        if 'CALIBRADO' in aviso:
            _texto(p,401,8,208,6,'MOTOR CALIBRADO · F6 DETALHES',4,AMARELO)
    finally:
        p.restore()
