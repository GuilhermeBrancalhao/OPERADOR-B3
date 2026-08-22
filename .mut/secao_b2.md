
---

## PARTE B (2/2) — 27 mutações NOVAS

Alvos escolhidos pelo critério da tarefa: o que nenhuma rodada tocou
(`gravacao/`, `core/barramento.py`, `core/relogio.py`, `dados/leitor_gravacao.py`,
`dados/replay.py`) e o que a onda 8 **acabou de escrever** (`_MapaProcedencia`,
`_RelogioServidor`, cauda de magnitude, compactação de heap). Mesmo protocolo:
suíte inteira por mutante, registro em voo, sha256 normalizado.

**Placar: 13 MORTAS · 14 SOBREVIVERAM (52% de sobrevivência).**

| # | arquivo:alvo | mutação | veredito |
|---|---|---|---|
| **G01** | `gravacao/gravador.py:149` | **substitui a lista de horários pelo min/max incremental — a CORREÇÃO** | 🟢 **SOBREVIVEU** |
| **G02** | `gravacao/gravador.py:117` | rotação de dia aceita voltar no tempo (`>` vira `!=`) | 🟢 **SOBREVIVEU** |
| **G03** | `gravacao/gravador.py:184` | `n_eventos_total` deixa de somar (vira o `max`) | 🟢 **SOBREVIVEU** |
| C01 | `gravacao/catalogo.py:100` | `--de/--ate` lidos em `-03` em vez de UTC | ☠️ MORTA |
| **C02** | `gravacao/catalogo.py:136` | **arquivo AUSENTE conta como íntegro** | 🟢 **SOBREVIVEU** |
| C03 | `gravacao/catalogo.py:148` | hash passa a incluir o cabeçalho | ☠️ MORTA |
| **C04** | `gravacao/catalogo.py:56` | `escanear` lê só o primeiro símbolo | 🟢 **SOBREVIVEU** |
| F01 | `gravacao/formato.py:59` | `decodificar_niveis` perde `n_orders` | ☠️ MORTA |
| **F02** | `gravacao/formato.py:78` | **comprador e vendedor trocados na volta do disco** | 🟢 **SOBREVIVEU** |
| **B01** | `core/barramento.py:48` | `publicar` itera uma cópia (a correção de reentrância) | 🟢 **SOBREVIVEU** |
| **B02** | `core/barramento.py:48` | **exceção de assinante engolida** | 🟢 **SOBREVIVEU** |
| B03 | `core/barramento.py:44` | ordenação por prioridade removida | ☠️ MORTA |
| **RL1** | `core/relogio.py:20` | **`RelogioReal` troca `monotonic_ns` por `time_ns`** | 🟢 **SOBREVIVEU** |
| RL2 | `core/relogio.py:63` | replay recusa timestamp igual | ☠️ MORTA |
| L01 | `dados/leitor_gravacao.py:137` | borda superior do recorte vira exclusiva | ☠️ MORTA |
| **L02** | `dados/leitor_gravacao.py:145` | desempate troca tipo↔índice | 🟢 **SOBREVIVEU** |
| **L03** | `dados/leitor_gravacao.py:94` | **base do catálogo errada ⇒ integridade nunca reprova** | 🟢 **SOBREVIVEU** |
| P01 | `dados/replay.py:19-20` | trade e delta trocam prioridade no empate | ☠️ MORTA |
| **O01** | `detectores.py:394` (onda 8) | **cursor da varredura AVANÇA ao remover** | 🟢 **SOBREVIVEU** |
| O02 | `detectores.py:374` (onda 8) | `_remover` não trata "a chave é a última" | ☠️ MORTA |
| **O03** | `detectores.py:403` (onda 8) | **RNG de despejo vira o `random` global** | 🟢 **SOBREVIVEU** |
| O04 | `dados/mt5.py:467` (onda 8) | janela deixa de ser estritamente monotônica | ☠️ MORTA |
| O05 | `dados/mt5.py:490` (onda 8) | `_resetar` não limpa a janela | ☠️ MORTA |
| O06 | `dados/mt5.py:472` (onda 8) | poda por idade deixa de rodar | ☠️ MORTA |
| O07 | `motor/sinais.py:426` (onda 8) | `_n_visto` conta antes do filtro | ☠️ MORTA |
| **O08** | `inferencia_mbp.py:802` (onda 8) | **teto de compactação `2×` vira `1×`** | 🟢 **SOBREVIVEU** |
| S01 | `app/saida.py:131` | marca `[OBS]` usa `>` em vez de `>=` | ☠️ MORTA |

### B.4 — o que as novas mostram

**G01 é a prova formal do maior gap.** Apliquei a **correção** — trocar a lista
por `min`/`max` incrementais — e os 574 testes continuam verdes. Junto com o
fato de que a versão atual também passa, isso estabelece o que interessa:
**nenhum teste da suíte distingue a implementação O(número de eventos) da
implementação O(1).** O defeito não é "não pego"; é **inatingível** por esta
suíte, nas duas direções. Um builder que o consertar não terá como provar que
consertou, e um que o reintroduzir não será pego. É por isso que o conserto
precisa vir acompanhado de um teste de crescimento, não só do patch de 3 linhas.

