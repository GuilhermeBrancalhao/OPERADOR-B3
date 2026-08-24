"""Relatórios offline, auditáveis e sem qualquer promoção automática."""

from __future__ import annotations

import gzip
import json
import os
from collections import Counter
from pathlib import Path

from fluxopro.shadow.governanca import politica_promocao_manifesto


def gerar_relatorio_particao(
    particao: Path,
    *,
    run_id: str,
) -> tuple[Path, Path]:
    """Resume uma partição fechada; só lê dados já persistidos."""
    features = list(_iter_jsonl(particao / "features.jsonl.gz"))
    labels = list(_iter_jsonl(particao / "labels.jsonl.gz"))
    manifesto = json.loads(
        (particao / "shadow_manifest.json").read_text(encoding="utf-8")
    )
    motivos = Counter(
        motivo for registro in features for motivo in registro.get("motivos", [])
    )
    estados = Counter(str(registro.get("estado")) for registro in features)
    qualidades = Counter(str(registro.get("qualidade")) for registro in labels)
    horizontes = Counter(str(registro.get("horizonte_s")) for registro in labels)
    retornos = [
        registro["retorno_direcional_ticks"]
        for registro in labels
        if isinstance(registro.get("retorno_direcional_ticks"), int)
    ]
    amostras_sem_label_por_capacidade = sum(
        registro.get("label_admitida") is False for registro in features
    )
    bloqueios = ["MIN_20_PREGOES", "MIN_10000_AMOSTRAS", "WALK_FORWARD"]
    payload = {
        "status": "FINALIZED",
        "run_id": run_id,
        "data": manifesto["data"],
        "symbol": manifesto["symbol"],
        "schema_versao": manifesto["schema_versao"],
        "config_versao": manifesto["config_versao"],
        "amostras": {
            "total": len(features),
            "admitidas_para_label": sum(
                registro.get("label_admitida") is True for registro in features
            ),
            "sem_label_por_capacidade": amostras_sem_label_por_capacidade,
            "motivos": dict(sorted(motivos.items())),
            "estados": dict(sorted(estados.items())),
        },
        "labels": {
            "total": len(labels),
            "qualidade": dict(sorted(qualidades.items())),
            "horizontes_s": dict(sorted(horizontes.items(), key=lambda item: int(item[0]))),
            "retorno_direcional_medio_ticks": (
                sum(retornos) / len(retornos) if retornos else None
            ),
            "alvo_atingido": sum(
                registro.get("alvo_atingido") is True for registro in labels
            ),
            "invalidacao": sum(
                registro.get("invalidacao_atingida") is True for registro in labels
            ),
        },
        "qualidade_feed": _resumir_feed(features),
        "promocao": {
            "elegivel_para_revisao_humana": False,
            "aplicacao_automatica": False,
            "bloqueios": bloqueios,
            "politica": politica_promocao_manifesto(),
        },
    }
    report_json = particao / "report.json"
    report_md = particao / "report.md"
    _json_atomico(report_json, payload)
    linhas = [
        f"# Shadow — {payload['symbol']} — {payload['data']}",
        "",
        f"- Execução: `{run_id}`",
        f"- Status: **{payload['status']}**",
        f"- Features: {len(features)}",
        f"- Labels: {len(labels)}",
        f"- Descartes por capacidade: {amostras_sem_label_por_capacidade}",
        f"- Qualidade dos labels: {dict(sorted(qualidades.items()))}",
        f"- Cobertura por horizonte: {payload['labels']['horizontes_s']}",
        "",
        "## Promoção",
        "",
        "**BLOQUEADA.** Shadow não altera produção e exige 20 pregões, 10.000 "
        "amostras, walk-forward, intervalo de confiança, guardrails, aprovação "
        "humana, configuração versionada e rollback testado.",
    ]
    _texto_atomico(report_md, "\n".join(linhas) + "\n")
    return report_json, report_md


def _iter_jsonl(caminho: Path):
    with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                yield json.loads(linha)


def _resumir_feed(features: list[dict]) -> dict:
    estados = Counter()
    latencias: list[float] = []
    sem_snapshot = 0
    for registro in features:
        qualidade = registro.get("qualidade_origem") or {}
        if not qualidade:
            sem_snapshot += 1
        estado = qualidade.get("state", qualidade.get("feed", "DESCONHECIDA"))
        estados[str(estado).upper()] += 1
        latencia = qualidade.get("latency_ns", qualidade.get("latencia_ns"))
        if isinstance(latencia, (int, float)) and not isinstance(latencia, bool):
            latencias.append(float(latencia))
    return {
        "estados": dict(sorted(estados.items())),
        "sem_snapshot": sem_snapshot,
        "latencia_media_ns": sum(latencias) / len(latencias) if latencias else None,
        "latencia_max_ns": max(latencias) if latencias else None,
    }


def _json_atomico(caminho: Path, payload: dict) -> None:
    _texto_atomico(
        caminho,
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )


def _texto_atomico(caminho: Path, texto: str) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    os.replace(temporario, caminho)
