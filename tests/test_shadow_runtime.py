from __future__ import annotations

import gzip
import json
import threading
import time
from pathlib import Path

from fluxopro.app.shadow_runtime import AsyncShadowWriter, ShadowRuntimeState
from fluxopro.core.eventos import Side
from fluxopro.shadow import AmostraFeatures, ConfigShadow, SidecarShadow


def _sample(ts: int, *, price: int = 100) -> AmostraFeatures:
    return AmostraFeatures(
        timestamp_ns=ts,
        symbol="WDOQ26",
        price_ticks=price,
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


def test_reset_espera_ack_quando_fila_esta_cheia_e_censura_sessao_anterior(
    tmp_path: Path, monkeypatch
) -> None:
    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(intervalo_amostra_ns=100_000_000_000, horizontes_s=(1,)),
    )
    entrou_no_writer = threading.Event()
    liberar_writer = threading.Event()
    original = sidecar.observar

    def bloquear(sample):
        entrou_no_writer.set()
        assert liberar_writer.wait(2)
        return original(sample)

    monkeypatch.setattr(sidecar, "observar", bloquear)
    writer = AsyncShadowWriter(sidecar, capacity=1)
    assert writer.submit(_sample(1))
    assert entrou_no_writer.wait(1)
    assert writer.submit(_sample(500_000_000))

    resultado: list[bool] = []
    reset = threading.Thread(target=lambda: resultado.append(writer.reset_session("WDOQ26")))
    reset.start()
    time.sleep(0.05)
    assert reset.is_alive(), "reset deve aguardar vaga/ack; nao pode ser descartado"

    liberar_writer.set()
    reset.join(2)
    assert resultado == [True]
    assert writer.submit(_sample(1_000_000_001, price=110))
    writer.close()

    arquivos = list(tmp_path.rglob("labels.jsonl.gz"))
    assert len(arquivos) == 1
    with gzip.open(arquivos[0], "rt", encoding="utf-8") as stream:
        labels = [json.loads(linha) for linha in stream if linha.strip()]
    anterior = [label for label in labels if label["price_inicial_ticks"] == 100]
    assert len(anterior) == 1
    assert anterior[0]["qualidade"] == "CENSURADA"
    assert anterior[0]["price_final_ticks"] == 100


def test_close_drena_fila_cheia_e_finaliza_apos_escrita_bloqueada(
    tmp_path: Path, monkeypatch,
) -> None:
    """O encerramento nao depende de inserir sentinela em fila cheia."""

    sidecar = SidecarShadow(
        tmp_path,
        ConfigShadow(
            intervalo_amostra_ns=1,
            horizontes_s=(1,),
            max_pendentes_por_simbolo=4,
            max_registros_buffer=8,
        ),
    )
    entrou = threading.Event()
    liberar = threading.Event()
    observar_original = sidecar.observar

    def observar_bloqueado(amostra):
        entrou.set()
        assert liberar.wait(2)
        observar_original(amostra)

    monkeypatch.setattr(sidecar, "observar", observar_bloqueado)
    writer = AsyncShadowWriter(sidecar, capacity=1)
    assert writer.submit(_sample(1_000_000_000))
    assert entrou.wait(1)
    assert writer.submit(_sample(2_000_000_000))

    # A primeira espera expira enquanto o worker esta bloqueado, mas a
    # solicitacao de close permanece instalada e nao perde a finalizacao.
    assert writer.close(timeout_s=0.01).state is ShadowRuntimeState.ERROR
    liberar.set()
    estado = writer.close(timeout_s=2.0)

    assert estado.state is ShadowRuntimeState.CLOSED
    assert not writer._thread.is_alive()
    assert len(list(tmp_path.rglob("run.json"))) == 1
