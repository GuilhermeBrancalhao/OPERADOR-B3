"""Sintese de voz do Sinal Ultra — NOVO (26/08/2026), 100% offline.

Pedido do operador (MUDANCAS E IMPLEMENTACOES.docx): "deve ser um robo
moderno, e com alta arquitetura deve falar com voz audivel o que o sinal
acima reproduz" — referindo-se ao Sinal Ultra (fluxopro/asg/sinal_ultra.py,
construido do zero na Fase 1, sem regra na fonte original).

Nao existia NENHUMA sintese de voz no projeto antes disso (varredura da
Fase 1 nao achou pyttsx3/gTTS/azure/winsound em lugar nenhum). Este modulo e
o motor: local, via SAPI5 do Windows (`pyttsx3`), sem enviar audio nem texto
para servico externo — coerente com o resto do projeto, que nunca faz
chamada de rede de terceiros no caminho de leitura de mercado.

## Threading

`engine.say()+runAndWait()` do pyttsx3 BLOQUEIA a thread ate a fala
terminar (2-5s tipico). Chamar isso na thread do Qt congelaria a janela
inteira a cada anuncio — mesmo motivo pelo qual a fonte de dados do painel
ja roda em thread propria (ver docstring de `scripts/painel.py`). Por isso
`LocutorASG` roda um worker dedicado consumindo uma fila; `falar()` so
enfileira e volta na hora.

O driver SAPI5 usa COM (`pythoncom`), que exige inicializacao POR THREAD —
por isso o motor pyttsx3 e criado DENTRO do worker, nunca no construtor
(que roda na thread de quem instancia `LocutorASG`, normalmente a UI).

## Nunca implicito, nunca trava o painel se faltar

`ConfigVoz.ativo` comeca `False` por padrao: subir um thread de audio (e
potencialmente falar alto) como efeito colateral de simplesmente montar um
widget seria uma automacao implicita — o mesmo principio ja aplicado em
outros projetos deste operador ("criar estrutura no Omie NUNCA e
implicito"). O operador liga explicitamente via `FLUXOPRO_VOZ=1` no
ambiente antes de abrir o painel (ver `fluxopro/ui/paineis/asg.py`).

Se `pyttsx3`/SAPI5 nao estiverem disponiveis (falta a lib, maquina sem
nenhuma voz instalada, outro SO), o worker marca `disponivel=False` e
`falar()` vira no-op silencioso — nunca derruba o painel por causa de
audio.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from fluxopro.asg.sinal_ultra import DirecaoUltra

__all__ = [
    "ConfigVoz",
    "LocutorASG",
    "texto_para_transicao_ultra",
]


@dataclass(frozen=True, slots=True)
class ConfigVoz:
    ativo: bool = False
    """Comeca desligado de proposito — ver docstring do modulo."""

    voz_id: str | None = None
    """Id da voz SAPI5 (ver `pyttsx3.init().getProperty('voices')`). `None`
    usa a voz padrao do Windows — em maquinas com "Microsoft Maria" (pt-BR)
    instalada, geralmente ja e essa."""

    volume: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError("volume deve estar entre 0 e 1")


def texto_para_transicao_ultra(anterior: DirecaoUltra, nova: DirecaoUltra) -> str | None:
    """O que anunciar quando o Sinal Ultra muda de estado, ou `None` se nao
    ha nada a dizer desta vez (mesma direcao, ou nunca esteve ligado).

    Funcao pura — nenhum acesso a fila/thread/motor de voz aqui, so a regra
    de QUANDO falar e O QUE falar. Testada sem tocar em audio nenhum.
    """

    if anterior is nova:
        return None
    if nova in (DirecaoUltra.COMPRA, DirecaoUltra.VENDA):
        lado = "compra" if nova is DirecaoUltra.COMPRA else "venda"
        fluxo = "comprador" if nova is DirecaoUltra.COMPRA else "vendedor"
        # O texto falado espelha o que a regiao OPERADOR IA mostra na tela
        # (fluxopro/ui/paineis/nexo/vies.py): quais portoes concordaram e o
        # que observar. Leitura, nunca conselho de execucao — nenhuma frase
        # daqui pode citar entrada, alvo, stop, tamanho ou momento de operar.
        return (
            f"Sinal Ultra de {lado} armado. As tres fontes concordam: "
            f"decisao de {lado}, Renko em tendencia e fluxo {fluxo} forte "
            "no maker proxy. Observe se o Renko perde a tendencia ou a forca "
            "do maker cruza o limiar. Leitura consultiva, nao e ordem."
        )
    if anterior is not DirecaoUltra.NENHUMA and nova is DirecaoUltra.NENHUMA:
        lado = "compra" if anterior is DirecaoUltra.COMPRA else "venda"
        return (
            f"Sinal Ultra de {lado} encerrado. A confluencia se desfez; "
            "o painel voltou a leitura sem sinal."
        )
    return None


_ITEM_ENCERRAR = object()


class LocutorASG:
    """Locutor com worker proprio. Seguro de instanciar mesmo com
    ``config.ativo=False`` ou sem pyttsx3 instalado — nesses casos nenhuma
    thread e criada e ``falar()``/``encerrar()`` sao no-op."""

    __slots__ = ("config", "_fila", "_thread", "_disponivel")

    def __init__(self, config: ConfigVoz | None = None) -> None:
        self.config = config or ConfigVoz()
        self._fila: queue.Queue[str | object] = queue.Queue()
        self._disponivel = False
        self._thread: threading.Thread | None = None
        if self.config.ativo:
            self._disponivel = True
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name="LocutorASG"
            )
            self._thread.start()

    def falar(self, texto: str | None) -> None:
        if texto is None or not self._disponivel:
            return
        self._fila.put(texto)

    def encerrar(self) -> None:
        if not self._disponivel or self._thread is None:
            return
        self._fila.put(_ITEM_ENCERRAR)
        self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        pythoncom = None
        try:
            import pythoncom as _pythoncom

            pythoncom = _pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass

        try:
            try:
                import pyttsx3

                motor = pyttsx3.init()
            except Exception:
                # Sem lib, sem driver SAPI5, ou sem NENHUMA voz instalada —
                # degrada em silencio, nunca propaga pro chamador (que ja
                # seguiu em frente, `falar()` nao espera resposta nenhuma).
                self._disponivel = False
                return

            if self.config.voz_id:
                try:
                    motor.setProperty("voice", self.config.voz_id)
                except Exception:
                    pass
            try:
                motor.setProperty("volume", self.config.volume)
            except Exception:
                pass

            while True:
                item = self._fila.get()
                if item is _ITEM_ENCERRAR:
                    break
                try:
                    motor.say(item)
                    motor.runAndWait()
                except Exception:
                    # Um anuncio falhar (driver caiu no meio do pregao, por
                    # exemplo) nao pode matar o worker pro resto do dia —
                    # so este item se perde, o proximo ainda tenta.
                    continue
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
