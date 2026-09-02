"""Sinal Ultra — filtro extra de confluencia, ORIGINAL DESTE PROJETO.

O "Sinal Ultra" citado no material de origem e admitidamente AUSENTE NA
FONTE (`fluxopro/metodologia/regras.py`, id `sinal_ultra.gatilho`: "saida de
caixa-preta do autor: nao ha regra de preco/tempo/volume que defina quando
dispara. Nao implementado."). Nao existe regra do autor a reproduzir aqui —
o que este modulo implementa e uma regra PROPRIA do projeto (nao da ASG, nao
do autor do metodo original), documentada explicitamente como tal. Nunca
apresente isto ao operador como "o Ultra verdadeiro" — e um filtro adicional
que este projeto decidiu construir porque a fonte nao definiu um.

Pedido do operador (26/08/2026, MUDANCAS E IMPLEMENTACOES.docx): "um filtro
a mais, com padroes bem definidos", que NAO pode "ascender toda hora" — tem
que ser raro e confirmado por multiplas fontes ao mesmo tempo, nunca uma
leitura isolada.

Regra implementada — dispara ULTRA (COMPRA ou VENDA) somente quando TODAS as
condicoes abaixo sao verdadeiras ao MESMO TEMPO (confluencia, nao maioria):

  1. O motor de decisao principal (`fluxopro.asg.decisao.MotorDecisaoASG`) ja
     confirmou a MESMA direcao. Ultra e um filtro A MAIS sobre o sinal que ja
     passou pelos gates existentes — nunca um sinal paralelo independente que
     possa contradizer o motor principal.
  2. O MakerProxy — score ja suavizado (ver
     `fluxopro.ui.paineis.asg._forca_maker_suavizada`, SMA-5 sobre o mesmo
     score que alimenta o gauge EQUILIBRIO) — e evidencia auxiliar no modo
     padrao. No modo estrito, ele precisa estar forte e na mesma direcao:
     `|forca| >= forca_maker_minima` E confianca alta.
  3. Essa confluencia persiste por `>= persistencia_minima_ns` CONTINUOS
     antes de ligar (debounce — evita ligar num unico trade de ruido).

O Renko continua sendo calculado e exibido como contexto independente, mas
nao bloqueia nem confirma o ULTRA no modo padrao. A decisao usa
DECISAO + CONTEXTO + PERSISTENCIA; o modo estrito opcional acrescenta MAKER
e CONFIANCA. Isso evita que uma visualizacao de tendencia com tijolos
grandes esconda uma confluencia real do fluxo.

Uma vez ligado, so desliga quando a confluencia quebra por
`>= tempo_para_desligar_ns` continuos: histerese assimetrica, liga so depois
de confirmado mas nao desliga no primeiro trade que sai de linha. E
deliberadamente o oposto do defeito relatado no gauge EQUILIBRIO (instantaneo,
sem nenhuma suavizacao — ver `asg.py`), porque aqui o objetivo explicito e
"nao pode ascender toda hora", nao refletir cada trade em tempo real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fluxopro.analytics.renko import FaseRenko

__all__ = [
    "ConfigSinalUltra",
    "DirecaoUltra",
    "EntradaSinalUltra",
    "MotorSinalUltra",
    "SinalUltraSnapshot",
]


class DirecaoUltra(Enum):
    COMPRA = "compra"
    VENDA = "venda"
    NENHUMA = "nenhuma"


@dataclass(frozen=True, slots=True)
class ConfigSinalUltra:
    forca_maker_minima: float = 0.5
    """IMPRECISO — proxy de engenharia deste projeto, nao ha limiar da fonte
    original (o Ultra da fonte e AUSENTE_NA_FONTE). 0.5 = metade da escala
    [-1, 1] do MakerProxy ja suavizado."""

    confianca_maker_alta_minima: float = 0.60
    """Confianca minima do MakerProxy (0-1) nesta confluencia.

    ``0,75`` era um portao inalcancavel para MBP/inferido: a penalidade de
    procedencia limita o melhor feed a ``0,6375`` antes mesmo de considerar a
    cobertura dos componentes. ``0,60`` e o piso de confirmacao da decisao
    consultiva; o ULTRA continua exigindo, simultaneamente, direcao,
    tendencia Renko, forca Maker e persistencia. O nome historico do campo e
    preservado por compatibilidade, mas este limiar e uma regra propria do
    Operador B3, nao a classificacao visual geral ``ConfiancaASG.ALTA``."""

    persistencia_minima_ns: int = 5_000_000_000
    """5s: quanto tempo a confluencia completa precisa se manter ANTES do
    Ultra ligar. Debounce contra ruido de um unico trade."""

    tempo_para_desligar_ns: int = 8_000_000_000
    """8s: quanto tempo a confluencia precisa ficar QUEBRADA antes do Ultra
    desligar, depois de ja estar ligado. Histerese assimetrica deliberada —
    ver docstring do modulo."""

    exigir_maker_como_gate: bool = False
    """Modo estrito opcional para estudos de sensibilidade.

    No modo padrao, decisao/contexto confirmado e persistente sustentam o
    Ultra. O MakerProxy continua exposto como evidencia auditavel, mas nao
    bloqueia sozinho uma confirmacao contextual.
    """

    def __post_init__(self) -> None:
        if not 0.0 <= self.forca_maker_minima <= 1.0:
            raise ValueError("forca_maker_minima deve estar entre 0 e 1")
        if not 0.0 <= self.confianca_maker_alta_minima <= 1.0:
            raise ValueError("confianca_maker_alta_minima deve estar entre 0 e 1")
        if self.persistencia_minima_ns < 0 or self.tempo_para_desligar_ns < 0:
            raise ValueError("tempos de histerese devem ser >= 0")
        if not isinstance(self.exigir_maker_como_gate, bool):
            raise TypeError("exigir_maker_como_gate deve ser bool")


@dataclass(frozen=True, slots=True)
class EntradaSinalUltra:
    """Retrato de UM instante — o motor nao le nenhum estado global."""

    timestamp_ns: int
    direcao_decisao_confirmada: DirecaoUltra
    """NENHUMA se o motor de decisao principal nao confirmou COMPRA/VENDA
    agora (ver `MotorDecisaoASG.avaliar`, campo de confirmacao)."""

    fase_renko: FaseRenko
    """Contexto legado/informativo. Nao participa da regra do ULTRA."""

    direcao_renko: DirecaoUltra
    """Direcao do ultimo tijolo fechado, apenas para diagnostico/UI."""

    forca_maker: float
    """Score do MakerProxy JA SUAVIZADO (mesmo numero do gauge EQUILIBRIO
    apos a correcao de 26/08/2026), em [-1, 1]."""

    confianca_maker_alta: bool
    """`confianca_maker >= ConfigSinalUltra.confianca_maker_alta_minima`,
    decidido pelo chamador (o motor nao conhece a escala de confianca do
    MakerProxy diretamente, para nao duplicar essa constante em dois lugares)."""

    contexto_alinhado: bool = True
    """Macro e Micro apontam para a direcao confirmada neste instante.

    O default `True` preserva consumidores antigos que ainda nao publicam a
    matriz contextual. A interface atual sempre preenche o valor a partir do
    snapshot; Ultra nao deve depender de Renko para representar contexto.
    """


@dataclass(frozen=True, slots=True)
class SinalUltraSnapshot:
    timestamp_ns: int
    direcao: DirecaoUltra
    """O que esta LIGADO agora, apos a histerese — o que a UI deve mostrar."""

    confluencia_no_instante: DirecaoUltra
    """O que a confluencia crua diria NESTE instante, antes de qualquer
    debounce/histerese — util para depuracao, nunca para exibir como o
    sinal "oficial" (isso e `direcao`)."""

    ligado_desde_ns: int | None
    """`None` quando `direcao is NENHUMA`."""

    pendente_desde_ns: int = 0
    """Instante em que a confluencia CRUA corrente (`confluencia_no_instante`)
    passou a valer sem interrupcao. E o cronometro que o motor ja mantinha
    internamente (`_pendente_desde_ns`) — este campo apenas o **publica**, e
    nao altera nada de quando o Ultra liga ou desliga.

    Existe porque sem ele a UI nao conseguia distinguir "a confluencia fechou
    agora" de "a confluencia esta fechada ha 4,8s e falta um piscar para o
    Ultra ligar" — as duas saiam como o mesmo estado mudo, que e o miolo do
    "nunca apareceu nada" relatado pelo operador em 26/08/2026. Com
    `entrada.timestamp_ns - pendente_desde_ns` a tela mostra a barra de
    confirmacao com numero REAL, nunca estimado.

    `0` antes da primeira chamada de `atualizar`."""

    janela_alvo_ns: int = 0
    """Quanto tempo a confluencia pendente precisa se manter para causar a
    PROXIMA transicao, ja escolhida entre as duas metades da histerese
    assimetrica pelo proprio motor:

    * ``persistencia_minima_ns`` quando o Ultra esta apagado e ha confluencia
      pendente (esta ARMANDO);
    * ``tempo_para_desligar_ns`` quando o Ultra esta aceso e a confluencia
      quebrou ou virou (esta SEGURANDO);
    * ``0`` quando nao ha transicao pendente — o estado corrente e estavel.

    Quem desenha nao precisa (e nao deve) reimplementar essa escolha: fazer a
    UI decidir qual das duas janelas se aplica seria uma segunda copia da
    regra de histerese, que envelheceria em silencio no dia em que o motor
    mudasse. O motor e quem sabe, entao e o motor quem diz."""

    config: ConfigSinalUltra | None = None
    """A configuracao DESTA instancia do motor, para que a UI exiba limiar e
    janela lidos da fonte em vez de redigitados.

    `nucleo.py` mostra "MAKER +0,58 / +0,50" e "JANELA DE 5,0 S": os dois
    numeros da direita tem de ser os que o motor realmente aplicou. Um
    `ConfigSinalUltra()` construido do lado da UI acerta por coincidencia
    enquanto ninguem passar configuracao customizada ao motor, e passa a
    mentir em silencio no dia em que alguem passar. `ConfigSinalUltra` e
    frozen, entao publicar a referencia nao abre caminho para a UI mexer no
    motor."""


class MotorSinalUltra:
    """Puro — alimentado por chamada direta (`atualizar`), nunca assina o
    barramento (mesmo invariante de `fluxopro.analytics.renko.Renko`)."""

    __slots__ = ("config", "_direcao_atual", "_direcao_pendente", "_pendente_desde_ns", "_ligado_desde_ns")

    def __init__(self, config: ConfigSinalUltra | None = None) -> None:
        self.config = config or ConfigSinalUltra()
        self._direcao_atual = DirecaoUltra.NENHUMA
        self._direcao_pendente = DirecaoUltra.NENHUMA
        self._pendente_desde_ns = 0
        self._ligado_desde_ns: int | None = None

    def _confluencia(self, entrada: EntradaSinalUltra) -> DirecaoUltra:
        alvo = entrada.direcao_decisao_confirmada
        if alvo is DirecaoUltra.NENHUMA:
            return DirecaoUltra.NENHUMA
        if not entrada.contexto_alinhado:
            return DirecaoUltra.NENHUMA
        if not self.config.exigir_maker_como_gate:
            return alvo
        if not entrada.confianca_maker_alta:
            return DirecaoUltra.NENHUMA
        if alvo is DirecaoUltra.COMPRA and entrada.forca_maker >= self.config.forca_maker_minima:
            return DirecaoUltra.COMPRA
        if alvo is DirecaoUltra.VENDA and entrada.forca_maker <= -self.config.forca_maker_minima:
            return DirecaoUltra.VENDA
        return DirecaoUltra.NENHUMA

    def atualizar(self, entrada: EntradaSinalUltra) -> SinalUltraSnapshot:
        alvo = self._confluencia(entrada)

        if alvo != self._direcao_pendente:
            self._direcao_pendente = alvo
            self._pendente_desde_ns = entrada.timestamp_ns
        duracao_ns = entrada.timestamp_ns - self._pendente_desde_ns

        if self._direcao_atual is DirecaoUltra.NENHUMA:
            if alvo is not DirecaoUltra.NENHUMA and duracao_ns >= self.config.persistencia_minima_ns:
                self._direcao_atual = alvo
                self._ligado_desde_ns = entrada.timestamp_ns
        elif alvo is not self._direcao_atual and duracao_ns >= self.config.tempo_para_desligar_ns:
            self._direcao_atual = DirecaoUltra.NENHUMA
            self._ligado_desde_ns = None
            # Achado do revisor (gauntlet, 26/08/2026): sem este reset, uma
            # reversao DIRETA de direcao (COMPRA -> VENDA sem passar por
            # NENHUMA) reaproveitava o mesmo cronometro que acabou de
            # satisfazer `tempo_para_desligar_ns` para JA satisfazer
            # `persistencia_minima_ns` da nova direcao na chamada seguinte —
            # o Ultra religava quase instantaneamente do lado oposto, sem a
            # janela de confirmacao propria que o modulo promete. Zerar o
            # cronometro no instante do desligamento forca a nova direcao a
            # cumprir sua PROPRIA janela de persistencia a partir daqui.
            self._pendente_desde_ns = entrada.timestamp_ns

        return SinalUltraSnapshot(
            timestamp_ns=entrada.timestamp_ns,
            direcao=self._direcao_atual,
            confluencia_no_instante=alvo,
            ligado_desde_ns=self._ligado_desde_ns,
            pendente_desde_ns=self._pendente_desde_ns,
            janela_alvo_ns=self._janela_alvo_ns(),
            config=self.config,
        )

    def _janela_alvo_ns(self) -> int:
        """Qual metade da histerese esta correndo agora — LEITURA, nao decisao.

        Chamada DEPOIS que `atualizar` ja resolveu a transicao do quadro, e
        derivada apenas do estado que ela deixou: nao ha ramo aqui que possa
        ligar, desligar ou adiar o Ultra. Espelha exatamente as duas
        comparacoes de `atualizar` (`persistencia_minima_ns` a partir de
        apagado, `tempo_para_desligar_ns` a partir de aceso) — se um dia essas
        comparacoes mudarem, este metodo tem de mudar junto, e e por isso que
        ele mora aqui, ao lado delas, e nao na regiao que desenha.
        """

        if self._direcao_atual is DirecaoUltra.NENHUMA:
            if self._direcao_pendente is DirecaoUltra.NENHUMA:
                return 0
            return self.config.persistencia_minima_ns
        if self._direcao_pendente is self._direcao_atual:
            return 0
        return self.config.tempo_para_desligar_ns
