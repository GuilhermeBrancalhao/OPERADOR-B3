# Da pesquisa para o código — o que virou o quê, e por quê

Mapa de auditoria entre `pesquisa/metodologia_regras.md` +
`pesquisa/ferramenta_componentes.md` e o pacote `fluxopro/metodologia/`.
Serve para responder uma pergunta só: **o produto é fiel à fonte?**

A fonte da verdade deste documento é o registro executável
`fluxopro/metodologia/regras.py` (`REGRAS`, 42 entradas; `PARAMETROS`, 17;
`FORA_DO_REGISTRO`, 3).
Ele é validado no import e conferido pela suíte
(`tests/test_metodologia.py`): citação com no máximo 15 palavras,
`AUSENTE_NA_FONTE` sem citação, parâmetro com dois valores de fonte exige
rótulo `IMPRECISO`, e **todo default declarado aqui tem de bater com o default
real do dataclass**. Se este documento divergir do código, a suíte quebra.

## A disciplina, em três linhas

| Rótulo | O que acontece com ele |
|---|---|
| `CONFIRMADO` | vira código |
| `IMPRECISO` | vira **parâmetro configurável**, nunca constante cravada |
| `INFERIDO` | vira código, mas a leitura sai **rotulada** como inferência |
| `AUSENTE NA FONTE` | **não vira regra do método** |

E o rótulo viaja: todo `Leitura*` do pacote carrega
`regras: tuple[RegraDocumentada, ...]`, com citação, vídeo, seção e
`Confianca`. Um painel pode mostrar "direcional ≥70%" **e** admitir que a
fonte oscila entre 70 e 75, porque o dado para isso está na mesma resposta.

---

## `metodologia_regras.md` — seção a seção

### §1 — Indicador percentual comprador × vendedor

| Regra | Rótulo | Situação |
|---|---|---|
| `dominancia.faixas` | CONFIRMADO | **Implementada, fora deste pacote**: `fluxopro/motor/sinais.py`, `FaixaConviccao` (LATERAL / PRE_DIRECIONAL / ZONA_CINZA / DIRECIONAL / MAXIMA_CONVICCAO). |
| `dominancia.limiar_direcional` | IMPRECISO | **Parâmetro** `ConfigMotorSinais.dominancia_minima` (default 0.70). Um vídeo diz 75%, outro 70% — o desacordo fica visível, e `ZONA_CINZA` marca o vão de 0,65–0,70 que a fonte não rotula. |
| `dominancia.nao_e_gatilho` | CONFIRMADO | Implementada: o percentual é condição 1 de uma confluência de 3, nunca gatilho sozinho. |

Nada de §1 foi reimplementado aqui — este pacote registra as regras para o
mapa ficar completo e aponta para onde elas já vivem.

### §2 — Exaustão de movimento

**Não implementada.** `exaustao.conceito` = AUSENTE NA FONTE: o termo
"exaustão"/"exausto" não ocorre em nenhuma transcrição lida. O
`DetectorExaustao` do repositório continua existindo como **componente
genérico de order flow**, de origem interna do projeto — as duas fontes ficam
separadas, e é esse o precedente que o pacote inteiro segue.

### §3 — Linha Azul → `fluxopro/metodologia/linha_azul.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `linha_azul.definicao` | CONFIRMADO | Implementada: nível = preço no instante em que o acumulado comprador/vendedor desde a abertura cruzou 50%. |
| `linha_azul.funcao_risco` | CONFIRMADO | Implementada **por omissão deliberada**: `LeituraLinhaAzul` não tem campo de gatilho, entrada ou direção sugerida. Publica nível, lado e distância. |
| `linha_azul.stop` | CONFIRMADO | Implementada: `distancia_ticks` (assinada). |
| `linha_azul.plotagem` | IMPRECISO | **Parâmetro.** O comportamento mudou entre versões da ferramenta original. Ver "Convenção declarada" abaixo. |
| `linha_azul.lado` | INFERIDO | Implementada **e rotulada**: `LadoDaLinha.leitura_inferida` devolve `Side`, e `LeituraLinhaAzul.confianca_lado` é `Confianca.INFERIDO` em toda leitura. **Parâmetro** `ConfigLinhaAzul.margem_ticks` (default 0): é o corte que decide ACIMA / ABAIXO / NA_LINHA, ou seja, o limiar da própria leitura inferida. |
| `linha_azul.janela_reset` | AUSENTE NA FONTE | Não há fórmula de acumulado nem regra de recálculo intradiário. Escolha declarada: acumula por agressor desde a abertura, reseta só na virada **explícita** de sessão (política de `EstadoMercado`). |

