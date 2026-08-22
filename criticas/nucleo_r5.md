# Auditoria adversarial R5 — `fluxo_pro` (commit `46ac053`, onda 8)

> Documento escrito INCREMENTALMENTE, parte a parte, conforme cada medição
> fecha. Nada aqui é afirmação do construtor: tudo que aparece como número foi
> medido nesta rodada, por este auditor, com o comando colado.

## Método

**Disciplina de mutação.** `.mut/harness_r6.py`. Para cada mutação: registro em
`.mut/r6_em_voo.json` **antes** de escrever no arquivo de produção; aplicação;
suíte inteira; restauração em `try/finally`; conferência do sha256 do conteúdo
**normalizado CRLF→LF** contra o pré-mutação, com `SystemExit` se divergir;
remoção do registro. `git diff` não é usado como prova de árvore limpa — já foi
provado cego neste repo pelo `.gitignore` da R3 — e a comparação crua contra o
blob de `HEAD` falha com `core.autocrlf=true`, que é o caso aqui. Ao fim de
cada lote, `r6_em_voo.json` volta a `[]` e isso é asserção do harness, não
inspeção manual.

**Leitura de código durante mutação em voo.** Enquanto um lote roda, o working
tree tem um arquivo de produção mutado. Toda leitura de código feita em
paralelo nesta auditoria saiu de `git show HEAD:<caminho>`, nunca do disco, e
toda medição que importa `fluxopro` foi serializada fora das janelas de
mutação. Isso está dito porque a alternativa — ler o disco e não perceber — é
exatamente o erro que o registro em voo existe para tornar detectável.

**Defeito do MEU harness, achado na conferência final e registrado porque a
próxima rodada vai reusar este código.** A restauração devolveu o **conteúdo**
certo em todas as 125 aplicações — o sha256 normalizado bateu 39/39 arquivos
contra `HEAD` — mas devolveu os **bytes** errados: escrevi com `newline=''`, que
grava `
` literal, enquanto o working tree deste repo é CRLF
(`core.autocrlf=true`). Resultado: 14 arquivos ficaram marcados `M` pelo `git
status` sem uma única diferença de conteúdo. Restaurado com
`git checkout -- fluxopro scripts` (seguro, porque a identidade de conteúdo já
estava provada), e a suíte re-conferida: **574 passed**, árvore idêntica ao
`HEAD`.

Duas lições, e a segunda é a que importa:
1. o harness deve escrever com `newline='
'` neste repo (é o que os harnesses
   da onda 8 faziam, via `Path.write_text`, que traduz para `os.linesep`);
2. **a conferência mandatória por sha256 normalizado está certa e não teria
   pego isto** — ela normaliza CRLF de propósito, que é justamente o que a torna
   confiável onde `git diff` mente. As duas checagens são complementares: a
   normalizada prova que nenhuma mutação ficou para trás; o `git status` prova
   que nenhum byte alheio mudou. **Rodar só uma das duas deixa um buraco**, e
   eu rodei só uma até o fim.

**Veredito de mutação.** Cada mutante enfrenta `pytest tests/ -q -x` inteiro,
não a lista de testes que o autor da mutação declarou. Uma mutação só é
"SOBREVIVEU" se **nenhum** dos 574 testes a pegou. Isso torna esta rodada mais
severa que as anteriores em alguns pontos e menos rápida em todos.

## Sumário executivo

| | |
|---|---|
| **Veredito** | **NÃO PASSA** |
| **Maior gap** | `fluxopro/gravacao/gravador.py:149` — a 6ª casa do defeito de crescimento |
| Suíte | 574 passam (47,19 s) |
| Re-mutação das 23 vivas da R4 + 8 novas | 16 mortas · 13 vivas · 2 âncoras extintas · **0 ressurreições** |
| Mutações NOVAS desta rodada | 27 · 13 mortas · **14 vivas (52%)** |
| Re-verificação das tabelas dos 5 builders da onda 8 | 67 · **66 mortas** · 1 viva (mal formada, já declarada pelo autor) |
| Total de aplicações de mutação nesta rodada | **125** · 95 mortas · 28 vivas · **0 ressurreições** |
| Números da onda 8 re-medidos | ver A.3 — **todos confirmam**, vários com folga |

**O que a onda 8 acertou:** tudo que prometeu. As cinco peças foram verificadas
uma a uma e nenhuma alegação numérica ficou aquém do medido; várias ficaram
acima. Re-apliquei as tabelas dos **cinco** builders — 67 mutações — e **66
morrem**; a única sobrevivente é a que o próprio autor já havia declarado mal
formada. Entre elas, N04/N05 (a física invertida do simulador), vivas desde a R2.
**Zero ressurreições em 125 aplicações de mutação.**

**Por que ainda assim NÃO PASSA:** a onda 8 respondeu à R4 com precisão, e a R4
não olhou para a camada de persistência. O ciclo gravar→reler — o único caminho
que existe para fechar o buraco de dado real que condena o projeto desde a R2 —
não funciona em nenhuma das duas pontas na escala do próprio produto: **4,85 GB**
para gravar um pregão (medido no objeto de produção), **37 GB** para relê-lo. E as 13 mutações que continuam vivas
depois de cinco rodadas estão, 12 delas, nessa mesma camada — e das 27 mutações
novas que plantei, **14 sobrevivem**, 11 delas nos mesmos módulos.

---

## Calibração do veredito contra a barra (feita ANTES de fechar)

Antes de eleger o maior gap, fui conferir se ele é grave **segundo a barra do
projeto**, e não só segundo meu gosto. `bar/barra_profit_pro.md` seção (d) diz,
com todas as letras:

> **Item 13 — Replay de Mercado** (…) *"Fora do núcleo mínimo, mas desejável
> para paridade mais completa (v2+): SuperDOM com envio de ordens,
> Bookmap/heatmap, **Replay de mercado**, Alarmes de agressão (…)"*

**Ou seja: a barra coloca replay no v2, não no núcleo mínimo do v1.** Isso
enfraquece a leitura ingênua do meu achado — "quebrou uma funcionalidade da
barra" — e eu registro isso contra mim mesmo, porque é exatamente o tipo de
conveniência que uma auditoria adversarial tem de recusar.

O achado continua sendo o maior gap por outra razão, mais forte:

**Neste projeto, gravar-e-reler não é uma funcionalidade — é o instrumento de
medição.** O núcleo mínimo do v1 é itens 1 a 6 da seção (d): Times & Trades,
livro, delta/agressão, VAP, ranking de players e candle+delta. Todos os seis
existem no código. O que nenhum dos seis tem é **calibração**: cada limiar que
os governa foi escolhido de leitura de vídeo, e a taxa de erro de cada um no
WDO é desconhecida (Parte D). O único caminho conhecido para calibrá-los é o
plano de 4 passos que a R3 escreveu e que a `PROGRESSO.md` mantém como plano
vigente — e o passo 1 dele é *gravar pregão*.

Some-se o que a docstring do próprio `gravador.py` afirma: **não existe fonte
externa de histórico de book para WDO/WIN.** A gravação não é uma cópia de
conveniência de um dado que se pode rebaixar de outro lugar; é a única cópia
que existirá. Se ela não roda na escala do pregão, os seis itens do núcleo
mínimo ficam permanentemente sem gabarito — e ficam assim em silêncio, porque
574 testes verdes não dizem nada sobre isso.

É por essa cadeia, e não por "quebrou o item 13", que o achado é o maior gap.

### Achado menor, mas corrosivo: a seção "verificado, não afirmado" está errada

`PROGRESSO.md:545-546`:

```
## Suíte de testes — estado real (verificado, não afirmado)
`python -m pytest tests/ -q` → **94 passed**. Rodei antes de escrever este parágrafo.
```

O número real é **574**. A seção está congelada na onda 3 e contradiz o próprio
documento em dois lugares (`:170` e `:360` registram 401). O problema não é o
número desatualizado — é *qual* seção está desatualizada: a única que carrega o
selo "verificado, não afirmado", ou seja, aquela que um leitor usaria como
âncora de confiança quando o resto do documento parecer otimista. Um selo de
honestidade que envelhece sem manutenção é pior que nenhum selo, porque
transfere credibilidade para o dado errado. Custa uma linha para corrigir.

---

## PARTE A — verificação da onda 8

### A.1 — suíte

```
$ python -m pytest tests/ -q
........................................................................ [ 12%]
........................................................................ [ 25%]
........................................................................ [ 37%]
........................................................................ [ 50%]
........................................................................ [ 62%]
........................................................................ [ 75%]
........................................................................ [ 87%]
......................................................................   [100%]
574 passed in 47.19s
```

574 passam. Confirmado. Isto é o piso, não a prova — as seções seguintes
mostram que 574 verdes convivem com um vazamento de 5 GB.

---

### A.4 — A SEXTA CASA (achada; é o maior gap desta rodada)

O critério que o builder da 5ª casa deixou no docstring de `_registrar_preco`:

> *qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão
> continua?*

Apliquei o critério a TODA coleção de instância do projeto. O inventário
completo está em A.4.3. A resposta é "número de eventos" — a resposta errada —
em **um** lugar, e ele é pior que a 5ª casa:

#### `fluxopro/gravacao/gravador.py:99` + `:149` — `Gravador._horarios`

```python
# :99
self._horarios: dict[tuple[str, date], list[int]] = {}
...
# :149  (dentro de _escrever, ou seja: caminho quente, UMA VEZ POR EVENTO)
self._horarios.setdefault((symbol, dia), []).append(evento.timestamp_ns)
```

E o consumo, único, lá no fim do dia (`:178-186`):

```python
horarios = self._horarios.pop((symbol, dia), [])
meta = {
    ...
    "hora_inicio_ns": min(horarios) if horarios else None,
    "hora_fim_ns": max(horarios) if horarios else None,
}
```

