# FluxoPro

Para o contrato de captura, armazenamento seguro, análise diária e publicação
controlada de dados reais, consulte
[ESPECIFICACAO_DADOS_REAIS.md](ESPECIFICACAO_DADOS_REAIS.md).

Terminal de leitura e interpretação de fluxo do mercado futuro brasileiro (WDO/WIN), em Python.
Lê o tape e o livro, deriva estado de microestrutura, e emite **sinais** segundo uma metodologia
extraída de fonte pública com citação e rótulo de confiança.

**Modo sinais é sempre.** Não existe envio de ordem no código, e a tela declara isso.

---

## O estado, em uma linha

`python -m pytest tests/ -q` → **1.602 passed**
· ~29 mil linhas de produção, ~25 mil de teste
· **o tape é de mercado real**; o livro ainda não.

O gargalo mudou de tamanho em 23/08/2026. `scripts/importar_mt5.py` puxa o histórico de tick
que o terminal MetaTrader 5 guarda e grava no formato do `Gravador`, então um pregão fechado
vira replay sem precisar de ninguém na frente da máquina durante o mercado. Medido no primeiro
uso, WDOU26 em 21/08/2026: **200.899 negócios**, 09:00→18:29, com 86,8% carregando o lado do
agressor.

O que **não** se resolve assim é o livro: `market_book_get` só existe com o mercado aberto, e o
MT5 não guarda histórico de book. Numa gravação importada o DOM e o bookmap ficam vazios — e a
gravação é honesta sobre isso, ela simplesmente não tem `snapshots.csv`. Para as duas metades,
o caminho continua sendo o pregão ao vivo.

Em 24/08/2026 a tarefa agendada capturou a primeira gravação ao vivo com **livro** preenchido —
até morrer sozinha às 13:21 (Ctrl+C externo; o terminal MT5 continuou de pé, só o processo de
gravação caiu) e ninguém relançar pelas quase 5 horas de pregão que faltavam. Os dados até ali
não se perderam — `Gravador` grava em append e o dia interrompido não tinha `.gz` — mas nada no
nível de processo sabia que devia tentar de novo. `scripts/supervisionar_gravacao.py` fecha essa
lacuna: reconecta `operar.py` enquanto a janela do pregão não fecha e o dia não está finalizado,
com um circuito que desiste se as quedas forem rápidas e seguidas (sinal de MT5 fora do ar, não
de um evento isolado). É o que `gravar_pregao.cmd` chama agora.

Em 25/08/2026 o supervisor provou a si mesmo: a gravação rodou do início ao fim sem cair
(**1.326.893 eventos**, `parcial: false`) e a tarefa fechou sozinha, sem precisar reconectar
nenhuma vez. No mesmo dia o repositório absorveu o workspace `ASG-like` (proposta consultiva
Stop/A1/A2/A3, `MakerProxy`, auditoria de shadow) desenvolvido em paralelo — 245 arquivos, sem
conflito real com a gravação, verificado por merge local e suíte inteira reexecutada.
`dados_manifesto.json` já cobre os 34 pregões, incluindo o de hoje.

---

## Rodar

```bash
pip install -r requirements.txt        # pytest; PySide6 só para a interface
```

```bash
# a interface, sobre o simulador — não precisa de corretora
python scripts/painel.py --fonte simulador --simbolo WDOV26

# o mesmo pipeline, headless, imprimindo sinais e detecções
python scripts/operar.py --fonte simulador --simbolo WDOV26

# importar um pregão JÁ FECHADO (só o tape; exige o terminal MT5 aberto e logado)
python scripts/importar_mt5.py --simbolo WDOU26 --data 2026-08-21 --saida dados/

# gravar um pregão AO VIVO — tape E livro (exige mercado aberto)
python scripts/operar.py --fonte mt5 --simbolo WDOU26 --gravar dados/

# o mesmo, mas reconectando sozinho se a captura cair antes da hora
# (é o que a tarefa agendada roda — ver "O gargalo mudou de tamanho" abaixo)
python scripts/supervisionar_gravacao.py --simbolo WDOU26 --gravar dados/ --fim 18:30

# reviver o que foi gravado, determinístico
python scripts/painel.py --fonte replay --arquivo dados/ --simbolo WDOU26

# rodar o motor sobre TODOS os pregões gravados e tabular o que ele viu
python scripts/estudo_pregoes.py --arquivo dados/ --simbolo WDOU26

# conferir que as gravações locais batem com o manifesto versionado
python scripts/manifesto_dados.py --arquivo dados/ --verificar
```

