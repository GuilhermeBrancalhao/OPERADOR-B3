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
from fluxopro.dados.mt5 import (
    AdaptadorMT5,
    _CursorTick,
    _importar_mt5,
    _normalizar_lote,
    _primeiro_do_ms,
    _RelogioServidor,
    derivar_deltas,
)

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


def test_sequencia_intercalada_de_trades_e_books_sai_monotonica():
    offset_s = 3 * 3600
    base_msc = (time.time_ns() + offset_s * 10**9) // 10**6
    tape = _tape_denso(40, base_msc, ticks_por_ms=2)
    fake = _FakeMT5(tape=tape, book_repetido=BOOK_PADRAO, visivel_ate_msc=base_msc)
    adaptador = _adaptador(fake)
    adaptador._sincronizar_relogio(fake)

    linha: list[int] = []
    cursor = _CursorTick()
    for i in range(1, 21):
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


def test_importar_mt5_sem_pacote_instalado_da_erro_claro():
    with pytest.raises(RuntimeError, match="MetaTrader5"):
        _importar_mt5()


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
