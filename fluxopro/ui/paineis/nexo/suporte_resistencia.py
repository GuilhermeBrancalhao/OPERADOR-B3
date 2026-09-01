"""Mapeamento EstadoNexo -> motor de Suporte/Resistência + desenho.

Fonte do contrato: ``INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md`` (pasta
Codex/outputs). O motor determinístico (schema, fórmulas, histerese,
saúde/sequência) mora em ``fluxopro/analytics/suporte_resistencia.py`` —
puro, sem QPainter, com suíte própria. ESTE módulo faz só duas coisas:

1. **Monta a entrada do motor** a partir do que o projeto JÁ calcula —
   nunca lê feed, livro ou socket diretamente (a regra da seção 2 do
   documento: "recebe um DTO já normalizado"). Cada um dos 8 componentes
   (A/B/R/J/P/D/E/T) é rotulado CONFIRMADO/IMPRECISO/AUSENTE, mesma
   convenção de ``fluxopro/analytics/renko.py``:

   - **A (agressão)** — CONFIRMADO como fonte, IMPRECISO como extração:
     recuperado do ranking já publicado em ``maker.detalhe``
     ("1o AGRESSAO +70% giro 3"), porque a estrutura completa
     (``MakerProxySnapshot.componentes``) não atravessa a fronteira até
     `EstadoNexo` hoje. Sem o componente no ranking (só top-3 aparecem),
     cai no score agregado do MakerProxy.
   - **R (reposição/absorção)** — mesma extração, procurando REPOSICAO
     e, na ausência, ABSORCAO.
   - **B (desequilíbrio de livro)** — AUSENTE NA FONTE: esta superfície
     não recebe livro L2 (ver `nexo/indisponivel.py`, estado SEM_BOOK).
     Proxy declarado: delta/volume do último candle fechado — é
     desequilíbrio de FLUXO observado, não profundidade de livro.
   - **J (rejeição de preço)** — CONFIRMADO: geometria clássica de pavio
     (pavio inferior maior = defesa compradora; pavio superior maior =
     defesa vendedora) do último candle, dado que o candle já carrega.
   - **P (persistência)** — CONFIRMADO: a força já composta do
     Velocímetro (`estado.leituras` apelido RITMO), que já combina
     magnitude e manutenção (`asg._forca_ritmo_composta`).
   - **D (delta acumulado)** — CONFIRMADO: soma de `Candle.delta` dos
     últimos candles sobre a soma de `Candle.volume` — o delta líquido
     real do período, não inventado.
   - **E (estrutura)** — CONFIRMADO: `FaseRenko` do agregador Renko já
     calculado (`estado.fase_renko`/`tijolos_renko`).
   - **T (estabilidade)** — IMPRECISO: coeficiente de variação dos
     fechamentos recentes contra um teto de engenharia
     (`TETO_CV_ESTABILIDADE`), proxy de "quão parado" o preço está — não
     há fórmula de estabilidade estrutural na fonte.

   Candidatos de ZONA vêm de níveis que o projeto já calcula como preços
   de interesse estatístico: POC/VAL/VAH do Volume Profile
   (`estado.vap_poc`/`vap_val`/`vap_vah`). `toques` fica em `0` (nenhuma
   contagem de toque por nível existe nesta superfície hoje) — declarado,
   nunca inventado.

2. **Desenha** o resultado — selo SUPORTE/RESISTÊNCIA/NEUTRO, MICRO/MACRO,
   saúde do feed e a leitura completa do rodapé de contagem
   COMPRA/VENDA (reaproveitada de `nexo/estatistica.py`).

Read-only: nenhuma função aqui aceita ordem, credencial ou parâmetro de
execução. Ver `fluxopro/analytics/suporte_resistencia.py` para os limites
de segurança herdados do documento de referência.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygon

from fluxopro.analytics import suporte_resistencia as sr
from fluxopro.analytics.renko import FaseRenko
from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis.nexo import EstadoNexo

__all__ = [
    "TETO_CV_ESTABILIDADE",
    "componente_agressao",
    "componente_reposicao",
    "componentes_do_ranking_maker",
    "construir_entrada_sr",
    "desenhar_selo",
    "desequilibrio_de_candles",
]

_PADRAO_LINHA_RANKING = re.compile(r"\d+o\s+([A-Z]+)\s+([+-]\d+)%")

TETO_CV_ESTABILIDADE = 0.01
"""IMPRECISO — proxy de engenharia. Coeficiente de variacao dos
fechamentos recentes acima deste teto satura a leitura de estabilidade em
0 (mercado "andando"); abaixo, cresce para 1 (mercado "parado"). Nenhuma
fonte declara este numero: e o mesmo tipo de teto de engenharia que
`fluxopro/ui/paineis/nexo/estatistica.py::TETO_EM_SIGMAS` ja assume."""

JANELA_DELTA_ACUMULADO = 6
JANELA_ESTABILIDADE = 12
LARGURA_ZONA_TICKS_PADRAO = 4
"""IMPRECISO — sem ATR calculado nesta superficie, a largura da zona nao
pode ser `max(2*tick_size, 0.15*ATR_60s)` como o documento pede
literalmente. 4 ticks e um piso de engenharia declarado, nao a formula da
fonte."""


def componentes_do_ranking_maker(detalhe: str) -> dict[str, float]:
    """Recupera ``{"AGRESSAO": 0.70, "REPOSICAO": -0.20, ...}`` do texto já
    publicado por ``asg._ranking_componentes_maker``. Não fabrica número:
    é o MESMO percentual que a tela do MakerProxy já mostra, só que
    recuperado do texto formatado — a estrutura completa
    (``MakerProxySnapshot.componentes``) não atravessa a fronteira até
    `EstadoNexo`. Só os top-3 aparecem no texto; os demais ficam ausentes
    do dicionário (nunca zero fingido)."""

    saida: dict[str, float] = {}
    for linha in (detalhe or "").splitlines():
        achado = _PADRAO_LINHA_RANKING.search(linha)
        if achado:
            saida[achado.group(1)] = int(achado.group(2)) / 100.0
    return saida


def _linha_por_apelido(leituras, apelido: str):
    for nome, linha in leituras:
        if nome == apelido:
            return linha
    return None


def componente_agressao(maker) -> float:
    if maker is None:
        return 0.0
    return componentes_do_ranking_maker(getattr(maker, "detalhe", "")).get(
        "AGRESSAO", float(getattr(maker, "forca", 0.0))
    )


def componente_reposicao(maker) -> float:
    if maker is None:
        return 0.0
    componentes = componentes_do_ranking_maker(getattr(maker, "detalhe", ""))
    if "REPOSICAO" in componentes:
        return componentes["REPOSICAO"]
    if "ABSORCAO" in componentes:
        return componentes["ABSORCAO"]
    return float(getattr(maker, "forca", 0.0))


def desequilibrio_de_candles(candles: tuple) -> float:
    """Proxy declarado de B (desequilibrio de livro) — ver docstring do
    modulo: delta/volume do ultimo candle FECHADO, nunca o em formacao
    (que ainda pode inverter o proprio sinal)."""

    if len(candles) < 2:
        return 0.0
    fechado = candles[-2]
    volume = getattr(fechado, "volume", 0)
    if volume <= 0:
        return 0.0
    return sr.clamp(getattr(fechado, "delta", 0) / volume)


def _rejeicao_de_candle(candle) -> float:
    """Geometria de pavio do ultimo candle: positivo = defesa compradora
    (pavio inferior maior), negativo = defesa vendedora (pavio superior
    maior)."""

    if candle is None:
        return 0.0
    amplitude = max(1, candle.high - candle.low)
    topo_corpo = max(candle.open, candle.close)
    base_corpo = min(candle.open, candle.close)
    pavio_superior = candle.high - topo_corpo
    pavio_inferior = base_corpo - candle.low
    return sr.clamp((pavio_inferior - pavio_superior) / amplitude)


def _persistencia(leituras) -> float:
    linha = _linha_por_apelido(leituras, "RITMO")
    return 0.0 if linha is None else sr.clamp(getattr(linha, "forca", 0.0))


def _delta_acumulado(candles: tuple) -> float:
    recentes = candles[-JANELA_DELTA_ACUMULADO:]
    if not recentes:
        return 0.0
    soma_delta = sum(getattr(c, "delta", 0) for c in recentes)
    soma_volume = sum(getattr(c, "volume", 0) for c in recentes) or 1
    return sr.clamp(soma_delta / soma_volume)


def _estrutura(fase_renko, tijolos_renko: tuple) -> float:
    if not tijolos_renko:
        return 0.0
    direcao = 1.0 if getattr(tijolos_renko[-1], "direcao", 0) > 0 else -1.0
    if fase_renko is FaseRenko.TENDENCIA:
        return sr.clamp(direcao * 0.8)
    if fase_renko is FaseRenko.POSSIVEL_INVERSAO:
        return sr.clamp(direcao * -0.5)
    if fase_renko is FaseRenko.PERDENDO_FORCA:
        return sr.clamp(direcao * 0.2)
    return 0.0


def _estabilidade(candles: tuple) -> float:
    recentes = candles[-JANELA_ESTABILIDADE:]
    if len(recentes) < 3:
        return 0.0
    fechamentos = [c.close for c in recentes]
    media = sum(fechamentos) / len(fechamentos)
    if media <= 0:
        return 0.0
    variancia = sum((f - media) ** 2 for f in fechamentos) / len(fechamentos)
    coeficiente_variacao = (variancia ** 0.5) / media
    return sr.clamp(1.0 - min(1.0, coeficiente_variacao / TETO_CV_ESTABILIDADE), 0.0, 1.0)


JANELA_TOQUES_AMOSTRAS = 6000
"""Quantas amostras de ``estado.serie`` a contagem de testes varre para
trás. `asg._serie` é uma `deque` — este teto é só uma guarda de custo, a
série real costuma ser menor."""


def contar_toques(serie: tuple, inferior: int, superior: int,
                  janela: int = JANELA_TOQUES_AMOSTRAS) -> int:
    """Quantos TESTES distintos a região ``[inferior, superior]`` sofreu.

    Um teste é uma **entrada** na faixa vinda de fora dela — nunca a
    contagem de amostras que caem dentro. A diferença importa: o preço
    parado em cima da região por um minuto gera centenas de amostras e
    **um** teste; contar amostras faria uma região visitada uma única vez
    parecer testada 300 vezes, e a força da zona (que pesa 20% em toques)
    saturaria sozinha, sempre.

    CONFIRMADO quanto à origem: ``estado.serie`` é a série de preços
    negociados já congelada no snapshot — nenhum dado novo é inferido
    aqui.

    Corrige o defeito medido em 31/08/2026: `toques` estava **cravado em
    0** nesta superfície, e como `calcular_forca_zona` pesa 0,20 em
    toques, a força de toda zona nascia teto ~0,45 — abaixo do
    `LIMIAR_FORCA_ZONA` de 0,55. Consequência medida no app real (sonda
    sobre replay de 2026-08-28, 138 quadros): **100% das zonas saíam
    `NEUTRO`**, e o painel nunca mostrava um suporte ou uma resistência.
    """

    return medir_regiao(serie, inferior, superior, janela)[0]


def medir_regiao(serie: tuple, inferior: int, superior: int,
                 janela: int = JANELA_TOQUES_AMOSTRAS) -> tuple[int, float]:
    """``(testes, taxa_de_rejeicao)`` da região ``[inferior, superior]``.

    Um **teste** é uma entrada na faixa vinda de fora (ver `contar_toques`).
    Ele é **rejeitado** quando o preço sai pelo MESMO lado por onde entrou
    — chegou na região e voltou; e é **rompido** quando sai pelo lado
    oposto — atravessou. ``taxa = rejeitados / testes_concluidos``; um
    teste ainda em curso (preço dentro da faixa agora) não entra no
    denominador, porque ainda não se sabe o desfecho.

    Por que isto existe (31/08/2026): a força da zona usava como
    "rejeição" a geometria de pavio do último candle do PREGÃO — uma
    medida **global**, idêntica para as três zonas ao mesmo tempo, que não
    dizia nada sobre a região específica. Rejeição de uma zona é, por
    definição, o que acontece quando o preço vai até ELA. Agora é isso que
    se mede, e sai da mesma `estado.serie` já congelada no snapshot.
    """

    if not serie or superior < inferior:
        return 0, 0.0
    testes = 0
    rejeitados = 0
    concluidos = 0
    dentro_antes = False
    lado_entrada = 0
    anterior = None
    for amostra in serie[-janela:]:
        preco = amostra[1]
        dentro = inferior <= preco <= superior
        if dentro and not dentro_antes:
            testes += 1
            # Veio de baixo (-1) ou de cima (+1). Sem amostra anterior o
            # lado e desconhecido (0) e esse teste nao pontua desfecho.
            lado_entrada = 0 if anterior is None else (-1 if anterior < inferior else 1)
        elif dentro_antes and not dentro:
            lado_saida = -1 if preco < inferior else 1
            if lado_entrada != 0:
                concluidos += 1
                if lado_saida == lado_entrada:
                    rejeitados += 1
        dentro_antes = dentro
        anterior = preco
    taxa = (rejeitados / concluidos) if concluidos else 0.0
    return testes, taxa


def lado_geometrico(preco_zona: int, ultimo_preco: int | None) -> "sr.LadoZona":
    """Posição da zona em relação ao preço agora: abaixo = SUPORTE, acima
    = RESISTÊNCIA. É **geometria**, não opinião — uma região abaixo do
    preço só pode ser testada por baixo.

    Existe separada de `sr.classificar_lado` (que é o lado CONFIRMADO
    pelo contexto, com limiar de força) porque as duas respondem
    perguntas diferentes, e esconder a zona enquanto o contexto não
    confirma foi exatamente o defeito de 31/08/2026: a tela ficava sem
    nenhum nível de preço durante o pregão inteiro.
    """

    if ultimo_preco is None:
        return sr.LadoZona.NEUTRO
    if preco_zona < ultimo_preco:
        return sr.LadoZona.SUPORTE
    if preco_zona > ultimo_preco:
        return sr.LadoZona.RESISTENCIA
    return sr.LadoZona.NEUTRO


def _zonas_candidatas(estado: EstadoNexo, contexto: float, componente_r: float,
                      componente_j: float, componente_b: float,
                      confianca: float, ultimo_preco: int | None) -> tuple[sr.Zona, ...]:
    """POC/VAL/VAH do Volume Profile como candidatos de zona — ver
    docstring do módulo para por que não há clustering de tick bruto
    aqui. `Zona.score` é a FORÇA da zona (o que
    `classificar_lado`/o motor usam para ATIVA/OBSERVACAO/EXPIRADA).

    O LADO gravado é o **confirmado pelo contexto** (regra da fonte).
    Quando ele sai `NEUTRO`, a tela ainda assim mostra a zona, rotulada
    pela `lado_geometrico` e declarada como não confirmada — ver
    `desenhar_selo`.
    """

    candidatos: list[sr.Zona] = []
    serie = estado.serie or ()
    for fonte, preco in (
        ("vap-poc", estado.vap_poc), ("vap-val", estado.vap_val), ("vap-vah", estado.vap_vah),
    ):
        if preco is None:
            continue
        largura = LARGURA_ZONA_TICKS_PADRAO
        inferior, superior = preco - largura, preco + largura
        toques, taxa_rejeicao = medir_regiao(serie, inferior, superior)
        # J passa a ser a rejeicao MEDIDA NESTA regiao. `componente_j` (o
        # pavio do ultimo candle) so entra como piso quando a regiao ainda
        # nao teve nenhum teste concluido — sem desfecho observado, a taxa
        # seria 0,0 e puniria uma zona recem-criada como se ela ja tivesse
        # falhado.
        rejeicao_zona = taxa_rejeicao if toques > 0 else max(0.0, componente_j)
        forca_zona = sr.calcular_forca_zona(componente_r, rejeicao_zona, componente_b, toques)
        lado = sr.classificar_lado(contexto, forca_zona)
        candidatos.append(sr.Zona(
            id=f"{fonte}-{preco}", lado=lado, preco=preco,
            inferior=inferior, superior=superior,
            score=forca_zona, confianca=confianca, toques=toques,
            fontes=(fonte,), status=sr.EstadoZona.ATIVA,  # reclassificado pelo motor por `score`
        ))
    return tuple(candidatos)


def construir_entrada_sr(estado: EstadoNexo) -> dict:
    """Monta os argumentos de ``MotorSuporteResistencia.processar`` a
    partir de ``EstadoNexo`` — função pura, testável sem motor nem
    QPainter. Quem chama ainda precisa fornecer ``event_id``/``sequencia``/
    ``agora_ns`` (o motor é stateful e mora no painel, não aqui).
    """

    candles = tuple(estado.candles_m15 or ())
    leituras = estado.leituras
    maker = estado.maker

    agressao = componente_agressao(maker)
    reposicao = componente_reposicao(maker)
    desequilibrio = desequilibrio_de_candles(candles)
    rejeicao = _rejeicao_de_candle(candles[-2] if len(candles) >= 2 else None)
    persistencia = _persistencia(leituras)
    delta = _delta_acumulado(candles)
    estrutura = _estrutura(estado.fase_renko, tuple(estado.tijolos_renko or ()))
    estabilidade = _estabilidade(candles)

    micro_score = sr.calcular_micro(agressao, desequilibrio, reposicao, rejeicao)
    macro_score = sr.calcular_macro(persistencia, delta, estrutura, estabilidade)
    contexto = sr.calcular_contexto(micro_score, macro_score)

    qualidade_micro = min(1.0, len(candles) / 2.0) if candles else 0.0
    qualidade_macro = min(1.0, len(candles) / float(JANELA_ESTABILIDADE))

    micro = sr.HorizonteScore(
        score=micro_score, qualidade=qualidade_micro, janela_ms=0,
        amostras=len(candles),
        componentes={"aggression": agressao, "book_imbalance": desequilibrio,
                    "replenishment": reposicao, "rejection": rejeicao},
    )
    macro = sr.HorizonteScore(
        score=macro_score, qualidade=qualidade_macro, janela_ms=0,
        amostras=len(candles),
        componentes={"persistence": persistencia, "cumulative_delta": delta,
                    "structure": estrutura, "stability": estabilidade},
    )

    ultimo_preco = estado.serie[-1][1] if estado.serie else None
    confianca = sr.confianca_zona(qualidade_micro, qualidade_macro, len(candles))
    zonas = _zonas_candidatas(estado, contexto, reposicao, rejeicao, desequilibrio, confianca,
                              ultimo_preco)

    return {
        "micro": micro, "macro": macro, "zonas_candidatas": zonas,
        "ultimo_preco": ultimo_preco,
    }


# ==========================================================================
# Desenho
# ==========================================================================
_COR_POR_LADO = {
    sr.LadoZona.SUPORTE: tema_asg.NEXO_VERDE,
    sr.LadoZona.RESISTENCIA: tema_asg.NEXO_ROSA,
    sr.LadoZona.NEUTRO: tema_asg.NEXO_MUTED,
}
_ROTULO_POR_LADO = {
    sr.LadoZona.SUPORTE: "SUPORTE",
    sr.LadoZona.RESISTENCIA: "RESISTÊNCIA",
    sr.LadoZona.NEUTRO: "NEUTRO",
}
_COR_POR_SAUDE = {
    sr.EstadoFeed.LIVE: tema_asg.ESTADO_AO_VIVO,
    sr.EstadoFeed.STALE: tema_asg.ESTADO_ATRASADO,
    sr.EstadoFeed.GAP: tokens.ALERT,
    sr.EstadoFeed.RECOVERING: tema_asg.NEXO_CIANO,
    sr.EstadoFeed.UNAVAILABLE: tema_asg.NEXO_MUTED,
}

# 31/08/2026 — o operador pegou `DIVERGENCE`/`LOW_CONFIDENCE`/`RECOVERING`
# CRUS na tela. Os `.value` dos enums vêm do documento de origem, que é em
# inglês; o produto inteiro fala português. Traduzir na BORDA (aqui, no
# desenho) e nunca no enum: o `.value` é contrato de DTO e continua o do
# documento para quem consome o snapshot.
_SAUDE_PT = {
    sr.EstadoFeed.LIVE: "AO VIVO",
    sr.EstadoFeed.STALE: "ATRASADO",
    sr.EstadoFeed.GAP: "FALHA DE SEQUÊNCIA",
    sr.EstadoFeed.RECOVERING: "RECUPERANDO",
    sr.EstadoFeed.UNAVAILABLE: "INDISPONÍVEL",
}
_ALERTA_PT = {
    sr.AlertaSR.NENHUM: "",
    sr.AlertaSR.OBSERVAR_SUPORTE: "OBSERVAR SUPORTE",
    sr.AlertaSR.OBSERVAR_RESISTENCIA: "OBSERVAR RESISTÊNCIA",
    sr.AlertaSR.NO_SUPORTE: "NO SUPORTE",
    sr.AlertaSR.NA_RESISTENCIA: "NA RESISTÊNCIA",
    sr.AlertaSR.DIVERGENCIA: "MICRO E MACRO DIVERGEM",
    sr.AlertaSR.BAIXA_CONFIANCA: "CONFIANÇA BAIXA",
}


def rotulo_saude(estado) -> str:
    """Texto em português do estado de feed — ver `_SAUDE_PT`."""

    return _SAUDE_PT.get(estado, "INDISPONÍVEL")


def rotulo_alerta(alerta) -> str:
    """Texto em português do alerta — ver `_ALERTA_PT`."""

    return _ALERTA_PT.get(alerta, "")


def texto_distancia(preco_zona: int, ultimo_preco: int | None, tick_size: float) -> str:
    """``+18 pts`` / ``-4 pts`` da referência — distância COM SINAL do
    preço atual até a zona. `—` quando não há preço observado (nunca
    ``0``, que leria como "estamos exatamente na zona")."""

    if ultimo_preco is None:
        return "—"
    pontos = (preco_zona - ultimo_preco) * (tick_size or 1.0)
    return f"{pontos:+.1f} pts"


def desenhar_selo(painter: QPainter, rect: QRect, snapshot) -> None:
    """Selo SUPORTE/RESISTÊNCIA/NEUTRO + MICRO/MACRO + saúde — a leitura
    central do documento de referência, adaptada à faixa estreita desta
    região (ver docstring do módulo)."""

    if rect.height() < 20 or rect.width() < 80:
        return

    if snapshot is None or snapshot.saude.estado is sr.EstadoFeed.UNAVAILABLE:
        painter.setFont(tokens.fonte_rotulo(7))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                         "SUPORTE/RESISTÊNCIA · SEM LEITURA")
        return

    dominante = snapshot.dominante
    lado = dominante.lado if dominante is not None else sr.LadoZona.NEUTRO
    confirmado = dominante is not None and lado is not sr.LadoZona.NEUTRO
    cor = _COR_POR_LADO[lado]
    cor_saude = _COR_POR_SAUDE.get(snapshot.saude.estado, tema_asg.NEXO_MUTED)

    # ---------------------------------------------------------------- titulo
    faixa_titulo = QRect(rect.left(), rect.top(), rect.width(), 15)
    painter.setFont(tokens.fonte_ui(10, QFont.Weight.Bold))
    painter.setPen(cor if confirmado else tema_asg.NEXO_MUTED)
    if confirmado:
        titulo = f"{_ROTULO_POR_LADO[lado]} · CONFIRMAÇÃO {dominante.confianca * 100:.0f}%"
    else:
        # Nunca "NEUTRO" sozinho: o operador leu isso como "mercado
        # equilibrado", quando o que o motor diz e "nenhuma zona passou o
        # limiar de forca". Sao coisas diferentes, e a segunda e a verdade.
        titulo = "SUPORTE/RESISTÊNCIA · SEM ZONA CONFIRMADA"
    painter.drawText(faixa_titulo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     titulo)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(cor_saude)
    painter.drawText(faixa_titulo, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     rotulo_saude(snapshot.saude.estado))

    # ------------------------------------------------------- alerta + micro/macro
    y = faixa_titulo.bottom() + 1
    faixa_alerta = QRect(rect.left(), y, rect.width(), 12)
    texto_alerta = rotulo_alerta(snapshot.alerta)
    if texto_alerta:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_AMARELO if snapshot.alerta is sr.AlertaSR.DIVERGENCIA
                       else tema_asg.NEXO_MUTED)
        painter.drawText(faixa_alerta, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         texto_alerta)
    if snapshot.micro is not None and snapshot.macro is not None:
        painter.setFont(tokens.fonte_numero(7, QFont.Weight.Bold))
        partes = f"MICRO {snapshot.micro.score:+.2f}   MACRO {snapshot.macro.score:+.2f}"
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(faixa_alerta, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         partes)
    y = faixa_alerta.bottom() + 2

    # ------------------------------------------------------------- as zonas
    zonas = tuple(snapshot.zonas or ())
    faixa_zonas = QRect(rect.left(), y, rect.width(), max(10, rect.bottom() - y))
    if not zonas:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(faixa_zonas, Qt.AlignmentFlag.AlignLeft,
                         "NENHUMA REGIÃO OBSERVADA (SEM VOLUME PROFILE)")
        return

    # Ordenadas por PREÇO decrescente: a leitura da tela passa a ter a
    # mesma orientacao do grafico (resistencia em cima, suporte embaixo).
    ordenadas = sorted(zonas, key=lambda z: -z.preco)
    vao = 4
    largura = max(60, (faixa_zonas.width() - vao * (len(ordenadas) - 1)) // len(ordenadas))
    for indice, zona in enumerate(ordenadas):
        caixa = QRect(faixa_zonas.left() + indice * (largura + vao), faixa_zonas.top(),
                      largura, faixa_zonas.height())
        _desenhar_zona(painter, caixa, zona, snapshot)


def _desenhar_zona(painter: QPainter, caixa: QRect, zona, snapshot) -> None:
    """Uma região: preço, distância com sinal, testes contados e força.

    O rótulo do lado usa `lado_geometrico` quando o contexto ainda não
    confirmou — a zona NUNCA some da tela por falta de confirmação (o
    defeito de 31/08/2026), e o grau de confirmação vai declarado na
    barra de força e no título do selo.
    """

    if caixa.width() < 50 or caixa.height() < 24:
        return
    lado_visivel = (zona.lado if zona.lado is not sr.LadoZona.NEUTRO
                    else lado_geometrico(zona.preco, snapshot.ultimo_preco))
    cor = _COR_POR_LADO[lado_visivel]
    confirmada = zona.lado is not sr.LadoZona.NEUTRO

    painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
    caneta = QPen(cor)
    caneta.setWidth(2 if confirmada else 1)
    # Zona ainda nao confirmada desenha moldura TRACEJADA: a diferenca
    # entre "medido e confirmado" e "candidata" tem de existir a olho, nao
    # so no texto.
    caneta.setStyle(Qt.PenStyle.SolidLine if confirmada else Qt.PenStyle.DotLine)
    painter.setPen(caneta)
    painter.drawRect(caixa.adjusted(0, 0, -1, -1))

    tick = snapshot.tick_size or 1.0
    preco_real = zona.preco * tick

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(4, 2, -4, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     _ROTULO_POR_LADO[lado_visivel])
    painter.drawText(caixa.adjusted(4, 2, -4, 0),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                     "/".join(zona.fontes).upper().replace("VAP-", ""))

    painter.setFont(tokens.fonte_numero(13, QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(caixa.adjusted(4, 9, -4, -12), Qt.AlignmentFlag.AlignCenter,
                     f"{preco_real:,.1f}".replace(",", "@").replace(".", ",").replace("@", "."))

    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(4, 0, -4, -2),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                     texto_distancia(zona.preco, snapshot.ultimo_preco, tick))
    painter.drawText(caixa.adjusted(4, 0, -4, -2),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                     f"{zona.toques} TESTES · FORÇA {zona.score * 100:.0f}%")


# ==========================================================================
# PLACAR DE SUPORTE/RESISTÊNCIA — desenho aprovado pelo operador (31/08/2026)
# ==========================================================================
#
# Lógica conferida nas AULAS DA SG/ASG (transcrições em
# `fluxo_pro/pesquisa/legendas`), não em suposição:
#
# * `TPk39osWiKY`: "quando ele vier com a força ultra, que é quando tem esse
#   RAIO aqui"; "a gente só vai dar ênfase para esse sinal quando ele
#   aparecer no NÍVEL MÁXIMO"; a setinha piscando (vermelha p/ baixo no
#   alerta de resistência, verde p/ cima no de suporte) é o sinal do sniper.
# * `W7lNHhliZXU`: "ele tem umas BARRINHAS ali que são PREENCHIDAS"; "como
#   que tá o TERMÔMETRO dessas sinalizações? eles sobem níveis agressivos ou
#   já tá perdendo força do sinal?".
#
# Daí as três regras desta região, todas confirmadas pelo operador:
#
# 1. **um lado por vez** — o alerta é de suporte OU de resistência, nunca os
#    dois; o lado oposto fica apagado em zero, e não escondido;
# 2. **raios = intensidade**, vinda da FORÇA DA ZONA (`Zona.score`);
# 3. **barrinhas = termômetro do nível**, preenchidas na mesma força.
#
# O fundo é TRANSLÚCIDO de propósito: o wallpaper do quadro atravessa, como
# em todo o resto da superfície integrada.

INTENSIDADE_MAXIMA = 5

_PONTOS_RAIO_SR = (
    (0.55, 0.00), (0.15, 0.55), (0.42, 0.55),
    (0.05, 1.00), (0.62, 0.42), (0.35, 0.42),
)


def intensidade_da_zona(score: float | None) -> int:
    """Força da zona [0,1] -> 0..5 raios.

    Reaproveita a MESMA escala já aprovada para a força observada
    (`estatistica.quantidade_raios_forca`: zero abaixo de 5%, um até 20%,
    dois até 40%, três até 60%, quatro até 80%, cinco acima) — duas escalas
    diferentes para "intensidade" na mesma tela seria exatamente o defeito
    de "dois pesos, uma leitura" que esta bancada já pegou antes.

    Import tardio porque `estatistica` importa ESTE módulo: no topo daria
    ciclo.
    """

    if score is None:
        return 0
    from fluxopro.ui.paineis.nexo.estatistica import quantidade_raios_forca

    return quantidade_raios_forca(score)


def texto_preco_regiao(preco_ticks, tick_size: float) -> str:
    """Preço da região no formato do produto (`5.219,5`). `—` sem zona."""

    if preco_ticks is None:
        return "—"
    valor = preco_ticks * (tick_size or 1.0)
    return f"{valor:,.1f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _poligono_raio_sr(caixa: QRect) -> QPolygon:
    return QPolygon([
        QPoint(caixa.left() + round(ux * caixa.width()),
               caixa.top() + round(uy * caixa.height()))
        for ux, uy in _PONTOS_RAIO_SR
    ])


def _seta(painter: QPainter, cx: int, cy: int, raio: int, cor, para_cima: bool) -> None:
    """Triangulo cheio do lado. `save`/`restore` de proposito: sem isso o
    `NoPen` usado para preencher VAZAVA para quem chama, e no Qt um
    `drawText` com `NoPen` NAO PINTA NADA — foi assim que os rotulos BUY e
    SELL sumiram da tela em 31/08/2026 (o desenho parecia certo porque a
    seta e o numero, que usam brush, continuavam aparecendo)."""

    sentido = 1 if para_cima else -1
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cor)
    painter.drawPolygon(QPolygon([
        QPoint(cx, cy - sentido * raio),
        QPoint(cx + round(raio * 0.8), cy + round(sentido * raio * 0.6)),
        QPoint(cx - round(raio * 0.8), cy + round(sentido * raio * 0.6)),
    ]))
    painter.restore()


def _chapa(painter: QPainter, rect: QRect, cor_borda, alfa: int = 70,
           largura: int = 1) -> None:
    """Chapa TRANSLÚCIDA — o wallpaper continua visível por trás."""

    painter.fillRect(rect, QColor(4, 8, 12, alfa))
    caneta = QPen(cor_borda)
    caneta.setWidth(largura)
    painter.setPen(caneta)
    painter.drawRect(rect.adjusted(0, 0, -1, -1))


def _card_lado(painter: QPainter, rect: QRect, rotulo: str, valor: int,
               cor, para_cima: bool, ativo: bool) -> None:
    _chapa(painter, rect, cor if ativo else tema_asg.NEXO_GRADE,
           alfa=88 if ativo else 46, largura=2 if ativo else 1)
    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(cor if ativo else tema_asg.NEXO_MUTED)
    _seta(painter, rect.left() + 16, rect.top() + 10, 4,
          cor if ativo else tema_asg.NEXO_GRADE, para_cima)
    painter.drawText(QRect(rect.left() + 24, rect.top() + 3, rect.width() - 28, 13),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo)
    painter.setFont(tokens.fonte_numero(max(16, min(34, rect.height() // 2)),
                                        QFont.Weight.Bold))
    painter.setPen(cor if ativo else tema_asg.NEXO_GRADE)
    painter.drawText(rect.adjusted(0, 13, 0, -3), Qt.AlignmentFlag.AlignCenter, str(valor))


def zona_de_referencia(snapshot):
    """Zona que o placar descreve: a CONFIRMADA quando existe, senão a mais
    PRÓXIMA do preço.

    Sem confirmação o operador ainda precisa do nível da região que o preço
    está encostando — o que muda é o rótulo (`NÃO CONFIRMADA`) e a moldura
    apagada, nunca esconder a informação.
    """

    if snapshot is None:
        return None
    dominante = getattr(snapshot, "dominante", None)
    if dominante is not None:
        return dominante
    zonas = tuple(getattr(snapshot, "zonas", ()) or ())
    if not zonas:
        return None
    ultimo = getattr(snapshot, "ultimo_preco", None)
    if ultimo is None:
        return zonas[0]
    return min(zonas, key=lambda z: abs(z.preco - ultimo))


def desenhar_placar(painter: QPainter, rect: QRect, snapshot) -> None:
    """Placar de suporte/resistência: lado, intensidade, região e nível.

    Substitui a contagem COMPRA/VENDA de leituras que ocupava esta região —
    ela media outra coisa (as 4 leituras da matriz), vivia empatada em
    33%/33% e não dizia nada sobre a REGIÃO DE PREÇO, que é o que a aula
    manda observar.
    """

    if rect.height() < 60 or rect.width() < 200:
        return

    referencia = zona_de_referencia(snapshot)
    tick = getattr(snapshot, "tick_size", 1.0) or 1.0 if snapshot else 1.0
    ultimo = getattr(snapshot, "ultimo_preco", None) if snapshot else None
    dominante = getattr(snapshot, "dominante", None) if snapshot else None
    confirmado = dominante is not None and dominante.lado is not sr.LadoZona.NEUTRO

    lado = getattr(referencia, "lado", None)
    if lado is None or lado is sr.LadoZona.NEUTRO:
        lado = (lado_geometrico(referencia.preco, ultimo)
                if referencia is not None else sr.LadoZona.NEUTRO)
    e_suporte = lado is sr.LadoZona.SUPORTE
    cor = _COR_POR_LADO.get(lado, tema_asg.NEXO_MUTED)

    score = getattr(referencia, "score", None)
    intensidade = intensidade_da_zona(score)

    # A regiao (`nexo/estatistica.py`) ja imprime "PLACAR ESTATISTICO" no
    # seu cabecalho — repetir aqui dava DOIS titulos empilhados na tela
    # (visto no retrato de 31/08/2026). Aqui fica so a saude do feed.
    saude = getattr(getattr(snapshot, "saude", None), "estado", None) if snapshot else None
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 8, 12),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     rotulo_saude(saude) if saude is not None else "SEM LEITURA")

    corpo = QRect(rect.left() + 4, rect.top() + 13, rect.width() - 8,
                  max(20, rect.height() - 16))

    # --------------------------------------------------------------- cards
    # DISTRIBUICAO PROPORCIONAL (31/08/2026, pedido do operador: "faca a
    # distribuicao total na tela"). Alturas fixas faziam o TERMOMETRO cair
    # fora em regiao baixa — medido pelo teste responsivo em 1280x600 e
    # 1480x780, onde sobravam 8px para uma faixa que precisa de 21. As tres
    # faixas agora dividem o corpo em fracao, entao todas cabem em qualquer
    # resolucao, e o teto de 72px impede o card de inchar em tela grande.
    altura_card = max(34, min(72, round(corpo.height() * 0.46)))
    largura_card = max(70, (corpo.width() - 26) // 2)
    _card_lado(painter, QRect(corpo.left(), corpo.top(), largura_card, altura_card),
               "BUY", intensidade if e_suporte else 0,
               tema_asg.NEXO_VERDE, True, e_suporte and intensidade > 0)
    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(corpo.left() + largura_card, corpo.top(), 26, altura_card),
                     Qt.AlignmentFlag.AlignCenter, "x")
    _card_lado(painter,
               QRect(corpo.left() + largura_card + 26, corpo.top(), largura_card, altura_card),
               "SELL", 0 if e_suporte else intensidade,
               tema_asg.NEXO_ROSA, False, (not e_suporte) and intensidade > 0)

    # ------------------------------------------ intensidade + preco da regiao
    y = corpo.top() + altura_card + 6
    if corpo.bottom() - y < 30:
        return
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(corpo.left(), y, 120, 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "INTENSIDADE")
    coluna_regiao = corpo.left() + min(140, corpo.width() // 2)
    painter.drawText(QRect(coluna_regiao, y, corpo.right() - coluna_regiao, 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "REGIÃO" if confirmado else "REGIÃO · NÃO CONFIRMADA")

    passo = min(20, max(12, (coluna_regiao - corpo.left() - 8) // INTENSIDADE_MAXIMA))
    # reserva a faixa do termometro ANTES de dimensionar o raio
    reserva_termometro = 22
    disponivel = max(10, corpo.bottom() - y - 14 - reserva_termometro)
    altura_raio = min(28, max(9, disponivel))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    for indice in range(INTENSIDADE_MAXIMA):
        aceso = indice < intensidade
        painter.setBrush(cor if aceso else QColor(42, 53, 66, 130))
        painter.drawPolygon(_poligono_raio_sr(
            QRect(corpo.left() + indice * passo, y + 12, max(6, passo - 5), altura_raio)))
    painter.restore()

    # A caixa do preco recebe a altura do RAIO mais folga, e a fonte sai de
    # uma FRACAO dessa caixa: com `fonte = altura_raio` a tinta media 36px
    # numa caixa de 30 e o Qt cortava o numero por baixo (medido em
    # 31/08/2026 pelo teste responsivo).
    caixa_preco = QRect(coluna_regiao, y + 11, corpo.right() - coluna_regiao,
                        altura_raio + 12)
    painter.setFont(tokens.fonte_numero(
        max(12, min(24, int(caixa_preco.height() * 0.62))), QFont.Weight.Bold))
    painter.setPen(cor)
    painter.drawText(caixa_preco,
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     texto_preco_regiao(getattr(referencia, "preco", None), tick))

    # ------------------------------------------------------------ termometro
    y2 = y + 14 + altura_raio + 4
    if corpo.bottom() - y2 < 14:
        return
    rotulo = f"TERMOMETRO DO NIVEL · {intensidade}/{INTENSIDADE_MAXIMA}"
    if intensidade >= INTENSIDADE_MAXIMA:
        rotulo += "  ·  NIVEL MAXIMO"
    if referencia is not None:
        rotulo += f"  ·  {referencia.toques} TESTES"
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(corpo.left(), y2, corpo.width(), 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo)
    faixa = QRect(corpo.left(), y2 + 11, corpo.width(),
                  max(5, min(16, corpo.bottom() - y2 - 11)))
    barras = max(6, min(20, faixa.width() // 14))
    acesas = int(round(max(0.0, min(1.0, float(score or 0.0))) * barras))
    vao = 3
    largura_barra = max(2, (faixa.width() - vao * (barras - 1)) // barras)
    for indice in range(barras):
        caixa = QRect(faixa.left() + indice * (largura_barra + vao), faixa.top(),
                      largura_barra, faixa.height())
        painter.fillRect(caixa, cor if indice < acesas else QColor(42, 53, 66, 120))
