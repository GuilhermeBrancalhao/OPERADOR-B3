# Metodologia de Leitura de Fluxo — Especificação Operacional

Extraído de transcrições (legendas .vtt/.txt, `pesquisa/legendas/`) de 11 vídeos:
6UPPrXrYeOY, ri9myKnGm9k, cyJVLkoZIvk, zenDbXgFEEw, SHjx2aHkmVA, xhpnmyQohPg,
FmURmlN3boI, TPk39osWiKY, W7lNHhliZXU, vs76O7j_inU, EPqye9iLNig.

Aviso metodológico: a legenda é automática (fala transcrita por máquina), contém
erros de grafia e nomes ("SG"/"ASG" parece ser sigla da ferramenta proprietária
do autor — provavelmente "Smart Grid" ou nome de marca; não aparece por extenso
em nenhum trecho lido — sinalizado como possível erro/abreviação não resolvida).
Toda citação abaixo tem no máximo ~15 palavras e serve só para ancorar a regra.

---

## 1. Indicador percentual comprador × vendedor ("SG"/"ASG")

**Definição operacional (CONFIRMADO):** ferramenta proprietária do autor mostra
uma porcentagem de "esforço" comprador vs. vendedor, calculada algoritmicamente
a partir do fluxo (não é o delta clássico de agressão explicado em fórmula —
o autor nunca diz "delta = compras a mercado − vendas a mercado"; ele descreve
o resultado, não o cálculo).

- Citação: "notem que nós temos aqui uma porcentagem 81% vendedora" (vs76O7j_inU)
- Cor = direção: "tudo que for vermelho na SG refere-se à leitura vendedora... tudo que é verde, leitura compradora... amarelo... indecisão" (vs76O7j_inU) — CONFIRMADO
- 50/50 = mercado sem lado definido: "pode ser que você veja ele 50% de compra, 50% de venda. Isso já mostra que não existe lado" (vs76O7j_inU) — CONFIRMADO, mercado tende a lateralizar
- Limiar de "direcional": "acima de 75% já é uma amostragem mais direcional" (vs76O7j_inU) — CONFIRMADO (75%, não exatamente 70%)
- Faixas mais detalhadas (outro vídeo, zenDbXgFEEw): "aqui, ó, 50% 65 tá pré-direcional e acima de 70% direcional" e "acima de 80%, 85, cara, não tem nem o que pensar" — CONFIRMADO, com **IMPRECISO**: os dois vídeos dão limiares ligeiramente diferentes (75% vs. 70%) para "direcional" — provavelmente o autor não usa um número fixo único, e sim uma faixa de convicção crescente.
- **Confiança recomendada como calibrável** (não fixa): "de 50% fico 70, 80% convicto" (SHjx2aHkmVA) — reforça que a convicção escala com o %, sem corte binário único.

**Limiares numéricos consolidados (para código):**
| faixa | leitura |
|---|---|
| 50% | empate / lateral |
| 50–65% | pré-direcional |
| ≥70–75% | direcional (zona de operação a favor) |
| ≥80–85% | máxima convicção ("não tem o que pensar") |

**Regra de entrada por percentual (CONFIRMADO, zenDbXgFEEw):** "Temos aqui 70% de um movimento comprador com apenas 30%... a partir disso" o autor busca comprar puxadas até uma referência de preço (a linha azul, ver seção 3), não simplesmente "comprar ao bater 70%": "não significa que a partir do momento que ele bate os 70% que eu saio comprando em qualquer região" (zenDbXgFEEw) — CONFIRMADO: o percentual é filtro de viés, não gatilho de entrada isolado; a entrada depende da micro (seção 6) e da região de preço.

**"Regra dos 70%" como setup didático (CONFIRMADO, cyJVLkoZIvk/FmURmlN3boI):** "quando tem aquela regra dos 70%" e "trade dos 70%" é citado como um operacional específico de ensino para iniciantes: "eu desenvolvi um operacional que é muito específico para iniciantes... o trade dos 70%" (FmURmlN3boI). Definição de sustentação: "se ele se sustentar acima de 70% e quando voltar nas regiões" (FmURmlN3boI) — CONFIRMADO.
**IMPRECISO/ATENÇÃO:** o próprio autor relativiza esse setup: "de uns 20 dias para cá, sendo bem realista com vocês, esse tipo de trade..." (frase cortada na legenda) — sinal de que a eficácia do setup varia no tempo; não tratar como regra permanente.

---

