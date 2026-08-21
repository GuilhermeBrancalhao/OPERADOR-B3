"""Volume Profile — volume negociado por nível de preço.

Conceito de leitura de fluxo: enquanto o candle mostra OHLC ao longo do
*tempo*, o Volume Profile gira o eixo e mostra quanto volume foi negociado em
cada *preço*, dentro de um período. Três leituras derivam dele:

- **POC** (Point of Control): o nível de preço com maior volume — o "consenso"
  de valor do período, tende a atrair preço de volta (magnetismo).
- **Value Area** (VAH/VAL): a faixa de preços que concentra a fatia
  configurável do volume total (70% é o padrão de mercado) ao redor do POC —
  fora dela o mercado historicamente "rejeitou" preço com mais força.
- **HVN/LVN** (High/Low Volume Nodes): níveis com volume muito acima ou muito
  abaixo da média do perfil — HVN tende a segurar preço (suporte/resistência
  por consenso), LVN tende a ser atravessado rápido (vácuo de liquidez).

Cada nível também separa volume por lado do agressor (comprador vs.
vendedor), então dá para ver não só *quanto* mas *quem* negociou ali.

Três formas de uso, todas construídas sobre o mesmo `registrar_trade`
incremental (O(1) por trade, sem realocar histórico):

1. `VolumeProfile` isolado — objeto que você alimenta manualmente ou via
   `VolumeProfile.de_trades(...)` para um range de trades já filtrado
   (uso em lote / range de tempo arbitrário).
2. `VolumeProfilePorPeriodo` — assina o `Barramento` e mantém um perfil por
   bucket de tempo fixo (`period_ns`), fechando o bucket anterior e abrindo
   um novo a cada trade que cruza a fronteira (mesmo padrão de
   `_CandleEmFormacao` em `estado_mercado.py`). Com `period_ns` igual à
   duração do pregão, o "período" vira o perfil de sessão.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


@dataclass(frozen=True, slots=True)
class ConfigVolumeProfile:
    """Parâmetros do perfil. Nenhum limiar é implícito no código."""

    value_area_pct: float = 0.70
    """Fatia do volume total que define a Value Area (padrão de mercado: 70%)."""

    hvn_multiplo_media: float = 1.5
    """Nível é HVN quando volume_total(nível) >= este múltiplo * média por nível."""

    lvn_multiplo_media: float = 0.5
    """Nível é LVN quando volume_total(nível) <= este múltiplo * média por nível."""


@dataclass(slots=True)
class NivelVolume:
    """Volume acumulado em um único nível de preço, separado por agressor."""

    volume_comprador: int = 0
    volume_vendedor: int = 0

    @property
    def volume_total(self) -> int:
        return self.volume_comprador + self.volume_vendedor

    @property
    def delta(self) -> int:
        return self.volume_comprador - self.volume_vendedor


@dataclass(slots=True)
class VolumeProfile:
    """Perfil de volume por preço, atualizado trade a trade.

    `registrar_trade` é o caminho quente: um dict lookup + soma, O(1) e sem
    alocação além do `NivelVolume` criado na primeira visita a um preço.
    """

    config: ConfigVolumeProfile = field(default_factory=ConfigVolumeProfile)
    _niveis: dict[int, NivelVolume] = field(default_factory=dict, repr=False)
    _volume_total: int = field(default=0, repr=False)

    @classmethod
    def de_trades(
        cls, trades: Iterable[Trade], config: ConfigVolumeProfile | None = None
    ) -> "VolumeProfile":
        """Constrói um perfil de um range de trades arbitrário (uso em lote).

        Internamente chama `registrar_trade` trade a trade — é o mesmo
        algoritmo incremental usado ao vivo, só que aplicado de uma vez a um
        conjunto já recortado (ex.: trades entre dois timestamps quaisquer).
        """
        perfil = cls(config=config or ConfigVolumeProfile())
        for trade in trades:
            perfil.registrar_trade(trade)
        return perfil

    def registrar_trade(self, trade: Trade) -> None:
        nivel = self._niveis.setdefault(trade.price, NivelVolume())
        if trade.side_agressor is AgressorSide.BUY:
            nivel.volume_comprador += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            nivel.volume_vendedor += trade.qty
        self._volume_total += trade.qty

    @property
    def volume_total(self) -> int:
        return self._volume_total

    def nivel(self, price: int) -> NivelVolume | None:
        return self._niveis.get(price)

    def niveis_ordenados(self) -> list[tuple[int, NivelVolume]]:
        return sorted(self._niveis.items(), key=lambda kv: kv[0])

    @property
    def poc(self) -> int | None:
        """Point of Control: preço de maior volume total.

        Empate desfeito pelo preço mais baixo (determinístico e documentado
        — não há convenção universal de desempate para POC).
        """
        if not self._niveis:
            return None
        return min(
            self._niveis.keys(),
            key=lambda preco: (-self._niveis[preco].volume_total, preco),
        )

    def value_area(self, pct: float | None = None) -> tuple[int, int] | None:
        """Faixa (VAL, VAH) que concentra `pct` (padrão: config) do volume.

        Algoritmo — expansão gulosa a partir do POC: a cada passo, compara o
        próximo nível acima do topo atual da faixa com o próximo nível abaixo
        da base atual, e adiciona o lado de maior volume (empate: adiciona os
        dois). Repete até a soma acumulada atingir `pct * volume_total` ou
        esgotar os níveis.
        """
        if not self._niveis:
            return None
        alvo_pct = pct if pct is not None else self.config.value_area_pct
        alvo_volume = alvo_pct * self._volume_total

        precos_ordenados = sorted(self._niveis.keys())
        poc = self.poc
        assert poc is not None
        idx_poc = precos_ordenados.index(poc)

        idx_baixo = idx_alto = idx_poc
        acumulado = self._niveis[poc].volume_total

        while acumulado < alvo_volume:
            proximo_alto = idx_alto + 1
            proximo_baixo = idx_baixo - 1
            tem_alto = proximo_alto < len(precos_ordenados)
            tem_baixo = proximo_baixo >= 0

            if not tem_alto and not tem_baixo:
                break

            vol_alto = (
                self._niveis[precos_ordenados[proximo_alto]].volume_total
                if tem_alto
                else -1
            )
            vol_baixo = (
                self._niveis[precos_ordenados[proximo_baixo]].volume_total
                if tem_baixo
                else -1
            )

            if tem_alto and (not tem_baixo or vol_alto > vol_baixo):
                idx_alto = proximo_alto
                acumulado += vol_alto
            elif tem_baixo and (not tem_alto or vol_baixo > vol_alto):
                idx_baixo = proximo_baixo
                acumulado += vol_baixo
            else:
                # empate: soma os dois lados nesta rodada
                idx_alto = proximo_alto
                idx_baixo = proximo_baixo
                acumulado += vol_alto + vol_baixo

        return (precos_ordenados[idx_baixo], precos_ordenados[idx_alto])

    def val(self, pct: float | None = None) -> int | None:
        area = self.value_area(pct)
        return area[0] if area else None

    def vah(self, pct: float | None = None) -> int | None:
        area = self.value_area(pct)
        return area[1] if area else None

    def _media_volume_por_nivel(self) -> float:
        if not self._niveis:
            return 0.0
        return self._volume_total / len(self._niveis)

    def hvn(self) -> list[int]:
        """High Volume Nodes: níveis com volume >= `hvn_multiplo_media` * média."""
        media = self._media_volume_por_nivel()
        limiar = self.config.hvn_multiplo_media * media
        return sorted(
            preco
            for preco, nivel in self._niveis.items()
            if nivel.volume_total >= limiar
        )

    def lvn(self) -> list[int]:
        """Low Volume Nodes: níveis com volume <= `lvn_multiplo_media` * média."""
        media = self._media_volume_por_nivel()
        limiar = self.config.lvn_multiplo_media * media
        return sorted(
            preco
            for preco, nivel in self._niveis.items()
            if nivel.volume_total <= limiar
        )


class VolumeProfilePorPeriodo:
    """Assina o `Barramento` e mantém um `VolumeProfile` por bucket de tempo.

    `period_ns` define o tamanho do bucket: um dia inteiro de pregão vira
    "perfil de sessão"; um valor menor (ex.: 1 hora) vira "perfil por
    período". O bucket corrente fica em `periodo_atual`; ao cruzar a
    fronteira ele é congelado e movido para `periodos_fechados`.
    """

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        period_ns: int,
        config: ConfigVolumeProfile | None = None,
    ) -> None:
        self._symbol = symbol
        self._period_ns = period_ns
        self._config = config or ConfigVolumeProfile()
        self._periodo_atual: VolumeProfile | None = None
        self._inicio_periodo_ns: int | None = None
        self._periodos_fechados: list[tuple[int, VolumeProfile]] = []

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return
        bucket = (trade.timestamp_ns // self._period_ns) * self._period_ns
        if self._inicio_periodo_ns is None or bucket != self._inicio_periodo_ns:
            if self._periodo_atual is not None:
                self._periodos_fechados.append(
                    (self._inicio_periodo_ns, self._periodo_atual)  # type: ignore[arg-type]
                )
            self._periodo_atual = VolumeProfile(config=self._config)
            self._inicio_periodo_ns = bucket
        self._periodo_atual.registrar_trade(trade)

    @property
    def periodo_atual(self) -> VolumeProfile | None:
        return self._periodo_atual

    @property
    def periodos_fechados(self) -> tuple[tuple[int, VolumeProfile], ...]:
        return tuple(self._periodos_fechados)

    def nova_sessao(self) -> None:
        """Zera o bucket corrente sem esperar cruzar a fronteira de tempo.

        Útil para forçar início de sessão manualmente (ex.: abertura do
        pregão) em vez de depender só do bucketing por `period_ns`.
        """
        self._periodo_atual = None
        self._inicio_periodo_ns = None
