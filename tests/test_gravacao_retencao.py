"""Retenção e durabilidade da camada de gravação (defeito R5, `criticas/nucleo_r5.md`
seção A.4 — "A SEXTA CASA" — e A.4.3, o gêmeo no lado da leitura).

POR QUE ESTE ARQUIVO EXISTE, e por que ele não se parece com os outros testes
de gravação: a auditoria R5 aplicou a CORREÇÃO do defeito (mutação `G01`,
trocar a lista de timestamps por `min`/`max` incrementais) e os 574 testes
continuaram verdes. Junto com o fato de que a versão defeituosa também
passava, isso prova algo mais forte que "o defeito não foi pego": **nenhum
teste da suíte era capaz de distinguir a implementação O(número de eventos)
da implementação O(1), nas duas direções.** Quem consertasse não teria como
provar; quem reintroduzisse não seria pego.

O motivo é de escala: toda a suíte de gravação opera com 1, 3, 5 e 10 eventos,
e o regime em que o defeito existe é 10^8 eventos — sete ordens de grandeza
acima. Mas o eixo certo não é escala bruta e sim RETENÇÃO: `len` (e bytes) das
estruturas de instância confrontado com quantas coisas VIVAS elas deveriam
descrever. Uma coleção sadia responde o mesmo número em 1.000 e em 100.000
eventos. É isso que se afirma aqui.

Os números medidos que motivaram o conserto (R5, objeto de produção):
  - `Gravador._horarios`: 44,9 B/evento -> 4,85 GB num pregão de 6 h a
    5.000 ev/s; 9,70 GB a 10.000 ev/s.
  - `AdaptadorLeitorGravacao._eventos_ordenados`: 342 B/evento -> 37 GB para
    RELER o mesmo pregão, tudo antes de publicar o primeiro evento.

E a durabilidade, que é o que transforma o vazamento em perda de dado: o
`meta.json` — sem o qual o `Catalogo` sequer indexa o dia — só era escrito em
`_fechar_dia`, e `_fechar_dia` não tinha chamador periódico. Um crash às 15 h
apagava o pregão inteiro do produto, com os CSVs intactos no disco. Não existe
segunda cópia de histórico de book de WDO/WIN.
"""

from __future__ import annotations

import dataclasses
import gc
import json
import sys
import tracemalloc
from collections import deque
from pathlib import Path

import pytest

import fluxopro.dados.leitor_gravacao as leitor_mod
import fluxopro.gravacao.gravador as gravador_mod
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import (
    AgressorSide,
    BookAction,
    BookDelta,
    BookLevel,
    BookSnapshot,
    Side,
    Trade,
)
from fluxopro.dados.eventos_captura import FalhaCaptura, TipoFalha
from fluxopro.dados.leitor_gravacao import (
    AdaptadorLeitorGravacao,
    GravacaoForaDeOrdemError,
)
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.gravacao.gravador import Gravador

_SYMBOL = "WDOV26"
_DIA_1_TS = 1_700_000_000_000_000_000  # bem no meio de um dia UTC qualquer
_MS = 1_000_000


# =====================================================================
# Instrumentação de retenção
# =====================================================================

_CONTAINERS = (list, tuple, set, frozenset, deque)


def _percorrer(obj, vistos: set[int]):
    """Anda pelo grafo de estado de um objeto, parando onde o estado deixa
    de ser do projeto: desce por dicionários, sequências e dataclasses (que
    é o que `_ArquivoAberto` é), e NÃO desce por handles de arquivo, hashers
    ou `Path` — cujo tamanho é constante e cujos atributos internos não
    dizem nada sobre retenção."""
    if id(obj) in vistos:
        return
    vistos.add(id(obj))
    yield obj
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            yield from _percorrer(chave, vistos)
            yield from _percorrer(valor, vistos)
    elif isinstance(obj, _CONTAINERS):
        for item in obj:
            yield from _percorrer(item, vistos)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for campo in dataclasses.fields(obj):
            yield from _percorrer(getattr(obj, campo.name), vistos)


def _estado_de_instancia(obj, ignorar: frozenset[str]) -> dict:
    return {k: v for k, v in vars(obj).items() if k not in ignorar}


