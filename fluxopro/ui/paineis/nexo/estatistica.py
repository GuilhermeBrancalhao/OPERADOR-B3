"""Regiao PLACAR ESTATISTICO (x 0,00-0,40 · y 0,79-1,00).

Esqueleto extraido da fileira de leituras derivadas de
``PainelNexoMercadoASG._desenhar_contexto_nexo``. Ancorado no canto inferior
esquerdo do quadro, sangrando ate as duas bordas.

Estrutura (rodada 1 desta regiao):

* uma faixa de contagem COMPRA/VENDA — cada lado conta quantas das
  ``leituras`` atuais apontam naquela direcao, com a legenda declarando o
  denominador (``N DE M LEITURAS``) para que a contagem nunca apareca sem a
  procedencia de onde saiu;
* uma tira de RAIOS a direita da contagem (28/08/2026: uma marca por
  LEITURA distinta, com teto de variacao medido da propria serie — ver
  `leituras_distintas` e `TETO_EM_SIGMAS`), construida a partir de
  ``estado.serie`` (a mesma serie de forca ja congelada no snapshot — nenhum
  dado novo e inferido aqui). Sem amostra, a tira declara o estado
  indisponivel em vez de desenhar barras falsas;
* o selo de Suporte/Resistência (31/08/2026, substitui os quatro ladrilhos
  de leitura HORIZONTE/PULSO/PRESENCA/RITMO): o operador apontou que esta
  faixa estava "muito pobre visualmente e com lógicas sem confiança" — os
  quatro ladrilhos só reimprimiam ``estado.leituras`` sem nenhuma leitura
  nova, e HORIZONTE/PULSO já migraram para o Dual Market Velocity Gauge em
  `nexo/contexto.py`. No lugar entra `estado.sr_snapshot`
  (``fluxopro.analytics.suporte_resistencia``), o motor determinístico de
  suporte/resistência construído a partir de
  ``INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md`` (pasta Codex, trazido pelo
  operador) — ver `nexo/suporte_resistencia.py` para o mapeamento e o
  desenho.

Nada aqui e clicavel nem envia ordem: e leitura consultiva, com a mesma
regra das demais regioes do NEXO.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen, QPolygon

from fluxopro.ui import tema_asg, tokens
from fluxopro.ui.paineis import asg as _asg
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import suporte_resistencia as _sr_ui

VAO_LADRILHO = 4
VAO_LINHA = 4
ALTURA_TITULO = 14
ALTURA_ROTULO_BARRAS = 9
ALTURA_LEGENDA_BARRAS = 10

# Achado do operador (27/08/2026): "por que mudancas tao abruptas sempre,
# precisa ser algo mais tecnico". Ate 26/08/2026 o placar contava 1-a-1
# quantas das 4 leituras (HORIZONTE/PULSO/PRESENCA/RITMO) cruzavam
# direcao=COMPRA/VENDA — uma leitura de confianca BAIXA valia exatamente o
# mesmo que uma de confianca ALTA, e cada cruzamento de zero saltava a
# contagem inteira em 1 (0->1->2->3->4), nunca gradual.
#
# IMPRECISO — pesos de engenharia deste projeto, sem formula de fonte pra
# "quanto uma leitura de baixa confianca deve contar menos". O que muda:
# a contagem 1-a-1 continua existindo (e a legenda "N DE M LEITURAS"
# continua o denominador honesto, nunca removido), mas o NUMERO GRANDE em
# cada caixa passa a ser um placar PONDERADO por confianca — continuo, nao
# discreto — em vez do inteiro 0-4.
PESO_CONFIANCA = {
    _asg.ConfiancaASG.ALTA: 1.0,
    _asg.ConfiancaASG.MEDIA: 0.6,
    _asg.ConfiancaASG.BAIXA: 0.3,
    _asg.ConfiancaASG.INDISPONIVEL: 0.0,
}
"""Peso de confiabilidade por nível de `ConfiancaASG` — tabela ÚNICA para
qualquer regiao que precise ponderar uma leitura pela confiança declarada
na matriz (usada aqui e pelo medidor duplo MICRO/MACRO em
`nexo/contexto.py`). Publica de propósito: duplicar esta tabela em outro
arquivo é o mesmo risco de "dois pesos, uma leitura" que a bancada deste
projeto já pegou noutro contexto."""
_PESO_CONFIANCA_PLACAR = PESO_CONFIANCA
"""Alias — mantido só para não reescrever cada uso já existente neste
arquivo. Consumidor NOVO deve importar `PESO_CONFIANCA`."""


def placar_ponderado(leituras: tuple[tuple[str, object], ...]) -> float:
    """Score em [-1, 1]: media das `forca` das leituras, ponderada pela
    confianca de cada uma. `0.0` quando nenhuma leitura tem confianca > 0
    (nunca divide por zero, nunca inventa direcao de leitura indisponivel).
    """

    pesos = [
        (float(getattr(linha, "forca", 0.0)), _PESO_CONFIANCA_PLACAR.get(linha.confianca, 0.0))
        for _, linha in leituras
    ]
    soma_pesos = sum(peso for _, peso in pesos)
    if soma_pesos <= 0:
        return 0.0
    bruto = sum(forca * peso for forca, peso in pesos) / soma_pesos
    return max(-1.0, min(1.0, bruto))


def pesos_por_lado(leituras: tuple[tuple[str, object], ...]) -> tuple[float, float]:
    """Convicção de CADA lado, medida separadamente, em [0, 1] cada uma.

    Achado do operador (27/08/2026: "mudancas tao abruptas sempre"). Ate
    aqui as duas caixas nasciam de UM unico score assinado
    (``max(0, score)`` / ``max(0, -score)``): um dos dois lados era
    **sempre exatamente 0%** e, ao cruzar o zero, os dois numeros trocavam
    de lugar de uma vez. Nao era o mercado virando de uma vez — era a
    formula.

    Agora cada lado soma as SUAS proprias leituras:

        compra = Σ w_i · max(0, f_i) / Σ w_i
        venda  = Σ w_i · max(0, -f_i) / Σ w_i

    com ``w_i`` o peso de confianca de ``_PESO_CONFIANCA_PLACAR``. Duas
    propriedades que o operador pode conferir na tela:

    * **discordancia fica visivel**: com HORIZONTE comprador e RITMO
      vendedor os dois numeros ficam positivos ao mesmo tempo — antes o
      painel era obrigado a esconder um dos dois;
    * **reconciliacao exata**: ``compra - venda == placar_ponderado(...)``
      ao float. O saldo impresso no titulo do placar E o mesmo score, nao
      um segundo numero de outra fonte;
    * ``compra + venda <= 1``; o que falta para 1 e leitura sem conviccao
      (forca perto de zero ou confianca baixa) — nunca renormalizamos para
      100%, porque isso fabricaria conviccao que ninguem mediu.

    CONFIRMADO quanto a origem dos dados (as `forca`/`confianca` sao as
    mesmas ja congeladas no snapshot); IMPRECISO quanto aos pesos de
    confianca, que sao de engenharia deste projeto.

    Custo: nenhum atraso. A continuidade vem da formula ser continua nas
    forcas, nao de media movel — uma virada real de HORIZONTE aparece no
    mesmo quadro em que acontece.
    """

    pares = [
        (float(getattr(linha, "forca", 0.0)), _PESO_CONFIANCA_PLACAR.get(linha.confianca, 0.0))
        for _, linha in leituras
    ]
    soma_pesos = sum(peso for _, peso in pares)
    if soma_pesos <= 0:
        return 0.0, 0.0
    compra = sum(max(0.0, forca) * peso for forca, peso in pares) / soma_pesos
    venda = sum(max(0.0, -forca) * peso for forca, peso in pares) / soma_pesos
    return min(1.0, compra), min(1.0, venda)


LIMIAR_DIVERGENCIA = 0.15
"""IMPRECISO — limiar de engenharia. Acima disso nos DOIS lados ao mesmo
tempo, o placar carimba DIVERGENTES no titulo: as leituras discordam de
verdade e o operador precisa saber que o saldo pequeno nao e calmaria, e
puxao dos dois lados. 0,15 e ~1 leitura de confianca ALTA a meia forca
entre 4."""


JANELA_SUAVIZACAO_FORCA = 5
"""Janela da media movel causal do MakerProxy (`asg.py`, gauge EQUILIBRIO /
PRESENCA / barra de pressao). **Nao governa mais a FORCA OBSERVADA desta
regiao** — ver `TETO_EM_SIGMAS` e a medicao que a desqualificou aqui.

