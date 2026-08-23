"""O produto nao envia ordem — provado, e nao afirmado.

## Por que este arquivo existe

"Modo SINAIS e sempre. Nao existe envio de ordem no codigo, e a tela declara
isso." Esta frase esta no `README.md`, no cabecalho de `scripts/painel.py`, e
uma versao dela e DESENHADA no rodape da janela, onde o operador le.

Ate este arquivo, nada a verificava. Ela estava garantida por comentario.

E a afirmacao mais séria que o produto faz. Um terminal de fluxo que ganha,
por descuido ou por uma linha bem-intencionada, a capacidade de mandar ordem
para a corretora deixa de ser um terminal de leitura e passa a ser um robo de
execucao — com dinheiro real de alguem do outro lado. As outras afirmacoes
deste projeto custam credibilidade quando erram; esta custa patrimonio.

Vale aqui a licao que a onda 11 pagou duas vezes em coisas menores: **lei
verificada caso a caso e sorte; lei verificada como varredura e portao.** So
que aqui nem caso a caso havia.

## Por que lista FECHADA, e nao lista de proibicoes

O jeito obvio seria proibir `order_send`, `order_check`, `TRADE_ACTION_DEAL` e
companhia. Isso falha do jeito silencioso: cobre o que hoje se sabe chamar, e
nao cobre o metodo de execucao que a proxima versao do pacote introduzir, nem
`getattr(mt5, "order_" + acao)`, nem um pacote de corretora diferente.

Aqui o teste enumera **tudo** o que o codigo acessa do modulo `MetaTrader5` e
exige que esteja em `SUPERFICIE_PERMITIDA`. Chamada nova reprova por ser nova,
nao por ser reconhecida como perigosa. Quem precisar de uma tem de escrever o
nome dela aqui — e ai a decisao aparece na revisao, que e onde ela pertence.

E o mesmo desenho de `tests/test_ui_retencao.py`, que enumera os paineis a
partir da janela em vez de uma lista digitada: um portao so continua valendo
depois que quem o escreveu sai se ele nao depender de alguem lembrar.

## O que este teste NAO prova

Nao prova que o programa e seguro, nem que a corretora nao pode ser acionada
por outro caminho — um `subprocess`, um `eval`, uma dependencia futura. Prova
uma coisa so, e com precisao: **o codigo deste repositorio nao toca em nenhuma
funcao de execucao do pacote `MetaTrader5`, e a superficie que ele toca esta
declarada.** Uma afirmacao estreita e verdadeira vale mais que uma larga e
esperancosa.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent

SUPERFICIE_PERMITIDA = frozenset(
    {
        # --- ciclo de vida da conexao ---
        "initialize",
        "shutdown",
        "last_error",
        # --- selecao de instrumento ---
        "symbol_select",
        "symbol_info_tick",
        # --- leitura de negocios ---
        "copy_ticks_from",
        "COPY_TICKS_ALL",
        "TICK_FLAG_BUY",
        "TICK_FLAG_SELL",
        # --- leitura de livro ---
        "market_book_add",
        "market_book_get",
        "market_book_release",
        "BOOK_TYPE_BUY",
        "BOOK_TYPE_SELL",
    }
)
"""Tudo o que o codigo pode acessar do pacote `MetaTrader5`.

Quinze nomes, e os quinze sao de LEITURA ou de conexao. Nenhum cria, altera ou
cancela ordem; nenhum consulta posicao aberta ou saldo.

