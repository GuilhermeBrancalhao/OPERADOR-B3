# Crítica adversarial R2 — verificação das correções + território novo

**Data:** 2026-08-21 · **Escopo:** verificar as correções alegadas da onda 4 + atacar `dados/`, `gravacao/`, `motor/sinais.py`, `microestrutura/inferencia_mbp.py`, `analytics/brokers.py`
**Barra:** leitura de fluxo tick-a-tick do WDO, picos de 5–10 mil eventos/s, nível Profit Pro (`bar/barra_profit_pro.md`)
**Método:** execução real — suíte, 12 re-mutações da R1, 33 mutações novas, benchmark do pipeline **completo** (o do builder não é), cProfile, 4 sondas adversariais, teste de reprodução do modo de falha WINFUT.

---

# VEREDITO: **NÃO PASSA**

As correções da onda 4 são **reais, não cosméticas** — isso precisa ser dito primeiro, porque é verdade e foi medido: 9 das 12 mutações que sobreviveram na R1 agora morrem; o `DetectorAbsorcao` saiu de 193 para **609.916 trades/s** e as deques monotônicas estão **semanticamente corretas** (0 divergências em 80.000 comparações contra varredura ingênua).

E ainda assim o veredito é o mesmo, por um motivo que a R1 previu na seção 6 e ninguém foi verificar: **o defeito quadrático não foi consertado, foi consertado num lugar só.** Ele vive intacto em `motor/sinais.py` — que é o produto — com uma janela **60x maior** que a do `DetectorAbsorcao`. O pipeline completo roda a **258 ev/s** contra uma barra de 10.000.

Somado a isso: **20 de 33 mutações novas sobreviveram (61%)**, pior que os 36% da R1. A camada inteira de gravação/catálogo/leitura pode ter a verificação de integridade desligada e a suíte continua verde. `inferencia_mbp.py` (476 linhas) tem **zero testes** e 4 de 4 mutações sobreviveram.

---

## ÚNICO MAIOR GAP

### `fluxopro/motor/sinais.py:109` e `:135` — `_dominancia` / `_micro_virou`

```python
# linha 109  (_dominancia)
self._trades_dominancia = [t for t in self._trades_dominancia if t.timestamp_ns >= limite]
vol_buy  = sum(t.qty for t in self._trades_dominancia if t.side_agressor is AgressorSide.BUY)   # 110
vol_sell = sum(t.qty for t in self._trades_dominancia if t.side_agressor is AgressorSide.SELL)  # 111

# linha 135  (_micro_virou)
self._trades_micro = [t for t in self._trades_micro if t.timestamp_ns >= limite]
```

É **a mesma linha** que a R1 apontou como maior gap em `detectores.py:72` — reconstrução completa da lista por trade, mais duas somas varrendo a janela inteira. Copiada para o motor de confluência. Com dois agravantes:

1. **A janela é `janela_dominancia_ns = 5 * 60_000_000_000` — cinco minutos** (`sinais.py:63`), 60x a janela de 5s do `DetectorAbsorcao`. A 5.000 trades/s ela guarda **1.500.000 trades**, reconstruídos a cada trade.
2. **`_na_regiao` (linha 119) chama `self._vp.val()` e `self._vp.vah()`** — e cada uma chama `value_area()` **separadamente**, que faz `sorted(self._niveis.keys())` + `self.poc` (um `min` sobre todos os níveis) + `precos_ordenados.index(poc)` (varredura linear) + a expansão gulosa. **Dois `sorted()` completos por trade**, no caminho quente.

### Medido — escalonamento do `MotorSinais` isolado

| N trades | seg | trades/s | µs/trade | fator ao dobrar N | veredito |
|---|---|---|---|---|---|
| 2.000 | 0,375 | 5.336 | 187 | — | NÃO PASSA |
| 4.000 | 1,739 | 2.300 | 435 | **x4,64** | NÃO PASSA |
| 8.000 | 7,499 | 1.067 | 937 | **x4,31** | NÃO PASSA |
| 16.000 | 23,707 | 675 | 1.482 | x3,16 | NÃO PASSA |
| 32.000 | 103,899 | 308 | 3.247 | **x4,38** | NÃO PASSA |

Custo linear dobra (x2,0); quadrático quadruplica (x4,0). **Os fatores medidos são 4,64 / 4,31 / 3,16 / 4,38.** É quadrático, e o motor **nunca** encosta na barra — nem com 2.000 trades ele passa de 5.336/s.

### cProfile — 8.000 trades pelo `MotorSinais`

