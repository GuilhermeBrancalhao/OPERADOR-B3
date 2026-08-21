"""Harness de mutacao da borda MT5.

Diferente do `.mut/harness.py` da casa em tres pontos que importam aqui:

1. Roda SO `tests/test_dados_mt5.py` — a suite inteira esta vermelha por
   trabalho em curso de outros modulos, e uma mutacao "morta" por falha
   alheia nao prova nada.
2. NOMEIA os testes que pegaram cada mutacao (a exigencia da rodada).
3. Confere a restauracao BYTE A BYTE por sha256 do arquivo inteiro, e nao
   por `git diff` — `fluxopro/dados/` casa com o padrao `dados/` do
   .gitignore e um diff vazio ali nao prova nada.

Uso: python .mut/harness_mt5.py .mut/mt5_borda.json
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ALVO_TESTES = "tests/test_dados_mt5.py"


def sha(caminho: pathlib.Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def rodar_pytest():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", ALVO_TESTES, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True, timeout=300,
    )
    saida = (r.stdout or "") + (r.stderr or "")
    nomes = re.findall(r"^FAILED [^:]+::(\S+)", saida, flags=re.M)
    nomes += re.findall(r"^ERROR [^:]+::(\S+)", saida, flags=re.M)
    ultima = saida.strip().splitlines()[-1] if saida.strip() else ""
    return r.returncode, ultima, nomes


def main(tabela_path):
    tabela = json.loads(pathlib.Path(tabela_path).read_text(encoding="utf-8"))
    resultados = []

    rc, linha, _ = rodar_pytest()
    print(f"BASELINE  rc={rc}  {linha}\n")
    if rc != 0:
        print("ABORTADO: a baseline de test_dados_mt5.py nao esta verde.")
        return 1

    for m in tabela:
        alvo = RAIZ / m["arquivo"]
        bruto_antes = alvo.read_bytes()
        sha_antes = hashlib.sha256(bruto_antes).hexdigest()
        original = bruto_antes.decode("utf-8")

        n = original.count(m["de"])
        if n != m.get("n", 1):
            resultados.append({"id": m["id"], "estado": "ERRO_ANCORA",
                               "detalhe": f"{n} ocorrencias", "testes": []})
            print(f'{m["id"]:5} ERRO_ANCORA  {n} ocorrencias  <- {m["desc"]}', flush=True)
            continue

        alvo.write_text(original.replace(m["de"], m["para"]), encoding="utf-8")
        try:
            rc, linha, nomes = rodar_pytest()
        finally:
            alvo.write_bytes(bruto_antes)

        sha_depois = sha(alvo)
        restaurado = sha_depois == sha_antes
        estado = "MORTA" if rc != 0 else "SOBREVIVEU"
        resultados.append({"id": m["id"], "estado": estado, "desc": m["desc"],
                           "linha": linha, "testes": nomes,
                           "restaurado_byte_a_byte": restaurado,
                           "sha256": sha_depois})
        marca = "" if restaurado else "  *** RESTAURACAO FALHOU ***"
        print(f'{m["id"]:5} {estado:11} {len(nomes):2} teste(s)  {linha}{marca}')
        print(f'      {m["desc"]}')
        for nome in nomes[:6]:
            print(f'        - {nome}')
        if len(nomes) > 6:
            print(f'        ... +{len(nomes)-6}')
        print(flush=True)

    print("=== RESUMO ===")
    sob = [r for r in resultados if r["estado"] == "SOBREVIVEU"]
    err = [r for r in resultados if r["estado"] == "ERRO_ANCORA"]
    nao_rest = [r for r in resultados if r.get("restaurado_byte_a_byte") is False]
    print(f"total={len(resultados)}  mortas={len(resultados)-len(sob)-len(err)}  "
          f"SOBREVIVERAM={len(sob)}  erro_ancora={len(err)}  "
          f"restauracao_falhou={len(nao_rest)}")
    for r in sob:
        print("  SOBREVIVEU:", r["id"], "-", r.get("desc"))
    for r in err:
        print("  ERRO_ANCORA:", r["id"], r["detalhe"])
    destino = RAIZ / ".mut" / (pathlib.Path(tabela_path).stem + "_res.json")
    destino.write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")
    print("sha256 final do alvo:", sha(RAIZ / "fluxopro/dados/mt5.py"))
    return 1 if (sob or err or nao_rest) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