`market_book_add` tem nome de escrita e nao e: ele ASSINA o livro de ofertas
do instrumento, que e o que permite `market_book_get` devolver algo. O par
dele e `market_book_release`. Fica registrado aqui porque um leitor apressado
desta lista tenderia a estranhar justamente o nome certo.
"""

_PACOTE = "MetaTrader5"


def _modulos() -> list[pathlib.Path]:
    """Todo `.py` de produção do repositorio.

    Exclui `tests/` (este arquivo cita os nomes proibidos, e ele mesmo
    reprovaria), o proprio empacotamento e as arvores de trabalho de outras
    sessoes em `.claude/worktrees/`, que sao copias e nao codigo publicado.
    """
    arquivos: list[pathlib.Path] = []
    for caminho in RAIZ.rglob("*.py"):
        partes = caminho.relative_to(RAIZ).parts
        if partes[0] in {"tests", ".claude", "build", "dist"}:
            continue
        if any(parte.startswith(".") or parte == "__pycache__" for parte in partes):
            continue
        arquivos.append(caminho)
    return sorted(arquivos)


def _apelidos_do_pacote(arvore: ast.AST) -> set[str]:
    """Sob que nomes locais o pacote `MetaTrader5` entrou neste modulo.

    Cobre `import MetaTrader5 as mt5`, `import MetaTrader5` e
    `from MetaTrader5 import x` — o terceiro devolve o marcador `*`, porque ali
    o nome importado JA E a superficie e nao ha atributo a inspecionar depois.
    """
    apelidos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                if alias.name == _PACOTE or alias.name.startswith(_PACOTE + "."):
                    apelidos.add(alias.asname or alias.name)
        elif isinstance(no, ast.ImportFrom) and no.module == _PACOTE:
            apelidos.add("*")
    return apelidos


def _guardas(arvore: ast.AST, apelidos: set[str]) -> set[str]:
    """Atributos que RECEBEM o modulo e passam a valer como apelido dele.

    Buraco encontrado pela propria prova deste arquivo, e nao por leitura: com
    a lista permitida esvaziada, a varredura acusou 16 acessos e **nenhum** era
    das linhas 637-638 de `fluxopro/dados/mt5.py`. O adaptador guarda o pacote
    em `self._mt5 = mt5` e chama por ali, e um teste que so olha `mt5.<algo>`
    nao ve `self._mt5.<algo>`.

    O tamanho do buraco: `self._mt5.order_send(...)` passaria batido pelo
    portao inteiro. Um portao com uma porta dos fundos nao e um portao mais
    fraco — e um portao que da falsa confianca, que e pior que nao ter.
    """
    guardas: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Assign) or not isinstance(no.value, ast.Name):
            continue
        if no.value.id not in apelidos:
            continue
        for alvo in no.targets:
            if isinstance(alvo, ast.Attribute):
                guardas.add(alvo.attr)
            elif isinstance(alvo, ast.Name):
                guardas.add(alvo.id)
    return guardas


def _e_do_pacote(no: ast.expr, apelidos: set[str], guardas: set[str]) -> bool:
    """`mt5` (nome direto) ou `self._mt5` (atributo que recebeu o modulo)."""
    if isinstance(no, ast.Name):
        return no.id in apelidos or no.id in guardas
    return isinstance(no, ast.Attribute) and no.attr in guardas


def _acessos(arvore: ast.AST, apelidos: set[str]) -> set[tuple[str, int]]:
    """`(nome, linha)` de todo atributo lido de um apelido do pacote.

    Pega `mt5.order_send` e tambem `getattr(mt5, "order_send")` — a segunda
    forma existe de verdade neste codigo, em `getattr(mt5, "symbol_info_tick",
    None)`, entao ignora-la deixaria um buraco do tamanho de uma string.

    Alcanca tambem os GUARDAS (`self._mt5.<algo>`) — ver `_guardas`.

    `getattr` com nome NAO literal (`getattr(mt5, "order_" + acao)`) e
    reportado como `<dinamico>`, que nunca esta na lista permitida e portanto
    reprova. Um acesso que o teste nao consegue ler e um acesso que ele nao
    pode aprovar.
    """
    guardas = _guardas(arvore, apelidos)
    achados: set[tuple[str, int]] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute) and _e_do_pacote(no.value, apelidos, guardas):
            achados.add((no.attr, no.lineno))
        elif (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "getattr"
            and no.args
            and _e_do_pacote(no.args[0], apelidos, guardas)
        ):
            alvo = no.args[1] if len(no.args) > 1 else None
            if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
                achados.add((alvo.value, no.lineno))
            else:
                achados.add(("<dinamico>", no.lineno))
    return achados


def _fora_da_superficie() -> list[str]:
    fora: list[str] = []
    for caminho in _modulos():
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"), str(caminho))
        except SyntaxError as erro:  # pragma: no cover — arquivo quebrado
            fora.append(f"{caminho.relative_to(RAIZ)}: nao parseia ({erro})")
            continue
        apelidos = _apelidos_do_pacote(arvore)
        if "*" in apelidos:
            fora.append(
                f"{caminho.relative_to(RAIZ)}: `from {_PACOTE} import ...` — "
                "a superficie deixa de ser inspecionavel por atributo"
            )
            apelidos.discard("*")
        for nome, linha in sorted(_acessos(arvore, apelidos), key=lambda p: p[1]):
            if nome not in SUPERFICIE_PERMITIDA:
                fora.append(f"{caminho.relative_to(RAIZ)}:{linha}: {_PACOTE}.{nome}")
    return fora


def test_o_codigo_so_toca_na_superficie_de_leitura_do_metatrader():
    """A afirmacao central: nada fora da lista declarada.

    Reprovar aqui NAO significa "alguem esta mandando ordem". Significa que a
    superficie do pacote usada pelo produto mudou e ninguem declarou — que e
    exatamente o momento em que a decisao deve ser tomada por uma pessoa, e nao
    herdada de um diff.
    """
    fora = _fora_da_superficie()
    assert not fora, (
        "acesso ao pacote %s fora de `SUPERFICIE_PERMITIDA`:\n%s\n\n"
        "Se o acesso e legitimo e de LEITURA, acrescente o nome a lista com o "
        "motivo. Se e de execucao, ele nao entra: o produto e modo sinais." % (
            _PACOTE,
            "\n".join(f"  {linha}" for linha in fora),
        )
    )


def test_a_superficie_declarada_nao_contem_execucao():
    """O portao do portao.

    A lista permitida e editavel — e essa e a graça dela. Este teste garante
    que editá-la nao seja um caminho silencioso para abrir execucao: nenhum
    nome da lista pode conter radical de ordem, posicao, negociacao ou conta.

    Nao substitui a revisao humana, e nao pretende: e a rede que pega o
    acrescimo distraido, nao o deliberado.
    """
    proibidos = (
        "order",
        "trade",
        "position",
        "deal",
        "account",
        "margin",
        "buy",
        "sell",
    )
    suspeitos = {
        nome: [radical for radical in proibidos if radical in nome.lower()]
        for nome in SUPERFICIE_PERMITIDA
    }
    suspeitos = {nome: r for nome, r in suspeitos.items() if r}

    # As duas excecoes sao FLAGS de leitura, e estao nomeadas uma a uma em vez
    # de cobertas por um filtro esperto: `TICK_FLAG_BUY`/`SELL` classificam o
    # agressor de um negocio JA OCORRIDO, e `BOOK_TYPE_BUY`/`SELL` dizem de que
    # lado do livro esta uma oferta. Nenhuma das quatro e verbo.
    esperadas = {
        "TICK_FLAG_BUY": ["buy"],
        "TICK_FLAG_SELL": ["sell"],
        "BOOK_TYPE_BUY": ["buy"],
        "BOOK_TYPE_SELL": ["sell"],
    }
    assert suspeitos == esperadas, (
        "nome com radical de execucao em `SUPERFICIE_PERMITIDA`:\n"
        + "\n".join(f"  {n}: {r}" for n, r in sorted(suspeitos.items()))
    )


def test_a_varredura_enxerga_o_modulo_que_fala_com_o_metatrader():
    """Sem isto, o teste passaria numa arvore em que o adaptador nem existe.

    E a mesma armadilha do `test_ui_retencao.py`: enumerar nao e exercitar. Se
    o filtro de `_modulos()` ficar apertado demais, ou o adaptador mudar de
    lugar, os dois testes acima continuariam verdes sem olhar linha nenhuma —
    verdes por vacuidade, que e a pior cor de verde.
    """
    inspecionados = {
        caminho: _apelidos_do_pacote(
            ast.parse(caminho.read_text(encoding="utf-8"), str(caminho))
        )
        for caminho in _modulos()
    }
    com_pacote = {c for c, apelidos in inspecionados.items() if apelidos}
    assert com_pacote, (
        f"nenhum modulo de producao importa {_PACOTE} — ou o adaptador sumiu, "
        "ou `_modulos()` esta filtrando demais e a varredura virou decorativa"
    )
    nomes = {c.name for c in com_pacote}
    assert "mt5.py" in nomes, f"adaptador nao encontrado; visto: {sorted(nomes)}"


def test_a_varredura_reprova_uma_chamada_de_execucao(tmp_path):
    """Prova por MUTACAO, e sem tocar no repositorio.

    O criterio deste projeto: teste que nunca foi visto reprovando nao e
    portao. Aqui a mutacao roda sobre um modulo sintetico, porque escrever
    `order_send` num arquivo de producao — ainda que por um segundo, ainda que
    revertido — e a unica coisa que este arquivo existe para impedir.
    """
    modulo = tmp_path / "adaptador_falso.py"
    modulo.write_text(
        "import MetaTrader5 as mt5\n"
        "def enviar(p):\n"
        "    return mt5.order_send(p)\n"
        "def dinamico(acao):\n"
        "    return getattr(mt5, 'order_' + acao)\n",
        encoding="utf-8",
    )
    arvore = ast.parse(modulo.read_text(encoding="utf-8"), str(modulo))
    apelidos = _apelidos_do_pacote(arvore)
    acessados = {nome for nome, _linha in _acessos(arvore, apelidos)}

    assert "order_send" in acessados
    assert "<dinamico>" in acessados, (
        "`getattr(mt5, 'order_' + acao)` precisa aparecer como <dinamico>: um "
        "acesso que o teste nao consegue ler nao pode ser aprovado em silencio"
    )
    assert not (acessados & SUPERFICIE_PERMITIDA)

    # A porta dos fundos, SOZINHA. No modulo acima `order_send` aparece pelas
    # duas rotas, e um `set` de nomes as confunde: o teste passaria mesmo que
    # `_guardas` nao existisse. Aqui o modulo so tem a rota do guarda.
    so_guarda = tmp_path / "so_guarda.py"
    so_guarda.write_text(
        chr(10).join(
            [
                "import MetaTrader5 as mt5",
                "class A:",
                "    def __init__(self):",
                "        self._mt5 = mt5",
                "    def enviar(self, p):",
                "        return self._mt5.order_send(p)",
            ]
        ),
        encoding="utf-8",
    )
    arvore_g = ast.parse(so_guarda.read_text(encoding="utf-8"), str(so_guarda))
    nomes_g = {
        nome for nome, _l in _acessos(arvore_g, _apelidos_do_pacote(arvore_g))
    }
    assert "order_send" in nomes_g, (
        "`self._mt5.order_send(...)` passou batido: o portao tem porta dos "
        "fundos, e portao com porta dos fundos da falsa confianca"
    )


@pytest.mark.parametrize(
    "arquivo,frase",
    [
        ("README.md", "Não existe envio de ordem no código"),
        ("scripts/painel.py", "nao envia ordem para lugar nenhum"),
    ],
)
def test_a_promessa_escrita_continua_no_lugar(arquivo, frase):
    """A frase que o portao acima sustenta.

    Se alguem apagar a promessa, este teste cai e obriga a decidir: ou a
    promessa volta, ou o portao perde o motivo de existir e sai junto. O que
    nao pode acontecer e o produto parar de prometer e ninguem notar — nem o
    contrario, prometer sem nada sustentando, que era a situacao ate aqui.
    """
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    assert frase in texto, f"{arquivo} nao contem mais: {frase!r}"
