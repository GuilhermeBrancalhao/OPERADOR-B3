"""Cobre o defeito medido em 28/08/2026: o Renko e o grafico de velas logo
abaixo desenhavam em escalas verticais independentes.

Medicao do retrato antes da correcao: ~44,6 px por PONTO na regiao do Renko
contra ~13,7 px por ponto na regiao das velas — 3,3x. Um tijolo de 0,5 pt
saia com ~24 px de altura enquanto uma vela inteira de 2 pts do grafico de
baixo tinha ~27 px. O pedido do operador nao e "Renko bonito", e "tijolos
proporcionais aos candles abaixo": com escalas divergentes o olho compara
amplitudes falsas entre uma regiao e a vizinha.

O teste mede os DOIS eixos no MESMO quadro, exatamente como o critico mediu
no retrato — nao confere constante copiada do codigo.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from fluxopro.analytics.renko import ConfigRenko, Renko  # noqa: E402
from fluxopro.ui.paineis import nexo  # noqa: E402
from fluxopro.ui.paineis.nexo import (  # noqa: E402
    EstadoNexo,
    candles as modulo_candles,
    forca as modulo_forca,
)


class _Candle(SimpleNamespace):
    pass


def _candles(n=40):
    """Velas com amplitude de dia real (dezenas de pontos), nao de tick."""
    saida = []
    for i in range(n):
        base = 100_000 + (i * 3) % 60
        saida.append(_Candle(
            open=base, close=base + 2, high=base + 6, low=base - 6,
            volume=10 + i, timestamp_ns=i * 5 * 60 * 1_000_000_000,
        ))
    return tuple(saida)


def _renko_real(divisor=10):
    """Tijolos vindos do agregador de verdade. `divisor` controla quanto
    preco a serie percorre: baixo = serie que enche a caixa (o caso do 1:1),
    alto = micro comprimida (o caso do fator declarado)."""
    from fluxopro.core.eventos import WDO_GRID

    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    for i in range(600):
        renko.registrar(i, 100_000 + (i % 7) + i // divisor)
    return renko


class _EspiaoRetangulos(QPainter):
    """Guarda todo `drawRect` com QRect. O corpo do tijolo e desenhado DUAS
    vezes no mesmo retangulo (preenchimento translucido + borda solida), o
    que o separa das placas de rotulo, desenhadas uma vez so."""

    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.retangulos = []

    def drawRect(self, *args):  # noqa: N802 — assinatura do Qt
        if args and isinstance(args[0], QRect):
            r = args[0]
            self.retangulos.append((r.left(), r.top(), r.width(), r.height()))
        super().drawRect(*args)


def _montar(qapp, zoom_preco=1.0, divisor=10):
    from fluxopro.ui.paineis.asg import PainelNexoMercadoASG

    painel = PainelNexoMercadoASG()
    painel.resize(1920, 1055)
    base = painel._estado_nexo()
    renko = _renko_real(divisor)
    quadro = QRect(0, 0, 1920, 1055 - nexo.ALTURA_RESSALVA)
    caixas = nexo.retangulos(quadro)

    estado = EstadoNexo(
        snapshot=base.snapshot, serie=(), grid=base.grid, paleta=base.paleta,
        maker=None, leituras=(), largura=1920, altura=1055,
        candles_m15=_candles(), candles_timeframe_min=5, candles_offset=0,
        candles_zoom_preco=zoom_preco,
        tijolos_renko=renko.tijolos, fase_renko=renko.fase,
        alvos_renko=renko.alvos(),
        renko_tamanho_ticks=renko.tamanho_tijolo_ticks,
    )
    px_por_tick_candle = modulo_candles.px_por_tick(caixas["candles"], estado)
    estado = EstadoNexo(**{**estado.__dict__,
                           "escala_candle_px_por_tick": px_por_tick_candle})
    return estado, caixas, px_por_tick_candle, renko


class _EspiaoCompleto(QPainter):
    """Guarda textos e linhas, com o estilo da caneta no momento do traco —
    e o que separa uma guia de alvo (tracejada, largura toda) da grade
    (solida) e da referencia do preco atual (pontilhada)."""

    def __init__(self, dispositivo):
        super().__init__(dispositivo)
        self.textos = []
        self.linhas = []

    def drawText(self, *args):  # noqa: N802 — assinatura do Qt
        for a in args:
            if isinstance(a, str):
                self.textos.append(a)
        super().drawText(*args)

    def drawLine(self, *args):  # noqa: N802 — assinatura do Qt
        if len(args) == 4 and all(isinstance(a, int) for a in args):
            self.linhas.append((self.pen().style(), args))
        super().drawLine(*args)


def _espiar(estado, rect):
    imagem = QImage(rect.right() + 1, rect.bottom() + 1,
                    QImage.Format.Format_ARGB32)
    painter = _EspiaoCompleto(imagem)
    modulo_forca.desenhar(painter, rect, estado)
    painter.end()
    return painter


def _textos_desenhados(estado, rect):
    return _espiar(estado, rect).textos


def _guias_e_rotulos(estado, rect):
    import re

    espiao = _espiar(estado, rect)
    guias = [l for estilo, l in espiao.linhas
             if estilo == Qt.PenStyle.DashLine]
    rotulos = [t for t in espiao.textos if re.match(r"^A[123][+-]", t)]
    return guias, rotulos


def _pinta_fora_do_retangulo(estado, rect):
    """Desenha a regiao no MEIO de uma tela pintada de sentinela e conta os
    pixels de sentinela que sumiram fora do retangulo. Prova por pixel, nao
    por coordenada: o recorte do Qt so aparece no pixel."""
    from PySide6.QtGui import QColor

    margem = 60
    largura = rect.right() + 1 + margem
    altura = rect.bottom() + 1 + margem
    imagem = QImage(largura, altura, QImage.Format.Format_ARGB32)
    sentinela = QColor(255, 0, 255)
    imagem.fill(sentinela)

    painter = QPainter(imagem)
    modulo_forca.desenhar(painter, rect, estado)
    painter.end()

    fora = 0
    for y in range(0, altura, 2):
        for x in range(0, largura, 2):
            if rect.contains(x, y):
                continue
            if imagem.pixelColor(x, y) != sentinela:
                fora += 1
    return fora


def _corpos_desenhados(estado, rect):
    """Os retangulos de tijolo, da esquerda para a direita.

    O corpo e desenhado DUAS vezes no mesmo retangulo (preenchimento
    translucido + borda solida), o que o separa das placas de rotulo,
    desenhadas uma vez so.
    """
    imagem = QImage(rect.right() + 1, rect.bottom() + 1,
                    QImage.Format.Format_ARGB32)
    painter = _EspiaoRetangulos(imagem)
    modulo_forca.desenhar(painter, rect, estado)
    painter.end()

    contagem = {}
    for retangulo in painter.retangulos:
        contagem[retangulo] = contagem.get(retangulo, 0) + 1
    corpos = [r for r, n in contagem.items() if n >= 2]
    assert corpos, "nenhum tijolo desenhado — a regiao voltou a ficar vazia"
    return sorted(corpos)


def test_o_renko_desenha_no_mesmo_px_por_tick_do_candle(qapp):
    """Serie que enche a caixa: a proporcao com o vizinho e LITERAL, 1:1.

    A medicao e POR TIJOLO contra o proprio deslocamento dele em ticks — o
    agregador redimensiona o tijolo ao longo do pregao
    (`ConfigRenko.tijolo_dinamico`), entao supor que todo tijolo da tela vale
    o tamanho corrente e simplesmente falso.
    """
    estado, caixas, px_por_tick_candle, renko = _montar(qapp)
    assert px_por_tick_candle > 0.0
    assert "· 1:1 COM CANDLE" in " ".join(
        _textos_desenhados(estado, caixas["forca"])), (
        "esta serie deveria caber em 1:1 — se ganhou fator, o teste abaixo "
        "nao esta medindo a proporcao literal")

    corpos = _corpos_desenhados(estado, caixas["forca"])
    # Os corpos, da esquerda para a direita, sao os ULTIMOS tijolos da serie.
    pares = list(zip(corpos, renko.tijolos[-len(corpos):]))
    assert len(pares) >= 10, "amostra pequena demais para medir uma escala"

    medidos = []
    for (_, _, _, altura_px), tijolo in pares:
        vao_ticks = abs(tijolo.fechamento - tijolo.abertura)
        assert vao_ticks >= 1
        medidos.append(altura_px / vao_ticks)

    media = sum(medidos) / len(medidos)
    assert abs(media - px_por_tick_candle) <= 0.5, (
        f"escalas divergem: Renko {media:.3f} px/tick contra candle "
        f"{px_por_tick_candle:.3f} px/tick"
    )
    # E nenhum tijolo isolado pode fugir mais que 1px do tamanho exato,
    # senao a escada deixa de ler como blocos iguais.
    for (_, _, _, altura_px), tijolo in pares:
        exato = abs(tijolo.fechamento - tijolo.abertura) * px_por_tick_candle
        assert abs(altura_px - exato) <= 1.0, (altura_px, exato)


def test_a_relacao_declarada_e_um_para_um():
    """O fator e o contrato de proporcao — se alguem mexer, o teste conta."""
    assert modulo_forca.FATOR_ESCALA_VS_CANDLE == 1.0


def test_serie_que_enche_a_caixa_fica_em_um_para_um():
    """Quando a micro percorre preco suficiente, 1:1 prevalece — preencher o
    ultimo pixel nao vale mais que a proporcao literal com o vizinho."""
    # faixa 40 ticks * 6 px = 240px numa caixa de 300: 80%, acima do minimo.
    escala, fator = modulo_forca.escala_do_renko(6.0, 2, 300, 40)
    assert fator == 1
    assert escala == 6.0


def test_serie_comprimida_ganha_fator_declarado_em_vez_de_caixa_vazia():
    """O defeito de 28/08/2026 (rodada 2): a serie inteira ocupava 63px de
    320 — 80% de vazio, tijolo de 9px. Vazio nao e solucao, e custo empurrado
    para o operador. O fator sobe, quantizado, e volta para virar rotulo."""
    # faixa 5 ticks * 6 px = 30px de 300: 10% da caixa.
    escala, fator = modulo_forca.escala_do_renko(6.0, 1, 300, 5)
    assert fator > 1, "serie comprimida tinha de ganhar fator"
    assert fator in modulo_forca.FATORES_DECLARAVEIS
    assert escala == 6.0 * fator
    # O teto do tijolo tem precedencia sobre encher a caixa: com 1 tick de
    # tijolo e 6 px/tick, passar de 3x estouraria ALTURA_TIJOLO_MAX_PX e
    # traria de volta o bloco gigante. O que sobrar de vazio depois disso e
    # a micro sendo pequena de verdade — e ai o vazio e informacao.
    assert round(escala) <= modulo_forca.ALTURA_TIJOLO_MAX_PX
    assert 5 * escala >= 5 * 6.0 * 2, "a ocupacao tinha de pelo menos dobrar"


def test_sem_escala_do_vizinho_a_regiao_admite_escala_propria():
    """Degradacao honesta: sem vela nao ha px/tick para copiar, e o quadro
    nao pode AFIRMAR uma proporcao que nao esta cumprindo."""
    escala, fator = modulo_forca.escala_do_renko(0.0, 2, 300, 40)
    assert fator == 0, "fator 0 e o codigo de 'sem vizinho para comparar'"
    assert escala * 2 >= modulo_forca.ALTURA_TIJOLO_MIN_PX


def test_o_fator_vai_escrito_no_quadro(qapp):
    """Fator escondido e a distorcao silenciosa que abriu o ciclo. Seja 1:1,
    seja 3x, seja sem vizinho, o quadro tem de DIZER qual e a relacao."""
    estado, caixas, _, _ = _montar(qapp)
    textos = _textos_desenhados(estado, caixas["forca"])
    declaracoes = [t for t in textos
                   if "COM CANDLE" in t or "DO CANDLE" in t or "ESCALA PROPRIA" in t]
    assert declaracoes, f"nenhuma declaracao de escala no quadro: {textos}"


def test_todo_nivel_marcado_vem_rotulado(qapp):
    """Guia muda e pior que guia nenhuma: o operador ve a linha e nao sabe
    que nivel e. Na rodada 2 saiam seis guias e quatro rotulos — as placas de
    fundo de um rotulo apagavam o texto do vizinho de cima."""
    estado, caixas, _, _ = _montar(qapp)
    guias, rotulos = _guias_e_rotulos(estado, caixas["forca"])
    assert guias, "nenhuma guia de alvo desenhada"
    assert len(rotulos) == len(guias), (
        f"{len(guias)} guias desenhadas para {len(rotulos)} rotulos: {rotulos}"
    )


def test_zoom_de_preco_do_candle_chega_ao_renko_sem_vazar_da_regiao(qapp):
    """Flanco que estava descoberto: nao ha como acionar o zoom pela linha de
    comando, entao o retrato nunca exercitava este caminho.

    Duas afirmacoes: (a) o zoom do eixo das velas chega ao Renko, porque e o
    MESMO eixo; (b) por maior que ele fique, nada e pintado fora do
    retangulo da regiao — `forca.py` nao recortava o proprio desenho e o
    tijolo transbordava por cima da vizinha.
    """
    estado_neutro, caixas, escala_neutra, _ = _montar(qapp)
    estado_zoom, _, escala_zoom, _ = _montar(qapp, zoom_preco=4.0)

    assert escala_zoom > escala_neutra * 2, (
        "zoom de preco no candle tem de esticar o eixo compartilhado")

    for estado in (estado_neutro, estado_zoom):
        assert _pinta_fora_do_retangulo(estado, caixas["forca"]) == 0
