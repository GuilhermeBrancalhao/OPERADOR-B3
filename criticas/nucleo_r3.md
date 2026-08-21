# Crítica adversarial R3 — terceira rodada

**Data:** 2026-08-21 · **Escopo:** verificar as correções da onda 5 + território que R1 e R2 não tocaram + ataque às junções
**Barra:** leitura de fluxo tick-a-tick do WDO, picos de 5–10 mil eventos/s, nível Profit Pro (`bar/barra_profit_pro.md`)
**Método:** execução real — suíte, 23 re-mutações (20 sobreviventes da R2 + 3 da R1), 28 mutações novas, benchmark próprio do pipeline com **tudo** ligado, cProfile, 9 sondas adversariais (`.mut/sonda_r3.py`, `.mut/sonda2_r3.py`, `.mut/sonda3_r3.py`, `.mut/bench_r3.py`).

> **Fora de escopo por instrução:** `fluxopro/app/`, `scripts/operar.py`, `bench_app.py` e `tests/test_app_*.py` apareceram durante esta auditoria (builder em paralelo). Não foram analisados nem mutados. Todas as medições e mutações abaixo foram feitas contra a suíte de **312 testes** que existia no início da rodada; ao final da rodada a suíte era de 396 (os 84 novos são do builder paralelo e passam).

---

# VEREDITO: **NÃO PASSA**

Primeiro o que é verdade e foi medido: **a onda 5 é o melhor trabalho das três rodadas.** O defeito quadrático do `MotorSinais` foi genuinamente eliminado — 152.874 ev/s isolados na minha máquina com custo por evento **plano** (fator µs/ev de 1,00 ao dobrar N cinco vezes), contra os 258 ev/s da R2. Os 476 linhas sem teste do `inferencia_mbp.py` viraram 1.193 linhas de teste, e 13 das 20 mutações que sobreviveram na R2 agora morrem — incluindo as 4 do MBP, uma delas derrubando 31 testes. As faixas de convicção da fonte existem, a divergência 70×75 está documentada, e a normalização por magnitude do caso WINFUT foi implementada com teste-controle honesto.

E o veredito é o mesmo, por quatro motivos independentes, todos medidos:

0. **A camada de dados inteira — `fluxopro/dados/`, 7 módulos — não está versionada.** Um `.gitignore` com o padrão `dados/` a torna invisível ao git. Um clone fresco deste repositório **não coleta os testes**: 5 erros de `ModuleNotFoundError: No module named 'fluxopro.dados'`. E as provas de "working tree limpo" da R1 e da R2 eram estruturalmente cegas exatamente aos arquivos que elas mais mutaram.
1. **O feed ao vivo trava permanentemente, em silêncio, a partir de 1.000 negócios/s** — dez vezes abaixo da barra. `AdaptadorMT5._puxar_ticks` congela e nenhuma `FalhaCaptura` é emitida. É o único caminho de dados ao vivo que existe.
2. **O defeito quadrático não foi consertado — foi movido de casa pela terceira vez.** Vive agora em `inferencia_mbp.py`, na forma exata dos dois anteriores, e a docstring publica uma tabela medida no eixo errado afirmando que a curva é plana. No regime real do WDO (book estreito, preço cravado) o módulo entrega **1.639 passos/s a 10.000/s de tape** e piora conforme o mercado acelera.
3. **O pipeline com o `InferidorMBP` ligado roda a 7.851 ev/s** — abaixo da barra. E o `InferidorMBP` não é opcional: sem UMDF/ProfitDLL, ele é a única ponte para microestrutura.

Somado a isso: **14 de 28 mutações novas sobreviveram (50%)**, com `perfil_player.py` deixando passar a inversão de quem agrediu e a troca de agressividade por passividade — os dois fatos que o módulo existe para medir.

---

## ÚNICO MAIOR GAP

### `.gitignore:5` — o padrão `dados/` apaga a camada de dados do controle de versão

```
$ cat .gitignore
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dados/          <-- linha 5

$ git check-ignore -v fluxopro/dados/mt5.py
.gitignore:5:dados/    fluxopro/dados/mt5.py
```

`dados/` sem barra inicial é um padrão **não ancorado**: casa com qualquer diretório chamado `dados` em qualquer profundidade. A intenção óbvia era ignorar um diretório de saída de gravação na raiz. O efeito é ignorar o **pacote de código** `fluxopro/dados/`.

`git ls-files fluxopro/` devolve 25 arquivos. O pacote `fluxopro/dados/` não está entre eles. Estão fora do controle de versão:

| módulo não versionado | o que é |
|---|---|
| `dados/mt5.py` (382 linhas) | **a única fonte de dados ao vivo do produto** |
| `dados/simulador.py` | o `SimuladorWDO` — a única fonte de qualquer medição de qualidade já feita |
| `dados/replay.py` | replay de CSV |
| `dados/leitor_gravacao.py` | replay de gravação — a base do backtest |
| `dados/adaptador.py` | a classe-base `AdaptadorDados` |
| `dados/eventos_captura.py` | `FalhaCaptura` / `TipoFalha` |
| `dados/__init__.py` | — |

### Consequência 1 — o repositório não reconstrói o produto

```
$ git clone . /tmp/c && cd /tmp/c && python -m pytest tests/ -q --collect-only
E   ModuleNotFoundError: No module named 'fluxopro.dados'   (x5)
ERROR tests/test_dados_mt5.py
ERROR tests/test_gravacao_gravador.py
ERROR tests/test_gravacao_integridade.py
ERROR tests/test_replay_determinismo.py
ERROR tests/test_simulador_determinismo.py
!!!!!!!!!!!!!!!!!!! Interrupted: 5 errors during collection !!!!!!!!!!!!!!!!!!!
277 tests collected, 5 errors
rc = 2
```

Os testes que consomem esses módulos **são versionados**; os módulos, não. O repositório está internamente inconsistente: qualquer CI, qualquer máquina nova, qualquer `git clone` recebe um projeto que não coleta. E se esta máquina for perdida, ~1.400 linhas — incluindo o adaptador MT5 inteiro — não existem em lugar nenhum.

### Consequência 2 — as provas de integridade das três rodadas eram vazias para esses arquivos

A R2 aplicou **dez** mutações em `fluxopro/dados/` (N01–N10) e encerrou publicando como prova de restauração:

```
$ git diff --stat -- fluxopro/
(vazio)
```

