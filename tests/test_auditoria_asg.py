from __future__ import annotations

import gzip
import inspect
import json
from pathlib import Path

from fluxopro.shadow import AmostraFeatures, ConfigShadow, SidecarShadow
from scripts import auditoria_asg
from scripts.auditoria_asg import (
    auditar_ausencia_ordens,
    auditar_particoes_shadow,
    auditar_repositorio,
    gerar_relatorios,
)


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


def test_guardrail_detecta_alias_reflexao_dict_eval_endpoint_e_import_dinamico(tmp_path):
    escrever(
        tmp_path / "adversarial.py",
        "import MetaTrader5 as origem\n"
        "import importlib\n"
        "def x(nome, http):\n"
        "    a = origem\n"
        "    getattr(a, 'order_' + 'send')\n"
        "    getattr(a, nome)\n"
        "    a.__getattribute__(nome)\n"
        "    vars(a)[nome]\n"
        "    a.__dict__[nome]\n"
        "    eval(nome)\n"
        "    http.post('/orders')\n"
        "    importlib.import_module(nome)\n",
    )
    achados, _ = auditar_ausencia_ordens(tmp_path, allowlist_testes=())
    codigos = {a.codigo for a in achados}
    assert {
        "API_ORDEM_DINAMICA",
        "API_CORRETORA_DINAMICA",
        "EXECUCAO_DINAMICA",
        "ENDPOINT_ORDEM",
        "IMPORT_DINAMICO_CORRETORA",
    } <= codigos


def _particao_valida(raiz: Path) -> Path:
    t0 = 1_777_939_200_000_000_000  # 2026-05-05 00:00 UTC
    lado = SidecarShadow(
        raiz,
        ConfigShadow(intervalo_amostra_ns=100_000_000_000, horizontes_s=(1,)),
    )
    lado.observar(AmostraFeatures(t0, "WDOQ26", 100, "NENHUM"))
    lado.observar(AmostraFeatures(t0 + 1_000_000_000, "WDOQ26", 101, "NENHUM"))
    lado.finalizar()
    return raiz / "2026-05-05" / "WDOQ26"


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
    with gzip.open(pasta / "labels.jsonl.gz", "rt", encoding="utf-8") as f:
        label = json.loads(next(f))
    label["id_amostra"] = "orfao"
    with gzip.open(pasta / "labels.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps(label) + "\n")
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert [a.codigo for a in achados] == ["LABEL_ORFAO"]


def test_auditoria_nao_ignora_particao_sem_manifesto(tmp_path):
    pasta = tmp_path / "2026-08-24" / "WDOQ26"
    pasta.mkdir(parents=True)
    achados, n = auditar_particoes_shadow(tmp_path)
    assert n == 1
    assert [a.codigo for a in achados] == ["MANIFESTO_AUSENTE"]


def test_schema_estrito_reprova_registro_apenas_com_id(tmp_path):
    pasta = _particao_valida(tmp_path)
    with gzip.open(pasta / "features.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write('{"id_amostra":"enganoso"}\n')
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert "REGISTRO_SCHEMA" in {a.codigo for a in achados}


def test_json_nan_e_reprovado_antes_do_schema(tmp_path):
    pasta = _particao_valida(tmp_path)
    with gzip.open(pasta / "features.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write('{"id_amostra":"x","score":NaN}\n')
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert "JSONL_INVALIDO" in {a.codigo for a in achados}


def test_auditoria_reprova_horizonte_fracionario_em_arquivo_adulterado(tmp_path):
    pasta = _particao_valida(tmp_path)
    with gzip.open(pasta / "features.jsonl.gz", "rt", encoding="utf-8") as f:
        feature = json.loads(next(f))
    feature["horizontes_s"] = [1.5]
    with gzip.open(pasta / "features.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps(feature) + "\n")
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert {"REGISTRO_SCHEMA", "HORIZONTES_DIVERGENTES"} <= {
        a.codigo for a in achados
    }


def test_auditoria_reprova_toque_forjado_na_admissao(tmp_path):
    pasta = _particao_valida(tmp_path)
    with gzip.open(pasta / "labels.jsonl.gz", "rt", encoding="utf-8") as f:
        label = json.loads(next(f))
    label.update(
        alvo_timestamp_ns=label["timestamp_amostra_ns"],
        alvo_atingido=True,
        duracao_ate_alvo_ns=0,
        primeiro_toque="ALVO",
    )
    with gzip.open(pasta / "labels.jsonl.gz", "wt", encoding="utf-8") as f:
        f.write(json.dumps(label) + "\n")
    achados, _ = auditar_particoes_shadow(tmp_path)
    assert any(
        a.codigo == "REGISTRO_SCHEMA" and "nao pode tocar na admissao" in a.detalhe
        for a in achados
    )


def test_shadow_ausente_e_skipped_explicito_e_nao_aprovacao_vazia(tmp_path, capsys):
    relatorio = auditar_repositorio(tmp_path)
    assert relatorio.status_shadow == "SKIPPED"
    assert relatorio.particoes_shadow_inspecionadas == 0
    assert auditoria_asg.main(["--raiz", str(tmp_path)]) == 0
    assert "SHADOW: SKIPPED" in capsys.readouterr().out


def test_report_json_e_markdown_documentam_status_e_human_gate(tmp_path):
    relatorio = auditar_repositorio(tmp_path)
    report_json, report_md = gerar_relatorios(relatorio, tmp_path / "report")
    dados = json.loads(report_json.read_text(encoding="utf-8"))
    texto = report_md.read_text(encoding="utf-8")
    assert dados["status"] == "SKIPPED"
    assert dados["status_shadow"] == "SKIPPED"
    assert dados["politica_promocao"]["status"] == "BLOQUEADA_POR_PADRAO"
    for trecho in (
        "20 pregões", "10.000 amostras", "walk-forward", "5%",
        "configuração versionada", "rollback testado", "aprovação humana",
    ):
        assert trecho in texto


def test_auditoria_jsonl_e_generator_e_relacao_exata_usa_indice_lateral():
    assert inspect.isgeneratorfunction(auditoria_asg._iter_jsonl_gz)
    fonte = Path(auditoria_asg.__file__).read_text(encoding="utf-8")
    assert "sqlite3" in fonte
    assert "readline(MAX_LINHA_BYTES + 1)" in fonte


def test_workflow_ci_executa_guardrail_testes_e_publica_reports():
    raiz = Path(__file__).resolve().parent.parent
    workflow = (raiz / ".github" / "workflows" / "auditoria-asg.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/auditoria_asg.py" in workflow
    assert "tests/test_shadow_*.py" in workflow
    assert "tests/test_sem_execucao.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "audit-report/" in workflow
