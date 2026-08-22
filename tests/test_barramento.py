from __future__ import annotations

from dataclasses import dataclass

import pytest

from fluxopro.core.barramento import Barramento


@dataclass(frozen=True, slots=True)
class _EventoTeste:
    valor: int


@dataclass(frozen=True, slots=True)
class _OutroEvento:
    valor: int


def test_ordem_por_prioridade_e_inscricao() -> None:
    barramento = Barramento()
    chamadas: list[str] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append("baixa_1"), prioridade=10)
    barramento.assinar(_EventoTeste, lambda e: chamadas.append("alta"), prioridade=0)
    barramento.assinar(_EventoTeste, lambda e: chamadas.append("baixa_2"), prioridade=10)

    barramento.publicar(_EventoTeste(valor=1))

    assert chamadas == ["alta", "baixa_1", "baixa_2"]


def test_apenas_assinantes_do_tipo_exato_sao_chamados() -> None:
    barramento = Barramento()
    chamadas: list[int] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append(e.valor))
    barramento.publicar(_OutroEvento(valor=99))

    assert chamadas == []


def test_publicar_sem_assinantes_nao_falha() -> None:
    barramento = Barramento()
    barramento.publicar(_EventoTeste(valor=1))


def test_mesma_prioridade_multiplos_tipos_independentes() -> None:
    barramento = Barramento()
    chamadas: list[str] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append(f"teste:{e.valor}"))
    barramento.assinar(_OutroEvento, lambda e: chamadas.append(f"outro:{e.valor}"))

    barramento.publicar(_EventoTeste(valor=1))
    barramento.publicar(_OutroEvento(valor=2))

    assert chamadas == ["teste:1", "outro:2"]


# ---------------------------------------------------------------------------
# Política 1 — reentrância: `publicar` entrega sobre um INSTANTÂNEO
#
# `criticas/nucleo_r5.md` B01: aplicar a CORREÇÃO de reentrância (iterar uma
# cópia) deixava os 574 testes verdes, ou seja, a política não estava decidida
# em direção nenhuma. Os dois testes abaixo decidem: assinar/desassinar de
# dentro de um callback afeta o PRÓXIMO evento, nunca o corrente.
# ---------------------------------------------------------------------------


def test_assinar_durante_publicar_nao_afeta_o_evento_corrente() -> None:
    """O assinante novo não estava inscrito quando o evento foi publicado.

    A prioridade 99 é escolhida de propósito: numa lista mutada durante a
    iteração o novo entraria DEPOIS do cursor do `for` e seria visitado — é
    o caso em que a ausência de política se manifesta como "às vezes sim".
    """
    barramento = Barramento()
    chamadas: list[str] = []

    def tardio(_evento) -> None:
        chamadas.append("tardio")

    def primeiro(_evento) -> None:
        chamadas.append("primeiro")
        barramento.assinar(_EventoTeste, tardio, prioridade=99)

    barramento.assinar(_EventoTeste, primeiro, prioridade=0)

    barramento.publicar(_EventoTeste(valor=1))
    assert chamadas == ["primeiro"], "assinante inscrito DURANTE a entrega recebeu o evento corrente"

    barramento.publicar(_EventoTeste(valor=2))
    assert chamadas == ["primeiro", "primeiro", "tardio"]


def test_desassinar_durante_publicar_nao_tira_do_evento_corrente() -> None:
    """A outra metade da mesma política. Sem instantâneo, remover um elemento
    à frente do cursor faria o `for` PULAR o assinante seguinte — perda
    silenciosa de entrega, o modo de falha mais caro deste barramento."""
    barramento = Barramento()
    chamadas: list[str] = []

    def segundo(_evento) -> None:
        chamadas.append("segundo")

    def terceiro(_evento) -> None:
        chamadas.append("terceiro")

    ja_removeu: list[bool] = []

    def primeiro(_evento) -> None:
        if not ja_removeu:
            assert barramento.desassinar(_EventoTeste, segundo)
            ja_removeu.append(True)
        chamadas.append("primeiro")

    barramento.assinar(_EventoTeste, primeiro, prioridade=0)
    barramento.assinar(_EventoTeste, segundo, prioridade=1)
    barramento.assinar(_EventoTeste, terceiro, prioridade=2)

    barramento.publicar(_EventoTeste(valor=1))
    assert chamadas == ["primeiro", "segundo", "terceiro"]

    chamadas.clear()
    barramento.publicar(_EventoTeste(valor=2))
    assert chamadas == ["primeiro", "terceiro"]


