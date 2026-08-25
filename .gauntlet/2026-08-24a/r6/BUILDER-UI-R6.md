# BUILDER UI R6 — evidências de execução

Este documento registra o trabalho e as provas do builder. Ele **não é um
veredito**, não concede `PASS` e não substitui a revisão humana/critic.

## Resultado implementado

- O estado operacional do ASG agora fecha a janela inteira: workspace, faixa,
  topo e rodapé compartilham `AO VIVO`, `ATRASADO`, `SEM BOOK`, `ERRO` ou
  `REPLAY` no mesmo quadro.
- O workspace ASG usa `PainelDOM`, `PainelTape` e `PainelBookmap` reais,
  alimentados pelo mesmo `Instantaneo`, junto de matriz, decisão, dados,
  processamento e evidências.
- O layout responsivo preserva as seis linhas da matriz e a decisão em
  1280x720, 1480x900 e 1920x1080; em 1920x1080 o Bookmap recebe a área
  operacional ampliada.
- O Ctrl+5 hidrata o último retrato antes da troca e fecha os backings depois
  da resolução da geometria pelo stack, ainda dentro do evento de teclado.
- Os workspaces Ctrl+1 a Ctrl+4 continuam usando suas docas e dimensões
  históricas. A UI segue sem superfície de ordens.

## Natureza das capturas

As 15 capturas `native_*` são classificadas como
`controlled_synthetic_integration_not_end_to_end`. Elas percorrem objetos reais
do produto — `Barramento -> SessaoFluxo -> PonteFluxo -> JanelaFluxo._tick ->
window_grab` — com eventos controlados e renderização Qt nativa. Não exercitam
adaptador externo e, portanto, **não são chamadas de end-to-end**.

Os manifests abaixo registram, por captura, estado solicitado/ASG/topo/rodapé,
resolução, caminho exercitado, painéis reais, retenção do Tape, colunas do
Bookmap, matriz/decisão e ausência de ordens:

- `evidence/native_1280x720_manifest.json`
- `evidence/native_1480x900_manifest.json`
- `evidence/native_1920x1080_manifest.json`

Validação dos 15 registros: dimensões exatas; estados coerentes; seis rótulos
da matriz presentes; decisão visível; banner `ORDENS NÃO DISPONÍVEIS`; contexto
real `PainelDOM/PainelTape/PainelBookmap`; `end_to_end=false`; adaptador externo
não exercitado.

## Prova do Ctrl+5 e preservação histórica

`ui-keyboard-probe-r6.py` usa `QTest.keyClick(... Ctrl+5)` no backend Windows,
publica eventos via barramento/sessão/ponte/tick e para o relógio antes do
atalho. O relatório `evidence/keyboard_probe_r6.json` registra:

- `snapshot_before_ctrl5 = 0`;
- `snapshot_immediate_ctrl5 = 1777200000000000000`;
- `immediate_blank = false`;
- matriz completa, decisão visível e ausência de ordens;
- DOM, Tape e Bookmap reais;
- Ctrl+1 a Ctrl+4 preservados em 1280x720 com suas docas históricas.

## Verificações executadas

- Foco R6: `49 passed` em `test_app_asg_integration.py`,
  `test_ui_asg_contratos.py` e `test_ui_janela.py`.
- Suíte integral nativa: `1582 passed, 3 skipped, 1 failed`. A única falha foi
  o microbenchmark preexistente
  `TestTrabalho::test_a_incrementalidade_do_delta_existe`, com razão variável
  abaixo do corte de 5,0x; repetição isolada oscilou entre aprovação e falha.
  Nenhum código desse painel ou limite do teste foi alterado.
- Auditoria ASG: `ORDENS: PASS`, 178 arquivos Python, nenhum achado. Shadow foi
  `SKIPPED` porque a execução não recebeu `--shadow-dir`.

## Gate

Nenhuma promoção ou aprovação é emitida por este relatório. O gate permanece
humano e independente.
