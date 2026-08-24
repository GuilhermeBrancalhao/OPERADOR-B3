"""Persistencia JSONL.GZ particionada para aprendizado estritamente shadow."""

from __future__ import annotations

import gzip
import json
import math
import os
import re
import uuid
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping

from fluxopro.shadow.modelos import (
    SCHEMA_VERSAO,
    AmostraFeatures,
    ConfigShadow,
    MotivoAmostra,
)
from fluxopro.shadow.governanca import politica_promocao_manifesto
from fluxopro.shadow.rotulos import RotuladorCausal
from fluxopro.shadow.relatorios import gerar_relatorio_particao
from fluxopro.shadow.schema import validar_manifesto, validar_registro


ARQUIVO_FEATURES = "features.jsonl.gz"
ARQUIVO_LABELS = "labels.jsonl.gz"
ARQUIVO_MANIFESTO = "shadow_manifest.json"
ARQUIVO_RUN = "run.json"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BufferShadowCheio(BufferError):
    """Backpressure: o chamador deve executar ``flush()`` e repetir o evento."""


class SidecarShadow:
    """Amostra snapshots e produz rotulos sem tocar parametros de producao.

    A API deliberadamente nao possui ``promover``, ``aplicar`` ou callback de
    configuracao. A unica saida e disco, sob um manifesto que declara
    ``promocao_automatica: false``.
    """

    def __init__(
        self,
        saida_dir: str | Path,
        config: ConfigShadow | None = None,
        *,
        run_id: str | None = None,
    ) -> None:
        self.saida_dir = Path(saida_dir)
        self.config = config or ConfigShadow()
        self.run_id = run_id or uuid.uuid4().hex
        if not _RUN_ID.fullmatch(self.run_id):
            raise ValueError("run_id deve ser identificador seguro de ate 64 caracteres")
        self.run_dir = self.saida_dir / "runs" / self.run_id
        if self.run_dir.exists():
            raise FileExistsError(
                f"execucao shadow imutavel ja existe: {self.run_dir}"
            )
        self._rotulador = RotuladorCausal(self.config)
        self._ultimo_timestamp: dict[str, int] = {}
        self._ultimo_estado: dict[str, str] = {}
        self._ultimo_bucket_periodico: dict[str, int] = {}
        self._sequencia: dict[str, int] = {}
        self._sessao_id: dict[str, int] = {}
        self._proxima_sessao_id = 0
        self._buffer: deque[tuple[str, str, str, dict]] = deque()
        self._particoes_tocadas: set[tuple[str, str]] = set()
        self._finalizado = False
        self.amostras_gravadas = 0
        self.amostras_sem_label_por_capacidade = 0
        self.rotulos_gravados = 0

    @property
    def n_pendentes(self) -> int:
        return self._rotulador.n_pendentes

    @property
    def pendentes_por_simbolo(self) -> dict[str, int]:
        return self._rotulador.pendentes_por_simbolo

    @property
    def n_registros_buffer(self) -> int:
        return len(self._buffer)

    def observar(self, amostra: AmostraFeatures) -> bool:
        """Consome um snapshot causal; retorna se ele foi persistido como feature."""
        if self._finalizado:
            raise RuntimeError("execucao shadow ja finalizada")
        self._validar_relogio_e_capacidade(amostra)

        motivos = self._motivos(amostra)
        n_labels = self._rotulador.quantos_fecham(
            amostra.symbol, amostra.timestamp_ns
        )
        necessarios = n_labels + bool(motivos)
        if len(self._buffer) + necessarios > self.config.max_registros_buffer:
            raise BufferShadowCheio(
                "buffer shadow cheio; execute flush() e repita o mesmo evento"
            )

        # Valida a serializacao antes de alterar relogio, labels ou fila. Em
        # caso de feature invalida o chamador pode corrigir e repetir o evento.
        features_json = _json_compativel(amostra.features) if motivos else None
        qualidade_json = (
            _json_compativel(amostra.qualidade_origem) if motivos else None
        )

        # Primeiro fecha janelas antigas. O rotulador garante que, se este tick
        # estiver depois do limite, ele nao entra no horizonte ja encerrado.
        self._persistir_rotulos(
            self._rotulador.avancar(
                amostra.symbol,
                amostra.timestamp_ns,
                amostra.price_ticks,
                amostra.qualidade_origem,
            )
        )

        self._ultimo_timestamp[amostra.symbol] = amostra.timestamp_ns
        self._ultimo_estado[amostra.symbol] = amostra.estado
        if MotivoAmostra.PERIODICA in motivos:
            self._ultimo_bucket_periodico[amostra.symbol] = (
                amostra.timestamp_ns // self.config.intervalo_amostra_ns
            )
        if not motivos:
            return False

        data_amostra = _data_utc(amostra.timestamp_ns)
        if amostra.symbol not in self._sessao_id:
            self._proxima_sessao_id += 1
            self._sessao_id[amostra.symbol] = self._proxima_sessao_id
        sequencia = self._sequencia.get(amostra.symbol, 0) + 1
        self._sequencia[amostra.symbol] = sequencia
        id_amostra = (
            f"{self.run_id}:{data_amostra}:{amostra.symbol}:"
            f"s{self._sessao_id[amostra.symbol]}:"
            f"{amostra.timestamp_ns}:{sequencia}"
        )

        admitida = self._rotulador.admitir(id_amostra, data_amostra, amostra)
        if not admitida:
            self.amostras_sem_label_por_capacidade += 1
        registro = {
            "schema_versao": SCHEMA_VERSAO,
            "tipo": "features",
            "id_amostra": id_amostra,
            "timestamp_ns": amostra.timestamp_ns,
            "symbol": amostra.symbol,
            "data": data_amostra,
            "price_ticks": amostra.price_ticks,
            "estado": amostra.estado,
            "direcao": amostra.direcao.value if amostra.direcao else None,
            "motivos": [m.value for m in motivos],
            "features": features_json,
            "qualidade_origem": qualidade_json,
            "alvo_preco_ticks": amostra.alvo_preco_ticks,
            "invalidacao_preco_ticks": amostra.invalidacao_preco_ticks,
            "horizontes_s": list(self.config.horizontes_s),
            "label_admitida": admitida,
            "modo": "shadow",
            "promocao_automatica": False,
            "config_versao": self.config.config_versao,
        }
        self._enfileirar(amostra.symbol, data_amostra, ARQUIVO_FEATURES, registro)
        self.amostras_gravadas += 1
        return True

    def flush(self, max_registros: int | None = None) -> int:
        """Persiste lateralmente registros ja ingeridos; nunca cria labels."""
        if max_registros is not None and max_registros < 0:
            raise ValueError("max_registros deve ser nao negativo ou None")
        limite = len(self._buffer) if max_registros is None else min(
            len(self._buffer), max_registros
        )
        escritos = 0
        while escritos < limite:
            symbol, data, nome, registro = self._buffer[0]
            self._escrever(symbol, data, nome, registro)
            self._buffer.popleft()
            escritos += 1
        return escritos

    def resetar_sessao(self, symbol: str) -> int:
        """Censura labels do simbolo antes de apagar qualquer estado causal."""
        n = self._rotulador.n_horizontes_pendentes(symbol)
        if len(self._buffer) + n > self.config.max_registros_buffer:
            raise BufferShadowCheio("flush necessario antes de resetar a sessao")
        self._persistir_rotulos(self._rotulador.censurar(symbol))
        self._ultimo_timestamp.pop(symbol, None)
        self._ultimo_estado.pop(symbol, None)
        self._ultimo_bucket_periodico.pop(symbol, None)
        self._sequencia.pop(symbol, None)
        self._sessao_id.pop(symbol, None)
        return n

    def finalizar(self) -> None:
        """Censura, drena e materializa relatórios imutáveis por partição."""
        if self._finalizado:
            return
        for symbol in self._rotulador.simbolos_pendentes:
            try:
                self.resetar_sessao(symbol)
            except BufferShadowCheio:
                self.flush()
                self.resetar_sessao(symbol)
        self.flush()
        for symbol, data in sorted(self._particoes_tocadas):
            gerar_relatorio_particao(
                self.run_dir / data / symbol,
                run_id=self.run_id,
            )
        if self._particoes_tocadas:
            self._finalizar_run()
        self._finalizado = True

    def fechar(self) -> None:
        self.finalizar()

    def _validar_relogio_e_capacidade(self, amostra: AmostraFeatures) -> None:
        anterior = self._ultimo_timestamp.get(amostra.symbol)
        if anterior is not None and amostra.timestamp_ns < anterior:
            raise ValueError(
                f"evento fora de ordem para {amostra.symbol}: "
                f"{amostra.timestamp_ns} < {anterior}"
            )
        if amostra.symbol not in self._ultimo_timestamp:
            if len(self._ultimo_timestamp) >= self.config.max_simbolos:
                raise OverflowError(
                    "max_simbolos atingido; recuse o simbolo novo ou crie outro sidecar"
                )

    def _motivos(self, amostra: AmostraFeatures) -> tuple[MotivoAmostra, ...]:
        motivos: list[MotivoAmostra] = []
        bucket = amostra.timestamp_ns // self.config.intervalo_amostra_ns
        ultimo_bucket = self._ultimo_bucket_periodico.get(amostra.symbol)
        if ultimo_bucket is None or bucket != ultimo_bucket:
            motivos.append(MotivoAmostra.PERIODICA)

        estado_anterior = self._ultimo_estado.get(amostra.symbol)
        mudou = estado_anterior is not None and amostra.estado != estado_anterior
        if mudou or estado_anterior is None:
            estado = amostra.estado.upper().replace("-", "_")
            if estado in {"PRE_SINAL", "PRÉ_SINAL"}:
                motivos.append(MotivoAmostra.PRE_SINAL)
            elif estado in {"CONFIRMADO", "CONFIRMACAO", "CONFIRMAÇÃO"}:
                motivos.append(MotivoAmostra.CONFIRMACAO)
            elif mudou:
                motivos.append(MotivoAmostra.MUDANCA_ESTADO)
        return tuple(motivos)

    def _persistir_rotulos(self, rotulos: list[dict]) -> None:
        for rotulo in rotulos:
            rotulo["qualidade_origem"] = _json_compativel(
                rotulo["qualidade_origem"]
            )
            self._enfileirar(
                rotulo["symbol"], rotulo["data_amostra"], ARQUIVO_LABELS, rotulo
            )
            self.rotulos_gravados += 1

    def _enfileirar(self, symbol: str, data: str, nome: str, registro: dict) -> None:
        if len(self._buffer) >= self.config.max_registros_buffer:
            raise AssertionError("preflight do buffer shadow falhou")
        colecao = "features" if nome == ARQUIVO_FEATURES else "labels"
        if erros := validar_registro(colecao, registro):
            raise ValueError(f"registro {colecao} fora do schema: {erros}")
        self._buffer.append((symbol, data, nome, registro))

    def _escrever(self, symbol: str, data: str, nome: str, registro: dict) -> None:
        self._garantir_run()
        diretorio = self.run_dir / data / symbol
        diretorio.mkdir(parents=True, exist_ok=True)
        self._particoes_tocadas.add((symbol, data))
        self._garantir_manifesto(diretorio, symbol, data)
        caminho = diretorio / nome
        # Abrir por registro cria membros gzip concatenados, previstos pelo
        # formato e lidos transparentemente por gzip.open. Nao ha handles
        # acumulados por simbolo/dia, logo a memoria nao cresce com particoes.
        with gzip.open(caminho, "at", encoding="utf-8", newline="\n") as arquivo:
            json.dump(
                registro,
                arquivo,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            arquivo.write("\n")

    def _garantir_manifesto(self, diretorio: Path, symbol: str, data: str) -> None:
        caminho = diretorio / ARQUIVO_MANIFESTO
        esperado = {
            "schema_versao": SCHEMA_VERSAO,
            "modo": "shadow",
            "promocao_automatica": False,
            "config_versao": self.config.config_versao,
            "symbol": symbol,
            "data": data,
            "colecoes": {
                "features": ARQUIVO_FEATURES,
                "labels": ARQUIVO_LABELS,
            },
            "horizontes_s": list(self.config.horizontes_s),
            "intervalo_amostra_ns": self.config.intervalo_amostra_ns,
            "limites": {
                "max_pendentes_por_simbolo": self.config.max_pendentes_por_simbolo,
                "max_simbolos": self.config.max_simbolos,
                "max_registros_buffer": self.config.max_registros_buffer,
            },
            "politica_promocao": politica_promocao_manifesto(),
        }
        if erros := validar_manifesto(esperado):
            raise AssertionError(f"manifesto gerado fora do schema: {erros}")
        if caminho.exists():
            existente = json.loads(caminho.read_text(encoding="utf-8"))
            if existente != esperado:
                raise ValueError(f"manifesto shadow incompativel: {caminho}")
        else:
            temporario = caminho.with_suffix(caminho.suffix + ".tmp")
            temporario.write_text(
                json.dumps(esperado, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            os.replace(temporario, caminho)
        # A colecao vazia existe desde o primeiro registro da particao. Isso
        # distingue "ainda sem labels" de "arquivo perdido" na auditoria.
        for nome in (ARQUIVO_FEATURES, ARQUIVO_LABELS):
            arquivo = diretorio / nome
            if not arquivo.exists():
                with gzip.open(arquivo, "wb"):
                    pass

    def _garantir_run(self) -> None:
        caminho = self.run_dir / ARQUIVO_RUN
        if caminho.exists():
            return
        self.run_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "schema_versao": SCHEMA_VERSAO,
            "run_id": self.run_id,
            "status": "OPEN",
            "modo": "shadow",
            "promocao_automatica": False,
            "config_versao": self.config.config_versao,
        }
        _escrever_json_atomico(caminho, payload)

    def _finalizar_run(self) -> None:
        caminho = self.run_dir / ARQUIVO_RUN
        payload = json.loads(caminho.read_text(encoding="utf-8"))
        payload.update(
            status="FINALIZED",
            particoes=[
                {"data": data, "symbol": symbol}
                for symbol, data in sorted(self._particoes_tocadas)
            ],
            amostras_gravadas=self.amostras_gravadas,
            rotulos_gravados=self.rotulos_gravados,
            amostras_sem_label_por_capacidade=(
                self.amostras_sem_label_por_capacidade
            ),
        )
        _escrever_json_atomico(caminho, payload)


def _data_utc(timestamp_ns: int) -> str:
    # Divisao inteira evita arredondar 23:59:59.999999999 para o dia seguinte.
    return datetime.fromtimestamp(timestamp_ns // 1_000_000_000, tz=timezone.utc).date().isoformat()


def _json_compativel(valor: object) -> object:
    if isinstance(valor, Enum):
        return valor.value
    if is_dataclass(valor) and not isinstance(valor, type):
        return _json_compativel(asdict(valor))
    if isinstance(valor, Mapping):
        return {str(k): _json_compativel(v) for k, v in valor.items()}
    if isinstance(valor, (tuple, list)):
        return [_json_compativel(v) for v in valor]
    if isinstance(valor, (set, frozenset)):
        return [_json_compativel(v) for v in sorted(valor, key=repr)]
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ValueError("JSON shadow nao aceita NaN ou infinito")
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    raise TypeError(f"feature nao serializavel em JSON: {type(valor).__name__}")


def _escrever_json_atomico(caminho: Path, payload: dict) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    os.replace(temporario, caminho)


# Nome alternativo explicito para integradores que usam o substantivo primeiro.
ShadowSidecar = SidecarShadow
