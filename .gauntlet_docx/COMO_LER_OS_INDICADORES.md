# Como ler os indicadores do NEXO

Escrito para operador. Cada seção diz **o que o número mede**, **de onde ele
sai** e **como interpretar**. Onde é proxy, está escrito que é proxy.

Regra que vale para o quadro inteiro: **nada aqui é recomendação de entrada e
nada envia ordem.** É leitura de fluxo, consultiva.

Rótulo de origem usado abaixo:

- **CONFIRMADO** — a regra vem de fonte do projeto (`pesquisa/*.md`, `bar/*.txt`).
- **IMPRECISO** — proxy honesto, construído por este projeto, sem fórmula de fonte.
- **AUSENTE NA FONTE** — a fonte não define isso; o painel declara em vez de fingir.

---

## 1. As quatro leituras derivadas

São os quatro ladrilhos na base esquerda. Cada um mostra uma **força de −100% a
+100%** (positivo = comprador, negativo = vendedor), um **rótulo de confiança**
(ALTA / MEDIA / BAIXA / SEM CONF) e, embaixo, o **valor de onde a força saiu** —
o número cru da métrica (`+534` contratos, `PARADO`) ou, quando a leitura é
suavizada, o próprio valor suavizado marcado com `MM5`. Esse texto pequeno
sempre carrega o mesmo sinal do número grande logo acima dele (seção 7).

### HORIZONTE — o dia inteiro
- **Mede:** o delta acumulado de agressão **desde a abertura**. É a maré.
- **Como sai:** valor cru (ex.: `+534` contratos) dividido por uma referência de
  magnitude do dia. **IMPRECISO** — a referência (8000 contratos) é escala de
  engenharia deste projeto; a fonte não publica uma. Se na prática o HORIZONTE
  vive saturado em ±100%, essa referência está baixa demais e deve ser ajustada.
- **Interpretar:** lento por natureza. Não vira em um negócio. Serve para dizer
  se o que você está vendo agora rema a favor ou contra o dia.

### PULSO — os últimos 15 segundos
- **Mede:** o mesmo delta de agressão, mas na janela micro (15 s).
- **Como sai:** igual ao HORIZONTE, com referência própria (80 contratos).
  **IMPRECISO** pelo mesmo motivo, e por isso **as duas escalas não se comparam
  entre si** — PULSO +100% não é "tão forte quanto" HORIZONTE +100%.
- **Interpretar:** é o curto prazo. Rápido, ruidoso, e o primeiro a virar.
  PULSO contra HORIZONTE é repique dentro da maré; PULSO a favor é continuação.

### PRESENÇA — o MakerProxy
- **Mede:** comportamento do livro: absorção, reposição, divergência, clips e
  agressão, agregados num único score.
- **Como sai:** `MakerProxy.pontuacao`, já **suavizado por média móvel de 5
  amostras** antes de chegar à tela. **IMPRECISO** — é proxy de comportamento de
  quem está no livro. **AUSENTE NA FONTE: identidade de contraparte.** A B3 não
  publica quem é quem no tape público; o painel nunca diz "o player X está
  comprando", porque não tem como saber.
- **Custo da suavização:** ~5 amostras de atraso. Sem ela o número girava de
  −100% a +100% em um único negócio. Uma virada real aparece em poucos quadros,
  não fica escondida.
- **O sufixo `MM5`** no texto pequeno avisa que aquele número é a média móvel de
  5 amostras, não o score cru do instante. Quando a média já virou e o score cru
  ainda não (ou o contrário), **o painel inteiro mostra a média** — número, cor,
  rótulo COMPRA/VENDA e barra do rodapé, todos ao mesmo tempo. Até 28/08 a média
  ia só para o número grande e o cru continuava mandando na cor e no rótulo: o
  mesmo MakerProxy aparecia em quatro lugares do quadro com dois sinais
  diferentes (ex.: "+73%" escrito em vermelho, rotulado VENDA, com "−33%"
  impresso logo abaixo). Ver seção 7.