# ---------------------------------------------------------------------------
# Política 2 — exceção de assinante PROPAGA
#
# `criticas/nucleo_r5.md` B02: engolir toda exceção deixava a suíte verde.
# Num barramento em que o Gravador divide a publicação com a saída, isso é a
# política que decide se um erro de exibição some com o pregão gravado.
# ---------------------------------------------------------------------------


def test_excecao_de_assinante_propaga_para_quem_publicou() -> None:
    barramento = Barramento()

    def explode(_evento) -> None:
        raise RuntimeError("assinante quebrado")

    barramento.assinar(_EventoTeste, explode)

    with pytest.raises(RuntimeError, match="assinante quebrado"):
        barramento.publicar(_EventoTeste(valor=1))


def test_excecao_de_assinante_interrompe_a_cadeia_e_isso_e_visivel() -> None:
    """A consequência da política, dita por inteiro: os assinantes seguintes
    NÃO rodam. Um `except: pass` em `publicar` deixaria `depois` rodar e
    ninguém saberia que `meio` falhou — que é exatamente o cenário em que
    metade da cadeia processa o evento e a outra metade não."""
    barramento = Barramento()
    chamadas: list[str] = []

    def antes(_evento) -> None:
        chamadas.append("antes")

    def meio(_evento) -> None:
        raise RuntimeError("quebrou no meio")

    def depois(_evento) -> None:
        chamadas.append("depois")

    barramento.assinar(_EventoTeste, antes, prioridade=0)
    barramento.assinar(_EventoTeste, meio, prioridade=1)
    barramento.assinar(_EventoTeste, depois, prioridade=2)

    with pytest.raises(RuntimeError):
        barramento.publicar(_EventoTeste(valor=1))

    assert chamadas == ["antes"], "a cadeia seguiu depois da excecao (excecao engolida)"


# ---------------------------------------------------------------------------
# Política 3 — `desassinar` existe; é ele que fecha a virada de sessão
# (`criticas/nucleo_r5.md` §C.2: 199 candles do dia 1 sobrevivendo ao dia 2)
# ---------------------------------------------------------------------------


def test_desassinar_para_de_entregar_e_diz_se_removeu() -> None:
    barramento = Barramento()
    chamadas: list[_EventoTeste] = []

    barramento.assinar(_EventoTeste, chamadas.append)
    barramento.publicar(_EventoTeste(valor=1))

    assert barramento.desassinar(_EventoTeste, chamadas.append) is True
    barramento.publicar(_EventoTeste(valor=2))
    assert [e.valor for e in chamadas] == [1]

    # segunda remoção não tem o que remover, e diz isso em vez de fingir
    assert barramento.desassinar(_EventoTeste, chamadas.append) is False
    assert barramento.desassinar(_OutroEvento, chamadas.append) is False


def test_desassinar_de_callback_que_nao_esta_inscrito_devolve_False() -> None:
    """O caso que os dois `False` do teste acima NÃO alcançam.

    Achado por mutação (`MB4` desta onda, sobrevivente do primeiro lote): lá,
    a primeira chamada cai em "tipo ficou sem assinante nenhum" e a segunda em
    "tipo nunca teve assinante" — as duas resolvidas pela guarda `if not
    atuais` **antes** da comparação. O ramo que decide de verdade — o tipo tem
    assinantes, mas nenhum é este callback — não era exercitado, e trocar o
    seu `return False` por `return True` deixava a suíte inteira verde.

    Um `desassinar` que mente ao dizer que removeu é pior que um que falha:
    `SessaoFluxo.iniciar_nova_sessao` confere o retorno para não seguir com um
    componente órfão ainda assinado.
    """
    barramento = Barramento()
    outro: list[int] = []
    nunca_inscrito: list[int] = []

    barramento.assinar(_EventoTeste, outro.append)

    # o tipo TEM assinante (`outro.append`), mas não este:
    assert barramento.desassinar(_EventoTeste, nunca_inscrito.append) is False

    # e quem estava inscrito continua inscrito — a chamada falha sem estragar
    barramento.publicar(_EventoTeste(valor=5))
    assert [e.valor for e in outro] == [5]
    assert nunca_inscrito == []


def test_desassinar_objeto_de_dono_desconhecido_devolve_zero() -> None:
    """A mesma pergunta para a variante por objeto: um dono que nunca assinou
    tem de devolver 0, mesmo com o barramento cheio de outros assinantes."""

    class Componente:
        def ao_teste(self, _e) -> None: ...

    inscrito, estranho = Componente(), Componente()
    barramento = Barramento()
    barramento.assinar(_EventoTeste, inscrito.ao_teste)

    assert barramento.desassinar_objeto(estranho) == 0
    assert len(barramento._assinantes[_EventoTeste]) == 1


