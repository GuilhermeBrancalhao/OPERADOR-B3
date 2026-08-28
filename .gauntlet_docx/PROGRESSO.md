# Gauntlet Loop — MUDANÇAS E IMPLEMENTAÇÕES (OPERADOR B3)

**Onde acompanhar:** este arquivo. Não interrompa o run; ele se atualiza sozinho.

## A barra (bar)

`bar/` — screenshots reais do **Profit Pro / Profit Ultra (Nelogica)** baixados da
documentação oficial em 21/08, já versionados neste repo, mais `bar/barra_profit_pro.md`
com o inventário funcional de cada ferramenta de fluxo.

**Por que esta barra:** é exatamente a plataforma que o operador usa como padrão quando
escreve "LONGE DO PADRAO DA ASG" no documento. É externa, é real, e pode ser aberta lado
a lado com o nosso retrato. Não precisa ser alcançada — existe para impedir que o run
pare em "bom para IA".

**Como inspecionar:** `.gauntlet_docx/capturar.cmd <saida.png>` renderiza o painel com
dados reais do pregão de 27/08 (recorte 13:00, 1920x1080, sempre idêntico entre rodadas).
O crítico abre esse PNG contra os PNGs de `bar/` e decide qual perde.

## Roteamento de modelos

| Papel | Tier | Modelo | Esforço |
|---|---|---|---|
| Lead / orquestrador | T3 | opus | alto |
| Builder visual/novo | T3 | opus | alto |
| Builder padrão | T2 | sonnet | médio |
| Builder mecânico | T1 | haiku | mínimo |
| Crítico (gosto/julgamento) | T3 | opus | alto |
| Crítico mensurável | T0 (comando) + T1 relatar | — | mínimo |
| Suavização | T2 | sonnet | médio |

**Orçamento:** ~50 chamadas de agente. Reserva de 25% exclusiva para críticos — nunca
gasta em rodada extra de build.

## Baseline (rodada 0)

`rodadas/r0_baseline.png` — estado antes do loop. Defeitos visíveis de imediato:

1. Candle renderizado como **um retângulo verde gigante**, não como velas.
2. Renko vazio ("AGUARDANDO DESLOCAMENTO DE PRECO") ocupando a maior área da tela.
3. Área morta enorme no centro-direita e centro-baixo.
4. VAP espremido numa coluna ilegível à esquerda.
5. Indicadores se contradizendo: gauge −100% VENDA, PULSO +100%, Placar 32%/0%, rodapé 23%/77%.
6. Visor do Sinal Ultra vazio.

## Peças

| # | Peça | Arquivo | Tier inicial |
|---|---|---|---|
| P1 | Candle: bug de render + janela do pregão | `nexo/candles.py` | T3 |
| P2 | Renko proporcional, preenche a região | `nexo/forca.py` | T3 |
| P3 | VAP moderno e legível | `nexo/ladder.py` | T3 |
| P4 | Visor Sinal Ultra | `nexo/nucleo.py` | T3 |
| P5 | OPERADOR IA com presença | `nexo/vies.py` | T3 |
| P6 | Composição / área morta | `nexo/__init__.py` | T3 |
| P7 | Coerência entre indicadores | `paineis/asg.py` | T3 |
| P8 | Força Observada legível | `nexo/estatistica.py` | T3 |

## Segunda passada — itens 11 e 13 (gradualidade)

Os itens 11 (termômetro de agressões / EQUILÍBRIO) e 13 (Força Observada em raios) foram
implementados numa sessão anterior e **nunca passaram por builder e crítico independentes**.
Esta passada corrige isso: eles vão à mesma bancada que as outras cinco peças.

| # | Peça | Arquivo | Pedido literal |
|---|---|---|---|
| P8 | Termômetro EQUILÍBRIO | `nexo/contexto.py` | "muda de negativo para positivo muito rápido... na teoria teria que ser igual um contragiro de carro que acelera e desacelera gradualmente; essas mudanças drásticas de extremos deve ser mostrado só quando existe agressões muito grandes em relação ao período constantemente" |
| P9 | Força Observada | `nexo/estatistica.py` | "também segue a mesma lógica de ser gradual, verifique alguma estatística em que podemos nos basear, e deve ser representados por raios, verde quando é positivo e vermelho para negativos" |

