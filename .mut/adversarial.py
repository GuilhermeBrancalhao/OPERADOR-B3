"""Ataques adversariais: (A) deques monotonicas vs varredura ingenua,
(B) dedup de 3 gatilhos perde episodio legitimo?, (C) perfil do MotorSinais,
(D) cenario de falha WINFUT no motor de sinais."""
from __future__ import annotations
import cProfile, io, pstats, random, sys

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.detectores import ConfigAbsorcao, DetectorAbsorcao
from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.motor.sinais import ConfigMotorSinais, EstagioSinal, MotorSinais

S = "WDOFUT"


def t(ts, price, qty, lado, i=0):
    return Trade(ts, S, price, qty, lado, f"t{i}")


# ---------------------------------------------------------------- A
def a_diferencial():
    """Deque monotonica DEVE dar exatamente o mesmo max/min que varredura ingenua."""
    print("=" * 84)
    print("A) DIFERENCIAL: deques monotonicas vs varredura ingenua (max/min da janela)")
    print("=" * 84)
    piores = 0
    for seed in range(200):
        rng = random.Random(seed)
        cfg = ConfigAbsorcao(janela_ns=1_000_000_000)
        det = DetectorAbsorcao(S, cfg)
        janela_ingenua = []
        ts = 1_000_000_000_000
        for i in range(400):
            # timestamps com saltos aleatorios (inclui buracos > janela)
            ts += rng.choice([1, 1000, 10_000, 1_000_000, 300_000_000, 1_200_000_000])
            price = 10_000 + rng.randrange(0, 6)
            tr = t(ts, price, rng.randint(1, 9),
                   rng.choice([AgressorSide.BUY, AgressorSide.SELL, AgressorSide.UNKNOWN]), i)
            det.ao_trade(tr)
            janela_ingenua.append(tr)
            lim = ts - cfg.janela_ns
            janela_ingenua = [x for x in janela_ingenua if x.timestamp_ns >= lim]
            esp_max = max(x.price for x in janela_ingenua)
            esp_min = min(x.price for x in janela_ingenua)
            got_max = det._max_precos[0][1]
            got_min = det._min_precos[0][1]
            vb = sum(x.qty for x in janela_ingenua if x.side_agressor is AgressorSide.BUY)
            vs = sum(x.qty for x in janela_ingenua if x.side_agressor is AgressorSide.SELL)
            if (esp_max, esp_min, vb, vs) != (got_max, got_min, det._volume_buy, det._volume_sell):
                piores += 1
                if piores <= 3:
                    print(f"  DIVERGENCIA seed={seed} i={i}: esperado max/min/vb/vs="
                          f"{esp_max}/{esp_min}/{vb}/{vs} obtido={got_max}/{got_min}/"
                          f"{det._volume_buy}/{det._volume_sell}")
                break
    print(f"  200 tapes aleatorios x 400 trades: divergencias = {piores}")
    print(f"  VEREDITO: {'MAX/MIN E VOLUMES CORRETOS' if piores == 0 else 'DEFEITO SEMANTICO'}\n")


