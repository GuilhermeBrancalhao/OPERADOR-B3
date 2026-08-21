# Fontes de Market Data B3 (WDO/WIN) para Python — Windows

Pesquisa para um sistema de leitura de fluxo em tempo real + replay histórico. Data da pesquisa: 2026-08-21.

---

## 1. Tabela comparativa

| Fonte | Dado disponível | Latência | Custo | Atrito de setup | Pacote Python |
|---|---|---|---|---|---|
| **MetaTrader5 (pacote `MetaTrader5`)** | Ticks (trade), candles, DOM (book) *se o corretor expuser* | Baixa (~ms a poucas dezenas de ms, depende do corretor) | Grátis (conta demo ou real na corretora) | Baixo — `pip install MetaTrader5`, precisa do terminal MT5 aberto e logado | Oficial (`MetaTrader5` no PyPI) |
| **ProfitDLL (Nelogica)** | Ticks, book completo (múltiplos níveis), histórico de trades via DLL | Muito baixa (<10ms divulgado pela Nelogica) | Pago — precisa de licença Profit Pro/plataforma Nelogica + contrato de acesso à DLL | Médio/Alto — DLL C, wrapper Python via `ctypes`, precisa manter referências de callback vivas, 32/64 bits específico | Não oficial no PyPI — usa a DLL diretamente (wrappers da comunidade, ex. repo `marcusgarim/profit-DLL`) |
| **Cedro Crystal / Market Data Cedro** | Quotes, book, trades — "centenas de mensagens" de market data B3 | Baixa (ms, divulgado pela Cedro, sem número público) | Pago, sob contrato via marketdatacloud.com.br | Médio — precisa contratar, consumir REST/Socket/WebSocket, não há SDK Python oficial pronto | Nenhum oficial — integração via REST/WebSocket com `requests`/`websockets` |
| **RTD do Tryd (Excel)** | Cotações em tempo real (não tick-a-tick puro, atualização ~2s configurável) | Média (segundos) | Depende da assinatura da Tryd/corretora | Alto para uso via Python — é pensado para Excel (DDE/RTD), exige ponte COM (`xlwings`/`win32com`) | Nenhum nativo — via automação COM do Excel |
| **B3 UMDF (acesso direto)** | Feed nativo binário (FIX SBE) de todos os mercados B3, o mais completo possível | Mínima (é a fonte primária) | Proibitivo para uso individual — exige link dedicado via RCB, contrato de distribuidor, custos fixos+variáveis pela Política Comercial de Market Data | Muito alto — infraestrutura de operadora certificada, contrato institucional | Nenhum — é um feed binário de baixo nível, não uma lib Python |
| **APIs públicas de corretoras (XP/Clear/Rico)** | — | — | — | — | Não existe API pública de mercado para desenvolvedores nessas corretoras (grupo XP Inc.); o canal delas é MT5/ProfitChart de terceiros, não uma API própria aberta |
| **B3 "Cotações Históricas" (grátis)** | OHLC diário, **só mercado à vista (ações)** — não cobre WDO/WIN | — | Grátis | Baixo — zip + txt de largura fixa, layout em PDF | Nenhum — parsing manual (`pandas.read_fwf`) |
| **B3 UP2DATA / UP2DATA On Demand** | Times & Trades tick-a-tick (negócio a negócio), inclusive derivativos (WDO/WIN); dados intraday, ajustes, posições em aberto | — (é histórico, entregue via SFTP/loja online) | Pago — loja online por volume/período, sem tier gratuito identificado | Médio — self-service via loja online, formatos TXT/CSV/JSON/XML | Nenhum — download + parsing |
| **Book histórico oficial (OFER_CPA/OFER_VDA)** | Reconstrução do livro de ofertas por timestamp | — | **Descontinuado** — B3 parou de publicar via FTP público no fim de 2019/2020 | N/A — não existe mais canal gratuito; nem os vendors credenciados consultados oferecem histórico de book/DOM, nem simplificado | N/A |
| **MT5 `copy_ticks_range` / `copy_ticks_from`** | Histórico de ticks guardado pelo terminal/corretor | — | Grátis (dentro da conta MT5) | Baixo, mas **profundidade real depende de cada corretor** — não há garantia de quantos meses ficam disponíveis; é comum ser limitado a poucas semanas/meses para ativos B3 | Oficial `MetaTrader5` |
| **Captura própria contínua (self-hosted)** | O que você mesmo gravar via MT5/ProfitDLL/Cedro a partir de hoje | Igual à fonte usada para captar | Custo da fonte usada + armazenamento | Baixo depois de montado — é só um logger rodando 24/7 no pregão | — |

---

## 2. Tempo real — detalhamento por via

### 2.1 MetaTrader5 (pacote Python `MetaTrader5`)

