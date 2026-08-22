"""Saída em texto: uma linha por sinal/detecção, com a EVIDÊNCIA visível.

A UI gráfica é trabalho de outra rodada (a stack está decidida em
`design/direcao_visual.md`: PySide6 + pyqtgraph). Isto aqui é a saída de
referência — e ela não é um placeholder: é o formato que prova a promessa do
produto.

## Por que a evidência aparece na linha, e não atrás de um `--verbose`

O projeto inteiro se apoia em "o usuário pode auditar por que algo foi
sinalizado". Um alerta que diz apenas `ABSORCAO COMPRA @5000.5` pede fé.
`DetectorAbsorcao` já devolve `volume_agressao_dominante`,
`volume_lado_oposto`, `deslocamento_ticks` e `n_trades_janela`; o
`MotorSinais` já devolve `dominancia`, `magnitude_relativa`, `na_regiao` e as
duas metades do delta da micro. Esconder isso deixaria o dicionário
`evidencia` — construído com custo em todo o caminho quente — sem consumidor,
e a promessa sem lastro. Então a evidência vai na mesma linha, resumida por
uma lista de campos por tipo de evento (`_CAMPOS_*`), na ordem em que se lê a
decisão.

## Observado × inferido

`[OBS]` quando `confianca == 1.0` (o gatilho foi tape impresso ou feed MBO
real); `[INF 0.85]` quando é hipótese. A distinção é a virtude declarada do
projeto e um `[INF]` que só aparecesse num log de debug não seria distinção
nenhuma. Não há terceira marca: ou o número é 1.0, ou não é.

## Critério de crescimento aplicado a `ConsoleFluxo.linhas`

*"Qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão
continua?"* — o critério do docstring de `_registrar_preco`
(`microestrutura/inferencia_mbp.py`).

`self.linhas` era uma `list` sem teto, alimentada uma vez por sinal e uma vez
por detecção. A resposta ao critério era **"o número de detecções e sinais do
pregão"**, e ela não para de crescer. O comentário de `_escrever` dizia
"eventos raros (dezenas por sessão, não por segundo)" e isso **está errado
como ordem de grandeza**: `criticas/nucleo_r5.md` §C.3 mediu 11.054 detecções
em 500.000 eventos — 2,2% dos eventos, não dezenas por sessão. Medido
(`.mut/sonda_r6b_crescimento.py`, `tracemalloc`):

    184 B/linha  ->  pregao 6 h a  5.000 ev/s = 2,39 M linhas = 0,44 GB
                     pregao 6 h a 10.000 ev/s = 4,78 M linhas = 0,88 GB

E `scripts/operar.py` **nunca lia `linhas`**: era meio giga de retenção para
ninguém. Duas correções, porque o buraco tinha duas metades:

* aqui, `linhas` virou um **anel limitado** (`deque(maxlen=...)`): a resposta
  ao critério passa a ser a constante `LIMITE_LINHAS_GUARDADAS`. O buffer
  responde "as últimas N linhas", que é o que um painel de log de UI quer —
  ninguém rola até a linha 2.000.000;
* no CLI, `guardar_linhas=False`, porque lá o consumidor real é o `stream`.
"""

from __future__ import annotations

import sys
from collections import deque
from typing import IO, Iterable, Mapping

from fluxopro.app.sessao_fluxo import DeteccaoAnotada, SessaoFluxo
from fluxopro.core.eventos import PriceGrid, Side
from fluxopro.microestrutura.eventos_mbo import CONFIANCA_OBSERVADO
from fluxopro.motor.sinais import EstagioSinal, Sinal

NS_POR_SEGUNDO = 1_000_000_000

LIMITE_LINHAS_GUARDADAS = 5_000
"""Teto do anel de `ConsoleFluxo.linhas` (ver "Critério de crescimento").

Não é calibração de produto — é a grandeza que substitui "número de eventos"
como limite do `len`. 5.000 linhas ≈ 0,9 MB e cobre com folga qualquer teste e
qualquer painel de log que se role à mão."""

