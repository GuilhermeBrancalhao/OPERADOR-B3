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
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

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
from fluxopro.ui.paineis.matriz import (
    MARCA_REGRA,
    ROTULO_CONFIANCA,
    LeituraMotor,
    PainelMatriz,
    derivar,
    regras_do_campo,
)
from fluxopro.ui.paineis.strips import StripRodape, StripTopo, cor_do_estado
from fluxopro.ui.paineis.tape import PainelTape
from fluxopro.ui.ponte import CAPACIDADE_TAPE, EstadoFeed, Instantaneo, PonteFluxo

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


def _separador(vertical: bool) -> QFrame:
    """1px de `--border`. E o unico "cromo" que a area de dados tem.

    `QSplitter` daria arrasto, e foi recusado por duas razoes: o punho e
    desenhado pelo ESTILO DO SISTEMA (V5 pede o contrario) e a geometria
    passaria a depender de onde o usuario largou o punho — o trilho da cadeia
    alinha os segmentos com as colunas, e alinhamento que depende de estado
    nao versionado e alinhamento que um dia sai errado no retrato."""
    linha = QFrame()
    if vertical:
        linha.setFixedWidth(1)
    else:
        linha.setFixedHeight(1)
    linha.setAutoFillBackground(True)
    paleta = linha.palette()
    paleta.setColor(QPalette.ColorRole.Window, tokens.BORDER)
    linha.setPalette(paleta)
    return linha


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

    def definir_cortes(self, cortes: tuple[int, int, int]) -> None:
        if cortes != self._cortes:
            self._cortes = cortes
            self.marcar_tudo_sujo()

    def segmentos(self) -> tuple[QRect, ...]:
        limites = (0, *self._cortes, self.width())
        return tuple(
            QRect(limites[i], 0, max(0, limites[i + 1] - limites[i]), self.height())
            for i in range(len(ETAPAS))
        )

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

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

        y = altura_cabecalho + 4
        for familia, implementadas, total, pior in self._familias:
            self._desenhar_familia(
                painter,
                QRect(0, y, self.width(), ALTURA_LINHA_REGRA),
                familia,
                implementadas,
                total,
                pior,
            )
            y += ALTURA_LINHA_REGRA

        y += 8
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(MARGEM, y, self.width() - 2 * MARGEM, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "LIMIARES EM VIGOR",
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(MARGEM, y + 15, self.width() - MARGEM, y + 15)
        y += 18
        for campo, rotulo in PARAMETROS_EM_VIGOR:
            self._desenhar_parametro(
                painter, QRect(0, y, self.width(), ALTURA_LINHA_PARAMETRO), campo, rotulo
            )
            y += ALTURA_LINHA_PARAMETRO

        self._desenhar_rodape(painter)

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

    def _desenhar_rodape(self, painter: QPainter) -> None:
        """Ancorado embaixo: e a ultima frase da coluna da DECISAO."""
        altura = 34
        rect = QRect(0, self.height() - altura, self.width(), altura)
        if rect.top() <= 0:
            return
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
class JanelaFluxo(QMainWindow):
    """Shell sem cromo, quatro regioes na ordem da cadeia, um relogio de dados."""

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
    ) -> None:
        super().__init__()
        self.ponte = ponte
        self.paleta = paleta
        self.sessao = sessao
        self.config_motor = config_motor if config_motor is not None else ConfigMotorSinais()
        self._ao_fechar = ao_fechar
        self._n_eventos = 0
        self._n_deteccoes = 0
        self._n_sinais = 0
        self._ultimo_sinal: object | None = None
        self._leitura: LeituraMotor | None = None
        self._estado_faixa: EstadoFeed | None = None
        self._quadros_sem_players = 0
        self._players_visivel = True

        self.setWindowTitle(f"FluxoPro — {simbolo}")
        self.resize(1480, 900)
        self._pintar_fundo()

        self.faixa = QFrame()
        self.faixa.setFixedHeight(ALTURA_FAIXA)
        self.faixa.setAutoFillBackground(True)

        self.ressalva = FaixaRessalva(*ressalva) if ressalva[0] else None
        self.topo = StripTopo(simbolo, grid, paleta=paleta)
        self.topo.definir_modo(modo)
        self.trilho = TrilhoCadeia()
        self.rodape = StripRodape()

        # --- elo 1: dados de mercado -------------------------------------
        self.dom = PainelDOM(grid, paleta=paleta, densidade=densidade)
        self.tape = PainelTape(grid, paleta=paleta, densidade=densidade)
        self.players = PainelPlayers(paleta=paleta, densidade=densidade)

        coluna_tape = QWidget()
        pilha_tape = QVBoxLayout(coluna_tape)
        pilha_tape.setContentsMargins(0, 0, 0, 0)
        pilha_tape.setSpacing(0)
        pilha_tape.addWidget(self.tape, 5)
        pilha_tape.addWidget(_separador(vertical=False))
        pilha_tape.addWidget(self.players, 2)

        self.area_dados = QWidget()
        linha_dados = QHBoxLayout(self.area_dados)
        linha_dados.setContentsMargins(0, 0, 0, 0)
        linha_dados.setSpacing(0)
        linha_dados.addWidget(self.dom, 3)
        linha_dados.addWidget(_separador(vertical=True))
        linha_dados.addWidget(coluna_tape, 2)

        # --- elo 2: processamento ----------------------------------------
        self.conduto = PainelConduto()

        # --- elo 3: estado derivado --------------------------------------
        self.matriz = PainelMatriz(
            grid, densidade=densidade, paleta=paleta, config=self.config_motor
        )

        # --- elo 4: decisao ----------------------------------------------
        self.hud = PainelHUD(densidade=densidade, paleta=paleta)
        self.regras = PainelRegras(self.config_motor)

        self.area_decisao = QWidget()
        self.area_decisao.setFixedWidth(LARGURA_DECISAO)
        pilha_decisao = QVBoxLayout(self.area_decisao)
        pilha_decisao.setContentsMargins(0, 0, 0, 0)
        pilha_decisao.setSpacing(0)
        pilha_decisao.addWidget(self.hud)
        pilha_decisao.addWidget(_separador(vertical=False))
        pilha_decisao.addWidget(self.regras, 1)

        # --- corpo: as quatro regioes, na ordem da cadeia -----------------
        self._corpo = QWidget()
        linha = QHBoxLayout(self._corpo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        linha.addWidget(self.area_dados, 5)
        linha.addWidget(_separador(vertical=True))
        linha.addWidget(self.conduto)
        linha.addWidget(_separador(vertical=True))
        linha.addWidget(self.matriz, 4)
        linha.addWidget(_separador(vertical=True))
        linha.addWidget(self.area_decisao)

        central = QWidget()
        coluna = QVBoxLayout(central)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        coluna.addWidget(self.faixa)
        if self.ressalva is not None:
            coluna.addWidget(self.ressalva)
        coluna.addWidget(self.topo)
        coluna.addWidget(self.trilho)
        coluna.addWidget(self._corpo, 1)
        coluna.addWidget(self.rodape)
        self.setCentralWidget(central)

        self._atualizar_faixa(EstadoFeed.AGUARDANDO)
        self._sincronizar_trilho()
        self.dom.setFocus()

        # Recolher/mostrar o ranking de players. Atalho e nao menu: menu e
        # cromo, e a area de dados nao tem cromo (V5).
        self._atalho_players = QShortcut(QKeySequence("Ctrl+P"), self)
        self._atalho_players.activated.connect(self.alternar_players)

        # UM relogio de dados. Os paineis tem os seus proprios relogios de
        # DESENHO (`PainelDenso`), e sao coisas diferentes de proposito: o de
        # dados decide o que a tela sabe, o de desenho decide quanto custa
        # mostrar. Juntar os dois traria de volta o repaint por tick.
        self._relogio = QTimer(self)
        self._relogio.setInterval(INTERVALO_QUADRO_MS)
        self._relogio.setTimerType(Qt.TimerType.PreciseTimer)
        self._relogio.timeout.connect(self._tick)
        self._relogio.start()

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
        base = (
            self.topo,
            self.trilho,
            self.dom,
            self.tape,
            self.players,
            self.conduto,
            self.matriz,
            self.hud,
            self.regras,
            self.rodape,
        )
        return base + ((self.ressalva,) if self.ressalva is not None else ())

    def _sincronizar_trilho(self) -> None:
        """Os cortes do trilho SAO as bordas das colunas. Uma conta so.

        O layout precisa estar resolvido antes da leitura: `activate()` forca
        isso, e sem ele a primeira sincronizacao leria a geometria do
        construtor (tudo em 640x480) e o trilho nasceria desalinhado ate o
        primeiro redimensionamento — que num retrato automatico nunca vem."""
        layout = self._corpo.layout()
        if layout is not None:
            layout.activate()
        cortes = tuple(
            widget.mapTo(self, widget.rect().topRight()).x() + 1
            for widget in (self.area_dados, self.conduto, self.matriz)
        )
        self.trilho.definir_cortes(cortes)  # type: ignore[arg-type]

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
        relogio dele, e `_tick` deixa de montar o ranking. As duas economias
        importam: a de desenho e a maior, a de dados evita ordenar uma lista
        de participantes que ninguem esta olhando."""
        if visivel == self._players_visivel:
            return
        self._players_visivel = visivel
        self.players.setVisible(visivel)
        if visivel:
            self._quadros_sem_players = 0

    # ---------------------------------------------------------------- quadro
    def _tick(self) -> None:
        retrato = self.ponte.ler()
        eventos = self.ponte.drenar_eventos()
        self._n_eventos += len(eventos)

        # Um `Sinal` e ESTADO, nao historia: so o ultimo importa. Uma
        # `Deteccao` e evento, e todas importam — a matriz empilha em slots
        # de tela e as mais velhas caem pelo fim.
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

        # `derivar(None, ...)` NAO e "sem sinal": e "sem sinal NOVO", e ai os
        # campos do motor vem do quadro anterior. `SessaoFluxo` emite `Sinal`
        # so na mudanca de estagio, entao passar o ultimo sinal de novo a cada
        # quadro reaplicaria uma evidencia velha como se fosse deste instante.
        self._leitura = derivar(
            sinal_do_quadro,
            # Lido do lado do Qt enquanto a thread da fonte escreve — e o
            # mesmo caminho de `scripts/retrato_matriz.py`. Sao tres leituras
            # escalares independentes e nenhuma invariante e afirmada ENTRE
            # elas; o que nao se pode fazer e ler assim algo com invariante
            # composta, e por isso o delta vem do `Instantaneo` (montado sob
            # o lock) em vez de `sessao.delta`.
            self.sessao.agressao if self.sessao is not None else None,
            _DeltaDoRetrato.de(retrato),
            anterior=self._leitura,
        )

        self.topo.aplicar(retrato)
        self.dom.aplicar(retrato.livro, retrato.ultimo_preco)
        self.tape.aplicar(retrato.novos_trades)
        self.matriz.aplicar(self._leitura, deteccoes)
        self.hud.aplicar(self._contexto(retrato))
        self._aplicar_players()
        self.conduto.aplicar(retrato, self._n_deteccoes, self._n_sinais)
        # O p95 relatado e o do DOM: e o painel mais denso do elo 1, entao e
        # o que primeiro acusaria uma regressao de desenho.
        self.rodape.aplicar(retrato, self.dom.p95_ms(), self._n_eventos)
        self._atualizar_faixa(retrato.estado)

    def desenhar_agora(self) -> None:
        """Fecha um quadro inteiro AGORA — le os dados e forca o desenho.

        Existe para captura. O relogio de DESENHO de cada painel e assincrono
        e so gasta quadro quando ha sujeira, entao um `grab()` disparado no
        meio do intervalo copiaria o backing do quadro anterior — a tela
        estaria certa 16 ms depois e o PNG, errado para sempre."""
        self._tick()
        for painel in self.paineis:
            painel._quadro()

    def _contexto(self, retrato: Instantaneo):
        taxa, volume = TAXA_NEUTRA, 0
        if self.sessao is not None and getattr(self.sessao, "agressao", None) is not None:
            taxa, volume = pressao_da_janela(self.sessao.agressao)
        # A barra do dia precisa das duas parcelas, e elas saem DERIVADAS do
        # retrato — nao lidas de `sessao.delta`. O construtor do HUD sugeriu
        # `self.sessao.delta.volume_comprador_sessao` e o par vendedor, o que
        # funcionaria e violaria a invariante que esta janela ja respeita: sao
        # tres escalares lidos da thread do Qt enquanto a thread da fonte
        # escreve, e entre eles existe uma invariante COMPOSTA
        # (`total == comprador + vendedor + nao_atribuido`). Uma leitura
        # rasgada daria parcelas que nao somam o total, e a barra desenharia
        # uma proporcao que nunca existiu.
        #
        # O `Instantaneo` traz delta, volume e nao-atribuido montados sob o
        # lock, no mesmo instante. Duas equacoes resolvem as parcelas:
        #     comprador + vendedor = volume - nao_atribuido
        #     comprador - vendedor = delta
        # A divisao por 2 e exata porque soma e diferenca tem sempre a mesma
        # paridade; `//` aqui nao arredonda nada, so evita o float.
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
            # Sem sessao nao ha de onde tirar participante nenhum. Manter o
            # painel na tela seria reservar coluna para um dado que este
            # processo nao tem como obter.
            self.definir_players_visivel(False)
            return
        if not self._players_visivel:
            self._quadros_sem_players += 1
            if self._quadros_sem_players % QUADROS_ENTRE_SONDAGENS:
                return
            # Sondagem barata (top 1) e espacada: o painel recolhido volta
            # sozinho se a fonte comecar a divulgar participante — o que
            # acontece de verdade quando se troca simulador por replay de
            # gravacao no meio do dia.
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

    def _atualizar_faixa(self, estado: EstadoFeed) -> None:
        if estado is self._estado_faixa:
            return
        self._estado_faixa = estado
        if estado in (EstadoFeed.VIVO, EstadoFeed.AGUARDANDO):
            cor = QColor(tokens.BG_BASE)  # discreta: sem noticia e boa noticia
        else:
            cor = cor_do_estado(estado)
        paleta_qt = self.faixa.palette()
        paleta_qt.setColor(QPalette.ColorRole.Window, cor)
        self.faixa.setPalette(paleta_qt)

    # ------------------------------------------------------------ fechamento
    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802
        self._relogio.stop()
        for painel in self.paineis:
            painel.parar_relogio()
        # Solta as assinaturas ANTES de deixar a janela morrer: sem isso o
        # barramento continuaria entregando o pregao inteiro a callbacks de
        # widgets destruidos, que no Qt e falha de segmentacao, nao excecao.
        self.ponte.desligar()
        if self._ao_fechar is not None:
            self._ao_fechar()
        super().closeEvent(evento)
