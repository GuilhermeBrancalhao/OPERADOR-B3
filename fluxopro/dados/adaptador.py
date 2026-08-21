"""Interface comum para toda fonte de eventos de mercado."""

from __future__ import annotations

from abc import ABC, abstractmethod

from fluxopro.core.barramento import Barramento


class AdaptadorDados(ABC):
    """Traduz uma fonte externa (arquivo, gerador sintético, feed ao vivo)
    em eventos publicados no `Barramento`. Concorrência e I/O ficam aqui —
    nunca dentro de `fluxopro.core`.
    """

    def __init__(self, barramento: Barramento) -> None:
        self._barramento = barramento

    @abstractmethod
    def iniciar(self) -> None: ...

    @abstractmethod
    def parar(self) -> None: ...
