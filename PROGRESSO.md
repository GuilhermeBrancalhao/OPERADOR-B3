# FLUXO PRO — Gauntlet Loop (progresso ao vivo)

Objetivo: plataforma própria de leitura e interpretação de fluxo do mercado futuro (WDO/WIN),
nível institucional (barra: Profit Pro da Nelogica), em Python, com:
- leitura em tempo real (camada de dados plugável: replay histórico, simulador, adaptadores MT5/ProfitDLL/Cedro)
- ferramentas de fluxo: times & trades, DOM/book, footprint, volume profile, delta, agressão, absorção, rastreio de player
- motor de sinais 100% parametrizável pelo usuário
- aprendizado contínuo (estatística online sobre acerto dos sinais)
- modo sinais por padrão; execução real atrás de interface desativada (usuário liga com credencial própria)

## Barra de qualidade
1. **UI**: screenshots reais do Profit Pro (armazenados em `bar/`) — comparação cega lado a lado.
2. **Motor**: replay determinístico (mesmo input → mesmo output), suíte de testes verde,
   latência do pipeline de analytics < 5ms por evento de tick em replay acelerado.
3. **Metodologia**: checklist dos conceitos de leitura de fluxo extraídos do canal @SergioGargantini
   e material ASG — cada conceito coberto por um módulo mensurável.

## Roteamento de modelos
| Papel | Tier | Modelo | Esforço |
|---|---|---|---|
| Lead | T3 | sonnet (sessão) | alto |
| Pesquisa/aquisição da barra | T1-T2 | haiku/sonnet | baixo |
| Builder visual/novel (UI, footprint) | T3 | opus | alto |
| Builder padrão (motor, testes) | T2 | sonnet | médio |
| Builder mecânico | T1 | haiku | mínimo |
| Crítico de gosto/UI | T3 | opus | alto |
| Crítico mensurável | T0+T1 | comando+haiku | mínimo |

Orçamento do run: ~2M tokens. Reserva de críticos: ~500k (não gastar em build).

## Decisões tomadas no lugar de perguntas
- Não consigo assistir vídeo/áudio: metodologia reconstruída de transcrições + artigos. (limitação declarada)
- Sem feed pago de dados B3 nesta máquina: camada de dados nasce com replay/simulador + adaptadores prontos para MT5/ProfitDLL/Cedro. (recurso pago ausente — não bloqueia o build)
- Execução real NUNCA sai ligada por padrão; eu não executo ordens — entrego a interface, o usuário conecta.
- Projeto novo em pasta própria `fluxo_pro/` (regra: não misturar projetos).
- Nome de trabalho: **FLUXO PRO** (troca quando o dono quiser).

## A METODOLOGIA (extraída de transcrições reais dos vídeos)

Estrutura do sinal ASG, confirmada com citação direta em 3 vídeos:

**Sequência de 3 condições (confluência obrigatória, nesta ordem):**
1. **Direção do dia** — indicador percentual comprador × vendedor ultrapassa ~**70%**. Abaixo disso ("51% contra 49%") não há trade.
2. **Retorno à região do Smart Money** — o preço faz pullback e volta a uma **faixa** de preço (não um preço exato) marcada pela ferramenta. A ferramenta **recalcula essa região dinamicamente** conforme o fluxo muda.
3. **Virada da "micro"** — o fluxo de curtíssimo prazo (seta + histograma) precisa virar na direção pretendida. "Você nunca vende enquanto essa seta tiver apontando para cima."

**Pré-sinal ("blackout" / farol amarelo):** antes da confirmação plena o histograma passa de cor cheia para **cinza/amarelo** — perda de força do lado dominante, ainda sem validar entrada.

**Ondas / regiões de microfrequência:** faixas onde o preço tende a oscilar lateralmente por segundos a minutos (briga institucional / distribuição de ordens). Regra: não vender no fundo da região nem comprar o topo. Rompeu a região → embala o próximo movimento; não rompeu → tende a voltar.

**Absorção:** um lado agride, o outro segura sem deixar o preço avançar → aviso "vendedor absorvendo a compra". É alerta de atenção, não entrada por si só.

**Gestão de risco (3 camadas):**
- *Stop de pânico* — longe, "cinto de segurança" para evento inesperado (notícia/tweet). Não é o stop esperado.
- *Stop manual pela cor* — "piscou verde, zera". Troca stop de 150-200 pontos por 30-40.
- *Parcial* — relativa a perfil; para iniciante, proteger cedo.

**Força do movimento:** a aceleração da micro mede a força. Acelerando na direção → alonga a operação. Virou → sai.

### Cobertura do canal
54 vídeos no canal. 15 transcritos na primeira passada. Download das 39 legendas restantes em curso — inclui a série **SNIPER ASG** completa (18 aulas), **Maker: rastrear HFTs e robôs** (2 partes), **Linha Azul e Regiões**, **Gráfico Renko**, **Smart Money + Porcentagem**, **IA ASG "Velocímetro" com Machine Learning**, aulas ao vivo de WINFUT e aulas básicas. As lacunas abaixo devem fechar com esse material.

**LACUNAS honestas do extrator** (não inventar): os termos "agressão", "delta", "exaustão", "defesa de preço", "renovação de oferta", "mão cheia/mínima" e a regra de "3 stops seguidos" **não aparecem** nos 3 vídeos lidos — estão em outros vídeos ainda não extraídos. O % comprador×vendedor é provavelmente o equivalente funcional de delta, mas ele nunca chama assim.

## ACHADO CRÍTICO — identidade de corretora não existe em WDO/WIN

O aprofundamento do feed UMDF derrubou uma premissa que eu tinha herdado da barra (o Profit Pro tem "Ranking de Corretoras"):

**Nenhum dos três caminhos de dados garante ver a corretora por trás da ordem nos minicontratos.** Os campos de identificação de contraparte só existem fora de negociação anônima, e o mecanismo RLP da B3 anonimiza por regra de negócio parte do volume de WIN/WDO — isso é característica do produto, não de nível de acesso. Pagar mais não resolve.

Custos apurados dos caminhos:
- **(A) MetaTrader5** — R$ 0, dias de setup. Nunca mostra corretora.
- **(B) Vendor pago (Cedro / ProfitDLL)** — preço sob consulta, semanas de atrito. Nenhum dos dois confirma publicamente entregar book por ordem com identidade.
- **(C) UMDF direto** — ~R$ 190-200 mil/ano (uso interno via vendor) a ~R$ 290 mil/ano (acesso direto), fora conectividade, e exige decoder FAST/SBE em C/C++/Rust (não há biblioteca Python pronta). Meses de trabalho.

**Consequência de design (e ela é boa):** o rastreio de player em WDO/WIN não pode se apoiar em identidade — tem de ser **inferido por comportamento**: assinatura de clip, regularidade de intervalo, reposição em nível, razão volume-executado/exibido. É exatamente a camada de microestrutura já em construção, que passa de "diferencial" a **espinha dorsal do produto**. O `RankingCorretoras` dos analytics vira ferramenta secundária, útil só onde o dado existir.

**Pendência para o dono:** confirmar por e-mail com marketdata@b3.com.br se a leitura por corretora é viável hoje nesses contratos, antes de qualquer gasto com (B) ou (C). Recomendação: ficar em (A) e investir o esforço na inferência comportamental.

