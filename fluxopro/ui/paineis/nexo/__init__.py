"""Composicao macro da superficie NEXO do workspace OPERADOR B3.

Este pacote existe por **costura de propriedade**: cada regiao da superficie
mora em um modulo proprio com uma unica entrada
``desenhar(painter, rect, estado)``. ``PainelNexoMercadoASG.desenhar`` deixa de
pintar e passa a apenas *alocar retangulos* e delegar, de modo que cada regiao
possa evoluir sem que dois autores disputem o mesmo arquivo.

Contratos preservados desta fronteira:

* nenhum modulo assina barramento, le sessao ou infere microestrutura — todos
  recebem o mesmo ``EstadoNexo`` imutavel, montado uma vez por quadro a partir
  do snapshot ja congelado pela janela;
* preco continua ``int`` em ticks dentro do estado; a conversao para pixel
  acontece somente dentro de cada ``desenhar``;
* nenhuma regiao oferece callback, botao ou campo — a superficie inteira e
  consultiva e nao envia ordem.

O mapa de regioes abaixo e o **contrato de composicao**: fracoes do quadro,
borda a borda, sem moldura de cartao entre elas. Ele nao e estilo (cor, fonte,
espessura continuam vindo de ``tokens``/``tema_asg``); e geometria, e por isso
mora aqui em vez de ficar espalhado como numero solto no meio da pintura.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from PySide6.QtCore import QRect

# Nome da regiao -> (x0, y0, x1, y1) em fracao do quadro.
#
# Sangria: a leitura e continua, como a de um terminal de video, e nao uma
# grade de cartoes — nao ha margem externa nem moldura ENTRE regioes.
#
# ATENCAO — este comentario ja afirmou "a uniao das regioes cobre o quadro de
# borda a borda, sem vao", e isso era FALSO: em 28/08/2026 a medicao acusou
# 12,1% do quadro sem dono nenhum, incluindo um vao de ~440x216 px no meio da
# coluna central. Uma declaracao de contrato que o proprio mapa desmente e
# pior que nenhuma declaracao: ela faz o defeito passar despercebido em toda
# revisao que confia no texto em vez de medir.
#
# O que vale hoje, medido e travado por `test_ui_nexo_vies.py`:
#
# * a coluna central (x 0,40-0,63) e coberta de ponta a ponta por
#   `nucleo` + `vies`, que se encostam em y 0,42 sem vao nem sobreposicao;
# * o resto do quadro AINDA tem area sem dono, e ela esta enumerada em
#   `VAOS_SEM_DONO` abaixo. Cada entrada e um defeito conhecido a ser
#   resolvido pelo dono da regiao vizinha — nao um vao decorativo.
#
# Quem mexer no mapa mexe nas DUAS coisas: o retangulo e esta lista.
VAOS_SEM_DONO: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    # (vizinho a quem a faixa naturalmente pertence, (x0, y0, x1, y1))
    ("contexto", (0.34, 0.00, 0.63, 0.02)),
    ("contexto", (0.34, 0.02, 0.40, 0.42)),
    ("contexto", (0.34, 0.42, 0.40, 0.56)),
    ("forca/candles", (0.63, 0.22, 1.00, 0.23)),
    ("candles", (0.98, 0.23, 1.00, 0.85)),
    ("candles/pressao", (0.62, 0.85, 1.00, 0.86)),
    ("ladder", (0.00, 0.56, 0.02, 0.65)),
    ("banner/estatistica", (0.00, 0.78, 0.42, 0.79)),
)
REGIOES: dict[str, tuple[float, float, float, float]] = {
    # VAP alargado de 0,06 -> 0,11 do quadro (27/08/2026, pedido do operador:
    # "o VAP precisa ter um visual mais moderno e completo"). Em 0,06 a regiao
    # tinha ~115px para preco + barra + agressao: os precos saiam em 6pt e a
    # barra ficava com menos de 60px, ilegivel no tamanho real. 0,11 (~210px em
    # 1920) e a menor largura em que cabem, sem sobreposicao, a faixa de preco
    # em 8pt, a barra dividida por agressao e o numero de volume do nivel.
    # `contexto` cede o espaco porque a metade direita dela e area vazia de
    # respiro; nenhuma outra regiao muda.
    "ladder": (0.00, 0.00, 0.11, 0.56),
    "contexto": (0.11, 0.00, 0.34, 0.56),
    # 31/08/2026 — a faixa `niveis` (os cinco chips BID2/BID/ULT/ASK/ASK2)
    # saiu a pedido do operador ("esse quadro e desnecessario"): os cinco
    # precos ja estao no ladder (VAP) logo a esquerda, com volume e
    # agressao por nivel, e no topo do quadro. Era a MESMA informacao
    # ocupando 10% da altura da coluna. O espaco vai para `banner`, que
    # carrega o alerta de fluxo extremo e vivia espremido.
    "banner": (0.00, 0.56, 0.40, 0.78),
    "estatistica": (0.00, 0.79, 0.40, 1.00),
    "nucleo": (0.40, 0.02, 0.63, 0.42),
    # 28/08/2026 — `vies` foi de (0,42 · 0,62 · 0,62 · 1,00) para colar no
    # rodape de `nucleo` (y 0,42) e assumir a coluna central inteira
    # (x 0,40-0,63, a MESMA de `nucleo`).
    #
    # O que havia antes: um vao de ~440x216 px sem dono nenhum entre o
    # rodape do visor e o topo do OPERADOR IA — 94% cor de fundo, o maior
    # campo morto da tela, e bem na fronteira das duas regioes que o
    # operador chamou de "feias, muito simples". As duas regioes do par
    # liam como dois blocos separados por um buraco em vez de um
    # instrumento so. Contra `bar/02_superdom_a.png` e
    # `bar/06_medidores_agressao_a.png`, que nao tem um centimetro sem
    # leitura, o par perdia por causa do vao, nao do conteudo.
    #
    # As bordas laterais (0,40 e 0,63) sao as de `nucleo` de proposito: as
    # duas regioes do par passam a ter a MESMA coluna, entao a fronteira
    # entre elas e uma linha horizontal limpa e nao um degrau. Isso tambem
    # fecha as duas tiras de ~38px e ~19px que sobravam ladeando o
    # OPERADOR IA ate a base do quadro.
    #
    # O retangulo de `nucleo` NAO foi tocado.
    "vies": (0.40, 0.42, 0.63, 1.00),
    # 28/08/2026 — a caixa do Renko foi ENCOLHIDA de 0,33 para 0,22 e a das
    # velas cresceu para cima (0,34 -> 0,23). Motivo: desde que o eixo do
    # Renko passou a compartilhar o px/tick das velas
    # (`nexo/forca.py`, FATOR_ESCALA_VS_CANDLE), a altura da caixa deixou de
    # ser uma escolha de composicao e virou uma escolha de QUANTO PRECO a
    # regiao enquadra. Com 0,33 ela enquadrava ~25 pontos para uma serie de
    # micro que percorre 3 — 80% de area vazia, medida no retrato.
    #
    # Nenhuma vizinha perde: as duas unicas regioes desta coluna sao estas, e
    # a diferenca inteira vai para `candles`, que tinha dado de sobra para o
    # espaco (o pregao inteiro em 5M). O grafico de velas ganha ~115px de
    # altura em 1920x1080, o que por sua vez AUMENTA o px/tick dele — e o
    # tijolo do Renko acompanha, porque e a mesma escala.
    "forca": (0.63, 0.00, 1.00, 0.22),
    "candles": (0.63, 0.23, 0.98, 0.85),
    "pressao": (0.63, 0.86, 1.00, 1.00),
}

# Ordem de pintura. Regioes sem sobreposicao hoje: a faixa `niveis`, unica que
# avancava sobre as vizinhas, saiu em 31/08/2026 (ver o comentario em REGIOES).
ORDEM_DESENHO: tuple[str, ...] = (
    "ladder",
    "contexto",
    "forca",
    "candles",
    "nucleo",
    "vies",
    "estatistica",
    "banner",
    "pressao",
)

# Altura, em pixels, da linha de ressalva permanente no rodape do quadro. Ela
# nao e cromo decorativo: e a declaracao de que a superficie e consultiva, e
# por contrato de projeto nao pode sumir. Fica fora da area das regioes para
# nao ser sobreposta.
ALTURA_RESSALVA = 13


@dataclass(frozen=True)
class EstadoNexo:
    """Retrato imutavel de um quadro, unico insumo de toda regiao.

    Nao carrega referencia ao painel nem ao feed: uma regiao ve exatamente o
    que esta aqui e nada mais. ``serie`` ja vem como tupla (o ``deque`` vivo
    do painel nunca atravessa a fronteira) e ``precos`` seguem ``int`` em
    ticks.

    ``tijolos_renko``/``fase_renko``/``alvos_renko`` e ``candles_m15`` vem de
    ``fluxopro.analytics.renko``/``candle_temporal`` — agregadores puros
    alimentados por chamada direta (nunca por assinatura de barramento),
    ja em forma de tupla/objeto imutavel antes de cruzar para a regiao.
    Default vazio para nao quebrar quem constroi ``EstadoNexo`` sem eles.
    """

    snapshot: object
    serie: tuple[tuple[int, int, float, int], ...]
    grid: object
    paleta: object
    maker: object | None
    leituras: tuple[tuple[str, object], ...]
    largura: int
    altura: int
    represado_s: float = 0.0
    """Ha quantos segundos o termometro de agressao esta preso no EQUILIBRIO
    por a agressao ser fraca demais para o periodo (`asg.VolanteGauge`).

    `0.0` quando nao esta preso. Existe para que o CUSTO do volante — a
    cauda de atraso, que em virada fraca e medida em minutos — apareca na
    tela e nao so na docstring; ver `nexo/contexto.py`. Default zero para
    nao quebrar quem constroi `EstadoNexo` sem ele.
    """

    tijolos_renko: tuple[object, ...] = ()
    fase_renko: object = None
    alvos_renko: object | None = None
    escala_candle_px_por_tick: float = 0.0
    """Pixels por tick do eixo vertical da regiao de VELAS, medido no quadro
    corrente por `nexo.candles.px_por_tick`.

    Existe para uma coisa so: o Renko (`nexo/forca.py`) desenhar na MESMA
    escala vertical do grafico logo abaixo. Achado do operador (27/08/2026):
    "esses renkos precisam ficar em tamanhos proporcionais aos candles
    abaixo". Medido em 28/08/2026 antes da amarracao: ~44,6 px/pt no Renko
    contra ~13,7 px/pt no candle — 3,3x, entao o olho comparava amplitudes
    falsas entre uma regiao e a vizinha.

    Preenchido em `asg.py` no momento do desenho (e o unico ponto que conhece
    os retangulos das duas regioes); `0.0` significa "ainda sem escala",
    e quem consome degrada para a propria escala, nunca inventa numero.
    """

    renko_tamanho_ticks: int = 0
    """Tamanho ATUAL do tijolo Renko em ticks (dinamico desde a Fase 1 — ver
    `fluxopro.analytics.renko.Renko.tamanho_tijolo_ticks`). Achado do
    operador (27/08/2026): o rotulo "RENKO · 4 PTS" ficou cravado em
    forca.py mesmo depois do tijolo deixar de ser fixo — este campo existe
    para o rotulo mostrar o tamanho de verdade."""
    candles_m15: tuple[object, ...] = ()
    vap_niveis: tuple[tuple[int, int, int, int, bool], ...] = ()
    vap_poc: int | None = None
    vap_timeframe_min: int = 0
    """0 = sessao inteira; 5/15 = perfil recortado dos ultimos N minutos."""
    vap_val: int | None = None
    vap_vah: int | None = None
    vap_volume_total: int = 0
    """Volume total do perfil VAP ATIVO (sessao inteira quando
    `vap_timeframe_min == 0`, senao o recorte de 5/15 min). Existe porque
    `vap_niveis` e truncado nos 120 maiores niveis: somar as tuplas daria um
    total quase certo e silenciosamente errado. Fonte: `VolumeProfile.volume_total`."""
    risco_volatilidade: float = 0.0
    alerta_exaustao: tuple[str, float] | None = None
    sinal_ultra: object | None = None
    """``SinalUltraSnapshot`` (fluxopro.asg.sinal_ultra) do quadro, ou None.
    Filtro adicional, construido do zero por este projeto — ver docstring de
    sinal_ultra.py. `None` so quando o painel que constroi EstadoNexo nao o
    calcula (compatibilidade com pontos de montagem antigos/testes)."""

    regime: object | None = None
    """``LinhaMatrizASG`` do REGIME do dia, ja COERENTE — ou None.

    Existe para que a celula REGIME do visor central (`nucleo.py`) nao
    precise decidir cor por conta propria. Ate 28/08/2026 aquele cartao
    pintava o valor direcional (COMPRADOR/VENDEDOR) em ciano fixo,
    independente da direcao: a palavra direcional mais destacada da tela
    sem o eixo de cor do quadro, e o mesmo ciano significando tambem
    "regime vendedor" (pendencia ja registrada por escrito em
    `vies.py`).

    Disciplina desta fronteira — a mesma de `leituras` — **um numero, um
    sinal**: `regime.direcao`, `regime.forca` e `regime.valor` apontam
    todos para o mesmo lado (garantido por `asg.leitura_e_coerente`), de
    modo que quem desenha so precisa consumir
    ``_asg._cor_nexo_direcao(estado.regime.direcao)`` em vez de escolher
    um token. `None` quando o snapshot ainda nao tem a linha REGIME."""

    candles_timeframe_min: int = 5
    """5 ou 15 — qual agregador de candle esta selecionado (pedido do
    operador, 27/08/2026: "de a opcao de time de 5M e 15M editavel"). O
    painel mantem os DOIS `CandleTemporal` sempre alimentados (ver asg.py);
    isto so diz qual dos dois `candles_m15` representa neste quadro."""

    candles_offset: int = 0
    """Quantos candles mais recentes ficam FORA da janela visivel — 0 e o
    presente (ao vivo). Cresce quando o operador arrasta o grafico pra
    tras. `nexo/candles.py` fatia `candles_m15` por isto antes de recortar
    as ultimas N velas visiveis; nunca descarta o candle em si, so a
    janela de exibicao."""

    candles_cursor: tuple[int, int] | None = None
    """(x, y) do cursor DENTRO da regiao de candles, ou None. Alimenta o
    crosshair e a leitura O/H/L/C da vela apontada (achado de 28/08/2026: o
    operador conseguia ampliar a vela mas nao ler o preco dela). E so
    posicao de mouse: nao entra em calculo, decisao ou gravacao."""

    candles_velas_visiveis: int | None = None
    """ZOOM DE TEMPO: quantas velas o operador quer ver na janela. `None` =
    janela do pregao inteiro (o padrao). Vem da roda do mouse sobre o
    grafico ou do arrasto horizontal sobre a escala de tempo (pedido do
    operador, 27/08/2026: "eu podendo mexer no grafico na escala
    arrastando"). `nexo/candles.py` limita entre VELAS_MIN e o pregao."""

    candles_zoom_preco: float = 1.0
    """ZOOM DE PRECO: fator sobre a faixa de precos visivel, ancorado no
    centro dela. 1,0 = a faixa das velas cabe inteira; >1 amplia; <1 achata.
    Vem do arrasto vertical sobre a escala de preco (ou da roda sobre ela).
    So recorta a exibicao — nao altera candle, tick nem grade."""

    dominancia_snapshot: object | None = None
    """``DominanciaSnapshot`` (fluxopro.analytics.dominancia) do quadro, ou
    None. Motor determinístico construído a partir de
    ``INSTRUCOES_CLAUDE_DOMINANCIA_COMPRADOR_VENDEDOR.md`` (pasta Codex,
    trazido pelo operador) — read-only, ULTRA com histerese multi-condição,
    Q6. Ver `nexo/dominancia.py` para o mapeamento e `nexo/pressao.py` para
    o desenho. `None` só quando o painel que constrói `EstadoNexo` não o
    calcula (compatibilidade com pontos de montagem antigos/testes)."""

    sr_snapshot: object | None = None
    analise_ia: object | None = None
    """Pacote da analise consultiva do Claude:
    ``(EstadoAnalise, AnaliseMercado | None, motivo, idade_s)``, publicado
    por `PainelNexoMercadoASG._pacote_analise`. `None` quando a analise
    esta desligada (`FLUXOPRO_ANALISE_IA=0`). A chamada ao CLI acontece
    numa thread propria (ver `fluxopro/analytics/analise_claude.py`) — este
    campo carrega so o ULTIMO resultado ja pronto, nunca uma promessa."""
    """``SuporteResistenciaSnapshot`` (fluxopro.analytics.suporte_resistencia)
    do quadro, ou None. Motor construido do zero por este projeto a partir
    de `INSTRUCOES_CLAUDE_SUPORTE_RESISTENCIA.md` (pasta Codex, trazido pelo
    operador) — read-only, nunca gera intencao de ordem. `None` so quando o
    painel que constroi EstadoNexo nao o calcula (compatibilidade com
    pontos de montagem antigos/testes); ver `nexo/estatistica.py` para o
    desenho e `fluxopro/ui/paineis/asg.py::_montar_entrada_sr` para o
    mapeamento dos 8 componentes a partir do que o projeto ja calcula."""


def retangulos(quadro: QRect) -> dict[str, QRect]:
    """Traduz o mapa de fracoes em retangulos inteiros dentro de ``quadro``.

    Arredonda nas bordas (e nao na largura) para que regioes vizinhas encostem
    exatamente, sem costura de um pixel entre elas.
    """

    saida: dict[str, QRect] = {}
    for nome, (fx0, fy0, fx1, fy1) in REGIOES.items():
        x0 = quadro.left() + round(quadro.width() * fx0)
        x1 = quadro.left() + round(quadro.width() * fx1)
        y0 = quadro.top() + round(quadro.height() * fy0)
        y1 = quadro.top() + round(quadro.height() * fy1)
        saida[nome] = QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
    return saida


_MODULOS: dict[str, ModuleType] = {}


def modulo(nome: str) -> ModuleType:
    """Importa a regiao sob demanda.

    O import e tardio de proposito: os modulos de regiao dependem de
    ``paineis.asg`` (enums de direcao, resolucao de cor por estado) e
    ``paineis.asg`` depende deste pacote. Importar so no primeiro quadro
    desfaz o ciclo sem exigir que ``asg`` exporte nada novo.

    A resolucao e por ``import`` literal, um por nome fixo de
    ``ORDEM_DESENHO`` — nunca ``importlib.import_module`` com string
    formatada. O auditor de ordens (`scripts/auditoria_asg.py`) reprova
    qualquer import dinamico por principio (poderia carregar API de
    corretora); aqui nao ha string vinda de fora, mas o padrao textual e
    identico ao de um carregador de plugin de verdade, entao a forma
    literal e a unica que passa o portao sem exigir excecao no auditor.
    """

    modulo_regiao = _MODULOS.get(nome)
    if modulo_regiao is not None:
        return modulo_regiao
    if nome not in ORDEM_DESENHO:
        raise ValueError(f"regiao desconhecida: {nome!r}")

    from . import (
        banner,
        candles,
        contexto,
        estatistica,
        forca,
        ladder,
        niveis,
        nucleo,
        pressao,
        vies,
    )

    _MODULOS.update(
        {
            "banner": banner,
            "candles": candles,
            "contexto": contexto,
            "estatistica": estatistica,
            "forca": forca,
            "ladder": ladder,
            "niveis": niveis,
            "nucleo": nucleo,
            "pressao": pressao,
            "vies": vies,
        }
    )
    return _MODULOS[nome]


__all__ = [
    "ALTURA_RESSALVA",
    "EstadoNexo",
    "ORDEM_DESENHO",
    "REGIOES",
    "modulo",
    "retangulos",
]
