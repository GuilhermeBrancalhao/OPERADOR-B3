# -*- coding: utf-8 -*-
"""Harness de mutacao da onda 9 — janela movel da referencia de magnitude.

Mesma disciplina do `.mut/harness_r6.py`, com duas diferencas deliberadas:

  1. registra em `.mut/r6_em_voo_motor.json` (arquivo PROPRIO). O repositorio
     tem outras frentes editando outros modulos ao mesmo tempo; compartilhar o
     registro em voo faria uma frente apagar a linha da outra.
  2. roda apenas `tests/test_motor_sinais.py`. A suite inteira tem falhas
     alheias em voo (`test_app_saida`, `test_app_pipeline` — as duas de outra
     frente), e com elas TODA mutacao daria "MORTA" por motivo errado. Um
     veredito de mutacao so vale contra uma suite verde.

Disciplina preservada:
  - registra ANTES de escrever no arquivo de producao;
  - restaura SEMPRE, em try/finally;
  - confere sha256 do conteudo NORMALIZADO (CRLF -> LF): a R5 registrou um
     restore que devolveu bytes errados por causa de CRLF;
  - confere tambem `git status --porcelain` do arquivo no fim;
  - aborta tudo se alguma restauracao nao bater;
  - apaga o registro ao restaurar;
  - nomeia o TESTE que matou cada mutante, e compara com o teste esperado.

Uso: python .mut/harness_r6_motor.py r6_motor_janela.json r6_motor_janela_res.json
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EM_VOO = os.path.join(RAIZ, ".mut", "r6_em_voo_motor.json")
SUITE = "tests/test_motor_sinais.py"
CR, LF = chr(13), chr(10)


def ler(p):
    return io.open(p, encoding="utf-8").read()


def escrever(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def sha(s):
    return hashlib.sha256(s.replace(CR + LF, LF).encode("utf-8")).hexdigest()


def em_voo_ler():
    if os.path.exists(EM_VOO):
        return json.load(io.open(EM_VOO, encoding="utf-8"))
    return []


def em_voo_gravar(lista):
    io.open(EM_VOO, "w", encoding="utf-8").write(
        json.dumps(lista, ensure_ascii=False, indent=2))


def git_sujo(arquivo):
    p = subprocess.run(["git", "status", "--porcelain", "--", arquivo],
                       cwd=RAIZ, capture_output=True, text=True)
    return (p.stdout or "").strip()


def rodar_suite():
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "-x", "--no-header",
         "--tb=no", "-p", "no:cacheprovider"],
        cwd=RAIZ, capture_output=True, text=True)
    saida = (p.stdout or "") + (p.stderr or "")
    mortos = re.findall(r"FAILED [^:]+::(\S+)", saida)
    return p.returncode == 0, (mortos[0] if mortos else ""), saida[-400:], time.time() - t0


def main():
    tabela = sys.argv[1]
    saida_nome = sys.argv[2]
    mutacoes = json.load(io.open(os.path.join(RAIZ, ".mut", tabela), encoding="utf-8"))

    # linha de base: a suite do motor tem de estar VERDE antes de comecar.
    ok, _, log, seg = rodar_suite()
    if not ok:
        raise SystemExit("linha de base VERMELHA, mutacao nao vale nada:\n" + log)
    print("linha de base VERDE (%.0fs)" % seg, flush=True)

    res = []
    for i, m in enumerate(mutacoes, 1):
        alvo = os.path.join(RAIZ, m["arquivo"].replace("/", os.sep))
        original = ler(alvo)
        sha_antes = sha(original)
        sujo_antes = git_sujo(m["arquivo"])
        n = original.count(m["de"])
        if n != 1:
            v = "ANCORA_EXTINTA" if n == 0 else "ANCORA_NAO_UNICA(%d)" % n
            print("[%2d/%d] %-5s %s -- %s" % (i, len(mutacoes), m["id"], v, m["desc"][:60]),
                  flush=True)
            res.append({"id": m["id"], "desc": m["desc"], "veredito": v})
            continue

        reg = em_voo_ler()
        reg.append({"id": m["id"], "arquivo": m["arquivo"],
                    "sha256_norm_original": sha_antes,
                    "git_status_antes": sujo_antes,
                    "aplicada_em": time.strftime("%Y-%m-%dT%H:%M:%S")})
        em_voo_gravar(reg)
        try:
            escrever(alvo, original.replace(m["de"], m["para"]))
            assert sha(ler(alvo)) != sha_antes, "mutacao nao alterou o arquivo: " + m["id"]
            ok, morto_em, log, seg = rodar_suite()
            veredito = "SOBREVIVEU" if ok else "MORTA"
            casou = (morto_em == m.get("espera_morrer_em"))
            print("[%2d/%d] %-5s %-10s %-52s %s" % (
                i, len(mutacoes), m["id"], veredito, morto_em or "(nenhum)",
                "" if casou or ok else "<- teste diferente do esperado"), flush=True)
            res.append({"id": m["id"], "desc": m["desc"], "veredito": veredito,
                        "morta_por": morto_em, "esperado": m.get("espera_morrer_em"),
                        "teste_esperado_confere": casou, "segundos": round(seg, 1),
                        "log": "" if ok else log[-300:]})
        finally:
            escrever(alvo, original)
            sha_depois = sha(ler(alvo))
            if sha_depois != sha_antes:
                raise SystemExit("RESTAURACAO FALHOU (sha) em %s: %s != %s"
                                 % (m["arquivo"], sha_depois, sha_antes))
            if git_sujo(m["arquivo"]) != sujo_antes:
                raise SystemExit("RESTAURACAO FALHOU (git status) em %s" % m["arquivo"])
            em_voo_gravar([e for e in em_voo_ler() if e["id"] != m["id"]])

    io.open(os.path.join(RAIZ, ".mut", saida_nome), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=2))

    print("\n=== RESUMO %s ===" % saida_nome)
    print("  %-6s %-11s %-6s %s" % ("id", "veredito", "casou", "morta por"))
    for r in res:
        print("  %-6s %-11s %-6s %s" % (
            r["id"], r["veredito"],
            "sim" if r.get("teste_esperado_confere") else "NAO",
            r.get("morta_por") or "-"))
    vivos = [r["id"] for r in res if r["veredito"] != "MORTA"]
    print("\n  %d/%d MORTAS. Sobreviventes: %s"
          % (len(res) - len(vivos), len(res), vivos or "nenhum"))
    assert em_voo_ler() == [], "r6_em_voo_motor.json nao ficou vazio"
    print("  registro em voo vazio: OK")
    print("  git status do alvo: %r" % (git_sujo("fluxopro/motor/sinais.py"),))


if __name__ == "__main__":
    main()
