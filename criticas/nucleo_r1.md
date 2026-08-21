# Crítica adversarial R1 — núcleo do FluxoPro

**Data:** 2026-08-21 · **Escopo:** `fluxopro/{core,analytics,microestrutura,motor}` + `tests/`
**Barra:** leitura de fluxo tick-a-tick do WDO em tempo real, picos de 5–10 mil eventos/s, comparável ao Profit Pro (`bar/barra_profit_pro.md`).
**Método:** execução real — suíte, 33 mutações em código de produção, benchmark de 500 mil eventos, cProfile, 12 sondas de microestrutura.

---

# VEREDITO: **NÃO PASSA**

O pipeline de núcleo + analytics passa com folga (55.612 ev/s medidos, barra 10.000). **Os detectores de microestrutura — que são o produto — entregam 42 trades/s onde a barra pede 10.000.** É 236x lento demais, e não é constante-de-proporcionalidade: é custo quadrático que piora conforme o mercado acelera. O mesmo detector dispara em **98,2% dos trades** num tape lateral normal.

Somado a isso: **`livro_mbo.py` (606 linhas, o arquivo mais intrincado do projeto) não tem um único teste direto.** Inverti o FIFO para LIFO — a regra de prioridade de fila que É o diferencial do produto — e os 94 testes passaram.

A barra **não** estava baixa. A suíte é que estava olhando para o lado errado.

---

## ÚNICO MAIOR GAP

### `fluxopro/microestrutura/detectores.py:72` — `DetectorAbsorcao.ao_trade`

```python
self._trades.append(trade)
limite = trade.timestamp_ns - cfg.janela_ns
self._trades = [t for t in self._trades if t.timestamp_ns >= limite]   # <-- LINHA 72

precos = [t.price for t in self._trades]                               # linha 74
deslocamento = max(precos) - min(precos)                               # linha 75
...
volume_buy  = sum(t.qty for t in self._trades if ...)                  # linha 79
volume_sell = sum(t.qty for t in self._trades if ...)                  # linha 80
```

Cinco varreduras completas da janela **por trade**. A janela é de 5 segundos: a 5.000 trades/s ela guarda 25.000 trades; a 10.000 trades/s, 50.000. O custo por trade cresce linearmente com a taxa do mercado, então o custo total cresce **quadraticamente** — o sistema fica mais lento exatamente quando o mercado fica mais interessante.

Não é um gargalo entre outros. No cProfile do pipeline completo, esta única função consome **3,92s de 6,71s (58% do tempo próprio, 79% do cumulativo)** para meros 10.000 trades. E o mesmo módulo `agressao.py` já resolve esse problema corretamente, na mesma janela deslizante, com `deque` + contadores incrementais O(1) — a solução existe no repositório, dez arquivos ao lado, e não foi aplicada aqui.

**Conserto:** `deque` com `popleft` por expiração + `volume_buy`/`volume_sell` como contadores incrementais + duas *monotonic deques* para `max(precos)`/`min(precos)`. Tudo O(1) amortizado. `DetectorExaustao` e `DetectorClipInstitucional` já usam janela por contagem e não têm o problema — só o Absorção.

---

## 1. Suíte de testes — saída literal

```
$ python -m pytest tests/ -q
........................................................................ [ 76%]
......................                                                   [100%]
94 passed in 1.01s
```

Verde, rápida, determinística. E, como o item 2 mostra, cega justamente onde o produto vive.

---

## 2. Teste de mutação — 33 defeitos deliberados

**12 de 33 sobreviveram (36%).** Working tree confirmado limpo ao final (`git diff --stat fluxopro/` vazio; suíte re-rodada: 94 passed).

### Tabela de sobrevivência