## Rodadas
| Peça | Rodada | Papel | Modelo | Veredito | Gap |
|---|---|---|---|---|---|
| **Núcleo** (eventos/book/replay/simulador) | 1 | builder | sonnet | ✅ verde | book é MBP, `n_orders` sempre 1 → sem ordem individual (resolvido pela peça de microestrutura) |
| **Analytics** (volume, footprint, delta, agressão, brokers, vwap) | 1 | builder | sonnet | ✅ verde | 7 módulos completos, 0 falhas |
| **Microestrutura/MBO** — livro + inferência MBP→MBO | 1 | builder | opus | ✅ verde (sobreviveu ao corte de contexto) | |
| **Microestrutura — detectores** (absorção/escora/iceberg/liquidez fantasma/exaustão/clip) | 2 | builder (eu, direto) | sonnet | ✅ verde, 20 testes | escrito após o corte, sem agente em background |
| **Perfil de player** (ranking por corretora) | 2 | builder (eu, direto) | sonnet | ✅ verde, 5 testes | |
| **Motor de sinais** (confluência das 3 condições ASG) | 2 | builder (eu, direto) | sonnet | ✅ verde, 6 testes | reconstrução funcional da lógica, não cópia pixel-a-pixel da ferramenta original — declarado no docstring |
| **MT5 + Gravador** (conexão, gravação, catálogo, CLI) | 1 | builder | sonnet | ✅ verde (sobreviveu ao corte; 1 bug real corrigido depois — normalização de tick 0-d do numpy) | |
| **Direção visual + stack de UI** | 1 | builder | opus | ❌ **FALHOU** — limite de gasto mensal atingido a meio do trabalho | scripts de benchmark parciais ficaram em `design/bench/`; **nenhuma decisão de stack foi tomada**; documento `design/direcao_visual.md` não existe |
| **Crítico do núcleo** (mutação + benchmark) | 1 | crítico | opus | ❌ **FALHOU** — mesmo limite | **núcleo nunca recebeu teste de mutação nem benchmark de carga real** — ninguém provou que aguenta o volume do WDO em dia agitado |
| **Legendas 54 vídeos** | 1 | pesquisa | haiku | ⚠️ parcial — 40+ vídeos baixados antes do corte (ver `pesquisa/legendas/`), mas **nenhum foi extraído/estruturado** como os 3 primeiros (só texto bruto) | metodologia continua baseada nos 3 vídeos originais |
| **Feed B3 UMDF** (aprofundamento) | 2 | pesquisa | sonnet | ✅ completado | identidade de corretora NÃO existe em WDO/WIN por design B3 (RLP anonimiza até 15%) |

## Onda 3 — retomada do gauntlet (limite de gasto liberado)
| Peça | Papel | Modelo | Estado |
|---|---|---|---|
| **Crítico adversarial do núcleo** | crítico | opus | ❌ **NÃO PASSA** → `criticas/nucleo_r1.md` |

### VEREDITO DO CRÍTICO: NÃO PASSA. A barra não estava baixa.
Núcleo e analytics passam com folga. **Os detectores de microestrutura — que são o produto — falham por duas ordens de grandeza.** Eu escrevi esses detectores no turno anterior e os apresentei como prontos; estavam errados.

**MAIOR GAP — `microestrutura/detectores.py:72`**: `DetectorAbsorcao.ao_trade` reconstrói a janela inteira a cada trade, mais 4 varreduras completas. Janela de 5s a 10.000 trades/s = 50.000 trades guardados; custo por trade cresce com a taxa do mercado ⇒ **custo total quadrático**. Fica mais lento exatamente quando o mercado fica interessante. Medido: **42 trades/s contra os 10.000 necessários — 236× lento demais**. `analytics/agressao.py` já resolve a mesma janela deslizante com `deque` + contadores O(1), dez arquivos ao lado — eu não olhei.

**`DetectorIceberg` é invenção, e a álgebra prova**: `razao = (n_reposicoes × exibido_max) / exibido_max = n_reposicoes`. O `exibido_max` **cancela** — a grandeza que o detector afirma medir é a única que ele garantidamente ignora. E `razao_minima=3.0` é literalmente o gatilho do `DetectorEscora`, então a mesma sequência emite ICEBERG e ESCORA juntos. O campo `volume_executado_estimado` na evidência nunca observou execução alguma.

**`DetectorAbsorcao` dispara em 98,2% dos trades** num tape lateral de 1 tick com config de fábrica, e não tem deduplicação — re-emite a cada trade.

### Mutações: 12 de 33 sobreviveram (36%)
`core/` e `analytics/` estão genuinamente cobertos (18 de 21 mutantes morreram). Os sobreviventes se concentram num só lugar: **`livro_mbo.py` — 606 linhas, o arquivo mais intrincado, tem ZERO testes diretos.** É importado só como fixture. Sobreviveram: fila **FIFO virando LIFO**, `melhor_bid()` devolvendo o **pior** bid, `popleft()`→`pop()`, `qty_a_frente` somando em vez de descontar, janela de reposição 1000× maior. Inverter a prioridade preço-tempo — que **é** o diferencial do produto — é invisível aos 94 testes.

### Benchmark (500k eventos, 5.000 trades/s)
| Estágio | ev/s | µs/ev | |
|---|---|---|---|
| barramento vazio | 106.934 | 9,35 | PASSA |
| + EstadoMercado | 61.280 | 16,32 | PASSA |
| + analytics (6 módulos) | 55.612 | 17,98 | PASSA |
| **+ detectores** | **42–1.587** | **630–23.583** | **NÃO PASSA** |

Memória: 2,5 MB (5,2 bytes/evento), sem vazamento. Núcleo+analytics sozinhos: ~116.000 ev/s, folga de 11×.

### Defeitos estruturais encontrados
- **Livro cruzado aceito em silêncio** (bid 10005 / ask 10001, sem exceção nem flag).
- **Nenhum sequence number** em `Trade`/`BookDelta`/`BookSnapshot` ⇒ gap de feed indetectável.
- **Virada de sessão não existe**: só `VolumeProfilePorPeriodo` reseta; `delta_sessao`, `Sessao.high/low` e `VWAP` acumulam para sempre.
- **`AgressorSide.UNKNOWN`** (leilão, RLP) entra no volume mas some do delta ⇒ `volume ≠ delta_buy + delta_sell`, sem contador de volume não atribuído.
- Hipótese do crítico **rejeitada por ele mesmo**: suspeitou de perda de precisão no VWAP, testou um dia inteiro (600k contratos), erro exatamente zero. Só vira defeito combinado com a falta de reset de sessão (cruza 2⁵³ por volta do 43º pregão contínuo).

## RODADA 2 DA CRÍTICA: **NÃO PASSA** (`criticas/nucleo_r2.md`)

As correções da onda 4 são **reais, mas parciais** — e o crítico achou coisa pior do que a rodada 1.

### O maior gap: eu repeti o defeito que acabara de mandar corrigir
`motor/sinais.py:109` e `:135` — `_dominancia` e `_micro_virou` reconstroem lista + somam varrendo, por trade. **É a mesma linha que a R1 condenou em `detectores.py:72`**, copiada para o motor de confluência, com a janela **60× maior** (5 minutos). Agravada por `_na_regiao`, que chama `val()` e `vah()` — e cada uma roda um `value_area()` separado com `sorted()` completo: **dois sorts por trade** no caminho quente. Eu escrevi esse código depois de ler o relatório que condenava exatamente esse padrão.

### O benchmark da onda 4 não media o sistema
`bench_carga.py` **nunca instancia `MotorSinais`**. Com N idêntico (40.000):

| Estágio | ev/s | |
|---|---|---|
| + 3 detectores | 25.230 | PASSA |
| **+ MotorSinais** | **258** | **NÃO PASSA — 39× abaixo** |

Uma peça colapsa o pipeline em **98×**. Escalonamento do motor isolado ao dobrar N: ×4,64 / ×4,31 / ×3,16 / ×4,38 — **quadrático**. O sistema inteiro roda a **258 ev/s**, não a 10.000.

### O que foi genuinamente corrigido
9 de 12 re-mutações da R1 agora morrem. O `livro_mbo.py` foi coberto de verdade (FIFO→LIFO derruba 17 testes). O `DetectorAbsorcao` mediu **609.916 trades/s** — a alegação de 239.639 era conservadora — e as deques monotônicas estão **semanticamente corretas**: 0 divergências em 80.000 comparações contra varredura ingênua. As adições da onda 4 estão bem cobertas: **5 de 5 mutações mortas**. Onde a onda 4 mexeu, ela testou.

