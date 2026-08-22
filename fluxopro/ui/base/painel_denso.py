"""`PainelDenso` — backing store + regiao suja + relogio proprio.

`design/direcao_visual.md` §6 chama esta classe de "o ativo mais valioso do
projeto de UI", e o motivo esta em §2: **o mesmo footprint em Qt vai de 13,3
fps repintando o quadro inteiro para 560 fps repintando so o que mudou.**
Fator 40. Nao e microotimizacao — e a diferenca entre um painel que serve
para operar e um que nao serve.

A causa nao e o toolkit. O bench mediu que 7.200 chamadas a uma funcao
**vazia** atraves da fronteira Python<->C++ ja custam 1,04 ms; uma grade
densa repintada inteira faz milhares dessas por quadro so para redesenhar
pixels identicos aos que ja estavam la. Entao a regra desta classe nao e
"desenhe rapido", e **"nao desenhe o que nao mudou"**.

Tres mecanismos, nesta ordem de importancia:

1. **Regiao suja.** Quem muda o estado marca o retangulo afetado. O quadro
   redesenha so esses retangulos, dentro de um clip. Se nada foi marcado, o
   quadro NAO ABRE UM `QPainter` — custa uma comparacao e retorna.

2. **Backing store.** O desenho vai para um `QPixmap` que sobrevive entre
   quadros; o `paintEvent` so copia. Assim o Qt pode pedir repintura por
   qualquer motivo (janela descoberta, troca de aba, DPI) sem que o painel
   precise reconstruir a grade.

3. **Rolagem.** `rolar()` move os pixels que continuam validos dentro do
   proprio backing e suja so a faixa que entrou. E o truque que faz o
   footprint chegar a 560 fps: uma coluna nova por quadro em vez de sessenta.

E o relogio e **proprio**, de 16 ms, desacoplado do tick de mercado. Num
pregao a 5.000 ev/s, deixar o barramento chamar `update()` pediria 5.000
quadros por segundo para uma tela que entrega 60. `ui/ponte.py` guarda os
eventos; aqui eles viram no maximo 62 quadros.
"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from fluxopro.ui import tokens

INTERVALO_QUADRO_MS = 16
"""~62 Hz. Nao 0 ("o mais rapido possivel"): a 0 o Qt reagenda o timer no
fim de cada quadro e o painel come uma CPU inteira para entregar quadros que
o monitor descarta."""

MAX_RETANGULOS_SUJOS = 32
"""Acima disto vale mais colapsar tudo no retangulo que os contem.

