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

    Política de retrocesso (decidida e fixada aqui): **recusar
    explicitamente**, levantando `ValueError`, em vez de ignorar
    silenciosamente ou só registrar um aviso.

    Por quê: as janelas deslizantes a jusante (deques do `DetectorAbsorcao`,
    do `MotorSinais` etc.) assumem tempo monotônico para podar por
    `timestamp_ns` — se o relógio aceitasse retroceder, um evento fora de
    ordem faria a poda de janela reconsiderar como "recente" um trade que já
    devia ter expirado (ou expirar um que não devia), corrompendo o estado
    da janela sem deixar rastro. É um estado incorreto que não se autocorrige
    sozinho: cada avanço subsequente herda a corrupção.

    Dado fora de ordem existe (rede, buffer, replay editado à mão), mas
    resolver isso é responsabilidade de quem alimenta o relógio — reordenar
    ou descartar ANTES de chamar `avancar_para` — não do relógio aceitar e
    mentir que o tempo é monotônico quando não é. Silenciar aqui trocaria um
    erro de dados barato de detectar (a exceção aponta o evento e o ponto
    exato) por uma corrupção de estado caro de detectar (só aparece como
    sinal errado rio abaixo, sem relação óbvia com a causa).
    """

    def __init__(self, inicio_ns: int = 0) -> None:
        self._atual_ns = inicio_ns

    def agora_ns(self) -> int:
        return self._atual_ns

    def avancar_para(self, timestamp_ns: int) -> None:
        """Avança o relógio para `timestamp_ns`. Aceita ficar parado (mesmo
        valor do atual — comum quando vários eventos compartilham o mesmo
        `timestamp_ns`), mas recusa qualquer valor menor que o atual."""
        if timestamp_ns < self._atual_ns:
            raise ValueError(
                f"relogio de replay nao pode retroceder: atual={self._atual_ns} "
                f"proposto={timestamp_ns}"
            )
        self._atual_ns = timestamp_ns
