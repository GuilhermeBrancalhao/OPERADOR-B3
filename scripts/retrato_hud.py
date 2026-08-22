"""Retrato PNG do HUD de contexto e do ranking de players.

Adaptado de `scripts/retrato.py`. Quatro diferencas que valem nota:

* **Nada de `QT_QPA_PLATFORM=offscreen`.** O plugin offscreen carrega ZERO
  familias de fonte e todo glifo sai como caixa vazia — um retrato que so
  mostra que a geometria existe. Aqui roda na plataforma nativa.

* **O instante do retrato e escolhido pelo motor, nao pelo relogio.** O
  simulador pode terminar com o farol em `NENHUM`, e um retrato de um farol
  apagado nao mostra o painel: mostra o silencio. Entao o script guarda,
  DENTRO da thread da fonte (que e onde o motor roda, sem corrida), o melhor
  instante da sessao — estagio mais avancado primeiro, maior pressao na
  janela como desempate. Sinal, saldo do dia, pressao da janela e ranking sao
  todos do MESMO momento; nao ha costura de dois instantes.

* **As corretoras sao sinteticas.** `dados/simulador.py` nao preenche
  `buyer_broker`/`seller_broker` — quem preenche e o replay de gravacao real.
  Para que o ranking mostre alguma coisa, este script retagueia cada negocio
  com um participante de um elenco FICTICIO (`SIM 01`..`SIM 20`), sorteado com
  peso Zipf para dar a cauda longa que um ranking de verdade tem. Nomes reais
  de corretora nao entram aqui por politica do projeto, e um ranking de nomes
  inventados que PARECEM reais seria pior que um rotulo obviamente sintetico.

* **A ressalva vai CARIMBADA NA IMAGEM, e nao no `stdout`.** Este script
  calibra os limiares do motor e fabrica os players; com os defaults
  embarcados, os mesmos dados dariam `SEM CONFLUÊNCIA / LATERAL` no lugar de
  `CONFIRMADO / DIRECIONAL`. Uma nota impressa no terminal nao viaja com o
  arquivo: o PNG circula sozinho, e sozinho ele afirmaria uma coisa que nao e
  verdade com os cortes de producao. A tarja e amarela (`ALERT`), tem 44px em
  duas linhas, e usa texto escuro sobre fundo saturado — o par de maior
  contraste da tela — e por isso e o ULTIMO elemento a morrer no canal, nao o
  primeiro. E ela **nao trunca**: a segunda linha encolhe a fonte ate caber
  (`_maior_que_cabe`), porque uma ressalva cortada pela metade continua
  parecendo uma frase inteira. Ver `scripts/transmissao.py`.

Uso:
    python scripts/retrato_hud.py [saida.png] [--sem-cor]
"""

import dataclasses
import random
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

from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados  # noqa: E402
from fluxopro.app.montagem import montar  # noqa: E402
from fluxopro.core.eventos import Trade  # noqa: E402
from fluxopro.microestrutura.perfil_player import PerfilPlayer  # noqa: E402
from fluxopro.motor.sinais import ConfigMotorSinais  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.dom import PainelDOM  # noqa: E402
from fluxopro.ui.paineis.hud import (  # noqa: E402
    ORDEM_ESTAGIOS,
    PainelHUD,
    PainelPlayers,
    contexto_do_sinal,
    players_de_perfil,
    pressao_da_janela,
)
from fluxopro.ui.paineis.strips import StripRodape, StripTopo  # noqa: E402
from fluxopro.ui.paineis.tape import PainelTape  # noqa: E402
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402

ALTURA_TARJA = 44
DOMINANCIA_PRODUCAO = ConfigMotorSinais().dominancia_minima
"""Lido do proprio default, e nao digitado: se alguem recalibrar o motor de
producao, a tarja passa a dizer o corte novo sem que ninguem lembre dela."""


