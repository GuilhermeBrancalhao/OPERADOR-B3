#!/usr/bin/env python
"""Audita as ascensoes oficiais do Ultra em um pregao completo.

O contador e por transicao ``NENHUMA -> COMPRA/VENDA`` do mesmo
``MotorSinalUltra`` usado pela interface. Quadros acesos nao sao tratados
como entradas. O replay e causal: os retornos sao calculados somente depois
do timestamp de cada ascensao.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import sys
from collections import Counter
from collections.abc import Mapping
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fluxopro.analytics.renko import FaseRenko  # noqa: E402
from fluxopro.app.config import ConfigOperacao, FonteDados  # noqa: E402
from fluxopro.app.montagem import OpcoesReplay, montar  # noqa: E402
from fluxopro.asg.sinal_ultra import (  # noqa: E402
    DirecaoUltra,
    EntradaSinalUltra,
    MotorSinalUltra,
)
from fluxopro.core.eventos import Side, Trade  # noqa: E402


def _side(value: object) -> Side | None:
    if isinstance(value, Side):
        return value
    if value in {"BUY", "COMPRA", "buy", "compra"}:
        return Side.BUY
    if value in {"SELL", "VENDA", "sell", "venda"}:
        return Side.SELL
    return None


def _side_mapping(mapping: object, *keys: str) -> Side | None:
    if not isinstance(mapping, Mapping):
        return None
    for key in keys:
        value = mapping.get(key)
        found = _side(value)
        if found is not None:
            return found
        if isinstance(value, dict):
            for nested in ("lado", "sentido", "comanda", "direction"):
                found = _side(value.get(nested))
                if found is not None:
                    return found
    return None


def _stats(values: list[float | int | None]) -> dict[str, object]:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return {"n": 0}
    return {
        "n": len(valid),
        "mean": round(statistics.mean(valid), 4),
        "median": round(statistics.median(valid), 4),
        "min": round(min(valid), 4),
        "max": round(max(valid), 4),
    }


def auditar(caminho: Path, simbolo: str, dia: date) -> dict[str, object]:
    config = ConfigOperacao(
        symbol=simbolo,
        fonte=FonteDados.REPLAY,
        ligar_leitura_asg=True,
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
    )
    montagem = montar(
        config,
        replay=OpcoesReplay(caminho=caminho, data=dia, velocidade="max"),
    )
    quadros: list[tuple[int, int]] = []
    episodes: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    previous = DirecaoUltra.NENHUMA
    counts: Counter[str] = Counter()
    motor = MotorSinalUltra()

    def on_trade(trade: Trade) -> None:
        nonlocal current, previous
        retrato = montagem.sessao.retrato_asg()
        if retrato is None or retrato.timestamp_ns != trade.timestamp_ns:
            return

        counts["retratos"] += 1
        if retrato.decisao.pre_sinal:
            counts["pre_sinais"] += 1
        if retrato.decisao.confirmacao:
            counts["confirmacoes"] += 1

        decisao_side = _side(retrato.decisao.direcao)
        macro_side = _side_mapping(retrato.leitura.macro, "lado", "sentido", "macro")
        micro_side = _side_mapping(
            retrato.leitura.micro, "comanda", "lado", "sentido", "micro"
        )
        aligned = (
            decisao_side is not None
            and macro_side is decisao_side
            and micro_side is decisao_side
        )
        if retrato.decisao.confirmacao and aligned:
            counts["confirmados_contexto_alinhado"] += 1

        target = (
            DirecaoUltra.COMPRA
            if retrato.decisao.confirmacao and decisao_side is Side.BUY
            else DirecaoUltra.VENDA
            if retrato.decisao.confirmacao and decisao_side is Side.SELL
            else DirecaoUltra.NENHUMA
        )
        maker = retrato.maker
        ultra = motor.atualizar(
            EntradaSinalUltra(
                timestamp_ns=trade.timestamp_ns,
                direcao_decisao_confirmada=target,
                fase_renko=FaseRenko.INDEFINIDA,
                direcao_renko=DirecaoUltra.NENHUMA,
                forca_maker=float(maker.pontuacao),
                confianca_maker_alta=float(maker.confianca) >= 0.60,
                contexto_alinhado=aligned,
            )
        )
        quadros.append((trade.timestamp_ns, trade.price))
        actual = ultra.direcao
        if actual is previous:
            return

        if current is not None:
            current["end_ts"] = trade.timestamp_ns
            current["duration_s"] = round(
                (trade.timestamp_ns - int(current["start_ts"])) / 1e9, 3
            )
        if actual is DirecaoUltra.NENHUMA:
            current = None
        else:
            current = {
                "start_ts": trade.timestamp_ns,
                "side": actual.value,
                "start_price": trade.price,
                "maker_percent": round(float(maker.percent), 4),
                "maker_confidence": round(float(maker.confianca), 4),
                "maker_feed_quality": round(float(maker.feed_quality), 4),
                "feed_state": retrato.feed_quality.state.value,
                "book_kind": retrato.feed_quality.book_kind.value,
                "decision_confidence": round(float(retrato.decisao.confianca), 4),
                "region_valid": bool(retrato.regiao.valida),
                "context_aligned": aligned,
                "blocks": list(retrato.decisao.bloqueios),
            }
            episodes.append(current)
        previous = actual

    montagem.barramento.assinar(Trade, on_trade, prioridade=999)
    montagem.fonte.iniciar()
    if current is not None and quadros:
        current["end_ts"] = quadros[-1][0]
        current["duration_s"] = round(
            (quadros[-1][0] - int(current["start_ts"])) / 1e9, 3
        )
    trades = montagem.sessao.contadores.n_trades_bus
    montagem.sessao.finalizar()

    timestamps = [item[0] for item in quadros]
    prices = [item[1] for item in quadros]
    for episode in episodes:
        horizons: dict[str, object] = {}
        start_ts = int(episode["start_ts"])
        start_price = int(episode["start_price"])
        for seconds in (1, 3, 5, 15):
            index = bisect.bisect_left(timestamps, start_ts + seconds * 1_000_000_000)
            if index >= len(prices):
                horizons[str(seconds)] = None
                continue
            raw_ticks = prices[index] - start_price
            signed_ticks = raw_ticks if episode["side"] == "compra" else -raw_ticks
            horizons[str(seconds)] = {
                "signed_ticks": signed_ticks,
                "raw_ticks": raw_ticks,
                "positive": signed_ticks > 0,
            }
        episode["horizons"] = horizons

    def horizon_stats(seconds: int) -> dict[str, object]:
        values = [
            item["horizons"][str(seconds)]["signed_ticks"]
            for item in episodes
            if item["horizons"].get(str(seconds)) is not None
        ]
        return {
            **_stats(values),
            "positive": sum(value > 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "zero": sum(value == 0 for value in values),
            "positive_pct": round(
                100.0 * sum(value > 0 for value in values) / max(len(values), 1), 2
            ),
        }

    return {
        "dia": str(dia),
        "simbolo": simbolo,
        "trades": trades,
        "formula_ultra": "decision-confirmada + macro/micro alinhados + persistencia 5s; Maker auxiliar; Renko fora do gate",
        "quadros": len(quadros),
        **dict(counts),
        "ultra_episodes": len(episodes),
        "episodes_by_side": dict(Counter(item["side"] for item in episodes)),
        "episode_duration_s": _stats([item.get("duration_s") for item in episodes]),
        "horizons_signed_ticks": {
            str(seconds): horizon_stats(seconds) for seconds in (1, 3, 5, 15)
        },
        "episode_details": episodes,
        "maker_feed_quality_at_activation": _stats(
            [item.get("maker_feed_quality") for item in episodes]
        ),
        "maker_percent_at_activation": _stats(
            [item.get("maker_percent") for item in episodes]
        ),
        "feed_states_at_activation": dict(
            Counter(item["feed_state"] for item in episodes)
        ),
        "book_kinds_at_activation": dict(
            Counter(item["book_kind"] for item in episodes)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arquivo", default="dados", type=Path)
    parser.add_argument("--simbolo", default="WDOU26")
    parser.add_argument("--data", default="2026-08-31")
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args()
    dia = date.fromisoformat(args.data)
    result = auditar(args.arquivo, args.simbolo, dia)
    output = args.saida or Path("outputs/auditoria_nexo_integracao") / (
        f"ultra_pregao_completo_{dia:%Y%m%d}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "episode_details"}, ensure_ascii=False, indent=2))
    print(f"relatorio={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
