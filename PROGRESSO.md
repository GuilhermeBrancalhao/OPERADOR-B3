# FLUXO PRO — Gauntlet Loop (progresso ao vivo)

Objetivo: plataforma própria de leitura e interpretação de fluxo do mercado futuro (WDO/WIN),
nível institucional (barra: Profit Pro da Nelogica), em Python, com:
- leitura em tempo real (camada de dados plugável: replay histórico, simulador, adaptadores MT5/ProfitDLL/Cedro)
- ferramentas de fluxo: times & trades, DOM/book, footprint, volume profile, delta, agressão, absorção, rastreio de player
- motor de sinais 100% parametrizável pelo usuário
- aprendizado contínuo (estatística online sobre acerto dos sinais)
- modo sinais por padrão; execução real atrás de interface desativada (usuário liga com credencial própria)

> **Estado corrente — 23/08/2026.** `python -m pytest tests/ -q` → **1.341 passed**.
> Fases 1, 2, 3 e 5 do plano de UI entregues e montadas numa janela só; `fluxopro/metodologia/`
> ligado ao pipeline vivo. Detalhe do ciclo em `GAUNTLET_ASG.md`.
> **Nenhum byte de mercado real em disco** — todo teste e todo retrato usam simulador ou mock.
>
> *(Este é o único lugar do arquivo onde o número de testes é mantido. Número velho sob selo de
> verificação é pior que número nenhum, porque convida a confiar — e este bloco ficou **quatro
> ondas** dizendo 796 depois de a suíte passar de mil. Foi uma revisão externa que apontou,
> não eu: escrevi a regra e cometi o defeito dela no mesmo arquivo.)*

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

## RODADA 5 DA CRÍTICA: **NÃO PASSA** (`criticas/nucleo_r5.md`)

### A 6ª casa — e desta vez com prova formal
`gravacao/gravador.py:149` acumula um `int` por evento do pregão inteiro **para produzir dois escalares** (`min`/`max`). Medido no objeto de produção: **44,9 B/evento → 4,85 GB** num pregão de 6 h a 5.000 ev/s. Gêmeo em `dados/leitor_gravacao.py`: **37 GB** para reler. Cerca de 13 linhas de conserto em cada.

O agravante: o `meta.json` com os hashes só é escrito em `_fechar_dia`, sem chamador periódico — **um OOM perde a gravação do dia inteiro**, e o gravador é a única fonte de histórico de book que este projeto terá.

**A prova formal (G01)**: o crítico **aplicou a correção** e os 574 testes continuaram verdes. **Nenhum teste distingue O(eventos) de O(1).** O critério que o builder da 5ª casa deixou no docstring funcionou — e revelou que a suíte inteira é cega a essa classe inteira de defeito.

O crítico escolheu esse gap contra dois concorrentes (vazão indefinida do pipeline, gate de magnitude) com uma justificativa que aceito: **gravar-e-reler é o instrumento de medição** que fecharia o buraco de dado real aberto desde a R2. As ondas 7-8 consertaram a captura (zero perda a 50.000 ticks/s, confirmado) e nunca olharam o armazenamento.

### Mutação: 125 aplicações, 0 ressurreições
| lote | aplicadas | mortas | vivas |
|---|---|---|---|
| vivas + novas da R4 | 31 | 16 | 13 |
| **novas desta rodada** | 27 | 13 | **14 (52%)** |
| tabelas dos 5 builders da onda 8 | 67 | **66** | 1 (já declarada mal formada pelo autor) |

**12 das 13 sobreviventes de cinco rodadas e 11 das 14 novas estão em `gravacao/` + `dados/` + `app/montagem`** — duas medições independentes apontando o mesmo subsistema, que é exatamente onde o critério de crescimento também condena.

### Achado novo: o espelho do WINFUT
Um **pico genuíno no fim do dia** (10× o normal — leilão de fechamento) eleva a referência de magnitude e o motor fica **mudo pelo resto do pregão** (`mag_rel` 0,100). Não é o fat finger, que o filtro de negócio único já pega: é movimento real. Os dois defeitos são o mesmo erro espelhado — a onda 8 trocou "esquece o pico" por "nunca esquece", **ambos ancorados no dia inteiro**. A R3 já pedia janela móvel.

### Os números da onda 8 conferem, vários com folga
Heap em 2 entradas até 4,8 M eventos (o dobro do testado), rompimento 27,9-90,2 µs, dedup 802 chaves plana em 6 h e degrau de 22,9 pp exatos, WINFUT `mag_rel` plana em 0,450, relógio dentro do +0,017%, motor 151.504 ev/s.

### Parte D — o buraco de dado real, quantificado
Zero bytes de mercado em disco, `MetaTrader5` não instalado. Das 536 funções `test_`: **53** usam o simulador, **35** o mock do MT5, **448** eventos escritos à mão, **0** tape real. Mas a concentração é o que importa: **24 das 29 do pipeline montado são simulador**, e **33 das 44 da borda ao vivo são mock** — o mesmo mock que já mentiu na R3 (ignorava `de` e `count`, escondendo o feed travado).

### O crítico registrou contra si mesmo
Que um dos seus ataques falhou (virou evidência **a favor** do desenho); que corrigiu uma afirmação absoluta própria após contra-leitura; e que **o próprio harness dele restaurou conteúdo certo com bytes errados** (LF vs CRLF), precisando de `git checkout` — com a lição de que sha256 normalizado e `git status` são complementares, não alternativos. Repassei esse aviso aos 3 builders da onda 9.

## Onda 11 — a lei do canal deixa de ser caso a caso (22/08)

Fechamento da Fase 1. Um `xfail`, um portão que mentia, e uma lei que só valia
onde alguém lembrava de aplicá-la.

### 1. O `xfail` — e o argumento dele, que estava errado

A sonda dizia: `de 30,0k` desenhava em 10px/`TEXT_MUTED` (3,94:1) ao lado de um
`▲ 51%` em 13px/BUY (6,92:1). O construtor da rodada 2 recusou, e o comentário
dele no código dizia por quê: *"perdê-lo no canal não produz leitura errada
nenhuma: a proporção continua sendo a proporção."*

Isso é verdade sobre a **barra** e falso sobre o **veredito**. `▲ 51%` de 30,0k
é convicção; `▲ 51%` de 30 lotes é ruído; e são o mesmo desenho quando o
denominador morre. O argumento decisivo estava três linhas abaixo, no código
dele mesmo, sobre o RLP: *"sem isto o saldo pareceria o retrato completo do dia
quando não é."* Palavra por palavra, o mesmo caso.

Conserto: `hud.FONTE_QUALIFICADOR = FONTE_VEREDITO` — **derivado**, não repetido,
para que aumentar o veredito sozinho não reabra o defeito em silêncio. A
hierarquia visual migra para PESO (400 × 600) e CROMA, que não é o que a
reescala come. Medido depois: 33,0% de retenção contra 26,4% do veredito, tendo
sido 32% × 39% antes — a ordem inverteu, que é o que a lei pede.

A mutação reprovou **1** teste, tendo eu mexido em **3** qualificadores. Os
outros dois ganharam teste; a mutação passou a reprovar 3 de 3.

### 2. O portão media outro lugar

Ao regenerar o retrato, ele saiu **1480×914** onde antes saía **1850×1143** —
mesma linha de comando, mesma máquina. `--caixas-retencao` multiplica pelo
`devicePixelRatio` da janela, então as caixas de uma passada a 125% recortam
coordenadas que não existem numa imagem gerada a 100%.