def _itens_retidos(obj, ignorar: frozenset[str]):
    """Tudo que o estado de instância de `obj` mantém vivo, uma vez cada."""
    vistos: set[int] = set()
    for valor in _estado_de_instancia(obj, ignorar).values():
        yield from _percorrer(valor, vistos)


def _elementos_retidos(obj, ignorar: frozenset[str] = frozenset()) -> int:
    """Soma dos `len` de TODA coleção alcançável a partir do estado de
    instância — recursivamente, porque o defeito da 6ª casa era uma `list`
    DENTRO de um `dict`: `len(self._horarios)` valia 1 com um milhão de
    timestamps guardados. Contar só o topo não o veria."""
    return sum(
        len(item) for item in _itens_retidos(obj, ignorar)
        if isinstance(item, (dict,) + _CONTAINERS)
    )


def _bytes_retidos(obj, ignorar: frozenset[str] = frozenset()) -> int:
    return sum(sys.getsizeof(item) for item in _itens_retidos(obj, ignorar))


# O barramento não é estado DO gravador (é injetado, compartilhado com
# analytics, motor e saída); medi-lo aqui misturaria a retenção de outro
# subsistema na conta deste.
_IGNORAR_NO_GRAVADOR = frozenset({"_barramento"})


# =====================================================================
# Fixtures de gravação
# =====================================================================

def _trade(ts_ns: int, trade_id: str = "T", price: int = 10000) -> Trade:
    return Trade(
        timestamp_ns=ts_ns, symbol=_SYMBOL, price=price, qty=5,
        side_agressor=AgressorSide.BUY, trade_id=trade_id,
    )


def _snapshot(ts_ns: int, price: int = 9999) -> BookSnapshot:
    return BookSnapshot(
        timestamp_ns=ts_ns, symbol=_SYMBOL,
        bids=(BookLevel(price, 10, 1),), asks=(BookLevel(price + 2, 8, 1),),
    )


def _delta(ts_ns: int, price: int = 9999) -> BookDelta:
    return BookDelta(
        timestamp_ns=ts_ns, symbol=_SYMBOL, side=Side.BUY,
        action=BookAction.UPDATE, price=price, qty=7, position=0,
    )


def _falha(ts_ns: int, detalhe: str = "x") -> FalhaCaptura:
    return FalhaCaptura(
        timestamp_ns=ts_ns, symbol=_SYMBOL, tipo=TipoFalha.GAP_TICKS, detalhe=detalhe,
    )


def _gravador_com_n_eventos(destino: Path, n: int, meta_a_cada: int = 0) -> Gravador:
    """Publica `n` eventos e devolve o gravador AINDA ABERTO — a retenção que
    importa é a do meio do pregão, não a de depois do `parar()`.
    `fsync_a_cada` alto porque o que se mede aqui é memória, não I/O."""
    barramento = Barramento()
    gravador = Gravador(barramento, destino, fsync_a_cada=10**9, meta_a_cada=meta_a_cada)
    gravador.iniciar()
    for i in range(n):
        barramento.publicar(_trade(_DIA_1_TS + i * _MS, trade_id=f"T{i}"))
    return gravador


def _fechar_handles(gravador: Gravador) -> None:
    """Simula a morte do processo: os arquivos param de ser escritos sem
    `parar()`, ou seja, sem `_fechar_dia`."""
    for arq in list(gravador._arquivos.values()):
        arq.handle.close()


# =====================================================================
# O TESTE QUE A R5 PROVOU NÃO EXISTIR — gravador
# =====================================================================

