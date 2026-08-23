"""Detectores de comportamento de player sobre o `LivroMBO`.

Cada detector é parametrizável (dataclass `Config...`, zero número mágico no
corpo) e emite um evento com `confianca: float` e `evidencia: dict` — quem lê
a saída precisa poder auditar POR QUE algo foi sinalizado, não só receber um
rótulo. Nenhum detector afirma fato onde só há hipótese: em feed agregado
(`FonteMicro.MBP_INFERIDO`) a confiança do evento de origem se propaga.

Termos usados de propósito NEUTROS: `LiquidezFantasma` em vez de "spoofing"
(acusação legal que este código não tem base para fazer).

## Procedência: como a confiança do evento de origem se propaga

Três detectores leem o `LivroMBO` (`DetectorEscora`,
`DetectorIcebergPorRecarga`, `DetectorLiquidezFantasma`). Em fonte MT5 ou
simulador esse livro é **inteiramente sintético** — reconstruído pelo
`InferidorMBP` a partir de book agregado por preço. Uma detecção feita ali é
hipótese sobre hipótese; publicá-la com `confianca=1.0` apagaria justamente a
distinção observado × inferido que este pacote existe para preservar.

Cada um desses três mantém um **livro-razão de procedência** alimentado pelos
`OrdemEvento` que constroem a evidência que ele lê:

    detector.acompanhar(livro)          # uma linha: assina o fluxo do livro
    # ou, no caminho pull:
    detector.verificar(..., evento=ev)  # o evento gatilho entra na cadeia

**Política de combinação: MÍNIMO da cadeia (elo mais fraco).** Justificativa,
porque a escolha não é neutra:

* A detecção é uma **conjunção**, não uma disjunção: a escora só existe se
  *cada uma* das N reposições aconteceu; o iceberg só existe se *cada* recarga
  aconteceu. A confiança de uma conjunção nunca é maior que a do termo menos
  confiável — o mínimo é a cota superior correta.
* **Produto seria correto sob independência, e os eventos não são
  independentes.** Todos saem do mesmo `InferidorMBP`, com a mesma janela de
  reconciliação, sobre o mesmo dado agregado: os erros são fortemente
  correlacionados. Multiplicar três hipóteses de 0,60 daria 0,216 e
  transformaria detecção legítima em ruído — pessimismo fabricado, tão
  inventado quanto o 1,0 que se quer eliminar.
* **Média (ponderada ou não) deixa um elo certo MASCARAR um chute.** Quatro
  eventos observados (1,0) e um inferido a 0,30 dariam 0,86 — e a detecção
  inteira depende exatamente do elo de 0,30.
* O mínimo é o t-norm de Gödel: **idempotente** (ver o mesmo fato inferido
  duas vezes não o torna mais certo) e **monótono** (juntar um fato observado
  nunca AUMENTA a confiança da cadeia). São precisamente as duas propriedades
  que a promessa "nunca apresentar hipótese como fato" exige.

`evidencia["procedencia"]` publica o rótulo (`OBSERVADA` / `INFERIDA` /
`DESCONHECIDA`) e `evidencia["n_eventos_procedencia"]` o tamanho da cadeia,
para que a decisão seja auditável e não precise de fé.

**Cadeia vazia** (`DESCONHECIDA`): quem nunca chamou `acompanhar`/`observar`
não deu ao detector nenhuma procedência, e o detector não inventa uma — cai
no default do pacote (`CONFIANCA_OBSERVADO`, o mesmo default de
`OrdemEvento`) e **declara na evidência** que não há cadeia. Ausência de
informação declarada não é a mesma coisa que afirmação de fato; o 1,0 mudo
que existia antes era. Nesse caso `evidencia["fonte"]` sai `None`, não
`"MBO"`: publicar o rótulo de feed observado sobre uma cadeia que não existe
seria cometer, no dicionário de auditoria, exatamente o erro que a confiança
deixou de cometer.

## Memória: todo estado retido tem teto

Detector de fluxo roda a 5–10 mil eventos/s por 6 horas. Qualquer estrutura
que cresça sem poda vira vazamento em minutos, não em dias:

* janelas de trade são `deque(maxlen=...)` dimensionadas pela config
  (`DetectorExaustao`, `DetectorClipInstitucional`) ou podadas por tempo
  (`DetectorAbsorcao`);
* os livros-razão de procedência/dedup dos detectores de livro são
  `_MapaProcedencia`, que **expira chave por tempo** (`JANELA_EPISODIO_NS`) e
  guarda `LIMITE_CHAVES_RASTREADAS` só como backstop — nunca o `set` que
  crescia um item por nível/ordem ao longo do pregão.

A ordem dessas duas coisas importa e custou uma revisão inteira para ficar
clara. A onda 7 pôs teto rígido de 4.096 chaves com despejo FIFO; a crítica R4
(§A.5) mediu a consequência e ela era **penhasco**, não degradação: 0% de
re-emissão indevida com 4.096 chaves em rotação e **100% com 5.000**. E como
Iceberg e Fantasma chaveavam por `order_id` — sintético, ~65.000 criados por
segundo pelo `InferidorMBP` —, 4.096 chaves eram **63 ms** de memória contra um
fenômeno que dura segundos. Contagem de chaves é a grandeza errada para
delimitar um episódio; **tempo** é a certa, e o teto por contagem fica onde
sempre devia estar: como limite de desastre, não como política.

## Chave de episódio: `(side, price)` nos três detectores de livro

Um iceberg em 5000,5 é UM episódio, independente de quantos `order_id` a ponte
inventou para representá-lo. O `order_id` identifica a ordem; não identifica o
fenômeno — e em feed inferido nem sequer identifica a ordem, porque é uma
etiqueta que o próprio sistema recicla. Ele segue publicado na `evidencia`.

## Virada de sessão

Todo detector expõe `iniciar_nova_sessao()`, que devolve o objeto ao estado de
recém-construído (janelas vazias, dedup rearmado, livro-razão de procedência
zerado) **sem trocar a instância nem a config**. Sem isso um nível sinalizado
no dia 1 fica mudo no dia 2 (`criticas/nucleo_r3.md` §C.4) e a janela de tape
atravessa o fechamento colando o último trade de ontem no primeiro de hoje.

`fluxopro/app/sessao_fluxo.py` opta por **recriar** os detectores na virada,
porque lá a virada também troca o `LivroMBO` e a religação dos ouvintes é
necessária de qualquer jeito. Os dois caminhos existem de propósito: quem
segura a referência (uma UI, um backtest que compara dias) reseta no lugar;
quem reconstrói a montagem inteira recria. O que **não** pode existir é
detector sem nenhum dos dois — que era o estado anterior.
"""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Hashable
from dataclasses import dataclass, field
from enum import Enum, unique
from itertools import islice

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.eventos_mbo import (
    CONFIANCA_OBSERVADO,
    FonteMicro,
    Ordem,
    OrdemEvento,
)
from fluxopro.microestrutura.livro_mbo import LivroMBO


@unique
class TipoDeteccao(Enum):
    ABSORCAO = "ABSORCAO"
    ESCORA = "ESCORA"
    ICEBERG = "ICEBERG"
    LIQUIDEZ_FANTASMA = "LIQUIDEZ_FANTASMA"
    EXAUSTAO = "EXAUSTAO"
    CLIP_INSTITUCIONAL = "CLIP_INSTITUCIONAL"


@dataclass(frozen=True, slots=True)
class Deteccao:
    timestamp_ns: int
    symbol: str
    tipo: TipoDeteccao
    side: Side
    price: int | None
    confianca: float
    evidencia: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Procedência — a cadeia de eventos que sustenta uma detecção de livro
# ---------------------------------------------------------------------------

