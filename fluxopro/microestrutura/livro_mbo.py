"""Livro de ofertas ordem-a-ordem, com fila FIFO por nível de preço.

`LivroMBO` é o estado que os detectores leem. Ele não sabe de onde os eventos
vêm: alimentado por um feed MBO real, cada chamada é um fato; alimentado pelo
`InferidorMBP`, cada chamada é uma hipótese — a diferença viaja no
`OrdemEvento` emitido (`fonte`/`confianca`), não na estrutura.

Custos no caminho quente (chamado por evento de book, a fonte mais volumosa):

* `adicionar`  — O(1) amortizado (`deque.append`; `heappush` só quando um nível
  de preço NOVO nasce, o que é raro).
* `cancelar`   — O(1). A remoção é preguiçosa: a ordem é marcada inativa e só é
  retirada da `deque` quando chega à frente da fila. Cada ordem entra e sai da
  deque no máximo uma vez, então o custo amortizado por ordem é constante.
* `executar`   — O(1) amortizado por contrato consumido.
* `modificar`  — O(1).
* `melhor_bid`/`melhor_ask` — O(1) amortizado (heap com remoção preguiçosa).
* `ultima_ordem_ativa` — O(1) amortizado. TAMBÉM é caminho quente, ao
  contrário do que esta lista deixava implícito: é por onde passa todo
  cancelamento inferido pelo `InferidorMBP`. A fila é podada pelas DUAS
  pontas — `executar` descarta morto pela frente, `ultima_ordem_ativa` pelo
  fim — porque é nessas duas pontas que as ordens saem.

Não há varredura de lista grande em nenhum desses caminhos. As APIs de
inspeção (`nivel`, `niveis_ordenados`) percorrem a fila e são de diagnóstico,
não de caminho quente.

Integridade: um livro CRUZADO (melhor bid >= melhor ask) tem DUAS causas
possíveis, e elas não significam a mesma coisa.

* **Alimentado por feed MBO real**, cruzamento é dado corrompido, evento
  perdido ou reordenação do feed. Mercado casado não cruza.
* **Alimentado pelo `InferidorMBP`** (book agregado por preço), cruzamento é
  também — e na prática, principalmente — DEFASAGEM DA PONTE: a queda de
  quantidade num nível só vira `cancelar` quando a janela de reconciliação
  expira, enquanto as inserções do lado oposto entram na hora. Nesse intervalo
  o livro reconstruído exibe liquidez que o feed já tirou. Isso não é feed
  ruim; é o preço de diferir o veredito execução×cancelamento.

O livro aceita o estado nos dois casos — recusar derrubaria a ingestão — mas
nunca em silêncio, e nunca confundindo um com o outro: ver `esta_cruzado`,
`cruzamento_e_transitorio`, `n_cruzamentos_detectados`,
`n_cruzamentos_por_reconciliacao` e `assinar_cruzamento`. Quem alimenta o
livro com defasagem declara isso em `registrar_liquidez_nao_aplicada`; sem
essa declaração todo cruzamento é tratado como corrupção, que é o padrão
certo. A verificação é O(1) e roda só onde o topo pode mudar.

Determinismo: a mesma sequência de chamadas produz sempre o mesmo estado e a
mesma sequência de eventos. Nenhuma estrutura depende de ordem de iteração de
`set`, de `hash` de objeto ou de relógio de parede.
"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import Side
from fluxopro.microestrutura.eventos_mbo import (
    CONFIANCA_OBSERVADO,
    FonteMicro,
    NivelDetalhado,
    Ordem,
    OrdemEvento,
    TipoEventoOrdem,
)

UM_SEGUNDO_NS = 1_000_000_000


def _mesclar(base: dict[str, object], extra: dict[str, object] | None) -> dict[str, object]:
    if extra:
        base.update(extra)
    return base


@dataclass(frozen=True, slots=True)
class ConfigLivroMBO:
    """Parâmetros do livro. Nenhum limiar cravado no código.

    `janela_reposicao_ns` — quanto tempo depois de um nível ser varrido uma
    ordem nova no mesmo preço ainda conta como reposição (defesa do preço).

    `exigir_mesmo_broker_para_reposicao` — quando o feed traz corretora por
    ordem (MBO real), exigir que a reposição venha do mesmo participante torna
    o sinal de "escora" muito mais forte. Em feed agregado não há corretora no
    book, então isto fica `False` e a reposição é uma propriedade do NÍVEL, não
    do player.
    """

    janela_reposicao_ns: int = 2 * UM_SEGUNDO_NS
    exigir_mesmo_broker_para_reposicao: bool = False


@dataclass(frozen=True, slots=True)
class CruzamentoLivro:
    """Alerta de livro cruzado (ou travado): o melhor bid alcançou o melhor ask.

    Emitido só quando o cruzamento é atribuído à FONTE — dado corrompido,
    evento perdido, reordenação. Defasagem conhecida de quem alimenta o livro
    (a ponte MBP) não produz alerta; ver `cruzamento_e_transitorio`.

    Não é um `OrdemEvento` de propósito: não é um fato do ciclo de vida de
    nenhuma ordem, é um diagnóstico sobre a INTEGRIDADE do livro. Misturá-lo no
    fluxo de `OrdemEvento` faria detectores que assinam eventos de ordem
    receberem algo que não é ordem.
    """

    timestamp_ns: int
    symbol: str
    melhor_bid: int
    melhor_ask: int
    n_cruzamentos: int


@dataclass(slots=True)
class _NivelInterno:
    price: int
    side: Side
    fila: deque[Ordem] = field(default_factory=deque)
    qty_total: int = 0
    n_ordens: int = 0

    # Volume total já executado neste nível desde que ele nasceu. Serve de
    # relógio de fila: quem entrou com X na frente ainda tem, no máximo,
    # X - (consumido desde a entrada) pela frente.
    consumido_acumulado: int = 0

    # Pico de quantidade simultaneamente VISÍVEL. É o denominador da razão de
    # iceberg (executado / exibido).
    qty_exibida_max: int = 0

    # Quantas ordens distintas já passaram pelo nível — distingue iceberg
    # (poucas ordens, muito volume) de reposição (muitas ordens).
    n_ordens_historicas: int = 0

    n_reposicoes: int = 0
    ts_ultimo_consumo_ns: int | None = None
    broker_ultimo_consumo: str = ""

    # O preço deste nível tem entrada VIVA no heap do lado? A remoção do heap é
    # preguiçosa: `melhor_bid`/`melhor_ask` descartam o topo quando o nível está
    # zerado. Sem esta marca, um nível esvaziado e depois REPOVOADO ficaria fora
    # do heap para sempre — o dicionário guarda o nível (histórico), então
    # `_obter_nivel` não republicava o preço e o topo de livro ficava errado em
    # silêncio.
    no_heap: bool = False


class LivroMBO:
    """Livro completo por ordem, com fila FIFO por nível de preço."""

    def __init__(
        self,
        symbol: str,
        config: ConfigLivroMBO | None = None,
        barramento: Barramento | None = None,
    ) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigLivroMBO()
        self._barramento = barramento
        self._ouvintes: list[Callable[[OrdemEvento], None]] = []

        self._ordens: dict[str, Ordem] = {}
        self._bids: dict[int, _NivelInterno] = {}
        self._asks: dict[int, _NivelInterno] = {}
        # Heaps com remoção preguiçosa. Bids guardam preço negado (max-heap).
        self._heap_bids: list[int] = []
        self._heap_asks: list[int] = []

        # Integridade: livro cruzado. Ver `esta_cruzado`.
        # `n_cruzamentos_detectados` conta só o que é problema da FONTE.
        # `n_cruzamentos_por_reconciliacao` conta o que é defasagem conhecida
        # de quem alimenta o livro — separado, porque somar os dois num
        # contador só é o que fazia o número mentir em modo MBP.
        self.n_cruzamentos_detectados = 0
        self.n_cruzamentos_por_reconciliacao = 0
        self._cruzado = False
        self._cruzamento_contado = False
        self._ouvintes_cruzamento: list[Callable[[CruzamentoLivro], None]] = []
        self._liquidez_nao_aplicada: Callable[[Side, int], bool] | None = None

    # ------------------------------------------------------------------
    # publicação
    # ------------------------------------------------------------------
    def assinar_evento(self, callback: Callable[[OrdemEvento], None]) -> None:
        """Registra ouvinte direto (alternativa ao barramento, sem alocação extra)."""
        self._ouvintes.append(callback)

    def _emitir(self, evento: OrdemEvento) -> None:
        for ouvinte in self._ouvintes:
            ouvinte(evento)
        if self._barramento is not None:
            self._barramento.publicar(evento)

    # ------------------------------------------------------------------
    # integridade — livro cruzado
    # ------------------------------------------------------------------
    def assinar_cruzamento(self, callback: Callable[[CruzamentoLivro], None]) -> None:
        """Registra ouvinte de alerta de livro cruzado. Opcional.

        Só recebe cruzamento atribuído à FONTE. Cruzamento transitório de
        reconciliação não é empurrado por aqui de propósito: alertar por algo
        que a própria ponte vai desfazer sozinha em 300 ms transformaria o
        canal de integridade em ruído proporcional ao volume do tape, que é
        exatamente o que faz um alerta deixar de ser lido. Ele fica registrado
        em `n_cruzamentos_por_reconciliacao`.
        """
        self._ouvintes_cruzamento.append(callback)

    def registrar_liquidez_nao_aplicada(self, consulta: Callable[[Side, int], bool]) -> None:
        """Quem alimenta o livro declara que aplica as saídas com DEFASAGEM.

        `consulta(side, price)` responde: "existe liquidez que a fonte já tirou
        deste nível e que o livro ainda exibe porque o veredito não saiu?".

        Existe por causa do `InferidorMBP`. Reconstruir MBO a partir de book
        agregado obriga a DIFERIR a queda de quantidade: até a janela de
        reconciliação expirar, aquela queda ainda pode ser explicada por um
        negócio cuja impressão não chegou, e aplicá-la na hora como
        cancelamento apagaria a distinção que o módulo inteiro existe para
        fazer. Enquanto isso as inserções do lado oposto entram na hora — logo
        o livro reconstruído fica cruzado POR CONSTRUÇÃO DA PONTE, sem que
        nada de errado tenha acontecido com o feed.

        Sem esta declaração, todo cruzamento é tratado como corrupção. Esse é
        o padrão certo: feed MBO real não cruza, e um livro que não sabe de
        defasagem nenhuma não deve inventar desculpa para o que vê.
        """
        self._liquidez_nao_aplicada = consulta

    @property
    def esta_cruzado(self) -> bool:
        """`True` quando o melhor bid alcançou o melhor ask. O(1) amortizado.

        É o FATO GEOMÉTRICO, e só ele: o topo de um lado alcançou o do outro.
        Não é sinônimo de "feed corrompido" — ver `cruzamento_e_transitorio`.

        POLÍTICA — sinalizar, nunca levantar exceção.

        Levantar exceção aqui seria a decisão errada: `adicionar`/`executar`
        rodam por evento de book (a fonte mais volumosa do sistema) e um feed
        ruim de madrugada derrubaria a aplicação inteira em vez de degradar.
        Pior: estouraria dentro do laço de ingestão, deixando o livro num
        estado parcialmente aplicado — exatamente a corrupção que se queria
        evitar.

        Então a política é: o livro ACEITA o estado cruzado, mas nunca em
        silêncio. Quem consome escolhe o rigor:

        * `esta_cruzado` — o fato geométrico;
        * `cruzamento_e_transitorio` — se o cruzamento ATUAL é defasagem
          conhecida da ponte MBP em vez de problema da fonte. O gate de
          "não operar com livro sujo" é
          `esta_cruzado and not cruzamento_e_transitorio`;
        * `n_cruzamentos_detectados` — episódios atribuídos à FONTE;
        * `n_cruzamentos_por_reconciliacao` — episódios de defasagem da ponte;
        * `assinar_cruzamento` — alerta empurrado dos primeiros.

        Cruzado (`bid > ask`) e TRAVADO (`bid == ask`) contam igual: nos dois
        casos existe negócio possível que o feed não reportou, e o spread
        calculado a jusante fica <= 0. `>=` é a comparação certa.

        Custo: dois `heapq` peek com limpeza preguiçosa (o mesmo trabalho de
        `melhor_bid`/`melhor_ask`) e dois `dict.get`. Não varre fila, não varre
        nível, não itera dicionário — o custo NÃO cresce com a profundidade do
        livro.
        """
        bid = self.melhor_bid()
        if bid is None:
            return False
        ask = self.melhor_ask()
        return ask is not None and bid >= ask

    @property
    def cruzamento_e_transitorio(self) -> bool:
        """O cruzamento ATUAL é defasagem da ponte, não problema da fonte?

        A pergunta é feita a quem alimenta o livro
        (`registrar_liquidez_nao_aplicada`) sobre os DOIS topos que estão se
        cruzando: algum dos dois exibe liquidez que a fonte já tirou? Se sim, o
        cruzamento é artefato da reconciliação e se desfaz sozinho quando o
        veredito sair.

        `False` quando não há defasagem declarada — inclusive quando não há
        cruzamento nenhum.

        A atribuição é feita pela CAUSA, não por um relógio. A alternativa
        óbvia — "só conte se persistir além da janela de reconciliação" —
        depende de calibrar um limiar contra outro limiar e erra na borda
        exata (o cruzamento pode nascer no mesmo timestamp da queda que o
        causou e durar a janela inteira). Perguntar pelo estado responde a
        mesma coisa sem limiar nenhum, e se corrige sozinha: quando o veredito
        sai, o `cancelar`/`executar` que o aplica chama esta verificação de
        novo — se o livro AINDA estiver cruzado, já não há defasagem para
        explicar e o episódio passa a contar como problema da fonte.
        """
        if self._liquidez_nao_aplicada is None:
            return False
        bid = self.melhor_bid()
        if bid is None:
            return False
        ask = self.melhor_ask()
        if ask is None or bid < ask:
            return False
        return self._liquidez_nao_aplicada(Side.BUY, bid) or self._liquidez_nao_aplicada(
            Side.SELL, ask
        )

    def _verificar_cruzamento(self, timestamp_ns: int) -> None:
        """Atualiza o latch de cruzamento. Chamado só onde o topo pode mudar.

        O contador é por EPISÓDIO (não-cruzado -> cruzado), não por evento: um
        feed que fica cruzado por mil mensagens é UMA anomalia, e contar mil
        transformaria o contador em ruído proporcional ao volume.

        Um episódio pode começar como defasagem da ponte e VIRAR problema da
        fonte: enquanto houver liquidez não aplicada explicando o cruzamento,
        ele conta em `n_cruzamentos_por_reconciliacao`; se o livro continuar
        cruzado depois que a explicação sumir, o mesmo episódio passa a contar
        em `n_cruzamentos_detectados` e alerta. É o caso do feed que corrompe
        durante uma reconciliação, e ele não pode ficar escondido atrás da
        desculpa da ponte.
        """
        if not self.esta_cruzado:
            self._cruzado = False
            self._cruzamento_contado = False
            return

        if self.cruzamento_e_transitorio:
            if not self._cruzado:
                self.n_cruzamentos_por_reconciliacao += 1
            self._cruzado = True
            return

        self._cruzado = True
        if self._cruzamento_contado:
            return
        self._cruzamento_contado = True
        self.n_cruzamentos_detectados += 1
        if self._ouvintes_cruzamento:
            bid = self.melhor_bid()
            ask = self.melhor_ask()
            if bid is not None and ask is not None:
                alerta = CruzamentoLivro(
                    timestamp_ns=timestamp_ns,
                    symbol=self.symbol,
                    melhor_bid=bid,
                    melhor_ask=ask,
                    n_cruzamentos=self.n_cruzamentos_detectados,
                )
                for ouvinte in self._ouvintes_cruzamento:
                    ouvinte(alerta)

    # ------------------------------------------------------------------
    # estrutura interna
    # ------------------------------------------------------------------
    def _lado(self, side: Side) -> dict[int, _NivelInterno]:
        return self._bids if side is Side.BUY else self._asks

    def _obter_nivel(self, side: Side, price: int) -> _NivelInterno:
        lado = self._lado(side)
        nivel = lado.get(price)
        if nivel is None:
            nivel = _NivelInterno(price=price, side=side)
            lado[price] = nivel
        if not nivel.no_heap:
            # Preço novo, OU nível que ressuscitou depois de ser esvaziado e
            # descartado do heap pela limpeza preguiçosa. Sem este segundo caso
            # o preço sumia do topo de livro permanentemente.
            if side is Side.BUY:
                heapq.heappush(self._heap_bids, -price)
            else:
                heapq.heappush(self._heap_asks, price)
            nivel.no_heap = True
        return nivel

    def _descartar_nivel_se_vazio(self, nivel: _NivelInterno) -> None:
        if nivel.n_ordens == 0 and nivel.qty_total == 0 and not nivel.fila:
            # O nível é mantido no dicionário enquanto guardar histórico útil
            # (reposições, pico exibido). Só some quando nunca teve nada.
            if nivel.n_ordens_historicas == 0:
                self._lado(nivel.side).pop(nivel.price, None)

    # ------------------------------------------------------------------
    # operações do caminho quente
    # ------------------------------------------------------------------
    def adicionar(
        self,
        order_id: str,
        side: Side,
        price: int,
        qty: int,
        timestamp_ns: int,
        broker: str = "",
        fonte: FonteMicro = FonteMicro.MBO,
        confianca: float = CONFIANCA_OBSERVADO,
        evidencia: dict[str, object] | None = None,
    ) -> Ordem:
        """Insere uma ordem no fim da fila do seu nível. O(1) amortizado."""
        if qty <= 0:
            raise ValueError(f"qty deve ser positiva (recebido {qty})")
        if order_id in self._ordens and self._ordens[order_id].ativa:
            raise ValueError(f"order_id ja ativo no livro: {order_id}")

        nivel = self._obter_nivel(side, price)
        ordem = Ordem(
            order_id=order_id,
            side=side,
            price=price,
            qty_original=qty,
            qty_restante=qty,
            timestamp_entrada_ns=timestamp_ns,
            broker=broker,
            position_na_fila=nivel.n_ordens,
            qty_a_frente_na_entrada=nivel.qty_total,
            consumido_nivel_na_entrada=nivel.consumido_acumulado,
        )
        ordem.eh_reposicao = self._eh_reposicao(nivel, timestamp_ns, broker)
        if ordem.eh_reposicao:
            nivel.n_reposicoes += 1

        nivel.fila.append(ordem)
        nivel.qty_total += qty
        nivel.n_ordens += 1
        nivel.n_ordens_historicas += 1
        if nivel.qty_total > nivel.qty_exibida_max:
            nivel.qty_exibida_max = nivel.qty_total
        self._ordens[order_id] = ordem

        self._emitir(
            OrdemEvento(
                timestamp_ns=timestamp_ns,
                symbol=self.symbol,
                tipo=TipoEventoOrdem.NEW,
                side=side,
                price=price,
                qty=qty,
                order_id=order_id,
                qty_restante=qty,
                broker=broker,
                fonte=fonte,
                confianca=confianca,
                evidencia=self._com_reposicao(evidencia, ordem),
            )
        )
        # Única operação que pode CRIAR um cruzamento: só entrar liquidez nova
        # move um topo na direção do outro lado.
        self._verificar_cruzamento(timestamp_ns)
        return ordem

    def _eh_reposicao(self, nivel: _NivelInterno, timestamp_ns: int, broker: str) -> bool:
        ts_consumo = nivel.ts_ultimo_consumo_ns
        if ts_consumo is None:
            return False
        if timestamp_ns - ts_consumo > self.config.janela_reposicao_ns:
            return False
        if self.config.exigir_mesmo_broker_para_reposicao:
            if not broker or broker != nivel.broker_ultimo_consumo:
                return False
        return True

    @staticmethod
    def _com_reposicao(
        evidencia: dict[str, object] | None, ordem: Ordem
    ) -> dict[str, object]:
        base: dict[str, object] = {"eh_reposicao": ordem.eh_reposicao}
        if evidencia:
            base.update(evidencia)
        return base

    def cancelar(
        self,
        order_id: str,
        timestamp_ns: int,
        fonte: FonteMicro = FonteMicro.MBO,
        confianca: float = CONFIANCA_OBSERVADO,
        evidencia: dict[str, object] | None = None,
        tipo: TipoEventoOrdem = TipoEventoOrdem.CANCEL,
    ) -> Ordem | None:
        """Retira uma ordem do livro. O(1) — a remoção da fila é preguiçosa."""
        ordem = self._ordens.get(order_id)
        if ordem is None or not ordem.ativa:
            return None

        nivel = self._lado(ordem.side).get(ordem.price)
        restante = ordem.qty_restante
        ordem.ativa = False
        ordem.qty_restante = 0
        ordem.timestamp_saida_ns = timestamp_ns
        if nivel is not None:
            nivel.qty_total -= restante
            nivel.n_ordens -= 1
            self._descartar_nivel_se_vazio(nivel)

        self._emitir(
            OrdemEvento(
                timestamp_ns=timestamp_ns,
                symbol=self.symbol,
                tipo=tipo,
                side=ordem.side,
                price=ordem.price,
                qty=restante,
                order_id=order_id,
                qty_restante=0,
                broker=ordem.broker,
                fonte=fonte,
                confianca=confianca,
                evidencia=dict(evidencia) if evidencia else {},
            )
        )
        # Saída de liquidez não cria cruzamento, mas DESFAZ um — sem isto o
        # latch ficaria preso e o próximo cruzamento real não seria contado.
        self._verificar_cruzamento(timestamp_ns)
        return ordem

    def expirar(self, order_id: str, timestamp_ns: int) -> Ordem | None:
        """Saída por regra de mercado, não por decisão do participante."""
        return self.cancelar(order_id, timestamp_ns, tipo=TipoEventoOrdem.EXPIRE)

    def modificar(
        self,
        order_id: str,
        nova_qty: int,
        timestamp_ns: int,
        fonte: FonteMicro = FonteMicro.MBO,
        confianca: float = CONFIANCA_OBSERVADO,
        tipo_evento: TipoEventoOrdem = TipoEventoOrdem.REPLACE,
        evidencia: dict[str, object] | None = None,
    ) -> Ordem | None:
        """Altera a quantidade de uma ordem viva. O(1).

        Redução mantém a prioridade de fila (é o comportamento das bolsas);
        aumento perde prioridade e a ordem vai para o fim da fila.

        `tipo_evento` permite marcar a redução como CANCEL parcial — é o que a
        inferência MBP faz quando a queda de quantidade do nível é menor que a
        ordem sintética do fim da fila.
        """
        ordem = self._ordens.get(order_id)
        if ordem is None or not ordem.ativa:
            return None
        if nova_qty <= 0:
            return self.cancelar(order_id, timestamp_ns, fonte=fonte, confianca=confianca)

        nivel = self._obter_nivel(ordem.side, ordem.price)
        delta = nova_qty - ordem.qty_restante
        if delta == 0:
            return ordem

        perdeu_prioridade = delta > 0
        if perdeu_prioridade:
            # Sai de onde está (preguiçosamente) e volta para o fim.
            ordem.ativa = False
            nivel.qty_total -= ordem.qty_restante
            nivel.n_ordens -= 1
            nova = Ordem(
                order_id=order_id,
                side=ordem.side,
                price=ordem.price,
                qty_original=nova_qty,
                qty_restante=nova_qty,
                timestamp_entrada_ns=timestamp_ns,
                broker=ordem.broker,
                position_na_fila=nivel.n_ordens,
                qty_a_frente_na_entrada=nivel.qty_total,
                # o executado herdado já aconteceu antes desta reentrada, então
                # a âncora de consumo o desconta para o saldo de fila zerar aqui
                consumido_nivel_na_entrada=nivel.consumido_acumulado - ordem.qty_executada,
                qty_executada=ordem.qty_executada,
                n_reducoes=ordem.n_reducoes,
                n_recargas=ordem.n_recargas,
                eh_reposicao=ordem.eh_reposicao,
            )
            nivel.fila.append(nova)
            nivel.qty_total += nova_qty
            nivel.n_ordens += 1
            self._ordens[order_id] = nova
            ordem = nova
        else:
            ordem.qty_restante = nova_qty
            ordem.n_reducoes += 1
            nivel.qty_total += delta

        if nivel.qty_total > nivel.qty_exibida_max:
            nivel.qty_exibida_max = nivel.qty_total

        self._emitir(
            OrdemEvento(
                timestamp_ns=timestamp_ns,
                symbol=self.symbol,
                tipo=tipo_evento,
                side=ordem.side,
                price=ordem.price,
                qty=abs(delta),
                order_id=order_id,
                qty_restante=nova_qty,
                broker=ordem.broker,
                fonte=fonte,
                confianca=confianca,
                evidencia=_mesclar(
                    {"delta_qty": delta, "perdeu_prioridade": perdeu_prioridade},
                    evidencia,
                ),
            )
        )
        return ordem

    def recarregar(
        self,
        order_id: str,
        qty_adicional: int,
        timestamp_ns: int,
        fonte: FonteMicro = FonteMicro.MBO,
        confianca: float = CONFIANCA_OBSERVADO,
    ) -> Ordem | None:
        """Reabastece uma ordem MANTENDO o `order_id` e a prioridade.

        É a assinatura de iceberg em feed MBO real: a mesma ordem executa mais
        do que jamais exibiu. Em feed agregado isto é indistinguível de uma
        ordem nova no mesmo preço — ver `inferencia_mbp`.
        """
        ordem = self._ordens.get(order_id)
        if ordem is None or not ordem.ativa or qty_adicional <= 0:
            return None
        nivel = self._obter_nivel(ordem.side, ordem.price)
        ordem.qty_restante += qty_adicional
        ordem.n_recargas += 1
        nivel.qty_total += qty_adicional
        if nivel.qty_total > nivel.qty_exibida_max:
            nivel.qty_exibida_max = nivel.qty_total

        self._emitir(
            OrdemEvento(
                timestamp_ns=timestamp_ns,
                symbol=self.symbol,
                tipo=TipoEventoOrdem.REPLACE,
                side=ordem.side,
                price=ordem.price,
                qty=qty_adicional,
                order_id=order_id,
                qty_restante=ordem.qty_restante,
                broker=ordem.broker,
                fonte=fonte,
                confianca=confianca,
                evidencia={
                    "recarga": True,
                    "n_recargas": ordem.n_recargas,
                    "qty_original": ordem.qty_original,
                    "qty_executada": ordem.qty_executada,
                },
            )
        )
        return ordem

    def executar(
        self,
        side: Side,
        price: int,
        qty: int,
        timestamp_ns: int,
        broker_agressor: str = "",
        fonte: FonteMicro = FonteMicro.MBO,
        confianca: float = CONFIANCA_OBSERVADO,
        evidencia: dict[str, object] | None = None,
    ) -> tuple[OrdemEvento, ...]:
        """Consome `qty` da FRENTE da fila do nível. O(1) amortizado por contrato.

        `side` é o lado das ordens PASSIVAS consumidas (uma agressão de compra
        consome o lado SELL). Devolve um evento TRADE por ordem tocada, na
        ordem de prioridade — é isso que dá a leitura de "quem estava na
        frente" que o fluxo agregado não tem.
        """
        nivel = self._lado(side).get(price)
        if nivel is None or qty <= 0:
            return ()

        eventos: list[OrdemEvento] = []
        restante = qty
        while restante > 0 and nivel.fila:
            frente = nivel.fila[0]
            if not frente.ativa or frente.qty_restante <= 0:
                nivel.fila.popleft()
                continue

            consumido = frente.qty_restante if frente.qty_restante <= restante else restante
            frente.qty_restante -= consumido
            frente.qty_executada += consumido
            frente.n_reducoes += 1
            restante -= consumido
            nivel.qty_total -= consumido
            nivel.consumido_acumulado += consumido
            nivel.ts_ultimo_consumo_ns = timestamp_ns
            nivel.broker_ultimo_consumo = frente.broker

            zerou = frente.qty_restante == 0
            if zerou:
                frente.ativa = False
                frente.timestamp_saida_ns = timestamp_ns
                nivel.fila.popleft()
                nivel.n_ordens -= 1

            base_evidencia: dict[str, object] = {
                "idade_ordem_ns": frente.idade_ns(timestamp_ns),
                "qty_executada_acumulada": frente.qty_executada,
                "qty_original_ordem": frente.qty_original,
                "n_recargas_ordem": frente.n_recargas,
                "zerou_ordem": zerou,
                "broker_agressor": broker_agressor,
            }
            if evidencia:
                base_evidencia.update(evidencia)

            evento = OrdemEvento(
                timestamp_ns=timestamp_ns,
                symbol=self.symbol,
                tipo=TipoEventoOrdem.TRADE,
                side=side,
                price=price,
                qty=consumido,
                order_id=frente.order_id,
                qty_restante=frente.qty_restante,
                broker=frente.broker,
                fonte=fonte,
                confianca=confianca,
                evidencia=base_evidencia,
            )
            eventos.append(evento)
            self._emitir(evento)

        self._descartar_nivel_se_vazio(nivel)
        # Uma varredura pode desfazer o cruzamento (foi ela que "resolveu" o
        # negócio que faltava). Uma checagem por CHAMADA, não por contrato.
        self._verificar_cruzamento(timestamp_ns)
        return tuple(eventos)

    # ------------------------------------------------------------------
    # leitura
    # ------------------------------------------------------------------
    def ordem(self, order_id: str) -> Ordem | None:
        return self._ordens.get(order_id)

    def idade_ordem_ns(self, order_id: str, agora_ns: int) -> int | None:
        ordem = self._ordens.get(order_id)
        return None if ordem is None else ordem.idade_ns(agora_ns)

    def qty_a_frente(self, order_id: str) -> int | None:
        """Volume ainda à frente da ordem na fila. O(1).

        É uma COTA SUPERIOR: desconta o que já foi executado no nível desde a
        entrada da ordem, mas não desconta ordens à frente que foram
        CANCELADAS (essas melhoram a posição sem gerar consumo). Manter o
        número exato exigiria varrer a fila — O(n) no caminho quente.
        """
        ordem = self._ordens.get(order_id)
        if ordem is None or not ordem.ativa:
            return None
        nivel = self._lado(ordem.side).get(ordem.price)
        if nivel is None:
            return None
        # Consumo do nível desde a entrada da ordem, descontando o que a
        # própria ordem já executou (isso saiu dela, não de quem está à frente).
        consumido_desde_entrada = (
            nivel.consumido_acumulado
            - ordem.consumido_nivel_na_entrada
            - ordem.qty_executada
        )
        return max(0, ordem.qty_a_frente_na_entrada - consumido_desde_entrada)

    def nivel(self, side: Side, price: int) -> NivelDetalhado | None:
        """Fotografia do nível com a fila explícita. API de inspeção — O(n)."""
        nivel = self._lado(side).get(price)
        if nivel is None:
            return None
        vivas = tuple(o for o in nivel.fila if o.ativa and o.qty_restante > 0)
        return NivelDetalhado(
            price=price,
            side=side,
            ordens=vivas,
            qty_total=nivel.qty_total,
            n_ordens=len(vivas),
        )

    def ultima_ordem_ativa(self, side: Side, price: int) -> Ordem | None:
        """Ordem de MENOR prioridade viva no nível (fim da fila). O(1) amortizado.

        É o alvo convencional de um cancelamento inferido a partir de dado
        agregado: sem identidade de ordem, cancelar a mais nova preserva a
        ordem mais antiga, que é a que carrega a informação de permanência.

        NÃO é API de inspeção: é caminho quente. Cada cancelamento inferido
        pelo `InferidorMBP` passa por aqui, e um cancelamento grande passa
        várias vezes seguidas (`_resolver_como_cancelamento` chama em laço até
        cobrir a queda). Como quem sai por aqui sai justamente do FIM da fila,
        e a remoção do livro é preguiçosa, a versão anterior — `for ordem in
        reversed(nivel.fila)` — revarria um sufixo de mortos que crescia a
        cada cancelamento: O(n²) por nível ao longo da sessão. Medido no
        `.mut/bench_r3.py` estágio 6 (a configuração real, MBP -> livro ->
        detectores), era o segundo maior custo do pipeline inteiro.

        A poda pelo fim é o espelho exato da que `executar` já fazia pela
        frente, e é segura porque `ativa=False` é definitivo: `adicionar`
        recusa `order_id` já ativo, `cancelar`/`expirar` nunca reativam, e o
        aumento de quantidade em `modificar` mata a entrada antiga e APPENDA
        uma nova. Uma entrada inativa na fila não volta a viver, então retirá-la
        não perde informação nenhuma — o histórico do nível mora nos contadores
        (`n_ordens_historicas`, `consumido_acumulado`), não na deque.
        """
        nivel = self._lado(side).get(price)
        if nivel is None:
            return None
        fila = nivel.fila
        while fila:
            ultima = fila[-1]
            if ultima.ativa and ultima.qty_restante > 0:
                return ultima
            fila.pop()
        return None

    def qty_total(self, side: Side, price: int) -> int:
        nivel = self._lado(side).get(price)
        return 0 if nivel is None else nivel.qty_total

    def n_reposicoes(self, side: Side, price: int) -> int:
        nivel = self._lado(side).get(price)
        return 0 if nivel is None else nivel.n_reposicoes

    def qty_exibida_max(self, side: Side, price: int) -> int:
        nivel = self._lado(side).get(price)
        return 0 if nivel is None else nivel.qty_exibida_max

    def melhor_bid(self) -> int | None:
        """Melhor compra. O(1) amortizado (heap com remoção preguiçosa)."""
        while self._heap_bids:
            price = -self._heap_bids[0]
            nivel = self._bids.get(price)
            if nivel is not None and nivel.qty_total > 0:
                return price
            heapq.heappop(self._heap_bids)
            if nivel is not None:
                # O nível continua no dicionário (guarda histórico), mas saiu do
                # heap. Se voltar a receber ordem, `_obter_nivel` republica.
                nivel.no_heap = False
        return None

    def melhor_ask(self) -> int | None:
        while self._heap_asks:
            price = self._heap_asks[0]
            nivel = self._asks.get(price)
            if nivel is not None and nivel.qty_total > 0:
                return price
            heapq.heappop(self._heap_asks)
            if nivel is not None:
                nivel.no_heap = False
        return None

    def niveis_ordenados(self, side: Side, profundidade: int = 10) -> tuple[NivelDetalhado, ...]:
        """Top N níveis do lado. API de inspeção — não é caminho quente."""
        lado = self._lado(side)
        precos = sorted(
            (p for p, n in lado.items() if n.qty_total > 0),
            reverse=side is Side.BUY,
        )[:profundidade]
        resultado = []
        for preco in precos:
            detalhe = self.nivel(side, preco)
            if detalhe is not None:
                resultado.append(detalhe)
        return tuple(resultado)
