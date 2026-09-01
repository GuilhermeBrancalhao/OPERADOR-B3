"""Placar de SUPORTE/RESISTENCIA e o alerta do banner (31/08/2026).

A logica foi conferida nas AULAS DA SG/ASG (transcricoes em
`fluxo_pro/pesquisa/legendas`), nao inferida:

* `TPk39osWiKY` — "quando ele vier com a forca ultra, que e quando tem esse
  RAIO aqui"; "so vai dar enfase para esse sinal quando ele aparecer no
  NIVEL MAXIMO"; "voce nunca vai fazer a compra em cima dessa sinalizacao"
  (resistencia) e "enquanto estiver o suporte detectado nesses niveis, voce
  vai evitar fazer a entrada de venda".
* `W7lNHhliZXU` — "ele tem umas BARRINHAS ali que sao PREENCHIDAS"; "como
  que ta o TERMOMETRO dessas sinalizacoes?".

O que estes testes travam: UM LADO POR VEZ, raios saindo da FORCA DA ZONA,
o preco da REGIAO no numero grande, e o alerta so tomando a faixa quando o
nivel e alto.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402

from fluxopro.analytics import suporte_resistencia as sr  # noqa: E402
from fluxopro.ui.paineis.nexo import banner  # noqa: E402
from fluxopro.ui.paineis.nexo import estatistica  # noqa: E402
from fluxopro.ui.paineis.nexo import suporte_resistencia as ui  # noqa: E402


def _zona(preco, lado, score, toques=4):
    return sr.Zona(id=f"z{preco}", lado=lado, preco=preco, inferior=preco - 4,
                   superior=preco + 4, score=score, confianca=0.9, toques=toques,
                   fontes=("vap-poc",), status=sr.EstadoZona.ATIVA)


def _snapshot(zonas=(), dominante=None, ultimo=10400, tick=0.5,
              saude=sr.EstadoFeed.LIVE):
    return SimpleNamespace(
        zonas=tuple(zonas), dominante=dominante, ultimo_preco=ultimo,
        tick_size=tick, saude=SimpleNamespace(estado=saude),
    )


# ===================================================== intensidade e preco
@pytest.mark.parametrize("score,esperado", [
    (None, 0), (0.0, 0), (0.049, 0), (0.05, 1), (0.20, 1),
    (0.21, 2), (0.40, 2), (0.60, 3), (0.80, 4), (0.81, 5), (1.0, 5),
])
def test_intensidade_vem_da_forca_da_zona(score, esperado):
    """Confirmado pelo operador: a intensidade dos raios sai da FORCA DA
    ZONA, na mesma escala ja aprovada para a forca observada."""

    assert ui.intensidade_da_zona(score) == esperado


def test_intensidade_usa_a_mesma_escala_da_forca_observada():
    """Duas escalas de 'intensidade' na mesma tela seriam 'dois pesos, uma
    leitura' — o defeito que esta bancada ja pegou antes."""

    for valor in (0.05, 0.3, 0.5, 0.7, 0.95):
        assert ui.intensidade_da_zona(valor) == estatistica.quantidade_raios_forca(valor)


def test_numero_grande_e_o_preco_da_regiao():
    """Confirmado pelo operador: 'É O PREÇO DA REGIÃO'."""

    assert ui.texto_preco_regiao(10439, 0.5) == "5.219,5"
    assert ui.texto_preco_regiao(None, 0.5) == "—"


# ===================================================== zona de referencia
def test_referencia_prefere_a_zona_confirmada():
    dominante = _zona(10500, sr.LadoZona.RESISTENCIA, 0.9)
    outra = _zona(10400, sr.LadoZona.NEUTRO, 0.2)
    assert ui.zona_de_referencia(_snapshot((outra, dominante), dominante)) is dominante


