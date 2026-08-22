"""Testes de `RelogioReplay` — política de retrocesso (defeito M09/R2).

A política decidida (ver docstring de `fluxopro/core/relogio.py`) é
RECUSAR explicitamente um avanço para um timestamp menor que o atual,
levantando `ValueError`, porque as janelas deslizantes a jusante (deques
por `timestamp_ns` do `DetectorAbsorcao`, do `MotorSinais` etc.) assumem
tempo monotônico — aceitar retroceder corrompe a janela sem deixar rastro.
"""

from __future__ import annotations

import time

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


# ---------------------------------------------------------------------------
# `RelogioReal` — o irmão AO VIVO, que é quem de fato roda em produção
#
# `criticas/nucleo_r5.md` RL1: trocar `time.monotonic_ns()` por
# `time.time_ns()` em `RelogioReal` deixava os 574 testes verdes. O módulo
# inteiro existe para que nada no núcleo leia o relógio da máquina, e
# `RelogioReplay` tem 20 linhas de docstring justificando por que retroceder
# é inaceitável — com teste. O irmão ao vivo não tinha o equivalente.
#
# O teste não olha o nome da função chamada (isso prenderia a implementação,
# não a semântica): ele SABOTA o relógio de parede e exige que `RelogioReal`
# não se abale. Um relógio de parede regride de verdade — ajuste de NTP,
# horário de verão, o operador acertando o Windows no meio do pregão — e a
# consequência é a mesma que `RelogioReplay` recusa: janela deslizante
# reconsiderando como "recente" o que já expirou.
# ---------------------------------------------------------------------------


def test_relogio_real_nao_regride_quando_o_relogio_de_PAREDE_regride(monkeypatch):
    parede = [10**18]

    def time_ns_que_anda_para_tras() -> int:
        parede[0] -= 10**9  # cada leitura volta 1 segundo
        return parede[0]

    monkeypatch.setattr(time, "time_ns", time_ns_que_anda_para_tras)

    relogio = RelogioReal()
    leituras = [relogio.agora_ns() for _ in range(5)]

    assert leituras == sorted(leituras), (
        "RelogioReal regrediu junto com o relogio de parede — ele esta lendo "
        "time_ns()/time(), nao um relogio monotonico"
    )


def test_relogio_real_nao_devolve_o_valor_do_relogio_de_parede(monkeypatch):
    """A outra metade: não basta ser monotônico, tem de não SER a parede.

    Um relógio de parede congelado é monotônico (todas as leituras iguais) e
    passaria no teste acima. Aqui a parede devolve uma sentinela fixa e
    absurda; se `RelogioReal` a repetir, ele é a parede.
    """
    sentinela = 424_242_424_242
    monkeypatch.setattr(time, "time_ns", lambda: sentinela)

    relogio = RelogioReal()
    assert relogio.agora_ns() != sentinela


def test_relogio_real_avanca_de_verdade(monkeypatch):
    """E não é um contador parado: entre duas leituras separadas por um
    `sleep` real, o valor tem de ter crescido."""
    relogio = RelogioReal()
    t1 = relogio.agora_ns()
    time.sleep(0.005)
    t2 = relogio.agora_ns()
    assert t2 > t1
