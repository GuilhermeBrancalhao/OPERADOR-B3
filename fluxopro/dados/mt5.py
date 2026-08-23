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

O offset é estimado pelo **MÁXIMO SOBRE UMA JANELA DESLIZANTE** de
amostras, com **detecção explícita de regressão do servidor** por cima.
Três fatos empurram para esse desenho, e cada um mata uma alternativa:

1. Toda amostra `time_msc - relógio_local` SUBESTIMA o offset verdadeiro,
   porque um tick só pode ser observado DEPOIS de ter acontecido. Por isso
   o estimador é um MÁXIMO e não a última amostra: com "a última vence",
   um mercado parado re-observa o mesmo tick velho a cada poll e o relógio
   derivado fica preso na hora do último negócio — erro crescendo sem
   limite (medido: -60 s e subindo 50 ms por poll com o tape parado há um
   minuto) e todo `BookSnapshot` carimbado no passado.

2. Máximo puro é uma CATRACA: nunca esquece. Se o relógio do servidor
   REGREDIR — troca de servidor da corretora, ajuste de NTP do lado deles,
   failover, virada de horário de verão — o offset fica inflado para o
   resto da vida do processo. Medido: 5.000 amostras corretas depois da
   regressão não movem o estimador um nanossegundo. E uma regressão de
   400 ms já excede a janela de reconciliação de 300 ms do `InferidorMBP`
   ⇒ 100% das execuções viram cancelamento, agora permanentemente. Por
   isso o máximo tem MEMÓRIA FINITA: `janela_s` (120 s por padrão).

3. Amostra velha e regressão de servidor produzem o MESMO sinal bruto
   ("estimativa abaixo do máximo vigente"), então magnitude sozinha não
   distingue as duas. O que distingue é o comportamento do relógio do
   SERVIDOR, não o do offset: com o tape parado o `time_msc` NÃO ANDA (é o
   mesmo tick de novo) e num tick fora de ordem ele recua UMA vez e o
   próximo já volta ao normal; numa regressão o `time_msc` recua e depois
   volta a ANDAR PARA A FRENTE num referencial deslocado, indefinidamente. Daí as duas
   regras que fazem o estimador funcionar nos três regimes:

   - **Admissão**: só entra na janela — e só é avaliada pelo detector — a
     amostra cujo `time_msc` ANDOU em relação ao último observado.
     Re-observar o mesmo tick, ou receber um tick atrasado, é informação
     zero sobre o offset. Consequência deliberada: com o tape parado a
     janela para de girar e o offset FICA, que é o comportamento certo
     porque não chegou informação nova que justificasse mudá-lo. A janela
     só esquece quando há tempo de servidor novo para esquecer em cima; é
     isso que impede o esquecimento de reintroduzir o defeito do item 1.
     O `deque` também nunca é esvaziado pela poda por idade (mantém no
     mínimo 1 entrada) pela mesma razão. E é por isso que um tick atrasado
     ISOLADO não pode disparar reset: ele nem chega ao detector.

   - **Detecção**, em dois tempos, porque nenhum sinal sozinho decide:

     *Armar* — o `time_msc` andou PARA TRÁS em relação ao anterior. É o
     único sinal FÍSICO que só uma regressão produz: tape parado repete o
     `time_msc`, tape lento não o faz recuar, e adaptador sobrecarregado
     também não (a hora do servidor continua subindo, só que mais devagar
     que a local). Armar não decide nada — um tick fora de ordem no lote
     também arma.

     *Confirmar* — com o detector armado, o `deficit = máximo vigente -
     estimativa desta amostra` das amostras SEGUINTES é exatamente o erro
     que o estimador está cometendo agora. Num tick fora de ordem isolado o
     tape volta ao normal e o déficit cai para a idade do tick
     (milissegundos): o detector DESARMA sem ter feito nada. Num step de
     servidor o tape voltou a andar num referencial deslocado e o déficit
     fica em ~recuo, amostra após amostra. `amostras_para_regressao`
     amostras consecutivas acima de `limiar_regressao_ns` são a prova de
     "persistente" em vez de "pico isolado": aí o estimador é RESETADO
     (janela e piso monotônico) e sai um `FalhaCaptura(RELOGIO_REGREDIU)`,
     alto, no log e na gravação.

     Convergência: `amostras_para_regressao + 1` polls — o tick do step em
     si só arma, não conta — ou seja ~200 ms com o poll padrão de 50 ms.
     Tape parado no meio do episódio não alimenta o detector (não há tempo
     de servidor novo) e um tick fora de ordem zera a contagem; os dois
     ATRASAM a convergência, nenhum a impede, e o teste de propriedade
     prende esse teto.

     As duas metades são necessárias. Só o déficit: `bench_mt5.py` no
     regime de 50.000 ticks/s mostra o adaptador consumindo tape mais devagar
     que o relógio de parede — o déficit cresce centenas de ms por poll e o
     detector declararia "regressão" onde o offset verdadeiro não mudou
     (medido: oito falsos positivos numa única passada do benchmark). Só o
     armar: todo tick fora de ordem viraria reset. Só o recuo do `time_msc`
     contra o pico já visto, sem déficit: numa regressão pequena o tape
     RECUPERA o pico em poucos polls (400 ms de recuo com poll de 50 ms:
     oito polls) enquanto o erro do offset continua exatamente 400 ms para
     sempre — o detector pararia de ver justamente o defeito que precisa
     ver.

     Falso positivo possível e aceito: um tick fora de ordem SEGUIDO de
     `amostras_para_regressao` polls atrasados em mais que
     `limiar_regressao_ns` cada. O reset nesse caso adota uma amostra
     levemente velha e o máximo volta a subir no poll seguinte —
     degradação de milissegundos, contra o erro permanente da catraca.

