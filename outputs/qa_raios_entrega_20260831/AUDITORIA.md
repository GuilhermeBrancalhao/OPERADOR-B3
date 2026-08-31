# Auditoria da correcao visual dos raios — 31/08/2026

Resultado: aprovado para o escopo do renderizador de FORCA OBSERVADA.
Baseline publicado: 8329775. A validacao anterior contava chamadas de desenho,
mas nao comprovava separacao dos pixels; cinco raios espremidos pareciam barras.

## Correcao

- Cada leitura agora ocupa uma coluna com uma pilha vertical de 0..5 raios.
  Os simbolos tem espaco entre si, sem invadir a leitura vizinha.
- Uma unica linha do tempo, da esquerda para a direita. Compra acima do eixo;
  venda abaixo. As duas faixas cronologicas experimentais foram descartadas.
- Contagem existente preservada: zero abaixo de 5%; um ate 20%, dois ate 40%,
  tres ate 60%, quatro ate 80%, cinco acima de 80%. Extremos sao limitados a cinco.
- Altura visual em degraus; percentual continuo da ultima leitura aparece no
  cabecalho com uma casa decimal. Nao e probabilidade nem criterio novo de entrada.
- Deduplicacao, limitador temporal, serie original e calculos do placar preservados.
  Este trabalho nao afirma equivalencia entre o placar e a serie historica.
- Ultimas 24 leituras visiveis nas tres resolucoes validadas. Em tamanhos extremos,
  o rodape declara o subconjunto; sem altura suficiente solicita ampliar.
- Tooltip usa as coordenadas do compositor integrado. Cor no limite exato de 5%
  agora acompanha a presenca do primeiro raio.
- Limite temporal pequeno permanece positivo na legenda, sem arredondar para 0%/s.

## Evidencia executada

227 testes aprovados; um aviso preexistente de construtor QMouseEvent depreciado.
JUnit: ../qa_raios_entrega_testes_20260831.xml.

Inclui contagem das bandas de pixels coloridos (0..5, nos dois lados), 120 simbolos
sem intersecao nas 24 pilhas, mouse real via QTest no tooltip, candles/arrasto,
workspaces legados, snapshots e suite de ausencia de execucao de ordens.

python -m scripts.auditar_raios --saida <NOVA_PASTA> reproduz:

- escala sintetica de cinco intensidades por lado usando o renderer de producao;
- capturas QWidget.grab da JanelaFluxo e recortes nativos do placar;
- 30 redesenhos em cada uma de 1280x720, 1480x900 e 1920x1080;
- hashes dos pixels iguais em cada conjunto e identidade/conteudo do snapshot
  preservados; 90 quadros no total;
- comparacao local do renderer anterior/atual: 30 pares em ordem alternada,
  apos aquecimento, com a mesma serie.

Capturas inspecionadas: escala_1_a_5.png, operador_1480x900.png e os tres
placar_<resolucao>.png. Simbolos discretos visiveis, header e legenda dentro do
quadro, sem contadores sobrepostos aos raios. Sem imagem gerada ou retoque.

## Medicoes

Dados brutos, serie e SHA256 das fontes em medicoes.json.

| Renderer da regiao | p50 | p95 |
|---|---:|---:|
| Baseline 8329775 | 4,786 ms | 5,701 ms |
| Pilhas separadas | 3,452 ms | 5,594 ms |

Redesenho do painel inteiro com copia de imagem: p95 55,11 / 58,60 / 125,83 ms
nas tres resolucoes. Ambiente compartilhado com testes concorrentes; nao e uma
garantia de 60 FPS nem medida de throughput de mercado.

## Limites e rastreabilidade

- Cenarios sinteticos, sem adaptador externo e sem evidencia de pregao real.
- Captura Qt offscreen nao comprova DPI/composicao do desktop.
- Comparacao de pixels usa FLUXOPRO_REDUCED_MOTION=1 somente no auditor.
  Tentativas anteriores falharam porque parar QTimers nao congela o relogio do
  wallpaper; snapshots estavam preservados. Nenhuma alteracao do fundo em producao.
- Aceite restrito a esta correcao; nao significa paridade com ASG, reproducao de
  formula proprietaria ou auditoria integral de todos os modulos.
- Artefatos antigos do worktree foram mantidos fora do commit.
- Rollback: reverter o commit desta entrega com git revert, preservando o historico.