Esse comando **não podia** devolver outra coisa: os arquivos mutados são ignorados pelo git. O mesmo vale para a R1 e para a primeira versão desta rodada. **Uma mutação deixada para trás em `mt5.py`, `simulador.py` ou `replay.py` teria entrado no produto e nenhuma das três auditorias teria como notar.**

Precisei verificar a minha própria restauração por outro caminho — conferindo, arquivo a arquivo, que a âncora original de cada uma das 51 mutações está presente e nenhuma substituição está aplicada:

```
mutacoes conferidas nas 4 tabelas
  TODAS as ancoras originais presentes e nenhuma mutacao aplicada -> restauracao integra
```
(as 3 únicas exceções são âncoras que a onda 5 legitimamente reescreveu — N16, N21, N23 — e nenhuma tem mutação aplicada.)

**Um defeito que esconde outros defeitos vale mais que qualquer defeito isolado.** Este apaga a evidência de todos os outros, custa um caractere para consertar, e enquanto existir nenhuma auditoria futura consegue provar o que afirma.

**Conserto:** trocar `dados/` por `/dados/` na linha 5 do `.gitignore` (ancorando na raiz), `git add fluxopro/dados/`, e conferir que `git ls-files fluxopro/ | wc -l` passa de 25 para 32. Depois, um teste de fumaça que rode `git clone` num tmpdir e exija `pytest --collect-only` com rc 0 — porque este defeito é da classe que volta.

---

## SEGUNDO MAIOR GAP

### `fluxopro/dados/mt5.py:214-215` — `_puxar_ticks` trava o feed para sempre em qualquer segundo com mais de 1.000 ticks

```python
de = ultimo_tick_time_msc // 1000 if ultimo_tick_time_msc else 0     # linha 214  <- SEGUNDOS
ticks = mt5.copy_ticks_from(self._symbol, de, 1000, mt5.COPY_TICKS_ALL)   # linha 215  <- 1000 primeiros
...
    if time_msc <= ultimo_tick_time_msc:
        continue                                                     # linha 232
    novo_ultimo = max(novo_ultimo, time_msc)                         # linha 233
```

`copy_ticks_from(symbol, date_from, count, flags)` devolve os **`count` primeiros** ticks a partir de `date_from`, em ordem crescente. `de` é truncado para o **segundo**. Logo, enquanto o cursor `ultimo_tick_time_msc` estiver dentro do segundo `S`, todo poll pede "os 1.000 primeiros ticks a partir de `S`" — e recebe sempre os mesmos 1.000. Se o segundo `S` tiver mais de 1.000 ticks, `novo_ultimo` para de avançar e **`de` nunca sai de `S`**. Não há recuperação: nenhum caminho do código volta a mover o cursor.

Reproduzido (`python .mut/sonda_r3.py c`), com 3.000 ticks dentro de um segundo — WDO a 3.000 negócios/s, **abaixo** do pico de 5–10 mil da barra:

```
 poll  ticks novos   ultimo_time_msc   de(seg)
    1        1,000         1,000,999     1,000
    2            0         1,000,999     1,000
    3            0         1,000,999     1,000
    4            0         1,000,999     1,000
   ...            0                ...     ...
   ticks entregues: 1.000 de 3.000. PERDIDOS PARA SEMPRE: 2.000
```

Três agravantes que transformam um bug de throughput num risco financeiro:

1. **É silencioso.** O único detector de falha (`_LIMIAR_GAP_S`, linhas 182-195) mede o intervalo entre **polls** com `time.monotonic()`, não a idade do **dado**. O polling continua saudável a 20 Hz enquanto o tape está congelado. Nenhuma `FalhaCaptura` é emitida.
2. **O sintoma é indistinguível de mercado parado.** Um operador olhando a tela vê tape vazio e book congelado — a leitura mais comum disso é "liquidez sumiu", que é exatamente uma condição em que se opera. E o congelamento acontece no **pico de volume**, isto é, no momento em que a leitura importa.
3. **O teste não pode pegar.** `tests/test_dados_mt5.py:74-77` — o mock ignora `de` e `count`:
   ```python
   def copy_ticks_from(self, symbol, de, count, flags):
       if self._ticks_por_chamada:
           return self._ticks_por_chamada.pop(0)
   ```
   Ele não implementa o contrato que está sendo testado. Os 10 testes de `mt5.py` passam com o feed morto.

**Conserto:** cursor em milissegundos (`copy_ticks_range(de_ms, ate_ms)` ou `copy_ticks_from` com `de` derivado do último `time_msc` sem truncar), `count` dimensionado para o pico (10.000 no mínimo) **com detecção de saturação** — se `len(ticks) == count`, a janela estourou e há perda: emitir `FalhaCaptura(TipoFalha.GAP_TICKS)` e repuxar. E um detector de staleness de **dado** (nenhum tick novo há X segundos em horário de pregão), separado do detector de intervalo de poll. O mock de teste tem de honrar `de` e `count`.

---

# PARTE A — as correções da R2, verificadas

## A.1 Suíte — saída literal

```
$ python -m pytest tests/ -q
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
........................                                                 [100%]
312 passed in 1.48s
```

## A.2 As 20 mutações que sobreviveram na R2, re-aplicadas (+ as 3 pendentes da R1)

Harness `.mut/harness.py` (substituição literal, `pytest`, restauração no `finally`). Tabela em `.mut/r3_remut.json`, resultados em `.mut/r3_remut_res.json`.