## 2. Exaustão de movimento

**AUSENTE NA FONTE como conceito nomeado.** Não há nenhuma ocorrência do termo
"exaustão"/"exausto" nas transcrições lidas. O que existe de mais próximo é
"desaceleração" da micro, tratado na seção 6 (Macro vs Micro) como sinal de
possível reversão, não como um conceito formal com regras de identificação
próprias. Se a base de código atual do fluxo_pro já tem um `DetectorExaustao`
(visto em `mutar.py` do próprio repo, referenciando `queda_volume_minima` e
exigência de "que o preço TENHA progredido"), essa definição vem de código
interno do projeto, não dos vídeos — não confundir as duas fontes.

---

## 3. Linha Azul

**Definição operacional (CONFIRMADO) — é o nível de 50% de equilíbrio comprador/vendedor da abertura, não suporte/resistência clássico nem média móvel:**

- Citação-chave: "o que vai determinar aqui é o cruzamento da linha azul... esta linha azul é o cruzamento dos 50%" (SHjx2aHkmVA) — CONFIRMADO: a linha azul é literalmente o nível de preço onde o indicador percentual (seção 1) cruzou 50/50 (empate comprador-vendedor), medido a partir da abertura do mercado.
- Regra "abaixo vende, acima compra" (do título do vídeo, confirmada em conteúdo): o preço abaixo da linha azul favorece leitura vendedora e acima favorece leitura compradora — inferido dos trechos "quebrou a linha azul para cima" tratado como reforço de compra, e o preço não conseguindo romper e devolvendo é tratado como reforço de venda: "ele volta para trás, atravessa a linha azul, rompe" citado como o inverso — **INFERIDO** (o autor não verbaliza a frase-título de forma tão direta nos trechos lidos; a leitura decorre do conjunto de exemplos).
- Função declarada pelo autor: referência de contexto de risco, não sinal isolado: "a ideia da linha azul é precisamente dar-te essa referência... dar-te uma ideia de que o preço não funcionou" (SHjx2aHkmVA) — CONFIRMADO.
- Ancoragem temporal: plota a partir da abertura do mercado: "desde a abertura do mercado um contexto" (SHjx2aHkmVA); em outro vídeo o autor conta que mudou o comportamento dela para não gerar mais na abertura por confusão dos alunos: "agora a linha azul ela não plota mais na abertura do mercado... porque a galera ficava muito louca" (FmURmlN3boI) — CONFIRMADO, mas **IMPRECISO/ATUALIZAÇÃO**: há uma mudança de comportamento entre vídeos — a regra de "onde ela plota" não é estável ao longo do tempo/versões da ferramenta.
- Serve de referência de stop: "projeção de stop para cima da linha" / "stop extremamente seguro de 150 pontos" ao usar a linha azul como nível de invalidação (SHjx2aHkmVA) — CONFIRMADO.
- Não é a mesma coisa que suporte/resistência (seção 5): é tratada como um nível derivado do próprio indicador percentual, não de acumulação de toques de preço.

**Resumo para implementação:** `linha_azul = preço no instante em que o acumulado comprador/vendedor desde a abertura cruzou 50%`. Detalhe de janela/reset e se recalcula intraday: AUSENTE NA FONTE (não há fórmula explícita de "acumulado", apenas a afirmação de que é "o cruzamento dos 50%").

---

## 4. Defesa de preço / escora / renovação de oferta

**IMPRECISO / fraco na fonte lida.** Só uma ocorrência direta de "defender":
"os vendedores já estão... defendendo a região" (cyJVLkoZIvk) — CONFIRMADO como
conceito qualitativo: um "player" trabalha uma região de preço com ordens
repetidas em vez de golpear o preço de uma vez, para não expor todo o volume:
"é muito mais interessante para você que... ao invés de... bater com muita
força esse preço, ele vai preferir trabalhar a posição dele dentro dessa
região" (cyJVLkoZIvk) — CONFIRMADO. É chamada de "região do Smart Money".

Não há, nos vídeos lidos, definição operacional de "renovação de oferta"
(reposição de ordem no book) com contagem mínima de eventos ou limiar
numérico — isso existe no código do repo (`n_reposicoes_minimo`,
`DetectorEscora`, visto em `mutar.py`), que é definição de ENGENHARIA interna
do projeto, não extraída destes vídeos. Marcar como **AUSENTE NA FONTE** a
fórmula de escora nos vídeos e usar a implementação já existente no código
como referência técnica separada.

