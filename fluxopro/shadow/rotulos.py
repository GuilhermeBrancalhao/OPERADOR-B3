"""Rotulador futuro causal e de memoria estritamente limitada."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from fluxopro.core.eventos import Side
from fluxopro.shadow.modelos import AmostraFeatures, ConfigShadow, QualidadeRotulo


@dataclass(slots=True)
class _Horizonte:
    segundos: int
    limite_ns: int
    minimo: int
    maximo: int
    ultimo_preco: int
    ultimo_timestamp_ns: int
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
                amostra, horizonte, amostra.timestamp_ns, amostra.price_ticks
            )
        fila.append(_Pendente(id_amostra, amostra, data_amostra, horizontes))
        return True

    def avancar(self, symbol: str, timestamp_ns: int, price_ticks: int) -> list[dict]:
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
                self._incorporar(pendente.amostra, horizonte, timestamp_ns, price_ticks)
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
    ) -> None:
        horizonte.minimo = min(horizonte.minimo, price_ticks)
        horizonte.maximo = max(horizonte.maximo, price_ticks)
        horizonte.ultimo_preco = price_ticks
        horizonte.ultimo_timestamp_ns = timestamp_ns
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
            "schema_versao": 1,
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
            "duracao_ate_alvo_ns": _duracao(a, horizonte.alvo_timestamp_ns),
            "duracao_ate_invalidacao_ns": _duracao(
                a, horizonte.invalidacao_timestamp_ns
            ),
            "qualidade": qualidade.value,
            "atraso_endpoint_ns": atraso_ns,
            "qualidade_origem": dict(a.qualidade_origem),
            "causal": True,
            "modo": "shadow",
            "promocao_automatica": False,
        }


def _duracao(amostra: AmostraFeatures, timestamp_ns: int | None) -> int | None:
    return None if timestamp_ns is None else timestamp_ns - amostra.timestamp_ns


def _tocou(direcao: Side | None, price: int, nivel: int, *, alvo: bool) -> bool:
    if direcao is Side.BUY:
        return price >= nivel if alvo else price <= nivel
    if direcao is Side.SELL:
        return price <= nivel if alvo else price >= nivel
    return price == nivel
