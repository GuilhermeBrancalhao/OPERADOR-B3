# Gauntlet — interface visual categoria ASG sobre o motor FluxoPro

**Aberto:** 22/08/2026 · **Arquivo de progresso ao vivo.** Não interromper para pedir status; ele é escrito aqui.

---

## Leitura honesta do briefing: o que ele especifica de visual

O briefing pericial de 22/08 é um documento de **engenharia forense**, não de design. Ele decide framework, divisão de linguagens, topologia e limites de prova. De especificação visual ele contém pouco — e é preciso dizer quanto, porque construir "a interface do briefing" sem isso seria inventar e chamar de reprodução.

O que **está** lá, e vira parâmetro:

| # | Parâmetro | Onde aparece no briefing | Classe |
|---|---|---|---|
| V1 | **Superfície inteiramente desenhada** — nenhum widget de sistema operacional | §1: "uma interface **inteiramente desenhada**"; e a tese de que Qt/WPF/Avalonia/Electron produziriam a mesma imagem | Confirmada |
| V2 | **HUD de densidade que "lembra jogos"** | Linha "É Unity ou engine de jogo?" — "O HUD lembra jogos" | Confirmada como descrição |
| V3 | **Cadeia legível**: `Market Data → processamento → Matrix → Dashboard` | §2, cadeia publicada pela própria ASG | Confirmada como declaração |
| V4 | **Camada intermediária de estado, nomeada e visível** ("Matrix") | §2: "estado intermediário chamado publicamente de Matrix" | Confirmada como descrição |
| V5 | **Sem decoração de janela** — entrega por captura/transmissão | §2: "transmissão por Zoom esconde decoração de janela e processo" | Confirmada |
| V6 | **Legibilidade sob recompressão de transmissão** | Consequência direta de V5: a tela é consumida via Zoom | Derivada |
| V7 | **Base própria; ferramenta externa em janela distinta** | "Profit Pro… sobrepostos à base ASG em **janelas distintas**" | Confirmada |

O que **não** está lá: paleta, tipografia, grid, lista de widgets, layout, densidade numérica. O briefing diz explicitamente que os pixels não identificam nem o framework.

### Escopo das regras de leitura — CORRIGIDO pelo dono, 22/08

Eu havia deixado as regras de leitura de fora, herdando a exclusão que o *briefing pericial* faz do próprio escopo. **O dono corrigiu: as regras ficam dentro do produto.** E ele está certo — a exclusão do briefing é sobre o que aquela perícia se propunha a investigar, não sobre o que este projeto pode construir. As regras não são material fechado:

- são **ensinadas nos vídeos públicos** do próprio autor;
- já estão **extraídas neste repositório** com citação direta e rótulo de confiança (`pesquisa/metodologia_regras.md`, 10 seções, 51 de 54 vídeos);
- e parte delas **já vive no motor** desde a onda 3 — as faixas de convicção e o gate de magnitude do caso WINFUT estão em `motor/sinais.py`.

Fica de fora apenas **marca, nome comercial e identidade visual de terceiros**, que é outra coisa e ninguém pediu.

**Isso vira a peça P4**, e traz uma disciplina que é o núcleo dela: cada regra entra no código com o rótulo da fonte. `CONFIRMADO` vira código; `IMPRECISO` vira **parâmetro**, nunca constante cravada; `AUSENTE NA FONTE` não é implementado como regra do método. O caso exemplar já tem precedente no repositório — "exaustão" não aparece em nenhum dos 54 vídeos, e o `DetectorExaustao` foi reclassificado como componente genérico de order flow em vez de ser apresentado como regra do autor.

E a API expõe o rótulo junto do valor. Um painel que mostra "direcional ≥70%" **e** admite que a fonte oscila entre 70 e 75 vale mais que um que finge precisão que a fonte não tem.

### Uma divergência deliberada, registrada e não escondida
A fonte codifica direção em **verde/vermelho/amarelo**. Este projeto usa **azul=compra / vermelho=venda**, com verde e âmbar no segundo canal. A razão é acessibilidade: verde↔vermelho colapsa em deuteranopia e protanopia (~8% dos homens), e a medição em `tests/test_ui_tokens.py` mostra que o par azul/vermelho separa 147 pontos no canal azul. **Faixas, limiares e rótulos vêm do método; a codificação de cor, não.**

### Decisão tomada no lugar de pergunta
O briefing recomenda **C++20/Linux + C#/.NET/Avalonia**. Não vou reescrever a stack: o próprio briefing classifica essa recomendação como "uma decisão nova de engenharia, não uma inferência", o pedido foi pela **interface visual**, e trocar de stack descartaria o motor e 796 testes verdes. Fica **Python + PySide6** — e V1 (superfície inteiramente desenhada) já é verdade aqui: `ui/base/painel_denso.py` desenha tudo em `QPainter` sobre backing store, sem um widget de SO na área de dados.

---

## A barra

**`bar/` — 25 capturas reais de Profit Pro / Bookmap já no repositório**, com o inventário funcional documentado em `bar/barra_profit_pro.md`.

Escolhida porque é externa, está em disco, e um crítico consegue abrir a nossa saída e a referência lado a lado no mesmo enquadramento. É a mesma barra que o projeto usa desde a onda 1, então o resultado é comparável com o histórico.

**Dois testes, e o segundo sai do próprio briefing:**

1. **A/B cego de composição.** O crítico recebe nosso PNG e um recorte da referência em enquadramento equivalente, sem rótulo de lado, e escolhe qual lê como terminal institucional. Empate conta como derrota nossa.
2. **Sobrevivência à transmissão (V6).** O PNG é reduzido e recomprimido em JPEG na faixa de uma chamada de vídeo; os números críticos têm de continuar legíveis. É medição, não gosto — roda por comando (T0).

Se a barra cair na primeira rodada, ela estava baixa e sobe.

---

## Roteamento

Modelos disponíveis neste harness: `opus`, `sonnet`, `haiku`, `fable`. Mapa: **T3 = opus**, **T2 = sonnet**, **T1 = haiku**, **T0 = comando, sem modelo**.

| Papel | Tier | Por quê |
|---|---|---|
| Lead / orquestração | T3 | uma instância, maior alavancagem |
| Construtor de peça visual/nova | T3 | é peça de gosto: um construtor barato perdendo 4 rodadas custa mais que um caro ganhando em 1 |
| Construtor de montagem/fiação | T2 | estado-alvo mais especificado |
| **Crítico de composição** | **T3** | regra zero — crítico fraco aprova cedo e cancela o método |
| Crítico de legibilidade sob transmissão | T0 → T1 | o veredito é um número; comando roda, modelo pequeno relata |
| Passada de coesão | T3 | artefato é visual |

Reserva: ~1/4 do orçamento para os críticos. Não é pool — juízo fica com ela.

---

## Decomposição

Menores peças julgáveis em separado. P1 e P2 criam arquivos novos (sem colisão, rodam em paralelo); P3 monta e por isso vem depois.

| Peça | O que é | Parâmetros | Barra específica |
|---|---|---|---|
| **P1 — Matriz de estado** | A camada intermediária visível: o que o motor derivou, numa superfície densa só. É o parâmetro mais distintivo do briefing (V4). | V1, V2, V4 | `09_tape_reading_*.png`, `01_times_trades_*.png` |
| **P2 — HUD de contexto** | Faixa heads-up: medidores de pressão, farol de 5 estágios do motor, placar de confluência. | V1, V2 | `06_medidores_agressao_*.png`, `04_ranking_corretoras_*.png` |
| **P4 — Regras de leitura no código** | Regime estrutural, velocímetro com persistência, placar estatístico, Linha Azul, macro×micro em escalas separadas, gestão de risco (3 stops, mão cheia/mínima). Cada uma com rótulo de confiança na API. | metodologia | fidelidade auditável à fonte, via `pesquisa/regras_no_codigo.md` |
| **P3 — Composição e cadeia** | Workspace que torna a cadeia V3 legível, sem cromo de janela (V5), sobrevivendo à transmissão (V6). | V3, V5, V6, V7 | A tela inteira contra `02_superdom_c.png` e `09_tape_reading_b.png` |

P1, P2 e P4 rodam em paralelo (arquivos disjuntos: `ui/paineis/matriz.py`, `ui/paineis/hud.py`, `fluxopro/metodologia/`). P3 monta, e por isso vem depois.

**Sobreposição conhecida P2 × P4:** os dois tocam "placar de confluência" — P2 constrói a *exibição*, P4 a *computação*. P2 vai calcular inline a partir do `MotorSinais`; P4 promove a componente de primeira classe. A onda 2 reconcilia. Registrado agora para não virar descoberta tardia.

---

