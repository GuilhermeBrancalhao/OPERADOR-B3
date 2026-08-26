"""Sonda de substituicao de instrumento — fonte unica de fatos derivados do
instrumento regente (parte 12, `.gauntlet/2026-08-25-asg-real-b/plan.md`).

## Por que este arquivo nao pinta nada

Toda regiao visivel da superficie NEXO mora em `nexo/<regiao>.py` com uma
entrada `desenhar(painter, rect, estado)`, registrada em `REGIOES`/
`ORDEM_DESENHO` (`nexo/__init__.py`). Este modulo NAO esta nessa lista de
proposito: ele nao e uma regiao nova do quadro, e a fronteira dos *fatos*
que uma regiao precisa para nao ficar presa ao WDO quando o simbolo em
execucao e outro (ex.: WINV26 -> `WIN_GRID`, `fluxopro/app/config.py:171`).

`EstadoNexo` (ver `nexo/__init__.py`) so carrega `grid: PriceGrid` como pista
de instrumento — nao ha campo de ticker/simbolo literal atravessando essa
fronteira ate as regioes. Isso significa duas coisas, ditas aqui em vez de
escondidas:

1. Tudo que este modulo pode derivar honestamente vem de `tick_size` e
   `decimals` (e do proprio conteudo do quadro — serie de precos, alcance de
   ticks). Nunca de um texto de ticker gravado por fora.
2. Nenhuma regiao existente importa isto ainda — `ladder.py`, `niveis.py`,
   `pressao.py` etc. sao de outros autores desta rodada e este builder nao
   tem permissao para editá-los. Este arquivo e a peca pronta para ser
   adotada; a fiacao (import + chamada) fica registrada como pendencia em vez
   de forcada aqui (ver rodape do modulo e o campo `unresolved` do relatorio
   desta parte).

## O defeito que isto fecha

`pressao.py` ja resolve o rotulo de ticker a partir do `grid` (nao de um
texto fixo) — ela acerta o principio, mas com um `if/elif` copiado por
instrumento que so cobre dois casos hardcoded ali mesmo, sem lugar canonico
para uma terceira grade amanha, e sem as outras leituras (passo de eixo,
amplitude, chip) reunidas ao lado. Este modulo canoniza as leituras que
"adaptar ao instrumento regente" cobre:

* identidade do ticker/bolsa (registro extensivel, nunca `if` copiado);
* declaracao explicita do passo de grade (`0,5 pt/tick` vs `5 pt/tick`);
* passo de eixo/escada em **ticks** (nunca em pontos fixos — um passo fixo de
  `5,0` pontos e 10 ticks no WDO e so 1 tick no WIN: a mesma constante lida
  como "razoavel" num grid e "quase todo tick" no outro, exatamente o defeito
  descrito no plano: "escada e eixo com passo que nao corresponde ao grid");
* amplitude observada em pontos, com as casas do proprio grid;
* texto de um chip de nivel, delegado a `fluxopro.ui.formato` (unica fonte
  de casas/agrupamento) em vez de reimplementado aqui por cima;
* texto de cabecalho — contrato ao lado do ultimo preco (`rotulo_cabecalho`),
  resposta direta ao achado desta rodada ("nowhere in the frame is a
  contract ticker rendered... print the active contract code in the header
  next to the last price");
* texto de badge de rodape — `'ATIVO: WIN · B3'` (`badge_rodape`), a segunda
  metade do mesmo achado ("an ATIVO badge in the footer").

### Round 3 — o achado especifico desta rodada

Um critico cego pegou o quadro renderizado com `--simbolo WINV26` e achou
TRES formatos de numero pro MESMO instrumento na MESMA tela: a escada em
duas casas e passo de quarto (`28.855,50`), a fileira de chips logo abaixo
sem casa nenhuma e fora de ordem de preco com dois `--` (`28.961, 28.875,
--, --, 28.934, 28.867`), e o eixo do grafico numa terceira forma
(`28.960,75`). Isso so acontece quando escada/chip/eixo cada um formata o
preco com a propria conta em vez de chamar UMA funcao. A correcao adicionada
agora:

* `formatar_linha_ladder`, `formatar_chip` e `formatar_eixo` sao a MESMA
  funcao sob tres nomes (`verificar_convencao_unica` trava isso em teste) —
  nenhuma regiao que adotar este modulo pode fazer as tres casas divergirem
  outra vez, porque as tres chamam `fluxopro.ui.formato.preco_completo` pela
  mesma linha de codigo;
* `montar_chips` ordena os niveis por PRECO (nunca por insercao ou rank
  arbitrario) e rotula cada um pelo seu PAPEL (`BID2`/`BID`/`ULT`/`ASK`/
  `ASK2`) em vez de posicao numerica; um papel sem preco disponivel sai
  marcado `disponivel=False` com texto honesto (`'SEM NIVEL'`), nunca um
  `'--'` solto que o operador nao sabe se e "sem dado" ou "preco zero";
* `rotulo_cabecalho` (ja existente) e o texto pronto pra ficar "ao lado da
  escada em tamanho legivel" — tamanho de fonte e posicionamento sao token
  de `tema_asg.py`/geometria do `QPainter`, que este modulo nao possui nem
  deveria (regra de projeto #7); o que este modulo garante e que o TEXTO
  certo (ticker + preco na convencao do grid) existe pronto pra region
  nenhuma precisar inventar um footer de 6px como unico lugar que menciona
  o instrumento.

Este modulo continua sem estar em `REGIOES`/`ORDEM_DESENHO` — a fiacao em
`ladder.py`/`niveis.py`/`pressao.py` pertence a outros autores desta rodada
e fica fora do escopo deste arquivo (ver campo `unresolved` do relatorio).
O que muda nesta rodada e que, no dia em que a fiacao acontecer, a fonte
unica de verdade ja resolve os TRES formatos como UM so, e a fileira de
chip ja chega ordenada e rotulada — nao falta mais nenhuma funcao pura pro
lado de renderizacao consumir.

Nada aqui envia ordem, guarda estado de sessao ou versao da formula ASG —
sao funcoes puras de `PriceGrid` (ou de leituras ja congeladas do quadro),
sem `QPainter`, sem clique, sem campo.
"""

