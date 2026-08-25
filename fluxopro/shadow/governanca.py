"""Human gate para candidatas shadow; avalia evidencia e nunca altera producao."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


POLITICA_PROMOCAO_VERSAO = "human-gate-v1"
MIN_PREGOES = 20
MIN_AMOSTRAS = 10_000
MAX_DEGRADACAO_GUARDRAIL = 0.05


def politica_promocao_manifesto() -> dict[str, object]:
    """Contrato serializavel e versionado, sem callback ou destino de escrita."""
    return {
        "versao": POLITICA_PROMOCAO_VERSAO,
        "aplicacao_automatica": False,
        "min_pregoes": MIN_PREGOES,
        "min_amostras": MIN_AMOSTRAS,
        "walk_forward_obrigatorio": True,
        "limite_inferior_ci_deve_superar_baseline": True,
        "degradacao_guardrail_maxima": MAX_DEGRADACAO_GUARDRAIL,
        "aprovacao_humana_obrigatoria": True,
        "config_versionada_obrigatoria": True,
        "rollback_testado_obrigatorio": True,
    }


@dataclass(frozen=True, slots=True)
class EvidenciaCandidata:
    pregoes: int
    amostras: int
    walk_forward_aprovado: bool
    limite_inferior_ci: float
    baseline: float
    degradacao_guardrail: float
    aprovacao_humana_id: str | None
    config_versao: str
    rollback_testado: bool

    def __post_init__(self) -> None:
        if type(self.pregoes) is not int or self.pregoes < 0:
            raise ValueError("pregoes deve ser inteiro nao negativo")
        if type(self.amostras) is not int or self.amostras < 0:
            raise ValueError("amostras deve ser inteiro nao negativo")
        for nome in ("limite_inferior_ci", "baseline", "degradacao_guardrail"):
            valor = getattr(self, nome)
            if type(valor) not in (int, float) or not math.isfinite(float(valor)):
                raise ValueError(f"{nome} deve ser finito")
        if self.degradacao_guardrail < 0:
            raise ValueError("degradacao_guardrail deve ser nao negativa")
        for nome in ("walk_forward_aprovado", "rollback_testado"):
            if type(getattr(self, nome)) is not bool:
                raise ValueError(f"{nome} deve ser booleano")


@dataclass(frozen=True, slots=True)
class AvaliacaoCandidata:
    elegivel_para_revisao_humana: bool
    bloqueios: tuple[str, ...]
    politica_versao: str = POLITICA_PROMOCAO_VERSAO
    aplicacao_automatica: bool = False


def avaliar_candidata(evidencia: EvidenciaCandidata) -> AvaliacaoCandidata:
    """Retorna elegibilidade documental; nao expoe qualquer operacao de aplicacao."""
    bloqueios: list[str] = []
    if evidencia.pregoes < MIN_PREGOES:
        bloqueios.append("MIN_20_PREGOES")
    if evidencia.amostras < MIN_AMOSTRAS:
        bloqueios.append("MIN_10000_AMOSTRAS")
    if not evidencia.walk_forward_aprovado:
        bloqueios.append("WALK_FORWARD")
    if evidencia.limite_inferior_ci <= evidencia.baseline:
        bloqueios.append("CI_INFERIOR_NAO_SUPERA_BASELINE")
    if evidencia.degradacao_guardrail > MAX_DEGRADACAO_GUARDRAIL:
        bloqueios.append("GUARDRAIL_MAIOR_5_PCT")
    if not evidencia.aprovacao_humana_id or not evidencia.aprovacao_humana_id.strip():
        bloqueios.append("APROVACAO_HUMANA")
    if not re.fullmatch(r"[A-Za-z0-9._-]*\d+[A-Za-z0-9._-]*", evidencia.config_versao):
        bloqueios.append("CONFIG_NAO_VERSIONADA")
    if not evidencia.rollback_testado:
        bloqueios.append("ROLLBACK_NAO_TESTADO")
    return AvaliacaoCandidata(not bloqueios, tuple(bloqueios))
