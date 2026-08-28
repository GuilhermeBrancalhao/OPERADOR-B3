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


def test_anuncio_diz_o_que_o_sinal_reproduz():
    """O pedido do operador e que a voz fale "o que o sinal acima reproduz",
    nao apenas o nome do sinal: o texto tem de citar as fontes que
    concordaram e o que observar."""

    texto = texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA).lower()
    assert "renko" in texto
    assert "maker" in texto
    assert "observe" in texto


def test_anuncio_carrega_a_ressalva_consultiva():
    """O canal de audio nao pode perder a ressalva que a tela carrega — quem
    so ouve o painel precisa ouvir que aquilo nao e ordem."""

    for nova in (DirecaoUltra.COMPRA, DirecaoUltra.VENDA):
        texto = texto_para_transicao_ultra(DirecaoUltra.NENHUMA, nova).lower()
        assert "nao e ordem" in texto


def test_anuncio_nunca_recomenda_execucao():
    proibidos = ("compre", "entre", "alvo", "stop", "recomend", "lote", "contrato")
    transicoes = (
        (DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA),
        (DirecaoUltra.NENHUMA, DirecaoUltra.VENDA),
        (DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),
        (DirecaoUltra.VENDA, DirecaoUltra.NENHUMA),
        (DirecaoUltra.COMPRA, DirecaoUltra.VENDA),
    )
    for anterior, nova in transicoes:
        texto = (texto_para_transicao_ultra(anterior, nova) or "").lower()
        for termo in proibidos:
            assert termo not in texto, (anterior, nova, termo, texto)


def test_encerramento_nomeia_o_lado_que_saiu():
    """"Sinal Ultra encerrado" sozinho nao diz qual sinal caiu — quem so
    ouve nao consegue distinguir o fim de uma compra do fim de uma venda."""

    compra = texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA).lower()
    venda = texto_para_transicao_ultra(DirecaoUltra.VENDA, DirecaoUltra.NENHUMA).lower()
    assert "compra" in compra
    assert "venda" in venda
    assert compra != venda


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