### O que continua vivo, contrariando o "corrigimos tudo"
- **M06** (`round()`→`int()` no `PriceGrid`) e **M09** (relógio de replay retrocede) **seguem vivas**.
- **20 de 33 mutações NOVAS sobreviveram (61% — pior que os 36% da R1).**
- **`inferencia_mbp.py`: 476 linhas, ZERO testes, 4/4 mutações vivas.** Inclui inverter o lado passivo e **transformar hipótese em fato** (confiança 0.55→1.0) — apagando a distinção observado × inferido que é a virtude declarada do projeto.
- **A cadeia de integridade da gravação pode ser inteiramente desligada com a suíte verde**: `verificar_integridade` aprovando tudo, o leitor não levantando exceção, e o recorte de horário do replay virando `return True`.

### Dois defeitos de lógica no motor — código meu
1. **`pre_sinal` tem rótulo falso.** `delta_inicio` nunca é comparado com a segunda metade. Medido: micro melhorando, parada, ou **piorando 4× contra** produzem os três o mesmo `PRE_SINAL`. O "farol amarelo" acende igual nos três casos.
2. **O modo de falha do WINFUT reproduz inteiro.** Fase vendedora de magnitude alta seguida de fase compradora de magnitude menor faz o motor emitir `CONFIRMADO` de compra, com `dominancia = 0.900` idêntica nas duas fases. E **1 único trade** leva de `CONFIRMADO` a `NENHUM` — zero histerese, contra o "se ele se sustentar" da fonte. Eu tinha registrado esse modo de falha no próprio PROGRESSO e implementei o motor sujeito a ele mesmo assim.
3. **As faixas de convicção não estão implementadas** — só um corte binário; a faixa 80-85% não existe. E a divergência 70% × 75% documentada na fonte foi omitida do docstring.

### Para dinheiro real, além de tudo acima
`MotorSinais` e `InferidorMBP` **não são importados por nenhum módulo de produção** — o produto ainda não foi montado. E nenhuma medição de qualidade de sinal tocou tape real: tudo saiu do `SimuladorWDO`, **cujas dinâmicas de preço podem ser invertidas sem quebrar um teste**.

## RODADA 3 DA CRÍTICA: **NÃO PASSA** (`criticas/nucleo_r3.md`)

### O maior gap era meu, e não era de código: o `.gitignore`
O padrão `dados/` que **eu** escrevi não estava ancorado na raiz, então casava também com `fluxopro/dados/`. **Sete módulos de código-fonte (~1.400 linhas) ficaram fora do controle de versão** — incluindo `mt5.py` (a única fonte ao vivo) e `simulador.py` (a fonte de toda medição de qualidade já feita). Clonar o repositório e coletar os testes dava `ModuleNotFoundError`: **o repositório não reconstruía o produto**.

O efeito colateral é pior que a perda: `git diff -- fluxopro/` era **estruturalmente cego** a esses arquivos. As provas de "árvore limpa" das rodadas 1 e 2 passavam por cima deles sem enxergar nada — a R2 mutou dez coisas em `fluxopro/dados/` e fechou com diff vazio. Uma mutação esquecida ali teria entrado no produto sem ninguém notar.

**Corrigido e provado**: padrão ancorado (`/dados/`) com o porquê escrito no arquivo; clone limpo agora coleta **401 testes** (antes 277 com 5 erros de import).

### O que a R3 confirmou como genuinamente corrigido
13 das 20 mutações sobreviventes da R2 morrem (N24 derruba 19 testes; N26 derruba 31). As três dívidas antigas da R1 (M06/M09/M27b) fechadas. `MotorSinais` a 152.874 ev/s com custo por evento **plano** — o defeito quadrático dele acabou de verdade, e os números do builder conferem sem inflação. Replay reproduz o vivo (0 divergências em 4.000), determinismo idêntico em 500k eventos.

### O que continua quebrado
1. **`mt5.py:214-215` — o feed trava para sempre, em silêncio, acima de 1.000 negócios/s** (dez vezes abaixo da barra). O cursor é truncado ao segundo e a chamada devolve sempre os mesmos 1.000 primeiros. Reproduzido: 1.000 de 3.000 ticks entregues, resto perdido, **zero `FalhaCaptura`** — o detector de gap mede intervalo de *poll*, não de *dado*. E o mock do teste ignora os parâmetros, então nenhum teste podia pegar.
2. **O quadrático mudou de casa pela terceira vez**, agora em `inferencia_mbp.py`. No regime real do WDO (preço cravado, spread 1 tick): 17.676 → 11.332 → 6.677 → 2.877 → **1.639 passos/s** conforme o tape acelera. A docstring publica uma tabela medida no **eixo errado** (largura do book) afirmando curva plana — a correção anterior otimizou e mediu o eixo que não domina o custo.
3. **Pipeline com tudo ligado: 7.851 ev/s**, abaixo da barra.
4. **Dois relógios na borda** (servidor × local): a mesma sequência vira `CANCEL` em vez de `TRADE`, e **uma gravação real fica irreproduzível** — no replay saem todos os books primeiro, todos os trades depois.
5. **O teste do WINFUT é honesto, mas está no único ponto da curva em que o gate segura.** O crítico construiu a variante que **passa**: com 20.000 trades laterais entre o pico e o repique, o p95 do reservoir desce e o motor emite **480 sinais de compra**.
6. **14 de 28 mutações novas sobreviveram (50%).** Pior módulo: `perfil_player.py` — inverter quem agrediu passa batido.
7. **8 de 12 componentes não têm `iniciar_nova_sessao`**, incluindo o `MotorSinais`: o p95 do dia 2 é o do dia 1.

## RODADA 4 DA CRÍTICA: **NÃO PASSA** (`criticas/nucleo_r4.md`)

### O maior gap foi criado pela correção da onda 7 — a 5ª casa
`inferencia_mbp.py:759-763` — `_registrar_preco` faz `heappush` incondicional a cada transição `0 → qty` de nível, sem dedup, sem teto, com poda preguiçosa só pela cabeça do heap. Medido: **2.400.001 entradas de heap para 2 níveis vivos** após 16 min a 5.000 ev/s, e **244 ms de latência num único evento** quando o topo esvazia (orçamento: 100-200 µs). Invisível porque o µs/passo *cai* enquanto a estrutura infla. R1 detectores → R2 motor → R3 inferência → R3 livro → **R4 inferência de novo, pela mão que consertou**.

### O que a onda 7 acertou (medido, não aceito)
- **MT5: 50.000 ticks/s com zero perda — confere.** Melhor peça das 4 rodadas.
- **Inferência: 1,00× plano, e resiste a 3 regimes que os builders não testaram** (preço cravado + cancelamento massivo + recarga; alternância rápida de topo; recarga sob topo estável): 0,98× a 1,04×.
- **Fiação `app/`: melhor território das 4 rodadas** — 7 de 10 mutações morrem, incluindo as 3 inversões de prioridade do barramento.

### Os outros três motivos
2. **182 testes novos, e as 20 re-mutações da R3 sobrevivem — zero mortas.** Os testes são bons mas vivem só nos 3 módulos do escopo dos builders. `perfil_player.py` entra na 4ª rodada com as 3 inversões da própria semântica passando.
3. **O relógio de máximo é uma catraca.** Regressão do servidor (troca de servidor da corretora, NTP) trava o offset inflado **para sempre** — 5.000 amostras corretas não o movem. 400 ms de regressão já excede a janela de reconciliação e reintroduz o modo de falha da R3, agora permanente.
4. **Pipeline sem resposta medida**: 5.873 ev/s (simulador cru, NÃO PASSA) × 14.236 ev/s (book estável, PASSA). A barra cai *dentro* do intervalo, e ambos os regimes são sintéticos.

