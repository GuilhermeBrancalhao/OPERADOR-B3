# Plano de partes — rodada zero

## visual-shell

ARTIFACT: Workspace ASG-like executável em 1280×720, 1480×900 e 1920×1080.
EVIDENCE: Capturas PNG lidas, comparação lado a lado com os cinco destaques e testes de redimensionamento.
DEFECT_CLASS: Hierarquia visual, legibilidade, densidade, identidade própria e ausência de ativos proprietários.

## read-model

ARTIFACT: Snapshot imutável único para o workspace, com preço, força, matriz, decisão, feed e procedência.
EVIDENCE: Testes de consistência de timestamp/símbolo, buffers limitados e replay determinístico.
DEFECT_CLASS: Leitura concorrente, dados desencontrados, memória sem limite e informação sem procedência.

## maker-integration

ARTIFACT: MakerProxy recebendo Trades, saúde do feed e detecções relevantes no caminho causal da sessão.
EVIDENCE: Testes de absorção, reposição, clips, divergência, MBP/MBO, book ausente e timestamp regressivo.
DEFECT_CLASS: Evidência de microestrutura não conectada, confirmação indevida e fórmula não auditável.

## compatibility-audit

ARTIFACT: Suite de regressão dos workspaces Fluxo, Book & Tape, Bookmap, Revisão e ASG, com auditoria de ausência de ordens.
EVIDENCE: Testes existentes e novos, replay congelado, grep de APIs de ordem e relatório de performance.
DEFECT_CLASS: Quebra de contrato, regressão visual, execução acidental de ordem e degradação de throughput.