**As três do gravador sobreviveram todas (G01, G02, G03).** `G02` faz a rotação
de dia aceitar retrocesso: um evento atrasado com a data de ontem **fecha o dia
corrente e reabre o anterior**, escrevendo `meta.json` no meio do pregão e
recomeçando os hashes. `G03` faz o `n_eventos_total` do `meta.json` mentir. O
`Gravador` é, nesta rodada, o módulo com a pior cobertura efetiva do projeto —
e é o único guardião de um dado que não tem segunda cópia.

**C02 + L03 + Y07 juntas desmontam a cadeia de integridade.** Cada uma sozinha é
uma mutação; juntas são o mesmo furo por três caminhos:

- `C02` — um arquivo **que não existe** passa a contar como íntegro
  (`resultado[nome_base] = True`);
- `L03` — apontar o catálogo de verificação um nível acima faz o índice sair
  vazio, então `_checar_integridade` não encontra nada para reprovar;
- `Y07` (viva desde a R4) — a verificação pode ser simplesmente **desligada em
  silêncio**.

A docstring de `verificar_integridade` (`catalogo.py:113-127`) dedica quinze
linhas a explicar que este é *"a única defesa contra gravação corrompida"*
porque *"não existe fonte externa de histórico de book para WDO/WIN"*. Três
mutações independentes a neutralizam sem mover um teste.

**F02 e N03 são a mesma inversão nos dois leitores.** `F02` troca
`buyer_broker`/`seller_broker` na volta do disco em `gravacao/formato.py`; `N03`
faz o mesmo em `dados/replay.py` e está viva pela 5ª rodada. Quem gravou o
pregão e quem leu o CSV podem discordar sobre **quem comprou e quem vendeu**, e
a suíte não distingue. Isso importa mais depois da onda 8, porque foi ela que
ligou `RankingCorretoras` e `PerfilPlayer` — os dois módulos cuja pergunta
inteira é "quem está fazendo o quê".

**B01 e B02: o barramento não prende nem a reentrância nem o isolamento de
exceção.** As duas reservas que a R3 levantou (§C.3) e nunca foram fechadas
continuam abertas, e agora estão medidas: `B01` aplica a **correção** de
reentrância (iterar uma cópia) e a suíte fica verde; `B02` **engole toda
exceção** de assinante e a suíte fica verde. Ou seja, o comportamento do
barramento diante de um assinante que levanta — se derruba a captura ao vivo ou
se segue em frente — não está decidido por teste nenhum, nas duas direções.
Num sistema single-threaded em que analytics, detectores, motor, saída **e o
gravador** compartilham a mesma publicação, é a política que decide se um erro
de exibição mata a gravação do pregão.

**RL1: `RelogioReal` pode trocar `monotonic_ns` por `time_ns` sem quebrar nada.**
O módulo inteiro existe (docstring de `core/relogio.py:1-8`) para que nada no
núcleo chame o relógio da máquina diretamente, e `RelogioReplay` tem 20 linhas
de docstring justificando por que retroceder é inaceitável — com teste
(`RL2` morre). O irmão ao vivo, que é quem de fato roda em produção, não tem o
teste equivalente.

**As três novas da onda 8 que sobreviveram são as três invariantes que os
próprios docstrings justificam por escrito:**

- **`O01`** — `_varrer` documenta em cinco linhas que *"ao remover, o cursor NÃO
  avança"*, porque `_remover` traz outra chave para o mesmo slot, *"é o que
  permite a um mapa cheio de cadáveres esvaziar em O(n) escritas em vez de
  nunca"*. Fazer o cursor avançar não quebra teste nenhum.
- **`O03`** — o `_SORTEIO_DESPEJO = random.Random(0x5EED2026)` pode virar o
  `random` global do processo. A alegação de determinismo por construção não
  tem asserção. (Ver C.3b: hoje é latente, e explico por quê.)
- **`O08`** — `_limiar = max(_PISO_TETO_HEAP, 2 * len(vivos))` pode virar
  `1 * len(vivos)`. O fator 2 é **a constante de amortização inteira** da
  correção da 5ª casa: com `1×` a compactação dispara a quase toda inserção e o
  custo O(1) amortizado volta a ser O(n) por evento. A onda 8 aprendeu (M1/M2)
  que `len` não prova nada e passou a contar **trabalho** com um espião sobre
  `_compactar_heap` — mas o espião conta se a compactação *aconteceu*, não se
  ela acontece **raramente**. O teste que faltou é sobre a frequência.

Note o padrão: `O04`, `O05`, `O06`, `O07` e `O02` **morrem** — as invariantes
mecânicas do código novo estão bem cobertas. O que sobrevive são as três
**constantes de política** (o cursor, a semente, o fator 2) que o autor
justificou em prosa e não converteu em asserção. É o modo de falha
característico de código muito bem documentado: a docstring vira o teste na
cabeça de quem escreveu.
