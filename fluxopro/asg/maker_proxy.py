"""MakerProxy independente, auditavel e limitado em memoria."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.dados.qualidade import (
    AggressorQuality,
    BookKind,
    FeedQualitySnapshot,
    FeedState,
)
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao

from .modelos import (
    ComponenteMaker,
    ConfigMakerProxy,
    EstadoMaker,
    MakerComponentScore,
    MakerEvidence,
    MakerProxySnapshot,
    ProcedenciaASG,
    congelar,
)


@dataclass(frozen=True, slots=True)
class _TradeRetido:
    timestamp_ns: int
    qty: int
    sinal: int
    price: int


_COMPONENTE_POR_DETECCAO = {
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
    """Agrega trades, detectores e saude do feed sem executar qualquer acao externa."""

    __slots__ = (
        "symbol", "config", "_trades", "_evidencias", "_historico",
        "_trade_ids", "_trade_ids_fila", "_timestamp_ns",
        "_last_market_timestamp_ns", "_last_feed_timestamp_ns", "_feed",
        "_feed_health", "_feed_temporalmente_valido",
        "_volume_total", "_volume_atribuido", "_delta_agressao",
        "_regime_side", "_regime_since_ns", "_regime_last_ns",
        "_descartados_duplicados", "_descartados_regressivos",
    )

    def __init__(self, symbol: str, config: ConfigMakerProxy | None = None) -> None:
        if not symbol:
            raise ValueError("symbol nao pode ser vazio")
        self.symbol = symbol
        self.config = config or ConfigMakerProxy()
        self._trades: deque[_TradeRetido] = deque()
        self._evidencias = {
            componente: deque(maxlen=self.config.max_evidencias_por_componente)
            for componente in ComponenteMaker if componente is not ComponenteMaker.AGRESSAO
        }
        self._historico: deque[tuple[int, int]] = deque(
            maxlen=self.config.max_amostras_persistencia
        )
        self._trade_ids: set[str] = set()
        self._trade_ids_fila: deque[str] = deque()
        self._timestamp_ns = 0
        self._last_market_timestamp_ns: int | None = None
        self._last_feed_timestamp_ns: int | None = None
        self._feed: FeedQualitySnapshot | None = None
        self._feed_health: FeedQualitySnapshot | None = None
        self._feed_temporalmente_valido = True
        self._volume_total = 0
        self._volume_atribuido = 0
        self._delta_agressao = 0
        self._regime_side: int | None = None
        self._regime_since_ns: int | None = None
        self._regime_last_ns: int | None = None
        self._descartados_duplicados = 0
        self._descartados_regressivos = 0

    def iniciar_nova_sessao(self) -> None:
        self._trades.clear()
        for janela in self._evidencias.values():
            janela.clear()
        self._historico.clear()
        self._trade_ids.clear()
        self._trade_ids_fila.clear()
        self._timestamp_ns = 0
        self._last_market_timestamp_ns = None
        self._last_feed_timestamp_ns = None
        self._feed = None
        self._feed_health = None
        self._feed_temporalmente_valido = True
        self._volume_total = self._volume_atribuido = self._delta_agressao = 0
        self._regime_side = self._regime_since_ns = self._regime_last_ns = None
        self._descartados_duplicados = self._descartados_regressivos = 0

    @property
    def n_trades_retidos(self) -> int:
        return len(self._trades)

    @property
    def n_evidencias_retidas(self) -> int:
        return sum(len(janela) for janela in self._evidencias.values())

    @property
    def n_amostras_persistencia(self) -> int:
        return len(self._historico)

    @property
    def n_trade_ids_retidos(self) -> int:
        return len(self._trade_ids)

    def _aceitar_timestamp_mercado(self, timestamp_ns: int) -> bool:
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns deve ser >= 0")
        if timestamp_ns < self._timestamp_ns:
            self._descartados_regressivos += 1
            return False
        self._last_market_timestamp_ns = timestamp_ns
        self._timestamp_ns = max(self._timestamp_ns, timestamp_ns)
        return True

    def _registrar_trade_id(self, trade_id: str) -> None:
        if not trade_id:
            return
        if len(self._trade_ids_fila) >= self.config.max_trade_ids_retidos:
            antigo = self._trade_ids_fila.popleft()
            self._trade_ids.discard(antigo)
        self._trade_ids.add(trade_id)
        self._trade_ids_fila.append(trade_id)

    def ao_trade(self, trade: Trade) -> MakerProxySnapshot | None:
        return self._ingerir_trade(trade, produzir_snapshot=True)

    def ingerir_trade(self, trade: Trade) -> bool:
        """Hot path: atualiza estado sem materializar o snapshot derivado."""

        return bool(self._ingerir_trade(trade, produzir_snapshot=False))

    def _ingerir_trade(
        self, trade: Trade, *, produzir_snapshot: bool
    ) -> MakerProxySnapshot | bool | None:
        if trade.symbol != self.symbol:
            return None if produzir_snapshot else False
        if not isinstance(trade.price, int) or isinstance(trade.price, bool):
            raise TypeError("trade.price deve ser int em ticks")
        if trade.qty < 0:
            raise ValueError("trade.qty deve ser >= 0")
        # ID vence timestamp: retransmissao antiga continua classificada como duplicata.
        if trade.trade_id and trade.trade_id in self._trade_ids:
            self._descartados_duplicados += 1
            return (
                self._snapshot(registrar_persistencia=False)
                if produzir_snapshot else False
            )
        if not self._aceitar_timestamp_mercado(trade.timestamp_ns):
            return (
                self._snapshot(registrar_persistencia=False)
                if produzir_snapshot else False
            )
        self._registrar_trade_id(trade.trade_id)
        sinal = (
            1 if trade.side_agressor is AgressorSide.BUY
            else -1 if trade.side_agressor is AgressorSide.SELL else 0
        )
        if len(self._trades) >= self.config.max_trades_retidos:
            self._remover_trade(self._trades.popleft())
        retido = _TradeRetido(trade.timestamp_ns, trade.qty, sinal, trade.price)
        self._trades.append(retido)
        self._volume_total += retido.qty
        if sinal:
            self._volume_atribuido += retido.qty
            self._delta_agressao += retido.qty * sinal
        self._expirar()
        # ``ingerir_trade`` e o caminho usado pela sessão em produção: ele
        # evita alocar snapshots por tick. Ainda assim, persistência e
        # estabilidade são parte do estado causal do Maker e precisam avançar
        # em cada trade aceito; deixar isso apenas em ``ao_trade`` fazia o
        # Maker ficar eternamente em AJUSTANDO no feed normal.
        self._atualizar_persistencia(self._score_corrente())
        return (
            self._snapshot(registrar_persistencia=False)
            if produzir_snapshot else True
        )

    def ao_deteccao(self, deteccao: Deteccao) -> MakerProxySnapshot | None:
        if deteccao.symbol != self.symbol:
            return None
        componente = _COMPONENTE_POR_DETECCAO.get(deteccao.tipo)
        if componente is None:
            return None
        if not self._aceitar_timestamp_mercado(deteccao.timestamp_ns):
            return self._snapshot(registrar_persistencia=False)
        multiplicador = -1 if componente is ComponenteMaker.DIVERGENCIA else 1
        evidencia = MakerEvidence(
            timestamp_ns=deteccao.timestamp_ns,
            symbol=deteccao.symbol,
            componente=componente,
            pontuacao=float(_sinal(deteccao.side) * multiplicador),
            confianca=float(max(0.0, min(1.0, deteccao.confianca))),
            procedencia=_procedencia(deteccao.evidencia.get("procedencia")),
            fonte=str(deteccao.evidencia.get("fonte") or "DESCONHECIDA"),
            tipo_evento=deteccao.tipo.value,
            preco_ticks=deteccao.price,
            detalhes=congelar(deteccao.evidencia),
            formula_version=self.config.formula_version,
        )
        self._evidencias[componente].append(evidencia)
        self._expirar()
        return self._snapshot(registrar_persistencia=True)

    def registrar_evidencia(self, evidencia: MakerEvidence) -> MakerProxySnapshot | None:
        if evidencia.symbol != self.symbol:
            return None
        if evidencia.componente is ComponenteMaker.AGRESSAO:
            raise ValueError("AGRESSAO deriva de Trade; use ao_trade")
        if not self._aceitar_timestamp_mercado(evidencia.timestamp_ns):
            return self._snapshot(registrar_persistencia=False)
        self._evidencias[evidencia.componente].append(evidencia)
        self._expirar()
        return self._snapshot(registrar_persistencia=True)

    def ao_feed_quality(self, feed: FeedQualitySnapshot) -> MakerProxySnapshot | None:
        return self._ingerir_feed_quality(feed, produzir_snapshot=True)

    def ingerir_feed_quality(self, feed: FeedQualitySnapshot) -> bool:
        """Hot path equivalente a :meth:`ao_feed_quality`, sem alocação."""

        return bool(self._ingerir_feed_quality(feed, produzir_snapshot=False))

    def _ingerir_feed_quality(
        self, feed: FeedQualitySnapshot, *, produzir_snapshot: bool
    ) -> MakerProxySnapshot | bool | None:
        if feed.symbol != self.symbol:
            return None if produzir_snapshot else False

        # ``timestamp_ns`` era historicamente um alias do relogio de ingresso.
        # Ele so e causal em snapshots legados que nao expoem o relogio de
        # mercado de forma independente.
        if hasattr(feed, "market_timestamp_ns"):
            market_timestamp_ns = feed.market_timestamp_ns
        else:
            market_timestamp_ns = feed.timestamp_ns

        if market_timestamp_ns is None:
            self._feed_health = feed
            # Telemetria sem relógio causal pode ser exibida, mas nunca pode
            # sustentar confirmação. O próximo snapshot com timestamp de
            # mercado válido rearma explicitamente esta condição.
            self._feed_temporalmente_valido = False
            return (
                self._snapshot(registrar_persistencia=False)
                if produzir_snapshot else False
            )
        if not isinstance(market_timestamp_ns, int) or isinstance(
            market_timestamp_ns, bool
        ):
            raise TypeError("feed.market_timestamp_ns deve ser int ou None")
        if market_timestamp_ns < 0:
            raise ValueError("feed.market_timestamp_ns deve ser >= 0")
        if market_timestamp_ns < self._timestamp_ns:
            self._descartados_regressivos += 1
            self._feed_temporalmente_valido = False
            return (
                self._snapshot(registrar_persistencia=False)
                if produzir_snapshot else False
            )

        self._last_feed_timestamp_ns = market_timestamp_ns
        self._timestamp_ns = market_timestamp_ns
        self._feed = feed
        self._feed_health = feed
        self._feed_temporalmente_valido = True
        self._expirar()
        return (
            self._snapshot(registrar_persistencia=False)
            if produzir_snapshot else True
        )

    atualizar_feed_quality = ao_feed_quality

    def snapshot(self, timestamp_ns: int | None = None) -> MakerProxySnapshot:
        # Mantem o argumento por compatibilidade, mas uma leitura local nao
        # possui procedencia de mercado e portanto jamais avanca o relogio.
        _ = timestamp_ns
        self._expirar()
        return self._snapshot(registrar_persistencia=False)

    ler = snapshot

    def _remover_trade(self, trade: _TradeRetido) -> None:
        self._volume_total -= trade.qty
        if trade.sinal:
            self._volume_atribuido -= trade.qty
            self._delta_agressao -= trade.qty * trade.sinal

    def _expirar(self) -> None:
        limite = self._timestamp_ns - int(self.config.janela_agressao_ns)
        while self._trades and self._trades[0].timestamp_ns < limite:
            self._remover_trade(self._trades.popleft())
        for componente, janela in self._evidencias.items():
            limite = self._timestamp_ns - self.config.janela_de(componente)
            while janela and janela[0].timestamp_ns < limite:
                janela.popleft()
        limite_hist = self._timestamp_ns - self.config.janela_contexto_ns
        while self._historico and self._historico[0][0] < limite_hist:
            self._historico.popleft()

    def _evidencia_agressao(self) -> MakerEvidence | None:
        if not self._trades or self._volume_total <= 0:
            return None
        score = self._delta_agressao / max(self._volume_atribuido, 1)
        maturidade = min(1.0, self._volume_atribuido / self.config.volume_referencia_agressao)
        confianca = (self._volume_atribuido / self._volume_total) * maturidade
        ultimo = self._trades[-1]
        return MakerEvidence(
            timestamp_ns=ultimo.timestamp_ns,
            symbol=self.symbol,
            componente=ComponenteMaker.AGRESSAO,
            pontuacao=max(-1.0, min(1.0, score)),
            confianca=max(0.0, min(1.0, confianca)),
            procedencia=ProcedenciaASG.OBSERVADA,
            fonte="TAPE",
            tipo_evento="JANELA_AGRESSAO",
            preco_ticks=ultimo.price,
            detalhes={
                "janela_ns": self.config.janela_micro_ns,
                "delta_atribuido": self._delta_agressao,
                "n_trades": len(self._trades),
                "volume_atribuido": self._volume_atribuido,
                "volume_total": self._volume_total,
            },
            formula_version=self.config.formula_version,
        )

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

    def _componente(
        self, componente: ComponenteMaker, evidencias: tuple[MakerEvidence, ...]
    ) -> tuple[float, float, float, bool, MakerComponentScore]:
        relevantes = tuple(e for e in evidencias if e.confianca >= self.config.confianca_minima)
        buy = sum(e.evidence_buy for e in relevantes)
        sell = sum(e.evidence_sell for e in relevantes)
        disponivel = bool(relevantes)
        score = (buy - sell) / (buy + sell + 1e-12) if disponivel else 0.0
        confianca = (
            sum(e.confianca for e in relevantes) / len(relevantes) if relevantes else 0.0
        )
        peso = self.config.peso_de(componente)
        item = MakerComponentScore(
            componente=componente,
            pontuacao=max(-1.0, min(1.0, score)),
            peso_configurado=peso,
            peso_efetivo=0.0,
            confianca=confianca,
            cobertura=1.0 if disponivel else 0.0,
            n_evidencias=len(evidencias),
            ultimo_timestamp_ns=evidencias[-1].timestamp_ns if evidencias else None,
            evidencias=evidencias,
            procedencia=self._combinar_procedencia(evidencias),
            formula_version=self.config.formula_version,
            evidencia_buy=buy,
            evidencia_sell=sell,
            percent=score * 100.0,
            janela_ns=self.config.janela_de(componente),
            disponivel=disponivel,
        )
        return score, confianca, peso, disponivel, item

    def _score_corrente(self) -> float:
        """Pontuação ponderada sem materializar o snapshot público.

        Esta versão reduzida é usada exclusivamente para atualizar a série de
        persistência no hot path. Ela preserva a mesma regra de cobertura e
        renormalização de :meth:`_snapshot`, mas não cria evidências, scores ou
        tuplas que a UI não consumirá naquele tick.
        """

        # No fluxo normal, apenas agressão está presente entre os cinco
        # componentes. Evitar criar ``MakerEvidence`` por tick mantém a
        # correção causal sem transformar a persistência em um snapshot
        # disfarçado.
        if not any(self._evidencias.values()):
            if not self._trades or self._volume_total <= 0:
                return 0.0
            volume_atribuido = self._volume_atribuido
            if volume_atribuido <= 0:
                return 0.0
            confianca = (volume_atribuido / self._volume_total) * min(
                1.0, volume_atribuido / self.config.volume_referencia_agressao
            )
            if confianca < self.config.confianca_minima:
                return 0.0
            return max(
                -1.0,
                min(1.0, self._delta_agressao / max(volume_atribuido, 1)),
            )

        evidencia_agressao = self._evidencia_agressao()
        peso_disponivel = 0.0
        pontuacao_ponderada = 0.0
        for componente in ComponenteMaker:
            evidencias = (
                (evidencia_agressao,) if componente is ComponenteMaker.AGRESSAO and evidencia_agressao
                else () if componente is ComponenteMaker.AGRESSAO
                else self._evidencias[componente]
            )
            compra = venda = 0.0
            n_relevantes = 0
            for evidencia in evidencias:
                if evidencia.confianca < self.config.confianca_minima:
                    continue
                compra += evidencia.evidence_buy
                venda += evidencia.evidence_sell
                n_relevantes += 1
            if not n_relevantes:
                continue
            score = (compra - venda) / (compra + venda + 1e-12)
            peso = self.config.peso_de(componente)
            peso_disponivel += peso
            pontuacao_ponderada += score * peso
        if not peso_disponivel:
            return 0.0
        return max(-1.0, min(1.0, pontuacao_ponderada / peso_disponivel))

    def _atualizar_persistencia(self, score: float) -> None:
        limiar = self.config.relevancia_minima
        lado = 1 if score >= limiar else -1 if score <= -limiar else 0
        ts = self._last_market_timestamp_ns if self._last_market_timestamp_ns is not None else 0
        if self._regime_since_ns is None or lado != self._regime_side:
            self._regime_side = lado
            self._regime_since_ns = ts
        self._regime_last_ns = ts
        self._historico.append((ts, lado))

    def _metricas_persistencia(self, score: float) -> tuple[int, float]:
        if self._regime_since_ns is None or self._regime_last_ns is None:
            return 0, 0.0
        persistence_ns = max(0, self._regime_last_ns - self._regime_since_ns)
        lado = 1 if score >= self.config.relevancia_minima else -1 if score <= -self.config.relevancia_minima else 0
        if lado != self._regime_side:
            persistence_ns = 0
        estabilidade = (
            sum(1 for _, item_lado in self._historico if item_lado == lado) / len(self._historico)
            if self._historico else 0.0
        )
        return persistence_ns, estabilidade

    def _qualidade_feed(self, inferred_evidence: bool) -> tuple[float, str, str, bool, bool]:
        feed = self._feed_health or self._feed
        if feed is None:
            return 0.0, "UNKNOWN", "NONE", inferred_evidence, True
        source = feed.source.value.upper()
        book_kind = feed.book_kind.value.upper()
        conectado = feed.state is FeedState.CONNECTED
        # Replay e simulador usam relógio lógico e deliberadamente não
        # publicam latência de rede. `None` só bloqueia uma fonte externa/ao
        # vivo que deveria ter relógios comparáveis (MT5/OTHER).
        latencia_desconhecida = (
            feed.latency_ns is None and source not in {"REPLAY", "SIMULATOR"}
        )
        atrasado = (
            (not self._feed_temporalmente_valido)
            or (not conectado)
            or latencia_desconhecida
            or (
                feed.latency_ns is not None
                and feed.latency_ns > self.config.latencia_feed_max_ns
            )
        )
        qualidade = 1.0 if conectado else 0.5 if feed.state is FeedState.DEGRADED else 0.0
        inferred = inferred_evidence or feed.book_kind is BookKind.MBP or feed.aggressor_quality in {
            AggressorQuality.INFERRED, AggressorQuality.PARTIAL
        }
        if feed.book_kind is BookKind.NONE:
            qualidade = 0.0
        elif feed.book_kind is BookKind.MBP or inferred_evidence:
            qualidade *= self.config.fator_confianca_mbp
        if feed.aggressor_quality is AggressorQuality.INFERRED:
            qualidade *= 0.85
        elif feed.aggressor_quality is AggressorQuality.PARTIAL:
            qualidade *= 0.90
        elif feed.aggressor_quality is AggressorQuality.UNKNOWN:
            qualidade *= 0.50
        recebidos = int(getattr(feed, "received_events", 0))
        aceitos = int(getattr(feed, "accepted_events", 0))
        anomalias = int(getattr(feed, "anomalies", 0))
        if recebidos > 0:
            qualidade *= max(0.0, min(1.0, aceitos / recebidos))
        if anomalias > 0:
            qualidade *= max(0.0, 1.0 - anomalias / max(recebidos, anomalias))
        if atrasado:
            qualidade = 0.0
        return max(0.0, min(1.0, qualidade)), source, book_kind, inferred, atrasado

    def _snapshot(self, *, registrar_persistencia: bool) -> MakerProxySnapshot:
        self._expirar()
        bruto: list[tuple[float, float, float, bool, MakerComponentScore]] = []
        todas: list[MakerEvidence] = []
        evidencia_agressao = self._evidencia_agressao()
        for componente in ComponenteMaker:
            evidencias = (
                (evidencia_agressao,) if componente is ComponenteMaker.AGRESSAO and evidencia_agressao
                else () if componente is ComponenteMaker.AGRESSAO
                else tuple(self._evidencias[componente])
            )
            todas.extend(evidencias)
            bruto.append(self._componente(componente, evidencias))

        peso_disponivel = sum(peso for _, _, peso, disponivel, _ in bruto if disponivel)
        cobertura = peso_disponivel / self.config.peso_total
        componentes: list[MakerComponentScore] = []
        score_total = 0.0
        for score, _, peso, disponivel, item in bruto:
            efetivo = peso / peso_disponivel if disponivel and peso_disponivel else 0.0
            score_total += score * efetivo
            componentes.append(MakerComponentScore(
                componente=item.componente, pontuacao=item.pontuacao,
                peso_configurado=item.peso_configurado, peso_efetivo=efetivo,
                confianca=item.confianca, cobertura=item.cobertura,
                n_evidencias=item.n_evidencias,
                ultimo_timestamp_ns=item.ultimo_timestamp_ns,
                evidencias=item.evidencias, procedencia=item.procedencia,
                formula_version=item.formula_version,
                evidencia_buy=item.evidencia_buy, evidencia_sell=item.evidencia_sell,
                percent=item.percent, janela_ns=item.janela_ns,
                disponivel=item.disponivel,
            ))
        score_total = max(-1.0, min(1.0, score_total))
        if registrar_persistencia and peso_disponivel:
            self._atualizar_persistencia(score_total)
        persistence_ns, stability = self._metricas_persistencia(score_total)
        inferred_evidence = any(e.procedencia is ProcedenciaASG.INFERIDA for e in todas)
        qualidade_feed, source, book_kind, inferred, atrasado = self._qualidade_feed(inferred_evidence)
        confidence = qualidade_feed * cobertura * stability
        percent = score_total * 100.0
        side = (
            Side.BUY if score_total >= self.config.relevancia_minima
            else Side.SELL if score_total <= -self.config.relevancia_minima else None
        )
        sinais = {
            1 if item.pontuacao >= self.config.relevancia_minima else -1
            for item in componentes
            if item.disponivel and abs(item.pontuacao) >= self.config.relevancia_minima
        }
        divergente = len(sinais) > 1
        tem_dados = bool(todas)
        if not tem_dados:
            estado = EstadoMaker.SEM_DADOS
        elif book_kind == "NONE" or atrasado:
            estado = EstadoMaker.SEM_BOOK
        elif (
            not peso_disponivel
            or persistence_ns < self.config.persistencia_minima_ns
            or confidence < self.config.confianca_minima
        ):
            estado = EstadoMaker.AJUSTANDO
        elif divergente:
            estado = EstadoMaker.DIVERGENTE
        elif side is None:
            estado = EstadoMaker.NEUTRO
        else:
            estado = EstadoMaker.COMPRADOR if side is Side.BUY else EstadoMaker.VENDEDOR

        todas_ordenadas = tuple(sorted(todas, key=lambda e: (e.timestamp_ns, e.componente.value)))
        procedencia = self._combinar_procedencia(todas_ordenadas)
        return MakerProxySnapshot(
            timestamp_ns=self._timestamp_ns, symbol=self.symbol, estado=estado,
            direcao=side, pontuacao=score_total, confianca=confidence,
            cobertura=cobertura,
            persistencia=min(1.0, persistence_ns / self.config.persistencia_minima_ns),
            componentes=tuple(componentes), procedencia=procedencia,
            formula_version=self.config.formula_version, percent=percent,
            persistence_ns=persistence_ns, source=source, book_kind=book_kind,
            inferred=inferred, evidence=todas_ordenadas,
            component_coverage=cobertura,
            component_availability=tuple((item.componente, item.disponivel) for item in componentes),
            feed_quality=qualidade_feed, stability=stability, book_delayed=atrasado,
            discarded_duplicates=self._descartados_duplicados,
            discarded_regressive=self._descartados_regressivos,
        )


__all__ = ["MakerProxy"]
