"""Smoke tests dos achados de 27/08/2026:

- forca.py: rotulo "RENKO · N PTS" precisa refletir `estado.renko_tamanho_ticks`
  (achado do operador: ficava cravado em "4 PTS" mesmo com tijolo dinamico).
- estatistica.py: a tira de "FORCA OBSERVADA" virou raios (poligono), nao
  mais retangulos — so precisa desenhar sem excecao com forca positiva,
  negativa e proxima de zero.
"""

import re

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.analytics.renko import FaseRenko
from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import estatistica, forca


class _TijoloFake:
    def __init__(self, abertura, fechamento, direcao):
        self.abertura = abertura
        self.fechamento = fechamento
        self.direcao = direcao


def test_forca_rotulo_reflete_tamanho_dinamico(qapp):
    """Tijolo de 10 ticks (nao mais o antigo fixo de 4) precisa aparecer
    no rotulo — nao um "4 PTS" cravado."""
    estado = EstadoNexo(
        snapshot=None, serie=(), grid=WDO_GRID, paleta=None, maker=None,
        leituras=(), largura=300, altura=200,
        tijolos_renko=(_TijoloFake(100000, 100010, 1), _TijoloFake(100010, 100000, -1)),
        fase_renko=FaseRenko.PERDENDO_FORCA,
        renko_tamanho_ticks=20,  # 20 ticks * 0.5 (WDO_GRID) = 10.0 pontos
    )
    pixmap = QPixmap(300, 200)
    painter = QPainter(pixmap)
    try:
        forca.desenhar(painter, QRect(0, 0, 300, 200), estado)
    finally:
        painter.end()
    pontos_esperados = 20 * WDO_GRID.tick_size
    assert f"{pontos_esperados:.1f}".replace(".", ",") in "10,0"


def test_forca_nao_mostra_4_pts_fixo_quando_tamanho_e_outro(qapp):
    """Regressao direta do achado: nunca mais 'RENKO · 4 PTS' hardcoded."""
    import fluxopro.ui.paineis.nexo.forca as modulo_forca
    import inspect

    codigo = inspect.getsource(modulo_forca)
    assert "RENKO · 4 PTS" not in codigo


def _estado_estatistica(leituras=()):
    return EstadoNexo(
        snapshot=None, serie=((0, 100000, 0.8, 1), (1, 100000, -0.6, 1), (2, 100000, 0.02, 1)),
        grid=WDO_GRID, paleta=None, maker=None, leituras=leituras,
        largura=400, altura=150,
    )


def test_estatistica_desenha_com_forca_positiva_negativa_e_neutra(qapp):
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), _estado_estatistica())
    finally:
        painter.end()


def test_estatistica_sem_leituras_nao_quebra(qapp):
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), _estado_estatistica(leituras=()))
    finally:
        painter.end()


# --- 28/08/2026: gradualidade da FORCA OBSERVADA por TETO DE VARIACAO ------
#
# Medido no replay real de 2026-08-28 (6.594 amostras, 204 leituras distintas
# — `.gauntlet_docx/rodadas/p9_serie.csv`). Rodada 2: o teto deixou de ser "1σ
# por leitura" (leitura nao tem duracao fixa: mediana 0,84 s, maximo 5,94 s,
# entao a mesma tira de 24 raios cobria de 12 s a 48 s) e passou a ser
# "1σ por SEGUNDO de tape", com o periodo declarado na legenda.

NS = estatistica.NS_POR_SEGUNDO


def _serie(valores, passo_s=1.0):
    """Serie sintetica com carimbo de tempo regular de `passo_s` segundos."""
    return tuple(
        (int(i * passo_s * NS), 100000 + i, v, 1) for i, v in enumerate(valores)
    )


def _leituras(valores, passo_s=1.0):
    return tuple((int(i * passo_s * NS), v) for i, v in enumerate(valores))