**A grandeza que limita o `len` é o número de eventos do pregão, e ela não para
de crescer enquanto o pregão continua.** A lista acumula um `int` por evento —
Trade, BookSnapshot, BookDelta e FalhaCaptura, todos — do primeiro ao último
evento do dia, para no fim produzir DOIS ESCALARES: o mínimo e o máximo.

Medição (`.mut/sonda_r6_colecoes.py`, `tracemalloc`, este auditor):

```
n=  100,000  bytes=    4,800,928  bytes/evento= 48.01
n=1,000,000  bytes=   48,448,672  bytes/evento= 48.45
  pregao 6h a  5,000 ev/s -> 108,000,000 eventos ->   5.23 GB so em _horarios
  pregao 6h a 10,000 ev/s -> 216,000,000 eventos ->  10.46 GB so em _horarios
  pregao 8h a  5,000 ev/s -> 144,000,000 eventos ->   6.98 GB so em _horarios
```

48,45 bytes por evento (o ponteiro de 8 bytes na lista mais o objeto `int`
grande de nanossegundos, que não é *cached small int*). O crescimento é
rigorosamente linear entre 100 k e 1 M, então a extrapolação é reta, não
otimista.

**Por que isto é pior que a 5ª casa.** A 5ª casa era uma estrutura cujo custo
tinha ao menos uma função (o heap servia para achar o topo do livro). Aqui não
há nem isso: `min` e `max` de um fluxo são calculáveis em O(1) de memória com
duas variáveis. Não existe versão do requisito em que guardar 108 milhões de
timestamps seja necessário. É desperdício puro, no caminho quente, com fator
~54 milhões de vezes mais memória que o necessário.

**Por que 574 testes não pegam.** Fui conferir a escala dos testes de gravação
e ela é menor do que eu supunha:

```
tests/test_gravacao_gravador.py:59    assert meta["n_eventos_total"] == 1
tests/test_gravacao_gravador.py:178   for i in range(5):
tests/test_gravacao_integridade.py:83 assert entrada.n_eventos_total == 3
tests/test_gravacao_integridade.py:163 ... for i in range(10)]
```

**1, 3, 5 e 10 eventos.** Em 10 eventos `_horarios` custa 485 bytes. O regime em
que o defeito existe é 10⁸ eventos — **sete ordens de grandeza acima**. Nenhum
teste da suíte exercita o gravador em ordem de grandeza de pregão, e nenhum
teste afirma nada sobre a memória de coisa alguma. O defeito é invisível por
construção para esta suíte, e continuaria invisível numa suíte dez vezes
maior escrita com o mesmo critério.

**Por que isto não é teórico.** Este é exatamente o caminho de
`scripts/operar.py --gravar` — o modo que a Parte C da própria tarefa manda
usar para provar reprodutibilidade, e o modo que qualquer operador usaria para
guardar o pregão. Um pregão de WDO com o pico de 5–10 mil eventos/s da barra
mata o processo por OOM antes do fechamento numa máquina de 8 ou 16 GB, e o
`meta.json` — que é onde moram os hashes de integridade — **só é escrito em
`_fechar_dia`**. Ou seja: o processo morre e a gravação do dia inteiro fica sem
`meta.json`, sem hash, e (ver `_comprimir_e_remover`) sem o `.gz`. Perde-se a
verificação de integridade do dia todo por um acumulador que não precisava
existir.

**A correção é de três linhas** (substituir a lista por `hora_inicio_ns` /
`hora_fim_ns` atualizados incrementalmente). O tamanho da correção é o que
torna o achado grave: não é uma escolha de projeto defensável, é um descuido
que sobreviveu a cinco rodadas de auditoria porque nenhuma delas olhou o
gravador com o critério de crescimento.

#### A.4.1 — inventário completo das coleções de instância

Critério aplicado a cada uma. "OK" = a grandeza que limita o `len` é níveis
vivos, ordens ativas, janela em ns, ou uma constante.

| local | coleção | o que limita o `len` | veredito |
|---|---|---|---|
| `gravacao/gravador.py:99` | `_horarios` | **número de eventos do pregão** | 🔴 **6ª CASA** |
| `motor/sinais.py:307` | `_janela_dominancia` | taxa × janela (5 min) | 🟠 ver A.4.2 |
| `analytics/agressao.py:98` | `_janela` | taxa × janela | 🟠 mesma forma |
| `analytics/brokers.py:90` | `_janela` | taxa × janela | 🟠 mesma forma |
| `detectores.py:665` | `_janela` | taxa × janela | 🟠 mesma forma |
| `motor/sinais.py:328,329` | `_micro_antiga/_micro_recente` | taxa × 15 s | 🟠 menor |
| `inferencia_mbp.py:293,294` | `_trades`, `_pendentes` | taxa × 300 ms | OK (janela curta) |
| `motor/sinais.py:310` | `_maiores_qty` | deque monotônico ⊂ janela | OK |
| `motor/sinais.py:316` | `_reservatorio` | `tamanho_topo_magnitude` = 32 | OK |
| `detectores.py:338` | `_MapaProcedencia._itens` | TTL 30 s + teto 65.536 | OK (onda 8) |
| `inferencia_mbp.py:319,320` | `_precos_no_heap_*` | níveis vivos × 2 (compactação) | OK (onda 8) |
| `dados/mt5.py:362` | `_RelogioServidor._janela` | janela 120 s + `max_amostras` | OK (onda 8) |
| `analytics/footprint.py:108` | `_niveis` | faixa de preço do candle | OK |
| `analytics/vwap.py:117` | `_ancoras` | nº de âncoras (constante) | OK |
| `core/estado_mercado.py:176,177` | `_bids`, `_asks` | níveis do book | OK |
| `livro_mbo.py:172-174` | `_ordens`, `_bids`, `_asks` | ordens ativas / níveis | OK |
| `perfil_player.py:70` | `_brokers` | nº de corretoras | OK |
| `gravacao/gravador.py:95,97,98` | `_dia_aberto`, `_arquivos`, `_contagens` | símbolos × dias abertos | OK |
| `gravacao/catalogo.py:48` | `_entradas` | dias gravados | OK |
| `core/barramento.py:35` | `_assinantes` | nº de assinaturas | OK |
| `inferencia_mbp.py:295,296` | `_trades_por_nivel`, `_pendentes_por_nivel` | ver A.4.3 | 🟡 a conferir |

**Só uma resposta contém "número de eventos": `_horarios`.** As cinco casas
anteriores foram todas achadas por esse critério aplicado a posteriori; esta é
a primeira achada aplicando-o de propósito, e é a única que o inventário
inteiro produz. Isso é, em si, um resultado favorável à onda 8 — o resto do
projeto passa no critério.

#### A.4.2 — a pista do builder do motor: `_janela_dominancia`

O builder do motor deixou anotado que `_janela_dominancia` cresce até
`taxa × janela` — 1,5 M de trades no default de 5 min a 5.000 tr/s. **Verifiquei
e é verdade, mas é uma classe diferente de defeito, e menos grave.**

É `O(taxa × janela)`, não `O(eventos)`: ela **para de crescer** quando o
mercado estabiliza na taxa — que é exatamente a segunda metade do critério.
Um pregão de 6 h não a faz maior que um de 5 min à mesma taxa. Por isso não é
a 6ª casa.

O que ela é: um **custo de memória mal dimensionado, não um vazamento**.
1,5 M de `_TradeJanela` a ~5.000 tr/s são centenas de MB por símbolo, e a
informação que a estrutura precisa manter é agregável — os volumes por lado já
são incrementais (`_vol_buy`/`_vol_sell`/`_vol_unknown`); o que exige o item
individual é só saber *quando* descontar na expiração. Isso é resolvível com
balde de tempo (p. ex. 100 ms), trocando 1,5 M de objetos por 3.000 baldes —
mesma semântica, 500× menos memória. Não é urgente como a 6ª casa (não
derruba o processo em algumas horas; degrada), mas está registrado.

`agressao.py:98`, `brokers.py:90` e `detectores.py:665` têm a mesma forma com
janelas menores.

#### A.4.3 — o gêmeo da 6ª casa, no lado da leitura

Ao aplicar o mesmo critério a `fluxopro/dados/leitor_gravacao.py` (módulo que a
Parte B da tarefa manda atacar) o inventário devolve **a mesma resposta errada
uma segunda vez** — e é isto que transforma o achado em veredito:

`fluxopro/dados/leitor_gravacao.py:139-146` — `_eventos_ordenados`

```python
def _eventos_ordenados(self) -> list[EventoGravado]:
    combinados: list[tuple[int, int, int, EventoGravado]] = []
    for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura):
        caminho = self._entrada.arquivo(formato.NOMES_ARQUIVO[tipo])
        for indice, evento in enumerate(_ler_arquivo(caminho, tipo)):
            if not self._dentro_do_intervalo(evento.timestamp_ns):
                continue
            combinados.append((evento.timestamp_ns, _ORDEM_TIPO[tipo], indice, evento))
    combinados.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in combinados]
```

`iniciar()` consome isso com `for evento in self._eventos_ordenados():` — ou
seja, **toda a janela pedida é materializada em memória, duas vezes, antes do
primeiro evento ser publicado**: uma lista de tuplas de 4 com o evento dentro, e
depois uma segunda lista com todos os eventos, as duas vivas ao mesmo tempo. E a
janela padrão é o pregão inteiro, porque `--de/--ate` são `None` se o usuário
não os passar (ver a contra-leitura no fim deste documento, que corrigiu uma
versão mais absoluta desta frase que eu tinha escrito antes).

Medido (sonda sintética, `dataclass(frozen=True, slots=True)` com os 8 campos
de `Trade`, mesma forma da tupla real):

```
  n=   50,000  so `combinados`=  16,723,178 B (334.5 B/ev)  +2a lista=  17,311,274 B (346.2 B/ev)
  n=  200,000  so `combinados`=  66,741,602 B (333.7 B/ev)  +2a lista=  68,509,698 B (342.5 B/ev)

  pregao 6h a  5,000 ev/s -> 108,000,000 eventos -> 37.0 GB SO para montar a lista de replay
  pregao 6h a 10,000 ev/s -> 216,000,000 eventos -> 74.0 GB SO para montar a lista de replay
```