def _maior_que_cabe(texto: str, largura: int):
    """A ressalva NAO pode truncar — F8 vale para ela tambem.

    Truncar a ressalva e o pior modo de falha possivel desta tarja: a frase
    que sobra continua parecendo completa, e o leitor nunca sabe que faltou
    pedaco. Entao a fonte encolhe ate caber, e o piso de 10px existe porque
    abaixo disso nao adianta caber."""
    for tamanho in range(13, 9, -1):
        fonte = tokens.fonte_ui(tamanho, 500)
        if QFontMetrics(fonte).horizontalAdvance(texto) <= largura:
            return fonte
    return tokens.fonte_ui(10, 500)


class TarjaRessalva(QWidget):
    """A ressalva, carimbada na propria imagem.

    Nao e um `PainelDenso` de proposito: nao pertence ao produto, pertence ao
    retrato. Se um dia virar peca de produto (a faixa de `REPLAY` de §3.5 e o
    mesmo objeto), ela migra para `ui/paineis/` com relogio e regiao suja.
    """

    def __init__(self, titulo: str, detalhe: str) -> None:
        super().__init__()
        self.titulo = titulo
        self.detalhe = detalhe
        self.setFixedHeight(ALTURA_TARJA)

    def paintEvent(self, evento) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), tokens.ALERT)
        # Texto ESCURO sobre ambar saturado: 12,34:1 pelo teste de tokens, o
        # par de maior contraste disponivel. Texto claro sobre ambar seria
        # bonito e ilegivel depois da recompressao.
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


saida = "design/retrato_hud.png"
for arg in sys.argv[1:]:
    if not arg.startswith("--"):
        saida = arg
sem_cor = "--sem-cor" in sys.argv
paleta = tokens.PALETA_SEM_COR if sem_cor else tokens.PALETA_COR

app = QApplication([])
cfg = ConfigOperacao(
    symbol="WDOV26",
    fonte=FonteDados.SIMULADOR,
    simulador=ConfigSimulador(seed=11, n_eventos=30_000, taxa_eventos_s=500.0),
    # Sinal por NEGOCIO, e nao so na mudanca de estagio. Em operacao o default
    # esta certo (nao inundar a trilha de eventos); para escolher o instante do
    # retrato, precisamos ver todos os instantes — com `True`, uma sessao que
    # nunca sai de `NENHUM` entrega UM sinal, o do primeiro negocio, e o
    # retrato sairia do instante menos informativo que existe.
    emitir_apenas_mudanca_de_estagio=False,
    # Motor CALIBRADO para o simulador, e isto vai CARIMBADO NA IMAGEM.
    # `dados/simulador.py` e um passeio aleatorio equilibrado: a dominancia
    # fica em ~0,52 e NUNCA cruza o corte de 0,70 da metodologia. Com o
    # default, o farol do retrato ficaria em `NENHUM` para sempre — o painel
    # mostraria o silencio do simulador, nao o proprio comportamento.
    # Nada aqui e fabricado na tela: sao os campos que `ConfigMotorSinais`
    # existe para expor ("nenhum limiar cravado no corpo — tudo calibravel
    # pelo usuario"), deslocados para a faixa que ESTE gerador de dados
    # ocupa. Num pregao de verdade os defaults valem.
    #
    # E a HISTERESE fica intacta (`persistencia_minima_*` nos defaults, 3
    # negocios e 0,5 s). Baixar o corte de dominancia move o motor para a
    # faixa do gerador; desligar a persistencia seria outra coisa — seria
    # deixar passar o ruido que a persistencia existe para filtrar, e um
    # `CONFIRMADO` obtido assim nao seria um estagio, seria um pixel.
    motor=ConfigMotorSinais(
        faixa_lateral_ate=0.505,
        faixa_pre_direcional_ate=0.515,
        dominancia_minima=0.525,
        faixa_maxima_conviccao_desde=0.60,
        magnitude_relativa_minima=0.20,
        janela_dominancia_ns=5_000_000_000,
        janela_micro_ns=3_000_000_000,
        margem_regiao_ticks=6,
    ),
)

ref: dict = {}
_RANK = {e: i for i, e in enumerate(ORDEM_ESTAGIOS)}
melhor: dict = {"rank": -1, "pressao": -1}

