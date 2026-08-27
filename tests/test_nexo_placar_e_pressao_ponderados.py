"""Cobre o achado do operador (27/08/2026): Placar Estatistico e o
indicador 56/44 "players" precisavam de logica mais tecnica, nao so
explicacao. As duas funcoes puras abaixo sao a formula em si — sem
tocar em QPainter, faceis de verificar isoladamente.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.ui.paineis.asg import ConfiancaASG, DirecaoASG, LinhaMatrizASG, ProcedenciaASG
from fluxopro.ui.paineis.nexo import estatistica, pressao
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.core.eventos import WDO_GRID


def _linha(nome, forca, confianca, direcao=None):
    if direcao is None:
        direcao = DirecaoASG.COMPRA if forca > 0 else DirecaoASG.VENDA if forca < 0 else DirecaoASG.NEUTRA
    return (nome, LinhaMatrizASG(
        componente=nome, direcao=direcao, valor="", forca=forca,
        confianca=confianca, procedencia=ProcedenciaASG.DERIVADO,
    ))


def test_placar_ponderado_favorece_leitura_de_alta_confianca():
    leituras = (
        _linha("HORIZONTE", 0.9, ConfiancaASG.ALTA),
        _linha("PULSO", -0.9, ConfiancaASG.BAIXA),
    )
    score = estatistica.placar_ponderado(leituras)
    assert score > 0, "leitura ALTA (+0.9) deve pesar mais que BAIXA (-0.9)"


def test_placar_ponderado_ignora_leitura_indisponivel():
    leituras = (
        _linha("HORIZONTE", 0.9, ConfiancaASG.ALTA),
        _linha("PULSO", -1.0, ConfiancaASG.INDISPONIVEL),
    )
    score = estatistica.placar_ponderado(leituras)
    assert score == 0.9, "confianca INDISPONIVEL tem peso 0 — nao deveria puxar o score"


def test_placar_ponderado_sem_leituras_com_peso_e_zero():
    leituras = (_linha("HORIZONTE", 0.9, ConfiancaASG.INDISPONIVEL),)
    assert estatistica.placar_ponderado(leituras) == 0.0


def test_placar_ponderado_fica_em_menos1_mais1():
    leituras = tuple(_linha(f"L{i}", 1.0, ConfiancaASG.ALTA) for i in range(4))
    assert estatistica.placar_ponderado(leituras) == 1.0


def test_desenha_contagem_sem_excecao(qapp):
    leituras = (
        _linha("HORIZONTE", 0.5, ConfiancaASG.ALTA),
        _linha("PULSO", -0.3, ConfiancaASG.MEDIA),
        _linha("PRESENCA", 0.1, ConfiancaASG.BAIXA),
        _linha("RITMO", 0.0, ConfiancaASG.INDISPONIVEL),
    )
    estado = EstadoNexo(
        snapshot=None, serie=((0, 100000, 0.1, 1),), grid=WDO_GRID, paleta=None,
        maker=None, leituras=leituras, largura=400, altura=150,
    )
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), estado)
    finally:
        painter.end()


def test_pressao_composta_pesos_somam_um():
    assert abs(pressao.PESO_MAKER_PRESSAO + pressao.PESO_RITMO_PRESSAO - 1.0) < 1e-9


def test_pressao_composta_diverge_do_maker_puro_quando_ritmo_discorda():
    so_maker = pressao.pressao_composta(maker_forca=0.8, ritmo_forca=0.0)
    com_ritmo_contra = pressao.pressao_composta(maker_forca=0.8, ritmo_forca=-1.0)
    assert com_ritmo_contra < so_maker, (
        "ritmo contra deve puxar o score pra baixo — antes de 27/08/2026 "
        "este numero era so o maker, nunca reagia ao ritmo"
    )


def test_pressao_composta_fica_em_menos1_mais1():
    assert pressao.pressao_composta(1.0, 1.0) == 1.0
    assert pressao.pressao_composta(-1.0, -1.0) == -1.0