Consequência concreta: o par `cobertura=trilho_elo1` foi reportado como
`MARGINAL 0,3 pp` medindo pixel fora da imagem, e como `VIOLADA 10,6 pp` quando
medido no lugar certo. **Um portão frouxo é ruim; um portão que mede outro
lugar e imprime um número é pior, porque assina.**

Conserto: `QT_SCALE_FACTOR=1` fixado antes de existir `QApplication`, só no
caminho de retrato. Pixel lógico e pixel de imagem passam a ser o mesmo em
qualquer máquina, e o conjunto inteiro de retratos foi regerado na mesma escala.

### 3. O par comparava densidade, não lei

Ainda no lugar certo, a comparação era entre um chip de 230×17 de texto denso
(energia 94) e o **segmento inteiro** do elo 1, 611×26 quase todo fundo (energia
19,6). Retenção média de Laplaciano não compara região densa com esparsa: o
fundo não tem traço para perder, só dilui o denominador. `Trilho.rect_rotulo`
aperta a caixa na métrica do texto — texto contra texto.

### 4. A lei virou piso

Com a medição finalmente válida, `cobertura` reprovou por 3,1 pp de verdade. A
causa era a segunda metade da lei do canal, já escrita no projeto: **ressalva
viaja em luminância, não em croma** (o JPEG subamostra croma 2×). O chip usava
`OK`, 9,57:1 — o token de menor luminância que ainda preenche chip.

Entraram `OK_FORTE` (12,38:1) e `NEUTRAL_FORTE` (10,96:1): mesma matiz, mesma
leitura, só que carregando o traço em luminância.

**E aqui está o que importa desta onda.** Escrevi o teste que varre *todos* os
tokens que preenchem chip, e ele reprovou dois que a medição nunca tinha
tocado: `CONFIRMADO` (`OK`, 9,57:1) e `INFERIDO` (`NEUTRAL`, 5,37:1 — mais baixo
que o `DANGER` que esta mesma peça havia abandonado por medição). Eles violavam
a lei desde sempre e nunca apareceram, porque o retrato amostrava regras
`IMPRECISO`.

> **Um portão que só olha o que caiu no retrato de hoje não é portão, é sorte.**
> A lei tinha sido verificada três vezes por medição e mesmo assim tinha duas
> violações vivas. Quem pegou foi a varredura, não a imagem.

Cinco pares no portão, todos aprovados, `exit 0`.

> **Os itens 5 a 7 não estão neste commit.** O conserto deles vive em
> `tests/medicao.py` e nos três `test_ui_*` de portão de tempo, que **outra
> sessão estava reescrevendo ao mesmo tempo** — ver o item 7. O que entrou aqui
> é só `conftest.py::_drenar_qt`. O resto fica registrado como achado, com o
> número medido, e chega no commit de quem está com aqueles arquivos na mão.
> Descrever conserto que não está no diff é o defeito que este arquivo já
> catalogou uma vez, na contagem de testes congelada sob selo de verificação.

### 5. A queda do processo, e o teste que herdava a suíte inteira

Ao medir os portões sob carga artificial (quatro processos queimando CPU), o
processo **caía**: `Windows fatal exception: access violation`, 5 de 6 rodadas
de `pytest tests/test_ui_*.py`.

O teste que caía era sempre `test_a_interface_desenha_sob_carga`, e ele passa
**6 de 6 sozinho sob a mesma carga**. Bissectado até o par mínimo:
`test_ui_composicao.py` + `test_ui_desempenho.py`. A causa é estrutural, não
dele: é o único teste da suíte que roda o laço de eventos de verdade
(`processEvents` num laço de 2 s) — todos os outros desenham chamando
`_quadro()` direto. Como a `QApplication` é de escopo de sessão, o primeiro
`processEvents()` despacha de uma vez tudo o que os testes anteriores deixaram
na fila, parte disso para objetos C++ que já não existem.

Drenar a fila entre os testes (`conftest.py::_drenar_qt`) reduziu o acúmulo e
**não fechou o buraco** — não há como saber o que cada widget de cada teste
ainda tem pendente. O que fecha é não compartilhar estado: com o cenário rodando em subprocesso,
com `QApplication` nova e fila vazia, foram 8 rodadas de 8 sem queda. Essa
mudança está no arquivo da outra sessão e chega no commit dela.

É o mesmo movimento que tirou a medição de GIL desta suíte para
`bench_ui_carga.py`, pelo mesmo motivo: quando o resultado depende do que rodou
antes, o portão não está medindo o produto.

### 6. O portão do DOM media o cache de fontes do Qt

Achado de passagem, e velho: `_medir_dom` nunca descartou quadros de
aquecimento, e o teste da matriz descarta dez desde sempre — com a nota
explicando por quê. Medido no DOM: **p95 de 24,95 ms** numa série cujo quadro
cheio custa ~4 ms. É o mesmo "25 ms" que a docstring da matriz cita, mesma
causa — a rasterização dos glifos na primeira combinação fonte/tamanho.

Passou despercebido porque o portão quase nunca chegava a afirmar o p95.

## Onda 13 — a exaustão calibrada, e a tarefa de segunda (23/08)

### O limiar não era o problema

O estudo da onda 12 mostrou exaustão em **76,5%** de todas as detecções e
registrou a pergunta: limiar frouxo, ou é o evento dominante mesmo?

Primeiro a procedência, antes de mexer: `exaustao.conceito` está marcada
**`AUSENTE_NA_FONTE`** no registro — o termo não aparece em nenhuma transcrição
lida. Não é regra do método; o detector existe como componente genérico, de
origem interna. Ou seja, os 76,5% da tela vêm do componente que o registro se
recusa a endossar. E o parâmetro não veio da fonte, então calibrar não fere a
disciplina.

Aí a causa apareceu no código, e não é limiar:

```python
terco = max(1, cfg.n_trades_janela // 3)
```

Com o default `n_trades_janela = 5`, isso dá `5 // 3 = 1`. O detector diz
comparar *"último terço vs primeiro terço da janela"* e comparava **um negócio
contra um negócio**. Um lote grande seguido de um pequeno bastava — o que num
tape real acontece o tempo todo.

> Não era limiar frouxo. Era a regra documentada não tendo como rodar.

### A varredura, sobre três pregões reais (13, 14 e 21/08)

| config | exaustões | share | det/min | sinais | confirmados |
|---|---|---|---|---|---|
| 5 trades, queda 0,40 (antigo) | 24.602 | 78,9% | 18,2 | 458 | 133 |
| 5 trades, queda 0,60 | 21.022 | 76,2% | 16,2 | 458 | 133 |
| 5 trades, queda 0,75 | 18.134 | 73,4% | 14,5 | 458 | 133 |
| **9 trades, queda 0,40 (novo)** | **9.246** | **58,5%** | **9,3** | 458 | 133 |
| 9 trades, queda 0,60 | 7.489 | 53,3% | 8,2 | 458 | 133 |
| 15 trades, queda 0,60 | 3.005 | 31,4% | 5,6 | 458 | 133 |

Duas leituras, e a segunda é a que impede conclusão errada:

* **A janela é a alavanca; o limiar de volume não.** 5→9 corta 62% das
  emissões; 0,40→0,75 corta 26%. Coerente: limiar não conserta uma comparação
  entre duas amostras de tamanho 1.