```
   ncalls  tottime  cumtime  filename:lineno(function)
    27980    9.795   21.543  {built-in method builtins.sum}
 25821188    3.985    3.985  motor/sinais.py:110(<genexpr>)
 23972929    3.742    3.742  motor/sinais.py:139(<genexpr>)
  6198812    2.127    2.127  motor/sinais.py:111(<genexpr>)
 11987954    1.894    1.894  motor/sinais.py:152(<genexpr>)
     8000    1.698   12.393  motor/sinais.py:107(_dominancia)
     5990    1.328   12.181  motor/sinais.py:132(_micro_virou)
```

**67,9 milhões de avaliações de generator para 8.000 trades** — ~8.500 por trade. `_dominancia` sozinha custa 1,55 ms/trade.

### `value_area()` sozinho, por número de níveis de preço da sessão

| níveis de preço | µs/trade (só `val()`+`vah()`) | teto de trades/s |
|---|---|---|
| 50 | 45,1 | 22.164 |
| 200 | 189,0 | **5.291 — NÃO PASSA** |
| 800 | 969,6 | **1.031 — NÃO PASSA** |
| 2.000 | 2.995,5 | **334 — NÃO PASSA** |

**A partir de ~120 níveis de preço distintos, `_na_regiao` sozinha já derruba a barra** — e um pregão de WDO cobre rotineiramente centenas de ticks. Isto é independente do defeito quadrático: é O(n log n) puro no caminho quente, por trade, duas vezes.

---

# PARTE A — as correções alegadas, medidas

## A.1 Suíte — saída literal

```
$ python -m pytest tests/ -q
........................................................................ [ 37%]
........................................................................ [ 74%]
.................................................                        [100%]
193 passed in 1.02s
```

## A.2 As 12 re-mutações da R1

Harness em `.mut/harness.py` (aplica por substituição literal, roda `pytest`, restaura sempre no `finally`).

| # | Arquivo | Mutação | R1 | **R2** | Teste que agora pega |
|---|---|---|---|---|---|
| **M06** | `core/eventos.py:50` | `round()`→`int()` no PriceGrid | 🟢 sobreviveu | 🟢 **AINDA SOBREVIVE** | — |
| **M09** | `core/relogio.py:39` | `RelogioReplay` aceita retroceder | 🟢 sobreviveu | 🟢 **AINDA SOBREVIVE** | — |
| M15 | `analytics/volume_profile.py:247` | `>=`→`>` no limiar de HVN | 🟢 sobreviveu | ☠️ MORTA | 1 falha |
| M19 | `analytics/agressao.py:137` | `>`→`>=` na expiração da janela | 🟢 sobreviveu | ☠️ MORTA | 1 falha |
| M22 | `microestrutura/livro_mbo.py:562` | fila FIFO vira LIFO (`fila[0]`→`fila[-1]`) | 🟢 sobreviveu | ☠️ MORTA | **17 falhas** |
| M23 | `microestrutura/livro_mbo.py:581` | `popleft()`→`pop()` ao zerar a ordem | 🟢 sobreviveu | ☠️ MORTA | 8 falhas |
| M24 | `microestrutura/livro_mbo.py:74` | janela de reposição 1000x maior | 🟢 sobreviveu | ☠️ MORTA | 1 falha |
| M25 | `microestrutura/livro_mbo.py:695` | `melhor_bid()` devolve o PIOR bid | 🟢 sobreviveu | ☠️ MORTA | 3 falhas |
| M26 | `microestrutura/livro_mbo.py:649` | `qty_a_frente` SOMA o consumo | 🟢 sobreviveu | ☠️ MORTA | 5 falhas |
| M27 | `microestrutura/detectores.py` | confiança do Iceberg-proxy 0.6→1.0 | 🟢 sobreviveu | **N/A — detector deletado** | — |
| **M27b** | `microestrutura/eventos_mbo.py:34` | *(substituta)* `CONFIANCA_OBSERVADO` 1.0→0.5 | — | 🟢 **SOBREVIVE** | — |
| M28 | `microestrutura/detectores.py:171` | `>=`→`>` no `volume_minimo` da Absorção | 🟢 sobreviveu | ☠️ MORTA | 4 falhas |
| M30 | `microestrutura/detectores.py:347` | IcebergPorRecarga não exige recarga | 🟢 sobreviveu | ☠️ MORTA | 1 falha |

**9 morrem, 2 continuam vivas, 1 virou inaplicável.** O buraco de 606 linhas do `livro_mbo.py` foi genuinamente fechado — `tests/test_micro_livro.py` tem hoje 1.059 linhas e a mutação FIFO→LIFO derruba 17 testes. Isso é conserto de verdade.

**Mas a alegação de "corrigimos tudo" é falsa em dois pontos.** M06 e M09 estavam no backlog #13 da R1 e continuam descobertos:
- **M06** — `PriceGrid.to_ticks` pode truncar em vez de arredondar e nada percebe. É a única fronteira float→int do sistema (`eventos.py:6-7`).
- **M09** — `RelogioReplay` pode aceitar retroceder no tempo. A R1 elogiou explicitamente essa guarda (seção 4.6) e o teste continua não existindo.

