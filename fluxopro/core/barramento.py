"""Event bus síncrono e determinístico.

O núcleo é single-threaded por design: `publicar` chama os assinantes
inline, na mesma thread, na mesma ordem sempre. Concorrência (I/O de rede,
replay em tempo real, etc.) fica inteiramente nos adaptadores de borda em
`fluxopro.dados`, que traduzem para eventos e os entregam ao barramento de
forma serializada.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, DefaultDict


@dataclass(slots=True)
class _Assinatura:
    prioridade: int
    ordem: int
    callback: Callable[[Any], None]


class Barramento:
    """Distribui eventos por tipo exato aos assinantes registrados.

    Ordem de entrega: menor `prioridade` primeiro; empate resolvido pela
    ordem de inscrição (`assinar` chamado antes entrega antes). A ordenação
    acontece em `assinar` (custo de setup), deixando `publicar` — o caminho
    quente, chamado por tick — como uma simples iteração sem alocação.
    """

    def __init__(self) -> None:
        self._assinantes: DefaultDict[type, list[_Assinatura]] = defaultdict(list)
        self._contador = itertools.count()

    def assinar(
        self, tipo: type, callback: Callable[[Any], None], prioridade: int = 0
    ) -> None:
        assinatura = _Assinatura(
            prioridade=prioridade, ordem=next(self._contador), callback=callback
        )
        lista = self._assinantes[tipo]
        lista.append(assinatura)
        lista.sort(key=lambda a: (a.prioridade, a.ordem))

    def publicar(self, evento: Any) -> None:
        for assinatura in self._assinantes.get(type(evento), ()):
            assinatura.callback(evento)
