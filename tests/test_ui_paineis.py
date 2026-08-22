"""DOM, tape e strips — comportamento, nao pixel.

Nenhum destes testes compara imagens. Comparacao de imagem quebra quando a
maquina troca de fonte e passa quando a logica quebra — e o inverso exato do
que se quer. O que se afirma aqui e o que o operador percebe: a escada nao
pula, o rastro apaga, o filtro filtra, e a direcao continua legivel quando a
cor sai de cena.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QEvent, QRect, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from fluxopro.core.eventos import WDO_GRID, BookLevel, BookSnapshot  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis import dom as mod_dom  # noqa: E402
from fluxopro.ui.paineis.dom import PainelDOM  # noqa: E402
from fluxopro.ui.paineis.strips import StripRodape, StripTopo  # noqa: E402
from fluxopro.ui.paineis.tape import PainelTape  # noqa: E402
from fluxopro.ui.ponte import Contadores, EstadoFeed, Instantaneo, ItemTape  # noqa: E402

T0 = 1_700_000_000_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)


def livro(centro: int = BASE, n: int = 10, offset: int = 0) -> BookSnapshot:
    return BookSnapshot(
        T0,
        "WDOV26",
        tuple(BookLevel(centro - k - 1, 100 + k + offset, 1 + k % 3) for k in range(n)),
        tuple(BookLevel(centro + k + 1, 90 + k + offset, 1 + k % 2) for k in range(n)),
    )


def _pronto(painel, largura: int, altura: int):
    painel.resize(largura, altura)
    painel.show()
    painel.ao_redimensionar(largura, altura)
    painel._recriar_backing()
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def dom(qapp):
    p = _pronto(PainelDOM(WDO_GRID), 420, 760)
    p.aplicar(livro(), BASE)
    p._quadro()
    return p


@pytest.fixture
def tape(qapp):
    return _pronto(PainelTape(WDO_GRID), 380, 760)


class TestEscadaTravada:
    def test_preco_dentro_da_zona_de_conforto_nao_move_a_escada(self, dom):
        """Uma escada que se recentraliza a cada tick e ilegivel.

        O olho perde a referencia espacial, que e a unica coisa que um DOM
        oferece alem dos numeros.
        """
        centro = dom._centro
        for delta in (0, 1, -1, 2, -3, 4, -4):
            dom.aplicar(livro(), BASE + delta)
        assert dom._centro == centro

    def test_preco_perto_da_borda_recentraliza(self, dom):
        centro = dom._centro
        longe = BASE + dom.n_niveis  # muito alem da zona de conforto
        dom.aplicar(livro(longe), longe)
        assert dom._centro == longe != centro

    def test_recentralizar_usa_ROLAGEM_e_nao_quadro_cheio(self, dom):
        """A razao de o deslizamento existir.

        Sem ele, cada recentralizacao seria um quadro cheio — e num dia de
        tendencia a escada recentraliza dezenas de vezes.
        """
        dom._quadro()
        assert not dom.tem_sujeira
        folga = max(1, int(dom.n_niveis * mod_dom.MARGEM_RECENTRALIZAR))
        alvo = dom._centro + (dom.n_niveis // 2) - folga + 1
        dom.aplicar(livro(alvo), alvo)
        assert not dom._tudo_sujo, "recentralizacao pequena nao pode sujar a tela toda"
        assert dom._sujos, "e tem de sujar a faixa que entrou"

    def test_salto_maior_que_a_escada_redesenha_tudo(self, dom):
        # Rolar seria mover pixels que vao ser todos sobrescritos.
        dom._quadro()
        alvo = dom._centro + dom.n_niveis * 3
        dom.aplicar(livro(alvo), alvo)
        assert dom._tudo_sujo

    def test_congelado_nao_recentraliza(self, dom):
        dom.congelar(True)
        centro = dom._centro
        longe = BASE + dom.n_niveis * 2
        dom.aplicar(livro(longe), longe)
        assert dom._centro == centro

    def test_espaco_alterna_o_congelamento(self, dom):
        assert not dom.congelado
        dom.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
        assert dom.congelado
        dom.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
        assert not dom.congelado

    def test_preco_cresce_para_CIMA(self, dom):
        """Inverter isso desorienta quem opera. Vale como contrato."""
        assert dom._preco_da_linha(0) > dom._preco_da_linha(dom.n_niveis - 1)

    def test_linha_e_preco_sao_inversos(self, dom):
        for linha in range(dom.n_niveis):
            assert dom._linha_do_preco(dom._preco_da_linha(linha)) == linha

    def test_preco_fora_da_escada_nao_tem_linha(self, dom):
        assert dom._linha_do_preco(dom._centro + 10_000) is None


class TestRetencaoDoDOM:
    def test_o_estado_nao_cresce_com_o_range_do_dia(self, dom):
        """Indexar por PRECO faria a estrutura crescer com o dia inteiro.

        E a forma exata do defeito que este projeto encontrou em oito
        arquivos. Aqui o estado e indexado por LINHA, entao ele e limitado
        pela tela por construcao — e este teste e o que impede alguem de
        "melhorar" isso para um dicionario por preco.
        """
        def tamanho() -> int:
            return sum(
                len(v)
                for v in (dom._qty_bid, dom._qty_ask, dom._ord_bid, dom._ord_ask, dom._rastro)
            )

        inicial = tamanho()
        preco = BASE
        for i in range(3000):
            preco += 1 if i % 2 else 2  # sobe o dia inteiro, 4.500 ticks
            dom.aplicar(livro(preco), preco)
        assert tamanho() == inicial == dom.n_niveis * 5

    def test_rastro_apaga_sozinho(self, dom):
        dom.aplicar(livro(offset=7), BASE)
        assert any(r > 0 for r in dom._rastro)
        for _ in range(mod_dom.QUADROS_RASTRO + 2):
            dom.aplicar(None, BASE)
        assert all(r == 0 for r in dom._rastro)


class TestSujeiraDoDOM:
    def test_um_nivel_que_muda_suja_uma_linha(self, dom):
        dom._quadro()
        assert not dom.tem_sujeira
        base = livro()
        bids = list(base.bids)
        bids[3] = BookLevel(bids[3].price, 55, 1)  # abaixo da escala corrente
        dom.aplicar(BookSnapshot(T0 + 1, "WDOV26", tuple(bids), base.asks), BASE)
        # O rodape tambem suja (a soma mudou), entao sao 2 retangulos — e nao
        # 40 linhas, que e o que importa.
        assert not dom._tudo_sujo
        assert len(dom._sujos) <= 2

    def test_a_faixa_suja_cai_EXATAMENTE_sobre_a_linha(self, dom):
        """A regressao do defeito que so o retrato PNG mostrou.

        `marcar_linha` assumia que as linhas comecam em y=0. No DOM elas
        comecam 24px abaixo, sob o cabecalho — entao a faixa suja caia uma
        altura de cabecalho ACIMA da linha real. A linha era redesenhada pela
        metade e a outra metade continuava com o valor antigo, o que na tela
        virava um digito cortado ao meio, parecendo um tracinho.

        Nenhum teste de comportamento veria: os dados estavam certos, o
        `len` estava certo, o numero de retangulos estava certo. So a imagem
        denunciou. Por isso a asserçao aqui e sobre a GEOMETRIA, nao sobre a
        contagem.
        """
        dom._quadro()
        alvo = 7
        dom._sujar_linha(alvo)
        (regiao,) = dom._sujos
        assert regiao.top() == dom._y_da_linha(alvo)
        assert regiao.height() == dom.densidade.altura_linha
        assert regiao.top() >= dom._y_corpo, "faixa suja invadiu o cabecalho"

    def test_toda_linha_visivel_tem_faixa_dentro_do_corpo(self, dom):
        for linha in range(dom.n_niveis):
            dom.marcar_tudo_sujo()
            dom._quadro()
            dom._sujar_linha(linha)
            (regiao,) = dom._sujos
            assert dom._y_corpo <= regiao.top()
            assert regiao.bottom() <= dom.height()

    def test_livro_identico_nao_suja_nada(self, dom):
        dom._quadro()
        dom.aplicar(livro(), BASE)
        assert not dom.tem_sujeira, "book repetido nao pode gerar quadro"

    def test_maximo_visivel_reescala_a_barra(self, dom):
        """A escala segue o maximo VISIVEL, nao o maximo do dia.

        Uma ordem gigante 30 niveis abaixo achataria todas as barras do topo
        e o painel viraria uma coluna de nada.
        """
        dom._quadro()
        base = livro()
        bids = list(base.bids)
        bids[0] = BookLevel(bids[0].price, 50_000, 1)
        dom.aplicar(BookSnapshot(T0 + 1, "WDOV26", tuple(bids), base.asks), BASE)
        assert dom._max_qty == 50_000
        assert dom._tudo_sujo, "mudar a escala exige redesenhar todas as barras"

    def test_escala_nao_reescala_a_cada_snapshot(self, dom):
        """A tempestade de repintura que o teste acima quase escondeu.

        Num book vivo o maximo muda quase todo snapshot. Se a escala o
        seguisse exatamente, o DOM repintaria o quadro inteiro dezenas de
        vezes por segundo e o ganho da regiao suja iria embora — com todos
        os testes de correcao passando, porque a TELA fica certa.
        """
        dom._quadro()
        cheios = 0
        for i in range(200):
            dom.aplicar(livro(offset=i), BASE)  # maximo sobe 1 por passada
            if dom._tudo_sujo:
                cheios += 1
            dom._quadro()
        # 100..309 atravessa dois degraus da serie 1-2-5 (200 e 500).
        assert cheios <= 3, f"{cheios} quadros cheios em 200 snapshots"

    def test_degrau_1_2_5(self):
        from fluxopro.ui.paineis.dom import _degrau_1_2_5

        assert [_degrau_1_2_5(v) for v in (1, 2, 3, 11, 20, 21, 60, 100, 101, 480)] == [
            1, 2, 5, 20, 20, 50, 100, 100, 200, 500,
        ]

    def test_escala_encolhe_so_com_folga(self, dom):
        # Histerese: sem ela, uma escala oscilando entre dois degraus
        # vizinhos repintaria a tela em vaivem.
        dom.aplicar(livro(offset=400), BASE)   # maximo ~509 -> degrau 1000
        dom._quadro()
        escala = dom._max_qty
        dom.aplicar(livro(offset=300), BASE)   # cai para ~409, ainda > 1000/4
        assert dom._max_qty == escala


class TestTape:
    def test_mais_novo_no_topo(self, tape):
        tape.aplicar((ItemTape(T0, BASE, 10, 1),))
        tape.aplicar((ItemTape(T0 + 1, BASE + 1, 20, -1),))
        assert tape._linhas[0].qty == 20

    def test_anel_tem_teto(self, tape):
        from fluxopro.ui.paineis.tape import CAPACIDADE_ANEL

        for i in range(CAPACIDADE_ANEL * 4):
            tape.aplicar((ItemTape(T0 + i, BASE, 1, 1),))
        assert len(tape._linhas) == CAPACIDADE_ANEL

    def test_filtro_barra_o_lote_pequeno_e_conta(self, tape):
        tape.definir_filtro(50)
        tape.aplicar(
            (
                ItemTape(T0, BASE, 5, 1),
                ItemTape(T0 + 1, BASE, 60, 1),
                ItemTape(T0 + 2, BASE, 10, -1),
            )
        )
        assert [i.qty for i in tape._linhas] == [60]
        assert tape._filtrados == 2

    def test_mudar_o_filtro_nao_reescreve_o_passado(self, tape):
        """Esconder o que o operador VIU acontecer e pior que nao filtrar.

        Reprocessar o anel daria uma tela que muda sozinha ao mexer no
        filtro, apagando negocios que ja passaram diante dos olhos dele.
        """
        tape.aplicar((ItemTape(T0, BASE, 5, 1),))
        tape.definir_filtro(1000)
        assert len(tape._linhas) == 1

    def test_poucos_negocios_rolam_muitos_redesenham(self, tape):
        tape._quadro()
        tape.aplicar((ItemTape(T0, BASE, 1, 1),))
        assert not tape._tudo_sujo and tape._sujos

        tape._quadro()
        muitos = tuple(ItemTape(T0 + i, BASE, 1, 1) for i in range(tape._n_visiveis + 5))
        tape.aplicar(muitos)
        assert tape._tudo_sujo

    def test_degraus_do_filtro_sao_previsiveis(self, tape):
        from fluxopro.ui.paineis.tape import _proximo_degrau

        assert _proximo_degrau(0, +1) == 5
        assert _proximo_degrau(50, +1) == 100
        assert _proximo_degrau(50, -1) == 25
        assert _proximo_degrau(0, -1) == 0          # nao passa do chao
        assert _proximo_degrau(1000, +1) == 1000    # nem do teto
        assert _proximo_degrau(37, +1) == 50        # valor fora da tabela

    def test_teclas_mudam_o_filtro(self, tape):
        tape.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.NoModifier))
        assert tape.qty_minima == 5
        tape.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Minus, Qt.KeyboardModifier.NoModifier))
        assert tape.qty_minima == 0


class TestSemCor:
    """§3.2: o modo sem cor e teste de regressao, nao enfeite.

    Se algum painel so distingue compra de venda pela cor, e aqui que
    aparece — porque nesta paleta as duas cores sao a MESMA.
    """

    def test_a_paleta_realmente_colapsa(self):
        p = tokens.PALETA_SEM_COR
        assert p.direcional(1) == p.direcional(-1)

    def test_tape_desenha_nas_duas_paletas_sem_estourar(self, qapp):
        for paleta in (tokens.PALETA_COR, tokens.PALETA_SEM_COR):
            painel = _pronto(PainelTape(WDO_GRID, paleta=paleta), 380, 400)
            painel.aplicar(
                (
                    ItemTape(T0, BASE, 300, 1),
                    ItemTape(T0 + 1, BASE - 1, 12, -1),
                    ItemTape(T0 + 2, BASE, 7, 0),
                )
            )
            painel.marcar_tudo_sujo()
            painel._quadro()
            assert painel.quadros_desenhados >= 1

    def test_a_seta_carrega_a_direcao_sem_a_cor(self):
        """O portador redundante, verificado como dado e nao como pixel.

        A luminancia de `--buy` e `--sell` e praticamente igual (1,07:1),
        entao num print em escala de cinza a cor nao salva ninguem. A seta
        salva.
        """
        from fluxopro.ui.paineis.tape import SEM_LADO, SETA_COMPRA, SETA_VENDA

        assert SETA_COMPRA != SETA_VENDA != SEM_LADO
        assert len({SETA_COMPRA, SETA_VENDA, SEM_LADO}) == 3

    def test_dom_desenha_sem_cor(self, qapp):
        painel = _pronto(PainelDOM(WDO_GRID, paleta=tokens.PALETA_SEM_COR), 420, 400)
        painel.aplicar(livro(), BASE)
        painel.marcar_tudo_sujo()
        painel._quadro()
        assert painel.quadros_desenhados >= 1


def _retrato(**trocas) -> Instantaneo:
    padrao = dict(
        estado=EstadoFeed.VIVO,
        ultimo_preco=BASE,
        primeiro_preco=BASE - 10,
        volume_sessao=12_480,
        delta_sessao=1_240,
        volume_nao_atribuido=0,
        ultimo_evento_ns=T0,
        atraso_s=0.05,
        contadores=Contadores(trades=900, snapshots=100, deltas=50),
    )
    padrao.update(trocas)
    return Instantaneo(**padrao)


class TestStrips:
    def test_topo_so_suja_quando_algo_visivel_muda(self, qapp):
        """Sem isto a strip repintaria 62 vezes por segundo para sempre.

        O atraso e arredondado a decimo de segundo justamente porque ele
        muda a cada quadro por construcao — e um campo que sempre muda
        anularia a economia de todo o resto.
        """
        topo = _pronto(StripTopo("WDOV26", WDO_GRID), 1200, 28)
        topo.aplicar(_retrato())
        topo._quadro()
        topo.aplicar(_retrato(atraso_s=0.052))
        assert not topo.tem_sujeira

    def test_topo_suja_quando_o_preco_muda(self, qapp):
        topo = _pronto(StripTopo("WDOV26", WDO_GRID), 1200, 28)
        topo.aplicar(_retrato())
        topo._quadro()
        topo.aplicar(_retrato(ultimo_preco=BASE + 1))
        assert topo.tem_sujeira

    def test_rodape_mostra_o_descarte(self, qapp):
        rodape = _pronto(StripRodape(), 1200, 22)
        rodape.aplicar(_retrato(contadores=Contadores(trades=10, descartados_tape=42)), 0.3, 0)
        assert "42 descartados" in rodape._texto_direita

    def test_rodape_omite_o_descarte_quando_nao_ha(self, qapp):
        rodape = _pronto(StripRodape(), 1200, 22)
        rodape.aplicar(_retrato(), 0.3, 0)
        assert "descartados" not in rodape._texto_direita

    def test_estado_do_feed_tem_cor_propria(self, qapp):
        from fluxopro.ui.paineis.strips import cor_do_estado

        assert cor_do_estado(EstadoFeed.VIVO) is tokens.OK
        assert cor_do_estado(EstadoFeed.ATRASADO) is tokens.ALERT
        assert cor_do_estado(EstadoFeed.SEM_FEED) is tokens.DANGER

    def test_volume_sem_lado_aparece_quando_existe(self, qapp):
        """RLP visivel: o Δdia nao pode parecer o retrato completo do dia.

        Se ha volume cujo agressor a B3 nao divulga, o operador tem direito
        de saber quanto do dia ficou de fora da conta.
        """
        topo = _pronto(StripTopo("WDOV26", WDO_GRID), 1200, 28)
        topo.aplicar(_retrato(volume_nao_atribuido=1_500))
        topo._quadro()
        assert topo._nao_atribuido == 1_500
