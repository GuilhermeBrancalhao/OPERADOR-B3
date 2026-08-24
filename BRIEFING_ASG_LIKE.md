# Briefing de implementação — Operador B3 ASG-like

Documento executivo versionado da missão aprovada. A fonte integral é o briefing fornecido pelo operador em 24/08/2026 e está materializada nesta execução em `.gauntlet/2026-08-24a/`.

## Contrato

Evoluir o Operador B3 sem remover nem degradar fluxos atuais, adicionando feed observável, MakerProxy transparente, matriz ASG-like, decisão estritamente consultiva, workspace dedicado, replay determinístico, aprendizado em shadow mode e auditoria contínua.

Não copiar código, marca, logotipo, ativos nem declarar a reprodução da fórmula proprietária da ASG. O Maker será um proxy independente, configurável, versionado, com evidências, cobertura, confiança e procedência.

## Invariantes

- preço interno em ticks inteiros;
- uma publicação ordenada por evento;
- snapshot consistente e imutável por quadro;
- memória limitada no caminho quente;
- nenhum LLM no processamento por tick;
- ausência, atraso e inferência de dados sempre visíveis;
- nenhum envio de ordens;
- Stop e A1/A2/A3 apenas informativos;
- parâmetros aprendidos jamais promovidos automaticamente.

## Entregas

1. `FeedQualitySnapshot` compatível com simulador, replay e MT5.
2. `MakerProxySnapshot` com absorção, reposição, divergência, clips e agressão.
3. `LeituraASG` e `DecisionSnapshot` imutáveis.
4. Workspace ASG-like adicional com DADOS, PROCESSAMENTO, MATRIZ e DECISÃO.
5. Sidecar de shadow learning causal e limitado.
6. Testes, benchmarks, screenshots, auditoria de procedência e rollback.

## Regra de aceite

Nenhum P0, P1 ou P2 aberto; testes antigos e novos aprovados; replay reproduzível; performance medida; ausência de APIs de ordem comprovada; limitações e Human Gate documentados.