| # | Arquivo:linha | Mutação | R2 | **R3** | Testes que pegam |
|---|---|---|---|---|---|
| N01 | `dados/replay.py:109` | sort perde o desempate `(ts, origem, índice)` | 🟢 | 🟢 **AINDA VIVE** | — |
| N03 | `dados/replay.py:34-35` | `buyer_broker`/`seller_broker` trocados no CSV | 🟢 | 🟢 **AINDA VIVE** | — |
| N04 | `dados/simulador.py:99-102` | agressão de COMPRA empurra o preço para BAIXO | 🟢 | 🟢 **AINDA VIVE** | — |
| N05 | `dados/simulador.py:92` | regime de absorção desligado | 🟢 | 🟢 **AINDA VIVE** | — |
| N06 | `dados/mt5.py:284` | bids ordenados do PIOR para o melhor | 🟢 | 🟢 **AINDA VIVE** | — |
| N08 | `dados/leitor_gravacao.py:130` | filtro de horário nunca exclui nada | 🟢 | ☠️ MORTA | 1 |
| N09 | `dados/leitor_gravacao.py:99` | hash divergente não levanta exceção | 🟢 | ☠️ MORTA | 3 |
| N10 | `dados/leitor_gravacao.py:145` | sort perde o desempate por tipo/índice | 🟢 | 🟢 **AINDA VIVE** | — |
| N11 | `gravacao/formato.py:60` | `decodificar_niveis` inverte a ordem | 🟢 | ☠️ MORTA | 1 |
| N12 | `gravacao/formato.py:31` | `SCHEMA_VERSAO` 1 → 99 | 🟢 | 🟢 **AINDA VIVE** | — |
| N14 | `gravacao/gravador.py:185-186` | `meta.json` com `hora_inicio`=MAX, `hora_fim`=MIN | 🟢 | ☠️ MORTA | 1 |
| N15 | `gravacao/gravador.py:143` | `fsync` nunca forçado | 🟢 | ☠️ MORTA | 2 |
| N16* | `gravacao/catalogo.py:137` | `verificar_integridade` aprova qualquer arquivo | 🟢 | ☠️ MORTA | 3 |
| N17 | `gravacao/catalogo.py:98` | `consultar_intervalo` usa `hora_inicio` como `hora_fim` | 🟢 | ☠️ MORTA | 2 |
| N18 | `motor/sinais.py:208` | `dominancia_minima` 0.70 → 0.0 | 🟢 | ☠️ MORTA | 2 |
| N22 | `motor/sinais.py:215` | janela da micro 15s → 1 dia | 🟢 | ☠️ MORTA | 1 |
| N23* | `microestrutura/inferencia_mbp.py:413` | perna do LADO nunca conferida | 🟢 | ☠️ MORTA | 3 |
| N24 | `microestrutura/inferencia_mbp.py:396-399` | lado passivo invertido | 🟢 | ☠️ MORTA | **19** |
| N25 | `microestrutura/inferencia_mbp.py:118` | confiança de cancelamento no topo 0.55 → 1.0 | 🟢 | ☠️ MORTA | 6 |
| N26 | `microestrutura/inferencia_mbp.py:252-253` | pendência expirada nunca vira cancelamento | 🟢 | ☠️ MORTA | **31** |
| M06 | `core/eventos.py:50` | `round()`→`int()` no `PriceGrid` | 🟢 (R1+R2) | ☠️ MORTA | 4 |
| M09 | `core/relogio.py:39` | `RelogioReplay` aceita retroceder | 🟢 (R1+R2) | ☠️ MORTA | 2 |
| M27b | `microestrutura/eventos_mbo.py:34` | `CONFIANCA_OBSERVADO` 1.0 → 0.5 | 🟢 (R2) | ☠️ MORTA | 8 |

`*` N16 e N23 deram `ERRO_ANCORA` porque o código foi reescrito; **re-derivei as duas contra o código vivo** (X17 e X23 da Parte B) e as duas morrem.

**Placar: 13 das 20 morrem; 7 continuam vivas. As 3 dívidas antigas da R1 (M06/M09/M27b) foram todas fechadas.**

### As 7 que continuam vivas, e por que importam

- **N04 + N05 — as dinâmicas de preço do `SimuladorWDO` continuam invertíveis sem quebrar nada.** Agressão de compra pode empurrar o preço para baixo, e o regime de absorção pode ser desligado, com a suíte verde. É a terceira rodada com essas duas vivas, e é a base do problema de validade científica da Parte D: **todo número de qualidade de sinal deste projeto saiu de um gerador cujo comportamento de mercado não tem uma única asserção.**
- **N03 + N06 — a semântica de identidade e de topo de book na borda continua descoberta.** `buyer_broker`/`seller_broker` podem ser trocados na leitura do CSV e os bids podem ser ordenados do pior para o melhor. Combinadas com X06 e X10 da Parte B (inversão do agressor no `perfil_player`), **quatro inversões independentes da camada "quem está fazendo o quê" passam despercebidas.**
- **N01 + N10 — a ordem determinística no empate de timestamp continua sem asserção nos dois adaptadores**, apesar de `tests/test_replay_determinismo.py` existir. Ele prova que a mesma entrada dá a mesma saída numa execução; não prova que a ordem no empate é a documentada. É a forma que um refactor real assume: some a garantia sem inverter nada.
- **N12 — `SCHEMA_VERSAO` pode ir a 99.** É o campo cuja função declarada é detectar incompatibilidade entre gravação e leitura.

**Prova de tree limpo — e por que ela não pode ser feita com `git diff`.**

Para os 12 arquivos versionados, comparação byte a byte contra o blob de `HEAD`: **todos idênticos**. `git diff --stat -- fluxopro/` vazio (`perfil_player.py` aparece como `M` por mtime; o conteúdo bate).

Para os 4 arquivos de `fluxopro/dados/` que esta rodada mutou (N01, N03, N04, N05, N06, N08, N09, N10, X11–X16), **git não serve** — eles são ignorados (ver "Único maior gap"). Verifiquei conferindo, nas 4 tabelas de mutação das três rodadas, que a âncora original de cada mutação está presente no arquivo e que nenhuma substituição está aplicada:

```
mutacoes conferidas nas 4 tabelas
  TODAS as ancoras originais presentes e nenhuma mutacao aplicada -> restauracao integra
```

Suíte re-executada: `312 passed`. `.mut/` é o material desta auditoria — nada de produção foi alterado.

## A.3 Os benchmarks, re-medidos por mim

### O que os builders alegam — confere

Rodei `python bench_motor.py` (o deles) na minha máquina:

| Alegação do builder | Medido por mim | Veredito |
|---|---|---|
| Motor isolado 184.013 ev/s | **152.874 ev/s** | confirma (variação de máquina) |
| Motor escalona linear | **fator µs/ev = 1,04 / 1,07 / 1,05 / 1,00** ao dobrar N 4x | **confirma — é linear** |
| Pipeline com motor 39.678 ev/s | **39.507 ev/s** | confirma |
| Inferência ~330.000 neg/s com níveis pendurados | **278.021 / 285.406 / 285.491 / 299.740** neg/s com 50/200/800/3000 níveis | confirma **nesse eixo** |

**A correção do `MotorSinais` é real e a folga é real.** Não há inflação de número.

### O que ninguém mediu — o pipeline com TUDO ligado