**Convenção declarada** (o que esta implementação escolheu, já que a fonte tem
duas versões):

1. A linha é o **último** cruzamento de 50%, não o primeiro
   (`ConvencaoLinhaAzul.ULTIMO_CRUZAMENTO`, default) — porque a fonte a usa
   como referência **viva** de invalidação, e um cruzamento das 9h01 não
   descreve o risco das 15h. `PRIMEIRO_CRUZAMENTO` existe e é suportado.
2. A convenção em vigor viaja em **toda leitura** (`LeituraLinhaAzul.convencao`),
   para nenhum painel precisar adivinhar qual versão está exibindo.
3. `volume_minimo_ancoragem` (default 0) adia o nascimento da linha: 0
   reproduz a versão que plota na abertura; qualquer valor > 0 reproduz a que
   "não plota mais na abertura", sem inventar o número que o autor usou.

Volume `UNKNOWN` (leilão, RLP) fica fora da razão e dentro do total, com
`volume_nao_atribuido` publicado — mesmo invariante do resto do projeto.

### §4 — Defesa de preço / escora

**Não implementada.** `escora.formula` = AUSENTE NA FONTE: "defender a região"
é qualitativo nos vídeos; `n_reposicoes_minimo` / `DetectorEscora` são
engenharia interna do projeto. As duas fontes ficam separadas.

### §5 — Sinal Ultra

**Não implementado.** `sinal_ultra.gatilho` = AUSENTE NA FONTE: saída de
caixa-preta, sem regra de preço/tempo/volume que defina quando dispara. Se um
dia entrar no `Placar`, entra como voto de um componente genérico do projeto,
com o rótulo do componente — não como regra do método.

### §6 — Macro × micro → `fluxopro/metodologia/macro_micro.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `macro_micro.macro` | CONFIRMADO | Implementada: acumulado de agressão desde a abertura (`janela_ns = 0`). |
| `macro_micro.micro` | CONFIRMADO | Implementada: variação do mesmo acumulado numa janela curta. |
| `macro_micro.hierarquia` | CONFIRMADO | Implementada: `LeituraMacroMicro.comanda` devolve o sentido da **micro**. |
| `macro_micro.escalas_incomparaveis` | CONFIRMADO | Implementada **como comportamento**, não como aviso — ver abaixo. |
| `macro_micro.contra_tendencia` | IMPRECISO | Implementada como flag qualitativa que **não bloqueia nada** (a frase da fonte está cortada na legenda). |
| `macro_micro.janela_micro` | AUSENTE NA FONTE | **Parâmetro** `ConfigMacroMicro.janela_micro_ns`. |

A regra de exibição da fonte — *"não confunda 10%, achando que a micro só
ficou 10% positiva"* — vira três coisas verificáveis:

- comparar (`<`, `>`, `==`, `-`, `/`) duas `MedidaContexto` de escalas
  diferentes levanta `EscalasIncomparaveisError`, em runtime;
- comparar uma `MedidaContexto` com um número cru também levanta — o número
  cru é justamente onde a escala se perde;
- `LeituraMacroMicro` **não expõe nenhum número que misture as duas**. Do par,
  só saem `alinhados` (bool) e `comanda` (`Side`) — comparação de sentido, a
  única que a fonte autoriza. `comparavel_por_magnitude` é um campo fixo em
  `False`, para a restrição aparecer na própria leitura.

A janela usada viaja em `MedidaContexto.janela_ns`: um painel não pode mostrar
"a micro" sem poder dizer de que janela está falando.

### §7 — Horários

**Não implementado.** `horarios.tabela` = AUSENTE NA FONTE. Existe só a
heurística qualitativa "fim de pregão é pior" e a âncora da linha azul na
abertura. Sem hora exata, nenhuma janela de horário virou regra do método.

