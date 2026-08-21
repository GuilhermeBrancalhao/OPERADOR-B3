"""Footprint ("Gráfico de Força") — bid×ask por nível de preço dentro do candle.

Conceito de leitura de fluxo: o candle normal só mostra OHLC. O footprint
abre cada candle em um histograma por nível de preço, com duas colunas —
quanto foi negociado por agressão **compradora** e quanto por agressão
**vendedora** naquele preço específico, dentro daquele candle. Isso revela
*onde dentro do candle* a força comprou ou vendeu, não só o resultado final.

Três leituras derivadas, todas parametrizáveis via `ConfigFootprint` (sem
limiar cravado no código):

- **Imbalance**: comparação *diagonal* entre níveis adjacentes — o volume
  comprador no preço P contra o volume vendedor no preço P+1 tick (e
  vice-versa para venda). É diagonal porque, num book em movimento, uma
  agressão de compra em P só "vence" a oferta que estava um tick acima; a
  comparação correta de força é contra o nível vizinho, não o mesmo nível.
  Um nível "vence" o vizinho quando a razão ultrapassa `limiar_imbalance`
  (padrão de mercado: 3x, ou seja 300%).
- **Delta divergente**: o candle fecha em alta mas o delta do candle é
  negativo (ou fecha em baixa com delta positivo) — sinal de que o preço
  subiu "aspirado" por oferta fraca, não por agressão real.
- **Absorção no extremo**: volume muito acima da média do candle concentrado
  exatamente na máxima ou mínima, com o preço revertendo a partir dali —
  sinal de que uma ordem grande "absorveu" a agressão sem deixar o preço
  continuar, tipicamente o início de uma reversão.

Todo o histograma é mantido incremental (`registrar_trade` é O(1)); as
detecções (imbalance/divergência/absorção) são calculadas sob demanda a
partir do estado acumulado do candle — O(níveis do candle), não O(histórico).

Trade com `AgressorSide.UNKNOWN` (leilão de abertura/fechamento, RLP) conta
em `volume_total` mas não em `delta` nem nos baldes comprador/vendedor de
`NivelFootprint` — isso é correto (não dá pra saber de que lado somar no
delta). O que não é opcional é o volume aparecer em algum lugar: veja
`NivelFootprint.qty_nao_atribuida` e `Footprint.volume_nao_atribuido`.
Footprint é por candle (não por sessão) — cada `FootprintPorTimeframe` já
fecha e abre um novo a cada bucket de `timeframe_ns`, então não há
acumulador de sessão aqui para resetar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade

NS_POR_MINUTO = 60_000_000_000


@dataclass(frozen=True, slots=True)
class ConfigFootprint:
    limiar_imbalance: float = 3.0
    """Razão diagonal mínima (comprador(P) / vendedor(P+1) ou o espelho) para
    marcar imbalance. Padrão de mercado: 3.0 (300%)."""

    qty_minima_imbalance: int = 5
    """Ignora o lado "forte" de níveis com qty abaixo deste piso — evita
    imbalance espúrio tipo 1 contra 0 (razão infinita) em ruído de poucos
    lotes. Default de fábrica vinha `0` (proteção desarmada) até a R4 medir
    42-72% dos níveis de um candle esparso marcados como imbalance por causa
    disso (`criticas/nucleo_r3.md` C.7, `criticas/nucleo_r4.md` achado 10) —
    uma razão 3:1 sobre 1 contrato contra 0 não é sinal, é ruído de tape fino.
    `5` é o piso: abaixo disso a razão diagonal não dispara nada, mesmo que
    ultrapasse `limiar_imbalance`. Ajuste para o contrato/liquidez do symbol
    (WDO negocia rotineiramente em clipes de 1-10 lotes; `5` filtra o ruído
    de ponta sem apagar imbalance real de tamanho médio)."""

    multiplo_absorcao: float = 2.0
    """Volume no nível do extremo (topo/fundo) precisa ser >= este múltiplo da
    média de volume por nível do candle para contar como candidato a absorção."""

    reversao_ticks_absorcao: int = 1
    """Quantos ticks o fechamento precisa recuar a partir do extremo (máxima ou
    mínima) para a absorção ser confirmada por reversão."""


@dataclass(slots=True)
class NivelFootprint:
    """Histograma bid×ask de um único nível de preço dentro de um candle.

    `qty_nao_atribuida` guarda trades com `AgressorSide.UNKNOWN` (leilão de
    abertura/fechamento, RLP). Antes esse volume entrava no
    `Footprint._volume_total` do candle mas em nível nenhum — o nível podia
    existir (criado por `setdefault`) com `volume_total == 0` enquanto o
    footprint inteiro contava o trade. Agora `volume_total` do nível inclui
    o balde não atribuído, então a soma dos níveis bate com o total do
    footprint."""

    qty_comprador: int = 0
    qty_vendedor: int = 0
    qty_nao_atribuida: int = 0

    @property
    def volume_total(self) -> int:
        return self.qty_comprador + self.qty_vendedor + self.qty_nao_atribuida

    @property
    def delta(self) -> int:
        return self.qty_comprador - self.qty_vendedor


class Footprint:
    """Footprint de um único candle, atualizado trade a trade."""

    def __init__(self, config: ConfigFootprint | None = None) -> None:
        self.config = config or ConfigFootprint()
        self._niveis: dict[int, NivelFootprint] = {}
        self._volume_total = 0
        self._volume_nao_atribuido = 0
        self._delta = 0
        self.preco_abertura: int | None = None
        self.preco_fechamento: int | None = None
        self.preco_maximo: int | None = None
        self.preco_minimo: int | None = None

    def registrar_trade(self, trade: Trade) -> None:
        nivel = self._niveis.setdefault(trade.price, NivelFootprint())
        if trade.side_agressor is AgressorSide.BUY:
            nivel.qty_comprador += trade.qty
            self._delta += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            nivel.qty_vendedor += trade.qty
            self._delta -= trade.qty
        else:
            nivel.qty_nao_atribuida += trade.qty
            self._volume_nao_atribuido += trade.qty
        self._volume_total += trade.qty

        if self.preco_abertura is None:
            self.preco_abertura = trade.price
        self.preco_fechamento = trade.price
        self.preco_maximo = (
            trade.price if self.preco_maximo is None else max(self.preco_maximo, trade.price)
        )
        self.preco_minimo = (
            trade.price if self.preco_minimo is None else min(self.preco_minimo, trade.price)
        )

    @property
    def volume_total(self) -> int:
        return self._volume_total

    @property
    def volume_nao_atribuido(self) -> int:
        """Qty do candle com `side_agressor is AgressorSide.UNKNOWN`.

        `volume_total == qty_comprador_total + qty_vendedor_total +
        volume_nao_atribuido` (some os níveis para conferir) — mesmo
        invariante de `NivelFootprint.volume_total`."""
        return self._volume_nao_atribuido

    @property
    def delta(self) -> int:
        return self._delta

    def nivel(self, price: int) -> NivelFootprint | None:
        return self._niveis.get(price)

    def niveis_ordenados(self) -> list[tuple[int, NivelFootprint]]:
        return sorted(self._niveis.items(), key=lambda kv: kv[0])

    def niveis_imbalance_compra(self) -> list[int]:
        """Preços onde qty_comprador(P) domina qty_vendedor(P+1 tick)."""
        limiar = self.config.limiar_imbalance
        piso = self.config.qty_minima_imbalance
        resultado = []
        for preco, nivel in self._niveis.items():
            if nivel.qty_comprador < piso or nivel.qty_comprador == 0:
                continue
            vizinho = self._niveis.get(preco + 1)
            qty_vendedor_vizinho = vizinho.qty_vendedor if vizinho else 0
            if qty_vendedor_vizinho == 0:
                resultado.append(preco)
            elif nivel.qty_comprador / qty_vendedor_vizinho >= limiar:
                resultado.append(preco)
        return sorted(resultado)

    def niveis_imbalance_venda(self) -> list[int]:
        """Preços onde qty_vendedor(P) domina qty_comprador(P-1 tick)."""
        limiar = self.config.limiar_imbalance
        piso = self.config.qty_minima_imbalance
        resultado = []
        for preco, nivel in self._niveis.items():
            if nivel.qty_vendedor < piso or nivel.qty_vendedor == 0:
                continue
            vizinho = self._niveis.get(preco - 1)
            qty_comprador_vizinho = vizinho.qty_comprador if vizinho else 0
            if qty_comprador_vizinho == 0:
                resultado.append(preco)
            elif nivel.qty_vendedor / qty_comprador_vizinho >= limiar:
                resultado.append(preco)
        return sorted(resultado)

    def delta_divergente(self) -> bool:
        """True se o preço subiu com delta negativo, ou caiu com delta positivo."""
        if self.preco_abertura is None or self.preco_fechamento is None:
            return False
        if self.preco_fechamento > self.preco_abertura and self._delta < 0:
            return True
        if self.preco_fechamento < self.preco_abertura and self._delta > 0:
            return True
        return False

    def _media_volume_por_nivel(self) -> float:
        if not self._niveis:
            return 0.0
        return self._volume_total / len(self._niveis)

    def absorcao_topo(self) -> bool:
        """Volume alto na máxima do candle com fechamento recuando dali."""
        if self.preco_maximo is None or self.preco_fechamento is None:
            return False
        nivel_topo = self._niveis.get(self.preco_maximo)
        if nivel_topo is None:
            return False
        media = self._media_volume_por_nivel()
        volume_alto = nivel_topo.volume_total >= self.config.multiplo_absorcao * media
        reversao = (
            self.preco_maximo - self.preco_fechamento
        ) >= self.config.reversao_ticks_absorcao
        return volume_alto and reversao

    def absorcao_fundo(self) -> bool:
        """Volume alto na mínima do candle com fechamento recuando dali."""
        if self.preco_minimo is None or self.preco_fechamento is None:
            return False
        nivel_fundo = self._niveis.get(self.preco_minimo)
        if nivel_fundo is None:
            return False
        media = self._media_volume_por_nivel()
        volume_alto = nivel_fundo.volume_total >= self.config.multiplo_absorcao * media
        reversao = (
            self.preco_fechamento - self.preco_minimo
        ) >= self.config.reversao_ticks_absorcao
        return volume_alto and reversao


@dataclass(slots=True)
class _FootprintFechado:
    timestamp_inicio_ns: int
    footprint: Footprint


class FootprintPorTimeframe:
    """Assina o `Barramento` e mantém um `Footprint` por candle (bucket de
    `timeframe_ns`), no mesmo padrão de bucketing de `estado_mercado.py`.
    """

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        timeframe_ns: int = NS_POR_MINUTO,
        config: ConfigFootprint | None = None,
    ) -> None:
        self._symbol = symbol
        self._timeframe_ns = timeframe_ns
        self._config = config or ConfigFootprint()
        self._atual: Footprint | None = None
        self._inicio_atual_ns: int | None = None
        self._fechados: list[_FootprintFechado] = []

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return
        bucket = (trade.timestamp_ns // self._timeframe_ns) * self._timeframe_ns
        if self._inicio_atual_ns is None or bucket != self._inicio_atual_ns:
            if self._atual is not None:
                self._fechados.append(
                    _FootprintFechado(self._inicio_atual_ns, self._atual)  # type: ignore[arg-type]
                )
            self._atual = Footprint(config=self._config)
            self._inicio_atual_ns = bucket
        self._atual.registrar_trade(trade)

    @property
    def footprint_atual(self) -> Footprint | None:
        return self._atual

    @property
    def footprints_fechados(self) -> tuple[_FootprintFechado, ...]:
        return tuple(self._fechados)
