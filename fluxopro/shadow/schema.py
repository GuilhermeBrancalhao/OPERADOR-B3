"""Schema v2 fechado para escritor e auditor compartilharem o mesmo contrato."""

from __future__ import annotations

import math
import re
from typing import Mapping

from fluxopro.shadow.governanca import politica_promocao_manifesto
from fluxopro.shadow.modelos import SCHEMA_VERSAO


FEATURE_KEYS = frozenset(
    {
        "schema_versao",
        "tipo",
        "id_amostra",
        "timestamp_ns",
        "symbol",
        "data",
        "price_ticks",
        "estado",
        "direcao",
        "motivos",
        "features",
        "qualidade_origem",
        "alvo_preco_ticks",
        "invalidacao_preco_ticks",
        "horizontes_s",
        "label_admitida",
        "modo",
        "promocao_automatica",
        "config_versao",
    }
)

LABEL_KEYS = frozenset(
    {
        "schema_versao",
        "tipo",
        "id_amostra",
        "symbol",
        "data_amostra",
        "timestamp_amostra_ns",
        "horizonte_s",
        "limite_horizonte_ns",
        "timestamp_final_observado_ns",
        "duracao_horizonte_ns",
        "duracao_observada_ns",
        "price_inicial_ticks",
        "price_final_ticks",
        "estado_na_amostra",
        "direcao_na_amostra",
        "alvo_preco_ticks",
        "invalidacao_preco_ticks",
        "min_price_ticks",
        "max_price_ticks",
        "retorno_ticks",
        "retorno_direcional_ticks",
        "mfe_ticks",
        "mae_ticks",
        "referencia_excursao",
        "alvo_atingido",
        "invalidacao_atingida",
        "alvo_timestamp_ns",
        "invalidacao_timestamp_ns",
        "primeiro_toque",
        "duracao_ate_alvo_ns",
        "duracao_ate_invalidacao_ns",
        "qualidade",
        "atraso_endpoint_ns",
        "qualidade_origem",
        "qualidade_feed_horizonte",
        "causal",
        "modo",
        "promocao_automatica",
        "config_versao",
    }
)

MANIFEST_KEYS = frozenset(
    {
        "schema_versao",
        "modo",
        "promocao_automatica",
        "config_versao",
        "symbol",
        "data",
        "colecoes",
        "horizontes_s",
        "intervalo_amostra_ns",
        "limites",
        "politica_promocao",
    }
)

QUALIDADE_HORIZONTE_KEYS = frozenset(
    {
        "n_observacoes",
        "n_sem_snapshot",
        "estado_pior",
        "estados",
        "latencia_min_ns",
        "latencia_max_ns",
        "latencia_media_ns",
        "sequence_gaps_max",
        "missing_events_max",
        "duplicates_max",
        "delayed_events_max",
        "unknown_aggressors_max",
    }
)

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONFIG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ESTADOS_FEED = {"OK", "DEGRADADA", "ERRO", "DESCONHECIDA"}


def validar_registro(colecao: str, valor: object) -> list[str]:
    if colecao == "features":
        return validar_feature(valor)
    if colecao == "labels":
        return validar_label(valor)
    return [f"colecao desconhecida: {colecao}"]


def validar_feature(valor: object) -> list[str]:
    erros = _objeto_exato(valor, FEATURE_KEYS)
    if erros:
        return erros
    assert isinstance(valor, dict)
    _comum(valor, erros, "features")
    _inteiro(valor, "timestamp_ns", erros, minimo=0)
    _inteiro(valor, "price_ticks", erros)
    _texto(valor, "estado", erros)
    _direcao(valor, "direcao", erros)
    _mapping(valor, "features", erros)
    _mapping(valor, "qualidade_origem", erros)
    _inteiro_ou_none(valor, "alvo_preco_ticks", erros)
    _inteiro_ou_none(valor, "invalidacao_preco_ticks", erros)
    _horizontes(valor.get("horizontes_s"), erros)
    _bool(valor, "label_admitida", erros)
    motivos = valor.get("motivos")
    if not isinstance(motivos, list) or not motivos or not all(
        isinstance(m, str) and m for m in motivos
    ):
        erros.append("motivos deve ser lista textual nao vazia")
    _validar_niveis(valor, "direcao", "price_ticks", erros)
    _json_finito(valor, "$", erros)
    return erros


