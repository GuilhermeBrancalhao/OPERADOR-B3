"""Projeção analítica pura do MESMO snapshot para gráfico, rodapé e F6.

Sem relógio, feed, Qt, LLM ou ordens. Ausência não é zero e um motor
indisponível nunca é substituído silenciosamente por outra metodologia.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from fluxopro.analytics.dominancia import calcular_placar
from fluxopro.analytics.renko import FaseRenko
from fluxopro.analytics.suporte_resistencia import EstadoFeed, EstadoZona, LadoZona
from fluxopro.ui.paineis.asg import ConfiancaASG, EstadoASG


@dataclass(frozen=True,slots=True)
class PressaoVisual:
    disponivel: bool = False
    compra: float | None = None
    venda: float | None = None
    score: float | None = None
    origem: str = 'DOMINÂNCIA'
    estado: str = 'INDISPONÍVEL'
    motivo: str = ''


@dataclass(frozen=True,slots=True)
class NivelVisual:
    rotulo: str
    preco: int
    origem: str
    classe: str
    inferior: int | None = None
    superior: int | None = None
    forca: float | None = None
    toques: int | None = None
    confirmado: bool | None = None


def _finito(valor):
    return isinstance(valor,(int,float)) and not isinstance(valor,bool) and math.isfinite(valor)


def leitura_disponivel(linha):
    return (linha is not None and _finito(getattr(linha,'forca',None))
            and getattr(linha,'confianca',None) not in (None,ConfiancaASG.INDISPONIVEL))


def motivo_bloqueio(estado):
    s = estado.snapshot
    if s is None:
        return 'SEM SNAPSHOT'
    if s.estado_operacional not in {EstadoASG.AO_VIVO,EstadoASG.REPLAY}:
        return s.estado_operacional.value
    c = s.contexto_bruto
    if c is None or not c.bids or not c.asks:
        return 'SEM BOOK'
    return ''


def pressao_do_snapshot(estado):
    bloqueio = motivo_bloqueio(estado)
    if bloqueio:
        return PressaoVisual(motivo=bloqueio)
    d = estado.dominancia_snapshot
    if d is not None:
        saude = getattr(d,'saude',None)
        if getattr(d,'timestamp_ns',None)!=estado.snapshot.timestamp_ns:
            return PressaoVisual(motivo='DOMINÂNCIA DE OUTRO QUADRO')
        if getattr(saude,'estado',None) is not EstadoFeed.LIVE:
            motivo = getattr(saude,'motivo',None) or getattr(getattr(saude,'estado',None),'value','SEM SAÚDE')
            return PressaoVisual(motivo=str(motivo))
        if not _finito(d.composite) or not -1<=d.composite<=1:
            return PressaoVisual(motivo='COMPOSTO INDISPONÍVEL')
        if str(getattr(d.estado,'value',''))=='UNAVAILABLE':
            return PressaoVisual(motivo='MOTOR INDISPONÍVEL')
        compra,venda = d.buy_percent,d.sell_percent
        if (not _finito(compra) or not _finito(venda) or not 0<=compra<=100
                or not 0<=venda<=100 or abs(compra+venda-100)>.001):
            return PressaoVisual(motivo='PERCENTUAIS INVÁLIDOS')
        rotulo = {'BUY':'COMPRA','SELL':'VENDA','ULTRA_BUY':'ULTRA COMPRA',
                  'ULTRA_SELL':'ULTRA VENDA','BALANCED':'BALANCEADO'}.get(d.estado.value,d.estado.value)
        return PressaoVisual(True,compra,venda,d.composite,'DOMINÂNCIA',rotulo)
    # Compatibilidade explícita para estados antigos que NÃO têm motor.
    maker = estado.maker if leitura_disponivel(estado.maker) else None
    ritmo = next((l for n,l in estado.leituras if n=='RITMO' and leitura_disponivel(l)),None)
    if maker is None and ritmo is None:
        return PressaoVisual(origem='PROXY AUXILIAR',motivo='SEM COMPONENTES VÁLIDOS')
    score = max(-1.,min(1.,.7*(maker.forca if maker else 0)+.3*(ritmo.forca if ritmo else 0)))
    compra,venda = calcular_placar(score)
    return PressaoVisual(True,compra,venda,score,'PROXY AUXILIAR','LEITURA PARCIAL',
                         '70% Maker + 30% Ritmo; não é a dominância do motor')


def preco_ticks_publicado(valor):
    """O contrato da decisão publica '10000t', não '5.000,0' em moeda."""
    if isinstance(valor,int) and not isinstance(valor,bool):
        return valor
    if isinstance(valor,str) and re.fullmatch(r'[+-]?\d+t?',valor.strip()):
        return int(valor.strip().removesuffix('t'))
    return None


def niveis_do_snapshot(estado):
    saida = []
    s = estado.snapshot
    saudavel = not motivo_bloqueio(estado)
    if saudavel and s.decisao.timestamp_ns==s.timestamp_ns:
        for nome,campo in [('STOP','stop'),('A1','alvo_1'),('A2','alvo_2'),('A3','alvo_3')]:
            preco = preco_ticks_publicado(getattr(s.decisao,campo,None))
            if preco is not None:
                saida.append(NivelVisual(nome,preco,'DECISÃO INFORMATIVA','STOP' if nome=='STOP' else 'ALVO'))
    sr = estado.sr_snapshot
    if (saudavel and sr is not None and sr.timestamp_ns==s.timestamp_ns
            and sr.saude.estado is EstadoFeed.LIVE):
        for zona in sr.zonas:
            if zona.status not in {EstadoZona.ATIVA,EstadoZona.OBSERVACAO}:
                continue
            if not zona.inferior<=zona.preco<=zona.superior:
                continue
            classe = ('SUPORTE' if zona.lado is LadoZona.SUPORTE else
                      'RESISTÊNCIA' if zona.lado is LadoZona.RESISTENCIA else 'OBSERVAÇÃO')
            confirmado = zona.lado is not LadoZona.NEUTRO and zona.status is EstadoZona.ATIVA
            saida.append(NivelVisual(classe,zona.preco,'S/R · PROXY INDEPENDENTE',classe,
                                    zona.inferior,zona.superior,zona.score,zona.toques,confirmado))
    for nome,preco in [('POC',estado.vap_poc),('VAL',estado.vap_val),('VAH',estado.vap_vah)]:
        if isinstance(preco,int) and not isinstance(preco,bool):
            saida.append(NivelVisual(nome,preco,f'VAP {estado.vap_timeframe_min or "SESSÃO"}',nome))
    return tuple(saida)


def fase_renko(estado):
    return {
        FaseRenko.TENDENCIA:'TENDÊNCIA',FaseRenko.PERDENDO_FORCA:'PERDENDO FORÇA',
        FaseRenko.POSSIVEL_INVERSAO:'POSSÍVEL INVERSÃO',FaseRenko.INDEFINIDA:'AQUECENDO',
    }.get(estado.fase_renko,'SEM FASE')


def historico_forca(estado):
    if estado.snapshot is None:
        return ()
    return tuple((ts,v) for ts,v in estado.serie_forca_ai
                 if ts<=estado.snapshot.timestamp_ns and _finito(v) and -1<=v<=1)[-23:]


def texto_auditoria(estado):
    from . import candles_de_analise
    pressao = pressao_do_snapshot(estado)
    linhas = ['ANÁLISE VINCULADA AO VISUAL',
              f'Pressão: {pressao.origem} | {pressao.estado} | {pressao.motivo}',
              f'Compra/venda: {pressao.compra!r} / {pressao.venda!r} (balanço, não probabilidade)',
              f'Base analítica M5: {len(candles_de_analise(estado))} candles; '
              f'exibição: M{estado.candles_timeframe_min}; zoom não recalcula o sinal.',
              f'Renko: {fase_renko(estado)} | tamanho atual {estado.renko_tamanho_ticks} ticks',
              'Alvos Renko são projeções proxy, separados de STOP/A1/A2/A3 da decisão.',
              'B usa profundidade real (5 níveis, peso 1/rank) quando disponível; senão delta/volume legado.',
              'W=-B continua proxy declarado; não é uma medição de cancelamentos/retirada.',
              'NÍVEIS DO SNAPSHOT ATUAL (não os do instante histórico apontado no gráfico):']
    linhas += [f'{n.rotulo}: {n.preco} ticks | {n.origem} | faixa={n.inferior}/{n.superior}'
               f' | força={n.forca!r} | testes={n.toques!r} | confirmado={n.confirmado}'
               for n in niveis_do_snapshot(estado)]
    d,sr = estado.dominancia_snapshot,estado.sr_snapshot
    if d is not None:
        linhas += [f'Dominância: saúde={d.saude.estado.value}; idade={d.saude.idade_ms} ms; '
                   f'motivo={d.saude.motivo}; qualidade={d.qualidade_agregada}; '
                   f'confiança={d.confianca_agregada} (não probabilidade)',
                   'Qualidade/confiança dos horizontes são proxies de aquecimento (n/12 candles), '
                   'não acurácia calibrada nem garantia de completude do feed.',
                   'Amostras = candles disponíveis na base; movimento M usa os últimos 2/8 M5. '
                   'A/B/R/W vêm do snapshot atual, não de livros históricos dos horizontes.']
        for nome,h in [('MICRO',d.micro),('MACRO',d.macro)]:
            if h is not None:
                linhas += [f'{nome}: janela nominal={h.janela_ms} ms; cobertura observada={h.cobertura_ms} ms; '
                           f'amostras={h.amostras}; score={h.score}']
    if sr is not None:
        linhas += [f'S/R: saúde={sr.saude.estado.value}; motivo={sr.saude.motivo}; '
                   f'zonas do motor={len(sr.zonas)}; alerta={sr.alerta.value}']
        linhas += [f'Zona {z.id}: {z.status.value} | lado={z.lado.value} | força={z.score} | '
                   f'limites={z.inferior}/{z.superior} | testes={z.toques}' for z in sr.zonas]
    return '\n'.join(linhas)