def test_gravador_retencao_nao_cresce_com_numero_de_eventos(tmp_path):
    """A afirmação central: a retenção do `Gravador` é a MESMA depois de
    1.000, 10.000 e 100.000 eventos do mesmo símbolo e do mesmo dia.

    A grandeza que limita o `len` de cada coleção aqui é SÍMBOLOS × DIAS
    ABERTOS (e, dentro de `_contagens`, os 4 tipos de evento) — nenhuma é
    limitada pelo número de eventos. Um `Gravador` que volte a guardar
    qualquer coisa por evento faz `elementos` crescer com `n` e este teste
    morre; foi exatamente essa distinção que a suíte inteira não sabia
    fazer (mutação `G01` da R5, que aplicou a correção e ficou verde).

    Repare que a contagem é RECURSIVA de propósito: o defeito original era
    `dict[chave] -> list[int]`, cujo `len` de topo é 1 com um milhão de
    timestamps dentro."""
    tamanhos = (1_000, 10_000, 100_000)
    elementos: dict[int, int] = {}
    bytes_: dict[int, int] = {}

    for n in tamanhos:
        gravador = _gravador_com_n_eventos(tmp_path / f"n{n}", n)
        try:
            elementos[n] = _elementos_retidos(gravador, _IGNORAR_NO_GRAVADOR)
            bytes_[n] = _bytes_retidos(gravador, _IGNORAR_NO_GRAVADOR)
        finally:
            _fechar_handles(gravador)

    # (a) contagem de elementos EXATAMENTE igual — 100x mais eventos, mesma
    #     estrutura retida.
    assert len(set(elementos.values())) == 1, (
        f"retencao do Gravador cresce com o numero de eventos: {elementos}"
    )

    # (b) e os bytes também ficam parados. A folga cobre variação de
    #     `getsizeof` de int/str, não crescimento estrutural: no defeito
    #     original o salto de 1.000 para 100.000 eventos era de ~4,4 MB.
    delta = bytes_[tamanhos[-1]] - bytes_[tamanhos[0]]
    assert abs(delta) < 4_096, f"bytes retidos crescem com os eventos: {bytes_}"

    # (c) o número que a auditoria mediu, virado do avesso: era 44,9 B/evento.
    b_por_evento = bytes_[tamanhos[-1]] / tamanhos[-1]
    assert b_por_evento < 1.0, f"{b_por_evento:.2f} B/evento retidos"


def test_gravador_nao_guarda_nenhuma_colecao_indexada_por_evento(tmp_path):
    """Complemento estrutural do teste acima, e mais específico: NENHUMA
    coleção de instância do `Gravador` pode ter `len` da ordem do número de
    eventos. Aqui a asserção é sobre cada coleção individualmente (a soma
    poderia, em tese, esconder uma coleção grande compensada por outra), e
    o teto é generoso — 64 — porque o que se recusa é a ordem de grandeza,
    não um valor exato."""
    n = 20_000
    gravador = _gravador_com_n_eventos(tmp_path, n)
    try:
        grandes = [
            (type(item).__name__, len(item))
            for item in _itens_retidos(gravador, _IGNORAR_NO_GRAVADOR)
            if isinstance(item, (dict,) + _CONTAINERS) and len(item) > 64
        ]
    finally:
        _fechar_handles(gravador)
    assert grandes == [], f"colecao de instancia com len ~ n_eventos: {grandes}"


# =====================================================================
# min/max incrementais continuam CORRETOS
# =====================================================================

def test_hora_inicio_e_fim_com_o_menor_chegando_por_ultimo(tmp_path):
    """O `min`/`max` virou incremental; incremental erra de um jeito que a
    lista não errava — basta uma comparação invertida ou uma atribuição
    incondicional. Este caso é o mais hostil possível para as duas: o MENOR
    timestamp do dia chega DEPOIS de milhares de eventos maiores, e o MAIOR
    chega no meio."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()

    base = _DIA_1_TS + 10_000 * _MS
    for i in range(2_000):
        barramento.publicar(_trade(base + i * _MS, trade_id=f"M{i}"))
    maior = base + 1_000_000 * _MS  # +1.000 s, ainda dentro do mesmo dia UTC
    barramento.publicar(_trade(maior, trade_id="MAIOR"))
    for i in range(2_000):
        barramento.publicar(_trade(base + i * _MS, trade_id=f"N{i}"))
    menor = _DIA_1_TS
    barramento.publicar(_trade(menor, trade_id="MENOR"))  # por ultimo
    gravador.parar()

    meta = json.loads((next((tmp_path / _SYMBOL).iterdir()) / "meta.json").read_text(encoding="utf-8"))
    assert meta["hora_inicio_ns"] == menor
    assert meta["hora_fim_ns"] == maior
    assert meta["n_eventos_total"] == 4_002


def test_hora_inicio_e_fim_consideram_os_quatro_tipos_de_evento(tmp_path):
    """`hora_inicio_ns`/`hora_fim_ns` descrevem o DIA GRAVADO, não o arquivo
    de trades: se um snapshot abre o dia e uma falha de captura o fecha, é
    isso que o meta tem de dizer. A falha importa em especial — é ela que
    prova que existe um buraco, e um meta que a deixe de fora faz o buraco
    parecer estar fora da janela gravada."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()

    barramento.publicar(_trade(_DIA_1_TS + 500 * _MS, trade_id="T"))
    barramento.publicar(_delta(_DIA_1_TS + 800 * _MS))
    barramento.publicar(_snapshot(_DIA_1_TS + 100 * _MS))   # o menor de todos
    barramento.publicar(_falha(_DIA_1_TS + 900 * _MS))      # o maior de todos
    gravador.parar()

    meta = json.loads((next((tmp_path / _SYMBOL).iterdir()) / "meta.json").read_text(encoding="utf-8"))
    assert meta["hora_inicio_ns"] == _DIA_1_TS + 100 * _MS
    assert meta["hora_fim_ns"] == _DIA_1_TS + 900 * _MS
    assert meta["n_eventos_total"] == 4


