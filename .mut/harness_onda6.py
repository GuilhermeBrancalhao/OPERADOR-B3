"""Harness de mutacao da onda 6, com escopo nas suites de microestrutura.

Diferenca para o `.mut/harness.py`: roda so `tests/test_micro_inferencia.py` e
`tests/test_micro_livro.py` (as suites que descrevem o contrato dos dois
arquivos mutados) e REPORTA O NOME dos testes que matam cada mutacao. Alem
disso confere, ao final, byte a byte, que cada arquivo tocado voltou ao
conteudo original.

Uso: python .mut/harness_onda6.py .mut/onda6.json
"""
import hashlib
import json
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SUITES = ["tests/test_micro_inferencia.py", "tests/test_micro_livro.py"]


def rodar_pytest():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *SUITES, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    saida = (r.stdout or "") + (r.stderr or "")
    mortos = []
    for linha in saida.splitlines():
        if linha.startswith("FAILED "):
            mortos.append(linha.split(" ")[1].split("::")[-1].split("[")[0])
    resumo = saida.strip().splitlines()[-1] if saida.strip() else ""
    return r.returncode, resumo, sorted(set(mortos))


def sha(caminho: pathlib.Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def main(tabela_path):
    tabela = json.loads(pathlib.Path(tabela_path).read_text(encoding="utf-8"))
    antes = {m["arquivo"]: sha(RAIZ / m["arquivo"]) for m in tabela}
    resultados = []
    for m in tabela:
        alvo = RAIZ / m["arquivo"]
        original = alvo.read_text(encoding="utf-8")
        n = original.count(m["de"])
        if n != m.get("n", 1):
            print(f'{m["id"]:5} ERRO_ANCORA  {n} ocorrencias', flush=True)
            resultados.append({"id": m["id"], "estado": "ERRO_ANCORA"})
            continue
        alvo.write_text(original.replace(m["de"], m["para"]), encoding="utf-8")
        try:
            rc, resumo, mortos = rodar_pytest()
        finally:
            alvo.write_text(original, encoding="utf-8")
        estado = "MORTA" if rc != 0 else "SOBREVIVEU"
        resultados.append(
            {"id": m["id"], "estado": estado, "desc": m["desc"],
             "resumo": resumo, "testes": mortos}
        )
        print(f'{m["id"]:5} {estado:11} {resumo}', flush=True)
        print(f'      {m["desc"]}', flush=True)
        for t in mortos[:4]:
            print(f'        -> {t}', flush=True)
        if len(mortos) > 4:
            print(f'        -> (+{len(mortos)-4} outros)', flush=True)

    print("\n=== RESUMO ===")
    sob = [r for r in resultados if r["estado"] != "MORTA"]
    print(f'total={len(resultados)}  mortas={len(resultados)-len(sob)}  NAO_MORTAS={len(sob)}')
    for r in sob:
        print("  ", r["id"], r["estado"])

    print("\n=== RESTAURACAO (sha256 antes x depois) ===")
    integro = True
    for arquivo, h in antes.items():
        agora = sha(RAIZ / arquivo)
        ok = agora == h
        integro &= ok
        print(f'  {"OK " if ok else "DIVERGIU"} {arquivo}  {agora[:16]}')
    print("  ->", "restauracao integra" if integro else "*** ARQUIVO ALTERADO ***")
    saida = RAIZ / ".mut" / (pathlib.Path(tabela_path).stem + "_res.json")
    saida.write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