Estado de partida: os dois usam **média móvel de 5 amostras** (`JANELA_SUAVIZACAO_FORCA = 5`),
acrescentada sem julgamento. Média móvel atrasa, mas não implementa nem o "contragiro" (que é
sobre **taxa de variação**, não sobre média) nem o critério de "extremo só com agressão grande
**em relação ao período**", que é uma afirmação estatística — comparação contra a própria
distribuição recente, não contra um limiar cravado.

### P9 Força Observada — ENCERRADA, vitória (2 rodadas)

O defeito real não era "muda rápido demais". A coluna de força de `estado.serie` **não é força
por negócio** — `aplicar` carimba um escalar do *snapshot* igual em todos os negócios daquele
instante. Medido: 6.594 amostras com apenas **204 valores distintos**, patamares de 32 amostras
em média. A janela visível é de 24 raios, e 24 < 32: **o normal era a tira ser 24 raios
idênticos**, afirmando sequência enquanto mostrava um nível repetido.

A média móvel de 5 era **inerte** — com patamar de 32, a janela vivia inteira dentro do
patamar. Não suavizava degrau nenhum; os 203 degraus reais passavam quase inteiros.

Corrigido com colapso de leituras repetidas + **limitador de taxa** (não média): teto = σ das
variações da própria série, convertido em **taxa por segundo** e impresso na tela junto do
período coberto. A/B na mesma série: a MM5 perdia nos dois eixos — distorcia 3,1× mais e nem
assim garantia passo menor.

Rodada 2 fechou a lacuna que o crítico levantou: cada raio era uma *leitura*, não uma fatia de
tempo, então a mesma tira cobria de 12,4 s a 47,8 s sem declarar nada. Hoje a legenda imprime
`24 LEITURAS · 14 S · TETO 14%/S (1σ) · LIMITADO`.

Verificação final, com sonda independente em run diferente: erro entre período impresso e span
real dos raios = **0,000000 s** em 8.111 amostras; **0 violações** do teto por segundo em 7.990
amostras; 36 das 41 mudanças cruas grandes freadas, e as 5 que passaram inteiras só porque o
tape realmente ficou parado. Maior lacuna: **nenhuma**.

Nota: o número de σ na docstring foi corrigido **pelo escopo, não pelo dígito** — 0,1898 era da
corrida inteira, o código só enxerga a deque de 480. Declarar um σ fixo era o defeito, já que
ele é remedido a cada quadro.

### P8 Termômetro EQUILÍBRIO — ENCERRADA, vitória (2 rodadas)

A média móvel de 5 **não era um volante**: limitava o passo por AMOSTRA, e o intervalo entre
snapshots vai de 0,28 s a 28 s. Em rajada o mostrador ainda girava a **0,80 escala/s** (a escala
inteira em 2,5 s). E, pior, ela **escondia extremo real**: onde o cru foi ao fundo de escala
11/9/8 vezes em três passadas, a MM5 mostrou 1/2/3.

Substituída por inércia de verdade (posição + velocidade, velocidade proporcional ao que falta,
teto de 0,20 escala/s) com fundo de escala relativo ao período — 2× a agressão típica dos
últimos **15 min**, e os 15 min são **CONFIRMADO**, vêm de `bar/medidores_agressao_text.txt`
("Períodos Adicionais (Média): 15 e 30 minutos"). Zona morta com histerese.

Verificação final, sonda independente (4.328 snapshots / 4.174 s):
- taxa exibida máx **0,2000 score/s** contra **3,401 score/s** do cru;
- extremo **sustentado** chega a 1,00; extremo de um snapshot isolado é cortado — o pedido;
- escala relativa limitou o alvo em 53,4% dos snapshots (não é limiar cravado);
- 28 viradas sustentadas, **0 perdidas**, mediana 2,2 s.

**Fórmula provada intacta bit a bit** após a rodada 2: o crítico reexecutou a série gravada na
rodada 1 pelo `VolanteGauge` atual — 515/515 snapshots, divergências > 1e-12: **0**.

Rodada 2 corrigiu o único ponto que não sobreviveu à medição independente: a docstring declarava
cauda de atraso de "~28 s", e a medição deu p90 de 70,8 s e máximo de 225,8 s. Agora declara os
**dois regimes** separados (forte: mediana 0,7 s, zero perdidas; fraca: cauda de minutos, que é
a supressão pedida) — e declara um número **pior** do que o crítico conseguiu medir, errando
para o lado da honestidade.

