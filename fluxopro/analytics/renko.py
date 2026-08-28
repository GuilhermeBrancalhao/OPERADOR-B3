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

    janela_amplitude_precos: int = 240
    """Quantos preços brutos recentes (não tijolos, negócios crus) entram no
    cálculo de amplitude usado pela recalibragem dinâmica."""

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
        self._precos_recentes: deque[int] = deque(
            maxlen=max(2, self._config.janela_amplitude_precos)
        )
        self._tijolos_desde_recalibragem = 0
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
        amplitude_ticks = max(self._precos_recentes) - min(self._precos_recentes)
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
        self._precos_recentes.append(preco)

        if self._ancora is None:
            self._ancora = preco
            self._recalibrar_tamanho()
            return

        # Aquecimento: enquanto nenhum tijolo fechou, o tamanho ainda e o valor
        # de partida cravado — que pode ser maior que a amplitude inteira da
        # sessao. Recalibra pelos precos crus para destravar o impasse (ver
        # `ConfigRenko.aquecimento_minimo_precos`).
        if (
            self._config.tijolo_dinamico
            and not self._tijolos
            and len(self._precos_recentes) >= self._config.aquecimento_minimo_precos
        ):
            self._precos_desde_aquecimento += 1
            if self._precos_desde_aquecimento >= self._config.aquecimento_a_cada_precos:
                self._precos_desde_aquecimento = 0
                self._recalibrar_tamanho()

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
            elif deslocamento <= -tam:
                novo_fechamento = self._ancora - tam
                self._tijolos.append(
                    TijoloRenko(timestamp_ns, self._ancora, novo_fechamento, -1)
                )
                self._ancora = novo_fechamento
                self._tijolos_desde_recalibragem += 1
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
