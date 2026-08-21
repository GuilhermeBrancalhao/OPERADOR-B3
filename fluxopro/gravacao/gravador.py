"""Gravador: assina o Barramento e persiste tudo em disco, particionado por
símbolo e por dia (UTC, derivado do `timestamp_ns` de cada evento — nunca do
relógio da máquina, para caber tanto em captura ao vivo quanto em replay).

É peça de primeira classe do sistema, não acessório: não existe hoje fonte
externa (grátis ou paga) de histórico de book para WDO/WIN
(`pesquisa/fontes_de_dados.md`, seção 3.3) — o que o dono gravar a partir de
agora É a base de replay que ele vai ter no futuro. Perder um evento aqui é
perder um pedaço de mercado que não volta.

Política de flush/fsync (decisão e porquê):
  - `flush()` (nível Python -> buffer do SO) depois de CADA linha escrita.
    Custo desprezível — writes de string curtas — e garante que um crash do
    processo Python não perde o que já foi "escrito" do ponto de vista do
    SO.
  - `os.fsync()` (buffer do SO -> disco) só a cada `fsync_a_cada` linhas
    (padrão 200) OU ao fechar/rotacionar um arquivo. fsync por linha
    custaria ms por evento — inviável no volume de um pregão inteiro; a
    cada N linhas limita a janela de perda a uma queda de energia/kernel
    panic (não a um crash do processo, que o flush já cobre) a, no pior
    caso, `fsync_a_cada` eventos.
  - `FalhaCaptura` é a exceção: fsync imediato, sempre — é o registro mais
    barato (poucas linhas por pregão) e o mais importante de não perder,
    porque é ele que prova que um buraco existe.

Formato: ver `fluxopro/gravacao/formato.py` para a decisão CSV vs Parquet
(CSV ao vivo, comprimido para `.csv.gz` na rotação) e o schema versionado.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import IO

from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import BookDelta, BookSnapshot, Trade
from fluxopro.dados.eventos_captura import FalhaCaptura
from fluxopro.gravacao import formato

_logger = logging.getLogger("fluxopro.gravacao.gravador")

_TIPOS_GRAVADOS = (Trade, BookSnapshot, BookDelta, FalhaCaptura)

_CABECALHOS = {
    Trade: formato.CABECALHO_TRADES,
    BookSnapshot: formato.CABECALHO_SNAPSHOTS,
    BookDelta: formato.CABECALHO_DELTAS,
    FalhaCaptura: formato.CABECALHO_FALHAS,
}
_SERIALIZADORES = {
    Trade: formato.trade_para_linha,
    BookSnapshot: formato.snapshot_para_linha,
    BookDelta: formato.delta_para_linha,
    FalhaCaptura: formato.falha_para_linha,
}


def _timestamp_para_data(timestamp_ns: int) -> date:
    return datetime.fromtimestamp(timestamp_ns / 1e9, tz=timezone.utc).date()


@dataclass
class _ArquivoAberto:
    caminho: Path
    handle: IO[str]
    writer: csv.writer
    hasher: "hashlib._Hash"
    n_linhas: int = 0
    n_desde_fsync: int = 0


class Gravador:
    def __init__(
        self,
        barramento: Barramento,
        saida_dir: str | Path,
        fsync_a_cada: int = 200,
    ) -> None:
        self._barramento = barramento
        self._saida = Path(saida_dir)
        self._fsync_a_cada = fsync_a_cada
        self._lock = threading.Lock()

        # (symbol, data) -> dia atualmente aberto para escrita
        self._dia_aberto: dict[str, date] = {}
        # (symbol, data, tipo) -> _ArquivoAberto
        self._arquivos: dict[tuple[str, date, type], _ArquivoAberto] = {}
        self._contagens: dict[tuple[str, date], dict[str, int]] = {}
        self._horarios: dict[tuple[str, date], list[int]] = {}

    # ------------------------------------------------------------------
    def iniciar(self) -> None:
        for tipo in _TIPOS_GRAVADOS:
            self._barramento.assinar(tipo, self._receber)

    def parar(self) -> None:
        with self._lock:
            for (symbol, dia) in list(self._dia_aberto.items()):
                self._fechar_dia(symbol, dia)

    # ------------------------------------------------------------------
    def _receber(self, evento: Trade | BookSnapshot | BookDelta | FalhaCaptura) -> None:
        symbol = evento.symbol
        data_evento = _timestamp_para_data(evento.timestamp_ns)

        with self._lock:
            dia_atual = self._dia_aberto.get(symbol)
            if dia_atual is not None and data_evento > dia_atual:
                self._fechar_dia(symbol, dia_atual)
                dia_atual = None
            if dia_atual is None:
                self._dia_aberto[symbol] = data_evento
                dia_atual = data_evento

            self._escrever(symbol, dia_atual, evento)

    def _escrever(self, symbol: str, dia: date, evento) -> None:
        tipo = type(evento)
        chave = (symbol, dia, tipo)
        arq = self._arquivos.get(chave)
        if arq is None:
            arq = self._abrir_arquivo(symbol, dia, tipo)
            self._arquivos[chave] = arq

        linha = _SERIALIZADORES[tipo](evento)
        arq.writer.writerow(linha)
        arq.handle.flush()
        arq.hasher.update(("\t".join(linha) + "\n").encode("utf-8"))
        arq.n_linhas += 1
        arq.n_desde_fsync += 1

        forcar_fsync = isinstance(evento, FalhaCaptura) or arq.n_desde_fsync >= self._fsync_a_cada
        if forcar_fsync:
            os.fsync(arq.handle.fileno())
            arq.n_desde_fsync = 0

        contagens = self._contagens.setdefault((symbol, dia), {})
        contagens[tipo.__name__] = contagens.get(tipo.__name__, 0) + 1
        self._horarios.setdefault((symbol, dia), []).append(evento.timestamp_ns)

    def _abrir_arquivo(self, symbol: str, dia: date, tipo: type) -> _ArquivoAberto:
        diretorio = self._saida / symbol / dia.isoformat()
        diretorio.mkdir(parents=True, exist_ok=True)
        caminho = diretorio / formato.NOMES_ARQUIVO[tipo]
        novo = not caminho.exists()
        handle = caminho.open("a", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        if novo:
            writer.writerow(_CABECALHOS[tipo])
            handle.flush()
        return _ArquivoAberto(caminho=caminho, handle=handle, writer=writer, hasher=hashlib.sha256())

    # ------------------------------------------------------------------
    def _fechar_dia(self, symbol: str, dia: date) -> None:
        hashes: dict[str, str] = {}
        for tipo in _TIPOS_GRAVADOS:
            chave = (symbol, dia, tipo)
            arq = self._arquivos.pop(chave, None)
            if arq is None:
                continue
            arq.handle.flush()
            os.fsync(arq.handle.fileno())
            arq.handle.close()
            hashes[formato.NOMES_ARQUIVO[tipo]] = arq.hasher.hexdigest()
            _comprimir_e_remover(arq.caminho)

        contagens = self._contagens.pop((symbol, dia), {})
        horarios = self._horarios.pop((symbol, dia), [])
        meta = {
            "symbol": symbol,
            "data": dia.isoformat(),
            "schema_versao": formato.SCHEMA_VERSAO,
            "contagens": contagens,
            "n_eventos_total": sum(contagens.values()),
            "hora_inicio_ns": min(horarios) if horarios else None,
            "hora_fim_ns": max(horarios) if horarios else None,
            "hashes_sha256": hashes,
            "gerado_em_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        diretorio = self._saida / symbol / dia.isoformat()
        (diretorio / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._dia_aberto.pop(symbol, None)
        _logger.info(
            "dia fechado: %s %s — %d eventos (%s)",
            symbol, dia.isoformat(), meta["n_eventos_total"], contagens,
        )


def _comprimir_e_remover(caminho: Path) -> None:
    """Comprime o CSV fechado para .csv.gz e remove o original. Feito só na
    rotação (arquivo já fechado), nunca durante escrita ao vivo — é aqui
    que a decisão 'CSV ao vivo, gzip em repouso' economiza CPU no caminho
    quente sem abrir mão do ganho de espaço em disco (ver benchmark).
    """
    destino = caminho.with_suffix(caminho.suffix + ".gz")
    with caminho.open("rb") as origem, gzip.open(destino, "wb", compresslevel=6) as saida:
        shutil.copyfileobj(origem, saida)
    caminho.unlink()