### §8 — Mão cheia × mão mínima → `fluxopro/metodologia/risco.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `risco.mao_cheia` | CONFIRMADO | `ModoTamanho.MAO_CHEIA`. |
| `risco.mao_minima` | CONFIRMADO | `ModoTamanho.MAO_MINIMA`. |
| `risco.meia_mao` | CONFIRMADO | `ModoTamanho.MEIA_MAO`, **derivada** de `contratos_mao_cheia // 2` quando não configurada — a fonte diz literalmente "metade do lote", então não é um terceiro número solto. |
| `risco.gatilho_de_tamanho` | AUSENTE NA FONTE | **Não implementado.** `GestorRisco.avaliar` **exige** a `QualidadeRegiao` de quem chama. O sistema não infere qual região é "boa" e não finge inferir. |
| `risco.numeros_de_contratos` | AUSENTE NA FONTE | **Parâmetro**, e a recusa é explícita: `ConfigRisco` nasce em 0 e `tamanho()` levanta `TamanhoNaoConfiguradoError`. 20/10/5 são o lote pessoal do autor. |

### §9 — Limite de perdas → `fluxopro/metodologia/risco.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `risco.tres_stops` | CONFIRMADO | Implementada: 3 stops **seguidos** na mesma região abandonam aquela região no dia. Um ganho quebra a sequência. É o achado numérico mais sólido da fonte. |
| `risco.limite_diario_agregado` | AUSENTE NA FONTE | **Não implementado, e a ausência é testada**: dez regiões bloqueadas não fecham a décima primeira. |
| `risco.tamanho_de_regiao` | AUSENTE NA FONTE | **Parâmetro** `tamanho_regiao_ticks` (default 20 ticks, escolha de engenharia). Limitação conhecida: dois stops a 1 tick de distância podem cair em buckets vizinhos. |

O botão "zerar" (§9, CONFIRMADO como comportamento, condicionado a sinal
contrário) não foi implementado: é ação de execução de ordem, fora do escopo
de um motor de leitura.

### §10 — Alvo / take profit

**Não implementado.** `alvo.formula` = AUSENTE NA FONTE: o conceito de alvo 1 /
alvo 2 existe, a regra de cálculo não. Nenhum alvo é projetado.

---

## `ferramenta_componentes.md` — os três componentes ausentes do código

### §8 e §6.2 — Regime estrutural → `fluxopro/metodologia/estrutura.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `estrutura.regime` | CONFIRMADO | Implementada: regime só muda ao **romper a máxima** ou **perder a mínima** do dia — ou ao cruzar a região de abertura (§6.2). A checagem roda antes de atualizar os extremos, senão todo preço novo seria seu próprio extremo. |
| `estrutura.ruido` | CONFIRMADO | Implementada: movimento contra o regime que não quebra estrutura sai marcado `ruido=True`, com `gatilho=NENHUM`. |
| `estrutura.amplitude_do_ruido` | AUSENTE NA FONTE | **Parâmetros** `ruido_minimo_ticks` e `margem_ticks`, ambos default 0. Os "~1000 pontos" são a amplitude do dia narrado, não um limiar. |

Custo de dados: só preço. `registrar_candle` aceita OHLC quando não há tick,
com a limitação declarada de que a ordem intra-candle não existe no dado
(aplica O→H→L→C).

### §3 e §7 — Velocímetro → `fluxopro/metodologia/velocimetro.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `velocimetro.dois_eixos` | CONFIRMADO | Implementada: grandeza (`magnitude_relativa`) e manutenção (`persistencia_ns`) saem em **campos separados**, nunca fundidos num número. |
| `velocimetro.virada` | CONFIRMADO | `EstadoVelocimetro.VIROU`. |
| `velocimetro.escala_fixa` | AUSENTE NA FONTE | **Não implementada, e a ausência é testada**: não há nenhum limiar absoluto de magnitude no módulo. `test_leitura_e_invariante_a_escala` multiplica o dia inteiro por 10 e por 1000 e exige a mesma sequência de estados — uma constante reintroduzida quebra a igualdade na hora. |
| `velocimetro.normalizacao_winfut` | CONFIRMADO | Implementada: referência = K-ésima maior magnitude da sessão (min-heap de tamanho K), com o máximo da sessão como fallback conservador enquanto a cauda é curta. |

Parâmetros: `janela_ns`, `magnitude_relativa_minima`,
`tolerancia_variacao`, `tamanho_topo_magnitude` — todos sem número na fonte.

### §2 — Placar estatístico → `fluxopro/metodologia/placar.py`

