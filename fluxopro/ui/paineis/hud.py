"""HUD de contexto — para onde, com quanta conviccao, e em que ponto da decisao.

Tres perguntas, respondidas sem que o operador leia numero nenhum:

* **Para onde** — o medidor de saldo do dia e a barra de pressao da janela
  curta (§1, item 8 de `bar/`).
* **Com quanta conviccao** — o placar de confluencia: quantas das tres
  condicoes de `motor/sinais.py` estao satisfeitas AGORA, e quais.
* **Em que ponto** — o farol de cinco estagios (`EstagioSinal`). O estagio *e*
  a informacao; mostrar so o binario "tem sinal / nao tem" jogaria fora
  DIRECAO_CONFIRMADA, NA_REGIAO e PRE_SINAL, que sao tres quartos do que o
  motor sabe.

## A falha da referencia, e o que fizemos com ela

`bar/06_medidores_agressao_a.png` e uma janela inteira — barra de titulo,
icones, ~90px — para exibir UM numero, repetido duas vezes. E o numero e
grafado **identico** nos dois sentidos: saldo vendedor `(49,10k)` e saldo
comprador `(42,31k)`, parenteses nos dois casos, distinguiveis so pela cor do
fundo. Tire a cor — daltonismo, monitor mal calibrado, print em escala de
cinza — e a informacao principal desaparece inteira.

Aqui cada valor direcional carrega **tres** portadores independentes:

1. **sinal explicito** no texto (`+42,3k` / `−49,1k`, via `ui/formato.py`,
   nunca parenteses);
2. **posicao** — a barra cresce para a direita a partir do zero se for
   compradora, para a esquerda se for vendedora, e o zero e uma linha
   desenhada, nao uma convencao;
3. **cor** — azul/vermelho, o eixo direcional unico do produto, e o terceiro
   portador, nunca o primeiro.

## A lei do canal, e o que ela mudou nesta peca

A entrega desta tela e por **captura e transmissao** (ver
`scripts/transmissao.py`): o operador nao ve os pixels que o `QPainter`
desenhou, ve o que sobrou depois de reescala e quantizacao com perdas. Nesse
canal o texto pequeno e a **primeira** coisa a morrer, e a geometria de area
grande e a ultima.

A primeira versao desta peca empilhava dois medidores bidirecionais com
escalas independentes — 2.500 lotes num, 1.200 no outro — e punha a escala
como um **rotulo** de 10px ao lado. No monitor funcionava. Depois do canal, o
rotulo virava borrao e sobravam duas barras azuis de comprimento quase igual
sobre escalas que diferiam 2,1x: o leitor concluia "a pressao do dia e a dos
5 s estao iguais" quando uma era o dobro da outra. **Uma mentira grafica
produzida pelo canal, nao pelo desenho** — e uma mentira que so existia
porque a legenda que a desmentia era feita do material mais fragil que a tela
tem.

A correcao nao foi engordar o rotulo. Foi **tirar do segundo medidor a escala
que ele nao precisava ter** — e essa mesma correcao teve de ser feita mais
tres vezes, porque o defeito nao era daquele medidor, era de uma FORMA:

> **uma grandeza de variacao grande desenhada como comprimento, com um rotulo
> pequeno encarregado de desfazer a confusao que sobra.**

As quatro ocorrencias, para quem for mexer nisto depois:

1. dois medidores empilhados com escalas diferentes — comparacao errada no
   **espaco**, entre duas barras vizinhas;
2. e 3. o ranking de players, duas vezes (piso de 3px, depois asas de
   comprimento proporcional ao volume) — detalhe em `PainelPlayers`;
4. o medidor do dia com catraca — comparacao errada no **TEMPO**, entre o
   quadro de agora e a lembranca do quadro de vinte minutos atras. Esta foi a
   mais teimosa porque o argumento que a defendia ("perder o rotulo custa a
   unidade do eixo, nao a leitura") e verdadeiro para comparacao espacial e
   **falso** para a temporal: o eixo se move enquanto o valor fica parado, e
   nao ha na tela nenhuma segunda barra que denuncie. Detalhe em
   `PainelHUD._desenhar_saldo_dia`.

As quatro foram fechadas do mesmo jeito — removendo a necessidade da escala,
nunca mitigando o rotulo. O que sobrou e um vocabulario de duas formas, e ele
vale para o produto inteiro:

| Forma | Significa | Escala |
|---|---|---|
| **Barra particionada de largura fixa** | proporcao entre dois lados | nenhuma — 0..100% e absoluto |
| **Numero alinhado a direita** | grandeza sem teto (lotes, volume) | unidade fixa por coluna |

**Nao ha uma unica barra com escala neste modulo.** Se voce for acrescentar
uma, saiba que esta reabrindo o defeito acima pela quinta vez.

Ha uma consequencia que parece um risco e nao e: as duas barras do `PainelHUD`
ficaram com a MESMA forma. Duas barras parecidas so enganam quando escondem
eixos diferentes — que era exatamente o defeito 1. Estas duas estao no mesmo
eixo 0..100% e diferem so no horizonte, entao pareceram-se e o operador pode
comparar uma com a outra ("no pregao 53% comprador, nos ultimos 5 s 71%"), que
e uma leitura nova que a peca nao oferecia.

A janela de agressao virou barra particionada porque a pergunta dela e
**proporcional** ("de tudo que passou nos ultimos 5 s, quanto foi comprador"),
e proporcao tem eixo absoluto: 0 a 100%, com 50% no meio. Sem escala nao ha
escala para o canal apagar, e sem escala **nao existe comparacao de
comprimento a ser feita errado** — a barra tem sempre a mesma largura. A
duvida deixa de ser possivel por construcao, em vez de ser desfeita por uma
legenda.

## O ranking de players

`bar/01_times_trades_a.png` responde "quem esta dominando" com uma **pizza
3D de 10 fatias**, callouts em caixas brancas ligadas por linhas-guia, mais
uma legenda embaixo repetindo os mesmos 10 pares cor/valor. Pizza e a pior
forma conhecida para comparar 10 categorias, a inclinacao distorce as areas,
e a legenda duplicada gasta o dobro do espaco. `bar/09_tape_reading_b.png`
prova que a mesma casa sabe fazer 24 linhas densas — mas em tema claro
zebrado de rosa e azul, com `Classifi…` truncado e o saldo colado na palavra.

Aqui o volume virou **coluna numerica** — que e o que le 500x sem esforco, e
o que a tela mais densa do acervo ja faz — e a barra ficou so com a proporcao
compra x venda do proprio player, limitada por natureza e portanto sem escala.
Todas as barras tem a mesma largura; o que varia e onde elas se partem, e as
costuras formam uma linha quebrada contra a espinha reta de 50%. O porque
dessa forma — e as tres formas erradas que vieram antes dela — esta na
docstring de `PainelPlayers`.

## Estruturas

Nada aqui cresce. `PainelHUD` guarda **uma** leitura (a corrente, nunca um
historico) e um vetor de bandas de tamanho fixo; `PainelPlayers` guarda no
maximo `top_n` linhas, truncadas na entrada e nao no desenho. E o defeito de
estrutura que cresce ja apareceu oito vezes neste projeto (ver
`PROGRESSO.md`); a nona nao vai ser aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from fluxopro.core.eventos import Side
from fluxopro.motor.sinais import EstagioSinal, FaixaConviccao, Sinal
from fluxopro.ui import formato, tokens
from fluxopro.ui.base.painel_denso import PainelDenso

# --------------------------------------------------------------------------
# Glifos — portadores de FORMA, o canal que sobrevive a ausencia de cor.
# --------------------------------------------------------------------------
SETA_COMPRA = "▲"
SETA_VENDA = "▼"
SEM_LADO = "·"

GLIFO_SIM = "●"
GLIFO_PARCIAL = "◐"
GLIFO_NAO = "○"


_metricas: dict[tuple, QFontMetrics] = {}


def metrica(fonte: QFont) -> QFontMetrics:
    """`QFontMetrics` memoizada, pelo mesmo motivo dos `QColor` de `tokens.py`.

    Medir texto e barato uma vez e caro por banda por quadro: construir um
    `QFontMetrics` atravessa a fronteira Python<->C++ e consulta o mecanismo
    de fontes. No caminho incremental — que e o quadro comum, o que roda 60
    vezes por segundo — essas construcoes eram ~40% do custo da banda.

    O cache e limitado por construcao: a chave vem dos parametros da fonte, e
    os pontos de chamada deste modulo usam um punhado fixo de combinacoes
    (`tokens.fonte_*` ja e memoizado pela mesma razao). Nao ha entrada nova
    por linha, por player nem por quadro."""
    chave = (
        tuple(fonte.families()),
        fonte.pixelSize(),
        int(fonte.weight()),
        fonte.capitalization().name,
    )
    m = _metricas.get(chave)
    if m is None:
        m = QFontMetrics(fonte)
        _metricas[chave] = m
    return m


class EstadoCondicao(Enum):
    """Uma condicao do motor tem TRES estados, nao dois.

    `PRE_SINAL` existe justamente porque a terceira condicao pode estar a
    meio caminho — a micro comecou a virar sem ter virado. Colapsar isso em
    booleano apagaria o estagio que mais interessa a quem esta esperando a
    entrada.
    """

    NAO = "NAO"
    PARCIAL = "PARCIAL"
    SIM = "SIM"

    @property
    def glifo(self) -> str:
        return {
            EstadoCondicao.NAO: GLIFO_NAO,
            EstadoCondicao.PARCIAL: GLIFO_PARCIAL,
            EstadoCondicao.SIM: GLIFO_SIM,
        }[self]


# Ordem de avanco do farol. Explicita, e nao `list(EstagioSinal)`, porque a
# ordem de declaracao de um Enum e um acidente de edicao: se alguem inserir
# um estagio no meio, o farol tem de ser reavaliado por gente, nao herdar
# uma posicao por sorte. `tests/test_ui_hud.py` reprova se um estagio novo
# entrar no motor sem passar por aqui.
ORDEM_ESTAGIOS: tuple[EstagioSinal, ...] = (
    EstagioSinal.NENHUM,
    EstagioSinal.DIRECAO_CONFIRMADA,
    EstagioSinal.NA_REGIAO,
    EstagioSinal.PRE_SINAL,
    EstagioSinal.CONFIRMADO,
)

_RANK: dict[EstagioSinal, int] = {e: i for i, e in enumerate(ORDEM_ESTAGIOS)}

ROTULO_CURTO: dict[EstagioSinal, str] = {
    EstagioSinal.NENHUM: "—",
    EstagioSinal.DIRECAO_CONFIRMADA: "DIREÇÃO",
    EstagioSinal.NA_REGIAO: "REGIÃO",
    EstagioSinal.PRE_SINAL: "PRÉ",
    EstagioSinal.CONFIRMADO: "CONF",
}

ROTULO_LONGO: dict[EstagioSinal, str] = {
    EstagioSinal.NENHUM: "SEM CONFLUÊNCIA",
    EstagioSinal.DIRECAO_CONFIRMADA: "DIREÇÃO CONFIRMADA",
    EstagioSinal.NA_REGIAO: "NA REGIÃO",
    EstagioSinal.PRE_SINAL: "PRÉ-SINAL",
    EstagioSinal.CONFIRMADO: "CONFIRMADO — ENTRADA",
}

ROTULO_FAIXA: dict[FaixaConviccao, str] = {
    FaixaConviccao.LATERAL: "LATERAL",
    FaixaConviccao.PRE_DIRECIONAL: "PRÉ-DIR",
    FaixaConviccao.ZONA_CINZA: "ZONA CINZA",
    FaixaConviccao.DIRECIONAL: "DIRECIONAL",
    FaixaConviccao.MAXIMA_CONVICCAO: "MÁX CONVICÇÃO",
}


def cor_do_estagio(estagio: EstagioSinal) -> QColor:
    """§3.1: **o farol e SEGUNDO canal, nao direcao.**

    Nenhum estagio usa azul ou vermelho — esses dois pertencem ao eixo
    compra/venda e so a ele. A rampa aqui e de *temperatura de atencao*:
    apagado, discreto, vivo, ambar, roxo. `ALERT` em `PRE_SINAL` e `SIGNAL`
    em `CONFIRMADO` sao atribuicoes literais de §3.2 — nao houve escolha a
    fazer nem token novo a inventar.
    """
    return {
        EstagioSinal.NENHUM: tokens.TEXT_MUTED,
        EstagioSinal.DIRECAO_CONFIRMADA: tokens.TEXT_SECONDARY,
        EstagioSinal.NA_REGIAO: tokens.TEXT_PRIMARY,
        EstagioSinal.PRE_SINAL: tokens.ALERT,
        EstagioSinal.CONFIRMADO: tokens.SIGNAL,
    }[estagio]


def _cor_da_condicao(estado: EstadoCondicao) -> QColor:
    return {
        EstadoCondicao.NAO: tokens.TEXT_MUTED,
        EstadoCondicao.PARCIAL: tokens.ALERT,
        EstadoCondicao.SIM: tokens.OK,
    }[estado]


# --------------------------------------------------------------------------
# Leitura — o que a tela usa, ja reduzido. Sem Qt no caminho de construcao.
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Condicao:
    rotulo: str
    estado: EstadoCondicao
    detalhe: str


N_CONDICOES = 3
"""As tres da metodologia, e so elas. Tamanho fixo por construcao: o placar
nunca vira uma lista que cresce."""

TAXA_NEUTRA = 0.5


@dataclass(frozen=True, slots=True)
class LeituraContexto:
    """Um retrato do contexto. Imutavel, e o painel guarda **um**.

    **Nao ha nenhuma grandeza absoluta desenhada como comprimento aqui.**
    `saldo_dia` existe e e mostrado, mas como NUMERO; a geometria do dia sai
    de `volume_comprador_dia`/`volume_vendedor_dia`, que dao uma proporcao em
    [0,1] com 0,5 = equilibrio — o mesmo eixo de `taxa_compra_janela`, so que
    no horizonte do pregao em vez do da janela. Que os dois medidores tenham
    o mesmo eixo e o ponto: da para compara-los.
    """

    estagio: EstagioSinal
    direcao: Side | None
    faixa: FaixaConviccao
    condicoes: tuple[Condicao, ...]
    saldo_dia: int
    taxa_compra_janela: float
    volume_janela: int
    volume_nao_atribuido: int
    volume_comprador_dia: int = 0
    volume_vendedor_dia: int = 0

    @property
    def n_satisfeitas(self) -> int:
        return sum(1 for c in self.condicoes if c.estado is EstadoCondicao.SIM)

    @property
    def volume_dia(self) -> int:
        """Volume do dia COM lado atribuido. Nao inclui o RLP — ele aparece
        a parte, como `s/lado`, porque nao pertence a nenhum dos dois
        segmentos e enfia-lo num deles seria inventar agressor."""
        return max(0, self.volume_comprador_dia) + max(0, self.volume_vendedor_dia)

    @property
    def taxa_compra_dia(self) -> float:
        """Parcela compradora do pregao, em [0,1]. Sem volume, equilibrio —
        pela mesma razao que `_normalizar_taxa` existe para a janela."""
        total = self.volume_dia
        if total <= 0:
            return TAXA_NEUTRA
        return min(1.0, max(0.0, max(0, self.volume_comprador_dia) / total))


VAZIO = LeituraContexto(
    estagio=EstagioSinal.NENHUM,
    direcao=None,
    faixa=FaixaConviccao.LATERAL,
    condicoes=(
        Condicao("DIREÇÃO DO DIA", EstadoCondicao.NAO, "—"),
        Condicao("REGIÃO", EstadoCondicao.NAO, "—"),
        Condicao("MICRO", EstadoCondicao.NAO, "—"),
    ),
    saldo_dia=0,
    taxa_compra_janela=TAXA_NEUTRA,
    volume_janela=0,
    volume_nao_atribuido=0,
)


def _pct(fracao: float) -> str:
    """Percentual SEM sinal — dominancia, magnitude, participacao.

    Poupar o `+` aqui nao contradiz a regra de §3.2: a regra e sobre valor
    DIRECIONAL, e 72% de dominancia nao aponta para lado nenhum sozinho. O
    lado esta em `direcao`, com seta e palavra."""
    return f"{fracao * 100:.0f}%"


def _condicoes_de(
    estagio: EstagioSinal, faixa: FaixaConviccao, evidencia: dict[str, object]
) -> tuple[Condicao, ...]:
    """As tres condicoes, derivadas do estagio PUBLICADO.

    Decisao que importa: os estados vem do `estagio` (pos-histerese) e nao
    dos booleanos crus de `evidencia` (pre-histerese). `evidencia` entra so
    nos DETALHES — o percentual de dominancia, o delta da micro.

    O motivo e que os dois discordam de proposito. `_estagio_bruto` responde
    "o que este trade sustenta"; `_aplicar_persistencia` responde "o que
    ficou de pe". Ler os booleanos crus daria um placar `3/3` ao lado de um
    farol em `NA_REGIAO`, e um painel que se contradiz na mesma faixa de
    28px e pior que um painel que mostra menos.
    """
    rank = _RANK[estagio]
    bloqueio = evidencia.get("bloqueio")
    dominancia = evidencia.get("dominancia")

    if bloqueio == "magnitude_relativa":
        # O gate do WINFUT: percentual alto sobre magnitude pequena nao e
        # direcao do dia. Dizer POR QUE a condicao 1 caiu vale mais que
        # dizer que caiu — sem isso o operador ve 85% e um farol apagado.
        relativa = evidencia.get("magnitude_relativa")
        detalhe_1 = "MAGNITUDE " + (
            _pct(float(relativa)) if isinstance(relativa, (int, float)) else "—"
        )
    elif isinstance(dominancia, (int, float)):
        detalhe_1 = _pct(float(dominancia)) + " " + ROTULO_FAIXA[faixa]
    else:
        detalhe_1 = ROTULO_FAIXA[faixa]

    na_regiao = evidencia.get("na_regiao")
    if rank >= _RANK[EstagioSinal.NA_REGIAO]:
        detalhe_2 = "DENTRO"
    elif na_regiao is None:
        detalhe_2 = "—"
    else:
        detalhe_2 = "FORA"

    delta_micro = evidencia.get("delta_micro_segunda_metade")
    detalhe_3 = (
        formato.formatar_sinalizado(int(delta_micro))
        if isinstance(delta_micro, (int, float))
        else "—"
    )

    if rank >= _RANK[EstagioSinal.CONFIRMADO]:
        estado_3 = EstadoCondicao.SIM
    elif rank >= _RANK[EstagioSinal.PRE_SINAL]:
        estado_3 = EstadoCondicao.PARCIAL
    else:
        estado_3 = EstadoCondicao.NAO

    return (
        Condicao(
            "DIREÇÃO DO DIA",
            EstadoCondicao.SIM if rank >= 1 else EstadoCondicao.NAO,
            detalhe_1,
        ),
        Condicao(
            "REGIÃO",
            EstadoCondicao.SIM
            if rank >= _RANK[EstagioSinal.NA_REGIAO]
            else EstadoCondicao.NAO,
            detalhe_2,
        ),
        Condicao("MICRO", estado_3, detalhe_3),
    )


def _normalizar_taxa(taxa: float, volume: int) -> float:
    """Janela vazia e EQUILIBRIO, nao 100% vendedor.

    `MedidorAgressao.taxa_compra` devolve `0.0` quando nao ha volume atribuido
    na janela — o que e correto como aritmetica e desastroso como pixel: a
    barra sairia inteira vermelha antes do primeiro negocio do dia. O painel
    nunca deve inventar um lado a partir de uma divisao por zero."""
    if volume <= 0:
        return TAXA_NEUTRA
    return min(1.0, max(0.0, taxa))


def contexto_do_sinal(
    sinal: Sinal | None,
    *,
    saldo_dia: int = 0,
    taxa_compra_janela: float = TAXA_NEUTRA,
    volume_janela: int = 0,
    volume_nao_atribuido: int = 0,
    volume_comprador_dia: int = 0,
    volume_vendedor_dia: int = 0,
    faixa: FaixaConviccao | None = None,
) -> LeituraContexto:
    """`Sinal` -> `LeituraContexto`. Puro; nao toca em widget nem em Qt."""
    if sinal is None:
        estagio, direcao, evidencia = VAZIO.estagio, None, {}
    else:
        estagio, direcao = sinal.estagio, sinal.direcao
        evidencia = sinal.evidencia or {}
    if faixa is None:
        bruta = evidencia.get("faixa")
        faixa = FaixaConviccao(bruta) if isinstance(bruta, str) else VAZIO.faixa
    return LeituraContexto(
        estagio=estagio,
        direcao=direcao,
        faixa=faixa,
        condicoes=_condicoes_de(estagio, faixa, evidencia),
        saldo_dia=saldo_dia,
        taxa_compra_janela=_normalizar_taxa(taxa_compra_janela, volume_janela),
        volume_janela=max(0, volume_janela),
        volume_nao_atribuido=volume_nao_atribuido,
        volume_comprador_dia=max(0, volume_comprador_dia),
        volume_vendedor_dia=max(0, volume_vendedor_dia),
    )


def contexto_do_motor(
    motor,
    *,
    saldo_dia: int = 0,
    taxa_compra_janela: float = TAXA_NEUTRA,
    volume_janela: int = 0,
    volume_nao_atribuido: int = 0,
    volume_comprador_dia: int = 0,
    volume_vendedor_dia: int = 0,
) -> LeituraContexto:
    """Le o motor pelas propriedades publicas, quando nao ha `Sinal` na mao.

    Serve o caso em que a UI acorda no meio da sessao: `ao_sinal` so dispara
    na MUDANCA de estagio, entao um painel recem-aberto ficaria em branco ate
    o proximo evento — mostrando "sem confluencia" onde ha uma confluencia
    montada. Sem `evidencia`, os detalhes saem como `—`; o farol, que e o que
    importa, sai certo."""
    faixa = motor.faixa_atual
    estagio = motor.estagio_atual
    return LeituraContexto(
        estagio=estagio,
        direcao=motor.direcao_atual,
        faixa=faixa,
        condicoes=_condicoes_de(estagio, faixa, {}),
        saldo_dia=saldo_dia,
        taxa_compra_janela=_normalizar_taxa(taxa_compra_janela, volume_janela),
        volume_janela=max(0, volume_janela),
        volume_nao_atribuido=volume_nao_atribuido,
        volume_comprador_dia=max(0, volume_comprador_dia),
        volume_vendedor_dia=max(0, volume_vendedor_dia),
    )


def pressao_da_janela(medidor) -> tuple[float, int]:
    """`analytics/agressao.MedidorAgressao` -> `(taxa_compra, volume_atribuido)`.

    O denominador e o volume **atribuido** (compra + venda), nao o total: o
    volume RLP, cujo agressor a B3 nao divulga, nao pertence a nenhum dos dois
    lados e inflaria o denominador de uma proporcao entre eles. Ele aparece a
    parte, no medidor do dia, como `s/lado`."""
    atribuido = medidor.volume_total_janela - medidor.volume_nao_atribuido
    return medidor.taxa_compra, max(0, atribuido)


@dataclass(frozen=True, slots=True)
class LinhaPlayer:
    """Uma linha do ranking, ja reduzida ao que as duas barras usam."""

    nome: str
    volume_total: int
    saldo_liquido: int
    agressividade: float = 0.0

    @property
    def volume_compra(self) -> int:
        """`(total + saldo) / 2`. Exato em inteiros: `total = c + v` e
        `saldo = c - v` tem sempre a mesma paridade."""
        return (self.volume_total + self.saldo_liquido) // 2

    @property
    def volume_venda(self) -> int:
        return (self.volume_total - self.saldo_liquido) // 2

    @property
    def taxa_compra(self) -> float:
        """Parcela compradora do proprio volume, em [0, 1], 0,5 = equilibrio.

        E o que a barra desenha, e a escolha e a mesma que fez a janela de
        agressao virar barra particionada: **proporcao tem eixo absoluto**.
        Player sem volume e equilibrio, nao 100% vendedor — pela mesma razao
        que `_normalizar_taxa` existe para a janela."""
        if self.volume_total <= 0:
            return TAXA_NEUTRA
        return min(1.0, max(0.0, self.volume_compra / self.volume_total))


def players_de_ranking(ranking, top_n: int = 20) -> tuple[LinhaPlayer, ...]:
    """`analytics/brokers.RankingCorretoras` -> linhas, ja truncado."""
    return tuple(
        LinhaPlayer(nome, est.volume_total, est.saldo_liquido)
        for nome, est in ranking.ranking_por_volume(top_n)
    )


def players_de_perfil(perfil, top_n: int = 20) -> tuple[LinhaPlayer, ...]:
    """`microestrutura/perfil_player.PerfilPlayer` -> linhas, ja truncado.

    Traz `agressividade` junto, que o `RankingCorretoras` nao tem: e a
    fracao dos negocios do player em que ELE cruzou o spread. Dois players
    com o mesmo saldo e agressividades opostas sao coisas diferentes — um
    esta perseguindo o preco, o outro esta sendo servido."""
    return tuple(
        LinhaPlayer(s.broker, s.volume_total, s.saldo_liquido, s.agressividade)
        for s in perfil.ranking_por_volume(top_n)
    )


# --------------------------------------------------------------------------
# Escala — degraus fixos, com catraca. So para o que e ABSOLUTO.
# --------------------------------------------------------------------------
_MANTISSAS = (100, 125, 160, 200, 250, 320, 400, 500, 640, 800)

# A escada de escala (`DEGRAUS_ESCALA`) e a catraca (`escala_para`) moravam
# aqui. Foram removidas inteiras, e nao aposentadas em silencio, quando o
# medidor do dia deixou de ter escala: eram a ultima coisa no produto que
# fazia um comprimento depender de um eixo movel. O historico do defeito que
# elas causavam esta em `PainelHUD._desenhar_saldo_dia`.
#
# Nenhuma barra deste modulo tem escala hoje. As duas do `PainelHUD` e as
# vinte do `PainelPlayers` sao particionadas num eixo 0..100%, e a unica
# grandeza sem teto que a tela mostra — saldo em lotes, volume em lotes — sai
# como numero alinhado a direita.


def texto_direcional(valor: int) -> str:
    """Seta + valor com sinal: `▲ +42,3k`, `▼ −49,1k`, `· 0`.

    A funcao existe separada do desenho para poder ser afirmada em teste sem
    QApplication — e porque e literalmente a correcao de F2. Se um dia o
    painel voltar a grafar os dois lados igual, e aqui que se ve."""
    if valor > 0:
        seta = SETA_COMPRA
    elif valor < 0:
        seta = SETA_VENDA
    else:
        seta = SEM_LADO
    return seta + " " + formato.abreviar(valor)


def texto_pressao(taxa_compra: float, volume: int) -> str:
    """`▲ 63%` / `▼ 63%` / `· —`.

    O numero e SEMPRE a fatia do lado dominante, que e exatamente o segmento
    que a seta aponta na barra particionada — comprimento e numero dizem a
    mesma coisa. Mostrar sempre a fatia compradora obrigaria o leitor a
    inverter de cabeca metade das vezes; e mostrar a fatia dominante sem a
    seta seria a falha F2 de volta — `63%` e `63%` grafados igual para
    leituras opostas."""
    if volume <= 0:
        return SEM_LADO + " —"
    if taxa_compra > TAXA_NEUTRA:
        return SETA_COMPRA + " " + _pct(taxa_compra)
    if taxa_compra < TAXA_NEUTRA:
        return SETA_VENDA + " " + _pct(1.0 - taxa_compra)
    return SEM_LADO + " " + _pct(TAXA_NEUTRA)


def texto_direcao(direcao: Side | None) -> str:
    if direcao is Side.BUY:
        return SETA_COMPRA + " COMPRA"
    if direcao is Side.SELL:
        return SETA_VENDA + " VENDA"
    return SEM_LADO + " SEM LADO"


def _valor_direcional(direcao: Side | None) -> int:
    return 1 if direcao is Side.BUY else (-1 if direcao is Side.SELL else 0)


def _valor_da_taxa(taxa: float, volume: int) -> int:
    if volume <= 0 or taxa == TAXA_NEUTRA:
        return 0
    return 1 if taxa > TAXA_NEUTRA else -1


# --------------------------------------------------------------------------
# Painel — o HUD
# --------------------------------------------------------------------------
ALTURA_MEDIDOR = 36
ALTURA_FAROL = 64
ALTURA_CONDICAO = 18

BANDA_CABECALHO = 0
BANDA_SALDO_DIA = 1
BANDA_PRESSAO = 2
BANDA_FAROL = 3
BANDA_CONDICAO_0 = 4
N_BANDAS = BANDA_CONDICAO_0 + N_CONDICOES

MARGEM = 8
ALTURA_BARRA = 12
LARGURA_COSTURA = 2
"""Costura entre os dois segmentos da barra particionada.