`bench_carga.py` e `bench_motor.py` chamam de "pipeline completo" um arranjo que **não instancia `LivroMBO`, `InferidorMBP`, `PerfilPlayer` nem os 3 detectores de MBO**. Montei o arranjo real em `.mut/bench_r3.py` (N=40.000 passos = 80.000 eventos, tape a 5.000/s):

| Estágio | ev/s | Veredito |
|---|---|---|
| 5. núcleo + analytics + 3 detectores de tape + `MotorSinais` | **38.859** | PASSA |
| 6a. **+ `InferidorMBP` + `LivroMBO`** (só as duas classes de produção, só os 2 `assinar` que o desenho manda) | **7.851** | **NÃO PASSA** |
| 6b. + `PerfilPlayer` | **7.076** | **NÃO PASSA** |

**Uma única ponte a mais derruba o pipeline em 5x e o coloca abaixo da barra.** E não é fiação minha: 6a usa apenas `bar.assinar(Trade, inf.ao_trade)` e `bar.assinar(BookSnapshot, inf.ao_snapshot)`.

**Resposta direta à pergunta "passa de 10.000 ev/s com tudo ligado?": NÃO. Passa de 7.851** — e isso com o book de 10 níveis e a distribuição de preços amigável do `SimuladorWDO`.

### Inferência com muitos níveis pendurados — o eixo certo é outro

O eixo que o builder mediu (número de **níveis pendurados**) é justamente o que o índice por preço conserta, e ali a curva é plana de verdade. **O eixo que dói no WDO é o oposto: book estreito, tudo no mesmo preço.** O WDO negocia rotineiramente em 2–3 preços com spread de 1 tick — e é aí que ambos os buckets (`_pendentes_por_preco[P]` e `_trades_por_preco[P]`) concentram tudo.

Tape realista, 50/50 de agressor no mesmo preço, bid caindo no topo (`python .mut/sonda_r3.py a`):

| tape a | passos/s medidos | pendentes | buffer | veredito |
|---|---|---|---|---|
| 500/s | 17.676 | 151 | 76 | PASSA |
| 1.000/s | 11.332 | 301 | 152 | PASSA |
| 2.000/s | **6.677** | 601 | 306 | **NÃO PASSA** |
| 5.000/s | **2.877** | 1.501 | 752 | **NÃO PASSA** |
| **10.000/s** | **1.639** | 3.001 | 1.495 | **NÃO PASSA — 6x lento** |

**O custo por evento cresce com a taxa do mercado. É o mesmo custo quadrático que a R1 condenou em `detectores.py:72` e a R2 em `sinais.py:109`, em sua terceira casa.** cProfile de 6.000 passos (`python .mut/sonda_r3.py b`):

```
   ncalls  tottime  cumtime  filename:lineno(function)
 15754500    5.280    7.627  inferencia_mbp.py:402(_lado_casa)
 15754500    2.347    2.347  inferencia_mbp.py:394(_lado_passivo)
     6000    1.978    5.793  inferencia_mbp.py:419(_conciliar_pendente_com_buffer)
     6000    1.977    5.802  inferencia_mbp.py:437(_conciliar_pendentes_com)
```

**15,7 milhões de chamadas a `_lado_casa` para 6.000 passos — 2.626 por passo**, 64% do tempo.

Causa exata:

```python
for buffer in self._trades_por_preco.get(pendente.price, ()):     # linha 427 — varre o BUCKET INTEIRO
    if buffer.qty_restante <= 0 or not self._lado_casa(...): continue
...
for pendente in self._pendentes_por_preco.get(buffer.price, ()):  # linha 439 — idem
...
while bucket and bucket[0].qty_restante <= 0:                     # linha 322 — poda só pela FRENTE
    bucket.popleft()
```

Um item vivo-mas-incasável na **cabeça** do bucket bloqueia toda a poda; todos os mortos atrás dele são re-varridos a cada evento. O bucket tem tamanho O(janela × taxa) — logo o custo por evento é O(taxa) e o custo total é O(n × taxa).

E o mais grave: **a docstring de `inferencia_mbp.py:180-197` publica uma tabela medida afirmando que a curva é plana em ~330.000 neg/s, e fecha com "num pipeline realista medem-se ~120.000 eventos/s, contra uma barra de 10.000".** A tabela é verdadeira e o eixo é o errado. Uma alegação medida no eixo em que o conserto funciona, apresentada como prova de que o módulo é rápido, é pior que nenhuma alegação — porque desarma a próxima revisão. O comentário na linha 194-197 ("`p` é tipicamente 1") é a hipótese que falha: medi `p` chegando a 3.001.

## A.4 O teste do WINFUT é honesto? **É — e o cenário passa pelo gate mesmo assim**

**O teste é honesto.** Verifiquei as três peças e todas fazem o que dizem:
- `test_winfut_nao_emite_confirmado_de_compra_no_repique_de_magnitude_menor` (`tests/test_motor_sinais.py:242`) reproduz o cenário do relato: fase vendedora qty 20, repique comprador qty 9 (razão 0,45, a mesma ordem do 915/1925), com **dominância percentual idêntica (0,900) nas duas fases** — que é o ponto.
- O controle (`:263`) desliga só `magnitude_relativa_minima` e **exige** que o motor caia no modo de falha. Ele cai. **É o gate que barra, não outro efeito** — confirmado: o teste principal ainda assere `dominancia >= 0.85` e `faixa == MAXIMA_CONVICCAO`, provando que as outras condições estavam satisfeitas.
- `test_magnitude_relativa_alta_nao_barra_movimento_do_tamanho_do_dia` (`:275`) fecha a saída fácil de o gate ser um "sempre não".

**Mas o cenário tem uma variante que atravessa o gate, e ela é mais realista que a testada.** O gate compara a magnitude corrente com o **p95 de uma amostra de reservoir do dia** (`sinais.py:394-429`). O reservoir é uniforme sobre o dia: se o pico extremo for menos de 5% dos trades do dia — que é exatamente o caso de um pico de abertura seguido de sessão normal — o p95 desce para o regime lateral e o repique passa.

Medido (`python .mut/sonda2_r3.py e`) — mesmo tape do teste, com uma fase lateral miúda inserida entre o pico e o repique:

| trades laterais entre as fases | `CONFIRMADO` de COMPRA emitidos | `magnitude_relativa` final | veredito |
|---|---|---|---|
| 0 *(o ponto que o teste usa)* | 0 | 0,450 | gate segurou |
| 900 | 0 | 0,450 | gate segurou |
| 3.000 | 0 | 0,451 | gate segurou |
| 9.000 | 0 | 0,555 | gate segurou |
| **20.000** | **480** | **0,920** | **MODO DE FALHA WINFUT** |

