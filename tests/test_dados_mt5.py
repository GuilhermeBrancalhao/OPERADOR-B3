"""Testes da borda ao vivo MT5.

O mock deste arquivo é a peça mais importante dele. A versão anterior
ignorava `de` e `count` em `copy_ticks_from` — devolvia um lote pré-cozido
por chamada — e por isso NENHUM teste podia observar o defeito real: com
`de` truncado ao segundo e `count` fixo em 1.000, todo poll pedia "os 1.000
primeiros ticks do segundo S" e recebia sempre os mesmos; acima de 1.000
negócios/s o cursor congelava e o feed morria em silêncio. Os 10 testes
passavam com o feed morto.

`_FakeMT5` aqui implementa o contrato que a API real tem:
`copy_ticks_from(symbol, de, count, flags)` devolve os `count` PRIMEIROS
ticks com `time >= de` (`de` em SEGUNDOS), em ordem crescente de `time_msc`.
`symbol_info_tick` devolve o último tick conhecido. `visivel_ate_msc`
existe para simular o tape crescendo entre polls, que é o regime em que os
defeitos de fronteira aparecem.
"""

from __future__ import annotations

import threading
import time
from collections import namedtuple

import numpy as np
import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
    WDO_GRID,
)
from fluxopro.dados import mt5 as mt5_mod
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
from fluxopro.dados.feed_observavel import FeedQualityMonitor, FeedQualityObserver
from fluxopro.dados.mt5 import (
    _AMOSTRAS_PARA_REGRESSAO,
    _JANELA_OFFSET_S,
    _LIMIAR_REGRESSAO_NS,
    AdaptadorMT5,
    _CursorTick,
    _importar_mt5,
    _normalizar_lote,
    _primeiro_do_ms,
    _RelogioServidor,
    derivar_deltas,
)
from fluxopro.dados.qualidade import FeedSource, FeedState

_TICK_DTYPE = [
    ("time", "i8"), ("bid", "f8"), ("ask", "f8"), ("last", "f8"),
    ("volume", "i8"), ("time_msc", "i8"), ("flags", "i4"), ("volume_real", "f8"),
]

BookInfo = namedtuple("BookInfo", ["type", "price", "volume", "volume_dbl"])
TickInfo = namedtuple("TickInfo", ["time", "time_msc", "bid", "ask", "last"])

TICK_FLAG_BUY = 1 << 5
TICK_FLAG_SELL = 1 << 6

BOOK_PADRAO = [BookInfo(0, 4999.5, 10, 10.0), BookInfo(1, 5000.5, 15, 15.0)]


def _tick(time_msc, bid, ask, last, volume, flags=0, volume_real=0.0):
    """Um registro estruturado 0-d — o formato que o numpy devolve quando o
    array tem exatamente 1 elemento e alguém indexa nele."""
    return _linhas([(time_msc, bid, ask, last, volume, flags, volume_real)])[0]


def _linhas(especs) -> np.ndarray:
    return np.array(
        [
            (msc // 1000, bid, ask, last, vol, msc, flags, vol_real)
            for (msc, bid, ask, last, vol, flags, vol_real) in especs
        ],
        dtype=_TICK_DTYPE,
    )


def _tape_denso(n, base_msc, ticks_por_ms=1, flags=TICK_FLAG_BUY):
    """`n` ticks a partir de `base_msc`, `ticks_por_ms` por milissegundo."""
    return _linhas(
        [
            (base_msc + i // ticks_por_ms, 4999.5, 5000.5, 5000.5, 1, flags, 0.0)
            for i in range(n)
        ]
    )


class _FakeMT5:
    """Mock do pacote MetaTrader5 com a MESMA semântica da API real.

    Contrato implementado (é o que o adaptador depende):

    * `copy_ticks_from(symbol, de, count, flags)` — `de` em SEGUNDOS desde a
      época; devolve os `count` PRIMEIROS ticks com `time_msc >= de*1000`,
      em ordem crescente de `time_msc`. Nunca mais que `count`. Um lote
      exatamente cheio é indistinguível de "há mais além dele" — é essa
      ambiguidade que o adaptador tem de tratar como saturação.
    * `symbol_info_tick(symbol)` — último tick conhecido do símbolo (é a
      única fonte de hora de servidor com o mercado parado).
    * `market_book_get(symbol)` — leitura corrente do DOM, sem tempo.

    `visivel_ate_msc` corta o tape para simular o tape que ainda vai chegar.
    """

    COPY_TICKS_ALL = 0
    TICK_FLAG_BUY = TICK_FLAG_BUY
    TICK_FLAG_SELL = TICK_FLAG_SELL
    BOOK_TYPE_BUY = 0
    BOOK_TYPE_SELL = 1

    def __init__(
        self,
        tape=None,
        books_por_chamada=None,
        book_repetido=None,
        visivel_ate_msc=None,
    ):
        tape = _linhas([]) if tape is None else np.asarray(tape, dtype=_TICK_DTYPE)
        self.tape = np.sort(tape, order="time_msc", kind="stable")
        self._books_por_chamada = list(books_por_chamada or [])
        self._book_repetido = book_repetido
        self.visivel_ate_msc = visivel_ate_msc

        self.chamadas: list[tuple[int, int]] = []  # (de_segundos, count) por chamada
        self.tamanhos_devolvidos: list[int] = []
        self.encerrado = False
        self.book_liberado = False

    # -- ciclo de vida -------------------------------------------------
    def initialize(self, **kwargs):
        return True

    def symbol_select(self, symbol, enable):
        return True

    def market_book_add(self, symbol):
        return True

    def market_book_release(self, symbol):
        self.book_liberado = True

    def last_error(self):
        return (0, "ok")

    def shutdown(self):
        self.encerrado = True

    # -- dados ---------------------------------------------------------
    def _visivel(self):
        if self.visivel_ate_msc is None:
            return self.tape
        return self.tape[self.tape["time_msc"] < self.visivel_ate_msc]

    def copy_ticks_from(self, symbol, de, count, flags):
        assert isinstance(de, int) and de >= 0, "date_from da API real é em SEGUNDOS"
        assert count >= 1, "count da API real é >= 1"
        self.chamadas.append((de, count))
        visivel = self._visivel()
        # lower bound por busca binária: os ticks já estão ordenados.
        inicio = int(np.searchsorted(visivel["time_msc"], de * 1000, side="left"))
        lote = visivel[inicio : inicio + count]
        self.tamanhos_devolvidos.append(len(lote))
        return lote

    def symbol_info_tick(self, symbol):
        visivel = self._visivel()
        if len(visivel) == 0:
            return None
        ultimo = visivel[-1]
        return TickInfo(
            time=int(ultimo["time"]),
            time_msc=int(ultimo["time_msc"]),
            bid=float(ultimo["bid"]),
            ask=float(ultimo["ask"]),
            last=float(ultimo["last"]),
        )

    def market_book_get(self, symbol):
        if self._books_por_chamada:
            return self._books_por_chamada.pop(0)
        return self._book_repetido


class _FakeMT5Antigo(_FakeMT5):
    """Módulo MetaTrader5 velho: sem `symbol_info_tick`."""

    symbol_info_tick = None


def _adaptador(fake, **kwargs):
    kwargs.setdefault("intervalo_poll_s", 0.001)
    return AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=fake, **kwargs)


def _drenar(adaptador, fake, cursor=None, max_polls=40):
    """Roda `_puxar_ticks` até o tape parar de render, como o loop de borda.

    Devolve `(trades, falhas, cursor, polls)`.
    """
    cursor = _CursorTick() if cursor is None else cursor
    trades: list[Trade] = []
    falhas: list[FalhaCaptura] = []
    parados = 0
    for polls in range(1, max_polls + 1):
        novos, cursor, novas_falhas = adaptador._puxar_ticks(fake, cursor)
        trades.extend(novos)
        falhas.extend(novas_falhas)
        parados = parados + 1 if not novos else 0
        if parados >= 2:
            return trades, falhas, cursor, polls
    raise AssertionError(
        f"o tape nao drenou em {max_polls} polls — cursor travado em {cursor}"
    )


def _chave(trade: Trade) -> tuple[int, int]:
    """(time_msc, ordem_no_ms) extraídos do `trade_id` MT5-<msc>-<ordem>-<flags>."""
    _, msc, ordem, _flags = trade.trade_id.split("-")
    return int(msc), int(ordem)


# ======================================================================
# Fidelidade do próprio mock — se ele mentir, todo o resto mente junto
# ======================================================================


def test_mock_honra_de_e_count_como_a_api_real():
    fake = _FakeMT5(tape=_tape_denso(3_000, 1_000_000, ticks_por_ms=3))

    lote = fake.copy_ticks_from("WDOV26", 1, 1_000, 0)
    assert len(lote) == 1_000, "count tem de limitar o lote"
    assert int(lote[0]["time_msc"]) == 1_000_000
    assert list(lote["time_msc"]) == sorted(lote["time_msc"]), "ordem crescente"

    # `de` em SEGUNDOS: pedir do segundo 1001 pula o segundo 1000 inteiro.
    lote_seg_2 = fake.copy_ticks_from("WDOV26", 1_001, 10_000, 0)
    assert all(int(t["time_msc"]) >= 1_001_000 for t in lote_seg_2)

    # pedir de um segundo além do tape devolve vazio, não o tape inteiro.
    assert len(fake.copy_ticks_from("WDOV26", 9_999, 1_000, 0)) == 0


def test_mock_devolve_lote_exatamente_cheio_quando_ha_mais():
    fake = _FakeMT5(tape=_tape_denso(50, 1_000_000))
    assert len(fake.copy_ticks_from("WDOV26", 1, 50, 0)) == 50
    assert len(fake.copy_ticks_from("WDOV26", 1, 60, 0)) == 50


# ======================================================================
# O defeito: mais de 1.000 negócios no mesmo segundo
# ======================================================================


def test_tres_mil_ticks_no_mesmo_segundo_chegam_todos_em_ordem_e_sem_duplicata():
    """O teste do defeito da R3.

    3.000 negócios dentro do segundo 1000 — WDO a 3.000 neg/s, ABAIXO do
    pico de 5–10 mil da barra do projeto. Com `count` fixo em 1.000 e `de`
    truncado ao segundo, chegavam 1.000 e o cursor congelava para sempre.
    """
    tape = _tape_denso(3_000, 1_000_000, ticks_por_ms=3)
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake, ticks_por_chamada=1_000)

    trades, falhas, cursor, _polls = _drenar(adaptador, fake)

    assert len(trades) == 3_000, "todos os 3.000 negócios do segundo têm de sair"
    ids = [t.trade_id for t in trades]
    assert len(set(ids)) == 3_000, "nenhuma duplicata"
    chaves = [_chave(t) for t in trades]
    assert chaves == sorted(chaves), "ordem crescente de (time_msc, ordem no ms)"
    assert chaves[0] == (1_000_000, 0)
    assert chaves[-1] == (1_000_999, 2)
    assert falhas == [], "nada foi perdido — não há razão para FalhaCaptura"
    assert cursor == _CursorTick(1_000_999, 3)


