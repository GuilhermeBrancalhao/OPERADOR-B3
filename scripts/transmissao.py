#!/usr/bin/env python
"""Degrada um retrato como uma transmissao de tela degradaria — parametro V6.

    python scripts/transmissao.py design/retrato_fase1.png

O briefing pericial de 22/08 registra que a entrega publica do dashboard alvo
e por **captura e transmissao**, e nao por aplicativo instalado. Isso deixa de
ser trivia e vira restricao de design: a tela nao e consumida nos pixels que
o `QPainter` desenhou, e sim depois de reescala e recompressao com perdas.

Um numero de 11px que passa no monitor pode virar borrao no destino. E o
inverso da otimizacao normal de UI densa: densidade que sobrevive ao monitor
nao e a mesma que sobrevive ao canal.

## O que este script NAO e

Nao e um simulador do codec do Zoom. Nao ha modelo de bitrate, de keyframe,
de movimento, nem do H.264. E um **proxy deliberadamente grosseiro** de duas
perdas que qualquer transmissao de tela impoe:

1. **Reescala** — a janela do espectador quase nunca tem a resolucao do
   emissor, e o reescalonamento e feito com interpolacao.
2. **Quantizacao com perdas** — compressao que ataca justamente bordas de
   alto contraste em area pequena, que e a descricao exata de um digito de
   11px sobre fundo escuro.

Chamar isso de "teste de Zoom" seria mentir sobre o instrumento. O que ele
mede honestamente e: *o que sobra do meu texto depois de perder resolucao e
detalhe*. Um painel que falha aqui falha em qualquer canal; um que passa nao
esta provado em nenhum canal especifico.

Por isso o veredito final continua sendo de um leitor humano ou de um
critico olhando o PNG degradado — o script produz a evidencia, nao a nota.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ESCALA_PADRAO = 0.72
"""Fracao da largura original na tela do espectador.

Um emissor de 1280 de largura numa janela compartilhada de ~920px. Nao e
um numero do protocolo; e uma reducao plausivel e conservadora — telas
partilhadas em reuniao costumam sofrer mais que isso, nao menos."""

QUALIDADE_PADRAO = 40
"""Qualidade JPEG. Baixa de proposito: o objetivo do teste e achar o que
QUEBRA, nao produzir um arquivo bonito. Um painel que continua legivel a 40
tem folga real; um calibrado para passar raspando a 85 nao prova nada."""


def degradar(
    origem: Path,
    destino: Path,
    escala: float = ESCALA_PADRAO,
    qualidade: int = QUALIDADE_PADRAO,
) -> tuple[QImage, int]:
    """Reescala para baixo, recomprime, e volta ao tamanho original.

    A volta ao tamanho original e o ponto: sem ela, a comparacao seria entre
    uma imagem grande e uma pequena, e o olho perdoaria a pequena. Voltando,
    as duas ficam no mesmo enquadramento e a perda aparece como o que ela e —
    borrao no lugar de digito.
    """
    imagem = QImage(str(origem))
    if imagem.isNull():
        raise SystemExit(f"nao consegui abrir {origem}")

    largura, altura = imagem.width(), imagem.height()
    reduzida = imagem.scaled(
        max(1, int(largura * escala)),
        max(1, int(altura * escala)),
        aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
        mode=Qt.TransformationMode.SmoothTransformation,
    )

    # Ida e volta pelo JPEG em disco: e o que introduz a quantizacao. Fazer
    # em memoria daria o mesmo resultado, mas o arquivo intermediario e util
    # para inspecionar o tamanho em bytes, que e a medida do quanto foi jogado
    # fora.
    intermediario = destino.with_suffix(".jpg")
    reduzida.save(str(intermediario), "JPEG", qualidade)
    bytes_intermediarios = intermediario.stat().st_size

    recarregada = QImage(str(intermediario))
    devolvida = recarregada.scaled(
        largura,
        altura,
        aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
        mode=Qt.TransformationMode.SmoothTransformation,
    )
    devolvida.save(str(destino), "PNG")
    return devolvida, bytes_intermediarios


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("origem", type=Path)
    p.add_argument("--destino", type=Path, default=None)
    p.add_argument("--escala", type=float, default=ESCALA_PADRAO)
    p.add_argument("--qualidade", type=int, default=QUALIDADE_PADRAO)
    args = p.parse_args(argv)

    destino = args.destino or args.origem.with_name(
        args.origem.stem + "_transmissao.png"
    )
    QApplication([])
    _, bytes_jpg = degradar(args.origem, destino, args.escala, args.qualidade)
    originais = args.origem.stat().st_size
    print(
        f"{destino} | escala {args.escala:.2f} qualidade {args.qualidade} | "
        f"{originais/1024:.0f} KB -> {bytes_jpg/1024:.0f} KB no canal "
        f"({100*bytes_jpg/originais:.0f}% do original)"
    )
    print(
        "Veredito e de quem OLHA o arquivo: os numeros criticos (preco, "
        "quantidade, delta) continuam legiveis? O script nao responde isso."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
