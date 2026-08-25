# Gauntlet workbench — OPERADOR B3

## Bar

`bar/` local, com referências de fluxo, SuperDOM, Tape, Bookmap e gráfico,
mais o retrato do produto em `design/operador_b3.png`.

## Rodada

- objetivo: integrar visual moderno e legível ao pipeline original;
- probes: UI/estados, dados causais, performance, ausência de ordens;
- evidências: screenshots, logs, diffs reproduzíveis, pytest e benchmark;
- resultado: `partial`, com gap de performance mensurado.

## Regra de honestidade

Esta execução não possui um crítico cego independente disponível no contexto.
Foi feita revisão de integração local, sem fabricar um veredito externo. O
Gauntlet formal deve repetir A/B cego na próxima rodada.

## Artefatos

- `design/operador_b3.png`
- `outputs/auditoria-operador-b3/operador_b3_degradado.png`
- `outputs/auditoria-operador-b3/benchmark.json`
- `AUDITORIA_OPERADOR_B3.md`
