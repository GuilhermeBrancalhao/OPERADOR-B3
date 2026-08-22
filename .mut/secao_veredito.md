
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
"não pego" — é inatingível por esta suíte nas duas direções, porque o maior teste
de gravação do projeto publica **10 eventos** e o regime do defeito é 10⁸.

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
4,8 M de eventos, o dobro do testado). As 10 mutações que o builder 5 alegou ter
matado morreram todas contra a suíte inteira, e isso inclui N04/N05 — a física
invertida do simulador, viva desde a R2 e o buraco mais citado das quatro
rodadas. Zero ressurreições em 31 re-aplicações. A virada de sessão saiu de 8 de
12 componentes carregando o dia anterior (R3) para **um só, declarado no código**.

O problema desta rodada não é qualidade de execução. É **escolha de alvo**: cinco
ondas consertaram o que a auditoria anterior apontou, e a auditoria anterior
nunca apontou a camada que guarda o dado. O ciclo respondeu com precisão a
perguntas cada vez mais estreitas enquanto o subsistema que ninguém perguntou
acumulava 12 das 13 mutações vivas do projeto.

A recomendação para a onda 9 é, portanto, de método e não de código: **antes de
consertar o que esta crítica apontou, rodar o critério de crescimento e uma
passada de mutação sobre os módulos que nenhuma rodada escolheu.** Foi assim que
esta rodada achou tudo o que achou.
