"""Macro × micro — e a API que torna difícil comparar as duas erradas.

O que a fonte diz (`metodologia_regras.md` §6):

    "isto daqui é a macro, ou seja, todo o movimento do dia"       (CONFIRMADO)
    "Micro é sempre agora, macro o contexto de forma mais ampla"   (CONFIRMADO)
    "a micro é quem manda no agora, no movimento do momento"       (CONFIRMADO)
    "não confunda 10%, achando que a micro só ficou 10% positiva"  (CONFIRMADO)

A última é uma **regra de exibição**, e é o eixo deste módulo: macro e micro
são medidas em escalas diferentes e não podem ser comparadas pelo mesmo número
percentual. Uma macro de +900 sobre um dia inteiro e uma micro de +900 sobre
quinze segundos não descrevem a mesma coisa, e a razão entre elas não
significa nada.

## Como a API torna o erro difícil

1. As duas medidas são o **mesmo tipo** `MedidaContexto`, mas carregam
   `escala`. Comparar (`<`, `>`, `==`, `-`, `/`) duas medidas de escalas
   diferentes levanta `EscalasIncomparaveisError`. Não é uma convenção
   documentada que alguém possa esquecer de ler: é uma exceção em runtime.
2. `LeituraMacroMicro` **não expõe nenhum número que misture as duas**. Não há
   razão, não há diferença, não há percentual conjunto. O que ela expõe do
   par é `alinhados` (bool) e `comanda` (`Side`) — comparação de **sentido**,
   que é a única que a fonte autoriza ("operar micro a favor da macro").
3. `comparavel_por_magnitude` é um campo com valor `False` fixo, para que
   quem lê a leitura veja a restrição sem precisar abrir a documentação.

## O que é AUSENTE NA FONTE aqui

O tamanho da janela da micro. O autor nunca diz "micro = últimos N minutos"; a
macro tem âncora (desde a abertura), a micro não tem nenhuma
(`macro_micro.janela_micro`). Vira `ConfigMacroMicro.janela_micro_ns`, e o
valor usado viaja em `MedidaContexto.janela_ns` de toda leitura — um painel
não pode mostrar "a micro" sem poder dizer de que janela está falando.

Contra-tendência (`macro_micro.contra_tendencia`) sai como flag qualitativa e
**não bloqueia nada**: a frase da fonte está cortada na legenda e não há regra
numérica de quando é permitido.

## Estado

Três contadores de sessão + uma `JanelaMovel` (anel de `n_baldes` inteiros).
Nada indexado por evento — critério de `fluxopro/gravacao/gravador.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.janela import JanelaMovel
from fluxopro.metodologia.regras import regras_de


class EscalasIncomparaveisError(TypeError):
    """Tentativa de comparar/misturar uma medida macro com uma micro.

    É a regra `macro_micro.escalas_incomparaveis` (CONFIRMADO) virando
    comportamento em vez de aviso na documentação.
    """


@unique
class Escala(Enum):
    MACRO = "MACRO"
    """Todo o movimento do dia, desde a abertura."""

    MICRO = "MICRO"
    """O movimento presente, numa janela curta configurável."""


@dataclass(frozen=True, slots=True, eq=False)
class MedidaContexto:
    """Um contador de contexto com a escala em que ele foi medido.

    Comparação e aritmética só valem **dentro da mesma escala**. Fora dela,
    `EscalasIncomparaveisError`.
    """

    escala: Escala
    valor: int
    """Contador em contratos, sempre `int`."""

    janela_ns: int
    """Lookback real. 0 significa "desde a abertura" (macro)."""

    amostras: int

    # -- comparacao ----------------------------------------------------
    def _exigir_mesma_escala(self, outro: object, operacao: str) -> MedidaContexto:
        if not isinstance(outro, MedidaContexto):
            raise EscalasIncomparaveisError(
                f"{operacao}: MedidaContexto so se compara com MedidaContexto "
                f"(recebeu {type(outro).__name__}). Comparar com um numero cru "
                "perde justamente a escala."
            )
        if outro.escala is not self.escala:
            raise EscalasIncomparaveisError(
                f"{operacao}: {self.escala.value} x {outro.escala.value} — "
                "macro e micro sao medidas em escalas diferentes e nao se "
                "comparam pelo mesmo numero. Compare o SENTIDO "
                "(MedidaContexto.sentido) ou cada uma dentro da propria escala."
            )
        return outro

    def __eq__(self, outro: object) -> bool:
        o = self._exigir_mesma_escala(outro, "==")
        return (self.valor, self.janela_ns, self.amostras) == (
            o.valor,
            o.janela_ns,
            o.amostras,
        )

    def __hash__(self) -> int:
        return hash((self.escala, self.valor, self.janela_ns, self.amostras))

    def __lt__(self, outro: object) -> bool:
        return self.valor < self._exigir_mesma_escala(outro, "<").valor

    def __le__(self, outro: object) -> bool:
        return self.valor <= self._exigir_mesma_escala(outro, "<=").valor

    def __gt__(self, outro: object) -> bool:
        return self.valor > self._exigir_mesma_escala(outro, ">").valor

    def __ge__(self, outro: object) -> bool:
        return self.valor >= self._exigir_mesma_escala(outro, ">=").valor

    def __sub__(self, outro: object) -> int:
        return self.valor - self._exigir_mesma_escala(outro, "-").valor

    def __truediv__(self, outro: object) -> float:
        o = self._exigir_mesma_escala(outro, "/")
        if o.valor == 0:
            raise ZeroDivisionError("divisao por medida de valor zero")
        return self.valor / o.valor

    # -- leitura -------------------------------------------------------
    @property
    def sentido(self) -> Side | None:
        """A única leitura desta medida que atravessa escalas com segurança."""
        if self.valor > 0:
            return Side.BUY
        if self.valor < 0:
            return Side.SELL
        return None

    def __repr__(self) -> str:
        return (
            f"MedidaContexto({self.escala.value}, valor={self.valor}, "
            f"janela_ns={self.janela_ns})"
        )


def comparar_magnitudes(a: MedidaContexto, b: MedidaContexto) -> int:
    """`-1/0/1` dentro da mesma escala; `EscalasIncomparaveisError` fora dela.

    Existe para dar um caminho **explícito e nomeado** a quem quer comparar
    magnitudes, em vez de deixar a pessoa descobrir a restrição por acidente.
    """
    a._exigir_mesma_escala(b, "comparar_magnitudes")
    if a.valor < b.valor:
        return -1
    return 0 if a.valor == b.valor else 1


@dataclass(frozen=True, slots=True)
class ConfigMacroMicro:
    """Ver `regras.parametros_de("ConfigMacroMicro")`."""

    janela_micro_ns: int = 15_000_000_000
    """AUSENTE NA FONTE. O valor usado viaja em toda leitura."""

    n_baldes: int = 8


@dataclass(frozen=True, slots=True)
class LeituraMacroMicro:
    """As duas medidas lado a lado — **e nenhum número que as misture**."""

    timestamp_ns: int
    macro: MedidaContexto
    micro: MedidaContexto
    volume_nao_atribuido: int
    comparavel_por_magnitude: bool = False
    """Fixo em `False`. Está aqui para a restrição ser visível na leitura."""

    regras: tuple[RegraDocumentada, ...] = field(default=())

    @property
    def comanda(self) -> Side | None:
        """Quem manda no preço agora: a micro. CONFIRMADO
        ("a micro é quem manda no agora, no movimento do momento")."""
        return self.micro.sentido

    @property
    def alinhados(self) -> bool:
        """Micro a favor da macro — comparação de SENTIDO, não de magnitude."""
        m, u = self.macro.sentido, self.micro.sentido
        return m is not None and u is not None and m is u

    @property
    def contra_tendencia(self) -> bool:
        """Micro contra a macro. Flag qualitativa: não bloqueia nada, porque a
        fonte não dá regra numérica de quando é permitido (IMPRECISO)."""
        m, u = self.macro.sentido, self.micro.sentido
        return m is not None and u is not None and m is not u


_REGRAS = regras_de(
    "macro_micro.macro",
    "macro_micro.micro",
    "macro_micro.hierarquia",
    "macro_micro.escalas_incomparaveis",
    "macro_micro.contra_tendencia",
    "macro_micro.janela_micro",
)


class MacroMicro:
    """Macro (desde a abertura) e micro (janela curta) do delta de agressão."""

    __slots__ = ("config", "_symbol", "_delta", "_amostras", "_nao_atribuido", "_janela")

    def __init__(self, symbol: str, config: ConfigMacroMicro | None = None) -> None:
        self.config = config or ConfigMacroMicro()
        self._symbol = symbol
        self._delta = 0
        self._amostras = 0
        self._nao_atribuido = 0
        self._janela = JanelaMovel(self.config.janela_micro_ns, self.config.n_baldes)

    def ao_trade(self, trade: Trade) -> LeituraMacroMicro:
        if trade.symbol != self._symbol:
            return self.leitura(trade.timestamp_ns)

        if trade.side_agressor is AgressorSide.BUY:
            self._delta += trade.qty
        elif trade.side_agressor is AgressorSide.SELL:
            self._delta -= trade.qty
        else:
            self._nao_atribuido += trade.qty

        self._amostras += 1
        self._janela.registrar(trade.timestamp_ns, self._delta)
        return self.leitura(trade.timestamp_ns)

    def leitura(self, timestamp_ns: int) -> LeituraMacroMicro:
        return LeituraMacroMicro(
            timestamp_ns=timestamp_ns,
            macro=MedidaContexto(
                escala=Escala.MACRO,
                valor=self._delta,
                janela_ns=0,
                amostras=self._amostras,
            ),
            micro=MedidaContexto(
                escala=Escala.MICRO,
                valor=self._janela.variacao,
                janela_ns=self._janela.duracao_ns,
                amostras=self._janela.amostras,
            ),
            volume_nao_atribuido=self._nao_atribuido,
            regras=_REGRAS,
        )

    @property
    def delta_macro(self) -> int:
        return self._delta

    def iniciar_nova_sessao(self) -> None:
        """A macro é "todo o movimento do dia" — do dia de hoje."""
        self._delta = 0
        self._amostras = 0
        self._nao_atribuido = 0
        self._janela.resetar()
