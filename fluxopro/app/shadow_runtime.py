"""Fronteira assíncrona entre o caminho de mercado e o sidecar shadow.

O barramento nunca executa I/O. Ele entrega snapshots imutáveis a uma fila
limitada; um único writer preserva a ordem causal e isola qualquer falha de
disco do pipeline consultivo.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from enum import StrEnum

from fluxopro.shadow import AmostraFeatures, BufferShadowCheio, SidecarShadow


class ShadowRuntimeState(StrEnum):
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ShadowRuntimeSnapshot:
    state: ShadowRuntimeState
    queue_size: int
    queue_capacity: int
    enqueued: int
    processed: int
    dropped_backpressure: int
    failures: int
    detail: str


@dataclass(frozen=True, slots=True)
class _ResetCommand:
    symbol: str
    ack: threading.Event
    resultado: list[Exception | None]


_STOP = object()


class AsyncShadowWriter:
    """Writer serial, limitado e fail-closed somente para o shadow."""

    def __init__(self, sidecar: SidecarShadow, *, capacity: int = 4_096) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity shadow deve ser inteiro positivo")
        self.sidecar = sidecar
        self._capacity = capacity
        self._queue: queue.Queue[AmostraFeatures | _ResetCommand | object] = (
            queue.Queue(maxsize=capacity)
        )
        self._lock = threading.Lock()
        self._state = ShadowRuntimeState.RUNNING
        self._enqueued = 0
        self._processed = 0
        self._dropped = 0
        self._failures = 0
        self._detail = "writer shadow ativo"
        self._disabled = False
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="operador-b3-shadow-writer",
            daemon=True,
        )
        self._thread.start()

    def submit(self, sample: AmostraFeatures) -> bool:
        return self._enqueue(sample)

    def reset_session(self, symbol: str, *, timeout_s: float = 15.0) -> bool:
        """Entrega a virada em ordem e só retorna após o reset causal.

        Amostras podem ser descartadas quando a fila está cheia, mas a virada
        não pode: perder esse comando permitiria que um label usasse o pregão
        seguinte como futuro. A espera é pelo writer, nunca por I/O no
        barramento. Se o writer não confirmar no prazo, o shadow é desligado
        de forma explícita; amostras posteriores passam a ser recusadas.
        """
        if timeout_s <= 0:
            raise ValueError("timeout_s deve ser positivo")
        comando = _ResetCommand(symbol, threading.Event(), [None])
        with self._lock:
            indisponivel = self._closed or self._disabled
        if indisponivel:
            self._disable_after_reset_failure("writer shadow indisponivel")
            return False
        try:
            self._queue.put(comando, timeout=timeout_s)
        except queue.Full:
            self._disable_after_reset_failure(
                "reset de sessao sem confirmacao: fila shadow cheia"
            )
            return False
        if not comando.ack.wait(timeout_s):
            self._disable_after_reset_failure(
                "reset de sessao sem confirmacao do writer"
            )
            return False
        if comando.resultado[0] is not None:
            return False
        return True

    def _enqueue(self, item: AmostraFeatures | _ResetCommand) -> bool:
        with self._lock:
            if self._closed or self._disabled:
                self._dropped += 1
                return False
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._lock:
                self._dropped += 1
                self._state = ShadowRuntimeState.DEGRADED
                self._detail = "fila shadow cheia; amostra descartada"
            return False
        with self._lock:
            self._enqueued += 1
        return True

    def snapshot(self) -> ShadowRuntimeSnapshot:
        with self._lock:
            return ShadowRuntimeSnapshot(
                state=self._state,
                queue_size=self._queue.qsize(),
                queue_capacity=self._capacity,
                enqueued=self._enqueued,
                processed=self._processed,
                dropped_backpressure=self._dropped,
                failures=self._failures,
                detail=self._detail,
            )

    def close(self, *, timeout_s: float = 15.0) -> ShadowRuntimeSnapshot:
        if timeout_s <= 0:
            raise ValueError("timeout_s deve ser positivo")
        with self._lock:
            already_closed = self._closed
            self._closed = True
        if already_closed:
            return self.snapshot()
        try:
            self._queue.put(_STOP, timeout=timeout_s / 2)
        except queue.Full:
            with self._lock:
                self._state = ShadowRuntimeState.ERROR
                self._failures += 1
                self._detail = "timeout ao encerrar fila shadow"
            return self.snapshot()
        self._thread.join(timeout=timeout_s / 2)
        if self._thread.is_alive():
            with self._lock:
                self._state = ShadowRuntimeState.ERROR
                self._failures += 1
                self._detail = "writer shadow nao encerrou no prazo"
        return self.snapshot()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                try:
                    if not self._disabled:
                        self.sidecar.finalizar()
                except Exception as exc:
                    self._record_failure(exc)
                else:
                    with self._lock:
                        if self._state is not ShadowRuntimeState.ERROR:
                            self._state = ShadowRuntimeState.CLOSED
                            self._detail = "writer shadow encerrado"
                finally:
                    self._queue.task_done()
                return
            try:
                if isinstance(item, _ResetCommand):
                    self._process_reset(item)
                else:
                    assert isinstance(item, AmostraFeatures)
                    if self._disabled:
                        with self._lock:
                            self._dropped += 1
                        continue
                    self._with_backpressure(lambda: self.sidecar.observar(item))
                with self._lock:
                    self._processed += 1
            except Exception as exc:  # fronteira de isolamento operacional
                self._record_failure(exc)
            finally:
                self._queue.task_done()

    def _process_reset(self, comando: _ResetCommand) -> None:
        try:
            with self._lock:
                indisponivel = self._disabled
            if indisponivel:
                raise RuntimeError("writer shadow indisponivel para reset")
            self._with_backpressure(lambda: self.sidecar.resetar_sessao(comando.symbol))
        except Exception as exc:
            comando.resultado[0] = exc
            self._record_failure(exc)
        finally:
            comando.ack.set()

    def _with_backpressure(self, operation) -> None:
        try:
            operation()
        except BufferShadowCheio:
            self.sidecar.flush()
            operation()

    def _record_failure(self, exc: Exception) -> None:
        with self._lock:
            self._disabled = True
            self._state = ShadowRuntimeState.ERROR
            self._failures += 1
            self._detail = f"{type(exc).__name__}: {exc}"

    def _disable_after_reset_failure(self, detail: str) -> None:
        """Degradação auditável quando a barreira de virada não fecha."""
        with self._lock:
            if self._disabled:
                return
            self._disabled = True
            self._state = ShadowRuntimeState.ERROR
            self._failures += 1
            self._detail = detail


__all__ = [
    "AsyncShadowWriter",
    "ShadowRuntimeSnapshot",
    "ShadowRuntimeState",
]
