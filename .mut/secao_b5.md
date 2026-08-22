
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