| # | Arquivo | Mutação | Resultado | Teste que pegou |
|---|---|---|---|---|
| M01 | core/estado_mercado.py | `BookDelta` de compra vai para o lado de venda | ☠️ MORTA | `test_snapshot_seguido_de_deltas_reconstroi_book_esperado` |
| M02 | core/estado_mercado.py | `max`→`min` no high do candle | ☠️ MORTA | `test_candle_ohlcv_e_delta` |
| M03 | core/estado_mercado.py | sinal do delta do candle invertido | ☠️ MORTA | `test_candle_ohlcv_e_delta` |
| M04 | core/estado_mercado.py | VWAP de sessão deixa de ponderar por qty | ☠️ MORTA | `test_vwap_e_high_low_de_sessao` |
| M05 | core/eventos.py | tolerância do PriceGrid afrouxada 10¹²x | ☠️ MORTA | `test_preco_desalinhado_levanta_erro` |
| **M06** | **core/eventos.py** | **`round()`→`int()` no PriceGrid (trunca)** | **🟢 SOBREVIVEU** | — |
| M07 | core/barramento.py | remove a ordenação por prioridade | ☠️ MORTA | `test_ordem_por_prioridade_e_inscricao` |
| M08 | core/barramento.py | prioridade invertida (maior primeiro) | ☠️ MORTA | `test_ordem_por_prioridade_e_inscricao` |
| **M09** | **core/relogio.py** | **`RelogioReplay` aceita retroceder no tempo** | **🟢 SOBREVIVEU** | — |
| M10 | analytics/delta.py | agressão vendedora soma em vez de subtrair | ☠️ MORTA | `test_delta_acumulado_de_sessao` |
| M11 | analytics/delta.py | `max`→`min` no delta_maximo intra-candle | ☠️ MORTA | `test_delta_maximo_e_minimo_intra_candle_revelam_reversao` |
| M12 | analytics/delta.py | divergência vira convergência (lógica invertida) | ☠️ MORTA | `test_delta_divergente_preco_sobe_delta_acumulado_cai` |
| M13 | analytics/volume_profile.py | comprador e vendedor trocados | ☠️ MORTA | `test_volume_total_e_niveis_separados_por_agressor` |
| M14 | analytics/volume_profile.py | POC vira o nível de MENOR volume | ☠️ MORTA | `test_poc_e_o_nivel_de_maior_volume` |
| **M15** | **analytics/volume_profile.py** | **`>=`→`>` no limiar de HVN** | **🟢 SOBREVIVEU** | — |
| M16 | analytics/footprint.py | imbalance deixa de ser diagonal | ☠️ MORTA | `test_imbalance_diagonal_no_limiar_exato_e_abaixo_dele` |
| M17 | analytics/footprint.py | `>=`→`>` no limiar de imbalance | ☠️ MORTA | `test_imbalance_diagonal_no_limiar_exato_e_abaixo_dele` |
| M18 | analytics/agressao.py | saldo de agressão com sinal invertido | ☠️ MORTA | `test_saldo_taxa_e_velocidade_sem_expiracao` |
| **M19** | **analytics/agressao.py** | **`>`→`>=` na expiração da janela** | **🟢 SOBREVIVEU** | — |
| M20 | analytics/vwap.py | soma de preço² vira soma de preço | ☠️ MORTA | `test_vwap_de_sessao_e_bandas` |
| M21 | analytics/brokers.py | saldo líquido vira volume total | ☠️ MORTA | `test_agregacao_por_corretora_volume_saldo_e_preco_medio` |
| **M22** | **microestrutura/livro_mbo.py** | **fila FIFO vira LIFO (`fila[0]`→`fila[-1]`)** | **🟢 SOBREVIVEU** | — |
| **M23** | **microestrutura/livro_mbo.py** | **`popleft()`→`pop()` ao zerar a ordem** | **🟢 SOBREVIVEU** | — |
| **M24** | **microestrutura/livro_mbo.py** | **janela de reposição 1000x maior** | **🟢 SOBREVIVEU** | — |
| **M25** | **microestrutura/livro_mbo.py** | **`melhor_bid()` devolve o PIOR bid** | **🟢 SOBREVIVEU** | — |
| **M26** | **microestrutura/livro_mbo.py** | **`qty_a_frente` SOMA o consumo em vez de descontar** | **🟢 SOBREVIVEU** | — |
| **M27** | **microestrutura/detectores.py** | **confiança do Iceberg-proxy 0.6 → 1.0** | **🟢 SOBREVIVEU** | — |
| **M28** | **microestrutura/detectores.py** | **`>=`→`>` no `volume_minimo` da Absorção** | **🟢 SOBREVIVEU** | — |
| M29 | microestrutura/detectores.py | `<`→`<=` no mínimo de reposições da Escora | ☠️ MORTA | `test_escora_dispara_apos_n_reposicoes` |
| **M30** | **microestrutura/detectores.py** | **IcebergPorRecarga deixa de exigir recarga observada** | **🟢 SOBREVIVEU** | — |
| M31 | microestrutura/detectores.py | Exaustão passa a exigir progresso de preço | ☠️ MORTA | `test_exaustao_detecta_volume_decrescente_sem_progresso` |
| M32 | microestrutura/detectores.py | Clip: `and` vira `or` | ☠️ MORTA | `test_clip_institucional_nao_dispara_com_tamanhos_irregulares` |
| M33 | microestrutura/detectores.py | LiquidezFantasma aceita ordem que já executou | ☠️ MORTA | `test_liquidez_fantasma_nao_dispara_se_executou_algo` |