def test_paginacao_escala_o_count_no_mesmo_segundo_em_vez_de_avancar_o_de():
    """Enquanto o cursor está dentro do segundo S, avançar `date_from`
    pularia ticks: o que cresce é a janela."""
    fake = _FakeMT5(tape=_tape_denso(3_000, 1_000_000, ticks_por_ms=3))
    adaptador = _adaptador(fake, ticks_por_chamada=1_000)

    trades, _cursor, _falhas = adaptador._puxar_ticks(fake, _CursorTick())

    assert len(trades) == 3_000, "um poll só tem de bastar quando o teto permite"
    assert fake.chamadas == [(0, 1_000), (0, 2_000), (0, 4_000)], (
        "mesmo `de`, `count` dobrando até o lote voltar incompleto"
    )
    assert fake.tamanhos_devolvidos == [1_000, 2_000, 3_000]


def test_dez_mil_ticks_no_mesmo_segundo_com_o_count_de_fabrica():
    """O pico declarado da barra do projeto, com o `ticks_por_chamada` que o
    produto usa de fábrica (10.000)."""
    fake = _FakeMT5(tape=_tape_denso(10_000, 1_000_000, ticks_por_ms=10))
    adaptador = _adaptador(fake)

    trades, falhas, _cursor, _polls = _drenar(adaptador, fake)

    assert len(trades) == 10_000
    assert len({t.trade_id for t in trades}) == 10_000
    assert falhas == []


# ======================================================================
# Saturação — pagina de novo, e cursor congelado é FALHA, nunca silêncio
# ======================================================================


def test_lote_exatamente_cheio_dispara_nova_pagina_em_vez_de_seguir():
    """Exatamente `count` é ambíguo: pode ser "acabou" ou "tem mais". O
    adaptador tem de pedir de novo para desambiguar."""
    fake = _FakeMT5(tape=_tape_denso(1_000, 1_000_000, ticks_por_ms=1))
    adaptador = _adaptador(fake, ticks_por_chamada=1_000)

    trades, _cursor, falhas = adaptador._puxar_ticks(fake, _CursorTick())

    assert fake.tamanhos_devolvidos[0] == 1_000, "primeiro lote voltou cheio"
    assert len(fake.chamadas) == 2, "lote cheio obriga uma segunda página"
    assert fake.chamadas[1] == (0, 2_000)
    assert fake.tamanhos_devolvidos[1] == 1_000, "a segunda provou que acabou"
    assert len(trades) == 1_000
    assert falhas == [], "não saturou no teto — não há perda a declarar"


def test_cursor_impossibilitado_de_avancar_emite_falha_captura_explicita():
    """Teto de paginação atingido E o cursor não anda: é perda de dado.

    Tem de sair `FalhaCaptura(GAP_TICKS)` dizendo o tamanho da janela, e o
    cursor tem de pular o segundo — girar em falso (o comportamento antigo)
    é o pior desfecho possível.
    """
    # 3.000 ticks no segundo 1000 com teto de 1.000: 2.000 não cabem.
    tape = np.concatenate(
        [
            _tape_denso(3_000, 1_000_000, ticks_por_ms=3),
            _tape_denso(5, 1_001_000, ticks_por_ms=1),  # o segundo SEGUINTE
        ]
    )
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake, ticks_por_chamada=1_000, teto_ticks_por_chamada=1_000)

    trades, falhas, cursor, polls = _drenar(adaptador, fake)

    tipos = [f.tipo for f in falhas]
    assert TipoFalha.GAP_TICKS in tipos, "perda de dado NUNCA pode ser silenciosa"
    congelado = [
        f for f in falhas if "NAO tem como avancar" in f.detalhe
    ]
    assert congelado, f"faltou a falha de cursor congelado; falhas={[f.detalhe for f in falhas]}"
    assert "1000" in congelado[0].detalhe, "a falha tem de dizer o tamanho da janela"
    assert congelado[0].symbol == "WDOV26"

    # e o feed VOLTA A ANDAR: o segundo seguinte é entregue.
    assert cursor.time_msc >= 1_001_000, f"o cursor não saiu do segundo 1000: {cursor}"
    assert any(_chave(t)[0] >= 1_001_000 for t in trades), (
        "depois do buraco o adaptador tem de voltar a entregar tape"
    )
    assert polls < 40, "não pode girar em falso"


