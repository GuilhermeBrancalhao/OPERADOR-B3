# Especificação de captura e análise diária de mercado real

Status: aprovada para a próxima implementação
Versão: 1.0
Responsável pela execução: equipe do Operador B3

## 1. Objetivo

Toda sessão real do MT5 deve ser capturada de forma identificável,
reproduzível e auditável. Ao final de cada pregão, o sistema deve produzir uma
análise derivada que permita responder:

- qual ativo foi capturado;
- qual foi a janela temporal e o fuso utilizado;
- quantos negócios, snapshots e deltas foram recebidos;
- se houve lacunas, duplicidades, atraso ou ausência de book;
- quais sinais, estados, MakerProxy, força, regiões, stops e alvos consultivos
  foram observados;
- quais resultados foram calculados depois do fechamento, sem lookahead;
- qual versão do código e das fórmulas produziu cada relatório.

Esta especificação não autoriza envio de ordens. O Operador B3 continua
exclusivamente consultivo.

## 2. Regra de armazenamento e publicação

O GitHub público é repositório de código e evidência, não depósito de dados
licenciados da B3/corretora.

### 2.1 Dados brutos

Os dados brutos devem ficar fora do Git e ser preservados no armazenamento
local ou privado configurado pelo operador:

```text
${OPERADOR_B3_MARKET_DATA_DIR}\
└── <simbolo>\
    └── <data-utc>\
        ├── trades.csv.gz
        ├── snapshots.csv.gz
        ├── deltas.csv.gz
        └── meta.json
```

O valor padrão de desenvolvimento é `dados\` na raiz do clone, mas a
implementação deve aceitar `OPERADOR_B3_MARKET_DATA_DIR` ou `--gravar` com
caminho absoluto. A pasta `dados\` permanece no `.gitignore`.

Nunca publicar no GitHub público:

- `trades.csv`, `trades.csv.gz`;
- `snapshots.csv`, `snapshots.csv.gz`;
- `deltas.csv`, `deltas.csv.gz`;
- credenciais, tokens, login do MT5 ou arquivos de configuração privada;
- qualquer dump bruto que possa violar a licença da corretora.

Se houver autorização jurídica para armazenar dados brutos em um remoto,
usar um bucket/repositório privado separado, com controle de acesso, retenção
e criptografia. Isso não deve ser confundido com o push público do código.

### 2.2 O que deve acompanhar o push do código

O próximo push pode e deve conter artefatos não sensíveis:

```text
relatorios/mercado/<data-utc>/<simbolo>/
├── resumo.md
├── resumo.json
├── manifest.json
├── performance.json
└── screenshots/
    ├── ao_vivo.png
    ├── fechamento.png
    └── estados_criticos.png
```

O relatório deve conter somente métricas agregadas e análises derivadas
aprovadas pelo operador. Cada número precisa carregar fonte, timestamp ou
janela, fórmula/versão, qualidade do feed e indicação `OBSERVADO`, `DERIVADO`
ou `INFERIDO`.

O `manifest.json` deve registrar, no mínimo:

```json
{
  "schema": "operador-b3-market-report-v1",
  "symbol": "WDOU26",
  "session_date_utc": "AAAA-MM-DD",
  "timezone": "UTC",
  "raw_data_location": "private://...",
  "raw_files": [
    {"name": "trades.csv.gz", "sha256": "...", "bytes": 0}
  ],
  "counts": {"trades": 0, "snapshots": 0, "deltas": 0},
  "source": "MT5",
  "book_kind": "MBP|MBO|NONE",
  "code_revision": "git-sha",
  "formula_versions": {"maker_proxy": "...", "decisao": "..."},
  "quality": {"gaps": 0, "duplicates": 0, "max_latency_ms": 0},
  "publication": {"raw_data_public": false, "reviewed": false}
}
```

O hash prova a identidade do insumo privado; não substitui a posse do arquivo
bruto e não revela o conteúdo ao GitHub.

## 3. Captura ao vivo

Com MT5 aberto, conectado e autenticado, o processo obrigatório é:

```powershell
python scripts\supervisionar_gravacao.py `
  --simbolo WDOU26 `
  --gravar "$env:OPERADOR_B3_MARKET_DATA_DIR" `
  --fim 18:30 `
  --status-a-cada 300
```

Se a variável não estiver definida, usar um caminho absoluto privado, por
exemplo:

```powershell
python scripts\supervisionar_gravacao.py `
  --simbolo WDOU26 `
  --gravar "D:\DadosOperadorB3\dados" `
  --fim 18:30
```

O supervisor deve:

1. validar que o símbolo existe no MT5;
2. registrar conexão, corretora e qualidade sem gravar credenciais;
3. iniciar `operar.py --fonte mt5 --gravar <diretório>`;
4. manter trades e book no mesmo barramento;
5. deduplicar e sinalizar lacunas;
6. reconectar com backoff limitado;
7. escrever log em `logs\pregao_<data>.log`;
8. fechar arquivos, hash e `meta.json` ao final;
9. marcar a sessão como `parcial: true` se houver interrupção;
10. nunca afirmar “dia completo” quando a captura não cobriu a janela.

O agendamento diário precisa chamar o caminho absoluto do clone e do ambiente
Python. A tarefa deve ser auditável com:

```powershell
schtasks /Query /TN "FluxoPro-GravarPregao" /V /FO LIST
```

Uma conexão visual do MT5, sem esse processo ou tarefa ativa, não é captura.

## 4. Fechamento e análise diária

Depois do fim do pregão, a rotina diária deve executar, nesta ordem:

```powershell
python scripts\manifesto_dados.py `
  --arquivo "$env:OPERADOR_B3_MARKET_DATA_DIR" `
  --verificar

python scripts\estudo_pregoes.py `
  --arquivo "$env:OPERADOR_B3_MARKET_DATA_DIR" `
  --simbolo WDOU26
```

Na implementação seguinte, encapsular essas etapas em um comando idempotente:

```text
scripts/fechar_pregao.py
  1. localizar a sessão mais recente;
  2. validar meta, hashes e contagens;
  3. rodar replay determinístico;
  4. recalcular MakerProxy, força, regiões e decisões consultivas;
  5. gerar labels somente após o timestamp de previsão;
  6. gerar resumo.md, resumo.json e manifest.json;
  7. gerar screenshots e métricas de qualidade;
  8. publicar apenas artefatos permitidos;
  9. retornar código diferente de zero se a sessão estiver inválida.
```

Separar claramente:

- `captura`: o que o MT5 forneceu;
- `derivação`: o que o motor calculou naquele instante;
- `avaliação posterior`: o que só pode ser conhecido depois;
- `publicação`: o que é permitido subir ao GitHub.

## 5. Gate obrigatório antes do push

O próximo push que alegar “dados reais analisados” deve passar por um gate
automatizado, preferencialmente `scripts/verificar_publicacao_mercado.py`:

```text
PASS se:
  - existe uma sessão finalizada ou explicitamente parcial;
  - meta.json e hashes estão íntegros;
  - o relatório identifica ativo, data, timestamps e revisão;
  - nenhum arquivo bruto ou segredo está staged;
  - raw_data_public == false;
  - o replay reproduz as contagens e estados declarados;
  - labels não usam dados posteriores à previsão;
  - análise e screenshots correspondem ao mesmo commit;
  - `scripts/auditoria_asg.py` retorna ORDENS: PASS.

FAIL se:
  - MT5 apenas está aberto, mas não existe processo de captura;
  - dados estão somente em memória;
  - o diretório é vazio;
  - existe divergência de hash;
  - há `trades.csv.gz`, `snapshots.csv.gz` ou `deltas.csv.gz` no staging;
  - o relatório usa linguagem de certeza para dado inferido;
  - qualquer API de ordem aparece fora da allowlist de testes.
```

Comandos mínimos de revisão:

```powershell
git status --short
git diff --cached --name-only
git diff --cached --check
git diff --cached --name-only | Select-String '(^|\\)(trades|snapshots|deltas)\\?\.csv'
python scripts\auditoria_asg.py --exigir-shadow --shadow-dir <shadow-validado>
```

## 6. Critérios de aceite

- uma sessão MT5 real aparece em `MARKET_DATA_DIR/<simbolo>/<data>`;
- `meta.json` informa se foi completa ou parcial;
- replay da sessão funciona sem MT5;
- relatório diário é gerado de modo idempotente;
- MakerProxy, força, VAP/candles, sinais e alertas mostram procedência;
- análise posterior não contamina a decisão histórica;
- dados brutos continuam fora do GitHub público;
- manifestos, relatórios e screenshots sobem no próximo push aprovado;
- o operador consegue localizar o dado privado por `raw_data_location` e
  verificar sua integridade pelo SHA-256;
- ausência de captura bloqueia a alegação de análise real.

## 7. Estado verificado em 2026-08-26

No clone `OPERADOR-B3-main-atualizado` não havia `dados\`, `logs\` nem processo
de captura ativo. Portanto, esta especificação foi adicionada para orientar a
próxima implementação, mas não constitui prova de que uma captura real já
ocorreu nesta máquina.