**M27b é um achado novo:** `CONFIANCA_OBSERVADO` pode virar 0.5 e a suíte não nota. Essa constante é a âncora de toda a distinção observado×inferido que `eventos_mbo.py:12-16` e `inferencia_mbp.py` inteiro existem para preservar.

**Prova de tree limpo:**
```
$ git status --short
?? .mut/
$ git diff --stat -- fluxopro/
(vazio)
$ python -m pytest tests/ -q
193 passed in 1.43s
```
(`.mut/` é o material desta auditoria: harness, tabelas de mutação, benchmark e sondas. Não é código de produção.)

## A.3 Benchmark — o pipeline do builder não é o pipeline completo

`bench_carga.py` mede 4 estágios e chama o estágio 4 de "pipeline completo". **Ele nunca instancia `MotorSinais`.** Também não instancia `LivroMBO`, `InferidorMBP`, `DetectorEscora`, `DetectorLiquidezFantasma` nem `DetectorIcebergPorRecarga`. O que ele chama de completo são 3 detectores dos 6.

Rodando o do builder, `python bench_carga.py --perfil`:

| Estágio | Tempo | Eventos/s | Veredito |
|---|---|---|---|
| 1. barramento vazio | 4,77s | 104.772 | PASSA |
| 2. + `EstadoMercado` | 5,71s | 87.641 | PASSA |
| 3. + analytics (6) | 7,69s | 65.048 | PASSA |
| 4. + 3 detectores (N=40k) | 0,78s | 51.606 | PASSA |

E `python bench_detectores.py`:

```
ANTIGO (quadratico)   n= 20,000  103.375s      193 trades/s  deteccoes= 19,920 (99.6%)
NOVO (deque O(1))     n=100,000    0.164s  609,916 trades/s  deteccoes=      1 ( 0.0%)
```

**A alegação de 239.639 trades/s é conservadora — medi 609.916.** O conserto do `DetectorAbsorcao` é honesto e a folga é real. Mas a conclusão que dele se tirou — "o sistema passa" — não se sustenta, porque o sistema medido não é o sistema.

### Pipeline REALMENTE completo (`.mut/bench_r2.py`), N idêntico

| Estágio | N | Tempo | Eventos/s | Veredito |
|---|---|---|---|---|
| 3. + analytics (6 módulos) | 40.000 | 1,05s | 38.128 | PASSA |
| 4. + 3 detectores | 40.000 | 1,59s | 25.230 | PASSA |
| **5. + `MotorSinais`** | **40.000** | **154,78s** | **258** | **NÃO PASSA — 39x lento** |

**Uma única peça a mais colapsa o pipeline em 98x.** E não é constante ruim: o estágio 5 piora conforme N cresce (a 100k eventos medi 226 ev/s, contra 258 a 40k).

### Efeito da janela de 5 minutos

| Mercado a | A janela de 5 min guardaria | Medido |
|---|---|---|
| 500 trades/s | 150.000 trades | 529 trades/s |
| 2.000 trades/s | 600.000 trades | 516 trades/s |
| 5.000 trades/s | **1.500.000 trades** | 525 trades/s |

**Resposta direta à pergunta: o sistema inteiro NÃO passa de 10.000 ev/s. Passa de 258.**

## A.4 O `DetectorAbsorcao` está semanticamente correto?

**As deques monotônicas: SIM, corretas.** Teste diferencial (`.mut/adversarial.py a`) — 200 tapes aleatórios × 400 trades, com saltos de timestamp de 1 ns a 1,2 s (incluindo buracos maiores que a janela), preços repetidos e agressor `UNKNOWN` misturado, comparando `_max_precos[0]`, `_min_precos[0]`, `_volume_buy` e `_volume_sell` contra varredura ingênua a cada trade:

```
200 tapes aleatorios x 400 trades: divergencias = 0
VEREDITO: MAX/MIN E VOLUMES CORRETOS
```

O uso de `<=`/`>=` ao podar as deques (linhas 146, 149) descarta preços iguais mais antigos e mantém o `seq` mais novo, que é justamente o que faz a expiração por `seq` (linhas 190-193) funcionar. Está certo.

**A dedup de 3 gatilhos: NÃO, perde episódio legítimo.** Medido:

```
episodio 1 (40 trades, 800 lotes vendedores em 10000): 1 alerta
pausa de 3s (nao esvazia a janela de 5s) + 1 trade
episodio 2 (mesma coisa de novo, mesmo preco):         0 alerta
>>> PERDEU o 2o episodio
```

