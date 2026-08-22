"""Catálogo: indexa o que o `Gravador` já gravou (varrendo `meta.json` por
`{saida}/{symbol}/{data}/`) e responde consultas do tipo "me dá o replay do
WDO de 2026-08-20 das 09:00 às 10:30" — é o que transforma uma pilha de CSVs
numa biblioteca utilizável em vez de só um diretório cheio de arquivo.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path

from fluxopro.gravacao import formato

_logger = logging.getLogger("fluxopro.gravacao.catalogo")


@dataclass(frozen=True, slots=True)
class EntradaCatalogo:
    symbol: str
    data: date
    diretorio: Path
    schema_versao: int
    contagens: dict[str, int]
    n_eventos_total: int
    hora_inicio_ns: int | None
    hora_fim_ns: int | None
    hashes_sha256: dict[str, str]
    # Quantas linhas de DADOS cada hash cobre. Presente nos metas escritos a
    # partir da correcao de durabilidade da R5 (checkpoint parcial); ausente
    # — dict vazio — nos metas antigos, e nesse caso o hash cobre o arquivo
    # inteiro. Ver `verificar_integridade` e `Gravador._checkpoint_meta`.
    n_linhas_hasheadas: dict[str, int] = field(default_factory=dict)
    # True enquanto o dia ainda esta sendo gravado (meta de checkpoint).
    parcial: bool = False

    def arquivo(self, nome_base: str) -> Path | None:
        """Caminho do arquivo (aceita comprimido `.gz` ou não) para um dos
        nomes em `formato.NOMES_ARQUIVO`, ou None se não existir."""
        candidato_gz = self.diretorio / (nome_base + ".gz")
        candidato_plano = self.diretorio / nome_base
        if candidato_gz.exists():
            return candidato_gz
        if candidato_plano.exists():
            return candidato_plano
        return None


class Catalogo:
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._entradas: dict[tuple[str, date], EntradaCatalogo] = {}

    def escanear(self) -> list[EntradaCatalogo]:
        """Varre `base_dir` inteiro e (re)constrói o índice em memória.
        Barato o bastante para chamar de novo a qualquer momento — não há
        estado incremental para ficar dessincronizado."""
        self._entradas.clear()
        if not self._base.is_dir():
            return []

        for symbol_dir in sorted(self._base.iterdir()):
            if not symbol_dir.is_dir():
                continue
            for dia_dir in sorted(symbol_dir.iterdir()):
                meta_path = dia_dir / "meta.json"
                if not meta_path.is_file():
                    continue
                entrada = _ler_meta(meta_path, dia_dir)
                if entrada is not None:
                    self._entradas[(entrada.symbol, entrada.data)] = entrada

        return list(self._entradas.values())

    def listar(self, symbol: str | None = None) -> list[EntradaCatalogo]:
        entradas = list(self._entradas.values())
        if symbol is not None:
            entradas = [e for e in entradas if e.symbol == symbol]
        return sorted(entradas, key=lambda e: (e.symbol, e.data))

    def consultar(self, symbol: str, data: date) -> EntradaCatalogo | None:
        return self._entradas.get((symbol, data))

    def consultar_intervalo(
        self,
        symbol: str,
        data: date,
        hora_inicio: time | None = None,
        hora_fim: time | None = None,
    ) -> tuple[EntradaCatalogo | None, int | None, int | None]:
        """Resolve "WDO de <data> das <hora_inicio> às <hora_fim>" para uma
        entrada do catálogo + o intervalo em `timestamp_ns` (UTC) que o
        leitor de gravação deve filtrar. Retorna `(None, None, None)` se o
        dia não estiver gravado."""
        entrada = self.consultar(symbol, data)
        if entrada is None:
            return None, None, None

        ts_inicio = None
        ts_fim = None
        if hora_inicio is not None:
            dt_inicio = datetime.combine(data, hora_inicio, tzinfo=timezone.utc)
            ts_inicio = int(dt_inicio.timestamp() * 1e9)
        if hora_fim is not None:
            dt_fim = datetime.combine(data, hora_fim, tzinfo=timezone.utc)
            ts_fim = int(dt_fim.timestamp() * 1e9)
        return entrada, ts_inicio, ts_fim

    def verificar_integridade(self, entrada: EntradaCatalogo) -> dict[str, bool]:
        """Recalcula o hash sha256 de cada arquivo gravado (linhas
        tab-separadas, mesmo formato usado pelo `Gravador` ao escrever) e
        compara com o que está no `meta.json`. Detecta arquivo truncado,
        editado à mão ou corrompido em transporte.

        Metas de CHECKPOINT (`parcial=True`, escritos durante o pregao) e
        metas de dia retomado depois de crash trazem `n_linhas_hasheadas`:
        o hash cobre as N PRIMEIRAS linhas de dados, nao o arquivo todo.
        Isso e o que torna o checkpoint verificavel — depois de um crash o
        CSV costuma ter MAIS linhas do que o ultimo checkpoint descreveu (as
        que o `flush` levou ao SO entre o checkpoint e a morte do processo),
        e comparar o hash do arquivo inteiro contra o hash de um prefixo
        reprovaria um dado intacto. Arquivo com MENOS linhas que o meta
        declara continua reprovando: isso e truncamento.

        Contrato: este método NUNCA deixa uma exceção de leitura escapar —
        gzip truncado, EOF inesperado, byte inválido etc. contam como
        integridade invalida (`False`), não como crash. Isso importa porque
        é a única defesa contra gravação corrompida (não existe fonte
        externa de histórico de book para WDO/WIN, ver docstring de
        `gravador.py`); se o contrato fosse "levanta uma exceção às vezes,
        um dict às vezes", um chamador que só testasse o caminho feliz
        deixaria passar despercebido um arquivo corrompido cujo erro de
        leitura não é o esperado.
        """
        resultado: dict[str, bool] = {}
        for nome_base, hash_esperado in entrada.hashes_sha256.items():
            caminho = entrada.arquivo(nome_base)
            if caminho is None:
                resultado[nome_base] = False
                continue
            try:
                hash_real = _hash_arquivo(
                    caminho, entrada.n_linhas_hasheadas.get(nome_base)
                )
            except (OSError, EOFError, UnicodeDecodeError, ValueError):
                _logger.warning(
                    "falha ao ler %s para verificacao de integridade "
                    "(arquivo truncado/corrompido?) — marcando invalido",
                    caminho,
                )
                resultado[nome_base] = False
                continue
            resultado[nome_base] = hash_real == hash_esperado
        return resultado


def _hash_arquivo(caminho: Path, n_linhas: int | None = None) -> str:
    """Hash das linhas de dados; com `n_linhas`, so das N primeiras.

    Nao ha guarda separada para "o arquivo tem MENOS linhas que N": ela seria
    inalcancavel na pratica, porque o sha256 de um prefixo de M linhas so
    coincide com o de um prefixo de N linhas quando M == N — truncamento ja
    reprova pela comparacao de hash. Linha defensiva que nenhuma mutacao
    consegue matar e peso morto, e este projeto ja aprendeu (R5, mutantes
    O01/O03/O08) que o que nao tem assercao nao esta decidido."""
    import csv
    import gzip

    abrir = gzip.open if caminho.suffix == ".gz" else open
    hasher = hashlib.sha256()
    lidas = 0
    with abrir(caminho, "rt", newline="", encoding="utf-8") as arquivo:
        leitor = csv.reader(arquivo)
        next(leitor, None)  # cabecalho nao entra no hash (Gravador so hasheia dados)
        for linha in leitor:
            if n_linhas is not None and lidas >= n_linhas:
                break
            hasher.update(("\t".join(linha) + "\n").encode("utf-8"))
            lidas += 1
    return hasher.hexdigest()


def _ler_meta(meta_path: Path, diretorio: Path) -> EntradaCatalogo | None:
    try:
        bruto = json.loads(meta_path.read_text(encoding="utf-8"))
        return EntradaCatalogo(
            symbol=bruto["symbol"],
            data=date.fromisoformat(bruto["data"]),
            diretorio=diretorio,
            schema_versao=bruto["schema_versao"],
            contagens=bruto["contagens"],
            n_eventos_total=bruto["n_eventos_total"],
            hora_inicio_ns=bruto["hora_inicio_ns"],
            hora_fim_ns=bruto["hora_fim_ns"],
            hashes_sha256=bruto["hashes_sha256"],
            n_linhas_hasheadas=bruto.get("n_linhas_hasheadas") or {},
            parcial=bool(bruto.get("parcial", False)),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
