"""Analise consultiva de fim de pregao via Claude Code CLI (`claude -p`).

Sem chave de API embutida no codigo: usa o `claude` ja autenticado na
maquina (mesmo caminho de outros projetos do usuario). Se o CLI nao
estiver disponivel ou estourar timeout, devolve None -- o pregao continua
sendo gravado no banco sem a analise, nunca trava o fechamento do dia por
causa disso.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile

from fluxopro.aprendizado.metricas_dia import MetricasDia
from fluxopro.aprendizado.padroes import DesvioMetrica

_TIMEOUT_S = 120

_SYSTEM_PROMPT = (
    "Voce e um analista de fluxo de mercado. Responda apenas com a analise "
    "de texto pedida, direto, sem pedir confirmacao, sem propor executar "
    "comandos e sem se referir a si mesmo como assistente de codigo."
)


def montar_prompt(metricas: MetricasDia, desvios: list[DesvioMetrica]) -> str:
    linhas = [
        f"Pregao {metricas.simbolo} {metricas.data}. "
        f"Abertura {metricas.preco_abertura} fechamento {metricas.preco_fechamento} "
        f"maxima {metricas.preco_maximo} minima {metricas.preco_minimo}.",
        f"Volume total {metricas.volume_total} (compra {metricas.volume_compra}, "
        f"venda {metricas.volume_venda}, delta {metricas.delta_volume}).",
        "Deteccoes do dia: "
        + ", ".join(f"{tipo}={qtd}" for tipo, qtd in sorted(metricas.contagem_deteccoes.items())),
    ]
    anomalos = [d for d in desvios if d.anomalo]
    if anomalos:
        linhas.append("Metricas fora do padrao historico (|z|>=2):")
        for d in anomalos:
            linhas.append(
                f"- {d.nome}: hoje={d.valor_hoje:.1f} media={d.media_historica:.1f} "
                f"desvio={d.desvio_padrao_historico:.1f} z={d.z_score:.2f} (n={d.n_amostras} dias)"
            )
    else:
        linhas.append("Nenhuma metrica fugiu do padrao historico por 2+ desvios.")
    linhas.append(
        "Escreva em portugues, no maximo 5 frases, uma leitura CONSULTIVA (nunca "
        "recomendacao de ordem) do que esse conjunto de numeros sugere sobre o "
        "comportamento do dia, para um operador experiente."
    )
    return "\n".join(linhas)


def gerar_analise_consultiva(
    metricas: MetricasDia, desvios: list[DesvioMetrica], executavel: str | None = None
) -> str | None:
    caminho_cli = executavel or shutil.which("claude")
    if not caminho_cli:
        return None
    prompt = montar_prompt(metricas, desvios)
    try:
        resultado = subprocess.run(
            [caminho_cli, "--system-prompt", _SYSTEM_PROMPT, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
            cwd=tempfile.gettempdir(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if resultado.returncode != 0:
        return None
    texto = resultado.stdout.strip()
    return texto or None
