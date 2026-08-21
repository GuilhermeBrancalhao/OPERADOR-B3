"""Testes da cadeia de integridade da gravação (defeito R2, `criticas/nucleo_r2.md`
seção "ÚNICO MAIOR GAP" / tabela N08/N09/N16/N17): prova que a verificação de
hash DETECTA corrupção, que o leitor RECUSA/sinaliza em vez de mentir, e que
o recorte por intervalo de horário REALMENTE filtra — as três coisas que a
auditoria mostrou poderem ser desligadas sem mover um teste.

Não existe fonte externa de histórico de book de WDO/WIN (ver docstring de
`gravador.py`): se essa cadeia mentir, todo backtest futuro fica envenenado
sem chance de comparar contra uma segunda fonte.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable

import pytest

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao, IntegridadeInvalidaError
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.gravacao.gravador import Gravador

_SYMBOL = "WDOV26"
_DIA_1_TS = 1_700_000_000_000_000_000  # bem no meio de um dia UTC qualquer


def _trade(ts_ns: int, trade_id: str, price: int = 10000, qty: int = 5) -> Trade:
    return Trade(
        timestamp_ns=ts_ns, symbol=_SYMBOL, price=price, qty=qty,
        side_agressor=AgressorSide.BUY, trade_id=trade_id,
    )


def _gravar(tmp_path: Path, trades: list[Trade]) -> None:
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path)
    gravador.iniciar()
    for t in trades:
        barramento.publicar(t)
    gravador.parar()


def _diretorio_do_dia(tmp_path: Path) -> Path:
    return next((tmp_path / _SYMBOL).iterdir())


def _editar_conteudo_gz(caminho: Path, transformar: Callable[[list[str]], list[str]]) -> None:
    """Descomprime, aplica `transformar` nas linhas de texto e recomprime —
    simula 'editado à mão' (gzip continua válido, o CONTEÚDO mudou)."""
    with gzip.open(caminho, "rt", encoding="utf-8", newline="") as f:
        linhas = f.read().splitlines()
    novas = transformar(linhas)
    with gzip.open(caminho, "wt", encoding="utf-8", newline="") as f:
        f.write("\n".join(novas) + "\n")


def _ts_utc(dia: date, hh: int, mm: int) -> int:
    dt = datetime.combine(dia, time(hh, mm), tzinfo=timezone.utc)
    return int(dt.timestamp() * 1e9)


# ---------------------------------------------------------------------
# Round-trip: gravar -> catalogar -> ler -> mesma sequência, integridade OK
# ---------------------------------------------------------------------

def test_round_trip_gravar_catalogar_ler_com_integridade_confirmada(tmp_path):
    trades = [
        _trade(_DIA_1_TS, "T1", price=10000, qty=5),
        _trade(_DIA_1_TS + 1_000_000_000, "T2", price=10001, qty=3),
        _trade(_DIA_1_TS + 2_000_000_000, "T3", price=10002, qty=7),
    ]
    _gravar(tmp_path, trades)

    catalogo = Catalogo(tmp_path)
    entradas = catalogo.escanear()
    assert len(entradas) == 1
    entrada = entradas[0]
    assert entrada.n_eventos_total == 3

    integridade = catalogo.verificar_integridade(entrada)
    assert integridade  # nao vazio
    assert all(integridade.values()), integridade

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    leitor = AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True)
    leitor.iniciar()

    assert [t.trade_id for t in coletados] == ["T1", "T2", "T3"]
    assert [t.price for t in coletados] == [10000, 10001, 10002]


# ---------------------------------------------------------------------
# Corrupção de CONTEÚDO (mata N16 + N09): verificar_integridade detecta,
# leitor recusa
# ---------------------------------------------------------------------

def test_verificar_integridade_detecta_conteudo_editado_a_mao(tmp_path):
    _gravar(tmp_path, [_trade(_DIA_1_TS, "T1", qty=5)])

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    assert all(catalogo.verificar_integridade(entrada).values())

    caminho = entrada.arquivo("trades.csv")
    assert caminho is not None
    _editar_conteudo_gz(
        caminho,
        lambda linhas: [linhas[0]] + [l.replace(",5,BUY,", ",9,BUY,") for l in linhas[1:]],
    )

    resultado = catalogo.verificar_integridade(entrada)
    assert resultado["trades.csv"] is False


def test_leitor_recusa_arquivo_com_conteudo_editado_a_mao(tmp_path):
    _gravar(tmp_path, [_trade(_DIA_1_TS, "T1", qty=5)])

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    caminho = entrada.arquivo("trades.csv")
    assert caminho is not None
    _editar_conteudo_gz(
        caminho,
        lambda linhas: [linhas[0]] + [l.replace(",5,BUY,", ",9,BUY,") for l in linhas[1:]],
    )

    barramento = Barramento()
    with pytest.raises(IntegridadeInvalidaError):
        AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True)


def test_verificar_integridade_detecta_hash_divergente_no_meta_sem_tocar_dado(tmp_path):
    """Hash inconsistente: o meta.json diz uma coisa, o dado real (nunca
    tocado) é outra — cobre o caso em que o PROPRIO meta foi adulterado,
    nao o CSV."""
    _gravar(tmp_path, [_trade(_DIA_1_TS, "T1")])

    diretorio = _diretorio_do_dia(tmp_path)
    meta_path = diretorio / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["hashes_sha256"]["trades.csv"] = "0" * 64
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]

    resultado = catalogo.verificar_integridade(entrada)
    assert resultado["trades.csv"] is False

    barramento = Barramento()
    with pytest.raises(IntegridadeInvalidaError):
        AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True)


def test_verificar_integridade_detecta_arquivo_truncado(tmp_path):
    trades = [_trade(_DIA_1_TS + i * 1_000_000_000, f"T{i}") for i in range(10)]
    _gravar(tmp_path, trades)

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    caminho = entrada.arquivo("trades.csv")
    assert caminho is not None

    bruto = caminho.read_bytes()
    caminho.write_bytes(bruto[: len(bruto) // 2])

    resultado = catalogo.verificar_integridade(entrada)
    assert resultado["trades.csv"] is False

    barramento = Barramento()
    with pytest.raises(IntegridadeInvalidaError):
        AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True)


def test_leitor_com_verificar_hash_false_documenta_contrato_de_pular_a_checagem(tmp_path):
    """`verificar_hash=False` é uma opção explícita e documentada (não um
    bug) — este teste só prova que o contrato é esse: sem ela, corrupção
    não é detectada na construção do leitor."""
    _gravar(tmp_path, [_trade(_DIA_1_TS, "T1", qty=5)])
    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    caminho = entrada.arquivo("trades.csv")
    assert caminho is not None
    _editar_conteudo_gz(
        caminho,
        lambda linhas: [linhas[0]] + [l.replace(",5,BUY,", ",9,BUY,") for l in linhas[1:]],
    )

    barramento = Barramento()
    leitor = AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=False)
    assert leitor is not None  # nao levanta


# ---------------------------------------------------------------------
# Recorte por intervalo de horário (mata N08 + N17): REALMENTE filtra
# ---------------------------------------------------------------------

def test_consultar_intervalo_nao_troca_hora_inicio_com_hora_fim(tmp_path):
    dia = date(2026, 8, 20)
    ts = _ts_utc(dia, 12, 0)
    _gravar(tmp_path, [_trade(ts, "T1")])

    catalogo = Catalogo(tmp_path)
    catalogo.escanear()

    entrada, ts_inicio, ts_fim = catalogo.consultar_intervalo(
        _SYMBOL, dia, hora_inicio=time(9, 0), hora_fim=time(10, 30)
    )
    assert entrada is not None
    assert ts_inicio == _ts_utc(dia, 9, 0)
    assert ts_fim == _ts_utc(dia, 10, 30)
    assert ts_inicio != ts_fim


def test_leitor_filtra_por_intervalo_de_horario_exclui_fora_da_janela(tmp_path):
    dia = date(2026, 8, 20)
    trades = [
        _trade(_ts_utc(dia, 8, 0), "ANTES"),
        _trade(_ts_utc(dia, 9, 15), "DENTRO_1"),
        _trade(_ts_utc(dia, 9, 45), "DENTRO_2"),
        _trade(_ts_utc(dia, 10, 0), "DENTRO_BORDA"),  # igual ao ts_fim, inclusive
        _trade(_ts_utc(dia, 11, 0), "DEPOIS"),
    ]
    _gravar(tmp_path, trades)

    catalogo = Catalogo(tmp_path)
    catalogo.escanear()
    entrada, ts_inicio, ts_fim = catalogo.consultar_intervalo(
        _SYMBOL, dia, hora_inicio=time(9, 0), hora_fim=time(10, 0)
    )
    assert entrada is not None

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    leitor = AdaptadorLeitorGravacao(
        barramento, entrada, ts_inicio_ns=ts_inicio, ts_fim_ns=ts_fim,
        catalogo=catalogo, verificar_hash=True,
    )
    leitor.iniciar()

    ids = {t.trade_id for t in coletados}
    assert ids == {"DENTRO_1", "DENTRO_2", "DENTRO_BORDA"}
    assert "ANTES" not in ids
    assert "DEPOIS" not in ids


def test_leitor_sem_filtro_de_horario_devolve_tudo(tmp_path):
    """Contraste com o teste acima: confirma que o comportamento default
    (sem ts_inicio/ts_fim) é devolver tudo — para não confundir "sem
    filtro" com "filtro quebrado"."""
    dia = date(2026, 8, 20)
    trades = [
        _trade(_ts_utc(dia, 8, 0), "A"),
        _trade(_ts_utc(dia, 11, 0), "B"),
    ]
    _gravar(tmp_path, trades)

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]

    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    leitor = AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True)
    leitor.iniciar()

    assert {t.trade_id for t in coletados} == {"A", "B"}
