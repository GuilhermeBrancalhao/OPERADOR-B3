"""`SessaoFluxo` — o produto montado: todas as peças instanciadas e ligadas.

Antes disto, `MotorSinais` e `InferidorMBP` não eram importados por módulo de
produção nenhum (registrado em `criticas/nucleo_r2.md:371-372`): as peças
existiam, testadas, e o pipeline nunca tinha rodado inteiro. Este arquivo é o
lugar onde a cadeia existe de verdade:

    fonte -> Barramento -> EstadoMercado -> analytics -> InferidorMBP
          -> LivroMBO -> detectores -> PerfilPlayer -> MotorSinais
          -> LeitorMetodo -> saída

Ver `fluxopro/app/config.py` para a ordem de entrega e por quê.

## Duas decisões que não são óbvias

**1. O perfil que o motor lê é de SESSÃO, não o `VolumeProfilePorPeriodo`.**
`MotorSinais` guarda uma referência fixa a um `VolumeProfile` e chama
`value_area()` nela. `VolumeProfilePorPeriodo` *troca* o objeto do perfil
corrente a cada bucket de tempo — a referência que o motor segurasse viraria o
perfil de uma hora atrás, em silêncio, na virada do bucket. Então a montagem
mantém um `VolumeProfile` próprio, de sessão, alimentado em
`PRIORIDADE_PERFIL_SESSAO`, e é ele que o motor recebe. O
`VolumeProfilePorPeriodo` continua existindo para leitura por período (é o que
uma UI desenha), sem ser caminho crítico do motor. O custo do duplo registro é
um `dict.setdefault` + duas somas por trade.

**2. Detecção vinda do livro inferido não pode sair com confiança 1.0.**
`DetectorEscora`, `DetectorIcebergPorRecarga` e `DetectorLiquidezFantasma` só
rodam sobre o `LivroMBO`, que em fonte MT5/simulador é **inteiramente
sintético** (montado pelo `InferidorMBP` a partir de book agregado). Publicar
isso como fato apagaria a distinção observado × inferido, que é a virtude
declarada do projeto.

Isso já foi corrigido NA ORIGEM: `microestrutura/detectores.py` propaga a
confiança da cadeia de `OrdemEvento` que sustenta cada detecção (política do
mínimo — ver a docstring daquele módulo). O que esta camada faz é duas coisas:

* **fiação** — `_ligar_livro` chama `detector.acompanhar(livro)` nos três
  detectores de livro ANTES de assinar `_ao_ordem_evento`, para que o evento
  gatilho já esteja na cadeia quando `verificar` roda. Sem essa linha o
  mecanismo existe e fica inerte, e toda detecção sai `DESCONHECIDA`;
* **fronteira** — `DeteccaoAnotada` carrega `fonte` e
  `confianca_efetiva = min(confianca_do_detector, confianca_do_gatilho)`.
  Era produto enquanto o detector emitia 1.0 fixo; com a propagação viva, o
  produto cobraria a mesma incerteza duas vezes (0,55 × 0,55 = 0,3025). Ver
  `SessaoFluxo._emitir_deteccao`.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CandleDelta, ConfigDelta, CumulativeDelta
from fluxopro.analytics.footprint import (
    Footprint,
    FootprintPorTimeframe,
    NivelFootprint,
    _FootprintFechado,
)
from fluxopro.analytics.volume_profile import (
    ConfigVolumeProfile,
    NivelVolume,
    VolumeProfile,
    VolumeProfilePorPeriodo,
)
from fluxopro.analytics.vwap import VWAP
from fluxopro.app.config import (
    PRIORIDADE_ANALYTICS,
    PRIORIDADE_ASG,
    PRIORIDADE_FEED_QUALITY,
    PRIORIDADE_MAKER,
    PRIORIDADE_METODO,
    PRIORIDADE_MICRO,
    PRIORIDADE_MOTOR,
    PRIORIDADE_PERFIL_SESSAO,
    PRIORIDADE_SAIDA,
    ConfigOperacao,
    FonteDados,
)
from fluxopro.app.shadow_runtime import AsyncShadowWriter, ShadowRuntimeSnapshot
from fluxopro.asg import (
    DecisionSnapshot,
    LeituraASG,
    MakerProxy,
    MakerProxySnapshot,
    MotorDecisaoASG,
    ProcedenciaASG,
    RegiaoOperacional,
)
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import BookDelta, BookSnapshot, Trade
from fluxopro.dados.feed_observavel import FeedQualityMonitor, FeedQualityObserver
from fluxopro.dados.qualidade import (
    AggressorQuality,
    BookKind,
    FeedQualitySnapshot,
    FeedSource,
)
from fluxopro.metodologia.leitura import LeitorMetodo, LeituraMetodo
from fluxopro.microestrutura.detectores import (
    Deteccao,
    DetectorAbsorcao,
    DetectorClipInstitucional,
    DetectorEscora,
    DetectorExaustao,
    DetectorIcebergPorRecarga,
    DetectorLiquidezFantasma,
    TipoDeteccao,
)
from fluxopro.microestrutura.eventos_mbo import (
    CONFIANCA_OBSERVADO,
    FonteMicro,
    OrdemEvento,
    TipoEventoOrdem,
)
from fluxopro.microestrutura.inferencia_mbp import InferidorMBP
from fluxopro.microestrutura.livro_mbo import CruzamentoLivro, LivroMBO
from fluxopro.microestrutura.perfil_player import PerfilPlayer
from fluxopro.motor.sinais import EstagioSinal, MotorSinais, Sinal
from fluxopro.shadow import AmostraFeatures, SidecarShadow


@dataclass(frozen=True, slots=True)
class DeteccaoAnotada:
    """`Deteccao` + a procedência do dado que a gerou.

    `confianca_efetiva` é o MÍNIMO entre a confiança que o detector propagou e
    a do `OrdemEvento` gatilho (1.0 quando o gatilho foi o tape, que é
    observado). Ver `SessaoFluxo._emitir_deteccao` para por que mínimo e não
    produto.

    Isto deixou de ser uma cota grosseira: `detectores.py` passou a propagar o
    mínimo da cadeia inteira, então uma escora de três reposições inferidas sai
    com a confiança da PIOR das três, não só com a da última. O `min` daqui
    permanece como rede: cobre o caso de detector sem cadeia registrada.
    """

    deteccao: Deteccao
    fonte: FonteMicro
    confianca_efetiva: float

    @property
    def inferida(self) -> bool:
        return self.confianca_efetiva < CONFIANCA_OBSERVADO


@dataclass(slots=True)
class Contadores:
    """Um contador POR ELO da cadeia, de propósito.

    `n_trades_bus`, `n_trades_perfil_sessao`, `n_trades_micro` e
    `n_trades_motor` medem a mesma coisa em quatro pontos diferentes do
    pipeline. Com tudo ligado eles têm de ser IGUAIS — é assim que a
    desconexão de qualquer peça vira um teste vermelho em vez de um silêncio
    (`tests/test_app_pipeline.py::test_severar_qualquer_elo_derruba_a_verificacao`).

    Escopo: são contadores da EXECUÇÃO, não da sessão de pregão —
    `iniciar_nova_sessao` não os zera de propósito, para que um processo que
    atravessa a virada continue sabendo quantos eventos processou no total.
    """

    n_trades_bus: int = 0
    n_snapshots_bus: int = 0
    n_deltas_bus: int = 0

    n_trades_perfil_sessao: int = 0
    n_trades_micro: int = 0
    n_snapshots_micro: int = 0
    n_deltas_micro: int = 0
    n_trades_motor: int = 0
    n_trades_metodo: int = 0

    n_ordem_eventos: int = 0
    n_ordem_eventos_inferidos: int = 0
    n_cruzamentos_livro: int = 0

    n_sinais_emitidos: int = 0
    n_deteccoes: int = 0
    n_deteccoes_inferidas: int = 0

    sinais_por_estagio: dict[EstagioSinal, int] = field(default_factory=dict)
    deteccoes_por_tipo: dict[TipoDeteccao, int] = field(default_factory=dict)
    ordem_eventos_por_tipo: dict[TipoEventoOrdem, int] = field(default_factory=dict)

    ts_primeiro_ns: int | None = None
    ts_ultimo_ns: int | None = None

    @property
    def n_eventos_bus(self) -> int:
        return self.n_trades_bus + self.n_snapshots_bus + self.n_deltas_bus

    @property
    def duracao_tape_ns(self) -> int:
        if self.ts_primeiro_ns is None or self.ts_ultimo_ns is None:
            return 0
        return self.ts_ultimo_ns - self.ts_primeiro_ns


PRIORIDADE_MARCA_THREAD = PRIORIDADE_ANALYTICS - 1
"""Antes de TUDO — inclusive dos analytics.

