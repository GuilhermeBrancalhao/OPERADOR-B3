"""Regressões do novo compositor: ausência de dados, repintura e gestos."""
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtTest import QTest

from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import referencia
from fluxopro.ui.paineis.nexo import assistente
from fluxopro.analytics.renko import TijoloRenko, AlvosRenko
from fluxopro.core.eventos import Candle


@pytest.fixture
def painel(qapp, monkeypatch):
    monkeypatch.setenv('FLUXOPRO_ANALISE_IA', '0')
    p = PainelNexoMercadoASG()
    p.resize(1480, 625)
    for i in range(45):
        p._candles_m15.registrar(i * 300_000_000_000, 10000+i, 4)
        p._candles_m15.registrar(i * 300_000_000_000+1, 10002+i, 3)
    yield p
    p.parar_relogio()
    p.close()
    p.deleteLater()


def render(estado, clip=None):
    imagem = QImage(1480, 625, QImage.Format.Format_ARGB32)
    imagem.fill(QColor('#010203'))
    p = QPainter(imagem)
    try:
        if clip is not None:
            p.setClipRect(clip)
        referencia.desenhar(p, imagem.rect(), estado)
    finally:
        p.end()
    return imagem


def test_dados_ausentes_nao_viram_equilibrio_ou_zero(painel, monkeypatch):
    estado = painel._estado_nexo()
    estado = replace(estado, snapshot=replace(estado.snapshot, contexto_bruto=None),
                     maker=None, leituras=(), candles_m15=(), serie=())
    textos = []
    original = referencia._texto
    def capturar(*args, **kwargs):
        textos.append(str(args[5]))
        return original(*args, **kwargs)
    monkeypatch.setattr(referencia, '_texto', capturar)
    render(estado)
    assert '50%' not in textos
    assert '+0.0%' not in textos
    assert '—' in textos
    render(replace(estado, snapshot=None))
    assert 'SEM DADOS' in textos


def test_repintura_parcial_preserva_os_pixels_do_quadro(painel):
    estado = painel._estado_nexo()
    inteiro = render(estado)
    for recorte in [QRect(265, 73, 310, 232), QRect(920, 300, 400, 210)]:
        parcial = render(estado, recorte)
        interior = recorte.adjusted(2, 2, -2, -2)
        a,b = parcial.copy(interior),inteiro.copy(interior)
        if a!=b:
            diferencas = [(x+interior.x(),y+interior.y(),hex(a.pixel(x,y)),hex(b.pixel(x,y)))
                          for y in range(a.height()) for x in range(a.width())
                          if a.pixel(x,y)!=b.pixel(x,y)]
            # Qt/DirectWrite pode quantizar a borda de um glifo recortado em
            # 1 LSB por canal, dependendo do cache de fontes. Não tolerar
            # deslocamento, camada faltante ou diferença de opacidade.
            erro = max(abs(((int(aa,16)>>s)&255)-((int(bb,16)>>s)&255))
                       for _,_,aa,bb in diferencas for s in (0,8,16,24))
            assert erro<=1, f'{len(diferencas)} pixels divergentes: {diferencas[:12]}'


def test_arrasto_muda_janela_sem_alterar_candles(painel, qapp):
    painel.show()
    qapp.processEvents()
    antes = painel._candles_m15.candles_fechados
    caixa = referencia.retangulos(painel.rect())['candles']
    inicio = caixa.center()
    QTest.mousePress(painel, Qt.MouseButton.LeftButton, pos=inicio)
    QTest.mouseMove(painel, inicio + QPoint(90, 0))
    QTest.mouseRelease(painel, Qt.MouseButton.LeftButton, pos=inicio + QPoint(90, 0))
    assert painel._candles_offset > 0
    assert painel._candles_m15.candles_fechados == antes


def test_zoom_timeframe_e_retorno_ao_automatico(painel, qapp):
    painel.show()
    qapp.processEvents()
    caixa = referencia.retangulos(painel.rect())['candles']
    pos = QPointF(caixa.right()-10, caixa.center().y())
    evento = QWheelEvent(pos, pos, QPoint(), QPoint(0, 120),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                         Qt.ScrollPhase.ScrollUpdate, False)
    qapp.sendEvent(painel, evento)
    assert painel._candles_zoom_preco > 1
    QTest.mouseClick(painel, Qt.MouseButton.LeftButton,
                     pos=QPoint(caixa.right()-80, caixa.bottom()-2))
    assert painel._timeframe_candles_min == 15
    QTest.mouseDClick(painel, Qt.MouseButton.LeftButton, pos=caixa.center())
    assert painel._candles_zoom_preco == 1.0
    assert painel._candles_offset == 0
    assert painel._candles_velas_visiveis is None


