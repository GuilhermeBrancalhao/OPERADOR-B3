"""Regressoes de composicao visual, sem dependencia de feed externo."""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter
from fluxopro.ui.fundo_operador import FundoOperador


def render(fundo, segundos=0, tamanho=(640, 360)):
    imagem = QImage(*tamanho, QImage.Format.Format_ARGB32)
    imagem.fill(QColor('#030609'))
    p = QPainter(imagem)
    fundo.pintar(p, imagem.rect(), segundos)
    p.end()
    return imagem


def test_asset_empacotado_e_loop_continuo(qapp, monkeypatch):
    monkeypatch.delenv('FLUXOPRO_WALLPAPER', raising=False)
    monkeypatch.delenv('FLUXOPRO_REDUCED_MOTION', raising=False)
    fundo = FundoOperador()
    assert not fundo.imagem.isNull()
    assert render(fundo, 0) == render(fundo, 48) == render(fundo, 96)
    assert render(fundo, 0) != render(fundo, 12)


@pytest.mark.parametrize('tamanho', [(1280, 720), (1480, 900), (1920, 1080)])
def test_cover_cache_limitado(qapp, tamanho):
    fundo = FundoOperador()
    render(fundo, tamanho=tamanho)
    assert fundo.cache.width() >= tamanho[0] + 40
    assert fundo.cache.height() >= tamanho[1] + 40
    chave = fundo.cache.cacheKey()
    render(fundo, 12, tamanho)
    assert fundo.cache.cacheKey() == chave
    render(fundo, tamanho=(400, 300))
    assert fundo.tamanho == (400, 300)


def test_movimento_reduzido(qapp, monkeypatch):
    monkeypatch.setenv('FLUXOPRO_REDUCED_MOTION', '1')
    fundo = FundoOperador()
    antes = render(fundo)
    fundo.alvo = (12, 12)
    fundo.avancar()
    assert fundo.cursor == (0, 0)
    assert render(fundo, 12) == antes


def test_fallback_preserva_fundo(qapp, monkeypatch):
    monkeypatch.setenv('FLUXOPRO_WALLPAPER', 'arquivo-inexistente.jpg')
    fundo = FundoOperador()
    assert fundo.imagem.isNull()
    imagem = render(fundo)
    assert imagem.pixelColor(0, 0) == QColor('#030609')
    assert imagem.pixelColor(320, 180) == QColor('#030609')


def test_nucleo_cantos_transparentes(qapp):
    from fluxopro.ui.paineis.nexo.assistente import _arte_escalada
    imagem = _arte_escalada(320)
    assert not imagem.isNull()
    assert imagem.pixelColor(0, 0).alpha() == 0
    assert imagem.pixelColor(319, 319).alpha() == 0
    assert imagem.pixelColor(160, 160).alpha() == 255


def test_painel_oculto_nao_solicita_redesenho(qapp, monkeypatch):
    from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
    painel = PainelNexoMercadoASG()
    chamadas = []
    monkeypatch.setattr(painel, 'marcar_tudo_sujo', lambda: chamadas.append(True))
    painel.hide()
    painel._avancar_wallpaper()
    assert chamadas == []
    painel.show()
    chamadas.clear()  # showEvent solicita seu proprio primeiro quadro.
    painel._avancar_wallpaper()
    assert chamadas == [True]
    painel.close()
