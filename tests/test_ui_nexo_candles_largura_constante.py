"""Cobre o defeito de 27/08/2026 relatado pelo operador: "os candle comeca
muito grande quando comeca o mercado e depois vao se ajustando e mudando de
tamanho".

A causa era a largura do corpo vir de `area_plot.width() // (len(velas)*2)`
— funcao da QUANTIDADE de velas ja formadas. Com 2 candles na abertura, cada
corpo tinha ~170px (o "retangulo verde gigante" do baseline) e encolhia a
cada vela nova. O teste mede a largura REAL pintada, interceptando o
`QPainter`, em tres momentos da sessao.
"""

from types import SimpleNamespace

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter

from fluxopro.ui.paineis.nexo import EstadoNexo, candles as modulo_candles


class _Candle(SimpleNamespace):
    pass


def _candles(n, passo_min=5):
    saida = []
    for i in range(n):
        base = 100_000 + (i % 5)
        saida.append(_Candle(
            open=base, close=base + 2, high=base + 4, low=base - 3,
            volume=10 + i, timestamp_ns=i * passo_min * 60 * 1_000_000_000,
        ))
    return tuple(saida)


class _PainterEspiao(QPainter):
    """Registra as larguras dos retangulos preenchidos na area do grafico."""

    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.larguras = []

    def fillRect(self, *args):  # noqa: N802 — assinatura do Qt
        if args and isinstance(args[0], QRect):
            self.larguras.append(args[0].width())
        super().fillRect(*args)


def _larguras_de_velas(estado_base, n_velas, rect):
    imagem = QImage(rect.width() + rect.left(), rect.height() + rect.top(),
                    QImage.Format.Format_ARGB32)
    painter = _PainterEspiao(imagem)
    estado = estado_base(_candles(n_velas))
    modulo_candles.desenhar(painter, rect, estado)
    painter.end()
    # Fundos do painel/plot/faixa e a calha do eixo (LARGURA_EIXO) sao
    # largos; o corpo da vela e o retangulo estreito e repetido.
    return [l for l in painter.larguras
            if 0 < l < 30 and l != modulo_candles.LARGURA_EIXO]


def _fabrica_estado(snapshot_minimo, grid):
    def montar(lista):
        return EstadoNexo(snapshot=snapshot_minimo, serie=(), grid=grid,
                          paleta=None, maker=None, leituras=(),
                          largura=900, altura=600,
                          candles_m15=lista, candles_timeframe_min=5,
                          candles_offset=0)
    return montar


def test_largura_da_vela_nao_depende_de_quantas_velas_existem(qapp, monkeypatch):
    from fluxopro.ui.paineis.asg import PainelNexoMercadoASG

    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)
    estado_real = painel._estado_nexo()
    montar = _fabrica_estado(estado_real.snapshot, estado_real.grid)
    rect = QRect(0, 0, 700, 480)

    larguras_abertura = _larguras_de_velas(montar, 2, rect)
    larguras_meio = _larguras_de_velas(montar, 30, rect)
    larguras_fim = _larguras_de_velas(montar, 100, rect)

    # A largura da VELA e a que mais se repete (corpo + volume de cada uma);
    # outros retangulos estreitos (faixa observada, pilulas) aparecem uma vez.
    from collections import Counter

    def largura_da_vela(amostras):
        assert amostras
        return Counter(amostras).most_common(1)[0][0]

    largura_abertura = largura_da_vela(larguras_abertura)
    # Na abertura a vela nao pode ser um bloco: com o defeito, era ~170px.
    assert largura_abertura <= 20, largura_abertura
    # E o tamanho e o MESMO nos tres momentos da sessao.
    assert (largura_abertura == largura_da_vela(larguras_meio)
            == largura_da_vela(larguras_fim))


def test_janela_cobre_o_pregao_inteiro_e_encolhe_no_timeframe_maior(qapp):
    largura_5m = modulo_candles.largura_slot_px(700, 5)
    largura_15m = modulo_candles.largura_slot_px(700, 15)
    # 15M tem um terco das velas do 5M no mesmo pregao => slot ~3x mais largo.
    assert largura_15m > largura_5m
    assert modulo_candles.MINUTOS_PREGAO // 5 > modulo_candles.MINUTOS_PREGAO // 15
