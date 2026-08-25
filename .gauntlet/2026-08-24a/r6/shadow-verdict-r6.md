# CRÍTICO SHADOW R6 — veredito fresh/read-only

## Veredito

**FAIL** no HEAD congelado `718376c06bf9251e246761a75b3310a03ec20a10` (`fix: validar shadow antes de assinar o barramento`).

Contagem: **P0 0 · P1 2 · P2 0**. A regra desta rodada exige zero P0/P1/P2; portanto não há PASS.

O código shadow auditado permaneceu igual ao HEAD durante os probes. Um trabalho UI concorrente apareceu sem commit durante a execução; ele não foi usado para aprovar nem reprovar os contratos shadow.

## Achados bloqueadores

### [P1] Reset de sessão pode ser descartado e labels atravessam pregões

`AsyncShadowWriter.reset_session()` envia `_ResetCommand` pela mesma fila descartável das amostras (`fluxopro/app/shadow_runtime.py:75-90`). Quando a fila está cheia, retorna `False`. `SessaoFluxo.iniciar_nova_sessao()` ignora esse retorno (`fluxopro/app/sessao_fluxo.py:1356-1358`) e libera imediatamente a nova sessão. O sidecar direto sabe censurar os labels no reset (`fluxopro/shadow/sidecar.py:190-201`), mas essa garantia se perde na fronteira assíncrona.

Probe real, fila de capacidade 1 e writer bloqueado:

- amostra do pregão anterior entrou no writer;
- uma segunda amostra ocupou a fila;
- `reset_session("WDOV26")` retornou `False`;
- a primeira amostra da sessão seguinte foi aceita;
- o label antigo saiu `COMPLETA`, preço inicial `100`, preço final `110`, duração `1.000.000.000 ns`.

O resultado correto após uma virada seria label antigo `CENSURADA`, preço final ainda `100`, sem usar preço do pregão seguinte. Isso é contaminação temporal direta do dataset e invalida treino/validação mesmo sem lookahead dentro de uma sessão.

Correção mínima: comandos de controle não podem compartilhar a política drop-on-full das amostras. A virada precisa ter entrega/ack obrigatórios antes de aceitar eventos da sessão seguinte, ou desabilitar o shadow de forma explícita e auditável. Adicionar teste adversarial com writer bloqueado, fila cheia e reset concorrente.

### [P1] Repetir o mesmo replay duplica a amostra lógica

O app cria `SidecarShadow` sem identidade de replay (`fluxopro/app/sessao_fluxo.py:655-659`); o sidecar então gera `run_id` aleatório (`fluxopro/shadow/sidecar.py:49-64`) e inclui esse UUID no `id_amostra` (`fluxopro/shadow/sidecar.py:141-145`). A suíte existente prova isolamento e IDs disjuntos entre runs (`tests/test_shadow_sidecar.py:334-357`), não idempotência nem reprodução do mesmo resultado.

Probe end-to-end com `SessaoFluxo`, `FonteDados.REPLAY`, mesmo `shadow_dir` e exatamente o mesmo Book/Trade duas vezes:

- runs criados: `2`;
- features agregadas: `2`;
- IDs distintos: `2`;
- amostras com o mesmo `(timestamp_ns, symbol)`: `2`.

Assim, reexecutar um replay bem-sucedido dobra os dados que um consumidor da raiz encontra. Os IDs diferentes apenas escondem a duplicata lógica; não tornam o replay idempotente ou reproduzível.

Correção mínima: exigir uma identidade determinística derivada de fonte/recorte/configuração/versão, ou um `run_id` explícito obrigatório no caminho de replay; rerun idêntico deve verificar e reutilizar/no-op o resultado finalizado. A auditoria também deve detectar duplicatas lógicas entre runs destinados ao mesmo recorte.

## P1 anteriores tentados e não reproduzidos

| Probe | Evidência real | Resultado |
|---|---|---|
| Flag inoperante | flag off não criou diretório; flag on produziu 1 feature e os dois reports | FECHADO |
| I/O no barramento | `SidecarShadow.observar()` ficou bloqueado; publicação completa retornou em `13,316 ms` e o I/O rodou em thread diferente | FECHADO |
| Falha de disco escapando | `OSError("disk-r6")` no writer não escapou; estado `error`, `failures=1`; domínio avançou de 1 para 2 trades | FECHADO |
| Replay não idempotente | duas execuções idênticas produziram duas amostras lógicas | **REPRODUZIDO — P1** |
| CI `SKIPPED` | pipeline oficial gerou dataset, executou `--exigir-shadow` e terminou `PASS`; o modo CLI sem dataset continua `SKIPPED` deliberadamente, mas não é usado pelo workflow | FECHADO NO CI |
| Ausência de `report.json`/`report.md` | integração gerou 1 de cada; pipeline CI também gerou ambos com status global/shadow `PASS`; auditoria focal cobre ausência | FECHADO |
| Lookahead | toque no timestamp de admissão foi ignorado; primeiro toque aceito em `+100.000.000 ns`, duração positiva e `primeiro_toque=ALVO` | FECHADO DENTRO DA SESSÃO |
| Promoção automática | candidata completa ficou apenas elegível para revisão; `aplicacao_automatica=False` e nenhuma API apply/promote/deploy no sidecar | FECHADO |

## CI, testes e reports

- Suíte focal R6: `77 passed in 11.35s` para runtime, sidecar, governança, auditoria, integração app e ausência de execução.
- Seleção equivalente ao workflow Ubuntu: `66 passed in 8.92s` (`3` arquivos `test_shadow_*.py` + auditoria + sem-execução).
- Pipeline CI materializado em diretório temporário: gerador exit `0`; auditoria estrita exit `0`; `ORDENS: PASS`; `SHADOW: PASS`; 1 partição, 12 registros; `report.json` e `report.md` presentes; ambos os status do JSON em `PASS`.
- O glob literal `tests/test_shadow_*.py` não é expandido pelo PowerShell local, mas é expandido pelo shell Ubuntu declarado no workflow. A repetição com os três arquivos resolvidos reproduziu a semântica oficial e passou.
- Uma execução da suíte global durante edição UI concorrente terminou `1559 passed, 3 skipped, 7 failed`; ela não é evidência admissível contra o HEAD congelado porque `scripts/painel.py` e `fluxopro/ui/paineis/asg.py` mudaram em momentos diferentes durante o próprio teste. Nenhum dos sete erros atingiu os módulos shadow, e as suítes shadow congeladas acima passaram.

## Escopo e conclusão

Não foi encontrado envio de ordem nem promoção automática. Flag, isolamento de I/O/disco, causalidade intra-sessão, reports e CI estrito estão implementados. Porém, a perda de reset sob backpressure cria label entre pregões e a identidade aleatória duplica replay. Ambos são P1 de integridade do dataset.

**Escolha final: REJECT / FAIL.** Novo julgamento exige fechar os dois P1 com probes adversariais oficiais; zero P0/P1/P2 continua sendo a única condição de PASS.