def test_renko_nao_substitui_tijolos_por_serie_de_precos(painel, monkeypatch):
    estado = replace(painel._estado_nexo(), tijolos_renko=(),
                     serie=((1, 10000, .5, 1), (2, 10020, -.5, 1)))
    assert referencia.geometria_renko(estado) == ((), None)
    textos = []
    monkeypatch.setattr(referencia, '_texto', lambda *a, **k: textos.append(str(a[5])))
    render(estado)
    assert 'AGUARDANDO TIJOLOS RENKO' in textos


def test_corpos_renko_preservam_abertura_fechamento_e_alvos(painel, monkeypatch):
    tijolos = (TijoloRenko(1,10000,10008,1), TijoloRenko(2,10008,10000,-1),
               TijoloRenko(3,10000,10016,1))
    alvos = AlvosRenko((10020,10030,10040),(9990,9980,9970))
    estado = replace(painel._estado_nexo(), tijolos_renko=tijolos, alvos_renko=alvos)
    corpos, (_,_,yp) = referencia.geometria_renko(estado)
    assert tuple(b for b,r in corpos) == tijolos
    assert corpos[0][1].height() == pytest.approx(abs(yp(10008)-yp(10000)))
    assert corpos[2][1].height() == pytest.approx(2*corpos[0][1].height())
    assert corpos[0][1].top() == corpos[1][1].top()
    assert corpos[1][1].left() > corpos[0][1].right()
    textos = []
    monkeypatch.setattr(referencia, '_texto', lambda *a, **k: textos.append(str(a[5])))
    render(estado)
    for numero in (1,2,3):
        assert any(t.startswith(f'A{numero}+') for t in textos)
        assert any(t.startswith(f'A{numero}−') for t in textos)


@pytest.mark.parametrize('valores',[(224,224,225,225),(104,104,104),(125,150,180),()])
def test_legendas_proximas_nao_colidem_nem_saem_do_grafico(valores):
    posicoes = referencia.posicoes_etiquetas(valores)
    assert len(posicoes)==len(valores)
    assert all(106<=y<=226 for y in posicoes)
    assert all(b-a>=5.69 for a,b in zip(posicoes,posicoes[1:]))


@pytest.mark.parametrize('saudavel,fase,titulo,esperado',[
    (True,'CONFIRMANDO','COMPRA','confirmacao'),
    (True,'FILTRO ATIVO','COMPRA','compra'),
    (True,'FILTRO ATIVO','VENDA','venda'),
    (True,'SEM CONFLUÊNCIA','AGUARDAR','equilibrio'),
    (False,'FILTRO ATIVO','COMPRA','bloqueado')])
def test_glifo_nao_simula_confirmacao_pendente_ou_feed_bloqueado(
        painel,saudavel,fase,titulo,esperado):
    modelo = replace(assistente.compor(painel._estado_nexo()),
                     saudavel=saudavel,fase=fase,titulo=titulo)
    assert referencia.glifo_nucleo(modelo)==esperado


@pytest.mark.parametrize('tamanho',[(640,270),(1480,625),(1920,1080),(980,720)])
def test_escala_uniforme_preserva_geometria_e_letterbox(tamanho):
    quadro = QRect(0,0,*tamanho)
    v,escala = referencia.viewport(quadro)
    assert v.width()/640 == pytest.approx(v.height()/270)
    assert v.width()/640 == pytest.approx(escala)
    assert v.left()>=0 and v.top()>=0
    assert v.right()<=quadro.width()+.001
    assert v.bottom()<=quadro.height()+.001
    assert v.center().x()==pytest.approx(quadro.width()/2)
    assert v.center().y()==pytest.approx(quadro.height()/2)


def test_eixo_imprime_precos_na_posicao_exata_da_transformacao(painel,monkeypatch):
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    capturados = []
    monkeypatch.setattr(referencia,'_texto',lambda *a,**k: capturados.append(a))
    monkeypatch.setattr(referencia,'_preco',lambda e,v:str(v))
    try:
        referencia._eixo(p,painel._estado_nexo(),10000,10100,lambda v:225-(v-10000),6)
    finally:
        p.end()
    for a in capturados:
        assert a[2]+2==pytest.approx(225-(int(a[5])-10000))


def test_tracos_internos_do_prisma_nao_herdam_preenchimento_das_faces(painel):
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    abertos = []
    class Espiao:
        def __getattr__(self,nome):
            return getattr(p,nome)
        def drawPath(self,caminho):
            inicio,fim = caminho.elementAt(0),caminho.elementAt(caminho.elementCount()-1)
            if inicio.x!=fim.x or inicio.y!=fim.y:
                abertos.append(p.brush().style())
            p.drawPath(caminho)
    try:
        referencia._contexto(Espiao(),painel._estado_nexo())
    finally:
        p.end()
    assert abertos
    assert set(abertos)=={Qt.BrushStyle.NoBrush}