A causa é estrutural, não de parâmetro. Dos três gatilhos de rearme:
- **Gatilho 1** (`deslocamento > deslocamento_maximo_ticks`) é o único que dispara na prática.
- **Gatilho 2** (âncora fora da faixa `[preco_min, preco_max]` da janela) só pode ocorrer se o preço se moveu — e se ele se moveu mais de 1 tick, o gatilho 1 já disparou antes. É quase sempre redundante.
- **Gatilho 3** (janela vazia) exige um buraco de **≥ 5 segundos sem nenhum trade**. No WDO líquido em pregão isso é praticamente inatingível.

Resultado líquido: **enquanto o preço ficar cravado dentro de `deslocamento_maximo_ticks`, o detector emite exatamente UM alerta — por mais absorções sucessivas e por mais players distintos que passem por ali.** A R1 mediu 98,2% de falso positivo; o conserto trocou por um falso negativo quase total **no exato regime em que o detector existe para operar** (preço parado = regime de absorção). O `PENDENTE(config)` na docstring (linhas 108-112) reconhece que `volume_minimo` absoluto não filtra nada — mas o defeito acima não é de limiar, é da regra de rearme.

---

# PARTE B — 33 mutações novas em território não coberto

**20 sobreviveram (61%).** A R1 teve 36%.

| # | Arquivo:linha | Mutação | Resultado | Teste que pega |
|---|---|---|---|---|
| N01 | `dados/replay.py:109` | sort perde o desempate `(ts, origem, índice)` | 🟢 **SOBREVIVEU** | — |
| N02 | `dados/replay.py:20-21` | no empate de ts, DELTA vem antes de TRADE | ☠️ MORTA | 1 falha |
| N03 | `dados/replay.py:34-35` | `buyer_broker`/`seller_broker` trocados na leitura do CSV | 🟢 **SOBREVIVEU** | — |
| N04 | `dados/simulador.py:99-102` | agressão de COMPRA empurra o preço para BAIXO | 🟢 **SOBREVIVEU** | — |
| N05 | `dados/simulador.py:92` | regime de absorção desligado (preço sempre desloca) | 🟢 **SOBREVIVEU** | — |
| N06 | `dados/mt5.py:284` | bids ordenados do PIOR para o melhor | 🟢 **SOBREVIVEU** | — |
| N07 | `dados/mt5.py:258-259` | flags `TICK_FLAG_BUY`/`SELL` trocadas | ☠️ MORTA | 3 falhas |
| N08 | `dados/leitor_gravacao.py:130` | filtro de horário nunca exclui nada | 🟢 **SOBREVIVEU** | — |
| N09 | `dados/leitor_gravacao.py:97` | hash divergente não levanta `IntegridadeInvalidaError` | 🟢 **SOBREVIVEU** | — |
| N10 | `dados/leitor_gravacao.py:144` | sort perde o desempate por tipo/índice | 🟢 **SOBREVIVEU** | — |
| N11 | `gravacao/formato.py:60` | `decodificar_niveis` devolve os níveis INVERTIDOS | 🟢 **SOBREVIVEU** | — |
| N12 | `gravacao/formato.py:31` | `SCHEMA_VERSAO` 1 → 99 | 🟢 **SOBREVIVEU** | — |
| N13 | `gravacao/gravador.py:138` | hasher deixa de acumular linhas | ☠️ MORTA | 1 falha |
| N14 | `gravacao/gravador.py:185-186` | `meta.json` grava `hora_inicio`=MAX e `hora_fim`=MIN | 🟢 **SOBREVIVEU** | — |
| N15 | `gravacao/gravador.py:143` | `fsync` nunca forçado, nem em `FalhaCaptura` | 🟢 **SOBREVIVEU** | — |
| N16 | `gravacao/catalogo.py:113` | `verificar_integridade` aprova qualquer arquivo | 🟢 **SOBREVIVEU** | — |
| N17 | `gravacao/catalogo.py:98` | `consultar_intervalo` usa `hora_inicio` como `hora_fim` | 🟢 **SOBREVIVEU** | — |
| N18 | `motor/sinais.py:62` | `dominancia_minima` 0.70 → 0.0 | 🟢 **SOBREVIVEU** | — |
| N19 | `motor/sinais.py:115-117` | direção dominante INVERTIDA (compra vira venda) | ☠️ MORTA | 4 falhas |
| N20 | `motor/sinais.py:130` | condição 2 (região de interesse) sempre verdadeira | ☠️ MORTA | 1 falha |
| N21 | `motor/sinais.py:148` | condição 3 (virada da micro) INVERTIDA | ☠️ MORTA | 3 falhas |
| N22 | `motor/sinais.py:65` | janela da micro 15s → 1 dia | 🟢 **SOBREVIVEU** | — |
| N23 | `microestrutura/inferencia_mbp.py:330` | queda casa com negócio de QUALQUER preço | 🟢 **SOBREVIVEU** | — |
| N24 | `microestrutura/inferencia_mbp.py:323-326` | lado passivo invertido (compra consome o BID) | 🟢 **SOBREVIVEU** | — |
| N25 | `microestrutura/inferencia_mbp.py:118` | confiança de cancelamento no topo 0.55 → 1.0 | 🟢 **SOBREVIVEU** | — |
| N26 | `microestrutura/inferencia_mbp.py:252-253` | pendência expirada nunca vira cancelamento | 🟢 **SOBREVIVEU** | — |
| N27 | `analytics/brokers.py:93` | preço médio soma preço sem ponderar por qty | ☠️ MORTA | 1 falha |
| N28 | `analytics/brokers.py:114` | janela expira o trade mas não devolve o volume | ☠️ MORTA | 1 falha |
| N29 | `core/estado_mercado.py:273` | **onda 4:** `iniciar_nova_sessao` não zera a sessão | ☠️ MORTA | 1 falha |
| N30 | `microestrutura/livro_mbo.py:209` | **onda 4:** `esta_cruzado` não conta livro TRAVADO (`bid == ask`) | ☠️ MORTA | 1 falha |
| N31 | `microestrutura/livro_mbo.py:218-219` | **onda 4:** contador de cruzamento conta por evento, não por transição | ☠️ MORTA | 1 falha |
| N32 | `core/estado_mercado.py:240` | **onda 4:** volume não atribuído do candle nunca é contado | ☠️ MORTA | 3 falhas |
| N33 | `analytics/volume_profile.py:80` | **onda 4:** volume não atribuído some do total do nível | ☠️ MORTA | 1 falha |

