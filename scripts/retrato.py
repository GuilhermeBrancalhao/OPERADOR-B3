"""Gera um PNG da janela do painel, sem tela — para revisao e documentacao."""
import os, sys, threading, time
# Sem QT_QPA_PLATFORM=offscreen de proposito: o plugin offscreen carrega
# ZERO familias de fonte, e todo glifo sai como caixa vazia. Para um
# retrato de verdade e preciso a plataforma nativa.
if "--offscreen" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")
sys.setswitchinterval(0.001)
from PySide6.QtWidgets import QApplication
from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados
from fluxopro.app.montagem import montar
from fluxopro.ui import tokens
from fluxopro.ui.janela import JanelaFluxo
from fluxopro.ui.ponte import PonteFluxo

saida = sys.argv[1] if len(sys.argv) > 1 else "design/retrato_fase1.png"
sem_cor = "--sem-cor" in sys.argv

app = QApplication([])
cfg = ConfigOperacao(symbol="WDOV26", fonte=FonteDados.SIMULADOR,
                     simulador=ConfigSimulador(seed=11, n_eventos=10**9, taxa_eventos_s=500.0))
ref = {}
m = montar(cfg, ao_sinal=lambda e: ref['p'].registrar_evento(e),
           ao_deteccao=lambda e: ref['p'].registrar_evento(e))
p = PonteFluxo(m.barramento); ref['p'] = p
j = JanelaFluxo(p, cfg.symbol, cfg.price_grid(), modo="SIMULADOR",
                paleta=tokens.PALETA_SEM_COR if sem_cor else tokens.PALETA_COR)
j.resize(1280, 800)
j.show()
j.tape.definir_filtro(5)

th = threading.Thread(target=m.fonte.iniciar, daemon=True); th.start()
fim = time.perf_counter() + 3.0
while time.perf_counter() < fim:
    app.processEvents()
m.fonte.parar(); th.join(timeout=3)

for _ in range(6):
    j._tick()
    for painel in (j.dom, j.tape, j.topo, j.rodape):
        painel._quadro()
    app.processEvents()

j.grab().save(saida)
print("%s | %d negocios | DOM p95 %.2f ms | %d quadros" % (
    saida, m.sessao.contadores.n_trades_bus, j.dom.p95_ms(), j.dom.quadros_desenhados))
m.sessao.finalizar()
