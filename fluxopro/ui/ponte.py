"""Adaptador `Barramento` -> Qt — `design/direcao_visual.md` §6, fase 0.

O barramento e sincrono e roda na thread da FONTE (ver `core/barramento.py`
e `scripts/operar.py`, onde `fonte.iniciar()` bloqueia). A interface roda na
thread do Qt. Este modulo e a unica costura entre as duas, e existe para
impor uma regra: **`publicar` nunca toca em widget**.

Se o barramento chamasse `update()` direto, cada tick agendaria um quadro —
que e literalmente o modo de falha que `base/painel_denso.py` foi escrito
para evitar (13,3 fps contra 560). Aqui os eventos entram num buffer e o
painel LE no seu proprio relogio de 16 ms. Num pregao a 5.000 ev/s isso e a
diferenca entre 5.000 quadros pedidos por segundo e 62 entregues.

## O teto, e por que ele nao e opcional

Buffer entre produtor rapido e consumidor lento e o defeito que este projeto
ja encontrou em OITO arquivos diferentes (ver `PROGRESSO.md`): estrutura que
cresce com o estado acumulado e e varrida tarde demais. Aqui ele seria pior
que nos outros, porque a UI travando por 2 s durante um leilao de abertura e
normal, e nesses 2 s entrariam ~10.000 negocios.

Entao o buffer tem teto e **o descarte e contado e exibido**. Um painel que
some com dado em silencio mente sobre a propria cobertura; um que mostra
`3.412 descartados` esta dizendo a verdade sobre um pregao que passou rapido
demais para a tela. As duas telas perdem o mesmo dado — so uma admite.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookDelta, BookSnapshot, Trade

NS_POR_SEGUNDO = 1_000_000_000

CAPACIDADE_TAPE = 4096
"""Negocios retidos entre duas leituras da UI.

