# FluxoPro

Terminal de leitura e interpretação de fluxo do mercado futuro brasileiro (WDO/WIN), em Python.
Lê o tape e o livro, deriva estado de microestrutura, e emite **sinais** segundo uma metodologia
extraída de fonte pública com citação e rótulo de confiança.

**Modo sinais é sempre.** Não existe envio de ordem no código, e a tela declara isso.

---

## O estado, em uma linha

`python -m pytest tests/ -q` → **1.321 passed, 1 xfailed**
· ~29 mil linhas de produção, ~25 mil de teste
· **nenhum byte de mercado real em disco** — todo retrato é do simulador, com carimbo na imagem.

Esse último ponto é o gargalo real do projeto e o único que não se resolve escrevendo código.

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

# gravar um pregão de verdade (exige MetaTrader5 numa conta de corretora)
python scripts/operar.py --fonte mt5 --simbolo WDOFUT --gravar dados/

# reviver o que foi gravado, determinístico
python scripts/painel.py --fonte replay --arquivo dados/ --simbolo WDOFUT
```

O núcleo roda **sem Qt**. Quem só quer o CLI não instala PySide6, e a suíte de interface se pula
sozinha.

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

## Quatro leis descobertas por medição

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

E o critério que atravessa o código todo, de cinco auditorias do núcleo: **estrutura que cresce
com o estado acumulado e é varrida tarde demais.** Foi encontrada em oito arquivos diferentes.
O critério de reconhecimento está no docstring de `fluxopro/gravacao/gravador.py`, e todo
acumulador novo passa por um teste de retenção que roda 1.000 e 20.000 eventos e exige o mesmo
tamanho em toda coleção alcançável.

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

1. **Dados reais.** Nenhum byte de mercado em disco. Só se resolve instalando o MetaTrader5 numa
   conta de corretora e rodando `scripts/operar.py --gravar` num pregão.
2. **Uma sonda `xfail` aberta**, com o endereço do conserto no próprio `reason`.
3. **Componentes da fonte cujo mecanismo não é público** — o "Maker" está classificado
   `NÃO REPLICÁVEL`, e construir a caixa visual dele seria dar aparência de autoridade a algo que
   o sistema não consegue calcular.

`PROGRESSO.md` e `GAUNTLET_ASG.md` têm o histórico rodada a rodada, incluindo os erros.