O contrato é o **líquido do momento** (`WDOU26` em agosto/2026), e não `WDOFUT`:
os nomes com `$` e `@` são contínuos sintéticos da corretora.

O núcleo roda **sem Qt**. Quem só quer o CLI não instala PySide6, e a suíte de interface se pula
sozinha.

---

## Reprodutibilidade dos números

`/dados/` está no `.gitignore` e continua: são 26 MB de tick da B3, licenciado da corretora. Isso
deixava um buraco real — os números publicados aqui e no `PROGRESSO.md` eram auditáveis só por
quem tem os arquivos. **Um resultado que só o autor reproduz é uma afirmação, não uma medição.**

`dados_manifesto.json` é versionado e carrega, por pregão: símbolo, data, contagem de eventos,
primeiro e último timestamp, e o **SHA-256** do arquivo gravado. Não carrega preço, volume, VWAP
nem estatística derivada — a fronteira é proposital: ele responde *"quais insumos foram usados, e
estão íntegros?"*, e não *"quanto o mercado andou?"*.

Se os hashes baterem, o estudo reproduz. Se não, o `--verificar` diz qual dia divergiu. E o
próprio `estudo_pregoes.py` imprime a linha `PROCEDENCIA` antes de qualquer número, para que
nenhuma tabela saia daqui parecendo auditada sem estar.

---

## Arquitetura

```
Simulador · Replay · MT5
          ↓
   Barramento (síncrono, ordem de prioridade declarada e testada)
          ↓
   SessaoFluxo ─┬─ EstadoMercado (OHLC, sessão)
                ├─ analytics (volume profile, delta, agressão, VWAP, footprint)
                ├─ microestrutura (livro MBO, inferência MBP→MBO, detectores)
                ├─ metodologia (regime, velocímetro, linha azul, macro×micro, placar, risco)
                └─ MotorSinais (confluência de 3 condições, histerese, evidência)
          ↓
   PonteFluxo — buffer com teto, descarte contado, retrato consistente sob lock
          ↓
   PySide6 / Qt 6 — tudo desenhado em QPainter sobre backing store
```

**Preços são sempre `int` em ticks.** Nunca float, em lugar nenhum.

A camada de UI não toca em objeto vivo da thread da fonte: lê um retrato montado sob lock, com
os campos consistentes entre si. Um relógio de dados só, na janela, que distribui o mesmo
instantâneo para todos os painéis — há teste varrendo os painéis para garantir.

---

## A metodologia, e a disciplina dela

`fluxopro/metodologia/regras.py` é um registro de **42 regras** extraídas de 51 de 54 vídeos
públicos, cada uma com citação direta, fonte e rótulo de confiança. As invariantes são validadas
**no import**:

| Rótulo | O que o produto faz |
|---|---|
| `CONFIRMADO` | vira código |
| `IMPRECISO` | vira **parâmetro configurável**, nunca constante cravada |
| `AUSENTE NA FONTE` | **não é implementado como regra do método** |

Nove regras estão marcadas `implementada=False`, cada uma com a citação que justifica a recusa.
Três exemplos do que isso significa na prática:

- O limite de perda é **por região** (*"eu não passo de três"*), e o autor nunca menciona limite
  diário agregado. Então ele não existe — e **a ausência é testada**: dez regiões bloqueadas não
  fecham a décima primeira.
- Os números de contratos são o lote pessoal do autor, não regra. `ConfigRisco` nasce em zero e
  levanta erro se você pedir tamanho sem configurar.
- O que separa região boa de turbulenta é julgamento visual, sem fórmula na fonte. Logo
  `GestorRisco.avaliar()` **exige** essa qualidade vinda do operador — o gestor não assina o
  barramento, e a leitura publicada não tem campo de risco. Não há caminho pelo qual uma decisão
  de tamanho saia do sistema sem uma pessoa.

`pesquisa/regras_no_codigo.md` é o mapa auditável, e um teste confronta cada default declarado
nele com o default real do código.

---

## Cinco leis descobertas por medição

Estão aqui porque valem além deste projeto, e cada uma custou uma rodada de crítica adversarial.

1. **O canal preserva o veredito e apaga a ressalva.** A tela é consumida por captura de vídeo;
   vereditos são grandes e saturados, ressalvas são pequenas e apagadas, então a transmissão
   inverte sistematicamente a honestidade da tela. Regra: *se um número tem ressalva, ela viaja no
   mesmo portador — e em token de **luminância**, não de croma, porque o JPEG subamostra croma 2×.*
   Ferramentas: `scripts/transmissao.py` e `scripts/retencao.py --par RESSALVA=VEREDITO`.
