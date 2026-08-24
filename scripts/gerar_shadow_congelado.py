"""Gera a pequena partição determinística usada pelo gate shadow do CI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from fluxopro.core.eventos import Side
from fluxopro.shadow import AmostraFeatures, ConfigShadow, SidecarShadow


T0 = 1_777_939_200_000_000_000


def gerar(saida: Path, run_id: str) -> Path:
    if saida.exists():
        raise FileExistsError(
            f"destino deve ser novo para preservar execucao imutavel: {saida}"
        )
    lado = SidecarShadow(
        saida,
        ConfigShadow(intervalo_amostra_ns=1_000_000_000, horizontes_s=(1, 3)),
        run_id=run_id,
    )
    for segundo, preco, estado in (
        (0, 100, "NENHUM"),
        (1, 101, "PRE_SINAL"),
        (2, 103, "CONFIRMADO"),
        (3, 102, "CONFIRMADO"),
    ):
        lado.observar(
            AmostraFeatures(
                timestamp_ns=T0 + segundo * 1_000_000_000,
                symbol="WDOQ26",
                price_ticks=preco,
                estado=estado,
                direcao=Side.BUY if segundo else None,
                features={"delta": preco - 100, "fonte": "CI_FROZEN_V1"},
                qualidade_origem={
                    "state": "connected",
                    "latency_ns": 1_000_000,
                    "sequence_gaps": 0,
                },
                alvo_preco_ticks=105 if segundo else None,
                invalidacao_preco_ticks=99 if segundo else None,
            )
        )
    lado.finalizar()
    return lado.run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--run-id", default="ci-frozen-v1")
    args = parser.parse_args(argv)
    print(gerar(args.saida, args.run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
