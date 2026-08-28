"""Fecha o dia: le trades+log gravados, compara contra o historico do banco,
pede uma leitura consultiva ao Claude (CLI) e grava tudo em SQLite.

Rodar depois que o gravador ja fechou o dia (arquivo .gz existe). Pensado
para entrar no final de scripts/publicar_pregao_dia.cmd.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fluxopro.aprendizado import banco, padroes
from fluxopro.aprendizado.consultor_llm import gerar_analise_consultiva
from fluxopro.aprendizado.metricas_dia import calcular_metricas_dia


def _achar_arquivo_trades(pasta_dia: Path) -> Path | None:
    for nome in ("trades.csv.gz", "trades.csv"):
        candidato = pasta_dia / nome
        if candidato.exists():
            return candidato
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simbolo", default="WDOU26")
    parser.add_argument("--data", required=True, help="AAAA-MM-DD")
    parser.add_argument("--raiz-dados", default=str(RAIZ / "dados"))
    parser.add_argument("--log", default=None, help="default: logs/pregao_<data>.log")
    parser.add_argument("--banco", default=str(RAIZ / "dados_aprendizado" / "asg.db"))
    parser.add_argument("--sem-llm", action="store_true", help="pula a chamada ao Claude CLI")
    args = parser.parse_args()

    pasta_dia = Path(args.raiz_dados) / args.simbolo / args.data
    caminho_trades = _achar_arquivo_trades(pasta_dia)
    if caminho_trades is None:
        print(f"sem trades gravados para {args.simbolo} {args.data} em {pasta_dia}", file=sys.stderr)
        return 1

    caminho_log = Path(args.log) if args.log else RAIZ / "logs" / f"pregao_{args.data}.log"

    metricas = calcular_metricas_dia(args.simbolo, args.data, caminho_trades, caminho_log)

    conexao = banco.conectar(Path(args.banco))
    historico_anterior = [h for h in banco.historico(conexao, args.simbolo) if h["data"] != args.data]
    desvios = padroes.comparar_contra_historico(metricas, historico_anterior)

    analise = None
    if not args.sem_llm:
        analise = gerar_analise_consultiva(metricas, desvios)

    banco.gravar_sessao(conexao, metricas, analise)

    print(f"{args.simbolo} {args.data}: {metricas.n_trades} trades, volume {metricas.volume_total}, "
          f"delta {metricas.delta_volume}")
    anomalos = [d for d in desvios if d.anomalo]
    if anomalos:
        print(f"{len(anomalos)} metrica(s) fora do padrao historico: " + ", ".join(d.nome for d in anomalos))
    if analise:
        print("--- leitura consultiva ---")
        print(analise)
    elif not args.sem_llm:
        print("(sem leitura consultiva -- claude CLI indisponivel ou sem resposta)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
