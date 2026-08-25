# Auditoria de integração — OPERADOR B3

Data: 2026-08-25
Branch: `feat/asg-like-v1`
Escopo: integração da superfície visual OPERADOR B3 ao pipeline PySide6 existente.

## Resumo executivo

Foi adicionado um quinto workspace público, acessível por `Ctrl+5` e pelo nome
`OPERADOR B3`, sem remover os quatro workspaces históricos. O identificador
persistido `ASG-like` permanece como alias de compatibilidade; ele não é uma
marca exibida na interface.

A superfície usa o mesmo retrato congelado da sessão para DOM, tape, bookmap,
força, MakerProxy, pressão e gráfico. O gráfico novo agrega `ItemTape` em
`Candle` com ticks inteiros, limite de 512 velas e rejeição de timestamps
regressivos. Nenhum painel possui callback ou API de envio de ordens.

## Evidências executadas

| Gate | Comando/evidência | Resultado |
|---|---|---|
| Focalizado | `pytest tests/test_ui_operador_b3_gui.py tests/test_ui_asg_paineis.py tests/test_ui_workspace.py -q` | **95 passed** |
| Integração | `pytest tests/test_ui_workspace.py tests/test_ui_asg_contratos.py tests/test_ui_asg_paineis.py tests/test_app_asg_integration.py tests/test_ui_janela.py tests/test_sem_execucao.py -q` | **149 passed** |
| Suíte completa | `pytest tests -q` | 1590 passed, 3 skipped, 2 gates de incrementalidade falharam por limiar/CPU do ambiente |
| Ordens | `python scripts/auditoria_asg.py` | `ORDENS: PASS` |
| Shadow | `python scripts/auditoria_asg.py` sem `--shadow-dir` | `SKIPPED` — diretório não fornecido |
| Retrato | `python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42 --duracao 2 --workspace OPERADOR B3 --retrato design/operador_b3.png` | **1480×900**, 417 negócios, 3 detecções, 3 sinais |
| Retenção | `scripts/transmissao.py` + `scripts/retencao.py` | executado; retenção marca 31,1%, gráfico 32,6% |
| Performance | `scripts/benchmark_asg.py --passos 1500 --execucoes 3` | **gap**: 9.063 eventos/s ASG completo; overhead Maker 20,8% |

O retrato usado na auditoria é [design/operador_b3.png](design/operador_b3.png).
O benchmark bruto está em `outputs/auditoria-operador-b3/benchmark.json`.

## Matriz de integração

| Item | Estado | Evidência |
|---|---|---|
| C1 dados de mercado | PASS | DOM, tape, bookmap e estado do feed continuam no mesmo `Instantaneo` |
| C2 processamento | PASS | força, pressão e métricas existentes preservadas |
| C3 matriz/decisão | PASS | snapshot ASG existente e workspace consultivo |
| C4 gráfico | PASS | `AgregadorCandles`, OHLC causal, ticks inteiros, 512 velas |
| C5 mini-tape | PASS | deque limitada a 256 itens |
| C6 identidade | PASS | marca geométrica própria OPERADOR B3/NEXO |
| C7 acessibilidade | PASS parcial | direção contém texto/glifo; paleta legada mantém azul/vermelho por compatibilidade, superfície nova usa verde/rosa |
| C8 replay | PASS parcial | caminho histórico preservado; validação diferencial completa permanece pendente |
| C9 MT5 | PASS preservado | adaptador existente e testes de integração mantidos |
| C10 shadow learning | PASS parcial | infraestrutura existente; execução de relatório diário depende de diretório de dados |
| C11 auditoria de ordens | PASS | `ORDENS: PASS`; Stop/Alvos permanecem consultivos |
| C12 retenção | PASS | limites explícitos nas novas coleções |
| C13 performance | GAP P2 | benchmark não atingiu as metas de 10k/s e 10% |
| C14 visual | PASS parcial | retrato próprio capturado; não há alegação de pixel-perfect sem pacote proprietário |

## Auditoria A/B/C

- A1–A11: preservados pelos testes existentes e pelos 149 testes focados.
- A12: referências internas e compatibilidade histórica permanecem no código;
  a interface visível usa `OPERADOR B3`, sem logo/avatar/ativo de terceiro.
- A13–A14: sem execução de ordens confirmada pelo script de auditoria.
- A15: não foi executado `pip uninstall PySide6`; isso seria destrutivo para o
  ambiente. A alternativa segura é a suíte headless/core, executada acima.
- B1–B9: snapshot, causalidade, limites, estados vazios e contrato de alias
  cobertos pelos testes focados.
- C1–C6: retrato, transmissão degradada, retenção e benchmark foram executados;
  performance permanece gap mensurado.

## Gauntlet

Bar: pacote visual local `bar/` + retrato real `design/operador_b3.png`.
Runner-up: referências locais de SuperDOM/Tape/Bookmap.
Probes: interação/estados, causalidade/replay, performance e ausência de ordens.

Esta rodada tem evidências reais e revisão de integração no mesmo contexto. Não
é declarada como veredito formal de crítico cego independente: nenhum crítico
externo foi inventado. O resultado deve ser tratado como `partial` até fechar o
gap de performance e executar uma rodada independente A/B.

## Gaps abertos

1. **P2 — performance:** otimizar o caminho Maker/ASG ou rever o benchmark para
   separar custo de UI e custo de domínio, mantendo a medição reproduzível.
2. **P2 — Gauntlet:** executar crítico cego independente com o pacote `bar/` e
   registrar comparação A/B sem rótulos.
3. **P2 — shadow:** rodar relatório com um pregão/replay congelado e validar
   labels sem lookahead.

Além do gap do benchmark, a suíte completa reproduziu duas falhas nos gates
de medição incremental preexistentes (`test_ui_footprint` e `test_ui_hud`):
uma execução ficou abaixo de 300 ms de CPU para o vigia e outra mediu razões
próximas de 5×. Elas não apontam para os novos módulos, mas impedem o rótulo
“suíte verde” nesta máquina e devem ser revalidadas em executor dedicado.

Nenhum P0/P1 foi observado nesta rodada. A entrega não declara fórmula
proprietária nem paridade pixel-perfect com produto de terceiro.
