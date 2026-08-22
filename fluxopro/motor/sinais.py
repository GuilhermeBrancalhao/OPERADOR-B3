"""Motor de sinais: codifica a confluência de 3 condições extraída da metodologia
ASG/Gargantini (ver `PROGRESSO.md`, seção "A METODOLOGIA", com citação direta
das transcrições dos vídeos).

As 3 condições, na ordem em que a metodologia exige:

1. **Direção do dia** — dominância percentual comprador×vendedor cruza um
   limiar. Sem isso, "não tem direcional, não tem ainda o alinhamento
   seguro". **A fonte diverge sobre o número exato do corte de
   "direcional"** e a divergência está registrada em
   `pesquisa/metodologia_regras.md:26-27`: um vídeo (`vs76O7j_inU`) diz
   *"acima de 75% já é uma amostragem mais direcional"*; outro
   (`zenDbXgFEEw`) diz *"acima de 70% direcional"*. A própria pesquisa marca
   o ponto como **IMPRECISO** e conclui que o autor provavelmente não usa um
   número fixo único, e sim uma faixa de convicção crescente. Aqui o default
   é 0.70 — o extremo inferior da divergência, que é o mais permissivo e
   portanto o que NÃO esconde o desacordo por trás de um corte mais alto —
   e `dominancia_minima` é parametrizável justamente para quem quiser 0.75.
   Escolher 0.70 é decisão de engenharia declarada, não leitura unívoca da
   fonte.
2. **Retorno a uma região de interesse** — o preço faz pullback e volta a
   uma FAIXA (não um preço exato). Aqui a região é aproximada por
   VAH/VAL do Volume Profile ou por uma faixa explícita fornecida por fora
   (ex.: nível de S/R) — a metodologia não expõe a fórmula exata da
   ferramenta original, então isto é uma reconstrução funcional, marcada
   como tal.
3. **Virada da "micro"** — o fluxo de curtíssimo prazo precisa reverter na
   direção pretendida. Aqui isso é operacionalizado pelo delta de uma janela
   curta mudando de sinal, combinado com a comparação da PRIMEIRA metade da
   janela contra a SEGUNDA (ver `_micro_virou`).

Este motor NÃO reproduz a "ferramenta" original pixel a pixel (não temos
acesso ao código dela) — ele implementa a MESMA LÓGICA DE CONFLUÊNCIA sobre
dado próprio, com parâmetros abertos para o usuário calibrar. Isso é
declarado explicitamente para não confundir "sinal equivalente" com "cópia".

## Faixas de convicção (`FaixaConviccao`) — e a colisão de nomes

`pesquisa/metodologia_regras.md:30-36` consolida a leitura do percentual em
quatro faixas: 50% empate/lateral · 50–65% pré-direcional · ≥70–75%
direcional · ≥80–85% máxima convicção. Todas estão implementadas em
`FaixaConviccao`, com os cortes parametrizáveis em `ConfigMotorSinais`.

Duas honestidades obrigatórias sobre essa tabela:

- **Existe um vão entre 0,65 e 0,70 que a fonte não rotula** — os dois
  números vêm de vídeos diferentes. Ele aparece aqui como
  `FaixaConviccao.ZONA_CINZA`, e não como "pré-direcional esticado até 0,70"
  nem como "direcional antecipado": inventar um rótulo para preencher o vão
  seria atribuir à fonte uma leitura que ela não deu.
- **`FaixaConviccao.PRE_DIRECIONAL` (50–65%, da fonte) NÃO é o mesmo que
  `EstagioSinal.PRE_SINAL`.** O primeiro é uma faixa do percentual de
  dominância; o segundo é um estágio da confluência (condições 1 e 2
  satisfeitas, micro ainda virando). Um sinal em `PRE_SINAL` está sempre em
  faixa `DIRECIONAL` ou `MAXIMA_CONVICCAO` — nunca em `PRE_DIRECIONAL`.

## O caso WINFUT: por que dominância percentual sozinha não basta

`pesquisa/ferramenta_componentes.md:97-105` registra o dia em que a macro
ficou vendedora quase o pregão inteiro (picos de −1500, −1735, **−1925**) e
depois inverteu para um pico comprador de ~**+915** — que "nunca se aproximou
da magnitude dos picos vendedores" e "em poucos minutos praticamente retrocede
tudo". Quem comprou aquilo ficou "mal posicionado". A conclusão da pesquisa é
explícita: *"a leitura correta exige normalizar por (a) magnitude relativa ao
histórico intradiário e (b) persistência temporal, não só o sinal
instantâneo."*

Uma razão percentual é cega às duas coisas: 90% de dominância sobre 1925
contratos e 90% sobre 915 dão o mesmo `0.900`. Por isso este motor aplica:

- **(a) magnitude relativa** — `_magnitude` é o |delta| absoluto da janela de
  dominância, e ele é comparado com o **pico robusto do regime corrente**: a
  K-ésima maior magnitude (`tamanho_topo_magnitude`) de uma **janela móvel
  medida em amostras aceitas**, não no relógio e não no dia inteiro.
  `magnitude_relativa = magnitude / referencia`. Abaixo de
  `magnitude_relativa_minima` a condição 1 **não** é dada por confirmada, por
  mais alto que esteja o percentual. Ver `_magnitude_referencia` para os DOIS
  defeitos espelhados que essa escolha fecha — a referência que esquece o pico
  (R3/R4: 480 `CONFIRMADO` espúrios com 20.000 laterais no meio) e a que nunca
  esquece (R5 §A.3.2: mudo o resto do pregão depois de um movimento genuíno de
  10×) — e para a aritmética de por que janela de tempo, decaimento com piso e
  K maior não resolvem.
- **(b) persistência / histerese** — o estágio publicado só sobe depois que a
  condição se sustenta por `persistencia_minima_trades` **e**
  `persistencia_minima_ns`, e só cai depois que a condição falha por
  `rebaixamento_minimo_trades` **e** `rebaixamento_minimo_ns`. A fonte pede
  isso literalmente: *"se ele se sustentar acima de 70%"*
  (`metodologia_regras.md:40`). Sem histerese um único trade derrubava a
  confluência inteira, e num tape de 5.000 trades/s o estágio piscava
  milhares de vezes por segundo — era função pura do último trade, não um
  estado.

## Custo — O(1) amortizado por trade

Tudo o que este motor mede por trade sai de contador incremental:

- `_janela_dominancia` é um `deque` com `_vol_buy`/`_vol_sell`/`_vol_unknown`
  incrementais (mesmo padrão de `DetectorAbsorcao` e `MedidorAgressao`). A
  versão anterior reconstruía a lista inteira (`[t for t in ... if ...]`) e
  somava duas vezes varrendo a janela — a **cada trade**, numa janela de
  **5 minutos**, que a 5.000 trades/s guarda 1.500.000 trades. Custo total
  quadrático na taxa do mercado: a crítica R2 mediu 258 ev/s contra a barra
  de 10.000, e 67,9 milhões de avaliações de generator para 8.000 trades.
- A janela da micro é mantida em DOIS deques (`_micro_antiga`/`_micro_recente`)
  separados por um corte temporal que só anda para frente, cada um com seu
  delta incremental — assim a comparação primeira×segunda metade sai em O(1)
  em vez de refatiar e re-somar a lista.
- `_na_regiao` usa VAL/VAH **cacheados**: `value_area()` é O(n log n) nos
  níveis de preço da sessão (`sorted()` + `min` do POC + `index()` + expansão
  gulosa), e a versão anterior chamava `val()` e `vah()` — ou seja, rodava
  `value_area()` DUAS vezes — por trade. A R2 mediu 969,6 µs/trade só nisso
  com 800 níveis, teto de 1.031 trades/s. Ver `_regiao` para a política de
  invalidação do cache.
- A referência de magnitude são R min-heaps top-K de tamanho FIXO (os blocos
  da janela móvel, mais `_reservatorio` como cauda da sessão) e um deque
  monotônico do maior negócio da janela (`_maiores_qty`): todas O(1) amortizado
  por trade, memória R·K inteiros, nenhuma crescendo com a duração da sessão.
  Ler a referência é `heap[0]` — O(1), sem cache e sem ordenação, ao contrário
  do percentil que estava aqui antes; o único trabalho extra é uma varredura de
  R blocos a cada B amostras aceitas (O(R/B) amortizado). Medido em
  `bench_motor.py` estágio 4, o eixo DURAÇÃO DE SESSÃO.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.core.eventos import AgressorSide, Side, Trade


@unique
class EstagioSinal(Enum):
    """Onde a confluência está, para refletir o "pré-sinal" (farol amarelo)."""

    NENHUM = "NENHUM"
    DIRECAO_CONFIRMADA = "DIRECAO_CONFIRMADA"      # condição 1 sozinha
    NA_REGIAO = "NA_REGIAO"                        # 1 + 2
    PRE_SINAL = "PRE_SINAL"                        # 1 + 2, micro começando a virar
    CONFIRMADO = "CONFIRMADO"                      # 1 + 2 + 3 — entrada


@unique
class FaixaConviccao(Enum):
    """Faixas de leitura do percentual de dominância (ver docstring do módulo).

    `LATERAL`, `PRE_DIRECIONAL`, `DIRECIONAL` e `MAXIMA_CONVICCAO` vêm da
    tabela de `pesquisa/metodologia_regras.md:30-36`. `ZONA_CINZA` é o vão
    entre 0,65 e 0,70 que a fonte deixa sem rótulo porque os dois limites vêm
    de vídeos diferentes — está aqui explicitamente para NÃO ser confundido
    com nenhuma das faixas que a fonte de fato descreve.
    """

    LATERAL = "LATERAL"                      # ~50% — "não existe lado"
    PRE_DIRECIONAL = "PRE_DIRECIONAL"        # 50–65%
    ZONA_CINZA = "ZONA_CINZA"                # 65–70% — sem rótulo na fonte
    DIRECIONAL = "DIRECIONAL"                # ≥70–75% — zona de operação
    MAXIMA_CONVICCAO = "MAXIMA_CONVICCAO"    # ≥80–85% — "não tem o que pensar"


# Ordem de "avanço" da confluência. Só existe para a histerese saber o que é
# promoção e o que é rebaixamento.
_RANK: dict[EstagioSinal, int] = {
    EstagioSinal.NENHUM: 0,
    EstagioSinal.DIRECAO_CONFIRMADA: 1,
    EstagioSinal.NA_REGIAO: 2,
    EstagioSinal.PRE_SINAL: 3,
    EstagioSinal.CONFIRMADO: 4,
}


@dataclass(frozen=True, slots=True)
class ConfigMotorSinais:
    """Nenhum limiar cravado no corpo — tudo calibrável pelo usuário.

    Condição 1 — dominância e faixas de convicção:
    `dominancia_minima` — corte de "direcional" (a fonte diverge entre 0.70 e
    0.75; ver docstring do módulo). É também o piso das faixas operacionais:
    abaixo dele o motor não sai de `NENHUM`.
    `faixa_lateral_ate` — até aqui é empate/lateral (a fonte: 50%).
    `faixa_pre_direcional_ate` — topo do "pré-direcional" da fonte (0.65).
    `faixa_maxima_conviccao_desde` — piso da "máxima convicção" (0.80–0.85 na
    fonte; default no extremo inferior, 0.80).
    `janela_dominancia_ns` — janela de trades usada para medir a dominância.

    Condição 1 (b) — normalização por magnitude (caso WINFUT):
    `magnitude_relativa_minima` — fração da magnitude de referência do dia
    abaixo da qual a direção NÃO é dada por confirmada, por mais alto que
    esteja o percentual.
    `tamanho_topo_magnitude` (K) — quantas das maiores magnitudes da sessão
    são guardadas. A referência é a **K-ésima maior**, então K−1 outliers
    (leilão de abertura, fat finger, um único burst) não conseguem levantá-la
    sozinhos. K menor = referência mais alta e gate mais rígido; K maior =
    mais robusto a outlier e mais permissivo.
    `fator_dominio_trade_unico` — a magnitude da janela só entra na
    referência se for maior que este fator vezes o MAIOR negócio isolado da
    janela. É o anticorpo contra o fat finger: um único negócio gigante deixa
    a janela inteira (600 trades, com a janela de 5 min do default) com
    magnitude ≈ o tamanho dele, e essas 600 amostras contaminadas afogariam
    qualquer top-K. Magnitude que um só negócio explica não é fluxo do dia —
    é aquele negócio. Com 1.0 o filtro está praticamente desligado.
    `minimo_amostras_referencia` — quantos trades a sessão precisa ter visto
    antes de a referência passar a ser a K-ésima maior. Antes disso a amostra
    é curta demais para uma cauda e a referência é o **máximo da sessão** (a
    leitura mais conservadora disponível: a razão nunca passa de 1,0). Manter
    igual a K é o natural — é exatamente quando o heap enche.
    `amostras_por_bloco_referencia` (B) e `blocos_referencia` (R) — a janela
    móvel da referência, medida em AMOSTRAS ACEITAS (não em trades e não no
    relógio). A cauda é mantida em R blocos de B amostras cada; a referência é
    a maior das K-ésimas maiores dos blocos vivos. A janela vale portanto
    entre (R−1)·B e R·B amostras, e ela é **a fronteira declarada entre
    episódio e regime**: um episódio que dure menos que (R−1)·B amostras
    aceitas jamais tira o pico do dia da referência (é a proteção WINFUT das
    R3/R4); um nível que se sustente por mais que R·B amostras aceitas passa a
    ser o regime e redefine a referência (é a saída do "mudo o resto do dia"
    da R5 §A.3.2). Ver `_magnitude_referencia` para por que o eixo é amostra
    aceita e não relógio, e por que decaimento com piso não resolve.
    Com `blocos_referencia <= 0` a janela vira INFINITA (nenhum bloco sai
    dela) e a referência nunca desce — o comportamento da onda 8, mantido como
    controle executável dos testes. Se `amostras_por_bloco_referencia` for
    menor que K nenhum bloco chega a fechar, e a referência degrada para o
    MÁXIMO da sessão: conservador e monótono, nunca permissivo.

    Condição 2 — região de interesse:
    `margem_regiao_ticks` — tolerância em ticks para considerar o preço
    "dentro" da região de interesse (VAH/VAL ou faixa explícita).
    `cache_regiao_max_trades` / `cache_regiao_max_ns` — invalidação do cache
    de VAL/VAH (ver `_regiao`).

    Condição 3 — micro:
    `janela_micro_ns` — janela curta do delta que representa a "micro".
    `pre_sinal_fracao_janela_micro` — ponto de corte TEMPORAL que separa a
    primeira da segunda metade da janela micro. 0.5 dá duas metades de mesma
    duração, que é o que torna a comparação entre elas honesta.

    Histerese / persistência:
    `persistencia_minima_trades` / `persistencia_minima_ns` — quanto uma
    condição melhor precisa se sustentar para o estágio SUBIR.
    `rebaixamento_minimo_trades` / `rebaixamento_minimo_ns` — quanto a
    condição precisa falhar para o estágio CAIR (ou trocar de direção no
    mesmo posto, que é pelo menos tão sério quanto cair de posto).
    """

    dominancia_minima: float = 0.70
    faixa_lateral_ate: float = 0.50
    faixa_pre_direcional_ate: float = 0.65
    faixa_maxima_conviccao_desde: float = 0.80
    janela_dominancia_ns: int = 5 * 60_000_000_000  # 5 min

    magnitude_relativa_minima: float = 0.60
    tamanho_topo_magnitude: int = 32
    fator_dominio_trade_unico: float = 2.0
    minimo_amostras_referencia: int = 32
    amostras_por_bloco_referencia: int = 2_048
    blocos_referencia: int = 4

    margem_regiao_ticks: int = 2
    cache_regiao_max_trades: int = 200
    cache_regiao_max_ns: int = 250_000_000  # 250 ms

    janela_micro_ns: int = 15_000_000_000  # 15s
    pre_sinal_fracao_janela_micro: float = 0.5

    persistencia_minima_trades: int = 3
    persistencia_minima_ns: int = 500_000_000  # 0,5s
    rebaixamento_minimo_trades: int = 3
    rebaixamento_minimo_ns: int = 500_000_000  # 0,5s


@dataclass(frozen=True, slots=True)
class Sinal:
    timestamp_ns: int
    symbol: str
    estagio: EstagioSinal
    direcao: Side | None
    evidencia: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class _TradeJanela:
    """Só o que a janela precisa — evita segurar o `Trade` inteiro vivo."""

    timestamp_ns: int
    qty: int
    lado: AgressorSide


def _delta_de(reg: _TradeJanela) -> int:
    """Contribuição de um trade para o delta. `UNKNOWN` contribui 0 — mas o
    volume dele é contado à parte (`volume_nao_atribuido`), nunca sumido."""
    if reg.lado is AgressorSide.BUY:
        return reg.qty
    if reg.lado is AgressorSide.SELL:
        return -reg.qty
    return 0


class MotorSinais:
    """Consome trades e mantém o estágio de confluência por símbolo.

    Não é dono do `VolumeProfile` — ele é injetado para que o chamador
    escolha janela/timeframe e para não duplicar estado que o módulo de
    analytics já mantém (o motor só lê `value_area()`; quem alimenta
    `registrar_trade()` no perfil é o chamador). A "micro" (condição 3) é
    computada internamente a partir dos próprios trades recebidos — não
    depende de `CumulativeDelta`/`MedidorAgressao` porque a janela e a
    regra de reversão aqui são específicas da confluência ASG, diferentes
    do delta de sessão genérico que esses módulos calculam.

    O estágio devolvido por `ao_trade` é o estágio PUBLICADO (depois da
    histerese). O estágio cru daquele trade vai em `evidencia["estagio_bruto"]`,
    para que a diferença entre "a condição está valendo agora" e "a condição
    se sustentou o bastante para eu agir" fique auditável.
    """

    def __init__(
        self,
        symbol: str,
        volume_profile: VolumeProfile,
        config: ConfigMotorSinais | None = None,
    ) -> None:
        self._symbol = symbol
        self._vp = volume_profile
        self.config = config if config is not None else ConfigMotorSinais()

        # --- condição 1: janela de dominância, tudo incremental ---
        self._janela_dominancia: deque[_TradeJanela] = deque()
        # deque monotônico decrescente (ts, qty) — `[0][1]` é o maior negócio
        # isolado ainda dentro da janela. Ver `_amostrar_magnitude`.
        self._maiores_qty: deque[tuple[int, int]] = deque()
        self._vol_buy = 0
        self._vol_sell = 0
        self._vol_unknown = 0

        # --- condição 1 (b): cauda da magnitude, em janela móvel ---
        # A janela é medida em AMOSTRAS ACEITAS e vive em R blocos de B
        # amostras, cada bloco com seu próprio min-heap top-K (`[0]` = K-ésima
        # maior DAQUELE bloco). `_reservatorio` é o bloco CORRENTE — o nome é
        # histórico, duas ondas atrás ele era um reservoir sampling do dia — e
        # `_blocos` guarda os R−1 blocos já fechados que ainda estão na janela.
        # `_ref_janela` é a maior das K-ésimas maiores dos blocos vivos,
        # mantida incrementalmente; `_resta_bloco` conta para BAIXO até fechar
        # o bloco corrente, para o caminho quente não ler config por amostra.
        # Memória: R·K inteiros — constante, não cresce com a duração do dia.
        self._reservatorio: list[int] = []
        self._blocos: deque[list[int]] = deque()
        self._resta_bloco = max(1, self.config.amostras_por_bloco_referencia)
        self._ref_janela = 0
        self._n_visto = 0
        self._max_sessao = 0
        self._fonte_referencia = "nenhuma"

        # --- condição 2: cache de VAL/VAH ---
        self._cache_regiao: tuple[int, int] | None = None
        self._cache_regiao_ts_ns: int | None = None
        self._cache_regiao_n = 0

        # --- condição 3: micro em duas metades temporais ---
        self._micro_antiga: deque[_TradeJanela] = deque()
        self._micro_recente: deque[_TradeJanela] = deque()
        self._delta_antiga = 0
        self._delta_recente = 0

        # --- histerese ---
        self._estagio_atual: EstagioSinal = EstagioSinal.NENHUM
        self._direcao_atual: Side | None = None
        self._faixa_atual: FaixaConviccao = FaixaConviccao.LATERAL
        self._candidato: tuple[EstagioSinal, Side | None] | None = None
        self._candidato_desde_ns: int = 0
        self._candidato_n: int = 0

    # ------------------------------------------------------------------
    # Condição 1 — dominância (O(1) amortizado)
    # ------------------------------------------------------------------
    def _registrar_dominancia(self, trade: Trade) -> None:
        cfg = self.config
        reg = _TradeJanela(trade.timestamp_ns, trade.qty, trade.side_agressor)
        self._janela_dominancia.append(reg)
        mono = self._maiores_qty
        while mono and mono[-1][1] <= reg.qty:
            mono.pop()
        mono.append((reg.timestamp_ns, reg.qty))
        if reg.lado is AgressorSide.BUY:
            self._vol_buy += reg.qty
        elif reg.lado is AgressorSide.SELL:
            self._vol_sell += reg.qty
        else:
            self._vol_unknown += reg.qty

        limite = trade.timestamp_ns - cfg.janela_dominancia_ns
        janela = self._janela_dominancia
        while janela and janela[0].timestamp_ns < limite:
            antigo = janela.popleft()
            if antigo.lado is AgressorSide.BUY:
                self._vol_buy -= antigo.qty
            elif antigo.lado is AgressorSide.SELL:
                self._vol_sell -= antigo.qty
            else:
                self._vol_unknown -= antigo.qty
        while mono and mono[0][0] < limite:
            mono.popleft()

    def _dominancia(self) -> tuple[float, Side | None]:
        vol_buy = self._vol_buy
        vol_sell = self._vol_sell
        total = vol_buy + vol_sell
        if total == 0:
            return 0.5, None
        if vol_buy >= vol_sell:
            return vol_buy / total, Side.BUY
        return vol_sell / total, Side.SELL

    def _magnitude(self) -> int:
        """Tamanho absoluto do desequilíbrio na janela — o análogo do
        "contador de contexto macro" do caso WINFUT (−1925 × +915). É o que a
        razão percentual joga fora."""
        return abs(self._vol_buy - self._vol_sell)

    def _faixa(self, dominancia: float) -> FaixaConviccao:
        cfg = self.config
        if dominancia <= cfg.faixa_lateral_ate:
            return FaixaConviccao.LATERAL
        if dominancia <= cfg.faixa_pre_direcional_ate:
            return FaixaConviccao.PRE_DIRECIONAL
        if dominancia < cfg.dominancia_minima:
            return FaixaConviccao.ZONA_CINZA
        if dominancia >= cfg.faixa_maxima_conviccao_desde:
            return FaixaConviccao.MAXIMA_CONVICCAO
        return FaixaConviccao.DIRECIONAL

    # ------------------------------------------------------------------
    # Condição 1 (b) — magnitude relativa ao histórico do dia
    # ------------------------------------------------------------------
    def _amostrar_magnitude(self, magnitude: int) -> None:
        """Guarda a CAUDA da sessão: as K maiores magnitudes já vistas.

        `_reservatorio` é um min-heap de tamanho fixo K, então `[0]` é a
        K-ésima maior magnitude do dia. Custo: uma comparação por trade no
        caso comum (a magnitude corrente não entra no topo) e O(log K) só
        quando entra — mais barato que o `random.randint` por trade do
        reservoir que estava aqui antes, e sem RNG nenhum, o que torna o
        motor determinístico por construção (não mais por seed fixa).

        **Filtro de negócio único.** Magnitude que UM negócio explica sozinho
        não é fluxo do dia — é aquele negócio. E ela não aparece uma vez: a
        magnitude é o |delta| de uma JANELA, então um fat finger de 100.000
        lotes deixa as CENTENAS de amostras que couberem na janela com
        magnitude ≈ o tamanho dele. Isso afogaria qualquer top-K (o defeito
        que o top-K sozinho teria) e travaria a referência pelo resto do
        pregão. Por isso a amostra só entra se a magnitude for maior que
        `fator_dominio_trade_unico` × o MAIOR negócio isolado ainda dentro da
        janela — que `_maiores_qty` mantém em O(1) amortizado, num deque
        monotônico decrescente alimentado por `_registrar_dominancia`.
        """
        cfg = self.config
        maior_negocio = self._maiores_qty[0][1] if self._maiores_qty else 0
        if magnitude <= cfg.fator_dominio_trade_unico * maior_negocio:
            return
        capacidade = cfg.tamanho_topo_magnitude
        self._n_visto += 1
        if magnitude > self._max_sessao:
            self._max_sessao = magnitude

        # A janela só anda AQUI — depois do filtro de negócio único. É o que a
        # torna cega a tape morno: 50.000 laterais miúdos não produzem UMA
        # amostra, e por isso lateralização não mexe na referência (era por
        # onde o defeito R3/R4 entrava). Ver `_magnitude_referencia`.
        bloco = self._reservatorio
        if len(bloco) < capacidade:
            heapq.heappush(bloco, magnitude)
            if len(bloco) == capacidade and bloco[0] > self._ref_janela:
                self._ref_janela = bloco[0]
        elif capacidade > 0 and magnitude > bloco[0]:
            heapq.heapreplace(bloco, magnitude)
            if bloco[0] > self._ref_janela:
                self._ref_janela = bloco[0]
        # conta para BAIXO e testa contra zero: um LOAD_ATTR e um COMPARE_OP a
        # menos por amostra do que reler `cfg.amostras_por_bloco_referencia`.
        # `_resta_bloco` e sempre reposto com um inteiro >= 1 (ver `_rolar_bloco`
        # e `__init__`), entao ele passa exatamente por zero.
        self._resta_bloco -= 1
        if not self._resta_bloco:
            self._rolar_bloco()

    def _rolar_bloco(self) -> None:
        """Fecha o bloco corrente e aposenta o mais antigo que sair da janela.

        Roda uma vez a cada B amostras aceitas — o único ponto do motor em que
        a referência pode DESCER, e ele custa O(R) com R fixo (4 no default),
        amortizado em O(R/B) por amostra. A recomputação é exata: `_ref_janela`
        volta a ser o máximo das K-ésimas maiores dos blocos que sobraram.
        (Só o caminho de controle `blocos_referencia <= 0` foge disso: lá nada
        é aposentado, então a lista de blocos cresce com o dia e este laço
        deixa de ser O(1) amortizado. É o preço de reproduzir a onda 8 sem
        manter o código dela vivo, e não roda em nenhuma config de fábrica.)

        Bloco com menos de K amostras não vota. É o análogo por bloco do
        `minimo_amostras_referencia`: o `[0]` de um heap com 3 elementos é o
        MENOR dos três, e deixar isso virar referência abriria o gate de par em
        par a cada troca de bloco — a razão nasceria em 1,0 a cada B amostras.
        Enquanto nenhum bloco votar, `_magnitude_referencia` devolve o MÁXIMO
        da sessão, que é a leitura conservadora (a razão não passa de 1,0).
        """
        cfg = self.config
        capacidade = cfg.tamanho_topo_magnitude
        self._blocos.append(self._reservatorio)
        # `blocos_referencia <= 0` = JANELA INFINITA: nenhum bloco sai, a
        # referência nunca desce, e sobra exatamente o comportamento da onda 8
        # (a cauda do dia inteiro). É o controle executável dos testes.
        if cfg.blocos_referencia > 0:
            while len(self._blocos) > cfg.blocos_referencia - 1:
                self._blocos.popleft()
        self._reservatorio = []
        self._resta_bloco = max(1, cfg.amostras_por_bloco_referencia)
        ref = 0
        for antigo in self._blocos:
            if len(antigo) == capacidade and antigo[0] > ref:
                ref = antigo[0]
        self._ref_janela = ref

    def _magnitude_referencia(self, timestamp_ns: int) -> float | None:
        """Pico ROBUSTO do REGIME corrente — K-ésima maior de uma janela móvel
        medida em AMOSTRAS ACEITAS, não no relógio e não no dia inteiro.

        ## Os dois defeitos, que são o mesmo erro espelhado

        Ancorar a referência no DIA INTEIRO falha nas duas pontas, e as duas
        pontas já foram medidas neste repositório:

        - **Referência que ESQUECE o pico** (percentil 0,95 de um reservoir
          uniforme do dia, até a onda 8). O reservoir representa a massa, não a
          cauda: com um pico de manhã e 20.000 trades laterais depois, a massa
          vira lateral, o p95 desce ao regime morno e um repique de 45% do pico
          real passa. R3 e R4 mediram idêntico: 480 `CONFIRMADO` de compra
          espúrios, `magnitude_relativa` 0,920.
        - **Referência que NUNCA esquece o pico** (K-ésima maior da SESSÃO, a
          correção da onda 8). Consertou o WINFUT — a R5 §A.3.2 confirmou a
          varredura inteira com `mag_rel` plana em 0,450 — e abriu o espelho:
          um movimento GENUÍNO de 10× (leilão de fechamento, rolagem de
          vencimento, programa institucional) leva a referência de 9.620 para
          96.200 e o motor fica **mudo pelo resto do pregão**, com `mag_rel`
          0,100. Não é o fat finger, que `fator_dominio_trade_unico` filtra: um
          movimento de 900 negócios não é explicado por nenhum deles sozinho.

        O modo de falha novo é PIOR que o que substituiu: o antigo exigia 33
        minutos de tape morno para aparecer, o novo exige UM evento grande — e
        o WDO tem pelo menos um por dia. E ele é silencioso, porque ausência de
        sinal não parece defeito.

        ## Por que o eixo da janela é a AMOSTRA ACEITA

        Este é o ponto que faz a correção funcionar sem reabrir o WINFUT.
        Amostra só entra na cauda depois do filtro de negócio único
        (`_amostrar_magnitude`), e tape lateral miúdo **não produz nenhuma**:
        na varredura da R5, `_n_visto` fica cravado em 2.390 tanto com 1.000
        quanto com 50.000 laterais. Os 49.000 laterais a mais são 82 minutos de
        relógio e ZERO amostras. Logo:

        - uma janela em amostras não anda durante lateralização — o defeito da
          R3/R4 não pode voltar por essa porta, e não volta nem com 50.000 nem
          com 5 milhões de laterais, porque o eixo simplesmente não se move;
        - ela anda quando o mercado PRODUZ evidência de magnitude — que é
          exatamente a condição sob a qual faz sentido dizer "o patamar mudou".

        A janela vale entre (R−1)·B e R·B amostras aceitas
        (`blocos_referencia` × `amostras_por_bloco_referencia`), e essa é a
        **fronteira declarada entre evento e regime**: episódio mais curto que
        (R−1)·B amostras é julgado contra o pico do dia; nível sustentado por
        mais que R·B amostras vira o novo regime. É a única coisa que separa os
        dois casos, porque eles são localmente indistinguíveis (ver abaixo).

        ## Por que as alternativas perdem — a aritmética de cada uma

        - **Janela móvel de TEMPO** (a sugestão literal do item 9 da R3): não
          funciona, e dá para provar com os dois cenários lado a lado. A
          regressão obrigatória varre até 50.000 laterais, que a 100 ms/trade
          são ~83 minutos entre o pico e o repique: a janela precisaria ser
          MAIOR que 83 min para o WINFUT continuar barrado. O ataque B da R5
          põe ~200 s entre o pico gigante e o movimento legítimo: a janela
          precisaria ser MENOR que isso para o motor voltar a falar. Um número
          maior que 83 min e menor que 200 s não existe. E qualquer N acima da
          duração do pregão é, por definição, o comportamento de hoje. O tempo
          é o eixo errado porque mede o relógio da SALA; a amostra aceita mede
          o do mercado.
        - **Decaimento lento com piso**: aritmeticamente impossível. Para o
          WINFUT continuar barrado a referência não pode cair abaixo de
          4.329/0,60 = 7.215 — ou seja **75%** do pico do dia (9.620). Para o
          motor voltar a falar depois do leilão ela precisa cair a
          9.620/0,60 = 16.033 — ou seja **16,7%** do pico do dia (96.200).
          Qualquer piso ancorado no pico da sessão teria de ser ao mesmo tempo
          ≥ 0,75 e ≤ 0,167 desse pico. Não existe. E vale para decaimento de
          QUALQUER velocidade: a velocidade muda quando se chega lá, não o fato
          de o caminho passar pelo ponto que reabre o WINFUT. Decaimento é uma
          função monótona do pico da sessão, e os dois cenários são o MESMO
          cenário escalado por 10 — o que muda é só a razão (45% × 10%).
        - **K maior** (para um evento sozinho não encher o topo): o leilão gera
          900 amostras altas; para K−1 outliers não levantarem a referência, K
          teria de passar de 900. Mas a K-ésima maior com K ≈ 1.000 num dia de
          ~200.000 amostras não é cauda: é corpo da distribuição — é o
          percentil sobre a massa, que é literalmente o defeito R3/R4 com outro
          nome. K grande é a mesma doença. Aqui K continua 32, só que POR
          BLOCO: dentro de cada bloco continuam sendo precisos K eventos
          concordando para levantar a referência, e a robustez a outlier fica
          intacta.
        - **Dois reservoirs (sessão + recente), o maior deles**: o de sessão
          nunca esquece, logo manda sempre, e o recente é peso morto. É o
          estado de hoje com o dobro do custo.
        - **Distinguir regime de evento pela FORMA do sinal** (contiguidade,
          número de rajadas, duração do episódio): os dois cenários são um pico
          contíguo seguido de um movimento menor, idênticos a menos da escala.
          Nenhuma função só da sequência de magnitudes os separa — separar por
          razão exigiria PASSAR 10% e BARRAR 45%, que é o gate ao contrário. O
          único separador honesto é QUANTA evidência o mercado produziu depois,
          e é isso que a janela em amostras conta.

        ## O que muda e o que não muda

        Dentro da janela a referência continua **monótona não-decrescente** (o
        heap de cada bloco só troca por valores maiores). Ela só desce em
        `_rolar_bloco`, e só depois de (R−1)·B amostras aceitas de evidência
        abaixo do pico. Enquanto a sessão tem menos de
        `minimo_amostras_referencia` amostras — ou enquanto nenhum bloco
        fechou K amostras, o que inclui a config degenerada B < K — a
        referência é `_max_sessao`, a leitura mais conservadora (a razão nunca
        passa de 1,0). Toda degradação aponta para o lado RESTRITIVO; nenhuma
        para o permissivo. Com `blocos_referencia <= 0` a janela vira INFINITA
        (nenhum bloco é aposentado, a referência nunca desce) e sobra o
        comportamento da onda 8 — é o controle executável dos testes.

        Custo: O(1) por amostra (uma comparação no caso comum, O(log K) quando
        entra no topo) mais O(R) a cada B amostras. Memória R·K inteiros,
        constante na duração da sessão — medido em `bench_motor.py` estágio 4.

        O parâmetro `timestamp_ns` sobrou da versão com cache por tempo e é
        mantido na assinatura de propósito: a resposta é O(1) e a janela não é
        temporal — nenhum chamador precisou mudar em nenhuma das duas ondas.
        """
        ref = self._ref_janela
        if ref and self._n_visto >= self.config.minimo_amostras_referencia:
            self._fonte_referencia = "janela"
            return float(ref)
        if self._n_visto == 0:
            self._fonte_referencia = "nenhuma"
            return None
        self._fonte_referencia = "max_sessao"
        return float(self._max_sessao)

    def iniciar_nova_sessao(self) -> None:
        """Virada de pregão — zera a referência de magnitude e o estágio.

        `criticas/nucleo_r3.md` §C.4 mediu a referência do dia 2 sendo a do
        dia 1 (o motor não tinha API para virar o dia): depois de um pregão de
        pânico o gate ficava fechado o dia inteiro; depois de um feriado
        morno, escancarado. A camada de app resolvia RECRIANDO o motor; com
        este método ela deixa de precisar, e quem usa o motor solto passa a
        ter como virar o dia.

        Zera o que é "do dia": cauda de magnitude (a da sessão E a janela
        móvel em blocos — a R5 §A.3.2 ataque D checou a primeira; a segunda
        entrou depois e é zerada aqui pelo mesmo motivo), janelas de dominância
        e micro, caches e a máquina de histerese. A config, não — ela é do
        usuário, não da sessão.
        """
        self._janela_dominancia.clear()
        self._maiores_qty.clear()
        self._vol_buy = self._vol_sell = self._vol_unknown = 0
        self._reservatorio = []
        self._n_visto = 0
        self._max_sessao = 0
        self._blocos.clear()
        self._resta_bloco = max(1, self.config.amostras_por_bloco_referencia)
        self._ref_janela = 0
        self._fonte_referencia = "nenhuma"
        self._cache_regiao = None
        self._cache_regiao_ts_ns = None
        self._cache_regiao_n = 0
        self._micro_antiga.clear()
        self._micro_recente.clear()
        self._delta_antiga = 0
        self._delta_recente = 0
        self._estagio_atual = EstagioSinal.NENHUM
        self._direcao_atual = None
        self._faixa_atual = FaixaConviccao.LATERAL
        self._candidato = None
        self._candidato_desde_ns = 0
        self._candidato_n = 0

    # ------------------------------------------------------------------
    # Condição 2 — região de interesse (VAL/VAH cacheados)
    # ------------------------------------------------------------------
    def _regiao(self, timestamp_ns: int) -> tuple[int, int] | None:
        """(VAL, VAH) do Volume Profile, com cache.

        Reconstrução funcional — a fonte não descreve a fórmula exata da
        ferramenta original (ver docstring do módulo).

        **Política de invalidação.** `value_area()` é O(n log n) nos níveis de
        preço da sessão e a versão anterior a chamava duas vezes por trade
        (uma por `val()`, outra por `vah()`), o que sozinho derrubava a barra
        a partir de ~120 níveis. Aqui ela é chamada UMA vez e o resultado vale
        até `cache_regiao_max_trades` trades OU `cache_regiao_max_ns` de tape
        decorridos — o que vier primeiro. Os dois critérios juntos porque um
        sozinho tem ponto cego: só por contagem, um tape lento seguraria o
        valor por minutos; só por tempo, um tape em rajada processaria dezenas
        de milhares de trades sem recalcular. Recalcular a cada tick compraria
        uma precisão que não existe: um trade move o volume de UM nível, e
        VAL/VAH só mudam quando a expansão gulosa em torno do POC troca de
        fronteira — o que exige volume acumulado, não um tick.

        Duas exceções deliberadas ao cache: perfil vazio (`None`) nunca é
        cacheado, para que um perfil que acabou de ser alimentado apareça no
        trade seguinte; e o cache é sempre recalculado na primeira chamada.
        """
        cfg = self.config
        precisa = (
            self._cache_regiao is None
            or self._cache_regiao_ts_ns is None
            or self._cache_regiao_n >= cfg.cache_regiao_max_trades
            or (timestamp_ns - self._cache_regiao_ts_ns) >= cfg.cache_regiao_max_ns
        )
        if precisa:
            self._cache_regiao = self._vp.value_area()
            self._cache_regiao_ts_ns = timestamp_ns
            self._cache_regiao_n = 0
        self._cache_regiao_n += 1
        return self._cache_regiao

    def _na_regiao(self, price: int, timestamp_ns: int) -> bool:
        area = self._regiao(timestamp_ns)
        if area is None:
            return False
        val, vah = area
        margem = self.config.margem_regiao_ticks
        return (val - margem) <= price <= (vah + margem)

    # ------------------------------------------------------------------
    # Condição 3 — micro em duas metades temporais (O(1) amortizado)
    # ------------------------------------------------------------------
    def _registrar_micro(self, trade: Trade) -> None:
        """Mantém a janela micro partida em duas metades por um corte TEMPORAL.

        A versão anterior fatiava `self._trades_micro[:len//2]` — por CONTAGEM
        de trades. Num tape em rajada, "a primeira metade dos trades" pode
        cobrir 9 dos 15 segundos da janela ou 0,2 deles, e comparar duas
        metades de durações diferentes não diz nada sobre fluxo. Aqui o corte
        é `agora - (1 - fração) * janela`: com fração 0.5 as duas metades têm
        exatamente a mesma duração, sempre.

        O corte só anda para frente (é função de `agora`), então cada trade
        migra de `_micro_recente` para `_micro_antiga` no máximo uma vez e é
        expirado no máximo uma vez — O(1) amortizado, sem refatiar lista nem
        re-somar delta.
        """
        cfg = self.config
        ts = trade.timestamp_ns
        reg = _TradeJanela(ts, trade.qty, trade.side_agressor)
        self._micro_recente.append(reg)
        self._delta_recente += _delta_de(reg)

        corte = ts - int(cfg.janela_micro_ns * (1.0 - cfg.pre_sinal_fracao_janela_micro))
        while self._micro_recente and self._micro_recente[0].timestamp_ns < corte:
            migrado = self._micro_recente.popleft()
            self._delta_recente -= _delta_de(migrado)
            self._micro_antiga.append(migrado)
            self._delta_antiga += _delta_de(migrado)

        limite = ts - cfg.janela_micro_ns
        while self._micro_antiga and self._micro_antiga[0].timestamp_ns < limite:
            antigo = self._micro_antiga.popleft()
            self._delta_antiga -= _delta_de(antigo)
        # Só ocorre com fração >= 1.0 (corte == agora): aí não há metade antiga
        # e a expiração precisa sair do próprio deque recente.
        while self._micro_recente and self._micro_recente[0].timestamp_ns < limite:
            antigo = self._micro_recente.popleft()
            self._delta_recente -= _delta_de(antigo)

    def _micro_virou(self, direcao: Side) -> tuple[bool, bool]:
        """Retorna (virou_completo, pre_sinal).

        `virou` — o delta da janela micro inteira cruzou para o sinal do alvo.

        `pre_sinal` — "o fluxo está virando na direção pretendida mas ainda
        não completou". Exige as três coisas ao mesmo tempo:
          1. as duas metades existem (sem as duas não há o que comparar);
          2. a primeira metade estava CONTRA o alvo;
          3. a segunda metade MELHOROU em relação à primeira, na direção do
             alvo (`delta_segunda > delta_primeira` para BUY, `<` para SELL).

        O item 3 é o conserto do rótulo falso: `delta_inicio` era calculado e
        usado só para decidir "estava contra", nunca comparado com a segunda
        metade. Com micro parada (−100 → −100) e com micro piorando 4x contra
        (−100 → −400) o motor emitia o mesmo `PRE_SINAL` que emitia com a
        micro melhorando (−100 → −20). Um mercado acelerando contra a posição
        recebia o mesmo farol amarelo de um mercado revertendo a favor.
        """
        if not self._micro_antiga and not self._micro_recente:
            return False, False

        delta_total = self._delta_antiga + self._delta_recente
        alvo_positivo = direcao is Side.BUY
        virou = (delta_total > 0) if alvo_positivo else (delta_total < 0)
        if virou:
            return True, False

        if not self._micro_antiga or not self._micro_recente:
            return False, False

        primeira = self._delta_antiga
        segunda = self._delta_recente
        estava_contra = (primeira <= 0) if alvo_positivo else (primeira >= 0)
        melhorou = (segunda > primeira) if alvo_positivo else (segunda < primeira)
        return False, (estava_contra and melhorou)

    # ------------------------------------------------------------------
    # Histerese
    # ------------------------------------------------------------------
    def _aplicar_persistencia(
        self, bruto: EstagioSinal, direcao_bruta: Side | None, timestamp_ns: int
    ) -> None:
        """Publica `bruto` só depois que ele se sustenta.

        Promoção (rank sobe) usa `persistencia_minima_*`; rebaixamento e troca
        de direção no mesmo posto usam `rebaixamento_minimo_*`. Trocar de lado
        sem cair de posto é pelo menos tão sério quanto cair de posto, então
        usa o limiar de saída, não o de entrada.

        Sem isto, a R2 mediu: `70 BUY + 30 SELL` → `CONFIRMADO`; **+1 único
        trade SELL** → `NENHUM`. O estágio não era um estado, era uma função
        pura do último trade.
        """
        cfg = self.config
        chave = (bruto, direcao_bruta)
        if chave != self._candidato:
            self._candidato = chave
            self._candidato_desde_ns = timestamp_ns
            self._candidato_n = 0
        self._candidato_n += 1

        if chave == (self._estagio_atual, self._direcao_atual):
            return

        promocao = _RANK[bruto] > _RANK[self._estagio_atual]
        if promocao:
            min_trades = cfg.persistencia_minima_trades
            min_ns = cfg.persistencia_minima_ns
        else:
            min_trades = cfg.rebaixamento_minimo_trades
            min_ns = cfg.rebaixamento_minimo_ns

        sustentou = (
            self._candidato_n >= min_trades
            and (timestamp_ns - self._candidato_desde_ns) >= min_ns
        )
        if sustentou:
            self._estagio_atual = bruto
            self._direcao_atual = direcao_bruta

    # ------------------------------------------------------------------
    def ao_trade(self, trade: Trade) -> Sinal:
        if trade.symbol != self._symbol:
            return Sinal(trade.timestamp_ns, self._symbol, EstagioSinal.NENHUM, None)

        ts = trade.timestamp_ns

        self._registrar_dominancia(trade)
        self._registrar_micro(trade)

        dominancia, direcao = self._dominancia()
        faixa = self._faixa(dominancia)
        self._faixa_atual = faixa

        magnitude = self._magnitude()
        self._amostrar_magnitude(magnitude)
        referencia = self._magnitude_referencia(ts)
        magnitude_relativa = (
            magnitude / referencia if referencia is not None and referencia > 0 else 1.0
        )

        evidencia: dict[str, object] = {
            "dominancia": dominancia,
            "faixa": faixa.value,
            "magnitude": magnitude,
            "magnitude_referencia": referencia,
            "magnitude_referencia_fonte": self._fonte_referencia,
            "magnitude_pico_sessao": self._max_sessao,
            "magnitude_relativa": magnitude_relativa,
            "volume_nao_atribuido": self._vol_unknown,
        }

        bruto, direcao_bruta = self._estagio_bruto(
            trade, direcao, faixa, magnitude_relativa, evidencia
        )
        evidencia["estagio_bruto"] = bruto.value
        self._aplicar_persistencia(bruto, direcao_bruta, ts)
        evidencia["persistencia_trades"] = self._candidato_n

        return Sinal(ts, self._symbol, self._estagio_atual, self._direcao_atual, evidencia)

    def _estagio_bruto(
        self,
        trade: Trade,
        direcao: Side | None,
        faixa: FaixaConviccao,
        magnitude_relativa: float,
        evidencia: dict[str, object],
    ) -> tuple[EstagioSinal, Side | None]:
        """Estágio que as condições sustentam NESTE trade, antes da histerese."""
        cfg = self.config
        direcional = faixa in (FaixaConviccao.DIRECIONAL, FaixaConviccao.MAXIMA_CONVICCAO)
        if direcao is None or not direcional:
            return EstagioSinal.NENHUM, None

        # Caso WINFUT: percentual alto sobre magnitude pequena não é direção do
        # dia — é o repique que "nunca se aproximou da magnitude dos picos"
        # anteriores. O gate roda ANTES de qualquer outra condição porque ele
        # invalida a condição 1, não as seguintes.
        if magnitude_relativa < cfg.magnitude_relativa_minima:
            evidencia["bloqueio"] = "magnitude_relativa"
            return EstagioSinal.NENHUM, None

        evidencia["direcao_dominante"] = direcao.value
        na_regiao = self._na_regiao(trade.price, trade.timestamp_ns)
        evidencia["na_regiao"] = na_regiao
        if not na_regiao:
            return EstagioSinal.DIRECAO_CONFIRMADA, direcao

        virou, pre_sinal = self._micro_virou(direcao)
        evidencia["micro_virou"] = virou
        evidencia["pre_sinal"] = pre_sinal
        evidencia["delta_micro_primeira_metade"] = self._delta_antiga
        evidencia["delta_micro_segunda_metade"] = self._delta_recente

        if virou:
            return EstagioSinal.CONFIRMADO, direcao
        if pre_sinal:
            return EstagioSinal.PRE_SINAL, direcao
        return EstagioSinal.NA_REGIAO, direcao

    # ------------------------------------------------------------------
    @property
    def estagio_atual(self) -> EstagioSinal:
        """Estágio PUBLICADO (pós-histerese)."""
        return self._estagio_atual

    @property
    def direcao_atual(self) -> Side | None:
        return self._direcao_atual

    @property
    def faixa_atual(self) -> FaixaConviccao:
        """Faixa de convicção da dominância no último trade — independe da
        histerese (é leitura instantânea do percentual, não estado)."""
        return self._faixa_atual
