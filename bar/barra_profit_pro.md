# Barra de Qualidade — Profit Pro / Profit Ultra (Nelogica)

Pesquisa de referência para o gauntlet de um sistema de análise de fluxo (v1). Fontes: Central de Ajuda oficial (`ajuda.nelogica.com.br`, categoria "Ferramentas de Fluxo" + "Módulos Opcionais > Plugin Tape Reading") e blog oficial (`blog.nelogica.com.br`), baixadas em 2026-08-21. HTML bruto das páginas e texto extraído ficam salvos junto dos screenshots (`*_raw.html` / `*_text.txt`) para conferência.

---

## (a) Checklist numerada — inventário completo de ferramentas de fluxo

### 1. Times & Trades
O que mostra: histórico de negócios (trades) executados em um ativo, negócio a negócio, com a direção da agressão (compra/venda) recebida diretamente da B3.
Abas: **Negócios** (data, valor, quantidade, tipo de agressão, marcador `*` quando a ordem varreu mais de um nível de preço), **Ordem Original** (agrupa por ordem original do player, não por negócio individual), **Compradores** / **Vendedores** (representatividade dos players por lado), **Saldo** (compra − venda por corretora, com preço médio calculável por 3 métodos: Padrão, Direto Vol./Qtd., VWAP), **Evolução no Tempo**, e — só no plugin Tape Reading — **Evolução do Player** e **Análise do Player**.
Colunas da visão tabela: Corretora, Porcentagem (%), Vol. Fin., Vol. Qtd. (positivo = comprado, negativo = vendido), Média (colorida verde/vermelha).
Colunas extras do plugin Tape Reading: Agressão Compra, Agressão Venda, Agressão Líquida, Passivo Líquido, L/P Bruto, Leilão.
Uso do trader: identificar qual corretora/instituição está "tomando" o book de um lado, medir agressão líquida por período, e (com o plugin) colorir os players mais ativos por ranking de volume.
Conceito correlato explicado na doc: **RLP** (Retail Liquidity Provider) — trades diretos dentro da corretora, sem passar pelo book.

### 2. Livro de Ofertas ("book")
O que mostra: todas as ofertas de compra e venda por nível de preço (profundidade de mercado), vindas eletronicamente da bolsa.
Abas inferiores: **Preços** (compra em azul à esquerda, venda em vermelho à direita), **Profundidade** (soma acumulada de contratos por 5 níveis + preço médio), **Gráfico** (oferta em linha rosa-claro, demanda em lilás, eixo horizontal = quantidade, vertical = preço), **Ofertas** (lista ordens e agentes, com filtro por agente, cor por regra de lote — ex. "verde-limão" para lotes ≥5).
Recursos: filtro por quantidade/período/agentes, **Escora Institucional** (destaca ofertas grandes e antigas para filtrar "blefes"), **Medidor de Leilão** (realça ofertas que compõem o preço teórico durante leilão), **Netrix** (variante visual do book com barras horizontais verdes de acúmulo por nível).
Uso do trader: ler pressão de compra/venda por nível de preço e detectar ordens grandes "penduradas".

### 3. SuperDOM
O que é: ferramenta de negociação embutida no Livro de Ofertas — DOM (Depth of Market) com envio de ordens padronizado via tecnologia **AutoOp**.
Colunas: (-) Ord. Compra, Qtd. Comp., **Preço** (coluna central), Qtd. Vend., (-) Ord. Venda, PNB, R$.
Modos de operação: **Padrão** (teclado + duplo clique) e **One Click Trading** (clique único do mouse); Ctrl+clique aumenta lote, Shift+clique reduz.
Tipos de ordem: Limitada (pendurada), a Mercado (botões "C Mercado"/"V Mercado"), Stop, e OCO via Editor de Estratégias.
Extras: barras indicativas de Ajuste, Preço de Abertura e VWAP ao lado dos níveis de preço (fixas, não configuráveis); **Volume At Price no SuperDOM** — barras verdes de volume à esquerda e barras azul(compra)/vermelho(venda) de agressão; centralização automática de preço; layout Padrão ou Scalper.
Uso do trader: operar diretamente no book, com contexto visual de onde está o volume/agressão.

### 4. Volume At Price (VAP) / Volume At Market
O que mostra: volume negociado por nível de preço, plotado no eixo do livro/gráfico (histograma horizontal).
Diferença citada na doc: Volume At Price complementa a leitura do Livro de Ofertas junto com Times & Trades; Volume At Market é tratado como ferramenta irmã na mesma seção "Ferramentas de Fluxo".
Uso do trader: achar níveis de preço com maior liquidez negociada (não só ofertada).

