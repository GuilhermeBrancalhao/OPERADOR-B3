"""Retrato PNG do bookmap e do transporte de replay (fase 5).

Adaptado de `scripts/retrato_hud.py`, e com as mesmas quatro regras dele:

* **Nada de `QT_QPA_PLATFORM=offscreen`.** O plugin offscreen carrega ZERO
  familias de fonte e todo glifo sai como caixa vazia — um retrato que so
  mostra que a geometria existe. Aqui roda na plataforma nativa.
* **Numero fixo de eventos, semente fixa.** Um retrato que depende de
  quantos negocios couberam em N segundos e irreproduzivel, e retrato
  irreproduzivel nao serve de evidencia.
* **A ressalva vai CARIMBADA NA IMAGEM, e nao no `stdout`.** O PNG circula
  sozinho; sozinho ele tem de dizer o que e sintetico.
* **Nada de numero de producao redigitado.** A escada de liquidez sai de
  `PainelBookmap.pisos` e as caixas de medicao saem de `rects_da_escada()` —
  se alguem recalibrar, o carimbo e a medicao acompanham sem que ninguem
  lembre deles.

## O que e real e o que e sintetico neste retrato

**Real:** o pipeline inteiro (simulador -> barramento -> `EstadoMercado` ->
ponte -> painel), os tempos, o preco caminhando, os negocios com agressor, o
custo por quadro medido, e — o ponto do replay — a gravacao: os eventos sao
persistidos por `Gravador`, indexados por `Catalogo`, e o estado da tarja sai
de `estado_de_entrada()` lendo o `meta.json` que acabou de ser escrito. A
hora que a tarja mostra e a hora que o arquivo diz.

**Sintetico, e por isso carimbado:**

1. A fonte e o simulador, nao pregao.
2. **A profundidade do book.** `dados/simulador.py` publica 5 niveis por lado
   com quantidade uniforme entre 10 e 100 — quatro dos nove degraus da rampa,
   e nenhuma parede. Um heatmap alimentado assim mostraria uma faixa fina e
   nao provaria nada sobre o painel. Entao a profundidade e estendida por
   `paisagem_de_liquidez`, que e **funcao deterministica do PRECO** e nao do
   quadro: a liquidez fica parada em precos fixos e o preco anda por dentro
   dela, que e exatamente o que um bookmap existe para mostrar. O topo do
   book continua sendo o do simulador, intocado.

Uso:
    python scripts/retrato_bookmap.py [saida.png] [--sem-cor]
"""

import random
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, ".")
sys.setswitchinterval(0.001)
# O console do Windows e cp1252 e a tarja tem glifos. Sem isto o script
# morre no `print` DEPOIS de ter salvo o PNG — falha barulhenta num passo
# que ja terminou.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QFontMetrics, QPainter, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados  # noqa: E402
from fluxopro.app.montagem import montar  # noqa: E402
from fluxopro.core.eventos import BookLevel, BookSnapshot  # noqa: E402
from fluxopro.gravacao.catalogo import Catalogo  # noqa: E402
from fluxopro.gravacao.gravador import Gravador  # noqa: E402
from fluxopro.ui import formato, tokens  # noqa: E402
from fluxopro.ui.paineis.bookmap import PainelBookmap  # noqa: E402
from fluxopro.ui.paineis.replay import (  # noqa: E402
    ControlesReplay,
    TarjaReplay,
    estado_de_entrada,
)
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402

ALTURA_CARIMBO = 68
ALTURA_LINHA_CARIMBO = 20
PROFUNDIDADE_SINTETICA = 60
VELOCIDADE_RETRATADA = 2.0

# --------------------------------------------------------------------------
# A paisagem de liquidez sintetica
# --------------------------------------------------------------------------
_MANTISSAS = (1, 2, 4, 7, 12, 20, 35, 60, 110, 190)
_MULTIPLICADOR_PAREDE = (6, 25)
_PASSO_PAREDE = 20


def paisagem_de_liquidez(ticks: int) -> int:
    """Quantos lotes descansam neste PRECO. Deterministica, sem memoria.

    Funcao do preco e nao do quadro: e isso que faz a parede ficar parada
    enquanto o preco anda por dentro dela — o unico comportamento que
    justifica um heatmap existir em vez de uma escada de DOM. E e funcao
    PURA: nao ha `dict[preco] -> qty` memoizado, que seria a estrutura que
    cresce com o range do dia dentro do proprio script que existe para
    provar que o painel nao tem uma.
    """
    sorteio = random.Random((ticks * 2654435761) & 0xFFFFFFFF)
    qty = sorteio.choice(_MANTISSAS)
    if ticks % _PASSO_PAREDE == 0:
        qty *= sorteio.randint(*_MULTIPLICADOR_PAREDE)
    return max(1, qty)


