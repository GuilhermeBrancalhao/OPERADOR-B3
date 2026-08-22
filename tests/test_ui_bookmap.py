"""Bookmap: comportamento, trabalho por quadro e RETENÇÃO.

O terceiro grupo é o motivo de este arquivo existir na forma em que está.
Um heatmap de liquidez é, na forma ingênua, uma estrutura indexada por
`(tempo, preço)` que só cresce enquanto o pregão anda — a definição literal
do defeito que este projeto encontrou em **oito arquivos** ao longo de cinco
auditorias (`PROGRESSO.md`; critério no docstring de
`fluxopro/gravacao/gravador.py`).

A auditoria R5 provou algo mais forte que "o defeito não foi pego": com toda
a suíte operando em 1, 3 e 10 eventos, **nenhum teste era capaz de
distinguir a implementação O(nº de eventos) da O(1), nas duas direções**.
Quem consertasse não teria como provar; quem reintroduzisse não seria pego.
O eixo que distingue não é escala bruta, é RETENÇÃO: o `len` de toda coleção
alcançável a partir do estado de instância, confrontado com quantas coisas
VIVAS ela deveria descrever. Uma coleção sadia responde o mesmo número em
1.000 e em 100.000 eventos.

E a contagem desce nos objetos aninhados. O defeito clássico daqui era um
`dict -> list` cujo `len` de topo valia 1 com um milhão de itens dentro;
contar só o topo não o veria.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter, deque
from dataclasses import dataclass

import pytest

from fluxopro.core.eventos import BookLevel, BookSnapshot, WDO_GRID
from fluxopro.ui import tokens
from fluxopro.ui.paineis import bookmap as bm
from fluxopro.ui.paineis.bookmap import (
    GeometriaBookmap,
    PainelBookmap,
    contraste,
    degrau_de,
    faixa_do_degrau,
    codigo_negocio,
    ler_liquidez,
    texto_sobre,
)

_SYMBOL = "WDOV26"
_T0 = 1_700_000_000_000_000_000
_MS = 1_000_000


# =====================================================================
# Instrumentação de retenção — mesma medida de `test_gravacao_retencao.py`
# =====================================================================

_CONTAINERS = (list, tuple, set, frozenset, deque, bytearray, bytes)


def _percorrer(obj, caminho: str, vistos: set[int], saida: list) -> None:
    """Anda pelo grafo de estado carimbando o CAMINHO de cada coleção.

    Caminho e não índice de visita: duas execuções com conteúdos diferentes
    visitam na mesma ordem estrutural mas com contagens diferentes, e uma
    chave numérica faria o diagnóstico apontar para a coleção errada. Com o
    caminho, a mensagem de falha diz `_negocios_coluna{}` e não `#459`.
    """
    if id(obj) in vistos:
        return
    vistos.add(id(obj))
    if isinstance(obj, (dict,) + _CONTAINERS):
        saida.append((caminho, type(obj).__name__, len(obj)))
    if isinstance(obj, dict):
        for valor in obj.values():
            _percorrer(valor, caminho + "{}", vistos, saida)
    elif isinstance(obj, (list, tuple, set, frozenset, deque)):
        for item in obj:
            _percorrer(item, caminho + "[]", vistos, saida)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for campo in dataclasses.fields(obj):
            _percorrer(getattr(obj, campo.name), caminho + "." + campo.name, vistos, saida)


def _colecoes_retidas(obj, ignorar: frozenset[str] = frozenset()) -> Counter:
    """Multiconjunto `(caminho, tipo, len)` de TODA coleção alcançável.

    Multiconjunto e não total: quando o número diverge, o que resolve o
    defeito é saber QUAL estrutura cresceu; um total só diz que alguma
    cresceu. E a descida é recursiva porque o defeito clássico deste projeto
    era um `dict -> list` cujo `len` de topo valia 1 com um milhão dentro.
    """
    saida: list = []
    vistos: set[int] = set()
    for chave, valor in vars(obj).items():
        if chave in ignorar:
            continue
        _percorrer(valor, chave, vistos, saida)
    return Counter(saida)


def _sem_balde(contagem: Counter) -> Counter:
    """Tira da comparação o único item cujo tamanho é legitimamente variável.

    `_negocios_coluna` guarda os preços que negociaram DENTRO do balde de
    tempo corrente: some inteiro a cada fechamento de coluna e é limitado
    pela altura da janela, não pelo número de eventos. Exigir igualdade dele
    seria exigir determinismo de conteúdo, que é outra coisa — e uma
    asserção que mede a coisa errada é a que envelhece mal."""
    return Counter(
        {k: v for k, v in contagem.items() if not k[0].startswith("_negocios_coluna")}
    )


def _elementos_retidos(obj, ignorar: frozenset[str] = frozenset()) -> int:
    return sum(
        tamanho * n for (_c, _t, tamanho), n in _colecoes_retidas(obj, ignorar).items()
    )


# `geometria`, `_bandas` e `_tabela` são geometria e paleta, não retenção de
# dado — mas ficam DENTRO da conta de propósito: se algum dia alguém indexar
# uma delas por preço, é exatamente ali que o defeito voltaria, e a conta
# tem de enxergar.
_IGNORAR = frozenset()


# =====================================================================
# Fixtures
# =====================================================================


@dataclass(frozen=True, slots=True)
class _Negocio:
    """O formato mínimo que `aplicar` consome — o de `ui/ponte.ItemTape`."""

    price: int
    qty: int
    agressor: int


def _livro(centro: int, ts_ns: int, profundidade: int = 10, qty: int = 40) -> BookSnapshot:
    return BookSnapshot(
        timestamp_ns=ts_ns,
        symbol=_SYMBOL,
        bids=tuple(
            BookLevel(price=centro - k, qty=qty + 3 * k, n_orders=1 + k)
            for k in range(profundidade)
        ),
        asks=tuple(
            BookLevel(price=centro + 1 + k, qty=qty + 2 * k, n_orders=1 + k)
            for k in range(profundidade)
        ),
    )


def _painel(qapp=None, largura: int = 900, altura: int = 480, **kwargs) -> PainelBookmap:
    painel = PainelBookmap(WDO_GRID, symbol=_SYMBOL, **kwargs)
    painel.resize(largura, altura)
    # `show()` porque `resizeEvent` — e portanto `ao_redimensionar` — so
    # chega a um widget que o Qt considera realizado. Sem ele o painel fica
    # com geometria zero e todo teste passaria por vacuidade, que e o pior
    # jeito de um teste de geometria ficar verde.
    painel.show()
    return painel


@pytest.fixture()
def painel(qapp):
    return _painel(qapp)


# =====================================================================
# 1. A escada de intensidade é ABSOLUTA
# =====================================================================


def test_degrau_e_monotonico_e_cobre_a_escada_inteira():
    anterior = -1
    for piso in bm.PISOS_LIQUIDEZ:
        degrau = degrau_de(piso)
        assert degrau > anterior
        anterior = degrau
    assert degrau_de(bm.PISOS_LIQUIDEZ[0] - 1) == -1
    assert degrau_de(10**9) == len(bm.PISOS_LIQUIDEZ) - 1


def test_escala_nao_depende_de_nada_alem_da_quantidade():
    """A prova de que não há auto-escala, e ela é estrutural.

    `degrau_de` é função de módulo: não recebe painel, não recebe janela, não
    tem `self`. Uma versão com `autoLevels` precisaria de um segundo
    argumento — e é essa impossibilidade, e não um comentário, que garante
    que a cor de hoje significa o que significava ontem.
    """
    import inspect

    parametros = list(inspect.signature(degrau_de).parameters)
    assert parametros == ["qty", "pisos"]
    # E o mesmo valor dá o mesmo degrau em qualquer contexto.
    assert degrau_de(120) == degrau_de(120) == 6


def test_faixa_do_degrau_encaixa_sem_buraco_nem_sobreposicao():
    for degrau in range(len(bm.PISOS_LIQUIDEZ)):
        piso, teto = faixa_do_degrau(degrau)
        assert degrau_de(piso) == degrau
        if teto is not None:
            assert degrau_de(teto - 1) == degrau
            assert degrau_de(teto) == degrau + 1


def test_codigo_e_leitura_sao_inversos_um_do_outro():
    """O readout não pode contradizer o pixel — ele lê o mesmo byte."""
    for degrau in range(len(bm.PISOS_LIQUIDEZ)):
        leitura = ler_liquidez(bm.codigo_bid(degrau))
        assert (leitura.tipo, leitura.lado, leitura.degrau) == ("bid", 1, degrau)
        leitura = ler_liquidez(bm.codigo_ask(degrau))
        assert (leitura.tipo, leitura.lado, leitura.degrau) == ("ask", -1, degrau)
    assert ler_liquidez(bm.VAZIO).tipo == "vazio"


def test_saldo_do_balde_decide_o_lado_do_negocio():
    """Mesma convenção de `tokens.Paleta.direcional`: zero é neutro, não
    compra. Um balde que recebeu tanto de um lado quanto do outro é volume
    sem direção, e não uma compra marginal."""
    assert codigo_negocio(+5) == bm.NEG_COMPRA
    assert codigo_negocio(-5) == bm.NEG_VENDA
    assert codigo_negocio(0) == bm.NEG_AMBOS


def test_a_celula_diz_as_duas_camadas(painel):
    """A separação em duas camadas existe para isto: um byte só não tinha
    como dizer que ali havia uma parede E que ela foi negociada."""
    livro = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 700, 1),), ())
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    painel.aplicar(
        livro=livro,
        ultimo_preco=5000,
        novos_trades=(_Negocio(5000, 40, -1),),
        agora_ns=_T0 + _MS,
    )
    leitura = painel.leitura_da_celula(
        painel._nivel_do_tick(5000), painel.geometria.n_cols - 1
    )
    assert leitura.tipo == "bid"
    assert leitura.degrau == degrau_de(700)
    assert leitura.negocio == bm.NEG_VENDA
    assert "BID" in leitura.texto and "negócio" in leitura.texto


# =====================================================================
# 2. Comportamento
# =====================================================================


def test_livro_vira_plano_no_degrau_certo(painel):
    livro = _livro(5000, _T0)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    coluna = painel.geometria.n_cols - 1
    for nivel_book in livro.bids:
        linha = painel._nivel_do_tick(nivel_book.price)
        leitura = painel.leitura_da_celula(linha, coluna)
        assert leitura.tipo == "bid"
        assert leitura.degrau == degrau_de(nivel_book.qty)
    for nivel_book in livro.asks:
        linha = painel._nivel_do_tick(nivel_book.price)
        assert painel.leitura_da_celula(linha, coluna).tipo == "ask"


def test_coluna_corrente_mostra_o_livro_e_nao_a_soma_do_balde(painel):
    """Somar contaria a mesma oferta parada várias vezes, e liquidez PARADA
    passaria a parecer liquidez CHEGANDO — o contrário do que o painel diz."""
    magro = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 3, 1),), ())
    for k in range(50):
        painel.aplicar(livro=magro, ultimo_preco=5000, agora_ns=_T0 + k)
    coluna = painel.geometria.n_cols - 1
    linha = painel._nivel_do_tick(5000)
    assert painel.leitura_da_celula(linha, coluna).degrau == degrau_de(3)


def test_o_negocio_sobrevive_a_reescrita_do_livro(painel):
    """O livro é reescrito todo quadro; o negócio do balde não pode piscar e
    sumir no quadro seguinte. Com as duas camadas isso é de graça — a
    reescrita do livro nem toca no plano de cima."""
    livro = _livro(5000, _T0)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    painel.aplicar(
        livro=livro,
        ultimo_preco=5000,
        novos_trades=(_Negocio(5001, 12, +1),),
        agora_ns=_T0 + _MS,
    )
    coluna = painel.geometria.n_cols - 1
    linha = painel._nivel_do_tick(5001)
    assert painel.leitura_da_celula(linha, coluna).negocio == bm.NEG_COMPRA
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0 + 2 * _MS)
    leitura = painel.leitura_da_celula(linha, coluna)
    assert leitura.negocio == bm.NEG_COMPRA
    assert leitura.tipo == "ask", "e a liquidez embaixo continua legivel"


def test_fechar_coluna_esquece_a_mais_antiga_e_desloca_o_resto(painel):
    g = painel.geometria
    marcador = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 700, 1),), ())
    painel.aplicar(livro=marcador, ultimo_preco=5000, agora_ns=_T0)
    linha = painel._nivel_do_tick(5000)
    ultima = g.n_cols - 1
    assert painel.leitura_da_celula(linha, ultima).degrau == degrau_de(700)

    vazio = BookSnapshot(_T0, _SYMBOL, (), ())
    ts = _T0
    for _ in range(3):
        ts += painel.intervalo_coluna_ns
        painel.aplicar(livro=vazio, ultimo_preco=5000, agora_ns=ts)
    assert painel.leitura_da_celula(linha, ultima - 3).degrau == degrau_de(700)

    for _ in range(g.n_cols + 2):
        ts += painel.intervalo_coluna_ns
        painel.aplicar(livro=vazio, ultimo_preco=5000, agora_ns=ts)
    assert all(
        painel.leitura_da_celula(linha, c).tipo == "vazio"
        and painel.leitura_da_celula(linha, c).negocio == bm.NEG_VAZIO
        for c in range(g.n_cols)
    )


def test_pico_da_janela_desce_quando_a_parede_sai_da_janela(painel):
    """A catraca é o defeito 4 do HUD — o mais teimoso deles. Um pico que só
    sobe compara o quadro de agora com a lembrança de vinte minutos atrás."""
    parede = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 4_000, 1),), ())
    painel.aplicar(livro=parede, ultimo_preco=5000, agora_ns=_T0)
    assert painel.pico_janela[0] == 4_000

    magro = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 7, 1),), ())
    ts = _T0
    for _ in range(painel.geometria.n_cols + 1):
        ts += painel.intervalo_coluna_ns
        painel.aplicar(livro=magro, ultimo_preco=5000, agora_ns=ts)
    assert painel.pico_janela[0] == 7


def test_pico_nao_anuncia_parede_fora_do_eixo_de_preco(painel):
    """Readout que cita o que nao esta desenhado e a falha do readout que
    contradiz o pixel, com o sinal trocado. O cabecalho chegou a anunciar
    `PICO 2.310 @ 5.110,0` num painel cujo eixo ia ate 5.038 — verdadeiro, e
    inutil, porque o leitor nao tinha como achar a parede na tela."""
    fora = painel.geometria.n_niveis * 3
    livro = BookSnapshot(
        _T0,
        _SYMBOL,
        (BookLevel(5000, 30, 1), BookLevel(5000 - fora, 9_000, 1)),
        (BookLevel(5001, 30, 1),),
    )
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    assert painel.pico_janela[0] == 30


def test_pico_desce_quando_o_eixo_de_preco_deixa_a_parede_para_tras(painel):
    parede = BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 4_000, 1),), ())
    painel.aplicar(livro=parede, ultimo_preco=5000, agora_ns=_T0)
    assert painel.pico_janela[0] == 4_000
    # O preco foge para longe: a parede continua dentro da janela de TEMPO e
    # sai da janela de PRECO. As duas mandam.
    longe = 5000 + 4 * painel.geometria.n_niveis
    magro = BookSnapshot(_T0, _SYMBOL, (BookLevel(longe, 11, 1),), ())
    painel.aplicar(livro=magro, ultimo_preco=longe, agora_ns=_T0 + _MS)
    assert painel.pico_janela[0] == 11


def test_trilha_do_meio_e_linha_conectada_e_nao_tracinhos(painel):
    """A primeira versao desenhava um segmento horizontal por coluna e
    deixava os saltos verticais em aberto. Com o meio andando alguns ticks
    entre baldes, o retrato mostrou pontilhado espalhado em vez de linha — e
    uma referencia que o olho nao consegue seguir nao serve de referencia,
    que e o unico trabalho dela no modo sem cor."""
    ts = _T0
    for preco in (5000, 5010):
        painel.aplicar(livro=_livro(preco, ts), ultimo_preco=preco, agora_ns=ts)
        ts += painel.intervalo_coluna_ns
    painel.aplicar(livro=_livro(5010, ts), ultimo_preco=5010, agora_ns=ts)

    g = painel.geometria
    imagem = _imagem_do_quadro(painel)
    coluna = g.n_cols - 2
    y_a = g.y_do_meio(painel._topo_ticks, painel._mid[coluna - 1])
    y_b = g.y_do_meio(painel._topo_ticks, painel._mid[coluna])
    assert abs(y_a - y_b) > g.altura_nivel, "o teste precisa de um DEGRAU de verdade"

    branco = tokens.TEXT_PRIMARY.rgb() & 0xFFFFFF
    x = g.x_da_coluna(coluna)
    encontrados = sum(
        1
        for y in range(min(y_a, y_b), max(y_a, y_b) + 1)
        if imagem.pixel(x, y) & 0xFFFFFF == branco
    )
    assert encontrados >= abs(y_a - y_b) - 1, (
        "o salto vertical entre duas colunas tem de estar desenhado: "
        "%d de %d pixels" % (encontrados, abs(y_a - y_b) + 1)
    )


def test_eixo_de_preco_anda_por_rolagem_e_leva_a_historia_junto(painel):
    livro = _livro(5000, _T0)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    linha_antes = painel._nivel_do_tick(5000)
    leitura_antes = painel.leitura_da_celula(linha_antes, painel.geometria.n_cols - 1)

    salto = painel.geometria.n_niveis  # bem além da zona de conforto
    painel.aplicar(livro=None, ultimo_preco=5000 + salto // 3, agora_ns=_T0 + _MS)
    linha_depois = painel._nivel_do_tick(5000)
    assert linha_depois != linha_antes
    # O dado antigo continua no MESMO preço, em outra linha: o eixo andou, o
    # conteúdo não foi reinterpretado.
    assert (
        painel.leitura_da_celula(linha_depois, painel.geometria.n_cols - 1)
        == leitura_antes
    )


def test_preco_fora_da_janela_e_descartado_sem_levantar(painel):
    """Um book com 200 níveis numa janela de 100 é normal em pregão; derrubar
    o painel por isso seria trocar um pixel a menos por uma tela preta."""
    fundo = BookSnapshot(
        _T0, _SYMBOL, (BookLevel(5000 - 10_000, 500, 1),), (BookLevel(5000 + 10_000, 500, 1),)
    )
    painel.aplicar(livro=fundo, ultimo_preco=5000, agora_ns=_T0)
    assert painel.pico_janela[0] == 0


def test_lane_de_agressao_e_proporcao_e_nao_volume(painel):
    painel.aplicar(livro=_livro(5000, _T0), ultimo_preco=5000, agora_ns=_T0)
    painel.aplicar(
        novos_trades=(_Negocio(5001, 30, +1), _Negocio(4999, 10, -1)),
        ultimo_preco=5000,
        agora_ns=_T0 + _MS,
    )
    coluna = painel.geometria.n_cols - 1
    assert (painel._neg_compra[coluna], painel._neg_venda[coluna]) == (30, 10)
    # Multiplicar o volume por mil não muda a proporção — que é a prova de
    # que a lane não carrega grandeza sem teto na geometria.
    outro = _painel(None)
    outro.aplicar(livro=_livro(5000, _T0), ultimo_preco=5000, agora_ns=_T0)
    outro.aplicar(
        novos_trades=(_Negocio(5001, 30_000, +1), _Negocio(4999, 10_000, -1)),
        ultimo_preco=5000,
        agora_ns=_T0 + _MS,
    )
    c2 = outro.geometria.n_cols - 1
    razao_a = painel._neg_compra[coluna] / (
        painel._neg_compra[coluna] + painel._neg_venda[coluna]
    )
    razao_b = outro._neg_compra[c2] / (outro._neg_compra[c2] + outro._neg_venda[c2])
    assert razao_a == pytest.approx(razao_b)


# =====================================================================
# 3. Geometria compartilhada — desenho e teste leem o MESMO marco
# =====================================================================


def _imagem_do_quadro(painel):
    painel._quadro()
    assert painel._backing is not None
    return painel._backing.toImage()


def test_o_pixel_da_celula_esta_onde_a_geometria_diz(painel):
    """Prova de marco compartilhado: se `desenhar` usasse outra aritmética de
    posição, a cor amostrada no centro que `GeometriaBookmap` aponta não
    seria a do degrau. É o que impede o teste de ser teatro (§3)."""
    # LONGE da trilha do meio de propósito: ela é desenhada por cima, com
    # contorno dos dois lados, e amostrar um nível colado no topo do book
    # mediria a trilha em vez da rampa.
    livro = _livro(5000, _T0, profundidade=10, qty=40)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    imagem = _imagem_do_quadro(painel)

    nivel_book = livro.bids[6]
    nivel = painel._nivel_do_tick(nivel_book.price)
    coluna = painel.geometria.n_cols - 1
    centro = painel.geometria.rect_celula(nivel, coluna).center()
    esperado = tokens.RAMPA_COMPRA[degrau_de(nivel_book.qty)].rgb()
    assert imagem.pixel(centro.x(), centro.y()) & 0xFFFFFF == esperado & 0xFFFFFF


def test_a_camada_de_negocio_pinta_por_cima_sem_apagar_o_dado(painel):
    """O negócio ganha o PIXEL — o que aconteceu vale mais que o que estava
    ofertado — mas não apaga a liquidez do plano, e é por isso que
    `leitura_da_celula` continua sabendo das duas."""
    livro = _livro(5000, _T0, profundidade=10, qty=40)
    alvo = livro.bids[6]
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    painel.aplicar(
        livro=livro,
        ultimo_preco=5000,
        novos_trades=(_Negocio(alvo.price, 9, +1),),
        agora_ns=_T0 + _MS,
    )
    imagem = _imagem_do_quadro(painel)
    nivel = painel._nivel_do_tick(alvo.price)
    coluna = painel.geometria.n_cols - 1
    centro = painel.geometria.rect_celula(nivel, coluna).center()
    assert imagem.pixel(centro.x(), centro.y()) & 0xFFFFFF == tokens.BUY.rgb() & 0xFFFFFF
    assert painel.leitura_da_celula(nivel, coluna).degrau == degrau_de(alvo.qty)


def test_celula_vazia_desenha_o_fundo_de_painel(painel):
    painel.aplicar(
        livro=BookSnapshot(_T0, _SYMBOL, (BookLevel(5000, 250, 1),), ()),
        ultimo_preco=5000,
        agora_ns=_T0,
    )
    imagem = _imagem_do_quadro(painel)
    nivel = painel._nivel_do_tick(5000)
    centro = painel.geometria.rect_celula(max(0, nivel - 8), painel.geometria.n_cols - 1).center()
    assert imagem.pixel(centro.x(), centro.y()) & 0xFFFFFF == tokens.BG_SURFACE.rgb() & 0xFFFFFF


def test_a_trilha_do_meio_tem_contorno_dos_dois_lados(painel):
    """No modo sem cor a marca de negócio também é `TEXT_PRIMARY`: com
    contorno de um lado só, num trecho de negócio denso sobrava meia linha —
    e meia linha não é uma referência que o olho siga. É justamente no modo
    sem cor que a trilha é o ÚNICO portador do lado."""
    livro = _livro(5000, _T0)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    imagem = _imagem_do_quadro(painel)
    g = painel.geometria
    x = g.x_da_coluna(g.n_cols - 1) + 1
    y = g.y_do_meio(painel._topo_ticks, painel._mid[g.n_cols - 1])
    escuro = tokens.BG_BASE.rgb() & 0xFFFFFF
    assert imagem.pixel(x, y) & 0xFFFFFF == tokens.TEXT_PRIMARY.rgb() & 0xFFFFFF
    assert imagem.pixel(x, y - 1) & 0xFFFFFF == escuro
    assert imagem.pixel(x, y + 1) & 0xFFFFFF == escuro


def test_colunas_em_e_o_inverso_de_x_da_coluna():
    g = GeometriaBookmap(0, 24, 40, 30, 4, 4)
    for coluna in range(g.n_cols):
        assert g.coluna_em(g.x_da_coluna(coluna)) == coluna
        assert g.coluna_em(g.x_da_coluna(coluna) + g.largura_coluna - 1) == coluna
        primeira, ultima = g.colunas_em(g.rect_coluna(coluna))
        assert (primeira, ultima) == (coluna, coluna)
    assert g.coluna_em(g.x_da_coluna(g.n_cols)) is None
    assert g.nivel_em(g.y0 - 1) is None


# =====================================================================
# 4. Modo sem cor — a posição carrega o lado
# =====================================================================


def test_sem_cor_a_rampa_colapsa_mas_a_intensidade_sobrevive(qapp):
    painel = _painel(qapp, paleta=tokens.PALETA_SEM_COR)
    assert painel.rampa_bid is painel.rampa_ask
    # A informação do heatmap é a INTENSIDADE, e ela continua monotônica e
    # distinguível degrau a degrau. O que o modo sem cor tira é o LADO.
    luminancias = [bm._luminancia(cor) for cor in painel.rampa_bid]
    assert luminancias == sorted(luminancias)
    assert luminancias[-1] > luminancias[0] * 1.5


def test_sem_cor_bid_fica_abaixo_e_ask_acima_da_trilha_do_meio(qapp):
    """O lado migra da cor para a POSIÇÃO, e a posição só é portador se a
    referência estiver desenhada. Aqui a referência é `y_do_meio` — a mesma
    função que `_desenhar_meio` usa para traçar a linha."""
    painel = _painel(qapp, paleta=tokens.PALETA_SEM_COR)
    livro = _livro(5000, _T0)
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)

    coluna = painel.geometria.n_cols - 1
    meio = painel.geometria.nivel_fracionario_do_meio(
        painel._topo_ticks, painel._mid[coluna]
    )
    vistos = 0
    for nivel in range(painel.geometria.n_niveis):
        leitura = painel.leitura_da_celula(nivel, coluna)
        if leitura.tipo == "bid":
            assert nivel > meio, "bid tem de ficar ABAIXO da trilha do meio"
            vistos += 1
        elif leitura.tipo == "ask":
            assert nivel < meio, "ask tem de ficar ACIMA da trilha do meio"
            vistos += 1
    assert vistos == len(livro.bids) + len(livro.asks)


def test_trilha_do_meio_cai_entre_o_melhor_bid_e_o_melhor_ask(painel):
    """Spread de um tick é o caso mais comum e o mais fácil de errar: o meio
    arredondado para tick encostaria num dos dois lados."""
    livro = BookSnapshot(
        _T0, _SYMBOL, (BookLevel(5000, 100, 1),), (BookLevel(5001, 100, 1),)
    )
    painel.aplicar(livro=livro, ultimo_preco=5000, agora_ns=_T0)
    g = painel.geometria
    coluna = g.n_cols - 1
    y_meio = g.y_do_meio(painel._topo_ticks, painel._mid[coluna])
    y_bid = g.rect_celula(painel._nivel_do_tick(5000), coluna).center().y()
    y_ask = g.rect_celula(painel._nivel_do_tick(5001), coluna).center().y()
    assert y_ask < y_meio <= y_bid


def test_toda_ancora_da_escada_le_sobre_o_proprio_degrau(painel):
    """A escala carimbada não pode virar texto escuro sobre fundo escuro no
    primeiro degrau (8% de alfa) nem claro sobre claro no último."""
    for cor in painel.rampa_bid + painel.rampa_ask + tokens.RAMPA_NEUTRA:
        assert contraste(texto_sobre(cor), cor) >= 4.5


# =====================================================================
# 5. Trabalho por quadro — a região suja
# =====================================================================


def test_quadro_sem_novidade_nao_abre_painter(painel):
    painel.aplicar(livro=_livro(5000, _T0), ultimo_preco=5000, agora_ns=_T0)
    painel._quadro()
    painel.zerar_medicao()
    for _ in range(10):
        painel._quadro()
    assert painel.quadros_desenhados == 0
    assert painel.quadros_vazios == 10


def test_um_quadro_em_regime_suja_uma_coluna_e_nao_a_tela(painel):
    painel.aplicar(livro=_livro(5000, _T0), ultimo_preco=5000, agora_ns=_T0)
    painel._quadro()  # consome o "tudo sujo" inicial
    painel.aplicar(livro=_livro(5000, _T0 + _MS), ultimo_preco=5000, agora_ns=_T0 + _MS)
    assert not painel._tudo_sujo
    largura_suja = sum(r.width() for r in painel._sujos)
    assert largura_suja <= 4 * painel.geometria.largura_coluna
    assert largura_suja < painel.width() // 4


def test_fechar_coluna_rola_o_backing_em_vez_de_redesenhar(painel):
    painel.aplicar(livro=_livro(5000, _T0), ultimo_preco=5000, agora_ns=_T0)
    painel._quadro()
    painel.aplicar(
        livro=_livro(5000, _T0 + painel.intervalo_coluna_ns),
        ultimo_preco=5000,
        agora_ns=_T0 + painel.intervalo_coluna_ns,
    )
    assert not painel._tudo_sujo, "fechar balde não pode custar a tela inteira"


# =====================================================================
# 6. RETENÇÃO — o motivo deste arquivo
# =====================================================================


def _rodar(painel, n_eventos: int, semente: int = 7) -> None:
    """Entrega `n_eventos` negócios e o book correspondente, com o preço
    andando de verdade (para exercitar a rolagem vertical) e o relógio
    andando de verdade (para exercitar o fechamento de colunas)."""
    sorteio = random.Random(semente)
    preco = 5000
    ts = _T0
    por_quadro = 100
    for quadro in range(max(1, n_eventos // por_quadro)):
        preco += sorteio.choice((-2, -1, 0, 1, 2))
        ts += 100 * _MS
        trades = tuple(
            _Negocio(
                preco + sorteio.randint(-3, 3),
                sorteio.randint(1, 400),
                sorteio.choice((1, -1, 0)),
            )
            for _ in range(por_quadro)
        )
        painel.aplicar(
            livro=_livro(preco, ts, profundidade=12, qty=sorteio.randint(1, 900)),
            ultimo_preco=preco,
            novos_trades=trades,
            agora_ns=ts,
        )


def test_retencao_nao_cresce_com_numero_de_eventos(qapp):
    pequeno = _painel(qapp, 640, 360)
    grande = _painel(qapp, 640, 360)
    _rodar(pequeno, 1_000)
    _rodar(grande, 100_000)

    # A janela inteira tem de ter virado mais de uma vez, senão o teste
    # provaria só que nada acontece — que é como um teste de retenção fica
    # verde sem medir nada.
    assert grande.colunas_fechadas > grande.geometria.n_cols
    assert grande.colunas_fechadas > pequeno.colunas_fechadas + 50
    magro = _colecoes_retidas(pequeno, _IGNORAR)
    gordo = _colecoes_retidas(grande, _IGNORAR)
    # `_negocios_coluna` é a única que varia de tamanho entre as duas
    # execuções, e ela é limitada por ALTURA — quantos preços distintos
    # negociaram dentro do balde de meio segundo corrente. Sai da comparação
    # de igualdade e entra numa asserção de TETO logo abaixo, que é a forma
    # honesta de afirmar "limitada pela geometria" para uma coleção que
    # legitimamente não tem tamanho fixo.
    magro, gordo = _sem_balde(magro), _sem_balde(gordo)
    assert magro == gordo, (
        "alguma coleção cresceu com o número de eventos: "
        + repr(((magro - gordo) + (gordo - magro)).most_common())
    )
    for painel_medido in (pequeno, grande):
        assert len(painel_medido._negocios_coluna) <= painel_medido.geometria.n_niveis


def test_nenhuma_colecao_e_indexada_por_preco_ou_por_tempo(qapp):
    """A conta explícita: cada coleção do painel, e a grandeza que a limita.

    Este é o teste que a auditoria R5 provou que faltava — o que distingue a
    versão O(nº de eventos) da O(1) NAS DUAS DIREÇÕES. Ele não mede um
    total: ele nomeia cada estrutura e afirma o valor exato que a geometria
    da janela impõe. Uma estrutura nova que ninguém previu quebra a soma.
    """
    painel = _painel(qapp, 640, 360)
    _rodar(painel, 40_000)
    g = painel.geometria

    assert len(painel._plano) == painel._stride * g.n_niveis
    assert len(painel._plano_neg) == painel._stride * g.n_niveis
    for vetor in (
        painel._mid,
        painel._pico_qty,
        painel._pico_ticks,
        painel._neg_compra,
        painel._neg_venda,
    ):
        assert len(vetor) == g.n_cols
    assert len(painel._negocios_coluna) <= g.n_niveis
    assert len(painel._bandas) == bm.N_BANDAS
    assert len(painel._tabela) == bm.N_TABELA

    # E o fecho: a soma de TODAS as coleções alcançáveis é exatamente a soma
    # das previstas acima. Se alguém acrescentar um `dict` novo indexado por
    # preço, esta linha é a que acusa — inclusive se ele estiver aninhado
    # dentro de outro, que é a forma em que o defeito já apareceu.
    previsto = (
        2 * painel._stride * g.n_niveis  # _plano + _plano_neg
        + 5 * g.n_cols  # os cinco vetores por coluna
        + len(painel._negocios_coluna)
        + bm.N_BANDAS
        + bm.N_TABELA
        + len(painel.pisos)
        + len(painel.rampa_bid)
        + len(painel.rampa_ask)
        + bm.N_TABELA_NEG
        + len(tokens.FAMILIAS_NUMERO) * 0  # nada de tipografia é retido aqui
    )
    assert _elementos_retidos(painel, _IGNORAR) == previsto


def test_encolher_a_janela_descarta_em_vez_de_guardar(qapp):
    painel = _painel(qapp, 900, 480)
    _rodar(painel, 5_000)
    antes = _elementos_retidos(painel, _IGNORAR)
    painel.resize(400, 240)
    depois = _elementos_retidos(painel, _IGNORAR)
    assert depois < antes, (
        "guardar o excedente 'para quando a janela crescer' é a mesma "
        "estrutura que cresce com o passado, com nome de cache"
    )
    assert len(painel._mid) == painel.geometria.n_cols
