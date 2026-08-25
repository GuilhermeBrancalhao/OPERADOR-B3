"""Geometria responsiva e informacao visivel dos paineis ASG-like."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    ContextoBrutoASGSnapshot,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    EtapaProcessamentoASG,
    EvidenciaASG,
    GateDecisaoASG,
    LinhaMatrizASG,
    MatrizASGSnapshot,
    NegocioBrutoASG,
    PainelDadosASG,
    PainelDecisaoASG,
    PainelEvidenciasASG,
    PainelMatrizASG,
    PainelNexoMercadoASG,
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


def _snapshots(estado: EstadoASG = EstadoASG.AO_VIVO):
    dados = DadosASGSnapshot(
        timestamp_ns=T0, estado=estado, fonte="REPLAY ARQUIVO", sequencia=98_765,
        atraso_ms=12.7, trades_s=320.4, niveis_book=40, gaps=2, anomalias=1,
        descartados=0, confianca=ConfiancaASG.MEDIA,
        procedencia=ProcedenciaASG.REPLAY, detalhe="GAP DE 2 EVENTOS VISIVEL",
    )
    proc = ProcessamentoASGSnapshot(
        T0, estado, "proxy-v1",
        (
            EtapaProcessamentoASG("NORMALIZACAO", "OK", .2, ConfiancaASG.ALTA,
                                  ProcedenciaASG.OBSERVADO),
            EtapaProcessamentoASG("MAKER PROXY", "AQUECIMENTO", 1.7,
                                  ConfiancaASG.BAIXA, ProcedenciaASG.INFERIDO),
        ),
        3,
        0,
    )
    desconhecido = estado is EstadoASG.DESCONHECIDO
    matriz = MatrizASGSnapshot(
        T0, estado,
        (
            LinhaMatrizASG("ABSORCAO", DirecaoASG.NEUTRA if desconhecido else DirecaoASG.COMPRA,
                            "INDISPONIVEL" if desconhecido else "+0,72", 0 if desconhecido else .72,
                            ConfiancaASG.INDISPONIVEL if desconhecido else ConfiancaASG.ALTA,
                            ProcedenciaASG.INDISPONIVEL if desconhecido else ProcedenciaASG.DERIVADO,
                            12),
            LinhaMatrizASG("DIVERGENCIA", DirecaoASG.NEUTRA if desconhecido else DirecaoASG.VENDA,
                            "INDISPONIVEL" if desconhecido else "-0,31", 0 if desconhecido else -.31,
                            ConfiancaASG.INDISPONIVEL if desconhecido else ConfiancaASG.MEDIA,
                            ProcedenciaASG.INDISPONIVEL if desconhecido else ProcedenciaASG.INFERIDO,
                            4),
        ),
        "5/6",
    )
    saudavel = estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
    decisao = DecisaoASGSnapshot(
        T0, estado, DirecaoASG.COMPRA if saudavel else DirecaoASG.AGUARDAR,
        "PRE-SINAL COMPRADOR" if saudavel else "SEM DECISAO",
        ("Book confirma reposicao; agressao ainda precisa persistir" if saudavel
         else f"Estado {estado.value} bloqueia decisao"),
        ConfiancaASG.MEDIA if saudavel else ConfiancaASG.INDISPONIVEL,
        ProcedenciaASG.DERIVADO if saudavel else ProcedenciaASG.INDISPONIVEL,
        (
            GateDecisaoASG("BOOK", ResultadoGate.PASSA if saudavel else ResultadoGate.AGUARDA,
                           "20 niveis" if saudavel else estado.value),
            GateDecisaoASG("PERSISTENCIA", ResultadoGate.AGUARDA, "2/3 janelas"),
        ),
        *(('5.082,0', '5.088,0', '5.091,0', '5.096,0') if saudavel else ('—',) * 4),
    )
    evid = TrilhaEvidenciasASGSnapshot(
        T0, estado,
        (
            EvidenciaASG(T0, "BOOK", "REPOSICAO", "+18 lotes",
                          ConfiancaASG.ALTA, ProcedenciaASG.OBSERVADO, estado),
            EvidenciaASG(T0 + 1_000_000, "PROXY", "DIVERGENCIA", "-0,31",
                          ConfiancaASG.MEDIA, ProcedenciaASG.INFERIDO, estado),
        ),
        18,
        2,
    )
    return dados, proc, matriz, decisao, evid


def _renderizar(painel, largura: int, altura: int):
    painel.resize(largura, altura)
    painel.marcar_tudo_sujo()
    painel._quadro()
    assert painel._backing is not None
    return painel._backing.toImage()


@pytest.mark.parametrize("estado", list(EstadoASG))
def test_estado_critico_esta_no_quadro_e_nao_em_hover(qapp, estado):
    painel = PainelDadosASG()
    painel.aplicar(_snapshots(estado)[0])
    painel.resize(420, 180)
    assert any(estado.value in texto for texto in painel.textos_visiveis())
    assert painel.toolTip() == ""
    imagem = _renderizar(painel, 420, 180)
    assert not imagem.isNull()


def test_cinco_paineis_publicam_confianca_e_procedencia(qapp):
    dados, proc, matriz, decisao, evid = _snapshots()
    paineis = (
        (PainelDadosASG(), dados),
        (PainelProcessamentoASG(), proc),
        (PainelMatrizASG(), matriz),
        (PainelDecisaoASG(), decisao),
        (PainelEvidenciasASG(), evid),
    )
    for painel, snapshot in paineis:
        painel.aplicar(snapshot)
        textos = painel.textos_visiveis()
        assert any("CONF" in texto for texto in textos), type(painel).__name__
        assert any(texto in {p.value for p in ProcedenciaASG} for texto in textos), type(painel).__name__


def test_dados_refluem_sem_espremer_colunas(qapp):
    painel = PainelDadosASG()
    assert _redimensionar_e_ler(painel, 700, painel.n_colunas) == 3
    assert _redimensionar_e_ler(painel, 500, painel.n_colunas) == 2
    assert _redimensionar_e_ler(painel, 300, painel.n_colunas) == 1


def test_matriz_troca_tabela_por_cartoes(qapp):
    painel = PainelMatrizASG()
    assert _redimensionar_e_ler(painel, 760, painel.modo_tabela)
    assert not _redimensionar_e_ler(painel, 520, painel.modo_tabela)


def test_workspace_tem_tres_arranjos_responsivos(qapp):
    workspace = WorkspaceASG()
    for largura, esperado in ((1280, "largo"), (900, "medio"), (640, "estreito")):
        workspace.resize(largura, 760)
        workspace._reorganizar()
        assert workspace.modo_layout == esperado
        assert all(p.parent() is workspace for p in workspace.paineis)


def test_snapshot_unico_alimenta_os_cinco_filhos(qapp):
    dados, proc, matriz, decisao, evid = _snapshots(EstadoASG.REPLAY)
    snapshot = WorkspaceASGSnapshot(T0, dados, proc, matriz, decisao, evid)
    workspace = WorkspaceASG()
    workspace.aplicar(snapshot)
    assert workspace.dados.snapshot is dados
    for painel in workspace.paineis:
        assert any("REPLAY" in texto for texto in painel.textos_visiveis())
    assert workspace._snapshot is snapshot


def test_nexo_gera_historico_causal_a_partir_de_cada_negocio_observado(qapp):
    dados, proc, matriz, decisao, evid = _snapshots()
    contexto = ContextoBrutoASGSnapshot(
        T0,
        EstadoASG.AO_VIVO,
        negocios=(
            NegocioBrutoASG(T0 + 1, 20_000, 3, 1),
            NegocioBrutoASG(T0 + 2, 20_004, 7, -1),
            NegocioBrutoASG(T0 + 3, 20_002, 5, 1),
        ),
        ultimo_preco=20_002,
    )
    painel = PainelNexoMercadoASG()
    painel.aplicar(WorkspaceASGSnapshot(T0, dados, proc, matriz, decisao, evid,
                                         contexto_bruto=contexto))
    assert [(ponto[0], ponto[1], ponto[3]) for ponto in painel._serie] == [
        (T0 + 1, 20_000, 3),
        (T0 + 2, 20_004, 7),
        (T0 + 3, 20_002, 5),
    ]
    imagem = _renderizar(painel, 1_280, 720)
    assert not imagem.isNull()


def test_modo_sem_cor_preserva_lado_em_texto_e_simbolo(qapp):
    _, _, matriz, decisao, _ = _snapshots()
    painel_matriz = PainelMatrizASG(paleta=tokens.PALETA_SEM_COR)
    painel_decisao = PainelDecisaoASG(paleta=tokens.PALETA_SEM_COR)
    painel_matriz.aplicar(matriz)
    painel_decisao.aplicar(decisao)
    assert "▲ COMPRA" in painel_matriz.textos_visiveis()
    assert "▼ VENDA" in painel_matriz.textos_visiveis()
    assert "▲ COMPRA" in painel_decisao.textos_visiveis()
    _renderizar(painel_matriz, 760, 240)
    _renderizar(painel_decisao, 520, 260)


def test_declaracoes_de_arquitetura_estao_no_conteudo_visivel(qapp):
    _, _, matriz, decisao, _ = _snapshots()
    painel_matriz = PainelMatrizASG()
    painel_decisao = PainelDecisaoASG()
    painel_matriz.aplicar(matriz)
    painel_decisao.aplicar(decisao)
    assert any("PROXY INDEPENDENTE" in texto for texto in painel_matriz.textos_visiveis())
    assert "CONSULTIVO · SEM ENVIO DE ORDENS" in painel_decisao.textos_visiveis()


def test_decisao_expoe_human_gate_sem_acao_clicavel(qapp):
    painel = PainelDecisaoASG()
    painel.aplicar(_snapshots()[3])
    textos = painel.textos_visiveis()
    assert "CONSULTIVO · SEM ENVIO DE ORDENS" in textos
    assert "STOP 5.082,0" in textos
    assert "A1 5.088,0" in textos
    assert not painel.findChildren(QWidget)


def _redimensionar_e_ler(widget, largura, leitor):
    widget.resize(largura, max(200, widget.height()))
    return leitor()