## Linha de base V6 medida ANTES de construir — e ela já achou uma lei de design

`scripts/transmissao.py` degrada um PNG como um canal degradaria: reescala a 0,72 e recomprime em JPEG a qualidade 40, depois devolve ao enquadramento original para a comparação ser honesta. **Não é um simulador de codec** e o script diz isso de si mesmo; é um proxy grosseiro de duas perdas que qualquer transmissão impõe. Rodado sobre a tela da Fase 1: 94 KB → 32 KB no canal (34%).

O que sobreviveu e o que não:

| Elemento | Portador | Sobreviveu? |
|---|---|---|
| Preço grande da strip, Δdia, variação % | 15px, `--text-primary` | **Sim**, sem esforço |
| Bandas direcionais do DOM (azul/vermelho) | bloco de cor + posição | **Sim**, é o portador mais robusto |
| Quantidades sobre as barras de profundidade | 11px `--text-primary` | **Sim**, no limite |
| Setas ▲▼ do tape | glifo | **Sim** |
| **Dígitos estáveis do preço** (`5.08`+`6,5`) | 11px **`--text-muted`** (3,94:1) | **Não** — o prefixo vira borrão |
| Carimbos de hora do tape | 11px `--text-secondary` | **Marginal**, começa a quebrar |

**Lei que isso impõe às três peças:** informação carregada por *contraste baixo em corpo pequeno* não existe do outro lado do canal. Contraste baixo continua válido para o que é **redundante por construção** — e o dígito estável é exatamente isso, o prefixo já está contido no número que o olho leu inteiro —, mas nenhum dado que só ele carregue pode ficar ali. Cor em bloco e posição são os portadores que atravessam; texto miúdo de baixo contraste, não.

Achado por medição, não por opinião, e antes de o primeiro pixel novo ser desenhado.

---

## Rodadas

| Onda | Peça | Papel | Modelo | Veredito |
|---|---|---|---|---|
| 1 | P1 — Matriz de estado | construtor | opus | ✅ entregue — `matriz.py` (1.298 linhas), 37 testes, razão cheio/incremental **17,9×** |
| 1 | P1 | **crítico** | opus | — em curso (A/B cego + canal + código) |
| 1 | P2 — HUD de contexto | construtor | opus | ✅ entregue — `hud.py`, 42 testes, razões **8,7×** (HUD) e **16,3×** (players) |
| 1 | P2 | **crítico** | opus | — em curso |
| 1 | P4 — Regras de leitura | construtor | opus | ✅ entregue — pacote `metodologia/`, **42 regras · 16 parâmetros · 9 recusas**, 52 testes |
| 1 | P2 | **crítico** | opus | ⚠️ **GANHOU — e por isso a barra sobe** |
| 2 | P1 — Matriz de estado | construtor r2 | opus | ✅ entregue — 37→**52 testes**, razão **38,7×**, suíte 942 |
| 2 | P1 | **crítico r2** | opus | ❌ **PERDEU** — banda de detecções é 60% da tela e não escaneia |
| 3 | P1 — Matriz de estado | construtor r3 | opus | ✅ entregue — 52→**81 testes**, banda 60%→44%, suíte **989** |
| 3 | P1 | **crítico r3** | opus | ❌ **PERDEU** — o mapa banda→regra não é auditado, e está errado |
| 4 | P1 — Matriz de estado | construtor r4 | opus | ✅ **o mapa foi deletado** — 81→92 testes, suíte **1.003** |

### RODADA 4 DE P1 — a correção estrutural, e o ataque deixou de ser expressável

`REGRAS_DA_BANDA` **foi deletado**. No lugar, a UI declara `CAMPOS_DA_BANDA` — nomes de campos de `ConfigMotorSinais`, que são fatos sobre o **código**, não sobre a fonte — e a regra vem do registro por `regras_do_campo(campo)`.

**A qualificação do nome é a parte fina:** `janela_micro_ns` existe em `ConfigMotorSinais` **e** em `ConfigMacroMicro`. Casar pelo nome curto faria a tela reivindicar o aval que `macro_micro.janela_micro` deu a **outro componente** — *"a mesma falha da MAGNITUDE, pelo lado oposto"*. Por isso a busca é pelo nome qualificado.

Três coisas passaram a constranger a declaração:

| Constrangimento | O que trava |
|---|---|
| `_validar_campos()` no import | recusa nome que não seja campo real do dataclass |
| Teste que lê `motor/sinais.py` com **`ast`** | exige que a união dos campos declarados seja **exatamente** o conjunto de botões que o motor consulta — botão novo sem procedência reprova, nome morto reprova |
| `BANDA_ESTAGIO` **não é escrita** | é `tuple(f.name for f in fields(ConfigMotorSinais))`; o farol é a confluência inteira, logo seu conjunto é superconjunto de todos, e **por construção a procedência dele nunca pode ser melhor que a de nenhuma outra banda** — o invariante que teria pego o defeito da r3, agora um teste |

**A mutação da r3 deixou de ser expressável**: não existe mais um único id de regra em código executável da UI (`test_a_ui_nao_escreve_id_de_regra_nenhum`). Ele rodou três análogos, todos vermelhos. E o próprio teste novo pegou **um segundo id digitado que ele não tinha visto** em `_rotulo_faixa`.

**A gramática do chip virou `§ <PIOR> k/n`** — pior procedência e cobertura numa string só, uma caneta só, pela lei da r2. E `SEM_REGISTRO` passou a ser a **pior** gravidade, não a melhor: *"olhamos e o registro diz por escrito que a fonte não tem" é auditável; "ninguém olhou" é buraco na auditoria.* Resultado com o registro de hoje: `1/20`, `1/5`, `0/7`, `0/2`. Nas palavras dele: **"chato de ler, e verdadeiro."**

No canal, **não há mais nenhum chip verde na tela**. O que a transmissão melhor preserva agora é `§ S/ REGISTRO 0/7` — âmbar, e verdadeiro.

**Regressão que ele introduziu e corrigiu sozinho:** a derivação varria as 42 notas por botão por banda a cada quadro — 34 varreduras, **31 ms de quadro cheio** contra os 16 do orçamento. Memoizada (o registro é imutável após o import): cheio 4,20 ms, incremental 0,203 ms, razão **20,7×**.

**A perda que ele declarou:** *"Perdi o ganho retórico da rodada 3 — 'as 33 regras avalizadas ganham superfície' — porque ele estava construído sobre uma afirmação falsa."* Trocou retórica por cobertura explícita.

**Aresta de aquecimento fechada:** abaixo de 30 amostras a fatia **não é publicada** — sai `—`, sem tinta e sem régua. Mesma regra do `PASSA SEM MEDIR`. E a tinta da coluna passou a marcar **só a linha rara**: antes a barra era proporcional à fatia, então a linha com mais tinta era a do tipo mais **comum** e a exceção ficava com o traço mais curto — o oposto do que a coluna existe para fazer.

### RODADA 3 DE P1: o crítico não aceitou a palavra, refez as mutações — e inventou uma terceira

Ele **reproduziu as duas mutações declaradas** e confirmou: 3 testes vermelhos cada, asserções realmente ancoradas no zero desenhado, espião cobrindo `fillRect`/`drawLine`. **r1 e r2 fechados**, registrado.

Depois fez a **mutação 3, dele**: trocou `BANDA_ESTAGIO` de `dominancia.nao_e_gatilho` para `risco.mao_cheia` — regra de **tamanho de posição**, nada a ver com confluência. Resultado: **81 passed**. O mapa banda→regra é inteiramente livre; o único teste que o toca é `assert REGRAS_DA_BANDA[BANDA_MAGNITUDE] == ()`, tautologia sobre um literal digitado.

**E o mapa está errado onde mais custa.** O farol de 5 estágios — o maior veredito da tela — recebe chip verde `§ CONFIRMADO`. Mas os estágios saem das condições 2 e 3, e o próprio `motor/sinais.py:22-30` declara que a condição 2 é *"uma reconstrução funcional"* e a 3 usa `janela_micro_ns`, que o registro marca `AUSENTE_NA_FONTE`.

> A banda MEDIDAS, movida **pela mesma janela micro**, exibe honestamente `§ S/ FONTE`. Duas bandas, o mesmo parâmetro `AUSENTE_NA_FONTE`, **chips contraditórios na mesma tela.**

**A ironia que fecha o argumento:** o docstring de `procedencia_metodologica` argumenta que *"um mapa escrito na UI seria uma SEGUNDA fonte de procedência, que envelhece em silêncio"* — e `REGRAS_DA_BANDA` é exatamente esse dict, **370 linhas abaixo**, sem validação e sem teste. A peça recusou o mapa na banda de detecções pelo motivo certo e o reintroduziu nas bandas do motor.

