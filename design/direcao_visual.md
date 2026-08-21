# Direção visual — FluxoPro

Documento de direção da camada visual. O motor (`fluxopro/core`, `analytics`,
`microestrutura`, `motor/sinais.py`, 94 testes verdes) está pronto; o que falta é
decidir *como se vê*. Este documento decide.

Referência de benchmark: Profit Pro / Profit Ultra (Nelogica), 23 screenshots
oficiais em `bar/`. Alvo declarado: **superar**, não copiar.

Data: 2026-08-21. Máquina de medição: Windows 11, Python 3.14.6, PySide6 6.11.2,
Dear PyGui 2.3.1, Chrome 148.

---

## 1. Leitura crítica da barra — onde o Profit Pro é forte e onde é datado

### O que ele acerta (e devemos preservar)

1. **Densidade sem medo.** `01_times_trades_a.png` mostra 20 corretoras × 5
   colunas numéricas em ~400px de altura. Não há padding decorativo. Isso está
   certo: o trader de fluxo quer *mais dado por polegada*, não respiro.
2. **Coluna de preço central no SuperDOM.** `02_superdom_c.png` — bid à
   esquerda, preço no meio, ask à direita, com a linha do último negócio
   partindo a tela. É a leitura correta de um DOM: o preço é o eixo, não uma
   coluna qualquer.
3. **Contexto ancorado no eixo de preço.** As barras de VWAP/abertura/ajuste
   ao lado dos níveis (`02_superdom_c.png`) põem a referência onde o olho já
   está. Bom padrão.
4. **Bookmap como peça separada.** `10_bookmap_heatmap_a.webp` é a melhor tela
   do conjunto: heatmap de liquidez + bolhas de execução + COB + SVP num só
   eixo de preço. É a única visualização ali que compõe várias fontes sem
   fragmentar em janelas.

### Onde é datado ou francamente fraco

