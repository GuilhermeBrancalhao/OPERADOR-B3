from __future__ import annotations

import gzip
import json
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
) -> AmostraFeatures:
    return AmostraFeatures(
        timestamp_ns=timestamp_ns,
        symbol=symbol,
        price_ticks=price,
        estado=estado,
        direcao=direcao,
        features={"delta": price - 100},
        qualidade_origem={"feed": "OK"},
        alvo_preco_ticks=alvo,
        invalidacao_preco_ticks=invalidacao,
    )


def ler(caminho):
    with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def particao(tmp_path, symbol="WDOQ26", data="2026-08-24"):
    return tmp_path / symbol / data


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


def test_particiona_por_simbolo_e_data_utc_e_declara_shadow_sem_promocao(tmp_path):
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
        assert manifesto["colecoes"] == {
            "features": "features.jsonl.gz",
            "labels": "labels.jsonl.gz",
        }


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