**E no canal:** o elemento que melhor atravessa é justamente o chip verde `§ CONFIRMADO` — *a transmissão preserva precisamente a afirmação falsa*, com selo de auditoria por cima.

### Dois achados colaterais que valem além de P1
- **A recusa da MAGNITUDE estava certa, e ele provou:** `regras.py:568-576` já pendura `magnitude_relativa_minima=0.25` em `velocimetro.normalizacao_winfut`; pendurar também o 0,60 do `MotorSinais` faria o registro afirmar **dois cortes contraditórios sob a mesma regra**, e `_validar()` não pegaria. **Buraco de P4:** o 0,60 é limiar vivo e calibrável **ausente de `PARAMETROS`**, e `_validar()` estruturalmente não pode cobrar — valida só o que foi declarado.
- **Aresta de aquecimento:** `fracao_tipo = n/total` faz a 1ª detecção sair 100%, e **nenhuma das 5 primeiras pode cruzar o corte de raridade** — um clip institucional na abertura aparece como a coisa mais comum da tela.

### P1 rodada 3 — integridade de teste provada por MUTAÇÃO, não afirmada

Ele não disse "os testes agora cobrem geometria". Ele mutou e mediu:

| Mutação | Resultado |
|---|---|
| `sentido = -1 if lado >= 0 else 1` em `_desenhar_eixo_dominancia` | **3 testes vermelhos** |
| lado invertido em `_barra_bipolar` | **3 testes vermelhos**, incl. `test_sem_cor_a_posicao_continua_dizendo_o_lado` |

E o desenho do teste é o que faz isso durar: as asserções são feitas **contra o zero desenhado** — a linha de centro que o próprio painel pinta — e não contra coordenadas copiadas do código de produção. *Mover a coluna não quebra o teste; inverter o lado, sim.* Mandei o crítico refazer as duas mutações em vez de aceitar a palavra dele.

O furo do rótulo estático também fechou: `test_a_direcao_e_recuperavel_do_texto_sozinho` agora exclui `« VENDA`/`COMPRA »` do conjunto, exige ausência da palavra oposta, e roda o caso espelho.

### O eixo de exceção, e os três portadores
Cada linha carrega a fatia que o seu tipo representava na sessão **no instante em que chegou**. Abaixo de 20% a linha é exceção e recebe **três portadores independentes**: régua de 3px em âmbar na borda (área chapada — o material que atravessa o canal), o número em âmbar, e a barra de fatia. *Tire qualquer um e a exceção continua achável.*

Verifiquei varrendo a coluna no retrato: 33, 33, 33, **2**, 33, 32, 32, 32, 31, **68**. As duas anomalias saltam.

**A banda caiu de 24 para 10 slots** — 60% → 44% da superfície. A frase dele: *"dez linhas continuam sendo estado; vinte e quatro eram log, e para log existe a trilha do rodapé."*

### As regras avalizadas ganharam pixel
Toda banda do motor passou a declarar a própria procedência, no mesmo vocabulário das detecções e lida de `REGRAS`: `§ CONFIRMADO` na confluência, `§ IMPRECISO` na dominância (**vale o pior elo, nunca a média**), `§ S/ FONTE` nas medidas (macro e micro são CONFIRMADO, mas o *tamanho* da janela micro é `AUSENTE_NA_FONTE`), `§ S/ REGISTRO` na magnitude.

O prefixo `§` nasceu de uma colisão que o retrato expôs: `CONFIRMADO` é ao mesmo tempo o último estágio do motor e o rótulo de maior confiança do registro, e os dois apareciam na mesma banda, do mesmo tamanho.

### A recusa que mais vale nesta rodada
Ele **não** pendurou a banda MAGNITUDE em `velocimetro.normalizacao_winfut`, embora seja `CONFIRMADO` e trate do mesmo fenômeno — porque é outro componente, com outro default (0,25 contra 0,60 do `MotorSinais`). *"Pendurar seria pegar emprestado um aval que ela não deu."* `§ S/ REGISTRO` é a verdade: o gate do WINFUT é engenharia interna deste projeto. Com teste fixando `REGRAS_DA_BANDA[BANDA_MAGNITUDE] == ()`.

**Pendência que ele declarou em vez de meio-fazer:** não renderizou as leituras de `LinhaAzul`, `MacroMicro`, `Estrutura` e `Placar` — seria a resposta máxima ao "0% às 33 regras", mas o `Placar` precisa de fiação de votos que não existe em `SessaoFluxo`. *"Isso é uma peça, não um ajuste."* Fica para o lead decidir.

### RODADA 2 DE P1: perdeu — e o achado é estrutural, não cosmético

**O que o crítico verificou FECHADO** (a rodada 2 funcionou, nada disso volta): as ressalvas atravessam o canal inteiras, ele **procurou veredito órfão de ressalva e não achou**, a procedência é derivada do registro sem dict na UI, e o estado é O(1) no número de eventos.

**A lacuna**, medida em pixel: a banda DETECÇÕES ocupa 60% da tela com 24 linhas de **largura de barra 32 e cor (125,136,150) idênticas**, sem cabeçalho de coluna, sem unidade, sem ordenação — e a única linha anômala (`CLIP INSTIT.`) sai tipograficamente igual às 23 `EXAUSTÃO`. A barra pergunta "dá para achar a linha anômala varrendo a coluna?" e a resposta é não; a referência, um grid feio de tema claro, dá.

### O achado mais fundo do ciclo inteiro

Respondendo à pergunta que eu tinha plantado sobre o `0 MÉTODO · 338 GENÉRICAS`, o crítico enumerou os dois lados:

| Lado | Conteúdo |
|---|---|
| Registro `metodologia/regras.py` | **42 regras, 33 implementadas**, 8 famílias vivas: dominância, estrutura, linha azul, macro/micro, placar, risco, velocímetro |
| `TipoDeteccao` que a banda exibe | 6 membros: `exaustao` e `escora` são `AUSENTE_NA_FONTE`; os outros **quatro nem existem no registro** |

Conclusão dele, e é dura: *"a peça deu 60% da sua superfície ao único fluxo que o registro não avaliza, e 0% às 33 regras que ele avaliza."* O ramo `MÉTODO` do chip é **inalcançável a partir de dado de produção** — e o teste que o exercita alimenta a string `"LINHA_AZUL"`, que sequer é membro de `TipoDeteccao`.

O zero é honesto sobre a banda. O que ele anuncia é que a banda está apontada para o conteúdo errado.

### E um buraco de integridade de teste que vale para a peça toda

O `PainterEspiao` intercepta **só `setPen` e `drawText`**. `grep fillRect tests/test_ui_matriz.py` → vazio. Consequência que o crítico mediu: **inverter `sentido` em `matriz.py:962` desenharia o cursor do eixo do lado errado e os 59 testes continuariam verdes.** Eixo, régua, barras de medidas e barra de confiança não têm uma asserção sequer. E o `any("COMPRA" in t)` de outro teste é satisfeito pelo rótulo estático do polo — ele confirmou rodando com `direcao=-1`.

Geometria que nenhum teste vê é geometria que pode inverter em silêncio. Mandado fechar como restrição, não como escolha.

*(Nota colateral: `tests/test_ui_desempenho.py` não menciona `matriz` em nenhuma linha — metade do comando que vinha sendo rodado não exercitava a peça.)*
| 2 | P2 — HUD de contexto | construtor r2 | opus | ✅ entregue — suíte **956**, carimbo na imagem |
| 2 | P2 | **crítico r2** | opus | ❌ **PERDEU** — mesma mentira gráfica, outro andar |
| 3 | P2 — HUD de contexto | construtor r3 | opus | ✅ **tirou a grandeza da geometria** — suíte **1.037** |
| 3 | P2 | **crítico r3** | opus | ❌ **PERDEU** — guarda é teatro; catraca inverte leitura no TEMPO |
| 4 | P2 — HUD de contexto | construtor r4 | opus | ✅ **nenhuma barra com escala sobrou no módulo** |
| — | Integração final | lead | — | ✅ parcelas do dia derivadas do retrato + 4 testes |

### RODADA 4 DE P2 — a forma morreu

**O guarda-teatro, consertado na raiz.** A causa era a violação do princípio dele mesmo: o teste media contra um marco que o desenho não usa. Extraiu `x_costura(taxa)` e passou **desenho e medição** a usá-la; depois trocou a asserção por linearidade contra os **dados** (`desvio ≈ (taxa − 0,5) × largura`, ±1px), não contra a aritmética do produto. Varreu de novo: **2, 3, 4, 5 e 6px agora reprovam** — o 3px, que era o único que passava, morreu.

