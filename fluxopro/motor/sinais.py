"""Motor de sinais: codifica a confluência de 3 condições extraída da metodologia
ASG/Gargantini (ver `PROGRESSO.md`, seção "A METODOLOGIA", com citação direta
das transcrições dos vídeos).

As 3 condições, na ordem em que a metodologia exige:

1. **Direção do dia** — dominância percentual comprador×vendedor cruza um
   limiar (a fonte usa ~70%; aqui é parametrizável). Sem isso, "não tem
   direcional, não tem ainda o alinhamento seguro".
2. **Retorno a uma região de interesse** — o preço faz pullback e volta a
   uma FAIXA (não um preço exato). Aqui a região é aproximada por
   VAH/VAL do Volume Profile ou por uma faixa explícita fornecida por fora
   (ex.: nível de S/R) — a metodologia não expõe a fórmula exata da
   ferramenta original, então isto é uma reconstrução funcional, marcada
   como tal.
3. **Virada da "micro"** — o fluxo de curtíssimo prazo precisa reverter na
   direção pretendida. Aqui isso é operacionalizado pelo `CumulativeDelta`
   de uma janela curta mudando de sinal, combinado com a saída do
   `MedidorAgressao`.

Este motor NÃO reproduz a "ferramenta" original pixel a pixel (não temos
acesso ao código dela) — ele implementa a MESMA LÓGICA DE CONFLUÊNCIA sobre
dado próprio, com parâmetros abertos para o usuário calibrar. Isso é
declarado explicitamente para não confundir "sinal equivalente" com "cópia".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade


@unique
class EstagioSinal(Enum):
    """Onde a confluência está, para refletir o "pré-sinal" (farol amarelo)."""

    NENHUM = "NENHUM"
    DIRECAO_CONFIRMADA = "DIRECAO_CONFIRMADA"      # condição 1 sozinha
    NA_REGIAO = "NA_REGIAO"                        # 1 + 2
    PRE_SINAL = "PRE_SINAL"                        # 1 + 2, micro começando a virar
    CONFIRMADO = "CONFIRMADO"                      # 1 + 2 + 3 — entrada


@dataclass(frozen=True, slots=True)
class ConfigMotorSinais:
    """Nenhum limiar cravado no corpo — tudo calibrável pelo usuário.

    `dominancia_minima` — fração (0-1) da dominância comprador/vendedor para
    considerar "direção do dia" confirmada (a fonte cita ~0.70).
    `janela_dominancia_ns` — janela de trades usada para medir a dominância.
    `margem_regiao_ticks` — tolerância em ticks para considerar o preço
    "dentro" da região de interesse (VAH/VAL ou faixa explícita).
    `janela_micro_ns` — janela curta do delta/agressão que representa a
    "micro" (fluxo de curtíssimo prazo).
    `pre_sinal_fracao_janela_micro` — fração da janela_micro_ns em que uma
    reversão parcial do delta já conta como pré-sinal (farol amarelo).
    """

    dominancia_minima: float = 0.70
    janela_dominancia_ns: int = 5 * 60_000_000_000  # 5 min
    margem_regiao_ticks: int = 2
    janela_micro_ns: int = 15_000_000_000  # 15s
    pre_sinal_fracao_janela_micro: float = 0.5


@dataclass(frozen=True, slots=True)
class Sinal:
    timestamp_ns: int
    symbol: str
    estagio: EstagioSinal
    direcao: Side | None
    evidencia: dict[str, object] = field(default_factory=dict)


class MotorSinais:
    """Consome trades e mantém o estágio de confluência por símbolo.

    Não é dono do `VolumeProfile` — ele é injetado para que o chamador
    escolha janela/timeframe e para não duplicar estado que o módulo de
    analytics já mantém (o motor só lê `val()`/`vah()`; quem alimenta
    `registrar_trade()` no perfil é o chamador). A "micro" (condição 3) é
    computada internamente a partir dos próprios trades recebidos — não
    depende de `CumulativeDelta`/`MedidorAgressao` porque a janela e a
    regra de reversão aqui são específicas da confluência ASG, diferentes
    do delta de sessão genérico que esses módulos calculam.
    """

    def __init__(
        self,
        symbol: str,
        volume_profile: VolumeProfile,
        config: ConfigMotorSinais | None = None,
    ) -> None:
        self._symbol = symbol
        self._vp = volume_profile
        self.config = config if config is not None else ConfigMotorSinais()

        self._trades_dominancia: list[Trade] = []
        self._trades_micro: list[Trade] = []
        self._direcao_atual: Side | None = None
        self._estagio_atual: EstagioSinal = EstagioSinal.NENHUM

    # ------------------------------------------------------------------
    def _dominancia(self, timestamp_ns: int) -> tuple[float, Side | None]:
        limite = timestamp_ns - self.config.janela_dominancia_ns
        self._trades_dominancia = [t for t in self._trades_dominancia if t.timestamp_ns >= limite]
        vol_buy = sum(t.qty for t in self._trades_dominancia if t.side_agressor is AgressorSide.BUY)
        vol_sell = sum(t.qty for t in self._trades_dominancia if t.side_agressor is AgressorSide.SELL)
        total = vol_buy + vol_sell
        if total == 0:
            return 0.5, None
        if vol_buy >= vol_sell:
            return vol_buy / total, Side.BUY
        return vol_sell / total, Side.SELL

    def _na_regiao(self, price: int) -> bool:
        """Região de interesse aproximada por VAH/VAL do Volume Profile.

        Reconstrução funcional — a fonte não descreve a fórmula exata da
        ferramenta original (ver docstring do módulo).
        """
        val = self._vp.val()
        vah = self._vp.vah()
        if val is None or vah is None:
            return False
        margem = self.config.margem_regiao_ticks
        return (val - margem) <= price <= (vah + margem)

    def _micro_virou(self, direcao: Side, timestamp_ns: int) -> tuple[bool, bool]:
        """Retorna (virou_completo, pre_sinal). "Micro" = delta da janela curta."""
        limite = timestamp_ns - self.config.janela_micro_ns
        self._trades_micro = [t for t in self._trades_micro if t.timestamp_ns >= limite]
        if not self._trades_micro:
            return False, False

        delta_micro = sum(
            t.qty if t.side_agressor is AgressorSide.BUY
            else -t.qty if t.side_agressor is AgressorSide.SELL
            else 0
            for t in self._trades_micro
        )
        # direção BUY pretendida: precisamos que o fluxo de curto prazo vire
        # comprador (delta_micro > 0); direção SELL: vire vendedor (< 0).
        alvo_positivo = direcao is Side.BUY
        virou = (delta_micro > 0) if alvo_positivo else (delta_micro < 0)

        marco = self.config.pre_sinal_fracao_janela_micro
        primeira_metade = self._trades_micro[: max(1, int(len(self._trades_micro) * marco))]
        delta_inicio = sum(
            t.qty if t.side_agressor is AgressorSide.BUY
            else -t.qty if t.side_agressor is AgressorSide.SELL
            else 0
            for t in primeira_metade
        )
        estava_contra = (delta_inicio <= 0) if alvo_positivo else (delta_inicio >= 0)
        pre_sinal = estava_contra and not virou and delta_micro != 0

        return virou, pre_sinal

    # ------------------------------------------------------------------
    def ao_trade(self, trade: Trade) -> Sinal:
        if trade.symbol != self._symbol:
            return Sinal(trade.timestamp_ns, self._symbol, EstagioSinal.NENHUM, None)

        self._trades_dominancia.append(trade)
        self._trades_micro.append(trade)

        dominancia, direcao = self._dominancia(trade.timestamp_ns)
        evidencia: dict[str, object] = {"dominancia": dominancia}

        if direcao is None or dominancia < self.config.dominancia_minima:
            self._estagio_atual = EstagioSinal.NENHUM
            return Sinal(trade.timestamp_ns, self._symbol, EstagioSinal.NENHUM, None, evidencia)

        evidencia["direcao_dominante"] = direcao.value
        na_regiao = self._na_regiao(trade.price)
        evidencia["na_regiao"] = na_regiao

        if not na_regiao:
            self._estagio_atual = EstagioSinal.DIRECAO_CONFIRMADA
            return Sinal(trade.timestamp_ns, self._symbol, EstagioSinal.DIRECAO_CONFIRMADA, direcao, evidencia)

        virou, pre_sinal = self._micro_virou(direcao, trade.timestamp_ns)
        evidencia["micro_virou"] = virou
        evidencia["pre_sinal"] = pre_sinal

        if virou:
            estagio = EstagioSinal.CONFIRMADO
        elif pre_sinal:
            estagio = EstagioSinal.PRE_SINAL
        else:
            estagio = EstagioSinal.NA_REGIAO

        self._estagio_atual = estagio
        return Sinal(trade.timestamp_ns, self._symbol, estagio, direcao, evidencia)

    @property
    def estagio_atual(self) -> EstagioSinal:
        return self._estagio_atual