IMPRECISO — 5 nunca teve justificativa escrita. Mantida porque `asg.py`
declara usar a mesma janela; quem for mexer no MakerProxy que a meca la."""


def _suavizar_forca(
    amostras: tuple[tuple[int, int, float, int], ...], janela: int = JANELA_SUAVIZACAO_FORCA
) -> tuple[float, ...]:
    """Media movel causal — MANTIDA so como termo de comparacao da evidencia
    desta rodada (`.gauntlet_docx/rodadas/p9_serie.csv`). Nao e mais o
    caminho de desenho: ver `suavizar_por_taxa`."""

    valores = [item[2] for item in amostras]
    suavizados = []
    for indice in range(len(valores)):
        inicio = max(0, indice - janela + 1)
        recorte = valores[inicio : indice + 1]
        suavizados.append(sum(recorte) / len(recorte))
    return tuple(suavizados)


def leituras_distintas(
    amostras: tuple[tuple[int, int, float, int], ...]
) -> tuple[tuple[int, float], ...]:
    """Colapsa repeticoes CONSECUTIVAS da forca em uma leitura so.

    Devolve ``(timestamp_ns da primeira amostra da leitura, forca)`` — o
    carimbo de tempo vem junto de proposito: sem ele a tira nao consegue
    declarar PERIODO nenhum, que foi a lacuna apontada na rodada 1 (ver
    `teto_por_segundo` e a legenda de `_desenhar_barras`).

    CONFIRMADO por medicao (28/08/2026, replay real de 2026-08-28 12:00,
    4.703 negocios / 6.594 amostras — `.gauntlet_docx/rodadas/p9_serie.csv`):
    a coluna de forca de `estado.serie` **nao e forca por negocio**, ao
    contrario do que a documentacao afirmava. `asg._registrar_amostra` recebe
    `self._forca_atual()`, que e um escalar do SNAPSHOT, carimbado identico em
    todos os negocios daquele snapshot. Medido: 6.594 amostras carregam apenas
    **204 valores distintos**; o patamar de valor repetido tem 32,3 amostras de
    media, 55 no p90 e 123 no maximo.

    Consequencia direta na tela, e este era o defeito real desta regiao: a
    janela visivel e de 24 amostras, e 24 < 32 — ou seja, **o normal era a tira
    inteira ser 24 raios identicos**. Conferido na propria evidencia: as
    ultimas 24 amostras da corrida valiam todas 0,656. A tira dizia mostrar
    "sequencia" e mostrava um nivel unico, 24 vezes.

    Colapsar nao descarta informacao de forca: a i-esima repeticao e o mesmo
    numero do mesmo snapshot, nao uma segunda observacao. O que a tira passa a
    mostrar e uma leitura por MUDANCA observada — e a legenda diz isso.
    """

    if not amostras:
        return ()
    saida = [(int(amostras[0][0]), float(amostras[0][2]))]
    for carimbo, _preco, forca, _qtd in amostras[1:]:
        if float(forca) != saida[-1][1]:
            saida.append((int(carimbo), float(forca)))
    return tuple(saida)


NS_POR_SEGUNDO = 1_000_000_000


def periodo_coberto_s(leituras: tuple[tuple[int, float], ...]) -> float:
    """Quantos SEGUNDOS de tape as `leituras` cobrem, do carimbo da primeira
    ao da ultima. `0.0` com menos de duas leituras ou carimbo nao monotono.

    Existe porque a tira precisa DECLARAR o periodo: uma leitura nao tem
    duracao fixa (medido: mediana 0,84 s, p90 2,33 s, maximo 5,94 s), entao a
    mesma tira de 24 raios cobre de ~12 s a ~48 s conforme o tape acelera ou
    esfria. Sem esse numero impresso, "constantemente" nao e verificavel.
    """

    if len(leituras) < 2:
        return 0.0
    duracao = leituras[-1][0] - leituras[0][0]
    return max(0.0, duracao / NS_POR_SEGUNDO)


TETO_EM_SIGMAS = 1.0
"""Quantos desvios-padrao de variacao a leitura da tela pode andar por
DURACAO TIPICA de leitura — convertido para "por segundo" em
`teto_por_segundo`, que e a forma que a tela usa e imprime.