### Leitura da tabela

**`core/` e `analytics/` estão genuinamente cobertos.** 18 de 21 mutações morreram, incluindo as difíceis (imbalance diagonal, delta divergente, ordenação do barramento, POC). Os testes ali são contrato de verdade, não teatro. Três limiares de fronteira `>=`/`>` escaparam (M15, M19) — dívida menor, não estrutural.

**`microestrutura/livro_mbo.py` é um buraco de 606 linhas.** As 5 mutações que plantei ali sobreviveram todas. O arquivo é importado por `test_micro_detectores.py` apenas como *fixture* para montar cenário dos detectores; nenhum teste afirma nada sobre o comportamento dele. Consequências concretas:

- **M22 (FIFO→LIFO)** é a pior. A prioridade preço-tempo é a razão de existir de um livro MBO — é o que `qty_a_frente`, `DetectorEscora` e toda a leitura de "quem está na frente" dependem. Inverter isso não quebra nada visível.
- **M25 (`melhor_bid` vira o pior bid)** passa despercebida. Todo cálculo de spread, topo de livro e proximidade (`DetectorLiquidezFantasma.ticks_proximidade`) sai errado em silêncio.
- **M26** corrompe `qty_a_frente`, cuja docstring explica com cuidado que é uma cota superior — e nenhum teste verifica se é sequer uma cota.

**Os dois detectores de Iceberg estão descobertos onde importa.** M27 (confiança 0.6→1.0) sobreviveu: o `0.6` é a única coisa que impede uma hipótese de ser apresentada como fato observado, e o módulo inteiro é construído em torno dessa distinção (`FonteMicro.MBO` vs `MBP_INFERIDO`, docstring linhas 5–7). Nenhum teste prende esse número. M30 sobreviveu: `DetectorIcebergPorRecarga` pode parar de exigir a recarga observada — a única coisa que o distingue do proxy — e os dois testes que ele tem continuam passando.

---

## 3. Benchmark de carga — `bench_carga.py`

500 mil eventos (250k trades + 250k book snapshots) via `SimuladorWDO`, **a 5.000 trades/s simulados** (o default de fábrica do simulador é 5 ev/s, que esvazia as janelas deslizantes de 5s e esconde o custo real delas — medir com ele seria auto-engano).

### Estágios cumulativos

| Estágio | Tempo | Eventos/s | µs/evento | Veredito |
|---|---|---|---|---|
| 1. barramento vazio (piso do simulador) | 4,68s | **106.934** | 9,35 | PASSA |
| 2. + `EstadoMercado` | 8,16s | **61.280** | 16,32 | PASSA |
| 3. + analytics (6 módulos) | 8,99s | **55.612** | 17,98 | PASSA |
| 4. + detectores | — | **42–1.587** | 630–23.583 | **NÃO PASSA** |

O estágio 1 inclui a geração pelo simulador (9,35 µs/ev), que é o piso da medição. Descontando-o, **o lado consumidor de núcleo + analytics custa ~8,6 µs/evento — cerca de 116.000 ev/s**, folga de 11x sobre a barra. Essa parte está sólida.

