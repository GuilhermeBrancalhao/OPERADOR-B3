"""Mede o texto pintado, inclusive a parte que Qt cortaria silenciosamente."""

import dataclasses
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



def _estado_com_zona(score=0.9, lado="RESISTENCIA", preco=10439):
    """`EstadoNexo` com um `sr_snapshot` — o placar novo le a ZONA, nao as
    leituras da matriz."""

    from fluxopro.analytics import suporte_resistencia as sr

    zona = sr.Zona(id="z", lado=getattr(sr.LadoZona, lado), preco=preco,
                   inferior=preco - 4, superior=preco + 4, score=score,
                   confianca=0.9, toques=4, fontes=("vap-poc",),
                   status=sr.EstadoZona.ATIVA)
    snapshot = SimpleNamespace(zonas=(zona,), dominante=zona, ultimo_preco=10400,
                               tick_size=0.5,
                               saude=SimpleNamespace(estado=sr.EstadoFeed.LIVE))
    base = _estado()
    return dataclasses.replace(base, sr_snapshot=snapshot)


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
def test_placar_declara_intensidade_regiao_e_nivel_sem_corte(qapp, largura, altura,
                                                            fracao, fracao_altura):
    """CONTRATO NOVO (31/08/2026) — a regiao deixou de mostrar a contagem
    ponderada das 4 leituras (que vivia empatada e nao falava da regiao de
    preco) e passou a ser o PLACAR DE SUPORTE/RESISTENCIA, com a logica
    conferida nas aulas da SG: intensidade em raios, preco da REGIAO e
    termometro do NIVEL.

    O que este teste preserva do contrato antigo, porque continua valendo em
    qualquer redesenho: nenhum rotulo pode ser CORTADO e a tipografia tem de
    ficar legivel nas tres resolucoes.
    """

    rect = QRect(13, 17, round(largura * fracao), round(altura * fracao_altura))
    registros = _pintar(estatistica, rect, _estado_com_zona())
    textos = [r[0] for r in registros]
    assert any("INTENSIDADE" in t for t in textos), textos
    assert any("REGI" in t for t in textos), textos
    assert any("TERMOMETRO" in t or "TERM" in t for t in textos), textos
    # o preco da regiao (numero grande) tem de estar escrito
    assert any("5.219,5" in t for t in textos), textos
    for registro in registros:
        _sem_corte(registro, rect)
        assert registro[3] >= 6, registro


def test_placar_mostra_um_lado_por_vez(qapp):
    """A aula: "alerta de resistencia maxima OU alerta de suporte maximo".
    O lado oposto aparece zerado, nunca escondido."""

    rect = QRect(13, 17, 520, 240)
    textos = [r[0] for r in _pintar(estatistica, rect, _estado_com_zona())]
    assert "BUY" in textos and "SELL" in textos
    assert "0" in textos, "o lado oposto tem de aparecer ZERADO, nao sumir"


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
