# Crítica adversarial R4 — quarta rodada

**Data:** 2026-08-21 · **Commit auditado:** `af92ba6` (onda 7) · **Suíte:** 494 testes
**Barra:** leitura tick-a-tick do WDO, picos de 5–10 mil ev/s, nível Profit Pro (`bar/barra_profit_pro.md`)
**Método:** execução real — suíte, re-mutação das sobreviventes da R3, mutações novas em território virgem, benchmarks re-medidos por mim, sondas em regimes que a onda 7 não testou (`.mut/sonda_r4.py` herdada do crítico morto, `.mut/sonda2_r4.py` minha).

> **Disciplina de mutação:** sha256 gravado antes, restauração e conferência byte a byte depois, `try/finally`, e registro do que está em voo em `.mut/r4_em_voo.json` ANTES de aplicar.

---

# VEREDITO: **NÃO PASSA**

*(justificativa completa ao fim; o maior gap está abaixo)*

---

## ÚNICO MAIOR GAP

### `fluxopro/microestrutura/inferencia_mbp.py:759-763` — `_registrar_preco` empilha sem dedup e sem teto: a **5ª casa** do mesmo defeito, dentro do módulo que a onda 7 acabou de declarar consertado

```python
def _registrar_preco(self, side: Side, price: int) -> None:      # :759
    if side is Side.BUY:
        heapq.heappush(self._heap_bids, -price)                  # :761  <- incondicional
    else:
        heapq.heappush(self._heap_asks, price)                   # :763
```

Chamado em `_observar_nivel` (`:436-437`) em **toda** transição `0 → qty` de um nível:

```python
if anterior == 0 and nova_qty > 0:
    self._registrar_preco(side, price)
```

Não há teste de pertinência, não há teto, e a remoção é **preguiçosa e só pelo topo** (`melhor_bid`, `:766-771`): o laço só descarta enquanto a **cabeça** do heap for um preço vazio. Um nível que pisca `0 → 300 → 0` — que é o comportamento normal de um nível de fundo do WDO, e é exatamente o regime de **recarga** que o produto existe para detectar — insere uma duplicata por recarga, **para sempre**.

**Medido** (`PYTHONPATH=. python .mut/sonda2_r4.py d`), taxa fixa de 5.000 snapshots/s, topo cravado em 10.000 e um único nível de fundo piscando:

| minutos de pregão | snapshots | `len(_heap_bids)` | níveis VIVOS | MB só do heap | µs/passo |
|---|---|---|---|---|---|
| 1 | 300.000 | **150.001** | **2** | 4,2 | 33,54 |
| 2 | 600.000 | **300.001** | **2** | 8,4 | 38,96 |
| 4 | 1.200.000 | **600.001** | **2** | 16,8 | 33,20 |
| 8 | 2.400.000 | **1.200.001** | **2** | 33,6 | 25,89 |
| 16 | 4.800.000 | **2.400.001** | **2** | 67,2 | 23,01 |

Crescimento **exatamente linear no tempo de pregão**, 1 entrada por recarga, com **dois** níveis vivos. Extrapolando o pregão de 6h a 5.000 ev/s: **54 milhões de entradas de heap para 2 níveis vivos.**

### Por que isto é o maior gap, e não só um vazamento

**1. O tempo de parede NÃO acusa — ele até melhora.** Repare na última coluna: 33,54 → 23,01 µs/passo. O custo por passo *cai* enquanto a estrutura infla. Qualquer benchmark de throughput — inclusive todos os da onda 7 — passa com folga com este defeito instalado. **É a quinta vez que este projeto mede o eixo amigável**, e desta vez o eixo amigável é o próprio que a onda 7 escolheu como métrica determinística de substituição.

**2. A dívida é paga de uma vez, num único evento, e no pior momento possível.** A poda preguiçosa não cobra nada enquanto o topo estiver ocupado. No instante em que o topo esvazia, `melhor_bid()` tem de fazer `heappop` de todo o backlog acumulado — num só evento (`.mut/sonda2_r4.py e`):

| ciclos de recarga | heap antes | **latência DO EVENTO** | orçamento da barra |
|---|---|---|---|
| 10.000 | 5.002 | 2.588 µs | 100–200 µs |
| 50.000 | 25.002 | 17.276 µs | 100–200 µs |
| 200.000 | 100.002 | 62.549 µs | 100–200 µs |
| **800.000** | **400.002** | **244.003 µs = 0,24 s** | 100–200 µs |

**Um único evento leva 244 ms** — 1.200× a 2.400× o orçamento por evento da barra. E o evento que dispara a cobrança é *o topo do book esvaziando*: o rompimento, o momento em que a leitura de fluxo vale alguma coisa. **O sistema congela por um quarto de segundo exatamente no tick em que o operador precisa dele**, e depois de 6h de pregão o backlog é ~27× maior que o pior caso medido acima.

**3. É memória sem teto num processo que roda 6h.** 67 MB de heap em 16 minutos *só na lista de inteiros*, sem contar os objetos `int` do CPython. O `DetectorExaustao` da onda 6 foi condenado por reter 200.000 objetos; este retém 54 milhões, no módulo que a onda 7 auditou linha a linha.

**4. A onda 7 declarou este módulo resolvido e mediu o eixo que não dói.** O PROGRESSO (onda 7) publica "1,0 → 1,0 (1,00×)" em candidatos percorridos por passo e "45.154 passos/s". Confirmo os dois números — e re-medi nos três regimes que ELES não testaram (preço cravado + cancelamento massivo + recarga; alternância rápida de topo), e o fator por passo é **plano nos dois** (0,98× a 1,04×). **A correção da onda 7 é real.** O defeito que encontrei não é o quadrático deles voltando: é uma estrutura nova, introduzida *pela própria correção* — o índice por preço precisou de um heap para responder `melhor_bid`, e o heap nasceu sem dedup e sem teto.

**Conserto:** o heap precisa de um conjunto-espelho (`set`) que impeça o push duplicado — `if price not in self._precos_bid: heappush(...); self._precos_bid.add(price)` — com remoção do `set` no mesmo ponto em que `melhor_bid` faz `heappop`. Custa O(1) em ambos os lados e transforma o tamanho do heap em O(níveis distintos do dia) em vez de O(recargas do dia). Junto: um teste que prenda `len(inf._heap_bids) <= k * len(inf._qty_por_nivel)` ao longo de uma sessão longa — porque este é o eixo que cinco rodadas de benchmark não olharam.

---

# PARTE A — as correções da onda 7, verificadas

## A.1 Suíte — saída literal

```
$ python -m pytest tests/ -q
........................................................................ [ 14%]
........................................................................ [ 29%]
........................................................................ [ 43%]
........................................................................ [ 58%]
........................................................................ [ 72%]
........................................................................ [ 87%]
..............................................................           [100%]
494 passed in 26.25s
```