### Memória

| Métrica | Valor |
|---|---|
| Pico (pipeline estágio 3, 500k eventos) | **2,5 MB** |
| Residente ao final | ~0,0 MB |
| Por evento | 5,2 bytes |

Excelente. Nenhum vazamento, nenhum acúmulo descontrolado no caminho de analytics.

### O gargalo, isolado (`DetectorAbsorcao`, janela de 5s cheia)

| Taxa do mercado | Janela guarda | µs/trade | Capacidade real | Veredito |
|---|---|---|---|---|
| 500 trades/s | 2.500 | 1.319 | 758/s | PASSA (raspando) |
| 1.000 trades/s | 5.000 | 4.553 | 220/s | NÃO PASSA — 4,6x lento |
| 2.000 trades/s | 10.000 | 4.687 | 213/s | NÃO PASSA — 9,4x lento |
| 4.000 trades/s | 20.000 | 9.732 | 103/s | NÃO PASSA — 38,9x lento |
| 8.000 trades/s | 40.000 | 18.923 | 53/s | NÃO PASSA — 151x lento |
| **10.000 trades/s** | **50.000** | **23.584** | **42/s** | **NÃO PASSA — 236x lento** |

O déficit **multiplica** conforme a taxa sobe (4,6x → 236x). É a assinatura de custo quadrático, não de constante ruim. Otimização micro não salva isto; só a troca de estrutura de dados.

### cProfile — top 10 por tempo próprio (pipeline completo, 10k trades)

```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
    10000    3.918    0.000    5.278    0.001 microestrutura/detectores.py:66(ao_trade)   <-- DetectorAbsorcao
    61458    0.695    0.000    0.695    0.000 {built-in method builtins.max}
    49998    0.678    0.000    0.678    0.000 {built-in method builtins.min}
   201131    0.149    0.000    0.393    0.000 random.py:335(randint)
    20000    0.134    0.000    5.926    0.000 core/barramento.py:48(publicar)
   201131    0.119    0.000    0.194    0.000 random.py:245(_randbelow_with_getrandbits)
    60000    0.077    0.000    0.296    0.000 dados/simulador.py:111(<genexpr>)
    10000    0.070    0.000    6.712    0.001 dados/simulador.py:61(_passo)
    60000    0.068    0.000    0.270    0.000 dados/simulador.py:119(<genexpr>)
    10000    0.062    0.000    0.177    0.000 microestrutura/detectores.py:391(ao_trade)
```

Um único `ao_trade` = 58% do tempo próprio. `max` e `min` (posições 2 e 3) são majoritariamente as chamadas da linha 75 do mesmo detector. Nada mais no sistema chega perto.

### Custo escondido pelo simulador

`SimuladorWDO` nunca preenche `buyer_broker`/`seller_broker`, então `RankingCorretoras` sai pela porta dos fundos em toda chamada e o benchmark **subestima** o pipeline real:

| Cenário | µs/trade | trades/s |
|---|---|---|
| broker vazio (como o simulador) | 0,23 | 4.271.624 |
| broker preenchido (como a B3) | 1,01 | 985.657 |

**4,4x mais caro** com dado realista. Ainda passa com folga, mas o número do estágio 3 é otimista. (Nota lateral: `bar/barra_profit_pro.md` e a própria `PROGRESSO.md` registram que a B3 anonimiza corretora em WDO/WIN por design — então o Ranking de Corretoras pode ser inaplicável ao instrumento-alvo. Fora do meu escopo, mas vale a decisão de produto.)

---

## 4. Caça a defeito de microestrutura

Cada item abaixo foi **executado**, não deduzido.

### 4.1 🔴 Livro cruzado (bid ≥ ask) aceito em silêncio — `core/estado_mercado.py:99-106`

```
snapshot: bid 10000 / ask 10001
BookDelta: UPDATE bid @ 10005
resultado: melhor bid = 10005 | melhor ask = 10001 | CRUZADO = True
```

