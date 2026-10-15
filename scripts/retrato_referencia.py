"""Print reproduzível: eventos sintéticos atravessam os agregadores reais."""
import argparse
import os
import json
import hashlib
from dataclasses import asdict,replace
from statistics import median
from time import perf_counter
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['FLUXOPRO_ANALISE_IA'] = '0'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from fluxopro.ui.paineis.asg import EstadoASG
from fluxopro.ui.paineis.nexo import referencia as compositor
from fluxopro.ui.paineis.nexo import analitica,assistente
from scripts.painel import montar_cenario_controlado_asg
from scripts.auditar_nexo_ai import enriquecer_historia, parar_timers, fechar_cenario


def detalhes_graficos(estado,destino):
    """Mesmo compositor vetorial em 4×; não é imagem criada por IA."""
    imagem = QImage(2560,1080,QImage.Format.Format_ARGB32)
    imagem.fill(QColor('#010203'))
    p = QPainter(imagem)
    try:
        estado = replace(estado,largura=2560,altura=1080,candles_cursor=None)
        compositor.desenhar(p,imagem.rect(),estado,'CONTROLADO')
    finally:
        p.end()
    recorte = imagem.copy(QRect(399*4,0,241*4,232*4))
    recorte.save(str(destino.with_name(destino.stem+'-detalhe.png')))
    # Mesmo estado: somente o zoom de preço, controlável na UI, muda.
    amostras = QImage(2560,1080,QImage.Format.Format_ARGB32)
    amostras.fill(QColor('#010203'))
    p = QPainter(amostras)
    try:
        compositor.desenhar(p,amostras.rect(),replace(estado,candles_zoom_preco=3.0),
                           'CONTROLADO')
    finally:
        p.end()
    amostras.copy(QRect(399*4,102*4,241*4,130*4)).save(
        str(destino.with_name(destino.stem+'-zoom.png')))


def benchmark_desenho(painel,repeticoes=12):
    imagem = QImage(painel.size(),QImage.Format.Format_ARGB32)
    estado = replace(painel._estado_nexo(),candles_cursor=None)
    tempos = []
    for _ in range(repeticoes):
        p = QPainter(imagem)
        inicio = perf_counter()
        try:
            compositor.desenhar(p,imagem.rect(),estado,'CONTROLADO')
        finally:
            p.end()
        tempos.append((perf_counter()-inicio)*1000)
    # Isola o custo dos gráficos para não atribuir todo o HUD ao material 3D.
    graficos = []
    v,escala = compositor.viewport(imagem.rect())
    for _ in range(6):
        p = QPainter(imagem)
        inicio = perf_counter()
        try:
            p.translate(v.x(),v.y()); p.scale(escala,escala)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            compositor._renko(p,estado); compositor._candles(p,estado)
        finally:
            p.end()
        graficos.append((perf_counter()-inicio)*1000)
    return {'repeticoes':repeticoes,'mediana_ms':round(median(tempos),2),
            'max_ms':round(max(tempos),2),'graficos_mediana_ms':round(median(graficos),2),
            'escopo':'pintura Qt; não inclui feed/bus/tick'}


