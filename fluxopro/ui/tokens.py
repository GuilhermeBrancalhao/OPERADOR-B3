"""Tokens de cor, tipografia e densidade — `design/direcao_visual.md` §3.

Tres regras que este modulo existe para impor:

1. **Nenhum painel escreve cor literal.** Toda cor vem daqui, ja como
   `QColor` alocado no import. Alocar `QColor` por celula por quadro e o
   erro classico que derruba FPS: numa grade de 40x6 sao 240 alocacoes
   por quadro que atravessam a fronteira Python<->C++ (§2 mediu 1,04 ms
   so em 7.200 chamadas a uma funcao vazia).

2. **Um eixo direcional so, em todo o produto**: azul = compra/bid/
   agressor comprador, vermelho = venda/ask/agressor vendedor. Sem
   "verde para saldo". Azul<->vermelho sobrevive a deuteranopia e
   protanopia (~8% dos homens); verde<->vermelho nao. Verde e ambar
   ficam livres para o SEGUNDO canal — estado do sistema e evento
   detectado —, e e isso que deixa mostrar "para onde" e "e dai" no
   mesmo pixel sem colisao.

3. **Modo sem cor e teste de regressao, nao enfeite.** `PALETA_SEM_COR`
   zera o eixo direcional; a tela tem de continuar legivel pelo sinal
   explicito (+/-) e pela posicao. Se algum painel so distingue compra de
   venda pela cor, o teste que renderiza nas duas paletas acusa.

Os contrastes anotados foram medidos por `design/bench/contraste_wcag.py`
contra `--bg-base #0B0E13`, e `tests/test_ui_tokens.py` os RECALCULA a
partir destas constantes — numero afirmado em comentario envelhece; numero
recalculado do proprio token, nao.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont

# --------------------------------------------------------------------------
# Superficies
# --------------------------------------------------------------------------
BG_BASE = QColor("#0B0E13")      # fundo da aplicacao, area de grafico
BG_SURFACE = QColor("#161B22")   # corpo de painel
BG_RAISED = QColor("#1F2630")    # cabecalho de painel, linha selecionada
BORDER = QColor("#2A323D")       # separador de coluna, moldura
BORDER_STRONG = QColor("#3D4854")  # painel com foco, divisor bid/ask

# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------
TEXT_PRIMARY = QColor("#E8EDF4")    # 16,43:1 — AAA — numeros vivos, preco
TEXT_SECONDARY = QColor("#9BA9BC")  #  8,10:1 — AAA — rotulos, unidades
TEXT_MUTED = QColor("#66727F")      #  3,94:1 — AA-large — SO em >=14px ou
# conteudo redundante (os digitos estaveis do preco), nunca sozinho
# carregando informacao.

# --------------------------------------------------------------------------
# Eixo direcional
# --------------------------------------------------------------------------
BUY = QColor("#3B9EFF")      # 6,92:1 — bid, agressao compradora, delta +
SELL = QColor("#FF5C6C")     # 6,44:1 — ask, agressao vendedora, delta -
NEUTRAL = QColor("#7D8896")  # 5,37:1 — volume sem direcao, imbalance nulo
NEUTRAL_FORTE = QColor("#BAC4D1")  # 10,96:1
"""O par de `OK_FORTE` para o cinza: preenchimento de CHIP, nao cor de dado.

Mesmo motivo, mesma medida. `NEUTRAL` a 5,37:1 e o token de MENOR luminancia
que ja preencheu chip neste projeto — mais baixo que o `DANGER` (5,45:1) que
a peca do metodo abandonou por medicao. Com texto escuro por cima, o traco do
chip `INFERIDO` viajava quase todo em croma, e croma e o que o canal
subamostra.

`NEUTRAL` continua certo onde e COR DE DADO (imbalance nulo, volume sem
direcao): la o traco e o proprio pixel colorido, nao uma letra escura
apoiada nele.
"""

# --------------------------------------------------------------------------
# Segundo canal — eventos e estado
# --------------------------------------------------------------------------
ABSORPTION = QColor("#FFB224")  # 10,72:1 — absorcao detectada
ALERT = QColor("#F7C948")       # 12,34:1 — pre-sinal, atencao, replay ativo
SIGNAL = QColor("#C77DFF")      #  7,18:1 — CONFIRMADO do motor/sinais.py
POC = QColor("#FFD166")         # 13,41:1 — POC do Volume Profile
VWAP = QColor("#5AC8FA")        # 10,20:1 — linha de VWAP
OK = QColor("#26D07C")          #  9,57:1 — conexao viva, latencia saudavel
OK_FORTE = QColor("#5BE8A5")    # 12,38:1 — MESMO verde, so que carregando o
"""Preenchimento de CHIP quando a leitura e "tudo vivo".

