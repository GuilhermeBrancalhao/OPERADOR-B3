"""Registro das regras do método — a fonte única de procedência do produto.

Este módulo **não importa nenhum componente** deste pacote (os componentes é
que importam daqui). O motivo é auditoria: o registro tem de poder ser lido,
listado e conferido sem instanciar nada, e `pesquisa/regras_no_codigo.md` é
gerado/conferido contra ele.

Três coisas moram aqui:

- `REGRAS` — toda regra extraída das pesquisas, com citação e rótulo. Inclui
  as que **recusamos implementar**, com `implementada=False` e a nota que
  justifica a recusa. Uma regra ausente do registro é uma regra que o produto
  não sustenta.
- `PARAMETROS` — os limiares que a fonte não fixa, com o valor default e o
  motivo. Todo `IMPRECISO` que virou configuração aparece aqui.
- `_validar()` — roda no import e é o que impede o registro de mentir:
  parâmetro cujo `valores_na_fonte` tem dois números diferentes exige regra
  `IMPRECISO`; `regra_id` tem de existir; regra não implementada não pode
  ter parâmetro pendurado nela apontando para código vivo.

## Divergência declarada: cor

A fonte usa **verde/vermelho/amarelo** para direção ("tudo que for vermelho na
SG refere-se à leitura vendedora... tudo que é verde, leitura compradora...
amarelo... indecisão", `vs76O7j_inU`). **Este projeto não segue a fonte
nisso**, por decisão de acessibilidade registrada em `design/direcao_visual.md`
§3.1: o eixo direcional é **azul = compra / vermelho = venda**, e verde/âmbar
ficam reservados ao segundo canal (estado do sistema, evento detectado) —
verde↔vermelho colapsa em deuteranopia e protanopia (~8% dos homens).
As faixas, os limiares e os rótulos deste pacote vêm do método; a codificação
de cor, não. Por isso nenhum componente daqui emite cor: eles emitem
`fluxopro.core.eventos.Side`, e quem pinta decide na camada de UI.
"""

from __future__ import annotations

from fluxopro.metodologia.confianca import (
    Confianca,
    CitacaoInvalidaError,
    ParametroCalibravel,
    RegraDocumentada,
)

_C = Confianca

