"""Tema do workspace ASG-like, derivado dos tokens visuais do FluxoPro.

O modulo e pequeno de proposito: ele nomeia papeis da nova superficie sem
criar uma segunda identidade visual.  Todas as cores-base continuam vindo de
``ui.tokens`` e sao alocadas uma unica vez no import, como nos demais paineis
QPainter do projeto.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from fluxopro.ui import tokens

# Superficies
FUNDO = tokens.BG_BASE
PAINEL = tokens.BG_SURFACE
CABECALHO = tokens.BG_RAISED
BORDA = tokens.BORDER
BORDA_FORTE = tokens.BORDER_STRONG

# Identidade das cinco areas. Cor e apenas o segundo canal: cada area tambem
# tem titulo e numero de etapa pintados pelo componente.
DADOS = tokens.VWAP
PROCESSAMENTO = tokens.ABSORPTION
MATRIZ = tokens.SIGNAL
DECISAO = tokens.OK_FORTE
EVIDENCIAS = tokens.NEUTRAL_FORTE

# Chips usam texto escuro sobre fundos de luminancia alta, o mesmo criterio
# medido nos paineis ``metodo`` e ``matriz``.
CHIP_TEXTO = tokens.BG_BASE
CONFIANCA_ALTA = tokens.OK_FORTE
CONFIANCA_MEDIA = tokens.ALERT
CONFIANCA_BAIXA = tokens.ABSORPTION
CONFIANCA_INDISPONIVEL = tokens.NEUTRAL_FORTE

ESTADO_AGUARDANDO = tokens.NEUTRAL_FORTE
ESTADO_DESCONHECIDO = tokens.NEUTRAL_FORTE
ESTADO_AO_VIVO = tokens.OK_FORTE
ESTADO_ATRASADO = tokens.ALERT
ESTADO_SEM_BOOK = tokens.ABSORPTION
ESTADO_ERRO = tokens.DANGER
ESTADO_REPLAY = tokens.POC

# Paleta da superficie NEXO. A referencia fornecida usa preto quase absoluto,
# verde/rosa neon e linhas muito finas. Esta e uma identidade propria, sem
# reutilizar logotipo, avatar ou ativo visual de terceiros.
NEXO_FUNDO = QColor("#030609")
NEXO_PAINEL = QColor("#070C12")
NEXO_PAINEL_ALTO = QColor("#0B1118")
NEXO_GRADE = QColor("#17232C")
NEXO_CIANO = QColor("#53D5E8")
NEXO_VERDE = QColor("#26F58A")
NEXO_ROSA = QColor("#FF3F68")
NEXO_AMARELO = QColor("#F5D547")
NEXO_TEXTO = QColor("#DCE9EC")
NEXO_MUTED = QColor("#6F858D")


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


NEXO_VERDE_FAIXA = _com_alpha(NEXO_VERDE, 34)
NEXO_ROSA_FAIXA = _com_alpha(NEXO_ROSA, 34)


# Pre-alocados: construir QColor dentro de uma linha quente de QPainter custa
# uma travessia Python/C++ por celula.
FUNDO_COMPRA = _com_alpha(tokens.BUY, 38)
FUNDO_VENDA = _com_alpha(tokens.SELL, 38)
FUNDO_ALERTA = _com_alpha(tokens.ALERT, 28)
FUNDO_ERRO = _com_alpha(tokens.DANGER, 30)
FUNDO_NEUTRO = _com_alpha(tokens.NEUTRAL, 22)


__all__ = [
    "BORDA",
    "BORDA_FORTE",
    "CABECALHO",
    "CHIP_TEXTO",
    "CONFIANCA_ALTA",
    "CONFIANCA_BAIXA",
    "CONFIANCA_INDISPONIVEL",
    "CONFIANCA_MEDIA",
    "DADOS",
    "DECISAO",
    "ESTADO_AGUARDANDO",
    "ESTADO_AO_VIVO",
    "ESTADO_ATRASADO",
    "ESTADO_DESCONHECIDO",
    "ESTADO_ERRO",
    "ESTADO_REPLAY",
    "ESTADO_SEM_BOOK",
    "EVIDENCIAS",
    "FUNDO",
    "FUNDO_ALERTA",
    "FUNDO_COMPRA",
    "FUNDO_ERRO",
    "FUNDO_NEUTRO",
    "FUNDO_VENDA",
    "MATRIZ",
    "NEXO_AMARELO",
    "NEXO_CIANO",
    "NEXO_FUNDO",
    "NEXO_GRADE",
    "NEXO_MUTED",
    "NEXO_PAINEL",
    "NEXO_PAINEL_ALTO",
    "NEXO_ROSA",
    "NEXO_ROSA_FAIXA",
    "NEXO_TEXTO",
    "NEXO_VERDE",
    "NEXO_VERDE_FAIXA",
    "PAINEL",
    "PROCESSAMENTO",
]
