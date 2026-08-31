"""Reforma 31/08/2026 de `fluxopro/ui/paineis/nexo/contexto.py`: MICRO/MACRO
migraram de texto para o Dual Market Velocity Gauge (dois arcos em contra-
rotação + prisma contínuo). Cobre a leitura de frescor, a extração de
MICRO/MACRO das `estado.leituras` e o desenho sem exceção nos estados
principais (disponível, indisponível, stale/replay).
"""

import dataclasses

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from fluxopro.core.eventos import WDO_GRID  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    LinhaMatrizASG,
    MatrizASGSnapshot,
    ProcedenciaASG,
    ProcessamentoASGSnapshot,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.nexo import EstadoNexo, contexto  # noqa: E402


def _linha(componente, direcao, valor, forca, confianca):
    return LinhaMatrizASG(
        componente=componente, direcao=direcao, valor=valor, forca=forca,
        confianca=confianca, procedencia=ProcedenciaASG.DERIVADO,
        detalhe="ESTRUTURA DO DIA",
    )


def _snapshot(estado_operacional=EstadoASG.AO_VIVO):
    return WorkspaceASGSnapshot(
        0,
        DadosASGSnapshot(0, estado=estado_operacional),
        ProcessamentoASGSnapshot(0, estado=estado_operacional),
        MatrizASGSnapshot(0, estado=estado_operacional),
        DecisaoASGSnapshot(0, estado=estado_operacional),
        TrilhaEvidenciasASGSnapshot(0, estado=estado_operacional),
        contexto_bruto=None,
    )


def _estado(macro_forca=0.3, micro_forca=0.6, macro_conf=ConfiancaASG.ALTA,
           micro_conf=ConfiancaASG.ALTA, estado_operacional=EstadoASG.AO_VIVO,
           com_maker=True):
    leituras = (
        ("HORIZONTE", _linha("MACRO", DirecaoASG.COMPRA if macro_forca >= 0 else DirecaoASG.VENDA,
                             f"{int(macro_forca * 2000):+d}", macro_forca, macro_conf)),
        ("PULSO", _linha("MICRO", DirecaoASG.COMPRA if micro_forca >= 0 else DirecaoASG.VENDA,
                         f"{int(micro_forca * 800):+d}", micro_forca, micro_conf)),
        ("PRESENCA", _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA)),
        ("RITMO", _linha("VELOCIMETRO", DirecaoASG.COMPRA, "ACELERANDO", 0.3, ConfiancaASG.MEDIA)),
    )
    maker = None
    if com_maker:
        maker = dataclasses.replace(
            _linha("MAKERPROXY", DirecaoASG.COMPRA, "+45%", 0.45, ConfiancaASG.ALTA),
            detalhe="1o DIVERGENCIA  +70%  giro 3\n2o AGRESSAO  -20%  giro 1",
        )
    return EstadoNexo(
        snapshot=_snapshot(estado_operacional), serie=((0, 100_000, 0.0, 0),),
        grid=WDO_GRID, paleta=None, maker=maker, leituras=leituras,
        largura=1920, altura=1055,
    )


def _desenha_sem_excecao(estado, rect=QRect(0, 0, 560, 600)):
    imagem = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    try:
        contexto.desenhar(painter, rect, estado)
    finally:
        painter.end()


# --------------------------------------------------------------- frescor
def test_frescor_ao_vivo():
    assert contexto.frescor_do_quadro(_estado(estado_operacional=EstadoASG.AO_VIVO)) == "LIVE"


def test_frescor_replay():
    assert contexto.frescor_do_quadro(_estado(estado_operacional=EstadoASG.REPLAY)) == "REPLAY"


def test_frescor_atrasado_e_stale():
    assert contexto.frescor_do_quadro(_estado(estado_operacional=EstadoASG.ATRASADO)) == "STALE"


