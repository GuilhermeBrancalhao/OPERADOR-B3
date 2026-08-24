"""Portoes do veredito cego do workspace UI — Gauntlet rodada 2."""

from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fluxopro.ui import tokens  # noqa: E402
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
    PainelDadosASG,
    PainelDecisaoASG,
    PainelEvidenciasASG,
    PainelMatrizASG,
    PainelProcessamentoASG,
    ProcedenciaASG,
    ProcessamentoASGSnapshot,
    ResultadoGate,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASG,
    WorkspaceASGSnapshot,
)

T0 = 1_700_000_000_000_000_000


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _quadro(estado: EstadoASG = EstadoASG.AO_VIVO, n: int = 20) -> WorkspaceASGSnapshot:
    saudavel = estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
    dados = DadosASGSnapshot(
        timestamp_ns=T0,
        estado=estado,
        fonte="MT5" if estado is not EstadoASG.REPLAY else "REPLAY",
        sequencia=10_000,
        atraso_ms=3.2,
        trades_s=70.0,
        niveis_book=20 if estado is not EstadoASG.SEM_BOOK else 0,
        gaps=None,
        anomalias=2,
        descartados=1,
        confianca=ConfiancaASG.ALTA if saudavel else ConfiancaASG.INDISPONIVEL,
        procedencia=ProcedenciaASG.OBSERVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
        detalhe="snapshot coerente",
    )
    etapas = tuple(
        EtapaProcessamentoASG(
            f"ETAPA {i:02d}",
            "OK" if saudavel else estado.value,
            i / 10,
            ConfiancaASG.ALTA if saudavel else ConfiancaASG.INDISPONIVEL,
            ProcedenciaASG.DERIVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
        )
        for i in range(n)
    )
    processamento = ProcessamentoASGSnapshot(T0, estado, "proxy-r2", etapas)
    linhas = tuple(
        LinhaMatrizASG(
            f"COMP {i:02d}",
            DirecaoASG.COMPRA if saudavel and i % 2 == 0 else
            DirecaoASG.VENDA if saudavel else DirecaoASG.NEUTRA,
            f"{(i + 1) / 100:+.2f}",
            (i + 1) / 100 if saudavel else 0.0,
            ConfiancaASG.MEDIA if saudavel else ConfiancaASG.INDISPONIVEL,
            ProcedenciaASG.DERIVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
            i + 1,
        )
        for i in range(n)
    )
    matriz = MatrizASGSnapshot(T0, estado, linhas, f"{n}/{n}")
    gates = tuple(
        GateDecisaoASG(
            f"GATE {i:02d}",
            ResultadoGate.PASSA if saudavel else ResultadoGate.AGUARDA,
            "confirmado" if saudavel else estado.value,
        )
        for i in range(n)
    )
    decisao = DecisaoASGSnapshot(
        T0,
        estado,
        DirecaoASG.COMPRA if saudavel else DirecaoASG.AGUARDAR,
        "CONFIRMADO" if saudavel else "SEM DECISAO",
        "evidencias convergentes" if saudavel else f"{estado.value} bloqueia decisao",
        ConfiancaASG.ALTA if saudavel else ConfiancaASG.INDISPONIVEL,
        ProcedenciaASG.DERIVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
        gates,
        *(('100t', '110t', '120t', '130t') if saudavel else ('—',) * 4),
    )
    itens = tuple(
        EvidenciaASG(
            T0 + i * 1_000_000,
            "BOOK",
            f"EVENTO {i:02d}",
            f"score {i:+d}",
            ConfiancaASG.ALTA if saudavel else ConfiancaASG.INDISPONIVEL,
            ProcedenciaASG.OBSERVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
            estado,
        )
        for i in range(n)
    )
    evidencias = TrilhaEvidenciasASGSnapshot(T0, estado, itens, n, n)
    return WorkspaceASGSnapshot(
        T0, dados, processamento, matriz, decisao, evidencias,
        estado_operacional=estado,
    )