494 testes, contra 312 na R3. **+182 testes.** Guarde este número para a seção A.2.

## A.2 As 21 mutações que a R3 deixou vivas, re-aplicadas: **20 de 20 continuam vivas. Zero mortas.**

Harness `.mut/harness_r4.py` (sha256 antes, `try/finally`, restauração conferida por sha256, registro em `.mut/r4_em_voo.json` ANTES de aplicar). Tabelas em `.mut/r4_remut.json` e `.mut/r4_remut2.json`; resultados em `*_res.json`.

| # | Arquivo | Mutação | R3 | **R4** |
|---|---|---|---|---|
| N01 | `dados/replay.py:109` | sort perde o desempate `(ts, origem, índice)` | 🟢 | 🟢 **AINDA VIVE** |
| N03 | `dados/replay.py:34-35` | `buyer_broker`/`seller_broker` trocados no CSV | 🟢 | 🟢 **AINDA VIVE** |
| N04 | `dados/simulador.py:96-99` | **agressão de COMPRA empurra o preço para BAIXO** | 🟢 | 🟢 **AINDA VIVE (4ª rodada)** |
| N05 | `dados/simulador.py:92` | regime de absorção desligado | 🟢 | 🟢 **AINDA VIVE (4ª rodada)** |
| N06 | `dados/mt5.py` | bids ordenados do PIOR para o melhor | 🟢 | 🟢 **AINDA VIVE** |
| N10 | `dados/leitor_gravacao.py:145` | sort perde o desempate por tipo/índice | 🟢 | 🟢 **AINDA VIVE** |
| N12 | `gravacao/formato.py:31` | `SCHEMA_VERSAO` 1 → 99 | 🟢 | 🟢 **AINDA VIVE** |
| X01 | `analytics/brokers.py:110` | janela expira com `>=` (trade na borda exata some) | 🟢 | 🟢 **AINDA VIVE** |
| X04 | `analytics/brokers.py:88` | aceita trade de OUTRO símbolo | 🟢 | 🟢 **AINDA VIVE** |
| X06 | `microestrutura/perfil_player.py:83-84` | **quem agrediu invertido (comprador↔vendedor)** | 🟢 | 🟢 **AINDA VIVE** |
| X08 | `microestrutura/perfil_player.py:99-101` | perna vendedora não conta clip | 🟢 | 🟢 **AINDA VIVE** |
| X10 | `microestrutura/perfil_player.py:38` | **`agressividade` mede o lado PASSIVO** | 🟢 | 🟢 **AINDA VIVE** |
| X15 | `dados/mt5.py` | `profundidade_maxima` ignorada | 🟢 | 🟢 **AINDA VIVE** |
| X16 | `dados/mt5.py` | `BookDelta` de ADD sempre com `position=0` | 🟢 | 🟢 **AINDA VIVE** |
| X18 | `gravacao/catalogo.py:54` | `escanear` não limpa o índice | 🟢 | 🟢 **AINDA VIVE** |
| X19 | `gravacao/catalogo.py:38-41` | `arquivo()` prefere o plano ao `.gz` | 🟢 | 🟢 **AINDA VIVE** |
| X20 | `gravacao/catalogo.py:103` | intervalo invertido reordenado em silêncio | 🟢 | 🟢 **AINDA VIVE** |
| X26 | `analytics/footprint.py:165-166` | vizinho diagonal zerado deixa de marcar imbalance | 🟢 | 🟢 **AINDA VIVE** |
| X27 | `analytics/footprint.py:200` | média de volume por nível divide por `n+1` | 🟢 | 🟢 **AINDA VIVE** |
| X28 | `analytics/footprint.py:193-194` | `delta_divergente` só olha alta | 🟢 | 🟢 **AINDA VIVE** |
| X14 | `dados/mt5.py:231` | dedup de tick vira `<` | 🟢 | ⚙️ **ÂNCORA EXTINTA** — legítimo: a onda 7 reescreveu `_puxar_ticks` e o cursor por segundo não existe mais |

**Placar: 20 vivas, 0 mortas, 1 âncora legitimamente extinta.**

Este é o resultado mais importante da Parte A, e não é sobre nenhum módulo em particular. **A onda 7 acrescentou 182 testes e nenhum deles mata uma única mutação que a rodada anterior deixou viva.** Os 182 testes são reais e são bons — são a razão de 7 das minhas 10 mutações novas morrerem (Parte B). Mas todos foram escritos *dentro* dos três módulos que os builders receberam (`detectores.py`, `mt5.py`, `inferencia_mbp.py`). Fora desses três, a cobertura de semântica não se moveu um milímetro em quatro rodadas.

Duas consequências que valem nomear:

- **`perfil_player.py` entra na quarta rodada com as três inversões da sua própria razão de existir passando batido.** X06 (quem agrediu), X10 (agressividade vira passividade) e X08 (clip da perna vendedora). O módulo tem 125 linhas e não ganhou um teste desde a R3.
- **`simulador.py` entra na quarta rodada sem uma única asserção sobre comportamento de mercado.** N04 e N05 vivem desde a R2. Isso não é um defeito do simulador — é o que retira o chão de todo número de qualidade já produzido por este projeto (Parte D).

**Prova de restauração.** `git status --porcelain` não lista um único arquivo de produção modificado. Conferência independente por sha256 dos 66 arquivos versionados de `fluxopro/`, `scripts/` e `tests/` contra o blob de `HEAD`: **0 divergências reais de conteúdo** (26 arquivos diferem só por CRLF, porque `core.autocrlf=true` nesta máquina — normalizados, batem). `.mut/r4_em_voo.json` foi apagado em cada `finally` e não existe agora.

> *Nota de método para o próximo auditor:* a R3 publicou "comparação byte a byte contra o blob de `HEAD` — todos idênticos". Com `core.autocrlf=true`, comparação byte a byte contra o blob **não pode** dar idêntico para arquivo CRLF. A prova precisa normalizar a quebra de linha. A conclusão dela (tree limpo) continua correta; o método publicado não reproduz.

## A.3 Os benchmarks, re-medidos por mim

### MT5 — **a alegação confere, e é a melhor peça da onda 7**

`$ python bench_mt5.py`

| tape (ticks/s) | entregues | **perdidos** | CPU | capacidade | custo/1s de tape |
|---|---|---|---|---|---|
| 1.000 | 5.000 | **0** | 0,037s | 134.469/s | 0,7% |
| 3.000 | 15.000 | **0** | 0,123s | 121.745/s | 2,5% |
| 5.000 | 25.000 | **0** | 0,193s | 129.544/s | 3,9% |
| 10.000 | 50.000 | **0** | 0,390s | 128.299/s | 7,8% |
| 20.000 | 100.000 | **0** | 1,130s | 88.531/s | 22,6% |
| **50.000** | **250.000** | **0** | 3,425s | 72.984/s | 68,5% |

