"""Tokens — contraste RECALCULADO, nao afirmado.

`design/direcao_visual.md` §3.2 publica uma tabela de razoes de contraste.
Uma tabela num documento e uma alegacao: alguem troca `#3B9EFF` por um azul
mais bonito, a tabela continua dizendo 6,92:1 e ninguem descobre ate um
operador daltonico reclamar. Aqui a razao sai do proprio `QColor`, entao a
troca do hex reprova o teste na hora.

A licao e a mesma que este projeto ja pagou no `PROGRESSO.md`: numero velho
sob selo de verificacao e pior que numero nenhum, porque convida a confiar.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui", reason="PySide6 nao instalado")

from fluxopro.ui import tokens  # noqa: E402


def _luminancia(cor) -> float:
    """Luminancia relativa WCAG 2.1."""
    def canal(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(cor.red()) + 0.7152 * canal(cor.green()) + 0.0722 * canal(cor.blue())


def contraste(a, b) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


# Piso por token, contra `--bg-base`. Sao os niveis WCAG que §3.2 declara,
# nao os valores exatos: exigir 6,92 na terceira casa reprovaria por um
# arredondamento e ensinaria a desligar o teste.
PISOS = {
    "TEXT_PRIMARY": 7.0,   # AAA
    "TEXT_SECONDARY": 7.0,  # AAA
    "TEXT_MUTED": 3.0,     # AA-large — o unico abaixo de AA, e por isso so
                           # pode aparecer em >=14px ou em conteudo redundante
    "BUY": 4.5,            # AA
    "SELL": 4.5,
    "NEUTRAL": 4.5,
    "ABSORPTION": 7.0,
    "ALERT": 7.0,
    "SIGNAL": 7.0,
    "POC": 7.0,
    "VWAP": 7.0,
    "OK": 7.0,
    "DANGER": 4.5,
}


@pytest.mark.parametrize("nome,piso", sorted(PISOS.items()))
def test_contraste_contra_o_fundo(nome, piso):
    razao = contraste(getattr(tokens, nome), tokens.BG_BASE)
    assert razao >= piso, f"{nome}: {razao:.2f}:1 abaixo do piso {piso}:1"


def test_nenhum_token_de_informacao_abaixo_de_3():
    """§3.2, ultima linha da tabela. Nao ha excecao."""
    for nome in PISOS:
        assert contraste(getattr(tokens, nome), tokens.BG_BASE) >= 3.0


def test_eixo_direcional_sobrevive_a_deuteranopia_e_protanopia():
    """A razao de ser azul/vermelho e nao verde/vermelho.

    Deuteranopia e protanopia (~8% dos homens) colapsam o eixo verde-
    vermelho porque comprimem os cones L e M; o canal AZUL fica intacto nas
    duas. Entao a propriedade que importa e a separacao em azul — e ela e
    grande: 255 contra 108.

    O que este teste NAO afirma, e a primeira versao dele afirmava por
    engano: que as duas cores sobrevivem a escala de cinza. Nao sobrevivem —
    a luminancia relativa das duas e praticamente a mesma (**1,07:1**), e num
    print monocromatico compra e venda saem no mesmo tom. Isso nao e defeito
    do token, e a razao de existir a redundancia obrigatoria de §3.2: sinal
    explicito + cor + posicao, tres portadores. A cor e o terceiro, nunca o
    unico — ver `test_direcao_e_recuperavel_do_texto_sozinho` em
    `test_ui_formato.py` e o modo sem cor logo abaixo.
    """
    assert abs(tokens.BUY.blue() - tokens.SELL.blue()) >= 100
    # E o par nao pode ser verde/vermelho, que e o que se quis evitar.
    assert tokens.BUY.blue() > tokens.BUY.green()


def test_texto_primario_legivel_sobre_o_degrau_mais_saturado():
    """§3.2: o texto por cima da celula de footprint e sempre `--text-primary`.

    Se a rampa ficar escura demais na ponta, o numero dentro da celula some —
    e a celula existe para mostrar o numero, nao a cor.
    """
    for rampa in (tokens.RAMPA_COMPRA, tokens.RAMPA_VENDA, tokens.RAMPA_NEUTRA):
        razao = contraste(tokens.TEXT_PRIMARY, rampa[-1])
        assert razao >= 4.5, f"{razao:.2f}:1 no degrau mais saturado"


class TestRampas:
    def test_monotonica(self):
        # Uma rampa que nao cresce monotonamente inverteria a leitura: uma
        # celula com mais volume pareceria ter menos.
        for rampa in (tokens.RAMPA_COMPRA, tokens.RAMPA_VENDA, tokens.RAMPA_NEUTRA):
            distancias = [contraste(c, tokens.BG_SURFACE) for c in rampa]
            assert distancias == sorted(distancias), "rampa nao monotonica"

    def test_degrau_satura_nas_pontas_sem_levantar(self):
        # Volume acima do maximo conhecido da janela e evento normal em
        # pregao; derrubar o painel por causa disso seria trocar um pixel
        # errado por uma tela preta.
        assert tokens.degrau(-5.0) == 0
        assert tokens.degrau(0.0) == 0
        assert tokens.degrau(1.0) == tokens.N_DEGRAUS_INTENSIDADE - 1
        assert tokens.degrau(99.0) == tokens.N_DEGRAUS_INTENSIDADE - 1

    def test_todo_indice_da_rampa_e_alcancavel(self):
        alcancados = {tokens.degrau(i / 100.0) for i in range(101)}
        assert alcancados == set(range(tokens.N_DEGRAUS_INTENSIDADE))

    def test_cores_sao_opacas(self):
        # Achatadas no import de proposito: pintar com alfa em tempo de
        # execucao custa blend por pixel a cada quadro.
        for rampa in (tokens.RAMPA_COMPRA, tokens.RAMPA_VENDA):
            assert all(c.alpha() == 255 for c in rampa)


class TestPaleta:
    def test_zero_e_neutro_e_nao_compra(self):
        assert tokens.PALETA_COR.direcional(0) is tokens.NEUTRAL
        assert tokens.PALETA_COR.direcional(1) is tokens.BUY
        assert tokens.PALETA_COR.direcional(-1) is tokens.SELL

    def test_modo_sem_cor_colapsa_o_eixo_inteiro(self):
        """Nao basta "cinza claro x cinza escuro": luminancia tambem e canal.

        Se compra e venda saissem em dois cinzas diferentes, o modo estaria
        so trocando um canal visual por outro — e o teste de que a tela e
        legivel SEM canal visual nenhum deixaria de provar o que promete.
        """
        p = tokens.PALETA_SEM_COR
        assert p.direcional(1) == p.direcional(-1) == p.direcional(0)
        assert not p.tem_cor


class TestDensidade:
    def test_espacamento_e_par(self):
        """§3.4: unidade base 4px, "nada de 5, 7, 13".

        A regra do documento e sobre ESPACAMENTO. A primeira versao deste
        teste a aplicou tambem a largura de celula e reprovou a densidade
        Padrao por causa de `celula_footprint_w = 46` — que e um numero do
        proprio documento. Largura de celula e ditada pela metrica do texto
        que precisa caber dentro (`12× 4` numa fonte de 10px), nao pela
        grade de espacamento; forcar multiplo de 4 la seria arredondar o
        layout para satisfazer um teste que leu a regra larga demais.
        """
        for d in tokens.DENSIDADES:
            assert d.altura_linha % 2 == 0, f"{d.nome}: altura de linha impar"
            assert d.celula_footprint_h % 2 == 0
            assert d.celula_footprint_w % 2 == 0

    def test_a_linha_cabe_a_fonte(self):
        # 11px de texto + respiro + separador de 1px. Se a fonte crescer
        # acima da linha, os descendentes sao cortados.
        for d in tokens.DENSIDADES:
            assert d.altura_linha >= d.fonte_grade + 3

    def test_ordenadas_e_distintas(self):
        alturas = [d.altura_linha for d in tokens.DENSIDADES]
        assert alturas == sorted(alturas) == [14, 18, 22]

    def test_quarenta_niveis_cabem_em_meia_tela_1440p(self):
        # §3.4 justifica a densidade Padrao exatamente com esta conta.
        assert tokens.PADRAO.altura_para(40) == 720


class TestFontes:
    def test_memoizadas(self):
        # Trocar de fonte no painter e barato; CONSTRUIR uma por celula nao e.
        assert tokens.fonte_numero(11) is tokens.fonte_numero(11)
        assert tokens.fonte_numero(11) is not tokens.fonte_numero(12)

    def test_numero_e_monoespacada_mesmo_sem_iosevka_instalada(self):
        # A maquina de CI nao tem Iosevka. A coluna de numeros nao pode
        # depender disso para alinhar.
        fonte = tokens.fonte_numero(11)
        assert fonte.fixedPitch()
        assert fonte.families()[0] == "Iosevka Term"

    def test_iosevka_vem_primeiro_por_medida_e_nao_por_gosto(self):
        # 0,5em contra 0,6em = ~17% mais colunas na mesma largura.
        assert tokens.FAMILIAS_NUMERO[0] == "Iosevka Term"
        assert "Consolas" in tokens.FAMILIAS_NUMERO  # degradacao aceitavel
