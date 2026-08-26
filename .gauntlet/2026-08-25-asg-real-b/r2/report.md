# Round 2 - Report (2026-08-25-asg-real-b)

## Pecas construidas nesta rodada

- fluxopro/ui/paineis/nexo/ladder.py - painel ladder do Nexo
- fluxopro/ui/paineis/nexo/contexto.py - painel de contexto do Nexo
- fluxopro/ui/paineis/nexo/niveis.py - painel de niveis do Nexo
- fluxopro/ui/paineis/nexo/banner.py - painel de banner do Nexo
- fluxopro/ui/paineis/nexo/estatistica.py - painel de estatistica do Nexo
- fluxopro/ui/paineis/nexo/nucleo.py - nucleo/orquestracao dos paineis Nexo
- fluxopro/ui/paineis/nexo/forca.py - painel de forca do Nexo
- fluxopro/ui/paineis/nexo/candles.py - painel de candles do Nexo
- fluxopro/ui/paineis/nexo/pressao.py - painel de pressao do Nexo
- fluxopro/ui/paineis/nexo/vies.py - painel de vies do Nexo
- fluxopro/ui/tema_asg.py - tema visual ASG compartilhado
- fluxopro/ui/paineis/nexo/indisponivel.py - estado "indisponivel" dos paineis Nexo
- fluxopro/ui/paineis/nexo/instrumento.py - seletor/contexto de instrumento do Nexo

## Verificacao de compliance (Round 2)

1. Grep de execucao de ordens (enviar_ordem|executar_ordem|colocar_ordem|OrderClient|corretora|def executar|callback_execucao)
   sobre os 13 arquivos acima: 0 matches. Nenhum painel contem logica de envio/execucao de ordem ou referencia a corretora.

2. float() em campos de preco/tick (grep -n "float(" + inspecao de contexto):
   - Unico hit: fluxopro/ui/paineis/nexo/pressao.py:240 -
     diametro_selo = max(14.0, min(float(banda_superior.height()), 30.0))
     Este float() converte uma altura de geometria Qt (height()), nao um valor de preco/price/tick.
     Nao e violacao.

3. Import/uso direto de fluxopro/dados ou do barramento ao vivo (grep -n "barramento|Barramento|assinar(" e busca por fluxopro.dados/import dados):
   0 matches nos 13 arquivos. Os paineis permanecem snapshot-only, sem acoplamento ao bus ou ao modulo de dados ao vivo.

## Conclusao

Nenhuma violacao encontrada nesta rodada. Nenhum BLOCKER.