Alegação "~80.000 ticks/s e zero perda até 50.000/s": **confirmada.** O congelamento permanente do feed que era o **segundo maior gap da R3 está genuinamente morto**, e o mock agora honra `de` e `count`. Esta correção é real, medida, e a mais valiosa das quatro rodadas.

### Inferência — **a alegação confere, inclusive nos regimes que eles não testaram**

`$ python bench_inferencia.py` — fator ao subir a taxa de 500 para 10.000/s:

| regime medido por eles | fator µs/passo | visitas/passo |
|---|---|---|
| 2. tape do lado que NÃO casa | 0,00× | 0,0 |
| 3. tape do lado que CASA | **1,00×** | 2,0 |
| 4. agressor DESCONHECIDO (leilão/RLP) | **1,00×** | 2,0 |
| 5. eixo antigo (largura do book) | plano | 0,0 |

**Confirmado: 1,00×, plano.** O quadrático da 3ª casa está morto.

**Três regimes que eles NÃO testaram, construídos por mim** (`.mut/sonda_r4.py`, herdada do crítico morto — a sonda estava correta e a aproveitei):

| regime | 500/s | 10.000/s | fator |
|---|---|---|---|
| **B. preço cravado + cancelamento massivo + recarga** | 17,88 µs/passo | 17,57 µs/passo | **0,98×** |
| **C. alternância rápida de topo** (bid alterna entre 2 preços a cada passo) | 26,72 µs/passo | 27,87 µs/passo | **1,04×** |
| **A. recarga sob topo estável** | — | 19.388 snapshots/s | — |

**O fator por passo é plano nos três.** Não achei o quadrático voltando. A correção da onda 7 resiste ao ataque.

**O que achei foi outra coisa, e é o maior gap desta rodada:** o regime A expõe que `len(_heap_bids)` chega a **100.001 entradas para 2 níveis vivos**, e o eixo que revela isso — **duração de pregão** — não aparece em nenhum benchmark deste repositório. Ver "Único maior gap" acima.

### Pipeline completo — o veredito por regime

`$ python bench_app.py` (n=30.000 passos = 60.000 eventos, melhor de 3):

| estágio | ev/s | veredito |
|---|---|---|
| 1. barramento + `EstadoMercado` | 73.218 | PASSA |
| 2. + analytics (6 módulos) | 64.366 | PASSA |
| 3. + detectores de tape (3) | 41.965 | PASSA |
| 4. + `MotorSinais` | 25.388 | PASSA |
| **5. + microestrutura — PIPELINE COMPLETO** | **5.873** | ***NÃO PASSA*** |

**Os dois regimes, medidos:**

| regime do book | ev/s | ord/ev | veredito |
|---|---|---|---|
| **(a) simulador cru** (fundo do book com qty aleatória a cada tick) | **6.457** | 6,46 | **NÃO PASSA** |
| **(b) book estável** (só o topo se move — DOM realista) | **14.236** | 0,98 | **PASSA** |

Escalonamento do pipeline completo: 146,95 → 139,75 → 141,56 → 151,13 µs/ev ao dobrar n quatro vezes — **linear** (×0,95 / ×1,01 / ×1,07). Não há custo não-linear *nesta janela de medição*.

**Veredito por regime, com honestidade sobre o que ele vale:**

- **Simulador cru: 5.873–6.457 ev/s. NÃO PASSA.** É pior que os 7.851 da R3 e que os 8.853 da onda 6 — consistente com o custo declarado da fiação de procedência (+19,5% no simulador, PROGRESSO onda 7) mais variação de máquina. A onda 7 pagou performance por correção, e declarou o preço. Correto.
- **Book estável: 14.236 ev/s. PASSA** — com 1,42× de folga sobre a barra de 10.000.

**E a ressalva que anula a leitura fácil dos dois números:** o regime (b) é uma construção dos próprios builders, e é *outra vez o eixo amigável*. Um DOM real não tem fundo perfeitamente estável — a verdade está entre (a) e (b), e **ninguém sabe onde, porque ninguém jamais observou um DOM real neste projeto** (Parte D: o pacote `MetaTrader5` não está sequer instalado nesta máquina). A pergunta "o pipeline passa a barra?" continua **sem resposta medida** depois de quatro rodadas, e o intervalo honesto é `[5.873 , 14.236]` — a barra de 10.000 cai dentro dele.

Junto: o vazamento do heap (maior gap) só se manifesta ao longo de horas, e **nenhum destes benchmarks roda por mais que 40.000 passos**. Os 14.236 ev/s do regime (b) são o número da primeira meia-hora.

## A.4 O relógio de MÁXIMO está certo? **Não. O máximo nunca esquece, e o erro é permanente.**

O estimador é uma **catraca** (`fluxopro/dados/mt5.py:214-219`):

```python
def observar(self, servidor_ns: int) -> None:
    estimativa = servidor_ns - time.time_ns()
    if not self._sincronizado or estimativa > self._offset_ns:   # :215  <- SÓ SOBE
        self._offset_ns = estimativa                             # :219
```

Não há decaimento, não há janela deslizante, não há re-sincronização, não há `iniciar_nova_sessao`. Uma vez alto, `_offset_ns` fica alto pelo resto da vida do processo.

O raciocínio do builder está certo *para o problema que ele resolvia*: toda amostra subestima o offset pela idade do tick, então o máximo é o melhor estimador **enquanto o relógio do servidor só anda para a frente**. A hipótese não declarada é "o relógio do servidor nunca regride". Ela é falsa: troca de servidor da corretora (o terminal reconecta em outro servidor MetaQuotes, com fuso e sincronia próprios), ajuste de NTP do lado deles, virada de horário de verão.

**Medido** (`PYTHONPATH=. python .mut/sonda3_r4.py f`), atacando `_RelogioServidor` diretamente:

```
   offset apos 50 ticks com servidor em GMT+3 : +10799.995 s   (verdade: +10800.000 s)   <- correto
   servidor RECUA para GMT+1; 5.000 ticks novos observados
   offset apos a regressao                    : +10799.995 s   (verdade agora: +3600.000 s)
   ERRO PERMANENTE do relogio derivado        : +7199.995 s  = 7,199,995 ms
   -> o erro e' 24,000x a janela de reconciliacao de 300 ms
```

**5.000 amostras corretas consecutivas não movem o offset um nanossegundo.** E não é preciso uma troca de fuso para matar o sistema:

```
   regressao MINIMA (400 ms, um ajuste de NTP banal):
     offset preso em 500 ms, verdade 100 ms -> erro 400 ms > janela de 300 ms
```

