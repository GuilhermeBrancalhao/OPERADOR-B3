# -*- coding: utf-8 -*-
"""Re-verificacao DIFERENCIAL das mutacoes cujo veredito ficou contaminado.

Por que existe: este trabalho roda com outros dois builders escrevendo em
`gravacao/`, `dados/leitor_gravacao.py` e `motor/sinais.py` ao mesmo tempo.
Durante o lote principal, `tests/test_gravacao_*` ficou vermelho por trabalho
alheio em voo. Como o lote roda `pytest -x` e `test_gravacao_*` vem ANTES de
`test_replay_*` na ordem alfabetica, toda mutacao aplicada nessa janela foi
reportada MORTA — com o nome de um teste que nao tem relacao nenhuma com o
arquivo mutado. Dez verdictos ficaram assim, e um deles (B01) contradizia uma
previsao de equivalencia, que foi o que fez o problema aparecer.

O criterio aqui NAO e "a suite passou": e **a suite falhou em algo NOVO**.

    MORTA  <=>  falhas(mutante) - falhas(baseline)  != conjunto vazio

Baseline medido imediatamente antes de cada mutacao, na mesma arvore, para
que uma mudanca do vizinho no meio do lote apareca no baseline e nao no
veredito. Roda SEM `-x`, porque o conjunto de falhas so e comparavel se a
suite for ate o fim.

Restauracao e conferencia identicas ao harness principal: bytes, sha256
normalizado e `git status`.
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
EM_VOO = os.path.join(RAIZ, '.mut', 'r6_em_voo_core_app.json')
CR, LF = chr(13), chr(10)


def sha_norm(dados: bytes) -> str:
    return hashlib.sha256(dados.replace(b'\r\n', b'\n')).hexdigest()


def em_voo_ler():
    if os.path.exists(EM_VOO):
        return json.load(io.open(EM_VOO, encoding='utf-8'))
    return []


def em_voo_gravar(lista):
    io.open(EM_VOO, 'w', encoding='utf-8').write(
        json.dumps(lista, ensure_ascii=False, indent=2))


def git_sujo(rel: str) -> str:
    p = subprocess.run(['git', 'status', '--porcelain', '--', rel],
                       cwd=RAIZ, capture_output=True, text=True)
    return (p.stdout or '').strip()


def falhas_da_suite() -> tuple[set, int, float]:
    """Conjunto de `arquivo::teste` que FALHARAM na suite inteira, sem -x."""
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-q', '--no-header',
         '-p', 'no:cacheprovider', '--tb=no'],
        cwd=RAIZ, capture_output=True, text=True)
    saida = (p.stdout or '')
    falhas = set(re.findall(r'^(?:FAILED|ERROR) ([^\s]+)', saida, re.M))
    m = re.search(r'(\d+) passed', saida)
    return falhas, int(m.group(1)) if m else -1, time.time() - t0


def main() -> None:
    tabela, so_ids, saida_nome = sys.argv[1], set(sys.argv[2].split(',')), sys.argv[3]
    todas = json.load(io.open(os.path.join(RAIZ, '.mut', tabela), encoding='utf-8'))
    mutacoes = [m for m in todas if m['id'] in so_ids]
    faltando = so_ids - {m['id'] for m in mutacoes}
    if faltando:
        raise SystemExit('ids nao encontrados: %s' % sorted(faltando))

    sujo_antes = {m['arquivo']: git_sujo(m['arquivo']) for m in mutacoes}

    res = []
    for i, m in enumerate(mutacoes, 1):
        rel = m['arquivo']
        alvo = os.path.join(RAIZ, rel.replace('/', os.sep))
        original = io.open(alvo, 'rb').read()
        sha_antes = sha_norm(original)
        texto = original.decode('utf-8')
        crlf = b'\r\n' in original

        def nl(s: str) -> str:
            return s.replace(LF, CR + LF) if crlf else s

        base, n_base, seg_base = falhas_da_suite()
        print('[%d/%d] %-6s baseline: %d passaram, %d falha(s) alheia(s) %s (%.0fs)'
              % (i, len(mutacoes), m['id'], n_base, len(base),
                 sorted(base) if base else '', seg_base), flush=True)

        de, para = nl(m['de']), nl(m['para'])
        if texto.count(de) != 1:
            res.append({'id': m['id'], 'arquivo': rel, 'desc': m['desc'],
                        'veredito': 'ANCORA_NAO_UNICA'})
            continue

        reg = em_voo_ler()
        reg.append({'id': m['id'], 'arquivo': rel, 'sha256_norm_original': sha_antes,
                    'aplicada_em': time.strftime('%Y-%m-%dT%H:%M:%S')})
        em_voo_gravar(reg)
        try:
            io.open(alvo, 'wb').write(texto.replace(de, para).encode('utf-8'))
            com_mut, n_mut, seg = falhas_da_suite()
            novas = com_mut - base
            veredito = 'MORTA' if novas else 'SOBREVIVEU'
            print('        %-6s %-10s (%.0fs) novas falhas: %s'
                  % (m['id'], veredito, seg, sorted(novas)[:3] or '(nenhuma)'), flush=True)
            res.append({'id': m['id'], 'arquivo': rel, 'desc': m['desc'],
                        'veredito': veredito,
                        'falhas_alheias_no_baseline': sorted(base),
                        'novas_falhas': sorted(novas)[:5],
                        'passaram_no_baseline': n_base, 'passaram_com_mutante': n_mut})
        finally:
            io.open(alvo, 'wb').write(original)
            depois = io.open(alvo, 'rb').read()
            if sha_norm(depois) != sha_antes or depois != original:
                raise SystemExit('RESTAURACAO FALHOU em %s' % rel)
            if git_sujo(rel) != sujo_antes[rel]:
                raise SystemExit('RESTAURACAO FALHOU (git status) em %s' % rel)
            em_voo_gravar([e for e in em_voo_ler() if e['id'] != m['id']])

    io.open(os.path.join(RAIZ, '.mut', saida_nome), 'w', encoding='utf-8').write(
        json.dumps(res, ensure_ascii=False, indent=2))

    print('\n=== RESUMO DIFERENCIAL %s ===' % saida_nome)
    for r in res:
        print('  %-6s %-20s %-12s %s' % (r['id'], r['arquivo'].split('/')[-1],
                                         r['veredito'], r['desc'][:58]))
    print('  --> %d MORTAS | %d SOBREVIVERAM' % (
        sum(1 for r in res if r['veredito'] == 'MORTA'),
        sum(1 for r in res if r['veredito'] == 'SOBREVIVEU')))
    if em_voo_ler() != []:
        raise SystemExit('registro em voo nao ficou vazio')
    print('  registro em voo vazio: OK')


if __name__ == '__main__':
    main()
