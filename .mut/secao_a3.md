
#### A.3.2 — WINFUT: a varredura confere, e o ataque acha o defeito ESPELHO

**Controle — a varredura da onda 8, re-executada por mim** (`.mut/sonda_r6_motor.py`):

```
  laterais  CONF compra   mag_rel   referencia   n_visto  veredito
         0            0     0.450        9,620     1,793  gate segurou
     1,000            0     0.450        9,620     2,390  gate segurou
     5,000            0     0.450        9,620     2,390  gate segurou
    20,000            0     0.450        9,620     2,390  gate segurou
    50,000            0     0.450        9,620     2,390  gate segurou
```

Zero espúrios e `mag_rel` **plana em 0,450** no eixo inteiro, exatamente como
alegado. A `referencia` fica cravada em 9.620 de 0 a 50.000 laterais — é essa
constância que prova que a razão voltou a ser propriedade do mercado. Confirmado.

**Ataque A — dois picos separados por laterais** (não testado pelos builders):
com 5.000 e 20.000 laterais entre os picos, **0 espúrios**. O gate segura. O caso
`n_lat=0` marca 442 confirmações, mas ele é artefato do meu cenário, não defeito:
com zero laterais o segundo pico (comprador, qty 20, legítimo) ainda está dentro
da janela de dominância de 60 s quando o repique começa, então o que está sendo
confirmado é o pico de verdade, não o repique. **Ataque A não quebra o gate.**

**Ataque C — laterais logo abaixo do filtro de negócio único** (a variante que a
tarefa sugeriu): **minha hipótese estava errada e o gate resistiu.** Eu esperava
que um regime de poucos negócios grandes fizesse o filtro
`magnitude <= fator_dominio_trade_unico x maior_negocio` rejeitar quase tudo,
deixando `_n_visto < minimo_amostras_referencia = 32`, o que faria
`_magnitude_referencia` cair no ramo `float(self._max_sessao)` — auto-normalizante,
gate inerte. Medido:

```
 qty/negocio  trades/janela   n_visto   referencia   mag_rel  CONF compra  veredito
       1,000             10       794        9,000     1.000          387  gate ATIVO
       1,000             20       792       17,000     1.000          381  gate ATIVO
         500             10       794        4,500     1.000          387  gate ATIVO
           5            600       792        1,535     0.518            0  gate ATIVO
```

`_n_visto` chega a ~790 em todos os regimes: o filtro **não** mata a contagem de
amostras. Registro como resultado negativo — é evidência A FAVOR do desenho, e
era a variante mais promissora que eu tinha.

**Ataque B — pico gigante no FIM do dia: ACHADO NOVO.** A varredura dos builders
sempre põe o pico no começo. Invertendo a ordem:

```
 qty do pico  CONF do mov. legitimo   mag_rel   referencia  veredito
          20                    533     1.000        9,620  confirma
         200                      0     0.100       96,200  *** MUDO o resto do dia ***
       2,000                      0     0.010      962,000  *** MUDO o resto do dia ***
```

Um movimento **grande e genuíno** (900 negócios de qty 200 — dez vezes o normal:
leilão de fechamento, rolagem de vencimento, programa institucional) eleva a
referência do dia de 9.620 para 96.200. Depois dele, um movimento **legítimo de
tamanho normal** produz `mag_rel = 0,100`, abaixo de
`magnitude_relativa_minima = 0,60`, e o motor emite **zero** sinais pelo resto do
pregão. Com qty 2.000, `mag_rel = 0,010`.

**Isto é o defeito da R3/R4 espelhado.** A onda 8 trocou "a referência ESQUECE o
pico" (permissivo demais — 480 espúrios) por "a referência NUNCA esquece o pico"
(restritivo demais — mudo o resto do dia). A monotonicidade não-decrescente
dentro da sessão é **propriedade declarada** de `_magnitude_referencia`
("nunca esquece o pico", `motor/sinais.py:475-489`), então isto não é um bug de
implementação: é o **custo do desenho, e esse custo nunca foi medido**.

Três razões por que o `fator_dominio_trade_unico` **não** protege aqui, apesar de
ter sido construído para o caso vizinho:

1. ele filtra magnitude que **um negócio** explica sozinho; um movimento de 900
   negócios não é explicado por nenhum deles isoladamente e passa direto;
