"""Cobre o achado do operador (item 20 do docx MUDANCAS E IMPLEMENTACOES,
27/08/2026): o VAP precisava de um filtro 5M/15M, que nunca tinha sido
implementado (so ganhou gradiente + POC na Fase 2)."""

from PySide6.QtCore import QPointF, QRect

from fluxopro.core.eventos import AgressorSide
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG
from fluxopro.ui.paineis.nexo import ladder as modulo_ladder


class _EventoFake:
    def __init__(self, x, y):
        self._ponto = QPointF(x, y)
        self.aceito = False

    def position(self):
        return self._ponto

    def accept(self):
        self.aceito = True


NS_POR_MIN = 60_000_000_000


def test_timeframe_do_vap_comeca_em_sessao_inteira(qapp):
    painel = PainelNexoMercadoASG()
    assert painel._vap_timeframe_min == 0


def test_perfil_vap_recorta_negocios_fora_da_janela(qapp):
    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)

    # 1 negocio "antigo" (20 min atras) a um preco isolado, depois negocios
    # recentes dentro dos ultimos 5 minutos a outro preco.
    painel._registrar_amostra(0, 100_000, 0.0, 50, AgressorSide.BUY)
    inicio_recente = 20 * NS_POR_MIN
    for i in range(10):
        painel._registrar_amostra(
            inicio_recente + i * NS_POR_MIN, 100_010, 0.0, 5, AgressorSide.BUY
        )

    painel._vap_timeframe_min = 5
    perfil = painel._perfil_vap_ativo()
    niveis = dict(perfil.niveis_ordenados())

    assert 100_000 not in niveis, "negocio de 20min atras nao pode entrar no recorte de 5M"
    assert 100_010 in niveis
    # janela de 5min a partir do ultimo negocio (min 29) so pega min 24..29 -> 6 negocios de qty 5
    assert niveis[100_010].volume_total == 30


def test_perfil_vap_sessao_inteira_nao_filtra_nada(qapp):
    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)
    painel._registrar_amostra(0, 100_000, 0.0, 50, AgressorSide.BUY)
    painel._registrar_amostra(30 * NS_POR_MIN, 100_010, 0.0, 5, AgressorSide.BUY)

    assert painel._vap_timeframe_min == 0
    perfil = painel._perfil_vap_ativo()
    niveis = dict(perfil.niveis_ordenados())
    assert 100_000 in niveis
    assert 100_010 in niveis


def test_clique_no_rotulo_do_vap_avanca_o_timeframe(qapp):
    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)
    painel._registrar_amostra(0, 100_000, 0.0, 10, AgressorSide.BUY)

    caixa = painel._retangulo_ladder()
    assert caixa is not None
    alvo = modulo_ladder.retangulo_rotulo(caixa).center()

    evento = _EventoFake(alvo.x(), alvo.y())
    painel.mousePressEvent(evento)
    assert painel._vap_timeframe_min == 5
    assert evento.aceito

    painel.mousePressEvent(_EventoFake(alvo.x(), alvo.y()))
    assert painel._vap_timeframe_min == 15

    painel.mousePressEvent(_EventoFake(alvo.x(), alvo.y()))
    assert painel._vap_timeframe_min == 0


def test_estado_nexo_carrega_o_timeframe_e_niveis_recortados(qapp):
    painel = PainelNexoMercadoASG()
    painel.resize(1200, 700)
    painel._registrar_amostra(0, 100_000, 0.0, 50, AgressorSide.BUY)
    painel._registrar_amostra(20 * NS_POR_MIN, 100_010, 0.0, 5, AgressorSide.BUY)
    painel._vap_timeframe_min = 5

    estado = painel._estado_nexo()
    assert estado.vap_timeframe_min == 5
    precos = {nivel[0] for nivel in estado.vap_niveis}
    assert 100_000 not in precos
    assert 100_010 in precos
