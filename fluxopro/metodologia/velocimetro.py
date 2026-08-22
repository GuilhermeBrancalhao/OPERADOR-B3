"""Velocímetro — momentum dos contadores de contexto, normalizado.

O que a fonte diz (`ferramenta_componentes.md` §3, vídeo `w8YGyNl5m24`):

    "535, ó, 537, 541... ela não tá perdendo o sinal"     (CONFIRMADO)
    "tá 410, 389, 300... ela virou"                        (CONFIRMADO)

"Acelerar" ali é a variação do VALOR de um contador de fluxo de curto prazo ao
longo do tempo — não velocidade de negócios. Os dois eixos que o autor trata
são **grandeza** (magnitude) e **manutenção** (não perder o sinal), e este
componente publica os dois separados, nunca fundidos num número só.

## A regra que este módulo RECUSA implementar

`regras.REGRAS["velocimetro.escala_fixa"]` está rotulada **AUSENTE NA FONTE**:
não existe limiar absoluto do tipo "acima de 250 = forte". Os números citados
(400, 600, 1200, 1900) variam por dia e por ativo, e a própria pesquisa
desmente a tabela fixa que uma extração anterior havia inventado.

Consequência de projeto, verificável: **não há nenhuma constante de magnitude
neste arquivo.** A leitura é invariante a escala — multiplicar todo o fluxo do
dia por 10 produz exatamente a mesma sequência de estados. `tests/` afirma
isso, e é a asserção que impede alguém de reintroduzir um "250" mais tarde.

## O caso WINFUT, que é o motivo de o componente existir

`ferramenta_componentes.md` §7, `kzvx33vruic`: a macro passou o pregão em
−1500/−1735/−1925, inverteu para +915 e "em poucos minutos ele praticamente
retrocede tudo" (CONFIRMADO). Ler o valor instantâneo teria dado compra. A
conclusão da pesquisa é literal: normalizar por **(a) magnitude relativa ao
histórico intradiário** e **(b) persistência temporal**.

Aqui isso é:

- (a) `magnitude_relativa = |variacao| / referencia`, onde `referencia` é a
  **K-ésima maior** magnitude já amostrada na sessão (min-heap de tamanho K).
  K−1 outliers — leilão de abertura, um burst isolado — não levantam a
  referência sozinhos. Antes de K amostras a referência é o MÁXIMO da sessão,
  a leitura mais conservadora possível (a razão nunca passa de 1,0).
- (b) `persistencia_ns` e `persistencia_amostras`: há quanto tempo o sentido
  não muda. Um sinal forte que dura segundos e um moderado que persiste têm
  números diferentes — e ficam em campos diferentes, para que a decisão de
  qual pesa mais seja de quem lê, não deste módulo.

`motor/sinais.py` resolve uma versão mais dura do mesmo problema (referência
em janela móvel de blocos, para separar *episódio* de *regime*). Aqui a
referência é da sessão inteira, deliberadamente mais simples: o velocímetro é
leitura de curto prazo e não porta de entrada, então uma referência que só
sobe é conservadora — no máximo cala, nunca autoriza.

## Estado

`JanelaMovel` (anel de `n_baldes` inteiros) + um heap de no máximo K inteiros
+ seis escalares. `len` limitado por `n_baldes` e por `tamanho_topo_magnitude`,
os dois constantes de configuração. Nada indexado por evento — critério de
`fluxopro/gravacao/gravador.py`. A amostragem da referência acontece **uma vez
por rolagem de balde**, não por trade: a taxa de amostragem é limitada pelo
relógio, não pela taxa do mercado.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Side
from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.janela import JanelaMovel
from fluxopro.metodologia.regras import regras_de


@unique
class EstadoVelocimetro(Enum):
    """Os estados que a fonte nomeia, mais os dois que ela exige por omissão."""

    SEM_DADOS = "SEM_DADOS"
    """Ainda não há referência de magnitude — a sessão mal começou."""

    PARADO = "PARADO"
    """Sem sentido definido, ou magnitude pequena demais perto do histórico
    do próprio dia. É o estado que o repique do WINFUT recebe."""

    ACELERANDO = "ACELERANDO"
    """Renovando o valor no mesmo sentido: "537, 541... não tá perdendo"."""

    MANTENDO = "MANTENDO"
    """Mesmo sentido, magnitude estável dentro da banda de tolerância."""

    DESACELERANDO = "DESACELERANDO"
    """"Perde força" — o análogo de tirar o pé do acelerador."""

    VIROU = "VIROU"
    """O sentido inverteu: "410, 389, 300... ela virou"."""


@dataclass(frozen=True, slots=True)
class ConfigVelocimetro:
    """Ver `regras.parametros_de("ConfigVelocimetro")`. Nenhum valor absoluto
    de magnitude aqui — a fonte não tem nenhum para copiar."""

    janela_ns: int = 15_000_000_000
    """Janela da "micro". AUSENTE NA FONTE (`macro_micro.janela_micro`)."""

    n_baldes: int = 8
    """Resolução do anel. Engenharia pura: define o erro do lookback."""

    tolerancia_variacao: float = 0.10
    """Banda morta entre ACELERANDO e DESACELERANDO, em fração. É relativa,
    não absoluta — de propósito: um corte absoluto seria a escala fixa que a
    fonte não tem."""

    magnitude_relativa_minima: float = 0.25
    """Abaixo disso a leitura é PARADO, por mais direcional que pareça. É o
    gate do caso WINFUT."""

    tamanho_topo_magnitude: int = 16
    """K da referência: a K-ésima maior magnitude da sessão."""

    minimo_amostras_referencia: int = 16
    """Antes disso a referência é o máximo da sessão (conservador)."""


@dataclass(frozen=True, slots=True)
class LeituraVelocimetro:
    """Os dois eixos da fonte — grandeza e manutenção — em campos separados."""

    timestamp_ns: int
    valor: int
    """Valor corrente do contador de contexto alimentado."""

    variacao: int
    """Quanto o contador andou na janela. Sempre `int`."""

    sentido: Side | None
    estado: EstadoVelocimetro

    magnitude_relativa: float | None
    """|variacao| dividido pela referência da sessão. `None` enquanto não há
    referência. **Este é o eixo (a) do caso WINFUT.**"""

    referencia_magnitude: int | None
    magnitude_pico_sessao: int

    persistencia_ns: int
    """Há quanto tempo o sentido não muda. **Eixo (b) do caso WINFUT.**"""

    persistencia_amostras: int

    duracao_janela_ns: int
    """Lookback REAL desta leitura (a janela de baldes é aproximada)."""

    amostras_janela: int
    regras: tuple[RegraDocumentada, ...] = field(default=())


_REGRAS = regras_de(
    "velocimetro.dois_eixos",
    "velocimetro.virada",
    "velocimetro.escala_fixa",
    "velocimetro.normalizacao_winfut",
)


class Velocimetro:
    """Momentum de um contador acumulado, com os dois eixos do caso WINFUT."""

    __slots__ = (
        "config",
        "_janela",
        "_topo",
        "_amostras_total",
        "_max_sessao",
        "_variacao_ref",
        "_variacao_anterior",
        "_sentido_persistente",
        "_persistencia_desde_ns",
        "_persistencia_amostras",
    )

    def __init__(self, config: ConfigVelocimetro | None = None) -> None:
        self.config = config or ConfigVelocimetro()
        if self.config.tamanho_topo_magnitude < 1:
            raise ValueError("tamanho_topo_magnitude deve ser >= 1")
        self._janela = JanelaMovel(self.config.janela_ns, self.config.n_baldes)
        self._topo: list[int] = []  # min-heap, len <= K por construcao
        self._amostras_total = 0
        self._max_sessao = 0
        self._variacao_ref = 0
        self._variacao_anterior = 0
        self._sentido_persistente: Side | None = None
        self._persistencia_desde_ns = 0
        self._persistencia_amostras = 0

    # ------------------------------------------------------------------
    def registrar(self, timestamp_ns: int, valor_acumulado: int) -> LeituraVelocimetro:
        """Alimenta o valor CORRENTE de um contador acumulado da sessão.

        Tipicamente `CumulativeDelta.delta_sessao`. O contador tem de valer 0
        no início da sessão (ver `JanelaMovel`).
        """
        if not isinstance(valor_acumulado, int) or isinstance(valor_acumulado, bool):
            raise TypeError("valor_acumulado deve ser int")

        balde_antes = self._janela.indice_balde
        self._janela.registrar(timestamp_ns, valor_acumulado)
        balde_agora = self._janela.indice_balde

        variacao = self._janela.variacao
        magnitude = abs(variacao)

        # Amostragem da referencia: UMA por rolagem de balde. Nao por trade —
        # senao a taxa do mercado, e nao o relogio, decidiria o peso de cada
        # instante na cauda.
        #
        # `_variacao_anterior` guarda a magnitude da janela UMA ROLAGEM ATRAS, e
        # e contra ela que o estado compara. Comparar contra o valor da rolagem
        # CORRENTE seria comparar a janela consigo mesma: o estado nunca sairia
        # de MANTENDO e uma virada de sentido jamais apareceria.
        if balde_antes is None:
            self._variacao_ref = variacao
        elif balde_agora != balde_antes:
            self._amostrar(abs(self._variacao_ref))
            self._variacao_anterior = self._variacao_ref
            self._variacao_ref = variacao

        referencia = self._referencia()
        relativa = (
            magnitude / referencia if referencia is not None and referencia > 0 else None
        )

        sentido = _sentido_de(variacao)
        self._atualizar_persistencia(sentido, timestamp_ns)

        estado = self._estado(sentido, magnitude, relativa)

        return LeituraVelocimetro(
            timestamp_ns=timestamp_ns,
            valor=valor_acumulado,
            variacao=variacao,
            sentido=sentido,
            estado=estado,
            magnitude_relativa=relativa,
            referencia_magnitude=referencia,
            magnitude_pico_sessao=self._max_sessao,
            persistencia_ns=max(0, timestamp_ns - self._persistencia_desde_ns),
            persistencia_amostras=self._persistencia_amostras,
            duracao_janela_ns=self._janela.duracao_ns,
            amostras_janela=self._janela.amostras,
            regras=_REGRAS,
        )

    # ------------------------------------------------------------------
    def _amostrar(self, magnitude: int) -> None:
        """Min-heap de tamanho FIXO K. `len(self._topo) <= K` por construção."""
        if magnitude <= 0:
            return
        self._amostras_total += 1
        self._max_sessao = max(self._max_sessao, magnitude)
        k = self.config.tamanho_topo_magnitude
        if len(self._topo) < k:
            heapq.heappush(self._topo, magnitude)
        elif magnitude > self._topo[0]:
            heapq.heapreplace(self._topo, magnitude)

    def _referencia(self) -> int | None:
        """K-ésima maior da sessão; máximo da sessão enquanto a cauda é curta.

        Máximo é a leitura CONSERVADORA: com ele `magnitude_relativa` nunca
        passa de 1,0, então o gate nunca fica mais frouxo do que ficaria com a
        cauda cheia. Um erro para o lado de calar, não de autorizar.
        """
        cfg = self.config
        if self._max_sessao <= 0:
            return None
        if len(self._topo) < cfg.tamanho_topo_magnitude:
            return self._max_sessao
        if self._amostras_total < cfg.minimo_amostras_referencia:
            return self._max_sessao
        return self._topo[0]

    def _atualizar_persistencia(self, sentido: Side | None, timestamp_ns: int) -> None:
        if sentido is not self._sentido_persistente:
            self._sentido_persistente = sentido
            self._persistencia_desde_ns = timestamp_ns
            self._persistencia_amostras = 0
        self._persistencia_amostras += 1

    def _estado(
        self,
        sentido: Side | None,
        magnitude: int,
        relativa: float | None,
    ) -> EstadoVelocimetro:
        cfg = self.config
        if relativa is None:
            return EstadoVelocimetro.SEM_DADOS
        if sentido is None:
            return EstadoVelocimetro.PARADO
        if relativa < cfg.magnitude_relativa_minima:
            return EstadoVelocimetro.PARADO

        ref = self._variacao_anterior
        sentido_ref = _sentido_de(ref)
        if sentido_ref is not None and sentido_ref is not sentido:
            return EstadoVelocimetro.VIROU

        base = abs(ref)
        if base == 0:
            return EstadoVelocimetro.ACELERANDO
        if magnitude > base * (1.0 + cfg.tolerancia_variacao):
            return EstadoVelocimetro.ACELERANDO
        if magnitude < base * (1.0 - cfg.tolerancia_variacao):
            return EstadoVelocimetro.DESACELERANDO
        return EstadoVelocimetro.MANTENDO

    # ------------------------------------------------------------------
    def iniciar_nova_sessao(self) -> None:
        """A referência de magnitude é "do histórico intradiário" — carregá-la
        para o dia seguinte mediria o repique de hoje contra o pico de ontem."""
        self._janela.resetar()
        self._topo.clear()
        self._amostras_total = 0
        self._max_sessao = 0
        self._variacao_ref = 0
        self._variacao_anterior = 0
        self._sentido_persistente = None
        self._persistencia_desde_ns = 0
        self._persistencia_amostras = 0


def _sentido_de(variacao: int) -> Side | None:
    """`Side`, nunca cor — ver a nota de divergência de cor em `regras.py`."""
    if variacao > 0:
        return Side.BUY
    if variacao < 0:
        return Side.SELL
    return None
