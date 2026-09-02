# ACHADO ABERTO — o filtro ULTRA nunca pode acender

**Data:** 01/09/2026
**Status:** RENKO REMOVIDO DA REGRA DO ULTRA; testes e replay real
revalidados com três gates operacionais
**Origem:** o operador, em 01/09/2026: *"nenhum momento vi direcao do mercado
nem ultra aceso"*.

---

## O que foi medido

Sonda no caminho REAL do produto (`assistente.desenhar_resumo` e
`MotorDecisaoASG.avaliar`), replay das gravacoes de `dados/WDOU26`, layout
integrado (`FLUXOPRO_NEXO_AI=1`).

### 1. As 4 condicoes do ULTRA, em 5 pregoes

| pregao | quadros | maximo atingido | condicoes que acenderam |
|---|---|---|---|
| 25/08 | 1.599 | **1 de 4** | so MAKER (270) |
| 26/08 | 1.779 | **1 de 4** | so MAKER (223) |
| 27/08 | 1.708 | **1 de 4** | so MAKER (245) |
| 28/08 | 1.008 | **1 de 4** | so MAKER (255) |
| 31/08 | 3.276 | **1 de 4** | so MAKER (713) |
| **total** | **9.370** | **nunca 2 de 4** | `DECISAO` e `CONFIANCA`: **ZERO** |

Cinco pregoes distintos, nenhum chega a 2 de 4. `MAKER` acende em todos, o
que prova que a medicao funciona — o que nao acontece e a confirmacao.

### 2. Por que `RENKO` tambem fica em zero

`RENKO` **nao e independente**: `nucleo._condicoes_ultra` calcula

```python
renko_ok = (fase is FaseRenko.TENDENCIA
            and confirmada          # <- depende de DECISAO
            and direcao_renko is alvo)
```

Com `DECISAO` apagada, `RENKO` e falso POR CONSTRUCAO, mesmo com o Renko em
TENDENCIA na tela. Das 4 lampadas, 3 estavam apagadas por um portao so.

**Ja corrigido na apresentacao** (nao no motor): `_Condicao.bloqueada_por`
faz a tela distinguir `·REN` (nem foi avaliada) de `−REN` (avaliada e nao
atendida). Os dois layouts leem a mesma funcao pura, entao a distincao
aparece igual nas duas telas.

### 3. A decisao nunca confirma — e a evidencia ESTA la

Pregao de 31/08, 1.601 quadros:

| medida | valor |
|---|---|
| `direcao == AGUARDAR` | **1.601 / 1.601 (100%)** |
| `confianca == INDISPONIVEL` | **1.601 / 1.601 (100%)** |
| matriz com **6 de 6** linhas apontando lado | 1.248 (78%) |
| motivo "pre-sinal presente; confirmacao bloqueada" | 878 |

Em 78% dos quadros as SEIS linhas da matriz apontam lado, e mesmo assim a
decisao sai `AGUARDAR` com confianca `INDISPONIVEL` em 100% dos quadros.

### 4. Onde exatamente o portao fecha

`fluxopro/asg/decisao.py:213` — `confirmacao = pre_sinal and not bloqueios`.

Espiando `MotorDecisaoASG.avaliar`, 6.467 decisoes no pregao de 31/08:

| bloqueio | quadros | % |
|---|---|---|
| `QUALIDADE_FEED_BAIXA` | **6.467** | **100%** |
| `CONFIANCA_BAIXA` | **6.467** | **100%** |
| `MAKER_NAO_CONFIRMADO` | **6.467** | **100%** |
| `PRECO_FORA_DA_REGIAO` | 1.977 | 31% |
| `PERSISTENCIA_INSUFICIENTE` | 1.527 | 24% |
| `INVALIDACAO_ESTRUTURAL_INVALIDA` | 941 | 15% |
| `DIRECAO_INDISPONIVEL` | 815 | 13% |
| `EVIDENCIA_IRRELEVANTE` | 815 | 13% |
| `SEM_BOOK` / `FEED_NAO_SAUDAVEL` | 1 | ~0% |