Este assinante não calcula nada: só carimba qual thread está publicando. Ele
tem de rodar antes do primeiro acumulador tocar no próprio dicionário, porque
é justamente esse carimbo que decide se montar o retrato inline é seguro (ver
`SessaoFluxo.retrato_de_analytics`). Carimbar depois deixaria uma janela em
que o primeiro trade da sessão já mutou o perfil e a UI ainda acha que
ninguém publicou."""


# ----------------------------------------------------------------------
# O retrato de analytics — congelado do lado de quem escreve
# ----------------------------------------------------------------------
# `derivar_footprint`, `derivar_perfil` e `derivar_delta` (em `ui/paineis/`)
# ITERAM coleções vivas: `VolumeProfile._niveis`, os níveis do candle do
# footprint, o histórico do delta. Chamá-los do lado do Qt enquanto a thread
# da fonte publica levanta `dictionary changed size during iteration` — foi o
# que derrubou o primeiro retrato da composição com 9.098 negócios.
#
# As três classes abaixo são DUBLÊS IMUTÁVEIS: expõem exatamente os nomes que
# aqueles três `derivar_*` leem, e nada mais. A UI continua chamando as mesmas
# funções, sobre um objeto que não tem thread nenhuma escrevendo nele.
#
# O congelamento acontece **na thread que publica**, nunca na do Qt. Copiar do
# lado do Qt trocaria a exceção por leitura RASGADA — um perfil com níveis de
# dois instantes, que não levanta erro e mente em silêncio. A exceção é o
# comportamento bom comparado a isso.


@dataclass(frozen=True, slots=True)
class FonteFootprintCongelada:
    """Dublê de `FootprintPorTimeframe` para leitura de um quadro.

    `footprints_fechados` vem **truncado em `n_colunas`**, não completo. Duas
    razões, e as duas são lei do projeto: a estrutura é limitada pela TELA
    (`derivar_footprint` só olha `[-(n_colunas-1):]` ou `[-1]`), e a
    propriedade homônima do acumulador constrói uma tupla da sessão inteira a
    cada acesso — tocá-la por quadro trocaria uma corrida por um custo
    O(sessão). O corte é feito por fatia sobre a lista interna, O(colunas).
    """

    footprint_atual: Footprint | None
    _inicio_atual_ns: int | None
    footprints_fechados: tuple[_FootprintFechado, ...]


@dataclass(frozen=True, slots=True)
class FontePerfilCongelada:
    """Dublê de `VolumeProfile`.

    `poc` e `value_area()` chegam PRÉ-CALCULADOS: no acumulador vivo os dois
    varrem o dicionário inteiro, e refazer isso do lado do Qt seria pagar duas
    varreduras por quadro sobre uma coleção que a fonte está mudando.

    `niveis_ordenados()` devolve a sessão inteira, e isso é deliberado:
    `derivar_perfil` decide `poc_empatado` contando níveis de MESMO volume
    entre TODOS, não entre os visíveis. Truncar aqui pela faixa da tela faria
    o painel dizer "POC empatado" com base numa amostra — trocar uma corrida
    por uma mentira mais barata. A grandeza é o número de PREÇOS negociados no
    dia (a amplitude), não o número de eventos; é a mesma cardinalidade que o
    acumulador já mantém, e a cópia é transitória de um quadro.
    """

    config: ConfigVolumeProfile
    volume_total: int
    volume_nao_atribuido: int
    poc: int | None
    _ordenados: tuple[tuple[int, NivelVolume], ...]
    _value_area: tuple[int, int] | None

    def niveis_ordenados(self) -> list[tuple[int, NivelVolume]]:
        return list(self._ordenados)

    def value_area(self, pct: float | None = None) -> tuple[int, int] | None:
        return self._value_area


@dataclass(frozen=True, slots=True)
class FonteDeltaCongelada:
    """Dublê de `CumulativeDelta`.

    `historico` vem truncado em `n_colunas` pela mesma razão do footprint. Por
    isso `delta_divergente()` NÃO é recalculado sobre o recorte: a janela de
    divergência é configurável e pode ser maior que a tela, e recalcular sobre
    o que sobrou responderia outra pergunta. O booleano é apurado na fonte,
    sobre o histórico inteiro, e viaja pronto.
    """

    config: ConfigDelta
    candle_atual: CandleDelta | None
    historico: tuple[CandleDelta, ...]
    delta_sessao: int
    volume_total_sessao: int
    volume_nao_atribuido_sessao: int
    _divergente: bool

    def delta_divergente(self) -> bool:
        return self._divergente


@dataclass(frozen=True, slots=True)
class RetratoAnalytics:
    """Os três acumuladores num instante só, no molde de `ui/ponte.Instantaneo`.

    Um retrato, e não três leituras: `derivar_perfil` consome a faixa de preço
    que o footprint definiu e `derivar_delta` consome o número de colunas do
    mesmo eixo. Ler os três em momentos diferentes daria uma tela costurada de
    dois instantes — é a mesma razão pela qual `ui/janela.py::_contexto`
    deriva as parcelas do dia do `Instantaneo` em vez de somar campos soltos.
    """

    footprint: FonteFootprintCongelada | None
    perfil_sessao: FontePerfilCongelada | None
    delta: FonteDeltaCongelada | None
    n_colunas: int


@dataclass(frozen=True, slots=True)
class RetratoASG:
    """Um quadro ASG-like inteiro, congelado na thread publicadora.

    A UI recebe uma unica referencia e nunca consulta Maker, feed, metodo ou
    decisao separadamente. Assim, todos os numeros do quadro pertencem ao
    mesmo evento de mercado, mesmo quando a fonte publica noutra thread.
    """

    timestamp_ns: int
    symbol: str
    feed_quality: FeedQualitySnapshot
    maker: MakerProxySnapshot
    leitura: LeituraASG
    regiao: RegiaoOperacional
    decisao: DecisionSnapshot

    def __post_init__(self) -> None:
        carimbos = {
            self.timestamp_ns,
            self.maker.timestamp_ns,
            self.leitura.timestamp_ns,
            self.regiao.timestamp_ns,
            self.decisao.timestamp_ns,
            self.feed_quality.market_timestamp_ns,
        }
        if carimbos != {self.timestamp_ns}:
            raise ValueError("RetratoASG exige um unico timestamp de mercado")
        simbolos = {
            self.symbol,
            self.maker.symbol,
            self.leitura.symbol,
            self.regiao.symbol,
            self.decisao.symbol,
            self.feed_quality.symbol,
        }
        if simbolos != {self.symbol}:
            raise ValueError("RetratoASG exige um unico symbol")


def _contrato_da_fonte(fonte: FonteDados) -> tuple[FeedSource, BookKind, AggressorQuality]:
    """Metadados declarados das fontes existentes; nunca inferidos do texto."""

    if fonte is FonteDados.SIMULADOR:
        return FeedSource.SIMULATOR, BookKind.MBP, AggressorQuality.NATIVE
    if fonte is FonteDados.REPLAY:
        # O replay CSV pode conter somente tape. O observador eleva para MBP
        # quando um BookSnapshot/BookDelta real for visto.
        return FeedSource.REPLAY, BookKind.NONE, AggressorQuality.UNKNOWN
    if fonte is FonteDados.MT5:
        # Disponibilidade declarada não é disponibilidade observada:
        # market_book_add/get podem falhar. O monitor eleva para MBP somente
        # após receber um BookSnapshot/BookDelta válido.
        return FeedSource.MT5, BookKind.NONE, AggressorQuality.INFERRED
    raise ValueError(f"fonte sem contrato de qualidade: {fonte!r}")


def _congelar_candle(footprint: Footprint) -> Footprint:
    """Cópia do candle VIVO — o único que a thread da fonte ainda muta.

    Os fechados não se copiam: `FootprintPorTimeframe` nunca mais escreve
    neles depois do `append`. Copiar o que já é imutável de fato seria custo
    por quadro sem invariante nenhuma comprada.

    A grandeza aqui é "níveis de preço de UM candle" — limitada pelo
    timeframe, não pela sessão nem pelo número de eventos.
    """
    copia = Footprint(config=footprint.config)
    copia._niveis = {
        preco: NivelFootprint(
            qty_comprador=nivel.qty_comprador,
            qty_vendedor=nivel.qty_vendedor,
            qty_nao_atribuida=nivel.qty_nao_atribuida,
        )
        for preco, nivel in footprint._niveis.items()
    }
    copia._volume_total = footprint._volume_total
    copia._volume_nao_atribuido = footprint._volume_nao_atribuido
    copia._delta = footprint._delta
    copia.preco_abertura = footprint.preco_abertura
    copia.preco_fechamento = footprint.preco_fechamento
    copia.preco_maximo = footprint.preco_maximo
    copia.preco_minimo = footprint.preco_minimo
    return copia


def _congelar_fonte_footprint(
    fonte: FootprintPorTimeframe | None, n_colunas: int
) -> FonteFootprintCongelada | None:
    if fonte is None:
        return None
    atual = fonte._atual
    guardar = max(0, n_colunas - 1) if n_colunas > 1 else 1
    # Fatia sobre a LISTA, não `fonte.footprints_fechados`: a propriedade
    # materializa a sessão inteira numa tupla a cada acesso.
    fechados = tuple(fonte._fechados[-guardar:]) if guardar else ()
    return FonteFootprintCongelada(
        footprint_atual=_congelar_candle(atual) if atual is not None else None,
        _inicio_atual_ns=fonte._inicio_atual_ns,
        footprints_fechados=fechados,
    )


def _congelar_fonte_perfil(
    perfil: VolumeProfile | None,
) -> FontePerfilCongelada | None:
    if perfil is None:
        return None
    ordenados = tuple(
        (
            preco,
            NivelVolume(
                volume_comprador=nivel.volume_comprador,
                volume_vendedor=nivel.volume_vendedor,
                volume_nao_atribuido=nivel.volume_nao_atribuido,
            ),
        )
        for preco, nivel in perfil.niveis_ordenados()
    )
    return FontePerfilCongelada(
        config=perfil.config,
        volume_total=perfil.volume_total,
        volume_nao_atribuido=perfil.volume_nao_atribuido,
        poc=perfil.poc,
        _ordenados=ordenados,
        _value_area=perfil.value_area(),
    )


def _congelar_fonte_delta(
    fonte: CumulativeDelta | None, n_colunas: int
) -> FonteDeltaCongelada | None:
    if fonte is None:
        return None
    guardar = max(0, n_colunas - 1) if n_colunas > 1 else 1
    # `CandleDelta` é congelado por construção (`_CandleDeltaEmFormacao.
    # congelar`), então a fatia da lista basta — não há o que copiar dentro.
    historico = tuple(fonte._historico[-guardar:]) if guardar else ()
    return FonteDeltaCongelada(
        config=fonte.config,
        candle_atual=fonte.candle_atual,
        historico=historico,
        delta_sessao=fonte.delta_sessao,
        volume_total_sessao=fonte.volume_total_sessao,
        volume_nao_atribuido_sessao=fonte.volume_nao_atribuido_sessao,
        _divergente=fonte.delta_divergente(),
    )


class SessaoFluxo:
    """Instancia e liga todas as peças; é o objeto que a aplicação segura.

    Não sabe de onde vêm os eventos: qualquer `AdaptadorDados` que publique no
    mesmo `Barramento` serve (simulador, replay de CSV, replay de gravação,
    MT5). Quem escolhe a fonte é `montagem.montar`.

    `ao_sinal` / `ao_deteccao` são os ganchos de saída. Nenhum é obrigatório —
    sem eles a sessão continua consistente e os contadores continuam válidos,
    o que é o que o benchmark quer medir.
    """

    def __init__(
        self,
        barramento: Barramento,
        config: ConfigOperacao | None = None,
        ao_sinal: Callable[[Sinal], None] | None = None,
        ao_deteccao: Callable[[DeteccaoAnotada], None] | None = None,
    ) -> None:
        self.barramento = barramento
        self.config = config if config is not None else ConfigOperacao()
        self.grid = self.config.price_grid()
        self.contadores = Contadores()
        self._ao_sinal = ao_sinal
        self._ao_deteccao = ao_deteccao

        cfg = self.config
        symbol = cfg.symbol

        # ------------------------------------------------------------------
        # Faixa 0 — núcleo primeiro, analytics depois. A ordem AQUI é a única
        # alavanca disponível (ver "LIMITAÇÃO REAL" em `app/config.py`).
        # ------------------------------------------------------------------
        self.estado = EstadoMercado(barramento, symbol, timeframe_ns=cfg.timeframe_ns)

        self.volume_profile: VolumeProfilePorPeriodo | None = None
        self.footprint: FootprintPorTimeframe | None = None
        self.delta: CumulativeDelta | None = None
        self.agressao: MedidorAgressao | None = None
        self.vwap: VWAP | None = None
        self.brokers: RankingCorretoras | None = None
        if cfg.ligar_analytics:
            self.volume_profile = VolumeProfilePorPeriodo(
                barramento, symbol, cfg.periodo_volume_profile_ns, cfg.volume_profile
            )
            self.footprint = FootprintPorTimeframe(
                barramento, symbol, cfg.timeframe_ns, cfg.footprint
            )
            self.delta = CumulativeDelta(barramento, symbol, cfg.delta)
            self.agressao = MedidorAgressao(barramento, symbol, cfg.agressao)
            self.vwap = VWAP(barramento, symbol, cfg.vwap)
            self.brokers = RankingCorretoras(barramento, symbol, cfg.brokers)

        # ------------------------------------------------------------------
        # Saúde do feed — canal lateral, observador e sem publicação aninhada.
        # Maker e LeituraASG dependem dela, portanto a ativam implicitamente.
        # ------------------------------------------------------------------
        self.feed_monitor: FeedQualityMonitor | None = None
        self.feed_observer: FeedQualityObserver | None = None
        if cfg.ligar_feed_quality or cfg.ligar_maker_proxy or cfg.ligar_leitura_asg:
            fonte_feed, tipo_book, qualidade_agressor = _contrato_da_fonte(cfg.fonte)
            self.feed_monitor = FeedQualityMonitor(
                source=fonte_feed,
                book_kind=tipo_book,
                aggressor_quality=qualidade_agressor,
                symbol=symbol,
                config=cfg.feed_quality,
            )
            self.feed_observer = FeedQualityObserver(
                barramento,
                self.feed_monitor,
                priority=PRIORIDADE_FEED_QUALITY,
            )
            self.feed_observer.iniciar()

        # ------------------------------------------------------------------
        # Perfil de sessão — o que o motor lê (ver docstring do módulo).
        # ------------------------------------------------------------------
        self.perfil_sessao = VolumeProfile(config=cfg.volume_profile)
        barramento.assinar(
            Trade, self._ao_trade_perfil_sessao, prioridade=PRIORIDADE_PERFIL_SESSAO
        )

        # ------------------------------------------------------------------
        # Microestrutura — a ponte MBP->MBO, o livro e os detectores de livro.
        # ------------------------------------------------------------------
        self.livro: LivroMBO | None = None
        self.inferidor: InferidorMBP | None = None
        self.det_escora: DetectorEscora | None = None
        self.det_iceberg: DetectorIcebergPorRecarga | None = None
        self.det_liquidez_fantasma: DetectorLiquidezFantasma | None = None
        if cfg.ligar_microestrutura:
            self.livro = LivroMBO(symbol, cfg.livro)
            self.inferidor = InferidorMBP(symbol, self.livro, cfg.inferencia)
            self.det_escora = DetectorEscora(cfg.escora)
            self.det_iceberg = DetectorIcebergPorRecarga(cfg.iceberg)
            self.det_liquidez_fantasma = DetectorLiquidezFantasma(
                self.grid.tick_size, cfg.liquidez_fantasma
            )
            self._ligar_livro(self.livro)

            barramento.assinar(Trade, self._ao_trade_micro, prioridade=PRIORIDADE_MICRO)
            barramento.assinar(
                BookSnapshot, self._ao_snapshot_micro, prioridade=PRIORIDADE_MICRO
            )
            barramento.assinar(
                BookDelta, self._ao_delta_micro, prioridade=PRIORIDADE_MICRO
            )

        # ------------------------------------------------------------------
        # Detectores de tape (leem `Trade` direto) + perfil de player.
        # ------------------------------------------------------------------
        self.det_absorcao: DetectorAbsorcao | None = None
        self.det_exaustao: DetectorExaustao | None = None
        self.det_clip: DetectorClipInstitucional | None = None
        if cfg.ligar_detectores_tape:
            self.det_absorcao = DetectorAbsorcao(symbol, cfg.absorcao)
            self.det_exaustao = DetectorExaustao(symbol, cfg.exaustao)
            self.det_clip = DetectorClipInstitucional(symbol, cfg.clip_institucional)
            barramento.assinar(
                Trade, self._ao_trade_detectores_tape, prioridade=PRIORIDADE_MICRO
            )

        self.perfil_player = PerfilPlayer(symbol, cfg.janela_periodo_player_ns)
        barramento.assinar(
            Trade, self._ao_trade_perfil_player, prioridade=PRIORIDADE_MICRO
        )

        # ------------------------------------------------------------------
        # MakerProxy — consumidor causal da microestrutura e do tape.
        # ------------------------------------------------------------------
        self.maker_proxy: MakerProxy | None = None
        if cfg.ligar_maker_proxy or cfg.ligar_leitura_asg:
            self.maker_proxy = MakerProxy(symbol, cfg.maker_proxy)
            barramento.assinar(
                Trade, self._ao_trade_maker, prioridade=PRIORIDADE_MAKER
            )

        # ------------------------------------------------------------------
        # Motor de confluência.
        # ------------------------------------------------------------------
        self.motor: MotorSinais | None = None
        if cfg.ligar_motor:
            self.motor = MotorSinais(symbol, self.perfil_sessao, cfg.motor)
            barramento.assinar(Trade, self._ao_trade_motor, prioridade=PRIORIDADE_MOTOR)

        self._ultimo_estagio: tuple[EstagioSinal, object] | None = None
        self._sinal_corrente: Sinal | None = None

        # ------------------------------------------------------------------
        # Método — os componentes de `fluxopro/metodologia/`, o último
        # PRODUTOR da cadeia (ver "a quarta seta" em `app/config.py`).
        #
        # `LeitorMetodo` não assina o barramento por conta própria — quem
        # assina é esta classe, com prioridade explícita. É a mesma política
        # de `MotorSinais` e do perfil de sessão, e é o que permite à virada
        # de sessão zerá-lo pelo método dele, sem desassinar e reassinar
        # nada (grupo (a) de `iniciar_nova_sessao`).
        # ------------------------------------------------------------------
        self.metodo: LeitorMetodo | None = None
        if cfg.ligar_metodologia:
            self.metodo = LeitorMetodo(symbol, cfg.metodologia)
            barramento.assinar(
                Trade, self._ao_trade_metodo, prioridade=PRIORIDADE_METODO
            )

        # ------------------------------------------------------------------
        # Matriz/decisão e sidecar shadow — último produtor antes da saída.
        # ------------------------------------------------------------------
        self.motor_decisao_asg: MotorDecisaoASG | None = None
        self.shadow: SidecarShadow | None = None
        self.shadow_writer: AsyncShadowWriter | None = None
        self._lock_retrato_asg = threading.Lock()
        self._retrato_asg: RetratoASG | None = None
        self._ultimo_retrato_asg_timestamp_ns: int | None = None
        if type(cfg.intervalo_retrato_asg_ns) is not int or cfg.intervalo_retrato_asg_ns < 1:
            raise ValueError("intervalo_retrato_asg_ns deve ser inteiro positivo")
        if cfg.ligar_shadow_learning and not cfg.ligar_leitura_asg:
            raise ValueError(
                "ligar_shadow_learning exige ligar_leitura_asg=True"
            )
        if cfg.ligar_shadow_learning and cfg.shadow_dir is None:
            raise ValueError("ligar_shadow_learning exige shadow_dir")
        if cfg.ligar_shadow_learning:
            assert cfg.shadow_dir is not None
            self.shadow = SidecarShadow(cfg.shadow_dir, cfg.shadow)
            self.shadow_writer = AsyncShadowWriter(
                self.shadow, capacity=cfg.shadow_queue_capacity
            )
        if cfg.ligar_leitura_asg:
            self.motor_decisao_asg = MotorDecisaoASG(cfg.decisao_asg)
            barramento.assinar(
                Trade, self._ao_trade_asg, prioridade=PRIORIDADE_ASG
            )

        # ------------------------------------------------------------------
        # Retrato de analytics — o carimbo de thread ANTES de tudo, a montagem
        # DEPOIS de tudo. Ver `retrato_de_analytics`.
        # ------------------------------------------------------------------
        self._lock_retrato = threading.Lock()
        self._retrato_analytics: RetratoAnalytics | None = None
        self._retrato_pedido = False
        self._retrato_n_colunas = 0
        self._thread_publicadora: int | None = None
        barramento.assinar(
            Trade, self._ao_trade_marca_thread, prioridade=PRIORIDADE_MARCA_THREAD
        )

        # ------------------------------------------------------------------
        # Contagem — por último, para "processado" querer dizer processado.
        # ------------------------------------------------------------------
        barramento.assinar(Trade, self._contar_trade, prioridade=PRIORIDADE_SAIDA)
        barramento.assinar(
            BookSnapshot, self._contar_snapshot, prioridade=PRIORIDADE_SAIDA
        )
        barramento.assinar(BookDelta, self._contar_delta, prioridade=PRIORIDADE_SAIDA)
        barramento.assinar(
            Trade, self._ao_trade_montar_retrato, prioridade=PRIORIDADE_SAIDA
        )

        self._perf_inicio: float | None = None
        self._perf_fim: float | None = None

    # ------------------------------------------------------------------
    # handlers
    # ------------------------------------------------------------------
    def _ao_trade_perfil_sessao(self, trade: Trade) -> None:
        if trade.symbol != self.config.symbol:
            return
        self.perfil_sessao.registrar_trade(trade)
        self.contadores.n_trades_perfil_sessao += 1

    def _ao_trade_micro(self, trade: Trade) -> None:
        assert self.inferidor is not None
        if trade.symbol != self.config.symbol:
            return
        self.contadores.n_trades_micro += 1
        self.inferidor.ao_trade(trade)

    def _ao_snapshot_micro(self, snapshot: BookSnapshot) -> None:
        assert self.inferidor is not None
        if snapshot.symbol != self.config.symbol:
            return
        self.contadores.n_snapshots_micro += 1
        self.inferidor.ao_snapshot(snapshot)

    def _ao_delta_micro(self, delta: BookDelta) -> None:
        assert self.inferidor is not None
        if delta.symbol != self.config.symbol:
            return
        self.contadores.n_deltas_micro += 1
        self.inferidor.ao_delta(delta)

    def _ao_trade_detectores_tape(self, trade: Trade) -> None:
        if trade.symbol != self.config.symbol:
            return
        for detector in (self.det_absorcao, self.det_exaustao, self.det_clip):
            if detector is None:
                continue
            deteccao = detector.ao_trade(trade)
            if deteccao is not None:
                # Gatilho é o tape impresso: fato observado, confiança intacta.
                self._emitir_deteccao(deteccao, FonteMicro.MBO, CONFIANCA_OBSERVADO)

    def _ao_trade_perfil_player(self, trade: Trade) -> None:
        self.perfil_player.ao_trade(trade)

    def _ao_trade_maker(self, trade: Trade) -> None:
        """Atualiza feed e tape no Maker usando somente o relógio do mercado."""

        assert self.maker_proxy is not None
        if trade.symbol != self.config.symbol:
            return
        if self.feed_monitor is not None:
            self.maker_proxy.ingerir_feed_quality(self.feed_monitor.snapshot())
        self.maker_proxy.ingerir_trade(trade)

    def _ao_trade_motor(self, trade: Trade) -> None:
        assert self.motor is not None
        if trade.symbol != self.config.symbol:
            return
        self.contadores.n_trades_motor += 1
        sinal = self.motor.ao_trade(trade)
        # Estado corrente e emissão são contratos distintos. A matriz precisa
        # do sinal deste trade mesmo quando o callback externo é suprimido por
        # `emitir_apenas_mudanca_de_estagio`.
        self._sinal_corrente = sinal
        chave = (sinal.estagio, sinal.direcao)
        if self.config.emitir_apenas_mudanca_de_estagio and chave == self._ultimo_estagio:
            return
        self._ultimo_estagio = chave
        cont = self.contadores
        cont.n_sinais_emitidos += 1
        cont.sinais_por_estagio[sinal.estagio] = (
            cont.sinais_por_estagio.get(sinal.estagio, 0) + 1
        )
        if self._ao_sinal is not None:
            self._ao_sinal(sinal)

    def _ao_trade_metodo(self, trade: Trade) -> None:
        """Alimenta os cinco componentes do método com o trade corrente.

        Um assinante só para os cinco, de propósito: eles têm de ler o MESMO
        trade e o retrato publicado carimba os cinco com o mesmo
        `timestamp_ns` (`LeituraMetodo` recusa o contrário). Cinco assinaturas
        independentes tornariam possível severar uma e publicar um retrato
        onde o placar foi apurado com o voto do velocímetro de antes.
        """
        assert self.metodo is not None
        if trade.symbol != self.config.symbol:
            return
        self.contadores.n_trades_metodo += 1
        self.metodo.ao_trade(trade)

    def leitura_do_metodo(self) -> LeituraMetodo | None:
        """O retrato consistente do método, ou `None`.

        É o que a interface chama — uma vez por quadro, na thread dela. Não
        drena, então qualquer painel pode chamar. `None` significa "método
        desligado (`ligar_metodologia=False`) ou nenhum trade ainda", e os
        dois casos se distinguem por `SessaoFluxo.metodo is None`.
        """
        if self.metodo is None:
            return None
        return self.metodo.ler()

    def feed_quality(self) -> FeedQualitySnapshot | None:
        """Última saúde imutável, lida diretamente e sem publicar no bus."""

        return self.feed_monitor.snapshot() if self.feed_monitor is not None else None

    def retrato_asg(self) -> RetratoASG | None:
        """Último quadro ASG-like consistente; não drena e não toca em vivos."""

        with self._lock_retrato_asg:
            return self._retrato_asg

    def _regiao_operacional(self, trade: Trade, maker: MakerProxySnapshot) -> RegiaoOperacional:
        area = self.motor.regiao_atual(trade.timestamp_ns) if self.motor is not None else None
        if area is None:
            return RegiaoOperacional(
                symbol=trade.symbol,
                timestamp_ns=trade.timestamp_ns,
                inicio_ticks=trade.price,
                fim_ticks=trade.price,
                nome="SEM REGIAO",
                confianca=0.0,
                procedencia=ProcedenciaASG.DESCONHECIDA,
                qualidade="SEM_REGIAO",
                valida=False,
            )
        val, vah = area
        invalidacao = None
        if maker.direcao is not None:
            invalidacao = val if maker.direcao.value == "BUY" else vah
        return RegiaoOperacional(
            symbol=trade.symbol,
            timestamp_ns=trade.timestamp_ns,
            inicio_ticks=val,
            fim_ticks=vah,
            nome="VALUE AREA DA SESSAO",
            confianca=1.0,
            procedencia=ProcedenciaASG.OBSERVADA,
            qualidade="DERIVADA_DO_VOLUME_OBSERVADO",
            valida=True,
            invalidacao_ticks=invalidacao,
        )

    def _ao_trade_asg(self, trade: Trade) -> None:
        """Congela matriz e decisão do mesmo trade, na thread publicadora."""

        assert self.maker_proxy is not None
        assert self.motor_decisao_asg is not None
        if trade.symbol != self.config.symbol:
            return
        ultimo = self._ultimo_retrato_asg_timestamp_ns
        if (
            ultimo is not None
            and trade.timestamp_ns - ultimo < self.config.intervalo_retrato_asg_ns
        ):
            return
        feed = self.feed_monitor.snapshot() if self.feed_monitor is not None else None
        maker = self.maker_proxy.snapshot()
        # Evento regressivo/duplicado não pode costurar um quadro novo com o
        # estado causal anterior. O monitor já registra a anomalia.
        if maker.timestamp_ns != trade.timestamp_ns:
            return
        if feed is None or feed.market_timestamp_ns != trade.timestamp_ns:
            return

        metodo = self.metodo.ler() if self.metodo is not None else None
        metodo_map = (
            asdict(metodo)
            if metodo is not None
            else {"timestamp_ns": trade.timestamp_ns, "symbol": trade.symbol}
        )
        metodo_map.setdefault("symbol", trade.symbol)
        sinal = self._sinal_corrente
        sinal_map = (
            asdict(sinal)
            if sinal is not None and sinal.timestamp_ns == trade.timestamp_ns
            else {"timestamp_ns": trade.timestamp_ns, "symbol": trade.symbol}
        )
        feed_map = asdict(feed)

        divergencias: list[str] = []
        if sinal is not None and sinal.direcao is not None and maker.direcao is not None:
            if sinal.direcao is not maker.direcao:
                divergencias.append("MAKER_DIVERGE_DO_MOTOR")
        if metodo is not None and metodo.placar.lado is not None and maker.direcao is not None:
            if metodo.placar.lado is not maker.direcao:
                divergencias.append("MAKER_DIVERGE_DO_PLACAR")

        leitura = LeituraASG.do_maker(
            maker,
            metodo=metodo_map,
            sinal=sinal_map,
            feed_quality=feed_map,
            divergencias=tuple(divergencias),
            provenance=(
                "maker:proxy-independente",
                "metodo:operador-b3",
                f"feed:{feed.source.value}/{feed.book_kind.value}",
            ),
        )
        regiao = self._regiao_operacional(trade, maker)
        decisao = self.motor_decisao_asg.avaliar(leitura, regiao, trade.price)
        retrato = RetratoASG(
            timestamp_ns=trade.timestamp_ns,
            symbol=trade.symbol,
            feed_quality=feed,
            maker=maker,
            leitura=leitura,
            regiao=regiao,
            decisao=decisao,
        )
        with self._lock_retrato_asg:
            self._retrato_asg = retrato
        self._ultimo_retrato_asg_timestamp_ns = trade.timestamp_ns
        self._observar_shadow(trade, retrato)

    def _observar_shadow(self, trade: Trade, retrato: RetratoASG) -> None:
        if self.shadow is None:
            return
        decisao = retrato.decisao
        proposta = decisao.proposta_risco
        estado = (
            "CONFIRMACAO" if decisao.confirmacao
            else "PRE_SINAL" if decisao.pre_sinal
            else retrato.maker.estado.value
        )
        amostra = AmostraFeatures(
            timestamp_ns=trade.timestamp_ns,
            symbol=trade.symbol,
            price_ticks=trade.price,
            estado=estado,
            direcao=decisao.direcao,
            features={
                "maker": retrato.maker.como_dict(),
                "matriz": retrato.leitura.como_dict(),
                "decisao": {
                    "nivel": decisao.nivel.value,
                    "pre_sinal": decisao.pre_sinal,
                    "confirmacao": decisao.confirmacao,
                    "bloqueios": decisao.bloqueios,
                    "confianca": decisao.confianca,
                },
            },
            qualidade_origem={
                "state": retrato.feed_quality.state.value,
                "source": retrato.feed_quality.source.value,
                "book_kind": retrato.feed_quality.book_kind.value,
                "latency_ns": retrato.feed_quality.latency_ns,
                "anomalies": retrato.feed_quality.anomalies,
            },
            alvo_preco_ticks=proposta.a1_ticks if proposta is not None else None,
            invalidacao_preco_ticks=(
                proposta.stop_ticks if proposta is not None else None
            ),
        )
        assert self.shadow_writer is not None
        self.shadow_writer.submit(amostra)

    def shadow_status(self) -> ShadowRuntimeSnapshot | None:
        """Telemetria explícita; erro do sidecar nunca vira erro do mercado."""
        return None if self.shadow_writer is None else self.shadow_writer.snapshot()

    # ------------------------------------------------------------------
    # Retrato de analytics
    # ------------------------------------------------------------------
    def _ao_trade_marca_thread(self, trade: Trade) -> None:
        """Só carimba quem está publicando. Roda ANTES de qualquer acumulador.

        Uma atribuição de inteiro por trade. Não há `if` de guarda de
        propósito: o carimbo tem de valer para a thread publicadora ATUAL, e
        um `if is None` congelaria a primeira — o que faria uma sessão
        alimentada primeiro pela thread do Qt (teste, script) e depois por uma
        thread de fonte de verdade escolher o caminho errado para sempre.
        """
        self._thread_publicadora = threading.get_ident()

    def _ao_trade_montar_retrato(self, trade: Trade) -> None:
        """Monta o retrato quando — e SÓ quando — a UI pediu um.

        Custo por trade fora do quadro: uma leitura de atributo booleano. A UI
        pede no máximo uma vez por quadro (62/s contra 5.000 ev/s), então o
        congelamento acontece ~1 vez a cada 80 negócios, e sempre na thread
        que escreve. Montar por trade seria pagar O(níveis) 5.000 vezes por
        segundo para desenhar 62.
        """
        if not self._retrato_pedido:
            return
        retrato = self._montar_retrato(self._retrato_n_colunas)
        with self._lock_retrato:
            self._retrato_analytics = retrato
            self._retrato_pedido = False

    def retrato_de_analytics(self, n_colunas: int = 0) -> RetratoAnalytics | None:
        """Footprint, perfil e delta num instante só — a UI chama isto.

        `None` quer dizer "ainda não há retrato deste lado do lock", e é
        resposta legítima do primeiro quadro depois que a fonte passou a
        publicar de outra thread: o pedido fica registrado e o próximo negócio
        o atende. Quem chama mantém a leitura anterior; não há quadro em que
        um painel mostre metade de um instante e metade de outro.

        ## Os dois caminhos, e por que o critério é a THREAD e não um lock

        `core/barramento.py` decidiu que **exceção de assinante PROPAGA** — não
        há `try/except` em `publicar`. Então o desenho óbvio (um assinante que
        pega o lock antes dos analytics e outro que solta depois) travaria a
        aplicação inteira no primeiro assinante que levantasse: o `release`
        nunca rodaria. Segurar um lock ATRAVÉS de uma cadeia de callbacks de
        terceiros é fiar-se em que nenhum deles falhe.

        O critério usado é outro e não tem esse buraco: `_thread_publicadora`
        é carimbado antes do primeiro acumulador tocar no próprio dicionário.

        * **Ninguém publicou ainda, ou quem publica sou EU** — não existe
          escrita concorrente possível, e o retrato é montado inline, sem
          lock. É o caso do `scripts/retrato_footprint.py` e da suíte, que
          alimentam e leem na mesma thread; para eles nada muda e nada fica
          um quadro atrasado.
        * **Quem publica é outra thread** — montar aqui seria a corrida. O
          pedido é registrado e o retrato devolvido é o último que a thread da
          fonte montou, sob a guarda do lock. O lock protege apenas a troca da
          referência, nunca uma iteração.
        """
        if (
            self._thread_publicadora is None
            or self._thread_publicadora == threading.get_ident()
        ):
            return self._montar_retrato(n_colunas)
        with self._lock_retrato:
            self._retrato_n_colunas = n_colunas
            self._retrato_pedido = True
            return self._retrato_analytics

    def _montar_retrato(self, n_colunas: int) -> RetratoAnalytics:
        """Congela os três acumuladores. **Só a thread que publica chama.**"""
        return RetratoAnalytics(
            footprint=_congelar_fonte_footprint(self.footprint, n_colunas),
            perfil_sessao=_congelar_fonte_perfil(self.perfil_sessao),
            delta=_congelar_fonte_delta(self.delta, n_colunas),
            n_colunas=n_colunas,
        )

    def _ligar_livro(self, livro: LivroMBO) -> None:
        """Assina o livro — na ORDEM que faz a procedência chegar a tempo.

        Os três detectores de livro entram primeiro, via `acompanhar`, e só
        depois entra `_ao_ordem_evento`. A ordem não é estética:
        `LivroMBO._emitir` percorre `_ouvintes` na ordem de registro, então
        quem assina antes vê o evento antes. Assinando primeiro, o evento
        gatilho já está na cadeia de procedência do detector quando
        `_ao_ordem_evento` chama `verificar` — que é a diferença entre a
        detecção sair com o mínimo da cadeia inteira (N reposições inferidas)
        e sair com `procedencia: DESCONHECIDA`.

        Invertida a ordem, nada quebra e nenhum teste de fiação reclama: as
        detecções apenas voltam a sair mudas sobre a própria origem. É
        exatamente a classe de defeito que este projeto vem perseguindo, então
        vale a linha de comentário e o teste que prende a ordem.
        """
        for detector in (
            self.det_escora,
            self.det_iceberg,
            self.det_liquidez_fantasma,
        ):
            if detector is not None:
                detector.acompanhar(livro)
        # Ouvinte direto em vez do barramento: `LivroMBO.assinar_evento`
        # existe para isso e evita republicar no meio de um `publicar`.
        livro.assinar_evento(self._ao_ordem_evento)
        livro.assinar_cruzamento(self._ao_cruzamento)

    def _ao_ordem_evento(self, evento: OrdemEvento) -> None:
        """Fecha o elo `InferidorMBP -> LivroMBO -> detectores de livro`.

        Cada tipo de evento dispara o detector que aquele tipo pode revelar —
        nenhum detector é chamado por tick "no escuro":

        * `NEW`   -> escora (o nível acabou de ser reposto depois de varrido);
        * `TRADE` -> iceberg por recarga (a ordem executou mais um pedaço);
        * `CANCEL`/`EXPIRE` -> liquidez fantasma (a ordem saiu; só agora dá
          para saber se saiu sem executar nada).
        """
        cont = self.contadores
        cont.n_ordem_eventos += 1
        cont.ordem_eventos_por_tipo[evento.tipo] = (
            cont.ordem_eventos_por_tipo.get(evento.tipo, 0) + 1
        )
        if evento.fonte is FonteMicro.MBP_INFERIDO:
            cont.n_ordem_eventos_inferidos += 1

        livro = self.livro
        assert livro is not None

        if evento.tipo is TipoEventoOrdem.NEW and self.det_escora is not None:
            deteccao = self.det_escora.verificar(
                livro, evento.side, evento.price, evento.timestamp_ns
            )
            if deteccao is not None:
                self._emitir_deteccao(deteccao, evento.fonte, evento.confianca)

        elif evento.tipo is TipoEventoOrdem.TRADE and self.det_iceberg is not None:
            ordem = livro.ordem(evento.order_id)
            if ordem is not None:
                deteccao = self.det_iceberg.verificar(
                    ordem, livro.symbol, evento.timestamp_ns
                )
                if deteccao is not None:
                    self._emitir_deteccao(deteccao, evento.fonte, evento.confianca)

        elif (
            evento.tipo in (TipoEventoOrdem.CANCEL, TipoEventoOrdem.EXPIRE)
            and self.det_liquidez_fantasma is not None
        ):
            ordem = livro.ordem(evento.order_id)
            if ordem is not None:
                oposto = (
                    livro.melhor_ask() if ordem.side.name == "BUY" else livro.melhor_bid()
                )
                deteccao = self.det_liquidez_fantasma.verificar(
                    ordem, livro.symbol, oposto
                )
                if deteccao is not None:
                    self._emitir_deteccao(deteccao, evento.fonte, evento.confianca)

    def _ao_cruzamento(self, cruzamento: CruzamentoLivro) -> None:
        self.contadores.n_cruzamentos_livro = cruzamento.n_cruzamentos

    def _emitir_deteccao(
        self, deteccao: Deteccao, fonte: FonteMicro, confianca_gatilho: float
    ) -> None:
        """Publica a detecção com a confiança da fronteira. `min`, não produto.

        Era produto quando `detectores.py` emitia `confianca=1.0` fixo: o
        detector não sabia de onde vinha o dado, e a única confiança real era a
        do `OrdemEvento` gatilho — multiplicar por 1,0 era só um jeito de
        deixá-la passar.

        Agora o detector propaga a cadeia inteira (mínimo dos `OrdemEvento` que
        sustentam a detecção) e o gatilho JÁ ESTÁ nessa cadeia, porque
        `_ligar_livro` assina os detectores antes deste método. Manter o
        produto cobraria a mesma incerteza duas vezes: uma cadeia de 0,55
        disparada por um evento de 0,55 sairia 0,3025 — pessimismo fabricado,
        e a distinção entre "inferido" e "muito inferido" viraria ruído.

        `min` é a mesma política do detector (t-norm de Gödel: idempotente e
        monótona), e continua sendo uma COTA — não um relaxamento. Ele importa
        no caso em que o detector NÃO tem cadeia (`procedencia: DESCONHECIDA`,
        confiança no default `CONFIANCA_OBSERVADO`): aí é o gatilho que segura
        o teto, e a fronteira segue impedindo que hipótese saia como fato.
        """
        anotada = DeteccaoAnotada(
            deteccao=deteccao,
            fonte=fonte,
            confianca_efetiva=min(deteccao.confianca, confianca_gatilho),
        )
        cont = self.contadores
        cont.n_deteccoes += 1
        if anotada.inferida:
            cont.n_deteccoes_inferidas += 1
        cont.deteccoes_por_tipo[deteccao.tipo] = (
            cont.deteccoes_por_tipo.get(deteccao.tipo, 0) + 1
        )
        if self._ao_deteccao is not None:
            self._ao_deteccao(anotada)

    # ------------------------------------------------------------------
    # contagem (última na fila)
    # ------------------------------------------------------------------
    def _marcar_tempo(self, timestamp_ns: int) -> None:
        cont = self.contadores
        if cont.ts_primeiro_ns is None:
            cont.ts_primeiro_ns = timestamp_ns
            self._perf_inicio = time.perf_counter()
        cont.ts_ultimo_ns = timestamp_ns

    def _contar_trade(self, trade: Trade) -> None:
        if trade.symbol != self.config.symbol:
            return
        self.contadores.n_trades_bus += 1
        self._marcar_tempo(trade.timestamp_ns)

    def _contar_snapshot(self, snapshot: BookSnapshot) -> None:
        if snapshot.symbol != self.config.symbol:
            return
        self.contadores.n_snapshots_bus += 1
        self._marcar_tempo(snapshot.timestamp_ns)

    def _contar_delta(self, delta: BookDelta) -> None:
        if delta.symbol != self.config.symbol:
            return
        self.contadores.n_deltas_bus += 1
        self._marcar_tempo(delta.timestamp_ns)

    # ------------------------------------------------------------------
    # ciclo de vida
    # ------------------------------------------------------------------
    #: Componentes que assinam o `Barramento` sozinhos, não têm método de
    #: reset e, por isso, NÃO podem ser zerados por esta camada.
    #:
    #: **Hoje: vazia.** Ela existiu enquanto `Barramento` não tinha
    #: `desassinar` — sem ele, trocar a instância de um componente que se
    #: inscreve no próprio construtor deixava a antiga assinada e dobrava a
    #: contagem. `criticas/nucleo_r5.md` §C.2 mediu a consequência: dos doze
    #: campos observados na virada de sessão, **um** carregava o dia
    #: anterior — os 199 candles fechados do `FootprintPorTimeframe`, o
    #: único nome que restava aqui. Com `Barramento.desassinar_objeto` o
    #: componente entra no grupo (b) (recriado com a mesma config) e a lista
    #: fica vazia.
    #:
    #: A constante permanece — vazia — de propósito: é o lugar declarado
    #: para o próximo componente que assinar a si mesmo sem API de reset, e
    #: `tests/test_app_pipeline.py::test_componentes_sem_reset_estao_declarados`
    #: exige que ela continue vazia, de modo que reintroduzir um o torne um
    #: teste vermelho em vez de uma sobra silenciosa de estado.
    SEM_RESET_POSSIVEL: tuple[str, ...] = ()

    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Virada de pregão — **explícita**, chamada por quem sabe o calendário.

        A política está fixada em `core/estado_mercado.py`: virada explícita,
        porque só quem alimenta os eventos conhece o calendário da B3 (regular
        + after, feriado, rolagem). Esta camada é justamente "o adaptador/app
        que sabe", então é aqui que a virada acontece de verdade.

        ## Três grupos, três tratamentos

        **(a) Tem `iniciar_nova_sessao`/`nova_sessao`** — `EstadoMercado`,
        `CumulativeDelta`, `VWAP`, `MedidorAgressao`, `VolumeProfilePorPeriodo`,
        `RankingCorretoras` e `LeitorMetodo`. Chamado. Convenção do núcleo:
        acumulador corrente zera, histórico fechado sobrevive.

        `LeitorMetodo` entra neste grupo — e não no (b), onde estão as peças
        recriadas — porque ele tem API de reset **e** não assina o barramento
        sozinho: recriá-lo exigiria desassinar e reassinar para nada, e o
        preço seria mudar a posição dele dentro da faixa 45. Cada um dos seis
        componentes que ele carrega sabe o que "do dia" significa para si
        (máxima/mínima do dia, referência de magnitude do dia, linha desde a
        abertura, aquecimento do pregão, região abandonada no dia), e o
        retrato publicado volta a `None` — um painel que continuasse mostrando
        o placar de ontem enquanto o pregão de hoje não teve trade nenhum
        seria exatamente o defeito que a virada existe para fechar.

        **(b) Não tem API, mas quem chama é esta classe** — `MotorSinais`, o
        perfil de sessão, `PerfilPlayer`, os seis detectores, `LivroMBO` e
        `InferidorMBP`. Nenhum deles assina o barramento por conta própria
        (o livro publica por `assinar_evento`, que esta classe religa), então a
        montagem os **recria** com a mesma config. Reset completo, sem tocar em
        nenhum módulo compartilhado.

        Por que isso não é zelo: `criticas/nucleo_r3.md` §C.4 mediu o percentil
        de magnitude do `MotorSinais` sobrevivendo intacto a um salto de 24h no
        timestamp (`964,025` antes e depois) — o gate do caso WINFUT, que a
        onda 5 construiu, ficaria calibrado por um dia que já acabou: fechado o
        dia inteiro depois de um pregão de pânico, escancarado depois de um
        feriado morno. Na mesma seção: `DetectorEscora._ja_sinalizado` e
        `DetectorIcebergPorRecarga._ja_sinalizado` nunca são limpos, então um
        nível sinalizado no dia 1 **fica mudo para sempre**.

        O `LivroMBO` entra neste grupo — e sim, isso diverge do
        `EstadoMercado`, que preserva o book de propósito. A divergência é
        deliberada: o book do `EstadoMercado` espelha o feed e é
        sobrescrito pelo primeiro snapshot do dia novo, enquanto o `LivroMBO`
        é uma RECONSTRUÇÃO que acumula histórico por nível
        (`n_reposicoes`, `consumido_acumulado`, `qty_exibida_max`) cuja
        definição é "desde que este nível nasceu". Carregar isso para o dia
        seguinte faria a primeira ordem do pregão parecer a terceira reposição
        de uma escora de ontem. O `InferidorMBP` vai junto porque a linha de
        base dele (`_qty_por_nivel`) é o book de ontem.

        **(c) Não tem API de reset e assina sozinho** — grupo VAZIO hoje
        (`SEM_RESET_POSSIVEL == ()`). `FootprintPorTimeframe` morava aqui e
        era, na medição de `criticas/nucleo_r5.md` §C.2, o **único** dos doze
        campos observados que sobrevivia à virada: 199 candles fechados do
        dia 1 apareciam numa consulta de histórico do dia 2, sem marca de
        sessão. A causa era a ausência de `desassinar` no `Barramento`; ela
        foi fechada, e o componente passou para o grupo (b) — desassinado por
        `desassinar_objeto` e recriado com a mesma config.

        Uma consequência a dizer em vez de esconder: o footprint recriado
        volta ao barramento no **fim** da faixa de prioridade 0, atrás dos
        outros analytics, em vez do slot que ocupava na montagem inicial.
        Isso é inócuo porque a faixa 0 é composta de acumuladores mutuamente
        independentes — nenhum analytics lê outro nem lê `EstadoMercado` (ver
        `app/config.py`, "a terceira seta"). O que **não** pode mudar é a
        posição relativa às faixas seguintes, e não muda: 0 continua antes de
        `PRIORIDADE_PERFIL_SESSAO`, `PRIORIDADE_MICRO`, `PRIORIDADE_MOTOR` e
        `PRIORIDADE_SAIDA`. `tests/test_app_pipeline.py` prende as duas
        metades dessa frase.

        `RankingCorretoras` tinha o mesmo problema (`janela_ns=None` de
        fábrica acumulava para sempre, e era o que de fato misturava
        sessões) mas ganhou `iniciar_nova_sessao()` — chamado abaixo, no
        grupo (a).
        """
        cfg = self.config
        symbol = cfg.symbol

        # (a) quem tem API própria
        self.estado.iniciar_nova_sessao(timestamp_ns)
        if self.delta is not None:
            self.delta.iniciar_nova_sessao(timestamp_ns)
        if self.vwap is not None:
            self.vwap.iniciar_nova_sessao(timestamp_ns)
        if self.agressao is not None:
            self.agressao.iniciar_nova_sessao(timestamp_ns)
        if self.volume_profile is not None:
            self.volume_profile.nova_sessao()
        if self.brokers is not None:
            self.brokers.iniciar_nova_sessao()
        if self.metodo is not None:
            # Grupo (a): tem API propria E nao assina o barramento sozinho,
            # entao zera no lugar em vez de ser recriado. Recriar exigiria
            # desassinar/reassinar e mudaria a posicao na faixa 45 sem
            # necessidade nenhuma.
            self.metodo.iniciar_nova_sessao(timestamp_ns)

        # (b) quem esta classe chama — recriado com a mesma config
        if self.footprint is not None:
            # Desassinar ANTES de construir o substituto: o construtor de
            # `FootprintPorTimeframe` se inscreve sozinho, e inverter a ordem
            # deixaria as duas instâncias assinadas por um instante — o que a
            # antiga lista `SEM_RESET_POSSIVEL` chamava de "dobrar a
            # contagem". `assert` porque 0 removidas significaria que o
            # componente nunca esteve ligado neste barramento, e seguir daí
            # produziria um footprint mudo em silêncio.
            removidas = self.barramento.desassinar_objeto(self.footprint)
            assert removidas > 0, "footprint nao estava assinado no barramento"
            self.footprint = FootprintPorTimeframe(
                self.barramento, symbol, cfg.timeframe_ns, cfg.footprint
            )

        self.perfil_sessao = VolumeProfile(config=cfg.volume_profile)
        if self.motor is not None:
            self.motor = MotorSinais(symbol, self.perfil_sessao, cfg.motor)
        self.perfil_player = PerfilPlayer(symbol, cfg.janela_periodo_player_ns)

        if self.det_absorcao is not None:
            self.det_absorcao = DetectorAbsorcao(symbol, cfg.absorcao)
            self.det_exaustao = DetectorExaustao(symbol, cfg.exaustao)
            self.det_clip = DetectorClipInstitucional(symbol, cfg.clip_institucional)

        if self.livro is not None:
            self.livro = LivroMBO(symbol, cfg.livro)
            self.inferidor = InferidorMBP(symbol, self.livro, cfg.inferencia)
            self.det_escora = DetectorEscora(cfg.escora)
            self.det_iceberg = DetectorIcebergPorRecarga(cfg.iceberg)
            self.det_liquidez_fantasma = DetectorLiquidezFantasma(
                self.grid.tick_size, cfg.liquidez_fantasma
            )
            # Religar: o livro novo não conhece os ouvintes do antigo. Mesma
            # função da montagem inicial, para que a ordem de assinatura (e
            # portanto a procedência) não possa divergir entre os dois
            # caminhos.
            self._ligar_livro(self.livro)

        self._ultimo_estagio = None
        self._sinal_corrente = None
        if self.maker_proxy is not None:
            self.maker_proxy.iniciar_nova_sessao()
        if self.shadow is not None:
            assert self.shadow_writer is not None
            self.shadow_writer.reset_session(symbol)
        with self._lock_retrato_asg:
            self._retrato_asg = None
        self._ultimo_retrato_asg_timestamp_ns = None

        # O retrato guardado é do pregão que acabou. Mantê-lo faria a UI
        # desenhar o footprint de ontem no primeiro quadro de hoje — a mesma
        # falha que zerar o retrato do método fecha no grupo (a).
        with self._lock_retrato:
            self._retrato_analytics = None
            self._retrato_pedido = False

    def finalizar(self, timestamp_ns: int | None = None) -> None:
        """Fecha a passada: drena o inferidor e congela a medição de taxa.

        `InferidorMBP.drenar` existe porque uma queda de quantidade fica
        pendente esperando saber se foi execução ou cancelamento — sem um
        evento novo empurrando o relógio, ela nunca resolveria. No fim de um
        replay isso é exatamente o que acontece, então o drain avança o relógio
        além da janela de reconciliação e força a decisão.
        """
        if self.inferidor is not None:
            base = timestamp_ns
            if base is None:
                base = self.contadores.ts_ultimo_ns or 0
            self.inferidor.drenar(base + self.config.inferencia.janela_reconciliacao_ns + 1)
        if self.shadow_writer is not None:
            self.shadow_writer.close()
        if self.feed_observer is not None:
            self.feed_observer.parar()
        self._perf_fim = time.perf_counter()

    # ------------------------------------------------------------------
    # leitura
    # ------------------------------------------------------------------
    def segundos_decorridos(self) -> float:
        if self._perf_inicio is None:
            return 0.0
        fim = self._perf_fim if self._perf_fim is not None else time.perf_counter()
        return max(fim - self._perf_inicio, 0.0)

    def taxa_eventos_s(self) -> float:
        """Vazão de ponta a ponta medida em relógio de parede (ev/s).

        É a barra do projeto (10.000 ev/s). Com fonte de replay em velocidade
        limitada ou com MT5 ao vivo o número mede o MERCADO, não o pipeline —
        só faz sentido como medida de capacidade em `velocidade="max"`.
        """
        segundos = self.segundos_decorridos()
        if segundos <= 0:
            return 0.0
        return self.contadores.n_eventos_bus / segundos