Cada retangulo custa uma troca de clip e uma passada do desenho da
subclasse. Depois de algumas dezenas de faixas espalhadas, o custo das
trocas passa o custo de redesenhar o bloco inteiro de uma vez. O numero e
uma escolha conservadora, e o efeito de errar para mais ou para menos e
so de desempenho — nunca de correcao."""


class PainelDenso(QWidget):
    """Classe-mae de todo painel de grade. Subclasse implementa `desenhar`.

    Contrato da subclasse:

    * `desenhar(painter, regiao)` — pinta o conteudo do retangulo `regiao`,
      e **so** dele. Pode assumir que o clip ja esta aplicado (pintar fora
      nao corrompe nada, so desperdica), e deve usar `regiao` para pular o
      que nao interessa: e ai que o ganho de 40x mora.
    * `ao_redimensionar(largura, altura)` — opcional; recalcula geometria
      derivada (quantas linhas cabem, largura de coluna).

    Nada disso e chamado pela thread da fonte de dados. Ver `ui/ponte.py`.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        intervalo_ms: int = INTERVALO_QUADRO_MS,
        cor_fundo: QColor = tokens.BG_SURFACE,
    ) -> None:
        super().__init__(parent)
        # O Qt so limpa o fundo se acharmos que ele precisa. Como o backing
        # cobre 100% da area, limpar seria pintar duas vezes cada pixel.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self.cor_fundo = cor_fundo
        self._backing: QPixmap | None = None
        self._sujos: list[QRect] = []
        self._tudo_sujo = True

        self._amostras_ms: deque[float] = deque(maxlen=512)
        self._quadros_desenhados = 0
        self._quadros_vazios = 0

        self._timer = QTimer(self)
        self._timer.setInterval(intervalo_ms)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._quadro)

    # ------------------------------------------------------------ ciclo de vida
    def iniciar_relogio(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def parar_relogio(self) -> None:
        self._timer.stop()

    def showEvent(self, evento) -> None:  # noqa: N802 — assinatura do Qt
        super().showEvent(evento)
        self.iniciar_relogio()

    def hideEvent(self, evento) -> None:  # noqa: N802
        # Painel escondido (outra aba, janela minimizada) nao gasta quadro.
        # Num terminal com 8 paineis e 3 visiveis, isso e mais da metade do
        # custo de UI que simplesmente nao acontece.
        self.parar_relogio()
        super().hideEvent(evento)

    # ------------------------------------------------------------ sujeira
    def marcar_sujo(self, rect: QRect) -> None:
        """Marca um retangulo para redesenho no proximo quadro."""
        if self._tudo_sujo or not rect.isValid():
            return
        if len(self._sujos) >= MAX_RETANGULOS_SUJOS:
            self.marcar_tudo_sujo()
            return
        self._sujos.append(rect)

    def marcar_linha(
        self, indice: int, altura_linha: int, y0: int = 0, largura: int = -1
    ) -> None:
        """Atalho para grade: suja a faixa horizontal de uma linha.

        `y0` e o topo da area de linhas — a altura do cabecalho, na pratica.
        Ele NAO tem default seguro por acidente: a primeira versao assumia
        zero, e o DOM, que comeca as linhas 24px abaixo, sujava a faixa
        errada por exatamente a altura do cabecalho. O efeito na tela era
        sutil e por isso pior — a linha era redesenhada pela metade e a outra
        metade continuava mostrando o valor ANTIGO, entao um digito aparecia
        cortado ao meio, parecendo um tracinho. Nenhum teste de comportamento
        pega isso; o retrato PNG pegou.
        """
        self.marcar_sujo(
            QRect(
                0,
                y0 + indice * altura_linha,
                self.width() if largura < 0 else largura,
                altura_linha,
            )
        )

    def marcar_tudo_sujo(self) -> None:
        self._tudo_sujo = True
        self._sujos.clear()

    @property
    def tem_sujeira(self) -> bool:
        return self._tudo_sujo or bool(self._sujos)

    def rolar(self, dx: int, dy: int, area: QRect | None = None) -> None:
        """Rola o backing e suja so a faixa que entrou.

        E o mecanismo do footprint: em vez de redesenhar 60 colunas por
        quadro, move as 59 que continuam validas e desenha 1.

        `area` limita a rolagem a um retangulo. Existe porque quase todo
        painel tem cabecalho e rodape FIXOS: rolar o backing inteiro
        arrastaria o cabecalho para dentro do corpo e depois redesenharia a
        faixa errada — os pixels ficariam certos so por acidente, quando a
        area exposta calhasse de cobrir o estrago.
        """
        if self._backing is None or (dx == 0 and dy == 0):
            return
        if self._tudo_sujo:
            return  # vai redesenhar inteiro de qualquer jeito
        alvo = area if area is not None else QRect(0, 0, self.width(), self.height())
        if not alvo.isValid():
            return
        proporcao = self._backing.devicePixelRatio()
        self._backing.scroll(
            int(dx * proporcao),
            int(dy * proporcao),
            _escalar(alvo, proporcao),
        )
        # Os retangulos ja marcados tambem andaram com os pixels — mas so os
        # que estao DENTRO da area rolada. Os de fora ficaram onde estavam.
        movidos: list[QRect] = []
        for r in self._sujos:
            movidos.append(r.translated(dx, dy) if alvo.contains(r) else r)
        self._sujos = movidos

        if dx > 0:
            self.marcar_sujo(QRect(alvo.left(), alvo.top(), dx, alvo.height()))
        elif dx < 0:
            self.marcar_sujo(QRect(alvo.right() + 1 + dx, alvo.top(), -dx, alvo.height()))
        if dy > 0:
            self.marcar_sujo(QRect(alvo.left(), alvo.top(), alvo.width(), dy))
        elif dy < 0:
            self.marcar_sujo(QRect(alvo.left(), alvo.bottom() + 1 + dy, alvo.width(), -dy))

    # ------------------------------------------------------------ desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        """Ponto de extensao. A base so pinta o fundo."""
        painter.fillRect(regiao, self.cor_fundo)

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        """Ponto de extensao opcional."""

    def _quadro(self) -> None:
        """Um quadro. Chamado pelo timer, NUNCA pelo barramento."""
        if not self.tem_sujeira:
            # O caminho mais importante da classe: quando nada mudou, o
            # custo de um quadro e este `if`. Sem ele, um painel parado
            # gastaria o mesmo que um painel em leilao de abertura.
            self._quadros_vazios += 1
            return
        if self._backing is None:
            self._recriar_backing()
            if self._backing is None:
                return

        inicio = time.perf_counter()
        painter = QPainter(self._backing)
        try:
            if self._tudo_sujo:
                regioes = [QRect(0, 0, self.width(), self.height())]
            else:
                regioes = self._sujos
            for regiao in regioes:
                painter.setClipRect(regiao)
                self.desenhar(painter, regiao)
        finally:
            painter.end()
        self._amostras_ms.append((time.perf_counter() - inicio) * 1000.0)
        self._quadros_desenhados += 1

        # Pede ao Qt so a area que mudou. `update()` sem argumento invalidaria
        # o widget inteiro e jogaria fora metade do ganho — o backing estaria
        # certo, mas a copia para a tela seria de quadro cheio.
        if self._tudo_sujo:
            self.update()
        else:
            for regiao in regioes:
                self.update(regiao)
        self._tudo_sujo = False
        self._sujos = []

    def paintEvent(self, evento) -> None:  # noqa: N802
        painter = QPainter(self)
        if self._backing is None:
            painter.fillRect(evento.rect(), self.cor_fundo)
            return
        # Copia so o retangulo pedido: numa janela parcialmente coberta, o
        # Qt pede pouco e nos entregamos pouco.
        painter.drawPixmap(evento.rect(), self._backing, _em_pixels(evento.rect(), self._backing))

    def resizeEvent(self, evento) -> None:  # noqa: N802
        super().resizeEvent(evento)
        self._recriar_backing()
        self.ao_redimensionar(self.width(), self.height())
        self.marcar_tudo_sujo()

    def _recriar_backing(self) -> None:
        largura, altura = self.width(), self.height()
        if largura <= 0 or altura <= 0:
            self._backing = None
            return
        proporcao = self.devicePixelRatioF() or 1.0
        # Backing em pixels de DISPOSITIVO. Sem isso, num monitor a 150%
        # (o padrao do Windows em notebook) o painel inteiro sairia
        # interpolado — e o produto vive de numero de 11px legivel.
        pixmap = QPixmap(int(largura * proporcao), int(altura * proporcao))
        pixmap.setDevicePixelRatio(proporcao)
        pixmap.fill(self.cor_fundo)
        self._backing = pixmap

    # ------------------------------------------------------------ medicao
    def p95_ms(self) -> float:
        """p95 do tempo de PAREDE de um quadro NAO vazio.

        E o numero que `tests/test_ui_desempenho.py` vigia e que o rodape
        mostra ao operador. p95 e nao media de proposito: a licao que este
        projeto pagou oito vezes e que o defeito de crescimento MELHORA a
        media enquanto piora a cauda — o trabalho se represa num evento raro
        em vez de se diluir. Media aqui seria o instrumento cego.

        **E tempo de parede, nao de CPU** — deliberadamente. Com a thread da
        fonte disputando o GIL, boa parte deste numero pode ser ESPERA e nao
        trabalho: medido sob carga do simulador, o custo de CPU do quadro do
        DOM e sub-milissegundo enquanto a parede da 12 ms (ver a tabela em
        `scripts/painel.py`). Trocar por `thread_time` faria o numero parecer
        otimo justamente quando a tela esta travando — e o que o operador
        precisa saber e quanto tempo passou entre um quadro e o proximo, nao
        quanto disso foi culpa de quem.
        """
        if not self._amostras_ms:
            return 0.0
        ordenadas = sorted(self._amostras_ms)
        indice = min(len(ordenadas) - 1, int(len(ordenadas) * 0.95))
        return ordenadas[indice]

    def zerar_medicao(self) -> None:
        self._amostras_ms.clear()
        self._quadros_desenhados = 0
        self._quadros_vazios = 0

    @property
    def quadros_desenhados(self) -> int:
        return self._quadros_desenhados

    @property
    def quadros_vazios(self) -> int:
        return self._quadros_vazios


def _em_pixels(rect: QRect, pixmap: QPixmap) -> QRect:
    return _escalar(rect, pixmap.devicePixelRatio())


def _escalar(rect: QRect, proporcao: float) -> QRect:
    if proporcao == 1.0:
        return rect
    return QRect(
        int(rect.x() * proporcao),
        int(rect.y() * proporcao),
        int(rect.width() * proporcao),
        int(rect.height() * proporcao),
    )
