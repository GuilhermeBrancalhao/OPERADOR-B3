# FLUXO PRO — Gauntlet Loop (progresso ao vivo)

Objetivo: plataforma própria de leitura e interpretação de fluxo do mercado futuro (WDO/WIN),
nível institucional (barra: Profit Pro da Nelogica), em Python, com:
- leitura em tempo real (camada de dados plugável: replay histórico, simulador, adaptadores MT5/ProfitDLL/Cedro)
- ferramentas de fluxo: times & trades, DOM/book, footprint, volume profile, delta, agressão, absorção, rastreio de player
- motor de sinais 100% parametrizável pelo usuário
- aprendizado contínuo (estatística online sobre acerto dos sinais)
- modo sinais por padrão; execução real atrás de interface desativada (usuário liga com credencial própria)

## Barra de qualidade
1. **UI**: screenshots reais do Profit Pro (armazenados em `bar/`) — comparação cega lado a lado.
2. **Motor**: replay determinístico (mesmo input → mesmo output), suíte de testes verde,
   latência do pipeline de analytics < 5ms por evento de tick em replay acelerado.
3. **Metodologia**: checklist dos conceitos de leitura de fluxo extraídos do canal @SergioGargantini
   e material ASG — cada conceito coberto por um módulo mensurável.

## Roteamento de modelos
| Papel | Tier | Modelo | Esforço |
|---|---|---|---|
| Lead | T3 | sonnet (sessão) | alto |
| Pesquisa/aquisição da barra | T1-T2 | haiku/sonnet | baixo |
| Builder visual/novel (UI, footprint) | T3 | opus | alto |
| Builder padrão (motor, testes) | T2 | sonnet | médio |
| Builder mecânico | T1 | haiku | mínimo |
| Crítico de gosto/UI | T3 | opus | alto |
| Crítico mensurável | T0+T1 | comando+haiku | mínimo |

Orçamento do run: ~2M tokens. Reserva de críticos: ~500k (não gastar em build).

## Decisões tomadas no lugar de perguntas
- Não consigo assistir vídeo/áudio: metodologia reconstruída de transcrições + artigos. (limitação declarada)
- Sem feed pago de dados B3 nesta máquina: camada de dados nasce com replay/simulador + adaptadores prontos para MT5/ProfitDLL/Cedro. (recurso pago ausente — não bloqueia o build)
- Execução real NUNCA sai ligada por padrão; eu não executo ordens — entrego a interface, o usuário conecta.
- Projeto novo em pasta própria `fluxo_pro/` (regra: não misturar projetos).
- Nome de trabalho: **FLUXO PRO** (troca quando o dono quiser).

## A METODOLOGIA (extraída de transcrições reais dos vídeos)

Estrutura do sinal ASG, confirmada com citação direta em 3 vídeos:

**Sequência de 3 condições (confluência obrigatória, nesta ordem):**
1. **Direção do dia** — indicador percentual comprador × vendedor ultrapassa ~**70%**. Abaixo disso ("51% contra 49%") não há trade.
2. **Retorno à região do Smart Money** — o preço faz pullback e volta a uma **faixa** de preço (não um preço exato) marcada pela ferramenta. A ferramenta **recalcula essa região dinamicamente** conforme o fluxo muda.
3. **Virada da "micro"** — o fluxo de curtíssimo prazo (seta + histograma) precisa virar na direção pretendida. "Você nunca vende enquanto essa seta tiver apontando para cima."

**Pré-sinal ("blackout" / farol amarelo):** antes da confirmação plena o histograma passa de cor cheia para **cinza/amarelo** — perda de força do lado dominante, ainda sem validar entrada.

**Ondas / regiões de microfrequência:** faixas onde o preço tende a oscilar lateralmente por segundos a minutos (briga institucional / distribuição de ordens). Regra: não vender no fundo da região nem comprar o topo. Rompeu a região → embala o próximo movimento; não rompeu → tende a voltar.

**Absorção:** um lado agride, o outro segura sem deixar o preço avançar → aviso "vendedor absorvendo a compra". É alerta de atenção, não entrada por si só.

**Gestão de risco (3 camadas):**
- *Stop de pânico* — longe, "cinto de segurança" para evento inesperado (notícia/tweet). Não é o stop esperado.
- *Stop manual pela cor* — "piscou verde, zera". Troca stop de 150-200 pontos por 30-40.
- *Parcial* — relativa a perfil; para iniciante, proteger cedo.

**Força do movimento:** a aceleração da micro mede a força. Acelerando na direção → alonga a operação. Virou → sai.

### Cobertura do canal
54 vídeos no canal. 15 transcritos na primeira passada. Download das 39 legendas restantes em curso — inclui a série **SNIPER ASG** completa (18 aulas), **Maker: rastrear HFTs e robôs** (2 partes), **Linha Azul e Regiões**, **Gráfico Renko**, **Smart Money + Porcentagem**, **IA ASG "Velocímetro" com Machine Learning**, aulas ao vivo de WINFUT e aulas básicas. As lacunas abaixo devem fechar com esse material.

