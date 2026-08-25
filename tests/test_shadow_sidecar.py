from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timezone

import pytest

from fluxopro.core.eventos import Side
from fluxopro.shadow import (
    AmostraFeatures,
    BufferShadowCheio,
    ConfigShadow,
    SidecarShadow,
)


S = 1_000_000_000
T0 = int(datetime(2026, 8, 24, 12, tzinfo=timezone.utc).timestamp() * S)


def amostra(
    timestamp_ns: int,
    price: int = 100,
    estado: str = "NENHUM",
    *,
    symbol: str = "WDOQ26",
    direcao: Side | None = None,
    alvo: int | None = None,
    invalidacao: int | None = None,
    qualidade: dict | None = None,
) -> AmostraFeatures:
    return AmostraFeatures(
        timestamp_ns=timestamp_ns,
        symbol=symbol,
        price_ticks=price,
        estado=estado,
        direcao=direcao,
        features={"delta": price - 100},
        qualidade_origem=qualidade if qualidade is not None else {"feed": "OK"},
        alvo_preco_ticks=alvo,
        invalidacao_preco_ticks=invalidacao,
    )


def ler(caminho):
    with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def particao(tmp_path, symbol="WDOQ26", data="2026-08-24"):
    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    return runs[0] / data / symbol


def test_amostra_a_cada_segundo_sem_mudancas_reiniciarem_a_cadencia(tmp_path):
    sidecar = SidecarShadow(tmp_path, ConfigShadow(horizontes_s=(1,)))

    assert sidecar.observar(amostra(T0))
    assert not sidecar.observar(amostra(T0 + 100_000_000))
    assert sidecar.observar(amostra(T0 + 200_000_000, estado="PRE_SINAL"))
    assert sidecar.observar(amostra(T0 + 300_000_000, estado="CONFIRMADO"))
    assert sidecar.observar(amostra(T0 + 400_000_000, estado="NA_REGIAO"))
    assert sidecar.observar(amostra(T0 + S, estado="NA_REGIAO"))

    sidecar.flush()
    features = ler(particao(tmp_path) / "features.jsonl.gz")
    assert [f["motivos"] for f in features] == [
        ["PERIODICA"],
        ["PRE_SINAL"],
        ["CONFIRMACAO"],
        ["MUDANCA_ESTADO"],
        ["PERIODICA"],
    ]


def test_periodica_usa_bucket_fixo_sem_deriva_e_inicio_preserva_confirmacao(tmp_path):
    lado = SidecarShadow(tmp_path, ConfigShadow(horizontes_s=(1,)))
    assert lado.observar(amostra(T0 + 200_000_000, estado="CONFIRMADO"))
    assert lado.observar(amostra(T0 + 1_900_000_000, estado="CONFIRMADO"))
    assert lado.observar(amostra(T0 + 2_000_000_000, estado="CONFIRMADO"))
    lado.flush()
    features = ler(particao(tmp_path) / "features.jsonl.gz")
    assert features[0]["motivos"] == ["PERIODICA", "CONFIRMACAO"]
    assert [f["timestamp_ns"] for f in features] == [
        T0 + 200_000_000,
        T0 + 1_900_000_000,
        T0 + 2_000_000_000,
    ]


def test_tick_depois_do_horizonte_fecha_mas_nao_contamina_label(tmp_path):
    config = ConfigShadow(
        intervalo_amostra_ns=100 * S,
        horizontes_s=(1,),
        tolerancia_qualidade_ns=300_000_000,
    )
    sidecar = SidecarShadow(tmp_path, config)
    sidecar.observar(amostra(T0, 100))
    sidecar.observar(amostra(T0 + 800_000_000, 110))
    sidecar.observar(amostra(T0 + 1_200_000_000, 50))

    sidecar.flush()
    labels = ler(particao(tmp_path) / "labels.jsonl.gz")
    assert len(labels) == 1
    label = labels[0]
    assert label["price_final_ticks"] == 110
    assert label["max_price_ticks"] == 110
    assert label["min_price_ticks"] == 100
    assert label["mfe_ticks"] == 10
    assert label["mae_ticks"] == 0
    assert label["referencia_excursao"] == "HIPOTESE_BUY"
    assert label["timestamp_final_observado_ns"] == T0 + 800_000_000
    assert label["qualidade"] == "COMPLETA"
    assert label["causal"] is True


