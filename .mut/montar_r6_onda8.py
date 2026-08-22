# -*- coding: utf-8 -*-
"""Junta as tabelas de mutacao dos 5 builders da onda 8 num lote unico, para
re-medir contra a suite INTEIRA o que cada um alegou ter matado.

Fontes:
  .mut/r5_dedup.json, r5_dedup2.json, r5_dedup3.json   (builder 3: dedup)
  .mut/r5_motor.json                                    (builder 4: motor/WINFUT)
  .mut/mutacoes_r5_relogio.json                         (builder 2: relogio MT5)
  .mut/harness_r5_heap.py :: MUTACOES                   (builder 1: heap/5a casa)
  .mut/mutacoes_r5.json                                 (builder 5: testes fracos)

As de `mutacoes_r5.json` que ja foram medidas no lote r4 (N04/N05/X01/X04/X06/
X08/X10/X26/X27/X28) sao puladas aqui para nao pagar duas vezes; as `*-own-*`
e Y10-R5 entram.
"""
import io, json, os, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUT = os.path.join(RAIZ, '.mut')
sys.path.insert(0, MUT)

JA_MEDIDAS = {'N04', 'N05', 'X01', 'X04', 'X06', 'X08', 'X10', 'X26', 'X27', 'X28'}

saida = []

for nome in ('r5_dedup.json', 'r5_dedup2.json', 'r5_dedup3.json',
             'r5_motor.json', 'mutacoes_r5_relogio.json', 'mutacoes_r5.json'):
    caminho = os.path.join(MUT, nome)
    if not os.path.exists(caminho):
        print('AUSENTE:', nome)
        continue
    for m in json.load(io.open(caminho, encoding='utf-8')):
        if 'de' not in m or 'para' not in m:
            continue
        if m.get('id') in JA_MEDIDAS:
            continue
        saida.append({'id': m['id'], 'arquivo': m['arquivo'],
                      'desc': m.get('desc') or m.get('descricao') or '',
                      'de': m['de'], 'para': m['para'], 'origem': nome})

# heap: a tabela vive como tuplas no proprio harness do builder
try:
    import harness_r5_heap as H
    for t in H.MUTACOES:
        mid, arq, desc, de, para = t[0], t[1], t[2], t[3], t[4]
        rel = os.path.relpath(arq, RAIZ).replace(os.sep, '/')
        saida.append({'id': 'H-' + mid, 'arquivo': rel, 'desc': desc,
                      'de': de, 'para': para, 'origem': 'harness_r5_heap.py'})
except Exception as e:
    print('nao consegui extrair a tabela do heap:', type(e).__name__, e)

# confere cada ancora contra HEAD
import subprocess
cache = {}
ok, ruim = [], []
for m in saida:
    p = m['arquivo']
    if p not in cache:
        cache[p] = subprocess.run(['git', 'show', 'HEAD:' + p], cwd=RAIZ,
                                  capture_output=True, text=True, encoding='utf-8').stdout
    n = cache[p].count(m['de'])
    (ok if n == 1 else ruim).append(m if n == 1 else (m['id'], p, n))

print('total juntado:', len(saida), '| ancoras unicas em HEAD:', len(ok))
for r in ruim:
    print('   ANCORA PROBLEMATICA:', r)
io.open(os.path.join(MUT, 'r6_onda8.json'), 'w', encoding='utf-8').write(
    json.dumps(ok, ensure_ascii=False, indent=2))
print('gravado .mut/r6_onda8.json com', len(ok), 'mutacoes')
