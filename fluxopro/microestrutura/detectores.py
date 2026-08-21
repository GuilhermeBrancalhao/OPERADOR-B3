"""Detectores de comportamento de player sobre o `LivroMBO`.

Cada detector é parametrizável (dataclass `Config...`, zero número mágico no
corpo) e emite um evento com `confianca: float` e `evidencia: dict` — quem lê
a saída precisa poder auditar POR QUE algo foi sinalizado, não só receber um
rótulo. Nenhum detector afirma fato onde só há hipótese: em feed agregado
(`FonteMicro.MBP_INFERIDO`) a confiança do evento de origem se propaga.

Termos usados de propósito NEUTROS: `LiquidezFantasma` em vez de "spoofing"
(acusação legal que este código não tem base para fazer).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.eventos_mbo import FonteMicro, Ordem
from fluxopro.microestrutura.livro_mbo import LivroMBO


@unique
class TipoDeteccao(Enum):
    ABSORCAO = "ABSORCAO"
    ESCORA = "ESCORA"
    ICEBERG = "ICEBERG"
    LIQUIDEZ_FANTASMA = "LIQUIDEZ_FANTASMA"
    EXAUSTAO = "EXAUSTAO"
    CLIP_INSTITUCIONAL = "CLIP_INSTITUCIONAL"


@dataclass(frozen=True, slots=True)
class Deteccao:
    timestamp_ns: int
    symbol: str
    tipo: TipoDeteccao
    side: Side
    price: int | None
    confianca: float
    evidencia: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Absorção
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigAbsorcao:
    """Agressão continuada num preço sem deslocamento além de N ticks."""

    volume_minimo: int = 300
    deslocamento_maximo_ticks: int = 1
    janela_ns: int = 5_000_000_000


@dataclass(slots=True)
class _TradeJanela:
    """Só o que a janela precisa — evita segurar o `Trade` inteiro vivo."""

    seq: int
    timestamp_ns: int
    price: int
    qty: int
    lado: AgressorSide


class DetectorAbsorcao:
    """Absorção de compra: vendedores agridem, preço não cai (e vice-versa).

    Custo: **O(1) amortizado por trade**. Cada trade entra e sai da janela
    `deque` exatamente uma vez, e `volume_buy`/`volume_sell` são contadores
    incrementais — mesmo padrão de `analytics/agressao.py`. Máximo e mínimo de
    preço na janela saem de duas *monotonic deques* (`_max_precos` decrescente,
    `_min_precos` crescente), cada uma com no máximo uma inserção e uma remoção
    amortizada por trade. A implementação anterior refazia cinco varreduras
    completas da janela por trade (expiração + max + min + duas somas), o que a
    5–10 mil trades/s significava 25–50 mil elementos varridos cinco vezes por
    evento: custo total quadrático na taxa do mercado.

    **Deduplicação (`_ja_sinalizado`).** Sem ela o detector re-emite o mesmo
    alerta a cada trade enquanto a condição durar — a crítica R1 mediu 98,2% dos
    trades sinalizados num tape lateral. Absorção é um EPISÓDIO (um player
    segurando uma faixa de preço), não um estado instantâneo, então vale um
    alerta por episódio. Diferente de `DetectorEscora`/`DetectorIceberg`, que
    usam um `set` que nunca é podado (vaza um item por nível ao longo do
    pregão), aqui basta **um único slot** `(lado_absorvedor, preço_âncora)`:
    a janela deslizante só consegue sustentar um episódio por vez.

    Regra de rearme — explícita, três gatilhos, todos significando "o episódio
    anterior acabou":

    1. **O preço deslocou** (`deslocamento > deslocamento_maximo_ticks`): a
       própria condição de absorção quebrou — quem estava segurando cedeu ou
       saiu. É o análogo direto do `discard` que `DetectorEscora` faz quando
       `n_reposicoes` cai abaixo do mínimo.
    2. **O preço-âncora saiu da faixa da janela**: o mercado migrou para outro
       preço; uma absorção no preço novo é um fenômeno novo, não a repetição
       do antigo.
    3. **A janela esvaziou** (buraco no tape ≥ `janela_ns`, ou virada de lado
       dominante): não há continuidade a preservar.

    Só rearma por evento observado — nunca por decurso de tempo isolado —, de
    modo que um episódio contínuo produz exatamente um alerta.

    PENDENTE(config): `volume_minimo` é absoluto e, na escala real do WDO
    (~125 mil lotes numa janela de 5s a 5 mil trades/s), o default de 300 é
    ultrapassado 400x e não filtra nada — o limiar deveria ser relativo ao
    volume da janela. Fora do escopo deste conserto (que é custo + dedup); o
    item está no backlog #4 da crítica R1.
    """

    def __init__(self, symbol: str, config: ConfigAbsorcao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigAbsorcao()

        self._janela: deque[_TradeJanela] = deque()
        self._volume_buy = 0
        self._volume_sell = 0
        # Monotonic deques: guardam (seq, price). `_max_precos` é decrescente e
        # `_min_precos` crescente, então o extremo da janela está sempre em [0].
        self._max_precos: deque[tuple[int, int]] = deque()
        self._min_precos: deque[tuple[int, int]] = deque()
        self._seq = 0
        # (lado que absorve, preço no momento do alerta) do episódio em curso.
        self._ja_sinalizado: tuple[Side, int] | None = None

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config

        seq = self._seq
        self._seq += 1
        self._janela.append(
            _TradeJanela(seq, trade.timestamp_ns, trade.price, trade.qty, trade.side_agressor)
        )
        if trade.side_agressor is AgressorSide.BUY:
            self._volume_buy += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            self._volume_sell += trade.qty

        preco = trade.price
        while self._max_precos and self._max_precos[-1][1] <= preco:
            self._max_precos.pop()
        self._max_precos.append((seq, preco))
        while self._min_precos and self._min_precos[-1][1] >= preco:
            self._min_precos.pop()
        self._min_precos.append((seq, preco))

        self._expirar(trade.timestamp_ns)

        if len(self._janela) == 1:
            # Gatilho 3: a janela esvaziou antes deste trade (buraco no tape
            # maior que a janela) — não há episódio anterior a continuar.
            self._ja_sinalizado = None

        preco_max = self._max_precos[0][1]
        preco_min = self._min_precos[0][1]
        deslocamento = preco_max - preco_min
        if deslocamento > cfg.deslocamento_maximo_ticks:
            # Gatilho 1: o preço deslocou — a condição de absorção quebrou.
            self._ja_sinalizado = None
            return None

        volume_buy = self._volume_buy
        volume_sell = self._volume_sell

        if volume_sell >= cfg.volume_minimo and volume_sell > volume_buy:
            # vendedores agridem, preço não cai → COMPRADOR está absorvendo
            return self._emitir(trade, Side.BUY, volume_sell, volume_buy,
                                deslocamento, preco_min, preco_max)
        if volume_buy >= cfg.volume_minimo and volume_buy > volume_sell:
            return self._emitir(trade, Side.SELL, volume_buy, volume_sell,
                                deslocamento, preco_min, preco_max)
        return None

    def _expirar(self, agora_ns: int) -> None:
        limite = agora_ns - self.config.janela_ns
        janela = self._janela
        while janela and janela[0].timestamp_ns < limite:
            antigo = janela.popleft()
            if antigo.lado is AgressorSide.BUY:
                self._volume_buy -= antigo.qty
            elif antigo.lado is AgressorSide.SELL:
                self._volume_sell -= antigo.qty
            # O extremo só sai da monotonic deque se for justamente este trade.
            if self._max_precos and self._max_precos[0][0] == antigo.seq:
                self._max_precos.popleft()
            if self._min_precos and self._min_precos[0][0] == antigo.seq:
                self._min_precos.popleft()

    def _emitir(
        self,
        trade: Trade,
        side: Side,
        volume_dominante: int,
        volume_oposto: int,
        deslocamento: int,
        preco_min: int,
        preco_max: int,
    ) -> Deteccao | None:
        anterior = self._ja_sinalizado
        if anterior is not None:
            lado_anterior, preco_ancora = anterior
            # Gatilhos 2 e 3: âncora fora da faixa atual, ou o lado que absorve
            # virou — episódio novo, rearma.
            if lado_anterior is not side or not (preco_min <= preco_ancora <= preco_max):
                anterior = None
                self._ja_sinalizado = None
        if anterior is not None:
            return None  # mesmo episódio, já alertado

        self._ja_sinalizado = (side, trade.price)
        return Deteccao(
            timestamp_ns=trade.timestamp_ns,
            symbol=self.symbol,
            tipo=TipoDeteccao.ABSORCAO,
            side=side,
            price=trade.price,
            confianca=1.0,
            evidencia={
                "volume_agressao_dominante": volume_dominante,
                "volume_lado_oposto": volume_oposto,
                "deslocamento_ticks": deslocamento,
                "n_trades_janela": len(self._janela),
            },
        )


# ---------------------------------------------------------------------------
# Escora (reposição / defesa de preço)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigEscora:
    n_reposicoes_minimo: int = 3


class DetectorEscora:
    """Nível cuja quantidade é reposta repetidamente após ser consumida."""

    def __init__(self, config: ConfigEscora | None = None) -> None:
        self.config = config if config is not None else ConfigEscora()
        self._ja_sinalizado: set[tuple[Side, int]] = set()

    def verificar(
        self, livro: LivroMBO, side: Side, price: int, timestamp_ns: int
    ) -> Deteccao | None:
        n_reposicoes = livro.n_reposicoes(side, price)
        chave = (side, price)
        if n_reposicoes < self.config.n_reposicoes_minimo:
            self._ja_sinalizado.discard(chave)
            return None
        if chave in self._ja_sinalizado:
            return None  # já emitido para este nível — evita repetir a cada tick
        self._ja_sinalizado.add(chave)
        return Deteccao(
            timestamp_ns=timestamp_ns,
            symbol=livro.symbol,
            tipo=TipoDeteccao.ESCORA,
            side=side,
            price=price,
            confianca=1.0,
            evidencia={
                "n_reposicoes": n_reposicoes,
                "qty_total_atual": livro.qty_total(side, price),
            },
        )


# ---------------------------------------------------------------------------
# Iceberg
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigIceberg:
    razao_minima: float = 3.0
    volume_executado_minimo: int = 200


# DELETADO: `DetectorIceberg` (proxy por nível de preço).
#
# Ele calculava `executado_estimado = n_reposicoes * qty_exibida_max` e depois
# `razao = executado_estimado / qty_exibida_max`. O `qty_exibida_max` CANCELA:
# a razão era identicamente `n_reposicoes`. Consequências, todas verificadas
# em execução pela crítica R1 (seção 5.1):
#
# 1. A grandeza anunciada pela docstring — "executa muito mais volume do que a
#    quantidade exibida" — era a única que a fórmula garantidamente ignorava:
#    um nível exibindo 10 lotes e outro exibindo 5.000 recebiam a mesma razão.
# 2. `razao_minima=3.0` virava, na prática, `n_reposicoes >= 3` — literalmente
#    o gatilho de `DetectorEscora` (`n_reposicoes_minimo=3`). A mesma sequência
#    emitia ICEBERG e ESCORA, e o operador lia isso como confluência.
# 3. `evidencia["volume_executado_estimado"]` publicava um número fabricado com
#    nome de medição: `n_reposicoes` conta ORDENS NOVAS que chegaram depois de
#    o nível ser varrido, não contratos executados. Num dicionário chamado
#    `evidencia`, cuja finalidade declarada é permitir auditoria, isso enganava
#    o auditor. Confiança 0.6 não conserta um número que mede outra coisa.
#
# A opção "consertar em vez de deletar" exigiria o volume REALMENTE executado
# por nível. Esse número existe (`_NivelInterno.consumido_acumulado`), mas é
# privado: `LivroMBO` expõe `qty_total`, `n_reposicoes` e `qty_exibida_max` e
# nada mais.
#
# PENDENTE(livro): para reconstruir um iceberg por NÍVEL (o único caminho em
# feed agregado, onde não há `order_id` e portanto não há `n_recargas`),
# `LivroMBO` precisa expor `consumido_acumulado(side, price) -> int`. Com ele a
# razão honesta é `consumido_acumulado / qty_exibida_max`, e aí sim o tamanho
# exibido entra na conta. Enquanto não existir, este arquivo NÃO tem como medir
# o fenômeno por nível — e um detector que não mede o que diz medir é pior que
# detector nenhum, porque consome a atenção do operador com falsa confluência.
#
# Fica de pé apenas `DetectorIcebergPorRecarga`, que é honesto: mede
# `Ordem.qty_executada` contra `Ordem.qty_original` e EXIGE `n_recargas > 0`
# observada. Ele só funciona em feed MBO real — o que é a verdade, não uma
# limitação a ser disfarçada por proxy.


class DetectorIcebergPorRecarga:
    """Versão observada (feed MBO real): usa `Ordem.n_recargas`, não proxy.

    É o único detector de iceberg do módulo. A recarga observada — mesma
    `order_id` sendo reabastecida — é a assinatura do fenômeno; sem ela, uma
    execução grande é só uma ordem grande. Por isso `n_recargas == 0` barra a
    emissão mesmo quando a razão executado/exibido é alta: essa combinação é
    alcançável (ex.: `LivroMBO.modificar` para cima recria a `Ordem` com
    `qty_original` novo e `qty_executada` herdado) e NÃO é iceberg.
    """

    def __init__(self, config: ConfigIceberg | None = None) -> None:
        self.config = config if config is not None else ConfigIceberg()
        self._ja_sinalizado: set[str] = set()

    def verificar(self, ordem: Ordem, symbol: str, timestamp_ns: int) -> Deteccao | None:
        if ordem.order_id in self._ja_sinalizado:
            return None
        volume_executado = ordem.qty_executada
        if volume_executado < self.config.volume_executado_minimo:
            return None
        base = ordem.qty_original if ordem.qty_original > 0 else 1
        razao = volume_executado / base
        if ordem.n_recargas == 0 or razao < self.config.razao_minima:
            return None
        self._ja_sinalizado.add(ordem.order_id)
        return Deteccao(
            timestamp_ns=timestamp_ns,
            symbol=symbol,
            tipo=TipoDeteccao.ICEBERG,
            side=ordem.side,
            price=ordem.price,
            confianca=1.0,
            evidencia={
                "order_id": ordem.order_id,
                "qty_original": ordem.qty_original,
                "qty_executada": volume_executado,
                "n_recargas": ordem.n_recargas,
                "razao": razao,
            },
        )


# ---------------------------------------------------------------------------
# Liquidez fantasma (retirada antes da execução, sem julgar intenção)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigLiquidezFantasma:
    qty_minima: int = 200
    vida_maxima_ns: int = 1_000_000_000
    ticks_proximidade: int = 2


class DetectorLiquidezFantasma:
    """Quantidade grande que aparece e some sem executar, perto do preço.

    Termo deliberadamente neutro — o código só observa retirada rápida sem
    execução; não afirma intenção nem usa a palavra "spoof".
    """

    def __init__(self, grid_tick_size: float, config: ConfigLiquidezFantasma | None = None) -> None:
        self.config = config if config is not None else ConfigLiquidezFantasma()
        self._tick_size = grid_tick_size

    def verificar(
        self, ordem: Ordem, symbol: str, melhor_preco_oposto: int | None
    ) -> Deteccao | None:
        cfg = self.config
        if ordem.ativa or ordem.qty_executada > 0:
            return None  # se executou nada, não é o fenômeno buscado
        if ordem.qty_original < cfg.qty_minima:
            return None
        if ordem.timestamp_saida_ns is None:
            return None
        vida_ns = ordem.timestamp_saida_ns - ordem.timestamp_entrada_ns
        if vida_ns > cfg.vida_maxima_ns:
            return None
        if melhor_preco_oposto is not None:
            distancia_ticks = abs(ordem.price - melhor_preco_oposto)
            if distancia_ticks > cfg.ticks_proximidade:
                return None
        return Deteccao(
            timestamp_ns=ordem.timestamp_saida_ns,
            symbol=symbol,
            tipo=TipoDeteccao.LIQUIDEZ_FANTASMA,
            side=ordem.side,
            price=ordem.price,
            confianca=1.0,
            evidencia={
                "order_id": ordem.order_id,
                "qty_original": ordem.qty_original,
                "vida_ns": vida_ns,
            },
        )


# ---------------------------------------------------------------------------
# Exaustão
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigExaustao:
    n_trades_janela: int = 5
    queda_volume_minima: float = 0.4  # último terço vs primeiro terço da janela


class DetectorExaustao:
    """Agressão de um lado com volume decrescente e sem progresso de preço."""

    def __init__(self, symbol: str, config: ConfigExaustao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigExaustao()
        self._trades: list[Trade] = []

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        self._trades.append(trade)
        if len(self._trades) < cfg.n_trades_janela:
            return None
        janela = self._trades[-cfg.n_trades_janela:]
        lado = janela[0].side_agressor
        if any(t.side_agressor != lado for t in janela) or lado.name == "UNKNOWN":
            return None

        terco = max(1, cfg.n_trades_janela // 3)
        vol_inicio = sum(t.qty for t in janela[:terco])
        vol_fim = sum(t.qty for t in janela[-terco:])
        if vol_inicio == 0:
            return None
        queda = 1.0 - (vol_fim / vol_inicio)
        preco_inicio = janela[0].price
        preco_fim = janela[-1].price
        progrediu = preco_fim != preco_inicio

        if queda >= cfg.queda_volume_minima and not progrediu:
            side = Side.BUY if lado.name == "BUY" else Side.SELL
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.EXAUSTAO,
                side=side,
                price=preco_fim,
                confianca=1.0,
                evidencia={
                    "volume_inicio_janela": vol_inicio,
                    "volume_fim_janela": vol_fim,
                    "queda_relativa": queda,
                    "preco_moveu": progrediu,
                },
            )
        return None


# ---------------------------------------------------------------------------
# Clip institucional / algoritmo (TWAP/POV)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigClipInstitucional:
    n_trades_minimo: int = 5
    cv_qty_maximo: float = 0.15  # coeficiente de variação (desvio/média)
    cv_intervalo_maximo: float = 0.30


class DetectorClipInstitucional:
    """Sequência de trades de tamanho e intervalo regulares (assinatura TWAP/POV)."""

    def __init__(self, symbol: str, config: ConfigClipInstitucional | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigClipInstitucional()
        self._trades: list[Trade] = []
        self._ja_sinalizado_janela: bool = False

    @staticmethod
    def _cv(valores: list[float]) -> float:
        n = len(valores)
        media = sum(valores) / n
        if media == 0:
            return float("inf")
        variancia = sum((v - media) ** 2 for v in valores) / n
        return (variancia ** 0.5) / media

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        self._trades.append(trade)
        if len(self._trades) > cfg.n_trades_minimo:
            self._trades.pop(0)
            self._ja_sinalizado_janela = False
        if len(self._trades) < cfg.n_trades_minimo:
            return None
        if self._ja_sinalizado_janela:
            return None

        qtys = [float(t.qty) for t in self._trades]
        intervalos = [
            float(self._trades[i].timestamp_ns - self._trades[i - 1].timestamp_ns)
            for i in range(1, len(self._trades))
        ]
        cv_qty = self._cv(qtys)
        cv_intervalo = self._cv(intervalos) if intervalos else float("inf")

        if cv_qty <= cfg.cv_qty_maximo and cv_intervalo <= cfg.cv_intervalo_maximo:
            self._ja_sinalizado_janela = True
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.CLIP_INSTITUCIONAL,
                side=Side.BUY if trade.side_agressor.name == "BUY" else Side.SELL,
                price=trade.price,
                confianca=1.0,
                evidencia={
                    "cv_quantidade": cv_qty,
                    "cv_intervalo": cv_intervalo,
                    "n_trades": len(self._trades),
                    "qty_media": sum(qtys) / len(qtys),
                },
            )
        return None