### Achados menores
- **Dedup 4.096 é penhasco, não degradação**: 0% de re-emissão em 4.096 chaves, **100% em 5.000**. E a consequência não é aceitável: Iceberg e Fantasma usam `order_id` sintético (6,5/evento) ⇒ **63 ms de memória** contra um fenômeno que dura segundos.
- **WINFUT com 20.000 laterais: idêntico à R3** — 480 `CONFIRMADO` espúrios. O gate continua cedendo (o builder do motor não estava na onda 7).
- **`qty_minima_imbalance = 0` está preso por teste** — cimento, não contrato.
- **Parte D inalterada**: `MetaTrader5` não instalado, `dados/` não existe, zero bytes de mercado em disco. Nenhuma linha de `mt5.py` jamais executou contra corretora.

Nota de método do crítico: a prova "byte a byte contra o blob de HEAD" da R3 **não reproduz** com `core.autocrlf=true` — a conclusão estava certa, o método não. A R4 normaliza CRLF: 66 arquivos, 0 divergências reais.

## Onda 8 — correções da R4

| Peça | Modelo | Estado |
|---|---|---|
| Inferência: 5ª casa (heap sem dedup/teto em `_registrar_preco`) | opus | 🔄 em voo |
| MT5: relógio de máximo vira catraca — precisa esquecer | opus | 🔄 em voo |
| Detectores: dedup 4.096 é penhasco; `order_id` sintético estoura em 63 ms | opus | 🔄 em voo |
| Motor: WINFUT com 20.000 laterais ainda fura o gate | opus | 🔄 em voo |
| Testes fracos: `perfil_player`, `brokers`, `simulador`, `footprint` (cimento) | sonnet | 🔄 em voo |

## Onda 7 — correções da R3 (retomada após queda por limite de gasto)

Os 3 builders da onda 7 caíram por limite de gasto mensal **no meio da escrita**: `detectores.py` (+516 linhas) e `mt5.py` (+365 linhas) ficaram em disco SEM os testes correspondentes — código de produção novo com suíte cega, que é o estado mais perigoso possível (1 teste da app quebrou por referenciar a API antiga; o resto passa sem exercitar nada do que mudou). O terceiro (inferência) morreu sem escrever nada.

Retomada com 3 builders novos, cada um instruído a **auditar o parcial antes de confiar nele**:

| Peça | Estado |
|---|---|
| **Detectores: completar parcial + retenção/confiança/dedup** | ✅ **26 → 67 testes, 21/21 mutações mortas, 7 pontas soltas no parcial + dupla penalização achada** |
| **MT5: completar parcial + mock honesto + 3.000 ticks/s** | ✅ **10 → 36 testes, 14/14 mutações mortas, 3 defeitos NOVOS achados no parcial** |
| **Inferência: quadrático (3ª casa) + `esta_cruzado`** | ✅ **12/12 mutações mortas, 15,7× → 1,00× no eixo certo, e achou a 4ª casa do quadrático** |

### Detectores — o mecanismo de procedência estava INERTE no produto
A auditoria do parcial achou 7 pontas soltas, e a mais grave redefine o que o parcial "entregou": **`acompanhar()` — a fiação inteira de propagação de confiança — tinha zero chamadores.** O mecanismo existia, era bonito, e estava desligado: toda detecção saía `procedencia: DESCONHECIDA`, confiança 1,0. O builder ligou em `sessao_fluxo._ligar_livro` e mediu o A/B no pipeline real: sem fiação, 0,85 publicado; com fiação, **0,55** — a fronteira sozinha publicava 0,85 para uma cadeia cujo elo mais fraco é 0,55.

E ao ligar, apareceu uma **dupla penalização**: a fronteira multiplicava a confiança do gatilho, que agora já está NA cadeia — 0,55 × 0,55 = 0,30, pessimismo fabricado. Corrigida para `min` (o mesmo t-norm do detector).

**Retenção, medida contra o HEAD real** (via `git show HEAD:` — não de memória):

| detector | retidos ANTES | DEPOIS |
|---|---|---|
| Exaustão (200k trades) | **200.000** | **5** |
| Escora (50k níveis) | 50.000 | 4.096 (teto FIFO) |
| Iceberg (50k ordens) | 50.000 | 4.096 |
| Fantasma | sem dedup — re-emitia | 4.096 |

**Auto-mutação 21/21** — e uma sobrevivente era **gap real, não mutante equivalente**: neutralizar a checagem de âncora da Exaustão passava por todos os testes porque em todos a mudança de âncora roteava por outro gatilho antes. Um fuzz sobre 23.308 emissões achou **914 casos** em que não roteava (`progrediu` compara as *pontas* da janela — preço que vagueia no meio e volta move a âncora invisivelmente). Fixado com traço determinístico de 7 trades + controle, e registrado como `PENDENTE(sensibilidade)`.

Aviso operacional registrado: um harness de mutação anterior morreu no meio e **deixou o arquivo mutado em disco** — o snapshot de bytes pegou; `git diff` sozinho não diria qual das 600 linhas era a mutação. Performance por detector: 3× a 50× a barra; a fiação custa +6,1% em DOM realista (passa a barra), +19,5% no simulador (viés documentado do simulador, não da mudança).

### Inferência — o quadrático morto no eixo certo, e a 4ª casa encontrada
**Estrutura**: índice por `(preço, lado_passivo)` — as duas pernas da reconciliação viraram a chave, e `_lado_casa` (15,7 milhões de chamadas na R3) foi **deletado**: o teste de lado dentro do laço era exatamente o custo. Bucket extra para agressor `UNKNOWN` (casa com os dois lados), consumo intercalado por ordem de chegada, `popleft` de prefixo morto — O(1) amortizado. Detalhe fino: código do lado como `int` na chave, porque `Enum.__hash__` é método Python hasheado 3×/negócio — medido, com enum a correção ficava 3× mais cara no caminho frio.

**A curva, medida em candidatos percorridos por passo** (métrica determinística — tempo de parede varia 4× nesta máquina, e foi confiando nele que a rodada anterior se convenceu do eixo errado):

| tape/s | ANTES | DEPOIS |
|---|---|---|
| 500 → 10.000 | 149 → 2.337 (**15,7×**) | **1,0 → 1,0 (1,00×)** |

Tempo de parede a 10.000/s: 1.532 → **45.154 passos/s**. E a prova do erro anterior: **o eixo antigo (largura do book) mede 0,0 candidatos percorridos** antes e depois — o laço nem rodava ali; era isso que a tabela publicava como prova de velocidade.

**`esta_cruzado` — atribuição pela causa, não por relógio.** O inferidor declara ao livro a defasagem de liquidez que ainda deve (`registrar_liquidez_nao_aplicada`), e a resposta sai da **diferença entre o que o livro exibe e o que o feed diz existir** — não de um contador paralelo que dessincroniza. `n_cruzamentos_detectados` volta a significar corrupção de fonte; `n_cruzamentos_por_reconciliacao` registra o transitório (não é anistia silenciosa); e o mecanismo **auto-corrige**: episódio que persiste depois da explicação sumir passa a acusar. Medido: feed limpo 5 → 0 acusações; feed corrompido 1 → 1, com alerta.

**A 4ª casa do quadrático — encontrada por profiling, fora do escopo pedido**: `livro_mbo.py:ultima_ordem_ativa` varria `reversed(nivel.fila)` a cada cancelamento inferido, e o sufixo de ordens mortas crescia a cada um — O(n²) por nível ao longo do pregão, **segundo maior custo do pipeline inteiro**. Corrigido com poda pelo fim, espelho da que `executar` já fazia pela frente. R1: detectores. R2: motor. R3: inferência. Agora: livro. A forma é sempre a mesma — varredura que cresce com o estado acumulado.

**Y4 sobreviveu na primeira rodada e o defeito era do TESTE**: a suíte de custo comparava só a *forma* da curva (razão entre taxas), então uma degradação que cresce com a duração da sessão passava. Teto absoluto + eixo de duração de pregão adicionados; o buraco está documentado para não voltar.

Duas pendências medidas e apontadas: `.mut/bench_r3.py` estágio 6 **mede o eixo errado de novo** (o simulador espalha preços, a patologia não dispara — quem usar aquele número como portão repete o erro), e `Enum.__hash__` com ~1M de chamadas no estágio 6 (constante, não crescimento; cirurgia ampla demais para builders em paralelo).