def test_saturacao_com_teto_baixo_nao_congela_o_feed_para_sempre():
    """Regressão direta do defeito: com o teto no `count` original de 1.000
    o adaptador perde parte do segundo — mas continua vivo e avisa."""
    tape = np.concatenate(
        [
            _tape_denso(3_000, 1_000_000, ticks_por_ms=3),
            _tape_denso(10, 1_002_000, ticks_por_ms=1),
        ]
    )
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake, ticks_por_chamada=1_000, teto_ticks_por_chamada=1_000)

    trades, falhas, _cursor, _polls = _drenar(adaptador, fake)

    entregues_seg_1002 = [t for t in trades if _chave(t)[0] >= 1_002_000]
    assert len(entregues_seg_1002) == 10, "o tape depois do buraco chega inteiro"
    perdidos = 3_000 + 10 - len(trades)
    assert perdidos > 0, "o cenário tem de perder dado (é o preço do teto)"
    assert len([f for f in falhas if f.tipo is TipoFalha.GAP_TICKS]) >= 1, (
        f"perdeu {perdidos} ticks sem emitir GAP_TICKS"
    )


def test_saturacao_nao_pode_rebobinar_o_cursor_para_tras():
    """O pulo de segundo do caminho congelado usa o segundo DO CURSOR, não
    o do começo do lote — senão um lote que atravessa vários segundos
    rebobinaria e re-entregaria tape."""
    fake = _FakeMT5(tape=_tape_denso(100, 1_000_000, ticks_por_ms=1))
    adaptador = _adaptador(fake, ticks_por_chamada=10, teto_ticks_por_chamada=10)

    cursor = _CursorTick()
    visto: list[tuple[int, int]] = []
    for _ in range(40):
        trades, novo, _falhas = adaptador._puxar_ticks(fake, cursor)
        assert novo.time_msc >= cursor.time_msc, f"cursor rebobinou: {cursor} -> {novo}"
        visto.extend(_chave(t) for t in trades)
        cursor = novo
        if not trades and cursor.time_msc >= 1_000_099:
            break
    assert len(visto) == len(set(visto)), "nenhum tick pode ser entregue duas vezes"


# ======================================================================
# Fronteiras
# ======================================================================


def test_tick_exatamente_no_timestamp_do_cursor_nao_duplica_nem_some():
    """Três negócios dividem o milissegundo do cursor. O primeiro poll vê só
    um deles; o segundo poll vê os três. Os outros dois têm de sair — uma
    vez cada. O gate antigo (`time_msc <= ultimo: continue`) matava os dois.
    """
    tape = _linhas(
        [
            (1_000_500, 4999.5, 5000.5, 5000.5, 1, TICK_FLAG_BUY, 0.0),
            (1_000_500, 4999.5, 5000.5, 5000.5, 2, TICK_FLAG_BUY, 0.0),
            (1_000_500, 4999.5, 5000.5, 5000.5, 3, TICK_FLAG_SELL, 0.0),
        ]
    )
    fake = _FakeMT5(tape=tape, visivel_ate_msc=1_000_501)
    adaptador = _adaptador(fake)

    # poll 1: o mock ainda só tem o primeiro dos três irmãos.
    fake.tape = tape[:1]
    trades_1, cursor, _ = adaptador._puxar_ticks(fake, _CursorTick())
    assert [_chave(t) for t in trades_1] == [(1_000_500, 0)]
    assert cursor == _CursorTick(1_000_500, 1)

    # poll 2: os três estão no tape; o lote re-inclui o irmão já entregue.
    fake.tape = tape
    trades_2, cursor, _ = adaptador._puxar_ticks(fake, cursor)
    assert [_chave(t) for t in trades_2] == [(1_000_500, 1), (1_000_500, 2)], (
        "os irmãos do milissegundo do cursor não podem ser descartados"
    )
    assert [t.qty for t in trades_2] == [2, 3]
    assert cursor == _CursorTick(1_000_500, 3)

    # poll 3: nada novo, e nada repetido.
    trades_3, cursor_3, _ = adaptador._puxar_ticks(fake, cursor)
    assert trades_3 == []
    assert cursor_3 == cursor


def test_virada_de_segundo_com_tape_denso_entrega_tudo_uma_vez_so():
    """O lote sempre recomeça no início do segundo do cursor. Na virada, o
    segundo antigo volta inteiro em toda chamada — e não pode vazar."""
    tape = np.concatenate(
        [
            _tape_denso(600, 1_000_400, ticks_por_ms=1),  # atravessa 1000 -> 1001
        ]
    )
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake, ticks_por_chamada=64)

    cursor = _CursorTick()
    entregues: list[tuple[int, int]] = []
    # tape revelado aos poucos, 50 ms por poll — a virada cai no meio.
    for corte in range(1_000_450, 1_001_100, 50):
        fake.visivel_ate_msc = corte
        trades, cursor, _falhas = adaptador._puxar_ticks(fake, cursor)
        entregues.extend(_chave(t) for t in trades)
    fake.visivel_ate_msc = None
    for _ in range(3):
        trades, cursor, _falhas = adaptador._puxar_ticks(fake, cursor)
        entregues.extend(_chave(t) for t in trades)

    assert len(entregues) == 600, "nenhum tick da virada pode sumir"
    assert len(set(entregues)) == 600, "nenhum tick da virada pode duplicar"
    assert entregues == sorted(entregues)
    assert entregues[0] == (1_000_400, 0)
    assert entregues[-1] == (1_000_999, 0)
    segundos = {msc // 1000 for msc, _ in entregues}
    assert segundos == {1_000}, "sanidade do cenário"


def test_virada_de_segundo_de_verdade_entre_dois_segundos_densos():
    tape = np.concatenate(
        [
            _tape_denso(1_500, 1_000_000, ticks_por_ms=3),   # segundo 1000
            _tape_denso(1_500, 1_001_000, ticks_por_ms=3),   # segundo 1001
        ]
    )
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake, ticks_por_chamada=256)

    trades, falhas, cursor, _polls = _drenar(adaptador, fake)

    chaves = [_chave(t) for t in trades]
    assert len(chaves) == 3_000
    assert len(set(chaves)) == 3_000
    assert chaves == sorted(chaves)
    assert {msc // 1000 for msc, _ in chaves} == {1_000, 1_001}
    assert falhas == []
    assert cursor.time_msc == 1_001_499


def test_lote_de_um_tick_so_e_normalizado_e_nao_percorre_os_campos():
    """numpy devolve um registro 0-d quando o array tem 1 elemento e alguém
    indexa nele; iterar nisso percorre os CAMPOS, não o registro."""
    registro = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.5, volume=1)
    assert getattr(registro, "ndim", 1) == 0
    normalizado = _normalizar_lote(registro)
    assert len(normalizado) == 1
    assert int(normalizado[0]["time_msc"]) == 1_000
    assert _normalizar_lote(None) is None


def test_busca_binaria_do_primeiro_do_ms():
    tape = _linhas(
        [(msc, 4999.5, 5000.5, 5000.5, 1, 0, 0.0) for msc in (10, 10, 20, 20, 20, 30)]
    )
    assert _primeiro_do_ms(tape, 0) == 0     # cursor virgem: não pula nada
    assert _primeiro_do_ms(tape, 10) == 0
    assert _primeiro_do_ms(tape, 15) == 2
    assert _primeiro_do_ms(tape, 20) == 2    # o PRIMEIRO do ms, não o último
    assert _primeiro_do_ms(tape, 30) == 5
    assert _primeiro_do_ms(tape, 99) == 6
    assert _primeiro_do_ms(_linhas([]), 10) == 0