`_ao_delta` grava direto no dicionário do lado, sem olhar o lado oposto. Sem exceção, sem flag, sem log, sem contador. Um livro cruzado envenena spread, mid-price, `DetectorLiquidezFantasma.ticks_proximidade` e toda a leitura de topo — e nada no sistema sabe que está envenenado. **`LivroMBO` tem exatamente o mesmo furo** (`_obter_nivel` não valida contra o heap oposto).

### 4.2 🔴 Nenhum sequence number — gap de feed é indetectável

```
campos de Trade + BookDelta + BookSnapshot:
['action','asks','bids','buyer_broker','position','price','qty','seller_broker',
 'side','side_agressor','symbol','timestamp_ns','trade_id']
campo de sequência: NENHUM
```

Se o feed pular eventos — reconexão, perda de UDP no UMDF, throttle — o sistema **reconstrói um livro errado e o apresenta como certo**. Não há como detectar, nem como pedir snapshot de recuperação. Para um produto que reconstrói estado incremental a partir de deltas, isto é infraestrutura ausente, não refinamento. (`gravacao/formato.py` merece checagem separada quanto a isso.)

### 4.3 🟠 `BookDelta` antes do primeiro snapshot → livro fantasma

```
BookDelta UPDATE bid @10000 qty 40, sem snapshot anterior
resultado: bids=[(10000, 40)] asks=[]
```

Livro de um lado só, tratado como estado válido e legítimo. Não existe estado "ainda não sincronizei" — nem em `EstadoMercado`, nem em `LivroMBO`. Na conexão ao vivo, é exatamente o que acontece nos primeiros milissegundos, e os detectores começam a ler dali.

### 4.4 🟠 Volume e delta ficam inconsistentes com agressor `UNKNOWN`

```
3 trades de 100 lotes, side_agressor = UNKNOWN
  delta_sessao        = 0     (some do delta)
  saldo_agressao      = 0     (some da agressão)
  volume_total_sessao = 300   (mas CONTA no volume)
  candle.volume = 300 | candle.delta = 0
```

Cada consumidor decide sozinho o que fazer com `UNKNOWN` e todos decidem "ignorar", mas o volume conta. Resultado: `volume ≠ |delta_buy| + |delta_sell|`, sem nenhum contador de "volume não atribuído" que permita ao operador perceber. **É exatamente o caso do leilão de abertura e fechamento** (onde não há agressor por definição) e do RLP. O `AgressorSide.UNKNOWN` existe no enum — o tratamento dele, não.

### 4.5 🟠 Virada de sessão/dia: não existe

| Componente | Método de virada |
|---|---|
| `EstadoMercado` | **NENHUM** |
| `Sessao` (high/low/vwap) | **NENHUM** |
| `VWAP` | **NENHUM** |
| `CumulativeDelta` | **NENHUM** |
| `MedidorAgressao` | **NENHUM** |
| `VolumeProfilePorPeriodo` | `nova_sessao()` ← o único |

`Sessao.high/low`, `CumulativeDelta.delta_sessao` e `VWAP._sessao` acumulam para sempre. O campo se chama `delta_sessao` e a docstring diz "desde o início da sessão", mas nada define o que é uma sessão nem como ela termina. O bucketing por `timeframe_ns` não resolve: pregão do WDO não começa à meia-noite UTC, e ele não trata leilão nem virada de vencimento. Sem processo reiniciado todo dia, o segundo pregão lê números do primeiro.

### 4.6 ✅ Trades com timestamp idêntico — degrada bem

`velocidade_trades_por_segundo()` devolve `0.0` quando a duração da janela é zero (guarda explícita), em vez de dividir por zero ou devolver infinito. `RelogioReplay` aceita o mesmo timestamp repetido e só recusa retroceder. **Correto.** Ressalva: a mutação M09 mostrou que a recusa de retrocesso não tem teste.

### 4.7 ✅ Hipótese REJEITADA — precisão dos acumuladores de volume

Suspeitei de perda de precisão em `_AcumuladorVWAP.soma_preco2_qty`, declarado `float` (`0.0`) enquanto `core/eventos.py` promete que "preços trafegam sempre como `int` ... sem os erros de arredondamento binário". **Testei e a hipótese não se sustenta:**