def test_relevo_estatico_e_transparente_e_cacheado(qapp):
    imagem = referencia._relevo_pressao()
    assert not imagem.isNull()
    assert imagem.hasAlphaChannel()
    assert imagem.pixelColor(0,0).alpha()==0
    assert referencia._relevo_pressao() is imagem


@pytest.mark.parametrize('cor',[referencia.GRAFICO_ALTA,referencia.GRAFICO_BAIXA])
def test_material_3d_tem_reflexo_fino_e_lateral_escura(qapp,cor):
    imagem = QImage(180,240,QImage.Format.Format_ARGB32)
    imagem.fill(QColor('#010203'))
    p = QPainter(imagem)
    rect = QRectF(10,10,4,20)
    antes = QRectF(rect)
    try:
        p.scale(6,6)
        referencia._corpo_3d(p,rect,cor,renko=True)
    finally:
        p.end()
    luminancia = lambda x: imagem.pixelColor(round(x*6),20*6).lightness()
    assert luminancia(11.2)>luminancia(10.1)+25
    assert luminancia(11.2)>luminancia(13.8)+25
    assert rect==antes  # bevel não modifica o retângulo de preço


@pytest.mark.parametrize('ys',[(110,110.4,111,111.3,112,112.4),(224,224.2,224.5,225,225.4,225.8),()])
def test_plaquetas_em_colunas_nao_colidem_ou_vazam(ys):
    posicoes = referencia.legendas_em_colunas(ys)
    assert len(posicoes)==len(ys)
    assert all(399<=x<=453 and 106<=y<=226 for x,y in posicoes)
    for i,(x,y) in enumerate(posicoes):
        for xx,yy in posicoes[i+1:]:
            assert abs(x-xx)>=26.9 or abs(y-yy)>=5.69


def test_relevo_preserva_abertura_fechamento_e_pavios(painel,monkeypatch):
    velas = (Candle(timestamp_ns=1,open=10000,high=10024,low=9994,
                    close=10010,volume=10,delta=2),
             Candle(timestamp_ns=2,open=10010,high=10021,low=9997,
                    close=10000,volume=20,delta=-3))
    e = replace(painel._estado_nexo(),candles_m15=velas,candles_offset=0,
                candles_zoom_preco=1.,candles_cursor=None)
    corpos,pavios = [],[]
    monkeypatch.setattr(referencia,'_corpo_3d',lambda p,r,*a,**k:corpos.append(QRectF(r)))
    monkeypatch.setattr(referencia,'_pavio_3d',lambda p,x,h,l,c:pavios.append((x,h,l)))
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    try:
        referencia._candles(p,e)
    finally:
        p.end()
    assert len(corpos)==len(pavios)==2
    # Mesmo range de preço das velas, com a margem original de 15%.
    lo,hi = 9994,10024
    pad = (hi-lo)*.15
    yp = lambda v:225-(v-(lo-pad))*115/(hi-lo+2*pad)
    for corpo,pavio,c in zip(corpos,pavios,velas):
        assert corpo.top()==pytest.approx(min(yp(c.open),yp(c.close)))
        assert corpo.height()==pytest.approx(abs(yp(c.open)-yp(c.close)))
        assert pavio[1]==pytest.approx(yp(c.high))
        assert pavio[2]==pytest.approx(yp(c.low))
    assert e.candles_m15==velas


def test_doji_permanece_traco_sem_ganhar_corpo_artificial(painel,monkeypatch):
    c = Candle(timestamp_ns=1,open=10000,high=10010,low=9990,
               close=10000,volume=10,delta=0)
    e = replace(painel._estado_nexo(),candles_m15=(c,),candles_offset=0,candles_cursor=None)
    corpos = []
    monkeypatch.setattr(referencia,'_corpo_3d',lambda *a,**k:corpos.append(a))
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    try:
        referencia._candles(p,e)
    finally:
        p.end()
    assert corpos==[]


@pytest.mark.parametrize('funcao,args',[
    (referencia._corpo_3d,(QRectF(5,5,4,12),referencia.GRAFICO_ALTA)),
    (referencia._pavio_3d,(7,4,20,referencia.GRAFICO_BAIXA)),
    (referencia._regiao_preco,(12,referencia.GRAFICO_AMBAR)),
    (referencia._etiqueta,(50,12,'5.024,0',referencia.GRAFICO_AMBAR,True))])
def test_material_nao_vaza_estado_do_qpainter(qapp,funcao,args):
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    try:
        p.setOpacity(.73)
        p.setPen(QColor('#123456'))
        p.setBrush(QColor('#654321'))
        p.setClipRect(QRect(0,0,200,200))
        antes = (p.pen(),p.brush(),p.opacity(),p.clipRegion(),p.transform(),p.font())
        funcao(p,*args)
        assert (p.pen(),p.brush(),p.opacity(),p.clipRegion(),p.transform(),p.font())==antes
    finally:
        p.end()
