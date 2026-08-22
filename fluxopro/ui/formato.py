"""Formatacao numerica da interface — `design/direcao_visual.md` §3.4.

Puro de proposito: nao importa Qt, entao roda em teste sem `QApplication`
e sem plataforma grafica. Toda regra de leitura de numero mora aqui, e nao
espalhada por painel, porque as tres que importam sao faceis de violar uma
de cada vez:

* **Sinal explicito, nunca parenteses.** O Profit Pro grafa saldo comprador
  e vendedor identicamente — `(49,10k)` e `(42,31k)` so se distinguem pela
  cor de fundo. Isso e falha de acessibilidade E de robustez: um print em
  escala de cinza, um monitor mal calibrado ou um daltonico perdem o dado.
  Aqui o sinal vem no texto, sempre, e a cor e o TERCEIRO portador.

* **Unidade fixa por coluna.** Uma coluna nao alterna entre `1.240` e
  `1,2k` conforme a magnitude: comparar duas linhas exigiria converter de
  cabeca. Quem escolhe a unidade e o painel, uma vez, para a coluna toda.

* **Digitos estaveis separados dos vivos.** `5.08`+`6,5`: o prefixo vai em
  `--text-muted` e o sufixo em `--text-primary`, para o olho pousar no que
  muda. O corte NAO e chutado — sai da propria grade de precos (ver
  `n_chars_vivos`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fluxopro.core.eventos import PriceGrid

MENOS = "−"
"""U+2212 MINUS SIGN, nao o hifen-menos do teclado.