### MT5 — o parcial estava certo na estrutura e errado em 3 pontos que só teste honesto revela
A estratégia de paginação do builder morto estava **correta** (cursor `(time_msc, ordem_no_ms)`, escalada de `count` na saturação, `FalhaCaptura` em cursor congelado). Mas ao escrever os testes contra um mock que honra `de`/`count`, apareceram 3 defeitos do próprio parcial:

1. **O relógio único mentia com o tape parado.** O offset servidor-local era estimado pela *última* amostra — mas um tick só pode ser visto depois de acontecer, então toda amostra subestima. Mercado quieto ⇒ o mesmo tick velho re-observado a cada poll ⇒ relógio derivado **preso na hora do último negócio** (erro medido: −60s, crescendo 50ms/poll). Todo `BookSnapshot` sairia carimbado no passado, 200× fora da janela de reconciliação. O parcial matou "dois relógios" e criou "um relógio que mente". Corrigido com estimador de **máximo**: erro constante, limitado pela idade do tick mais fresco.
2. **Partida a frio do epoch**: cursor zerado fazia `copy_ticks_from(sym, 0, ...)` devolver os primeiros ticks **do histórico, de anos atrás**, publicados como tape ao vivo. Agora o primeiro poll semeia o cursor com `symbol_info_tick`.
3. **O(n²) sobre o segundo**: `date_from` em segundos re-recebe o segundo inteiro a cada poll e o laço varria tudo de novo — 36% de um núcleo a 10k ticks/s. Busca binária pelo ms do cursor: caiu a 12,4%, linear de novo.

**Números**: ~80.000 ticks/s sustentados, **zero perda até 50.000 ticks/s** (5× a barra). Antes: 1.000 de 3.000 entregues e o feed morto para sempre. O mock novo respeita cursor e count — a mutação T08 sobreviveu na primeira rodada e o builder reescreveu o teste (congelando `time_ns`) até ela morrer, em vez de aceitar.

Decisão registrada como não-goal: **sem detector de staleness de dado** — sem calendário de sessão, tape quieto e feed morto são indistinguíveis e o alarme seria falso-positivo o dia todo; a saturação de cursor cobre o modo de falha que a R3 mediu.

## Onda 6 — o produto montado (e 5 defeitos que 3 auditorias não pegaram)

`fluxopro/app/` + `scripts/operar.py` existem: `ConfigOperacao`, `SessaoFluxo`, `ConsoleFluxo` e um CLI que roda com simulador (sem corretora), replay ou MT5. **401 testes verdes.** O CLI foi executado de verdade e imprime sinais, detecções com evidência, e resumo de sessão.

**Ordem de prioridade do barramento** declarada com teste de comportamento: perfil de sessão antes do motor (senão o motor lê o mercado de um trade atrás) e `InferidorMBP` antes do motor. Uma escolha fina: o motor recebe `VolumeProfile` de sessão e **não** `VolumeProfilePorPeriodo` — este último *troca o objeto* na virada de bucket, e o motor guardaria referência a um perfil morto, em silêncio.

**Limitação real do `Barramento`, reportada em vez de escondida**: sete componentes assinam a si mesmos no construtor sem parâmetro de prioridade, então a montagem não consegue ordená-los — a única alavanca é a ordem de construção. Mitigado (tudo que a app assina usa prioridade explícita, com teste prendendo os 13 assinantes na ordem exata), não resolvido na raiz.

### 5 defeitos que nenhuma das 3 auditorias pegou
1. **`DetectorExaustao` vaza memória sem limite**: 200.000 trades entram, 200.000 ficam retidos — a 5.000 trades/s × 6h são ~108 milhões de objetos vivos. O `DetectorClipInstitucional`, 60 linhas abaixo, já fazia certo.
2. **Detectores de livro publicam hipótese como fato**: emitem `confianca=1.0` fixo sobre um `LivroMBO` que em MT5/simulador é inteiramente sintético.
3. **`esta_cruzado` não significa "feed corrompido" em modo MBP**: 14 cruzamentos em 1.200 eventos limpos, porque a ponte cruza o livro **por construção** enquanto reconcilia.
4. **`DetectorExaustao` sem deduplicação**: dispara 2-3 vezes no mesmo preço em 30 ms.
5. Virada de sessão: dois componentes carregam o dia anterior e a app **não tem como consertar**, porque assinam no construtor e o `Barramento` não expõe `desassinar`.

### Sobre o benchmark: 8.853 ev/s, com diagnóstico
12% abaixo da barra — mas o builder mediu a causa em vez de justificar: o `SimuladorWDO` regenera o fundo do book a cada tick, gerando **6,5× mais eventos de ordem** que um DOM real. Controle medido: com book estável, o mesmo pipeline faz **17.659 ev/s**; a microestrutura isolada faz 86.444 ordens/s. Qualquer benchmark futuro que use o simulador herda esse viés.

## Onda 5 — correções da rodada 2

| Peça | Modelo | Estado |
|---|---|---|
| **Motor de sinais: O(1) + faixas + WINFUT + histerese** | opus | ✅ **6 → 33 testes, 8/8 mutações mortas** |
| **Inferência MBP→MBO: 476 linhas sem teste** | opus | ✅ **0 → 61 testes, 17/17 mutações mortas, 3 defeitos reais** |
| **Integridade da gravação + M06 + M09** | sonnet | ✅ **31 testes, 8/8 mutações mortas** |

### Inferência MBP→MBO — de zero a 61 testes, e 3 defeitos reais achados

**Defeito 1 — o agressor `UNKNOWN` recebia confiança máxima (0,90).** A reconciliação tem duas pernas: preço e lado passivo. Com `UNKNOWN` a segunda simplesmente não acontece — e mesmo assim a execução saía valendo o mesmo que uma com lado confirmado. Não é hipotético: o RLP anonimiza parte do volume de WDO/WIN. Corrigido com teto configurável (aplicado por `min`, nunca por atribuição) e `lado_passivo_confirmado` na evidência.

**Defeito 2 — evidência autocontraditória.** Numa queda fora do topo com negócio impresso *naquele mesmo preço*, o saldo saía com confiança 0,90 e a ressalva "fora do topo não havia como negociar" — enquanto o próprio módulo acabara de atribuir contratos a uma execução ali. A premissa da confiança alta estava falsificada pela evidência do evento anterior.

**Defeito 3 — a docstring prometia O(1) amortizado e o código varria a janela inteira.** Cada negócio percorria todas as quedas pendentes e cada queda todos os negócios em buffer. Medido: 130.000 → 41.000 → **7.300 neg/s** com 50/200/800 níveis pendurados — **abaixo da barra**. Corrigido com índice por preço (poda preguiçosa, buckets vazios removidos): **~330.000 neg/s, plano**. A docstring agora traz a curva medida em vez da alegação.

**Sofisticação que vale registro — mutante equivalente detectado.** Depois da correção do índice por preço, a mutação N23 da R2 virou **equivalente**: o ramo `if buffer.price != pendente.price` tornou-se inalcançável, então mutá-lo não muda comportamento nenhum. O builder percebeu, verificou os dois únicos chamadores, **removeu o ramo morto** e substituiu por N23a/N23b, que atacam o mecanismo que de fato garante o preço. Mutante equivalente é a armadilha clássica do teste de mutação — tratar como "sobrevivente" levaria a escrever teste para código impossível de executar.

A mutação mais grave morta: **confiança de cancelamento 0,55 → 1,0**, que convertia hipótese em fato e apagava a distinção observado × inferido — a virtude declarada do módulo.

### Motor de sinais — o gap #1 fechado, e o modo de falha do WINFUT morto

**Performance** (mesmo tape determinístico, N=8.000):

| | antes | depois |
|---|---|---|
| ev/s | 1.135 | **184.013** (162×) |
| µs/ev | 880,95 | 5,43 |

