"""Componentes QPainter do workspace ASG-like.

Esta e deliberadamente uma fronteira visual. Os paineis nao assinam o
barramento, nao leem sessao e nao inferem estado: recebem snapshots imutaveis
prontos uma vez por quadro. Assim a janela central pode integra-los depois sem
misturar thread de dados, regra de negocio e pintura.

A superficie inteira e consultiva. ``PainelDecisaoASG`` pinta essa ressalva
no proprio quadro e nao oferece sinal, callback ou API de envio de ordem.
"""

from __future__ import annotations

import math
import os
import time
import statistics
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace as dataclass_replace
from enum import Enum, unique

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

from fluxopro.analytics.candle_temporal import CandleTemporal, ConfigCandleTemporal
from fluxopro.analytics.renko import ConfigRenko, FaseRenko, Renko
from fluxopro.analytics.analise_claude import MotorAnaliseClaude, ligado_por_ambiente
from fluxopro.analytics.dominancia import MotorDominancia
from fluxopro.analytics.suporte_resistencia import MotorSuporteResistencia
from fluxopro.asg.sinal_ultra import (
    ConfigSinalUltra,
    DirecaoUltra,
    EntradaSinalUltra,
    MotorSinalUltra,
)
from fluxopro.audio.voz import (
    ConfigVoz,
    LocutorASG,
    texto_para_perda_de_alinhamento,
    texto_para_realinhamento,
    texto_para_transicao_ultra,
)
from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, PriceGrid, Trade, WDO_GRID
from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.paineis.bookmap import PainelBookmap
from fluxopro.ui.paineis.cockpit import PainelCockpit
from fluxopro.ui.paineis.dom import PainelDOM
from fluxopro.ui.paineis.grafico import PainelGrafico, PainelMiniTape
# Contrato de composicao da superficie NEXO. Somente o pacote raiz entra aqui:
# os modulos de regiao sao importados sob demanda no primeiro quadro, o que
# desfaz o ciclo (regiao -> asg -> nexo) sem exportar nada novo deste modulo.
from fluxopro.ui.paineis import nexo
from fluxopro.ui.paineis.placar_visual import (
    PainelMarcaOperador,
    PainelPlacarVisual,
    PainelPressaoMercado,
)
from fluxopro.ui.paineis.tape import PainelTape
from fluxopro.ui.ponte import Instantaneo

def _direcao_ultra_de(direcao: "DirecaoASG") -> DirecaoUltra:
    """Ponte entre o vocabulario de 4 estados da UI (DirecaoASG) e o de 3
    estados do motor de Sinal Ultra (DirecaoUltra) — AGUARDAR e NEUTRA viram
    igualmente NENHUMA la, porque nenhum dos dois e uma direcao confirmada."""

    if direcao is DirecaoASG.COMPRA:
        return DirecaoUltra.COMPRA
    if direcao is DirecaoASG.VENDA:
        return DirecaoUltra.VENDA
    return DirecaoUltra.NENHUMA


def _agressor_de_int(valor: int) -> AgressorSide:
    """Mesma convenção já usada nesta classe: >0 comprador, <0 vendedor."""

    if valor > 0:
        return AgressorSide.BUY
    if valor < 0:
        return AgressorSide.SELL
    return AgressorSide.UNKNOWN


# Voz do Sinal Ultra (fluxopro/audio/voz.py) — NUNCA liga sozinha. Montar um
# painel (inclusive em teste) nao pode ter como efeito colateral abrir uma
# thread de audio e falar alto; o operador liga explicitamente definindo
# FLUXOPRO_VOZ=1 no ambiente antes de abrir o painel.
_VOZ_ATIVA_POR_PADRAO = os.environ.get("FLUXOPRO_VOZ", "").strip().lower() in {"1", "true", "sim"}

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


def cor_estado(estado: EstadoASG) -> QColor:
    """Cor do estado para strips globais e paineis usarem a mesma fonte."""

    return _COR_ESTADO[estado]


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


def _cor_nexo_direcao(direcao: DirecaoASG) -> QColor:
    """Eixo neon da superficie NEXO, separado da paleta tecnica legada."""

    if direcao is DirecaoASG.COMPRA:
        return tema_asg.NEXO_VERDE
    if direcao is DirecaoASG.VENDA:
        return tema_asg.NEXO_ROSA
    if direcao is DirecaoASG.AGUARDAR:
        return tema_asg.NEXO_AMARELO
    return tema_asg.NEXO_CIANO


def _cor_nexo_estado(estado: EstadoASG) -> QColor:
    if estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}:
        return tema_asg.NEXO_VERDE
    if estado in {EstadoASG.ATRASADO, EstadoASG.AGUARDANDO, EstadoASG.SEM_BOOK}:
        return tema_asg.NEXO_AMARELO
    if estado is EstadoASG.ERRO:
        return tema_asg.NEXO_ROSA
    return tema_asg.NEXO_CIANO


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
class NivelBrutoASG:
    """Um nivel do livro, copiado para o quadro consultivo ASG."""

    preco: int
    quantidade: int
    ordens: int


@dataclass(frozen=True, slots=True)
class NegocioBrutoASG:
    """Uma impressao do tape que pertence ao mesmo quadro do DOM."""

    timestamp_ns: int
    preco: int
    quantidade: int
    agressor: int