- **Interpretar:** é a leitura de **quem está segurando o preço**, não de para
  onde o preço foi. Livro absorvendo compra com preço caindo é normal — e é
  justamente o caso em que PRESENÇA e RITMO discordam.

### RITMO — o velocímetro
- **Mede:** dois eixos ao mesmo tempo: **grandeza** (quanto o mercado andou na
  janela, relativo ao próprio dia) e **manutenção** (se está ACELERANDO,
  MANTENDO, DESACELERANDO, VIROU ou PARADO).
- **Como sai:** `magnitude_relativa × fator de manutenção × direção`.
  **CONFIRMADO** quanto aos dois eixos (`fluxopro/metodologia/velocimetro.py`).
  **IMPRECISO** quanto ao fator (ACELERANDO 1,00 · MANTENDO 0,85 ·
  DESACELERANDO 0,45 · VIROU 0,30 · PARADO 0,00).
- **Por que mudou (27/08):** antes o ladrilho mostrava **+100% com "DESACELERANDO"
  escrito ao lado** — o número usava só a grandeza e ignorava a manutenção. Um
  empurrão grande que já estava morrendo aparecia como convicção máxima.
- **Interpretar:** o número grande é "quanto de ritmo existe **agora**"; o rótulo
  ao lado continua mostrando o eixo de manutenção separado, para quem quiser os
  dois. PARADO = 0%, mesmo com movimento grande, porque abaixo do gate de
  magnitude a leitura não é confiável.

---

## 2. EQUILÍBRIO — o termômetro grande (topo esquerdo)

- **Mede:** o score do MakerProxy suavizado — **o mesmo número que o ladrilho
  PRESENÇA**, em formato de mostrador. "Mesmo número" aqui é literal e
  verificável: os dois leem a mesma leitura, com o mesmo sinal, a mesma cor e o
  mesmo rótulo. Se algum dia os dois divergirem na tela, é defeito, não leitura
  — e há teste automatizado prendendo isso (seção 7).
- **Interpretar:** é o **livro agora**, e só isso. Ele **não** é resumo do quadro
  e **não** é média das quatro leituras. Se ele marca −100% VENDA enquanto o
  placar abaixo marca saldo levemente comprador, não há erro: são fontes
  diferentes (livro instantâneo × quatro leituras, uma delas desde a abertura).

---

## 3. PLACAR ESTATÍSTICO — as duas caixas COMPRA / VENDA

Este é o bloco que o operador apontou como "mudanças abruptas demais". A causa
era de fórmula, e foi corrigida.

- **O que era (até 27/08):** as duas caixas nasciam de **um único score
  assinado**. Um dos dois lados era **sempre exatamente 0%**, e ao cruzar o zero
  os dois números trocavam de lugar de uma vez. Não era o mercado virando de
  uma vez — era a conta.
- **O que é agora:** cada lado soma **as suas próprias leituras**, ponderadas
  pela confiança de cada uma:

```
compra = Σ(peso · parte compradora da força) / Σ(peso)
venda  = Σ(peso · parte vendedora da força) / Σ(peso)

peso: ALTA 1,0 · MEDIA 0,6 · BAIXA 0,3 · SEM CONF 0,0
```

- **Origem:** as forças e confianças são as mesmas já congeladas no snapshot
  (CONFIRMADO). Os pesos por confiança são **IMPRECISOS** — engenharia deste
  projeto.
- **Três coisas que você pode conferir na tela:**
  1. **Discordância aparece.** Com HORIZONTE comprador e PRESENÇA vendedora, os
     **dois** números ficam positivos ao mesmo tempo. Antes o painel era obrigado
     a zerar um deles. Quando os dois passam de 15%, o título carimba
     **LEITURAS DIVERGENTES**.
  2. **Nada salta.** Passo pequeno na força → passo pequeno no número. Não há
     mais degrau no cruzamento do zero. E **não há atraso**: a continuidade vem
     de a fórmula ser contínua, não de média móvel. Virada real aparece no mesmo
     quadro.
  3. **`SALDO` no canto direito do título é, ao centavo, `compra − venda`.** É a
     ponte explícita entre as duas caixas e o score único que o resto do quadro
     usa. Não é um terceiro número de outra fonte.
