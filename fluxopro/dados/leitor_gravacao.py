"""Adaptador de replay que lê o formato do `Gravador` (trades, snapshots,
book deltas e falhas de captura, particionados por símbolo/dia — ver
`fluxopro/gravacao/formato.py`).

Não estende `AdaptadorReplay` (`fluxopro/dados/replay.py`): aquele é o
formato mínimo do núcleo (só trade + delta, 2 arquivos passados à mão) e
`replay.py` documenta explicitamente que estender o formato deve ser feito
num leitor novo, não quebrando o existente. Este arquivo é esse leitor novo:
lê o layout com metadados/hash produzido pelo `Gravador` e pelo `Catalogo`,
com filtro por intervalo de tempo, verificação de integridade e velocidade
configurável — mesmo contrato de `AdaptadorDados`, mesma ordem de entrega
que o núcleo já testa (empate de timestamp: por tipo, depois ordem original).

Retenção em memória (o GEMEO da 6a casa, auditoria R5):
  Até a R5 `_eventos_ordenados` era uma `list`: lia os quatro arquivos
  inteiros para dentro de uma lista de tuplas de 4 (com o evento dentro),
  ordenava tudo e devolvia uma SEGUNDA lista com os eventos — as duas vivas
  ao mesmo tempo, ANTES de publicar o primeiro evento. Medido: 342 B/evento,
  linear, **37 GB para reler um pregão de 6 h a 5.000 ev/s** (74 GB a
  10.000 ev/s). A janela padrão é o pregão inteiro, porque `--de/--ate` são
  `None` quando o usuário não os passa.

  A razão da ordenação global é legítima — é ela que garante o determinismo
  do replay, `(timestamp_ns, tipo, índice_no_arquivo)` — mas ela não exige a
  lista: os quatro arquivos já saem do `Gravador` em ordem de chegada, então
  um `heapq.merge` sobre os quatro iteradores com a MESMA chave produz
  exatamente a mesma sequência com memória O(1) no número de eventos.
  `_ler_arquivo` já era um gerador de verdade (streaming do gzip linha a
  linha); a preguiça existia e era desperdiçada na linha seguinte.

  Duas consequências que valem registro:
  - `parar()` volta a funcionar. Antes, o flag era conferido só DENTRO do
    laço de publicação, e o processo ficava preso montando a lista sem
    responder ao `--duracao`. Agora a montagem é o próprio laço.
  - a ordem de entrega é IDÊNTICA à da versão com `sort`, e há guarda para
    provar isso em execução: ver `_JANELA_REORDENACAO` e
    `GravacaoForaDeOrdemError`.
"""

from __future__ import annotations

import csv
import gzip
import heapq
import logging
import operator
import time
from pathlib import Path
from typing import Iterator

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookDelta, BookSnapshot, Trade
from fluxopro.dados.adaptador import AdaptadorDados
from fluxopro.dados.eventos_captura import FalhaCaptura
from fluxopro.gravacao import formato
from fluxopro.gravacao.catalogo import Catalogo, EntradaCatalogo

_logger = logging.getLogger("fluxopro.dados.leitor_gravacao")

EventoGravado = Trade | BookSnapshot | BookDelta | FalhaCaptura

# Ordem de desempate quando dois eventos de tipos diferentes têm o mesmo
# timestamp_ns — mesma prioridade de leitura de mercado que `replay.py` usa
# (trade primeiro), estendida para snapshot/delta/falha.
_ORDEM_TIPO = {Trade: 0, BookSnapshot: 1, BookDelta: 2, FalhaCaptura: 3}

# Janela de reordenacao POR ARQUIVO, em eventos.
#
# `heapq.merge` so devolve a ordem global correta se cada entrada ja vier
# ordenada, e o `Gravador` escreve na ordem de PUBLICACAO — que e a ordem do
# relogio na captura ao vivo, mas ele nao recusa um evento atrasado (ver
# `test_gravador_meta_hora_inicio_e_hora_fim_nao_sao_trocados`, que publica
# fora de ordem de proposito). A versao com `sort` global absorvia qualquer
# desordem ao custo de segurar o pregao inteiro em RAM.
#
# Esta janela mantem a tolerancia a desordem LOCAL (jitter de feed: um punhado
# de eventos) sem reintroduzir o crescimento: sao no maximo
# 4 x _JANELA_REORDENACAO eventos em memoria, constante no tamanho do pregao.
# Desordem MAIOR que a janela nao e absorvida em silencio — e detectada na
# saida e vira `GravacaoForaDeOrdemError`. Emitir replay fora de ordem sem
# avisar seria pior que falhar: envenenaria qualquer backtest sem deixar
# rastro, e determinismo de ordem e o contrato inteiro deste modulo.
_JANELA_REORDENACAO = 64

_CHAVE = operator.itemgetter(0)

_LEITORES = {
    Trade: formato.linha_para_trade,
    BookSnapshot: formato.linha_para_snapshot,
    BookDelta: formato.linha_para_delta,
    FalhaCaptura: formato.linha_para_falha,
}


