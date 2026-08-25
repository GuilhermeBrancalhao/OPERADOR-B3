# Status de integração ASG-like — R8

O pacote de evidências foi avaliado por builders e críticos separados. A
comparação visual é **proxy-biased**: a barra congelada contém a baseline do
Operador B3 e referências públicas de mercado, não uma captura real da ASG.

## Fechado com evidência

- Workspace ASG-like consultivo, com DOM, Tape, Bookmap, matriz, decisão e
  trilha de evidências no mesmo quadro.
- Feed health/procedência e estados AO VIVO, ATRASADO, SEM BOOK, ERRO e
  REPLAY; capturas são integração controlada, não E2E.
- MakerProxy independente, rotulado e fora do placar legado.
- DecisionSnapshot somente informativo; auditoria de ordens passou.
- Shadow learning assíncrono, com reset causal, replay idempotente e
  fechamento que drena eventos aceitos sob backpressure.
- Auditoria R8: `ORDENS: PASS`, `SHADOW: PASS` (1 partição, 12 registros).
- Atalhos físicos Qt Ctrl+5/Ctrl+1 cobertos por teste de integração.

## Gates ainda abertos

1. **Performance:** `PERFORMANCE_ASG.md` registra 4.219 eventos/s, abaixo da
   meta de 10.000 do briefing.
2. **Feed real:** `FEED_DISCOVERY.md` confirma adaptador MT5 no código, mas
   não havia terminal, pacote ou credencial ativos para comprovar mercado ao
   vivo nesta máquina. Nenhuma fonte textual de LLM foi convertida em tick.
3. **Human Gate:** ainda faltam capturas/gravação reais fornecidas pelo
   operador para comparar hierarquia e densidade ASG em distância operacional.

Logo, este repositório não deve ser declarado com integração plena, paridade
visual ASG ou feed real comprovado até que os três gates sejam fechados.
