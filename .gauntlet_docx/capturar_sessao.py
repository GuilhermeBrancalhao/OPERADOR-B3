"""Retrato do painel com o PREGAO INTEIRO carregado (158 mil negocios reais).

## Por que existe

O caminho normal de retrato (`.gauntlet_docx/capturar.cmd`) roda o replay pelo
pipeline completo — book, microestrutura, detectores de tape, motor. Isso e o
certo para julgar as regioes que dependem do LIVRO (nucleo/decisao, banner,
maker proxy), mas custa caro: medido em 28/08, o replay anda a ~5,5x o tempo
real, entao 2 minutos de parede cobrem ~11 minutos de tape. Um pregao de 9
horas levaria ~1h40 de parede.

Consequencia pratica: qualquer regiao que precise de MUITAS amostras para ter
forma — candle do pregao inteiro, Renko, VAP de sessao — aparecia quase vazia
no retrato, e um critico julgando aquilo estaria julgando a fixture, nao o
produto.

## O que este script faz, e o que ele deliberadamente NAO faz

Le `trades.csv.gz` do dia inteiro e alimenta os agregadores do painel pela
MESMA porta que o produto usa ao vivo (`_registrar_amostra`), negocio a
negocio, na ordem. Candle, Renko, VAP e a serie visual ficam exatamente como
ficariam depois de um pregao inteiro aberto.

Nao reconstroi o livro de ofertas, nao roda detectores de tape nem o motor de
sinais: as regioes alimentadas por MBO/MBP (decisao, evidencias, maker) ficam
no estado "sem dado" de proposito. Para julgar ESSAS, use `capturar.cmd`.

Ou seja: as duas fixtures sao complementares e cada uma e honesta sobre o que
cobre. Nenhuma das duas fabrica dado — as duas leem o mesmo pregao gravado.

    python .gauntlet_docx/capturar_sessao.py saida.png [--timeframe 5|15]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DIA_PADRAO = "2026-08-27"
SIMBOLO_PADRAO = "WDOU26"


def _carregar_trades(caminho: Path):
    abrir = gzip.open if caminho.suffix == ".gz" else open
    with abrir(caminho, "rt", newline="", encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            yield (
                int(linha["timestamp_ns"]),
                int(linha["price"]),
                int(linha["qty"]),
                linha.get("side_agressor", "UNKNOWN"),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saida")
    parser.add_argument("--dia", default=DIA_PADRAO)
    parser.add_argument("--simbolo", default=SIMBOLO_PADRAO)
    parser.add_argument("--timeframe", type=int, default=5, choices=(5, 15))
    parser.add_argument("--vap-timeframe", type=int, default=0, choices=(0, 5, 15))
    parser.add_argument("--largura", type=int, default=1920)
    parser.add_argument("--altura", type=int, default=1080)
    args = parser.parse_args()

    from PySide6.QtGui import QPixmap, QPainter
    from PySide6.QtWidgets import QApplication

    from fluxopro.core.eventos import AgressorSide
    from fluxopro.ui import tema_asg
    from fluxopro.ui.paineis.asg import PainelNexoMercadoASG

    app = QApplication.instance() or QApplication([])

    caminho = RAIZ / "dados" / args.simbolo / args.dia / "trades.csv.gz"
    if not caminho.exists():
        caminho = caminho.with_suffix("")
    if not caminho.exists():
        print(f"sem trades gravados em {caminho}", file=sys.stderr)
        return 1

    painel = PainelNexoMercadoASG()
    painel.resize(args.largura, args.altura)
    painel._timeframe_candles_min = args.timeframe
    painel._vap_timeframe_min = args.vap_timeframe

    # Sem um snapshot de LIVRO o painel baixa, corretamente, o veu
    # "AGUARDANDO PRIMEIRO SNAPSHOT" sobre tudo — e ai nao da para julgar
    # regiao nenhuma. Aplicamos a MESMA fixture sintetica e rotulada que
    # `scripts/painel.py` ja usa para os retratos de estado do produto
    # (`quadro_evidencia_asg`), que se declara na propria imagem como cenario
    # congelado. O tape continua sendo 100% real; so o estado de livro e
    # sintetico, e isso esta escrito na tela.
    #
    # ARMADILHA MEDIDA EM 28/08, corrigida aqui: `aplicar()` NAO e so estado —
    # ele tambem chama `_registrar_amostra` com o preco do snapshot. Como o
    # cenario congelado negocia numa faixa arbitraria (2.543), aquele preco
    # entrava no VAP/Renko/candle como se fosse tape real, e aparecia no perfil
    # do dia como dois niveis fantasma a milhares de ticks da faixa negociada.
    # Isso ja custou uma rodada inteira de critica sobre um defeito inexistente.
    # Aqui o `_registrar_amostra` fica desligado durante a aplicacao do
    # snapshot: o estado (que levanta o veu) entra, a amostra sintetica nao.
    # Depois disto, 100% das amostras dos agregadores sao tape real.
    from scripts.painel import quadro_evidencia_asg
    from fluxopro.ui.paineis.asg import EstadoASG

    registrar_real = painel._registrar_amostra
    painel._registrar_amostra = lambda *a, **k: None
    try:
        painel.aplicar(quadro_evidencia_asg(EstadoASG.REPLAY))
    finally:
        painel._registrar_amostra = registrar_real

    lados = {"BUY": AgressorSide.BUY, "SELL": AgressorSide.SELL}
    n = 0
    for timestamp_ns, preco, qtd, lado in _carregar_trades(caminho):
        painel._registrar_amostra(
            timestamp_ns, preco, 0.0, qtd, lados.get(lado, AgressorSide.UNKNOWN)
        )
        n += 1

    # Mesma porta de pintura que `tests/test_ui_composicao.py` usa: a regiao
    # NEXO nao pinta por `paintEvent` proprio, quem aloca os retangulos e
    # delega e `desenhar(painter, regiao)`.
    from PySide6.QtCore import QRect

    pixmap = QPixmap(args.largura, args.altura)
    pixmap.fill(tema_asg.NEXO_FUNDO)
    painter = QPainter(pixmap)
    try:
        painel.desenhar(painter, QRect(0, 0, args.largura, args.altura))
    finally:
        painter.end()

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(destino))
    print(f"{destino} | {n} negocios | candle {args.timeframe}M | vap {args.vap_timeframe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