```
dia inteiro simulado: 600.000 contratos, preço ~10.800 ticks
soma_preco2_qty exato (int)   = 209842482601588
soma_preco2_qty atual (float) = 209842482601588.0
erro absoluto = 0.0 | erro relativo na variância = 0.00e+00%
```

2,1×10¹⁴ cabe folgado nos 2⁵³ ≈ 9,0×10¹⁵ de mantissa do float64 — cada soma é exata. O cancelamento catastrófico existe (E[p²]=116.655.242 menos E[p]²=116.641.849 para sobrar ~13.393) mas sobram dígitos de sobra. **Não é defeito na escala real.** Vira defeito só combinado com 4.5: sem reset de sessão, o acumulador cruza 2⁵³ por volta do 43º pregão contínuo e começa a perder precisão em silêncio. O conserto de 4.5 elimina o risco; trocar `0.0` por `0` (int exato) elimina de vez, por 2 caracteres.

### 4.8 🟡 `PriceGrid` — a tolerância está certa, o teste é que não prende

M06 (`round()`→`int()`) sobreviveu. A tolerância em si é defensável: `|razão − ticks| > 1e-6` é absoluta sobre a razão, o que dá 5×10⁻⁷ em preço no WDO e 5×10⁻⁶ no WIN — escala com o instrumento, como deve. O problema é que nenhum teste distingue arredondar de truncar, então a garantia é acidental.

---

## 5. Revisão dos detectores — `microestrutura/detectores.py`

### 5.1 🔴 `DetectorIceberg` (proxy): a fórmula é inventada

```python
executado_estimado = livro.n_reposicoes(side, price) * exibido_max   # linha 187
razao = executado_estimado / exibido_max if exibido_max else 0.0     # linha 190
```

**É indefensável, e a álgebra prova em uma linha:** `razao = (n_reposicoes × exibido_max) / exibido_max = n_reposicoes`. O `exibido_max` cancela. Medido:

```
exibida_max=   10  n_reposicoes=5  ->  razao=5.0
exibida_max=  500  n_reposicoes=5  ->  razao=5.0
exibida_max=9999  n_reposicoes=3  ->  razao=3.0
```

Três consequências:

1. **A razão não depende do tamanho exibido.** Um nível que mostra 10 lotes e um que mostra 5.000 recebem a mesma razão. A grandeza que o detector afirma medir — "executa muito mais volume do que a quantidade exibida", docstring linha 170 — é a única coisa que a fórmula garantidamente ignora.
2. **`razao_minima=3.0` é, na prática, `n_reposicoes >= 3`** — literalmente o mesmo gatilho do `DetectorEscora` (`n_reposicoes_minimo=3`). Confirmado em execução: a mesma sequência de 4 add+execute no mesmo nível emite **ICEBERG e ESCORA simultaneamente**. Dois rótulos, um fenômeno, e o operador vê "confluência".
3. **`volume_executado_estimado` na evidência nunca observou execução nenhuma.** `n_reposicoes` conta *ordens novas que chegaram depois de o nível ser varrido* (`livro_mbo.py:222-231`) — não conta contratos executados. O campo publica um número fabricado com nome de medição, dentro de um `evidencia` cuja finalidade declarada (docstring linhas 4–6) é permitir auditoria. Aqui a evidência engana o auditor.

Medido: `evidencia = {'qty_exibida_max': 100, 'volume_executado_estimado': 300, 'razao': 3.0, ...}` — nada foi executado além do que foi exibido; o "300" é 3×100.

**O honesto seria** ou (a) rastrear `consumido_acumulado` do nível — que `_NivelInterno` **já mantém** (`livro_mbo.py:84`) e que é a medição verdadeira de volume executado — ou (b) deletar o detector e ficar só com `DetectorIcebergPorRecarga`, que mede o fenômeno de verdade. O comentário nas linhas 183-186 admite a improvisação ("usamos o proxy de ... como sinal auxiliar"), mas a confiança 0.6 e um campo chamado `volume_executado_estimado` não comunicam "este número é o produto de duas grandezas não relacionadas".

