# Da pesquisa para o código — o que virou o quê, e por quê

Mapa de auditoria entre `pesquisa/metodologia_regras.md` +
`pesquisa/ferramenta_componentes.md` e o pacote `fluxopro/metodologia/`.
Serve para responder uma pergunta só: **o produto é fiel à fonte?**

A fonte da verdade deste documento é o registro executável
`fluxopro/metodologia/regras.py` (`REGRAS`, 42 entradas; `PARAMETROS`, 16).
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
| `linha_azul.lado` | INFERIDO | Implementada **e rotulada**: `LadoDaLinha.leitura_inferida` devolve `Side`, e `LeituraLinhaAzul.confianca_lado` é `Confianca.INFERIDO` em toda leitura. |
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

São 16 parâmetros pendurados em 11 regras. As 9 recusas: `exaustao.conceito`,
`escora.formula`, `sinal_ultra.gatilho`, `horarios.tabela`, `alvo.formula`,
`maker.formula`, `risco.limite_diario_agregado`, `risco.gatilho_de_tamanho`,
`placar.fonte_llm` — cada uma com `nota` explicando o porquê.

Contagens conferíveis a qualquer momento: `len(REGRAS)`, `len(PARAMETROS)` e
`len(nao_implementadas())` em `fluxopro/metodologia/regras.py`.