**F1 — Dois vocabulários de cor concorrentes para a mesma pergunta ("quem
está ganhando?").**
Evidência: `03_livro_ofertas_a.png` usa **azul = compra / vermelho = venda**.
`05_cumulative_delta_b.png`, na mesma plataforma, usa **verde = comprador /
vermelho = vendedor**. Pior: em `05_cumulative_delta_b.png` o gráfico de
candles logo acima do delta usa um *terceiro* sistema — candle **branco
(oco) = alta, preto (preenchido) = baixa**. São três codificações de
direcionalidade empilhadas verticalmente na mesma janela. O trader tem de
trocar de dicionário três vezes ao varrer 600px de tela.
*Nossa regra:* **um único par direcional em todo o produto**. Ver §3.

**F2 — Cor como único portador do sinal, sem redundância.**
Evidência: `06_medidores_agressao_a.png`. O saldo vendedor aparece como
`(49,10k)` sobre faixa vermelha; o saldo comprador como `(42,31k)` sobre faixa
verde. **Os dois números são grafados igual** — parênteses nos dois casos, sem
sinal. Remova a cor (daltonismo deutan/protan, monitor mal calibrado,
screenshot em preto e branco) e a informação principal desaparece por
completo. É um defeito de acessibilidade *e* de robustez operacional.
*Nossa regra:* todo valor direcional carrega **sinal explícito + cor +
posição**. Redundância tripla.

**F3 — Ink-to-data ratio catastrófico nos painéis de resumo.**
Evidência A: `06_medidores_agressao_a.png` — uma janela inteira, com barra de
título, ícones de compartilhar/maximizar/fechar e ~90px de altura, para exibir
**um número**, e ainda o repete duas vezes na mesma janela (`(49,10k)` no topo
e `[Diário] Acúmulo de Agressão - Saldo: (49,10k)` logo abaixo).
Evidência B: `01_times_trades_c.png` — a aba "Saldo" gasta ~460px de altura
num gráfico de duas barras para mostrar `-39.708 Necton` e `39.708 Outras`,
que são **espelhos exatos um do outro**. Um único número resolveria.
*Nossa regra:* nenhum painel de resumo pode ocupar mais de 28px de altura
por métrica. Medidores viram *strip* horizontal na barra de status, não
janela.

**F4 — Dataviz de 2005: pizza 3D com callouts e legenda duplicada.**
Evidência: `01_times_trades_a.png` — gráfico de pizza com sombreado
pseudo-3D, 10 fatias, rótulos de % em caixas brancas ligadas por linhas-guia
saindo em todas as direções, **mais** uma legenda separada embaixo repetindo
os mesmos 10 pares cor/valor. Pizza é a pior forma conhecida para comparar 10
categorias; a inclinação 3D distorce as áreas; e a legenda duplicada gasta
o dobro do espaço. A tabela ao lado, essa sim, já responde tudo.
*Nossa regra:* ranking de corretoras é **barra horizontal ordenada com valor
rotulado na ponta**, sem legenda (a cor é redundante ao rótulo). Zero pizzas.

**F5 — Os dois lados do book em eixos de preço diferentes.**
Evidência: `03_livro_ofertas_a.png`, aba Profundidade. A coluna "Compra"
desce de `108.035` para `107.991`; a coluna "Venda" *sobe* de `108.040` para
`108.087`. As duas listas estão lado a lado mas **não compartilham linha de
preço** — a linha 5 da esquerda (`108.024`) e a linha 5 da direita
(`108.048`) não têm relação alguma. É impossível ler "quanto tem no bid e no
ask *deste* nível" sem contar linhas. O SuperDOM da mesma plataforma
(`02_superdom_c.png`) faz certo, com preço central. Duas ferramentas, dois
modelos mentais incompatíveis, no mesmo produto.
*Nossa regra:* **um só eixo de preço**, sempre, em toda peça que fale de
nível. Bid e ask são colunas *desse* eixo.

**F6 — Formatação numérica que quebra a varredura vertical.**
Evidência: `03_livro_ofertas_a.png`, coluna "Qtde": `29`, `346`, `1,13k`,
`1,88k`, `2,62k`, `3,43k`, `10,05k`. A unidade **muda no meio da coluna** e
o número de caracteres varia de 2 a 6. O olho não consegue comparar magnitudes
por largura nem por posição decimal. Em `02_superdom_a.png` o problema é o
oposto e igualmente ruim: 40 linhas de preço escritas por extenso
(`5.086,50`, `5.086,00`, `5.085,50`…) onde **só os dois últimos dígitos
mudam** — 6 dos 8 caracteres são ruído repetido 40 vezes.
*Nossa regra:* unidade fixa por coluna (nunca `k` misturado com unidade
crua), alinhamento decimal, algarismos tabulares, e no eixo de preço os
dígitos estáveis em `text-mudo` com os dígitos significativos em
`text-primario`.

**F7 — Inconsistência de tema entre módulos.**
Evidência: `09_tape_reading_b.png` (Ranking de Ativos) é **tema claro**, com
zebrado rosa/azul-bebê, dentro de uma plataforma que é escura em todo o resto
(`01`, `02`, `03`, `05`, `06`, `07`, `08`, `10`). É o carimbo de legado: um
módulo adquirido/plugado que nunca foi reconciliado com o design da casa. A
mesma tela ainda estoura texto — a coluna "Classifi…" mostra `22:rrelevant`
com o valor colidindo na palavra.
*Nossa regra:* **um tema, escuro, um só conjunto de tokens**, aplicado por
construção — nenhum painel desenha cor literal.

**F8 — Truncamento por toda parte e navegação por abas que transbordam.**
Evidência: `09_tape_reading_a.png` — cabeçalhos `Qtd Co…`, `Qtd Ve…`,
`Classifi…`, e a coluna de saldo com `-5.546` colado em `rrelevant`.
`01_times_trades_a.png` — a barra de abas inferior tem 7 abas e já precisa de
setas `‹ ›` para rolar, com "Análise…" cortada. O eixo X de
`09_tape_reading_a.png` está com rótulos rotacionados 90° **e invertido**
(100 → 0 da esquerda para a direita), com todos os pontos esmagados na borda
direita.
*Nossa regra:* rótulo de coluna nunca trunca — se não cabe, a coluna sai (o
usuário escolhe o conjunto). Zero texto rotacionado. Escalas sempre
crescentes da esquerda para a direita.

---

## 2. Decisão de stack — com números medidos

### Carga de teste (idêntica para os três)

Definida em `design/bench/workload.py`, para que os números sejam
comparáveis:

- **Footprint**: 60 níveis de preço × 40 barras = **2.400 células**; cada
  célula = 1 retângulo preenchido + 2 números (`bid×ask`) ⇒ 2.400 rects +
  4.800 desenhos de texto por quadro.
- **DOM**: 40 níveis × 6 colunas = 240 textos + 80 barras por quadro.
- **Heatmap** (bookmap): 200 níveis × 600 colunas = 120.000 células, rolando
  1 coluna por tick.

Duas estratégias de desenho foram medidas em cada toolkit, porque a diferença
entre elas é a decisão de verdade:

- **quadro cheio** — repinta as 2.400 células a cada tick (a implementação
  ingênua);
- **incremental** — rola o *backing store* uma coluna e repinta **só a barra
  corrente (60 células)**. É o que um footprint real precisa: a cada tick, só
  a última barra muda.

### Resultados medidos

Reproduzir: `cd design/bench && C:/bv/Scripts/python.exe bench_qt.py`
(idem `bench_qt2.py`, `bench_dpg.py`, `bench_web_ponte.py`;
`bench_canvas.html` servido por `python -m http.server`).

**(a) Footprint — 2.400 células**

| Caminho | p50 | p95 | p99 | fps(p50) |
|---|---|---|---|---|
| PySide6 — QWidget janela real, quadro cheio | 75,24 ms | 100,25 ms | 181,17 ms | **13,3** (12,7 entregues) |
| PySide6 — QPainter offscreen, quadro cheio | 41,54 ms | 138,33 ms | 189,91 ms | 24,1 |
| PySide6 — QGraphicsScene (modo retido) | 39,79 ms | 77,95 ms | 86,60 ms | 25,1 |
| PySide6 — `drawRects` em lote (só fundos) | 11,77 ms | 20,37 ms | 25,77 ms | 84,9 |
| PySide6 — mosaico NumPy (quadro inteiro vetorizado) | 21,22 ms | 33,71 ms | 41,11 ms | 47,1 |
| **PySide6 — incremental (scroll + 1 coluna)** | **1,79 ms** | **3,17 ms** | **3,93 ms** | **560,2** |
| Dear PyGui — quadro cheio (7.200 `configure_item`) | 58,74 ms | 94,90 ms | 554,65 ms | 17,0 |
| Dear PyGui — só coluna nova (180 `configure_item`) | 5,83 ms | 7,11 ms | 30,26 ms | 171,6 |
| Dear PyGui — *piso*: render sem atualizar nada | 5,37 ms | 10,75 ms | 19,67 ms | 186,4 |
| Canvas 2D (Chrome) — quadro cheio | 37,00 ms | 39,40 ms | 42,00 ms | 27,0 (**21,9 reais via rAF**) |
| **Canvas 2D (Chrome) — incremental (60 células)** | **3,30 ms** | **4,60 ms** | **5,20 ms** | **303,0** |
| *Piso de Python*: 7.200 chamadas a função vazia | 1,04 ms | 1,93 ms | 5,52 ms | 960,1 |

**(b) DOM — 40 níveis × 6 colunas**

| Caminho | p50 | p95 | fps(p50) |
|---|---|---|---|
| PySide6 — QPainter offscreen | 1,76 ms | 2,55 ms | **566,9** |

**(c) Heatmap 200×600 rolando**

| Caminho | p50 | p95 | fps(p50) |
|---|---|---|---|
| **pyqtgraph `ImageItem`** | **5,12 ms** | 6,42 ms | **195,4** |
| Dear PyGui textura dinâmica (`add_raw_texture`) | 9,34 ms | 11,62 ms | 107,1 |

**(d) Ponte Python → navegador (latência ida-e-volta, WebSocket localhost)**

| Mensagem | p50 | p95 | bytes | msg/s |
|---|---|---|---|---|
| DOM 40×6 JSON | 0,44 ms | 0,81 ms | 2.210 B | 1.994 |
| DOM 40×6 binário | 0,47 ms | 0,89 ms | 965 B | 1.696 |
| Footprint delta (60 células) binário | 0,62 ms | 1,29 ms | 485 B | 1.271 |
| Footprint snapshot (2.400 células) | 1,69 ms | 5,25 ms | 19.205 B | 414 |
| *Serializar* DOM JSON (sem rede) | 0,113 ms | 0,169 ms | — | — |
| *Serializar* DOM binário (sem rede) | **0,021 ms** | 0,033 ms | — | — |

### O que os números dizem

**Achado 1 — o toolkit quase não importa; a estratégia de desenho importa
40×.** No Qt, o mesmo footprint vai de **13,3 fps** (quadro cheio, janela
real) para **560 fps** (incremental). No canvas, de 21,9 para 303. A decisão
de engenharia — *backing store + repinta só a coluna corrente* — vale mais
que qualquer escolha de biblioteca. Qualquer stack que se escolha **precisa**
desse caminho.

**Achado 2 — o gargalo do caminho ingênuo é o laço Python, não o rasterizador.**
7.200 chamadas a uma **função vazia** já custam 1,04 ms (p50). Mas o
`drawRects` em lote, com os mesmos 2.400 retângulos agrupados em 32 chamadas,
custa 11,77 ms — ou seja, o custo real está em atravessar a fronteira
Python↔C++ 7.200 vezes por quadro. A saída não é "otimizar o loop": é **não
ter o loop**.

**Achado 3 — a ponte web é barata; o custo do web é outro.** 0,62 ms de
ida-e-volta e 485 B por atualização de footprint. Serializar o DOM em binário
custa 0,021 ms — ruído. **A ponte não é argumento contra o web.** O argumento
contra o web é: um segundo runtime, um segundo idioma (TS), um segundo build,
um protocolo binário a versionar entre os dois lados, e — decisivo — o
canvas incremental (3,30 ms) é **1,8× mais lento** que o Qt incremental
(1,79 ms) enquanto exige todo esse aparato adicional.

**Achado 4 — Dear PyGui tem um piso que não dá para furar.** "Render sem
atualizar **nada**" custa 5,37 ms (p50). É modo imediato sobre GPU: redesenha
a cena inteira todo quadro, por construção. Por isso o caminho incremental do
DPG (5,83 ms) é praticamente idêntico ao seu piso — **não existe repintura
parcial em DPG**. Com 4 painéis na tela esse piso se soma. Pior, o p99 do
quadro cheio é **554 ms** — meio segundo de congelamento, visível e
inaceitável num DOM.

**Achado 5 — o heatmap decide o desempate.** `pyqtgraph.ImageItem` faz
120.000 células a 5,12 ms (195 fps) contra 9,34 ms (107 fps) da textura do
DPG — quase 2×. E o Bookmap é a peça mais cara que vamos construir.

### DECISÃO: **PySide6 (Qt 6) + pyqtgraph**

**Por que ganha**

- Mais rápido no caminho que vamos realmente usar: **1,79 ms p50 / 3,17 ms
  p95** no footprint incremental, contra 3,30/4,60 do canvas e 5,83/7,11 do
  DPG. Sobra orçamento: com 16,7 ms por quadro a 60 fps, o footprint consome
  **11%** do frame e deixa o resto para DOM (1,76 ms), heatmap (5,12 ms) e
  gráfico.
- **p99 de 3,93 ms.** É o número que importa num DOM: não é a média que o
  trader sente, é o engasgo. O DPG entrega p99 de 30 ms no melhor caminho e
  554 ms no pior.
- **Zero ponte.** O motor é Python síncrono (`Barramento.publicar` chama os
  assinantes inline, mesma thread). Qt roda **no mesmo processo**: o widget
  assina o barramento e lê o `EstadoMercado` direto, sem serializar, sem
  copiar, sem versionar protocolo. Latência motor→pixel = custo do
  `paintEvent`, e nada mais.
- **Multi-monitor de verdade.** Toda `QMainWindow`/`QDockWidget` destacado é
  uma janela nativa do SO, com DPI por monitor (`Qt::HighDpiScaleFactorRoundingPolicy`)
  e posição persistível via `saveGeometry()`/`saveState()` — que é exatamente
  o mecanismo de *workspace salvável* de §4, de graça.
- **Docking pronto.** `QDockWidget` + `QMainWindow::saveState()` dá
  arrastar/encaixar/destacar/tabular sem escrever gerenciador de layout.

**Por que Dear PyGui perde**

Piso de 5,37 ms por quadro **sem atualizar nada**, ausência de repintura
parcial (o truque que vale 40× simplesmente não existe lá), p99 de 554 ms no
quadro cheio, heatmap 2× mais lento, e — fora do benchmark — **uma única
viewport de SO**, o que mata multi-monitor num produto cujo usuário roda 3
telas. Ganha em uma coisa só: `pip install` e pronto, sem toolkit nativo. Não
compensa.

**Por que web (FastAPI + WebSocket + canvas/TS) perde**

Não perde por latência — a ponte custa 0,62 ms, é aceitável. Perde por
**custo total**: canvas incremental 1,8× mais lento que Qt, mais um segundo
runtime, um segundo idioma, um protocolo binário versionado nas duas pontas,
e docking/multi-monitor que o navegador não entrega (janelas de navegador não
encaixam entre si; a Window Management API é parcial e pede permissão). Todo
esse aparato para ficar mais lento. **Fica reservado como caminho de v3 para
um modo somente-leitura remoto** (celular/tablet acompanhando o pregão), onde
a ponte já está provada barata — não para a estação principal.

**Restrição que a decisão impõe (não negociável)**

Nenhum painel de grade pode repintar o quadro inteiro por tick. Todo painel
denso implementa: `QPixmap` de backing store → `scroll()` → repinta **só** a
região suja. Isso vira requisito de arquitetura em §6, fase 1, não
"otimização depois".

---

## 3. Sistema de design

### 3.1 Princípio de cor: **um eixo direcional, dois canais de significado**

O erro do Profit Pro (F1) é ter três vocabulários direcionais. A regra aqui:

- **Eixo direcional (compra × venda)** — **um par só, em todo o produto**:
  **azul = compra/bid/agressor comprador**, **vermelho = venda/ask/agressor
  vendedor**. Vale no book, no DOM, no footprint, no delta, no tape, no
  ranking, nos candles. Sem exceção, sem "verde para saldo".
  *Por que azul/vermelho e não verde/vermelho:* azul↔vermelho sobrevive a
  deuteranopia e protanopia (as duas formas comuns, ~8% dos homens);
  verde↔vermelho não. E é a convenção que o trader de B3 já traz do book.
- **Verde e âmbar ficam livres** para o **segundo canal**: *estado do
  sistema* e *evento detectado* — não direção. Verde = sistema saudável /
  sinal confirmado a favor; âmbar = absorção / atenção; roxo = sinal do motor.

Isso é o que nos deixa mostrar, no mesmo pixel, **"para onde"** (azul/vermelho)
e **"e daí"** (âmbar/roxo/verde) sem colisão.

### 3.2 Tokens — tema escuro único

Razões de contraste **medidas** por `design/bench/contraste_wcag.py`
(WCAG 2.1, contra `--bg-base #0B0E13`).

**Superfícies**

| Token | Hex | Uso | vs. base |
|---|---|---|---|
| `--bg-base` | `#0B0E13` | fundo da aplicação, área de gráfico | — |
| `--bg-surface` | `#161B22` | corpo de painel | 1,12:1 |
| `--bg-raised` | `#1F2630` | cabeçalho de painel, linha selecionada | 1,27:1 |
| `--border` | `#2A323D` | separador de coluna, moldura de painel | 1,49:1 |
| `--border-strong` | `#3D4854` | painel com foco, divisor bid/ask | 2,07:1 |

**Texto**

| Token | Hex | Contraste | Nível | Uso |
|---|---|---|---|---|
| `--text-primary` | `#E8EDF4` | 16,43:1 | AAA | números vivos, preço |
| `--text-secondary` | `#9BA9BC` | 8,10:1 | AAA | rótulos de coluna, unidades |
| `--text-muted` | `#66727F` | 3,94:1 | AA-large | dígitos estáveis do preço, grade |

`--text-muted` é AA-large (3,94:1) e por isso **só** aparece em ≥14px ou em
conteúdo redundante (os dígitos do milhar que não mudam) — nunca sozinho
carregando informação.

**Eixo direcional**

| Token | Hex | Contraste | Nível | Uso |
|---|---|---|---|---|
| `--buy` | `#3B9EFF` | 6,92:1 | AA | bid, agressão compradora, delta positivo |
| `--sell` | `#FF5C6C` | 6,44:1 | AA | ask, agressão vendedora, delta negativo |
| `--neutral` | `#7D8896` | 5,37:1 | AA | volume sem direção, imbalance nulo |

Fundos de célula do footprint usam esses hues com **opacidade 0,08 → 0,72 em
9 degraus** sobre `--bg-surface`, e o texto por cima sempre `--text-primary`
(16,43:1 sobre a base; ≥4,8:1 mesmo sobre o degrau mais saturado).

**Segundo canal — eventos e estado**

| Token | Hex | Contraste | Nível | Uso |
|---|---|---|---|---|
| `--absorption` | `#FFB224` | 10,72:1 | AAA | absorção detectada (halo + borda) |
| `--alert` | `#F7C948` | 12,34:1 | AAA | pré-sinal, atenção, replay ativo |
| `--signal` | `#C77DFF` | 7,18:1 | AAA | `CONFIRMADO` do `motor/sinais.py` |
| `--poc` | `#FFD166` | 13,41:1 | AAA | POC do Volume Profile |
| `--vwap` | `#5AC8FA` | 10,20:1 | AAA | linha de VWAP |
| `--ok` | `#26D07C` | 9,57:1 | AAA | conexão viva, latência saudável |
| `--danger` | `#FF3B30` | 5,45:1 | AA | desconectado, erro |

Todos passam AA ou melhor. Nenhum token de informação fica abaixo de 3:1.

**Redundância obrigatória (corrige F2)**

Todo valor direcional é renderizado com **três** portadores:
`sinal explícito` (`+1.240` / `−1.240`, nunca parênteses) + `cor` + `posição`
(acima/abaixo da linha zero, ou lado do eixo). Um modo
`Ajustes → Acessibilidade → Sem cor` deixa a tela legível só com sinal e
posição — e esse modo é um **teste de regressão**, não um enfeite.

### 3.3 Tipografia

**Números: `Iosevka Term` (fallback `JetBrains Mono` → `Consolas`).**

Critérios, nesta ordem:

1. **Avanço estreito.** Iosevka Term tem avanço de `0,5em` contra `0,6em` de
   JetBrains Mono e Consolas. Num DOM de 6 colunas numéricas, isso são
   **~17% mais colunas na mesma largura** — cabe uma coluna inteira a mais
   por monitor. Num produto cuja tese é densidade, isso é a métrica decisiva.
2. **Algarismos tabulares por construção** (é monoespaçada): coluna de
   números alinha por posição decimal sem hack de CSS/Qt.
3. **Desambiguação.** Zero fatiado, `1`/`l`/`I` distintos — obrigatório
   quando `1.081` e `l.081` significariam coisas diferentes.
4. **Legibilidade em 11px.** Iosevka mantém altura-x alta em corpo pequeno,
   que é onde o produto vive.

**Rótulos e UI: `Inter` (variable), com `font-feature-settings: "tnum"`**
ligado em qualquer número que apareça em rótulo.

**Escala** (base 12px; densidade "Padrão"):

| Papel | Tam. | Peso | Altura de linha | Onde |
|---|---|---|---|---|
| `num-micro` | 10 px | 400 | 12 px | célula de footprint (bid×ask) |
| `num-grid` | 11 px | 400 | 14 px | DOM, tape, tabelas |
| `num-grid-em` | 11 px | 600 | 14 px | último negócio, valor destacado |
| `num-price` | 12 px | 500 | 16 px | coluna central de preço |
| `num-kpi` | 18 px | 600 | 22 px | strip de resumo (delta do dia, saldo) |
| `label` | 10 px | 500 | 12 px | cabeçalho de coluna, `letter-spacing: .04em`, caixa alta |
| `ui` | 12 px | 400 | 16 px | menus, diálogos, ajustes |

Nada acima de 18px na tela de operação. Títulos grandes são espaço roubado do
dado.

### 3.4 Grid, densidade e espaçamento

- **Unidade base: 4px.** Todo espaçamento é múltiplo (4/8/12/16). Nada de 5,
  7, 13.
- **Altura de linha de grade: 18px** (Padrão) — cabe 11px de texto + 4px de
  respiro + 1px de separador; 40 níveis de DOM ocupam 720px, que entra numa
  metade vertical de monitor 1440p.
- **Três densidades**, alternáveis a quente (`Ctrl+Shift+D`), porque o mesmo
  trader usa 1 monitor no notebook e 3 na mesa:

  | Densidade | Linha | Fonte de grade | Célula de footprint | 40 níveis |
  |---|---|---|---|---|
  | Compacta | 14 px | 10 px | 40×12 px | 560 px |
  | **Padrão** | **18 px** | **11 px** | **46×14 px** | **720 px** |
  | Confortável | 22 px | 12 px | 52×18 px | 880 px |

- **Padding de painel: 0.** O conteúdo denso encosta na borda; o respiro vem
  do cabeçalho de 24px e do separador de 1px `--border`. Padding decorativo
  em painel de fluxo é dado que não coube.
- **Alinhamento**: números **sempre à direita**, alinhados na vírgula
  decimal; rótulos à esquerda; unidade fixa por coluna (corrige F6).

### 3.5 Estados

Estes não são "telas de erro" — num terminal de fluxo, **o estado da conexão é
informação de trading**. Um dado atrasado que parece vivo é pior que uma tela
preta.

| Estado | Sinal visual | Regra |
|---|---|---|
| **Vazio** (sem pregão / antes da abertura) | Grade desenhada, células vazias, marca d'água `AGUARDANDO ABERTURA · WDOFUT · 09:00` em `--text-muted` 14px, centralizada | A **grade aparece**. Nunca um retângulo em branco: o trader precisa reconhecer o painel. |
| **Carregando** (replay buscando, snapshot inicial) | Grade + esqueleto: barras `--bg-raised` na largura média de cada coluna, pulsando 1,2 s ease-in-out, ±6% de opacidade | Sem spinner. Esqueleto mostra a *forma* do que vem. Máx. 3 s; depois vira "atrasado". |
| **Dado atrasado** (último tick > 2 s) | Painel ganha borda `--alert` 1px; badge no cabeçalho: `⏱ 4,2 s` em `--alert`; **os números permanecem legíveis, sem esmaecer** | Não escurecer o dado — o trader ainda quer ver o último preço conhecido. Acima de 10 s, o badge vira `--danger` e a strip de status pisca uma vez. |
| **Desconectado** | Faixa `--danger` de 3px no topo da janela **inteira** (não do painel); cabeçalho de cada painel: `● SEM FEED · 12:41:07`; números congelam em `--text-secondary` | Estado global merece sinal global. E é o único caso em que atenuamos os números: eles são fósseis. |
| **Erro** (falha de parsing, gap de sequência no MBO) | Faixa `--danger` + linha na *trilha de eventos* (§4) com carimbo de tempo e o motivo literal; painel afetado ganha ícone `⚠` clicável | Erro **nunca** é modal. Modal num pregão é dano. Tudo vai para a trilha, e a trilha é consultável. |
| **Replay ativo** | Faixa `--alert` de 3px no topo + `▶ REPLAY 06/12 10:35 · 2,0×` fixo | Copiamos a tarja amarela do Profit (`08_replay_a.png`) — essa ele acerta. Impossível confundir replay com ao vivo. |

---

## 4. Arquitetura de layout

### 4.1 Modelo de janelas

- **Shell** = `QMainWindow` com área central de `QDockWidget`s.
- **Painel** = um `QDockWidget` — arrastável, encaixável, tabulável,
  **destacável para janela nativa** (multi-monitor).
- **Workspace** = `saveGeometry()` + `saveState()` + estado próprio de cada
  painel (símbolo, densidade, escala), serializado em
  `%APPDATA%/FluxoPro/workspaces/<nome>.json`. Troca por `Ctrl+1..9`.
  Workspaces de fábrica: **Fluxo** (padrão), **Book & Tape**, **Bookmap**,
  **Revisão** (pós-pregão, com replay).
- **Multi-monitor**: cada janela destacada guarda monitor + geometria + DPI.
  Ao restaurar num arranjo de telas diferente, a janela órfã vai para o
  monitor primário **com aviso na trilha de eventos** — nunca abre fora da
  área visível (defeito clássico de terminal).
- **Foco**: o painel com foco de teclado tem borda `--border-strong`. Um só
  por vez. Atalhos de negociação só valem no painel focado — sem isso,
  one-click trading é roleta.

### 4.2 Tela inicial

Sem splash decorativo. Ao abrir: **Sala de Controle**, uma tela só, que
responde três perguntas antes de qualquer gráfico:

1. **Feed** — conectado? latência p50/p99 dos últimos 60 s? gap de sequência
   MBO?
2. **Instrumentos** — WDOFUT / WINFUT: último, variação, volume acumulado,
   delta do dia, hora do último tick.
3. **Workspace** — os 4 cartões de workspace, o último usado em destaque.
   `Enter` abre.

Se o feed já está vivo e há workspace anterior, a Sala de Controle se
auto-dispensa em 1,5 s (com barra de progresso cancelável por qualquer
tecla). Ninguém quer um portal entre ele e o pregão.

### 4.3 Wireframe — tela principal de fluxo (workspace "Fluxo")

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ FluxoPro   WDOFUT ▾  │ ● FEED 0,8ms │ 5.086,50 ▲+0,34% │ Δdia +12.480 │ 14:32:07 │ [⚙] [▭] [×]│  ← 28px
├───────────────────────────────────────────┬────────────────────┬─────────────────────────────┤
│ FOOTPRINT · WDOFUT · 500 ticks       [⋮]  │ DOM          [⋮]   │ TAPE                  [⋮]   │  ← cab. 24px
│                                           │                    │                             │
│  5.088,0 │ 12× 4 │ 33× 8 │  7× 2 │ ····   │ ORD QTD│PREÇO│QTD  │ 14:32:07,412  5.086,5  25 ▲│
│  5.087,5 │  8×11 │ 21×19 │ 14× 6 │ ····   │────────┼─────┼──── │ 14:32:07,398  5.086,5  10 ▲│
│  5.087,0 │ 41×[9]│ 88×12 │ 30× 4 │ ····   │  2 340 │5.088│     │ 14:32:07,377  5.086,0 120 ▼│
│ ▸5.086,5 │ 19×22 │ 12×74 │ 55×[3]│ ····   │  1 180 │5.087│     │ 14:32:07,301  5.086,0  15 ▼│
│  5.086,0 │  6× 9 │  4×31 │ 18×12 │ ····   │    905 │5.087│     │ 14:32:06,988  5.086,5   5 ▲│
│  5.085,5 │ ····  │  2× 8 │  9× 5 │ ····   │══ 5.086,5 ═ ÚLTIMO │ 14:32:06,844  5.086,5 300 ▲│  ← linha do último
│  5.085,0 │ ····  │ ····  │  3× 2 │ ····   │        │5.086│ 420 │ 14:32:06,702  5.086,0  40 ▼│
│                                           │        │5.085│ 1210│ 14:32:06,655  5.086,0   8 ▼│
│  Σ  1.204   980    1.455   612            │        │5.084│  760│ 14:32:06,410  5.086,5  60 ▲│
│  Δ   +224  −118     +91   −340            │        │5.083│  305│                             │
│ ┌───────────────────────────────────────┐ │────────┴─────┴──── │  filtro: ≥ 50  [▾]          │
│ │ VOLUME PROFILE (histograma lateral)   │ │ Σbid 2.425 Σask 2.695                            │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓ POC 5.086,5              │ │ imbalance −5,3%    │                             │
│ └───────────────────────────────────────┘ │                    │                             │
├───────────────────────────────────────────┴────────────────────┼─────────────────────────────┤
│ DELTA ACUMULADO · sessão                                 [⋮]   │ RANKING DE CORRETORAS  [⋮]  │
│  +18k ┤                                          ╭──────       │ Ideal    ████████████ +2,4k │
│       │                              ╭───────────╯             │ XP       ████████     +1,9k │
│    0 ─┼──────────────╮───────────────╯                         │ BTG      ██████       +1,2k │
│  −8k  ┤              ╰───╯                                     │ Genial   ████         −0,9k │
│       └────┬────┬────┬────┬────┬────┬────┬────┬────┬────       │ Clear    ███          −1,4k │
│          09h  10h  11h  12h  13h  14h                          │ Modal    ██           −2,2k │
├────────────────────────────────────────────────────────────────┴─────────────────────────────┤
│ ● AO VIVO │ MBO ok, 0 gaps │ p99 1,9ms │ 12.482 trades │ trilha: 3 eventos ▸  │ Fluxo  ⌄     │  ← 22px
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

Notas do wireframe, contra as fraquezas de §1:

- **Um eixo de preço** governa footprint, DOM e Volume Profile. O DOM tem
  preço central (acerto do SuperDOM), e o footprint compartilha a mesma
  grade de linhas (corrige **F5**).
- Preço grafado com **dígitos estáveis em `--text-muted`**: `5.08`**`6,5`**
  (corrige **F6**).
- Delta por barra com **sinal explícito** `+224` / `−340` (corrige **F2**).
- Ranking em **barras horizontais ordenadas**, valor na ponta, sem legenda e
  sem pizza (corrige **F4**).
- Medidor de agressão vive na **strip de topo** (`Δdia +12.480`, 28px) e não
  numa janela própria (corrige **F3**).
- Estado do feed é permanente e discreto: `● FEED 0,8ms` no topo,
  `p99 1,9ms` no rodapé. Nenhum modal.

---

## 5. Os 3 momentos que definem o produto

São as três interações onde o produto se prova ou se desmoraliza. Cada uma tem
orçamento de latência derivado dos números de §2.

### Momento 1 — o instante em que uma absorção é detectada

*O que acontece:* `microestrutura/detectores.py` emite absorção — um nível
está engolindo agressão sem ceder preço. É o evento mais valioso do produto:
o trader tem talvez 2 segundos para agir.

**Comportamento exato:**

- **t = 0 ms** (mesmo quadro do tick que disparou): a célula do nível ganha
  borda de 2px `--absorption #FFB224` e o fundo salta para 0,72 de opacidade.
  Sem transição — **o primeiro quadro já mostra o estado final**. Animar a
  chegada atrasa a informação.
- **t = 0 → 260 ms**: *halo* de 8px em volta da célula, `--absorption` a 45%
  de opacidade, decaindo a 0 em 260 ms (`ease-out`). O halo é o único
  elemento animado, e ele **anuncia o que já está desenhado** — nunca o
  contrário.
- **t = 0**: linha na trilha de eventos do rodapé, `⬤ ABSORÇÃO 5.086,5 ·
  1.240 lotes · 14:32:07,412`. Contador `trilha: 4 eventos` incrementa.
- **Persistência**: a borda âmbar fica enquanto a condição valer, e some com
  fade de 400 ms quando cair. **A absorção não vira confete**: nível que já
  foi marcado nos últimos 30 s reforça a marca existente em vez de disparar
  novo halo.
- **Som** (opcional, desligado por padrão): um clique de 40 ms, 880 Hz.
- **Orçamento**: detecção → pixel em **≤ 16 ms** (um quadro). Cabe: o motor é
  in-process e o repaint incremental custa 1,79 ms p50 / 3,93 ms p99.

*Por que assim:* o Profit sinaliza eventos por cor de célula apenas
(`09_tape_reading_b.png` usa zebrado rosa para "relevante"), sem movimento e
sem trilha — em tela densa isso é invisível. Movimento **breve e periférico**
é a única coisa que a visão captura fora da fóvea sem roubar o foco.

### Momento 2 — leitura do DOM em movimento rápido

*O que acontece:* o mercado destrava; 40 níveis mudam dezenas de vezes por
segundo e o preço varre 6 ticks em 400 ms. É onde toda plataforma treme.

**Comportamento exato:**

- **Taxa de quadro fixa em 60 fps**, desacoplada do tick. O motor atualiza o
  modelo à velocidade que vier; o painel lê o estado no `QTimer` de 16 ms.
  **Nunca repintar por tick** — a 500 ticks/s isso é serrilhamento visual e
  desperdício. Custo medido: 1,76 ms por quadro (566 fps de teto) ⇒ **10% do
  orçamento**.
- **Sem tearing**: `QPixmap` de backing store, um único `blit` por quadro, e
  o painel declara `Qt::WA_OpaquePaintEvent` + `WA_NoSystemBackground`. Nada
  de repintar fundo antes do conteúdo.
- **A escada não pula.** O preço central fica **travado no meio** enquanto o
  último negócio estiver na faixa central de ±8 níveis; só então recentraliza,
  e recentraliza **por rolagem animada de 120 ms**, não por salto. Salto de
  escada é como se erra clique em one-click trading.
- **Rastro de mudança**: quantidade que muda ganha 90 ms de fundo a 0,25 de
  opacidade na cor do lado (`--buy`/`--sell`), decaindo a 0. Sem animação de
  número (contagem crescente é mentira: mostra valores que nunca existiram).
- **Nível varrido** (quantidade → 0 com execução): 140 ms de flash
  `--text-primary` a 0,3, depois some. É a diferença entre "cancelaram" e
  "comeram", e o trader precisa ver qual foi.
- **Congelamento manual**: `Espaço` congela a escada para leitura, com faixa
  `--alert` e `⏸ CONGELADO · 1,4 s` — os dados continuam entrando por trás.
  Soltar volta ao vivo com rolagem de 120 ms. Não existe em Profit; é aqui
  que superamos.
- **Orçamento**: p99 de quadro **≤ 8 ms**. Medido 2,55 ms p95 no DOM.

### Momento 3 — o footprint rolando durante a formação da barra

*O que acontece:* a barra corrente cresce célula a célula; barras antigas
rolam para a esquerda; o trader compara o imbalance de agora com o de 3 barras
atrás.

**Comportamento exato:**

- **A arquitetura é a decisão de §2, Achado 1.** Backing store `QPixmap` com
  o histórico já rasterizado; a cada tick, **repinta só a coluna corrente
  (60 células, 1,79 ms)**; quando a barra fecha, `pix.scroll(-CELL_W, 0)` e a
  nova coluna nasce à direita. **Nunca** os 2.400 (75 ms = 13 fps = produto
  morto).
- **A barra corrente é visivelmente "viva"**: borda esquerda de 2px
  `--text-secondary` e fundo do cabeçalho `--bg-raised`. Barras fechadas não
  têm. O trader nunca confunde barra em formação com barra fechada — erro
  caro e comum.
- **Rolagem manual** (roda do mouse / arrastar): `scroll()` do backing store,
  **zero rerrasterização** do que já está pintado; só as colunas que entram
  pela borda são desenhadas. Alvo: **60 fps durante o arrasto**, com
  orçamento de 3,17 ms p95 medido. Ao rolar para trás, badge
  `⏮ HISTÓRICO −14 barras` e a tecla `End` volta ao vivo.
- **Imbalance** marcado com **borda**, não com mais uma cor: célula com razão
  ≥ 3:1 ganha borda de 1px no lado dominante. Cor já está saturada com
  direção e intensidade; uma quarta dimensão precisa de outro canal — forma.
- **Hover**: sem tooltip flutuante (tooltip em grade densa tapa o dado que se
  quer ler). O detalhe da célula sob o cursor aparece na **strip do rodapé**,
  posição fixa: `5.086,5 · bid 19 × ask 22 · Δ +3 · 41 negócios`. O olho
  aprende um lugar só.
- **Orçamento**: p99 de quadro **≤ 6 ms** com footprint + DOM + delta na
  mesma tela. Soma medida: 1,79 + 1,76 ≈ 3,6 ms p50.

---

## 6. Plano de implementação em fases

Regra que atravessa todas as fases: **nenhum painel denso repinta o quadro
inteiro**. O contrato `PainelDenso` (backing store + região suja) nasce na
fase 1 e é pré-requisito de merge, não otimização posterior.

### Fase 0 — fundação (o que torna as outras baratas)

1. `fluxopro/ui/tokens.py` — os tokens de §3.2 como constantes tipadas
   (`QColor` pré-alocados; alocar `QColor` por célula por quadro é o erro que
   derruba FPS). Nenhum painel escreve cor literal, **jamais**.
2. `fluxopro/ui/base/painel_denso.py` — a classe-mãe: `QPixmap` de backing
   store, `scroll()`, `regiao_suja`, `QTimer` de 16 ms desacoplado do tick,
   `WA_OpaquePaintEvent`. **É o ativo mais valioso do projeto de UI.**
3. `fluxopro/ui/ponte.py` — adaptador `Barramento → Qt`. O barramento é
   síncrono e single-thread (`barramento.py`); o adaptador acumula em buffer
   e o painel **lê o estado no seu próprio relógio**. Nunca `publicar` chama
   `update()` direto — isso reintroduz repaint por tick.
4. `fluxopro/ui/formato.py` — formatação numérica de §3.4: unidade fixa por
   coluna, sinal explícito, dígitos estáveis separados dos significativos.
5. Teste de desempenho no CI: `tests/test_ui_desempenho.py` falha se o
   footprint incremental passar de **4 ms p95** (medido hoje: 3,17 ms). O
   número já é conhecido — o regresso vira erro, não descoberta.

### Fase 1 — o primeiro painel útil ligado ao motor real (**marco: dá para operar olhando**)

Ordem escolhida por *valor por semana*, não por facilidade:

1. **DOM** — é a peça mais simples (1,76 ms medidos, 566 fps de teto), a mais
   usada, e valida a fundação inteira: eixo de preço, escada travada, rastro
   de mudança, congelamento por `Espaço` (Momento 2). Consome
   `microestrutura/livro_mbo.py`.
2. **Tape** — lista virtualizada de trades com filtro por lote. Valida o
   caminho de alto volume de eventos e o `AgressorSide` de `core/eventos.py`.
3. **Strip de topo + rodapé** — último, variação, Δdia, estado do feed,
   trilha de eventos. Isso já mata o painel-janela de medidores do Profit
   (**F3**) e dá os estados de §3.5 desde o primeiro dia.

Entregável da fase 1: **uma janela, três painéis, feed ao vivo**. Já é
utilizável.

### Fase 2 — a peça que diferencia

4. **Footprint** (Momento 3) — o painel caro, agora sobre fundação provada.
   Consome `analytics/footprint.py` + `delta.py`.
5. **Volume Profile lateral** com POC/VAH/VAL, compartilhando o eixo de preço
   do footprint (`analytics/volume_profile.py`).
6. **Delta acumulado** (`analytics/delta.py`) no painel inferior,
   compartilhando o eixo de tempo do footprint.

### Fase 3 — docking, workspace e multi-monitor

7. `QDockWidget` + `saveState()`/`saveGeometry()`; os 4 workspaces de fábrica;
   `Ctrl+1..9`; regra da janela órfã (§4.1).
8. **Sala de Controle** (§4.2).
9. Densidades Compacta/Padrão/Confortável a quente.

Deliberadamente *depois* dos painéis: docking sem painel bom é moldura vazia.

### Fase 4 — eventos, sinais e ranking

10. **Absorção e detectores** (Momento 1) — halo, trilha, persistência.
    Consome `microestrutura/detectores.py`.
11. **Motor de sinais** — `EstagioSinal` (`NENHUM → DIRECAO_CONFIRMADA →
    NA_REGIAO → PRE_SINAL → CONFIRMADO`) como um **farol de 5 estágios** na
    strip de topo, usando `--alert` para pré-sinal e `--signal` para
    confirmado. O estágio é a informação — mostrar só o binário jogaria fora
    o melhor do `motor/sinais.py`.
12. **Ranking de corretoras** em barras ordenadas (§1 F4), de
    `analytics/brokers.py` + `microestrutura/perfil_player.py`.

### Fase 5 — Bookmap e replay

13. **Bookmap/heatmap** com `pyqtgraph.ImageItem` (5,12 ms / 195 fps medidos)
    — a peça mais bonita e a mais cara; por isso vem quando o resto está
    estável.
14. **Replay** com a tarja `--alert` (§3.5), controles de velocidade e
    arrastar-para-voltar, sobre `fluxopro/gravacao`.

### Não fazer agora

- **Envio de ordens.** One-click trading exige regime de foco, confirmação e
  auditoria que não se acrescenta depois com segurança. Fase própria, com
  desenho próprio.
- **Cliente web.** A ponte está medida e é barata (0,62 ms), então continua
  viável — mas como **v3 somente-leitura** para acompanhar o pregão fora da
  mesa. Não como estação principal.

---

## Anexo — como reproduzir os números

```
cd design/bench
C:/bv/Scripts/python.exe bench_qt.py          # Qt: ingênuo, retido, janela real, heatmap
C:/bv/Scripts/python.exe bench_qt2.py         # Qt: lote, mosaico numpy, INCREMENTAL
C:/bv/Scripts/python.exe bench_dpg.py         # Dear PyGui: piso, quadro cheio, textura
C:/bv/Scripts/python.exe bench_web_ponte.py   # ponte websocket: latência e bytes
C:/bv/Scripts/python.exe -m http.server 8801  # e abrir bench_canvas.html no Chrome
C:/bv/Scripts/python.exe contraste_wcag.py    # razões de contraste WCAG dos tokens
```

`workload.py` define a carga comum aos quatro — alterá-lo invalida a
comparação.