2. o `K = 32` do top-K não ajuda: o movimento gigante gera centenas de amostras
   grandes e preenche as 32 posições;
3. não há decaimento, nem janela móvel, nem referência por regime — a referência
   é do **dia inteiro**, e só sobe.

E é exatamente o item 9 do backlog da R3 (*"robustez do gate de magnitude a
pico < 5% do dia — janela de referência por regime, ou percentil sobre janela
móvel em vez do dia inteiro"*). A onda 8 trocou percentil-do-dia por
top-K-do-dia: as duas ancoradas no dia inteiro. **A recomendação estrutural da
R3 não foi adotada, e este ataque é a demonstração de por que ela importava.**

Assimetria que fecha o argumento: o modo de falha antigo (480 espúrios) exigia
**33 minutos de tape morno** para aparecer; este exige **um** evento grande, e o
pregão do WDO tem pelo menos um por dia (o leilão de fechamento). O modo de falha
novo é mais frequente que o que ele substituiu — e mais silencioso, porque
ausência de sinal não parece defeito.

**Ataque D — virada de sessão no motor: limpo.** `iniciar_nova_sessao()` zera
`_n_visto` (896 → 0), `_max_sessao` (962.000 → 0), `_reservatorio` (32 → 0),
`_janela_dominancia`, `_maiores_qty` e as micro-janelas; a referência volta a
`None`, e o dia 2 opera normalmente (892 confirmações, `mag_rel` 1,000). Isso
fecha o achado C.4 da R3 (o p95 sobrevivendo intacto a um salto de 24 h).

#### A.3.3 — dedup: confirmado, número a número

`.mut/sonda_r5_dedup.py`:

```
D) RETENCAO - 6 h de pregao a 65.000 eventos/s de ordem
  t= 1.0 h  chaves=802     t= 4.0 h  chaves=802
  t= 2.0 h  chaves=802     t= 5.0 h  chaves=802
  t= 3.0 h  chaves=802
  pico=802   teto=65536   (a chave viva e o NIVEL, ~800)

A2) MESMO teto (512) nas duas politicas
    chaves |   FIFO 512 |   NOVA 512 | degrau NOVA
       512 |       0.0% |       0.0% |   +0.0 pp
       560 |     100.0% |      16.2% |  +16.2 pp
       640 |     100.0% |      35.4% |  +19.2 pp
       768 |     100.0% |      56.2% |  +20.9 pp
      1024 |     100.0% |      79.1% |  +22.9 pp
      1536 |     100.0% |      92.8% |  +13.7 pp
      2048 |     100.0% |      98.1% |   +5.3 pp
```

| alegação | medido | veredito |
|---|---|---|
| retenção **802 chaves plana em 6 h** | 802, plana da 1ª à 5ª hora | confirma, exato |
| curva **sem penhasco**, maior degrau **22,9 pp** | maior degrau **22,9 pp** (em 1.024) contra 100 pp do FIFO | confirma, exato |
| com o teto real (65.536), 0% de re-emissão | 0,0% até 50.000 chaves em rotação | confirma |

#### A.3.4 — relógio: confirmado

`python bench_mt5.py`:

```
    tape   entregues  perdidos      CPU      capacidade  custo/1s de tape
  10,000      50,000         0   0.389s       128,411/s              7.8%
  50,000     250,000         0   2.354s       106,189/s             47.1%

Relogio de servidor - custo de `observar` + `agora_ns` por poll
        maximo puro (onda 7)            tape andando     0.122s       608 ns
   janela + deteccao (atual)            tape andando     0.231s      1154 ns
   janela + deteccao (atual)         tape parado 4:1     0.447s      2233 ns
```

- **Feed: zero perdidos até 50.000 ticks/s**, 5× a barra. Confirma a onda 7 e a
  confirmação da R4.
- **Custo do relógio novo:** 1.154 ns/poll × 20 polls/s = **23 µs por segundo de
  tape** (44,7 µs com tape parado). A alegação era +34 µs/s, +0,017%. O número
  alegado cai **dentro** do intervalo que medi. Confirmado. O estimador novo
  custa 1,9× o da onda 7 (1.154 contra 608 ns), o que também bate com o declarado.

#### A.3.5 — pipeline completo: o número da R4 continua indefinido

`python bench_app.py`:

```
estagio                                         ev/s (bus)    us/ev   ord/ev  veredito
1. barramento + EstadoMercado                       88,325     11.32     0.00  PASSA
2. + analytics (6 modulos)                          65,333     15.31     0.00  PASSA
3. + detectores de tape (3)                         43,747     22.86     0.00  PASSA
4. + MotorSinais                                    34,552     28.94     0.00  PASSA
5. + microestrutura  <<< PIPELINE COMPLETO           7,405    135.04     6.50  *** NAO PASSA ***

CONTROLE: muda so o BOOK
  (a) fundo aleatorio por tick (SimuladorWDO)         7,652 ev/s  ord/ev= 6.46  *** NAO PASSA ***
  (b) fundo estavel (DOM realista)                   19,225 ev/s  ord/ev= 0.98  PASSA

ESCALONAMENTO (procurando custo nao-linear)
     5,000     7,500 ev/s   133.33 us/ev        -
    10,000     7,422 ev/s   134.73 us/ev    x1.01
    20,000     7,360 ev/s   135.88 us/ev    x1.01
    40,000     7,270 ev/s   137.56 us/ev    x1.01
```

**Custo linear** (`x1,01` ao dobrar N quatro vezes): não há sexta casa de defeito
quadrático no pipeline, o que é coerente com o inventário da Parte A.

Mas o número que decide a barra continua **indefinido**, agora com margens um
pouco melhores que as da R4: **7.405 ev/s** no simulador cru contra
**19.225 ev/s** com book estável (a R4 mediu 5.873 × 14.236). A barra de 10.000
cai **dentro** do intervalo pela segunda rodada consecutiva. A diferença entre os
dois regimes é `ord/ev = 6,50` contra `0,98` — quantos eventos de ordem o
`InferidorMBP` precisa inferir por evento de mercado, que é inteiramente
propriedade de **como o book se mexe**, não do código.

**Qual dos dois é o WDO?** Ninguém neste projeto sabe, e não dá para saber sem
gravar um DOM real e contar. É a Parte D reaparecendo como número: a pergunta
*"o produto passa na barra de vazão?"* tem como resposta *"depende de um dado que
não existe em disco"*, e o caminho para obtê-lo é o que a Parte A mostrou
quebrado. Registro isto explicitamente porque é a segunda rodada em que o
**único critério quantitativo da barra** fica sem resposta — e porque o motivo
de ficar sem resposta é o mesmo maior gap.

#### A.3.6 — o Gravador sob carga (nunca medido em nenhuma rodada)

`.mut/sonda_r6_gravador.py`, código de produção, objeto vivo:

```
1) VAZAO do Gravador (barra do projeto: 10.000 ev/s)
   eventos   segundos         ev/s     us/ev  veredito
    20,000       0.46       43,220      23.1  PASSA
    60,000       1.35       44,428      22.5  PASSA

2) `_horarios` no objeto VIVO
  eventos publicados   len(_horarios)   bytes da lista   B/evento
              10,000           10,000          445,176       44.5
              40,000           40,000        1,791,064       44.8
              80,000           80,000        3,591,960       44.9

    pregao 6h a  5,000 ev/s ->   108,000,000 eventos ->   4.85 GB so em _horarios
    pregao 6h a 10,000 ev/s ->   216,000,000 eventos ->   9.70 GB so em _horarios
```

Duas leituras, e a segunda é a que importa:

- **O gravador é rápido o bastante**: 44.000 ev/s, 4,4× a barra, com
  `fsync_a_cada=200` de fábrica. Ele não é gargalo de CPU. Isso é um resultado
  favorável e vale registrar, porque significa que a correção da 6ª casa não
  precisa negociar desempenho contra memória — não há tensão a resolver.
- **`len(_horarios)` é exatamente o número de eventos publicados**, medido no
  objeto de produção: 10.000 / 40.000 / 80.000. 44,9 B por evento, linear. A
  extrapolação sintética da Parte A (48,45 B/ev) era **conservadora para mais**;
  o número do objeto vivo dá 4,85 GB em vez de 5,23 GB. O achado se mantém com o
  número medido no código de verdade.
