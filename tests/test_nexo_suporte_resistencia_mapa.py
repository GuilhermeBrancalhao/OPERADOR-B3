"""Mapeamento EstadoNexo -> motor de Suporte/Resistência
(`fluxopro/ui/paineis/nexo/suporte_resistencia.py`). Cobre a extração dos 8
componentes a partir de dados que o projeto já calcula (candles, ranking do
MakerProxy, Renko, RITMO) e o desenho do selo sem exceção.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from fluxopro.analytics import suporte_resistencia as sr  # noqa: E402
from fluxopro.analytics.renko import FaseRenko  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DirecaoASG,
    LinhaMatrizASG,
    ProcedenciaASG,
)
from fluxopro.ui.paineis.nexo import EstadoNexo, suporte_resistencia as mapa  # noqa: E402


def _candle(open_, high, low, close, volume, delta):
    return SimpleNamespace(open=open_, high=high, low=low, close=close,
                           volume=volume, delta=delta)


def _linha(componente, direcao, valor, forca, confianca, detalhe=""):
    return LinhaMatrizASG(componente=componente, direcao=direcao, valor=valor,
                          forca=forca, confianca=confianca,
                          procedencia=ProcedenciaASG.DERIVADO, detalhe=detalhe)


# ============================================================ ranking parser
def test_componentes_do_ranking_extrai_nome_e_percentual():
    texto = "1o AGRESSAO  +70%  giro 3\n2o REPOSICAO  -20%  giro 1\n3o CLIPS  +14%  giro 7"
    componentes = mapa.componentes_do_ranking_maker(texto)
    assert componentes == {"AGRESSAO": 0.70, "REPOSICAO": -0.20, "CLIPS": 0.14}


def test_componentes_do_ranking_vazio_devolve_dict_vazio():
    assert mapa.componentes_do_ranking_maker("") == {}
    assert mapa.componentes_do_ranking_maker(None) == {}


def test_componente_agressao_usa_ranking_quando_presente():
    maker = _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA,
                   detalhe="1o AGRESSAO  +70%  giro 3")
    assert mapa.componente_agressao(maker) == pytest.approx(0.70)


def test_componente_agressao_cai_para_forca_agregada_sem_ranking():
    maker = _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA, detalhe="")
    assert mapa.componente_agressao(maker) == pytest.approx(0.45)


def test_componente_agressao_sem_maker_e_zero():
    assert mapa.componente_agressao(None) == 0.0


def test_componente_reposicao_prefere_reposicao_a_absorcao():
    maker = _linha("MAKERPROXY", DirecaoASG.VENDA, "-30%", -0.30, ConfiancaASG.MEDIA,
                   detalhe="1o REPOSICAO  -60%  giro 2\n2o ABSORCAO  +10%  giro 1")
    assert mapa.componente_reposicao(maker) == pytest.approx(-0.60)


def test_componente_reposicao_usa_absorcao_quando_reposicao_ausente():
    maker = _linha("MAKERPROXY", DirecaoASG.VENDA, "-30%", -0.30, ConfiancaASG.MEDIA,
                   detalhe="1o ABSORCAO  +25%  giro 1")
    assert mapa.componente_reposicao(maker) == pytest.approx(0.25)


# ============================================================ candles
def test_desequilibrio_le_o_candle_fechado_nao_o_em_formacao():
    fechado = _candle(100, 105, 99, 104, volume=100, delta=50)
    em_formacao = _candle(104, 106, 103, 105, volume=10, delta=-9)
    assert mapa.desequilibrio_de_candles((fechado, em_formacao)) == pytest.approx(0.5)


def test_desequilibrio_sem_candles_suficientes_e_zero():
    assert mapa.desequilibrio_de_candles(()) == 0.0
    assert mapa.desequilibrio_de_candles((_candle(1, 2, 0, 1, 10, 5),)) == 0.0


def test_rejeicao_pavio_inferior_maior_e_defesa_compradora():
    candle = _candle(open_=100, high=101, low=90, close=100.5, volume=10, delta=1)
    assert mapa._rejeicao_de_candle(candle) > 0


def test_rejeicao_pavio_superior_maior_e_defesa_vendedora():
    candle = _candle(open_=100, high=110, low=99, close=99.5, volume=10, delta=-1)
    assert mapa._rejeicao_de_candle(candle) < 0


def test_rejeicao_sem_candle_e_zero():
    assert mapa._rejeicao_de_candle(None) == 0.0


def test_delta_acumulado_soma_janela_recente():
    candles = tuple(_candle(0, 0, 0, 0, volume=10, delta=5) for _ in range(10))
    assert mapa._delta_acumulado(candles) == pytest.approx(0.5)


def test_estabilidade_preco_constante_e_maxima():
    candles = tuple(_candle(0, 0, 0, close=100.0, volume=1, delta=0) for _ in range(5))
    assert mapa._estabilidade(candles) == pytest.approx(1.0)


def test_estabilidade_amostra_insuficiente_e_zero():
    assert mapa._estabilidade((_candle(0, 0, 0, 100, 1, 0),)) == 0.0


# ============================================================ estrutura (renko)
class _Tijolo:
    def __init__(self, direcao):
        self.direcao = direcao


def test_estrutura_tendencia_de_alta():
    valor = mapa._estrutura(FaseRenko.TENDENCIA, (_Tijolo(1),))
    assert valor > 0


def test_estrutura_tendencia_de_baixa():
    valor = mapa._estrutura(FaseRenko.TENDENCIA, (_Tijolo(-1),))
    assert valor < 0


def test_estrutura_possivel_inversao_inverte_o_sinal_da_tendencia():
    valor = mapa._estrutura(FaseRenko.POSSIVEL_INVERSAO, (_Tijolo(1),))
    assert valor < 0


def test_estrutura_sem_tijolos_e_zero():
    assert mapa._estrutura(FaseRenko.INDEFINIDA, ()) == 0.0


# ============================================================ construir_entrada_sr
def _estado_completo():
    candles = tuple(_candle(100 + i, 100 + i + 2, 100 + i - 2, 100 + i + 1,
                            volume=20, delta=5) for i in range(15))
    leituras = (
        ("HORIZONTE", _linha("MACRO", DirecaoASG.COMPRA, "+400", 0.4, ConfiancaASG.ALTA)),
        ("PULSO", _linha("MICRO", DirecaoASG.COMPRA, "+200", 0.6, ConfiancaASG.ALTA)),
        ("PRESENCA", _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA,
                            detalhe="1o AGRESSAO  +70%  giro 3\n2o REPOSICAO  +40%  giro 2")),
        ("RITMO", _linha("VELOCIMETRO", DirecaoASG.COMPRA, "ACELERANDO", 0.5, ConfiancaASG.MEDIA)),
    )
    maker = leituras[2][1]
    return EstadoNexo(
        snapshot=None, serie=((0, 10050, 0.0, 0),), grid=None, paleta=None,
        maker=maker, leituras=leituras, largura=1920, altura=1055,
        candles_m15=candles, fase_renko=FaseRenko.TENDENCIA,
        tijolos_renko=(_Tijolo(1), _Tijolo(1), _Tijolo(1)),
        vap_poc=10040, vap_val=10020, vap_vah=10060,
    )


def test_construir_entrada_sr_devolve_micro_macro_e_zonas():
    entrada = mapa.construir_entrada_sr(_estado_completo())
    assert entrada["micro"] is not None
    assert entrada["macro"] is not None
    assert -1.0 <= entrada["micro"].score <= 1.0
    assert -1.0 <= entrada["macro"].score <= 1.0
    assert len(entrada["zonas_candidatas"]) == 3  # POC, VAL, VAH
    assert entrada["ultimo_preco"] == 10050


def test_construir_entrada_sr_sem_candles_nem_vap_nao_quebra():
    estado = EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                        leituras=(), largura=1920, altura=1055)
    entrada = mapa.construir_entrada_sr(estado)
    assert entrada["zonas_candidatas"] == ()
    assert entrada["ultimo_preco"] is None
    assert entrada["micro"].amostras == 0


# ============================================================ desenho
def _desenha_sem_excecao(snapshot, rect=QRect(0, 0, 700, 60)):
    imagem = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    try:
        mapa.desenhar_selo(painter, rect, snapshot)
    finally:
        painter.end()


def test_desenha_selo_sem_snapshot_sem_excecao(qapp):
    _desenha_sem_excecao(None)


def test_desenha_selo_unavailable_sem_excecao(qapp):
    snapshot = sr.SuporteResistenciaSnapshot(
        schema_version=1, stream_id="t", event_id="e1", sequencia=1, timestamp_ns=1,
        instrumento="WDO", tick_size=0.5, ultimo_preco=None, micro=None, macro=None,
        contra_giro=sr.ContraGiro(None, None, False), zonas=(), dominante=None,
        alerta=sr.AlertaSR.NENHUM,
        saude=sr.Saude(sr.EstadoFeed.UNAVAILABLE, 9999.0, None, None, "teste"),
    )
    _desenha_sem_excecao(snapshot)


def test_desenha_selo_suporte_ao_vivo_sem_excecao(qapp):
    motor = sr.MotorSuporteResistencia("t")
    entrada = mapa.construir_entrada_sr(_estado_completo())
    snapshot = motor.processar(
        event_id="e1", sequencia=1, timestamp_ns=1_000_000_000, instrumento="WDO",
        tick_size=0.5, agora_ns=1_000_000_000, **entrada,
    )
    _desenha_sem_excecao(snapshot)


def test_desenha_selo_regiao_pequena_nao_estoura(qapp):
    _desenha_sem_excecao(None, rect=QRect(0, 0, 10, 10))
