"""Renko: blocos por deslocamento de preço, nunca por tempo.

Fonte: `pesquisa/ferramenta_componentes.md` §6.1, extraído de `ijsZl8EzeH8.txt`
e `w8YGyNl5m24.txt` ("ASG | Gráfico Renko: Aprenda os Gatilhos de Entrada que
Funcionam no Day Trade"). Rótulos de confiança por regra, no mesmo padrão de
`fluxopro/metodologia/regras.py`:

- **CONFIRMADO** — cada lado do dia projeta até três alvos (A1/A2/A3). A
  região do alvo NEGATIVO (abaixo do preço) é estatisticamente a melhor para
  pensar em COMPRA de contratendência; a região do alvo POSITIVO (acima) é a
  melhor para VENDA de contratendência. Regra de disciplina do autor: nunca
  comprar no alvo positivo, nunca vender no negativo — são os "piores preços"
  para entrar a favor do movimento (risco alto de falso rompimento).
- **CONFIRMADO** — existe uma "cor interna" (segundo estado, sobreposto):
  verde quando a tendência está sustentada, cinza quando perde força/tende a
  lateralizar, vermelho quando há possível inversão de fase. Funciona como
  alerta antecipado ("pode antecipar algo que a micro ainda não confirmou").
- **IMPRECISO** — o tamanho do tijolo. A fonte nunca fixa um número; `4`
  pontos vem do operador deste projeto, não do autor do método, e desde
  28/08/2026 vale só como semente até a primeira calibragem dinâmica: o
  próprio operador constatou que 4 pontos fixos não representam a micro.
  A calibragem é uma fração da amplitude recente, com piso de **1 tick** do
  papel (`ConfigRenko.tijolo_minimo_ticks`) — piso em pontos é armadilha,
  porque muda de significado a cada instrumento.
- **AUSENTE NA FONTE, INFERIDO como replicável** — a fórmula exata de
  "amplitude média da frequência do dia" que ancora os alvos A1/A2/A3 nunca é
  revelada. Aqui a amplitude usa o alcance (high-low) dos últimos
  `janela_amplitude_tijolos` tijolos como proxy — rotulado como proxy, nunca
  apresentado como a fórmula do autor.
- **IMPRECISO** — o limiar exato de tijolos-na-mesma-direção que separa
  "tendência sustentada" de "perdendo força" também não tem número na fonte;
  `tijolos_para_tendencia` é um parâmetro configurável, não uma constante
  cravada.

Preço é sempre `int` em ticks. `tamanho_tijolo_pontos` é convertido para
ticks via o `PriceGrid` do símbolo em execução — nunca cravado por
instrumento. Retenção limitada por `maxlen_tijolos` (mesmo critério de
`fluxopro/gravacao/gravador.py`): a lista de tijolos fechados não cresce sem
teto ao longo do pregão.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from fluxopro.core.eventos import PriceGrid

__all__ = [
    "AlvosRenko",
    "ConfigRenko",
    "FaseRenko",
    "Renko",
    "TijoloRenko",
]


@dataclass(frozen=True, slots=True)
class TijoloRenko:
    """Um bloco fechado: abertura, fechamento e direção. Preço em ticks."""

    timestamp_ns: int
    abertura: int
    fechamento: int
    direcao: int  # +1 (alta) ou -1 (baixa); nunca 0 — um tijolo sempre desloca


class FaseRenko(Enum):
    """"Cor interna" do Renko — ver docstring do módulo."""

    TENDENCIA = "tendencia"  # verde: sustentada
    PERDENDO_FORCA = "perdendo_forca"  # cinza: possível lateralização
    POSSIVEL_INVERSAO = "possivel_inversao"  # vermelho: inversão de fase
    INDEFINIDA = "indefinida"  # sem tijolos suficientes para classificar


@dataclass(frozen=True, slots=True)
class AlvosRenko:
    """Alvos A1/A2/A3 de cada lado, em ticks absolutos (não deltas)."""

    positivos: tuple[int, int, int]
    negativos: tuple[int, int, int]

    def pior_preco_para_venda(self) -> int:
        """A1 positivo — o autor: nunca vender aqui, é o pior preço a favor."""

        return self.positivos[0]

    def pior_preco_para_compra(self) -> int:
        """A1 negativo — o autor: nunca comprar aqui, é o pior preço a favor."""

        return self.negativos[0]


@dataclass(frozen=True, slots=True)
class ConfigRenko:
    tamanho_tijolo_pontos: float = 4.0
    """IMPRECISO — não vem da fonte, é o parâmetro pedido pelo operador.
    Com `tijolo_dinamico=True` (padrão) isto vira só o tamanho inicial, antes
    da primeira recalibragem — ver `tijolo_dinamico`."""

    tijolo_dinamico: bool = True
    """26/08/2026, achado do operador: tijolo fixo em 4 pontos ficava
    "totalmente distorcido" — desproporcional ao candle abaixo, porque o
    candle se auto-ajusta à amplitude do dia (`nexo/candles.py`) e o Renko
    não. Com True, o tamanho do tijolo é recalibrado periodicamente (ver
    `recalibrar_a_cada_tijolos`) como uma fração da amplitude recente
    observada — nunca comparado ao candle diretamente, só à própria
    volatilidade recente do papel. Com False, mantém o comportamento antigo
    (tamanho fixo o pregão inteiro)."""

    fracao_da_amplitude_recente: float = 0.12
    """IMPRECISO — proxy de engenharia, não há número da fonte para "quanto
    da amplitude recente vira um tijolo". Fração do range (máx-mín) dos
    últimos `janela_amplitude_precos` preços observados."""

    tijolo_minimo_ticks: int = 1
    """IMPRECISO — piso do tijolo dinâmico, em TICKS do próprio instrumento,
    nunca em pontos.

    Achado do operador (28/08/2026): o piso antigo era `2.0` PONTOS, o que no
    WDO (tick de 0,5) equivale a 4 ticks. Numa janela real de pregão em que o
    papel andou 2,5 pontos no total, 4 ticks é maior que o dia inteiro — a
    região ficava LITERALMENTE vazia. O piso natural de um Renko é o passo da
    grade de preços do papel (1 tick); abaixo disso não existe deslocamento
    representável, e acima disso o piso deixa de ser um piso e vira uma
    calibragem cravada por instrumento — o que o `tijolo_dinamico` existe
    justamente para evitar."""

    tijolo_maximo_pontos: float = 20.0
    """Teto, para o tijolo dinâmico não inflar a um bloco único cobrindo o dia."""

    janela_amplitude_precos: int = 20000
    """TETO DE MEMÓRIA da janela de amplitude, não o seu tamanho útil — quem
    manda no recorte é `janela_amplitude_s`. Só existe para o deque não
    crescer sem limite num pregão inteiro.

    Era 240 até 01/09/2026, e aí ERA o recorte útil. Medido na gravação de
    31/08: 240 negócios cobrem 66 SEGUNDOS de pregão (mediana) e amplitude de
    5 ticks; a 12% disso o tijolo dava `round(0,6) = 1` tick e ficava PRESO no
    piso o pregão inteiro (7.303 tijolos no dia, num dia cuja amplitude total
    foi de 48 ticks). Contar NEGÓCIOS faz a janela encolher no tempo justo
    quando o mercado acelera — exatamente quando ela precisava ser larga."""

    janela_amplitude_s: float = 1200.0
    """Recorte de TEMPO da amplitude que dimensiona o tijolo: 20 minutos.

    Vem da referência do operador (01/09/2026): "foram 4 candles de 5m, olha a
    quantidade de renko". 4 x 5min = 20min é o período que ele quer enxergar
    de uma vez, então é essa a amplitude que tem de caber na região — o tijolo
    é dimensionado pela MESMA janela que o olho dele percorre, e não por um
    punhado de negócios dos últimos segundos.

    Medido na mesma gravação: o range de 20 minutos é de 2 ticks na mediana e
    26 no p90, o que a 12% dá tijolo de 1 tick nas fases paradas e 3 ticks nas
    ativas — e é a 3 ticks que ~80-100 tijolos cobrem os 20 minutos, em vez
    dos ~7 minutos que a janela de 240 negócios entregava."""

    recalibrar_a_cada_tijolos: int = 5
    """Recalibra o tamanho do tijolo a cada N tijolos FECHADOS, nunca a cada
    negócio — mudar o tamanho no meio de uma sequência quebraria a leitura
    visual da fase (`FaseRenko`) no meio do movimento."""

    aquecimento_minimo_precos: int = 24
    """Quantos preços crus precisam ter chegado antes da PRIMEIRA calibragem
    dinâmica, a que acontece ANTES de existir qualquer tijolo.

    Defeito corrigido em 28/08/2026 (impasse de partida): a recalibragem só
    rodava depois que um tijolo FECHAVA, mas o tamanho de partida
    (`tamanho_tijolo_pontos`, valor cravado pelo operador) podia ser maior que
    toda a amplitude da sessão — e aí nenhum tijolo fechava nunca, logo a
    recalibragem nunca rodava. Impasse: o dimensionamento dinâmico dependia do
    resultado que ele mesmo deveria destravar. Enquanto nenhum tijolo tiver
    fechado, o tamanho é recalibrado a cada `aquecimento_a_cada_precos` preços
    observados; assim que o primeiro tijolo fecha, o aquecimento acaba e volta
    a valer só a recalibragem por tijolos fechados."""

    aquecimento_a_cada_precos: int = 8

    precos_sem_tijolo_para_destravar: int = 200
    """Quantos preços podem chegar SEM nenhum tijolo fechar antes de a
    recalibragem de destrave voltar a rodar (achado de 01/09/2026).

    O impasse de partida documentado em `aquecimento_minimo_precos` REAPARECE
    depois do primeiro tijolo: se o regime aperta e o tijolo vigente fica maior
    que a amplitude nova, nada fecha, logo a recalibragem por fechamento nunca
    roda, logo o tijolo nunca encolhe. Este contador separa os dois casos que
    de fora parecem o mesmo — MOVIMENTO em curso (tijolos fechando, tamanho
    intocado, que é o que `test_aquecimento_para_assim_que_o_primeiro_tijolo_fecha`
    protege) e REGIÃO TRAVADA (nada fechando há muito tempo). Só no segundo o
    destrave age, e só para encolher."""

    tijolos_para_tendencia: int = 3
    """IMPRECISO — limiar de tijolos seguidos na mesma direção para FaseRenko.TENDENCIA."""

    janela_amplitude_tijolos: int = 20
    """Quantos tijolos fechados entram no cálculo de amplitude (proxy dos alvos)."""

    maxlen_tijolos: int = 300
    """Teto de retenção — ~1200 pontos de deslocamento a 4pts/tijolo, generoso p/ 1 pregão."""


def _tamanho_tijolo_ticks(grid: PriceGrid, config: ConfigRenko) -> int:
    ticks = round(config.tamanho_tijolo_pontos / grid.tick_size)
    return max(1, ticks)


class Renko:
    """Agregador puro — alimentado por chamada direta, nunca por barramento.

    Painéis de UI nunca assinam o barramento (invariante do projeto); esta
    classe existe justamente para poder viver dentro de um painel, alimentada
    pelos mesmos negócios já entregues via snapshot/retrato.
    """

    def __init__(self, grid: PriceGrid, config: ConfigRenko | None = None) -> None:
        self._grid = grid
        self._config = config or ConfigRenko()
        self._tamanho_ticks = _tamanho_tijolo_ticks(grid, self._config)
        self._tijolos: deque[TijoloRenko] = deque(maxlen=self._config.maxlen_tijolos)
        self._ancora: int | None = None  # fechamento do último tijolo fechado
        self._ultimo_timestamp_ns = 0
        # (timestamp_ns, preco): o recorte util e por TEMPO
        # (`janela_amplitude_s`); o `maxlen` abaixo e so teto de memoria.
        self._precos_recentes: deque[tuple[int, int]] = deque(
            maxlen=max(2, self._config.janela_amplitude_precos)
        )
        self._tijolos_desde_recalibragem = 0
        self._precos_desde_ultimo_tijolo = 0
        # Comeca "vencido" para que a primeira calibragem de aquecimento role
        # no exato preco em que o minimo de amostras e atingido.
        self._precos_desde_aquecimento = max(1, self._config.aquecimento_a_cada_precos)

    @property
    def tamanho_tijolo_ticks(self) -> int:
        return self._tamanho_ticks

    def _recalibrar_tamanho(self) -> None:
        """Ajusta `_tamanho_ticks` a partir da amplitude recente observada.

        Nunca roda no meio de uma sequência de tijolos abertos — só é chamada
        depois que um tijolo fecha, e só a cada `recalibrar_a_cada_tijolos`
        fechamentos (ver docstring de `ConfigRenko.recalibrar_a_cada_tijolos`).
        """

        if not self._config.tijolo_dinamico or len(self._precos_recentes) < 2:
            return
        precos = [p for _t, p in self._precos_recentes]
        amplitude_ticks = max(precos) - min(precos)
        if amplitude_ticks <= 0:
            return
        # Toda a conta e feita em TICKS: o piso do tijolo e o passo da grade do
        # papel, nao um numero de pontos cravado que muda de significado de um
        # instrumento para o outro (ver `ConfigRenko.tijolo_minimo_ticks`).
        piso = max(1, self._config.tijolo_minimo_ticks)
        teto = max(piso, round(self._config.tijolo_maximo_pontos / self._grid.tick_size))
        alvo = round(amplitude_ticks * self._config.fracao_da_amplitude_recente)
        self._tamanho_ticks = max(piso, min(teto, alvo))

    def registrar(self, timestamp_ns: int, preco: int) -> None:
        """Alimenta um novo preço observado. Preço em ticks inteiros."""

        if timestamp_ns < self._ultimo_timestamp_ns:
            return
        self._ultimo_timestamp_ns = timestamp_ns
        self._precos_recentes.append((timestamp_ns, preco))
        # Eviccao por TEMPO, nao por contagem: a janela tem de valer os mesmos
        # `janela_amplitude_s` tanto no mercado parado quanto no acelerado.
        corte = timestamp_ns - int(self._config.janela_amplitude_s * 1e9)
        while len(self._precos_recentes) > 2 and self._precos_recentes[0][0] < corte:
            self._precos_recentes.popleft()

        if self._ancora is None:
            self._ancora = preco
            self._recalibrar_tamanho()
            return

        # Aquecimento: enquanto nenhum tijolo fechou, o tamanho ainda e o valor
        # de partida cravado — que pode ser maior que a amplitude inteira da
        # sessao. Recalibra pelos precos crus para destravar o impasse (ver
        # `ConfigRenko.aquecimento_minimo_precos`).
        # O MESMO impasse volta DEPOIS do primeiro tijolo (achado de
        # 01/09/2026, por teste): se o regime aperta e o tijolo vigente fica
        # maior que a amplitude nova, nenhum tijolo fecha, logo a recalibragem
        # por fechamento nunca roda, logo o tijolo nunca encolhe. O gate antigo
        # era `not self._tijolos` e so cobria a PARTIDA.
        #
        # Aqui a recalibragem de destrave so pode ENCOLHER o tijolo: crescer no
        # meio de uma sequencia aberta e o que a docstring de
        # `_recalibrar_tamanho` proibe, e nao e necessario para destravar.
        self._precos_desde_ultimo_tijolo += 1
        travado = (
            self._precos_desde_ultimo_tijolo
            >= self._config.precos_sem_tijolo_para_destravar
        )
        if (
            self._config.tijolo_dinamico
            and (not self._tijolos or travado)
            and len(self._precos_recentes) >= self._config.aquecimento_minimo_precos
        ):
            self._precos_desde_aquecimento += 1
            if self._precos_desde_aquecimento >= self._config.aquecimento_a_cada_precos:
                self._precos_desde_aquecimento = 0
                if not self._tijolos:
                    self._recalibrar_tamanho()
                else:
                    anterior = self._tamanho_ticks
                    self._recalibrar_tamanho()
                    self._tamanho_ticks = min(anterior, self._tamanho_ticks)

        tam = self._tamanho_ticks
        while True:
            deslocamento = preco - self._ancora
            if deslocamento >= tam:
                novo_fechamento = self._ancora + tam
                self._tijolos.append(
                    TijoloRenko(timestamp_ns, self._ancora, novo_fechamento, +1)
                )
                self._ancora = novo_fechamento
                self._tijolos_desde_recalibragem += 1
                self._precos_desde_ultimo_tijolo = 0
            elif deslocamento <= -tam:
                novo_fechamento = self._ancora - tam
                self._tijolos.append(
                    TijoloRenko(timestamp_ns, self._ancora, novo_fechamento, -1)
                )
                self._ancora = novo_fechamento
                self._tijolos_desde_recalibragem += 1
                self._precos_desde_ultimo_tijolo = 0
            else:
                break
            if self._tijolos_desde_recalibragem >= self._config.recalibrar_a_cada_tijolos:
                self._tijolos_desde_recalibragem = 0
                tam_anterior = tam
                self._recalibrar_tamanho()
                tam = self._tamanho_ticks
                if tam != tam_anterior:
                    # tamanho mudou no fechamento do ultimo tijolo — o loop
                    # continua com o NOVO tamanho para o deslocamento restante,
                    # nunca reabre ou redimensiona tijolos ja fechados.
                    continue

    @property
    def tijolos(self) -> tuple[TijoloRenko, ...]:
        return tuple(self._tijolos)

    @property
    def fase(self) -> FaseRenko:
        """Classificação qualitativa (verde/cinza/vermelho) — ver docstring do módulo.

        Regra implementada (IMPRECISA, sem número revelado na fonte):
        - `tijolos_para_tendencia` ou mais seguidos na MESMA direção -> TENDENCIA.
        - o último tijolo inverte a direção da sequência anterior (>=2 tijolos
          na direção anterior) -> POSSIVEL_INVERSAO.
        - qualquer outra alternância -> PERDENDO_FORCA.
        """

        tijolos = self._tijolos
        if len(tijolos) < 2:
            return FaseRenko.INDEFINIDA

        direcao_atual = tijolos[-1].direcao
        seguidos = 1
        for tijolo in reversed(list(tijolos)[:-1]):
            if tijolo.direcao != direcao_atual:
                break
            seguidos += 1

        if seguidos >= self._config.tijolos_para_tendencia:
            return FaseRenko.TENDENCIA

        anterior = tijolos[-2].direcao
        if seguidos == 1 and anterior != direcao_atual:
            # a direção anterior já vinha de uma sequência (>=2)?
            if len(tijolos) >= 3 and tijolos[-3].direcao == anterior:
                return FaseRenko.POSSIVEL_INVERSAO

        return FaseRenko.PERDENDO_FORCA

    def alvos(self) -> AlvosRenko | None:
        """A1/A2/A3 de cada lado, ancorados no fechamento do último tijolo.

        Amplitude = alcance (max-min de fechamentos) dos últimos
        `janela_amplitude_tijolos` tijolos — proxy de "amplitude média da
        frequência do dia" (fórmula exata AUSENTE NA FONTE). `None` enquanto
        não há tijolo fechado nenhum.
        """

        if not self._tijolos:
            return None

        janela = list(self._tijolos)[-self._config.janela_amplitude_tijolos :]
        fechamentos = [t.fechamento for t in janela]
        amplitude = max(1, max(fechamentos) - min(fechamentos))
        ancora = self._tijolos[-1].fechamento

        passo = max(1, round(amplitude / 3))
        positivos = (ancora + passo, ancora + passo * 2, ancora + passo * 3)
        negativos = (ancora - passo, ancora - passo * 2, ancora - passo * 3)
        return AlvosRenko(positivos=positivos, negativos=negativos)