### 5.2 🔴 `DetectorAbsorcao` dispara em 98,2% dos trades num tape lateral

Medido — 6.000 trades a 2.000/s, preço oscilando entre 2 ticks, volume normal de WDO, viés vendedor leve, **config de fábrica**:

```
detecções de ABSORÇÃO = 5.889  (98,2% dos trades)
tem dedup (_ja_sinalizado)? False
```

Duas causas somadas:

- **`volume_minimo=300` não filtra nada** na escala real. A 5.000 trades/s com ~5 lotes de média, a janela de 5s acumula ~125.000 lotes — o limiar é ultrapassado **400x**. A única condição que sobra de pé é `deslocamento <= 1 tick`, ou seja: *"o preço ficou parado"*. Que é a definição de mercado lateral, não de absorção.
- **`DetectorAbsorcao` não tem `_ja_sinalizado`**, ao contrário de `DetectorEscora` (linha 131) e `DetectorIceberg` (linha 174). Enquanto a condição durar, ele re-emite o mesmo alerta a cada trade. Milhares de eventos idênticos para um único fenômeno.

O limiar precisa ser relativo (fração do volume da janela, ou múltiplo do volume médio por nível), não absoluto — e o detector precisa do dedup que os irmãos dele já têm.

### 5.3 🟠 `DetectorExaustao` — 3.210 disparos por minuto no simulador

Rodado sobre o `SimuladorWDO` com config de fábrica: **318 detecções em 30.000 trades (1,1%), ~3.210 por minuto**. Ruído.

Dois defeitos de lógica, ambos na janela de 5 trades:

- **`progrediu = preco_fim != preco_inicio`** (linha 340) compara só o primeiro e o último trade. O preço pode subir 10 ticks e voltar dentro da janela e contar como "não progrediu". Deveria olhar `max`/`min` da janela.
- **`terco = max(1, 5 // 3) = 1`**: com o `n_trades_janela=5` padrão, "queda do volume do último terço vs. o primeiro terço" compara **um único trade contra um único trade**. `queda >= 0.4` vira "o 5º trade é 40% menor que o 1º" — evento aleatório com probabilidade alta em qualquer tape. A palavra "terço" descreve uma estatística que a config padrão não produz.

### 5.4 🟠 `Footprint`: imbalance marca tudo com a config padrão

`qty_minima_imbalance = 0` por default, combinado com a regra `if qty_vendedor_vizinho == 0: resultado.append(preco)` (footprint.py:134-135). Medido:

```
3 trades de 1 LOTE, só compradores, 3 níveis consecutivos
niveis_imbalance_compra() = [10000, 10001, 10002]   <- os 3 marcados
```

Qualquer nível sem contraparte diagonal vira imbalance, inclusive com 1 lote contra 0. A docstring do próprio campo (linhas 49-50) diz que o piso serve para "evitar imbalance espúrio tipo 1 contra 0 (razão infinita)" — e o default o desliga. **A proteção existe e vem desarmada de fábrica.** Nas extremidades do candle, onde a diagonal não tem vizinho por construção, o falso positivo é garantido.

### 5.5 🟢 `DetectorClipInstitucional` e `DetectorLiquidezFantasma` resistiram

262 disparos/min no simulador (0,1% dos trades) — a mais seletiva do conjunto, e os testes de fronteira mataram M32 e M33. `LiquidezFantasma` também acerta a nomenclatura neutra (docstring linhas 258-263): observa retirada rápida sem execução e não afirma intenção. É o melhor código do arquivo.

### 5.6 🟠 Contradição entre docstring e implementação

Docstring do módulo, linhas 5-7: *"em feed agregado (`FonteMicro.MBP_INFERIDO`) a confiança do evento de origem se propaga."* `FonteMicro` é importado na linha 19 e **nunca usado no arquivo**. Todos os detectores cravam `confianca=1.0` (exceto o proxy de Iceberg, 0.6). Um detector rodando sobre livro reconstruído pelo `InferidorMBP` — cujo módulo inteiro existe para marcar hipótese como hipótese — emite detecção com confiança 1.0, apagando exatamente a distinção que o pacote foi construído para preservar. E M27 mostrou que nenhum teste protege isso.