---

## 5. Suporte vs Resistência ("Sinal Ultra")

**Definição operacional (CONFIRMADO):** é um "estágio elevado" (mais forte) do
conceito clássico de suporte/resistência, sinalizado por um alerta visual
específico ("força ultra... este raio... uma setinha piscando"):
"Ele é um estágio elevado do nível de suporte e de resistência" (TPk39osWiKY).

- Gatilho de disparo: aparece "em cenários específicos de mercado" — não é
  constante — "não é assim uma sinalização que... é constante" (TPk39osWiKY) — CONFIRMADO, mas vago (não há regra numérica de quando dispara).
- Efeito dual declarado: "ou ele vai melhorar uma operação já em aberto ou ele
  vem para atrapalhar o contexto" (TPk39osWiKY) — CONFIRMADO: o sinal por si só
  não diz a direção do resultado, exige contexto (a micro do movimento).
- Regra de invalidação/uso citada no vídeo "Suporte vs Resistência: Quando
  Funciona e Quando Engana" (W7lNHhliZXU): confluência com micro/macro
  positivos aumenta a chance de funcionar: "temos um cenário aonde a micro e a
  macro é positiva, nós temos uma melhor confluência" (W7lNHhliZXU) — CONFIRMADO como regra qualitativa de confluência, sem limiar numérico.

**Nível de confiança:** CONFIRMADO como conceito, mas **NÃO IMPLEMENTÁVEL sem
julgamento extra** — não há regra de preço/tempo/volume que defina
objetivamente quando o "sinal ultra" aparece; é uma saída direta da
ferramenta proprietária (caixa-preta), não uma regra derivável do texto.

---

## 6. Macro vs Micro

**Definição operacional (CONFIRMADO, citação mais direta em EPqye9iLNig):**
- "isto daqui é a macro, ou seja, todo o movimento do dia" (EPqye9iLNig) — CONFIRMADO: macro = contexto direcional do dia inteiro.
- "Micro é o movimento presente, ou seja... o curto movimento, ele é o que está [acontecendo agora]" (EPqye9iLNig) — CONFIRMADO: micro = movimento imediato/atual.
- Resumo direto do autor: "Micro é sempre agora, macro [é] o contexto de forma mais ampla" (EPqye9iLNig) — CONFIRMADO.
- Hierarquia de decisão: a micro comanda o preço no curtíssimo prazo, mas pode contrariar a macro temporariamente: "a micro é quem manda no agora, no movimento do momento" (xhpnmyQohPg) — CONFIRMADO.
- Regra de não confundir escala: "não confunda 10%, achando que a micro só ficou 10% positiva... é uma outra história" (xhpnmyQohPg) — CONFIRMADO: sinaliza que macro e micro são medidas em escalas diferentes e não devem ser comparadas diretamente pelo mesmo número percentual.
- Janela de tempo exata de cada uma: **AUSENTE NA FONTE.** O autor nunca define
  "micro = últimos N minutos" ou "macro = do open até agora" com um número de
  minutos/candles. A única baliza temporal explícita é que a macro cobre
  "todo o movimento do dia" (ou seja, desde a abertura) — o que dá uma âncora
  para a macro (dia inteiro / desde abertura), mas não para a micro.

**Confluência (CONFIRMADO):** operar micro a favor da macro é preferido;
contra-tendência é tratado como operação de maior risco: "de contratendência, você não pode ser [leviano/deixar solto]" (6UPPrXrYeOY, frase cortada) — CONFIRMADO como recomendação qualitativa, sem regra numérica de quando é permitido.

---

## 7. Horários

**Fraco/disperso na fonte.** Não há uma tabela de horários explícita nos
trechos lidos. Elementos encontrados:
- A linha azul se ancora "desde a abertura do mercado" (SHjx2aHkmVA) — CONFIRMADO.
- Um horário específico citado como referência de exemplo em aula (não regra geral): "o horário 9:54" (6UPPrXrYeOY) — é apenas timestamp do exemplo, não regra.
- Menção qualitativa a horário desfavorável: "o horário já tava é um horário já não muito agradável... é um horário já do final do dia" (SHjx2aHkmVA) — CONFIRMADO como noção qualitativa (final do dia = pior), mas sem hora exata definida no trecho lido.
- Referência de horário associado a fechamento de posição por proximidade do fim de sessão: "próximo horário de..." (frase cortada, SHjx2aHkmVA).

