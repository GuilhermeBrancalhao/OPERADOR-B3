"""Configuração única do produto montado, e a ordem de entrega no barramento.

Até aqui cada peça tinha a sua `Config...` e ninguém tinha a de cima. Quem
quisesse operar precisava instanciar quinze objetos na ordem certa e conhecer
os quinze defaults. `ConfigOperacao` agrega todas — **por composição, não por
cópia**: cada campo guarda a dataclass original do módulo dono, de modo que um
default novo lá aparece aqui sem edição, e um valor calibrado aqui é
exatamente o mesmo objeto que o módulo recebe. Nenhum limiar é redigitado
neste arquivo.

## Ordem de entrega (prioridade no `Barramento`)

`Barramento.assinar(tipo, callback, prioridade)` entrega da menor prioridade
para a maior; empate resolve pela ordem de inscrição. A cadeia de dependência
real do pipeline é:

    fonte -> EstadoMercado -> analytics -> microestrutura -> motor -> saída

e as faixas abaixo a materializam. Duas dessas setas são **load-bearing** (se
inverterem, o resultado muda):

1. **perfil de sessão (analytics) antes do `MotorSinais`.** A condição 2 do
   motor ("o preço voltou à região") lê VAL/VAH do `VolumeProfile` que a
   montagem alimenta. Se o motor rodasse antes, o trade corrente não estaria
   no perfil e a região seria a de um trade atrás. Escolha declarada: **o
   perfil inclui o trade que está sendo avaliado** — é o que faz `_na_regiao`
   responder sobre o mercado de agora, e é determinístico nos dois sentidos,
   mas só um deles é o pretendido.
2. **`InferidorMBP` antes dos detectores de livro.** O inferidor é quem
   traduz book agregado em `OrdemEvento` e alimenta o `LivroMBO`; os
   detectores de escora/iceberg/liquidez fantasma leem esse livro. Rodar
   antes do inferidor os faria ler o livro do evento anterior.

A terceira seta — `EstadoMercado` antes dos analytics — **hoje não é
load-bearing** e vale dizer em vez de fingir: nenhum módulo de analytics lê
`EstadoMercado`; todos acumulam direto do `Trade`. A ordem está fixada mesmo
assim porque a saída e qualquer UI futura leem `EstadoMercado` como "o estado
do mercado neste instante", e um consumidor que rodasse antes dele leria
estado defasado.

## LIMITAÇÃO REAL do barramento, encontrada nesta montagem

O `Barramento` **expressa** prioridade, mas os componentes do núcleo e dos
analytics **assinam a si mesmos no construtor, sem parâmetro de prioridade**
(`EstadoMercado.__init__`, `VolumeProfilePorPeriodo.__init__`,
`FootprintPorTimeframe`, `CumulativeDelta`, `MedidorAgressao`, `VWAP`,
`RankingCorretoras` — todos chamam `barramento.assinar(Trade, ...)` com o
default `prioridade=0`). Consequência: **a montagem não consegue atribuir
prioridade a essas peças**; todas caem na faixa 0 e a única alavanca que
sobra é a *ordem de construção* (o desempate por ordem de inscrição).

Isso é frágil por dois motivos: (a) o invariante fica implícito numa sequência
de linhas de um construtor, não num número declarado; (b) qualquer peça que
passe a assinar um segundo tipo depois cai no fim da faixa sem aviso.

Duas mitigações aplicadas aqui, em vez de reportar e seguir:
- tudo que **esta camada** assina usa prioridade explícita (`PRIORIDADE_*`
  abaixo), então motor, microestrutura e saída são imunes à ordem de
  construção;
- `tests/test_app_montagem.py::test_ordem_de_entrega_no_barramento` prende a
  ordem observada com uma sonda, de modo que reordenar o construtor por
  descuido quebra um teste em vez de mudar o resultado em silêncio.

O conserto de raiz (aceitar `prioridade` nos construtores do núcleo/analytics)
não foi feito aqui de propósito: mexe em sete arquivos compartilhados que
estão sob revisão adversarial em paralelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.analytics.agressao import ConfigAgressao
from fluxopro.analytics.brokers import ConfigRankingCorretoras
from fluxopro.analytics.delta import ConfigDelta
from fluxopro.analytics.footprint import ConfigFootprint
from fluxopro.analytics.volume_profile import ConfigVolumeProfile
from fluxopro.analytics.vwap import ConfigVWAP
from fluxopro.core.eventos import WDO_GRID, WIN_GRID, PriceGrid
from fluxopro.microestrutura.detectores import (
    ConfigAbsorcao,
    ConfigClipInstitucional,
    ConfigEscora,
    ConfigExaustao,
    ConfigIceberg,
    ConfigLiquidezFantasma,
)
from fluxopro.microestrutura.inferencia_mbp import ConfigInferenciaMBP
from fluxopro.microestrutura.livro_mbo import ConfigLivroMBO
from fluxopro.motor.sinais import ConfigMotorSinais

NS_POR_SEGUNDO = 1_000_000_000
NS_POR_MINUTO = 60 * NS_POR_SEGUNDO
NS_POR_HORA = 60 * NS_POR_MINUTO
NS_POR_DIA = 24 * NS_POR_HORA

# --- faixas de prioridade do barramento (menor entrega primeiro) -----------
# Faixa 0 é ocupada pelos componentes que assinam a si mesmos sem prioridade
# (ver "LIMITAÇÃO REAL" na docstring do módulo). As faixas abaixo são as que
# esta camada controla de fato.
PRIORIDADE_ESTADO = 0
"""`EstadoMercado` — reservada, mas hoje imposta por ordem de construção."""

PRIORIDADE_ANALYTICS = 0
"""Os 6 módulos de analytics — idem."""

PRIORIDADE_PERFIL_SESSAO = 25
"""O `VolumeProfile` de sessão que o `MotorSinais` lê. Explícita: precisa
estar atualizada ANTES do motor, e essa é a seta que não pode inverter."""

PRIORIDADE_MICRO = 30
"""`InferidorMBP` (que alimenta o `LivroMBO`), detectores de tape e
`PerfilPlayer`."""

PRIORIDADE_MOTOR = 40
"""`MotorSinais` — depois de todo estado de que ele depende."""

PRIORIDADE_SAIDA = 50
"""Contadores e consumidor de saída — leem o mundo já atualizado."""


@unique
class FonteDados(Enum):
    """De onde vem o tape. `SIMULADOR` roda sem MT5 e sem corretora."""

    SIMULADOR = "simulador"
    REPLAY = "replay"
    MT5 = "mt5"


def grid_para_simbolo(symbol: str) -> PriceGrid:
    """WIN* -> `WIN_GRID`; o resto assume WDO. Mesma regra de `scripts/gravar.py`."""
    return WIN_GRID if symbol[:3].upper() == "WIN" else WDO_GRID


@dataclass(frozen=True, slots=True)
class ConfigSimulador:
    """Parâmetros do `SimuladorWDO` que a montagem precisa expor.

    Existe porque `SimuladorWDO` recebe tudo por argumento solto e não tem
    dataclass de config própria — sem isto, calibrar o simulador exigiria
    editar código, que é justamente o que `ConfigOperacao` promete evitar.
    """

    seed: int = 42
    volatilidade: float = 1.0
    taxa_eventos_s: float = 5.0
    preco_inicial: float = 5000.0
    n_eventos: int = 1000


@dataclass(frozen=True, slots=True)
class ConfigOperacao:
    """Tudo o que o produto precisa para rodar, num objeto só.

    Todos os defaults são os das próprias peças (nenhum número redigitado).
    Sobrescrever é `dataclasses.replace(cfg, motor=ConfigMotorSinais(...))` ou
    passar o campo no construtor — o usuário final calibra sem tocar em código.

    Os quatro `ligar_*` não são hooks de teste: são a chave de custo do
    pipeline (microestrutura é o estágio mais caro; quem só quer footprint e
    VWAP desliga o resto). Eles também tornam cada elo do wiring **verificável
    por ausência** — ver `tests/test_app_pipeline.py`.
    """

    symbol: str = "WDOFUT"
    fonte: FonteDados = FonteDados.SIMULADOR
    grid: PriceGrid | None = None
    """`None` = deriva do símbolo por `grid_para_simbolo`."""

    timeframe_ns: int = NS_POR_MINUTO
    """Bucket de candle do `EstadoMercado`, do footprint e do delta por candle."""

    periodo_volume_profile_ns: int = NS_POR_HORA
    """Bucket do `VolumeProfilePorPeriodo`. NÃO é o perfil que o motor lê —
    esse é o de sessão, que a montagem mantém à parte."""

    janela_periodo_player_ns: int = NS_POR_HORA
    """Janela de "período" do `PerfilPlayer` (persistência de um broker)."""

    # --- configs das peças, por composição ---
    volume_profile: ConfigVolumeProfile = field(default_factory=ConfigVolumeProfile)
    footprint: ConfigFootprint = field(default_factory=ConfigFootprint)
    delta: ConfigDelta = field(default_factory=ConfigDelta)
    agressao: ConfigAgressao = field(default_factory=ConfigAgressao)
    vwap: ConfigVWAP = field(default_factory=ConfigVWAP)
    brokers: ConfigRankingCorretoras = field(default_factory=ConfigRankingCorretoras)

    livro: ConfigLivroMBO = field(default_factory=ConfigLivroMBO)
    inferencia: ConfigInferenciaMBP = field(default_factory=ConfigInferenciaMBP)

    absorcao: ConfigAbsorcao = field(default_factory=ConfigAbsorcao)
    escora: ConfigEscora = field(default_factory=ConfigEscora)
    iceberg: ConfigIceberg = field(default_factory=ConfigIceberg)
    liquidez_fantasma: ConfigLiquidezFantasma = field(
        default_factory=ConfigLiquidezFantasma
    )
    exaustao: ConfigExaustao = field(default_factory=ConfigExaustao)
    clip_institucional: ConfigClipInstitucional = field(
        default_factory=ConfigClipInstitucional
    )

    motor: ConfigMotorSinais = field(default_factory=ConfigMotorSinais)
    simulador: ConfigSimulador = field(default_factory=ConfigSimulador)

    # --- estágios ligáveis ---
    ligar_analytics: bool = True
    ligar_microestrutura: bool = True
    ligar_detectores_tape: bool = True
    ligar_motor: bool = True

    emitir_apenas_mudanca_de_estagio: bool = True
    """Se `True`, um `Sinal` só sai quando (estágio, direção) MUDA. `False`
    entrega um sinal por trade — a 5.000 trades/s isso é ruído puro no console,
    mas é o que uma UI que desenha o estado corrente quer."""

    def price_grid(self) -> PriceGrid:
        return self.grid if self.grid is not None else grid_para_simbolo(self.symbol)