def test_tick_invalido_na_ponta_do_lote_nao_prende_o_cursor():
    """Preço fora da grade não vira `Trade` — mas o cursor tem de passar por
    ele, senão um tick inválido segura o feed."""
    tape = _linhas(
        [
            (1_000_000, 4999.5, 5000.5, 5000.5, 1, TICK_FLAG_BUY, 0.0),
            (1_000_001, 4999.5, 5000.5, 5000.37, 1, TICK_FLAG_BUY, 0.0),  # fora da grade
            (1_000_002, 0.0, 0.0, 0.0, 1, TICK_FLAG_BUY, 0.0),            # preço zero
        ]
    )
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake)

    trades, cursor, _falhas = adaptador._puxar_ticks(fake, _CursorTick())

    assert len(trades) == 1
    assert cursor.time_msc == 1_000_002, f"cursor preso no tick invalido: {cursor}"
    assert cursor.ordem_no_ms == 1


# ======================================================================
# Um relógio só na borda
# ======================================================================


class _RelogioFalso:
    """Relogio local controlavel — `time_ns` e `monotonic_ns` andam juntos.

    Sem ele nao da para testar a JANELA do estimador: a poda por idade e por
    `time.monotonic_ns()`, e esperar 120 s de verdade nao e teste.
    """

    def __init__(self, base_ns=1_700_000_000_000_000_000):
        self.ns = base_ns
        self.mono = 5_000_000_000

    def avancar(self, segundos):
        delta = int(segundos * 10**9)
        self.ns += delta
        self.mono += delta

    def instalar(self, monkeypatch):
        monkeypatch.setattr(mt5_mod.time, "time_ns", lambda: self.ns)
        monkeypatch.setattr(mt5_mod.time, "monotonic_ns", lambda: self.mono)
        return self




def _tape_com_offset_de_servidor(n, offset_s, ticks_por_ms=1):
    """Tape cujo `time_msc` está `offset_s` à frente do relógio local — é o
    que um servidor MetaQuotes em GMT+3 entrega para uma máquina em GMT-3."""
    base_msc = (time.time_ns() + offset_s * 10**9) // 10**6
    return _tape_denso(n, base_msc, ticks_por_ms=ticks_por_ms), base_msc


def test_book_e_trade_da_mesma_rodada_de_poll_sao_ordenaveis():
    """O achado C.1 da R3: `Trade` vinha do relógio do SERVIDOR e
    `BookSnapshot` do relógio LOCAL. Com o servidor em GMT+3 e a janela de
    reconciliação do InferidorMBP em 300 ms, 100% das execuções viravam
    cancelamentos e a gravação saía com todos os books antes de todos os
    trades.
    """
    offset_s = 3 * 3600
    tape, _base = _tape_com_offset_de_servidor(20, offset_s)
    fake = _FakeMT5(tape=tape, book_repetido=BOOK_PADRAO)
    adaptador = _adaptador(fake)

    # mesma ordem do `_loop_borda`: ticks e depois book, na mesma rodada.
    adaptador._sincronizar_relogio(fake)
    trades, _cursor, _falhas = adaptador._puxar_ticks(fake, _CursorTick())
    snapshot = adaptador._puxar_book(fake)

    assert trades and snapshot is not None
    ultimo_trade = trades[-1].timestamp_ns

    assert snapshot.timestamp_ns > ultimo_trade, (
        "o book lido depois dos trades tem de vir depois deles no tempo"
    )
    distancia_ms = (snapshot.timestamp_ns - ultimo_trade) / 1e6
    assert distancia_ms < 300, (
        f"book e trade da mesma rodada ficaram a {distancia_ms:.0f} ms — fora da "
        "janela de reconciliacao de 300 ms; sao dois relogios diferentes"
    )
    # e o carimbo do book está no fuso do SERVIDOR, não no local.
    adianto_s = (snapshot.timestamp_ns - time.time_ns()) / 1e9
    assert adianto_s > offset_s - 60, (
        f"book carimbado com o relogio local (adianto de {adianto_s:.0f}s, "
        f"esperado ~{offset_s}s)"
    )


def test_falha_captura_usa_o_mesmo_relogio_do_trade():
    offset_s = 3 * 3600
    tape, _base = _tape_com_offset_de_servidor(5, offset_s)
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake)

    trades, _cursor, _falhas = adaptador._puxar_ticks(fake, _CursorTick())
    falha = adaptador._falha(TipoFalha.ERRO_FONTE, "teste")

    assert falha.timestamp_ns > trades[-1].timestamp_ns
    assert (falha.timestamp_ns - trades[-1].timestamp_ns) / 1e6 < 300


