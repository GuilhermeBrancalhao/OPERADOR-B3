"""Composicao macro da superficie NEXO do workspace OPERADOR B3.

Este pacote existe por **costura de propriedade**: cada regiao da superficie
mora em um modulo proprio com uma unica entrada
``desenhar(painter, rect, estado)``. ``PainelNexoMercadoASG.desenhar`` deixa de
pintar e passa a apenas *alocar retangulos* e delegar, de modo que cada regiao
possa evoluir sem que dois autores disputem o mesmo arquivo.

Contratos preservados desta fronteira:

* nenhum modulo assina barramento, le sessao ou infere microestrutura — todos
  recebem o mesmo ``EstadoNexo`` imutavel, montado uma vez por quadro a partir
  do snapshot ja congelado pela janela;
* preco continua ``int`` em ticks dentro do estado; a conversao para pixel
  acontece somente dentro de cada ``desenhar``;
* nenhuma regiao oferece callback, botao ou campo — a superficie inteira e
  consultiva e nao envia ordem.

O mapa de regioes abaixo e o **contrato de composicao**: fracoes do quadro,
borda a borda, sem moldura de cartao entre elas. Ele nao e estilo (cor, fonte,
espessura continuam vindo de ``tokens``/``tema_asg``); e geometria, e por isso
mora aqui em vez de ficar espalhado como numero solto no meio da pintura.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from PySide6.QtCore import QRect

# Nome da regiao -> (x0, y0, x1, y1) em fracao do quadro.
#
# Sangria total: a uniao das regioes cobre o quadro de borda a borda. Nao ha
# vao, margem externa nem moldura entre regioes — a leitura e continua, como a
# de um terminal de video, e nao uma grade de cartoes.
REGIOES: dict[str, tuple[float, float, float, float]] = {
    "ladder": (0.00, 0.00, 0.06, 0.56),
    "contexto": (0.06, 0.00, 0.34, 0.56),
    "niveis": (0.02, 0.55, 0.40, 0.65),
    "banner": (0.00, 0.65, 0.40, 0.78),
    "estatistica": (0.00, 0.79, 0.40, 1.00),
    "nucleo": (0.40, 0.02, 0.63, 0.42),
    "vies": (0.42, 0.62, 0.62, 1.00),
    "forca": (0.63, 0.00, 1.00, 0.33),
    "candles": (0.63, 0.34, 0.98, 0.85),
    "pressao": (0.63, 0.86, 1.00, 1.00),
}

# Ordem de pintura. ``niveis`` entra depois de ``ladder``/``contexto`` porque a
# faixa de chips avanca 0,01 do quadro sobre elas de proposito (o mesmo
# encaixe do material de referencia), e quem chega por ultimo fica por cima.
ORDEM_DESENHO: tuple[str, ...] = (
    "ladder",
    "contexto",
    "forca",
    "candles",
    "nucleo",
    "vies",
    "estatistica",
    "banner",
    "niveis",
    "pressao",
)

# Altura, em pixels, da linha de ressalva permanente no rodape do quadro. Ela
# nao e cromo decorativo: e a declaracao de que a superficie e consultiva, e
# por contrato de projeto nao pode sumir. Fica fora da area das regioes para
# nao ser sobreposta.
ALTURA_RESSALVA = 13


@dataclass(frozen=True)
class EstadoNexo:
    """Retrato imutavel de um quadro, unico insumo de toda regiao.

    Nao carrega referencia ao painel nem ao feed: uma regiao ve exatamente o
    que esta aqui e nada mais. ``serie`` ja vem como tupla (o ``deque`` vivo
    do painel nunca atravessa a fronteira) e ``precos`` seguem ``int`` em
    ticks.

    ``tijolos_renko``/``fase_renko``/``alvos_renko`` e ``candles_m15`` vem de
    ``fluxopro.analytics.renko``/``candle_temporal`` — agregadores puros
    alimentados por chamada direta (nunca por assinatura de barramento),
    ja em forma de tupla/objeto imutavel antes de cruzar para a regiao.
    Default vazio para nao quebrar quem constroi ``EstadoNexo`` sem eles.
    """

    snapshot: object
    serie: tuple[tuple[int, int, float, int], ...]
    grid: object
    paleta: object
    maker: object | None
    leituras: tuple[tuple[str, object], ...]
    largura: int
    altura: int
    tijolos_renko: tuple[object, ...] = ()
    fase_renko: object = None
    alvos_renko: object | None = None
    candles_m15: tuple[object, ...] = ()
    vap_niveis: tuple[tuple[int, int, int, int, bool], ...] = ()
    vap_poc: int | None = None
    vap_val: int | None = None
    vap_vah: int | None = None
    risco_volatilidade: float = 0.0
    alerta_exaustao: tuple[str, float] | None = None
    sinal_ultra: object | None = None
    """``SinalUltraSnapshot`` (fluxopro.asg.sinal_ultra) do quadro, ou None.
    Filtro adicional, construido do zero por este projeto — ver docstring de
    sinal_ultra.py. `None` so quando o painel que constroi EstadoNexo nao o
    calcula (compatibilidade com pontos de montagem antigos/testes)."""


def retangulos(quadro: QRect) -> dict[str, QRect]:
    """Traduz o mapa de fracoes em retangulos inteiros dentro de ``quadro``.

    Arredonda nas bordas (e nao na largura) para que regioes vizinhas encostem
    exatamente, sem costura de um pixel entre elas.
    """

    saida: dict[str, QRect] = {}
    for nome, (fx0, fy0, fx1, fy1) in REGIOES.items():
        x0 = quadro.left() + round(quadro.width() * fx0)
        x1 = quadro.left() + round(quadro.width() * fx1)
        y0 = quadro.top() + round(quadro.height() * fy0)
        y1 = quadro.top() + round(quadro.height() * fy1)
        saida[nome] = QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
    return saida


_MODULOS: dict[str, ModuleType] = {}


def modulo(nome: str) -> ModuleType:
    """Importa a regiao sob demanda.

    O import e tardio de proposito: os modulos de regiao dependem de
    ``paineis.asg`` (enums de direcao, resolucao de cor por estado) e
    ``paineis.asg`` depende deste pacote. Importar so no primeiro quadro
    desfaz o ciclo sem exigir que ``asg`` exporte nada novo.

    A resolucao e por ``import`` literal, um por nome fixo de
    ``ORDEM_DESENHO`` — nunca ``importlib.import_module`` com string
    formatada. O auditor de ordens (`scripts/auditoria_asg.py`) reprova
    qualquer import dinamico por principio (poderia carregar API de
    corretora); aqui nao ha string vinda de fora, mas o padrao textual e
    identico ao de um carregador de plugin de verdade, entao a forma
    literal e a unica que passa o portao sem exigir excecao no auditor.
    """

    modulo_regiao = _MODULOS.get(nome)
    if modulo_regiao is not None:
        return modulo_regiao
    if nome not in ORDEM_DESENHO:
        raise ValueError(f"regiao desconhecida: {nome!r}")

    from . import (
        banner,
        candles,
        contexto,
        estatistica,
        forca,
        ladder,
        niveis,
        nucleo,
        pressao,
        vies,
    )

    _MODULOS.update(
        {
            "banner": banner,
            "candles": candles,
            "contexto": contexto,
            "estatistica": estatistica,
            "forca": forca,
            "ladder": ladder,
            "niveis": niveis,
            "nucleo": nucleo,
            "pressao": pressao,
            "vies": vies,
        }
    )
    return _MODULOS[nome]


__all__ = [
    "ALTURA_RESSALVA",
    "EstadoNexo",
    "ORDEM_DESENHO",
    "REGIOES",
    "modulo",
    "retangulos",
]
