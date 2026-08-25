# Auditoria de integração — rodada R0

## Escopo

Reescrita visual NEXO no workspace compatível `ASG-like`, integração de
MakerProxy e preservação dos workspaces históricos. A chave e o nome técnico
`ASG-like` foram deliberadamente mantidos como ABI para atalhos, perfis salvos
e testes; a identidade exibida é `OPERADOR B3 · NEXO`.

## Alterações auditadas

- `PainelNexoMercadoASG` cria uma superfície autoral de pressão, sinal
  consultivo, preço observado e força derivada; séries visuais usam
  `deque(maxlen=180)`.
- `WorkspaceASG` preserva DOM, Tape, Bookmap, Dados, Processamento, Matriz,
  Decisão e Trilha; apenas muda sua hierarquia em telas largas.
- `SessaoFluxo._emitir_deteccao` encaminha a mesma `Deteccao` causal ao
  MakerProxy antes do callback externo. O Maker continua descartando tipos não
  mapeados ou timestamps regressivos.
- A decisão continua apenas informativa: a UI declara `SEM ENVIO DE ORDENS`.

## Evidência executada

| Probe | Resultado |
|---|---|
| UI, sessão e regressão histórica | `63 passed` |
| UI + ausência de ordens + auditoria | `86 passed` |
| R1 focada após correções | `201 passed` |
| Auditoria AST de APIs de ordem | PASS, 178 módulos Python, nenhum achado |
| Screenshots controlados | 5 estados em 1280×720, 1480×900 e 1920×1080 |
| Matriz completa nos três tamanhos | PASS nos testes; seis componentes visíveis |
| Maker sessão→detecção | PASS por novo teste de integração |

Os screenshots são integração controlada Barramento→Sessão→Ponte→Janela,
explicitamente rotulados como não E2E. Eles não comprovam adaptador externo ou
feed de mercado real.

## Gaps abertos

- **UI-001:** o gráfico NEXO é um trajeto de preço observado com eixo temporal
  e marcadores min/max, mas ainda não possui candle builder/OHLC. Não inventar
  candles: exigir um agregador causal antes de desenhá-los.
- **PERF-001:** a medição isolada R1 (`benchmark-r4.json`, 30 execuções, sem
  pytest concorrente) marcou baseline mediana `9.195/s`, ASG completo
  `6.914/s` e overhead Maker `21,33%`; portanto não atingiu a barra de
  `10.000/s` e `10%`. O limite permanece aberto e bloqueia a alegação de
  integração plena. O perfilamento deve separar custo de persistência,
  microestrutura e matriz antes de qualquer relaxamento.
- **SHADOW-001:** não havia uma partição real de shadow para validar; o
  auditor marca isso como SKIPPED, não PASS.

## Fechamento R1 parcial

Após a crítica cega, foram corrigidos e testados:

- `MAKER-001`: `ingerir_trade`, que não materializa snapshot no hot path,
  agora atualiza a persistência com a mesma pontuação ponderada do snapshot;
  foi adicionada prova de dois trades em três segundos.
- `THREAD-001`: o produtor reivindica o pedido de analytics sob lock antes de
  congelar; um pedido intercalado permanece pendente para o próximo quadro.
- `GEOMETRY-001`: `JanelaFluxo._estado_salvo` restaura geometria e estado, com
  teste de round-trip.
- A ponte detector→Maker passou a ser exercitada pelo Barramento com detector
  de absorção habilitado, não apenas por método privado.

- O caminho `ingerir_trade` agora atualiza persistência sem materializar
  snapshot público. A otimização rápida trata o caso comum de agressão isolada
  sem criar `MakerEvidence` por tick; a equivalência com o snapshot ponderado
  permanece coberta pelo teste do hot path.

O auditor independente encontrou nenhum P0. A auditoria P1 fechou `MAKER-001`;
os gaps de desempenho, gráfico e shadow continuam abertos até haver
evidência. A migração de `saveState` legado foi coberta por teste com docas
sem NEXO e fechada como `COMPAT-001`.

O resultado não declara paridade
visual com qualquer terceiro nem aprovação de integração plena.