def test_sequencia_intercalada_de_trades_e_books_sai_monotonica(monkeypatch):
    """Trades (tempo do servidor) e books (tempo derivado) intercalados na
    mesma linha do tempo, sem inversão.

    O relógio local é CONTROLADO e anda 1 ms por poll, o mesmo passo com que
    o tape avança. Sem isso o teste é uma moeda: o tape de mentira andava
    1 ms por rodada enquanto o relógio de parede andava ~0,1 ms, então o
    relógio derivado (local + offset) ultrapassava legitimamente o tape e o
    piso monotônico empurrava um book para depois do trade seguinte —
    medido em ~10% das execuções, com o estimador desta onda E com o da
    onda 7. Nenhum servidor real entrega tape 10x mais rápido que o relógio
    de parede; o regime era do fixture, não do código.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    offset_s = 3 * 3600
    base_msc = (falso.ns + offset_s * 10**9) // 10**6
    tape = _tape_denso(40, base_msc, ticks_por_ms=2)
    fake = _FakeMT5(tape=tape, book_repetido=BOOK_PADRAO, visivel_ate_msc=base_msc)
    adaptador = _adaptador(fake)
    adaptador._sincronizar_relogio(fake)

    linha: list[int] = []
    cursor = _CursorTick()
    for i in range(1, 21):
        falso.avancar(0.001)  # o relógio local anda junto com o tape
        fake.visivel_ate_msc = base_msc + i
        trades, cursor, _falhas = adaptador._puxar_ticks(fake, cursor)
        linha.extend(t.timestamp_ns for t in trades)
        snapshot = adaptador._puxar_book(fake)
        linha.append(snapshot.timestamp_ns)

    assert len(linha) == 40 + 20
    assert linha == sorted(linha), "a linha do tempo da borda tem de ser monotônica"


def test_relogio_servidor_estima_offset_pelo_maximo_e_nao_pela_ultima_amostra():
    """Tick observado é sempre um tick que JÁ aconteceu: toda amostra
    SUBESTIMA o offset. Com "a última vence", um mercado parado re-observa o
    mesmo tick velho e o relógio derivado fica preso na hora do último
    negócio — o erro cresce a cada poll.
    """
    relogio = _RelogioServidor()
    offset_verdadeiro_ns = 3 * 3600 * 10**9

    fresco_ns = time.time_ns() + offset_verdadeiro_ns
    relogio.observar(fresco_ns)
    offset_bom = relogio.offset_ns
    assert relogio.sincronizado

    # o mesmo tick, re-observado 60 s "depois" (tape parado).
    velho_ns = fresco_ns
    for _ in range(5):
        relogio.observar(velho_ns)
    assert relogio.offset_ns >= offset_bom, (
        "amostra de tick velho não pode piorar o offset"
    )

    derivado = relogio.agora_ns()
    esperado = time.time_ns() + offset_verdadeiro_ns
    erro_s = abs(derivado - esperado) / 1e9
    assert erro_s < 1.0, f"relogio derivado com erro de {erro_s:.1f}s"


def test_relogio_servidor_e_estritamente_monotonico(monkeypatch):
    """Com o relógio local CONGELADO — que é o que a granularidade grosseira
    de `time_ns()` no Windows produz na prática dentro de um mesmo poll —
    dois eventos derivados empatariam no tempo sem o piso monotônico. E dois
    eventos que empatam deixam a ordem de entrega irreconstruível no replay,
    que ordena por timestamp.
    """
    congelado = 1_700_000_000_000_000_000
    monkeypatch.setattr(mt5_mod.time, "time_ns", lambda: congelado)

    relogio = _RelogioServidor()
    relogio.observar(congelado + 10**9)
    amostras = [relogio.agora_ns() for _ in range(200)]

    assert amostras == sorted(amostras)
    assert len(set(amostras)) == 200, "dois eventos não podem empatar no tempo"


def test_relogio_derivado_nunca_empata_com_o_ultimo_tick_observado(monkeypatch):
    congelado = 1_700_000_000_000_000_000
    monkeypatch.setattr(mt5_mod.time, "time_ns", lambda: congelado)

    relogio = _RelogioServidor()
    futuro_ns = congelado + 5 * 3600 * 10**9
    relogio.observar(futuro_ns)

    assert relogio.agora_ns() > futuro_ns, (
        "um book derivado no mesmo instante do último trade é indistinguível "
        "dele na ordenação do replay"
    )


def test_relogio_derivado_nunca_retrocede_apos_tick_mais_novo(monkeypatch):
    """Um tick à frente do relógio derivado empurra o piso: o próximo evento
    sem tempo próprio tem de vir DEPOIS dele, nunca antes."""
    congelado = 1_700_000_000_000_000_000
    monkeypatch.setattr(mt5_mod.time, "time_ns", lambda: congelado)

    relogio = _RelogioServidor()
    relogio.observar(congelado)              # offset ~0
    antes = relogio.agora_ns()
    salto_ns = congelado + 60 * 10**9        # tick 60 s à frente
    relogio.observar(salto_ns)
    depois = relogio.agora_ns()

    assert depois > salto_ns > antes


def test_sem_tick_nenhum_o_adaptador_avisa_que_caiu_no_relogio_local(caplog):
    fake = _FakeMT5()
    adaptador = _adaptador(fake)
    with caplog.at_level("WARNING", logger="fluxopro.dados.mt5"):
        antes = adaptador._agora_ns()
        depois = adaptador._agora_ns()
    assert depois > antes
    assert any("relogio LOCAL" in r.message for r in caplog.records), (
        "degradar para o relogio local nao pode ser silencioso"
    )


# ======================================================================
# Partida a frio
# ======================================================================


def test_cursor_inicial_e_semeado_pelo_ultimo_tick_conhecido():
    """`copy_ticks_from(sym, 0, ...)` devolve os PRIMEIROS ticks do
    histórico — anos atrás. Partir do zero publicaria histórico velho como
    tape ao vivo."""
    tape = _tape_denso(5, 1_700_000_000_000, ticks_por_ms=1)
    fake = _FakeMT5(tape=tape)
    adaptador = _adaptador(fake)

    cursor = adaptador._cursor_inicial(fake)

    assert cursor.time_msc == 1_700_000_000_004
    assert cursor.ordem_no_ms == 0, "os irmãos do ms do último tick têm de entrar"


def test_cursor_inicial_sem_symbol_info_tick_avisa_e_degrada(caplog):
    fake = _FakeMT5Antigo(tape=_tape_denso(3, 1_000_000))
    adaptador = _adaptador(fake)
    with caplog.at_level("WARNING", logger="fluxopro.dados.mt5"):
        cursor = adaptador._cursor_inicial(fake)
    assert cursor == _CursorTick()
    assert any("semear o cursor" in r.message for r in caplog.records)


def test_adaptador_nao_republica_o_historico_na_partida():
    """Ponta a ponta: com um tape de 5.000 ticks históricos, a partida só
    pode entregar o último (e os irmãos do milissegundo dele)."""
    tape = _tape_denso(5_000, 1_700_000_000_000, ticks_por_ms=1)
    fake = _FakeMT5(tape=tape)
    barramento = Barramento()
    trades: list[Trade] = []
    barramento.assinar(Trade, trades.append)

    adaptador = AdaptadorMT5(
        barramento, "WDOV26", WDO_GRID, mt5_module=fake, intervalo_poll_s=0.005
    )
    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.2)
    adaptador.parar()
    thread.join(timeout=2.0)

    assert len(trades) <= 2, f"a partida republicou {len(trades)} ticks de historico"
    assert trades, "o ultimo tick conhecido do simbolo deve sair"


# ======================================================================
# Testes preservados da suíte anterior (mesma intenção, mock honesto)
# ======================================================================


def test_importar_mt5_sem_pacote_instalado_da_erro_claro(monkeypatch):
    """A ausencia do pacote e SIMULADA, e nao herdada da maquina.

    Este teste passava por acidente: ele so verificava a mensagem porque o
    `MetaTrader5` nao estava instalado aqui. No dia em que o pacote entrou — e
    entrou, para ligar o terminal de verdade — ele virou vermelho sem que nada
    do produto tivesse mudado.

    Um teste cujo resultado depende do que ESTA instalado na maquina nao mede o
    codigo, mede o ambiente. Aqui o `ImportError` e forcado, entao a mensagem
    de erro continua sendo verificada nas duas maquinas: na que tem o pacote e
    na que nao tem.
    """
    import builtins

    real = builtins.__import__

    def sem_mt5(nome, *args, **kwargs):
        if nome == "MetaTrader5":
            raise ImportError("simulado: pacote ausente")
        return real(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_mt5)
    with pytest.raises(RuntimeError, match="MetaTrader5"):
        _importar_mt5()


def test_importar_mt5_devolve_o_pacote_quando_ele_existe():
    """A outra metade, que faltava.

    Sem ela, o teste acima passaria numa versao de `_importar_mt5` que
    levantasse SEMPRE — e a suite ficaria verde com o adaptador ao vivo
    quebrado.
    """
    pytest.importorskip("MetaTrader5", reason="pacote nao instalado nesta maquina")
    modulo = _importar_mt5()
    assert modulo.__name__ == "MetaTrader5"


def test_derivar_deltas_add_update_delete():
    anterior = BookSnapshot(
        timestamp_ns=100, symbol="WDOV26",
        bids=(BookLevel(9999, 10, 1), BookLevel(9998, 20, 2)),
        asks=(BookLevel(10001, 15, 1),),
    )
    atual = BookSnapshot(
        timestamp_ns=200, symbol="WDOV26",
        bids=(BookLevel(9999, 30, 1), BookLevel(9997, 5, 1)),  # 9999 update, 9998 delete, 9997 add
        asks=(BookLevel(10001, 15, 1),),  # sem mudanca
    )
    deltas = derivar_deltas(anterior, atual)
    por_preco = {(d.side, d.price): d for d in deltas}

    assert por_preco[(Side.BUY, 9999)].action == BookAction.UPDATE
    assert por_preco[(Side.BUY, 9999)].qty == 30
    assert por_preco[(Side.BUY, 9998)].action == BookAction.DELETE
    assert por_preco[(Side.BUY, 9997)].action == BookAction.ADD
    assert por_preco[(Side.BUY, 9997)].qty == 5
    # ask nao mudou -> nenhum delta do lado SELL
    assert not any(d.side == Side.SELL for d in deltas)


def test_derivar_deltas_snapshot_identico_nao_gera_delta():
    snap = BookSnapshot(
        timestamp_ns=100, symbol="WDOV26",
        bids=(BookLevel(9999, 10, 1),), asks=(BookLevel(10001, 15, 1),),
    )
    assert derivar_deltas(snap, snap) == []


def test_inferir_agressor_via_flags_buy():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.5, volume=1, flags=TICK_FLAG_BUY)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.BUY


def test_inferir_agressor_via_flags_sell():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=4999.5, volume=1, flags=TICK_FLAG_SELL)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.SELL


def test_inferir_agressor_sem_flags_por_preco_no_ask_e_compra():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.5, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.BUY


def test_inferir_agressor_sem_flags_por_preco_no_bid_e_venda():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=4999.5, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.SELL


def test_inferir_agressor_ambiguo_e_unknown():
    adaptador = AdaptadorMT5(Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5())
    tick = _tick(1_000, bid=4999.5, ask=5000.5, last=5000.0, volume=1, flags=0)
    assert adaptador._inferir_agressor(_FakeMT5(), tick) is AgressorSide.UNKNOWN


def test_adaptador_mt5_publica_trades_via_fila_ate_thread_principal():
    """Mesma intenção do teste original (thread de borda -> fila -> barramento
    -> `parar()` encerra o módulo), agora com um tape honesto de 1 tick."""
    fake = _FakeMT5(
        tape=_linhas([(1_000, 4999.5, 5000.5, 5000.5, 3, TICK_FLAG_BUY, 0.0)])
    )
    barramento = Barramento()
    trades: list[Trade] = []
    barramento.assinar(Trade, trades.append)

    adaptador = AdaptadorMT5(
        barramento, "WDOV26", WDO_GRID, mt5_module=fake, intervalo_poll_s=0.01
    )
    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.2)
    adaptador.parar()
    thread.join(timeout=2.0)

    assert len(trades) == 1, "o unico tick do tape sai uma vez so, apesar dos N polls"
    assert trades[0].symbol == "WDOV26"
    assert trades[0].side_agressor is AgressorSide.BUY
    assert trades[0].qty == 3
    assert fake.encerrado is True
    assert fake.book_liberado is True


def test_excecao_de_assinante_fecha_thread_e_terminal_mt5():
    fake = _FakeMT5(
        tape=_linhas([(1_000, 4999.5, 5000.5, 5000.5, 3, TICK_FLAG_BUY, 0.0)])
    )
    barramento = Barramento()

    def falhar(_trade: Trade) -> None:
        raise RuntimeError("assinante quebrou")

    barramento.assinar(Trade, falhar)
    adaptador = AdaptadorMT5(
        barramento,
        "WDOV26",
        WDO_GRID,
        mt5_module=fake,
        intervalo_poll_s=0.001,
        fila_maxsize=2,
    )

    with pytest.raises(RuntimeError, match="assinante quebrou"):
        adaptador.iniciar()

    assert adaptador._thread is not None and not adaptador._thread.is_alive()
    assert fake.encerrado is True
    assert fake.book_liberado is True


def test_fila_mt5_e_limitada_e_parametros_de_backpressure_sao_validados():
    adaptador = AdaptadorMT5(
        Barramento(),
        "WDOV26",
        WDO_GRID,
        mt5_module=_FakeMT5(),
        fila_maxsize=3,
        backpressure_timeout_s=0.01,
    )

    assert adaptador._fila.maxsize == 3
    with pytest.raises(ValueError, match="fila_maxsize"):
        AdaptadorMT5(
            Barramento(), "WDOV26", WDO_GRID, mt5_module=_FakeMT5(), fila_maxsize=0
        )
    with pytest.raises(ValueError, match="backpressure_timeout_s"):
        AdaptadorMT5(
            Barramento(),
            "WDOV26",
            WDO_GRID,
            mt5_module=_FakeMT5(),
            backpressure_timeout_s=0,
        )


def test_backpressure_mt5_e_interrompivel_e_descarte_vira_falha_captura():
    barramento = Barramento()
    trades: list[Trade] = []
    falhas: list[FalhaCaptura] = []
    barramento.assinar(Trade, trades.append)
    barramento.assinar(FalhaCaptura, falhas.append)
    adaptador = AdaptadorMT5(
        barramento,
        "WDOV26",
        WDO_GRID,
        mt5_module=_FakeMT5(),
        fila_maxsize=1,
        backpressure_timeout_s=0.01,
    )
    primeiro = Trade(100, "WDOV26", 10_000, 1, AgressorSide.BUY, "T1")
    tardio = Trade(101, "WDOV26", 10_001, 1, AgressorSide.BUY, "T2")
    assert adaptador._enfileirar(primeiro)
    resultado: list[bool] = []

    produtor = threading.Thread(
        target=lambda: resultado.append(adaptador._enfileirar(tardio))
    )
    adaptador._thread = produtor
    produtor.start()
    time.sleep(0.03)
    assert produtor.is_alive(), "fila cheia deve aplicar backpressure, nao descartar cedo"

    adaptador._parar_evt.set()
    produtor.join(timeout=1)
    assert resultado == [False]

    # Drena o evento aceito e, antes de sair, materializa o descarte pendente.
    adaptador._loop_consumo()

    assert trades == [primeiro]
    assert len(falhas) == 1
    assert falhas[0].tipo is TipoFalha.GAP_TICKS
    assert "dropped_events=1" in falhas[0].detalhe
    assert "queue_maxsize=1" in falhas[0].detalhe


def test_falha_polling_mt5_emite_desconexao_erro_e_reconexao_observaveis():
    class _FakeInstavel(_FakeMT5):
        def __init__(self):
            super().__init__()
            self._falhou = False

        def copy_ticks_from(self, symbol, de, count, flags):
            if not self._falhou:
                self._falhou = True
                raise OSError("rede caiu")
            return super().copy_ticks_from(symbol, de, count, flags)

    fake = _FakeInstavel()
    barramento = Barramento()
    falhas: list[FalhaCaptura] = []
    barramento.assinar(FalhaCaptura, falhas.append)
    monitor = FeedQualityMonitor(source=FeedSource.MT5, clock_ns=time.time_ns)
    observer = FeedQualityObserver(barramento, monitor)
    observer.iniciar()
    adaptador = AdaptadorMT5(
        barramento,
        "WDOV26",
        WDO_GRID,
        mt5_module=fake,
        intervalo_poll_s=0.005,
        fila_maxsize=8,
    )

    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.08)
    adaptador.parar()
    thread.join(timeout=2)

    tipos = [falha.tipo for falha in falhas]
    assert tipos.count(TipoFalha.DESCONEXAO) == 1
    assert tipos.count(TipoFalha.ERRO_FONTE) == 1
    assert tipos.count(TipoFalha.RECONEXAO) == 1
    snap = monitor.snapshot()
    assert snap.disconnects == 1
    assert snap.source_errors == 1
    assert snap.reconnections == 1
    assert snap.state is FeedState.CONNECTED
    assert snap.reconnect_attempts == 0


def test_adaptador_mt5_deriva_book_delta_entre_polls_consecutivos():
    book_1 = [BookInfo(0, 4999.5, 10, 10.0), BookInfo(1, 5000.5, 15, 15.0)]
    book_2 = [BookInfo(0, 4999.5, 25, 25.0), BookInfo(1, 5000.5, 15, 15.0)]
    fake = _FakeMT5(books_por_chamada=[book_1, book_2, book_2], book_repetido=book_2)

    barramento = Barramento()
    snapshots: list[BookSnapshot] = []
    deltas: list[BookDelta] = []
    barramento.assinar(BookSnapshot, snapshots.append)
    barramento.assinar(BookDelta, deltas.append)

    adaptador = AdaptadorMT5(
        barramento, "WDOV26", WDO_GRID, mt5_module=fake, intervalo_poll_s=0.01
    )
    thread = threading.Thread(target=adaptador.iniciar, daemon=True)
    thread.start()
    time.sleep(0.2)
    adaptador.parar()
    thread.join(timeout=2.0)

    assert len(snapshots) >= 2
    # a segunda leitura de book (qty 10->25 no bid) deve ter gerado UPDATE
    assert any(d.action == BookAction.UPDATE and d.qty == 25 for d in deltas)


# ======================================================================
# O relogio esquece regressoes do servidor (R4 A.4)
# ======================================================================
#
# O estimador de MAXIMO da onda 7 consertou o relogio preso com tape parado
# e criou uma catraca: uma regressao do relogio do servidor (troca de
# servidor da corretora, ajuste de NTP, failover) inflava o offset PARA
# SEMPRE. Uma regressao de 400 ms ja excede a janela de reconciliacao de
# 300 ms do `InferidorMBP` ⇒ 100% das execucoes viram cancelamento. Os
# testes abaixo prendem os TRES regimes que o estimador tem de separar:
# tape parado (nao pode prender), regressao de servidor (tem de esquecer,
# em tempo limitado e ALTO) e tick atrasado isolado (NAO pode resetar).


def _alimentar(relogio, falso, offset_ns, n, passo_s=0.05, idade_s=0.0):
    """`n` ticks de um servidor com `offset_ns`, tape andando a `passo_s`.

    `idade_s` e a idade do tick no momento em que e observado — a
    SUBESTIMACAO estrutural que obriga o estimador a ser um maximo.
    Devolve a lista de retornos de `observar` (para ver a regressao).
    """
    saidas = []
    for _ in range(n):
        falso.avancar(passo_s)
        servidor_ns = falso.ns + offset_ns - int(idade_s * 10**9)
        saidas.append(relogio.observar(servidor_ns))
    return saidas


def _erro_do_derivado_s(relogio, falso, offset_ns):
    """Quanto o relogio derivado erra em relacao a verdade corrente."""
    return abs(relogio.agora_ns() - (falso.ns + offset_ns)) / 1e9


def test_relogio_esquece_regressao_de_400ms_do_servidor(monkeypatch):
    """O caso medido pela R4: 400 ms de recuo bastam para estourar a janela
    de reconciliacao de 300 ms, e com o maximo puro o erro era PERMANENTE
    (5.000 amostras corretas nao moviam o estimador um nanossegundo).

    Contrato preso aqui: converge em `_AMOSTRAS_PARA_REGRESSAO` amostras (3
    polls, ~150 ms com o poll padrao de 50 ms) e `observar` DEVOLVE o recuo
    para virar `FalhaCaptura` — corrigir em silencio nao vale.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_bom = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_bom, 50)
    assert _erro_do_derivado_s(relogio, falso, offset_bom) < 0.05

    # o servidor RECUA 400 ms e o tape continua andando no referencial novo.
    recuo_ns = 400_000_000
    offset_novo = offset_bom - recuo_ns
    saidas = _alimentar(relogio, falso, offset_novo, 20)

    detectadas = [x for x in saidas if x is not None]
    assert detectadas, "regressao de 400 ms passou despercebida — o maximo virou catraca"
    assert abs(detectadas[0] - recuo_ns) < 50_000_000, (
        f"recuo reportado ({detectadas[0]}) nao bate com os 400 ms reais"
    )
    # o tick do step em si nao ANDA para a frente (recua), entao nao conta
    # para o detector: convergencia = `_AMOSTRAS_PARA_REGRESSAO` + 1 polls.
    polls_ate_detectar = saidas.index(detectadas[0]) + 1
    assert polls_ate_detectar <= _AMOSTRAS_PARA_REGRESSAO + 1, (
        f"a regressao levou {polls_ate_detectar} polls para ser detectada"
    )

    erro_s = _erro_do_derivado_s(relogio, falso, offset_novo)
    assert erro_s * 1000 < 300, (
        f"apos a regressao o relogio derivado erra {erro_s * 1000:.0f} ms — "
        "ainda fora da janela de reconciliacao de 300 ms do InferidorMBP"
    )