class IntegridadeInvalidaError(RuntimeError):
    pass


class GravacaoForaDeOrdemError(RuntimeError):
    """Um arquivo da gravacao esta fora de ordem por mais de
    `_JANELA_REORDENACAO` eventos. Levantada em vez de publicar uma sequencia
    fora de ordem — ver o comentario de `_JANELA_REORDENACAO`."""


def _abrir_texto(caminho: Path):
    if caminho.suffix == ".gz":
        return gzip.open(caminho, "rt", newline="", encoding="utf-8")
    return caminho.open("r", newline="", encoding="utf-8")


def _ler_arquivo(caminho: Path | None, tipo: type) -> Iterator[EventoGravado]:
    if caminho is None:
        return
    leitor_linha = _LEITORES[tipo]
    with _abrir_texto(caminho) as arquivo:
        for linha in csv.DictReader(arquivo):
            yield leitor_linha(linha)


class AdaptadorLeitorGravacao(AdaptadorDados):
    """Reproduz, na ordem correta, o que o `Gravador` persistiu para um
    símbolo num dia — com filtro opcional de horário, exatamente o caso de
    uso "me dá o replay do WDO de 2026-08-20 das 09:00 às 10:30" que o
    `Catalogo` resolve para `(entrada, ts_inicio, ts_fim)`.
    """

    def __init__(
        self,
        barramento: Barramento,
        entrada: EntradaCatalogo,
        ts_inicio_ns: int | None = None,
        ts_fim_ns: int | None = None,
        velocidade: float | str = "max",
        verificar_hash: bool = True,
        catalogo: Catalogo | None = None,
    ) -> None:
        super().__init__(barramento)
        self._entrada = entrada
        self._ts_inicio = ts_inicio_ns
        self._ts_fim = ts_fim_ns
        self._velocidade = velocidade
        self._verificar_hash = verificar_hash
        self._catalogo = catalogo
        self._parar = False

        if verificar_hash:
            self._checar_integridade()

    def _checar_integridade(self) -> None:
        catalogo = self._catalogo or Catalogo(self._entrada.diretorio.parent.parent)
        resultado = catalogo.verificar_integridade(self._entrada)
        falhas = [nome for nome, ok in resultado.items() if not ok]
        if falhas:
            raise IntegridadeInvalidaError(
                f"hash divergente para {self._entrada.symbol} "
                f"{self._entrada.data.isoformat()}: {falhas}"
            )

    def iniciar(self) -> None:
        self._parar = False
        primeiro_ts: int | None = None
        wall_inicio: float | None = None

        for evento in self._eventos_ordenados():
            if self._parar:
                break
            if self._velocidade != "max":
                if primeiro_ts is None:
                    primeiro_ts = evento.timestamp_ns
                    wall_inicio = time.monotonic()
                else:
                    fator = float(self._velocidade)
                    decorrido_evento_s = (evento.timestamp_ns - primeiro_ts) / 1e9 / fator
                    decorrido_wall_s = time.monotonic() - wall_inicio  # type: ignore[operator]
                    espera = decorrido_evento_s - decorrido_wall_s
                    if espera > 0:
                        time.sleep(espera)
            self._barramento.publicar(evento)

    def parar(self) -> None:
        self._parar = True

    def _dentro_do_intervalo(self, ts: int) -> bool:
        if self._ts_inicio is not None and ts < self._ts_inicio:
            return False
        if self._ts_fim is not None and ts > self._ts_fim:
            return False
        return True

    def _fluxo_de_um_arquivo(
        self, tipo: type
    ) -> Iterator[tuple[tuple[int, int, int], EventoGravado]]:
        """`(chave, evento)` de UM arquivo, em ordem de chave, mantendo no
        maximo `_JANELA_REORDENACAO` eventos em memoria. A chave e a mesma
        que a versao com `sort` global usava: `(timestamp_ns, ordem do tipo,
        indice no arquivo)`. O indice torna a chave unica dentro do arquivo,
        entao o heap nunca compara os eventos entre si."""
        ordem = _ORDEM_TIPO[tipo]
        caminho = self._entrada.arquivo(formato.NOMES_ARQUIVO[tipo])
        janela: list[tuple[tuple[int, int, int], EventoGravado]] = []
        for indice, evento in enumerate(_ler_arquivo(caminho, tipo)):
            if not self._dentro_do_intervalo(evento.timestamp_ns):
                continue
            heapq.heappush(janela, ((evento.timestamp_ns, ordem, indice), evento))
            if len(janela) > _JANELA_REORDENACAO:
                yield heapq.heappop(janela)
        while janela:
            yield heapq.heappop(janela)

    def _eventos_ordenados(self) -> Iterator[EventoGravado]:
        """Mesma sequencia que a antiga lista ordenada, em memoria O(1) no
        numero de eventos: `heapq.merge` sobre os quatro arquivos, com a
        mesma chave de desempate. Ver "Retencao em memoria" no topo."""
        fluxos = [
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
            yield evento