#: Teto de chaves rastreadas por detector de livro. É o BACKSTOP de memória,
#: não a política: quem regula o tamanho no dia a dia é `JANELA_EPISODIO_NS`
#: (chave que ninguém toca há uma janela sai). O teto só existe para que um
#: feed patológico não consiga fazer o mapa crescer sem limite, e por isso é
#: dimensionado com ordens de grandeza de folga sobre a população de chaves
#: VIVAS que um pregão produz (~1.200 níveis `(side, price)` num WDO).
#:
#: HISTÓRICO — por que 4.096 não servia (`criticas/nucleo_r4.md` §A.5): com a
#: chave por `order_id` sintético, o `InferidorMBP` cria ~6,5 ordens por evento
#: de mercado, ~65.000 chaves/s na barra de 10.000 ev/s. 4.096 chaves cobriam
#: **63 ms** de tape contra um fenômeno (iceberg recarregando) que dura
#: segundos. E o despejo FIFO desabava em PENHASCO: 0% de re-emissão indevida
#: com 4.096 chaves em rotação, 100% com 5.000. Os dois lados foram
#: consertados — a chave (ver `_chave_do_evento`) e a política (ver
#: `_MapaProcedencia`).
LIMITE_CHAVES_RASTREADAS = 65536

#: Quanto tempo uma chave sobrevive sem ser tocada. É a definição operacional
#: de "episódio": um iceberg em 5000,5 que recarrega de 3 em 3 segundos é UM
#: episódio; o mesmo nível voltando a chamar atenção meia hora depois é outro.
#: 30 s cobre com folga a duração de uma recarga de iceberg e de uma sequência
#: de reposições de escora, e é curto o bastante para que o mapa encolha
#: sozinho quando o mercado esfria.
JANELA_EPISODIO_NS = 30_000_000_000

#: Sorteio do despejo por excedente. Semente FIXA de propósito: o despejo
#: precisa ser IMPREVISÍVEL EM RELAÇÃO À ORDEM DAS CHAVES (é isso que mata a
#: ressonância da varredura cíclica), não imprevisível entre execuções — teste
#: e reprodução de incidente valem mais que entropia aqui.
_SORTEIO_DESPEJO = random.Random(0x5EED2026)


@dataclass(slots=True)
class _Procedencia:
    """Cadeia de evidência de UMA chave (um nível de preço) num episódio.

    `confianca` é o mínimo já visto e `fonte` degrada para `MBP_INFERIDO` no
    primeiro evento inferido — as duas grandezas são monótonas para baixo, de
    modo que a ordem de chegada dos eventos não muda o resultado.

    `ts_ultimo_ns` é o relógio do EVENTO (não da máquina): é ele que define se
    a chave ainda está dentro do episódio. `pos` é o índice desta chave no
    vetor de despejo do `_MapaProcedencia` — detalhe de estrutura, mora aqui
    porque um dicionário paralelo custaria uma segunda tabela hash no caminho
    quente.
    """

    confianca: float = CONFIANCA_OBSERVADO
    fonte: FonteMicro = FonteMicro.MBO
    n_eventos: int = 0
    sinalizado: bool = False
    ts_ultimo_ns: int = 0
    pos: int = -1

    def somar(self, confianca: float, fonte: FonteMicro) -> None:
        if confianca < self.confianca:
            self.confianca = confianca
        if fonte is FonteMicro.MBP_INFERIDO:
            self.fonte = FonteMicro.MBP_INFERIDO
        self.n_eventos += 1

    def reiniciar(self) -> None:
        """Episódio novo na MESMA chave: cadeia zerada e direito de emitir de
        volta. Não é despejo — a entrada continua no mapa, no mesmo slot."""
        self.confianca = CONFIANCA_OBSERVADO
        self.fonte = FonteMicro.MBO
        self.n_eventos = 0
        self.sinalizado = False

    @property
    def rotulo(self) -> str:
        if self.n_eventos == 0:
            return "DESCONHECIDA"
        return "INFERIDA" if self.fonte is FonteMicro.MBP_INFERIDO else "OBSERVADA"

    def como_evidencia(self) -> dict[str, object]:
        """Publica a cadeia. Com cadeia vazia, `fonte` é `None` — nunca `MBO`.

        `self.fonte` nasce `MBO` porque é o default de `OrdemEvento`, mas com
        `n_eventos == 0` esse valor não foi observado: ninguém o registrou. Ele
        é o default, e default publicado como medição é a mesma mentira que o
        `confianca=1.0` fixo era.
        """
        return {
            "procedencia": self.rotulo,
            "n_eventos_procedencia": self.n_eventos,
            "fonte": self.fonte.value if self.n_eventos else None,
        }


