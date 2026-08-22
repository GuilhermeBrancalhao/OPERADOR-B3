"""Placar Estatístico — agregador de confluência, com estabilidade × oscilação.

O que a fonte diz (`ferramenta_componentes.md` §2, vídeo `Rwm3uzxZhhc`):

    "ele lê os sinais que a SG já lê do mercado"                 (CONFIRMADO)
    "aguardar se de fato existe uma confluência mais estável"     (CONFIRMADO)

O placar é **meta-leitura**: soma sinais que já existem, não olha o mercado.
Consequência direta na API — `Placar.registrar` recebe os votos de fora e
**não assina o `Barramento`**. Um componente que lê o mercado por dentro e se
chama "placar" já não é o objeto que a fonte descreve.

## Faixas e leituras

- Placar estável (sem oscilar) = confluência real. Oscilação nos primeiros
  minutos de pregão é ruído de abertura e não se opera (`placar.aquecimento`,
  IMPRECISO: "primeiros minutos" não tem número → `aquecimento_ns`).
- "Goleada" (4-0, 5-0) = não operar contra. **IMPRECISO**: a fonte cita dois
  placares, então o corte é `diferenca_goleada`, não uma constante.
- Empate ou virada = alerta de possível reversão e de proteção antecipada.

## Quem vota

A ferramenta original soma até cinco fontes: contexto micro, contexto macro, a
"setinha" (Sniper), suporte/resistência e o "auxílio do ChatGPT". As duas
últimas **não são fontes embutidas deste produto**:

- `sinal_ultra.gatilho` é AUSENTE NA FONTE (caixa-preta, sem regra de disparo).
- `placar.fonte_llm` é CONFIRMADO que existe lá e recusado aqui — o próprio
  autor diz que "não serve como um gatilho de entrada como a SG"
  (`_zs79_15iJQ`), e é consultivo com latência.

Este `Placar` aceita qualquer conjunto de votos que o chamador montar, o que
deixa a escolha explícita de quem monta em vez de embutida no produto.

## Estado

Sete escalares + um anel de `n_baldes_oscilacao` contadores de mudança. O
`len` é limitado por `n_baldes_oscilacao`, constante de configuração. Os nomes
das fontes **não são acumulados** — eles atravessam a leitura e são
descartados; guardar o conjunto de nomes já vistos seria uma coleção indexada
por quem chama, e é exatamente o tipo de crescimento silencioso que o critério
de `fluxopro/gravacao/gravador.py` proíbe.

Cor: o placar publica `Side`, nunca verde/vermelho/amarelo — ver a nota de
divergência de cor em `regras.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Side
from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.regras import regras_de


@unique
class VotoPlacar(Enum):
    """Voto de uma fonte. `NEUTRO` conta como fonte presente sem lado."""

    COMPRA = "COMPRA"
    VENDA = "VENDA"
    NEUTRO = "NEUTRO"


@dataclass(frozen=True, slots=True)
class ConfigPlacar:
    """Ver `regras.parametros_de("ConfigPlacar")`."""

    diferenca_goleada: int = 4
    """Diferença de votos que caracteriza "goleada". A fonte cita 4-0 e 5-0;
    default no menor dos dois (alerta antes)."""

    estabilidade_minima_ns: int = 30_000_000_000
    """Quanto o placar precisa ficar parado para ser lido como estável. A
    fonte diz "estável" sem duração nenhuma."""

    aquecimento_ns: int = 300_000_000_000
    """"Primeiros minutos de pregão", sem número na fonte."""

    janela_oscilacao_ns: int = 60_000_000_000
    oscilacoes_para_instavel: int = 3
    """Quantas mudanças de placar dentro da janela já contam como oscilação."""

    n_baldes_oscilacao: int = 6
    """Resolução do anel que conta mudanças. Engenharia pura."""


@dataclass(frozen=True, slots=True)
class LeituraPlacar:
    """O placar agora, e o que ele está fazendo ao longo do tempo."""

    timestamp_ns: int
    compra: int
    venda: int
    neutro: int
    lado: Side | None
    goleada: bool
    estavel: bool
    oscilando: bool
    em_aquecimento: bool
    virou: bool
    """O lado mudou nesta leitura (inclui virar para empate)."""

    alerta_reversao: bool
    """Virou vindo de uma goleada — o alerta que a fonte descreve."""

    mudancas_na_janela: int
    estavel_ha_ns: int
    fontes: tuple[str, ...]
    regras: tuple[RegraDocumentada, ...] = field(default=())

    @property
    def placar(self) -> str:
        """Como a fonte lê: `"4 a 0"`, sempre maior primeiro."""
        maior, menor = max(self.compra, self.venda), min(self.compra, self.venda)
        return f"{maior} a {menor}"

    @property
    def total_fontes(self) -> int:
        return self.compra + self.venda + self.neutro

    @property
    def operavel(self) -> bool:
        """Estável, fora do aquecimento, sem oscilar e com um lado.

        Não é gatilho de entrada — é o filtro de disciplina que a fonte
        descreve ("aguardar se de fato existe uma confluência mais estável").
        """
        return (
            self.lado is not None
            and self.estavel
            and not self.oscilando
            and not self.em_aquecimento
        )


_REGRAS = regras_de(
    "placar.meta_leitura",
    "placar.estabilidade",
    "placar.goleada",
    "placar.aquecimento",
    "placar.virada",
)


class Placar:
    """Soma votos de outros componentes e mede estabilidade × oscilação."""

    __slots__ = (
        "config",
        "_abertura_ns",
        "_par_atual",
        "_estavel_desde_ns",
        "_lado_atual",
        "_goleada_atual",
        "_bal_idx",
        "_bal_n",
        "_dur_balde",
        "_idx_balde",
    )

    def __init__(self, config: ConfigPlacar | None = None) -> None:
        self.config = config or ConfigPlacar()
        cfg = self.config
        if cfg.n_baldes_oscilacao < 1:
            raise ValueError("n_baldes_oscilacao deve ser >= 1")
        if cfg.janela_oscilacao_ns // cfg.n_baldes_oscilacao < 1:
            raise ValueError("janela_oscilacao_ns curta demais para os baldes")

        self._abertura_ns: int | None = None
        self._par_atual: tuple[int, int] | None = None
        self._estavel_desde_ns = 0
        self._lado_atual: Side | None = None
        self._goleada_atual = False
        # Anel de contagem de mudancas: len fixo em n_baldes_oscilacao.
        self._bal_idx = [-1] * cfg.n_baldes_oscilacao
        self._bal_n = [0] * cfg.n_baldes_oscilacao
        self._dur_balde = cfg.janela_oscilacao_ns // cfg.n_baldes_oscilacao
        self._idx_balde: int | None = None

    # ------------------------------------------------------------------
    def registrar(
        self,
        timestamp_ns: int,
        votos: Mapping[str, VotoPlacar],
    ) -> LeituraPlacar:
        """Conta os votos deste instante. Nada dos votos é retido."""
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns nao pode ser negativo")

        compra = venda = neutro = 0
        for voto in votos.values():
            if voto is VotoPlacar.COMPRA:
                compra += 1
            elif voto is VotoPlacar.VENDA:
                venda += 1
            else:
                neutro += 1

        if self._abertura_ns is None:
            self._abertura_ns = timestamp_ns
            self._estavel_desde_ns = timestamp_ns

        cfg = self.config
        par = (compra, venda)
        lado = _lado_de(compra, venda)
        goleada = abs(compra - venda) >= cfg.diferenca_goleada

        mudou_placar = self._par_atual is not None and par != self._par_atual
        virou = self._par_atual is not None and lado is not self._lado_atual
        alerta = virou and self._goleada_atual

        if mudou_placar:
            self._registrar_mudanca(timestamp_ns)
            self._estavel_desde_ns = timestamp_ns
        elif self._par_atual is None:
            self._marcar_balde(timestamp_ns)

        self._par_atual = par
        self._lado_atual = lado
        self._goleada_atual = goleada

        estavel_ha = max(0, timestamp_ns - self._estavel_desde_ns)
        mudancas = self._mudancas_na_janela(timestamp_ns)

        return LeituraPlacar(
            timestamp_ns=timestamp_ns,
            compra=compra,
            venda=venda,
            neutro=neutro,
            lado=lado,
            goleada=goleada,
            estavel=estavel_ha >= cfg.estabilidade_minima_ns,
            oscilando=mudancas >= cfg.oscilacoes_para_instavel,
            em_aquecimento=(timestamp_ns - self._abertura_ns) < cfg.aquecimento_ns,
            virou=virou,
            alerta_reversao=alerta,
            mudancas_na_janela=mudancas,
            estavel_ha_ns=estavel_ha,
            fontes=tuple(votos),
            regras=_REGRAS,
        )

    # ------------------------------------------------------------------
    def _marcar_balde(self, timestamp_ns: int) -> int:
        idx = timestamp_ns // self._dur_balde
        if self._idx_balde is not None and idx < self._idx_balde:
            idx = self._idx_balde
        slot = idx % len(self._bal_idx)
        if self._bal_idx[slot] != idx:
            self._bal_idx[slot] = idx
            self._bal_n[slot] = 0
        self._idx_balde = idx
        return slot

    def _registrar_mudanca(self, timestamp_ns: int) -> None:
        self._bal_n[self._marcar_balde(timestamp_ns)] += 1

    def _mudancas_na_janela(self, timestamp_ns: int) -> int:
        """Soma dos baldes vivos. O(`n_baldes_oscilacao`), constante."""
        self._marcar_balde(timestamp_ns)
        assert self._idx_balde is not None
        n = len(self._bal_idx)
        total = 0
        for k in range(self._idx_balde - (n - 1), self._idx_balde + 1):
            slot = k % n
            if self._bal_idx[slot] == k:
                total += self._bal_n[slot]
        return total

    # ------------------------------------------------------------------
    @property
    def lado(self) -> Side | None:
        return self._lado_atual

    def iniciar_nova_sessao(self) -> None:
        """Reseta inclusive o aquecimento — "primeiros minutos de pregão" é
        do pregão de hoje."""
        self._abertura_ns = None
        self._par_atual = None
        self._estavel_desde_ns = 0
        self._lado_atual = None
        self._goleada_atual = False
        self._idx_balde = None
        for i in range(len(self._bal_idx)):
            self._bal_idx[i] = -1
            self._bal_n[i] = 0


def _lado_de(compra: int, venda: int) -> Side | None:
    if compra > venda:
        return Side.BUY
    if venda > compra:
        return Side.SELL
    return None
