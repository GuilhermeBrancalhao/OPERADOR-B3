"""A ponte: reconstruir eventos de ORDEM a partir de book AGREGADO POR PREÇO.

=============================================================================
POR QUE ISTO EXISTE
=============================================================================
O feed acessível hoje (DOM do MetaTrader5, via `market_book_add`/
`market_book_get`) entrega MBP — *market by price*: por nível, só o total de
contratos e às vezes a contagem de ordens. Um nível que vai de 150 para 120
contratos é TUDO o que se vê. O feed MBO — *market by order*, com identidade,
tamanho e prioridade de cada ordem — só existe em UMDF/ProfitDLL.

A leitura de fluxo que este projeto serve é sobre COMPORTAMENTO DE ORDEM. Sem
uma ponte, ela simplesmente não roda no dado disponível. Esta ponte existe
para rodar — e para dizer, em cada evento que produz, o quanto aquilo é
chute.

=============================================================================
O QUE É OBSERVADO (fato)
=============================================================================
* A quantidade total de cada nível de preço, a cada leitura do book.
* A variação dessa quantidade entre duas leituras.
* Cada negócio impresso: preço, quantidade, lado do agressor, timestamp.
* A ordem temporal entre esses dois fluxos, dentro da resolução do feed.

=============================================================================
O QUE É INFERIDO (hipótese, sempre com `confianca < 1.0`)
=============================================================================
* **Queda de quantidade = execução ou cancelamento.** A distinção sai da
  RECONCILIAÇÃO com o fluxo de negócios: se houve negócio naquele preço, no
  mesmo lado passivo, dentro de `janela_reconciliacao_ns`, a queda é atribuída
  a execução até o volume negociado; o que sobra é atribuído a cancelamento.
  Exemplo canônico: nível cai de 150 para 120 (queda de 30). Houve trade de 30
  naquele preço no mesmo instante -> execução, confiança alta. Não houve trade
  nenhum -> cancelamento.
* **Quanto vale um cancelamento inferido depende de ONDE ele aconteceu.** Longe
  do topo do livro nenhum negócio poderia ter ocorrido, então "sem trade" é
  prova quase direta de cancelamento (confiança alta). No topo, "sem trade"
  pode ser apenas um negócio cuja impressão ainda não chegou — por isso a
  resolução é DIFERIDA até a janela de reconciliação expirar, e mesmo assim
  sai com confiança baixa.
* **Aumento de quantidade = ordem nova.** Pode ser uma ordem só, podem ser
  dez; pode ser também uma ordem existente aumentada (que na bolsa perde
  prioridade). Modelamos como uma ordem sintética nova.
* **A fila.** As ordens sintéticas entram no fim e são consumidas pela frente
  (prioridade preço-tempo). Isso IMITA a regra da bolsa, mas a composição real
  da fila é desconhecida. Cancelamento inferido tira do FIM da fila, por
  convenção: sem identidade, preservar a ordem mais antiga preserva a única
  informação de permanência que existe.

=============================================================================
O QUE É INDETECTÁVEL SEM MBO REAL (nenhuma engenharia resolve)
=============================================================================
1. **Identidade da ordem.** 150 -> 120 pode ser uma ordem de 30 cancelada, três
   de 10, ou uma de 200 reduzida para 170. Indistinguível, ponto final.
2. **Posição real na fila e prioridade temporal.** Nada no MBP diz quem chegou
   antes. Toda posição de fila aqui é convenção, não medição.
3. **Idade de uma ordem específica.** Mede-se a idade do NÍVEL, nunca a da
   oferta que interessa.
4. **Iceberg de verdade.** A parte oculta nunca aparece no dado. O sintoma
   (executar mais do que exibia) é IDÊNTICO ao de várias ordens repondo o
   preço rapidamente. MBP não separa iceberg de reposição — só MBO separa,
   porque lá é o mesmo `order_id` executando além do que exibiu.
5. **Modificação vs. cancelar+recolocar.** Uma redução de quantidade e um
   cancelamento parcial produzem exatamente o mesmo delta.
6. **Autoria por ordem no book.** O DOM do MT5 não traz corretora. A corretora
   só existe no negócio impresso — e nem sempre. Logo, "quem está defendendo
   o preço" é sempre hipótese sobre o NÍVEL, jamais sobre o participante.
7. **Cancelamento simultâneo à execução no mesmo preço e instante.** Os dois
   viram um delta só; a separação é rateio, não medição.
8. **Ordens que nascem e morrem entre duas leituras.** O MT5 é polling; nada
   garante ver uma oferta que viveu menos que o intervalo de leitura. Retirada
   muito rápida de liquidez pode não deixar rastro NENHUM.

Consequência prática: em modo MBP, `DetectorIceberg` e `DetectorReposicao`
olham para o mesmo sintoma por caminhos diferentes e ambos saem com confiança
reduzida — é assim que tem de ser.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass

from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.microestrutura.eventos_mbo import FonteMicro, TipoEventoOrdem
from fluxopro.microestrutura.livro_mbo import LivroMBO

UM_MILISSEGUNDO_NS = 1_000_000


@dataclass(frozen=True, slots=True)
class ConfigInferenciaMBP:
    """Parâmetros da ponte MBP -> MBO. Nenhum limiar cravado no código.

    `janela_reconciliacao_ns` — folga temporal entre a queda de quantidade no
    book e a impressão do negócio correspondente. Precisa cobrir o jitter do
    feed (no MT5, o intervalo de polling). Curta demais: execução vira
    cancelamento. Longa demais: cancelamento vira execução.

    `profundidade_topo_ticks` — a que distância do melhor preço um nível ainda
    é "negociável". Fora disso, uma queda sem negócio é cancelamento quase
    certo, e a confiança sobe.

    `confianca_execucao_lado_nao_confirmado` — TETO (não valor fixo) para a
    execução inferida a partir de negócio com agressor `UNKNOWN`. Ver
    `_executar`: sem o lado do agressor, metade da reconciliação não
    aconteceu, então a execução não pode valer o mesmo que uma com o lado
    confirmado.
    """

    janela_reconciliacao_ns: int = 300 * UM_MILISSEGUNDO_NS
    profundidade_topo_ticks: int = 2

    confianca_execucao_com_trade_exato: float = 0.90
    confianca_execucao_parcial: float = 0.70
    confianca_execucao_lado_nao_confirmado: float = 0.60
    confianca_cancelamento_no_topo: float = 0.55
    confianca_cancelamento_fora_topo: float = 0.90
    confianca_insercao: float = 0.85

    prefixo_ordem_sintetica: str = "INF"


@dataclass(slots=True)
class _TradeBuffer:
    """Negócio impresso ainda não conciliado com queda de quantidade."""

    timestamp_ns: int
    price: int
    qty_restante: int
    agressor: AgressorSide
    trade_id: str


@dataclass(slots=True)
class _QuedaPendente:
    """Queda de quantidade esperando para saber se foi execução ou cancelamento."""

    timestamp_ns: int
    side: Side
    price: int
    qty_restante: int
    qty_original: int
    distancia_do_topo: int

    # Quanto desta queda já foi atribuído a execução. Não é contabilidade
    # redundante com `qty_restante`: ele distingue "sobra de uma queda que
    # NEGOCIOU" de "queda que nunca viu negócio", e essas duas coisas não
    # podem sair com a mesma confiança de cancelamento — ver
    # `_resolver_como_cancelamento`.
    qty_executada: int = 0


class InferidorMBP:
    """Traduz book agregado + fluxo de negócios em eventos de ordem.

    Alimenta um `LivroMBO` com ordens SINTÉTICAS, de modo que os detectores
    consumam exatamente o mesmo `OrdemEvento` nos dois mundos — a diferença
    aparece em `fonte=MBP_INFERIDO` e `confianca<1.0`, nunca na forma do dado.

    Custos — o que a reconciliação obriga, medido, não estimado:

    * `ao_trade` e `ao_delta` são O(p) no número de itens vivos DO MESMO PREÇO
      (quedas pendentes para um negócio, negócios em buffer para uma queda),
      mais O(1) amortizado de manutenção das filas. Só o mesmo preço pode
      casar, então este é o custo mínimo da regra; `p` é tipicamente 1 e é
      limitado pelo que couber em `janela_reconciliacao_ns`.
    * `ao_snapshot` é O(k) no número de níveis do snapshot, que é o custo
      mínimo de olhar o snapshot.

    O índice por preço (`_pendentes_por_preco`, `_trades_por_preco`) existe
    exatamente para isso. Sem ele, cada negócio varria TODAS as quedas
    pendentes e cada queda varria TODOS os negócios em buffer — custo
    proporcional à janela inteira, não ao preço, e portanto crescente com a
    LARGURA do book. Medido com negócios que não casam com nada, variando só
    o número de níveis pendurados:

        niveis pendurados |  varrendo a janela  |  com indice por preco
                       50 |      ~130.000 neg/s |          ~330.000 neg/s
                      200 |       ~41.000 neg/s |          ~330.000 neg/s
                      800 |        ~7.300 neg/s |          ~330.000 neg/s

    (ordens de grandeza de uma máquina só, não benchmark de referência — o que
    importa aqui é a FORMA da curva, não o valor absoluto.)

    A coluna da esquerda desaba porque o custo era do TAMANHO DA JANELA; a da
    direita é plana porque passou a ser do preço. Num pipeline realista (book
    de 20 níveis, tape casando, janela default de 300 ms) medem-se ~120.000
    eventos/s, contra uma barra de 10.000.
    """

    def __init__(
        self,
        symbol: str,
        livro: LivroMBO,
        config: ConfigInferenciaMBP | None = None,
    ) -> None:
        self.symbol = symbol
        self.livro = livro
        self.config = config if config is not None else ConfigInferenciaMBP()

        self._qty_por_nivel: dict[tuple[Side, int], int] = {}

        # Duas visões das MESMAS estruturas, e as duas são necessárias:
        # a deque global dá a ordem de EXPIRAÇÃO (FIFO por timestamp), o
        # índice por preço dá a busca de CASAMENTO sem varrer a janela.
        # Só o mesmo preço pode casar — o índice é por preço e não por
        # (lado, preço) porque um agressor `UNKNOWN` casa com os dois lados.
        self._trades: deque[_TradeBuffer] = deque()
        self._pendentes: deque[_QuedaPendente] = deque()
        self._trades_por_preco: dict[int, deque[_TradeBuffer]] = {}
        self._pendentes_por_preco: dict[int, deque[_QuedaPendente]] = {}

        self._relogio_ns = 0
        self._seq = 0

        # Heaps com remoção preguiçosa para melhor bid/ask do dado agregado.
        self._heap_bids: list[int] = []
        self._heap_asks: list[int] = []

    # ------------------------------------------------------------------
    # entradas
    # ------------------------------------------------------------------
    def ao_trade(self, trade: Trade) -> None:
        """Negócio impresso: primeiro paga quedas pendentes, o resto vira buffer."""
        if trade.symbol != self.symbol:
            return
        self._avancar_relogio(trade.timestamp_ns)

        buffer = _TradeBuffer(
            timestamp_ns=trade.timestamp_ns,
            price=trade.price,
            qty_restante=trade.qty,
            agressor=trade.side_agressor,
            trade_id=trade.trade_id,
        )
        self._conciliar_pendentes_com(buffer)
        if buffer.qty_restante > 0:
            self._trades.append(buffer)
            self._trades_por_preco.setdefault(buffer.price, deque()).append(buffer)

    def ao_snapshot(self, snapshot: BookSnapshot) -> None:
        """Book completo (caso do `market_book_get` do MT5): difere contra o estado."""
        if snapshot.symbol != self.symbol:
            return
        self._avancar_relogio(snapshot.timestamp_ns)

        vistos: set[tuple[Side, int]] = set()
        for nivel in snapshot.bids:
            vistos.add((Side.BUY, nivel.price))
        for nivel in snapshot.asks:
            vistos.add((Side.SELL, nivel.price))

        # Níveis que sumiram do snapshot foram a zero. Itera sobre uma lista
        # fixa para não mutar o dicionário durante a varredura, e em ordem
        # determinística (dict preserva ordem de inserção).
        for chave in [c for c in self._qty_por_nivel if c not in vistos]:
            side, price = chave
            self._observar_nivel(snapshot.timestamp_ns, side, price, 0)

        for nivel in snapshot.bids:
            self._observar_nivel(snapshot.timestamp_ns, Side.BUY, nivel.price, nivel.qty)
        for nivel in snapshot.asks:
            self._observar_nivel(snapshot.timestamp_ns, Side.SELL, nivel.price, nivel.qty)

    def ao_delta(self, delta: BookDelta) -> None:
        """Atualização incremental de um nível."""
        if delta.symbol != self.symbol:
            return
        self._avancar_relogio(delta.timestamp_ns)
        nova_qty = 0 if delta.action is BookAction.DELETE else delta.qty
        self._observar_nivel(delta.timestamp_ns, delta.side, delta.price, nova_qty)

    def drenar(self, timestamp_ns: int) -> None:
        """Força a resolução de tudo que já passou da janela de reconciliação.

        Necessário no fim de um replay ou quando o fluxo fica ocioso: sem um
        evento novo para empurrar o relógio, uma queda pendente ficaria presa
        sem virar cancelamento.
        """
        self._avancar_relogio(timestamp_ns)

    # ------------------------------------------------------------------
    # relógio e expiração
    # ------------------------------------------------------------------
    def _avancar_relogio(self, timestamp_ns: int) -> None:
        if timestamp_ns > self._relogio_ns:
            self._relogio_ns = timestamp_ns
        limite = self._relogio_ns - self.config.janela_reconciliacao_ns

        while self._trades and self._trades[0].timestamp_ns < limite:
            expirado = self._trades.popleft()
            # Zerar antes de podar o índice: é assim que a poda preguiçosa do
            # bucket sabe que este negócio morreu sem ter sido conciliado.
            expirado.qty_restante = 0
            self._podar_bucket(self._trades_por_preco, expirado.price)

        while self._pendentes and self._pendentes[0].timestamp_ns < limite:
            pendente = self._pendentes.popleft()
            self._resolver_como_cancelamento(pendente)  # zera `qty_restante`
            self._podar_bucket(self._pendentes_por_preco, pendente.price)

    @staticmethod
    def _podar_bucket(indice: dict[int, deque], price: int) -> None:
        """Descarta do início do bucket o que já não pode casar com nada.

        Poda preguiçosa e amortizada: cada item entra e sai uma vez só. O
        bucket vazio some do índice para que um pregão inteiro de preços
        distintos não vire vazamento de memória.
        """
        bucket = indice.get(price)
        if bucket is None:
            return
        while bucket and bucket[0].qty_restante <= 0:
            bucket.popleft()
        if not bucket:
            del indice[price]

    # ------------------------------------------------------------------
    # observação de nível
    # ------------------------------------------------------------------
    def _observar_nivel(self, timestamp_ns: int, side: Side, price: int, nova_qty: int) -> None:
        chave = (side, price)
        anterior = self._qty_por_nivel.get(chave, 0)
        if nova_qty == anterior:
            return

        if anterior == 0 and nova_qty > 0:
            self._registrar_preco(side, price)

        if nova_qty > anterior:
            self._qty_por_nivel[chave] = nova_qty
            self._inserir_sintetica(timestamp_ns, side, price, nova_qty - anterior, anterior)
            return

        # A distância do topo é medida ANTES de aplicar a queda: o que importa
        # é se o nível era negociável no instante em que a liquidez saiu. Se o
        # nível ERA o topo e zerou, medir depois o faria parecer afastado.
        distancia = self._distancia_do_topo(side, price)

        if nova_qty == 0:
            self._qty_por_nivel.pop(chave, None)
        else:
            self._qty_por_nivel[chave] = nova_qty

        queda = anterior - nova_qty
        pendente = _QuedaPendente(
            timestamp_ns=timestamp_ns,
            side=side,
            price=price,
            qty_restante=queda,
            qty_original=queda,
            distancia_do_topo=distancia,
        )
        self._conciliar_pendente_com_buffer(pendente)
        if pendente.qty_restante > 0:
            self._pendentes.append(pendente)
            self._pendentes_por_preco.setdefault(price, deque()).append(pendente)

    def _inserir_sintetica(
        self, timestamp_ns: int, side: Side, price: int, qty: int, qty_anterior: int
    ) -> None:
        self._seq += 1
        order_id = f"{self.config.prefixo_ordem_sintetica}-{self._seq}"
        self.livro.adicionar(
            order_id=order_id,
            side=side,
            price=price,
            qty=qty,
            timestamp_ns=timestamp_ns,
            broker="",
            fonte=FonteMicro.MBP_INFERIDO,
            confianca=self.config.confianca_insercao,
            evidencia={
                "observado": "aumento_de_qty_no_nivel",
                "qty_anterior": qty_anterior,
                "qty_nova": qty_anterior + qty,
                "inferido": "uma_ordem_nova_sintetica",
                "ressalva": "o aumento pode vir de N ordens; a decomposicao e desconhecida",
            },
        )

    # ------------------------------------------------------------------
    # reconciliação queda <-> negócio
    # ------------------------------------------------------------------
    @staticmethod
    def _lado_passivo(agressor: AgressorSide) -> Side | None:
        if agressor is AgressorSide.BUY:
            return Side.SELL
        if agressor is AgressorSide.SELL:
            return Side.BUY
        return None

    def _lado_casa(self, pendente: _QuedaPendente, buffer: _TradeBuffer) -> bool:
        """Decide só a perna do LADO da reconciliação. A do preço é estrutural.

        A igualdade de preço não é conferida aqui porque não pode falhar: os
        dois únicos chamadores percorrem o bucket de `_trades_por_preco` /
        `_pendentes_por_preco` indexado exatamente pelo preço que se está
        casando. Conferir de novo seria um ramo inalcançável — e ramo
        inalcançável é pior que ramo ausente, porque parece proteção. Quem
        garante o preço é o índice, e é o índice que os testes exercitam
        (`test_negocio_em_outro_preco_nao_explica_a_queda`).
        """
        lado = self._lado_passivo(buffer.agressor)
        # Agressor desconhecido casa com qualquer lado — o preço já é evidência
        # forte, e o volume só pode ser consumido uma vez. O preço de pagar por
        # essa folga é confiança menor, cobrada em `_executar`.
        return lado is None or lado is pendente.side

    def _conciliar_pendente_com_buffer(self, pendente: _QuedaPendente) -> None:
        """Queda chegou DEPOIS do negócio: paga com o que já está no buffer.

        Percorre só os negócios DO MESMO PREÇO, na ordem de chegada — que é a
        mesma ordem relativa da fila global, porque o bucket é alimentado por
        ela. Negócio de outro preço nunca poderia casar, então visitá-lo era
        trabalho puro.
        """
        for buffer in self._trades_por_preco.get(pendente.price, ()):
            if pendente.qty_restante <= 0:
                break
            if buffer.qty_restante <= 0 or not self._lado_casa(pendente, buffer):
                continue
            self._executar(pendente, buffer)
        self._podar_bucket(self._trades_por_preco, pendente.price)
        while self._trades and self._trades[0].qty_restante <= 0:
            self._trades.popleft()

    def _conciliar_pendentes_com(self, buffer: _TradeBuffer) -> None:
        """Negócio chegou DEPOIS da queda: paga as quedas pendentes."""
        for pendente in self._pendentes_por_preco.get(buffer.price, ()):
            if buffer.qty_restante <= 0:
                break
            if pendente.qty_restante <= 0 or not self._lado_casa(pendente, buffer):
                continue
            self._executar(pendente, buffer)
        self._podar_bucket(self._pendentes_por_preco, buffer.price)
        while self._pendentes and self._pendentes[0].qty_restante <= 0:
            self._pendentes.popleft()

    def _executar(self, pendente: _QuedaPendente, buffer: _TradeBuffer) -> None:
        qty = min(pendente.qty_restante, buffer.qty_restante)
        exato = qty == pendente.qty_original and qty == buffer.qty_restante
        confianca = (
            self.config.confianca_execucao_com_trade_exato
            if exato
            else self.config.confianca_execucao_parcial
        )

        # A reconciliação tem DUAS pernas: mesmo preço e mesmo lado passivo.
        # Com agressor `UNKNOWN` (leilão de abertura/fechamento, e o RLP que
        # anonimiza parte do volume de WDO/WIN na B3) a segunda perna não
        # aconteceu — `_lado_casa` deixa passar assim mesmo, o que é a decisão certa,
        # mas o resultado é uma hipótese mais fraca e não pode sair valendo o
        # mesmo que uma execução com o lado confirmado. Teto, não valor fixo:
        # assim a confiança do lado não confirmado nunca supera a do
        # confirmado, qualquer que seja a configuração.
        lado_confirmado = self._lado_passivo(buffer.agressor) is not None
        if not lado_confirmado:
            confianca = min(confianca, self.config.confianca_execucao_lado_nao_confirmado)

        atraso = abs(buffer.timestamp_ns - pendente.timestamp_ns)
        self.livro.executar(
            side=pendente.side,
            price=pendente.price,
            qty=qty,
            timestamp_ns=max(pendente.timestamp_ns, buffer.timestamp_ns),
            broker_agressor="",
            fonte=FonteMicro.MBP_INFERIDO,
            confianca=confianca,
            evidencia={
                "observado": "queda_de_qty_no_nivel_e_negocio_no_mesmo_preco",
                "queda_qty": pendente.qty_original,
                "trade_id": buffer.trade_id,
                "trade_qty_usada": qty,
                "agressor": buffer.agressor.value,
                "lado_passivo_confirmado": lado_confirmado,
                "atraso_ns": atraso,
                "janela_ns": self.config.janela_reconciliacao_ns,
                "inferido": "execucao",
                "casamento_exato": exato,
            },
        )
        pendente.qty_restante -= qty
        pendente.qty_executada += qty
        buffer.qty_restante -= qty

    def _resolver_como_cancelamento(self, pendente: _QuedaPendente) -> None:
        """Janela expirou sem negócio que explicasse (todo) o saldo da queda."""
        no_topo = pendente.distancia_do_topo <= self.config.profundidade_topo_ticks

        # A confiança ALTA do ramo "fora do topo" repousa numa premissa
        # verificável: naquele preço não havia como negociar. Quando parte
        # desta mesma queda casou com um negócio impresso NO PRÓPRIO PREÇO, a
        # premissa está falsificada pela evidência do próprio módulo — o nível
        # negociou. Emitir "fora do topo nao havia como negociar" com 0.90
        # nesse caso seria publicar uma justificativa que os dados desmentem.
        negociou = pendente.qty_executada > 0
        negociavel = no_topo or negociou
        confianca = (
            self.config.confianca_cancelamento_no_topo
            if negociavel
            else self.config.confianca_cancelamento_fora_topo
        )
        restante = pendente.qty_restante
        while restante > 0:
            ordem = self.livro.ultima_ordem_ativa(pendente.side, pendente.price)
            if ordem is None:
                break
            if ordem.qty_restante <= restante:
                restante -= ordem.qty_restante
                self.livro.cancelar(
                    ordem.order_id,
                    timestamp_ns=pendente.timestamp_ns,
                    fonte=FonteMicro.MBP_INFERIDO,
                    confianca=confianca,
                    evidencia=self._evidencia_cancelamento(pendente, negociavel, ordem.qty_restante),
                )
            else:
                # A queda é menor que a ordem sintética do fim da fila: é um
                # cancelamento PARCIAL, emitido como CANCEL (e não REPLACE)
                # porque a leitura de fluxo que interessa é "liquidez saiu".
                self.livro.modificar(
                    ordem.order_id,
                    nova_qty=ordem.qty_restante - restante,
                    timestamp_ns=pendente.timestamp_ns,
                    fonte=FonteMicro.MBP_INFERIDO,
                    confianca=confianca,
                    tipo_evento=TipoEventoOrdem.CANCEL,
                    evidencia=self._evidencia_cancelamento(pendente, negociavel, restante),
                )
                restante = 0
        pendente.qty_restante = 0

    def _evidencia_cancelamento(
        self, pendente: _QuedaPendente, negociavel: bool, qty: int
    ) -> dict[str, object]:
        negociou = pendente.qty_executada > 0
        return {
            "observado": "queda_de_qty_no_nivel_sem_negocio_no_preco",
            "queda_qty": pendente.qty_original,
            "qty_atribuida": qty,
            "qty_ja_atribuida_a_execucao": pendente.qty_executada,
            "janela_ns": self.config.janela_reconciliacao_ns,
            "distancia_do_topo_ticks": pendente.distancia_do_topo,
            "nivel_negociavel": negociavel,
            "negocio_observado_no_preco": negociou,
            "inferido": "cancelamento",
            "ressalva": (
                "parte desta queda casou com negocio no proprio preco: o nivel"
                " negociou, entao o saldo pode ser impressao ainda por chegar"
                if negociou
                else "no topo do livro a ausencia de negocio pode ser atraso de impressao"
                if negociavel
                else "fora do topo nao havia como negociar: cancelamento quase certo"
            ),
        }

    # ------------------------------------------------------------------
    # topo do livro sobre o dado agregado
    # ------------------------------------------------------------------
    def _registrar_preco(self, side: Side, price: int) -> None:
        if side is Side.BUY:
            heapq.heappush(self._heap_bids, -price)
        else:
            heapq.heappush(self._heap_asks, price)

    def melhor_bid(self) -> int | None:
        while self._heap_bids:
            price = -self._heap_bids[0]
            if self._qty_por_nivel.get((Side.BUY, price), 0) > 0:
                return price
            heapq.heappop(self._heap_bids)
        return None

    def melhor_ask(self) -> int | None:
        while self._heap_asks:
            price = self._heap_asks[0]
            if self._qty_por_nivel.get((Side.SELL, price), 0) > 0:
                return price
            heapq.heappop(self._heap_asks)
        return None

    def _distancia_do_topo(self, side: Side, price: int) -> int:
        topo = self.melhor_bid() if side is Side.BUY else self.melhor_ask()
        if topo is None:
            return 0
        return abs(topo - price)
