"""Auto-mutação da correção do heap (R5).

Protocolo:
  * grava `.mut/r5_em_voo.json` ANTES de escrever no arquivo de produção;
  * restaura no `finally`, sempre;
  * confere sha256 do conteúdo NORMALIZADO (CRLF -> LF) contra o original,
    porque neste repo `git diff` e comparação crua contra o blob de HEAD já
    foram provados não confiáveis (core.autocrlf=true);
  * aborta tudo se alguma restauração não bater.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys

RAIZ = r'C:\Users\Usuário\Desktop\CLAUDE\fluxo_pro'
EM_VOO = os.path.join(RAIZ, '.mut', 'r5_em_voo.json')
INF = os.path.join(RAIZ, 'fluxopro', 'microestrutura', 'inferencia_mbp.py')
LIVRO = os.path.join(RAIZ, 'fluxopro', 'microestrutura', 'livro_mbo.py')
CR, LF = chr(13), chr(10)


def ler(p: str) -> str:
    return io.open(p, encoding='utf-8').read()


def escrever(p: str, s: str) -> None:
    io.open(p, 'w', encoding='utf-8', newline=CR + LF).write(s)


def sha(s: str) -> str:
    return hashlib.sha256(s.replace(CR + LF, LF).encode('utf-8')).hexdigest()


MUTACOES = [
    # (id, arquivo, descrição, de, para, teste_esperado)
    (
        'M1', INF, 'remove a dedup do heap de BIDS (volta o push incondicional)',
        """            if price in self._precos_no_heap_bid:
                return
            heapq.heappush(self._heap_bids, -price)""",
        """            heapq.heappush(self._heap_bids, -price)""",
        'test_recarga_do_mesmo_nivel_nao_gera_TRABALHO_no_heap',
    ),
    (
        'M2', INF, 'remove a dedup do heap de ASKS',
        """            if price in self._precos_no_heap_ask:
                return
            heapq.heappush(self._heap_asks, price)""",
        """            heapq.heappush(self._heap_asks, price)""",
        'test_recarga_do_mesmo_nivel_nao_gera_TRABALHO_no_heap',
    ),
    (
        'M3', INF, 'remove o TETO (nunca compacta o lado da compra)',
        """            if len(self._heap_bids) > self._limiar_heap_bid:
                self._compactar_heap(Side.BUY)""",
        """            pass  # MUTACAO: sem teto""",
        'test_heap_de_precos_tem_teto_no_numero_de_niveis_vivos',
    ),
    (
        'M4', INF, 'volta a poda SO pela cabeca (espelho nunca solta o preco)',
        """            heapq.heappop(self._heap_bids)
            # Sai do espelho junto: sem isto o nível que RESSUSCITA nunca mais
            # seria republicado e o topo do livro ficaria errado em silêncio —
            # o mesmo bug que a marca `no_heap` do `LivroMBO` já pagou uma vez.
            self._precos_no_heap_bid.discard(price)""",
        """            heapq.heappop(self._heap_bids)""",
        'test_topo_continua_correto_depois_de_mil_recargas',
    ),
    (
        'M5', INF, 'espelho do ASK nunca solta o preco no heappop',
        """            heapq.heappop(self._heap_asks)
            self._precos_no_heap_ask.discard(price)""",
        """            heapq.heappop(self._heap_asks)""",
        'test_topo_de_ask_continua_correto_depois_de_mil_recargas',
    ),
    (
        'M6', INF, 'compactacao mantem os niveis MORTOS (filtro invertido p/ >= 0)',
        """                if self._qty_por_nivel.get((Side.BUY, p), 0) > 0
            ]
            heapq.heapify(vivos)
            self._heap_bids = vivos""",
        """                if self._qty_por_nivel.get((Side.BUY, p), 0) >= 0
            ]
            heapq.heapify(vivos)
            self._heap_bids = vivos""",
        'test_heap_de_precos_tem_teto_no_numero_de_niveis_vivos',
    ),
    (
        'M7', INF, 'compactacao DESCARTA os niveis vivos (mantem so os mortos)',
        """                if self._qty_por_nivel.get((Side.BUY, p), 0) > 0
            ]""",
        """                if self._qty_por_nivel.get((Side.BUY, p), 0) <= 0
            ]""",
        'test_compactacao_do_heap_preserva_todos_os_niveis_vivos',
    ),
    (
        'M8', INF, 'piso do teto sobe a 10**9: compactacao nunca dispara',
        '_PISO_TETO_HEAP = 64',
        '_PISO_TETO_HEAP = 10**9',
        'test_heap_de_precos_tem_teto_no_numero_de_niveis_vivos',
    ),
    (
        'M9', LIVRO, 'LivroMBO: remove a compactacao do lado da compra',
        """                if len(self._heap_bids) > self._limiar_heap_bid:
                    self._compactar_heap(Side.BUY)""",
        """                pass  # MUTACAO: sem teto""",
        'test_heap_nao_cresce_com_preco_distinto_enquanto_o_topo_fica_ocupado',
    ),
    (
        'M10', LIVRO, 'LivroMBO: compactacao nao desmarca `no_heap` do nivel morto',
        """            else:
                nivel.no_heap = False
        heapq.heapify(vivos)""",
        """        heapq.heapify(vivos)""",
        'test_nivel_descartado_pela_compactacao_volta_ao_topo_se_ressuscitar',
    ),
    (
        'M11', LIVRO, 'LivroMBO: compactacao descarta os niveis VIVOS',
        """            if nivel.qty_total > 0:
                vivos.append(entrada)""",
        """            if nivel.qty_total <= 0:
                vivos.append(entrada)""",
        'test_compactacao_preserva_a_ordem_de_todos_os_niveis_vivos',
    ),
    (
        'M12', LIVRO, 'LivroMBO: remove a compactacao do lado da venda',
        """                if len(self._heap_asks) > self._limiar_heap_ask:
                    self._compactar_heap(Side.SELL)""",
        """                pass  # MUTACAO: sem teto""",
        'test_heap_de_asks_tambem_e_compactado',
    ),
]