**O builder recusou uma orientação minha, com dado.** Eu sugeri avisar na tela quando o
mostrador ficasse represado "mais de um minuto". Ele mediu o estado: mediana 3,6 s, máximo
22,2 s — um limiar de 30 s ou 1 min **nunca acenderia**, seria elemento declarado e inexistente,
a mesma família de defeito que o aviso existiria para evitar. Implementou em 15 s (entre o p90 e
o máximo do próprio estado). O crítico verificou a recusa com a própria sonda e confirmou:
137 episódios, máximo 20,9 s — 30 s acenderia zero vezes.

## Rodadas

| Peça | Rodada | Papel | Modelo | Veredito | Nota |
|---|---|---|---|---|---|
| — | 0 | baseline | — | — | captura inicial |
| P1 candles | 1 | builder | opus | entregue | largura da vela vinha de `plot/(n*2)` — 170px com 2 velas. Agora largura fixa por slot de tempo, eixo de hora real, arrasto casado com o pixel |
| P2 renko | 1 | builder | opus | entregue | **impasse de partida**: tijolo de 4pts > amplitude do dia ⇒ nenhum tijolo fechava ⇒ recalibragem nunca rodava. Piso passou a ser em ticks; 0 → 179 tijolos |
| P3 vap | 1 | builder | opus | entregue | região 0,06 → 0,11 do quadro; janela fixa de ticks descartava o POC ⇒ agora agrupa em vez de recortar; seletor SESSAO/5M/15M visível |
| P1 candles | 1 | crítico | opus | **derrota** | arrasto só faz *pan*; não há escala. "Mexer no gráfico na escala arrastando" foi pedido literal; 108 velas esmagadas em ~9px de slot |
| P2 renko | 1 | crítico | opus | **derrota** | eixo do Renko 3,3× mais esticado que o do candle (44,6 px/pt × 13,7 px/pt) — "proporcionais aos candles abaixo" não está cumprido. Rótulo "4R" contradiz "0,5 PTS"; "300 TIJOLOS" mas ~34 desenhados |
| P3 vap | 1 | crítico | opus | **derrota** | modo SESSÃO deriva o passo do preço da altura da coluna, não da faixa real: escada de 5.108,0 a **2.605,5** num papel que negociou 5.147–5.182, e **zero barras**. 5M/15M corretos |
| P1 candles | 2 | builder+crítico | opus | **VITÓRIA** | zoom de tempo e de preço por arrasto no eixo e por roda. Crítico disparou `QMouseEvent`/`QWheelEvent` reais e renderizou 6 PNGs, um por gesto |
| P1 candles | 3 | builder | opus | *em curso* | barra levantada: crosshair + leitura O/H/L/C da vela sob o cursor (o Profit mostra permanentemente) |
| P2 renko | 2 | builder | opus | entregue | **3,26× → 1,01×**. Canal explícito de `px_por_tick` preenchido no único ponto que conhece as duas regiões; regiões seguem puras. Rótulo "4R"→"0,5R" derivado, rodapé "89 DE 300 TIJOLOS" |
| P2 renko | 2 | crítico | opus | *em curso* | |
| P3 vap | 2 | crítico | opus | **derrota** | premissa numérica do crítico estava ERRADA (ver abaixo), mas o princípio "anunciar quantos ≠ não esconder" foi acatado |
| P3 vap | 3 | builder | opus | entregue | nível fora da escala agora aparece condensado com **preço e volume** (`▼ 2.543,5 +1 · 148`), localizável |
| P7 coerência | 1 | builder | opus | entregue | placar de dois lados vivos, `compra − venda == placar_ponderado()` ao float; RITMO mostrava +100% com "DESACELERANDO" ao lado |
| P7 coerência | 1 | crítico | opus | **derrota** | o defeito de sinal-vs-grandeza corrigido no RITMO **renasceu na PRESENÇA**: 4 pontos da tela, mesmo número, sinais e cores contraditórios |

### Onda 2 e rodadas seguintes

