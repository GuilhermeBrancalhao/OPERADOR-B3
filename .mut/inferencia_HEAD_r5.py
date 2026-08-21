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

# Código do lado dentro da CHAVE do índice de reconciliação. São inteiros, e
# não o próprio `Side`, por medição: `Enum.__hash__` é um método escrito em
# Python (`hash(self._name_)`), e a chave é hasheada 3 vezes por negócio no
# caminho quente. Trocar o enum por inteiro no par foi o que devolveu o custo
# por evento ao patamar de antes do índice por nível — a chave hasheia em C.
# A tradução acontece uma vez só, por comparação de identidade (`is`), que não
# hasheia nada. Ver `_cod_lado`.
_COD_COMPRA = 0
_COD_VENDA = 1
_COD_DESCONHECIDO = 2  # agressor `UNKNOWN`: candidato dos dois lados


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

    # O lado do livro que este negócio pode ter consumido, derivado uma vez só
    # na entrada. `None` = agressor desconhecido, que casa com os dois lados.
    lado_passivo: Side | None = None

    # `(preço, código do lado passivo)` — a chave do bucket onde este negócio
    # mora. Guardada, não recalculada: é consultada na entrada, na poda e na
    # expiração.
    chave: tuple[int, int] = (0, _COD_DESCONHECIDO)

    # Posição na fila global de chegada. Serve para percorrer DOIS buckets
    # (o do lado e o dos desconhecidos) como se fossem um só, na ordem em que
    # os eventos realmente chegaram. Sem isto, partir o índice por lado
    # mudaria silenciosamente a ordem de casamento.
    ordem_chegada: int = 0