def validar_label(valor: object) -> list[str]:
    erros = _objeto_exato(valor, LABEL_KEYS)
    if erros:
        return erros
    assert isinstance(valor, dict)
    _comum(valor, erros, "label_futuro")
    for nome in (
        "timestamp_amostra_ns",
        "horizonte_s",
        "limite_horizonte_ns",
        "timestamp_final_observado_ns",
        "duracao_horizonte_ns",
        "duracao_observada_ns",
        "atraso_endpoint_ns",
    ):
        _inteiro(valor, nome, erros, minimo=0)
    if type(valor.get("horizonte_s")) is int and valor["horizonte_s"] <= 0:
        erros.append("horizonte_s deve ser positivo")
    for nome in (
        "price_inicial_ticks",
        "price_final_ticks",
        "min_price_ticks",
        "max_price_ticks",
        "retorno_ticks",
        "mfe_ticks",
        "mae_ticks",
    ):
        _inteiro(valor, nome, erros)
    for nome in (
        "retorno_direcional_ticks",
        "alvo_preco_ticks",
        "invalidacao_preco_ticks",
        "alvo_timestamp_ns",
        "invalidacao_timestamp_ns",
        "duracao_ate_alvo_ns",
        "duracao_ate_invalidacao_ns",
    ):
        _inteiro_ou_none(valor, nome, erros)
    _texto(valor, "estado_na_amostra", erros)
    _direcao(valor, "direcao_na_amostra", erros)
    if valor.get("referencia_excursao") not in {"DIRECAO_SINAL", "HIPOTESE_BUY"}:
        erros.append("referencia_excursao invalida")
    for nome in ("alvo_atingido", "invalidacao_atingida", "causal"):
        _bool(valor, nome, erros)
    if valor.get("primeiro_toque") not in {
        "ALVO",
        "INVALIDACAO",
        "EMPATE",
        "NENHUM",
    }:
        erros.append("primeiro_toque invalido")
    if valor.get("qualidade") not in {"COMPLETA", "PARCIAL", "CENSURADA"}:
        erros.append("qualidade invalida")
    _mapping(valor, "qualidade_origem", erros)
    _validar_qualidade_horizonte(valor.get("qualidade_feed_horizonte"), erros)
    _validar_temporal_label(valor, erros)
    _validar_primeiro_toque(valor, erros)
    _validar_niveis(valor, "direcao_na_amostra", "price_inicial_ticks", erros)
    _json_finito(valor, "$", erros)
    return erros


def validar_manifesto(valor: object) -> list[str]:
    erros = _objeto_exato(valor, MANIFEST_KEYS)
    if erros:
        return erros
    assert isinstance(valor, dict)
    _comum(valor, erros, None)
    _horizontes(valor.get("horizontes_s"), erros)
    _inteiro(valor, "intervalo_amostra_ns", erros, minimo=1)
    _mapping(valor, "limites", erros)
    limites = valor.get("limites")
    if isinstance(limites, dict):
        esperados = {
            "max_pendentes_por_simbolo",
            "max_simbolos",
            "max_registros_buffer",
        }
        if set(limites) != esperados or any(
            type(item) is not int or item <= 0 for item in limites.values()
        ):
            erros.append("limites devem ter schema fechado e inteiros positivos")
    if valor.get("colecoes") != {
        "features": "features.jsonl.gz",
        "labels": "labels.jsonl.gz",
    }:
        erros.append("colecoes divergentes")
    if valor.get("politica_promocao") != politica_promocao_manifesto():
        erros.append("politica_promocao divergente")
    _json_finito(valor, "$", erros)
    return erros


def _objeto_exato(valor: object, chaves: frozenset[str]) -> list[str]:
    if not isinstance(valor, dict):
        return ["registro deve ser objeto JSON"]
    recebidas = set(valor)
    erros = []
    if faltantes := sorted(chaves - recebidas):
        erros.append(f"campos ausentes: {faltantes}")
    if extras := sorted(recebidas - chaves):
        erros.append(f"campos extras: {extras}")
    return erros


def _comum(valor: dict, erros: list[str], tipo: str | None) -> None:
    if valor.get("schema_versao") != SCHEMA_VERSAO:
        erros.append(f"schema_versao deve ser {SCHEMA_VERSAO}")
    if tipo is not None and valor.get("tipo") != tipo:
        erros.append(f"tipo deve ser {tipo}")
    if valor.get("modo") != "shadow":
        erros.append("modo deve ser shadow")
    if valor.get("promocao_automatica") is not False:
        erros.append("promocao_automatica deve ser false")
    _texto(valor, "symbol", erros)
    data = valor.get("data", valor.get("data_amostra"))
    if not isinstance(data, str) or not _DATA.fullmatch(data):
        erros.append("data deve usar AAAA-MM-DD")
    config = valor.get("config_versao")
    if not isinstance(config, str) or not _CONFIG.fullmatch(config):
        erros.append("config_versao invalida")
    if "id_amostra" in valor:
        _texto(valor, "id_amostra", erros)


def _inteiro(valor: dict, nome: str, erros: list[str], minimo: int | None = None) -> None:
    item = valor.get(nome)
    if type(item) is not int:
        erros.append(f"{nome} deve ser inteiro")
    elif minimo is not None and item < minimo:
        erros.append(f"{nome} deve ser >= {minimo}")


