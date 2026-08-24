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
ESTADO_AO_VIVO = tokens.OK_FORTE
ESTADO_ATRASADO = tokens.ALERT
ESTADO_SEM_BOOK = tokens.ABSORPTION
ESTADO_ERRO = tokens.DANGER
ESTADO_REPLAY = tokens.POC


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


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
    "PAINEL",
    "PROCESSAMENTO",
]
