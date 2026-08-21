"""R4 - (F) relogio de MAXIMO nunca esquece; (G) rotacao da dedup vira peneira."""
from __future__ import annotations
import sys, time
from unittest.mock import patch

MS = 1_000_000; S = 1_000_000_000

def f_relogio():
    from fluxopro.dados.mt5 import _RelogioServidor
    print("\nF) RELOGIO DE MAXIMO x REGRESSAO DO SERVIDOR MT5")
    print("   cenario: corretora troca de servidor / NTP do lado deles recua o relogio")
    rel = _RelogioServidor()
    local = 1_700_000_000 * S
    OFF = 3 * 3600 * S  # servidor em GMT+3

    def obs(off_real, idade_ms=5):
        # tick visto agora, gerado ha `idade_ms`; servidor = local + off_real
        with patch("time.time_ns", return_value=local):
            rel.observar(local + off_real - idade_ms * MS)

    for _ in range(50):
        obs(OFF)
    print(f"   offset apos 50 ticks com servidor em GMT+3 : {rel.offset_ns/S:+.3f} s   (verdade: {OFF/S:+.3f} s)")

    # REGRESSAO: o servidor recua 2 horas (troca de servidor da corretora)
    OFF2 = 1 * 3600 * S
    for _ in range(5_000):
        obs(OFF2)
    erro = rel.offset_ns - OFF2
    print(f"   servidor RECUA para GMT+1; 5.000 ticks novos observados")
    print(f"   offset apos a regressao                    : {rel.offset_ns/S:+.3f} s   (verdade agora: {OFF2/S:+.3f} s)")
    print(f"   ERRO PERMANENTE do relogio derivado        : {erro/S:+.3f} s  = {erro/MS:,.0f} ms")
    print(f"   janela de reconciliacao do InferidorMBP    : 300 ms")
    print(f"   -> o erro e' {erro/MS/300:,.0f}x a janela. 100% das execucoes viram CANCELAMENTO.")
    print(f"   nao ha decaimento, nem janela, nem resync, nem reset: _offset_ns so SOBE (mt5.py:215-219)")

    # regressao pequena, ainda letal
    rel2 = _RelogioServidor()
    for _ in range(50):
        with patch("time.time_ns", return_value=local):
            rel2.observar(local + 500*MS)
    for _ in range(50):
        with patch("time.time_ns", return_value=local):
            rel2.observar(local + 100*MS)
    print(f"\n   regressao MINIMA (400 ms, um ajuste de NTP banal):")
    print(f"     offset preso em {rel2.offset_ns/MS:,.0f} ms, verdade 100 ms -> erro {rel2.offset_ns/MS-100:,.0f} ms > janela de 300 ms")

def g_dedup():
    from fluxopro.microestrutura.detectores import _MapaProcedencia, LIMITE_CHAVES_RASTREADAS
    from fluxopro.core.eventos import Side
    print("\nG) ROTACAO DA DEDUP (teto FIFO de %d chaves)" % LIMITE_CHAVES_RASTREADAS)
    for n_niveis in (100, 2_000, 4_096, 5_000, 8_000, 20_000):
        m = _MapaProcedencia()
        reemissoes = 0
        VOLTAS = 3
        for volta in range(VOLTAS):
            for p in range(n_niveis):
                ch = (Side.BUY, p)
                ja = m.obter(ch)
                if volta > 0 and (ja is None or not ja.sinalizado):
                    reemissoes += 1
                m.de(ch)
                proc = m.obter(ch)
                if proc is not None:
                    proc.sinalizado = True
        total = n_niveis * (VOLTAS - 1)
        pct = 100.0 * reemissoes / total if total else 0
        marca = "  <-- PENEIRA" if pct > 50 else ""
        print(f"   niveis distintos em rotacao {n_niveis:>7,}  re-emissoes {reemissoes:>8,} de {total:>8,}  = {pct:5.1f}%{marca}")
    print("   WDO tem ~2-4 mil niveis de preco distintos tocados num pregao;")
    print("   a chave e' (lado, preco) -> 2 lados => o espaco de chaves e' ~2x isso.")

if __name__=="__main__":
    w=sys.argv[1] if len(sys.argv)>1 else "fg"
    if "f" in w: f_relogio()
    if "g" in w: g_dedup()
