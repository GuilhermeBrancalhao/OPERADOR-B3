# -*- coding: utf-8 -*-
"""Monta a tabela de mutacoes NOVAS da R6 e confere cada ancora contra HEAD
(nao contra o working tree: ha mutacao em voo do lote de re-mutacao)."""
import io, json, os, subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def head(p):
    r = subprocess.run(['git', 'show', 'HEAD:' + p], cwd=RAIZ,
                       capture_output=True, text=True, encoding='utf-8')
    return r.stdout


GRAV = 'fluxopro/gravacao/gravador.py'
CAT = 'fluxopro/gravacao/catalogo.py'
FMT = 'fluxopro/gravacao/formato.py'
BAR = 'fluxopro/core/barramento.py'
REL = 'fluxopro/core/relogio.py'
LEI = 'fluxopro/dados/leitor_gravacao.py'
REP = 'fluxopro/dados/replay.py'
DET = 'fluxopro/microestrutura/detectores.py'
MT5 = 'fluxopro/dados/mt5.py'
SIN = 'fluxopro/motor/sinais.py'
INF = 'fluxopro/microestrutura/inferencia_mbp.py'
SAI = 'fluxopro/app/saida.py'

M = [
    # ---------- gravacao/ : a 6a casa e a indexacao por intervalo ----------
    dict(id='G01', arquivo=GRAV,
         desc='6a CASA: troca a lista de horarios pelo min/max incremental (a CORRECAO). Verde = nenhum teste distingue O(eventos) de O(1)',
         de='        self._horarios.setdefault((symbol, dia), []).append(evento.timestamp_ns)',
         para='''        _hs = self._horarios.setdefault((symbol, dia), [])
        _ts = evento.timestamp_ns
        if not _hs:
            _hs.extend((_ts, _ts))
        else:
            if _ts < _hs[0]:
                _hs[0] = _ts
            if _ts > _hs[1]:
                _hs[1] = _ts'''),
    dict(id='G02', arquivo=GRAV,
         desc='rotacao de dia aceita voltar no tempo: evento atrasado fecha o dia corrente e reabre o anterior',
         de='            if dia_atual is not None and data_evento > dia_atual:',
         para='            if dia_atual is not None and data_evento != dia_atual:'),
    dict(id='G03', arquivo=GRAV,
         desc='n_eventos_total do meta.json deixa de somar tudo (conta so o tipo mais frequente)',
         de='            "n_eventos_total": sum(contagens.values()),',
         para='            "n_eventos_total": max(contagens.values()) if contagens else 0,'),
    dict(id='C01', arquivo=CAT,
         desc='INDEXACAO POR INTERVALO: --de/--ate passam a ser lidos no fuso de Sao Paulo (-03) em vez de UTC',
         de='            dt_inicio = datetime.combine(data, hora_inicio, tzinfo=timezone.utc)',
         para='            dt_inicio = datetime.combine(data, hora_inicio, tzinfo=timezone(timedelta(hours=-3)))',
         pre_de='from datetime import date, datetime, time, timezone',
         pre_para='from datetime import date, datetime, time, timedelta, timezone'),
    dict(id='C02', arquivo=CAT,
         desc='integridade: arquivo AUSENTE passa a contar como valido',
         de='''            if caminho is None:
                resultado[nome_base] = False
                continue''',
         para='''            if caminho is None:
                resultado[nome_base] = True
                continue'''),
    dict(id='C03', arquivo=CAT,
         desc='hash do catalogo passa a incluir o cabecalho (divergencia sistematica contra o Gravador)',
         de='        next(leitor, None)  # cabecalho nao entra no hash (Gravador so hasheia dados)',
         para='        pass  # cabecalho ENTRA no hash'),
    dict(id='C04', arquivo=CAT,
         desc='escanear le so o primeiro simbolo (gravacao multi-simbolo perde os demais em silencio)',
         de='''        for symbol_dir in sorted(self._base.iterdir()):
            if not symbol_dir.is_dir():
                continue''',
         para='''        for symbol_dir in sorted(self._base.iterdir())[:1]:
            if not symbol_dir.is_dir():
                continue'''),
    dict(id='F01', arquivo=FMT,
         desc='formato: decodificar_niveis perde n_orders (usa qty no lugar)',
         de='        niveis.append(BookLevel(price=int(preco_s), qty=int(qty_s), n_orders=int(n_s)))',
         para='        niveis.append(BookLevel(price=int(preco_s), qty=int(qty_s), n_orders=int(qty_s)))'),
    dict(id='F02', arquivo=FMT,
         desc='formato: linha_para_trade troca comprador e vendedor na volta do disco',
         de='''        buyer_broker=linha.get("buyer_broker") or "",
        seller_broker=linha.get("seller_broker") or "",
    )


def snapshot_para_linha''',
         para='''        buyer_broker=linha.get("seller_broker") or "",
        seller_broker=linha.get("buyer_broker") or "",
    )


def snapshot_para_linha'''),
    # ---------- core/ ----------
    dict(id='B01', arquivo=BAR,
         desc='barramento: publicar itera uma COPIA (a CORRECAO de reentrancia). Verde = reentrancia nao e prendida em direcao nenhuma',
         de='        for assinatura in self._assinantes.get(type(evento), ()):\n            assinatura.callback(evento)',
         para='        for assinatura in list(self._assinantes.get(type(evento), ())):\n            assinatura.callback(evento)'),
    dict(id='B02', arquivo=BAR,
         desc='barramento: excecao de assinante engolida (o resto da cadeia continua como se nada tivesse acontecido)',
         de='        for assinatura in self._assinantes.get(type(evento), ()):\n            assinatura.callback(evento)',
         para='        for assinatura in self._assinantes.get(type(evento), ()):\n            try:\n                assinatura.callback(evento)\n            except Exception:\n                pass'),
    dict(id='B03', arquivo=BAR,
         desc='barramento: ordenacao por prioridade deixa de acontecer em assinar (ordem passa a ser a de inscricao pura)',
         de='        lista.append(assinatura)\n        lista.sort(key=lambda a: (a.prioridade, a.ordem))',
         para='        lista.append(assinatura)'),
    dict(id='RL1', arquivo=REL,
         desc='relogio: RelogioReal troca monotonic_ns por time_ns (volta no tempo em ajuste de NTP)',
         de='    def agora_ns(self) -> int:\n        return time.monotonic_ns()',
         para='    def agora_ns(self) -> int:\n        return time.time_ns()'),
    dict(id='RL2', arquivo=REL,
         desc='relogio: replay recusa timestamp IGUAL (a docstring diz que empate e comum e aceito de proposito)',
         de='        if timestamp_ns < self._atual_ns:',
         para='        if timestamp_ns <= self._atual_ns:'),
    # ---------- dados/ ----------
    dict(id='L01', arquivo=LEI,
         desc='leitor: borda superior do recorte vira exclusiva (evento no ts_fim exato some do replay)',
         de='        if self._ts_fim is not None and ts > self._ts_fim:',
         para='        if self._ts_fim is not None and ts >= self._ts_fim:'),
    dict(id='L02', arquivo=LEI,
         desc='leitor: desempate troca tipo<->indice (deterministico ainda, contrato de ordem por tipo quebrado)',
         de='        combinados.sort(key=lambda item: (item[0], item[1], item[2]))\n        return [item[3] for item in combinados]',
         para='        combinados.sort(key=lambda item: (item[0], item[2], item[1]))\n        return [item[3] for item in combinados]'),
    dict(id='L03', arquivo=LEI,
         desc='leitor: base do catalogo de verificacao sobe um nivel so (catalogo vazio => integridade nunca reprova)',
         de='        catalogo = self._catalogo or Catalogo(self._entrada.diretorio.parent.parent)',
         para='        catalogo = self._catalogo or Catalogo(self._entrada.diretorio.parent)'),
    dict(id='P01', arquivo=REP,
         desc='replay: trade e delta trocam a prioridade no empate de timestamp (constantes de origem invertidas)',
         de='_ORIGEM_TRADE = 0\n_ORIGEM_DELTA = 1',
         para='_ORIGEM_TRADE = 1\n_ORIGEM_DELTA = 0'),
    # ---------- codigo NOVO da onda 8 ----------
    dict(id='O01', arquivo=DET,
         desc='ONDA8 dedup: o cursor da varredura AVANCA ao remover (quebra a invariante que permite esvaziar em O(n) escritas)',
         de='''            if self._expirado(self._itens[chave]):
                self._remover(chave)''',
         para='''            if self._expirado(self._itens[chave]):
                self._remover(chave)
                self._cursor = i + 1'''),
    dict(id='O02', arquivo=DET,
         desc='ONDA8 dedup: _remover deixa de tratar "a chave e a ultima" (indice corrompido ao remover a cauda)',
         de='''        ultima = self._chaves.pop()
        if ultima != chave:
            self._chaves[i] = ultima
            self._itens[ultima].pos = i''',
         para='''        ultima = self._chaves.pop()
        self._chaves[i] = ultima
        self._itens[ultima].pos = i'''),
    dict(id='O03', arquivo=DET,
         desc='ONDA8 dedup: RNG de despejo vira o modulo global random (nao mais o Random proprio semeado)',
         de='        self._remover(self._chaves[_SORTEIO_DESPEJO.randrange(len(self._chaves))])',
         para='        self._remover(self._chaves[random.randrange(len(self._chaves))])'),
    dict(id='O04', arquivo=MT5,
         desc='ONDA8 relogio: janela deixa de ser estritamente monotonica (<= vira <): amostras iguais empilham',
         de='        while janela and janela[-1][1] <= estimativa:',
         para='        while janela and janela[-1][1] < estimativa:'),
    dict(id='O05', arquivo=MT5,
         desc='ONDA8 relogio: _resetar nao limpa a janela (amostras do referencial ANTIGO sobrevivem ao reset)',
         de='''        self._janela.clear()
        self._sincronizado = True''',
         para='''        self._sincronizado = True'''),
    dict(id='O06', arquivo=MT5,
         desc='ONDA8 relogio: poda por IDADE deixa de rodar (a janela so encolhe pelo teto duro: a catraca volta parcialmente)',
         de='        while len(janela) > 1 and janela[0][0] < limite:\n            janela.popleft()',
         para='        pass'),
    dict(id='O07', arquivo=SIN,
         desc='ONDA8 magnitude: _n_visto conta ANTES do filtro de negocio unico (piso de amostras satisfeito por amostra descartada)',
         de='''        if magnitude <= cfg.fator_dominio_trade_unico * maior_negocio:
            return
        capacidade = cfg.tamanho_topo_magnitude
        self._n_visto += 1''',
         para='''        self._n_visto += 1
        if magnitude <= cfg.fator_dominio_trade_unico * maior_negocio:
            return
        capacidade = cfg.tamanho_topo_magnitude'''),
    dict(id='O08', arquivo=INF,
         desc='ONDA8 heap: teto de compactacao vira 1x len(vivos) (compacta quase a cada insercao: O(n) por evento volta)',
         de='self._limiar_heap_bid = max(_PISO_TETO_HEAP, 2 * len(vivos))',
         para='self._limiar_heap_bid = max(_PISO_TETO_HEAP, 1 * len(vivos))'),
    # ---------- app/ ----------
    dict(id='S01', arquivo=SAI,
         desc='saida: marca [OBS]/[INF] usa > em vez de >= (confianca exatamente 1.0 passa a imprimir como INFERIDA)',
         de='    if confianca >= CONFIANCA_OBSERVADO:',
         para='    if confianca > CONFIANCA_OBSERVADO:'),
]

ok, ruim, cache = [], [], {}
for m in M:
    p = m['arquivo']
    if p not in cache:
        cache[p] = head(p)
    n = cache[p].count(m['de'])
    if 'pre_de' in m and cache[p].count(m['pre_de']) != 1:
        ruim.append((m['id'], p, 'pre_de x%d' % cache[p].count(m['pre_de'])))
        continue
    if n == 1:
        ok.append(m)
    else:
        ruim.append((m['id'], p, 'de x%d' % n))

print('ancoras OK:', len(ok), 'de', len(M))
for r in ruim:
    print('  PROBLEMA', r)
io.open(os.path.join(RAIZ, '.mut', 'r6_novas.json'), 'w', encoding='utf-8').write(
    json.dumps(ok, ensure_ascii=False, indent=2))
print('gravado .mut/r6_novas.json')