* **A coluna de sinais não se move.** 458 e 133 nas seis configurações, com a
  exaustão indo de 24.602 a 3.005. **Exaustão não alimenta a confluência** —
  mexer aqui muda o que a tela MOSTRA, não o que o produto DECIDE.

Escolhido **9**, e não 15: nove é o menor valor em que o terço vira três
negócios, mínimo para "volume caindo ao longo da janela" ser tendência em vez
de diferença entre dois lotes. Quinze reduziria mais filtrando fenômeno de
verdade, e não há nada na fonte que justifique.

Efeito no pregão de 21/08: detecções de 9.661 para **5.068**; exaustão de 7.421
(76,8%) para **2.828 (55,8%)**; absorção **1.332** e clip **908** inalterados —
a mudança tocou só o que devia.

### Cinco testes caíram, e a correção não foi afrouxá-los

Com a janela em 9, o cenário sintético de 2.000 eventos parou de produzir
detecção de tape. A saída **não** foi devolver a janela curta na config do
teste: isso deixaria a suíte verde exercitando uma configuração que não vai para
produção — o teste passaria a medir um produto que não existe. Os cenários
subiram para 10.000 eventos (CLI: 6.000), dimensionados por medição.

### A tarefa agendada, e o defeito que o teste de fumaça achou

`FluxoPro-GravarPregao`, segunda a sexta 09:00, chamando
`scripts/gravar_pregao.cmd`. Disparada e morta em 25 s para provar a cadeia
inteira: Agendador → cmd → Python → MT5 → Gravador.

E o teste de fumaça achou um defeito real. Ao conectar num domingo, o adaptador
republicou **141 negócios do último minuto de sexta** — todos já gravados e
hasheados — e o `Gravador` criou um `trades.csv` solto **ao lado** do
`trades.csv.gz` finalizado. Dois arquivos com o mesmo nome-base, e o catálogo
passando a ter de escolher. **Ia se repetir toda segunda às 09:00.**

Guarda: dia finalizado é reconhecido pela existência do `.gz`, e o evento é
**descartado com contagem pública** (`descartados_por_dia_fechado`). Descartar,
e não recusar — recusar abortaria a captura do dia novo por causa de um minuto
do dia velho. Dois testes: um prova a guarda, outro prova que ela **não**
atrapalha a retomada após crash, sem o qual trocar o descarte por um `raise`
passaria despercebido.

---

## Onda 12 — o primeiro pregão real em disco (23/08)

O `README.md` abria, desde sempre, dizendo **"nenhum byte de mercado real em
disco"** e chamando isso de o único gargalo que não se resolve escrevendo
código. A frase estava certa sobre metade do problema e errada sobre a outra.

O dono ligou o MetaTrader 5 (Genial, conta 1953458) num **domingo**, com o
mercado fechado. Medido na hora:

| | |
|---|---|
| `initialize()` | `True` — terminal build 6140, 118.570 símbolos |
| `market_book_get` | **0 níveis** — o livro só existe com pregão aberto |
| `copy_ticks_from` | **200.914 ticks** do pregão de sexta |
| lado do agressor | **86,8%** dos negócios |

Ou seja: o terminal guarda histórico de **tick**, e não de **book**. O tape —
que é o insumo de delta, agressão, footprint, exaustão e absorção — estava
disponível o tempo todo, a uma chamada de distância, e o projeto não tinha
caminho para importá-lo porque o adaptador MT5 é um streamer que lê do agora em
diante.

`scripts/importar_mt5.py` fecha isso. Não inventa formato: publica `Trade` no
`Barramento` com o `Gravador` assinado, igual ao pipeline ao vivo, e o
resultado é lido por `--fonte replay` sem caminho especial. A conversão de tick
para `Trade` foi **extraída** para `dados.mt5.trade_de_tick`, usada agora pelos
dois — se cada um convertesse do seu jeito, a gravação ao vivo e a importada do
mesmo pregão divergiriam, e a divergência só apareceria ao comparar as duas.

### 32 pregões importados, e o que a série disse

Importados todos os dias que o terminal guardava: **09/07 a 21/08, 3.475.958
negócios, 26 MB**. `scripts/estudo_pregoes.py` roda o motor sobre cada um e
tabula — porque um pregão sozinho não diz nada. `EXAUSTAO 7.421` num dia parece
muito ou pouco? Sem a série ao lado, é opinião.

| | julho (16 dias) | agosto (16 dias) |
|---|---|---|
| negócios/dia (mediana) | 16.088 | 198.158 |
| detecções por minuto | 0,3 | **16,5** (11,8 a 21,1) |
| volume **sem lado do agressor** | **25,4%** | **4,5%** |

**A taxa de detecção é estável no regime líquido.** O volume varia 2× entre os
dias de agosto e a taxa varia menos que isso. O detector não explode com o
volume — que era a pergunta que motivou o estudo.

**O contrato tem vida, e o degrau é 31/07.** `WDOU26` só virou a referência do
dólar em agosto; antes a liquidez estava no vencimento anterior. Média única
sobre os 32 dias não descreve nenhum dos dois regimes, então o script separa os
grupos pela **mediana**, não por data digitada.

**O achado não esperado: 25,4% × 4,5% de volume sem agressor.** No contrato
magro, um quarto do fluxo chega sem lado identificado — e delta, agressão e
footprint são construídos sobre esse lado. A tela mostra `s/lado` como ressalva,
mas a metodologia **não trata isso como regime distinto**. Fica registrado como
pergunta aberta de calibração.

### Dois dados adversos sobre a calibração

1. **Exaustão é 76,5% de todas as detecções** — 113.770 de 148.773, contra
   12,9% de absorção e 10,7% de clip institucional. Ou exaustão é mesmo o evento
   dominante do fluxo, ou o limiar dela está frouxo em relação aos outros dois.
2. **O motor confirmou sinal em 32 de 32 pregões**, inclusive nos dias magros
   com 8 mil negócios e um terço do fluxo sem lado. Em 16/07, com 84 detecções
   no dia inteiro, saíram 8 confirmados.

   Isso **não** está registrado aqui como robustez. Confluência de três
   condições que confirma todo dia, em qualquer liquidez, merece desconfiança:
   ou as três são fáceis demais de satisfazer juntas, ou a histerese deixa o
   estágio subir com evidência fraca. Um pregão só nunca mostraria isso.

### O terceiro erro de unidade do dia

A primeira tabela saiu com `det/min` de **10.475** — cento e setenta e cinco
detecções por segundo. Eu havia dividido por `sessao.segundos_decorridos()`, que
mede o **relógio de parede do processo**: no replay a velocidade máxima, 9,5 h de
pregão passam em 40 s. O valor certo é ~17/min. E a coluna `vwap` saía em
**ticks** (10.339) com o dólar a 5.169.

> Uma taxa dividida pelo relógio errado não é uma taxa imprecisa — é outra
> grandeza. A unidade é parte da medida.

Os três erros de relógio desta onda — janela no fuso do servidor, filtro em três
referenciais, e agora duração de parede no lugar de tempo de mercado — têm a
mesma forma: **dois relógios no mesmo cálculo, e nenhum deles nomeado.**

### O resultado, sobre o pregão de 21/08/2026 (WDOU26)