> **Nota de método que vale para qualquer harness de mutação:** a primeira tentativa dele usou `/tmp`, que o Git Bash e o Python do Windows resolvem para lugares diferentes. As mutações **nunca chegaram ao arquivo** e cinco falsos "passou" apareceram. *"Um harness de mutação que não muta reporta o código como perfeito."* (Eu mesmo tropecei nessa exata pedra mais cedo neste ciclo, com um script de diagnóstico.)

**A catraca saiu.** Ele reproduziu o par antes de mexer — **133px → 33px, 4,0×, mesmo saldo** — e removeu a necessidade da escala, como nas r1 e r3: o saldo em lotes virou **número**, a geometria virou a **parcela compradora do pregão**, limitada a 0..100%. `DEGRAUS_ESCALA`, `escala_para`, `_escala_dia` e a barra bidirecional inteira saíram. **Não há mais uma única barra com escala no módulo.**

```
t0  +2.200 de  10,0k  ->  costura +32 px
t1  +9.000 de 100,0k  ->  costura +13 px   (o pico)
t2  +2.200 de  10,0k  ->  costura +32 px
t0 e t2, pixel a pixel: IDÊNTICOS
```

E o que a barra passou a dizer virou propriedade real: `+2.200 de 10,0k` desenha +32px (61% comprador); `+2.200 de 100,0k` desenha +2px (51%). **Mesmo saldo, forças diferentes** — a versão com catraca desenhava as duas igual.

**A objeção que ele levantou contra si mesmo:** as duas barras do HUD ficaram com a **mesma forma**, de propósito, e ele escreveu o teste afirmando a **igualdade**. O argumento: duas barras parecidas só enganam quando escondem eixos diferentes, que era o defeito 1; estas estão no mesmo eixo e diferem só no horizonte, então compará-las virou leitura possível e certa. E o teste antigo que afirmava que eram diferentes **passava por acidente** — a banda do dia estava vazia por falta de dado.

**Portão intermitente, diagnosticado em vez de afrouxado.** 1 reprovação em 5, e não era regressão: o quadro cheio ficou ~15% mais barato (5 `drawLine` a menos), o **numerador** encolheu, e a razão caiu de 5,7× para 5,5× contra o limite de 5,0. Com 10% de folga, a contenção das outras suítes rodando em paralelo cruzava o limite. Trocou mediana por **mínimo** nos portões do arquivo dele: *"contenção só adiciona tempo, então a menor amostra mede o desenho e não o vizinho. Baixar o limite teria trocado um portão instável por um portão cego."*

### A lacuna que ele não podia fechar, e como eu fechei
Ele achou que **no app rodando a barra do dia saía vazia** — `janela.py` não passava as parcelas — verificou que a degradação era honesta (0px pintados, nunca um 50/50 falso) e deixou o endereço exato com três linhas de correção.

Não apliquei as três linhas. Elas leriam `sessao.delta.volume_comprador_sessao` e o par vendedor: **três escalares lidos da thread do Qt enquanto a thread da fonte escreve, com uma invariante COMPOSTA entre eles** (`total == comprador + vendedor + não atribuído`). Uma leitura rasgada daria parcelas que não somam o total, e a barra desenharia uma proporção que nunca existiu — exatamente o princípio que P3 já tinha estabelecido nesta janela.

Derivei do `Instantaneo`, que é montado sob o lock, por duas equações:
```
comprador + vendedor = volume − não_atribuído
comprador − vendedor = delta
```
A divisão por 2 é exata porque soma e diferença têm sempre a mesma paridade. Com 4 testes, incluindo o de retrato inconsistente: se a invariante quebrar rio acima, a parcela sai **zerada em vez de negativa** — mesmo critério do `PASSA SEM MEDIR`.
| — | P3 — Composição | **crítico** | opus | ⚠️ **ganhou o A/B, perdeu na lei do canal** |
| 2 | P3 — Composição | construtor r2 | opus | ✅ **achou o defeito no próprio escopo primeiro** — 42 testes (40+2 xfail) |

### P3 rodada 2 — aplicou a crítica em si antes de apontar para os outros

**O defeito do crítico existia no conduto dele.** `PICO DO CANO 8%` era veredito sem denominador — 8% de quê? O teto do buffer não estava em lugar nenhum da tela. Agora sai `7% de 4.096` **num `drawText` só**, mesma fonte, mesma caneta: *"o canal não tem como levar um e deixar o outro"*. E o caminho que devolve só `8%` **não existe**. Quando não coube, ele alargou a coluna de 96 para 120 — *"cedeu a largura da coluna, não o corpo da escala."*

Verifiquei no degradado: `7% de 4.096` chega inteiro e legível.

**A asserção generalizável:** o espião de `QPainter` passou a registrar corpo, peso e caneta por `drawText`, e o teste reprova quando o token de escala renderiza com `px` menor **ou** contraste WCAG menor que o veredito que ele qualifica — **recalculando a luminância do token, nunca tabelada.**

**Duas sondas `xfail(strict=False)` apontando para escopo alheio**, com o endereço exato do conserto no próprio `reason` — conferi rodando com `-rx`:

> `de 30,0k` desenha em 10px/`TEXT_MUTED` (3,94:1) enquanto o veredito `▲ 51%` desenha em 13px/`BUY` (6,92:1) — menor **E** mais apagada, as duas coisas que o canal come primeiro. 32% de retenção contra 39% do veredito.

Elas não tocam nos arquivos dos outros; quando a correção entrar viram XPASS e podem ir para `strict`. É a forma mais honesta de entregar um achado que cruza arquivos sem invadir a peça de outro construtor.

**E ele leu os próprios números com disciplina.** A caixa `saldo_escala` virou vazia porque o outro construtor removeu o `±3,2k`, e a razão saltou para 271%: *"ruído de JPEG sobre energia quase nula, não uma melhora — a leitura certa é 'o token saiu de cena'."* Recusou ler ruído como ganho.

**O que continua errado e ele declarou não ser dele:** no mesmo degradado, `▼ 51%` chega perfeito e `de 28,8k` chega borrão. Mora em `hud.py`, e é o que P2 r4 está fechando.

### CRÍTICA DE P3: ganhou o A/B — e não por empate

Sobre a referência (`02_superdom_c.png`, o SuperDOM da Nelogica): *"o veredito de B — `Forte Tendência de Alta ▲▲▲` — é **oráculo puro**: sem limiar, sem escala, sem fonte."* A cadeia do candidato é apontável sem legenda, não há cromo de SO, e cada número carrega procedência e o corte de produção ao lado do calibrado.

**As três afirmações fortes da peça, todas verificadas POR MUTAÇÃO:**

| Afirmação | Mutação aplicada | Resultado |
|---|---|---|
| A cadeia é geometria, não legenda | trocar a geometria real pelos fatores de esticamento copiados | **reprovou** em 1700×1000 (`assert 669 >= 700`) + o teste de cobertura |
| O trilho não republica veredito | fazer o trilho publicar `74%` | **reprovou** (`'%' not in ...`) |
| Relógio único | — | `ponte.ler()` só em `janela.py:1072`, com teste varrendo `paineis/*.py` |

E o carimbo: derivado por `dataclasses.fields`, **nenhum número digitado**, com `("","")` quando não há calibração nem simulador — carimbo permanente vira moldura e para de ser lido.

### A lacuna: a escala vive no portador que o canal come primeiro

Ele **inventou uma medida** para provar o que nenhuma inspeção a olho resolveria — energia média do Laplaciano por região, antes e depois da recompressão:

| região | retenção |
|---|---|
| escala `±3,2k` | **17%** |
| veredito `▲ +2,4k` que ela qualifica | 32% |
| escala `de 30,0k` | **30%** |
| veredito `▲ 51%` que ela qualifica | 38% |
| régua de ticks | **27%** |
| badge `§ S/ REGISTRO 1/5` | 35% |
| tarja do carimbo | **47%** |
| `0,525 (prod. 0,70)` | 37% |

**Em três bandas a ressalva retém menos que o veredito que ela qualifica.** E o detalhe pior: no zoom 7×, `±3,2k` **não some — vira mush legível como `12,2k`**.

> Escala que desaparece é perda. Escala que **sobrevive errada** é mentira.

A sentença dele: *"o time já sabe construir o portador resistente; só não o aplicou onde a régua vive."*

### O instrumento virou ferramenta do repositório
Transformei a medida do crítico em `scripts/retencao.py`, com modo `--par RESSALVA=VEREDITO` que **afirma a lei do canal** e sai com código 1 quando ela é violada. Uma medida que vive na cabeça de um auditor precisa ser redescoberta a cada rodada.