def test_regressao_do_servidor_vira_falha_captura_no_fluxo(monkeypatch):
    """A regressao nao pode ficar so dentro do estimador: o replay tem de
    ver a descontinuidade. Aqui pelo caminho real (`_puxar_ticks`)."""
    falso = _RelogioFalso().instalar(monkeypatch)
    base_msc = (falso.ns + 3 * 3600 * 10**9) // 10**6

    # 10 ticks bons, depois o servidor recua 2 s e o tape recomeca dali.
    bons = [(base_msc + i, 4999.5, 5000.5, 5000.5, 1, TICK_FLAG_BUY, 0.0) for i in range(10)]
    recuado = base_msc - 2000
    depois = [(recuado + i, 4999.5, 5000.5, 5000.5, 1, TICK_FLAG_BUY, 0.0) for i in range(10)]

    adaptador = _adaptador(_FakeMT5())
    falhas_vistas = []
    cursor = _CursorTick()
    for lote in [bons] + [[t] for t in depois]:
        fake = _FakeMT5(tape=_linhas(lote))
        _trades, _c, falhas = adaptador._puxar_ticks(fake, _CursorTick())
        falhas_vistas.extend(falhas)
        falso.avancar(0.05)

    tipos = [f.tipo for f in falhas_vistas]
    assert TipoFalha.RELOGIO_REGREDIU in tipos, (
        "regressao do relogio do servidor tem de ser ALTA (FalhaCaptura), "
        f"nunca silenciosa; falhas vistas: {tipos}"
    )
    falha = next(f for f in falhas_vistas if f.tipo is TipoFalha.RELOGIO_REGREDIU)
    assert "recuou" in falha.detalhe
    assert falha.symbol == adaptador._symbol


