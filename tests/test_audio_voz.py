import threading

from fluxopro.asg.sinal_ultra import DirecaoUltra
from fluxopro.audio.voz import ConfigVoz, LocutorASG, texto_para_transicao_ultra


def test_sem_transicao_nao_fala():
    assert texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.NENHUMA) is None
    assert texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.COMPRA) is None


def test_liga_compra_anuncia_compra():
    texto = texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA)
    assert texto is not None
    assert "compra" in texto.lower()


def test_liga_venda_anuncia_venda():
    texto = texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.VENDA)
    assert texto is not None
    assert "venda" in texto.lower()


def test_desliga_anuncia_encerrado():
    texto = texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA)
    assert texto is not None
    assert "encerrado" in texto.lower()


def test_reversao_direta_nao_e_confundida():
    """COMPRA->VENDA direto deve anunciar VENDA, nao 'encerrado'."""
    texto = texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.VENDA)
    assert texto is not None
    assert "venda" in texto.lower()
    assert "encerrado" not in texto.lower()


def test_config_inativa_nunca_sobe_thread():
    """ConfigVoz.ativo=False (o padrao) nao pode criar NENHUMA thread —
    e o que garante que montar o painel em teste/CI nunca dispara audio."""
    antes = threading.active_count()
    locutor = LocutorASG(ConfigVoz(ativo=False))
    assert threading.active_count() == antes
    locutor.falar("isso nunca deveria ser dito")
    locutor.encerrar()
    assert threading.active_count() == antes


def test_locutor_padrao_e_inativo():
    locutor = LocutorASG()
    assert locutor.config.ativo is False


def test_volume_invalido_rejeitado():
    import pytest

    with pytest.raises(ValueError):
        ConfigVoz(volume=1.5)