Em `BG_BASE`, e nao um contorno claro: com cor, ela separa azul de vermelho;
**sem** cor, e a UNICA coisa que marca onde um lado acaba e o outro comeca,
porque `PALETA_SEM_COR` colapsa os dois no mesmo pixel. Dois pixels de largura
para sobreviver a reescala de 0,72 do canal (viram 1,4) — um pixel so seria
apagado pela interpolacao justamente na peca que carrega a leitura."""


class PainelHUD(PainelDenso):
    """Saldo do dia + pressao da janela + farol de estagio + placar.

    Altura fixa: e uma FAIXA, no sentido de HUD — mora na borda do espaco de
    trabalho e nunca disputa area com a grade. As barras querem largura, nao
    altura, entao a faixa e uma coluna estreita e alta, com barras de largura
    total, e nao uma tira horizontal onde cada medidor teria 80px.

    A sujeira e por BANDA, e as bandas sao um vetor de tamanho fixo
    (`N_BANDAS`). Mudar a pressao da janela repinta 36px de altura, nao 214 —
    e e o caso comum, porque a janela de agressao muda a cada negocio
    enquanto o farol passa minutos parado.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        rotulo_janela: str = "AGRESSÃO 5s",
    ) -> None:
        super().__init__(parent)
        self.densidade = densidade
        self.paleta = paleta
        self.rotulo_janela = rotulo_janela

        self._leitura = VAZIO
        self._rects: tuple[QRect, ...] = ()

        self.setFixedHeight(self.altura_natural)
        self.setMinimumWidth(240)
        self._recalcular_bandas(self.width())

    # ------------------------------------------------------------- geometria
    @property
    def altura_natural(self) -> int:
        return (
            self.densidade.altura_cabecalho
            + 2 * ALTURA_MEDIDOR
            + ALTURA_FAROL
            + N_CONDICOES * ALTURA_CONDICAO
        )

    def _recalcular_bandas(self, largura: int) -> None:
        alturas = (
            [self.densidade.altura_cabecalho, ALTURA_MEDIDOR, ALTURA_MEDIDOR, ALTURA_FAROL]
            + [ALTURA_CONDICAO] * N_CONDICOES
        )
        rects: list[QRect] = []
        y = 0
        for altura in alturas:
            rects.append(QRect(0, y, max(1, largura), altura))
            y += altura
        self._rects = tuple(rects)

    def ao_redimensionar(self, largura: int, altura: int) -> None:
        self._recalcular_bandas(largura)

    def rect_banda(self, indice: int) -> QRect:
        return self._rects[indice]

    def rect_barra(self, indice_banda: int) -> QRect:
        """A trilha de uma banda de medidor.

        Publica porque o teste recorta exatamente esta faixa: se a conta do
        recorte fosse escrita a parte, ela poderia divergir do desenho e o
        teste passaria a medir outra coisa sem avisar."""
        banda = self._rects[indice_banda]
        return QRect(
            banda.left() + MARGEM,
            banda.top() + 20,
            max(2, banda.width() - 2 * MARGEM),
            ALTURA_BARRA,
        )

    def rect_segmento(self, banda: QRect, indice: int) -> QRect:
        """Um segmento do farol. O CORRENTE e mais alto que os outros.

        A altura extra e um portador geometrico do "voce esta aqui": cor
        atravessa o canal bem, mas cor sozinha nao diz qual segmento e o
        ponteiro quando varios estao acesos. Quatro pixels de diferenca de
        altura sobrevivem a reescala; um rotulo de 9px, nao."""
        n = len(ORDEM_ESTAGIOS)
        vao = 4
        util = banda.width() - 2 * MARGEM - vao * (n - 1)
        largura = max(4, util // n)
        x = banda.left() + MARGEM + indice * (largura + vao)
        corrente = indice == _RANK[self._leitura.estagio]
        topo = banda.top() + (18 if corrente else 20)
        return QRect(x, topo, largura, 14 if corrente else 10)

    # ----------------------------------------------------------------- dados
    def aplicar(self, leitura: LeituraContexto) -> None:
        """Absorve uma leitura e suja **so** as bandas que mudaram."""
        anterior = self._leitura
        self._leitura = leitura
        sujas = [False] * N_BANDAS

        if (
            leitura.saldo_dia != anterior.saldo_dia
            or leitura.taxa_compra_dia != anterior.taxa_compra_dia
            or leitura.volume_dia != anterior.volume_dia
            or leitura.volume_nao_atribuido != anterior.volume_nao_atribuido
        ):
            sujas[BANDA_SALDO_DIA] = True
        if (
            leitura.taxa_compra_janela != anterior.taxa_compra_janela
            or leitura.volume_janela != anterior.volume_janela
        ):
            sujas[BANDA_PRESSAO] = True

        mudou_condicao = leitura.condicoes != anterior.condicoes
        if (
            leitura.estagio is not anterior.estagio
            or leitura.direcao is not anterior.direcao
            or mudou_condicao  # o placar "n/3" e desenhado na banda do farol
        ):
            sujas[BANDA_FAROL] = True
        if mudou_condicao:
            for i in range(N_CONDICOES):
                if leitura.condicoes[i] != anterior.condicoes[i]:
                    sujas[BANDA_CONDICAO_0 + i] = True

        for indice, suja in enumerate(sujas):
            if suja:
                self.marcar_sujo(self._rects[indice])

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if not self._rects:
            self._recalcular_bandas(self.width())
        for indice, rect in enumerate(self._rects):
            if not rect.intersects(regiao):
                continue
            self._desenhar_banda(painter, indice, rect)

    def _desenhar_banda(self, painter: QPainter, indice: int, rect: QRect) -> None:
        if indice == BANDA_CABECALHO:
            self._desenhar_cabecalho(painter, rect)
        elif indice == BANDA_SALDO_DIA:
            self._desenhar_saldo_dia(painter, rect)
        elif indice == BANDA_PRESSAO:
            self._desenhar_pressao(painter, rect)
        elif indice == BANDA_FAROL:
            self._desenhar_farol(painter, rect)
        else:
            self._desenhar_condicao(
                painter, rect, self._leitura.condicoes[indice - BANDA_CONDICAO_0]
            )

    def _desenhar_cabecalho(self, painter: QPainter, rect: QRect) -> None:
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM // 2, 0, -MARGEM // 2, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Contexto"
        )
        # Legenda do eixo, uma vez para os dois medidores. Em `TEXT_MUTED`
        # porque e conteudo REDUNDANTE — a seta e o sinal ja dizem o lado —,
        # que e a unica condicao em que §3.2 permite o token. E os glifos sao
        # os MESMOS do resto do produto: setas de meia-direita nao existem em
        # toda fonte de fallback, e uma legenda que vira caixa vazia numa
        # maquina sem Inter e pior que legenda nenhuma.
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            interno,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            SETA_VENDA + " venda   compra " + SETA_COMPRA,
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

    def _linha_rotulo(self, rect: QRect) -> QRect:
        return QRect(rect.left() + MARGEM, rect.top() + 4, rect.width() - 2 * MARGEM, 12)

    def _desenhar_veredito(
        self, painter: QPainter, linha: QRect, rotulo: str, texto: str, cor: QColor
    ) -> int:
        """Rotulo a esquerda, veredito a direita. Devolve a largura do rotulo."""
        fonte_rotulo = tokens.fonte_rotulo()
        painter.setFont(fonte_rotulo)
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            linha, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, rotulo
        )
        painter.setFont(tokens.fonte_numero(13, 600))
        painter.setPen(cor)
        painter.drawText(
            linha, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto
        )
        return metrica(fonte_rotulo).horizontalAdvance(rotulo)

    def _desenhar_saldo_dia(self, painter: QPainter, rect: QRect) -> None:
        """O saldo do dia: **numero** para a magnitude, **proporcao** para a
        geometria.

        Esta banda tinha uma barra bidirecional cujo comprimento era
        `saldo/escala`, com a escala numa catraca que nunca encolhe. Medido:

            saldo +2.200, escala  2.500  ->  133 px
            um pico de 9.000 leva a escala a 10.000, e ela FICA
            saldo +2.200, escala 10.000  ->   33 px

        Mesmo saldo, comprimento 4,0x menor, e o unico portador da mudanca
        era um `±2,5k` de 10px que o canal apaga. **O erro nao e perder a
        unidade do eixo — e a comparacao TEMPORAL**: o operador varre a tela,
        compara com a lembranca do quadro de vinte minutos atras, ve o trilho
        encolher a um quarto e conclui que a pressao compradora desabou,
        quando o saldo esta identico e quem mudou foi o eixo. Leitura
        invertida, nao unidade perdida — e por isso o argumento que sustentou
        este rotulo em duas rodadas ("perder o rotulo custa a unidade, nao a
        leitura") era falso: ele so valia para comparacao no ESPACO.

        E a mesma forma de defeito das outras duas vezes, deslocada do espaco
        para o tempo. A correcao e a mesma das outras duas: **tirar a
        necessidade da escala**, e nao engordar o rotulo nem acrescentar uma
        marca discreta. O saldo em lotes vira numero — que e onde grandeza sem
        teto pertence — e a geometria passa a mostrar a parcela compradora do
        pregao, limitada por natureza a 0..100%.

        A banda de baixo tem exatamente a mesma forma, e isso e deliberado:
        as duas respondem a mesma pergunta em horizontes diferentes, **no
        mesmo eixo**, entao comparar uma com a outra ("no pregao 53%
        comprador, nos ultimos 5 s 71%") passa a ser possivel e a ser certo.
        Duas barras parecidas so sao risco quando escondem eixos diferentes —
        que era precisamente o defeito da primeira rodada."""
        leitura = self._leitura
        valor = leitura.saldo_dia
        cor = self.paleta.direcional(valor)
        linha = self._linha_rotulo(rect)
        texto = texto_direcional(valor)
        largura_rotulo = self._desenhar_veredito(painter, linha, "SALDO DIA", texto, cor)

        if leitura.volume_dia:
            # O denominador, como na banda de baixo. `TEXT_MUTED` porque
            # perde-lo no canal nao produz leitura errada nenhuma: a proporcao
            # continua sendo a proporcao. E este e o teste que o `±2,5k` nao
            # passava — la o rotulo era a unica coisa que dizia o eixo.
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(linha.left() + largura_rotulo + 8, linha.top(), 80, linha.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "de " + formato.abreviar(leitura.volume_dia, com_sinal=False),
            )
        if leitura.volume_nao_atribuido:
            # RLP: volume real cujo agressor a B3 nao divulga. Sem isto o
            # saldo pareceria o retrato completo do dia quando nao e.
            largura_valor = metrica(tokens.fonte_numero(13, 600)).horizontalAdvance(
                texto
            )
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                linha.adjusted(0, 0, -largura_valor - 8, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "s/lado " + formato.abreviar(leitura.volume_nao_atribuido, com_sinal=False),
            )

        self._desenhar_barra_particionada(
            painter,
            self.rect_barra(BANDA_SALDO_DIA),
            leitura.taxa_compra_dia,
            leitura.volume_dia,
        )

    def _desenhar_pressao(self, painter: QPainter, rect: QRect) -> None:
        leitura = self._leitura
        taxa, volume = leitura.taxa_compra_janela, leitura.volume_janela
        cor = self.paleta.direcional(_valor_da_taxa(taxa, volume))
        linha = self._linha_rotulo(rect)
        largura_rotulo = self._desenhar_veredito(
            painter, linha, self.rotulo_janela, texto_pressao(taxa, volume), cor
        )

        if volume:
            # "63% de que?" — o denominador. Em `TEXT_MUTED` porque perder
            # este numero no canal nao produz leitura errada nenhuma: a
            # proporcao continua sendo a proporcao.
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(linha.left() + largura_rotulo + 8, linha.top(), 80, linha.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "de " + formato.abreviar(volume, com_sinal=False),
            )

        self._desenhar_barra_particionada(
            painter, self.rect_barra(BANDA_PRESSAO), taxa, volume
        )

    def _desenhar_barra_particionada(
        self, painter: QPainter, trilha: QRect, taxa: float, volume: int
    ) -> None:
        """Sempre cheia; o que muda e ONDE ela se parte.

        Nao ha escala, entao nao ha escala para o canal apagar nem para o
        leitor comparar errado com a barra de cima. A trilha ocupa a mesma
        largura em todo quadro: a unica variavel e a posicao da costura.
        """
        painter.fillRect(trilha, tokens.BG_RAISED)
        meio = trilha.left() + trilha.width() // 2
        if volume > 0:
            corte = trilha.left() + int(round(taxa * trilha.width()))
            corte = min(max(corte, trilha.left()), trilha.right() + 1)
            largura_compra = corte - trilha.left()
            if largura_compra > 0:
                painter.fillRect(
                    QRect(trilha.left(), trilha.top(), largura_compra, trilha.height()),
                    self.paleta.compra,
                )
            largura_venda = trilha.right() + 1 - corte
            if largura_venda > 0:
                painter.fillRect(
                    QRect(corte, trilha.top(), largura_venda, trilha.height()),
                    self.paleta.venda,
                )
            # A costura. Ver `LARGURA_COSTURA`: e o que mantem a particao
            # visivel quando as duas cores colapsam numa so.
            painter.fillRect(
                QRect(
                    corte - LARGURA_COSTURA // 2,
                    trilha.top(),
                    LARGURA_COSTURA,
                    trilha.height(),
                ),
                tokens.BG_BASE,
            )

        # A referencia de 50%, FORA da barra: dentro, ela seria pintada por
        # cima por um dos dois lados justamente quando estivesse perto da
        # costura, que e quando mais importa.
        painter.setPen(tokens.BORDER_STRONG)
        painter.drawLine(meio, trilha.top() - 3, meio, trilha.top() - 1)
        painter.drawLine(meio, trilha.bottom() + 1, meio, trilha.bottom() + 3)

    def _desenhar_farol(self, painter: QPainter, rect: QRect) -> None:
        leitura = self._leitura
        rank = _RANK[leitura.estagio]
        cor = cor_do_estagio(leitura.estagio)

        linha = self._linha_rotulo(rect)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            linha, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Farol"
        )
        painter.setFont(tokens.fonte_ui(11, 600))
        painter.setPen(self.paleta.direcional(_valor_direcional(leitura.direcao)))
        painter.drawText(
            linha,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            texto_direcao(leitura.direcao),
        )

        for i, estagio in enumerate(ORDEM_ESTAGIOS):
            segmento = self.rect_segmento(rect, i)
            if i <= rank:
                # Cada segmento na cor do PROPRIO estagio, e nao todos na cor
                # do corrente. Com uma cor so, `CONFIRMADO` virava um bloco
                # roxo unico e `PRE_SINAL` um bloco ambar unico: depois do
                # canal, distinguir os dois dependia de contar cinco blocos
                # contra quatro por cima de vaos de 4px que a reescala come.
                # Com a rampa, o ULTIMO segmento aceso diz o estagio por cor,
                # e a rampa inteira diz o caminho andado.
                painter.fillRect(segmento, cor_do_estagio(estagio))
            else:
                painter.fillRect(segmento, tokens.BG_RAISED)
                painter.setPen(tokens.BORDER)
                painter.drawRect(segmento.adjusted(0, 0, -1, -1))
            painter.setFont(tokens.fonte_rotulo(9))
            painter.setPen(tokens.TEXT_PRIMARY if i == rank else tokens.TEXT_MUTED)
            painter.drawText(
                QRect(segmento.left(), rect.top() + 34, segmento.width(), 10),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                ROTULO_CURTO[estagio],
            )

        linha_nome = QRect(rect.left() + MARGEM, rect.top() + 48, rect.width() - 2 * MARGEM, 12)
        painter.setFont(tokens.fonte_ui(11, 600))
        painter.setPen(cor)
        painter.drawText(
            linha_nome,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ROTULO_LONGO[leitura.estagio],
        )
        painter.setFont(tokens.fonte_numero(11, 600))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            linha_nome,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{leitura.n_satisfeitas}/{N_CONDICOES}",
        )
        painter.setPen(tokens.BORDER)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

    def _desenhar_condicao(self, painter: QPainter, rect: QRect, condicao: Condicao) -> None:
        cor = _cor_da_condicao(condicao.estado)
        painter.setFont(tokens.fonte_numero(11))
        painter.setPen(cor)
        painter.drawText(
            QRect(rect.left() + MARGEM, rect.top(), 14, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            condicao.estado.glifo,
        )
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(
            tokens.TEXT_SECONDARY if condicao.estado is EstadoCondicao.NAO else tokens.TEXT_PRIMARY
        )
        painter.drawText(
            QRect(rect.left() + MARGEM + 18, rect.top(), rect.width(), rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            condicao.rotulo,
        )
        painter.setFont(tokens.fonte_numero(11))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width() - MARGEM, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            condicao.detalhe,
        )


# --------------------------------------------------------------------------
# Painel — o ranking de players
# --------------------------------------------------------------------------
TOP_N_PADRAO = 20
"""Vinte, e nao dez. §1 elogia justamente isto na referencia — "20 corretoras
x 5 colunas numericas em ~400px de altura, sem padding decorativo" — e
`bar/09_tape_reading_b.png` chega a 24 linhas. A pizza de
`01_times_trades_a.png` so consegue mostrar 10 fatias mais uma categoria
"Outras" que apaga nove players dentro de uma unica cor. Barra horizontal nao
tem esse teto: a vigesima linha custa 18px e nenhuma tinta a mais."""

LARGURA_NOME = 84
LARGURA_VOLUME = 52
LARGURA_SALDO = 56
"""Piso da coluna de saldo. A largura REAL sai de `QFontMetrics` sobre
`MOLDE_SALDO` (ver `PainelPlayers._largura_saldo`), e a diferenca entre as
duas ja custou um defeito: com 56px cravados, `▲ +200,0k` transbordava a
coluna e pintava glifos azuis POR CIMA da barra do vizinho. A tela ficava com
uma barra que nao era barra, e nenhum teste de comportamento pegaria isso —
pegou o teste que recorta a barra e compara pixels."""

MOLDE_SALDO = "▼ −999,9k"
"""O maior saldo plausivel, usado so para MEDIR a coluna. Medir e melhor que
cravar por dois motivos: a fonte muda entre maquinas (Iosevka, JetBrains,
Consolas tem avancos diferentes) e a densidade muda o corpo. Um numero
cravado esta certo numa combinacao e errado nas outras."""

LARGURA_AGRESSIVIDADE = 40
LARGURA_MINIMA_COM_AGRESSIVIDADE = 500
"""Abaixo disto a coluna de agressividade SAI (F8: rotulo de coluna nunca
trunca; se nao cabe, a coluna nao aparece). Nunca `Agressiv…`."""

ALTURA_BARRA_PLAYER = 8
LARGURA_MINIMA_BARRA = 24
ESPESSURA_ESPINHA = 2


class PainelPlayers(PainelDenso):
    """Ranking de players — uma coluna de barras particionadas, zero pizzas.

    ## O defeito que esta forma existe para nao ter

    Este painel errou a MESMA coisa tres vezes, e as duas primeiras correcoes
    so mudaram o problema de andar:

    1. **Comprimento = volume, preenchimento = parcela compradora, tique na
       metade.** Legivel nos tres primeiros players; na cauda a trilha tinha
       10px e o tique deixava de ser discriminavel.
    2. **Barra de vies bidirecional com piso de 3px.** Medido: contra saldos
       de `+8,2k` a `−37` — 222x de intervalo —, **dezenove das vinte barras
       ficavam em exatamente 3px**. O que desmentia a fileira de tracos iguais
       era a palavra `VIÉS` em corpo 10, que o canal apaga.
    3. **Duas asas com comprimento = volume de cada lado.** Melhor, e ainda
       errado: o volume de um ranking de corretoras varre ~500x
       (`09_tape_reading_b.png` vai de 10,23% a 0,02% de participacao). Com
       500x, a asa da vigesima linha nao fica pequena — ela arredonda para
       **zero** e a linha some.

    As tres sao a mesma falha, e e a falha da primeira rodada desta peca
    tambem, nos medidores empilhados: **uma grandeza de variacao enorme
    desenhada como comprimento, com um rotulo pequeno encarregado de desfazer
    a confusao que sobra.** Piso, normalizacao, rotulo e ate a decomposicao em
    parcelas sao remendos enquanto a grandeza continuar sendo um comprimento.

    ## A saida: tirar a grandeza de 500x da geometria

    A regra que ficou: **comprimento serve a grandezas limitadas; numero serve
    a grandezas que varrem ordens de magnitude.** §3.4 ja dizia metade disso
    (numeros a direita, unidade fixa por coluna, algarismos tabulares) e
    `bar/09_tape_reading_b.png`, a tela mais densa do acervo, faz exatamente
    isso: nenhuma barra, colunas numericas alinhadas. Um numero le 500x sem
    esforco; uma barra, nunca.

    Entao:

    * **o volume virou coluna numerica** (`54,0k`, `2,9k`), alinhada a direita
      com unidade fixa — e a lista continua ordenada por ele, entao a ordem se
      le na coluna;
    * **a barra ficou so com a proporcao** compra x venda do proprio player,
      que e **limitada por natureza** (0..100%, 50% no meio) e por isso nao
      tem escala, nao tem piso e nao tem rotulo carregando a leitura.

    ## Por que particionada de largura fixa, e nao bidirecional

    Porque bidirecional-a-partir-de-um-zero e a forma reservada ao saldo do
    dia (ver a tabela no topo do modulo), e usar a mesma geometria para uma
    proporcao foi exatamente a colisao apontada na rodada 2.

    E porque a leitura fica melhor. Todas as barras tem a mesma largura, entao
    o que varia e **onde elas se partem** — e as costuras formam uma linha
    quebrada contra a espinha reta de 50%. Achar o player anomalo vira
    procurar o maior desvio de um alinhamento, que e a coisa mais sensivel que
    a visao humana faz (acuidade vernier), e que sobrevive ao canal porque
    depende de duas bordas duras e nao de medir um comprimento pequeno contra
    uma referencia distante.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        densidade: tokens.Densidade = tokens.PADRAO,
        paleta: tokens.Paleta = tokens.PALETA_COR,
        top_n: int = TOP_N_PADRAO,
    ) -> None:
        super().__init__(parent)
        self.densidade = densidade
        self.paleta = paleta
        self.top_n = max(1, top_n)

        # Nao ha `_escala` nenhuma nesta classe, e a ausencia e o resultado
        # que importa: a unica grandeza desenhada e limitada por natureza.
        self._linhas: tuple[LinhaPlayer, ...] = ()
        self._largura_saldo_cache: int | None = None
        self.setMinimumSize(220, 120)

    # ------------------------------------------------------------- geometria
    @property
    def _y_corpo(self) -> int:
        return self.densidade.altura_cabecalho

    @property
    def mostra_agressividade(self) -> bool:
        return self.width() >= LARGURA_MINIMA_COM_AGRESSIVIDADE

    @property
    def _largura_saldo(self) -> int:
        """Largura MEDIDA da coluna de saldo. Ver `MOLDE_SALDO`.

        Memoizada pelo mesmo motivo dos `QColor` de `tokens.py`: medir texto
        e barato uma vez e caro por linha por quadro."""
        if self._largura_saldo_cache is None:
            self._largura_saldo_cache = max(
                LARGURA_SALDO,
                metrica(
                    tokens.fonte_numero(self.densidade.fonte_grade, 600)
                ).horizontalAdvance(MOLDE_SALDO)
                + 4,
            )
        return self._largura_saldo_cache

    def rect_linha(self, indice: int) -> QRect:
        altura = self.densidade.altura_linha
        return QRect(0, self._y_corpo + indice * altura, max(1, self.width()), altura)

    @property
    def _x_barra(self) -> int:
        return MARGEM + LARGURA_NOME + 4

    @property
    def _largura_barra(self) -> int:
        reservado = (
            (LARGURA_AGRESSIVIDADE + 4 if self.mostra_agressividade else 0)
            + (LARGURA_VOLUME + 4)
            + (self._largura_saldo + MARGEM)
            + 4
        )
        return max(LARGURA_MINIMA_BARRA, self.width() - self._x_barra - reservado)

    def rect_barra(self, indice: int) -> QRect:
        """A barra da linha. Largura FIXA — a mesma em todas as vinte.

        Publica porque o teste recorta e MEDE exatamente esta faixa: se a
        conta do recorte fosse escrita a parte, ela poderia divergir do
        desenho e o teste passaria a medir outra coisa sem avisar."""
        linha = self.rect_linha(indice)
        return QRect(
            self._x_barra,
            linha.top() + (linha.height() - ALTURA_BARRA_PLAYER) // 2,
            self._largura_barra,
            ALTURA_BARRA_PLAYER,
        )

    def x_costura(self, taxa_compra: float) -> int:
        """Onde a barra se parte, para uma dada parcela compradora.

        Publica, e usada TANTO pelo desenho QUANTO pela medicao do teste. A
        razao esta escrita em sangue: a primeira versao do teste-guarda media
        o desvio contra `rect_barra().center().x()` — `left + (w-1)//2` — que
        e um marco que o desenho **nao usa**. O off-by-one de um pixel
        rebaixava o menor desvio nao nulo de 3 para 2 e fazia a assercao
        anti-piso passar raspando: o guarda pegava piso de 4, 5 e 6px e
        deixava passar exatamente o de 3px, que e o unico que ja existiu no
        produto. Marco de teste e marco de desenho tem de ser a mesma funcao,
        pelo mesmo motivo que o recorte vem de `rect_barra`."""
        barra = self.rect_barra(0)
        corte = barra.left() + int(round(taxa_compra * barra.width()))
        return min(max(corte, barra.left()), barra.right() + 1)

    @property
    def _x_volume(self) -> int:
        return self.width() - MARGEM - self._largura_saldo - 4 - LARGURA_VOLUME

    @property
    def _x_agressividade(self) -> int:
        return self._x_volume - 4 - LARGURA_AGRESSIVIDADE

    @property
    def n_visiveis(self) -> int:
        util = max(0, self.height() - self._y_corpo)
        return max(0, util // self.densidade.altura_linha)

    # ----------------------------------------------------------------- dados
    def aplicar(self, linhas: tuple[LinhaPlayer, ...]) -> None:
        """Absorve o ranking. **Trunca na entrada**, nunca no desenho.

        Truncar so no desenho deixaria o painel segurando a lista inteira de
        corretoras da sessao — o defeito de estrutura que cresce, escondido
        atras de uma tela que parece limitada.

        Repare no que NAO acontece aqui: nao ha recalculo de escala, e por
        isso nao ha o caso "um player cresceu, repinta as vinte linhas". Sem
        escala compartilhada, mudanca de uma linha e sujeira de uma linha."""
        novas = tuple(linhas[: self.top_n])
        anteriores = self._linhas
        self._linhas = novas
        if self._tudo_sujo:
            return
        if len(novas) != len(anteriores):
            self.marcar_tudo_sujo()
            return
        for i, (nova, antiga) in enumerate(zip(novas, anteriores)):
            if nova != antiga:
                self.marcar_sujo(self.rect_linha(i))

    # --------------------------------------------------------------- desenho
    def desenhar(self, painter: QPainter, regiao: QRect) -> None:
        painter.fillRect(regiao, self.cor_fundo)
        if regiao.top() < self._y_corpo:
            self._desenhar_cabecalho(painter)
        if not self._linhas:
            painter.setFont(tokens.fonte_ui(14))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(regiao, Qt.AlignmentFlag.AlignCenter, "SEM PLAYERS")
            return
        altura = self.densidade.altura_linha
        limite = min(self.n_visiveis, len(self._linhas))
        if limite <= 0:
            return
        # A espinha ANTES das barras, de proposito. Ela e a referencia de 50%
        # contra a qual as costuras sao lidas; desenhada por cima, cobriria a
        # costura justamente quando as duas estao perto — que e quando a
        # leitura importa. Desenhada por baixo, ela aparece nos 10px de
        # respiro entre uma barra e a proxima, forma uma linha tracejada forte
        # ao longo da coluna, e nunca disputa pixel com o dado.
        self._desenhar_espinha(painter, regiao, limite)
        primeira = max(0, (regiao.top() - self._y_corpo) // altura)
        ultima = min(limite - 1, (regiao.bottom() - self._y_corpo) // altura)
        for indice in range(primeira, ultima + 1):
            self._desenhar_linha(painter, indice, self._linhas[indice])

    def _desenhar_espinha(self, painter: QPainter, regiao: QRect, limite: int) -> None:
        """O eixo de 50% da coluna, continuo do cabecalho ao fim da lista.

        Uma linha unica, e nao um tracinho por linha: e o que transforma vinte
        barras isoladas numa escala vernier, e e o elemento do painel que
        melhor atravessa o canal — um traco vertical de centenas de pixels
        contra glifos de 10px."""
        if limite <= 0:
            return
        x = self.rect_barra(0).center().x()
        topo = max(regiao.top(), self._y_corpo)
        base = min(regiao.bottom(), self.rect_linha(limite - 1).bottom())
        if base <= topo:
            return
        # DOIS pixels, e nao um. `BORDER_STRONG` da 2,07:1 contra a
        # superficie — suficiente num monitor e magro depois da reescala de
        # 0,72 do canal. Largura compra o que contraste nao pode comprar sem
        # inventar token: 2px viram 1,4 e sobrevivem. E esta linha nao e
        # enfeite de grade; e a referencia contra a qual as vinte costuras sao
        # lidas, entao ela e o pixel mais importante da coluna.
        painter.fillRect(
            QRect(x, topo, ESPESSURA_ESPINHA, base - topo + 1), tokens.BORDER_STRONG
        )

    def _desenhar_cabecalho(self, painter: QPainter) -> None:
        rect = QRect(0, 0, self.width(), self._y_corpo)
        painter.fillRect(rect, tokens.BG_RAISED)
        interno = rect.adjusted(MARGEM // 2, 0, -MARGEM // 2, 0)
        painter.setFont(tokens.fonte_rotulo())
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            interno, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Players"
        )
        painter.drawText(
            QRect(
                self.width() - MARGEM - self._largura_saldo,
                0,
                self._largura_saldo,
                self._y_corpo,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "Saldo",
        )
        painter.drawText(
            QRect(self._x_volume, 0, LARGURA_VOLUME, self._y_corpo),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "Volume",
        )
        # Legenda do eixo, com os MESMOS glifos do resto do produto. Em
        # `TEXT_MUTED` porque e redundante: o lado ja esta na posicao do
        # segmento. E nao ha escala a escrever — este eixo e 0..100%, e um
        # eixo absoluto nao tem o que o canal apague.
        barra = self.rect_barra(0)
        painter.setPen(tokens.TEXT_MUTED)
        painter.drawText(
            QRect(barra.left(), 0, barra.width(), self._y_corpo),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            SETA_VENDA + " venda   50%   compra " + SETA_COMPRA,
        )
        if self.mostra_agressividade:
            painter.drawText(
                QRect(self._x_agressividade, 0, LARGURA_AGRESSIVIDADE, self._y_corpo),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "Agr",
            )
        painter.setPen(tokens.BORDER)
        painter.drawLine(0, self._y_corpo - 1, self.width(), self._y_corpo - 1)

    def _desenhar_linha(self, painter: QPainter, indice: int, linha: LinhaPlayer) -> None:
        rect = self.rect_linha(indice)
        altura = rect.height()
        cor = self.paleta.direcional(linha.saldo_liquido)

        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade))
        painter.setPen(tokens.TEXT_PRIMARY)
        painter.drawText(
            QRect(rect.left() + MARGEM, rect.top(), LARGURA_NOME, altura),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            linha.nome[:10],
        )

        # ---------------------------------------------- a barra particionada
        # Mesma geometria da barra de pressao do HUD, e de proposito: mesma
        # pergunta (proporcao entre dois lados), mesma forma, mesma leitura.
        barra = self.rect_barra(indice)
        painter.fillRect(barra, tokens.BG_RAISED)
        if linha.volume_total > 0:
            corte = self.x_costura(linha.taxa_compra)
            if corte > barra.left():
                painter.fillRect(
                    QRect(barra.left(), barra.top(), corte - barra.left(), barra.height()),
                    self.paleta.compra,
                )
            if corte <= barra.right():
                painter.fillRect(
                    QRect(corte, barra.top(), barra.right() + 1 - corte, barra.height()),
                    self.paleta.venda,
                )
            # A costura: com cor, separa azul de vermelho; SEM cor, e a unica
            # coisa que marca onde um lado acaba e o outro comeca. Ver
            # `LARGURA_COSTURA`.
            painter.fillRect(
                QRect(
                    corte - LARGURA_COSTURA // 2,
                    barra.top(),
                    LARGURA_COSTURA,
                    barra.height(),
                ),
                tokens.BG_BASE,
            )

        painter.setFont(tokens.fonte_numero(10))
        painter.setPen(tokens.TEXT_SECONDARY)
        painter.drawText(
            QRect(self._x_volume, rect.top(), LARGURA_VOLUME, altura),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            formato.abreviar(linha.volume_total, com_sinal=False),
        )

        if self.mostra_agressividade:
            painter.setFont(tokens.fonte_numero(10))
            painter.setPen(tokens.TEXT_MUTED)
            painter.drawText(
                QRect(self._x_agressividade, rect.top(), LARGURA_AGRESSIVIDADE, altura),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _pct(linha.agressividade),
            )

        painter.setFont(tokens.fonte_numero(self.densidade.fonte_grade, 600))
        painter.setPen(cor)
        # Retangulo LIMITADO a propria coluna, e nao "do zero ate a margem".
        # Com o rect largo, um saldo comprido nao transbordava para o vazio —
        # transbordava para cima da barra do lado, e o Qt nao tem como saber
        # que aquilo ali ja e outra coisa.
        painter.drawText(
            QRect(
                rect.width() - MARGEM - self._largura_saldo,
                rect.top(),
                self._largura_saldo,
                altura,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            texto_direcional(linha.saldo_liquido),
        )
