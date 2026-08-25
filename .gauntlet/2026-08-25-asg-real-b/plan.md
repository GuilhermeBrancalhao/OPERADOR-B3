# Plano congelado — 2026-08-25-asg-real-b

Bar: **A.S.G — Algorithmic System Generation**, 100 quadros de vídeo fornecidos
pelo operador em `bar/` (95 sequenciais `frame_0XX.jpg` + 5 `destaque_*.jpg`).
Produto: workspace **OPERADOR B3** do FluxoPro (PySide6/Qt 6).

Modalidade única de julgamento: **Static visual** — abrir a coisa rodando em
tamanho real e olhar ao lado do bar. Ferramenta:

```
python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42 \
  --duracao 2 --workspace "OPERADOR B3" --retrato <path>
```

PNG determinístico 1480x900 em ~2,5 s, headless-safe nesta máquina. **Não há
Playwright neste repo**: este flag do próprio CLI É a ferramenta da modalidade.

> A modalidade NÃO enxerga hover/focus/pressed, movimento, variante clara,
> nem largura de janela não testada. Nenhuma parte abaixo depende disso.
> Os quadros do bar são 640x270 — o bar **não sustenta** julgamento de
> glifo/tipografia fina. Julga-se região, proporção, densidade, linguagem
> cromática e presença/ausência de elemento.

---

## HARD CONSTRAINTS (herdadas VERBATIM por todo prompt de builder e de crítico)

1. **Zero capacidade de execução de ordem em qualquer lugar** — nenhum campo de
   quantidade, nenhuma boleta, nenhum botão clicável de executar, nenhum
   callback de execução, nenhum cliente de corretora/API. Rótulos como
   COMPRA/VENDA/ENTRADA/STOP/A1/A2/A3/CONFIRMADO são leituras consultivas
   apenas e nunca podem ser clicáveis para executar.
2. **Preço continua `int` em ticks** por todo o pipeline/modelo/snapshot —
   conversão para pixel só na fronteira de desenho.
3. **A UI nunca toca objeto vivo da thread de dados** — cada painel recebe
   exatamente um snapshot imutável por quadro, sob lock, vindo do relógio único
   da janela; nenhum painel pode assinar o barramento, inferir microestrutura
   ou decidir.
4. **MakerProxy/MotorDecisaoASG/sessão shadow permanecem independentes da UI**,
   e a fórmula real do ASG é **NÃO-REPLICÁVEL** — nunca inferi-la dos quadros,
   nunca alegar paridade, preservar o disclaimer existente em tela/README.
5. **Nunca copiar o logo, o rosto, a marca, o texto proprietário ou os ativos
   originais do ASG** — reproduzir função espacial, densidade e linguagem
   visual apenas, com ativos próprios do FluxoPro/NEXO.
6. **Tocar somente nos arquivos do próprio workspace OPERADOR B3** — não
   redesenhar os outros quatro workspaces (Fluxo, Book & Tape, Bookmap,
   Revisão) nem quebrar Ctrl+1..9, o opt-in `--persistir-workspace` (desligado
   por padrão) ou o reancoramento de janela órfã.
7. **Toda pintura continua QPainter/backing-store pelo sistema de
   tokens/stylesheet existente** — nenhuma cor/fonte/dimensão literal espalhada
   em código novo.
8. **Quando o replay MT5 não tiver histórico de book, mostrar estado honesto de
   indisponível** — nunca fabricar liquidez sintética.

---

## Estado de partida (medido, não herdado)

- `PainelNexoMercadoASG` (`asg.py:1645-2563`) pinta **a superfície inteira**;
  em `WorkspaceASG._reorganizar` todos os outros painéis vão para
  `(-10000,-10000)`. `cockpit.py`, `placar_visual.py`, `grafico.py` compõem o
  workspace nominalmente mas **não pintam pixel visível** hoje.
- Suíte: 1602 testes passando (commit `3a8338e`, tag `gauntlet-r0`).
- Overhead MakerProxy medido: ~20,8%. 2 gates de incrementalidade flaky por
  contenção de CPU. Nenhuma parte abaixo tem licença para regredir isso.