### 5.7 🟡 Ruído bruto de `_ja_sinalizado`, por completude

`DetectorEscora._ja_sinalizado` e `DetectorIceberg._ja_sinalizado` são `set`s indexados por `(side, price)` que **nunca são podados**. Ao longo de um pregão inteiro sem reset (ver 4.5), acumulam uma entrada por nível de preço já sinalizado. Vazamento pequeno em memória; grande em semântica — um nível sinalizado às 9h nunca mais dispara às 17h.

---

## 6. Fora do escopo, mas registrado

- **`fluxopro/microestrutura/inferencia_mbp.py` (476 linhas)** e **`fluxopro/motor/sinais.py` (202 linhas)** não foram atacados por mutação nesta rodada. Dado o resultado do `livro_mbo.py`, presumir cobertura ali seria imprudente — R2 deveria começar por eles.
- A **documentação deste projeto é excepcionalmente honesta** — em particular o cabeçalho de `inferencia_mbp.py`, que separa explicitamente "o que é observado", "o que é inferido" e "o que é indetectável sem MBO real". Isso é raro e vale preservar. O problema não é o projeto mentir sobre o que sabe; é o teste não prender o que o código promete.
- **`bench_carga.py`** ficou na raiz do projeto e é reexecutável: `python bench_carga.py --perfil`.

---

## 7. Backlog priorizado

| # | Item | Arquivo:linha | Gravidade |
|---|---|---|---|
| 1 | `DetectorAbsorcao` O(n) por trade → deque + contadores incrementais + monotonic deque | `detectores.py:72,74-80` | 🔴 bloqueia a barra |
| 2 | Suíte de testes para `LivroMBO` (FIFO, `melhor_bid/ask`, `qty_a_frente`, reposição, remoção preguiçosa) | `livro_mbo.py` (606 linhas, 0 testes) | 🔴 |
| 3 | `DetectorIceberg` proxy: usar `consumido_acumulado` (já existe) ou deletar o detector | `detectores.py:187-190` | 🔴 |
| 4 | Limiar relativo + `_ja_sinalizado` no `DetectorAbsorcao` (98,2% de falso positivo) | `detectores.py:53,82,98` | 🔴 |
| 5 | Detecção de livro cruzado em `EstadoMercado` e `LivroMBO` | `estado_mercado.py:99-106` | 🔴 |
| 6 | Sequence number + detecção de gap nos eventos de feed | `core/eventos.py` | 🔴 |
| 7 | Ciclo de vida de sessão: `nova_sessao()` em `EstadoMercado`, `VWAP`, `CumulativeDelta` | 5 classes | 🟠 |
| 8 | Política única para `AgressorSide.UNKNOWN` + contador de volume não atribuído | `estado_mercado.py`, `delta.py`, `agressao.py` | 🟠 |
| 9 | Estado "não sincronizado" até o primeiro snapshot | `estado_mercado.py:99` | 🟠 |
| 10 | `qty_minima_imbalance` com default > 0 | `footprint.py:48` | 🟠 |
| 11 | `DetectorExaustao`: `progrediu` por max/min da janela; revisar o "terço" com n=5 | `detectores.py:332,340` | 🟠 |
| 12 | Propagar `FonteMicro`/confiança nos detectores (ou corrigir a docstring) | `detectores.py:5-7,19` | 🟠 |
| 13 | Testes de fronteira `>=`/`>` (M15, M19, M28) e `round` vs `int` (M06); retrocesso do relógio (M09) | vários | 🟡 |
| 14 | `soma_preco_qty`/`soma_preco2_qty` como `int` | `vwap.py:50-51` | 🟡 |

---

*Working tree verificado limpo ao final: `git diff --stat fluxopro/` vazio, `git status --short -- fluxopro/` vazio, suíte re-executada — 94 passed. As 33 mutações foram revertidas uma a uma. Modificações em `PROGRESSO.md` e `pesquisa/` são de outro agente rodando em paralelo, não deste trabalho. Único arquivo criado por esta revisão: `bench_carga.py` e este relatório.*