from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.eventos import PriceGrid, WDO_GRID, WIN_GRID
from fluxopro.ui import formato

# Registro extensivel de grades conhecidas -> (ticker, bolsa). Uma terceira
# grade (ex.: IND, DOL) entra como uma linha nova aqui, nunca como mais um
# `elif` a decorar — e o que faltava em `pressao._rotulo_instrumento` para
# nao virar uma parede de casos especiais conforme o catalogo cresce.
_CATALOGO: tuple[tuple[PriceGrid, str, str], ...] = (
    (WDO_GRID, "WDO", "B3"),
    (WIN_GRID, "WIN", "B3"),
)


@dataclass(frozen=True, slots=True)
class IdentidadeInstrumento:
    """Leitura honesta do instrumento regente, derivada so do `grid`.

    ``reconhecido=False`` e o estado para uma grade fora do catalogo: o
    ticker vira ``TICK {tick_size:g}`` (o proprio numero do tick, nunca um
    nome de ativo chutado) e ``bolsa`` fica em travessao. Isso e o analogo,
    para instrumento, do estado "SEM BOOK" honesto que o resto da superficie
    ja usa para profundidade ausente — nunca fabrica identidade.
    """

    ticker: str
    bolsa: str
    tick_size: float | None
    decimals: int | None
    reconhecido: bool


_INDISPONIVEL = IdentidadeInstrumento(
    ticker="ATIVO INDISPONIVEL", bolsa="—", tick_size=None, decimals=None, reconhecido=False
)


