"""Rotulador futuro causal e de memoria estritamente limitada."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from fluxopro.core.eventos import Side
from fluxopro.shadow.modelos import (
    SCHEMA_VERSAO,
    AmostraFeatures,
    ConfigShadow,
    QualidadeRotulo,
)


_ESTADOS_QUALIDADE = ("OK", "DEGRADADA", "ERRO", "DESCONHECIDA")
_CONTADORES_QUALIDADE = (
    "sequence_gaps",
    "missing_events",
    "duplicates",
    "delayed_events",
    "unknown_aggressors",
)


@dataclass(slots=True)
class _QualidadeHorizonte:
    n_observacoes: int = 0
    n_sem_snapshot: int = 0
    estados: dict[str, int] = field(
        default_factory=lambda: {estado: 0 for estado in _ESTADOS_QUALIDADE}
    )
    latencia_min_ns: int | None = None
    latencia_max_ns: int | None = None
    latencia_soma_ns: int = 0
    latencia_n: int = 0
    maximos: dict[str, int | None] = field(
        default_factory=lambda: {nome: None for nome in _CONTADORES_QUALIDADE}
    )

    def incorporar(self, snapshot: Mapping[str, object]) -> None:
        self.n_observacoes += 1
        if not snapshot:
            self.n_sem_snapshot += 1
        estado = _estado_qualidade(snapshot)
        self.estados[estado] += 1
        latencia = _inteiro_qualidade(snapshot, "latency_ns", "latencia_ns")
        if latencia is not None:
            self.latencia_min_ns = (
                latencia
                if self.latencia_min_ns is None
                else min(self.latencia_min_ns, latencia)
            )
            self.latencia_max_ns = (
                latencia
                if self.latencia_max_ns is None
                else max(self.latencia_max_ns, latencia)
            )
            self.latencia_soma_ns += latencia
            self.latencia_n += 1
        for nome in _CONTADORES_QUALIDADE:
            valor = _inteiro_qualidade(snapshot, nome)
            if valor is not None:
                atual = self.maximos[nome]
                self.maximos[nome] = valor if atual is None else max(atual, valor)

    def registro(self) -> dict[str, object]:
        pior = max(
            _ESTADOS_QUALIDADE,
            key=lambda estado: (_rank_qualidade(estado) if self.estados[estado] else -1),
        )
        return {
            "n_observacoes": self.n_observacoes,
            "n_sem_snapshot": self.n_sem_snapshot,
            "estado_pior": pior,
            "estados": dict(self.estados),
            "latencia_min_ns": self.latencia_min_ns,
            "latencia_max_ns": self.latencia_max_ns,
            "latencia_media_ns": (
                self.latencia_soma_ns / self.latencia_n if self.latencia_n else None
            ),
            "sequence_gaps_max": self.maximos["sequence_gaps"],
            "missing_events_max": self.maximos["missing_events"],
            "duplicates_max": self.maximos["duplicates"],
            "delayed_events_max": self.maximos["delayed_events"],
            "unknown_aggressors_max": self.maximos["unknown_aggressors"],
        }


@dataclass(slots=True)
class _Horizonte:
    segundos: int
    limite_ns: int
    minimo: int
    maximo: int
    ultimo_preco: int
    ultimo_timestamp_ns: int
    qualidade_feed: _QualidadeHorizonte = field(default_factory=_QualidadeHorizonte)
    alvo_timestamp_ns: int | None = None
    invalidacao_timestamp_ns: int | None = None


@dataclass(slots=True)
class _Pendente:
    id_amostra: str
    amostra: AmostraFeatures
    data_amostra: str
    horizontes: deque[_Horizonte] = field(default_factory=deque)


class RotuladorCausal:
    """Mantem apenas amostras cujos horizontes ainda nao terminaram.

    Um evento com ``timestamp_ns > limite`` finaliza a janela antes de ser
    incorporado. Assim uma negociacao aos 1,2 s jamais contamina o rotulo de
    1 s; ela somente informa ao rotulador que esse horizonte ja acabou.
    """

    def __init__(self, config: ConfigShadow) -> None:
        self.config = config
        self._pendentes: dict[str, deque[_Pendente]] = {}
        self.descartadas_por_capacidade = 0

    @property
    def n_pendentes(self) -> int:
        return sum(map(len, self._pendentes.values()))

    @property
    def pendentes_por_simbolo(self) -> dict[str, int]:
        return {symbol: len(fila) for symbol, fila in self._pendentes.items()}

    @property
    def simbolos_pendentes(self) -> tuple[str, ...]:
        return tuple(self._pendentes)

    def n_horizontes_pendentes(self, symbol: str | None = None) -> int:
        filas = self._pendentes.values() if symbol is None else (self._pendentes.get(symbol, ()),)
        return sum(len(p.horizontes) for fila in filas for p in fila)

    def quantos_fecham(self, symbol: str, timestamp_ns: int) -> int:
        return sum(
            horizonte.limite_ns <= timestamp_ns
            for pendente in self._pendentes.get(symbol, ())
            for horizonte in pendente.horizontes
        )

    def admitir(self, id_amostra: str, data_amostra: str, amostra: AmostraFeatures) -> bool:
        fila = self._pendentes.setdefault(amostra.symbol, deque())
        if len(fila) >= self.config.max_pendentes_por_simbolo:
            self.descartadas_por_capacidade += 1
            return False
        horizontes = deque(
            _Horizonte(
                segundos=h,
                limite_ns=amostra.timestamp_ns + h * 1_000_000_000,
                minimo=amostra.price_ticks,
                maximo=amostra.price_ticks,
                ultimo_preco=amostra.price_ticks,
                ultimo_timestamp_ns=amostra.timestamp_ns,
            )
            for h in self.config.horizontes_s
        )
        for horizonte in horizontes:
            self._incorporar(
                amostra,
                horizonte,
                amostra.timestamp_ns,
                amostra.price_ticks,
                amostra.qualidade_origem,
            )
        fila.append(_Pendente(id_amostra, amostra, data_amostra, horizontes))
        return True

    def avancar(
        self,
        symbol: str,
        timestamp_ns: int,
        price_ticks: int,
        qualidade_feed: Mapping[str, object],
    ) -> list[dict]:
        """Avanca o relogio de um simbolo e devolve rotulos agora conhecidos."""
        fila = self._pendentes.get(symbol)
        if not fila:
            return []
        prontos: list[dict] = []
        mantidos: deque[_Pendente] = deque()
        while fila:
            pendente = fila.popleft()
            restantes: deque[_Horizonte] = deque()
            while pendente.horizontes:
                horizonte = pendente.horizontes.popleft()
                if timestamp_ns > horizonte.limite_ns:
                    prontos.append(self._fechar(pendente, horizonte, censurada=False))
                    continue
                self._incorporar(
                    pendente.amostra,
                    horizonte,
                    timestamp_ns,
                    price_ticks,
                    qualidade_feed,
                )
                if timestamp_ns == horizonte.limite_ns:
                    prontos.append(self._fechar(pendente, horizonte, censurada=False))
                else:
                    restantes.append(horizonte)
            pendente.horizontes = restantes
            if restantes:
                mantidos.append(pendente)
        if mantidos:
            self._pendentes[symbol] = mantidos
        else:
            self._pendentes.pop(symbol, None)
        return prontos

    def censurar(self, symbol: str | None = None) -> list[dict]:
        """Fecha um simbolo (ou todos) sem inventar o futuro ausente."""
        prontos: list[dict] = []
        simbolos = tuple(self._pendentes) if symbol is None else (symbol,)
        for nome in simbolos:
            fila = self._pendentes.pop(nome, ())
            for pendente in fila:
                for horizonte in pendente.horizontes:
                    prontos.append(self._fechar(pendente, horizonte, censurada=True))
        return prontos

    def censurar_todos(self) -> list[dict]:
        return self.censurar()

    @staticmethod
    def _incorporar(
        amostra: AmostraFeatures,
        horizonte: _Horizonte,
        timestamp_ns: int,
        price_ticks: int,
        qualidade_feed: Mapping[str, object],
    ) -> None:
        horizonte.minimo = min(horizonte.minimo, price_ticks)
        horizonte.maximo = max(horizonte.maximo, price_ticks)
        horizonte.ultimo_preco = price_ticks
        horizonte.ultimo_timestamp_ns = timestamp_ns
        horizonte.qualidade_feed.incorporar(qualidade_feed)
        # O retrato de admissao define preco e qualidade de origem, mas nao e
        # futuro. Nem alvo nem invalidacao podem nascer com duracao zero.
        if timestamp_ns <= amostra.timestamp_ns:
            return
        if (
            horizonte.alvo_timestamp_ns is None
            and amostra.alvo_preco_ticks is not None
            and _tocou(amostra.direcao, price_ticks, amostra.alvo_preco_ticks, alvo=True)
        ):
            horizonte.alvo_timestamp_ns = timestamp_ns
        if (
            horizonte.invalidacao_timestamp_ns is None
            and amostra.invalidacao_preco_ticks is not None
            and _tocou(
                amostra.direcao,
                price_ticks,
                amostra.invalidacao_preco_ticks,
                alvo=False,
            )
        ):
            horizonte.invalidacao_timestamp_ns = timestamp_ns

    def _fechar(
        self, pendente: _Pendente, horizonte: _Horizonte, censurada: bool
    ) -> dict:
        a = pendente.amostra
        atraso_ns = max(0, horizonte.limite_ns - horizonte.ultimo_timestamp_ns)
        if censurada:
            qualidade = QualidadeRotulo.CENSURADA
        elif atraso_ns <= self.config.tolerancia_qualidade_ns:
            qualidade = QualidadeRotulo.COMPLETA
        else:
            qualidade = QualidadeRotulo.PARCIAL

        retorno = horizonte.ultimo_preco - a.price_ticks
        if a.direcao is Side.BUY:
            retorno_direcional = retorno
            mfe = horizonte.maximo - a.price_ticks
            mae = a.price_ticks - horizonte.minimo
        elif a.direcao is Side.SELL:
            retorno_direcional = -retorno
            mfe = a.price_ticks - horizonte.minimo
            mae = horizonte.maximo - a.price_ticks
        else:
            retorno_direcional = None
            # Sem lado publicado, as excursoes continuam sendo labels uteis:
            # MFE/MAE descrevem a hipotese compradora, explicitada pelo campo
            # ``referencia_excursao`` para nao fingir uma direcao inexistente.
            mfe = horizonte.maximo - a.price_ticks
            mae = a.price_ticks - horizonte.minimo

        return {
            "schema_versao": SCHEMA_VERSAO,
            "tipo": "label_futuro",
            "id_amostra": pendente.id_amostra,
            "symbol": a.symbol,
            "data_amostra": pendente.data_amostra,
            "timestamp_amostra_ns": a.timestamp_ns,
            "horizonte_s": horizonte.segundos,
            "limite_horizonte_ns": horizonte.limite_ns,
            "timestamp_final_observado_ns": horizonte.ultimo_timestamp_ns,
            "duracao_horizonte_ns": horizonte.segundos * 1_000_000_000,
            "duracao_observada_ns": horizonte.ultimo_timestamp_ns - a.timestamp_ns,
            "price_inicial_ticks": a.price_ticks,
            "price_final_ticks": horizonte.ultimo_preco,
            "estado_na_amostra": a.estado,
            "direcao_na_amostra": a.direcao.value if a.direcao else None,
            "alvo_preco_ticks": a.alvo_preco_ticks,
            "invalidacao_preco_ticks": a.invalidacao_preco_ticks,
            "min_price_ticks": horizonte.minimo,
            "max_price_ticks": horizonte.maximo,
            "retorno_ticks": retorno,
            "retorno_direcional_ticks": retorno_direcional,
            "mfe_ticks": mfe,
            "mae_ticks": mae,
            "referencia_excursao": (
                "DIRECAO_SINAL" if a.direcao is not None else "HIPOTESE_BUY"
            ),
            "alvo_atingido": horizonte.alvo_timestamp_ns is not None,
            "invalidacao_atingida": horizonte.invalidacao_timestamp_ns is not None,
            "alvo_timestamp_ns": horizonte.alvo_timestamp_ns,
            "invalidacao_timestamp_ns": horizonte.invalidacao_timestamp_ns,
            "primeiro_toque": _primeiro_toque(horizonte),
            "duracao_ate_alvo_ns": _duracao(a, horizonte.alvo_timestamp_ns),
            "duracao_ate_invalidacao_ns": _duracao(
                a, horizonte.invalidacao_timestamp_ns
            ),
            "qualidade": qualidade.value,
            "atraso_endpoint_ns": atraso_ns,
            "qualidade_origem": dict(a.qualidade_origem),
            "qualidade_feed_horizonte": horizonte.qualidade_feed.registro(),
            "causal": True,
            "modo": "shadow",
            "promocao_automatica": False,
            "config_versao": self.config.config_versao,
        }


def _duracao(amostra: AmostraFeatures, timestamp_ns: int | None) -> int | None:
    return None if timestamp_ns is None else timestamp_ns - amostra.timestamp_ns


def _tocou(direcao: Side | None, price: int, nivel: int, *, alvo: bool) -> bool:
    if direcao is Side.BUY:
        return price >= nivel if alvo else price <= nivel
    if direcao is Side.SELL:
        return price <= nivel if alvo else price >= nivel
    return price == nivel


def _primeiro_toque(horizonte: _Horizonte) -> str:
    alvo = horizonte.alvo_timestamp_ns
    invalidacao = horizonte.invalidacao_timestamp_ns
    if alvo is None and invalidacao is None:
        return "NENHUM"
    if alvo is not None and invalidacao is not None:
        if alvo == invalidacao:
            return "EMPATE"
        return "ALVO" if alvo < invalidacao else "INVALIDACAO"
    return "ALVO" if alvo is not None else "INVALIDACAO"


def _valor_texto(valor: object) -> str:
    if isinstance(valor, Enum):
        valor = valor.value
    return str(valor).strip().upper()


def _estado_qualidade(snapshot: Mapping[str, object]) -> str:
    bruto = next(
        (snapshot[chave] for chave in ("state", "estado", "feed") if chave in snapshot),
        None,
    )
    texto = _valor_texto(bruto) if bruto is not None else ""
    if texto in {"OK", "CONNECTED", "CONECTADO", "HEALTHY", "SAUDAVEL"}:
        return "OK"
    if texto in {"DEGRADED", "DEGRADADO", "DEGRADADA", "DELAYED", "ATRASADO"}:
        return "DEGRADADA"
    if texto in {"ERROR", "ERRO", "CLOSED", "ENCERRADO", "STOPPED", "PARADO"}:
        return "ERRO"
    return "DESCONHECIDA"


def _rank_qualidade(estado: str) -> int:
    return {"OK": 0, "DESCONHECIDA": 1, "DEGRADADA": 2, "ERRO": 3}[estado]


def _inteiro_qualidade(
    snapshot: Mapping[str, object], *chaves: str
) -> int | None:
    for chave in chaves:
        valor = snapshot.get(chave)
        if type(valor) is int and valor >= 0:
            return valor
    return None
