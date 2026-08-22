#!/usr/bin/env python
"""Mede quanto de um TRAÇO sobrevive ao canal, caixa a caixa.

    python scripts/retencao.py design/retrato_composicao.png \\
        --caixa "escala:1150,168,90,14" --caixa "veredito:1400,140,80,18"

`scripts/transmissao.py` produz a imagem degradada; este script responde a
pergunta que ela levanta e não resolve: **o que exatamente se perdeu, e onde.**

## De onde isto veio

Um crítico deste projeto inventou a medida no meio de uma auditoria, para
provar uma alegação que nenhuma inspeção a olho resolveria. Ele mediu, por
região, a energia média do Laplaciano — a quantidade de borda — antes e
depois da recompressão, e achou o seguinte:

| região | retenção |
|---|---|
| escala `±3,2k` | **17%** |
| veredito `▲ +2,4k` que ela qualifica | 32% |
| régua de ticks | **27%** |
| badge `§ S/ REGISTRO 1/5` | 35% |
| tarja de carimbo | **47%** |

Em três bandas a **ressalva reteve menos que o veredito que ela qualifica** —
que é a lei do canal deste produto, medida em número em vez de afirmada.

Virou script porque uma medida que vive na cabeça de um auditor tem de ser
redescoberta a cada rodada, e porque o número que ela produz é o que
transforma "acho que ficou ilegível" em "reteve 17% contra 32% do veredito".

## Por que Laplaciano, e o que ele NÃO mede

Compressão com perdas ataca alta frequência: é a borda de um glífo de 10px
que ela joga fora primeiro, não a área chapada de um bloco. A energia do
Laplaciano é justamente uma medida de alta frequência local, então a queda
dela é um proxy direto do que a recompressão levou.

O que ele **não** mede: se o texto ficou LEGÍVEL. Retenção alta com traço
deslocado ainda pode ser ilegível, e — pior e observado neste projeto —
retenção média pode produzir um número que **sobrevive errado**: um `±3,2k`
que vira mush lido como `12,2k` não sumiu, mentiu. Escala que desaparece é
perda; escala que sobrevive errada é defeito. Nenhuma métrica de energia
distingue os dois casos; para isso só olhando.

Então este script mede **exposição ao risco**, não legibilidade. Retenção
baixa numa caixa que carrega ressalva é motivo para ir olhar, e é motivo
suficiente para reprovar um desenho — porque a lei do produto não pede que a
ressalva seja legível a duras penas, e sim que ela viaje **no mesmo portador
do dado que qualifica**.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scripts.transmissao import ESCALA_PADRAO, QUALIDADE_PADRAO, degradar  # noqa: E402


def _cinza(imagem: QImage) -> tuple[list[float], int, int]:
    """Luminância por pixel, em lista plana. Sem numpy: a dependência não
    existe no projeto e a conta é rodada em algumas dezenas de caixas, não
    por quadro."""
    convertida = imagem.convertToFormat(QImage.Format.Format_Grayscale8)
    largura, altura = convertida.width(), convertida.height()
    bits = convertida.constBits()
    passo = convertida.bytesPerLine()
    plano = [0.0] * (largura * altura)
    for y in range(altura):
        base = y * passo
        destino = y * largura
        for x in range(largura):
            plano[destino + x] = float(bits[base + x])
    return plano, largura, altura


def energia_de_traco(imagem: QImage, caixa: tuple[int, int, int, int]) -> float:
    """Magnitude média do Laplaciano dentro da caixa.

    Kernel de 4 vizinhos. Bordas da caixa entram com o vizinho recortado, o
    que subestima levemente a energia — igual nos dois lados da comparação,
    então a RAZÃO, que é o que interessa, não sofre.
    """
    x0, y0, largura_caixa, altura_caixa = caixa
    plano, largura, altura = _cinza(imagem)
    x1 = min(largura, x0 + largura_caixa)
    y1 = min(altura, y0 + altura_caixa)
    x0, y0 = max(0, x0), max(0, y0)
    if x1 - x0 < 3 or y1 - y0 < 3:
        raise SystemExit(f"caixa pequena demais depois do recorte: {caixa}")

    soma = 0.0
    n = 0
    for y in range(y0 + 1, y1 - 1):
        linha = y * largura
        acima = (y - 1) * largura
        abaixo = (y + 1) * largura
        for x in range(x0 + 1, x1 - 1):
            centro = plano[linha + x]
            lap = (
                plano[linha + x - 1]
                + plano[linha + x + 1]
                + plano[acima + x]
                + plano[abaixo + x]
                - 4.0 * centro
            )
            soma += abs(lap)
            n += 1
    return soma / n if n else 0.0


def _caixa(texto: str) -> tuple[str, tuple[int, int, int, int]]:
    nome, _, numeros = texto.partition(":")
    partes = [p.strip() for p in numeros.split(",")]
    if len(partes) != 4:
        raise argparse.ArgumentTypeError(
            f"caixa invalida: {texto!r} (use nome:x,y,largura,altura)"
        )
    return nome, tuple(int(p) for p in partes)  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("origem", type=Path)
    p.add_argument(
        "--caixa",
        type=_caixa,
        action="append",
        required=True,
        metavar="NOME:X,Y,L,A",
        help="regiao a medir; repita para varias",
    )
    p.add_argument("--escala", type=float, default=ESCALA_PADRAO)
    p.add_argument("--qualidade", type=int, default=QUALIDADE_PADRAO)
    p.add_argument(
        "--par",
        action="append",
        default=[],
        metavar="RESSALVA=VEREDITO",
        help=(
            "afirma a lei do canal: a ressalva tem de reter ao menos tanto "
            "quanto o veredito que ela qualifica. Repita para varios pares."
        ),
    )
    args = p.parse_args(argv)

    QApplication([])
    original = QImage(str(args.origem))
    if original.isNull():
        raise SystemExit(f"nao consegui abrir {args.origem}")
    destino = args.origem.with_name(args.origem.stem + "_retencao.png")
    degradada, _ = degradar(args.origem, destino, args.escala, args.qualidade)

    retencao: dict[str, float] = {}
    # Uma casa decimal, e não zero. Com arredondamento inteiro, 31,8% e 32,3%
    # imprimem os dois "32%" e o veredito de violação fica parecendo bug do
    # script. Número que não explica a própria conclusão é o defeito que este
    # produto inteiro existe para não cometer.
    print(f"{'regiao':<34} {'antes':>8} {'depois':>8} {'retencao':>9}")
    for nome, caixa in args.caixa:
        antes = energia_de_traco(original, caixa)
        depois = energia_de_traco(degradada, caixa)
        razao = (depois / antes) if antes else 0.0
        retencao[nome] = razao
        print(f"{nome:<34} {antes:8.2f} {depois:8.2f} {razao*100:7.1f}%")

    problemas = 0
    for par in args.par:
        ressalva, _, veredito = par.partition("=")
        if ressalva not in retencao or veredito not in retencao:
            raise SystemExit(f"par {par!r} cita caixa que nao foi medida")
        margem = (retencao[veredito] - retencao[ressalva]) * 100
        if margem <= 0:
            continue
        problemas += 1
        # `MARGINAL` porque a medida tem ruído próprio: a caixa é desenhada à
        # mão, o kernel recorta nas bordas, e o JPEG é determinístico mas não
        # uniforme. Sob ~2 pontos, o veredito é "vá olhar", não "está errado" —
        # dizer o contrário seria emitir do script o mesmo oráculo sem margem
        # que ele foi escrito para caçar na tela.
        grau = "MARGINAL" if margem < 2.0 else "VIOLADA"
        print(
            f"\nLEI DO CANAL {grau}: '{ressalva}' retem "
            f"{retencao[ressalva]*100:.1f}% e o veredito '{veredito}' que "
            f"ela qualifica retem {retencao[veredito]*100:.1f}% "
            f"(margem {margem:.1f} pp). "
            "A transmissao entrega a conclusao e come a ressalva."
        )

    if args.par and not problemas:
        print("\nTodos os pares: a ressalva retem ao menos tanto quanto o veredito.")
    print(
        "\nRetencao mede EXPOSICAO, nao legibilidade — e nao distingue "
        "'sumiu' de 'sobreviveu errado'. Para isso, olhe "
        f"{destino}."
    )
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
