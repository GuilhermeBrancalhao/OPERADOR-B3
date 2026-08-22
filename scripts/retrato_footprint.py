"""Retrato PNG do footprint, do perfil lateral e do delta acumulado.

Adaptado de `scripts/retrato_hud.py`. Quatro notas que valem tanto quanto o
codigo:

* **Nada de `QT_QPA_PLATFORM=offscreen`.** O plugin offscreen carrega ZERO
  familias de fonte e todo glifo sai como caixa vazia — um retrato que so
  mostra que a geometria existe. Aqui roda na plataforma nativa do Windows.

* **As tres pecas sao montadas como a janela vai monta-las**, com os DOIS
  eixos compartilhados por identidade de objeto: `PainelPerfil` recebe o
  `EixoPreco` do footprint e `PainelDeltaAcumulado` recebe o `EixoTempo`. Se o
  retrato tivesse eixos proprios, ele nao provaria nada sobre a composicao —
  provaria so que tres paineis sabem desenhar sozinhos.

* **A calibragem vai CARIMBADA NA IMAGEM, e nao no `stdout`.** O candle do
  produto e de um minuto; a 500 eventos por segundo simulados, uma sessao de
  retrato caberia em dois candles e a grade sairia com duas colunas. Entao o
  bucket e encurtado — e essa e uma decisao que muda o que a tela mostra.
  Uma nota impressa no terminal nao viaja com o arquivo: o PNG circula
  sozinho. A tarja e amarela (`ALERT`), tem 44px e usa texto escuro sobre
  fundo saturado — o par de maior contraste da tela, e por isso o ULTIMO
  elemento a morrer no canal. Os numeros dela sao LIDOS das configuracoes,
  nunca digitados.

* **A tarja nao trunca.** A segunda linha encolhe a fonte ate caber
  (`_maior_que_cabe`), porque uma ressalva cortada pela metade continua
  parecendo uma frase inteira.

Uso:
    python scripts/retrato_footprint.py [saida.png] [--sem-cor]
"""

import sys
import threading
import time

sys.path.insert(0, ".")
sys.setswitchinterval(0.001)

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QFontMetrics, QPainter, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from fluxopro.analytics.delta import ConfigDelta  # noqa: E402
from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados  # noqa: E402
from fluxopro.app.montagem import montar  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.delta_acumulado import (  # noqa: E402
    PainelDeltaAcumulado,
    derivar_delta,
)
from fluxopro.ui.paineis.footprint import PainelFootprint, derivar_footprint  # noqa: E402
from fluxopro.ui.paineis.perfil import PainelPerfil, derivar_perfil  # noqa: E402

ALTURA_TARJA = 44
TIMEFRAME_PRODUCAO_NS = ConfigOperacao().timeframe_ns
"""Lido do proprio default, e nao digitado: se alguem recalibrar o produto, a
tarja passa a dizer o corte novo sem que ninguem lembre dela."""

TIMEFRAME_RETRATO_NS = 5_000_000_000


def _maior_que_cabe(texto: str, largura: int):
    """A ressalva NAO pode truncar — F8 vale para ela tambem."""
    for tamanho in range(13, 9, -1):
        fonte = tokens.fonte_ui(tamanho, 500)
        if QFontMetrics(fonte).horizontalAdvance(texto) <= largura:
            return fonte
    return tokens.fonte_ui(10, 500)


