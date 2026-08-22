"""Benchmark do `MotorSinais` — o modulo que a critica R2 mediu em 258 ev/s.

A barra e a mesma do resto do projeto: 10.000 eventos/s (pico do WDO).

Tres medicoes, nesta ordem:

  1. MOTOR ISOLADO      -> N trades direto em `MotorSinais.ao_trade`, com um
                           `VolumeProfile` realista (centenas de niveis de
                           preco, que e o que faz `value_area()` doer).
  2. ESCALONAMENTO      -> dobra N e mostra o us/ev. Custo O(1) por evento
                           mantem o us/ev PLANO; custo quadratico o DOBRA a
                           cada dobra de N (foi o que a R2 mediu: fatores de
                           x4,64 / x4,31 / x3,16 / x4,38 no tempo total).
  3. PIPELINE COMPLETO  -> barramento + EstadoMercado + 6 analytics + 3
                           detectores + MotorSinais. E o estagio que
                           `bench_carga.py` NAO mede (ele para nos detectores).
  4. SESSAO LONGA       -> o eixo DURACAO DE SESSAO, que `criticas/nucleo_r4.md`
                           SS.C.6 aponta faltar em todos os seis benchmarks da
                           raiz: mede o custo dos ULTIMOS 10.000 trades de uma
                           sessao de N, e o tamanho das estruturas de estado no
                           fim. Media global esconde degradacao tardia; um
                           estado que cresce com o dia aparece aqui e so aqui.
  5. A/B contra o GIT  -> (--ab) roda a versao da ARVORE e a versao COMMITADA
                           do motor no MESMO processo, alternadas, no MESMO
                           tape, e compara o MELHOR tempo de cada uma. E o
                           unico estagio que responde "esta correcao custou
                           caro?" sem depender do humor da maquina: aqui a
                           variacao medida entre execucoes identicas passa de
                           50% (150.759 e 89.746 ev/s no mesmo binario), o que
                           torna qualquer comparacao entre DUAS execucoes
                           separadas inutil. Alternar as duas e tomar o minimo
                           tira o ruido, que e sempre aditivo.

Uso:
    python bench_motor.py                    # completo
    python bench_motor.py --n 200000         # motor isolado com N trades
    python bench_motor.py --escala-base 2000 --escala-dobras 5
    python bench_motor.py --perfil           # + cProfile do motor isolado
    python bench_motor.py --so-escala        # so a tabela de escalonamento
    python bench_motor.py --so-ab            # so o A/B contra a versao commitada
    python bench_motor.py --so-ab --ab-ref f6fe46f --ab-repeticoes 9
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import io
import pstats
import random
import subprocess
import sys
import time
import types

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfile, VolumeProfilePorPeriodo
from fluxopro.analytics.vwap import VWAP
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.microestrutura.detectores import (
    DetectorAbsorcao,
    DetectorClipInstitucional,
    DetectorExaustao,
)
from fluxopro.motor.sinais import ConfigMotorSinais, MotorSinais

SYMBOL = "WDOFUT"
UMA_HORA_NS = 3_600_000_000_000
BARRA_EV_S = 10_000

# Taxa de pico do WDO. Importa MUITO aqui: e ela que define quantos trades a
# janela de 5 minutos do motor guarda (a 5.000 trades/s sao 1.500.000).
TAXA_PICO_TRADES_S = 5_000.0


def _tape(n: int, seed: int = 7, taxa: float = TAXA_PICO_TRADES_S) -> list[Trade]:
    """Tape sintetico deterministico com CENTENAS de niveis de preco distintos.

    A quantidade de niveis e o que faz `value_area()` custar: a R2 mediu
    969,6 us/trade com 800 niveis. Um random walk de N passos com passo +-1
    tick cobre ~sqrt(N) niveis, o que da ~450 niveis em 200 mil trades — a
    ordem de grandeza de um pregao de WDO.
    """
    rng = random.Random(seed)
    passo_ns = int(1e9 / taxa)
    preco = 500_000
    trades: list[Trade] = []
    for i in range(n):
        preco += rng.choice((-1, 0, 0, 1))
        lado = AgressorSide.BUY if rng.random() < 0.55 else AgressorSide.SELL
        trades.append(
            Trade(
                timestamp_ns=i * passo_ns,
                symbol=SYMBOL,
                price=preco,
                qty=rng.randint(1, 20),
                side_agressor=lado,
                trade_id=str(i),
            )
        )
    return trades


def _motor_e_perfil() -> tuple[MotorSinais, VolumeProfile]:
    vp = VolumeProfile()
    return MotorSinais(SYMBOL, vp, ConfigMotorSinais()), vp


def _rodar_motor(trades: list[Trade]) -> float:
    """Alimenta motor + perfil (o chamador e quem alimenta o perfil, por
    contrato do `MotorSinais`). Devolve segundos."""
    motor, vp = _motor_e_perfil()
    gc.collect()
    t0 = time.perf_counter()
    for t in trades:
        vp.registrar_trade(t)
        motor.ao_trade(t)
    dt = time.perf_counter() - t0
    del motor, vp
    return dt


def _veredito(eps: float) -> str:
    return "PASSA" if eps >= BARRA_EV_S else "NAO PASSA"


def bench_isolado(n: int) -> None:
    print(f"\n{'=' * 92}")
    print(f"1. MOTOR ISOLADO — {n:,} trades por `MotorSinais.ao_trade`")
    print(f"{'=' * 92}")
    trades = _tape(n)
    niveis = len({t.price for t in trades})
    dt = _rodar_motor(trades)
    eps = n / dt
    print(
        f"  {n:>9,} trades  {dt:8.3f}s  {eps:12,.0f} ev/s  "
        f"{dt * 1e6 / n:8.2f} us/ev   {_veredito(eps)}"
        f"   ({niveis} niveis de preco distintos)"
    )


def bench_escalonamento(base: int, dobras: int) -> None:
    print(f"\n{'=' * 92}")
    print("2. ESCALONAMENTO — dobra N; us/ev PLANO = O(1)/evento, us/ev DOBRANDO = quadratico")
    print(f"{'=' * 92}")
    print(f"  {'N trades':>10}  {'seg':>9}  {'ev/s':>12}  {'us/ev':>9}  "
          f"{'fator tempo':>12}  {'fator us/ev':>12}")
    anterior_dt = None
    anterior_us = None
    for i in range(dobras):
        n = base * (2 ** i)
        dt = _rodar_motor(_tape(n))
        us = dt * 1e6 / n
        f_dt = f"x{dt / anterior_dt:.2f}" if anterior_dt else "—"
        f_us = f"x{us / anterior_us:.2f}" if anterior_us else "—"
        anterior_dt, anterior_us = dt, us
        print(f"  {n:>10,}  {dt:9.3f}  {n / dt:12,.0f}  {us:9.2f}  "
              f"{f_dt:>12}  {f_us:>12}   {_veredito(n / dt)}")
    print("\n  LINEAR: fator tempo ~x2,0 e fator us/ev ~x1,0 (custo por evento plano).")
    print("  QUADRATICO: fator tempo ~x4,0 e fator us/ev ~x2,0.")


def _montar_pipeline(barramento: Barramento, com_motor: bool) -> list[object]:
    vivos: list[object] = [
        EstadoMercado(barramento, SYMBOL),
        VolumeProfilePorPeriodo(barramento, SYMBOL, period_ns=UMA_HORA_NS),
        FootprintPorTimeframe(barramento, SYMBOL),
        CumulativeDelta(barramento, SYMBOL),
        MedidorAgressao(barramento, SYMBOL),
        RankingCorretoras(barramento, SYMBOL),
        VWAP(barramento, SYMBOL),
    ]
    det_abs = DetectorAbsorcao(SYMBOL)
    det_exa = DetectorExaustao(SYMBOL)
    det_clip = DetectorClipInstitucional(SYMBOL)
    vivos.extend([det_abs, det_exa, det_clip])
    barramento.assinar(Trade, det_abs.ao_trade)
    barramento.assinar(Trade, det_exa.ao_trade)
    barramento.assinar(Trade, det_clip.ao_trade)
    if com_motor:
        vp = VolumeProfile()
        motor = MotorSinais(SYMBOL, vp, ConfigMotorSinais())
        vivos.extend([vp, motor])

        def _ao_trade(trade: Trade) -> None:
            vp.registrar_trade(trade)
            motor.ao_trade(trade)

        vivos.append(_ao_trade)
        barramento.assinar(Trade, _ao_trade)
    return vivos


def bench_pipeline(n_passos: int, taxa: float) -> None:
    print(f"\n{'=' * 92}")
    print(f"3. PIPELINE COMPLETO — {n_passos * 2:,} eventos "
          f"({n_passos:,} trades + {n_passos:,} snapshots), taxa {taxa:,.0f} trades/s")
    print(f"{'=' * 92}")
    for rotulo, com_motor in (
        ("4. + 3 detectores (SEM motor)", False),
        ("5. + MotorSinais", True),
    ):
        barramento = Barramento()
        vivos = _montar_pipeline(barramento, com_motor)
        sim = SimuladorWDO(
            barramento, seed=7, taxa_eventos_s=taxa, n_eventos=n_passos, symbol=SYMBOL
        )
        gc.collect()
        t0 = time.perf_counter()
        sim.iniciar()
        dt = time.perf_counter() - t0
        del vivos
        n_ev = n_passos * 2
        eps = n_ev / dt
        print(f"  {rotulo:<32} {dt:8.2f}s {eps:12,.0f} ev/s "
              f"{dt * 1e6 / n_ev:8.2f} us/ev   {_veredito(eps)}")


def bench_sessao_longa(base: int, dobras: int, amostra: int = 10_000) -> None:
    """Custo dos ULTIMOS `amostra` trades conforme a sessao se alonga.

    A media global do estagio 2 dilui um custo que so aparece no fim do dia.
    Aqui o relogio so conta na cauda: se alguma estrutura do motor crescer com
    a duracao da sessao, o us/ev da cauda sobe com N mesmo com o us/ev medio
    plano. As quatro colunas de tamanho sao as estruturas de estado do motor —
    todas tem de ser CONSTANTES no eixo N (a janela satura na taxa x janela;
    a cauda de magnitude e o topo-K, de tamanho fixo; o deque de maior qty e
    monotonico dentro da janela; e a janela movel da referencia guarda R blocos
    de no maximo K inteiros cada, teto R*K = 128 no default, independente de
    quantas amostras o dia produziu).
    """
    print(f"\n{'=' * 92}")
    print(f"4. SESSAO LONGA — custo dos ULTIMOS {amostra:,} trades de uma sessao de N")
    print(f"{'=' * 92}")
    print(f"  {'N trades':>10}  {'cauda seg':>10}  {'cauda ev/s':>12}  {'cauda us/ev':>12}"
          f"  {'janela':>10}  {'topo mag':>9}  {'mono qty':>9}  {'blocos':>7}")
    for i in range(dobras):
        n = base * (2 ** i)
        trades = _tape(n)
        motor, vp = _motor_e_perfil()
        gc.collect()
        corte = n - amostra
        for t in trades[:corte]:
            vp.registrar_trade(t)
            motor.ao_trade(t)
        t0 = time.perf_counter()
        for t in trades[corte:]:
            vp.registrar_trade(t)
            motor.ao_trade(t)
        dt = time.perf_counter() - t0
        us = dt * 1e6 / amostra
        blocos = sum(len(b) for b in motor._blocos) + len(motor._reservatorio)
        print(f"  {n:>10,}  {dt:10.3f}  {amostra / dt:12,.0f}  {us:12.2f}"
              f"  {len(motor._janela_dominancia):>10,}  {len(motor._reservatorio):>9,}"
              f"  {len(motor._maiores_qty):>9,}  {blocos:>7,}   {_veredito(amostra / dt)}")
        del motor, vp, trades
    print("\n  PLANO no us/ev da cauda e CONSTANTE nas 4 colunas de tamanho = estado do")
    print("  motor nao cresce com a duracao da sessao.")


def _carregar_versao_do_git(ref: str):
    """Le fluxopro/motor/sinais.py COMMITADO em `ref` e o executa como modulo a
    parte, para as duas versoes coexistirem no mesmo processo.

    Nao mexe na arvore de trabalho (nada de stash) — o repositorio pode ter
    outras frentes editando outros arquivos ao mesmo tempo.
    """
    try:
        r = subprocess.run(
            ["git", "show", f"{ref}:fluxopro/motor/sinais.py"],
            capture_output=True, text=True, encoding="utf-8",
        )
    except OSError as e:
        print(f"  (A/B indisponivel: {e})")
        return None
    if r.returncode != 0:
        print(f"  (A/B indisponivel: git show {ref} falhou)")
        return None
    nome = "sinais_git_" + "".join(c if c.isalnum() else "_" for c in ref)
    mod = types.ModuleType(nome)
    mod.__file__ = f"<git:{ref}:fluxopro/motor/sinais.py>"
    # `@dataclass` resolve anotacoes por `sys.modules[cls.__module__]`: sem
    # registrar o modulo antes do exec, o decorador estoura com NoneType.
    sys.modules[nome] = mod
    exec(compile(r.stdout, mod.__file__, "exec"), mod.__dict__)
    return mod


def _rodar_motor_de(mod, trades: list[Trade]) -> float:
    """Uma passada cronometrada com `perf_counter`.

    NAO use `process_time` aqui: no Windows a granularidade dele e 15,6 ms, e
    uma passada de 25.000 trades leva ~200 ms — 13 tiques, ou seja ~7% de ruido
    de quantizacao sozinho, mais do que a diferenca que este estagio existe
    para medir. `perf_counter` tem resolucao de nanossegundos e paga o preco de
    contar o tempo fora da CPU; o antidoto para isso e repetir e olhar o
    MINIMO, que e o que `bench_ab` faz.
    """
    vp = VolumeProfile()
    motor = mod.MotorSinais(SYMBOL, vp, mod.ConfigMotorSinais())
    gc.collect()
    t0 = time.perf_counter()
    for t in trades:
        vp.registrar_trade(t)
        motor.ao_trade(t)
    dt = time.perf_counter() - t0
    del motor, vp
    return dt


def _bytecode_por_evento(mod, trades: list[Trade]) -> float:
    """Opcodes executados DENTRO do modulo do motor, por trade.

    Determinista: mesma entrada, mesmo numero. E o unico jeito de responder
    "esta correcao reintroduziu custo por evento?" numa maquina com outras seis
    frentes rodando — cronometro nenhum resolve isso (o A/B por relogio mediu
    razoes pareadas de 0,78x a 1,55x para o MESMO par de versoes).

    Conta so os frames cujo arquivo e o do motor: `VolumeProfile.registrar_trade`
    e identica nas duas versoes e so diluiria a diferenca.
    """
    arquivo = mod.__file__
    contagem = 0

    def local(frame, evento, arg):
        nonlocal contagem
        if evento == "opcode":
            contagem += 1
        return local

    def global_(frame, evento, arg):
        if evento == "call" and frame.f_code.co_filename == arquivo:
            frame.f_trace_opcodes = True
            return local
        return None

    vp = VolumeProfile()
    motor = mod.MotorSinais(SYMBOL, vp, mod.ConfigMotorSinais())
    sys.settrace(global_)
    try:
        for t in trades:
            vp.registrar_trade(t)
            motor.ao_trade(t)
    finally:
        sys.settrace(None)
    return contagem / len(trades)


def bench_ab(n: int, repeticoes: int, ref: str) -> None:
    """A/B da arvore contra a versao commitada, alternadas no mesmo processo."""
    print(f"\n{'=' * 92}")
    print(f"5. A/B — arvore x `{ref}`, {repeticoes} repeticoes ALTERNADAS, {n:,} trades cada")
    print(f"{'=' * 92}")
    base = _carregar_versao_do_git(ref)
    if base is None:
        return
    import fluxopro.motor.sinais as arvore

    trades = _tape(n)
    tempos = {"commitada": [], "arvore": []}
    # ordem ALTERNADA dentro do par: metade das repeticoes comeca pela arvore,
    # para nenhuma das duas herdar sistematicamente o cache quente da outra.
    for i in range(repeticoes):
        if i % 2:
            tempos["arvore"].append(_rodar_motor_de(arvore, trades))
            tempos["commitada"].append(_rodar_motor_de(base, trades))
        else:
            tempos["commitada"].append(_rodar_motor_de(base, trades))
            tempos["arvore"].append(_rodar_motor_de(arvore, trades))

    print(f"  {'versao':>10}  {'melhor s':>9}  {'melhor ev/s':>12}  {'melhor us/ev':>12}"
          f"  {'mediana ev/s':>13}  {'pior ev/s':>11}")
    melhores = {}
    for rotulo in ("commitada", "arvore"):
        v = sorted(tempos[rotulo])
        melhores[rotulo] = v[0]
        mediana = v[len(v) // 2]
        print(f"  {rotulo:>10}  {v[0]:9.3f}  {n / v[0]:12,.0f}  {v[0] * 1e6 / n:12.2f}"
              f"  {n / mediana:13,.0f}  {n / v[-1]:11,.0f}")
    razao = melhores["arvore"] / melhores["commitada"]
    delta_us = (melhores["arvore"] - melhores["commitada"]) * 1e6 / n
    # Razao PAREADA: cada repeticao roda as duas versoes coladas, entao boa
    # parte do ruido da maquina cai na divisao. A mediana das razoes pareadas
    # e o estimador que resiste a uma maquina ocupada; o melhor-a-melhor so
    # vale quando a maquina esta quieta — e a distancia entre a coluna
    # `melhor ev/s` e a coluna `pior ev/s` diz qual dos dois casos e este.
    pares = sorted(a / c for c, a in zip(tempos["commitada"], tempos["arvore"]))
    razao_par = pares[len(pares) // 2]
    print()
    print("  custo por evento da arvore sobre a commitada:")
    print(f"    melhor x melhor .............. {razao:.3f}x ({delta_us:+.3f} us/ev)")
    print(f"    mediana das razoes pareadas .. {razao_par:.3f}x "
          f"(faixa {pares[0]:.3f}x a {pares[-1]:.3f}x)")
    print("  Criterio: <= 1,05 nos DOIS = sem custo por evento reintroduzido.")
    print(f"  {'OK' if max(razao, razao_par) <= 1.05 else 'REGRESSAO'}")

    curto = trades[: min(len(trades), 20_000)]
    ops_base = _bytecode_por_evento(base, curto)
    ops_arv = _bytecode_por_evento(arvore, curto)
    print()
    print(f"  BYTECODE EXECUTADO no motor, por trade ({len(curto):,} trades, determinista):")
    print(f"    commitada .................... {ops_base:9.2f} opcodes/ev")
    print(f"    arvore ....................... {ops_arv:9.2f} opcodes/ev")
    print(f"    razao ........................ {ops_arv / ops_base:9.3f}x "
          f"({ops_arv - ops_base:+.2f} opcodes/ev)")
    print("  Este e o numero que nao depende da maquina. Criterio: <= 1,05.")
    print(f"  {'OK' if ops_arv / ops_base <= 1.05 else 'REGRESSAO'}")


def perfil(n: int) -> None:
    print(f"\n{'=' * 92}")
    print(f"cPROFILE — motor isolado, {n:,} trades, top 12 por tempo proprio")
    print(f"{'=' * 92}")
    trades = _tape(n)
    pr = cProfile.Profile()
    pr.enable()
    _rodar_motor(trades)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(12)
    print("\n".join(s.getvalue().splitlines()[4:24]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200_000, help="trades no motor isolado")
    ap.add_argument("--escala-base", type=int, default=25_000)
    ap.add_argument("--escala-dobras", type=int, default=5)
    ap.add_argument("--pipeline-n", type=int, default=40_000, help="passos do simulador")
    ap.add_argument("--taxa", type=float, default=TAXA_PICO_TRADES_S)
    ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--so-escala", action="store_true")
    ap.add_argument("--so-isolado", action="store_true")
    ap.add_argument("--so-sessao", action="store_true")
    ap.add_argument("--ab", action="store_true", help="A/B contra a versao commitada")
    ap.add_argument("--so-ab", action="store_true")
    ap.add_argument("--ab-ref", default="HEAD")
    ap.add_argument("--ab-n", type=int, default=200_000)
    ap.add_argument("--ab-repeticoes", type=int, default=5)
    ap.add_argument("--sessao-base", type=int, default=50_000)
    ap.add_argument("--sessao-dobras", type=int, default=4)
    args = ap.parse_args()

    print(f"BARRA: {BARRA_EV_S:,} eventos/s (pico do WDO).")
    if args.so_escala:
        bench_escalonamento(args.escala_base, args.escala_dobras)
        return
    if args.so_isolado:
        bench_isolado(args.n)
        return
    if args.so_sessao:
        bench_sessao_longa(args.sessao_base, args.sessao_dobras)
        return
    if args.so_ab:
        bench_ab(args.ab_n, args.ab_repeticoes, args.ab_ref)
        return
    bench_isolado(args.n)
    bench_escalonamento(args.escala_base, args.escala_dobras)
    bench_pipeline(args.pipeline_n, args.taxa)
    bench_sessao_longa(args.sessao_base, args.sessao_dobras)
    if args.ab:
        bench_ab(args.ab_n, args.ab_repeticoes, args.ab_ref)
    if args.perfil:
        perfil(min(args.n, 50_000))


if __name__ == "__main__":
    main()
