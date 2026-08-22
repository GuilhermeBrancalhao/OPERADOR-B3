"""DOM — a escada de precos. `design/direcao_visual.md` §4.3 e §6 fase 1.

Primeiro painel de proposito: e a peca mais usada, a mais simples (1,76 ms
medidos no bench, teto de 566 fps) e a que **valida a fundacao inteira** —
eixo de preco, escada travada, rastro de mudanca e congelamento. Se o
`PainelDenso` estivesse errado, e aqui que apareceria.

Tres decisoes que o Profit Pro erra ou complica, e que aqui sao contrato:

* **A escada nao pula.** O preco central so se move quando o ultimo negocio
  chega perto da borda, e quando move, move por ROLAGEM: os niveis que
  continuam validos deslizam dentro do backing e so a faixa que entrou e
  redesenhada. Uma escada que se recentraliza a cada tick e ilegivel — o
  olho perde a referencia espacial, que e a unica coisa que um DOM oferece
  alem dos numeros.

* **Um eixo de preco so**, com bid a esquerda e ask a direita da MESMA
  coluna central. A aba Profundidade do Profit poe os dois lados em eixos
  diferentes (fraqueza F5 de §1); o SuperDOM do mesmo produto faz certo.

* **Congelar e uma tecla.** `Espaco` trava a escada onde esta, para ler um
  nivel sem que ele fuja. Enquanto congelado, a tarja diz isso — um DOM
  que parece vivo e nao esta e pior que um DOM parado.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import BookSnapshot, PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

QUADROS_RASTRO = 30
"""~0,5 s a 62 Hz. O rastro existe para o olho pegar a mudanca que aconteceu
enquanto ele estava em outra parte da tela; mais longo que isso e a tela
inteira fica acesa e o realce deixa de significar alguma coisa."""

MARGEM_RECENTRALIZAR = 0.25
"""Fracao da escada, em cada ponta, que funciona como zona de conforto.