## Leitura da tabela

**As adições da onda 4 estão bem cobertas — 5 de 5 mortas** (N29–N33). `iniciar_nova_sessao`, `esta_cruzado` (incluindo a distinção travado×cruzado e a contagem por transição) e os contadores de volume não atribuído têm teste de contrato de verdade. Onde a onda 4 mexeu, ela testou.

**A camada de persistência é um buraco maior que o `livro_mbo.py` era.** 9 de 12 mutações em `gravacao/` + `leitor_gravacao` + `catalogo` sobreviveram. Duas são graves de forma qualitativa:

- **N16 + N09 juntas** — `Catalogo.verificar_integridade` pode aprovar qualquer arquivo (`resultado[nome] = True`) **e** `AdaptadorLeitorGravacao._checar_integridade` pode deixar de levantar exceção, e as duas coisas somadas não movem um teste. O `sha256` por arquivo é a única defesa contra gravação truncada, editada à mão ou corrompida em transporte — que é literalmente a razão de o `meta.json` guardar hash. **A cadeia de integridade inteira pode ser desligada com a suíte verde.**
- **N08** — o recorte de horário (`_dentro_do_intervalo`) pode virar `return True` e nada percebe. É exatamente o caso de uso que a docstring do módulo anuncia: *"me dá o replay do WDO de 2026-08-20 das 09:00 às 10:30"*. O produto entregaria o dia inteiro e o operador acharia que está vendo a janela pedida.
- **N12** — `SCHEMA_VERSAO` pode ir para 99. É o campo cuja função declarada (`formato.py:13`) é detectar incompatibilidade de esquema entre gravação e leitura.
- **N01 e N10** — o desempate determinístico do sort some **nos dois** adaptadores, apesar de existir um `tests/test_replay_determinismo.py`. O teste prova que a mesma entrada produz a mesma saída **numa execução**; não prova que a ordem no empate de timestamp é a documentada (`replay.py:56-58`: *"trades entregues antes de deltas"*). N02 morre porque inverte a constante; N01 sobrevive porque remove a garantia sem inverter nada — e é essa a forma que um refactor real assume.

**`inferencia_mbp.py`: 4 de 4 sobreviveram — o arquivo tem zero testes.** Confirmado por busca: nenhum arquivo em `tests/` menciona `inferencia_mbp`, e nenhum módulo de produção importa `InferidorMBP`. São 476 linhas que hoje não são exercitadas por nada.
- **N24** inverte o lado passivo — a regra mais básica do módulo (agressão de compra consome o ASK). Toda atribuição execução×cancelamento sai espelhada.
- **N23** faz uma queda de quantidade casar com negócio de **qualquer preço**: execução atribuída ao nível errado, silenciosamente.
- **N25** eleva `confianca_cancelamento_no_topo` de 0.55 para 1.0. O cabeçalho do arquivo (linhas 26-41) dedica quinze linhas a explicar por que um cancelamento inferido no topo é a hipótese **mais fraca** do módulo. Nenhum teste prende esse número — nem M27b prende `CONFIANCA_OBSERVADO`. **A distinção observado×inferido, que é o valor honesto deste projeto, não tem uma única asserção sustentando.**

