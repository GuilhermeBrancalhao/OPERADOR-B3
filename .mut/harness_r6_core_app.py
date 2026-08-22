# -*- coding: utf-8 -*-
"""Harness de mutacao do builder core+app (onda 9, resposta a R5).

Disciplina obrigatoria (a mesma da R5, com UMA correcao):
  1. registra em `.mut/r6_em_voo_core_app.json` ANTES de escrever no arquivo
     de producao;
  2. restaura SEMPRE, em try/finally;
  3. confere sha256 do conteudo NORMALIZADO (CRLF -> LF) contra o
     pre-mutacao, com SystemExit se divergir;
  4. confere `git status --porcelain` do arquivo, que tem de voltar limpo;
  5. apaga o registro ao restaurar.

CORRECAO sobre o harness da R5, cujo defeito o proprio auditor registrou:
ele restaurou o CONTEUDO certo com os BYTES errados (escreveu com
`newline=''`, gravando LF num working tree CRLF), e 14 arquivos ficaram
marcados `M` sem uma unica diferenca de conteudo. Aqui a leitura e a
restauracao sao em BYTES (`read_bytes`/`write_bytes`): a restauracao e
byte-a-byte identica por construcao, nao por convencao de escrita. E as duas
checagens rodam JUNTAS, porque sao complementares e nao alternativas — a
normalizada prova que nenhuma mutacao ficou para tras (e nao mente onde
`git diff` mente, por causa do core.autocrlf=true deste repo); o `git status`
prova que nenhum byte alheio mudou.

NOTA sobre `git checkout` como rede de seguranca: NAO serve aqui. Este
trabalho roda com 2 outros builders mexendo em `gravacao/` e `motor/`, e o
proprio arquivo mutado tem alteracoes ainda nao commitadas — um
`git checkout -- <arquivo>` apagaria o trabalho em voo em vez de restaurar a
mutacao. (Aprendido do jeito caro nesta sessao.)

Veredito: MORTA = a suite pegou. SOBREVIVEU = suite inteira verde COM o defeito.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EM_VOO = os.path.join(RAIZ, '.mut', 'r6_em_voo_core_app.json')
CR, LF = chr(13), chr(10)


def sha_norm(dados: bytes) -> str:
    """sha256 do conteudo com CRLF normalizado para LF."""
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


def rodar_suite():
    """Suite INTEIRA. Uma mutacao so 'sobrevive' se NENHUM teste a pegar."""
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-q', '-x', '--no-header',
         '-p', 'no:cacheprovider'],
        cwd=RAIZ, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout or '')[-1200:], time.time() - t0


def main() -> None:
    tabela = sys.argv[1]
    saida = sys.argv[2]
    mutacoes = json.load(io.open(os.path.join(RAIZ, '.mut', tabela), encoding='utf-8'))

    # Estado do git ANTES do lote: o que ja estava sujo (trabalho em voo dos
    # outros builders + o meu) nao pode ser confundido com residuo de mutacao.
    sujo_antes = {}
    for m in mutacoes:
        sujo_antes.setdefault(m['arquivo'], git_sujo(m['arquivo']))

    res = []
    for i, m in enumerate(mutacoes, 1):
        rel = m['arquivo']
        alvo = os.path.join(RAIZ, rel.replace('/', os.sep))
        if not os.path.exists(alvo):
            res.append({'id': m['id'], 'arquivo': rel, 'desc': m['desc'],
                        'veredito': 'ARQUIVO_AUSENTE'})
            continue

        original = io.open(alvo, 'rb').read()
        sha_antes = sha_norm(original)
        texto = original.decode('utf-8')
        crlf = b'\r\n' in original

        def nl(s: str) -> str:
            return s.replace(LF, CR + LF) if crlf else s

        de, para = nl(m['de']), nl(m['para'])
        n = texto.count(de)
        if n != 1:
            v = 'ANCORA_EXTINTA' if n == 0 else 'ANCORA_NAO_UNICA(%d)' % n
            print('[%d/%d] %-6s %-22s -- %s' % (i, len(mutacoes), m['id'], v, m['desc'][:64]),
                  flush=True)
            res.append({'id': m['id'], 'arquivo': rel, 'desc': m['desc'], 'veredito': v})
            continue

        reg = em_voo_ler()
        reg.append({'id': m['id'], 'arquivo': rel, 'sha256_norm_original': sha_antes,
                    'bytes_original': len(original),
                    'aplicada_em': time.strftime('%Y-%m-%dT%H:%M:%S')})
        em_voo_gravar(reg)
        try:
            mutado = texto
            if m.get('pre_de'):
                pd, pp = nl(m['pre_de']), nl(m['pre_para'])
                if mutado.count(pd) != 1:
                    raise SystemExit('pre_de nao unico: ' + m['id'])
                mutado = mutado.replace(pd, pp)
            mutado = mutado.replace(de, para)
            io.open(alvo, 'wb').write(mutado.encode('utf-8'))
            if sha_norm(io.open(alvo, 'rb').read()) == sha_antes:
                raise SystemExit('mutacao nao alterou o arquivo: ' + m['id'])

            ok, log, seg = rodar_suite()
            veredito = 'SOBREVIVEU' if ok else 'MORTA'
            print('[%d/%d] %-6s %-10s (%4.0fs) -- %s' % (
                i, len(mutacoes), m['id'], veredito, seg, m['desc'][:64]), flush=True)
            res.append({'id': m['id'], 'arquivo': rel, 'desc': m['desc'],
                        'veredito': veredito, 'segundos': round(seg, 1),
                        'pego_por': '' if ok else log[-500:]})
        finally:
            # Restauracao BYTE A BYTE (nao por reescrita de texto).
            io.open(alvo, 'wb').write(original)
            depois = io.open(alvo, 'rb').read()
            if sha_norm(depois) != sha_antes:
                raise SystemExit('RESTAURACAO FALHOU (conteudo) em %s' % rel)
            if depois != original:
                raise SystemExit('RESTAURACAO FALHOU (bytes) em %s' % rel)
            agora = git_sujo(rel)
            if agora != sujo_antes[rel]:
                raise SystemExit(
                    'RESTAURACAO FALHOU (git status) em %s: %r != %r'
                    % (rel, agora, sujo_antes[rel]))
            em_voo_gravar([e for e in em_voo_ler() if e['id'] != m['id']])

    io.open(os.path.join(RAIZ, '.mut', saida), 'w', encoding='utf-8').write(
        json.dumps(res, ensure_ascii=False, indent=2))

    print('\n=== RESUMO %s ===' % saida)
    for r in res:
        print('  %-6s %-22s %-12s %s' % (r['id'], r['arquivo'].split('/')[-1],
                                         r['veredito'], r['desc'][:60]))
    vivas = [r for r in res if r['veredito'] == 'SOBREVIVEU']
    print('  --> %d mutacoes | %d MORTAS | %d SOBREVIVERAM | %d ancora extinta' % (
        len(res),
        sum(1 for r in res if r['veredito'] == 'MORTA'),
        len(vivas),
        sum(1 for r in res if str(r['veredito']).startswith('ANCORA'))))

    if em_voo_ler() != []:
        raise SystemExit('r6_em_voo_core_app.json nao ficou vazio')
    print('  registro em voo vazio: OK')
    for rel, antes in sujo_antes.items():
        if git_sujo(rel) != antes:
            raise SystemExit('git status de %s mudou ao longo do lote' % rel)
    print('  git status identico ao inicio do lote: OK')


if __name__ == '__main__':
    main()
