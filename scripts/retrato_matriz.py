"""Retrato da MATRIZ DE ESTADO, com motor real rodando. Adaptado de `retrato.py`.

Uso:  python scripts/retrato_matriz.py [saida.png] [--sem-cor] [--segundos N]

Nao usar `QT_QPA_PLATFORM=offscreen`: o plugin offscreen carrega ZERO
familias de fonte e todo glifo sai como caixa vazia. Para um retrato de
verdade e preciso a plataforma nativa do Windows.
"""
import os
import sys
import threading
import time

if "--offscreen" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")
sys.setswitchinterval(0.001)

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados
from fluxopro.app.montagem import montar
from fluxopro.ui import tokens
from fluxopro.ui.paineis.matriz import PainelMatriz, derivar
from fluxopro.ui.paineis.strips import StripTopo
from fluxopro.ui.ponte import PonteFluxo

saida = "design/retrato_matriz.png"
segundos = 8.0
for i, arg in enumerate(sys.argv[1:], start=1):
    if arg.endswith(".png"):
        saida = arg
    elif arg == "--segundos":
        segundos = float(sys.argv[i + 1])
sem_cor = "--sem-cor" in sys.argv
paleta = tokens.PALETA_SEM_COR if sem_cor else tokens.PALETA_COR

app = QApplication([])
cfg = ConfigOperacao(
    symbol="WDOV26",
    fonte=FonteDados.SIMULADOR,
    simulador=ConfigSimulador(seed=11, n_eventos=10**9, taxa_eventos_s=900.0),
)
ref: dict = {}
montagem = montar(
    cfg,
    ao_sinal=lambda e: ref["p"].registrar_evento(e),
    ao_deteccao=lambda e: ref["p"].registrar_evento(e),
)
ponte = PonteFluxo(montagem.barramento)
ref["p"] = ponte

janela = QMainWindow()
janela.setWindowTitle("FluxoPro — matriz de estado")
central = QWidget()
coluna = QVBoxLayout(central)
coluna.setContentsMargins(0, 0, 0, 0)
coluna.setSpacing(0)
topo = StripTopo(cfg.symbol, cfg.price_grid(), paleta=paleta)
topo.definir_modo("SIMULADOR")
matriz = PainelMatriz(
    cfg.price_grid(), densidade=tokens.PADRAO, paleta=paleta, config=cfg.motor
)
coluna.addWidget(topo)
coluna.addWidget(matriz, 1)
janela.setCentralWidget(central)
# Altura fechada nas bandas: 28 (strip) + 24 + 40 + 40 + 16 + 36 + 88 +
# 16 + 14 + 10x18. Um retrato com sobra embaixo mediria a janela, nao o
# painel. Encolheu de 720 para 482 na rodada 3, junto com o teto de slots.
janela.resize(620, 482)
janela.show()

leitura = None


def tick() -> None:
    """UM dono do relogio de dados, como em `ui/janela.py`."""
    global leitura
    retrato = ponte.ler()
    topo.aplicar(retrato)
    ultimo_sinal = None
    deteccoes = []
    for evento in ponte.drenar_eventos():
        if hasattr(evento, "estagio"):
            ultimo_sinal = evento  # so o ULTIMO importa: e estado, nao historia
        else:
            deteccoes.append(evento)
    leitura = derivar(
        ultimo_sinal, montagem.sessao.agressao, montagem.sessao.delta, anterior=leitura
    )
    matriz.aplicar(leitura, deteccoes)


thread = threading.Thread(target=montagem.fonte.iniciar, daemon=True)
thread.start()
fim = time.perf_counter() + segundos
while time.perf_counter() < fim:
    tick()
    app.processEvents()
montagem.fonte.parar()
thread.join(timeout=3)

for _ in range(8):
    tick()
    for painel in (topo, matriz):
        painel._quadro()
    app.processEvents()

janela.grab().save(saida)
print(
    "%s | %d negocios | %d deteccoes | estagio %s | dominancia %.3f | matriz p95 %.2f ms"
    % (
        saida,
        montagem.sessao.contadores.n_trades_bus,
        matriz.n_deteccoes,
        leitura.estagio.value,
        leitura.dominancia,
        matriz.p95_ms(),
    )
)
montagem.sessao.finalizar()