20.000 negócios laterais a ~10/s são ~33 minutos de tape morno — trivial num pregão de WDO, e a forma que o relato de 11/02 descreve (pico de manhã, repique depois). **O teste do repo está no único ponto da curva em que o gate segura.**

Duas fragilidades estruturais junto:
- **A calibração é knife-edge em `percentil_magnitude_referencia = 0.95`.** O gate só protege enquanto o pico do dia for mais de 5% dos trades do dia. Nada no código ou no teste registra essa dependência.
- **No começo do dia o gate está escancarado por desenho**, e a própria docstring admite: *"a referência é a própria magnitude corrente e a razão nasce em ~1.0"* (`sinais.py:413-415`). A abertura — o momento de maior risco e de maior magnitude — é o momento em que o gate não filtra nada.

## A.5 As 3 correções da inferência — duas completas, uma incompleta

| Defeito alegado | Confirmado? | Correção |
|---|---|---|
| **UNKNOWN com confiança máxima** | Sim | **COMPLETA.** `_executar` aplica `confianca = min(confianca, config.confianca_execucao_lado_nao_confirmado)` (`inferencia_mbp.py:466-468`) — **teto, não valor fixo**, então a invariante "lado não confirmado nunca vale mais que confirmado" é estrutural e não pode ser quebrada por configuração. N24/N25 agora morrem com 19 e 6 falhas. |
| **Evidência autocontraditória** | Sim | **COMPLETA.** `_resolver_como_cancelamento` (`:496-512`) agora deriva `negociavel = no_topo or negociou`, onde `negociou = pendente.qty_executada > 0` — o ramo "fora do topo não havia como negociar" deixou de ser emitido com 0.90 quando os dados do próprio módulo o desmentem. O campo `qty_executada` existe só para isso e a docstring explica por quê. |
| **Docstring mentindo sobre O(1)** | Sim | **INCOMPLETA — e a nova docstring é pior que a antiga.** O índice por preço é uma otimização real e resolve o eixo "largura do book". Mas a nova docstring (`:180-197`) publica uma tabela medida **no único eixo em que o conserto funciona**, conclui "plana", e afirma "~120.000 eventos/s num pipeline realista". Medi 1.639 passos/s no regime real do WDO (A.3) e 7.851 ev/s no pipeline (A.3). A alegação de que `p` é "tipicamente 1" (`:194`) falha: medi `p = 3.001`. |

---

# PARTE B — 28 mutações novas em território virgem

**14 sobreviveram (50%).** Tabela em `.mut/r3_novas.json`, resultados em `.mut/r3_novas_res.json`.

| # | Arquivo:linha | Mutação | Resultado | Testes que pegam |
|---|---|---|---|---|
| X01 | `analytics/brokers.py:110` | janela expira com `>=` (trade na borda exata some) | 🟢 **SOBREVIVEU** | — |
| X02 | `analytics/brokers.py:140` | `ranking_por_saldo` do mais VENDEDOR primeiro | ☠️ MORTA | 1 |
| X03 | `analytics/brokers.py:61` | `preco_medio_venda` usa a soma da COMPRA | ☠️ MORTA | 1 |
| X04 | `analytics/brokers.py:88` | aceita trade de OUTRO símbolo | 🟢 **SOBREVIVEU** | — |
| X05 | `analytics/brokers.py:132` | `ranking_por_volume` ignora `top_n` | ☠️ MORTA | 1 |
| X06 | `microestrutura/perfil_player.py:83-84` | **quem agrediu invertido (comprador↔vendedor)** | 🟢 **SOBREVIVEU** | — |
| X07 | `microestrutura/perfil_player.py:82` | `periodo` sempre 0 → persistência sempre 1 | ☠️ MORTA | 1 |
| X08 | `microestrutura/perfil_player.py:99-101` | perna vendedora não conta clip (tamanho médio inflado) | 🟢 **SOBREVIVEU** | — |
| X09 | `microestrutura/perfil_player.py:124` | `ranking_por_volume` do MENOR para o maior | ☠️ MORTA | 1 |
| X10 | `microestrutura/perfil_player.py:38` | **`agressividade` mede o lado PASSIVO** | 🟢 **SOBREVIVEU** | — |
| X11 | `dados/mt5.py:369` | `derivar_deltas` nunca emite DELETE | ☠️ MORTA | 1 |
| X12 | `dados/mt5.py:355` | `derivar_deltas` nunca emite UPDATE | ☠️ MORTA | 2 |
| X13 | `dados/mt5.py:271` | negócio NO ask deixa de ser agressão de compra (`>=`→`>`) | ☠️ MORTA | 1 |
| X14 | `dados/mt5.py:231` | dedup de tick vira `<` (reprocessa o último a cada poll) | 🟢 **SOBREVIVEU** | — |
| X15 | `dados/mt5.py:289` | `profundidade_maxima` ignorada (book inteiro publicado) | 🟢 **SOBREVIVEU** | — |
| X16 | `dados/mt5.py:352` | `BookDelta` de ADD sempre com `position=0` | 🟢 **SOBREVIVEU** | — |
| X17 | `gravacao/catalogo.py:137` | `verificar_integridade` aprova qualquer arquivo *(re-derivada da N16)* | ☠️ MORTA | 3 |
| X18 | `gravacao/catalogo.py:54` | `escanear` não limpa o índice (entrada apagada sobrevive) | 🟢 **SOBREVIVEU** | — |
| X19 | `gravacao/catalogo.py:38-41` | `arquivo()` prefere o plano ao `.gz` (lê a versão velha) | 🟢 **SOBREVIVEU** | — |
| X20 | `gravacao/catalogo.py:103` | intervalo invertido é silenciosamente reordenado | 🟢 **SOBREVIVEU** | — |
| X21 | `core/barramento.py:46` | prioridade ignorada (só ordem de inscrição) | ☠️ MORTA | 1 |
| X22 | `core/barramento.py:46` | empate resolvido pela ordem INVERSA de inscrição | ☠️ MORTA | 1 |
| X23 | `microestrutura/inferencia_mbp.py:413` | perna do LADO nunca conferida *(re-derivada da N23)* | ☠️ MORTA | 3 |
| X24 | `microestrutura/inferencia_mbp.py:324-325` | bucket vazio nunca sai do índice (vazamento por preço) | ☠️ MORTA | 1 |
| X25 | `analytics/footprint.py:163` | diagonal do imbalance de COMPRA invertida (P−1 em vez de P+1) | ☠️ MORTA | 1 |
| X26 | `analytics/footprint.py:165-166` | vizinho diagonal zerado deixa de marcar imbalance | 🟢 **SOBREVIVEU** | — |
| X27 | `analytics/footprint.py:200` | média de volume por nível divide por `n+1` | 🟢 **SOBREVIVEU** | — |
| X28 | `analytics/footprint.py:193-194` | `delta_divergente` só olha alta | 🟢 **SOBREVIVEU** | — |

