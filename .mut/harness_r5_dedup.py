# -*- coding: utf-8 -*-
"""Harness de auto-mutacao do conserto R5 da dedup (detectores.py).

Iguais ao harness_r4: sha256 antes/depois normalizando CRLF, registro EM VOO
antes de aplicar, restauracao no `finally` conferida por hash.

Duas diferencas, as duas deliberadas:

1. Roda so `tests/test_micro_detectores.py` + `tests/test_app_pipeline.py`.
   A suite inteira esta VERMELHA por um teste alheio
   (`tests/test_dados_mt5.py::test_propriedade_erro_do_relogio_limitado_em_
   sequencia_adversarial`, do builder do mt5, em voo em paralelo). Com a suite
   inteira toda mutacao apareceria como MORTA sem provar nada.
2. Reporta o NOME dos testes que morreram, nao so o codigo de saida — mutacao
   que "morre" sem dizer quem a matou nao e evidencia.

O registro em voo vai para `r5_em_voo_dedup_detectores.json` e nao para
`r5_em_voo.json`: este ultimo esta OCUPADO agora pelo builder de
`fluxopro/motor/sinais.py` (mutacao M07). Sobrescrever o registro em voo de
outro builder e destruir exatamente a informacao que existe para restaurar o
arquivo dele se algo travar.

Uso: python .mut/harness_r5_dedup.py .mut/r5_dedup.json
"""
import hashlib
import json
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
EM_VOO = RAIZ / ".mut" / "r5_em_voo_dedup_detectores.json"
ALVOS = ["tests/test_micro_detectores.py", "tests/test_app_pipeline.py"]
CR = chr(13)
LF = chr(10)
CRLF = CR + LF


def sha(caminho):
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def rodar():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *ALVOS, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    saida = (r.stdout or "") + (r.stderr or "")
    mortos = sorted(
        {l.split(" ")[1].split("::")[-1].split(" ")[0]
         for l in saida.splitlines() if l.startswith("FAILED ")}
    )
    ultima = saida.strip().splitlines()[-1] if saida.strip() else ""
    return r.returncode, ultima, mortos


def main(tabela_path):
    tabela = json.loads(pathlib.Path(tabela_path).read_text(encoding="utf-8"))
    res = []
    for m in tabela:
        alvo = RAIZ / m["arquivo"]
        original = alvo.read_bytes()
        h0 = hashlib.sha256(original).hexdigest()
        crlf = CRLF.encode() in original
        texto = original.decode("utf-8").replace(CRLF, LF)
        n = texto.count(m["de"])
        if n != m.get("n", 1):
            res.append({"id": m["id"], "estado": "ERRO_ANCORA",
                        "detalhe": f"{n} ocorrencias"})
            print(f'{m["id"]:5} ERRO_ANCORA  {n} ocorrencias', flush=True)
            continue
        EM_VOO.write_text(
            json.dumps({"id": m["id"], "arquivo": m["arquivo"],
                        "sha256_original": h0, "de": m["de"], "para": m["para"]},
                       indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            novo = texto.replace(m["de"], m["para"])
            if crlf:
                novo = novo.replace(LF, CRLF)
            alvo.write_bytes(novo.encode("utf-8"))
            rc, ultima, mortos = rodar()
        finally:
            alvo.write_bytes(original)
            assert sha(alvo) == h0, f"RESTAURACAO FALHOU {m['id']}"
            EM_VOO.unlink(missing_ok=True)
        estado = "MORTA" if rc != 0 else "SOBREVIVEU"
        res.append({"id": m["id"], "estado": estado, "desc": m["desc"],
                    "linha": ultima, "testes": mortos})
        print(f'{m["id"]:5} {estado:11} {ultima}', flush=True)
        for t in mortos[:6]:
            print(f'        + {t}', flush=True)
    saida = pathlib.Path(tabela_path).with_name(
        pathlib.Path(tabela_path).stem + "_res.json")
    saida.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n=== RESUMO ===")
    sob = [r for r in res if r["estado"] == "SOBREVIVEU"]
    err = [r for r in res if r["estado"] == "ERRO_ANCORA"]
    print(f"total={len(res)} mortas={len(res)-len(sob)-len(err)} "
          f"SOBREVIVERAM={len(sob)} erro_ancora={len(err)}")
    for r in sob:
        print("  SOBREVIVEU:", r["id"], "-", r.get("desc", ""))


if __name__ == "__main__":
    main(sys.argv[1])
