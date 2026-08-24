"""Contratos imutaveis do nucleo ASG-like independente.

As formulas sao do Operador B3, abertas e versionadas; nada aqui alega
reproduzir formula proprietaria. Precos sao inteiros em ticks e toda colecao
publicada e uma tupla ou um ``FrozenMapping`` profundamente imutavel.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum, StrEnum, unique
from typing import Any

from fluxopro.core.eventos import Side

MAKER_FORMULA_VERSION = "maker-proxy-independent-v2"
DECISION_FORMULA_VERSION = "operator-b3-consultive-v2"


@unique
class ComponenteMaker(StrEnum):
    AGRESSAO = "AGRESSAO"
    ABSORCAO = "ABSORCAO"
    REPOSICAO = "REPOSICAO"
    DIVERGENCIA = "DIVERGENCIA"
    CLIPS = "CLIPS"


@unique
class EstadoMaker(StrEnum):
    SEM_DADOS = "SEM_DADOS"
    SEM_BOOK = "SEM_BOOK"
    AJUSTANDO = "AJUSTANDO"
    NEUTRO = "NEUTRO"
    COMPRADOR = "COMPRADOR"
    VENDEDOR = "VENDEDOR"
    DIVERGENTE = "DIVERGENTE"


@unique
class ProcedenciaASG(StrEnum):
    OBSERVADA = "OBSERVADA"
    INFERIDA = "INFERIDA"
    MISTA = "MISTA"
    DESCONHECIDA = "DESCONHECIDA"


@unique
class NivelDecisao(StrEnum):
    AGUARDAR = "AGUARDAR"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"


def _validar_fracao(nome: str, valor: float) -> None:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser numero")
    if not 0.0 <= float(valor) <= 1.0:
        raise ValueError(f"{nome} deve estar entre 0 e 1")


def _validar_tick(nome: str, valor: int) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise TypeError(f"{nome} deve ser int em ticks (nunca float)")


@dataclass(frozen=True, slots=True)
class FrozenMapping(Mapping[str, object]):
    _items: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        itens = tuple((str(k), congelar(v)) for k, v in tuple(self._items))
        chaves = tuple(k for k, _ in itens)
        if len(chaves) != len(set(chaves)):
            raise ValueError("FrozenMapping nao aceita chaves duplicadas")
        object.__setattr__(self, "_items", itens)

    def __getitem__(self, chave: str) -> object:
        for nome, valor in self._items:
            if nome == chave:
                return valor
        raise KeyError(chave)

    def __iter__(self) -> Iterator[str]:
        return (chave for chave, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)


def congelar(valor: object) -> object:
    """Copia recursivamente mappings, dataclasses e sequencias para imutaveis."""
    if isinstance(valor, Mapping):
        return FrozenMapping(tuple(
            (str(k), congelar(v))
            for k, v in sorted(valor.items(), key=lambda par: str(par[0]))
        ))
    if is_dataclass(valor) and not isinstance(valor, type):
        return FrozenMapping(tuple(
            (campo.name, congelar(getattr(valor, campo.name))) for campo in fields(valor)
        ))
    if isinstance(valor, (list, tuple)):
        return tuple(congelar(item) for item in valor)
    if isinstance(valor, (set, frozenset)):
        return tuple(sorted((congelar(item) for item in valor), key=repr))
    return valor


congelar_detalhes = congelar


def _mapping(valor: object, nome: str) -> FrozenMapping:
    congelado = congelar(valor)
    if not isinstance(congelado, FrozenMapping):
        raise TypeError(f"{nome} deve ser dataclass ou Mapping")
    return congelado


def _primitivo(valor: object) -> object:
    if isinstance(valor, Mapping):
        return {str(k): _primitivo(v) for k, v in valor.items()}
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, tuple):
        return [_primitivo(item) for item in valor]
    if hasattr(valor, "como_dict"):
        return valor.como_dict()  # type: ignore[no-any-return, union-attr]
    return valor


@dataclass(frozen=True, slots=True)
class ConfigMakerProxy:
    """Defaults de engenharia publicados no briefing, todos configuraveis."""

    janela_curta_ns: int = 1_000_000_000
    janela_micro_ns: int = 5_000_000_000
    janela_contexto_ns: int = 30_000_000_000
    persistencia_minima_ns: int = 3_000_000_000
    relevancia_minima: float = 0.07
    confianca_minima: float = 0.60
    peso_absorcao: float = 0.30
    peso_reposicao: float = 0.30
    peso_divergencia: float = 0.20
    peso_clips: float = 0.10
    peso_agressao: float = 0.10
    max_trades_retidos: int = 8_192
    max_evidencias_por_componente: int = 64
    max_amostras_persistencia: int = 256
    max_trade_ids_retidos: int = 16_384
    volume_referencia_agressao: int = 300
    latencia_feed_max_ns: int = 1_000_000_000
    fator_confianca_mbp: float = 0.75
    # Aliases configuraveis da rodada 1.
    janela_agressao_ns: int | None = None
    janela_evidencia_ns: int | None = None
    limiar_direcional: float | None = None
    limiar_componente_ativo: float = 1e-9
    formula_version: str = MAKER_FORMULA_VERSION

    def __post_init__(self) -> None:
        if self.janela_agressao_ns is None:
            object.__setattr__(self, "janela_agressao_ns", self.janela_micro_ns)
        if self.janela_evidencia_ns is None:
            object.__setattr__(self, "janela_evidencia_ns", self.janela_contexto_ns)
        if self.limiar_direcional is None:
            object.__setattr__(self, "limiar_direcional", self.relevancia_minima)
        for nome in (
            "janela_curta_ns", "janela_micro_ns", "janela_contexto_ns",
            "persistencia_minima_ns", "max_trades_retidos",
            "max_evidencias_por_componente", "max_amostras_persistencia",
            "max_trade_ids_retidos", "volume_referencia_agressao",
            "latencia_feed_max_ns", "janela_agressao_ns", "janela_evidencia_ns",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
                raise ValueError(f"{nome} deve ser inteiro >= 1")
        for nome in (
            "relevancia_minima", "confianca_minima", "fator_confianca_mbp",
            "limiar_direcional", "limiar_componente_ativo",
        ):
            _validar_fracao(nome, float(getattr(self, nome)))
        for componente, peso in self.pesos:
            if peso < 0:
                raise ValueError(f"peso de {componente.value} deve ser >= 0")
        if self.peso_total <= 0:
            raise ValueError("ao menos um peso deve ser positivo")
        if not self.formula_version.strip():
            raise ValueError("formula_version nao pode ser vazia")

    @property
    def pesos(self) -> tuple[tuple[ComponenteMaker, float], ...]:
        return (
            (ComponenteMaker.ABSORCAO, float(self.peso_absorcao)),
            (ComponenteMaker.REPOSICAO, float(self.peso_reposicao)),
            (ComponenteMaker.DIVERGENCIA, float(self.peso_divergencia)),
            (ComponenteMaker.CLIPS, float(self.peso_clips)),
            (ComponenteMaker.AGRESSAO, float(self.peso_agressao)),
        )

    @property
    def peso_total(self) -> float:
        return sum(peso for _, peso in self.pesos)

    def peso_de(self, componente: ComponenteMaker) -> float:
        for atual, peso in self.pesos:
            if atual is componente:
                return peso
        raise KeyError(componente)

    def janela_de(self, componente: ComponenteMaker) -> int:
        if componente is ComponenteMaker.CLIPS:
            return self.janela_curta_ns
        if componente in {ComponenteMaker.AGRESSAO, ComponenteMaker.ABSORCAO}:
            return self.janela_micro_ns
        return self.janela_contexto_ns


@dataclass(frozen=True, slots=True)
class MakerEvidence:
    timestamp_ns: int
    symbol: str
    componente: ComponenteMaker
    pontuacao: float
    confianca: float
    procedencia: ProcedenciaASG
    fonte: str
    tipo_evento: str
    preco_ticks: int | None = None
    detalhes: Mapping[str, object] = field(default_factory=FrozenMapping)
    formula_version: str = MAKER_FORMULA_VERSION

    def __post_init__(self) -> None:
        if self.timestamp_ns < 0:
            raise ValueError("timestamp_ns deve ser >= 0")
        if not -1.0 <= self.pontuacao <= 1.0:
            raise ValueError("pontuacao deve estar entre -1 e 1")
        _validar_fracao("confianca", self.confianca)
        if self.preco_ticks is not None:
            _validar_tick("preco_ticks", self.preco_ticks)
        object.__setattr__(self, "detalhes", _mapping(self.detalhes, "detalhes"))

    @property
    def score(self) -> float:
        return self.pontuacao

    @property
    def evidence_buy(self) -> float:
        return max(0.0, self.pontuacao) * self.confianca

    @property
    def evidence_sell(self) -> float:
        return max(0.0, -self.pontuacao) * self.confianca

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns, "symbol": self.symbol,
            "componente": self.componente.value, "pontuacao": self.pontuacao,
            "confianca": self.confianca, "procedencia": self.procedencia.value,
            "fonte": self.fonte, "tipo_evento": self.tipo_evento,
            "preco_ticks": self.preco_ticks, "detalhes": _primitivo(self.detalhes),
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class MakerComponentScore:
    componente: ComponenteMaker
    pontuacao: float
    peso_configurado: float
    peso_efetivo: float
    confianca: float
    cobertura: float
    n_evidencias: int
    ultimo_timestamp_ns: int | None
    evidencias: tuple[MakerEvidence, ...] = ()
    procedencia: ProcedenciaASG = ProcedenciaASG.DESCONHECIDA
    formula_version: str = MAKER_FORMULA_VERSION
    evidencia_buy: float = 0.0
    evidencia_sell: float = 0.0
    percent: float = 0.0
    janela_ns: int = 0
    disponivel: bool = False

    def __post_init__(self) -> None:
        if not -1.0 <= self.pontuacao <= 1.0:
            raise ValueError("pontuacao deve estar entre -1 e 1")
        for nome in ("confianca", "cobertura", "peso_efetivo"):
            _validar_fracao(nome, getattr(self, nome))
        if not -100.0 <= self.percent <= 100.0:
            raise ValueError("percent deve estar entre -100 e 100")
        object.__setattr__(self, "evidencias", tuple(self.evidencias))

    @property
    def score(self) -> float:
        return self.pontuacao

    def como_dict(self) -> dict[str, Any]:
        return {
            "componente": self.componente.value, "pontuacao": self.pontuacao,
            "percent": self.percent, "evidencia_buy": self.evidencia_buy,
            "evidencia_sell": self.evidencia_sell,
            "peso_configurado": self.peso_configurado, "peso_efetivo": self.peso_efetivo,
            "confianca": self.confianca, "cobertura": self.cobertura,
            "n_evidencias": self.n_evidencias,
            "ultimo_timestamp_ns": self.ultimo_timestamp_ns,
            "evidencias": [item.como_dict() for item in self.evidencias],
            "procedencia": self.procedencia.value, "janela_ns": self.janela_ns,
            "disponivel": self.disponivel, "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class MakerProxySnapshot:
    # Campos da rodada 1 preservados para a UI.
    timestamp_ns: int
    symbol: str
    estado: EstadoMaker
    direcao: Side | None
    pontuacao: float
    confianca: float
    cobertura: float
    persistencia: float
    componentes: tuple[MakerComponentScore, ...]
    procedencia: ProcedenciaASG
    formula_version: str = MAKER_FORMULA_VERSION
    # Contrato canonico da rodada 2.
    percent: float | None = None
    persistence_ns: int = 0
    source: str = "UNKNOWN"
    book_kind: str = "NONE"
    inferred: bool = False
    evidence: tuple[MakerEvidence, ...] = ()
    component_coverage: float | None = None
    component_availability: tuple[tuple[ComponenteMaker, bool], ...] = ()
    feed_quality: float = 0.0
    stability: float = 0.0
    book_delayed: bool = False
    discarded_duplicates: int = 0
    discarded_regressive: int = 0
    # Nomes canonicos tambem sao campos; os nomes em portugues acima sao aliases legados.
    state: EstadoMaker | None = None
    side: Side | None = None
    confidence: float | None = None
    component_scores: tuple[MakerComponentScore, ...] | None = None

    def __post_init__(self) -> None:
        if not -1.0 <= self.pontuacao <= 1.0:
            raise ValueError("pontuacao deve estar entre -1 e 1")
        percentual = self.pontuacao * 100.0 if self.percent is None else self.percent
        cobertura = self.cobertura if self.component_coverage is None else self.component_coverage
        if not -100.0 <= percentual <= 100.0:
            raise ValueError("percent deve estar entre -100 e 100")
        for nome, valor in (
            ("confianca", self.confianca), ("cobertura", self.cobertura),
            ("persistencia", self.persistencia), ("component_coverage", cobertura),
            ("feed_quality", self.feed_quality), ("stability", self.stability),
        ):
            _validar_fracao(nome, float(valor))
        object.__setattr__(self, "percent", float(percentual))
        object.__setattr__(self, "component_coverage", float(cobertura))
        object.__setattr__(self, "componentes", tuple(self.componentes))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "component_availability", tuple(self.component_availability))
        object.__setattr__(self, "state", self.estado if self.state is None else self.state)
        object.__setattr__(self, "side", self.direcao if self.side is None else self.side)
        object.__setattr__(
            self, "confidence", self.confianca if self.confidence is None else self.confidence
        )
        object.__setattr__(
            self, "component_scores",
            self.componentes if self.component_scores is None else tuple(self.component_scores),
        )
        if self.state is not self.estado or self.side is not self.direcao:
            raise ValueError("aliases state/side inconsistentes")
        if self.confidence != self.confianca or self.component_scores != self.componentes:
            raise ValueError("aliases confidence/component_scores inconsistentes")

    @property
    def score(self) -> float:
        return self.pontuacao

    def componente(self, componente: ComponenteMaker) -> MakerComponentScore:
        for item in self.componentes:
            if item.componente is componente:
                return item
        raise KeyError(componente)

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns, "symbol": self.symbol,
            "state": self.estado.value,
            "side": self.direcao.value if self.direcao is not None else None,
            "percent": self.percent, "confidence": self.confianca,
            "persistence_ns": self.persistence_ns,
            "component_scores": [item.como_dict() for item in self.componentes],
            "component_coverage": self.component_coverage,
            "component_availability": [[c.value, v] for c, v in self.component_availability],
            "evidence": [item.como_dict() for item in self.evidence],
            "source": self.source, "book_kind": self.book_kind,
            "inferred": self.inferred, "feed_quality": self.feed_quality,
            "stability": self.stability, "book_delayed": self.book_delayed,
            "procedencia": self.procedencia.value,
            "discarded_duplicates": self.discarded_duplicates,
            "discarded_regressive": self.discarded_regressive,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class LeituraASG:
    timestamp_ns: int
    symbol: str
    maker: MakerProxySnapshot
    formula_version: str = DECISION_FORMULA_VERSION
    metodo: Mapping[str, object] = field(default_factory=FrozenMapping)
    sinal: Mapping[str, object] = field(default_factory=FrozenMapping)
    feed_quality: Mapping[str, object] = field(default_factory=FrozenMapping)
    macro: Mapping[str, object] = field(default_factory=FrozenMapping)
    micro: Mapping[str, object] = field(default_factory=FrozenMapping)
    linha_azul: Mapping[str, object] = field(default_factory=FrozenMapping)
    regime: Mapping[str, object] = field(default_factory=FrozenMapping)
    velocimetro: Mapping[str, object] = field(default_factory=FrozenMapping)
    placar: Mapping[str, object] = field(default_factory=FrozenMapping)
    divergencias: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.timestamp_ns != self.maker.timestamp_ns or self.symbol != self.maker.symbol:
            raise ValueError("LeituraASG e MakerProxySnapshot devem compartilhar instante e symbol")
        congelados: dict[str, FrozenMapping] = {}
        for nome in (
            "metodo", "sinal", "feed_quality", "macro", "micro",
            "linha_azul", "regime", "velocimetro", "placar",
        ):
            atual = _mapping(getattr(self, nome), nome)
            timestamp = atual.get("timestamp_ns", atual.get("ingress_timestamp_ns"))
            if timestamp is not None and timestamp != self.timestamp_ns:
                raise ValueError(f"{nome} e MakerProxySnapshot devem ter o mesmo timestamp")
            symbol = atual.get("symbol")
            if symbol is not None and symbol != self.symbol:
                raise ValueError(f"{nome} e MakerProxySnapshot devem ter o mesmo symbol")
            congelados[nome] = atual
            object.__setattr__(self, nome, atual)
        metodo = congelados["metodo"]
        derivacoes = {
            "macro": metodo.get("macro_micro", FrozenMapping()),
            "micro": metodo.get("macro_micro", FrozenMapping()),
            "linha_azul": metodo.get("linha_azul", FrozenMapping()),
            "regime": metodo.get("estrutura", FrozenMapping()),
            "velocimetro": metodo.get("velocimetro", FrozenMapping()),
            "placar": metodo.get("placar", FrozenMapping()),
        }
        for nome, valor in derivacoes.items():
            if not getattr(self, nome):
                object.__setattr__(self, nome, _mapping(valor, nome))
        object.__setattr__(self, "divergencias", tuple(self.divergencias))
        object.__setattr__(self, "provenance", tuple(self.provenance))

    @classmethod
    def do_maker(cls, maker: MakerProxySnapshot, **partes: object) -> LeituraASG:
        permitidos = {
            "metodo", "sinal", "feed_quality", "macro", "micro", "linha_azul",
            "regime", "velocimetro", "placar", "divergencias", "provenance",
        }
        desconhecidos = set(partes) - permitidos
        if desconhecidos:
            raise TypeError(f"partes desconhecidas: {sorted(desconhecidos)}")
        return cls(timestamp_ns=maker.timestamp_ns, symbol=maker.symbol, maker=maker, **partes)

    @property
    def maker_proxy(self) -> MakerProxySnapshot:
        return self.maker

    @property
    def procedencia(self) -> tuple[str, ...]:
        return self.provenance

    @property
    def estado(self) -> EstadoMaker:
        return self.maker.estado

    @property
    def direcao(self) -> Side | None:
        return self.maker.direcao

    @property
    def pontuacao(self) -> float:
        return self.maker.pontuacao

    @property
    def confianca(self) -> float:
        return self.maker.confianca

    @property
    def cobertura(self) -> float:
        return self.maker.cobertura

    @property
    def persistencia(self) -> float:
        return self.maker.persistencia

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns, "symbol": self.symbol,
            "maker_proxy": self.maker.como_dict(), "macro": _primitivo(self.macro),
            "micro": _primitivo(self.micro), "linha_azul": _primitivo(self.linha_azul),
            "regime": _primitivo(self.regime), "velocimetro": _primitivo(self.velocimetro),
            "placar": _primitivo(self.placar), "feed_quality": _primitivo(self.feed_quality),
            "sinal": _primitivo(self.sinal), "divergencias": list(self.divergencias),
            "provenance": list(self.provenance), "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class RegiaoOperacional:
    symbol: str
    timestamp_ns: int
    inicio_ticks: int
    fim_ticks: int
    nome: str = "REGIAO"
    confianca: float = 1.0
    procedencia: ProcedenciaASG = ProcedenciaASG.DESCONHECIDA
    formula_version: str = "operator-b3-region-v2"
    qualidade: str = "VALIDA"
    valida: bool = True
    invalidacao_ticks: int | None = None
    obstaculo_ticks: int | None = None

    def __post_init__(self) -> None:
        _validar_tick("inicio_ticks", self.inicio_ticks)
        _validar_tick("fim_ticks", self.fim_ticks)
        if self.inicio_ticks > self.fim_ticks:
            raise ValueError("inicio_ticks deve ser <= fim_ticks")
        _validar_fracao("confianca", self.confianca)
        for nome in ("invalidacao_ticks", "obstaculo_ticks"):
            if getattr(self, nome) is not None:
                _validar_tick(nome, getattr(self, nome))

    @property
    def largura_ticks(self) -> int:
        return self.fim_ticks - self.inicio_ticks + 1

    def contem(self, preco_ticks: int) -> bool:
        _validar_tick("preco_ticks", preco_ticks)
        return self.inicio_ticks <= preco_ticks <= self.fim_ticks

    def como_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "timestamp_ns": self.timestamp_ns,
            "inicio_ticks": self.inicio_ticks, "fim_ticks": self.fim_ticks,
            "nome": self.nome, "qualidade": self.qualidade, "valida": self.valida,
            "confianca": self.confianca, "procedencia": self.procedencia.value,
            "invalidacao_ticks": self.invalidacao_ticks,
            "obstaculo_ticks": self.obstaculo_ticks,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class PropostaRisco:
    direcao: Side
    entrada_ticks: int
    stop_ticks: int
    a1_ticks: int
    a2_ticks: int
    a3_ticks: int
    risco_ticks: int
    consultiva: bool = True
    formula_version: str = DECISION_FORMULA_VERSION
    invalidacao_ticks: int | None = None
    obstaculo_ticks: int | None = None

    def __post_init__(self) -> None:
        for nome in ("entrada_ticks", "stop_ticks", "a1_ticks", "a2_ticks", "a3_ticks"):
            _validar_tick(nome, getattr(self, nome))
        if not isinstance(self.risco_ticks, int) or self.risco_ticks < 1:
            raise ValueError("risco_ticks deve ser inteiro >= 1")
        if self.consultiva is not True:
            raise ValueError("PropostaRisco e estritamente informativa")

    def como_dict(self) -> dict[str, Any]:
        return {
            "direcao": self.direcao.value, "entrada_ticks": self.entrada_ticks,
            "stop_ticks": self.stop_ticks, "a1_ticks": self.a1_ticks,
            "a2_ticks": self.a2_ticks, "a3_ticks": self.a3_ticks,
            "risco_ticks": self.risco_ticks, "invalidacao_ticks": self.invalidacao_ticks,
            "obstaculo_ticks": self.obstaculo_ticks, "consultiva": self.consultiva,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class DecisionSnapshot:
    timestamp_ns: int
    symbol: str
    nivel: NivelDecisao
    direcao: Side | None
    leitura: LeituraASG
    regiao: RegiaoOperacional
    proposta_risco: PropostaRisco | None
    motivos: tuple[str, ...]
    procedencia: tuple[str, ...]
    consultiva: bool = True
    formula_version: str = DECISION_FORMULA_VERSION
    placar: Mapping[str, object] = field(default_factory=FrozenMapping)
    qualidade_regiao: str = "DESCONHECIDA"
    pre_sinal: bool = False
    confirmacao: bool = False
    invalidacao_ticks: int | None = None
    obstaculo_ticks: int | None = None
    razao: str = "REGRA DO OPERADOR B3"
    bloqueios: tuple[str, ...] = ()
    confianca: float = 0.0
    stop_proposto: int | None = None
    a1_ticks: int | None = None
    a2_ticks: int | None = None
    a3_ticks: int | None = None

    def __post_init__(self) -> None:
        if self.timestamp_ns != self.leitura.timestamp_ns:
            raise ValueError("DecisionSnapshot e LeituraASG devem ter o mesmo timestamp")
        if self.symbol != self.leitura.symbol or self.symbol != self.regiao.symbol:
            raise ValueError("symbol inconsistente no DecisionSnapshot")
        if self.consultiva is not True:
            raise ValueError("DecisionSnapshot e estritamente informativo")
        if self.confirmacao and self.proposta_risco is None:
            raise ValueError("confirmacao exige proposta de risco informativa")
        _validar_fracao("confianca", self.confianca)
        object.__setattr__(self, "motivos", tuple(self.motivos))
        object.__setattr__(self, "procedencia", tuple(self.procedencia))
        object.__setattr__(self, "bloqueios", tuple(self.bloqueios))
        object.__setattr__(self, "placar", _mapping(self.placar, "placar"))
        if self.proposta_risco is not None:
            niveis = {
                "stop_proposto": self.proposta_risco.stop_ticks,
                "a1_ticks": self.proposta_risco.a1_ticks,
                "a2_ticks": self.proposta_risco.a2_ticks,
                "a3_ticks": self.proposta_risco.a3_ticks,
            }
            for nome, esperado in niveis.items():
                atual = getattr(self, nome)
                if atual is not None and atual != esperado:
                    raise ValueError(f"{nome} inconsistente com proposta_risco")
                object.__setattr__(self, nome, esperado)

    @property
    def tem_proposta_informativa(self) -> bool:
        return self.proposta_risco is not None

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns, "symbol": self.symbol,
            "nivel": self.nivel.value,
            "direcao": self.direcao.value if self.direcao is not None else None,
            "placar": _primitivo(self.placar), "regiao": self.regiao.como_dict(),
            "qualidade_regiao": self.qualidade_regiao, "pre_sinal": self.pre_sinal,
            "confirmacao": self.confirmacao, "invalidacao_ticks": self.invalidacao_ticks,
            "stop_proposto": self.stop_proposto, "a1_ticks": self.a1_ticks,
            "a2_ticks": self.a2_ticks, "a3_ticks": self.a3_ticks,
            "obstaculo_ticks": self.obstaculo_ticks, "razao": self.razao,
            "bloqueios": list(self.bloqueios), "motivos": list(self.motivos),
            "confianca": self.confianca, "procedencia": list(self.procedencia),
            "proposta_risco": self.proposta_risco.como_dict() if self.proposta_risco else None,
            "consultiva": self.consultiva, "formula_version": self.formula_version,
        }
