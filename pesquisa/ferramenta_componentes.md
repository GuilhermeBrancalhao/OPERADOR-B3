# Engenharia reversa conceitual da ASG (Sérgio Gargantini) — componentes, medidas e sinais

Fonte: transcrições em `pesquisa/legendas/*.txt`. Método: extrair o que o autor DIZ que a ferramenta faz e o que se pode INFERIR do comportamento demonstrado na tela. Nunca inventar fórmula, limiar ou threshold que não apareça na fala. Toda citação é literal e curta (≤15 palavras).

Convenção de classificação: **CONFIRMADO** (o autor descreve explicitamente o mecanismo) / **IMPRECISO** (ele fala, mas de forma vaga, sem parâmetro) / **INFERIDO** (dedução minha a partir do comportamento mostrado — marcada como tal).

---

## 1. Maker

**O que mede.** Um indicador percentual (ex.: "8%", "26%") que representa, segundo o autor, o interesse líquido de compra/venda dos *market makers* — não é leitura de nome de corretora, é "leitura sofisticada" de comportamento algorítmico. CONFIRMADO que ele NÃO usa identidade de corretora: *"a ASG não considera nome de corretor"* (`BbnGYiwygFQ.txt`). O próprio autor cita inspiração em "speedofer" (grafia dele) — disputa de HFTs pelo topo do book.

**Dado de entrada.** IMPRECISO/AUSENTE NA FONTE — o autor nunca revela a fórmula. Ele descreve o fenômeno-alvo (absorção de agressão, reposicionamento de book, disputa por liquidez) mas não o cálculo: *"o reposicionamento do book, a própria disputa por liquidez"* (`BbnGYiwygFQ.txt`). É plausível que combine book (nível de reposição/absorção) com fluxo agressor, mas isso é INFERIDO, não confirmado.

**Estados/cores.** Percentual + cor: verde = "estável em um nível mais comprador"; vermelho = estável vendedor; cinza = "irrelevante" (ainda ajustando, sem convicção). Limiar citado pelo autor: *"acima de 6 a 7% de forma estável"* passa a ganhar relevância (`BbnGYiwygFQ.txt`); valores de 20-26% são tratados como excepcionais (`7P4_13Fkmuk.txt`).

**Sinal emitido.** Divergência entre Maker e o contexto (micro/macro) é o sinal central: Maker oposto ao movimento de preço sugere que o player está "trabalhando uma posição", não uma exposição — script clássico de acumulação distribuída (ir contra o próprio fluxo aparente para não mover o preço médio). Não é gatilho de entrada; é alerta de atenção/gestão de risco (puxar stop).

**Reproduzível com nosso feed?** NÃO com dados MBP/book nível 1-2 do MT5 sem identidade — o mecanismo real é desconhecido (AUSENTE NA FONTE), então não há especificação para replicar, só o comportamento-alvo. Poderíamos tentar um proxy análogo a `PerfilPlayer`/`DetectorEscora`+`DetectorAbsorcao` combinados numa janela, mas seria uma reinterpretação nossa, não uma cópia informada.

---

## 2. Placar Estatístico

**O que mede.** Contagem simples de quantos sinais principais da ASG estão "confluindo" para compra vs. venda, expressa como placar de futebol (ex. "4 a 0", "3 a 1"). CONFIRMADO: *"é uma leitura da própria ASG... ele lê os sinais que a SG já lê do mercado"* (`Rwm3uzxZhhc.txt`) — ou seja, é uma meta-leitura (soma de sinais internos), não leitura direta do mercado.

**Componentes somados** (conforme o autor lista, um a um, na tela): contexto micro, contexto macro, a "setinha" (Sniper ASG), suporte/resistência, e o "auxílio do ChatGPT" — até 5 fontes possíveis, daí placares até 5 a 0.

**Janela.** Não é uma janela temporal fixa — é o estado atual dos outros indicadores no instante.

**Como se lê.** Placar estável (sem oscilar) = confluência real, "aguardar se de fato existe uma confluência mais estável". Nos primeiros minutos de pregão a oscilação é esperada (ruído de abertura) e não deve ser operada. Regra de disciplina: evitar operar contra o placar quando é "goleada" (4-0, 5-0); quando empata ou vira, é sinal de possível reversão e de proteção antecipada de posição.

**Sinal emitido.** Nenhum sinal numérico próprio — é agregação; o "sinal" é a mudança do próprio placar ao longo do tempo (de 5-0 para 3-1, por ex.), interpretada como alerta de virada.

