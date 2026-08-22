
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