Rodando sobre a composição atual, reproduzi a tarja em 44,6% (ele mediu 47%; as caixas são desenhadas à mão). E o script me pegou num defeito meu na primeira versão: com arredondamento inteiro, 31,8% e 32,3% imprimiam ambos "32%" e o veredito de violação parecia bug. Passou a uma casa decimal, e abaixo de 2 pontos percentuais o veredito é `MARGINAL`, não `VIOLADA` — **emitir do script um oráculo sem margem seria cometer o defeito que ele existe para caçar.**

### RODADA 3 DE P2: as 4 alegações se sustentam — e ele achou duas coisas piores

O crítico **remediu a coluna** e achou **mais** do que o construtor alegou: 14 valores absolutos distintos, maior 19px, menor não-nulo 1px, **razão 19×** contra os 16× reportados. Confirmou largura fixa (254px nas 20 linhas), volume fora da geometria, `PainelPlayers` sem escala nenhuma, e a **defesa vernier atravessando o canal** — a espinha continua legível no JPEG degradado. O ranking está resolvido.

#### 1. O teste-guarda é TEATRO, provado por mutação

Ele reintroduziu o piso da r2 — o defeito que a docstring do teste diz que ele "teria reprovado" — e `test_costuras_distintas_para_players_distintos` **passou**.

A causa é cirúrgica: `_medir_costura` mede contra `barra.center().x()` (`left+(w-1)//2`) enquanto o corte real é `left+round(taxa*w)`. O off-by-one rebaixa o menor não-nulo de 3 para 2, e `16 >= 8*2` passa **raspando**. Ele varreu os pisos: **4px reprova · 5px reprova · 6px reprova · 3px passa.**

> *"O teste pega qualquer piso menos o único que já existiu no produto."*

Quem reprovou a mutação foram dois **outros** testes. O guarda nomeado não trabalha. Lição de classe: **o teste mediu contra um marco que o código de produção não usa** — exatamente o princípio que o próprio construtor aplicou certo quando fez o recorte vir de `rect_barra_saldo()`.

#### 2. Terceira ocorrência da mesma forma ⇒ DECISÃO DE LEAD

Ele mediu o par que ninguém tinha medido:

```
saldo +2.200 → escala 2.500 → fração 0,880
pico de 9.000 → escala sobe para 10.000 (a catraca nunca encolhe)
saldo volta a +2.200 → fração 0,220
        MESMO SALDO, comprimento 4,0× menor
```

E o único portador da mudança é o `±2,5k` de 10px que o canal apaga.

O argumento de r2/r3 — *"perder o rótulo custa a unidade do eixo, não uma leitura errada"* — **não se sustenta**, porque a comparação não é espacial e sim **temporal**: a segunda barra do par é a lembrança do operador do quadro de vinte minutos atrás. Ele vê o trilho do dia encolher a um quarto e conclui "a pressão desabou", quando o saldo é idêntico e o que mudou foi o eixo.

É o defeito da r1 deslocado do espaço para o tempo. **Terceira ocorrência** ⇒ o protocolo manda parar e re-decidir no nível do lead, e foi o que fiz: mandei igualar o padrão dele mesmo — nas r1 e r3 ele matou essa forma **removendo a necessidade da escala**. Não vale mitigar uma terceira vez com rótulo maior. Ou o `SALDO DIA` deixa de depender de escala móvel, ou a escala vira **geometria visível** que o canal não apaga.

**Higiene verificada por mim:** a mutação do crítico saiu do disco (`grep max(3, abs` vazio, 59 passed). Este projeto já pagou por harness de mutação morto deixando defeito em disco; confiro sempre.

---

---

# CONTINUAÇÃO — terminar todas as fases (pedido do dono, 22/08)

Publicado o ciclo anterior em `94788fb`. O dono pediu o **projeto inteiro, todas as fases, sem interrupção**. O plano de `design/direcao_visual.md` §6 tem as fases 2, 3 e 5 abertas, e há uma lacuna estrutural maior que qualquer uma delas.

## Onda A — quatro construtores em paralelo, arquivos disjuntos

| Peça | Escopo | Arquivos |
|---|---|---|
| **F2 — a peça que diferencia** | Footprint com leitura diagonal, Volume Profile lateral com POC/VAH/VAL no mesmo eixo de preço, Delta acumulado no mesmo eixo de tempo | `ui/paineis/footprint.py`, `perfil.py`, `delta_acumulado.py` |
| **MET — a lacuna estrutural** | Ligar `fluxopro/metodologia/` no pipeline vivo | `app/sessao_fluxo.py`, `app/config.py`, `metodologia/*` |
| **F5 — bookmap e replay** | Heatmap de liquidez e replay com tarja de janela | `ui/paineis/bookmap.py`, `replay.py` |
| **XF — fechar a sonda** | A régua de dominância em 10px contra veredito em 14px | `ui/paineis/matriz.py` |

**MET é a mais importante das quatro**, e não é uma fase do plano de UI. O pacote de metodologia foi entregue **isolado**: 42 regras, 33 implementadas, 9 componentes — e **nada alimentado por evento nenhum**. Foi o crítico que diagnosticou: *"a peça deu 60% da sua superfície ao único fluxo que o registro não avaliza, e 0% às 33 regras que ele avaliza."* O placar lê `0 MÉTODO` e **não pode ler outra coisa** enquanto os componentes não receberem trades. Fechar isso é o que torna as regras que o dono mandou trazer para dentro visíveis de fato, e não uma listagem de registro.

Cada construtor recebeu as quatro leis medidas no ciclo anterior como restrição dura, não como sugestão — a lei do canal, a distinção entre escala que some e escala que mente, a regra de tirar a grandeza da geometria, e a proibição de teste que mede contra marco que o desenho não usa.

**A armadilha específica do bookmap** foi nomeada no briefing dele: um heatmap de liquidez é, por definição, uma estrutura que cresce com o tempo do pregão — a nona casa do defeito que este projeto encontrou em oito arquivos. O teste de retenção foi pedido junto com o código, não depois.

## Onda B — depois de A
Fase 3 (docking, `saveState`, os 4 workspaces de fábrica, `Ctrl+1..9`, regra da janela órfã, Sala de Controle, densidades a quente) **mais a montagem de tudo em `janela.py`** — um dono só para o arquivo, porque quatro peças novas entrando na composição ao mesmo tempo é colisão garantida.

## Onda C
Críticos adversariais em A/B cego sobre o que sair de A e B, no mesmo protocolo: barra em `bar/`, canal medido, mutação obrigatória, veredito binário.

---

# ENCERRAMENTO DO PRIMEIRO CICLO

**Suíte final:** `python -m pytest tests/ -q` → **1.044 passed, 2 xfailed**. Partida em 796.

## A barra usada, e por quê
`bar/` — 25 capturas reais de Profit Pro / Bookmap já no repositório, com inventário funcional documentado. Escolhida por ser externa, estar em disco, e permitir A/B cego no mesmo enquadramento. **Subiu uma vez**, quando P2 venceu na r1 contra `06_medidores_agressao`: aquela referência responde 1 das 3 perguntas da peça, e vencer na primeira rodada é sinal de barra baixa.

Ao segundo teste — sobrevivência ao canal — o ciclo acrescentou um terceiro instrumento, `scripts/retencao.py`, nascido de uma medida que um crítico inventou no meio da auditoria.

## Onde chegou
| Peça | Rodadas | Fim |
|---|---|---|
| P1 — Matriz de estado | 4 build + 3 crítica | mapa digitado **deletado**; procedência derivada do registro, com prova por mutação |
| P2 — HUD de contexto | 4 build + 3 crítica | **nenhuma barra com escala** no módulo; guarda-teatro consertado na raiz |
| P4 — Regras de leitura | 1 build | 42 regras, 16 parâmetros, **9 recusas**, invariantes validadas no import |
| P3 — Composição | 2 build + 1 crítica | **ganhou o A/B** contra o SuperDOM; cadeia é geometria, provada por mutação |

## A última lacuna não fechada — o handoff
Uma sonda `xfail` viva, com endereço exato: **os cortes da régua de dominância desenham em 10px enquanto o percentual que eles ancoram desenha em 14px** (`matriz.py`). Quando corrigida, vira XPASS e pode ir para `strict`.

E uma **discordância de critério declarada, não resolvida**: P2 recusou aplicar o mesmo tratamento ao `de 16,5k` da agressão, argumentando que ali perder o rótulo custa o *qualificador* e não a *leitura*, porque todas as costuras estão sempre no mesmo eixo. É discordância sobre o critério, não sobre o fato. Fica registrada para quem decidir.