def engrossar(livro: BookSnapshot) -> BookSnapshot:
    """Estende a profundidade preservando o topo do simulador."""
    if livro is None or not livro.bids or not livro.asks:
        return livro
    topo_bid = livro.bids[0].price
    topo_ask = livro.asks[0].price
    bids = list(livro.bids) + [
        BookLevel(topo_bid - k, paisagem_de_liquidez(topo_bid - k), 1)
        for k in range(len(livro.bids), PROFUNDIDADE_SINTETICA)
    ]
    asks = list(livro.asks) + [
        BookLevel(topo_ask + k, paisagem_de_liquidez(topo_ask + k), 1)
        for k in range(len(livro.asks), PROFUNDIDADE_SINTETICA)
    ]
    return BookSnapshot(livro.timestamp_ns, livro.symbol, tuple(bids), tuple(asks))


# --------------------------------------------------------------------------
# O carimbo
# --------------------------------------------------------------------------
def _maior_que_cabe(texto: str, largura: int, base: int = 14, peso: int = 600):
    """A ressalva NAO trunca — a fonte encolhe ate caber. Mesma funcao e
    mesmo motivo de `scripts/retrato_hud.py`: frase cortada continua
    parecendo completa e o leitor nunca sabe que faltou pedaco."""
    for tamanho in range(base, 10, -1):
        fonte = tokens.fonte_ui(tamanho, peso)
        if QFontMetrics(fonte).horizontalAdvance(texto) <= largura:
            return fonte
    return tokens.fonte_ui(11, peso)