def test_mfe_mae_alvo_invalidacao_duracao_e_qualidade(tmp_path):
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1,)),
    )
    sidecar.observar(
        amostra(T0, 100, "CONFIRMADO", direcao=Side.BUY, alvo=103, invalidacao=98)
    )
    sidecar.observar(amostra(T0 + 200_000_000, 104, "CONFIRMADO"))
    sidecar.observar(amostra(T0 + 400_000_000, 97, "CONFIRMADO"))
    sidecar.observar(amostra(T0 + S, 102, "CONFIRMADO"))

    sidecar.flush()
    label = ler(particao(tmp_path) / "labels.jsonl.gz")[0]
    assert label["retorno_ticks"] == 2
    assert label["retorno_direcional_ticks"] == 2
    assert label["mfe_ticks"] == 4
    assert label["mae_ticks"] == 3
    assert label["alvo_atingido"] is True
    assert label["invalidacao_atingida"] is True
    assert label["duracao_ate_alvo_ns"] == 200_000_000
    assert label["duracao_ate_invalidacao_ns"] == 400_000_000
    assert label["duracao_observada_ns"] == S
    assert label["qualidade"] == "COMPLETA"
    assert label["qualidade_origem"] == {"feed": "OK"}
    assert label["primeiro_toque"] == "ALVO"


def test_qualidade_feed_e_agregada_durante_horizonte_sem_lookahead(tmp_path):
    lado = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1,)),
    )
    lado.observar(
        amostra(
            T0,
            qualidade={"state": "connected", "latency_ns": 10, "sequence_gaps": 0},
        )
    )
    lado.observar(
        amostra(
            T0 + 500_000_000,
            qualidade={"state": "degraded", "latency_ns": 30, "sequence_gaps": 2},
        )
    )
    # Esta qualidade esta depois de 1s: fecha a janela, mas nao entra nela.
    lado.observar(
        amostra(
            T0 + 1_200_000_000,
            qualidade={"state": "error", "latency_ns": 999, "sequence_gaps": 99},
        )
    )
    lado.flush()

    qualidade = ler(particao(tmp_path) / "labels.jsonl.gz")[0][
        "qualidade_feed_horizonte"
    ]
    assert qualidade == {
        "n_observacoes": 2,
        "n_sem_snapshot": 0,
        "estado_pior": "DEGRADADA",
        "estados": {"OK": 1, "DEGRADADA": 1, "ERRO": 0, "DESCONHECIDA": 0},
        "latencia_min_ns": 10,
        "latencia_max_ns": 30,
        "latencia_media_ns": 20.0,
        "sequence_gaps_max": 2,
        "missing_events_max": None,
        "duplicates_max": None,
        "delayed_events_max": None,
        "unknown_aggressors_max": None,
    }


@pytest.mark.parametrize(
    "direcao,alvo,invalidacao",
    [
        (Side.BUY, 100, 98),
        (Side.BUY, 103, 100),
        (Side.SELL, 100, 103),
        (Side.SELL, 98, 100),
        (None, 103, 98),
    ],
)
def test_niveis_buy_sell_invertidos_ou_sem_direcao_sao_rejeitados(
    direcao, alvo, invalidacao
):
    with pytest.raises(ValueError):
        amostra(T0, 100, direcao=direcao, alvo=alvo, invalidacao=invalidacao)


def test_timestamp_de_admissao_nunca_conta_como_toque(tmp_path):
    lado = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1,)),
    )
    lado.observar(amostra(T0, 100, direcao=Side.BUY, alvo=103, invalidacao=98))
    lado.observar(amostra(T0, 103))  # mesmo timestamp: nao e futuro
    lado.observar(amostra(T0 + 100_000_000, 103))
    lado.observar(amostra(T0 + S, 101))
    lado.flush()
    label = ler(particao(tmp_path) / "labels.jsonl.gz")[0]
    assert label["alvo_timestamp_ns"] == T0 + 100_000_000
    assert label["duracao_ate_alvo_ns"] == 100_000_000


@pytest.mark.parametrize(
    "eventos,esperado",
    [
        ([(100_000_000, 103), (200_000_000, 98)], "ALVO"),
        ([(100_000_000, 98), (200_000_000, 103)], "INVALIDACAO"),
        ([(100_000_000, 103), (100_000_000, 98)], "EMPATE"),
        ([(100_000_000, 101)], "NENHUM"),
    ],
)
def test_primeiro_toque_explicito(tmp_path, eventos, esperado):
    lado = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1,)),
    )
    lado.observar(amostra(T0, 100, direcao=Side.BUY, alvo=103, invalidacao=98))
    for deslocamento, preco in eventos:
        lado.observar(amostra(T0 + deslocamento, preco))
    lado.observar(amostra(T0 + S, 100))
    lado.flush()
    label = ler(particao(tmp_path) / "labels.jsonl.gz")[0]
    assert label["primeiro_toque"] == esperado