# ---------------------------------------------------------------- B
def b_dedup():
    print("=" * 84)
    print("B) DEDUP: dois episodios LEGITIMOS separados por pausa, mesmo preco")
    print("=" * 84)
    cfg = ConfigAbsorcao(volume_minimo=300, deslocamento_maximo_ticks=1,
                         janela_ns=5_000_000_000)
    det = DetectorAbsorcao(S, cfg)
    ts = 1_000_000_000_000
    alertas = []
    # Episodio 1: 4s de agressao vendedora pesada em 10000, preco nao cai.
    for i in range(40):
        ts += 100_000_000  # 100ms
        d = det.ao_trade(t(ts, 10_000, 20, AgressorSide.SELL, i))
        if d: alertas.append(("ep1", i, d.evidencia["volume_agressao_dominante"]))
    print(f"  episodio 1 (40 trades, 800 lotes vendedores em 10000): {len(alertas)} alerta(s)")
    # Pausa de 3s: NAO esvazia a janela de 5s. Um trade solitario mantem viva.
    ts += 3_000_000_000
    det.ao_trade(t(ts, 10_000, 1, AgressorSide.BUY, 999))
    n1 = len(alertas)
    # Episodio 2: NOVA leva de agressao vendedora, mesmo preco. Fenomeno novo.
    for i in range(40):
        ts += 100_000_000
        d = det.ao_trade(t(ts, 10_000, 20, AgressorSide.SELL, 1000 + i))
        if d: alertas.append(("ep2", i, d.evidencia["volume_agressao_dominante"]))
    print(f"  episodio 2 (mesma coisa de novo, apos pausa de 3s): {len(alertas)-n1} alerta(s)")
    print(f"  >>> {'PERDEU o 2o episodio' if len(alertas)-n1 == 0 else 'ok'}")

    print("\n  B2) episodio de 6 HORAS no mesmo preco (pregao inteiro, sem buraco de 5s)")
    det2 = DetectorAbsorcao(S, cfg)
    ts = 1_000_000_000_000
    n = 0
    for i in range(60_000):          # 6h a 1 trade/360ms
        ts += 360_000_000
        if det2.ao_trade(t(ts, 10_000 + (i % 2), 20, AgressorSide.SELL, i)):
            n += 1
    print(f"     60.000 trades, preco oscilando 1 tick, 1.2M lotes vendidos: {n} alerta(s)")

    print("\n  B3) o lado que absorve VIRA e VOLTA (deveria rearmar e realertar)")
    det3 = DetectorAbsorcao(S, cfg)
    ts = 1_000_000_000_000
    seq = []
    for fase, lado in enumerate([AgressorSide.SELL, AgressorSide.BUY, AgressorSide.SELL]):
        for i in range(40):
            ts += 10_000_000
            d = det3.ao_trade(t(ts, 10_000, 30, lado, fase * 100 + i))
            if d: seq.append((fase, lado.name, d.side.name))
    print(f"     alertas: {[(f, l, s) for f, l, s in seq]}")
    print()


# ---------------------------------------------------------------- C
def c_perfil_motor():
    print("=" * 84)
    print("C) PERFIL do MotorSinais — onde o tempo vai (8.000 trades)")
    print("=" * 84)
    rng = random.Random(5)
    trades, ts = [], 1_000_000_000_000
    for i in range(8_000):
        ts += 200_000
        trades.append(t(ts, 10_000 + rng.randrange(60), rng.randint(1, 10),
                        AgressorSide.BUY if rng.random() < 0.8 else AgressorSide.SELL, i))
    vp = VolumeProfile()
    m = MotorSinais(S, vp)
    pr = cProfile.Profile(); pr.enable()
    for tr in trades:
        vp.registrar_trade(tr); m.ao_trade(tr)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(10)
    print("\n".join(s.getvalue().splitlines()[4:20]))
    print()