### 5. Volume Profile
O que mostra: no próprio gráfico de candles, um histograma lateral de volume negociado por faixa de preço ao longo do período.
Configurações: Exibir Trades Diretos, Exibir Trades de Leilão, Barras por Agressão (cor por lado comprador/vendedor), Exibir Volume Acumulado, **Destacar Maior Barra de Volume = POC (Point of Control)** — plotado em vermelho, Escrever Volume ao Destacar (hover mostra valor numérico).
Modos: automático (um perfil por candle/dia) ou personalizado (um único bloco de VP para um intervalo selecionado arrastando o mouse).
Limites de profundidade histórica por ativo: WIN 8 dias, WDO 30 dias, DOL/IND 180 dias, ações Bovespa 360 dias.
Uso do trader: achar zonas de valor (value area) e o preço de maior negociação (POC) para suporte/resistência.

### 6. Gráfico de Força / Gráfico Tape Reading (Footprint) — plugin Tape Reading
O que mostra: dentro de cada candle (tick), duas colunas de histograma — esquerda = agressão na **venda**, direita = agressão na **compra** — por nível de preço, lidas na diagonal (bid×ask por nível).
Elementos adicionais no candle: dois retângulos — o de cima é o saldo (compra − venda: negativo = pressão vendedora, positivo = pressão compradora), o de baixo é o volume total somado (compra + venda).
Parâmetros avançados citados: Imbalance, Sequencial, Exaustão (documentados em artigo à parte).
Disponibilidade: nativo no Profit Ultra; contratável como módulo opcional nas demais versões (One, Plus, Pro, White Label).
Uso do trader: casar leitura de fluxo (quem agrediu, quanto) com leitura gráfica (onde o preço reagiu), no mesmo candle.

### 7. Cumulative Delta (Delta acumulado)
O que mostra: gráfico auxiliar (abaixo do gráfico principal) da agressão líquida acumulada por período — soma contínua de (volume comprador − volume vendedor).
Cores: barra verde = maior acúmulo de agressão compradora no período; barra vermelha = maior agressão vendedora.
Configuração: tipo de volume (Quantidade padrão, Financeiro, Negócios); aba Aparência para cor/estilo de linha.
Uso do trader: confirmar ou divergir a tendência de preço com a força real de fluxo (ex. preço sobe mas delta cai = possível exaustão).

### 8. Medidores de Agressão / Medidores de Pressão
O que mostra: barra/faixa colorida de largura total (vermelha ou verde) exibindo o saldo acumulado de agressão do dia (ou desde hora configurada) para um ativo — "(49,10k)" vermelho = saldo vendedor líquido; "(42,31k)" verde = saldo comprador líquido.
Uso do trader: visão instantânea, tipo termômetro, da pressão dominante no ativo sem abrir gráfico.

### 9. Ranking de Ativos / Ranking de Corretoras (identificação de grandes players)
O que mostra: compilado da performance das corretoras no dia — Volume Total, Negócios, Volume de Compra/Venda, Saldos Positivo/Negativo — com gráfico de pizza colorido das 10 maiores corretoras por volume, e tabela abaixo com as demais.
Colunas do Ranking de Ativos (plugin Tape Reading): Saldo Participação, Saldo Agressão, Posição Saldo Agressão (★ força vs. histórico do próprio player), Taxa de Participação, Posição Taxa de Participação, Lote Piorado (quanto o player piora seu próprio preço), Posição Lote Piorado, Volume Quantidade, ADV (vs. volume médio de vários dias), **Algoritmo** (identifica TWAP/POV/outros), Status (Estável/Aumentando/Decrementando/Desativado/Reativado), Início/Fim.
Uso do trader: identificar liquidez do dia por corretora e detectar algoritmos institucionais em operação (TWAP, POV visíveis nos screenshots).

### 10. Análise de Ativo / Análise de Players (plugin Tape Reading)
O que mostra: dispersão (scatter) de players por corretora em quadrantes de volume × persistência — quadrante superior-esquerdo = players de maior volume e maior persistência de compra/venda = maior impacto no preço.
Variáveis: Quantidade negociada, Taxa de Participação, ADV.
Uso do trader: separar "ruído" (players erráticos) de players que realmente movem o preço.