_LISTA: tuple[RegraDocumentada, ...] = (
    # ------------------------------------------------------------------
    # §1 — indicador percentual comprador × vendedor (já vive em motor/sinais)
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="dominancia.faixas",
        titulo="Faixas de convicção do percentual comprador × vendedor",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §1",
        citacao="aqui, ó, 50% 65 tá pré-direcional e acima de 70% direcional",
        fonte="zenDbXgFEEw",
        nota="Já implementado fora deste pacote, em fluxopro/motor/sinais.py "
        "(FaixaConviccao). Registrado aqui para o mapa ficar completo.",
    ),
    RegraDocumentada(
        id="dominancia.limiar_direcional",
        titulo="Corte de 'direcional' — a fonte dá dois números",
        confianca=_C.IMPRECISO,
        secao="metodologia_regras.md §1",
        citacao="acima de 75% já é uma amostragem mais direcional",
        fonte="vs76O7j_inU",
        nota="Outro vídeo (zenDbXgFEEw) diz 70%. Dois números para o mesmo "
        "conceito significam que o autor não usa corte fixo — vira "
        "ConfigMotorSinais.dominancia_minima, default 0.70 (extremo inferior, "
        "o mais permissivo, o que NÃO esconde o desacordo).",
    ),
    RegraDocumentada(
        id="dominancia.nao_e_gatilho",
        titulo="O percentual é filtro de viés, não gatilho de entrada",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §1",
        citacao="não significa que a partir do momento que ele bate os 70%",
        fonte="zenDbXgFEEw",
    ),
    # ------------------------------------------------------------------
    # §2 — exaustão: recusada
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="exaustao.conceito",
        titulo="Exaustão de movimento",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §2",
        nota="O termo 'exaustão'/'exausto' não ocorre em nenhuma transcrição "
        "lida. NÃO é regra do método e este pacote não a implementa. O "
        "DetectorExaustao do repo continua existindo como componente genérico "
        "de order flow, de origem interna do projeto — as duas fontes ficam "
        "separadas, é o precedente que este pacote segue.",
        implementada=False,
    ),
    # ------------------------------------------------------------------
    # §3 — Linha Azul
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="linha_azul.definicao",
        titulo="Linha azul = preço no cruzamento dos 50% desde a abertura",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §3",
        citacao="esta linha azul é o cruzamento dos 50%",
        fonte="SHjx2aHkmVA",
    ),
    RegraDocumentada(
        id="linha_azul.funcao_risco",
        titulo="É referência de contexto de risco, não sinal isolado",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §3",
        citacao="a ideia da linha azul é precisamente dar-te essa referência",
        fonte="SHjx2aHkmVA",
        nota="Por isso LeituraLinhaAzul não tem campo de gatilho nem de "
        "entrada: ela publica nível, lado e distância, e nada mais.",
    ),
    RegraDocumentada(
        id="linha_azul.stop",
        titulo="Serve de nível de invalidação / projeção de stop",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §3",
        citacao="projeção de stop para cima da linha",
        fonte="SHjx2aHkmVA",
    ),
    RegraDocumentada(
        id="linha_azul.plotagem",
        titulo="Quando a linha passa a existir mudou entre versões",
        confianca=_C.IMPRECISO,
        secao="metodologia_regras.md §3",
        citacao="agora a linha azul ela não plota mais na abertura do mercado",
        fonte="FmURmlN3boI",
        nota="Em SHjx2aHkmVA ela ancora 'desde a abertura'; em FmURmlN3boI o "
        "autor conta que mudou o comportamento. Duas versões da ferramenta, "
        "duas regras. Convenção DECLARADA desta implementação: a linha é o "
        "ÚLTIMO cruzamento de 50% da sessão (não o primeiro), e só existe "
        "depois de ConfigLinhaAzul.volume_minimo_ancoragem contratos "
        "atribuídos — 0 reproduz a versão antiga, >0 a nova.",
    ),
    RegraDocumentada(
        id="linha_azul.lado",
        titulo="Abaixo favorece venda, acima favorece compra",
        confianca=_C.INFERIDO,
        secao="metodologia_regras.md §3",
        citacao="quebrou a linha azul para cima",
        fonte="SHjx2aHkmVA",
        nota="A pesquisa marca INFERIDO: o autor não verbaliza a frase-título; "
        "a leitura decorre do conjunto de exemplos. Publicado como leitura "
        "rotulada INFERIDO, nunca como confirmação.",
    ),
    RegraDocumentada(
        id="linha_azul.janela_reset",
        titulo="Fórmula do 'acumulado' e reset intradiário",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §3",
        nota="A fonte só afirma que é 'o cruzamento dos 50%'; não há fórmula "
        "de acumulado nem regra de recálculo intradiário. Esta implementação "
        "acumula volume por agressor desde a abertura e reseta só na virada "
        "EXPLÍCITA de sessão, mesma política de EstadoMercado.",
    ),
    # ------------------------------------------------------------------
    # §4 e §5 — escora e sinal ultra: recusados
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="escora.formula",
        titulo="Renovação de oferta / escora — fórmula quantitativa",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §4",
        nota="Nos vídeos 'defender a região' é qualitativo. A contagem mínima "
        "de reposições (n_reposicoes_minimo, DetectorEscora) é engenharia "
        "interna do projeto, não extraída da fonte. Não reimplementado aqui.",
        implementada=False,
    ),
    RegraDocumentada(
        id="sinal_ultra.gatilho",
        titulo="Sinal Ultra (suporte/resistência reforçado)",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §5",
        nota="Saída de caixa-preta da ferramenta do autor: não há regra de "
        "preço/tempo/volume que defina quando dispara. Não implementado. Se "
        "entrar no Placar, entra como voto de um componente genérico do "
        "projeto, com o rótulo do componente, não como regra do método.",
        implementada=False,
    ),
    # ------------------------------------------------------------------
    # §6 — macro × micro
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="macro_micro.macro",
        titulo="Macro = movimento do dia inteiro",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §6",
        citacao="isto daqui é a macro, ou seja, todo o movimento do dia",
        fonte="EPqye9iLNig",
    ),
    RegraDocumentada(
        id="macro_micro.micro",
        titulo="Micro = movimento presente",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §6",
        citacao="Micro é sempre agora, macro o contexto de forma mais ampla",
        fonte="EPqye9iLNig",
    ),
    RegraDocumentada(
        id="macro_micro.hierarquia",
        titulo="A micro é quem manda no preço agora",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §6",
        citacao="a micro é quem manda no agora, no movimento do momento",
        fonte="xhpnmyQohPg",
    ),
    RegraDocumentada(
        id="macro_micro.escalas_incomparaveis",
        titulo="Macro e micro são medidas em escalas diferentes",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §6",
        citacao="não confunda 10%, achando que a micro só ficou 10% positiva",
        fonte="xhpnmyQohPg",
        nota="Regra de EXIBIÇÃO, e a API a torna difícil de violar: comparar "
        "duas MedidaContexto de escalas diferentes levanta "
        "EscalasIncomparaveisError, e a leitura conjunta não expõe nenhum "
        "número que misture as duas — só alinhamento de SENTIDO.",
    ),
    RegraDocumentada(
        id="macro_micro.contra_tendencia",
        titulo="Micro contra a macro é operação de maior risco",
        confianca=_C.IMPRECISO,
        secao="metodologia_regras.md §6",
        citacao="de contratendência, você não pode ser",
        fonte="6UPPrXrYeOY",
        nota="A frase está cortada na legenda e não há regra numérica de "
        "quando é permitido. Publicado como flag qualitativa "
        "(contra_tendencia), sem bloquear nada.",
    ),
    RegraDocumentada(
        id="macro_micro.janela_micro",
        titulo="Tamanho da janela da micro",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §6",
        nota="O autor nunca diz 'micro = últimos N minutos'. A macro tem "
        "âncora (desde a abertura); a micro não tem nenhuma. Vira parâmetro "
        "ConfigMacroMicro.janela_micro_ns, a calibrar com dados, e o valor "
        "usado viaja em toda leitura (MedidaContexto.janela_ns).",
    ),
    # ------------------------------------------------------------------
    # §7 — horários: recusado
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="horarios.tabela",
        titulo="Tabela de horários de operação",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §7",
        nota="Só existe a heurística qualitativa 'fim de pregão é pior' e a "
        "âncora da linha azul na abertura. Sem hora exata na fonte, nenhuma "
        "janela de horário é implementada como regra do método.",
        implementada=False,
    ),
    # ------------------------------------------------------------------
    # §8 — tamanho de posição
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="risco.mao_cheia",
        titulo="Região de alta convicção → tamanho máximo",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §8",
        citacao="essa aqui eu vou entrar com a mão cheia",
        fonte="6UPPrXrYeOY",
    ),
    RegraDocumentada(
        id="risco.mao_minima",
        titulo="Região turbulenta → reduzir tamanho",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §8",
        citacao="eu vou entrar menos pesado... entro com cinco",
        fonte="6UPPrXrYeOY",
    ),
    RegraDocumentada(
        id="risco.meia_mao",
        titulo="Metade do lote, com proteção rápida de parte",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §8",
        citacao="eu entro com a metade do lote",
        fonte="6UPPrXrYeOY",
        nota="Por ser literalmente 'metade', MEIA_MAO é DERIVADA de "
        "contratos_mao_cheia quando não configurada — não é um terceiro "
        "número solto.",
    ),
    RegraDocumentada(
        id="risco.gatilho_de_tamanho",
        titulo="O que decide 'região boa' × 'região turbulenta'",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §8",
        nota="O critério é qualitativo e depende de julgamento visual "
        "combinado (%, linha azul, macro/micro). Não há volatilidade, spread "
        "nem percentual que dispare a redução. Consequência na API: "
        "GestorRisco.avaliar EXIGE a QualidadeRegiao do operador — o sistema "
        "não infere, e não finge inferir.",
        implementada=False,
    ),
    RegraDocumentada(
        id="risco.numeros_de_contratos",
        titulo="Quantos contratos são 'mão cheia' e 'mão mínima'",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §8",
        nota="20, 10 e 5 são exemplos pessoais do autor, não tabela de regra. "
        "ConfigRisco nasce com 0 (não configurado) e GestorRisco.tamanho "
        "RECUSA responder até o operador informar o próprio lote.",
    ),
    # ------------------------------------------------------------------
    # §9 — limite de perdas
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="risco.tres_stops",
        titulo="Máximo de 3 stops seguidos na mesma região",
        confianca=_C.CONFIRMADO,
        secao="metodologia_regras.md §9",
        citacao="eu tenho uma regra que eu não passo de três",
        fonte="6UPPrXrYeOY",
        nota="O achado numérico mais sólido da fonte. É regra POR REGIÃO: "
        "atingido o limite, aquela região fica abandonada no dia; as outras "
        "seguem liberadas.",
    ),
    RegraDocumentada(
        id="risco.limite_diario_agregado",
        titulo="Limite diário de perdas somando todas as regiões",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §9",
        nota="O autor nunca menciona 'encerro o dia após X'. Não existe e NÃO "
        "foi inventado: GestorRisco não tem contador diário agregado, e "
        "N stops em N regiões distintas não bloqueiam uma região nova.",
        implementada=False,
    ),
    RegraDocumentada(
        id="risco.tamanho_de_regiao",
        titulo="O que delimita 'a mesma região'",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §9",
        nota="A fonte fala em 'região' sem definir amplitude. Vira "
        "ConfigRisco.tamanho_regiao_ticks (bucket de preço). O default é "
        "escolha de engenharia; o efeito de borda (dois stops a 1 tick de "
        "distância caindo em buckets vizinhos) é limitação conhecida.",
    ),
    # ------------------------------------------------------------------
    # §10 — alvo: recusado
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="alvo.formula",
        titulo="Onde ficam alvo 1 e alvo 2",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="metodologia_regras.md §10",
        nota="O conceito de alvo 1/alvo 2 existe e é usado para parciais, mas "
        "a regra de CÁLCULO não está na fonte (sem múltiplo de risco, sem "
        "projeção). Nenhum alvo é projetado por este pacote.",
        implementada=False,
    ),
    # ------------------------------------------------------------------
    # Estrutura (ferramenta_componentes.md §8 e §6.2) — caso WINFUT
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="estrutura.regime",
        titulo="Regime só muda quando perde a máxima/mínima do dia",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §8",
        citacao="candle vendedor... acha que o mercado tá fritando",
        fonte="Cbj66x1JXoA",
        nota="A citação é a REJEIÇÃO explícita de ler candle isolado como "
        "prova de mudança de estrutura. A regra positiva, na paráfrase da "
        "pesquisa (§8 item 1 e §6.2): perder mínima do dia — ou a região de "
        "abertura — é mudança real de regime; não perder é ruído, por mais "
        "forte que o candle pareça.",
    ),
    RegraDocumentada(
        id="estrutura.ruido",
        titulo="Movimento contra o regime que não quebra estrutura é ruído",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §8",
        citacao="ruído / ondulação momentânea",
        fonte="Cbj66x1JXoA",
    ),
    RegraDocumentada(
        id="estrutura.amplitude_do_ruido",
        titulo="Quão grande pode ser a 'barrigada' e ainda ser ruído",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="ferramenta_componentes.md §8",
        nota="Os '~1000 pontos' são a amplitude do dia narrado, em pontos de "
        "WIN — exemplo, não limiar. ConfigEstrutura.ruido_minimo_ticks nasce "
        "em 0: enquanto a estrutura segura, QUALQUER movimento contrário é "
        "ruído, que é literalmente o que a fonte afirma.",
    ),
    # ------------------------------------------------------------------
    # Velocímetro (ferramenta_componentes.md §3 e §7)
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="velocimetro.dois_eixos",
        titulo="Grandeza e manutenção são os dois eixos da leitura",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §3",
        citacao="535, ó, 537, 541... ela não tá perdendo o sinal",
        fonte="w8YGyNl5m24",
        nota="'Acelerar' na fonte é a variação do valor do contador de curto "
        "prazo ao longo do tempo, não velocidade de negócios.",
    ),
    RegraDocumentada(
        id="velocimetro.virada",
        titulo="Perder força / virar de sentido",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §3",
        citacao="tá 410, 389, 300... ela virou",
        fonte="w8YGyNl5m24",
    ),
    RegraDocumentada(
        id="velocimetro.escala_fixa",
        titulo="Escala absoluta do tipo 'acima de 250 = forte'",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="ferramenta_componentes.md §3",
        nota="Os números citados (400, 600, 1200, 1900) variam por dia e por "
        "ativo; a própria pesquisa desmente a tabela fixa que uma extração "
        "anterior tinha inventado. Consequência: o Velocimetro NÃO tem "
        "limiar absoluto nenhum — só magnitude RELATIVA ao histórico da "
        "sessão. É por isso que a leitura é invariante a escala.",
    ),
    RegraDocumentada(
        id="velocimetro.normalizacao_winfut",
        titulo="Normalizar por magnitude histórica e por persistência",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §7",
        citacao="em poucos minutos ele praticamente retrocede tudo",
        fonte="kzvx33vruic",
        nota="Caso WINFUT: a macro inverteu para +915 depois de picos de "
        "−1925 e devolveu tudo. Ler o valor instantâneo é insuficiente — "
        "exige (a) magnitude relativa ao histórico intradiário e (b) tempo "
        "de permanência. Os dois eixos são publicados separados.",
    ),
    # ------------------------------------------------------------------
    # Placar estatístico (ferramenta_componentes.md §2)
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="placar.meta_leitura",
        titulo="O placar é meta-leitura: soma sinais, não lê o mercado",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §2",
        citacao="ele lê os sinais que a SG já lê do mercado",
        fonte="Rwm3uzxZhhc",
        nota="Por isso Placar.registrar recebe os votos de fora e não assina "
        "o barramento: ele não tem leitura própria do mercado.",
    ),
    RegraDocumentada(
        id="placar.estabilidade",
        titulo="Placar estável = confluência real; oscilando = ruído",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §2",
        citacao="aguardar se de fato existe uma confluência mais estável",
        fonte="Rwm3uzxZhhc",
    ),
    RegraDocumentada(
        id="placar.goleada",
        titulo="Não operar contra a 'goleada'",
        confianca=_C.IMPRECISO,
        secao="ferramenta_componentes.md §2",
        citacao="goleada (4-0, 5-0)",
        fonte="Rwm3uzxZhhc",
        nota="Dois placares citados como goleada, com número máximo de fontes "
        "variando (até 5). O corte vira ConfigPlacar.diferenca_goleada.",
    ),
    RegraDocumentada(
        id="placar.aquecimento",
        titulo="Oscilação nos primeiros minutos é esperada e não se opera",
        confianca=_C.IMPRECISO,
        secao="ferramenta_componentes.md §2",
        citacao="nos primeiros minutos de pregão a oscilação é esperada",
        fonte="Rwm3uzxZhhc",
        nota="'Primeiros minutos' sem número → ConfigPlacar.aquecimento_ns. "
        "Citação na voz da pesquisa (paráfrase), não transcrição literal.",
    ),
    RegraDocumentada(
        id="placar.virada",
        titulo="Empate ou virada do placar = alerta de reversão",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §2",
        citacao="quando empata ou vira, é sinal de possível reversão",
        fonte="Rwm3uzxZhhc",
        nota="Citação na voz da pesquisa (paráfrase do trecho do vídeo), não "
        "transcrição literal do autor — registrado para não inflar a força "
        "da evidência.",
    ),
    RegraDocumentada(
        id="placar.fonte_llm",
        titulo="O 'auxílio do ChatGPT' como quinta fonte do placar",
        confianca=_C.CONFIRMADO,
        secao="ferramenta_componentes.md §2 e §4",
        citacao="não serve como um gatilho de entrada como a SG",
        fonte="_zs79_15iJQ",
        nota="Confirmado que existe na ferramenta original, e recusado aqui: "
        "é LLM consultivo com latência, que o próprio autor diz não servir de "
        "gatilho. O Placar aceita qualquer conjunto de votos, então quem "
        "quiser pode passá-lo — mas ele não é fonte embutida do produto.",
        implementada=False,
    ),
    # ------------------------------------------------------------------
    # Maker: recusado
    # ------------------------------------------------------------------
    RegraDocumentada(
        id="maker.formula",
        titulo="Maker — percentual de viés oculto dos market makers",
        confianca=_C.AUSENTE_NA_FONTE,
        secao="ferramenta_componentes.md §1",
        nota="O autor descreve o fenômeno-alvo mas nunca a fórmula, e o feed "
        "MT5 (sem RLP/identidade, book nível 1-2) pode não sustentar a "
        "fidelidade. Não implementado — qualquer proxy seria reinterpretação "
        "nossa, e entraria como componente genérico, não como regra do método.",
        implementada=False,
    ),
)