Por que os limiares são esses. `limiar_regressao_ns` = 250 ms é escolhido
CONTRA a janela de reconciliação de 300 ms do `InferidorMBP`: toda
regressão capaz de estourar essa janela é detectada e corrigida em
`amostras_para_regressao` + 1 polls; regressão menor que 250 ms não estoura a
janela de 300 ms de qualquer jeito, e a janela deslizante a absorve
sozinha em no máximo `janela_s`. `amostras_para_regressao` = 3 é o menor
valor que não confunde um par de ticks fora de ordem com um step.
`janela_s` = 120 s é o teto do erro residual de uma regressão sub-limiar,
e é longo o bastante para que uma pausa de tape de alguns minutos com
ticks esparsos não force o estimador a adotar amostras degradadas.
`max_amostras` = 4096 é um teto DURO de memória. O `deque` é monotônico e
normalmente tem um punhado de entradas — a amostra nova expulsa todas as
menores —, mas o pior caso existe e tem nome: offset ESTRITAMENTE
DECRESCENTE, que é o adaptador consumindo tape mais devagar que o relógio
de parede. Aí nada é expulso e a fila cresceria com a duração da sessão.
Ao estourar o teto, a janela efetiva encurta pela frente — degradação
segura, nunca crescimento sem limite.

**Alternativas descartadas, e por quê.** *Decaimento do offset em direção
à amostra corrente*: não existe taxa que sirva aos dois regimes. Com o
tape parado a amostra corrente é o tick velho, e ela envelhece sem limite
— decair na direção dela é decair na direção do erro do item 1, só que
mais devagar; para que a deriva com tape parado fosse aceitável, a taxa
teria de ser tão lenta que uma regressão levaria muito mais que
`janela_s` para ser absorvida. *Janela deslizante SOZINHA*: absorve
qualquer regressão, mas só em `janela_s` — e durante esses 120 s toda
execução vira cancelamento, que é exatamente o modo de falha que se quer
matar. *Detecção de regressão SOZINHA*: não pega regressão abaixo do
limiar, e baixar o limiar o bastante para pegá-las faz o detector confundir
tape parado com step. As três peças juntas cobrem o espaço; nenhuma cobre
sozinha.

O reset da regressão quebra a monotonicidade do relógio derivado de
propósito — o piso `_ultimo_ns` também volta, senão ele sozinho prenderia
o relógio no referencial antigo. Essa é a única quebra, e ela é ANUNCIADA
pelo `FalhaCaptura(RELOGIO_REGREDIU)`: o replay vê a descontinuidade e
sabe de onde ela veio, em vez de herdar um relógio mentiroso em silêncio.

Não existe fonte mais fresca no pacote `MetaTrader5`: `symbol_info_tick`
devolve o mesmo último tick, e `terminal_info` não expõe hora de servidor.


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
from collections import deque
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