**Conclusão:** regra de horário de abertura/fechamento com números exatos —
**AUSENTE NA FONTE** nos vídeos lidos. Existe apenas a heurística qualitativa
"operar perto do fim do pregão é pior" e "a linha azul referencia a abertura".

---

## 8. Gestão de tamanho de posição ("mão cheia" vs "mão mínima")

**Definição operacional (CONFIRMADO, 6UPPrXrYeOY):**
- Região "boa"/de alta convicção → tamanho máximo: "quando eu vejo que tá muito bom a região, falar: 'Cara, essa aqui eu vou entrar com a mão cheia'" — CONFIRMADO.
- Região "turbulenta"/incerta → reduzir tamanho: "quando eu vejo que a região é turbulenta... eu vou entrar menos pesado... entro com cinco" (ao invés de 20) — CONFIRMADO.
- Alternativa: entrar com metade do lote e sair de parte rápido para "puxar o médio para baixo": "eu entro com a metade do lote, mas... penso em proteger um pouco mais rápido para jogar o médio para baixo e tento subir aí com... 30% do lote" — CONFIRMADO.
- Critério de decisão do tamanho é **qualitativo** ("região boa" vs "turbulenta"), não numérico (não há definição de volatilidade/spread/percentual que dispare a redução). Números de contratos citados (20, 10, 5) são exemplos pessoais do autor, não uma tabela de regra fixa.

**Nível de confiança:** CONFIRMADO como padrão comportamental, mas
**NÃO IMPLEMENTÁVEL diretamente** — a classificação "região boa vs turbulenta"
depende de julgamento visual/contextual do operador (combinação de %, linha
azul, sinal ultra, macro/micro). Aproximação sugerida: usar como proxy de
"turbulência" um limiar calibrável sobre volatilidade recente (ex.: ATR ou
desvio-padrão dos últimos N candles) ou sobre a proximidade de níveis-chave
(linha azul, suporte/resistência) — parâmetro a calibrar, não extraído do
texto.

---

## 9. Limite de perdas / número máximo de stops no dia

**Definição operacional (CONFIRMADO, 6UPPrXrYeOY) — regra de "não mais que 3
stops seguidos na mesma região":**
- "às vezes eu tomo três stops seguidos na região... eu tenho uma regra que eu não passo de três. Então, se eu tomei três é porque a região tá muito confusa" — CONFIRMADO.
- É uma regra **por região/setup**, não necessariamente um limite geral diário de perdas em R$/pontos: o autor não menciona explicitamente "encerro o dia após X reais de prejuízo" nos trechos lidos.
- Reforço da atitude após atingir o limite: parar de insistir na região ("não adianta ficar dando murro em ponta de faca") — CONFIRMADO como regra comportamental, não numérica adicional.
- Uso do botão "zerar" como ferramenta de saída de emergência, mas condicionado a sinal contrário aparecer, não como rotina fixa: "somente se... esse cara aqui ficar verde" (6UPPrXrYeOY) — CONFIRMADO.

**Nível de confiança:** CONFIRMADO — este é o achado numérico mais sólido desta
lacuna prioritária: **máximo de 3 stops seguidos na mesma região/setup antes
de abandonar aquela região no dia.** Não há evidência de um número máximo de
stops absoluto para o dia inteiro (todas as regiões somadas) nos vídeos lidos — **AUSENTE NA FONTE** para essa versão mais ampla da regra.

---

## 10. Alvo / take profit

**Fraco/qualitativo na fonte.** Não há fórmula de projeção matemática de alvo
(ex.: múltiplo de risco, projeção de Fibonacci, etc.) nos trechos lidos.
Elementos encontrados:
- Uso de "alvo 1" / "alvo 2" como zonas discretas de saída parcial: "tá na região do alvo um, alvo dois. É uma extremidade agradável" (SHjx2aHkmVA) — CONFIRMADO como conceito (existe uma sequência de alvos), mas sem a regra de cálculo de onde ficam esses níveis.
- Alvo associado a onde "players" têm posições a fechar/repor: "onde os compradores estão com alvos de projeção. Para quê? para pagamento de..." (frase cortada, SHjx2aHkmVA) — **IMPRECISO** (frase incompleta na legenda, sentido cortado).
- Ideia de parcial ligada à decisão de "pagar uma parcial" perto do stop/risco: "ele pagar uma parcial ou se o cara quer..." (6UPPrXrYeOY, frase cortada) — **IMPRECISO** (contexto insuficiente para regra).
- Uso de tamanho de posição para viabilizar alvo distante com stop caro controlado: "entro com a mão mínima... tento carregar para fazer um alvo... se der o stop não fica caro porque eu tô entrando leve" (6UPPrXrYeOY) — CONFIRMADO: há relação entre tamanho reduzido e aceitação de alvo mais distante/stop mais largo, mas sem fórmula de razão risco/retorno explícita.

