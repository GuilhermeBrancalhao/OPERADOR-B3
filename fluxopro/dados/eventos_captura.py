"""Eventos de borda que não pertencem ao vocabulário do núcleo (`fluxopro.core`).

`FalhaCaptura` existe porque um adaptador de dados ao vivo (ex.: MT5) e o
gravador precisam de um jeito explícito de dizer "aqui pode ter faltado
dado" — o núcleo não tem esse conceito e não deveria: perda de dado é um
problema de borda (rede, polling, disco), não de domínio. Emitir esse evento
em vez de silenciosamente continuar é o que impede um buraco no book/trade
de virar um replay que mente sobre o que realmente aconteceu.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique


@unique
class TipoFalha(Enum):
    GAP_TICKS = "GAP_TICKS"  # polling pode ter pulado ticks (timestamp descontinuo)
    GAP_BOOK = "GAP_BOOK"  # polling de book atrasou alem do limite tolerado
    DESCONEXAO = "DESCONEXAO"  # perda de conexao com a fonte
    RECONEXAO = "RECONEXAO"  # conexao restabelecida apos DESCONEXAO
    ERRO_FONTE = "ERRO_FONTE"  # fonte devolveu erro explicito (ex.: mt5.last_error())


@dataclass(frozen=True, slots=True)
class FalhaCaptura:
    timestamp_ns: int
    symbol: str
    tipo: TipoFalha
    detalhe: str