### 11. Bookmap / Mapa de Calor (Heatmap) do book
O que mostra: heatmap de liquidez do book ao longo do tempo — eixo Y = preço, eixo X = tempo, intensidade de cor = tamanho da oferta parada naquele nível; bolhas coloridas sobrepostas = negócios executados (verde = compra agressora, vermelho = venda agressora), tamanho da bolha = volume do negócio.
Painéis laterais: COB (contas/book) e SVP (Session Volume Profile) com números de volume por nível.
Escala de cores configurável (azul→ciano→amarelo→vermelho = liquidez crescente, no screenshot de referência).
Disponível como módulo opcional em White Label, Profit One, Pro e Ultra.
Uso do trader: ver onde a liquidez está "empilhada" e antecipar níveis de suporte/resistência antes de serem testados.

### 12. Filtro de players / corretoras e coloração por ranking
Recurso transversal (Times & Trades, Livro de Ofertas): permite monitorar agentes específicos, atribuir cor por agente ou por faixa de lote, e colorir players por posição no ranking de volume/agressão/negócios.

### 13. Replay de Mercado
O que faz: recarrega todos os negócios/trades de um pregão anterior para estudo, usando o preço negociado no momento (sem reconstituir fila/liquidez real).
Controles: play/pausa, avanço trade a trade, avanço para horário específico, velocidade 0,1x–10x (Profit Pro/Ultra; até 5x nas White Label); no Profit Ultra é possível arrastar a barra do tempo para voltar atrás sem reiniciar a sessão.
Requer Módulo de Simulação para operar de forma simulada durante o replay. Suporta séries históricas de contratos vencidos (WINFUT, INDFUT, WDOFUT, DOLFUT) e replay de múltiplos ativos.
Uso do trader: testar leitura de fluxo e estratégias discricionárias contra dias reais já ocorridos.

### 14. Alarmes / Alertas
Alarmes de Agressão (plugin Tape Reading): gatilhos configuráveis por Compra/Venda de um ativo, Inversão, Presença de player específico, Algoritmo detectado, etc.
Notificações gerais: som e/ou mensagem na tela, configuráveis por tipo de evento (menu Notificações > Alertas).

### 15. Automação / Estratégias (NTSL)
Editor de Estratégias: linguagem proprietária **NTSL** (Nelogica Trading System Language, sintaxe próxima de Pascal/EasyLanguage) para codificar, testar (backtest) e simular estratégias.
Tipos de estratégia: indicador, regra de coloração, execução (backtest/automação ao vivo), alarme, seleção (screening).
Automação de Estratégias: ativação/execução ao vivo das estratégias codificadas, inclusive rodando contra o Replay.
Loja de Estratégias (marketplace): desenvolvedores parceiros comercializam estratégias prontas.

---

## (b) Descrição visual da UI

- **Tema**: escuro (dark theme) em toda a plataforma — fundo quase preto/azul-marinho muito escuro (`#0c0f14`–`#151a22` aproximado), sem opção clara aparente nos prints oficiais.
- **Densidade**: muito alta — grids compactos, fonte pequena (~11-13px), muitas colunas numéricas lado a lado, várias janelas/painéis (MDI, tipo "múltiplas janelas internas") abertos simultaneamente lado a lado (gráfico + book + T&T + ranking).
- **Cor de compra/bid**: **azul** predomina no Livro de Ofertas e no SuperDOM (coluna esquerda de compra); barras de agressão de compra também aparecem em **azul** no Volume At Price do SuperDOM.
- **Cor de venda/ask**: **vermelho/vinho** na coluna de venda do book e SuperDOM; no Livro de Ofertas (aba Preços) é explicitamente "azul para compra, vermelho para venda".
- **Verde vs. vermelho**: usado para saldo/delta/indicadores de agressão e pressão (verde = líquido comprador, vermelho = líquido vendedor) — Cumulative Delta, Medidores de Agressão, coluna "Média" do Times & Trades. Ou seja, a plataforma usa **dois pares de cores diferentes**: azul/vermelho para book e ordens, verde/vermelho para saldo e pressão agregada.
- **Candles**: nos gráficos de preço os candles de alta aparecem **brancos (ocos)** e os de baixa **pretos (preenchidos)** — não o padrão verde/vermelho comum em outras plataformas — com "Fch" (fechamento) em vermelho e "A" (atual) em verde no cabeçalho do ativo.
- **Amarelo**: usado para destaque de nível/preço central no SuperDOM e para tarjas de aviso (ex. tarja amarela quando o Replay está ativo).
- **Bookmap/heatmap**: paleta contínua azul-escuro → ciano → amarelo → vermelho para intensidade de liquidez, com bolhas verdes/vermelhas sobrepostas marcando negócios executados por tamanho.
- **Gráficos de pizza** (Ranking de Corretoras): paleta categórica de ~10 cores distintas (azul, roxo, laranja, verde, ciano, amarelo, etc.), uma por corretora, com % rotulado em caixas.
- **Ícones/topo de janela**: barra de título compacta em cada painel com ticker, variação %, e ícones de compartilhar/redimensionar/fechar — cada ferramenta é uma "janelinha" independente dentro da plataforma.