## Leitura da tabela

**`core/barramento.py` está bem coberto — 2 de 2 mortas.** A ordem de prioridade e o desempate por ordem de inscrição têm asserção de contrato de verdade (`tests/test_barramento.py:18`). É o único módulo desta rodada com 100%.

**`microestrutura/perfil_player.py` é o pior achado da Parte B — 3 de 5 vivas, e as 3 são a semântica do módulo.**
- **X06 inverte quem agrediu.** `lado_comprador_agrediu` e `lado_vendedor_agrediu` podem ser trocados: toda a atribuição agressor×passivo do módulo sai espelhada e nada percebe.
- **X10 troca agressividade por passividade.** `agressividade` é a primeira métrica listada na docstring do módulo (linha 3) — a que responde "esse player estava atacando ou defendendo". Pode devolver exatamente o complemento e a suíte fica verde.
- **X08** faz o tamanho médio de clip da perna vendedora dobrar.

Os 5 testes de `test_micro_perfil_player.py` (68 linhas para 125 de produção) pegam ordenação e período — a plumbing — e não pegam nenhuma das três semânticas. E o módulo **não tem assinatura no barramento**: `PerfilPlayer.ao_trade` não é registrado por nenhum módulo de produção do núcleo.

**`dados/mt5.py` — 4 de 8 vivas, e as 4 são a borda ao vivo.** O que morre é `derivar_deltas` (bem testado). O que sobrevive é tudo que só acontece contra o terminal real: dedup de tick (X14), limite de profundidade (X15), posição no book (X16). É exatamente o perímetro em que vive o maior gap desta rodada — e a razão é a mesma: o mock não implementa o contrato que representa.

**`gravacao/catalogo.py` — a onda 5 fechou a integridade (X17 e N17 morrem, 3 e 2 falhas), mas o ciclo de vida do índice continua descoberto.** X18 (índice não é limpo no re-escaneamento → um dia apagado do disco continua listado), X19 (lê o `.csv` velho em vez do `.csv.gz` novo quando os dois existem — que é o estado transitório do próprio `_comprimir_e_remover`) e X20 (intervalo invertido aceito em silêncio) sobrevivem.

**`analytics/footprint.py` — 3 de 4 vivas, todas na leitura, não na contabilidade.** X26 pode inverter a política do vizinho zerado, X27 pode errar a média por nível (que é o denominador de `absorcao_topo`/`absorcao_fundo`) e X28 pode cegar metade da divergência de delta. O que morre é só a direção da diagonal (X25).

**`analytics/brokers.py` — 3 de 5 mortas.** O módulo deixado deliberadamente de fora da onda 4 está melhor do que se esperava: preço médio ponderado, ordenação e `top_n` têm teste. Sobrevivem o limite exato da janela (X01) e o filtro de símbolo (X04).

---

# PARTE C — ataques às junções

## C.1 Dois componentes podem discordar do mesmo fato? **Sim — e a causa é uma fronteira de relógio**

`AdaptadorMT5` carimba os dois tipos de evento com **relógios diferentes**:

```python
timestamp_ns=time_msc * 1_000_000,   # mt5.py:246 — relógio do SERVIDOR MT5
timestamp_ns=time.time_ns(),         # mt5.py:299 — relógio LOCAL (UTC)
```

Servidores MetaQuotes rodam tipicamente em GMT+2/+3. A janela de reconciliação do `InferidorMBP` é de **300 ms**. Medido (`python .mut/sonda_r3.py d`) — mesma sequência de mercado (queda de 40 lotes no bid, negócio de 40 no mesmo preço 1 ms depois):

```
com offset de +3h no trade -> eventos gerados: {'CANCEL': 1}
CONTROLE, um relogio so    -> eventos gerados: {'TRADE': 1}
```

**A mesma sequência vira execução ou cancelamento dependendo só do relógio.** Essa é a distinção inteira do produto: "o nível foi consumido" contra "o nível foi retirado". Com qualquer offset acima de 300 ms — e o offset típico é de horas, não de milissegundos — **100% das execuções viram cancelamentos** e o `LivroMBO` publica um livro que nunca negociou.

Nenhum teste cobre a fronteira: o mock injeta `time_msc` coerente com o relógio local da máquina de teste.

## C.2 Reprodutibilidade real do replay — **funciona no simulador, quebra na gravação real**

Montei a prova que faltava (`python .mut/sonda2_r3.py g`): pipeline ao vivo com `Gravador` anexado, depois replay do arquivo gravado por um pipeline idêntico, comparando `(ts, estágio, direção, dominância, detecção)` trade a trade.

```
   ao vivo:  4,000 trades processados
   replay:   4,000 trades processados
   linhas comparadas: 4,000   DIVERGENCIAS: 0
```

**Boa notícia: com o `SimuladorWDO`, o replay reproduz o vivo exatamente.** O `seed_reservatorio_magnitude = 42` fixo (`sinais.py:217`) é o que torna o `MotorSinais` reprodutível apesar do reservoir sampling — decisão certa.

**Má notícia: uma gravação feita pelo `AdaptadorMT5` real é impossível de reproduzir na ordem certa**, corolário direto de C.1. O `AdaptadorLeitorGravacao` ordena por `(timestamp_ns, tipo, índice)` (`leitor_gravacao.py:145`) — e os timestamps gravados vêm dos dois relógios. Medido (`python .mut/sonda3_r3.py j`), 20 pares trade→book publicados nessa ordem ao vivo:

```
   ordem ao vivo   (10 primeiros): [('T',0), ('B',0), ('T',1), ('B',1), ('T',2), ...]
   ordem no replay (10 primeiros): [('B',0), ('B',1), ('B',2), ('B',3), ('B',4), ...]
   iguais? NAO — 1a divergencia no indice 0
```

