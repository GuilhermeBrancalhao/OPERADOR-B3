"""Custo do `InferidorMBP` NO EIXO QUE DOMINA: a TAXA DO TAPE com preço cravado.

Por que este arquivo existe
===========================
O mesmo defeito quadrático já mudou de casa três vezes (`detectores.py`,
`motor/sinais.py`, `inferencia_mbp.py`). Na terceira, a correção anterior
otimizou e MEDIU o eixo errado: variou a LARGURA do book (quantos níveis
distintos existem pendurados) e publicou uma curva plana. A largura é
justamente o eixo que um índice por preço já resolvia.

O eixo que dói no WDO é o oposto da largura. O WDO negocia rotineiramente em
2-3 preços com spread de 1 tick: tudo — quedas pendentes e negócios em buffer —
cai no MESMO bucket. O que enche esse bucket é a TAXA DO TAPE, porque o bucket
guarda o que couber em `janela_reconciliacao_ns` (300 ms de fábrica): a 10.000
negócios/s são 3.000 itens vivos por bucket.

Logo: mede-se a taxa, com preço concentrado, e olha-se o custo POR PASSO. Se o
custo por passo sobe quando a taxa sobe, o custo total é O(n × taxa) — é o
defeito quadrático, onde quer que ele esteja morando.

A métrica principal é CONTAGEM, não relógio
===========================================
`visitas/passo` = quantos candidatos a reconciliação o módulo percorre para
processar um passo. É determinística, não depende de máquina nem de carga, e é
exatamente a grandeza que o defeito faz crescer. O tempo de parede entra junto
(melhor de N repetições), mas como coadjuvante: numa máquina compartilhada ele
varia 4x entre execuções idênticas, e foi confiando nele que a rodada anterior
publicou uma curva plana no eixo errado.

O eixo que NENHUM benchmark deste repositório varria: DURAÇÃO
=============================================================
A auditoria R4 achou a 5a casa do mesmo defeito — `_registrar_preco` empilhava
sem dedup e sem teto — e ela atravessou uma onda inteira de builders que
estavam profilando ESTE módulo. Não passou por descuido: passou porque todo
benchmark daqui varre TAXA ou TAMANHO DE ESTRUTURA, com no máximo 40.000
passos, e mede MÉDIA. Enquanto o heap inflava para 2,4 milhões de entradas,
o us/passo médio CAÍA (33,54 -> 23,01): a média melhorava enquanto o sistema
apodrecia, porque o trabalho extra ficava represado num evento raro em vez de
diluído em todos.

Por isso o estágio 6 (`retencao`) mede três coisas que a média esconde:

* **(a) DURAÇÃO** — minutos de pregão simulado a 5.000 ev/s, não milhares de
  passos.
* **(b) RETENÇÃO** — `len` das estruturas internas ao fim, confrontado com o
  número de níveis VIVOS que elas deveriam descrever. Se a razão cresce com o
  tempo, há vazamento, esteja a média onde estiver.
* **(c) LATÊNCIA DE CAUDA** — p99 e MÁXIMO por evento, jamais a média. Foi um
  único evento de 244 ms — no tick em que o topo do book esvazia, ou seja, no
  rompimento — que a média de 23 us escondia.

Quem for otimizar este módulo: rode `retencao` ANTES e DEPOIS. Uma melhora de
vazão com retenção subindo não é melhora, é dívida trocando de lugar.

Uso:
    python bench_inferencia.py                 # os 4 regimes + eixo antigo + retenção
    python bench_inferencia.py taxa            # só o eixo que dói
    python bench_inferencia.py retencao        # duração + retenção + cauda
    python bench_inferencia.py taxa OUTRO.py   # A/B contra outra implementação
    python bench_inferencia.py retencao OUTRO.py
                                               # (ex.: a versão de `git show HEAD:`)
"""

from __future__ import annotations

import gc
import importlib.util
import random
import sys
import time
from collections import deque

from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Side, Trade
from fluxopro.microestrutura.livro_mbo import LivroMBO

SYMBOL = "WDOFUT"
BASE = 1_700_000_000_000_000_000
BID = 10_000
ASK = 10_001  # spread de 1 tick — o regime real do WDO
BARRA = 10_000  # eventos/s que o produto precisa sustentar
REPETICOES = 3

TAXAS = (500, 1_000, 2_000, 5_000, 10_000)
# Folga do veredito de retenção: o teto do heap tem um piso constante
# (compactar um heap minúsculo não paga o custo). Ver `_PISO_TETO_HEAP`.
_PISO_ESPERADO = 128


