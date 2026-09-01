"""Capturas Qt reais e 30 quadros deterministas; entradas sinteticas rotuladas.

Executar: python -m scripts.auditar_raios --saida outputs/qa_raios
Nao conecta corretora, nao modifica configuracao nem publica ordens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

from scripts.auditar_nexo_ai import (
    QApplication, EstadoASG, fechar_cenario, enriquecer_historia,
    identidade_dados, parar_timers, quadro_painel, render_painel, serializar,
)
from scripts.painel import montar_cenario_controlado_asg
from fluxopro.ui.paineis.nexo import assistente, estatistica
from fluxopro.ui import tokens
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter


def comparar_renderer(serie):
    """30 pares no mesmo processo; baseline fixo antes desta correcao."""
    raiz = Path(__file__).resolve().parents[1]
    codigo = subprocess.check_output(
        ["git", "show", "8329775:fluxopro/ui/paineis/nexo/estatistica.py"],
        cwd=raiz, text=True, encoding="utf-8")
    namespace = {"__name__": "baseline_estatistica"}
    exec(compile(codigo, "baseline_estatistica", "exec"), namespace)
    renderers = {"baseline": namespace["_desenhar_barras"], "pilhas": estatistica._desenhar_barras}
    tempos = {k: [] for k in renderers}
    imagem = QImage(212, 185, QImage.Format.Format_ARGB32)
    for rodada in range(33):
        ordem = list(renderers) if rodada % 2 == 0 else list(reversed(renderers))
        for nome in ordem:
            imagem.fill(QColor("#030609"))
            p = QPainter(imagem)
            inicio = time.perf_counter()
            renderers[nome](p, imagem.rect(), serie)
            tempo = (time.perf_counter() - inicio) * 1000
            p.end()
            if rodada >= 3:
                tempos[nome].append(tempo)
    return {nome: {"ms": valores, "p50_ms": statistics.median(valores),
                   "p95_ms": sorted(valores)[28]} for nome, valores in tempos.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()
    args.saida.mkdir(parents=True, exist_ok=False)
    # Parar os QTimers nao congela o relogio monotonic do wallpaper.
    # A opcao oficial fixa a cenografia somente neste processo de auditoria.
    os.environ["FLUXOPRO_REDUCED_MOTION"] = "1"
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    relatorio = {"fonte": "CENARIO SINTETICO QA; NAO E PREGAO",
                 "qt_platform": app.platformName(), "screenshots": [],
                 "wallpaper_motion": "disabled_for_pixel_comparison",
                 "escala": [.1, .3, .5, .7, .9], "quadros": []}

    # Mesmo renderer, cinco entradas conhecidas para cada lado. Nao e um
    # mockup: sao os pixels nativos usados pelo painel, sem retoque/upscale.
    imagem = QImage(840, 270, QImage.Format.Format_ARGB32)
    imagem.fill(QColor("#030609"))
    p = QPainter(imagem)
    p.setFont(tokens.fonte_rotulo(11))
    p.setPen(QColor("white"))
    p.drawText(QRect(12, 3, 816, 23), "QA SINTETICO - ESCALA 1, 2, 3, 4, 5 RAIOS - NAO E PREGAO")
    for i, sinal in enumerate((1, -1)):
        valores = tuple((j * 1_000_000_000, 10000, sinal*v, 1)
                        for j, v in enumerate(relatorio["escala"]))
        estatistica._desenhar_barras(p, QRect(12 + i * 418, 28, 398, 230), valores)
    p.end()
    assert imagem.save(str(args.saida / "escala_1_a_5.png"))
    janela, sessao, manifesto = montar_cenario_controlado_asg(
        EstadoASG.AO_VIVO, largura=1480, altura=900)
    try:
        parar_timers(janela)
        relatorio["fabrica"] = manifesto
        relatorio["historico"] = enriquecer_historia(janela, sessao)
        parar_timers(janela)
        painel = janela.asg.nexo
        relatorio["serie_congelada"] = serializar(painel._estado_nexo().serie)
        relatorio["renderer_ab_30"] = comparar_renderer(painel._estado_nexo().serie)
        for largura, altura in ((1280, 720), (1480, 900), (1920, 1080)):
            janela.resize(largura, altura)
            app.processEvents()
            parar_timers(janela)
            janela.asg.layout().activate()
            for widget in janela.paineis:
                if widget.isVisible():
                    widget.marcar_tudo_sujo()
                    widget._quadro()
            # Controle congela tanto mercado como fase do wallpaper.
            antes = identidade_dados(painel)
            render_painel(painel)
            tempos, hashes = [], []
            for _ in range(30):
                inicio = time.perf_counter()
                quadro = render_painel(painel)
                tempos.append((time.perf_counter() - inicio) * 1000)
                hashes.append(hashlib.sha256(bytes(quadro.constBits())).hexdigest())
            registro = {"resolucao": [largura, altura], "amostras_ms": tempos,
                        "p50_ms": statistics.median(tempos),
                        "p95_ms": sorted(tempos)[28],
                        "pixels_deterministas": len(set(hashes)) == 1,
                        "snapshot_preservado": antes == identidade_dados(painel)}
            registro["campos_alterados"] = [
                k for k, v in identidade_dados(painel).items() if antes[k] != v]
            registro["hashes"] = hashes
            (args.saida / f"sonda_{largura}.json").write_text(
                json.dumps(registro, indent=2), encoding="utf-8")
            print(registro["pixels_deterministas"], registro["snapshot_preservado"],
                  registro["campos_alterados"], flush=True)
            assert registro["pixels_deterministas"] and registro["snapshot_preservado"]
            relatorio["quadros"].append(registro)
            nome = f"operador_{largura}x{altura}.png"
            assert janela.grab().save(str(args.saida / nome))
            regiao = assistente.caixas_integradas(quadro_painel(painel))["estatistica"]
            recorte = f"placar_{largura}x{altura}.png"
            assert painel.grab(regiao).save(str(args.saida / recorte))
            relatorio["screenshots"].extend([nome, recorte])
            print(f"{largura}x{altura}: 30 quadros identicos; p95={registro['p95_ms']:.2f}ms", flush=True)
    finally:
        fechar_cenario(janela, sessao)
    relatorio["limitacoes"] = [
        "Qt offscreen nao comprova DPI/desktop ou feed real.",
        "Tempos incluem copia de imagem; nao sao throughput do pipeline.",
        "Comparacao visual deve ser inspecionada, nao deduzida dos testes.",
    ]
    raiz = Path(__file__).resolve().parents[1]
    relatorio["sha256_fontes"] = {
        str(p.relative_to(raiz)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [raiz / "fluxopro/ui/paineis/nexo/estatistica.py",
                  raiz / "fluxopro/ui/paineis/asg.py", Path(__file__).resolve()]}
    (args.saida / "medicoes.json").write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    print(args.saida.resolve())


if __name__ == "__main__":
    main()