```
eventos          : 200.899   (9,49 h de tape em 38,6 s → 5.202 ev/s)
sinais emitidos  : 141       (39 CONFIRMADO, 40 PRÉ-SINAL)
detecções        : 9.661     — todas OBSERVADAS, nenhuma inferida
                   EXAUSTÃO 7.421 · ABSORÇÃO 1.332 · CLIP INSTITUCIONAL 908
mercado          : máx 5194,5  mín 5142,5  vwap 5170
volume           : 2.362.146  (compr 1.092.391 · vend 1.181.864 · s/lado 87.891)
perfil de sessão : VAL 5143 · POC 5152 · VAH 5181,5
```

### Dois erros meus no caminho, e os dois eram de RELÓGIO

1. **Importei 45% do pregão e não percebi.** A janela padrão que escrevi era
   `09:00–18:30`, pensando na B3. Mas o `copy_ticks_from` interpreta o horário
   no fuso do **servidor da corretora**: os cinco pregões de 17 a 21/08 aparecem
   começando entre 03:00 e 04:07. Peguei 90.459 dos 200.914 ticks, e o script
   relatou "90.459 trades gravados" — número grande, que parece bom até você
   saber qual era o total.

   Conserto: o script passou a **relatar a cobertura** (primeiro → último), não
   só a contagem. *Contagem sem intervalo não diz se faltou pedaço.*

2. **Três relógios no mesmo fluxo.** Pedia ticks num `datetime` ingênuo (lido no
   fuso do servidor), filtrava o fim em hora **local**, e relatava cobertura numa
   terceira conversão — enquanto o `Gravador` particiona a pasta do dia por
   **UTC**. Unificado em UTC, que é o relógio que a gravação já usava, a pergunta
   virou uma só e sem fuso: *este tick cai no dia UTC pedido?* A cobertura foi de
   `06:00→15:29` para `09:00:38→18:29:59`, que é o pregão inteiro da B3.

### Um teste que dependia do ambiente

Instalar o pacote `MetaTrader5` derrubou
`test_importar_mt5_sem_pacote_instalado_da_erro_claro`. Ele passava por
**ausência da dependência**, não por comportamento do código. A ausência virou
simulada (`monkeypatch` no `__import__`), e ganhou o par que faltava: um teste
que prova que `_importar_mt5` **devolve** o pacote quando ele existe — sem o
qual a versão que levantasse sempre passaria igual.

### O que continua faltando

O **livro**. Não há histórico de book no MT5, e fabricar um a partir de bid/ask
seria pior que não ter: pareceria leitura de fluxo e seria desenho. DOM e
bookmap só se enchem com `scripts/operar.py --fonte mt5 --gravar` durante o
pregão aberto.

---

### 9. A varredura de retenção que faltava na interface

O núcleo tinha varredura para o defeito assinatura do projeto — 1.000 contra
20.000 eventos, mesmo `len` em toda coleção. A interface **não tinha**: tinha
prova painel a painel, escrita quando alguém lembrou, cobrindo cinco dos
catorze. Ficavam de fora tape, footprint, perfil, delta, matriz, HUD, método,
regras e trilha.

Mesma forma do item 4 desta onda, e por isso mesmo vale registrar: a lei do
canal também estava verificada três vezes e tinha duas violações vivas.

`tests/test_ui_retencao.py` enumera `JanelaFluxo._paineis` — não uma lista
digitada —, publica no barramento de verdade e drena pelo `_tick`. Painel novo
entra na varredura no dia em que entra na janela. Resultado: **66 coleções
vigiadas em 14 painéis**, e nenhuma cresce.

Três coisas só a mutação mostrou, e as três eram o teste, não o código:

1. **Sem sessão, dois painéis mediam zero nas duas pontas.** `perfil` e
   `players` são alimentados pelo retrato da sessão; a janela nua não lhes dá
   nada, e "não cresceu" virava verdade por ausência de dado — o mesmo defeito
   do teste da matriz a 262 px, fora da janela alcançável.
2. **Sem corretora, `players` continuava vazio.** O passeio não preenchia
   `buyer_broker`/`seller_broker`, então o ranking não tinha o que rankear.
   Oitenta identidades distintas, e não uma por trade: o índice é POR
   CORRETORA, e inventar identidade nova a cada evento reprovaria um
   dicionário que está certo.
3. **O passeio não andava no relógio.** Com 1 ms por evento, 1.000 e 20.000
   eventos cobrem 1 s e 20 s — e uma mutação que enfiava um `set` de inícios de
   candle dentro do `EixoTempo` **sobreviveu**, porque nesse intervalo não há
   candle novo. Com 1 s por evento a varredura cobre 17 min contra 5h30, e a
   mesma mutação passou a reprovar em dois painéis, porque o eixo é
   compartilhado.

> Um teste de retenção que não anda no relógio só vigia as coleções indexadas
> por evento, e deixa de fora justamente as que guardam histórico.

Prova final: 3 mutações em 3 lugares diferentes (lista sem teto no tape, dict
por trade dentro do `PainelPlayers`, acumulador um nível abaixo no eixo), 3
reprovações.

### 8. O instrumento lia memória liberada

Os dois testes de geometria do canal no HUD reprovavam com a máquina ocupada,
e eu atribuí à contenção. Estava errado, e a causa é pior: `_recorte` era
`bytes(painel._backing.copy(rect).toImage().constBits())`. `constBits()`
devolve uma janela para o buffer do `QImage`; o PySide6 não mantém o dono vivo
pela janela; numa cadeia de temporários o `QImage` morre antes de `bytes()`
terminar de copiar. **86 recortes corrompidos em 400**, e zero nas mesmas 400
guardando a referência.

Não era escala reintroduzida no produto. Era o instrumento.

Dois desdobramentos:

* O `_recorte` do footprint escapava **por acidente** — usa `pixelColor` e
  nunca toca em `constBits()`. O docstring dele culpava enchimento de linha,
  sob o selo "custou uma investigação; fica escrito". Enchimento é real e é o
  problema menor; quem lesse aquilo, tratasse o enchimento e trocasse por
  `constBits()` por velocidade reintroduziria a leitura de memória liberada.
  Corrigido, apontando para a forma certa.
* Varridos os outros usos vivos de `constBits()`: `scripts/retencao.py::_cinza`
  e `design/bench/bench_qt2.py` guardam o `QImage` em variável com nome. Estão
  corretos — os números de retenção da lei do canal não estavam contaminados.

Fica junto do item 6 como a mesma lição em duas roupas: **antes de acusar o
código medido, conferir o que mede.** No item 6 o portão media o cache de
fontes do Qt; aqui o recorte media memória que já não era dele.

### 7. Duas sessões escrevendo no mesmo arquivo (erro meu)

`tests/medicao.py` estava sendo reescrito por **outra sessão** ao mesmo tempo.
Eu li o arquivo, escrevi por cima, e apaguei uma função dela. Perda clássica de
atualização: leitura velha, escrita nova.

Fica registrado porque a lição não é sobre Qt: **antes de gravar por cima de um
arquivo que não é só seu, confira se ele mudou desde a leitura.** O sintoma foi
três arquivos de teste com `ImportError` e vinte minutos gastos procurando um
defeito que eu mesmo tinha criado.

O instrumento dela é melhor que o meu e prevaleceu: eu media razão parede/CPU
do **laço inteiro** com `process_time` (granularidade de 15,6 ms no Windows);
ela mede o custo de CPU de **cada quadro** com `QueryThreadCycleTime`, que
conta ciclos, e descarta as amostras em que o processo não estava rodando. A
granularidade do julgamento passa a ser a mesma do objeto julgado, que era
exatamente o que faltava.