def _inteiro_ou_none(valor: dict, nome: str, erros: list[str]) -> None:
    if valor.get(nome) is not None and type(valor.get(nome)) is not int:
        erros.append(f"{nome} deve ser inteiro ou null")


def _texto(valor: dict, nome: str, erros: list[str]) -> None:
    if not isinstance(valor.get(nome), str) or not valor[nome]:
        erros.append(f"{nome} deve ser texto nao vazio")


def _bool(valor: dict, nome: str, erros: list[str]) -> None:
    if type(valor.get(nome)) is not bool:
        erros.append(f"{nome} deve ser booleano")


def _mapping(valor: dict, nome: str, erros: list[str]) -> None:
    if not isinstance(valor.get(nome), dict):
        erros.append(f"{nome} deve ser objeto")


def _direcao(valor: dict, nome: str, erros: list[str]) -> None:
    if valor.get(nome) not in {None, "BUY", "SELL"}:
        erros.append(f"{nome} deve ser BUY, SELL ou null")


def _horizontes(valor: object, erros: list[str]) -> None:
    if not isinstance(valor, list) or not valor:
        erros.append("horizontes_s deve ser lista nao vazia")
        return
    if any(type(h) is not int or h <= 0 for h in valor):
        erros.append("horizontes_s aceita somente inteiros positivos")
    elif valor != sorted(set(valor)):
        erros.append("horizontes_s deve estar ordenado e sem repeticao")


def _validar_niveis(
    valor: dict, direcao_nome: str, preco_nome: str, erros: list[str]
) -> None:
    direcao = valor.get(direcao_nome)
    preco = valor.get(preco_nome)
    alvo = valor.get("alvo_preco_ticks")
    invalidacao = valor.get("invalidacao_preco_ticks")
    if alvo is None and invalidacao is None:
        return
    if direcao not in {"BUY", "SELL"} or type(preco) is not int:
        erros.append("niveis exigem direcao e preco validos")
    elif direcao == "BUY" and (
        (alvo is not None and alvo <= preco)
        or (invalidacao is not None and invalidacao >= preco)
    ):
        erros.append("niveis BUY invertidos")
    elif direcao == "SELL" and (
        (alvo is not None and alvo >= preco)
        or (invalidacao is not None and invalidacao <= preco)
    ):
        erros.append("niveis SELL invertidos")


def _validar_temporal_label(valor: dict, erros: list[str]) -> None:
    inicio = valor.get("timestamp_amostra_ns")
    fim = valor.get("timestamp_final_observado_ns")
    limite = valor.get("limite_horizonte_ns")
    if all(type(v) is int for v in (inicio, fim, limite)):
        if fim < inicio or fim > limite:
            erros.append("janela temporal label invalida")
        horizonte = valor.get("horizonte_s")
        if type(horizonte) is int and limite != inicio + horizonte * 1_000_000_000:
            erros.append("limite_horizonte_ns diverge do horizonte")
        if (
            type(valor.get("duracao_observada_ns")) is int
            and valor["duracao_observada_ns"] != fim - inicio
        ):
            erros.append("duracao_observada_ns divergente")
        if (
            type(valor.get("duracao_horizonte_ns")) is int
            and type(horizonte) is int
            and valor["duracao_horizonte_ns"] != horizonte * 1_000_000_000
        ):
            erros.append("duracao_horizonte_ns divergente")
        if (
            type(valor.get("atraso_endpoint_ns")) is int
            and valor["atraso_endpoint_ns"] != limite - fim
        ):
            erros.append("atraso_endpoint_ns divergente")
    for nome in ("alvo_timestamp_ns", "invalidacao_timestamp_ns"):
        toque = valor.get(nome)
        if toque is not None and type(inicio) is int and toque <= inicio:
            erros.append(f"{nome} nao pode tocar na admissao")
        if toque is not None and type(limite) is int and toque > limite:
            erros.append(f"{nome} esta depois do horizonte")
    for prefixo in ("alvo", "invalidacao"):
        toque = valor.get(f"{prefixo}_timestamp_ns")
        atingido = valor.get(
            "alvo_atingido" if prefixo == "alvo" else "invalidacao_atingida"
        )
        duracao = valor.get(f"duracao_ate_{prefixo}_ns")
        if atingido is not (toque is not None):
            erros.append(f"{prefixo}_atingido diverge do timestamp")
        esperado = None if toque is None or type(inicio) is not int else toque - inicio
        if duracao != esperado:
            erros.append(f"duracao_ate_{prefixo}_ns divergente")
    inicial = valor.get("price_inicial_ticks")
    final = valor.get("price_final_ticks")
    minimo = valor.get("min_price_ticks")
    maximo = valor.get("max_price_ticks")
    if all(type(v) is int for v in (inicial, final, minimo, maximo)):
        if not minimo <= inicial <= maximo or not minimo <= final <= maximo:
            erros.append("min/max nao contêm preços inicial/final")
        retorno = final - inicial
        if valor.get("retorno_ticks") != retorno:
            erros.append("retorno_ticks divergente")
        direcao = valor.get("direcao_na_amostra")
        esperado_direcional = (
            retorno
            if direcao == "BUY"
            else -retorno
            if direcao == "SELL"
            else None
        )
        if valor.get("retorno_direcional_ticks") != esperado_direcional:
            erros.append("retorno_direcional_ticks divergente")
        mfe = maximo - inicial if direcao != "SELL" else inicial - minimo
        mae = inicial - minimo if direcao != "SELL" else maximo - inicial
        if valor.get("mfe_ticks") != mfe or valor.get("mae_ticks") != mae:
            erros.append("MFE/MAE divergentes")