A 5.000 ev/s isso e ~0,8 s de folga: cobre um engasgo de quadro (16 ms) com
50x de margem, e ainda assim tem teto. Numeros maiores nao compram robustez,
compram atraso — um tape 10 s atrasado nao e um tape."""

CAPACIDADE_EVENTOS = 512
"""Deteccoes e sinais. Muito menor porque a taxa e outra: a auditoria mediu
11 mil deteccoes em 500 mil eventos, ~2%."""

LIMITE_ATRASO_S = 2.0
"""Acima disto o painel entra em "dado atrasado" (§3.5). Nao esmaece o
numero: o trader ainda quer ver o ultimo preco conhecido."""

LIMITE_DESCONEXAO_S = 10.0


class EstadoFeed(Enum):
    AGUARDANDO = "aguardando"      # antes do primeiro evento
    VIVO = "vivo"
    ATRASADO = "atrasado"          # ultimo evento ha mais de LIMITE_ATRASO_S
    SEM_FEED = "sem_feed"          # mais de LIMITE_DESCONEXAO_S
    ENCERRADO = "encerrado"        # a fonte terminou por conta propria


@dataclass(frozen=True, slots=True)
class ItemTape:
    """Uma linha do tape, ja reduzida ao que a tela usa.

    Guardar o `Trade` inteiro custaria manter vivo o objeto de dominio por
    4.096 linhas; guardar o que se desenha custa menos e desacopla a UI de
    mudancas no evento de dominio.
    """

    timestamp_ns: int
    price: int
    qty: int
    agressor: int  # +1 comprador, -1 vendedor, 0 desconhecido (RLP)


@dataclass
class Contadores:
    trades: int = 0
    snapshots: int = 0
    deltas: int = 0
    descartados_tape: int = 0
    descartados_eventos: int = 0

    @property
    def total(self) -> int:
        return self.trades + self.snapshots + self.deltas


@dataclass
class Instantaneo:
    """O que a UI le de uma vez, ja consistente entre si.

    Ler campo a campo da ponte enquanto a thread da fonte escreve daria uma
    tela costurada de dois instantes — preco de agora com volume de antes.
    Um instantaneo montado sob o lock nao tem esse buraco.
    """

    estado: EstadoFeed
    ultimo_preco: int | None
    primeiro_preco: int | None
    volume_sessao: int
    delta_sessao: int
    volume_nao_atribuido: int
    ultimo_evento_ns: int
    atraso_s: float
    contadores: Contadores
    novos_trades: tuple[ItemTape, ...] = ()
    livro: BookSnapshot | None = None


class PonteFluxo:
    """Assina o barramento e guarda o minimo para a tela, com teto.

    Nao herda de `QObject` de proposito: a ponte tem de poder ser testada
    sem `QApplication`, e o unico recurso Qt que ela usaria (`Signal`) e
    justamente o que reintroduziria acoplamento por evento.
    """

    def __init__(
        self,
        barramento: Barramento,
        capacidade_tape: int = CAPACIDADE_TAPE,
        capacidade_eventos: int = CAPACIDADE_EVENTOS,
    ) -> None:
        self._lock = threading.Lock()
        self._tape: deque[ItemTape] = deque(maxlen=capacidade_tape)
        self._eventos: deque[object] = deque(maxlen=capacidade_eventos)
        self._contadores = Contadores()

        self._ultimo_preco: int | None = None
        self._primeiro_preco: int | None = None
        self._volume = 0
        self._delta = 0
        self._nao_atribuido = 0
        self._ultimo_evento_ns = 0
        self._ultimo_ingresso_perf = 0.0
        self._livro: BookSnapshot | None = None
        self._encerrado = False

        barramento.assinar(Trade, self._ao_trade)
        barramento.assinar(BookSnapshot, self._ao_snapshot)
        barramento.assinar(BookDelta, self._ao_delta)
        self._barramento = barramento

    # ---------------------------------------------------------------- entrada
    # Tudo abaixo roda na thread da FONTE. Nada aqui pode tocar em widget,
    # criar QPixmap, nem chamar update().

    def _ao_trade(self, trade: Trade) -> None:
        agressor = _agressor_para_int(trade.side_agressor)
        item = ItemTape(trade.timestamp_ns, trade.price, trade.qty, agressor)
        with self._lock:
            if len(self._tape) == self._tape.maxlen:
                # `deque` com `maxlen` descarta pela esquerda em silencio.
                # Contar ANTES do append e o que transforma perda invisivel
                # em numero na tela.
                self._contadores.descartados_tape += 1
            self._tape.append(item)
            self._contadores.trades += 1
            self._volume += trade.qty
            if agressor > 0:
                self._delta += trade.qty
            elif agressor < 0:
                self._delta -= trade.qty
            else:
                # RLP anonimiza ate 15% do volume de WDO/WIN por regra da B3.
                # Entra no volume e NAO no delta — a mesma assimetria que o
                # `Candle` carrega, aqui contada em vez de descartada.
                self._nao_atribuido += trade.qty
            if self._primeiro_preco is None:
                self._primeiro_preco = trade.price
            self._ultimo_preco = trade.price
            self._marcar_tempo(trade.timestamp_ns)

    def _ao_snapshot(self, snapshot: BookSnapshot) -> None:
        with self._lock:
            # So o ULTIMO importa: o book nao tem historia na tela do DOM.
            # Acumular snapshots seria guardar 5.000 fotos por segundo para
            # desenhar uma.
            self._livro = snapshot
            self._contadores.snapshots += 1
            self._marcar_tempo(snapshot.timestamp_ns)

    def _ao_delta(self, delta: BookDelta) -> None:
        with self._lock:
            self._contadores.deltas += 1
            self._marcar_tempo(delta.timestamp_ns)

    def registrar_evento(self, evento: object) -> None:
        """Deteccoes e sinais, vindos dos callbacks de `SessaoFluxo`."""
        with self._lock:
            if len(self._eventos) == self._eventos.maxlen:
                self._contadores.descartados_eventos += 1
            self._eventos.append(evento)

    def marcar_encerrado(self) -> None:
        with self._lock:
            self._encerrado = True

    def _marcar_tempo(self, timestamp_ns: int) -> None:
        # Chamado sob o lock. Dois relogios de proposito: `timestamp_ns` e
        # tempo de MERCADO (pode ser replay acelerado, ou 2019), e
        # `perf_counter` e tempo de PAREDE, o unico que responde "faz quanto
        # tempo que nao chega nada". Confundir os dois faria um replay de
        # arquivo antigo aparecer como feed morto.
        if timestamp_ns > self._ultimo_evento_ns:
            self._ultimo_evento_ns = timestamp_ns
        self._ultimo_ingresso_perf = time.perf_counter()

    # ------------------------------------------------------------------ saida
    # Tudo abaixo roda na thread do QT.

    def ler(self) -> Instantaneo:
        """Drena o que chegou desde a ultima leitura e devolve um retrato.

        **UM DONO SO.** Este metodo esvazia o buffer, entao quem chamar
        segundo recebe tape vazio. Quem chama e a janela, uma vez por
        quadro, e ela distribui o mesmo `Instantaneo` para todos os paineis
        (`janela.py`). Painel nenhum chama `ler` sozinho.

        A alternativa — cada painel com seu proprio cursor sobre um buffer
        compartilhado — foi recusada porque o buffer so poderia ser liberado
        quando o painel MAIS LENTO tivesse lido, e ai o teto deixaria de ser
        um teto: um painel travado seguraria a memoria de todos. O acoplamento
        que se ganha aqui (a janela e a dona do relogio de dados) e menor que
        o que se perderia la.
        """
        agora = time.perf_counter()
        with self._lock:
            novos = tuple(self._tape)
            self._tape.clear()
            atraso = (
                agora - self._ultimo_ingresso_perf
                if self._ultimo_ingresso_perf > 0.0
                else 0.0
            )
            estado = self._estado(atraso)
            return Instantaneo(
                estado=estado,
                ultimo_preco=self._ultimo_preco,
                primeiro_preco=self._primeiro_preco,
                volume_sessao=self._volume,
                delta_sessao=self._delta,
                volume_nao_atribuido=self._nao_atribuido,
                ultimo_evento_ns=self._ultimo_evento_ns,
                atraso_s=atraso,
                contadores=Contadores(**vars(self._contadores)),
                novos_trades=novos,
                livro=self._livro,
            )

    def _estado(self, atraso_s: float) -> EstadoFeed:
        # Chamado sob o lock.
        if self._encerrado:
            return EstadoFeed.ENCERRADO
        if self._ultimo_ingresso_perf == 0.0:
            return EstadoFeed.AGUARDANDO
        if atraso_s >= LIMITE_DESCONEXAO_S:
            return EstadoFeed.SEM_FEED
        if atraso_s >= LIMITE_ATRASO_S:
            return EstadoFeed.ATRASADO
        return EstadoFeed.VIVO

    def drenar_eventos(self) -> tuple[object, ...]:
        with self._lock:
            itens = tuple(self._eventos)
            self._eventos.clear()
            return itens

    def desligar(self) -> None:
        """Solta as assinaturas.

        Sem isso, uma janela fechada continuaria recebendo o pregao inteiro
        pelo barramento — o objeto vive enquanto o barramento segurar o
        callback."""
        self._barramento.desassinar_objeto(self)


def _agressor_para_int(lado: object) -> int:
    """`AgressorSide` -> -1/0/+1 sem importar o Enum no caminho quente.

    `Enum.__hash__` e um metodo Python; a auditoria da onda 7 mediu isso
    custando caro quando chamado por negocio (3x por trade, 15,7 M chamadas).
    Aqui a conversao acontece UMA vez, na entrada, e o resto da UI compara
    inteiros.
    """
    nome = getattr(lado, "name", "")
    if nome == "BUY":
        return 1
    if nome == "SELL":
        return -1
    return 0