342 bytes por evento, linear. **37 GB para reler um pregão que o projeto se
propõe a gravar.**

Aqui, ao contrário de `_horarios`, existe uma razão: a ordenação global por
`(ts, tipo, índice)` é o que garante o determinismo do replay (é a garantia que
`N10` protege). Mas a razão não exige a lista: os quatro arquivos já saem do
`Gravador` ordenados por timestamp (ele escreve na ordem de chegada e o relógio
é monotônico), então `heapq.merge` sobre os quatro iteradores, com a mesma
chave `(ts, _ORDEM_TIPO[tipo], indice)`, produz **exatamente a mesma sequência**
em memória O(4). A correção é de ~10 linhas e não muda uma linha de saída.

#### A.4.4 — por que os dois juntos são o veredito

Separados, são dois bugs de memória. Juntos, são a única coisa que importa
nesta rodada:

> **O ciclo gravar → reler é o único caminho que o projeto tem para fechar o
> buraco de dado real — e ele não funciona em nenhuma das duas pontas, na
> escala do próprio produto.**

Desde a R2 toda auditoria termina no mesmo lugar: nenhum número de qualidade
deste sistema jamais tocou tape de verdade, e o conserto é gravar pregão e
medir contra ele. A R3 elevou isso a plano de 4 passos, cujo passo 1 é
"gravar 5 pregões com `scripts/gravar.py`". As ondas 7 e 8 consertaram os dois
bloqueios que a R3 apontou para esse passo (o feed que travava acima de 1.000
neg/s e o relógio único). **Consertaram a captura e deixaram de olhar o
armazenamento.** Hoje:

| etapa | estado | por quê |
|---|---|---|
| capturar do MT5 a 50.000 ticks/s | ✅ onda 7 (a R4 confirmou) | — |
| **gravar um pregão em disco** | ❌ | `gravador.py:149` — 4,85 GB de `_horarios` (medido); OOM antes do fechamento, e o `meta.json` com os hashes só é escrito em `_fechar_dia` ⇒ **perde-se o dia inteiro** |
| **reler o pregão gravado** | ❌ | `leitor_gravacao.py:139` — 37 GB antes de publicar o 1º evento |
| medir sinal contra o tape | ❌ | depende dos dois acima |

O produto sabe ler o mercado rápido e não sabe guardar o que leu. As duas
correções somam ~13 linhas, e nenhuma das duas tem um teste que as force,
porque toda a suíte de gravação opera em centenas de eventos — três a cinco
ordens de grandeza abaixo do regime em que o defeito existe.

---

### A.3 — re-medição dos números da onda 8

Rodei tudo eu mesmo. Onde a onda 8 acertou, está registrado como acerto.

#### A.3.1 — a 5ª casa (heap): **confirmada, e melhor que o alegado**

`python bench_inferencia.py`, estágio 6 (o eixo que escondeu a 5ª casa):

```
 min     eventos   len(heap)  vivos  heap/vivo  media us    p99 us       max us   rompim. us       ev/s  veredito
   1     300,000           2      1        2.0     14.59     42.80      6,443.8         31.6     63,007  PASSA
   2     600,000           2      1        2.0     16.24     53.00     78,268.2         34.4     56,498  PASSA
   4   1,200,000           2      1        2.0     15.18     47.30    163,053.8         90.2     60,596  PASSA
   8   2,400,000           2      1        2.0     18.23     60.80    302,542.6         27.9     50,593  PASSA
  16   4,800,000           2      1        2.0     17.92     69.00    837,749.3         34.5     51,349  PASSA

  piso de ruido desta maquina (trabalho fixo, sem estrutura): p50 2.8 us | p99 8.7 us | max 2,925.8 us
  orcamento por evento da barra: 200 us. Alvo do rompimento: < 1.000 us (1 ms).
```

| alegação da onda 8 | medido por mim | veredito |
|---|---|---|
| heap 2,4 M → **2 entradas** | **2 entradas**, e mantém 2 até **4,8 M de eventos** (o dobro do testado) | ✅ confirma e **excede** |
| pior evento 5,3 s → **28 µs** | rompimento **27,9 – 90,2 µs** nas cinco durações | ✅ confirma |
| vazão **47.142 ev/s** | **50.593 – 63.007 ev/s** | ✅ confirma (acima) |

A razão `heap/vivo` fica **2,0 constante** de 1 a 16 minutos. Essa é a prova
que interessa — não a vazão. E a coluna `max µs` continua em centenas de
milissegundos *com a correção aplicada*, o que confirma a nota metodológica do
builder: `max` aqui é ruído de escalonamento do sistema operacional
(o piso da máquina mede 2.925,8 µs sem estrutura de dado nenhuma), e julgar a
cauda por ele levaria a conclusão errada nas duas direções. A coluna
`rompimento` é o eixo certo. **Este é o melhor trabalho da onda 8** e a
metodologia que ele estabelece é reutilizável.

Os demais estágios do bench também ficam planos: fator 1,00× em
`visitas/passo` de 500 a 10.000 tape/s (estágios 1-4), e 0,0 visitas/negócio
com 50 a 3.000 níveis pendurados (estágio 5, ~247.000 neg/s).

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


---

## PARTE B (1/2) — re-mutação: as 23 vivas da R4 + as 8 novas dela

Protocolo: `.mut/harness_r6.py`. Registro em `.mut/r6_em_voo.json` **antes** de
escrever; restauração em `try/finally`; sha256 do conteúdo **normalizado
CRLF→LF** conferido contra o pré-mutação a cada restauração, com `SystemExit`
se divergir; registro apagado ao restaurar. Ao final, `r6_em_voo.json` = `[]`
(conferido). Cada mutação enfrenta a **suíte inteira** (`pytest tests/ -q -x`),
não um subconjunto declarado — uma mutação só "sobrevive" se nenhum dos 574
a pegar.

**Placar: 16 MORTAS · 13 SOBREVIVEM · 2 ÂNCORAS EXTINTAS. Zero ressurreições.**

| # | arquivo | mutação | R4 | **R6** |
|---|---|---|---|---|
| N04 | `dados/simulador.py` | agressão de COMPRA empurra o preço para BAIXO | 🟢 viva (4 rodadas) | ☠️ **MORTA** |
| N05 | `dados/simulador.py` | regime de absorção desligado | 🟢 viva (4 rodadas) | ☠️ **MORTA** |
| X06 | `perfil_player.py` | quem agrediu invertido | 🟢 viva | ☠️ **MORTA** |
| X08 | `perfil_player.py` | perna vendedora não conta clip | 🟢 viva | ☠️ **MORTA** |
| X10 | `perfil_player.py` | `agressividade` mede o lado PASSIVO | 🟢 viva | ☠️ **MORTA** |
| X01 | `analytics/brokers.py` | janela expira com `>=` | 🟢 viva | ☠️ **MORTA** |
| X04 | `analytics/brokers.py` | aceita trade de outro símbolo | 🟢 viva | ☠️ **MORTA** |
| X26 | `analytics/footprint.py` | vizinho diagonal zerado não marca | 🟢 viva | ☠️ **MORTA** |
| X27 | `analytics/footprint.py` | média por nível divide por n+1 | 🟢 viva | ☠️ **MORTA** |
| X28 | `analytics/footprint.py` | `delta_divergente` só olha alta | 🟢 viva | ☠️ **MORTA** |
| Y01 | `app/config.py` | perfil de sessão entrega depois do motor | ☠️ | ☠️ MORTA |
| Y02 | `app/config.py` | micro entrega depois do motor | ☠️ | ☠️ MORTA |
| Y03 | `app/config.py` | saída entrega antes de tudo | ☠️ | ☠️ MORTA |
| Y05 | `app/montagem.py` | recorte `--de/--ate` ignorado no CSV | ☠️ | ☠️ MORTA |
| Y08 | `app/saida.py` | inferida impressa como OBSERVADA | ☠️ | ☠️ MORTA |
| Y09 | `app/saida.py` | direção do sinal sempre `-` | ☠️ | ☠️ MORTA |
| **N01** | `dados/replay.py` | sort perde o desempate `(ts, origem, índice)` | 🟢 | 🟢 **VIVA — 5ª rodada** |
| **N03** | `dados/replay.py` | `buyer_broker`/`seller_broker` trocados no CSV | 🟢 | 🟢 **VIVA — 5ª rodada** |
| **N06** | `dados/mt5.py` | bids do PIOR para o melhor | 🟢 | 🟢 **VIVA — 5ª rodada** |
| **N10** | `dados/leitor_gravacao.py` | sort perde o desempate por tipo/índice | 🟢 | 🟢 **VIVA — 5ª rodada** |
| **N12** | `gravacao/formato.py` | `SCHEMA_VERSAO` 1 → 99 | 🟢 | 🟢 **VIVA — 5ª rodada** |
| **X15** | `dados/mt5.py` | `profundidade_maxima` ignorada | 🟢 | 🟢 **VIVA** |
| **X16** | `dados/mt5.py` | `BookDelta` de ADD sempre `position=0` | 🟢 | 🟢 **VIVA** |
| **X18** | `gravacao/catalogo.py` | `escanear` não limpa o índice | 🟢 | 🟢 **VIVA** |
| **X19** | `gravacao/catalogo.py` | `arquivo()` prefere o plano ao `.gz` | 🟢 | 🟢 **VIVA** |
| **X20** | `gravacao/catalogo.py` | intervalo invertido aceito em silêncio | 🟢 | 🟢 **VIVA** |
| **Y04** | `app/montagem.py` | fonte construída antes da sessão | 🟢 | 🟢 **VIVA** |
| **Y06** | `app/montagem.py` | escolhe o dia MAIS ANTIGO da gravação | 🟢 | 🟢 **VIVA** |
| **Y07** | `app/montagem.py` | verificação de hash desligada em silêncio | 🟢 | 🟢 **VIVA** |
| X14 | `dados/mt5.py` | dedup de tick vira `<` | 🟢 | ⚙️ âncora extinta (onda 7 reescreveu — legítimo) |
| Y10 | `analytics/footprint.py` | piso do imbalance vai a 10 | ☠️ | ⚙️ âncora extinta (o default virou 5 na onda 8 — legítimo) |

