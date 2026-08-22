# -*- coding: utf-8 -*-
"""Harness de mutacao da auditoria R6 (5a rodada adversarial).

Disciplina obrigatoria:
  1. registra em `.mut/r6_em_voo.json` ANTES de escrever no arquivo de producao;
  2. restaura SEMPRE, em try/finally;
  3. confere sha256 do conteudo NORMALIZADO (CRLF -> LF): `git diff` ja foi
     provado cego neste repo (o .gitignore da R3) e a comparacao crua contra o
     blob de HEAD falha com core.autocrlf=true;
  4. aborta tudo se alguma restauracao nao bater;
  5. apaga o registro ao restaurar.

Veredito: MORTA = a suite pegou. SOBREVIVEU = 574 testes verdes com o defeito.
"""
from __future__ import annotations
import hashlib, io, json, os, subprocess, sys, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EM_VOO = os.path.join(RAIZ, '.mut', 'r6_em_voo.json')
CR, LF = chr(13), chr(10)


def ler(p): return io.open(p, encoding='utf-8').read()
def escrever(p, s): io.open(p, 'w', encoding='utf-8', newline='').write(s)
def sha(s): return hashlib.sha256(s.replace(CR + LF, LF).encode('utf-8')).hexdigest()


def em_voo_ler():
    if os.path.exists(EM_VOO):
        return json.load(io.open(EM_VOO, encoding='utf-8'))
    return []


def em_voo_gravar(l):
    io.open(EM_VOO, 'w', encoding='utf-8').write(json.dumps(l, ensure_ascii=False, indent=2))


def rodar_suite():
    """Suite INTEIRA com -x. Uma mutacao so 'sobrevive' se NENHUM dos 574 pega."""
    t0 = time.time()
    p = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q', '-x', '--no-header', '-p', 'no:cacheprovider'],
                       cwd=RAIZ, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout or '')[-1500:], time.time() - t0


def main():
    tabelas = sys.argv[1].split(',')
    saida = sys.argv[2]
    mutacoes = []
    for t in tabelas:
        d = json.load(io.open(os.path.join(RAIZ, '.mut', t), encoding='utf-8'))
        for m in d:
            if 'de' in m and 'para' in m:
                m['_tabela'] = t
                mutacoes.append(m)

    res = []
    for i, m in enumerate(mutacoes, 1):
        alvo = os.path.join(RAIZ, m['arquivo'].replace('/', os.sep))
        if not os.path.exists(alvo):
            res.append({**{k: m[k] for k in ('id', 'arquivo', 'desc', '_tabela')}, 'veredito': 'ARQUIVO_AUSENTE'})
            continue
        original = ler(alvo)
        sha_antes = sha(original)
        n = original.count(m['de'])
        if n != 1:
            v = 'ANCORA_EXTINTA' if n == 0 else 'ANCORA_NAO_UNICA(%d)' % n
            print('[%d/%d] %s %s -- %s' % (i, len(mutacoes), m['id'], v, m['desc'][:60]), flush=True)
            res.append({**{k: m[k] for k in ('id', 'arquivo', 'desc', '_tabela')}, 'veredito': v})
            continue

        reg = em_voo_ler()
        reg.append({'id': m['id'], 'arquivo': m['arquivo'], 'sha256_norm_original': sha_antes,
                    'aplicada_em': time.strftime('%Y-%m-%dT%H:%M:%S')})
        em_voo_gravar(reg)
        try:
            mutado = original
            if m.get('pre_de'):
                assert mutado.count(m['pre_de']) == 1, 'pre_de nao unico: ' + m['id']
                mutado = mutado.replace(m['pre_de'], m['pre_para'])
            mutado = mutado.replace(m['de'], m['para'])
            escrever(alvo, mutado)
            assert sha(ler(alvo)) != sha_antes, 'mutacao nao alterou o arquivo: ' + m['id']
            ok, log, seg = rodar_suite()
            veredito = 'SOBREVIVEU' if ok else 'MORTA'
            print('[%d/%d] %s %s (%.0fs) -- %s' % (i, len(mutacoes), m['id'], veredito, seg, m['desc'][:60]), flush=True)
            res.append({**{k: m[k] for k in ('id', 'arquivo', 'desc', '_tabela')},
                        'veredito': veredito, 'segundos': round(seg, 1),
                        'log': ('' if ok else log[-400:])})
        finally:
            escrever(alvo, original)
            sha_depois = sha(ler(alvo))
            if sha_depois != sha_antes:
                raise SystemExit('RESTAURACAO FALHOU em %s (%s != %s)' % (m['arquivo'], sha_depois, sha_antes))
            em_voo_gravar([e for e in em_voo_ler() if e['id'] != m['id']])

    io.open(os.path.join(RAIZ, '.mut', saida), 'w', encoding='utf-8').write(
        json.dumps(res, ensure_ascii=False, indent=2))
    print('\n=== RESUMO %s ===' % saida)
    for r in res:
        print('  %-10s %-12s %s' % (r['id'], r['veredito'], r['desc'][:70]))
    assert em_voo_ler() == [], 'r6_em_voo.json nao ficou vazio'
    print('registro em voo vazio: OK')


if __name__ == '__main__':
    main()
