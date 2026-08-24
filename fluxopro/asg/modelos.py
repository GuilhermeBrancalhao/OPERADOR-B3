"""Contratos imutaveis da leitura ASG-like independente.

O nome do pacote identifica a experiencia de uso. Os calculos abaixo nao
reproduzem nem alegam reproduzir qualquer formula proprietaria: cada retrato
carrega uma ``formula_version`` propria e evidencia auditavel.

Precos sao sempre inteiros em ticks. Colecoes publicadas sao tuplas para que
um snapshot entregue a outra thread nao possa mudar depois da publicacao.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum, StrEnum, unique
from typing import Any

from fluxopro.core.eventos import Side


MAKER_FORMULA_VERSION = "maker-proxy-independent-v1"
DECISION_FORMULA_VERSION = "decision-consultive-v1"


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
    NEUTRO = "NEUTRO"
    DIVERGENTE = "DIVERGENTE"
    COMPRADOR = "COMPRADOR"
    VENDEDOR = "VENDEDOR"


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
    """Mapping pequeno, ordenado e sem qualquer operacao de mutacao."""

    _items: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        itens = tuple(
            (str(chave), congelar_detalhes(valor)) for chave, valor in self._items
        )
        chaves = tuple(chave for chave, _ in itens)
        if len(set(chaves)) != len(chaves):
            raise ValueError("FrozenMapping nao aceita chaves duplicadas")
        object.__setattr__(self, "_items", itens)

    def __getitem__(self, chave: str) -> object:
        for nome, valor in self._items:
            if nome == chave:
                return valor
        raise KeyError(chave)

    def __iter__(self):
        return (chave for chave, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)


def congelar_detalhes(valor: object) -> object:
    """Converte estruturas usuais de evidencia para valores profundamente imutaveis."""
    if isinstance(valor, Mapping):
        return FrozenMapping(
            tuple(
                (str(chave), congelar_detalhes(item))
                for chave, item in sorted(valor.items(), key=lambda par: str(par[0]))
            )
        )
    if is_dataclass(valor) and not isinstance(valor, type):
        return FrozenMapping(
            tuple(
                (campo.name, congelar_detalhes(getattr(valor, campo.name)))
                for campo in fields(valor)
            )
        )
    if isinstance(valor, (list, tuple)):
        return tuple(congelar_detalhes(item) for item in valor)
    if isinstance(valor, (set, frozenset)):
        return tuple(sorted((congelar_detalhes(item) for item in valor), key=repr))
    return valor


def _primitivo(valor: object) -> object:
    if isinstance(valor, Mapping):
        return {str(chave): _primitivo(item) for chave, item in valor.items()}
    if isinstance(valor, StrEnum):
        return valor.value
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Side):
        return valor.value
    if isinstance(valor, tuple):
        return [_primitivo(item) for item in valor]
    if hasattr(valor, "como_dict"):
        return valor.como_dict()  # type: ignore[no-any-return, union-attr]
    return valor


@dataclass(frozen=True, slots=True)
class ConfigMakerProxy:
    """Janelas, limites e pesos declarados do proxy independente."""

    janela_agressao_ns: int = 5_000_000_000
    janela_evidencia_ns: int = 30_000_000_000
    max_trades_retidos: int = 8_192
    max_evidencias_por_componente: int = 64
    max_amostras_persistencia: int = 64
    volume_referencia_agressao: int = 300

    peso_agressao: float = 0.25
    peso_absorcao: float = 0.25
    peso_reposicao: float = 0.20
    peso_divergencia: float = 0.15
    peso_clips: float = 0.15

    limiar_direcional: float = 0.20
    limiar_componente_ativo: float = 1e-9
    formula_version: str = MAKER_FORMULA_VERSION

    def __post_init__(self) -> None:
        for nome in (
            "janela_agressao_ns",
            "janela_evidencia_ns",
            "max_trades_retidos",
            "max_evidencias_por_componente",
            "max_amostras_persistencia",
            "volume_referencia_agressao",
        ):
            valor = getattr(self, nome)
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
                raise ValueError(f"{nome} deve ser inteiro >= 1")
        for nome, peso in self.pesos:
            if not isinstance(peso, (int, float)) or isinstance(peso, bool) or peso < 0:
                raise ValueError(f"peso de {nome.value} deve ser >= 0")
        if self.peso_total <= 0:
            raise ValueError("ao menos um peso do MakerProxy deve ser positivo")
        _validar_fracao("limiar_direcional", self.limiar_direcional)
        _validar_fracao("limiar_componente_ativo", self.limiar_componente_ativo)
        if not self.formula_version.strip():
            raise ValueError("formula_version nao pode ser vazia")

    @property
    def pesos(self) -> tuple[tuple[ComponenteMaker, float], ...]:
        return (
            (ComponenteMaker.AGRESSAO, float(self.peso_agressao)),
            (ComponenteMaker.ABSORCAO, float(self.peso_absorcao)),
            (ComponenteMaker.REPOSICAO, float(self.peso_reposicao)),
            (ComponenteMaker.DIVERGENCIA, float(self.peso_divergencia)),
            (ComponenteMaker.CLIPS, float(self.peso_clips)),
        )

    @property
    def peso_total(self) -> float:
        return sum(peso for _, peso in self.pesos)

    def peso_de(self, componente: ComponenteMaker) -> float:
        return dict(self.pesos)[componente]


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
        congelado = congelar_detalhes(self.detalhes)
        if not isinstance(congelado, FrozenMapping):
            raise TypeError("detalhes deve ser um Mapping")
        object.__setattr__(self, "detalhes", congelado)

    @property
    def score(self) -> float:
        return self.pontuacao

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "symbol": self.symbol,
            "componente": self.componente.value,
            "pontuacao": self.pontuacao,
            "confianca": self.confianca,
            "procedencia": self.procedencia.value,
            "fonte": self.fonte,
            "tipo_evento": self.tipo_evento,
            "preco_ticks": self.preco_ticks,
            "detalhes": _primitivo(self.detalhes),
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
    evidencias: tuple[MakerEvidence, ...] = field(default_factory=tuple)
    procedencia: ProcedenciaASG = ProcedenciaASG.DESCONHECIDA
    formula_version: str = MAKER_FORMULA_VERSION

    def __post_init__(self) -> None:
        if not -1.0 <= self.pontuacao <= 1.0:
            raise ValueError("pontuacao deve estar entre -1 e 1")
        for nome in ("confianca", "cobertura", "peso_efetivo"):
            _validar_fracao(nome, getattr(self, nome))
        if self.peso_configurado < 0:
            raise ValueError("peso_configurado deve ser >= 0")
        if self.n_evidencias < 0:
            raise ValueError("n_evidencias deve ser >= 0")

    @property
    def score(self) -> float:
        return self.pontuacao

    def como_dict(self) -> dict[str, Any]:
        return {
            "componente": self.componente.value,
            "pontuacao": self.pontuacao,
            "peso_configurado": self.peso_configurado,
            "peso_efetivo": self.peso_efetivo,
            "confianca": self.confianca,
            "cobertura": self.cobertura,
            "n_evidencias": self.n_evidencias,
            "ultimo_timestamp_ns": self.ultimo_timestamp_ns,
            "evidencias": [item.como_dict() for item in self.evidencias],
            "procedencia": self.procedencia.value,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class MakerProxySnapshot:
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

    def __post_init__(self) -> None:
        if not -1.0 <= self.pontuacao <= 1.0:
            raise ValueError("pontuacao deve estar entre -1 e 1")
        for nome in ("confianca", "cobertura", "persistencia"):
            _validar_fracao(nome, getattr(self, nome))

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
            "timestamp_ns": self.timestamp_ns,
            "symbol": self.symbol,
            "estado": self.estado.value,
            "direcao": self.direcao.value if self.direcao is not None else None,
            "pontuacao": self.pontuacao,
            "confianca": self.confianca,
            "cobertura": self.cobertura,
            "persistencia": self.persistencia,
            "componentes": [item.como_dict() for item in self.componentes],
            "procedencia": self.procedencia.value,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class LeituraASG:
    """Quadro composto, pronto para integrar metodo, sinal e feed quality.

    Os tres retratos opcionais sao capturados como mappings profundamente
    imutaveis. Isso permite compor dataclasses hoje existentes sem reter os
    ``dict`` mutaveis internos que alguns contratos legados ainda carregam.
    """

    timestamp_ns: int
    symbol: str
    maker: MakerProxySnapshot
    formula_version: str = DECISION_FORMULA_VERSION
    metodo: Mapping[str, object] = field(default_factory=FrozenMapping)
    sinal: Mapping[str, object] = field(default_factory=FrozenMapping)
    feed_quality: Mapping[str, object] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        if self.timestamp_ns != self.maker.timestamp_ns:
            raise ValueError("LeituraASG e MakerProxySnapshot devem ter o mesmo timestamp")
        if self.symbol != self.maker.symbol:
            raise ValueError("LeituraASG e MakerProxySnapshot devem ter o mesmo symbol")
        for nome in ("metodo", "sinal", "feed_quality"):
            congelado = congelar_detalhes(getattr(self, nome))
            if not isinstance(congelado, FrozenMapping):
                raise TypeError(f"{nome} deve ser dataclass ou Mapping")
            timestamp = congelado.get("timestamp_ns")
            if timestamp is not None and timestamp != self.timestamp_ns:
                raise ValueError(f"{nome} e MakerProxySnapshot devem ter o mesmo timestamp")
            symbol = congelado.get("symbol")
            if symbol is not None and symbol != self.symbol:
                raise ValueError(f"{nome} e MakerProxySnapshot devem ter o mesmo symbol")
            object.__setattr__(self, nome, congelado)

    @classmethod
    def do_maker(
        cls,
        maker: MakerProxySnapshot,
        *,
        metodo: object | None = None,
        sinal: object | None = None,
        feed_quality: object | None = None,
    ) -> LeituraASG:
        vazio = FrozenMapping()
        return cls(
            timestamp_ns=maker.timestamp_ns,
            symbol=maker.symbol,
            maker=maker,
            metodo=vazio if metodo is None else congelar_detalhes(metodo),
            sinal=vazio if sinal is None else congelar_detalhes(sinal),
            feed_quality=vazio if feed_quality is None else congelar_detalhes(feed_quality),
        )

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
            "timestamp_ns": self.timestamp_ns,
            "symbol": self.symbol,
            "maker": self.maker.como_dict(),
            "metodo": _primitivo(self.metodo),
            "sinal": _primitivo(self.sinal),
            "feed_quality": _primitivo(self.feed_quality),
            "formula_version": self.formula_version,
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
    formula_version: str = "operational-region-input-v1"

    def __post_init__(self) -> None:
        _validar_tick("inicio_ticks", self.inicio_ticks)
        _validar_tick("fim_ticks", self.fim_ticks)
        if self.inicio_ticks > self.fim_ticks:
            raise ValueError("inicio_ticks deve ser <= fim_ticks")
        _validar_fracao("confianca", self.confianca)

    @property
    def largura_ticks(self) -> int:
        return self.fim_ticks - self.inicio_ticks + 1

    def contem(self, preco_ticks: int) -> bool:
        _validar_tick("preco_ticks", preco_ticks)
        return self.inicio_ticks <= preco_ticks <= self.fim_ticks

    def como_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp_ns": self.timestamp_ns,
            "inicio_ticks": self.inicio_ticks,
            "fim_ticks": self.fim_ticks,
            "nome": self.nome,
            "confianca": self.confianca,
            "procedencia": self.procedencia.value,
            "formula_version": self.formula_version,
        }


@dataclass(frozen=True, slots=True)
class PropostaRisco:
    """Niveis informativos; nao representa nem pode enviar uma ordem."""

    direcao: Side
    entrada_ticks: int
    stop_ticks: int
    a1_ticks: int
    a2_ticks: int
    a3_ticks: int
    risco_ticks: int
    consultiva: bool = True
    formula_version: str = DECISION_FORMULA_VERSION

    def __post_init__(self) -> None:
        for nome in ("entrada_ticks", "stop_ticks", "a1_ticks", "a2_ticks", "a3_ticks"):
            _validar_tick(nome, getattr(self, nome))
        if not isinstance(self.risco_ticks, int) or self.risco_ticks < 1:
            raise ValueError("risco_ticks deve ser inteiro >= 1")
        if self.consultiva is not True:
            raise ValueError("PropostaRisco e estritamente consultiva")

    def como_dict(self) -> dict[str, Any]:
        return {
            "direcao": self.direcao.value,
            "entrada_ticks": self.entrada_ticks,
            "stop_ticks": self.stop_ticks,
            "a1_ticks": self.a1_ticks,
            "a2_ticks": self.a2_ticks,
            "a3_ticks": self.a3_ticks,
            "risco_ticks": self.risco_ticks,
            "consultiva": self.consultiva,
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

    def __post_init__(self) -> None:
        if self.timestamp_ns != self.leitura.timestamp_ns:
            raise ValueError("DecisionSnapshot e LeituraASG devem ter o mesmo timestamp")
        if self.symbol != self.leitura.symbol or self.symbol != self.regiao.symbol:
            raise ValueError("symbol inconsistente no DecisionSnapshot")
        if self.consultiva is not True:
            raise ValueError("DecisionSnapshot e estritamente consultivo")
        if self.nivel is NivelDecisao.AGUARDAR and self.proposta_risco is not None:
            raise ValueError("AGUARDAR nao pode publicar proposta de risco")
        if self.nivel is not NivelDecisao.AGUARDAR and self.proposta_risco is None:
            raise ValueError("A1/A2/A3 exigem proposta de risco")

    @property
    def tem_proposta_informativa(self) -> bool:
        return self.proposta_risco is not None

    def como_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "symbol": self.symbol,
            "nivel": self.nivel.value,
            "direcao": self.direcao.value if self.direcao is not None else None,
            "leitura": self.leitura.como_dict(),
            "regiao": self.regiao.como_dict(),
            "proposta_risco": (
                self.proposta_risco.como_dict() if self.proposta_risco is not None else None
            ),
            "motivos": list(self.motivos),
            "procedencia": list(self.procedencia),
            "consultiva": self.consultiva,
            "formula_version": self.formula_version,
        }