def test_sem_confirmacao_usa_a_zona_mais_proxima_do_preco():
    """O operador precisa do NIVEL da regiao que o preco esta encostando
    mesmo antes da confirmacao — esconder seria o defeito de 31/08."""

    perto = _zona(10405, sr.LadoZona.NEUTRO, 0.3)
    longe = _zona(10800, sr.LadoZona.NEUTRO, 0.9)
    assert ui.zona_de_referencia(_snapshot((longe, perto), None, ultimo=10400)) is perto


def test_sem_zona_nenhuma_devolve_none():
    assert ui.zona_de_referencia(_snapshot()) is None
    assert ui.zona_de_referencia(None) is None


# ============================================================ alerta (banner)
def _estado(snapshot):
    from fluxopro.ui.paineis.nexo import EstadoNexo

    return EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                      leituras=(), largura=1920, altura=1055, sr_snapshot=snapshot)


def test_alerta_e_de_um_lado_so():
    """A aula: 'alerta de resistencia maxima OU alerta de suporte maximo'.
    Nunca os dois — o retorno carrega UM lado."""

    zona = _zona(10500, sr.LadoZona.RESISTENCIA, 0.9)
    alerta = banner.alerta_suporte_resistencia(_estado(_snapshot((zona,), zona)))
    assert alerta is not None
    titulo, subtitulo, _cor, para_cima = alerta
    assert para_cima is False, "resistencia aponta para BAIXO"
    assert "RESISTENCIA" in titulo
    assert "EVITE COMPRAR" in subtitulo, "a aula proibe COMPRAR na resistencia"


def test_alerta_de_suporte_inverte_lado_e_conduta():
    zona = _zona(10300, sr.LadoZona.SUPORTE, 0.9)
    titulo, subtitulo, _c, para_cima = banner.alerta_suporte_resistencia(
        _estado(_snapshot((zona,), zona, ultimo=10400)))
    assert para_cima is True
    assert "SUPORTE" in titulo
    assert "EVITE VENDER" in subtitulo


def test_nivel_maximo_troca_o_titulo_para_ULTRA():
    """'so vai dar enfase para esse sinal quando ele aparecer no NIVEL
    MAXIMO' — o titulo tem de distinguir os dois casos."""

    forte = _zona(10500, sr.LadoZona.RESISTENCIA, 0.95)
    media = _zona(10500, sr.LadoZona.RESISTENCIA, 0.55)
    t_forte = banner.alerta_suporte_resistencia(_estado(_snapshot((forte,), forte)))[0]
    t_media = banner.alerta_suporte_resistencia(_estado(_snapshot((media,), media)))[0]
    assert t_forte.startswith("ULTRA")
    assert not t_media.startswith("ULTRA")


def test_zona_fraca_nao_toma_a_faixa_de_alerta():
    """'nao e assim uma sinalizacao que ela e constante'. Alerta que acende
    sempre deixa de ser alerta."""

    fraca = _zona(10500, sr.LadoZona.RESISTENCIA, 0.15)
    assert banner.alerta_suporte_resistencia(_estado(_snapshot((fraca,), fraca))) is None


def test_sem_zona_nao_ha_alerta():
    assert banner.alerta_suporte_resistencia(_estado(_snapshot())) is None
    assert banner.alerta_suporte_resistencia(_estado(None)) is None


def test_alerta_traz_o_preco_da_regiao_no_subtitulo():
    zona = _zona(10439, sr.LadoZona.RESISTENCIA, 0.9)
    _t, subtitulo, _c, _p = banner.alerta_suporte_resistencia(
        _estado(_snapshot((zona,), zona)))
    assert "5.219,5" in subtitulo


# ================================================================= desenho
def _desenha(rect, snapshot):
    imagem = QImage(max(1, rect.width()), max(1, rect.height()),
                    QImage.Format.Format_ARGB32)
    # `fill` OBRIGATORIO: `QImage` nasce com memoria NAO INICIALIZADA. Sem
    # isto o teste de pixel passava sozinho (lixo zerado) e falhava na suite
    # (lixo de outra imagem), com verde e vermelho empatando no mesmo numero
    # — flakiness que o proprio teste criou, nao defeito do desenho.
    imagem.fill(QColor("black"))
    painter = QPainter(imagem)
    try:
        ui.desenhar_placar(painter, rect, snapshot)
    finally:
        painter.end()
    return imagem