| Peça | Rodada | Veredito | Nota |
|---|---|---|---|
| P1 candles | 3 | *em crítica* | crosshair ancorado na vela + readout O/H/L/C permanente; sem cursor mostra a última vela **rotulada como tal** |
| P2 renko | 2 | **derrota** | amarração verificada e aprovada (13,69 × 13,70 px/pt, razão 1,00), mas obtida **encolhendo**: série ocupa 63px de 320 (80% vazio), rótulos A2+/A2− mudos. "Trocar distorção por ilegibilidade" |
| P3 vap | 3 | **derrota** | crítico **retratou** a lacuna anterior após refazer a medição no tape. Nova: linha agrupada rotulada por um preço só carregando volume de dois (POC inflado 2×) |
| P3 vap | 4 | entregue | `rotulo_faixa()` varrido na região inteira (linha agrupada, linha de ponta, VAH/VAL interpolados no tick real). **Defeito latente novo**: a linha "fora da escala" era desenhada por baixo do rodapé em certas alturas — invisível, justo o que ela existe para impedir. Preso varrendo 81 alturas |
| P7 coerência | 2 | **derrota** | 4 portas fecharam e foram verificadas uma a uma; `MM5` aprovado como honesto. Mas a família **renasceu na 3ª porta**: cartão REGIME em ciano fixo, contradizendo o placar, e ausente do documento |
| P4 visor Ultra | 1 | *em curso* | |
| P5 OPERADOR IA | 1 | *em curso* | |

### P3 VAP — ENCERRADA, vitória (5 rodadas)

Veredito final do crítico, verificado em pixel nativo e cruzado com o tape:
"A região entrega agora o que `bar/volume_profile_text.txt` define como Volume Profile —
barras por agressão, POC como maior barra, valor numérico no destaque e value area
delimitada — sobre o pregão inteiro de 158.440 negócios, com filtro 5M/15M funcionando e
cada número verificável contra o tape." Maior lacuna: **nenhuma**.

Defeitos reais corrigidos nesta peça, nenhum deles cosmético:
1. Janela fixa de ticks centrada no último negócio **descartava o POC** num perfil de sessão.
2. Escala vinha de `min`/`max` e **um print aberrante real do tape** (2.543,0, tick 5.086, em
   meio a 158 mil negócios entre 5.147 e 5.182) colapsava o dia inteiro numa linha.
3. Rótulo de linha agrupada nomeava **um preço e carregava o volume de dois** (POC inflado 2×).
4. Linha de "fora da escala" desenhada **por baixo do rodapé** em certas alturas — invisível,
   justo o que ela existe para impedir. Preso varrendo 81 alturas de janela.
5. `VAL`/`VAH` e o número de volume pintados **na mesma coordenada**, se destruindo.

O teste da correção final foi **mutado duas vezes** antes de ser aceito: a primeira versão
passava nas duas mutações (retângulo de largura zero não intersecta nada), então ganhou pisos
de largura. Separar zerando um dos lados não é separar.

### P2 Renko — ENCERRADA, vitória (3 rodadas)

Veredito final, medido por varredura de pixel (gridlines achadas por coluna, sem confiar em
rótulo): Renko **30,83 px/pt** × candle **15,375 px/pt** = razão **2,005**, contra
`ESCALA 2X DO CANDLE` escrito na tela — a declaração é verdadeira. Ocupação 20% → **42%**,
rótulos de nível **6 de 6** (eram 4), rodapé "44 DE 300 TIJOLOS" honesto. Maior lacuna:
**nenhuma**.

Defeitos reais corrigidos:
1. **Impasse de partida**: tijolo inicial de 4 pts > amplitude do dia ⇒ nenhum tijolo fechava
   ⇒ a recalibragem dinâmica, que só roda após um fechamento, nunca rodava. O dimensionamento
   dependia do resultado que ele mesmo deveria destravar. Piso passou a ser em **ticks**.
2. Eixo **3,26× mais esticado** que o do candle, silenciosamente. Agora amarrado por um campo
   preenchido no único ponto que conhece os dois retângulos — regiões seguem puras.
3. Rótulo "4R" cravado contradizendo o tijolo real; rodapé contando o acervo, não o desenhado.
4. Rótulos de nível mudos: as placas de fundo de um apagavam o texto do vizinho. Agora o
   rótulo procura coluna livre e, **se não houver lugar, a linha também não é desenhada** —
   guia muda é pior que guia nenhuma.
