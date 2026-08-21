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
"""

from __future__ import annotations

import csv
import gzip
import logging
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

_LEITORES = {
    Trade: formato.linha_para_trade,
    BookSnapshot: formato.linha_para_snapshot,
    BookDelta: formato.linha_para_delta,
    FalhaCaptura: formato.linha_para_falha,
}


class IntegridadeInvalidaError(RuntimeError):
    pass


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

    def _eventos_ordenados(self) -> list[EventoGravado]:
        combinados: list[tuple[int, int, int, EventoGravado]] = []
        for tipo in (Trade, BookSnapshot, BookDelta, FalhaCaptura):
            caminho = self._entrada.arquivo(formato.NOMES_ARQUIVO[tipo])
            for indice, evento in enumerate(_ler_arquivo(caminho, tipo)):
                if not self._dentro_do_intervalo(evento.timestamp_ns):
                    continue
                combinados.append((evento.timestamp_ns, _ORDEM_TIPO[tipo], indice, evento))
        combinados.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in combinados]
