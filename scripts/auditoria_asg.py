"""Auditoria automatizada dos guardrails ASG-like.

Verifica duas fronteiras independentes:

* chamadas de execucao de ordens (inclusive nomes equivalentes e ``getattr``
  dinamico) fora de uma allowlist fechada de testes;
* particoes do sidecar com manifesto shadow e as colecoes JSONL.GZ esperadas.

Uso::

    python scripts/auditoria_asg.py --raiz . --shadow-dir dados/shadow

O codigo de saida e 0 somente quando nenhuma violacao for encontrada.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path


COLECOES_ESPERADAS = frozenset({"features", "labels"})
ARQUIVOS_ESPERADOS = {
    "features": "features.jsonl.gz",
    "labels": "labels.jsonl.gz",
}
ARQUIVO_MANIFESTO = "shadow_manifest.json"

# Lista fechada: estes testes precisam citar APIs proibidas para provar que a
# propria auditoria reprova mutacoes. Um teste novo nao ganha excecao por estar
# sob tests/; precisa entrar conscientemente aqui.
ALLOWLIST_TESTES_PADRAO = (
    "tests/test_sem_execucao.py",
    "tests/test_auditoria_asg.py",
)

_NOMES_EXECUCAO = frozenset(
    {
        "order_send",
        "order_check",
        "send_order",
        "place_order",
        "submit_order",
        "create_order",
        "new_order",
        "cancel_order",
        "delete_order",
        "replace_order",
        "modify_order",
        "execute_order",
        "placeorder",
        "submitorder",
        "cancelorder",
        "open_position",
        "close_position",
        "enviar_ordem",
        "criar_ordem",
        "cancelar_ordem",
        "alterar_ordem",
        "executar_ordem",
        "abrir_posicao",
        "fechar_posicao",
    }
)
_CONSTANTE_EXECUCAO = re.compile(
    r"^(TRADE_ACTION_(DEAL|PENDING|MODIFY|REMOVE)|ORDER_TYPE_(BUY|SELL).*)$",
    re.IGNORECASE,
)
_RADICAL_DINAMICO = re.compile(
    r"(order|ordem|position|posicao|posição|trade_action)", re.IGNORECASE
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

    @property
    def aprovado(self) -> bool:
        return not self.achados


def auditar_repositorio(
    raiz: str | Path,
    shadow_dir: str | Path | None = None,
    allowlist_testes: tuple[str, ...] = ALLOWLIST_TESTES_PADRAO,
) -> RelatorioAuditoria:
    raiz = Path(raiz).resolve()
    achados_ordem, n_python = auditar_ausencia_ordens(raiz, allowlist_testes)
    achados_shadow: list[Achado] = []
    n_particoes = 0
    if shadow_dir is not None:
        caminho_shadow = Path(shadow_dir)
        if not caminho_shadow.is_absolute():
            caminho_shadow = raiz / caminho_shadow
        achados_shadow, n_particoes = auditar_particoes_shadow(caminho_shadow)
    return RelatorioAuditoria(
        tuple(achados_ordem + achados_shadow), n_python, n_particoes
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
            achados.append(Achado("PY_INVALIDO", relativo, str(erro)))
            continue
        achados.extend(_achados_execucao(arvore, relativo))
    return achados, inspecionados


def auditar_particoes_shadow(shadow_dir: Path) -> tuple[list[Achado], int]:
    achados: list[Achado] = []
    if not shadow_dir.exists():
        return [Achado("SHADOW_AUSENTE", str(shadow_dir), "diretorio nao existe")], 0

    particoes = sorted(
        dia
        for symbol in shadow_dir.iterdir()
        if symbol.is_dir()
        for dia in symbol.iterdir()
        if dia.is_dir()
    )
    if not particoes:
        return [
            Achado(
                "PARTICAO_AUSENTE",
                str(shadow_dir),
                "nenhuma particao symbol/data com manifesto foi encontrada",
            )
        ], 0

    for particao in particoes:
        manifesto_path = particao / ARQUIVO_MANIFESTO
        relativo = manifesto_path.relative_to(shadow_dir).as_posix()
        if not manifesto_path.is_file():
            achados.append(
                Achado(
                    "MANIFESTO_AUSENTE",
                    relativo,
                    "particao sem shadow_manifest.json",
                )
            )
            continue
        try:
            manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as erro:
            achados.append(Achado("MANIFESTO_INVALIDO", relativo, str(erro)))
            continue
        _validar_manifesto(manifesto_path, relativo, manifesto, achados)
        _validar_colecoes(manifesto_path.parent, manifesto, achados, shadow_dir)
    return achados, len(particoes)


def _arquivos_python(raiz: Path):
    ignorados = {".git", ".claude", ".venv", "venv", "build", "dist", "__pycache__"}
    for caminho in sorted(raiz.rglob("*.py")):
        try:
            partes = caminho.relative_to(raiz).parts
        except ValueError:
            continue
        if any(parte in ignorados or parte.startswith(".") for parte in partes):
            continue
        yield caminho


def _nome_chamada(no: ast.expr) -> str | None:
    if isinstance(no, ast.Name):
        return no.id
    if isinstance(no, ast.Attribute):
        return no.attr
    return None


def _achados_execucao(arvore: ast.AST, caminho: str) -> list[Achado]:
    achados: list[Achado] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            nome = _nome_chamada(no.func)
            if (
                isinstance(no.func, ast.Name)
                and nome is not None
                and nome.lower() in _NOMES_EXECUCAO
            ):
                achados.append(
                    Achado("API_ORDEM", caminho, f"chamada de {nome}", no.lineno)
                )
            if (
                isinstance(no.func, ast.Name)
                and no.func.id == "getattr"
                and len(no.args) >= 2
            ):
                alvo = no.args[1]
                if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
                    if alvo.value.lower() in _NOMES_EXECUCAO:
                        achados.append(
                            Achado(
                                "API_ORDEM_DINAMICA",
                                caminho,
                                f"getattr para {alvo.value}",
                                no.lineno,
                            )
                        )
                elif _base_parece_corretora(no.args[0]):
                    achados.append(
                        Achado(
                            "API_CORRETORA_DINAMICA",
                            caminho,
                            "getattr dinamico sobre cliente de mercado/corretora",
                            no.lineno,
                        )
                    )
        elif isinstance(no, ast.Attribute):
            if no.attr.lower() in _NOMES_EXECUCAO or (
                no.attr.lower() in {"buy", "sell", "market_order"}
                and _base_parece_corretora(no.value)
            ):
                achados.append(
                    Achado("API_ORDEM", caminho, f"referencia a {no.attr}", no.lineno)
                )
            elif _CONSTANTE_EXECUCAO.match(no.attr):
                achados.append(
                    Achado(
                        "CONSTANTE_ORDEM", caminho, f"uso de {no.attr}", no.lineno
                    )
                )
        elif isinstance(no, ast.Name) and _CONSTANTE_EXECUCAO.match(no.id):
            achados.append(
                Achado("CONSTANTE_ORDEM", caminho, f"uso de {no.id}", no.lineno)
            )
        elif isinstance(no, ast.ImportFrom):
            for alias in no.names:
                if alias.name.lower() in _NOMES_EXECUCAO:
                    achados.append(
                        Achado(
                            "API_ORDEM",
                            caminho,
                            f"import direto de {alias.name}",
                            no.lineno,
                        )
                    )
    # Evita duplicatas quando uma constante aparece dentro de outro no AST.
    return list(dict.fromkeys(achados))


def _base_parece_corretora(no: ast.expr) -> bool:
    nomes: list[str] = []
    while isinstance(no, ast.Attribute):
        nomes.append(no.attr)
        no = no.value
    if isinstance(no, ast.Name):
        nomes.append(no.id)
    return bool(_RADICAL_DINAMICO.search("_".join(nomes))) or any(
        nome.lower() in {"mt5", "broker", "brokerage", "client", "exchange"}
        for nome in nomes
    )


def _validar_manifesto(
    caminho: Path, relativo: str, manifesto: object, achados: list[Achado]
) -> None:
    if not isinstance(manifesto, dict):
        achados.append(Achado("MANIFESTO_INVALIDO", relativo, "raiz nao e objeto"))
        return
    if manifesto.get("modo") != "shadow":
        achados.append(Achado("MODO_INVALIDO", relativo, "modo deve ser shadow"))
    if manifesto.get("promocao_automatica") is not False:
        achados.append(
            Achado(
                "PROMOCAO_AUTOMATICA",
                relativo,
                "promocao_automatica deve ser false",
            )
        )
    colecoes = manifesto.get("colecoes")
    if not isinstance(colecoes, dict) or set(colecoes) != COLECOES_ESPERADAS:
        achados.append(
            Achado(
                "COLECOES_INVALIDAS",
                relativo,
                f"esperado exatamente {sorted(COLECOES_ESPERADAS)}",
            )
        )
    partes = caminho.parts
    if len(partes) >= 3:
        symbol, data = partes[-3], partes[-2]
        if manifesto.get("symbol") != symbol or manifesto.get("data") != data:
            achados.append(
                Achado(
                    "PARTICAO_DIVERGENTE",
                    relativo,
                    "symbol/data do manifesto divergem do caminho",
                )
            )


def _validar_colecoes(
    diretorio: Path,
    manifesto: object,
    achados: list[Achado],
    shadow_dir: Path,
) -> None:
    if not isinstance(manifesto, dict) or not isinstance(manifesto.get("colecoes"), dict):
        return
    colecoes = manifesto["colecoes"]
    ids_features: set[str] = set()
    ids_labels: set[str] = set()
    for colecao, nome_esperado in ARQUIVOS_ESPERADOS.items():
        nome = colecoes.get(colecao)
        relativo_dir = diretorio.relative_to(shadow_dir).as_posix()
        if nome != nome_esperado:
            achados.append(
                Achado(
                    "ARQUIVO_DIVERGENTE",
                    f"{relativo_dir}/{ARQUIVO_MANIFESTO}",
                    f"{colecao} deve apontar para {nome_esperado}",
                )
            )
            continue
        caminho = diretorio / nome
        if not caminho.is_file():
            achados.append(
                Achado(
                    "ARQUIVO_AUSENTE",
                    caminho.relative_to(shadow_dir).as_posix(),
                    f"colecao {colecao} nao encontrada",
                )
            )
            continue
        registros = _ler_jsonl_gz(caminho, shadow_dir, achados)
        destino = ids_features if colecao == "features" else ids_labels
        for registro in registros:
            id_amostra = registro.get("id_amostra")
            if not isinstance(id_amostra, str):
                achados.append(
                    Achado(
                        "ID_AUSENTE",
                        caminho.relative_to(shadow_dir).as_posix(),
                        "registro sem id_amostra textual",
                    )
                )
            else:
                destino.add(id_amostra)
            if registro.get("promocao_automatica") is True:
                achados.append(
                    Achado(
                        "PROMOCAO_AUTOMATICA",
                        caminho.relative_to(shadow_dir).as_posix(),
                        "registro habilita promocao automatica",
                    )
                )
    orfaos = ids_labels - ids_features
    if orfaos:
        achados.append(
            Achado(
                "LABEL_ORFAO",
                diretorio.relative_to(shadow_dir).as_posix(),
                f"{len(orfaos)} id(s) sem feature na particao",
            )
        )


def _ler_jsonl_gz(
    caminho: Path, shadow_dir: Path, achados: list[Achado]
) -> list[dict]:
    registros: list[dict] = []
    relativo = caminho.relative_to(shadow_dir).as_posix()
    try:
        with gzip.open(caminho, "rt", encoding="utf-8") as arquivo:
            for n, linha in enumerate(arquivo, 1):
                if not linha.strip():
                    continue
                valor = json.loads(linha)
                if not isinstance(valor, dict):
                    raise ValueError("linha JSON nao e objeto")
                registros.append(valor)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as erro:
        achados.append(Achado("JSONL_GZ_INVALIDO", relativo, str(erro), locals().get("n")))
    return registros


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=Path.cwd())
    parser.add_argument("--shadow-dir", type=Path)
    parser.add_argument(
        "--permitir-teste",
        action="append",
        default=[],
        help="glob relativo adicional para testes que exercitam a auditoria",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    allowlist = ALLOWLIST_TESTES_PADRAO + tuple(args.permitir_teste)
    relatorio = auditar_repositorio(args.raiz, args.shadow_dir, allowlist)
    if relatorio.achados:
        for achado in relatorio.achados:
            print(achado.texto())
        print(
            f"REPROVADO: {len(relatorio.achados)} achado(s); "
            f"{relatorio.arquivos_python_inspecionados} Python; "
            f"{relatorio.particoes_shadow_inspecionadas} particoes shadow"
        )
        return 1
    print(
        f"APROVADO: {relatorio.arquivos_python_inspecionados} Python; "
        f"{relatorio.particoes_shadow_inspecionadas} particoes shadow"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
