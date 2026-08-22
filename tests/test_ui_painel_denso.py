"""`PainelDenso` — a fundacao que decide se o produto roda a 13 fps ou a 560.

Estes testes nao medem tempo (isso e `test_ui_desempenho.py`). Medem
**trabalho**: quantas vezes a subclasse foi chamada e com que retangulo. E a
mesma licao que a onda 8 deste projeto aprendeu com as mutacoes M1/M2 —
`len` de uma estrutura nao provava nada, e o teste so passou a valer quando
comecou a contar trabalho em vez de tamanho. Um painel que desenha o quadro
inteiro a cada tick continua CORRETO na tela; so e inutilizavel. Correcao
nao pega isso; contagem pega.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QPainter, QResizeEvent  # noqa: E402

from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.base import painel_denso as mod  # noqa: E402
from fluxopro.ui.base.painel_denso import PainelDenso  # noqa: E402


class PainelSonda(PainelDenso):
    """Registra cada chamada de desenho e o retangulo pedido."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regioes: list[QRect] = []
        self.linhas_desenhadas: list[int] = []

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        self.regioes.append(QRect(regiao))
        painter.fillRect(regiao, tokens.BG_SURFACE)
        # Simula uma grade de 18px: so as linhas que cruzam a regiao.
        primeira = max(0, regiao.top() // 18)
        ultima = min(self.height() // 18, regiao.bottom() // 18)
        for linha in range(primeira, ultima + 1):
            self.linhas_desenhadas.append(linha)
            painter.fillRect(QRect(0, linha * 18, self.width(), 17), tokens.BG_RAISED)


@pytest.fixture
def painel(qapp):
    p = PainelSonda()
    p.resize(400, 720)
    p.show()
    p.ao_redimensionar(400, 720)
    p._recriar_backing()
    p.marcar_tudo_sujo()
    p._quadro()
    p.regioes.clear()
    p.linhas_desenhadas.clear()
    p.zerar_medicao()
    return p


class TestQuadroOcioso:
    def test_sem_sujeira_nao_abre_painter(self, painel):
        """O caminho mais importante da classe.

        Sem este `if`, um painel parado gastaria o mesmo que um painel em
        leilao de abertura — e num terminal com 8 paineis abertos e 6 sem
        novidade, isso e a maior parte do custo de UI que simplesmente nao
        deve acontecer.
        """
        for _ in range(1000):
            painel._quadro()
        assert painel.regioes == []
        assert painel.quadros_desenhados == 0
        assert painel.quadros_vazios == 1000

    def test_marcar_sujo_acorda_exatamente_um_quadro(self, painel):
        painel.marcar_sujo(QRect(0, 36, 400, 18))
        painel._quadro()
        painel._quadro()
        painel._quadro()
        assert painel.quadros_desenhados == 1
        assert painel.quadros_vazios == 2


class TestRegiaoSuja:
    def test_uma_linha_suja_desenha_uma_linha(self, painel):
        """O fator 40 em forma de asserçao.

        40 linhas na tela, uma mudou. Se a subclasse for chamada com o
        retangulo inteiro, este teste reprova mesmo que os pixels finais
        estejam corretos.
        """
        painel.marcar_sujo(QRect(0, 5 * 18, 400, 18))
        painel._quadro()
        assert painel.linhas_desenhadas == [5]

    def test_duas_regioes_separadas_nao_viram_o_bloco_entre_elas(self, painel):
        painel.marcar_sujo(QRect(0, 0, 400, 18))
        painel.marcar_sujo(QRect(0, 30 * 18, 400, 18))
        painel._quadro()
        assert painel.linhas_desenhadas == [0, 30]
        assert len(painel.regioes) == 2

    def test_a_sujeira_e_zerada_depois_do_quadro(self, painel):
        painel.marcar_sujo(QRect(0, 0, 400, 18))
        assert painel.tem_sujeira
        painel._quadro()
        assert not painel.tem_sujeira

    def test_muitas_regioes_colapsam_em_uma(self, painel):
        """Acima do teto, uma passada inteira sai mais barata que N clips.

        Cada retangulo custa uma troca de clip e uma passada da subclasse.
        Depois de algumas dezenas espalhadas, o custo das trocas passa o de
        redesenhar o bloco inteiro — e o colapso e o que impede a lista de
        sujos de virar, ela propria, uma estrutura que cresce.
        """
        for i in range(mod.MAX_RETANGULOS_SUJOS + 5):
            painel.marcar_sujo(QRect(0, i * 18, 400, 18))
        painel._quadro()
        assert len(painel.regioes) == 1
        assert painel.regioes[0] == QRect(0, 0, 400, 720)

    def test_marcar_sujo_depois_de_tudo_sujo_e_no_op(self, painel):
        painel.marcar_tudo_sujo()
        painel.marcar_sujo(QRect(0, 0, 10, 10))
        assert painel._sujos == []
        painel._quadro()
        assert len(painel.regioes) == 1

    def test_a_lista_de_sujos_nao_cresce_entre_quadros(self, painel):
        for i in range(500):
            painel.marcar_sujo(QRect(0, (i % 40) * 18, 400, 18))
            painel._quadro()
        assert painel._sujos == []


class TestRolagem:
    def test_rolar_suja_so_a_faixa_que_entrou(self, painel):
        painel.rolar(0, 3 * 18)
        painel._quadro()
        assert painel.regioes == [QRect(0, 0, 400, 54)]
        assert painel.linhas_desenhadas == [0, 1, 2]  # 54px = 3 linhas de 18

    def test_rolar_para_cima_suja_a_faixa_de_baixo(self, painel):
        painel.rolar(0, -2 * 18)
        painel._quadro()
        (regiao,) = painel.regioes
        assert regiao.bottom() == 719
        assert regiao.height() == 36

    def test_area_limita_a_rolagem_e_preserva_o_cabecalho(self, painel):
        """O bug que a primeira versao tinha, fixado como regressao.

        Quase todo painel tem cabecalho fixo. Rolar o backing INTEIRO
        arrastaria o cabecalho para dentro do corpo e depois sujaria a faixa
        errada — os pixels ficariam certos so por acidente, quando a area
        exposta calhasse de cobrir o estrago. Com `area`, a faixa suja nasce
        dentro do corpo.
        """
        corpo = QRect(0, 24, 400, 696)
        painel.rolar(0, 18, corpo)
        painel._quadro()
        (regiao,) = painel.regioes
        assert regiao.top() == 24, "a faixa exposta comeca no CORPO, nao no topo"
        assert regiao.height() == 18

    def test_rolar_move_os_sujos_de_dentro_da_area(self, painel):
        painel.marcar_sujo(QRect(0, 100, 400, 18))
        painel.rolar(0, 18)
        painel._quadro()
        tops = sorted(r.top() for r in painel.regioes)
        assert 118 in tops, "o retangulo ja marcado tambem andou com os pixels"

    def test_rolar_sem_deslocamento_e_no_op(self, painel):
        painel.rolar(0, 0)
        assert not painel.tem_sujeira

    def test_rolar_com_tudo_sujo_nao_faz_nada(self, painel):
        painel.marcar_tudo_sujo()
        painel.rolar(0, 18)
        painel._quadro()
        assert len(painel.regioes) == 1


class TestBacking:
    def test_redimensionar_recria_e_suja_tudo(self, painel):
        anterior = painel.size()
        painel.resize(500, 360)
        painel.resizeEvent(QResizeEvent(painel.size(), anterior))
        assert painel._tudo_sujo
        painel._quadro()
        assert painel.regioes[0].size().width() == 500

    def test_backing_em_pixels_de_dispositivo(self, qapp):
        """Sem isso, num monitor a 150% o painel sai interpolado.

        E o produto vive de numero de 11px legivel — um DOM borrado nao e
        um DOM.
        """
        p = PainelSonda()
        p.resize(200, 100)
        p._recriar_backing()
        proporcao = p.devicePixelRatioF() or 1.0
        assert p._backing.width() == int(200 * proporcao)
        assert p._backing.devicePixelRatio() == proporcao

    def test_tamanho_zero_nao_estoura(self, qapp):
        p = PainelSonda()
        p.resize(0, 0)
        p._recriar_backing()
        assert p._backing is None
        p.marcar_tudo_sujo()
        p._quadro()  # nao levanta


class TestRelogio:
    def test_esconder_para_o_relogio(self, painel):
        assert painel._timer.isActive()
        painel.hide()
        assert not painel._timer.isActive()
        painel.show()
        assert painel._timer.isActive()

    def test_intervalo_e_de_16ms_e_nao_zero(self, painel):
        # A 0 o Qt reagenda no fim de cada quadro e o painel come uma CPU
        # inteira para entregar quadros que o monitor descarta.
        assert painel._timer.interval() == mod.INTERVALO_QUADRO_MS == 16


class TestMedicao:
    def test_p95_ignora_quadros_vazios(self, painel):
        """Se os quadros vazios entrassem na amostra, o p95 viraria propaganda.

        Um painel parado tem 1 us por quadro; misturar isso com os quadros
        reais afundaria o percentil e o portao de desempenho pararia de
        acusar qualquer coisa.
        """
        painel.marcar_sujo(QRect(0, 0, 400, 18))
        painel._quadro()
        for _ in range(10_000):
            painel._quadro()
        assert len(painel._amostras_ms) == 1

    def test_p95_sem_amostra_e_zero(self, painel):
        assert painel.p95_ms() == 0.0

    def test_amostras_tem_teto(self, painel):
        # A medicao nao pode virar a estrutura que cresce.
        for i in range(5000):
            painel.marcar_sujo(QRect(0, 0, 400, 18))
            painel._quadro()
        assert len(painel._amostras_ms) == painel._amostras_ms.maxlen == 512
