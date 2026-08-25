"""Gráficos causais da superfície OPERADOR B3.

O gráfico não fabrica candles para preencher a tela. Ele agrega somente os
itens recebidos pela ponte, no timeframe configurado, e mantém um teto fixo
de 512 velas. Essa escolha é deliberada: uma lista ilimitada seria invisível
num retrato curto, mas cresceria durante um pregão inteiro e violaria a lei de
retenção já medida no núcleo. A escala trabalha em ticks inteiros; conversão
para preço decimal só acontece ao formatar um rótulo.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPainter, QPolygon

from fluxopro.core.eventos import Candle, PriceGrid
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.ponte import ItemTape


@dataclass(slots=True)
class AgregadorCandles:
    """Converte ``ItemTape`` em ``Candle`` fechado sem lookahead.

    A vela corrente é substituída apenas por trades cujo timestamp já chegou;
    quando o bucket muda, a vela anterior entra numa ``deque(maxlen=512)``.
    Trades fora de ordem são ignorados, porque aceitar um timestamp regressivo
    alteraria uma vela que a UI já exibiu e faria replay e ao vivo divergirem.
    ``agressor == 0`` permanece no volume total e no campo de volume não
    atribuído, nunca é inventado como compra ou venda.
    """

    grid: PriceGrid
    timeframe_ns: int
    MAX_CANDLES: int = 512
    _velas: deque[Candle] = field(init=False, repr=False)
    _corrente: Candle | None = field(default=None, init=False, repr=False)
    _ultimo_timestamp_ns: int = field(default=-1, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.timeframe_ns <= 0:
            raise ValueError("timeframe_ns deve ser positivo")
        if self.MAX_CANDLES <= 0:
            raise ValueError("MAX_CANDLES deve ser positivo")
        self._velas = deque(maxlen=self.MAX_CANDLES)

    def aplicar(self, novos: tuple[ItemTape, ...]) -> bool:
        fechou = False
        for item in novos:
            timestamp_ns = int(item.timestamp_ns)
            if timestamp_ns < self._ultimo_timestamp_ns:
                continue
            self._ultimo_timestamp_ns = timestamp_ns
            inicio = (timestamp_ns // self.timeframe_ns) * self.timeframe_ns
            volume = int(item.qty)
            delta = int(item.qty) if item.agressor > 0 else -int(item.qty) if item.agressor < 0 else 0
            desconhecido = int(item.qty) if item.agressor == 0 else 0
            corrente = self._corrente
            if corrente is None or corrente.timestamp_ns != inicio:
                if corrente is not None:
                    self._velas.append(corrente)
                    fechou = True
                self._corrente = Candle(
                    timestamp_ns=inicio,
                    open=int(item.price), high=int(item.price), low=int(item.price),
                    close=int(item.price), volume=volume, delta=delta,
                    volume_nao_atribuido=desconhecido,
                )
                continue
            self._corrente = Candle(
                timestamp_ns=inicio,
                open=corrente.open,
                high=max(corrente.high, int(item.price)),
                low=min(corrente.low, int(item.price)),
                close=int(item.price),
                volume=corrente.volume + volume,
                delta=corrente.delta + delta,
                volume_nao_atribuido=corrente.volume_nao_atribuido + desconhecido,
            )
        return fechou

    def velas(self) -> tuple[Candle, ...]:
        return tuple(self._velas) + ((self._corrente,) if self._corrente is not None else ())

    def vela_corrente(self) -> Candle | None:
        return self._corrente


@dataclass(frozen=True, slots=True)
class EixoPrecoGrafico:
    """Mapeia ticks para pixels sem transformar preço em ``float``."""

    minimo: int
    maximo: int
    topo: int
    altura: int

    def y(self, preco_ticks: int) -> int:
        amplitude = max(1, self.maximo - self.minimo)
        fracao = max(0, min(amplitude, int(preco_ticks) - self.minimo))
        return self.topo + self.altura - (fracao * max(1, self.altura - 1) // amplitude)


class PainelMiniTape(PainelDenso):
    """Linha de tape compacta, limitada a 256 impressões e sem efeitos de ordem."""

    def __init__(self, parent=None, capacidade: int = 256) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)
        self._itens: deque[ItemTape] = deque(maxlen=capacidade)
        self._ultimo_preco: int | None = None

    def aplicar(self, novos: tuple[ItemTape, ...], ultimo_preco: int | None) -> None:
        if novos:
            self._itens.extend(novos)
        self._ultimo_preco = ultimo_preco
        self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        return ("MINI-TAPE", "OBSERVADO", "SEM ENVIO DE ORDENS")

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        itens = tuple(self._itens)
        if len(itens) < 2:
            painter.setPen(tema_asg.NEXO_TEXTO)
            painter.setFont(tokens.fonte_rotulo(9))
            painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO PRIMEIRO EVENTO")
            return
        precos = [item.price for item in itens]
        minimo, maximo = min(precos), max(precos)
        eixo = EixoPrecoGrafico(minimo, maximo, regiao.top() + 8, max(1, regiao.height() - 16))
        pontos: list[QPoint] = []
        for indice, item in enumerate(itens):
            x = regiao.left() + 4 + indice * max(1, (regiao.width() - 8) // max(1, len(itens) - 1))
            pontos.append(QPoint(x, eixo.y(item.price)))
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawPolyline(QPolygon(pontos))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(regiao.adjusted(4, 3, -4, -3), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         "MINI-TAPE · OBSERVADO")


class PainelGrafico(PainelDenso):
    """Candles e níveis, consumindo somente retratos congelados da UI."""

    def __init__(self, grid: PriceGrid, timeframe_ns: int, parent=None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.NEXO_FUNDO)
        self.grid = grid
        self.agregador = AgregadorCandles(grid, timeframe_ns)
        self._ultimo_preco: int | None = None

    def aplicar(self, novos: tuple[ItemTape, ...], leitura=None, retrato=None,
                ultimo_preco: int | None = None) -> None:
        self.agregador.aplicar(tuple(novos))
        self._ultimo_preco = ultimo_preco
        self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        corrente = self.agregador.vela_corrente()
        return (
            "GRAFICO DO ATIVO", "CANDLE OBSERVADO", "OHLC CAUSAL",
            "SEM LOOKAHEAD", "AGUARDANDO GRAFICO" if corrente is None else "VELA EM FORMACAO",
        )

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        velas = self.agregador.velas()
        if not velas:
            painter.setPen(tema_asg.NEXO_TEXTO)
            painter.setFont(tokens.fonte_rotulo(9))
            painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO GRAFICO DO ATIVO")
            return
        precos = [preco for vela in velas for preco in (vela.high, vela.low)]
        eixo = EixoPrecoGrafico(min(precos), max(precos), regiao.top() + 14,
                                max(1, regiao.height() - 30))
        painter.setPen(tema_asg.NEXO_GRADE)
        for fracao in (0.25, 0.50, 0.75):
            y = regiao.top() + int(regiao.height() * fracao)
            painter.drawLine(regiao.left(), y, regiao.right(), y)
        largura = max(3, (regiao.width() - 18) // max(1, len(velas) * 2))
        for indice, vela in enumerate(velas):
            x = regiao.left() + 9 + indice * max(1, (regiao.width() - 18) // max(1, len(velas)))
            cor = tema_asg.NEXO_VERDE if vela.close >= vela.open else tema_asg.NEXO_ROSA
            painter.setPen(cor)
            painter.drawLine(x, eixo.y(vela.high), x, eixo.y(vela.low))
            topo = min(eixo.y(vela.open), eixo.y(vela.close))
            baixo = max(eixo.y(vela.open), eixo.y(vela.close))
            painter.fillRect(QRect(x - largura // 2, topo, largura, max(2, baixo - topo)), cor)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(regiao.adjusted(5, 3, -5, -3), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         "CANDLE OBSERVADO · OHLC CAUSAL")
        painter.drawText(regiao.adjusted(5, 3, -5, -3), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                         "SEM LOOKAHEAD")


__all__ = ["AgregadorCandles", "EixoPrecoGrafico", "PainelGrafico", "PainelMiniTape"]
