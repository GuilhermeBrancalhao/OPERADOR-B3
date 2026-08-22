"""Event bus síncrono e determinístico.

O núcleo é single-threaded por design: `publicar` chama os assinantes
inline, na mesma thread, na mesma ordem sempre. Concorrência (I/O de rede,
replay em tempo real, etc.) fica inteiramente nos adaptadores de borda em
`fluxopro.dados`, que traduzem para eventos e os entregam ao barramento de
forma serializada.

## As três políticas deste módulo, decididas aqui e presas por teste

A auditoria R5 (`criticas/nucleo_r5.md`, mutações `B01`/`B02`) mediu que o
comportamento do barramento diante de **reentrância** e de **exceção de
assinante** não estava decidido por teste nenhum — nas duas direções. Num
sistema single-threaded em que analytics, detectores, motor, saída **e o
gravador** compartilham a mesma publicação, essas duas não são detalhe de
implementação: são a política que decide se um erro de exibição mata a
gravação do pregão. Ficam declaradas:

**1. `publicar` entrega sobre um INSTANTÂNEO.** A lista de assinantes de cada
tipo é uma **tupla imutável**, trocada inteira por `assinar`/`desassinar`.
Consequência: quem assina (ou desassina) de dentro de um callback **não**
afeta a entrega do evento corrente — só a do próximo. Isso não custa nada no
caminho quente: `publicar` não copia nada, apenas itera a tupla que buscou;
a imutabilidade faz o instantâneo de graça. A alternativa (lista mutada
durante a iteração) não é "outra política", é ausência de política: o
assinante novo é visitado ou não conforme a posição em que a ordenação o
colocou em relação ao cursor do `for`.

**2. Exceção de assinante PROPAGA.** Não há `try/except` em `publicar`: um
assinante que levanta interrompe a cadeia e o erro sobe para quem publicou.
É a mesma escolha de "falha FECHADA" que `RelogioReplay` faz para
retrocesso e que `app/montagem.py` faz para recorte de horário: um erro
barato de detectar (a exceção aponta o assinante) é preferível a um estado
silenciosamente incompleto (metade da cadeia processou o evento, a outra
metade não, e nada registra que isso aconteceu). Quem quiser isolar um
consumidor cosmético — uma UI, um logger — envolve o **próprio callback** em
`try/except`, onde a decisão de engolir é local e visível.

**3. `desassinar` existe.** Sem ele, "trocar a instância de um componente que
assina a si mesmo no construtor" dobrava a contagem, e por isso
`SessaoFluxo` mantinha `FootprintPorTimeframe` numa lista de
`SEM_RESET_POSSIVEL` — o último componente a carregar o dia anterior na
virada de sessão (`criticas/nucleo_r5.md` §C.2 mediu 199 candles do dia 1
sobrevivendo ao dia 2). A ausência estava registrada desde a onda 6.

## Critério de crescimento aplicado a `_assinantes`

*"Qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão
continua?"* — `len(_assinantes)` é o número de **tipos de evento** (uma
constante do vocabulário) e `len(_assinantes[tipo])` é o número de
**assinaturas vivas**. Nenhum dos dois é função do número de eventos. O caso
que faria crescer com o tempo é a virada de sessão recriando componentes que
assinam a si mesmos — e é exatamente para isso que `desassinar` entrou:
`tests/test_barramento.py::test_virada_repetida_nao_faz_o_barramento_crescer`
prende o invariante.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable


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
        self._assinantes: dict[type, tuple[_Assinatura, ...]] = {}
        self._contador = itertools.count()

    def assinar(
        self, tipo: type, callback: Callable[[Any], None], prioridade: int = 0
    ) -> None:
        assinatura = _Assinatura(
            prioridade=prioridade, ordem=next(self._contador), callback=callback
        )
        atuais = self._assinantes.get(tipo, ())
        self._assinantes[tipo] = tuple(
            sorted(atuais + (assinatura,), key=lambda a: (a.prioridade, a.ordem))
        )

    def desassinar(self, tipo: type, callback: Callable[[Any], None]) -> bool:
        """Remove a assinatura de `callback` para `tipo`. `True` se removeu.

        Comparação por **igualdade**, não por identidade: `obj.metodo` cria um
        objeto de método ligado novo a cada acesso, e dois deles do mesmo par
        (instância, função) são `==` mas não `is`. Comparar por `is` faria
        `desassinar(Trade, componente.ao_trade)` falhar em silêncio — o modo
        de falha exato que este método existe para eliminar.
        """
        atuais = self._assinantes.get(tipo)
        if not atuais:
            return False
        restantes = tuple(a for a in atuais if a.callback != callback)
        if len(restantes) == len(atuais):
            return False
        self._assinantes[tipo] = restantes
        return True

    def desassinar_objeto(self, dono: object) -> int:
        """Remove TODA assinatura cujo callback é método ligado de `dono`.

        É a operação que "trocar a instância de um componente" precisa: quem
        recria um componente não conhece (nem deveria conhecer) os nomes dos
        métodos privados que ele registrou no construtor. Devolve quantas
        assinaturas saíram — 0 é resposta legítima e o chamador que exige
        remoção deve conferir.
        """
        removidas = 0
        for tipo, atuais in list(self._assinantes.items()):
            restantes = tuple(
                a for a in atuais if getattr(a.callback, "__self__", None) is not dono
            )
            if len(restantes) != len(atuais):
                removidas += len(atuais) - len(restantes)
                self._assinantes[tipo] = restantes
        return removidas

    def publicar(self, evento: Any) -> None:
        for assinatura in self._assinantes.get(type(evento), ()):
            assinatura.callback(evento)