## Suposições que tomei no lugar de perguntas
1. **Stack fica em Python/PySide6.** O briefing recomenda C++20 + C#/Avalonia, mas classifica a própria recomendação como "decisão nova de engenharia, não inferência", e o pedido foi pela interface visual.
2. **Reproduzir a categoria, não a tela.** Nenhuma marca de terceiro entra. As *regras de leitura* entraram por correção explícita do dono.
3. **Eixo azul/vermelho contra o verde/vermelho/amarelo da fonte**, por deuteranopia e protanopia. Registrado como divergência deliberada, não escondido.

## Condição de parada
**Ganhos por rodada convergiram nas lacunas nomeadas.** As últimas rodadas de P1, P2 e P3 fecharam cada uma sua lacuna **estruturalmente** — não por mitigação — e as três foram provadas por mutação. O que resta está caracterizado com precisão e entregue como sonda executável, não como observação.

## O que custou
15 agentes: 4 construtores (P1–P4) e 7 críticos, mais rodadas de retomada. Peça que mais consumiu sem se mover: **nenhuma** — todas as quatro fecharam ao menos uma lacuna estrutural. A que consumiu mais foi P2 (4 rodadas), e as duas últimas foram a mesma forma de defeito perseguida até a raiz.

## O que este ciclo descobriu, e vale além dele
1. **O canal preserva o veredito e apaga a ressalva** — não por acaso, por convenção tipográfica. Vereditos são grandes e saturados; ressalvas são pequenas e apagadas.
2. **Escala que desaparece é perda; escala que sobrevive errada é mentira.** `±3,2k` virando `12,2k` é pior que sumir.
3. **A resposta para "grandeza de variação enorme desenhada como comprimento" é tirar a grandeza da geometria**, não achar uma escala melhor. Descoberto três vezes, em três lugares.
4. **Um teste que mede contra um marco que o desenho não usa é teatro** — e só a mutação revela.
5. **Um harness de mutação que não muta reporta o código como perfeito.**

## E o que continua igual desde a primeira onda
**Nenhum byte de mercado real em disco.** Todo retrato deste ciclo é do simulador, com carimbo na imagem dizendo isso. A tela está pronta para receber um pregão gravado.

### RODADA 3 DE P2 — atacou a FORMA, e a forma cedeu

Ele reproduziu a medição do crítico primeiro, para trabalhar com os números dele:

| | resultado |
|---|---|
| **r2** | 20 barras, **todas 3px**, 1 valor distinto, razão **1×** |
| **r3** | desvios de costura: `[15, −16, −13, 2, −4, −1, 0, −6, −5, −2, −5, 3, 2, −1, 0, −10, 10, 14, 1, 5]` — **16 valores distintos**, maior 16px, menor não-nulo 1px, razão **16×** |

**A jogada:** volume saiu da geometria e virou **coluna numérica**. Volume de corretora varre ~500×, e *nenhuma barra lê 500×* — toda tentativa termina em piso, normalização ou rótulo minúsculo fazendo o trabalho da geometria. Número lê 500× sem esforço, e é literalmente o que a tela mais densa do acervo faz: zero barras, colunas numéricas alinhadas.

A barra ficou só com a **proporção compra×venda do próprio participante** — limitada por natureza (0–100%, 50% no meio), logo sem escala, sem piso, sem rótulo carregando leitura. Largura fixa nas 20 linhas; o que varia é **onde ela se parte**, e as costuras formam uma linha quebrada contra a espinha reta.

> Achar o anômalo virou achar o maior desvio de um alinhamento — **acuidade vernier**, que depende de duas bordas duras e não de medir comprimento pequeno contra referência distante.

**Efeito colateral que confirma que a forma era a causa:** `PainelPlayers` **não tem mais escala nenhuma**. Três versões tiveram, as três falharam. E some junto o repaint global — sem escala compartilhada, mudar uma linha suja uma linha.

### A tentativa que falhou, relatada por ele
O primeiro conserto foi *butterfly* — duas asas, comprimento = volume de cada lado. Parecia certo porque as parcelas variam 19× e não 222×. **O teste da cauda reprovou:** com 500× de spread as duas asas da 20ª linha arredondam para **zero** e a linha some, pior que os 3px. *"Foi isso que me forçou a tirar volume da geometria em vez de decompô-lo. A decomposição também era remendo."*

### Os testes que faltavam, agora escritos
- `test_costuras_distintas_para_players_distintos` — a medição do crítico virou asserção: ≥10 valores distintos, sinal da costura concorda com o sinal do saldo linha a linha, e **maior desvio ≥ 8× o menor não-nulo** (com piso, essa razão é 1). A r2 reprovaria aqui.
- `test_a_barra_do_ranking_nao_reusa_a_forma_do_medidor_do_dia` — o confronto **entre painéis**, que era exatamente o par colidente que nenhum teste cobria.
- `test_o_volume_nao_toca_mais_na_geometria` — volumes 500× diferentes com as mesmas proporções ⇒ **pixels idênticos**.
| 3 | P3 — Composição e cadeia | construtor | opus | — em curso |

### RODADA 2 DE P2: perdeu — e é a MESMA FORMA de defeito duas vezes

O crítico verificou fechado, e não volta: o carimbo lê o corte de produção da configuração (conferiu o default em `motor/sinais.py:247`), sem cor passa nas 20 linhas inclusive na cauda, sem cor literal, sem estrutura que cresce. **E o buraco do espião não existe aqui** — `_recorte` lê o backing store real, então `fillRect` conta e a geometria tem asserção de pixel. Esta peça fez certo o que derrubou a irmã.

**A lacuna, medida:** a coluna VIÉS reusa a geometria que a **própria tabela do módulo** reserva para "saldo assinado com catraca escrita" para desenhar uma **proporção sem escala**. E `PISO_BARRA_VIES = 3` trava **19 das 20 barras em exatamente 3px** — classificando pixel a pixel em x∈[1150,1215]. Contra saldos de `+8,2k` a `−37`, **220× de intervalo**, o operador vê vinte traços iguais. O que os desmente é a palavra `VIÉS` em corpo 10, que vira borrão no canal junto com a coluna AGR inteira.

A sentença do crítico: *"é a mentira gráfica da rodada 1 — veredito preservado, ressalva apagada pelo canal — **mudada de andar, não corrigida**."*

**Por que isso muda como devolvi.** É a segunda rodada seguida com a mesma FORMA: uma grandeza de variação grande aparece como comprimentos quase iguais, e o que desfaz a confusão é um rótulo pequeno que o canal apaga. Na r1 era a escala dos medidores; agora é o piso da barra de viés. Ele resolveu a primeira **removendo a necessidade da escala** — a melhor jogada do ciclo. Mandei atacar a *forma*, não a instância. O protocolo do gauntlet manda escalar quando o mesmo buraco sobrevive duas rodadas; se sobreviver a terceira, é estrutural e a decisão volta para o lead.

**Buraco de cobertura que explica o silêncio dos testes:** `test_as_duas_barras_do_hud_tem_formas_diferentes` compara só as barras **dentro** do `PainelHUD`; nenhum teste confronta a barra de viés do `PainelPlayers` com a do saldo do dia — que é o par colidente. E `test_um_vies_minusculo_ainda_desenha_barra_visivel` afirma que a barra **existe**, nunca que comprimentos diferentes dão comprimentos diferentes.

### P3 despachada — o produto ainda não tem tela

Quatro painéis bons e nenhuma composição: `PainelMatriz`, `PainelHUD` e `PainelPlayers` vivem **só** em geradores de retrato e testes; `janela.py` monta apenas DOM e tape. P3 monta o workspace, torna a cadeia legível, e responde à observação do crítico de P1 sobre a interface dar espaço ao fluxo que o registro não avaliza e nenhum às 33 regras que ele avaliza.

### P2 rodada 2 — a correção foi remover a escala, não engordar o rótulo

A frase do construtor resume: *"Não engordei o rótulo: tirei do segundo medidor a escala que ele não precisava ter."*

A janela de agressão deixou de ser saldo absoluto (que exige escala) e virou **proporção** — eixo 0-100% com 50% no meio, absoluto e imutável. Virou barra **particionada, sempre cheia**: a largura nunca muda, só a posição da costura. **Sem escala não há escala para o canal apagar**, e sem escala não existe comparação de comprimento a ser feita errado. A dúvida deixou de ser possível por construção, em vez de ser desfeita por uma legenda de 10px.

Isso fixou um **vocabulário de formas** que agora vale na peça inteira:

| Forma | Significa | Tem escala? |
|---|---|---|
| bidirecional a partir do zero | saldo assinado | sim, e escrita |
| particionada sempre cheia | proporção | não — por construção |
| unidirecional a partir do canto | magnitude sem sinal | — |

