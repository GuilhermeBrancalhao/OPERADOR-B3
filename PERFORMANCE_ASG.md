# Performance ASG-like — medição R8

Data: 2026-08-25. O comando reproduzível foi:

```powershell
.\.venv-asg\Scripts\python scripts\benchmark_asg.py `
  --passos 2000 --execucoes 30 `
  --saida .gauntlet\2026-08-24a\r8\final\benchmark_30.json
```

## Resultado

| Variante | Mediana eventos/s | p50 us/evento | p95 us/evento |
|---|---:|---:|---:|
| Baseline observável | 5.149 | 194,23 | 292,94 |
| MakerProxy | 4.885 | 204,72 | 390,36 |
| ASG completo | 4.219 | 237,10 | 361,13 |

- Overhead mediano do MakerProxy: **5,40%** — PASS para o limite de 10%.
- Throughput ASG completo: **4.219 eventos/s** — FAIL para a meta de 10.000
  eventos/s.

Esta medição é deliberadamente preservada como falha: não autoriza afirmar
que o requisito de performance do briefing está cumprido.

## Próxima frente de otimização

1. Perfilar `SessaoFluxo` sob o mesmo replay antes de alterar lógica.
2. Separar atualizações de book de recomputações de decisão que não mudam a
   janela ASG.
3. Medir alocação por evento e substituir estruturas transitórias do caminho
   quente sem abrir coleções ilimitadas.
4. Rodar exatamente o mesmo benchmark de 30 execuções; só reduzir o gap com
   evidência reproduzível permite fechar este gate.