| Regra | Rótulo | Situação |
|---|---|---|
| `placar.meta_leitura` | CONFIRMADO | Implementada **por construção**: `Placar.registrar` recebe votos de fora e **não assina o `Barramento`**. Sem votos não há lado, por mais fluxo que exista. |
| `placar.estabilidade` | CONFIRMADO | `estavel`, `oscilando`, `mudancas_na_janela`, `estavel_ha_ns`. |
| `placar.goleada` | IMPRECISO | **Parâmetro** `diferenca_goleada` (default 4, o menor dos dois placares citados). |
| `placar.aquecimento` | IMPRECISO | **Parâmetro** `aquecimento_ns`. |
| `placar.virada` | CONFIRMADO | `virou` e `alerta_reversao` (virada vinda de goleada). |
| `placar.fonte_llm` | CONFIRMADO, **recusado** | Existe na ferramenta original; não é fonte embutida deste produto. O próprio autor diz que *"não serve como um gatilho de entrada como a SG"*. Quem quiser pode passá-lo como voto — a escolha fica de quem monta. |

### §1 — Maker

**Não implementado.** `maker.formula` = AUSENTE NA FONTE: o autor descreve o
fenômeno-alvo e nunca a fórmula, e o feed MT5 (sem RLP/identidade, book nível
1-2) pode não sustentar a fidelidade. Qualquer proxy seria reinterpretação
nossa e entraria como componente genérico.

---

## A fiação — onde as regras passaram a ser alimentadas

Até esta rodada este documento descrevia um pacote **isolado**: 33 regras
implementadas, nove componentes testados, e **nenhum evento de produção
chegando a eles**. Um mapa de auditoria de código que nunca roda audita pouco.

Agora `fluxopro/metodologia/leitura.py::LeitorMetodo` recebe cada `Trade` do
pipeline — por `fluxopro/app/sessao_fluxo.py`, prioridade
`app/config.py::PRIORIDADE_METODO` (45, entre o motor e a contagem) — e
publica um `LeituraMetodo` imutável com as cinco leituras **do mesmo
instante**.

| componente | de onde vem o dado | regra que autoriza |
|---|---|---|
| `RegimeDoDia` | `trade.price` (ticks, `int`) | `estrutura.regime` |
| `MacroMicro` | `trade` (agressor + qty) | `macro_micro.macro` / `.micro` |
| `Velocimetro` | `MacroMicro.delta_macro` | `velocimetro.dois_eixos` |
| `LinhaAzul` | `trade` (agressor + preço) | `linha_azul.definicao` |
| `Placar` | os quatro votos acima | `placar.meta_leitura` |
| `GestorRisco` | **nada** — ver abaixo | `risco.gatilho_de_tamanho` |

Três consequências que valem estar escritas:

1. **Tick, não OHLC.** `RegimeDoDia.registrar_candle` existe para quem só tem
   candle, e o próprio módulo declara a limitação (a ordem em que máxima e
   mínima aconteceram DENTRO do candle não existe no dado; ele aplica
   O→H→L→C). No pipeline há tape, então a fiação usa `registrar_preco` — *"com
   tick disponível, use `registrar_preco`... o caso WINFUT é justamente sobre
   não confundir a ordem dos eventos com o resultado agregado"*.
2. **Um contador, não três.** O velocímetro mede o delta de agressão que o
   `MacroMicro` acumulou, e `tests/test_app_metodologia.py` confere esse
   número contra `CumulativeDelta.delta_sessao` — o mesmo delta calculado por
   outro caminho, na camada de analytics. Os extremos do regime são conferidos
   contra `EstadoMercado.sessao.high/low` pela mesma razão.
3. **O `Placar` continua sem assinar o barramento** (`placar.meta_leitura`,
   CONFIRMADO). Quem assina é a `SessaoFluxo`; ela monta os votos e os
   entrega. Quem vota é `ConfigMetodologia.fontes_placar` — escolha declarada
   de quem monta, não fatalidade embutida. O default são as quatro fontes que
   este pacote sustenta com regra registrada; as duas que a ferramenta
   original tem e o produto recusa (`sinal_ultra.gatilho`, `placar.fonte_llm`)
   continuam fora.

### O que a UI chama

```python
leitura = sessao.leitura_do_metodo()   # LeituraMetodo | None
```

`None` significa "método desligado (`ligar_metodologia=False`) ou nenhum trade
ainda"; os dois casos se distinguem por `sessao.metodo is None`. A chamada
**não drena** (ao contrário de `PonteFluxo.ler`, que esvazia um buffer e por
isso tem dono único): é estado de nível, e todo painel vê o mesmo objeto.

