"""Harness de mutação: aplica, roda pytest, restaura. Uso: python .mut/harness.py <tabela.json>"""
import json, subprocess, sys, pathlib, shutil, os

RAIZ = pathlib.Path(__file__).resolve().parent.parent

def rodar_pytest():
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
                       cwd=RAIZ, capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    return r.returncode, saida.strip().splitlines()[-1] if saida.strip() else ""

def falhas(saida_linha):
    return saida_linha

def main(tabela_path):
    tabela = json.loads(pathlib.Path(tabela_path).read_text(encoding="utf-8"))
    resultados = []
    for m in tabela:
        alvo = RAIZ / m["arquivo"]
        original = alvo.read_text(encoding="utf-8")
        if m["de"] not in original:
            resultados.append((m["id"], "ERRO_ANCORA", "string de origem nao encontrada"))
            print(f'{m["id"]:6} ERRO_ANCORA  {m["arquivo"]}  ::  {m["de"][:70]!r}', flush=True)
            continue
        n = original.count(m["de"])
        esperado = m.get("n", 1)
        if n != esperado:
            resultados.append((m["id"], "ERRO_ANCORA", f"{n} ocorrencias, esperado {esperado}"))
            print(f'{m["id"]:6} ERRO_ANCORA  {n} ocorrencias (esperado {esperado})', flush=True)
            continue
        mutado = original.replace(m["de"], m["para"])
        alvo.write_text(mutado, encoding="utf-8")
        try:
            rc, linha = rodar_pytest()
        finally:
            alvo.write_text(original, encoding="utf-8")
        estado = "MORTA" if rc != 0 else "SOBREVIVEU"
        resultados.append((m["id"], estado, linha))
        print(f'{m["id"]:6} {estado:11} {linha}   <- {m["desc"]}', flush=True)
    print("\n=== RESUMO ===")
    sob = [r for r in resultados if r[1] == "SOBREVIVEU"]
    err = [r for r in resultados if r[1] == "ERRO_ANCORA"]
    print(f"total={len(resultados)}  mortas={len(resultados)-len(sob)-len(err)}  SOBREVIVERAM={len(sob)}  erro_ancora={len(err)}")
    for r in sob:
        print("  SOBREVIVEU:", r[0])
    for r in err:
        print("  ERRO_ANCORA:", r[0], r[2])
    json.dump(resultados, open(RAIZ / ".mut" / (pathlib.Path(tabela_path).stem + "_res.json"), "w"), indent=1)

if __name__ == "__main__":
    main(sys.argv[1])