@pytest.mark.parametrize(
    "estado",
    [EstadoASG.DESCONHECIDO, EstadoASG.AGUARDANDO, EstadoASG.ATRASADO,
     EstadoASG.SEM_BOOK, EstadoASG.ERRO],
)
def test_estado_nao_operacional_bloqueia_decisao_confirmada(estado):
    with pytest.raises(ValueError, match="exige decisao AGUARDAR"):
        DecisaoASGSnapshot(
            T0, estado, DirecaoASG.COMPRA, "CONFIRMADO", "motivo",
            ConfiancaASG.ALTA, ProcedenciaASG.DERIVADO,
        )


def test_workspace_recusa_estado_operacional_contraditorio():
    quadro = _quadro()
    dados_sem_book = replace(quadro.dados, estado=EstadoASG.SEM_BOOK)
    with pytest.raises(ValueError, match="estado operacional contraditorio"):
        WorkspaceASGSnapshot(
            T0, dados_sem_book, quadro.processamento, quadro.matriz,
            quadro.decisao, quadro.evidencias,
        )


def test_workspace_recebe_um_snapshot_asg_tipado_por_quadro(qapp):
    workspace = WorkspaceASG()
    with pytest.raises(TypeError, match="WorkspaceASGSnapshot tipado"):
        workspace.aplicar(SimpleNamespace())  # type: ignore[arg-type]


def test_estado_desconhecido_do_maker_e_neutro_e_bloqueado():
    componente = SimpleNamespace(
        componente=SimpleNamespace(value="ABSORCAO"), pontuacao=.9,
        confianca=.95, cobertura=1.0, n_evidencias=4,
    )
    maker = SimpleNamespace(
        timestamp_ns=T0, estado=SimpleNamespace(value="NOVO_ESTADO"),
        componentes=(componente,), cobertura=1.0,
        procedencia=SimpleNamespace(value="OBSERVADA"), formula_version="x",
    )
    matriz = MatrizASGSnapshot.de_leitura(maker)
    assert matriz.estado is EstadoASG.DESCONHECIDO
    assert matriz.linhas[0].direcao is DirecaoASG.NEUTRA
    assert matriz.linhas[0].forca == 0
    assert matriz.linhas[0].valor == "INDISPONIVEL"


def test_feed_sem_gap_disponivel_nao_inventa_zero_nem_perda(qapp):
    feed = SimpleNamespace(
        timestamp_ns=T0, state=SimpleNamespace(value="connected"),
        source=SimpleNamespace(value="mt5"), book_kind=SimpleNamespace(value="mbp"),
        aggressor_quality=SimpleNamespace(value="native"), depth=20,
        sequence_gaps=None, duplicates=3, sequence_regressions=2,
        regressive_timestamps=1, dropped_events=4, latency_ns=0,
    )
    snapshot = DadosASGSnapshot.de_feed(feed)
    painel = PainelDadosASG()
    painel.resize(700, 220)
    painel.aplicar(snapshot)
    assert snapshot.gaps is None
    assert snapshot.anomalias == 6
    assert snapshot.descartados == 4
    assert any("GAPS INDISPONIVEL" in texto for texto in painel.textos_visiveis())
    assert any("ANOMALIAS 6" in texto for texto in painel.textos_visiveis())
    assert any("DESCARTADOS 4" in texto for texto in painel.textos_visiveis())


@pytest.mark.parametrize("resolucao", [(1280, 720), (1480, 900), (1920, 1080)])
def test_tres_resolucoes_nao_desenham_linha_sob_rodape(qapp, resolucao):
    workspace = WorkspaceASG()
    workspace.resize(*resolucao)
    workspace.aplicar(_quadro(n=30))
    workspace.show()
    qapp.processEvents()
    workspace.layout().activate()
    for painel in workspace.paineis:
        painel.marcar_tudo_sujo()
        painel._quadro()
        assert painel._backing is not None
        rects = painel.retangulos_visiveis()
        assert all(rect.bottom() < painel.faixa_rodape().top() for _, rect in rects)
        assert painel.texto_visibilidade().startswith("VISIVEIS ")
    workspace.hide()