@pytest.mark.parametrize("estado_op", [EstadoASG.ERRO, EstadoASG.DESCONHECIDO, EstadoASG.AGUARDANDO])
def test_frescor_sem_sinal_e_unavailable(estado_op):
    assert contexto.frescor_do_quadro(_estado(estado_operacional=estado_op)) == "UNAVAILABLE"


def test_frescor_sem_book_nao_degrada_o_gauge():
    """MICRO/MACRO vem do fluxo, nao do livro L2 — SEM_BOOK nao e motivo
    para este medidor especifico virar UNAVAILABLE."""
    assert contexto.frescor_do_quadro(_estado(estado_operacional=EstadoASG.SEM_BOOK)) == "LIVE"


def test_frescor_sem_snapshot_e_unavailable():
    estado = dataclasses.replace(_estado(), snapshot=None)
    assert contexto.frescor_do_quadro(estado) == "UNAVAILABLE"


# ------------------------------------------------------- extracao macro/micro
def test_linha_por_apelido_acha_horizonte_e_pulso():
    estado = _estado(macro_forca=0.4, micro_forca=-0.2)
    macro = contexto._linha_por_apelido(estado.leituras, "HORIZONTE")
    micro = contexto._linha_por_apelido(estado.leituras, "PULSO")
    assert macro.forca == pytest.approx(0.4)
    assert micro.forca == pytest.approx(-0.2)


def test_linha_por_apelido_ausente_devolve_none():
    assert contexto._linha_por_apelido((), "HORIZONTE") is None


def test_confiabilidade_indisponivel_e_zero():
    linha = _linha("MACRO", DirecaoASG.NEUTRA, "SEM DADOS", 0.0, ConfiancaASG.INDISPONIVEL)
    assert contexto._confiabilidade_de(linha) == 0.0


def test_confiabilidade_none_e_zero():
    assert contexto._confiabilidade_de(None) == 0.0


# --------------------------------------------------------------- desenho
def test_desenha_estado_positivo_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(macro_forca=0.38, micro_forca=0.62))


def test_desenha_estado_negativo_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(macro_forca=-0.44, micro_forca=-0.71))


def test_desenha_contragiro_divergente_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(macro_forca=-0.52, micro_forca=0.76,
                                 macro_conf=ConfiancaASG.MEDIA))


def test_desenha_ambos_indisponiveis_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(macro_forca=0.0, micro_forca=0.0,
                                 macro_conf=ConfiancaASG.INDISPONIVEL,
                                 micro_conf=ConfiancaASG.INDISPONIVEL))


def test_desenha_stale_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(estado_operacional=EstadoASG.ATRASADO))


def test_desenha_sem_maker_sem_excecao(qapp):
    _desenha_sem_excecao(_estado(com_maker=False))


def test_desenha_sem_leituras_sem_excecao(qapp):
    estado = dataclasses.replace(_estado(), leituras=())
    _desenha_sem_excecao(estado)


def test_desenha_regiao_pequena_nao_estoura(qapp):
    _desenha_sem_excecao(_estado(), rect=QRect(0, 0, 40, 40))


def test_ambos_indisponiveis_composto_e_zero_com_rotulo_sem_dado():
    """Denominador zero e '0 = SEM DADO', nunca BALANCO operacional — a
    UI precisa marcar a diferenca (documento de referencia, secao 4)."""
    macro = _linha("MACRO", DirecaoASG.NEUTRA, "SEM DADOS", 0.0, ConfiancaASG.INDISPONIVEL)
    micro = _linha("MICRO", DirecaoASG.NEUTRA, "SEM DADOS", 0.0, ConfiancaASG.INDISPONIVEL)
    from fluxopro.analytics import velocidade_dual as vd

    confiab_macro = contexto._confiabilidade_de(macro)
    confiab_micro = contexto._confiabilidade_de(micro)
    assert confiab_macro == 0.0 and confiab_micro == 0.0
    composto = vd.composto_micro_macro(0.0, confiab_micro, 0.0, confiab_macro)
    assert composto == 0.0
