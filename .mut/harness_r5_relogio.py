"""Harness de auto-mutacao do builder do RELOGIO da borda MT5 (R4 A.4).

Para cada mutacao em `mutacoes_r5_relogio.json`:

1. Le o arquivo alvo e calcula sha256 do conteudo com CRLF normalizado p/ LF
   (`core.autocrlf=true` nesta maquina; sha do byte cru pisca sem motivo).
2. Grava a mutacao no arquivo EM VOO -- registro ANTES de aplicar.
3. Aplica a substituicao literal (exige ancora unica).
4. Roda `tests/test_dados_mt5.py` e NOMEIA os testes que falharam.
5. try/finally: restaura o conteudo original e confere o sha256.
6. Remove a mutacao do arquivo EM VOO.

NOTA sobre o nome do arquivo em voo: a tarefa pede `.mut/r5_em_voo.json`,
mas ha quatro builders em paralelo nesta rodada e o harness irmao
(`.mut/harness_r5.py`) ja documentou que esse nome colide. Sobrescrever o
rastreamento em voo de um processo irmao ativo destruiria justamente a
informacao que o arquivo existe para preservar. Uso um nome proprio pelo
mesmo motivo e com a mesma convencao que o irmao adotou.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MUT_DIR = RAIZ / ".mut"
TABELA = MUT_DIR / "mutacoes_r5_relogio.json"
EM_VOO = MUT_DIR / "r5_em_voo_relogio_mt5.json"
RESULTADO = MUT_DIR / "r5_relogio_resultado.json"
ALVO_TESTES = "tests/test_dados_mt5.py"


def sha256_normalizado(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def ler_em_voo() -> list:
    return json.loads(EM_VOO.read_text(encoding="utf-8")) if EM_VOO.exists() else []


def gravar_em_voo(lista: list) -> None:
    EM_VOO.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


def rodar_testes() -> tuple[bool, str, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", ALVO_TESTES, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, timeout=600,
    )
    saida = (proc.stdout or "") + (proc.stderr or "")
    nomes = re.findall(r"^FAILED [^:]+::(\S+)", saida, flags=re.M)
    nomes += re.findall(r"^ERROR [^:]+::(\S+)", saida, flags=re.M)
    ultima = saida.strip().splitlines()[-1] if saida.strip() else ""
    return proc.returncode == 0, ultima, nomes


def main() -> int:
    mutacoes = json.loads(TABELA.read_text(encoding="utf-8"))

    verde, linha, _ = rodar_testes()
    print(f"BASELINE  {'VERDE' if verde else 'VERMELHA'}  {linha}\n")
    if not verde:
        print("ABORTADO: baseline vermelha, mutacao nao prova nada.")
        return 1

    resultados = []
    for m in mutacoes:
        caminho = RAIZ / m["arquivo"]
        original = caminho.read_text(encoding="utf-8")
        sha_antes = sha256_normalizado(caminho)

        ocorrencias = original.count(m["de"])
        if ocorrencias != 1:
            resultados.append({"id": m["id"], "desc": m["desc"],
                               "veredito": f"ANCORA_{ocorrencias}x"})
            print(f'[{m["id"]}] ANCORA {ocorrencias}x -- pulando: {m["desc"]}',
                  flush=True)
            continue

        gravar_em_voo(ler_em_voo() + [{
            "id": m["id"], "arquivo": m["arquivo"], "desc": m["desc"],
            "sha256_original_normalizado": sha_antes,
        }])

        try:
            caminho.write_text(original.replace(m["de"], m["para"]), encoding="utf-8")
            passou, linha, nomes = rodar_testes()
            veredito = "SOBREVIVEU" if passou else "MORTA"
            resultados.append({"id": m["id"], "arquivo": m["arquivo"],
                               "desc": m["desc"], "veredito": veredito,
                               "linha": linha, "testes_que_pegaram": nomes})
            print(f'[{m["id"]}] {veredito:11} {len(nomes)} teste(s)  {linha}',
                  flush=True)
            for n in nomes:
                print(f"          <- {n}")
        finally:
            caminho.write_text(original, encoding="utf-8")
            sha_depois = sha256_normalizado(caminho)
            assert sha_depois == sha_antes, f"RESTAURACAO FALHOU em {m['arquivo']}"
            gravar_em_voo([e for e in ler_em_voo() if e["id"] != m["id"]])

    RESULTADO.write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    if EM_VOO.exists():
        EM_VOO.unlink()

    sobreviventes = [r for r in resultados if r["veredito"] == "SOBREVIVEU"]
    print("\n=== RESUMO ===")
    for r in resultados:
        print(f'  {r["id"]}: {r["veredito"]:11} {r["desc"]}')
    print(f"\n{len(resultados) - len(sobreviventes)}/{len(resultados)} mortas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
