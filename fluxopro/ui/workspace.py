"""Workspaces — FASE 3 de `direcao_visual.md` §6, e a regra da janela órfã.

§4.1 pede quatro coisas, e três delas o Qt dá de graça:

> **Workspace** = `saveGeometry()` + `saveState()` + estado próprio de cada
> painel, serializado em `%APPDATA%/FluxoPro/workspaces/<nome>.json`. Troca
> por `Ctrl+1..9`. Workspaces de fábrica: **Fluxo**, **Book & Tape**,
> **Bookmap**, **Revisão**.

A quarta não:

> Ao restaurar num arranjo de telas diferente, a janela órfã vai para o
> monitor primário **com aviso na trilha de eventos** — nunca abre fora da
> área visível (defeito clássico de terminal).

`restoreGeometry` do Qt **não** garante isso. Ele restaura os números que
foram salvos; se o monitor da direita não existe mais, a janela vai para onde
o monitor estava. É o defeito que §4.1 nomeia, e é por isso que
`reancorar` existe e é uma função **pura de geometria** — testável sem
monitor nenhum, o que é a única forma de testar isto num CI.

## O conflito docking × cadeia, decidido

`ui/janela.py` recusou `QSplitter` por duas razões escritas lá: *"o punho é
desenhado pelo estilo do SO (viola V5) e faria o alinhamento do trilho
depender de estado não versionado"*. `QDockWidget` tem o mesmo problema em
dose maior. A decisão tomada aqui, e implementada em `ui/janela.py`, é:

**os dois convivem, e quem se subordina é o trilho.**

1. **O cromo do SO é substituído, não tolerado.** Cada doca recebe
   `setTitleBarWidget()` com um cabeçalho desenhado por nós, e o separador do
   `QMainWindow` recebe folha de estilo **derivada dos tokens**
   (`folha_de_estilo`), não uma cor literal. Os pixels passam a vir de código
   versionado — que era a objeção real ao `QSplitter`, e não o docking em si.

2. **O trilho deixa de ser uma afirmação sobre o produto e passa a ser uma
   afirmação sobre o ARRANJO.** Ele lê a geometria real das docas visíveis,
   agrupa por elo da cadeia e só desenha quatro segmentos quando os quatro
   elos ocupam faixas horizontais **disjuntas e em ordem**. Quando não
   ocupam — doca escondida, flutuando noutro monitor, tabulada atrás de
   outra, ou fora de ordem — ele **recusa desenhar a cadeia** e diz
   `ARRANJO LIVRE`, com o motivo, e escreve uma linha na trilha de eventos.

A alternativa era manter o trilho fixo em quatro segmentos. Seria pior do que
não ter trilho: o próprio `janela.py` argumenta que *"um trilho que não
acompanhasse a largura da coluna seria uma legenda"*, e legenda desalinhada
ensina o operador a apontar para o lugar errado. O que o docking custou,
então, foi **a garantia de que a cadeia sempre está legível** — e esse custo
está dito na tela, não escondido.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect

from fluxopro.ui import tokens

# --------------------------------------------------------------------------
# As docas e os elos da cadeia
# --------------------------------------------------------------------------
ELO_FORA = 0
ELO_DADOS = 1
ELO_PROCESSAMENTO = 2
ELO_ESTADO = 3
ELO_DECISAO = 4
N_ELOS = 4

ELO_DA_DOCA: dict[str, int] = {
    # elo 1 — dados de mercado, crus
    "dom": ELO_DADOS,
    "tape": ELO_DADOS,
    "players": ELO_DADOS,
    "bookmap": ELO_DADOS,
    # elo 2 — processamento
    "conduto": ELO_PROCESSAMENTO,
    # elo 3 — estado derivado
    "footprint": ELO_ESTADO,
    "perfil": ELO_ESTADO,
    "delta": ELO_ESTADO,
    "matriz": ELO_ESTADO,
    # elo 4 — decisão
    "hud": ELO_DECISAO,
    "metodo": ELO_DECISAO,
    "regras": ELO_DECISAO,
    # Camada ASG-like consultiva. Ela resume os quatro elos, mas ocupa a
    # coluna de decisão ao lado dos painéis originais — nunca os substitui.
    "asg": ELO_DECISAO,
    # fora da cadeia: transporte e meta. Não têm elo porque não SÃO elo —
    # pô-los num elo qualquer para "completar" o trilho seria mentir sobre a
    # cadeia para poder desenhá-la.
    "replay": ELO_FORA,
    "trilha": ELO_FORA,
}

TITULO_DA_DOCA: dict[str, str] = {
    "dom": "DOM",
    "tape": "TAPE",
    "players": "PLAYERS",
    "bookmap": "BOOKMAP",
    "conduto": "CONDUTO",
    "footprint": "FOOTPRINT",
    "perfil": "PERFIL DE VOLUME",
    "delta": "DELTA ACUMULADO",
    "matriz": "MATRIZ DE ESTADO",
    "hud": "HUD",
    "metodo": "MÉTODO",
    "regras": "REGISTRO DE REGRAS",
    # A chave ``asg`` é uma ABI interna/persistida; a identidade exibida é
    # própria e não sugere vínculo, reprodução ou licença de terceiro.
    "asg": "OPERADOR B3 · NEXO",
    "nexo_ai": "NEXO AI · PAINEL VERTICAL",
    "replay": "REPLAY",
    "trilha": "TRILHA DE EVENTOS",
}


@dataclass(frozen=True, slots=True)
class Workspace:
    """Um arranjo de fábrica: quais docas ficam visíveis, e em que ordem.

    `docas` é o conjunto VISÍVEL. As demais existem na janela e ficam
    escondidas — construir e destruir painel a cada troca de workspace
    reiniciaria o histórico de tela do footprint e do bookmap toda vez, que é
    o oposto do que um workspace serve para fazer.
    """

    nome: str
    atalho: int
    """1..9, o dígito de `Ctrl+N`."""
    descricao: str
    docas: tuple[str, ...]
    rotulo: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.atalho <= 9:
            raise ValueError("§4.1 dá Ctrl+1..9; %r está fora" % (self.atalho,))
        for doca in self.docas:
            if doca not in ELO_DA_DOCA:
                raise ValueError("doca desconhecida: %r" % (doca,))

    @property
    def elos_cobertos(self) -> frozenset[int]:
        return frozenset(
            ELO_DA_DOCA[d] for d in self.docas if ELO_DA_DOCA[d] != ELO_FORA
        )

    @property
    def cadeia_completa(self) -> bool:
        """O arranjo tem doca visível para os QUATRO elos?

        Um workspace sem isto é legítimo — `Bookmap` existe para olhar
        liquidez, não para ler a cadeia inteira —, e é exatamente o caso em
        que o trilho tem de dizer `ARRANJO LIVRE` em vez de inventar segmento.
        """
        return self.elos_cobertos == frozenset(range(1, N_ELOS + 1))

    @property
    def nome_exibicao(self) -> str:
        """Nome público da sala, sem quebrar o identificador persistido."""

        return self.rotulo or self.nome


WORKSPACES_DE_FABRICA: tuple[Workspace, ...] = (
    Workspace(
        "Fluxo",
        1,
        "a cadeia inteira em quatro colunas — o arranjo canônico",
        ("dom", "tape", "players", "conduto", "footprint", "perfil", "delta",
         "matriz", "hud", "metodo", "regras"),
    ),
    Workspace(
        "Book & Tape",
        2,
        "leitura de curtíssimo prazo: livro, negócios e decisão",
        ("dom", "tape", "players", "conduto", "matriz", "hud", "metodo", "regras"),
    ),
    Workspace(
        "Bookmap",
        3,
        "liquidez no tempo, com o tape ao lado",
        ("bookmap", "tape", "conduto", "delta", "hud", "metodo"),
    ),
    Workspace(
        "Revisão",
        4,
        "pós-pregão: replay, trilha e o que o método leu",
        ("replay", "trilha", "tape", "conduto", "footprint", "perfil", "delta",
         "matriz", "metodo", "regras"),
    ),
)

NOMES_DE_FABRICA: tuple[str, ...] = tuple(w.nome for w in WORKSPACES_DE_FABRICA)
PADRAO = WORKSPACES_DE_FABRICA[0]

# Extensão opt-in. Os quatro nomes e atalhos de fábrica acima permanecem uma
# ABI pública (testes, perfis salvos e documentação). O ASG-like entra como
# quinto arranjo disponível sem reescrever essa lista histórica.
WORKSPACE_ASG = Workspace(
    "ASG-like",
    5,
    "fluxo completo com MakerProxy independente e decisão consultiva",
    ("dom", "tape", "players", "bookmap", "conduto", "footprint", "perfil",
    "delta", "asg", "trilha"),
    "OPERADOR B3",
)
WORKSPACE_NEXO_AI = Workspace(
    "NEXO AI",
    6,
    "painel vertical com núcleo, gráfico e três cartões de leitura",
    (),
    "NEXO AI",
)
WORKSPACES_DISPONIVEIS: tuple[Workspace, ...] = (
    *WORKSPACES_DE_FABRICA,
    WORKSPACE_ASG,
    WORKSPACE_NEXO_AI,
)
NOMES_DISPONIVEIS: tuple[str, ...] = tuple(w.nome for w in WORKSPACES_DISPONIVEIS)
NOMES_DE_ENTRADA: tuple[str, ...] = tuple(w.nome_exibicao for w in WORKSPACES_DISPONIVEIS)


def por_atalho(digito: int) -> Workspace | None:
    for w in WORKSPACES_DISPONIVEIS:
        if w.atalho == digito:
            return w
    return None


def por_nome(nome: str) -> Workspace | None:
    for w in WORKSPACES_DISPONIVEIS:
        if w.nome == nome or w.nome_exibicao == nome:
            return w
    return None


# --------------------------------------------------------------------------
# A regra da janela órfã — pura, testável sem monitor
# --------------------------------------------------------------------------
FRACAO_VISIVEL_MINIMA = 0.5
"""Quanto da janela precisa cair em área de tela para ela NÃO ser órfã.