### B.1 — leitura: a onda 8 entregou exatamente o que prometeu, e só isso

**As 10 que o builder 5 alegou ter matado morreram, todas as 10.** Verifiquei
uma por uma contra a suíte inteira, não contra a lista de testes que ele
declarou. Isso inclui N04 e N05 — *"agressão de compra empurra o preço para
baixo"* e *"absorção desligada"* —, vivas desde a R2 e o buraco de validade
mais citado das quatro rodadas anteriores. O gerador de toda medição de
qualidade do projeto finalmente tem asserção sobre a física que gera. **Zero
ressurreições** entre as 16 mortas.

**E as 13 que sobreviveram concentram-se num lugar só.** Agrupando por
subsistema:

| subsistema | vivas | de |
|---|---|---|
| `gravacao/catalogo.py` | **3** | 3 |
| `dados/replay.py` | **2** | 2 |
| `app/montagem.py` (o caminho gravação→sessão) | **3** | 4 |
| `dados/mt5.py` (só a borda ao vivo) | **3** | 4 |
| `dados/leitor_gravacao.py` | **1** | 1 |
| `gravacao/formato.py` | **1** | 1 |
| analytics + microestrutura + motor + app/config + app/saida | **0** | 16 |

**Doze das treze sobreviventes estão na camada de persistência e replay** — a
mesma camada que a Parte A acabou de condenar por crescer com o número de
eventos nas duas pontas. Dois métodos independentes — cobertura de mutação e o
critério de crescimento do docstring de `_registrar_preco` — apontam para o
mesmo subsistema, e nenhuma das cinco ondas o escolheu como alvo.

Duas dessas merecem nome próprio porque interagem com o achado principal:

- **`Y07` — a verificação de hash da gravação pode ser desligada em silêncio e
  a suíte fica verde.** O sha256 por arquivo é a única defesa contra gravação
  corrompida, e não existe fonte externa de histórico de book para WDO/WIN. É
  a terceira rodada com esse buraco na mesma vizinhança (a R2 mediu 9 de 12
  mutações vivas em `gravacao/`).
- **`Y06` — a montagem escolhe o dia mais antigo da gravação em vez do mais
  recente, e nada quebra.** Combinado com `X18` (o índice não é limpo no
  re-escaneamento, então um dia apagado do disco continua listado), o replay
  pode rodar sobre um dia que já não existe — e essa é a única fonte de dado
  histórico que o produto tem.

### B.2 — achado de leitura na camada de persistência: o fuso de `--de/--ate`

Achado enquanto montava as mutações novas; não precisa de mutação para ser
demonstrado, mas ganhou uma (`C01`) para medir se a suíte o prende.

`scripts/operar.py` documenta, na primeira linha do próprio módulo, o caso de
uso canônico:

```
python scripts/operar.py --fonte replay --arquivo dados/ --simbolo WDOV26 --de 09:00 --ate 10:30 --velocidade 10
```

`09:00` só pode significar a abertura do WDO na B3 — **horário de São Paulo**.
`_hora()` (`operar.py:53-59`) devolve um `datetime.time` **ingênuo**, sem fuso.
`montagem.py:140` o repassa a `Catalogo.consultar_intervalo`, que faz
(`catalogo.py:100` e `:104`):

```python
dt_inicio = datetime.combine(data, hora_inicio, tzinfo=timezone.utc)
ts_inicio = int(dt_inicio.timestamp() * 1e9)
```

**O horário do usuário é interpretado como UTC.** `--de 09:00 --ate 10:30` pede
06:00–07:30 de Brasília. O WDO abre 09:00 BRT = **12:00 UTC**. A janela pedida
cai inteira antes da abertura, e `_dentro_do_intervalo` (`leitor_gravacao.py:135`)
descarta tudo em silêncio: o replay do exemplo publicado no cabeçalho do
próprio script devolve **zero eventos**, sem erro, sem aviso, sem log.

Não existe nenhuma menção a fuso em `operar.py`, `montagem.py`, `catalogo.py`
ou `leitor_gravacao.py`.

**E aqui a mutação `C01` deu o resultado mais instrutivo da Parte B: ela
MORREU.** Existe, sim, um teste que prende a convenção — e ele é tautológico.
`tests/test_gravacao_integridade.py:205-218`:

```python
def _ts_utc(dia: date, hh: int, mm: int) -> int:                     # :62-63
    dt = datetime.combine(dia, time(hh, mm), tzinfo=timezone.utc)
    ...

def test_consultar_intervalo_nao_troca_hora_inicio_com_hora_fim(tmp_path):
    entrada, ts_inicio, ts_fim = catalogo.consultar_intervalo(
        _SYMBOL, dia, hora_inicio=time(9, 0), hora_fim=time(10, 30))
    assert ts_inicio == _ts_utc(dia, 9, 0)
    assert ts_fim == _ts_utc(dia, 10, 30)
```

O valor esperado é **re-derivado com exatamente a mesma expressão que a
implementação usa** (`datetime.combine(..., tzinfo=timezone.utc)`). O teste não
compara o código com uma convenção decidida: compara o código consigo mesmo. Ele
mata `C01` porque `C01` faz as duas linhas discordarem — e é **incapaz, por
construção**, de detectar que a convenção está errada para a B3, porque mover o
fuso nos dois lugares ao mesmo tempo o manteria verde.

Repare ainda que o teste usa `time(9, 0)` e `time(10, 30)` — **os números exatos
do exemplo publicado no cabeçalho de `operar.py`** — e os afirma como UTC. Ou
seja: a suíte cristalizou como UTC precisamente o horário que a documentação do
produto apresenta como abertura do WDO. As duas peças se contradizem e nenhuma
das duas pode notar.

E `Y05` (o recorte ignorado no CSV) morre, o que mostra que existe teste para o
recorte *acontecer*; o que não existe é teste para ele acontecer **na hora
certa**.

### B.3 — o que uma sexta rodada deveria atacar (e esta não atacou)

Registro para não desarmar a próxima revisão, no espírito da lição da R3 sobre
tabela medida no eixo errado:

- **Não medi `livro_mbo.py` sob carga nesta rodada.** A compactação de heap dele
  é a mesma da inferência (`livro_mbo.py:397-410`) e a onda 8 diz tê-la
  aplicado; eu confirmei a da inferência com benchmark próprio, mas a do livro
  só por leitura de código e pela mutação `O08` (que ataca a da inferência).
- **Não ataquei `eventos_mbo.py` nem `estado_mercado.py`.** Rodadas anteriores
  os cobriram (M27b, N29, N32 mortas) mas nenhuma depois da onda 7.
- **Não exercitei `FalhaCaptura` de ponta a ponta.** O caminho
  `TipoFalha.RELOGIO_REGREDIU` → gravação → catálogo → replay nunca foi
  percorrido inteiro por teste nem por sonda em nenhuma rodada.

---


---

## PARTE B (2/2) — 27 mutações NOVAS

Alvos escolhidos pelo critério da tarefa: o que nenhuma rodada tocou
(`gravacao/`, `core/barramento.py`, `core/relogio.py`, `dados/leitor_gravacao.py`,
`dados/replay.py`) e o que a onda 8 **acabou de escrever** (`_MapaProcedencia`,
`_RelogioServidor`, cauda de magnitude, compactação de heap). Mesmo protocolo:
suíte inteira por mutante, registro em voo, sha256 normalizado.

**Placar: 13 MORTAS · 14 SOBREVIVERAM (52% de sobrevivência).**

| # | arquivo:alvo | mutação | veredito |
|---|---|---|---|
| **G01** | `gravacao/gravador.py:149` | **substitui a lista de horários pelo min/max incremental — a CORREÇÃO** | 🟢 **SOBREVIVEU** |
| **G02** | `gravacao/gravador.py:117` | rotação de dia aceita voltar no tempo (`>` vira `!=`) | 🟢 **SOBREVIVEU** |
| **G03** | `gravacao/gravador.py:184` | `n_eventos_total` deixa de somar (vira o `max`) | 🟢 **SOBREVIVEU** |
| C01 | `gravacao/catalogo.py:100` | `--de/--ate` lidos em `-03` em vez de UTC | ☠️ MORTA — **por teste tautológico, ver B.2** |
| **C02** | `gravacao/catalogo.py:136` | **arquivo AUSENTE conta como íntegro** | 🟢 **SOBREVIVEU** |
| C03 | `gravacao/catalogo.py:148` | hash passa a incluir o cabeçalho | ☠️ MORTA |
| **C04** | `gravacao/catalogo.py:56` | `escanear` lê só o primeiro símbolo | 🟢 **SOBREVIVEU** |
| F01 | `gravacao/formato.py:59` | `decodificar_niveis` perde `n_orders` | ☠️ MORTA |
| **F02** | `gravacao/formato.py:78` | **comprador e vendedor trocados na volta do disco** | 🟢 **SOBREVIVEU** |
| **B01** | `core/barramento.py:48` | `publicar` itera uma cópia (a correção de reentrância) | 🟢 **SOBREVIVEU** |
| **B02** | `core/barramento.py:48` | **exceção de assinante engolida** | 🟢 **SOBREVIVEU** |
| B03 | `core/barramento.py:44` | ordenação por prioridade removida | ☠️ MORTA |
| **RL1** | `core/relogio.py:20` | **`RelogioReal` troca `monotonic_ns` por `time_ns`** | 🟢 **SOBREVIVEU** |
| RL2 | `core/relogio.py:63` | replay recusa timestamp igual | ☠️ MORTA |
| L01 | `dados/leitor_gravacao.py:137` | borda superior do recorte vira exclusiva | ☠️ MORTA |
| **L02** | `dados/leitor_gravacao.py:145` | desempate troca tipo↔índice | 🟢 **SOBREVIVEU** |
| **L03** | `dados/leitor_gravacao.py:94` | **base do catálogo errada ⇒ integridade nunca reprova** | 🟢 **SOBREVIVEU** |
| P01 | `dados/replay.py:19-20` | trade e delta trocam prioridade no empate | ☠️ MORTA |
| **O01** | `detectores.py:394` (onda 8) | **cursor da varredura AVANÇA ao remover** | 🟢 **SOBREVIVEU** |
| O02 | `detectores.py:374` (onda 8) | `_remover` não trata "a chave é a última" | ☠️ MORTA |
| **O03** | `detectores.py:403` (onda 8) | **RNG de despejo vira o `random` global** | 🟢 **SOBREVIVEU** |
| O04 | `dados/mt5.py:467` (onda 8) | janela deixa de ser estritamente monotônica | ☠️ MORTA |
| O05 | `dados/mt5.py:490` (onda 8) | `_resetar` não limpa a janela | ☠️ MORTA |
| O06 | `dados/mt5.py:472` (onda 8) | poda por idade deixa de rodar | ☠️ MORTA |
| O07 | `motor/sinais.py:426` (onda 8) | `_n_visto` conta antes do filtro | ☠️ MORTA |
| **O08** | `inferencia_mbp.py:802` (onda 8) | **teto de compactação `2×` vira `1×`** | 🟢 **SOBREVIVEU** |
| S01 | `app/saida.py:131` | marca `[OBS]` usa `>` em vez de `>=` | ☠️ MORTA |

