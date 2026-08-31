"""Analise consultiva do mercado AO VIVO via Claude Code CLI (`claude -p`).

Irma de `fluxopro/aprendizado/consultor_llm.py`, que faz a leitura de FIM
de pregao. Esta aqui roda DURANTE o pregao (e no replay, exigencia do
operador) e alimenta a regiao `nexo/vies.py`.

Tres regras que governam o desenho deste modulo, todas medidas antes de
escritas (31/08/2026, `claude -p` nesta maquina):

1. **Nunca na thread da UI.** A chamada mediu 18 s a 30 s de ponta a ponta.
   O painel redesenha a 60 fps; bloquear um unico quadro nisso congelaria a
   tela por meio minuto. Toda chamada vive numa `Thread` daemon e o
   resultado e publicado num slot protegido por `Lock`.

2. **Intervalo longo e explicito.** Cada chamada custa dinheiro e demora;
   `INTERVALO_MIN_S` e o piso entre duas analises. O painel PEDE a cada
   quadro — quem decide se vale a pena e este modulo, nunca a UI.

3. **Degradar declarando.** Sem o CLI, com timeout, com erro ou com
   resposta fora do formato, `ultima()` devolve o estado
   `AUSENTE`/`ERRO` e a tela escreve isso. Nunca inventa leitura, nunca
   repete a analise velha sem dizer a idade dela.

Consultivo por contrato: o prompt proibe recomendacao de ordem, entrada,
saida ou stop, e o texto renderizado carrega a mesma ressalva do resto do
NEXO. Este modulo nao envia ordem nem le credencial de corretora.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum, unique

__all__ = [
    "INTERVALO_MIN_S",
    "TIMEOUT_S",
    "EstadoAnalise",
    "AnaliseMercado",
    "montar_prompt",
    "parsear_resposta",
    "MotorAnaliseClaude",
    "ligado_por_ambiente",
]

INTERVALO_MIN_S = 90.0
"""Piso entre duas analises, em segundos de RELOGIO DE PAREDE (nunca de
mercado): o custo e a latencia sao reais mesmo quando o replay corre a
400x. Com a chamada medindo 18-30 s, 90 s deixa a analise ociosa a maior
parte do tempo em vez de enfileirar pedidos."""

TIMEOUT_S = 90.0
"""Teto de uma chamada. Acima disso a thread desiste e o estado vira ERRO
— melhor uma leitura declarada como indisponivel do que uma thread presa
segurando o slot para sempre."""

_INSTRUCOES = (
    "Voce e um analista de fluxo de mercado brasileiro (mini-dolar WDO na "
    "B3). Responda SEMPRE em portugues do Brasil, em tom consultivo.\n"
    "NUNCA recomende ordem, entrada, saida, stop, alvo ou tamanho de "
    "posicao — voce descreve o que os dados mostram, nao o que fazer.\n"
    "Nao use markdown, nao escreva introducao nem despedida.\n"
    "Responda EXATAMENTE neste formato, uma linha por campo:\n"
    "CENARIO: <uma palavra: ALTA|BAIXA|LATERAL|INDEFINIDO>\n"
    "TITULO: <ate 40 caracteres>\n"
    "LEITURA: <2 frases curtas sobre o que os dados mostram>\n"
    "ATENCAO: <1 frase sobre o principal risco ou o que observar>\n"
)
"""As instrucoes viajam DENTRO do prompt (stdin), nunca em
`--append-system-prompt`.

Medido em 31/08/2026 nesta maquina (Windows, `claude.CMD`): um texto com
QUEBRA DE LINHA passado como ARGUMENTO e perdido pelo wrapper `.CMD`, e o
CLI responde `Error: Input must be provided either through stdin or as a
prompt argument when using --print` com `returncode 1`. Testadas tres
formas — prompt em argumento (falha), `--system-prompt` + `-p` em
argumento (falha) e prompt por STDIN (funciona) — e so a terceira
sobrevive.