**Todos os books primeiro, todos os trades depois.** Nenhuma reconciliação MBP sobrevive a isso. E na virada de sessão o mesmo offset joga trade e book em **dias diferentes** no disco, quebrando o particionamento do `Gravador`. Backtest sobre gravação real é hoje inviável — e é a base de qualquer validação.

## C.3 Ordem de entrega no barramento — **testada e correta**

`Barramento.assinar` ordena por `(prioridade, ordem)` no setup e `publicar` só itera (`barramento.py:46,49`). X21 e X22 morrem: existe teste de contrato para prioridade e para desempate por ordem de inscrição. **Não achei caminho em que analytics leia estado velho do `EstadoMercado`** dentro do núcleo — a serialização single-threaded e a ordenação em `assinar` seguram.

Duas reservas, nenhuma testada:
- **Reentrância.** `publicar` itera a lista que `assinar` muta; um assinante que assine durante uma publicação corrompe a iteração em curso. Nada barra e nada testa.
- **Ausência de isolamento de exceção.** Uma exceção em qualquer assinante aborta a publicação inteira e mata os assinantes de prioridade maior. Numa borda ao vivo, um erro de analytics derruba a captura.

## C.4 Virada de sessão — **8 de 12 componentes carregam o dia anterior**

Medido (`python .mut/sonda2_r3.py f`):

| TEM `iniciar_nova_sessao` | **NÃO TEM** |
|---|---|
| `EstadoMercado`, `CumulativeDelta`, `MedidorAgressao`, `VWAP` | `VolumeProfilePorPeriodo`, `FootprintPorTimeframe`, `RankingCorretoras`, `PerfilPlayer`, `DetectorAbsorcao`, `DetectorExaustao`, `DetectorClipInstitucional`, **`MotorSinais`** |

O caso grave é o `MotorSinais`, porque o estado que sobrevive é **a calibração do gate que a onda 5 acabou de construir**:

```
   p95 da magnitude ao fim do 'dia 1' = 964,025
   p95 apos salto de 24h no timestamp  = 964,025
```

O gate de magnitude do dia 2 está calibrado por um dia que já acabou. Depois de um dia de pânico ele fica fechado o dia inteiro; depois de um feriado morno, escancarado. A docstring diz "percentil da magnitude **do dia**" (`sinais.py:408`) — não existe API para começar um dia.

Junto: `RankingCorretoras` vem com `janela_ns = None` de fábrica (acumula desde a construção, sem janela e sem reset); `PerfilPlayer` acumula para sempre; e `DetectorEscora._ja_sinalizado` / `DetectorIcebergPorRecarga._ja_sinalizado` nunca são limpos — **um nível sinalizado no dia 1 fica mudo para sempre.**

## C.5 Determinismo sob carga — **passa**

500.000 eventos, duas execuções, comparação de tupla a tupla (`python .mut/sonda2_r3.py h`):

```
   execucao 1: 250,000 trades em   9.35s (53,492 ev/s)
   execucao 2: 250,000 trades em   8.38s (59,684 ev/s)
   -> IDENTICAS (deterministico)
```

## C.6 Metade dos detectores de microestrutura não tem caminho de invocação

`DetectorEscora`, `DetectorIcebergPorRecarga` e `DetectorLiquidezFantasma` expõem `verificar(...)` — API de **pull**, que exige um chamador que monte os argumentos certos. No núcleo auditado, **nenhum módulo de produção os instancia nem chama `verificar`**; só os testes e o benchmark. Tive de escrever a fiação eu mesmo para conseguir medir o estágio 6. (A fiação existe hoje em `fluxopro/app/sessao_fluxo.py:370-394`, fora do escopo desta rodada.)

Junto com isso, o achado 5.6 da R1 continua intocado na terceira rodada: `FonteMicro` é importado em `detectores.py:20` e **nunca usado**; as 6 detecções saem com `confianca=1.0` fixo; e a docstring do módulo (`detectores.py:7`) continua prometendo que *"a confiança do evento de origem se propaga"*. Com o `InferidorMBP` sendo a única fonte disponível, **todo evento de livro é hipótese e todo detector publica certeza.**

## C.7 Footprint: o imbalance diagonal marca a maioria dos níveis

`qty_minima_imbalance: int = 0` (`footprint.py:57`) — o piso vem desarmado de fábrica pela terceira rodada (achado 5.4 da R1). Com piso 0, `nivel.qty_comprador < 0` é sempre falso, sobra só o `== 0`, e o ramo `qty_vizinho == 0 → append` (`:165-166` e `:181-182`) marca imbalance de razão infinita a partir de **1 lote contra 0**. Medido (`python .mut/sonda3_r3.py i2`):

| trades no candle | níveis | % dos níveis marcados como imbalance |
|---|---|---|
| 40 | 18 | **50,0%** |
| 60 (faixa larga) | 29 | **72,4%** |
| 100 | 21 | **42,9%** |
| 200 (faixa larga) | 41 | **53,7%** |
| 1.000 | 21 | 9,5% |

Num candle esparso — o caso comum de 1 minuto de WDO num tick fino — a lista de imbalance vira "todo nível que negociou". X26 e X27 sobreviverem confirma que nenhuma asserção prende esse comportamento.

---

# PARTE D — dá para decidir uma operação com dinheiro real?

**Não.** Priorizado por risco, e sem inventar trabalho:

| # | O que falta | Onde | Risco se ignorado |
|---|---|---|---|
| 0 | **Ancorar o padrão (`dados/` → `/dados/`), versionar `fluxopro/dados/`, e um teste de fumaça de `git clone` + `pytest --collect-only`** | `.gitignore:5` | O produto não reconstrói a partir do repositório e nenhuma auditoria consegue provar que restaurou o que mutou. |
| 1 | **Cursor de tick em milissegundos + detecção de saturação de `count` + staleness de DADO** | `dados/mt5.py:214-215,182-195` | O feed congela em silêncio no pico de volume e o operador lê tape parado como mercado parado. |
| 2 | **Um relógio só na borda** — carimbar book com tempo de servidor, ou trades com tempo local, e registrar o offset medido | `dados/mt5.py:246` × `:299` | 100% das execuções viram cancelamentos; gravação real fica irreproduzível (C.1, C.2). |
| 3 | **Custo do `InferidorMBP` no eixo do preço** — poda O(1) do meio do bucket (índice por `(preço, lado)` + remoção do item conciliado), não só pela frente | `inferencia_mbp.py:427,439,322` | 7.851 ev/s no pipeline, 1.639 no regime real do WDO. Bloqueia a barra. |
| 4 | **Corrigir a docstring de custo de `inferencia_mbp.py`** para medir o eixo que dói | `inferencia_mbp.py:180-197` | Uma tabela medida no eixo errado desarma a próxima revisão. Custa 20 minutos. |
| 5 | **`iniciar_nova_sessao` no `MotorSinais`** (reservoir de magnitude, janelas, persistência, caches) **e nos 7 outros componentes sem reset** | `motor/sinais.py`, `perfil_player.py`, `brokers.py`, `footprint.py`, `detectores.py` | O gate anti-WINFUT do dia 2 calibrado pelo dia 1 (C.4). |
| 6 | **Sequence number + detecção de gap de feed** | `core/eventos.py` — **ainda inexistente** (item 5 da R2, item 6 da R1) | Livro reconstruído de deltas sem detecção de gap apresenta estado errado como certo. |
| 7 | **Testes de semântica do `perfil_player.py`** (agressividade, agressor, clip por perna) | `perfil_player.py:38,83-84,99-101` | 3 inversões da leitura de player passam despercebidas (X06/X08/X10). |
| 8 | **`FonteMicro`/confiança propagada nos 6 detectores** | `detectores.py:7,20,223,267,356,413,471,541` | Terceira rodada intocado. Toda hipótese do MBP é publicada como fato. |
| 9 | **Robustez do gate de magnitude a pico<5% do dia** (janela de referência por regime, ou percentil sobre janela móvel em vez do dia inteiro) | `motor/sinais.py:394-429` | O modo de falha WINFUT passa na variante realista (A.4). |
| 10 | **`qty_minima_imbalance` default > 0** | `analytics/footprint.py:57` | Terceira rodada intocado. 42–72% dos níveis marcados (C.7). |
| 11 | **Ciclo de vida do `Catalogo`** (limpar índice, preferir `.gz`, recusar intervalo invertido) | `gravacao/catalogo.py:54,38-41,103` | Replay do dia errado ou da versão velha do arquivo. |
| 12 | **Isolamento de exceção e reentrância no barramento** | `core/barramento.py:48-50` | Erro de analytics derruba a captura ao vivo. |

## O buraco de validade científica — tamanho e conserto

**Nenhuma medição de qualidade de sinal deste projeto jamais tocou tape real.** Três rodadas de auditoria, incluindo esta, mediram tudo sobre o `SimuladorWDO`. E o `SimuladorWDO` **não tem uma única asserção sobre o comportamento de mercado que ele gera**: N04 (agressão de compra empurra o preço para baixo) e N05 (regime de absorção desligado) sobrevivem pela terceira rodada consecutiva.

O tamanho disso não é "falta um backtest". É que a cadeia inteira de justificativa do produto está sem chão:

- Todo limiar de fábrica — `dominancia_minima=0.70`, `magnitude_relativa_minima`, `limiar_imbalance=3.0`, `multiplo_absorcao=2.0`, `janela_reconciliacao_ns=300ms` — foi escolhido de leitura de vídeo, não de dado. Nenhum foi calibrado contra nada.
- A taxa de falso positivo/negativo de cada detector é **desconhecida**. A R1 mediu 98,2% de falso positivo no `DetectorAbsorcao` — sobre o simulador. Esse número não significa nada sobre o WDO.
- O `InferidorMBP` faz uma afirmação verificável — "esta queda foi execução, aquela foi cancelamento" — e **nunca foi confrontado com a verdade**. Existe verdade disponível: o volume impresso no tape é público. Uma gravação de meia hora de WDO permite medir a taxa de acerto da reconciliação diretamente.
- O gate anti-WINFUT foi construído a partir de **um** episódio narrado num documento de pesquisa, reproduzido sinteticamente, e a variante realista dele já fura o gate (A.4).

**O que fecharia o buraco, em ordem, e o que cada passo custa:**

1. **Gravar.** Antes de qualquer coisa, `scripts/gravar.py` contra o WDO ao vivo por 5 pregões. Mas isso **hoje não produz um arquivo utilizável**: o feed trava acima de 1.000 negócios/s (gap 1) e a gravação sai com dois relógios (gap 2). **Os gaps 1 e 2 não são bugs de borda — são o que impede a validação de começar.** É por isso que estão no topo da lista, acima do defeito de custo.
2. **Fixar o simulador contra a gravação.** Com tape real na mão, escrever os testes que faltam ao `SimuladorWDO` (N04/N05) calibrando as dinâmicas contra estatísticas medidas do WDO real: distribuição de qty, autocorrelação de agressor, frequência de deslocamento por tick. Só então o simulador vira instrumento em vez de decoração.
3. **Medir a reconciliação do `InferidorMBP` contra a verdade impressa.** Volume executado inferido × volume impresso no tape, por nível, por janela. É a única métrica deste projeto que tem gabarito objetivo, e ela sozinha diz se a camada de microestrutura vale alguma coisa em modo MBP.
4. **Só então medir sinal.** Taxa de disparo por hora, por regime (abertura/lateral/tendência), e o que aconteceu com o preço nos N ticks seguintes a cada `CONFIRMADO`. Não para provar lucro — para saber se o sinal é raro ou constante, e se muda de comportamento entre regimes.

Até o passo 3, **nenhum número de qualidade produzido por este sistema pode ser citado como evidência de nada**, e isso inclui os números favoráveis desta auditoria.

---

*Working tree verificado nos dois regimes: para os 12 arquivos versionados, comparação byte a byte contra o blob de `HEAD` — todos idênticos; para os 4 de `fluxopro/dados/`, que o git ignora, conferência de âncora original em todas as tabelas de mutação das três rodadas — restauração íntegra. Suíte re-executada. As 51 mutações (23 re-aplicadas + 28 novas) foram revertidas uma a uma pelo `finally` do harness. Material de reprodução em `.mut/`: `harness.py`, `r3_remut.json`/`r3_novas.json` (tabelas) e `*_res.json` (resultados), `bench_r3.py` (pipeline com tudo ligado), `sonda_r3.py {a,b,c,d}`, `sonda2_r3.py {e,f,g,h,i}`, `sonda3_r3.py {j,i2}`. Nenhum arquivo de produção foi alterado por esta revisão. `fluxopro/app/`, `scripts/operar.py`, `bench_app.py` e `tests/test_app_*.py` foram deliberadamente ignorados.*