**Uma regressão de 400 ms já basta.** A onda 7 matou "dois relógios" (R3 §C.1) e depois matou "um relógio que mente com o tape parado" — e o que sobrou é **um relógio que mente para sempre depois de qualquer regressão do servidor**. O modo de falha final é *idêntico* ao da R3 §C.1: todo `BookSnapshot` carimbado fora da janela de reconciliação ⇒ 100% das execuções viram cancelamento; e como `_ultimo_ns` é um piso monotônico (`:225-231`), a gravação também volta a sair irreproduzível (R3 §C.2), com todos os books depois de todos os trades.

Agravante: **não existe teste de regressão do relógio.** Os 36 testes de `mt5.py` exercitam o avanço; nenhum recua o servidor.

**Conserto:** o máximo precisa de memória finita — máximo sobre uma **janela deslizante** (o máximo dos últimos N minutos de amostras), que é o estimador padrão para offset de relógio justamente porque tolera step do servidor. Junto: quando a amostra corrente ficar abaixo do offset vigente por mais que um limiar e por muitas amostras seguidas, isso **é** um step — emitir `FalhaCaptura` e re-sincronizar, em vez de ignorar em silêncio.

## A.5 Dedup com teto FIFO de 4.096: o ataque de rotação **vira peneira, e o penhasco é vertical**

`_MapaProcedencia` (`detectores.py:183`), `LIMITE_CHAVES_RASTREADAS = 4096` (`:138`), despejo FIFO por chave menos recentemente **alimentada** (`:229-231`). O comportamento está honestamente documentado (`:192-206`) e preso por testes (`tests/test_micro_detectores.py:985,996,1025`). A pergunta não é se está documentado — é se a **consequência operacional** é aceitável.

**Medido** (`PYTHONPATH=. python .mut/sonda3_r4.py g`), rotação estrita em ciclo, 3 voltas:

| chaves distintas em rotação | re-emissões | de | **%** |
|---|---|---|---|
| 100 | 0 | 200 | 0,0% |
| 2.000 | 0 | 4.000 | 0,0% |
| **4.096** | **0** | **8.192** | **0,0%** |
| **5.000** | **10.000** | **10.000** | **100,0%** |
| 8.000 | 16.000 | 16.000 | 100,0% |
| 20.000 | 40.000 | 40.000 | 100,0% |

**Não é uma degradação suave — é um penhasco.** Em 4.096 chaves a dedup é perfeita; em 5.000 ela é **totalmente** inútil. É a patologia clássica de LRU sob varredura cíclica: a chave despejada é sempre exatamente a próxima que será revisitada.

**A consequência operacional NÃO é aceitável, e a razão é a chave escolhida.** `DetectorEscora` usa `(side, price)` (`:580`) — ~1.200 chaves num pregão de WDO, com folga confortável sob o teto. Mas `DetectorIcebergPorRecarga` (`:683`) e `DetectorLiquidezFantasma` (`:767`) usam **`order_id`**:

```python
def _chave_do_evento(self, evento: OrdemEvento) -> Hashable:
    return evento.order_id
```

Em modo MBP — que é o único modo disponível, porque não há UMDF/ProfitDLL — **os `order_id` são sintéticos, criados pelo `InferidorMBP` a cada inserção inferida.** O `bench_app.py` mede **6,5 eventos de ordem por evento de mercado** (389.910 em 60.000). Na barra de 10.000 ev/s de mercado isso é ~65.000 `order_id` novos por segundo, e **4.096 chaves cobrem 63 milissegundos de tape**.

Um iceberg é, por definição, uma ordem que recarrega **ao longo de segundos**. Entre duas recargas da mesma ordem passam dezenas de milhares de `order_id` novos, a chave é despejada, e a recarga seguinte é tratada como episódio novo. **Os dois detectores que existem para reconhecer persistência de uma mesma ordem têm uma memória de 63 ms.** O teto não está espremendo a cauda fria da distribuição; está cortando a mediana do fenômeno que o detector persegue.

**Conserto:** o teto não pode ser um número absoluto de chaves quando a chave é um id de alta rotatividade. Ou o despejo passa a ser por **idade** (chave viva enquanto o episódio está dentro da janela do detector, que é o critério semântico), ou a chave desses dois detectores passa a ser `(side, price)` como a da Escora — e nesse caso 4.096 volta a ser generoso. E o número precisa de um teste que o confronte com a taxa de criação de `order_id` medida (6,5/evento), não com uma rotação sintética de 100 chaves.

---

# PARTE B — 10 mutações novas na fiação que a R3 não pôde tocar

`fluxopro/app/` e `scripts/` nasceram na onda 6, depois do fim da R3, e nunca foram mutados. Tabela em `.mut/r4_novas.json`, resultados em `.mut/r4_novas_res.json`.

| # | Arquivo:linha | Mutação | Resultado | Testes que pegam |
|---|---|---|---|---|
| Y01 | `app/config.py:108` | `PRIORIDADE_PERFIL_SESSAO` 25 → 45: o perfil de sessão passa a entregar **depois** do motor — "a seta que não pode inverter" | ☠️ **MORTA** | 2 |
| Y02 | `app/config.py:112` | `PRIORIDADE_MICRO` 30 → 45: o `InferidorMBP` entrega depois do motor | ☠️ **MORTA** | 2 |
| Y03 | `app/config.py:119` | `PRIORIDADE_SAIDA` 50 → 1: a saída lê o mundo de um evento atrás | ☠️ **MORTA** | 1 |
| Y04 | `app/montagem.py:177-178` | fonte construída **antes** da sessão (a corrida que a docstring diz não ser invariante) | 🟢 **SOBREVIVEU** | — |
| Y05 | `app/montagem.py:110` | `--de/--ate` no CSV do núcleo passa a ser ignorado em silêncio (falha ABERTA) | ☠️ **MORTA** | 1 |
| Y06 | `app/montagem.py:139` | `max(e.data)` → `min(e.data)`: escolhe o dia **mais antigo** da gravação | 🟢 **SOBREVIVEU** | — |
| Y07 | `app/montagem.py:152` | `verificar_hash=opcoes.verificar_hash` → `False`: integridade desligada em silêncio | 🟢 **SOBREVIVEU** | — |
| Y08 | `app/saida.py:131-132` | toda detecção inferida é impressa como `[OBS]` — a marca de procedência mente | ☠️ **MORTA** | 5 |
| Y09 | `app/saida.py:161` | direção do sinal sempre impressa como `-` | ☠️ **MORTA** | 1 |
| Y10 | `analytics/footprint.py:57` | `qty_minima_imbalance` 0 → 10 | ☠️ **MORTA** | 1 |

**Placar: 7 mortas, 3 vivas (30% de sobrevivência) — de longe o melhor território das quatro rodadas.** Para comparação: R3 teve 50% de sobrevivência, e as re-mutações desta rodada tiveram 100%.

## Leitura da tabela

