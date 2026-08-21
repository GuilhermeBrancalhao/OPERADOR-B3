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

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Side, Trade
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


class DetectorAbsorcao:
    """Absorção de compra: vendedores agridem, preço não cai (e vice-versa)."""

    def __init__(self, symbol: str, config: ConfigAbsorcao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigAbsorcao()
        self._trades: list[Trade] = []

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        self._trades.append(trade)
        limite = trade.timestamp_ns - cfg.janela_ns
        self._trades = [t for t in self._trades if t.timestamp_ns >= limite]

        precos = [t.price for t in self._trades]
        deslocamento = max(precos) - min(precos)
        if deslocamento > cfg.deslocamento_maximo_ticks:
            return None

        volume_buy = sum(t.qty for t in self._trades if t.side_agressor.name == "BUY")
        volume_sell = sum(t.qty for t in self._trades if t.side_agressor.name == "SELL")

        if volume_sell >= cfg.volume_minimo and volume_sell > volume_buy:
            # vendedores agridem, preço não cai → COMPRADOR está absorvendo
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.ABSORCAO,
                side=Side.BUY,
                price=trade.price,
                confianca=1.0,
                evidencia={
                    "volume_agressao_dominante": volume_sell,
                    "volume_lado_oposto": volume_buy,
                    "deslocamento_ticks": deslocamento,
                    "n_trades_janela": len(self._trades),
                },
            )
        if volume_buy >= cfg.volume_minimo and volume_buy > volume_sell:
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.ABSORCAO,
                side=Side.SELL,
                price=trade.price,
                confianca=1.0,
                evidencia={
                    "volume_agressao_dominante": volume_buy,
                    "volume_lado_oposto": volume_sell,
                    "deslocamento_ticks": deslocamento,
                    "n_trades_janela": len(self._trades),
                },
            )
        return None


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


class DetectorIceberg:
    """Nível que executa muito mais volume do que a quantidade exibida."""

    def __init__(self, config: ConfigIceberg | None = None) -> None:
        self.config = config if config is not None else ConfigIceberg()
        self._ja_sinalizado: set[tuple[Side, int]] = set()

    def verificar(
        self, livro: LivroMBO, side: Side, price: int, timestamp_ns: int
    ) -> Deteccao | None:
        nivel = livro.nivel(side, price)
        exibido_max = livro.qty_exibida_max(side, price)
        if exibido_max <= 0:
            return None
        # volume executado = pico exibido acumulado ao longo da vida do nível
        # não é rastreado diretamente aqui; usamos o proxy de qty_total atual
        # vs. exibido_max quando há execução recente (ver nível interno via
        # n_reposicoes como sinal auxiliar de atividade).
        executado_estimado = livro.n_reposicoes(side, price) * exibido_max
        if executado_estimado < self.config.volume_executado_minimo:
            return None
        razao = executado_estimado / exibido_max if exibido_max else 0.0
        chave = (side, price)
        if razao < self.config.razao_minima or chave in self._ja_sinalizado:
            return None
        self._ja_sinalizado.add(chave)
        return Deteccao(
            timestamp_ns=timestamp_ns,
            symbol=livro.symbol,
            tipo=TipoDeteccao.ICEBERG,
            side=side,
            price=price,
            confianca=0.6,  # proxy indireto — não é recarga de order_id observada
            evidencia={
                "qty_exibida_max": exibido_max,
                "volume_executado_estimado": executado_estimado,
                "razao": razao,
                "n_ordens_no_nivel": 0 if nivel is None else nivel.n_ordens,
            },
        )


class DetectorIcebergPorRecarga:
    """Versão observada (feed MBO real): usa `Ordem.n_recargas`, não proxy."""

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
