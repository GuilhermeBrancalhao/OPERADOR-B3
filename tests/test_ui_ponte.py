"""A ponte `Barramento` -> Qt. Sem Qt: a classe e pura de proposito.

O teste central deste arquivo e o de RETENCAO. Este projeto encontrou a
mesma forma de defeito em oito arquivos diferentes — "estrutura que cresce
com o estado acumulado e e varrida tarde demais" — e nenhuma das oito foi
achada medindo vazao, porque enquanto a estrutura incha a MEDIA ate melhora.
Um buffer entre a thread da fonte e a thread da interface e o lugar mais
obvio possivel para a nona, e por isso ele nasce com teto, com contador de
descarte, e com um teste que prova as duas coisas.
"""

from __future__ import annotations

import threading

import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.ui import ponte as mod_ponte
from fluxopro.ui.ponte import EstadoFeed, PonteFluxo

T0 = 1_700_000_000_000_000_000


def trade(i: int, qty: int = 10, lado: AgressorSide = AgressorSide.BUY, preco: int = 10_173) -> Trade:
    return Trade(T0 + i * 1_000_000, "WDOV26", preco, qty, lado, f"t{i}")


def snapshot(i: int, preco: int = 10_173) -> BookSnapshot:
    return BookSnapshot(
        T0 + i * 1_000_000,
        "WDOV26",
        tuple(BookLevel(preco - k - 1, 100 + k, 1) for k in range(5)),
        tuple(BookLevel(preco + k + 1, 90 + k, 1) for k in range(5)),
    )


@pytest.fixture
def par():
    bus = Barramento()
    return bus, PonteFluxo(bus)


class TestRetencao:
    def test_o_buffer_nao_cresce_com_o_numero_de_eventos(self, par):
        """A prova de que nao ha nona casa.

        Mede a estrutura ALCANCAVEL, nao um `len` de topo: o defeito do
        `gravador` era um `dict -> list` cujo `len` de topo valia 1 com um
        milhao de timestamps dentro. Aqui a soma dos `len` internos e o que
        tem de ficar parado.
        """
        bus, p = par

        def tamanho() -> int:
            return len(p._tape) + len(p._eventos)

        # As duas medidas TEM de estar acima da capacidade: comparar um
        # buffer ainda enchendo (500) com um saturado provaria so que 500 !=
        # 4096, que e verdade e nao e o ponto.
        for i in range(5_000):
            bus.publicar(trade(i))
        depois_de_5k = tamanho()

        for i in range(5_000, 50_000):
            bus.publicar(trade(i))
        depois_de_50k = tamanho()

        assert depois_de_50k == depois_de_5k == mod_ponte.CAPACIDADE_TAPE
        # E o livro NAO acumula: so o ultimo importa para o DOM.
        for i in range(10_000):
            bus.publicar(snapshot(i))
        assert isinstance(p._livro, BookSnapshot)
        assert tamanho() == mod_ponte.CAPACIDADE_TAPE

    def test_o_que_foi_descartado_e_contado_e_nao_engolido(self, par):
        """Painel que some com dado em silencio mente sobre a propria cobertura.

        As duas telas — a que conta e a que nao conta — perdem o MESMO dado.
        So uma admite, e e a diferenca entre um operador que sabe que o
        pregao passou rapido demais e um que acha que viu tudo.
        """
        bus, p = par
        total = mod_ponte.CAPACIDADE_TAPE + 137
        for i in range(total):
            bus.publicar(trade(i))
        retrato = p.ler()
        assert retrato.contadores.trades == total
        assert retrato.contadores.descartados_tape == 137
        assert len(retrato.novos_trades) == mod_ponte.CAPACIDADE_TAPE

    def test_contadores_de_sessao_nao_sao_afetados_pelo_descarte(self, par):
        # Volume e delta do dia sao agregados na entrada, nao derivados do
        # buffer. Se dependessem do buffer, um engasgo da UI mudaria o
        # numero do dia — que e informacao de mercado, nao de interface.
        bus, p = par
        for i in range(mod_ponte.CAPACIDADE_TAPE * 3):
            bus.publicar(trade(i, qty=2))
        retrato = p.ler()
        assert retrato.volume_sessao == mod_ponte.CAPACIDADE_TAPE * 3 * 2

    def test_eventos_tambem_tem_teto_e_contador(self, par):
        _, p = par
        for i in range(mod_ponte.CAPACIDADE_EVENTOS + 9):
            p.registrar_evento(object())
        assert p._contadores.descartados_eventos == 9
        assert len(p.drenar_eventos()) == mod_ponte.CAPACIDADE_EVENTOS


