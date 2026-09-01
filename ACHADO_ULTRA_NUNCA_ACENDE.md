# ACHADO ABERTO — o filtro ULTRA nunca pode acender

**Data:** 01/09/2026
**Status:** DIAGNOSTICADO, NAO CORRIGIDO (de proposito — ver "Por que nao consertei")
**Origem:** o operador, em 01/09/2026: *"nenhum momento vi direcao do mercado
nem ultra aceso"*.

---

## O que foi medido

Sonda no caminho REAL do produto (`assistente.desenhar_resumo` e
`MotorDecisaoASG.avaliar`), replay das gravacoes de `dados/WDOU26`, layout
integrado (`FLUXOPRO_NEXO_AI=1`).

### 1. As 4 condicoes do ULTRA, em 5 pregoes

| pregao | quadros | maximo atingido | condicoes que acenderam |
|---|---|---|---|
| 25/08 | 1.599 | **1 de 4** | so MAKER (270) |
| 26/08 | 1.779 | **1 de 4** | so MAKER (223) |
| 27/08 | 1.708 | **1 de 4** | so MAKER (245) |
| 28/08 | 1.008 | **1 de 4** | so MAKER (255) |
| 31/08 | 3.276 | **1 de 4** | so MAKER (713) |
| **total** | **9.370** | **nunca 2 de 4** | `DECISAO` e `CONFIANCA`: **ZERO** |

Cinco pregoes distintos, nenhum chega a 2 de 4. `MAKER` acende em todos, o
que prova que a medicao funciona — o que nao acontece e a confirmacao.

### 2. Por que `RENKO` tambem fica em zero

`RENKO` **nao e independente**: `nucleo._condicoes_ultra` calcula

```python
renko_ok = (fase is FaseRenko.TENDENCIA
            and confirmada          # <- depende de DECISAO
            and direcao_renko is alvo)
```

Com `DECISAO` apagada, `RENKO` e falso POR CONSTRUCAO, mesmo com o Renko em
TENDENCIA na tela. Das 4 lampadas, 3 estavam apagadas por um portao so.

**Ja corrigido na apresentacao** (nao no motor): `_Condicao.bloqueada_por`
faz a tela distinguir `·REN` (nem foi avaliada) de `−REN` (avaliada e nao
atendida). Os dois layouts leem a mesma funcao pura, entao a distincao
aparece igual nas duas telas.

### 3. A decisao nunca confirma — e a evidencia ESTA la

Pregao de 31/08, 1.601 quadros:

| medida | valor |
|---|---|
| `direcao == AGUARDAR` | **1.601 / 1.601 (100%)** |
| `confianca == INDISPONIVEL` | **1.601 / 1.601 (100%)** |
| matriz com **6 de 6** linhas apontando lado | 1.248 (78%) |
| motivo "pre-sinal presente; confirmacao bloqueada" | 878 |

Em 78% dos quadros as SEIS linhas da matriz apontam lado, e mesmo assim a
decisao sai `AGUARDAR` com confianca `INDISPONIVEL` em 100% dos quadros.

### 4. Onde exatamente o portao fecha

`fluxopro/asg/decisao.py:213` — `confirmacao = pre_sinal and not bloqueios`.

Espiando `MotorDecisaoASG.avaliar`, 6.467 decisoes no pregao de 31/08:

| bloqueio | quadros | % |
|---|---|---|
| `QUALIDADE_FEED_BAIXA` | **6.467** | **100%** |
| `CONFIANCA_BAIXA` | **6.467** | **100%** |
| `MAKER_NAO_CONFIRMADO` | **6.467** | **100%** |
| `PRECO_FORA_DA_REGIAO` | 1.977 | 31% |
| `PERSISTENCIA_INSUFICIENTE` | 1.527 | 24% |
| `INVALIDACAO_ESTRUTURAL_INVALIDA` | 941 | 15% |
| `DIRECAO_INDISPONIVEL` | 815 | 13% |
| `EVIDENCIA_IRRELEVANTE` | 815 | 13% |
| `SEM_BOOK` / `FEED_NAO_SAUDAVEL` | 1 | ~0% |

- `pre_sinal = True` em **3.965 de 6.467 (61%)** — o pre-sinal existe.
- `confirmacao = True` em **0 de 6.467**.
- Nenhuma decisao, em nenhum quadro, saiu **sem bloqueio**.

**Tres bloqueios disparam em 100% das decisoes**: `QUALIDADE_FEED_BAIXA`,
`CONFIANCA_BAIXA` e `MAKER_NAO_CONFIRMADO`. Combinacao mais frequente
(3.374x): exatamente esses tres, sozinhos.

## Por que isto e defeito, e nao mercado parado

Um bloqueio que dispara em **6.467 de 6.467** decisoes, em **5 pregoes
diferentes**, nao esta descrevendo condicao de mercado — esta descrevendo um
portao que nao abre. `QUALIDADE_FEED_BAIXA` num replay de dado GRAVADO e
especialmente suspeito: nao ha feed degradado ali, o arquivo esta completo.

E o mesmo formato de dois defeitos ja confirmados neste projeto:

- `EstadoFeed.REPLAY` — membro de enum que nao existia, derrubava a
  dominancia em todo quadro de replay;
- a saude de S/R presa em `STALE` durante ~50 min por exigir 10 candles, com
  rotulo que dizia "ATRASADO" e mandava procurar problema de conexao.

Nos tres casos: um estado inalcancavel escondido atras de um rotulo
plausivel.

## Proximo passo sugerido

Medir, para cada um dos tres bloqueios de 100%, o valor observado contra o
limiar configurado — do mesmo jeito que se fez com a janela de amplitude do
Renko. A hipotese a testar primeiro e que os tres compartilham uma raiz
(a qualidade/confianca do maker), ja que `CONFIANCA_BAIXA` e
`MAKER_NAO_CONFIRMADO` andam sempre juntos com `QUALIDADE_FEED_BAIXA`.

## Por que nao consertei

O operador nao estava presente, e mexer em quem confirma direcao muda o
comportamento do produto inteiro — inclusive o que ele mostra como leitura
consultiva. Nesta mesma sessao eu declarei coisas prontas ou quebradas tres
vezes com o instrumento errado (`tail` cortando saida ordenada, captura no
meio da pintura, screenshot ignorando DPI). Diagnostico com numero e barato
de revisar; alteracao as cegas no motor de decisao, nao.

## Como reproduzir

```bash
python scripts/painel.py --fonte replay --arquivo dados --data 2026-08-31 \
    --velocidade max --duracao 300 --simbolo WDOU26
```

Com a sonda que espia `MotorDecisaoASG.avaliar` e conta
`snapshot.bloqueios` (a sonda usada vive no scratchpad da sessao; o essencial
e monkeypatch de `avaliar` + `collections.Counter` sobre `bloqueios`,
`pre_sinal` e `confirmacao`).