def test_tape_parado_por_10_minutos_nao_prende_o_relogio_derivado(monkeypatch):
    """O defeito que o MAXIMO consertou, e que a correcao da regressao NAO
    pode reintroduzir. Com o tape parado o mesmo tick e re-observado a cada
    poll e cada amostra e mais velha que a anterior; se o estimador adotasse
    a amostra corrente (ou deixasse a janela envelhecer ate so restar
    amostra degradada), o relogio derivado ficaria preso na hora do ultimo
    negocio e o erro cresceria sem limite — medido: -60 s e subindo.

    10 minutos e MAIS que a janela de 120 s de proposito: e exatamente o
    regime em que uma janela deslizante ingenua quebra.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_ns = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_ns, 20)

    tick_congelado = falso.ns + offset_ns  # o ultimo negocio do dia
    piores = []
    for _ in range(10 * 60 * 20):  # 10 min a 20 polls/s
        falso.avancar(0.05)
        assert relogio.observar(tick_congelado) is None, (
            "tape parado nao e regressao de servidor — nao pode resetar"
        )
        piores.append(_erro_do_derivado_s(relogio, falso, offset_ns))

    assert max(piores) < 1.0, (
        f"com o tape parado 10 min o relogio derivado errou {max(piores):.1f} s — "
        "ficou preso na hora do ultimo negocio (defeito da onda 6)"
    )
    assert relogio.amostras_na_janela <= 2, (
        "re-observar o mesmo tick nao pode encher a janela"
    )


def test_tick_atrasado_isolado_nao_dispara_reset(monkeypatch):
    """A distincao que sustenta o desenho: um tick atrasado no meio do fluxo
    produz o MESMO sinal bruto que uma regressao ("estimativa abaixo do
    maximo"). O que separa os dois e o relogio do SERVIDOR — na regressao o
    tape volta a ANDAR PARA A FRENTE num referencial novo; um tick atrasado
    e um ponto isolado e o proximo tick volta acima do pico.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_ns = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_ns, 30)
    offset_antes = relogio.offset_ns

    atraso_ns = 5 * 10**9  # 5 s de atraso: MUITO acima do limiar de 250 ms
    for _ in range(40):
        falso.avancar(0.05)
        assert relogio.observar(falso.ns + offset_ns - atraso_ns) is None, (
            "um tick atrasado ISOLADO nao e regressao de servidor"
        )
        falso.avancar(0.05)
        assert relogio.observar(falso.ns + offset_ns) is None

    assert relogio.offset_ns >= offset_antes - 10**8, (
        "tick atrasado isolado degradou o offset"
    )
    assert _erro_do_derivado_s(relogio, falso, offset_ns) < 0.1


