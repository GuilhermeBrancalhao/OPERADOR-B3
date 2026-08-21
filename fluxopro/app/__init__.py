"""Camada de aplicação — onde as peças viram produto.

`fluxopro.core`, `fluxopro.analytics`, `fluxopro.microestrutura` e
`fluxopro.motor` são bibliotecas: cada uma resolve um pedaço e nenhuma sabe da
existência das outras. Este pacote é o único lugar que sabe de todas, e é o
que faltava — `criticas/nucleo_r2.md:371` registrou que `MotorSinais` e
`InferidorMBP` não eram importados por nenhum módulo de produção.

Três arquivos, três responsabilidades:

* `config.py` — `ConfigOperacao`, a configuração única, e as prioridades de
  entrega no barramento (com a justificativa da ordem e a limitação
  encontrada).
* `sessao_fluxo.py` — `SessaoFluxo`: instancia e liga tudo, mantém os
  contadores por elo, faz a virada de sessão.
* `montagem.py` — `montar()`: escolhe a fonte de dados e devolve o pipeline
  pronto.
* `saida.py` — `ConsoleFluxo`: a saída em texto, com a evidência visível.

O CLI que usa isto é `scripts/operar.py`.
"""

from __future__ import annotations

from fluxopro.app.config import (
    PRIORIDADE_ANALYTICS,
    PRIORIDADE_ESTADO,
    PRIORIDADE_MICRO,
    PRIORIDADE_MOTOR,
    PRIORIDADE_PERFIL_SESSAO,
    PRIORIDADE_SAIDA,
    ConfigOperacao,
    ConfigSimulador,
    FonteDados,
    grid_para_simbolo,
)
from fluxopro.app.montagem import (
    FonteIndisponivelError,
    Montagem,
    OpcoesReplay,
    criar_fonte,
    montar,
)
from fluxopro.app.saida import ConsoleFluxo
from fluxopro.app.sessao_fluxo import Contadores, DeteccaoAnotada, SessaoFluxo

__all__ = [
    "ConfigOperacao",
    "ConfigSimulador",
    "ConsoleFluxo",
    "Contadores",
    "DeteccaoAnotada",
    "FonteDados",
    "FonteIndisponivelError",
    "Montagem",
    "OpcoesReplay",
    "PRIORIDADE_ANALYTICS",
    "PRIORIDADE_ESTADO",
    "PRIORIDADE_MICRO",
    "PRIORIDADE_MOTOR",
    "PRIORIDADE_PERFIL_SESSAO",
    "PRIORIDADE_SAIDA",
    "SessaoFluxo",
    "criar_fonte",
    "grid_para_simbolo",
    "montar",
]
