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

Retenção em memória (a 6a CASA do defeito de crescimento — auditoria R5):
  Até a R5 este módulo guardava `self._horarios[(symbol, dia)] -> list[int]`,
  um `int` de nanossegundos POR EVENTO, do primeiro ao último do pregão,
  para no fim produzir DOIS ESCALARES (`min` e `max`). Medido no objeto de
  produção: 44,9 B/evento -> **4,85 GB** num pregão de 6 h a 5.000 ev/s
  (9,70 GB a 10.000 ev/s). Não havia versão do requisito em que isso fosse
  necessário: `min`/`max` de um fluxo são O(1) de memória.

  O agravante era de DURABILIDADE, não só de RAM: o `meta.json` — que é onde
  moram os hashes de integridade e sem o qual o `Catalogo` sequer INDEXA o
  dia — só era escrito em `_fechar_dia`, e `_fechar_dia` só tem dois
  chamadores (virada de dia UTC e `parar()`), nenhum periódico. Um OOM às
  15h perdia a gravação do dia inteiro, e não existe segunda cópia
  (ver o parágrafo acima sobre fonte externa).

  Hoje:
  - `_hora_inicio_ns` / `_hora_fim_ns`: dois `int` por (símbolo, dia) aberto,
    atualizados incrementalmente. O `len` de toda coleção de instância deste
    módulo é limitado por SÍMBOLOS × DIAS ABERTOS — uma grandeza que para de
    crescer enquanto o pregão continua. Nenhuma é limitada por número de
    eventos.
  - `meta_a_cada` (padrão 5.000 eventos): checkpoint periódico do
    `meta.json`, com fsync dos CSVs ANTES da escrita e troca atômica do
    `meta.json` (tmp + `os.replace`). Ver `_checkpoint_meta`.

  O critério, que vale para qualquer estrutura nova aqui dentro (é o mesmo
  do docstring de `_registrar_preco` em `microestrutura/inferencia_mbp.py`):
  **"qual grandeza limita o `len` disto, e ela para de crescer enquanto o
  pregão continua?"**. Se a resposta contiver "número de eventos", é a mesma
  casa. `tests/test_gravacao_retencao.py` transforma esse critério em
  asserção — a auditoria R5 provou (mutação G01) que, sem ele, a suíte
  inteira é INCAPAZ de distinguir a versão O(eventos) da versão O(1).

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
        meta_a_cada: int = 5_000,
    ) -> None:
        self._barramento = barramento
        self._saida = Path(saida_dir)
        self._fsync_a_cada = fsync_a_cada
        self._meta_a_cada = meta_a_cada
        self._lock = threading.Lock()

        # (symbol, data) -> dia atualmente aberto para escrita
        self._dia_aberto: dict[str, date] = {}
        # (symbol, data, tipo) -> _ArquivoAberto
        self._arquivos: dict[tuple[str, date, type], _ArquivoAberto] = {}
        self._contagens: dict[tuple[str, date], dict[str, int]] = {}
        # DOIS escalares por (symbol, dia) — nunca a lista de timestamps.
        # Ver "Retenção em memória" no docstring do módulo.
        self._hora_inicio_ns: dict[tuple[str, date], int] = {}
        self._hora_fim_ns: dict[tuple[str, date], int] = {}
        self._desde_meta: dict[tuple[str, date], int] = {}
        # Um contador por (symbol, dia) DESCARTADO. Limitado pelo numero de
        # dias que uma execucao encosta, nao por eventos — o criterio deste
        # arquivo aplicado a ele mesmo.
        self._descartados: dict[tuple[str, date], int] = {}

    # ------------------------------------------------------------------
    def iniciar(self) -> None:
        for tipo in _TIPOS_GRAVADOS:
            self._barramento.assinar(tipo, self._receber)

    @property
    def descartados_por_dia_fechado(self) -> dict[tuple[str, date], int]:
        """Quantos eventos foram descartados por chegarem a um dia finalizado.

        Publico porque descarte silencioso e o defeito que este projeto passou
        cinco auditorias caçando: quem opera precisa poder perguntar.
        """
        with self._lock:
            return dict(self._descartados)

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
                # O rabo republicado de um dia JA FECHADO em execucao anterior
                # (ver `_descartar_de_dia_fechado`) nao pode virar "dia aberto"
                # nesta execucao: um processo novo, sem `_dia_aberto[symbol]`
                # ainda, que recebe so esse rabo tratava esse dia velho como o
                # dia corrente — e quando o primeiro evento de HOJE chegasse,
                # `_fechar_dia` fechava aquele dia velho de novo, com as
                # contagens desta execucao (zero) e SOBRESCREVIA o
                # `meta.json` real (hashes inclusos) por um de 0 eventos.
                # Achado ao vivo em 2026-08-26 -> meta.json clobbrado no
                # ciclo seguinte (27/08 09:00).
                if self._dia_ja_finalizado(symbol, data_evento, type(evento)):
                    self._descartar_de_dia_fechado(symbol, data_evento)
                    return
                self._dia_aberto[symbol] = data_evento
                dia_atual = data_evento

            self._escrever(symbol, dia_atual, evento)

    def _escrever(self, symbol: str, dia: date, evento) -> None:
        tipo = type(evento)
        chave = (symbol, dia, tipo)
        arq = self._arquivos.get(chave)
        if arq is None:
            if self._dia_ja_finalizado(symbol, dia, tipo):
                self._descartar_de_dia_fechado(symbol, dia)
                return
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

        chave_dia = (symbol, dia)
        contagens = self._contagens.setdefault(chave_dia, {})
        contagens[tipo.__name__] = contagens.get(tipo.__name__, 0) + 1

        # min/max INCREMENTAIS. Dois `int` por dia aberto, não um por evento.
        ts = evento.timestamp_ns
        inicio = self._hora_inicio_ns.get(chave_dia)
        if inicio is None or ts < inicio:
            self._hora_inicio_ns[chave_dia] = ts
        fim = self._hora_fim_ns.get(chave_dia)
        if fim is None or ts > fim:
            self._hora_fim_ns[chave_dia] = ts

        self._desde_meta[chave_dia] = self._desde_meta.get(chave_dia, 0) + 1
        if self._meta_a_cada > 0 and self._desde_meta[chave_dia] >= self._meta_a_cada:
            self._checkpoint_meta(symbol, dia)

    def _dia_ja_finalizado(self, symbol: str, dia: date, tipo: type) -> bool:
        """O dia ja foi fechado e comprimido numa execucao anterior?

        `_fechar_dia` comprime o `.csv` em `.csv.gz` e apaga o original, entao a
        presenca do `.gz` **e** a marca de finalizado. Nao se le o `meta.json`
        aqui de proposito: o `.gz` e o mesmo arquivo que a verificacao de
        integridade hasheia, e perguntar ao arquivo e mais barato e mais direto
        que perguntar ao metadado que descreve o arquivo.
        """
        caminho = self._saida / symbol / dia.isoformat() / formato.NOMES_ARQUIVO[tipo]
        return caminho.with_suffix(caminho.suffix + ".gz").exists()

    def _descartar_de_dia_fechado(self, symbol: str, dia: date) -> None:
        """Evento de um dia ja finalizado: DESCARTA, conta, e avisa uma vez.

        ## O caso real que trouxe esta guarda

        O adaptador MT5 republica o rabo da sessao anterior ao conectar. Num
        teste da tarefa agendada, num domingo, a conexao trouxe **141 negocios
        do ultimo minuto de sexta** — todos ja gravados e hasheados — e o
        gravador criou um `trades.csv` solto ao lado do `trades.csv.gz`
        finalizado. Dois arquivos com o mesmo nome-base no mesmo dia, e o
        catalogo passa a ter de escolher entre eles.

        Isso ia se repetir em toda segunda-feira as 09:00.

        ## Por que descartar, e nao recusar

        A guarda obvia seria levantar erro. Seria pior: a captura de segunda
        inteira abortaria por causa de um minuto de sexta que ja esta em disco.
        A retomada apos crash — que e o motivo de `_abrir_arquivo` saber anexar
        — continua funcionando, porque um dia interrompido nao tem `.gz`.

        O aviso sai UMA vez por dia descartado, e nao por evento: 141 linhas de
        log identicas escondem a informacao em vez de entrega-la. A contagem
        continua subindo e fica no fim.
        """
        chave = (symbol, dia)
        n = self._descartados.get(chave, 0) + 1
        self._descartados[chave] = n
        if n == 1:
            _logger.warning(
                "evento de %s %s chegou com o dia JA FECHADO (existe .gz) — "
                "descartando. Normalmente e o rabo da sessao anterior que o "
                "adaptador republica ao conectar; ele ja esta gravado.",
                symbol,
                dia,
            )

    def _abrir_arquivo(self, symbol: str, dia: date, tipo: type) -> _ArquivoAberto:
        diretorio = self._saida / symbol / dia.isoformat()
        diretorio.mkdir(parents=True, exist_ok=True)
        caminho = diretorio / formato.NOMES_ARQUIVO[tipo]
        novo = not caminho.exists()
        # Retomada depois de um crash: o arquivo ja tem linhas de dados. O
        # hasher precisa comecar do CONTEUDO QUE JA ESTA LA, senao o
        # `meta.json` final descreve so o pedaco novo e a verificacao de
        # integridade reprova o dia inteiro como corrompido — que e
        # exatamente o oposto do que o checkpoint existe para conseguir.
        hasher = hashlib.sha256()
        n_linhas = 0
        if not novo:
            hasher, n_linhas = _hash_e_contar_existente(caminho)
        handle = caminho.open("a", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        if novo:
            writer.writerow(_CABECALHOS[tipo])
            handle.flush()
        return _ArquivoAberto(
            caminho=caminho, handle=handle, writer=writer,
            hasher=hasher, n_linhas=n_linhas,
        )

    # ------------------------------------------------------------------
    def _checkpoint_meta(self, symbol: str, dia: date) -> None:
        """`meta.json` PARCIAL, escrito no meio do pregao sem fechar o dia.

        Decisao de durabilidade (auditoria R5). Sem isto, `_fechar_dia` e o
        unico escritor do `meta.json` e nao ha chamador periodico: qualquer
        morte do processo — OOM, queda de energia, Ctrl+C bruto, disco cheio
        — deixa os CSVs em disco SEM `meta.json`, e sem `meta.json` o
        `Catalogo` nem enxerga o dia (`escanear` pula o diretorio). Ou seja:
        o dado existe no disco e o produto se comporta como se nao
        existisse. Nao ha segunda copia de pregao de WDO/WIN.

        Ordem das operacoes, e ela importa:
          1. `flush` + `fsync` de CADA arquivo aberto do dia — assim o
             prefixo que o meta vai descrever esta DURAVEL antes de ser
             descrito. A ordem inversa produziria um meta que aponta para
             bytes que o disco ainda nao tem.
          2. `hasher.hexdigest()` do prefixo escrito ate aqui (hexdigest nao
             consome o hasher; ele segue acumulando as linhas seguintes).
          3. `n_linhas_hasheadas` por arquivo — sem isso o hash de prefixo
             seria inverificavel, porque depois do crash o arquivo tende a
             ter MAIS linhas do que o checkpoint cobriu (as que o `flush`
             levou ao SO entre o checkpoint e a morte). Ver
             `Catalogo.verificar_integridade`.
          4. escrita ATOMICA do `meta.json` (tmp + `os.replace`): um
             `meta.json` truncado no meio e indistinguivel de um corrompido
             para `_ler_meta`, e derrubaria o dia do indice — o proprio mal
             que o checkpoint existe para evitar.

        Cadencia por CONTAGEM DE EVENTOS, nao por tempo: a unidade da perda
        e o evento, a contagem e deterministica (logo, testavel) e nao
        precisa de relogio. O custo e desprezivel — a 44.000 ev/s medidos, o
        padrao de 5.000 eventos da um checkpoint a cada ~0,11 s, e ele so
        acrescenta um `hexdigest` por arquivo a um `fsync` que a politica de
        `fsync_a_cada=200` ja faria 25 vezes no mesmo intervalo.
        """
        hashes: dict[str, str] = {}
        n_linhas: dict[str, int] = {}
        for tipo in _TIPOS_GRAVADOS:
            arq = self._arquivos.get((symbol, dia, tipo))
            if arq is None:
                continue
            arq.handle.flush()
            os.fsync(arq.handle.fileno())
            arq.n_desde_fsync = 0
            nome = formato.NOMES_ARQUIVO[tipo]
            hashes[nome] = arq.hasher.hexdigest()
            n_linhas[nome] = arq.n_linhas

        self._gravar_meta(symbol, dia, hashes, n_linhas, parcial=True)
        self._desde_meta[(symbol, dia)] = 0

    def _gravar_meta(
        self,
        symbol: str,
        dia: date,
        hashes: dict[str, str],
        n_linhas: dict[str, int],
        parcial: bool,
    ) -> None:
        contagens = dict(self._contagens.get((symbol, dia), {}))
        meta = {
            "symbol": symbol,
            "data": dia.isoformat(),
            "schema_versao": formato.SCHEMA_VERSAO,
            "contagens": contagens,
            "n_eventos_total": sum(contagens.values()),
            "hora_inicio_ns": self._hora_inicio_ns.get((symbol, dia)),
            "hora_fim_ns": self._hora_fim_ns.get((symbol, dia)),
            "hashes_sha256": hashes,
            "n_linhas_hasheadas": n_linhas,
            "parcial": parcial,
            "gerado_em_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        diretorio = self._saida / symbol / dia.isoformat()
        diretorio.mkdir(parents=True, exist_ok=True)
        _escrever_json_atomico(diretorio / "meta.json", meta)

    def _fechar_dia(self, symbol: str, dia: date) -> None:
        hashes: dict[str, str] = {}
        n_linhas: dict[str, int] = {}
        for tipo in _TIPOS_GRAVADOS:
            chave = (symbol, dia, tipo)
            arq = self._arquivos.pop(chave, None)
            if arq is None:
                continue
            arq.handle.flush()
            os.fsync(arq.handle.fileno())
            arq.handle.close()
            nome = formato.NOMES_ARQUIVO[tipo]
            hashes[nome] = arq.hasher.hexdigest()
            n_linhas[nome] = arq.n_linhas
            _comprimir_e_remover(arq.caminho)

        self._gravar_meta(symbol, dia, hashes, n_linhas, parcial=False)

        contagens = self._contagens.pop((symbol, dia), {})
        self._hora_inicio_ns.pop((symbol, dia), None)
        self._hora_fim_ns.pop((symbol, dia), None)
        self._desde_meta.pop((symbol, dia), None)
        self._dia_aberto.pop(symbol, None)
        _logger.info(
            "dia fechado: %s %s — %d eventos (%s)",
            symbol, dia.isoformat(), sum(contagens.values()), contagens,
        )


def _escrever_json_atomico(caminho: Path, dados: dict) -> None:
    """Escreve em `<nome>.tmp` e troca com `os.replace` — atomico no mesmo
    volume, tanto em POSIX quanto em Windows. Um `meta.json` truncado por
    crash no meio da escrita e lido como corrompido por `_ler_meta`, que
    devolve `None`, e o dia SOME do catalogo; a troca atomica garante que o
    que estiver la seja sempre um meta inteiro — o anterior ou o novo."""
    tmp = caminho.parent / (caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def _hash_e_contar_existente(caminho: Path) -> tuple["hashlib._Hash", int]:
    """Reconstroi o hasher a partir das linhas de dados ja presentes no CSV,
    no MESMO formato tab-separado que `_escrever` usa, e devolve quantas
    sao. Chamado so quando o gravador reabre um arquivo que ja existe
    (retomada depois de crash)."""
    hasher = hashlib.sha256()
    n = 0
    with caminho.open("r", newline="", encoding="utf-8") as arquivo:
        leitor = csv.reader(arquivo)
        next(leitor, None)  # cabecalho nao entra no hash
        for linha in leitor:
            hasher.update(("\t".join(linha) + "\n").encode("utf-8"))
            n += 1
    return hasher, n


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
