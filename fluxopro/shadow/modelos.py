"""Contratos imutaveis do sidecar de aprendizado em modo shadow.

O modulo depende apenas da biblioteca padrao e dos enums do nucleo. Ele nao
importa a aplicacao nem a UI, portanto pode ser usado em captura, replay e em
testes sem PySide6.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum, StrEnum, unique
from types import MappingProxyType
from typing import Mapping

from fluxopro.core.eventos import Side


HORIZONTES_PADRAO_S = (1, 3, 5, 15, 30)
SCHEMA_VERSAO = 2
CONFIG_VERSAO_PADRAO = "shadow-v2"


@unique
class MotivoAmostra(StrEnum):
    PERIODICA = "PERIODICA"
    MUDANCA_ESTADO = "MUDANCA_ESTADO"
    PRE_SINAL = "PRE_SINAL"
    CONFIRMACAO = "CONFIRMACAO"


@unique
class QualidadeRotulo(StrEnum):
    COMPLETA = "COMPLETA"
    PARCIAL = "PARCIAL"
    CENSURADA = "CENSURADA"


def _congelar(valor: object) -> object:
    """Copia e congela recursivamente para o snapshot nao mudar por alias."""
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ValueError("mappings shadow nao aceitam NaN ou infinito")
    if isinstance(valor, Mapping):
        return MappingProxyType({str(k): _congelar(v) for k, v in valor.items()})
    if isinstance(valor, (list, tuple)):
        return tuple(_congelar(v) for v in valor)
    if isinstance(valor, (set, frozenset)):
        return frozenset(_congelar(v) for v in valor)
    return valor


def _mapa_imutavel(valor: Mapping[str, object] | None) -> Mapping[str, object]:
    congelado = _congelar(valor or {})
    assert isinstance(congelado, Mapping)
    return congelado


@dataclass(frozen=True, slots=True)
class AmostraFeatures:
    """Retrato causal no instante da decisao de amostrar.

    ``alvo_preco_ticks`` e ``invalidacao_preco_ticks`` sao niveis absolutos,
    e nao ordens. Servem somente para rotular se o mercado os tocou depois.
    """

    timestamp_ns: int
    symbol: str
    price_ticks: int
    estado: str | Enum
    direcao: Side | None = None
    features: Mapping[str, object] = field(default_factory=dict)
    qualidade_origem: Mapping[str, object] = field(default_factory=dict)
    alvo_preco_ticks: int | None = None
    invalidacao_preco_ticks: int | None = None

    def __post_init__(self) -> None:
        if type(self.timestamp_ns) is not int or self.timestamp_ns < 0:
            raise ValueError("timestamp_ns deve ser nao negativo")
        if type(self.price_ticks) is not int:
            raise ValueError("price_ticks deve ser inteiro")
        if not self.symbol or any(c in self.symbol for c in "/\\"):
            raise ValueError("symbol deve ser nao vazio e nao pode conter separador")
        estado = self.estado.value if isinstance(self.estado, Enum) else self.estado
        if not isinstance(estado, str) or not estado:
            raise ValueError("estado deve ser nao vazio")
        object.__setattr__(self, "estado", estado)
        if self.direcao is not None and not isinstance(self.direcao, Side):
            object.__setattr__(self, "direcao", Side(self.direcao))
        for nome in ("alvo_preco_ticks", "invalidacao_preco_ticks"):
            valor = getattr(self, nome)
            if valor is not None and type(valor) is not int:
                raise ValueError(f"{nome} deve ser inteiro ou None")
        self._validar_niveis()
        object.__setattr__(self, "features", _mapa_imutavel(self.features))
        object.__setattr__(
            self, "qualidade_origem", _mapa_imutavel(self.qualidade_origem)
        )

    def _validar_niveis(self) -> None:
        alvo = self.alvo_preco_ticks
        invalidacao = self.invalidacao_preco_ticks
        if alvo is None and invalidacao is None:
            return
        if self.direcao is None:
            raise ValueError("alvo/invalidation exigem direcao BUY ou SELL")
        if self.direcao is Side.BUY:
            if alvo is not None and alvo <= self.price_ticks:
                raise ValueError("alvo BUY deve ficar acima do preco de admissao")
            if invalidacao is not None and invalidacao >= self.price_ticks:
                raise ValueError("invalidacao BUY deve ficar abaixo do preco de admissao")
        else:
            if alvo is not None and alvo >= self.price_ticks:
                raise ValueError("alvo SELL deve ficar abaixo do preco de admissao")
            if invalidacao is not None and invalidacao <= self.price_ticks:
                raise ValueError("invalidacao SELL deve ficar acima do preco de admissao")


@dataclass(frozen=True, slots=True)
class ConfigShadow:
    intervalo_amostra_ns: int = 1_000_000_000
    horizontes_s: tuple[int, ...] = HORIZONTES_PADRAO_S
    tolerancia_qualidade_ns: int = 1_000_000_000
    max_pendentes_por_simbolo: int = 4_096
    max_simbolos: int = 64
    max_registros_buffer: int = 32_768
    config_versao: str = CONFIG_VERSAO_PADRAO

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizontes_s", tuple(self.horizontes_s))
        inteiros = {
            "intervalo_amostra_ns": self.intervalo_amostra_ns,
            "tolerancia_qualidade_ns": self.tolerancia_qualidade_ns,
            "max_pendentes_por_simbolo": self.max_pendentes_por_simbolo,
            "max_simbolos": self.max_simbolos,
            "max_registros_buffer": self.max_registros_buffer,
        }
        if any(type(valor) is not int for valor in inteiros.values()):
            raise ValueError("intervalos e limites shadow devem ser inteiros")
        if self.intervalo_amostra_ns <= 0:
            raise ValueError("intervalo_amostra_ns deve ser positivo")
        if not self.horizontes_s or any(
            type(h) is not int or h <= 0 for h in self.horizontes_s
        ):
            raise ValueError("horizontes_s deve conter apenas inteiros positivos")
        if tuple(sorted(set(self.horizontes_s))) != self.horizontes_s:
            raise ValueError("horizontes_s deve estar ordenado e sem repeticao")
        if self.tolerancia_qualidade_ns < 0:
            raise ValueError("tolerancia_qualidade_ns deve ser nao negativa")
        if (
            self.max_pendentes_por_simbolo <= 0
            or self.max_simbolos <= 0
            or self.max_registros_buffer <= 0
        ):
            raise ValueError("limites de memoria devem ser positivos")
        minimo_buffer = self.max_pendentes_por_simbolo * len(self.horizontes_s) + 1
        if self.max_registros_buffer < minimo_buffer:
            raise ValueError(
                "max_registros_buffer deve comportar todos os labels que um "
                f"unico tick pode fechar mais a feature ({minimo_buffer})"
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.config_versao):
            raise ValueError("config_versao deve ser um identificador versionado")
