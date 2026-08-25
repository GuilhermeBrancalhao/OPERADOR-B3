"""A janela montada, e o pipeline inteiro entrando nela.

Os testes de painel provam cada peca; estes provam a costura, que e onde
moram os defeitos que nenhum teste de unidade ve: quem le a ponte, quem
distribui, quem desliga.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados  # noqa: E402
from fluxopro.app.montagem import montar  # noqa: E402
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import (  # noqa: E402
    WDO_GRID,
    AgressorSide,
    BookLevel,
    BookSnapshot,
    Trade,
)
from fluxopro.ui.janela import JanelaFluxo  # noqa: E402
from fluxopro.ui.ponte import EstadoFeed, PonteFluxo  # noqa: E402
from fluxopro.ui.workspace import WORKSPACE_ASG  # noqa: E402

T0 = 1_700_000_000_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)


@pytest.fixture
def montagem_ui(qapp):
    bus = Barramento()
    ponte = PonteFluxo(bus)
    janela = JanelaFluxo(ponte, "WDOV26", WDO_GRID)
    janela.resize(1280, 800)
    janela.show()
    yield bus, ponte, janela
    janela.close()


def _publicar(bus, i: int, preco: int = BASE) -> None:
    bus.publicar(
        Trade(T0 + i * 1_000_000, "WDOV26", preco, 5 + i % 20,
              AgressorSide.BUY if i % 2 else AgressorSide.SELL, f"t{i}")
    )
    bus.publicar(
        BookSnapshot(
            T0 + i * 1_000_000,
            "WDOV26",
            tuple(BookLevel(preco - k - 1, 100 + k + i, 1) for k in range(8)),
            tuple(BookLevel(preco + k + 1, 90 + k + i, 1) for k in range(8)),
        )
    )


class TestRelogioUnico:
    def test_um_tick_alimenta_todos_os_paineis(self, montagem_ui):
        """A razao de a janela ser dona do relogio de dados.

        `PonteFluxo.ler()` esvazia o buffer. Se cada painel lesse por conta
        propria, o segundo receberia tape vazio — e o bug apareceria como
        "o tape as vezes pula negocios", que e das coisas mais dificeis de
        diagnosticar depois.
        """
        bus, _, janela = montagem_ui
        for i in range(30):
            _publicar(bus, i)
        janela._tick()

        assert janela.dom._centro is not None, "DOM recebeu o livro"
        assert len(janela.tape._linhas) == 30, "tape recebeu TODOS os negocios"
        assert janela.topo._ultimo == BASE, "strip recebeu o preco"

    def test_paineis_mostram_o_mesmo_instante(self, montagem_ui):
        # Tela costurada de tres momentos e o que um retrato unico evita.
        bus, _, janela = montagem_ui
        for i in range(10):
            _publicar(bus, i, BASE + i)
        janela._tick()
        assert janela.topo._ultimo == janela.tape._linhas[0].price == BASE + 9

    def test_tick_sem_dado_nao_gera_trabalho(self, montagem_ui):
        """Feed parado tem de custar zero quadros, ponta a ponta.

        A primeira versao deste teste media `tem_sujeira` logo depois de 50
        ticks e reprovava por um motivo legitimo que eu nao tinha previsto: o
        RASTRO do DOM ainda estava expirando, e a expiracao suja a linha de
        proposito (e o que apaga o realce). O teste estava errado sobre o
        codigo. Medir quadros DESENHADOS depois de o rastro apagar e a
        pergunta certa.
        """
        from fluxopro.ui.paineis.dom import QUADROS_RASTRO

        bus, _, janela = montagem_ui
        _publicar(bus, 0)
        paineis = (janela.dom, janela.tape, janela.topo, janela.rodape)
        for _ in range(QUADROS_RASTRO + 5):
            janela._tick()
            for painel in paineis:
                painel._quadro()

        for painel in paineis:
            painel.zerar_medicao()
        for _ in range(50):
            janela._tick()
            for painel in paineis:
                painel._quadro()

        assert janela.dom.quadros_desenhados == 0
        assert janela.tape.quadros_desenhados == 0
        assert janela.dom.quadros_vazios == 50


class TestFaixaDeEstado:
    def test_discreta_quando_esta_tudo_bem(self, montagem_ui):
        bus, _, janela = montagem_ui
        _publicar(bus, 0)
        janela._tick()
        assert janela._estado_faixa is EstadoFeed.VIVO

    def test_grita_quando_o_feed_morre(self, montagem_ui, monkeypatch):
        """§3.5: "estado global merece sinal global"."""
        from fluxopro.ui import ponte as mod_ponte

        bus, _, janela = montagem_ui
        agora = [1000.0]
        monkeypatch.setattr(mod_ponte.time, "perf_counter", lambda: agora[0])
        _publicar(bus, 0)
        janela._tick()
        agora[0] += mod_ponte.LIMITE_DESCONEXAO_S + 1
        janela._tick()
        assert janela._estado_faixa is EstadoFeed.SEM_FEED


class TestASGR6:
    def test_ctrl5_tem_retrato_bloqueado_antes_do_primeiro_tick(self, montagem_ui, qapp):
        _, _, janela = montagem_ui
        janela.aplicar_workspace(WORKSPACE_ASG)
        qapp.processEvents()
        assert janela._area_operacional.currentWidget() is janela.asg
        assert janela.asg._snapshot is not None
        for painel in janela.asg.paineis:
            painel._quadro()
        assert "AGUARDANDO" in " ".join(janela.asg.contexto_bruto.textos_visiveis())

    @pytest.mark.parametrize(
        ("estado_asg", "estado_global"),
        [
            ("AO_VIVO", EstadoFeed.VIVO),
            ("ATRASADO", EstadoFeed.ATRASADO),
            ("SEM_BOOK", EstadoFeed.SEM_BOOK),
            ("ERRO", EstadoFeed.ERRO),
            ("REPLAY", EstadoFeed.VIVO),
        ],
    )
    def test_fixture_de_estados_sincroniza_topo_rodape_tarja_e_asg(
        self, montagem_ui, estado_asg, estado_global
    ):
        from fluxopro.ui.paineis.asg import EstadoASG
        from scripts.painel import aplicar_fixture_asg

        _, _, janela = montagem_ui
        estado = EstadoASG[estado_asg]
        aplicar_fixture_asg(janela, estado)

        assert janela.topo._estado is estado_global
        assert janela._estado_faixa is estado_global
        assert estado.value in janela.rodape._texto_esquerda
        assert all(estado.value in " ".join(painel.textos_visiveis())
                   for painel in janela.asg.paineis)
        assert janela.tarja_replay.isVisible() is (estado is EstadoASG.REPLAY)


class TestFechamento:
    def test_fechar_solta_o_barramento_e_para_os_relogios(self, qapp):
        """No Qt isto nao e vazamento, e falha de segmentacao.

        Uma janela fechada cujos callbacks continuam no barramento aponta
        para widgets destruidos, e chamar la derruba o processo.
        """
        bus = Barramento()
        ponte = PonteFluxo(bus)
        janela = JanelaFluxo(ponte, "WDOV26", WDO_GRID)
        janela.show()
        _publicar(bus, 0)
        janela.close()

        for i in range(100):
            _publicar(bus, i)
        assert ponte.ler().contadores.trades == 1
        assert not janela._relogio.isActive()
        assert not janela.dom._timer.isActive()

    def test_callback_de_fechamento_e_chamado(self, qapp):
        bus = Barramento()
        chamado = []
        janela = JanelaFluxo(
            PonteFluxo(bus), "WDOV26", WDO_GRID, ao_fechar=lambda: chamado.append(True)
        )
        janela.show()
        janela.close()
        assert chamado == [True]


class TestPipelineCompleto:
    def test_o_simulador_atravessa_ate_a_tela(self, qapp):
        """Do gerador de eventos ate o backing store, sem atalho.

        E a unica prova de que a interface esta ligada no MESMO pipeline do
        CLI e nao numa copia paralela — se o painel mostrasse numero
        diferente de `scripts/operar.py`, um dos dois estaria mentindo.

        Continua sendo dado SIMULADO: nenhum byte de mercado real existe em
        disco neste projeto, e nenhum teste desta suite prova o contrario.
        """
        config = ConfigOperacao(
            symbol="WDOV26",
            fonte=FonteDados.SIMULADOR,
            simulador=ConfigSimulador(seed=42, n_eventos=3_000, taxa_eventos_s=1e6),
        )
        ponte_ref = {}
        montagem = montar(
            config,
            ao_sinal=lambda e: ponte_ref["p"].registrar_evento(e),
            ao_deteccao=lambda e: ponte_ref["p"].registrar_evento(e),
        )
        ponte = PonteFluxo(montagem.barramento)
        ponte_ref["p"] = ponte

        janela = JanelaFluxo(ponte, config.symbol, config.price_grid())
        janela.resize(1280, 800)
        janela.show()
        try:
            montagem.fonte.iniciar()  # sincrono e sem espera entre eventos
            janela._tick()
            for painel in (janela.dom, janela.tape, janela.topo, janela.rodape):
                painel._quadro()

            retrato = ponte.ler()
            assert retrato.contadores.trades > 0
            assert janela.dom._backing is not None
            assert janela.dom.quadros_desenhados >= 1
            assert janela.tape._linhas, "o tape recebeu negocios do simulador"
            # O painel conta o MESMO que a sessao de dominio contou. E a
            # asserçao que prova que sao um pipeline so: a `SessaoFluxo`
            # mantem um contador por elo da cadeia justamente para que a
            # desconexao de qualquer peca vire teste vermelho em vez de
            # silencio, e a interface passa a ser mais um elo conferido.
            assert retrato.contadores.trades == montagem.sessao.contadores.n_trades_bus
        finally:
            janela.close()
            montagem.sessao.finalizar()