# ---------------------------------------------------------------- D
def d_winfut():
    """Modo de falha documentado em pesquisa/ferramenta_componentes.md secao 7.

    Macro vendedora ~90% da sessao com picos de magnitude -1925; um pico
    COMPRADOR breve de +915 (metade da magnitude) inverte o sinal instantaneo.
    A fonte diz: a leitura correta exige normalizar por magnitude relativa ao
    historico intradiario E por persistencia temporal. O motor faz alguma
    dessas duas coisas?
    """
    print("=" * 84)
    print("D) CENARIO WINFUT — o motor cai no modo de falha documentado?")
    print("=" * 84)
    cfg = ConfigMotorSinais(dominancia_minima=0.70,
                            janela_dominancia_ns=5 * 60_000_000_000,
                            margem_regiao_ticks=2,
                            janela_micro_ns=15_000_000_000)
    vp = VolumeProfile()
    m = MotorSinais(S, vp)
    ts = 1_000_000_000_000
    INT = 100_000_000  # 10 trades/s -> 5 min = 3000 trades

    # FASE 1 — 90% da sessao vendedora, magnitude alta (equivalente a -1925).
    hist = []
    for i in range(6_000):
        ts += INT
        lado = AgressorSide.SELL if i % 10 < 9 else AgressorSide.BUY   # 90% vendedor
        tr = t(ts, 10_000 + (i % 5), 20, lado, i)
        vp.registrar_trade(tr)
        s = m.ao_trade(tr)
        hist.append(s)
    print(f"  FASE 1 (10 min, 90% vendedor, magnitude ALTA):")
    print(f"    estagio final = {hist[-1].estagio.name}  direcao = "
          f"{hist[-1].direcao.name if hist[-1].direcao else None}  "
          f"dominancia = {hist[-1].evidencia['dominancia']:.3f}")

    # FASE 2 — pico comprador BREVE e de magnitude MENOR (o +915 contra -1925).
    # Basta que a janela de 5 min vire comprador: sao 3.000 trades.
    for i in range(3_200):
        ts += INT
        lado = AgressorSide.BUY if i % 10 < 9 else AgressorSide.SELL
        tr = t(ts, 10_000 + (i % 5), 9, lado, 100_000 + i)   # qty MENOR: 9 vs 20
        vp.registrar_trade(tr)
        s = m.ao_trade(tr)
    print(f"  FASE 2 (5,3 min, 90% comprador, magnitude MENOR — qty 9 vs 20):")
    print(f"    estagio = {s.estagio.name}  direcao = "
          f"{s.direcao.name if s.direcao else None}  "
          f"dominancia = {s.evidencia['dominancia']:.3f}")
    virou = s.direcao is Side.BUY
    print()
    print(f"  >>> O motor inverteu a direcao do dia para COMPRA? {virou}")
    print(f"  >>> Ele normalizou por magnitude relativa ao historico do dia? "
          f"NAO — `_dominancia` so olha a janela corrente")
    print(f"  >>> Ele exigiu persistencia (a fonte pede 'se ele se sustentar')? "
          f"NAO — 1 trade cruza o limiar e o estagio muda")

    # Prova da ausencia de persistencia: 1 unico trade derruba DIRECAO_CONFIRMADA.
    print("\n  D2) PROVA de ausencia de histerese/persistencia:")
    vp2 = VolumeProfile(); m2 = MotorSinais(S, ConfigMotorSinais() and vp2) if False else None
    vp2 = VolumeProfile()
    m2 = MotorSinais(S, vp2, ConfigMotorSinais(dominancia_minima=0.70,
                                               janela_dominancia_ns=10_000_000_000))
    ts2 = 1_000_000_000_000
    # 70 compras / 30 vendas -> dominancia exatamente 0.70
    est = []
    for i in range(100):
        ts2 += 100_000_000
        lado = AgressorSide.BUY if i < 70 else AgressorSide.SELL
        tr = t(ts2, 10_000, 1, lado, i)
        vp2.registrar_trade(tr); est.append(m2.ao_trade(tr))
    print(f"     apos 70 BUY + 30 SELL: dominancia={est[-1].evidencia['dominancia']:.4f} "
          f"estagio={est[-1].estagio.name}")
    ts2 += 100_000_000
    tr = t(ts2, 10_000, 1, AgressorSide.SELL, 999)
    vp2.registrar_trade(tr); s2 = m2.ao_trade(tr)
    print(f"     +1 unico trade SELL:   dominancia={s2.evidencia['dominancia']:.4f} "
          f"estagio={s2.estagio.name}   <-- mudou de estagio com UM trade")
    print()


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else "todos"
    if alvo in ("todos", "a"): a_diferencial()
    if alvo in ("todos", "b"): b_dedup()
    if alvo in ("todos", "c"): c_perfil_motor()
    if alvo in ("todos", "d"): d_winfut()