def _validar_primeiro_toque(valor: dict, erros: list[str]) -> None:
    alvo = valor.get("alvo_timestamp_ns")
    invalidacao = valor.get("invalidacao_timestamp_ns")
    esperado = "NENHUM"
    if alvo is not None and invalidacao is not None:
        esperado = "EMPATE" if alvo == invalidacao else (
            "ALVO" if alvo < invalidacao else "INVALIDACAO"
        )
    elif alvo is not None:
        esperado = "ALVO"
    elif invalidacao is not None:
        esperado = "INVALIDACAO"
    if valor.get("primeiro_toque") != esperado:
        erros.append(f"primeiro_toque deve ser {esperado}")
    if alvo is not None and valor.get("alvo_preco_ticks") is None:
        erros.append("toque ALVO sem nivel declarado")
    if invalidacao is not None and valor.get("invalidacao_preco_ticks") is None:
        erros.append("toque INVALIDACAO sem nivel declarado")


def _validar_qualidade_horizonte(valor: object, erros: list[str]) -> None:
    sub = _objeto_exato(valor, QUALIDADE_HORIZONTE_KEYS)
    erros.extend(f"qualidade_feed_horizonte: {erro}" for erro in sub)
    if sub:
        return
    assert isinstance(valor, dict)
    for nome in ("n_observacoes", "n_sem_snapshot"):
        _inteiro(valor, nome, erros, minimo=0)
    if valor.get("estado_pior") not in _ESTADOS_FEED:
        erros.append("estado_pior invalido")
    estados = valor.get("estados")
    if not isinstance(estados, dict) or set(estados) != _ESTADOS_FEED or any(
        type(n) is not int or n < 0 for n in estados.values()
    ):
        erros.append("estados de qualidade invalidos")
    elif type(valor.get("n_observacoes")) is int and sum(estados.values()) != valor[
        "n_observacoes"
    ]:
        erros.append("contagem de estados diverge de n_observacoes")
    elif isinstance(estados, dict) and any(estados.values()):
        ranks = {"OK": 0, "DESCONHECIDA": 1, "DEGRADADA": 2, "ERRO": 3}
        pior = max(
            (estado for estado, n in estados.items() if n), key=ranks.__getitem__
        )
        if valor.get("estado_pior") != pior:
            erros.append("estado_pior diverge das contagens")
    if valor.get("n_observacoes") == 0:
        erros.append("n_observacoes deve ser positivo")
    if (
        type(valor.get("n_sem_snapshot")) is int
        and type(valor.get("n_observacoes")) is int
        and valor["n_sem_snapshot"] > valor["n_observacoes"]
    ):
        erros.append("n_sem_snapshot excede n_observacoes")
    for nome in QUALIDADE_HORIZONTE_KEYS - {
        "n_observacoes",
        "n_sem_snapshot",
        "estado_pior",
        "estados",
        "latencia_media_ns",
    }:
        if valor.get(nome) is not None and type(valor.get(nome)) is not int:
            erros.append(f"{nome} deve ser inteiro ou null")
    media = valor.get("latencia_media_ns")
    if media is not None and (
        type(media) not in (int, float) or not math.isfinite(float(media))
    ):
        erros.append("latencia_media_ns deve ser finita ou null")


def _json_finito(valor: object, caminho: str, erros: list[str]) -> None:
    if isinstance(valor, float) and not math.isfinite(valor):
        erros.append(f"numero nao finito em {caminho}")
    elif isinstance(valor, dict):
        for chave, item in valor.items():
            _json_finito(item, f"{caminho}.{chave}", erros)
    elif isinstance(valor, list):
        for indice, item in enumerate(valor):
            _json_finito(item, f"{caminho}[{indice}]", erros)