def test_hora_inicio_e_fim_sao_por_dia_e_nao_vazam_de_um_dia_para_o_outro(tmp_path):
    """A rotação de dia esvazia os acumuladores. Se `_hora_inicio_ns` não
    for esvaziado em `_fechar_dia`, o dia 2 herda a hora de início do dia 1
    e o catálogo passa a descrever uma janela que nunca existiu."""
    um_dia = 24 * 60 * 60 * 1_000_000_000
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()
    barramento.publicar(_trade(_DIA_1_TS, trade_id="D1"))
    barramento.publicar(_trade(_DIA_1_TS + um_dia + 7 * _MS, trade_id="D2"))
    gravador.parar()

    dias = sorted((tmp_path / _SYMBOL).iterdir())
    metas = [json.loads((d / "meta.json").read_text(encoding="utf-8")) for d in dias]
    assert metas[0]["hora_inicio_ns"] == metas[0]["hora_fim_ns"] == _DIA_1_TS
    assert metas[1]["hora_inicio_ns"] == metas[1]["hora_fim_ns"] == _DIA_1_TS + um_dia + 7 * _MS


# =====================================================================
# Durabilidade: meta.json periódico
# =====================================================================

def test_parar_devolve_a_retencao_do_gravador_a_zero(tmp_path):
    """Depois de `parar()` não pode sobrar estado de dia nenhum. Um
    acumulador por dia que não seja esvaziado em `_fechar_dia` transforma o
    `Gravador` num vazamento de longo prazo — mais lento que o da 6ª casa
    (cresce com DIAS, não com eventos), mas na mesma família, e num processo
    que a `scripts/gravar.py` foi feita para deixar rodando."""
    um_dia = 24 * 60 * 60 * 1_000_000_000
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9, meta_a_cada=5)
    gravador.iniciar()
    for d in range(3):
        for i in range(20):
            barramento.publicar(_trade(_DIA_1_TS + d * um_dia + i * _MS, trade_id=f"D{d}T{i}"))
    gravador.parar()

    assert _elementos_retidos(gravador, _IGNORAR_NO_GRAVADOR) == 0, vars(gravador)


def test_checkpoint_fsyncia_os_csvs_antes_de_escrever_o_meta(tmp_path, monkeypatch):
    """Ordem, e ela é a decisão inteira: o `meta.json` descreve um PREFIXO
    dos CSVs por hash. Se o meta for escrito antes do `fsync`, ele passa a
    apontar para bytes que o disco ainda não tem — e é justamente na queda
    de energia (o caso que o `fsync` cobre e o `flush` não) que o meta
    sobrevive e o prefixo não. Registrar a ordem é a única forma de prender
    isso: nenhuma asserção sobre o conteúdo final consegue."""
    ordem: list[str] = []
    monkeypatch.setattr(gravador_mod.os, "fsync", lambda _fd: ordem.append("fsync"))
    original = gravador_mod._escrever_json_atomico
    monkeypatch.setattr(
        gravador_mod, "_escrever_json_atomico",
        lambda caminho, dados: (ordem.append("meta"), original(caminho, dados))[1],
    )

    gravador = _gravador_com_n_eventos(tmp_path, 10, meta_a_cada=10)
    try:
        assert ordem.count("meta") == 1, ordem
        assert ordem[-1] == "meta"
        assert ordem[ordem.index("meta") - 1] == "fsync", ordem
    finally:
        _fechar_handles(gravador)


