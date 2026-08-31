"""Contratos do painel vertical NEXO AI."""

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QImage, QPainter

from fluxopro.ui.paineis.asg import (
    ContextoBrutoASGSnapshot,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    MatrizASGSnapshot,
    ProcessamentoASGSnapshot,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.nexo_ai_vertical import PainelNexoAIVertical, NexoAISnapshot


def _vazio() -> WorkspaceASGSnapshot:
    return WorkspaceASGSnapshot(
        0,
        DadosASGSnapshot(0),
        ProcessamentoASGSnapshot(0),
        MatrizASGSnapshot(0),
        DecisaoASGSnapshot(0),
        TrilhaEvidenciasASGSnapshot(0),
        contexto_bruto=ContextoBrutoASGSnapshot(0),
    )


def test_snapshot_vertical_tem_tres_cards_e_nao_inventa_preco() -> None:
    snapshot = NexoAISnapshot.de_workspace(_vazio(), "WDOU26")
    assert len(snapshot.cards) == 3
    assert [card.titulo for card in snapshot.cards] == [
        "AGUARDAR", "CONFIANÇA", "FORÇA DO FLUXO"
    ]
    assert snapshot.preco is None
    assert snapshot.book_kind == "NONE"


def test_painel_vertical_renderiza_em_coluna_portrait(qapp) -> None:
    painel = PainelNexoAIVertical(simbolo="WDOU26")
    painel.resize(1480, 900)
    painel.show()
    qapp.processEvents()
    imagem = QImage(QSize(1480, 900), QImage.Format.Format_ARGB32)
    imagem.fill(0)
    painter = QPainter(imagem)
    painel.render(painter, QPoint(0, 0))
    painter.end()
    assert imagem.width() == 1480
    assert painel.snapshot.cards[0].titulo == "AGUARDAR"
    painel.close()
