"""O retrato de analytics montado do lado de quem escreve.

Promovido de `tests/test_ui_workspace.py::test_sonda_retrato_do_footprint_sob_lock`,
que era uma sonda `xfail` com endereco: `derivar_footprint`, `derivar_perfil` e
`derivar_delta` ITERAM colecoes vivas da thread da fonte
(`VolumeProfile._niveis`, os niveis do candle, o historico do delta), e do lado
do Qt isso levanta `dictionary changed size during iteration` — o que derrubou
o primeiro retrato da composicao com 9.098 negocios. `ui/janela.py::
_aplicar_footprint` degradava com relatorio na trilha, e degradar nao e
consertar.

O que estes testes medem, e por que cada um existe:

* **A corrida existe.** Um teste que so mostrasse o retrato funcionando nao
  provaria nada: talvez a corrida nunca acontecesse. Entao o mesmo laco roda
  duas vezes contra o MESMO produtor — pela colecao viva (reprova) e pelo
  retrato (passa). E a prova por mutacao: trocar a fonte do retrato pela fonte
  viva reprova o teste.

* **Leitura RASGADA nao levanta erro.** Copiar a colecao do lado do Qt trocaria
  a excecao por uma tela costurada de dois instantes, que mente em silencio.
  Nao ha excecao para testar; ha INVARIANTE: a soma dos niveis tem de bater com
  o volume total do mesmo retrato. Uma copia feita do lado errado do lock
  quebra essa soma sem levantar nada, e e por isso que a assercao e sobre a
  aritmetica e nao sobre `pytest.raises`.

* **Limitado pela TELA.** O recorte do historico e conferido contra o numero de
  candles, que e a grandeza que NAO pode mandar no tamanho da estrutura.
"""

from __future__ import annotations

import threading
import time

import pytest

from fluxopro.analytics.volume_profile import VolumeProfile
from fluxopro.app.config import ConfigOperacao
from fluxopro.app.sessao_fluxo import (
    RetratoAnalytics,
    SessaoFluxo,
    _congelar_fonte_perfil,
)
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.ui.paineis.delta_acumulado import derivar_delta
from fluxopro.ui.paineis.footprint import derivar_footprint
from fluxopro.ui.paineis.perfil import derivar_perfil

SIMBOLO = "WDOV26"
BASE = 5000
T0 = 1_700_000_000_000_000_000
TIMEFRAME_NS = 60_000_000_000


def _sessao() -> SessaoFluxo:
    barramento = Barramento()
    cfg = ConfigOperacao(
        symbol=SIMBOLO,
        timeframe_ns=TIMEFRAME_NS,
        ligar_microestrutura=False,
        ligar_detectores_tape=False,
        ligar_motor=False,
        ligar_metodologia=False,
    )
    return SessaoFluxo(barramento, cfg)


def _trade(i: int, preco: int) -> Trade:
    return Trade(
        T0 + i * 1_000_000_000,
        SIMBOLO,
        preco,
        1 + (i % 5),
        AgressorSide.BUY if i % 2 else AgressorSide.SELL,
        "t%d" % i,
    )


def _alimentar(sessao: SessaoFluxo, n: int) -> None:
    for i in range(n):
        sessao.barramento.publicar(_trade(i, BASE + (i % 37)))


# --------------------------------------------------------------------------
# 1. A corrida — a mesma leitura pelos dois caminhos
# --------------------------------------------------------------------------
class _Produtor(threading.Thread):
    """A thread da FONTE. Cada negocio cria um preco NOVO, de proposito.

    Um preco novo por negocio faz o dicionario do perfil crescer a cada
    publicacao — que e a condicao exata de `dictionary changed size during
    iteration`. Reciclar precos deixaria o defeito depender de o dict calhar
    de redimensionar durante a leitura, e um teste que so as vezes mede o que
    diz nao mede nada.
    """

    def __init__(self, sessao: SessaoFluxo) -> None:
        super().__init__(daemon=True)
        self.sessao = sessao
        self.parar = threading.Event()
        self.publicados = 0

    def run(self) -> None:
        i = 0
        while not self.parar.is_set():
            self.sessao.barramento.publicar(_trade(i, BASE + i))
            self.publicados = i
            i += 1


def _martelar(ler, orcamento_s: float = 4.0):
    """Roda `ler()` contra um produtor vivo. Devolve a 1a excecao, ou `None`."""
    sessao = _sessao()
    _alimentar(sessao, 200)
    produtor = _Produtor(sessao)
    produtor.start()
    limite = time.perf_counter() + orcamento_s
    erro = None
    try:
        while time.perf_counter() < limite and erro is None:
            try:
                ler(sessao)
            except Exception as exc:  # noqa: BLE001 — e o que se esta medindo
                erro = exc
    finally:
        produtor.parar.set()
        produtor.join(timeout=5.0)
    return erro


def _ler_das_colecoes_vivas(sessao: SessaoFluxo) -> None:
    """O caminho ANTIGO: os tres `derivar_*` sobre os acumuladores vivos."""
    derivar_footprint(sessao.footprint, None, 40)
    derivar_perfil(sessao.perfil_sessao, (BASE - 50, BASE + 50))
    derivar_delta(sessao.delta, None, 40)


def _ler_do_retrato(sessao: SessaoFluxo) -> None:
    """O caminho NOVO: os MESMOS tres `derivar_*`, sobre o retrato."""
    retrato = sessao.retrato_de_analytics(40)
    if retrato is None:
        return
    derivar_footprint(retrato.footprint, None, retrato.n_colunas)
    derivar_perfil(retrato.perfil_sessao, (BASE - 50, BASE + 50))
    derivar_delta(retrato.delta, None, retrato.n_colunas)