# ----------------------------------------------------------------------
# instrumentação — conta os candidatos percorridos, sem tocar em produção
# ----------------------------------------------------------------------
class _DequeContada(deque):
    """Bucket do índice que conta cada item percorrido."""

    def __init__(self, contador: list[int]) -> None:
        super().__init__()
        self._contador = contador

    def __iter__(self):
        contador = self._contador
        for item in super().__iter__():
            contador[0] += 1
            yield item


class _IndiceContado(dict):
    """Índice que cria buckets contados. `setdefault` é o único ponto de criação."""

    def __init__(self, contador: list[int]) -> None:
        super().__init__()
        self._contador = contador

    def setdefault(self, chave, _padrao):  # noqa: D102 - contrato de dict
        bucket = dict.get(self, chave)
        if bucket is None:
            bucket = _DequeContada(self._contador)
            self[chave] = bucket
        return bucket


def _nomes_dos_indices(inf) -> tuple[str, str]:
    """Aceita a nomenclatura nova (`_por_nivel`) e a antiga (`_por_preco`)."""
    if hasattr(inf, "_trades_por_nivel"):
        return "_trades_por_nivel", "_pendentes_por_nivel"
    return "_trades_por_preco", "_pendentes_por_preco"


def _instrumentar(inf) -> list[int]:
    contador = [0]
    for nome in _nomes_dos_indices(inf):
        assert not getattr(inf, nome), "instrumentar só faz sentido no índice vazio"
        setattr(inf, nome, _IndiceContado(contador))
    return contador


def _carregar_inferidor(caminho: str | None):
    """Classe `InferidorMBP` — a do pacote, ou a de um arquivo alternativo."""
    if caminho is None:
        from fluxopro.microestrutura.inferencia_mbp import InferidorMBP

        return InferidorMBP
    spec = importlib.util.spec_from_file_location("_inferencia_alternativa", caminho)
    assert spec is not None and spec.loader is not None, caminho
    modulo = importlib.util.module_from_spec(spec)
    # `@dataclass(slots=True)` recria a classe e procura o módulo dela em
    # `sys.modules`; sem registrar antes, o exec_module estoura.
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo.InferidorMBP


# ----------------------------------------------------------------------
# O EIXO QUE DOMINA — taxa do tape, preço cravado, spread de 1 tick
# ----------------------------------------------------------------------
def _uma_passada(Inferidor, taxa: int, n_passos: int, escolher_agressor, contar: bool):
    """Um passo = uma leitura de book (bid caindo) + um negócio no MESMO preço."""
    livro = LivroMBO(SYMBOL)
    inf = Inferidor(SYMBOL, livro)
    contador = _instrumentar(inf) if contar else [0]
    ts = BASE
    intervalo = max(1, int(1e9 / taxa))
    rng = random.Random(4)
    qty = 10**9
    inf.ao_snapshot(
        BookSnapshot(ts, SYMBOL, (BookLevel(BID, qty, 1),), (BookLevel(ASK, qty, 1),))
    )
    gc.collect()
    t0 = time.perf_counter()
    for i in range(n_passos):
        ts += intervalo
        qty -= 2
        inf.ao_snapshot(
            BookSnapshot(ts, SYMBOL, (BookLevel(BID, qty, 1),), (BookLevel(ASK, 10**9, 1),))
        )
        inf.ao_trade(Trade(ts, SYMBOL, BID, 1, escolher_agressor(rng), f"t{i}"))
    dt = time.perf_counter() - t0
    return dt, contador[0], len(inf._pendentes), len(inf._trades)


def _regime(Inferidor, rotulo: str, sub: str, n_passos: int, escolher_agressor) -> None:
    print(f"\n{rotulo}")
    print(f"  {sub}")
    print(
        f"\n{'tape/s':>9} {'visitas/passo':>14} {'fator':>7} "
        f"{'us/passo':>10} {'passos/s':>11} {'pend':>7} {'buf':>7}  veredito"
    )
    base: float | None = None
    for taxa in TAXAS:
        _, visitas, pend, buf = _uma_passada(Inferidor, taxa, n_passos, escolher_agressor, True)
        melhor = min(
            _uma_passada(Inferidor, taxa, n_passos, escolher_agressor, False)[0]
            for _ in range(REPETICOES)
        )
        por_passo = visitas / n_passos
        fator = "" if base is None else f"{por_passo / base:.2f}x"
        if base is None:
            base = max(por_passo, 1e-9)
        passos_s = n_passos / melhor
        ok = "PASSA" if passos_s >= BARRA else "*** NAO PASSA ***"
        print(
            f"{taxa:>9,} {por_passo:>14.1f} {fator:>7} {1e6 / passos_s:>10.2f} "
            f"{passos_s:>11,.0f} {pend:>7,} {buf:>7,}  {ok}"
        )