- **`compra + venda` pode dar menos que 100%.** O que falta é leitura **sem
  convicção** (força perto de zero, ou confiança baixa). O painel **não**
  renormaliza para 100% de propósito: isso fabricaria convicção que ninguém mediu.
- **A legenda `N DE 4 LEITURAS` continua embaixo** e é o denominador honesto:
  quantas leituras *apontam* para aquele lado, independentemente de quanta força
  elas têm. É normal ver "3 DE 4 LEITURAS" com apenas 7% — três leituras
  comprando fraquinho valem pouco.

---

## 4. FORÇA OBSERVADA — a tira de raios

- **Mede:** a força por negócio da própria série do quadro, uma marca por
  amostra, últimas 24.
- **Como sai:** média móvel **causal** de 5 amostras (só olha para trás) sobre os
  valores reais da série. Sem suavização a tira alternava de sinal a cada negócio
  e não dava para ler tendência nenhuma.
- **Interpretar:** verde para cima = agressão compradora; vermelho para baixo =
  vendedora. Serve para ver **sequência**, não nível. Sem amostra o bloco declara
  `SEM HISTÓRICO DE FORÇA` em vez de desenhar barra inventada.

---

## 5. PRESSÃO — o par 56 / 44 (canto inferior direito)

- **Mede:** propensão do fluxo do livro para positivo ou negativo, na escala
  0–100 (as duas metades sempre somam 100 — é um trilho só, dividido no ponto
  real do corte).
- **Como sai:** `pressão = 0,70 × PRESENÇA (MakerProxy) + 0,30 × RITMO`,
  reescalado de [−1, +1] para [0, 100]. **IMPRECISO** — os pesos são de
  engenharia deste projeto.
- **O que era antes:** literalmente `50 + MakerProxy × 50`. Era **o mesmo número**
  do EQUILÍBRIO e do PRESENÇA, em três lugares, fingindo ser três leituras.
  Agora ele carrega uma segunda fonte (RITMO) e por isso pode divergir do gauge —
  ex.: livro absorvendo compra mas preço já perdendo ritmo.
- **AUSENTE NA FONTE:** "qual player está mandando no mercado". Não existe
  identidade de contraparte no tape público da B3. Este par é composição de duas
  leituras de comportamento, não identificação de participante — e o rodapé
  imprime a composição (`MAKER 70% + RITMO 30% · PROXY`) para que isso nunca
  passe por outra coisa.
- **O rótulo de coerência no rodapé** é a reconciliação que faltava:
  - `CONFIRMA O PLACAR` — pressão e saldo do placar apontam para o mesmo lado.
  - `DIVERGE DO PLACAR` — apontam para lados opostos, os dois com magnitude
    relevante (>10%). **Isso é informação, não defeito:** o livro está fazendo
    uma coisa e as leituras derivadas outra. Momento de cautela, não de entrada.
  - `NEUTRO VS PLACAR` — pelo menos um dos dois está perto de zero; sinal oposto
    aí é ruído, e o painel não trata como discordância.

---

## 6. Como ler o conjunto, em uma frase por caso

