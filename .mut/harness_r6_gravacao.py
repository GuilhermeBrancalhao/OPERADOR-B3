# -*- coding: utf-8 -*-
"""Harness de auto-mutacao do lote GRAVACAO (onda 9, resposta a R5 secao A.4).

Diferencas em relacao a `.mut/harness_r6.py`, e as duas primeiras vem do
defeito que o proprio auditor da R5 registrou contra si:

  1. RESTAURACAO POR BYTES. O harness da R5 restaurou o CONTEUDO certo com os
     BYTES errados (`newline=''` grava LF num working tree CRLF), e 14
     arquivos ficaram marcados `M` pelo `git status` sem uma unica diferenca
     de conteudo. Aqui o original e guardado como BYTES e devolvido como
     BYTES: a restauracao e exata por construcao.
  2. AS DUAS CONFERENCIAS, nao uma. sha256 do conteudo NORMALIZADO (prova que
     nenhuma mutacao ficou para tras, e nao mente onde `git diff` mente por
     causa de `core.autocrlf=true`) E `git status --porcelain` dos arquivos do
     lote antes/depois (prova que nenhum byte alheio mudou). Sao
     complementares; rodar so uma deixa buraco.
  3. VEREDITO CONTRA A LINHA DE BASE DO MOMENTO. Ha outros builders mexendo
     nesta mesma arvore agora, e a suite tem falha alheia em voo. Uma mutacao
     so e MORTA se fizer falhar um teste que NAO estava falhando na linha de
     base medida imediatamente antes do lote — e o harness registra QUAL
     teste a matou, para que qualquer atribuicao errada fique visivel.
  4. Varias substituicoes por mutacao (`edits`), porque desfazer uma correcao
     estrutural (M01) exige tocar quatro pontos coerentes entre si.

Uso: python .mut/harness_r6_gravacao.py .mut/r6_gravacao.json .mut/r6_gravacao_res.json
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
EM_VOO = os.path.join(RAIZ, '.mut', 'r6_em_voo_gravacao.json')
CR, LF = chr(13), chr(10)

ARQUIVOS_DO_LOTE = [
    'fluxopro/gravacao/gravador.py',
    'fluxopro/gravacao/catalogo.py',
    'fluxopro/gravacao/formato.py',
    'fluxopro/dados/leitor_gravacao.py',
]


def ler_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def escrever_bytes(p, b):
    with open(p, 'wb') as f:
        f.write(b)


def sha_norm(b: bytes) -> str:
    return hashlib.sha256(b.replace((CR + LF).encode(), LF.encode())).hexdigest()


def sha_bruto(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_status_do_lote() -> str:
    p = subprocess.run(['git', 'status', '--porcelain', '--'] + ARQUIVOS_DO_LOTE,
                       cwd=RAIZ, capture_output=True, text=True)
    return p.stdout.strip()


def em_voo_ler():
    if os.path.exists(EM_VOO):
        return json.load(io.open(EM_VOO, encoding='utf-8'))
    return []


def em_voo_gravar(l):
    io.open(EM_VOO, 'w', encoding='utf-8').write(json.dumps(l, ensure_ascii=False, indent=2))


_RE_FALHA = re.compile(r'^FAILED (\S+)', re.M)


def rodar_suite():
    """Suite INTEIRA. Devolve (conjunto de node ids que falharam, segundos)."""
    t0 = time.time()
    p = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q', '--no-header',
                        '--tb=no', '-rf', '-p', 'no:cacheprovider'],
                       cwd=RAIZ, capture_output=True, text=True)
    saida = (p.stdout or '') + (p.stderr or '')
    return set(_RE_FALHA.findall(saida)), time.time() - t0


def aplicar(texto: str, edits, eol: str) -> str:
    """As ancoras da tabela sao escritas com LF; o working tree deste repo e
    CRLF. Traduzir aqui (em vez de guardar CRLF na tabela) e o que impede a
    tabela de so casar por acidente de fim de linha."""
    for de, para in edits:
        if eol != LF:
            de = de.replace(LF, eol)
            para = para.replace(LF, eol)
        n = texto.count(de)
        if n != 1:
            raise AssertionError('ancora com %d ocorrencias: %r' % (n, de[:70]))
        texto = texto.replace(de, para)
    return texto


def main():
    tabela = sys.argv[1]
    saida_json = sys.argv[2]
    mutacoes = json.load(io.open(os.path.join(RAIZ, tabela), encoding='utf-8'))

    status_inicial = git_status_do_lote()
    print('git status do lote (inicial):\n%s\n' % (status_inicial or '(limpo)'), flush=True)

    print('linha de base: rodando a suite inteira...', flush=True)
    base_falhas, seg = rodar_suite()
    print('linha de base: %d falha(s) alheia(s) em %.0fs -> %s\n'
          % (len(base_falhas), seg, sorted(base_falhas) or '(nenhuma)'), flush=True)

    res = []
    for i, m in enumerate(mutacoes, 1):
        alvo = os.path.join(RAIZ, m['arquivo'].replace('/', os.sep))
        original = ler_bytes(alvo)
        sha_b, sha_n = sha_bruto(original), sha_norm(original)
        texto = original.decode('utf-8')

        # registro EM VOO antes de qualquer escrita
        reg = em_voo_ler()
        reg.append({'id': m['id'], 'arquivo': m['arquivo'],
                    'sha256_bruto_original': sha_b, 'sha256_norm_original': sha_n,
                    'aplicada_em': time.strftime('%Y-%m-%dT%H:%M:%S')})
        em_voo_gravar(reg)
        try:
            eol = CR + LF if (CR + LF) in texto else LF
            mutado = aplicar(texto, m['edits'], eol)
            assert mutado != texto, 'mutacao nao alterou o arquivo: ' + m['id']
            escrever_bytes(alvo, mutado.encode('utf-8'))
            falhas, seg = rodar_suite()
            novas = sorted(falhas - base_falhas)
            veredito = 'MORTA' if novas else 'SOBREVIVEU'
            print('[%2d/%d] %-5s %-10s (%.0fs) %s' % (i, len(mutacoes), m['id'], veredito, seg,
                                                      m['desc'][:62]), flush=True)
            if novas:
                print('         morta por: %s' % ' | '.join(n.split('::')[-1] for n in novas[:4]), flush=True)
            res.append({'id': m['id'], 'arquivo': m['arquivo'], 'desc': m['desc'],
                        'veredito': veredito, 'segundos': round(seg, 1),
                        'mortas_por': novas[:6], 'n_testes_que_pegaram': len(novas)})
        finally:
            escrever_bytes(alvo, original)
            devolvido = ler_bytes(alvo)
            if sha_bruto(devolvido) != sha_b or sha_norm(devolvido) != sha_n:
                raise SystemExit('RESTAURACAO FALHOU em %s' % m['arquivo'])
            em_voo_gravar([e for e in em_voo_ler() if e['id'] != m['id']])

    io.open(os.path.join(RAIZ, saida_json), 'w', encoding='utf-8').write(
        json.dumps(res, ensure_ascii=False, indent=2))

    status_final = git_status_do_lote()
    print('\n=== RESUMO ===')
    for r in res:
        print('  %-5s %-10s %-2s  %s' % (r['id'], r['veredito'], r['n_testes_que_pegaram'], r['desc'][:64]))
    print('\nmortas=%d  sobreviveram=%d  de %d'
          % (sum(1 for r in res if r['veredito'] == 'MORTA'),
             sum(1 for r in res if r['veredito'] == 'SOBREVIVEU'), len(res)))
    assert em_voo_ler() == [], 'r6_em_voo_gravacao.json nao ficou vazio'
    print('registro em voo vazio: OK')
    print('git status do lote (final):\n%s' % (status_final or '(limpo)'))
    assert status_final == status_inicial, 'git status do lote MUDOU (byte alheio tocado)'
    print('git status identico ao inicial: OK')


if __name__ == '__main__':
    main()