class _MapaProcedencia:
    """Livro-razão de procedência/dedup: expira por TEMPO, teto por segurança.

    ## O defeito que esta estrutura teve, e por que a forma mudou

    A onda 7 tirou daqui um `set` que crescia um item por nível/ordem para
    sempre, e pôs um `OrderedDict` com teto de 4.096 e despejo FIFO pela chave
    menos recentemente alimentada. O vazamento morreu; nasceram dois defeitos,
    medidos em `criticas/nucleo_r4.md` §A.5:

    1. **Penhasco.** Sob rotação cíclica de chaves a vítima do FIFO é sempre
       exatamente a próxima chave a ser revisitada. Medido: **0% de re-emissão
       indevida com 4.096 chaves em rotação, 100% com 5.000.** Não é
       degradação, é um paredão — e o operador o atravessa sem aviso num
       pregão agitado.
    2. **Teto contado em chaves erradas.** Iceberg e Fantasma usavam
       `order_id`, que em modo MBP é SINTÉTICO (~65.000/s). 4.096 chaves eram
       63 ms de memória contra um fenômeno que dura segundos.

    ## As duas respostas

    **(a) A política primária é TEMPO, não contagem.** Uma chave vive enquanto
    o mercado a toca; parada por `janela_episodio_ns`, expira. Esse é o
    critério SEMÂNTICO: o dedup existe para não repetir alerta dentro de um
    episódio, e episódio é uma coisa que dura um tempo — não uma coisa que
    ocupa um dos N slots. Com expiração por tempo o tamanho do mapa se regula
    sozinho na população de chaves VIVAS, que é exatamente o que se queria
    limitar.

    A expiração é preguiçosa (verificada no acesso) mais uma varredura
    incremental de duas posições por chave nova. A preguiçosa sozinha bastaria
    para a CORREÇÃO — chave expirada nunca é lida como válida; a varredura
    existe para a MEMÓRIA, para que o mapa encolha quando o mercado esfria em
    vez de ficar cheio de cadáveres até o teto.

    **(b) O teto continua existindo, mas a vítima é SORTEADA.** Quando mais de
    `limite` chaves estão simultaneamente vivas não existe chave fria a
    preferir: todas foram tocadas dentro da janela. Nesse regime qualquer
    critério determinístico pode entrar em ressonância com o padrão de acesso —
    e o FIFO entra, do pior jeito possível. Sorteando a vítima, a taxa de
    acerto passa a ser ~`limite/N` em vez de zero: degradação suave, sem
    paredão. Perde-se a preferência por chave fria; ganha-se que essa
    preferência passa a ser feita por quem tem a informação certa (o relógio),
    e não pela posição numa fila.

    Consequência aceita e documentada: uma chave pode voltar a emitir — se
    ficou parada uma janela inteira (aí a re-emissão é CORRETA: é episódio
    novo), ou se foi sorteada em regime de excedente (aí é o preço do teto, e o
    teto é `LIMITE_CHAVES_RASTREADAS`, com ordens de grandeza de folga sobre a
    população viva real).

    ## Leitura não renova

    Só `de`/`somar` (ingestão de evento, marcação de `sinalizado`) renovam o
    relógio da chave; `obter` e `rearmar` leem sem renovar. A atividade que
    mantém uma chave viva é o mercado mexer nela, não o detector perguntar por
    ela — se a consulta renovasse, um `verificar` chamado em laço sobre uma
    chave morta a seguraria viva indefinidamente.
    """

    __slots__ = (
        "_limite", "_janela_ns", "_itens", "_chaves", "_agora_ns", "_cursor",
        "_desde_varredura",
    )

    #: Uma posição é varrida a cada N escritas. A varredura tem de existir mesmo
    #: quando NENHUMA chave nova é criada — é o caso em que o mercado esfria com
    #: o mesmo punhado de níveis ativo, e uma varredura presa à inserção nunca
    #: roda: os cadáveres ficam até o teto, que é a forma exata do vazamento que
    #: esta estrutura existe para não ter.
    #:
    #: O orçamento é UMA posição por escrita, paga em RAJADA de
    #: `_ESCRITAS_POR_VARREDURA` a cada `_ESCRITAS_POR_VARREDURA` escritas. O
    #: trabalho total é o mesmo de varrer a cada evento; o que a rajada evita é
    #: a chamada de função por evento, que custava ~2x o caminho quente inteiro
    #: (medido). A rajada é limitada a 8 — continua O(1) por evento, nunca uma
    #: passada O(n) num evento isolado.
    #:
    #: Pagar em rajada não é detalhe: com uma posição por disparo, uma posição
    #: que se revela expirada consome o orçamento inteiro daquele disparo (o
    #: cursor não avança, para reexaminar o slot), e um mapa com 20 mil chaves
    #: mortas levaria 8 x 20.000 escritas para esvaziar em vez de 20.000.
    _ESCRITAS_POR_VARREDURA = 8
    #: Varredura EXTRA na inserção: quem cria chave nova paga a limpeza de mais
    #: duas, de modo que a reclamação acompanhe a taxa de criação. Todas são
    #: O(1) por evento — nunca uma passada O(n) num evento isolado.
    _VARREDURA_POR_INSERCAO = 2

    def __init__(
        self,
        limite: int = LIMITE_CHAVES_RASTREADAS,
        janela_episodio_ns: int = JANELA_EPISODIO_NS,
    ) -> None:
        self._limite = max(1, int(limite))
        self._janela_ns = max(0, int(janela_episodio_ns))
        self._itens: dict[Hashable, _Procedencia] = {}
        self._chaves: list[Hashable] = []
        self._agora_ns = 0
        self._cursor = 0
        self._desde_varredura = 0

    def __len__(self) -> int:
        return len(self._itens)

    @property
    def limite(self) -> int:
        return self._limite

    @property
    def janela_episodio_ns(self) -> int:
        return self._janela_ns

    @property
    def agora_ns(self) -> int:
        """Relógio do mapa: o maior timestamp de evento já visto.

        Monótono de propósito. Um feed que entregue um evento com timestamp
        ATRASADO (reordenação, remendo de gap) não pode fazer o relógio da
        dedup andar para trás e ressuscitar episódios já encerrados.
        """
        return self._agora_ns

    # -- expiração ----------------------------------------------------------
    def _expirado(self, item: _Procedencia) -> bool:
        return self._agora_ns - item.ts_ultimo_ns > self._janela_ns

    def _remover(self, chave: Hashable) -> None:
        """Tira a chave em O(1): troca com a última do vetor e encurta."""
        item = self._itens.pop(chave)
        i = item.pos
        ultima = self._chaves.pop()
        if ultima != chave:
            self._chaves[i] = ultima
            self._itens[ultima].pos = i

    def _varrer(self, quantas: int) -> None:
        """Varredura incremental: olha `quantas` posições e tira as expiradas.

        O cursor é rotativo, então ao longo de N escritas o vetor inteiro é
        visitado — sem nenhuma passada O(n) num único evento (é esse tipo de
        passada que produz pico de latência num evento isolado).

        Ao remover, o cursor NÃO avança: `_remover` traz outra chave para o
        mesmo slot, e essa chave também precisa ser examinada. É o que permite
        a um mapa cheio de cadáveres esvaziar em O(n) escritas em vez de nunca.
        """
        for _ in range(quantas):
            n = len(self._chaves)
            if n == 0:
                return
            i = self._cursor % n
            chave = self._chaves[i]
            if self._expirado(self._itens[chave]):
                self._remover(chave)
                # o slot `i` agora tem OUTRA chave: o cursor não avança, para
                # que ela também seja examinada.
            else:
                self._cursor = i + 1

    def _despejar_sorteado(self) -> None:
        self._remover(self._chaves[_SORTEIO_DESPEJO.randrange(len(self._chaves))])

    # -- API ----------------------------------------------------------------
    def avancar(self, agora_ns: int) -> None:
        """Anda o relógio SEM tocar em chave nenhuma.

        Existe porque a leitura de dedup (`obter`) é feita antes da escrita, e
        ela precisa julgar a expiração pelo instante do evento em curso — não
        pelo do evento anterior. Sem isto um nível sinalizado há uma hora
        continuaria barrando o alerta até que alguma OUTRA chave fizesse o
        relógio andar.
        """
        if agora_ns > self._agora_ns:
            self._agora_ns = agora_ns

    def obter(self, chave: Hashable) -> _Procedencia | None:
        """Leitura pura: não cria, não renova, e chave expirada sai como None.

        Expirada é ausente do ponto de vista de quem lê — se a entrada ainda
        está fisicamente no mapa (a varredura não chegou nela) isso é detalhe
        de memória, não semântica.
        """
        item = self._itens.get(chave)
        if item is None or self._expirado(item):
            return None
        return item

    def de(self, chave: Hashable, agora_ns: int | None = None) -> _Procedencia:
        """Entrada da chave para ESCRITA — cria, renova o relógio e poda."""
        agora = self._agora_ns
        if agora_ns is not None and agora_ns > agora:
            agora = self._agora_ns = agora_ns
        item = self._itens.get(chave)
        if item is not None:
            # Caminho quente: chave viva sendo realimentada. Nada de estrutura,
            # só o relógio dela.
            if agora - item.ts_ultimo_ns > self._janela_ns:
                item.reiniciar()  # mesma chave, episódio novo
            item.ts_ultimo_ns = agora
            # Varredura amortizada, contada aqui em vez de num método: é o
            # caminho quente do pacote inteiro e uma chamada a mais custa mais
            # que o trabalho que ela faz.
            n = self._desde_varredura + 1
            if n >= self._ESCRITAS_POR_VARREDURA:
                self._desde_varredura = 0
                self._varrer(self._ESCRITAS_POR_VARREDURA)
            else:
                self._desde_varredura = n
            return item
        self._varrer(self._VARREDURA_POR_INSERCAO)
        if len(self._chaves) >= self._limite:
            self._despejar_sorteado()
        item = _Procedencia(ts_ultimo_ns=agora, pos=len(self._chaves))
        self._chaves.append(chave)
        self._itens[chave] = item
        return item

    def somar(
        self,
        chave: Hashable,
        confianca: float,
        fonte: FonteMicro,
        agora_ns: int | None = None,
    ) -> _Procedencia:
        item = self.de(chave, agora_ns)
        item.somar(confianca, fonte)
        return item

    def rearmar(self, chave: Hashable) -> None:
        """Desmarca a chave sem apagar a cadeia de procedência nem renovar."""
        item = self._itens.get(chave)
        if item is not None:
            item.sinalizado = False

    def limpar(self) -> None:
        """Esquece tudo, relógio inclusive. Virada de sessão, não caminho quente."""
        self._itens.clear()
        self._chaves.clear()
        self._agora_ns = 0
        self._cursor = 0
        self._desde_varredura = 0


