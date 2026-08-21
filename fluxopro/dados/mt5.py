"""Adaptador de dados ao vivo via terminal MetaTrader5.

Import do pacote `MetaTrader5` é preguiçoso e protegido: o módulo Python
deste arquivo importa e é testável em qualquer máquina (Linux/CI/sem MT5
instalado); o erro só aparece — com mensagem clara — quando `iniciar()` é
chamado de fato. Para teste, injete um módulo falso via `mt5_module=`.

Fronteira de concorrência: o pacote `MetaTrader5` não tem streaming nativo,
só polling (ver `pesquisa/fontes_de_dados.md`). Uma *thread de borda*
(`_thread_borda`) faz esse polling contra o terminal MT5 e só enfileira
objetos já traduzidos para os tipos de `fluxopro.core.eventos` — nunca
toca o barramento. A thread principal (dentro de `iniciar()`, que bloqueia
até `parar()`) drena a fila e publica no `Barramento`, respeitando a regra
do núcleo de que `publicar()` só é chamado de um único lugar serializado.


ESTRATÉGIA DE PAGINAÇÃO DE TICKS (por que não se perde nem duplica)
------------------------------------------------------------------
`copy_ticks_from(symbol, date_from, count, flags)` devolve os `count`
PRIMEIROS ticks a partir de `date_from`, em ordem crescente — e `date_from`
tem granularidade de **segundo**. Não existe API no pacote `MetaTrader5`
que aceite um cursor em milissegundos: `copy_ticks_range(de, ate)` também
recebe segundos. Logo, o cursor de retomada é sempre o *segundo* do último
tick visto, e a janela pedida SEMPRE re-inclui ticks já entregues.

Daí decorrem as três peças desta implementação:

1. **Paginação por escalada de `count`, não por avanço do `date_from`.**
   Enquanto o cursor estiver dentro do segundo `S`, avançar `date_from`
   pularia ticks; o que precisa crescer é a janela. Se a chamada devolveu
   EXATAMENTE `count` ticks, a janela saturou — provavelmente há mais — e
   a chamada é refeita com `count` dobrado, até o lote voltar incompleto
   (prova de que a janela cobriu tudo) ou até o teto
   `teto_ticks_por_chamada`. É o defeito original: `count` fixo em 1.000
   com `date_from` truncado ao segundo fazia todo poll pedir "os 1.000
   primeiros ticks do segundo S" e receber sempre os mesmos 1.000 — o
   cursor nunca saía de S e o resto do tape era perdido para sempre.

   Por que não `copy_ticks_range`: ele exige um limite superior. O único
   limite superior disponível é o relógio LOCAL — que é justamente a outra
   fonte de tempo que este módulo deixou de usar (ver abaixo); com o
   servidor adiantado, `ate` cortaria ticks legítimos "do futuro". Além
   disso `copy_ticks_range` não tem `count`, então não há como OBSERVAR
   saturação: ele devolve tudo ou estoura memória, sem ponto de auditoria.
   A escalada de `count` torna a saturação um fato mensurável e emitível.

2. **Deduplicação por `(time_msc, ordem_no_ms)`, não por `time_msc`.**
   Vários negócios cabem no mesmo milissegundo — em pico de WDO isso é a
   regra, não a exceção. O gate antigo (`if time_msc <= ultimo: continue`)
   descartava todos os irmãos do último milissegundo entregue. O cursor é
   o par `(último time_msc entregue, quantos ticks daquele ms já saíram)`.
   Como `date_from` é o *segundo* de `time_msc`, o lote sempre começa
   ANTES do primeiro tick daquele milissegundo, então contar a ordem
   dentro do lote dá a mesma ordem absoluta em toda chamada — é isso que
   torna o par um identificador estável. `trade_id` carrega essa ordem
   (`MT5-<time_msc>-<ordem>-<flags>`) para ser único de verdade.

3. **Cursor congelado é FALHA, nunca silêncio.** Se o lote saturou no teto
   E o cursor não avançou, não há mais como progredir dentro daquele
   segundo. Em vez de girar em falso (o comportamento antigo), emite-se
   `FalhaCaptura(GAP_TICKS)` dizendo quantos ticks a janela comportava, e
   o cursor é forçado para o segundo seguinte. Perde-se dado — mas ALTO, e
   o replay saberá que ali há um buraco. Perder dado em silêncio é o pior
   comportamento possível para um sistema cuja única fonte de histórico é
   o que ele mesmo grava.


UM RELÓGIO SÓ NA BORDA
----------------------
Todo evento que sai deste adaptador é carimbado com o relógio do SERVIDOR
MT5 — o mesmo que carimba `time_msc` nos ticks. Antes, `Trade` usava
`time_msc` (servidor) e `BookSnapshot`/`FalhaCaptura` usavam
`time.time_ns()` (local). Servidores MetaQuotes rodam tipicamente em
GMT+2/+3, e a janela de reconciliação do `InferidorMBP` é de 300 ms: com
os dois relógios, 100% das execuções viravam cancelamentos, e uma gravação
real ficava irreproduzível (o leitor ordena por timestamp, então saíam
todos os books primeiro e todos os trades depois).

O servidor é o relógio certo porque é o tempo em que o negócio aconteceu
na bolsa, é o único dos dois que o replay reproduz, e é a base da janela de
reconciliação. Quem tem tempo próprio (o tick) usa o seu; quem não tem
(`market_book_get` devolve só níveis, `FalhaCaptura` é sintética) recebe um
tempo **derivado** — relógio local deslocado pelo offset medido contra o
último `time_msc` observado, com piso monotônico. `_RelogioServidor`
concentra isso num lugar só, e `derivado` é o nome do fato: não é medição,
é extrapolação declarada.

O offset é estimado pelo **MÁXIMO** das amostras, não pela última. Um tick
só pode ser observado DEPOIS de ter acontecido, então toda amostra
`time_msc - relógio_local` SUBESTIMA o offset verdadeiro pela idade do
tick. Com "a última amostra vence", um mercado parado re-observa o mesmo
tick velho a cada poll e o relógio derivado fica preso na hora do último
negócio — o erro cresce sem limite (medido: -60s e subindo 50ms por poll,
com o mercado parado há 1 minuto), e todo `BookSnapshot` sai carimbado no
passado. Com o máximo, a amostra velha é descartada, o erro fica CONSTANTE
e limitado pela idade do tick mais fresco já visto — milissegundos em
pregão ativo — e só melhora conforme o tape acorda. Não existe fonte mais
fresca no pacote `MetaTrader5`: `symbol_info_tick` devolve o mesmo último
tick, e `terminal_info` não expõe hora de servidor.


PARTIDA A FRIO — POR QUE O CURSOR É SEMEADO
-------------------------------------------
`copy_ticks_from(symbol, 0, ...)` não devolve "nada": devolve os `count`
PRIMEIROS ticks do histórico disponível, de anos atrás. Um cursor zerado na
partida faria o adaptador publicar histórico antigo como se fosse tape ao
vivo, saturar a paginação até o teto e emitir `GAP_TICKS` a cada poll até
arrastar o cursor até hoje. Por isso o primeiro poll semeia o cursor com o
`time_msc` de `symbol_info_tick` (o último tick conhecido do símbolo), com
`ordem_no_ms=0` para que os irmãos daquele milissegundo entrem. Sem
`symbol_info_tick` (módulo MT5 antigo, símbolo sem tick), avisa e degrada
para o começo do histórico — ALTO, nunca em silêncio.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from types import ModuleType
from typing import NamedTuple, Optional

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    PriceGrid,
    Side,
    Trade,
)
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha

_logger = logging.getLogger("fluxopro.dados.mt5")

# Limite de "atraso aceitável" entre um poll e o outro antes de considerar
# que pode ter havido perda de tick/book (a máquina travou, o terminal MT5
# travou, rede caiu etc.). Empírico, não documentado pela MetaQuotes.
# ATENÇÃO: mede intervalo de POLL, não idade do DADO — um feed congelado com
# polling saudável não aparece aqui; quem detecta isso é a saturação de
# `_puxar_ticks`.
_LIMIAR_GAP_S = 2.0

# Quantos ticks pedir na primeira chamada de cada poll. Como `date_from` tem
# granularidade de segundo, a janela precisa caber o SEGUNDO inteiro, não só
# o intervalo de poll: 10.000 é o pico da barra do projeto (10 mil eventos/s).
_TICKS_POR_CHAMADA_PADRAO = 10_000

# Teto da escalada. 500.000 ticks num único segundo é ~50x o pico da barra;
# se nem isso bastar, o adaptador desiste ALTO (FalhaCaptura) em vez de
# congelar em silêncio.
_TETO_TICKS_POR_CHAMADA = 500_000

EventoBruto = Trade | BookSnapshot | BookDelta | FalhaCaptura


class _CursorTick(NamedTuple):
    """Posição exata de retomada no tape.

    `ordem_no_ms` é quantos ticks com exatamente `time_msc` já foram
    entregues — sem ele, todo negócio que dividisse o milissegundo com o
    último entregue seria descartado como "já processado".
    """

    time_msc: int = 0
    ordem_no_ms: int = 0

    @property
    def segundo(self) -> int:
        """O `date_from` a pedir: o segundo do último tick entregue.

        Nunca o segundo SEGUINTE — o resto daquele segundo ainda pode não
        ter sido entregue, e a dedup por `(time_msc, ordem)` cuida da
        sobreposição.
        """
        return self.time_msc // 1000 if self.time_msc else 0


class _RelogioServidor:
    """Fonte de tempo ÚNICA da borda MT5 (ver "UM RELÓGIO SÓ" no topo).

    `observar` mede o offset entre o relógio do servidor (`time_msc` de um
    tick) e o relógio local; `agora_ns` devolve o instante corrente já no
    referencial do servidor, para os eventos que não trazem tempo próprio.
    O piso `_ultimo_ns` garante que a sequência que sai do adaptador seja
    monotônica mesmo quando o offset é remedido entre dois eventos.

    O estimador é o MÁXIMO das amostras, não a última — ver "UM RELÓGIO SÓ
    NA BORDA" no topo do módulo. Toda amostra subestima o offset pela idade
    do tick; a maior amostra é a do tick mais fresco já visto.
    """

    __slots__ = ("_offset_ns", "_sincronizado", "_ultimo_ns")

    def __init__(self) -> None:
        self._offset_ns = 0
        self._sincronizado = False
        self._ultimo_ns = 0

    @property
    def sincronizado(self) -> bool:
        return self._sincronizado

    @property
    def offset_ns(self) -> int:
        """Servidor menos local, em ns. 0 enquanto nenhum tick foi visto."""
        return self._offset_ns

    def observar(self, servidor_ns: int) -> None:
        estimativa = servidor_ns - time.time_ns()
        if not self._sincronizado or estimativa > self._offset_ns:
            # amostra melhor (tick mais fresco). Amostra menor é tick VELHO
            # re-observado: aceitá-la prenderia o relógio derivado na hora
            # do último negócio.
            self._offset_ns = estimativa
        self._sincronizado = True
        if servidor_ns > self._ultimo_ns:
            self._ultimo_ns = servidor_ns

    def agora_ns(self) -> int:
        derivado = time.time_ns() + self._offset_ns
        if derivado <= self._ultimo_ns:
            # piso monotônico: nunca voltar no tempo nem empatar com o
            # evento anterior, senão a ordem de entrega deixa de ser
            # reconstruível no replay (que ordena por timestamp).
            derivado = self._ultimo_ns + 1
        self._ultimo_ns = derivado
        return derivado


def _importar_mt5() -> ModuleType:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as erro:
        raise RuntimeError(
            "pacote 'MetaTrader5' nao esta instalado (pip install MetaTrader5). "
            "So funciona em Windows com o terminal MT5 instalado e logado. "
            "Use AdaptadorMT5(mt5_module=<mock>) para testar sem a dependencia real."
        ) from erro
    return mt5


def _normalizar_lote(ticks):
    """numpy devolve um registro estruturado 0-d (escalar) quando o array
    tem exatamente 1 tick — normaliza para sequência antes de iterar, senão
    `for tick in ticks` percorre os CAMPOS do registro em vez do registro.
    """
    if ticks is None:
        return None
    if getattr(ticks, "ndim", 1) == 0:
        return [ticks]
    return ticks


def _primeiro_do_ms(ticks, time_msc: int) -> int:
    """Índice do primeiro tick do lote com `time_msc >= alvo` (lower bound).

    Busca binária em Python puro — `ticks` é um array estruturado do numpy
    em produção, mas este módulo não importa numpy (não é dependência
    declarada do projeto) e precisa aceitar também a lista que
    `_normalizar_lote` devolve no caso de 1 tick.

    Pressupõe o lote em ordem crescente de `time_msc`, que é o contrato de
    `copy_ticks_from`. Se o contrato for quebrado o laço de `_puxar_ticks`
    ainda tem o gate `time_msc < cursor.time_msc` como rede.
    """
    if time_msc <= 0:
        return 0
    baixo, alto = 0, len(ticks)
    while baixo < alto:
        meio = (baixo + alto) // 2
        if int(ticks[meio]["time_msc"]) < time_msc:
            baixo = meio + 1
        else:
            alto = meio
    return baixo


class AdaptadorMT5(AdaptadorDados):
    def __init__(
        self,
        barramento: Barramento,
        symbol: str,
        price_grid: PriceGrid,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        intervalo_poll_s: float = 0.05,
        profundidade_maxima: int = 10,
        ticks_por_chamada: int = _TICKS_POR_CHAMADA_PADRAO,
        teto_ticks_por_chamada: int = _TETO_TICKS_POR_CHAMADA,
        mt5_module: ModuleType | None = None,
    ) -> None:
        super().__init__(barramento)
        self._symbol = symbol
        self._grid = price_grid
        self._login = login
        self._password = password
        self._server = server
        self._intervalo_poll_s = intervalo_poll_s
        self._profundidade_maxima = profundidade_maxima
        self._ticks_por_chamada = max(1, ticks_por_chamada)
        self._teto_ticks_por_chamada = max(self._ticks_por_chamada, teto_ticks_por_chamada)
        self._mt5_injetado = mt5_module

        self._fila: "queue.Queue[EventoBruto]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._parar_evt = threading.Event()
        self._book_habilitado = False
        self._mt5: ModuleType | None = None
        self._relogio = _RelogioServidor()
        self._avisou_relogio_local = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        mt5 = self._mt5_injetado if self._mt5_injetado is not None else _importar_mt5()
        self._mt5 = mt5

        kwargs = {}
        if self._login is not None:
            kwargs["login"] = self._login
        if self._password is not None:
            kwargs["password"] = self._password
        if self._server is not None:
            kwargs["server"] = self._server
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"mt5.initialize() falhou: {mt5.last_error()}")

        if not mt5.symbol_select(self._symbol, True):
            mt5.shutdown()
            raise RuntimeError(
                f"mt5.symbol_select({self._symbol!r}) falhou: {mt5.last_error()}"
            )

        self._book_habilitado = bool(mt5.market_book_add(self._symbol))
        if not self._book_habilitado:
            _logger.warning(
                "market_book_add(%s) falhou (%s) — corretora pode nao expor DOM "
                "para este simbolo; seguindo so com trades.",
                self._symbol,
                mt5.last_error(),
            )

        self._parar_evt.clear()
        self._thread = threading.Thread(
            target=self._loop_borda, name="mt5-borda", daemon=True
        )
        self._thread.start()

        self._loop_consumo()

    def parar(self) -> None:
        self._parar_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._mt5 is not None:
            if self._book_habilitado:
                self._mt5.market_book_release(self._symbol)
            self._mt5.shutdown()

    # ------------------------------------------------------------------
    # Tempo — um relógio só para tudo que sai daqui
    # ------------------------------------------------------------------

    def _agora_ns(self) -> int:
        """Instante corrente no referencial do SERVIDOR MT5, DERIVADO.

        Usado só por evento sem tempo próprio (book snapshot, falha de
        captura). Enquanto nenhum tick foi observado o offset é
        desconhecido e isto degrada para o relógio local — avisando uma
        vez, porque nessa janela os eventos não são comparáveis com trades
        de um servidor em outro fuso.
        """
        if not self._relogio.sincronizado and not self._avisou_relogio_local:
            self._avisou_relogio_local = True
            _logger.warning(
                "relogio do servidor MT5 ainda nao observado (nenhum tick e "
                "symbol_info_tick indisponivel) — carimbando eventos derivados "
                "com o relogio LOCAL. Se o servidor estiver em outro fuso, os "
                "eventos desta janela nao sao comparaveis com os trades."
            )
        return self._relogio.agora_ns()

    def _sincronizar_relogio(self, mt5: ModuleType) -> None:
        """Semeia o offset sem depender de negócio nenhum.

        Em mercado parado (ou antes do primeiro tick do dia) o único jeito
        de saber a hora do servidor é `symbol_info_tick`, que devolve o
        último tick conhecido do símbolo com seu `time_msc`. `getattr` em
        vez de chamada direta porque o adaptador tem de continuar
        funcionando contra módulos MT5 mais antigos.
        """
        if self._relogio.sincronizado:
            return
        obter = getattr(mt5, "symbol_info_tick", None)
        if obter is None:
            return
        tick = obter(self._symbol)
        if tick is None:
            return
        time_msc = int(getattr(tick, "time_msc", 0) or 0)
        if time_msc > 0:
            self._relogio.observar(time_msc * 1_000_000)

    def _cursor_inicial(self, mt5: ModuleType) -> _CursorTick:
        """Onde começar a ler o tape na partida (ver "PARTIDA A FRIO").

        `ordem_no_ms=0` de propósito: o último tick conhecido e todos os
        irmãos do milissegundo dele entram — na partida nada foi entregue
        ainda, então entregá-los é estado corrente do tape, não duplicata.
        """
        obter = getattr(mt5, "symbol_info_tick", None)
        tick = obter(self._symbol) if obter is not None else None
        time_msc = int(getattr(tick, "time_msc", 0) or 0) if tick is not None else 0
        if time_msc > 0:
            return _CursorTick(time_msc, 0)
        _logger.warning(
            "symbol_info_tick(%s) nao deu um time_msc para semear o cursor — "
            "comecando do inicio do historico disponivel. O primeiro poll pode "
            "trazer ticks antigos e saturar a paginacao ate o cursor alcancar o "
            "presente.",
            self._symbol,
        )
        return _CursorTick()

    def _falha(self, tipo: TipoFalha, detalhe: str) -> FalhaCaptura:
        return FalhaCaptura(
            timestamp_ns=self._agora_ns(),
            symbol=self._symbol,
            tipo=tipo,
            detalhe=detalhe,
        )

    # ------------------------------------------------------------------
    # Thread de borda: só MT5 + fila. Nunca toca o barramento.
    # ------------------------------------------------------------------

    def _loop_borda(self) -> None:
        mt5 = self._mt5
        assert mt5 is not None
        # partida a frio: NUNCA do epoch (ver "PARTIDA A FRIO" no topo).
        cursor = self._cursor_inicial(mt5)
        snapshot_anterior: BookSnapshot | None = None
        ultimo_poll_ok = time.monotonic()
        conectado = True

        while not self._parar_evt.is_set():
            agora = time.monotonic()
            try:
                self._sincronizar_relogio(mt5)

                novos_ticks, cursor, falhas = self._puxar_ticks(mt5, cursor)
                for trade in novos_ticks:
                    self._fila.put(trade)
                for falha in falhas:
                    self._fila.put(falha)

                if self._book_habilitado:
                    snapshot = self._puxar_book(mt5)
                    if snapshot is not None:
                        self._fila.put(snapshot)
                        if snapshot_anterior is not None:
                            for delta in derivar_deltas(snapshot_anterior, snapshot):
                                self._fila.put(delta)
                        snapshot_anterior = snapshot

                if not conectado:
                    self._fila.put(
                        self._falha(TipoFalha.RECONEXAO, "polling voltou a responder")
                    )
                    conectado = True

                gap_s = agora - ultimo_poll_ok
                if gap_s > _LIMIAR_GAP_S:
                    self._fila.put(
                        self._falha(
                            TipoFalha.GAP_TICKS,
                            f"intervalo entre polls de {gap_s:.2f}s excedeu o "
                            f"limiar de {_LIMIAR_GAP_S:.2f}s — ticks/book podem "
                            "ter sido perdidos nessa janela",
                        )
                    )
                ultimo_poll_ok = agora
            except Exception as erro:  # defesa: nunca deixar a thread morrer muda
                conectado = False
                self._fila.put(
                    self._falha(TipoFalha.ERRO_FONTE, f"{type(erro).__name__}: {erro}")
                )
                _logger.exception("erro no polling do MT5")

            time.sleep(self._intervalo_poll_s)

    def _copiar_ticks_paginado(self, mt5: ModuleType, de_s: int):
        """Puxa o segundo `de_s` inteiro, escalando `count` enquanto saturar.

        Devolve `(ticks, saturado, count_pedido)`. `saturado=True` significa
        "o lote voltou EXATAMENTE cheio no teto" — isto é, a janela não
        provou ter coberto tudo e pode haver tick além dela.
        """
        count = self._ticks_por_chamada
        while True:
            ticks = _normalizar_lote(
                mt5.copy_ticks_from(self._symbol, de_s, count, mt5.COPY_TICKS_ALL)
            )
            if ticks is None:
                return None, False, count
            if len(ticks) < count:
                # lote incompleto é a PROVA de que a janela cobriu o que
                # existe a partir de `de_s` — só aqui se pode seguir em frente.
                return ticks, False, count
            if count >= self._teto_ticks_por_chamada:
                return ticks, True, count
            count = min(count * 2, self._teto_ticks_por_chamada)

    def _puxar_ticks(
        self, mt5: ModuleType, cursor: _CursorTick
    ) -> tuple[list[Trade], _CursorTick, list[FalhaCaptura]]:
        de_s = cursor.segundo
        ticks, saturado, count_pedido = self._copiar_ticks_paginado(mt5, de_s)
        falhas: list[FalhaCaptura] = []
        if ticks is None or len(ticks) == 0:
            return [], cursor, falhas

        trades: list[Trade] = []
        novo = cursor
        vistos_no_ms: dict[int, int] = {}

        # O lote SEMPRE recomeça no início do segundo do cursor, então a cada
        # poll ele re-inclui tudo que já saiu daquele segundo. Varrer isso em
        # Python custa O(ticks do segundo) por poll — a 20 Hz e 10 mil
        # ticks/s vira O(n²) sobre o segundo: 36% de um núcleo só nisto, e
        # crescendo com o quadrado do volume (medido em `bench_mt5.py`; com
        # o pulo abaixo cai para 12% e volta a ser linear no tick).
        # `_primeiro_do_ms` pula direto para o milissegundo do cursor por
        # busca binária; o resto do laço fica proporcional só ao que é novo.
        # A contagem de `ordem` continua ABSOLUTA porque todos os ticks de um
        # mesmo `time_msc` são contíguos e começam exatamente nesse índice.
        inicio = _primeiro_do_ms(ticks, cursor.time_msc)

        for pos in range(inicio, len(ticks)):
            tick = ticks[pos]
            time_msc = int(tick["time_msc"])
            ordem = vistos_no_ms.get(time_msc, 0)
            vistos_no_ms[time_msc] = ordem + 1

            # dedup pelo PAR: o lote sempre re-inclui o começo do segundo,
            # e vários ticks dividem o mesmo milissegundo.
            if time_msc < cursor.time_msc:
                # inalcançável com lote ordenado (a busca binária já pulou);
                # rede de segurança para um lote fora de ordem.
                continue
            if time_msc == cursor.time_msc and ordem < cursor.ordem_no_ms:
                continue

            # o cursor avança por TODO tick aceito, inclusive o que não vira
            # Trade (preço fora da grade, preço zerado) — senão um tick
            # inválido na ponta do lote prenderia o cursor.
            if time_msc > novo.time_msc:
                novo = _CursorTick(time_msc, ordem + 1)
            elif time_msc == novo.time_msc and ordem + 1 > novo.ordem_no_ms:
                novo = _CursorTick(time_msc, ordem + 1)

            preco_bruto = float(tick["last"]) if tick["last"] else float(tick["bid"])
            if preco_bruto <= 0:
                continue
            try:
                preco_ticks = self._grid.to_ticks(preco_bruto)
            except ValueError:
                continue

            agressor = self._inferir_agressor(mt5, tick)
            trades.append(
                Trade(
                    timestamp_ns=time_msc * 1_000_000,
                    symbol=self._symbol,
                    price=preco_ticks,
                    qty=int(tick["volume"]) if tick["volume"] else int(tick["volume_real"]),
                    side_agressor=agressor,
                    # a ordem no ms entra no id: sem ela, negócios do mesmo
                    # milissegundo com as mesmas flags teriam id igual.
                    trade_id=f"MT5-{time_msc}-{ordem}-{int(tick['flags'])}",
                )
            )

        # o tempo do servidor vem do tick mais novo do lote (crescente).
        self._relogio.observar(int(ticks[len(ticks) - 1]["time_msc"]) * 1_000_000)

        if saturado:
            congelou = novo == cursor
            falhas.append(
                self._falha(
                    TipoFalha.GAP_TICKS,
                    (
                        f"copy_ticks_from devolveu o lote cheio ({count_pedido} ticks) "
                        f"no teto de paginacao a partir do segundo {de_s}: "
                        + (
                            "o cursor NAO tem como avancar (mais de "
                            f"{count_pedido} ticks ja entregues nesse segundo); "
                            "pulando para o segundo seguinte — ha um buraco de "
                            "ticks aqui"
                            if congelou
                            else "pode haver ticks alem da janela nesse segundo"
                        )
                    ),
                )
            )
            if congelou:
                # liveness acima de completude: girar em falso para sempre
                # (o defeito original) é pior que perder um pedaço avisando.
                novo = _CursorTick((de_s + 1) * 1000, 0)

        return trades, novo, falhas

    def _inferir_agressor(self, mt5: ModuleType, tick) -> AgressorSide:
        flags = int(tick["flags"]) if "flags" in tick.dtype.names else 0
        flag_buy = getattr(mt5, "TICK_FLAG_BUY", 1 << 5)
        flag_sell = getattr(mt5, "TICK_FLAG_SELL", 1 << 6)
        tem_buy = bool(flags & flag_buy)
        tem_sell = bool(flags & flag_sell)
        if tem_buy and not tem_sell:
            return AgressorSide.BUY
        if tem_sell and not tem_buy:
            return AgressorSide.SELL

        # Sem flag conclusiva: compara preço do trade com bid/ask vigentes.
        preco = float(tick["last"]) if tick["last"] else None
        bid = float(tick["bid"]) if tick["bid"] else None
        ask = float(tick["ask"]) if tick["ask"] else None
        if preco is not None and ask is not None and preco >= ask:
            return AgressorSide.BUY
        if preco is not None and bid is not None and preco <= bid:
            return AgressorSide.SELL
        return AgressorSide.UNKNOWN

    def _puxar_book(self, mt5: ModuleType) -> BookSnapshot | None:
        book = mt5.market_book_get(self._symbol)
        if not book:
            return None

        bids_brutos = [item for item in book if item.type in (0, getattr(mt5, "BOOK_TYPE_BUY", 0))]
        asks_brutos = [item for item in book if item.type in (1, getattr(mt5, "BOOK_TYPE_SELL", 1))]
        bids_brutos.sort(key=lambda i: -i.price)
        asks_brutos.sort(key=lambda i: i.price)

        def _para_niveis(itens) -> tuple[BookLevel, ...]:
            niveis = []
            for item in itens[: self._profundidade_maxima]:
                try:
                    preco_ticks = self._grid.to_ticks(float(item.price))
                except ValueError:
                    continue
                qty = int(item.volume) if item.volume else int(item.volume_dbl)
                niveis.append(BookLevel(price=preco_ticks, qty=qty, n_orders=1))
            return tuple(niveis)

        return BookSnapshot(
            # DERIVADO: `market_book_get` não devolve tempo nenhum. Relógio
            # do servidor, o mesmo dos trades — nunca `time.time_ns()`.
            timestamp_ns=self._agora_ns(),
            symbol=self._symbol,
            bids=_para_niveis(bids_brutos),
            asks=_para_niveis(asks_brutos),
        )

    # ------------------------------------------------------------------
    # Thread principal: só ela chama `Barramento.publicar`.
    # ------------------------------------------------------------------

    def _loop_consumo(self) -> None:
        while not (self._parar_evt.is_set() and self._fila.empty()):
            try:
                evento = self._fila.get(timeout=0.1)
            except queue.Empty:
                continue
            self._barramento.publicar(evento)


def derivar_deltas(anterior: BookSnapshot, atual: BookSnapshot) -> list[BookDelta]:
    """Compara dois snapshots consecutivos do mesmo símbolo e produz os
    `BookDelta` que levam de um ao outro — ADD (nível novo), DELETE (nível
    que sumiu) ou UPDATE (quantidade mudou na mesma posição). É o que
    alimenta a camada de microestrutura sem que ela precise conhecer MT5.
    """
    deltas: list[BookDelta] = []
    deltas.extend(_diff_lado(anterior.bids, atual.bids, Side.BUY, atual.timestamp_ns, atual.symbol))
    deltas.extend(_diff_lado(anterior.asks, atual.asks, Side.SELL, atual.timestamp_ns, atual.symbol))
    return deltas


def _diff_lado(
    antes: tuple[BookLevel, ...],
    depois: tuple[BookLevel, ...],
    side: Side,
    timestamp_ns: int,
    symbol: str,
) -> list[BookDelta]:
    antes_por_preco = {nivel.price: nivel for nivel in antes}
    depois_por_preco = {nivel.price: nivel for nivel in depois}
    deltas: list[BookDelta] = []

    for posicao, nivel in enumerate(depois):
        anterior_nivel = antes_por_preco.get(nivel.price)
        if anterior_nivel is None:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.ADD,
                    price=nivel.price,
                    qty=nivel.qty,
                    position=posicao,
                )
            )
        elif anterior_nivel.qty != nivel.qty:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.UPDATE,
                    price=nivel.price,
                    qty=nivel.qty,
                    position=posicao,
                )
            )

    for nivel in antes:
        if nivel.price not in depois_por_preco:
            deltas.append(
                BookDelta(
                    timestamp_ns=timestamp_ns,
                    symbol=symbol,
                    side=side,
                    action=BookAction.DELETE,
                    price=nivel.price,
                    qty=0,
                    position=-1,
                )
            )

    return deltas