Esta e a "estatistica em que podemos nos basear" que o operador pediu: nao
um numero escolhido a gosto, e sim a mesma linguagem de z-score de
`fluxopro/aprendizado/padroes.py`, que ja mede "grande em relacao ao
periodo" contra media e desvio-padrao do proprio historico. Aqui o
historico e a serie do quadro e a grandeza medida e a VARIACAO entre
leituras consecutivas.

Com 1σ, um salto de z σ leva ~⌈z⌉ leituras de duracao tipica para aparecer
inteiro: z=1 passa direto (sem atraso nenhum), z=3 leva 3. E exatamente o
pedido — "mudancas drasticas de extremos so quando existe agressoes muito
grandes em relacao ao periodo constantemente": pico isolado e cortado e
recua na leitura seguinte; empurrao que se SUSTENTA chega ao extremo, porque
ganha mais 1σ a cada duracao tipica.

**Escopo da medicao — corrigido na rodada 2, era imprecisao de declaracao.**
O codigo NUNCA ve a corrida inteira: `asg._serie` e uma `deque(maxlen=480)`,
entao o σ de cada quadro sai de, no maximo, 480 amostras (22 a ~70 leituras
distintas, conforme a cadencia). Ha portanto DOIS escopos, e eles nao dao o
mesmo numero:

* **corrida inteira** (204 leituras): σ = 0,1898. E o escopo da tabela
  comparativa abaixo — serve para comparar as FORMULAS entre si sobre a mesma
  serie, e so para isso;
* **janela que o codigo enxerga** (deque de 480): σ **nao e uma constante** —
  medido quadro a quadro no mesmo run, mediana 0,1761, minimo 0,0423, maximo
  0,3243. Uma sonda independente, em outro run, mediu 0,1334 na mediana. Os
  tres numeros sao compativeis: σ e remedido a cada quadro de proposito, e e
  por isso que ele **sai impresso na legenda** em vez de ficar so aqui.

A rodada 1 desta regiao declarava "σ = 0,1898" como se fosse o que o teto vale
em tela; era o σ da corrida inteira. Numero de docstring que nao bate com o
que o codigo ve e o mesmo defeito de declaracao que esta bancada ja reprovou.

Em unidade de tela (teto POR SEGUNDO, que e o que a legenda mostra), medido
quadro a quadro no mesmo run: mediana **8,7%/s**, faixa de 1,8%/s a 17,0%/s;
280 amostras de arranque sem teto nenhum, com `SEM TETO (AMOSTRA CURTA)`
escrito na legenda durante todas elas. O periodo coberto pelos 24 raios
visiveis: mediana 31,2 s, maximo 60,0 s — a razao de ele ser declarado.

Comparacao contra a media movel de 5 que estava aqui, amostra a amostra,
sobre a MESMA serie (corrida inteira):

| | maior passo | erro medio vs cru | atraso (correlacao cruzada) |
|---|---|---|---|
| cru | 0,6008 | — | — |
| MM5 | 0,1989 | 0,1325 | 0 amostras (r=0,902) |
| teto 1σ | **0,1898** (garantido) | **0,0422** | 0 amostras (r=0,973) |

A MM5 perde nos dois eixos: distorce 3,1x mais e nem assim garante passo
menor — ela nao tem teto nenhum, so dilui. O teto tem garantia dura e ainda
fica 3x mais perto do valor cru, porque so age quando o salto e grande de
verdade.

**Custo, e ele esta na tela:** medido por critico independente no replay de
28/08 — 6,4% das amostras com cor divergente do valor cru, 1,0% com cor
oposta, em 8 episodios, mediana 1,51 s e maximo 4,28 s de atraso. Enquanto a
leitura persegue o alvo, a regiao desenha um tracinho pontilhado na altura do
valor CRU sobre o raio e carimba `LIMITADO` na legenda — o operador ve que a
leitura esta atras de um numero maior, em vez de o painel esconder a virada.

IMPRECISO quanto ao valor 1,0 (poderia ser 0,5 ou 2,0); CONFIRMADO quanto a
origem do teto, que e medido da propria serie a cada quadro e nao esta
cravado em lugar nenhum."""

MIN_VARIACOES_PARA_TETO = 8
"""Abaixo disto nao ha teto: a leitura crua passa inteira.

