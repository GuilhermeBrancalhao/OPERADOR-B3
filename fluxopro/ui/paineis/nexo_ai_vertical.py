"""Painel vertical NEXO AI, uma superfície consultiva baseada em snapshots.

O módulo é deliberadamente independente do compositor ASG legado. Ele recebe
um ``WorkspaceASGSnapshot`` imutável, deriva apenas valores de apresentação e
desenha uma experiência vertical: núcleo grande, gráfico e três cartões.
Nenhuma regra de decisão ou chamada de mercado mora nesta camada.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Iterable

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QSizePolicy, QWidget

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.asg import (
    ContextoBrutoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    WorkspaceASGSnapshot,
)


@dataclass(frozen=True, slots=True)
class NexoAICardSnapshot:
    titulo: str
    valor: str
    detalhe: str
    percentual: float | None
    estado: str
    procedencia: str


@dataclass(frozen=True, slots=True)
class NexoAISnapshot:
    timestamp_ns: int
    simbolo: str
    preco: int | None
    serie_preco: tuple[int, ...]
    direcao: str
    forca_mercado: float | None
    fase: str
    confianca_decisao: float | None
    confianca_feed: float | None
    maker_proxy: float | None
    dominancia: float | None
    delta: str
    agressao: str
    absorcao: str
    reposicao: str
    clips: str
    pre_sinal: str
    confirmacao: str
    regiao: str
    stop_informativo: str
    alvos_informativos: tuple[str, str, str]
    bloqueios: tuple[str, ...]
    procedencia: str
    book_kind: str
    replay: bool
    estado_feed: str
    cards: tuple[NexoAICardSnapshot, NexoAICardSnapshot, NexoAICardSnapshot]

    @classmethod
    def de_workspace(
        cls, snapshot: WorkspaceASGSnapshot, simbolo: str = "WDO"
    ) -> "NexoAISnapshot":
        contexto = snapshot.contexto_bruto or ContextoBrutoASGSnapshot(
            snapshot.timestamp_ns,
            estado=snapshot.estado_operacional or snapshot.dados.estado,
        )
        serie = tuple(int(item.preco) for item in contexto.negocios[-240:])
        if not serie and contexto.ultimo_preco is not None:
            serie = (int(contexto.ultimo_preco),)

        def linha(nome: str):
            return next((item for item in snapshot.matriz.linhas if item.componente == nome), None)

        def valor(nome: str, default: str = "SEM DADOS") -> str:
            item = linha(nome)
            return default if item is None else item.valor

        def forca(nome: str) -> float | None:
            item = linha(nome)
            return None if item is None else max(-1.0, min(1.0, float(item.forca)))

        def confianca_numerica(texto: str) -> float | None:
            normalizado = texto.upper()
            return {"ALTA": 0.85, "MEDIA": 0.60, "BAIXA": 0.30}.get(normalizado)

        direcao = snapshot.decisao.direcao.value
        fase = snapshot.decisao.titulo or "AGUARDAR"
        bloqueios = tuple(
            gate.motivo for gate in snapshot.decisao.gates
            if "AGUARDA" in gate.resultado.value.upper()
        )
        maker = linha("MAKERPROXY")
        dominancia = forca("MICRO")
        forca_mercado = dominancia if dominancia is not None else forca("VELOCIMETRO")
        feed_conf = confianca_numerica(snapshot.dados.confianca.value)
        decisao_conf = confianca_numerica(snapshot.decisao.confianca.value)
        estado = snapshot.estado_operacional or snapshot.dados.estado
        book_kind = "MBP" if contexto.bids or contexto.asks else "NONE"
        procedencia = snapshot.decisao.procedencia.value
        status = estado.value.upper()

        cards = (
            NexoAICardSnapshot(
                "AGUARDAR",
                "AGUARDAR" if snapshot.decisao.direcao is DirecaoASG.AGUARDAR else direcao,
                fase.upper()[:42],
                None,
                status,
                procedencia,
            ),
            NexoAICardSnapshot(
                "CONFIANÇA",
                "—" if decisao_conf is None else f"{decisao_conf * 100:.0f}%",
                f"FEED {('—' if feed_conf is None else f'{feed_conf * 100:.0f}%')} · {snapshot.matriz.cobertura}",
                decisao_conf,
                status,
                procedencia,
            ),
            NexoAICardSnapshot(
                "FORÇA DO FLUXO",
                "—" if forca_mercado is None else f"{forca_mercado * 100:+.0f}%",
                f"MAKER {('—' if maker is None else maker.valor)} · {book_kind}",
                forca_mercado,
                status,
                "DERIVADO" if maker is not None else "SEM DADOS",
            ),
        )
        return cls(
            timestamp_ns=snapshot.timestamp_ns,
            simbolo=simbolo,
            preco=contexto.ultimo_preco,
            serie_preco=serie,
            direcao=direcao,
            forca_mercado=forca_mercado,
            fase=fase,
            confianca_decisao=decisao_conf,
            confianca_feed=feed_conf,
            maker_proxy=None if maker is None else maker.forca,
            dominancia=dominancia,
            delta=valor("MICRO"),
            agressao=valor("VELOCIMETRO"),
            absorcao=valor("ABSORCAO"),
            reposicao=valor("REPOSICAO"),
            clips=valor("CLIPS"),
            pre_sinal="SIM" if any("PRE" in item.upper() for item in bloqueios) else "NÃO",
            confirmacao="SIM" if snapshot.decisao.direcao is not DirecaoASG.AGUARDAR else "NÃO",
            regiao="VALIDA" if snapshot.decisao.stop != "—" else "AGUARDANDO",
            stop_informativo=snapshot.decisao.stop,
            alvos_informativos=(snapshot.decisao.alvo_1, snapshot.decisao.alvo_2, snapshot.decisao.alvo_3),
            bloqueios=bloqueios,
            procedencia=procedencia,
            book_kind=book_kind,
            replay=estado is EstadoASG.REPLAY,
            estado_feed=status,
            cards=cards,
        )


class PainelNexoAIVertical(QWidget):
    """Painel vertical funcional: núcleo, gráfico e três cards empilhados."""

    def __init__(self, parent: QWidget | None = None, simbolo: str = "WDO") -> None:
        super().__init__(parent)
        self.simbolo = simbolo
        self._snapshot = NexoAISnapshot.de_workspace(self._snapshot_vazio(), simbolo)
        self._historico: deque[float] = deque(maxlen=120)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(250, 520)

    @staticmethod
    def _snapshot_vazio() -> WorkspaceASGSnapshot:
        from fluxopro.ui.paineis.asg import (
            DadosASGSnapshot, DecisaoASGSnapshot, MatrizASGSnapshot,
            ProcessamentoASGSnapshot, TrilhaEvidenciasASGSnapshot,
        )
        return WorkspaceASGSnapshot(
            0, DadosASGSnapshot(0), ProcessamentoASGSnapshot(0),
            MatrizASGSnapshot(0), DecisaoASGSnapshot(0),
            TrilhaEvidenciasASGSnapshot(0), contexto_bruto=ContextoBrutoASGSnapshot(0),
        )

    def aplicar(self, snapshot: WorkspaceASGSnapshot) -> None:
        self._snapshot = NexoAISnapshot.de_workspace(snapshot, self.simbolo)
        if self._snapshot.forca_mercado is not None:
            self._historico.append(self._snapshot.forca_mercado)
        self.update()

    def aplicar_mercado(self, retrato: object) -> None:
        """Atualiza somente preço/série com o retrato bruto do mesmo quadro."""

        negocios = tuple(getattr(retrato, "novos_trades", ()))
        pontos = tuple(int(getattr(item, "price")) for item in negocios)
        if pontos:
            serie = tuple((self._snapshot.serie_preco + pontos)[-240:])
            forca = self._snapshot.forca_mercado
            self._snapshot = replace(
                self._snapshot,
                preco=int(getattr(retrato, "ultimo_preco", pontos[-1])),
                serie_preco=serie,
            )
            if forca is not None:
                self._historico.append(forca)
        elif getattr(retrato, "ultimo_preco", None) is not None:
            preco = int(getattr(retrato, "ultimo_preco"))
            serie = self._snapshot.serie_preco
            if not serie or serie[-1] != preco:
                serie = tuple((serie + (preco,))[-240:])
            self._snapshot = replace(
                self._snapshot, preco=preco, serie_preco=serie
            )
        self.update()

    @property
    def snapshot(self) -> NexoAISnapshot:
        return self._snapshot

    def sizeHint(self):  # noqa: N802
        from PySide6.QtCore import QSize
        return QSize(420, 860)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#05080d"))
        largura = min(540, max(250, self.width() - 24))
        esquerda = self.rect().center().x() - largura // 2
        rect = QRect(esquerda, 8, largura, max(0, self.height() - 16))
        self._cabecalho(painter, rect)
        y = rect.top() + 34
        nucleo_h = max(230, int(rect.height() * 0.39))
        grafico_h = max(92, int(rect.height() * 0.15))
        card_h = max(78, int((rect.height() - nucleo_h - grafico_h - 56) / 3))
        self._nucleo(painter, QRect(rect.left(), y, rect.width(), nucleo_h))
        y += nucleo_h + 8
        self._grafico(painter, QRect(rect.left(), y, rect.width(), grafico_h))
        y += grafico_h + 8
        for card in self._snapshot.cards:
            self._card(painter, QRect(rect.left(), y, rect.width(), card_h), card)
            y += card_h + 8
        self._rodape(painter, rect)

    def _cabecalho(self, p: QPainter, r: QRect) -> None:
        p.setFont(tokens.fonte_ui(11, QFont.Weight.Bold))
        p.setPen(QColor("#e7f7ff"))
        p.drawText(r.adjusted(4, 0, -4, -r.height() + 22), Qt.AlignmentFlag.AlignLeft, "NEXO AI")
        p.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        p.setPen(QColor("#6b93a6"))
        meta = f"{self._snapshot.simbolo}  ·  {self._snapshot.estado_feed}  ·  {'REPLAY' if self._snapshot.replay else 'AO VIVO'}"
        p.drawText(r.adjusted(4, 0, -4, -r.height() + 22), Qt.AlignmentFlag.AlignRight, meta)

    def _nucleo(self, p: QPainter, r: QRect) -> None:
        self._moldura(p, r, "NÚCLEO DE LEITURA")
        cx, cy = r.center().x(), r.top() + int(r.height() * 0.47)
        raio = max(65, min(125, min(r.width(), r.height()) // 3))
        cor = self._cor_direcao(self._snapshot.direcao)
        for extra, alpha in ((28, 30), (18, 65), (8, 130)):
            p.setPen(QPen(QColor(cor.red(), cor.green(), cor.blue(), alpha), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPoint(cx, cy), raio + extra, raio + extra)
        grad = QLinearGradient(cx - raio, cy - raio, cx + raio, cy + raio)
        grad.setColorAt(0.0, QColor("#203b58"))
        grad.setColorAt(0.55, QColor("#142234"))
        grad.setColorAt(1.0, QColor(cor.red(), cor.green(), cor.blue(), 180))
        p.setPen(QPen(cor, 2))
        p.setBrush(grad)
        p.drawEllipse(QPoint(cx, cy), raio, raio)
        p.setBrush(QColor("#071019"))
        p.drawEllipse(QPoint(cx, cy), max(20, raio // 3), max(20, raio // 3))
        p.setPen(cor)
        p.setFont(tokens.fonte_numero(max(18, raio // 3), QFont.Weight.Bold))
        valor = "—" if self._snapshot.forca_mercado is None else f"{self._snapshot.forca_mercado * 100:+.0f}%"
        p.drawText(QRect(cx - raio, cy - 20, 2 * raio, 40), Qt.AlignmentFlag.AlignCenter, valor)
        p.setFont(tokens.fonte_ui(9, QFont.Weight.Bold))
        p.drawText(QRect(cx - raio - 12, cy + raio + 8, 2 * raio + 24, 20), Qt.AlignmentFlag.AlignCenter, self._snapshot.direcao.upper())
        p.setFont(tokens.fonte_rotulo(7))
        p.setPen(QColor("#7594a3"))
        p.drawText(r.adjusted(10, 0, -10, -10), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, f"PREÇO  {self._preco()}")
        p.drawText(r.adjusted(10, 0, -10, -10), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, "CONSULTIVO · SEM ORDENS")

    def _grafico(self, p: QPainter, r: QRect) -> None:
        self._moldura(p, r, "GRÁFICO DO ATIVO · FORÇA DO MERCADO")
        area = r.adjusted(8, 24, -8, -8)
        serie = self._snapshot.serie_preco
        if len(serie) < 2:
            p.setPen(QColor("#67808d"))
            p.setFont(tokens.fonte_rotulo(8))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO DADOS DE MERCADO")
            return
        lo, hi = min(serie), max(serie)
        escala = max(1, hi - lo)
        pontos = [QPoint(area.left() + i * area.width() // (len(serie) - 1), area.bottom() - (v - lo) * area.height() // escala) for i, v in enumerate(serie)]
        p.setPen(QPen(self._cor_direcao(self._snapshot.direcao), 2))
        p.drawPolyline(QPolygon(pontos))
        p.setPen(QColor("#37505f"))
        for f in (0.25, 0.5, 0.75):
            p.drawLine(area.left(), area.top() + int(area.height() * f), area.right(), area.top() + int(area.height() * f))

    def _card(self, p: QPainter, r: QRect, card: NexoAICardSnapshot) -> None:
        cor = self._cor_status(card.estado)
        self._moldura(p, r, card.titulo)
        p.setPen(cor)
        p.setFont(tokens.fonte_numero(max(15, min(24, r.height() // 4)), QFont.Weight.Bold))
        p.drawText(r.adjusted(12, 23, -12, -r.height() + 54), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, card.valor)
        p.setPen(QColor("#9bb2bd"))
        p.setFont(tokens.fonte_rotulo(8))
        p.drawText(r.adjusted(12, 48, -12, -8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, card.detalhe)
        p.setPen(QColor("#6a8794"))
        p.drawText(r.adjusted(12, 0, -12, -8), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, card.procedencia)
        if card.percentual is not None:
            bar = QRect(r.left() + 12, r.bottom() - 7, max(0, r.width() - 24), 3)
            p.fillRect(bar, QColor("#142631"))
            p.fillRect(QRect(bar.left(), bar.top(), int(bar.width() * max(0.0, min(1.0, card.percentual))), bar.height()), cor)

    def _rodape(self, p: QPainter, r: QRect) -> None:
        p.setPen(QColor("#587482"))
        p.setFont(tokens.fonte_rotulo(7))
        p.drawText(r.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, "DADOS OBSERVADOS · DERIVAÇÕES IDENTIFICADAS")
        p.drawText(r.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, "NEXO v2")

    @staticmethod
    def _moldura(p: QPainter, r: QRect, titulo: str) -> None:
        p.fillRect(r, QColor("#0a1119"))
        p.setPen(QPen(QColor("#1e3542"), 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setPen(QColor("#6f91a0"))
        p.setFont(tokens.fonte_rotulo(8))
        p.drawText(r.adjusted(10, 4, -10, -r.height() + 19), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)

    @staticmethod
    def _cor_direcao(direcao: str) -> QColor:
        texto = direcao.upper()
        if "VENDA" in texto:
            return QColor("#ff6f9f")
        if "COMPRA" in texto:
            return QColor("#38e0b1")
        return QColor("#f0c36b")

    @staticmethod
    def _cor_status(status: str) -> QColor:
        texto = status.upper()
        if "ERRO" in texto:
            return QColor("#ff6f9f")
        if "VIVO" in texto or "REPLAY" in texto:
            return QColor("#38e0b1")
        return QColor("#f0c36b")

    def _preco(self) -> str:
        if self._snapshot.preco is None:
            return "—"
        try:
            inteiro, fracao = formato.formatar_preco(self._snapshot_preco_grid(), self._snapshot.preco)
            return f"{inteiro}{fracao}"
        except Exception:
            return str(self._snapshot.preco)

    @staticmethod
    def _snapshot_preco_grid():
        from fluxopro.core.eventos import WDO_GRID
        return WDO_GRID