| O que você vê | Leitura |
|---|---|
| EQUILÍBRIO, PLACAR e PRESSÃO no mesmo lado, RITMO ACELERANDO | Fluxo alinhado; a leitura mais limpa que o painel produz. |
| EQUILÍBRIO forte em um lado, PLACAR com saldo pequeno | O livro está decidido, o dia não. Movimento de curto prazo dentro de uma maré contrária. |
| Título com `LEITURAS DIVERGENTES` | As quatro leituras se puxam. Saldo pequeno aqui **não** é calmaria — é briga. |
| Rodapé com `DIVERGE DO PLACAR` | Livro contra leituras derivadas. Verifique PRESENÇA × HORIZONTE antes de qualquer coisa. |
| RITMO em 0% com PULSO grande | Movimento sem manutenção: empurrão pontual, gate de magnitude não validou. |
| `REGIME COMPRADOR` com saldo do PLACAR negativo | Estrutura do dia intacta, fluxo do momento contra: correção dentro de tendência. Discordância esperada — ver seção 8. |
| `EVID.` baixo com PRESENÇA em ±100% | Convicção alta sobre amostra minúscula. Desconfie. |
| Qualquer bloco dizendo `INDISPONÍVEL` / `SEM ...` | Falta dado. O painel prefere declarar a inventar número. |

---

## 7. A regra que vale para TODO indicador: um número, um sinal

Toda leitura deste painel publica o mesmo valor por quatro portas diferentes:

| Porta | Quem lê |
|---|---|
| o número grande | o ladrilho da base |
| a cor (verde/vermelho) | todas as regiões |
| o rótulo COMPRA / VENDA | mostrador e legendas |
| o texto pequeno e a barra do rodapé | lista de contexto e par de pressão |

**As quatro têm de mostrar o mesmo sinal, sempre.** Esse é o contrato, e ele é
verificado por teste, não por olho — porque o defeito de "percentual alto ao
lado do rótulo oposto" já apareceu duas vezes neste painel:

1. no **RITMO** (+100% com "DESACELERANDO" ao lado), porque grandeza e
   manutenção eram eixos diferentes somados num número só;
2. na **PRESENÇA** (+73% em vermelho, rotulado VENDA, com −33% impresso
   embaixo), porque a suavização trocava só a grandeza e deixava o sinal no
   score cru;
3. no **REGIME** (a palavra COMPRADOR/VENDEDOR em ciano fixo), porque quem
   desenhava o cartão escolhia a cor por conta própria em vez de consumir a
   direção da leitura.

Ficou claro que a causa era **estrutural**, não local: sinal e grandeza viajavam
separados e cada consumidor recombinava por conta própria — por isso o conserto
de um indicador fazia o defeito reaparecer no vizinho. Agora qualquer recálculo
de força passa por um único ponto que devolve a leitura inteira coerente
(número, sinal, cor, rótulo e texto juntos), a leitura do REGIME atravessa
pronta até quem a desenha, e um teste varre **todas** as leituras da matriz
exigindo que força e direção apontem para o mesmo lado — a varredura existe
justamente para a família não renascer numa quarta porta. Se você vir na
tela um número de um lado e um rótulo do outro, **isso é bug, e vale reportar**;
não é uma leitura sutil que você precise interpretar.

**Como o painel garante isso, na prática.** Toda leitura direcional passa por um
portão único antes de ser desenhada. Quando número e rótulo discordam, a regra é
**o rótulo e a cor seguem o número** — porque o número é o que você lê. A leitura
não é apagada da tela: seria caro demais perder um HORIZONTE válido porque um
campo secundário veio torto. A exceção é o REGIME, onde a medida é a própria
palavra (vinda da estrutura de preço) e o número é que deriva dela; ali uma
incoerência indica dado corrompido, e o cartão degrada honestamente para `—`.

Um detalhe pequeno da mesma regra: **zero não tem lado.** Uma leitura em zero
imprime `+0%` e cor **neutra** — nunca `-0%`, e nunca verde ou vermelho. Era o
caso do RITMO em PARADO: o velocímetro ainda tinha um sentido registrado, e o
ladrilho saía verde com "+0%" escrito. Magnitude zero não autoriza pintar lado.

