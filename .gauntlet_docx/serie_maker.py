"""Registrador TEMPORAL do gauge EQUILIBRIO (P8).

Roda o painel REAL pelo pipeline REAL (`scripts.painel.main`, replay com
livro), so que grampeia `PainelNexoMercadoASG.aplicar` para gravar, a cada
snapshot: o score CRU do MakerProxy e o score que a UI mostra. Um PNG nao
prova gradualidade; esta serie prova.

    python .gauntlet_docx/serie_maker.py saida.csv -- <args de scripts/painel.py>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def main() -> int:
    saida = Path(sys.argv[1])
    resto = sys.argv[2:]
    if resto and resto[0] == "--":
        resto = resto[1:]

    from fluxopro.ui.paineis import asg as _asg

    linhas: list[tuple[int, float, float]] = []
    aplicar_real = _asg.PainelNexoMercadoASG.aplicar

    def aplicar_grampeado(self, snapshot):
        bruta = next(
            (l.forca for l in snapshot.matriz.linhas if l.componente == "MAKERPROXY"),
            None,
        )
        aplicar_real(self, snapshot)
        if bruta is not None:
            linha = self._linha_maker()
            mostrado = 0.0 if linha is None else linha.forca
            linhas.append((snapshot.timestamp_ns, bruta, mostrado))

    _asg.PainelNexoMercadoASG.aplicar = aplicar_grampeado
    try:
        from scripts.painel import main as painel_main

        codigo = painel_main(resto)
    finally:
        _asg.PainelNexoMercadoASG.aplicar = aplicar_real

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_ns", "bruta", "mostrada"])
        w.writerows(linhas)
    print(f"{saida} | {len(linhas)} snapshots")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