def comparacao(imagem, destino, referencia):
    """A/B com identidade ocultada; não usa similaridade de preços distintos."""
    fonte = QImage(str(referencia))
    if fonte.isNull():
        raise ValueError(f'Referência inválida: {referencia}')
    v,_ = compositor.viewport(imagem.rect())
    gerada = imagem.copy(v.toAlignedRect()).scaled(640,270,Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    pares = (gerada,fonte)
    canvas = QImage(1280,270,QImage.Format.Format_ARGB32)
    canvas.fill(QColor('#010203'))
    p = QPainter(canvas)
    try:
        for i,quadro in enumerate(pares):
            p.drawImage(i*640,0,quadro)
            # Mesma máscara nos dois: marca/avatar são excluídos, não a moldura.
            p.fillRect(QRect(i*640+270,118,120,152),QColor('#010203'))
    finally:
        p.end()
    canvas.save(str(destino))


def antes_depois_graficos(antes,depois,destino):
    imagens = [QImage(str(antes)),QImage(str(depois))]
    if any(i.isNull() for i in imagens):
        raise ValueError('Print anterior/atual inválido para comparação')
    recortes = []
    for imagem in imagens:
        v,s = compositor.viewport(imagem.rect())
        rect = QRect(round(v.x()+399*s),round(v.y()+14*s),round(241*s),round(218*s))
        recortes.append(imagem.copy(rect))
    w,h = recortes[1].width(),recortes[1].height()
    canvas = QImage(w*2+16,h+32,QImage.Format.Format_ARGB32)
    canvas.fill(QColor('#010203'))
    p = QPainter(canvas)
    try:
        for i,(nome,imagem) in enumerate(zip(('ANTES','AGORA'),recortes)):
            x = i*(w+16)
            compositor._texto(p,x,0,w,28,nome,12,QColor('#d9e3df'))
            p.drawImage(QRect(x,32,w,h),imagem)
    finally:
        p.end()
    canvas.save(str(destino))


def salvar_evidencias(janela, destino, referencia,detalhes=False):
    imagem = janela.grab().toImage()
    if not imagem.save(str(destino)):
        raise RuntimeError('Não foi possível salvar o print')
    e = janela.asg.nexo._estado_nexo()
    comparacao(janela.asg.nexo.grab().toImage(),
               destino.with_name(destino.stem+'-ab.png'),referencia)
    if detalhes:
        detalhes_graficos(e,destino)
    destino.with_suffix('.txt').write_text(assistente.texto_auditoria(e),encoding='utf-8')
    dados = {
        'origem':'eventos sintéticos pelo Barramento/Sessao/Ponte reais',
        'referencia':str(referencia.resolve()),
        'referencia_sha256':hashlib.sha256(referencia.read_bytes()).hexdigest(),
        'resolucao':[imagem.width(),imagem.height()],
        'renko':len(e.tijolos_renko),'candles':len(e.candles_m15),
        'vap':len(e.vap_niveis),'estado':e.snapshot.dados.estado.value,
        'fonte':str(e.snapshot.dados.fonte),
        'analitica':{'pressao':asdict(analitica.pressao_do_snapshot(e)),
                     'fase_renko':analitica.fase_renko(e),
                     'niveis':[asdict(n) for n in analitica.niveis_do_snapshot(e)],
                     'base_m5':len(e.candles_analiticos or ()),
                     'timeframe_exibido':e.candles_timeframe_min},
        'desempenho_pintura':benchmark_desenho(janela.asg.nexo),
        'detalhe_graficos':'vetorial 4×, mesmo EstadoNexo' if detalhes else None,
        'ab':{'esquerda':'implementação','direita':'referência'},
        'exclusoes':['identidade própria','números e série distintos',
                     'Renko superior solicitado, diferente da linha nos frames'],
        'limites':'Frames 640x270 comprimidos; nenhum executável ou recurso ASG original.'}
    destino.with_suffix('.json').write_text(json.dumps(dados,indent=2,ensure_ascii=False),encoding='utf-8')
    return e


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--largura',type=int,default=1480)
    parser.add_argument('--altura',type=int,default=625)
    parser.add_argument('--estado',choices=[e.name for e in EstadoASG],default='AO_VIVO')
    parser.add_argument('--detalhes-graficos',action='store_true')
    parser.add_argument('--comparar-anterior',type=Path)
    parser.add_argument('--referencia',type=Path,default=Path(__file__).resolve().parents[1]/
                        '.gauntlet/2026-08-25-asg-real-b/bar/frame_038.jpg')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    janela, sessao, _ = montar_cenario_controlado_asg(
        EstadoASG[args.estado], largura=args.largura, altura=args.altura)
    try:
        parar_timers(janela)
        enriquecer_historia(janela, sessao,estado=EstadoASG[args.estado])
        app.processEvents()
        painel = janela.asg.nexo
        painel.marcar_tudo_sujo()
        painel._quadro()
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        e = salvar_evidencias(janela,args.saida,args.referencia,args.detalhes_graficos)
        if args.comparar_anterior is not None:
            antes_depois_graficos(args.comparar_anterior,args.saida,
                                 args.saida.with_name(args.saida.stem+'-antes-depois.png'))
        print(f'Print: {args.saida.resolve()}')
        print(f'Renko: {len(e.tijolos_renko)} tijolos reais; candles: '
              f'{len(e.candles_m15)}; níveis VAP: {len(e.vap_niveis)}')
    finally:
        fechar_cenario(janela, sessao)


if __name__ == '__main__':
    main()
