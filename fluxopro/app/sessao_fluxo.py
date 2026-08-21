"""`SessaoFluxo` — o produto montado: todas as peças instanciadas e ligadas.

Antes disto, `MotorSinais` e `InferidorMBP` não eram importados por módulo de
produção nenhum (registrado em `criticas/nucleo_r2.md:371-372`): as peças
existiam, testadas, e o pipeline nunca tinha rodado inteiro. Este arquivo é o
lugar onde a cadeia existe de verdade:

    fonte -> Barramento -> EstadoMercado -> analytics -> InferidorMBP
          -> LivroMBO -> detectores -> PerfilPlayer -> MotorSinais -> saída

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

import time
from dataclasses import dataclass, field
from typing import Callable

from fluxopro.analytics.agressao import MedidorAgressao
from fluxopro.analytics.brokers import RankingCorretoras
from fluxopro.analytics.delta import CumulativeDelta
from fluxopro.analytics.footprint import FootprintPorTimeframe
from fluxopro.analytics.volume_profile import VolumeProfile, VolumeProfilePorPeriodo
from fluxopro.analytics.vwap import VWAP
from fluxopro.app.config import (
    PRIORIDADE_MICRO,
    PRIORIDADE_MOTOR,
    PRIORIDADE_PERFIL_SESSAO,
    PRIORIDADE_SAIDA,
    ConfigOperacao,
)
from fluxopro.core.barramento import Barramento
from fluxopro.core.estado_mercado import EstadoMercado
from fluxopro.core.eventos import BookDelta, BookSnapshot, Trade
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
        # Motor de confluência.
        # ------------------------------------------------------------------
        self.motor: MotorSinais | None = None
        if cfg.ligar_motor:
            self.motor = MotorSinais(symbol, self.perfil_sessao, cfg.motor)
            barramento.assinar(Trade, self._ao_trade_motor, prioridade=PRIORIDADE_MOTOR)

        self._ultimo_estagio: tuple[EstagioSinal, object] | None = None

        # ------------------------------------------------------------------
        # Contagem — por último, para "processado" querer dizer processado.
        # ------------------------------------------------------------------
        barramento.assinar(Trade, self._contar_trade, prioridade=PRIORIDADE_SAIDA)
        barramento.assinar(
            BookSnapshot, self._contar_snapshot, prioridade=PRIORIDADE_SAIDA
        )
        barramento.assinar(BookDelta, self._contar_delta, prioridade=PRIORIDADE_SAIDA)

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

    def _ao_trade_motor(self, trade: Trade) -> None:
        assert self.motor is not None
        if trade.symbol != self.config.symbol:
            return
        self.contadores.n_trades_motor += 1
        sinal = self.motor.ao_trade(trade)
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
    #: reset e, por isso, NÃO podem ser zerados por esta camada. Trocar a
    #: instância deixaria a antiga assinada (contagem dobrada) e a nova no fim
    #: da faixa de prioridade — `Barramento` não tem `desassinar`.
    SEM_RESET_POSSIVEL = ("FootprintPorTimeframe", "RankingCorretoras")

    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Virada de pregão — **explícita**, chamada por quem sabe o calendário.

        A política está fixada em `core/estado_mercado.py`: virada explícita,
        porque só quem alimenta os eventos conhece o calendário da B3 (regular
        + after, feriado, rolagem). Esta camada é justamente "o adaptador/app
        que sabe", então é aqui que a virada acontece de verdade.

        ## Três grupos, três tratamentos

        **(a) Tem `iniciar_nova_sessao`/`nova_sessao`** — `EstadoMercado`,
        `CumulativeDelta`, `VWAP`, `MedidorAgressao`, `VolumeProfilePorPeriodo`.
        Chamado. Convenção do núcleo: acumulador corrente zera, histórico
        fechado sobrevive.

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

        **(c) Não tem API e assina sozinho** — `FootprintPorTimeframe` e
        `RankingCorretoras` (ver `SEM_RESET_POSSIVEL`). Estes **continuam
        carregando o dia anterior** e esta camada não tem como consertar:
        `Barramento` não expõe `desassinar`, então trocar a instância dobraria
        a contagem. Fica declarado em vez de silenciado. O footprint é o menos
        grave (ele fecha por bucket de tempo, então o candle corrente vira);
        `RankingCorretoras` com `janela_ns=None` de fábrica acumula desde a
        construção e é o que de fato mistura sessões.
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

        # (b) quem esta classe chama — recriado com a mesma config
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