2. **Escala que desaparece é perda; escala que sobrevive errada é mentira.** Um `±3,2k` que
   chega ao outro lado legível como `12,2k` é pior que um que some.
3. **Grandeza de variação enorme não vira comprimento.** A resposta é tirar a grandeza da
   geometria, não procurar uma escala melhor. Descoberto três vezes, em três painéis.
4. **Teste que mede contra um marco que o desenho não usa é teatro** — e só a mutação revela.
   Um guarda anti-piso deste projeto passava com o único piso que já existiu no produto.
   O caso extremo: o portão de canal derivava as caixas de medição multiplicando pelo
   `devicePixelRatio` da janela, então numa passada a 125% ele recortava coordenadas que **não
   existem** na imagem gerada a 100%. Ele acusou 0,3 pp de margem contra pixel fora da imagem e,
   na passada seguinte, 10,6 pp de violação real. Um portão frouxo é ruim; um portão que mede
   outro lugar e imprime um número é pior, porque assina.
5. **Lei aplicada caso a caso é sorte; lei aplicada como piso é portão.** A regra "ressalva em
   token de luminância alta" foi verificada três vezes por medição no retrato — e o chip de
   `CONFIRMADO` violava-a o tempo todo, sem nunca aparecer, porque o retrato amostrava regras
   `IMPRECISO`. Quem pegou foi um teste que varre **todos** os tokens que preenchem chip, não a
   imagem: `tests/test_ui_tokens.py::test_preenchimento_de_chip_nunca_abaixo_do_piso_de_luminancia`.

E o critério que atravessa o código todo, de cinco auditorias do núcleo: **estrutura que cresce
com o estado acumulado e é varrida tarde demais.** Foi encontrada em oito arquivos diferentes.
O critério de reconhecimento está no docstring de `fluxopro/gravacao/gravador.py`, e todo
acumulador novo passa por um teste de retenção que roda 1.000 e 20.000 eventos e exige o mesmo
tamanho em toda coleção alcançável — no núcleo (`tests/test_metodologia.py`) e, desde a onda 11,
também na interface inteira (`tests/test_ui_retencao.py`), que enumera os catorze painéis a
partir da própria janela em vez de uma lista digitada.

---

## Medições

```bash
python bench_carga.py       # vazão e escala do pipeline
python bench_ui_carga.py    # contenção de GIL entre a fonte e a interface
python -m pytest tests/test_ui_desempenho.py   # portão de repintura incremental
```

Nesta máquina: pipeline completo **~42,5 mil ev/s** com custo linear, **5,2 bytes/evento**,
pico de 2,5 MB em 500 mil eventos. Quadro incremental do DOM a 0,33 ms contra 4,4 ms de quadro
cheio — razão de 13×, e o portão de CI reprova abaixo de 5×.

---

## O que falta

1. **O livro.** O tape real já entra por `scripts/importar_mt5.py`; o book não, porque o MT5 não
   guarda histórico dele. DOM, bookmap e tudo que depende de liquidez parada só se enchem com
   `scripts/operar.py --fonte mt5 --gravar` durante o pregão aberto.
2. **Human gate visual.** O workspace `ASG-like` está implementado, mas a comparação permanece
   `proxy-biased` até o operador fornecer capturas reais autorizadas da ASG. Não há alegação de
   paridade visual ou pixel-perfect.
3. **Fórmula proprietária do Maker.** Ela continua classificada `NÃO REPLICÁVEL`. O produto usa
   um `MakerProxy` independente, aberto, versionado e acompanhado de evidências, cobertura,
   procedência e confiança; ele não é apresentado como fórmula da ASG.
4. **Comprovação ao vivo nesta máquina.** O adaptador MT5 e seus estados de falha estão
   implementados, mas uma sessão viva exige terminal autenticado, pacote `MetaTrader5`, símbolo
   selecionado e pregão aberto. Veja `FEED_DISCOVERY.md`.

O workspace novo abre com `Ctrl+5` ou:

```bash
python scripts/painel.py --fonte simulador --workspace ASG-like --simbolo WDOV26
```

Ele é estritamente consultivo: Stop, A1, A2 e A3 são propostas informativas e não existe envio
de ordens no produto.

`PROGRESSO.md` e `GAUNTLET_ASG.md` têm o histórico rodada a rodada, incluindo os erros.