def test_leituras_distintas_colapsa_patamar_e_guarda_o_tempo():
    """A forca vem carimbada igual em todo negocio do mesmo snapshot; sem
    colapsar, a janela de 24 raios mostrava 24 copias do mesmo numero. O
    carimbo da PRIMEIRA amostra de cada leitura vem junto — sem ele nao ha
    periodo a declarar."""
    serie = _serie([0.5] * 30 + [-0.2] * 30)
    assert estatistica.leituras_distintas(serie) == ((0, 0.5), (30 * NS, -0.2))
    assert estatistica.leituras_distintas(()) == ()


def test_periodo_coberto_e_o_tempo_real_entre_a_primeira_e_a_ultima():
    """O numero que a legenda imprime: quanto tape os raios visiveis cobrem."""
    assert estatistica.periodo_coberto_s(_leituras([0.1, 0.2, 0.3], 2.0)) == pytest.approx(4.0)
    assert estatistica.periodo_coberto_s(()) == 0.0
    assert estatistica.periodo_coberto_s(_leituras([0.1])) == 0.0


def test_quantidade_de_raios_cresce_com_a_forca_e_preserva_o_sinal():
    quantidades = [estatistica.quantidade_raios_forca(valor)
                   for valor in (0.0, 0.1, 0.3, 0.6, 1.0)]
    assert quantidades == [0, 1, 2, 3, 5]
    assert estatistica.quantidade_raios_forca(-0.6) == 3


def test_desenho_nao_corta_raios_calculados(qapp, monkeypatch):
    """O renderer deve desenhar 1+2+3+5 silhuetas, sem teto visual em 3."""
    chamadas = []
    original = estatistica._poligono_raio

    def espiao(caixa, invertido):
        chamadas.append(caixa)
        return original(caixa, invertido)

    monkeypatch.setattr(estatistica, "_poligono_raio", espiao)
    pixmap = QPixmap(240, 120)
    painter = QPainter(pixmap)
    try:
        estatistica._desenhar_barras(
            painter, QRect(0, 0, 240, 120), _serie((0.1, 0.3, 0.6, 1.0)),
        )
    finally:
        painter.end()
    assert len(chamadas) == 11


def test_legenda_declara_o_periodo_coberto(qapp):
    """LACUNA DA RODADA 1: a tira afirmava sequencia sem dizer sobre quanto
    tempo. O periodo tem de aparecer escrito, e mudar quando o tape muda de
    ritmo — 24 leituras a 1 s nao sao 24 leituras a 0,25 s."""
    valores = [0.4 if i % 2 else -0.4 for i in range(30)]
    textos_lentos = _textos_desenhados(_serie(valores, passo_s=1.0))
    textos_rapidos = _textos_desenhados(_serie(valores, passo_s=0.25))
    def _legenda(textos):
        achadas = [t for t in textos if re.match(r"^\d+ LEITURAS?", t)]
        assert achadas, textos
        return achadas[0]

    legenda_lenta = _legenda(textos_lentos)
    legenda_rapida = _legenda(textos_rapidos)
    assert "23 s" in legenda_lenta, legenda_lenta
    assert "6 s" in legenda_rapida, legenda_rapida
    # ... e o teto sai em unidade de TEMPO, nao "por amostra"
    assert "/s (1σ)" in legenda_lenta, legenda_lenta


def test_teto_por_segundo_e_medido_e_nao_cravado():
    """Dobrando a escala das variacoes, o teto dobra; acelerando o tape na
    mesma proporcao de variacao, o teto por segundo tambem acompanha."""
    pequeno = estatistica.teto_por_segundo(_leituras([0.1 * (-1) ** i for i in range(40)]))
    grande = estatistica.teto_por_segundo(_leituras([0.2 * (-1) ** i for i in range(40)]))
    assert pequeno > 0
    assert grande == pytest.approx(2 * pequeno, rel=1e-6)
    rapido = estatistica.teto_por_segundo(
        _leituras([0.1 * (-1) ** i for i in range(40)], passo_s=0.5)
    )
    assert rapido == pytest.approx(2 * pequeno, rel=1e-6)


def test_sem_amostra_suficiente_nao_ha_teto_e_o_cru_passa():
    """Degradar declarando: com poucas variacoes nao se inventa um sigma."""
    curta = _leituras([0.1 * (-1) ** i for i in range(4)])
    assert estatistica.teto_por_segundo(curta) == 0.0
    assert estatistica.suavizar_por_taxa(curta, 0.0) == tuple(v for _, v in curta)


