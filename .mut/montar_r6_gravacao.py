# -*- coding: utf-8 -*-
"""Monta `.mut/r6_gravacao.json` — a tabela de auto-mutacao do lote gravacao."""
import io, json, os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = 'fluxopro/gravacao/gravador.py'
C = 'fluxopro/gravacao/catalogo.py'
L = 'fluxopro/dados/leitor_gravacao.py'

M = []


def mut(id_, arquivo, desc, edits):
    M.append({'id': id_, 'arquivo': arquivo, 'desc': desc, 'edits': edits})


# --------------------------------------------------------------- M01
# Desfaz a correcao inteira: volta a lista de timestamps (a mutacao G01 da
# R5, so que na direcao contraria — ela APLICOU a correcao e a suite ficou
# verde; aqui se remove a correcao e o teste de retencao tem de pegar).
mut('M01', G, 'volta a lista de timestamps por evento (a 6a casa reaberta)', [
    ["""        # DOIS escalares por (symbol, dia) — nunca a lista de timestamps.
        # Ver "Retenção em memória" no docstring do módulo.
        self._hora_inicio_ns: dict[tuple[str, date], int] = {}
        self._hora_fim_ns: dict[tuple[str, date], int] = {}
""",
     """        self._horarios: dict[tuple[str, date], list[int]] = {}
"""],
    ["""        # min/max INCREMENTAIS. Dois `int` por dia aberto, não um por evento.
        ts = evento.timestamp_ns
        inicio = self._hora_inicio_ns.get(chave_dia)
        if inicio is None or ts < inicio:
            self._hora_inicio_ns[chave_dia] = ts
        fim = self._hora_fim_ns.get(chave_dia)
        if fim is None or ts > fim:
            self._hora_fim_ns[chave_dia] = ts
""",
     """        self._horarios.setdefault(chave_dia, []).append(evento.timestamp_ns)
"""],
    ["""            "hora_inicio_ns": self._hora_inicio_ns.get((symbol, dia)),
            "hora_fim_ns": self._hora_fim_ns.get((symbol, dia)),
""",
     """            "hora_inicio_ns": min(self._horarios.get((symbol, dia)) or [None]),
            "hora_fim_ns": max(self._horarios.get((symbol, dia)) or [None]),
"""],
    ["""        self._hora_inicio_ns.pop((symbol, dia), None)
        self._hora_fim_ns.pop((symbol, dia), None)
""",
     """        self._horarios.pop((symbol, dia), None)
"""],
])

# --------------------------------------------------------------- M02..M04
mut('M02', G, 'min incremental com a comparacao INVERTIDA (ts > inicio)', [
    ['        if inicio is None or ts < inicio:', '        if inicio is None or ts > inicio:'],
])
mut('M03', G, 'max incremental com a comparacao INVERTIDA (ts < fim)', [
    ['        if fim is None or ts > fim:', '        if fim is None or ts < fim:'],
])
mut('M04', G, 'hora_inicio sobrescrita a cada evento (sem teste de menor)', [
    ['        if inicio is None or ts < inicio:', '        if True:'],
])
mut('M05', G, 'rotacao de dia nao limpa hora_inicio/hora_fim (vaza p/ o dia seguinte)', [
    ["""        self._hora_inicio_ns.pop((symbol, dia), None)
        self._hora_fim_ns.pop((symbol, dia), None)
""",
     """        pass
"""],
])