Existe porque `OK` reprovou na lei do canal e nenhum ajuste de corpo resolve.
Medido no retrato: o chip de cobertura, preenchido em `OK`, reteve 37,1% de
traco contra 40,2% do rotulo do trilho que ele qualifica — e ele ja estava a
13px/700, o corpo e o peso maximos da peca. Os chips vizinhos, identicos em
tudo menos no token (`ALERT` 12,34:1, `ABSORPTION` 10,72:1), retiveram 46,4% e
48,3%.

A causa e a segunda metade da lei, escrita em `paineis/metodo.py::
_COR_CONFIANCA`: texto escuro sobre token de baixa luminancia carrega o traco
quase so em CROMA, e o JPEG subamostra croma 2x. `OK` a 9,57:1 e o token de
menor luminancia que ainda preenche chip.

Mesma matiz, mesma leitura ("verde = saudavel"): o que muda e so o quanto do
traco viaja em luminancia. `OK` continua certo para ponto de status e para
linha fina, onde nao ha texto escuro por cima para sustentar.
"""
DANGER = QColor("#FF3B30")      #  5,45:1 — desconectado, erro


@dataclass(frozen=True)
class Paleta:
    """O eixo direcional, indireto de proposito.

    Painel nenhum le `BUY`/`SELL` direto: le `paleta.compra`/`paleta.venda`.
    E o unico ponto onde o modo sem cor consegue entrar sem que cada painel
    conheca a existencia do modo.
    """

    compra: QColor
    venda: QColor
    neutro: QColor
    tem_cor: bool

    def direcional(self, valor: int | float) -> QColor:
        """Cor de um valor com sinal. Zero e neutro, nao compra."""
        if valor > 0:
            return self.compra
        if valor < 0:
            return self.venda
        return self.neutro


PALETA_COR = Paleta(compra=BUY, venda=SELL, neutro=NEUTRAL, tem_cor=True)

# No modo sem cor o eixo inteiro colapsa para UMA cor. Nao e "cinza claro
# para compra e cinza escuro para venda" — isso seria a mesma falha com
# outra roupa, porque luminancia tambem e canal visual. A direcao passa a
# viver so no sinal explicito e na posicao, que e exatamente o que o teste
# precisa provar que basta.
PALETA_SEM_COR = Paleta(
    compra=TEXT_PRIMARY, venda=TEXT_PRIMARY, neutro=TEXT_PRIMARY, tem_cor=False
)


def _mesclar(frente: QColor, fundo: QColor, alfa: float) -> QColor:
    """Achata `frente` sobre `fundo` com opacidade `alfa`, no import.

    Pintar com alfa em tempo de execucao custa blend por pixel a cada
    quadro; a cor achatada e opaca e desenha no caminho rapido.
    """
    return QColor(
        round(frente.red() * alfa + fundo.red() * (1 - alfa)),
        round(frente.green() * alfa + fundo.green() * (1 - alfa)),
        round(frente.blue() * alfa + fundo.blue() * (1 - alfa)),
    )


N_DEGRAUS_INTENSIDADE = 9
_ALFA_MIN, _ALFA_MAX = 0.08, 0.60
"""§3.2 se contradiz aqui, e este e o lado da contradicao que ficou.

O documento pede "opacidade 0,08 -> 0,72 em 9 degraus" E "o texto por cima
sempre `--text-primary` (>=4,8:1 mesmo sobre o degrau mais saturado)". As
duas coisas nao sao verdadeiras ao mesmo tempo: `tests/test_ui_tokens.py`
recalcula e a 0,72 o contraste cai para **3,85:1** — abaixo do minimo AA de
4,5, e bem abaixo do que o proprio documento promete. A 0,60 da 4,79:1, que
e o numero prometido.

Entao a promessa de legibilidade venceu a de saturacao, porque a celula do
footprint existe para mostrar o NUMERO; a cor e o contexto. Perde-se um
pouco de faixa dinamica na ponta da rampa, e o degrau continua monotonico e
distinguivel.