def test_meta_json_e_escrito_periodicamente_sem_fechar_o_dia(tmp_path):
    """Um crash no meio do pregão não pode mais custar o dia inteiro. Sem
    `parar()` e sem virada de dia, o `meta.json` tem de existir, dizer-se
    PARCIAL e descrever o que já foi gravado."""
    gravador = _gravador_com_n_eventos(tmp_path, 25, meta_a_cada=10)
    try:
        meta_path = next((tmp_path / _SYMBOL).iterdir()) / "meta.json"
        assert meta_path.is_file(), "nenhum meta.json antes de _fechar_dia"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["parcial"] is True
        assert meta["n_eventos_total"] == 20  # ultimo checkpoint, nao 25
        assert meta["hashes_sha256"]["trades.csv"]
        assert meta["n_linhas_hasheadas"]["trades.csv"] == 20
    finally:
        _fechar_handles(gravador)


def test_meta_parcial_e_indexavel_e_verificavel_apos_crash(tmp_path):
    """O ponto inteiro da decisão de durabilidade: depois de uma morte
    abrupta, o dia continua sendo um dia do catálogo e a integridade dele
    continua PROVÁVEL — mesmo com o CSV tendo mais linhas do que o último
    checkpoint descreveu (as que o `flush` levou ao SO entre o checkpoint e
    a morte). É esse descasamento que `n_linhas_hasheadas` existe para
    resolver; sem ele, dado intacto seria reprovado como corrompido."""
    gravador = _gravador_com_n_eventos(tmp_path, 25, meta_a_cada=10)
    _fechar_handles(gravador)  # morte do processo: sem parar(), sem .gz

    catalogo = Catalogo(tmp_path)
    entradas = catalogo.escanear()
    assert len(entradas) == 1, "o dia sumiu do catalogo depois do crash"
    entrada = entradas[0]
    assert entrada.parcial is True
    assert entrada.n_eventos_total == 20

    resultado = catalogo.verificar_integridade(entrada)
    assert resultado["trades.csv"] is True, resultado

    # e o replay do prefixo funciona de ponta a ponta
    barramento = Barramento()
    coletados: list[Trade] = []
    barramento.assinar(Trade, coletados.append)
    AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=True).iniciar()
    assert [t.trade_id for t in coletados[:3]] == ["T0", "T1", "T2"]


def test_integridade_reprova_prefixo_truncado_abaixo_do_declarado(tmp_path):
    """A tolerância do teste anterior é assimétrica de propósito: MAIS
    linhas que o meta declara é dado a mais (legítimo depois de crash);
    MENOS é truncamento, e continua reprovando."""
    gravador = _gravador_com_n_eventos(tmp_path, 25, meta_a_cada=20)
    _fechar_handles(gravador)

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    assert catalogo.verificar_integridade(entrada)["trades.csv"] is True

    caminho = entrada.arquivo("trades.csv")
    assert caminho is not None
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    caminho.write_text("\n".join(linhas[:6]) + "\n", encoding="utf-8")

    assert catalogo.verificar_integridade(entrada)["trades.csv"] is False


def test_meta_json_nunca_deixa_arquivo_temporario_para_tras(tmp_path):
    """A escrita do meta é tmp + `os.replace`. O `.tmp` sobrevivendo à
    troca é sinal de que a atomicidade foi trocada por uma cópia — e um
    `meta.json` escrito no lugar, sem troca atômica, pode ser encontrado
    truncado por um leitor concorrente ou por um crash, o que derruba o dia
    do índice (`_ler_meta` devolve `None`)."""
    gravador = _gravador_com_n_eventos(tmp_path, 30, meta_a_cada=10)
    diretorio = next((tmp_path / _SYMBOL).iterdir())
    try:
        assert not (diretorio / "meta.json.tmp").exists()
        json.loads((diretorio / "meta.json").read_text(encoding="utf-8"))
    finally:
        _fechar_handles(gravador)


