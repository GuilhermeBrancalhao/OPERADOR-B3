"""Formatacao da interface — puro, sem Qt e sem tela.

O que estes testes protegem nao e estetica. Sao tres regras de leitura que
o `design/direcao_visual.md` §3.4 levanta a partir de fraquezas concretas
da barra que serviu de referencia, e que somem no primeiro refactor se
ninguem estiver olhando.
"""

from __future__ import annotations

import pytest

from fluxopro.core.eventos import WDO_GRID, WIN_GRID, PriceGrid
from fluxopro.ui import formato


class TestSinalExplicito:
    """A fraqueza F2: `(49,10k)` e `(42,31k)` distinguiveis so pela cor.

    Um print em escala de cinza, um monitor mal calibrado ou um operador
    daltonico perdem o dado inteiro. O sinal tem de estar no TEXTO.
    """

    def test_positivo_leva_mais(self):
        assert formato.formatar_sinalizado(1240) == "+1.240"

    def test_negativo_leva_menos_tipografico_nunca_parenteses(self):
        saida = formato.formatar_sinalizado(-1240)
        assert saida == "−1.240"
        assert "(" not in saida and ")" not in saida

    def test_zero_nao_leva_sinal(self):
        # `+0` sugeriria compra marginal onde nao ha nada. Zero de delta e um
        # estado com significado proprio — equilibrio —, nao um positivo
        # pequeno.
        assert formato.formatar_sinalizado(0) == "0"

    def test_direcao_e_recuperavel_do_texto_sozinho(self):
        # A prova da regra: sem NENHUMA cor, os dois valores sao
        # distinguiveis. E o que o modo sem cor depende para funcionar.
        assert formato.formatar_sinalizado(4910) != formato.formatar_sinalizado(-4910)
        assert formato.formatar_sinalizado(-4910).startswith(formato.MENOS)

    def test_menos_e_u2212_e_nao_hifen(self):
        # Numa monoespacada o hifen tem a largura certa e a ALTURA errada:
        # fica baixo e curto, e some ao lado de digitos.
        assert formato.MENOS == "−"
        assert "-" not in formato.formatar_sinalizado(-7)

    def test_casas_decimais(self):
        assert formato.formatar_sinalizado(-1234.5, casas=1) == "−1.234,5"
        assert formato.formatar_sinalizado(0.004, casas=2) == "0,00"

    def test_percentual(self):
        assert formato.formatar_percentual(0.0034) == "+0,34%"
        assert formato.formatar_percentual(-0.053, casas=1) == "−5,3%"


class TestDigitosEstaveis:
    """A fraqueza F6: preco sem hierarquia visual.

    O corte entre o que esta parado e o que se mexe e DERIVADO da grade de
    precos, nao escolhido a olho — e por isso funciona para WDO e WIN sem
    regra por instrumento.
    """

    def test_wdo_bate_a_referencia_do_documento(self):
        # §4.3 grafa exatamente `5.08` + `6,5`.
        assert formato.formatar_preco(WDO_GRID, WDO_GRID.to_ticks(5086.5)) == ("5.08", "6,5")

    def test_win_um_tick_alcanca_dois_digitos(self):
        assert formato.formatar_preco(WIN_GRID, WIN_GRID.to_ticks(141230)) == ("141.2", "30")

    def test_concatenados_dao_o_preco_inteiro(self):
        for grid, preco in ((WDO_GRID, 5086.5), (WDO_GRID, 999.5), (WIN_GRID, 141230)):
            ticks = grid.to_ticks(preco)
            estavel, vivo = formato.formatar_preco(grid, ticks)
            assert estavel + vivo == formato.preco_completo(grid, ticks)

    def test_a_parte_apagada_e_sempre_redundante(self):
        # Condicao de §3.2 para usar `--text-muted` (3,94:1, so AA-large):
        # ele nunca pode carregar informacao sozinho. Aqui isso e estrutural
        # — o prefixo esta contido no numero completo.
        ticks = WDO_GRID.to_ticks(5086.5)
        estavel, _ = formato.formatar_preco(WDO_GRID, ticks)
        assert formato.preco_completo(WDO_GRID, ticks).startswith(estavel)

    def test_largura_do_corte_nao_depende_do_preco_visto_primeiro(self):
        """O bug que a primeira versao tinha, fixado como regressao.

        Medir o prefixo comum contra os vizinhos a +-8 ticks dava corte
        DIFERENTE perto de uma virada de dezena, entao a largura da coluna
        passava a depender de qual preco a sessao viu primeiro. Coluna que
        muda de forma sozinha e pior que coluna sem corte nenhum.
        """
        ordem_a = [5080.0, 5086.5, 5089.5, 5090.0]
        larguras = {len(formato.formatar_preco(WDO_GRID, WDO_GRID.to_ticks(p))[1]) for p in ordem_a}
        assert larguras == {3}, "todo preco de 4 digitos+1 casa tem 3 chars vivos"

    def test_derivacao_vale_para_grade_inventada(self):
        # Nao ha tabela por instrumento: a regra sai do tick.
        grid = PriceGrid(tick_size=0.01, decimals=2)
        assert formato.n_digitos_vivos(grid) == 2
        assert formato.formatar_preco(grid, grid.to_ticks(12.34)) == ("12,", "34")


class TestUnidadeFixa:
    def test_inteiro_agrupa_milhar_em_pt_br(self):
        assert formato.formatar_inteiro(1240) == "1.240"
        assert formato.formatar_inteiro(999) == "999"
        assert formato.formatar_inteiro(1234567) == "1.234.567"

    def test_agrupamento_nao_depende_de_locale(self):
        # `locale` e estado global do processo e varia por maquina: seria a
        # mesma tela mostrando numeros diferentes em duas maquinas do mesmo
        # escritorio.
        import locale as _locale

        anterior = _locale.setlocale(_locale.LC_ALL)
        try:
            try:
                _locale.setlocale(_locale.LC_ALL, "C")
            except _locale.Error:
                pytest.skip("locale C indisponivel nesta maquina")
            assert formato.formatar_inteiro(1234567) == "1.234.567"
        finally:
            _locale.setlocale(_locale.LC_ALL, anterior)

    def test_abreviar_e_so_para_coluna_que_escolheu_essa_unidade(self):
        assert formato.abreviar(2400) == "+2,4k"
        assert formato.abreviar(-1_400_000) == "−1,4M"
        assert formato.abreviar(940) == "+940"

    def test_abreviar_sem_sinal(self):
        assert formato.abreviar(2400, com_sinal=False) == "2,4k"


class TestTempo:
    def test_milissegundo_aparece(self):
        # No tape, dois negocios no mesmo segundo sao a diferenca entre uma
        # ordem grande fatiada e duas decisoes distintas.
        saida = formato.formatar_hora_ns(1_700_000_007_412_000_000)
        assert saida.endswith(",412")
        assert len(saida) == len("00:00:00,000")

    def test_duracao_troca_de_unidade_no_segundo(self):
        assert formato.formatar_duracao_s(4.2) == "4,2 s"
        assert formato.formatar_duracao_s(0.32) == "320 ms"