class _DetectorDeLivro:
    """Base dos detectores que leem o `LivroMBO` — carrega a procedência.

    Não é herança por economia de linhas: é o ponto único onde a política de
    combinação (mínimo da cadeia, ver docstring do módulo) fica escrita, para
    que os três detectores não possam divergir dela em silêncio.
    """

    __slots__ = ("_procedencia",)

    def __init__(
        self,
        limite_chaves: int = LIMITE_CHAVES_RASTREADAS,
        janela_episodio_ns: int = JANELA_EPISODIO_NS,
    ) -> None:
        self._procedencia = _MapaProcedencia(limite_chaves, janela_episodio_ns)

    # -- ingestão de procedência -------------------------------------------
    def acompanhar(self, livro: LivroMBO) -> None:
        """Assina o fluxo de eventos do livro. É a fiação recomendada.

        A partir daqui toda detecção deste detector carrega a confiança dos
        `OrdemEvento` que a sustentam, sem o chamador precisar repassar nada.
        """
        livro.assinar_evento(self.observar)

    def observar(self, evento: OrdemEvento) -> None:
        """Registra um `OrdemEvento` na cadeia da chave que ele afeta.

        O `timestamp_ns` do evento é o relógio da dedup — ver `_MapaProcedencia`.
        """
        self._procedencia.somar(
            self._chave_do_evento(evento),
            evento.confianca,
            evento.fonte,
            evento.timestamp_ns,
        )

    def _chave_do_evento(self, evento: OrdemEvento) -> Hashable:
        """Chave de episódio. Os TRÊS detectores de livro usam `(side, price)`.

        A uniformidade é deliberada — ver `criticas/nucleo_r4.md` §A.5. Iceberg
        e Fantasma chaveavam por `order_id`, o que só faria sentido em feed MBO
        real; em modo MBP (o único disponível, porque não há UMDF/ProfitDLL) o
        `order_id` é uma etiqueta que o `InferidorMBP` inventa a cada inserção
        inferida, com rotatividade medida de ~65.000/s. Dedup por uma etiqueta
        que o próprio sistema recicla 65 mil vezes por segundo não deduplica
        nada: a chave morria antes do fenômeno.

        Do ponto de vista do operador o episódio nunca foi a etiqueta. É
        "alguém está recarregando liquidez em 5000,5" ou "liquidez grande
        aparece e some em 5000,5" — um episódio no NÍVEL, independente de
        quantos ids sintéticos a ponte gerou para representá-lo. O `order_id`
        segue publicado na `evidencia` de quem o tem; ele identifica a ordem,
        só não identifica o episódio.
        """
        return (evento.side, evento.price)

    # -- ciclo de vida ------------------------------------------------------
    def iniciar_nova_sessao(self) -> None:
        """Esquece o pregão anterior: cadeia de procedência e dedup zerados.

        Não desassina o livro — a assinatura feita por `acompanhar` é do
        chamador. Quem troca o `LivroMBO` na virada (é o que a app faz, porque
        `n_reposicoes` é acumulado "desde que o nível nasceu") tem de chamar
        `acompanhar` no livro novo, exatamente como na montagem inicial.
        """
        self._procedencia.limpar()

    # -- leitura ------------------------------------------------------------
    @property
    def n_chaves_rastreadas(self) -> int:
        """Tamanho corrente do livro-razão. Existe para o teste de retenção."""
        return len(self._procedencia)

    def esta_sinalizado(self, chave: Hashable) -> bool:
        """A chave já emitiu no episódio corrente? Leitura de dedup.

        Substitui o `chave in detector._ja_sinalizado` que a API antiga
        permitia — existe para que teste e UI leiam o dedup sem alcançar o mapa
        privado, e para que a consulta NÃO renove o relógio da chave (ver
        `_MapaProcedencia`). Chave cujo episódio expirou responde `False`: o
        direito de emitir voltou.
        """
        item = self._procedencia.obter(chave)
        return item is not None and item.sinalizado


# ---------------------------------------------------------------------------
# Absorção
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigAbsorcao:
    """Agressão continuada num preço sem deslocamento além de N ticks."""

    volume_minimo: int = 300
    deslocamento_maximo_ticks: int = 1
    janela_ns: int = 5_000_000_000


@dataclass(slots=True)
class _TradeJanela:
    """Só o que a janela precisa — evita segurar o `Trade` inteiro vivo."""

    seq: int
    timestamp_ns: int
    price: int
    qty: int
    lado: AgressorSide


