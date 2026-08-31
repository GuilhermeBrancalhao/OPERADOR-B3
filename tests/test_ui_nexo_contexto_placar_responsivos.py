"""Mede o texto pintado, inclusive a parte que Qt cortaria silenciosamente."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter

from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui import tema_asg
from fluxopro.ui.paineis.asg import ConfiancaASG, DirecaoASG
from fluxopro.ui.paineis.nexo import EstadoNexo, contexto, estatistica


class _TextoPintado(QPainter):
    def __init__(self, imagem):
        super().__init__(imagem)
        self.textos = []

    def drawText(self, *args):  # noqa: N802
        if len(args) == 3 and isinstance(args[0], QRect):
            rect, flags, texto = args
            self.textos.append((texto, QRect(rect), self.boundingRect(rect, flags, texto),
                                self.font().pixelSize()))
        return super().drawText(*args)


def _estado(presenca="-100% SUAV", ritmo="DESACELERANDO"):
    def linha(valor, direcao, forca):
        return SimpleNamespace(valor=valor, direcao=direcao, forca=forca,
                               confianca=ConfiancaASG.ALTA)

    return EstadoNexo(
        snapshot=None, serie=tuple((i * 1_000_000_000, 10_000, (-1) ** i * 0.4, 1)
                                  for i in range(32)),
        grid=WDO_GRID, paleta=None, maker=None,
        leituras=(("HORIZONTE", linha("+100", DirecaoASG.COMPRA, 0.4)),
                  ("PULSO", linha("-100", DirecaoASG.VENDA, -0.5)),
                  ("PRESENCA", linha(presenca, DirecaoASG.VENDA, -1.0)),
                  ("RITMO", linha(ritmo, DirecaoASG.VENDA, -0.2))),
        largura=1280, altura=720,
    )


def _pintar(modulo, rect, estado):
    imagem = QImage(rect.right() + 8, rect.bottom() + 8, QImage.Format.Format_ARGB32)
    imagem.fill(tema_asg.NEXO_FUNDO)
    painter = _TextoPintado(imagem)
    painter.setClipRect(rect)
    try:
        modulo.desenhar(painter, rect, estado)
    finally:
        painter.end()
    return painter.textos


def _sem_corte(registro, regiao):
    texto, caixa, tinta, _ = registro
    assert regiao.contains(caixa), (texto, caixa, regiao)
    # Tolerancia de 1px para arredondamento de metricas Qt, nao para letras.
    assert caixa.adjusted(-1, -1, 1, 1).contains(tinta), (texto, caixa, tinta)


@pytest.mark.parametrize("largura,altura", [(1280, 600), (1480, 780), (1920, 960)])
@pytest.mark.parametrize("fracao", [0.26, 0.23], ids=["central-ai", "classico"])
@pytest.mark.parametrize("valor", ["DESACELERANDO", "ACELERANDO", "SEM DADOS"])
def test_contexto_mostra_nome_valor_e_suav_completos(qapp, largura, altura, fracao, valor):
    rect = QRect(13, 17, round(largura * fracao), round(altura * 0.56))
    estado = _estado(ritmo=valor)
    registros = _pintar(contexto, rect, estado)
    desejados = [r for r in registros if r[0] in {"PRESENCA", "-100% SUAV", "RITMO", valor}]
    assert len(desejados) == 4
    for registro in desejados:
        _sem_corte(registro, rect)
        assert registro[3] >= 7
    # Os dois pares nao se sobrepoem entre si, nem nome com seu valor.
    for i, a in enumerate(desejados):
        for b in desejados[i + 1:]:
            assert not a[2].intersects(b[2]), (a, b)


@pytest.mark.parametrize("largura,altura", [(1280, 600), (1480, 780), (1920, 960)])
@pytest.mark.parametrize("fracao,fracao_altura", [(0.37, 0.34), (0.40, 0.21)],
                         ids=["central-ai", "classico"])
def test_placar_preserva_percentuais_contagem_e_qualificador(qapp, largura, altura,
                                                           fracao, fracao_altura):
    rect = QRect(13, 17, round(largura * fracao), round(altura * fracao_altura))
    registros = _pintar(estatistica, rect, _estado())
    legendas = [r for r in registros if "CONV" in r[0]]
    assert len(legendas) == 2
    assert "1 DE 4 LEITURAS" in legendas[0][0]
    assert "3 DE 4 LEITURAS" in legendas[1][0]
    numeros = [r for r in registros if r[0] in {"10%", "42%"}]
    assert len(numeros) == 2
    for registro in legendas:
        _sem_corte(registro, rect)
        assert "PONDERADA" in registro[0]
        assert "CONVICCAO" in registro[0] or "CONV." in registro[0]
        assert registro[3] >= (7 if "\n" in registro[0] else 6)
    for numero, legenda in zip(numeros, legendas):
        _sem_corte(numero, rect)
        assert numero[3] >= 16
        assert not numero[2].intersects(legenda[2])


def test_leituras_largas_preservam_disposicao_lado_a_lado(qapp):
    rect = QRect(13, 17, 260, 120)
    imagem = QImage(300, 160, QImage.Format.Format_ARGB32)
    painter = _TextoPintado(imagem)
    try:
        contexto._leituras(painter, rect, _estado().leituras[2:])
    finally:
        painter.end()
    nome, valor = painter.textos[:2]
    assert nome[1].top() == valor[1].top()
    assert nome[1].right() < valor[1].left()
    for registro in painter.textos:
        _sem_corte(registro, rect)


def test_placar_largo_preserva_legenda_original_em_uma_linha(qapp):
    rect = QRect(13, 17, 320, 100)
    imagem = QImage(350, 140, QImage.Format.Format_ARGB32)
    painter = _TextoPintado(imagem)
    try:
        estatistica._desenhar_placar(painter, rect, "COMPRA", 0.5, 2, 4, tema_asg.NEXO_VERDE)
    finally:
        painter.end()
    legenda = painter.textos[-1]
    assert legenda[0] == "2 DE 4 LEITURAS · CONVICCAO PONDERADA"
    assert legenda[3] == 6
    _sem_corte(legenda, rect)