- Rodadas anteriores (`2026-08-24a`, `2026-08-25-asg-ref-ui-a`,
  `2026-08-25-operador-b3`, `2026-08-25-ui`) cortaram em 3-4 partes gigantes
  (`visual-shell`) contra um bar genérico e **nunca tiveram crítico cego real**
  (registrado como `manual-fallback`). Esta rodada não recomeça do zero: ela
  substitui aquele corte grosso por corte por **região**, contra o ASG real.

## Mapa de regiões do bar (fração de 640x270, medido nos quadros)

| Região | x | y |
|---|---|---|
| Escada de preço / smart money | 0,00–0,06 | 0,00–0,56 |
| Cena CONTEXTO (prisma + arcos) | 0,06–0,34 | 0,00–0,56 |
| Faixa de chips numerados 1..6 | 0,02–0,40 | 0,55–0,65 |
| Banner de estado (cunha ALERTA) | 0,00–0,40 | 0,65–0,78 |
| Placar estatístico + histograma | 0,00–0,40 | 0,79–1,00 |
| Visor HUD central (octógono) | 0,40–0,63 | 0,02–0,42 |
| Bloco de marca | 0,42–0,62 | 0,62–1,00 |
| Gráfico de força (topo direito) | 0,63–1,00 | 0,00–0,33 |
| Gráfico de candles | 0,63–0,98 | 0,34–0,85 |
| Pressão % + bloco do instrumento | 0,63–1,00 | 0,86–1,00 |

> A tira vertical de ícones coloridos em x≈0,41 nos quadros é **barra de
> ferramentas do capturador de vídeo, não é o produto**. Nenhum builder a imita
> e nenhum crítico a cobra.

## Costura de propriedade

Para dar propriedade exclusiva de arquivo a builders paralelos, a parte 0 extrai
`fluxopro/ui/paineis/nexo/` — um módulo por região, cada um com entrada
`desenhar(painter, rect, estado)` — e faz `PainelNexoMercadoASG.desenhar`
apenas alocar retângulos e delegar. **A parte 0 tem de aterrissar antes das
partes 1..9 começarem**; ela é julgável sozinha (mapa macro de regiões).

---

# Partes

## 0 · composicao-macro

ARTIFACT: `PainelNexoMercadoASG.desenhar` reduzido a alocação de retângulos +
pacote `fluxopro/ui/paineis/nexo/` com um módulo-esqueleto por região, e a
composição macro do quadro (posição, proporção e sangria de cada uma das dez
regiões, borda a borda, sem cartões com moldura e sem faixa de aviso comendo o
topo).

EVIDENCE: `--retrato` em 1480x900 lido ao lado de `frame_001.jpg`,
`frame_038.jpg` e `destaque_5007_referencia_alvo.jpg`, conferido contra o mapa
de regiões acima.

DEFECT_CLASS: mapa de regiões divergente, proporção errada, grade de cartões
com moldura onde o bar é contínuo, densidade baixa, área morta, cromo/chrome
consumindo área operacional.

## 1 · escada-preco

ARTIFACT: coluna de escada de preço à esquerda — duas micro-colunas de números
minúsculos, preço corrente destacado em cápsula, marcador de nível, rótulo de
rodapé da coluna.

EVIDENCE: `--retrato` recortado em x 0–0,06 ao lado do mesmo recorte de
`destaque_5007_referencia_alvo.jpg` e `frame_072.jpg`.

DEFECT_CLASS: densidade de linhas errada, ausência da segunda micro-coluna,
destaque do preço corrente ilegível ou ausente, escada que não acompanha o
tick grid do símbolo.

## 2 · cena-contexto

ARTIFACT: cena CONTEXTO — prisma isométrico, dois arcos-medidor concêntricos
com contador numérico e legenda curta, leitura percentual de mercado com
legenda, campo de fundo escuro com profundidade.

EVIDENCE: `--retrato` recortado em x 0,06–0,34 ao lado de
`destaque_1800_smart_money_regioes.jpg`, `destaque_1654_atualizacao_micro.jpg`
e `frame_038.jpg`.

