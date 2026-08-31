"""A composicao — uma janela so, e a CADEIA desenhada nela.

`design/direcao_visual.md` §4.1 pede shell + paineis + workspace; o briefing
pericial de 22/08 pede quatro coisas que esta camada, e so ela, pode
entregar:

* **V3 — a cadeia legivel.** `dados de mercado -> processamento -> estado
  derivado -> decisao`. Ate aqui a cadeia existia no codigo (fonte ->
  `SessaoFluxo` -> `MotorSinais` -> `Sinal`) e nao existia na tela: um painel
  bom ao lado de outro painel bom nao e uma cadeia, e uma prateleira. Aqui
  ela vira geometria: o corpo tem QUATRO regioes na ordem da cadeia, e o
  `TrilhoCadeia` do topo tem QUATRO segmentos **alinhados com elas**, cada um
  do tamanho exato da regiao que nomeia. Nomear e alinhar sao a mesma
  operacao — um trilho que nao acompanhasse a largura da coluna seria uma
  legenda, e legenda e o que a §1 cobra da referencia.

* **V5 — sem cromo.** A area de dados nao tem um widget de sistema: nem
  `QSplitter` (o punho e desenhado pelo estilo do SO), nem `QMenuBar`, nem
  `QStatusBar`, nem barra de rolagem. Os separadores sao `QFrame` de 1px
  pintados com `tokens.BORDER`, e todo o resto e `QPainter` sobre backing
  store. A tela e consumida por captura: o que aparecer de cromo aparece na
  transmissao.

* **V6 — sobreviver ao canal.** A lei medida desta rodada e que **o canal
  preserva o veredito e apaga a ressalva** (`scripts/transmissao.py`). Entao
  nesta camada nenhuma ressalva viaja em corpo menor que o dado que ela
  qualifica: as ressalvas do `PainelRegras` sao CHIPS — bloco preenchido com
  texto escuro, a forma que a recompressao nao apaga —, e a ressalva de
  sessao e uma FAIXA de 44px em ambar saturado no topo da janela.

  A rodada 2 estreitou a lei num ponto que faltava: **escala e unidade sao
  ressalva.** A medicao de canal mostrou tres bandas em que a escala retinha
  menos traco que o veredito que ela qualifica — e uma delas nem sumia,
  sobrevivia ERRADA (`±3,2k` lido como `12,2k`), que e pior que sumir. Aqui
  a regra virou construcao: `7% de 4.096` e `0,525 (prod. 0,70)` saem num
  `drawText` so, com a mesma fonte e a mesma caneta, e
  `tests/test_ui_composicao.py::escala_nao_e_mais_fraca` reprova quem
  separar os dois em portadores de forca diferente.

* **O carimbo.** `FaixaRessalva` existe para que calibracao e dado fabricado
  viajem DENTRO da imagem. Quem monta a janela passa o texto; `scripts/
  painel.py` o deriva comparando `ConfigMotorSinais` com os defaults de
  producao, campo a campo, sem redigitar nenhum numero.

## O que a composicao decidiu colocar em primeiro plano

O critico da rodada anterior observou que a interface dava espaco ao fluxo
que `fluxopro/metodologia/regras.py` **nao** avaliza e nenhum as regras que
ele avaliza. A composicao responde com area: a coluna da DECISAO carrega o
`PainelRegras`, que lista as 13 familias do registro com quantas de cada uma
o produto implementa, e os limiares EM VIGOR com o rotulo de procedencia de
cada um. Quem olhar a tela ve, sem abrir arquivo nenhum, que `exaustao` e
0/1 `S/ FONTE` — e que a banda de deteccoes onde ela aparece nao tem o mesmo
lastro que a banda de dominancia.

## Um relogio de dados

Continua valendo, e agora com quatro consumidores em vez de dois:
`PonteFluxo.ler()` esvazia o buffer, entao a janela le UMA vez por quadro e
distribui o MESMO `Instantaneo` para todos. Painel nenhum chama `ler`
sozinho. Os relogios de DESENHO seguem sendo de cada painel
(`base/painel_denso.py`) — o de dados decide o que a tela sabe, o de desenho
decide quanto custa mostrar.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from fluxopro.analytics.delta import ConfigDelta
from fluxopro.app.config import ConfigOperacao
from fluxopro.core.eventos import PriceGrid
from fluxopro.metodologia.confianca import Confianca
from fluxopro.metodologia.regras import REGRAS
from fluxopro.motor.sinais import ConfigMotorSinais
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import INTERVALO_QUADRO_MS, PainelDenso
from fluxopro.ui.paineis.dom import PainelDOM
from fluxopro.ui.paineis.hud import (
    TAXA_NEUTRA,
    PainelHUD,
    PainelPlayers,
    contexto_do_sinal,
    players_de_perfil,
    pressao_da_janela,
)
from fluxopro.ui.paineis import matriz as matriz_mod
from fluxopro.ui.paineis.matriz import (
    MARCA_REGRA,
    ROTULO_CONFIANCA,
    LeituraMotor,
    PainelMatriz,
    derivar,
    regras_do_campo,
)
from fluxopro.ui.paineis.bookmap import PainelBookmap
from fluxopro.ui.paineis.asg import (
    ConfiancaASG,
    ContextoBrutoASGSnapshot,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    MatrizASGSnapshot,
    ProcessamentoASGSnapshot,
    ProcedenciaASG,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASG,
    WorkspaceASGSnapshot,
    cor_estado as cor_estado_asg,
    rotulo_estado as rotulo_estado_asg,
)
from fluxopro.ui.paineis.nexo_ai_vertical import PainelNexoAIVertical
from fluxopro.ui.paineis.delta_acumulado import PainelDeltaAcumulado, derivar_delta
from fluxopro.ui.paineis.footprint import PainelFootprint, derivar_footprint
from fluxopro.ui.paineis.metodo import PainelMetodo
from fluxopro.ui.paineis.metodo import altura_natural as altura_natural_metodo
from fluxopro.ui.paineis.perfil import PainelPerfil, derivar_perfil
from fluxopro.ui.paineis.replay import ControlesReplay, EstadoReplay, TarjaReplay
from fluxopro.ui.paineis.strips import StripRodape, StripTopo, cor_do_estado
from fluxopro.ui.paineis.tape import PainelTape
from fluxopro.ui.ponte import CAPACIDADE_TAPE, EstadoFeed, Instantaneo, PonteFluxo
from fluxopro.ui.trilha import Nivel, PainelTrilha, TrilhaEventos
from fluxopro.ui.workspace import (
    ELO_DA_DOCA,
    ELO_FORA,
    N_ELOS,
    TITULO_DA_DOCA,
    WORKSPACES_DE_FABRICA,
    Workspace,
    cortes_da_cadeia,
    folha_de_estilo,
    por_atalho,
    reancorar,
)

ALTURA_FAIXA = 3
"""§3.5: "estado global merece sinal global". A faixa e da JANELA, nao do
painel — desconexao nao e problema do DOM, e de todo mundo."""

ALTURA_TRILHO = 26
"""O trilho da cadeia. Alto o bastante para 12px semibold em `TEXT_PRIMARY`,
que e o corpo que a medicao de `scripts/transmissao.py` mostrou atravessar o
canal sem esforco. Um trilho de 16px com rotulo de 9px seria a peca mais
importante da composicao escrita no unico corpo que morre na transmissao."""

LARGURA_CONDUTO = 120
"""Largura do elo 2.

Eram 96, e a medicao de canal da rodada 2 cobrou os outros 24: `de 4.096` —
a escala do medidor de ocupacao — nao cabia, e a saida barata seria escreve-la
menor que o `8%` que ela qualifica. Essa e exatamente a troca que o canal
pune, entao quem cedeu foi a largura da coluna e nao o corpo da escala."""
ALTURA_RODAPE_CANO = 58
"""Rodape do medidor de ocupacao: rotulo, veredito, escala e descarte.

Era 44 e nao cabia a escala. Aumentar o rodape foi a escolha contra encolher
a escala: a fatia do cano que se perde e desenho, e a escala e argumento."""
ALTURA_RESSALVA = 44
LARGURA_DECISAO = 340

MARGEM = 8

SLOTS_MINIMOS_MATRIZ = 3
"""Quantas deteccoes a banda tem de conseguir mostrar para a composicao
aceitar dar a doca a `PainelMatriz`.

Nasce de um defeito medido, e nao de gosto: no workspace **Revisão** a doca
da matriz chegava aos 260px do `setMinimumSize` do proprio painel, e nessa
altura `matriz.ao_redimensionar` calcula `util < 0` — ZERO slots. O painel
continua desenhando o rotulo `DETECÇÕES 0 MÉTODO · N GENÉRICAS` e a linha de
colunas (`matriz.py:1664`, `_desenhar_deteccoes`, que so retorna DEPOIS de
desenhar as duas), e o que o operador ve e um cabecalho que promete N
deteccoes sobre vao vazio. Banda que reserva cabecalho e nao mostra linha e
pior que banda ausente.

O conserto de dentro (nao mostrar o cabecalho quando nao ha slot, ou pedir
minimo compativel com a propria banda) e de `matriz.py` e nao meu. O que a
composicao pode garantir — e garante — e que nenhum arranjo de fabrica
entregue a essa doca uma altura em que a banda nao caiba: tres linhas e o
menor numero em que a banda ainda e uma LISTA, e nao uma amostra."""


def altura_minima_matriz(
    densidade: tokens.Densidade = tokens.PADRAO,
    slots: int = SLOTS_MINIMOS_MATRIZ,
) -> int:
    """Altura em que `PainelMatriz` ainda abre `slots` linhas de deteccao.

    Derivada das constantes do PROPRIO painel — copiar os numeros aqui seria
    uma segunda geometria, que envelhece no dia em que a matriz mudar uma
    banda de altura e ninguem vier corrigir esta linha."""
    fixas = (
        densidade.altura_cabecalho
        + matriz_mod.ALTURA_ESTAGIO
        + matriz_mod.ALTURA_DOMINANCIA
        + matriz_mod.ALTURA_REGUA
        + matriz_mod.ALTURA_MAGNITUDE
        + matriz_mod.ALTURA_ROTULO
        + 4 * densidade.altura_linha
    )
    banda = (
        matriz_mod.ALTURA_ROTULO
        + matriz_mod.ALTURA_COLUNAS
        + min(slots, matriz_mod.MAX_SLOTS_DETECCAO) * densidade.altura_linha
    )
    return fixas + banda


CARENCIA_PLAYERS_QUADROS = 240
"""Quadros sem NENHUM participante antes de o painel de players se recolher.

~4 s a 62 Hz, e mais que o dobro disso sob carga — o relogio de DADOS
tambem perde quadros quando a fonte inunda, e um numero calibrado no ideal
faz o recolhimento acontecer ou nao dependendo da maquina. Era 400 e o
retrato saiu diferente em duas execucoes seguidas: nao-determinismo em
evidencia e evidencia estragada. A B3 divulga corretora em WDO/WIN; o simulador nao preenche
`buyer_broker`/`seller_broker` e o MT5 tampouco. Manter um painel que a fonte
nunca vai poder preencher ocupando a coluna e pior que recolhe-lo: nao e o
estado VAZIO de §3.5 (que e "ainda nao chegou" e merece a grade desenhada), e
"esta fonte nao tem esse dado". Se um participante aparecer depois, o painel
volta — a decisao e reversivel e se corrige sozinha."""

QUADROS_ENTRE_SONDAGENS = 120
"""Espacamento da sondagem que faz o painel recolhido voltar (~2 s).

