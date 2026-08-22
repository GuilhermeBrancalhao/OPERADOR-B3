"""Volume Profile lateral — POC, VAH, VAL no MESMO eixo de preco do footprint.

§1 do documento de direcao cobra da referencia a fraqueza **F5**: a aba
Profundidade poe compra e venda em eixos de preco diferentes lado a lado, e a
linha 5 da esquerda nao tem relacao nenhuma com a linha 5 da direita. A
correcao adotada aqui nao e "usar a mesma formula nos dois paineis" — formula
copiada diverge na primeira mudanca. E **o mesmo objeto**: este painel recebe
o `EixoPreco` do footprint e nao tem eixo proprio. Alinhamento errado deixa de
ser improvavel e passa a ser impossivel.

## Por que a barra deste painel pode ser comprimento, e a do footprint nao

A lei que este ciclo mediu tres vezes: *grandeza de variacao enorme desenhada
como comprimento, com um rotulo pequeno encarregado de desfazer a confusao,
mente.* Volume de nivel varre ordens de magnitude, entao a pergunta e
obrigatoria.

Tres coisas separam este caso dos tres defeitos de `hud.py`:

1. **O fundo de escala nao e escolhido: e o POC.** Por definicao o POC e o
   nivel de maior volume, entao a barra do POC e SEMPRE exatamente cheia. Nao
   ha catraca a subir, nao ha degrau 1-2-5 a quantizar e nao ha rotulo de
   escala para o canal apagar — a propria barra cheia e a legenda do eixo.
2. **A comparacao e espacial e simultanea, nunca contra a memoria.** Todos os
   niveis dividem UM eixo, dentro do mesmo quadro. O defeito 4 de `hud.py`
   (a catraca) era comparacao TEMPORAL: um valor parado encolhendo porque o
   eixo andou, sem nenhuma segunda barra na tela que denunciasse. Aqui, se o
   POC dobra, a silhueta inteira renormaliza junto e a mudanca e visivel como
   forma.
3. **Barra que arredonda para zero aqui e informacao, nao perda.** Nos
   players, comprimento zero significava "este player sumiu da tela" — falso,
   ele existe. Aqui significa "praticamente nada foi negociado neste preco",
   que e a definicao de LVN e uma das leituras que o perfil existe para dar.
   Por isso **nao ha piso**: piso foi o remendo que fez dezenove das vinte
   barras do ranking ficarem com exatamente 3px, e um piso aqui apagaria
   justamente a distincao entre o nivel vazio e o nivel raso.

O que **nao** e comprimento: o volume em lotes. Esse e numero, alinhado a
direita, unidade fixa — a regra de §3.4 e a mesma correcao que o ranking de
players recebeu.

## A cor da barra e cinza, e isso e uma afirmacao

`--neutral` e o token de "volume sem direcao" (§3.2). O perfil soma agressao
compradora e vendedora do nivel: ele nao tem lado. Pintar de azul ou vermelho
seria inventar direcao a partir de uma soma que a apagou. A direcao daquele
mesmo preco esta desenhada na MESMA LINHA, uma peca a esquerda, dentro das
celulas do footprint — e essa e a composicao: o footprint responde "de que
lado, em qual candle", o perfil responde "quanto, na sessao inteira".

## As duas ressalvas que viajam com o veredito

* **POC empatado.** `analytics/volume_profile.py` desempata pelo preco mais
  baixo e diz na propria docstring que "nao ha convencao universal de
  desempate para POC". Um POC escolhido por criterio arbitrario nao pode sair
  com a mesma marca de um POC unico: quando ha empate, o marcador vira ambar
  e o rotulo vira `POC ≡`, no mesmo glifo, no mesmo retangulo sujo.
* **Volume sem lado.** O RLP anonimiza ate 15% do volume de WDO/WIN. Ele entra
  no `volume_total` de cada nivel — e deve — mas isso significa que a barra
  mais alta pode ser alta por volume cujo agressor ninguem divulgou. O chip do
  cabecalho carrega a fatia, e chip e a forma que a transmissao nao come.

E o corte da area de valor (70%) vai DESENHADO no cabecalho, lido de
`ConfigVolumeProfile`, nunca cravado: uma regua que mente sobre o proprio
corte e pior que regua nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.analytics.volume_profile import ConfigVolumeProfile
from fluxopro.core.eventos import PriceGrid
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso
from fluxopro.ui.paineis.footprint import (
    ALTURA_CHIP_MINIMA,
    CORPO_CHIP,
    MARGEM,
    EixoPreco,
    chip,
    metrica,
    procedencia_de_config,
)

ALTURA_ROTULO = 16
LARGURA_MINIMA_BARRA = 24
ESPESSURA_MARCADOR = 2
"""Dois pixels, e nao um. A reescala de 0,72 do canal transforma 2px em 1,4 e
1px em nada — e o marcador do POC e o pixel mais importante desta coluna."""

GLIFO_ACIMA = "▲"
GLIFO_ABAIXO = "▼"
MARCA_EMPATE = "≡"


@dataclass(frozen=True, slots=True)
class LeituraPerfil:
    """O perfil ja reduzido ao que a tela usa, e ja RECORTADO pela tela.

    `niveis` traz so os precos visiveis: o painel nao guarda o perfil inteiro
    da sessao, que cresce com a amplitude do dia. POC, VAH e VAL, esses, sao
    calculados sobre o perfil COMPLETO — recortar antes de calcular daria um
    POC da janela em vez do POC da sessao, que e outra coisa e nao e a que o
    operador pede.
    """

    niveis: tuple[tuple[int, int], ...] = ()
    poc: int | None = None
    volume_poc: int = 0
    poc_empatado: bool = False
    val: int | None = None
    vah: int | None = None
    pct_area: float = 0.0
    volume_total: int = 0
    volume_sem_lado: int = 0

    @property
    def fracao_sem_lado(self) -> float:
        if self.volume_total <= 0:
            return 0.0
        return self.volume_sem_lado / self.volume_total


def derivar_perfil(perfil, faixa_visivel: tuple[int, int] | None) -> LeituraPerfil:
    """`analytics.volume_profile.VolumeProfile` -> `LeituraPerfil`. Puro.

    `faixa_visivel` vem de `EixoPreco.faixa_visivel` — e o recorte que mantem
    a estrutura do painel limitada pela TELA e nao pela amplitude da sessao.
    """
    if perfil is None or perfil.volume_total <= 0:
        return LeituraPerfil()
    ordenados = perfil.niveis_ordenados()
    poc = perfil.poc
    volume_poc = 0
    empatados = 0
    for _, nivel in ordenados:
        if nivel.volume_total > volume_poc:
            volume_poc = nivel.volume_total
            empatados = 1
        elif nivel.volume_total == volume_poc:
            empatados += 1
    area = perfil.value_area()
    pct = perfil.config.value_area_pct
    if faixa_visivel is None:
        visiveis: tuple[tuple[int, int], ...] = ()
    else:
        baixo, alto = faixa_visivel
        visiveis = tuple(
            (preco, nivel.volume_total)
            for preco, nivel in ordenados
            if baixo <= preco <= alto
        )
    return LeituraPerfil(
        niveis=visiveis,
        poc=poc,
        volume_poc=volume_poc,
        poc_empatado=empatados > 1,
        val=area[0] if area else None,
        vah=area[1] if area else None,
        pct_area=pct,
        volume_total=perfil.volume_total,
        volume_sem_lado=perfil.volume_nao_atribuido,
    )


class PainelPerfil(PainelDenso):
    """A coluna lateral de volume por preco, no eixo do footprint."""

    def __init__(
        self,
        grid: PriceGrid,
        eixo: EixoPreco,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        config: ConfigVolumeProfile | None = None,
    ) -> None:
        super().__init__(parent)
        self.grid = grid
        # NAO ha eixo proprio. Ver a docstring do modulo: o alinhamento com o
        # footprint e por identidade de objeto, nao por coincidencia de conta.
        self.eixo = eixo
        self.densidade = densidade
        self.paleta = paleta
        self.config = config if config is not None else ConfigVolumeProfile()

        self._leitura = LeituraPerfil()
        # Estado desenhado indexado por LINHA DA TELA — limitado por
        # construcao ao que cabe. Indexar por preco faria a estrutura crescer
        # com a amplitude do dia, que e a forma exata do defeito que este
        # projeto encontrou em oito arquivos.
        #
        # E o que se guarda e o RESULTADO GEOMETRICO — `(largura em pixels,
        # degrau da rampa)` — e nao o volume. A diferenca decide a
        # incrementalidade deste painel: a barra e normalizada pelo POC, entao
        # todo negocio no nivel do POC muda o denominador de TODAS as barras.
        # Comparando volumes, a resposta e "tudo mudou" quase todo quadro;
        # comparando pixels, a resposta e "nada mudou" enquanto o POC cresce
        # 0,1%, que e o caso comum. Comparar o que se desenha em vez do que se
        # recebe e o que mantem o painel dentro do portao de 5x.
        self._render: list[tuple[int, int]] = []
        self._versao_eixo = -1
        self._fm_rotulo = metrica(tokens.fonte_rotulo())
        self._fm_chip = metrica(tokens.fonte_rotulo(CORPO_CHIP))
        self.setMinimumSize(120, 200)

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.eixo.y0

    @property
    def area_barras(self) -> QRect:
        return QRect(
            0,
            self._y_corpo,
            self.width(),
            self.eixo.n_linhas * self.eixo.altura_linha,
        )

    @property
    def largura_util(self) -> int:
        """Largura maxima de uma barra — a do POC, sempre.

        Publica porque o teste calcula a expectativa a partir dela, com a
        MESMA conta que o desenho usa."""
        return max(LARGURA_MINIMA_BARRA, self.width() - 2 * MARGEM)

    def rect_barra(self, linha: int) -> QRect:
        """A calha de uma linha. **Publica porque o teste recorta exatamente
        esta faixa** — recorte escrito a parte pode divergir do desenho e o
        teste passa a medir outra coisa sem avisar."""
        altura = max(2, self.eixo.altura_linha - 2)
        return QRect(
            MARGEM,
            self.eixo.y_da_linha(linha) + (self.eixo.altura_linha - altura) // 2,
            self.largura_util,
            altura,
        )

    def largura_da_barra(self, volume: int) -> int:
        """Comprimento da barra de um nivel. Sem piso, de proposito.

        Piso foi o remendo que fez dezenove das vinte barras do ranking de
        players terem exatamente 3px contra 222x de intervalo. Aqui um nivel
        que arredonda para zero e um LVN — e um LVN e informacao, nao perda.
        """
        if self._leitura.volume_poc <= 0 or volume <= 0:
            return 0
        fracao = max(0.0, min(1.0, volume / self._leitura.volume_poc))
        return int(fracao * self.largura_util)

    def _linha_de(self, preco: int | None) -> int | None:
        return self.eixo.linha_do_preco(preco) if preco is not None else None

    def _sujar_linha(self, linha: int | None) -> None:
        if linha is None:
            return
        self.marcar_sujo(QRect(0, self.eixo.y_da_linha(linha), self.width(), self.eixo.altura_linha))

    # ---------------------------------------------------------------- dados
    @property
    def leitura(self) -> LeituraPerfil:
        return self._leitura

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self._render = []
        self._versao_eixo = -1

    def aplicar(self, leitura: LeituraPerfil) -> None:
        """Absorve o quadro. Uma linha cuja GEOMETRIA mudou e uma linha suja."""
        anterior = self._leitura
        self._leitura = leitura

        if self._versao_eixo != self.eixo.versao or len(self._render) != self.eixo.n_linhas:
            # O eixo e do FOOTPRINT. Quando ele recentraliza, toda linha deste
            # painel passa a falar de outro preco — nao ha diff possivel, e
            # fingir que ha seria desenhar o volume de um preco na linha de
            # outro.
            self._versao_eixo = self.eixo.versao
            self._render = [(0, 0)] * self.eixo.n_linhas
            self.marcar_tudo_sujo()

        novos = self._render_de(leitura)
        if not self._tudo_sujo:
            for linha, (velho, novo_valor) in enumerate(zip(self._render, novos)):
                if velho != novo_valor:
                    self._sujar_linha(linha)
            for preco_velho, preco_novo in (
                (anterior.poc, leitura.poc),
                (anterior.val, leitura.val),
                (anterior.vah, leitura.vah),
            ):
                if preco_velho != preco_novo:
                    self._sujar_linha(self._linha_de(preco_velho))
                    self._sujar_linha(self._linha_de(preco_novo))
            if (anterior.poc_empatado, anterior.volume_poc) != (
                leitura.poc_empatado,
                leitura.volume_poc,
            ):
                # O numero de lotes do POC e desenhado na linha do POC: ele
                # muda mesmo quando nenhum pixel de barra muda.
                self._sujar_linha(self._linha_de(leitura.poc))
            # O cabecalho suja pelo que ele MOSTRA — o chip arredondado —, e
            # nao pelos numeros crus. O volume da sessao muda a cada negocio;
            # `S/ LADO 6%` nao. Sujar pelo cru poria um retangulo a mais em
            # todo quadro para reescrever os mesmos pixels.
            if _chip_sem_lado(anterior) != _chip_sem_lado(leitura):
                self.marcar_sujo(QRect(0, 0, self.width(), self._y_corpo))
        self._render = novos

    def _render_de(self, leitura: LeituraPerfil) -> list[tuple[int, int]]:
        """A geometria de cada linha — a MESMA conta que o desenho usa."""
        saida = [(0, 0)] * self.eixo.n_linhas
        if leitura.volume_poc <= 0:
            return saida
        for preco, volume in leitura.niveis:
            linha = self.eixo.linha_do_preco(preco)
            if linha is None:
                continue
            fracao = max(0.0, min(1.0, volume / leitura.volume_poc))
            saida[linha] = (self.largura_da_barra(volume), tokens.degrau(fracao))
        return saida

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            self._desenhar_cabecalho(painter)
        area = self.area_barras
        alvo = area.intersected(regiao)
        if not alvo.isValid():
            return
        if not self._leitura.niveis:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "SEM PERFIL AINDA")
            return
        self._desenhar_area_de_valor(painter, alvo)
        altura = self.eixo.altura_linha
        primeira = max(0, (alvo.top() - self._y_corpo) // altura)
        ultima = min(self.eixo.n_linhas - 1, (alvo.bottom() - self._y_corpo) // altura)
        for linha in range(primeira, ultima + 1):
            self._desenhar_linha(painter, linha)
        self._desenhar_marcadores(painter, alvo)

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        rect = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM, 0, -MARGEM, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        # O CORTE da area de valor, lido da configuracao e desenhado junto do
        # nome: `ÁREA DE VALOR` sem o `70%` e um adjetivo sem numero.
        titulo = "PERFIL · ÁREA %s" % _pct(self._leitura.pct_area or self.config.value_area_pct)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, titulo
        )
        x = MARGEM + self._fm_rotulo.horizontalAdvance(titulo) + 8
        rotulo, cor = procedencia_de_config(type(self.config))
        largura = self._fm_chip.horizontalAdvance(rotulo) + 12
        altura = max(ALTURA_CHIP_MINIMA, rect.height() - 6)
        topo = rect.top() + (rect.height() - altura) // 2
        if x + largura <= rect.right() - MARGEM:
            chip(painter, QRect(x, topo, largura, altura), rotulo, cor)
            x += largura + 8
        # A fatia sem agressor divulgado, em chip. O perfil soma volume de
        # QUALQUER agressor, inclusive o que a B3 nao divulga — sem esta
        # fatia, o POC pareceria um retrato completo do que passou.
        texto = _chip_sem_lado(self._leitura)
        if texto:
            largura = self._fm_chip.horizontalAdvance(texto) + 12
            if x + largura <= rect.right() - MARGEM:
                chip(painter, QRect(x, topo, largura, altura), texto, tokens.NEUTRAL)
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, rect.bottom(), rect.width(), rect.bottom())

    def _desenhar_area_de_valor(self, painter: QPainter, alvo: QRect) -> None:
        """A area de valor como REGIAO no eixo de preco, nao como rotulo.

        VAH e VAL sao posicoes, e posicao e o portador que melhor atravessa o
        canal: uma faixa de dezenas de pixels de altura contra dois glifos de
        10px. A faixa e `--bg-raised` (1,27:1 contra a superficie) porque ela
        e contexto — se competisse com as barras, viraria o dado."""
        leitura = self._leitura
        if leitura.val is None or leitura.vah is None:
            return
        linha_val = self.eixo.linha_do_preco(leitura.val)
        linha_vah = self.eixo.linha_do_preco(leitura.vah)
        topo = self.eixo.y_da_linha(linha_vah) if linha_vah is not None else self.area_barras.top()
        base = (
            self.eixo.y_da_linha(linha_val) + self.eixo.altura_linha
            if linha_val is not None
            else self.area_barras.bottom() + 1
        )
        faixa = QRect(0, topo, self.width(), max(0, base - topo)).intersected(alvo)
        if faixa.isValid():
            painter.fillRect(faixa, tokens.BG_RAISED)

    def _desenhar_linha(self, painter: QPainter, linha: int) -> None:
        if linha >= len(self._render):
            return
        largura, grau = self._render[linha]
        if largura <= 0:
            return
        barra = self.rect_barra(linha)
        # `--neutral`: volume somado nao tem lado, e pinta-lo de azul ou
        # vermelho seria inventar direcao a partir de uma soma que a apagou.
        painter.fillRect(
            QRect(barra.left(), barra.top(), largura, barra.height()),
            tokens.RAMPA_NEUTRA[grau],
        )

    def _desenhar_marcadores(self, painter: QPainter, alvo: QRect) -> None:
        leitura = self._leitura
        # Quantos chips de "fora da tela" ja foram empilhados em cada borda.
        # Sem esta conta, POC e VAL fora da tela pelo mesmo lado sairiam um em
        # cima do outro, e o segundo apagaria o primeiro — a referencia
        # sumiria em silencio, que e o modo de falha que o chip existe para
        # evitar.
        empilhados = {True: 0, False: 0}
        for preco, rotulo in (
            (leitura.vah, "VAH"),
            (leitura.val, "VAL"),
            (leitura.poc, "POC"),
        ):
            if preco is None:
                continue
            e_poc = rotulo == "POC"
            linha = self.eixo.linha_do_preco(preco)
            if linha is None:
                self._desenhar_fora_da_tela(painter, preco, rotulo, e_poc, empilhados)
                continue
            y = self.eixo.y_da_linha(linha)
            if y + self.eixo.altura_linha < alvo.top() or y > alvo.bottom():
                continue
            if e_poc:
                # Ambar quando o desempate foi ARBITRARIO. Mesma forma, mesmo
                # lugar, mesma espessura do caso decidido — se o canal comer
                # uma marca, come as duas.
                cor = tokens.ABSORPTION if leitura.poc_empatado else tokens.POC
                texto = rotulo + (" " + MARCA_EMPATE if leitura.poc_empatado else "")
            else:
                cor, texto = tokens.TEXT_SECONDARY, rotulo
            painter.fillRect(
                QRect(0, y + (self.eixo.altura_linha - ESPESSURA_MARCADOR) // 2, self.width(), ESPESSURA_MARCADOR),
                cor,
            )
            painter.setFont(tokens.fonte_rotulo())
            painter.setPen(cor)
            painter.drawText(
                QRect(0, y, self.width() - 2, self.eixo.altura_linha),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                texto,
            )
            if e_poc:
                painter.setFont(tokens.fonte_numero(10))
                painter.setPen(tokens.TEXT_PRIMARY)
                painter.drawText(
                    QRect(MARGEM, y, self.width() - 2 * MARGEM, self.eixo.altura_linha),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    formato.formatar_inteiro(leitura.volume_poc),
                )

    def _desenhar_fora_da_tela(
        self,
        painter: QPainter,
        preco: int,
        rotulo: str,
        e_poc: bool,
        empilhados: dict[bool, int],
    ) -> None:
        """Referencia fora da janela de preco: chip na borda, com a seta.

        Some-la seria pior que mostra-la: uma coluna sem POC parece uma coluna
        sem POC calculado, e nao um POC que ficou acima da tela. A seta diz o
        lado e o preco vai junto, no mesmo chip."""
        faixa = self.faixa_visivel_ou_none()
        if faixa is None:
            return
        acima = preco > faixa[1]
        seta = GLIFO_ACIMA if acima else GLIFO_ABAIXO
        texto = "%s %s %s" % (seta, rotulo, formato.preco_completo(self.grid, preco))
        largura = self._fm_chip.horizontalAdvance(texto) + 12
        if largura > self.width() - 2 * MARGEM:
            return  # F8
        area = self.area_barras
        nivel = empilhados[acima]
        desvio = nivel * (ALTURA_ROTULO + 2)
        y = area.top() + desvio if acima else area.bottom() - ALTURA_ROTULO - desvio
        if y < area.top() or y + ALTURA_ROTULO > area.bottom():
            return
        empilhados[acima] = nivel + 1
        cor = tokens.POC if e_poc else tokens.TEXT_SECONDARY
        chip(painter, QRect(MARGEM, y, largura, ALTURA_ROTULO), texto, cor)

    def faixa_visivel_ou_none(self) -> tuple[int, int] | None:
        return self.eixo.faixa_visivel


def _chip_sem_lado(leitura: LeituraPerfil) -> str:
    """O texto do chip de volume sem lado — o que o cabecalho realmente mostra."""
    fracao = leitura.fracao_sem_lado
    return "S/ LADO " + _pct(fracao) if fracao > 0 else ""


def _pct(fracao: float) -> str:
    """`0.7` -> `70%`. Percentual sem sinal: fatia nao aponta para lado
    nenhum, e §3.2 exige sinal so de valor DIRECIONAL."""
    return f"{round(fracao * 100)}%"