def eixo_taxa(Inferidor, n_passos: int = 8_000) -> None:
    _regime(
        Inferidor,
        "1. TAPE 50/50 NO MESMO PREÇO (metade casa, metade vira buffer)",
        "regime real do WDO: bid caindo no topo, spread de 1 tick, preço cravado",
        n_passos,
        lambda rng: AgressorSide.SELL if rng.random() < 0.5 else AgressorSide.BUY,
    )
    _regime(
        Inferidor,
        "2. TAPE INTEIRO DO LADO QUE NÃO CASA (agressor de COMPRA, queda no BID)",
        "pior caso do casamento: nenhum negócio pode explicar nenhuma queda",
        n_passos,
        lambda rng: AgressorSide.BUY,
    )
    _regime(
        Inferidor,
        "3. TAPE INTEIRO DO LADO QUE CASA (agressor de VENDA, queda no BID)",
        "todo negócio casa, mas a queda é maior que o negócio: sobra pendência",
        n_passos,
        lambda rng: AgressorSide.SELL,
    )
    _regime(
        Inferidor,
        "4. AGRESSOR DESCONHECIDO (leilão / RLP) — candidato dos DOIS lados",
        "o caso em que a perna do lado não pode ser resolvida pela chave do índice",
        n_passos,
        lambda rng: AgressorSide.UNKNOWN,
    )


# ----------------------------------------------------------------------
# O EIXO ANTIGO — largura do book, para contraste
# ----------------------------------------------------------------------
def eixo_largura(Inferidor, n_negocios: int = 20_000) -> None:
    """A curva que a docstring antiga publicava. Plana — e é o eixo errado.

    Mantida aqui para que a comparação seja explícita: a largura do book NÃO é
    o que faz o custo explodir, e medi-la não prova nada sobre a barra.
    """
    print("\n5. EIXO ANTIGO — LARGURA DO BOOK (níveis distintos pendurados)")
    print("  negócios que não casam com nada, variando só quantos preços existem")
    print(f"\n{'niveis':>9} {'visitas/neg':>12} {'us/neg':>10} {'neg/s':>12}  veredito")
    for n_niveis in (50, 200, 800, 3_000):
        livro = LivroMBO(SYMBOL)
        inf = Inferidor(SYMBOL, livro)
        contador = _instrumentar(inf)
        ts = BASE
        for i in range(n_niveis):
            inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (), (BookLevel(ASK + i, 100, 1),)))
            ts += 1
        for i in range(n_niveis):
            inf.ao_snapshot(BookSnapshot(ts, SYMBOL, (), (BookLevel(ASK + i, 40, 1),)))
            ts += 1
        contador[0] = 0
        gc.collect()
        t0 = time.perf_counter()
        for i in range(n_negocios):
            ts += 1
            inf.ao_trade(Trade(ts, SYMBOL, ASK - 500, 1, AgressorSide.BUY, f"n{i}"))
        dt = time.perf_counter() - t0
        eps = n_negocios / dt
        ok = "PASSA" if eps >= BARRA else "*** NAO PASSA ***"
        print(
            f"{n_niveis:>9,} {contador[0] / n_negocios:>12.1f} "
            f"{1e6 / eps:>10.2f} {eps:>12,.0f}  {ok}"
        )


# ----------------------------------------------------------------------
# O EIXO QUE NINGUÉM VARRIA — DURAÇÃO, RETENÇÃO E LATÊNCIA DE CAUDA
# ----------------------------------------------------------------------
MINUTOS = (1, 2, 4, 8, 16)
TAXA_RETENCAO = 5_000  # ev/s
ORCAMENTO_EVENTO_US = 200.0  # teto por evento da barra (100-200 us)


def _percentil(ordenados: list[float], q: float) -> float:
    if not ordenados:
        return 0.0
    idx = min(len(ordenados) - 1, max(0, int(round(q * (len(ordenados) - 1)))))
    return ordenados[idx]


