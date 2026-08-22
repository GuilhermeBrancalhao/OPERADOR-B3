"""Regime estrutural — mudança de tendência só quando perde a máxima/mínima.

Regra (`regras.REGRAS["estrutura.regime"]`, CONFIRMADO,
`ferramenta_componentes.md` §8 e §6.2, vídeo `Cbj66x1JXoA`):

    "candle vendedor... acha que o mercado tá fritando"

é a rejeição explícita, pelo autor, de ler candle isolado como prova de
mudança de estrutura. A regra positiva, na paráfrase da pesquisa: o mercado só
vira vendedor de fato **quando perde a mínima do dia** (ou a região de
abertura); enquanto o preço fica acima da abertura e perto da máxima, venda é
"ruído / ondulação momentânea", por maior que seja a barrigada.

## Por que este é o componente mais barato e o mais valioso

Não precisa de book, de identidade de corretora nem de MBO: só de preço. E é
exatamente o que faltava no caso WINFUT (`ferramenta_componentes.md` §7) — um
contexto macro que inverteu de sinal por poucos minutos teria dado compra,
enquanto a estrutura do dia nunca autorizou nada disso.

## Estado, e o critério do gravador

Sete inteiros e dois enums por instância: abertura, máxima, mínima, último
preço, timestamp, regime e regime anterior. **Nenhuma coleção.** O `len` de
qualquer coisa aqui dentro não é indexado por evento, por preço visitado nem
por duração de sessão — não há nada a crescer. (Critério de
`fluxopro/gravacao/gravador.py`: "qual grandeza limita o `len` disto, e ela
para de crescer enquanto o pregão continua?")

## O que este componente NÃO faz

Não projeta alvo (`alvo.formula`, AUSENTE NA FONTE), não classifica região
como boa ou turbulenta (`risco.gatilho_de_tamanho`, AUSENTE NA FONTE) e não
emite cor — emite `Side` (ver a nota de divergência de cor em `regras.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Candle, Side
from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.regras import regras_de


@unique
class RegimeEstrutural(Enum):
    """Regime do dia. `INDEFINIDO` até o primeiro rompimento de extremo."""

    INDEFINIDO = "INDEFINIDO"
    COMPRADOR = "COMPRADOR"
    VENDEDOR = "VENDEDOR"

    @property
    def lado(self) -> Side | None:
        if self is RegimeEstrutural.COMPRADOR:
            return Side.BUY
        if self is RegimeEstrutural.VENDEDOR:
            return Side.SELL
        return None


@unique
class GatilhoEstrutural(Enum):
    """O que mudou o regime NESTE preço — vazio na esmagadora maioria deles."""

    NENHUM = "NENHUM"
    ROMPEU_MAXIMA = "ROMPEU_MAXIMA"
    PERDEU_MINIMA = "PERDEU_MINIMA"
    CRUZOU_ABERTURA = "CRUZOU_ABERTURA"


@dataclass(frozen=True, slots=True)
class ConfigEstrutura:
    """Ver `regras.parametros_de("ConfigEstrutura")` para o porquê de cada um."""

    margem_ticks: int = 0
    """Quanto ALÉM do extremo o preço precisa ir para "perder" a estrutura.
    A fonte não dá tolerância; 0 é a leitura literal."""

    margem_abertura_ticks: int = 0
    """Idem, para a "região de abertura". A fonte diz "região", não "preço" —
    quem quiser uma região de verdade sobe este número."""

    ruido_minimo_ticks: int = 0
    """Recuo mínimo, contra o regime, para a leitura marcar `ruido`. 0 = todo
    movimento contrário que não quebra estrutura é ruído, que é o que a fonte
    afirma. Os "~1000 pontos" da fonte são a amplitude do dia narrado."""

    usar_abertura: bool = True
    """Liga o segundo gatilho ("ou a região de abertura", §6.2)."""


@dataclass(frozen=True, slots=True)
class LeituraEstrutural:
    """Uma leitura publicada, com a procedência anexada em `regras`."""

    timestamp_ns: int
    preco: int
    regime: RegimeEstrutural
    regime_anterior: RegimeEstrutural
    gatilho: GatilhoEstrutural
    ruido: bool
    abertura: int | None
    maxima: int | None
    minima: int | None
    regras: tuple[RegraDocumentada, ...] = field(default=())

    @property
    def mudou_de_regime(self) -> bool:
        return self.regime is not self.regime_anterior

    @property
    def lado(self) -> Side | None:
        return self.regime.lado

    @property
    def distancia_maxima_ticks(self) -> int | None:
        """Quanto falta, em ticks, para romper a máxima do dia."""
        if self.maxima is None:
            return None
        return self.maxima - self.preco

    @property
    def distancia_minima_ticks(self) -> int | None:
        """Quanto falta, em ticks, para perder a mínima do dia."""
        if self.minima is None:
            return None
        return self.preco - self.minima


_REGRAS = regras_de("estrutura.regime", "estrutura.ruido", "estrutura.amplitude_do_ruido")


class RegimeDoDia:
    """Regime estrutural a partir de preço puro. Sem coleções, sem book."""

    __slots__ = (
        "config",
        "_abertura",
        "_maxima",
        "_minima",
        "_regime",
        "_ultimo_preco",
        "_ultimo_ts",
    )

    def __init__(self, config: ConfigEstrutura | None = None) -> None:
        self.config = config or ConfigEstrutura()
        self._abertura: int | None = None
        self._maxima: int | None = None
        self._minima: int | None = None
        self._regime = RegimeEstrutural.INDEFINIDO
        self._ultimo_preco = 0
        self._ultimo_ts = 0

    # ------------------------------------------------------------------
    def registrar_preco(self, preco: int, timestamp_ns: int) -> LeituraEstrutural:
        """Alimenta um preço em TICKS (`int`, nunca float) e devolve a leitura.

        A checagem de rompimento roda **antes** de atualizar os extremos — do
        contrário todo preço novo já seria seu próprio extremo e nada jamais
        seria "perda de mínima".
        """
        if not isinstance(preco, int) or isinstance(preco, bool):
            raise TypeError("preco deve ser int em ticks (nunca float)")

        cfg = self.config
        anterior = self._regime
        gatilho = GatilhoEstrutural.NENHUM

        if self._abertura is None:
            self._abertura = self._maxima = self._minima = preco
        else:
            assert self._maxima is not None and self._minima is not None
            if preco > self._maxima + cfg.margem_ticks:
                gatilho = GatilhoEstrutural.ROMPEU_MAXIMA
                self._regime = RegimeEstrutural.COMPRADOR
            elif preco < self._minima - cfg.margem_ticks:
                gatilho = GatilhoEstrutural.PERDEU_MINIMA
                self._regime = RegimeEstrutural.VENDEDOR
            elif cfg.usar_abertura:
                # "ou a regiao de abertura": so dispara quando o preco cruza a
                # abertura SEM ter quebrado extremo — devolver o dia inteiro e
                # atravessar o open e mudanca de regime, mesmo dentro do range.
                abaixo = preco < self._abertura - cfg.margem_abertura_ticks
                acima = preco > self._abertura + cfg.margem_abertura_ticks
                if abaixo and self._regime is not RegimeEstrutural.VENDEDOR:
                    gatilho = GatilhoEstrutural.CRUZOU_ABERTURA
                    self._regime = RegimeEstrutural.VENDEDOR
                elif acima and self._regime is not RegimeEstrutural.COMPRADOR:
                    gatilho = GatilhoEstrutural.CRUZOU_ABERTURA
                    self._regime = RegimeEstrutural.COMPRADOR

            self._maxima = max(self._maxima, preco)
            self._minima = min(self._minima, preco)

        self._ultimo_preco = preco
        self._ultimo_ts = timestamp_ns

        return LeituraEstrutural(
            timestamp_ns=timestamp_ns,
            preco=preco,
            regime=self._regime,
            regime_anterior=anterior,
            gatilho=gatilho,
            ruido=self._ruido(preco, gatilho),
            abertura=self._abertura,
            maxima=self._maxima,
            minima=self._minima,
            regras=_REGRAS,
        )

    def _ruido(self, preco: int, gatilho: GatilhoEstrutural) -> bool:
        """Movimento CONTRA o regime que não quebrou estrutura nenhuma."""
        if gatilho is not GatilhoEstrutural.NENHUM:
            return False
        cfg = self.config
        if self._regime is RegimeEstrutural.COMPRADOR and self._maxima is not None:
            recuo = self._maxima - preco
            return recuo > 0 and recuo >= cfg.ruido_minimo_ticks
        if self._regime is RegimeEstrutural.VENDEDOR and self._minima is not None:
            recuo = preco - self._minima
            return recuo > 0 and recuo >= cfg.ruido_minimo_ticks
        return False

    # ------------------------------------------------------------------
    def registrar_candle(self, candle: Candle) -> LeituraEstrutural:
        """Alimenta um `Candle` OHLC quando não há tick disponível.

        **Limitação declarada:** a ordem em que máxima e mínima aconteceram
        DENTRO do candle não existe no dado. Esta função aplica O→H→L→C, então
        num candle que fez primeiro a mínima e depois a máxima ela pode marcar
        `ROMPEU_MAXIMA` antes de `PERDEU_MINIMA`, invertendo o regime final.
        Com tick disponível, use `registrar_preco` — a diferença é real e o
        caso WINFUT é justamente sobre não confundir a ordem dos eventos com
        o resultado agregado.
        """
        ts = candle.timestamp_ns
        self.registrar_preco(candle.open, ts)
        self.registrar_preco(candle.high, ts)
        self.registrar_preco(candle.low, ts)
        return self.registrar_preco(candle.close, ts)

    # ------------------------------------------------------------------
    @property
    def regime(self) -> RegimeEstrutural:
        return self._regime

    @property
    def abertura(self) -> int | None:
        return self._abertura

    @property
    def maxima(self) -> int | None:
        return self._maxima

    @property
    def minima(self) -> int | None:
        return self._minima

    @property
    def amplitude_ticks(self) -> int:
        if self._maxima is None or self._minima is None:
            return 0
        return self._maxima - self._minima

    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Virada EXPLÍCITA pelo chamador — mesma política de `EstadoMercado`.

        Máxima, mínima e abertura são "do dia" por definição; carregá-las para
        o dia seguinte faria o regime do dia 2 responder sobre o dia 1.
        """
        self._abertura = None
        self._maxima = None
        self._minima = None
        self._regime = RegimeEstrutural.INDEFINIDO
        self._ultimo_preco = 0
        self._ultimo_ts = 0