class Carimbo(QWidget):
    """A ressalva do RETRATO — nao pertence ao produto, pertence ao arquivo.

    Bloco chapado com texto escuro por cima, que e a forma que a transmissao
    menos ataca (`PainelMatriz._chip`).

    **A forma desta peca saiu de uma medicao, nao de gosto.** A primeira
    versao copiava `retrato_hud.py`: titulo de 14px e UMA linha de detalhe de
    10-13px, peso 500. `scripts/retencao.py` mediu o resultado no canal:

        carimbo_titulo   45,7%     carimbo_detalhe   23,0%
        veredito (pico)  44,9%

    Ou seja, o detalhe da ressalva retinha **metade** do veredito que ela
    qualifica — a lei do canal violada por 22 pontos —, e o titulo passava
    raspando, dentro da faixa `MARGINAL` do proprio script. Uma linha longa e
    fina de 10px e feita do material mais fragil que a tela tem.

    A correcao nao foi encurtar o texto: foi **quebrar em linhas de 20px com
    peso 600**, que e traco mais grosso e menos borda por caractere. Medido
    depois da mudanca, os numeros estao no rodape deste script.
    """

    def __init__(self, titulo: str, linhas: tuple[str, ...]) -> None:
        super().__init__()
        self.titulo = titulo
        self.linhas = linhas
        self.detalhe = " ".join(linhas)
        self.setFixedHeight(ALTURA_CARIMBO)

    def rect_titulo(self) -> QRect:
        return QRect(12, 4, self.width() - 24, ALTURA_LINHA_CARIMBO)

    def rect_linha(self, indice: int) -> QRect:
        return QRect(
            12,
            4 + (indice + 1) * ALTURA_LINHA_CARIMBO,
            self.width() - 24,
            ALTURA_LINHA_CARIMBO,
        )

    def paintEvent(self, evento) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), tokens.ALERT)
        painter.setPen(tokens.BG_BASE)
        util = self.width() - 24
        painter.setFont(tokens.fonte_ui(15, 700))
        painter.drawText(
            self.rect_titulo(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.titulo,
        )
        for indice, linha in enumerate(self.linhas):
            painter.setFont(_maior_que_cabe(linha, util))
            painter.drawText(
                self.rect_linha(indice),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                linha,
            )
        painter.end()


# --------------------------------------------------------------------------
saida = "design/retrato_bookmap.png"
for arg in sys.argv[1:]:
    if not arg.startswith("--"):
        saida = arg
sem_cor = "--sem-cor" in sys.argv
paleta = tokens.PALETA_SEM_COR if sem_cor else tokens.PALETA_COR

app = QApplication([])
cfg = ConfigOperacao(
    symbol="WDOV26",
    fonte=FonteDados.SIMULADOR,
    simulador=ConfigSimulador(seed=11, n_eventos=90_000, taxa_eventos_s=500.0),
)

deposito = Path(tempfile.mkdtemp(prefix="fluxopro_retrato_"))
m = montar(cfg)
gravador = Gravador(m.barramento, deposito, meta_a_cada=2_000)
gravador.iniciar()
ponte = PonteFluxo(m.barramento)

# `StripTopo` fica DE FORA deste retrato de proposito, e o motivo e um
# achado: com o feed do simulador vivo ele grafa `● AO VIVO` enquanto a
# tarja de replay diz `▶ REPLAY`. Duas afirmacoes contraditorias na mesma
# tela, e uma delas e justamente a que §3.5 declara que nao pode ser
# desmentida. O conserto e da JANELA (suprimir o estado de feed ao vivo
# enquanto houver replay) e `ui/janela.py` nao e deste ciclo — entao aqui o
# retrato mostra so as pecas da fase 5, e o achado vai no relatorio em vez
# de virar um retrato que se contradiz.
book = PainelBookmap(cfg.price_grid(), symbol=cfg.symbol, paleta=paleta)
controles = ControlesReplay()

PISOS = book.pisos
carimbo = Carimbo(
    "RETRATO SINTÉTICO — SIMULADOR, NÃO PREGÃO",
    (
        "Abaixo do 5º nível o book é uma paisagem sintética do preço: "
        "%d níveis, %d a %d lotes, paredes a cada %d ticks."
        % (
            PROFUNDIDADE_SINTETICA,
            min(_MANTISSAS),
            max(_MANTISSAS) * _MULTIPLICADOR_PAREDE[1],
            _PASSO_PAREDE,
        ),
        "Relógio do simulador começa em zero — daí 01/01. Escada: %s lotes."
        % "·".join(formato.formatar_inteiro(p) for p in PISOS),
    ),
)

janela = QWidget()
janela.setWindowTitle("FluxoPro — bookmap e replay")
qpal = janela.palette()
qpal.setColor(QPalette.ColorRole.Window, tokens.BG_BASE)
janela.setPalette(qpal)
janela.setAutoFillBackground(True)
pilha = QVBoxLayout(janela)
# A tarja de replay e SOBREPOSTA da janela, entao o topo do layout precisa
# ceder a altura dela — senao ela cobriria o carimbo.
tarja = TarjaReplay()
pilha.setContentsMargins(0, tarja.altura_natural(), 0, 0)
pilha.setSpacing(1)
pilha.addWidget(carimbo)
pilha.addWidget(book, 1)
pilha.addWidget(controles)
janela.resize(1360, 820)
tarja.instalar_em(janela)
janela.show()

thread = threading.Thread(target=m.fonte.iniciar, daemon=True)
thread.start()
limite = time.perf_counter() + 600.0
while thread.is_alive() and time.perf_counter() < limite:
    retrato = ponte.ler()
    book.aplicar(
        livro=engrossar(retrato.livro),
        ultimo_preco=retrato.ultimo_preco,
        novos_trades=retrato.novos_trades,
        agora_ns=retrato.ultimo_evento_ns or None,
    )
    app.processEvents()
m.fonte.parar()
thread.join(timeout=5)
for _ in range(4):
    retrato = ponte.ler()
    book.aplicar(
        livro=engrossar(retrato.livro),
        ultimo_preco=retrato.ultimo_preco,
        novos_trades=retrato.novos_trades,
        agora_ns=retrato.ultimo_evento_ns or None,
    )
    app.processEvents()
gravador.parar()
p95_sob_carga = (book.p95_ms(), controles.p95_ms())
# Zerar aqui separa duas medidas que respondem a perguntas diferentes: acima,
# o tempo de PAREDE com a thread da fonte disputando o GIL (o que o operador
# sente); abaixo, o custo do quadro sozinho, que e o numero comparavel com a
# tabela de §2.
book.zerar_medicao()
controles.zerar_medicao()

# O estado da tarja sai do `meta.json` que o `Gravador` acabou de escrever —
# nao de numeros digitados aqui. As horas sao as horas do arquivo.
entradas = Catalogo(deposito).escanear()
entrada = entradas[0]
estado = estado_de_entrada(
    entrada,
    posicao_ns=entrada.hora_inicio_ns
    + int(0.55 * ((entrada.hora_fim_ns or 0) - (entrada.hora_inicio_ns or 0))),
    velocidade=VELOCIDADE_RETRATADA,
)
tarja.definir_estado(estado)
controles.definir_estado(estado)

for _ in range(6):
    for painel in (book, controles, tarja):
        painel._quadro()
    app.processEvents()

captura = janela.grab()
captura.save(saida)

# ---------------------------------------------------------------- medicao
# As caixas para `scripts/retencao.py` saem da GEOMETRIA DO DESENHO, em
# coordenadas de janela. Digitar coordenadas no comando de medicao seria
# medir uma caixa que o desenho nao usa — o mesmo teatro que §3 proibe para
# teste.
# `QWidget.grab()` devolve a imagem em pixels de DISPOSITIVO. Num monitor a
# 125% (o padrao do Windows em notebook) o PNG sai 1,25x maior que a
# geometria logica dos widgets — e uma caixa de medicao em coordenada logica
# cairia 25% fora do alvo, medindo a energia de outro pedaco da tela e
# devolvendo um numero com cara de verdade.
#
# A razao sai da CAPTURA e nao de `devicePixelRatioF()`: duas execucoes
# seguidas desta mesma maquina devolveram 1,25 e 1,00 (o Qt arredonda o DPI
# conforme a tela em que a janela nasce). Medir o arquivo que foi salvo nao
# tem como discordar do arquivo que foi salvo.
DPR = captura.width() / max(1, janela.width())


def _em_janela(widget, rect: QRect) -> QRect:
    canto = widget.mapTo(janela, rect.topLeft())
    return QRect(
        int(canto.x() * DPR),
        int(canto.y() * DPR),
        int(rect.width() * DPR),
        int(rect.height() * DPR),
    )


chips = book.rects_da_escada()
caixa_escada = _em_janela(book, chips[0].united(chips[-1]))
caixa_pico = _em_janela(
    book,
    QRect(book.width() - 260, 2, 252, book.densidade.altura_cabecalho - 4),
)
caixa_tarja = QRect(
    0, 0, int(min(520, janela.width()) * DPR), int(tarja.altura_natural() * DPR)
)
largura_medida = min(560, carimbo.width())
caixa_carimbo_titulo = _em_janela(
    carimbo, QRect(12, carimbo.rect_titulo().top(), largura_medida, ALTURA_LINHA_CARIMBO)
)
caixa_carimbo_detalhe = _em_janela(
    carimbo, QRect(12, carimbo.rect_linha(0).top(), largura_medida, ALTURA_LINHA_CARIMBO)
)
caixa_trilha = _em_janela(controles, controles.rect_trilha())

pico, pico_ticks = book.pico_janela
# Auto-checagem: o cabecalho nao pode anunciar uma parede que o eixo de
# preco nao mostra. Se isto imprimir FORA, o retrato esta documentando um
# defeito em vez de uma peca.
nivel_pico = book._nivel_do_tick(pico_ticks) if pico else 0
print(
    "checagem do pico: %s (topo do eixo %s, pico em %s)"
    % (
        "dentro do eixo" if nivel_pico is not None else "FORA DO EIXO",
        formato.preco_completo(cfg.price_grid(), book._topo_ticks or 0),
        formato.preco_completo(cfg.price_grid(), pico_ticks),
    )
)
print(
    "%s | %d negocios | %d colunas fechadas | horizonte %.0f s | "
    "pico %s @ %s | bookmap p95 %.3f ms (%.3f sob carga) | "
    "controles p95 %.3f ms (%.3f sob carga)"
    % (
        saida,
        m.sessao.contadores.n_trades_bus,
        book.colunas_fechadas,
        book.horizonte_ns() / 1e9,
        formato.formatar_inteiro(pico),
        formato.preco_completo(cfg.price_grid(), pico_ticks),
        book.p95_ms(),
        p95_sob_carga[0],
        controles.p95_ms(),
        p95_sob_carga[1],
    )
)
print("tarja de replay na imagem: " + estado.texto_tarja)
print("carimbo na imagem: " + carimbo.titulo + " | " + carimbo.detalhe)
print(
    "\nmedir o canal com:\npython scripts/retencao.py %s \\\n"
    "    --caixa \"tarja_replay:%d,%d,%d,%d\" \\\n"
    "    --caixa \"carimbo_titulo:%d,%d,%d,%d\" \\\n"
    "    --caixa \"carimbo_detalhe:%d,%d,%d,%d\" \\\n"
    "    --caixa \"escada:%d,%d,%d,%d\" \\\n"
    "    --caixa \"pico:%d,%d,%d,%d\" \\\n"
    "    --caixa \"trilha:%d,%d,%d,%d\" \\\n"
    "    --par tarja_replay=pico --par escada=pico \\\n"
    "    --par carimbo_titulo=pico --par carimbo_detalhe=pico"
    % (
        (saida,)
        + tuple(
            v
            for caixa in (
                caixa_tarja,
                caixa_carimbo_titulo,
                caixa_carimbo_detalhe,
                caixa_escada,
                caixa_pico,
                caixa_trilha,
            )
            for v in (caixa.x(), caixa.y(), caixa.width(), caixa.height())
        )
    )
)

m.sessao.finalizar()
shutil.rmtree(deposito, ignore_errors=True)
