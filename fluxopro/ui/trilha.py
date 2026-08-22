"""A trilha de eventos — o lugar onde `direcao_visual.md` manda o erro morar.

§3.5 e §4.1 citam a trilha tres vezes e nunca a construiram:

> Erro **nunca** e modal. Modal num pregao e dano. Tudo vai para a trilha, e a
> trilha e consultavel.

> Ao restaurar num arranjo de telas diferente, a janela orfa vai para o
> monitor primario **com aviso na trilha de eventos**.

Ate aqui o rodape escrevia `trilha: N eventos` contando `Deteccao`/`Sinal` do
barramento — um contador sem lugar nenhum para consultar. Este modulo e o
lugar.

## Por que ela e um modelo, e nao um `print`

Duas das tres exigencias acima sao sobre coisas que acontecem **antes de
existir tela** (restaurar workspace, reancorar janela orfa) ou **fora do
caminho de dados** (falha ao ler um arquivo de workspace). Um `logging` nao
serve: o operador nao esta olhando o terminal, e §3.5 diz que a informacao e
consultavel na tela.

## Estado — o criterio do gravador

*"Qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregao
continua?"* (`fluxopro/gravacao/gravador.py`). Aqui a resposta e `CAPACIDADE`:
a trilha e um `deque(maxlen=...)`, e o mais velho cai pelo fim. Ela **nao** e
indexada por evento de mercado, nem por tempo. O contador `total` continua
crescendo — e um inteiro, nao uma colecao — porque "3 de 512 mostrados" e
diferente de "3 aconteceram", e o rodape precisa dizer qual dos dois.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, unique

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

CAPACIDADE = 256
"""Linhas retidas. Teto de MEMORIA, nao de sessao: o pregao dura o dia e a
trilha nao pode crescer com ele."""


@unique
class Nivel(Enum):
    """Tres niveis, e nao cinco: cada nivel a mais e uma cor a mais na tela."""

    INFO = "INFO"
    AVISO = "AVISO"
    ERRO = "ERRO"


_COR_NIVEL = {
    Nivel.INFO: tokens.TEXT_SECONDARY,
    Nivel.AVISO: tokens.ALERT,
    Nivel.ERRO: tokens.DANGER,
}


def cor_do_nivel(nivel: Nivel) -> QColor:
    return _COR_NIVEL[nivel]


@dataclass(frozen=True, slots=True)
class EventoTrilha:
    """Uma linha. `origem` e o nome do subsistema, `texto` e o motivo literal.

    §3.5 pede *"carimbo de tempo e o motivo literal"*. Literal quer dizer que
    o texto nao e um codigo que o leitor tenha de traduzir — a mensagem ja e
    a frase que ele leria num relatorio.
    """

    timestamp_ns: int
    nivel: Nivel
    origem: str
    texto: str

    @property
    def linha(self) -> str:
        return "%s  %-5s  %s · %s" % (
            formato.formatar_hora_ns(self.timestamp_ns),
            self.nivel.value,
            self.origem,
            self.texto,
        )


class TrilhaEventos:
    """Fila limitada, com lock. Escrita de qualquer thread, lida pela do Qt.

    O lock e o mesmo padrao de `ui/ponte.py`: a fonte de dados roda numa
    thread propria e uma falha dela (gap de sequencia no MBO, §3.5 "Erro") tem
    de chegar a trilha sem que a thread do Qt esteja no meio de uma leitura.
    """

    def __init__(self, capacidade: int = CAPACIDADE) -> None:
        self._lock = threading.Lock()
        self._itens: deque[EventoTrilha] = deque(maxlen=capacidade)
        self._total = 0
        self._versao = 0

    def registrar(
        self, nivel: Nivel, origem: str, texto: str, timestamp_ns: int | None = None
    ) -> EventoTrilha:
        evento = EventoTrilha(
            time.time_ns() if timestamp_ns is None else timestamp_ns,
            nivel,
            origem,
            texto,
        )
        with self._lock:
            self._itens.append(evento)
            self._total += 1
            self._versao += 1
        return evento

    def info(self, origem: str, texto: str) -> EventoTrilha:
        return self.registrar(Nivel.INFO, origem, texto)

    def aviso(self, origem: str, texto: str) -> EventoTrilha:
        return self.registrar(Nivel.AVISO, origem, texto)

    def erro(self, origem: str, texto: str) -> EventoTrilha:
        return self.registrar(Nivel.ERRO, origem, texto)

    def recentes(self, n: int | None = None) -> tuple[EventoTrilha, ...]:
        """Do mais NOVO para o mais velho — a ordem em que se le uma trilha."""
        with self._lock:
            itens = tuple(reversed(self._itens))
        return itens if n is None else itens[:n]

    @property
    def total(self) -> int:
        """Quantos aconteceram — nao quantos couberam."""
        with self._lock:
            return self._total

    @property
    def versao(self) -> int:
        """Contador de mudanca, para o painel saber se precisa repintar."""
        with self._lock:
            return self._versao

    def __len__(self) -> int:
        with self._lock:
            return len(self._itens)


ALTURA_LINHA = 16


class PainelTrilha(PainelDenso):
    """A trilha, consultavel. O painel do workspace **Revisao**.

    Estrutura limitada pela TELA: `n_linhas` vem da altura, e so essas sao
    pedidas a `TrilhaEventos.recentes`. O painel nao guarda copia da fila.
    """

    def __init__(
        self,
        trilha: TrilhaEventos,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
    ) -> None:
        super().__init__(parent, cor_fundo=tokens.BG_SURFACE)
        self.trilha = trilha
        self.densidade = densidade
        self._versao_vista = -1
        self._fm = QFontMetrics(tokens.fonte_numero(11))
        self.setMinimumSize(280, 120)

    @property
    def n_linhas(self) -> int:
        return max(0, (self.height() - self.densidade.altura_cabecalho) // ALTURA_LINHA)

    def aplicar(self) -> None:
        versao = self.trilha.versao
        if versao != self._versao_vista:
            self._versao_vista = versao
            self.marcar_tudo_sujo()

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self.marcar_tudo_sujo()

    def rect_linha(self, indice: int) -> QRect:
        y = self.densidade.altura_cabecalho + indice * ALTURA_LINHA
        return QRect(0, y, self.width(), ALTURA_LINHA)

    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        cabecalho = QRect(0, 0, self.width(), self.densidade.altura_cabecalho)
        painter.fillRect(cabecalho, tokens.BG_RAISED)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, cabecalho.bottom(), self.width(), cabecalho.bottom())
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        total = self.trilha.total
        retidos = len(self.trilha)
        # "3 de 512" e o par que impede a trilha de mentir sobre a propria
        # cobertura: um painel que so dissesse "3 eventos" afirmaria que
        # foram 3 quando 509 cairam pelo fim.
        painter.drawText(
            cabecalho.adjusted(8, 0, -8, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "TRILHA DE EVENTOS  ·  %s RETIDOS DE %s"
            % (formato.formatar_inteiro(retidos), formato.formatar_inteiro(total)),
        )

        eventos = self.trilha.recentes(self.n_linhas)
        if not eventos:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(0, cabecalho.bottom(), self.width(), self.height() - cabecalho.height()),
                Qt.AlignmentFlag.AlignCenter,
                "SEM EVENTOS",
            )
            return

        painter.setFont(tokens.fonte_numero(11))
        for indice, evento in enumerate(eventos):
            linha = self.rect_linha(indice)
            if indice % 2:
                painter.fillRect(linha, tokens.BG_BASE)
            painter.setPen(cor_do_nivel(evento.nivel))
            painter.drawText(
                linha.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                evento.linha,
            )