def test_horizontes_exigem_inteiros_e_json_rejeita_nao_finitos(tmp_path):
    with pytest.raises(ValueError, match="inteiros positivos"):
        ConfigShadow(horizontes_s=(1, 3.5))
    with pytest.raises(ValueError, match="NaN|infinito"):
        AmostraFeatures(T0, "WDOQ26", 100, "NENHUM", features={"x": math.nan})
    with pytest.raises(ValueError, match="NaN|infinito"):
        AmostraFeatures(
            T0, "WDOQ26", 100, "NENHUM", qualidade_origem={"latency": math.inf}
        )


def test_cinco_horizontes_padrao_sao_emitidos_somente_quando_conhecidos(tmp_path):
    sidecar = SidecarShadow(tmp_path, ConfigShadow(intervalo_amostra_ns=100 * S))
    sidecar.observar(amostra(T0, 100))
    for segundo in (1, 3, 5, 15, 30):
        sidecar.observar(amostra(T0 + segundo * S, 100 + segundo))
        sidecar.flush()
        labels = ler(particao(tmp_path) / "labels.jsonl.gz")
        assert [r["horizonte_s"] for r in labels] == [h for h in (1, 3, 5, 15, 30) if h <= segundo]
    assert sidecar.n_pendentes == 0


def test_fechar_censura_sem_inventar_o_futuro(tmp_path):
    sidecar = SidecarShadow(
        tmp_path, ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1, 3))
    )
    sidecar.observar(amostra(T0, 100))
    sidecar.observar(amostra(T0 + 500_000_000, 101))
    sidecar.fechar()

    labels = ler(particao(tmp_path) / "labels.jsonl.gz")
    assert {r["qualidade"] for r in labels} == {"CENSURADA"}
    assert {r["duracao_observada_ns"] for r in labels} == {500_000_000}


def test_fila_pendente_e_limitada_e_descarte_fica_visivel_no_feature(tmp_path):
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(
            intervalo_amostra_ns=1,
            horizontes_s=(30,),
            max_pendentes_por_simbolo=2,
        ),
    )
    for i in range(5):
        sidecar.observar(amostra(T0 + i, 100 + i))

    assert sidecar.n_pendentes == 2
    assert sidecar.pendentes_por_simbolo == {"WDOQ26": 2}
    assert sidecar.amostras_sem_label_por_capacidade == 3
    sidecar.flush()
    features = ler(particao(tmp_path) / "features.jsonl.gz")
    assert [f["label_admitida"] for f in features] == [True, True, False, False, False]


def test_particiona_por_data_e_simbolo_utc_e_declara_shadow_sem_promocao(tmp_path):
    t_fim = int(datetime(2026, 8, 24, 23, 59, 59, tzinfo=timezone.utc).timestamp() * S)
    sidecar = SidecarShadow(
        tmp_path, ConfigShadow(intervalo_amostra_ns=1, horizontes_s=(1,))
    )
    sidecar.observar(amostra(t_fim, symbol="WDOQ26"))
    sidecar.observar(amostra(t_fim + S, symbol="WDOQ26"))
    sidecar.observar(amostra(t_fim + S, symbol="WINQ26"))
    sidecar.fechar()

    for symbol, data in (
        ("WDOQ26", "2026-08-24"),
        ("WDOQ26", "2026-08-25"),
        ("WINQ26", "2026-08-25"),
    ):
        pasta = particao(tmp_path, symbol, data)
        assert (pasta / "features.jsonl.gz").is_file()
        assert (pasta / "labels.jsonl.gz").is_file()
        manifesto = json.loads((pasta / "shadow_manifest.json").read_text(encoding="utf-8"))
        assert manifesto["modo"] == "shadow"
        assert manifesto["promocao_automatica"] is False
        assert manifesto["config_versao"] == "shadow-v2"
        assert manifesto["politica_promocao"]["aplicacao_automatica"] is False
        assert manifesto["colecoes"] == {
            "features": "features.jsonl.gz",
            "labels": "labels.jsonl.gz",
        }
        assert (pasta / "report.json").is_file()
        assert (pasta / "report.md").is_file()