IMPRECISO — engenharia. `padroes.py` aceita z-score com n>=2, o que aqui
daria um σ que muda de valor a cada amostra nova e limitaria por um numero
sem significado. Com poucas variacoes observadas preferimos NAO limitar a
limitar por um sigma inventado: degradar declarando, nunca fabricar.
Medido: no arranque isso vale por ~130 amostras, e a legenda diz
`SEM TETO (AMOSTRA CURTA)` durante todo esse tempo."""


def teto_de_variacao(leituras: tuple[tuple[int, float], ...]) -> float:
    """Desvio-padrao populacional das VARIACOES entre leituras consecutivas.

    `0.0` = amostra insuficiente. Nunca chuta um sigma. E a materia-prima de
    `teto_por_segundo`, que e o teto que a tela usa de fato.
    """

    if len(leituras) < MIN_VARIACOES_PARA_TETO + 1:
        return 0.0
    valores = [valor for _, valor in leituras]
    variacoes = [b - a for a, b in zip(valores, valores[1:])]
    media = sum(variacoes) / len(variacoes)
    variancia = sum((v - media) ** 2 for v in variacoes) / len(variacoes)
    return variancia ** 0.5


def _duracao_mediana_s(leituras: tuple[tuple[int, float], ...]) -> float:
    if len(leituras) < 2:
        return 0.0
    duracoes = sorted(
        (b[0] - a[0]) / NS_POR_SEGUNDO for a, b in zip(leituras, leituras[1:])
    )
    meio = len(duracoes) // 2
    if len(duracoes) % 2:
        return duracoes[meio]
    return (duracoes[meio - 1] + duracoes[meio]) / 2


def teto_por_segundo(leituras: tuple[tuple[int, float], ...]) -> float:
    """Teto de variacao **por SEGUNDO de tape** — a unidade que a rodada 2
    corrigiu. `0.0` = sem teto (amostra curta), e o valor cru passa inteiro.

        teto/s = σ(variacoes entre leituras) · TETO_EM_SIGMAS / duracao
                 MEDIANA de uma leitura

    Por que em segundos, e nao por leitura (lacuna julgada na rodada 1): uma
    leitura nao tem duracao fixa. Medido no replay real de 28/08 (326 leituras
    distintas): duracao mediana 0,84 s, p90 2,33 s, maxima 5,94 s — ou seja, a
    MESMA tira de 24 raios cobre de 12,4 s a 47,8 s (mediana 25,9 s) conforme
    o tape acelera ou esfria. Com o teto ancorado em leitura, ele era uma trava
    elastica no tempo: os mesmos 0,13 valiam para 0,84 s ou para 5,9 s. E o
    pedido do operador tem a palavra `periodo` dentro dele — "agressoes muito
    grandes em relacao ao **periodo** constantemente". Sem escala de tempo
    fixa, "constantemente" nao e verificavel.

    Agora a permissao de cada leitura e `teto/s × Δt daquela leitura`: quem
    demorou mais anda proporcionalmente mais, porque mais tempo passou de
    verdade. A leitura de duracao TIPICA continua ganhando exatamente 1σ, que
    e o comportamento verificado e aprovado na rodada 1 — a mudanca corrige a
    elasticidade nas pontas, nao o miolo.

    Invariante que a tela passa a garantir, e que e verificavel com relogio na
    mao: **nenhum trecho anda mais que `teto/s` por segundo** (antes: "1σ por
    leitura de duracao indefinida", que nao se podia conferir).

    Base estatistica: mesma linguagem de z-score de
    `fluxopro/aprendizado/padroes.py` ("grande em relacao ao periodo" medido
    contra media e desvio-padrao do proprio historico). Nada cravado: σ e a
    duracao mediana sao remedidos a cada quadro, e o teto sai IMPRESSO na
    legenda (`TETO 16%/s`), junto do periodo que a tira cobre (`· 26 s`).

    Mediana como normalizador (e nao media) e escolha de engenharia —
    IMPRECISO: a distribuicao de duracao tem cauda longa (0,84 s de mediana
    contra 5,94 s de maximo) e a media seria puxada pelas pausas.
    """

    sigma = teto_de_variacao(leituras)
    if sigma <= 0:
        return 0.0
    duracao = _duracao_mediana_s(leituras)
    if duracao <= 0:
        return 0.0
    return sigma * TETO_EM_SIGMAS / duracao


def suavizar_por_taxa(
    leituras: tuple[tuple[int, float], ...], teto_s: float
) -> tuple[float, ...]:
    """Limitador de TAXA em TEMPO (o "contragiro" do operador), nao media movel.

        g_i = g_(i-1) + clamp(f_i - g_(i-1), ± teto_s · Δt_i)

    causal, comecando no primeiro valor observado. Diferenca que importa: uma
    media movel atrasa TODO movimento, inclusive o lento; o limitador nao toca
    em movimento algum que ande menos que `teto_s` por segundo — ele so age no
    salto. Por isso o erro medio contra o valor cru e ~3x menor que o da MM5
    (medicao completa em `TETO_EM_SIGMAS`).

    Gap grande de tempo libera passo grande **de proposito**: se o tape ficou
    6 s sem nova leitura, o mercado teve 6 s para andar, e fingir que o relogio
    nao correu seria a mentira que a disciplina do projeto proibe. O custo
    continua declarado na tela (tracinho no valor cru + carimbo `LIMITADO`).

    `teto_s <= 0` devolve os valores intactos.
    """

    if not leituras:
        return ()
    valores = [valor for _, valor in leituras]
    if teto_s <= 0:
        return tuple(valores)
    saida = [valores[0]]
    atual = valores[0]
    for anterior, atual_leitura in zip(leituras, leituras[1:]):
        delta_t = max(0.0, (atual_leitura[0] - anterior[0]) / NS_POR_SEGUNDO)
        permitido = teto_s * delta_t
        passo = atual_leitura[1] - atual
        atual += max(-permitido, min(permitido, passo))
        saida.append(atual)
    return tuple(saida)


def _cor_forca(forca: float):
    """Mapeia o sinal da forca observada para o eixo de cor do NEXO.

    Usa o mesmo par verde/rosa das demais regioes (``_cor_nexo_direcao``);
    nao inventa paleta nova para a tira de barras.
    """

    if forca >= 0.05:
        return _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA)
    if forca <= -0.05:
        return _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA)
    return _asg._cor_nexo_direcao(_asg.DirecaoASG.NEUTRA)


def desenhar(painter: QPainter, rect: QRect, estado: EstadoNexo) -> None:
    if rect.height() < 30 or rect.width() < 100:
        return

    leituras = estado.leituras
    total = len(leituras)

    compra_peso, venda_peso = pesos_por_lado(leituras)
    saldo = compra_peso - venda_peso

    # 31/08/2026 — o titulo passou a descrever o que a regiao MOSTRA. Ele
    # dizia "4 LEITURAS PONDERADAS POR CONFIANCA · SALDO x% · N=4", que era
    # a contagem das leituras da matriz; essa contagem saiu da tela (ver o
    # comentario do layout abaixo) e o titulo antigo virava afirmacao falsa
    # sobre um numero que nao esta mais ali.
    painter.setFont(tokens.fonte_rotulo(8))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 4, rect.top(), rect.width() - 110, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     "PLACAR ESTATISTICO  ·  SUPORTE / RESISTENCIA")
    painter.drawText(QRect(rect.right() - 106, rect.top(), 102, ALTURA_TITULO),
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                     f"SALDO {saldo * 100:+.0f}%")

    corpo = QRect(rect.left(), rect.top() + ALTURA_TITULO + 2, rect.width(),
                  max(20, rect.height() - ALTURA_TITULO - 2))

    if not leituras:
        painter.setPen(tema_asg.NEXO_GRADE)
        painter.drawRect(corpo.adjusted(1, 1, -2, -2))
        painter.setFont(tokens.fonte_rotulo(8))
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(corpo, Qt.AlignmentFlag.AlignCenter,
                         "SEM LEITURA DERIVADA · AGUARDANDO SNAPSHOT")
        return

    # 31/08/2026: 0,60 para o resumo deixava ~40% para o selo de S/R, e o
    # selo tinha de caber titulo + alerta + micro/macro + as REGIOES com
    # preco. Com as zonas na tela (correcao do dia) a faixa de baixo passa
    # a carregar a informacao que o operador de fato usa, e fica com a
    # metade maior.
    # No classico em 1280px, 44px nao reservam numero de 16px mais a
    # legenda compacta de duas linhas. Mantem a proporcao nos demais
    # tamanhos; so aumenta o piso para impedir sobreposicao de texto.
    # A referencia reserva quase dois tercos do bloco para a leitura de
    # forca; com 46% os raios eram matematicamente presentes, mas ilegiveis
    # no quadro 1280x720. O selo de S/R continua com o espaco minimo abaixo.
    # ------------------------------------------------------------------
    # 31/08/2026 — REDESENHO APROVADO PELO OPERADOR (print antes de aplicar).
    #
    # A regiao passa a ser o PLACAR DE SUPORTE/RESISTENCIA, com a logica
    # conferida nas aulas da SG/ASG (ver `nexo/suporte_resistencia.py`,
    # bloco do placar): um lado por vez, raios = intensidade vinda da FORCA
    # DA ZONA, barrinhas = termometro do nivel, e o numero grande e o PRECO
    # DA REGIAO.
    #
    # O que saiu, e por que: a contagem COMPRA/VENDA das 4 leituras da
    # matriz (`_desenhar_contagem`) e o bloco de fontes (`_desenhar_fontes`)
    # mediam OUTRA coisa — o placar ponderado das leituras — e viviam
    # empatados em 33%/33% sem dizer nada sobre a regiao de preco, que e o
    # que a aula manda observar. As funcoes continuam no modulo (testes e
    # tooltip as usam); so deixaram de ocupar a tela.
    #
    # A FORCA OBSERVADA (a tira de raios) FICA: e leitura de historico, nao
    # de regiao, e nao conflita com o placar novo. Vai para a faixa de baixo,
    # que e a "distribuicao total" que o operador pediu.
    # MEDIDO NA TELA (31/08/2026): tentei manter a FORCA OBSERVADA numa
    # faixa de 30% aqui embaixo e ela ficou com 73px — menos que o cabecalho
    # (32) + rodape (22) + a meia-altura que o simbolo de raio exige. O
    # resultado foi a propria regiao escrevendo "AMPLIE O PAINEL", e o
    # termometro do placar sumindo por falta de altura.
    #
    # A regiao passa a ser SO o placar de suporte/resistencia, que e o que o
    # operador aprovou no print. A FORCA OBSERVADA nao foi apagada do
    # projeto: `_desenhar_barras` continua aqui, com seus testes, para quem
    # tiver espaco para ela.
    _sr_ui.desenhar_placar(painter, corpo, estado.sr_snapshot)


def texto_tooltip(rect: QRect, pos: QPoint, estado: EstadoNexo) -> str | None:
    """Explicacao contextual para o passe-mouse na regiao estatistica.

    O texto e derivado do mesmo snapshot usado na pintura. Nao calcula um
    novo score e nao acessa feed: serve apenas para tornar a leitura do
    quadro verificavel sem depender de memoria ou de cor.
    """

    if not rect.contains(pos) or not estado.leituras:
        return None
    corpo = QRect(rect.left(), rect.top() + ALTURA_TITULO + 2, rect.width(),
                  max(20, rect.height() - ALTURA_TITULO - 2))
    altura_resumo = max(82, round(corpo.height() * 0.72))
    linha = QRect(corpo.left(), corpo.top(), corpo.width(), altura_resumo)
    largura_contagem = max(150, round(linha.width() * 0.38))
    largura_fontes = max(110, round(linha.width() * 0.26))
    limite_contagem = linha.left() + largura_contagem
    limite_fontes = limite_contagem + VAO_LADRILHO + largura_fontes
    saldo = pesos_por_lado(estado.leituras)[0] - pesos_por_lado(estado.leituras)[1]
    if pos.x() < limite_contagem:
        return (
            "PLACAR ESTATÍSTICO\n"
            "COMPRA e VENDA são forças separadas, ponderadas pela confiança.\n"
            "Alta=1,0 · Média=0,6 · Baixa=0,3 · Indisponível=0,0\n"
            f"Saldo atual: {saldo * 100:+.0f}%\n"
            "Não é probabilidade nem ordem; é leitura consultiva."
        )
    if pos.x() < limite_fontes:
        return (
            "FONTES DA FORÇA\n"
            "Cada linha mostra a contribuição da mesma leitura usada no placar.\n"
            "COMPRA usa força positiva; VENDA usa força negativa.\n"
            "— significa que a fonte não está disponível no snapshot."
        )
    return (
        "FORÇA OBSERVADA\n"
        "Cada posição é uma leitura cronológica da força composta.\n"
        "Acima da linha = compra · abaixo = venda.\n"
        "Pilhas separadas de 0 a 5 raios = intensidade; cor = direcao.\n"
        "Zero abaixo de 5%; 1 ate 20%, 2 ate 40%, 3 ate 60%, 4 ate 80%, 5 acima de 80%.\n"
        "Percentual exato no cabecalho; altura em degraus. Nao e probabilidade.\n"
        "A série é histórica e não representa uma nova decisão."
    )


def _desenhar_contagem(painter: QPainter, rect: QRect,
                       leituras: tuple[tuple[str, object], ...], total: int) -> None:
    """Duas caixas com moldura de estado: quantas leituras apontam pra cada lado.

    A contagem nasce de ``leituras`` (o mesmo tanto passado para os
    ladrilhos abaixo) — nunca um numero solto: a legenda de cada caixa
    declara o denominador de onde ela saiu.
    """

    n_compra = sum(1 for _, linha in leituras if linha.direcao is _asg.DirecaoASG.COMPRA)
    n_venda = sum(1 for _, linha in leituras if linha.direcao is _asg.DirecaoASG.VENDA)
    # Cada lado sai da SUA propria soma (ver `pesos_por_lado`), nao de um
    # score assinado unico — por isso os dois podem ser >0 ao mesmo tempo e
    # nenhum dos dois salta ao cruzar o zero.
    peso_compra, peso_venda = pesos_por_lado(leituras)
    largura = max(40, (rect.width() - VAO_LADRILHO) // 2)
    caixa_compra = QRect(rect.left(), rect.top(), largura, rect.height())
    caixa_venda = QRect(caixa_compra.right() + VAO_LADRILHO, rect.top(),
                        max(40, rect.width() - largura - VAO_LADRILHO), rect.height())
    _desenhar_placar(painter, caixa_compra, "COMPRA", peso_compra, n_compra, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA))
    _desenhar_placar(painter, caixa_venda, "VENDA", peso_venda, n_venda, total,
                     _asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA))


def _desenhar_fontes(painter: QPainter, rect: QRect,
                     leituras: tuple[tuple[str, object], ...]) -> None:
    """Mostra a decomposicao do mesmo conjunto que alimenta o placar.

    ``—`` e deliberado quando a matriz nao publica a fonte: a tabela nao
    transforma ausencia de Linha Azul/Regime em zero. Os percentuais sao
    contribuicoes assinadas por fonte, enquanto o grafico ao lado mostra a
    serie temporal da forca composta do snapshot.
    """

    painter.fillRect(rect, tema_asg.NEXO_PAINEL_ALTO)
    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawRect(rect.adjusted(0, 0, -1, -1))

    por_nome = {str(nome).upper(): linha for nome, linha in leituras}
    aliases = {
        "MACRO": ("MACRO", "HORIZONTE"),
        "MICRO": ("MICRO", "PULSO"),
        "LINHA": ("LINHA", "LINHA AZUL", "MAKERPROXY", "PRESENCA"),
        "REGIME": ("REGIME", "VELOCIMETRO", "RITMO"),
    }

    fonte = tokens.fonte_rotulo(6)
    painter.setFont(fonte)
    cabecalho_y = rect.top() + 16
    colunas = (rect.left() + 5, rect.left() + round(rect.width() * 0.42),
               rect.left() + round(rect.width() * 0.70))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(rect.left() + 5, rect.top() + 3, rect.width() - 10, 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     "FONTE")
    painter.setPen(_asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA))
    painter.drawText(QRect(colunas[1], rect.top() + 3, rect.width() // 3, 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     "COMPRA")
    painter.setPen(_asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA))
    painter.drawText(QRect(colunas[2], rect.top() + 3, rect.width() // 3, 11),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     "VENDA")

    painter.setPen(tema_asg.NEXO_GRADE)
    painter.drawLine(rect.left() + 3, cabecalho_y, rect.right() - 3, cabecalho_y)
    altura_linha = max(14, (rect.height() - 19) // 4)
    for indice, rotulo in enumerate(("MACRO", "MICRO", "LINHA", "REGIME")):
        y = cabecalho_y + indice * altura_linha
        painter.setPen(tema_asg.NEXO_GRADE)
        if indice:
            painter.drawLine(rect.left() + 3, y, rect.right() - 3, y)
        linha = None
        for alias in aliases[rotulo]:
            linha = por_nome.get(alias)
            if linha is not None:
                break
        if linha is None:
            compra, venda = "—", "—"
        else:
            valor = max(-1.0, min(1.0, float(getattr(linha, "forca", 0.0))))
            compra = f"{max(0.0, valor) * 100:.0f}%" if valor > 0.005 else "—"
            venda = f"{max(0.0, -valor) * 100:.0f}%" if valor < -0.005 else "—"
        painter.setFont(fonte)
        painter.setPen(tema_asg.NEXO_MUTED)
        painter.drawText(QRect(colunas[0], y + 2, max(30, colunas[1] - colunas[0] - 4),
                               altura_linha), Qt.AlignmentFlag.AlignLeft, rotulo)
        painter.setPen(_asg._cor_nexo_direcao(_asg.DirecaoASG.COMPRA)
                       if compra != "—" else tema_asg.NEXO_MUTED)
        painter.drawText(QRect(colunas[1], y + 2, max(22, colunas[2] - colunas[1] - 3),
                               altura_linha), Qt.AlignmentFlag.AlignLeft, compra)
        painter.setPen(_asg._cor_nexo_direcao(_asg.DirecaoASG.VENDA)
                       if venda != "—" else tema_asg.NEXO_MUTED)
        painter.drawText(QRect(colunas[2], y + 2, rect.right() - colunas[2] - 4,
                               altura_linha), Qt.AlignmentFlag.AlignLeft, venda)


def _desenhar_placar(painter: QPainter, caixa: QRect, rotulo: str, peso: float,
                     contagem: int, total: int, cor) -> None:
    """`peso` (0-1, ja isolado por lado — ver `placar_ponderado`) e o NUMERO
    GRANDE agora; `contagem`/`total` continuam so na legenda de baixo, como
    o denominador honesto de sempre — nunca removidos, so deixaram de ser
    o numero principal."""

    painter.fillRect(caixa, tema_asg.NEXO_PAINEL_ALTO)
    caneta = QPen(cor)
    caneta.setWidth(2)
    painter.setPen(caneta)
    painter.drawRect(caixa.adjusted(1, 1, -2, -2))

    painter.setFont(tokens.fonte_rotulo(7))
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(caixa.adjusted(6, 4, -6, 0),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, rotulo)

    legenda = f"{contagem} DE {total} LEITURAS · CONVICCAO PONDERADA"
    fonte_legenda = tokens.fonte_rotulo(6)
    largura_texto = max(1, caixa.width() - 12)
    compacta = QFontMetrics(fonte_legenda).horizontalAdvance(legenda) > largura_texto
    altura_legenda = 11
    flags_legenda = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
    if compacta:
        # Mantem denominador e natureza ponderada. CONV. abrevia somente
        # CONVICCAO; nao remove qualificadores nem trunca a palavra final.
        # O layout largo continua com a legenda original em uma linha.
        fonte_legenda = tokens.fonte_rotulo(7)
        metrica = QFontMetrics(fonte_legenda)
        qualificador = "CONVICCAO PONDERADA"
        if metrica.horizontalAdvance(qualificador) > largura_texto:
            qualificador = "CONV. PONDERADA"
        legenda = f"{contagem} DE {total} LEITURAS\n{qualificador}"
        flags_legenda |= Qt.TextFlag.TextWordWrap
        altura_legenda = metrica.boundingRect(
            QRect(0, 0, largura_texto, caixa.height()), flags_legenda, legenda).height()

    area_numero = caixa.adjusted(6, 12, -6, -altura_legenda - 3)
    tamanho_numero = max(16, min(30, caixa.height() // 2))
    fonte_numero = tokens.fonte_numero(tamanho_numero, QFont.Weight.Bold)
    while compacta and tamanho_numero > 16 and QFontMetrics(fonte_numero).height() > area_numero.height():
        tamanho_numero -= 1
        fonte_numero = tokens.fonte_numero(tamanho_numero, QFont.Weight.Bold)
    painter.setFont(fonte_numero)
    painter.setPen(cor)
    painter.drawText(area_numero, Qt.AlignmentFlag.AlignCenter,
                     f"{round(peso * 100)}%")

    painter.setFont(fonte_legenda)
    painter.setPen(tema_asg.NEXO_MUTED)
    painter.drawText(QRect(caixa.left() + 6, caixa.bottom() - altura_legenda - 2,
                          largura_texto, altura_legenda), flags_legenda, legenda)


# Silhueta de raio/relampago (pedido do operador, 27/08/2026: "deve ser
# representados por raios, verde quando e positivo e vermelho para
# negativos" — substitui a barra retangular lisa). Pontos em coordenadas
# UNITARIAS (0..1 em x e y), sentido "caindo" de cima pra baixo (y=0 topo,
# y=1 base) — a forma natural de um relampago aponta pra baixo. Barras
# NEGATIVAS (que ja crescem do eixo pra baixo neste grafico) usam a forma
# direto; POSITIVAS espelham verticalmente, porque aqui "positivo" cresce
# pra cima como qualquer outra barra do produto — o raio come continua
# apontando "para fora" do eixo em vez de de cabeca para baixo.
# Ordem no contorno, para que o raio continue legível mesmo quando a coluna
# fica estreita (o poligono anterior se cruzava e acabava parecendo uma linha).
_PONTOS_RAIO_UNITARIOS = (
    (0.46, 0.00), (1.00, 0.00), (0.63, 0.40), (0.96, 0.40),
    (0.12, 1.00), (0.36, 0.58), (0.00, 0.58),
)


def _poligono_raio(caixa: QRect, invertido: bool) -> QPolygon:
    largura = max(0, caixa.width() - 1)
    altura = max(0, caixa.height() - 1)
    pontos = []
    for ux, uy in _PONTOS_RAIO_UNITARIOS:
        y = (1.0 - uy) if invertido else uy
        pontos.append(QPoint(caixa.left() + round(ux * largura), caixa.top() + round(y * altura)))
    return QPolygon(pontos)


RAIOS_MAX_POR_LEITURA = 5


def quantidade_raios_forca(forca: float) -> int:
    """Converte a intensidade absoluta [-1,1] em 0..5 raios visuais.

    A força continua sendo a altura do conjunto; a quantidade é uma segunda
    codificação visual monotônica do mesmo snapshot. Zero não fabrica raio e
    valores muito pequenos ainda ganham um único marcador legível.
    """

    magnitude = max(0.0, min(1.0, abs(float(forca))))
    if magnitude < 0.05:
        return 0
    return min(RAIOS_MAX_POR_LEITURA, max(1, math.ceil(magnitude * RAIOS_MAX_POR_LEITURA)))


def _texto_periodo(segundos: float) -> str:
    """Periodo coberto pela tira, em unidade legivel de relance.

    Abaixo de 90 s em segundos inteiros (a faixa medida no replay real:
    12 s a 48 s); acima disso em minutos, para nao imprimir "312 s".
    """

    if segundos < 90:
        return f"{segundos:.0f} s"
    return f"{segundos / 60:.0f} min"


ALTURA_MIN_RAIO_PX = 5
"""Piso de legibilidade do SIMBOLO de raio, em pixels.

DEFEITO CORRIGIDO EM 31/08/2026 (operador: "a representacao visual da
quantidade crescente de raios ainda precisa ser corrigida para cumprir
integralmente o que foi aprovado").

A contagem 0..5 sempre esteve certa — e por isso a suite passava. O que
falhava era o TAMANHO: a altura saia de `(metade - 4*vao) // 5`, sem piso,
e o unico portao era `area.height() >= 24`. Medido:

    area util   24px -> simbolo de 1px
    area util   40px -> simbolo de 2px
    area util   78px -> simbolo de 5px   <- a regiao REAL do produto

Com 1-5px o glifo de relampago degenera num tracinho horizontal: na tela do
pregao o cabecalho dizia `VENDA -21,3% · 2/5` e o operador via dois riscos
colados, nada parecido com a escada da escala aprovada
(`outputs/qa_raios_entrega_20260831/escala_1_a_5.png`), que foi medida numa
caixa bem maior, com simbolo de ~12px.

Abaixo deste piso o desenho NAO encolhe mais: primeiro o VAO cede (o
espacamento e conforto, o simbolo e a leitura), e se ainda assim nao couber
a regiao declara `AMPLIE O PAINEL` em vez de desenhar um risco que finge ser
um raio."""


def geometria_pilha_raios(metade: int) -> tuple[int, int] | None:
    """`(altura_do_simbolo, vao)` para caber os 5 niveis em `metade` pixels.

    `None` quando nem com vao minimo o simbolo alcanca
    `ALTURA_MIN_RAIO_PX` — o chamador declara em vez de desenhar.

    Funcao PURA e publica de proposito: e a MESMA regra que decide o portao
    ("cabe?") e o desenho ("de que tamanho?"). Ter duas copias dessa conta
    foi exatamente o que deixou o portao aceitar 24px enquanto o desenho
    produzia 1px.
    """

    for vao in (2, 1):
        altura = (metade - 4 * vao) // 5
        if altura >= ALTURA_MIN_RAIO_PX:
            return min(12, altura), vao
    return None


def caixas_pilha_raios(area: QRect, coluna: int, colunas: int, forca: float) -> tuple[QRect, ...]:
    """Simbolos separados verticalmente; nenhuma multiplicacao ocupa a largura.

    A altura passa a ser quantizada em 1..5 niveis. O percentual continuo e
    mostrado no cabecalho; a formula da forca e seu limitador nao mudam.
    """
    quantidade = quantidade_raios_forca(forca)
    if not quantidade or area.width() < colunas * 3:
        return ()
    meio = area.center().y()
    metade = min(meio - area.top(), area.bottom() - meio) - 2
    geometria = geometria_pilha_raios(metade)
    if geometria is None:
        return ()
    altura, vao = geometria
    x0 = area.left() + coluna * area.width() // colunas
    x1 = area.left() + (coluna + 1) * area.width() // colunas
    largura = max(1, min(10, x1 - x0 - 1))
    x = x0 + (x1 - x0 - largura) // 2
    caixas = []
    for indice in range(quantidade):
        deslocamento = 2 + indice * (altura + vao)
        y = meio - deslocamento - altura if forca > 0 else meio + deslocamento
        caixas.append(QRect(x, y, largura, altura))
    return tuple(caixas)


def _desenhar_barras(painter: QPainter, rect: QRect,
                     serie: tuple[tuple[int, int, float, int], ...]) -> None:
    """Historico cronologico com pilhas de 0..5 raios realmente separados.

    Mantem deduplicacao, limitador por segundo e ultimas 24 leituras. Em
    larguras extremas o rodape declara o subconjunto visivel. A quantidade
    codifica a intensidade em degraus; nao muda o score publicado.
    """
    painter.save()
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    painter.setPen(tema_asg.NEXO_GRADE)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def texto(caixa, conteudo, tamanho=8, cor=tema_asg.NEXO_MUTED):
        painter.setFont(tokens.fonte_rotulo(tamanho))
        painter.setPen(cor)
        painter.drawText(caixa, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         conteudo)

    texto(QRect(rect.left() + 5, rect.top() + 2, rect.width() - 10, 14),
          "FORÇA OBSERVADA", 9)
    if not serie:
        texto(rect.adjusted(5, 18, -5, -4), "SEM HISTÓRICO", 8)
        painter.restore()
        return

    leituras = leituras_distintas(serie)
    teto = teto_por_segundo(leituras)
    limitadas = suavizar_por_taxa(leituras, teto)
    # 31/08/2026 — cabecalho e rodape cederam 4px cada para a AREA DO
    # GRAFICO. O simbolo de raio tem piso de legibilidade
    # (`ALTURA_MIN_RAIO_PX`) e a conta que o dimensiona divide a meia-altura
    # por 5 niveis: com 36+26 reservados, uma regiao de 120px sobrava 58 de
    # area e o simbolo caia abaixo do piso — a pilha inteira sumia. Os dois
    # blocos de texto continuam cabendo (14px + 15px = 29 < 32).
    altura_cabecalho = 32
    altura_rodape = 22
    area = rect.adjusted(5, altura_cabecalho, -5, -altura_rodape)
    capacidade = max(1, min(24, area.width() // 4))
    visiveis = leituras[-capacidade:]
    exibidas = limitadas[-len(visiveis):]
    atual = exibidas[-1]
    quantidade = quantidade_raios_forca(atual)
    lado = "COMPRA" if atual > 0 else "VENDA"
    if quantidade == 0:
        lado = "NEUTRO"
    if rect.width() < 140:
        lado = {"COMPRA": "C", "VENDA": "V", "NEUTRO": "N"}[lado]
    percentual = f"{atual * 100:+.1f}%".replace(".", ",")
    texto(QRect(rect.left() + 5, rect.top() + 17, rect.width() - 10, 15),
          f"{lado} {percentual} · {quantidade}/5", 9, _cor_forca(atual))
    meio = area.center().y()
    metade = max(1, min(meio - area.top(), area.bottom() - meio) - 2)
    limitou = any(abs(bruto - valor) > .01 for valor, (_, bruto) in zip(exibidas, visiveis)) and teto > 0

    if area.height() >= 24 and area.width() >= len(exibidas) * 3:
        # Linha de zero separa compra/venda; cada coluna continua sendo UMA
        # leitura. Pilhas crescem para fora do eixo, sem formas coladas.
        painter.setPen(QPen(tema_asg.NEXO_MUTED, 1))
        painter.drawLine(area.left(), meio, area.right(), meio)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for indice, (valor, (_, bruto)) in enumerate(zip(exibidas, visiveis)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_cor_forca(valor))
            for caixa in caixas_pilha_raios(area, indice, len(exibidas), valor):
                painter.drawPolygon(_poligono_raio(caixa, valor > 0))
            # Marca crua ocupa a borda do slot, nao se funde com os raios.
            if teto > 0 and abs(bruto - valor) > .01:
                x = area.left() + (indice + 1) * area.width() // len(exibidas) - 1
                y = meio - round(max(-1.0, min(1.0, bruto)) * metade)
                painter.setPen(_cor_forca(bruto))
                painter.drawPoint(x, y)
    else:
        texto(area, "AMPLIE O PAINEL", 8)

    periodo = periodo_coberto_s(visiveis)
    plural = "LEITURA" if len(visiveis) == 1 else "LEITURAS"
    legenda = f"{len(visiveis)} {plural}"
    if capacidade < min(24, len(leituras)):
        legenda += f"/{min(24, len(leituras))}"
    if periodo > 0:
        legenda += f" · {_texto_periodo(periodo)}"
    if teto > 0:
        taxa = teto * 100
        taxa_texto = ("<0,01" if taxa < .01 else
                      f"{taxa:.2f}".replace(".", ",") if taxa < 1 else f"{taxa:.0f}")
        legenda += f"\nTETO {taxa_texto}%/s (1σ)"
        if limitou:
            legenda += " · LIMITADO"
    else:
        legenda += "\nSEM TETO (AMOSTRA CURTA)"
    texto(QRect(rect.left() + 4, rect.bottom() - altura_rodape + 1,
                rect.width() - 8, altura_rodape), legenda, 7)
    painter.restore()
