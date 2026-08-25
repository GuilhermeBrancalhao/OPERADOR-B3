"""Decisao exclusivamente consultiva — REGRA DO OPERADOR B3."""

from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.eventos import Side

from .modelos import (
    DECISION_FORMULA_VERSION,
    DecisionSnapshot,
    EstadoMaker,
    FrozenMapping,
    LeituraASG,
    MakerProxySnapshot,
    NivelDecisao,
    PropostaRisco,
    RegiaoOperacional,
)


@dataclass(frozen=True, slots=True)
class ConfigMotorDecisaoASG:
    score_a1: float = 0.07
    score_a2: float = 0.35
    score_a3: float = 0.65
    confianca_a1: float = 0.60
    confianca_a2: float = 0.70
    confianca_a3: float = 0.80
    cobertura_a1: float = 0.60
    cobertura_a2: float = 0.70
    cobertura_a3: float = 0.80
    persistencia_a1: float = 1.0
    persistencia_a2: float = 1.0
    persistencia_a3: float = 1.0
    persistencia_minima_ns: int = 3_000_000_000
    confianca_minima: float = 0.60
    relevancia_minima: float = 0.07
    confianca_regiao_minima: float = 0.60
    idade_regiao_max_ns: int = 30_000_000_000
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
        for nome in ("confianca_minima", "relevancia_minima", "confianca_regiao_minima"):
            valor = float(getattr(self, nome))
            if not 0.0 <= valor <= 1.0:
                raise ValueError(f"{nome} deve estar entre 0 e 1")
        for nome in (
            "persistencia_minima_ns", "idade_regiao_max_ns", "stop_fora_regiao_ticks",
            "alvo_a1_r", "alvo_a2_r", "alvo_a3_r",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
                raise ValueError(f"{nome} deve ser inteiro >= 1")
        if not self.alvo_a1_r < self.alvo_a2_r < self.alvo_a3_r:
            raise ValueError("alvos A1/A2/A3 devem ser crescentes")


class MotorDecisaoASG:
    """Publica gates, bloqueios e niveis informativos; nao executa operacoes."""

    __slots__ = ("config",)

    def __init__(self, config: ConfigMotorDecisaoASG | None = None) -> None:
        self.config = config or ConfigMotorDecisaoASG()

    def propor_risco(
        self, direcao: Side, entrada_ticks: int, regiao: RegiaoOperacional
    ) -> PropostaRisco:
        if not isinstance(entrada_ticks, int) or isinstance(entrada_ticks, bool):
            raise TypeError("entrada_ticks deve ser int em ticks")
        margem = self.config.stop_fora_regiao_ticks
        if direcao is Side.BUY:
            invalidacao = (
                regiao.invalidacao_ticks
                if regiao.invalidacao_ticks is not None else regiao.inicio_ticks
            )
            stop = invalidacao - margem
            risco = entrada_ticks - stop
            sinal = 1
        elif direcao is Side.SELL:
            invalidacao = (
                regiao.invalidacao_ticks
                if regiao.invalidacao_ticks is not None else regiao.fim_ticks
            )
            stop = invalidacao + margem
            risco = stop - entrada_ticks
            sinal = -1
        else:
            raise ValueError("direcao deve ser BUY ou SELL")
        if risco < 1:
            raise ValueError("entrada e invalidacao produzem risco invalido")
        return PropostaRisco(
            direcao=direcao,
            entrada_ticks=entrada_ticks,
            stop_ticks=stop,
            a1_ticks=entrada_ticks + sinal * risco * self.config.alvo_a1_r,
            a2_ticks=entrada_ticks + sinal * risco * self.config.alvo_a2_r,
            a3_ticks=entrada_ticks + sinal * risco * self.config.alvo_a3_r,
            risco_ticks=risco,
            formula_version=self.config.formula_version,
            invalidacao_ticks=invalidacao,
            obstaculo_ticks=regiao.obstaculo_ticks,
        )

    def _nivel_confirmado(self, leitura: LeituraASG) -> NivelDecisao:
        magnitude = abs(leitura.maker.percent or 0.0) / 100.0
        for numero, nivel in ((3, NivelDecisao.A3), (2, NivelDecisao.A2), (1, NivelDecisao.A1)):
            if (
                magnitude >= getattr(self.config, f"score_a{numero}")
                and leitura.confianca >= getattr(self.config, f"confianca_a{numero}")
                and leitura.cobertura >= getattr(self.config, f"cobertura_a{numero}")
                and leitura.persistencia >= getattr(self.config, f"persistencia_a{numero}")
            ):
                return nivel
        return NivelDecisao.A1

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
            raise TypeError("entrada_ticks deve ser int em ticks")

        maker = leitura.maker
        bloqueios: list[str] = []
        motivos: list[str] = []
        regiao_temporalmente_valida = True
        if regiao.timestamp_ns > leitura.timestamp_ns:
            bloqueios.append("REGIAO_FUTURA")
            regiao_temporalmente_valida = False
        elif leitura.timestamp_ns - regiao.timestamp_ns > self.config.idade_regiao_max_ns:
            bloqueios.append("REGIAO_EXPIRADA")
            regiao_temporalmente_valida = False
        if not regiao.valida:
            bloqueios.append("REGIAO_INVALIDA")
        if regiao.confianca < self.config.confianca_regiao_minima:
            bloqueios.append("QUALIDADE_REGIAO_BAIXA")
        if not regiao.contem(entrada_ticks):
            bloqueios.append("PRECO_FORA_DA_REGIAO")

        direcao = maker.direcao
        relevante = abs(maker.percent or 0.0) >= self.config.relevancia_minima * 100.0
        regiao_ok = (
            regiao_temporalmente_valida and regiao.valida
            and regiao.confianca >= self.config.confianca_regiao_minima
            and regiao.contem(entrada_ticks)
        )
        pre_sinal = direcao is not None and relevante and regiao_ok

        if direcao is None:
            bloqueios.append("DIRECAO_INDISPONIVEL")
        if maker.estado is EstadoMaker.SEM_DADOS:
            bloqueios.append("SEM_DADOS")
        if maker.book_kind == "NONE" or maker.estado is EstadoMaker.SEM_BOOK:
            bloqueios.append("SEM_BOOK")
        if maker.book_delayed:
            bloqueios.append("BOOK_ATRASADO")
        if maker.feed_quality <= 0.0:
            bloqueios.append("FEED_NAO_SAUDAVEL")
        if maker.feed_quality < self.config.confianca_minima:
            bloqueios.append("QUALIDADE_FEED_BAIXA")
        if maker.confianca < self.config.confianca_minima:
            bloqueios.append("CONFIANCA_BAIXA")
        if maker.persistence_ns < self.config.persistencia_minima_ns:
            bloqueios.append("PERSISTENCIA_INSUFICIENTE")
        if not relevante:
            bloqueios.append("EVIDENCIA_IRRELEVANTE")
        if maker.estado not in {
            EstadoMaker.COMPRADOR, EstadoMaker.VENDEDOR, EstadoMaker.DIVERGENTE
        }:
            bloqueios.append("MAKER_NAO_CONFIRMADO")
        if maker.estado is EstadoMaker.DIVERGENTE:
            motivos.append("ALERTA: MakerProxy divergente; nao e veto automatico")

        if direcao is not None:
            margem = self.config.stop_fora_regiao_ticks
            if direcao is Side.BUY:
                invalidacao = (
                    regiao.invalidacao_ticks
                    if regiao.invalidacao_ticks is not None
                    else regiao.inicio_ticks
                )
                risco_estrutural = entrada_ticks - (invalidacao - margem)
            else:
                invalidacao = (
                    regiao.invalidacao_ticks
                    if regiao.invalidacao_ticks is not None
                    else regiao.fim_ticks
                )
                risco_estrutural = (invalidacao + margem) - entrada_ticks
            if risco_estrutural < 1:
                bloqueios.append("INVALIDACAO_ESTRUTURAL_INVALIDA")

        # Remove repeticoes sem perder a ordem explicativa.
        bloqueios = list(dict.fromkeys(bloqueios))
        confirmacao = pre_sinal and not bloqueios
        proposta: PropostaRisco | None = None
        nivel = NivelDecisao.AGUARDAR
        if confirmacao and direcao is not None:
            proposta = self.propor_risco(direcao, entrada_ticks, regiao)
            nivel = self._nivel_confirmado(leitura)
            motivos.append(
                f"{nivel.value}: confirmacao consultiva; stop um tick alem da invalidacao"
            )
        elif pre_sinal:
            motivos.append("pre-sinal presente; confirmacao bloqueada")
        else:
            motivos.append("aguardando regiao valida e evidencia direcional")

        procedencia = (
            f"maker:{maker.procedencia.value}",
            f"feed:{maker.source}/{maker.book_kind}",
            f"regiao:{regiao.procedencia.value}",
            f"maker_formula:{maker.formula_version}",
            f"decision_formula:{self.config.formula_version}",
            "regra:REGRA DO OPERADOR B3",
        )
        confianca = min(maker.confianca, regiao.confianca)
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
            placar=leitura.placar if leitura.placar else FrozenMapping(),
            qualidade_regiao=regiao.qualidade,
            pre_sinal=pre_sinal,
            confirmacao=confirmacao,
            invalidacao_ticks=(proposta.invalidacao_ticks if proposta else regiao.invalidacao_ticks),
            obstaculo_ticks=regiao.obstaculo_ticks,
            razao="REGRA DO OPERADOR B3 · stop +1 tick · A1/A2/A3 = 1R/2R/3R",
            bloqueios=tuple(bloqueios),
            confianca=confianca,
        )

    decidir = avaliar


__all__ = ["ConfigMotorDecisaoASG", "MotorDecisaoASG"]