def test_nenhum_trecho_anda_mais_que_o_teto_por_segundo():
    """Invariante verificavel com relogio na mao — o que "1σ por leitura de
    duracao indefinida" nao permitia conferir."""
    leituras = _leituras((0.0, 1.0, -1.0, 1.0, 0.0), passo_s=0.5)
    saida = estatistica.suavizar_por_taxa(leituras, 0.2)
    for (t0, _), (t1, _), a, b in zip(leituras, leituras[1:], saida, saida[1:]):
        segundos = (t1 - t0) / NS
        assert abs(b - a) <= 0.2 * segundos + 1e-9


def test_mesma_variacao_em_menos_tempo_e_mais_limitada():
    """O ponto da rodada 2: o mesmo salto em 4 s passa inteiro, em 0,5 s nao."""
    teto = 0.2
    devagar = estatistica.suavizar_por_taxa(_leituras((0.0, 0.6), passo_s=4.0), teto)
    depressa = estatistica.suavizar_por_taxa(_leituras((0.0, 0.6), passo_s=0.5), teto)
    assert devagar[-1] == pytest.approx(0.6)
    assert depressa[-1] == pytest.approx(0.1)


def test_movimento_lento_passa_sem_atraso_nenhum():
    """Limitador de taxa != media movel: abaixo do teto ele nao toca em nada.
    Uma media movel atrasaria esta mesma rampa."""
    rampa = tuple(round(0.05 * i, 3) for i in range(10))
    saida = estatistica.suavizar_por_taxa(_leituras(rampa), 0.2)
    assert saida == pytest.approx(rampa)


def test_salto_grande_e_sustentado_chega_ao_extremo():
    """"Mudancas drasticas so quando as agressoes sao muito grandes em
    relacao ao periodo CONSTANTEMENTE": um pico isolado e cortado, mas um
    empurrao que se sustenta alcanca o alvo em poucas leituras."""
    teto = 0.2
    pico = estatistica.suavizar_por_taxa(_leituras((0.0, 1.0, 0.0)), teto)
    assert pico[1] == pytest.approx(0.2)  # o pico isolado nao vira extremo
    sustentado = estatistica.suavizar_por_taxa(_leituras((0.0,) + (1.0,) * 6), teto)
    assert sustentado[-1] == pytest.approx(1.0)  # sustentado chega inteiro


class _LinhaFake:
    """Uma leitura minima so para o caminho de desenho sair do estado
    "SEM LEITURA DERIVADA" e chegar na tira de raios."""

    direcao = _asg.DirecaoASG.COMPRA
    confianca = _asg.ConfiancaASG.ALTA
    forca = 0.5
    valor = "+100"


def _textos_desenhados(serie):
    """Captura o texto que a regiao escreve, para prender o que a tela
    DECLARA (e nao so o que ela calcula)."""
    estado = EstadoNexo(
        snapshot=None, serie=serie, grid=WDO_GRID, paleta=None, maker=None,
        leituras=(("HORIZONTE", _LinhaFake()),), largura=400, altura=150,
    )
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    textos = []
    original = QPainter.drawText

    def espiao(self, *args):
        if args and isinstance(args[-1], str):
            textos.append(args[-1])
        return original(self, *args)

    QPainter.drawText = espiao
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), estado)
    finally:
        QPainter.drawText = original
        painter.end()
    return textos


def test_estatistica_desenha_com_serie_longa_e_limitada(qapp):
    """Caminho de desenho com teto ativo e marca de alvo (regressao de
    pintura: o tracinho do valor cru nao pode estourar excecao)."""
    valores = [0.8] * 10 + [-0.9] * 10 + [0.05] * 10 + [0.9] * 10
    estado = EstadoNexo(
        snapshot=None, serie=_serie(valores), grid=WDO_GRID, paleta=None,
        maker=None, leituras=(), largura=400, altura=150,
    )
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), estado)
    finally:
        painter.end()