DEFECT_CLASS: círculo chapado no lugar de arco parcial, prisma ausente ou sem
volume, número dominante sem legenda, escala tipográfica invertida (rótulo
maior que a leitura), fundo sem profundidade.

## 3 · faixa-niveis

ARTIFACT: faixa horizontal de chips numerados (1..6) — cápsulas arredondadas
com índice acima, valor de preço dentro, estado por cor (ativo destacado, nível
vazio como `--`), largura variável para o chip em foco.

EVIDENCE: `--retrato` recortado em y 0,55–0,65 ao lado do mesmo recorte de
`destaque_5007_referencia_alvo.jpg` e `frame_095.jpg`.

DEFECT_CLASS: faixa ausente, chips sem estado vazio, índice não pareado ao
valor, cápsula sem hierarquia entre nível ativo e inativo, chip clicável.

## 4 · banner-estado

ARTIFACT: banner de estado — cunha diagonal de alerta à esquerda, palavra de
estado em caixa alta vazada ocupando a faixa, linha de orientação em itálico
pequeno acima.

EVIDENCE: `--retrato` recortado em y 0,65–0,78 ao lado do mesmo recorte de
`frame_001.jpg` e `destaque_4643_confirmacao_entrada.jpg`.

DEFECT_CLASS: banner como texto simples em cartão, corte diagonal ausente,
palavra de estado sem peso visual, linha de orientação ausente ou concorrendo
com a palavra de estado, rótulo que sugere ação executável.

## 5 · placar-estatistico

ARTIFACT: bloco inferior esquerdo — título, ladrilho BUY e ladrilho SELL com
contador grande, medalhão circular, fileira de chips de status curtos e tira de
barras verticais densas ao lado.

EVIDENCE: `--retrato` recortado em y 0,79–1,00, x 0–0,40 ao lado do mesmo
recorte de `destaque_5007_referencia_alvo.jpg` e `frame_038.jpg`.

DEFECT_CLASS: placar como texto corrido, ladrilhos sem moldura de estado, tira
de barras ausente, chips de status ausentes, contagem sem procedência.

## 6 · visor-hud

ARTIFACT: visor central — moldura octogonal com cantos chanfrados e marcas de
canto, cabeçalho de carimbo de tempo em fonte pequena, glifo direcional grande
ao centro, e o segundo estado do visor (ícone + legenda curta) que os quadros
mostram alternando.

EVIDENCE: `--retrato` recortado em x 0,40–0,63, y 0,02–0,42 ao lado de
`destaque_4643_confirmacao_entrada.jpg` (glifo duplo), `frame_001.jpg` (glifo
para cima) e `destaque_2148_uso_grafico.jpg` (estado com legenda).

DEFECT_CLASS: moldura retangular ou hexagonal simples, ausência do carimbo de
tempo, glifo pequeno demais para a moldura, moldura vazia sem segundo estado,
visor que parece um botão.

## 7 · grafico-forca

ARTIFACT: gráfico de força no topo direito — série preenchida serrilhada, linha
pontilhada oscilante sobreposta, e trilho de eixo de preço à direita com muitos
níveis pequenos e um nível corrente em cápsula destacada.

EVIDENCE: `--retrato` recortado em x 0,63–1,00, y 0,00–0,33 ao lado do mesmo
recorte de `destaque_5007_referencia_alvo.jpg` (baixa) e `frame_038.jpg` (alta).

DEFECT_CLASS: área chapada sem serrilha, ausência da linha pontilhada, trilho
de eixo de preço ausente, cápsula do preço corrente ausente, densidade de
níveis do eixo baixa demais.

## 8 · grafico-candles

ARTIFACT: gráfico principal de candles — corpos verde/rosa, linhas horizontais
de referência cada uma com etiqueta de preço colorida na borda esquerda, faixa
tracejada de região, rótulo de anotação junto aos candles, eixo de preço à
direita e cápsula do preço corrente no eixo.

