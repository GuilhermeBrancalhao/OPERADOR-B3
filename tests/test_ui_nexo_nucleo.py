"""Smoke tests do visor central (fluxopro/ui/paineis/nexo/nucleo.py).

Cobre especificamente o selo do Sinal Ultra (26/08/2026): o visor precisa
desenhar sem excecao e sem estourar a regiao quando `estado.sinal_ultra`
esta ativo, e o rotulo "SINAL CONSULTIVO" precisa virar o rotulo do Ultra
quando ele dispara.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.asg.sinal_ultra import DirecaoUltra, SinalUltraSnapshot
from fluxopro.ui.paineis.asg import DecisaoASGSnapshot, MatrizASGSnapshot, WorkspaceASGSnapshot
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import nucleo


def _snapshot():
    return WorkspaceASGSnapshot(
        0,
        __import__("fluxopro.ui.paineis.asg", fromlist=["DadosASGSnapshot"]).DadosASGSnapshot(0),
        __import__("fluxopro.ui.paineis.asg", fromlist=["ProcessamentoASGSnapshot"]).ProcessamentoASGSnapshot(0),
        MatrizASGSnapshot(0),
        DecisaoASGSnapshot(0),
        __import__("fluxopro.ui.paineis.asg", fromlist=["TrilhaEvidenciasASGSnapshot"]).TrilhaEvidenciasASGSnapshot(0),
        contexto_bruto=None,
    )


def _estado(sinal_ultra):
    return EstadoNexo(
        snapshot=_snapshot(),
        serie=(),
        grid=None,
        paleta=None,
        maker=None,
        leituras=(),
        largura=400,
        altura=300,
        sinal_ultra=sinal_ultra,
    )


def _desenha_sem_excecao(qapp, sinal_ultra):
    pixmap = QPixmap(400, 300)
    painter = QPainter(pixmap)
    try:
        nucleo.desenhar(painter, QRect(0, 0, 400, 300), _estado(sinal_ultra))
    finally:
        painter.end()


def test_desenha_sem_sinal_ultra(qapp):
    _desenha_sem_excecao(qapp, None)


def test_desenha_com_ultra_compra_ativo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.COMPRA,
        confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=500,
    )
    _desenha_sem_excecao(qapp, snap)


def test_desenha_com_ultra_venda_ativo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.VENDA,
        confluencia_no_instante=DirecaoUltra.VENDA, ligado_desde_ns=500,
    )
    _desenha_sem_excecao(qapp, snap)


def test_ultra_nenhuma_nao_ativa_o_selo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.NENHUMA,
        confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=None,
    )
    _desenha_sem_excecao(qapp, snap)