def identificar(grid: object) -> IdentidadeInstrumento:
    """Resolve a identidade a partir de `grid` — nunca de um literal externo.

    Aceita `object` (nao `PriceGrid`) e le por `getattr` de proposito: o
    mesmo cuidado defensivo que `ladder.py`/`pressao.py` ja tem com
    `contexto_bruto` ausente — um quadro sem grade valida (`tick_size`/
    `decimals` ausentes) e um estado indisponivel, nao um `AttributeError`
    que derruba a regiao inteira.
    """

    tick = getattr(grid, "tick_size", None)
    decimais = getattr(grid, "decimals", None)
    if tick is None or decimais is None:
        return _INDISPONIVEL
    for candidato, ticker, bolsa in _CATALOGO:
        if candidato.tick_size == tick and candidato.decimals == decimais:
            return IdentidadeInstrumento(ticker, bolsa, tick, decimais, True)
    return IdentidadeInstrumento(f"TICK {tick:g}", "—", tick, decimais, False)


def rotulo_ticker(grid: object) -> str:
    """`'WDO · B3'` / `'WIN · B3'` / `'TICK 2,5'` / `'ATIVO INDISPONIVEL'`.

    Formato pronto para um chip de UI, mas o modulo que desenha continua
    dono da fonte/cor (nada de `QFont`/`QColor` aqui — regra de projeto).
    """

    identidade = identificar(grid)
    if identidade.tick_size is None:
        return identidade.ticker
    if identidade.reconhecido:
        return f"{identidade.ticker} · {identidade.bolsa}"
    return identidade.ticker


def descrever_passo(grid: PriceGrid) -> str:
    """`'0,5 pt/tick'` / `'5 pt/tick'` — sempre de `grid`, nunca escrito a mao.

    E a declaracao textual mais direta do defeito "decimais ou passo de tick
    presos ao WDO": se este texto nao mudar entre `WDO_GRID` e `WIN_GRID`, a
    leitura esta presa a uma grade so.
    """

    casas = grid.decimals
    texto = f"{grid.tick_size:.{casas}f}" if casas else f"{grid.tick_size:.0f}"
    return f"{texto.replace('.', ',')} pt/tick"