**`motor/sinais.py`: 3 mortas, 2 sobreviveram** — mas as que morrem são as inversões grosseiras (N19, N21) e a que apaga uma condição (N20). **N18 sobrevive: `dominancia_minima` pode ir a 0.0** e os 6 testes passam, porque todos injetam config própria (`tests/test_motor_sinais.py:18`) e nenhum exerce o default de fábrica. **N22 sobrevive: a "micro" pode virar uma janela de 1 dia** — deixando de ser micro, que é a definição da condição 3.

---

# PARTE C — ataque ao motor de sinais

## C.1 O que NÃO está testado nas 6 asserções

Os 6 testes cobrem: sem dominância → `NENHUM`; dominância fora da região → `DIRECAO_CONFIRMADA`; confluência completa → `CONFIRMADO`; um caso de `PRE_SINAL`; `estagio_atual`; símbolo alheio ignorado. **É um teste por transição do enum, uma vez cada.** Fora de cobertura:

- **Qualquer default de fábrica.** Todos os testes injetam `ConfigMotorSinais(...)` próprio (N18 e N22 sobreviveram por isso).
- **Comportamento no limiar exato.** `dominancia < self.config.dominancia_minima` (linha 174) — nenhum teste com dominância exatamente 0.70.
- **Expiração das duas janelas.** Nenhum teste faz trades saírem de `_trades_dominancia` ou `_trades_micro` por tempo.
- **`AgressorSide.UNKNOWN`.** `_dominancia` (110-111) simplesmente não conta UNKNOWN em lado nenhum, e `_micro_virou` (139-144) soma `0`. Leilão de abertura e RLP viram invisíveis para o motor, sem contador, sem evidência. É o defeito 4.4 da R1 reaparecendo num módulo que a onda 4 não visitou — enquanto `estado_mercado`, `volume_profile` e `agressao` ganharam `volume_nao_atribuido`, o motor de sinais não ganhou.
- **Persistência / histerese.** Nenhum teste, e nenhum código (ver C.4).
- **`total == 0`** devolve `(0.5, None)` (linha 114) — sem teste.
- **Custo.** Nenhum teste ou benchmark do builder toca o motor.

## C.2 É o mesmo defeito quadrático da R1? **É, e pior.**

Medido e apresentado na seção "ÚNICO MAIOR GAP": fatores de x4,64 / x4,31 / x3,16 / x4,38 ao dobrar N, 67,9 milhões de avaliações de genexpr para 8.000 trades, e a janela é 60x maior que a do detector que a R1 condenou. **Sim, é o mesmo defeito, na mesma forma sintática, com o parâmetro pior.**

## C.3 `_na_regiao` é O(n log n) no caminho quente? **É.**

`val()` → `value_area()` → `sorted()`. `vah()` → `value_area()` → `sorted()` **de novo**. Nenhum cache, nenhuma memoização, nenhum resultado reaproveitado — a mesma `value_area()` é computada duas vezes por trade para extrair `[0]` e depois `[1]` da mesma tupla. Além do `sorted()`, cada chamada faz `self.poc` (um `min` sobre todos os níveis), `precos_ordenados.index(poc)` (varredura linear) e a expansão gulosa até 70% do volume. Números na tabela do gap: **a barra cai a partir de ~120 níveis de preço distintos**, e um pregão de WDO cobre centenas.

Custo real a 10k ev/s: com 800 níveis (sessão normal), `val()+vah()` sozinhos custam 969,6 µs/trade — teto de **1.031 trades/s**, 10x abaixo da barra, antes de somar qualquer outra coisa.

## C.4 A lógica de `pre_sinal` é defensável? **Não — o rótulo é falso.**

```python
primeira_metade = self._trades_micro[: max(1, int(len(self._trades_micro) * marco))]   # 151
delta_inicio = sum(...)                                                                 # 153
estava_contra = (delta_inicio <= 0) if alvo_positivo else (delta_inicio >= 0)            # 158
pre_sinal = estava_contra and not virou and delta_micro != 0                             # 159
```

`delta_inicio` é calculado e usado **só** em `estava_contra`. **Ele nunca é comparado com a segunda metade.** Não existe no predicado nenhuma noção de melhora. Medido (direção pretendida BUY, primeira metade sempre −100):

| segunda metade | leitura correta | o que o motor diz |
|---|---|---|
| −100 (micro parada) | nada mudou | `PRE_SINAL` |
| −20 (micro melhorando) | começando a virar | `PRE_SINAL` |
| **−400 (micro piorando 4x contra)** | **fuja** | **`PRE_SINAL`** |

`EstagioSinal.PRE_SINAL` está documentado (`sinais.py:43`) como *"1 + 2, micro começando a virar"* e a config chama isso de *"farol amarelo"* (linha 59). **Um mercado acelerando contra a posição recebe o mesmo farol amarelo que um mercado revertendo a favor.** Além disso `primeira_metade` é fatiada por **contagem de trades**, não por tempo — num tape em rajada a "primeira metade" pode cobrir 9 dos 15 segundos ou 0,2 deles.