def test_replays_repetidos_ficam_isolados_por_run_e_sem_ids_duplicados(tmp_path):
    for run_id in ("replay-001", "replay-002"):
        sidecar = SidecarShadow(
            tmp_path,
            ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1,)),
            run_id=run_id,
        )
        sidecar.observar(amostra(T0, 100))
        sidecar.observar(amostra(T0 + S, 101))
        sidecar.finalizar()

    ids_por_run = []
    for run_id in ("replay-001", "replay-002"):
        pasta = tmp_path / "runs" / run_id / "2026-08-24" / "WDOQ26"
        ids = {registro["id_amostra"] for registro in ler(pasta / "features.jsonl.gz")}
        ids_por_run.append(ids)
        run = json.loads(
            (tmp_path / "runs" / run_id / "run.json").read_text(encoding="utf-8")
        )
        assert run["status"] == "FINALIZED"
        assert json.loads((pasta / "report.json").read_text(encoding="utf-8"))[
            "run_id"
        ] == run_id
    assert ids_por_run[0].isdisjoint(ids_por_run[1])


def test_run_id_finalizado_e_imutavel(tmp_path):
    sidecar = SidecarShadow(tmp_path, run_id="imutavel-1")
    sidecar.observar(amostra(T0))
    sidecar.finalizar()
    with pytest.raises(FileExistsError, match="imutavel"):
        SidecarShadow(tmp_path, run_id="imutavel-1")


def test_rejeita_evento_fora_de_ordem_e_limita_numero_de_simbolos(tmp_path):
    sidecar = SidecarShadow(tmp_path, ConfigShadow(max_simbolos=1, horizontes_s=(1,)))
    sidecar.observar(amostra(T0))
    with pytest.raises(ValueError, match="fora de ordem"):
        sidecar.observar(amostra(T0 - 1))
    with pytest.raises(OverflowError, match="max_simbolos"):
        sidecar.observar(amostra(T0, symbol="WINQ26"))


def test_observar_apenas_enfileira_e_backpressure_permite_flush_e_retry(tmp_path):
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(
            intervalo_amostra_ns=1,
            horizontes_s=(1,),
            max_pendentes_por_simbolo=1,
            max_registros_buffer=2,
        ),
    )
    sidecar.observar(amostra(T0))
    assert sidecar.n_registros_buffer == 1
    assert list(tmp_path.iterdir()) == [], "ingestao por tick nao pode tocar no disco"

    with pytest.raises(BufferShadowCheio, match="flush"):
        sidecar.observar(amostra(T0 + S, 101))
    # O evento recusado nao avancou o relogio: depois do flush ele e repetivel.
    assert sidecar.flush() == 1
    assert sidecar.observar(amostra(T0 + S, 101))
    assert sidecar.n_registros_buffer == 2  # label de 1s + feature periodica
    sidecar.flush()


def test_reset_censura_e_impede_label_de_cruzar_sessoes(tmp_path):
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100 * S, horizontes_s=(1, 3)),
    )
    sidecar.observar(amostra(T0, 100))
    assert sidecar.resetar_sessao("WDOQ26") == 2
    # Nova sessao pode recomecar o relogio sem completar labels anteriores.
    sidecar.observar(amostra(T0 - 10 * S, 999))
    sidecar.finalizar()

    labels = ler(particao(tmp_path) / "labels.jsonl.gz")
    antigos = [r for r in labels if r["price_inicial_ticks"] == 100]
    assert len(antigos) == 2
    assert {r["qualidade"] for r in antigos} == {"CENSURADA"}
    assert {r["price_final_ticks"] for r in antigos} == {100}


def test_mappings_de_features_sao_profundamente_imutaveis():
    origem = {"book": {"bids": [1, 2]}, "tags": {"a", "b"}}
    registro = AmostraFeatures(T0, "WDOQ26", 100, "NENHUM", features=origem)
    origem["book"]["bids"].append(3)

    assert registro.features["book"]["bids"] == (1, 2)
    with pytest.raises(TypeError):
        registro.features["book"]["novo"] = 1
    with pytest.raises(AttributeError):
        registro.features["book"]["bids"].append(3)


def test_sidecar_nao_expoe_api_de_promocao_automatica(tmp_path):
    nomes = {nome.lower() for nome in dir(SidecarShadow(tmp_path))}
    assert not {
        nome
        for nome in nomes
        if any(radical in nome for radical in ("promov", "promotion", "auto_apply"))
    }


def test_modulos_shadow_nao_dependem_de_pyside6():
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent / "fluxopro" / "shadow"
    imports = []
    for caminho in raiz.glob("*.py"):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), str(caminho))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                imports.extend(alias.name for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                imports.append(no.module)
    assert not [nome for nome in imports if nome == "PySide6" or nome.startswith("PySide6.")]