def test_adaptador_atrasado_nao_e_confundido_com_regressao(monkeypatch):
    """Regime achado pelo `bench_mt5.py`: no pico de 50.000 ticks/s cada poll
    custa mais CPU do que o tape que ele consome, entao o adaptador FICA PARA
    TRAS — a hora do servidor continua subindo, so que mais devagar que a
    local, e a estimativa despenca centenas de ms por poll.

    Um detector que olhasse so o deficit chamaria isso de regressao (medido:
    oito falsos positivos numa unica passada do benchmark) e RESETARIA o
    estimador numa amostra velha, jogando fora o unico offset bom que ele
    tem. O que separa os dois casos e o sinal fisico: aqui o `time_msc`
    NUNCA anda para tras.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_ns = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_ns, 30)
    offset_bom = relogio.offset_ns

    # 40 polls em que o local anda 500 ms e o tape so 50 ms: o adaptador
    # acumula 450 ms de atraso por poll, 18 s no fim.
    servidor_ns = falso.ns + offset_ns
    for _ in range(40):
        falso.avancar(0.5)          # relogio local: +500 ms
        servidor_ns += 50_000_000   # tape consumido:  +50 ms
        assert relogio.observar(servidor_ns) is None, (
            "adaptador atrasado NAO e regressao de servidor — o time_msc nunca "
            "andou para tras"
        )

    assert relogio.offset_ns >= offset_bom - 10**8, (
        "o estimador jogou fora o offset bom por causa do proprio atraso"
    )


def test_regressao_sub_limiar_e_absorvida_pela_janela_deslizante(monkeypatch):
    """Recuo abaixo de `_LIMIAR_REGRESSAO_NS` nao dispara o detector — e nem
    precisa, porque nao estoura a janela de 300 ms. Quem o corrige e a
    MEMORIA FINITA do maximo, em no maximo `_JANELA_OFFSET_S`. Com o maximo
    puro esse erro era permanente.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_bom = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_bom, 50)

    recuo_ns = _LIMIAR_REGRESSAO_NS // 2
    offset_novo = offset_bom - recuo_ns
    saidas = _alimentar(
        relogio, falso, offset_novo, int(_JANELA_OFFSET_S / 0.05) + 40
    )
    assert all(x is None for x in saidas), (
        "recuo sub-limiar nao deve ser declarado regressao (falso positivo)"
    )
    erro_s = _erro_do_derivado_s(relogio, falso, offset_novo)
    assert erro_s * 1000 < 50, (
        f"a janela deslizante nao esqueceu o offset velho: erro de "
        f"{erro_s * 1000:.0f} ms depois de {_JANELA_OFFSET_S:.0f} s"
    )


def test_janela_do_offset_tem_memoria_limitada(monkeypatch):
    """R4 tambem achou vazamento de heap em estrutura sem teto. A janela e um
    deque monotonico com teto DURO: sessao longa nao pode virar memoria.
    """
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor(janela_s=10**6, max_amostras=64)

    # offset ESTRITAMENTE DECRESCENTE e o pior caso do deque monotonico:
    # cada amostra nova e MENOR que a anterior, entao nenhuma e podada pela
    # regra do maximo e todas ficam na fila. (Offset crescente e o caso
    # facil: a amostra nova expulsa todas as anteriores e a fila tem 1.)
    # O regime existe: e o adaptador consumindo tape mais devagar que o
    # relogio de parede — o mesmo do `test_adaptador_atrasado...`.
    servidor_ns = falso.ns + 10**9
    for _ in range(5000):
        falso.avancar(0.010)          # local: +10 ms
        servidor_ns += 1_000_000      # tape:  +1 ms
        relogio.observar(servidor_ns)
    assert relogio.amostras_na_janela <= 64, (
        f"janela cresceu para {relogio.amostras_na_janela} entradas apesar do teto"
    )


def test_propriedade_erro_do_relogio_limitado_em_sequencia_adversarial(monkeypatch):
    """Propriedade: em QUALQUER mistura de tape andando, tape parado, ticks
    fora de ordem e regressoes de servidor,

      (a) o erro do relogio derivado e LIMITADO — nada de catraca;
      (b) fora dos episodios de convergencia que se seguem a cada
          regressao, o erro fica dentro dos 300 ms da reconciliacao do
          `InferidorMBP`;
      (c) cada episodio de convergencia FECHA, e em poucas amostras.

    A sequencia e deterministica (semente fixa) e o tape e simulado como
    estado de verdade (`servidor_ns` corrente), nao como sorteio
    independente: tape parado repete o ULTIMO tick, tick fora de ordem e um
    tick JA passado, regressao desloca o referencial inteiro para tras. Sem
    isso o teste testaria um mundo que nao existe.

    O teto de `_MAX_AMOSTRAS_CONVERGENCIA` amostras e maior que os
    `_AMOSTRAS_PARA_REGRESSAO + 1` do caso limpo de proposito: tape parado
    nao alimenta o detector (nao ha tempo de servidor novo) e um tick fora
    de ordem no meio do episodio zera a contagem de suspeitas. Os dois
    ATRASAM a convergencia; nenhum dos dois a impede — e e isso que este
    teste prende.
    """
    import random

    _MAX_AMOSTRAS_CONVERGENCIA = 20

    rng = random.Random(20260821)
    falso = _RelogioFalso().instalar(monkeypatch)
    relogio = _RelogioServidor()

    offset_ns = 3 * 3600 * 10**9
    _alimentar(relogio, falso, offset_ns, 20)
    servidor_ns = falso.ns + offset_ns

    pior_absoluto = 0.0
    pior_fora_de_episodio = 0.0
    episodios = []       # tamanho de cada convergencia, em amostras
    em_episodio = 0      # 0 = estavel; >0 = amostras desde a regressao
    regressoes = 0

    for passo in range(4000):
        modo = rng.choices(
            ["andar", "parado", "fora_de_ordem", "regressao"],
            weights=[70, 20, 8, 2],
        )[0]
        falso.avancar(0.05)

        if modo == "parado":
            relogio.observar(servidor_ns)          # o mesmo tick de novo
        elif modo == "fora_de_ordem":
            relogio.observar(servidor_ns - rng.randint(10**9, 8 * 10**9))
        else:
            if modo == "regressao":
                offset_ns -= rng.randint(300_000_000, 10 * 10**9)
                if em_episodio:
                    episodios.append(em_episodio)  # regressao sobre regressao
                em_episodio = 1
                regressoes += 1
            servidor_ns = falso.ns + offset_ns
            relogio.observar(servidor_ns)

        erro = _erro_do_derivado_s(relogio, falso, offset_ns)
        pior_absoluto = max(pior_absoluto, erro)

        if em_episodio:
            if erro * 1000 < 300:
                episodios.append(em_episodio)
                em_episodio = 0
            else:
                em_episodio += 1
                assert em_episodio <= _MAX_AMOSTRAS_CONVERGENCIA, (
                    f"no passo {passo} o relogio nao convergiu em "
                    f"{_MAX_AMOSTRAS_CONVERGENCIA} amostras apos a regressao "
                    f"(erro corrente {erro * 1000:.0f} ms) — e catraca de novo"
                )
        else:
            pior_fora_de_episodio = max(pior_fora_de_episodio, erro)

    assert regressoes >= 20, "a sequencia adversarial nao exercitou regressoes"
    assert len(episodios) >= regressoes - 1, "algum episodio nunca fechou"
    assert pior_absoluto < 30.0, (
        f"erro do relogio derivado chegou a {pior_absoluto:.1f} s — nem "
        "durante a convergencia ele pode ser ilimitado"
    )
    assert pior_fora_de_episodio * 1000 < 300, (
        f"fora dos episodios de convergencia o erro chegou a "
        f"{pior_fora_de_episodio * 1000:.0f} ms — acima da janela de 300 ms"
    )
