# Baseline ASG-like

- Data: 2026-08-24 (America/Sao_Paulo)
- Branch de origem: `main`
- Commit-base: `a2934c468eeff993784875acecd4d7801ddc805e`
- Branch de implementação: `feat/asg-like-v1`
- Barra congelada: `.gauntlet/2026-08-24a/bar/`
- Classificação visual: ASG-like funcional, proxy-biased até o Human Gate

## Evidências já confirmadas

- Aplicação PySide6/Qt6 com painéis QPainter.
- Barramento síncrono e determinístico.
- Preços internos em ticks inteiros.
- Fontes simulador, replay e MT5.
- Snapshots imutáveis e coleções limitadas.
- Workspaces Fluxo, Book & Tape, Bookmap e Revisão.
- Analytics de agressão, delta, footprint, volume profile e VWAP.
- Microestrutura MBP→MBO inferida e detectores de absorção, reposição/iceberg, exaustão, liquidez fantasma e clips.
- Metodologia com Macro, Micro, Regime, Linha Azul, Velocímetro e Placar.
- Fórmula proprietária do Maker não documentada e não reproduzível honestamente.
- 54 entradas de vídeo e 50 transcrições; ausentes: `zo35aF2C3Ks`, `jfE7-fwPmrA`, `PuUwzNMk-ak` e `RNGQ-BJWMWo`.
- Nenhuma ponte estruturada denominada Claude encontrada no clone.
- Texto ou imagem de LLM não será tratado como feed de mercado.

## Baseline de testes conhecido

Reexecução na branch, Python do sistema sem PySide6/NumPy: a coleta completa falhou em quatro módulos por dependências ausentes. A suíte compatível com esse ambiente, ignorando exatamente esses quatro módulos, concluiu com **755 aprovados e 14 ignorados em 360,17 s**. O ambiente isolado `.venv-asg` foi então criado para executar a suíte visual completa sem alterar o Python global.

## Segurança

O produto é consultivo. Qualquer surgimento de `order_send` ou equivalente fora de testes explicitamente permitidos é P0 e bloqueia a entrega.
