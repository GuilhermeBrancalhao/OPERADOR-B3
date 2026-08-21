"""Testes de `RelogioReplay` — política de retrocesso (defeito M09/R2).

A política decidida (ver docstring de `fluxopro/core/relogio.py`) é
RECUSAR explicitamente um avanço para um timestamp menor que o atual,
levantando `ValueError`, porque as janelas deslizantes a jusante (deques
por `timestamp_ns` do `DetectorAbsorcao`, do `MotorSinais` etc.) assumem
tempo monotônico — aceitar retroceder corrompe a janela sem deixar rastro.
"""

from __future__ import annotations

import pytest

from fluxopro.core.relogio import RelogioReal, RelogioReplay


def test_relogio_replay_comeca_no_valor_de_inicio():
    relogio = RelogioReplay(inicio_ns=1_000)
    assert relogio.agora_ns() == 1_000


def test_relogio_replay_avanca_para_frente():
    relogio = RelogioReplay(inicio_ns=1_000)
    relogio.avancar_para(2_000)
    assert relogio.agora_ns() == 2_000
    relogio.avancar_para(5_000)
    assert relogio.agora_ns() == 5_000


def test_relogio_replay_aceita_ficar_parado_no_mesmo_timestamp():
    """Vários eventos podem compartilhar o mesmo timestamp_ns (mesmo
    nanossegundo) — isso não é retrocesso e não deve ser recusado."""
    relogio = RelogioReplay(inicio_ns=3_000)
    relogio.avancar_para(3_000)
    assert relogio.agora_ns() == 3_000


def test_relogio_replay_recusa_retroceder():
    relogio = RelogioReplay(inicio_ns=10_000)
    with pytest.raises(ValueError, match="retroceder"):
        relogio.avancar_para(9_999)
    # e o estado NAO deve ter mudado com a tentativa recusada
    assert relogio.agora_ns() == 10_000


def test_relogio_replay_recusa_retroceder_apos_avancos_normais():
    relogio = RelogioReplay(inicio_ns=0)
    relogio.avancar_para(100)
    relogio.avancar_para(200)
    with pytest.raises(ValueError):
        relogio.avancar_para(150)
    # avanco recusado nao deve ter corrompido o relogio: continua em 200
    assert relogio.agora_ns() == 200
    # e o relogio continua utilizavel para avancos validos depois da recusa
    relogio.avancar_para(300)
    assert relogio.agora_ns() == 300


def test_relogio_real_usa_monotonic_ns():
    relogio = RelogioReal()
    t1 = relogio.agora_ns()
    t2 = relogio.agora_ns()
    assert isinstance(t1, int)
    assert t2 >= t1
