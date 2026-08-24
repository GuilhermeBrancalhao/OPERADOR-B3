from __future__ import annotations

import gzip
import json
from pathlib import Path

from scripts.auditoria_asg import auditar_ausencia_ordens, auditar_particoes_shadow


def escrever(path: Path, texto: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")


def test_detecta_order_send_e_equivalentes_mas_respeita_allowlist_fechada(tmp_path):
    escrever(tmp_path / "fluxopro" / "adaptador.py", "def x(mt5):\n    return mt5.order_send({})\n")
    escrever(tmp_path / "fluxopro" / "broker.py", "def x(api):\n    return api.submit_order({})\n")
    escrever(tmp_path / "fluxopro" / "pt.py", "def x(api):\n    return api.enviar_ordem({})\n")
    escrever(
        tmp_path / "tests" / "test_auditoria_asg.py",
        "def mutacao(mt5):\n    return mt5.order_send({})\n",
    )

    achados, n = auditar_ausencia_ordens(tmp_path)
    assert n == 3
    assert {(a.caminho, a.codigo) for a in achados} == {
        ("fluxopro/adaptador.py", "API_ORDEM"),
        ("fluxopro/broker.py", "API_ORDEM"),
        ("fluxopro/pt.py", "API_ORDEM"),
    }


def test_detecta_getattr_literal_dinamico_e_constante_de_execucao(tmp_path):
    escrever(
        tmp_path / "x.py",
        "def a(mt5, nome):\n"
        "    getattr(mt5, 'order_send')({})\n"
        "    getattr(mt5, nome)({})\n"
        "    return mt5.TRADE_ACTION_DEAL\n",
    )
    achados, _ = auditar_ausencia_ordens(tmp_path, allowlist_testes=())
    assert {a.codigo for a in achados} == {
        "API_ORDEM_DINAMICA",
        "API_CORRETORA_DINAMICA",
        "CONSTANTE_ORDEM",
    }


def test_detecta_referencia_a_api_mesmo_antes_da_chamada(tmp_path):
    escrever(tmp_path / "x.py", "def a(mt5):\n    callback = mt5.order_send\n    return callback\n")
    achados, _ = auditar_ausencia_ordens(tmp_path, allowlist_testes=())
    assert [(a.codigo, a.linha) for a in achados] == [("API_ORDEM", 2)]


def _particao_valida(raiz: Path) -> Path:
    pasta = raiz / "WDOQ26" / "2026-08-24"
    pasta.mkdir(parents=True)
    manifesto = {
        "schema_versao": 1,
        "modo": "shadow",
        "promocao_automatica": False,
        "symbol": "WDOQ26",
        "data": "2026-08-24",
        "colecoes": {
            "features": "features.jsonl.gz",
            "labels": "labels.jsonl.gz",
        },
    }
    (pasta / "shadow_manifest.json").write_text(json.dumps(manifesto), encoding="utf-8")
    with gzip.open(pasta / "features.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"id_amostra": "a", "promocao_automatica": False}) + "\n")
    with gzip.open(pasta / "labels.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"id_amostra": "a"}) + "\n")
    return pasta


def test_auditoria_confirma_colecoes_e_arquivos_esperados(tmp_path):
    _particao_valida(tmp_path)
    achados, n = auditar_particoes_shadow(tmp_path)
    assert achados == []
    assert n == 1


def test_auditoria_reprova_arquivo_ausente_label_orfao_e_promocao(tmp_path):
    pasta = _particao_valida(tmp_path)
    (pasta / "labels.jsonl.gz").unlink()
    manifesto = json.loads((pasta / "shadow_manifest.json").read_text(encoding="utf-8"))
    manifesto["promocao_automatica"] = True
    (pasta / "shadow_manifest.json").write_text(json.dumps(manifesto), encoding="utf-8")

    achados, _ = auditar_particoes_shadow(tmp_path)
    assert {a.codigo for a in achados} == {"PROMOCAO_AUTOMATICA", "ARQUIVO_AUSENTE"}


def test_auditoria_reprova_label_sem_feature_da_mesma_particao(tmp_path):
    pasta = _particao_valida(tmp_path)
    with gzip.open(pasta / "labels.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps({"id_amostra": "orfao"}) + "\n")
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert [a.codigo for a in achados] == ["LABEL_ORFAO"]


def test_auditoria_nao_ignora_particao_sem_manifesto(tmp_path):
    pasta = tmp_path / "WDOQ26" / "2026-08-24"
    pasta.mkdir(parents=True)
    achados, n = auditar_particoes_shadow(tmp_path)
    assert n == 1
    assert [a.codigo for a in achados] == ["MANIFESTO_AUSENTE"]