# --- Limiares do estimador de offset do relogio de servidor ---------------
# A justificativa de cada numero esta em "UM RELOGIO SO NA BORDA" no topo.
# Memoria finita do maximo: teto do erro residual de uma regressao de
# servidor pequena demais para o detector abaixo enxergar.
_JANELA_OFFSET_S = 120.0
# Recuo do `time_msc` a partir do qual vale a pena suspeitar de step de
# servidor. 250 ms e escolhido CONTRA a janela de reconciliacao de 300 ms do
# `InferidorMBP`: o que pode estourar aquela janela tem de ser detectado.
_LIMIAR_REGRESSAO_NS = 250_000_000
# Amostras consecutivas e crescentes abaixo do pico para declarar step. 3 e o
# menor valor que nao confunde um par de ticks fora de ordem com uma regressao.
_AMOSTRAS_PARA_REGRESSAO = 3
# Teto DURO de entradas no deque da janela -- a memoria nao pode crescer com a
# duracao da sessao (a janela e monotonica e costuma ter poucas entradas).
_MAX_AMOSTRAS_OFFSET = 4096

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
    """Fonte de tempo UNICA da borda MT5 (ver "UM RELOGIO SO" no topo).

    `observar` mede o offset entre o relogio do servidor (`time_msc` de um
    tick) e o relogio local; `agora_ns` devolve o instante corrente ja no
    referencial do servidor, para os eventos que nao trazem tempo proprio.
    O piso `_ultimo_ns` garante que a sequencia que sai do adaptador seja
    monotonica mesmo quando o offset e remedido entre dois eventos.

    O estimador e o MAXIMO SOBRE UMA JANELA DESLIZANTE, com deteccao
    explicita de regressao do servidor -- a justificativa completa (por que
    maximo, por que janela, por que deteccao, e por que decaimento e cada
    peca isolada perdem) esta em "UM RELOGIO SO NA BORDA" no topo do
    modulo. Os quatro parametros do construtor sao os limiares desse
    desenho e estao explicados la, um a um.

    `observar` devolve `None` no caso normal e a MAGNITUDE em ns do recuo
    quando detecta uma regressao de servidor -- o chamador transforma isso
    num `FalhaCaptura(RELOGIO_REGREDIU)`. Nunca engolir em silencio: o
    reset quebra a monotonicidade do relogio derivado de proposito, e o
    replay precisa saber onde.
    """

    __slots__ = (
        "_amostras_para_regressao",
        "_armado",
        "_janela",
        "_janela_ns",
        "_limiar_regressao_ns",
        "_max_amostras",
        "_sincronizado",
        "_suspeitas",
        "_ultimo_ns",
        "_ultimo_observado_ns",
    )

    def __init__(
        self,
        janela_s: float = _JANELA_OFFSET_S,
        limiar_regressao_ns: int = _LIMIAR_REGRESSAO_NS,
        amostras_para_regressao: int = _AMOSTRAS_PARA_REGRESSAO,
        max_amostras: int = _MAX_AMOSTRAS_OFFSET,
    ) -> None:
        # deque monotonicamente DECRESCENTE em `estimativa`: a frente e o
        # maximo da janela e tambem a entrada mais VELHA, entao a poda por
        # idade e a leitura do maximo sao o mesmo ponto. O(1) amortizado.
        self._janela: "deque[tuple[int, int]]" = deque()
        self._janela_ns = max(1, int(janela_s * 1_000_000_000))
        self._limiar_regressao_ns = max(0, int(limiar_regressao_ns))
        self._amostras_para_regressao = max(1, int(amostras_para_regressao))
        self._max_amostras = max(1, int(max_amostras))

        self._sincronizado = False
        self._armado = False
        self._ultimo_ns = 0
        self._ultimo_observado_ns = 0
        self._suspeitas = 0

    @property
    def sincronizado(self) -> bool:
        return self._sincronizado

    @property
    def offset_ns(self) -> int:
        """Servidor menos local, em ns. 0 enquanto nenhum tick foi visto."""
        return self._janela[0][1] if self._janela else 0

    @property
    def amostras_na_janela(self) -> int:
        """Tamanho do deque monotonico -- para teste de memoria limitada."""
        return len(self._janela)

    def observar(self, servidor_ns: int) -> Optional[int]:
        """Alimenta o estimador com o `time_msc` (em ns) de um tick.

        Devolve `None` normalmente, ou o DEFICIT em ns quando conclui que o
        relogio do SERVIDOR regrediu (e ja se re-sincronizou nele).
        """
        estimativa = servidor_ns - time.time_ns()
        if not self._sincronizado:
            self._resetar(servidor_ns, estimativa)
            return None

        anterior = self._ultimo_observado_ns
        self._ultimo_observado_ns = servidor_ns

        if servidor_ns < anterior:
            # ARMAR: o relogio do SERVIDOR andou para tras. E o unico sinal
            # fisico que so uma regressao produz — tape parado repete o
            # `time_msc`, tape atrasado nao o faz recuar, e adaptador
            # sobrecarregado tambem nao (a hora do servidor continua
            # subindo, so que mais devagar que a local). Armar nao decide
            # nada: um tick fora de ordem tambem chega aqui.
            self._armado = True
            self._suspeitas = 0
            if servidor_ns > self._ultimo_ns:
                self._ultimo_ns = servidor_ns
            return None

        if servidor_ns == anterior:
            # ADMISSAO: re-observar o mesmo tick (tape parado) e informacao
            # zero sobre o offset. Deixar essa amostra entrar — ou envelhecer
            # a janela — e o defeito da "ultima amostra vence" de volta.
            return None

        if self._armado:
            regressao = self._avaliar_regressao(estimativa)
            if regressao is not None:
                self._resetar(servidor_ns, estimativa)
                return regressao

        self._admitir(estimativa)
        if servidor_ns > self._ultimo_ns:
            self._ultimo_ns = servidor_ns
        return None

    def _avaliar_regressao(self, estimativa: int) -> Optional[int]:
        """Com o detector ARMADO, o recuo do servidor foi um step ou um tick
        fora de ordem? Decide pelo DEFICIT das amostras seguintes.

        `deficit = maximo_vigente - estimativa desta amostra` e exatamente o
        erro que o estimador esta cometendo agora, e cada regime o assina
        diferente:

        * tick fora de ordem isolado — o tape volta ao normal no proximo
          tick e o deficit cai para a idade do tick (milissegundos): o
          detector DESARMA sem ter feito nada;
        * step de servidor — o tape voltou a andar num referencial
          deslocado, e o deficit fica em ~recuo, amostra apos amostra. Sao
          as `amostras_para_regressao` consecutivas que provam "persistente"
          em vez de "pico isolado".

        Falso positivo possivel e aceito: um tick fora de ordem SEGUIDO de
        `amostras_para_regressao` polls atrasados em mais que
        `limiar_regressao_ns` cada. O reset nesse caso adota uma amostra
        levemente velha e o maximo volta a subir no poll seguinte —
        degradacao de milissegundos, contra o erro permanente que a catraca
        produzia.
        """
        deficit = self.offset_ns - estimativa
        if deficit <= self._limiar_regressao_ns:
            self._armado = False
            self._suspeitas = 0
            return None
        self._suspeitas += 1
        if self._suspeitas >= self._amostras_para_regressao:
            return deficit
        return None

    def _admitir(self, estimativa: int) -> None:
        agora_mono = time.monotonic_ns()
        janela = self._janela
        while janela and janela[-1][1] <= estimativa:
            janela.pop()
        janela.append((agora_mono, estimativa))
        limite = agora_mono - self._janela_ns
        while len(janela) > 1 and janela[0][0] < limite:
            janela.popleft()
        while len(janela) > self._max_amostras:
            # teto DURO de memoria: encurta a janela efetiva pela frente
            # (a entrada mais velha), nunca cresce sem limite.
            janela.popleft()

    def _resetar(self, servidor_ns: int, estimativa: int) -> None:
        """Recomeca o estimador no referencial da amostra corrente.

        O piso `_ultimo_ns` volta junto — de proposito. Ele e um maximo
        monotonico do tempo de servidor; mante-lo depois de um step para
        baixo prenderia o relogio derivado no referencial antigo mesmo com
        o offset ja corrigido, que e metade do defeito que se esta
        consertando.
        """
        self._janela.clear()
        self._sincronizado = True
        self._armado = False
        self._suspeitas = 0
        self._ultimo_observado_ns = servidor_ns
        self._ultimo_ns = servidor_ns
        self._admitir(estimativa)

    def agora_ns(self) -> int:
        derivado = time.time_ns() + self.offset_ns
        if derivado <= self._ultimo_ns:
            # piso monotonico: nunca voltar no tempo nem empatar com o
            # evento anterior, senao a ordem de entrega deixa de ser
            # reconstruivel no replay (que ordena por timestamp).
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