EVIDENCE: `--retrato` recortado em x 0,63–0,98, y 0,34–0,85 ao lado do mesmo
recorte de `destaque_5007_referencia_alvo.jpg` e `destaque_2148_uso_grafico.jpg`.

DEFECT_CLASS: candles sem etiquetas de preço na borda esquerda, ausência da
faixa tracejada, ausência do rótulo de anotação, eixo direito sem cápsula,
candles esparsos demais para a largura, linha de referência sem valor.

## 9 · pressao-instrumento

ARTIFACT: rodapé direito — duas leituras percentuais grandes opostas (alta e
baixa) com barra de sublinhado proporcional, e bloco de identificação do
instrumento com medalhão, ticker, amplitude em pontos e lado do operador.

EVIDENCE: `--retrato` recortado em x 0,63–1,00, y 0,86–1,00 ao lado do mesmo
recorte de `frame_072.jpg` e `destaque_1800_smart_money_regioes.jpg`.

DEFECT_CLASS: barra de pressão de largura total no lugar do par de leituras,
percentuais sem barra proporcional, bloco do instrumento ausente, amplitude sem
unidade, ticker fixo que não vem do símbolo em execução.

## RESOLUÇÕES DO LEAD PÓS-PARTE-0 (antes da rodada 1)

O builder da parte 0 devolveu três achados em `unresolved` que exigiam decisão
antes de as partes 1-12 começarem. Resolvido aqui, não deixado para os
builders decidirem sozinhos (isso duplicaria trabalho ou faria dois autores
escreverem no mesmo arquivo):

1. **Colisão em `nexo/vies.py`**: a região "Bloco de marca" (0,42–0,62 ×
   0,62–1,00, identidade NEXO) não tinha dono. Resolvido: a parte 10 passa a
   se chamar **coerencia-vies-e-identidade** e possui as duas coisas —
   resolvedor de paleta (`cor_vies`) e o bloco de identidade (`desenhar`) —
   já que ambos vivem no mesmo arquivo e ambos são "propagação de linguagem
   visual coerente", não conteúdo de dado.
2. **Vãos mortos**: x 0,34–0,40 (y 0–0,55) e x 0,40–0,63 (y 0,42–0,62) não
   tinham dono. Resolvido: a parte 2 (cena-contexto) absorve o primeiro vão —
   sua região passa de 0,06–0,34 para **0,06–0,40** — e a parte 10 absorve o
   segundo — sua faixa vertical passa de 0,62–1,00 para **0,42–1,00** dentro
   da coluna central 0,40–0,63. Nenhuma parte nova; apenas a fronteira de
   quem pinta o quê.
3. **Faixa amarela de carimbo do simulador** (`ressalva_da_config`, pintada
   pela janela, fora de qualquer parte): é regra do projeto (dado fabricado
   tem de vir carimbado NA imagem) e é ausente num retrato de mercado real —
   os quadros do bar são de mercado real, logo NUNCA terão essa faixa.
   Resolvido: todo crítico abaixo é instruído a **desconsiderar essa faixa
   como artefato do modo simulador**, nunca como defeito de composição —
   não é comparável 1:1 com o bar por natureza, e nenhuma parte tem
   autorização para tentar escondê-la ou encolhê-la (seria mascarar o
   carimbo obrigatório, o que a regra do projeto proíbe).
4. **Nenhum teste trava o mapa macro** — registrado como dívida técnica a
   cobrar no relatório final, não bloqueia a rodada 1.

## 10 · coerencia-vies-e-identidade

ARTIFACT: propagação cromática do viés — resolvedor de paleta por estado
direcional (`nexo/vies.py` + tokens) fazendo o quadro inteiro comutar
coerentemente entre leitura de alta e leitura de baixa, como os quadros do bar
fazem.

EVIDENCE: dois `--retrato` do produto, `--seed 42` e `--seed 7`, lidos lado a
lado com um par de quadros do bar de vieses opostos (`frame_038.jpg` alta
verde × `destaque_5007_referencia_alvo.jpg` baixa vermelha).

DEFECT_CLASS: região que não acompanha o viés, verde e vermelho coexistindo sem
significado, cor como canal único de decisão sem texto/glifo acompanhando,
saturação inconsistente entre regiões, quebra do modo `--sem-cor`.