**Reproduzível?** SIM, estruturalmente — é apenas um somatório de outputs de outros detectores que já produzimos ou pretendemos produzir (contexto micro/macro, sinal de exaustão/sniper, S/R). Não depende de dado exclusivo (book de identidade), depende de termos os sub-sinais prontos.

---

## 3. Velocímetro / Aceleração da micro

**O que é medido.** O autor usa a metáfora do carro/velocímetro para "aceleração" — mas a evidência textual mostra que o que ele chama de "acelerar" é a variação do valor numérico da micro ao longo do tempo (ela sobe/desce de número em número): *"535, ó, 537, 541... ela não tá perdendo o sinal"* (`w8YGyNl5m24.txt`) e *"tá 410, 389, 300... ela virou"* (mesmo arquivo). Ou seja, é a magnitude/velocidade da mudança de um contador de fluxo de curto prazo (a "micro"), não necessariamente velocidade de negócios per se.

**Escala numérica mencionada.** Nas transcrições lidas aqui aparecem exemplos como "400, 600" (`w8YGyNl5m24.txt`) e valores de macro como "100, 1200, 1500... 1900, 25" (`kzvx33vruic.txt`, `Cbj66x1JXoA.txt`). Não há na fonte um limiar fixo do tipo "acima de 250 = forte" — os valores citados variam por dia e por ativo, e o autor trata "grandeza" (magnitude) e "manutenção" (não perder o sinal) como os dois eixos, não uma escala fixa universal. Portanto: **AUSENTE NA FONTE** a escala fixa "250, 300, 400" mencionada na extração anterior — nesta leitura direta das transcrições, os números citados são contextuais/dia-a-dia, não uma tabela de calibração fixa e documentada. Isso precisa ser marcado como IMPRECISO/não confirmado nesta rodada de fontes.

**Estados.** Aceleração = manutenção/renovação do valor no mesmo sentido (não perde o sinal); desaceleração = o valor "perde força", análogo a "tirar o pé do acelerador" — o preço tende a perder tração e reverter.

**Reproduzível?** SIM, conceitualmente — é a derivada/momentum de um contador de fluxo agressor de curto prazo. Já temos primitivas equivalentes (delta, agressão) em `fluxopro/analytics/delta.py` e `agressao.py`; falta um "velocímetro" explícito = taxa de variação desses contadores numa janela curta, com estado de aceleração/desaceleração.

---

## 4. Machine Learning / IA

**O que o autor efetivamente diz.**
1. Existe integração com ChatGPT via API da OpenAI: a ASG envia um resumo do contexto e recebe de volta uma leitura textual com níveis de preço e viés — com latência perceptível (não é tempo real): *"ela envia sinal por API pra empresa do Chat GPT"* (`_zs79_15iJQ.txt`). Isso é um LLM consultivo (texto explicativo com preços-chave), não um classificador binário de sinal de entrada. O próprio autor avisa: *"não serve como um gatilho de entrada como a SG"* (`_zs79_15iJQ.txt`).
2. Há uma menção separada, mais vaga, a "machine learning": *"a SG, ela gera relatórios... um processo chamado machine learning, que ele me dá estatística... sugestões do que pode ser melhorado na ASG"* (`w8YGyNl5m24.txt`). Isso descreve um processo de **auto-diagnóstico/melhoria do próprio sistema** (meta-análise de desempenho dos indicadores), não um modelo preditivo de preço rodando ao vivo na tela.

**Evidência real vs. marketing.** Não há, nas fontes lidas, nenhuma descrição de um modelo de ML classificando padrões de mercado em tempo real (tipo "IA prevê que vai subir"). O que existe documentado: (a) um LLM de terceiros (ChatGPT/OpenAI) consultado via API, com atraso, para dar contexto textual; (b) uma alegação de uso de "machine learning" para gerar relatórios de melhoria do próprio produto — sem detalhe técnico, e reconhecidamente `AUSENTE NA FONTE` quanto a arquitetura, features ou validação. Não encontrei o vídeo `RNGQ-BJWMWo.txt` ("Velocímetro com Machine Learning") no diretório — **arquivo não existe em `pesquisa/legendas/`**, portanto essa alegação específica de "Velocímetro com ML" não pôde ser verificada nesta pesquisa.

**Reproduzível?** O componente (b) do ChatGPT é trivialmente reproduzível (chamada de API com prompt sobre o estado agregado dos indicadores). O componente de "ML interno" é opaco — nada a copiar, só a ideia genérica de logging + análise de desempenho, que já é boa prática de engenharia, não uma feature de trading.

