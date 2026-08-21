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