def test_gravador_retomado_apos_crash_reconstroi_o_hash_do_que_ja_existia(tmp_path):
    """Retomada: o processo morreu e alguém rodou `gravar.py` de novo no
    mesmo dia. O arquivo é reaberto em modo append, então o hasher precisa
    começar do conteúdo QUE JÁ ESTÁ NO DISCO. Se ele começar do zero, o
    `meta.json` final descreve só o pedaço novo e a verificação de
    integridade reprova um dia inteiramente íntegro — transformando a única
    defesa contra corrupção num gerador de alarme falso."""
    primeiro = _gravador_com_n_eventos(tmp_path, 12, meta_a_cada=0)
    _fechar_handles(primeiro)

    barramento = Barramento()
    segundo = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    segundo.iniciar()
    for i in range(12, 20):
        barramento.publicar(_trade(_DIA_1_TS + i * _MS, trade_id=f"T{i}"))
    segundo.parar()

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    assert entrada.n_linhas_hasheadas["trades.csv"] == 20
    assert catalogo.verificar_integridade(entrada)["trades.csv"] is True

    barramento2 = Barramento()
    coletados: list[Trade] = []
    barramento2.assinar(Trade, coletados.append)
    AdaptadorLeitorGravacao(barramento2, entrada, catalogo=catalogo, verificar_hash=True).iniciar()
    assert [t.trade_id for t in coletados] == [f"T{i}" for i in range(20)]


# =====================================================================
# O TESTE QUE A R5 PROVOU NÃO EXISTIR — leitor (o gêmeo, 37 GB)
# =====================================================================

def _gravar_trades(destino: Path, n: int) -> tuple[Catalogo, object]:
    barramento = Barramento()
    gravador = Gravador(barramento, destino, fsync_a_cada=10**9)
    gravador.iniciar()
    for i in range(n):
        barramento.publicar(_trade(_DIA_1_TS + i * _MS, trade_id=f"T{i}"))
    gravador.parar()
    catalogo = Catalogo(destino)
    return catalogo, catalogo.escanear()[0]


def _pico_de_replay(destino: Path, n: int) -> int:
    catalogo, entrada = _gravar_trades(destino, n)
    barramento = Barramento()
    vistos = [0]

    def contar(_evento) -> None:
        vistos[0] += 1

    barramento.assinar(Trade, contar)
    leitor = AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=False)

    gc.collect()
    tracemalloc.start()
    try:
        leitor.iniciar()
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert vistos[0] == n
    return pico


def test_replay_nao_materializa_a_janela_em_memoria(tmp_path):
    """O gêmeo da 6ª casa: `_eventos_ordenados` segurava a janela pedida
    inteira em RAM — duas vezes, e antes de publicar o primeiro evento —,
    342 B/evento, 37 GB para reler um pregão de 6 h a 5.000 ev/s. A janela
    padrão É o pregão inteiro, porque `--de/--ate` são `None` se o usuário
    não os passar.

    A asserção é sobre o PICO durante o replay: 10x mais eventos não podem
    custar mais memória de pico. Na versão com `sort` global o pico crescia
    linearmente (~0,7 MB para 2.000 eventos, ~6,8 MB para 20.000)."""
    pico_pequeno = _pico_de_replay(tmp_path / "pequeno", 2_000)
    pico_grande = _pico_de_replay(tmp_path / "grande", 20_000)

    assert pico_grande < 1_500_000, f"pico de {pico_grande} B para 20.000 eventos"
    assert pico_grande - pico_pequeno < 700_000, (
        f"o pico cresce com o numero de eventos: {pico_pequeno} -> {pico_grande}"
    )