- **Pacote oficial** no PyPI (`pip install MetaTrader5`), só Windows, wheels para CPython 3.8–3.13 em x86-64. Precisa do terminal MT5 instalado e logado (a lib Python conversa com o terminal local via IPC, não é standalone).
- **Corretoras BR que oferecem WDO/WIN via MT5**: pelos fóruns MQL5 e relatos de usuários, corretoras como **Clear, Rico, XP, Modalmais, Terra** disponibilizam servidores MT5 com esses contratos (confirmar servidor/símbolo exato com cada uma — nomes de símbolo variam, ex. `WDOU26`, `WINZ26` ou com sufixos próprios da corretora). Corretoras internacionais **não** têm ativos B3.
- **O que expõe**:
  - `copy_ticks_from()` / `copy_ticks_range()` — ticks de trade (`COPY_TICKS_ALL`/`COPY_TICKS_TRADE`/`COPY_TICKS_INFO`).
  - `copy_rates_from()` / `copy_rates_range()` — candles OHLC prontos.
  - `market_book_add(symbol)` + `market_book_get(symbol)` — **DOM (book)**: retorna tupla de `BookInfo(type, price, volume, volume_dbl)`. Exige assinatura prévia via `market_book_add`; **a disponibilidade do book depende inteiramente do que o corretor expõe** — muitos brokers só mostram uma fração do book real ou nem oferecem DOM para todos os símbolos. Liberar com `market_book_release()`.
- **Limitações práticas**: histórico de ticks fica limitado ao que o corretor mantém no servidor (não documentado formalmente — na prática, relatos de usuários indicam de semanas a poucos meses para ativos B3, bem menor que Forex). Não há garantia contratual de profundidade de book em múltiplos níveis — muitas corretoras só passam melhor oferta (nível 1).

**Exemplo mínimo — conectar e puxar ticks:**
```python
import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

if not mt5.initialize():
    print("initialize() failed:", mt5.last_error())
    quit()

# login já deve estar salvo no terminal, ou passe login/password/server:
# mt5.initialize(login=123456, password="xxx", server="Corretora-Demo")

symbol = "WDOU26"  # ajustar ao contrato vigente e ao símbolo da corretora
mt5.symbol_select(symbol, True)

ticks = mt5.copy_ticks_range(
    symbol,
    datetime(2026, 8, 18),
    datetime(2026, 8, 21),
    mt5.COPY_TICKS_ALL,
)
df = pd.DataFrame(ticks)
df["time"] = pd.to_datetime(df["time"], unit="s")
print(df.tail())

mt5.shutdown()
```

**Exemplo mínimo — book em tempo real (DOM):**
```python
import MetaTrader5 as mt5
import time

mt5.initialize()
symbol = "WINZ26"

if not mt5.market_book_add(symbol):
    print("market_book_add falhou:", mt5.last_error())
else:
    for _ in range(20):
        book = mt5.market_book_get(symbol)
        if book:
            for level in book:
                print(level.type, level.price, level.volume)
        time.sleep(0.5)
    mt5.market_book_release(symbol)

mt5.shutdown()
```

**Exemplo mínimo — stream de ticks via polling (ideal para fluxo):**
```python
import MetaTrader5 as mt5
import time

mt5.initialize()
symbol = "WDOU26"
mt5.symbol_select(symbol, True)

last_time = 0
while True:
    tick = mt5.symbol_info_tick(symbol)
    if tick and tick.time_msc != last_time:
        print(tick.time_msc, tick.bid, tick.ask, tick.last, tick.volume)
        last_time = tick.time_msc
    time.sleep(0.05)  # MT5 não tem push nativo em Python; é polling
```

> Nota: o pacote Python do MT5 **não tem callback/streaming nativo** — tudo é polling contra o terminal local. Para fluxo de alta frequência isso é uma limitação real (latência de polling + overhead de IPC).

### 2.2 ProfitDLL (Nelogica)