@dataclass(frozen=True, slots=True)
class ContextoBrutoASGSnapshot:
    """DOM, tape e liquidez tipo bookmap de um unico retrato de UI.

    Nao e um segundo consumidor da ponte: a janela cria esta estrutura a
    partir do ``Instantaneo`` que acabou de distribuir aos paineis historicos.
    O carimbo e o do ``WorkspaceASGSnapshot`` para impedir que a superficie
    ASG misture um retrato bruto de um quadro com uma decisao de outro.
    """

    timestamp_ns: int
    estado: EstadoASG = EstadoASG.AGUARDANDO
    bids: tuple[NivelBrutoASG, ...] = ()
    asks: tuple[NivelBrutoASG, ...] = ()
    negocios: tuple[NegocioBrutoASG, ...] = ()
    ultimo_preco: int | None = None
    detalhe: str = "AGUARDANDO RETRATO BRUTO"

    def __post_init__(self) -> None:
        object.__setattr__(self, "bids", tuple(self.bids))
        object.__setattr__(self, "asks", tuple(self.asks))
        object.__setattr__(self, "negocios", tuple(self.negocios))

    @classmethod
    def de_instantaneo(
        cls, instantaneo: object, timestamp_ns: int, estado: EstadoASG
    ) -> ContextoBrutoASGSnapshot:
        """Copia somente os campos imutaveis que o painel efetivamente le."""

        livro = getattr(instantaneo, "livro", None)

        def niveis(nome: str) -> tuple[NivelBrutoASG, ...]:
            return tuple(
                NivelBrutoASG(
                    int(getattr(nivel, "price")),
                    int(getattr(nivel, "qty")),
                    int(getattr(nivel, "n_orders", 0)),
                )
                for nivel in tuple(getattr(livro, nome, ()) if livro is not None else ())[:8]
            )

        negocios = tuple(
            NegocioBrutoASG(
                int(getattr(item, "timestamp_ns")),
                int(getattr(item, "price")),
                int(getattr(item, "qty")),
                int(getattr(item, "agressor", 0)),
            )
            for item in tuple(getattr(instantaneo, "novos_trades", ()))[:10]
        )
        return cls(
            timestamp_ns=timestamp_ns,
            estado=estado,
            bids=niveis("bids"),
            asks=niveis("asks"),
            negocios=negocios,
            ultimo_preco=getattr(instantaneo, "ultimo_preco", None),
            detalhe=(
                "DOM · TAPE · BOOKMAP NO MESMO QUADRO"
                if livro is not None else "SEM SNAPSHOT DE BOOK NESTE QUADRO"
            ),
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
    contexto_bruto: ContextoBrutoASGSnapshot | None = None

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
        contexto = self.contexto_bruto
        if contexto is not None and contexto.timestamp_ns != self.timestamp_ns:
            raise ValueError("contexto bruto precisa pertencer ao mesmo quadro ASG")
        if contexto is not None and contexto.estado is not estado:
            raise ValueError("contexto bruto precisa declarar o estado operacional do quadro")


class _PainelASG(PainelDenso):
    titulo = "ASG-LIKE"
    etapa = "0"
    cor_secao = tema_asg.EVIDENCIAS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tema_asg.PAINEL)
        # A troca de docas resolve primeiro a geometria antiga e so depois a
        # nova largura. Um minimo por filho faria o modo estreito transitorio
        # somar cinco alturas e redimensionar a janela antes de o composto
        # ganhar a area inteira. O conteudo tem virtualizacao propria, logo o
        # layout pode ignorar o hint sem perder estado nem escrever fora.
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        self.setMinimumHeight(0)

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
        self.setMinimumHeight(0)

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
    titulo = "MATRIZ NEXO"
    etapa = "3"
    cor_secao = tema_asg.MATRIZ

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR,
                 grid: object | None = None) -> None:
        super().__init__(parent)
        self.paleta = paleta
        self._snapshot = MatrizASGSnapshot(0)
        self.setMinimumHeight(0)

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
        # A matriz é uma leitura atômica de seis componentes. Em 1280×720 a
        # área útil é menor, mas ainda precisa mostrar a matriz inteira; a
        # redução é só de espaçamento vertical, não remove linhas nem cria
        # paginação silenciosa.
        if self.modo_tabela():
            return 24 if self.height() < 270 else 28
        return 48

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
                 paleta: tokens.Paleta = tokens.PALETA_COR,
                 grid: object | None = None) -> None:
        super().__init__(parent)
        self.paleta = paleta
        self._snapshot = DecisaoASGSnapshot(0)
        self.setMinimumHeight(0)

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
        textos.extend(("LEITURA ATUAL", "CONFIANCA", "PLANO CONSULTIVO"))
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
        self._desenhar_resumo_operacional(
            painter,
            self.topo_gates() + len(self.retangulos_visiveis()) * ALTURA_LINHA,
        )
        self._desenhar_rodape_decisao(painter)

    def _desenhar_resumo_operacional(self, painter: QPainter, y_inicial: int) -> None:
        """Preenche a área livre com contexto, nunca com decoração fictícia.

        A coluna de decisão pode ser alta. Os três blocos derivam somente do
        snapshot imutável: não criam sinal, previsão ou envio de ordem.
        """

        s = self._snapshot
        rodape = self.faixa_rodape()
        area = QRect(MARGEM, y_inicial + VAO, self.width() - 2 * MARGEM,
                     rodape.top() - y_inicial - 2 * VAO)
        if area.height() < 58 or area.width() < 100:
            return
        painter.fillRect(area, tema_asg.FUNDO_NEUTRO)
        painter.setPen(tema_asg.BORDA)
        painter.drawRect(area.adjusted(0, 0, -1, -1))
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(area.adjusted(7, 3, -7, -area.height() + 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "LEITURA ATUAL · RASTRO CONSULTIVO")

        linhas = (
            ("LEITURA", rotulo_direcao(s.direcao), _cor_direcao(s.direcao, self.paleta)),
            ("CONFIANCA", s.confianca.value, _COR_CONFIANCA[s.confianca]),
            ("PLANO", "BLOQUEADO" if s.direcao is DirecaoASG.AGUARDAR else "INFORMATIVO",
             tokens.ALERT if s.direcao is DirecaoASG.AGUARDAR else tema_asg.DECISAO),
        )
        y = area.y() + 22
        # O bloco é deliberadamente alto: em telas largas a decisão precisa
        # continuar sendo o segundo ponto de leitura, não deixar uma coluna
        # vazia ao lado da matriz. Cada faixa é um fato do snapshot.
        altura = max(18, (area.bottom() - y - 4) // len(linhas))
        for nome, valor, cor in linhas:
            if y + altura > area.bottom():
                break
            painter.setPen(tema_asg.BORDA)
            painter.drawLine(area.x() + 5, y + altura - 1, area.right() - 5, y + altura - 1)
            painter.setFont(tokens.fonte_rotulo(8))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(QRect(area.x() + 7, y + 4, area.width() - 14, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, nome)
            painter.setFont(tokens.fonte_ui(min(18, max(9, altura // 4)), QFont.Weight.DemiBold))
            painter.setPen(cor)
            painter.drawText(QRect(area.x() + 7, y + 16, area.width() - 14, altura - 19),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             valor)
            y += altura

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
        self.setMinimumHeight(0)

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


class PainelContextoBrutoASG(_PainelASG):
    """Leitura bruta compacta para conferir a conclusao ASG sem trocar tela."""

    titulo = "CONTEXTO BRUTO"
    etapa = "0"
    cor_secao = tema_asg.DADOS

    def __init__(self, parent: QWidget | None = None,
                 grid: object | None = None) -> None:
        super().__init__(parent)
        self.grid = grid
        self._snapshot = ContextoBrutoASGSnapshot(0)
        self.setMinimumHeight(0)

    def aplicar(self, snapshot: ContextoBrutoASGSnapshot) -> None:
        mudou = _chave_visual(snapshot) != _chave_visual(self._snapshot)
        self._snapshot = snapshot
        if mudou:
            self.marcar_tudo_sujo()

    def total_itens(self) -> int:
        return len(self._snapshot.bids) + len(self._snapshot.asks) + len(self._snapshot.negocios)

    def capacidade_pagina(self) -> int:
        return self.total_itens()

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        # Este painel pinta tres faixas proporcionais, nao uma lista
        # virtualizada. As caixas sao derivadas no mesmo ``desenhar`` e nunca
        # excedem o rodape; nao ha linhas indexadas para expor ao navegador.
        return ()

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        textos = [rotulo_estado(s.estado), s.detalhe, "DOM", "TAPE", "BOOKMAP · LIQUIDEZ"]
        textos.extend(
            f"BID {nivel.preco} {nivel.quantidade}" for nivel in s.bids
        )
        textos.extend(
            f"ASK {nivel.preco} {nivel.quantidade}" for nivel in s.asks
        )
        textos.extend(
            f"TAPE {negocio.preco} {negocio.quantidade}" for negocio in s.negocios
        )
        return tuple(textos)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        s = self._snapshot
        self._cabecalho(painter, s.estado, "SINCRONIZADO")
        corpo = QRect(MARGEM, ALTURA_CABECALHO + 4, self.width() - 2 * MARGEM,
                      self.faixa_rodape().top() - ALTURA_CABECALHO - 8)
        if corpo.height() <= 28:
            return
        if self.width() >= 560:
            largura = (corpo.width() - 2 * VAO) // 3
            self._desenhar_dom(painter, QRect(corpo.x(), corpo.y(), largura, corpo.height()))
            self._desenhar_tape(painter, QRect(corpo.x() + largura + VAO, corpo.y(), largura,
                                               corpo.height()))
            self._desenhar_bookmap(painter, QRect(corpo.right() - largura + 1, corpo.y(), largura,
                                                  corpo.height()))
        else:
            altura = max(42, (corpo.height() - 2 * VAO) // 3)
            self._desenhar_dom(painter, QRect(corpo.x(), corpo.y(), corpo.width(), altura))
            self._desenhar_tape(painter, QRect(corpo.x(), corpo.y() + altura + VAO,
                                               corpo.width(), altura))
            self._desenhar_bookmap(painter, QRect(corpo.x(), corpo.y() + 2 * (altura + VAO),
                                                  corpo.width(),
                                                  max(0, corpo.bottom() - (corpo.y() + 2 * (altura + VAO)) + 1)))
        self._desenhar_rodape(painter, s.detalhe)

    def _caixa(self, painter: QPainter, rect: QRect, titulo: str) -> QRect:
        painter.fillRect(rect, tema_asg.FUNDO_NEUTRO)
        painter.setPen(tema_asg.BORDA)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setFont(tokens.fonte_rotulo(9))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(rect.adjusted(5, 0, -5, -rect.height() + 17),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)
        return rect.adjusted(5, 19, -5, -4)

    def _preco(self, preco: int) -> str:
        if self.grid is not None:
            try:
                return formato.formatar_preco(self.grid, preco)[0] + formato.formatar_preco(self.grid, preco)[1]
            except (AttributeError, TypeError, ValueError):
                pass
        return formato.formatar_inteiro(preco)

    def _desenhar_dom(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa(painter, rect, "DOM · BID / ASK")
        linhas = max(1, min(5, area.height() // 18))
        bids, asks = self._snapshot.bids[:linhas], self._snapshot.asks[:linhas]
        if not bids and not asks:
            self._texto_vazio(painter, area, "SEM BOOK")
            return
        for indice in range(max(len(bids), len(asks))):
            y = area.y() + indice * 18
            if indice < len(bids):
                item = bids[indice]
                self._linha_lado(painter, QRect(area.x(), y, area.width() // 2 - 2, 17), item,
                                 self.paleta.compra if hasattr(self, "paleta") else tokens.OK, True)
            if indice < len(asks):
                item = asks[indice]
                self._linha_lado(painter, QRect(area.x() + area.width() // 2 + 2, y,
                                                area.width() // 2 - 2, 17), item,
                                 tokens.DANGER, False)

    def _linha_lado(self, painter: QPainter, rect: QRect, item: NivelBrutoASG,
                    cor: QColor, bid: bool) -> None:
        frac = min(1.0, item.quantidade / max(1, max(
            [nivel.quantidade for nivel in self._snapshot.bids + self._snapshot.asks] or [1]
        )))
        largura = max(1, int(rect.width() * frac))
        barra = QRect(rect.x() if bid else rect.right() - largura + 1, rect.y(), largura, rect.height())
        painter.fillRect(barra, cor.darker(170))
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        texto = f"{self._preco(item.preco)} {item.quantidade}"
        painter.drawText(rect.adjusted(2, 0, -2, 0),
                         (Qt.AlignmentFlag.AlignLeft if bid else Qt.AlignmentFlag.AlignRight)
                         | Qt.AlignmentFlag.AlignVCenter, texto)

    def _desenhar_tape(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa(painter, rect, "TAPE · NEGOCIOS")
        itens = self._snapshot.negocios[:max(1, area.height() // 18)]
        if not itens:
            self._texto_vazio(painter, area, "SEM NEGOCIOS")
            return
        for indice, item in enumerate(itens):
            linha = QRect(area.x(), area.y() + indice * 18, area.width(), 17)
            cor = tokens.OK if item.agressor > 0 else tokens.DANGER if item.agressor < 0 else tokens.NEUTRAL
            painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
            painter.setPen(cor)
            sinal = "▲" if item.agressor > 0 else "▼" if item.agressor < 0 else "◆"
            painter.drawText(linha, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{sinal} {self._preco(item.preco)}")
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(linha, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(item.quantidade))

    def _desenhar_bookmap(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa(painter, rect, "BOOKMAP · LIQUIDEZ")
        niveis = self._snapshot.asks[:4] + self._snapshot.bids[:4]
        if not niveis:
            self._texto_vazio(painter, area, "SEM LIQUIDEZ")
            return
        maximo = max(nivel.quantidade for nivel in niveis)
        altura = max(3, area.height() // max(1, len(niveis)))
        for indice, item in enumerate(niveis):
            y = area.y() + indice * altura
            cor = tokens.DANGER if indice < len(self._snapshot.asks[:4]) else tokens.OK
            largura = max(2, int(area.width() * item.quantidade / maximo))
            painter.fillRect(QRect(area.x(), y + 1, largura, max(2, altura - 2)), cor.darker(145))
            painter.setFont(tokens.fonte_numero(8))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(QRect(area.x() + 3, y, area.width() - 6, altura),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{self._preco(item.preco)} · {item.quantidade}")

    def _texto_vazio(self, painter: QPainter, rect: QRect, texto: str) -> None:
        painter.setFont(tokens.fonte_ui(9))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)


# ---------------------------------------------------------------------------
# Volante do termometro de agressao (gauge EQUILIBRIO / PRESENCA / barra de
# pressao — os tres leem o MESMO numero, ver `_linha_com_forca`).
# ---------------------------------------------------------------------------

# TAXA_MAX_VOLANTE_POR_SEGUNDO — teto de contragiro, em unidades de score
# por SEGUNDO (a escala inteira vale 2,0: de -1 a +1).
# Rotulo: IMPRECISO (proxy calibrado por medicao propria; a fonte descreve
# periodos e medias dos Medidores de Agressao, nunca uma taxa de giro).
# De onde veio: serie real medida em 28/08/2026 no replay WDOU26 de 12:00
# (190 snapshots, `.gauntlet_docx/rodadas/p8_serie_antes.csv`). A media
# movel de 5 amostras que estava aqui limita o passo por AMOSTRA, nao por
# tempo: como o intervalo entre snapshots medido vai de 0,28 s a 28 s
# (mediana 2,28 s), em rajada ela ainda girava a 0,80 score/s — a escala
# inteira em 2,5 s, tipicamente UM quadro. Com 0,20/s a travessia completa
# leva no minimo 10 s, ou seja >= 4 snapshots na cadencia mediana medida:
# o operador ve o giro acontecer em vez de ver o resultado dele.
TAXA_MAX_VOLANTE_POR_SEGUNDO = 0.20

# TEMPO_ACOMODACAO_VOLANTE_S — constante de tempo da perseguicao ao alvo.
# E o que faz o ponteiro DESACELERAR ao chegar (velocidade proporcional a
# distancia que falta), em vez de bater no alvo em velocidade de cruzeiro.
# Rotulo: IMPRECISO. Escolhido como ~1 intervalo tipico entre snapshots
# (mediana medida 2,28 s), para que o ponteiro acomode dentro do proprio
# ritmo de chegada de dado e nao entre em regime de perseguicao infinita.
TEMPO_ACOMODACAO_VOLANTE_S = 1.5

# TEMPO_INERCIA_VOLANTE_S — constante de tempo da ACELERACAO: a velocidade
# do ponteiro tambem nao muda de uma vez. E a massa do volante; sem ela a
# rampa liga e desliga em degrau e o movimento volta a parecer digital.
# Rotulo: IMPRECISO. Metade da acomodacao — amortecido, sem ultrapassagem.
TEMPO_INERCIA_VOLANTE_S = 0.8

# DT_MAX_VOLANTE_S — teto do passo de integracao. Buraco de dado nao vira
# teleporte: o maior intervalo medido na serie real foi 28 s, que a 0,20/s
# permitiria atravessar a escala inteira em UM quadro. Com este teto o
# passo visual maximo por snapshot e 0,20 x 1,5 = 0,30 de score — da mesma
# ordem do maior passo que a MM5 produzia (0,276 medido), so que agora e um
# TETO, nao um acidente da cadencia. Rotulo: IMPRECISO.
DT_MAX_VOLANTE_S = 1.5

# JANELA_PERIODO_VOLANTE_S — o "periodo" contra o qual uma agressao e
# julgada grande. Rotulo: CONFIRMADO — `bar/medidores_agressao_text.txt`
# descreve os Medidores de Agressao com "Periodos Adicionais (Media)" de
# "15 e 30 minutos"; 15 min e o menor periodo nomeado pela fonte.
JANELA_PERIODO_VOLANTE_S = 15 * 60

# Z_EXTREMO_VOLANTE — quantas vezes a agressao TIPICA do periodo (rms em
# torno do zero) valem "agressao muito grande em relacao ao periodo", ou
# seja, o fundo de escala do mostrador.
# Rotulo: IMPRECISO, com precedente interno: `fluxopro/aprendizado/padroes.py`
# ja normaliza por dispersao do historico em vez de por limiar cravado.
# 2x a tipica: o fundo de escala deixa de ser "o cru encostou em 1,0" e
# passa a exigir o dobro do que aquele periodo vinha entregando.
Z_EXTREMO_VOLANTE = 2.0

# AMOSTRAS_MINIMAS_PERIODO — abaixo disso nao ha distribuicao, so ruido, e
# o alvo e o proprio score cru (ainda passando pelo volante). Custo
# declarado: os primeiros ~20 snapshots (~45 s na cadencia medida) rodam em
# escala ABSOLUTA, nao relativa ao periodo. Rotulo: IMPRECISO.
AMOSTRAS_MINIMAS_PERIODO = 20

# LIMIAR_SAIDA_EQUILIBRIO / LIMIAR_RETORNO_EQUILIBRIO — a zona morta do
# termometro, com histerese (gatilho Schmitt). Sem ela o mostrador troca de
# COR e de rotulo COMPRA/VENDA em cima de qualquer epsilon: `_direcao_de_score`
# vira o lado a partir de 1e-9. Medido em 28/08 na serie real de 190
# snapshots (120 s de tape): o cru cruza o zero 27 vezes, a MM5 14 e o
# volante SEM zona morta 25 — ou seja, uma troca de cor a cada ~5 s, que e
# exatamente a queixa do operador ("muda de negativo para positivo muito
# rapido"). Limitar a VELOCIDADE nao resolve frequencia de cruzamento; so a
# zona morta resolve.
# Rotulo: IMPRECISO, mas derivado, nao cravado. Como o fundo de escala vale
# `Z_EXTREMO_VOLANTE` x a agressao tipica do periodo, 0,25 de escala = meia
# agressao tipica: abaixo disso o periodo nao distingue lado nenhum e o
# mostrador declara EQUILIBRIO. O retorno a 0,15 (60% da saida) e a folga
# que impede tremer na propria borda.
LIMIAR_SAIDA_EQUILIBRIO = 0.25
LIMIAR_RETORNO_EQUILIBRIO = 0.15

# DESVIO_MINIMO_PERIODO — piso do desvio-padrao, para que um periodo
# quase constante nao gere z gigante por divisao por quase-zero.
# Rotulo: AUSENTE_NA_FONTE (guarda numerica, nao regra de mercado).
DESVIO_MINIMO_PERIODO = 0.05


class VolanteGauge:
    """Termometro de agressao com INERCIA e escala relativa ao periodo.

    Existe por causa de dois pedidos distintos do operador sobre o gauge
    EQUILIBRIO, que a media movel de 5 amostras anterior nao atendia:

    1. "na teoria teria que ser igual um contragiro de carro que acelera e
       desacelera gradualmente". Media movel nao e isso: ela ATRASA o mesmo
       salto e limita o passo por AMOSTRA, nao por tempo. Medido na serie
       real de 28/08 (`.gauntlet_docx/rodadas/p8_serie_antes.csv`), a MM5
       ainda girava a 0,80 de score por segundo em rajada. Aqui o ponteiro
       tem posicao E velocidade: a velocidade persegue a distancia que
       falta (desacelera ao chegar), ela propria muda com constante de
       tempo (acelera gradual) e e limitada por um teto em score/SEGUNDO
       (o contragiro). Cadencia de dado irregular deixa de virar salto.

    2. "essas mudancas drasticas de extremos deve ser mostrado so quando
       existe agressoes muito grandes em relacao ao periodo, constantemente".
       Isso e estatistica, nao limiar cravado. O fundo de escala deixa de
       ser "o score cru bateu em 1,0" e passa a ser "a agressao vale
       `Z_EXTREMO_VOLANTE` x a agressao TIPICA do periodo" — a tipica medida
       como rms das leituras dos ultimos `JANELA_PERIODO_VOLANTE_S`
       segundos, que e o menor periodo nomeado pela fonte.

       A dispersao e medida EM TORNO DO ZERO, nao em torno da media do
       periodo, e isso e uma decisao com evidencia: o zero deste mostrador
       tem significado fisico (EQUILIBRIO). Centrar na media do periodo faz
       o ponteiro trocar de lado quando a agressao apenas VOLTA para a media
       sem trocar de lado — medido em 28/08 na serie real, a versao centrada
       na media cruzava o zero 26 vezes em 190 snapshots, PIOR que as 14 da
       media movel que ela deveria melhorar.

    3. "constantemente" e servido por duas coisas juntas: a rampa da camada
       1 (a 0,20/s, sair do zero e chegar ao fundo de escala custa >= 5 s de
       alvo sustentado — um pico isolado nao chega la) e a zona morta com
       histerese (`LIMIAR_SAIDA_EQUILIBRIO`), sem a qual o mostrador troca
       de cor em cima de qualquer epsilon.

    O alvo combina absoluto e relativo pelo MENOR modulo — extremo exige ser
    grande em absoluto E grande para o periodo — e o SINAL vem sempre da
    agressao crua.

    CUSTO, declarado porque suavizar nao pode virar mentira. Os numeros
    abaixo sao de 4.361 snapshots / 5.043 s de tape real WDOU26
    (`.gauntlet_docx/rodadas/p8_cauda.py`), NAO da janela de 120 s da
    primeira medicao: naquela janela a cauda parecia ~28 s e isso era
    otimista por 8x. Cauda so se mede em janela larga, e ela tem DOIS
    REGIMES que nao podem ser declarados como um numero so:

    - virada FORTE — o cru troca de lado e chega a ficar grande para o
      periodo (pico 0,25 a 1,00): n=108, atraso mediano 0,7 s, p90 4,5 s,
      MAXIMO 25,8 s.
    - virada FRACA — o cru troca de lado mas nunca fica grande para o
      periodo (pico 0,04 a 0,25), e a zona morta portanto NAO deixa a tela
      seguir: n=35, mediana 3,9 s, p90 41,4 s, MAXIMO 225,8 s.

    Ou seja: o mostrador acompanha depressa o que e agressao de verdade, e
    demora minutos para acompanhar o que nao e — que e exatamente o filtro
    pedido, mas so vale como custo declarado se o numero grande estiver
    escrito. Nas duas classes, ZERO viradas sustentadas foram perdidas
    (n=143). A media movel anterior virava junto (mediana 0 s) — e virava
    junto tambem nas viradas que nao se sustentaram.

    Um mal-entendido que a medicao desfez: esses 225 s NAO sao "mostrador
    congelado no zero". O estado de ficar preso no EQUILIBRIO tendo
    agressao de um lado so foi medido a parte (`segundos_represado`) e dura
    no maximo 22,2 s na mesma janela. E esse estado, nao a cauda, que
    `nexo/contexto.py` carimba na tela.
    - o texto pequeno da leitura declara `SUAV` (ver `_linha_com_forca`)
      para nao ser confundido com o score do instante.
    - um periodo em que o score fica CRAVADO no mesmo valor (inclusive
      cravado em +1,0, como na fixture sintetica de livro de
      `capturar_sessao.py`) tem agressao tipica igual ao proprio valor, e o
      mostrador estaciona em exatamente 1/`Z_EXTREMO_VOLANTE` da escala
      (0,50). Isso e deliberado: pressao constante nao e agressao "muito
      grande em relacao ao periodo", mas tambem nao e equilibrio. Quem quer
      o score do instante le o tape, nao o termometro.

    Estado puro em Python (sem Qt), para ser testavel sem tela. Nao e
    idempotente: `avancar` integra o tempo e SO pode ser chamado quando
    chega snapshot novo — nunca no caminho de pintura.
    """

    def __init__(self) -> None:
        self.valor = 0.0
        self.velocidade = 0.0
        self._ts_ns = 0
        self._lado = 0
        # Instante em que o ponteiro passou a ficar PRESO na zona morta
        # tendo agressao do outro lado do zero para mostrar. Zero = solto.
        self._represado_ns = 0
        self._periodo: deque[tuple[int, float]] = deque()

    @property
    def andou(self) -> bool:
        """Ja recebeu snapshot com relogio? Antes disso nao ha leitura
        propria e quem le deve mostrar o score cru."""

        return self._ts_ns > 0

    def alvo(self, bruta: float) -> float:
        """Onde o ponteiro QUER chegar — ja na escala relativa ao periodo."""

        valores = [v for _, v in self._periodo]
        if len(valores) < AMOSTRAS_MINIMAS_PERIODO:
            return max(-1.0, min(1.0, bruta))
        # Dispersao medida EM TORNO DO ZERO (rms), nao em torno da media do
        # periodo — ver a docstring da classe: o zero deste mostrador e o
        # EQUILIBRIO, e recentrar na media do periodo faz o ponteiro trocar
        # de lado sem a agressao ter trocado de lado. Medido em 28/08 na
        # serie real: a versao centrada na media produzia 26 trocas de sinal
        # em 190 snapshots contra 14 da MM5 que ela deveria melhorar.
        tipica = max(DESVIO_MINIMO_PERIODO,
                     math.sqrt(statistics.fmean(v * v for v in valores)))
        relativo = abs(bruta) / (Z_EXTREMO_VOLANTE * tipica)
        return math.copysign(min(1.0, abs(bruta), relativo), bruta)

    def segundos_represado(self, agora_ns: int) -> float:
        """Ha quantos segundos o ponteiro esta preso no EQUILIBRIO com
        agressao de um lado so para mostrar. `0.0` quando esta solto.

        Existe para o custo do volante poder ir A TELA, e nao so a
        docstring — ver `nexo/contexto.py`. Enquanto isso vale zero, a
        leitura de EQUILIBRIO e simplesmente a leitura; quando passa de
        dezenas de segundos, o operador esta olhando um zero que significa
        "ha fluxo, mas fraco para o periodo", e isso e outra coisa.
        """

        if self._represado_ns <= 0 or agora_ns <= self._represado_ns:
            return 0.0
        return (agora_ns - self._represado_ns) / 1_000_000_000

    def _alvo_com_equilibrio(self, bruta: float, timestamp_ns: int) -> float:
        """`alvo` passado pela zona morta com histerese.

        O lado so e ADOTADO quando o alvo passa de `LIMIAR_SAIDA_EQUILIBRIO`,
        e so e largado quando cai abaixo de `LIMIAR_RETORNO_EQUILIBRIO` — ou
        quando o alvo aparece do outro lado, caso em que o mostrador volta
        para o EQUILIBRIO e tem de reconquistar o limiar de saida do lado
        novo. E por isso que uma troca de sinal na tela exige agressao
        sustentada dos dois lados da virada, e nao um instante.
        """

        alvo = self.alvo(bruta)
        lado = 0 if alvo == 0.0 else (1 if alvo > 0 else -1)
        if self._lado == 0:
            if abs(alvo) >= LIMIAR_SAIDA_EQUILIBRIO:
                self._lado = lado
        elif lado != self._lado or abs(alvo) < LIMIAR_RETORNO_EQUILIBRIO:
            self._lado = 0
        if self._lado == 0 and lado != 0:
            # Ha agressao, e ela nao e forte o bastante para o periodo. E o
            # regime de cauda longa: a tela mostra EQUILIBRIO enquanto o cru
            # ja trocou de lado. Marcar desde quando, para poder DIZER.
            if self._represado_ns == 0:
                self._represado_ns = timestamp_ns
        else:
            self._represado_ns = 0
        return alvo if self._lado != 0 else 0.0

    def avancar(self, bruta: float, timestamp_ns: int) -> float:
        self._periodo.append((timestamp_ns, bruta))
        corte = timestamp_ns - JANELA_PERIODO_VOLANTE_S * 1_000_000_000
        while self._periodo and self._periodo[0][0] < corte:
            self._periodo.popleft()

        if self._ts_ns <= 0 or timestamp_ns <= self._ts_ns:
            # Primeiro snapshot (ou relogio que nao andou): sem dt nao ha
            # taxa, e sem taxa o ponteiro nao se move. Comeca no zero.
            self._ts_ns = max(self._ts_ns, timestamp_ns)
            return self.valor

        dt = min(DT_MAX_VOLANTE_S, (timestamp_ns - self._ts_ns) / 1_000_000_000)
        self._ts_ns = timestamp_ns

        velocidade_alvo = ((self._alvo_com_equilibrio(bruta, timestamp_ns) - self.valor)
                           / TEMPO_ACOMODACAO_VOLANTE_S)
        peso = min(1.0, dt / TEMPO_INERCIA_VOLANTE_S)
        self.velocidade += (velocidade_alvo - self.velocidade) * peso
        self.velocidade = max(-TAXA_MAX_VOLANTE_POR_SEGUNDO,
                              min(TAXA_MAX_VOLANTE_POR_SEGUNDO, self.velocidade))
        self.valor = max(-1.0, min(1.0, self.valor + self.velocidade * dt))
        return self.valor


class PainelNexoMercadoASG(_PainelASG):
    """Superfície primária própria: pulso, pressão, sinal e mapa de preço.

    A composição dialoga com a densidade dos prints de referência, mas toda a
    semântica é do Operador B3: não há logotipo, avatar, marca, imagem ou
    fórmula de terceiros. O painel recebe somente o snapshot já congelado da
    janela e mantém uma série curta, delimitada e exclusivamente visual.
    """

    titulo = "NEXO · PULSO DO MERCADO"
    etapa = "0"
    cor_secao = tema_asg.MATRIZ

    def __init__(
        self,
        parent: QWidget | None = None,
        grid: PriceGrid = WDO_GRID,
        paleta: tokens.Paleta = tokens.PALETA_COR,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.paleta = paleta
        # Nova composição somente neste painel; rollback sem perder estado.
        self._nexo_ai_ativo = os.environ.get("FLUXOPRO_NEXO_AI", "1") != "0"
        self._dialogo_nexo_ai = None
        from PySide6.QtGui import QKeySequence, QShortcut

        self._atalho_nexo_detalhes = QShortcut(QKeySequence("F6"), self)
        self._atalho_nexo_detalhes.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._atalho_nexo_detalhes.activated.connect(self._abrir_detalhes_nexo_ai)
        self._atalho_nexo_classico = QShortcut(QKeySequence("F7"), self)
        self._atalho_nexo_classico.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._atalho_nexo_classico.activated.connect(self._alternar_nexo_ai)
        self.setAccessibleName("Operador B3 · NEXO AI. F6 detalhes; F7 composição clássica.")
        self._snapshot = WorkspaceASGSnapshot(
            0,
            DadosASGSnapshot(0),
            ProcessamentoASGSnapshot(0),
            MatrizASGSnapshot(0),
            DecisaoASGSnapshot(0),
            TrilhaEvidenciasASGSnapshot(0),
            contexto_bruto=ContextoBrutoASGSnapshot(0),
        )
        # Historico exclusivamente visual, limitado. Cada ponto vem de um
        # negocio observado (quando a ponte o entrega), e nao de um valor
        # sintetizado pela UI. Isso permite candles causais e um grafico que
        # ganha densidade no pregão sem reter dados indefinidamente.
        self._serie: deque[tuple[int, int, float, int]] = deque(maxlen=480)
        self._serie_forca_ai: deque[tuple[int, float]] = deque(maxlen=48)
        # Buffer de negocios crus (timestamp, preco, qty, agressor) so pra
        # montar o VAP recortado em 5M/15M sob pedido (achado do operador em
        # 27/08/2026: o VAP so tinha o perfil da sessao inteira). Trimado por
        # TEMPO (nao por contagem) porque o ritmo de negocios varia demais ao
        # longo do pregao pra um maxlen fixo ser seguro nos dois sentidos.
        self._trades_vap_recentes: deque[tuple[int, int, int, AgressorSide]] = deque()
        self._vap_timeframe_min = 0
        """0 = perfil da sessao inteira (`self._vap`, nunca reamostrado);
        5/15 = perfil recortado dos ultimos N minutos via `_perfil_vap_ativo`."""
        # Renko (gráfico superior direito, "4R"): blocos por deslocamento de
        # preço, nunca por tempo. Agregador puro, alimentado por chamada
        # direta junto com `_serie` — nunca assina o barramento. Ver
        # docstring de `fluxopro/analytics/renko.py` para os rótulos de
        # confiança (CONFIRMADO/IMPRECISO/AUSENTE NA FONTE) por regra.
        # Semente visual mais fina: o Renko continua dinamico e auditavel,
        # mas comeca com blocos de 2 pontos para dar mais degraus desde a
        # abertura. O tamanho real segue sendo recalibrado pelo agregador.
        self._renko = Renko(grid, ConfigRenko(tamanho_tijolo_pontos=2.0))
        # VAP (volume por preço): substitui a escada tipo DOM na lateral
        # esquerda, por pedido do operador — "é um vap, é um volume
        # profile... só que eu consigo trabalhar num nível de refinamento"
        # (pesquisa/ferramenta_componentes.md §5, 3mfeHZhMZrc.txt).
        # Alimentado pelos MESMOS negocios que ja alimentam `_serie` — nunca
        # um segundo feed. Retenção: um nível por PREÇO distinto realmente
        # negociado, não por evento — bounded pela faixa de preço da sessão,
        # não pelo número de trades.
        self._vap = VolumeProfile()
        # Candle temporal M5 (gráfico inferior direito): mesmo padrão de
        # bucketing de `estado_mercado.py`, mas com retenção limitada — ver
        # docstring de `fluxopro/analytics/candle_temporal.py`. O candle em
        # formação aparece desde o PRIMEIRO negócio do dia — nao esperamos
        # 5 minutos para o operador ver o pavio se formando.
        self._candles_m15 = CandleTemporal(ConfigCandleTemporal(timeframe_ns=5 * 60_000_000_000))
        # 15 minutos (pedido do operador, 27/08/2026: "de a opcao de time
        # de 5M e 15M editavel"). Alimentado em PARALELO ao de 5 minutos,
        # sempre — nunca reconstruido na troca de timeframe, o que perderia
        # o dia ate ali (`self._serie` guarda preco/forca, nao agressor por
        # negocio, entao nao daria pra refazer o volume por lado depois).
        self._candles_15m = CandleTemporal(ConfigCandleTemporal(timeframe_ns=15 * 60_000_000_000))
        self._timeframe_candles_min = 5
        self._candles_offset = 0
        self._arrasto_candles_ativo = False
        self._arrasto_candles_x0 = 0
        self._arrasto_candles_offset0 = 0
        # ESCALA do grafico (pedido do operador, 27/08/2026: "eu podendo
        # mexer no grafico na escala arrastando"). Sao dois zooms
        # independentes, como em qualquer grafico de pregao:
        #   - tempo: quantas velas cabem na janela. `None` = janela do pregao
        #     inteiro (o padrao calculado por `nexo/candles.py`).
        #   - preco: fator multiplicativo sobre a faixa de precos visivel;
        #     1,0 e a faixa "cabe tudo", >1 amplia (achata menos), <1 achata.
        # Nenhum dos dois altera dado nenhum: sao so o recorte que a pintura
        # usa. Preco continua int de ticks ate a fronteira de desenho.
        self._candles_velas_visiveis: int | None = None
        self._candles_zoom_preco = 1.0
        # CROSSHAIR / leitura por vela (achado de 28/08/2026: dava para
        # ampliar a vela mas nao para LER o preco dela). Guarda a posicao do
        # cursor SO quando ela cai dentro da regiao de candles; fora dali o
        # estado volta a None e nada e repintado por causa do mouse.
        self._cursor_candles: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self._arrasto_escala: str | None = None  # "tempo" | "preco"
        self._arrasto_escala_x0 = 0
        self._arrasto_escala_y0 = 0
        self._arrasto_escala_base = 0.0
        # Termometro de agressao do MakerProxy (gauge EQUILIBRIO, PRESENCA e
        # a barra 56/44 de "pressao" em pressao.py — os 3 leem o MESMO
        # numero). Ate 28/08/2026 aqui havia uma media movel de 5 amostras;
        # ela foi MEDIDA na serie real e reprovada (ver `VolanteGauge`):
        # limitava o passo por amostra, nao por tempo, e nao tinha nocao
        # nenhuma do que e "grande em relacao ao periodo".
        self._volante_maker = VolanteGauge()
        # Sinal Ultra (fluxopro/asg/sinal_ultra.py) — filtro adicional
        # construido do zero por este projeto (a fonte original nunca
        # definiu essa regra). So consultivo: nunca aparece aqui como envio
        # de ordem, so como snapshot lido pela regiao nucleo.py.
        self._sinal_ultra = MotorSinalUltra(ConfigSinalUltra())
        self._ultimo_sinal_ultra = None
        self._direcao_ultra_anunciada = DirecaoUltra.NENHUMA
        # Fase da histerese (ARMADO/SEGURANDO/...) na ultima vez que a voz
        # olhou pra ela — ver `_atualizar_sinal_ultra`. `AUSENTE` porque
        # ainda nao ha `SinalUltraSnapshot` no primeiro quadro, mesmo valor
        # que `nexo.vies.fase_do_filtro_de_sinal(None)` devolveria.
        self._fase_ultra_anunciada = "ausente"
        # Ver docstring de `_VOZ_ATIVA_POR_PADRAO` — desligado por padrao.
        self._locutor = LocutorASG(ConfigVoz(ativo=_VOZ_ATIVA_POR_PADRAO))
        # Suporte/Resistencia (fluxopro/analytics/suporte_resistencia.py) —
        # motor determinístico construído do zero por este projeto a partir
        # de INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md (pasta Codex, trazido
        # pelo operador). Stateful (sequencia/idempotencia/saude de feed),
        # por isso vive aqui — um por painel, nunca recriado por quadro.
        self._motor_sr = MotorSuporteResistencia(stream_id="nexo")
        self._sr_sequencia = 0
        # A sequencia dos motores conta EVENTO (snapshot novo), nunca
        # QUADRO. Ate 31/08/2026 ela incrementava a cada `desenhar()` —
        # 60 vezes por segundo — enquanto o `event_id` derivava do
        # timestamp do snapshot, que muda MUITO mais devagar. Efeito
        # medido no app real: o cache devolvia cedo sem registrar a
        # sequencia, e quando enfim chegava um timestamp novo a sequencia
        # tinha "saltado" ~20 posicoes; o motor lia isso como GAP, entrava
        # em RECOVERING e o gap seguinte zerava o contador de recuperacao.
        # Resultado: 128 de 138 quadros presos em RECOVERING e dominancia
        # 100% INDISPONIVEL. Guardar o ultimo timestamp e so avancar a
        # sequencia quando ele muda faz sequencia e event_id andarem
        # juntos, que e a premissa do motor.
        self._sr_ultimo_ts = -1
        # Dominância Comprador/Vendedor
        # (fluxopro/analytics/dominancia.py) — motor irmão do de Suporte/
        # Resistência, construído a partir de
        # INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md (pasta Codex).
        self._motor_dominancia = MotorDominancia(stream_id="nexo")
        self._dominancia_sequencia = 0
        self._dominancia_ultimo_ts = -1  # ver comentario em `_sr_ultimo_ts`
        # Analise consultiva do Claude (fluxopro/analytics/analise_claude.py).
        # A chamada mede 14-30 s e vive numa thread propria: este painel
        # apenas PEDE a cada quadro e le o ultimo resultado pronto. Nunca
        # espera, nunca bloqueia os 60 fps.
        self._motor_analise = MotorAnaliseClaude() if ligado_por_ambiente() else None

    def _calcular_sr_snapshot(self, estado_parcial: nexo.EstadoNexo):
        """Roda o motor de Suporte/Resistencia sobre o `EstadoNexo` do
        quadro (ainda sem `sr_snapshot`) e devolve o snapshot publicado.

        Import tardio de `nexo.suporte_resistencia` pelo MESMO motivo do
        `nexo_indisponivel` em `desenhar()`: o pacote raiz `nexo` e o unico
        que entra no topo deste arquivo (ver comentario ao lado do import),
        os modulos de regiao carregam sob demanda para desfazer o ciclo
        regiao -> asg -> nexo.
        """

        from fluxopro.ui.paineis.nexo import suporte_resistencia as nexo_sr

        entrada = nexo_sr.construir_entrada_sr(estado_parcial)
        timestamp_ns = max(1, int(self._snapshot.timestamp_ns))
        # Sequencia por EVENTO, nunca por quadro — ver `_sr_ultimo_ts`.
        if timestamp_ns != self._sr_ultimo_ts:
            self._sr_sequencia += 1
            self._sr_ultimo_ts = timestamp_ns
        # REPLAY nao tem "atraso de parede" que signifique alguma coisa —
        # timestamps historicos comparados contra o relogio real dariam
        # idade de dias. So em AO_VIVO o relogio de parede mede staleness
        # de verdade; e a UNICA leitura desta funcao que consulta relogio,
        # e so para ISTO (saude de feed), nunca para decidir zona ou score.
        em_replay = getattr(self._snapshot, "estado_operacional", None) is EstadoASG.REPLAY
        agora_ns = timestamp_ns if em_replay else time.time_ns()
        return self._motor_sr.processar(
            event_id=f"sr-{timestamp_ns}",
            sequencia=self._sr_sequencia,
            timestamp_ns=timestamp_ns,
            instrumento=getattr(self.grid, "simbolo", "WDO"),
            tick_size=self.grid.tick_size,
            agora_ns=agora_ns,
            **entrada,
        )

    def _pacote_analise(self, estado_parcial: nexo.EstadoNexo):
        """Pede uma analise (o motor decide se e a hora) e devolve o ultimo
        resultado pronto: ``(estado, analise, motivo, idade_s)``.

        Import tardio de `nexo.analise` pelo mesmo motivo dos demais
        modulos de regiao — so o pacote raiz `nexo` entra no topo deste
        arquivo.
        """

        if self._motor_analise is None:
            return None
        from fluxopro.ui.paineis.nexo import analise as nexo_analise

        try:
            dados = nexo_analise.dados_do_estado(estado_parcial)
            # So pede analise quando ha mercado para analisar — sem o gate,
            # a primeira chamada saia no quadro zero e ocupava a tela por
            # 90 s dizendo que nao havia dados (ver `dados_suficientes`).
            if nexo_analise.dados_suficientes(dados):
                self._motor_analise.solicitar(dados)
        except Exception:  # noqa: BLE001
            # Uma analise decorativa NUNCA pode derrubar o quadro. Se a
            # extracao de dados falhar, a regiao desenha "sem analise".
            return None
        estado_a, analise, motivo = self._motor_analise.ultima()
        return estado_a, analise, motivo, self._motor_analise.idade_s()

    def _calcular_dominancia_snapshot(self, estado_parcial: nexo.EstadoNexo):
        """Roda o motor de Dominância Comprador/Vendedor sobre o
        `EstadoNexo` do quadro — mesmo padrão de `_calcular_sr_snapshot`
        (import tardio para não violar a regra de só o pacote raiz `nexo`
        entrar no topo deste arquivo)."""

        from fluxopro.ui.paineis.nexo import dominancia as nexo_dominancia

        entrada = nexo_dominancia.construir_entrada_dominancia(estado_parcial)
        timestamp_ns = max(1, int(self._snapshot.timestamp_ns))
        # Sequencia por EVENTO, nunca por quadro — ver `_sr_ultimo_ts`.
        if timestamp_ns != self._dominancia_ultimo_ts:
            self._dominancia_sequencia += 1
            self._dominancia_ultimo_ts = timestamp_ns
        em_replay = getattr(self._snapshot, "estado_operacional", None) is EstadoASG.REPLAY
        agora_ns = timestamp_ns if em_replay else time.time_ns()
        idade_ms = 0.0 if em_replay else max(0.0, (agora_ns - timestamp_ns) / 1_000_000.0)
        return self._motor_dominancia.processar(
            event_id=f"dom-{timestamp_ns}",
            sequencia=self._dominancia_sequencia,
            timestamp_ns=timestamp_ns,
            instrumento=getattr(self.grid, "simbolo", "WDO"),
            modo="REPLAY" if em_replay else "LIVE",
            idade_ms=idade_ms,
            **entrada,
        )

    def aplicar(self, snapshot: WorkspaceASGSnapshot) -> None:
        self._snapshot = snapshot
        from fluxopro.ui.paineis.nexo.assistente import forca_publicada

        forca_ai = forca_publicada(snapshot)
        if (forca_ai is None or (self._serie_forca_ai
                and snapshot.timestamp_ns < self._serie_forca_ai[-1][0])):
            self._serie_forca_ai.clear()
        if forca_ai is not None:
            ponto_ai = (snapshot.timestamp_ns, forca_ai)
            if self._serie_forca_ai and snapshot.timestamp_ns == self._serie_forca_ai[-1][0]:
                self._serie_forca_ai[-1] = ponto_ai
            else:
                self._serie_forca_ai.append(ponto_ai)
        linha_maker_bruta = next(
            (l for l in snapshot.matriz.linhas if l.componente == "MAKERPROXY"), None
        )
        if linha_maker_bruta is not None and snapshot.timestamp_ns > 0:
            # O volante INTEGRA o tempo: so pode andar quando chega snapshot
            # novo. O caminho de pintura (`_forca_maker_suavizada`) so LE.
            self._volante_maker.avancar(linha_maker_bruta.forca, snapshot.timestamp_ns)
        contexto = snapshot.contexto_bruto
        negocios = () if contexto is None else tuple(contexto.negocios)
        for negocio in sorted(negocios, key=lambda item: item.timestamp_ns):
            self._registrar_amostra(
                negocio.timestamp_ns,
                negocio.preco,
                self._forca_atual(),
                negocio.quantidade,
                _agressor_de_int(negocio.agressor),
            )
        if not negocios and contexto is not None and contexto.ultimo_preco is not None:
            self._registrar_amostra(
                snapshot.timestamp_ns,
                int(contexto.ultimo_preco),
                self._forca_atual(),
                0,
            )
        self._atualizar_sinal_ultra(snapshot.timestamp_ns)
        self.marcar_tudo_sujo()

    def _atualizar_sinal_ultra(self, timestamp_ns: int) -> None:
        """Alimenta o `MotorSinalUltra` com o retrato JA calculado deste
        quadro (decisao confirmada + Renko + MakerProxy suavizado) — nunca
        lookahead, so o que a UI ja tem em maos neste instante."""

        if timestamp_ns <= 0:
            return
        direcao_decisao = _direcao_ultra_de(self._snapshot.decisao.direcao)
        tijolos = self._renko.tijolos
        direcao_renko = DirecaoUltra.NENHUMA
        if tijolos:
            ultimo = tijolos[-1].direcao
            direcao_renko = DirecaoUltra.COMPRA if ultimo > 0 else DirecaoUltra.VENDA
        linha_maker = self._linha_maker()
        forca_maker = 0.0 if linha_maker is None else linha_maker.forca
        confianca_alta = linha_maker is not None and linha_maker.confianca is ConfiancaASG.ALTA
        self._ultimo_sinal_ultra = self._sinal_ultra.atualizar(
            EntradaSinalUltra(
                timestamp_ns=timestamp_ns,
                direcao_decisao_confirmada=direcao_decisao,
                fase_renko=self._renko.fase,
                direcao_renko=direcao_renko,
                forca_maker=forca_maker,
                confianca_maker_alta=confianca_alta,
            )
        )
        nova_direcao = self._ultimo_sinal_ultra.direcao
        fase_agora = nexo.modulo("vies").fase_do_filtro_de_sinal(self._ultimo_sinal_ultra)
        if nova_direcao is not self._direcao_ultra_anunciada:
            # Transicao de DIRECAO (armou/encerrou) sempre manda no texto —
            # o "armado" ja afirma "as fontes concordam", entao a fase deste
            # mesmo instante fica batizada como ja anunciada, sem narrar
            # separadamente (evita falar duas vezes na mesma virada).
            texto = texto_para_transicao_ultra(self._direcao_ultra_anunciada, nova_direcao)
            self._locutor.falar(texto)
            self._direcao_ultra_anunciada = nova_direcao
            self._fase_ultra_anunciada = fase_agora
        elif fase_agora != self._fase_ultra_anunciada:
            # Achado de auditoria (28/08/2026): "a voz nao anuncia a perda
            # de alinhamento do Ultra". A direcao nao mudou (o selo continua
            # aceso do mesmo lado) mas a fase da histerese sim — e o visor
            # central e o OPERADOR IA ja mostram essa mudanca na tela (ver
            # `nexo/nucleo.py` e `nexo/vies.py`); so a voz ficava muda.
            _vies = nexo.modulo("vies")
            if fase_agora == _vies.SEGURANDO:
                self._locutor.falar(texto_para_perda_de_alinhamento(nova_direcao))
            elif fase_agora == _vies.ARMADO and self._fase_ultra_anunciada == _vies.SEGURANDO:
                self._locutor.falar(texto_para_realinhamento(nova_direcao))
            self._fase_ultra_anunciada = fase_agora

    def aplicar_mercado(self, retrato: Instantaneo) -> None:
        negocios = tuple(retrato.novos_trades)
        for negocio in sorted(negocios, key=lambda item: item.timestamp_ns):
            self._registrar_amostra(
                negocio.timestamp_ns,
                int(negocio.price),
                self._forca_atual(),
                int(negocio.qty),
                _agressor_de_int(negocio.agressor),
            )
        preco = retrato.ultimo_preco
        if not negocios and preco is not None and self._snapshot.timestamp_ns > 0:
            self._registrar_amostra(
                max(self._snapshot.timestamp_ns, retrato.ultimo_evento_ns),
                int(preco),
                self._forca_atual(),
                0,
            )
        self.marcar_tudo_sujo()

    def _registrar_amostra(
        self,
        timestamp_ns: int,
        preco: int,
        forca: float,
        quantidade: int = 0,
        agressor: AgressorSide = AgressorSide.UNKNOWN,
    ) -> None:
        if self._serie and timestamp_ns < self._serie[-1][0]:
            return
        ponto = (timestamp_ns, preco, max(-1.0, min(1.0, forca)), max(0, quantidade))
        if self._serie and timestamp_ns == self._serie[-1][0] and preco == self._serie[-1][1]:
            self._serie[-1] = ponto
        else:
            self._serie.append(ponto)
        # Renko e candle M15 leem o MESMO preco/negocio que a serie visual —
        # nunca um segundo feed, so um segundo agregador sobre o mesmo dado.
        self._renko.registrar(timestamp_ns, preco)
        self._candles_m15.registrar(timestamp_ns, preco, quantidade, agressor)
        self._candles_15m.registrar(timestamp_ns, preco, quantidade, agressor)
        if quantidade > 0:
            self._vap.registrar_trade(
                Trade(timestamp_ns=timestamp_ns, symbol="", price=preco,
                     qty=quantidade, side_agressor=agressor, trade_id="")
            )
            self._trades_vap_recentes.append((timestamp_ns, preco, quantidade, agressor))
            limite = timestamp_ns - self._JANELA_VAP_RECENTE_NS_MAX
            while self._trades_vap_recentes and self._trades_vap_recentes[0][0] < limite:
                self._trades_vap_recentes.popleft()

    def _forca_atual(self) -> float:
        linhas = self._snapshot.matriz.linhas
        if not linhas:
            return 0.0
        pesos = [linha.forca for linha in linhas if linha.componente != "MAKERPROXY"]
        if not pesos:
            pesos = [linha.forca for linha in linhas]
        return sum(pesos) / max(1, len(pesos))

    JANELA_RISCO_VOLATILIDADE = 20
    """IMPRECISO — nao ha formula de "risco de volatilidade" em nenhuma
    fonte deste projeto (pesquisa/*.md). Janela de amostras recentes usada
    para o desvio-padrao dos precos, rotulada como proxy, nunca como a
    metodologia do autor."""

    LIMIAR_DOMINANCIA_EXAUSTAO = 0.85

    def _risco_volatilidade(self) -> float:
        """Proxy de risco de volatilidade: desvio-padrao dos ultimos precos
        observados, normalizado pelo tick do simbolo, clampado em [0, 1].

        IMPRECISO/INFERIDO — nenhuma fonte deste projeto revela uma formula
        de "risco de volatilidade"; isto e um desvio-padrao classico sobre
        os MESMOS precos reais de `_serie` (nenhum dado novo), nunca
        apresentado como calculo do autor da metodologia.
        """

        amostras = list(self._serie)[-self.JANELA_RISCO_VOLATILIDADE:]
        if len(amostras) < 3:
            return 0.0
        precos = [item[1] for item in amostras]
        media = sum(precos) / len(precos)
        variancia = sum((p - media) ** 2 for p in precos) / len(precos)
        desvio_ticks = variancia ** 0.5
        # 6 ticks de desvio-padrao ~= risco maximo (1.0) — piso arbitrario
        # de normalizacao, documentado como tal, nunca um limiar da fonte.
        return max(0.0, min(1.0, desvio_ticks / 6.0))

    def _alerta_exaustao(self) -> tuple[str, float] | None:
        """Estado de exaustao direcional: fluxo extremo e sustentado num
        sentido, onde entrar CONTRA o movimento e o pior preco (mesma regra
        de disciplina do 4R — ver `fluxopro/analytics/renko.py`). Nunca uma
        ordem, so um aviso para nao operar contratendencia sem esperar
        enfraquecer/pullback.

        Le a leitura MACRO (`HORIZONTE`, ja calculada em
        `_linhas_contexto_nexo`) — nenhum dado novo, so um limiar sobre o
        que ja existe. Retorna (direcao_do_extremo, magnitude) ou None.
        """

        for apelido, linha in self._linhas_contexto_nexo():
            if apelido != "HORIZONTE":
                continue
            if linha.forca >= self.LIMIAR_DOMINANCIA_EXAUSTAO:
                return ("COMPRA", linha.forca)
            if linha.forca <= -self.LIMIAR_DOMINANCIA_EXAUSTAO:
                return ("VENDA", linha.forca)
        return None

    def _linha_regime(self) -> LinhaMatrizASG | None:
        """A linha REGIME do snapshot, verificada como coerente antes de
        atravessar a fronteira.

        O REGIME ja nasce solidario em `_linhas_da_matriz_asg` (a `forca`
        e derivada da PROPRIA `direcao`: +1 comprador, -1 vendedor). O que
        faltava era **entregar isso a quem desenha** — o cartao central lia
        so o texto e escolhia um token de cor fixo. Agora a leitura inteira
        atravessa, e a assercao abaixo impede que uma futura mudanca de
        fonte reintroduza sinal e palavra em desacordo.
        """

        linha = next(
            (l for l in self._snapshot.matriz.linhas if l.componente == "REGIME"), None
        )
        if linha is None or not leitura_e_coerente(linha):
            return None
        return linha

    def _linha_maker_coerente(self, linha: LinhaMatrizASG) -> LinhaMatrizASG:
        """Aplica a suavizacao do MakerProxy SEM quebrar a solidariedade
        entre grandeza e sinal — ver `_linha_com_forca`.

        Este metodo existe porque o `dataclass_replace(linha, forca=...)`
        solto (o que havia aqui ate 28/08/2026) trocava so a grandeza: a
        `direcao` e o `valor` continuavam vindo do score CRU. Com a media
        movel de um lado e o cru do outro, o mesmo MakerProxy aparecia em
        quatro lugares do quadro com sinais diferentes.
        """

        return _linha_com_forca(linha, self._forca_maker_suavizada(linha.forca))

    def _forca_maker_suavizada(self, bruta: float) -> float:
        """LEITURA pura do volante — nunca avanca o tempo.

        Pintar o mesmo quadro duas vezes tem de dar o mesmo numero; quem
        integra e `aplicar`, uma vez por snapshot. Enquanto o volante nunca
        andou (nenhum snapshot com timestamp), a leitura e o proprio cru.
        """

        if not self._volante_maker.andou:
            return bruta
        return self._volante_maker.valor

    def _linha_maker(self) -> LinhaMatrizASG | None:
        for linha in self._snapshot.matriz.linhas:
            if linha.componente == "MAKERPROXY":
                return self._linha_maker_coerente(linha)
        return None

    def total_itens(self) -> int:
        return len(self._serie)

    def capacidade_pagina(self) -> int:
        return self._serie.maxlen or 0

    def retangulos_visiveis(self) -> tuple[tuple[int, QRect], ...]:
        return ()

    def textos_visiveis(self) -> tuple[str, ...]:
        s = self._snapshot
        maker = self._linha_maker()
        textos = [
            "NEXO", "PULSO DO MERCADO", "PRESSAO INSTITUCIONAL",
            "SINAL CONSULTIVO", "MAPA DE PRECO", "FORCA DO FLUXO",
            "SEM ENVIO DE ORDENS", rotulo_estado(s.estado_operacional),
            rotulo_direcao(s.decisao.direcao), s.decisao.titulo,
            f"STOP {s.decisao.stop}", f"A1 {s.decisao.alvo_1}",
            f"A2 {s.decisao.alvo_2}", f"A3 {s.decisao.alvo_3}",
        ]
        if maker is not None:
            textos.extend(("MAKERPROXY", maker.valor, maker.detalhe))
        if self._serie:
            preco = formato.formatar_preco(self.grid, self._serie[-1][1])
            textos.append(f"PRECO {preco[0]}{preco[1]}")
        else:
            textos.append("AGUARDANDO PRECO")
        return tuple(textos)

    N_NIVEIS_DESTACADOS = 3
    """CONFIRMADO na fonte (f0hrhzhLDVM.txt): "voce so vai dar importancia
    pra ela pra esses TRES precos que aparecem destacados... do contrario,
    voce esquece ela". Nunca um numero solto — e o unico caso em que a
    contagem exata vem dita na transcricao, nao inferida."""

    _JANELA_VAP_RECENTE_NS_MAX = 15 * 60 * 1_000_000_000

    def _perfil_vap_ativo(self) -> VolumeProfile:
        """Perfil da sessao inteira (padrao) ou recortado aos ultimos
        5/15 minutos, conforme `self._vap_timeframe_min` (chip clicavel no
        rodape do VAP, ver `mousePressEvent`). Recorte SEMPRE reconstruido do
        mesmo buffer de negocios crus — nunca um segundo feed."""

        if self._vap_timeframe_min <= 0:
            return self._vap
        janela_ns = self._vap_timeframe_min * 60 * 1_000_000_000
        if not self._trades_vap_recentes:
            return VolumeProfile()
        agora_ns = self._trades_vap_recentes[-1][0]
        limite = agora_ns - janela_ns
        trades = (
            Trade(timestamp_ns=ts, symbol="", price=preco, qty=qtd,
                 side_agressor=agressor, trade_id="")
            for ts, preco, qtd, agressor in self._trades_vap_recentes
            if ts >= limite
        )
        return VolumeProfile.de_trades(trades)

    def _congelar_vap(
        self, perfil: VolumeProfile | None = None, top_n: int = 120
    ) -> tuple[tuple[int, int, int, int, bool], ...]:
        """Congela ate `top_n` niveis do VAP em tuplas planas (retencao
        limitada — `VolumeProfile` e objeto vivo, uma regiao NUNCA pode
        reter referencia a ele).

        (preco, volume_total, volume_comprador, volume_vendedor,
        e_destacado). "e_destacado" = esta entre os `N_NIVEIS_DESTACADOS`
        de maior volume do perfil inteiro — os outros sao "lixo" na
        linguagem da fonte, mostrados apagados, nunca escondidos (a fonte
        e explicita: nao existe filtro que apague o nivel, so que reduz a
        importancia visual dele). O criterio de SELECAO do autor para
        quais 3 destacar continua AUSENTE NA FONTE al'em de "volume"; aqui
        e literalmente o volume total do nivel, rotulado como proxy.
        """

        niveis = (perfil if perfil is not None else self._perfil_vap_ativo()).niveis_ordenados()
        por_volume = sorted(niveis, key=lambda kv: kv[1].volume_total, reverse=True)
        destacados = {preco for preco, _ in por_volume[: self.N_NIVEIS_DESTACADOS]}
        recortados = por_volume[:top_n]
        saida = [
            (preco, nivel.volume_total, nivel.volume_comprador, nivel.volume_vendedor,
             preco in destacados)
            for preco, nivel in recortados
        ]
        saida.sort(key=lambda item: item[0])
        return tuple(saida)

    def _agregador_candles_atual(self) -> CandleTemporal:
        return self._candles_15m if self._timeframe_candles_min == 15 else self._candles_m15

    def _alternar_nexo_ai(self) -> None:
        self._nexo_ai_ativo = not self._nexo_ai_ativo
        self.marcar_tudo_sujo()

    def _abrir_detalhes_nexo_ai(self) -> None:
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout
        from fluxopro.ui.paineis.nexo import assistente

        # Um único diálogo, reaberto com o quadro atual. É explicitamente uma
        # captura congelada; não mantém ponte para feed nem temporizador.
        if self._dialogo_nexo_ai is None:
            dialogo = QDialog(self)
            dialogo.setWindowTitle("NEXO AI · Procedência e condições · snapshot congelado")
            dialogo.resize(780, 600)
            layout = QVBoxLayout(dialogo)
            texto = QPlainTextEdit(dialogo)
            texto.setReadOnly(True)
            texto.setObjectName("nexo_ai_auditoria")
            texto.setAccessibleName("Dados e condições do snapshot NEXO AI")
            layout.addWidget(texto)
            self._dialogo_nexo_ai = dialogo
        texto = self._dialogo_nexo_ai.findChild(QPlainTextEdit, "nexo_ai_auditoria")
        texto.setPlainText(assistente.texto_auditoria(self._estado_nexo()))
        self._dialogo_nexo_ai.show()
        self._dialogo_nexo_ai.raise_()

    def _retangulo_candles(self) -> QRect | None:
        """Mesmo calculo de `desenhar()` para a regiao "candles" — reaproveitado
        pelos handlers de mouse pra saber onde o clique/arrasto caiu, sem
        duplicar a logica de `nexo.retangulos`."""

        largura, altura = self.width(), self.height()
        if largura < 420 or altura < 180:
            return None
        quadro = QRect(0, 0, largura, max(1, altura - nexo.ALTURA_RESSALVA))
        return nexo.retangulos(quadro).get("candles")

    def _retangulo_ladder(self) -> QRect | None:
        largura, altura = self.width(), self.height()
        if largura < 420 or altura < 180:
            return None
        quadro = QRect(0, 0, largura, max(1, altura - nexo.ALTURA_RESSALVA))
        return nexo.retangulos(quadro).get("ladder")

    def mousePressEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()

        if self._nexo_ai_ativo:
            from fluxopro.ui.paineis.nexo import assistente

            quadro = QRect(0, 0, self.width(), max(1, self.height() - nexo.ALTURA_RESSALVA))
            central = assistente.caixas_integradas(quadro)["assistente"]
            if assistente.retangulos_internos(central)["detalhes"].contains(pos):
                self._abrir_detalhes_nexo_ai()
                evento.accept()
                return

        caixa_ladder = self._retangulo_ladder()
        if caixa_ladder is not None:
            modulo_ladder = nexo.modulo("ladder")
            # Selecao DIRETA do timeframe pelo seletor de tres segmentos no
            # topo do VAP (SESSAO/5M/15M). O rodape continua ciclando, como
            # antes — o seletor so tira o filtro do escuro.
            for minutos, caixa_seg in modulo_ladder.retangulos_timeframe(caixa_ladder).items():
                if caixa_seg.contains(pos):
                    if self._vap_timeframe_min != minutos:
                        self._vap_timeframe_min = minutos
                        self.marcar_tudo_sujo()
                    evento.accept()
                    return
            if modulo_ladder.retangulo_rotulo(caixa_ladder).contains(pos):
                self._vap_timeframe_min = {0: 5, 5: 15, 15: 0}[self._vap_timeframe_min]
                self.marcar_tudo_sujo()
                evento.accept()
                return

        caixa = self._retangulo_candles()
        if caixa is None or not caixa.contains(pos):
            super().mousePressEvent(evento)
            return
        modulo_candles = nexo.modulo("candles")
        barra_controles = QRect(caixa.left(), caixa.top() + 14, caixa.width(),
                                modulo_candles.ALTURA_BARRA_CONTROLES)
        controles = modulo_candles.retangulos_controles(barra_controles)
        if controles["timeframe"].contains(pos):
            self._timeframe_candles_min = 15 if self._timeframe_candles_min == 5 else 5
            self._candles_offset = 0
            self.marcar_tudo_sujo()
            evento.accept()
            return
        if controles["agora"].contains(pos) and modulo_candles.escala_fora_do_automatico(
                self._estado_nexo()):
            self._voltar_escala_ao_automatico()
            evento.accept()
            return
        # ESCALA ARRASTAVEL (pedido do operador, 27/08/2026): pegar o eixo de
        # PRECO (calha da direita) e arrastar na vertical comprime/expande a
        # escala de preco; pegar a escala de TEMPO (rodape) e arrastar na
        # horizontal muda quantas velas cabem na janela. E o gesto do Profit:
        # o eixo e a alavanca, o miolo do grafico continua sendo pan.
        if modulo_candles.retangulo_eixo_preco(caixa).contains(pos):
            self._arrasto_escala = "preco"
            self._arrasto_escala_y0 = pos.y()
            self._arrasto_escala_base = self._candles_zoom_preco
            evento.accept()
            return
        if modulo_candles.retangulo_eixo_tempo(caixa).contains(pos):
            self._arrasto_escala = "tempo"
            self._arrasto_escala_x0 = pos.x()
            self._arrasto_escala_base = float(self._velas_visiveis_efetivas(caixa))
            evento.accept()
            return
        self._arrasto_candles_ativo = True
        self._arrasto_candles_x0 = pos.x()
        self._arrasto_candles_offset0 = self._candles_offset
        evento.accept()

    def _atualizar_cursor_candles(self, evento) -> bool:
        """Estado do crosshair. Devolve True quando o evento foi consumido
        (cursor dentro do grafico) — fora dali o painel nem se suja.

        Custo por quadro: so marca sujo quando o cursor muda de VELA ou anda
        pelo menos 2px na vertical. Varrer o grafico com o mouse nao vira um
        repaint por pixel.
        """

        pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
        caixa = self._retangulo_candles()
        if caixa is None or not caixa.contains(pos):
            if self._cursor_candles is not None:
                self._cursor_candles = None
                self.marcar_tudo_sujo()
            return False
        modulo_candles = nexo.modulo("candles")
        novo = (pos.x(), pos.y())
        anterior = self._cursor_candles
        if anterior is not None:
            estado = self._estado_nexo()
            mesma_vela = (modulo_candles.indice_vela_em(caixa, estado, novo[0])
                          == modulo_candles.indice_vela_em(caixa, estado, anterior[0]))
            if mesma_vela and abs(novo[1] - anterior[1]) < 2:
                return True
        self._cursor_candles = novo
        self.marcar_tudo_sujo()
        return True

    def leaveEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        """Cursor saiu do widget: o crosshair some. Sem isto ele congelaria
        no ultimo ponto e o operador leria uma vela que nao esta apontando."""

        if self._cursor_candles is not None:
            self._cursor_candles = None
            self.marcar_tudo_sujo()
        super().leaveEvent(evento)

    def _voltar_escala_ao_automatico(self) -> None:
        """Desfaz TODO ajuste manual da vista de uma vez: volta ao presente,
        a janela do dia e a escala de preco neutra.

        Antes o chip so zerava `_candles_offset`; com o eixo ampliado em 4x,
        clicar nele nao mudava nada (medido em 28/08/2026: zoom 4,0 antes e
        depois, 85 das 116 velas fora da vista nos dois casos). Um controle
        que existe mas nao desfaz e pior que controle nenhum — e por isso o
        desenho e este metodo leem a MESMA `escala_fora_do_automatico`.
        """

        self._candles_offset = 0
        self._candles_velas_visiveis = None
        self._candles_zoom_preco = 1.0
        self.marcar_tudo_sujo()

    def mouseDoubleClickEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        """Duplo-clique no eixo de preco volta a escala ao automatico — o
        mesmo gesto do grafico de referencia, para quem procura no eixo
        antes de procurar no chip."""

        pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
        caixa = self._retangulo_candles()
        if caixa is not None and caixa.contains(pos):
            modulo_candles = nexo.modulo("candles")
            if (modulo_candles.retangulo_eixo_preco(caixa).contains(pos)
                    or modulo_candles.retangulo_eixo_tempo(caixa).contains(pos)):
                self._voltar_escala_ao_automatico()
                evento.accept()
                return
        super().mouseDoubleClickEvent(evento)

    def _total_candles_do_dia(self) -> int:
        """Quantas velas o dia REALMENTE tem no timeframe selecionado (as
        fechadas mais a em formacao). E este numero que dimensiona a janela
        padrao: um teto de relogio cortava as primeiras velas do pregao."""

        agregador = self._agregador_candles_atual()
        return len(agregador.candles_fechados) + (1 if agregador.candle_atual else 0)

    def _velas_visiveis_efetivas(self, caixa) -> int:
        """Quantas velas a janela mostra AGORA — inclusive quando o operador
        ainda nao mexeu na escala (`None` = a sessao inteira disponivel).
        Serve de ponto de partida do zoom, para o primeiro arrasto nao dar
        um salto."""

        modulo_candles = nexo.modulo("candles")
        return modulo_candles.slots_da_janela(
            caixa.width() if caixa is not None else 400,
            self._timeframe_candles_min, self._candles_velas_visiveis,
            self._total_candles_do_dia())

    def _aplicar_zoom_tempo(self, fator: float, caixa=None) -> None:
        """Multiplica o numero de velas visiveis. Menos velas = mais zoom."""

        modulo_candles = nexo.modulo("candles")
        caixa = caixa if caixa is not None else self._retangulo_candles()
        atual = self._velas_visiveis_efetivas(caixa)
        alvo = int(round(atual * fator))
        alvo = max(modulo_candles.VELAS_MIN, alvo)
        # O mesmo total usado pelo desenho define o teto. Um limite sem
        # total cortava o início de sessões longas ao pedir zoom-out.
        novo = modulo_candles.slots_da_janela(
            caixa.width() if caixa is not None else 400,
            self._timeframe_candles_min, alvo, self._total_candles_do_dia())
        if novo != self._candles_velas_visiveis:
            self._candles_velas_visiveis = novo
            self.marcar_tudo_sujo()

    def _aplicar_zoom_preco(self, fator: float) -> None:
        modulo_candles = nexo.modulo("candles")
        novo = max(modulo_candles.ZOOM_PRECO_MIN,
                   min(modulo_candles.ZOOM_PRECO_MAX, self._candles_zoom_preco * fator))
        if abs(novo - self._candles_zoom_preco) > 1e-6:
            self._candles_zoom_preco = novo
            self.marcar_tudo_sujo()

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        if self._arrasto_escala is not None:
            pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
            caixa = self._retangulo_candles()
            modulo_candles = nexo.modulo("candles")
            if self._arrasto_escala == "preco":
                # 120px de arrasto dobram (pra cima) ou reduzem a metade (pra
                # baixo) a escala — o gesto e continuo e reversivel, sem
                # degrau: solta e pega de novo de onde parou.
                dy = self._arrasto_escala_y0 - pos.y()
                fator = 2.0 ** (dy / 120.0)
                novo = max(modulo_candles.ZOOM_PRECO_MIN,
                           min(modulo_candles.ZOOM_PRECO_MAX,
                               self._arrasto_escala_base * fator))
                if abs(novo - self._candles_zoom_preco) > 1e-6:
                    self._candles_zoom_preco = novo
                    self.marcar_tudo_sujo()
            else:
                # Arrastar a escala de tempo pra ESQUERDA comprime (mais velas
                # na mesma largura); pra direita expande (menos velas, leitura
                # aberta de um trecho).
                dx = pos.x() - self._arrasto_escala_x0
                alvo = int(round(self._arrasto_escala_base * (2.0 ** (-dx / 200.0))))
                novo = modulo_candles.slots_da_janela(
                    caixa.width() if caixa is not None else 400,
                    self._timeframe_candles_min,
                    max(modulo_candles.VELAS_MIN, alvo),
                    self._total_candles_do_dia())
                if novo != self._candles_velas_visiveis:
                    self._candles_velas_visiveis = novo
                    self.marcar_tudo_sujo()
            evento.accept()
            return
        if not self._arrasto_candles_ativo:
            # Sem botao pressionado: e o CROSSHAIR. `setMouseTracking` vale
            # para o widget inteiro, entao o filtro de regiao mora aqui — o
            # cursor so vira estado (e so suja quadro) dentro da regiao de
            # candles. Passar por VAP, Renko, nucleo ou placar nao repinta
            # nada por causa do mouse.
            if self._atualizar_cursor_candles(evento):
                evento.accept()
                return
            super().mouseMoveEvent(evento)
            return
        pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
        caixa = self._retangulo_candles()
        modulo_candles = nexo.modulo("candles")
        # Passo do arrasto = largura de UM slot de tempo, a mesma conta que o
        # desenho usa (`candles.largura_slot_px`). Antes era uma estimativa
        # propria (largura // 11), que nao tinha relacao com a grade
        # realmente pintada: o grafico andava mais (ou menos) que o mouse.
        passo_px = max(3.0, modulo_candles.largura_slot_px(
            caixa.width() if caixa is not None else 400, self._timeframe_candles_min,
            self._candles_velas_visiveis, self._total_candles_do_dia()))
        dx = pos.x() - self._arrasto_candles_x0
        # Arrastar pra DIREITA revela velas mais ANTIGAS (convencao usual de
        # grafico: empurrar o grafico com o dedo/mouse pra direita "puxa" o
        # passado pra dentro da tela) — por isso o sinal positivo aqui.
        delta_velas = round(dx / passo_px)
        candles = self._agregador_candles_atual()
        total = len(candles.candles_fechados) + (1 if candles.candle_atual else 0)
        offset_maximo = max(0, total - modulo_candles.VELAS_MIN)
        novo_offset = max(0, min(offset_maximo, self._arrasto_candles_offset0 + delta_velas))
        if novo_offset != self._candles_offset:
            self._candles_offset = novo_offset
            self.marcar_tudo_sujo()
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        if self._arrasto_escala is not None:
            self._arrasto_escala = None
            evento.accept()
            return
        if self._arrasto_candles_ativo:
            self._arrasto_candles_ativo = False
            evento.accept()
            return
        super().mouseReleaseEvent(evento)

    def wheelEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        """Roda do mouse = zoom. Sobre a calha do eixo de preco, ela mexe na
        escala VERTICAL; em qualquer outro ponto do grafico, no numero de
        velas da janela (escala HORIZONTAL). Fora da regiao de candles, o
        evento segue para a base intocado."""

        caixa = self._retangulo_candles()
        pos = evento.position().toPoint() if hasattr(evento, "position") else evento.pos()
        delta = evento.angleDelta().y() if hasattr(evento, "angleDelta") else 0
        if caixa is None or not caixa.contains(pos) or not delta:
            super().wheelEvent(evento)
            return
        modulo_candles = nexo.modulo("candles")
        # Um "clique" de roda = 120 -> 1 passo de 15%. Composto, entao o gesto
        # e reversivel: subir e descer a mesma quantidade volta ao mesmo lugar.
        passos = delta / 120.0
        if modulo_candles.retangulo_eixo_preco(caixa).contains(pos):
            self._aplicar_zoom_preco(1.15 ** passos)
        else:
            self._aplicar_zoom_tempo(1.15 ** (-passos), caixa)
        evento.accept()

    def _estado_nexo(self) -> nexo.EstadoNexo:
        """Congela o quadro em um valor imutavel antes de qualquer pintura.

        Nenhuma regiao recebe o painel, o ``deque`` vivo ou o feed: ela ve
        exatamente este retrato e nada mais. Precos seguem ``int`` em ticks.
        """

        _perfil_vap = self._perfil_vap_ativo()
        estado = nexo.EstadoNexo(
            snapshot=self._snapshot,
            serie=tuple(self._serie),
            serie_forca_ai=tuple(self._serie_forca_ai),
            grid=self.grid,
            paleta=self.paleta,
            maker=self._linha_maker(),
            represado_s=self._volante_maker.segundos_represado(
                self._snapshot.timestamp_ns),
            leituras=self._linhas_contexto_nexo(),
            regime=self._linha_regime(),
            largura=self.width(),
            altura=self.height(),
            tijolos_renko=self._renko.tijolos,
            fase_renko=self._renko.fase,
            alvos_renko=self._renko.alvos(),
            renko_tamanho_ticks=self._renko.tamanho_tijolo_ticks,
            candles_m15=self._agregador_candles_atual().candles_fechados
            + ((self._agregador_candles_atual().candle_atual,)
               if self._agregador_candles_atual().candle_atual else ()),
            candles_timeframe_min=self._timeframe_candles_min,
            candles_offset=self._candles_offset,
            candles_cursor=self._cursor_candles,
            candles_velas_visiveis=self._candles_velas_visiveis,
            candles_zoom_preco=self._candles_zoom_preco,
            vap_niveis=self._congelar_vap(_perfil_vap),
            vap_poc=_perfil_vap.poc,
            vap_timeframe_min=self._vap_timeframe_min,
            # Value area do perfil ATIVO, nao mais do perfil de sessao: com o
            # filtro em 5M/15M o VAL/VAH vinha da sessao inteira e contradizia
            # as barras desenhadas ao lado dele (defeito achado ao alargar o
            # VAP em 27/08/2026).
            vap_val=_perfil_vap.val(),
            vap_vah=_perfil_vap.vah(),
            vap_volume_total=_perfil_vap.volume_total,
            risco_volatilidade=self._risco_volatilidade(),
            alerta_exaustao=self._alerta_exaustao(),
            sinal_ultra=self._ultimo_sinal_ultra,
        )
        estado = dataclass_replace(estado, sr_snapshot=self._calcular_sr_snapshot(estado))
        estado = dataclass_replace(
            estado, dominancia_snapshot=self._calcular_dominancia_snapshot(estado))
        # A analise entra por ULTIMO: ela le dominancia e S/R ja publicados,
        # entao fala dos mesmos numeros que a tela mostra.
        return dataclass_replace(estado, analise_ia=self._pacote_analise(estado))

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        """Aloca retangulos e delega. Este metodo nao pinta conteudo.

        A composicao e continua e sangra ate as quatro bordas: nao ha cabecalho
        de cromo comendo o topo, nao ha margem externa e nao ha moldura de
        cartao entre regioes. O unico pixel reservado e a linha de ressalva do
        rodape, que por contrato de projeto nao pode desaparecer.
        """

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(regiao, tema_asg.NEXO_FUNDO)
        largura, altura = self.width(), self.height()
        if largura < 420 or altura < 180:
            painter.setFont(tokens.fonte_ui(11, QFont.Weight.DemiBold))
            painter.setPen(tema_asg.NEXO_TEXTO)
            painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter,
                             "NEXO · REDIMENSIONE A JANELA")
            return

        estado = self._estado_nexo()
        quadro = QRect(0, 0, largura, max(1, altura - nexo.ALTURA_RESSALVA))
        from fluxopro.ui.paineis.nexo import assistente

        caixas = (assistente.caixas_integradas(quadro) if self._nexo_ai_ativo
                  else nexo.retangulos(quadro))

        # Amarracao de escala entre duas regioes vizinhas: o Renko ("forca")
        # tem de desenhar na MESMA escala vertical do grafico de velas logo
        # abaixo ("candles"), senao o olho compara amplitudes falsas entre uma
        # e outra (achado do operador, 27/08/2026). Este e o unico ponto do
        # codigo que conhece os retangulos das DUAS regioes — as regioes
        # continuam funcoes puras, sem uma enxergar a outra. A medida vem da
        # funcao pura de `candles`, nunca de uma copia da formula.
        estado = dataclass_replace(
            estado,
            escala_candle_px_por_tick=nexo.modulo("candles").px_por_tick(
                caixas["candles"], estado),
        )
        for nome in nexo.ORDEM_DESENHO:
            if self._nexo_ai_ativo and nome in {"nucleo", "vies"}:
                continue
            painter.save()
            try:
                # Isolar a região inclui a sangria de antialiasing: o núcleo
                # clássico não pode alterar pixels do gráfico ao alternar F7.
                painter.setClipRect(caixas[nome], Qt.ClipOperation.IntersectClip)
                if self._nexo_ai_ativo and nome == "banner":
                    assistente.desenhar_resumo(painter, caixas[nome], estado)
                else:
                    nexo.modulo(nome).desenhar(painter, caixas[nome], estado)
            finally:
                painter.restore()

        if self._nexo_ai_ativo:
            assistente.desenhar(painter, caixas["assistente"], estado)

        # Camada de honestidade: no-op quando o quadro esta saudavel
        # (`diagnosticar` devolve None), e um veu+cartao nomeando o que
        # esta contaminado quando nao esta — nunca fabrica leitura sobre
        # dado que a fonte nao tem. Desenhada por cima de tudo, de
        # proposito: e a ultima palavra sobre o quadro, nao uma regiao a
        # mais competindo por atencao.
        #
        # Import tardio (mesmo motivo do `nexo.modulo()`): indisponivel.py
        # importa `asg` de volta para os enums de estado, e nao esta em
        # `ORDEM_DESENHO` porque nao e uma regiao espacial, e sim uma
        # camada que cobre todas elas.
        from fluxopro.ui.paineis.nexo import indisponivel as nexo_indisponivel

        painter.save()
        try:
            nexo_indisponivel.desenhar(painter, quadro, estado)
        finally:
            painter.restore()

        self._ressalva(painter, QRect(0, quadro.bottom() + 1, largura,
                                      nexo.ALTURA_RESSALVA))

    def _ressalva(self, painter: QPainter, rect: QRect) -> None:
        """Declaracao permanente: superficie consultiva, sem envio de ordens."""

        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(rect.adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "DADOS OBSERVADOS · DERIVACOES ROTULADAS · SEM ENVIO DE ORDENS")
        painter.setPen(tema_asg.NEXO_CIANO)
        painter.drawText(rect.adjusted(4, 0, -4, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         "NEXO v1 · PROXY INDEPENDENTE")

    def _linhas_contexto_nexo(self) -> tuple[tuple[str, LinhaMatrizASG], ...]:
        """Quatro leituras curtas para o bloco de contexto, sem nova regra."""

        apelidos = {
            "MACRO": "HORIZONTE",
            "MICRO": "PULSO",
            "MAKERPROXY": "PRESENCA",
            "VELOCIMETRO": "RITMO",
        }
        saida = []
        for linha in self._snapshot.matriz.linhas:
            apelido = apelidos.get(linha.componente)
            if apelido is None:
                continue
            if linha.componente == "MAKERPROXY":
                linha = self._linha_maker_coerente(linha)
            # Portao unico: NENHUMA das quatro leituras chega a tela sem
            # passar por aqui. Ate 28/08/2026 so o REGIME era conferido, e
            # HORIZONTE/PULSO/PRESENCA/RITMO desenhavam direto — justamente
            # as quatro em que a familia de defeitos ja nasceu duas vezes.
            saida.append((apelido, _coerir_leitura(linha)))
        return tuple(saida[:4])

    def _caixa_nexo(self, painter: QPainter, rect: QRect, titulo: str) -> QRect:
        painter.fillRect(rect, tema_asg.PAINEL)
        painter.setPen(tema_asg.BORDA)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setFont(tokens.fonte_rotulo(9))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(rect.adjusted(7, 0, -7, -rect.height() + 18),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo)
        return rect.adjusted(7, 21, -7, -6)

    def _desenhar_pressao(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa_nexo(painter, rect, "PRESSAO INSTITUCIONAL · PROXY")
        maker = self._linha_maker()
        direcao = maker.direcao if maker is not None else DirecaoASG.NEUTRA
        forca = maker.forca if maker is not None else 0.0
        cor = _cor_direcao(direcao, self.paleta)
        centro = QPoint(area.center().x(), area.y() + max(38, area.height() // 3))
        raio = max(22, min(area.width() // 4, area.height() // 6))
        painter.setPen(tema_asg.BORDA_FORTE)
        painter.drawEllipse(centro, raio + 8, raio + 8)
        painter.setPen(cor)
        painter.drawEllipse(centro, raio, raio)
        painter.setFont(tokens.fonte_numero(max(12, min(24, raio // 2 + 8)), QFont.Weight.Bold))
        painter.drawText(QRect(centro.x() - raio, centro.y() - 14, 2 * raio, 28),
                         Qt.AlignmentFlag.AlignCenter, f"{forca * 100:+.0f}%")
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(area.x(), centro.y() + raio + 8, area.width(), 16),
                         Qt.AlignmentFlag.AlignCenter,
                         "COMPRA" if direcao is DirecaoASG.COMPRA else
                         "VENDA" if direcao is DirecaoASG.VENDA else "EQUILIBRIO")

        barra = QRect(area.x() + 4, area.bottom() - 66, max(1, area.width() - 8), 12)
        painter.fillRect(barra, tema_asg.FUNDO_NEUTRO)
        meio = barra.center().x()
        painter.setPen(tema_asg.BORDA_FORTE)
        painter.drawLine(meio, barra.top(), meio, barra.bottom())
        largura = int(abs(forca) * barra.width() / 2)
        if largura:
            x = meio + 1 if forca > 0 else meio - largura
            painter.fillRect(QRect(x, barra.y(), largura, barra.height()), cor)
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        cobertura = maker.detalhe if maker is not None else "SEM EVIDENCIA"
        painter.drawText(QRect(area.x(), barra.bottom() + 5, area.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, cobertura.upper())
        painter.setFont(tokens.fonte_ui(8))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(QRect(area.x(), area.bottom() - 22, area.width(), 14),
                         Qt.AlignmentFlag.AlignCenter, "OBSERVADO / INFERIDO DECLARADO")

    def _desenhar_sinal(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa_nexo(painter, rect, "NEXO · SINAL CONSULTIVO")
        decisao = self._snapshot.decisao
        direcao = decisao.direcao
        cor = _cor_direcao(direcao, self.paleta)
        cx, cy = area.center().x(), area.y() + max(42, area.height() // 3)
        raio = max(25, min(area.width() // 3, area.height() // 5))
        poligono = QPolygon([
            QPoint(cx - raio // 2, cy - raio), QPoint(cx + raio // 2, cy - raio),
            QPoint(cx + raio, cy), QPoint(cx + raio // 2, cy + raio),
            QPoint(cx - raio // 2, cy + raio), QPoint(cx - raio, cy),
        ])
        painter.setPen(tema_asg.BORDA_FORTE)
        painter.setBrush(tema_asg.FUNDO_NEUTRO)
        painter.drawPolygon(poligono)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setFont(tokens.fonte_numero(max(18, raio), QFont.Weight.Bold))
        painter.setPen(cor)
        simbolo = "▲" if direcao is DirecaoASG.COMPRA else "▼" if direcao is DirecaoASG.VENDA else "◆"
        painter.drawText(QRect(cx - raio, cy - raio // 2, 2 * raio, raio),
                         Qt.AlignmentFlag.AlignCenter, simbolo)
        painter.setFont(tokens.fonte_ui(9, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(QRect(area.x(), cy + raio + 8, area.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, decisao.titulo)
        painter.setFont(tokens.fonte_ui(8))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(QRect(area.x() + 4, cy + raio + 26, area.width() - 8, 32),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         decisao.motivo)
        y = area.bottom() - 41
        painter.setPen(tokens.ALERT)
        painter.setFont(tokens.fonte_rotulo(8))
        painter.drawText(QRect(area.x(), y, area.width(), 13), Qt.AlignmentFlag.AlignCenter,
                         "NAO ENVIA ORDENS")
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.setFont(tokens.fonte_numero(8))
        painter.drawText(QRect(area.x(), y + 16, area.width(), 13), Qt.AlignmentFlag.AlignCenter,
                         f"STOP {decisao.stop} · A1 {decisao.alvo_1}")

    def _desenhar_grafico(self, painter: QPainter, rect: QRect) -> None:
        area = self._caixa_nexo(painter, rect, "MAPA DE PRECO · FORCA DO FLUXO")
        faixa_forca = max(38, area.height() // 4)
        forca_rect = QRect(area.x(), area.y(), area.width(), faixa_forca)
        preco_rect = QRect(area.x(), forca_rect.bottom() + VAO, area.width(),
                           max(20, area.bottom() - forca_rect.bottom() - VAO + 1))
        painter.fillRect(forca_rect, tema_asg.FUNDO_NEUTRO)
        painter.fillRect(preco_rect, tema_asg.FUNDO_NEUTRO)
        painter.setPen(tema_asg.BORDA)
        painter.drawRect(forca_rect.adjusted(0, 0, -1, -1))
        painter.drawRect(preco_rect.adjusted(0, 0, -1, -1))
        self._desenhar_forca(painter, forca_rect)
        self._desenhar_trajeto_preco(painter, preco_rect)

    def _desenhar_forca(self, painter: QPainter, rect: QRect) -> None:
        amostras = tuple(self._serie)
        meio = rect.center().y()
        painter.setPen(tema_asg.BORDA_FORTE)
        painter.drawLine(rect.left(), meio, rect.right(), meio)
        if len(amostras) < 2:
            painter.setFont(tokens.fonte_ui(8))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO FORCA DO FLUXO")
            return
        pontos = []
        for indice, (_, _, forca, _) in enumerate(amostras):
            x = rect.left() + round(indice * max(1, rect.width() - 1) / max(1, len(amostras) - 1))
            y = meio - round(forca * max(1, rect.height() // 2 - 7))
            pontos.append(QPoint(x, y))
        painter.setPen(_cor_direcao(_direcao_de_score(amostras[-1][2]), self.paleta))
        painter.drawPolyline(QPolygon(pontos))
        ultimo = amostras[-1][2]
        painter.setFont(tokens.fonte_numero(9, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(rect.adjusted(6, 2, -6, -2),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         f"FORCA {ultimo * 100:+.0f}%")
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(rect.adjusted(6, 2, -6, -2),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         "DELTA / VOLUME")

    def _desenhar_trajeto_preco(self, painter: QPainter, rect: QRect) -> None:
        amostras = tuple(self._serie)
        if len(amostras) < 2:
            painter.setFont(tokens.fonte_ui(9, QFont.Weight.DemiBold))
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO TRAJETO DE PRECO")
            return
        precos = [item[1] for item in amostras]
        minimo, maximo = min(precos), max(precos)
        amplitude = max(1, maximo - minimo)
        for fracao in (0.25, 0.50, 0.75):
            y = rect.top() + round(rect.height() * fracao)
            painter.setPen(tema_asg.BORDA)
            painter.drawLine(rect.left(), y, rect.right(), y)
        pontos = []
        for indice, (_, preco, _, _) in enumerate(amostras):
            x = rect.left() + round(indice * max(1, rect.width() - 1) / max(1, len(amostras) - 1))
            y = rect.bottom() - round((preco - minimo) * max(1, rect.height() - 18) / amplitude) - 8
            pontos.append(QPoint(x, y))
        direcao = _direcao_de_score(amostras[-1][2])
        painter.setPen(_cor_direcao(direcao, self.paleta))
        painter.drawPolyline(QPolygon(pontos))
        ultimo_preco = formato.formatar_preco(self.grid, precos[-1])
        painter.setFont(tokens.fonte_numero(10, QFont.Weight.DemiBold))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(rect.adjusted(6, 4, -6, -4),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         f"PRECO {ultimo_preco[0]}{ultimo_preco[1]}")
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(rect.adjusted(6, 4, -6, -4),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                         "OBSERVADO · JANELA LIMITADA")
        # Escala e tempo tornam a trajetória auditável como gráfico, em vez
        # de uma linha decorativa. Não há OHLC neste contrato: os marcadores
        # declaram que se trata de preço observado por evento.
        preco_min = formato.formatar_preco(self.grid, minimo)
        preco_max = formato.formatar_preco(self.grid, maximo)
        inicio = formato.formatar_hora_ns(amostras[0][0])
        fim = formato.formatar_hora_ns(amostras[-1][0])
        painter.setFont(tokens.fonte_numero(8))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(rect.adjusted(6, 4, -6, -4),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                         f"MAX {preco_max[0]}{preco_max[1]}")
        painter.drawText(rect.adjusted(6, 4, -6, -4),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         f"{inicio} → {fim}")
        painter.drawText(QRect(rect.right() - 70, rect.center().y() - 7, 66, 14),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"MIN {preco_min[0]}{preco_min[1]}")
        niveis = ("STOP", "A1", "A2", "A3")
        valores = (
            self._snapshot.decisao.stop, self._snapshot.decisao.alvo_1,
            self._snapshot.decisao.alvo_2, self._snapshot.decisao.alvo_3,
        )
        painter.setFont(tokens.fonte_numero(8))
        for indice, (nome, valor) in enumerate(zip(niveis, valores)):
            if valor == "—":
                continue
            y = rect.bottom() - 15 - indice * 14
            painter.setPen(tokens.ALERT if nome == "STOP" else tema_asg.MATRIZ)
            painter.drawLine(rect.left() + 4, y, rect.right() - 58, y)
            painter.drawText(QRect(rect.right() - 54, y - 7, 52, 14),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{nome} {valor}")


class WorkspaceASG(QWidget):
    """Composto responsivo pronto para ser inserido pela janela central.

    DOM, Tape e Bookmap sao as implementacoes operacionais reais, alimentadas
    pelo mesmo ``Instantaneo`` que abastece as docas historicas. Instancias
    dedicadas evitam reparentear docas e preservam os quatro workspaces
    anteriores. Os cinco paineis ASG continuam consumindo um unico snapshot.
    """

    LIMIAR_LARGO = 1120
    LIMIAR_MEDIO = 720

    def __init__(self, parent: QWidget | None = None,
                 paleta: tokens.Paleta = tokens.PALETA_COR,
                 grid: PriceGrid = WDO_GRID, symbol: str = "",
                 densidade: tokens.Densidade = tokens.PADRAO,
                 timeframe_ns: int = 60_000_000_000) -> None:
        super().__init__(parent)
        # O composto e a superficie operacional inteira no Ctrl+5. ``Ignored``
        # impede que um sizeHint de desktop force a janela a crescer quando o
        # Qt ainda esta resolvendo a antiga arvore de docas durante a troca.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.nexo = PainelNexoMercadoASG(self, grid, paleta)
        self.cockpit = PainelCockpit(self)
        self.placar_visual = PainelPlacarVisual(self)
        self.pressao_visual = PainelPressaoMercado(self)
        self.marca_operador = PainelMarcaOperador(self)
        self.grafico = PainelGrafico(grid, timeframe_ns, self)
        self.mini_tape = PainelMiniTape(self)
        self.contexto_bruto = PainelContextoBrutoASG(self, grid)
        self.dados = PainelDadosASG(self)
        self.processamento = PainelProcessamentoASG(self)
        self.matriz = PainelMatrizASG(self, paleta)
        self.decisao = PainelDecisaoASG(self, paleta)
        self.evidencias = PainelEvidenciasASG(self)
        self.dom = PainelDOM(grid, self, densidade=densidade, paleta=paleta)
        self.tape = PainelTape(grid, self, densidade=densidade, paleta=paleta)
        self.bookmap = PainelBookmap(
            grid,
            symbol=symbol,
            parent=self,
            densidade=densidade,
            paleta=paleta,
            # O Bookmap do workspace compartilha uma faixa horizontal menor
            # que o painel dedicado. Em 500 ms ele mostrava apenas poucos
            # blocos na borda e desperdicava o contexto que a tela prometia.
            # 250 ms preserva a semantica de balde e dobra a historia visivel
            # sem alterar o Bookmap dos workspaces legados.
            intervalo_coluna_ns=250_000_000,
        )
        for painel in (self.dom, self.tape, self.bookmap):
            painel.setMinimumSize(0, 0)
            painel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.paineis = (self.nexo, self.contexto_bruto, self.dados, self.processamento,
                        self.matriz, self.decisao, self.evidencias)
        self.paineis_contexto = (self.dom, self.tape, self.bookmap)
        self.paineis_extras = (
            self.cockpit, self.placar_visual, self.pressao_visual,
            self.marca_operador, self.grafico, self.mini_tape,
        )
        # NEXO, tal como o antigo Pulso, tem um ciclo visual próprio: recebe
        # o retrato de mercado e desenha no próximo quadro Qt. Não o incluímos
        # neste contrato de hidratação síncrona para não exigir geometria já
        # resolvida durante Ctrl+5 (a janela ainda pode estar oculta).
        self.todos_paineis = self.paineis_contexto + (
            self.dados, self.processamento, self.matriz,
            self.decisao, self.evidencias,
        ) + self.paineis_extras
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._snapshot: WorkspaceASGSnapshot | None = None
        self._modo = ""
        # Ctrl+5 pode ocorrer antes do primeiro tick. Entregar o retrato
        # bloqueado e legivel evita expor a area operacional como quadro vazio.
        self.aplicar(WorkspaceASGSnapshot(
            0,
            DadosASGSnapshot(0),
            ProcessamentoASGSnapshot(0),
            MatrizASGSnapshot(0),
            DecisaoASGSnapshot(0),
            TrilhaEvidenciasASGSnapshot(0),
            contexto_bruto=ContextoBrutoASGSnapshot(0),
        ))
        self._reorganizar(force=True)

    @property
    def modo_layout(self) -> str:
        return self._modo

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(960, 540)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # A responsividade e decidida pela geometria efetiva, nao por um piso
        # capaz de redimensionar permanentemente a janela hospedeira.
        return QSize(0, 0)

    def aplicar(self, snapshot: WorkspaceASGSnapshot) -> None:
        """Aplica exatamente um snapshot tipado e coerente por quadro."""

        if not isinstance(snapshot, WorkspaceASGSnapshot):
            raise TypeError("WorkspaceASG.aplicar exige WorkspaceASGSnapshot tipado")
        self._snapshot = snapshot
        self.nexo.aplicar(snapshot)
        self.cockpit.aplicar(snapshot)
        self.placar_visual.aplicar(snapshot)
        self.marca_operador.aplicar(snapshot)
        self.contexto_bruto.aplicar(snapshot.contexto_bruto or ContextoBrutoASGSnapshot(
            snapshot.timestamp_ns,
            estado=snapshot.estado_operacional or snapshot.dados.estado,
            detalhe="CONTEXTO BRUTO INDISPONIVEL NESTE QUADRO",
        ))
        self.dados.aplicar(snapshot.dados)
        self.processamento.aplicar(snapshot.processamento)
        self.matriz.aplicar(snapshot.matriz)
        self.decisao.aplicar(snapshot.decisao)
        self.evidencias.aplicar(snapshot.evidencias)

    def aplicar_mercado(self, retrato: Instantaneo) -> None:
        """Distribui um unico retrato da ponte aos tres paineis reais."""

        if not isinstance(retrato, Instantaneo):
            raise TypeError("WorkspaceASG.aplicar_mercado exige Instantaneo tipado")
        self.dom.aplicar(retrato.livro, retrato.ultimo_preco)
        self.tape.aplicar(retrato.novos_trades)
        self.bookmap.aplicar(
            retrato.livro, retrato.ultimo_preco, retrato.novos_trades
        )
        self.grafico.aplicar(retrato.novos_trades, ultimo_preco=retrato.ultimo_preco)
        self.mini_tape.aplicar(retrato.novos_trades, retrato.ultimo_preco)
        compra = sum(int(item.qty) for item in retrato.novos_trades if item.agressor > 0)
        venda = sum(int(item.qty) for item in retrato.novos_trades if item.agressor < 0)
        self.pressao_visual.aplicar(compra, venda, bool(compra or venda))
        self.nexo.aplicar_mercado(retrato)

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._reorganizar()

    def _reorganizar(self, force: bool = False) -> None:
        largura = self.width()
        modo = ("largo" if largura >= self.LIMIAR_LARGO else
                "medio" if largura >= self.LIMIAR_MEDIO else "estreito")
        if modo == self._modo and not force:
            # O ajuste de altura roda em QUALQUER modo. Ate 31/08/2026 so
            # o modo "largo" reajustava, entao numa janela estreita ou
            # media uma mudanca so de ALTURA (maximizar, arrastar a borda
            # de baixo) nao mexia em stretch nenhum e o painel ficava com
            # a altura antiga.
            self._ajustar_altura_larga()
            return
        self._modo = modo
        for painel in self.paineis + self.paineis_contexto + self.paineis_extras:
            self._layout.removeWidget(painel)
            # O workspace ASG agora e uma superficie autoral unica. Os
            # paineis tecnicos permanecem filhos vivos, com snapshot e
            # backing atualizados, mas nao contaminam a composicao visual.
            # Eles continuam disponiveis nos workspaces Ctrl+1..4.
            # Tamanho funcional fora do viewport: textos_visiveis(),
            # virtualizacao e backings continuam exercitando os contratos
            # antigos, enquanto a coordenada negativa impede qualquer
            # pixel do painel tecnico de aparecer sobre a composicao NEXO.
            painel.setGeometry(QRect(-10000, -10000,
                                     max(800, self.width()),
                                     max(240, self.height())))
            painel.show()
        for indice in range(8):
            self._layout.setRowStretch(indice, 0)
            self._layout.setColumnStretch(indice, 0)
        # O NEXO ocupa todo o quadro em qualquer breakpoint. A leitura dos
        # frames de referencia e uma composicao unica, e nao uma faixa em
        # cima da grade antiga. O modo continua registrado para manter a
        # responsividade/testes e para o proprio painel adaptar tipografia.
        self._layout.addWidget(self.nexo, 0, 0, 1, 1)
        self._layout.setColumnStretch(0, 1)
        self._layout.setRowStretch(0, 1)
        self.nexo.raise_()

    def _ajustar_altura_larga(self) -> None:
        """Toda a altura do workspace vai para a superficie NEXO.

        DEFEITO CORRIGIDO EM 31/08/2026 (relatado pelo operador: "a
        interface nao ocupa a tela inteira, somente uma parte").

        Esta funcao distribuia a altura em QUATRO faixas, com pesos
        ``(9, 2, 2, 1)``, de quando o workspace era uma grade: NEXO em
        cima e matriz / DOM-Tape-Bookmap / trilha nas linhas de baixo.
        Essas faixas deixaram de existir — `_reorganizar` manda todos os
        paineis tecnicos para ``(-10000, -10000)`` e monta o NEXO sozinho
        em ``(0, 0, 1, 1)``. As linhas 1..3 ficaram VAZIAS mas continuaram
        consumindo 5 de 14 do stretch, e o Qt reservou 36% da altura para
        widget nenhum.

        Medido na tela do operador (1536x816): workspace com 763px e
        NEXO com 491 — exatamente ``763 * 9/14`` — e 272px de campo preto
        embaixo. Como o NEXO e a unica coisa posicionada no grid, a linha
        0 leva tudo e as demais vao a zero.
        """

        self._layout.setRowStretch(0, 1)
        for linha in range(1, 8):
            self._layout.setRowStretch(linha, 0)


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


def _sem_zero_negativo(forca: float) -> float:
    """`-0.0` vira `0.0`. CONFIRMADO — regra do proprio painel: zero nao tem lado.

    `f"{-0.0:+.0f}%"` imprime `-0%`: um sinal de VENDA em cima de uma leitura
    que e exatamente zero e que ja esta pintada de NEUTRA. O defeito foi
    consertado uma vez, LOCALMENTE, no RITMO (`_forca_ritmo_composta`) — e
    sobreviveu no MakerProxy, saindo por tres portas ao mesmo tempo no
    retrato de 28/08: `-0%` no mostrador EQUILIBRIO, `-0%` no ladrilho
    PRESENCA e `-0% MM5` no texto pequeno. E a mesma familia de "grandeza e
    sinal viajando separados", so que na casa decimal.

    O corte e o MESMO de `_direcao_de_score`, de proposito: so zera o que a
    direcao ja declarou NEUTRA. Uma leitura de -0,4% continua saindo com o
    sinal dela — isto nao e um deadband novo, e a remocao do sinal de um
    zero.
    """

    return 0.0 if _direcao_de_score(forca) is DirecaoASG.NEUTRA else forca


def _linha_com_forca(linha: LinhaMatrizASG, forca: float) -> LinhaMatrizASG:
    """Troca a forca de uma leitura e RE-DERIVA tudo que carrega o sinal.

    Regra estrutural deste painel (28/08/2026): **grandeza e sinal nunca
    viajam separados**. Uma `LinhaMatrizASG` publica o mesmo numero por
    tres portas — `forca` (o numero grande do ladrilho), `direcao` (de onde
    saem a COR e o rotulo COMPRA/VENDA em toda regiao do NEXO) e `valor`
    (o texto pequeno da lista de contexto) — e cada consumidor le uma delas
    sem falar com os outros.

    O defeito que isso conserta: a suavizacao do MakerProxy trocava so a
    `forca`, e `direcao`/`valor` continuavam vindos do score CRU. Resultado
    na tela, com o cru em -0,33 e a media movel em +0,73: a lista de
    contexto dizia "PRESENCA -33%", o ladrilho imprimia "+73%" em vermelho
    com "-33%" embaixo, o gauge EQUILIBRIO desenhava "+73%" rotulado VENDA,
    e a barra do rodape desenhava "73% COMPRA" em verde. Quatro leituras
    do MESMO numero, com dois sinais.

    O mesmo defeito ja havia aparecido no RITMO (numero alto ao lado do
    rotulo DESACELERANDO) e foi consertado la de forma local — por isso
    renasceu. Aqui ele e fechado na origem: qualquer recalculo de forca
    tem de passar por esta funcao, que devolve a linha inteira coerente.

    `valor` passa a declarar `SUAV` quando o numero e suavizado, para que o
    texto pequeno nao seja confundido com o score cru do instante. O sufixo
    era `MM5` ate 28/08/2026, quando a media movel de 5 amostras foi
    substituida pelo `VolanteGauge` (inercia em tempo + escala relativa ao
    periodo); o rotulo deixou de nomear a janela justamente porque nomear o
    mecanismo no rosto do numero foi o que deixou a tela mentindo sobre a
    formula quando a formula mudou.
    """

    forca = _sem_zero_negativo(forca)
    return dataclass_replace(
        linha,
        forca=forca,
        direcao=_direcao_de_score(forca),
        valor=f"{forca * 100:+.0f}% SUAV",
    )


def sinal_da_leitura(linha: LinhaMatrizASG) -> int:
    """`-1`, `0` ou `+1` — o sinal UNICO de uma leitura.

    E o contrato que cor, rotulo COMPRA/VENDA, numero impresso e barra do
    rodape tem de respeitar juntos. Existe para ser verificavel por teste,
    nao so por inspecao visual.
    """

    if linha.direcao is DirecaoASG.COMPRA:
        return 1
    if linha.direcao is DirecaoASG.VENDA:
        return -1
    return 0


def leitura_e_coerente(linha: LinhaMatrizASG) -> bool:
    """A `forca` impressa e a `direcao` que pinta apontam para o mesmo lado?

    **Zero nao tem lado, e por isso zero tambem nao pode ser pintado.** Ate
    28/08/2026 esta funcao devolvia `True` incondicionalmente para forca
    zero, o que deixava passar uma linha com `forca 0.0` e
    `direcao=COMPRA` — na tela, um ladrilho VERDE com "+0%" escrito, que e
    exatamente o tipo de contradicao que esta disciplina existe para
    impedir (o caso real: VELOCIMETRO com `sentido` definido mas estado
    PARADO). Agora forca zero exige direcao NEUTRA/AGUARDAR.

    A regra completa, entao: `_direcao_de_score(linha.forca)` tem de ser
    IGUAL a `linha.direcao`, com AGUARDAR aceito no lugar de NEUTRA (e um
    estado de espera declarado, nao um lado).
    """

    sinal_forca = _direcao_de_score(linha.forca)
    if sinal_forca is DirecaoASG.NEUTRA:
        return linha.direcao in (DirecaoASG.NEUTRA, DirecaoASG.AGUARDAR)
    return linha.direcao is sinal_forca


def _coerir_leitura(linha: LinhaMatrizASG) -> LinhaMatrizASG:
    """Portao de producao: nenhuma leitura direcional chega a tela sem
    passar por aqui.

    **O que eu escolhi e por que.** Havia duas saidas para uma linha
    reprovada pelo invariante:

    * *barrar* (nao desenhar), como o REGIME faz — mas isso **apagaria
      leitura legitima da tela**. Um HORIZONTE valido sumir porque um
      campo secundario veio torto e um preco alto demais para pagar, e
      deixaria o operador sem a leitura em vez de com ela;
    * *corrigir na origem*, que e o que esta funcao faz: re-deriva
      `direcao` a partir da `forca`, porque **a forca e o numero que o
      operador le** — o percentual grande do ladrilho. O rotulo e a cor
      passam a seguir o numero, nunca o contrario.

    A excecao declarada e o **REGIME**: la a medida E a palavra
    (COMPRADOR/VENDEDOR, vinda da estrutura de preco) e a `forca` e que e
    derivada dela (+1/-1). Re-derivar a direcao a partir da forca seria
    circular, entao o REGIME continua com o gate de *barrar*
    (`_linha_regime`): palavra em desacordo com o proprio sinal indica
    dado corrompido, e o cartao degrada para "—".

    Custo: se algum dia uma fonte passar a emitir `direcao` com semantica
    propria, diferente do sinal da `forca`, esta funcao vai silenciosamente
    sobrescrever essa semantica. O contrato deste painel e que isso NAO
    existe — uma leitura tem um sinal so — e o teste de varredura por
    componente e quem defende esse contrato.
    """

    if leitura_e_coerente(linha):
        return linha
    return dataclass_replace(linha, direcao=_direcao_de_score(linha.forca))


def _ranking_componentes_maker(maker: object, top_n: int = 3) -> str:
    """Os N componentes do MakerProxy de maior magnitude, "1o/2o/3o".

    Pedido do operador: um "Maker 1o/2o/3o" no estilo ranking. A fonte do
    metodo (BbnGYiwygFQ.txt) descreve o Maker como UM sinal agregado, nao um
    ranking de tres entidades — inventar um mecanismo de ranking novo seria
    fabricar dado. Isto e o que existe de verdade e e honesto sobre esse
    pedido: `MakerProxySnapshot.componentes` ja quebra o mesmo sinal agregado
    em ABSORCAO/REPOSICAO/DIVERGENCIA/CLIPS/AGRESSAO (fluxopro/asg/
    maker_proxy.py, jamais por nome de corretora); aqui so ordenamos essa
    quebra por |pontuacao| e mostramos os `top_n`. "Giro" = numero de
    evidencias que sustentam aquele componente, nao um giro de contratos —
    rotulado como tal para nao alegar um dado que a fonte nao calcula.
    """

    componentes = tuple(getattr(maker, "componentes", ()) or ())
    if not componentes:
        return ""
    ordenados = sorted(componentes, key=lambda c: abs(getattr(c, "pontuacao", 0.0)), reverse=True)
    linhas = []
    for posicao, comp in enumerate(ordenados[:top_n], start=1):
        nome = str(getattr(comp, "componente", "?"))
        # `_sem_zero_negativo`: achado de 28/08/2026 (auditoria pos-entrega) —
        # esta linha usava `pontuacao` crua, entao um componente exatamente
        # zero podia imprimir "-0%" (o mesmo defeito que ja saiu do
        # EQUILIBRIO/PRESENCA/RITMO nesta sessao, so que renascido aqui,
        # numa quarta porta que o portao `leitura_e_coerente` nao cobre
        # porque este texto nunca vira LinhaMatrizASG, so string livre).
        pontuacao = _sem_zero_negativo(float(getattr(comp, "pontuacao", 0.0)))
        giro = int(getattr(comp, "n_evidencias", 0))
        # `_sem_zero_negativo` so zera o que JA e zero no float bruto — nao
        # cobre o caso irmao, achado pelo proprio teste desta correcao: um
        # score real e nao-zero (ex. -0,001, VENDA de verdade) que ARREDONDA
        # para "0" na casa exibida (`:+.0f`) e sai como "-0%" mesmo assim.
        # Aqui o corte e no valor JA ARREDONDADO, nao no bruto.
        percentual = round(pontuacao * 100)
        texto_percentual = "+0%" if percentual == 0 else f"{percentual:+d}%"
        linhas.append(f"{posicao}o {nome}  {texto_percentual}  giro {giro}")
    # Uma linha por posicao — nao uma so string espremida — porque uma
    # unica linha de ~5px era, na pratica, ilegivel (achado do operador
    # olhando o app ao vivo: "onde esta os makers?" com o texto la, so que
    # pequeno demais pra ler).
    return "\n".join(linhas)


# IMPRECISO — nao ha, em nenhuma fonte deste projeto (pesquisa/*.md), uma
# escala declarada para "quanto de delta de agressao e MUITO" em HORIZONTE
# (desde a abertura) ou PULSO (janela de 15s, ConfigMacroMicro.janela_micro_ns).
# Antes, a formula `numero / max(abs(numero), 1)` colapsava para sign(numero)
# sempre que |numero| >= 1 — HORIZONTE/PULSO so podiam mostrar -100%/0%/+100%,
# nunca um grau intermediario (achado do operador: "esta sem sentido").
# Aqui cada metrica e normalizada contra a PROPRIA referencia de magnitude
# (nunca contra a magnitude uma da outra — macro_micro.py proibe comparar
# escalas), dando gradacao continua sem fingir que o numero de referencia
# vem do metodo original. Ajuste estes dois valores se a referencia se
# mostrar alta/baixa demais na pratica.
REFERENCIA_MAGNITUDE_HORIZONTE_CONTRATOS = 8000.0
REFERENCIA_MAGNITUDE_PULSO_CONTRATOS = 80.0


# IMPRECISO — fatores de engenharia deste projeto.
#
# Achado do operador (27/08/2026): o ladrilho RITMO mostrava "+100%" com o
# rotulo "DESACELERANDO" logo abaixo, no mesmo ladrilho. Nao era erro de
# leitura: `LeituraVelocimetro` tem DOIS eixos declarados
# (`fluxopro/metodologia/velocimetro.py`) — GRANDEZA (`magnitude_relativa`)
# e MANUTENCAO (`estado`) — e o numero grande usava so o primeiro. Um
# movimento grande que ja esta perdendo forca aparecia como conviccao
# maxima.
#
# Aqui a manutencao entra como FATOR sobre a magnitude, para que o numero
# na tela signifique "quanto de ritmo o mercado tem AGORA" e nao "quao
# grande foi o ultimo empurrao". A direcao (sinal) continua vindo so do
# `sentido` — nunca invertida por este fator. O rotulo de estado continua
# impresso ao lado: quem quiser os dois eixos separados continua tendo.
_FATOR_MANUTENCAO_RITMO = {
    "ACELERANDO": 1.00,
    "MANTENDO": 0.85,
    "DESACELERANDO": 0.45,
    # VIROU: o sentido acabou de inverter — ha movimento, mas a leitura de
    # continuidade e a mais fraca das que ainda tem sentido definido.
    "VIROU": 0.30,
    "PARADO": 0.0,
    "SEM_DADOS": 0.0,
}


def _forca_ritmo_composta(magnitude: object, estado_nome: str, sinal: float) -> float:
    """GRANDEZA x MANUTENCAO x direcao — ver `_FATOR_MANUTENCAO_RITMO`.

    Custo declarado: um mercado que acelera do zero passa a chegar ao
    numero cheio um passo depois (o estado precisa virar ACELERANDO), mas
    nao ha media movel nem atraso temporal aqui — o fator e do proprio
    quadro, entao uma virada real nunca fica escondida atras de historico.
    """

    if not isinstance(magnitude, (int, float)) or isinstance(magnitude, bool):
        return 0.0
    fator = _FATOR_MANUTENCAO_RITMO.get(estado_nome.upper(), 0.0)
    bruta = _forca_limitada(float(magnitude) * fator) * sinal
    # `+.0f` sobre -0.0 imprime "-0%": um sinal de venda em cima de uma
    # leitura que e exatamente zero. Zero nao tem lado.
    return 0.0 if bruta == 0 else bruta


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

    def contexto(nome: str, valor: object, referencia: float) -> LinhaMatrizASG:
        numero = int(valor) if isinstance(valor, int) and not isinstance(valor, bool) else None
        return LinhaMatrizASG(
            componente=nome,
            direcao=_direcao_numero(numero),
            valor="SEM DADOS" if numero is None else f"{numero:+d}",
            forca=0.0 if numero is None else _forca_limitada(numero / referencia),
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
        contexto("MACRO", valor_macro, REFERENCIA_MAGNITUDE_HORIZONTE_CONTRATOS),
        contexto("MICRO", valor_micro, REFERENCIA_MAGNITUDE_PULSO_CONTRATOS),
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
            valor=f"{_sem_zero_negativo(maker_score) * 100:+.0f}%",
            forca=_sem_zero_negativo(maker_score),
            confianca=_confianca_numerica(maker_conf),
            procedencia=_procedencia_do_maker(getattr(maker, "procedencia", "")),
            evidencias=len(tuple(getattr(maker, "evidence", ()))),
            detalhe=(
                _ranking_componentes_maker(maker)
                or f"PERSIST {int(getattr(maker, 'persistence_ns', 0)) / 1e9:.1f}s"
            ),
        ),
        LinhaMatrizASG(
            componente="VELOCIMETRO",
            direcao=_direcao_textual(velocidade_lado),
            valor=_valor_enum(velocidade_estado).upper(),
            forca=_forca_ritmo_composta(
                magnitude,
                _valor_enum(velocidade_estado),
                -1.0 if _direcao_textual(velocidade_lado) is DirecaoASG.VENDA else 1.0,
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
    "ContextoBrutoASGSnapshot",
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
    "NegocioBrutoASG",
    "NivelBrutoASG",
    "PainelContextoBrutoASG",
    "PainelDadosASG",
    "PainelDecisaoASG",
    "PainelEvidenciasASG",
    "PainelMatrizASG",
    "PainelNexoMercadoASG",
    "PainelProcessamentoASG",
    "ProcedenciaASG",
    "ProcessamentoASGSnapshot",
    "ResultadoGate",
    "TrilhaEvidenciasASGSnapshot",
    "WorkspaceASG",
    "WorkspaceASGSnapshot",
    "cor_estado",
    "rotulo_direcao",
    "rotulo_estado",
]