def _tape_recarga(Inferidor, minutos: int) -> dict[str, float]:
    """Pregão longo com um nível de FUNDO piscando `0 -> 300 -> 0` sem parar.

    É o regime real do WDO e é exatamente o que o produto existe para detectar
    (recarga). O topo permanece OCUPADO durante todo o tape, então a poda
    preguiçosa pela cabeça do heap nunca cobra nada — a dívida fica represada.
    No último evento o topo esvazia: é aí que ela é cobrada de uma só vez, e é
    esse evento (o rompimento) que o p99/máximo revela e a média não.
    """
    livro = LivroMBO(SYMBOL)
    inf = Inferidor(SYMBOL, livro)
    ts = BASE
    intervalo = max(1, int(1e9 / TAXA_RETENCAO))
    n_eventos = minutos * 60 * TAXA_RETENCAO
    fundo = BID - 5

    topo_qty = 10**9
    inf.ao_snapshot(
        BookSnapshot(ts, SYMBOL, (BookLevel(BID, topo_qty, 1),), (BookLevel(ASK, 10**9, 1),))
    )
    latencias: list[float] = []
    gc.collect()
    perf = time.perf_counter
    t0 = perf()
    for i in range(n_eventos):
        ts += intervalo
        # alterna 0 <-> 300 no nível de fundo: uma transição `0 -> qty` a cada
        # dois eventos, e é ela que chama `_registrar_preco`.
        qty_fundo = 300 if i % 2 == 0 else 0
        bids = (BookLevel(BID, topo_qty, 1),)
        if qty_fundo:
            bids = bids + (BookLevel(fundo, qty_fundo, 1),)
        e0 = perf()
        inf.ao_snapshot(BookSnapshot(ts, SYMBOL, bids, (BookLevel(ASK, 10**9, 1),)))
        latencias.append((perf() - e0) * 1e6)
    dt_tape = perf() - t0

    heap_antes = len(inf._heap_bids)

    # O EVENTO DO ROMPIMENTO: o topo esvazia e o fundo some junto. Agora
    # `melhor_bid` precisa descartar todo o backlog num único evento.
    # São DOIS eventos, e o segundo é o que dói: no primeiro, `melhor_bid`
    # ainda encontra os níveis vivos no topo do heap (a distância do topo é
    # medida ANTES de a queda ser aplicada), então a dívida só é cobrada na
    # PRÓXIMA consulta — quando toda a cabeça já está morta. Medir só o
    # primeiro evento devolve 47 us e esconde o defeito inteiro.
    ts += intervalo
    e0 = perf()
    inf.ao_snapshot(
        BookSnapshot(ts, SYMBOL, (BookLevel(BID - 20, 50, 1),), (BookLevel(ASK, 10**9, 1),))
    )
    lat_a = (perf() - e0) * 1e6
    ts += intervalo
    e0 = perf()
    inf.ao_snapshot(
        BookSnapshot(ts, SYMBOL, (BookLevel(BID - 20, 10, 1),), (BookLevel(ASK, 10**9, 1),))
    )
    lat_b = (perf() - e0) * 1e6
    lat_rompimento = max(lat_a, lat_b)
    latencias.append(lat_a)
    latencias.append(lat_b)

    vivos = sum(1 for (lado, _), q in inf._qty_por_nivel.items() if lado is Side.BUY and q > 0)
    ordenados = sorted(latencias)
    return {
        "eventos": float(n_eventos),
        "heap": float(heap_antes),
        "vivos": float(max(vivos, 1)),
        "p50": _percentil(ordenados, 0.50),
        "p99": _percentil(ordenados, 0.99),
        "max": ordenados[-1],
        "rompimento": lat_rompimento,
        "media": sum(latencias) / len(latencias),
        "vazao": n_eventos / dt_tape,
    }


def _ruido_da_maquina(n: int = 200_000) -> dict[str, float]:
    """Piso de ruído: a MESMA medição, sobre trabalho de tamanho FIXO.

    Sem isto o `max us` da tabela é ilegível. Nesta máquina, com outros
    processos pesados em paralelo, um laço aritmético sem estrutura de dado
    NENHUMA mede 86.735 us no pior evento — puro escalonamento do SO. Quem ler
    um pico de 80 ms na tabela sem esta linha vai atribuir ao código o que é da
    máquina, e quem "corrigir" esse pico vai declarar vitória sobre nada.

    O número atribuível ao CÓDIGO é a coluna `rompimento`, que é um evento
    determinístico e identificado: nele, e só nele, a dívida represada no heap
    vence de uma vez. Compare `rompimento` com o orçamento; leia `max` e `p99`
    com o desconto desta linha.
    """
    perf = time.perf_counter
    latencias = []
    x = 0
    gc.collect()
    for _ in range(n):
        e0 = perf()
        for _ in range(40):
            x = (x * 31 + 7) % 1000003
        latencias.append((perf() - e0) * 1e6)
    ordenados = sorted(latencias)
    return {
        "p50": _percentil(ordenados, 0.50),
        "p99": _percentil(ordenados, 0.99),
        "max": ordenados[-1],
    }