---

## Onda 10 — FASE 1 DA INTERFACE: a primeira tela (22/08)

**Escolha do dono**, contra "fechar a metodologia" e "rodada 6 de crítica": construir o painel. Entregue: `fluxopro/ui/` (fundação + 3 painéis), `scripts/painel.py`, **139 testes novos** (657 → **796**, todos verdes), e dois retratos PNG em `design/`.

**A fundação (`ui/base/painel_denso.py`)** é o ativo. §2 mediu que o mesmo footprint vai de 13,3 fps repintando tudo a 560 fps repintando só o que mudou — fator 40, e a causa não é o toolkit: 7.200 chamadas a uma função **vazia** através da fronteira Python↔C++ já custam 1,04 ms. Medido no MEU código, não herdado do bench:

| painel | quadro cheio p50 | incremental p50 | ganho |
|---|---|---|---|
| DOM 40 níveis @420×760 | 4,413 ms | 0,327 ms | **13,5×** |
| Tape @380×760 | 5,407 ms | 0,163 ms (rolagem) | **33,3×** |
| quadro **ocioso** | — | **1,00 µs** | o `if` que retorna sem abrir `QPainter` |

**O portão de CI tem duas formas, e a segunda é a que vale.** §6 pede "falhar acima de 4 ms p95". Limite absoluto sozinho é frágil: numa máquina rápida passaria mesmo com a incrementalidade removida. Então há também a **razão cheio/incremental ≥ 5×**, que não mede velocidade — mede se a fundação ainda funciona — e sobrevive a trocar de máquina, porque as duas medidas sofrem juntas.

### O defeito que só apareceu sob carga real
Todos os números acima são com o painel **sozinho no processo**. Com a fonte na thread dela, o quadro do DOM foi de sub-milissegundo para **12 ms**, e a tela caiu a 15 fps. O que denunciou foi separar `thread_time` de `perf_counter`: o custo de CPU era sub-ms, os 12 ms eram **espera de GIL** contra um produtor que nunca faz I/O. (Cheguei a ler errado antes, com `process_time`, que soma a CPU de todas as threads e escondia a espera.) É um dial, não um bug — fluidez de tela contra vazão de ingestão:

| troca de GIL | ingestão | quadros/6s | DOM p95 |
|---|---|---|---|
| 5 ms (padrão CPython) | 2.462 ev/s | 90 (15 fps) | 34,5 ms |
| **1 ms** (adotado no painel) | **1.320 ev/s** | **230 (38 fps)** | **15,7 ms** |
| 0,5 ms | 938 ev/s | 360 (60 fps) | 9,3 ms |

Fica em `scripts/painel.py` e **não** no núcleo: `operar.py` é headless e existe para vazão. É a lição do próprio projeto — *medir o CONJUNTO, não cada fix isolado* — valendo para a interface.

### Três defeitos que só o RETRATO mostrou
Renderizar a janela em PNG achou o que 136 testes de comportamento não viam, porque em todos os três **os dados estavam certos**:

1. **Texto azul sobre barra azul** (e vermelho sobre vermelho): a quantidade sumia dentro da barra que existe para representá-la. Número sobre barra passou a ser `--text-primary` — a direção já está na barra, na posição e na coluna.
2. **Preço ancorado na borda direita da coluna**, não no meio: colidia com a quantidade de venda, dois números impressos um por cima do outro.
3. **A faixa suja caía 24px acima da linha real** — `marcar_linha` assumia origem em y=0 e o DOM começa sob o cabeçalho. A linha era redesenhada pela metade e a outra metade guardava o valor antigo, o que na tela virava **um dígito cortado ao meio, parecendo um tracinho**. `len` certo, contagem de retângulos certa, dados certos. Fixado com asserção sobre GEOMETRIA, não sobre contagem.

### E um que o teste achou primeiro, maior que o teste
Qualquer novo máximo no book forçava repintura total. Num book vivo o máximo muda quase todo snapshot ⇒ o ganho da região suja iria embora, **com todos os testes de correção passando**, porque a tela fica certa. A escala passou a andar em degraus 1‑2‑5 por década com histerese de ¼.

### Contra o próprio documento de design
§3.2 pede opacidade até **0,72** E "≥4,8:1 mesmo sobre o degrau mais saturado". As duas não são verdadeiras juntas: a 0,72 o contraste cai para **3,85:1**, abaixo do mínimo AA. A 0,60 dá 4,79:1. Ficou a promessa de legibilidade. Só apareceu porque `test_ui_tokens.py` **recalcula** o contraste do token em vez de conferir a tabela publicada contra ela mesma.

### O que a fase 1 NÃO tem
Footprint, volume profile, delta acumulado, docking, workspaces, sala de controle, ranking de corretoras, bookmap, replay com tarja — fases 2 a 5. E `pyqtgraph` **não** está em `requirements.txt`: nenhuma linha o importa ainda, e listar dependência que ninguém usa é mentir sobre o que o projeto precisa.

**O gargalo não mudou**: os dois retratos são do SIMULADOR. Nenhum byte de mercado real existe em disco.

## Onda 9 — correções da R5

| Peça | Modelo | Estado |
|---|---|---|
| **6ª casa: gravador e leitor O(eventos) + durabilidade do meta** | opus | ✅ **17/17 mortas, 4,52 GiB → 806 B, 45,7 GiB → 642 KB** |
| **Motor: referência de magnitude deixa o motor mudo** | opus | ✅ **15/15 mortas, resolve os DOIS lados, +3,4% de custo** |
| **27 mutações vivas em `core/`, `app/`, `scripts/`, `replay`** | opus | ✅ **47/50 mortas (3 provadas equivalentes) + achou a 7ª e a 8ª casas** |

### A 7ª e a 8ª casas — o critério continua produzindo
O builder aplicou o critério de crescimento aos seus 11 arquivos (varredura estática + `tracemalloc`) e duas coleções responderam "número de eventos do pregão":

| | onde | medido | agora |
|---|---|---|---|
| **7ª casa** | `dados/replay.py::_eventos_ordenados` | 347 B/evento → **37,3 GB** em 6 h a 5.000 ev/s | `heapq.merge`, **248 B constante** |
| **8ª casa** | `app/saida.py::ConsoleFluxo.linhas` | 184 B/linha → **0,44 GB/pregão** — e o CLI **nunca lia** o buffer | anel `deque(maxlen=5000)` + desligado no CLI |

A 7ª é a **gêmea exata** do que a R5 achou no `leitor_gravacao.py` — mesma forma, no outro leitor, e o inventário da auditoria não a cobriu. A 8ª estava numa camada que o inventário nem listou (`app/`), e o comentário que a justificava — *"eventos raros, dezenas por sessão"* — **contradizia a própria auditoria**, que mediu 11.054 detecções em 500.000 eventos. Ele corrigiu a frase no código.

**Consertos de produção**: `Barramento.desassinar` (a linha que a R5 disse valer "mais que as três mutações do barramento juntas"), com instantâneo de reentrância **sem alocação no caminho quente**; `FootprintPorTimeframe` recriado na virada — `SEM_RESET_POSSIVEL` virou `()`, fechando a última sobra medida (199 candles do dia 1 aparecendo no dia 2); e o exemplo do CLI que devolvia zero eventos em silêncio por causa de fuso.