### B.4 — o que as novas mostram

**G01 é a prova formal do maior gap.** Apliquei a **correção** — trocar a lista
por `min`/`max` incrementais — e os 574 testes continuam verdes. Junto com o
fato de que a versão atual também passa, isso estabelece o que interessa:
**nenhum teste da suíte distingue a implementação O(número de eventos) da
implementação O(1).** O defeito não é "não pego"; é **inatingível** por esta
suíte, nas duas direções. Um builder que o consertar não terá como provar que
consertou, e um que o reintroduzir não será pego. É por isso que o conserto
precisa vir acompanhado de um teste de crescimento, não só do patch de 3 linhas.

**As três do gravador sobreviveram todas (G01, G02, G03).** `G02` faz a rotação
de dia aceitar retrocesso: um evento atrasado com a data de ontem **fecha o dia
corrente e reabre o anterior**, escrevendo `meta.json` no meio do pregão e
recomeçando os hashes. `G03` faz o `n_eventos_total` do `meta.json` mentir. O
`Gravador` é, nesta rodada, o módulo com a pior cobertura efetiva do projeto —
e é o único guardião de um dado que não tem segunda cópia.

**C02 + L03 + Y07 juntas desmontam a cadeia de integridade.** Cada uma sozinha é
uma mutação; juntas são o mesmo furo por três caminhos:

- `C02` — um arquivo **que não existe** passa a contar como íntegro
  (`resultado[nome_base] = True`);
- `L03` — apontar o catálogo de verificação um nível acima faz o índice sair
  vazio, então `_checar_integridade` não encontra nada para reprovar;
- `Y07` (viva desde a R4) — a verificação pode ser simplesmente **desligada em
  silêncio**.

A docstring de `verificar_integridade` (`catalogo.py:113-127`) dedica quinze
linhas a explicar que este é *"a única defesa contra gravação corrompida"*
porque *"não existe fonte externa de histórico de book para WDO/WIN"*. Três
mutações independentes a neutralizam sem mover um teste.

**F02 e N03 são a mesma inversão nos dois leitores.** `F02` troca
`buyer_broker`/`seller_broker` na volta do disco em `gravacao/formato.py`; `N03`
faz o mesmo em `dados/replay.py` e está viva pela 5ª rodada. Quem gravou o
pregão e quem leu o CSV podem discordar sobre **quem comprou e quem vendeu**, e
a suíte não distingue. Isso importa mais depois da onda 8, porque foi ela que
ligou `RankingCorretoras` e `PerfilPlayer` — os dois módulos cuja pergunta
inteira é "quem está fazendo o quê".

**B01 e B02: o barramento não prende nem a reentrância nem o isolamento de
exceção.** As duas reservas que a R3 levantou (§C.3) e nunca foram fechadas
continuam abertas, e agora estão medidas: `B01` aplica a **correção** de
reentrância (iterar uma cópia) e a suíte fica verde; `B02` **engole toda
exceção** de assinante e a suíte fica verde. Ou seja, o comportamento do
barramento diante de um assinante que levanta — se derruba a captura ao vivo ou
se segue em frente — não está decidido por teste nenhum, nas duas direções.
Num sistema single-threaded em que analytics, detectores, motor, saída **e o
gravador** compartilham a mesma publicação, é a política que decide se um erro
de exibição mata a gravação do pregão.

**RL1: `RelogioReal` pode trocar `monotonic_ns` por `time_ns` sem quebrar nada.**
O módulo inteiro existe (docstring de `core/relogio.py:1-8`) para que nada no
núcleo chame o relógio da máquina diretamente, e `RelogioReplay` tem 20 linhas
de docstring justificando por que retroceder é inaceitável — com teste
(`RL2` morre). O irmão ao vivo, que é quem de fato roda em produção, não tem o
teste equivalente.

**As três novas da onda 8 que sobreviveram são as três invariantes que os
próprios docstrings justificam por escrito:**

- **`O01`** — `_varrer` documenta em cinco linhas que *"ao remover, o cursor NÃO
  avança"*, porque `_remover` traz outra chave para o mesmo slot, *"é o que
  permite a um mapa cheio de cadáveres esvaziar em O(n) escritas em vez de
  nunca"*. Fazer o cursor avançar não quebra teste nenhum.
- **`O03`** — o `_SORTEIO_DESPEJO = random.Random(0x5EED2026)` pode virar o
  `random` global do processo. A alegação de determinismo por construção não
  tem asserção. (Ver C.3b: hoje é latente, e explico por quê.)
- **`O08`** — `_limiar = max(_PISO_TETO_HEAP, 2 * len(vivos))` pode virar
  `1 * len(vivos)`. O fator 2 é **a constante de amortização inteira** da
  correção da 5ª casa: com `1×` a compactação dispara a quase toda inserção e o
  custo O(1) amortizado volta a ser O(n) por evento. A onda 8 aprendeu (M1/M2)
  que `len` não prova nada e passou a contar **trabalho** com um espião sobre
  `_compactar_heap` — mas o espião conta se a compactação *aconteceu*, não se
  ela acontece **raramente**. O teste que faltou é sobre a frequência.

Note o padrão: `O04`, `O05`, `O06`, `O07` e `O02` **morrem** — as invariantes
mecânicas do código novo estão bem cobertas. O que sobrevive são as três
**constantes de política** (o cursor, a semente, o fator 2) que o autor
justificou em prosa e não converteu em asserção. É o modo de falha
característico de código muito bem documentado: a docstring vira o teste na
cabeça de quem escreveu.

---

## PARTE B (extra) — B.5: re-verificação das 67 mutações que os 5 builders da onda 8 alegam ter matado

Não bastava conferir as 10 do builder 5 (que apareceram no lote da R4). Juntei as
tabelas dos **cinco** builders num lote único e re-apliquei tudo contra a suíte
inteira, com o mesmo protocolo:

| origem | mutações |
|---|---|
| `.mut/r5_dedup.json` + `r5_dedup2.json` + `r5_dedup3.json` (dedup) | 13 + 9 + 3 |
| `.mut/mutacoes_r5_relogio.json` (relógio MT5) | 12 |
| `.mut/harness_r5_heap.py :: MUTACOES` (heap / 5ª casa) | 12 |
| `.mut/r5_motor.json` (motor / WINFUT) | 10 |
| `.mut/mutacoes_r5.json`, as não medidas no lote da R4 (`*-own-*`, `Y10-R5`) | 8 |
| **total** | **67** |

### Resultado: **66 MORTAS · 1 SOBREVIVEU · 0 ressurreições**

E a única sobrevivente é aquela que o próprio builder já tinha reportado como
defeituosa:

| # | veredito | observação |
|---|---|---|
| **D03** | 🟢 SOBREVIVEU | *"volta o despejo determinístico (FIFO) no excedente"* — o relato da onda 8 registra, por conta própria, que **D03 sobreviveu por mutação mal formada do próprio builder**, e que ela foi refeita como LRU estrito |
| **D03b** | ☠️ MORTA | a versão refeita. Morre, como o builder disse que morria |

Conferi nominalmente as que mais importam, uma a uma: `D09b`, `D19b`, `D20b`
(dedup — varredura amortizada, varredura na inserção, relógio do `limpar`),
`M08`, `M09`, `M10` (motor — as três que sobreviveram na 1ª passada do builder e
geraram testes novos), `R11` (relógio — a que sobreviveu por teste de memória
invertido) e `H-M1`, `H-M2`, `H-M7`, `H-M11` (heap — as quatro que expuseram
defeito do teste, incluindo as que usavam 40-50 preços abaixo do piso de 64).
**Todas as onze morrem.**

### O que isso significa

Somando os três lotes desta rodada:

| lote | aplicações | mortas | vivas | extintas |
|---|---|---|---|---|
| re-mutação das vivas da R4 + novas da R4 | 31 | 16 | 13 | 2 |
| mutações **novas** desta auditoria | 27 | 13 | **14** | 0 |
| re-verificação das tabelas da onda 8 | 67 | **66** | 1 (mal formada, conhecida) | 0 |
| **total** | **125** | **95** | **28** | **2** |

**Zero ressurreições em 125 aplicações.** Nenhuma correção de onda anterior foi
desfeita, nenhuma alegação de morte de mutante da onda 8 se mostrou falsa, e o
único desvio é um que o próprio construtor já havia declarado.