**A fiação da onda 6 é o trabalho mais bem testado do repositório, e a prova é a mais difícil de forjar: as três prioridades do barramento morrem.** Y01, Y02 e Y03 não são erros de digitação detectáveis por um teste de fumaça — são inversões de *ordem de entrega*, que só um teste de comportamento pega. `tests/test_app_pipeline.py` tem esse teste. Isso vale registrar depois de três rodadas condenando este projeto por testar plumbing em vez de semântica: **aqui a semântica está presa.** O mesmo para Y08 — a marca `[OBS]`/`[INF]` na tela, que é o único lugar onde o operador vê a diferença entre fato e hipótese, tem 5 testes atrás dela.

**As 3 sobreviventes são todas do `montagem.py`, e duas delas escolhem dados errados em silêncio:**

- **Y06 é a mais séria. O replay carrega o dia mais antigo em vez do mais recente e nada acusa.** `dia = ... else max(e.data for e in disponiveis)` (`montagem.py:139`) é a linha que decide **qual pregão o operador vai analisar** quando ele não passa `--data`. Trocar `max` por `min` faz o sistema abrir silenciosamente a gravação mais velha do catálogo. Não há mensagem, não há aviso, e a tela é idêntica — o operador estuda o fluxo de um dia e acredita estar olhando outro. É a mesma classe do "erro de contraparte": os números estão todos certos e são sobre o objeto errado.
- **Y07 desliga a verificação de hash da gravação em silêncio.** A onda 5 foi elogiada pela R3 por transformar a integridade da gravação "de decorativa a real" (N09/N16/N17 morreram). Mas o *ponto de consumo* dessa integridade — o único lugar do produto que decide se vai conferir o hash — pode ser cravado em `False` e a suíte inteira fica verde. A corrente de integridade tem um elo testado e um interruptor não testado.
- **Y04 é a mais leve, e a docstring já a antecipa.** `montagem.py:167-175` explica, corretamente, que construir a fonte antes da sessão é "uma corrida que só não estoura porque `iniciar()` ainda não foi chamado — e 'só não estoura porque ninguém chamou ainda' não é invariante". O builder identificou o risco, escreveu a justificativa, e **não escreveu o teste que prende a ordem**. Um raciocínio correto num comentário não impede um refactor de inverter duas linhas.

## O achado incômodo: Y10 morreu, e isso é uma má notícia

`qty_minima_imbalance: int = 0` (`footprint.py:57`) é o piso desarmado que a R1 achou, a R2 repetiu e a R3 mediu — marcando **42% a 72% dos níveis** de um candle esparso como imbalance. Está condenado há três rodadas e continua 0.

Mudá-lo para 10 **quebra um teste**. Ou seja: o default que quatro rodadas pediram para consertar agora está **preso pela suíte**. O teste não afirma que 0 é o valor certo; ele afirma o comportamento que decorre de 0. O efeito prático é que a onda 8 vai tentar consertar isto, ver um teste vermelho, e ter de decidir se o teste é contrato ou se é cimento em volta do defeito. Registro aqui para que essa decisão seja consciente: **é cimento.**

---

# PARTE C — os pendentes declarados, conferidos no código vivo

## C.1 Sessão: 9 dos 13 componentes têm reset agora — mas o `MotorSinais` não tem, e o conserto está no lugar errado

| componente | reset próprio | onde |
|---|---|---|
| `EstadoMercado` | ✅ | `core/estado_mercado.py:252` |
| `CumulativeDelta` | ✅ | `analytics/delta.py:168` |
| `VWAP` | ✅ | `analytics/vwap.py:128` |
| `MedidorAgressao` | ✅ | `analytics/agressao.py:241` |
| `VolumeProfilePorPeriodo` | ✅ (`nova_sessao`) | `analytics/volume_profile.py:307` |
| `DetectorEscora` / `Iceberg` / `LiquidezFantasma` | ✅ **NOVO** | `detectores.py:281` |
| `DetectorAbsorcao` | ✅ **NOVO** | `detectores.py:411` |
| `DetectorExaustao` | ✅ **NOVO** | `detectores.py:894` |
| `DetectorClipInstitucional` | ✅ **NOVO** | `detectores.py:994` |
| **`MotorSinais`** | ❌ **NÃO TEM** | classe em `motor/sinais.py:277` |
| **`PerfilPlayer`** | ❌ **NÃO TEM** | `perfil_player.py:59` |
| **`FootprintPorTimeframe`** | ❌ **NÃO TEM** | `footprint.py:237` |
| **`RankingCorretoras`** | ❌ **NÃO TEM** | `brokers.py:71` |

Os 5 detectores ganharam reset na onda 7 (eram o escopo do builder de detectores). Os 4 que faltam são exatamente os 4 módulos que **nenhum builder da onda 7 tinha no escopo**.

**O `MotorSinais` — o caso grave da R3 §C.4 — está resolvido pela porta dos fundos, e a distinção importa.** `SessaoFluxo.iniciar_nova_sessao` (`app/sessao_fluxo.py:517`) não chama reset: ela **recria os objetos** (`:585 self.motor = MotorSinais(...)`, `:587 PerfilPlayer(...)`, `:589-599` detectores, livro e inferidor). Como o reservoir de magnitude vive em estado de `__init__` (`sinais.py:312-316`), recriar de fato zera a calibração do gate. **O modo de falha concreto da R3 §C.4 está fechado para quem passa pela `SessaoFluxo`** — que é o CLI, e portanto o produto.

Três ressalvas medidas:

1. **Quem usa `MotorSinais` direto não tem como começar um dia.** Não há API. Todo benchmark, todo teste e qualquer UI futura que instancie o motor fora da `SessaoFluxo` herda o problema original.
2. **`seed_reservatorio_magnitude = 42` é constante** (`sinais.py:217`). Recriar o motor todo dia re-semeia o mesmo 42, então o reservoir sorteia **a mesma sequência aleatória em todos os pregões**. Para reprodutibilidade de replay isso é a decisão certa (a R3 elogiou). Para a calibração de um gate que se pretende estatístico sobre o dia, é um viés fixo repetido — a amostra de reservoir do dia 1 e a do dia 2 usam as mesmas posições de sorteio. Ninguém mediu se isso importa; ninguém registrou que é uma escolha.
3. **`FootprintPorTimeframe` e `RankingCorretoras` continuam sem reset possível**, e agora isso está **declarado no código**: `app/sessao_fluxo.py:515` — `SEM_RESET_POSSIVEL = ("FootprintPorTimeframe", "RankingCorretoras")`, com a docstring (`:560-566`) culpando a ausência de `Barramento.desassinar`. Passar de defeito escondido a limitação declarada e nomeada é progresso real. Continua sendo dois componentes que carregam o dia anterior.

## C.2 A variante do WINFUT com 20.000 trades laterais: **o gate continua cedendo, idêntico à R3**

O builder do motor não estava na onda 7, e o resultado é exatamente o previsto. Re-executei a sonda da R3 sem alterar nada (`PYTHONPATH=. python .mut/sonda2_r3.py e`):