Sondar todo quadro reintroduziria o custo que recolher o painel economiza;
sondar nunca faria do recolhimento uma decisao permanente tomada nos
primeiros 6 s de uma sessao que ainda vai durar o pregao inteiro."""


# --------------------------------------------------------------------------
# Adaptadores — o que a janela monta para os paineis, sem correr atras da
# thread da fonte.
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _DeltaDoRetrato:
    """O que `matriz.derivar` espera de um `CumulativeDelta`, vindo do retrato.

    Podia ser `sessao.delta` direto — `scripts/retrato_matriz.py` faz assim —
    mas ler o objeto vivo do lado do Qt e ler enquanto a thread da fonte
    escreve, e a matriz sairia costurada de dois instantes. O `Instantaneo` ja
    traz os TRES numeros (delta, volume, nao atribuido) montados sob o lock,
    no mesmo instante do DOM e do tape. Um adaptador de 3 campos compra
    consistencia que nao existiria de outro jeito.
    """

    delta_sessao: int
    volume_nao_atribuido_sessao: int
    volume_total_sessao: int

    @staticmethod
    def de(retrato: Instantaneo) -> "_DeltaDoRetrato":
        return _DeltaDoRetrato(
            delta_sessao=retrato.delta_sessao,
            volume_nao_atribuido_sessao=retrato.volume_nao_atribuido,
            volume_total_sessao=retrato.volume_sessao,
        )


# O `_separador` de 1px que dividia as colunas saiu com o docking: quem separa
# doca de doca agora e o `QMainWindow::separator`, declarado a partir dos
# tokens em `ui/workspace.folha_de_estilo` — e o argumento que recusava o
# `QSplitter` (punho desenhado pelo estilo do SO, alinhamento dependendo de
# estado nao versionado) esta escrito la, resolvido, em "o conflito docking x
# cadeia".


def _maior_que_cabe(alternativas: tuple[str, ...], largura: int, fonte: QFont) -> str:
    """A primeira alternativa que cabe INTEIRA. Nunca trunca (F8).

    Rotulo cortado pela metade continua parecendo um rotulo inteiro — e a
    fraqueza F8 que §1 cobra da referencia (`Classifi…` colidindo com o
    saldo). Aqui a tela encolhe o VOCABULARIO, nao o texto."""
    metrica = QFontMetrics(fonte)
    for texto in alternativas:
        if metrica.horizontalAdvance(texto) <= largura:
            return texto
    return alternativas[-1]


def _chip(painter: QPainter, rect: QRect, texto: str, fundo: QColor) -> None:
    """Bloco preenchido com texto escuro — a forma que atravessa o canal.

    Copia deliberada do `_chip` de `paineis/matriz.py`, e nao uma variacao:
    ressalva tem UM formato neste produto. A medicao que originou a regra
    esta la; o que importa aqui e que a coluna da DECISAO fale a mesma
    lingua da matriz, senao o operador teria de aprender dois vocabularios
    de procedencia na mesma tela."""
    painter.fillRect(rect, fundo)
    painter.setFont(tokens.fonte_rotulo())
    painter.setPen(tokens.BG_BASE)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)


_GRAVIDADE: dict[Confianca | None, int] = {
    Confianca.CONFIRMADO: 0,
    Confianca.INFERIDO: 1,
    Confianca.IMPRECISO: 2,
    Confianca.AUSENTE_NA_FONTE: 3,
    None: 4,
}
"""Ordem de gravidade — o chip mostra o PIOR elo, nunca a media.

`None` (nenhuma regra cobre) e o PIOR de todos, e nao o melhor, pela mesma
razao que `paineis/matriz.py` da: "olhamos e o registro diz por escrito que a
fonte nao tem isso" e auditavel; "ninguem olhou" e um buraco na auditoria.

A tabela e repetida aqui em vez de importada porque la ela e `_privada` e
`matriz.py` esta em revisao paralela — importar o privado de um painel faria
a composicao quebrar quando o painel se reorganizasse. O acoplamento que
sobra e so pelos nomes PUBLICOS (`ROTULO_CONFIANCA`, `MARCA_REGRA`,
`regras_do_campo`), que sao vocabulario e contrato, nao detalhe."""


def _rotulo_confianca(confianca: Confianca | None) -> str:
    return MARCA_REGRA + " " + ROTULO_CONFIANCA[confianca]


def formatar_limiar(campo: str, valor: object) -> str:
    """`0.70` -> `0,70`; `15_000_000_000` -> `15,0 s`.

    Mora aqui, e nao no painel, porque `scripts/painel.py` precisa da MESMA
    formatacao para montar a ressalva: o carimbo da imagem e a linha do
    painel tem de dizer o mesmo numero com os mesmos digitos, senao o leitor
    tem de decidir em qual acreditar."""
    if campo.endswith("_ns"):
        return formato.formatar_duracao_s(float(valor) / 1e9)  # type: ignore[arg-type]
    if isinstance(valor, float):
        # Tres casas, mas nunca menos de duas: `0,7` ao lado de `0,525` faria
        # dois limiares da mesma grandeza parecerem de precisoes diferentes.
        texto = f"{valor:.3f}"
        if texto.endswith("0"):
            texto = texto[:-1]
        return texto.replace(".", ",")
    return str(valor)


def _cor_da_confianca(confianca: Confianca | None) -> QColor:
    if confianca is Confianca.CONFIRMADO:
        return tokens.OK
    if confianca is None or confianca is Confianca.AUSENTE_NA_FONTE:
        return tokens.ABSORPTION
    return tokens.ALERT


# --------------------------------------------------------------------------
# 0. A ressalva — o carimbo NA IMAGEM
# --------------------------------------------------------------------------
class FaixaRessalva(PainelDenso):
    """Calibracao e dado fabricado, carimbados dentro da propria tela.

    O PNG circula sozinho. Uma nota no `stdout` nao viaja com o arquivo, e
    uma tela que afirma `CONFIRMADO / DIRECIONAL` com o motor recalibrado
    para caber num gerador de dados esta afirmando, sozinha, uma coisa que
    nao e verdade com os cortes de producao.

    Ambar saturado com texto escuro (12,34:1, o par de maior contraste da
    paleta) porque e o ULTIMO elemento a morrer no canal, e nao o primeiro —
    e a segunda linha ENCOLHE a fonte ate caber em vez de truncar, pela mesma
    razao de `_maior_que_cabe`.
    """

    def __init__(self, titulo: str, detalhe: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tokens.ALERT)
        self.titulo = titulo
        self.detalhe = detalhe
        self.setFixedHeight(ALTURA_RESSALVA)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, tokens.ALERT)
        painter.setPen(tokens.BG_BASE)
        util = self.width() - 2 * (MARGEM + 4)
        painter.setFont(tokens.fonte_ui(14, 700))
        painter.drawText(
            QRect(MARGEM + 4, 4, util, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.titulo,
        )
        fonte = tokens.fonte_ui(10, 500)
        for tamanho in range(13, 9, -1):
            candidata = tokens.fonte_ui(tamanho, 500)
            if QFontMetrics(candidata).horizontalAdvance(self.detalhe) <= util:
                fonte = candidata
                break
        painter.setFont(fonte)
        painter.drawText(
            QRect(MARGEM + 4, 22, util, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.detalhe,
        )


# --------------------------------------------------------------------------
# 1. O trilho da cadeia
# --------------------------------------------------------------------------
ETAPAS: tuple[tuple[str, str, str], ...] = (
    ("1 · DADOS DE MERCADO", "1 · DADOS", "DADOS"),
    ("2 · PROCESSAMENTO", "2 · PROC.", "PROC."),
    ("3 · ESTADO DERIVADO", "3 · ESTADO", "ESTADO"),
    ("4 · DECISÃO", "4 · DECISÃO", "DECISÃO"),
)
"""Os quatro elos, do mais longo ao mais curto. Ver `_maior_que_cabe`."""

ROTULO_ARRANJO_LIVRE = "ARRANJO LIVRE · SEM CADEIA"
"""O que o trilho grafa quando o docking desmanchou as quatro colunas."""


class TrilhoCadeia(PainelDenso):
    """Os quatro elos da cadeia, cada um do tamanho da regiao que nomeia.

    **O que ele NAO faz e a decisao mais importante desta peca.** Ele nao
    repete veredito nenhum: nada de `DIRECIONAL 74%` no elo 3 nem de
    `PRÉ-SINAL` no elo 4. A lei medida da rodada e que o canal preserva o
    veredito e apaga a ressalva; um veredito repetido no trilho seria
    exatamente um veredito publicado LONGE da ressalva que o qualifica — a
    regua na matriz, o placar no HUD. O trilho responde ONDE, e o painel
    embaixo responde O QUE, com as ressalvas dele junto.

    Os cortes vem da geometria REAL das colunas (`JanelaFluxo.
    _sincronizar_trilho`), nao de uma copia dos fatores de esticamento: duas
    contas para a mesma largura e a forma mais barata de desalinhar rotulo e
    dado depois do primeiro redimensionamento.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_RAISED)
        self.setFixedHeight(ALTURA_TRILHO)
        self._cortes: tuple[int, int, int] = (0, 0, 0)
        self._motivo = ""

    def definir_cortes(self, cortes: tuple[int, int, int]) -> None:
        if (cortes, "") != (self._cortes, self._motivo):
            self._cortes = cortes
            self._motivo = ""
            self.marcar_tudo_sujo()

    def definir_arranjo_livre(self, motivo: str) -> None:
        """O docking desmanchou a cadeia: o trilho SE ABSTEM de afirma-la.

        Ver `ui/workspace.py`, secao "o conflito docking x cadeia". Quatro
        segmentos desenhados sobre um arranjo que nao tem quatro colunas
        seriam legenda desalinhada, e o proprio modulo argumenta que legenda
        desalinhada e pior que rotulo nenhum: o operador aprende a apontar
        para o lugar errado.
        """
        if motivo != self._motivo:
            self._motivo = motivo
            self.marcar_tudo_sujo()

    @property
    def arranjo_livre(self) -> bool:
        return bool(self._motivo)

    @property
    def motivo(self) -> str:
        return self._motivo

    def segmentos(self) -> tuple[QRect, ...]:
        """Os quatro segmentos, ou UM so quando o arranjo nao e cadeia.

        A cardinalidade e a afirmacao: quem receber uma tupla de 1 sabe que
        nao ha cadeia para apontar, sem ter de ler texto."""
        if self._motivo:
            return (QRect(0, 0, self.width(), self.height()),)
        limites = (0, *self._cortes, self.width())
        return tuple(
            QRect(limites[i], 0, max(0, limites[i + 1] - limites[i]), self.height())
            for i in range(len(ETAPAS))
        )

    def rect_rotulo(self, indice: int) -> QRect:
        """A caixa APERTADA do texto do elo — largura da metrica, nao do
        segmento.

        Existe por causa de uma medicao errada, nao por estetica. O portao de
        canal comparava a retencao de traco do chip de cobertura (230x17 de
        texto denso, energia 94) contra a do SEGMENTO inteiro do elo 1
        (611x26, quase todo fundo, energia 19,6) e acusava violacao de 10,6
        pp. Retencao media de Laplaciano nao compara regiao densa com regiao
        esparsa: o fundo nao tem traco para perder, entao ele so dilui o
        denominador e inflaciona a retencao da caixa grande.

        Comparar TEXTO com TEXTO e a unica forma de o numero significar o que
        o nome dele diz.
        """
        segmento = self.segmentos()[indice]
        if self._motivo:
            return segmento
        fonte = tokens.fonte_ui(12, 600)
        interno = segmento.adjusted(MARGEM + 6, 0, -(MARGEM + 6), 0)
        texto = _maior_que_cabe(ETAPAS[indice], max(0, interno.width()), fonte)
        largura = QFontMetrics(fonte).horizontalAdvance(texto)
        return QRect(interno.left(), segmento.top() + 4, largura + 2, segmento.height() - 8)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        if self._motivo:
            self._desenhar_arranjo_livre(painter)
            return

        fonte = tokens.fonte_ui(12, 600)
        for indice, segmento in enumerate(self.segmentos()):
            if segmento.width() <= 0:
                continue
            interno = segmento.adjusted(MARGEM + 6, 0, -(MARGEM + 6), 0)
            if interno.width() <= 0:
                continue
            painter.setFont(fonte)
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                interno,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _maior_que_cabe(ETAPAS[indice], interno.width(), fonte),
            )
            # A ancora do elo com a coluna: um traco de 2px na base do
            # segmento, exatamente da largura da regiao la embaixo. E o que
            # transforma quatro rotulos numa cadeia apontavel.
            painter.fillRect(
                QRect(segmento.left() + 2, self.height() - 3, segmento.width() - 4, 2),
                tokens.BORDER_STRONG,
            )

        caneta = QPen(tokens.TEXT_SECONDARY, 2)
        painter.setPen(caneta)
        meio = self.height() // 2 - 1
        for x in self._cortes:
            # Seta desenhada, e nao o glifo "›": forma vetorial de 2px
            # atravessa a recompressao melhor que um glifo pequeno, e nao
            # depende de a familia de fonte existir na maquina.
            painter.drawLine(x - 4, meio - 4, x + 1, meio)
            painter.drawLine(x + 1, meio, x - 4, meio + 4)

    def _desenhar_arranjo_livre(self, painter: QPainter) -> None:
        """Um bloco preenchido, e o motivo literal ao lado.

        Chip e nao texto fino: esta e a RESSALVA mais importante da tela
        quando ela aparece — "o que voce esta vendo nao esta em ordem de
        cadeia" —, e a lei medida e que o canal apaga a ressalva."""
        rotulo = ROTULO_ARRANJO_LIVRE
        fonte = tokens.fonte_rotulo(11)
        metrica = QFontMetrics(fonte)
        largura = metrica.horizontalAdvance(rotulo) + 2 * MARGEM
        caixa = QRect(MARGEM, 4, largura, self.height() - 9)
        painter.fillRect(caixa, tokens.ALERT)
        painter.setFont(fonte)
        painter.setPen(tokens.BG_BASE)
        painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, rotulo)

        resto = QRect(
            caixa.right() + MARGEM, 0, self.width() - caixa.right() - 2 * MARGEM, self.height()
        )
        if resto.width() <= 0:
            return
        painter.setFont(tokens.fonte_ui(11))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            resto,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _maior_que_cabe(
                (self._motivo, self._motivo.split(" ")[0]), resto.width(), tokens.fonte_ui(11)
            ),
        )


