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
  pontos vem do operador deste projeto, não do autor do método.
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
    """IMPRECISO — não vem da fonte, é o parâmetro pedido pelo operador."""

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

    @property
    def tamanho_tijolo_ticks(self) -> int:
        return self._tamanho_ticks

    def registrar(self, timestamp_ns: int, preco: int) -> None:
        """Alimenta um novo preço observado. Preço em ticks inteiros."""

        if timestamp_ns < self._ultimo_timestamp_ns:
            return
        self._ultimo_timestamp_ns = timestamp_ns

        if self._ancora is None:
            self._ancora = preco
            return

        tam = self._tamanho_ticks
        while True:
            deslocamento = preco - self._ancora
            if deslocamento >= tam:
                novo_fechamento = self._ancora + tam
                self._tijolos.append(
                    TijoloRenko(timestamp_ns, self._ancora, novo_fechamento, +1)
                )
                self._ancora = novo_fechamento
                continue
            if deslocamento <= -tam:
                novo_fechamento = self._ancora - tam
                self._tijolos.append(
                    TijoloRenko(timestamp_ns, self._ancora, novo_fechamento, -1)
                )
                self._ancora = novo_fechamento
                continue
            break

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
