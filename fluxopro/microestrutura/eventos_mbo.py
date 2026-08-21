"""Tipos de microestrutura por ORDEM (MBO), separados do núcleo agregado.

O núcleo (`fluxopro.core.eventos`) modela o mercado por PREÇO: um `BookLevel`
diz "há 150 contratos a 5000.5", sem dizer de quantas ordens esses 150 vêm,
quem as colocou nem há quanto tempo estão lá. A leitura de fluxo que este
pacote serve precisa do nível abaixo: a ORDEM individual, sua posição na fila
e seu comportamento no tempo.

Duas realidades de dado convivem aqui, e o tipo carrega qual delas gerou o
evento:

* `FonteMicro.MBO` — feed ordem-a-ordem de verdade (UMDF/ProfitDLL). O evento
  é OBSERVADO: `confianca == 1.0`.
* `FonteMicro.MBP_INFERIDO` — feed agregado por preço (o DOM do MetaTrader5).
  O evento é INFERIDO por `inferencia_mbp.InferidorMBP` a partir da variação
  de quantidade do nível reconciliada com o fluxo de negócios. `confianca` é
  sempre `< 1.0` e `evidencia` diz em cima de quê a inferência foi feita.

Nada neste pacote pode apagar essa distinção: um evento inferido nunca deve
ser apresentado ao usuário como fato observado.

Preços seguem a convenção do núcleo: SEMPRE `int` de ticks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Side

# Confiança de um evento que veio de feed MBO real — não é estimativa, é leitura.
CONFIANCA_OBSERVADO = 1.0


@unique
class TipoEventoOrdem(Enum):
    """Ciclo de vida de uma ordem no livro."""

    NEW = "NEW"
    """Ordem entrou no livro."""

    REPLACE = "REPLACE"
    """Quantidade alterada. Redução mantém prioridade; aumento vai para o fim."""

    CANCEL = "CANCEL"
    """Ordem retirada pelo participante, sem execução do saldo."""

    TRADE = "TRADE"
    """Parte (ou todo) do saldo da ordem foi executado contra uma agressão."""

    EXPIRE = "EXPIRE"
    """Ordem saiu por regra do mercado (fim de sessão, validade), não por decisão."""


@unique
class FonteMicro(Enum):
    """De onde o evento de ordem veio — determina se é fato ou hipótese."""

    MBO = "MBO"
    """Feed ordem-a-ordem. Evento observado."""

    MBP_INFERIDO = "MBP_INFERIDO"
    """Feed agregado por preço. Evento reconstruído por inferência."""


@dataclass(slots=True)
class Ordem:
    """Uma ordem viva (ou já encerrada) no livro.

    Mutável de propósito: é a entidade que o `LivroMBO` atualiza no caminho
    quente. Quem publica estado para fora emite `OrdemEvento` (imutável).

    Campos de rastreio comportamental (o que a metodologia de fluxo lê):

    * `qty_executada` / `n_reducoes` — quanto foi consumido e em quantos golpes.
    * `n_recargas` — quantas vezes a ordem foi reabastecida mantendo o mesmo
      `order_id` (assinatura de iceberg em feed MBO real).
    * `eh_reposicao` — a ordem entrou logo após o mesmo preço ser varrido,
      isto é, é candidata a "escora" (defesa de preço).
    * `qty_a_frente_na_entrada` — volume que já estava na frente da fila quando
      esta ordem entrou; com o consumo acumulado do nível, dá a posição atual
      em O(1).
    """

    order_id: str
    side: Side
    price: int
    qty_original: int
    qty_restante: int
    timestamp_entrada_ns: int
    broker: str = ""
    position_na_fila: int = 0

    qty_executada: int = 0
    n_reducoes: int = 0
    n_recargas: int = 0
    qty_a_frente_na_entrada: int = 0
    consumido_nivel_na_entrada: int = 0
    eh_reposicao: bool = False
    ativa: bool = True
    timestamp_saida_ns: int | None = None

    def idade_ns(self, agora_ns: int) -> int:
        """Tempo que a ordem passou no livro até `agora_ns` (ou até sair)."""
        fim = self.timestamp_saida_ns if self.timestamp_saida_ns is not None else agora_ns
        return max(0, fim - self.timestamp_entrada_ns)


@dataclass(frozen=True, slots=True)
class OrdemEvento:
    """Evento imutável de ciclo de vida de ordem, publicado no barramento.

    `confianca` e `evidencia` NÃO são enfeite: em feed agregado todo evento
    aqui é hipótese, e o usuário precisa poder auditar por que o sistema
    decidiu que aquilo foi execução e não cancelamento.

    `evidencia` é um dicionário de primitivos (int/float/str/bool) para ser
    serializável e comparável em teste. O dataclass é `frozen`, mas o dict
    interno não é congelado pela linguagem — por convenção, ninguém muta
    `evidencia` depois de construída (e por isso `__hash__` não deve ser usado
    nestes eventos).
    """

    timestamp_ns: int
    symbol: str
    tipo: TipoEventoOrdem
    side: Side
    price: int
    qty: int
    order_id: str = ""
    qty_restante: int = 0
    broker: str = ""
    fonte: FonteMicro = FonteMicro.MBO
    confianca: float = CONFIANCA_OBSERVADO
    evidencia: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NivelDetalhado:
    """Fotografia de um nível de preço com a fila de ordens explícita.

    `ordens` vem na ordem de prioridade (frente da fila primeiro). Em feed
    agregado a fila é sintética: uma ordem por bloco de quantidade inferido, e
    a ordem real de prioridade é DESCONHECIDA — ver `inferencia_mbp`.
    """

    price: int
    side: Side
    ordens: tuple[Ordem, ...]
    qty_total: int
    n_ordens: int
