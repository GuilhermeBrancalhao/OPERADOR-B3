from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fluxopro.app.config import ConfigOperacao, FonteDados  # noqa: E402
from fluxopro.app.sessao_fluxo import SessaoFluxo  # noqa: E402
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import (  # noqa: E402
    AgressorSide,
    BookLevel,
    BookSnapshot,
    Trade,
)
from fluxopro.ui.janela import JanelaFluxo  # noqa: E402
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402


SYMBOL = "WDOV26"
T0 = 1_777_200_000_000_000_000
PRICE = 10_000
EVIDENCE = ROOT / ".gauntlet" / "2026-08-24a" / "r6" / "evidence"


def publicar(bus: Barramento) -> None:
    bus.publicar(
        BookSnapshot(
            T0,
            SYMBOL,
            tuple(BookLevel(PRICE - i, 100 + i * 20, i + 1) for i in range(1, 9)),
            tuple(BookLevel(PRICE + i, 110 + i * 18, i + 1) for i in range(1, 9)),
        )
    )
    for indice in range(12):
        bus.publicar(
            Trade(
                T0 + indice,
                SYMBOL,
                PRICE + (indice % 3) - 1,
                10 + indice,
                AgressorSide.BUY if indice % 2 else AgressorSide.SELL,
                f"r6-key-{indice}",
            )
        )


def tecla(window: JanelaFluxo, digito: int) -> None:
    QTest.keyClick(
        window,
        getattr(Qt.Key, f"Key_{digito}"),
        Qt.KeyboardModifier.ControlModifier,
    )


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    bus = Barramento()
    config = ConfigOperacao(
        symbol=SYMBOL,
        fonte=FonteDados.SIMULADOR,
        ligar_analytics=False,
        ligar_microestrutura=False,
        ligar_detectores_tape=False,
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
        ligar_leitura_asg=True,
    )
    sessao = SessaoFluxo(bus, config)
    assert sessao.feed_monitor is not None
    sessao.feed_monitor.connected("probe controlado R6")
    window = JanelaFluxo(
        PonteFluxo(bus), SYMBOL, config.price_grid(),
        sessao=sessao, config=config, persistir=False,
    )
    try:
        window.resize(1280, 720)
        window.show()
        QTest.qWaitForWindowExposed(window, 2_000)
        app.processEvents()
        publicar(bus)
        window._tick()
        window._relogio.stop()
        antes = window.asg._snapshot
        assert antes is not None and antes.timestamp_ns == 0

        tecla(window, 5)
        imediato = window.asg._snapshot
        assert imediato is not None and imediato.timestamp_ns == T0
        assert window._area_operacional.currentWidget() is window.asg
        assert window.asg.dom._ultimo_preco == PRICE + 1
        assert len(window.asg.tape._linhas) == 12
        app.processEvents()
        imagem = EVIDENCE / "keyboard_ctrl5_immediate_r6.png"
        window.grab().save(str(imagem))
        rotulos_faltantes = sorted(
            {"MACRO", "MICRO", "LINHA AZUL", "REGIME", "MAKERPROXY", "VELOCIMETRO"}
            - set(window.asg.matriz.textos_visiveis())
        )
        decisao_visivel = window.asg.decisao.isVisible()
        sem_ordens = "CONSULTIVO · SEM ENVIO DE ORDENS" in (
            window.asg.decisao.textos_visiveis()
        )

        tamanho = [window.width(), window.height()]
        historicos = []
        for digito, nome in ((1, "Fluxo"), (2, "Book & Tape"), (3, "Bookmap"), (4, "Revisão")):
            tecla(window, digito)
            app.processEvents()
            historicos.append(
                {
                    "shortcut": f"Ctrl+{digito}",
                    "workspace": window.workspace.nome,
                    "expected": nome,
                    "size": [window.width(), window.height()],
                    "visible_docks": sorted(
                        chave for chave, doca in window.docas.items() if doca.isVisible()
                    ),
                }
            )
            assert window.workspace.nome == nome
            assert [window.width(), window.height()] == tamanho

        report = {
            "platform": app.platformName(),
            "timer_stopped_before_ctrl5": True,
            "snapshot_before_ctrl5": antes.timestamp_ns,
            "snapshot_immediate_ctrl5": imediato.timestamp_ns,
            "immediate_blank": False,
            "missing_matrix_labels": rotulos_faltantes,
            "decision_visible": decisao_visivel,
            "no_orders_banner": sem_ordens,
            "real_context": ["PainelDOM", "PainelTape", "PainelBookmap"],
            "window_size": tamanho,
            "historical_workspaces": historicos,
            "classification": "native_ui_keyboard_integration_not_external_e2e",
        }
        output = EVIDENCE / "keyboard_probe_r6.json"
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=True))
        return 0
    finally:
        window.close()
        sessao.finalizar(T0 + 11)
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
