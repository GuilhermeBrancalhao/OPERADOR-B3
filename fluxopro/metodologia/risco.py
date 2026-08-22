"""Gestão de risco — 3 stops por região, e os dois modos de tamanho.

O que a fonte diz (`metodologia_regras.md` §§8-9, vídeo `6UPPrXrYeOY`):

    "eu tenho uma regra que eu não passo de três"        (CONFIRMADO)
    "essa aqui eu vou entrar com a mão cheia"            (CONFIRMADO)
    "eu vou entrar menos pesado... entro com cinco"      (CONFIRMADO)
    "eu entro com a metade do lote"                      (CONFIRMADO)

A regra dos três stops é o achado numérico mais sólido da fonte sobre limite
de perda. Ela é **por região**: atingido o limite, aquela região fica
abandonada no dia ("se eu tomei três é porque a região tá muito confusa"); as
outras seguem liberadas.

## As três coisas que este módulo se RECUSA a fazer

1. **Limite diário agregado** (`risco.limite_diario_agregado`, AUSENTE NA
   FONTE). O autor nunca menciona "encerro o dia após X". Não existe contador
   diário aqui, e N stops em N regiões distintas **não** bloqueiam uma região
   nova. Inventar esse limite seria colocar na boca da fonte uma regra que
   ela não tem — e é um teste, não só um comentário.
2. **Decidir sozinho o tamanho** (`risco.gatilho_de_tamanho`, AUSENTE NA
   FONTE). "Região boa" × "região turbulenta" é julgamento visual combinado
   (%, linha azul, macro/micro); não há volatilidade nem spread que dispare a
   redução. Por isso `avaliar()` **exige** a `QualidadeRegiao` de quem chama.
   O sistema não infere, e não finge inferir.
3. **Escolher quantos contratos são "mão cheia"**
   (`risco.numeros_de_contratos`, AUSENTE NA FONTE). 20, 10 e 5 são o lote
   pessoal do autor. `ConfigRisco` nasce em 0 = não configurado, e
   `tamanho()` levanta `TamanhoNaoConfiguradoError` até o operador informar o
   próprio. Meia mão é a única derivável, porque a fonte diz literalmente
   "metade do lote".

## Estado, e por que ele é limitado por construção

`_regioes` é `dict[int, _Regiao]`, e o critério de
`fluxopro/gravacao/gravador.py` ("qual grandeza limita o `len` disto, e ela
para de crescer enquanto o pregão continua?") responde: **regiões com pelo
menos um stop consecutivo em aberto, ou bloqueadas** — ou seja, a ordem de
grandeza do número de operações PERDEDORAS do operador no dia (dezenas), não
de eventos de mercado. Duas travas garantem isso:

- nada é criado por preço observado: só `registrar_resultado` cria entrada, e
  `permite_entrada`/`estado` são consultas puras;
- um `GANHO` **remove** a entrada da região (o contador de stops seguidos
  volta a zero, e zero não precisa ser guardado).

Região bloqueada é a exceção: fica no dicionário até a virada de sessão,
porque é ela que carrega a proibição.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.regras import regras_de


@unique
class ModoTamanho(Enum):
    """Os tamanhos que a fonte nomeia. Nenhum número embutido."""

    MAO_CHEIA = "MAO_CHEIA"
    MEIA_MAO = "MEIA_MAO"
    MAO_MINIMA = "MAO_MINIMA"


@unique
class QualidadeRegiao(Enum):
    """Classificação que **o operador** faz — o gatilho é AUSENTE NA FONTE."""

    BOA = "BOA"
    INCERTA = "INCERTA"
    TURBULENTA = "TURBULENTA"


@unique
class ResultadoOperacao(Enum):
    GANHO = "GANHO"
    STOP = "STOP"


class TamanhoNaoConfiguradoError(ValueError):
    """`ConfigRisco` ainda não tem o lote do operador. Ver §8: os números da
    fonte (20/10/5) são exemplos pessoais, não tabela de regra."""


@dataclass(frozen=True, slots=True)
class ConfigRisco:
    """Ver `regras.parametros_de("ConfigRisco")`."""

    stops_maximos_por_regiao: int = 3
    """O número da fonte, e o único default aqui que vem dela."""

    tamanho_regiao_ticks: int = 20
    """Amplitude do bucket de preço que define "a mesma região". AUSENTE NA
    FONTE: escolha de engenharia, a calibrar por instrumento. Limitação
    conhecida do bucket: dois stops a 1 tick de distância podem cair em
    buckets vizinhos e contar separado."""

    contratos_mao_cheia: int = 0
    """0 = não configurado (ver `TamanhoNaoConfiguradoError`)."""

    contratos_mao_minima: int = 0
    contratos_meia_mao: int = 0
    """0 = derivar de `contratos_mao_cheia // 2` ("metade do lote")."""


@dataclass(frozen=True, slots=True)
class EstadoRegiao:
    """O que se sabe de uma região de preço agora."""

    regiao: int
    faixa_ticks: tuple[int, int]
    stops_seguidos: int
    bloqueada: bool
    regras: tuple[RegraDocumentada, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Decisao:
    """Resposta a "posso entrar aqui, e com quanto?"."""

    permitida: bool
    modo: ModoTamanho
    contratos: int | None
    """`None` quando o lote não foi configurado — a recusa é explícita, não um
    número inventado."""

    regiao: EstadoRegiao
    motivo: str
    regras: tuple[RegraDocumentada, ...] = field(default=())


_REGRAS_REGIAO = regras_de(
    "risco.tres_stops", "risco.limite_diario_agregado", "risco.tamanho_de_regiao"
)
_REGRAS_TAMANHO = regras_de(
    "risco.mao_cheia",
    "risco.meia_mao",
    "risco.mao_minima",
    "risco.gatilho_de_tamanho",
    "risco.numeros_de_contratos",
)


@dataclass(slots=True)
class _Regiao:
    stops_seguidos: int = 0
    bloqueada: bool = False


_MODO_POR_QUALIDADE = {
    QualidadeRegiao.BOA: ModoTamanho.MAO_CHEIA,
    QualidadeRegiao.INCERTA: ModoTamanho.MEIA_MAO,
    QualidadeRegiao.TURBULENTA: ModoTamanho.MAO_MINIMA,
}


class GestorRisco:
    """Contador de stops por região + mapeamento de tamanho por julgamento."""

    __slots__ = ("config", "_regioes")

    def __init__(self, config: ConfigRisco | None = None) -> None:
        self.config = config or ConfigRisco()
        if self.config.tamanho_regiao_ticks < 1:
            raise ValueError("tamanho_regiao_ticks deve ser >= 1")
        if self.config.stops_maximos_por_regiao < 1:
            raise ValueError("stops_maximos_por_regiao deve ser >= 1")
        self._regioes: dict[int, _Regiao] = {}

    # ------------------------------------------------------------------
    def regiao_de(self, preco: int) -> int:
        """Bucket de preço. Preço em TICKS (`int`), nunca float."""
        if not isinstance(preco, int) or isinstance(preco, bool):
            raise TypeError("preco deve ser int em ticks (nunca float)")
        return preco // self.config.tamanho_regiao_ticks

    def _faixa(self, regiao: int) -> tuple[int, int]:
        largura = self.config.tamanho_regiao_ticks
        base = regiao * largura
        return base, base + largura - 1

    def _estado(self, regiao: int) -> EstadoRegiao:
        r = self._regioes.get(regiao)
        return EstadoRegiao(
            regiao=regiao,
            faixa_ticks=self._faixa(regiao),
            stops_seguidos=r.stops_seguidos if r else 0,
            bloqueada=r.bloqueada if r else False,
            regras=_REGRAS_REGIAO,
        )

    def estado_regiao(self, preco: int) -> EstadoRegiao:
        """Consulta PURA: não cria entrada no dicionário."""
        return self._estado(self.regiao_de(preco))

    def permite_entrada(self, preco: int) -> bool:
        """`False` só se ESTA região bateu o limite. Nenhum limite agregado."""
        return not self._estado(self.regiao_de(preco)).bloqueada

    # ------------------------------------------------------------------
    def registrar_resultado(
        self,
        preco: int,
        resultado: ResultadoOperacao,
    ) -> EstadoRegiao:
        """Registra o desfecho de uma operação na região do `preco`.

        `GANHO` zera os stops seguidos — a fonte fala em "três stops
        SEGUIDOS" — e remove a entrada, a menos que a região já esteja
        bloqueada (o bloqueio vale para o dia inteiro: "não adianta ficar
        dando murro em ponta de faca").
        """
        regiao = self.regiao_de(preco)
        r = self._regioes.get(regiao)

        if resultado is ResultadoOperacao.GANHO:
            if r is None:
                return self._estado(regiao)
            if r.bloqueada:
                r.stops_seguidos = 0
            else:
                del self._regioes[regiao]
            return self._estado(regiao)

        if r is None:
            r = _Regiao()
            self._regioes[regiao] = r
        r.stops_seguidos += 1
        if r.stops_seguidos >= self.config.stops_maximos_por_regiao:
            r.bloqueada = True
        return self._estado(regiao)

    # ------------------------------------------------------------------
    def modo_para(self, qualidade: QualidadeRegiao) -> ModoTamanho:
        """Mapeamento puro de um julgamento do operador para um modo."""
        return _MODO_POR_QUALIDADE[qualidade]

    def tamanho(self, modo: ModoTamanho) -> int:
        """Contratos do modo. Levanta se o operador não informou o lote."""
        cfg = self.config
        if modo is ModoTamanho.MAO_CHEIA:
            valor = cfg.contratos_mao_cheia
        elif modo is ModoTamanho.MAO_MINIMA:
            valor = cfg.contratos_mao_minima
        else:
            # "eu entro com a metade do lote" — derivada, nao um numero solto.
            valor = cfg.contratos_meia_mao or (cfg.contratos_mao_cheia // 2)

        if valor <= 0:
            raise TamanhoNaoConfiguradoError(
                f"{modo.value} sem lote configurado em ConfigRisco. Os numeros "
                "da fonte (20/10/5) sao o lote pessoal do autor, nao regra — "
                "informe o seu."
            )
        return valor

    def avaliar(self, preco: int, qualidade: QualidadeRegiao) -> Decisao:
        """Entrada única: "posso operar aqui, e com quanto?".

        `qualidade` é **obrigatória** e vem do operador: o gatilho que separa
        "região boa" de "região turbulenta" é AUSENTE NA FONTE.
        """
        estado = self.estado_regiao(preco)
        modo = self.modo_para(qualidade)
        try:
            contratos: int | None = self.tamanho(modo)
        except TamanhoNaoConfiguradoError:
            contratos = None

        if estado.bloqueada:
            motivo = (
                f"regiao {estado.regiao} abandonada no dia: "
                f"{estado.stops_seguidos} stops seguidos "
                f"(limite {self.config.stops_maximos_por_regiao})"
            )
            return Decisao(False, modo, contratos, estado, motivo, _REGRAS_REGIAO)

        motivo = f"regiao livre ({estado.stops_seguidos} stops seguidos)"
        return Decisao(
            True, modo, contratos, estado, motivo, _REGRAS_REGIAO + _REGRAS_TAMANHO
        )

    # ------------------------------------------------------------------
    @property
    def regioes_bloqueadas(self) -> tuple[int, ...]:
        return tuple(sorted(k for k, v in self._regioes.items() if v.bloqueada))

    @property
    def regioes_rastreadas(self) -> int:
        """Tamanho do estado — usado pelos testes de retenção."""
        return len(self._regioes)

    def iniciar_nova_sessao(self) -> None:
        """"Abandonar a região NO DIA" só faz sentido se o dia acabar."""
        self._regioes.clear()
