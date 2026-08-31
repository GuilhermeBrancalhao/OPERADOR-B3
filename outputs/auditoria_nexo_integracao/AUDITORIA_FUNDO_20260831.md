# Fundo integrado — verificação em 31/08/2026

Referência solicitada: exec-946a3f3e-caeb-4f7f-86d0-e984b6a4da1f.png.

## Estado: implementação parcial; aceite visual NÃO aprovado

Implementados: imagem local empacotada, cover proporcional com cache de tamanho
único, uma passagem de wallpaper sob o compositor NEXO, ciclo de 48 segundos,
paralaxe do cursor, modo reduzido, fallback escuro e bloqueio de redesenho
oculto/minimizado. Núcleo com máscara de transição; molduras externas dos cards
centrais removidas. Contornos compra/venda preservados. Nenhuma regra de mercado
alterada nesta rodada. Corrigido retorno ausente no movimento do mouse sem arrasto.

## Evidências

- 36 testes direcionados aprovados: fundo, candles/arrasto, força/estatística e
  ausência de execução. Um aviso de API de QMouseEvent depreciada.
- 60 testes aprovados na execução conjunta de test_nexo_ai_integracao.py e
  test_ui_fundo_operador.py (há 8 testes de fundo repetidos entre os comandos).
- Captura real 1680x945: fundo_aprovado_final.png.
- Captura real 980x620: fundo_aprovado_pequeno.png.
- Fonte das capturas: simulador, não mercado real. Sem fabricação de histórico
  para imitar candles da referência.
- Suíte geral não constitui evidência de aprovação até resultado final.

## Diferenças abertas

1. Cabeçalho, faixa de simulador e rodapé ainda opacos: wallpaper contínuo apenas
   na área operacional NEXO, não na janela inteira.
2. Textura original não é pixel a pixel igual à textura da referência gerada.
3. Placar/força e tipografia não reproduzem a composição da referência.
4. Em 980x620 há sobreposição de rótulos no contexto e textos secundários pequenos.
5. Não foi executado benchmark de 30 rodadas nem validação manual prolongada do
   movimento. Os testes comprovam periodicidade por pixels, não conforto visual.

## Configuração

FLUXOPRO_REDUCED_MOTION=1 desativa o movimento no próximo início.
FLUXOPRO_WALLPAPER permite indicar outro arquivo; arquivo ausente deixa fundo escuro.
Sem essas variáveis, utiliza assets/wallpaper-original.jpg do pacote.

Não declarar perfeito, pixel-perfect ou auditoria integral aprovada. Nenhum commit
ou push realizado nesta rodada. Alterações anteriores do worktree preservadas.
