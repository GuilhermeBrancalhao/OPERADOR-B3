"""Converte legendas .vtt em texto corrido, removendo timestamps e duplicatas.

O YouTube gera legenda automatica com "rolagem": cada cue repete as ultimas
palavras da cue anterior. Concatenar cru triplica o texto. Aqui a deduplicacao
e feita por linha ja vista, preservando a ordem de aparicao.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RE_TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->")
RE_TAG = re.compile(r"<[^>]+>")


def converter(caminho_vtt: Path) -> str:
    linhas_vistas: set[str] = set()
    saida: list[str] = []

    for linha in caminho_vtt.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if RE_TIMESTAMP.match(linha):
            continue
        if linha.isdigit():
            continue
        linha = RE_TAG.sub("", linha).strip()
        if not linha or linha in linhas_vistas:
            continue
        linhas_vistas.add(linha)
        saida.append(linha)

    return " ".join(saida)


def main() -> int:
    pasta = Path(__file__).parent / "legendas"
    convertidos = 0
    for vtt in sorted(pasta.glob("*.pt.vtt")):
        video_id = vtt.name[: -len(".pt.vtt")]
        destino = pasta / f"{video_id}.txt"
        if destino.exists():
            continue
        texto = converter(vtt)
        if not texto:
            print(f"VAZIO: {video_id}")
            continue
        destino.write_text(texto, encoding="utf-8")
        convertidos += 1
        print(f"{video_id}: {len(texto)} chars")
    print(f"\nconvertidos: {convertidos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
