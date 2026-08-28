"""Regiao VAP — Volume At Price (x 0,00-0,06 · y 0,00-0,56).

Trocado de escada tipo DOM para VAP por pedido do operador: a fonte
(`pesquisa/ferramenta_componentes.md` §5, `f0hrhzhLDVM.txt`) descreve essa
regiao como "um vap, um volume profile, um volume at price" — mas
customizado, nao o perfil classico de plataforma de varejo.

Regras da fonte, com rotulo de confianca:

- **CONFIRMADO, numero exato** — "voce so vai dar importancia pra ela pra
  esses TRES precos que aparecem destacados... do contrario, voce esquece
  ela". So 3 niveis por vez sao "destacados"; o resto e "lixo" na
  linguagem do autor — mostrado apagado (`NEXO_MUTED`), NUNCA escondido (a
  fonte nunca fala em ocultar nivel, so em reduzir a importancia visual).
- **CONFIRMADO** — "quanto maior a barra, mais importancia ela tem": o
  comprimento da barra e o proprio volume negociado naquele preco.
- **CONFIRMADO** — zonas sem barra destacada ("lacunas") sao onde o preco
  "corre mais rapido" — o LVN classico, ja calculado por
  `VolumeProfile.lvn()`.
- **AUSENTE NA FONTE** — o criterio exato de SELECAO dos 3 destacados
  (o autor diz "eu filtrei do jeito que eu gosto" sem revelar a regra).
  Aqui o criterio e o volume total do nivel — maior proxy honesto
  disponivel, rotulado como tal, nunca apresentado como a formula do autor.
- **CONFIRMADO, decisao deliberada de design** — a fonte explicitamente NAO
  poe este painel do lado do grafico de candles ("nao vou por do lado do
  grafico... e para voces desfocarem do grafico"). Este painel continua
  isolado na lateral esquerda, longe do candle M5 — por design, nao por
  limitacao de espaco.

Volume vem de `fluxopro.analytics.volume_profile.VolumeProfile`, alimentado
pelos MESMOS negocios que ja alimentam `estado.serie` — nunca um segundo
feed. Preco em `int` de ticks; a barra e so a fronteira de desenho.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen

from fluxopro.ui import formato, tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

ALTURA_LINHA_MIN = 9
ALTURA_LINHA_MAX = 20
ALTURA_LINHA_ALVO = 10

FRACAO_LANE_PRECO = 0.42

LARGURA_MIN = 24
ALTURA_ROTULO = 12
ALTURA_MIN_PARA_ROTULO = 60


def retangulo_rotulo(rect: QRect) -> QRect:
    """Faixa inferior do rotulo — tambem o alvo de clique do timeframe
    (SESSAO/5M/15M). Funcao PURA, reaproveitada por `desenhar` (pintar) e
    por `PainelNexoMercadoASG.mousePressEvent` (hit-test), mesmo padrao
    de `candles.retangulos_controles`."""

    return QRect(rect.left(), rect.bottom() - ALTURA_ROTULO, rect.width(), ALTURA_ROTULO)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.width() < LARGURA_MIN or rect.height() < ALTURA_LINHA_MIN * 2:
        return

    niveis = estado.vap_niveis
    ultimo = estado.serie[-1][1] if estado.serie else None

    if not niveis:
        _desenhar_indisponivel(painter, rect, ultimo, estado)
        return

    por_tick: dict[int, tuple[int, int, int, bool]] = {
        preco: (volume_total, volume_comprador, volume_vendedor, destacado)
        for preco, volume_total, volume_comprador, volume_vendedor, destacado in niveis
    }
    ticks_conhecidos = list(por_tick.keys())
    if ultimo is not None:
        ticks_conhecidos.append(ultimo)
    tick_min, tick_max = min(ticks_conhecidos), max(ticks_conhecidos)

    reservar_rotulo = rect.height() >= ALTURA_MIN_PARA_ROTULO
    altura_util = rect.height() - (ALTURA_ROTULO if reservar_rotulo else 0)
    n_linhas = max(1, altura_util // ALTURA_LINHA_ALVO)
    altura = max(ALTURA_LINHA_MIN, min(ALTURA_LINHA_MAX, altura_util // n_linhas))

    centro = ultimo if ultimo is not None else round((tick_min + tick_max) / 2)
    centro = min(max(centro, tick_min), tick_max)

    topo = centro + n_linhas // 2
    ticks = list(range(topo, topo - n_linhas, -1))

    maior_volume = max((por_tick.get(t, (0, 0, 0, False))[0] for t in ticks), default=0) or 1

    largura_preco = max(1, int(rect.width() * FRACAO_LANE_PRECO))
    x_barra = rect.left() + largura_preco
    largura_barra = rect.width() - largura_preco

    fonte_preco = tokens.fonte_numero(6, QFont.Weight.DemiBold)
    fonte_qtd = tokens.fonte_numero(6, QFont.Weight.Normal)
    painter.setFont(fonte_preco)
    y_destaque: int | None = None
    for indice, tick in enumerate(ticks):
        y = rect.top() + indice * altura
        volume_total, volume_comprador, volume_vendedor, destacado = por_tick.get(
            tick, (0, 0, 0, False)
        )

        if volume_total <= 0:
            cor, cor_barra = tema_asg.NEXO_MUTED, None
        elif volume_comprador >= volume_vendedor:
            cor, cor_barra = tema_asg.NEXO_VERDE, tema_asg.NEXO_VERDE_FAIXA
        else:
            cor, cor_barra = tema_asg.NEXO_ROSA, tema_asg.NEXO_ROSA_FAIXA

        # Niveis fora dos 3 destacados sao "lixo" na linguagem da fonte:
        # apagados, nunca escondidos — a barra continua real, so perde
        # saturacao/prioridade visual.
        if not destacado and volume_total > 0:
            cor_barra = tema_asg.NEXO_MUTED

        if volume_total > 0 and cor_barra is not None and largura_barra > 2:
            comprimento = max(2, int(largura_barra * volume_total / maior_volume))
            caixa_barra = QRect(x_barra, y + 1, comprimento, max(2, altura - 2))
            # Barra em gradiente (nunca fillRect chapado): pedido do
            # operador ("visual mais moderno... 3D"). Um degrade horizontal
            # sutil, mais claro na base do preco e esmaecendo na ponta —
            # a mesma leitura de "vidro com profundidade" ja usada no visor
            # central (nucleo.py) e no disco do OPERADOR IA (vies.py), nunca
            # uma cor nova inventada para esta regiao.
            gradiente_barra = QLinearGradient(caixa_barra.left(), 0, caixa_barra.right(), 0)
            cor_base = QColor(cor_barra)
            cor_ponta = QColor(cor_barra)
            cor_ponta.setAlpha(max(20, cor_ponta.alpha() // 2))
            gradiente_barra.setColorAt(0.0, cor_base.lighter(115))
            gradiente_barra.setColorAt(1.0, cor_ponta)
            painter.fillRect(caixa_barra, gradiente_barra)
            if destacado:
                painter.setPen(QPen(cor, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(caixa_barra)
                painter.setFont(fonte_qtd)
                painter.drawText(
                    QRect(x_barra + 2, y, largura_barra - 4, altura),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    formato.abreviar(volume_total, com_sinal=False),
                )
                painter.setFont(fonte_preco)

        # POC (preco de maior volume da sessao — "travamento de preco" no
        # pedido do operador): a UNICA marca nesta faixa lateral que nao
        # depende do recorte de `ticks_conhecidos` — sinaliza mesmo quando o
        # POC ja saiu da janela visivel de precos, com uma seta lateral em
        # vez de tentar desenhar uma linha fora da regiao.
        if tick == estado.vap_poc:
            painter.setPen(QPen(tema_asg.NEXO_AMARELO, 2))
            painter.drawLine(rect.left(), y + altura // 2, rect.left() + 3, y + altura // 2)

        if tick == ultimo:
            y_destaque = y
            continue

        painter.setPen(cor if destacado else tema_asg.NEXO_MUTED)
        preco = formato.formatar_preco(estado.grid, tick)
        painter.drawText(
            QRect(rect.left(), y, largura_preco - 3, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{preco[0]}{preco[1]}",
        )

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(x_barra, rect.top(), x_barra, rect.top() + n_linhas * altura)

    if y_destaque is not None and ultimo is not None:
        caixa = QRect(rect.left(), y_destaque, rect.width(), altura)
        painter.fillRect(caixa, tema_asg.NEXO_AMARELO)
        painter.setPen(tema_asg.CHIP_TEXTO)
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        painter.drawText(
            caixa, Qt.AlignmentFlag.AlignCenter, formato.preco_completo(estado.grid, ultimo)
        )

    if reservar_rotulo:
        painter.setFont(tokens.fonte_rotulo(6))
        sufixo_tf = "SESSAO" if estado.vap_timeframe_min <= 0 else f"{estado.vap_timeframe_min}M"
        rotulo = f"VAP {sufixo_tf}"
        if estado.vap_poc is not None:
            preco_poc = formato.formatar_preco(estado.grid, estado.vap_poc)
            painter.setPen(tema_asg.NEXO_AMARELO)
            rotulo = f"VAP {sufixo_tf} · POC {preco_poc[0]}{preco_poc[1]}"
        else:
            painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(
            retangulo_rotulo(rect),
            Qt.AlignmentFlag.AlignCenter,
            f"⇄ {rotulo}",
        )


def _desenhar_indisponivel(
    painter: QPainter, rect: QRect, ultimo: int | None, estado: EstadoNexo
) -> None:
    """Estado honesto quando o VAP ainda nao tem negocio nenhum registrado.

    Nunca desenha barra aqui: sem volume nao ha o que medir, e uma barra de
    comprimento chutado seria volume sintetico.
    """
    if ultimo is not None:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_numero(8, QFont.Weight.DemiBold))
        preco = formato.formatar_preco(estado.grid, ultimo)
        centro = QRect(rect.left(), rect.center().y() - 9, rect.width(), 14)
        painter.drawText(centro, Qt.AlignmentFlag.AlignCenter, f"{preco[0]}{preco[1]}")
        painter.setFont(tokens.fonte_rotulo(6))
        painter.drawText(
            QRect(rect.left(), centro.bottom(), rect.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            "SEM\nVAP",
        )
    else:
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.setFont(tokens.fonte_rotulo(7))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "SEM\nVAP")