def test_replay_publica_o_primeiro_evento_sem_ler_o_arquivo_inteiro(tmp_path, monkeypatch):
    """Mesma afirmação do teste acima por um eixo que não depende de medir
    memória — e por isso não depende de folga nenhuma: quantas linhas foram
    LIDAS do disco quando o primeiro evento é publicado. Streaming lê um
    punhado (a janela de reordenação); materializar lê tudo."""
    n = 5_000
    catalogo, entrada = _gravar_trades(tmp_path, n)

    lidas = [0]
    original = leitor_mod._ler_arquivo

    def espiao(caminho, tipo):
        for evento in original(caminho, tipo):
            lidas[0] += 1
            yield evento

    monkeypatch.setattr(leitor_mod, "_ler_arquivo", espiao)

    no_primeiro: list[int] = []
    barramento = Barramento()
    barramento.assinar(Trade, lambda _t: no_primeiro or no_primeiro.append(lidas[0]))
    AdaptadorLeitorGravacao(barramento, entrada, catalogo=catalogo, verificar_hash=False).iniciar()

    teto = 4 * leitor_mod._JANELA_REORDENACAO + 8
    assert no_primeiro and no_primeiro[0] <= teto, (
        f"leu {no_primeiro} linhas antes de publicar o 1o evento de {n}"
    )
    assert lidas[0] == n  # e leu tudo, no fim


# =====================================================================
# A ordem de entrega não mudou (é o contrato inteiro do módulo)
# =====================================================================

def test_replay_entrega_na_mesma_ordem_da_ordenacao_global(tmp_path):
    """`heapq.merge` só substitui o `sort` global se produzir EXATAMENTE a
    mesma sequência. A ordem esperada é recalculada aqui pela definição —
    `(timestamp_ns, ordem do tipo, índice no arquivo)` — a partir da ordem
    de publicação, e não copiada da implementação. O cenário empilha de
    propósito os três empates que a chave precisa desempatar: tipos
    diferentes no mesmo ts, o mesmo tipo repetido no mesmo ts, e ts fora de
    ordem entre tipos."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()

    publicados: list[tuple[int, type, str]] = []

    def publicar(evento, rotulo: str) -> None:
        barramento.publicar(evento)
        publicados.append((evento.timestamp_ns, type(evento), rotulo))

    t0 = _DIA_1_TS
    publicar(_delta(t0 + 2 * _MS), "d0")
    publicar(_trade(t0 + 2 * _MS, trade_id="ta"), "ta")      # empata com d0
    publicar(_trade(t0 + 2 * _MS, trade_id="tb"), "tb")      # empata com ta (mesmo tipo)
    publicar(_snapshot(t0 + 2 * _MS), "s0")                  # empata com todos
    publicar(_falha(t0 + 2 * _MS), "f0")
    publicar(_trade(t0, trade_id="t_antes"), "t_antes")      # ts menor, chega depois
    publicar(_delta(t0 + 1 * _MS), "d1")
    publicar(_snapshot(t0 + 5 * _MS), "s1")
    publicar(_trade(t0 + 5 * _MS, trade_id="tc"), "tc")
    gravador.parar()

    # Ordem esperada, recalculada pela DEFINIÇÃO a partir da ordem de
    # publicação: cada evento recebe o índice que terá dentro do arquivo do
    # seu próprio tipo, e o conjunto é ordenado por (ts, tipo, índice).
    ordem_tipo = leitor_mod._ORDEM_TIPO
    indice_no_arquivo: dict[type, int] = {}
    chaveados: list[tuple[tuple[int, int, int], str]] = []
    for ts, tipo, rotulo in publicados:
        indice = indice_no_arquivo.get(tipo, 0)
        indice_no_arquivo[tipo] = indice + 1
        chaveados.append(((ts, ordem_tipo[tipo], indice), rotulo))
    esperado = [rotulo for _chave, rotulo in sorted(chaveados, key=lambda p: p[0])]

    _ROTULO = {
        Trade: lambda e: e.trade_id,
        BookSnapshot: lambda e: "s0" if e.timestamp_ns == t0 + 2 * _MS else "s1",
        BookDelta: lambda e: "d0" if e.timestamp_ns == t0 + 2 * _MS else "d1",
        FalhaCaptura: lambda e: "f0",
    }

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    barramento2 = Barramento()
    recebidos: list[str] = []
    for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura):
        barramento2.assinar(tipo, lambda e: recebidos.append(_ROTULO[type(e)](e)))
    AdaptadorLeitorGravacao(barramento2, entrada, catalogo=catalogo, verificar_hash=True).iniciar()

    assert recebidos == esperado
    # e o de ts menor vem primeiro, ainda que tenha sido publicado por ultimo
    assert esperado[0] == "t_antes"
    assert recebidos[0] == "t_antes"


def test_replay_absorve_desordem_local_dentro_da_janela(tmp_path):
    """O `Gravador` escreve na ordem de PUBLICAÇÃO e não recusa um evento
    atrasado — a suíte tem um teste que publica fora de ordem de propósito.
    A versão com `sort` global absorvia qualquer desordem, ao custo de
    segurar o pregão inteiro. A janela de reordenação preserva a tolerância
    à desordem LOCAL (jitter de feed) sem reintroduzir o crescimento."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()
    ordem_publicacao = list(range(300))
    # desloca alguns poucos itens para tras — bem dentro da janela
    for i in (50, 51, 120):
        ordem_publicacao[i], ordem_publicacao[i - 5] = ordem_publicacao[i - 5], ordem_publicacao[i]
    for i in ordem_publicacao:
        barramento.publicar(_trade(_DIA_1_TS + i * _MS, trade_id=f"T{i}"))
    gravador.parar()

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    barramento2 = Barramento()
    recebidos: list[Trade] = []
    barramento2.assinar(Trade, recebidos.append)
    AdaptadorLeitorGravacao(barramento2, entrada, catalogo=catalogo, verificar_hash=True).iniciar()

    assert [t.trade_id for t in recebidos] == [f"T{i}" for i in range(300)]


