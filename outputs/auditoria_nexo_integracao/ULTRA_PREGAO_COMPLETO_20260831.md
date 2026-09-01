# Auditoria de pregão completo — Ultra

Data do replay: 31/08/2026
Símbolo: `WDOU26`
Fonte: replay local `dados/WDOU26/2026-08-31`
Pipeline: `fluxopro.app.montagem.montar`

## Resultado direto

O Ultra ascendeu **66 vezes por episódios oficiais**:

- **53 compras**;
- **13 vendas**;
- 20.796 retratos processados;
- 35.902 negócios processados;
- incidência de episódios: **0,184% dos negócios**.

Um episódio é contado somente na transição `NENHUMA -> COMPRA/VENDA`. Quadros
continuamente acesos não são contados como novas ascensões.

## Validação dos gates

As 66 ascensões verificadas no replay atenderam simultaneamente:

- decisão principal confirmada;
- Macro e Micro alinhados com a direção;
- região operacional válida;
- persistência mínima de 5 segundos;
- feed conectado;
- livro MBP disponível;
- confiança da decisão igual a 0,90.

O Maker permaneceu **evidência auxiliar**, conforme a configuração atual. Ele
foi preservado no snapshot e auditado, mas não bloqueou uma confirmação
contextual. O Renko ficou fora do gate.

## Retorno posterior assinado

Valores em ticks, com o sinal da direção do episódio. `positivo` significa
deslocamento posterior a favor da direção exibida; não representa P&L, pois
não inclui spread, custos, slippage ou regra de execução.

| Horizonte | Todos (n=66) | Compras (n=53) | Vendas (n=13) |
|---|---:|---:|---:|
| 1 s | 24,24% positivos; média +0,0455 | 22,64%; média -0,0189 | 30,77%; média +0,3077 |
| 3 s | 33,33% positivos; média +0,1970 | 33,96%; média +0,0755 | 30,77%; média +0,6923 |
| 5 s | 40,91% positivos; média +0,2727 | 37,74%; média +0,1132 | 53,85%; média +0,9231 |
| 15 s | 43,94% positivos; média +0,5455 | 39,62%; média +0,0943 | 61,54%; média +2,3846 |

Mediana do retorno geral: zero tick em todos os horizontes. As durações dos
episódios tiveram mediana de 38,637 s, mínimo de 8,423 s e máximo de 177,778 s.

## Interpretação

**A lógica faz sentido como filtro de contexto:** não houve ascensão sem
confirmação, sem região, sem alinhamento Macro/Micro ou antes da persistência
mínima. O resultado mostra que o problema anterior de “nunca ascende” foi
removido sem transformar cada quadro visual em uma nova entrada.

**A qualidade preditiva ainda é inconclusiva:** neste único pregão, a maioria
dos sinais não teve deslocamento positivo no horizonte de 1–15 s, a mediana
foi zero e o resultado de compra foi praticamente neutro. O lado vendedor
teve leitura melhor em 5–15 s, mas com apenas 13 episódios. Isso não autoriza
calibrar parâmetros nem afirmar vantagem estatística.

## Procedência e reprodução

- Sonda versionada: `scripts/auditoria_ultra_pregao.py`.
- JSON completo, incluindo cada episódio e seus horizontes:
  `ultra_pregao_completo_20260831_r2.json`.
- Testes do motor: `37 passed` (`tests/test_asg_sinal_ultra.py` e
  `tests/test_asg_decisao.py`).
- A sonda foi compilada com `py_compile`.
- Nenhuma ordem é enviada; Stop e alvos continuam informativos.

## Limitações

Este relatório cobre um único pregão salvo. Episódios podem ocorrer próximos
no tempo e os horizontes podem compartilhar observações, portanto não são
amostras independentes. Para concluir sobre utilidade operacional, ainda são
necessários vários pregões, baseline comparável, custos e validação temporal
fora da amostra.