O retrato é **imutável e consistente entre campos por construção**: as cinco
leituras são montadas de uma vez sob o lock, e o construtor **recusa**
(`LeiturasInconsistentesError`) um retrato cujas leituras não tenham o mesmo
`timestamp_ns`. Um placar 4×0 comprador ao lado de um velocímetro que já virou
não seria uma tela imprecisa — seria uma tela que mente sobre a confluência,
porque o placar exibido foi apurado com o voto do velocímetro de antes.
`sessao.agressao`, hoje lido como três escalares soltos sem invariante
declarado entre eles, é o precedente que a fiação não repete.

Cada leitura carrega o próprio `regras: tuple[RegraDocumentada, ...]`, e
`leitura.regras` devolve a união das cinco (`REGRAS_DO_METODO_VIVO`, 24
regras) — é com ela que um painel pode exibir citação, vídeo, seção e rótulo
ao lado de cada número que desenha, em vez de o placar de fidelidade ler
`0 MÉTODO`.

### O risco continua fora do caminho automático

`risco.gatilho_de_tamanho` é AUSENTE NA FONTE, e a recusa agora é
**estrutural**, não só documentada:

- `GestorRisco` é instanciado e exposto (`sessao.metodo.risco`), mas **não é
  alimentado por evento nenhum** — 2.000 eventos de pregão deixam
  `regioes_rastreadas == 0`;
- `LeituraMetodo` **não tem campo de risco**, então não existe caminho pelo
  qual uma decisão de tamanho saia deste pacote sem que uma pessoa tenha
  passado a `QualidadeRegiao` e registrado o desfecho de uma operação.

A UI chama `sessao.metodo.risco.avaliar(preco, QualidadeRegiao.X)` e
`registrar_resultado(preco, ResultadoOperacao.X)` — as duas com entrada do
operador, sempre.

---

## `FORA_DO_REGISTRO` — os limiares que o registro **não** avaliza

`_validar()` confere a coerência do que foi **declarado**. O que ele
estruturalmente não podia cobrar é o que ninguém declarou: um limiar que mora
numa `Config*`, muda o veredito do produto e nunca foi registrado não viola
regra nenhuma, porque não existe para o validador. Foi assim que
`ConfigMotorSinais.magnitude_relativa_minima` (0,60) atravessou cinco
auditorias.

O conserto inverte a direção da cobrança: o conjunto do que **precisa** ser
declarado passa a vir do código, e `tests/test_metodologia.py::TestCoberturaDoRegistro`
faz a derivação. O critério é estreito e verificável:

> todo **nome de campo** que `PARAMETROS` declara para algum dono tem de estar
> declarado — em `PARAMETROS` ou em `FORA_DO_REGISTRO` — em **todo outro dono
> conhecido** que tenha um campo com esse nome.

É exatamente a classe de defeito da auditoria: um limiar que *parece* coberto
porque um homônimo de outro componente está coberto. O teste tem controle por
mutação — retirar uma declaração faz a checagem acusar aquele nome.

| limiar | valor | por que não está em `PARAMETROS` |
|---|---|---|
| `ConfigMotorSinais.magnitude_relativa_minima` | 0,60 | ver abaixo |
| `ConfigMotorSinais.tamanho_topo_magnitude` | 32 | homônimo do K do velocímetro (16); mesma ideia, referências diferentes (sessão inteira × janela móvel em amostras aceitas) |
| `ConfigMotorSinais.janela_micro_ns` | 15 s | homônimo de `ConfigMacroMicro.janela_micro_ns`; o aval de `macro_micro.janela_micro` é **daquele** componente |

**Isto não é um segundo registro de procedência — é o inverso dele.** Nenhum
consumidor deve lê-lo como cobertura, e nenhum lê:
`fluxopro/ui/paineis/matriz.py::regras_do_campo` continua respondendo tupla
vazia para estes três botões, que é a verdade sobre eles.

### O 0,60, e por que ele não foi pendurado em `velocimetro.normalizacao_winfut`

Aquela regra é **CONFIRMADO** e já hospeda
`ConfigVelocimetro.magnitude_relativa_minima` (0,25). O que a fonte confirma
ali é o **mecanismo** — *"normalizar por magnitude histórica e por
persistência"*, o caso WINFUT — e **não um número**: `velocimetro.escala_fixa`
registra, em AUSENTE NA FONTE, que não existe corte absoluto na fonte.