| trades laterais entre as fases | `CONFIRMADO` de COMPRA emitidos | `magnitude_relativa` final | veredito |
|---|---|---|---|
| 0 *(o ponto que o teste do repo usa)* | 0 | 0,450 | gate segurou |
| 900 | 0 | 0,450 | gate segurou |
| 3.000 | 0 | 0,451 | gate segurou |
| 9.000 | 0 | 0,555 | gate segurou |
| **20.000** | **480** | **0,920** | ***MODO DE FALHA WINFUT*** |

**Inalterado.** 20.000 negócios laterais a ~10/s são ~33 minutos de tape morno — a forma exata do episódio narrado (pico de manhã, repique depois). O único episódio de falha real que este projeto conhece continua atravessando o gate construído para barrá-lo, e o teste do repositório continua parado no único ponto da curva em que o gate segura.

## C.3 `FootprintPorTimeframe` / `RankingCorretoras` sem reset

Confirmado acima (C.1). Junto: `RankingCorretoras` continua com `janela_ns = None` de fábrica — acumula desde a construção, sem janela e sem reset. E X01 (borda exata da janela) e X04 (aceita trade de outro símbolo) continuam vivas na quarta rodada.

## C.4 `Enum.__hash__` quente: a correção é local e **incompleta dentro do próprio módulo**

A onda 7 registrou como pendência "cirurgia ampla demais para builders em paralelo". O estado real é mais estreito que isso:

- **Aplicada:** `_COD_COMPRA/_COD_VENDA/_COD_DESCONHECIDO` (`inferencia_mbp.py:105-107`), usados nas chaves em `:328, :463, :595` via `_cod_lado` (`:398`).
- **NÃO aplicada no mesmo módulo:** `self._qty_por_nivel: dict[tuple[Side, int], int]` (`inferencia_mbp.py:272`) continua com chave de **enum**, e é consultada em `:432, :440, :450, :452, :753, :768, :776` — ou seja, **em toda observação de nível e em todo `melhor_bid`/`melhor_ask`**, que é o caminho mais quente do módulo. A justificativa escrita em `:99-104` para trocar enum por int aplica-se literalmente a este dicionário e ele ficou de fora.
- **NÃO aplicada fora:** `detectores.py` usa chaves `(Side, price)` e o teste as fixa (`tests/test_micro_detectores.py:1041`).

Não é uma pendência "ampla demais"; dentro de `inferencia_mbp.py` é uma linha e sete usos.

## C.5 `PENDENTE` no código — 4 ocorrências, todas em `detectores.py`

```
detectores.py:353  PENDENTE(retenção): um tape com timestamp CONGELADO (feed defeituoso...
detectores.py:389  PENDENTE(config): `volume_minimo` é absoluto e, na escala real do WDO...
detectores.py:644  PENDENTE(livro): para reconstruir um iceberg por NÍVEL (o único caminho...
detectores.py:876  PENDENTE(sensibilidade): que `progrediu` olhe só as pontas é uma escolha...
```

Nenhuma em `scripts/`, nenhuma nos outros módulos. Todas foram escritas pelo builder da onda 7 — é o único builder das quatro ondas que registrou as próprias dívidas no código em vez de no relatório. Vale como padrão a copiar.

## C.6 `bench_r3.py` mede o eixo amigável — confirmado, e a doença é geral

A onda 7 declarou que `.mut/bench_r3.py` estágio 6 "mede o eixo errado de novo". Confirmo, e amplio: **é o eixo amigável em todo benchmark deste repositório.** Nenhum dos seis `bench_*.py` da raiz varre o eixo **duração de sessão**; todos varrem taxa ou tamanho de estrutura, com no máximo 40.000 passos. É por isso que o vazamento do heap (maior gap) atravessou a onda 7 inteira sem ser visto — inclusive pelo builder que estava profilando aquele exato módulo e achou a 4ª casa do quadrático no `livro_mbo.py`.

## C.7 Barramento: as duas reservas da R3 §C.3 continuam abertas

`core/barramento.py` tem 50 linhas. `desassinar`: **não existe**. Isolamento de exceção: **não existe** — `publicar` é `for assinatura in ...: assinatura.callback(evento)` (`:49-50`), e uma exceção em qualquer assinante aborta a entrega aos de prioridade maior. Reentrância: **insegura** — `assinar` faz `append` e `sort` (`:45-46`) na mesma lista que `publicar` itera.

Isto agora tem consequência nomeada no produto: é a ausência de `desassinar` que impede o reset de `FootprintPorTimeframe` e `RankingCorretoras` (C.1). Um defeito de 50 linhas no núcleo é a causa raiz de uma limitação declarada duas camadas acima.

---

# PARTE D — dinheiro real

## A pergunta central, respondida: **nada mudou. Nenhuma medição de qualidade tocou tape real, e não podia ter tocado.**

Verificado no sistema de arquivos, não no discurso:

1. **Não existe um único byte de dado de mercado neste repositório.** Varredura da árvore inteira por `.csv`, `.csv.gz`, `.parquet`, `meta.json`, catálogos, `.jsonl`: dois resultados, ambos código-fonte (`gravacao/catalogo.py` e seu `.pyc`). O diretório `dados/` **não existe**. Não há `gravacoes/`, não há saída de gravador. Os únicos arquivos de payload são screenshots de marketing do Profit Pro (`bar/`) e legendas de YouTube (`pesquisa/`).
2. **O pacote `MetaTrader5` não está instalado nesta máquina.** `python -c "import MetaTrader5"` → `ModuleNotFoundError`. **Nenhuma linha de `fluxopro/dados/mt5.py` jamais executou contra nada.** Os 36 testes novos e excelentes da onda 7 dirigem um mock escrito à mão cuja semântica é, ela própria, uma hipótese sobre a API real (`tests/test_dados_mt5.py:92`).
3. **A infraestrutura de gravação existe e nunca foi usada.** `scripts/operar.py:142` tem `--gravar`; `scripts/gravar.py` tem `--fonte mt5`. Ambos funcionam ponta a ponta **contra o simulador**. Nenhum catálogo, nenhum log, nenhum artefato de uma sessão real em lugar nenhum.
4. **O `SimuladorWDO` continua sem uma asserção sobre mercado.** Todo o conjunto de asserções de `tests/test_simulador_determinismo.py` é: determinismo, contagem, `qty > 0`, 5 níveis, `bid < ask`, timestamps monotônicos e únicos. **Todas invariantes sob N04 e N05** — que é por isso que as duas sobrevivem pela quarta rodada.
5. **Os limiares de fábrica continuam vindo de vídeo.** `dominancia_minima=0.70` (`sinais.py:208`, justificado como "a fonte diverge entre 0.70 e 0.75"), `magnitude_relativa_minima=0.60` (`:214`, sem origem citada), `limiar_imbalance=3.0` (`footprint.py:53-55`, "padrão de mercado"), `multiplo_absorcao=2.0` (`:61-63`, sem origem), `janela_reconciliacao_ns=300ms` (`inferencia_mbp.py:130`, "precisa cobrir o jitter do feed" — jitter que nunca foi observado).
6. **A reconciliação do `InferidorMBP` nunca foi confrontada com a verdade impressa.** Os testes de `test_micro_inferencia.py:1249-1325` medem **custo** ("O(1) amortizado"), não **acerto**. A única métrica deste projeto com gabarito objetivo continua sem um único número, na quarta rodada.

