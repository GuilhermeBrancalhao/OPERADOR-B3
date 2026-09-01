"""QA independente da janela REAL, sem feed externo, IA ou ordens.

    python -m scripts.auditar_nexo_ai
    python -m pytest tests/test_nexo_ai_integracao.py -q

As capturas sao QWidget.grab() da JanelaFluxo montada por scripts.painel.
Offscreen e o backend padrao: exercita os widgets reais, mas NAO comprova
composicao do desktop, DPI de monitor ou E2E de corretora. Artefatos novos
ficam numa pasta exclusiva; nenhum resultado anterior e sobrescrito.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import __version__ as QT_BINDING_VERSION
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from fluxopro.core.eventos import AgressorSide, BookLevel, BookSnapshot, Trade
from fluxopro.ui.paineis import nexo
from fluxopro.ui.paineis.asg import EstadoASG
from fluxopro.ui.paineis.nexo import assistente
from scripts.painel import montar_cenario_controlado_asg

S = 1_000_000_000
ROTULO = "CENARIO CONTROLADO NAO E2E - NAO E PREGAO"
RESOLUCOES = ((1280, 720), (1480, 900), (1920, 1080))
ESTADOS = (EstadoASG.AO_VIVO, EstadoASG.REPLAY, EstadoASG.ATRASADO,
           EstadoASG.SEM_BOOK, EstadoASG.ERRO)
FONTES = ("fluxopro/ui/paineis/asg.py", "fluxopro/ui/paineis/nexo/assistente.py",
          "fluxopro/ui/paineis/nexo/__init__.py", "fluxopro/ui/paineis/nexo/candles.py",
          "fluxopro/ui/paineis/nexo/contexto.py", "fluxopro/ui/paineis/nexo/estatistica.py",
          "fluxopro/ui/paineis/nexo/vies.py", "fluxopro/ui/paineis/nexo/nucleo.py",
          "fluxopro/ui/paineis/nexo/forca.py", "fluxopro/ui/assets/nexo_ai_reference.png",
          "scripts/painel.py", "scripts/auditar_nexo_ai.py", "tests/test_nexo_ai_integracao.py",
          "fluxopro/ui/paineis/nexo/contexto.py", "fluxopro/ui/paineis/nexo/estatistica.py",
          "tests/test_ui_nexo_contexto_placar_responsivos.py", "pyproject.toml")


def serializar(valor):
    if dataclasses.is_dataclass(valor):
        return {f.name: serializar(getattr(valor, f.name)) for f in dataclasses.fields(valor)}
    if isinstance(valor, Enum):
        return {"enum": type(valor).__name__, "name": valor.name, "value": valor.value}
    if isinstance(valor, dict):
        return {str(k): serializar(v) for k, v in valor.items()}
    if isinstance(valor, (tuple, list)):
        return [serializar(v) for v in valor]
    if isinstance(valor, QColor):
        return valor.name(QColor.NameFormat.HexArgb)
    if isinstance(valor, QRect):
        return list(valor.getRect())
    if isinstance(valor, float) and not math.isfinite(valor):
        return str(valor)
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    raise TypeError(f"Tipo sem serializacao auditavel: {type(valor).__name__}")


def hash_imagem(imagem):
    return hashlib.sha256(bytes(imagem.constBits())).hexdigest()


def hashes_fontes():
    return {nome: hashlib.sha256((ROOT / nome).read_bytes()).hexdigest()
            for nome in FONTES if (ROOT / nome).is_file()}


def parar_timers(janela):
    """Congela a sessao controlada para comparar o MESMO snapshot."""
    for timer in janela.findChildren(QTimer):
        timer.stop()


def fechar_cenario(janela, sessao):
    parar_timers(janela)
    sessao.finalizar(janela.asg.nexo._snapshot.timestamp_ns)
    janela.close()
    janela.deleteLater()
    QApplication.instance().processEvents()


def enriquecer_historia(janela, sessao, *, horas=6, passos=240, estado=EstadoASG.AO_VIVO):
    """Somente eventos sinteticos no bus; nunca injeta candles ou decisao UI.

    240 intervalos em seis horas, quatro negocios por intervalo: pavios e
    corpos nascem dos mesmos eventos que a sessao/ponte realmente recebem.
    O selo permanente da fabrica de cenarios continua na janela inteira.
    """
    if horas <= 0 or passos < 2:
        raise ValueError("Historia exige horas > 0 e ao menos dois passos")
    ts0 = janela.asg.nexo._snapshot.timestamp_ns + S
    passo_ns = int(horas * 3600 * S / (passos - 1))
    trades_antes = sessao.contadores.n_trades_bus
    books_antes = sessao.contadores.n_snapshots_bus
    for i in range(passos):
        ts = ts0 + i * passo_ns
        preco = 10_000 + round(65 * math.sin(i / 19) + 24 * math.sin(i / 5) + i / 4)
        if estado is not EstadoASG.SEM_BOOK:
            sessao.barramento.publicar(BookSnapshot(
                ts, janela.simbolo,
                tuple(BookLevel(preco - k - 1, 140 + (i + k) % 70, 3) for k in range(8)),
                tuple(BookLevel(preco + k + 1, 130 + (i * 3 + k) % 80, 3) for k in range(8))))
        for n, delta in enumerate((0, 6, -5, 2 if i % 2 else -2)):
            sessao.barramento.publicar(Trade(
                ts + n * 100_000_000, janela.simbolo, preco + delta,
                20 + (i * 7 + n * 13) % 80,
                AgressorSide.BUY if delta >= 0 else AgressorSide.SELL,
                f"QA-CONTROLADO-NAO-E2E-{estado.name}-{i}-{n}"))
        janela._tick()
    # A fabrica ja estabeleceu erro/atraso; reafirma apos a historia para
    # nao confundir recuperacao do monitor com o estado solicitado.
    if estado is EstadoASG.ERRO:
        sessao.feed_monitor.failed(ROTULO + " - falha declarada")
    elif estado is EstadoASG.ATRASADO:
        sessao.feed_monitor.disconnected(ROTULO + " - transporte atrasado")
    if estado in {EstadoASG.ERRO, EstadoASG.ATRASADO}:
        sessao.barramento.publicar(Trade(ts + S, janela.simbolo, preco, 1,
                                       AgressorSide.BUY, f"QA-{estado.name}-final"))
        janela._tick()
    return {"label": ROTULO, "origin": "deterministic_synthetic_domain_events",
            "injected_ui_snapshots": False, "start_ns": ts0,
            "end_ns": janela.asg.nexo._snapshot.timestamp_ns,
            "duration_hours_requested": horas, "steps": passos,
            "trades_added": sessao.contadores.n_trades_bus - trades_antes,
            "books_added": sessao.contadores.n_snapshots_bus - books_antes,
            "generator": "sin(i/19)*65 + sin(i/5)*24 + i/4; OHLC offsets 0,6,-5,+/-2"}


def quadro_painel(painel):
    return QRect(0, 0, painel.width(), max(1, painel.height() - nexo.ALTURA_RESSALVA))


def render_painel(painel):
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel._backing.toImage().copy()


def tecla_real(janela, painel, tecla):
    janela.activateWindow()
    painel.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.instance().processEvents()
    QTest.keyClick(painel, tecla)
    QApplication.instance().processEvents()


def identidade_dados(painel):
    """Identidades mais conteudo: F7 nao pode substituir agregador nem dados."""
    return {"snapshot_id": id(painel._snapshot),
            "snapshot": serializar(painel._snapshot),
            "aggregator_ids": [id(painel._candles_m15), id(painel._candles_15m), id(painel._renko)],
            "candles_5m": serializar(painel._candles_m15.candles_fechados),
            "current_5m": serializar(painel._candles_m15.candle_atual),
            "candles_15m": serializar(painel._candles_15m.candles_fechados),
            "current_15m": serializar(painel._candles_15m.candle_atual),
            "renko": serializar(painel._renko.tijolos), "series": list(painel._serie),
            "ai_series": list(painel._serie_forca_ai),
            "viewport": [painel._timeframe_candles_min, painel._candles_offset,
                         painel._candles_velas_visiveis, painel._candles_zoom_preco]}


def estatisticas(amostras):
    ordenadas = sorted(amostras)
    return {"n": len(amostras), "unit": "ms", "p50": statistics.median(amostras),
            "p95": ordenadas[math.ceil(.95 * len(ordenadas)) - 1],
            "p95_method": "nearest_rank", "min": min(amostras), "max": max(amostras),
            "samples": amostras}


def diferenca_pixels(a, b):
    """Localiza diferenca no recorte sem gerar ou retocar imagens."""
    if a.size() != b.size():
        return {"same_size": False}
    aa, bb = bytes(a.constBits()), bytes(b.constBits())
    pontos = [(i // 4 % a.width(), i // 4 // a.width())
              for i in range(0, len(aa), 4) if aa[i:i+4] != bb[i:i+4]]
    return {"same_size": True, "changed_pixels": len(pontos),
            "bbox_in_crop": ([min(x for x, y in pontos), min(y for x, y in pontos),
                              max(x for x, y in pontos), max(y for x, y in pontos)] if pontos else None)}


def geometria_original():
    """Le baseline versionado sem executar codigo nem criar checkout."""
    path = "fluxopro/ui/paineis/nexo/__init__.py"
    proc = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", check=True)
    tree = ast.parse(proc.stdout)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "REGIOES":
            return ast.literal_eval(node.value), hashlib.sha256(proc.stdout.encode()).hexdigest()
    raise RuntimeError("REGIOES nao encontrada no HEAD; baseline NAO verificado")


def medir_geometria(painel, original):
    quadro = quadro_painel(painel)
    caixas = assistente.caixas_integradas(quadro)
    direitos = {}
    for nome in ("forca", "candles", "pressao"):
        x0, y0, x1, y1 = original[nome]
        esperado = QRect(quadro.left() + round(quadro.width() * x0),
                         quadro.top() + round(quadro.height() * y0),
                         round(quadro.width() * x1) - round(quadro.width() * x0),
                         round(quadro.height() * y1) - round(quadro.height() * y0))
        direitos[nome] = {"current": caixas[nome], "head_original": esperado,
                          "identical": caixas[nome] == esperado}
    internos = assistente.retangulos_internos(caixas["assistente"])
    return {"panel_rect": painel.rect(), "quadro": quadro, "regions": caixas,
            "ai_internal": internos, "right_charts": direitos,
            "core_height_fraction": internos["nucleo"].height() / caixas["assistente"].height(),
            "internal_containment": {k: caixas["assistente"].contains(v) for k, v in internos.items()},
            "visual_approval": "NOT_ASSESSED_BY_SCRIPT"}


def salvar_png(pixmap, destino):
    if not pixmap.save(str(destino), "PNG"):
        raise RuntimeError(f"PNG nao salvo: {destino}")
    return {"file": destino.name, "width": pixmap.width(), "height": pixmap.height(),
            "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}


def auditar_cenario(app, estado, tamanho, pasta, original, ambiente, preparado=None):
    largura, altura = tamanho
    janela, sessao, manifesto, historia = preparado
    janela.resize(largura, altura)
    app.processEvents()
    janela.asg.layout().activate()
    try:
        parar_timers(janela)
        app.processEvents()
        parar_timers(janela)
        # Resize invalida também os backing stores do cabeçalho/ressalva.
        # Seus timers estão parados deliberadamente: fechar TODOS os quadros
        # visíveis sem novo _tick, para não capturar faixas vazias nem drenar
        # novamente a ponte. É captura da janela, não só do painel central.
        for visivel in janela.paineis:
            if visivel.isVisible():
                visivel.marcar_tudo_sujo()
                visivel._quadro()
        painel = janela.asg.nexo
        if not painel._nexo_ai_ativo:
            raise RuntimeError("A captura inicial exige AI default; verifique FLUXOPRO_NEXO_AI")
        antes = identidade_dados(painel)
        nome = f"{estado.name.lower()}_{largura}x{altura}"
        # Aquecimento separado; todas as amostras seguintes forcam desenho.
        for _ in range(3):
            render_painel(painel)
        imagens, custos, custos_janela = [], [], []
        for _ in range(30):
            inicio = time.perf_counter_ns()
            img = render_painel(painel)
            custos.append((time.perf_counter_ns() - inicio) / 1e6)
            imagens.append(hash_imagem(img))
        for _ in range(30):
            inicio = time.perf_counter_ns()
            captura = janela.grab()
            custos_janela.append((time.perf_counter_ns() - inicio) / 1e6)
        screenshots = [salvar_png(captura, pasta / f"{nome}.png")]
        # Recorte nativo, sem upscale e sem qualquer geracao por IA.
        central = assistente.caixas_integradas(quadro_painel(painel))["assistente"]
        screenshots.append(salvar_png(painel.grab(central), pasta / f"{nome}_ai_crop.png"))
        leitura = painel._estado_nexo()
        dados = {"requested_state": estado.name, "actual_state": leitura.snapshot.estado_operacional.name,
                 "factory_manifest": manifesto,
                 "history": historia, "window_class": type(janela).__name__,
                 "window_size": [janela.width(), janela.height()],
                 "device_pixel_ratio": janela.devicePixelRatioF(),
                 "panel_origin_in_window": list(painel.mapTo(janela, QPoint(0, 0)).toTuple()),
                 "source_hashes_at_capture": hashes_fontes(),
                 "geometry": medir_geometria(painel, original),
                 "workspace_snapshot": leitura.snapshot,
                 "model_snapshot": assistente.compor(leitura),
                 "ultra_snapshot": leitura.sinal_ultra,
                 "chart_snapshot": {"candles": leitura.candles_m15, "renko": leitura.tijolos_renko,
                                    "series": leitura.serie, "ai_series": leitura.serie_forca_ai},
                 "render": {"panel_forced_with_image_copy": estatisticas(custos),
                            "window_grab_cached_panels": estatisticas(custos_janela),
                            "distinct_panel_pixel_hashes": sorted(set(imagens)),
                            "deterministic_30": len(set(imagens)) == 1,
                            "state_unchanged": antes == identidade_dados(painel),
                            "environment_label": ambiente,
                            "timing_includes": "Painel._quadro forcado + toImage().copy(); exclui hash PNG e I/O"},
                 "screenshots": screenshots}
        if painel._nexo_ai_ativo:  # A/B em todos os estados, mesmo snapshot e mesma janela
            ai_img = render_painel(painel)
            tecla_real(janela, painel, Qt.Key.Key_F7)
            classico_img = render_painel(painel)
            direitos = nexo.retangulos(quadro_painel(painel))
            dados["f7"] = {"classic_opened": not painel._nexo_ai_ativo,
                           "identity_and_data_preserved": antes == identidade_dados(painel),
                           "right_pixels_equal": {k: ai_img.copy(direitos[k]) == classico_img.copy(direitos[k])
                                                  for k in ("forca", "candles", "pressao")}}
            dados["f7"]["right_pixel_differences"] = {
                k: diferenca_pixels(ai_img.copy(direitos[k]), classico_img.copy(direitos[k]))
                for k in ("forca", "candles", "pressao")}
            screenshots.append(salvar_png(janela.grab(), pasta / f"{nome}_classico.png"))
            for _ in range(3):
                render_painel(painel)
            custos_classico, hashes_classico = [], []
            for _ in range(30):
                inicio = time.perf_counter_ns()
                img_classico = render_painel(painel)
                custos_classico.append((time.perf_counter_ns() - inicio) / 1e6)
                hashes_classico.append(hash_imagem(img_classico))
            stats_classico = estatisticas(custos_classico)
            dados["render"]["classic_forced_with_image_copy"] = stats_classico
            dados["render"]["classic_deterministic_30"] = len(set(hashes_classico)) == 1
            dados["render"]["ratio_ai_over_classic"] = {
                "p50": statistics.median(custos) / stats_classico["p50"],
                "p95": estatisticas(custos)["p95"] / stats_classico["p95"]}
            dados["render"]["ab_order"] = "AI then CLASSIC; 3 warmups + 30 forced each; same snapshot"
            dados["render"]["ab_state_unchanged"] = antes == identidade_dados(painel)
            tecla_real(janela, painel, Qt.Key.Key_F7)
            dados["f7"]["ai_restored"] = painel._nexo_ai_ativo
            tecla_real(janela, painel, Qt.Key.Key_F6)
            dialogo = painel._dialogo_nexo_ai
            dados["f6"] = {"keyboard_opened": bool(dialogo and dialogo.isVisible())}
            if dialogo and dialogo.isVisible():
                texto = dialogo.findChild(QPlainTextEdit, "nexo_ai_auditoria")
                dados["f6"]["text"] = texto.toPlainText()
                dados["f6"]["read_only"] = texto.isReadOnly()
                screenshots.append(salvar_png(dialogo.grab(), pasta / f"{nome}_procedencia.png"))
                dialogo.close()
                app.processEvents()
            alvo = assistente.retangulos_internos(central)["detalhes"].center()
            QTest.mouseClick(painel, Qt.MouseButton.LeftButton, pos=alvo)
            app.processEvents()
            dados["f6"]["click_opened"] = bool(painel._dialogo_nexo_ai and painel._dialogo_nexo_ai.isVisible())
            if painel._dialogo_nexo_ai:
                painel._dialogo_nexo_ai.close()
        return serializar(dados)
    finally:
        parar_timers(janela)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, help="Nova pasta exclusiva (nao pode existir)")
    parser.add_argument("--estados", nargs="+", choices=[e.name for e in ESTADOS],
                        default=[e.name for e in ESTADOS])
    parser.add_argument("--ambiente", default="Carga concorrente nao controlada; nao interpretar como benchmark isolado")
    args = parser.parse_args(argv)
    pasta = args.saida or ROOT / "outputs" / "qa_nexo_ai_independente" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    pasta.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    original, baseline_hash = geometria_original()
    report = {"classification": ROTULO, "end_to_end": False,
              "external_adapter_exercised": False, "screenshot_source": "real_JanelaFluxo_QWidget_grab",
              "qt_platform": app.platformName(), "qt_binding": QT_BINDING_VERSION,
              "python": sys.version, "os": platform.platform(),
              "environment_label": args.ambiente,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "source_hashes_before": hashes_fontes(), "head_regions_sha256": baseline_hash,
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "limitations": ["Offscreen nao valida DPI/desktop nativo.",
                              "Cenarios nao sao pregao, nao usam adaptador externo e nao sao E2E.",
                              "Nao ha aprovacao visual automatica nem limiar de performance arbitrario.",
                              "Compra/venda do motor sao verificadas nos testes; harness nao forca sinais.",
                              "AGUARDANDO sem eventos e verificado nos testes; fabrica sempre publica eventos."],
              "scenarios": [], "errors": [], "visual_verdict": "PENDING_HUMAN_OR_INDEPENDENT_IMAGE_INSPECTION"}
    for estado_nome in args.estados:
        estado = EstadoASG[estado_nome]
        print(f"Preparando historia {estado_nome} - {ROTULO}", flush=True)
        janela, sessao, manifesto = montar_cenario_controlado_asg(estado, largura=1480, altura=900)
        try:
            parar_timers(janela)
            historia = enriquecer_historia(janela, sessao, estado=estado)
            preparado = (janela, sessao, manifesto, historia)
            for tamanho in RESOLUCOES:
                print(f"Auditando {estado_nome} {tamanho[0]}x{tamanho[1]} - {ROTULO}", flush=True)
                try:
                    report["scenarios"].append(auditar_cenario(app, estado, tamanho, pasta, original, args.ambiente, preparado))
                except Exception:
                    report["errors"].append({"state": estado_nome, "size": tamanho, "error": traceback.format_exc()})
                    print(report["errors"][-1]["error"], flush=True)
                report["source_hashes_after"] = hashes_fontes()
                report["sources_unchanged_during_run"] = report["source_hashes_before"] == report["source_hashes_after"]
                (pasta / "measurements.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        finally:
            fechar_cenario(janela, sessao)
    print(f"ARTEFATOS: {pasta.resolve()}", flush=True)
    print(f"CENARIOS: {len(report['scenarios'])}; ERROS: {len(report['errors'])}; sem autoaprovacao visual", flush=True)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