Pendurar o 0,60 na mesma regra faria o registro afirmar **dois cortes
diferentes sob um rótulo CONFIRMADO**, e do lado da tela `regras_do_campo`
passaria a exibir `CONFIRMADO` para um limiar que a fonte nunca deu. Os dois
números não são contraditórios entre si — são componentes com trabalhos
diferentes (o velocímetro é leitura de curto prazo e erra para o lado de
calar; o motor é porta de entrada) — mas nenhum dos dois tem aval numérico
da fonte.

O landing correto é uma regra AUSENTE NA FONTE própria, hospedando os dois
cortes com seus donos separados. Ele **não foi feito nesta rodada** porque
muda o que `regras_do_campo` responde para o botão `magnitude_relativa_minima`
do painel do motor, e com isso três expectativas literais de
`tests/test_ui_matriz.py` — arquivo de outro construtor, em edição
concorrente. Enquanto não entra, o painel diz `S/ REGISTRO`, que é a verdade,
e a ausência deixou de ser silêncio: está declarada, com dono, valor e motivo,
e um teste a cobra.

---

## Divergência declarada: cor

A fonte codifica direção em **verde/vermelho/amarelo**. Este projeto **não a
segue nisso**: o eixo direcional é **azul = compra / vermelho = venda**, com
verde e âmbar reservados ao segundo canal (estado do sistema, evento
detectado). A decisão é de acessibilidade e está em `design/direcao_visual.md`
§3.1 — verde↔vermelho colapsa em deuteranopia e protanopia (~8% dos homens);
azul↔vermelho não, e é a convenção que o trader de B3 traz do book.

As faixas, os limiares e os rótulos vêm do método; a codificação de cor, não.
Consequência prática: **nenhum componente de `fluxopro/metodologia/` emite
cor.** Todos emitem `fluxopro.core.eventos.Side`, e quem pinta decide na
camada de UI. A divergência está registrada no docstring de
`fluxopro/metodologia/__init__.py` e de `regras.py`, não escondida.

---

## Resumo

As 42 regras do registro, por rótulo e por destino:

| Rótulo | Virou código | Recusada | Total |
|---|---|---|---|
| `CONFIRMADO` | 21 | 1 (`placar.fonte_llm`) | 22 |
| `IMPRECISO` | 5 (todas como parâmetro) | 0 | 5 |
| `INFERIDO` | 1 (rotulada na leitura) | 0 | 1 |
| `AUSENTE NA FONTE` | 6 (só como parâmetro/convenção declarada, nunca como regra) | 8 | 14 |
| **Total** | **33** | **9** | **42** |

Os 6 `AUSENTE NA FONTE` que têm código são exatamente aqueles em que a fonte
descreve o **conceito** mas não o **número**, e o número virou configuração
com o motivo escrito: `linha_azul.janela_reset`, `macro_micro.janela_micro`,
`risco.numeros_de_contratos`, `risco.tamanho_de_regiao`,
`estrutura.amplitude_do_ruido`, `velocimetro.escala_fixa`. Nenhum deles é
apresentado como regra do autor.

São 17 parâmetros pendurados em 12 regras, mais 3 limiares declarados em
`FORA_DO_REGISTRO` — vivos, calibráveis, e que o registro **não** avaliza. As
9 recusas: `exaustao.conceito`,
`escora.formula`, `sinal_ultra.gatilho`, `horarios.tabela`, `alvo.formula`,
`maker.formula`, `risco.limite_diario_agregado`, `risco.gatilho_de_tamanho`,
`placar.fonte_llm` — cada uma com `nota` explicando o porquê.

Contagens conferíveis a qualquer momento: `len(REGRAS)`, `len(PARAMETROS)`,
`len(FORA_DO_REGISTRO)` e `len(nao_implementadas())` em
`fluxopro/metodologia/regras.py`.

As 33 regras implementadas deixaram de viver num pacote isolado, e a soma
fecha: **24** respondem por um `LeituraMetodo` publicado a cada trade do
pipeline (ver "A fiação", acima, e `REGRAS_DO_METODO_VIVO`), **6** pelo
`GestorRisco`, que só responde a comando do operador, e as **3** de
`dominancia.*` já viviam fora deste pacote, em `fluxopro/motor/sinais.py`.