@dataclass(slots=True)
class _QuedaPendente:
    """Queda de quantidade esperando para saber se foi execução ou cancelamento."""

    timestamp_ns: int
    side: Side
    price: int
    qty_restante: int
    qty_original: int
    distancia_do_topo: int

    # `(preço, código do lado)`. Mesma codificação da chave do negócio, de
    # propósito: um negócio do lado passivo S mora na chave que a queda do
    # lado S procura.
    chave: tuple[int, int] = (0, _COD_DESCONHECIDO)

    ordem_chegada: int = 0

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

    Custos — QUAL EIXO DOMINA, e por que a tabela anterior media o errado.

    * `ao_trade` e `ao_delta` são O(1) AMORTIZADO. O casamento é indexado por
      NÍVEL — `(preço, lado)`, as DUAS pernas da reconciliação — e dentro de um
      nível o consumo é estritamente FIFO, então o que morre forma sempre um
      prefixo e cada item entra e sai do índice uma vez só.
    * `ao_snapshot` é O(k) no número de níveis do snapshot, que é o custo
      mínimo de olhar o snapshot.

    A versão anterior desta docstring publicava uma curva plana medida na
    LARGURA do book (quantos preços distintos estão pendurados) e concluía que
    o módulo sustentava ~330.000 neg/s. A tabela era verdadeira e o eixo era o
    errado: a largura é justamente o que um índice por preço já resolvia, e
    naquele cenário o laço de casamento nem chega a rodar (0 candidatos
    percorridos por negócio, medido). Uma alegação medida no eixo em que a
    correção funciona, apresentada como prova de velocidade, é pior que
    nenhuma alegação — desarma a revisão seguinte.

    O eixo que dói no WDO é o OPOSTO da largura. O WDO negocia rotineiramente
    em 2-3 preços com spread de 1 tick: tudo cai no mesmo bucket. O que enche
    esse bucket é a TAXA DO TAPE, porque ele guarda o que couber em
    `janela_reconciliacao_ns` — a 10.000 negócios/s são 3.000 itens vivos.
    Indexar só por preço deixava a perna do LADO para um teste dentro do laço,
    e um negócio que não podia casar com nada varria o bucket inteiro para
    descobrir isso. Custo por evento O(taxa), custo total O(n × taxa): o
    defeito quadrático.

    Medido com `bench_inferencia.py` (preço cravado, spread de 1 tick, bid
    caindo no topo; um passo = 1 leitura de book + 1 negócio). A grandeza é
    CANDIDATOS PERCORRIDOS POR PASSO, que é determinística — tempo de parede
    varia 4x entre execuções idênticas numa máquina compartilhada, e foi
    confiando nele que a medição anterior se convenceu:

        tape/s | indice por PRECO  | indice por NIVEL (`(preco, lado)`)
               | 50/50 | so o que  | 50/50 | so o que
               |       | nao casa  |       | nao casa
           500 |   149 |       298 |     1 |        0
         1.000 |   294 |       590 |     1 |        0
         2.000 |   573 |     1.156 |     1 |        0
         5.000 | 1.333 |     2.720 |     1 |        0
        10.000 | 2.337 |     4.876 |     1 |        0
        fator  | 15,7x |     16,4x |  1,0x |     1,0x

    A coluna da esquerda cresce LINEARMENTE com a taxa — é o custo quadrático.
    A da direita é plana porque a chave já respondeu as duas perguntas que o
    laço fazia. Em tempo de parede, no mesmo cenário a 10.000/s de tape: de
    1.532 para 45.154 passos/s numa máquina ociosa, e de 544 para 22.646 na
    mesma máquina sob carga. O valor absoluto varia com a máquina; a razão e o
    veredito contra a barra de 10.000 eventos/s, não.

    O eixo antigo continua plano depois da mudança — 0 candidatos percorridos
    por negócio de 50 a 3.000 níveis pendurados, o mesmo de antes — como tem
    de ser: corrigir o eixo que dói não podia estragar o outro.
    `tests/test_micro_inferencia.py` prende os dois eixos, e prende também o
    NÍVEL absoluto, não só a forma da curva: uma degradação que cresce com a
    duração do pregão em vez de com a taxa passa por qualquer teste que só
    compare duas taxas entre si (medido — foi assim que uma mutação de poda
    sobreviveu à primeira versão desta suíte).
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
        # índice por NÍVEL dá a busca de CASAMENTO sem varrer a janela.
        #
        # A chave é `(preço, lado)` — as DUAS pernas da reconciliação, não só
        # o preço. Indexar só por preço deixava a perna do lado para um teste
        # dentro do laço, e num book estreito (o regime do WDO) o laço varria
        # o bucket inteiro para descobrir que nada casava. Ver a seção "QUAL
        # EIXO DOMINA O CUSTO" na docstring da classe.
        #
        # Do lado do negócio, o "lado" da chave é o lado PASSIVO que ele pode
        # ter consumido; `None` é o bucket dos agressores desconhecidos, que
        # casam com os dois lados e por isso não podem morar em nenhum dos
        # dois.
        self._trades: deque[_TradeBuffer] = deque()
        self._pendentes: deque[_QuedaPendente] = deque()
        self._trades_por_nivel: dict[tuple[int, int], deque[_TradeBuffer]] = {}
        self._pendentes_por_nivel: dict[tuple[int, int], deque[_QuedaPendente]] = {}

        self._relogio_ns = 0
        self._seq = 0
        self._seq_chegada = 0

        # O livro reconstruído fica transitoriamente CRUZADO por construção
        # desta ponte: a queda de quantidade só vira `cancelar` quando a
        # janela de reconciliação expira, enquanto as inserções do lado oposto
        # entram na hora. Declarar a defasagem ao livro é o que impede o
        # contador de integridade dele de acusar corrupção de feed onde só há
        # atraso conhecido da ponte. Ver `tem_liquidez_nao_aplicada` e
        # `LivroMBO.registrar_liquidez_nao_aplicada`.
        livro.registrar_liquidez_nao_aplicada(self.tem_liquidez_nao_aplicada)

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

        self._seq_chegada += 1
        lado_passivo = self._lado_passivo(trade.side_agressor)
        buffer = _TradeBuffer(
            timestamp_ns=trade.timestamp_ns,
            price=trade.price,
            qty_restante=trade.qty,
            agressor=trade.side_agressor,
            trade_id=trade.trade_id,
            lado_passivo=lado_passivo,
            chave=(trade.price, self._cod_lado(lado_passivo)),
            ordem_chegada=self._seq_chegada,
        )
        self._conciliar_pendentes_com(buffer)
        if buffer.qty_restante > 0:
            self._trades.append(buffer)
            self._trades_por_nivel.setdefault(buffer.chave, deque()).append(buffer)

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
            self._podar_bucket(self._trades_por_nivel, expirado.chave)

        while self._pendentes and self._pendentes[0].timestamp_ns < limite:
            pendente = self._pendentes.popleft()
            self._resolver_como_cancelamento(pendente)  # zera `qty_restante`
            self._podar_bucket(self._pendentes_por_nivel, pendente.chave)

    @staticmethod
    def _cod_lado(side: Side | None) -> int:
        """Lado -> código inteiro da chave do índice. Só comparação de identidade."""
        if side is Side.BUY:
            return _COD_COMPRA
        if side is Side.SELL:
            return _COD_VENDA
        return _COD_DESCONHECIDO

    @staticmethod
    def _podar_bucket(indice: dict, chave: tuple) -> None:
        """Descarta do início do bucket o que já não pode casar com nada.

        Poda preguiçosa e amortizada: cada item entra e sai uma vez só, e o
        que morreu forma SEMPRE um prefixo — dentro de um nível o consumo é
        estritamente FIFO, porque todo casamento começa pela frente do bucket.
        É essa invariante que faz `popleft` na frente bastar; sem ela ficaria
        lixo no meio e a varredura voltaria.

        O bucket vazio some do índice para que um pregão inteiro de preços
        distintos não vire vazamento de memória.
        """
        bucket = indice.get(chave)
        if bucket is None:
            return
        while bucket and bucket[0].qty_restante <= 0:
            bucket.popleft()
        if not bucket:
            del indice[chave]

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
        self._seq_chegada += 1
        pendente = _QuedaPendente(
            timestamp_ns=timestamp_ns,
            side=side,
            price=price,
            qty_restante=queda,
            qty_original=queda,
            distancia_do_topo=distancia,
            chave=(price, self._cod_lado(side)),
            ordem_chegada=self._seq_chegada,
        )
        self._conciliar_pendente_com_buffer(pendente)
        if pendente.qty_restante > 0:
            self._pendentes.append(pendente)
            self._pendentes_por_nivel.setdefault(pendente.chave, deque()).append(pendente)

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

    @staticmethod
    def _em_ordem_de_chegada(primeiro, segundo):
        """Percorre DOIS buckets como se fossem um só, na ordem de chegada.

        Existe por causa do agressor desconhecido, que é o único item que não
        pode morar num bucket de lado: ele casa com os dois. Partir o índice
        por lado sem isto mudaria a ordem de casamento em silêncio — um
        negócio recente do lado certo passaria à frente de um desconhecido
        mais antigo. A ordem sai de `ordem_chegada` (contador monotônico), não
        do timestamp, porque dois eventos do mesmo instante ainda têm uma
        ordem de chegada bem definida.

        Nenhum dos dois buckets é mutado durante a iteração: quem casa só
        altera `qty_restante` dos itens, e a poda roda depois do laço.

        Não é gerador: com um dos buckets vazio — que é o caso esmagador, já
        que agressor desconhecido é exceção — devolve o outro bucket direto e
        não paga criação de gerador nenhuma no caminho quente.
        """
        if not segundo:
            return primeiro
        if not primeiro:
            return segundo
        return InferidorMBP._intercalar(primeiro, segundo)

    @staticmethod
    def _intercalar(primeiro, segundo):
        """Merge por `ordem_chegada` de dois buckets ambos não vazios."""
        it_a, it_b = iter(primeiro), iter(segundo)
        a = next(it_a, None)
        b = next(it_b, None)
        while a is not None and b is not None:
            if a.ordem_chegada <= b.ordem_chegada:
                yield a
                a = next(it_a, None)
            else:
                yield b
                b = next(it_b, None)
        while a is not None:
            yield a
            a = next(it_a, None)
        while b is not None:
            yield b
            b = next(it_b, None)

    def _conciliar_pendente_com_buffer(self, pendente: _QuedaPendente) -> None:
        """Queda chegou DEPOIS do negócio: paga com o que já está no buffer.

        Percorre só os negócios que podem casar com esta queda — mesmo preço E
        lado passivo compatível — na ordem de chegada. Os dois buckets são o do
        lado desta queda e o dos agressores desconhecidos; negócio de outro
        preço ou do outro lado não é visitado, porque a chave do índice já o
        excluiu. Não existe teste de lado dentro do laço: seria um ramo
        inalcançável, e ramo inalcançável é pior que ramo ausente porque parece
        proteção. Quem garante as duas pernas é o índice, e é o índice que os
        testes exercitam (`test_negocio_em_outro_preco_nao_explica_a_queda`,
        `test_agressao_de_compra_sozinha_nao_explica_queda_no_bid`).
        """
        chave_do_lado = pendente.chave
        chave_desconhecidos = (pendente.price, _COD_DESCONHECIDO)
        indice = self._trades_por_nivel
        for buffer in self._em_ordem_de_chegada(
            indice.get(chave_do_lado, ()), indice.get(chave_desconhecidos, ())
        ):
            if pendente.qty_restante <= 0:
                break
            if buffer.qty_restante <= 0:
                continue
            self._executar(pendente, buffer)
        self._podar_bucket(indice, chave_do_lado)
        self._podar_bucket(indice, chave_desconhecidos)
        while self._trades and self._trades[0].qty_restante <= 0:
            self._trades.popleft()

    def _conciliar_pendentes_com(self, buffer: _TradeBuffer) -> None:
        """Negócio chegou DEPOIS da queda: paga as quedas pendentes.

        Com o lado do agressor conhecido, um bucket só pode explicar a queda e
        o índice vai direto nele. Com agressor desconhecido (leilão, RLP) a
        perna do lado não aconteceu: os dois buckets são candidatos e são
        percorridos na ordem de chegada. O preço de pagar por essa folga é
        confiança menor, cobrada em `_executar`.
        """
        indice = self._pendentes_por_nivel
        if buffer.lado_passivo is not None:
            # A chave do negócio e a da queda que ele pode explicar são a
            # MESMA tupla: mesmo preço, mesmo código de lado.
            chaves = (buffer.chave,)
            candidatos = indice.get(buffer.chave, ())
        else:
            chaves = ((buffer.price, _COD_COMPRA), (buffer.price, _COD_VENDA))
            candidatos = self._em_ordem_de_chegada(
                indice.get(chaves[0], ()), indice.get(chaves[1], ())
            )
        for pendente in candidatos:
            if buffer.qty_restante <= 0:
                break
            if pendente.qty_restante <= 0:
                continue
            self._executar(pendente, buffer)
        for chave in chaves:
            self._podar_bucket(indice, chave)
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
        # aconteceu — o índice deixa passar assim mesmo (o bucket dos
        # desconhecidos é candidato dos dois lados), o que é a decisão certa,
        # mas o resultado é uma hipótese mais fraca e não pode sair valendo o
        # mesmo que uma execução com o lado confirmado. Teto, não valor fixo:
        # assim a confiança do lado não confirmado nunca supera a do
        # confirmado, qualquer que seja a configuração.
        lado_confirmado = buffer.lado_passivo is not None
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
    # defasagem da ponte (integridade do livro reconstruído)
    # ------------------------------------------------------------------
    def tem_liquidez_nao_aplicada(self, side: Side, price: int) -> bool:
        """O livro ainda exibe liquidez que o feed já tirou deste nível?

        É a pergunta que separa CRUZAMENTO TRANSITÓRIO DE RECONCILIAÇÃO de
        cruzamento de verdade. Em modo MBP o livro fica cruzado por construção
        desta ponte: a queda de quantidade vira `livro.cancelar` só quando a
        janela de reconciliação expira — porque até lá ela ainda pode ser
        explicada por um negócio cuja impressão não chegou — enquanto as
        inserções do lado oposto entram na hora. Nesse intervalo o livro
        reconstruído exibe um nível que o feed já esvaziou, e é ele que cruza.

        A resposta NÃO sai de um contador paralelo, que poderia dessincronizar
        e mentir. Sai da comparação direta entre as duas verdades que este
        módulo já mantém: quanto o feed diz que existe no nível
        (`_qty_por_nivel`, atualizado no instante da leitura) e quanto o livro
        reconstruído ainda exibe (`livro.qty_total`, atualizado só quando o
        veredito sai). A diferença É a defasagem, por definição — não há como
        ela discordar do estado real.

        O(1): dois `dict.get`.
        """
        excedente = self.livro.qty_total(side, price) - self._qty_por_nivel.get((side, price), 0)
        return excedente > 0

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