# Campos da evidência mostrados em linha, por tipo de evento, na ordem de
# leitura da decisão. Campo ausente é simplesmente pulado (nem todo estágio
# produz toda evidência: um `NENHUM` bloqueado por magnitude não chega a
# avaliar região nem micro).
_CAMPOS_SINAL: tuple[str, ...] = (
    "dominancia",
    "magnitude",
    "magnitude_relativa",
    "bloqueio",
    "na_regiao",
    "micro_virou",
    "pre_sinal",
    "delta_micro_primeira_metade",
    "delta_micro_segunda_metade",
    "estagio_bruto",
    "persistencia_trades",
    "volume_nao_atribuido",
)

_ABREVIACOES: Mapping[str, str] = {
    "dominancia": "dom",
    "magnitude": "mag",
    "magnitude_relativa": "mag_rel",
    "na_regiao": "regiao",
    "micro_virou": "micro",
    "delta_micro_primeira_metade": "micro_1a",
    "delta_micro_segunda_metade": "micro_2a",
    "estagio_bruto": "bruto",
    "persistencia_trades": "persist",
    "volume_nao_atribuido": "vol_nao_atrib",
    "volume_agressao_dominante": "vol_dom",
    "volume_lado_oposto": "vol_oposto",
    "deslocamento_ticks": "desloc_t",
    "n_trades_janela": "n_janela",
    "volume_inicio_janela": "vol_ini",
    "volume_fim_janela": "vol_fim",
    "queda_relativa": "queda",
    "cv_quantidade": "cv_qty",
    "cv_intervalo": "cv_int",
    "qty_total_atual": "qty_nivel",
    "n_reposicoes": "reposicoes",
    "qty_original": "qty_orig",
    "qty_executada": "qty_exec",
    "n_recargas": "recargas",
}

_DIRECAO: Mapping[Side, str] = {Side.BUY: "COMPRA", Side.SELL: "VENDA"}


def formatar_hora(timestamp_ns: int) -> str:
    """`HH:MM:SS.mmm` a partir do timestamp do evento.

    Sem fuso e sem data de propósito: em feed ao vivo o timestamp é epoch UTC
    e isto vira a hora do pregão; em replay do simulador ele começa em 0 e isto
    vira o tempo decorrido de tape. Os dois casos são legíveis, e converter
    para data completa faria o simulador imprimir `1970-01-01` em toda linha.
    """
    total_ms = timestamp_ns // 1_000_000
    ms = total_ms % 1000
    total_s = total_ms // 1000
    return f"{total_s // 3600 % 24:02d}:{total_s // 60 % 60:02d}:{total_s % 60:02d}.{ms:03d}"


def _fmt_valor(valor: object) -> str:
    if isinstance(valor, bool):
        return "sim" if valor else "nao"
    if isinstance(valor, float):
        return f"{valor:.3f}"
    return str(valor)


def formatar_evidencia(
    evidencia: Mapping[str, object], campos: Iterable[str] | None = None
) -> str:
    """`chave=valor` separado por espaço, só com o que existe na evidência.

    `campos=None` mostra a evidência inteira na ordem em que o produtor a
    montou — é o caso dos detectores, cujas evidências já são curtas e cuja
    ordem já é a ordem do raciocínio.
    """
    chaves = list(campos) if campos is not None else list(evidencia.keys())
    partes = [
        f"{_ABREVIACOES.get(chave, chave)}={_fmt_valor(evidencia[chave])}"
        for chave in chaves
        if chave in evidencia
    ]
    return " ".join(partes)


def marca_confianca(confianca: float) -> str:
    if confianca >= CONFIANCA_OBSERVADO:
        return "[OBS]"
    return f"[INF {confianca:.2f}]"