def inferir_agressor(mt5: ModuleType, tick) -> AgressorSide:
    """Quem AGREDIU neste negocio, pelas flags e, na falta delas, pelo preco.

    Funcao de MODULO, e nao metodo, porque ha dois consumidores: o adaptador ao
    vivo e `scripts/importar_mt5.py`, que le o mesmo `copy_ticks_from` sobre um
    pregao ja fechado. Se cada um inferisse do seu jeito, a gravacao feita ao
    vivo e a importada do mesmo dia divergiriam — e a divergencia so apareceria
    ao comparar duas leituras do mesmo pregao, que e o momento em que ninguem
    espera diferenca.

    A B3 marca `TICK_FLAG_BUY`/`TICK_FLAG_SELL` na maioria dos negocios (medido
    em WDOU26, pregao de 21/08/2026: 86,8% de 90.459). O resto cai na
    comparacao com bid/ask, e o que nao decide vira `UNKNOWN` — que o produto
    trata como volume sem lado, nao como zero.
    """
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


def trade_de_tick(
    mt5: ModuleType, tick, symbol: str, grid: PriceGrid, ordem: int
) -> Trade | None:
    """Um tick do MT5 vira um `Trade`, ou `None` se nao for negocio utilizavel.

    `None` para preco zerado ou fora da grade — os dois casos existem no dado
    de verdade (tick de atualizacao de book sem negocio, e preco que nao cai
    num multiplo do tick). Quem chama e responsavel por avancar o cursor
    MESMO assim: prender o cursor num tick invalido foi um defeito real deste
    adaptador.

    O `trade_id` carrega a ordem dentro do milissegundo. Sem ela, negocios do
    mesmo ms com as mesmas flags teriam id igual — e o dedupe da gravacao
    apagaria negocio de verdade.
    """
    preco_bruto = float(tick["last"]) if tick["last"] else float(tick["bid"])
    if preco_bruto <= 0:
        return None
    try:
        preco_ticks = grid.to_ticks(preco_bruto)
    except ValueError:
        return None

    time_msc = int(tick["time_msc"])
    return Trade(
        timestamp_ns=time_msc * 1_000_000,
        symbol=symbol,
        price=preco_ticks,
        qty=int(tick["volume"]) if tick["volume"] else int(tick["volume_real"]),
        side_agressor=inferir_agressor(mt5, tick),
        trade_id=f"MT5-{time_msc}-{ordem}-{int(tick['flags'])}",
    )


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

            trade = trade_de_tick(mt5, tick, self._symbol, self._grid, ordem)
            if trade is None:
                continue
            trades.append(trade)

        # o tempo do servidor vem do tick mais novo do lote (crescente).
        recuo_ns = self._relogio.observar(
            int(ticks[len(ticks) - 1]["time_msc"]) * 1_000_000
        )
        if recuo_ns is not None:
            # o relogio do servidor deu um step para tras e o estimador ja se
            # re-sincronizou nele. Isso NAO pode ser silencioso: o relogio
            # derivado acabou de saltar para tras, e o replay precisa saber
            # onde a descontinuidade esta (ver "UM RELOGIO SO NA BORDA").
            falhas.append(
                self._falha(
                    TipoFalha.RELOGIO_REGREDIU,
                    f"relogio do servidor MT5 recuou {recuo_ns / 1e6:.3f} ms em "
                    f"{_AMOSTRAS_PARA_REGRESSAO} amostras consecutivas "
                    "(troca de servidor da corretora, ajuste de NTP ou failover); "
                    "estimador de offset resetado no referencial novo — os "
                    "eventos derivados daqui em diante nao sao comparaveis com "
                    "os anteriores sem levar este salto em conta"
                )
            )
            _logger.warning(
                "relogio do servidor MT5 regrediu %.3f ms — estimador de offset "
                "resetado",
                recuo_ns / 1e6,
            )

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
        """Delega para a funcao de modulo. Ver `inferir_agressor`."""
        return inferir_agressor(mt5, tick)

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