Com N=200.000 sobre um tape de 432 níveis distintos (o número de níveis que fazia `value_area()` doer): **117.591 ev/s**. A assinatura quadrática sumiu — ao dobrar N, o µs/ev antes ia ×1,33 → ×1,85 → ×2,36; agora fica ×1,05 → ×0,98 → ×1,02. Plano até 400.000 trades.

**Pipeline completo**: o colapso de 98× ao ligar o motor virou queda de ~22%.

| Estágio | R2 | depois |
|---|---|---|
| + 3 detectores | 25.230 | 51.079 |
| **+ MotorSinais** | **258** | **39.678** |

**Como**: janela de dominância com `deque` + contadores incrementais (padrão do `DetectorAbsorcao`); janela micro em **dois** deques separados por corte temporal monotônico, o que dá a comparação primeira × segunda metade em O(1); `value_area()` chamado **uma** vez e cacheado (VAL+VAH juntos), com invalidação por contagem **ou** tempo de tape — os dois porque cada critério sozinho tem ponto cego (tape lento segura o valor por minutos; tape em rajada processa dezenas de milhares de trades sem recalcular).

**`pre_sinal` corrigido**: o corte passou a ser temporal (metades de mesma duração, não por contagem de trades) e exige que a segunda metade tenha **melhorado na direção do alvo**. Os três casos que a auditoria mediu agora se separam: −100→−20 é `PRE_SINAL`; −100→−100 e −100→−400 são `NA_REGIAO`.

**WINFUT morto, com teste-controle**: `magnitude` = |delta| da janela normalizado pelo percentil 0,95 da distribuição **do próprio dia** (reservoir sampling com seed determinística). Mais histerese: promoção exige sustentação em trades **e** tempo; rebaixamento idem — um trade isolado não derruba mais o estágio.
O teste roda 900 trades 90% vendedores de qty 20, seguidos de 900 trades 90% compradores de qty 9 (razão 0,45 — a mesma proporção do +915 contra −1925 do relato). Resultado: **nenhum** sinal de compra em todo o tape, com `bloqueio == "magnitude_relativa"`, `dominancia ≥ 0,85` e `faixa == MAXIMA_CONVICCAO` — ou seja, **não é o percentual que barra, é a magnitude**.
O que torna isso prova e não alegação: há um **teste-controle** que roda o mesmo tape com o gate desligado e **exige que o motor caia no modo de falha**. E um terceiro que garante que o gate não é um "sempre não" — movimento na magnitude do próprio dia passa a `CONFIRMADO`.

**Faixas de convicção** implementadas como enum parametrizável, com uma decisão honesta: existe uma `ZONA_CINZA` entre 0,65 e 0,70 porque **a fonte não dá rótulo a essa faixa** — preencher seria atribuir à fonte uma leitura que ela não deu. O docstring registra a divergência 70% × 75% citando os dois vídeos e a marca IMPRECISO da pesquisa, e declara 0.70 como escolha de engenharia, não leitura unívoca.

**Bônus**: testes que exercem os **defaults de fábrica** — matam duas mutações que sobreviveram na R2 (`dominancia_minima`→0.0 e janela micro→1 dia) justamente porque nenhum teste tocava a config padrão.

### Integridade da gravação — de decorativa a real
A cadeia inteira que podia ser desligada com a suíte verde agora resiste. Testes que **corrompem o arquivo de propósito** (byte alterado, truncamento, hash divergente no meta sem tocar no dado) e provam que a verificação detecta e o leitor recusa. O recorte por horário passou a ser provado de verdade: eventos fora da janela **não** voltam.

Isso importa porque o gravador é a **única** fonte de histórico de book que este projeto vai ter — não existe histórico público de book na B3. Base de replay corrompida em silêncio envenenaria todo backtest futuro.

Um defeito real corrigido no caminho: `verificar_integridade` deixava escapar `EOFError` cru num gzip truncado, em vez de reportar `False` de forma consistente.

**M06 morta** (`PriceGrid`: `round()` → `int()`): `int()` trunca em direção a zero, então diverge de `round()` em preços negativos e em frações — erro de conversão silencioso na fronteira mais crítica do sistema. Agora há 12 testes cobrindo erro de flutuante positivo e negativo.

**M09 morta** (relógio de replay retrocedendo). O código já recusava corretamente; faltava o teste e a justificativa escrita. Política confirmada e documentada: **recusar com `ValueError`**, porque as janelas deslizantes a jusante assumem tempo monotônico e aceitar retrocesso corromperia estado em silêncio. Dado fora de ordem é problema de quem alimenta o relógio — reordenar antes de chamar —, não do relógio mentir que é monotônico. Timestamp igual ao atual continua permitido, pois não é retrocesso.

**Três mutações extras fechadas por iniciativa do builder** (N14, N15, N11), por serem baratas e parte da mesma cadeia: `hora_inicio`/`hora_fim` trocados no meta, `fsync` de `FalhaCaptura` deixando de ser imediato, e inversão de ordem em `decodificar_niveis`.

## Onda 4 — correções do veredito

| Peça | Modelo | Estado |
|---|---|---|
| **Detectores: janela O(1) + decisão sobre o Iceberg** | opus | ✅ **24× de folga sobre a barra** |
| **Livro MBO: testes diretos + livro cruzado** | opus | ✅ **71 testes, 5/5 mutações mortas** |
| **Virada de sessão + volume não atribuído (RLP)** | sonnet | ✅ **189 testes, 2/2 mutações mortas** |

### Detectores — o maior gap, fechado com 24× de folga
`DetectorAbsorcao` reescrito com `deque` + contadores incrementais + **duas deques monotônicas** para max/min de preço (cada trade carrega um `seq`; o extremo só sai da frente quando é justamente o que expirou). Zero varredura.

| Tape de pior caso (preço preso em 2 ticks, config de fábrica) | trades/s | µs/trade |
|---|---|---|
| ANTIGO (quadrático) | 196 | 5.096,01 |
| **NOVO (deque O(1))** | **239.639** | **4,17** |

Contra a barra de 10.000 trades/s: **24× de folga**. E a assinatura quadrática some — no antigo o custo por trade **dobra quando N dobra** (483 → 1.549 → 2.615 → 5.575 µs); no novo fica plano (3,16 → 2,76 → 1,49 → 1,55 µs).

**Dedup com rearme de 3 gatilhos**, documentado: (1) preço deslocou além do limite; (2) o preço-âncora saiu da faixa da janela; (3) a janela esvaziou ou o lado dominante virou. A justificativa importa — absorção é um **episódio**, não um estado instantâneo, então vale um alerta por episódio. E o slot de dedup é **único**, não um `set` que cresce sem poda: uma janela deslizante só sustenta um episódio por vez.

O ruído de 98,2% caiu para **1 detecção** no mesmo tape. E a dedup não está engolindo fenômeno: naquele tape o preço nunca sai da faixa de 1 tick em 10s inteiros, então é genuinamente um episódio só.

### `DetectorIceberg`: DELETADO
O builder investigou o caminho de consertar e o encontrou **bloqueado**: `consumido_acumulado` existe em `_NivelInterno` mas o `LivroMBO` não o expõe publicamente — as leituras disponíveis (`qty_total`, `n_reposicoes`, `qty_exibida_max`) nenhuma mede volume executado. Sem tocar no livro, não havia como medir a grandeza. Deletou, e deixou no lugar a álgebra do defeito mais `# PENDENTE(livro): expor consumido_acumulado(side, price)` — com ele a razão honesta seria `consumido_acumulado / qty_exibida_max`.

Deletar código que mente é correção, não desistência. Sobrou só o `DetectorIcebergPorRecarga`, que é honesto por usar `n_recargas` observada.

**Investigação do M30 que vale registro**: o teste que *deveria* pegar "iceberg sem exigir recarga" não pegava porque **o filtro de razão barrava antes** (`500/500 = 1.0 < 3.0`), então a guarda nunca era exercida. O builder achou um cenário pela API pública que a exercita de verdade (`modificar` para cima recria a ordem preservando `qty_executada`) — teste que passa a matar a mutação.