Consequencia que passa deste modulo: `fluxopro/aprendizado/consultor_llm.py`
usa exatamente a forma que falha, entao a analise de fim de pregao devolve
`None` em toda maquina Windows desde que foi escrita. Ela degrada em
silencio por contrato proprio, e por isso ninguem viu."""


@unique
class EstadoAnalise(Enum):
    AUSENTE = "AUSENTE"        # nunca rodou / CLI indisponivel
    ANALISANDO = "ANALISANDO"  # thread em voo
    PRONTA = "PRONTA"
    ERRO = "ERRO"              # timeout, saida vazia ou formato invalido


@dataclass(frozen=True, slots=True)
class AnaliseMercado:
    cenario: str
    titulo: str
    leitura: str
    atencao: str
    momento_s: float
    """`time.monotonic()` de quando a resposta chegou — a tela imprime a
    IDADE a partir disto. Uma leitura de 4 minutos atras nao pode parecer
    de agora."""


def ligado_por_ambiente() -> bool:
    """`FLUXOPRO_ANALISE_IA=0` desliga. Ligado por padrao a pedido do
    operador (31/08/2026), que quer a analise valendo tambem no replay."""

    return os.environ.get("FLUXOPRO_ANALISE_IA", "1").strip().lower() not in {
        "0", "false", "nao", "off",
    }


def _linha(rotulo: str, valor: object) -> str:
    return f"- {rotulo}: {valor}"


def montar_prompt(dados: dict) -> str:
    """Texto enviado ao CLI, a partir de um dicionario JA extraido do
    `EstadoNexo`. Funcao PURA — testavel sem Qt, sem thread e sem rede.

    Chaves ausentes viram "sem leitura" em vez de zero: um zero fabricado
    entraria no raciocinio do modelo como se fosse medicao.
    """

    def leia(chave: str, sufixo: str = "") -> str:
        valor = dados.get(chave)
        if valor is None or valor == "":
            return "sem leitura"
        return f"{valor}{sufixo}"

    partes = [
        _INSTRUCOES,
        f"Dados observados agora no {leia('instrumento')} "
        f"({leia('modo')}, horario de mercado {leia('hora')}):",
        _linha("Preco", leia("preco")),
        _linha("Variacao do dia", leia("variacao_dia")),
        _linha("Volume", leia("volume")),
        _linha("Dominancia do fluxo", leia("dominancia")),
        _linha("Placar compra/venda", leia("placar")),
        _linha("Velocidade micro", leia("micro")),
        _linha("Velocidade macro", leia("macro")),
        _linha("Divergencia micro-macro", leia("divergencia", " graus")),
        _linha("MakerProxy (ranking)", leia("maker")),
        _linha("Renko", leia("renko")),
        _linha("Regime estrutural do dia", leia("regime")),
        _linha("Suporte/Resistencia", leia("suporte_resistencia")),
        _linha("Sinal Ultra", leia("ultra")),
        _linha("Risco de volatilidade (0-1)", leia("risco_volatilidade")),
        "",
        "Descreva o cenario. Se os sinais se contradizem, diga isso "
        "explicitamente em vez de escolher um lado.",
    ]
    return "\n".join(partes)


def parsear_resposta(texto: str) -> AnaliseMercado | None:
    """Le a saida do CLI no formato pedido. `None` quando o formato nao
    veio — nunca devolve uma analise pela metade nem inventa campo.

    Tolerante ao que o modelo costuma fazer de sobra (linha em branco,
    espaco extra, rotulo com acento) e intolerante ao que importa: sem
    LEITURA nao ha analise.
    """

    if not texto:
        return None
    campos: dict[str, str] = {}
    for linha in texto.splitlines():
        limpa = linha.strip().lstrip("#*- ").strip()
        if ":" not in limpa:
            continue
        rotulo, _, valor = limpa.partition(":")
        chave = (rotulo.strip().upper()
                 .replace("Á", "A").replace("Ç", "C").replace("Ã", "A")
                 .replace("Ê", "E").replace("Ú", "U").replace("Í", "I"))
        if chave in {"CENARIO", "TITULO", "LEITURA", "ATENCAO"} and chave not in campos:
            # O `*` tambem sai do VALOR: o modelo as vezes devolve
            # `**CENARIO:** ALTA`, e limpar so o inicio da linha deixava
            # o valor como `** ALTA` — que nao casa com nenhum cenario
            # valido e virava INDEFINIDO silenciosamente.
            campos[chave] = valor.strip().strip("*").strip()
    if not campos.get("LEITURA"):
        return None
    cenario = campos.get("CENARIO", "INDEFINIDO").upper().split()[0]
    if cenario not in {"ALTA", "BAIXA", "LATERAL", "INDEFINIDO"}:
        cenario = "INDEFINIDO"
    return AnaliseMercado(
        cenario=cenario,
        titulo=campos.get("TITULO", "")[:60],
        leitura=campos["LEITURA"],
        atencao=campos.get("ATENCAO", ""),
        momento_s=time.monotonic(),
    )


class MotorAnaliseClaude:
    """Orquestra a chamada ao CLI fora da thread da UI.

    Uso: o painel chama `solicitar(dados)` a cada quadro e `ultima()` para
    desenhar. O motor decide sozinho se dispara — a UI nunca espera.
    """

    def __init__(self, executavel: str | None = None,
                 intervalo_s: float = INTERVALO_MIN_S,
                 timeout_s: float = TIMEOUT_S) -> None:
        self._cli = executavel or shutil.which("claude")
        self._intervalo_s = intervalo_s
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._analise: AnaliseMercado | None = None
        self._estado = EstadoAnalise.AUSENTE
        self._em_voo = False
        self._ultimo_disparo_s = -1e9
        self._motivo: str | None = None if self._cli else "claude nao encontrado no PATH"

    # ------------------------------------------------------------ leitura
    def ultima(self) -> tuple[EstadoAnalise, AnaliseMercado | None, str | None]:
        with self._lock:
            return self._estado, self._analise, self._motivo

    def disponivel(self) -> bool:
        return self._cli is not None

    # ------------------------------------------------------------ escrita
    def solicitar(self, dados: dict, agora_s: float | None = None) -> bool:
        """Dispara uma analise se for a hora. Devolve `True` quando de fato
        disparou. Nunca bloqueia: o trabalho todo vai para uma thread."""

        if self._cli is None:
            return False
        agora = time.monotonic() if agora_s is None else agora_s
        with self._lock:
            if self._em_voo:
                return False
            if agora - self._ultimo_disparo_s < self._intervalo_s:
                return False
            self._em_voo = True
            self._ultimo_disparo_s = agora
            self._estado = EstadoAnalise.ANALISANDO
        prompt = montar_prompt(dados)
        threading.Thread(target=self._rodar, args=(prompt,), daemon=True).start()
        return True

    def _rodar(self, prompt: str) -> None:
        analise: AnaliseMercado | None = None
        motivo: str | None = None
        try:
            resultado = subprocess.run(
                # Prompt INTEIRO por stdin — ver `_INSTRUCOES` para a
                # medicao que descartou as formas com argumento.
                [self._cli, "-p"], input=prompt,
                capture_output=True, text=True, timeout=self._timeout_s,
                encoding="utf-8", errors="replace",
            )
            if resultado.returncode != 0:
                motivo = f"cli saiu {resultado.returncode}"
            else:
                analise = parsear_resposta(resultado.stdout)
                if analise is None:
                    motivo = "resposta fora do formato"
        except subprocess.TimeoutExpired:
            motivo = f"timeout {self._timeout_s:.0f}s"
        except OSError as erro:
            motivo = f"falha ao executar: {erro}"
        with self._lock:
            self._em_voo = False
            if analise is not None:
                self._analise = analise
                self._estado = EstadoAnalise.PRONTA
                self._motivo = None
            else:
                # A analise ANTERIOR e mantida de proposito: e melhor uma
                # leitura velha COM idade impressa do que tela vazia. O
                # estado, porem, vira ERRO — quem olha ve que a ultima
                # tentativa falhou.
                self._estado = EstadoAnalise.ERRO
                self._motivo = motivo

    def idade_s(self, agora_s: float | None = None) -> float | None:
        """Segundos desde que a analise atual chegou. `None` sem analise."""

        with self._lock:
            if self._analise is None:
                return None
            agora = time.monotonic() if agora_s is None else agora_s
            return max(0.0, agora - self._analise.momento_s)
