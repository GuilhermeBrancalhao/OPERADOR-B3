# Descoberta do feed — 2026-08-24

## Resultado verificável nesta máquina

Classificação atual: **adaptador MT5 implementado, conexão ao vivo não comprovada nesta execução**.

- O repositório possui `fluxopro/dados/mt5.py` e a montagem seleciona esse adaptador quando `FonteDados.MT5` é configurado.
- Nenhum processo `terminal64`, MetaTrader ou MT5 estava ativo durante a inspeção.
- O módulo Python `MetaTrader5` não estava instalado no Python do sistema usado pelo projeto.
- Nenhuma ponte estruturada Claude/Anthropic, WebSocket, ZeroMQ ou contrato de feed externo foi encontrada em `fluxopro/`, `scripts/`, `tests/` ou `README.md`.
- Nenhuma variável de ambiente com nome Claude/Anthropic/MT5/MetaTrader foi observada; valores de segredos não foram lidos.

Isso não prova que a conta do operador nunca recebeu mercado ao vivo; prova apenas que **não é possível afirmar conexão viva hoje a partir do estado local inspecionado**. O código MT5 continua sendo a fronteira oficial disponível, mas exige terminal, pacote, autenticação e mercado ativos para comprovação.

## Contrato de segurança

- Texto, screenshot ou resposta de LLM não será transformado em `Trade`, `BookSnapshot` ou `BookDelta`.
- Uma fonte externa só será ligada quando houver origem, transporte, autenticação, schema, timestamp, sequência, profundidade, qualidade do agressor e política de reconexão documentados.
- Ausência de contrato externo não dispara fallback silencioso: a interface deve identificar explicitamente SIMULADOR, REPLAY, MT5 ou INDISPONÍVEL.

## Checklist para comprovar MT5 ao vivo

1. Terminal MetaTrader 5 ativo e autenticado.
2. Pacote `MetaTrader5` disponível no mesmo Python que executa o Operador B3.
3. Símbolo WDO/WIN selecionado e visível no Market Watch.
4. `initialize()`, `symbol_info_tick()` e `market_book_add()` confirmados sem erro.
5. Trades e book publicados com timestamps monotônicos por uma janela controlada.
6. Evidência bruta de latência, lacunas, duplicatas, profundidade e reconexão preservada no relatório.
7. Auditoria de ausência de qualquer chamada de ordem aprovada.