- `pre_sinal = True` em **3.965 de 6.467 (61%)** — o pre-sinal existe.
- `confirmacao = True` em **0 de 6.467**.
- Nenhuma decisao, em nenhum quadro, saiu **sem bloqueio**.

**Tres bloqueios disparam em 100% das decisoes**: `QUALIDADE_FEED_BAIXA`,
`CONFIANCA_BAIXA` e `MAKER_NAO_CONFIRMADO`. Combinacao mais frequente
(3.374x): exatamente esses tres, sozinhos.

## Por que isto e defeito, e nao mercado parado

Um bloqueio que dispara em **6.467 de 6.467** decisoes, em **5 pregoes
diferentes**, nao esta descrevendo condicao de mercado — esta descrevendo um
portao que nao abre. `QUALIDADE_FEED_BAIXA` num replay de dado GRAVADO e
especialmente suspeito: nao ha feed degradado ali, o arquivo esta completo.

E o mesmo formato de dois defeitos ja confirmados neste projeto:

- `EstadoFeed.REPLAY` — membro de enum que nao existia, derrubava a
  dominancia em todo quadro de replay;
- a saude de S/R presa em `STALE` durante ~50 min por exigir 10 candles, com
  rotulo que dizia "ATRASADO" e mandava procurar problema de conexao.

Nos tres casos: um estado inalcancavel escondido atras de um rotulo
plausivel.

## Proximo passo sugerido

Medir, para cada um dos tres bloqueios de 100%, o valor observado contra o
limiar configurado — do mesmo jeito que se fez com a janela de amplitude do
Renko. A hipotese a testar primeiro e que os tres compartilham uma raiz
(a qualidade/confianca do maker), ja que `CONFIANCA_BAIXA` e
`MAKER_NAO_CONFIRMADO` andam sempre juntos com `QUALIDADE_FEED_BAIXA`.

## Histórico do diagnóstico antes da correção

O operador não estava presente na rodada de diagnóstico original. Por isso a
alteração foi adiada até que os portões fossem medidos e a correção pudesse
ser testada no caminho real. O diagnóstico permanece como evidência histórica;
o status atual e as correções estão registrados na seção seguinte.

## Atualização da correção — 01/09/2026

O operador autorizou a correção dos portões identificados. Foram fechadas
duas causas de código, sem transformar ausência de evidência em sinal:

1. **Qualidade do agressor no replay.** O contrato de replay começa sem uma
   declaração de qualidade, mas os `Trade` gravados carregam `BUY`/`SELL`.
   Depois do primeiro lado conhecido, o monitor agora promove `UNKNOWN` para
   `PARTIAL` — nunca para `NATIVE`. Lados desconhecidos posteriores continuam
   sendo contados em `unknown_aggressors`.
2. **Confiança do ULTRA.** O limiar próprio foi alinhado ao piso consultivo
   de `0,60`. O corte anterior de `0,75` era inalcançável para MBP/inferido,
   cujo teto de procedência é `0,6375` antes da cobertura dos componentes. O
   valor bruto de confiança agora acompanha a linha da matriz, e o motor e a
   UI usam exatamente o mesmo limiar configurado. O rótulo visual geral
   `ConfiancaASG.ALTA` não é mais usado como cópia paralela dessa regra.

O Renko foi auditado e não recebeu alteração nesta correção. Os testes de
destravamento inicial, destravamento após região travada, janela de amplitude
por tempo, retenção limitada e alvos permanecem aprovados.

### Limite honesto da validação real

Uma janela real de 3 minutos do replay de 31/08, após a correção, passou a
reportar `aggressor_quality=PARTIAL`, `book=MBP` e `feed_quality=0,675`. Ela
chegou a cobertura Maker máxima de `0,70` e confiança máxima de `0,455`, por
isso não confirmou decisão nem acendeu o ULTRA nessa janela. Isso é uma
condição de dados insuficientes, não um portão inalcançável: o teste sintético
com todos os requisitos continua ligando o ULTRA, enquanto o replay mantém a
proteção contra falso positivo.

