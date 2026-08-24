"""Auditoria ASG: ordem, schema shadow streaming, reports e Human Gate.

Sem ``--shadow-dir`` o resultado shadow e explicitamente ``SKIPPED``. Use
``--report-dir`` para materializar ``report.json`` e ``report.md``.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import gzip
import json
import re
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

_RAIZ_SCRIPT = Path(__file__).resolve().parent.parent
if str(_RAIZ_SCRIPT) not in sys.path:
    sys.path.insert(0, str(_RAIZ_SCRIPT))

from fluxopro.shadow.governanca import politica_promocao_manifesto
from fluxopro.shadow.schema import validar_manifesto, validar_registro


COLECOES_ESPERADAS = frozenset({"features", "labels"})
ARQUIVOS_ESPERADOS = {"features": "features.jsonl.gz", "labels": "labels.jsonl.gz"}
ARQUIVO_MANIFESTO = "shadow_manifest.json"
ARQUIVOS_RELATORIO = ("report.json", "report.md")
_DATA_PARTICAO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_ACHADOS = 1_000
MAX_LINHA_BYTES = 4 * 1024 * 1024

ALLOWLIST_TESTES_PADRAO = (
    "tests/test_sem_execucao.py",
    "tests/test_auditoria_asg.py",
)

_NOMES_EXECUCAO = frozenset(
    {
        "order_send", "order_check", "send_order", "place_order",
        "submit_order", "create_order", "new_order", "cancel_order",
        "delete_order", "replace_order", "modify_order", "execute_order",
        "placeorder", "submitorder", "cancelorder", "open_position",
        "close_position", "enviar_ordem", "criar_ordem", "cancelar_ordem",
        "alterar_ordem", "executar_ordem", "abrir_posicao", "fechar_posicao",
    }
)
_PACOTES_CORRETORA = (
    "MetaTrader5", "alpaca", "alpaca_trade_api", "ib_insync", "ibapi",
    "ccxt", "binance",
)
_CONSTANTE_EXECUCAO = re.compile(
    r"^(TRADE_ACTION_(DEAL|PENDING|MODIFY|REMOVE)|ORDER_TYPE_(BUY|SELL).*)$",
    re.IGNORECASE,
)
_RADICAL_CORRETORA = re.compile(
    r"(mt5|broker|brokerage|corretora|exchange|trading|order|ordem)", re.IGNORECASE
)
_ENDPOINT_ORDEM = re.compile(
    r"/(orders?|positions?|trades?)(?:[/?#]|$)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Achado:
    codigo: str
    caminho: str
    detalhe: str
    linha: int | None = None

    def texto(self) -> str:
        local = self.caminho + (f":{self.linha}" if self.linha else "")
        return f"[{self.codigo}] {local}: {self.detalhe}"


@dataclass(frozen=True, slots=True)
class RelatorioAuditoria:
    achados: tuple[Achado, ...]
    arquivos_python_inspecionados: int
    particoes_shadow_inspecionadas: int
    registros_shadow_inspecionados: int
    status_ordens: str
    status_shadow: str

    @property
    def aprovado(self) -> bool:
        return self.status_ordens == "PASS" and self.status_shadow != "FAIL"


def auditar_repositorio(
    raiz: str | Path,
    shadow_dir: str | Path | None = None,
    allowlist_testes: tuple[str, ...] = ALLOWLIST_TESTES_PADRAO,
) -> RelatorioAuditoria:
    raiz = Path(raiz).resolve()
    achados_ordem, n_python = auditar_ausencia_ordens(raiz, allowlist_testes)
    achados_shadow: list[Achado] = []
    n_particoes = n_registros = 0
    status_shadow = "SKIPPED"
    if shadow_dir is not None:
        caminho_shadow = Path(shadow_dir)
        if not caminho_shadow.is_absolute():
            caminho_shadow = raiz / caminho_shadow
        achados_shadow, n_particoes, n_registros = _auditar_particoes_detalhado(
            caminho_shadow
        )
        status_shadow = "FAIL" if achados_shadow else "PASS"
    achados = tuple((achados_ordem + achados_shadow)[:MAX_ACHADOS])
    return RelatorioAuditoria(
        achados,
        n_python,
        n_particoes,
        n_registros,
        "FAIL" if achados_ordem else "PASS",
        status_shadow,
    )


def auditar_ausencia_ordens(
    raiz: Path,
    allowlist_testes: tuple[str, ...] = ALLOWLIST_TESTES_PADRAO,
) -> tuple[list[Achado], int]:
    achados: list[Achado] = []
    inspecionados = 0
    for caminho in _arquivos_python(raiz):
        relativo = caminho.relative_to(raiz).as_posix()
        if any(fnmatch.fnmatch(relativo, padrao) for padrao in allowlist_testes):
            continue
        inspecionados += 1
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"), str(caminho))
        except (OSError, UnicodeDecodeError, SyntaxError) as erro:
            _add(achados, Achado("PY_INVALIDO", relativo, str(erro)))
            continue
        for achado in _achados_execucao(arvore, relativo):
            _add(achados, achado)
    return achados, inspecionados


def auditar_particoes_shadow(shadow_dir: Path) -> tuple[list[Achado], int]:
    achados, particoes, _registros = _auditar_particoes_detalhado(shadow_dir)
    return achados, particoes


def _auditar_particoes_detalhado(
    shadow_dir: Path,
) -> tuple[list[Achado], int, int]:
    achados: list[Achado] = []
    if not shadow_dir.exists():
        return [Achado("SHADOW_AUSENTE", str(shadow_dir), "diretorio nao existe")], 0, 0
    n_particoes = n_registros = 0
    candidatos: set[Path] = set()
    for item in shadow_dir.rglob("*"):
        if item.is_dir() and _DATA_PARTICAO.fullmatch(item.parent.name):
            candidatos.add(item)
    for symbol_dir in sorted(candidatos):
        data_dir = symbol_dir.parent
        if symbol_dir.is_dir():
            n_particoes += 1
            n_registros += _auditar_particao(
                shadow_dir, data_dir, symbol_dir, achados
            )
    if n_particoes == 0:
        _add(
            achados,
            Achado(
                "PARTICAO_AUSENTE", str(shadow_dir),
                "nenhuma particao data/symbol foi encontrada",
            ),
        )
    return achados, n_particoes, n_registros


def _auditar_particao(
    shadow_dir: Path, data_dir: Path, symbol_dir: Path, achados: list[Achado]
) -> int:
    relativo_dir = symbol_dir.relative_to(shadow_dir).as_posix()
    manifesto_path = symbol_dir / ARQUIVO_MANIFESTO
    if not manifesto_path.is_file():
        _add(
            achados,
            Achado(
                "MANIFESTO_AUSENTE", f"{relativo_dir}/{ARQUIVO_MANIFESTO}",
                "particao sem manifesto",
            ),
        )
        return 0
    manifesto = _ler_json(manifesto_path, shadow_dir, achados)
    if manifesto is None:
        return 0
    for erro in validar_manifesto(manifesto):
        codigo = (
            "PROMOCAO_AUTOMATICA"
            if erro == "promocao_automatica deve ser false"
            else "POLITICA_PROMOCAO_INVALIDA"
            if "politica_promocao" in erro
            else "MANIFESTO_SCHEMA"
        )
        _add(achados, Achado(codigo, relativo_dir, erro))
    if isinstance(manifesto, dict) and (
        manifesto.get("data") != data_dir.name
        or manifesto.get("symbol") != symbol_dir.name
    ):
        _add(
            achados,
            Achado(
                "PARTICAO_DIVERGENTE", relativo_dir,
                "layout deve ser data/symbol e coincidir com manifesto",
            ),
        )
    run_path = data_dir.parent / "run.json"
    run_meta = _ler_json(run_path, shadow_dir, achados) if run_path.is_file() else None
    if run_meta is None:
        _add(
            achados,
            Achado(
                "RUN_MANIFEST_AUSENTE",
                data_dir.parent.relative_to(shadow_dir).as_posix(),
                "particao deve pertencer a uma execucao isolada e persistida",
            ),
        )
    elif not isinstance(run_meta, dict) or (
        run_meta.get("status") != "FINALIZED"
        or run_meta.get("run_id") != data_dir.parent.name
        or run_meta.get("promocao_automatica") is not False
    ):
        _add(
            achados,
            Achado(
                "RUN_MANIFEST_INVALIDO",
                run_path.relative_to(shadow_dir).as_posix(),
                "run_id, status final ou bloqueio de promocao invalido",
            ),
        )
    paths = {
        nome: symbol_dir / arquivo for nome, arquivo in ARQUIVOS_ESPERADOS.items()
    }
    for colecao, caminho in paths.items():
        if not caminho.is_file():
            _add(
                achados,
                Achado(
                    "ARQUIVO_AUSENTE",
                    caminho.relative_to(shadow_dir).as_posix(),
                    f"colecao {colecao} ausente",
                ),
            )
    if not all(caminho.is_file() for caminho in paths.values()):
        return 0
    for nome in ARQUIVOS_RELATORIO:
        caminho = symbol_dir / nome
        if not caminho.is_file():
            _add(
                achados,
                Achado(
                    "RELATORIO_AUSENTE",
                    caminho.relative_to(shadow_dir).as_posix(),
                    "finalizacao shadow deve produzir report.json e report.md",
                ),
            )
    report_json = symbol_dir / "report.json"
    if report_json.is_file():
        relatorio = _ler_json(report_json, shadow_dir, achados)
        if not isinstance(relatorio, dict) or (
            relatorio.get("status") != "FINALIZED"
            or relatorio.get("data") != data_dir.name
            or relatorio.get("symbol") != symbol_dir.name
            or (
                isinstance(run_meta, dict)
                and relatorio.get("run_id") != run_meta.get("run_id")
            )
            or relatorio.get("promocao", {}).get("aplicacao_automatica") is not False
        ):
            _add(
                achados,
                Achado(
                    "RELATORIO_INVALIDO",
                    report_json.relative_to(shadow_dir).as_posix(),
                    "status, particao ou bloqueio de promocao invalido",
                ),
            )
    return _validar_streams_exatos(paths, shadow_dir, achados, manifesto)


def _validar_streams_exatos(
    paths: dict[str, Path],
    shadow_dir: Path,
    achados: list[Achado],
    manifesto: object,
) -> int:
    n_registros = 0
    with tempfile.TemporaryDirectory(prefix="auditoria-asg-") as temporario:
        banco = sqlite3.connect(str(Path(temporario) / "ids.sqlite3"))
        banco.execute("CREATE TABLE features (id TEXT PRIMARY KEY)")
        for n, registro in _iter_jsonl_gz(paths["features"], shadow_dir, achados):
            n_registros += 1
            _validar_linha(
                "features", paths["features"], n, registro, shadow_dir, achados,
                manifesto,
            )
            id_amostra = registro.get("id_amostra") if isinstance(registro, dict) else None
            if isinstance(id_amostra, str):
                try:
                    banco.execute("INSERT INTO features(id) VALUES (?)", (id_amostra,))
                except sqlite3.IntegrityError:
                    _add(
                        achados,
                        Achado(
                            "ID_DUPLICADO",
                            paths["features"].relative_to(shadow_dir).as_posix(),
                            id_amostra,
                            n,
                        ),
                    )
        banco.commit()
        for n, registro in _iter_jsonl_gz(paths["labels"], shadow_dir, achados):
            n_registros += 1
            _validar_linha(
                "labels", paths["labels"], n, registro, shadow_dir, achados,
                manifesto,
            )
            id_amostra = registro.get("id_amostra") if isinstance(registro, dict) else None
            if isinstance(id_amostra, str):
                existe = banco.execute(
                    "SELECT 1 FROM features WHERE id = ?", (id_amostra,)
                ).fetchone()
                if existe is None:
                    _add(
                        achados,
                        Achado(
                            "LABEL_ORFAO",
                            paths["labels"].relative_to(shadow_dir).as_posix(),
                            id_amostra,
                            n,
                        ),
                    )
        banco.close()
    return n_registros


def _validar_linha(
    colecao: str,
    caminho: Path,
    linha: int,
    registro: object,
    shadow_dir: Path,
    achados: list[Achado],
    manifesto: object,
) -> None:
    for erro in validar_registro(colecao, registro):
        codigo = (
            "PROMOCAO_AUTOMATICA"
            if erro == "promocao_automatica deve ser false"
            else "REGISTRO_SCHEMA"
        )
        _add(
            achados,
            Achado(
                codigo,
                caminho.relative_to(shadow_dir).as_posix(),
                erro,
                linha,
            ),
        )
    if not isinstance(registro, dict) or not isinstance(manifesto, dict):
        return
    data = registro.get("data", registro.get("data_amostra"))
    if registro.get("symbol") != caminho.parent.name or data != caminho.parent.parent.name:
        _add(
            achados,
            Achado(
                "REGISTRO_PARTICAO",
                caminho.relative_to(shadow_dir).as_posix(),
                "symbol/data do registro divergem da particao",
                linha,
            ),
        )
    if registro.get("config_versao") != manifesto.get("config_versao"):
        _add(
            achados,
            Achado(
                "CONFIG_DIVERGENTE",
                caminho.relative_to(shadow_dir).as_posix(),
                "config_versao diverge do manifesto",
                linha,
            ),
        )
    horizontes = manifesto.get("horizontes_s")
    if colecao == "features" and registro.get("horizontes_s") != horizontes:
        _add(
            achados,
            Achado(
                "HORIZONTES_DIVERGENTES",
                caminho.relative_to(shadow_dir).as_posix(),
                "feature diverge do manifesto",
                linha,
            ),
        )
    if colecao == "labels" and registro.get("horizonte_s") not in (horizontes or []):
        _add(
            achados,
            Achado(
                "HORIZONTE_NAO_DECLARADO",
                caminho.relative_to(shadow_dir).as_posix(),
                "label usa horizonte ausente do manifesto",
                linha,
            ),
        )


def _iter_jsonl_gz(
    caminho: Path, shadow_dir: Path, achados: list[Achado]
) -> Iterator[tuple[int, object]]:
    relativo = caminho.relative_to(shadow_dir).as_posix()
    try:
        with gzip.open(caminho, "rb") as arquivo:
            n = 0
            while True:
                bruto = arquivo.readline(MAX_LINHA_BYTES + 1)
                if not bruto:
                    break
                n += 1
                if len(bruto) > MAX_LINHA_BYTES and not bruto.endswith(b"\n"):
                    _add(
                        achados,
                        Achado(
                            "LINHA_EXCESSIVA", relativo,
                            f"linha excede {MAX_LINHA_BYTES} bytes", n,
                        ),
                    )
                    while bruto and not bruto.endswith(b"\n"):
                        bruto = arquivo.readline(MAX_LINHA_BYTES + 1)
                    continue
                if not bruto.strip():
                    continue
                try:
                    valor = json.loads(
                        bruto.decode("utf-8"), parse_constant=_rejeitar_constante_json
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as erro:
                    _add(achados, Achado("JSONL_INVALIDO", relativo, str(erro), n))
                    continue
                yield n, valor
    except OSError as erro:
        _add(achados, Achado("GZIP_INVALIDO", relativo, str(erro)))


def _ler_json(caminho: Path, raiz: Path, achados: list[Achado]) -> object | None:
    try:
        return json.loads(
            caminho.read_text(encoding="utf-8"),
            parse_constant=_rejeitar_constante_json,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as erro:
        _add(
            achados,
            Achado(
                "MANIFESTO_INVALIDO",
                caminho.relative_to(raiz).as_posix(),
                str(erro),
            ),
        )
        return None


def _rejeitar_constante_json(valor: str) -> None:
    raise ValueError(f"constante JSON nao finita: {valor}")


def _arquivos_python(raiz: Path) -> Iterator[Path]:
    ignorados = {".git", ".claude", ".venv", "venv", "build", "dist", "__pycache__"}
    for caminho in raiz.rglob("*.py"):
        partes = caminho.relative_to(raiz).parts
        if any(parte in ignorados or parte.startswith(".") for parte in partes):
            continue
        yield caminho


def _achados_execucao(arvore: ast.AST, caminho: str) -> list[Achado]:
    achados: list[Achado] = []
    taint, tem_corretora = _taint_corretora(arvore)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            _auditar_chamada(no, caminho, taint, tem_corretora, achados)
        elif isinstance(no, ast.Attribute):
            nome = no.attr.lower()
            if nome in _NOMES_EXECUCAO or (
                nome in {"buy", "sell", "market_order"}
                and _expr_tainted(no.value, taint)
            ):
                _add(
                    achados,
                    Achado("API_ORDEM", caminho, f"referencia a {no.attr}", no.lineno),
                )
            elif _CONSTANTE_EXECUCAO.match(no.attr):
                _add(
                    achados,
                    Achado("CONSTANTE_ORDEM", caminho, f"uso de {no.attr}", no.lineno),
                )
        elif isinstance(no, ast.Name) and _CONSTANTE_EXECUCAO.match(no.id):
            _add(achados, Achado("CONSTANTE_ORDEM", caminho, f"uso de {no.id}", no.lineno))
        elif isinstance(no, ast.ImportFrom):
            for alias in no.names:
                if alias.name.lower() in _NOMES_EXECUCAO:
                    _add(
                        achados,
                        Achado("API_ORDEM", caminho, f"import de {alias.name}", no.lineno),
                    )
        elif isinstance(no, ast.Subscript) and _subscript_corretora(no, taint):
            _add(
                achados,
                Achado(
                    "API_CORRETORA_DINAMICA", caminho,
                    "acesso por dicionario/indice sobre cliente de corretora", no.lineno,
                ),
            )
    return list(dict.fromkeys(achados))


def _auditar_chamada(
    no: ast.Call,
    caminho: str,
    taint: set[str],
    tem_corretora: bool,
    achados: list[Achado],
) -> None:
    nome = _nome_chamada(no.func)
    if isinstance(no.func, ast.Name) and nome and nome.lower() in _NOMES_EXECUCAO:
        _add(achados, Achado("API_ORDEM", caminho, f"chamada de {nome}", no.lineno))
    if (
        tem_corretora
        and isinstance(no.func, ast.Name)
        and no.func.id in {"eval", "exec", "compile"}
    ):
        _add(
            achados,
            Achado("EXECUCAO_DINAMICA", caminho, f"uso de {no.func.id}", no.lineno),
        )
    base_reflexao: ast.expr | None = None
    nome_reflexao: ast.expr | None = None
    if nome == "getattr" and len(no.args) >= 2:
        base_reflexao, nome_reflexao = no.args[0], no.args[1]
    elif nome == "__getattribute__" and isinstance(no.func, ast.Attribute) and no.args:
        base_reflexao, nome_reflexao = no.func.value, no.args[0]
    elif nome == "attrgetter" and no.args:
        nome_reflexao = no.args[0]
    if nome_reflexao is not None:
        alvo = _texto_constante(nome_reflexao)
        base_suspeita = (
            (base_reflexao is not None and _expr_tainted(base_reflexao, taint))
            or tem_corretora
        )
        if alvo is not None and alvo.lower() in _NOMES_EXECUCAO:
            _add(
                achados,
                Achado("API_ORDEM_DINAMICA", caminho, f"reflexao para {alvo}", no.lineno),
            )
        elif alvo is None and base_suspeita:
            _add(
                achados,
                Achado(
                    "API_CORRETORA_DINAMICA", caminho,
                    "reflexao dinamica em modulo que importa corretora", no.lineno,
                ),
            )
    if nome in {"__import__", "import_module"} and no.args:
        modulo = _texto_constante(no.args[0])
        if modulo is None or modulo.startswith(_PACOTES_CORRETORA):
            _add(
                achados,
                Achado(
                    "IMPORT_DINAMICO_CORRETORA", caminho,
                    "import dinamico pode carregar API de corretora", no.lineno,
                ),
            )
    if isinstance(no.func, ast.Attribute) and no.func.attr.lower() == "post" and no.args:
        endpoint = _texto_constante(no.args[0])
        if endpoint and _ENDPOINT_ORDEM.search(endpoint):
            _add(achados, Achado("ENDPOINT_ORDEM", caminho, endpoint, no.lineno))


def _taint_corretora(arvore: ast.AST) -> tuple[set[str], bool]:
    taint: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                if alias.name.startswith(_PACOTES_CORRETORA):
                    taint.add(alias.asname or alias.name.split(".")[0])
        elif (
            isinstance(no, ast.ImportFrom)
            and no.module
            and no.module.startswith(_PACOTES_CORRETORA)
        ):
            taint.update(alias.asname or alias.name for alias in no.names)
    mudou = True
    while mudou:
        mudou = False
        for no in ast.walk(arvore):
            if isinstance(no, (ast.Assign, ast.AnnAssign)):
                valor = no.value
                alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
                if valor is not None and _expr_tainted(valor, taint):
                    for alvo in alvos:
                        nome = _alvo_nome(alvo)
                        if nome and nome not in taint:
                            taint.add(nome)
                            mudou = True
    return taint, bool(taint)


def _expr_tainted(no: ast.expr, taint: set[str]) -> bool:
    if isinstance(no, ast.Name):
        return no.id in taint or bool(_RADICAL_CORRETORA.search(no.id))
    if isinstance(no, ast.Attribute):
        return no.attr in taint or _expr_tainted(no.value, taint)
    if isinstance(no, ast.Subscript):
        return _expr_tainted(no.value, taint)
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "vars":
        return bool(no.args and _expr_tainted(no.args[0], taint))
    return False


def _subscript_corretora(no: ast.Subscript, taint: set[str]) -> bool:
    base = no.value
    if isinstance(base, ast.Attribute) and base.attr == "__dict__":
        return _expr_tainted(base.value, taint)
    if isinstance(base, ast.Call) and isinstance(base.func, ast.Name) and base.func.id == "vars":
        return bool(base.args and _expr_tainted(base.args[0], taint))
    return False


def _alvo_nome(no: ast.expr) -> str | None:
    if isinstance(no, ast.Name):
        return no.id
    if isinstance(no, ast.Attribute):
        return no.attr
    return None


def _nome_chamada(no: ast.expr) -> str | None:
    if isinstance(no, ast.Name):
        return no.id
    if isinstance(no, ast.Attribute):
        return no.attr
    return None


def _texto_constante(no: ast.expr) -> str | None:
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        esquerda = _texto_constante(no.left)
        direita = _texto_constante(no.right)
        return esquerda + direita if esquerda is not None and direita is not None else None
    return None


def _add(achados: list[Achado], achado: Achado) -> None:
    if len(achados) < MAX_ACHADOS:
        achados.append(achado)


def gerar_relatorios(
    relatorio: RelatorioAuditoria, destino: str | Path
) -> tuple[Path, Path]:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    report_json = destino / "report.json"
    report_md = destino / "report.md"
    status = (
        "FAIL"
        if not relatorio.aprovado
        else "SKIPPED"
        if relatorio.status_shadow == "SKIPPED"
        else "PASS"
    )
    payload = {
        "status": status,
        "status_ordens": relatorio.status_ordens,
        "status_shadow": relatorio.status_shadow,
        "arquivos_python_inspecionados": relatorio.arquivos_python_inspecionados,
        "particoes_shadow_inspecionadas": relatorio.particoes_shadow_inspecionadas,
        "registros_shadow_inspecionados": relatorio.registros_shadow_inspecionados,
        "achados": [asdict(achado) for achado in relatorio.achados],
        "politica_promocao": {
            "status": "BLOQUEADA_POR_PADRAO",
            **politica_promocao_manifesto(),
        },
    }
    report_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    linhas = [
        "# Auditoria ASG", "",
        f"- Resultado: **{payload['status']}**",
        f"- APIs de ordem: **{relatorio.status_ordens}**",
        f"- Shadow: **{relatorio.status_shadow}**",
        f"- Python inspecionado: {relatorio.arquivos_python_inspecionados}",
        f"- Partições shadow: {relatorio.particoes_shadow_inspecionadas}",
        f"- Registros shadow: {relatorio.registros_shadow_inspecionados}", "",
        "## Política de promoção", "",
        (
            "**BLOQUEADA POR PADRÃO.** Não há aplicação automática. Uma candidata só "
            "fica elegível para revisão humana após 20 pregões, 10.000 amostras, "
            "walk-forward aprovado, limite inferior do CI acima do baseline, degradação "
            "de guardrail de no máximo 5%, configuração versionada, rollback testado e "
            "aprovação humana identificada."
        ),
        "", "## Achados", "",
    ]
    linhas.extend(
        ["Nenhum."] if not relatorio.achados
        else [f"- {achado.texto()}" for achado in relatorio.achados]
    )
    report_md.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return report_json, report_md


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--shadow-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument(
        "--exigir-shadow",
        action="store_true",
        help="falha quando --shadow-dir não foi fornecido ou não foi aprovado",
    )
    parser.add_argument("--permitir-teste", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    allowlist = ALLOWLIST_TESTES_PADRAO + tuple(args.permitir_teste)
    relatorio = auditar_repositorio(args.raiz, args.shadow_dir, allowlist)
    print(f"ORDENS: {relatorio.status_ordens}")
    if relatorio.status_shadow == "SKIPPED":
        print("SHADOW: SKIPPED - --shadow-dir nao fornecido")
    else:
        print(
            f"SHADOW: {relatorio.status_shadow} — "
            f"{relatorio.particoes_shadow_inspecionadas} particoes, "
            f"{relatorio.registros_shadow_inspecionados} registros"
        )
    for achado in relatorio.achados:
        print(achado.texto())
    if args.report_dir is not None:
        report_json, report_md = gerar_relatorios(relatorio, args.report_dir)
        print(f"REPORTS: {report_json} | {report_md}")
    aprovado = relatorio.aprovado and (
        not args.exigir_shadow or relatorio.status_shadow == "PASS"
    )
    return 0 if aprovado else 1


if __name__ == "__main__":
    raise SystemExit(main())