- **Requisitos**: contrato de licença Profit (Profit Pro ou equivalente) + solicitar acesso à ProfitDLL na área logada do site da Nelogica (corporativo@nelogica.com.br). Após liberado, baixa-se `ProfitDLL.zip` com as DLLs de 32/64 bits, exemplos (Delphi, C#, C++, **Python**) e manual em PDF.
- **O que expõe**: ticks, book completo em múltiplos níveis, dados históricos de trades sob requisição — é o feed mais completo entre as opções "de varejo", com latência divulgada abaixo de 10ms.
- **Atrito**: não é um pacote PyPI — é uma DLL nativa consumida via `ctypes`/`cffi`. Em Python, callbacks precisam ser mantidos vivos em variáveis de escopo durável (comuns crashes silenciosos se isso for esquecido). Exige atenção à arquitetura (32 vs 64 bits) coerente entre Python e a DLL.
- Existe um repositório de terceiros (`marcusgarim/profit-DLL` no GitHub) com documentação e exemplo `profitDLL.py`, útil como ponto de partida, mas não é oficial da Nelogica.

### 2.3 Cedro Crystal / Market Data Cedro

- Serviço de redistribuição oficial de dados B3 (vendor credenciado), com **REST (JSON), Socket e WebSocket**. Cobre quotes, book e trades em tempo real ou delay.
- **Custo**: contratado sob demanda via marketdatacloud.com.br — sem tabela pública de preço nem trial claro na página institucional; é preciso falar com o comercial.
- **Atrito**: não há SDK Python oficial — integração é via HTTP/WebSocket cru (fácil de fazer com `requests`/`websockets`, mas sem exemplos prontos).

### 2.4 RTD do Tryd (Excel)

- RTD/DDE é uma tecnologia pensada para **planilhas**, não para Python diretamente. Para usar em Python seria necessário abrir o Excel como servidor RTD e consumir via COM (`win32com`/`xlwings`), o que é gambiarra para um sistema de fluxo em tempo real — atualização padrão de ~2s (configurável), longe de tick-a-tick.
- Exige Tryd e Excel rodando como administrador, .NET Framework ≥ 3.5.
- **Veredicto**: via de baixa prioridade — mais para dashboards simples do que para motor de fluxo.

### 2.5 B3 UMDF (acesso direto ao feed)

- UMDF é a consolidação nativa de todos os sinais de market data da B3 (spot, opções, futuros, câmbio, cripto), com variante binária (FIX SBE) de latência mínima — é literalmente a fonte primária que os vendors (Cedro, Bloomberg etc.) consomem.
- **Custo proibitivo confirmado**: exige conexão via RCB (rede de comunicação da B3), contratação de link dedicado com operadora certificada, e contrato de distribuição sujeito a custos fixos e variáveis pela Política Comercial de Market Data da B3. É desenhado para instituições/distribuidores, não para uso individual.
- **Veredicto**: descartar para este projeto.

### 2.6 APIs de corretoras (XP, Clear, Rico)

- XP, Clear e Rico pertencem ao grupo XP Inc. e **não publicam API pública de market data para desenvolvedores**. O canal delas para dados/execução automatizada é via plataformas de terceiros já integradas (MT5, ProfitChart, Vérios, Alkanza, Fast Trade) — ou seja, a via prática continua sendo MT5/Profit, não uma API proprietária dessas corretoras.

---

## 3. Histórico / replay — detalhamento por via

### 3.1 B3 "Cotações Históricas" (gratuito)

- Cobre **mercado à vista (ações)**, granularidade **diária**, histórico desde 1986, arquivo ZIP com TXT de largura fixa (layout em PDF oficial). **Não inclui WDO/WIN** (contratos futuros/derivativos ficam fora desse serviço específico).

### 3.2 B3 UP2DATA / UP2DATA On Demand (pago)

- Loja online de dados históricos da B3, cobrindo **Times & Trades (negócio a negócio, tick-a-tick)** inclusive para derivativos (WDO/WIN), além de ajustes, posição em aberto e mais. Entrega via SFTP ou loja online, formatos TXT/CSV/JSON/XML.
- Substituiu o antigo FTP público de negócios (NEG), que foi desligado em meados de 2020.
- **Sem tier gratuito identificado** — é serviço comercial por volume/período.

### 3.3 Book histórico (DOM) — descontinuado

- Até fim de 2019 a B3 publicava via FTP público arquivos `OFER_CPA_BMF_aaaammdd.gz` / `OFER_VDA_BMF_aaaammdd.gz` (ordens de compra/venda, timestamp em milissegundos, ~500-600MB compactados/dia), que permitiam reconstruir o book em qualquer instante passado.
- Esse canal foi **desligado em 2020**; a B3 informou que passaria a ser comercializado por empresas credenciadas. Na prática, relatos de usuários (fórum MQL5, ago/2026) mostram que **nem os vendors credenciados oferecem hoje histórico de book/DOM**, nem versão simplificada (ex.: snapshot a cada 1s).
- **Conclusão**: não existe hoje fonte — grátis ou paga de fácil acesso — para reconstruir o book histórico de WDO/WIN antes da data em que você mesmo começar a gravar.

### 3.4 MT5 `copy_ticks_range` / `copy_ticks_from`

- Puxa o histórico de ticks que o **terminal/corretor** mantiver localmente. Não há SLA documentado de profundidade — na prática, para ativos B3, o retido costuma ser bem mais curto que em Forex (semanas a poucos meses, variando por corretora). Serve bem para replay recente, não para anos de histórico.

### 3.5 Outras fontes gratuitas de histórico (limitadas)

- **Backtester.com.br**: OHLCV diário/intraday gratuito para ações, índices, ETFs, BDRs — cobertura de derivativos como WDO/WIN não confirmada como tick-a-tick; tratar como fonte secundária de candles, não de fluxo.
- Nenhuma fonte gratuita encontrada que ofereça **tick-a-tick histórico de WDO/WIN com profundidade de anos**. Isso hoje é serviço pago (UP2DATA) ou depende da retenção do seu corretor MT5/Profit.

---

## 4. Feed direto B3 (UMDF) — avaliação séria, não descartada por custo

Investigação a pedido do dono do projeto, a partir da página oficial [Plataformas de difusão | B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/plataformas-de-difusao/) e dos documentos técnicos e comerciais públicos da B3. Contato oficial da B3 para este assunto: marketdata@b3.com.br, +55 11 2565-5996 (Gerência de Market Data e Serviços de Conectividade); GDS (conectividade) em gds@b3.com.br; Certificação em tradingcertification@b3.com.br, +55 11 2565-5029.

### 4.1. Os três canais — diferenças técnicas

Fonte primária: [UMDF Market Data Specification (FIX/FAST) v2.2.0](https://www.b3.com.br/data/files/83/C0/9E/B7/D3543910B371F339AC094EA8/UMDF_MarketDataSpecification.pdf) e Política Comercial de Market Data v3.0.4 (capítulo 2).

| Canal | Protocolo / transporte | Latência | Público-alvo declarado pela B3 | Book: MBO ou MBP |
|---|---|---|---|---|
| **UMDF BINARY** | Nativo do PUMA Trading System, FIX **SBE** (Simple Binary Encoding) v1.0, UDP multicast | A menor de todas — "otimizado para baixa latência" | High Frequency Traders e clientes de **CO-LOCATION B3**; algoritmos e ferramentas sensíveis à latência | Oferece acesso ao livro de ofertas em **diferentes níveis de profundidade**, incluindo book por ordem (MBO) — é o canal onde a B3 mantém o gerenciamento "Order Depth Book" (ver 4.1.1) |
| **FIX/FAST UMDF** (UDP) | FIX 5.0 + FAST (compressão/serialização), UDP multicast | Baixa (mas maior que o binário) | Todos os tipos de distribuidores/redistribuidores/usuários finais — é o canal "completo, contínuo e serializado" | Também oferece MBO ou MBP, dependendo do canal/instrumento (ver 4.1.1) |
| **FIX/FAST UMDF Conflated** | FIX 4.4, **TCP/IP** (não multicast) | Deliberadamente degradada: book atualizado a cada **300ms**; trades/estatísticas/notícias continuam em tempo real | Distribuidores/redistribuidores para **telas de negociação ou consulta** — a B3 recomenda **não usar para algoritmos ou envio automatizado de ordens** | Recuperação do book em diferentes níveis de profundidade, mas sem granularidade de tick |

Cada canal é dividido em três streams: **Incremental** (updates em tempo real), **Snapshot Recovery** (recuperação do estado do book) e **Instrument Definition** (dicionário de instrumentos). Há ainda um **TCP Replayer** (recupera mensagens perdidas da sessão corrente) e um **TCP Historical Replayer** (recupera mensagens desde o início da semana de pregão corrente — só para uso de *gráficos*, a B3 proíbe explicitamente usá-lo para recuperação em produção ou consumo em tempo real). Ou seja: mesmo pagando pelo acesso direto, **não existe histórico de semanas/meses via UMDF** — o replay nativo da B3 cobre no máximo a semana de pregão corrente.

#### 4.1.1. MBO vs. MBP — o que a B3 realmente publica

- **Order Depth Book (MBO — "Market By Order")**: cada ordem individual aparece como uma entrada separada do book, identificada por um `OrderID` (tag 37) que define a prioridade dentro do nível de preço. É o nível mais granular.
- **Price Depth Book (MBP — "Market By Price" / "TOB")**: cada entrada agrega todas as ordens de um mesmo preço, com contagem de ordens (`NumberOfOrders`) e volume total — não dá para ver ordens individuais.
- A Política Comercial (capítulo 5.2) formaliza isso como dois **níveis comerciais**: **L1** (melhor oferta de compra/venda + negócios fechados — sem livro completo) e **L2** ("informações contidas no livro de ofertas como um todo... inclui o L1, o livro de ofertas com **preços agregados (Market By Price – MBP)**"). Ou seja: **a oferta comercial padrão (L2) é MBP, não MBO** — o texto da política não promete book por ordem individual no L2. O UMDF BINARY é descrito como oferecendo "acesso... aos dados que compõem o livro de ofertas em diferentes níveis de profundidade", o que sugere que o MBO pode existir como um canal técnico separado (voltado a HFT/co-location), mas isso **não está garantido nem precificado explicitamente** na tabela de preços pública — precisaria confirmar com marketdata@b3.com.br se o MBO é comercializável fora de co-location e qual o canal/preço específico.

### 4.2. Como se contrata — vendor, sub-vendor e cliente direto

Fonte: [Política Comercial de Market Data B3 v3.0.4](https://www.b3.com.br/data/files/6D/77/9D/65/0AB929106EEC8429AC094EA8/Politica%20Comercial%20de%20Market%20Data%20v3.0.4.1.pdf), capítulos 3, 4 e 8.

- **DISTRIBUIDOR**: captura o MARKET DATA B3 **diretamente** da infraestrutura da B3 (acesso direto). Assina o CONTRATO DE DISTRIBUIÇÃO.
- **REDISTRIBUIDOR**: captura o dado **indiretamente**, através de um Distribuidor (ex.: via Cedro, Nelogica etc.). Também assina o CONTRATO DE DISTRIBUIÇÃO — **é aqui que mora a resposta para "pessoa física ou empresa própria pode assinar para uso interno":** sim, mas precisa virar um "Redistribuidor" oficial da B3, com contrato próprio, **mesmo usando um vendor como fonte**. A política é explícita: *"O MARKET DATA B3 deverá ser contratado por todos os provedores de infraestrutura tecnológica intermediária que fornecerem solução que exiba o MARKET DATA B3, independentemente da finalidade."* — ou seja, construir seu próprio software que consome e processa o feed (mesmo só para uso interno, mesmo não expondo tela) já obriga contrato e pagamento à B3, além do que se paga ao vendor pela entrega técnica do dado.
- **Categoria "vendor/sub-vendor"** citada na página institucional não é uma categoria formal separada no documento — a Política usa apenas Distribuidor/Redistribuidor, e cita "FACILITADORES DE SERVIÇO" (agentes terceirizados que ajudam a distribuir, mas não têm contrato próprio com a B3) como o conceito mais próximo de "sub-vendor".
- **Non-display vs. display**: existe, sim, e é central para uso algorítmico. **NON-DISPLAY** é definido como "acesso ao MARKET DATA B3 por meio de um dispositivo que não esteja fornecendo a visualização" — processos, algoritmos de negociação, servidores. Duas variantes:
  - **Non-display por aplicação** (interno/externo, nacional/internacional) — cobrado por instância de aplicação.
  - **Non-display Enterprise** — número **ilimitado** de aplicações sob um único usuário, cobrado por usuário final.
- **Documentação exigida**: assinatura do **CONTRATO DE DISTRIBUIÇÃO** com 6-7 anexos (contatos, opções de uso/distribuição, dados cadastrais do Grupo econômico, dados do Distribuidor fornecedor, dados de Facilitadores, transferência de responsabilidade, tratamento LGPD) + envio de **RELATÓRIO MENSAL** (CSV/TXT) identificando cada usuário final por nome, CPF/CNPJ, e-mail, endereço, meio de acesso e profundidade acessada — sujeito a **auditoria da B3 com retroatividade de 12 a 24 meses**.
- Não existe "licença de uso interno mais barata" no sentido de simplificada — existe uma categoria comercial própria ("USO EXCLUSIVAMENTE INTERNO", ver tabela abaixo) que é mais barata que a distribuição externa, mas ainda exige o mesmo contrato formal, relatório mensal e auditoria.

### 4.3. Custos reais — valores públicos da tabela de preços (vigência a partir de 01/01/2025)

Fonte: Política Comercial de Market Data B3 v3.0.4, capítulo 13 (tabela de preços), documento público. Valores em R$ para instituição **Nacional**, dataset **Mercado Futuro e Câmbio** (onde estão WDO/WIN) — os valores de "Outras Instituições" (não PNP/PN) são os aplicáveis a uma empresa/pessoa fora do quadro de corretoras:

**Taxas fixas (mensais, cobradas junto com as variáveis):**

| Modalidade | Nacional |
|---|---|
| Distribuição Externa, Acesso Direto, Tempo Real (Outras Instituições) | R$ 48.314,57/mês |
| Distribuição Externa, Acesso Indireto, Tempo Real (Outras Instituições) | R$ 40.262,14/mês |
| **Uso Exclusivamente Interno, Acesso Direto** | **R$ 24.157,29/mês** |
| **Uso Exclusivamente Interno, Acesso Indireto (via um vendor)** | **R$ 16.104,86/mês** |

**Taxas variáveis (por usuário final/aplicação, mensais, dataset Mercado Futuro/Câmbio, Outras Instituições, Nacional):**

| Meio de acesso | Valor |
|---|---|
| Terminal/Internet, usuário profissional, L1 | R$ 144,95/mês |
| Terminal/Internet, usuário profissional, L2 | R$ 209,39/mês |
| Non-display por aplicação, interno | R$ 56,41/mês |
| Non-display por aplicação, externo | R$ 72,49/mês |
| Non-display Enterprise, por usuário final | R$ 1.610,51/mês |

**Conta prática mínima** para um sistema próprio de leitura de fluxo, uso 100% interno (não redistribuído), consumindo via um vendor (acesso indireto) e rodando como aplicação non-display: **R$ 16.104,86 (taxa fixa) + R$ 56,41 (non-display interno) ≈ R$ 16.161/mês (~R$ 194.000/ano) só de taxa B3** — **isso não inclui** o que o vendor (Cedro, Nelogica etc.) cobra pela entrega técnica do feed, nem conectividade. Se o acesso fosse direto (contratando conectividade própria com a B3 em vez de via vendor), a taxa fixa mensal sobe para R$ 24.157,29/mês (~R$ 290.000/ano).

**Custo de conectividade física**: a B3 confirma que o **FIX/FAST multicast só é distribuído via RCB (Rede de Comunicação B3) e RCCF2** — não há acesso via internet aberta para consumo de produção. A **única exceção documentada é para o ambiente de certificação**: *"Internet VPN: o cliente deve configurar um túnel GRE com a bolsa, para permitir tráfego multicast"* — ou seja, existe VPN só para testar/certificar a aplicação antes de ir para produção; o ambiente de produção real exige RCB/RCCF2 (link dedicado via operadora certificada) ou co-location. **O custo desse link/rede não está na Política Comercial de Market Data** (é cobrado à parte, pela infraestrutura de conectividade B3/operadoras) — não encontrei tarifário público para isso; precisaria consultar diretamente o GDS (gds@b3.com.br) ou a área de conectividade da B3.

**Conclusão de custo**: mesmo no cenário mais barato e mais restrito (uso interno, acesso indireto via vendor, non-display), o piso documentado é da ordem de **R$ 190-200 mil/ano só em taxas B3**, sem contar o vendor nem a conectividade. Isso está muito acima do custo de um projeto individual/pequena operação, mas não é "impossível" — é uma decisão de investimento, não uma barreira técnica.

### 4.4. Viabilidade técnica em Python

- **Especificação pública**: sim, existe e é detalhada. B3 publica: [UMDF Market Data Specification (FIX/FAST)](https://www.b3.com.br/data/files/83/C0/9E/B7/D3543910B371F339AC094EA8/UMDF_MarketDataSpecification.pdf) (protocolo, templates FAST, mecanismo de recovery, tipos de mensagem — 81 páginas), o [Binary UMDF Message Reference v2.2.0](https://www.b3.com.br/data/files/C4/A2/DF/11/E92599100A29E189AC094EA8/BinaryUMDF-MessageReference-v.2.2.0-enUS.pdf) (mensagens do canal SBE binário), e os templates FAST em XML na página [FIX/FAST UMDF para desenvolvedores](https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-desenvolvedores-e-vendors/fix-fast-umdf/), sob "Templates FAST" e "Reference Code".
- **Certificação obrigatória**: nenhum sistema pode ir para produção sem passar por um processo de certificação com a equipe da B3 (tradingcertification@b3.com.br) — isso é adicional ao custo comercial e trava o prazo de implantação em semanas/meses de desenvolvimento + agendamento de certificação.
- **Decoder de referência**: a própria B3 disponibiliza código-fonte de referência para decodificação FAST, **mas só em C++** (compilável com MSVC++ ou gcc/g++), **sem garantia e sem suporte** — a especificação diz textualmente: *"B3 does not provide support for any FAST decoders, including the reference code."*
- **Bibliotecas Python prontas**: **não encontrei nenhuma biblioteca Python aberta e mantida especificamente para decodificar o UMDF da B3** (nem FIX/FAST nem SBE binário). O único SDK comercial de terceiros identificado é o **OnixS Binary UMDF SBE Market Data Handler**, que oferece C++ e .NET — não Python, e é pago. Isso não prova que não exista nenhum projeto Python isolado em algum repositório privado ou pouco divulgado, mas nada de relevante apareceu nas buscas.
- **Um decoder em Python aguenta o volume?** A Cedro documentou, para o UMDF Conflated, um pico observado de **294 milhões de mensagens de market data em um dia**, com pico de **~90 mil mensagens/segundo** no agregado de todo o mercado (22/10/2021) — isso é para o feed consolidado, não para um único instrumento. Um canal filtrado só para WDO/WIN teria volume bem menor, mas ainda em milhares de mensagens/segundo em dias voláteis. **Avaliação honesta**: decodificar FAST (que usa compressão bit-a-bit com estado incremental) ou SBE binário em Python puro, mensagem a mensagem, em um laço `while True` de rede, é arriscado para não perder pacotes sob rajada — é o padrão do setor (e o motivo dos SDKs existentes serem C++/.NET) usar um núcleo de decodificação em C/C++/Rust (via `ctypes`/`cffi`/`pybind11`/PyO3) e só subir para Python na camada de agregação/estratégia. Construir esse núcleo do zero em C é um projeto de engenharia não trivial — semanas de trabalho especializado, já que a B3 não dá suporte ao decoder de referência.

### 4.5. Alternativa intermediária — vendors credenciados

| Vendor | O que entrega (confirmado nas fontes) | Faixa de preço |
|---|---|---|
| **Cedro Technologies** (Market Data Cedro / Crystal / Anywhere) | Redistribuição oficial B3, API REST (JSON), Socket e WebSocket; "quotes, book, trades" — não confirmei se o nível de book entregue é MBO ou MBP | Não público — contratação sob consulta via marketdatacloud.com.br |
| **Nelogica (ProfitDLL)** | Tick a tick, book completo, histórico de trades sob requisição, latência divulgada <10ms; existe conteúdo institucional da própria Nelogica ("Do tick ao dashboard: construa sua análise de players com a ProfitDLL") sugerindo suporte a alguma forma de análise de players/fluxo — **não consegui confirmar o conteúdo exato desse artigo** (bloqueado por acesso), então não posso afirmar se isso inclui identificação de corretora | Não público — vinculado a contrato de licença Profit Pro, sob consulta via corporativo@nelogica.com.br |
| **Trademap** | Aparece como vendor de mercado ("Assinaturas" no FAQ deles), mas não encontrei confirmação técnica de que ofereça feed de book/tick programável (parece mais voltado a plataforma de análise para usuário final do que a uma API B3) | Não confirmado |
| **Tryd (RTD)** | Cotação via Excel (DDE/RTD), não é feed programável de book — via de menor prioridade já registrada na Seção 2.4 | N/A |

**Nenhum dos vendors pesquisados publica preço nem confirma explicitamente se entrega MBO (ordem individual) ou apenas MBP (agregado)** — isso precisa ser perguntado diretamente a cada um antes de qualquer decisão de compra.

### 4.6. O ponto que decide tudo: dá para ver a corretora?

Este é o requisito central da leitura de fluxo ao estilo Gargantini (ver ordem individual + código de corretora/agente por trás dela). A pesquisa encontrou evidência **contra** a disponibilidade confiável desse dado, mesmo pagando pelo UMDF direto:

1. O próprio *Message Reference* do UMDF mostra os campos **288-MDEntryBuyer** e **289-MDEntrySeller** (que carregariam o código do comprador/vendedor em uma entrada de book ou trade) marcados como **"Sent on bids/offers, but not on MBP/TOB or anonymous trading"** e **"Not sent for anonymous trades"** — ou seja, esses campos só aparecem quando a negociação **não é anônima**, e nunca aparecem no nível comercial L2 (MBP).
2. O histórico de revisão da própria especificação registra, em **dezembro/2016**: *"Changed tags 288 and 289 for book and trades for anonymous trading"* — evidência de que a B3 ampliou o uso de negociação anônima ao longo do tempo.
3. Fora da especificação técnica, a B3 confirma que existe um mecanismo oficial de negociação anônima chamado **RLP (Retail Liquidity Provider)**, ativado pela própria corretora do cliente, no qual **a oferta não aparece no book** e **o volume via RLP pode chegar a até 15% do volume total negociado especificamente em WIN e WDO** — ou seja, uma fatia relevante e reconhecida do fluxo de varejo nesses dois contratos é estruturalmente anônima por desenho, não por limitação técnica do feed.

**Conclusão**: não há garantia — nem pagando o UMDF Binary mais caro — de ver o código de corretora por trás de cada ordem/negócio em WDO/WIN. Uma fração doa dados vem anônima por regra de negócio da B3 (RLP), e mesmo fora do RLP os campos de identificação de contraparte dependem do tipo de negociação. Isso é uma limitação de **política de mercado**, não de dinheiro: nem o distribuidor mais caro contorna isso.

### 4.7. Veredicto de 3 caminhos

**(A) MT5 grátis, agora**
- Qualidade de fluxo: ticks + book conforme o corretor expuser (tipicamente MBP/nível 1-2, não MBO); **não expõe corretora/agente por trás da ordem** — nenhuma corretora de varejo repassa esse dado ao cliente MT5.
- Custo: R$ 0.
- Prazo/atrito: dias — `pip install`, plugar no adapter já recomendado na Seção 4 (veredicto original).
- Veredicto: não atende ao requisito de ver corretora; atende bem a fluxo agregado (book nível 1-2 + tape reading clássico sem identidade de contraparte).

**(B) Vendor pago intermediário (Cedro / ProfitDLL)**
- Qualidade de fluxo: potencialmente tick a tick + book mais profundo/melhor latência que MT5; **não há confirmação pública de que qualquer um deles entregue MBO com identificação de corretora** — precisa perguntar diretamente antes de contratar. Mesmo que entreguem, a B3 despacha os campos 288/289 só fora de negociação anônima, então o RLP dos 15% de WIN/WDO continua invisível de qualquer forma.
- Custo: não público, mas claramente inferior ao acesso direto (dezenas a poucas centenas de R$/mês por usuário é o padrão do setor para non-display de varejo/profissional avançado — precisa cotar).
- Prazo/atrito: médio — processo comercial + integração via REST/WebSocket (Cedro) ou `ctypes` com DLL nativa (Nelogica), dias a poucas semanas.
- Veredicto: degrau intermediário sensato **se e somente se** a checagem prévia confirmar que o vendor entrega MBO com contraparte identificada — o que não está confirmado nesta pesquisa.

**(C) UMDF direto (Binary/FAST/Conflated)**
- Qualidade de fluxo: o mais completo tecnicamente disponível (book por ordem, latência mínima), mas **mesmo aqui a identificação de corretora não é garantida** para a fatia RLP/anônima do WIN/WDO (até 15% do volume) — ou seja, o caminho mais caro não resolve sozinho o requisito central da leitura Gargantini.
- Custo: piso documentado de **~R$ 190-200 mil/ano** só em taxas B3 (uso interno, acesso indireto via vendor, non-display) até ~R$ 290 mil/ano (acesso direto) — **sem contar** conectividade RCB/RCCF2 (custo não público) nem o desenvolvimento do decoder.
- Prazo/atrito: alto — contrato de distribuição com 6-7 anexos, relatório mensal auditável, certificação técnica obrigatória, e um decoder FAST/SBE que a B3 não suporta (provável necessidade de núcleo em C/C++/Rust). Meses de trabalho, não dias.
- Veredicto: **não recomendado para este projeto agora** — custo e atrito desproporcionais ao ganho, dado que nem resolve por completo o requisito de identificar corretora (o RLP é anônimo por regra de negócio, não por nível de acesso).

**Recomendação objetiva**: o requisito "ver ordem individual + código de corretora" **não é satisfeito garantidamente por nenhum dos três caminhos** para WDO/WIN, porque a B3 estruturalmente anonimiza até 15% do fluxo desses contratos via RLP e restringe os campos de identidade de contraparte a negociação não anônima. Antes de gastar em (B) ou (C), vale confirmar por e-mail com marketdata@b3.com.br (ou com a Cedro/Nelogica) **se a leitura de fluxo por corretora ainda é viável hoje para WDO/WIN**, e em que percentual do book — a resposta pode reduzir a ambição do projeto (fluxo agregado por perfil de player, não por corretora nomeada) independentemente de quanto se pague.

## 5. Veredicto de arquitetura

**Para tempo real (tick-a-tick + book), o caminho de menor atrito é o pacote `MetaTrader5`**: é grátis, oficial, `pip install`, funciona com corretoras BR já conhecidas (Clear/Rico/XP/Modalmais/Terra) e dá ticks + candles prontos, com book (DOM) condicionado ao que a corretora expuser via `market_book_add`/`market_book_get`. A limitação real é a ausência de streaming nativo (é tudo polling) e a incerteza sobre profundidade de book por corretora — isso deve ser validado empiricamente antes de comprometer a arquitetura ao DOM do MT5.

Se o projeto evoluir e exigir book completo multi-nível com latência de profissional, o próximo degrau é o **ProfitDLL da Nelogica** (melhor granularidade e latência divulgada, mas exige licença paga e integração via `ctypes` com uma DLL nativa — mais atrito de engenharia). **Cedro Crystal** é a alternativa institucional via REST/WebSocket, útil se quiser desacoplar de um terminal desktop rodando localmente, mas também é pago e sem SDK Python pronto. **B3 UMDF é inviável** para uso individual (custo/infra de distribuidor). **RTD do Tryd** e **APIs de corretoras** não são caminhos viáveis para um motor de fluxo em Python.

**Para histórico/replay**, não existe hoje fonte gratuita de tick-a-tick nem de book para WDO/WIN — o FTP público de negócios e o de ofertas (book) foram descontinuados (2020/2019). A opção paga oficial é a **B3 UP2DATA** (Times & Trades tick-a-tick, sem book reconstruído). Na prática, para este projeto a estratégia mais viável é: (1) usar `copy_ticks_range` do MT5 para o histórico recente que o corretor ainda mantiver (semanas/meses), e (2) **montar um gravador próprio desde já** (logger 24/7 capturando ticks + snapshots de book via MT5/ProfitDLL) para construir sua própria base de replay dali para frente — é a única forma de garantir profundidade de book histórico, já que nenhuma fonte externa (grátis ou paga) oferece isso hoje.

**Adaptador a construir primeiro**: um `MT5Adapter` único cobrindo três funções — (a) stream de ticks via polling de `symbol_info_tick`, (b) leitura de book via `market_book_add/get`, e (c) gravação simultânea em disco (parquet/csv por dia) para alimentar o replay futuro. Esse adaptador entrega tempo real e começa a resolver o histórico ao mesmo tempo, com custo zero e setup mínimo — e serve de base para depois trocar o transporte por ProfitDLL/Cedro sem reescrever a camada de replay.

---

## Fontes consultadas

- [Documentation on MQL5: market_book_get / Python Integration](https://www.mql5.com/en/docs/python_metatrader5/mt5marketbookget_py)
- [Documentation on MQL5: copy_ticks_range / Python Integration](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py)
- [Como baixar dados da B3 com MetaTrader 5 e Python | Asimov Academy](https://hub.asimov.academy/blog/como-baixar-dados-da-b3-com-metatrader-5-e-python/)
- [Histórico de Book de Ofertas B3 - Fórum MQL5](https://www.mql5.com/pt/forum/449407)
- [pypi.org/project/MetaTrader5](https://pypi.org/project/metatrader5)
- [Ecossistema ProfitDLL e primeiros passos – Nelogica](https://ajuda.nelogica.com.br/hc/pt-br/articles/22396517026203-Ecossistema-ProfitDLL-e-primeiros-passos)
- [Como obter acesso à ProfitDLL – Nelogica](https://ajuda.nelogica.com.br/hc/pt-br/articles/51583791325211-Como-obter-acesso-%C3%A0-ProfitDLL)
- [GitHub - marcusgarim/profit-DLL](https://github.com/marcusgarim/profit-DLL)
- [API B3 (Bolsa de Valores) – Market Data - Cedro Technologies](https://cedrotech.com/blog/api-b3-bolsa-de-valores-market-data/)
- [Market Data Cloud – APIs de Market Data em tempo real](https://www.marketdatacloud.com.br/)
- [Como ativar RTD e DDE? – Tryd](https://ajuda.tryd.com.br/hc/pt-br/articles/10730836194971-Como-ativar-RTD-e-DDE)
- [Perguntas frequentes | B3 (Market Data)](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/distribuidores/perguntas-frequentes/)
- [Política Comercial de Market Data B3](https://www.b3.com.br/data/files/6D/77/9D/65/0AB929106EEC8429AC094EA8/Politica%20Comercial%20de%20Market%20Data%20v3.0.4.1.pdf)
- [B3 Market Data Feed (UMDF) — Documentation](https://apis.io/apis/b3-exchange/b3-market-data-feed-umdf/)
- [Cotações históricas | B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
- [Sobre UP2DATA | B3](https://b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/up2data/sobre-up2data/)
- [UP2DATA ON DEMAND | B3](https://www.b3.com.br/pt_br/noticias/up2data-on-demand.htm)
- [Ajustes do pregão | B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/derivativos/s_ajuspreg/)
- [Backtester | Dados Históricos de ações da B3 [GRÁTIS]](https://backtester.com.br/)
- [Plataformas de difusão | B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/plataformas-de-difusao/)
- [Política Comercial de Market Data B3 v3.0.4 (PDF, com tabela de preços)](https://www.b3.com.br/data/files/6D/77/9D/65/0AB929106EEC8429AC094EA8/Politica%20Comercial%20de%20Market%20Data%20v3.0.4.1.pdf)
- [UMDF Market Data Specification (FIX/FAST) v2.2.0 (PDF)](https://www.b3.com.br/data/files/83/C0/9E/B7/D3543910B371F339AC094EA8/UMDF_MarketDataSpecification.pdf)
- [MARKET DATA B3: Binary UMDF Message Reference v2.2.0 (PDF)](https://www.b3.com.br/data/files/C4/A2/DF/11/E92599100A29E189AC094EA8/BinaryUMDF-MessageReference-v.2.2.0-enUS.pdf)
- [FIX/FAST UMDF | B3 (portal de desenvolvedores/vendors)](https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-desenvolvedores-e-vendors/fix-fast-umdf/)
- [FIX/FAST UMDF Conflated | B3](https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-desenvolvedores-e-vendors/fix-fast-umdf-conflated/)
- [B3 Binary UMDF SBE Market Data Handler SDK (OnixS, comercial)](https://www.onixs.biz/b3-binary-umdf-sbe-feed-market-data-handler.html)
- [RLP: como ativar? – Nelogica](https://blog.nelogica.com.br/rlp-o-que-e/)
- [Ecossistema ProfitDLL e primeiros passos – Nelogica](https://ajuda.nelogica.com.br/hc/pt-br/articles/22396517026203-Ecossistema-ProfitDLL-e-primeiros-passos)
- [Do tick ao dashboard: construa sua análise de players com a ProfitDLL – Nelogica (acesso bloqueado nesta pesquisa, referência não confirmada em detalhe)](https://ajuda.nelogica.com.br/hc/pt-br/articles/11966404695195-Do-tick-ao-dashboard-construa-sua-an%C3%A1lise-de-players-com-a-ProfitDLL)
- [Assinaturas – TradeMap](https://faq.trademap.com.br/hc/pt-br/categories/360005616393-Assinaturas)