5. Com zoom de preço alto os tijolos **vazavam da região**. `setClipRect`, provado por teste
   de pixel-sentinela (o recorte do Qt só se manifesta no pixel, não na coordenada).

A tensão real da peça — 1:1 com o candle *versus* preencher a caixa — foi resolvida atacando
os dois lados: a região encolheu (0,33 → 0,22 do quadro, e o espaço foi para o candle, que
tinha dado de sobra) e o fator, quando ainda não enche, é **quantizado e escrito na tela**.
Fator escondido foi a distorção silenciosa que abriu o ciclo.

### P7 Coerência dos indicadores — ENCERRADA, vitória (4 rodadas)

Veredito final: "todo número direcional concorda com sua cor e seu rótulo nas quatro portas, e
a única discordância que resta na tela — `REGIME COMPRADOR` com `SALDO −48%` — vem rotulada
`ESTRUTURA DO DIA` no próprio cartão, com regra rastreada até `pesquisa/ferramenta_componentes.md:113`
e `fluxopro/metodologia/estrutura.py:179-194`." Maior lacuna: **nenhuma**.

O crítico achou **três portas** e depois o defeito do próprio portão:
1. RITMO exibindo +100% com "DESACELERANDO" ao lado (usava grandeza, ignorava manutenção).
2. PRESENÇA com quatro pontos da tela mostrando o mesmo número com dois sinais.
3. Cartão REGIME em ciano fixo, contradizendo o placar, ausente do documento.
4. **A varredura que "prendia a família" era vazia para 3 dos 6 componentes** — fixture com
   força 0,0 e `return True` incondicional para zero. Teste verde por estar fora do cenário.

A causa era única e estrutural: `dataclass_replace(linha, forca=...)` trocava **só a grandeza**;
`direcao` (de onde saem cor e rótulo) e `valor` continuavam vindo do score cru. Por isso
"renascia" a cada correção local.

A regra do zero desmascarou um defeito **vivo**, não hipotético: `RITMO em PARADO` tinha
direção COMPRA registrada e saía como ladrilho **verde escrito "+0%"** — passava porque força
zero retornava `True` incondicional.

Fechado com portão único aplicado a todas as leituras antes de desenhar (corrige re-derivando
a direção da força — o número que o operador lê manda no rótulo; REGIME é exceção declarada,
lá a palavra *é* a medida), mais uma **guarda da guarda**: teste que exige cada componente
aparecer com força ≠ 0 em algum cenário, e outro que reproduz a combinação histórica do
MakerProxy e exige que o invariante a reprove.

Entregue junto: `.gauntlet_docx/COMO_LER_OS_INDICADORES.md`, atendendo ao pedido nº 2 do
documento — o que cada indicador mede, como sai, como interpretar, com proxy marcado como
proxy e a identidade de player declarada AUSENTE NA FONTE (o tape público da B3 não a carrega),
em vez de fingir saber qual player está mandando.

### P1 Candles — ENCERRADA, vitória (6 rodadas, 3 vitórias)

Veredito final: "vela de tamanho único, timeframe editável, pregão inteiro na tela e eixo que
ele move arrastando — e agora também o retorno ao auto-ajuste que o Profit tem, com rótulo que
corresponde ao que o clique faz." Maior lacuna: **nenhuma**.

Defeitos reais corrigidos:
1. **A queixa original, explicada**: a largura da vela era `plot / (n_velas × 2)` — com 2 velas
   na abertura, cada corpo tinha ~170 px. "Começa muito grande e vai se ajustando" era isso.
2. Escala de preço calculada sobre velas que não estavam na tela; grade vertical sem relação
   com tempo (nenhuma escala de hora); passo do arrasto inventado, o gráfico andava distância
   diferente do mouse.
3. Sem crosshair e sem leitura por vela — o operador via a forma e não conseguia ler o preço.
4. **`MINUTOS_PREGAO = 540` era teto, não piso**: o dia tem 116 velas de 5M contra 108 slots,
   então **as 8 primeiras velas da abertura ficavam fora por padrão** — e a abertura é
   justamente o trecho da reclamação. O rótulo prometia "JANELA DO PREGÃO".
5. **Não havia volta para a escala automática.** O builder havia afirmado que o operador tinha
   "o controle que desfaz na mão dele"; o crítico clicou no chip com zoom 4,0 e mediu 4,0 antes
   e depois. 85 das 116 velas ficavam fora da vista sem caminho de retorno.