Numa fonte monoespacada o hifen tem a mesma largura, mas fica na altura
errada (baixo e curto) e some ao lado de digitos. O menos tipografico
alinha com a barra do `+`, o que importa quando as duas linhas estao
empilhadas numa coluna."""

MAIS = "+"


def _agrupar_milhar(digitos: str) -> str:
    """`1240` -> `1.240`. Separador pt-BR, sem depender de `locale`.

    `locale` e estado global do processo e varia por maquina; num painel de
    trading isso seria a mesma tela mostrando numeros diferentes em duas
    maquinas do mesmo escritorio.
    """
    if len(digitos) <= 3:
        return digitos
    partes = []
    while len(digitos) > 3:
        partes.append(digitos[-3:])
        digitos = digitos[:-3]
    partes.append(digitos)
    return ".".join(reversed(partes))


def formatar_inteiro(valor: int) -> str:
    """Inteiro sem sinal forcado — para quantidade, que nao tem direcao."""
    return _agrupar_milhar(str(abs(valor))) if valor >= 0 else MENOS + _agrupar_milhar(str(-valor))


def formatar_sinalizado(valor: int | float, casas: int = 0) -> str:
    """`+1.240` / `−1.240` / `0`.

    Zero sai SEM sinal: `+0` sugeriria compra marginal onde nao ha nada, e
    o zero de delta e um estado com significado proprio (equilibrio), nao
    um positivo pequeno.
    """
    if casas == 0:
        n = int(round(valor))
        if n == 0:
            return "0"
        corpo = _agrupar_milhar(str(abs(n)))
    else:
        if abs(valor) < 0.5 / (10**casas):
            return "0," + "0" * casas
        texto = f"{abs(valor):.{casas}f}"
        inteiro, _, dec = texto.partition(".")
        corpo = _agrupar_milhar(inteiro) + "," + dec
    return (MAIS if valor > 0 else MENOS) + corpo


def formatar_percentual(fracao: float, casas: int = 2) -> str:
    """Fracao (0,0034) -> `+0,34%`. Sinal explicito pela mesma regra."""
    return formatar_sinalizado(fracao * 100.0, casas=casas) + "%"


def abreviar(valor: int | float, com_sinal: bool = True) -> str:
    """`+2.400` -> `+2,4k`. SO para a coluna que escolheu essa unidade.

    Existe para barra de ranking, onde o rotulo compete com a barra pelo
    espaco e a comparacao e visual (o comprimento da barra), nao aritmetica.
    Nao usar em coluna de grade: la a unidade fixa manda.
    """
    sinal = ""
    if com_sinal and valor > 0:
        sinal = MAIS
    elif valor < 0:
        sinal = MENOS
    magnitude = abs(valor)
    if magnitude >= 1_000_000:
        corpo = f"{magnitude / 1_000_000:.1f}".replace(".", ",") + "M"
    elif magnitude >= 1_000:
        corpo = f"{magnitude / 1_000:.1f}".replace(".", ",") + "k"
    else:
        corpo = str(int(round(magnitude)))
    return sinal + corpo


def n_digitos_vivos(grid: PriceGrid) -> int:
    """Quantos DIGITOS do fim do preco um unico tick consegue mexer.

    Derivado da grade, nao chutado, e sem olhar o preco corrente — que e o
    ponto. A primeira versao disto media o prefixo comum entre o preco e os
    vizinhos a +-8 ticks: parecia mais principiado e era pior por dois
    motivos. Marcava 4 caracteres como vivos no WDO (`5.0`+`86,5`) quando a
    referencia do produto pede `5.08`+`6,5`; e, perto de uma virada de
    dezena, os vizinhos tinham comprimentos diferentes e o corte saia
    diferente — ou seja, a LARGURA da coluna dependia de qual preco a
    sessao viu primeiro. Coluna que muda de forma sozinha e pior que coluna
    sem corte nenhum.

    A regra aqui: `passo` e o tick medido em unidades do ultimo digito
    exibido (WDO: 0,5 com 1 casa = 5; WIN: 5 com 0 casas = 5). O tick
    alcanca `len(str(passo))` digitos, e o `+1` e o vai-um — somar 5 a
    `...6,5` muda tambem a unidade. Da 2 digitos para os dois instrumentos,
    que sao `6,5` e `30`.
    """
    passo = round(grid.tick_size * (10 ** grid.decimals))
    return len(str(max(1, passo))) + 1


def n_chars_vivos(grid: PriceGrid, ticks: int) -> int:
    """Idem, mas em CARACTERES do texto ja formatado.

    Separador decimal e ponto de milhar ocupam caractere sem serem digito;
    contar em digitos e converter aqui evita que `5.086,5` e `141.230`
    precisem de regra propria.
    """
    texto = _texto_preco(grid, ticks)
    faltam = n_digitos_vivos(grid)
    chars = 0
    for ch in reversed(texto):
        chars += 1
        if ch.isdigit():
            faltam -= 1
            if faltam == 0:
                break
    return min(chars, len(texto))


def _texto_preco(grid: PriceGrid, ticks: int) -> str:
    preco = grid.to_price(ticks)
    if grid.decimals == 0:
        return _agrupar_milhar(str(int(round(preco))))
    texto = f"{preco:.{grid.decimals}f}"
    inteiro, _, dec = texto.partition(".")
    return _agrupar_milhar(inteiro) + "," + dec


def formatar_preco(grid: PriceGrid, ticks: int) -> tuple[str, str]:
    """`(estavel, vivo)` — `('5.08', '6,5')`.

    Concatenados dao o preco completo; o painel pinta o primeiro em
    `--text-muted` e o segundo em `--text-primary`. A parte apagada e
    redundante (esta contida no numero inteiro que o olho ja leu), que e a
    condicao de §3.2 para usar `--text-muted`.
    """
    texto = _texto_preco(grid, ticks)
    vivos = n_chars_vivos(grid, ticks)
    corte = len(texto) - vivos
    return texto[:corte], texto[corte:]


def preco_completo(grid: PriceGrid, ticks: int) -> str:
    return _texto_preco(grid, ticks)


def formatar_hora_ns(timestamp_ns: int) -> str:
    """`14:32:07,412` — hora local, milissegundo separado por virgula.

    Milissegundo importa: no tape, dois negocios no mesmo segundo sao a
    diferenca entre uma ordem grande fatiada e duas decisoes distintas.
    """
    segundos, resto = divmod(timestamp_ns, 1_000_000_000)
    momento = datetime.fromtimestamp(segundos, tz=timezone.utc).astimezone()
    return momento.strftime("%H:%M:%S") + "," + f"{resto // 1_000_000:03d}"


def formatar_duracao_s(segundos: float) -> str:
    """`4,2 s` / `320 ms` — para o badge de atraso do feed (§3.5)."""
    if segundos < 1.0:
        return f"{segundos * 1000:.0f} ms"
    return f"{segundos:.1f}".replace(".", ",") + " s"


def formatar_latencia_ms(ms: float) -> str:
    if ms < 10.0:
        return f"{ms:.1f}".replace(".", ",") + "ms"
    return f"{ms:.0f}ms"