**Três sobreviventes, todas provadas equivalentes** — não supostas. A prova de que `heapq.merge` mantém uma entrada por iterável (tornando o índice na chave redundante) ficou na docstring, para a próxima rodada não gastar um ciclo redescobrindo.

### O erro de método que ele pegou em si mesmo
Dez veredictos do primeiro lote saíram "MORTA" por testes de **outro builder** que estavam vermelhos naquele momento — e `pytest -x` para no primeiro erro, que vinha antes no alfabeto. Ele reexecutou com critério **diferencial** (morta ⇔ falhas do mutante menos falhas da baseline ≠ ∅, com baseline remedida antes de cada mutação). Resultado: 6 morriam de verdade, **4 não** — e duas dessas eram furos reais dele (um `assert` que caía numa guarda e nunca exercitava o ramo decisivo; um teste que passava **pelo motivo errado**). Sem essa checagem, teria reportado 47 de 48 com dois furos dentro.

**E apagou o próprio trabalho uma vez**: usou `git checkout -- replay.py` para desfazer um spot-check e levou junto a reescrita inteira, não commitada. Refez e registrou o aviso no harness. Num repositório com três builders e nada commitado, `git checkout` não é rede de segurança — é destruição.

### Magnitude — a janela é medida em AMOSTRAS ACEITAS, não no relógio
A cauda passou a viver em 4 blocos de 2.048 amostras, cada um com seu top-K; a referência é a maior das K-ésimas dos blocos vivos. Janela efetiva: 6.144 a 8.192 **amostras aceitas**.

**Por que isso resolve os dois lados de uma vez**: amostra só entra depois do filtro de negócio único, então **tape lateral miúdo não produz nenhuma**. Medido: o contador ficou cravado em 2.390 tanto com 1.000 laterais quanto com 50.000 (82 minutos de relógio, zero evidência). A janela **não anda durante lateralização** — o defeito R3/R4 não volta nem com 5 milhões de laterais — e **anda quando o mercado produz magnitude**, então o pico de fechamento sai depois de fluxo normal. A janela virou a **fronteira declarada entre evento e regime**.

**A aritmética que mata as alternativas** (no docstring):
- *Janela de tempo*: a regressão do WINFUT põe até 83 min entre pico e repique (logo N > 83 min); o ataque novo põe ~200 s entre pico e movimento legítimo (logo N < 200 s). **Não existe número maior que 83 min e menor que 200 s.** Tempo mede o relógio da sala, não o do mercado.
- *Decaimento com piso*: para barrar o WINFUT a referência não pode cair abaixo de **75%** do pico; para o motor voltar a falar precisa cair a **16,7%**. Impossível para qualquer velocidade — os dois cenários são o mesmo, escalado por 10.
- *K maior*: o leilão gera 900 amostras altas; K teria de passar de 900, e a 900-ésima de ~200.000 é corpo da distribuição — o percentil sobre a massa, que é o defeito R3/R4 com outro nome.

**Regressão idêntica à onda 8** (0 espúrios, `mag_rel` plana em 0,450, referência cravada em 9.620 — número a número). **Eixo novo**: com pico de 2×/5×/10×/50×, o tempo de volta é **constante em ~7.300 amostras**, dentro da faixa declarada — assinatura de mecanismo escala-invariante (decaimento daria tempo crescente com o pico). Controle: com a janela desligada, mudo o dia inteiro.

**Ressalva honesta do builder**: na sonda exata do crítico (900 trades após o pico) o motor **continua mudo** — e isso está certo, 900 amostras não são evidência de mudança de patamar.

**Mediu custo em bytecode, não em relógio**: com 6 frentes rodando, o relógio de parede variava 2× entre execuções idênticas. Ele acrescentou **opcodes por evento** — 496,78 → 513,43 (**+3,4%**), reprodutível ao centésimo — e decompôs: +10,65 o mecanismo, +3,00 o rastro, +3,00 a evidência. A primeira versão custava +9,4% e ele refez. Memória: 128 inteiros constantes.

### A 6ª casa fechada — e o teste que a suíte inteira não tinha

| | ANTES | DEPOIS |
|---|---|---|
| `Gravador`, retenção | 44,90 B/evento | **806 B, constante** |
| pregão 6 h a 5.000 ev/s | **4,52 GiB** | **806 B** |
| `Leitor`, pico para reler | 454,5 B/evento | 2,0 B/evento |
| pregão 6 h a 5.000 ev/s | **45,7 GiB** | **~642 KB** |

O pico do leitor faz **platô em 642.588 → 642.613 bytes ao dobrar de 160k para 320k eventos** — 25 bytes de diferença. Vazão do gravador: 39.505–42.235 ev/s, ~4× a barra. A correção não custou desempenho.

**O teste central é recursivo, e isso é o ponto.** `test_gravador_retencao_nao_cresce_com_numero_de_eventos` mede o `len` e os bytes de toda coleção **alcançável** do estado de instância, porque o defeito era `dict → list`: o `len` de topo valia 1 com um milhão de timestamps dentro. Um teste ingênuo de `len` teria passado com o defeito presente. Complementado por dois eixos independentes no leitor: pico de `tracemalloc` e "quantas linhas foram lidas quando o 1º evento é publicado".

**M01 e M13 são a prova pedida**: eram exatamente o G01 e o gêmeo que a R5 mostrou serem invisíveis à suíte inteira. Agora morrem. **17 de 17 mutações mortas, zero sobreviventes.**

**Uma divergência deliberada da sugestão do crítico**: `heapq.merge` só está correto se cada arquivo já vier ordenado — mas o `Gravador` escreve na ordem de *publicação* e aceita evento atrasado (a própria suíte tem teste disso). O builder usou janela de reordenação de 64 eventos, que preserva a tolerância sem reintroduzir crescimento, e **desordem maior levanta exceção** em vez de publicar replay fora de ordem em silêncio. Efeito colateral: `parar()` voltou a responder — antes o processo ficava preso montando a lista.

**Durabilidade do meta: feita, e a razão não era OOM.** Sem `meta.json` o `Catalogo` **nem indexa o dia** — um crash às 15h fazia o produto se comportar como se os CSVs no disco não existissem. Checkpoint a cada 5.000 eventos, com quatro decisões acopladas: fsync dos CSVs antes do meta; `n_linhas_hasheadas` por arquivo (o hash cobre um *prefixo*, senão dado intacto seria reprovado como corrompido após crash); escrita atômica; e hasher semeado do conteúdo em disco na retomada.

Removeu uma guarda defensiva inalcançável do `catalogo.py` com a justificativa certa: **linha que nenhuma mutação mata é peso morto**.

## Onda 8 — correções da R4

> **Nota de método — o registro em voo virou infraestrutura crítica.** Criei o `.mut/*_em_voo.json` depois que o crítico da R4 morreu por limite no meio de uma mutação. Nesta onda ele **pagou duas vezes**: (1) um timeout matou o harness do motor no meio da mutação M10 e deixou um `while False:` em disco — o registro + sha256 identificou e desfez, e a suíte teria ficado **verde com o defeito**, porque só um teste o pegava; (2) dois builders colidiram no mesmo nome de arquivo e adotaram nomes próprios por conta, sem que eu precisasse intervir. Numa execução com 5 builders mutando código em paralelo, `git diff` não basta — já foi provado cego neste repo (o `.gitignore`) e não distingue mutação de trabalho legítimo.