**Essa guarda era local até 28/08, e por isso a família sobreviveu.** O conserto
tinha sido feito só dentro do RITMO. O MakerProxy continuava passando o zero
negativo adiante, e no retrato de fechamento ele saiu por três portas ao mesmo
tempo — `-0%` no mostrador EQUILÍBRIO, `-0%` no ladrilho PRESENÇA e `-0% MM5` no
texto pequeno — todas as três já pintadas de neutro, só com o sinal errado.
Agora a normalização está no **mesmo portão único** que re-deriva direção, cor e
rótulo, e o corte usado é o mesmo de `_direcao_de_score`: só perde o sinal aquilo
que a direção já declarou NEUTRO. Uma leitura de −0,4% continua saindo negativa.

---

## 8. O visor central: REGIME, CONFIANÇA e EVID.

São as três células abaixo do visor grande. Elas **não** são resumo do resto do
quadro — cada uma tem fonte própria, e é por isso que podem discordar do placar
sem que nenhuma esteja errada.

### REGIME — COMPRADOR / VENDEDOR / INDEFINIDO
- **Mede:** a estrutura do dia. O mercado só é declarado vendedor quando
  **perde a mínima do dia** (ou a região de abertura); enquanto o preço se
  segura acima da abertura e perto da máxima, venda é ondulação, "por maior que
  seja a barrigada".
- **Origem: CONFIRMADO** — é a única leitura do quadro com regra de fonte
  explícita (`fluxopro/metodologia/estrutura.py`, `ferramenta_componentes.md`
  §8 e §6.2). Não usa livro, não usa identidade de corretora, não usa fluxo:
  **só preço**.
- **Por que ele pode discordar do PLACAR, legitimamente:** o REGIME é a
  estrutura do **dia inteiro** e muda apenas na quebra de um extremo; o PLACAR é
  a convicção **agora** de quatro leituras de fluxo, e se mexe negócio a
  negócio. `REGIME COMPRADOR` com `SALDO −32%` significa, literalmente: *a
  estrutura do dia ainda não foi rompida para baixo, mas o fluxo neste momento
  está vendedor.* Isso é o caso clássico de correção dentro de tendência — é
  informação útil, não contradição. O inverso (REGIME virando enquanto o placar
  já estava do outro lado há tempo) é o REGIME confirmando, com atraso e mais
  evidência, o que o fluxo antecipou.
- **Custo do método:** o REGIME é deliberadamente lento. Ele foi feito para
  **não** virar por candle isolado. Não espere que ele acompanhe o PLACAR.
- **Cor:** desde 28/08 a palavra é pintada no mesmo eixo direcional do resto do
  quadro — verde para COMPRADOR, vermelho para VENDEDOR. Até então era ciano
  fixo: a palavra direcional mais destacada da tela era a única sem o eixo de
  cor, e o mesmo ciano significava também "regime vendedor". Ver seção 7.

### CONFIANÇA
- **Mede:** a confiança da **decisão consultiva** exibida no visor logo acima
  (ALTA / MEDIA / BAIXA), não a confiança do REGIME nem a do placar.
- **Como sai:** classificação por faixa do score de confiança da leitura.
  **IMPRECISO** quanto aos cortes de faixa. Um traço (`—`) significa que ainda
  não há confiança apurada — normal enquanto o visor está em AGUARDAR.
- **Interpretar:** é o qualificador da frase do visor. Frase forte com
  confiança BAIXA vale menos que a frase sugere.

### EVID.
- **Mede:** **quantas evidências** o MakerProxy tem retidas na trilha do
  momento — quantos eventos observados sustentam a leitura atual, não um volume
  de contratos e não um placar de acertos.
- **Como sai:** contagem dos itens retidos na trilha (limitada a 64 por quadro;
  quando a contagem bate no teto, o painel mostra `retidos/total` na trilha).
- **Interpretar:** é o "tamanho da amostra" do que o MakerProxy está afirmando.
  `EVID. 3` com PRESENÇA em ±100% é convicção alta sobre pouquíssima evidência —
  exatamente o tipo de leitura para desconfiar. Número alto não valida a
  direção; só diz que não é um evento isolado.

---

## 9. Os níveis marcados nos gráficos — `A1/A2/A3` e `STOP`