def test_placar_desenha_sem_excecao_em_varios_tamanhos(qapp):
    zona = _zona(10439, sr.LadoZona.RESISTENCIA, 0.9)
    snap = _snapshot((zona,), zona)
    for largura, altura in ((560, 250), (420, 180), (300, 120), (200, 60)):
        _desenha(QRect(0, 0, largura, altura), snap)


def test_placar_sem_snapshot_nao_estoura(qapp):
    _desenha(QRect(0, 0, 560, 250), None)
    _desenha(QRect(0, 0, 560, 250), _snapshot())


def test_placar_acende_apenas_o_lado_da_zona(qapp):
    """Prova por PIXEL: numa resistencia o vermelho domina o verde na
    metade dos cards; num suporte, o contrario."""

    def contar(snapshot):
        imagem = _desenha(QRect(0, 0, 560, 250), snapshot)
        verdes = vermelhos = 0
        for y in range(20, 100):
            for x in range(0, 560):
                c = imagem.pixelColor(x, y)
                if c.green() > 140 and c.red() < 110:
                    verdes += 1
                elif c.red() > 140 and c.green() < 110:
                    vermelhos += 1
        return verdes, vermelhos

    res = _zona(10500, sr.LadoZona.RESISTENCIA, 0.9)
    sup = _zona(10300, sr.LadoZona.SUPORTE, 0.9)
    v_res, r_res = contar(_snapshot((res,), res, ultimo=10400))
    v_sup, r_sup = contar(_snapshot((sup,), sup, ultimo=10400))
    assert r_res > v_res, "resistencia deveria acender o lado VENDEDOR"
    assert v_sup > r_sup, "suporte deveria acender o lado COMPRADOR"


# ============================== o alerta PRECISA aparecer no layout INTEGRADO
def test_layout_integrado_desenha_a_placa_de_alerta(qapp):
    """DEFEITO RELATADO PELO OPERADOR: "ainda esta faltando o alerta de
    suporte e resistencia, ATE AGORA NAO TEVE".

    O alerta morava em `nexo/banner.py`, mas o layout integrado NAO desenha
    o banner — `asg.desenhar` troca a regiao por
    `assistente.desenhar_resumo`. O alerta era calculado a cada quadro e nao
    tinha como chegar na tela. Este teste chama a funcao do layout NOVO e
    exige o titulo escrito.
    """

    from fluxopro.ui.paineis.nexo import assistente

    zona = _zona(10500, sr.LadoZona.RESISTENCIA, 0.95)
    estado = _estado(_snapshot((zona,), zona, ultimo=10400))

    textos = []
    original = QPainter.drawText

    def espiao(self, *args):
        if args and isinstance(args[-1], str):
            textos.append(args[-1])
        return original(self, *args)

    imagem = QImage(520, 90, QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    QPainter.drawText = espiao
    try:
        assistente.desenhar_resumo(painter, QRect(0, 0, 520, 90), estado)
    finally:
        QPainter.drawText = original
        painter.end()

    assert any("RESISTENCIA" in t for t in textos), textos
    assert any("ALERTA" in t for t in textos), textos
    assert any("EVITE COMPRAR" in t for t in textos), textos


def test_layout_integrado_sem_alerta_mantem_o_resumo(qapp):
    """Sem zona forte a faixa volta ao resumo de sempre — o alerta nao pode
    sequestrar a regiao permanentemente."""

    from fluxopro.ui.paineis.nexo import assistente

    fraca = _zona(10500, sr.LadoZona.RESISTENCIA, 0.10)
    estado = _estado(_snapshot((fraca,), None, ultimo=10400))
    imagem = QImage(520, 90, QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    try:
        assistente.desenhar_resumo(painter, QRect(0, 0, 520, 90), estado)
    finally:
        painter.end()
