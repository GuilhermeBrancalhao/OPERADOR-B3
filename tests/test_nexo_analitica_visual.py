"""Analítica/visual: fixtures sintéticas tipadas, sem pregão ou corretora."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QPainter

from fluxopro.analytics import dominancia as dom, suporte_resistencia as sr
from fluxopro.analytics.renko import FaseRenko
from fluxopro.asg.modelos import ComponenteMaker,MakerComponentScore
from fluxopro.core.eventos import AgressorSide,Candle,WDO_GRID
from fluxopro.ui import tokens
from fluxopro.ui.paineis import asg
from fluxopro.ui.paineis.nexo import EstadoNexo,analitica,referencia,dominancia,suporte_resistencia

S = 1_000_000_000
TS = 10_000*S


def workspace(ts=TS,estado=asg.EstadoASG.AO_VIVO,fonte='SIMULATOR',**decisao):
    return asg.WorkspaceASGSnapshot(ts,asg.DadosASGSnapshot(ts,estado,fonte),
        asg.ProcessamentoASGSnapshot(ts,estado),asg.MatrizASGSnapshot(ts,estado),
        asg.DecisaoASGSnapshot(ts,estado,**decisao),asg.TrilhaEvidenciasASGSnapshot(ts,estado),
        contexto_bruto=asg.ContextoBrutoASGSnapshot(ts,estado,
            bids=(asg.NivelBrutoASG(9999,300,3),asg.NivelBrutoASG(9998,100,2)),
            asks=(asg.NivelBrutoASG(10001,100,1),asg.NivelBrutoASG(10002,100,1)),ultimo_preco=10000))


def linha(forca=.6):
    return asg.LinhaMatrizASG('MAKERPROXY',asg.DirecaoASG.COMPRA,'+60%',forca,
                            asg.ConfiancaASG.ALTA,asg.ProcedenciaASG.DERIVADO)


def candles(n=15,sinal=1):
    return tuple(Candle(timestamp_ns=i*300*S,open=10000+sinal*i,
                        close=10000+sinal*i+1,high=10004+sinal*i,low=9996+sinal*i,
                        volume=20,delta=sinal*6) for i in range(n))


def estado(**kwargs):
    base = EstadoNexo(workspace(),(),WDO_GRID,tokens.PALETA_COR,linha(),(),1480,625,
                      candles_m15=candles(),candles_analiticos=candles())
    return replace(base,**kwargs)


def dominancia_valida(e):
    return dom.MotorDominancia('fixture').processar(event_id='1',sequencia=1,
        timestamp_ns=e.snapshot.timestamp_ns,instrumento='WDO',modo='LIVE',idade_ms=0,
        **dominancia.construir_entrada_dominancia(e))


def zona(status=sr.EstadoZona.ATIVA,lado=sr.LadoZona.SUPORTE):
    return sr.Zona('suporte-10000',lado,10000,9996,10004,.8,.9,3,('vap-val',),status)


def snapshot_sr(e,zonas):
    return sr.SuporteResistenciaSnapshot(1,'fixture','1',1,e.snapshot.timestamp_ns,'WDO',.5,
        10000,None,None,sr.ContraGiro(None,None,False),zonas,None,sr.AlertaSR.NENHUM,
        sr.Saude(sr.EstadoFeed.LIVE,0,None,None,None))


def test_pressao_consumida_e_exatamente_a_publicada_no_motor():
    e = estado()
    d = dominancia_valida(e)
    p = analitica.pressao_do_snapshot(replace(e,dominancia_snapshot=d))
    assert p.disponivel and p.origem=='DOMINÂNCIA'
    assert (p.compra,p.venda,p.score)==(d.buy_percent,d.sell_percent,d.composite)
    assert p.compra+p.venda==100
    assert d.micro.janela_ms==600_000 and d.macro.janela_ms==2_400_000


@pytest.mark.parametrize('saude',[sr.EstadoFeed.STALE,sr.EstadoFeed.GAP,
                                 sr.EstadoFeed.RECOVERING,sr.EstadoFeed.UNAVAILABLE])
def test_motor_indisponivel_nao_vira_proxy_silencioso(saude):
    e = estado()
    d = replace(dominancia_valida(e),composite=None,buy_percent=None,sell_percent=None,
                saude=dom.Saude(saude,2000,'fixture-bloqueada'))
    p = analitica.pressao_do_snapshot(replace(e,dominancia_snapshot=d))
    assert not p.disponivel and p.compra is None and p.venda is None
    assert p.origem=='DOMINÂNCIA'


@pytest.mark.parametrize('campo,valor',[
    ('composite',float('nan')),('composite',float('inf')),('composite',2),
    ('buy_percent',-1),('sell_percent',float('nan')),('buy_percent',1),('timestamp_ns',TS+1)])
def test_percentuais_invalidos_ou_de_outro_quadro_nao_sao_exibidos(campo,valor):
    e = estado()
    d = replace(dominancia_valida(e),**{campo:valor})
    assert not analitica.pressao_do_snapshot(replace(e,dominancia_snapshot=d)).disponivel


@pytest.mark.parametrize('status',[asg.EstadoASG.ATRASADO,asg.EstadoASG.SEM_BOOK,
                                  asg.EstadoASG.ERRO,asg.EstadoASG.AGUARDANDO])
def test_feed_bloqueado_nao_publica_pressao_ativa(status):
    e = estado()
    d = dominancia_valida(e)
    p = analitica.pressao_do_snapshot(replace(e,snapshot=workspace(estado=status),dominancia_snapshot=d))
    assert not p.disponivel and p.motivo==status.value


def test_fallback_so_existe_no_contrato_legado_e_e_declarado():
    p = analitica.pressao_do_snapshot(estado())
    assert p.disponivel and p.origem=='PROXY AUXILIAR'
    assert p.compra==71 and p.venda==29  # 0.7*0.6, sem fabricar o ritmo ausente


@pytest.mark.parametrize('entrada,esperado',[
    ('10000t',10000),('10000',10000),(10000,10000),('-12t',-12),
    ('5.000,0',None),('12.5t',None),(True,None),(None,None),('—',None)])
def test_parser_de_niveis_preserva_ticks_e_rejeita_moeda_ambigua(entrada,esperado):
    assert analitica.preco_ticks_publicado(entrada)==esperado


def test_stop_e_tres_alvos_do_dto_agora_chegam_ao_grafico_e_as_capsulas(qapp,monkeypatch):
    e = estado(snapshot=workspace(stop='9990t',alvo_1='10010t',alvo_2='10020t',alvo_3='10030t'))
    niveis = analitica.niveis_do_snapshot(e)
    assert [(n.rotulo,n.preco) for n in niveis]==[('STOP',9990),('A1',10010),('A2',10020),('A3',10030)]
    textos = []
    monkeypatch.setattr(referencia,'_texto',lambda *a,**kw:textos.append(str(a[5])))
    imagem = QImage(640,270,QImage.Format.Format_ARGB32)
    p = QPainter(imagem)
    try:
        referencia._niveis(p,e)
    finally:
        p.end()
    assert referencia._preco(e,9990) in textos and referencia._preco(e,10010) in textos
    assert '—' not in [n.rotulo for n in niveis]


def test_regioes_publicadas_mantem_limites_e_testes_sem_promover_observacao():
    e = estado()
    zonas = (zona(),replace(zona(lado=sr.LadoZona.NEUTRO),id='observacao',preco=10002,
                           inferior=10001,superior=10003,status=sr.EstadoZona.OBSERVACAO),
             replace(zona(sr.EstadoZona.INVALIDADA),id='invalida'))
    ns = analitica.niveis_do_snapshot(replace(e,sr_snapshot=snapshot_sr(e,zonas)))
    assert len(ns)==2
    assert (ns[0].inferior,ns[0].superior,ns[0].toques)==(9996,10004,3)
    assert ns[0].confirmado and not ns[1].confirmado and ns[1].classe=='OBSERVAÇÃO'


def test_sr_antigo_nao_e_desenhado_como_regiao_atual():
    e = estado()
    snap = replace(snapshot_sr(e,(zona(),)),timestamp_ns=TS-1)
    assert analitica.niveis_do_snapshot(replace(e,sr_snapshot=snap))==()


def test_timeframe_visual_nao_muda_as_entradas_da_analitica():
    e = estado()
    outro = replace(e,candles_m15=candles(8,-1),candles_timeframe_min=15,
                    candles_offset=5,candles_zoom_preco=3,candles_velas_visiveis=10)
    assert dominancia.construir_entrada_dominancia(e)==dominancia.construir_entrada_dominancia(outro)
    assert suporte_resistencia.construir_entrada_sr(e)==suporte_resistencia.construir_entrada_sr(outro)


def test_base_analitica_vazia_nao_e_substituida_por_candles_da_tela():
    entrada = dominancia.construir_entrada_dominancia(estado(candles_analiticos=()))
    assert entrada['componentes_micro'] is None and entrada['amostras_macro']==0


def test_componente_book_usa_quantidade_real_e_nao_delta_do_candle():
    e = estado(candles_m15=candles(15,-1))
    b = suporte_resistencia.desequilibrio_de_book(e)
    assert b==pytest.approx((350-150)/(350+150))
    assert dominancia.componentes_micro(e)['B']==b
    assert suporte_resistencia.construir_entrada_sr(e)['micro'].componentes['book_imbalance']==b


def test_componentes_numericos_nao_dependem_do_top3_arredondado():
    c = MakerComponentScore(ComponenteMaker.AGRESSAO,.123456,.3,.3,.9,1.,4,TS,disponivel=True)
    m = replace(linha(),componentes_maker=(c,),detalhe='1o AGRESSAO +99% giro 9')
    assert suporte_resistencia.componente_agressao(m)==pytest.approx(.123456)
    assert suporte_resistencia.componente_reposicao(m)==0  # ausência não vira agregado .6
    indisponivel = replace(m,componentes_maker=(replace(c,disponivel=False),))
    assert suporte_resistencia.componente_agressao(indisponivel)==0


def test_vap_curto_expira_sem_novos_negocios_e_sessao_permanece(qapp,monkeypatch):
    monkeypatch.setenv('FLUXOPRO_ANALISE_IA','0')
    p = asg.PainelNexoMercadoASG()
    try:
        p._registrar_amostra(TS,10000,.5,40,AgressorSide.BUY)
        p._snapshot = workspace(TS+6*60*S)
        p._vap_timeframe_min = 5
        assert p._perfil_vap_ativo().volume_total==0
        p._vap_timeframe_min = 15
        assert p._perfil_vap_ativo().volume_total==40
        p._snapshot = workspace(TS+16*60*S)
        assert p._perfil_vap_ativo().volume_total==0
        assert p._vap.volume_total==40
    finally:
        p.parar_relogio(); p.close(); p.deleteLater()


@pytest.mark.parametrize('fonte,idade_zero',[('SIMULATOR',True),('REPLAY',True),('MT5',False)])
def test_relogio_sintetico_nao_e_comparado_com_parede_ao_vivo_continua(fonte,idade_zero):
    class Painel:
        _calcular_sr_snapshot = asg.PainelNexoMercadoASG._calcular_sr_snapshot
        _calcular_dominancia_snapshot = asg.PainelNexoMercadoASG._calcular_dominancia_snapshot
    p = Painel()
    p.grid = WDO_GRID
    p._snapshot = workspace(fonte=fonte)
    p._sr_sequencia=p._dominancia_sequencia=0
    p._sr_ultimo_ts=p._dominancia_ultimo_ts=-1
    p._motor_sr=sr.MotorSuporteResistencia('fixture')
    p._motor_dominancia=dom.MotorDominancia('fixture')
    e = estado(snapshot=p._snapshot)
    saidas = (p._calcular_sr_snapshot(e),p._calcular_dominancia_snapshot(e))
    for saida in saidas:
        assert (saida.saude.idade_ms==0)==idade_zero


def test_f6_descreve_fontes_mesmos_niveis_e_limites_da_metodologia():
    e = estado(vap_poc=10000,fase_renko=FaseRenko.PERDENDO_FORCA)
    texto = analitica.texto_auditoria(e)
    assert 'M5' in texto and 'PERDENDO FORÇA' in texto and '10000 ticks' in texto
    assert 'W=-B' in texto and 'não é uma medição' in texto and 'não probabilidade' in texto


def test_histograma_usa_forca_canonica_sem_dados_futuros_ou_fallback_de_negocios():
    e = estado(serie_forca_ai=((TS-4,.4),(TS-3,float('nan')),(TS-2,2.),(TS+1,-.8)),
               serie=((TS-1,10000,.99,10),))
    assert analitica.historico_forca(e)==((TS-4,.4),)
    assert analitica.historico_forca(replace(e,serie_forca_ai=()))==()


def test_histograma_tem_limite_de_23_amostras_publicadas():
    amostras = tuple((TS-30+i,.5) for i in range(30))
    assert analitica.historico_forca(estado(serie_forca_ai=amostras))==amostras[-23:]
