# -*- coding: utf-8 -*-
"""Sonda R6 — PARTE C: ataques de sistema.

C.1 reprodutibilidade gravar->reler
C.2 virada de sessao: quem tem reset, o que sobra
C.3 determinismo: motor sem random; _MapaProcedencia com vitima SORTEADA
C.4 interacao entre os relogios/janelas da onda 8

Uso: PYTHONPATH=. python .mut/sonda_r6_sistema.py
"""
from __future__ import annotations
import inspect, os, random, shutil, sys, tempfile
from datetime import date

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Side, Trade
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.gravacao.gravador import Gravador
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao
from fluxopro.app.config import ConfigOperacao
from fluxopro.app.sessao_fluxo import SessaoFluxo
from fluxopro.microestrutura import detectores as D

LINHA = "=" * 78

# =====================================================================  C.3a
print(LINHA)
print("C.3a — DETERMINISMO do pipeline: duas execucoes do MESMO tape")
print(LINHA)


def rodar(n, seed=7):
    bar = Barramento()
    cfg = ConfigOperacao(symbol="WDOV26")
    sessao = SessaoFluxo(bar, cfg)
    saidas = []
    sessao.motor_saida = None
    fonte = SimuladorWDO(bar, symbol="WDOV26", seed=seed, n_eventos=n)
    orig = sessao.ao_trade if hasattr(sessao, "ao_trade") else None
    fonte.iniciar()
    sessao.finalizar()
    c = sessao.contadores
    return (c.n_eventos_bus, c.n_trades_bus, c.n_deltas_bus,
            getattr(c, "n_sinais", None), getattr(c, "n_deteccoes", None))


try:
    a = rodar(250_000)
    b = rodar(250_000)
    print(f"  execucao 1: {a}")
    print(f"  execucao 2: {b}")
    print(f"  => {'IDENTICAS' if a == b else '*** DIVERGEM ***'}")
except Exception as e:
    print("  ERRO:", type(e).__name__, e)

# =====================================================================  C.3b
print()
print(LINHA)
print("C.3b — o RNG do despejo do _MapaProcedencia")
print(LINHA)
print(f"  _SORTEIO_DESPEJO e' {D._SORTEIO_DESPEJO!r} (modulo-global, semeado)")
print(f"  LIMITE_CHAVES_RASTREADAS = {D.LIMITE_CHAVES_RASTREADAS:,}")
print(f"  JANELA_EPISODIO_NS       = {D.JANELA_EPISODIO_NS:,} ns "
      f"({D.JANELA_EPISODIO_NS/1e9:.0f} s)")
fonte_limpar = inspect.getsource(D._MapaProcedencia.limpar)
print(f"  limpar() resemeia o RNG? "
      f"{'SIM' if 'SORTEIO' in fonte_limpar or 'seed' in fonte_limpar else '*** NAO ***'}")

# (i) o despejo chega a disparar em regime realista?
mapa = D._MapaProcedencia()
ts = 0
for i in range(300_000):          # 300k eventos, faixa de preco realista do WDO
    ts += 1_000_000              # 1 ms por evento
    lado = Side.BUY if i % 2 else Side.SELL
    preco = 5000 + (i % 2000)    # 2.000 ticks distintos = faixa de um pregao
    mapa.somar((lado, preco), 1.0, D.FonteMicro.MBO, agora_ns=ts)
print(f"  (i) 300.000 eventos, 2.000 ticks distintos, chaves (side,price):")
print(f"      len(mapa) = {len(mapa):,}  contra teto de {D.LIMITE_CHAVES_RASTREADAS:,}")
print(f"      => despejo sorteado {'DISPAROU' if len(mapa) >= D.LIMITE_CHAVES_RASTREADAS else 'NUNCA DISPAROU'}")

