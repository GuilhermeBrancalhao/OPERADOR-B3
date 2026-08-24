"""Contrato imutavel e vocabulario acessivel dos componentes ASG-like."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    EtapaProcessamentoASG,
    EvidenciaASG,
    GateDecisaoASG,
    LinhaMatrizASG,
    MatrizASGSnapshot,
    ProcedenciaASG,
    ProcessamentoASGSnapshot,
    ResultadoGate,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
    rotulo_direcao,
    rotulo_estado,
)

T0 = 1_700_000_000_000_000_000


def _workspace() -> WorkspaceASGSnapshot:
    dados = DadosASGSnapshot(
        timestamp_ns=T0,
        estado=EstadoASG.AO_VIVO,
        fonte="MT5",
        sequencia=123,
        atraso_ms=2.4,
        trades_s=84.0,
        niveis_book=20,
        gaps=0,
        anomalias=0,
        descartados=0,
        confianca=ConfiancaASG.ALTA,
        procedencia=ProcedenciaASG.OBSERVADO,
        detalhe="SEQUENCIA CONTINUA",
    )
    processamento = ProcessamentoASGSnapshot(
        T0,
        EstadoASG.AO_VIVO,
        "maker-proxy-v1",
        [EtapaProcessamentoASG("ABSORCAO", "OK", 0.3, ConfiancaASG.ALTA,
                               ProcedenciaASG.DERIVADO)],
    )
    matriz = MatrizASGSnapshot(
        T0,
        EstadoASG.AO_VIVO,
        [LinhaMatrizASG("ABSORCAO", DirecaoASG.COMPRA, "+0,72", .72,
                        ConfiancaASG.ALTA, ProcedenciaASG.DERIVADO, 14)],
        "5/6",
    )
    decisao = DecisaoASGSnapshot(
        T0,
        EstadoASG.AO_VIVO,
        DirecaoASG.COMPRA,
        "PRE-SINAL COMPRADOR",
        "Quatro de cinco gates passam",
        ConfiancaASG.MEDIA,
        ProcedenciaASG.DERIVADO,
        [GateDecisaoASG("COBERTURA", ResultadoGate.PASSA, "5/6")],
    )
    evidencias = TrilhaEvidenciasASGSnapshot(
        T0,
        EstadoASG.AO_VIVO,
        [EvidenciaASG(T0, "BOOK", "REPOSICAO", "+18 lotes",
                      ConfiancaASG.ALTA, ProcedenciaASG.OBSERVADO)],
        1,
        1,
    )
    return WorkspaceASGSnapshot(T0, dados, processamento, matriz, decisao, evidencias)


def test_snapshots_sao_congelados_e_normalizam_colecoes_para_tuplas():
    snapshot = _workspace()
    assert isinstance(snapshot.processamento.etapas, tuple)
    assert isinstance(snapshot.matriz.linhas, tuple)
    assert isinstance(snapshot.decisao.gates, tuple)
    assert isinstance(snapshot.evidencias.itens, tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.dados.fonte = "OUTRA"  # type: ignore[misc]


@pytest.mark.parametrize("estado", list(EstadoASG))
def test_todo_estado_tem_palavra_e_simbolo(estado):
    rotulo = rotulo_estado(estado)
    assert estado.value in rotulo
    assert rotulo[0] in "?○●!×▶"


@pytest.mark.parametrize(
    ("direcao", "simbolo"),
    [
        (DirecaoASG.COMPRA, "▲"),
        (DirecaoASG.VENDA, "▼"),
        (DirecaoASG.NEUTRA, "◆"),
        (DirecaoASG.AGUARDAR, "○"),
    ],
)
def test_direcao_nao_depende_de_cor(direcao, simbolo):
    assert rotulo_direcao(direcao) == f"{simbolo} {direcao.value}"


def test_decisao_e_estritamente_consultiva_na_api():
    campos = set(DecisaoASGSnapshot.__dataclass_fields__)
    proibidos = {nome for nome in campos if any(p in nome for p in ("enviar", "ordem", "executar"))}
    assert not proibidos
    assert not any(hasattr(DecisaoASGSnapshot, nome) for nome in ("send", "execute", "submit"))


def test_workspace_recusa_componentes_de_quadros_diferentes():
    snapshot = _workspace()
    dados_atrasados = DadosASGSnapshot(T0 - 1)
    with pytest.raises(ValueError, match="unico timestamp"):
        WorkspaceASGSnapshot(
            T0,
            dados_atrasados,
            snapshot.processamento,
            snapshot.matriz,
            snapshot.decisao,
            snapshot.evidencias,
        )


def test_adaptador_de_feed_preserva_ausencia_e_procedencia():
    feed = SimpleNamespace(
        timestamp_ns=T0,
        state=SimpleNamespace(value="connected"),
        source=SimpleNamespace(value="mt5"),
        book_kind=SimpleNamespace(value="none"),
        aggressor_quality=SimpleNamespace(value="inferred"),
        depth=0,
        sequence_gaps=3,
        duplicates=2,
        sequence_regressions=1,
        regressive_timestamps=0,
        dropped_events=4,
        latency_ns=12_500_000,
        last_sequence=44,
        detail="Livro indisponivel",
    )
    visual = DadosASGSnapshot.de_feed(feed)
    assert visual.estado is EstadoASG.SEM_BOOK
    assert visual.procedencia is ProcedenciaASG.INFERIDO
    assert visual.confianca is ConfiancaASG.BAIXA
    assert visual.gaps == 3
    assert visual.anomalias == 3
    assert visual.descartados == 4


def test_feed_sem_contador_de_gap_publica_indisponivel_sem_falhar():
    feed = SimpleNamespace(
        timestamp_ns=T0,
        state=SimpleNamespace(value="connected"),
        source=SimpleNamespace(value="mt5"),
        book_kind=SimpleNamespace(value="mbp"),
        aggressor_quality=SimpleNamespace(value="native"),
        depth=20,
        sequence_gaps=None,
        latency_ns=0,
    )
    visual = DadosASGSnapshot.de_feed(feed)
    assert visual.gaps is None


def test_adaptadores_do_maker_mantem_score_e_evidencia():
    evidencia = SimpleNamespace(
        timestamp_ns=T0,
        fonte="MBO",
        tipo_evento="REPOSICAO",
        pontuacao=-0.4,
        confianca=0.8,
        procedencia=SimpleNamespace(value="OBSERVADA"),
    )
    componente = SimpleNamespace(
        componente=SimpleNamespace(value="REPOSICAO"),
        pontuacao=-0.4,
        confianca=0.8,
        cobertura=0.75,
        n_evidencias=1,
        evidencias=(evidencia,),
    )
    maker = SimpleNamespace(
        timestamp_ns=T0,
        estado=SimpleNamespace(value="VENDEDOR"),
        componentes=(componente,),
        cobertura=0.75,
        procedencia=SimpleNamespace(value="OBSERVADA"),
        formula_version="maker-proxy-independent-v1",
    )
    matriz = MatrizASGSnapshot.de_leitura(maker)
    trilha = TrilhaEvidenciasASGSnapshot.de_maker(maker)
    processamento = ProcessamentoASGSnapshot.de_maker(maker)
    assert matriz.linhas[0].direcao is DirecaoASG.VENDA
    assert matriz.linhas[0].valor == "-0,40"
    assert matriz.cobertura == "75%"
    assert trilha.itens[0].evento == "REPOSICAO"
    assert processamento.etapas[0].procedencia is ProcedenciaASG.OBSERVADO
