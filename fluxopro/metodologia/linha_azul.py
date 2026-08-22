"""Linha Azul — o preço onde o acumulado comprador/vendedor cruzou 50%.

O que a fonte diz (`metodologia_regras.md` §3, vídeo `SHjx2aHkmVA`):

    "esta linha azul é o cruzamento dos 50%"                       (CONFIRMADO)
    "a ideia da linha azul é precisamente dar-te essa referência"  (CONFIRMADO)
    "projeção de stop para cima da linha"                          (CONFIRMADO)

Não é suporte/resistência clássico nem média móvel: é um nível derivado do
próprio indicador percentual, medido desde a abertura. E é **referência de
risco e de invalidação, não gatilho** — por isso `LeituraLinhaAzul` não tem
campo nenhum de entrada, direção sugerida ou sinal. Ela publica um nível, um
lado e uma distância.

## O IMPRECISO, e a convenção que esta implementação declara

`metodologia_regras.md:65` registra que o comportamento de plotagem **mudou
entre versões da ferramenta original**: num vídeo ela ancora "desde a abertura
do mercado"; noutro o autor conta que "agora a linha azul ela não plota mais
na abertura do mercado... porque a galera ficava muito louca" (`FmURmlN3boI`).
Duas versões, duas regras — não há uma para copiar.

**Convenção declarada desta implementação (`ConfigLinhaAzul`):**

1. **Último cruzamento, não o primeiro.** `ConvencaoLinhaAzul.ULTIMO_CRUZAMENTO`
   é o default porque a fonte usa a linha como referência VIVA de invalidação
   ("dar-te uma ideia de que o preço não funcionou"): um cruzamento das 9h01
   deixa de descrever o risco das 15h. `PRIMEIRO_CRUZAMENTO` existe e é
   suportado — a escolha fica visível em `LeituraLinhaAzul.convencao`, em toda
   leitura, para nenhum painel precisar adivinhar qual versão está vendo.
2. **A linha só existe depois de `volume_minimo_ancoragem` contratos
   atribuídos.** Com 0 (default) o comportamento é o da versão antiga (pode
   nascer na abertura); qualquer valor > 0 reproduz a versão que "não plota
   mais na abertura", sem fingir saber qual número o autor usou.
3. **Reset só na virada EXPLÍCITA de sessão**, mesma política de
   `EstadoMercado.iniciar_nova_sessao`. A fórmula do "acumulado" e o recálculo
   intradiário são AUSENTE NA FONTE (`linha_azul.janela_reset`).

## Volume sem agressor

`AgressorSide.UNKNOWN` (leilão, RLP) **não entra na razão** — não há lado a
somar — mas é contado à parte e publicado em `volume_nao_atribuido`, no mesmo
invariante do resto do projeto: o volume some do numerador, nunca do sistema.

## Estado

Sete inteiros e dois enums. Nenhuma coleção — o cruzamento é detectado
comparando a razão de agora com a de antes, sem histórico
(`fluxopro/gravacao/gravador.py`: nada indexado por evento).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.metodologia.confianca import Confianca, RegraDocumentada
from fluxopro.metodologia.regras import regras_de


@unique
class ConvencaoLinhaAzul(Enum):
    """Qual cruzamento de 50% a linha guarda. A fonte não decide isso."""

    ULTIMO_CRUZAMENTO = "ULTIMO_CRUZAMENTO"
    PRIMEIRO_CRUZAMENTO = "PRIMEIRO_CRUZAMENTO"


@unique
class LadoDaLinha(Enum):
    """Leitura de posição do preço. Rotulada INFERIDO — ver `linha_azul.lado`."""

    ACIMA = "ACIMA"
    ABAIXO = "ABAIXO"
    NA_LINHA = "NA_LINHA"
    SEM_LINHA = "SEM_LINHA"

    @property
    def leitura_inferida(self) -> Side | None:
        """"Abaixo vende, acima compra" — **INFERIDO**, não verbalizado pelo
        autor; decorre do conjunto de exemplos. Nunca tratar como confirmação."""
        if self is LadoDaLinha.ACIMA:
            return Side.BUY
        if self is LadoDaLinha.ABAIXO:
            return Side.SELL
        return None


@dataclass(frozen=True, slots=True)
class ConfigLinhaAzul:
    """Ver `regras.parametros_de("ConfigLinhaAzul")`."""

    convencao: ConvencaoLinhaAzul = ConvencaoLinhaAzul.ULTIMO_CRUZAMENTO
    volume_minimo_ancoragem: int = 0
    """Contratos atribuídos exigidos antes de a linha passar a existir."""

    margem_ticks: int = 0
    """Tolerância para o preço ser lido como "na linha"."""


@dataclass(frozen=True, slots=True)
class LeituraLinhaAzul:
    """Nível, lado e distância. **Nenhum campo de gatilho, de propósito.**"""

    timestamp_ns: int
    preco: int
    nivel: int | None
    """Preço do cruzamento de 50%. `None` enquanto não houve nenhum."""

    nivel_timestamp_ns: int | None
    lado: LadoDaLinha
    fracao_compradora: float
    """Volume comprador / (comprador + vendedor). 0.5 é o empate da fonte."""

    volume_comprador: int
    volume_vendedor: int
    volume_nao_atribuido: int
    cruzou_agora: bool
    convencao: ConvencaoLinhaAzul
    """A convenção em vigor viaja em TODA leitura — ver o IMPRECISO no módulo."""

    confianca_lado: Confianca = Confianca.INFERIDO
    regras: tuple[RegraDocumentada, ...] = field(default=())

    @property
    def distancia_ticks(self) -> int | None:
        """Distância assinada do preço até a linha, em ticks. É a medida que a
        fonte usa para dimensionar stop ("projeção de stop para cima da
        linha")."""
        if self.nivel is None:
            return None
        return self.preco - self.nivel


_REGRAS = regras_de(
    "linha_azul.definicao",
    "linha_azul.funcao_risco",
    "linha_azul.stop",
    "linha_azul.plotagem",
    "linha_azul.lado",
    "linha_azul.janela_reset",
)


class LinhaAzul:
    """Nível de 50% de equilíbrio comprador/vendedor desde a abertura."""

    __slots__ = (
        "config",
        "_symbol",
        "_comprador",
        "_vendedor",
        "_nao_atribuido",
        "_fracao_anterior",
        "_nivel",
        "_nivel_ts",
        "_ultimo_preco",
    )

    def __init__(self, symbol: str, config: ConfigLinhaAzul | None = None) -> None:
        self.config = config or ConfigLinhaAzul()
        self._symbol = symbol
        self._comprador = 0
        self._vendedor = 0
        self._nao_atribuido = 0
        self._fracao_anterior: float | None = None
        self._nivel: int | None = None
        self._nivel_ts: int | None = None
        self._ultimo_preco = 0

    # ------------------------------------------------------------------
    def ao_trade(self, trade: Trade) -> LeituraLinhaAzul:
        """Acumula o trade e devolve a leitura. Preço em ticks (`int`)."""
        if trade.symbol != self._symbol:
            return self.leitura(trade.timestamp_ns, self._ultimo_preco)

        if trade.side_agressor is AgressorSide.BUY:
            self._comprador += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            self._vendedor += trade.qty
        else:
            # UNKNOWN nao tem lado a somar: fica fora da razao, dentro do total.
            self._nao_atribuido += trade.qty

        self._ultimo_preco = trade.price
        cruzou = self._atualizar_nivel(trade.price, trade.timestamp_ns)
        return self.leitura(trade.timestamp_ns, trade.price, cruzou_agora=cruzou)

    def _atualizar_nivel(self, preco: int, timestamp_ns: int) -> bool:
        """Detecta o cruzamento de 50% comparando a razão com a anterior."""
        atribuido = self._comprador + self._vendedor
        if atribuido <= 0:
            return False
        if atribuido < self.config.volume_minimo_ancoragem:
            # Ainda nao ancorada: a fracao anterior tambem nao conta, senao o
            # primeiro trade depois do minimo veria um "cruzamento" fabricado.
            self._fracao_anterior = None
            return False

        fracao = self._comprador / atribuido
        anterior = self._fracao_anterior
        self._fracao_anterior = fracao

        if anterior is None:
            return False
        cruzou = (anterior < 0.5 <= fracao) or (anterior > 0.5 >= fracao)
        if not cruzou:
            return False

        if (
            self._nivel is None
            or self.config.convencao is ConvencaoLinhaAzul.ULTIMO_CRUZAMENTO
        ):
            self._nivel = preco
            self._nivel_ts = timestamp_ns
        return True

    # ------------------------------------------------------------------
    def leitura(
        self,
        timestamp_ns: int,
        preco: int,
        cruzou_agora: bool = False,
    ) -> LeituraLinhaAzul:
        atribuido = self._comprador + self._vendedor
        fracao = self._comprador / atribuido if atribuido else 0.5
        return LeituraLinhaAzul(
            timestamp_ns=timestamp_ns,
            preco=preco,
            nivel=self._nivel,
            nivel_timestamp_ns=self._nivel_ts,
            lado=self._lado(preco),
            fracao_compradora=fracao,
            volume_comprador=self._comprador,
            volume_vendedor=self._vendedor,
            volume_nao_atribuido=self._nao_atribuido,
            cruzou_agora=cruzou_agora,
            convencao=self.config.convencao,
            regras=_REGRAS,
        )

    def _lado(self, preco: int) -> LadoDaLinha:
        if self._nivel is None:
            return LadoDaLinha.SEM_LINHA
        margem = self.config.margem_ticks
        if preco > self._nivel + margem:
            return LadoDaLinha.ACIMA
        if preco < self._nivel - margem:
            return LadoDaLinha.ABAIXO
        return LadoDaLinha.NA_LINHA

    # ------------------------------------------------------------------
    @property
    def nivel(self) -> int | None:
        return self._nivel

    @property
    def volume_total(self) -> int:
        """Sempre igual à soma dos três baldes — nenhum volume some."""
        return self._comprador + self._vendedor + self._nao_atribuido

    def iniciar_nova_sessao(self) -> None:
        """A linha é "desde a abertura do mercado"; a de ontem não descreve
        hoje. Virada EXPLÍCITA pelo chamador, política de `EstadoMercado`."""
        self._comprador = 0
        self._vendedor = 0
        self._nao_atribuido = 0
        self._fracao_anterior = None
        self._nivel = None
        self._nivel_ts = None
        self._ultimo_preco = 0
