"""Mapeamento EstadoNexo -> motor de Dominância Comprador/Vendedor
(`fluxopro/ui/paineis/nexo/dominancia.py`). Cobre a extração dos 5
componentes (A/B/R/W/M) e o desenho do selo de estado sem exceção.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from fluxopro.analytics import dominancia as dom  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DirecaoASG,
    LinhaMatrizASG,
    ProcedenciaASG,
)
from fluxopro.ui.paineis.nexo import EstadoNexo, dominancia as mapa  # noqa: E402


def _candle(open_, high, low, close, volume, delta):
    return SimpleNamespace(open=open_, high=high, low=low, close=close,
                           volume=volume, delta=delta)


def _linha(componente, direcao, valor, forca, confianca, detalhe=""):
    return LinhaMatrizASG(componente=componente, direcao=direcao, valor=valor,
                          forca=forca, confianca=confianca,
                          procedencia=ProcedenciaASG.DERIVADO, detalhe=detalhe)


def _estado_com_candles(n=15, delta=5, volume=20, detalhe_maker=""):
    candles = tuple(_candle(100 + i, 100 + i + 2, 100 + i - 2, 100 + i + 1,
                            volume=volume, delta=delta) for i in range(n))
    maker = _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA,
                   detalhe=detalhe_maker)
    return EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=maker,
                      leituras=(), largura=1920, altura=1055, candles_m15=candles)


# ============================================================ componentes
def test_componentes_micro_traz_os_cinco_ids():
    entrada = mapa.componentes_micro(_estado_com_candles())
    assert set(entrada.keys()) == {"A", "B", "R", "W", "M"}


def test_componente_w_e_o_inverso_do_desequilibrio():
    entrada = mapa.componentes_micro(_estado_com_candles(delta=10, volume=20))
    assert entrada["W"] == pytest.approx(-entrada["B"])


def test_movimento_positivo_quando_fechamentos_sobem():
    candles = tuple(_candle(0, 0, 0, close=100 + i, volume=1, delta=0) for i in range(10))
    estado = EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                        leituras=(), largura=1920, altura=1055, candles_m15=candles)
    assert mapa._movimento(candles, mapa.JANELA_MOVIMENTO_MACRO) > 0


def test_movimento_sem_candles_suficientes_e_zero():
    assert mapa._movimento((), 5) == 0.0


def test_componentes_reaproveitam_ranking_do_maker():
    estado = _estado_com_candles(detalhe_maker="1o AGRESSAO  +80%  giro 3\n2o REPOSICAO  +50%  giro 1")
    entrada = mapa.componentes_micro(estado)
    assert entrada["A"] == pytest.approx(0.80)
    assert entrada["R"] == pytest.approx(0.50)


# ============================================================ construir_entrada
def test_construir_entrada_sem_candles_devolve_none():
    estado = EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                        leituras=(), largura=1920, altura=1055)
    entrada = mapa.construir_entrada_dominancia(estado)
    assert entrada["componentes_micro"] is None
    assert entrada["componentes_macro"] is None
    assert entrada["qualidade_micro"] == 0.0


def test_construir_entrada_com_candles_devolve_componentes():
    entrada = mapa.construir_entrada_dominancia(_estado_com_candles())
    assert entrada["componentes_micro"] is not None
    assert entrada["componentes_macro"] is not None
    assert entrada["amostras_micro"] == 15


def test_construir_entrada_alimenta_o_motor_sem_excecao():
    motor = dom.MotorDominancia("teste")
    entrada = mapa.construir_entrada_dominancia(_estado_com_candles())
    snapshot = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1, instrumento="WDO", modo="LIVE",
        idade_ms=10.0, **entrada,
    )
    assert snapshot.estado is not None


# ============================================================ rotulo/desenho
def test_rotulo_estado_conhece_todos_os_estados():
    for estado in dom.EstadoDominancia:
        assert isinstance(mapa.rotulo_estado(estado), str)


def _desenha_sem_excecao(snapshot, rect=QRect(0, 0, 300, 20)):
    imagem = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    try:
        mapa.desenhar_estado(painter, rect, snapshot)
    finally:
        painter.end()


def test_desenha_estado_sem_snapshot_sem_excecao(qapp):
    _desenha_sem_excecao(None)


def test_desenha_estado_ultra_buy_sem_excecao(qapp):
    motor = dom.MotorDominancia("t")
    entrada = mapa.construir_entrada_dominancia(_estado_com_candles(delta=20, volume=20))
    snapshot = motor.processar(event_id="e1", sequencia=1, timestamp_ns=1, instrumento="WDO",
                               modo="LIVE", idade_ms=10.0, **entrada)
    _desenha_sem_excecao(snapshot)


def test_desenha_estado_regiao_pequena_nao_estoura(qapp):
    _desenha_sem_excecao(None, rect=QRect(0, 0, 5, 5))
