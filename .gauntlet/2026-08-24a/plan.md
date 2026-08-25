# Plano congelado da execução

## market-core

ARTIFACT: contratos imutáveis, MakerProxy, LeituraASG e decisão consultiva.

EVIDENCE: testes unitários, replay determinístico, snapshots serializados e procedência por componente.

DEFECT_CLASS: cálculo direcional incorreto, confiança enganosa, leitura mutável, integração regressiva e qualquer caminho de envio de ordem.

## feed-health

ARTIFACT: FeedQualitySnapshot e integração observável das fontes existentes, sem conversão de texto ou imagem em ticks.

EVIDENCE: testes de sequência, deduplicação, timestamp regressivo, atraso, reconexão e ausência de dependência.

DEFECT_CLASS: perda silenciosa, troca silenciosa de fonte, estado de saúde incorreto e inconsistência temporal.

## workspace-ui

ARTIFACT: workspace ASG-like adicional, responsivo e consultivo, preservando todos os workspaces anteriores.

EVIDENCE: screenshots em 1280x720, 1480x900 e 1920x1080; estados vazio, vivo, atrasado, sem book, divergência, pré-sinal, confirmação, replay e erro.

DEFECT_CLASS: regressão visual, informação crítica invisível, dependência apenas de cor/hover, repaint oculto e leitura cruzada entre threads.

## shadow-audit

ARTIFACT: gravação sidecar limitada, labels futuras, relatórios, guardrails e auditoria automatizada de ausência de ordens.

EVIDENCE: testes de causalidade temporal, limites de memória, manifestos, benchmarks e logs brutos.

DEFECT_CLASS: lookahead, crescimento ilimitado, alteração automática de produção, benchmark não reproduzível e falsa alegação de paridade ASG.