Duas voltas atrás registradas por honestidade: o builder enquadrou o eixo por percentil p05–p95
para se defender de velas fora de patamar que **não existiam** (o harness de captura dele
reproduzia um defeito de fixture que eu já havia corrigido) — revertido, porque percentil
descarta extremos por construção, o mesmo defeito que o VAP teve de consertar. E o crítico
registrou o que **não** verificou: o estado combinado de pan e zoom simultâneos.

### A causa raiz das reincidências de sinal

Não era da PRESENÇA nem do RITMO. Um `dataclass_replace(linha, forca=...)` trocava **só a
grandeza**; `direcao` (de onde saem cor e rótulo em toda a superfície) e `valor` (o texto do
contexto) continuavam vindo do score **cru**. Com o cru em −0,33 e a média móvel em +0,73, o
mesmo número saía por quatro portas com dois sinais. Por isso "renascia" a cada correção
local: sinal e grandeza viajavam separados e cada consumidor recombinava por conta própria.

Fechado na origem com ponto único (`_linha_com_forca`) e um invariante genérico que varre uma
grade de forças exigindo que **todos os consumidores leiam o mesmo sinal** — mais um teste
negativo que prova que o invariante reprova a combinação antiga.

### Custo da paralelização (registrado por honestidade)

Editar regiões diferentes da mesma superfície em paralelo produziu janelas em que a árvore não
renderiza (`nucleo.py` e `forca.py` pegos em meio a edição). Não corrompeu trabalho — cada
builder tem `test_ui_composicao.py`, que pinta o painel inteiro, na bateria obrigatória — mas
custou uma captura abortada que quase levou um builder a diagnosticar por um PNG velho.
**Portão de fechamento: suíte completa + render do painel inteiro antes de qualquer commit.**

### Segundo defeito do meu próprio harness (rodada 3)

O crítico do VAP reprovou por níveis "fora da escala" em 5.180,5/5.181,5. O builder foi
conferir o tape antes de aceitar: **esses preços nunca negociaram** (o dia inteiro ficou
entre 5.145,5 e 5.179,5, medido em `trades.csv.gz`). Os níveis fantasma eram 2.543,0/2.543,5,
**injetados pela minha própria fixture**: `capturar_sessao.py` chamava
`painel.aplicar(quadro_evidencia_asg(...))` para levantar o véu, e `aplicar()` também chama
`_registrar_amostra` — o preço do cenário congelado entrava no VAP como se fosse tape.

Corrigido: o registro de amostra fica desligado durante a aplicação do snapshot. Custou uma
rodada de crítica e uma de build sobre um defeito inexistente. Lição registrada: **fixture é
artefato e merece a mesma desconfiança que o produto** — as duas primeiras lacunas do run
foram defeitos meus, não do painel.

Nenhuma peça venceu na rodada 1 — o que é o esperado. Barra vencida de primeira significaria
barra baixa demais.

Os três críticos julgaram **o artefato renderizado**, não o relato do builder: cada um gerou os
próprios retratos e mediu pixel/preço na imagem. Dois deles pegaram, de forma independente, que
o `capturar.cmd` estava devolvendo 0 negócios — defeito do meu harness, já corrigido (`--de 12:00`).

### Correção do próprio harness (rodada 1)

O fixture original (`capturar.cmd`, 20s de replay) cobria ~11 min de tape — qualquer
gráfico saía vazio e o crítico julgaria a fixture, não o produto. Foi medido: o replay
anda a ~5x o tempo real, um pregão inteiro levaria ~1h40 de parede.

Criado `.gauntlet_docx/capturar_sessao.py`: carrega os **158.440 negócios reais** do dia
direto pela mesma porta que o produto usa ao vivo (`_registrar_amostra`). Candle, Renko e
VAP ficam como ficariam depois de um pregão inteiro aberto. Não reconstrói livro — para
as regiões de livro (decisão, banner, maker) continua valendo `capturar.cmd`. As duas
fixtures são complementares e cada uma declara o que cobre. Nenhuma fabrica dado.

## Condição de parada

Aberta. Encerra quando (1) o operador chamar de pronto, (2) o ganho por rodada deixar de
importar, ou (3) o orçamento acabar. A condição que encerrar fica registrada aqui.