class ConsoleFluxo:
    """Consumidor de sinais e detecções que imprime linhas auditáveis.

    Guarda as últimas `limite_linhas` linhas em `linhas` além de escrever no
    `stream` — assim o teste verifica o formato sem capturar stdout, e uma UI
    futura pode reusar o mesmo formatador para o painel de log.

    `linhas` é um anel (`deque` com `maxlen`), não uma lista sem fim: ver
    "Critério de crescimento" na docstring do módulo. Quem não vai ler o
    buffer — o CLI é o caso — passa `guardar_linhas=False` e não paga nada.
    """

    def __init__(
        self,
        grid: PriceGrid,
        stream: IO[str] | None = None,
        guardar_linhas: bool = True,
        mostrar_estagio_nenhum: bool = False,
        limite_linhas: int = LIMITE_LINHAS_GUARDADAS,
    ) -> None:
        self.grid = grid
        self.stream = stream if stream is not None else sys.stdout
        self.guardar_linhas = guardar_linhas
        self.mostrar_estagio_nenhum = mostrar_estagio_nenhum
        self.linhas: deque[str] = deque(maxlen=limite_linhas)

    # ------------------------------------------------------------------
    def ao_sinal(self, sinal: Sinal) -> None:
        if sinal.estagio is EstagioSinal.NENHUM and not self.mostrar_estagio_nenhum:
            return
        direcao = _DIRECAO.get(sinal.direcao, "-") if sinal.direcao else "-"
        faixa = str(sinal.evidencia.get("faixa", "-"))
        linha = (
            f"{formatar_hora(sinal.timestamp_ns)}  SINAL     "
            f"{sinal.estagio.value:<19} {direcao:<6} {faixa:<17} "
            f"| {formatar_evidencia(sinal.evidencia, _CAMPOS_SINAL)}"
        )
        self._escrever(linha)

    def ao_deteccao(self, anotada: DeteccaoAnotada) -> None:
        det = anotada.deteccao
        direcao = _DIRECAO.get(det.side, "-")
        preco = "-" if det.price is None else f"{self.grid.to_price(det.price):g}"
        linha = (
            f"{formatar_hora(det.timestamp_ns)}  DETECCAO  "
            f"{det.tipo.value:<19} {direcao:<6} @{preco:<10} "
            f"{marca_confianca(anotada.confianca_efetiva):<11} "
            f"| {formatar_evidencia(det.evidencia)}"
        )
        self._escrever(linha)

    # ------------------------------------------------------------------
    def cabecalho(self, sessao: SessaoFluxo) -> None:
        cfg = sessao.config
        estagios = [
            nome
            for nome, ligado in (
                ("analytics", cfg.ligar_analytics),
                ("microestrutura", cfg.ligar_microestrutura),
                ("detectores_tape", cfg.ligar_detectores_tape),
                ("motor", cfg.ligar_motor),
            )
            if ligado
        ]
        # Só ASCII no que vai para o console: o terminal padrão do Windows é
        # cp1252 e transforma travessão/acento em `?` — a saída ficaria feia
        # justamente na primeira linha que o dono vê.
        self._escrever(
            f"FLUXO PRO | simbolo={cfg.symbol} fonte={cfg.fonte.value} "
            f"tick={self.grid.tick_size:g} estagios={'+'.join(estagios)}"
        )
        self._escrever(
            "hora          tipo      evento              direcao contexto          "
            "| evidencia"
        )
        self._escrever("-" * 118)

    def linha_status(self, sessao: SessaoFluxo) -> str:
        c = sessao.contadores
        return (
            f"eventos={c.n_eventos_bus} (trades={c.n_trades_bus} "
            f"book={c.n_snapshots_bus + c.n_deltas_bus}) "
            f"{sessao.taxa_eventos_s():,.0f} ev/s | "
            f"ordens_inferidas={c.n_ordem_eventos_inferidos}/{c.n_ordem_eventos} | "
            f"sinais={c.n_sinais_emitidos} deteccoes={c.n_deteccoes} "
            f"(inferidas={c.n_deteccoes_inferidas})"
        )

    def resumo(self, sessao: SessaoFluxo) -> None:
        c = sessao.contadores
        self._escrever("-" * 118)
        self._escrever("RESUMO DA SESSAO")
        self._escrever(
            f"  eventos processados : {c.n_eventos_bus}  "
            f"(trades={c.n_trades_bus} snapshots={c.n_snapshots_bus} "
            f"deltas={c.n_deltas_bus})"
        )
        self._escrever(
            f"  tape                : {c.duracao_tape_ns / NS_POR_SEGUNDO:.1f}s  |  "
            f"parede: {sessao.segundos_decorridos():.2f}s  |  "
            f"{sessao.taxa_eventos_s():,.0f} ev/s"
        )
        self._escrever(
            f"  ordens (MBP->MBO)   : {c.n_ordem_eventos}  "
            f"(inferidas={c.n_ordem_eventos_inferidos}) "
            f"cruzamentos_livro={c.n_cruzamentos_livro}"
        )
        if c.ordem_eventos_por_tipo:
            for tipo, n in sorted(
                c.ordem_eventos_por_tipo.items(), key=lambda kv: -kv[1]
            ):
                self._escrever(f"      {tipo.value:<22} {n}")

        self._escrever(f"  sinais emitidos     : {c.n_sinais_emitidos}")
        for estagio, n in sorted(
            c.sinais_por_estagio.items(), key=lambda kv: -kv[1]
        ):
            self._escrever(f"      {estagio.value:<22} {n}")

        self._escrever(
            f"  deteccoes           : {c.n_deteccoes}  "
            f"(inferidas={c.n_deteccoes_inferidas} "
            f"observadas={c.n_deteccoes - c.n_deteccoes_inferidas})"
        )
        for tipo, n in sorted(c.deteccoes_por_tipo.items(), key=lambda kv: -kv[1]):
            self._escrever(f"      {tipo.value:<22} {n}")

        self._resumo_mercado(sessao)

    def _resumo_mercado(self, sessao: SessaoFluxo) -> None:
        sess = sessao.estado.sessao
        if sess.volume_total == 0:
            return
        grid = self.grid
        alto = "-" if sess.high is None else f"{grid.to_price(sess.high):g}"
        baixo = "-" if sess.low is None else f"{grid.to_price(sess.low):g}"
        self._escrever(
            f"  mercado             : max={alto} min={baixo} "
            f"vwap={grid.to_price(round(sess.vwap)):g} "
            f"volume={sess.volume_total} "
            f"(compr={sess.volume_comprador} vend={sess.volume_vendedor} "
            f"nao_atrib={sess.volume_nao_atribuido})"
        )
        area = sessao.perfil_sessao.value_area()
        if area is not None:
            val, vah = area
            poc = sessao.perfil_sessao.poc
            self._escrever(
                f"  perfil de sessao    : VAL={grid.to_price(val):g} "
                f"POC={'-' if poc is None else f'{grid.to_price(poc):g}'} "
                f"VAH={grid.to_price(vah):g}"
            )
        if sessao.motor is not None:
            self._escrever(
                f"  motor (final)       : estagio={sessao.motor.estagio_atual.value} "
                f"direcao={_DIRECAO.get(sessao.motor.direcao_atual, '-') if sessao.motor.direcao_atual else '-'} "
                f"faixa={sessao.motor.faixa_atual.value}"
            )

    # ------------------------------------------------------------------
    def _escrever(self, linha: str) -> None:
        if self.guardar_linhas:
            self.linhas.append(linha)
        # `flush=True` não é zelo: com stdout redirecionado (`| tee`, `> log`)
        # o Python usa buffer de bloco, e sem flush TODAS as linhas apareciam
        # só no fim da execução — num programa que acompanha o pregão ao vivo
        # isso é a diferença entre um monitor e um relatório.
        #
        # Correção de uma frase que estava aqui e era falsa: "sinal e detecção
        # são eventos raros (dezenas por sessão, não por segundo)". A medição
        # de `criticas/nucleo_r5.md` §C.3 dá 11.054 detecções em 500.000
        # eventos — milhares por sessão, ~110/s a 5.000 ev/s. O flush continua
        # justificável nessa taxa (não é caminho por tick), mas a frase era o
        # apoio de "guardar toda linha em memória não tem custo", e não era.
        # Ver "Critério de crescimento" na docstring do módulo.
        print(linha, file=self.stream, flush=True)