def eixo_retencao(Inferidor, minutos=MINUTOS) -> None:
    print("\n6. DURAÇÃO x RETENÇÃO x LATÊNCIA DE CAUDA (o eixo que escondeu a 5a casa)")
    print(f"  nível de fundo recarregando `0->300->0` a {TAXA_RETENCAO:,} ev/s;"
          " topo ocupado até o último evento")
    print("  a MÉDIA é o eixo amigável: ela CAI enquanto a estrutura infla."
          " Olhe heap/vivos e rompimento.")
    ruido = _ruido_da_maquina()
    print(
        f"  piso de ruido desta maquina (trabalho fixo, sem estrutura):"
        f" p50 {ruido['p50']:.1f} us | p99 {ruido['p99']:.1f} us | max {ruido['max']:,.1f} us"
    )
    print("  => `max` e `p99` abaixo carregam esse ruido; a coluna ATRIBUIVEL ao"
          " codigo e `rompimento`.")
    print(
        f"\n{'min':>4} {'eventos':>11} {'len(heap)':>11} {'vivos':>6} {'heap/vivo':>10} "
        f"{'media us':>9} {'p99 us':>9} {'max us':>12} {'rompim. us':>12} {'ev/s':>10}  veredito"
    )
    for m in minutos:
        r = _tape_recarga(Inferidor, m)
        # Dois vereditos independentes, porque um esconde o outro:
        # retenção (heap tem de descrever níveis vivos) e cauda (nenhum evento
        # pode estourar o orçamento da barra).
        vaza = r["heap"] > 4 * r["vivos"] + _PISO_ESPERADO
        # O veredito de cauda usa o evento ATRIBUÍVEL (o rompimento), não o
        # `max` bruto: numa máquina carregada o `max` é escalonamento do SO, e
        # julgar por ele torna o benchmark um gerador de falso alarme.
        estoura = r["rompimento"] > 1_000.0
        if vaza and estoura:
            ok = "*** VAZA E ESTOURA ***"
        elif vaza:
            ok = "*** VAZA ***"
        elif estoura:
            ok = "*** ESTOURA A CAUDA ***"
        else:
            ok = "PASSA"
        print(
            f"{m:>4} {r['eventos']:>11,.0f} {r['heap']:>11,.0f} {r['vivos']:>6,.0f} "
            f"{r['heap'] / r['vivos']:>10,.1f} {r['media']:>9.2f} {r['p99']:>9.2f} "
            f"{r['max']:>12,.1f} {r['rompimento']:>12,.1f} {r['vazao']:>10,.0f}  {ok}"
        )
    print(f"\n  orçamento por evento da barra: {ORCAMENTO_EVENTO_US:.0f} us."
          " Alvo do rompimento: < 1.000 us (1 ms).")
    print("  ANTES da correcao do heap (R5), 16 min de tape: len(heap) 2.400.001"
          " para 1 nivel vivo, rompimento 5.328.847 us (5,3 s).")


def main() -> None:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    alternativa = sys.argv[2] if len(sys.argv) > 2 else None
    Inferidor = _carregar_inferidor(alternativa)
    print("=" * 92)
    print("InferidorMBP — custo por passo. Barra do produto: 10.000 eventos/s.")
    print("Um passo = 1 leitura de book + 1 negócio (2 eventos).")
    print(f"implementacao: {alternativa or 'fluxopro.microestrutura.inferencia_mbp'}")
    print("visitas/passo = candidatos percorridos na reconciliacao (deterministico).")
    print("=" * 92)
    if alvo in ("tudo", "taxa"):
        eixo_taxa(Inferidor)
    if alvo in ("tudo", "largura"):
        eixo_largura(Inferidor)
    if alvo in ("tudo", "retencao"):
        eixo_retencao(Inferidor)
    print()


if __name__ == "__main__":
    main()