@pytest.mark.parametrize(
    "atributo",
    ["dados", "processamento", "matriz", "decisao", "evidencias"],
)
def test_timestamp_do_quadro_sozinho_nao_suja_painel(qapp, atributo):
    quadro = _quadro(n=8)
    painel = {
        "dados": PainelDadosASG(),
        "processamento": PainelProcessamentoASG(),
        "matriz": PainelMatrizASG(),
        "decisao": PainelDecisaoASG(),
        "evidencias": PainelEvidenciasASG(),
    }[atributo]
    painel.resize(760, 260)
    original = getattr(quadro, atributo)
    painel.aplicar(original)
    painel._quadro()
    assert not painel.tem_sujeira
    painel.aplicar(replace(original, timestamp_ns=T0 + 1))
    assert not painel.tem_sujeira


def test_mudanca_de_conteudo_visivel_continua_pedindo_repaint(qapp):
    painel = PainelDadosASG()
    painel.resize(700, 220)
    original = _quadro().dados
    painel.aplicar(original)
    painel._quadro()
    assert not painel.tem_sujeira
    painel.aplicar(replace(original, detalhe="conteudo visual novo"))
    assert painel.tem_sujeira


@pytest.mark.parametrize("tecla", [Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_End])
def test_teclado_navega_conteudo_virtualizado(qapp, tecla):
    painel = PainelMatrizASG()
    painel.resize(760, 220)
    painel.aplicar(_quadro(n=30).matriz)
    evento = QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier)
    painel.keyPressEvent(evento)
    assert evento.isAccepted()
    assert painel.primeiro_visivel > 0
    assert "COMP 00" not in painel.textos_visiveis()


def test_home_end_setas_pagina_e_roda_respeitam_limites(qapp):
    painel = PainelEvidenciasASG()
    painel.resize(760, 160)
    painel.aplicar(_quadro(n=30).evidencias)
    painel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_End,
                                  Qt.KeyboardModifier.NoModifier))
    fim = painel.primeiro_visivel
    assert fim > 0
    painel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Home,
                                  Qt.KeyboardModifier.NoModifier))
    assert painel.primeiro_visivel == 0
    painel.wheelEvent(_Roda(-120))
    assert painel.primeiro_visivel == 3
    painel.wheelEvent(_Roda(120))
    assert painel.primeiro_visivel == 0


def test_textos_visiveis_nao_vazam_linhas_fora_da_pagina(qapp):
    quadro = _quadro(n=30)
    painel = PainelProcessamentoASG()
    painel.resize(420, 150)
    painel.aplicar(quadro.processamento)
    textos = painel.textos_visiveis()
    assert "ETAPA 00" in textos
    assert "ETAPA 29" not in textos
    painel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_End,
                                  Qt.KeyboardModifier.NoModifier))
    textos_fim = painel.textos_visiveis()
    assert "ETAPA 00" not in textos_fim
    assert "ETAPA 29" in textos_fim


def test_evento_da_trilha_aparece_uma_unica_vez(qapp):
    painel = PainelEvidenciasASG()
    painel.resize(760, 120)
    item = EvidenciaASG(
        T0, "BOOK", "REPOSICAO", "+18 lotes",
        ConfiancaASG.ALTA, ProcedenciaASG.OBSERVADO,
    )
    painel.aplicar(TrilhaEvidenciasASGSnapshot(T0, EstadoASG.AO_VIVO, (item,), 1, 1))
    assert sum(texto.count("REPOSICAO") for texto in painel.textos_visiveis()) == 1


def test_paleta_sem_cor_mantem_simbolos_em_pagina_virtualizada(qapp):
    quadro = _quadro(n=20)
    matriz = PainelMatrizASG(paleta=tokens.PALETA_SEM_COR)
    decisao = PainelDecisaoASG(paleta=tokens.PALETA_SEM_COR)
    matriz.resize(760, 220)
    decisao.resize(520, 220)
    matriz.aplicar(quadro.matriz)
    decisao.aplicar(quadro.decisao)
    assert any("▲ COMPRA" in texto or "▼ VENDA" in texto
               for texto in matriz.textos_visiveis())
    assert "▲ COMPRA" in decisao.textos_visiveis()


class _Roda:
    def __init__(self, delta: int) -> None:
        self._delta = delta
        self.aceito = False

    def angleDelta(self) -> QPoint:  # noqa: N802
        return QPoint(0, self._delta)

    def accept(self) -> None:
        self.aceito = True
