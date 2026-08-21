"""Medidor de Agressão — pressão de compra/venda e velocidade do tape.

Conceito de leitura de fluxo: "agressão" é quem cruzou o spread e pegou o
preço do book (comprou no ask ou vendeu no bid), diferente de quem só ficou
ofertando. Uma janela deslizante de trades recentes (por tempo, por
quantidade de trades, ou ambos) mede:

- **Saldo de agressão**: volume comprador - volume vendedor na janela — o
  "termômetro" instantâneo equivalente ao Medidor de Pressão do Profit Pro.
- **Taxa de agressão**: fração do volume da janela que foi comprador vs.
  vendedor.
- **Velocidade do tape**: trades/segundo e contratos/segundo na janela —
  tape acelerando é sinal de interesse crescente, independente da direção.
- **Clip grande**: um trade cuja quantidade está acima de um percentil da
  distribuição recente de tamanhos — candidato a ordem institucional
  cortando o book. A distribuição é mantida por *reservoir sampling*
  (algoritmo R, com seed determinística) para não guardar o histórico
  inteiro de trades só para estimar um percentil.

Tudo incremental: a janela expira por tempo e/ou contagem a cada trade
(O(1) amortizado — cada trade entra e sai da janela deque exatamente uma
vez), e o reservoir sampling atualiza a amostra em O(1) por trade.

## Volume não atribuído (`AgressorSide.UNKNOWN`)

Trade com agressor desconhecido entrava na janela (`_janela.append`, conta
para velocidade/tape) mas não incrementava nenhum dos contadores de
compra/venda — o volume simplesmente não aparecia em `saldo_agressao` nem em
lugar nenhum que o operador pudesse ver. `_qty_nao_atribuida_janela` e
`_n_nao_atribuida_janela` fecham essa lacuna, expostos via
`volume_nao_atribuido` e `n_nao_atribuido`; `volume_total_janela` (soma dos
três baldes) é sempre igual à soma de `qty` de todo trade na janela.

## Ciclo de vida de sessão

A janela deslizante se autolimpa por tempo/contagem, mas o reservoir
sampling (`_reservatorio`/`_n_visto`) nunca resetava — a amostra usada para
estimar o percentil de "clip grande" ia se diluindo com trades de sessões
cada vez mais antigas, e nada garantia que a janela deslizante estivesse
vazia exatamente na virada (trades do fim da sessão anterior podem
continuar dentro do critério de tempo/contagem por mais alguns trades da
sessão nova). `iniciar_nova_sessao()` zera janela, os três baldes de volume
e o reservoir sampling — reset completo, sem herança da sessão anterior.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade


@dataclass(frozen=True, slots=True)
class ConfigAgressao:
    janela_ns: int | None = 5_000_000_000
    """Tamanho da janela deslizante em nanossegundos. `None` desativa o
    critério de tempo (janela só limitada por `janela_n_trades`)."""

    janela_n_trades: int | None = None
    """Tamanho da janela deslizante em número de trades. `None` desativa o
    critério de contagem. Se ambos estiverem ativos, o trade sai da janela
    assim que qualquer um dos dois critérios for violado."""

    percentil_clip_grande: float = 0.95
    """Percentil (0-1) da distribuição amostrada de quantidades acima do qual
    um trade é considerado clip grande."""

    tamanho_reservatorio: int = 500
    """Capacidade máxima da amostra de reservoir sampling."""

    seed_reservatorio: int = 42
    """Seed do gerador aleatório do reservoir sampling — determinística para
    que o mesmo replay produza sempre a mesma amostra."""


@dataclass(slots=True)
class _TradeJanela:
    timestamp_ns: int
    qty: int
    lado: AgressorSide


class MedidorAgressao:
    """Assina o `Barramento` e mede agressão/velocidade numa janela deslizante."""

    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        config: ConfigAgressao | None = None,
    ) -> None:
        self._symbol = symbol
        self.config = config or ConfigAgressao()

        self._janela: deque[_TradeJanela] = deque()
        self._qty_compra_janela = 0
        self._qty_venda_janela = 0
        self._qty_nao_atribuida_janela = 0
        self._n_compra_janela = 0
        self._n_venda_janela = 0
        self._n_nao_atribuida_janela = 0

        self._reservatorio: list[int] = []
        self._rng = random.Random(self.config.seed_reservatorio)
        self._n_visto = 0

        barramento.assinar(Trade, self._ao_trade)

    def _ao_trade(self, trade: Trade) -> None:
        if trade.symbol != self._symbol:
            return

        self._janela.append(
            _TradeJanela(trade.timestamp_ns, trade.qty, trade.side_agressor)
        )
        if trade.side_agressor is AgressorSide.BUY:
            self._qty_compra_janela += trade.qty
            self._n_compra_janela += 1
        elif trade.side_agressor is AgressorSide.SELL:
            self._qty_venda_janela += trade.qty
            self._n_venda_janela += 1
        else:
            self._qty_nao_atribuida_janela += trade.qty
            self._n_nao_atribuida_janela += 1

        self._expirar_janela(trade.timestamp_ns)
        self._atualizar_reservatorio(trade.qty)

    def _expirar_janela(self, agora_ns: int) -> None:
        janela_ns = self.config.janela_ns
        janela_n = self.config.janela_n_trades
        while self._janela:
            expira_por_tempo = (
                janela_ns is not None and agora_ns - self._janela[0].timestamp_ns > janela_ns
            )
            expira_por_contagem = janela_n is not None and len(self._janela) > janela_n
            if not (expira_por_tempo or expira_por_contagem):
                break
            antigo = self._janela.popleft()
            if antigo.lado is AgressorSide.BUY:
                self._qty_compra_janela -= antigo.qty
                self._n_compra_janela -= 1
            elif antigo.lado is AgressorSide.SELL:
                self._qty_venda_janela -= antigo.qty
                self._n_venda_janela -= 1
            else:
                self._qty_nao_atribuida_janela -= antigo.qty
                self._n_nao_atribuida_janela -= 1

    def _atualizar_reservatorio(self, qty: int) -> None:
        """Reservoir sampling (algoritmo R): mantém uma amostra uniforme de
        tamanho fixo sem guardar o fluxo inteiro de trades."""
        capacidade = self.config.tamanho_reservatorio
        if len(self._reservatorio) < capacidade:
            self._reservatorio.append(qty)
        else:
            indice_sorteado = self._rng.randint(0, self._n_visto)
            if indice_sorteado < capacidade:
                self._reservatorio[indice_sorteado] = qty
        self._n_visto += 1

    @property
    def saldo_agressao(self) -> int:
        return self._qty_compra_janela - self._qty_venda_janela

    @property
    def volume_nao_atribuido(self) -> int:
        """Qty na janela com `side_agressor is AgressorSide.UNKNOWN`."""
        return self._qty_nao_atribuida_janela

    @property
    def n_nao_atribuido(self) -> int:
        return self._n_nao_atribuida_janela

    @property
    def volume_total_janela(self) -> int:
        """Sempre igual a `qty_compra + qty_venda + volume_nao_atribuido` —
        nenhum trade da janela conta no total sem cair em algum dos três
        baldes."""
        return (
            self._qty_compra_janela
            + self._qty_venda_janela
            + self._qty_nao_atribuida_janela
        )

    @property
    def taxa_compra(self) -> float:
        total = self._qty_compra_janela + self._qty_venda_janela
        return self._qty_compra_janela / total if total else 0.0

    @property
    def taxa_venda(self) -> float:
        total = self._qty_compra_janela + self._qty_venda_janela
        return self._qty_venda_janela / total if total else 0.0

    def velocidade_trades_por_segundo(self) -> float:
        """Trades/s na janela. Precisa de >= 2 trades para estimar uma
        duração; com 0 ou 1 trade retorna 0.0 (janela recém-aberta)."""
        if len(self._janela) < 2:
            return 0.0
        duracao_s = (self._janela[-1].timestamp_ns - self._janela[0].timestamp_ns) / 1e9
        if duracao_s <= 0:
            return 0.0
        return len(self._janela) / duracao_s

    def velocidade_contratos_por_segundo(self) -> float:
        if len(self._janela) < 2:
            return 0.0
        duracao_s = (self._janela[-1].timestamp_ns - self._janela[0].timestamp_ns) / 1e9
        if duracao_s <= 0:
            return 0.0
        total_qty = sum(t.qty for t in self._janela)
        return total_qty / duracao_s

    def _percentil_amostra(self, p: float) -> float | None:
        """Percentil por interpolação linear entre ranks (mesmo método do
        default `numpy.percentile`), calculado sobre a amostra do reservoir."""
        if not self._reservatorio:
            return None
        dados = sorted(self._reservatorio)
        if len(dados) == 1:
            return float(dados[0])
        posicao = p * (len(dados) - 1)
        indice_baixo = int(posicao)
        indice_alto = min(indice_baixo + 1, len(dados) - 1)
        fracao = posicao - indice_baixo
        return dados[indice_baixo] + (dados[indice_alto] - dados[indice_baixo]) * fracao

    def limiar_clip_grande(self) -> float | None:
        return self._percentil_amostra(self.config.percentil_clip_grande)

    def is_clip_grande(self, qty: int) -> bool:
        limiar = self.limiar_clip_grande()
        if limiar is None:
            return False
        return qty >= limiar

    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Reset completo: esvazia a janela deslizante (com os três baldes
        de volume/contagem) e o reservoir sampling. Ver docstring do módulo
        para o porquê do reservoir também zerar (sem reset, a amostra usada
        para o percentil de clip grande se diluiria entre sessões, e a
        janela deslizante sozinha não garante estar vazia bem na virada)."""
        self._janela.clear()
        self._qty_compra_janela = 0
        self._qty_venda_janela = 0
        self._qty_nao_atribuida_janela = 0
        self._n_compra_janela = 0
        self._n_venda_janela = 0
        self._n_nao_atribuida_janela = 0
        self._reservatorio = []
        self._n_visto = 0
