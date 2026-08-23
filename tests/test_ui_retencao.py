"""Retencao da interface INTEIRA, num teste so.

## Por que este arquivo existe

O defeito assinatura deste projeto — *estrutura que cresce com o estado
acumulado e e varrida tarde demais* — foi encontrado em oito arquivos, em
cinco auditorias do nucleo. O criterio de reconhecimento esta no docstring de
`fluxopro/gravacao/gravador.py`: **"qual grandeza limita o `len` disto, e ela
para de crescer enquanto o pregao continua?"**

O nucleo tem varredura para isso: `tests/test_metodologia.py::
test_nenhuma_estrutura_cresce_com_o_numero_de_eventos` instancia os seis
componentes de metodologia, roda 1.000 e 20.000 eventos e exige o mesmo `len`
em toda colecao alcancavel.

A interface **nao tinha**. Tinha prova painel a painel — bookmap, DOM, ponte,
`PainelDenso`, replay, workspace —, cada uma escrita quando alguem lembrou.
Ficavam de fora tape, footprint, perfil, delta, matriz, HUD, metodo, regras e
a trilha. Nove dos catorze.

Isso e exatamente a forma do erro que esta suite pagou para aprender no mesmo
dia em que este arquivo nasceu: a lei do canal ("ressalva em token de
luminancia alta") tinha sido verificada TRES vezes por medicao no retrato e
mesmo assim tinha duas violacoes vivas — `CONFIRMADO` e `INFERIDO` —, porque o
retrato so amostrava regras `IMPRECISO` e os chips delas nunca apareciam na
imagem medida. Quem pegou foi a varredura que olhou todos os tokens, nao a
imagem.

> **Lei verificada caso a caso e sorte. Lei verificada como varredura e
> portao.**

## O que este teste NAO faz

Nao tem lista de paineis digitada. Ele enumera `JanelaFluxo._paineis`, que e o
mesmo dicionario que a janela usa para distribuir o instantaneo. Painel novo
entra na varredura no dia em que entra na janela, sem ninguem lembrar — que e
a unica forma de um portao continuar valendo depois que quem o escreveu sai.

Nao inventa caminho de alimentacao: publica `Trade` e `BookSnapshot` no
barramento de verdade e chama `janela._tick()`, que e o relogio de dados unico.
O que ele mede e o estado que a interface REALMENTE acumula rodando, nao o que
um `aplicar` sintetico deixaria.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from fluxopro.app.config import ConfigOperacao  # noqa: E402
from fluxopro.app.sessao_fluxo import SessaoFluxo  # noqa: E402
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import (  # noqa: E402
    WDO_GRID,
    AgressorSide,
    BookLevel,
    BookSnapshot,
    Trade,
)
from fluxopro.ui.janela import JanelaFluxo  # noqa: E402
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402

SIMBOLO = "WDOV26"
T0 = 1_700_000_000_000_000_000
BASE = 500_000

PASSO_NS = 1_000_000_000
"""Um segundo por evento — e nao um milissegundo, que era o passo original.

Descoberto por MUTACAO, e so por ela. Uma mutacao que enfiava um `set` de
inicios de candle dentro do `EixoTempo` **sobreviveu** a este teste: com 1 ms
por evento, 1.000 e 20.000 eventos cobrem 1 s e 20 s de pregao, e nesse
intervalo nao ha candle novo nenhum. O acumulador indexado por TEMPO crescia
e as duas medicoes davam o mesmo numero.

Com 1 s por evento a varredura passa a cobrir ~17 minutos contra ~5h30 — mais
de um pregao inteiro na ponta grande —, e o eixo do tempo entra no que e
vigiado. Um teste de retencao que nao anda no relogio so vigia as colecoes
indexadas por evento, e deixa de fora justamente as que guardam historico.
"""

N_CORRETORAS = 80
"""Quantas corretoras distintas o passeio apresenta.

`players` mediu ZERO na versao anterior deste arquivo, porque o passeio nao
preenchia `buyer_broker`/`seller_broker` e o ranking nao tinha o que rankear —
o painel entrava na varredura sem ser varrido.