Isto merece ser dito sem qualificação: **os relatos dos cinco builders da onda 8
são honestos no detalhe verificável.** Auditar cinco rodadas deste projeto e
encontrar 66 de 67 alegações confirmadas — com a 67ª sendo justamente a que o
autor marcou como sua própria falha de método — é um resultado incomum, e é
evidência de que o registro em voo, a conferência de sha256 e o hábito de
publicar as sobreviventes estão funcionando como disciplina.

**O contraste com os outros dois lotes é exatamente o achado do documento.** Onde
a onda 8 trabalhou, a cobertura é praticamente total (66/67). Onde ela não olhou,
metade das mutações novas sobrevive (14/27) e treze mutações resistem há cinco
rodadas — e as duas regiões não se sobrepõem:

```
     onda 8 mirou:  microestrutura, motor, mt5(relógio), analytics, perfil_player
                    -> 66/67 mortas | 0/16 novas sobreviventes nesses módulos

     ninguém mirou:  gravacao/, dados/leitor_gravacao, dados/replay, core/barramento,
                     core/relogio, app/montagem
                    -> 12/13 sobreviventes de 5 rodadas | 11/14 novas sobreviventes
```

A qualidade do trabalho não é o problema. **A seleção de alvo é.**

---

## Verificação independente do maior gap (contra-leitura)

Não confiei na minha própria leitura. Submeti as duas afirmações da Parte A a um
segundo leitor com a instrução explícita de **refutá-las**, lendo tudo por
`git show HEAD:` (o working tree tinha mutação em voo). As duas voltaram
confirmadas, e a contra-leitura acrescentou três coisas que eu não tinha:

**(a) O pior caso é o caso de uso principal, não um caso de borda.** Eu havia
verificado `scripts/operar.py --gravar`, que é opt-in. Mas existe
`scripts/gravar.py` — a CLI dedicada de gravação contínua — e lá o `Gravador`
é **incondicional** (`gravar.py:135-136`), com `n_eventos = 10**9` por padrão
(`:132`) rodando até Ctrl+C, e `parar()` só no `finally` (`:173`). A ferramenta
cuja única razão de existir é gravar um pregão inteiro é exatamente a que
dispara o defeito.

**(b) `_fechar_dia` tem exatamente dois chamadores, nenhum periódico.**
`gravador.py:119` (virada de dia em UTC) e `:109` (dentro de `parar()`). Não há
timer, limiar de tamanho nem rotação por número de linhas. `fsync_a_cada` zera
`n_desde_fsync` e não encosta em `_horarios` — não é rotação. Confirmado que
nada libera a lista antes do fim do dia.

**(c) Correção de escopo contra mim mesmo, na afirmação do leitor.** Eu escrevi
que `_eventos_ordenados` materializa "o dia inteiro". O correto é: o filtro
`_dentro_do_intervalo` é aplicado **durante** a construção
(`leitor_gravacao.py:142`), então a lista é limitada pela **janela pedida**, não
pelo dia. O ponto sobrevive porque a janela **é** o dia inteiro por padrão —
`montagem.py:148-156` deriva `ts_inicio/ts_fim` de `opcoes.de`/`opcoes.ate`, que
são `None` a menos que o usuário passe `--de/--ate`. A redação correta é: *o
replay segura em RAM toda a janela pedida antes de publicar o primeiro evento, e
a janela padrão é o pregão inteiro.* Registro a correção porque a versão
absoluta que escrevi antes era mais forte do que os fatos sustentam. (E note a
ironia com B.2: a única forma de **não** cair no caso ruim é passar `--de/--ate`
— as flags cujo fuso está errado.)

Dois detalhes a mais que a contra-leitura levantou e que valem registro:

- `_ler_arquivo` (`leitor_gravacao.py:58-64`) **é** um gerador de verdade, que
  faz streaming do gzip linha a linha. A preguiça existe e é imediatamente
  desperdiçada na linha 141, que a drena para dentro da lista. O conserto por
  `heapq.merge` não precisa construir infraestrutura nova: ela já está lá.
- `parar()` (`:127-128`) só levanta um flag conferido **dentro** do laço
  (`:112`). O `--duracao` de `operar.py:267` disparando durante a materialização
  não a interrompe — o processo fica preso montando a lista, sem responder.

**Argumento que a contra-leitura tornou possível e que é o mais incômodo para o
projeto:** este mesmo código-base *sabe* que o padrão é perigoso e se protege
dele em dois outros lugares — `detectores.py:168` define
`LIMITE_CHAVES_RASTREADAS = 65536` com a justificativa escrita de ser um limite
de desastre, e `mt5.py:471-476` poda a janela com o comentário de que ela
"nunca cresce sem limite". As duas defesas nasceram de auditoria (R4 e R3). O
`Gravador` nunca foi auditado, e é o único módulo do projeto sem nenhuma
defesa desse tipo. **O defeito não sobreviveu a cinco rodadas porque é sutil;
sobreviveu porque ninguém olhou.**

---

---

## PARTE C — ataques de sistema

Todas as sondas desta parte estão em `.mut/sonda_r6_sistema.py` e foram
executadas com a árvore **restaurada** (nenhuma mutação em voo), condição
conferida por `r6_em_voo.json == []` antes de cada execução.

### C.1 — reprodutibilidade: gravar → reler

```
  gravado: 1 entrada(s) de catalogo
    symbol=WDOV26  n_eventos_total=16,000
    integridade: {'trades.csv': True, 'book_snapshots.csv': True}
    ao vivo : (16000, 8000, 0)
    relido  : (16000, 8000, 0)
    => IDENTICO
```

Pipeline completo ao vivo com `Gravador` no mesmo barramento, depois
`Catalogo.escanear()` + `AdaptadorLeitorGravacao` sobre o gravado. **Idêntico**,
com os hashes de integridade conferindo. A R3 mediu 0 divergências em 4.000
trades; **o resultado sobrevive a duas ondas de mudança**, incluindo o
`_RelogioServidor` novo e a dedup por TTL — que eram justamente os dois suspeitos
por serem sensíveis a timestamp. Confirmado.

Ressalva honesta sobre o alcance deste teste: ele roda sobre `SimuladorWDO`, cujo
tape tem **um relógio só**. A reprodutibilidade sobre gravação do `AdaptadorMT5`
real — onde a R3 achou o problema dos dois relógios — continua **não testável**,
porque não existe gravação real (Parte D). O que este resultado prova é que o
caminho gravação→catálogo→leitor é determinístico; não prova que a captura ao
vivo carimba timestamps coerentes.

### C.2 — virada de sessão

```
  campo                                             dia 1    apos virada  veredito
  footprint._niveis (candle corrente)                   0              0  zerou
  footprint candles fechados                          199            199  *** SOBROU ***
  motor._n_visto                                    41573              0  zerou
  motor._max_sessao                                   959              0  zerou
  motor len(_reservatorio)                             32              0  zerou
  motor len(_janela_dominancia)                      1530              0  zerou
  brokers n_corretoras                                  0              0  zerou
  perfil_player n_brokers                               0              0  zerou
  livro n_ordens                                   248710              0  zerou
  det_escora n_chaves                                  16              0  zerou
  det_fantasma n_chaves                                16              0  zerou
  estado.volume_sessao                             401563              0  zerou
  => 1 campo(s) carregam o dia anterior: ['footprint candles fechados']
  SEM_RESET_POSSIVEL declarado na app: ('FootprintPorTimeframe',)
```

**Onze componentes têm `iniciar_nova_sessao` hoje** (contra 1 na R1 e 4 na R3):
`MedidorAgressao`, `RankingCorretoras`, `CumulativeDelta`, `VWAP`,
`EstadoMercado`, `SessaoFluxo`, `MotorSinais` e quatro em `detectores.py`. O
`SessaoFluxo` fecha os que não têm API **recriando a instância** com a mesma
config e religando o livro (`sessao_fluxo.py:594-617`).

**Virei a sessão e tudo zerou, com exatamente uma exceção: os 199 candles
fechados do `FootprintPorTimeframe`** — que é precisamente o único nome na
constante `SEM_RESET_POSSIVEL`. A causa está documentada no código: ele assina o
barramento sozinho no construtor e `Barramento` não expõe `desassinar`, então
trocar a instância dobraria a contagem. **É a única sobra, e ela está declarada
em vez de silenciada.** Isso fecha o achado C.4 da R3, que media 8 de 12
componentes carregando o dia anterior.

Duas observações que o número traz e a declaração não:

- a sobra é **199 candles**, não "algum estado": uma consulta ao histórico de
  footprint no dia 2 devolve candles do dia 1 misturados, sem marca de sessão;
- a raiz é uma linha que falta em `core/barramento.py` — um método
  `desassinar`. É a mesma ausência que a onda 6 registrou e que agora bloqueia o
  último componente. Vale mais que as três mutações do barramento juntas.

### C.3 — determinismo

**(a) O pipeline é determinístico em 500.000 eventos.**

```
  execucao 1: (500000, 250000, 0, None, 11054)
  execucao 2: (500000, 250000, 0, None, 11054)
  => IDENTICAS
```

Inclusive as 11.054 detecções. O motor perdeu o `random` na onda 8 e o resultado
se mantém. Confirmado.

**(b) O `_MapaProcedencia` com vítima sorteada: reintroduziu não-determinismo,
mas ele é LATENTE — e explico exatamente até onde.**

```
  _SORTEIO_DESPEJO e' <random.Random object> (modulo-global, semeado 0x5EED2026)
  LIMITE_CHAVES_RASTREADAS = 65,536
  limpar() resemeia o RNG? *** NAO ***

  (i) 300.000 eventos, 2.000 ticks distintos, chaves (side,price):
      len(mapa) = 2,000  contra teto de 65,536
      => despejo sorteado NUNCA DISPAROU

  (ii) com teto forcado (limite=64, TTL infinito, 4.000 chaves novas):
       sobreviventes da 1a passada: (3768, 3778, 3837, 3840, 3865, ...)
       sobreviventes da 2a passada: (3755, 3771, 3816, 3853, 3867, ...)
       => DIVERGEM - o RNG global nao volta ao inicio entre sessoes
```