Com 40 linhas, o preco pode andar 10 niveis antes de a escada mexer. Menor
que isso e a escada se mexe demais; maior e o preco encosta na borda e o
trader perde a vista de um dos lados justo quando ele importa."""


class PainelDOM(PainelDenso):
    """Escada de precos com profundidade agregada dos dois lados."""

    def __init__(
        self,
        grid: PriceGrid,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        n_niveis: int = 40,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        self.densidade = densidade
        self.paleta = paleta
        self.n_niveis = n_niveis

        self._centro: int | None = None
        self._ultimo_preco: int | None = None
        self._congelado = False

        # Estado desenhado, indexado por LINHA (nao por preco): limitado
        # por construcao ao que cabe na tela. Indexar por preco faria a
        # estrutura crescer com o range do dia — a forma exata do defeito
        # que este projeto encontrou em oito arquivos.
        self._qty_bid: list[int] = []
        self._qty_ask: list[int] = []
        self._ord_bid: list[int] = []
        self._ord_ask: list[int] = []
        self._rastro: list[int] = []

        self._max_qty = 1
        self._soma_bid = 0
        self._soma_ask = 0

        self._fm_grade = QFontMetrics(tokens.fonte_numero(densidade.fonte_grade))
        self._fm_preco = QFontMetrics(
            tokens.fonte_numero(densidade.fonte_grade + 1, 500)
        )

        self._x_ord = self._x_qty_bid = self._x_preco = self._x_qty_ask = 0
        self._x_preco_fim = self._x_ord_ask = 0
        self._largura_coluna = 0
        self._largura_barra_max = 1

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(220, 200)
        self._resetar_linhas()

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    @property
    def _altura_rodape(self) -> int:
        return self.densidade.altura_linha

    @property
    def _area_corpo(self) -> QRect:
        return QRect(
            0,
            self._y_corpo,
            self.width(),
            max(0, self.height() - self._y_corpo - self._altura_rodape),
        )

    def _resetar_linhas(self) -> None:
        n = self.n_niveis
        self._qty_bid = [0] * n
        self._qty_ask = [0] * n
        self._ord_bid = [0] * n
        self._ord_ask = [0] * n
        self._rastro = [0] * n

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        util = max(0, altura - self._y_corpo - self._altura_rodape)
        cabem = max(4, util // self.densidade.altura_linha)
        if cabem != self.n_niveis:
            self.n_niveis = cabem
            self._resetar_linhas()
        # Cinco colunas simetricas em torno do preco:
        #
        #   ORD | QTD |  PRECO  | QTD | ORD
        #   <--- bid ---|        |--- ask --->
        #
        # A simetria nao e estetica. O retrato da primeira versao mostrou o
        # problema: a barra de venda comecava na coluna da QUANTIDADE em vez
        # da borda do preco, entao os dois lados tinham escalas visuais
        # diferentes e a comparacao de profundidade — que e a leitura que o
        # DOM existe para dar — ficava enviesada a favor da compra.
        self._largura_coluna = max(24, largura // 5)
        self._x_ord = 0
        self._x_qty_bid = self._largura_coluna
        self._x_preco = self._largura_coluna * 2
        self._x_preco_fim = self._x_preco + self._largura_coluna
        self._x_qty_ask = self._x_preco_fim
        self._x_ord_ask = largura - self._largura_coluna
        # Cada lado tem exatamente o mesmo espaco para crescer.
        self._largura_barra_max = max(1, self._x_preco - 4)

    def _y_da_linha(self, linha: int) -> int:
        return self._y_corpo + linha * self.densidade.altura_linha

    def _preco_da_linha(self, linha: int) -> int:
        # Linha 0 e a mais ALTA da tela = maior preco. Escada de preco cresce
        # para cima, sempre; inverter isso e desorientar quem opera.
        assert self._centro is not None
        return self._centro + (self.n_niveis // 2) - linha

    def _linha_do_preco(self, preco: int) -> int | None:
        if self._centro is None:
            return None
        linha = self._centro + (self.n_niveis // 2) - preco
        return linha if 0 <= linha < self.n_niveis else None

    def _sujar_linha(self, linha: int) -> None:
        """Suja UMA linha da escada, ja com o deslocamento do cabecalho.

        Existe para que nenhuma chamada precise lembrar do `y0`: era esse
        esquecimento que fazia a faixa suja cair 24px acima da linha real.
        """
        self.marcar_linha(linha, self.densidade.altura_linha, y0=self._y_corpo)

    # ---------------------------------------------------------------- dados
    def aplicar(self, livro: BookSnapshot | None, ultimo_preco: int | None) -> None:
        """Absorve um retrato do book. Chamado pela janela, uma vez por quadro."""
        if ultimo_preco is not None and ultimo_preco != self._ultimo_preco:
            anterior = self._ultimo_preco
            self._ultimo_preco = ultimo_preco
            for p in (anterior, ultimo_preco):
                linha = self._linha_do_preco(p) if p is not None else None
                if linha is not None:
                    self._sujar_linha(linha)

        if self._centro is None:
            referencia = ultimo_preco
            if referencia is None and livro is not None:
                referencia = _referencia_do_livro(livro)
            if referencia is None:
                return
            self._centro = referencia
            self.marcar_tudo_sujo()
        elif not self._congelado and ultimo_preco is not None:
            self._talvez_recentralizar(ultimo_preco)

        if livro is not None:
            self._absorver_livro(livro)
        self._envelhecer_rastro()

    def _talvez_recentralizar(self, preco: int) -> None:
        assert self._centro is not None
        folga = max(1, int(self.n_niveis * MARGEM_RECENTRALIZAR))
        linha = self._centro + (self.n_niveis // 2) - preco
        if folga <= linha < self.n_niveis - folga:
            return
        novo_centro = preco
        deslocamento = novo_centro - self._centro  # em ticks
        self._centro = novo_centro
        # Preco SUBINDO desloca a escada para BAIXO na tela: o nivel que
        # estava na linha k passa para k + deslocamento.
        self._deslizar(deslocamento)

    def _deslizar(self, ticks: int) -> None:
        """Move o estado das linhas e rola o backing junto.

        E o unico lugar do painel que troca O(n_linhas) de trabalho por um
        blit; sem isso, cada recentralizacao seria um quadro cheio.
        """
        if ticks == 0:
            return
        if abs(ticks) >= self.n_niveis:
            self._resetar_linhas()
            self.marcar_tudo_sujo()
            return
        for vetor in (self._qty_bid, self._qty_ask, self._ord_bid, self._ord_ask, self._rastro):
            if ticks > 0:
                del vetor[-ticks:]
                vetor[:0] = [0] * ticks
            else:
                k = -ticks
                del vetor[:k]
                vetor.extend([0] * k)
        # So o CORPO rola: cabecalho e rodape sao fixos, e arrasta-los para
        # dentro da escada deixaria a tarja "CONGELADO" viajando entre os
        # precos.
        self.rolar(0, ticks * self.densidade.altura_linha, self._area_corpo)

    def _absorver_livro(self, livro: BookSnapshot) -> None:
        novo_bid = [0] * self.n_niveis
        novo_ask = [0] * self.n_niveis
        novo_ord_bid = [0] * self.n_niveis
        novo_ord_ask = [0] * self.n_niveis
        soma_bid = soma_ask = 0
        maximo = 1

        for nivel in livro.bids:
            soma_bid += nivel.qty
            linha = self._linha_do_preco(nivel.price)
            if linha is not None:
                novo_bid[linha] = nivel.qty
                novo_ord_bid[linha] = nivel.n_orders
                maximo = max(maximo, nivel.qty)
        for nivel in livro.asks:
            soma_ask += nivel.qty
            linha = self._linha_do_preco(nivel.price)
            if linha is not None:
                novo_ask[linha] = nivel.qty
                novo_ord_ask[linha] = nivel.n_orders
                maximo = max(maximo, nivel.qty)

        for linha in range(self.n_niveis):
            mudou = (
                novo_bid[linha] != self._qty_bid[linha]
                or novo_ask[linha] != self._qty_ask[linha]
                or novo_ord_bid[linha] != self._ord_bid[linha]
                or novo_ord_ask[linha] != self._ord_ask[linha]
            )
            if mudou:
                self._rastro[linha] = QUADROS_RASTRO
                self._sujar_linha(linha)

        self._qty_bid = novo_bid
        self._qty_ask = novo_ask
        self._ord_bid = novo_ord_bid
        self._ord_ask = novo_ord_ask
        if (soma_bid, soma_ask) != (self._soma_bid, self._soma_ask):
            self.marcar_sujo(
                QRect(0, self.height() - self._altura_rodape, self.width(), self._altura_rodape)
            )
        self._soma_bid, self._soma_ask = soma_bid, soma_ask
        self._ajustar_escala(maximo)

    def _ajustar_escala(self, maximo: int) -> None:
        """Escala das barras de profundidade — quantizada, com histerese.

        A escala acompanha o maximo VISIVEL e nao o do dia: uma ordem
        gigante 30 niveis abaixo achataria todas as barras do topo e o
        painel viraria uma coluna de nada.

        Mas segui-lo *exatamente* seria pior. Mudar a escala obriga a
        redesenhar todas as barras, e num book vivo o maximo muda quase a
        cada snapshot — o painel repintaria o quadro inteiro dezenas de
        vezes por segundo e o ganho da regiao suja iria embora. Foi um teste
        de sujeira que expos isso: ele reprovou por "tudo sujo" onde
        esperava uma linha, e o teste estava certo sobre o codigo, nao sobre
        si mesmo.

        Entao a escala anda em degraus 1-2-5 por decada (10, 20, 50, 100...),
        o que da no maximo tres reescalas por ordem de grandeza; e so encolhe
        quando o maximo cai abaixo de um QUARTO do degrau, o que impede o
        vaivem de uma escala que oscila entre dois degraus vizinhos.
        """
        alvo = _degrau_1_2_5(maximo)
        if alvo > self._max_qty or maximo * 4 < self._max_qty:
            self._max_qty = max(1, alvo)
            self.marcar_tudo_sujo()

    def _envelhecer_rastro(self) -> None:
        for linha, restante in enumerate(self._rastro):
            if restante > 0:
                self._rastro[linha] = restante - 1
                if restante - 1 == 0:
                    self._sujar_linha(linha)

    # --------------------------------------------------------------- teclado
    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        if evento.key() == Qt.Key.Key_Space:
            self.congelar(not self._congelado)
            evento.accept()
            return
        if evento.key() == Qt.Key.Key_C:
            self.recentralizar()
            evento.accept()
            return
        super().keyPressEvent(evento)

    def congelar(self, congelado: bool) -> None:
        self._congelado = congelado
        self.marcar_tudo_sujo()

    @property
    def congelado(self) -> bool:
        return self._congelado

    def recentralizar(self) -> None:
        if self._ultimo_preco is None:
            return
        self._centro = self._ultimo_preco
        self._resetar_linhas()
        self.marcar_tudo_sujo()

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            self._desenhar_cabecalho(painter)
        rodape_y = self.height() - self._altura_rodape
        if regiao.bottom() >= rodape_y:
            self._desenhar_rodape(painter, rodape_y)
        if self._centro is None:
            self._desenhar_vazio(painter, regiao)
            return

        altura = self.densidade.altura_linha
        # SO as linhas que cruzam a regiao suja. E aqui que o fator 40 mora:
        # uma mudanca de um nivel desenha uma linha, nao quarenta.
        primeira = max(0, (regiao.top() - self._y_corpo) // altura)
        ultima = min(self.n_niveis - 1, (regiao.bottom() - self._y_corpo) // altura)
        for linha in range(primeira, ultima + 1):
            self._desenhar_linha(painter, linha)

    def _desenhar_vazio(self, painter: QPainter, regiao: QRect) -> None:
        painter.setFont(tokens.fonte_ui(14))
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "AGUARDANDO ABERTURA")

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        rect = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(rect, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        alturas = rect.adjusted(4, 0, -4, 0)
        painter.drawText(alturas, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "DOM")
        if self._congelado:
            painter.setPen(tokens.ALERT)
            painter.drawText(
                alturas, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "CONGELADO"
            )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self._y_corpo - 1, self.width(), self._y_corpo - 1)

    def _desenhar_rodape(self, painter: QPainter, y: int) -> None:
        rect = QRect(0, y, self.width(), self._altura_rodape)
        painter.fillRect(rect, tokens.BG_RAISED)
        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        interno = rect.adjusted(4, 0, -4, 0)
        painter.setPen(self.paleta.compra)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "B " + formato.formatar_inteiro(self._soma_bid),
        )
        painter.setPen(self.paleta.venda)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_inteiro(self._soma_ask) + " A",
        )
        total = self._soma_bid + self._soma_ask
        desequilibrio = (self._soma_bid - self._soma_ask) / total if total else 0.0
        painter.setPen(self.paleta.direcional(desequilibrio))
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            formato.formatar_percentual(desequilibrio, casas=1),
        )

    def _desenhar_linha(self, painter: QPainter, linha: int) -> None:
        y = self._y_da_linha(linha)
        altura = self.densidade.altura_linha
        preco = self._preco_da_linha(linha)
        largura = self.width()
        rect_linha = QRect(0, y, largura, altura)

        e_ultimo = preco == self._ultimo_preco
        if e_ultimo:
            painter.fillRect(rect_linha, tokens.BG_RAISED)
        elif self._rastro[linha] > 0:
            # Rastro: a intensidade cai com a idade da mudanca. Usa a rampa
            # do LADO que tem quantidade, para o realce nao inventar direcao.
            fracao = self._rastro[linha] / QUADROS_RASTRO
            indice = tokens.degrau(fracao * 0.6)
            if self._qty_bid[linha] and not self._qty_ask[linha]:
                rampa = tokens.RAMPA_COMPRA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA
            elif self._qty_ask[linha] and not self._qty_bid[linha]:
                rampa = tokens.RAMPA_VENDA if self.paleta.tem_cor else tokens.RAMPA_NEUTRA
            else:
                rampa = tokens.RAMPA_NEUTRA
            painter.fillRect(rect_linha, rampa[indice])

        # Barras de profundidade, do centro para fora. Fundo antes do texto.
        self._barra(painter, linha, y, altura, lado_compra=True)
        self._barra(painter, linha, y, altura, lado_compra=False)

        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        # Numero SOBRE barra vai em `--text-primary`, nunca na cor do lado.
        # O retrato da primeira versao tinha azul sobre azul e vermelho sobre
        # vermelho: a quantidade — o dado — sumia dentro da barra que existe
        # para representa-la. A direcao ja esta na barra, na posicao e na
        # coluna; a cor do texto seria o quarto portador da mesma informacao,
        # pago com a legibilidade do unico dado que so o texto carrega.
        if self._ord_bid[linha]:
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(self._x_ord + 4, y, self._largura_coluna - 8, altura),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(self._ord_bid[linha]),
            )
        if self._qty_bid[linha]:
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                QRect(self._x_qty_bid, y, self._largura_coluna - 8, altura),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                formato.formatar_inteiro(self._qty_bid[linha]),
            )
        if self._qty_ask[linha]:
            painter.setPen(tokens.TEXT_PRIMARY)
            painter.drawText(
                QRect(self._x_qty_ask + 8, y, self._largura_coluna - 8, altura),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                formato.formatar_inteiro(self._qty_ask[linha]),
            )
        if self._ord_ask[linha]:
            painter.setPen(tokens.TEXT_SECONDARY)
            painter.drawText(
                QRect(self._x_ord_ask + 4, y, self._largura_coluna - 8, altura),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                str(self._ord_ask[linha]),
            )

        self._desenhar_preco(painter, preco, y, altura, e_ultimo)

        painter.setPen(tokens.BORDER)
        painter.drawLine(0, y + altura - 1, largura, y + altura - 1)

    def _barra(self, painter: QPainter, linha: int, y: int, altura: int, lado_compra: bool) -> None:
        qty = self._qty_bid[linha] if lado_compra else self._qty_ask[linha]
        if not qty:
            return
        fracao = min(1.0, qty / self._max_qty)
        largura_barra = int(fracao * self._largura_barra_max)
        if largura_barra <= 0:
            return
        rampa = tokens.RAMPA_COMPRA if lado_compra else tokens.RAMPA_VENDA
        if not self.paleta.tem_cor:
            rampa = tokens.RAMPA_NEUTRA
        cor = rampa[tokens.degrau(fracao)]
        # As duas crescem a partir da BORDA DO PRECO, para fora e com o mesmo
        # comprimento maximo: o olho compara dois comprimentos que partem do
        # mesmo eixo, que e a unica comparacao honesta.
        if lado_compra:
            x = self._x_preco - largura_barra
        else:
            x = self._x_preco_fim
        painter.fillRect(QRect(x, y + 1, largura_barra, altura - 2), cor)

    def _desenhar_preco(
        self, painter: QPainter, preco: int, y: int, altura: int, e_ultimo: bool
    ) -> None:
        estavel, vivo = formato.formatar_preco(self.grid, preco)
        fonte = tokens.fonte_numero(self.densidade.fonte_grade + 1, 500 if e_ultimo else 400)
        painter.setFont(fonte)
        metrica = self._fm_preco if e_ultimo else self._fm_grade
        largura_estavel = metrica.horizontalAdvance(estavel)
        largura_vivo = metrica.horizontalAdvance(vivo)
        # Meio da coluna, nao a borda dela. A primeira versao somava a largura
        # inteira e ancorava o preco na BORDA DIREITA, onde ele colidia com a
        # quantidade de venda — dois numeros impressos um por cima do outro,
        # que o retrato mostrou e nenhum teste de comportamento veria.
        centro = self._x_preco + self._largura_coluna // 2
        x = centro - (largura_estavel + largura_vivo) // 2
        caixa = QRect(x, y, largura_estavel, altura)
        # Digitos estaveis em `--text-muted` (§3.2): a parte apagada e
        # redundante, esta contida no numero que o olho ja leu inteiro.
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, estavel)
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            QRect(x + largura_estavel, y, largura_vivo + 2, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            vivo,
        )


def _degrau_1_2_5(valor: int) -> int:
    """Menor numero da forma 1/2/5 x 10^k que cobre `valor`.

    A serie 1-2-5 e a mesma dos eixos de grafico de engenharia, e pela mesma
    razao: cobre uma decada em tres passos com razoes proximas (2x, 2,5x,
    2x), entao nenhuma reescala muda o desenho de forma violenta.
    """
    if valor <= 1:
        return 1
    escala = 1
    while escala < valor:
        for m in (2, 5, 10):
            if m * escala >= valor:
                return m * escala
        escala *= 10
    return escala


def _referencia_do_livro(livro: BookSnapshot) -> int | None:
    if livro.bids and livro.asks:
        return (livro.bids[0].price + livro.asks[0].price) // 2
    if livro.bids:
        return livro.bids[0].price
    if livro.asks:
        return livro.asks[0].price
    return None