## 11 · indisponivel-novel  *(teste de região nova — o bar não cobre)*

ARTIFACT: estado honesto de indisponível quando o replay/feed não tem histórico
de book — a superfície OPERADOR B3 inteira comunicando o que **não** pode ser
lido, na mesma linguagem visual, sem liquidez sintética, sem medidor cheio e
sem percentual inventado.

EVIDENCE:
```
python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42 \
  --duracao 2 --workspace "OPERADOR B3" --retrato <path> --retrato-estados-asg
```
lê `<path>_sem_book.png` e `<path>_replay.png`. **Os 95 quadros do bar não
contêm nenhum estado degradado** — não há o que copiar; julga-se por coerência
com a linguagem estabelecida e por honestidade.

DEFECT_CLASS: medidor/percentual mostrando valor cheio sem book (hoje o estado
SEM BOOK ainda pinta CONTEXTO +100% e FORÇA +87% — liquidez fabricada),
indisponibilidade comunicada só por cor, estado degradado com linguagem visual
estranha ao resto, tela que esconde a degradação em vez de nomeá-la.

## 12 · substituicao-instrumento  *(sonda de substituição — entrada regente trocada)*

ARTIFACT: adaptação da superfície ao instrumento regente — grade de tick,
casas decimais do preço, passo da escada, escala do eixo, valores dos chips de
nível, amplitude em pontos e identificação do ticker derivados do símbolo em
execução, nunca cravados.

EVIDENCE: sonda de substituição autoral desta rodada — **uma entrada regente
trocada**:
```
python scripts/painel.py --fonte simulador --simbolo WINV26 --seed 7 \
  --duracao 2 --workspace "OPERADOR B3" --retrato <path>
```
`WINV26` seleciona `WIN_GRID` em vez de `WDO_GRID`
(`fluxopro/app/config.py:171`), com passo de tick e casas decimais diferentes —
verificado: WDO renderiza `4.999,5`, WIN renderiza `4.995`. Qualidade adapta a
tela inteira; mimetismo ou quebra, ou repete calado a resposta do bar
(escala/ticker no formato NASDAQ-CME `28.8xx` dos quadros).

DEFECT_CLASS: casas decimais ou passo de tick presos ao WDO, ticker/exchange
literal copiado do bar, amplitude em pontos calculada com tick errado, escada e
eixo com passo que não corresponde ao grid do símbolo, chips de nível com
valores no formato do bar.

---

## Propriedade de arquivo (exclusiva; nenhum builder edita fora da sua linha)

| # | Parte | owned_files |
|---|---|---|
| 0 | composicao-macro | `fluxopro/ui/paineis/asg.py` (só `PainelNexoMercadoASG.desenhar` + fiação), `fluxopro/ui/paineis/nexo/__init__.py` |
| 1 | escada-preco | `fluxopro/ui/paineis/nexo/ladder.py` |
| 2 | cena-contexto | `fluxopro/ui/paineis/nexo/contexto.py` |
| 3 | faixa-niveis | `fluxopro/ui/paineis/nexo/niveis.py` |
| 4 | banner-estado | `fluxopro/ui/paineis/nexo/banner.py` |
| 5 | placar-estatistico | `fluxopro/ui/paineis/nexo/estatistica.py` |
| 6 | visor-hud | `fluxopro/ui/paineis/nexo/nucleo.py` |
| 7 | grafico-forca | `fluxopro/ui/paineis/nexo/forca.py` |
| 8 | grafico-candles | `fluxopro/ui/paineis/nexo/candles.py` |
| 9 | pressao-instrumento | `fluxopro/ui/paineis/nexo/pressao.py` |
| 10 | coerencia-vies | `fluxopro/ui/paineis/nexo/vies.py`, `fluxopro/ui/tema_asg.py` |
| 11 | indisponivel-novel | `fluxopro/ui/paineis/nexo/indisponivel.py` |
| 12 | substituicao-instrumento | `fluxopro/ui/paineis/nexo/instrumento.py` |