Oitenta e o numero de identidades distintas, e nao "todas diferentes a cada
trade" de proposito: o ranking e indexado POR CORRETORA, e a B3 tem um cadastro
fixo dessa ordem de grandeza. Alimentar identidade nova a cada evento provaria
um crescimento que o mercado nao produz, e reprovaria um dicionario que esta
certo. O que este teste procura e a colecao indexada por TRADE disfarçada de
colecao indexada por corretora — e essa cresce igual com oitenta ou com oito
mil.
"""

N_PEQUENO, N_GRANDE = 1_000, 20_000
"""O mesmo par da varredura do nucleo, e pelo mesmo motivo.

Vinte vezes mais eventos separa O(1) de O(eventos) sem deixar o teste lento.
Um fator de 2 nao separaria O(1) de O(log n) — mas nenhuma colecao desta
camada e logaritmica, e o que se procura aqui e a lista que so cresce.
"""


def _publicar(bus, i: int) -> None:
    """Um trade e um snapshot, com o preco ANDANDO.

    O passeio importa em dois eixos, preco e identidade. Preco fixo nao abre coluna nova no footprint, nao move o
    eixo do bookmap e nao cria nivel novo no perfil — ou seja, um teste de
    retencao com preco parado passa sem exercitar nada do que costuma crescer.
    A faixa de 977 ticks e larga o bastante para obrigar reancoragem, e
    periodica para o resultado nao mudar de rodada.
    """
    preco = BASE + (i % 977) - 488
    ns = T0 + i * PASSO_NS
    bus.publicar(
        Trade(
            ns,
            SIMBOLO,
            preco,
            5 + i % 40,
            AgressorSide.BUY if i % 3 else AgressorSide.SELL,
            f"t{i}",
            buyer_broker="%03d" % (i % N_CORRETORAS),
            seller_broker="%03d" % ((i * 7) % N_CORRETORAS),
        )
    )
    bus.publicar(
        BookSnapshot(
            ns,
            SIMBOLO,
            tuple(BookLevel(preco - k - 1, 100 + k + i % 50, 1) for k in range(8)),
            tuple(BookLevel(preco + k + 1, 90 + k + i % 50, 1) for k in range(8)),
        )
    )


def _campos(objeto):
    """`__dict__` e `__slots__`. Os paineis usam os dois, e olhar so um deles
    devolveria dicionario vazio justamente para as peças mais otimizadas."""
    vistos = set()
    for nome, valor in getattr(objeto, "__dict__", {}).items():
        vistos.add(nome)
        yield nome, valor
    for classe in type(objeto).__mro__:
        for nome in getattr(classe, "__slots__", ()):
            if nome in vistos:
                continue
            vistos.add(nome)
            try:
                yield nome, getattr(objeto, nome)
            except AttributeError:  # pragma: no cover — slot nao preenchido
                pass


def _colecoes_de(objeto, prefixo: str = "") -> dict[str, int]:
    """`len` de toda colecao alcancavel, descendo um nivel em objetos nossos.

    Desce um nivel porque o defeito ja apareceu escondido num campo de um
    campo. Ignora `str`/`bytes`, que tem `len` e nao sao acumuladores.
    """
    tamanhos: dict[str, int] = {}
    for nome, valor in _campos(objeto):
        if nome.startswith("__") or isinstance(valor, (str, bytes)):
            continue
        if isinstance(valor, (list, dict, set, tuple, frozenset)) or hasattr(
            valor, "maxlen"
        ):
            try:
                tamanhos[prefixo + nome] = len(valor)
            except TypeError:  # pragma: no cover — colecao sem len
                pass
        elif type(valor).__module__.startswith("fluxopro.") and not prefixo:
            tamanhos.update(_colecoes_de(valor, f"{nome}."))
    return tamanhos


def _janela(qapp):
    """Janela COM sessao de verdade, e nao a janela nua.

    A primeira versao deste arquivo montava `JanelaFluxo` sem sessao, e ela
    passava — com `perfil._leitura.niveis` e `players._linhas` medindo ZERO nas
    duas pontas. Sao os paineis alimentados pelo retrato da sessao: sem sessao
    eles nao recebem nada, e "nao cresceu" vira verdade por ausencia de dado.

    E o mesmo defeito que esta suite pegou horas antes num teste da matriz que
    media a 262 px, fora da janela de tamanho alcancavel: **passar por estar
    fora do cenario nao e passar.** Aqui a sessao real assina o mesmo
    barramento, entao os catorze paineis veem o pregao inteiro.
    """
    bus = Barramento()
    sessao = SessaoFluxo(bus, ConfigOperacao(symbol=SIMBOLO))
    janela = JanelaFluxo(PonteFluxo(bus), SIMBOLO, WDO_GRID, sessao=sessao)
    janela.resize(1480, 900)
    janela.show()
    return bus, janela


def _medir(qapp, n: int) -> dict[str, dict[str, int]]:
    bus, janela = _janela(qapp)
    try:
        for i in range(1, n + 1):
            _publicar(bus, i)
            # Um `_tick` a cada 20 eventos: a UI desenha a ~60 Hz contra
            # milhares de eventos por segundo, entao drenar a cada evento
            # mediria um regime que nao existe em pregao nenhum. E o regime de
            # LOTE e o que costuma esconder crescimento, porque um `aplicar`
            # que recebe vinte itens de uma vez e onde as listas incham.
            if i % 20 == 0:
                janela._tick()
        janela._tick()
        return {
            chave: _colecoes_de(painel)
            for chave, painel in sorted(janela._paineis.items())
        }
    finally:
        janela.close()


def test_nenhum_painel_da_interface_cresce_com_o_numero_de_eventos(qapp):
    """20x mais eventos, o mesmo `len` em toda colecao de todo painel.

    Se reprovar, a mensagem ja diz o painel, o campo e os dois tamanhos — nao
    ha o que investigar antes de comecar a consertar.
    """
    pequeno = _medir(qapp, N_PEQUENO)
    grande = _medir(qapp, N_GRANDE)

    assert set(pequeno) == set(grande)
    cresceram = {
        f"{painel}.{campo}": (tamanho, grande[painel].get(campo))
        for painel, campos in pequeno.items()
        for campo, tamanho in campos.items()
        if tamanho != grande[painel].get(campo)
    }
    assert not cresceram, (
        f"colecao(oes) crescendo com o numero de eventos ({N_PEQUENO} -> "
        f"{N_GRANDE}):\n"
        + "\n".join(f"  {k}: {a} -> {b}" for k, (a, b) in sorted(cresceram.items()))
    )


def test_a_varredura_enxerga_todos_os_paineis_da_janela(qapp):
    """O portao do portao.

    Uma varredura que enumera menos do que existe da a MESMA sensacao de
    cobertura com menos cobertura — o defeito que este arquivo existe para
    fechar, aplicado a ele mesmo. Aqui se afirma que a medicao alcancou todos
    os paineis registrados na janela, e que nenhum saiu com o dicionario vazio
    por o `__slots__` nao ter sido percorrido.
    """
    medido = _medir(qapp, 40)
    _bus, janela = _janela(qapp)
    try:
        esperados = set(janela._paineis)
    finally:
        janela.close()

    assert set(medido) == esperados
    sem_colecao = sorted(chave for chave, campos in medido.items() if not campos)
    assert not sem_colecao, (
        "paineis que a varredura nao conseguiu inspecionar (nenhuma colecao "
        f"encontrada): {sem_colecao}"
    )

    # E a metade que importa: enumerar nao e exercitar. `players` media zero
    # ate o passeio passar a preencher corretora, e um painel que nao recebe
    # dado "nao cresce" por ausencia, nao por desenho.
    #
    # A excecao sai da CLASSE BASE, e nao de uma lista de nomes: um painel cujo
    # unico estado sao os campos de escrituracao do `PainelDenso` nao tem
    # acumulador proprio para exercitar. Uma lista de nomes envelheceria em
    # silencio — bastaria alguem dar um acumulador ao painel isento para ele
    # sair da varredura para sempre.
    da_base = _campos_da_base()
    inertes = sorted(
        chave
        for chave, campos in medido.items()
        if not any(
            tamanho for nome, tamanho in campos.items() if nome not in da_base
        )
        and any(nome not in da_base for nome in campos)
    )
    assert not inertes, (
        "paineis com acumulador proprio que ficou VAZIO durante a varredura — "
        f"eles nao estao sendo exercitados: {inertes}"
    )


def _campos_da_base() -> frozenset[str]:
    """Os campos de escrituracao do `PainelDenso` (`_sujos`, `_amostras_ms`),
    lidos da propria classe em vez de digitados."""
    from fluxopro.ui.base.painel_denso import PainelDenso

    class _Nu(PainelDenso):
        def desenhar(self, painter, regiao):  # pragma: no cover — nunca desenha
            pass

    nu = _Nu()
    try:
        return frozenset(_colecoes_de(nu))
    finally:
        nu.deleteLater()