### Pendência do `Candle` — fechada por mim
Adicionei `volume_nao_atribuido` ao dataclass `Candle` (default 0, não quebra construção existente) e à contabilização em `_atualizar_candle`, com 4 testes novos. Apliquei a mim mesmo o padrão exigido dos builders: **mutei o próprio fix** (voltando ao bug original) e confirmei que 3 testes morrem; revertido, `193 passed`.

### Livro MBO — de zero para 71 testes diretos
Todas as 5 mutações que sobreviveram à auditoria agora **morrem**, e o builder foi além: cobriu as duas leituras possíveis das linhas ambíguas. O caso mais instrutivo — os primeiros testes injetavam `ConfigLivroMBO` explícita e por isso eram **cegos a uma mutação no valor padrão de fábrica**; ele percebeu e adicionou um teste que prende o default. Suíte: **183 passed**.

**Política de livro cruzado: sinalizar, nunca levantar.** `esta_cruzado` (O(1)) + `n_cruzamentos_detectados` + callback de alerta. A justificativa é boa: exceção em `adicionar`/`executar` derrubaria a ingestão por causa de um feed ruim e deixaria o livro parcialmente aplicado — exatamente a corrupção que se queria evitar. Decisões finas: `bid >= ask` conta como anomalia (livro travado com spread zero também esconde negócio não reportado); contador **por transição**, não por evento, senão um feed cruzado por mil mensagens viraria mil anomalias em vez de uma; e prova de custo O(1) sem cronômetro, por sonda determinística que conta acessos ao dicionário.

### BUG REAL pré-existente, encontrado e corrigido (a auditoria não pegou)
**Nível esvaziado e depois repovoado sumia do topo do livro para sempre.** `melhor_bid()` limpa o preço do heap quando o nível está zerado, mas o nível sobrevive no dicionário (guarda histórico), então `_obter_nivel` não republicava. Basta um consumidor **ler** o topo no instante exato em que o nível está vazio. Reproduzido em código intocado (`git show HEAD:...`): `melhor_bid()` trava em 4999 mesmo com 7 contratos vivos a 5000. Envenena spread, o `ticks_proximidade` do `DetectorLiquidezFantasma` e o próprio `esta_cruzado` — em silêncio. Corrigido com marca `_NivelInterno.no_heap`, O(1), com teste de não-inchaço do heap.

### Sessão — política: reset explícito pelo chamador
`iniciar_nova_sessao(timestamp_ns)` em `EstadoMercado`, `CumulativeDelta`, `VWAP` e `MedidorAgressao`. A escolha por **chamada explícita** em vez de detecção automática por data está justificada: esta camada só enxerga timestamp de negócio, não o calendário da bolsa — e a sessão de WDO/WIN **não vira à meia-noite UTC** (há sessão regular + after, feriados, rolagem de vencimento). Quem quiser automático tem o helper opcional `sessao_mudou(...)` com corte de dia configurável, em vez de meia-noite cravada.

Convenção de reset uniformizada (seguindo o único precedente que já existia, `VolumeProfilePorPeriodo.nova_sessao()`): o acumulador **corrente** zera; o **histórico fechado** (`candles_fechados`, `historico`, `periodos_fechados`) sobrevive. O `MedidorAgressao` também limpa a amostra de reservoir sampling — senão o limiar de "clip grande" misturaria sessões para sempre.

Bônus: `soma_preco_qty`/`soma_preco2_qty` do VWAP passaram de `float` para `int`. Como preços são ticks inteiros, as somas agora são **exatas por construção** — o risco de precisão que a auditoria investigou deixa de existir por design, não por estar longe do limite.

### Volume não atribuído (RLP) — agora contado, não descartado
Contadores explícitos onde antes havia assimetria silenciosa: `Sessao`, `CumulativeDelta`, `MedidorAgressao`, `NivelVolume`/`VolumeProfile`, `NivelFootprint`/`Footprint`. Cada um tem teste do invariante `volume_total == comprador + vendedor + nao_atribuido` com sequência mista. Isso importa porque o RLP anonimiza até 15% do volume de WDO/WIN por regra da B3 — descartar isso em silêncio era o sistema mentir sobre a própria cobertura.

### PENDENTE herdado (fora do escopo do builder, corretamente sinalizado)
A mesma assimetria de UNKNOWN persiste no **`Candle`** dentro de `EstadoMercado._atualizar_candle`: `candle.volume` conta trades UNKNOWN, `candle.delta` não. Corrigir exige adicionar campo ao dataclass `Candle` em `core/eventos.py` — arquivo compartilhado que outros builders estavam usando. O builder deixou intacto e sinalizou em vez de tocar em núcleo compartilhado durante execução paralela. **A corrigir na próxima rodada.**

### Limitação documentada, deliberadamente NÃO corrigida
`qty_a_frente` deixa de ser a cota superior que promete quando a ordem **da frente** faz `recarregar` (iceberg): há 180 pela frente e o livro responde 100. Consertar exigiria varrer a fila — O(n) no caminho quente, fora do contrato. Fixado em `test_qty_a_frente_NAO_enxerga_recarga_a_frente_limitacao_conhecida` para virar decisão visível em vez de surpresa futura.
| **Direção visual + decisão de stack** | builder | opus | ✅ → `design/direcao_visual.md` (734 linhas) + benchmarks em `design/bench/` |

### Decisão de stack: **PySide6 (Qt 6) + pyqtgraph** — com números medidos, não opinião
| Cenário | Qt | Dear PyGui | Web (canvas 2D) |
|---|---|---|---|
| Footprint incremental (60 células) | **1,79 ms p50 · 560 fps** | 5,83 ms | 3,30 ms |
| DOM 40×6 | **1,76 ms · 567 fps** | — | — |
| Heatmap 200×600 | **5,12 ms · 195 fps** | 9,34 ms · 107 fps | — |

**O achado que decide o produto não é o toolkit — é a estratégia de desenho.** O mesmo footprint em Qt vai de **13,3 fps** (repintando o quadro inteiro, 75,2 ms) para **560 fps** (repintura incremental, só a coluna corrente). Fator **40×**. O gargalo é atravessar a fronteira Python↔C++ 7.200 vezes por quadro — 7.200 chamadas a uma função *vazia* já custam 1,04 ms.

Isso vira **restrição de arquitetura, não preferência**: nenhum painel denso pode repintar o quadro inteiro por tick. A fase 0 do plano cria `PainelDenso` (backing store + região suja + `QTimer` de 16 ms desacoplado do tick) como pré-requisito de merge, com teste de CI que **falha acima de 4 ms p95** — o número de hoje é conhecido, então regressão vira erro em vez de descoberta tardia.

**Por que as outras perdem:** Dear PyGui tem piso intransponível (render sem atualizar nada já custa 5,37 ms; modo imediato não permite repintura parcial, então o truque de 40× não existe lá) e uma única viewport de SO, o que mata multi-monitor. Web não perde por latência (ponte WebSocket custa 0,62 ms ida-e-volta, 485 B por atualização) — perde por custo total: canvas 1,8× mais lento *e* um segundo runtime, segundo idioma, protocolo binário versionado nas duas pontas, sem docking nativo. Fica reservado para um v3 remoto somente-leitura. Qt roda **in-process** com o motor (`Barramento.publicar` é síncrono, mesma thread): zero serialização, e `QDockWidget` + `saveState()` entregam docking, multi-monitor e workspace salvável sem código próprio.

### Design system
Eixo direcional **azul/vermelho, não verde/vermelho** — sobrevive a deuteranopia e protanopia, e libera verde e âmbar para o segundo canal (estado do sistema e evento detectado). Os 14 tokens passam WCAG AA ou melhor contra o fundo `#0B0E13`: compra `#3B9EFF` (6,92:1), venda `#FF5C6C` (6,44:1), absorção `#FFB224` (10,72:1) — calculados por `design/bench/contraste_wcag.py`, nenhum contraste afirmado sem medir.

