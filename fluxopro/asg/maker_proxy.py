"""MakerProxy transparente sobre trades e detectores existentes.

O proxy agrega cinco leituras publicas e independentes. Pesos sao
renormalizados somente entre componentes com cobertura naquele instante;
assim a ausencia de book nao vira voto neutro silencioso. Cobertura continua
publicada separadamente para impedir que um unico componente pareca uma
leitura completa.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao

from .modelos import (
    ComponenteMaker,
    ConfigMakerProxy,
    EstadoMaker,
    MakerComponentScore,
    MakerEvidence,
    MakerProxySnapshot,
    ProcedenciaASG,
    congelar_detalhes,
)


@dataclass(frozen=True, slots=True)
class _TradeRetido:
    timestamp_ns: int
    qty: int
    sinal: int
    price: int


_COMPONENTE_POR_DETECCAO: dict[TipoDeteccao, ComponenteMaker] = {
    TipoDeteccao.ABSORCAO: ComponenteMaker.ABSORCAO,
    TipoDeteccao.ESCORA: ComponenteMaker.REPOSICAO,
    TipoDeteccao.ICEBERG: ComponenteMaker.REPOSICAO,
    TipoDeteccao.EXAUSTAO: ComponenteMaker.DIVERGENCIA,
    TipoDeteccao.LIQUIDEZ_FANTASMA: ComponenteMaker.DIVERGENCIA,
    TipoDeteccao.CLIP_INSTITUCIONAL: ComponenteMaker.CLIPS,
}


def _sinal(side: Side) -> int:
    return 1 if side is Side.BUY else -1


def _procedencia(valor: object) -> ProcedenciaASG:
    texto = str(getattr(valor, "value", valor) or "").upper()
    if texto in {"OBSERVADA", "MBO"}:
        return ProcedenciaASG.OBSERVADA
    if texto in {"INFERIDA", "MBP_INFERIDO"}:
        return ProcedenciaASG.INFERIDA
    if texto == "MISTA":
        return ProcedenciaASG.MISTA
    return ProcedenciaASG.DESCONHECIDA


class MakerProxy:
    """Agregador consultivo com memoria limitada e evidencia por componente."""

    __slots__ = (
        "symbol",
        "config",
        "_trades",
        "_evidencias",
        "_historico",
        "_timestamp_ns",
        "_volume_total",
        "_volume_atribuido",
        "_delta_agressao",
    )

    def __init__(self, symbol: str, config: ConfigMakerProxy | None = None) -> None:
        if not symbol:
            raise ValueError("symbol nao pode ser vazio")
        self.symbol = symbol
        self.config = config or ConfigMakerProxy()
        self._trades: deque[_TradeRetido] = deque(maxlen=self.config.max_trades_retidos)
        self._evidencias: dict[ComponenteMaker, deque[MakerEvidence]] = {
            componente: deque(maxlen=self.config.max_evidencias_por_componente)
            for componente in ComponenteMaker
            if componente is not ComponenteMaker.AGRESSAO
        }
        self._historico: deque[float] = deque(
            maxlen=self.config.max_amostras_persistencia
        )
        self._timestamp_ns = 0
        self._volume_total = 0
        self._volume_atribuido = 0
        self._delta_agressao = 0

    def iniciar_nova_sessao(self) -> None:
        self._trades.clear()
        for janela in self._evidencias.values():
            janela.clear()
        self._historico.clear()
        self._timestamp_ns = 0
        self._volume_total = 0
        self._volume_atribuido = 0
        self._delta_agressao = 0

    @property
    def n_trades_retidos(self) -> int:
        return len(self._trades)

    @property
    def n_evidencias_retidas(self) -> int:
        return sum(len(janela) for janela in self._evidencias.values())

    @property
    def n_amostras_persistencia(self) -> int:
        return len(self._historico)

    def ao_trade(self, trade: Trade) -> MakerProxySnapshot | None:
        """Incorpora um trade do simbolo e publica exatamente um novo retrato."""
        if trade.symbol != self.symbol:
            return None
        if not isinstance(trade.price, int) or isinstance(trade.price, bool):
            raise TypeError("trade.price deve ser int em ticks (nunca float)")
        if trade.qty < 0:
            raise ValueError("trade.qty deve ser >= 0")
        if trade.side_agressor is AgressorSide.BUY:
            sinal = 1
        elif trade.side_agressor is AgressorSide.SELL:
            sinal = -1
        else:
            sinal = 0
        if len(self._trades) == self._trades.maxlen:
            self._remover_trade(self._trades.popleft())
        retido = _TradeRetido(trade.timestamp_ns, trade.qty, sinal, trade.price)
        self._trades.append(retido)
        self._volume_total += retido.qty
        if retido.sinal:
            self._volume_atribuido += retido.qty
            self._delta_agressao += retido.qty * retido.sinal
        self._avancar_relogio(trade.timestamp_ns)
        return self._snapshot(registrar_persistencia=True)

    def ao_deteccao(self, deteccao: Deteccao) -> MakerProxySnapshot | None:
        """Adapta a saida publica dos detectores sem depender do estado interno deles."""
        if deteccao.symbol != self.symbol:
            return None
        componente = _COMPONENTE_POR_DETECCAO.get(deteccao.tipo)
        if componente is None:
            return None

        # Exaustao e liquidez que desaparece sao divergencias: a hipotese
        # direcional do proxy e oposta ao lado publicado pelo detector. Esta
        # transformacao e nossa, declarada aqui; nao e atribuida a ASG.
        multiplicador = -1 if componente is ComponenteMaker.DIVERGENCIA else 1
        evidencia_detector = deteccao.evidencia
        procedencia = _procedencia(evidencia_detector.get("procedencia"))
        fonte = str(evidencia_detector.get("fonte") or "DESCONHECIDA")
        evidencia = MakerEvidence(
            timestamp_ns=deteccao.timestamp_ns,
            symbol=deteccao.symbol,
            componente=componente,
            pontuacao=float(_sinal(deteccao.side) * multiplicador),
            confianca=float(max(0.0, min(1.0, deteccao.confianca))),
            procedencia=procedencia,
            fonte=fonte,
            tipo_evento=deteccao.tipo.value,
            preco_ticks=deteccao.price,
            detalhes=congelar_detalhes(evidencia_detector),
        )
        return self.registrar_evidencia(evidencia)

    def registrar_evidencia(
        self, evidencia: MakerEvidence
    ) -> MakerProxySnapshot | None:
        """Ponto de extensao auditavel para componentes que ja chegam normalizados."""
        if evidencia.symbol != self.symbol:
            return None
        if evidencia.componente is ComponenteMaker.AGRESSAO:
            raise ValueError("AGRESSAO e derivada de Trade; use ao_trade")
        self._evidencias[evidencia.componente].append(evidencia)
        self._avancar_relogio(evidencia.timestamp_ns)
        return self._snapshot(registrar_persistencia=True)

    def snapshot(self, timestamp_ns: int | None = None) -> MakerProxySnapshot:
        """Consulta pura; nao cria amostra artificial de persistencia."""
        if timestamp_ns is not None:
            if timestamp_ns < 0:
                raise ValueError("timestamp_ns deve ser >= 0")
            self._avancar_relogio(timestamp_ns)
        return self._snapshot(registrar_persistencia=False)

    ler = snapshot

    def _avancar_relogio(self, timestamp_ns: int) -> None:
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns deve ser >= 0")
        if timestamp_ns > self._timestamp_ns:
            self._timestamp_ns = timestamp_ns
        self._expirar()

    def _expirar(self) -> None:
        limite_trade = self._timestamp_ns - self.config.janela_agressao_ns
        while self._trades and self._trades[0].timestamp_ns < limite_trade:
            self._remover_trade(self._trades.popleft())
        limite_evidencia = self._timestamp_ns - self.config.janela_evidencia_ns
        for janela in self._evidencias.values():
            while janela and janela[0].timestamp_ns < limite_evidencia:
                janela.popleft()

    def _remover_trade(self, trade: _TradeRetido) -> None:
        self._volume_total -= trade.qty
        if trade.sinal:
            self._volume_atribuido -= trade.qty
            self._delta_agressao -= trade.qty * trade.sinal

    def _score_agressao(self) -> tuple[float, float, MakerEvidence | None, int]:
        if not self._trades:
            return 0.0, 0.0, None, 0
        volume_total = self._volume_total
        if volume_total <= 0:
            return 0.0, 0.0, None, len(self._trades)
        volume_atribuido = self._volume_atribuido
        delta = self._delta_agressao
        score_bruto = delta / max(volume_atribuido, 1)
        maturidade = min(1.0, volume_atribuido / self.config.volume_referencia_agressao)
        confianca = (volume_atribuido / volume_total) * maturidade
        ultimo = self._trades[-1]
        evidencia = MakerEvidence(
            timestamp_ns=ultimo.timestamp_ns,
            symbol=self.symbol,
            componente=ComponenteMaker.AGRESSAO,
            pontuacao=max(-1.0, min(1.0, score_bruto)),
            confianca=confianca,
            procedencia=ProcedenciaASG.OBSERVADA,
            fonte="TAPE",
            tipo_evento="JANELA_AGRESSAO",
            preco_ticks=ultimo.price,
            detalhes=congelar_detalhes(
                {
                    "delta_atribuido": delta,
                    "n_trades": len(self._trades),
                    "volume_atribuido": volume_atribuido,
                    "volume_total": volume_total,
                }
            ),
        )
        return evidencia.pontuacao, confianca, evidencia, len(self._trades)

    @staticmethod
    def _agregar_evidencias(
        evidencias: tuple[MakerEvidence, ...],
    ) -> tuple[float, float]:
        if not evidencias:
            return 0.0, 0.0
        soma_confianca = sum(item.confianca for item in evidencias)
        if soma_confianca > 0:
            score = sum(item.pontuacao * item.confianca for item in evidencias) / soma_confianca
        else:
            score = sum(item.pontuacao for item in evidencias) / len(evidencias)
        # Evidencias repetidas nao fabricam certeza: usa a media, nao soma.
        confianca = soma_confianca / len(evidencias)
        return max(-1.0, min(1.0, score)), max(0.0, min(1.0, confianca))

    @staticmethod
    def _combinar_procedencia(evidencias: tuple[MakerEvidence, ...]) -> ProcedenciaASG:
        if not evidencias:
            return ProcedenciaASG.DESCONHECIDA
        valores = {item.procedencia for item in evidencias}
        if valores == {ProcedenciaASG.OBSERVADA}:
            return ProcedenciaASG.OBSERVADA
        if valores == {ProcedenciaASG.INFERIDA}:
            return ProcedenciaASG.INFERIDA
        if valores == {ProcedenciaASG.DESCONHECIDA}:
            return ProcedenciaASG.DESCONHECIDA
        return ProcedenciaASG.MISTA

    def _persistencia(self, score_atual: float) -> float:
        if not self._historico:
            return 0.0
        limiar = self.config.limiar_componente_ativo
        if abs(score_atual) <= limiar:
            return sum(abs(item) <= limiar for item in self._historico) / len(self._historico)
        sinal_atual = 1 if score_atual > 0 else -1
        return sum(
            1 for item in self._historico if item * sinal_atual > limiar
        ) / len(self._historico)

    def _snapshot(self, *, registrar_persistencia: bool) -> MakerProxySnapshot:
        self._expirar()
        temporarios: list[tuple[ComponenteMaker, float, float, tuple[MakerEvidence, ...], int]] = []

        score, confianca, evidencia, n_trades = self._score_agressao()
        evidencias_agressao = (evidencia,) if evidencia is not None else ()
        temporarios.append(
            (ComponenteMaker.AGRESSAO, score, confianca, evidencias_agressao, n_trades)
        )
        for componente in ComponenteMaker:
            if componente is ComponenteMaker.AGRESSAO:
                continue
            evidencias = tuple(self._evidencias[componente])
            score, confianca = self._agregar_evidencias(evidencias)
            temporarios.append((componente, score, confianca, evidencias, len(evidencias)))

        disponiveis = [
            item
            for item in temporarios
            if item[4] > 0 and self.config.peso_de(item[0]) > 0
        ]
        peso_disponivel = sum(self.config.peso_de(item[0]) for item in disponiveis)
        cobertura = peso_disponivel / self.config.peso_total

        componentes: list[MakerComponentScore] = []
        todas_evidencias: list[MakerEvidence] = []
        for componente, score, confianca, evidencias, n_evidencias in temporarios:
            peso = self.config.peso_de(componente)
            peso_efetivo = peso / peso_disponivel if n_evidencias and peso_disponivel else 0.0
            todas_evidencias.extend(evidencias)
            componentes.append(
                MakerComponentScore(
                    componente=componente,
                    pontuacao=score,
                    peso_configurado=peso,
                    peso_efetivo=peso_efetivo,
                    confianca=confianca,
                    cobertura=1.0 if n_evidencias else 0.0,
                    n_evidencias=n_evidencias,
                    ultimo_timestamp_ns=(evidencias[-1].timestamp_ns if evidencias else None),
                    evidencias=evidencias,
                    procedencia=self._combinar_procedencia(evidencias),
                    formula_version=self.config.formula_version,
                )
            )

        pontuacao = sum(item.pontuacao * item.peso_efetivo for item in componentes)
        confianca_total = sum(item.confianca * item.peso_efetivo for item in componentes)
        pontuacao = max(-1.0, min(1.0, pontuacao))
        if registrar_persistencia and peso_disponivel:
            self._historico.append(pontuacao)
        persistencia = self._persistencia(pontuacao)

        if not peso_disponivel:
            estado = EstadoMaker.SEM_DADOS
            direcao = None
        elif pontuacao >= self.config.limiar_direcional:
            estado = EstadoMaker.COMPRADOR
            direcao = Side.BUY
        elif pontuacao <= -self.config.limiar_direcional:
            estado = EstadoMaker.VENDEDOR
            direcao = Side.SELL
        else:
            sinais = {
                1 if item.pontuacao > self.config.limiar_componente_ativo else -1
                for item in componentes
                if abs(item.pontuacao) > self.config.limiar_componente_ativo
                and item.peso_efetivo > 0
            }
            estado = EstadoMaker.DIVERGENTE if len(sinais) > 1 else EstadoMaker.NEUTRO
            direcao = None

        return MakerProxySnapshot(
            timestamp_ns=self._timestamp_ns,
            symbol=self.symbol,
            estado=estado,
            direcao=direcao,
            pontuacao=pontuacao,
            confianca=max(0.0, min(1.0, confianca_total)),
            cobertura=max(0.0, min(1.0, cobertura)),
            persistencia=max(0.0, min(1.0, persistencia)),
            componentes=tuple(componentes),
            procedencia=self._combinar_procedencia(tuple(todas_evidencias)),
            formula_version=self.config.formula_version,
        )


__all__ = ["MakerProxy"]