REGRAS: dict[str, RegraDocumentada] = {r.id: r for r in _LISTA}
"""Registro imutável na prática: montado no import, nunca cresce em runtime."""


PARAMETROS: tuple[ParametroCalibravel, ...] = (
    ParametroCalibravel(
        nome="ConfigLinhaAzul.convencao",
        padrao="ULTIMO_CRUZAMENTO",
        valores_na_fonte=("plota na abertura", "não plota na abertura"),
        motivo="O comportamento mudou entre versões da ferramenta do autor; "
        "não há uma regra única a copiar. Default: último cruzamento, porque "
        "a fonte usa a linha como referência VIVA de invalidação e um "
        "cruzamento das 9h01 deixa de descrever o risco de agora.",
        regra_id="linha_azul.plotagem",
    ),
    ParametroCalibravel(
        nome="ConfigLinhaAzul.volume_minimo_ancoragem",
        padrao=0,
        valores_na_fonte=(),
        motivo="Quantos contratos atribuídos a linha exige antes de existir. "
        "0 reproduz a versão que plota na abertura; qualquer valor > 0 "
        "reproduz a versão que 'não plota mais na abertura'.",
        regra_id="linha_azul.plotagem",
        unidade="contratos",
    ),
    ParametroCalibravel(
        nome="ConfigEstrutura.ruido_minimo_ticks",
        padrao=0,
        valores_na_fonte=(1000,),
        motivo="Os ~1000 pontos do dia narrado são exemplo, não limiar; 0 diz "
        "o que a fonte de fato afirma (enquanto a estrutura segura, o "
        "movimento contrário é ruído).",
        regra_id="estrutura.amplitude_do_ruido",
        unidade="ticks",
    ),
    ParametroCalibravel(
        nome="ConfigEstrutura.margem_ticks",
        padrao=0,
        valores_na_fonte=(),
        motivo="Quanto além do extremo conta como perda de estrutura. A fonte "
        "não dá tolerância; 0 é a leitura literal de 'perdeu a mínima'.",
        regra_id="estrutura.amplitude_do_ruido",
        unidade="ticks",
    ),
    ParametroCalibravel(
        nome="ConfigVelocimetro.janela_ns",
        padrao=15_000_000_000,
        valores_na_fonte=(),
        motivo="É a janela da micro, e a fonte nunca a define.",
        regra_id="macro_micro.janela_micro",
        unidade="ns",
    ),
    ParametroCalibravel(
        nome="ConfigVelocimetro.magnitude_relativa_minima",
        padrao=0.25,
        valores_na_fonte=(),
        motivo="Fração da magnitude de referência da sessão abaixo da qual o "
        "movimento é lido como PARADO. A fonte manda normalizar por "
        "magnitude (caso WINFUT) mas não dá o corte.",
        regra_id="velocimetro.normalizacao_winfut",
    ),
    ParametroCalibravel(
        nome="ConfigVelocimetro.tolerancia_variacao",
        padrao=0.10,
        valores_na_fonte=(),
        motivo="Banda morta entre ACELERANDO e DESACELERANDO. Sem ela o "
        "estado troca a cada tick; a fonte fala de 'renovar o valor', não de "
        "qualquer variação.",
        regra_id="velocimetro.escala_fixa",
    ),
    ParametroCalibravel(
        nome="ConfigVelocimetro.tamanho_topo_magnitude",
        padrao=16,
        valores_na_fonte=(),
        motivo="K da referência de magnitude (K-ésima maior da sessão). K−1 "
        "outliers não conseguem levantar a referência sozinhos.",
        regra_id="velocimetro.normalizacao_winfut",
    ),
    ParametroCalibravel(
        nome="ConfigPlacar.diferenca_goleada",
        padrao=4,
        valores_na_fonte=(4, 5),
        motivo="A fonte cita 4-0 e 5-0 como goleada. Default no menor dos "
        "dois, que é o mais conservador (alerta antes).",
        regra_id="placar.goleada",
        unidade="votos de diferença",
    ),
    ParametroCalibravel(
        nome="ConfigPlacar.estabilidade_minima_ns",
        padrao=30_000_000_000,
        valores_na_fonte=(),
        motivo="A fonte diz 'estável' sem duração nenhuma.",
        regra_id="placar.estabilidade",
        unidade="ns",
    ),
    ParametroCalibravel(
        nome="ConfigPlacar.aquecimento_ns",
        padrao=300_000_000_000,
        valores_na_fonte=(),
        motivo="'Primeiros minutos de pregão' sem número na fonte.",
        regra_id="placar.aquecimento",
        unidade="ns",
    ),
    ParametroCalibravel(
        nome="ConfigMacroMicro.janela_micro_ns",
        padrao=15_000_000_000,
        valores_na_fonte=(),
        motivo="A macro tem âncora (desde a abertura); a micro não tem "
        "nenhuma na fonte.",
        regra_id="macro_micro.janela_micro",
        unidade="ns",
    ),
    ParametroCalibravel(
        nome="ConfigRisco.stops_maximos_por_regiao",
        padrao=3,
        valores_na_fonte=(3,),
        motivo="Único número da fonte sobre limite de perda, e ele é firme "
        "('não passo de três'). Configurável para quem usa outro, mas o "
        "default É o da fonte.",
        regra_id="risco.tres_stops",
        unidade="stops",
    ),
    ParametroCalibravel(
        nome="ConfigRisco.tamanho_regiao_ticks",
        padrao=20,
        valores_na_fonte=(),
        motivo="A fonte fala em 'região' sem amplitude. O default é escolha "
        "de engenharia e precisa ser calibrado por instrumento.",
        regra_id="risco.tamanho_de_regiao",
        unidade="ticks",
    ),
    ParametroCalibravel(
        nome="ConfigRisco.contratos_mao_cheia",
        padrao=0,
        valores_na_fonte=(20,),
        motivo="Os 20 contratos são o lote pessoal do autor. 0 significa NÃO "
        "CONFIGURADO e faz o gestor recusar responder tamanho.",
        regra_id="risco.numeros_de_contratos",
        unidade="contratos",
    ),
    ParametroCalibravel(
        nome="ConfigRisco.contratos_mao_minima",
        padrao=0,
        valores_na_fonte=(5,),
        motivo="Os 5 contratos são exemplo pessoal do autor, pela mesma razão.",
        regra_id="risco.numeros_de_contratos",
        unidade="contratos",
    ),
)


