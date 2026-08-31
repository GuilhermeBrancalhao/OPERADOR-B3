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

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QPainter

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


def _zonas_candidatas(estado: EstadoNexo, contexto: float, componente_r: float,
                      componente_j: float, componente_b: float,
                      confianca: float) -> tuple[sr.Zona, ...]:
    """POC/VAL/VAH do Volume Profile como candidatos de zona — ver
    docstring do módulo para por que não há clustering de tick bruto
    aqui. `toques=0`: nenhuma contagem de toque por nível existe nesta
    superfície hoje. `Zona.score` é a FORÇA da zona (o que
    `classificar_lado`/o motor usam para ATIVA/OBSERVACAO/EXPIRADA) — o
    CONTEXTO (micro/macro) decide o LADO, nunca o score da zona em si."""

    candidatos: list[sr.Zona] = []
    for fonte, preco in (
        ("vap-poc", estado.vap_poc), ("vap-val", estado.vap_val), ("vap-vah", estado.vap_vah),
    ):
        if preco is None:
            continue
        largura = LARGURA_ZONA_TICKS_PADRAO
        forca_zona = sr.calcular_forca_zona(componente_r, componente_j, componente_b, toques=0)
        lado = sr.classificar_lado(contexto, forca_zona)
        candidatos.append(sr.Zona(
            id=f"{fonte}-{preco}", lado=lado, preco=preco,
            inferior=preco - largura, superior=preco + largura,
            score=forca_zona, confianca=confianca, toques=0,
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
    zonas = _zonas_candidatas(estado, contexto, reposicao, rejeicao, desequilibrio, confianca)

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
                         "SUPORTE/RESISTÊNCIA · UNAVAILABLE")
        return

    dominante = snapshot.dominante
    lado = dominante.lado if dominante is not None else sr.LadoZona.NEUTRO
    cor = _COR_POR_LADO[lado]
    cor_saude = _COR_POR_SAUDE.get(snapshot.saude.estado, tema_asg.NEXO_MUTED)

    faixa_titulo = QRect(rect.left(), rect.top(), rect.width(), 16)
    painter.setFont(tokens.fonte_ui(10, QFont.Weight.Bold))
    painter.setPen(cor)
    titulo = _ROTULO_POR_LADO[lado]
    if dominante is not None and lado is not sr.LadoZona.NEUTRO:
        titulo += f" · CONF {dominante.confianca * 100:.0f}%"
    painter.drawText(faixa_titulo, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     titulo)
    painter.setFont(tokens.fonte_rotulo(6))
    painter.setPen(cor_saude)
    painter.drawText(faixa_titulo, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     snapshot.saude.estado.value
                     + (f" · {snapshot.saude.idade_ms:.0f}MS" if snapshot.saude.idade_ms else ""))

    y = faixa_titulo.bottom() + 2
    if snapshot.alerta is not sr.AlertaSR.NENHUM:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_AMARELO if snapshot.alerta is sr.AlertaSR.DIVERGENCIA else cor)
        painter.drawText(QRect(rect.left(), y, rect.width(), 11),
                         Qt.AlignmentFlag.AlignLeft, snapshot.alerta.value)
        y += 12

    if snapshot.micro is not None and snapshot.macro is not None:
        largura_metade = rect.width() // 2
        for indice, (nome, horizonte) in enumerate((("MICRO", snapshot.micro), ("MACRO", snapshot.macro))):
            caixa = QRect(rect.left() + indice * largura_metade, y, largura_metade - 4, 13)
            painter.setFont(tokens.fonte_rotulo(6))
            painter.setPen(tema_asg.NEXO_MUTED)
            painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, nome)
            painter.setFont(tokens.fonte_numero(8, QFont.Weight.Bold))
            painter.setPen(tema_asg.NEXO_VERDE if horizonte.score >= 0 else tema_asg.NEXO_ROSA)
            painter.drawText(caixa, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{horizonte.score:+.2f}")
        y += 15

    if dominante is not None and lado is not sr.LadoZona.NEUTRO:
        painter.setFont(tokens.fonte_rotulo(6))
        painter.setPen(tema_asg.NEXO_MUTED)
        preco_txt = f"REGIÃO {dominante.preco} · {'/'.join(dominante.fontes)}"
        painter.drawText(QRect(rect.left(), y, rect.width(), 11),
                         Qt.AlignmentFlag.AlignLeft, preco_txt[:60])
