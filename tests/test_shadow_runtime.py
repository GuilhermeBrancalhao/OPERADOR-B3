from __future__ import annotations

import time
from pathlib import Path

from fluxopro.app.shadow_runtime import AsyncShadowWriter, ShadowRuntimeState
from fluxopro.core.eventos import Side
from fluxopro.shadow import AmostraFeatures, ConfigShadow, SidecarShadow


def _sample(ts: int) -> AmostraFeatures:
    return AmostraFeatures(
        timestamp_ns=ts,
        symbol="WDOQ26",
        price_ticks=100,
        estado="NEUTRO",
        direcao=Side.BUY,
    )


def test_writer_tira_flush_da_thread_publicadora(tmp_path: Path, monkeypatch) -> None:
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(
            intervalo_amostra_ns=1,
            horizontes_s=(1,),
            max_pendentes_por_simbolo=1,
            max_registros_buffer=2,
        ),
    )
    original = sidecar.flush

    def lento(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(sidecar, "flush", lento)
    writer = AsyncShadowWriter(sidecar, capacity=8)
    inicio = time.perf_counter()
    assert writer.submit(_sample(1))
    assert writer.submit(_sample(2))
    publish_ms = (time.perf_counter() - inicio) * 1_000
    writer.close()
    assert publish_ms < 20


def test_falha_de_disco_fica_isolada_e_visivel(tmp_path: Path, monkeypatch) -> None:
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(
            intervalo_amostra_ns=1,
            horizontes_s=(1,),
            max_pendentes_por_simbolo=1,
            max_registros_buffer=2,
        ),
    )

    def falhar(*args, **kwargs):
        raise OSError("disco simulado")

    monkeypatch.setattr(sidecar, "flush", falhar)
    writer = AsyncShadowWriter(sidecar, capacity=8)
    assert writer.submit(_sample(1))
    assert writer.submit(_sample(2))
    deadline = time.time() + 2
    while writer.snapshot().failures == 0 and time.time() < deadline:
        time.sleep(0.01)
    status = writer.close()
    assert status.state is ShadowRuntimeState.ERROR
    assert status.failures == 1
    assert "OSError" in status.detail


def test_fila_limitada_descarta_sem_bloquear(tmp_path: Path, monkeypatch) -> None:
    sidecar = SidecarShadow(tmp_path)
    gate = __import__("threading").Event()
    original = sidecar.observar

    def bloquear(sample):
        gate.wait(1)
        return original(sample)

    monkeypatch.setattr(sidecar, "observar", bloquear)
    writer = AsyncShadowWriter(sidecar, capacity=1)
    assert writer.submit(_sample(1))
    deadline = time.time() + 1
    while writer.snapshot().queue_size and time.time() < deadline:
        time.sleep(0.005)
    assert writer.submit(_sample(2))
    assert not writer.submit(_sample(3))
    assert writer.snapshot().dropped_backpressure == 1
    gate.set()
    writer.close()