**Conclusão:** o conceito de "alvo 1 / alvo 2" existe e é usado para parciais,
mas a REGRA DE CÁLCULO de onde ficam esses alvos (medida de projeção, %
específico, distância em pontos) está **AUSENTE NA FONTE** nos vídeos lidos.

---

## IMPLEMENTÁVEL vs NÃO IMPLEMENTÁVEL

### Implementável (definição precisa o bastante para virar código)

1. **Indicador percentual comprador/vendedor com faixas de convicção** —
   50% = lateral, 50–65% pré-direcional, ≥70–75% direcional, ≥80–85% máxima
   convicção. Implementável desde que o projeto já produza (ou aproxime) esse
   percentual comprador/vendedor a partir do book/agressão — a fonte não
   ensina a FÓRMULA do %, só os limiares de leitura sobre um % já calculado.
2. **Linha azul como nível de cruzamento de 50%** — se o percentual acima for
   calculável em série temporal desde a abertura, a linha azul é o preço no
   instante do cruzamento de 50/50. Implementável com uma ressalva: o
   comportamento de "não plotar mais na abertura" mudou entre versões da
   ferramenta do autor — decidir e documentar explicitamente a regra de janela
   usada na implementação própria (parâmetro calibrável).
3. **Regra dos 3 stops seguidos por região** — limite direto: bloquear novas
   entradas na mesma região/setup após 3 perdas seguidas nela, liberando outras
   regiões. Facilmente implementável como contador por "zona de preço" ou por
   "setup ativo".
4. **Gestão de tamanho por dois níveis (mão cheia / mão mínima)** — o
   *mecanismo* (dois ou três tamanhos de posição, redução em cenário de
   incerteza) é implementável; o *gatilho* que decide qual tamanho usar não é
   (ver não implementável, item 2).
5. **Macro = contexto do dia inteiro (desde abertura); Micro = movimento
   recente/atual** — implementável como duas séries (ex.: acumulado do dia vs.
   janela móvel curta), mas o tamanho exato da janela da micro precisa ser
   calibrado (não está na fonte).

### Não implementável diretamente (depende de julgamento visual/contextual — como aproximar)

1. **Exaustão de movimento** — conceito ausente na fonte como regra. Se o
   projeto já tem `DetectorExaustao` (código, não vídeo), documentar a origem
   separada; não tratar como regra do método original do autor.
2. **Gatilho de troca mão cheia ↔ mão mínima ("região boa" vs "turbulenta")**
   — depende de leitura visual combinada de %, linha azul e contexto. Aproximar
   com parâmetro calibrável de volatilidade recente (ex.: ATR/desvio-padrão em
   N candles) ou distância a níveis-chave, testado e ajustado empiricamente
   com dados históricos, não copiado do texto.
3. **Sinal Ultra (suporte/resistência reforçado)** — saída de caixa-preta da
   ferramenta do autor; sem fórmula de disparo no texto. Aproximar com
   contagem de toques em zona de preço + reforço se coincidir com %
   direcional ≥ 75%, como proxy calibrável — não é a regra original, é uma
   aproximação declarada.
4. **Defesa de preço / escora / renovação de oferta** — qualitativo nos
   vídeos; a fórmula quantitativa (nº mínimo de reposições no book) só existe
   no código interno do projeto (`n_reposicoes_minimo`), não nos vídeos.
   Manter as duas fontes separadas na documentação.
5. **Horário ótimo/ruim de operar** — só há a heurística "fim de pregão é
   pior" e "linha azul ancora na abertura". Aproximar com um parâmetro
   calibrável de "janela de horário permitida" definido empiricamente (ex.:
   configuração de horário de início/fim de operação), não extraído do texto.
6. **Alvo / projeção de take profit** — existe o conceito de alvo 1/alvo 2,
   mas não a fórmula de cálculo. Aproximar com parâmetro calibrável de
   múltiplo de risco (ex.: 1R, 2R) ou de projeção de faixa de preço
   (ex.: medida de amplitude do movimento anterior), documentado como
   aproximação e não como regra do autor.