### Revalidação em pregões inteiros — 01/09/2026

A frase acima não deve ser lida como validação de um pregão inteiro. O caminho
real foi reexecutado em três dias gravados, com feed, microestrutura, Maker e
decisão ativos; a cadência de auditoria foi reduzida para 1 segundo e os
analytics exclusivamente visuais ficaram desligados para tornar a varredura
multi-dia reproduzível.

| pregão | quadros | pré-sinais | confirmações | confiança Maker máx. |
|---|---:|---:|---:|---:|
| 25/08/2026 | 20.236 | 13.277 | 1 | 0,675 |
| 26/08/2026 | 19.658 | 9.912 | 196 | 0,675 |
| 31/08/2026 | 17.511 | 7.985 | 7 | 0,675 |

No pregão de 31/08, as sete confirmações passaram simultaneamente pelo Maker
(força absoluta de `51%` a `56%`, confiança `0,6075`, cobertura `0,90`), mas
o Renko estava em `PERDENDO_FORCA` em todas elas. Portanto, o ULTRA não ficou
apagado por `confiança Maker=0,392`; ficou sem a quarta condição de confluência
(`Renko=TENDENCIA`). No mesmo pregão o Renko atingiu `TENDENCIA` em 4.243
leituras de trade, mas nenhuma coincidiu com uma confirmação do motor.

### Correção de integração do quadro

Também foi encontrado e corrigido um defeito independente: a janela avaliava
o ULTRA antes de entregar os negócios do `Instantaneo` ao Renko e o painel
recebia o contexto bruto pela hidratação e novamente pela distribuição de
mercado. O caminho normal agora passa `alimentar_contexto=False` na hidratação
e avalia o ULTRA depois de `aplicar_mercado`; chamadas diretas antigas mantêm o
comportamento compatível. O teste dedicado verifica a ordem e garante que o
Renko já tem os negócios do quadro quando o filtro é avaliado.

Isso corrige a integração, mas não transforma automaticamente uma leitura
`PERDENDO_FORCA` em tendência. O próximo ajuste do limiar
`tijolos_para_tendencia` deve ser calibrado sobre todos os pregões, com
contagem de sobreposição e replay diferencial, e não reduzido apenas para
forçar o primeiro ULTRA a acender.

### Alteração autorizada — Renko fora do acionamento do ULTRA — 01/09/2026

O operador solicitou retirar o Renko da lógica. A alteração foi aplicada de
forma isolada:

1. `MotorSinalUltra._confluencia` agora exige somente DECISÃO confirmada,
   Maker forte na mesma direção e confiança Maker acima do limiar configurado;
2. a persistência contínua e a histerese permanecem intactas;
3. `fase_renko` e `direcao_renko` continuam no contrato por compatibilidade e
   permanecem disponíveis para gráficos e diagnóstico, mas são informativos;
4. o painel passou de quatro para três lâmpadas e deixou de apresentar Renko
   como gate, evitando que o operador interprete contexto como bloqueio.

### Revalidação após remover Renko

O pregão inteiro de 31/08 foi reprocessado no pipeline real com
microestrutura, detectores, metodologia, feed, MakerProxy e decisão ativos;
somente analytics visuais foram desligados para manter a medição reproduzível.

| medida | resultado |
|---|---:|
| negócios processados | 35.902 |
| quadros ASG | 17.510 |
| pré-sinais | 7.985 |
| confirmações | 7 |
| confirmações com Maker acima de 0,60 | 7 |
| ULTRA ligado | 0 |

O resultado é importante: o Renko deixou de bloquear, mas o ULTRA ainda não
ligou nesse pregão porque as sete confirmações não permaneceram simultâneas
por 5 segundos, que é a persistência configurada. A proteção de persistência
não foi removida nem reduzida silenciosamente. Portanto, o teste confirma a
remoção do Renko, mas também revela que o próximo gargalo real é a duração da
confluência DECISÃO + MAKER + CONFIANÇA.

### Correção final de circularidade — contexto primário — 01/09/2026