class DetectorAbsorcao:
    """Absorção de compra: vendedores agridem, preço não cai (e vice-versa).

    Custo: **O(1) amortizado por trade**. Cada trade entra e sai da janela
    `deque` exatamente uma vez, e `volume_buy`/`volume_sell` são contadores
    incrementais — mesmo padrão de `analytics/agressao.py`. Máximo e mínimo de
    preço na janela saem de duas *monotonic deques* (`_max_precos` decrescente,
    `_min_precos` crescente), cada uma com no máximo uma inserção e uma remoção
    amortizada por trade. A implementação anterior refazia cinco varreduras
    completas da janela por trade (expiração + max + min + duas somas), o que a
    5–10 mil trades/s significava 25–50 mil elementos varridos cinco vezes por
    evento: custo total quadrático na taxa do mercado.

    **Retenção.** A janela é podada por TEMPO, não por contagem: o teto é
    `janela_ns × taxa do tape` (a 5 mil trades/s e 5 s de janela, ~25 mil
    `_TradeJanela` — ~2 MB, constante, independente do tamanho do pregão). É um
    teto de verdade, não crescimento: `tests/test_micro_detectores.py::
    test_absorcao_retencao_limitada_pela_janela_de_tempo` processa 200.000
    trades e mede.
    PENDENTE(retenção): um tape com timestamp CONGELADO (feed defeituoso
    repetindo o mesmo `time_msc`) não expira nada e a janela cresce com o
    número de trades. Um teto duro por contagem mudaria a semântica dos
    contadores de volume, então fica registrado em vez de mal-consertado —
    `test_absorcao_janela_cresce_com_timestamp_congelado` documenta o limite.

    **Deduplicação (`_ja_sinalizado`).** Sem ela o detector re-emite o mesmo
    alerta a cada trade enquanto a condição durar — a crítica R1 mediu 98,2% dos
    trades sinalizados num tape lateral. Absorção é um EPISÓDIO (um player
    segurando uma faixa de preço), não um estado instantâneo, então vale um
    alerta por episódio. Aqui basta **um único slot**
    `(lado_absorvedor, preço_âncora)`: a janela deslizante só consegue sustentar
    um episódio por vez. (`DetectorEscora`/`DetectorIcebergPorRecarga` precisam
    de um mapa, porque a chave deles é o nível/a ordem — mas o mapa deles também
    tem teto, ver `_MapaProcedencia`.)

    Regra de rearme — explícita, três gatilhos, todos significando "o episódio
    anterior acabou":

    1. **O preço deslocou** (`deslocamento > deslocamento_maximo_ticks`): a
       própria condição de absorção quebrou — quem estava segurando cedeu ou
       saiu. É o análogo direto do `rearmar` que `DetectorEscora` faz quando
       `n_reposicoes` cai abaixo do mínimo.
    2. **O preço-âncora saiu da faixa da janela**: o mercado migrou para outro
       preço; uma absorção no preço novo é um fenômeno novo, não a repetição
       do antigo.
    3. **A janela esvaziou** (buraco no tape ≥ `janela_ns`, ou virada de lado
       dominante): não há continuidade a preservar.

    Só rearma por evento observado — nunca por decurso de tempo isolado —, de
    modo que um episódio contínuo produz exatamente um alerta.

    Procedência: este detector lê o TAPE (`Trade`), que é impresso pela bolsa e
    portanto observado. Não há cadeia a propagar — `CONFIANCA_OBSERVADO` aqui é
    fato, não default preguiçoso.

    PENDENTE(config): `volume_minimo` é absoluto e, na escala real do WDO
    (~125 mil lotes numa janela de 5s a 5 mil trades/s), o default de 300 é
    ultrapassado 400x e não filtra nada — o limiar deveria ser relativo ao
    volume da janela. Fora do escopo deste conserto (que é custo + dedup); o
    item está no backlog #4 da crítica R1.
    """

    def __init__(self, symbol: str, config: ConfigAbsorcao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigAbsorcao()

        self._janela: deque[_TradeJanela] = deque()
        self._volume_buy = 0
        self._volume_sell = 0
        # Monotonic deques: guardam (seq, price). `_max_precos` é decrescente e
        # `_min_precos` crescente, então o extremo da janela está sempre em [0].
        self._max_precos: deque[tuple[int, int]] = deque()
        self._min_precos: deque[tuple[int, int]] = deque()
        self._seq = 0
        # (lado que absorve, preço no momento do alerta) do episódio em curso.
        self._ja_sinalizado: tuple[Side, int] | None = None

    def iniciar_nova_sessao(self) -> None:
        """Zera a janela e o dedup. O `_seq` também: ele só ordena a janela."""
        self._janela.clear()
        self._max_precos.clear()
        self._min_precos.clear()
        self._volume_buy = 0
        self._volume_sell = 0
        self._seq = 0
        self._ja_sinalizado = None

    @property
    def n_trades_retidos(self) -> int:
        """Tamanho corrente da janela. Existe para o teste de retenção."""
        return len(self._janela)

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config

        seq = self._seq
        self._seq += 1
        self._janela.append(
            _TradeJanela(seq, trade.timestamp_ns, trade.price, trade.qty, trade.side_agressor)
        )
        if trade.side_agressor is AgressorSide.BUY:
            self._volume_buy += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            self._volume_sell += trade.qty

        preco = trade.price
        while self._max_precos and self._max_precos[-1][1] <= preco:
            self._max_precos.pop()
        self._max_precos.append((seq, preco))
        while self._min_precos and self._min_precos[-1][1] >= preco:
            self._min_precos.pop()
        self._min_precos.append((seq, preco))

        self._expirar(trade.timestamp_ns)

        if len(self._janela) == 1:
            # Gatilho 3: a janela esvaziou antes deste trade (buraco no tape
            # maior que a janela) — não há episódio anterior a continuar.
            self._ja_sinalizado = None

        preco_max = self._max_precos[0][1]
        preco_min = self._min_precos[0][1]
        deslocamento = preco_max - preco_min
        if deslocamento > cfg.deslocamento_maximo_ticks:
            # Gatilho 1: o preço deslocou — a condição de absorção quebrou.
            self._ja_sinalizado = None
            return None

        volume_buy = self._volume_buy
        volume_sell = self._volume_sell

        if volume_sell >= cfg.volume_minimo and volume_sell > volume_buy:
            # vendedores agridem, preço não cai → COMPRADOR está absorvendo
            return self._emitir(trade, Side.BUY, volume_sell, volume_buy,
                                deslocamento, preco_min, preco_max)
        if volume_buy >= cfg.volume_minimo and volume_buy > volume_sell:
            return self._emitir(trade, Side.SELL, volume_buy, volume_sell,
                                deslocamento, preco_min, preco_max)
        return None

    def _expirar(self, agora_ns: int) -> None:
        limite = agora_ns - self.config.janela_ns
        janela = self._janela
        while janela and janela[0].timestamp_ns < limite:
            antigo = janela.popleft()
            if antigo.lado is AgressorSide.BUY:
                self._volume_buy -= antigo.qty
            elif antigo.lado is AgressorSide.SELL:
                self._volume_sell -= antigo.qty
            # O extremo só sai da monotonic deque se for justamente este trade.
            if self._max_precos and self._max_precos[0][0] == antigo.seq:
                self._max_precos.popleft()
            if self._min_precos and self._min_precos[0][0] == antigo.seq:
                self._min_precos.popleft()

    def _emitir(
        self,
        trade: Trade,
        side: Side,
        volume_dominante: int,
        volume_oposto: int,
        deslocamento: int,
        preco_min: int,
        preco_max: int,
    ) -> Deteccao | None:
        anterior = self._ja_sinalizado
        if anterior is not None:
            lado_anterior, preco_ancora = anterior
            # Gatilhos 2 e 3: âncora fora da faixa atual, ou o lado que absorve
            # virou — episódio novo, rearma.
            if lado_anterior is not side or not (preco_min <= preco_ancora <= preco_max):
                anterior = None
                self._ja_sinalizado = None
        if anterior is not None:
            return None  # mesmo episódio, já alertado

        self._ja_sinalizado = (side, trade.price)
        return Deteccao(
            timestamp_ns=trade.timestamp_ns,
            symbol=self.symbol,
            tipo=TipoDeteccao.ABSORCAO,
            side=side,
            price=trade.price,
            confianca=CONFIANCA_OBSERVADO,  # tape impresso: fato, não hipótese
            evidencia={
                "volume_agressao_dominante": volume_dominante,
                "volume_lado_oposto": volume_oposto,
                "deslocamento_ticks": deslocamento,
                "n_trades_janela": len(self._janela),
                "procedencia": "OBSERVADA",
                "fonte": FonteMicro.MBO.value,
            },
        )


# ---------------------------------------------------------------------------
# Escora (reposição / defesa de preço)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigEscora:
    n_reposicoes_minimo: int = 3
    #: Backstop de memória: níveis com estado retido (dedup + procedência).
    max_niveis_rastreados: int = LIMITE_CHAVES_RASTREADAS
    #: Quanto tempo um nível parado continua deduplicado. Ver `_MapaProcedencia`.
    janela_episodio_ns: int = JANELA_EPISODIO_NS


class DetectorEscora(_DetectorDeLivro):
    """Nível cuja quantidade é reposta repetidamente após ser consumida.

    **Procedência.** As reposições que sustentam a detecção são `OrdemEvento`
    do nível `(side, price)`; a confiança emitida é o MÍNIMO da cadeia daquele
    nível (ver a docstring do módulo para por que mínimo e não produto/média).
    Ligue com `acompanhar(livro)`, ou passe o evento gatilho em
    `verificar(..., evento=ev)`.

    **Retenção.** O `set` de `_ja_sinalizado` da versão anterior nunca era
    podado: um item por nível de preço que já atingiu o limiar, para sempre
    (defeito apontado pela crítica R2 e repetido na R3, seção C.4). Agora o
    estado vive num `_MapaProcedencia`, que expira por tempo
    (`janela_episodio_ns`) e tem `max_niveis_rastreados` como backstop.

    **Rearme.** Dois caminhos, e os dois precisam existir: `rearmar` explícito
    quando `n_reposicoes` cai abaixo do mínimo (o livro diz que o episódio
    acabou), e a expiração da janela quando o nível simplesmente para de dar
    sinal (o livro não diz nada, e silêncio prolongado também encerra
    episódio).
    """

    __slots__ = ("config",)

    def __init__(self, config: ConfigEscora | None = None) -> None:
        cfg = config if config is not None else ConfigEscora()
        super().__init__(cfg.max_niveis_rastreados, cfg.janela_episodio_ns)
        self.config = cfg

    def verificar(
        self,
        livro: LivroMBO,
        side: Side,
        price: int,
        timestamp_ns: int,
        evento: OrdemEvento | None = None,
    ) -> Deteccao | None:
        if evento is not None:
            self.observar(evento)
        n_reposicoes = livro.n_reposicoes(side, price)
        chave = (side, price)
        if n_reposicoes < self.config.n_reposicoes_minimo:
            # Rearma o nível sem apagar a cadeia de procedência: o contador de
            # reposições do livro é cumulativo, então o que muda aqui é só o
            # direito de emitir de novo.
            self._procedencia.rearmar(chave)
            return None
        proc = self._procedencia.de(chave, timestamp_ns)
        if proc.sinalizado:
            return None  # já emitido para este nível — evita repetir a cada tick
        proc.sinalizado = True
        evidencia: dict[str, object] = {
            "n_reposicoes": n_reposicoes,
            "qty_total_atual": livro.qty_total(side, price),
        }
        evidencia.update(proc.como_evidencia())
        return Deteccao(
            timestamp_ns=timestamp_ns,
            symbol=livro.symbol,
            tipo=TipoDeteccao.ESCORA,
            side=side,
            price=price,
            confianca=proc.confianca,
            evidencia=evidencia,
        )


# ---------------------------------------------------------------------------
# Iceberg
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigIceberg:
    razao_minima: float = 3.0
    volume_executado_minimo: int = 200
    #: Backstop de memória: níveis `(side, price)` com estado retido. O nome
    #: fala em "ordens" por compatibilidade com quem já configura isto; a
    #: chave deixou de ser `order_id` (ver `_chave_do_evento`).
    max_ordens_rastreadas: int = LIMITE_CHAVES_RASTREADAS
    #: Duração do episódio de iceberg: recargas separadas por menos que isso
    #: são o MESMO episódio e valem um alerta só. 30 s cobre com folga o
    #: intervalo entre recargas medido; é este número, e não uma contagem de
    #: chaves, que define a memória do detector.
    janela_episodio_ns: int = JANELA_EPISODIO_NS


# DELETADO: `DetectorIceberg` (proxy por nível de preço).
#
# Ele calculava `executado_estimado = n_reposicoes * qty_exibida_max` e depois
# `razao = executado_estimado / qty_exibida_max`. O `qty_exibida_max` CANCELA:
# a razão era identicamente `n_reposicoes`. Consequências, todas verificadas
# em execução pela crítica R1 (seção 5.1):
#
# 1. A grandeza anunciada pela docstring — "executa muito mais volume do que a
#    quantidade exibida" — era a única que a fórmula garantidamente ignorava:
#    um nível exibindo 10 lotes e outro exibindo 5.000 recebiam a mesma razão.
# 2. `razao_minima=3.0` virava, na prática, `n_reposicoes >= 3` — literalmente
#    o gatilho de `DetectorEscora` (`n_reposicoes_minimo=3`). A mesma sequência
#    emitia ICEBERG e ESCORA, e o operador lia isso como confluência.
# 3. `evidencia["volume_executado_estimado"]` publicava um número fabricado com
#    nome de medição: `n_reposicoes` conta ORDENS NOVAS que chegaram depois de
#    o nível ser varrido, não contratos executados. Num dicionário chamado
#    `evidencia`, cuja finalidade declarada é permitir auditoria, isso enganava
#    o auditor. Confiança 0.6 não conserta um número que mede outra coisa.
#
# A opção "consertar em vez de deletar" exigiria o volume REALMENTE executado
# por nível. Esse número existe (`_NivelInterno.consumido_acumulado`), mas é
# privado: `LivroMBO` expõe `qty_total`, `n_reposicoes` e `qty_exibida_max` e
# nada mais.
#
# PENDENTE(livro): para reconstruir um iceberg por NÍVEL (o único caminho em
# feed agregado, onde não há `order_id` e portanto não há `n_recargas`),
# `LivroMBO` precisa expor `consumido_acumulado(side, price) -> int`. Com ele a
# razão honesta é `consumido_acumulado / qty_exibida_max`, e aí sim o tamanho
# exibido entra na conta. Enquanto não existir, este arquivo NÃO tem como medir
# o fenômeno por nível — e um detector que não mede o que diz medir é pior que
# detector nenhum, porque consome a atenção do operador com falsa confluência.
#
# Fica de pé apenas `DetectorIcebergPorRecarga`, que é honesto: mede
# `Ordem.qty_executada` contra `Ordem.qty_original` e EXIGE `n_recargas > 0`
# observada. Ele só funciona em feed MBO real — o que é a verdade, não uma
# limitação a ser disfarçada por proxy.


class DetectorIcebergPorRecarga(_DetectorDeLivro):
    """Versão observada (feed MBO real): usa `Ordem.n_recargas`, não proxy.

    É o único detector de iceberg do módulo. A recarga observada — mesma
    `order_id` sendo reabastecida — é a assinatura do fenômeno; sem ela, uma
    execução grande é só uma ordem grande. Por isso `n_recargas == 0` barra a
    emissão mesmo quando a razão executado/exibido é alta: essa combinação é
    alcançável (ex.: `LivroMBO.modificar` para cima recria a `Ordem` com
    `qty_original` novo e `qty_executada` herdado) e NÃO é iceberg.

    **Procedência e dedup são por `(side, price)`, não por `order_id`.** Era
    por `order_id` até a crítica R4 (§A.5) medir a consequência: em modo MBP o
    `order_id` é sintético e o `InferidorMBP` cria ~65.000 por segundo, então
    a memória do detector durava 63 ms contra um iceberg que recarrega por
    segundos — cada recarga virava episódio novo e o alerta se repetia. O
    episódio que o operador enxerga é "estão recarregando em 5000,5"; a cadeia
    de procedência do NÍVEL é também a cadeia certa, porque é ela que junta as
    recargas e as execuções que formam a razão. O `order_id` continua na
    `evidencia`.

    **Retenção.** O `set[str]` de `order_id` sinalizados crescia um item por
    ordem sinalizada e nunca era podado. Agora vive no `_MapaProcedencia`, que
    expira por `janela_episodio_ns` e usa `max_ordens_rastreadas` de backstop.
    """

    __slots__ = ("config",)

    def __init__(self, config: ConfigIceberg | None = None) -> None:
        cfg = config if config is not None else ConfigIceberg()
        super().__init__(cfg.max_ordens_rastreadas, cfg.janela_episodio_ns)
        self.config = cfg

    def verificar(
        self,
        ordem: Ordem,
        symbol: str,
        timestamp_ns: int,
        evento: OrdemEvento | None = None,
    ) -> Deteccao | None:
        if evento is not None:
            self.observar(evento)
        self._procedencia.avancar(timestamp_ns)
        chave = (ordem.side, ordem.price)
        proc_existente = self._procedencia.obter(chave)
        if proc_existente is not None and proc_existente.sinalizado:
            return None
        volume_executado = ordem.qty_executada
        if volume_executado < self.config.volume_executado_minimo:
            return None
        base = ordem.qty_original if ordem.qty_original > 0 else 1
        razao = volume_executado / base
        if ordem.n_recargas == 0 or razao < self.config.razao_minima:
            return None
        proc = self._procedencia.de(chave, timestamp_ns)
        proc.sinalizado = True
        evidencia: dict[str, object] = {
            "order_id": ordem.order_id,
            "qty_original": ordem.qty_original,
            "qty_executada": volume_executado,
            "n_recargas": ordem.n_recargas,
            "razao": razao,
        }
        evidencia.update(proc.como_evidencia())
        return Deteccao(
            timestamp_ns=timestamp_ns,
            symbol=symbol,
            tipo=TipoDeteccao.ICEBERG,
            side=ordem.side,
            price=ordem.price,
            confianca=proc.confianca,
            evidencia=evidencia,
        )


# ---------------------------------------------------------------------------
# Liquidez fantasma (retirada antes da execução, sem julgar intenção)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigLiquidezFantasma:
    qty_minima: int = 200
    vida_maxima_ns: int = 1_000_000_000
    ticks_proximidade: int = 2
    #: Backstop de memória: níveis `(side, price)` com estado retido. Nome
    #: mantido por compatibilidade; a chave deixou de ser `order_id`.
    max_ordens_rastreadas: int = LIMITE_CHAVES_RASTREADAS
    #: Duração do episódio. Liquidez grande que aparece e some repetidamente
    #: no MESMO nível dentro desta janela é um episódio só — que é como o
    #: operador lê o fenômeno, e não uma ordem de cada vez.
    janela_episodio_ns: int = JANELA_EPISODIO_NS


class DetectorLiquidezFantasma(_DetectorDeLivro):
    """Quantidade grande que aparece e some sem executar, perto do preço.

    Termo deliberadamente neutro — o código só observa retirada rápida sem
    execução; não afirma intenção nem usa a palavra "spoof".

    **Procedência.** A cadeia é do nível `(side, price)`: as entradas e as
    retiradas que passaram por ele. Em livro inferido cada uma dessas é
    hipótese do `InferidorMBP` (foi cancelamento ou foi execução que não
    vimos?), e é exatamente essa dúvida que a confiança emitida precisa
    carregar.

    **Dedup por episódio — por NÍVEL, não por ordem.** Chavear por `order_id`
    dava dedup perfeito para a mesma `Ordem` e nenhum para o fenômeno: em modo
    MBP a mesma liquidez aparecendo e sumindo dez vezes em 5000,5 chega como
    dez `order_id` sintéticos distintos e produzia dez alertas. Pior, com o
    teto antigo (4.096 chaves contra ~65.000 ids novos por segundo) nem a
    repetição da mesma ordem era barrada por muito tempo. A chave agora é o
    nível e a memória é a `janela_episodio_ns`.
    """

    __slots__ = ("config", "_tick_size")

    def __init__(
        self, grid_tick_size: float, config: ConfigLiquidezFantasma | None = None
    ) -> None:
        cfg = config if config is not None else ConfigLiquidezFantasma()
        super().__init__(cfg.max_ordens_rastreadas, cfg.janela_episodio_ns)
        self.config = cfg
        self._tick_size = grid_tick_size

    def verificar(
        self,
        ordem: Ordem,
        symbol: str,
        melhor_preco_oposto: int | None,
        evento: OrdemEvento | None = None,
    ) -> Deteccao | None:
        if evento is not None:
            self.observar(evento)
        cfg = self.config
        if ordem.ativa or ordem.qty_executada > 0:
            return None  # se executou nada, não é o fenômeno buscado
        if ordem.qty_original < cfg.qty_minima:
            return None
        if ordem.timestamp_saida_ns is None:
            return None
        # O relógio da dedup é o instante do fenômeno, e tem de andar ANTES da
        # leitura do dedup — senão a expiração é julgada pelo evento anterior.
        # As guardas acima vêm primeiro de propósito: são baratas e não mexem
        # em estado, então uma `Ordem` que nem é candidata não move o relógio.
        self._procedencia.avancar(ordem.timestamp_saida_ns)
        chave = (ordem.side, ordem.price)
        proc_existente = self._procedencia.obter(chave)
        if proc_existente is not None and proc_existente.sinalizado:
            return None
        vida_ns = ordem.timestamp_saida_ns - ordem.timestamp_entrada_ns
        if vida_ns > cfg.vida_maxima_ns:
            return None
        if melhor_preco_oposto is not None:
            distancia_ticks = abs(ordem.price - melhor_preco_oposto)
            if distancia_ticks > cfg.ticks_proximidade:
                return None
        proc = self._procedencia.de(chave, ordem.timestamp_saida_ns)
        proc.sinalizado = True
        evidencia: dict[str, object] = {
            "order_id": ordem.order_id,
            "qty_original": ordem.qty_original,
            "vida_ns": vida_ns,
        }
        evidencia.update(proc.como_evidencia())
        return Deteccao(
            timestamp_ns=ordem.timestamp_saida_ns,
            symbol=symbol,
            tipo=TipoDeteccao.LIQUIDEZ_FANTASMA,
            side=ordem.side,
            price=ordem.price,
            confianca=proc.confianca,
            evidencia=evidencia,
        )


# ---------------------------------------------------------------------------
# Exaustão
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigExaustao:
    n_trades_janela: int = 9
    """Negocios na janela. **Era 5, e 5 tornava a propria regra impossivel.**

    O corpo calcula `terco = max(1, n_trades_janela // 3)`. Com 5, isso da
    `5 // 3 = 1`: o detector diz comparar "ultimo terco vs primeiro terco" e
    compara UM negocio contra UM negocio. Um lote grande seguido de um pequeno
    dispara — o que num tape real acontece o tempo todo.

    Nao era limiar frouxo. Era a regra documentada nao tendo como rodar.

    Medido sobre tres pregoes reais (13, 14 e 21/08/2026, WDOU26):

    | config                | exaustoes | share  | det/min | sinais |
    |---|---|---|---|---|
    | 5 trades, queda 0,40  |    24.602 | 78,9%  |    18,2 | 458 |
    | 5 trades, queda 0,75  |    18.134 | 73,4%  |    14,5 | 458 |
    | **9 trades, queda 0,40** | **9.246** | **58,5%** | **9,3** | 458 |
    | 15 trades, queda 0,60 |     3.005 | 31,4%  |     5,6 | 458 |

    Duas leituras da tabela:

    * **O tamanho da janela e a alavanca; o limiar de volume nao.** Passar de 5
      para 9 corta 62% das emissoes; endurecer a queda de 0,40 para 0,75 corta
      26%. Faz sentido: o limiar nao conserta uma comparacao entre duas
      amostras de tamanho 1.
    * **A coluna de sinais nao se move.** 458 sinais e 133 confirmados nas seis
      configuracoes. Exaustao nao alimenta a confluencia do motor — coerente
      com ela ser `AUSENTE_NA_FONTE` no registro da metodologia. Mexer aqui
      muda o que a tela MOSTRA, e nao o que o produto DECIDE.

    Nove, e nao quinze: nove e o menor valor em que o terco vira tres negocios,
    que e o minimo para "volume caindo ao longo da janela" ser uma tendencia em
    vez de uma diferenca entre dois lotes. Quinze reduz mais, e reduziria por
    filtrar fenomeno de verdade — nao ha nada na fonte que justifique.
    """

    queda_volume_minima: float = 0.4
    """Queda minima do ultimo terco em relacao ao primeiro.

    Continua 0,4: a varredura acima mostra que este e o parametro FRACO, e
    nao ha nada na fonte que sustente outro numero — `exaustao.conceito` esta
    marcada `AUSENTE_NA_FONTE` em `metodologia/regras.py`. Mudar por gosto
    seria cravar constante sem procedencia, que e exatamente o que este
    projeto nao faz.
    """


class DetectorExaustao:
    """Agressão de um lado com volume decrescente e sem progresso de preço.

    **Retenção — o defeito que este detector tinha.** `self._trades` era uma
    `list` com `append` e NENHUMA poda, enquanto o corpo só lia
    `self._trades[-n_trades_janela:]`. Todo trade do pregão ficava vivo para
    que 5 fossem usados: 200.000 trades entravam, 200.000 ficavam retidos; a
    5.000 trades/s por 6 horas isso é ~108 milhões de objetos `Trade`
    referenciados por um detector que precisa de cinco. O padrão certo já
    estava 60 linhas abaixo, em `DetectorClipInstitucional`. Agora a janela é
    `deque(maxlen=n_trades_janela)` — dimensionada pela config, não por
    constante — e o `deque` também elimina a cópia por fatia que o corpo fazia
    a cada trade.

    **Deduplicação por episódio** (mesmo padrão de `DetectorAbsorcao`, com a
    regra de rearme escrita). Sem ela o detector disparava 2–3 vezes no mesmo
    preço dentro de 30 ms: cada trade novo que mantivesse a condição gerava um
    alerta. Exaustão é um EPISÓDIO (um lado agredindo cada vez menos sem tirar
    o preço do lugar), então vale um alerta por episódio, guardado num único
    slot `(lado, preço_âncora)` — a janela por contagem só sustenta um episódio
    por vez.

    Regra de rearme — três gatilhos, todos significando "o episódio acabou":

    1. **A continuidade quebrou**: entrou na janela um trade de lado diferente
       (ou `UNKNOWN`). A agressão de um lado só, que é a premissa do fenômeno,
       deixou de existir.
    2. **O preço progrediu dentro da janela** (`preco_fim != preco_inicio`): a
       condição de exaustão quebrou — quem agredia conseguiu andar. É o análogo
       exato do gatilho 1 de `DetectorAbsorcao` (o deslocamento).
    3. **O lado ou o preço-âncora mudaram** em relação ao alerta anterior:
       exaustão de outro lado, ou no preço vizinho, é fenômeno novo.

    Diferente de `DetectorAbsorcao`, NÃO há gatilho de "janela esvaziou": esta
    janela é por CONTAGEM, não por tempo, e nunca esvazia sozinha. O análogo é
    o gatilho 1. Queda de volume abaixo do limiar NÃO rearma — mesmo critério
    da absorção, onde volume abaixo do mínimo também não rearma: a condição
    afrouxou, o episódio não terminou.

    **Os três gatilhos são independentes — o 3 não é redundante.** Parece que
    toda mudança de âncora teria de passar antes pelo gatilho 1 ou 2, e não
    passa: `progrediu` compara as PONTAS da janela (`janela[0]` × `janela[-1]`),
    não o intervalo. Um tape cujo preço sai de 5002, passa por 5003 no meio e
    volta a 5002 nas pontas tem `progrediu == False`, e a âncora migra sem o
    gatilho 2 ver. Medido: num fuzz de 23.308 emissões, 914 chegaram ao gatilho
    3 com `_ja_sinalizado` não-nulo e âncora diferente. Preso por
    `test_exaustao_gatilho_3_dispara_com_a_janela_de_pontas_iguais` (e pelo
    controle logo abaixo dele) — a auto-mutação `if False:` na comparação de
    âncora sobrevivia a todos os outros testes de exaustão.

    PENDENTE(sensibilidade): que `progrediu` olhe só as pontas é uma escolha
    herdada, não medida. Um critério por AMPLITUDE da janela (máximo − mínimo,
    como o `deslocamento` de `DetectorAbsorcao`) seria mais fiel a "o preço
    andou" e reduziria emissões em tape oscilante. Trocar muda a taxa de
    detecção do produto, então fica registrado em vez de alterado de passagem.

    Procedência: lê o TAPE, que é observado. `CONFIANCA_OBSERVADO` aqui é fato.
    """

    def __init__(self, symbol: str, config: ConfigExaustao | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigExaustao()
        # maxlen pela config: a janela retém exatamente o que lê, nunca o
        # pregão inteiro.
        self._trades: deque[Trade] = deque(maxlen=max(1, self.config.n_trades_janela))
        # (lado agressor, preço-âncora) do episódio já alertado.
        self._ja_sinalizado: tuple[Side, int] | None = None

    def iniciar_nova_sessao(self) -> None:
        """Zera a janela e o dedup — o dia 2 não continua o episódio do dia 1."""
        self._trades.clear()
        self._ja_sinalizado = None

    @property
    def n_trades_retidos(self) -> int:
        """Tamanho corrente da janela. Existe para o teste de retenção."""
        return len(self._trades)

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        self._trades.append(trade)
        janela = self._trades
        n = len(janela)
        if n < cfg.n_trades_janela:
            return None
        lado = janela[0].side_agressor
        if any(t.side_agressor is not lado for t in janela) or lado.name == "UNKNOWN":
            # Gatilho 1: a agressão de lado único quebrou — episódio encerrado.
            self._ja_sinalizado = None
            return None

        terco = max(1, cfg.n_trades_janela // 3)
        vol_inicio = sum(t.qty for t in islice(janela, 0, terco))
        vol_fim = sum(t.qty for t in islice(janela, n - terco, n))
        if vol_inicio == 0:
            return None
        queda = 1.0 - (vol_fim / vol_inicio)
        preco_inicio = janela[0].price
        preco_fim = janela[-1].price
        progrediu = preco_fim != preco_inicio
        if progrediu:
            # Gatilho 2: o preço andou — a condição de exaustão quebrou.
            self._ja_sinalizado = None
            return None

        if queda >= cfg.queda_volume_minima:
            side = Side.BUY if lado.name == "BUY" else Side.SELL
            anterior = self._ja_sinalizado
            if anterior is not None and (anterior[0] is not side or anterior[1] != preco_fim):
                # Gatilho 3: lado ou preço-âncora novos — episódio novo.
                anterior = None
            if anterior is not None:
                return None  # mesmo episódio, já alertado
            self._ja_sinalizado = (side, preco_fim)
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.EXAUSTAO,
                side=side,
                price=preco_fim,
                confianca=CONFIANCA_OBSERVADO,  # tape impresso: fato
                evidencia={
                    "volume_inicio_janela": vol_inicio,
                    "volume_fim_janela": vol_fim,
                    "queda_relativa": queda,
                    "preco_moveu": progrediu,
                    "procedencia": "OBSERVADA",
                    "fonte": FonteMicro.MBO.value,
                },
            )
        return None


# ---------------------------------------------------------------------------
# Clip institucional / algoritmo (TWAP/POV)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConfigClipInstitucional:
    n_trades_minimo: int = 5
    cv_qty_maximo: float = 0.15  # coeficiente de variação (desvio/média)
    cv_intervalo_maximo: float = 0.30


class DetectorClipInstitucional:
    """Sequência de trades de tamanho e intervalo regulares (assinatura TWAP/POV).

    Retenção: `deque(maxlen=n_trades_minimo)` — o `pop(0)` da versão anterior
    já mantinha a janela no tamanho certo (era daqui que o padrão correto
    deveria ter sido copiado para `DetectorExaustao`), mas era O(n) por trade e
    dependia de uma comparação de tamanho no corpo. O `maxlen` faz a poda ser
    estrutural: não existe caminho de código que a esqueça.

    Dedup: o flag `_ja_sinalizado_janela` já era por JANELA (um alerta por
    conjunto de N trades) e continua com a mesma semântica — rearma exatamente
    quando a janela estava cheia e um trade novo empurrou o mais antigo para
    fora.
    """

    def __init__(self, symbol: str, config: ConfigClipInstitucional | None = None) -> None:
        self.symbol = symbol
        self.config = config if config is not None else ConfigClipInstitucional()
        self._trades: deque[Trade] = deque(maxlen=max(1, self.config.n_trades_minimo))
        self._ja_sinalizado_janela: bool = False

    def iniciar_nova_sessao(self) -> None:
        """Zera a janela e o dedup por janela."""
        self._trades.clear()
        self._ja_sinalizado_janela = False

    @property
    def n_trades_retidos(self) -> int:
        """Tamanho corrente da janela. Existe para o teste de retenção."""
        return len(self._trades)

    @staticmethod
    def _cv(valores: list[float]) -> float:
        n = len(valores)
        media = sum(valores) / n
        if media == 0:
            return float("inf")
        variancia = sum((v - media) ** 2 for v in valores) / n
        return (variancia ** 0.5) / media

    def ao_trade(self, trade: Trade) -> Deteccao | None:
        if trade.symbol != self.symbol:
            return None
        cfg = self.config
        # A janela já estava cheia? Então este trade EXPULSA o mais antigo e a
        # janela passa a ser outra — mesmo ponto em que o `pop(0)` rearmava.
        estava_cheia = len(self._trades) == self._trades.maxlen
        self._trades.append(trade)
        if estava_cheia:
            self._ja_sinalizado_janela = False
        if len(self._trades) < cfg.n_trades_minimo:
            return None
        if self._ja_sinalizado_janela:
            return None

        qtys = [float(t.qty) for t in self._trades]
        intervalos = [
            float(self._trades[i].timestamp_ns - self._trades[i - 1].timestamp_ns)
            for i in range(1, len(self._trades))
        ]
        cv_qty = self._cv(qtys)
        cv_intervalo = self._cv(intervalos) if intervalos else float("inf")

        if cv_qty <= cfg.cv_qty_maximo and cv_intervalo <= cfg.cv_intervalo_maximo:
            self._ja_sinalizado_janela = True
            return Deteccao(
                timestamp_ns=trade.timestamp_ns,
                symbol=self.symbol,
                tipo=TipoDeteccao.CLIP_INSTITUCIONAL,
                side=Side.BUY if trade.side_agressor.name == "BUY" else Side.SELL,
                price=trade.price,
                confianca=CONFIANCA_OBSERVADO,  # tape impresso: fato
                evidencia={
                    "cv_quantidade": cv_qty,
                    "cv_intervalo": cv_intervalo,
                    "n_trades": len(self._trades),
                    "qty_media": sum(qtys) / len(qtys),
                    "procedencia": "OBSERVADA",
                    "fonte": FonteMicro.MBO.value,
                },
            )
        return None
