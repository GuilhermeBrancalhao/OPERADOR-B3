"""Componentes QPainter do workspace ASG-like.

Esta e deliberadamente uma fronteira visual. Os paineis nao assinam o
barramento, nao leem sessao e nao inferem estado: recebem snapshots imutaveis
prontos uma vez por quadro. Assim a janela central pode integra-los depois sem
misturar thread de dados, regra de negocio e pintura.

A superficie inteira e consultiva. ``PainelDecisaoASG`` pinta essa ressalva
no proprio quadro e nao oferece sinal, callback ou API de envio de ordem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QGridLayout, QWidget

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

ALTURA_CABECALHO = 28
ALTURA_LINHA = 24
ALTURA_SELO = 18
MARGEM = 8
VAO = 4


@unique
class EstadoASG(Enum):
    AGUARDANDO = "AGUARDANDO"
    AO_VIVO = "AO VIVO"
    ATRASADO = "ATRASADO"
    SEM_BOOK = "SEM BOOK"
    ERRO = "ERRO"
    REPLAY = "REPLAY"


@unique
class ConfiancaASG(Enum):
    ALTA = "CONF ALTA"
    MEDIA = "CONF MEDIA"
    BAIXA = "CONF BAIXA"
    INDISPONIVEL = "CONF —"


@unique
class ProcedenciaASG(Enum):
    OBSERVADO = "OBSERVADO"
    DERIVADO = "DERIVADO"
    INFERIDO = "INFERIDO"
    REPLAY = "REPLAY"
    INDISPONIVEL = "SEM FONTE"


@unique
class DirecaoASG(Enum):
    COMPRA = "COMPRA"
    VENDA = "VENDA"
    NEUTRA = "NEUTRA"
    AGUARDAR = "AGUARDAR"


@unique
class ResultadoGate(Enum):
    PASSA = "✓ PASSA"
    BLOQUEIA = "× BLOQUEIA"
    AGUARDA = "○ AGUARDA"


_ROTULO_ESTADO = {
    EstadoASG.AGUARDANDO: "○ AGUARDANDO",
    EstadoASG.AO_VIVO: "● AO VIVO",
    EstadoASG.ATRASADO: "! ATRASADO",
    EstadoASG.SEM_BOOK: "× SEM BOOK",
    EstadoASG.ERRO: "× ERRO",
    EstadoASG.REPLAY: "▶ REPLAY",
}

_COR_ESTADO = {
    EstadoASG.AGUARDANDO: tema_asg.ESTADO_AGUARDANDO,
    EstadoASG.AO_VIVO: tema_asg.ESTADO_AO_VIVO,
    EstadoASG.ATRASADO: tema_asg.ESTADO_ATRASADO,
    EstadoASG.SEM_BOOK: tema_asg.ESTADO_SEM_BOOK,
    EstadoASG.ERRO: tema_asg.ESTADO_ERRO,
    EstadoASG.REPLAY: tema_asg.ESTADO_REPLAY,
}

_COR_CONFIANCA = {
    ConfiancaASG.ALTA: tema_asg.CONFIANCA_ALTA,
    ConfiancaASG.MEDIA: tema_asg.CONFIANCA_MEDIA,
    ConfiancaASG.BAIXA: tema_asg.CONFIANCA_BAIXA,
    ConfiancaASG.INDISPONIVEL: tema_asg.CONFIANCA_INDISPONIVEL,
}


def rotulo_estado(estado: EstadoASG) -> str:
    """Estado por simbolo + palavra; nunca depende apenas de cor."""

    return _ROTULO_ESTADO[estado]


def rotulo_direcao(direcao: DirecaoASG) -> str:
    return {
        DirecaoASG.COMPRA: "▲ COMPRA",
        DirecaoASG.VENDA: "▼ VENDA",
        DirecaoASG.NEUTRA: "◆ NEUTRA",
        DirecaoASG.AGUARDAR: "○ AGUARDAR",
    }[direcao]


def _cor_direcao(direcao: DirecaoASG, paleta: tokens.Paleta) -> QColor:
    if direcao is DirecaoASG.COMPRA:
        return paleta.compra
    if direcao is DirecaoASG.VENDA:
        return paleta.venda
    if direcao is DirecaoASG.AGUARDAR:
        return tokens.ALERT
    return paleta.neutro


@dataclass(frozen=True, slots=True)
class MetricaASG:
    nome: str
    valor: str
    unidade: str = ""
    detalhe: str = ""


@dataclass(frozen=True, slots=True)
class DadosASGSnapshot:
    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    fonte: str = "SEM FONTE"
    sequencia: int | None = None
    atraso_ms: float | None = None
    trades_s: float = 0.0
    niveis_book: int = 0
    gaps: int = 0
    descartados: int = 0
    confianca: ConfiancaASG = ConfiancaASG.INDISPONIVEL
    procedencia: ProcedenciaASG = ProcedenciaASG.INDISPONIVEL
    detalhe: str = "AGUARDANDO PRIMEIRO SNAPSHOT"

    @classmethod
    def de_feed(cls, snapshot: object) -> DadosASGSnapshot:
        """Adapta ``FeedQualitySnapshot`` sem acoplar a UI ao produtor.

        O contrato e estrutural: os nomes abaixo sao os campos publicos do
        snapshot de qualidade. Isso tambem permite fontes futuras oferecerem
        o mesmo retrato sem a UI precisar importar o adaptador concreto.
        """

        fonte = _valor_enum(getattr(snapshot, "source", getattr(snapshot, "fonte", "other")))
        book = _valor_enum(getattr(snapshot, "book_kind", "none"))
        estado_feed = _valor_enum(getattr(snapshot, "state", getattr(snapshot, "estado", "")))
        estado = _estado_do_feed(estado_feed, fonte, book)
        qualidade = _valor_enum(getattr(snapshot, "aggressor_quality", "unknown"))
        confianca, procedencia = _qualidade_do_agressor(qualidade, fonte)
        descartados = sum(
            int(getattr(snapshot, nome, 0))
            for nome in ("duplicates", "sequence_regressions", "regressive_timestamps")
        )
        detalhe = str(getattr(snapshot, "detail", "")).strip()
        if not detalhe:
            detalhe = f"BOOK {book.upper()} · AGRESSOR {qualidade.upper()}"
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=estado,
            fonte=fonte.upper(),
            sequencia=getattr(snapshot, "last_sequence", None),
            atraso_ms=float(getattr(snapshot, "latency_ns", 0)) / 1_000_000.0,
            trades_s=0.0,
            niveis_book=int(getattr(snapshot, "depth", getattr(snapshot, "profundidade", 0))),
            gaps=int(getattr(snapshot, "sequence_gaps", 0)),
            descartados=descartados,
            confianca=confianca,
            procedencia=procedencia,
            detalhe=detalhe,
        )


@dataclass(frozen=True, slots=True)
class EtapaProcessamentoASG:
    nome: str
    estado: str
    latencia_ms: float | None = None
    confianca: ConfiancaASG = ConfiancaASG.INDISPONIVEL
    procedencia: ProcedenciaASG = ProcedenciaASG.INDISPONIVEL
    detalhe: str = ""


@dataclass(frozen=True, slots=True)
class ProcessamentoASGSnapshot:
    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    versao: str = "—"
    etapas: tuple[EtapaProcessamentoASG, ...] = ()
    fila: int = 0
    perdas: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "etapas", tuple(self.etapas))

    @classmethod
    def de_maker(cls, snapshot: object) -> ProcessamentoASGSnapshot:
        """Adapta ``MakerProxySnapshot`` para o cano de processamento."""

        etapas = []
        for item in tuple(getattr(snapshot, "componentes", ())):
            score = float(getattr(item, "pontuacao", getattr(item, "score", 0.0)))
            nome = _valor_enum(getattr(item, "componente", "COMPONENTE")).upper()
            etapas.append(
                EtapaProcessamentoASG(
                    nome=nome,
                    estado="ATIVO" if abs(score) > 1e-9 else "NEUTRO",
                    confianca=_confianca_numerica(float(getattr(item, "confianca", 0.0))),
                    procedencia=_procedencia_do_maker(getattr(snapshot, "procedencia", "")),
                    detalhe=f"score {score:+.2f}".replace(".", ","),
                )
            )
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=_estado_do_maker(snapshot),
            versao=str(getattr(snapshot, "formula_version", "—")),
            etapas=tuple(etapas),
        )


@dataclass(frozen=True, slots=True)
class LinhaMatrizASG:
    componente: str
    direcao: DirecaoASG
    valor: str
    forca: float
    confianca: ConfiancaASG
    procedencia: ProcedenciaASG
    evidencias: int = 0
    detalhe: str = ""


@dataclass(frozen=True, slots=True)
class MatrizASGSnapshot:
    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    linhas: tuple[LinhaMatrizASG, ...] = ()
    cobertura: str = "0/0"
    modelo: str = "PROXY INDEPENDENTE · MAKER V1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "linhas", tuple(self.linhas))

    @classmethod
    def de_leitura(cls, leitura: object) -> MatrizASGSnapshot:
        """Adapta ``LeituraASG`` ou um ``MakerProxySnapshot`` diretamente."""

        maker = getattr(leitura, "maker", leitura)
        linhas = []
        procedencia = _procedencia_do_maker(getattr(maker, "procedencia", ""))
        for item in tuple(getattr(maker, "componentes", ())):
            score = float(getattr(item, "pontuacao", getattr(item, "score", 0.0)))
            linhas.append(
                LinhaMatrizASG(
                    componente=_valor_enum(getattr(item, "componente", "COMPONENTE")).upper(),
                    direcao=_direcao_de_score(score),
                    valor=f"{score:+.2f}".replace(".", ","),
                    forca=score,
                    confianca=_confianca_numerica(float(getattr(item, "confianca", 0.0))),
                    procedencia=procedencia,
                    evidencias=int(getattr(item, "n_evidencias", 0)),
                    detalhe=(f"cobertura {100 * float(getattr(item, 'cobertura', 0.0)):.0f}%"),
                )
            )
        cobertura = 100 * float(getattr(maker, "cobertura", 0.0))
        return cls(
            timestamp_ns=int(getattr(maker, "timestamp_ns")),
            estado=_estado_do_maker(maker),
            linhas=tuple(linhas),
            cobertura=f"{cobertura:.0f}%",
            modelo="PROXY INDEPENDENTE · " + str(getattr(maker, "formula_version", "MAKER V1")),
        )


@dataclass(frozen=True, slots=True)
class GateDecisaoASG:
    nome: str
    resultado: ResultadoGate
    motivo: str


@dataclass(frozen=True, slots=True)
class DecisaoASGSnapshot:
    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    direcao: DirecaoASG = DirecaoASG.AGUARDAR
    titulo: str = "SEM DECISAO"
    motivo: str = "Aguardando evidencias suficientes"
    confianca: ConfiancaASG = ConfiancaASG.INDISPONIVEL
    procedencia: ProcedenciaASG = ProcedenciaASG.INDISPONIVEL
    gates: tuple[GateDecisaoASG, ...] = ()
    stop: str = "—"
    alvo_1: str = "—"
    alvo_2: str = "—"
    alvo_3: str = "—"

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", tuple(self.gates))

    @classmethod
    def de_decisao(cls, snapshot: object) -> DecisaoASGSnapshot:
        """Adapta ``DecisionSnapshot``; niveis permanecem informativos."""

        leitura = getattr(snapshot, "leitura")
        maker = getattr(leitura, "maker", leitura)
        nivel = _valor_enum(getattr(snapshot, "nivel", "AGUARDAR")).upper()
        direcao = _direcao_externa(getattr(snapshot, "direcao", None))
        motivos = tuple(str(item) for item in getattr(snapshot, "motivos", ()))
        resultado = ResultadoGate.AGUARDA if nivel == "AGUARDAR" else ResultadoGate.PASSA
        gates = tuple(
            GateDecisaoASG(f"CRITERIO {i + 1}", resultado, motivo)
            for i, motivo in enumerate(motivos)
        )
        proposta = getattr(snapshot, "proposta_risco", None)

        def nivel_ticks(nome: str) -> str:
            if proposta is None:
                return "—"
            valor = getattr(proposta, nome, None)
            return "—" if valor is None else f"{int(valor)}t"

        procedencias = tuple(str(item) for item in getattr(snapshot, "procedencia", ()))
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=_estado_do_maker(maker),
            direcao=direcao,
            titulo=f"{nivel} {direcao.value}" if nivel != "AGUARDAR" else "SEM DECISAO",
            motivo=" · ".join(motivos) if motivos else "Aguardando evidencias suficientes",
            confianca=_confianca_numerica(float(getattr(leitura, "confianca", 0.0))),
            procedencia=_procedencia_textual(procedencias),
            gates=gates,
            stop=nivel_ticks("stop_ticks"),
            alvo_1=nivel_ticks("a1_ticks"),
            alvo_2=nivel_ticks("a2_ticks"),
            alvo_3=nivel_ticks("a3_ticks"),
        )


@dataclass(frozen=True, slots=True)
class EvidenciaASG:
    timestamp_ns: int
    origem: str
    evento: str
    leitura: str
    confianca: ConfiancaASG
    procedencia: ProcedenciaASG
    estado: EstadoASG = EstadoASG.AO_VIVO


@dataclass(frozen=True, slots=True)
class TrilhaEvidenciasASGSnapshot:
    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    itens: tuple[EvidenciaASG, ...] = ()
    total: int = 0
    retidos: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "itens", tuple(self.itens))

    @classmethod
    def de_maker(cls, snapshot: object, limite: int = 64) -> TrilhaEvidenciasASGSnapshot:
        """Achata evidencias limitadas do MakerProxy, da mais nova para a antiga."""

        itens = []
        for componente in tuple(getattr(snapshot, "componentes", ())):
            for evidencia in tuple(getattr(componente, "evidencias", ())):
                score = float(getattr(evidencia, "pontuacao", 0.0))
                itens.append(
                    EvidenciaASG(
                        timestamp_ns=int(getattr(evidencia, "timestamp_ns")),
                        origem=str(getattr(evidencia, "fonte", "MAKER")),
                        evento=str(getattr(evidencia, "tipo_evento", "EVIDENCIA")),
                        leitura=f"{score:+.2f}".replace(".", ","),
                        confianca=_confianca_numerica(
                            float(getattr(evidencia, "confianca", 0.0))
                        ),
                        procedencia=_procedencia_do_maker(
                            getattr(evidencia, "procedencia", "")
                        ),
                        estado=_estado_do_maker(snapshot),
                    )
                )
        itens.sort(key=lambda item: item.timestamp_ns, reverse=True)
        total = len(itens)
        retidos = tuple(itens[: max(0, limite)])
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=_estado_do_maker(snapshot),
            itens=retidos,
            total=total,
            retidos=len(retidos),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceASGSnapshot:
    """Um quadro coerente para os cinco paineis."""

    timestamp_ns: int
    dados: DadosASGSnapshot
    processamento: ProcessamentoASGSnapshot
    matriz: MatrizASGSnapshot
    decisao: DecisaoASGSnapshot
    evidencias: TrilhaEvidenciasASGSnapshot

    def __post_init__(self) -> None:
        carimbos = {
            self.dados.timestamp_ns,
            self.processamento.timestamp_ns,
            self.matriz.timestamp_ns,
            self.decisao.timestamp_ns,
            self.evidencias.timestamp_ns,
        }
        if carimbos != {self.timestamp_ns}:
            raise ValueError("WorkspaceASGSnapshot exige um unico timestamp por quadro")


class _PainelASG(PainelDenso):
    titulo = "ASG-LIKE"
    etapa = "0"
    cor_secao = tema_asg.EVIDENCIAS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.PAINEL)
        self.setMinimumSize(240, 112)

    def _cabecalho(self, painter: QPainter, estado: EstadoASG, meta: str = "") -> None:
        rect = QRect(0, 0, self.width(), ALTURA_CABECALHO)
        painter.fillRect(rect, tema_asg.CABECALHO)
        painter.fillRect(QRect(0, 0, 3, rect.height()), self.cor_secao)
        painter.setPen(tema_asg.BORDA)
        painter.drawLine(0, rect.bottom(), rect.right(), rect.bottom())

        painter.setFont(tokens.fonte_ui(11, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        titulo = f"{self.etapa}  {self.titulo}"
        painter.drawText(
            rect.adjusted(MARGEM, 0, -MARGEM, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            titulo,
        )

        estado_txt = rotulo_estado(estado)
        if meta and self.width() >= 420:
            estado_txt = f"{meta}  ·  {estado_txt}"
        painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
        painter.setPen(_COR_ESTADO[estado])
        painter.drawText(
            rect.adjusted(MARGEM, 0, -MARGEM, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            estado_txt,
        )

    def _chip(
        self, painter: QPainter, x: int, y: int, texto: str, fundo: QColor, altura: int = 16
    ) -> int:
        fonte = tokens.fonte_ui(9, QFont.Weight.DemiBold)
        largura = QFontMetrics(fonte).horizontalAdvance(texto) + 10
        rect = QRect(x, y, largura, altura)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fundo)
        painter.drawRoundedRect(rect, 2, 2)
        painter.setFont(fonte)
        painter.setPen(tema_asg.CHIP_TEXTO)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        return rect.right() + VAO

    def _chips_qualidade(
        self,
        painter: QPainter,
        x: int,
        y: int,
        confianca: ConfiancaASG,
        procedencia: ProcedenciaASG,
        completos: bool = True,
    ) -> int:
        conf = confianca.value if completos else confianca.value.replace("CONF ", "")
        proc = procedencia.value if completos else _abreviar_procedencia(procedencia)
        x = self._chip(painter, x, y, conf, _COR_CONFIANCA[confianca])
        return self._chip(painter, x, y, proc, tema_asg.EVIDENCIAS)

    def _vazio(self, painter: QPainter, mensagem: str) -> None:
        painter.setFont(tokens.fonte_ui(12))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, ALTURA_CABECALHO, self.width() - 2 * MARGEM,
                  self.height() - ALTURA_CABECALHO),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "○ " + mensagem,
        )


class PainelDadosASG(_PainelASG):
    titulo = "DADOS"
    etapa = "1"
    cor_secao = tema_asg.DADOS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = DadosASGSnapshot(0)
        self.setMinimumHeight(150)

    @property
    def snapshot(self) -> DadosASGSnapshot:
        return self._snapshot

    def aplicar(self, snapshot: DadosASGSnapshot) -> None:
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.marcar_tudo_sujo()

    def n_colunas(self) -> int:
        if self.width() >= 620:
            return 3
        if self.width() >= 360:
            return 2
        return 1

    def metricas(self) -> tuple[MetricaASG, ...]:
        s = self._snapshot
        atraso = "—" if s.atraso_ms is None else f"{s.atraso_ms:.1f}".replace(".", ",")
        sequencia = "—" if s.sequencia is None else formato.formatar_inteiro(s.sequencia)
        return (
            MetricaASG("SEQUENCIA", sequencia),
            MetricaASG("ATRASO", atraso, "ms"),
            MetricaASG("TRADES/S", f"{s.trades_s:.1f}".replace(".", ",")),
            MetricaASG("BOOK", formato.formatar_inteiro(s.niveis_book), "niveis"),
            MetricaASG("GAPS", formato.formatar_inteiro(s.gaps)),
            MetricaASG("DESCARTADOS", formato.formatar_inteiro(s.descartados)),
        )

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        return (rotulo_estado(s.estado), s.fonte, s.detalhe) + tuple(
            f"{m.nome} {m.valor} {m.unidade}".strip() for m in self.metricas()
        ) + (s.confianca.value, s.procedencia.value)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, s.fonte)

        y = ALTURA_CABECALHO + 6
        painter.setFont(tokens.fonte_ui(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        detalhe = s.fonte if self.width() < 420 else s.detalhe
        painter.drawText(QRect(MARGEM, y, self.width() - 2 * MARGEM, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detalhe)
        self._chips_qualidade(painter, MARGEM, y + 18, s.confianca, s.procedencia,
                              completos=self.width() >= 380)
        y += 40

        colunas = self.n_colunas()
        largura = max(1, (self.width() - 2 * MARGEM - (colunas - 1) * VAO) // colunas)
        linhas = (len(self.metricas()) + colunas - 1) // colunas
        altura = max(30, (self.height() - y - 6 - (linhas - 1) * VAO) // linhas)
        for i, metrica in enumerate(self.metricas()):
            coluna, linha = i % colunas, i // colunas
            rect = QRect(MARGEM + coluna * (largura + VAO), y + linha * (altura + VAO),
                         largura, altura)
            painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
            painter.setPen(tema_asg.BORDA)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_rotulo(9))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(rect.adjusted(6, 2, -6, -altura // 2),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             metrica.nome)
            painter.setFont(tokens.fonte_numero(13, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            valor = f"{metrica.valor} {metrica.unidade}".rstrip()
            painter.drawText(rect.adjusted(6, altura // 2 - 2, -6, -2),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, valor)


class PainelProcessamentoASG(_PainelASG):
    titulo = "PROCESSAMENTO"
    etapa = "2"
    cor_secao = tema_asg.PROCESSAMENTO

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = ProcessamentoASGSnapshot(0)
        self.setMinimumHeight(150)

    def aplicar(self, snapshot: ProcessamentoASGSnapshot) -> None:
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), f"VERSAO {s.versao}", f"FILA {s.fila}",
                  f"PERDAS {s.perdas}"]
        for etapa in s.etapas:
            textos.extend((etapa.nome, etapa.estado, etapa.detalhe,
                           etapa.confianca.value, etapa.procedencia.value))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, f"v{s.versao}")
        if not s.etapas:
            self._vazio(painter, "PROCESSAMENTO NAO INICIADO")
            return

        estreito = self.width() < 500
        altura = 38 if estreito else ALTURA_LINHA
        y = ALTURA_CABECALHO
        for indice, etapa in enumerate(s.etapas):
            if y >= self.height():
                break
            linha = QRect(0, y, self.width(), altura)
            if indice % 2:
                painter.fillRect(linha, tema_asg.FUNDO_NEUTRO)
            painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(QRect(MARGEM, y, 24, 22), Qt.AlignmentFlag.AlignVCenter,
                             f"{indice + 1:02d}")
            painter.setFont(tokens.fonte_ui(10, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(QRect(36, y, max(70, self.width() // 3), 22),
                             Qt.AlignmentFlag.AlignVCenter, etapa.nome)
            latencia = "— ms" if etapa.latencia_ms is None else (
                f"{etapa.latencia_ms:.1f} ms".replace(".", ","))
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(QRect(self.width() // 2, y, self.width() // 4, 22),
                             Qt.AlignmentFlag.AlignVCenter, latencia)
            painter.setPen(_cor_resultado_texto(etapa.estado))
            painter.drawText(QRect(0, y, self.width() - MARGEM, 22),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             _simbolo_estado_livre(etapa.estado))
            if estreito:
                self._chips_qualidade(painter, 36, y + 20, etapa.confianca,
                                      etapa.procedencia, completos=False)
            y += altura

        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(MARGEM, self.height() - 20, self.width() - 2 * MARGEM, 18),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"FILA {s.fila}  ·  PERDAS {s.perdas}")


class PainelMatrizASG(_PainelASG):
    titulo = "MATRIZ ASG-LIKE"
    etapa = "3"
    cor_secao = tema_asg.MATRIZ

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR) -> None:
        super().__init__(parent)
        self.paleta = paleta
        self._snapshot = MatrizASGSnapshot(0)
        self.setMinimumHeight(210)

    def aplicar(self, snapshot: MatrizASGSnapshot) -> None:
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.marcar_tudo_sujo()

    def modo_tabela(self) -> bool:
        return self.width() >= 640

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), s.modelo, f"COBERTURA {s.cobertura}"]
        for linha in s.linhas:
            textos.extend((linha.componente, rotulo_direcao(linha.direcao), linha.valor,
                           linha.detalhe, linha.confianca.value,
                           linha.procedencia.value, f"EVID {linha.evidencias}"))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, f"COBERTURA {s.cobertura}")
        selo = QRect(0, ALTURA_CABECALHO, self.width(), ALTURA_SELO)
        painter.fillRect(selo, tema_asg.FUNDO_NEUTRO)
        painter.setFont(tokens.fonte_ui(9, QFont.Weight.Bold))
        painter.setPen(tema_asg.MATRIZ)
        painter.drawText(selo, Qt.AlignmentFlag.AlignCenter, "PROXY INDEPENDENTE")
        if not s.linhas:
            painter.setFont(tokens.fonte_ui(12))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(MARGEM, selo.bottom(), self.width() - 2 * MARGEM,
                      self.height() - selo.bottom()),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "○ SEM LEITURA · MATRIZ AGUARDANDO EVIDENCIAS",
            )
            return
        if self.modo_tabela():
            self._desenhar_tabela(painter)
        else:
            self._desenhar_cartoes(painter)

    def _desenhar_tabela(self, painter: QPainter) -> None:
        y = ALTURA_CABECALHO + ALTURA_SELO
        cab = QRect(0, y, self.width(), 20)
        painter.fillRect(cab, tema_asg.FUNDO_NEUTRO)
        colunas = self._colunas()
        painter.setFont(tokens.fonte_rotulo(9))
        painter.setPen(tokens.TEXT_SECONDARY)
        for nome, rect in zip(("COMPONENTE", "LEITURA", "FORCA", "QUALIDADE", "EVID"), colunas):
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)
        y += cab.height()
        for indice, linha in enumerate(self._snapshot.linhas):
            rect = QRect(0, y + indice * 28, self.width(), 28)
            if rect.top() >= self.height():
                break
            if indice % 2:
                painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
            colunas = tuple(QRect(r.x(), rect.y(), r.width(), rect.height()) for r in self._colunas())
            painter.setFont(tokens.fonte_ui(10, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(colunas[0], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             linha.componente)
            painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
            painter.setPen(_cor_direcao(linha.direcao, self.paleta))
            painter.drawText(colunas[1], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{rotulo_direcao(linha.direcao)}  {linha.valor}")
            self._barra_forca(painter, colunas[2].adjusted(0, 9, -8, -9), linha.forca)
            self._chips_qualidade(painter, colunas[3].x(), rect.y() + 6,
                                  linha.confianca, linha.procedencia, completos=False)
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(colunas[4], Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(linha.evidencias))

    def _colunas(self) -> tuple[QRect, ...]:
        w = self.width() - 2 * MARGEM
        larguras = (int(w * .22), int(w * .25), int(w * .18), int(w * .27))
        x = MARGEM
        rects = []
        for largura in larguras:
            rects.append(QRect(x, ALTURA_CABECALHO + ALTURA_SELO, largura, 20))
            x += largura
        rects.append(QRect(x, ALTURA_CABECALHO + ALTURA_SELO,
                           self.width() - MARGEM - x, 20))
        return tuple(rects)

    def _desenhar_cartoes(self, painter: QPainter) -> None:
        y = ALTURA_CABECALHO + ALTURA_SELO + VAO
        for indice, linha in enumerate(self._snapshot.linhas):
            rect = QRect(MARGEM, y + indice * 48, self.width() - 2 * MARGEM, 44)
            if rect.top() >= self.height():
                break
            painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
            painter.setPen(tema_asg.BORDA)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_ui(10, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(rect.adjusted(6, 2, -6, -22), Qt.AlignmentFlag.AlignVCenter,
                             linha.componente)
            painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
            painter.setPen(_cor_direcao(linha.direcao, self.paleta))
            painter.drawText(rect.adjusted(6, 20, -6, -2), Qt.AlignmentFlag.AlignVCenter,
                             f"{rotulo_direcao(linha.direcao)}  {linha.valor}")
            self._chips_qualidade(painter, max(rect.x() + 100, rect.right() - 120), rect.y() + 4,
                                  linha.confianca, linha.procedencia, completos=False)

    def _barra_forca(self, painter: QPainter, rect: QRect, valor: float) -> None:
        painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
        centro = rect.center().x()
        painter.setPen(tema_asg.BORDA_FORTE)
        painter.drawLine(centro, rect.top(), centro, rect.bottom())
        fracao = min(1.0, max(-1.0, valor))
        largura = int(abs(fracao) * max(1, rect.width() // 2))
        if largura:
            if fracao > 0:
                painter.fillRect(QRect(centro + 1, rect.y(), largura, rect.height()), self.paleta.compra)
            else:
                painter.fillRect(QRect(centro - largura, rect.y(), largura, rect.height()), self.paleta.venda)
        # + / - nos extremos mantem o eixo legivel sem cor.
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(rect.adjusted(2, -3, -2, -3), Qt.AlignmentFlag.AlignLeft, "−")
        painter.drawText(rect.adjusted(2, -3, -2, -3), Qt.AlignmentFlag.AlignRight, "+")


class PainelDecisaoASG(_PainelASG):
    titulo = "DECISAO"
    etapa = "4"
    cor_secao = tema_asg.DECISAO

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR) -> None:
        super().__init__(parent)
        self.paleta = paleta
        self._snapshot = DecisaoASGSnapshot(0)
        self.setMinimumHeight(210)

    def aplicar(self, snapshot: DecisaoASGSnapshot) -> None:
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.marcar_tudo_sujo()

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), "CONSULTIVO · SEM ENVIO DE ORDENS",
                  rotulo_direcao(s.direcao), s.titulo, s.motivo,
                  s.confianca.value, s.procedencia.value,
                  f"STOP {s.stop}", f"A1 {s.alvo_1}", f"A2 {s.alvo_2}", f"A3 {s.alvo_3}"]
        for gate in s.gates:
            textos.extend((gate.nome, gate.resultado.value, gate.motivo))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado)
        faixa = QRect(0, ALTURA_CABECALHO, self.width(), 20)
        painter.fillRect(faixa, tema_asg.FUNDO_ALERTA)
        painter.setFont(tokens.fonte_ui(9, QFont.Weight.Bold))
        painter.setPen(tokens.ALERT)
        painter.drawText(faixa, Qt.AlignmentFlag.AlignCenter,
                         "CONSULTIVO · SEM ENVIO DE ORDENS")

        veredito = QRect(MARGEM, faixa.bottom() + VAO, self.width() - 2 * MARGEM, 50)
        fundo = (tema_asg.FUNDO_COMPRA if s.direcao is DirecaoASG.COMPRA else
                 tema_asg.FUNDO_VENDA if s.direcao is DirecaoASG.VENDA else
                 tema_asg.FUNDO_NEUTRO)
        painter.fillRect(veredito, fundo)
        painter.setPen(_cor_direcao(s.direcao, self.paleta))
        painter.setFont(tokens.fonte_ui(16, QFont.Weight.Bold))
        painter.drawText(veredito.adjusted(8, 2, -8, -22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         rotulo_direcao(s.direcao))
        painter.setFont(tokens.fonte_ui(10))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(veredito.adjusted(8, 24, -8, -2),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         s.titulo)
        self._chips_qualidade(painter, max(MARGEM, self.width() - 150),
                              veredito.y() + 4, s.confianca, s.procedencia, completos=False)

        y = veredito.bottom() + VAO
        painter.setFont(tokens.fonte_ui(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(MARGEM, y, self.width() - 2 * MARGEM, 30),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter |
                         Qt.TextFlag.TextWordWrap, s.motivo)
        y += 32
        for gate in s.gates:
            if y + ALTURA_LINHA >= self.height() - 24:
                break
            painter.setFont(tokens.fonte_ui(9, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(QRect(MARGEM, y, self.width() // 3, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, gate.nome)
            painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
            painter.setPen(_cor_gate(gate.resultado))
            painter.drawText(QRect(self.width() // 3, y, self.width() // 3, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, gate.resultado.value)
            painter.setFont(tokens.fonte_ui(9))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(QRect(2 * self.width() // 3, y,
                                   self.width() // 3 - MARGEM, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             gate.motivo)
            y += ALTURA_LINHA

        painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(QRect(MARGEM, self.height() - 22, self.width() - 2 * MARGEM, 20),
                         Qt.AlignmentFlag.AlignCenter,
                         f"STOP {s.stop}  ·  A1 {s.alvo_1}  ·  A2 {s.alvo_2}  ·  A3 {s.alvo_3}")


class PainelEvidenciasASG(_PainelASG):
    titulo = "TRILHA DE EVIDENCIAS"
    etapa = "5"
    cor_secao = tema_asg.EVIDENCIAS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = TrilhaEvidenciasASGSnapshot(0)
        self.setMinimumHeight(140)

    def aplicar(self, snapshot: TrilhaEvidenciasASGSnapshot) -> None:
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            self.marcar_tudo_sujo()

    @property
    def n_linhas(self) -> int:
        return max(0, (self.height() - ALTURA_CABECALHO) // ALTURA_LINHA)

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), f"{s.retidos} RETIDOS DE {s.total}"]
        for item in s.itens[:self.n_linhas]:
            textos.extend((item.origem, item.evento, item.leitura,
                           rotulo_estado(item.estado), item.confianca.value,
                           item.procedencia.value))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, f"{s.retidos}/{s.total} RETIDOS")
        if not s.itens:
            self._vazio(painter, "SEM EVIDENCIAS RETIDAS")
            return
        for indice, item in enumerate(s.itens[:self.n_linhas]):
            y = ALTURA_CABECALHO + indice * ALTURA_LINHA
            linha = QRect(0, y, self.width(), ALTURA_LINHA)
            if indice % 2:
                painter.fillRect(linha, tema_asg.FUNDO_NEUTRO)
            painter.setFont(tokens.fonte_numero(9))
            painter.setPen(_COR_ESTADO[item.estado])
            hora = formato.formatar_hora_ns(item.timestamp_ns)
            painter.drawText(QRect(MARGEM, y, 66, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, hora)
            painter.setFont(tokens.fonte_ui(9, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(QRect(76, y, max(60, self.width() // 7), ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, item.origem)
            painter.setFont(tokens.fonte_ui(9))
            painter.setPen(tokens.TEXT_SECONDARY)
            x = 82 + max(60, self.width() // 7)
            largura = max(20, self.width() - x - (170 if self.width() >= 640 else 8))
            texto = f"{_simbolo_estado_livre(item.evento)} {item.evento} · {item.leitura}"
            painter.drawText(QRect(x, y, largura, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, texto)
            if self.width() >= 640:
                self._chips_qualidade(painter, self.width() - 166, y + 4,
                                      item.confianca, item.procedencia, completos=False)


class WorkspaceASG(QWidget):
    """Composto responsivo pronto para ser inserido pela janela central.

    ``largo`` usa tres colunas, ``medio`` duas e ``estreito`` uma. A troca e
    feita apenas no resize do composto; os cinco filhos preservam backing e
    relogio proprios.
    """

    LIMIAR_LARGO = 1120
    LIMIAR_MEDIO = 720

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR) -> None:
        super().__init__(parent)
        self.dados = PainelDadosASG(self)
        self.processamento = PainelProcessamentoASG(self)
        self.matriz = PainelMatrizASG(self, paleta)
        self.decisao = PainelDecisaoASG(self, paleta)
        self.evidencias = PainelEvidenciasASG(self)
        self.paineis = (self.dados, self.processamento, self.matriz,
                        self.decisao, self.evidencias)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._snapshot: WorkspaceASGSnapshot | None = None
        self._modo = ""
        self._reorganizar(force=True)

    @property
    def modo_layout(self) -> str:
        return self._modo

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1280, 760)

    def aplicar(self, snapshot: WorkspaceASGSnapshot) -> None:
        """Aplica exatamente um snapshot tipado e coerente por quadro."""

        self._snapshot = snapshot
        self.dados.aplicar(snapshot.dados)
        self.processamento.aplicar(snapshot.processamento)
        self.matriz.aplicar(snapshot.matriz)
        self.decisao.aplicar(snapshot.decisao)
        self.evidencias.aplicar(snapshot.evidencias)

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._reorganizar()

    def _reorganizar(self, force: bool = False) -> None:
        largura = self.width()
        modo = ("largo" if largura >= self.LIMIAR_LARGO else
                "medio" if largura >= self.LIMIAR_MEDIO else "estreito")
        if modo == self._modo and not force:
            return
        self._modo = modo
        for painel in self.paineis:
            self._layout.removeWidget(painel)
        if modo == "largo":
            self._layout.addWidget(self.dados, 0, 0)
            self._layout.addWidget(self.processamento, 0, 1)
            self._layout.addWidget(self.decisao, 0, 2, 2, 1)
            self._layout.addWidget(self.matriz, 1, 0, 1, 2)
            self._layout.addWidget(self.evidencias, 2, 0, 1, 3)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 1)
            self._layout.setColumnStretch(2, 1)
        elif modo == "medio":
            self._layout.addWidget(self.dados, 0, 0)
            self._layout.addWidget(self.processamento, 0, 1)
            self._layout.addWidget(self.matriz, 1, 0)
            self._layout.addWidget(self.decisao, 1, 1)
            self._layout.addWidget(self.evidencias, 2, 0, 1, 2)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 1)
            self._layout.setColumnStretch(2, 0)
        else:
            for linha, painel in enumerate(self.paineis):
                self._layout.addWidget(painel, linha, 0)
            self._layout.setColumnStretch(0, 1)
            self._layout.setColumnStretch(1, 0)
            self._layout.setColumnStretch(2, 0)


def _abreviar_procedencia(procedencia: ProcedenciaASG) -> str:
    return {
        ProcedenciaASG.OBSERVADO: "OBS",
        ProcedenciaASG.DERIVADO: "DER",
        ProcedenciaASG.INFERIDO: "INF",
        ProcedenciaASG.REPLAY: "RPL",
        ProcedenciaASG.INDISPONIVEL: "S/FONTE",
    }[procedencia]


def _simbolo_estado_livre(texto: str) -> str:
    alto = texto.upper()
    if any(p in alto for p in ("ERRO", "FALHA", "BLOQUE", "SEM BOOK")):
        return "× " + texto
    if any(p in alto for p in ("AGUARD", "PENDENTE", "AQUEC")):
        return "○ " + texto
    return "✓ " + texto


def _cor_resultado_texto(texto: str) -> QColor:
    alto = texto.upper()
    if any(p in alto for p in ("ERRO", "FALHA", "BLOQUE", "SEM BOOK")):
        return tokens.DANGER
    if any(p in alto for p in ("AGUARD", "PENDENTE", "AQUEC")):
        return tokens.ALERT
    return tokens.OK


def _cor_gate(resultado: ResultadoGate) -> QColor:
    if resultado is ResultadoGate.PASSA:
        return tokens.OK
    if resultado is ResultadoGate.BLOQUEIA:
        return tokens.DANGER
    return tokens.ALERT


def _valor_enum(valor: object) -> str:
    """Valor textual de Enum/StrEnum sem importar o tipo produtor."""

    bruto = getattr(valor, "value", valor)
    return str(bruto)


def _estado_do_feed(estado: str, fonte: str, book: str) -> EstadoASG:
    estado = estado.lower()
    fonte = fonte.lower()
    book = book.lower()
    if estado == "error":
        return EstadoASG.ERRO
    if fonte == "replay":
        return EstadoASG.REPLAY
    if estado in {"degraded", "reconnecting"}:
        return EstadoASG.ATRASADO
    if estado == "connected" and book == "none":
        return EstadoASG.SEM_BOOK
    if estado == "connected":
        return EstadoASG.AO_VIVO
    return EstadoASG.AGUARDANDO


def _qualidade_do_agressor(qualidade: str, fonte: str) -> tuple[ConfiancaASG, ProcedenciaASG]:
    qualidade = qualidade.lower()
    if fonte.lower() == "replay":
        procedencia = ProcedenciaASG.REPLAY
    elif qualidade == "native":
        procedencia = ProcedenciaASG.OBSERVADO
    elif qualidade in {"inferred", "partial"}:
        procedencia = ProcedenciaASG.INFERIDO
    else:
        procedencia = ProcedenciaASG.INDISPONIVEL
    confianca = {
        "native": ConfiancaASG.ALTA,
        "partial": ConfiancaASG.MEDIA,
        "inferred": ConfiancaASG.BAIXA,
        "unknown": ConfiancaASG.INDISPONIVEL,
    }.get(qualidade, ConfiancaASG.INDISPONIVEL)
    return confianca, procedencia


def _confianca_numerica(valor: float) -> ConfiancaASG:
    if valor >= 0.75:
        return ConfiancaASG.ALTA
    if valor >= 0.45:
        return ConfiancaASG.MEDIA
    if valor > 0.0:
        return ConfiancaASG.BAIXA
    return ConfiancaASG.INDISPONIVEL


def _procedencia_do_maker(valor: object) -> ProcedenciaASG:
    texto = _valor_enum(valor).upper()
    if "OBSERV" in texto:
        return ProcedenciaASG.OBSERVADO
    if "INFER" in texto:
        return ProcedenciaASG.INFERIDO
    if "MISTA" in texto:
        return ProcedenciaASG.DERIVADO
    if "REPLAY" in texto:
        return ProcedenciaASG.REPLAY
    return ProcedenciaASG.INDISPONIVEL


def _procedencia_textual(valores: tuple[str, ...]) -> ProcedenciaASG:
    texto = " ".join(valores).upper()
    if "REPLAY" in texto:
        return ProcedenciaASG.REPLAY
    if "INFER" in texto:
        return ProcedenciaASG.INFERIDO
    if "OBSERV" in texto:
        return ProcedenciaASG.OBSERVADO
    if valores:
        return ProcedenciaASG.DERIVADO
    return ProcedenciaASG.INDISPONIVEL


def _direcao_de_score(score: float) -> DirecaoASG:
    if score > 1e-9:
        return DirecaoASG.COMPRA
    if score < -1e-9:
        return DirecaoASG.VENDA
    return DirecaoASG.NEUTRA


def _direcao_externa(valor: object) -> DirecaoASG:
    if valor is None:
        return DirecaoASG.AGUARDAR
    texto = _valor_enum(valor).upper()
    if texto in {"BUY", "COMPRA", "BID"}:
        return DirecaoASG.COMPRA
    if texto in {"SELL", "VENDA", "ASK"}:
        return DirecaoASG.VENDA
    return DirecaoASG.NEUTRA


def _estado_do_maker(snapshot: object) -> EstadoASG:
    texto = _valor_enum(getattr(snapshot, "estado", "SEM_DADOS")).upper()
    return EstadoASG.AGUARDANDO if texto in {"SEM_DADOS", "AGUARDANDO"} else EstadoASG.AO_VIVO


__all__ = [
    "ConfiancaASG",
    "DadosASGSnapshot",
    "DecisaoASGSnapshot",
    "DirecaoASG",
    "EstadoASG",
    "EtapaProcessamentoASG",
    "EvidenciaASG",
    "GateDecisaoASG",
    "LinhaMatrizASG",
    "MatrizASGSnapshot",
    "MetricaASG",
    "PainelDadosASG",
    "PainelDecisaoASG",
    "PainelEvidenciasASG",
    "PainelMatrizASG",
    "PainelProcessamentoASG",
    "ProcedenciaASG",
    "ProcessamentoASGSnapshot",
    "ResultadoGate",
    "TrilhaEvidenciasASGSnapshot",
    "WorkspaceASG",
    "WorkspaceASGSnapshot",
    "rotulo_direcao",
    "rotulo_estado",
]
