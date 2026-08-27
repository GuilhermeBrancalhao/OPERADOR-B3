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
  2. O Renko 4R (`fluxopro.analytics.renko.Renko`) esta em
     `FaseRenko.TENDENCIA` (tijolos seguidos na mesma direcao, ver
     `ConfigRenko.tijolos_para_tendencia`) NA MESMA direcao da decisao.
  3. O MakerProxy — score ja suavizado (ver
     `fluxopro.ui.paineis.asg._forca_maker_suavizada`, SMA-5 sobre o mesmo
     score que alimenta o gauge EQUILIBRIO) — esta forte e na mesma direcao:
     `|forca| >= forca_maker_minima` E confianca alta.
  4. Essa confluencia persiste por `>= persistencia_minima_ns` CONTINUOS
     antes de ligar (debounce — evita ligar num unico trade de ruido).

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

    confianca_maker_alta_minima: float = 0.75
    """Confianca minima do MakerProxy (0-1) para contar como "confianca alta"
    nesta confluencia."""

    persistencia_minima_ns: int = 5_000_000_000
    """5s: quanto tempo a confluencia completa precisa se manter ANTES do
    Ultra ligar. Debounce contra ruido de um unico trade."""

    tempo_para_desligar_ns: int = 8_000_000_000
    """8s: quanto tempo a confluencia precisa ficar QUEBRADA antes do Ultra
    desligar, depois de ja estar ligado. Histerese assimetrica deliberada —
    ver docstring do modulo."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.forca_maker_minima <= 1.0:
            raise ValueError("forca_maker_minima deve estar entre 0 e 1")
        if not 0.0 <= self.confianca_maker_alta_minima <= 1.0:
            raise ValueError("confianca_maker_alta_minima deve estar entre 0 e 1")
        if self.persistencia_minima_ns < 0 or self.tempo_para_desligar_ns < 0:
            raise ValueError("tempos de histerese devem ser >= 0")


@dataclass(frozen=True, slots=True)
class EntradaSinalUltra:
    """Retrato de UM instante — o motor nao le nenhum estado global."""

    timestamp_ns: int
    direcao_decisao_confirmada: DirecaoUltra
    """NENHUMA se o motor de decisao principal nao confirmou COMPRA/VENDA
    agora (ver `MotorDecisaoASG.avaliar`, campo de confirmacao)."""

    fase_renko: FaseRenko
    direcao_renko: DirecaoUltra
    """Direcao do ultimo tijolo Renko FECHADO. NENHUMA se ainda nao houver
    tijolo (`Renko.tijolos` vazio)."""

    forca_maker: float
    """Score do MakerProxy JA SUAVIZADO (mesmo numero do gauge EQUILIBRIO
    apos a correcao de 26/08/2026), em [-1, 1]."""

    confianca_maker_alta: bool
    """`confianca_maker >= ConfigSinalUltra.confianca_maker_alta_minima`,
    decidido pelo chamador (o motor nao conhece a escala de confianca do
    MakerProxy diretamente, para nao duplicar essa constante em dois lugares)."""


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
        if entrada.fase_renko is not FaseRenko.TENDENCIA:
            return DirecaoUltra.NENHUMA
        if entrada.direcao_renko is not alvo:
            return DirecaoUltra.NENHUMA
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
        )