---

## 5. Barras laterais / regiões destacadas (o "novo leitor de volume")

**O que é.** Um perfil de preço customizado no lado esquerdo da tela, visualmente parecido com Volume Profile / Volume at Price, mas filtrado para mostrar só ~3 preços "importantes" por vez (não o perfil completo). CONFIRMADO pelo autor: *"é um vap, é um volume profile... só que eu consigo trabalhar num nível de... refinamento"* (`3mfeHZhMZrc.txt`); e explicitamente: *"não tem nada a ver tipo com o que tem na profit"* (`iMaYILO80j8.txt`) — ele nega ser volume agregado bruto de plataforma de varejo.

**Dado de entrada.** Volume executado por nível de preço (barras), aparentemente com algum filtro de relevância que descarta a maioria dos níveis ("lixo do fluxo") e destaca só os que ele julga estatisticamente importantes. O filtro exato é **AUSENTE NA FONTE** — ele diz que "filtrou os dados" e "extrai do jeito que eu quero" mas não revela o critério.

**Estados/leitura.** Barra grande = nível relevante, reforça uma região de Smart Money quando coincide com ela; barra ausente/pequena = "lixo", preço tende a atravessar rápido (região de baixa fricção). Só os 3 preços em destaque (por vez) importam; o resto é ruído deliberado.

**Sinal emitido.** Não é sinal de entrada isolado — funciona como confirmação: preço sustentando-se acima/abaixo de uma barra grande + micro acelerando na mesma direção = gatilho válido; preço batendo na barra e não passando = reforço de reversão/scalp contrário.

**Reproduzível com nosso feed?** SIM, em princípio — é volume-por-preço a partir de trades/ticks, algo que `fluxopro/analytics/volume_profile.py` já deveria cobrir na sua forma clássica. O que falta é o "filtro de relevância" que reduz a poucos níveis — critério desconhecido, precisaria ser desenhado por nós (ex.: percentil de volume, ou volume por nível vs. média móvel do dia).

---

## 6. Gráficos: Renko e Temporal — gatilhos específicos

### 6.1 Gráfico de Renko
- Mostra blocos por deslocamento de preço (não por tempo). Cada dia gera até 3 "alvos" para cada lado: **A1/A2/A3 positivos** (alvos do comprador, acima) e **A1/A2/A3 negativos** (alvos do vendedor, abaixo).
- Regra de leitura CONFIRMADA: as regiões de alvo do vendedor (sinal "−") são estatisticamente as melhores para pensar em COMPRA de contratendência (é onde o vendedor realiza), e vice-versa para venda no alvo do comprador. *"essa região é também de fato as piores regiões para você atuar a favor da tendência"* (`ijsZl8EzeH8.txt`).
- Regra de disciplina: nunca vender no alvo negativo, nunca comprar no alvo positivo — são os "piores preços" para entrar a favor do movimento (alto risco de falso rompimento).
- "Cor interna" do Renko (um segundo gráfico sobreposto/"sombra"): verde = tendência sustentada; cinza = perda de força/possível lateralização; vermelho = possível inversão de fase. Funciona como sinal de alerta antecipado, "pode antecipar algo que a micro ainda não confirmou" (`w8YGyNl5m24.txt`).
- Regiões "entre" os alvos = "buraco negro" — preço corre mais rápido, pior lugar para operar (nem entrada nem stop confiável).

### 6.2 Gráfico Temporal
- Mostra até ~5-6 preços fixos do dia ("holograma") — os melhores pontos de entrada/stop, plotados como linhas horizontais dinâmicas (mudam de posição/relevância ao longo do dia).
- **Linha azul**: referência de "amplitude média da frequência do dia" — divide o gráfico numa lógica de viés: preço abaixo dela = pensar em venda; acima = pensar em compra, até romper.
- Linha verde = suporte (preço tende a ficar acima); linha vermelha = resistência; podem trocar de cor quando o preço cruza (perde a região).
- **Zona de stop** (faixa vermelha) e **zona amarela** (primeira camada, "menos técnica"): regiões sugeridas para posicionamento de stop, atualizadas dinamicamente, e sempre determinadas pelo lado que a "micro" favorece no momento.
- Regra chave (contexto vs. estrutura, `Cbj66x1JXoA.txt`): mercado só é considerado "vendedor" de fato quando perde a mínima do dia (ou a região de abertura); enquanto o preço permanece acima da abertura/próximo da máxima, qualquer venda é "momentânea", não estrutural — mesmo com macro/micro negativas.