E ele manteve o `±2,5k` do medidor do dia morrendo no canal **de propósito**, com a justificativa certa: com a barra de baixo em outra forma, perder aquele rótulo custa a *unidade do eixo*, não uma *leitura errada*. A diferença entre os dois modos de falha é a justificativa inteira da mudança.

**O carimbo** — verifiquei na imagem degradada e é o elemento mais legível da página: tarja âmbar de 44px, texto escuro, dizendo retrato sintético, dominância 0,525 em vez de 0,70, players fictícios, e *"com os cortes de produção esta mesma sessão leria SEM CONFLUÊNCIA / LATERAL"*. O corte de produção é **lido de `ConfigMotorSinais()`**, não digitado. A segunda linha encolhe a fonte até caber — *"ressalva truncada continua parecendo frase inteira, que é o pior modo de falha possível dela."*

**Correção do teste errado, feita do jeito que não se repete:** o recorte passou a vir de `rect_barra_saldo()`, a mesma função que o painel usa para desenhar. Conta paralela no teste pode divergir do desenho e passar a medir outra coisa sem avisar.

**Dois defeitos que os testes novos acharam nele:**
- O comentário do módulo afirmava "pior preenchimento 80%"; o teste que **recalcula** a escada acusou **78%** — os degraus redondos valem 1,28, não 1,25. Corrigiu o comentário, não o teste.
- `▲ +200,0k` transbordava a coluna de saldo e pintava glifos azuis **por cima da barra do vizinho** — uma barra que não era barra. Nenhum teste de comportamento pegaria; pegou o que recorta a barra e compara pixels.

**Não-mudança declarada:** a razão incremental do HUD é **5,7×**, não 13× como o DOM, e é estrutural — 7 bandas contra 40 linhas, com ~0,06 ms de custo fixo por quadro. Ele mediu, documentou o teto no docstring e parou de perseguir margem que a geometria não permite.

### P1 rodada 2 — o que mudou, verificado por mim na imagem degradada

Abri `design/retrato_matriz_transmissao.png` e confirmei: `+100,0% NÃO CONFIRMADO` atravessa **inteiro**, `CONVICÇÃO MÁXIMA ≥80%` sobrevive com o limiar junto, o chip âmbar `PASSA SEM MEDIR` e o `0 MÉTODO · 338 GENÉRICAS` chegam nítidos. **Não existe mais um `PASSA` limpo nem um `+100,0%` a seco para o canal preservar sozinho.**

As decisões que sustentam isso:

**Procedência derivada do registro, não um mapa na UI.** `matriz.py` importa `metodologia.regras.REGRAS` e deriva a família pelo nome do tipo (`EXAUSTAO` → `exaustao.*` → não sustentada). Um `dict` tipo→procedência escrito na UI seria uma segunda fonte de verdade que envelhece em silêncio — recusado de propósito. E há teste do **ramo positivo** com `LINHA_AZUL` provando que o mecanismo liga sozinho no dia em que o pacote implementar `absorcao.*`.

**A ressalva entrou na mesma string, no mesmo `drawText`, com a mesma caneta:** `+100,0% NÃO CONFIRMADO`. E há teste afirmando que `+100,0%` sozinho **não** aparece entre os textos desenhados.

**`PASSA` sem medida deixou de existir como forma.** Sem referência, o valor não é publicado como medida: vira `SEM REFERÊNCIA` no mesmo corpo, calha vazia, e o veredito é o chip `PASSA SEM MEDIR` — *a ressalva está dentro da palavra, não dá para ler pela metade.*

**O limiar saiu da régua e entrou no rótulo da faixa** — `CONVICÇÃO MÁXIMA ≥80%`, `DIRECIONAL ≥70% · FONTE DIVERGE` — porque a régua de 10px é a primeira coisa que o canal apaga, e sem ela "convicção máxima" é adjetivo sem número. O `FONTE DIVERGE` sai do rótulo `IMPRECISO` do registro, não de opinião do painel.

**A recusa que mais vale:** ele **não** marcou divergência de fonte na faixa `CONVICÇÃO MÁXIMA`, porque o registro não tem regra documentando aquele desacordo — só o corte de 70. *"Inventar divergência onde o registro não registra é o mesmo pecado ao contrário."* Com teste afirmando a **ausência** do aviso ali.

### RODADA 1 DE P2: ganhou, e a vitória condena a barra

O crítico foi direto: a referência `06_medidores_agressao` responde **1 das 3 perguntas** que a peça existe para responder — não tem farol nem placar. *"Não é empate: B cobre 1 das 3 perguntas."* Vencer isso na primeira rodada prova que a barra estava baixa, e o protocolo é explícito sobre o que fazer. **Barra nova para P2: `09_tape_reading_b.png` + `02_superdom_c.png`**, as duas telas mais densas do acervo.

O que ele confirmou que funciona: o candidato **escapa** da falha da referência no teste sem cor — com o eixo direcional colapsado, o sinal explícito, o glifo e a barra saindo do zero desenhado continuam carregando a direção, e no ranking o tique da metade ainda discrimina (SIM 01 passa dele, SIM 02/03 não).

**A lacuna, e é a lei do canal outra vez:** a escala `±2,5k` / `±1,2k` — única coisa que autoriza comparar os dois medidores empilhados — é corpo 10 em `TEXT_SECONDARY` ao lado de um veredito corpo 13 peso 600 saturado. Ela **some** no canal, deixando duas barras de comprimento quase igual (89% e 82% da meia-trilha) sobre escalas que diferem **2,1×**. A decisão de escalas independentes existia justamente para evitar essa mentira gráfica — e o canal a produz de volta.

### Achados menores, registrados
- **Teste que passa pelo motivo errado:** `test_o_ranking_distingue_comprador_de_vendedor_SEM_cor` compara os pixels do painel **inteiro**, então o texto assinado sozinho já o aprova; ele não prova o que o docstring dele afirma. O HUD tem o par correto (recorta só a faixa da barra); o ranking não tem.
- **Farol em `CONFIRMADO` vira bloco único** — a progressão é real no código, mas no estágio terminal os cinco segmentos ficam indistinguíveis de uma barra cheia, e nenhum teste renderiza dois estágios comparando pixels do farol.
- Da linha SIM 05 para baixo a trilha tem ~10px e o tique deixa de ser discriminável.

### RESTRIÇÃO NOVA — o carimbo tem de estar na imagem

O crítico achou o problema que mais me importa como lead, porque afeta artefatos que eu faço circular: `scripts/retrato_hud.py` baixa o corte para `dominancia_minima=0,525` (contra 0,70 da metodologia) e fabrica o elenco `SIM 01..SIM 20`. Está declarado no script e no `print` — e **ausente da imagem**. O PNG exibe `CONFIRMADO — ENTRADA` e `53% DIRECIONAL`, rótulos que com os defaults embarcados seriam `SEM CONFLUÊNCIA / LATERAL`.

> A ressalva ficou no stdout, e **stdout não viaja com o arquivo**.

Regra que passa a valer para toda peça: **calibração ou dado fabricado que altere o que a tela afirma tem de estar carimbado NA IMAGEM**, legível depois da degradação de canal. É a lei do canal aplicada ao próprio processo de documentar o trabalho.

### P4 — as regras entraram, e o registro se recusa a mentir

Nove módulos em `fluxopro/metodologia/`. O que sustenta a peça não é a quantidade, são as **invariantes validadas no import**:

- citação ≤ 15 palavras;
- `AUSENTE_NA_FONTE` **não pode ter citação** e exige nota;
- `CONFIRMADO`/`IMPRECISO` exigem citação + fonte;
- `INFERIDO` exige nota.

O registro não importa nenhum componente — é auditável sem instanciar nada.

**Três testes que fazem o documento não conseguir mentir:**

| Teste | O que trava |
|---|---|
| `test_defaults_declarados_batem_com_os_defaults_reais` | confronta cada default do mapa de auditoria com o default real do `dataclass` — o documento não diverge do código sem quebrar a suíte |
| `test_leitura_e_invariante_a_escala` | multiplica o dia inteiro por 10 e por 1.000 e exige a **mesma sequência de estados**; reintroduzir um "250 = forte" quebra a igualdade na hora |
| `test_nenhuma_estrutura_cresce_com_o_numero_de_eventos` | roda os seis componentes com 1.000 e 20.000 eventos e exige o mesmo `len` em toda coleção de instância, **descendo nos objetos aninhados** |

**As 9 recusas, cada uma com a citação que a justifica.** As três que mais dizem sobre a disciplina:

- **`risco.limite_diario_agregado`** — *"eu tenho uma regra que eu não passo de três"* é **por região**; o autor nunca menciona limite do dia inteiro. E **a ausência é testada**: dez regiões bloqueadas não fecham a décima primeira. Testar que algo *não* existe é raro e é o que impede a regra de reaparecer por conveniência.
- **`risco.numeros_de_contratos`** — 20/10/5 é o lote pessoal do autor, não regra. `ConfigRisco` nasce em **0** e `tamanho()` levanta `TamanhoNaoConfiguradoError`. O sistema se recusa a herdar o tamanho de mão de outra pessoa.
- **`risco.gatilho_de_tamanho`** — o que separa região boa de turbulenta é julgamento visual. Consequência na API: `avaliar()` **exige** a `QualidadeRegiao` do operador; não há caminho que a dispense. A regra ausente virou uma pergunta obrigatória ao dono, em vez de um chute do código.

**Parâmetro em vez de constante, onde a fonte oscila:** a Linha Azul tem duas versões de plotagem na fonte, então a convenção é escolhida, declarada e **viaja em toda leitura** (`LeituraLinhaAzul.convencao`). O placar cita 4-0 *e* 5-0 para goleada — default no menor, que alerta antes.

**Defeito que ele achou em si mesmo:** a primeira versão do `Velocimetro` comparava a janela corrente com a rolagem corrente do balde — isto é, **consigo mesma**. O estado nunca saía de `MANTENDO` e uma virada de sentido jamais apareceria. Corrigido com uma rolagem de atraso, com o porquê no código.

### P2 — a decisão que resolve a peça
**A direção virou geometria, não matiz — e o teste é pixel, não intenção.** O medidor é barra bidirecional com o zero *desenhado* no meio da trilha; o ranking é trilha com contorno cujo comprimento é o volume, preenchida pela parcela compradora, com tique fixo na metade. Nos dois casos "de que lado" é comparação de **posição entre dois pixels**.

E o teste central não afirma que o código chama `paleta.direcional`: renderiza `+42.310` e `−42.310` **na mesma paleta sem cor** e exige que os dois backing stores **difiram** — com um segundo teste recortando só a faixa da barra, sem o texto, exigindo que difiram também. É literalmente o teste que a referência do mercado reprovaria: `(49,10k)` e `(42,31k)` em cinza são o mesmo pixel.

Outras duas: o placar sai do **estágio publicado**, não da evidência crua, porque `Sinal.evidencia` carrega os booleanos de *antes* da histerese e o estágio vem de *depois* — lê-los daria um `3/3` ao lado de um farol em `NA_REGIAO`, e painel que se contradiz em 28px é pior que painel que mostra menos. E as escalas dos dois medidores são independentes **e escritas na tela** (`±2,5k` / `±1,2k`), porque saldo do dia vive em dezenas de milhares e a janela de 5 s em centenas — barras empilhadas convidam a comparar comprimentos, e comparar escalas diferentes é mentira gráfica.

**Ressalva declarada pelo próprio construtor:** o simulador não preenche corretora, então o gerador de retrato reetiqueta os negócios com um elenco fictício `SIM 01..SIM 20` e calibra `dominancia_minima=0,525` para a faixa que esse gerador ocupa — mantendo a histerese nos defaults. Está documentado no script e impresso na saída. **O ranking do retrato é de corretoras que não existem**, e isso precisa continuar dito em qualquer lugar onde a imagem apareça.

### P1 — o que o construtor relatou contra si mesmo
Duas coisas que valem registro porque são o método funcionando:

**A régua roubava o portão.** Enquanto a régua das faixas (50/65/70/80) dividia retângulo sujo com o eixo, cada tick repintava também os nove rótulos dela — e isso sozinho punha a razão cheio/incremental em **4,9×**, abaixo do portão de 5×. Separada em banda própria, subiu para 17,9×. A regra que ficou: *o que não muda não compartilha retângulo sujo com o que muda.*

**O primeiro retrato expôs um erro que nenhum teste veria.** O motor publicava `NENHUM` (histerese ainda acumulando, 1 negócio) enquanto a janela já estava 100% compradora, e o painel desenhava o cursor colado na ponta da COMPRA com o número em cinza e sem sinal — como se o lado fosse desconhecido. Virou dois campos distintos: `direcao` (pós-histerese, alimenta o farol) e `direcao_dominante` (leitura instantânea, alimenta o eixo). As duas são verdade ao mesmo tempo e dizem coisas diferentes.

### RODADA 1 DE P1: **PERDEU**

**Maior lacuna nomeada:** a banda DETECÇÕES — ~60% da superfície e o conteúdo mais repetido do painel — apresenta `EXAUSTÃO` com a mesma tipografia de um veredito do método, sem um pixel de procedência **metodológica**. E o crítico achou o que eu não tinha visto: `fluxopro/metodologia/regras.py` **já existe** (P4 entregou em paralelo) com `id="exaustao.conceito"`, `confianca=AUSENTE_NA_FONTE` — e `matriz.py` sequer importa esse registro.

A formulação dele é melhor que a minha: o painel gasta uma coluna inteira, um token âmbar e três parágrafos de docstring para distinguir procedência do **dado** (MBO × MBP inferido), e **zero** para distinguir procedência da **regra**. O operador lê "o motor concluiu, pelo método, exaustão" 22 vezes seguidas quando a resposta honesta é "um detector interno genérico disparou 320 vezes em 2,5 s".

**O que ele verificou e absolveu** — vale tanto quanto o que reprovou:
- Rodou a suíte: `44 passed`.
- Procurou a **nona casa** do defeito de crescimento aplicando o critério do `gravador.py` a toda coleção de `matriz.py`. Não está lá: `_deteccoes` limitado por `MAX_SLOTS_DETECCAO=24`, contador O(1), lote temporário limitado pelo `deque(maxlen=...)` da ponte. E há teste de retenção que prova (1.000 detecções → `len == n_slots`).
- Os testes provam comportamento: o espião compara **texto desenhado**, não pixel, para afirmar legibilidade sem cor; a razão cheio/incremental é medida em vez de ms cravado.
- Achado colateral: `PainelMatriz` **não está montado em `ui/janela.py`** — vive só no gerador de retrato e nos testes. Escopo de P3.

### A LEI QUE ESTA RODADA DESCOBRIU — vale para o produto inteiro

Eu havia registrado, da linha de base V6, que *contraste baixo em corpo pequeno não sobrevive ao canal*. O crítico afiou isso num achado bem pior, e ele mediu:

> No `opcao_B_transmissao.png`, **sobreviveram** `PASSA` em verde, `+100,0%` e `NENHUM`. **Morreram** `9 sem referência · valor assumido`, o `(1 neg)` que desmente a convicção máxima, e a coluna inteira de MEDIDAS.

Ou seja: **o canal preserva o veredito e apaga a ressalva.** Não por acaso — por convenção tipográfica. Vereditos são grandes e saturados; ressalvas são pequenas e apagadas. A transmissão então *inverte sistematicamente a honestidade epistêmica* da tela, e entrega ao espectador exatamente o oráculo que o painel foi escrito para eliminar.

**Restrição que passa a valer para P1 r2, P2, P3 e qualquer peça futura:** se um número tem ressalva, a ressalva viaja no **mesmo portador** do número — mesma banda, mesmo corpo, mesma saturação — ou o número não é publicado naquela forma. Ressalva em corpo menor que o dado que ela qualifica é, neste produto, um defeito medível.

### O que eu vi no retrato, como lead, antes de despachar o crítico
22 dos 24 slots de detecção visíveis são **`EXAUSTÃO`**, 320 na sessão — e "exaustão" é justamente o conceito marcado **`AUSENTE NA FONTE`** em `pesquisa/metodologia_regras.md` §2: não aparece em nenhum dos 54 vídeos. O item mais proeminente da tela é o que menos pertence ao método, e ainda dispara em quase todo negócio. Não vou dizer isso ao crítico como resposta pronta — a restrição de fidelidade está no briefing dele e ele que decida se é *a* maior lacuna ou se há pior. Registrado aqui para não se perder caso ele vá por outro caminho.

*(atualizado conforme as peças caem)*

### Risco conhecido desta onda
Instruí os dois construtores a adaptar `scripts/retrato.py` para gerar seus PNGs. Se os dois editarem o mesmo arquivo em paralelo, um sobrescreve o outro. O arquivo está commitado (`02ec4ab`), então a recuperação é barata; a passada de coesão resolve. Registrado como erro meu de briefing, não como defeito dos construtores.

---

## Estado inicial verificado

`python -m pytest tests/ -q` → **796 passed** (commit `02ec4ab`). Fase 1 da UI entregue: `PainelDenso`, DOM, tape, strips. É sobre isso que a categoria ASG vai ser construída.

**Continua valendo:** nenhum byte de mercado real em disco. Todo retrato é do simulador.
