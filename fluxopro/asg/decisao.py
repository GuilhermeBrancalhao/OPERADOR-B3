"""Motor estritamente consultivo para A1/A2/A3 e niveis de risco."""

from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.eventos import Side

from .modelos import (
    DECISION_FORMULA_VERSION,
    DecisionSnapshot,
    EstadoMaker,
    LeituraASG,
    MakerProxySnapshot,
    NivelDecisao,
    PropostaRisco,
    RegiaoOperacional,
)


@dataclass(frozen=True, slots=True)
class ConfigMotorDecisaoASG:
    """Cortes abertos do classificador consultivo; nenhum e formula da ASG."""

    score_a1: float = 0.20
    score_a2: float = 0.40
    score_a3: float = 0.65
    confianca_a1: float = 0.35
    confianca_a2: float = 0.55
    confianca_a3: float = 0.75
    cobertura_a1: float = 0.25
    cobertura_a2: float = 0.50
    cobertura_a3: float = 0.75
    persistencia_a1: float = 0.40
    persistencia_a2: float = 0.60
    persistencia_a3: float = 0.80
    stop_fora_regiao_ticks: int = 1
    alvo_a1_r: int = 1
    alvo_a2_r: int = 2
    alvo_a3_r: int = 3
    formula_version: str = DECISION_FORMULA_VERSION

    def __post_init__(self) -> None:
        for prefixo in ("score", "confianca", "cobertura", "persistencia"):
            valores = tuple(float(getattr(self, f"{prefixo}_a{i}")) for i in (1, 2, 3))
            if not all(0.0 <= item <= 1.0 for item in valores):
                raise ValueError(f"cortes de {prefixo} devem estar entre 0 e 1")
            if valores != tuple(sorted(valores)):
                raise ValueError(f"cortes de {prefixo} devem ser nao decrescentes")
        for nome in (
            "stop_fora_regiao_ticks",
            "alvo_a1_r",
            "alvo_a2_r",
            "alvo_a3_r",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
                raise ValueError(f"{nome} deve ser inteiro >= 1")
        if not self.alvo_a1_r < self.alvo_a2_r < self.alvo_a3_r:
            raise ValueError("alvos A1/A2/A3 devem ser estritamente crescentes")


class MotorDecisaoASG:
    """Classifica a leitura e calcula uma proposta; nao possui API de execucao."""

    __slots__ = ("config",)

    def __init__(self, config: ConfigMotorDecisaoASG | None = None) -> None:
        self.config = config or ConfigMotorDecisaoASG()

    def propor_risco(
        self,
        direcao: Side,
        entrada_ticks: int,
        regiao: RegiaoOperacional,
    ) -> PropostaRisco:
        if not isinstance(entrada_ticks, int) or isinstance(entrada_ticks, bool):
            raise TypeError("entrada_ticks deve ser int em ticks (nunca float)")
        margem = self.config.stop_fora_regiao_ticks
        if direcao is Side.BUY:
            stop = regiao.inicio_ticks - margem
            risco = entrada_ticks - stop
            sinal = 1
        elif direcao is Side.SELL:
            stop = regiao.fim_ticks + margem
            risco = stop - entrada_ticks
            sinal = -1
        else:  # defesa para valores que imitem Enum sem serem Side
            raise ValueError("direcao deve ser Side.BUY ou Side.SELL")
        if risco < 1:
            raise ValueError("entrada deve ficar do lado de risco valido em relacao ao stop")
        return PropostaRisco(
            direcao=direcao,
            entrada_ticks=entrada_ticks,
            stop_ticks=stop,
            a1_ticks=entrada_ticks + sinal * risco * self.config.alvo_a1_r,
            a2_ticks=entrada_ticks + sinal * risco * self.config.alvo_a2_r,
            a3_ticks=entrada_ticks + sinal * risco * self.config.alvo_a3_r,
            risco_ticks=risco,
            formula_version=self.config.formula_version,
        )

    def _nivel(self, leitura: LeituraASG) -> NivelDecisao:
        magnitude = abs(leitura.pontuacao)
        for numero, nivel in (
            (3, NivelDecisao.A3),
            (2, NivelDecisao.A2),
            (1, NivelDecisao.A1),
        ):
            if (
                magnitude >= getattr(self.config, f"score_a{numero}")
                and leitura.confianca >= getattr(self.config, f"confianca_a{numero}")
                and leitura.cobertura >= getattr(self.config, f"cobertura_a{numero}")
                and leitura.persistencia >= getattr(self.config, f"persistencia_a{numero}")
            ):
                return nivel
        return NivelDecisao.AGUARDAR

    def avaliar(
        self,
        leitura: LeituraASG | MakerProxySnapshot,
        regiao: RegiaoOperacional,
        entrada_ticks: int,
    ) -> DecisionSnapshot:
        if isinstance(leitura, MakerProxySnapshot):
            leitura = LeituraASG.do_maker(leitura)
        if leitura.symbol != regiao.symbol:
            raise ValueError("leitura e regiao devem ter o mesmo symbol")
        if not isinstance(entrada_ticks, int) or isinstance(entrada_ticks, bool):
            raise TypeError("entrada_ticks deve ser int em ticks (nunca float)")

        motivos: list[str] = []
        nivel = NivelDecisao.AGUARDAR
        proposta: PropostaRisco | None = None
        direcao = leitura.direcao

        if leitura.estado in {EstadoMaker.SEM_DADOS, EstadoMaker.NEUTRO}:
            motivos.append(f"maker {leitura.estado.value.lower()}")
        elif leitura.estado is EstadoMaker.DIVERGENTE:
            motivos.append("componentes direcionais divergentes")
        elif direcao is None:
            motivos.append("direcao indisponivel")
        else:
            nivel = self._nivel(leitura)
            if nivel is NivelDecisao.AGUARDAR:
                motivos.append(
                    "score, confianca, cobertura ou persistencia abaixo dos cortes A1"
                )
            else:
                proposta = self.propor_risco(direcao, entrada_ticks, regiao)
                motivos.append(
                    f"{nivel.value}: cortes consultivos satisfeitos; "
                    f"stop {self.config.stop_fora_regiao_ticks} tick(s) alem da regiao"
                )

        procedencia = (
            f"maker:{leitura.maker.procedencia.value}",
            f"regiao:{regiao.procedencia.value}",
            f"maker_formula:{leitura.maker.formula_version}",
            f"decision_formula:{self.config.formula_version}",
        )
        return DecisionSnapshot(
            timestamp_ns=leitura.timestamp_ns,
            symbol=leitura.symbol,
            nivel=nivel,
            direcao=direcao,
            leitura=leitura,
            regiao=regiao,
            proposta_risco=proposta,
            motivos=tuple(motivos),
            procedencia=procedencia,
            formula_version=self.config.formula_version,
        )

    decidir = avaliar


__all__ = ["ConfigMotorDecisaoASG", "MotorDecisaoASG"]