**Reproduzível?** O conceito de alvo por amplitude (Renko A1/A2/A3) e linhas de S/R dinâmicas por "amplitude média da frequência" é **INFERIDO como replicável** com ATR/range-based projections — mas o cálculo exato de "amplitude média da frequência do dia" é AUSENTE NA FONTE (não há fórmula revelada).

---

## 7. Caso WINFUT — "o dia em que o fluxo enganou todo mundo" (`kzvx33vruic.txt`)

**Cenário descrito pelo autor (11/02):** durante ~90% da sessão a macro ficou negativa (chegando a picos de −1500, −1735, −1925 no contador de contexto macro), mas o preço, em vez de continuar caindo, subiu — criando uma aparente contradição entre "contexto vendedor" e "preço subindo".

**Explicação do autor:** os vendedores (não necessariamente um único player, mas "o conjunto") teriam manipulado o mercado subindo enquanto vendiam ("sobem vendendo e depois descarregam a venda") — descrito pelo autor como possível "busca de liquidez", termo que ele mesmo relativiza ("tanto faz o que for"). A macro chegou a inverter para um pico positivo de ~+900/+915, mas **nunca se aproximou da magnitude dos picos vendedores** (−1925) e reverteu rapidamente ("em poucos minutos ele praticamente retrocede tudo").

**O ponto de falha que ele expõe (valioso para teste):** ler só o valor absoluto do contador de contexto no momento presente é insuficiente — é preciso comparar a MAGNITUDE do pico oposto contra o histórico de magnitude do dia, e observar o TEMPO de permanência em cada lado (a maior parte da sessão foi vendedora; o pico comprador foi breve). Quem comprou o rompimento da "estrutura" sem essa comparação teria ficado "mal posicionado" quando o mercado devolveu >2.500 pontos e rompeu a mínima do dia.

**Por que é valioso como caso de teste:** revela um limite real do método — o "contexto macro" isolado (soma cumulativa point-in-time) pode inverter de sinal por período curto sem que isso represente reversão real; a leitura correta exige normalizar por (a) magnitude relativa ao histórico intradiário e (b) persistência temporal, não só o sinal instantâneo. Isso é diretamente testável contra qualquer indicador de contexto cumulativo que viermos a construir: um "contexto macro" ingênuo teria dado sinal de compra falso nesse dia.

**Classificação:** CONFIRMADO quanto ao comportamento relatado pelo autor (valores e sequência dos fatos, conforme narrado por ele — não há dado bruto independente para auditar); a "explicação causal" (manipulação deliberada / busca de liquidez) é a INTERPRETAÇÃO do autor, não um fato verificável a partir da transcrição.

---

## 8. Ruído vendedor vs. estrutura (`Cbj66x1JXoA.txt`)

**Regra estrutural CONFIRMADA:** o mercado só muda de regime (de comprador para vendedor) quando perde referências estruturais concretas — a mínima do dia e/ou a região de abertura — não apenas por um candle ou movimento de venda pontual. Enquanto o preço permanece acima da abertura e "próximo à máxima" (mesmo com barrigadas de até ~1000 pontos), o autor classifica o mercado como estruturalmente comprador; movimentos de venda dentro disso são "ruído"/"ondulação momentânea", não reversão.

**Critério de distinção dado pelo autor:**
1. Structural: perder mínima/abertura = mudança real de regime. Não perder = ruído, independente de quão "forte" pareça o candle.
2. Persistência: uma micro vendedora que não é "renovada" (não faz nova mínima) perde força e tende a reverter — análogo ao "tirar o pé do acelerador".
3. Ele explicitamente rejeita ler candle isolado ("candle vendedor... acha que o mercado tá fritando") como prova de mudança de estrutura.

**Reproduzível?** SIM — isso é essencialmente uma regra de "regime de tendência por máxima/mínima do dia" (comparável a um filtro de estrutura de swing highs/lows), perfeitamente implementável com dados de tick/OHLC puros, sem precisar de book ou identidade de corretora.

---

## MAPA PARA O NOSSO CÓDIGO

Arquivos lidos: `fluxopro/microestrutura/detectores.py` (Absorção, Escora, Iceberg, Liquidez Fantasma, Exaustão, Clip Institucional) e `fluxopro/microestrutura/perfil_player.py` (`PerfilPlayer`, agregação por `broker`). Também `fluxopro/analytics/` (`agressao.py`, `delta.py`, `footprint.py`, `volume_profile.py`, `vwap.py`) — não lidos linha a linha nesta pesquisa, mas confirmados existentes por nome.