class TestAgressao:
    def test_delta_e_volume_com_lados_misturados(self, par):
        bus, p = par
        bus.publicar(trade(1, qty=30, lado=AgressorSide.BUY))
        bus.publicar(trade(2, qty=12, lado=AgressorSide.SELL))
        retrato = p.ler()
        assert retrato.volume_sessao == 42
        assert retrato.delta_sessao == 18

    def test_rlp_entra_no_volume_e_nao_no_delta_e_e_contado(self, par):
        """A B3 anonimiza ate 15% do volume de WDO/WIN pela regra do RLP.

        Somar esse volume no delta inventaria direcao; descarta-lo em
        silencio faria o painel mentir sobre a propria cobertura. A terceira
        opcao — contar a parte sem lado — e a unica honesta, e e a mesma que
        o `Candle` do nucleo adotou.
        """
        bus, p = par
        bus.publicar(trade(1, qty=100, lado=AgressorSide.BUY))
        bus.publicar(trade(2, qty=40, lado=AgressorSide.UNKNOWN))
        retrato = p.ler()
        assert retrato.volume_sessao == 140
        assert retrato.delta_sessao == 100
        assert retrato.volume_nao_atribuido == 40
        # Invariante: volume == comprado - vendido (em modulo) + sem lado.
        assert retrato.volume_sessao == abs(retrato.delta_sessao) + retrato.volume_nao_atribuido

    def test_agressor_vira_inteiro_na_entrada(self, par):
        # `Enum.__hash__` e um metodo Python; a onda 7 mediu isso custando
        # caro no caminho quente. A conversao acontece UMA vez.
        bus, p = par
        bus.publicar(trade(1, lado=AgressorSide.SELL))
        (item,) = p.ler().novos_trades
        assert item.agressor == -1
        assert isinstance(item.agressor, int)


class TestDrenagem:
    def test_ler_esvazia_e_o_segundo_leitor_ve_vazio(self, par):
        """O contrato de UM DONO, fixado como teste e nao so como docstring.

        Se alguem apontar um segundo painel direto na ponte, este teste
        continua passando (e correto), mas o comportamento fica documentado
        onde o proximo builder vai procurar.
        """
        bus, p = par
        bus.publicar(trade(1))
        assert len(p.ler().novos_trades) == 1
        assert p.ler().novos_trades == ()

    def test_retrato_e_consistente_entre_campos(self, par):
        # Ler campo a campo enquanto a fonte escreve daria uma tela costurada
        # de dois instantes: preco de agora com volume de antes.
        bus, p = par
        for i in range(1, 11):
            bus.publicar(trade(i, qty=1, preco=10_000 + i))
        retrato = p.ler()
        assert retrato.ultimo_preco == 10_010
        assert retrato.volume_sessao == 10
        assert retrato.novos_trades[-1].price == 10_010

    def test_primeiro_preco_fica_congelado_para_a_variacao_do_dia(self, par):
        bus, p = par
        bus.publicar(trade(1, preco=10_000))
        bus.publicar(trade(2, preco=10_050))
        retrato = p.ler()
        assert retrato.primeiro_preco == 10_000
        assert retrato.ultimo_preco == 10_050


