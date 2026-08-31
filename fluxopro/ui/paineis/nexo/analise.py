"""Regiao de ANALISE DE MERCADO (Claude) dentro do console OPERADOR IA.

Duas responsabilidades, separadas de proposito:

* `dados_do_estado` — traduz o `EstadoNexo` do quadro no dicionario que o
  prompt consome. Funcao PURA: nenhum subprocess, nenhuma thread, nenhum
  QPainter. E ela que garante que a analise fale **dos numeros que estao
  na tela**, e nao de um segundo calculo paralelo — foi o pedido do
  operador ("uma analise explicando conforme os dados que a interface
  oferece");
* `desenhar_analise` — pinta o resultado.

O motor (thread, intervalo, timeout, degradacao) mora em
`fluxopro/analytics/analise_claude.py`. Aqui nao ha rede.

Consultivo: o prompt proibe recomendacao de ordem e o rodape do bloco
repete a ressalva. Nada nesta regiao envia ordem.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from fluxopro.analytics.analise_claude import EstadoAnalise
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

__all__ = ["dados_do_estado", "dados_suficientes", "desenhar_analise",
           "cor_do_cenario", "altura_minima"]

CAMPOS_ESSENCIAIS = ("preco", "dominancia")


def dados_suficientes(dados: dict) -> bool:
    """O quadro ja tem mercado para analisar?

    DEFEITO CORRIGIDO EM 31/08/2026: a analise disparava no PRIMEIRO
    quadro, antes de o replay entregar qualquer negocio, e o Claude
    respondia — corretamente — "Nao ha dados de preco, volume, dominancia
    ou velocidade disponiveis neste momento". Como o piso entre chamadas e
    de 90 s, essa leitura vazia ficava na tela por um minuto e meio, e uma
    chamada paga era gasta para nao dizer nada.

    Exigimos preco E dominancia: sao os dois campos sem os quais qualquer
    frase sobre o mercado seria inventada.
    """

    if not all(dados.get(campo) not in (None, "") for campo in CAMPOS_ESSENCIAIS):
        return False
    # Dominancia ainda INDISPONIVEL e o motor sem leitura, nao um mercado
    # equilibrado: analisar aqui gastaria uma chamada para dizer que o
    # principal insumo esta ausente.
    return str(dados.get("dominancia", "")).upper() != "INDISPONIVEL"

ALTURA_MINIMA = 74


def altura_minima() -> int:
    return ALTURA_MINIMA


def _fmt(valor, casas: int = 2) -> str | None:
    if valor is None:
        return None
    try:
        return f"{float(valor):+.{casas}f}".replace(".", ",")
    except (TypeError, ValueError):
        return None


def _texto_dominancia(snapshot) -> tuple[str | None, str | None]:
    if snapshot is None:
        return None, None
    estado = getattr(getattr(snapshot, "estado", None), "name", None)
    compra = getattr(snapshot, "buy_percent", None)
    venda = getattr(snapshot, "sell_percent", None)
    placar = None
    if compra is not None and venda is not None:
        placar = f"{compra:.0f}% compra / {venda:.0f}% venda"
    return estado, placar


def _texto_sr(snapshot) -> str | None:
    if snapshot is None:
        return None
    zonas = tuple(getattr(snapshot, "zonas", ()) or ())
    tick = getattr(snapshot, "tick_size", 1.0) or 1.0
    dominante = getattr(snapshot, "dominante", None)
    if not zonas:
        return "nenhuma regiao observada"
    descricao = ", ".join(
        f"{z.preco * tick:.1f} ({'/'.join(z.fontes).replace('vap-', '').upper()}, "
        f"{z.toques} testes, forca {z.score * 100:.0f}%)"
        for z in sorted(zonas, key=lambda z: -z.preco)
    )
    if dominante is not None and getattr(dominante.lado, "name", "") != "NEUTRO":
        return f"zona CONFIRMADA {dominante.lado.name} em {dominante.preco * tick:.1f}; {descricao}"
    return f"nenhuma zona confirmada; regioes observadas em {descricao}"


def _hora_do_snapshot(snapshot) -> str | None:
    """`HH:MM:SS` do relógio de MERCADO do quadro (nunca o da máquina): em
    replay a análise precisa falar da hora do pregão gravado."""

    carimbo = getattr(snapshot, "timestamp_ns", None)
    if not carimbo:
        return None
    from datetime import datetime, timezone

    try:
        momento = datetime.fromtimestamp(int(carimbo) / 1_000_000_000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return momento.strftime("%H:%M:%S")


def dados_do_estado(estado: EstadoNexo) -> dict:
    """Dicionario de entrada do prompt, tirado SO do que a tela mostra.

    Campo que a tela nao tem sai ausente (o prompt escreve "sem leitura")
    — nunca zero, que o modelo leria como medicao.
    """

    snapshot = estado.snapshot
    dom_estado, dom_placar = _texto_dominancia(getattr(estado, "dominancia_snapshot", None))

    maker = estado.maker
    ranking = (getattr(maker, "detalhe", "") or "").replace("\n", "; ") or None

    linha_micro = linha_macro = None
    for apelido, linha in (estado.leituras or ()):
        if apelido == "PULSO":
            linha_micro = _fmt(getattr(linha, "forca", None))
        elif apelido == "HORIZONTE":
            linha_macro = _fmt(getattr(linha, "forca", None))

    fase = getattr(getattr(estado, "fase_renko", None), "name", None)
    tijolos = len(tuple(estado.tijolos_renko or ()))
    renko = f"{fase}, {tijolos} tijolos" if fase else None

    ultra = estado.sinal_ultra
    ultra_txt = None
    if ultra is not None:
        direcao = getattr(getattr(ultra, "direcao", None), "name", "NENHUMA")
        ultra_txt = f"direcao {direcao}"

    # As fontes abaixo sao as MESMAS que as regioes ja desenham. A primeira
    # versao deste mapeamento leu `snapshot.ultimo_preco`,
    # `snapshot.volume_sessao` e `snapshot.simbolo` — nenhum dos tres existe
    # em `WorkspaceASGSnapshot`, entao `preco` saia None, o gate de
    # `dados_suficientes` reprovava todo quadro e a analise nunca disparava.
    # Preco e volume vem de `estado.serie`, que e a serie ja congelada no
    # snapshot e usada por `nexo/estatistica.py` e pelo motor de S/R.
    serie = tuple(estado.serie or ())
    tick = float(getattr(estado.grid, "tick_size", 0) or 0) or 1.0
    preco = f"{serie[-1][1] * tick:,.1f}".replace(",", "@").replace(".", ",").replace("@", ".") if serie else None
    volume = sum(int(amostra[3]) for amostra in serie) if serie else None

    return {
        # `WDO_GRID` so carrega tick/decimais — nao ha campo de simbolo
        # nesta fronteira. O contrato negociado nao muda a leitura de fluxo,
        # e o prompt ja diz "mini-dolar WDO na B3": melhor um rotulo honesto
        # e generico do que inventar o vencimento.
        "instrumento": getattr(estado.grid, "simbolo", None) or "WDO (mini-dolar B3)",
        "modo": getattr(getattr(snapshot, "estado_operacional", None), "name", None),
        "hora": _hora_do_snapshot(snapshot),
        "preco": preco,
        "variacao_dia": None,
        "volume": volume,
        "dominancia": dom_estado,
        "placar": dom_placar,
        "micro": linha_micro,
        "macro": linha_macro,
        "divergencia": None,
        "maker": ranking,
        "renko": renko,
        "regime": getattr(getattr(estado, "regime", None), "name", None),
        "suporte_resistencia": _texto_sr(getattr(estado, "sr_snapshot", None)),
        "ultra": ultra_txt,
        "risco_volatilidade": _fmt(getattr(estado, "risco_volatilidade", None)),
    }


_COR_CENARIO = {
    "ALTA": tema_asg.NEXO_VERDE,
    "BAIXA": tema_asg.NEXO_ROSA,
    "LATERAL": tema_asg.NEXO_CIANO,
    "INDEFINIDO": tema_asg.NEXO_MUTED,
}


def cor_do_cenario(cenario: str) -> QColor:
    return _COR_CENARIO.get((cenario or "").upper(), tema_asg.NEXO_MUTED)


def _quebrar(painter: QPainter, texto: str, largura: int, max_linhas: int) -> list[str]:
    """Quebra em palavras respeitando a largura REAL da fonte corrente."""

    metrica = painter.fontMetrics()
    linhas: list[str] = []
    atual = ""
    for palavra in (texto or "").split():
        tentativa = f"{atual} {palavra}".strip()
        if metrica.horizontalAdvance(tentativa) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
            if len(linhas) == max_linhas:
                break
    if atual and len(linhas) < max_linhas:
        linhas.append(atual)
    if len(linhas) == max_linhas and atual and linhas[-1] != atual:
        linhas[-1] = metrica.elidedText(linhas[-1] + " " + atual,
                                        Qt.TextElideMode.ElideRight, largura)
    return linhas


def desenhar_analise(painter: QPainter, rect: QRect, pacote) -> None:
    """Bloco da analise. `pacote` e a tupla publicada pelo painel:
    ``(EstadoAnalise, AnaliseMercado | None, motivo, idade_s)``."""

    if rect.height() < 30 or rect.width() < 120:
        return

    estado_analise, analise, motivo, idade_s = (
        pacote if pacote else (EstadoAnalise.AUSENTE, None, None, None)
    )
    cor = cor_do_cenario(analise.cenario if analise else "")

    # Cabecalho: rotulo + estado do motor. O estado vai SEMPRE, porque uma
    # leitura de 4 minutos atras nao pode parecer de agora.
    faixa = QRect(rect.left(), rect.top(), rect.width(), 13)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(faixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "ANALISE DE MERCADO · CLAUDE")

    if estado_analise is EstadoAnalise.ANALISANDO and analise is None:
        selo, cor_selo = "CONSULTANDO...", tema_asg.NEXO_CIANO
    elif estado_analise is EstadoAnalise.ANALISANDO:
        selo, cor_selo = "ATUALIZANDO...", tema_asg.NEXO_CIANO
    elif estado_analise is EstadoAnalise.ERRO:
        selo, cor_selo = (motivo or "INDISPONIVEL").upper()[:28], tokens.ALERT
    elif estado_analise is EstadoAnalise.PRONTA and idade_s is not None:
        selo, cor_selo = f"HA {idade_s:.0f}S", tema_asg.NEXO_MUTED
    else:
        selo, cor_selo = "SEM ANALISE", tema_asg.NEXO_MUTED
    painter.setPen(cor_selo)
    painter.drawText(faixa, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, selo)

    painter.setPen(QPen(tema_asg.NEXO_GRADE, 1))
    painter.drawLine(rect.left(), faixa.bottom(), rect.right(), faixa.bottom())

    corpo = QRect(rect.left(), faixa.bottom() + 4, rect.width(),
                  max(10, rect.bottom() - faixa.bottom() - 4))
    if analise is None:
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        texto = ("Aguardando a primeira leitura do analista."
                 if estado_analise is not EstadoAnalise.ERRO
                 else f"Analise indisponivel: {motivo or 'motivo nao informado'}.")
        painter.drawText(corpo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, texto)
        return

    # Tarja do cenario + titulo, na cor da direcao lida.
    y = corpo.top()
    tarja = QRect(corpo.left(), y, corpo.width(), 19)
    fundo = QColor(cor)
    fundo.setAlpha(38)
    painter.fillRect(tarja, fundo)
    painter.setPen(QPen(cor, 2))
    painter.drawLine(tarja.left(), tarja.top(), tarja.left(), tarja.bottom())
    painter.setFont(tokens.fonte_ui(10, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(tarja.adjusted(8, 0, -6, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     analise.cenario)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_TEXTO)
    painter.drawText(tarja.adjusted(8, 0, -6, 0),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     analise.titulo)
    y = tarja.bottom() + 4

    # LEITURA e ATENCAO. A reparticao MEDE as duas antes de desenhar
    # qualquer uma: a primeira versao reservava 2 linhas fixas para a
    # ATENCAO, ela usava 3, e a LEITURA — que e a analise em si — saia
    # cortada no meio de uma palavra ("...e o Sinal Ul...").
    largura_texto = corpo.width() - 4
    fonte_corpo = tokens.fonte_ui(7)
    painter.setFont(fonte_corpo)
    passo = painter.fontMetrics().height()
    linhas_totais = (corpo.bottom() - y) // passo
    if linhas_totais < 1:
        return

    linhas_leitura = _quebrar(painter, analise.leitura, largura_texto, 12)
    passo_atencao = passo
    texto_atencao = f"ATENÇÃO · {analise.atencao}" if analise.atencao else ""
    linhas_atencao = _quebrar(painter, texto_atencao, largura_texto, 12) if texto_atencao else []

    # A ATENCAO e reservada INTEIRA antes da leitura: ela e a frase de
    # risco, e meia frase de risco ("...o que fragiliza") e pior que
    # nenhuma. A LEITURA cede as linhas que faltarem — ela e descritiva e
    # sobrevive elidida, com no minimo duas linhas.
    #
    # A primeira versao fazia o contrario (leitura primeiro, atencao com o
    # resto) e o aviso saia cortado no meio da palavra na tela real.
    reserva_atencao = min(len(linhas_atencao), max(0, linhas_totais - 2))
    cabem_leitura = max(1, linhas_totais - reserva_atencao)
    linhas_leitura = linhas_leitura[:cabem_leitura]
    cabem_atencao = min(len(linhas_atencao), linhas_totais - len(linhas_leitura))

    painter.setFont(fonte_corpo)
    painter.setPen(tema_asg.NEXO_TEXTO)
    for linha in linhas_leitura:
        painter.drawText(QRect(corpo.left(), y, largura_texto, passo),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, linha)
        y += passo

    if cabem_atencao:
        # `fonte_ui`, nao `fonte_rotulo`: a segunda e caixa-alta e o aviso
        # inteiro saia gritado e miudo, o oposto de legivel.
        painter.setFont(fonte_corpo)
        painter.setPen(tema_asg.NEXO_AMARELO)
        for linha in linhas_atencao[:cabem_atencao]:
            painter.drawText(QRect(corpo.left(), y, largura_texto, passo_atencao),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, linha)
            y += passo_atencao