Há uma frase nos dois módulos de config — "Nenhum limiar cravado no código" (`sinais.py:162`, `inferencia_mbp.py:112`) — que é verdadeira e está sendo usada no lugar errado. Ela afirma **parametrizabilidade**. O que falta é **calibração**. São propriedades diferentes, e a primeira está sendo apresentada onde a segunda faria falta.

## Lista da R3, reavaliada e repriorizada

| R3 # | O que faltava | Estado em R4 |
|---|---|---|
| 0 | `.gitignore` ancorado, `fluxopro/dados/` versionado | ✅ **FECHADO** — `b3e5bc6`. 39 arquivos versionados em `fluxopro/`+`scripts/`; a prova de restauração desta rodada só foi possível por causa disso |
| 1 | Cursor de tick em ms + saturação de `count` | ✅ **FECHADO E MEDIDO** — zero perda até 50.000 ticks/s (A.3). A melhor correção das 4 rodadas |
| 2 | Um relógio só na borda | ⚠️ **PIOR QUE ABERTO** — os dois relógios morreram, mas o estimador de máximo é uma catraca sem esquecimento: uma regressão de 400 ms do servidor reintroduz o modo de falha idêntico, **permanentemente** (A.4) |
| 3 | Custo do `InferidorMBP` no eixo do preço | ✅ **FECHADO** no eixo condenado (1,00× plano em 5 regimes, incluindo 3 que eles não testaram) — ❌ **e abriu a 5ª casa**, no heap de preços que a própria correção introduziu (maior gap) |
| 4 | Corrigir a docstring de custo | ✅ **FECHADO** — a tabela nova mede candidatos percorridos, métrica determinística, e documenta o erro anterior |
| 5 | `iniciar_nova_sessao` nos 8 sem reset | 🟡 **PARCIAL** — 5 detectores ganharam; `MotorSinais` resolvido por recriação na `SessaoFluxo`; `PerfilPlayer`, `FootprintPorTimeframe`, `RankingCorretoras` **abertos** (C.1) |
| 6 | Sequence number + detecção de gap de feed | ❌ **INEXISTENTE** — 4ª rodada. `core/eventos.py` continua sem |
| 7 | Testes de semântica do `perfil_player.py` | ❌ **INTOCADO** — X06/X08/X10 vivas pela 2ª rodada (A.2) |
| 8 | `FonteMicro` / confiança propagada nos detectores | ✅ **FECHADO, e foi o achado da onda 7** — `acompanhar()` tinha zero chamadores; agora é chamado em `sessao_fluxo.py:380`, os 3 detectores de livro propagam `proc.confianca` (`:602, :721, :810`), e Y08 morre com 5 testes |
| 9 | Robustez do gate de magnitude a pico<5% do dia | ❌ **INTOCADO** — o modo de falha WINFUT reproduz idêntico (C.2) |
| 10 | `qty_minima_imbalance` default > 0 | ❌ **INTOCADO na 4ª rodada — e agora PRESO por teste** (Parte B, Y10) |
| 11 | Ciclo de vida do `Catalogo` | ❌ **INTOCADO** — X18/X19/X20 vivas |
| 12 | Isolamento de exceção e reentrância no barramento | ❌ **INTOCADO** — e agora é a causa raiz declarada de dois componentes sem reset (C.7) |

## O que falta, priorizado por risco, para a onda 8

| # | O que fazer | Onde | Risco se ignorado |
|---|---|---|---|
| **1** | **Dedup do heap de preços** (`set` espelho no push, remoção no pop) + teste que prenda `len(_heap_bids)` ao número de níveis vivos ao longo de uma sessão longa | `inferencia_mbp.py:759-763` | 244 ms de congelamento num único evento, no rompimento; 54 M de entradas em 6 h (maior gap) |
| **2** | **Máximo com janela deslizante no offset do relógio** + `FalhaCaptura` em step detectado + teste que faça o servidor regredir | `dados/mt5.py:214-219` | Uma regressão de 400 ms do servidor da corretora reintroduz 100% de execuções viradas em cancelamento, permanentemente (A.4) |
| **3** | **Um eixo de DURAÇÃO DE SESSÃO em todos os benchmarks** (não só taxa e tamanho) | `bench_*.py` (os seis) | É o eixo que escondeu o gap #1 de uma onda inteira de builders que estavam profilando aquele módulo |
| **4** | **Chave de dedup por idade, ou `(side, price)` nos detectores de `order_id`** | `detectores.py:683, :767, :138` | Iceberg e Fantasma têm 63 ms de memória contra um fenômeno que dura segundos (A.5) |
| **5** | **Testes de semântica do `perfil_player.py`** (agressividade, agressor, clip por perna) | `perfil_player.py:38, 83-84, 99-101` | 3 inversões da leitura de player, 2ª rodada intocadas |
| **6** | **Asserções de mercado no `SimuladorWDO`** (direção do preço sob agressão; regime de absorção ativo) | `dados/simulador.py:92, 96-99` | 4ª rodada. É o que retira o chão de **todo** número deste projeto — inclusive os favoráveis desta auditoria |
| **7** | **Testes de `montagem.py`** para escolha de dia e verificação de hash | `app/montagem.py:139, :152` | Replay silencioso do dia errado; integridade desligável sem alarme (Parte B) |
| **8** | **Gate de magnitude sobre janela móvel**, não sobre o dia | `motor/sinais.py:394-429` | O único episódio de falha real conhecido continua atravessando (C.2) |
| **9** | Isolamento de exceção + `desassinar` no barramento | `core/barramento.py:48-50` | Erro de analytics derruba a captura; e destrava o reset de 2 componentes |
| **10** | `qty_minima_imbalance > 0` — **e reescrever o teste que hoje cimenta o 0** | `analytics/footprint.py:57` | 42–72% dos níveis marcados; 4ª rodada |
| **11** | Sequence number e detecção de gap de feed | `core/eventos.py` | 4ª rodada inexistente |

## O buraco de validade científica — inalterado, e agora com uma data