def test_replay_recusa_desordem_maior_que_a_janela_em_vez_de_mentir(tmp_path):
    """Desordem além da janela não pode ser publicada em silêncio: replay
    fora de ordem envenena qualquer backtest sem deixar rastro, e
    determinismo de ordem é o contrato deste módulo. Falhar alto é a
    degradação COM relatório."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()
    for i in range(300):
        barramento.publicar(_trade(_DIA_1_TS + (i + 1) * _MS, trade_id=f"T{i}"))
    barramento.publicar(_trade(_DIA_1_TS, trade_id="ATRASADO"))  # 300 posicoes atras
    gravador.parar()

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    barramento2 = Barramento()
    barramento2.assinar(Trade, lambda _t: None)
    leitor = AdaptadorLeitorGravacao(barramento2, entrada, catalogo=catalogo, verificar_hash=True)
    with pytest.raises(GravacaoForaDeOrdemError):
        leitor.iniciar()


def test_recorte_por_horario_continua_filtrando_no_caminho_streaming(tmp_path):
    """O filtro de intervalo passou a ser aplicado dentro do gerador de
    cada arquivo. Se ele se perder ali, o `--de/--ate` vira decoração e o
    replay devolve o dia inteiro."""
    barramento = Barramento()
    gravador = Gravador(barramento, tmp_path, fsync_a_cada=10**9)
    gravador.iniciar()
    for i in range(500):
        barramento.publicar(_trade(_DIA_1_TS + i * _MS, trade_id=f"T{i}"))
        if i % 100 == 0:
            barramento.publicar(_snapshot(_DIA_1_TS + i * _MS))
    gravador.parar()

    catalogo = Catalogo(tmp_path)
    entrada = catalogo.escanear()[0]
    ts_ini = _DIA_1_TS + 100 * _MS
    ts_fim = _DIA_1_TS + 199 * _MS

    barramento2 = Barramento()
    trades: list[Trade] = []
    snaps: list[BookSnapshot] = []
    barramento2.assinar(Trade, trades.append)
    barramento2.assinar(BookSnapshot, snaps.append)
    AdaptadorLeitorGravacao(
        barramento2, entrada, ts_inicio_ns=ts_ini, ts_fim_ns=ts_fim,
        catalogo=catalogo, verificar_hash=True,
    ).iniciar()

    assert [t.trade_id for t in trades] == [f"T{i}" for i in range(100, 200)]
    assert [s.timestamp_ns for s in snaps] == [_DIA_1_TS + 100 * _MS]