def test_ler_as_colecoes_vivas_de_outra_thread_levanta():
    """A MUTACAO do teste de baixo: trocar o retrato pela colecao viva reprova.

    Sem esta metade, "o retrato nao levantou excecao" seria compativel com
    "nunca houve corrida nenhuma".
    """
    erro = _martelar(_ler_das_colecoes_vivas)
    assert isinstance(erro, RuntimeError), (
        "a corrida que o retrato existe para fechar nao foi reproduzida: %r" % erro
    )
    assert "changed size during iteration" in str(erro)


def test_o_retrato_atravessa_a_mesma_corrida_sem_levantar():
    assert _martelar(_ler_do_retrato) is None


# --------------------------------------------------------------------------
# 2. Leitura rasgada — a que nao levanta erro nenhum
# --------------------------------------------------------------------------
def test_o_retrato_fecha_a_aritmetica_sob_producao_concorrente():
    """`volume_total` do perfil e a soma dos niveis DO MESMO INSTANTE.

    Uma copia montada do lado do Qt pega os niveis num instante e o total em
    outro; a soma passa a nao fechar e nada levanta excecao. E por isso que a
    prova aqui e aritmetica.
    """
    sessao = _sessao()
    _alimentar(sessao, 200)
    produtor = _Produtor(sessao)
    produtor.start()
    conferidos = 0
    try:
        limite = time.perf_counter() + 2.0
        while time.perf_counter() < limite:
            retrato = sessao.retrato_de_analytics(40)
            if retrato is None or retrato.perfil_sessao is None:
                continue
            perfil = retrato.perfil_sessao
            soma = sum(n.volume_total for _, n in perfil.niveis_ordenados())
            assert soma == perfil.volume_total
            conferidos += 1
    finally:
        produtor.parar.set()
        produtor.join(timeout=5.0)
    assert conferidos > 0, "nenhum retrato chegou do outro lado do lock"
    assert produtor.publicados > 0


def test_congelar_o_perfil_desliga_o_dado_do_acumulador():
    """O congelado nao e uma VISTA: mutar a fonte depois nao o move.

    Guardar a referencia do `NivelVolume` vivo passaria em qualquer teste de
    valor tirado no mesmo instante, e mentiria um negocio depois.
    """
    perfil = VolumeProfile()
    perfil.registrar_trade(_trade(0, BASE))
    congelado = _congelar_fonte_perfil(perfil)
    assert congelado is not None
    antes = congelado.niveis_ordenados()[0][1].volume_total
    for i in range(1, 20):
        perfil.registrar_trade(_trade(i, BASE))
    assert congelado.niveis_ordenados()[0][1].volume_total == antes
    assert congelado.volume_total < perfil.volume_total


# --------------------------------------------------------------------------
# 3. Limitado pela TELA, nunca pelo numero de eventos
# --------------------------------------------------------------------------
@pytest.mark.parametrize("n_candles", [5, 60, 400])
def test_o_recorte_e_o_das_colunas_e_nao_o_da_sessao(n_candles):
    sessao = _sessao()
    for c in range(n_candles):
        for k in range(3):
            sessao.barramento.publicar(
                Trade(
                    T0 + c * TIMEFRAME_NS + k * 1_000_000,
                    SIMBOLO,
                    BASE + k,
                    2,
                    AgressorSide.BUY,
                    "c%dk%d" % (c, k),
                )
            )
    retrato = sessao.retrato_de_analytics(24)
    assert retrato is not None
    assert retrato.footprint is not None and retrato.delta is not None
    assert len(retrato.footprint.footprints_fechados) <= 23
    assert len(retrato.delta.historico) <= 23
    # A prova por mutacao do recorte: se ele viesse do numero de candles, esta
    # igualdade entre as tres parametrizacoes seria impossivel.
    assert len(retrato.footprint.footprints_fechados) == min(23, n_candles - 1)


def test_o_retrato_diz_a_mesma_coisa_que_a_leitura_direta_em_repouso():
    """Congelar nao pode mudar o numero. Com a fonte parada, os dois batem."""
    sessao = _sessao()
    _alimentar(sessao, 500)
    retrato = sessao.retrato_de_analytics(30)
    assert isinstance(retrato, RetratoAnalytics)
    faixa = (BASE - 50, BASE + 50)
    assert derivar_perfil(retrato.perfil_sessao, faixa) == derivar_perfil(
        sessao.perfil_sessao, faixa
    )
    assert derivar_footprint(retrato.footprint, None, 30) == derivar_footprint(
        sessao.footprint, None, 30
    )
    assert derivar_delta(retrato.delta, None, 30) == derivar_delta(
        sessao.delta, None, 30
    )


def test_a_virada_de_sessao_nao_deixa_o_retrato_de_ontem():
    sessao = _sessao()
    _alimentar(sessao, 100)
    assert sessao.retrato_de_analytics(10) is not None
    sessao._thread_publicadora = -1  # forca o caminho do outro lado do lock
    sessao.retrato_de_analytics(10)
    sessao.iniciar_nova_sessao(T0 + 86_400_000_000_000)
    assert sessao.retrato_de_analytics(10) is None


def test_analytics_desligado_devolve_retrato_com_os_tres_vazios():
    """`ligar_analytics=False` nao pode virar `AttributeError` na UI."""
    cfg = ConfigOperacao(
        symbol=SIMBOLO,
        ligar_analytics=False,
        ligar_microestrutura=False,
        ligar_detectores_tape=False,
        ligar_motor=False,
        ligar_metodologia=False,
    )
    sessao = SessaoFluxo(Barramento(), cfg)
    retrato = sessao.retrato_de_analytics(10)
    assert retrato is not None
    assert retrato.footprint is None and retrato.delta is None
    assert retrato.perfil_sessao is not None  # o perfil de sessao sempre existe