**LACUNAS honestas do extrator** (não inventar): os termos "agressão", "delta", "exaustão", "defesa de preço", "renovação de oferta", "mão cheia/mínima" e a regra de "3 stops seguidos" **não aparecem** nos 3 vídeos lidos — estão em outros vídeos ainda não extraídos. O % comprador×vendedor é provavelmente o equivalente funcional de delta, mas ele nunca chama assim.

## ACHADO CRÍTICO — identidade de corretora não existe em WDO/WIN

O aprofundamento do feed UMDF derrubou uma premissa que eu tinha herdado da barra (o Profit Pro tem "Ranking de Corretoras"):

**Nenhum dos três caminhos de dados garante ver a corretora por trás da ordem nos minicontratos.** Os campos de identificação de contraparte só existem fora de negociação anônima, e o mecanismo RLP da B3 anonimiza por regra de negócio parte do volume de WIN/WDO — isso é característica do produto, não de nível de acesso. Pagar mais não resolve.

Custos apurados dos caminhos:
- **(A) MetaTrader5** — R$ 0, dias de setup. Nunca mostra corretora.
- **(B) Vendor pago (Cedro / ProfitDLL)** — preço sob consulta, semanas de atrito. Nenhum dos dois confirma publicamente entregar book por ordem com identidade.
- **(C) UMDF direto** — ~R$ 190-200 mil/ano (uso interno via vendor) a ~R$ 290 mil/ano (acesso direto), fora conectividade, e exige decoder FAST/SBE em C/C++/Rust (não há biblioteca Python pronta). Meses de trabalho.

**Consequência de design (e ela é boa):** o rastreio de player em WDO/WIN não pode se apoiar em identidade — tem de ser **inferido por comportamento**: assinatura de clip, regularidade de intervalo, reposição em nível, razão volume-executado/exibido. É exatamente a camada de microestrutura já em construção, que passa de "diferencial" a **espinha dorsal do produto**. O `RankingCorretoras` dos analytics vira ferramenta secundária, útil só onde o dado existir.

**Pendência para o dono:** confirmar por e-mail com marketdata@b3.com.br se a leitura por corretora é viável hoje nesses contratos, antes de qualquer gasto com (B) ou (C). Recomendação: ficar em (A) e investir o esforço na inferência comportamental.

## Rodadas
| Peça | Rodada | Papel | Modelo | Veredito | Gap |
|---|---|---|---|---|---|
| **Núcleo** (eventos/book/replay/simulador) | 1 | builder | sonnet | ✅ 23 verdes | book é MBP, `n_orders` sempre 1 → sem ordem individual (peça 3 resolve) |
| **Analytics** (volume, footprint, delta, agressão, brokers, vwap) | 1 | builder | sonnet | ✅ 53 verdes (30 novos + 23 core intactos) | 7 módulos completos, 0 falhas |
| **Microestrutura/MBO** + detectores (absorção/iceberg/reposição) | 1 | builder | opus | 🔄 em voo | 25-30 testes esperados |
| **Direção visual** + stack (PyQt6/Dear PyGui benchmark) | 1 | builder | opus | 🔄 em voo | design system + decisão de stack |
| **Crítico do núcleo** (mutação + benchmark) | 1 | crítico | opus | 🔄 em voo | mutantes, eventos/s real, microestrutura |
| **MT5 + Gravador** (conexão, gravação, CLI) | 1 | builder | sonnet | 🔄 em voo | adaptador, formato CSV/Parquet, replay |
| **Legendas 54 vídeos** (download + índice) | 1 | pesquisa | haiku | 🔄 em voo | consolidação das 39 faltando |
| **Feed B3 UMDF** (aprofundamento) | 2 | pesquisa | sonnet | ✅ completado | identidade de corretora NÃO existe em WDO/WIN por design B3 |

## Log
- [setup] Pasta criada, barra e pesquisa despachadas em paralelo.
- [wave-0] 4 agentes no ar: metodologia ASG (T2), barra Profit Pro (T2), fontes de dados B3 (T2), núcleo do motor (T2 build). Python 3.14.6 confirmado no host.
- [wave-0][ok] **fontes de dados** → `pesquisa/fontes_de_dados.md`. Veredicto: `MetaTrader5` (pip, grátis, Clear/Rico/XP/Modal) é a via de tempo real de menor atrito (ticks + book por polling, sem streaming nativo). ProfitDLL/Cedro = pago. **Não existe histórico público de book** (FTP da B3 descontinuado; UP2DATA é pago e sem book) ⇒ **DECISÃO ARQUITETURAL: o gravador próprio é peça de primeira classe** — o adaptador MT5 grava tudo em disco desde o dia 1 para formar a base de replay. Isso reforça a prioridade do `AdaptadorReplay` já em construção.