Duas regiões desenham níveis de preço com nome próprio, e é importante saber
exatamente o que eles são — porque a seção 10 promete que o painel não recomenda
entrada, e esses rótulos são o ponto onde essa promessa mais se confunde.

### No gráfico de candles: `STOP`, `A1`, `A2`, `A3`
- **O que são:** os níveis que a **decisão consultiva** publicou no momento em
  que ela existiu. Aparecem **só quando há decisão** — sem decisão, nenhuma
  linha é desenhada. São **etiquetas de leitura**: não há botão, ordem ou clique
  associado a elas, e o painel não envia nada.
- **Origem: CONFIRMADO** quanto ao fato de virem da decisão
  (`fluxopro/ui/paineis/nexo/candles.py`), **IMPRECISO** quanto aos números —
  são a leitura daquela decisão, não uma recomendação de preço de entrada nem de
  onde colocar risco. O painel os imprime para você poder **conferir a decisão
  contra o gráfico**, não para segui-los.

### No Renko: `A1+ ALVO DO COMPRADOR` e `A1- ALVO DO VENDEDOR`
- **O que são:** as faixas onde cada lado costuma **realizar**. `A1` é a mais
  próxima (onde a zona começa), `A2` e `A3` as seguintes. Só o `A1` de cada lado
  recebe o nome por extenso, para não repetir a mesma placa três vezes.
- **Origem: CONFIRMADO** (`ijsZl8EzeH8.txt`).
- **A leitura de disciplina que a fonte carrega**, escrita aqui e não na tela:
  comprar **dentro** do alvo do comprador é comprar no preço onde o comprador que
  já estava posicionado está saindo — historicamente o pior preço do movimento
  para entrar a favor. O mesmo vale espelhado para o alvo do vendedor. **Isso é
  contexto sobre a zona, não instrução:** o painel não sabe o que você está
  fazendo, não sabe seu risco e não decide seu momento.
- **Por que mudou (28/08):** as duas placas diziam `EVITAR COMPRAS` e
  `EVITAR VENDAS`. A frase é imperativa e se lê como ordem de entrada, a dois
  palmos de um rodapé que carimba `NÃO É ORDEM · NÃO É RECOMENDAÇÃO`. O nome da
  zona diz a mesma coisa sem mandar em ninguém, e usa o mesmo vocabulário
  (`alvo`, `A1/A2/A3`) que a região do candle já usava para os mesmos níveis.

### A placa de ALERTA: `FLUXO COMPRADOR EXTREMO` / `FLUXO VENDEDOR EXTREMO`
- **Mede:** HORIZONTE saturado e sustentado num lado só. O subtítulo carrega o
  número (`SUPORTE MÁXIMO · HORIZONTE +88%` ou `RESISTÊNCIA MÁXIMA · …`).
- **A leitura de disciplina, de novo escrita aqui e não na tela:** fluxo extremo
  e sustentado é o pior lugar para ir contra. **Não é um sinal de entrada do
  outro lado, e não é hora de nada** — é o estado do dia, nomeado.
- **Por que mudou (28/08):** a placa dizia `CUIDADO COM COMPRAS AGORA` /
  `CUIDADO COM VENDAS AGORA` — imperativa, com `AGORA` dentro, ou seja, momento
  de operar, e na maior fonte daquela metade da tela. Era a mesma família do
  `EVITAR` do Renko, viva numa segunda região: a de rótulo que instrui num painel
  que promete não instruir.

---

## 10. O que este painel deliberadamente NÃO faz

- Não identifica participante ou corretora (dado inexistente na fonte pública).
- **Não recomenda entrada, saída, momento de operar nem tamanho de risco.** Ele
  marca níveis (seção 9) e diz de onde eles vieram; a decisão de operar,
  qualquer uma, é sua e acontece fora deste painel.
- Não envia ordem, em nenhuma circunstância, por nenhum caminho.
- Não normaliza número para "fechar 100%" quando a convicção medida não fecha.
- Não esconde discordância entre leituras: quando elas discordam, ele diz.