A conclusão acima ficou obsoleta como regra de produção e permanece apenas
como histórico da rodada anterior. A leitura das transcrições do Maker foi
incorporada de forma independente: Maker é complementar; a confirmação deve
nascer da leitura de contexto e da região, sem contar Maker duas vezes.

Foram aplicadas três mudanças auditáveis:

1. `MotorDecisaoASG` agora prioriza Micro, Placar e Macro para direção e
   confiança contextual quando esses campos existem. `MakerProxy` só volta a
   ser gate com `ConfigMotorDecisaoASG(exigir_maker_como_gate=True)`.
2. `MotorSinalUltra` removeu a dependência circular e passou a exigir, no modo
   padrão, decisão confirmada, Macro e Micro alinhados e persistência de 5 s.
   Maker continua no snapshot, na procedência e no alerta de divergência.
3. A UI não transforma pré-sinal em Ultra: somente títulos A1/A2/A3 do
   snapshot confirmado alimentam o motor Ultra. Renko continua visual e
   informativo.

### Revalidação final do caminho real — 31/08/2026

Pregão inteiro reprocessado em `montar()` com feed de gravação, livro,
microestrutura, metodologia, MakerProxy e decisão ativos. A sonda usou a
mesma janela de 5 s e a mesma condição contextual do painel; os números abaixo
são quadros de snapshot, não quantidade de entradas:

| medida | resultado |
|---|---:|
| negócios processados | 35.902 |
| quadros ASG | 17.511 |
| pré-sinais | 10.210 |
| confirmações | 8.624 |
| quadros Macro–Micro alinhados e confirmados | 4.396 |
| quadros Ultra comprador | 3.578 |
| quadros Ultra vendedor | 1.372 |
| estado final | NENHUMA |

O Ultra deixou de ser estruturalmente impossível e foi observado nos dois
lados. A duração de vários quadros do mesmo episódio não deve ser somada como
se fossem entradas; a próxima auditoria deve contar transições
`NENHUMA -> COMPRA/VENDA` separadamente. A regra não é fórmula proprietária da
ASG: é a `REGRA DO OPERADOR B3`, versionada como
`operator-b3-consultive-v3-context-primary`.

## Como reproduzir

```bash
python scripts/painel.py --fonte replay --arquivo dados --data 2026-08-31 \
    --velocidade max --duracao 300 --simbolo WDOU26
```

Com a sonda que espia `MotorDecisaoASG.avaliar` e conta
`snapshot.bloqueios` (a sonda usada vive no scratchpad da sessao; o essencial
e monkeypatch de `avaliar` + `collections.Counter` sobre `bloqueios`,
`pre_sinal` e `confirmacao`).

---

## Seletividade em TEMPO DE MERCADO — 02/09/2026

Pergunta do operador: *"investiga o Renko em TENDENCIA nunca coincidir com
confirmação"*.

### 1. A pergunta partia de uma premissa errada

A frase "o Renko atingiu TENDENCIA em 4.243 leituras, mas nenhuma coincidiu
com uma confirmação" sugere uma relação (anticorrelação) entre duas
variáveis. Medindo as duas do **MESMO `EstadoNexo`, no mesmo instante** —
para "nunca coincide" não poder ser artefato de bases diferentes:

| fase do Renko | confirmada | não confirmada |
|---|---:|---:|
| TENDENCIA | **250** | 0 |
| PERDENDO_FORCA | 1.446 | 0 |
| POSSIVEL_INVERSAO | 452 | 0 |
| INDEFINIDA | 1 | 3 |

**Sobreposição observada: 250. Esperada sob independência: 249,65.**

Não há anticorrelação alguma. O que havia antes era uma variável
constante-zero: a confirmação não ocorria (`AGUARDAR` em 1.601 de 1.601
quadros). **Não é possível haver sobreposição com um evento que não
acontece** — o Renko nunca teve participação nisso. A correção de contexto
primário resolveu, e o Renko era espectador.