# --------------------------------------------------------------- durabilidade
mut('M06', G, 'checkpoint periodico do meta.json desligado', [
    ['        if self._meta_a_cada > 0 and self._desde_meta[chave_dia] >= self._meta_a_cada:',
     '        if False:'],
])
mut('M07', G, 'checkpoint nao registra n_linhas_hasheadas', [
    ["""            n_linhas[nome] = arq.n_linhas

        self._gravar_meta(symbol, dia, hashes, n_linhas, parcial=True)""",
     """            n_linhas.pop(nome, None)

        self._gravar_meta(symbol, dia, hashes, n_linhas, parcial=True)"""],
])
mut('M08', G, 'checkpoint escreve o meta ANTES do fsync dos CSVs', [
    ["""            arq.handle.flush()
            os.fsync(arq.handle.fileno())
            arq.n_desde_fsync = 0
            nome = formato.NOMES_ARQUIVO[tipo]""",
     """            nome = formato.NOMES_ARQUIVO[tipo]"""],
])
mut('M09', G, 'meta.json escrito sem troca atomica (deixa o .tmp para tras)', [
    ['    os.replace(tmp, caminho)', '    caminho.write_bytes(tmp.read_bytes())'],
])
mut('M10', G, 'retomada apos crash nao semeia o hasher com o que ja estava no disco', [
    ['        if not novo:\n            hasher, n_linhas = _hash_e_contar_existente(caminho)',
     '        if False:\n            hasher, n_linhas = _hash_e_contar_existente(caminho)'],
])
mut('M11', C, 'hash de prefixo com off-by-one (>= vira >)', [
    ['            if n_linhas is not None and lidas >= n_linhas:',
     '            if n_linhas is not None and lidas > n_linhas:'],
])
mut('M12', C, 'verificacao ignora n_linhas_hasheadas e hasheia o arquivo inteiro', [
    ['            if n_linhas is not None and lidas >= n_linhas:', '            if False:'],
])

# --------------------------------------------------------------- leitor
mut('M13', L, 'leitor volta a materializar a janela inteira (o gemeo de 37 GB)', [
    ["""        fluxos = [
            self._fluxo_de_um_arquivo(tipo)
            for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura)
        ]
        ultima: tuple[int, int, int] | None = None
        for chave, evento in heapq.merge(*fluxos, key=_CHAVE):
            if ultima is not None and chave < ultima:
                raise GravacaoForaDeOrdemError(
                    f"{self._entrada.symbol} {self._entrada.data.isoformat()}: "
                    f"evento {chave} depois de {ultima} — desordem maior que a "
                    f"janela de {_JANELA_REORDENACAO} eventos; o replay nao "
                    f"seria deterministico"
                )
            ultima = chave
            yield evento""",
     """        combinados = []
        for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura):
            caminho = self._entrada.arquivo(formato.NOMES_ARQUIVO[tipo])
            for indice, evento in enumerate(_ler_arquivo(caminho, tipo)):
                if not self._dentro_do_intervalo(evento.timestamp_ns):
                    continue
                combinados.append((evento.timestamp_ns, _ORDEM_TIPO[tipo], indice, evento))
        combinados.sort(key=lambda item: (item[0], item[1], item[2]))
        return iter([item[3] for item in combinados])"""],
])
mut('M14', L, 'chave do merge perde o desempate por indice no arquivo', [
    ['heapq.heappush(janela, ((evento.timestamp_ns, ordem, indice), evento))',
     'heapq.heappush(janela, ((evento.timestamp_ns, ordem, 0), evento))'],
])
mut('M15', L, 'guarda de ordem removida (replay fora de ordem publicado em silencio)', [
    ['            if ultima is not None and chave < ultima:', '            if False:'],
])
mut('M16', L, 'janela de reordenacao vai a zero (perde a tolerancia a desordem local)', [
    ['_JANELA_REORDENACAO = 64', '_JANELA_REORDENACAO = 0'],
])
mut('M17', L, 'filtro de intervalo perdido no caminho streaming', [
    ["""            if not self._dentro_do_intervalo(evento.timestamp_ns):
                continue
            heapq.heappush""",
     """            heapq.heappush"""],
])

io.open(os.path.join(RAIZ, '.mut', 'r6_gravacao.json'), 'w', encoding='utf-8').write(
    json.dumps(M, ensure_ascii=False, indent=2))
print('%d mutacoes' % len(M))