A contradicao so apareceu porque o teste recalcula o contraste do proprio
token em vez de conferir a tabela publicada contra ela mesma."""


def _rampa(cor: QColor) -> tuple[QColor, ...]:
    passo = (_ALFA_MAX - _ALFA_MIN) / (N_DEGRAUS_INTENSIDADE - 1)
    return tuple(
        _mesclar(cor, BG_SURFACE, _ALFA_MIN + passo * i)
        for i in range(N_DEGRAUS_INTENSIDADE)
    )


RAMPA_COMPRA = _rampa(BUY)
RAMPA_VENDA = _rampa(SELL)
RAMPA_NEUTRA = _rampa(NEUTRAL)


def degrau(fracao: float) -> int:
    """Mapeia 0..1 no indice da rampa, com as pontas saturando.

    `fracao` fora de [0,1] nao levanta: um volume acima do maximo conhecido
    da janela e evento normal em pregao, e derrubar o painel por causa
    disso seria trocar um pixel errado por uma tela preta.
    """
    if fracao <= 0.0:
        return 0
    if fracao >= 1.0:
        return N_DEGRAUS_INTENSIDADE - 1
    return int(fracao * N_DEGRAUS_INTENSIDADE)


# --------------------------------------------------------------------------
# Densidade — §3.4. Unidade base 4px; nada de 5, 7, 13.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Densidade:
    nome: str
    altura_linha: int
    fonte_grade: int
    celula_footprint_w: int
    celula_footprint_h: int

    @property
    def altura_cabecalho(self) -> int:
        return 24

    def altura_para(self, n_linhas: int) -> int:
        return n_linhas * self.altura_linha


COMPACTA = Densidade("Compacta", 14, 10, 40, 12)
PADRAO = Densidade("Padrao", 18, 11, 46, 14)
CONFORTAVEL = Densidade("Confortavel", 22, 12, 52, 18)

DENSIDADES = (COMPACTA, PADRAO, CONFORTAVEL)


# --------------------------------------------------------------------------
# Tipografia — §3.3
# --------------------------------------------------------------------------
FAMILIAS_NUMERO = ("Iosevka Term", "JetBrains Mono", "Consolas", "Courier New")
"""Ordem deliberada. Iosevka Term tem avanco 0,5em contra 0,6em das outras:
~17% mais colunas na mesma largura, uma coluna inteira a mais por monitor.
Num produto cuja tese e densidade, isso e a metrica decisiva. As tres
seguintes sao degradacao aceitavel, nao equivalentes — o layout continua
correto porque todas sao monoespacadas, so cabe menos."""

FAMILIAS_UI = ("Inter", "Segoe UI", "Arial")

_cache_fontes: dict[tuple[str, int, int], QFont] = {}


def fonte_numero(tamanho_px: int, peso: int = QFont.Weight.Normal) -> QFont:
    """`QFont` monoespacada, memoizada.

    A memoizacao existe pelo mesmo motivo dos `QColor` pre-alocados: trocar
    de fonte no painter e barato, CONSTRUIR uma fonte por celula nao e.
    """
    chave = ("num", tamanho_px, int(peso))
    fonte = _cache_fontes.get(chave)
    if fonte is None:
        fonte = QFont()
        fonte.setFamilies(list(FAMILIAS_NUMERO))
        fonte.setPixelSize(tamanho_px)
        fonte.setWeight(QFont.Weight(peso))
        # Iosevka ja e monoespacada, mas se NENHUMA das quatro existir na
        # maquina o fallback do sistema pode ser proporcional, e a coluna de
        # numeros passaria a dancar. Estas duas linhas protegem esse caso.
        fonte.setStyleHint(QFont.StyleHint.Monospace)
        fonte.setFixedPitch(True)
        _cache_fontes[chave] = fonte
    return fonte


def fonte_ui(tamanho_px: int, peso: int = QFont.Weight.Normal) -> QFont:
    chave = ("ui", tamanho_px, int(peso))
    fonte = _cache_fontes.get(chave)
    if fonte is None:
        fonte = QFont()
        fonte.setFamilies(list(FAMILIAS_UI))
        fonte.setPixelSize(tamanho_px)
        fonte.setWeight(QFont.Weight(peso))
        _cache_fontes[chave] = fonte
    return fonte


def fonte_rotulo(tamanho_px: int = 10) -> QFont:
    """Cabecalho de coluna: caixa alta, `letter-spacing: .04em` (§3.3)."""
    chave = ("rotulo", tamanho_px, 0)
    fonte = _cache_fontes.get(chave)
    if fonte is None:
        fonte = QFont()
        fonte.setFamilies(list(FAMILIAS_UI))
        fonte.setPixelSize(tamanho_px)
        fonte.setWeight(QFont.Weight.Medium)
        fonte.setCapitalization(QFont.Capitalization.AllUppercase)
        fonte.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104.0)
        _cache_fontes[chave] = fonte
    return fonte
