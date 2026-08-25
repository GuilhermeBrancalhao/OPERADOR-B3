"""Benchmark reproduzível da integração ASG-like.

Compara o mesmo fluxo determinístico em três configurações: baseline com
observabilidade de feed, MakerProxy e matriz/decisão completas. O JSON bruto
permite auditar as 30 execuções sem depender da tabela resumida.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fluxopro.app.config import ConfigOperacao, FonteDados
from fluxopro.app.sessao_fluxo import SessaoFluxo
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade


SYMBOL = "WDOFUT"


@dataclass(frozen=True)
class Resultado:
    variante: str
    repeticao: int
    eventos: int
    segundos: float
    eventos_s: float
    micros_evento: float


def _eventos(n_passos: int):
    eventos = []
    base = 10_000
    for i in range(n_passos):
        ts = 1_780_000_000_000_000_000 + i * 200_000
        lado = AgressorSide.BUY if i % 2 else AgressorSide.SELL
        preco = base + ((i // 40) % 5) - 2
        eventos.append(Trade(ts, SYMBOL, preco, 1 + i % 8, lado, f"b{i}"))
        bids = tuple(BookLevel(preco - k - 1, 70 + (i + k) % 20, 1) for k in range(5))
        asks = tuple(BookLevel(preco + k + 1, 68 + (i + 2 * k) % 20, 1) for k in range(5))
        eventos.append(BookSnapshot(ts, SYMBOL, bids, asks))
    return tuple(eventos)


VARIANTES = {
    "baseline_observavel": dict(
        ligar_feed_quality=True,
        ligar_maker_proxy=False,
        ligar_leitura_asg=False,
    ),
    "maker_proxy": dict(
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
        ligar_leitura_asg=False,
    ),
    "asg_completo": dict(
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
        ligar_leitura_asg=True,
    ),
}


def _rodar(variante: str, repeticao: int, eventos) -> Resultado:
    bus = Barramento()
    cfg = ConfigOperacao(
        symbol=SYMBOL,
        fonte=FonteDados.SIMULADOR,
        **VARIANTES[variante],
    )
    sessao = SessaoFluxo(bus, cfg)
    assert sessao.feed_monitor is not None
    sessao.feed_monitor.connected("fonte sintetica do benchmark pronta")
    gc.collect()
    inicio = time.perf_counter()
    for evento in eventos:
        bus.publicar(evento)
    segundos = time.perf_counter() - inicio
    sessao.finalizar(eventos[-1].timestamp_ns if eventos else 0)
    n = len(eventos)
    return Resultado(
        variante=variante,
        repeticao=repeticao,
        eventos=n,
        segundos=segundos,
        eventos_s=n / segundos,
        micros_evento=segundos * 1_000_000 / n,
    )


def _resumo(resultados: list[Resultado]) -> dict:
    por_variante = {}
    for nome in VARIANTES:
        linhas = [r for r in resultados if r.variante == nome]
        micros = [r.micros_evento for r in linhas]
        taxas = [r.eventos_s for r in linhas]
        por_variante[nome] = {
            "execucoes": len(linhas),
            "eventos_por_execucao": linhas[0].eventos,
            "eventos_s_mediana": statistics.median(taxas),
            "eventos_s_min": min(taxas),
            "micros_evento_p50": statistics.median(micros),
            "micros_evento_p95": statistics.quantiles(micros, n=100, method="inclusive")[94],
        }
    base = por_variante["baseline_observavel"]["micros_evento_p50"]
    maker = por_variante["maker_proxy"]["micros_evento_p50"]
    overhead = (maker / base - 1.0) * 100.0
    return {
        "barra_eventos_s": 10_000,
        "limite_overhead_maker_percent": 10.0,
        "variantes": por_variante,
        "overhead_maker_percent": overhead,
        "throughput_pass": por_variante["asg_completo"]["eventos_s_mediana"] >= 10_000,
        "maker_overhead_pass": overhead <= 10.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--passos", type=int, default=2_000)
    parser.add_argument("--execucoes", type=int, default=30)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()
    if args.passos <= 0 or args.execucoes < 2:
        parser.error("--passos deve ser > 0 e --execucoes >= 2")

    eventos = _eventos(args.passos)
    resultados = []
    # Intercalar reduz viés de aquecimento ou carga variável entre variantes.
    for repeticao in range(1, args.execucoes + 1):
        for variante in VARIANTES:
            resultados.append(_rodar(variante, repeticao, eventos))

    documento = {
        "schema": "operador-b3-benchmark-asg-v1",
        "passos": args.passos,
        "eventos_por_execucao": len(eventos),
        "execucoes_por_variante": args.execucoes,
        "resumo": _resumo(resultados),
        "medicoes": [asdict(r) for r in resultados],
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(documento, indent=2), encoding="utf-8")
    print(json.dumps(documento["resumo"], indent=2))
    return 0 if all(
        (
            documento["resumo"]["throughput_pass"],
            documento["resumo"]["maker_overhead_pass"],
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
