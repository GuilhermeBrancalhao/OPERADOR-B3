# Runbook — Operador B3 ASG-like funcional

## Execução segura

Crie/ative o ambiente do projeto e abra o simulador:

```powershell
.\.venv-asg\Scripts\python scripts\painel.py --fonte simulador --workspace ASG-like --simbolo WDOV26
```

Atalhos: `Ctrl+1` Fluxo, `Ctrl+2` Book & Tape, `Ctrl+3` Bookmap,
`Ctrl+4` Revisão e `Ctrl+5` ASG-like.

Replay determinístico:

```powershell
.\.venv-asg\Scripts\python scripts\painel.py --fonte replay --arquivo dados --simbolo WDOV26 --workspace ASG-like
```

MT5, somente depois de validar terminal, pacote, login, símbolo e pregão:

```powershell
.\.venv-asg\Scripts\python scripts\painel.py --fonte mt5 --simbolo WDOV26 --workspace ASG-like
```

O estado inicial do book MT5 é `NONE`. Ele só muda para `MBP` após um book
válido observado; expiração vira `GAP_BOOK` e bloqueia confirmação.

## Evidências e auditoria

```powershell
.\.venv-asg\Scripts\python scripts\gerar_shadow_congelado.py --saida .gauntlet\shadow-check --run-id check-v1
.\.venv-asg\Scripts\python scripts\auditoria_asg.py --raiz . --shadow-dir .gauntlet\shadow-check --exigir-shadow --report-dir .gauntlet\audit-check
.\.venv-asg\Scripts\python scripts\benchmark_asg.py --execucoes 30 --passos 2000 --saida .gauntlet\benchmark-asg.json
```

O shadow é opt-in e exige simultaneamente `ligar_leitura_asg=True`,
`ligar_shadow_learning=True` e `shadow_dir`. Escrita gzip ocorre num writer
separado com fila limitada. Falha de disco degrada somente o sidecar.

## Rollback

Os defaults de `ConfigOperacao` deixam feed quality, MakerProxy, LeituraASG e
shadow desligados. Para voltar ao comportamento histórico, use esses defaults
e um dos quatro workspaces antigos. Para rollback de código, o commit anterior
à integração central é `f27b898`; não use reset destrutivo em worktree com
alterações não salvas.

## Limites honestos

- Produto consultivo; nunca envia ordens.
- MakerProxy é fórmula independente do Operador B3.
- Feed textual ou imagem de LLM nunca vira tick.
- Conexão MT5 ao vivo não foi comprovada nesta máquina em 2026-08-24.
- Avaliação visual permanece proxy-biased até o Human Gate com capturas reais.