# Elenco ficticio. Peso Zipf (1/k) para a cauda longa que um ranking real tem
# — sem isso as vinte barras sairiam do mesmo tamanho e o painel nao provaria
# nada sobre ordenacao.
ELENCO = tuple("SIM %02d" % (k + 1) for k in range(20))
PESOS = tuple(1.0 / (k + 1) for k in range(len(ELENCO)))
_sorteio = random.Random(11)
perfil_sintetico = PerfilPlayer(cfg.symbol)


def ao_sinal(sinal):
    """Roda na thread da FONTE — que e exatamente onde queremos ler o motor.

    Ler `sessao.agressao` do lado do Qt seria corrida com o produtor. Aqui o
    retrato de um instante e montado no proprio instante, sem lock."""
    ref["ponte"].registrar_evento(sinal)
    sessao = ref["sessao"]
    rank = _RANK.get(sinal.estagio, 0)
    pressao = abs(sessao.agressao.saldo_agressao) if sessao.agressao else 0
    # Estagio primeiro, pressao como desempate: um farol aceso vale mais que
    # uma barra longa, mas entre dois instantes do mesmo estagio o retrato
    # merece o mais informativo.
    if (rank, pressao) <= (melhor["rank"], melhor["pressao"]):
        return
    taxa, volume = pressao_da_janela(sessao.agressao) if sessao.agressao else (0.5, 0)
    melhor.update(
        rank=rank,
        pressao=pressao,
        sinal=sinal,
        saldo_dia=sessao.delta.delta_sessao if sessao.delta else 0,
        volume_comprador_dia=sessao.delta.volume_comprador_sessao if sessao.delta else 0,
        volume_vendedor_dia=sessao.delta.volume_vendedor_sessao if sessao.delta else 0,
        taxa_janela=taxa,
        volume_janela=volume,
        nao_atribuido=sessao.delta.volume_nao_atribuido_sessao if sessao.delta else 0,
        comprador_dia=sessao.delta.volume_comprador_sessao if sessao.delta else 0,
        vendedor_dia=sessao.delta.volume_vendedor_sessao if sessao.delta else 0,
        players=players_de_perfil(perfil_sintetico, top_n=20),
    )


m = montar(cfg, ao_sinal=ao_sinal, ao_deteccao=lambda e: ref["ponte"].registrar_evento(e))


def _retaguear(trade: Trade) -> None:
    """Da um par de participantes ao negocio e alimenta o perfil sintetico."""
    comprador = _sorteio.choices(ELENCO, weights=PESOS)[0]
    vendedor = _sorteio.choices(ELENCO, weights=PESOS)[0]
    if vendedor == comprador:
        vendedor = ELENCO[(ELENCO.index(comprador) + 1) % len(ELENCO)]
    perfil_sintetico.ao_trade(
        dataclasses.replace(trade, buyer_broker=comprador, seller_broker=vendedor)
    )


m.barramento.assinar(Trade, _retaguear)
ponte = PonteFluxo(m.barramento)
ref["ponte"] = ponte
ref["sessao"] = m.sessao

tarja = TarjaRessalva(
    "RETRATO SINTÉTICO — DADOS DE SIMULADOR, NÃO DE PREGÃO",
    "Motor calibrado para o gerador: dominância mínima %s em vez de %s  ·  "
    "players fictícios SIM 01-20  ·  com os cortes de produção esta mesma "
    "sessão leria SEM CONFLUÊNCIA / LATERAL."
    % (
        f"{cfg.motor.dominancia_minima:.3f}".replace(".", ","),
        f"{DOMINANCIA_PRODUCAO:.2f}".replace(".", ","),
    ),
)

topo = StripTopo(cfg.symbol, cfg.price_grid(), paleta=paleta)
topo.definir_modo("SIMULADOR")
dom = PainelDOM(cfg.price_grid(), paleta=paleta)
tape = PainelTape(cfg.price_grid(), paleta=paleta)
hud = PainelHUD(paleta=paleta)
players = PainelPlayers(paleta=paleta)
rodape = StripRodape()