## C.5 As faixas de convicção da fonte — **não implementadas**

`pesquisa/metodologia_regras.md:30-36` consolida a metodologia numa tabela de quatro faixas:

| faixa | leitura (fonte) |
|---|---|
| 50% | empate / lateral |
| 50–65% | pré-direcional |
| ≥70–75% | direcional (zona de operação a favor) |
| ≥80–85% | máxima convicção |

**O motor implementa um único corte binário** (`dominancia < dominancia_minima` → `NENHUM`; caso contrário → direção confirmada). Não existem as faixas 50–65 nem ≥80–85. Consequências concretas:

- **A faixa de máxima convicção não existe.** Dominância 0,71 e dominância 0,95 produzem exatamente o mesmo `EstagioSinal`, e a `evidencia` carrega só o número cru. A fonte trata 80-85% como categoricamente diferente (*"não tem nem o que pensar"*, `metodologia_regras.md:27`).
- **Colisão de nome.** A fonte chama 50–65% de **"pré-direcional"**. O motor tem um estágio chamado **`PRE_SINAL`** que significa outra coisa inteiramente (micro parcialmente virada, condições 1 e 2 já satisfeitas). Quem cruzar o código com a metodologia vai ler um pelo outro.
- **A divergência 70 × 75 NÃO está tratada.** `metodologia_regras.md:27` registra explicitamente o conflito: um vídeo diz *"acima de 75% já é uma amostragem mais direcional"*, outro diz *"acima de 70% direcional"*, e a nota marca **IMPRECISO**. O docstring do motor (`sinais.py:8`) diz apenas *"a fonte usa ~70%"* e o comentário da config (linha 54) repete *"a fonte cita ~0.70"*. **Escolheu-se um dos dois números e a existência do outro foi omitida** — num projeto cuja virtude documentada é justamente separar o que é observado do que é hipótese. O valor 0.70 está dentro da faixa e é defensável; a omissão da divergência não é.

## C.6 O modo de falha WINFUT — **o motor cai nele inteiro**

`pesquisa/ferramenta_componentes.md:105` descreve o modo de falha e o que seria a leitura correta:

> *"a leitura correta exige normalizar por (a) magnitude relativa ao histórico intradiário e (b) persistência temporal, não só o sinal instantâneo. (...) um 'contexto macro' ingênuo teria dado sinal de compra falso nesse dia."*

Reproduzi o cenário (`.mut/adversarial.py d`): fase 1 com 90% de agressão vendedora e **magnitude alta** (qty 20); fase 2 com 90% compradora e **magnitude menor** (qty 9) — o análogo do pico +915 contra os −1925 do relato.

```
FASE 1 (10 min, 90% vendedor, magnitude ALTA):
  estagio = CONFIRMADO   direcao = SELL   dominancia = 0.900
FASE 2 (5,3 min, 90% comprador, magnitude MENOR — qty 9 vs 20):
  estagio = CONFIRMADO   direcao = BUY    dominancia = 0.900
```

**O motor inverte a direção do dia e emite `CONFIRMADO` de compra — exatamente o sinal falso que a fonte documenta.** E note: `dominancia = 0.900` nos dois casos, **idêntica**, porque `_dominancia` devolve uma razão dentro da janela corrente, cega ao tamanho absoluto do fluxo. A `evidencia` publicada carrega só `dominancia` — nem um auditor humano lendo a evidência consegue ver que a fase 2 foi metade da magnitude da fase 1.

- **(a) normalização por magnitude relativa ao histórico intradiário:** ausente. `_dominancia` (107-117) só olha a janela de 5 min. Não há memória do dia, nem pico, nem magnitude de referência.
- **(b) persistência temporal:** ausente. A fonte pede explicitamente *"se ele se sustentar acima de 70%"* (`metodologia_regras.md:40`). Prova medida:

```
apos 70 BUY + 30 SELL:  dominancia=0.7000  estagio=CONFIRMADO
+1 unico trade SELL:    dominancia=0.6931  estagio=NENHUM
```

**Um único trade derruba a confluência inteira.** Zero histerese, zero tempo mínimo de sustentação, zero debounce. Num tape de 5.000 trades/s oscilando ao redor do limiar, esse estágio pisca milhares de vezes por segundo. O `EstagioSinal` não é um estado — é uma função pura do último trade.

---

# PARTE D — o que ainda não existe, por impacto