Meia janela e não um pixel: uma janela 95% fora da tela satisfaz "tem
interseção" e continua sendo o defeito que §4.1 descreve — o operador vê uma
lasca e não consegue nem arrastá-la de volta, porque a barra de título ficou
do lado de fora."""


def area_visivel(geometria: QRect, areas: tuple[QRect, ...]) -> int:
    """Pixels da janela que caem em alguma tela.

    Soma as interseções. As áreas de tela reportadas pelo Qt são disjuntas
    (`QScreen.availableGeometry` não se sobrepõe entre monitores), então somar
    não conta pixel duas vezes.
    """
    total = 0
    for area in areas:
        corte = geometria.intersected(area)
        if not corte.isEmpty():
            total += corte.width() * corte.height()
    return total


def e_orfa(
    geometria: QRect,
    areas: tuple[QRect, ...],
    fracao_minima: float = FRACAO_VISIVEL_MINIMA,
) -> bool:
    propria = geometria.width() * geometria.height()
    if propria <= 0:
        return True
    if not areas:
        return True
    return area_visivel(geometria, areas) < fracao_minima * propria


def reancorar(
    geometria: QRect,
    areas: tuple[QRect, ...],
    primaria: QRect,
    fracao_minima: float = FRACAO_VISIVEL_MINIMA,
) -> tuple[QRect, bool]:
    """`(geometria corrigida, era_órfã)` — a regra de §4.1, sem Qt de janela.

    Órfã vai para o monitor primário **inteira**: encolhida se for maior que
    ele e depois empurrada para dentro. Não centralizada — centralizar
    descartaria a proporção que o operador escolheu; encolher e encaixar
    preserva o máximo do arranjo que ainda cabe.

    Não-órfã volta intacta. Uma janela que estivesse 60% visível e fosse
    "arrumada" mesmo assim seria a função remexendo num arranjo deliberado.
    """
    if not e_orfa(geometria, areas, fracao_minima):
        return geometria, False
    largura = min(geometria.width(), primaria.width())
    altura = min(geometria.height(), primaria.height())
    x = min(max(geometria.x(), primaria.left()), primaria.right() - largura + 1)
    y = min(max(geometria.y(), primaria.top()), primaria.bottom() - altura + 1)
    return QRect(x, y, largura, altura), True


# --------------------------------------------------------------------------
# O trilho, subordinado ao arranjo
# --------------------------------------------------------------------------
MOTIVO_ELO_AUSENTE = "elo %d sem painel visível"
MOTIVO_FORA_DE_ORDEM = "elo %d à esquerda do elo %d"
MOTIVO_SOBREPOSTOS = "elos %d e %d ocupam a mesma faixa"


def cortes_da_cadeia(
    faixas: tuple[tuple[int, int] | None, ...], largura: int
) -> tuple[tuple[int, int, int] | None, str]:
    """Os três cortes do trilho, ou `(None, motivo)` se o arranjo não é cadeia.

    `faixas[i]` é `(x_esquerda, x_direita)` da união das docas do elo `i+1`,
    em coordenadas da janela, ou `None` se o elo não tem doca visível.

    Pura de propósito: é a conta que decide se o trilho AFIRMA ou se ABSTÉM, e
    ela precisa ser exercitável sem montar catorze painéis. O desenho e o
    teste chamam esta função, não uma cópia dela (lei nº 6).
    """
    if len(faixas) != N_ELOS:
        raise ValueError("a cadeia tem %d elos" % N_ELOS)
    for indice, faixa in enumerate(faixas):
        if faixa is None:
            return None, MOTIVO_ELO_AUSENTE % (indice + 1)
    for i in range(N_ELOS - 1):
        atual = faixas[i]
        seguinte = faixas[i + 1]
        assert atual is not None and seguinte is not None
        if seguinte[0] <= atual[0]:
            return None, MOTIVO_FORA_DE_ORDEM % (i + 2, i + 1)
        if seguinte[0] <= atual[1]:
            return None, MOTIVO_SOBREPOSTOS % (i + 1, i + 2)
    cortes = tuple(
        min(max(0, faixas[i + 1][0]), largura) for i in range(N_ELOS - 1)  # type: ignore[index]
    )
    return cortes, ""  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Cromo: a folha de estilo derivada dos tokens
# --------------------------------------------------------------------------
def folha_de_estilo() -> str:
    """O separador do `QMainWindow`, pintado por NÓS.

    É o ponto em que o docking deixa de violar V5. O punho do `QSplitter` era
    desenhado pelo estilo do sistema; o separador do `QMainWindow` também é,
    a menos que se declare — então declara-se, com 1px e a cor que o resto da
    composição usa para separar coluna (`_separador` em `janela.py` desenha
    exatamente isto num `QFrame`).

    Os valores vêm de `tokens`, nunca de um literal: `tokens.BORDER.name()`
    responde pelo hex, e quem trocar o token troca o separador junto.
    """
    return (
        "QMainWindow::separator { background: %s; width: 1px; height: 1px; "
        "margin: 0px; padding: 0px; }\n"
        "QMainWindow::separator:hover { background: %s; }\n"
        "QDockWidget { border: 0px; }\n"
        % (tokens.BORDER.name(), tokens.BORDER_STRONG.name())
    )


# --------------------------------------------------------------------------
# Persistência
# --------------------------------------------------------------------------
VERSAO_ARQUIVO = 1


def diretorio_de_workspaces() -> Path:
    """`%APPDATA%/FluxoPro/workspaces`, com escape para quem não é Windows.

    `FLUXOPRO_WORKSPACES` tem precedência — é o que permite ao teste escrever
    num `tmp_path` sem tocar no perfil de quem roda a suíte. Um teste que
    gravasse no `%APPDATA%` real apagaria o arranjo do operador para provar
    que sabe gravar arquivo.
    """
    forcado = os.environ.get("FLUXOPRO_WORKSPACES")
    if forcado:
        return Path(forcado)
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "FluxoPro" / "workspaces"


def caminho_do_workspace(nome: str) -> Path:
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)
    return diretorio_de_workspaces() / (seguro + ".json")


def serializar(nome: str, geometria: QByteArray, estado: QByteArray, extra: dict) -> str:
    """JSON, com os dois blobs do Qt em base64.

    JSON e não `QSettings`: §4.1 pede um arquivo por workspace num caminho
    nomeado, e um formato que uma pessoa possa abrir e apagar quando o Qt
    salvar um arranjo impossível — que acontece.
    """
    return json.dumps(
        {
            "versao": VERSAO_ARQUIVO,
            "nome": nome,
            "geometria": base64.b64encode(bytes(geometria)).decode("ascii"),
            "estado": base64.b64encode(bytes(estado)).decode("ascii"),
            "extra": extra,
        },
        ensure_ascii=False,
        indent=1,
    )


def desserializar(texto: str) -> tuple[QByteArray, QByteArray, dict]:
    dados = json.loads(texto)
    if dados.get("versao") != VERSAO_ARQUIVO:
        raise ValueError(
            "arquivo de workspace na versão %r; esta build lê %d"
            % (dados.get("versao"), VERSAO_ARQUIVO)
        )
    return (
        QByteArray(base64.b64decode(dados["geometria"])),
        QByteArray(base64.b64decode(dados["estado"])),
        dict(dados.get("extra") or {}),
    )


def salvar(nome: str, geometria: QByteArray, estado: QByteArray, extra: dict) -> Path:
    caminho = caminho_do_workspace(nome)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(serializar(nome, geometria, estado, extra), encoding="utf-8")
    return caminho


def carregar(nome: str) -> tuple[QByteArray, QByteArray, dict] | None:
    """`None` quando não há arquivo — ausência não é erro, é primeira vez."""
    caminho = caminho_do_workspace(nome)
    if not caminho.exists():
        return None
    return desserializar(caminho.read_text(encoding="utf-8"))
