"""Componentes QPainter do workspace ASG-like.

Esta e deliberadamente uma fronteira visual. Os paineis nao assinam o
barramento, nao leem sessao e nao inferem estado: recebem snapshots imutaveis
prontos uma vez por quadro. Assim a janela central pode integra-los depois sem
misturar thread de dados, regra de negocio e pintura.

A superficie inteira e consultiva. ``PainelDecisaoASG`` pinta essa ressalva
no proprio quadro e nao oferece sinal, callback ou API de envio de ordem.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace as dataclass_replace
from enum import Enum, unique

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QGridLayout, QWidget

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

ALTURA_CABECALHO = 28
ALTURA_LINHA = 24
ALTURA_SELO = 18
ALTURA_RODAPE = 20
MARGEM = 8
VAO = 4


@unique
class EstadoASG(Enum):
    DESCONHECIDO = "DESCONHECIDO"
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
    EstadoASG.DESCONHECIDO: "? DESCONHECIDO",
    EstadoASG.AGUARDANDO: "○ AGUARDANDO",
    EstadoASG.AO_VIVO: "● AO VIVO",
    EstadoASG.ATRASADO: "! ATRASADO",
    EstadoASG.SEM_BOOK: "× SEM BOOK",
    EstadoASG.ERRO: "× ERRO",
    EstadoASG.REPLAY: "▶ REPLAY",
}

_COR_ESTADO = {
    EstadoASG.DESCONHECIDO: tema_asg.ESTADO_DESCONHECIDO,
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
    gaps: int | None = 0
    anomalias: int = 0
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
        anomalias = sum(
            int(getattr(snapshot, nome, 0) or 0)
            for nome in ("duplicates", "sequence_regressions", "regressive_timestamps")
        )
        gaps_bruto = getattr(snapshot, "sequence_gaps", None)
        gaps = None if gaps_bruto is None else int(gaps_bruto)
        descartados_bruto = getattr(snapshot, "dropped_events", 0)
        descartados = 0 if descartados_bruto is None else int(descartados_bruto)
        detalhe = str(getattr(snapshot, "detail", "")).strip()
        if not detalhe:
            detalhe = f"BOOK {book.upper()} · AGRESSOR {qualidade.upper()}"
        timestamp_mercado = getattr(snapshot, "market_timestamp_ns", None)
        if timestamp_mercado is None:
            timestamp_mercado = getattr(snapshot, "timestamp_ns")
        latencia = getattr(snapshot, "latency_ns", None)
        return cls(
            timestamp_ns=int(timestamp_mercado),
            estado=estado,
            fonte=fonte.upper(),
            sequencia=getattr(snapshot, "last_sequence", None),
            atraso_ms=(None if latencia is None else float(latencia) / 1_000_000.0),
            trades_s=0.0,
            niveis_book=int(getattr(snapshot, "depth", getattr(snapshot, "profundidade", 0))),
            gaps=gaps,
            anomalias=anomalias,
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

        estado_maker = _estado_do_maker(snapshot)
        etapas = []
        for item in tuple(getattr(snapshot, "componentes", ())):
            score = float(getattr(item, "pontuacao", getattr(item, "score", 0.0)))
            nome = _valor_enum(getattr(item, "componente", "COMPONENTE")).upper()
            etapas.append(
                EtapaProcessamentoASG(
                    nome=nome,
                    estado=("BLOQUEADO · DESCONHECIDO" if estado_maker is EstadoASG.DESCONHECIDO
                            else "ATIVO" if abs(score) > 1e-9 else "NEUTRO"),
                    confianca=(ConfiancaASG.INDISPONIVEL
                               if estado_maker is EstadoASG.DESCONHECIDO else
                               _confianca_numerica(float(getattr(item, "confianca", 0.0)))),
                    procedencia=(ProcedenciaASG.INDISPONIVEL
                                 if estado_maker is EstadoASG.DESCONHECIDO else
                                 _procedencia_do_maker(getattr(snapshot, "procedencia", ""))),
                    detalhe=f"score {score:+.2f}".replace(".", ","),
                )
            )
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=estado_maker,
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
        if self.estado is EstadoASG.DESCONHECIDO and any(
            linha.direcao in {DirecaoASG.COMPRA, DirecaoASG.VENDA} or linha.forca != 0
            for linha in self.linhas
        ):
            raise ValueError("estado DESCONHECIDO exige matriz neutra e bloqueada")

    @classmethod
    def de_leitura(cls, leitura: object) -> MatrizASGSnapshot:
        """Adapta ``LeituraASG`` ou um ``MakerProxySnapshot`` diretamente."""

        maker = getattr(leitura, "maker", leitura)
        estado = _estado_do_maker(maker)
        if hasattr(leitura, "maker"):
            linhas = _linhas_da_matriz_asg(leitura, maker, estado)
            cobertura = 100 * float(getattr(maker, "cobertura", 0.0))
            return cls(
                timestamp_ns=int(getattr(maker, "timestamp_ns")),
                estado=estado,
                linhas=linhas,
                cobertura=f"{cobertura:.0f}%",
                modelo="MATRIZ ASG-LIKE · PROXY INDEPENDENTE · "
                + str(getattr(maker, "formula_version", "MAKER V1")),
            )

        # Compatibilidade para consumidores que ainda entregam somente o
        # MakerProxySnapshot: conserva a decomposição por evidência.
        linhas = []
        procedencia = _procedencia_do_maker(getattr(maker, "procedencia", ""))
        for item in tuple(getattr(maker, "componentes", ())):
            score = float(getattr(item, "pontuacao", getattr(item, "score", 0.0)))
            desconhecido = estado is EstadoASG.DESCONHECIDO
            linhas.append(
                LinhaMatrizASG(
                    componente=_valor_enum(getattr(item, "componente", "COMPONENTE")).upper(),
                    direcao=DirecaoASG.NEUTRA if desconhecido else _direcao_de_score(score),
                    valor="INDISPONIVEL" if desconhecido else f"{score:+.2f}".replace(".", ","),
                    forca=0.0 if desconhecido else score,
                    confianca=(ConfiancaASG.INDISPONIVEL if desconhecido else
                               _confianca_numerica(float(getattr(item, "confianca", 0.0)))),
                    procedencia=(ProcedenciaASG.INDISPONIVEL if desconhecido else procedencia),
                    evidencias=int(getattr(item, "n_evidencias", 0)),
                    detalhe=(f"cobertura {100 * float(getattr(item, 'cobertura', 0.0)):.0f}%"),
                )
            )
        cobertura = 100 * float(getattr(maker, "cobertura", 0.0))
        return cls(
            timestamp_ns=int(getattr(maker, "timestamp_ns")),
            estado=estado,
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
        if self.estado not in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}:
            if self.direcao is not DirecaoASG.AGUARDAR:
                raise ValueError(
                    f"estado {self.estado.value} exige decisao AGUARDAR, nunca confirmada"
                )
            if any(gate.resultado is ResultadoGate.PASSA for gate in self.gates):
                raise ValueError(
                    f"estado {self.estado.value} nao pode publicar gate saudavel PASSA"
                )
            if self.confianca is not ConfiancaASG.INDISPONIVEL:
                raise ValueError(
                    f"estado {self.estado.value} exige confianca INDISPONIVEL"
                )
            if any(valor != "—" for valor in (self.stop, self.alvo_1, self.alvo_2, self.alvo_3)):
                raise ValueError(
                    f"estado {self.estado.value} nao pode publicar STOP/A1/A2/A3"
                )
            if "CONFIRM" in self.titulo.upper():
                raise ValueError(
                    f"estado {self.estado.value} nao pode publicar titulo confirmado"
                )

    @classmethod
    def de_decisao(cls, snapshot: object) -> DecisaoASGSnapshot:
        """Adapta ``DecisionSnapshot``; niveis permanecem informativos."""

        leitura = getattr(snapshot, "leitura")
        maker = getattr(leitura, "maker", leitura)
        nivel = _valor_enum(getattr(snapshot, "nivel", "AGUARDAR")).upper()
        estado = _estado_do_maker(maker)
        direcao = _direcao_externa(getattr(snapshot, "direcao", None))
        if estado not in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}:
            direcao = DirecaoASG.AGUARDAR
        motivos = tuple(str(item) for item in getattr(snapshot, "motivos", ()))
        resultado = (
            ResultadoGate.PASSA
            if nivel != "AGUARDAR" and estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
            else ResultadoGate.AGUARDA
        )
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
            estado=estado,
            direcao=direcao,
            titulo=f"{nivel} {direcao.value}" if nivel != "AGUARDAR" else "SEM DECISAO",
            motivo=" · ".join(motivos) if motivos else "Aguardando evidencias suficientes",
            confianca=(
                _confianca_numerica(float(getattr(leitura, "confianca", 0.0)))
                if estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
                else ConfiancaASG.INDISPONIVEL
            ),
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

        estado_maker = _estado_do_maker(snapshot)
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
                        confianca=(ConfiancaASG.INDISPONIVEL
                                   if estado_maker is EstadoASG.DESCONHECIDO else
                                   _confianca_numerica(
                                       float(getattr(evidencia, "confianca", 0.0))
                                   )),
                        procedencia=(ProcedenciaASG.INDISPONIVEL
                                     if estado_maker is EstadoASG.DESCONHECIDO else
                                     _procedencia_do_maker(
                                         getattr(evidencia, "procedencia", "")
                                     )),
                        estado=estado_maker,
                    )
                )
        itens.sort(key=lambda item: item.timestamp_ns, reverse=True)
        total = len(itens)
        retidos = tuple(itens[: max(0, limite)])
        return cls(
            timestamp_ns=int(getattr(snapshot, "timestamp_ns")),
            estado=estado_maker,
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
    estado_operacional: EstadoASG | None = None

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
        estado = self.dados.estado if self.estado_operacional is None else self.estado_operacional
        object.__setattr__(self, "estado_operacional", estado)
        estados = {
            self.dados.estado,
            self.processamento.estado,
            self.matriz.estado,
            self.decisao.estado,
            self.evidencias.estado,
        }
        if estados != {estado}:
            nomes = ", ".join(sorted(item.value for item in estados))
            raise ValueError(f"estado operacional contraditorio: {nomes}")


class _PainelASG(PainelDenso):
    titulo = "ASG-LIKE"
    etapa = "0"
    cor_secao = tema_asg.EVIDENCIAS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.PAINEL)
        # O workspace pode ocupar uma doca estreita em 1280x720. Conteúdo
        # excedente é virtualizado pelo próprio painel; impor a altura de
        # todas as linhas como mínimo faria a janela crescer além da tela.
        self.setMinimumSize(170, 64)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._primeiro_visivel = 0

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

    def _textos_qualidade(
        self,
        confianca: ConfiancaASG,
        procedencia: ProcedenciaASG,
        completos: bool,
    ) -> tuple[str, str]:
        return (
            confianca.value if completos else confianca.value.replace("CONF ", ""),
            procedencia.value if completos else _abreviar_procedencia(procedencia),
        )

    def _vazio(self, painter: QPainter, mensagem: str) -> None:
        painter.setFont(tokens.fonte_ui(12))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, ALTURA_CABECALHO, self.width() - 2 * MARGEM,
                  max(0, self.faixa_rodape().top() - ALTURA_CABECALHO)),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "○ " + mensagem,
        )

    def total_itens(self) -> int:
        return 0

    def capacidade_pagina(self) -> int:
        return 0

    @property
    def primeiro_visivel(self) -> int:
        self._limitar_primeiro()
        return self._primeiro_visivel

    def intervalo_visivel(self) -> tuple[int, int]:
        total = self.total_itens()
        capacidade = self.capacidade_pagina()
        self._limitar_primeiro()
        fim = min(total, self._primeiro_visivel + capacidade)
        return self._primeiro_visivel, fim

    def indices_visiveis(self) -> range:
        primeiro, fim = self.intervalo_visivel()
        return range(primeiro, fim)

    def faixa_rodape(self) -> QRect:
        return QRect(0, max(ALTURA_CABECALHO, self.height() - ALTURA_RODAPE),
                     self.width(), ALTURA_RODAPE)

    def texto_visibilidade(self) -> str:
        total = self.total_itens()
        primeiro, fim = self.intervalo_visivel()
        if not total or fim <= primeiro:
            return f"VISIVEIS 0/{total}"
        return f"VISIVEIS {fim - primeiro}/{total} · ITENS {primeiro + 1}-{fim}"

    def _desenhar_rodape(self, painter: QPainter, texto_esquerda: str = "") -> None:
        rect = self.faixa_rodape()
        painter.fillRect(rect, tema_asg.CABECALHO)
        painter.setPen(tema_asg.BORDA)
        painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_SECONDARY)
        interno = rect.adjusted(MARGEM, 0, -MARGEM, 0)
        if texto_esquerda:
            painter.drawText(interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             texto_esquerda)
        painter.drawText(interno, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         self.texto_visibilidade())

    def _limitar_primeiro(self) -> None:
        maximo = max(0, self.total_itens() - max(1, self.capacidade_pagina()))
        self._primeiro_visivel = min(maximo, max(0, self._primeiro_visivel))

    def _mover_para(self, primeiro: int) -> None:
        anterior = self._primeiro_visivel
        self._primeiro_visivel = primeiro
        self._limitar_primeiro()
        if self._primeiro_visivel != anterior:
            self.marcar_tudo_sujo()

    def keyPressEvent(self, evento) -> None:  # noqa: N802
        tecla = evento.key()
        pagina = max(1, self.capacidade_pagina())
        if tecla == Qt.Key.Key_Up:
            self._mover_para(self._primeiro_visivel - 1)
        elif tecla == Qt.Key.Key_Down:
            self._mover_para(self._primeiro_visivel + 1)
        elif tecla == Qt.Key.Key_PageUp:
            self._mover_para(self._primeiro_visivel - pagina)
        elif tecla == Qt.Key.Key_PageDown:
            self._mover_para(self._primeiro_visivel + pagina)
        elif tecla == Qt.Key.Key_Home:
            self._mover_para(0)
        elif tecla == Qt.Key.Key_End:
            self._mover_para(self.total_itens())
        else:
            super().keyPressEvent(evento)
            return
        evento.accept()

    def wheelEvent(self, evento) -> None:  # noqa: N802
        delta = evento.angleDelta().y()
        if delta:
            passos = max(1, abs(delta) // 120) * 3
            self._mover_para(self._primeiro_visivel + (-passos if delta > 0 else passos))
            evento.accept()
            return
        super().wheelEvent(evento)

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self._limitar_primeiro()


class PainelDadosASG(_PainelASG):
    titulo = "DADOS"
    etapa = "1"
    cor_secao = tema_asg.DADOS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = DadosASGSnapshot(0)
        self.setMinimumHeight(80)

    @property
    def snapshot(self) -> DadosASGSnapshot:
        return self._snapshot

    def aplicar(self, snapshot: DadosASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        self._limitar_primeiro()
        if mudou:
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
            MetricaASG(
                "GAPS",
                "INDISPONIVEL" if s.gaps is None else formato.formatar_inteiro(s.gaps),
            ),
            MetricaASG("ANOMALIAS", formato.formatar_inteiro(s.anomalias)),
            MetricaASG("DESCARTADOS", formato.formatar_inteiro(s.descartados)),
        )

    def total_itens(self) -> int:
        return len(self.metricas())

    def capacidade_pagina(self) -> int:
        altura = max(0, self.faixa_rodape().top() - (ALTURA_CABECALHO + 46))
        return (altura // 34) * self.n_colunas()

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        colunas = self.n_colunas()
        largura = max(1, (self.width() - 2 * MARGEM - (colunas - 1) * VAO) // colunas)
        y = ALTURA_CABECALHO + 46
        resultado = []
        for posicao, indice in enumerate(self.indices_visiveis()):
            coluna, linha = posicao % colunas, posicao // colunas
            rect = QRect(MARGEM + coluna * (largura + VAO), y + linha * 34, largura, 30)
            if rect.bottom() < self.faixa_rodape().top():
                resultado.append((indice, rect))
        return tuple(resultado)

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        detalhe = s.fonte if self.width() < 420 else s.detalhe
        metricas = self.metricas()
        textos = [rotulo_estado(s.estado), detalhe]
        textos.extend(self._textos_qualidade(
            s.confianca, s.procedencia, completos=True
        ))
        if self.width() >= 420:
            textos.append(s.fonte)
        textos.extend(
            f"{metricas[i].nome} {metricas[i].valor} {metricas[i].unidade}".strip()
            for i, _ in self.retangulos_visiveis()
        )
        textos.append(self.texto_visibilidade())
        return tuple(textos)

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
                              completos=True)
        metricas = self.metricas()
        for i, rect in self.retangulos_visiveis():
            metrica = metricas[i]
            painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
            painter.setPen(tema_asg.BORDA)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_rotulo(9))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(rect.adjusted(6, 1, -6, -15),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             metrica.nome)
            painter.setFont(tokens.fonte_numero(13, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_PRIMARY)
            valor = f"{metrica.valor} {metrica.unidade}".rstrip()
            painter.drawText(rect.adjusted(6, 13, -6, -1),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, valor)
        self._desenhar_rodape(painter)


class PainelProcessamentoASG(_PainelASG):
    titulo = "PROCESSAMENTO"
    etapa = "2"
    cor_secao = tema_asg.PROCESSAMENTO

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = ProcessamentoASGSnapshot(0)
        self.setMinimumHeight(80)

    def aplicar(self, snapshot: ProcessamentoASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        self._limitar_primeiro()
        if mudou:
            self.marcar_tudo_sujo()

    def total_itens(self) -> int:
        return len(self._snapshot.etapas)

    def altura_item(self) -> int:
        return 38 if self.width() < 500 else ALTURA_LINHA

    def capacidade_pagina(self) -> int:
        return max(0, self.faixa_rodape().top() - ALTURA_CABECALHO) // self.altura_item()

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        altura = self.altura_item()
        return tuple(
            (indice, QRect(0, ALTURA_CABECALHO + posicao * altura, self.width(), altura))
            for posicao, indice in enumerate(self.indices_visiveis())
        )

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), f"FILA {s.fila}", f"PERDAS {s.perdas}",
                  self.texto_visibilidade()]
        if self.width() >= 420:
            textos.append(f"v{s.versao}")
        for indice, _ in self.retangulos_visiveis():
            etapa = s.etapas[indice]
            textos.extend((etapa.nome, _simbolo_estado_livre(etapa.estado)))
            textos.extend(self._textos_qualidade(
                etapa.confianca, etapa.procedencia, completos=True
            ))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, f"v{s.versao}")
        if not s.etapas:
            self._vazio(painter, "PROCESSAMENTO NAO INICIADO")
            self._desenhar_rodape(painter, f"FILA {s.fila} · PERDAS {s.perdas}")
            return

        estreito = self.width() < 500
        for indice, linha in self.retangulos_visiveis():
            etapa = s.etapas[indice]
            y = linha.y()
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
            limite_estado = self.width() - (196 if not estreito else MARGEM)
            painter.drawText(QRect(0, y, limite_estado, 22),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             _simbolo_estado_livre(etapa.estado))
            if estreito:
                self._chips_qualidade(painter, 36, y + 20, etapa.confianca,
                                      etapa.procedencia, completos=True)
            else:
                self._chips_qualidade(painter, self.width() - 190, y + 4,
                                      etapa.confianca, etapa.procedencia, completos=True)
        self._desenhar_rodape(painter, f"FILA {s.fila} · PERDAS {s.perdas}")


class PainelMatrizASG(_PainelASG):
    titulo = "MATRIZ ASG-LIKE"
    etapa = "3"
    cor_secao = tema_asg.MATRIZ

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR) -> None:
        super().__init__(parent)
        self.paleta = paleta
        self._snapshot = MatrizASGSnapshot(0)
        self.setMinimumHeight(80)

    def aplicar(self, snapshot: MatrizASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        self._limitar_primeiro()
        if mudou:
            self.marcar_tudo_sujo()

    def modo_tabela(self) -> bool:
        return self.width() >= 640

    def total_itens(self) -> int:
        return len(self._snapshot.linhas)

    def topo_itens(self) -> int:
        return ALTURA_CABECALHO + ALTURA_SELO + (20 if self.modo_tabela() else VAO)

    def altura_item(self) -> int:
        return 28 if self.modo_tabela() else 48

    def capacidade_pagina(self) -> int:
        return max(0, self.faixa_rodape().top() - self.topo_itens()) // self.altura_item()

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        topo = self.topo_itens()
        altura = self.altura_item()
        if self.modo_tabela():
            return tuple(
                (indice, QRect(0, topo + posicao * altura, self.width(), altura))
                for posicao, indice in enumerate(self.indices_visiveis())
            )
        return tuple(
            (indice, QRect(MARGEM, topo + posicao * altura,
                           self.width() - 2 * MARGEM, 44))
            for posicao, indice in enumerate(self.indices_visiveis())
        )

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), "PROXY INDEPENDENTE", self.texto_visibilidade()]
        if self.width() >= 420:
            textos.append(f"COBERTURA {s.cobertura}")
        for indice, _ in self.retangulos_visiveis():
            linha = s.linhas[indice]
            textos.extend((linha.componente, rotulo_direcao(linha.direcao), linha.valor))
            textos.extend(self._textos_qualidade(
                linha.confianca, linha.procedencia, completos=True
            ))
            textos.append(f"EVID {linha.evidencias}")
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
                      max(0, self.faixa_rodape().top() - selo.bottom())),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "○ SEM LEITURA · MATRIZ AGUARDANDO EVIDENCIAS",
            )
            self._desenhar_rodape(painter)
            return
        if self.modo_tabela():
            self._desenhar_tabela(painter)
        else:
            self._desenhar_cartoes(painter)
        self._desenhar_rodape(painter)

    def _desenhar_tabela(self, painter: QPainter) -> None:
        y = ALTURA_CABECALHO + ALTURA_SELO
        cab = QRect(0, y, self.width(), 20)
        painter.fillRect(cab, tema_asg.FUNDO_NEUTRO)
        colunas = self._colunas()
        painter.setFont(tokens.fonte_rotulo(9))
        painter.setPen(tokens.TEXT_SECONDARY)
        for nome, rect in zip(("COMPONENTE", "LEITURA", "FORCA", "QUALIDADE", "EVID"), colunas):
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)
        for indice, rect in self.retangulos_visiveis():
            linha = self._snapshot.linhas[indice]
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
                                  linha.confianca, linha.procedencia, completos=True)
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
        for indice, rect in self.retangulos_visiveis():
            linha = self._snapshot.linhas[indice]
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
            self._chips_qualidade(painter, max(rect.x() + 100, rect.right() - 190), rect.y() + 4,
                                  linha.confianca, linha.procedencia, completos=True)
            painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(rect.adjusted(6, 22, -6, -2),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"EVID {linha.evidencias}")

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
        self.setMinimumHeight(80)

    def aplicar(self, snapshot: DecisaoASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        self._limitar_primeiro()
        if mudou:
            self.marcar_tudo_sujo()

    def total_itens(self) -> int:
        return len(self._snapshot.gates)

    def faixa_rodape(self) -> QRect:
        altura = 38
        return QRect(0, max(ALTURA_CABECALHO, self.height() - altura), self.width(), altura)

    def topo_gates(self) -> int:
        return 136

    def capacidade_pagina(self) -> int:
        return max(0, self.faixa_rodape().top() - self.topo_gates()) // ALTURA_LINHA

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        return tuple(
            (indice, QRect(0, self.topo_gates() + posicao * ALTURA_LINHA,
                           self.width(), ALTURA_LINHA))
            for posicao, indice in enumerate(self.indices_visiveis())
        )

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), "CONSULTIVO · SEM ENVIO DE ORDENS",
                  rotulo_direcao(s.direcao), s.titulo, s.motivo,
                  f"STOP {s.stop}", f"A1 {s.alvo_1}", f"A2 {s.alvo_2}", f"A3 {s.alvo_3}",
                  self.texto_visibilidade()]
        textos.extend(self._textos_qualidade(s.confianca, s.procedencia, completos=True))
        for indice, _ in self.retangulos_visiveis():
            gate = s.gates[indice]
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
        self._chips_qualidade(painter, max(MARGEM, self.width() - 200),
                              veredito.y() + 4, s.confianca, s.procedencia, completos=True)

        y = veredito.bottom() + VAO
        painter.setFont(tokens.fonte_ui(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(MARGEM, y, self.width() - 2 * MARGEM, 30),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter |
                         Qt.TextFlag.TextWordWrap, s.motivo)
        for indice, rect_gate in self.retangulos_visiveis():
            gate = s.gates[indice]
            y = rect_gate.y()
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
        self._desenhar_rodape_decisao(painter)

    def _desenhar_rodape_decisao(self, painter: QPainter) -> None:
        s = self._snapshot
        rect = self.faixa_rodape()
        painter.fillRect(rect, tema_asg.CABECALHO)
        painter.setPen(tema_asg.BORDA)
        painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(QRect(MARGEM, rect.y(), self.width() - 2 * MARGEM, 19),
                         Qt.AlignmentFlag.AlignCenter,
                         f"STOP {s.stop} · A1 {s.alvo_1} · A2 {s.alvo_2} · A3 {s.alvo_3}")
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(MARGEM, rect.y() + 19, self.width() - 2 * MARGEM, 18),
                         Qt.AlignmentFlag.AlignCenter, self.texto_visibilidade())


class PainelEvidenciasASG(_PainelASG):
    titulo = "TRILHA DE EVIDENCIAS"
    etapa = "5"
    cor_secao = tema_asg.EVIDENCIAS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snapshot = TrilhaEvidenciasASGSnapshot(0)
        self.setMinimumHeight(80)

    def aplicar(self, snapshot: TrilhaEvidenciasASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        self._limitar_primeiro()
        if mudou:
            self.marcar_tudo_sujo()

    @property
    def n_linhas(self) -> int:
        return self.capacidade_pagina()

    def total_itens(self) -> int:
        return len(self._snapshot.itens)

    def capacidade_pagina(self) -> int:
        return max(0, self.faixa_rodape().top() - ALTURA_CABECALHO) // ALTURA_LINHA

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        return tuple(
            (indice, QRect(0, ALTURA_CABECALHO + posicao * ALTURA_LINHA,
                           self.width(), ALTURA_LINHA))
            for posicao, indice in enumerate(self.indices_visiveis())
        )

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), self.texto_visibilidade()]
        if self.width() >= 420:
            textos.append(f"{s.retidos}/{s.total} RETIDOS")
        for indice, _ in self.retangulos_visiveis():
            item = s.itens[indice]
            textos.extend((formato.formatar_hora_ns(item.timestamp_ns), item.origem,
                           _simbolo_estado_livre(item.evento), item.leitura))
            if self.width() >= 640:
                textos.extend(self._textos_qualidade(
                    item.confianca, item.procedencia, completos=True
                ))
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, f"{s.retidos}/{s.total} RETIDOS")
        if not s.itens:
            self._vazio(painter, "SEM EVIDENCIAS RETIDAS")
            self._desenhar_rodape(painter)
            return
        for indice, linha in self.retangulos_visiveis():
            item = s.itens[indice]
            y = linha.y()
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
            largura = max(20, self.width() - x - (224 if self.width() >= 640 else 8))
            texto = f"{_simbolo_estado_livre(item.evento)} · {item.leitura}"
            painter.drawText(QRect(x, y, largura, ALTURA_LINHA),
                             Qt.AlignmentFlag.AlignVCenter, texto)
            if self.width() >= 640:
                self._chips_qualidade(painter, self.width() - 220, y + 4,
                                      item.confianca, item.procedencia, completos=True)
        self._desenhar_rodape(painter)


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

        if not isinstance(snapshot, WorkspaceASGSnapshot):
            raise TypeError("WorkspaceASG.aplicar exige WorkspaceASGSnapshot tipado")
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


def _campo(objeto: object, nome: str, padrao: object = None) -> object:
    if isinstance(objeto, Mapping):
        return objeto.get(nome, padrao)
    return getattr(objeto, nome, padrao)


def _direcao_textual(valor: object) -> DirecaoASG:
    texto = _valor_enum(valor).upper()
    if texto in {"BUY", "COMPRA", "COMPRADOR", "ACIMA"}:
        return DirecaoASG.COMPRA
    if texto in {"SELL", "VENDA", "VENDEDOR", "ABAIXO"}:
        return DirecaoASG.VENDA
    return DirecaoASG.NEUTRA


def _direcao_numero(valor: int | float | None) -> DirecaoASG:
    if valor is None:
        return DirecaoASG.NEUTRA
    return _direcao_de_score(float(valor))


def _forca_limitada(valor: float) -> float:
    return max(-1.0, min(1.0, valor))


def _linhas_da_matriz_asg(
    leitura: object, maker: object, estado: EstadoASG
) -> tuple[LinhaMatrizASG, ...]:
    """Macro, Micro, Linha Azul, Regime, MakerProxy e Velocímetro."""

    macro_micro = _campo(leitura, "macro", {})
    medida_macro = _campo(macro_micro, "macro", {})
    medida_micro = _campo(_campo(leitura, "micro", {}), "micro", {})
    valor_macro = _campo(medida_macro, "valor")
    valor_micro = _campo(medida_micro, "valor")
    linha_azul = _campo(leitura, "linha_azul", {})
    regime = _campo(leitura, "regime", {})
    velocimetro = _campo(leitura, "velocimetro", {})

    def contexto(nome: str, valor: object) -> LinhaMatrizASG:
        numero = int(valor) if isinstance(valor, int) and not isinstance(valor, bool) else None
        return LinhaMatrizASG(
            componente=nome,
            direcao=_direcao_numero(numero),
            valor="SEM DADOS" if numero is None else f"{numero:+d}",
            forca=0.0 if numero is None else _forca_limitada(numero / max(abs(numero), 1)),
            confianca=(ConfiancaASG.INDISPONIVEL if numero is None else ConfiancaASG.MEDIA),
            procedencia=(ProcedenciaASG.INDISPONIVEL if numero is None else ProcedenciaASG.DERIVADO),
            detalhe="ESCALA PROPRIA · NAO COMPARAR MAGNITUDES",
        )

    fracao = _campo(linha_azul, "fracao_compradora")
    nivel = _campo(linha_azul, "nivel")
    lado_linha = _campo(linha_azul, "lado", "SEM_LINHA")
    regime_nome = _campo(regime, "regime", "INDEFINIDO")
    velocidade_estado = _campo(velocimetro, "estado", "SEM_DADOS")
    velocidade_lado = _campo(velocimetro, "sentido")
    magnitude = _campo(velocimetro, "magnitude_relativa")
    maker_score = float(getattr(maker, "pontuacao", getattr(maker, "score", 0.0)))
    maker_conf = float(getattr(maker, "confianca", getattr(maker, "confidence", 0.0)))

    linhas = [
        contexto("MACRO", valor_macro),
        contexto("MICRO", valor_micro),
        LinhaMatrizASG(
            componente="LINHA AZUL",
            direcao=_direcao_textual(lado_linha),
            valor="SEM LINHA" if nivel is None else f"{int(nivel)}t",
            forca=(
                0.0
                if not isinstance(fracao, (int, float)) or isinstance(fracao, bool)
                else _forca_limitada((float(fracao) - 0.5) * 2.0)
            ),
            confianca=(ConfiancaASG.INDISPONIVEL if nivel is None else ConfiancaASG.BAIXA),
            procedencia=(ProcedenciaASG.INDISPONIVEL if nivel is None else ProcedenciaASG.INFERIDO),
            detalhe=_valor_enum(lado_linha).upper(),
        ),
        LinhaMatrizASG(
            componente="REGIME",
            direcao=_direcao_textual(regime_nome),
            valor=_valor_enum(regime_nome).upper(),
            forca=(1.0 if _direcao_textual(regime_nome) is DirecaoASG.COMPRA
                   else -1.0 if _direcao_textual(regime_nome) is DirecaoASG.VENDA else 0.0),
            confianca=ConfiancaASG.MEDIA,
            procedencia=ProcedenciaASG.DERIVADO,
            detalhe="ESTRUTURA DO DIA",
        ),
        LinhaMatrizASG(
            componente="MAKERPROXY",
            direcao=_direcao_de_score(maker_score),
            valor=f"{maker_score * 100:+.0f}%",
            forca=maker_score,
            confianca=_confianca_numerica(maker_conf),
            procedencia=_procedencia_do_maker(getattr(maker, "procedencia", "")),
            evidencias=len(tuple(getattr(maker, "evidence", ()))),
            detalhe=f"PERSIST {int(getattr(maker, 'persistence_ns', 0)) / 1e9:.1f}s",
        ),
        LinhaMatrizASG(
            componente="VELOCIMETRO",
            direcao=_direcao_textual(velocidade_lado),
            valor=_valor_enum(velocidade_estado).upper(),
            forca=(
                0.0 if not isinstance(magnitude, (int, float)) or isinstance(magnitude, bool)
                else _forca_limitada(float(magnitude))
                * (-1.0 if _direcao_textual(velocidade_lado) is DirecaoASG.VENDA else 1.0)
            ),
            confianca=(ConfiancaASG.INDISPONIVEL if velocidade_lado is None else ConfiancaASG.MEDIA),
            procedencia=ProcedenciaASG.DERIVADO,
            detalhe="MAGNITUDE + MANUTENCAO",
        ),
    ]
    if estado is EstadoASG.DESCONHECIDO:
        linhas = [
            dataclass_replace(
                linha,
                direcao=DirecaoASG.NEUTRA,
                valor="INDISPONIVEL",
                forca=0.0,
                confianca=ConfiancaASG.INDISPONIVEL,
                procedencia=ProcedenciaASG.INDISPONIVEL,
            )
            for linha in linhas
        ]
    return tuple(linhas)


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
    if estado in {"stopped", "connecting", "closed", ""}:
        return EstadoASG.AGUARDANDO
    if estado == "connected" and book == "none":
        return EstadoASG.SEM_BOOK
    if estado == "connected" and book in {"mbp", "mbo"}:
        return EstadoASG.AO_VIVO
    return EstadoASG.DESCONHECIDO


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
    if texto in {"SEM_DADOS", "AGUARDANDO"}:
        return EstadoASG.AGUARDANDO
    if texto == "SEM_BOOK":
        return EstadoASG.SEM_BOOK
    if texto == "AJUSTANDO":
        return EstadoASG.AGUARDANDO
    if texto in {"NEUTRO", "DIVERGENTE", "COMPRADOR", "VENDEDOR"}:
        return EstadoASG.AO_VIVO
    return EstadoASG.DESCONHECIDO


def _chave_visual(snapshot: object) -> tuple[tuple[str, object], ...]:
    """Conteudo pintado do snapshot, sem o carimbo do quadro.

    ``timestamp_ns`` do snapshot agrega coerencia entre produtores, mas nao e
    desenhado em nenhum cabecalho. Evidencias aninhadas continuam carregando
    seus proprios timestamps, que sao texto visivel e portanto fazem parte da
    igualdade normal da tupla ``itens``.
    """

    return tuple(
        (campo.name, getattr(snapshot, campo.name))
        for campo in fields(snapshot)
        if campo.name != "timestamp_ns"
    )


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