A R3 escreveu que até medir a reconciliação contra a verdade impressa, "nenhum número de qualidade produzido por este sistema pode ser citado como evidência de nada". Isso continua literalmente verdadeiro, e a onda 7 **melhorou as condições para fechá-lo sem fechá-lo**: o feed que travava acima de 1.000 ticks/s (gap 1 da R3, o bloqueio declarado do passo 1) está morto e medido a 50.000 ticks/s. Gravar um pregão real deixou de ser impossível por defeito de código.

O que ainda impede o passo 1 é (a) o relógio de catraca (A.4), que faz qualquer gravação real sair irreproduzível depois de um step do servidor, e (b) o fato banal de que **o pacote `MetaTrader5` não está instalado e nenhuma corretora foi conectada**. O primeiro é trabalho de engenharia de uma tarde. O segundo não é trabalho de builder nenhum — é uma decisão do dono do projeto, e é a única coisa nesta lista que nenhuma onda seguinte pode resolver sozinha.

Duas notas sobre como ler a evidência deste projeto, que valem mais que qualquer item da lista:

- **O viés medido do simulador (6,5× mais eventos de ordem que um DOM real) está documentado em `PROGRESSO.md:260` com o aviso "qualquer benchmark futuro que use o simulador herda esse viés" — e o aviso não foi propagado para trás.** Todo número de throughput publicado no arquivo antes dessa linha o herda também.
- **`PROGRESSO.md:212` registra que um harness de mutação morreu e deixou o arquivo mutado em disco.** Como `simulador.py:96-99` não tem teste (N04), a única razão para acreditar que ele está correto hoje é que eu li o código nesta rodada. Nada na suíte distingue "correto" de "ainda não mutado", e nenhuma queda futura de harness seria detectável. Foi por isso que esta rodada gravou sha256 antes de cada mutação e conferiu depois.

---

# VEREDITO: **NÃO PASSA**

Primeiro o que é verdade e foi medido, porque a onda 7 merece: **as três correções alegadas são reais e as três conferem na minha máquina.** O feed MT5 entrega 50.000 ticks/s com zero perda, contra "1.000 de 3.000 e o feed morto para sempre" — é a melhor peça de engenharia das quatro rodadas. O quadrático da 3ª casa está morto e resiste a três regimes de ataque que os builders não testaram. A fiação de procedência dos detectores estava **inerte** no produto e o próprio builder descobriu isso auditando o parcial de um colega morto, ligou, mediu o A/B e ainda achou a dupla penalização que a religação criou. E a fiação `fluxopro/app/` da onda 6 é o território mais bem testado do repositório: 7 das minhas 10 mutações morrem, incluindo as três inversões de prioridade do barramento — semântica presa por teste de comportamento, que é o que três rodadas vinham cobrando.

E o veredito é o mesmo, por quatro motivos independentes, todos medidos:

1. **A 5ª casa do mesmo defeito está aberta, dentro do módulo que a onda 7 declarou consertado, e foi criada pela correção.** `_registrar_preco` empilha sem dedup e sem teto: 2,4 milhões de entradas de heap para 2 níveis vivos em 16 minutos de pregão, e **244 ms de latência num único evento** — o evento em que o topo do book esvazia, que é o rompimento. R1: detectores. R2: motor. R3: inferência. Onda 7: livro. Agora: o heap da própria correção da inferência. A forma nunca mudou — estrutura que cresce com o estado acumulado, invisível no eixo que se mede.

2. **182 testes novos não mataram uma única mutação viva da rodada anterior.** 20 de 20 sobrevivem. Os testes são bons e estão todos dentro dos três módulos que os builders receberam. Fora deles — `perfil_player.py` com as três inversões da sua própria semântica, `simulador.py` sem uma asserção de mercado, `catalogo.py`, `brokers.py`, `footprint.py` — a cobertura não se moveu em quatro rodadas. Um processo que só cobre o que está no escopo do bilhete converge para uma suíte grande sobre uma superfície pequena.

3. **O relógio piorou de forma sutil.** Trocar o último pelo máximo consertou o modo de falha medido e criou um pior: um estimador sem esquecimento, onde 5.000 amostras corretas não corrigem uma regressão de 400 ms do servidor. O modo de falha final é *o mesmo* da R3 §C.1 — 100% das execuções viradas em cancelamento — só que agora permanente e sem nenhum teste que possa vê-lo.

4. **Nenhuma medição de qualidade tocou tape real, e o pipeline não tem resposta medida para a barra.** O `MetaTrader5` não está instalado, `dados/` não existe, zero bytes de mercado em disco. O pipeline completo faz **5.873 ev/s** no simulador cru e **14.236 ev/s** no book estável — e os dois regimes são sintéticos, com a barra de 10.000 caindo exatamente dentro do intervalo. Quatro rodadas depois, a pergunta "passa de 10.000 ev/s?" continua sem resposta, porque a única forma de respondê-la é olhar um DOM de verdade.

## ÚNICO MAIOR GAP

**`fluxopro/microestrutura/inferencia_mbp.py:759-763`** — `_registrar_preco` faz `heapq.heappush` incondicional a cada transição `0 → qty` de um nível (chamado em `:436-437`), sem teste de pertinência e sem teto, com poda preguiçosa que só remove pela cabeça do heap. Um nível de fundo que pisca `0 → 300 → 0` — o comportamento normal do WDO, e exatamente o padrão de **recarga** que o produto existe para detectar — insere uma duplicata por recarga para sempre. Medido: **2.400.001 entradas de heap para 2 níveis vivos** após 16 minutos a 5.000 ev/s, com o custo por passo *caindo* (33,54 → 23,01 µs) enquanto a estrutura infla — invisível para todo benchmark do repositório — e **244.003 µs de latência num único evento** quando o topo finalmente esvazia, contra um orçamento de 100–200 µs por evento na barra.

---

*Working tree verificado: `git status --porcelain` sem nenhum arquivo de produção modificado; conferência independente por sha256 dos 66 arquivos versionados de `fluxopro/`, `scripts/` e `tests/` contra o blob de `HEAD` — **0 divergências reais de conteúdo** (26 diferem só por CRLF, `core.autocrlf=true`). As 31 mutações (21 re-aplicadas + 10 novas) foram revertidas uma a uma pelo `finally` do harness, cada restauração conferida por sha256 antes de prosseguir, e `.mut/r4_em_voo.json` gravado antes de cada aplicação e apagado depois — não existe agora. Suíte re-executada ao fim: `494 passed`. Material de reprodução em `.mut/`: `harness_r4.py`, `r4_remut.json`/`r4_remut2.json`/`r4_novas.json` (tabelas) e `*_res.json` (resultados), `sonda_r4.py {a,b,c}` (herdada do crítico da R4 anterior, regimes não testados pela onda 7), `sonda2_r4.py {d,e}` (vazamento e pico de latência do heap), `sonda3_r4.py {f,g}` (regressão do relógio, rotação da dedup). Nenhum arquivo de produção foi alterado por esta revisão.*