def test_desassinar_compara_por_igualdade_e_nao_por_identidade() -> None:
    """`obj.metodo` cria um objeto novo a cada acesso. Comparar por `is`
    faria `desassinar` devolver False em silêncio para o caso mais comum —
    desligar um componente que se inscreveu no próprio construtor."""

    class Componente:
        def __init__(self) -> None:
            self.vistos: list[int] = []

        def ao_evento(self, evento: _EventoTeste) -> None:
            self.vistos.append(evento.valor)

    comp = Componente()
    barramento = Barramento()
    barramento.assinar(_EventoTeste, comp.ao_evento)

    assert comp.ao_evento is not comp.ao_evento  # a premissa do teste
    assert barramento.desassinar(_EventoTeste, comp.ao_evento) is True

    barramento.publicar(_EventoTeste(valor=7))
    assert comp.vistos == []


def test_desassinar_objeto_remove_todas_as_assinaturas_do_dono() -> None:
    """A operação que "trocar a instância" precisa: quem recria um componente
    não conhece os nomes dos métodos privados que ele registrou sozinho."""

    class Componente:
        def __init__(self) -> None:
            self.vistos: list[str] = []

        def ao_teste(self, _e) -> None:
            self.vistos.append("teste")

        def ao_outro(self, _e) -> None:
            self.vistos.append("outro")

    velho, novo = Componente(), Componente()
    barramento = Barramento()
    for comp in (velho, novo):
        barramento.assinar(_EventoTeste, comp.ao_teste)
        barramento.assinar(_OutroEvento, comp.ao_outro)

    assert barramento.desassinar_objeto(velho) == 2
    assert barramento.desassinar_objeto(velho) == 0

    barramento.publicar(_EventoTeste(valor=1))
    barramento.publicar(_OutroEvento(valor=2))

    assert velho.vistos == []
    assert novo.vistos == ["teste", "outro"]


def test_desassinar_objeto_nao_confunde_instancias_da_mesma_classe() -> None:
    """Remoção por `__self__ is dono`, não por nome de método: duas
    instâncias da mesma classe registram callbacks com o mesmo `__name__` —
    e é exatamente esse o caso da virada de sessão (a instância velha e a
    nova do mesmo componente convivem por um instante)."""

    class Componente:
        def __init__(self) -> None:
            self.n = 0

        def ao_teste(self, _e) -> None:
            self.n += 1

    a, b = Componente(), Componente()
    barramento = Barramento()
    barramento.assinar(_EventoTeste, a.ao_teste)
    barramento.assinar(_EventoTeste, b.ao_teste)

    barramento.desassinar_objeto(a)
    barramento.publicar(_EventoTeste(valor=1))

    assert (a.n, b.n) == (0, 1)


def test_virada_repetida_nao_faz_o_barramento_crescer() -> None:
    """Critério de crescimento aplicado a `_assinantes`.

    "Qual grandeza limita o `len` disto?" — assinaturas vivas. O único jeito
    de a resposta virar "número de viradas de sessão" é recriar um componente
    que se inscreve sozinho SEM desassinar o antigo, que é o que a ausência
    de `desassinar` obrigava. 200 viradas têm de deixar o barramento do mesmo
    tamanho que 0 viradas — e não é só memória: cada instância órfã continua
    recebendo, e a contagem dobra a cada virada.
    """

    class Componente:
        def __init__(self, barramento: Barramento) -> None:
            self.n = 0
            barramento.assinar(_EventoTeste, self._ao_evento)

        def _ao_evento(self, _e) -> None:
            self.n += 1

    barramento = Barramento()
    comp = Componente(barramento)
    tamanho_inicial = len(barramento._assinantes[_EventoTeste])

    for _ in range(200):
        barramento.desassinar_objeto(comp)
        comp = Componente(barramento)

    assert len(barramento._assinantes[_EventoTeste]) == tamanho_inicial

    barramento.publicar(_EventoTeste(valor=1))
    assert comp.n == 1, "instancias orfas continuaram assinadas"


def test_prioridade_vale_para_quem_assina_depois_da_primeira_publicacao() -> None:
    """A ordenação acontece em `assinar`, e tem de valer para inscrições
    feitas a qualquer momento — não só para as do bootstrap. É o caminho que
    a virada de sessão passa a exercitar."""
    barramento = Barramento()
    chamadas: list[str] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append("tarde"), prioridade=10)
    barramento.publicar(_EventoTeste(valor=1))
    barramento.assinar(_EventoTeste, lambda e: chamadas.append("cedo"), prioridade=0)

    chamadas.clear()
    barramento.publicar(_EventoTeste(valor=2))
    assert chamadas == ["cedo", "tarde"]