A resposta em três partes:

1. **Sim, é não-determinismo real.** `_SORTEIO_DESPEJO` é global de módulo,
   compartilhado por todas as instâncias de `_MapaProcedencia` do processo (há
   três, uma por detector de livro), e `limpar()` — o reset de virada de sessão —
   **não o resemeia**. Forçando o teto, duas "sessões" no mesmo processo dão
   conjuntos de sobreviventes diferentes. Dois replays do mesmo dia no mesmo
   processo divergiriam.
2. **Não, ele não dispara em operação.** A troca de chave da onda 8 — de
   `order_id` para `(side, price)` — é o que o torna inerte: 300.000 eventos
   sobre a faixa de preço de um pregão inteiro produzem **2.000 chaves** contra
   um teto de **65.536**, uma folga de 33×. O despejo sorteado é backstop de
   desastre, e desastre não acontece na faixa de preço do WDO. A retenção medida
   em A.3.3 (802 chaves em 6 h) confirma pelo outro lado.
3. **É aceitável?** Sim, com uma ressalva. O sorteio é o que mata o penhasco
   (A.3.3: 22,9 pp contra 100 pp) e essa troca vale a pena. Mas a alegação da
   onda 8 de que *"o motor virou determinístico por construção, não por seed"*
   vale para o **motor** e não se estende ao pacote: os detectores continuam
   determinísticos **por seed**, e por uma seed guardada em estado global de
   módulo que nenhum reset toca. O conserto certo é uma linha — instanciar o
   `Random` **por mapa**, semeado na construção, e resemeá-lo em `limpar()` —
   e transforma "latente porque a folga é 33×" em "impossível por construção".
   Enquanto não for feito, `O03` sobrevivendo significa que nada impede um
   refactor futuro de trocar o `Random` semeado pelo `random` global.

### C.4 — interação entre as janelas da onda 8

```
  dedup do _MapaProcedencia   TTL     30 s   base: timestamp do EVENTO (tape)
  janela do _RelogioServidor         120 s   base: RELOGIO DE PAREDE
  janela de dominancia do motor      300 s   base: timestamp do EVENTO (tape)
```

**As três janelas convivem, mas não compartilham base de tempo.** Duas medem
tape (`_MapaProcedencia._agora_ns` é o maior timestamp de evento visto; a janela
de dominância poda por `trade.timestamp_ns`) e uma mede parede
(`_RelogioServidor._admitir` usa `time.monotonic_ns()` para envelhecer a janela).

Não achei cenário em que isso produza estado **incoerente**, e digo por quê: as
duas de tape são internamente consistentes entre si, e a de parede governa um
objeto — o estimador de offset — que não alimenta nem a dedup nem a dominância;
ele só carimba `timestamp_ns` na borda. A separação é, na verdade, a escolha
certa: um estimador de offset **precisa** de tempo de parede, porque a grandeza
que ele mede é a diferença entre os dois relógios.

Fica o registro de um regime em que a diferença é observável, sem que eu tenha
demonstrado dano: sob sobrecarga do adaptador — o regime de 50.000 ticks/s que o
próprio `bench_mt5.py` documenta, em que *"o adaptador consome tape mais devagar
que o relógio de parede"* — a janela de 120 s envelhece **mais rápido em relação
ao dado** que as outras duas. O efeito é a janela do relógio ficar efetivamente
mais curta em tempo-de-tape justamente no pico de volume. O builder do relógio já
tratou o sintoma vizinho (foi essa observação que o levou a criar o *armar*), e
o gate de admissão limita o estrago. **Classifico como observação, não como
defeito** — mas é a costura mais provável de romper primeiro se alguém mexer nas
constantes.

---

## PARTE D — dinheiro real: o tamanho do buraco

### D.1 — as três perguntas, respondidas de novo

```
=== MetaTrader5 instalado? ===
ModuleNotFoundError: No module named 'MetaTrader5'

=== dados/ existe? ===
ls: cannot access 'dados': No such file or directory

=== qualquer .csv / .csv.gz / meta.json de mercado em disco? ===
(nenhum arquivo encontrado na arvore inteira)

=== requirements.txt ===
pytest>=8.0
```

`requirements.txt` tem **uma** dependência, e é o pytest. `MetaTrader5` não é
nem declarado como dependência opcional. Nenhuma linha de `fluxopro/dados/mt5.py`
— o maior módulo do projeto, 1.044 linhas — jamais executou contra corretora
nenhuma. Quinta rodada, mesma resposta.

### D.2 — o tamanho, quantificado

"Falta dado real" já foi dito quatro vezes. O que ainda não tinha sido medido é
**o quanto do produto está apoiado em quê**. Classifiquei as 536 funções
`test_` (574 casos coletados, a diferença é parametrização) pela procedência
dos eventos que cada uma consome:

| procedência dos eventos | funções `test_` | o que isso prova |
|---|---|---|
| construídos à mão no próprio teste | **448** (83,6%) | a LÓGICA está certa dada a entrada. Não diz nada sobre a entrada ser a do WDO |
| `SimuladorWDO` | **53** (9,9%) | idem, mais a física do simulador (que só ganhou asserção na onda 8) |
| mock do `MetaTrader5` | **35** (6,5%) | o adaptador conversa certo com **o mock** |
| **tape real do WDO** | **0** (0,0%) | — |

Onde os 53+35 se concentram:

| arquivo | total | simulador | mock MT5 | à mão |
|---|---|---|---|---|
| `test_app_pipeline.py` | 29 | **24** | 0 | 5 |
| `test_app_montagem.py` | 17 | **13** | 0 | 4 |
| `test_dados_mt5.py` | 44 | 0 | **33** | 11 |
| `test_app_saida.py` | 16 | 6 | 0 | 10 |
| `test_app_cli.py` | 14 | 3 | 0 | 11 |

Isso corrige, para melhor, o enunciado da pergunta: **não são 574 testes
dependentes do `SimuladorWDO`, são 53.** A maioria da suíte testa lógica com
entrada fabricada à mão, e isso é uma forma legítima de teste. O buraco é mais
estreito do que "a suíte inteira é fictícia" — e mais fundo onde está:

1. **O produto montado é 100% simulador.** Das 29 funções de
   `test_app_pipeline.py` — o único lugar onde o sistema existe como produto e
   não como peças — **24 rodam sobre `SimuladorWDO`** e nenhuma sobre outra
   coisa. Toda afirmação sobre *comportamento de ponta a ponta* vem de um
   gerador cuja física do mercado só passou a ter asserção na onda 8 (N04/N05
   sobreviveram a R2, R3 e R4: por três auditorias, "agressão de compra empurra
   o preço para baixo" não quebrava um teste).
2. **A borda ao vivo é 100% mock, e o mock já mentiu.** 33 das 44 funções de
   `test_dados_mt5.py` descrevem `mt5.py` contra um mock escrito pelos mesmos
   construtores. A R3 provou o modo de falha exato: o mock ignorava `de` e
   `count`, e **os 10 testes de então passavam com o feed permanentemente morto
   acima de 1.000 ticks/s**. A onda 7 consertou o feed e melhorou o mock; nada
   garante que a próxima divergência mock↔terminal seja detectada, porque a
   fidelidade do mock não é asserção de ninguém — não existe teste de contrato
   contra a API real, nem sequer contra a assinatura do pacote `MetaTrader5`
   (que não está instalado).
3. **Nenhum limiar de fábrica foi calibrado.** `dominancia_minima=0.70`,
   `magnitude_relativa_minima=0.60`, `fator_dominio_trade_unico=2.0`,
   `tamanho_topo_magnitude=32`, `janela_reconciliacao_ns=300 ms`,
   `JANELA_EPISODIO_NS=30 s`, `_LIMIAR_REGRESSAO_NS=250 ms`,
   `qty_minima_imbalance=5`. Todos saíram de leitura de vídeo ou de raciocínio
   sobre o próprio código. **A taxa de falso positivo de cada detector no WDO
   continua desconhecida** — não estimada mal, desconhecida.
4. **A única afirmação do produto com gabarito objetivo nunca foi conferida.**
   O `InferidorMBP` diz "esta queda de quantidade foi execução, aquela foi
   cancelamento". O volume executado é público: está impresso no tape. Meia
   hora de WDO gravado permite medir a taxa de acerto com precisão. Isso nunca
   foi feito, e é a medição de maior valor por hora de trabalho no projeto
   inteiro.

### D.3 — o que exatamente fecharia o buraco, e o que mudou nesta rodada

A R3 escreveu o plano de 4 passos. Reavaliando cada um contra o estado de hoje:

| passo | estado na R3 | estado agora | bloqueio |
|---|---|---|---|
| **0. instalar `MetaTrader5` + conta com WDO** | não feito | **não feito** | fora do código: exige a máquina do dono, terminal MT5 instalado e uma conta de corretora. É o único bloqueio que nenhum builder pode remover |
| **1. gravar 5 pregões** | bloqueado pelo feed que travava a 1.000 neg/s e pelos dois relógios | **feed e relógio consertados (ondas 7 e 8, confirmados)**; mas agora bloqueado por `gravador.py:149` — 4,85 GB de `_horarios` (medido), OOM antes de fechar o dia, e sem `_fechar_dia` não há `meta.json`, hash nem `.gz` | **A.4 desta rodada** |
| **2. reler a gravação e fixar o simulador contra ela** | bloqueado pelo passo 1 | bloqueado pelo passo 1 **e** por `leitor_gravacao.py:139` — 37 GB antes do primeiro evento | **A.4.3 desta rodada** |
| **3. medir a reconciliação do `InferidorMBP` contra o volume impresso** | bloqueado | bloqueado pelos passos 1-2 | — |
| **4. medir qualidade de sinal por regime** | bloqueado | bloqueado pelos passos 1-3 | — |

**O que mudou de verdade entre a R3 e agora: o passo 1 saiu de "a captura não
funciona" para "a captura funciona e o armazenamento não".** É progresso real —
o gargalo andou uma casa — mas o passo 1 continua não executável, e com ele os
passos 2, 3 e 4.

**Custo estimado para desbloquear os passos 1 e 2: ~13 linhas** (min/max
incremental no `Gravador`, `heapq.merge` no leitor). O passo 0 não é código.

---

---

---

# VEREDITO

## **NÃO PASSA**

## O ÚNICO MAIOR GAP

> ### `fluxopro/gravacao/gravador.py:149`
>
> ```python
> self._horarios.setdefault((symbol, dia), []).append(evento.timestamp_ns)
> ```
>
> Uma lista que acumula **um `int` por evento do pregão** — Trade, BookSnapshot,
> BookDelta e FalhaCaptura, todos — para produzir, no fim do dia, **dois
> escalares**: `min(horarios)` e `max(horarios)` (`:185-186`).
>
> **4,85 GB** num pregão de 6 h a 5.000 ev/s; **9,70 GB** a 10.000 ev/s
> (medido no objeto de produção: 44,9 B/evento, linear de 10 k a 80 k eventos).
> O processo morre por OOM antes do fechamento — e como o `meta.json` com os
> hashes de integridade e a compressão `.gz` só acontecem em `_fechar_dia`, que
> tem exatamente dois chamadores e nenhum periódico, **perde-se a gravação do dia
> inteiro**, não só a memória.
>
> Gêmeo, na outra ponta do mesmo ciclo: `fluxopro/dados/leitor_gravacao.py:139-146`
> — **37 GB** para reler o que foi gravado (342 B/evento; a janela é o pregão
> inteiro sempre que `--de/--ate` não são passados).

### Por que este, e não outro

Havia três candidatos defensáveis. Registro por que os outros dois perderam:

- **A vazão do pipeline (7.405 × 19.225 ev/s, A.3.5)** é o único critério
  quantitativo explícito da barra e continua indefinido pela segunda rodada. Mas
  ele não é *o* gap porque não é acionável: a pergunta "qual dos dois regimes é o
  WDO?" só se responde com um DOM real gravado. Ele é **consequência** do gap,
  não concorrente dele.
- **O gate de magnitude mudo o resto do dia (A.3.2, ataque B)** é o achado novo
  mais interessante desta rodada e o mais próximo do produto. Mas é um erro de
  calibração de política, corrigível com uma janela de referência móvel — e a
  escolha da janela certa também depende de dado real.

O gap do gravador vence porque **é o pré-requisito dos outros dois e de todo o
resto**. Desde a R2 toda auditoria termina na mesma frase: nenhum número de
qualidade deste projeto jamais tocou tape de verdade. A R3 transformou isso num
plano de 4 passos cujo passo 1 é *gravar pregão*. As ondas 7 e 8 removeram os
dois bloqueios que a R3 apontou para esse passo — o feed que travava acima de
1.000 neg/s e os dois relógios — e ambos foram confirmados por mim nesta rodada
(zero perdidos a 50.000 ticks/s). **Consertaram a captura e não olharam o
armazenamento.** O gargalo andou uma casa e continua fechado.

E a docstring do próprio `gravador.py` fecha o argumento: **não existe fonte
externa de histórico de book para WDO/WIN.** A gravação não é uma cópia de
conveniência — é a única cópia que existirá.

### Por que ele sobreviveu a cinco rodadas

Não por sutileza. Este mesmo código-base **sabe** que o padrão é perigoso e se
protege dele em dois outros lugares — `detectores.py:168`
(`LIMITE_CHAVES_RASTREADAS = 65536`, com a justificativa escrita) e
`mt5.py:471-476` (a poda com o comentário "nunca cresce sem limite"). As duas
defesas nasceram de auditoria: R4 e R3. O `Gravador` é o único módulo do projeto
sem nenhuma defesa desse tipo, e é o único que **nenhuma das cinco rodadas
escolheu como alvo**. Sobreviveu porque ninguém olhou.

Duas medições independentes desta rodada apontam para o mesmo lugar, e essa
convergência é o resultado mais forte do documento:

| método | o que apontou |
|---|---|
| o critério de crescimento do docstring de `_registrar_preco` | a 6ª casa está em `gravacao/`, e é a **única** resposta "número de eventos" no inventário inteiro |
| cobertura de mutação | **12 das 13** sobreviventes de 5 rodadas, e **9 das 14** novas, estão em `gravacao/` + `dados/` + o caminho de montagem |

### A prova de que a suíte não alcança o defeito

Mutação `G01`: apliquei **a correção** (`min`/`max` incrementais) e os 574 testes
continuam verdes. A versão atual também passa. **Nenhum teste da suíte distingue
a implementação O(número de eventos) da implementação O(1).** O defeito não é
"não pego" — é inatingível por esta suíte nas duas direções. Os testes dedicados
ao `Gravador` publicam **1, 3, 5 e 10 eventos**; o maior teste que o exercita de
ponta a ponta (`tests/test_app_montagem.py:318-332`, gravar→reler com verificação
de hash) publica **400** (200 trades + 200 snapshots). O regime do defeito é
10⁸ — cinco a sete ordens de grandeza acima de qualquer teste existente.

Corolário para quem for consertar: **o patch de 3 linhas não é a entrega.** Sem
um teste que prenda o crescimento (`len(_horarios)` constante enquanto o número
de eventos cresce), a correção não é verificável e a regressão não é detectável.

---

## O que ainda impede uso com dinheiro real

Passar na barra técnica não é estar pronto para operar, e este projeto não passa
nem na primeira. Mas mesmo que os dois consertos de memória entrassem amanhã,
**continuaria proibido operar**, por razões que nenhum builder resolve sozinho:

| # | bloqueio | quem resolve |
|---|---|---|
| 1 | **Zero bytes de mercado real em disco.** `MetaTrader5` não instalado, `dados/` inexistente, nenhum `.csv`/`.gz`/`meta.json` na árvore. Nenhuma linha de `mt5.py` (1.044 linhas, o maior módulo) jamais executou contra corretora | **o dono** — máquina, terminal MT5, conta |
| 2 | **Nenhum limiar foi calibrado.** `dominancia_minima=0.70`, `magnitude_relativa_minima=0.60`, `fator_dominio_trade_unico=2.0`, `K=32`, `janela_reconciliacao_ns=300ms`, TTL de 30 s, `250 ms` de regressão — todos de leitura de vídeo. A taxa de falso positivo de cada detector no WDO é **desconhecida** | depende de (1) |
| 3 | **A única afirmação com gabarito objetivo nunca foi conferida**: o `InferidorMBP` diz "isto foi execução, aquilo foi cancelamento", e o volume executado está impresso no tape. Meia hora de gravação mede a taxa de acerto | depende de (1) |
| 4 | **A borda ao vivo é 100% mock** — 33 de 44 funções de `test_dados_mt5.py` — e o mock já mentiu uma vez: na R3 os testes passavam com o feed permanentemente morto acima de 1.000 ticks/s | depende de (1) |
| 5 | **A vazão do produto montado não tem resposta** (7.405 × 19.225 ev/s; a barra de 10.000 cai no meio) | depende de (1) |
| 6 | Zero linhas de UI (a barra é uma plataforma visual); nenhuma integração de envio de ordem (decisão de risco declarada) | escopo |

Os itens 2 a 5 são **o mesmo item**: todos esperam dado real, e dado real espera
o gap desta rodada. É por isso que ele é o maior.

**O caminho mais curto para sair daqui**, em ordem, com o custo honesto:

1. `min`/`max` incrementais no `Gravador` + `heapq.merge` no leitor — **~13
   linhas**, mais os dois testes de crescimento que faltam. O `_ler_arquivo` já
   é gerador; a infraestrutura de streaming existe e está sendo desperdiçada.
2. Instalar `MetaTrader5`, abrir conta, gravar **um** pregão de WDO. Não cinco:
   um basta para descobrir se o book real se parece com o regime (a) ou o (b) do
   `bench_app`, e isso sozinho resolve o item 5.
3. Medir a reconciliação do `InferidorMBP` contra o volume impresso. É a medição
   de maior valor por hora do projeto inteiro, e a única com gabarito.
4. Só então calibrar limiares e medir qualidade de sinal.

Até o passo 3, **nenhum número de qualidade produzido por este sistema pode ser
citado como evidência de nada** — incluindo os números favoráveis desta
auditoria.

---

## Nota final, contra o desânimo

O veredito é NÃO PASSA, e a onda 8 merece um registro que o veredito não
transmite: **ela acertou tudo que prometeu.** Re-medi cada uma das cinco peças e
nenhuma alegação ficou aquém; várias ficaram acima (o heap segura 2 entradas até
4,8 M de eventos, o dobro do testado; a vazão do motor deu 151.504 ev/s contra
143.649 alegados). Re-apliquei as tabelas de mutação dos cinco builders — 67
mutações — e **66 morrem**, com a única sobrevivente sendo exatamente aquela que
o autor havia marcado, por conta própria, como mutação mal formada dele mesmo.
Isso inclui N04/N05, a física invertida do simulador, viva desde a R2 e o buraco
mais citado das quatro rodadas anteriores. **Zero ressurreições em 125
aplicações.** A virada de sessão saiu de 8 de 12 componentes carregando o dia
anterior (R3) para **um só, declarado no código** — e eu o medi: 199 candles.

O problema desta rodada não é qualidade de execução. É **escolha de alvo**: cinco
ondas consertaram o que a auditoria anterior apontou, e a auditoria anterior
nunca apontou a camada que guarda o dado. O ciclo respondeu com precisão a
perguntas cada vez mais estreitas enquanto o subsistema que ninguém perguntou
acumulava 12 das 13 mutações vivas do projeto.

A recomendação para a onda 9 é, portanto, de método e não de código: **antes de
consertar o que esta crítica apontou, rodar o critério de crescimento e uma
passada de mutação sobre os módulos que nenhuma rodada escolheu.** Foi assim que
esta rodada achou tudo o que achou.