class TarjaRessalva(QWidget):
    """A ressalva, carimbada na propria imagem.

    Nao e um `PainelDenso` de proposito: nao pertence ao produto, pertence ao
    retrato.
    """

    def __init__(self, titulo: str, detalhe: str) -> None:
        super().__init__()
        self.titulo = titulo
        self.detalhe = detalhe
        self.setFixedHeight(ALTURA_TARJA)

    def paintEvent(self, evento) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), tokens.ALERT)
        # Texto ESCURO sobre ambar saturado: 12,34:1 pelo teste de tokens.
        painter.setPen(tokens.BG_BASE)
        util = self.width() - 24
        painter.setFont(tokens.fonte_ui(14, 700))
        painter.drawText(
            QRect(12, 4, util, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.titulo,
        )
        painter.setFont(_maior_que_cabe(self.detalhe, util))
        painter.drawText(
            QRect(12, 22, util, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.detalhe,
        )
        painter.end()


def _duracao(ns: int) -> str:
    segundos = ns / 1_000_000_000
    if segundos >= 60:
        return f"{segundos / 60:g} min".replace(".", ",")
    return f"{segundos:g} s".replace(".", ",")


saida = "design/retrato_footprint.png"
for arg in sys.argv[1:]:
    if not arg.startswith("--"):
        saida = arg
sem_cor = "--sem-cor" in sys.argv
paleta = tokens.PALETA_SEM_COR if sem_cor else tokens.PALETA_COR

app = QApplication([])
cfg = ConfigOperacao(
    symbol="WDOV26",
    fonte=FonteDados.SIMULADOR,
    simulador=ConfigSimulador(
        seed=11, n_eventos=62_000, taxa_eventos_s=500.0, volatilidade=0.35
    ),
    # Bucket encurtado para o gerador. O simulador avanca o relogio em
    # `1/taxa_eventos_s` por evento: com o candle de producao (1 min), esta
    # sessao inteira caberia em poucas colunas e a grade nao mostraria o que
    # ela existe para mostrar. Vai carimbado na imagem.
    timeframe_ns=TIMEFRAME_RETRATO_NS,
    delta=ConfigDelta(timeframe_ns=TIMEFRAME_RETRATO_NS),
    # O footprint, o perfil e o delta NAO consomem microestrutura, detectores,
    # motor nem metodologia. Desligar os quatro nao muda um pixel destes
    # paineis e faz a sessao de retrato caber em segundos em vez de minutos —
    # e um retrato irreproduzivel por timeout nao serve de evidencia.
    ligar_microestrutura=False,
    ligar_detectores_tape=False,
    ligar_motor=False,
    ligar_metodologia=False,
)

montagem = montar(cfg)
sessao = montagem.sessao

footprint = PainelFootprint(
    cfg.price_grid(),
    paleta=paleta,
    config=cfg.footprint,
    simbolo=cfg.symbol,
    timeframe_ns=cfg.timeframe_ns,
)
perfil = PainelPerfil(
    cfg.price_grid(), footprint.eixo_preco, paleta=paleta, config=cfg.volume_profile
)
delta = PainelDeltaAcumulado(footprint.eixo_tempo, paleta=paleta, config=cfg.delta)

footprint.setFixedHeight(520)
delta.setFixedHeight(200)
perfil.setFixedWidth(200)

esquerda = QWidget()
coluna_esquerda = QVBoxLayout(esquerda)
coluna_esquerda.setContentsMargins(0, 0, 0, 0)
coluna_esquerda.setSpacing(1)
coluna_esquerda.addWidget(footprint)
coluna_esquerda.addWidget(delta)

espacador = QWidget()
espacador.setFixedHeight(201)
direita = QWidget()
coluna_direita = QVBoxLayout(direita)
coluna_direita.setContentsMargins(0, 0, 0, 0)
coluna_direita.setSpacing(0)
coluna_direita.addWidget(perfil)
coluna_direita.addWidget(espacador)

corpo = QWidget()
horizontal = QHBoxLayout(corpo)
horizontal.setContentsMargins(0, 0, 0, 0)
horizontal.setSpacing(1)
horizontal.addWidget(esquerda, 1)
horizontal.addWidget(direita)

tarja = TarjaRessalva(
    "RETRATO SINTÉTICO — DADOS DE SIMULADOR, NÃO DE PREGÃO",
    "Candle de %s em vez de %s, para caber colunas na tela  ·  microestrutura, "
    "detectores, motor e metodologia desligados (não alimentam estes painéis)  ·  "
    "com os cortes de produção esta mesma sessão daria %d coluna(s)."
    % (
        _duracao(cfg.timeframe_ns),
        _duracao(TIMEFRAME_PRODUCAO_NS),
        max(
            1,
            int(cfg.simulador.n_eventos / cfg.simulador.taxa_eventos_s * 1e9)
            // TIMEFRAME_PRODUCAO_NS,
        ),
    ),
)

janela = QWidget()
janela.setWindowTitle("FluxoPro — footprint, perfil e delta acumulado")
qpal = janela.palette()
qpal.setColor(QPalette.ColorRole.Window, tokens.BG_BASE)
janela.setPalette(qpal)
janela.setAutoFillBackground(True)
pilha = QVBoxLayout(janela)
pilha.setContentsMargins(0, 0, 0, 0)
pilha.setSpacing(1)
pilha.addWidget(tarja)
pilha.addWidget(corpo, 1)
janela.resize(1360, ALTURA_TARJA + 520 + 200 + 4)
janela.show()


def tick() -> None:
    """UM dono do relogio de dados, como em `ui/janela.py`.

    A ORDEM importa e e a mesma que a janela tem de usar: o footprint
    primeiro, porque e ele que move os dois eixos; o perfil depois, porque
    consome a faixa de preco que o footprint acabou de definir; o delta por
    ultimo, porque le o numero de colunas."""
    footprint.aplicar(
        derivar_footprint(
            sessao.footprint, footprint.inicio_vivo_ns, footprint.eixo_tempo.n_colunas
        )
    )
    perfil.aplicar(derivar_perfil(sessao.perfil_sessao, footprint.faixa_visivel))
    delta.aplicar(
        derivar_delta(sessao.delta, delta.inicio_vivo_ns, footprint.eixo_tempo.n_colunas)
    )


thread = threading.Thread(target=montagem.fonte.iniciar, daemon=True)
thread.start()
limite = time.perf_counter() + 120.0
while thread.is_alive() and time.perf_counter() < limite:
    tick()
    app.processEvents()
montagem.fonte.parar()
thread.join(timeout=5)

for _ in range(6):
    tick()
    for painel in (footprint, perfil, delta):
        painel._quadro()
    app.processEvents()

janela.grab().save(saida)
preenchidas = sum(1 for c in footprint.colunas_visiveis if c is not None)
print(
    "%s | %d negocios | %d/%d colunas | %d niveis | POC %s (%d lotes) | "
    "VA %s-%s | delta %s | escala %d | eixos alinhados: %s | "
    "footprint p95 %.3f ms · perfil %.3f ms · delta %.3f ms"
    % (
        saida,
        sessao.contadores.n_trades_bus,
        preenchidas,
        footprint.eixo_tempo.n_colunas,
        footprint.eixo_preco.n_linhas,
        perfil.leitura.poc,
        perfil.leitura.volume_poc,
        perfil.leitura.val,
        perfil.leitura.vah,
        delta.texto_acumulado(),
        delta.escala,
        delta.alinhado,
        footprint.p95_ms(),
        perfil.p95_ms(),
        delta.p95_ms(),
    )
)
# As caixas de `scripts/retencao.py` saem da GEOMETRIA DO PROPRIO PAINEL, e
# nao de um recorte medido a mao no PNG. A docstring daquele script avisa que
# a caixa desenhada a mao e uma das fontes de ruido da medida; aqui ela vem do
# mesmo `QRect` que o desenho usou, mapeado para a janela.
ultimo = footprint.eixo_tempo.n_colunas - 1


def _caixa(nome, widget, rect):
    canto = widget.mapTo(janela, rect.topLeft())
    return '"%s:%d,%d,%d,%d"' % (nome, canto.x(), canto.y(), rect.width(), rect.height())


print("caixas para scripts/retencao.py (ressalva=veredito):")
print(
    "  --caixa "
    + _caixa("procedencia_delta", delta, delta.rect_chip_procedencia)
    + " --caixa "
    + _caixa("valor_delta", delta, delta.rect_texto_valor)
)
print(
    "  --caixa "
    + _caixa("limiar_imbalance", footprint, footprint.rect_chip_limiar)
    + " --caixa "
    + _caixa("saldo_num", footprint, footprint.rect_numero_saldo(ultimo))
)
print(
    "  --caixa "
    + _caixa("escala_saldo", footprint, footprint.rect_rotulo_rodape(2))
    + " --caixa "
    + _caixa("saldo_num", footprint, footprint.rect_numero_saldo(ultimo))
)
print("  --par procedencia_delta=valor_delta --par limiar_imbalance=saldo_num")
print(
    "  (escala_saldo NAO e par: `Δ SALDO ±10%` e conteudo REDUNDANTE, nao "
    "ressalva. O fundo de escala e constante do produto — nao se move entre "
    "quadros —, a comparacao entre candles e espacial e simultanea, e o saldo "
    "em lotes esta no mesmo corpo logo acima. Perde-lo no canal custa a "
    "unidade do eixo, nunca a leitura, que e a condicao de §3.2 para conteudo "
    "redundante. E medido mesmo assim, para ficar no registro.)"
)
print("tarja carimbada na imagem: " + tarja.titulo + " | " + tarja.detalhe)
sessao.finalizar()