def _validar() -> None:
    """Roda no import. Impede o registro de afirmar o que não sustenta."""
    if len(REGRAS) != len(_LISTA):
        raise CitacaoInvalidaError("id de regra duplicado no registro")

    nomes = set()
    for p in PARAMETROS:
        if p.nome in nomes:
            raise CitacaoInvalidaError(f"parametro duplicado: {p.nome}")
        nomes.add(p.nome)

        regra = REGRAS.get(p.regra_id)
        if regra is None:
            raise CitacaoInvalidaError(
                f"{p.nome}: regra_id {p.regra_id!r} nao existe no registro"
            )
        if not regra.implementada:
            raise CitacaoInvalidaError(
                f"{p.nome}: pendurado em {p.regra_id!r}, que esta marcada "
                "implementada=False. Parametro de configuracao e codigo vivo — "
                "os dois nao podem coexistir sem escolher um."
            )
        if p.fonte_diverge and regra.confianca is not Confianca.IMPRECISO:
            raise CitacaoInvalidaError(
                f"{p.nome}: a fonte da {p.valores_na_fonte} para "
                f"{p.regra_id!r}, que esta rotulada {regra.confianca.value}. "
                "Fonte que diverge exige rotulo IMPRECISO."
            )


_validar()


def regra(id_: str) -> RegraDocumentada:
    """Acesso pontual — levanta `KeyError` em id inexistente, de propósito."""
    return REGRAS[id_]


def regras_de(*ids: str) -> tuple[RegraDocumentada, ...]:
    """Tupla de regras por id, para pendurar numa leitura."""
    return tuple(REGRAS[i] for i in ids)


def parametros_de(classe: str) -> tuple[ParametroCalibravel, ...]:
    """Parâmetros declarados de uma `ConfigX` (ex.: `"ConfigRisco"`)."""
    return tuple(p for p in PARAMETROS if p.alvo[0] == classe)


def nao_implementadas() -> tuple[RegraDocumentada, ...]:
    """As regras que o produto recusa sustentar, com o motivo em `nota`."""
    return tuple(r for r in _LISTA if not r.implementada)