| Componente ASG | Equivalente hoje | Status |
|---|---|---|
| **Maker** | Nenhum direto. `PerfilPlayer` agrega por `broker` (exige `buyer_broker`/`seller_broker`), mas o Maker do autor explicitamente NÃO usa identidade de corretora — é comportamental. `DetectorEscora`+`DetectorAbsorcao`+`DetectorClipInstitucional` cobrem partes do comportamento-alvo (reposição, absorção, regularidade tipo TWAP), mas nada os combina num percentual único de "viés oculto". | **Falta construir** — e é o mais complexo, porque a própria fonte não revela o mecanismo. |
| **Placar Estatístico** | Não existe um agregador. Os sub-sinais (contexto micro/macro, exaustão) têm equivalentes parciais em `analytics/agressao.py`/`delta.py`; falta o somatório com "placar" e a lógica de estabilidade/oscilação. | **Falta construir** (mas é simples — agregação de outputs já existentes ou a existir). |
| **Velocímetro/aceleração da micro** | Nenhum "velocímetro" explícito. `analytics/delta.py` deve dar o contador bruto; falta a derivada/momentum com estado aceleração/desaceleração. | **Precisa ajuste** — construir a camada de taxa de variação sobre o que já existe. |
| **IA/LLM consultivo** | Não existe. É infraestrutura pura (chamada de API), sem relação com detectores de microestrutura. | Falta construir, mas é baixa prioridade/baixo valor analítico (o próprio autor diz que "é o que menos importa"). |
| **Barras laterais (volume por preço filtrado)** | `analytics/volume_profile.py` deve cobrir o profile clássico. Falta o filtro de relevância (reduzir a poucos níveis "importantes"). | **Precisa ajuste** — camada de seleção/ranking sobre volume profile existente. |
| **Renko A1/A2/A3 + cor interna** | Nenhum equivalente. Não achei um módulo de "projeção de alvos por range" nem de "estado de fase" (verde/cinza/vermelho). | **Falta construir.** |
| **Gráfico temporal (linha azul, S/R dinâmicos, zona de stop)** | Parcialmente comparável a suporte/resistência dinâmico, mas não vi módulo de S/R em `analytics/`. | **Falta construir** (fora do escopo microestrutura pura — é mais projeção estatística de range). |
| **Regra estrutural (perde mínima/máxima do dia = mudança de regime)** | Nenhum módulo de "estrutura de swing" identificado nos arquivos lidos. | **Falta construir**, mas é simples e maior valor por esforço. |
| **DetectorClipInstitucional (TWAP/POV) — já existe** | Já existe e é robusto (CV de tamanho e intervalo, dataclass `ConfigClipInstitucional`). Cobre parcialmente a "regularidade" que caracteriza HFT/algoritmo mencionada nos vídeos `BbnGYiwygFQ.txt`/`7P4_13Fkmuk.txt` (reposição de ordens, disputa por liquidez), mas o Maker do autor é mais amplo (combina book + fluxo), enquanto nosso detector só olha trades. | Existe, mas cobre só uma fatia do que o autor descreve como "Maker". |

### Os 3 componentes mais valiosos ainda ausentes do nosso código

1. **Regra estrutural de regime (máxima/mínima do dia)** — maior retorno por esforço: simples de implementar com dados de tick/OHLC puros (sem book, sem identidade), e o caso WINFUT mostra que é exatamente o que faltaria para não ser enganado por um "contexto macro" ingênuo baseado só em soma cumulativa instantânea.
2. **"Velocímetro"/momentum sobre os contadores de contexto (micro/macro)** — normalizar por magnitude histórica intradiária e por persistência temporal, não só ler o valor absoluto no instante — é a lição central do caso WINFUT e falta como camada explícita sobre `analytics/delta.py`.
3. **Placar Estatístico (agregador de confluência com detecção de estabilidade/oscilação)** — baixo custo de construção (é só orquestração dos outros sinais) e alto valor prático de disciplina operacional (evitar operar em ruído/empate).

**Nota de viabilidade de dados:** todos os 3 acima são construíveis com tick + candle puro do MT5 (sem depender de book de identidade nem de MBO/MBP profundo) — não esbarram na limitação de dados descrita em `pesquisa/fontes_de_dados.md`. Já o "Maker" — o sinal mais valioso segundo o autor — depende de mecanismo não revelado e possivelmente de granularidade de book que nosso feed (MetaTrader5, sem RLP/identidade, book nível 1-2) pode não sustentar com a mesma fidelidade.