class TestEstadoDoFeed:
    """§3.5: num terminal de fluxo o estado da conexao E informacao de trading."""

    def test_antes_do_primeiro_evento(self, par):
        _, p = par
        assert p.ler().estado is EstadoFeed.AGUARDANDO

    def test_vivo_atrasado_e_sem_feed_pelo_relogio_de_parede(self, par, monkeypatch):
        bus, p = par
        agora = [1000.0]
        monkeypatch.setattr(mod_ponte.time, "perf_counter", lambda: agora[0])

        bus.publicar(trade(1))
        assert p.ler().estado is EstadoFeed.VIVO

        agora[0] += mod_ponte.LIMITE_ATRASO_S + 0.1
        retrato = p.ler()
        assert retrato.estado is EstadoFeed.ATRASADO
        assert retrato.atraso_s == pytest.approx(2.1, abs=0.01)

        agora[0] += mod_ponte.LIMITE_DESCONEXAO_S
        assert p.ler().estado is EstadoFeed.SEM_FEED

    def test_replay_de_arquivo_antigo_nao_parece_feed_morto(self, par, monkeypatch):
        """Dois relogios de proposito.

        `timestamp_ns` e tempo de MERCADO — num replay pode ser 2019. Se o
        estado saisse dele, todo replay abriria como "SEM FEED" e a tarja de
        desconexao ficaria acesa o tempo todo, que e o jeito mais rapido de
        ensinar um operador a ignorar a tarja.
        """
        bus, p = par
        agora = [1000.0]
        monkeypatch.setattr(mod_ponte.time, "perf_counter", lambda: agora[0])
        antigo = Trade(1_500_000_000_000_000_000, "WDOV26", 10_000, 1, AgressorSide.BUY, "velho")
        bus.publicar(antigo)
        assert p.ler().estado is EstadoFeed.VIVO

    def test_encerrado_vence_o_atraso(self, par):
        bus, p = par
        bus.publicar(trade(1))
        p.marcar_encerrado()
        assert p.ler().estado is EstadoFeed.ENCERRADO


class TestConcorrencia:
    def test_produtor_em_outra_thread_nao_perde_contagem(self, par):
        """A fonte roda em thread propria (`scripts/painel.py`).

        Nao prova ausencia de corrida — nenhum teste prova —, mas se o lock
        sumir num refactor, os contadores divergem sob esta carga.
        """
        bus, p = par
        n_por_thread, n_threads = 2000, 4

        def produzir(base: int) -> None:
            for i in range(n_por_thread):
                bus.publicar(trade(base + i, qty=1))

        threads = [
            threading.Thread(target=produzir, args=(t * n_por_thread,)) for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        retrato = p.ler()
        esperado = n_por_thread * n_threads
        assert retrato.contadores.trades == esperado
        assert retrato.volume_sessao == esperado

    def test_leitura_concorrente_com_escrita_nao_estoura(self, par):
        bus, p = par
        parar = threading.Event()

        def produzir() -> None:
            i = 0
            while not parar.is_set():
                bus.publicar(trade(i, qty=1))
                i += 1

        produtor = threading.Thread(target=produzir)
        produtor.start()
        try:
            for _ in range(200):
                retrato = p.ler()
                # Invariante que uma leitura rasgada quebraria: o retrato
                # nunca mostra mais negocios drenados do que a sessao contou.
                assert len(retrato.novos_trades) <= retrato.contadores.trades
        finally:
            parar.set()
            produtor.join(timeout=5.0)


class TestDesligar:
    def test_solta_as_assinaturas(self, par):
        """Janela fechada nao pode continuar recebendo o pregao.

        No Qt isso e pior que vazamento: o callback aponta para um widget
        destruido, e chamar la e falha de segmentacao, nao excecao.
        """
        bus, p = par
        bus.publicar(trade(1))
        antes = p.ler().contadores.trades
        p.desligar()
        for i in range(100):
            bus.publicar(trade(i))
        assert p.ler().contadores.trades == antes

    def test_deltas_de_book_contam_mas_nao_acumulam(self, par):
        bus, p = par
        for i in range(1000):
            bus.publicar(
                BookDelta(T0 + i, "WDOV26", Side.BUY, BookAction.UPDATE, 10_000, 5, 0)
            )
        retrato = p.ler()
        assert retrato.contadores.deltas == 1000
        assert len(p._tape) == 0