| # | Lacuna | Onde | Por que importa |
|---|---|---|---|
| 1 | **Custo do `MotorSinais`** — deque + contadores incrementais em `_dominancia`/`_micro_virou`; `value_area` com cache invalidado por escrita (ou VAH/VAL incrementais) | `motor/sinais.py:109,135,125-126` | 258 ev/s contra barra de 10.000. Bloqueia tudo. |
| 2 | **Persistência e normalização por magnitude no motor** — histerese no limiar, tempo mínimo de sustentação, magnitude relativa ao histórico do dia | `motor/sinais.py:107-117,164-198` | É o modo de falha que a própria pesquisa do projeto documenta (C.6). Sem isto o sinal é ruído com nome de sinal. |
| 3 | **Testes de `inferencia_mbp.py`** (476 linhas, 0 testes, 4/4 mutações vivas) | `microestrutura/inferencia_mbp.py` | É a única ponte para o feed que existe hoje (MT5/MBP). Sem MBO real, todo detector roda em cima dela. |
| 4 | **Testes da cadeia de integridade da gravação** (hash, `SCHEMA_VERSAO`, recorte de horário, ordem determinística) | `gravacao/catalogo.py:113`, `dados/leitor_gravacao.py:97,130,144`, `gravacao/formato.py:31` | 9/12 mutações vivas. Replay é a base de backtest e de auditoria; se ele mente, tudo a jusante mente. |
| 5 | **Sequence number + detecção de gap de feed** | `core/eventos.py` — **ainda inexistente** (verificado: nenhum campo de sequência em `Trade`/`BookDelta`/`BookSnapshot`/`formato.py`) | Item 6 do backlog da R1, não endereçado. Livro reconstruído de deltas sem detecção de gap apresenta estado errado como certo. |
| 6 | **Regra de rearme do `DetectorAbsorcao`** — episódio por volume/tempo, não por deslocamento de preço | `detectores.py:155-166,205-216` | Hoje um pregão inteiro de absorção no mesmo preço rende 1 alerta (A.4). |
| 7 | **Livro cruzado e estado "não sincronizado" em `EstadoMercado`** | `core/estado_mercado.py` — `esta_cruzado` foi para o `LivroMBO` e **não** para o `EstadoMercado` (verificado: nenhuma menção fora de um comentário em `:269`) | Achados 4.1 e 4.3 da R1, metade resolvidos. O `EstadoMercado` é o que alimenta analytics. |
| 8 | **`FonteMicro`/confiança propagada nos detectores** | `detectores.py:7,20` — `FonteMicro` continua importado e **nunca usado**; todos os 6 `confianca=1.0` | Achado 5.6 da R1, intocado. A docstring continua prometendo propagação que não existe. |
| 9 | **`UNKNOWN` no motor de sinais** | `motor/sinais.py:110-111,139-144` | A onda 4 fechou isso em `estado_mercado`, `volume_profile` e `agressao`, e esqueceu o motor. |
| 10 | **`qty_minima_imbalance` default > 0** | `analytics/footprint.py:57` — ainda `= 0` | Achado 5.4 da R1, intocado. A proteção continua desarmada de fábrica. |
| 11 | **M06 / M09 / M27b** — testes de `round`×`int` no `PriceGrid`, retrocesso do relógio, e `CONFIANCA_OBSERVADO` | `core/eventos.py:50`, `core/relogio.py:39`, `eventos_mbo.py:34` | Dívida pequena, mas alegada como resolvida e não está. |

---

# O que ainda impede uso com dinheiro real (mesmo depois do gap #1)

Registro à parte, porque não é falha de execução e nenhuma otimização resolve:

- **O `MotorSinais` nunca foi ligado a nada.** Não é instanciado por nenhum módulo de produção nem por nenhum benchmark — só pelos próprios testes. Não existe aplicação, wiring, UI ou saída. O produto ainda não foi montado.
- **`InferidorMBP` também não é importado por ninguém**, então o caminho MBP→MBO — o único disponível sem UMDF/ProfitDLL — nunca rodou ponta a ponta.
- **Nenhum backtest contra tape real.** Toda medição de qualidade de sinal neste projeto (R1 e R2 inclusive) foi feita sobre `SimuladorWDO`, cujas próprias dinâmicas de preço podem ser invertidas sem quebrar teste nenhum (N04, N05). Nada aqui foi confrontado com um pregão gravado.
- **`RankingCorretoras` pode ser inaplicável ao instrumento-alvo** — a B3 anonimiza corretora em WDO/WIN (registrado na própria `PROGRESSO.md`). Decisão de produto pendente desde a R1.

---

*Working tree verificado limpo: `git status --short` devolve só `?? .mut/`; `git diff --stat -- fluxopro/` vazio; suíte re-executada — 193 passed. As 45 mutações (12 re-aplicadas + 33 novas) foram revertidas uma a uma pelo `finally` do harness. Material de reprodução em `.mut/`: `harness.py` (motor de mutação), `r1.json`/`r2.json` (tabelas), `bench_r2.py` (pipeline completo, `python .mut/bench_r2.py`), `adversarial.py` (sondas A–D, `python .mut/adversarial.py {a|b|c|d}`). Nenhum arquivo de produção foi alterado por esta revisão.*