| Peça | Modelo | Estado |
|---|---|---|
| **Inferência: 5ª casa (heap sem dedup/teto)** | opus | ✅ **12/12 mortas, 2,4M → 2 entradas, 5,3 s → 28 µs** |
| **MT5: relógio de máximo vira catraca** | opus | ✅ **36 → 44 testes, 12/12 mutações mortas** |
| **Detectores: dedup 4.096 é penhasco** | opus | ✅ **+34 testes, 28 mutações / 4 rodadas, penhasco 100 pp → 22,9 pp** |
| **Motor: WINFUT com 20.000 laterais fura o gate** | opus | ✅ **33 → 51 testes, 10/10 mortas, 480 espúrios → 0** |
| **Testes fracos: `perfil_player`, `brokers`, `simulador`, `footprint`** | sonnet | ✅ **+24 testes, 18/18 mutações mortas** |

### Dedup — a chave errada era o problema maior, não o teto
**A chave**: Iceberg e Fantasma chaveavam por `order_id`. Medido: 5 s de tape a 65.000 ordens sintéticas/s produzem **325.000 chaves por `order_id` contra 802 por `(side, price)` — 405×**. Um episódio de iceberg é "estão recarregando em 5000,5", não "a etiqueta que a ponte inventou nesta inserção". O `order_id` continua na `evidencia`; só deixou de ser identidade.

**O penhasco**: teto duro virou expiração por tempo (30 s) com teto por contagem só de backstop (4.096 → 65.536) e **vítima sorteada** no excedente. O sorteio é o que mata a patologia — com FIFO ou LRU sob varredura cíclica, a vítima é sempre exatamente a próxima chave a ser revisitada.

| chaves em rotação | onda 7 (FIFO 4.096) | agora |
|---|---|---|
| 4.096 | 0,0% | 0,0% |
| **5.000** | **100,0%** | **0,0%** |
| 50.000 | 100,0% | **0,0%** |

Com o mesmo teto nas duas políticas, para exercitar o excedente: FIFO salta 0% → 100% entre 512 e 560 chaves; a nova sobe 0 → 16,2 → 35,4 → 56,2 → 79,1 → 92,8 → 98,1%. **Maior degrau: 22,9 pp contra 100 pp.** Retenção em 6 h a 65.000 ev/s: 802 chaves, plano.

**28 aplicações em 4 rodadas**; 6 sobreviventes iniciais viraram 6 testes novos. Uma delas (D03) sobreviveu por **mutação mal formada do próprio builder** — ele percebeu, refez como LRU estrito e ela morreu. Custo: o mapa ficou 2,2× mais caro por operação (TTL e relógio em Python onde `move_to_end` era C), declarado — e ainda 122× acima da barra.

**Erro registrado sem recuperação**: ao gravar a sonda, o builder **sobrescreveu um arquivo de mesmo nome de outro builder** em `.mut/` (untracked, sem restauração possível). Renomeou a sua e liberou o nome. O registro em voo não foi afetado — ele já usava nome próprio.

### A 5ª casa fechada — e o critério para achar a 6ª antes da auditoria

| tape de recarga, 5.000 ev/s | antes | depois |
|---|---|---|
| entradas de heap (16 min, 1 nível vivo) | **2.400.001** | **2** |
| pior evento de rompimento | **5,3 s** | **28 µs** |
| vazão | 12.954 ev/s | **47.142 ev/s** |

Duas defesas: **dedup** por conjunto-espelho (com `discard` no `heappop`, senão o nível que ressuscita fica exilado do topo em silêncio — bug que a onda 4 já pagou uma vez no livro) e **teto** por compactação amortizada. A dedup sozinha não bastaria: num livro que caminha, cada preço entra uma vez e nunca sai, porque a poda preguiçosa só alcança a cabeça. O `livro_mbo.py` tinha a dedup desde a onda 4 mas **não tinha teto** — 5.001 entradas para 1 nível vivo; recebeu a mesma compactação.

**Achado metodológico que muda como medimos daqui pra frente**: o `max µs` bruto continua em centenas de ms **mesmo depois da correção** — e não é código. Um laço aritmético de controle, sem estrutura de dado alguma, mede 7.250 µs no pior evento nesta máquina (86.735 µs com 4 builders em paralelo). O `bench_inferencia.py` agora imprime esse **piso de ruído** e o veredito de cauda julga a coluna `rompimento` (evento determinístico e identificado), não o `max`. Sem isso o próximo builder "corrige" ruído de escalonamento e declara vitória sobre nada.

**Quatro mutações sobreviveram na primeira rodada, e cada uma expôs defeito do TESTE, não do código**: M1/M2 — com a compactação no lugar, tirar a dedup não faz o heap crescer, só churnar; `len` não era prova de nada, e o teste passou a contar **trabalho** (espião sobre `_compactar_heap`). M7/M11 — os testes de compactação usavam 40-50 preços, **abaixo do piso de 64**: a compactação nunca rodava. Testes verdes que não executavam a linha que diziam cobrir.

#### Como reconhecer a 6ª casa (do docstring de `_registrar_preco`)
As cinco: R1 `detectores._trades` · R2 `sinais._dominancia`/`_micro_virou` · R3 `inferencia._lado_casa` · R3 `livro.ultima_ordem_ativa` · R4 este heap. Forma comum: **estrutura que cresce com estado acumulado e é varrida ou podada tarde demais**.

**Nenhuma das cinco foi achada por vazão, e não é acidente**: enquanto a estrutura infla, o custo *médio* CAI (33,54 → 23,01 µs/passo aqui), porque o trabalho fica represado num evento raro em vez de diluído em todos.

O teste prático para qualquer `list`/`deque`/`dict`/`set`/heap de instância: **qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão continua?** Se a resposta contiver "número de eventos/recargas/negócios/atualizações" em vez de "níveis vivos / ordens ativas / janela em ns", a 6ª casa é essa — e o benchmark que a esconde já está verde.

### WINFUT — o gate fechado, e a razão voltou a ser propriedade do mercado
A referência de magnitude deixou de ser percentil sobre reservoir uniforme e passou a ser a **K-ésima maior magnitude da sessão** (min-heap de tamanho fixo, K=32): nunca esquece o pico, é monótona não-decrescente dentro da sessão, O(1) para ler. O `random` e a seed saíram inteiros — **o motor virou determinístico por construção**, não por seed.

| N laterais | R3/R4 | agora | mag_rel |
|---|---|---|---|
| 0 … 9.000 | — | 0 | 0,450 |
| **20.000** | **480 espúrios** (mag_rel 0,920) | **0** | **0,450** |
| 50.000 | — | 0 | 0,450 |

**A `mag_rel` ficou plana em 0,450 no eixo inteiro** — a razão voltou a ser propriedade do mercado, não de quanto tempo o pregão ficou parado depois. Controle (gate desligado): 371/783/783 espúrios, provando que o cenário é real. E não é "sempre não": repique na magnitude do próprio dia confirma 413-533 vezes, `mag_rel` 1,000.

**O filtro que não estava no enunciado e era indispensável**: a magnitude é o |delta| de uma *janela*, então um fat finger de 100.000 lotes deixa **centenas** de amostras da janela com magnitude ≈ o tamanho dele — top-K sozinho afogaria e travaria a referência o dia inteiro. Daí o `fator_dominio_trade_unico`: a amostra só entra se for maior que 2× o maior negócio isolado ainda na janela (deque monotônico, O(1)). Sem ele, o teste de outlier morre.

