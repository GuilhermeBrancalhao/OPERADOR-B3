"""Trocar a densidade a quente sem apagar o historico de tela.

Promovido de `tests/test_ui_workspace.py::test_sonda_densidade_preserva_historico`,
que era uma sonda `xfail` com endereco: `Ctrl+Shift+D` reconstruia os paineis e
o historico de TELA recomecava — colunas do footprint, plano do bookmap, linhas
do tape —, e o conserto pedido era um `aplicar_densidade(nova)` em
`paineis/footprint.py`, `paineis/bookmap.py` e `paineis/tape.py` que
recalculasse as `QFontMetrics` do construtor.

O que estes testes medem, e por que cada um existe:

* **Preservar nao basta.** A solucao ingenua — mutar `painel.densidade` e nao
  mexer em mais nada — preserva o historico INTEIRO e passaria em qualquer
  teste que so olhasse para ele. Ela deixa a geometria calculada com a fonte
  antiga e o texto desenhado com a nova: calha estreita, rotulo descartado por
  F8, nenhum erro em lugar nenhum. Entao a assercao principal nao e sobre o
  historico: e que o painel fica **indistinguivel de um recem-construido** na
  densidade nova, atributo derivado por atributo derivado.

* **Prova por mutacao, e ela e executavel.** `test_a_medicao_ingenua_reprova`
  aplica a densidade SEM remedir — exatamente o atalho recusado — e exige que
  a comparacao com o painel recem-construido falhe. Se um dia `_medir` virar
  no-op, e este teste que fica vermelho primeiro.

* **Ate o PIXEL.** A ultima frente e o desenho: os rotulos do rodape do
  footprint tem de continuar saindo. E o sintoma que a calha medida com a
  fonte errada produz, e nenhuma comparacao de atributo o cobre.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402

from fluxopro.core.eventos import WDO_GRID  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.bookmap import PainelBookmap  # noqa: E402
from fluxopro.ui.paineis.delta_acumulado import PainelDeltaAcumulado  # noqa: E402
from fluxopro.ui.paineis.footprint import (  # noqa: E402
    ROTULOS_RODAPE,
    Celula,
    Coluna,
    LeituraFootprint,
    PainelFootprint,
)
from fluxopro.ui.paineis.perfil import PainelPerfil  # noqa: E402
from fluxopro.ui.paineis.tape import PainelTape  # noqa: E402
from fluxopro.ui.ponte import ItemTape  # noqa: E402

BASE = 5000
T0 = 1_700_000_000_000_000_000
SIMBOLO = "WDOV26"


def _textos(painel) -> list[str]:
    pixmap = QPixmap(max(1, painel.width()), max(1, painel.height()))
    painter = QPainter(pixmap)
    vistos: list[str] = []
    original = painter.drawText

    class _Espiao:
        def __getattr__(self, nome):
            return getattr(painter, nome)

        def drawText(self, *args):  # noqa: N802
            for arg in args:
                if isinstance(arg, str):
                    vistos.append(arg)
            original(*args)

    try:
        painel.desenhar(_Espiao(), QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return vistos


def _coluna(inicio_ns: int, viva: bool = True) -> Coluna:
    niveis = tuple(
        (BASE + k, Celula(qty_venda=3 + k, qty_compra=4 + k, qty_sem_lado=0))
        for k in range(-4, 5)
    )
    return Coluna(
        inicio_ns=inicio_ns,
        viva=viva,
        niveis=niveis,
        volume_total=140,
        volume_compra=80,
        volume_venda=60,
        volume_sem_lado=0,
        delta=20,
        preco_maximo=BASE + 4,
        preco_minimo=BASE - 4,
    )


# --------------------------------------------------------------------------
# O que "densidade aplicada" tem de querer dizer, painel a painel
# --------------------------------------------------------------------------
#: Atributo derivado da densidade que um painel recem-construido teria. A
#: comparacao e contra o CONSTRUTOR, e nao contra numeros cravados aqui: um
#: valor cravado envelheceria na primeira mudanca de molde ou de fonte e o
#: teste passaria a medir a propria memoria.
DERIVADOS = {
    "footprint": (
        "_largura_calha",
        "_fm_preco",
        "_fm_celula",
        "_fm_rotulo",
        "_fm_chip",
    ),
    "bookmap": ("_largura_eixo", "_fm_grade", "_fm_rotulo"),
    "tape": ("_fm",),
    "perfil": ("_fm_rotulo", "_fm_chip"),
    "delta": ("_fm_rotulo", "_fm_chip", "_fm_numero"),
}


def _dimensionar(painel, largura: int, altura: int):
    """`resize` num widget que nunca foi mostrado nao dispara o evento do Qt,
    entao a geometria e aplicada explicitamente — do contrario metade destes
    testes mediria um painel de zero coluna e passaria por vacuidade."""
    painel.resize(largura, altura)
    painel.ao_redimensionar(largura, altura)
    return painel


def _novo(nome: str, d: tokens.Densidade):
    if nome == "footprint":
        return _dimensionar(
            PainelFootprint(WDO_GRID, densidade=d, simbolo=SIMBOLO, timeframe_ns=60),
            900,
            500,
        )
    if nome == "bookmap":
        return _dimensionar(PainelBookmap(WDO_GRID, symbol=SIMBOLO, densidade=d), 900, 500)
    if nome == "tape":
        return _dimensionar(PainelTape(WDO_GRID, densidade=d), 400, 500)
    dono = _dimensionar(PainelFootprint(WDO_GRID, densidade=d), 900, 500)
    if nome == "perfil":
        return _dimensionar(PainelPerfil(WDO_GRID, dono.eixo_preco, densidade=d), 200, 500)
    return _dimensionar(PainelDeltaAcumulado(dono.eixo_tempo, densidade=d), 900, 200)


def _assinatura(painel, nome: str) -> tuple:
    """O que a densidade define, do jeito que o desenho vai usar.

    `QFontMetrics` nao compara por igualdade util, entao a assinatura usa o
    que o desenho de fato consulta: altura da linha e avanco de um molde.
    """
    partes: list = [painel.densidade]
    for atributo in DERIVADOS[nome]:
        valor = getattr(painel, atributo)
        if hasattr(valor, "horizontalAdvance"):
            partes.append((valor.height(), valor.horizontalAdvance("5.086,5")))
        else:
            partes.append(valor)
    return tuple(partes)


@pytest.mark.parametrize("nome", sorted(DERIVADOS))
@pytest.mark.parametrize("destino", [tokens.COMPACTA, tokens.CONFORTAVEL])
def test_aplicar_densidade_deixa_o_painel_igual_a_um_recem_construido(
    qapp, nome, destino
):
    """A assercao central, e a que a solucao ingenua reprova.

    Preservar o historico e a metade facil. A metade que decide e esta: depois
    da troca, TODO derivado da densidade tem de valer o que valeria se o
    painel tivesse nascido nessa densidade.
    """
    trocado = _novo(nome, tokens.PADRAO)
    trocado.aplicar_densidade(destino)
    referencia = _novo(nome, destino)
    assert _assinatura(trocado, nome) == _assinatura(referencia, nome)


#: Paineis que MEDEM alguma coisa a partir da densidade. `perfil` e `delta`
#: ficam de fora e isso e um achado, nao um esquecimento: as `QFontMetrics`
#: que eles guardam saem de `fonte_rotulo()`, que nao le a densidade. Para os
#: dois, o atalho ingenuo produziria o mesmo resultado, e afirmar o contrario
#: seria escrever um teste que mede a propria expectativa. O que eles TEM de
#: fazer na troca — invalidar o que ja esta calculado em pixel — e medido em
#: `test_os_paineis_do_eixo_alheio_invalidam_o_que_ja_calcularam`.
MEDEM_DA_DENSIDADE = ("bookmap", "footprint", "tape")


@pytest.mark.parametrize("nome", MEDEM_DA_DENSIDADE)
def test_a_medicao_ingenua_reprova(qapp, nome):
    """Mutacao: trocar o campo sem remedir. O teste de cima TEM de ficar vermelho.

    Sem esta metade, "o painel bate com o recem-construido" seria compativel
    com "a densidade nao muda nada que se meca" — e ai a assercao de cima
    seria decoracao.
    """
    ingenuo = _novo(nome, tokens.PADRAO)
    ingenuo.densidade = tokens.CONFORTAVEL  # o atalho recusado, e so ele
    referencia = _novo(nome, tokens.CONFORTAVEL)
    assert _assinatura(ingenuo, nome) != _assinatura(referencia, nome)


@pytest.mark.parametrize("nome", sorted(DERIVADOS))
def test_aplicar_a_mesma_densidade_e_operacao_nula(qapp, nome):
    painel = _novo(nome, tokens.PADRAO)
    antes = _assinatura(painel, nome)
    painel.aplicar_densidade(tokens.PADRAO)
    assert _assinatura(painel, nome) == antes


# --------------------------------------------------------------------------
# O historico de TELA sobrevive — a queixa original da sonda
# --------------------------------------------------------------------------
def test_o_footprint_mantem_as_colunas_e_as_chaves_do_eixo(qapp):
    painel = _novo("footprint", tokens.PADRAO)
    painel.aplicar(LeituraFootprint(viva=_coluna(T0)))
    painel.aplicar(
        LeituraFootprint(viva=_coluna(T0 + 60), fechada=_coluna(T0, viva=False))
    )
    vivas_antes = [c for c in painel._colunas if c is not None]
    assert len(vivas_antes) >= 2

    painel.aplicar_densidade(tokens.COMPACTA)

    vivas_depois = [c for c in painel._colunas if c is not None]
    assert vivas_depois == vivas_antes[-len(vivas_depois) :]
    # A chave do candle, que e por onde o painel de delta se posiciona,
    # continua no eixo. O INDICE pode andar — `EixoTempo.configurar` ancora as
    # colunas a direita quando cabe mais gente —, e por isso a assercao e
    # sobre a chave, nao sobre a posicao.
    assert painel.eixo_tempo.coluna_do_inicio(T0 + 60) is not None


def test_o_tape_mantem_as_linhas(qapp):
    painel = _novo("tape", tokens.PADRAO)
    itens = tuple(
        ItemTape(T0 + i, BASE + (i % 5), 10, 1 if i % 2 else -1) for i in range(50)
    )
    painel.aplicar(itens)
    antes = list(painel._linhas)
    assert len(antes) == 50
    painel.aplicar_densidade(tokens.CONFORTAVEL)
    assert list(painel._linhas) == antes
    # `_n_visiveis` sai de `altura_linha` e TEM de ter sido refeito: com a
    # densidade confortavel cabe menos linha na mesma altura.
    referencia = _novo("tape", tokens.CONFORTAVEL)
    assert painel._n_visiveis == referencia._n_visiveis


def test_o_bookmap_mantem_o_plano(qapp):
    from fluxopro.core.eventos import BookLevel, BookSnapshot

    painel = _novo("bookmap", tokens.PADRAO)
    for i in range(30):
        painel.aplicar(
            BookSnapshot(
                T0 + i * 1_000_000_000,
                SIMBOLO,
                tuple(BookLevel(BASE - k, 100 + k, 1) for k in range(1, 6)),
                tuple(BookLevel(BASE + k, 100 + k, 1) for k in range(1, 6)),
            ),
            BASE,
            (),
        )
    assert any(painel._plano), "o plano nasceu vazio; o teste nao mede nada"
    colunas_antes = painel._colunas_fechadas
    n_cols_antes = painel.geometria.n_cols
    # A ULTIMA coluna e "agora", e e por ela que o reprojeto ancora a direita.
    ultima_antes = bytes(
        painel._plano[linha * painel._stride + n_cols_antes - 1]
        for linha in range(painel.geometria.n_niveis)
    )

    painel.aplicar_densidade(tokens.COMPACTA)

    # Sem a mudanca de grade o teste nao mediria reprojeto nenhum: a calha
    # estreita da densidade compacta abre coluna, e e ai que `_realocar`
    # decide entre reprojetar e zerar.
    assert painel.geometria.n_cols != n_cols_antes
    ultima_depois = bytes(
        painel._plano[linha * painel._stride + painel.geometria.n_cols - 1]
        for linha in range(painel.geometria.n_niveis)
    )
    assert ultima_depois[: len(ultima_antes)] == ultima_antes[: len(ultima_depois)]
    assert any(ultima_depois), "a coluna de agora foi zerada — o plano recomecou"
    assert painel._colunas_fechadas == colunas_antes


# --------------------------------------------------------------------------
# Ate o pixel — o sintoma que a comparacao de atributo nao pega
# --------------------------------------------------------------------------
@pytest.mark.parametrize("destino", [tokens.COMPACTA, tokens.CONFORTAVEL])
def test_os_rotulos_do_rodape_sobrevivem_a_troca(qapp, destino):
    """A calha e medida contra o mais largo dos rotulos do rodape.

    Medida com a fonte antiga e desenhada com a nova, ela fica estreita e a
    regra F8 descarta o rotulo — a faixa de barras do saldo fica sem nome, e
    nada levanta erro. Por isso a ultima frente e o texto que sai do
    `QPainter`, e nao um numero de atributo.
    """
    painel = _novo("footprint", tokens.PADRAO)
    painel.aplicar(LeituraFootprint(viva=_coluna(T0)))
    painel.aplicar_densidade(destino)
    saiu = " ".join(_textos(painel))
    for rotulo in ROTULOS_RODAPE:
        assert rotulo in saiu, "%r caiu na troca para %s" % (rotulo, destino.nome)


def test_os_paineis_do_eixo_alheio_invalidam_o_que_ja_calcularam(qapp):
    """`PainelPerfil` e `PainelDeltaAcumulado` nao medem nada da densidade —
    guardam RESULTADO em pixel, calculado com a geometria de antes.

    Manter esse cache seria a mesma falha por outro caminho: a barra do perfil
    e o cabecalho do delta continuariam com os pixels da densidade anterior
    ate o dado mudar por conta propria.
    """
    perfil = _novo("perfil", tokens.PADRAO)
    perfil._versao_eixo = 7
    perfil.aplicar_densidade(tokens.COMPACTA)
    assert perfil._versao_eixo == -1

    delta = _novo("delta", tokens.PADRAO)
    delta._chave_cabecalho = ("qualquer",)
    delta._inicios_vistos = (1, 2, 3)
    delta.aplicar_densidade(tokens.COMPACTA)
    assert delta._chave_cabecalho is None
    assert delta._inicios_vistos == ()