# --------------------------------------------------------------------------
# 2. O conduto — a etapa que nao tinha superficie
# --------------------------------------------------------------------------
class PainelConduto(PainelDenso):
    """O elo 2 da cadeia: o que o processamento fez com o que entrou.

    Existia so como conceito. `SessaoFluxo` recebe centenas de milhares de
    eventos, os detectores devolvem milhares de deteccoes e o motor publica
    dezenas de sinais — um funil de tres degraus que ninguem via. Aqui ele e
    a propria coluna: tres numeros empilhados, estreitando, com a seta entre
    eles.

    E embaixo o que `ui/ponte.py` diz em prosa e nenhuma tela dizia: **a
    ocupacao do buffer, com o pico retido, e o descarte contado.** Um painel
    que some com dado em silencio mente sobre a propria cobertura; a barra
    diz quanto do cano foi usado no pior momento da sessao, que e a unica
    forma de saber se o teto de 4.096 e folga ou e limite.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(LARGURA_CONDUTO)
        self._eventos = 0
        self._deteccoes = 0
        self._sinais = 0
        self._descartados = 0
        self._ocupacao = 0.0
        self._pico = 0.0

    def aplicar(self, retrato: Instantaneo, n_deteccoes: int, n_sinais: int) -> None:
        contadores = retrato.contadores
        ocupacao = len(retrato.novos_trades) / CAPACIDADE_TAPE
        pico = max(self._pico, ocupacao)
        descartados = contadores.descartados_tape + contadores.descartados_eventos
        # Comparacao pelo que e DESENHADO (o pico em pontos percentuais
        # inteiros), nao pelo float: sem isso a barra sujaria a cada quadro
        # para mover zero pixel.
        mudou = (
            contadores.total != self._eventos
            or n_deteccoes != self._deteccoes
            or n_sinais != self._sinais
            or descartados != self._descartados
            or int(pico * 100) != int(self._pico * 100)
            or int(ocupacao * 100) != int(self._ocupacao * 100)
        )
        self._eventos = contadores.total
        self._deteccoes = n_deteccoes
        self._sinais = n_sinais
        self._descartados = descartados
        self._ocupacao = ocupacao
        self._pico = pico
        if mudou:
            self.marcar_tudo_sujo()

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return tokens.PADRAO.altura_cabecalho

    def _y_funil(self) -> tuple[int, ...]:
        return tuple(self._y_corpo + 10 + i * 46 for i in range(3))

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        cabecalho = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(cabecalho, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            cabecalho.adjusted(6, 0, -6, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _maior_que_cabe(
                ("PROCESSAMENTO", "PROCESSO", "PROC."),
                self.width() - 12,
                tokens.fonte_rotulo(),
            ),
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self._y_corpo - 1, self.width(), self._y_corpo - 1)

        degraus = (
            ("EVENTOS", self._eventos),
            ("DETECÇÕES", self._deteccoes),
            ("SINAIS", self._sinais),
        )
        for indice, (y, (rotulo, valor)) in enumerate(zip(self._y_funil(), degraus)):
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(0, y, self.width(), 12),
                Qt.AlignmentFlag.AlignCenter,
                rotulo,
            )
            painter.setFont(tokens.fonte_numero(14, 600))
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                QRect(0, y + 12, self.width(), 18),
                Qt.AlignmentFlag.AlignCenter,
                formato.formatar_inteiro(valor),
            )
            if indice < len(degraus) - 1:
                caneta = QPen(tokens.TEXT_MUTED, 2)
                painter.setPen(caneta)
                meio = self.width() // 2
                painter.drawLine(meio - 4, y + 34, meio, y + 39)
                painter.drawLine(meio, y + 39, meio + 4, y + 34)

        self._desenhar_cano(painter)

    def _desenhar_cano(self, painter: QPainter) -> None:
        """A ocupacao do buffer, com o pico retido, A ESCALA e o descarte.

        **A escala e o numero, no mesmo portador.** `8%` sozinho e um
        veredito sem denominador: 8% de que? A medicao de canal da rodada 2
        mostrou que a escala e sistematicamente o primeiro token a morrer na
        transmissao — nao por acaso, por convencao tipografica, porque
        escala se escreve pequena e apagada e veredito se escreve grande e
        saturado. O resultado e que a transmissao INVERTE a honestidade da
        tela: entrega o veredito e come a regua.

        Aqui `8% de 4.096` sai num `drawText` so, com a MESMA fonte e a
        MESMA caneta — o canal nao tem como levar um e deixar o outro. Se
        nao couber na largura, quebra em duas linhas com o mesmo corpo e a
        mesma cor; o que nao acontece nunca e a escala encolher para caber.
        """
        topo = self._y_funil()[-1] + 40
        base = self.height() - ALTURA_RODAPE_CANO
        if base - topo < 40:
            return
        largura = 16
        x = (self.width() - largura) // 2
        trilha = QRect(x, topo, largura, base - topo)
        painter.fillRect(trilha, tokens.BG_BASE)
        painter.setPen(tokens.BORDER)
        painter.drawRect(trilha)

        altura_cheia = int(trilha.height() * min(1.0, self._ocupacao))
        if altura_cheia > 0:
            painter.fillRect(
                QRect(trilha.left() + 1, trilha.bottom() - altura_cheia, largura - 1, altura_cheia),
                tokens.NEUTRAL,
            )
        y_pico = trilha.bottom() - int(trilha.height() * min(1.0, self._pico))
        painter.setPen(QPen(tokens.ALERT, 2))
        painter.drawLine(trilha.left() - 4, y_pico, trilha.right() + 4, y_pico)

        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(0, base + 4, self.width(), 12),
            Qt.AlignmentFlag.AlignCenter,
            "PICO DO CANO",
        )
        # Veredito e escala na mesma fonte, na mesma caneta, e de preferencia
        # no mesmo `drawText`.
        fonte = tokens.fonte_numero(12, 600)
        painter.setFont(fonte)
        painter.setPen(tokens.TEXT_PRIMARY)
        for indice, linha in enumerate(self.linhas_do_pico()):
            painter.drawText(
                QRect(0, base + 16 + indice * 14, self.width(), 14),
                Qt.AlignmentFlag.AlignCenter,
                linha,
            )
        # Descarte: o numero que `ui/ponte.py` existe para nao esconder. Zero
        # aparece igual — some-lo quando zera ensinaria o olho a nao procurar
        # por ele justamente no dia em que ele deixa de ser zero. E a unidade
        # (`desc.`) vai dentro do mesmo `drawText` pela regra da escala.
        painter.setFont(fonte)
        painter.setPen(tokens.ALERT if self._descartados else tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(0, base + 44, self.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            formato.formatar_inteiro(self._descartados) + " desc.",
        )

    def linhas_do_pico(self) -> tuple[str, ...]:
        """`("8% de 4.096",)` — ou duas linhas, quando nao cabe numa.

        O que nao existe e o caminho que devolve so `8%`: a escala nao e
        opcional, e a largura da coluna nao e argumento para omiti-la.
        `CAPACIDADE_TAPE` e lido de `ui/ponte.py`, nunca digitado — quem
        mexer no teto do buffer muda o denominador na tela junto."""
        pct = f"{int(self._pico * 100)}%"
        escala = "de " + formato.formatar_inteiro(CAPACIDADE_TAPE)
        junto = pct + " " + escala
        cabe = QFontMetrics(tokens.fonte_numero(12, 600)).horizontalAdvance(junto)
        if cabe <= max(0, self.width() - 8):
            return (junto,)
        return (pct, escala)


# --------------------------------------------------------------------------
# 3. O registro — a coluna que faltava
# --------------------------------------------------------------------------
ALTURA_LINHA_REGRA = 18
ALTURA_LINHA_PARAMETRO = 34
"""Duas linhas: o rotulo com o chip em cima, o valor com a ressalva embaixo.
Ver `PainelRegras._desenhar_parametro` — o primeiro retrato mostrou o valor
CORTADO quando as quatro coisas dividiam uma linha de 18px."""

ROTULO_FAMILIA: dict[str, str] = {
    "dominancia": "DOMINÂNCIA",
    "linha_azul": "LINHA AZUL",
    "macro_micro": "MACRO × MICRO",
    "velocimetro": "VELOCÍMETRO",
    "estrutura": "ESTRUTURA",
    "placar": "PLACAR",
    "risco": "RISCO",
    "exaustao": "EXAUSTÃO",
    "escora": "ESCORA",
    "sinal_ultra": "SINAL ULTRA",
    "horarios": "HORÁRIOS",
    "alvo": "ALVO",
    "maker": "MAKER",
}
"""Traducao de exibicao. Familia que faltar aqui aparece com o proprio id em
caixa alta — o painel nunca ESCONDE uma familia por nao ter rotulo: o
registro e a fonte da lista, este dicionario e so ortografia."""

#: Limiares do motor que a tela usa para julgar. A PROCEDENCIA de cada um
#: nao esta escrita aqui: vem de `matriz.regras_do_campo`, que procura o nome
#: QUALIFICADO (`ConfigMotorSinais.janela_micro_ns`) no registro. Uma segunda
#: tabela de procedencia nesta camada seria uma segunda verdade — e ja teria
#: errado neste exato ponto: `macro_micro.janela_micro` responde por
#: `ConfigMacroMicro`, nao pelo campo homonimo do motor, e reivindicar aquele
#: aval aqui seria pegar emprestado o que ninguem deu.
PARAMETROS_EM_VIGOR: tuple[tuple[str, str], ...] = (
    ("dominancia_minima", "DOMINÂNCIA MÍN."),
    ("magnitude_relativa_minima", "MAGNITUDE MÍN."),
    ("janela_dominancia_ns", "JANELA DOMINÂNCIA"),
    ("janela_micro_ns", "JANELA MICRO"),
)

ALTURA_RODAPE_REGRAS = 34
"""Duas linhas: a frase de modo em cima, o motivo embaixo. Ver
`PainelRegras._desenhar_rodape`."""

CORPO_CORTE = 12
"""Corpo da linha de corte. Nunca menor que o do rodape que ela qualifica
(11px): a lei do canal, medida, e que a ressalva em corpo menor morre na
transmissao e a conclusao sobrevive sozinha."""

ALTURA_TITULO_LIMIARES = 18
"""Rotulo `LIMIARES EM VIGOR` mais a regua de 1px embaixo dele."""

VAO_SECAO = 8

RODAPE_MODO = "MODO SINAIS · NÃO ENVIA ORDEM"
"""O fim honesto da cadeia. O elo 4 chama-se DECISAO e a decisao e do
operador: este programa nao manda ordem para lugar nenhum
(`scripts/painel.py`). Escrito na coluna da decisao, e nao so no `--help`."""


def _familias() -> tuple[tuple[str, int, int, Confianca], ...]:
    """`(familia, implementadas, total, pior confianca)`, lido do registro.

    Derivado, nunca digitado: uma tabela escrita aqui seria uma SEGUNDA fonte
    de procedencia, que envelhece em silencio no dia em que alguem implementar
    uma familia nova. `regras.py` valida no import; este painel so le."""
    ordem: list[str] = []
    for id_ in REGRAS:
        familia = id_.split(".")[0]
        if familia not in ordem:
            ordem.append(familia)
    linhas = []
    for familia in ordem:
        regras = [r for i, r in REGRAS.items() if i.split(".")[0] == familia]
        implementadas = sum(1 for r in regras if r.implementada)
        pior = max((r.confianca for r in regras), key=lambda c: _GRAVIDADE[c])
        linhas.append((familia, implementadas, len(regras), pior))
    # Quem o produto sustenta primeiro, quem ele recusa depois — e dentro de
    # cada grupo, a familia maior antes. A ordem e a mensagem: a leitura de
    # cima para baixo vai do que tem lastro para o que nao tem.
    linhas.sort(key=lambda linha: (linha[1] == 0, -linha[1], -linha[2], linha[0]))
    return tuple(linhas)


@dataclass(frozen=True, slots=True)
class LayoutRegras:
    """Quem cabe INTEIRO na coluna do registro, e o que ficou de fora.

    O desenho e o teste leem esta mesma funcao: e a lei n.o 6 aplicada ao
    painel em que a lei n.o 2 (F8) tinha sido violada. Antes, `desenhar`
    empilhava as treze familias e os quatro limiares a partir do topo e o
    rodape era desenhado por cima do que sobrou — as duas ultimas familias
    ficavam ESCRITAS EM CIMA de `MODO SINAIS · NÃO ENVIA ORDEM`, e os
    limiares caiam fora do widget sem que nada dissesse que existiam.

    **Quem cede e a lista, nunca o rodape.** A frase do rodape e a
    declaracao de escopo do produto (este programa nao manda ordem): se ela
    nao couber, nao ha painel que valha a pena desenhar. Uma familia que nao
    cabe, ao contrario, e uma ausencia DECLARAVEL — cabe em uma linha dizer
    quantas ficaram fora, e e o que `texto_do_corte` escreve. Meia lista
    silenciosa seria a fraqueza F8: parece a lista inteira.

    A ordem das secoes nao muda com a altura de proposito. Promover os
    limiares na frente das familias quando aperta faria a ordem de leitura
    do painel depender do tamanho da janela — o operador aprenderia uma
    tela diferente a cada arrasto de divisor.
    """

    altura: int
    rodape: QRect
    rodape_visivel: bool
    y_familias: int
    n_familias: int
    familias_fora: int
    y_limiares: int
    """Topo do rotulo `LIMIARES EM VIGOR`. `-1` quando a secao nao entra."""
    n_limiares: int
    limiares_fora: int
    y_corte: int
    """Topo da linha que declara o que ficou de fora. `-1` quando nada ficou."""

    @property
    def completo(self) -> bool:
        return self.familias_fora == 0 and self.limiares_fora == 0


def layout_regras(
    altura: int,
    n_familias: int,
    n_limiares: int = len(PARAMETROS_EM_VIGOR),
    densidade: tokens.Densidade = tokens.PADRAO,
) -> LayoutRegras:
    """Geometria do `PainelRegras` para uma altura dada. Pura, sem widget."""
    topo = densidade.altura_cabecalho + 4
    rodape = QRect(0, altura - ALTURA_RODAPE_REGRAS, 0, ALTURA_RODAPE_REGRAS)
    vazio = LayoutRegras(
        altura=altura,
        rodape=rodape,
        rodape_visivel=False,
        y_familias=topo,
        n_familias=0,
        familias_fora=n_familias,
        y_limiares=-1,
        n_limiares=0,
        limiares_fora=n_limiares,
        y_corte=-1,
    )
    if rodape.top() < topo:
        # Nem o rodape cabe abaixo do cabecalho: o painel desenha so o
        # cabecalho. Um rodape mordendo o cabecalho seria a mesma
        # sobreposicao, um andar acima.
        return vazio

    disponivel = rodape.top() - topo
    inteiro = (
        n_familias * ALTURA_LINHA_REGRA
        + VAO_SECAO
        + ALTURA_TITULO_LIMIARES
        + n_limiares * ALTURA_LINHA_PARAMETRO
    )
    if disponivel >= inteiro:
        y_limiares = topo + n_familias * ALTURA_LINHA_REGRA + VAO_SECAO
        return LayoutRegras(
            altura=altura,
            rodape=rodape,
            rodape_visivel=True,
            y_familias=topo,
            n_familias=n_familias,
            familias_fora=0,
            y_limiares=y_limiares,
            n_limiares=n_limiares,
            limiares_fora=0,
            y_corte=-1,
        )

    # Nao cabe tudo: a linha do corte e reservada ANTES de distribuir o
    # resto. Ela e a unica coisa que impede a lista cortada de parecer
    # inteira, entao ela nao pode ser a primeira a ser sacrificada.
    sobra = disponivel - ALTURA_LINHA_REGRA
    if sobra < 0:
        # Nem a linha do corte cabe. O rodape ja coube (`rodape.top() >=
        # topo`), e ele continua desenhado: quem cede e a lista, sempre —
        # inclusive quando o que sobra dela e nada.
        return dataclasses.replace(vazio, rodape_visivel=True)

    cabem = min(n_familias, sobra // ALTURA_LINHA_REGRA)
    sobra -= cabem * ALTURA_LINHA_REGRA
    y_limiares = -1
    postos = 0
    if cabem == n_familias:
        espaco = sobra - VAO_SECAO - ALTURA_TITULO_LIMIARES
        if espaco >= ALTURA_LINHA_PARAMETRO:
            postos = min(n_limiares, espaco // ALTURA_LINHA_PARAMETRO)
            y_limiares = topo + cabem * ALTURA_LINHA_REGRA + VAO_SECAO
            sobra -= VAO_SECAO + ALTURA_TITULO_LIMIARES + postos * ALTURA_LINHA_PARAMETRO
    y_corte = rodape.top() - ALTURA_LINHA_REGRA
    return LayoutRegras(
        altura=altura,
        rodape=rodape,
        rodape_visivel=True,
        y_familias=topo,
        n_familias=cabem,
        familias_fora=n_familias - cabem,
        y_limiares=y_limiares,
        n_limiares=postos,
        limiares_fora=n_limiares - postos,
        y_corte=y_corte,
    )


def familias_na_tela(
    familias: tuple[tuple[str, int, int, Confianca], ...], n_linhas: int
) -> tuple[tuple[str, int, int, Confianca], ...]:
    """Quais familias sobrevivem a `n_linhas`. O corte e no MEIO, de proposito.

    A lista chega ordenada de quem tem lastro para quem nao tem — as
    RECUSADAS (`0/1`) sao a cauda. Cortar pela cauda, que e o que uma
    truncagem ingenua faz, apagaria exatamente `EXAUSTÃO 0/1 § S/ FONTE` e
    `MAKER 0/1`: as linhas que desmentem, de dentro da tela, o item mais
    frequente da banda de deteccoes. Seria a lei n.o 1 cometida em geometria
    — o aperto preservando o veredito e comendo a ressalva.

    Entao quem some primeiro e o MIOLO: as familias implementadas do meio da
    lista, que o painel ja resume no `n/n` do cabecalho. A ordem de leitura
    nao muda com a altura; o que muda e quantas linhas dela existem, e a
    linha de corte diz quantas.
    """
    if n_linhas >= len(familias):
        return familias
    if n_linhas <= 0:
        return ()
    recusadas = tuple(f for f in familias if f[1] == 0)
    # Metade e metade, e nao "as recusadas primeiro": uma lista so de `0/1`
    # inverteria a mentira em vez de corrigi-la — o painel passaria a
    # parecer um produto que nao implementa nada. As duas metades da
    # afirmacao (o que tem lastro, o que nao tem) sobrevivem ao aperto
    # juntas, ou o corte nao seria honesto em nenhuma das direcoes.
    n_cauda = min(len(recusadas), max(1, n_linhas // 2)) if recusadas else 0
    cauda = recusadas[len(recusadas) - n_cauda:] if n_cauda else ()
    cabeca = familias[: n_linhas - n_cauda]
    return cabeca + cauda


def texto_do_corte(familias_fora: int, limiares_fora: int) -> tuple[str, ...]:
    """Alternativas do mais explicito ao mais curto (F8, `_maior_que_cabe`).

    Nunca `…`: reticencia diz que ha mais alguma coisa, e nao QUANTA. O
    numero e o conteudo da linha."""
    partes = []
    if familias_fora:
        partes.append("%d FAMÍLIAS" % familias_fora)
    if limiares_fora:
        partes.append("%d LIMIARES" % limiares_fora)
    junto = " · ".join(partes)
    curto = "+".join(
        p.split(" ")[0] for p in partes
    )
    return (
        "COLUNA CURTA · %s FORA DA TELA" % junto,
        "%s FORA DA TELA" % junto,
        "%s FORA" % junto,
        "%s FORA" % curto,
    )


class PainelRegras(PainelDenso):
    """As regras que o registro avaliza, e os limiares em vigor.

    Nasce da observacao do critico da rodada anterior: a interface dava area
    ao fluxo que `metodologia/regras.py` **nao** avaliza (a banda de
    deteccoes) e nenhuma as 33 regras que ele avaliza. Area e argumento numa
    tela densa — quem ganha coluna ganha a atencao.

    Duas secoes, e as duas sao lidas do registro em vez de escritas:

    1. **Familias.** `DOMINÂNCIA 3/3 § IMPRECISO` — quantas regras da familia
       o produto implementa, e a PIOR procedencia entre elas. `EXAUSTÃO 0/1
       § S/ FONTE` aparece na mesma lista, e essa e a linha que faz o painel
       valer: ela desmente, de dentro da propria tela, o item mais frequente
       da banda de deteccoes.
    2. **Limiares em vigor.** O valor que ESTE processo esta usando, com o
       default de producao ao lado quando eles diferem. Calibrar o motor pela
       linha de comando passa a mexer na tela, e nao so no comportamento —
       um corte diferente do de producao nunca fica invisivel.

    O painel e mobiliario: o conteudo nao muda entre dois trades, entao ele
    desenha uma vez e nunca mais suja. E de proposito que ele nao tem
    `aplicar`.

    **Quando a coluna nao cabe**, quem manda e `layout_regras` e o que ela
    decide esta escrito la: o rodape e intocavel, a lista cede, e o que
    cedeu vai escrito numa linha em vez de desaparecer.
    """

    def __init__(
        self,
        config: ConfigMotorSinais | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config if config is not None else ConfigMotorSinais()
        self.padrao = ConfigMotorSinais()
        self._familias = _familias()
        self._implementadas = sum(1 for r in REGRAS.values() if r.implementada)
        self.setMinimumSize(240, 200)

    # ----------------------------------------------------------- geometria
    def layout_corrente(self) -> LayoutRegras:
        """A geometria corrente. MESMA funcao que o teste mede."""
        return layout_regras(
            self.height(), len(self._familias), len(PARAMETROS_EM_VIGOR)
        )

    # ------------------------------------------------------------- conteudo
    def texto_do_parametro(self, campo: str) -> str:
        """`0,70` — e `0,525 (prod. 0,70)` quando ha calibracao.

        A ressalva viaja no MESMO portador do numero: mesma linha, mesmo
        corpo, mesma cor de ressalva do resto da tela. E a lei desta rodada
        aplicada ao lugar onde ela e mais facil de violar."""
        atual = getattr(self.config, campo)
        padrao = getattr(self.padrao, campo)
        texto = formatar_limiar(campo, atual)
        if atual != padrao:
            texto += f"  (prod. {formatar_limiar(campo, padrao)})"
        return texto

    def calibrado(self, campo: str) -> bool:
        return getattr(self.config, campo) != getattr(self.padrao, campo)

    def procedencia_do_campo(self, campo: str) -> tuple[str, QColor]:
        """Pior procedencia entre as regras que respondem pelo botao.

        Tupla vazia — o registro nao cobre este limiar — vira `S/ REGISTRO`,
        que e o pior rotulo e nao o mais brando: um limiar vivo, calibravel,
        que ninguem registrou nao pode contar como aval."""
        ids = regras_do_campo(campo)
        pior: Confianca | None = None
        if ids:
            pior = max((REGRAS[i].confianca for i in ids), key=lambda c: _GRAVIDADE[c])
        return _rotulo_confianca(pior), _cor_da_confianca(pior)

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        altura_cabecalho = tokens.PADRAO.altura_cabecalho
        self._desenhar_cabecalho(painter, QRect(0, 0, self.width(), altura_cabecalho))

        plano = self.layout_corrente()
        y = plano.y_familias
        for familia, implementadas, total, pior in familias_na_tela(
            self._familias, plano.n_familias
        ):
            self._desenhar_familia(
                painter,
                QRect(0, y, self.width(), ALTURA_LINHA_REGRA),
                familia,
                implementadas,
                total,
                pior,
            )
            y += ALTURA_LINHA_REGRA

        if plano.n_limiares:
            y = plano.y_limiares
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(MARGEM, y, self.width() - 2 * MARGEM, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "LIMIARES EM VIGOR",
            )
            painter.setPen(tokens.BORDER)
            painter.drawLine(MARGEM, y + 15, self.width() - MARGEM, y + 15)
            y += ALTURA_TITULO_LIMIARES
            for campo, rotulo in PARAMETROS_EM_VIGOR[: plano.n_limiares]:
                self._desenhar_parametro(
                    painter,
                    QRect(0, y, self.width(), ALTURA_LINHA_PARAMETRO),
                    campo,
                    rotulo,
                )
                y += ALTURA_LINHA_PARAMETRO

        self._desenhar_corte(painter, plano)
        self._desenhar_rodape(painter, plano)

    def _desenhar_cabecalho(self, painter: QPainter, rect: QRect) -> None:
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Método"
        )
        painter.setFont(tokens.fonte_numero(11, 600))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._implementadas}/{len(REGRAS)} regras",
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, rect.bottom(), self.width(), rect.bottom())

    def _largura_chip(self) -> int:
        return min(96, max(72, self.width() // 4))

    def _desenhar_familia(
        self,
        painter: QPainter,
        linha: QRect,
        familia: str,
        implementadas: int,
        total: int,
        pior: Confianca,
    ) -> None:
        largura_chip = self._largura_chip()
        recusada = implementadas == 0
        painter.setFont(tokens.fonte_ui(11, 600 if not recusada else 400))
        painter.setPen(tokens.TEXT_PRIMARY if not recusada else tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, linha.top(), linha.width() - 2 * MARGEM - largura_chip - 46, linha.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ROTULO_FAMILIA.get(familia, familia.upper()),
        )
        painter.setFont(tokens.fonte_numero(11, 600))
        painter.setPen(tokens.TEXT_PRIMARY if not recusada else tokens.TEXT_MUTED)
        painter.drawText(
            QRect(
                linha.width() - MARGEM - largura_chip - 44,
                linha.top(),
                40,
                linha.height(),
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{implementadas}/{total}",
        )
        _chip(
            painter,
            QRect(
                linha.width() - MARGEM - largura_chip,
                linha.top() + 3,
                largura_chip,
                linha.height() - 6,
            ),
            _rotulo_confianca(pior),
            _cor_da_confianca(pior),
        )

    def _desenhar_parametro(
        self, painter: QPainter, linha: QRect, campo: str, rotulo: str
    ) -> None:
        """Duas linhas, e a segunda e a razao de existirem duas.

        A versao de uma linha punha rotulo, valor, ressalva de calibracao e
        chip no mesmo `QRect` de 340px — e o primeiro retrato mostrou o
        resultado: `JANELA DOMINÂNCIA  ) s  (prod. 300,0 s)`. O valor tinha
        sido CORTADO ao meio pelo clip, e um numero cortado continua
        parecendo um numero. E a fraqueza F8 cometida por aperto em vez de
        por descuido, dentro do painel que existe para nao afirmar demais.

        Com a linha do valor inteira para si, o valor cabe com a ressalva
        junto — mesmo corpo, mesma cor, mesma linha —, que e o que a lei do
        canal exige."""
        largura_chip = self._largura_chip()
        texto_chip, cor_chip = self.procedencia_do_campo(campo)
        meia = linha.height() // 2
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, linha.top(), linha.width() - 2 * MARGEM - largura_chip - 4, meia),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            rotulo,
        )
        painter.setFont(tokens.fonte_numero(12, 600))
        painter.setPen(tokens.ALERT if self.calibrado(campo) else tokens.TEXT_PRIMARY)
        painter.drawText(
            QRect(MARGEM + 12, linha.top() + meia, linha.width() - 2 * MARGEM - 12, meia),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.texto_do_parametro(campo),
        )
        _chip(
            painter,
            QRect(
                linha.width() - MARGEM - largura_chip,
                linha.top() + 2,
                largura_chip,
                meia - 2,
            ),
            texto_chip,
            cor_chip,
        )

    def _desenhar_corte(self, painter: QPainter, plano: LayoutRegras) -> None:
        """A linha que declara o que a coluna curta deixou de fora.

        Em `ALERT` (12,34:1) e nao em `DANGER` (5,45:1): a lei do canal desta
        rodada tem duas metades, e a segunda diz que ressalva viaja em
        LUMINANCIA, nao em croma — o JPEG subamostra croma 2x e come
        exatamente o tipo de aviso que esta linha e."""
        if plano.y_corte < 0:
            return
        faixa = QRect(MARGEM, plano.y_corte, self.width() - 2 * MARGEM, ALTURA_LINHA_REGRA)
        fonte = tokens.fonte_ui(CORPO_CORTE, 700)
        texto = _maior_que_cabe(
            texto_do_corte(plano.familias_fora, plano.limiares_fora),
            faixa.width() - 8,
            fonte,
        )
        # CHIP, e nao texto colorido: a primeira versao saiu em `ALERT` sobre
        # o fundo do painel e `scripts/retencao.py` reprovou o par —
        # `corte_regras` retinha 37,6% contra 44,2% do rodape que ela
        # qualifica. Bloco preenchido com texto escuro e a forma que este
        # produto ja usa para ressalva, e e a que a recompressao nao apaga.
        # O corpo e o MESMO do rodape (11px, 600): a ressalva nunca viaja
        # menor que o dado que ela qualifica.
        largura = min(faixa.width(), QFontMetrics(fonte).horizontalAdvance(texto) + 12)
        rect = QRect(faixa.left(), faixa.top() + 1, largura, faixa.height() - 2)
        painter.fillRect(rect, tokens.ALERT)
        painter.setFont(fonte)
        painter.setPen(tokens.BG_BASE)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)

    def _desenhar_rodape(self, painter: QPainter, plano: LayoutRegras) -> None:
        """Ancorado embaixo: e a ultima frase da coluna da DECISAO."""
        if not plano.rodape_visivel:
            return
        rect = QRect(plano.rodape)
        rect.setWidth(self.width())
        painter.setPen(tokens.BORDER)
        painter.drawLine(MARGEM, rect.top(), self.width() - MARGEM, rect.top())
        painter.setFont(tokens.fonte_ui(11, 600))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            rect.adjusted(MARGEM, 4, -MARGEM, -16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            RODAPE_MODO,
        )
        painter.setFont(tokens.fonte_ui(11))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            rect.adjusted(MARGEM, 16, -MARGEM, -2),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{len(REGRAS) - self._implementadas} regras recusadas, com o motivo no registro",
        )


# --------------------------------------------------------------------------
# 4. A janela

# --------------------------------------------------------------------------
# 4. A doca — o cromo do SO trocado por cromo nosso
# --------------------------------------------------------------------------
ALTURA_CABECALHO_DOCA = 20
"""Cabecalho proprio de cada doca. 20px e o menor corpo em que `fonte_rotulo`
de 10px ainda respira, e um cabecalho maior custaria area de dado catorze
vezes."""


class CabecalhoDoca(QWidget):
    """A barra de titulo de um `QDockWidget`, desenhada por nos.

    E o pedaco que faz o docking parar de violar V5. Por padrao o Qt desenha
    o titulo, o botao de flutuar e o de fechar com o ESTILO DO SISTEMA — que
    era exatamente a objecao que a composicao usou para recusar `QSplitter`
    ("o punho e desenhado pelo estilo do SO"). `setTitleBarWidget` substitui a
    barra inteira; o que sobra do estilo do sistema e o separador entre docas,
    e esse vai declarado em `workspace.folha_de_estilo`, a partir dos tokens.

    Nao e um `PainelDenso`: nao tem dado, nao muda entre quadros e nao merece
    um `QTimer`. Catorze relogios de desenho para pintar catorze titulos fixos
    seria pagar o preco do ativo mais caro do projeto de UI pelo texto que
    menos muda na tela.

    Nao ha botao de fechar de proposito. Um painel que o operador pode perder
    com um clique e um painel em que ele nao pode confiar no meio do pregao; a
    troca de arranjo e por workspace (`Ctrl+1..9`), que e reversivel e
    nomeada.
    """

    def __init__(self, chave: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.titulo = TITULO_DA_DOCA.get(chave, chave.upper())
        self.elo = ELO_DA_DOCA.get(chave, ELO_FORA)
        self.setFixedHeight(ALTURA_CABECALHO_DOCA)
        self.setAutoFillBackground(True)

    def paintEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, tokens.BG_RAISED)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, rect.bottom(), rect.width(), rect.bottom())
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            rect.adjusted(MARGEM, 0, -MARGEM, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.titulo,
        )
        if self.elo != ELO_FORA:
            # O numero do elo NO cabecalho da doca. E o que mantem a cadeia
            # apontavel quando o trilho se abstem: com o arranjo desmanchado o
            # operador ainda le, em cada painel, a que altura da cadeia ele
            # pertence. A ressalva sobrevive a perda do veredito.
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                rect.adjusted(MARGEM, 0, -MARGEM, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "ELO %d" % self.elo,
            )
        painter.end()


# --------------------------------------------------------------------------
# 5. A janela
# --------------------------------------------------------------------------
class JanelaFluxo(QMainWindow):
    """Shell com docking, quatro elos da cadeia, e UM relogio de dados.

    ## O que mudou, e o que nao mudou

    A cadeia continua sendo a afirmacao central desta camada — mas ela deixou
    de ser uma promessa do LAYOUT e passou a ser uma leitura do ARRANJO. Ver
    `ui/workspace.py`, secao "o conflito docking x cadeia": os dois convivem, e
    quem se subordina e o trilho.

    Um relogio de dados: `_tick` le a ponte uma vez e distribui o mesmo
    `Instantaneo`; painel nenhum chama `ponte.ler()`. `sessao.leitura_do_metodo()`
    entra no mesmo quadro — nao drena, e imutavel, e traz os cinco retratos do
    metodo com o mesmo `timestamp_ns` por construcao.
    """

    def __init__(
        self,
        ponte: PonteFluxo,
        simbolo: str,
        grid: PriceGrid,
        modo: str = "",
        paleta: tokens.Paleta = tokens.PALETA_COR,
        densidade: tokens.Densidade = tokens.PADRAO,
        ao_fechar=None,
        config_motor: ConfigMotorSinais | None = None,
        sessao=None,
        ressalva: tuple[str, str] = ("", ""),
        config: ConfigOperacao | None = None,
        em_replay: bool = False,
        workspace: Workspace | None = None,
        persistir: bool = False,
        trilha: TrilhaEventos | None = None,
    ) -> None:
        super().__init__()
        self.ponte = ponte
        self.simbolo = simbolo
        self.grid = grid
        self.paleta = paleta
        self.densidade = densidade
        self.sessao = sessao
        self.config = config if config is not None else ConfigOperacao(symbol=simbolo)
        self.config_motor = config_motor if config_motor is not None else ConfigMotorSinais()
        self.trilha = trilha if trilha is not None else TrilhaEventos()
        self._ao_fechar = ao_fechar
        self._persistir = persistir
        self._em_replay = em_replay
        self._modo = modo
        self._n_eventos = 0
        self._n_deteccoes = 0
        self._n_sinais = 0
        self._ultimo_sinal: object | None = None
        self._ultimo_instantaneo: Instantaneo | None = None
        self._estado_operacional_asg: EstadoASG | None = EstadoASG.AGUARDANDO
        self._leitura: LeituraMotor | None = None
        self._estado_faixa: EstadoFeed | None = None
        self._chave_faixa: tuple[EstadoFeed, str | None] | None = None
        self._quadros_sem_players = 0
        self._players_visivel = True
        self._motivo_trilho = ""
        self._quadros_perdidos_corrida = 0

        self.setWindowTitle(f"FluxoPro — {simbolo}")
        self.resize(1480, 900)
        self._pintar_fundo()

        self.faixa = QFrame()
        self.faixa.setFixedHeight(ALTURA_FAIXA)
        self.faixa.setAutoFillBackground(True)

        self.ressalva = FaixaRessalva(*ressalva) if ressalva[0] else None
        self.topo = StripTopo(simbolo, grid, paleta=paleta)
        self.topo.definir_modo(modo, replay=em_replay)
        self.trilho = TrilhoCadeia()
        self.rodape = StripRodape()

        # O anfitriao das docas e um `QMainWindow` ANINHADO. As strips e o
        # trilho tem de ficar FORA da area de docking — se estivessem no
        # widget central do anfitriao, uma doca arrastada para a borda
        # passaria por cima do trilho, e o trilho e justamente o que afirma
        # onde as colunas estao.
        self._host = QMainWindow()
        self._host.setDockNestingEnabled(True)
        self._host.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )
        # V5: o separador do `QMainWindow` deixa de ser desenhado pelo SO.
        self._host.setStyleSheet(folha_de_estilo())
        vazio = QWidget()
        vazio.setMaximumSize(0, 0)
        self._host.setCentralWidget(vazio)

        self.docas: dict[str, QDockWidget] = {}
        self._paineis: dict[str, QWidget] = {}
        self._montar_paineis()
        self._montar_docas()

        # A doca ASG existe no estado serializado por compatibilidade de
        # nomes, mas o composto real nao mora nela: no Ctrl+5 ele ocupa a
        # area operacional inteira em um stack. Isso isola o layout historico
        # e elimina o sizeHint transitorio da antiga coluna de decisao.
        self._asg_doca_placeholder = QWidget()
        self.docas["asg"].setWidget(self._asg_doca_placeholder)
        self.asg.setParent(None)
        self._area_operacional = QStackedWidget()
        self._area_operacional.setMinimumSize(0, 0)
        self._area_operacional.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self._area_operacional.addWidget(self._host)
        self._area_operacional.addWidget(self.asg)
        self._area_operacional.addWidget(self.nexo_ai)

        self.tarja_replay = TarjaReplay()
        self.tarja_replay.instalar_em(self)
        self.tarja_replay.setVisible(False)

        central = QWidget()
        coluna = QVBoxLayout(central)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self.faixa)
        if self.ressalva is not None:
            coluna.addWidget(self.ressalva)
        coluna.addWidget(self.topo)
        coluna.addWidget(self.trilho)
        coluna.addWidget(self._area_operacional, 1)
        coluna.addWidget(self.rodape)
        self.setCentralWidget(central)

        # O arranjo canonico e capturado AQUI, antes de qualquer arquivo de
        # workspace entrar. E o piso de todo `Ctrl+N`: sem ele, um estado
        # salvo estranho contaminaria os quatro workspaces de fabrica de uma
        # vez e nao haveria como voltar sem apagar arquivo na mao.
        self._estado_de_fabrica = self._host.saveState()

        self._atalhos: list[QShortcut] = []
        self._instalar_atalhos()

        self._workspace: Workspace = workspace or WORKSPACES_DE_FABRICA[0]
        self.aplicar_workspace(self._workspace, registrar=False)

        self._conferir_eixos()
        self._atualizar_faixa(EstadoFeed.AGUARDANDO)
        self._sincronizar_trilho()
        self.dom.setFocus()

        self._relogio = QTimer(self)
        self._relogio.setInterval(INTERVALO_QUADRO_MS)
        self._relogio.setTimerType(Qt.TimerType.PreciseTimer)
        self._relogio.timeout.connect(self._tick)
        self._relogio.start()

    # ------------------------------------------------------------- montagem
    #: Paineis que sabem trocar de densidade a quente, preservando o estado
    #: de tela. `footprint`, `perfil` e `delta` andam JUNTOS: os dois ultimos
    #: recebem os eixos do primeiro por identidade de objeto, entao preservar
    #: um sem o outro quebraria o acoplamento que faz os tres compartilharem
    #: eixo. Ou os tres ficam, ou os tres sao reconstruidos.
    TROCAM_A_QUENTE = ("footprint", "perfil", "delta", "bookmap", "tape")

    def _montar_paineis(self, preservados: dict | None = None) -> None:
        """Constroi os paineis na densidade corrente.

        Chamado no construtor e de novo em `aplicar_densidade`. A ORDEM de
        construcao importa num ponto so, e e o ponto que o construtor da fase
        2 documentou: `PainelPerfil` e `PainelDeltaAcumulado` recebem os eixos
        do `PainelFootprint` **por identidade de objeto**. Nao ha copia, nao
        ha formula equivalente — e o mesmo `EixoPreco` e o mesmo `EixoTempo`.

        `preservados` reaproveita instancias que ja trocaram de densidade a
        quente, em vez de descarta-las. E o que permite `Ctrl+Shift+D` nao
        apagar as colunas do footprint, o plano do bookmap e o anel do tape.
        """
        vivos = preservados or {}
        cfg = self.config
        d, p = self.densidade, self.paleta

        self.dom = PainelDOM(self.grid, paleta=p, densidade=d)
        self.tape = vivos.get("tape") or PainelTape(self.grid, paleta=p, densidade=d)
        self.players = PainelPlayers(paleta=p, densidade=d)
        self.bookmap = vivos.get("bookmap") or PainelBookmap(
            self.grid, symbol=self.simbolo, paleta=p, densidade=d
        )

        self.conduto = PainelConduto()
        self.conduto.setFixedWidth(LARGURA_CONDUTO)

        if "footprint" in vivos:
            # Os tres juntos, ou nenhum — ver `TROCAM_A_QUENTE`.
            self.footprint = vivos["footprint"]
            self.perfil = vivos["perfil"]
            self.delta = vivos["delta"]
        else:
            self.footprint = PainelFootprint(
                self.grid,
                densidade=d,
                paleta=p,
                config=cfg.footprint,
                simbolo=self.simbolo,
                timeframe_ns=cfg.timeframe_ns,
            )
            self.perfil = PainelPerfil(
                self.grid,
                self.footprint.eixo_preco,
                densidade=d,
                paleta=p,
                config=cfg.volume_profile,
            )
            self.delta = PainelDeltaAcumulado(
                self.footprint.eixo_tempo, densidade=d, paleta=p, config=cfg.delta
            )
        self.matriz = PainelMatriz(
            self.grid, densidade=d, paleta=p, config=self.config_motor
        )
        # O minimo do painel (260px) e menor que a altura em que a sua
        # propria banda de deteccoes abre a primeira linha. Ver
        # `altura_minima_matriz`: a composicao nao conserta `matriz.py`,
        # so recusa entregar a ela uma doca em que a banda so cabe como
        # promessa.
        self.matriz.setMinimumHeight(altura_minima_matriz(d))

        self.hud = PainelHUD(densidade=d, paleta=p)
        self.metodo = PainelMetodo(self.grid, densidade=d, paleta=p)
        self.regras = PainelRegras(self.config_motor)
        self.asg = WorkspaceASG(
            paleta=p, grid=self.grid, symbol=self.simbolo, densidade=d,
            timeframe_ns=self.config.timeframe_ns,
        )
        self.nexo_ai = PainelNexoAIVertical(simbolo=self.simbolo)

        self.controles_replay = ControlesReplay(densidade=d)
        self.controles_replay.buscou.connect(self._ao_buscar_replay)
        self.controles_replay.velocidade_mudou.connect(self._ao_mudar_velocidade)
        self.controles_replay.pausa_alternada.connect(self._ao_alternar_pausa)
        self.painel_trilha = PainelTrilha(self.trilha, densidade=d)

        self._paineis = {
            "dom": self.dom,
            "tape": self.tape,
            "players": self.players,
            "bookmap": self.bookmap,
            "conduto": self.conduto,
            "footprint": self.footprint,
            "perfil": self.perfil,
            "delta": self.delta,
            "matriz": self.matriz,
            "hud": self.hud,
            "metodo": self.metodo,
            "regras": self.regras,
            "asg": self.asg,
            "replay": self.controles_replay,
            "trilha": self.painel_trilha,
        }

    def _nova_doca(self, chave: str) -> QDockWidget:
        doca = QDockWidget(TITULO_DA_DOCA[chave], self._host)
        # `objectName` nao e cosmetico: `saveState`/`restoreState` casam doca
        # com estado POR ESSE NOME. Uma doca sem nome volta do arquivo no
        # lugar errado, em silencio.
        doca.setObjectName("doca_" + chave)
        doca.setTitleBarWidget(CabecalhoDoca(chave))
        doca.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        doca.setWidget(self._paineis[chave])
        self.docas[chave] = doca
        return doca

    def _montar_docas(self) -> None:
        """O arranjo canonico: quatro colunas, na ordem da cadeia.

        Construido por `splitDockWidget` explicito e nao por `addDockWidget`
        em area: `addDockWidget` deixa o Qt escolher a ordem, e a ordem AQUI e
        a afirmacao do produto.
        """
        area = Qt.DockWidgetArea.LeftDockWidgetArea
        host = self._host
        host.addDockWidget(area, self._nova_doca("dom"))
        H = Qt.Orientation.Horizontal
        V = Qt.Orientation.Vertical

        # PRIMEIRO o esqueleto de COLUNAS, so com splits horizontais. A ordem
        # importa e custou uma passada: subdividir uma coluna na vertical
        # ANTES de terminar os cortes horizontais faz o corte seguinte incidir
        # sobre a sub-celula, e a coluna do elo 3 passa a ocupar a largura
        # inteira por baixo do elo 4 — dois elos na mesma faixa, e o trilho
        # (corretamente) se abstem num arranjo que era para ser o canonico.
        host.splitDockWidget(self.docas["dom"], self._nova_doca("tape"), H)
        host.splitDockWidget(self.docas["tape"], self._nova_doca("conduto"), H)
        host.splitDockWidget(self.docas["conduto"], self._nova_doca("matriz"), H)
        host.splitDockWidget(self.docas["matriz"], self._nova_doca("hud"), H)

        # DEPOIS as subdivisoes, cada uma dentro da coluna do seu elo.
        host.splitDockWidget(self.docas["tape"], self._nova_doca("players"), V)
        host.splitDockWidget(self.docas["matriz"], self._nova_doca("footprint"), V)
        host.splitDockWidget(self.docas["footprint"], self._nova_doca("perfil"), H)
        host.splitDockWidget(self.docas["footprint"], self._nova_doca("delta"), V)
        host.splitDockWidget(self.docas["hud"], self._nova_doca("metodo"), V)
        host.splitDockWidget(self.docas["metodo"], self._nova_doca("regras"), V)
        # A camada ASG-like nasce escondida nos quatro workspaces históricos.
        # No Ctrl+5 ela se torna a superfície operacional inteira; manter os
        # demais painéis simultaneamente visíveis a confinaria à antiga
        # coluna de decisão e esconderia justamente Matriz e Decisão.
        host.splitDockWidget(self.docas["hud"], self._nova_doca("asg"), V)

        # O bookmap nasce TABULADO com o DOM: os dois respondem a mesma
        # pergunta (onde esta a liquidez) em escalas de tempo diferentes, e
        # ocupam a mesma coluna do elo 1.
        host.tabifyDockWidget(self.docas["dom"], self._nova_doca("bookmap"))

        # Transporte e meta: rodape da area de docking, FORA da cadeia.
        host.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self._nova_doca("replay")
        )
        host.splitDockWidget(self.docas["replay"], self._nova_doca("trilha"), H)

        host.resizeDocks(
            [self.docas["dom"], self.docas["tape"], self.docas["conduto"],
             self.docas["matriz"], self.docas["hud"]],
            [300, 220, LARGURA_CONDUTO, 460, LARGURA_DECISAO],
            H,
        )
        # As alturas da coluna da DECISAO vem da geometria dos proprios
        # paineis (`altura_natural`), e nao de tres numeros escolhidos a olho:
        # o primeiro retrato saiu com `PainelRegras` espremido e as duas
        # ultimas familias desenhadas por cima do rodape `MODO SINAIS`, que e
        # a linha que diz que o produto nao envia ordem. Ressalva coberta por
        # dado e o modo de falha que esta rodada inteira existe para nao ter.
        host.resizeDocks(
            [self.docas["hud"], self.docas["metodo"], self.docas["regras"]],
            [220, altura_natural_metodo(self.densidade) + ALTURA_CABECALHO_DOCA, 520],
            V,
        )

    def _conferir_eixos(self) -> None:
        """`ConfigDelta.timeframe_ns` tem de bater com `ConfigOperacao`.

        Nao "corrige" nada: se as duas configuracoes discordam, quem esta
        errado e quem montou, e o painel de delta ja acende `EIXOS ≠` sozinho
        — comportamento correto, e nao defeito. O que a janela faz e deixar a
        divergencia ESCRITA na trilha, com os dois numeros, para o operador
        nao precisar deduzir do painel por que o eixo nao alinha.
        """
        seu = self.config.delta.timeframe_ns
        meu = self.config.timeframe_ns
        if seu != meu:
            self.trilha.aviso(
                "eixos",
                "ConfigDelta.timeframe_ns=%s e ConfigOperacao.timeframe_ns=%s: o "
                "delta acumulado vai acender EIXOS ≠"
                % (formato.formatar_duracao_s(seu / 1e9), formato.formatar_duracao_s(meu / 1e9)),
            )

    # ------------------------------------------------------------- atalhos
    def _instalar_atalhos(self) -> None:
        def liga(sequencia: str, alvo) -> None:
            atalho = QShortcut(QKeySequence(sequencia), self)
            atalho.activated.connect(alvo)
            self._atalhos.append(atalho)

        liga("Ctrl+P", self.alternar_players)
        liga("Ctrl+Shift+D", self.proxima_densidade)
        for digito in range(1, 10):
            liga("Ctrl+%d" % digito, lambda d=digito: self.workspace_por_atalho(d))

    # ---------------------------------------------------------- workspaces
    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def workspace_por_atalho(self, digito: int) -> bool:
        alvo = por_atalho(digito)
        if alvo is None:
            # Ctrl+5..9 existem em §4.1 e ainda nao tem workspace. Silencio
            # seria o atalho parecer quebrado; a trilha diz que ele funcionou
            # e nao havia para onde ir.
            self.trilha.info("workspace", "Ctrl+%d não tem workspace atribuído" % digito)
            return False
        self.aplicar_workspace(alvo)
        return True

    def aplicar_workspace(self, alvo: Workspace, registrar: bool = True) -> None:
        """Troca o arranjo. Esconde doca, nunca destroi painel.

        Destruir e reconstruir a cada `Ctrl+N` reiniciaria o historico de tela
        do footprint e do bookmap toda vez — o operador que fosse ao Bookmap
        conferir uma coisa e voltasse encontraria a grade do Fluxo vazia.
        """
        tamanho_antes = self.size()
        estado = self._estado_salvo(alvo)
        self._host.restoreState(estado if estado is not None else self._estado_de_fabrica)
        # O WorkspaceASG ja agrega DADOS (DOM/Tape/Bookmap/volume),
        # PROCESSAMENTO, MATRIZ, DECISAO e EVIDENCIAS. Ele precisa da area de
        # docking inteira para que as seis linhas da matriz sejam operacionais
        # em 1280x720. Os quatro workspaces historicos continuam usando
        # exatamente ``alvo.docas`` e o estado canonico congelado.
        eh_asg = alvo.nome_exibicao == "OPERADOR B3"
        eh_nexo_ai = alvo.nome_exibicao == "NEXO AI"
        if eh_asg or eh_nexo_ai:
            # O stack ASG so pode ficar visivel depois de receber o retrato
            # mais recente. Se a sessao ainda nao produziu um, o construtor
            # ja deixou um quadro AGUARDANDO legivel em vez de uma area vazia.
            self._hidratar_asg(self._ultimo_instantaneo)
        if self._ultimo_instantaneo is not None:
            self._aplicar_estado_global(
                self._ultimo_instantaneo,
                self._estado_operacional_asg if eh_asg else None,
            )
        visiveis = set() if (eh_asg or eh_nexo_ai) else set(alvo.docas)
        for chave, doca in self.docas.items():
            doca.setVisible(chave in visiveis)
        self._area_operacional.setCurrentWidget(
            self.nexo_ai if eh_nexo_ai else self.asg if eh_asg else self._host
        )
        if eh_asg:
            # ``setCurrentWidget`` resolve a geometria final dos filhos e
            # invalida backings calculados enquanto a pagina estava oculta.
            # Fechar o quadro sincronicamente, antes de devolver o evento de
            # Ctrl+5 ao Qt, impede a exposicao desse backing recem-invalido.
            self.asg.layout().activate()
            for painel in self.asg.todos_paineis:
                painel._quadro()
        self.trilho.setVisible(not (eh_asg or eh_nexo_ai))
        self._workspace = alvo
        self.setWindowTitle(
            f"NEXO AI — Operador B3 — {self.simbolo}"
            if eh_nexo_ai else
            f"Operador B3 — NEXO consultivo — {self.simbolo}"
            if eh_asg else f"FluxoPro — {self.simbolo}"
        )
        self._sincronizar_trilho()
        # Trocar workspace nunca e autorizacao para alterar a geometria da
        # janela. A restauracao explicita tambem neutraliza sizeHints
        # transitórios enquanto o Qt colapsa/expande a arvore de docas.
        self.resize(tamanho_antes)
        if registrar:
            self.trilha.info("workspace", "%s — %s" % (alvo.nome_exibicao, alvo.descricao))
        if not alvo.cadeia_completa:
            self.trilha.aviso(
                "cadeia",
                "o workspace %s não cobre os quatro elos: o trilho vai se abster"
                % alvo.nome,
            )

    def _estado_salvo(self, alvo: Workspace):
        if not self._persistir:
            return None
        from fluxopro.ui import workspace as ws_mod

        try:
            dados = ws_mod.carregar(alvo.nome)
        except (ValueError, OSError) as erro:
            # §3.5: erro nunca e modal, vai para a trilha com o motivo
            # literal. E o arranjo de fabrica assume — um workspace ilegivel
            # nao pode ser motivo para a janela nao abrir.
            self.trilha.erro("workspace", "não li %s: %s" % (alvo.nome, erro))
            return None
        if dados is None:
            return None
        geometria, estado, _extra = dados
        # O formato persistido sempre carregou os dois blobs, mas a janela
        # histórica só restaurava o saveState. Aplicar ambos mantém o
        # workspace do operador e torna o campo ``geometria`` auditável.
        if geometria and not self.restoreGeometry(geometria):
            self.trilha.aviso("workspace", "geometria salva não foi restaurada: %s" % alvo.nome)
        return estado

    def salvar_workspace(self):
        """Grava geometria + estado do arranjo corrente. `None` se desligado."""
        if not self._persistir:
            return None
        from fluxopro.ui import workspace as ws_mod

        try:
            return ws_mod.salvar(
                self._workspace.nome,
                self.saveGeometry(),
                self._host.saveState(),
                {"densidade": self.densidade.nome, "simbolo": self.simbolo},
            )
        except OSError as erro:
            self.trilha.erro("workspace", "não gravei %s: %s" % (self._workspace.nome, erro))
            return None

    def restaurar_geometria(self, geometria) -> bool:
        """Restaura a geometria da janela E aplica a regra da janela orfa."""
        ok = bool(self.restoreGeometry(geometria))
        self.aplicar_regra_da_orfa()
        return ok

    # ------------------------------------------------------- janela orfa
    def _areas_de_tela(self) -> tuple[tuple[QRect, ...], QRect]:
        app = QApplication.instance()
        telas = list(app.screens()) if app is not None else []
        areas = tuple(tela.availableGeometry() for tela in telas)
        primaria = QRect()
        if app is not None and app.primaryScreen() is not None:
            primaria = app.primaryScreen().availableGeometry()
        elif areas:
            primaria = areas[0]
        return areas, primaria

    def aplicar_regra_da_orfa(self) -> tuple[str, ...]:
        """§4.1: janela orfa vai para o primario **com aviso na trilha**.

        Vale para a janela principal E para cada doca destacada — e "cada
        janela destacada guarda monitor + geometria" que §4.1 pede, do lado em
        que da para consertar. Sem isto, restaurar um arranjo de tres monitores
        numa maquina de um monitor abre painel fora da area visivel, que e o
        "defeito classico de terminal" nomeado no documento.
        """
        areas, primaria = self._areas_de_tela()
        if not areas or primaria.isEmpty():
            return ()
        avisos: list[str] = []
        alvos: list[tuple[str, QWidget]] = [("janela principal", self)]
        alvos += [
            (TITULO_DA_DOCA.get(chave, chave), doca)
            for chave, doca in self.docas.items()
            if doca.isFloating() and doca.isVisible()
        ]
        for nome, alvo in alvos:
            antes = alvo.frameGeometry()
            depois, orfa = reancorar(antes, areas, primaria)
            if not orfa:
                continue
            alvo.setGeometry(depois)
            texto = (
                "%s estava fora da área visível (%dx%d em %d,%d); "
                "trazida para o monitor primário em %d,%d"
                % (
                    nome,
                    antes.width(), antes.height(), antes.x(), antes.y(),
                    depois.x(), depois.y(),
                )
            )
            avisos.append(texto)
            self.trilha.aviso("multi-monitor", texto)
        return tuple(avisos)

    # ---------------------------------------------------------- densidade
    def proxima_densidade(self) -> tokens.Densidade:
        indice = tokens.DENSIDADES.index(self.densidade)
        return self.aplicar_densidade(
            tokens.DENSIDADES[(indice + 1) % len(tokens.DENSIDADES)]
        )

    def aplicar_densidade(self, nova: tokens.Densidade) -> tokens.Densidade:
        """Fase 3, item 9: as tres densidades a quente, SEM perder historico.

        A versao anterior **reconstruia** os paineis, e a justificativa dela
        estava certa pela metade: mutar so `painel.densidade` deixaria a
        geometria calculada com a fonte ANTIGA e o texto desenhado com a nova —
        calha estreita, rotulo descartado por F8, e nenhum erro em lugar
        nenhum. O que ela nao tinha era a terceira opcao.

        Os paineis passaram a expor `aplicar_densidade`, que refaz **todo**
        derivado da densidade (as `QFontMetrics` do construtor inclusive) e
        preserva o estado de tela. Entao o custo que estava dito aqui — "o
        historico de tela recomeca" — deixou de existir, e a linha da trilha
        que o anunciava saiu junto: ressalva que sobrevive ao conserto vira
        mentira com selo de honestidade.

        Quem nao expoe o metodo continua sendo reconstruido, e o docking e
        preservado de qualquer forma (`saveState`/`restoreState`).
        """
        if nova is self.densidade:
            return nova
        self.densidade = nova

        # Os que sabem trocar a quente refazem os proprios derivados e ficam
        # de pe; os demais sao reconstruidos como antes.
        preservados = {}
        for chave in self.TROCAM_A_QUENTE:
            painel = self._paineis.get(chave)
            metodo = getattr(painel, "aplicar_densidade", None)
            if painel is not None and callable(metodo):
                metodo(nova)
                preservados[chave] = painel

        estado = self._host.saveState()
        visiveis = {c for c, dc in self.docas.items() if dc.isVisible()}
        asg_antigo = self.asg
        nexo_ai_antigo = self.nexo_ai
        asg_ativo = self._workspace.nome_exibicao == "OPERADOR B3"
        nexo_ai_ativo = self._workspace.nome_exibicao == "NEXO AI"
        antigos = [
            painel
            for chave, painel in self._paineis.items()
            if chave not in preservados
        ]
        for painel in antigos:
            if isinstance(painel, PainelDenso):
                painel.parar_relogio()
        for painel in asg_antigo.todos_paineis:
            painel.parar_relogio()

        self._montar_paineis(preservados=preservados)
        if asg_ativo or nexo_ai_ativo:
            self._hidratar_asg(self._ultimo_instantaneo)
        for chave, doca in self.docas.items():
            if chave == "asg":
                doca.setWidget(self._asg_doca_placeholder)
            else:
                doca.setWidget(self._paineis[chave])
        self._area_operacional.removeWidget(asg_antigo)
        self._area_operacional.addWidget(self.asg)
        self._area_operacional.removeWidget(nexo_ai_antigo)
        self._area_operacional.addWidget(self.nexo_ai)
        self._area_operacional.setCurrentWidget(
            self.nexo_ai if nexo_ai_ativo else self.asg if asg_ativo else self._host
        )
        for painel in antigos:
            painel.setParent(None)
            painel.deleteLater()

        self._host.restoreState(estado)
        for chave, doca in self.docas.items():
            doca.setVisible(chave in visiveis)

        self._leitura = None
        self._sincronizar_trilho()
        self.trilha.info("densidade", nova.nome)
        return nova

    # ------------------------------------------------------------- aparencia
    def _pintar_fundo(self) -> None:
        paleta_qt = self.palette()
        paleta_qt.setColor(QPalette.ColorRole.Window, tokens.BG_BASE)
        paleta_qt.setColor(QPalette.ColorRole.Base, tokens.BG_SURFACE)
        paleta_qt.setColor(QPalette.ColorRole.WindowText, tokens.TEXT_PRIMARY)
        self.setPalette(paleta_qt)
        self.setAutoFillBackground(True)

    @property
    def paineis(self) -> tuple[PainelDenso, ...]:
        """Todo painel da janela — usado para parar relogio e para os testes."""
        base: list[PainelDenso] = [self.topo, self.trilho, self.rodape, self.tarja_replay]
        base += [p for p in self._paineis.values() if isinstance(p, PainelDenso)]
        base += list(self.asg.todos_paineis)
        if self.ressalva is not None:
            base.append(self.ressalva)
        return tuple(base)

    # ------------------------------------------------------------ o trilho
    def faixas_dos_elos(self) -> tuple[tuple[int, int] | None, ...]:
        """A faixa horizontal de cada elo, em coordenadas da JANELA.

        Uniao das docas visiveis e ancoradas do elo. Doca escondida nao entra
        (nao ocupa faixa nenhuma) e doca FLUTUANDO tambem nao — ela esta noutra
        janela, possivelmente noutro monitor, e mapear a coordenada dela para
        esta janela daria um numero sem significado geometrico.
        """
        layout = self._host.layout()
        if layout is not None:
            layout.activate()
        faixas: list[tuple[int, int] | None] = []
        for elo in range(1, N_ELOS + 1):
            esquerda: int | None = None
            direita: int | None = None
            for chave, doca in self.docas.items():
                if ELO_DA_DOCA[chave] != elo or doca.isFloating() or not doca.isVisible():
                    continue
                if not self._host.rect().contains(
                    QRect(doca.mapTo(self._host, doca.rect().topLeft()), doca.size())
                ):
                    # Doca TABULADA atras de outra. Ela continua "visivel" para
                    # o Qt — o `QDockWidget` nao foi escondido, so nao e a aba
                    # da frente — e o Qt a estaciona FORA da area do anfitriao
                    # (x negativo). Sem este corte, a aba de tras contamina a
                    # faixa do elo com uma coluna que ninguem esta vendo: foi
                    # assim que o elo 1 passou a comecar em x = -500.
                    #
                    # O criterio e geometrico e nao `visibleRegion()`: a regiao
                    # visivel so fica correta depois de o sistema expor a
                    # janela de verdade, e o retrato automatico e o teste medem
                    # antes disso.
                    continue
                l = doca.mapTo(self, doca.rect().topLeft()).x()
                r = doca.mapTo(self, doca.rect().topRight()).x()
                esquerda = l if esquerda is None else min(esquerda, l)
                direita = r if direita is None else max(direita, r)
            faixas.append(None if esquerda is None else (esquerda, direita))  # type: ignore[arg-type]
        return tuple(faixas)

    def _sincronizar_trilho(self) -> None:
        """Os cortes SAO as bordas reais das colunas. Uma conta so.

        `activate()` forca o layout a se resolver antes da leitura: sem ele a
        primeira sincronizacao leria a geometria do construtor e o trilho
        nasceria desalinhado ate o primeiro redimensionamento — que num
        retrato automatico nunca vem.
        """
        cortes, motivo = cortes_da_cadeia(self.faixas_dos_elos(), self.trilho.width())
        if cortes is None:
            if motivo != self._motivo_trilho and self.isVisible():
                # So na MUDANCA: `resizeEvent` passa por aqui dezenas de vezes
                # num arrasto, e uma trilha inundada pelo proprio arrasto e uma
                # trilha em que o gap de sequencia do MBO nao vai ser achado.
                self.trilha.aviso("cadeia", "trilho abstém-se — " + motivo)
            self._motivo_trilho = motivo
            self.trilho.definir_arranjo_livre(motivo)
            return
        if self._motivo_trilho and self.isVisible():
            self.trilha.info("cadeia", "arranjo voltou a ser quatro colunas em ordem")
        self._motivo_trilho = ""
        self.trilho.definir_cortes(cortes)

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._sincronizar_trilho()

    def showEvent(self, evento) -> None:  # noqa: N802
        super().showEvent(evento)
        self._sincronizar_trilho()

    # ------------------------------------------------------------- players
    def alternar_players(self) -> None:
        self.definir_players_visivel(not self._players_visivel)

    def definir_players_visivel(self, visivel: bool) -> None:
        """Painel escondido nao gasta quadro — `PainelDenso.hideEvent` para o
        relogio dele, e `_tick` deixa de montar o ranking."""
        if visivel == self._players_visivel:
            return
        self._players_visivel = visivel
        doca = self.docas.get("players")
        if doca is not None:
            doca.setVisible(visivel and "players" in self._workspace.docas)
        self.players.setVisible(visivel)
        if visivel:
            self._quadros_sem_players = 0

    # ------------------------------------------------------------- replay
    def definir_estado_replay(self, estado: EstadoReplay) -> None:
        """A tarja da JANELA INTEIRA, e o transporte, do mesmo estado.

        E o unico caminho pelo qual a tela entra em modo replay: as strips
        recebem o mesmo `ativo` que a tarja, entao nao existe quadro em que a
        tarja diga `▶ REPLAY` e a strip diga `● AO VIVO`. A contradicao que o
        construtor do replay achou morreu em `paineis/strips.rotulo_do_estado`,
        e este metodo e o que garante que as duas afirmacoes tem UMA fonte.
        """
        self._em_replay = estado.ativo
        self.tarja_replay.definir_estado(estado)
        self.tarja_replay.setVisible(estado.ativo)
        self.controles_replay.definir_estado(estado)
        self.topo.definir_modo(estado.texto_tarja if estado.ativo else self._modo,
                               replay=estado.ativo)

    def _ao_buscar_replay(self, timestamp_ns: int) -> None:
        self.trilha.info("replay", "busca para %s" % formato.formatar_hora_ns(timestamp_ns))

    def _ao_mudar_velocidade(self, velocidade: float) -> None:
        self.trilha.info("replay", "velocidade %s" % formato.formatar_sinalizado(velocidade, 2))

    def _ao_alternar_pausa(self, pausado: bool) -> None:
        self.trilha.info("replay", "pausado" if pausado else "tocando")

    # ---------------------------------------------------------------- quadro
    def _tick(self) -> None:
        retrato = self.ponte.ler()
        self._ultimo_instantaneo = retrato
        eventos = self.ponte.drenar_eventos()
        self._n_eventos += len(eventos)

        deteccoes = []
        sinal_do_quadro = None
        for evento in eventos:
            if hasattr(evento, "estagio"):
                sinal_do_quadro = evento
                self._ultimo_sinal = evento
                self._n_sinais += 1
            else:
                deteccoes.append(evento)
        self._n_deteccoes += len(deteccoes)

        self._leitura = derivar(
            sinal_do_quadro,
            self.sessao.agressao if self.sessao is not None else None,
            _DeltaDoRetrato.de(retrato),
            anterior=self._leitura,
        )

        self.dom.aplicar(retrato.livro, retrato.ultimo_preco)
        self.tape.aplicar(retrato.novos_trades)
        self.bookmap.aplicar(
            retrato.livro, retrato.ultimo_preco, retrato.novos_trades
        )
        self.matriz.aplicar(self._leitura, deteccoes)
        self.hud.aplicar(self._contexto(retrato))
        self._aplicar_metodo()
        estado_asg = self._aplicar_asg(retrato)
        self._aplicar_footprint()
        self._aplicar_players()
        self.painel_trilha.aplicar()
        self.conduto.aplicar(retrato, self._n_deteccoes, self._n_sinais)
        self._aplicar_estado_global(retrato, estado_asg)

    def _aplicar_footprint(self) -> None:
        """Footprint, perfil e delta — nesta ordem, e a ordem e o contrato.

        O footprint move os DOIS eixos (recentraliza o preco, rola o tempo). O
        perfil consome a faixa de preco que o footprint acabou de definir; o
        delta consome o numero de colunas do mesmo `EixoTempo`. Invertida, a
        ordem entrega ao perfil a faixa do quadro ANTERIOR — um painel atrasado
        um quadro em relacao ao vizinho com que ele compartilha o eixo.
        """
        # ATE A ONDA PASSADA isto lia `sessao.footprint`, `sessao.perfil_sessao`
        # e `sessao.delta` DIRETO — acumuladores vivos da thread da fonte — e os
        # tres `derivar_*` iteram colecoes deles. Do lado do Qt isso e iterar um
        # dicionario que a outra thread faz crescer: `dictionary changed size
        # during iteration`, que derrubou o primeiro retrato desta composicao
        # com 9.098 negocios. Havia aqui uma guarda que capturava o
        # `RuntimeError`, contava `_quadros_perdidos_corrida` e pulava o quadro
        # — e ela nunca foi o conserto, so um relatorio honesto de que o
        # produto estava perdendo quadros.
        #
        # `app/sessao_fluxo.py` passou a expor `retrato_de_analytics`, no molde
        # de `ui/ponte.Instantaneo`: retrato montado do lado de la e entregue
        # pronto. Nao ha mais o que capturar, entao a guarda saiu.
        if self.sessao is None or not hasattr(self.sessao, "retrato_de_analytics"):
            return
        n_colunas = self.footprint.eixo_tempo.n_colunas
        retrato = self.sessao.retrato_de_analytics(n_colunas)
        if retrato is None:
            # Primeiro quadro do outro lado do lock: a thread da fonte ainda
            # nao montou nenhum. Manter a leitura anterior e o certo — a tela
            # fica um quadro velha, e nao mente.
            return
        leitura_fp = derivar_footprint(
            retrato.footprint, self.footprint.inicio_vivo_ns, retrato.n_colunas
        )
        leitura_pf = derivar_perfil(retrato.perfil_sessao, self.footprint.faixa_visivel)
        leitura_dl = derivar_delta(
            retrato.delta, self.delta.inicio_vivo_ns, retrato.n_colunas
        )
        self.footprint.aplicar(leitura_fp)
        self.perfil.aplicar(leitura_pf)
        self.delta.aplicar(leitura_dl)

    def _aplicar_metodo(self) -> None:
        """`sessao.leitura_do_metodo()` — uma vez por quadro, sem drenar.

        A janela **nao** toca em `sessao.metodo.<componente>`: aqueles sao
        acumuladores vivos da thread da fonte, e ler campo a campo daria uma
        tela costurada de dois instantes — o defeito que `LeituraMetodo` existe
        para tornar impossivel (os cinco carimbos de tempo sao iguais por
        construcao, e o construtor recusa o contrario).
        """
        ler = getattr(self.sessao, "leitura_do_metodo", None) if self.sessao else None
        self.metodo.aplicar(ler() if callable(ler) else None)

    def _hidratar_asg(self, instantaneo: Instantaneo | None) -> EstadoASG | None:
        """Atualiza o ASG antes de o Ctrl+5 expor seu stack."""

        if self.sessao is None:
            return None
        ler = getattr(self.sessao, "retrato_asg", None)
        retrato = ler() if callable(ler) else None
        if retrato is None:
            return None

        dados = DadosASGSnapshot.de_feed(retrato.feed_quality)
        taxa = getattr(self.sessao, "taxa_eventos_s", None)
        if callable(taxa):
            dados = dataclasses.replace(dados, trades_s=float(taxa()))
        estado = dados.estado
        processamento = dataclasses.replace(
            ProcessamentoASGSnapshot.de_maker(retrato.maker), estado=estado
        )
        matriz = dataclasses.replace(
            MatrizASGSnapshot.de_leitura(retrato.leitura), estado=estado
        )
        evidencias = dataclasses.replace(
            TrilhaEvidenciasASGSnapshot.de_maker(retrato.maker), estado=estado
        )

        decisao_bruta = DecisaoASGSnapshot.de_decisao(retrato.decisao)
        if estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}:
            decisao = dataclasses.replace(decisao_bruta, estado=estado)
        else:
            decisao = DecisaoASGSnapshot(
                timestamp_ns=retrato.timestamp_ns,
                estado=estado,
                direcao=DirecaoASG.AGUARDAR,
                titulo="DECISAO BLOQUEADA",
                motivo=(
                    retrato.feed_quality.detail
                    or "Qualidade do feed insuficiente para confirmar"
                ),
                confianca=ConfiancaASG.INDISPONIVEL,
                procedencia=ProcedenciaASG.INDISPONIVEL,
            )
        self.asg.aplicar(
            WorkspaceASGSnapshot(
                timestamp_ns=retrato.timestamp_ns,
                dados=dados,
                processamento=processamento,
                matriz=matriz,
                decisao=decisao,
                evidencias=evidencias,
                estado_operacional=estado,
                contexto_bruto=(
                    ContextoBrutoASGSnapshot.de_instantaneo(
                        instantaneo, retrato.timestamp_ns, estado
                    )
                    if instantaneo is not None else ContextoBrutoASGSnapshot(
                        retrato.timestamp_ns,
                        estado=estado,
                        detalhe="AGUARDANDO RETRATO BRUTO DO MESMO QUADRO",
                    )
                ),
            )
        )
        if instantaneo is not None:
            layout = self.asg.layout()
            if layout is not None:
                layout.activate()
            self.asg.aplicar_mercado(instantaneo)
        self._estado_operacional_asg = estado
        return estado

    def _aplicar_asg(self, instantaneo: Instantaneo) -> EstadoASG | None:
        """Atualiza o workspace ASG visivel com o retrato unico do quadro."""

        if self._workspace.nome_exibicao not in {"OPERADOR B3", "NEXO AI"}:
            return None
        if self._workspace.nome_exibicao == "NEXO AI":
            self.nexo_ai.aplicar_mercado(instantaneo)
        estado = self._hidratar_asg(instantaneo) or self._estado_operacional_asg
        if self._workspace.nome_exibicao == "NEXO AI" and self.asg.snapshot is not None:
            self.nexo_ai.aplicar(self.asg.snapshot)
            self.nexo_ai.aplicar_mercado(instantaneo)
        return estado

    def _aplicar_estado_global(
        self,
        retrato: Instantaneo,
        estado_asg: EstadoASG | None,
    ) -> None:
        """Fecha strips, faixa e ASG sobre uma unica leitura operacional."""

        operacional = (
            None
            if estado_asg is None
            else (rotulo_estado_asg(estado_asg), cor_estado_asg(estado_asg))
        )
        self.topo.aplicar(retrato, estado_operacional=operacional)
        self.rodape.aplicar(
            retrato,
            self.dom.p95_ms(),
            self._n_eventos,
            replay=self._em_replay,
            estado_operacional=operacional,
        )
        self._atualizar_faixa(retrato.estado, operacional)

    def desenhar_agora(self) -> None:
        """Fecha um quadro inteiro AGORA — le os dados e forca o desenho."""
        self._tick()
        for painel in self.paineis:
            painel._quadro()

    def _contexto(self, retrato: Instantaneo):
        taxa, volume = TAXA_NEUTRA, 0
        if self.sessao is not None and getattr(self.sessao, "agressao", None) is not None:
            taxa, volume = pressao_da_janela(self.sessao.agressao)
        atribuido = retrato.volume_sessao - retrato.volume_nao_atribuido
        comprador = (atribuido + retrato.delta_sessao) // 2
        vendedor = (atribuido - retrato.delta_sessao) // 2
        return contexto_do_sinal(
            self._ultimo_sinal,  # type: ignore[arg-type]
            saldo_dia=retrato.delta_sessao,
            taxa_compra_janela=taxa,
            volume_janela=volume,
            volume_nao_atribuido=retrato.volume_nao_atribuido,
            volume_comprador_dia=max(0, comprador),
            volume_vendedor_dia=max(0, vendedor),
        )

    def _aplicar_players(self) -> None:
        perfil = getattr(self.sessao, "perfil_player", None) if self.sessao else None
        if perfil is None:
            self.definir_players_visivel(False)
            return
        if not self._players_visivel:
            self._quadros_sem_players += 1
            if self._quadros_sem_players % QUADROS_ENTRE_SONDAGENS:
                return
            if players_de_perfil(perfil, top_n=1):
                self.definir_players_visivel(True)
            return
        linhas = players_de_perfil(perfil, top_n=self.players.top_n)
        self.players.aplicar(linhas)
        if linhas:
            self._quadros_sem_players = 0
        else:
            self._quadros_sem_players += 1
            if self._quadros_sem_players >= CARENCIA_PLAYERS_QUADROS:
                self.definir_players_visivel(False)

    def _atualizar_faixa(
        self,
        estado: EstadoFeed,
        estado_operacional: tuple[str, QColor] | None = None,
    ) -> None:
        chave = (estado, None if estado_operacional is None else estado_operacional[0])
        if chave == self._chave_faixa:
            return
        self._chave_faixa = chave
        self._estado_faixa = estado
        if estado_operacional is not None:
            cor = estado_operacional[1]
        elif estado in (EstadoFeed.VIVO, EstadoFeed.AGUARDANDO):
            cor = QColor(tokens.BG_BASE)  # discreta: sem noticia e boa noticia
        else:
            cor = cor_do_estado(estado)
            self.trilha.registrar(
                Nivel.ERRO if estado is EstadoFeed.SEM_FEED else Nivel.AVISO,
                "feed",
                "estado passou a %s" % estado.name,
            )
        paleta_qt = self.faixa.palette()
        paleta_qt.setColor(QPalette.ColorRole.Window, cor)
        self.faixa.setPalette(paleta_qt)

    # ------------------------------------------------------------ fechamento
    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802
        self._relogio.stop()
        self.salvar_workspace()
        for painel in self.paineis:
            painel.parar_relogio()
        # Solta as assinaturas ANTES de deixar a janela morrer: sem isso o
        # barramento continuaria entregando o pregao inteiro a callbacks de
        # widgets destruidos, que no Qt e falha de segmentacao, nao excecao.
        self.ponte.desligar()
        if self._ao_fechar is not None:
            self._ao_fechar()
        super().closeEvent(evento)