## (c) Screenshots salvos

Todos em `C:\Users\Usuário\Desktop\CLAUDE\fluxo_pro\bar\` (23 imagens PNG/WEBP baixadas diretamente das páginas oficiais):

| Arquivo | Ferramenta | Fonte |
|---|---|---|
| `01_times_trades_a/b/c.png` | Times & Trades (Negócios, Ranking de corretoras/pizza, configurações) | ajuda.nelogica.com.br |
| `02_superdom_a/b/c.png` | SuperDOM (painel de negociação, DOM completo) | ajuda.nelogica.com.br |
| `03_livro_ofertas_a/b/c.png` | Livro de Ofertas (Preços/Profundidade/Ofertas) | ajuda.nelogica.com.br |
| `04_ranking_corretoras_a/b.png` | Ranking de Corretoras (pizza + tabela) | ajuda.nelogica.com.br |
| `05_cumulative_delta_a/b.png` | Cumulative Delta (barras + gráfico de candle) | ajuda.nelogica.com.br |
| `06_medidores_agressao_a/b.png` | Medidores de Agressão/Pressão (barra vermelha/verde) | ajuda.nelogica.com.br |
| `07_grafico_func_a/b.png` | Ferramentas gráficas gerais | ajuda.nelogica.com.br |
| `08_replay_a/b.png` | Replay de Mercado (tarja amarela, controles) | ajuda.nelogica.com.br |
| `09_tape_reading_a/b.png` | Gráfico Footprint / Análise de Ativo (plugin Tape Reading) | ajuda.nelogica.com.br |
| `10_bookmap_heatmap_a/b/c.webp` | Bookmap — mapa de calor do book, escala de cores | blog.nelogica.com.br |

Também salvos: HTML bruto (`*_raw.html`) e texto extraído (`*_text.txt`) de 12 páginas oficiais (Times & Trades, SuperDOM, Livro de Ofertas, Volume Profile, Ranking de Corretoras, Cumulative Delta, Medidores de Agressão, Plugin Tape Reading, Replay de Mercado, Gráfico: Funcionalidades e Ferramentas, Automação de Estratégias, Editor de Estratégias, Conheça o Profit Ultra) — para conferência textual sem depender de acesso à internet.

## (d) Núcleo de fluxo — o que um sistema v1 PRECISA ter para ser comparável

Subconjunto mínimo (sem isso, não é comparável a um "Profit Pro simplificado"):

1. **Times & Trades** — feed de negócios com direção de agressão (compra/venda), preço, quantidade, hora.
2. **Livro de Ofertas (book)** — profundidade de preço, compra (azul) à esquerda / venda (vermelho) à direita, por nível.
3. **Saldo de agressão / Delta** — líquido comprador vs. vendedor por período, com indicação visual verde/vermelho (equivalente a Medidores de Agressão + Cumulative Delta simplificado).
4. **Volume por preço (VAP/Volume Profile)** — histograma de volume por faixa de preço, com destaque do nível de maior volume (equivalente ao POC).
5. **Ranking/filtro de corretoras ou players** — mesmo que simplificado, mostrar "quem" está dominando o volume do dia.
6. **Gráfico de candles integrado ao fluxo** — candle + indicador de delta/agressão abaixo, para correlacionar preço com força de fluxo (versão simplificada do Footprint/Gráfico de Força).

Fora do núcleo mínimo, mas desejável para paridade mais completa (v2+): SuperDOM com envio de ordens, Bookmap/heatmap, Replay de mercado, Alarmes de agressão, Automação/NTSL, Análise de Players (persistência/relevância), Ranking de Ativos com detecção de algoritmo.

---

**Nota de auditoria**: a categoria oficial "Ferramentas de Fluxo" da Central de Ajuda Nelogica lista exatamente: PriceTrader, Times & Trades, Volume At Market, Mapa de Fluxo, Identificando os Grandes Players, Medidores de Pressão, Livro de Ofertas, SuperDOM, Volume At Price — usada aqui como lista canônica da própria fabricante, cruzada com o módulo opcional "Plugin Tape Reading" (Footprint, Ranking de Ativos, Análise de Ativo/Players, Alarmes de Agressão) e os indicadores gráficos "Cumulative Delta" e "Medidores de Agressão".