**Ficou mais rápido**: 138.412 → **143.649 ev/s**, porque saíram o `random.randint` por trade e o `sorted()` de 500 itens a cada 100 trades. M08, M09 e M10 sobreviveram na primeira passada — os três testes que os matam nasceram disso.

**O registro em voo salvou o repositório**: um timeout matou o harness no meio de M10 e deixou a mutação em disco; o `r5_em_voo` + sha256 identificou e desfez. Sem ele, um `while False:` teria ficado no `_registrar_dominancia` — **e a suíte ficaria verde com ele**, porque só o teste de outlier o pega.

### Relógio — máximo sobre janela deslizante + detecção de regressão em dois tempos
A catraca foi desfeita sem reintroduzir o defeito que o máximo corrigira. Três regras, cada uma cobrindo um regime: **máximo** (toda amostra subestima o offset pela idade do tick); **janela de 120 s com gate de admissão** — só entra amostra cujo `time_msc` andou, porque re-observar o mesmo tick é informação zero, e é isso que permite esquecer sem voltar a travar com tape parado; e **detecção em dois tempos** — *armar* quando o `time_msc` recua (único sinal físico exclusivo de regressão), *confirmar* com 3 amostras de déficit acima de 250 ms, com reset e `FalhaCaptura(RELOGIO_REGREDIU)`.

O limiar de 250 ms é escolhido **contra a janela de 300 ms do `InferidorMBP`**: toda regressão capaz de estourá-la é detectada; abaixo disso não estoura e a janela absorve sozinha. Convergência após regressão de 400 ms: **4 polls ≈ 200 ms**.

**Duas correções que só a construção revelou:**
- Medir o *recuo do `time_msc`* contra o pico não funciona — numa regressão de 400 ms com poll de 50 ms o tape recupera o pico em 8 polls, enquanto o erro do offset continua 400 ms para sempre. Por isso o *confirmar* mede déficit, não recuo.
- **Déficit sozinho dá falso positivo, e quem denunciou foi o próprio `bench_mt5.py`**: no regime de 50.000 ticks/s o adaptador consome tape mais devagar que o relógio de parede, o déficit cresce centenas de ms/poll e o detector disparava 8 vezes numa passada. Daí o *armar*. Virou teste.

**Flake alheio corrigido**: `test_sequencia_intercalada...` era uma moeda — ~10% de falha medida, **com o estimador novo E com o da onda 7** (o fixture fazia o tape andar 1 ms/poll contra ~0,1 ms de relógio real). Agora usa relógio controlado.

Custo: `observar` roda 1× por poll (20×/s), não por tick — **+34 µs por segundo de tape**, contra ~200 ms de CPU/s na barra: **+0,017%**. R11 sobreviveu na 1ª rodada porque o teste de memória usava o pior caso invertido; corrigido e morto na 2ª.

### Testes fracos — o simulador podia estar invertido e ninguém saberia
Os 4 módulos que nenhuma onda tocou. **18 de 18 mutações mortas**, incluindo as 3 inversões de semântica de `perfil_player.py` que sobreviveram desde a R3 (quem agrediu, agressividade medindo o lado passivo, perna vendedora não contando clip).

O achado que mais importa é o **simulador**: N04 e N05 — "agressão de COMPRA empurra preço para BAIXO" e "absorção desligada" — sobreviveram a R2, R3 e R4. Ou seja, o gerador de toda medição de qualidade deste projeto podia ter a física do mercado invertida sem quebrar um teste. Agora há testes de propriedade de mercado: preço desloca na direção do agressor, absorção a 100% impede deslocamento, compra consome o topo do **ask** (não do bid), player grande gera clips fora do padrão.

**`qty_minima_imbalance` deixou de ser cimento**: default de `0` → `5`, justificado (WDO negocia em clipes de 1-10 lotes; razão infinita de 1 contra 0 marcava 42-72% dos níveis de um candle esparso como imbalance espúrio). O teste que travava o zero foi reescrito para prender a **semântica** da razão diagonal, passando o piso explicitamente, e ganhou um irmão dedicado ao piso.

**`RankingCorretoras` ganhou `iniciar_nova_sessao`** e saiu de `SEM_RESET_POSSIVEL` na app — sobrou só o `FootprintPorTimeframe` sem solução (assina no construtor e o `Barramento` não expõe `desassinar`).

Nota de coordenação: o builder achou `.mut/r5_em_voo.json` **ocupado por um irmão vivo** (mutação ativa em `motor/sinais.py`) e usou um nome próprio em vez de sobrescrever — o rastreamento em voo funcionou como projetado.

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
> **Congelado em 2026-08-21, onda 6** — este parágrafo dizia "94 passed" sob o selo *"verificado, não afirmado"* muito depois de o número ter mudado. Um builder da onda 9 apontou, e ele tinha razão: número velho sob selo de verificação é pior que número nenhum, porque convida a confiar. O número corrente vive no topo do arquivo, não aqui.

`python -m pytest tests/ -q` → **94 passed** *(verdadeiro na onda 6; o número corrente vive no cabeçalho deste arquivo — em 22/08 são 796)*.

## O que NÃO estava pronto na onda 6 (histórico — vários itens já fechados)
1. ~~**Interface gráfica**~~: continua valendo — zero linhas de UI. A decisão de stack fechou na onda 6 (`design/direcao_visual.md`, PySide6 + pyqtgraph com benchmark medido), mas **nenhum painel foi construído**.
2. ~~**Núcleo sem crítica adversarial**~~ — **fechado**: cinco rodadas de auditoria, centenas de mutações aplicadas, seis casas do defeito de crescimento encontradas e corrigidas.
3. **Metodologia ASG incompleta**: só 3 dos 54 vídeos foram extraídos e estruturados com citação direta. Termos como "delta", "agressão", "exaustão" (no vocabulário do autor) e a regra de "3 stops seguidos" vêm de vídeos ainda não lidos meticulosamente.
4. **Execução real de ordem**: não existe NENHUMA integração de envio de ordem a corretora/plataforma. O motor de sinais emite `Sinal`, não ordens. Ligar isso a uma corretora é decisão de risco que não deve ser automatizada sem revisão explícita do usuário.
5. **Sem UMDF direto**: decisão tomada de ficar em MT5 (grátis, sem identidade de corretora) — UMDF direto custaria ~R$190-290 mil/ano e não entrega identidade de corretora em WDO/WIN de qualquer forma.

## Repositório
Publicado em https://github.com/GuilhermeBrancalhao/OPERADOR-B3 (privado), branch `main`, primeiro commit com todo o código acima.

## Log
- [setup] Pasta criada, barra e pesquisa despachadas em paralelo.
- [wave-0] 4 agentes no ar: metodologia ASG (T2), barra Profit Pro (T2), fontes de dados B3 (T2), núcleo do motor (T2 build). Python 3.14.6 confirmado no host.
- [wave-0][ok] **fontes de dados** → `pesquisa/fontes_de_dados.md`. Veredicto: `MetaTrader5` (pip, grátis, Clear/Rico/XP/Modal) é a via de tempo real de menor atrito (ticks + book por polling, sem streaming nativo). ProfitDLL/Cedro = pago. **Não existe histórico público de book** (FTP da B3 descontinuado; UP2DATA é pago e sem book) ⇒ **DECISÃO ARQUITETURAL: o gravador próprio é peça de primeira classe** — o adaptador MT5 grava tudo em disco desde o dia 1 para formar a base de replay. Isso reforça a prioridade do `AdaptadorReplay` já em construção.
