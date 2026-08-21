"""Abstração de tempo do núcleo.

Nada dentro de `fluxopro.core` chama `time.time()`/`time.monotonic_ns()`
diretamente — todo consumo de tempo passa por um `Relogio`, para que o
mesmo código rode tanto sobre dados de replay (tempo determinístico, definido
pelo timestamp dos próprios eventos) quanto sobre dados ao vivo (tempo real).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class Relogio(ABC):
    @abstractmethod
    def agora_ns(self) -> int: ...


class RelogioReal(Relogio):
    """Tempo de parede monotônico, para operação ao vivo."""

    def agora_ns(self) -> int:
        return time.monotonic_ns()


class RelogioReplay(Relogio):
    """Tempo determinístico que só avança quando mandado — pelo timestamp
    do evento sendo processado, nunca pelo relógio da máquina.
    """

    def __init__(self, inicio_ns: int = 0) -> None:
        self._atual_ns = inicio_ns

    def agora_ns(self) -> int:
        return self._atual_ns

    def avancar_para(self, timestamp_ns: int) -> None:
        if timestamp_ns < self._atual_ns:
            raise ValueError("relogio de replay nao pode retroceder")
        self._atual_ns = timestamp_ns