ALVOS = 'tests/test_micro_inferencia.py tests/test_micro_livro.py'


def rodar_pytest(k: str | None) -> tuple[int, str]:
    cmd = [sys.executable, '-m', 'pytest'] + ALVOS.split() + ['-q', '--no-header', '-x']
    if k:
        cmd += ['-k', k]
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def main() -> None:
    originais = {INF: ler(INF), LIVRO: ler(LIVRO)}
    shas = {p: sha(s) for p, s in originais.items()}
    resultados = []

    for mid, arq, desc, de, para, teste in MUTACOES:
        atual = ler(arq)
        if de not in atual:
            resultados.append((mid, desc, teste, 'NAO APLICOU (padrao ausente)'))
            print(f'{mid}: PADRAO AUSENTE — {desc}')
            continue
        # 1) registrar ANTES de escrever
        with io.open(EM_VOO, 'w', encoding='utf-8') as fh:
            json.dump({'id': mid, 'arquivo': arq, 'descricao': desc,
                       'sha256_original_normalizado': shas[arq]}, fh, ensure_ascii=False, indent=2)
        try:
            escrever(arq, atual.replace(de, para, 1))
            codigo, saida = rodar_pytest(teste)
            if codigo == 0:
                veredito = '*** SOBREVIVEU ***'
            else:
                linha = [ln for ln in saida.splitlines() if ln.startswith('FAILED')]
                veredito = 'MORREU: ' + (linha[0].split('::')[-1].split(' ')[0] if linha
                                         else 'falhou sem nome')
            resultados.append((mid, desc, teste, veredito))
            print(f'{mid}: {veredito} — {desc}')
        finally:
            escrever(arq, originais[arq])
            conferido = sha(ler(arq))
            if conferido != shas[arq]:
                print(f'!!! RESTAURACAO FALHOU em {arq}: {conferido} != {shas[arq]}')
                raise SystemExit(2)
            os.remove(EM_VOO)

    print('\n| # | mutação | teste que a mata | veredito |')
    print('|---|---------|------------------|----------|')
    for mid, desc, teste, ver in resultados:
        print(f'| {mid} | {desc} | `{teste}` | {ver} |')

    for p, s in originais.items():
        assert sha(ler(p)) == shas[p], p
    print('\nsha256 final confere nos 2 arquivos de producao (normalizado CRLF->LF).')
    print('em_voo existe?', os.path.exists(EM_VOO))


if __name__ == '__main__':
    main()