# (ii) forcando o despejo: e' reprodutivel entre SESSOES do mesmo processo?
def sequencia_despejo(limite=64, n=4_000):
    m = D._MapaProcedencia(limite=limite, janela_episodio_ns=10**18)  # TTL infinito
    t = 0
    for i in range(n):
        t += 1_000_000
        m.somar((Side.BUY, i), 1.0, D.FonteMicro.MBO, agora_ns=t)
    return tuple(sorted(k[1] for k in m._itens))

s1 = sequencia_despejo()
s2 = sequencia_despejo()          # 2a "sessao" no MESMO processo
print(f"  (ii) com teto forcado (limite=64, TTL infinito, 4.000 chaves novas):")
print(f"       sobreviventes da 1a passada: {s1[:8]}...")
print(f"       sobreviventes da 2a passada: {s2[:8]}...")
print(f"       => {'IGUAIS (deterministico)' if s1 == s2 else '*** DIVERGEM — o RNG global nao volta ao inicio entre sessoes ***'}")

# (iii) e um processo novo? (compara com o valor gravado do processo anterior)
import hashlib, json
arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "r6_despejo_ref.json")
h = hashlib.sha256(repr(s1).encode()).hexdigest()[:16]
if os.path.exists(arq):
    ant = json.load(open(arq))
    print(f"  (iii) processo ANTERIOR: {ant['h']}   este processo: {h}")
    print(f"        => {'IGUAIS entre processos' if ant['h'] == h else '*** DIVERGEM entre processos ***'}")
else:
    json.dump({"h": h}, open(arq, "w"))
    print(f"  (iii) primeira execucao; gravado {h} para comparar no proximo processo")

# =====================================================================  C.2
print()
print(LINHA)
print("C.2 — VIRADA DE SESSAO: o que sobra do dia anterior")
print(LINHA)
bar = Barramento()
cfg = ConfigOperacao(symbol="WDOV26")
sessao = SessaoFluxo(bar, cfg)
fonte = SimuladorWDO(bar, symbol="WDOV26", seed=3, n_eventos=60_000)
fonte.iniciar()
sessao.finalizar()


def _n(v):
    return v() if callable(v) else v


def foto(s):
    f = {}
    fp = getattr(s, "footprint", None)
    if fp is not None:
        f["footprint._niveis (candle corrente)"] = len(getattr(fp, "_niveis", {}) or {})
        f["footprint candles fechados"] = len(getattr(fp, "_fechados", []) or [])
    if s.motor is not None:
        f["motor._n_visto"] = s.motor._n_visto
        f["motor._max_sessao"] = s.motor._max_sessao
        f["motor len(_reservatorio)"] = len(s.motor._reservatorio)
        f["motor len(_janela_dominancia)"] = len(s.motor._janela_dominancia)
    if s.brokers is not None:
        f["brokers n_corretoras"] = len(getattr(s.brokers, "_estatisticas", {}) or {})
    if s.perfil_player is not None:
        f["perfil_player n_brokers"] = len(getattr(s.perfil_player, "_brokers", {}) or {})
    if s.livro is not None:
        f["livro n_ordens"] = len(getattr(s.livro, "_ordens", {}) or {})
    if s.det_escora is not None:
        f["det_escora n_chaves"] = s.det_escora.n_chaves_rastreadas
    if s.det_liquidez_fantasma is not None:
        f["det_fantasma n_chaves"] = s.det_liquidez_fantasma.n_chaves_rastreadas
    f["estado.delta_sessao"] = getattr(s.estado.sessao, "delta", None)
    f["estado.volume_sessao"] = getattr(s.estado.sessao, "volume_total", None)
    return f


antes = foto(sessao)
sessao.iniciar_nova_sessao(10**18)
depois = foto(sessao)
print(f"  {'campo':<40} {'dia 1':>14} {'apos virada':>14}  veredito")
sobrou = []
for k in antes:
    a_, d_ = antes[k], depois.get(k)
    ok = (d_ in (0, None, 0.0)) or (a_ == d_ == 0)
    if not ok:
        sobrou.append(k)
    print(f"  {k:<40} {str(a_):>14} {str(d_):>14}  {'zerou' if ok else '*** SOBROU ***'}")