coluna_contexto = QWidget()
coluna_contexto.setFixedWidth(520)
vertical = QVBoxLayout(coluna_contexto)
vertical.setContentsMargins(0, 0, 0, 0)
vertical.setSpacing(1)
vertical.addWidget(hud)
vertical.addWidget(players, 1)

corpo = QWidget()
horizontal = QHBoxLayout(corpo)
horizontal.setContentsMargins(0, 0, 0, 0)
horizontal.setSpacing(1)
horizontal.addWidget(dom, 3)
horizontal.addWidget(tape, 2)
horizontal.addWidget(coluna_contexto)

janela = QWidget()
janela.setWindowTitle("FluxoPro — contexto")
qpal = janela.palette()
qpal.setColor(QPalette.ColorRole.Window, tokens.BG_BASE)
janela.setPalette(qpal)
janela.setAutoFillBackground(True)
pilha = QVBoxLayout(janela)
pilha.setContentsMargins(0, 0, 0, 0)
pilha.setSpacing(1)
pilha.addWidget(tarja)
pilha.addWidget(topo)
pilha.addWidget(corpo, 1)
pilha.addWidget(rodape)
janela.resize(1360, 780)
janela.show()
tape.definir_filtro(5)

# Numero FIXO de eventos, e nao um relogio de parede: um retrato que depende
# de quantos negocios couberam em 4 s sai diferente a cada execucao, e um
# retrato irreproduzivel nao serve de evidencia. Aqui a mesma seed da sempre
# a mesma tela.
thread = threading.Thread(target=m.fonte.iniciar, daemon=True)
thread.start()
limite = time.perf_counter() + 60.0
while thread.is_alive() and time.perf_counter() < limite:
    retrato = ponte.ler()
    topo.aplicar(retrato)
    dom.aplicar(retrato.livro, retrato.ultimo_preco)
    tape.aplicar(retrato.novos_trades)
    rodape.aplicar(retrato, dom.p95_ms(), len(ponte.drenar_eventos()))
    app.processEvents()
m.fonte.parar()
thread.join(timeout=5)
for _ in range(4):
    retrato = ponte.ler()
    topo.aplicar(retrato)
    dom.aplicar(retrato.livro, retrato.ultimo_preco)
    tape.aplicar(retrato.novos_trades)
    rodape.aplicar(retrato, dom.p95_ms(), len(ponte.drenar_eventos()))
    app.processEvents()

sinal_retratado = melhor.get("sinal")
hud.aplicar(
    contexto_do_sinal(
        sinal_retratado,
        saldo_dia=melhor.get("saldo_dia", 0),
        volume_comprador_dia=melhor.get("comprador_dia", 0),
        volume_vendedor_dia=melhor.get("vendedor_dia", 0),
        taxa_compra_janela=melhor.get("taxa_janela", 0.5),
        volume_janela=melhor.get("volume_janela", 0),
        volume_nao_atribuido=melhor.get("nao_atribuido", 0),
    )
)
players.aplicar(melhor.get("players") or players_de_perfil(perfil_sintetico, top_n=20))

for _ in range(6):
    for painel in (dom, tape, topo, rodape, hud, players):
        painel._quadro()
    app.processEvents()

janela.grab().save(saida)
estagio = sinal_retratado.estagio.value if sinal_retratado else "NENHUM (nao houve sinal)"
print(
    "%s | %d negocios | farol %s | saldo dia %s | janela %.0f%% de %s | "
    "HUD p95 %.3f ms | players p95 %.3f ms"
    % (
        saida,
        m.sessao.contadores.n_trades_bus,
        estagio,
        melhor.get("saldo_dia", 0),
        melhor.get("taxa_janela", 0.5) * 100,
        melhor.get("volume_janela", 0),
        hud.p95_ms(),
        players.p95_ms(),
    )
)
print("tarja carimbada na imagem: " + tarja.titulo + " | " + tarja.detalhe)
m.sessao.finalizar()
