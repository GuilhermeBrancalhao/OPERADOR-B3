"""Camada de analytics de fluxo — leitura de mercado construída sobre o núcleo.

Cada módulo aqui dentro assina eventos do `Barramento` (mesmo padrão de
`fluxopro.core.estado_mercado`) e mantém estado incremental: nenhum destes
componentes recalcula histórico a cada trade, porque em uso real eles rodam
no hot path (um callback por tick). Os seis módulos cobrem o núcleo mínimo de
paridade com o Profit Pro descrito em `bar/barra_profit_pro.md`:

- `volume_profile` — volume por nível de preço (POC, Value Area, HVN/LVN).
- `footprint` — histograma comprador×vendedor por nível dentro do candle.
- `delta` — delta acumulado da sessão e divergência delta×preço.
- `agressao` — taxa/velocidade de agressão em janela deslizante e clip grande.
- `brokers` — ranking de corretoras por volume e saldo.
- `vwap` — VWAP de sessão e ancorado, com bandas de desvio padrão.
"""

from __future__ import annotations