print(f"  => {len(sobrou)} campo(s) carregam o dia anterior: {sobrou if sobrou else 'nenhum'}")
print(f"  SEM_RESET_POSSIVEL declarado na app: {SessaoFluxo.SEM_RESET_POSSIVEL}")

# =====================================================================  C.1
print()
print(LINHA)
print("C.1 — REPRODUTIBILIDADE: gravar e reler produz os MESMOS sinais?")
print(LINHA)
tmp = tempfile.mkdtemp(prefix="r6_grav_")
try:
    bar1 = Barramento()
    cfg1 = ConfigOperacao(symbol="WDOV26")
    s1v = SessaoFluxo(bar1, cfg1)
    grav = Gravador(bar1, tmp, fsync_a_cada=5000)
    grav.iniciar()
    SimuladorWDO(bar1, symbol="WDOV26", seed=11, n_eventos=8_000).iniciar()
    s1v.finalizar()
    grav.parar()
    vivo = (s1v.contadores.n_eventos_bus, s1v.contadores.n_trades_bus,
            s1v.contadores.n_deltas_bus)

    cat = Catalogo(tmp)
    entradas = cat.escanear()
    print(f"  gravado: {len(entradas)} entrada(s) de catalogo em {tmp}")
    if entradas:
        e = entradas[0]
        print(f"    symbol={e.symbol} data={e.data} n_eventos_total={e.n_eventos_total:,}")
        print(f"    integridade: {cat.verificar_integridade(e)}")
        bar2 = Barramento()
        s2v = SessaoFluxo(bar2, ConfigOperacao(symbol="WDOV26"))
        AdaptadorLeitorGravacao(bar2, e, catalogo=cat).iniciar()
        s2v.finalizar()
        rele = (s2v.contadores.n_eventos_bus, s2v.contadores.n_trades_bus,
                s2v.contadores.n_deltas_bus)
        print(f"    ao vivo : {vivo}")
        print(f"    relido  : {rele}")
        print(f"    => {'IDENTICO' if vivo == rele else '*** DIVERGE ***'}")
    else:
        print("  *** nenhuma entrada: o catalogo nao indexou a gravacao ***")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# =====================================================================  C.4
print()
print(LINHA)
print("C.4 — INTERACAO entre as janelas da onda 8: qual BASE DE TEMPO cada uma usa")
print(LINHA)
import inspect as _i
from fluxopro.dados import mt5 as _m
from fluxopro.motor import sinais as _s

fonte_admitir = _i.getsource(_m._RelogioServidor._admitir)
fonte_varrer = _i.getsource(D._MapaProcedencia._expirado)
fonte_dom = _i.getsource(_s.MotorSinais._registrar_dominancia)

def base(src):
    if "monotonic_ns" in src or "time.time_ns" in src:
        return "RELOGIO DE PAREDE"
    return "timestamp do EVENTO (tape)"

print(f"  dedup do _MapaProcedencia   TTL {D.JANELA_EPISODIO_NS/1e9:>6.0f} s   base: {base(fonte_varrer)}")
print(f"  janela do _RelogioServidor      {_m._JANELA_OFFSET_S:>6.0f} s   base: {base(fonte_admitir)}")
print(f"  janela de dominancia do motor   {_s.ConfigMotorSinais().janela_dominancia_ns/1e9:>6.0f} s   base: {base(fonte_dom)}")
print()
print("  => as tres NAO compartilham base de tempo. Em regime normal (tape ~ parede)")
print("     elas coincidem; sob sobrecarga do adaptador — o regime de 50.000 ticks/s")
print("     que o proprio bench_mt5 documenta, em que o adaptador consome tape mais")
print("     devagar que a parede — a janela do relogio envelhece MAIS RAPIDO em")
print("     relacao ao dado do que as outras duas.")