Nota de ferramenta: `scripts/auditoria_ultra_pregao.py` passa
`fase_renko=FaseRenko.INDEFINIDA` cravado ao motor. Ele não pode observar
esta coincidência — não é defeito (o Renko deixou de ser gate), mas o script
não serve para estudar esta pergunta.

### 2. O que a medição encontrou no caminho

Replay de 31/08 no caminho real, **426,3 min de tempo de mercado cobertos**
(~59% da sessão), 4.918 quadros. Cada quadro pesa o `dt` de tempo de MERCADO
até o quadro seguinte — quadro de UI não é amostra uniforme de tempo, e
lacunas acima de 60 s são descartadas.

| medida | valor |
|---|---:|
| fração do tempo com ULTRA aceso | **9,86%** |
| ULTRA comprador / vendedor | 8,10% / 1,76% |
| episódios (`NENHUMA -> lado`) | **57** |
| duração mediana do episódio | **41,08 s** |
| tempo com `DECISAO` acesa | **100,00%** |
| tempo com `CONTEXTO` acesa | **100,00%** |
| tempo com `PERSISTENCIA` acesa | 9,86% |

**Validação cruzada:** a auditoria independente do operador
(`ULTRA_PREGAO_COMPLETO_20260831.md`, contagem por negócio na sessão
inteira) achou 66 episódios com mediana de 38,637 s. Aqui, 57 episódios com
mediana de 41,08 s em 59% da sessão. Duas medições independentes, por
caminhos diferentes, convergindo — a taxa de disparo do ULTRA é confiável.

### 3. O achado: duas das três lâmpadas são decorativas

`DECISAO` e `CONTEXTO` ficam acesas **100,00% do tempo de mercado**. Uma
condição sempre verdadeira não filtra nada e não carrega informação: o
operador nunca aprende nada olhando para essas duas lâmpadas. Na prática a
confluência de três condições é **uma só** — persistência, cuja fração
(9,86%) é idêntica à do ULTRA aceso.

É o defeito anterior com o sinal trocado. Antes, três das quatro condições
estavam apagadas por construção (`RENKO` era filha de `DECISAO`, e `DECISAO`
nunca confirmava). Agora, duas das três estão acesas por construção. Em
ambos os casos o painel promete mais discriminação do que entrega.

**A taxa de disparo em si não é o problema.** 9,86% do pregão, com episódios
de ~41 s de mediana, é compatível com a fonte ("não é uma sinalização
constante"). O problema é o painel afirmar três portões quando só um decide.

### 4. Correção de uma medida minha, antes de qualquer conclusão

Na primeira passada eu reportei "ULTRA aceso em 33% dos quadros". Isso era
contagem por QUADRO DE UI, que não é amostra uniforme de tempo. Em tempo de
mercado são **9,86%** — a diferença é o viés de amostragem, não uma mudança
no produto. A ressalva foi declarada antes de medir e se confirmou.

### 5. Próximo passo sugerido

Não é reduzir limiar. É decidir o que as três lâmpadas devem significar:

- se `DECISAO` e `CONTEXTO` são pré-requisitos sempre satisfeitos no regime
  atual, elas deveriam sair do painel de confluência (ou virar um único selo
  de "base pronta"), deixando visível o que de fato varia;
- ou os limiares de `DECISAO`/`CONTEXTO` deveriam voltar a discriminar, e aí
  a pergunta é qual evidência eles deveriam exigir — decisão a ser tomada com
  a fonte na mão, não calibrando para um alvo de disparo.

### Como reproduzir

Sonda que espia `assistente.desenhar_resumo` e acumula, por quadro, o `dt` de
`snapshot.timestamp_ns` até o quadro seguinte, atribuindo esse tempo ao estado
de `sinal_ultra.direcao` e às condições de `nucleo._condicoes_ultra`. Lacunas
acima de 60 s são descartadas. Episódios são contados por transição
`NENHUMA -> COMPRA/VENDA`, a mesma unidade da auditoria por negócio.

```bash
python scripts/painel.py --fonte replay --arquivo dados --data 2026-08-31 \
    --velocidade max --duracao 900 --simbolo WDOU26
```