Fonte: **Iosevka Term** (avanço 0,5em) contra JetBrains Mono/Consolas (0,6em) cabe ~17% mais colunas na mesma largura — uma coluna inteira a mais por monitor, num produto cuja tese é densidade.

### Fraquezas concretas da barra (8 achadas, com screenshot nomeado)
As mais graves: **três vocabulários de cor direcional empilhados na mesma janela** (candle branco/preto + delta verde/vermelho sobre book azul/vermelho); **saldo comprador e vendedor grafados identicamente** — `(49,10k)` e `(42,31k)` distinguíveis só pela cor de fundo, que é falha de acessibilidade e de robustez; os **dois lados do book em eixos de preço diferentes** na aba Profundidade, enquanto o SuperDOM do mesmo produto faz certo; e um módulo em **tema claro** dentro de plataforma escura — legado não reconciliado.
| **Metodologia: lacunas e gestão de risco** — 11 vídeos (aulas avançadas, linha azul, macro/micro) | pesquisa | sonnet | ✅ → `pesquisa/metodologia_regras.md` |

### Regras numéricas recuperadas (fecham a maior lacuna da onda 1)
1. **Faixas de convicção do percentual comprador/vendedor** — 50% empate/lateral · 50–65% pré-direcional · ≥70–75% direcional · ≥80–85% convicção máxima. CONFIRMADO, com imprecisão pontual: dois vídeos divergem entre 70% e 75% como corte de "direcional" ⇒ vira parâmetro, não constante.
2. **Linha Azul = o preço onde o indicador percentual cruza 50%, ancorado na abertura**. CONFIRMADO, mas a regra de plotagem mudou entre versões da ferramenta ⇒ tratar como definição instável.
3. **Máximo de 3 stops seguidos na mesma região** antes de abandoná-la no dia. CONFIRMADO — é o achado numérico mais sólido sobre limite de perda. Não há evidência de limite diário agregado entre regiões.
4. **Dois modos de tamanho**: "mão cheia" em região de alta convicção vs "mão mínima" em região turbulenta (stop mais barato). Mecanismo CONFIRMADO; o gatilho que classifica a região é visual/qualitativo, não numérico ⇒ precisa de parâmetro calibrável.
5. **Macro = movimento do dia inteiro desde a abertura; Micro = movimento imediato — e é a micro que manda no preço agora.** CONFIRMADO. A janela exata da micro está AUSENTE NA FONTE ⇒ nosso `janela_micro_ns` fica como parâmetro sem valor canônico.

### Correção de rumo: "exaustão" não vem do método
O extrator confirmou que **"exaustão de movimento" está AUSENTE em todos os 11 vídeos**. O `DetectorExaustao` que escrevi é conceito padrão de order flow, legítimo por si só — mas **não faz parte da metodologia ASG** e eu não devia tê-lo apresentado junto dos outros como se fosse. Fica no código, reclassificado como detector genérico de microestrutura, não como regra do método.

Também AUSENTES: regra de horário de operação e fórmula de alvo/take-profit — fracas demais para virar código sem parâmetro calibrável.
| **Ferramenta: componentes e detectores** — 14 vídeos (Maker/HFT, placar, velocímetro, ML, caso de falha WINFUT) | pesquisa | sonnet | ✅ → `pesquisa/ferramenta_componentes.md` |

### Achado central da onda 3: o caso de falha do WINFUT
O vídeo em que "o fluxo enganou todo mundo" é o teste de estresse mais valioso do método. Cenário: o contexto macro marcava ~90% vendedor (picos de até −1925), **e o preço subiu assim mesmo**. A razão: o pico comprador oposto (~+915) nunca igualou a magnitude histórica do dia e reverteu em minutos.

**Lição que vira requisito de código**: ler o sinal instantâneo é insuficiente — é preciso **normalizar por magnitude relativa** (comparar o pico atual com a distribuição do dia) **e exigir persistência temporal**. Um sinal forte que dura segundos não é o mesmo que um sinal moderado que persiste. Nosso `MotorSinais` hoje só olha dominância na janela; isso é exatamente o modo de falha documentado.

**3 componentes que faltam no código** (do mapeamento contra `fluxopro/`):
1. **Regra estrutural de regime** — mudança de tendência só é reconhecida quando perde a máxima/mínima do dia. Barato de construir (só precisa de OHLC), é a lição direta do caso WINFUT.
2. **Velocímetro / momentum** sobre os contadores de contexto, normalizado por magnitude histórica e persistência — camada sobre `analytics/delta.py`.
3. **Placar Estatístico** — agregador de confluência entre os sinais que já existem, com detecção de estabilidade vs oscilação.

**Honestidade sobre o "Maker"**: é o sinal mais valorizado pelo autor e o menos replicável. O mecanismo nunca é revelado na fonte, e provavelmente depende de granularidade de book que o feed MT5 não entrega. Marcado como NÃO REPLICÁVEL, não como pendência. O `RNGQ-BJWMWo` (Velocímetro com ML) não chegou a baixar — o vídeo de machine learning continua sem extração.

**Transcrições**: 51 de 54 vídeos agora em texto puro (converti os 35 `.vtt` pendentes com `pesquisa/vtt_para_txt.py`, que deduplica a rolagem da legenda automática do YouTube).

## Suíte de testes — estado real (verificado, não afirmado)
`python -m pytest tests/ -q` → **94 passed**. Rodei antes de escrever este parágrafo.

## O que NÃO está pronto (honestidade > cobertura)
1. **Interface gráfica**: zero linhas de UI. Todo o trabalho é motor/dados, headless. O benchmark de stack (PyQt6 vs Dear PyGui vs web) começou mas não fechou — os scripts em `design/bench/` são parciais e não têm veredito.
2. **Núcleo sem crítica adversarial**: os 23 testes originais passam, mas ninguém tentou quebrar por mutação nem mediu throughput real contra o pico de 5-10k eventos/s do WDO. Isso é uma lacuna de confiança, não só de feature.
3. **Metodologia ASG incompleta**: só 3 dos 54 vídeos foram extraídos e estruturados com citação direta. Termos como "delta", "agressão", "exaustão" (no vocabulário do autor) e a regra de "3 stops seguidos" vêm de vídeos ainda não lidos meticulosamente.
4. **Execução real de ordem**: não existe NENHUMA integração de envio de ordem a corretora/plataforma. O motor de sinais emite `Sinal`, não ordens. Ligar isso a uma corretora é decisão de risco que não deve ser automatizada sem revisão explícita do usuário.
5. **Sem UMDF direto**: decisão tomada de ficar em MT5 (grátis, sem identidade de corretora) — UMDF direto custaria ~R$190-290 mil/ano e não entrega identidade de corretora em WDO/WIN de qualquer forma.

## Repositório
Publicado em https://github.com/GuilhermeBrancalhao/OPERADOR-B3 (privado), branch `main`, primeiro commit com todo o código acima.

## Log
- [setup] Pasta criada, barra e pesquisa despachadas em paralelo.
- [wave-0] 4 agentes no ar: metodologia ASG (T2), barra Profit Pro (T2), fontes de dados B3 (T2), núcleo do motor (T2 build). Python 3.14.6 confirmado no host.
- [wave-0][ok] **fontes de dados** → `pesquisa/fontes_de_dados.md`. Veredicto: `MetaTrader5` (pip, grátis, Clear/Rico/XP/Modal) é a via de tempo real de menor atrito (ticks + book por polling, sem streaming nativo). ProfitDLL/Cedro = pago. **Não existe histórico público de book** (FTP da B3 descontinuado; UP2DATA é pago e sem book) ⇒ **DECISÃO ARQUITETURAL: o gravador próprio é peça de primeira classe** — o adaptador MT5 grava tudo em disco desde o dia 1 para formar a base de replay. Isso reforça a prioridade do `AdaptadorReplay` já em construção.