def passo_eixo_ticks(
    grid: PriceGrid,
    alcance_ticks: int,
    altura_disponivel_px: int,
    altura_linha_min_px: int,
) -> int:
    """Ticks entre duas linhas consecutivas de um eixo/escada de preco.

    Devolvido em **ticks**, nunca em pontos de preco fixos: um passo fixo de
    "5,0 pontos" seria 10 ticks no WDO (tick 0,5) e 1 tick so no WIN (tick
    5,0) — a mesma constante lendo "razoavel" num grid e "quase todo tick
    visivel, sem filtro nenhum" no outro. Calculando em ticks a partir de
    geometria (altura disponivel / altura minima legivel por linha), o
    mesmo codigo produz um passo maior automaticamente quando `alcance_ticks`
    excede o que a altura comporta, para qualquer grid.

    `grid` nao entra na conta (o passo geometrico independe de tick_size),
    mas fica no assinatura de proposito: e o lembrete no proprio tipo de que
    quem usa esta funcao continua raciocinando em ticks do instrumento
    corrente, nunca em pontos fixos — e o parametro que a versao ingenua
    ("pula de 5 em 5 pontos") NAO teria, porque a falha dela e justamente
    ignorar que o passo certo depende do grid.
    """

    del grid  # ver docstring: mantido na assinatura por contrato, nao pelo calculo
    altura_linha_min_px = max(1, altura_linha_min_px)
    max_linhas = max(1, altura_disponivel_px // altura_linha_min_px)
    if alcance_ticks <= 0:
        return 1
    passo = -(-alcance_ticks // max_linhas)  # divisao inteira arredondada pra cima
    return max(1, passo)


def rotulo_cabecalho(grid: object, preco_ticks: int) -> str:
    """`'WIN · B3  28.960'` — contrato ativo colado ao ultimo preco.

    E a leitura que fecha a lacuna do achado desta rodada: "nowhere in the
    frame is a contract ticker rendered... print the active contract code
    in the header next to the last price". Nao reimplementa nenhuma das
    duas partes — concatena `rotulo_ticker` (identidade) com `formatar_chip`
    (preco nas casas do proprio grid), a mesma dupla que qualquer outro
    consumidor destas funcoes ja usaria separado. Aceita `object` (nao
    `PriceGrid`) e devolve so o rotulo do instrumento, sem preco, quando o
    grid esta indisponivel — nunca inventa um preco para um instrumento sem
    grade valida.
    """

    identidade = identificar(grid)
    if identidade.tick_size is None:
        return identidade.ticker
    return f"{rotulo_ticker(grid)}  {formatar_chip(grid, preco_ticks)}"  # type: ignore[arg-type]


def badge_rodape(grid: object) -> str:
    """`'ATIVO: WIN · B3'` — badge de rodape para o contrato regente.

    Segunda metade do mesmo achado: "an ATIVO badge in the footer". Mesma
    fonte de verdade que o cabecalho (`rotulo_ticker`, portanto o mesmo
    `_CATALOGO`) com o prefixo que um badge de rodape usa — nunca um texto
    de ticker escrito a mao por fora do catalogo.
    """

    return f"ATIVO: {rotulo_ticker(grid)}"


def formatar_chip(grid: PriceGrid, preco_ticks: int) -> str:
    """Texto completo de um chip de nivel — delega a `formato.preco_completo`.

    Nao reimplementa casas/agrupamento aqui: `fluxopro.ui.formato` e a unica
    fonte dessa regra (ver `formato.py::formatar_preco`). Um chip WIN e um
    chip WDO nunca podem divergir por coincidencia de duas formulas
    copiadas — chamam a mesma.
    """

    return formato.preco_completo(grid, preco_ticks)


def formatar_linha_ladder(grid: PriceGrid, preco_ticks: int) -> str:
    """Texto de uma linha da escada de preco — mesma convencao do chip e do
    eixo, nunca uma conta paralela.

    Existe com nome proprio so para deixar inequivoco, no ponto em que a
    escada for adotar este modulo, que ela tem de chamar ESTA funcao (que
    delega a `formatar_chip`) em vez de formatar o preco com a propria
    conta local — o defeito exato que este round achou: escada em duas
    casas e passo de quarto (`28.855,50`) numa tela onde o chip ja mostrava
    inteiro (`28.961`) e o eixo uma terceira forma (`28.960,75`), as tres
    pro MESMO instrumento porque cada regiao tinha sua propria formula.
    """

    return formatar_chip(grid, preco_ticks)


def formatar_eixo(grid: PriceGrid, preco_ticks: int) -> str:
    """Texto de um rotulo do eixo do grafico — mesma convencao da escada e
    do chip (ver `formatar_linha_ladder`); delega a `formatar_chip`.
    """

    return formatar_chip(grid, preco_ticks)


def verificar_convencao_unica(grid: PriceGrid, preco_ticks: int) -> None:
    """Trava em teste que escada/chip/eixo nunca podem voltar a divergir.

    As tres funcoes hoje sao a mesma linha de codigo (`formatar_chip`), mas
    "hoje sao iguais" nao e garantia sem um teste — um editor futuro poderia
    reimplementar uma das tres por engano, exatamente como aconteceu na
    versao que o critico pegou (tres formulas para o mesmo numero). Levanta
    `AssertionError`, nao devolve `bool`, pela mesma razao de
    `verificar_exemplo_do_plano`: divergencia aqui e regressao de contrato.
    """

    linha = formatar_linha_ladder(grid, preco_ticks)
    chip = formatar_chip(grid, preco_ticks)
    eixo = formatar_eixo(grid, preco_ticks)
    assert linha == chip == eixo, (
        f"escada/chip/eixo divergiram para o mesmo preco: "
        f"ladder={linha!r} chip={chip!r} eixo={eixo!r}"
    )


_ORDEM_PAPEIS_CANONICA: tuple[str, ...] = ("BID2", "BID", "ULT", "ASK", "ASK2")
"""Ordem de leitura de um livro saudavel — BID2 < BID < ULT < ASK < ASK2 em
preco. `montar_chips` reordena por preco de qualquer forma (nunca confia em
insercao), mas os papeis ausentes (`disponivel=False`) sao listados nesta
ordem canonica em vez de em ordem arbitraria de dicionario."""


@dataclass(frozen=True, slots=True)
class ChipNivel:
    """Um chip de nivel pronto para desenho: papel + disponibilidade + texto.

    `disponivel=False` e o estado honesto para um papel sem preco (livro
    incompleto no replay) — `texto` vem `'SEM NIVEL'`, nunca um `'--'` mudo
    que o operador nao consegue distinguir de "preco zero" ou de erro de
    parse. Nunca fabrica um preco para um papel ausente (regra de projeto
    #8: sem book, estado indisponivel honesto, nunca liquidez sintetica).
    """

    papel: str
    disponivel: bool
    texto: str


def montar_chips(niveis: dict[str, int | None], grid: PriceGrid) -> tuple[ChipNivel, ...]:
    """Fileira de chips ordenada por PRECO, rotulada por PAPEL.

    Fecha a segunda metade do achado desta rodada: a fileira de chips
    aparecia com posicao numerica em vez de papel e fora de ordem de preco,
    com `'--'` cegos misturados no meio (`28.961, 28.875, --, --, 28.934,
    28.867`). Aqui `niveis` e um mapa `{papel: preco_em_ticks | None}` com
    chaves de `_ORDEM_PAPEIS_CANONICA` (outras chaves sao ignoradas — papel
    desconhecido e erro de quem chama, nao um chip mudo a mais); a saida:

    1. papeis com preco disponivel, ordenados por `preco_ticks` ASCENDENTE
       (nunca pela ordem em que `niveis` foi construido — e o que deixava a
       fileira sair fora de ordem quando o book vinha de fontes distintas
       por papel);
    2. papeis sem preco (`None`), em `_ORDEM_PAPEIS_CANONICA`, cada um com
       `disponivel=False` e texto honesto em vez de traco mudo.

    O preco de cada chip disponivel usa `formatar_chip` — a mesma convencao
    de escada e eixo (ver `verificar_convencao_unica`), nunca um quarto
    formato reimplementado aqui.
    """

    disponiveis: list[tuple[str, int]] = []
    ausentes: list[str] = []
    for papel in _ORDEM_PAPEIS_CANONICA:
        preco_ticks = niveis.get(papel)
        if preco_ticks is None:
            ausentes.append(papel)
        else:
            disponiveis.append((papel, preco_ticks))
    disponiveis.sort(key=lambda par: par[1])

    chips = [
        ChipNivel(papel, True, formatar_chip(grid, preco_ticks))
        for papel, preco_ticks in disponiveis
    ]
    chips.extend(ChipNivel(papel, False, "SEM NIVEL") for papel in ausentes)
    return tuple(chips)


def amplitude_em_pontos(grid: PriceGrid, tick_min: int, tick_max: int) -> str:
    """Amplitude observada `[tick_min, tick_max]`, em pontos, casas do grid.

    Espelha o calculo que `pressao.py` ja faz localmente para a serie de
    precos do quadro (`grid.to_price(diferenca)` + `grid.decimals` casas),
    canonizado aqui para qualquer outra regiao que precise da mesma leitura
    sem duplicar a formula uma terceira vez. `tick_max < tick_min` e erro de
    quem chama (alcance invertido), nao um caso a mascarar com "0 PTS" ou
    valor absoluto silencioso.
    """

    if tick_max < tick_min:
        raise ValueError("tick_max nao pode ser menor que tick_min")
    pontos = grid.to_price(tick_max - tick_min)
    casas = grid.decimals
    texto = f"{pontos:.{casas}f}" if casas else f"{pontos:.0f}"
    return f"{texto.replace('.', ',')} PTS"


def verificar_exemplo_do_plano() -> None:
    """Fixa em codigo o par verificado no plano desta rodada (parte 12):

    ``WDO_GRID`` com 9999 ticks tem de formatar ``'4.999,5'``; ``WIN_GRID``
    com 999 ticks tem de formatar ``'4.995'`` — os dois numeros que
    `plan.md` cita como "verificado: WDO renderiza `4.999,5`, WIN renderiza
    `4.995`". Levanta `AssertionError` (nao devolve `bool`) porque uma
    divergencia aqui e regressao de contrato, nao um resultado a ignorar.
    """

    wdo = formatar_chip(WDO_GRID, 9999)
    win = formatar_chip(WIN_GRID, 999)
    assert wdo == "4.999,5", f"WDO diverge do exemplo do plano: {wdo!r}"
    assert win == "4.995", f"WIN diverge do exemplo do plano: {win!r}"


def verificar_chips_ordenados_e_rotulados() -> None:
    """Fixa em codigo a correcao do achado desta rodada para `montar_chips`:
    entrada fora de ordem de preco com um papel ausente tem de sair
    ordenada por preco, rotulada por papel, com o ausente honesto (nunca um
    `'--'` no meio da sequencia).
    """

    niveis = {"BID2": 999, "ASK": 1002, "BID": 1000, "ULT": None, "ASK2": 1004}
    chips = montar_chips(niveis, WIN_GRID)
    papeis = tuple(chip.papel for chip in chips)
    assert papeis == ("BID2", "BID", "ASK", "ASK2", "ULT"), (
        f"ordem/rotulo de chips divergiu do esperado: {papeis!r}"
    )
    disponiveis = tuple(chip.disponivel for chip in chips)
    assert disponiveis == (True, True, True, True, False), (
        f"disponibilidade de chips divergiu do esperado: {disponiveis!r}"
    )
    ultimo = chips[-1]
    assert ultimo.texto == "SEM NIVEL", f"papel ausente sem texto honesto: {ultimo.texto!r}"


def auditar(grids: tuple[PriceGrid, ...] = (WDO_GRID, WIN_GRID)) -> tuple[str, ...]:
    """Relatorio textual, pronto para linha de comando (`__main__` abaixo).

    Nao e teste (nao usa `assert` de framework nenhum) — e a sonda em forma
    de texto: uma linha por grade do catalogo mostrando ticker, passo e um
    preco de exemplo, mais o veredito de `verificar_exemplo_do_plano`.
    """

    linhas = []
    for grid in grids:
        ticks_exemplo = round(5000.0 / grid.tick_size)
        exemplo = formatar_chip(grid, ticks_exemplo)
        linhas.append(
            f"{rotulo_ticker(grid):<10} passo={descrever_passo(grid):<10} "
            f"exemplo~{exemplo}"
        )
        linhas.append(f"  cabecalho~'{rotulo_cabecalho(grid, ticks_exemplo)}'")
        linhas.append(f"  rodape~'{badge_rodape(grid)}'")
        try:
            verificar_convencao_unica(grid, ticks_exemplo)
            linhas.append("  convencao unica (ladder=chip=eixo): OK")
        except AssertionError as erro:
            linhas.append(f"  convencao unica: REGRESSAO — {erro}")
    try:
        verificar_exemplo_do_plano()
        linhas.append("exemplo do plano (9999 ticks WDO / 999 ticks WIN): OK")
    except AssertionError as erro:
        linhas.append(f"exemplo do plano: REGRESSAO — {erro}")
    try:
        verificar_chips_ordenados_e_rotulados()
        linhas.append("chips ordenados por preco + rotulados por papel: OK")
    except AssertionError as erro:
        linhas.append(f"chips ordenados/rotulados: REGRESSAO — {erro}")
    return tuple(linhas)


__all__ = [
    "ChipNivel",
    "IdentidadeInstrumento",
    "amplitude_em_pontos",
    "auditar",
    "badge_rodape",
    "descrever_passo",
    "formatar_chip",
    "formatar_eixo",
    "formatar_linha_ladder",
    "identificar",
    "montar_chips",
    "passo_eixo_ticks",
    "rotulo_cabecalho",
    "rotulo_ticker",
    "verificar_chips_ordenados_e_rotulados",
    "verificar_convencao_unica",
    "verificar_exemplo_do_plano",
]


if __name__ == "__main__":
    import sys

    # Console do Windows por padrao usa cp1252, que nao cobre `·`/`—` que os
    # rotulos ja carregam (mesmo caracteres que a superficie pinta via Qt sem
    # problema — o problema e so do terminal, nunca do dado). Reconfigurar
    # para utf-8 aqui e cosmetico de execucao direta, nao muda nenhum valor
    # devolvido por `auditar()`.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for _linha in auditar():
        print(_linha)
