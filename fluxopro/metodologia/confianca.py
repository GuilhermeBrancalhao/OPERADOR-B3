"""Rótulo de confiança: a peça que impede este pacote de fingir precisão.

`pesquisa/metodologia_regras.md` e `pesquisa/ferramenta_componentes.md` não
entregam "as regras" — entregam regras **com procedência**: cada uma vem com
citação literal curta e um rótulo (`CONFIRMADO`, `IMPRECISO`, `INFERIDO`,
`AUSENTE NA FONTE`). Perder o rótulo no caminho para o código é o modo de
falha específico desta peça: um painel que mostra "direcional ≥70%" sem dizer
que a fonte oscila entre 70 e 75 afirma mais do que a fonte sustenta.

Por isso o rótulo não é comentário nem documentação ao lado — é **dado**, e
viaja junto com toda leitura publicada por este pacote (todo `Leitura*` daqui
carrega `regras: tuple[RegraDocumentada, ...]`).

## As invariantes que este módulo torna impossíveis de violar

1. **Citação de no máximo `LIMITE_PALAVRAS_CITACAO` palavras.** É a disciplina
   que as próprias pesquisas se impuseram ("Toda citação abaixo tem no máximo
   ~15 palavras e serve só para ancorar a regra").
2. **`AUSENTE_NA_FONTE` não pode ter citação.** É a invariante que dá o nome ao
   rótulo: se há citação, a fonte não está ausente. Ela obriga, em troca, uma
   `nota` — porque uma regra ausente só é auditável se estiver escrito *o que*
   está ausente e *o que* o código fez a respeito.
3. **`CONFIRMADO` e `IMPRECISO` exigem citação e fonte.** Sem elas o rótulo
   seria opinião do implementador com cara de evidência.
4. **`INFERIDO` exige nota.** A dedução tem de estar escrita, senão vira
   indistinguível de `CONFIRMADO`.

`implementada=False` é primeira classe, não ausência de código esquecida: é
como se registra "a fonte descreve isto, e nós recusamos transformar em regra
do método" (ver `regras.py`, blocos `exaustao.*`, `maker.*`, `sinal_ultra.*`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

LIMITE_PALAVRAS_CITACAO = 15
"""Teto de palavras por citação — mesma disciplina das pesquisas de origem."""


@unique
class Confianca(Enum):
    """Rótulo de procedência de uma regra, copiado das pesquisas de origem."""

    CONFIRMADO = "CONFIRMADO"
    """O autor descreve o mecanismo explicitamente."""

    IMPRECISO = "IMPRECISO"
    """Ele fala, mas sem parâmetro — ou dá números diferentes em vídeos
    diferentes. **Vira parâmetro configurável, nunca constante cravada.**"""

    INFERIDO = "INFERIDO"
    """Dedução da pesquisa a partir do comportamento mostrado, não da fala."""

    AUSENTE_NA_FONTE = "AUSENTE_NA_FONTE"
    """Não existe na fonte. **Não vira regra do método.** Se um conceito
    equivalente existir por ser padrão de order flow, ele é componente
    genérico e é rotulado como tal — precedente: `DetectorExaustao`."""


class CitacaoInvalidaError(ValueError):
    """Uma `RegraDocumentada` violou uma das invariantes de procedência."""


@dataclass(frozen=True, slots=True)
class RegraDocumentada:
    """Uma regra de leitura de fluxo com sua procedência anexada.

    `secao` aponta o arquivo e a seção da pesquisa (o endereço auditável);
    `fonte` é o vídeo de onde a citação saiu (id do YouTube, como nas
    pesquisas). `nota` é onde mora toda divergência entre o que a fonte diz e
    o que o código faz — incluindo as escolhas de engenharia declaradas.
    """

    id: str
    titulo: str
    confianca: Confianca
    secao: str
    citacao: str = ""
    fonte: str = ""
    nota: str = ""
    implementada: bool = True

    def __post_init__(self) -> None:
        if not self.id or not self.titulo or not self.secao:
            raise CitacaoInvalidaError(f"regra sem id/titulo/secao: {self.id!r}")

        palavras = len(self.citacao.split())
        if palavras > LIMITE_PALAVRAS_CITACAO:
            raise CitacaoInvalidaError(
                f"{self.id}: citacao com {palavras} palavras, "
                f"teto e {LIMITE_PALAVRAS_CITACAO}"
            )

        if self.confianca is Confianca.AUSENTE_NA_FONTE:
            if self.citacao:
                raise CitacaoInvalidaError(
                    f"{self.id}: AUSENTE_NA_FONTE com citacao — se ha citacao, "
                    "a fonte nao esta ausente"
                )
            if not self.nota:
                raise CitacaoInvalidaError(
                    f"{self.id}: AUSENTE_NA_FONTE sem nota — o que esta ausente "
                    "e o que o codigo fez a respeito precisam estar escritos"
                )
        elif self.confianca is Confianca.INFERIDO:
            if not self.nota:
                raise CitacaoInvalidaError(f"{self.id}: INFERIDO sem nota")
        else:
            if not self.citacao or not self.fonte:
                raise CitacaoInvalidaError(
                    f"{self.id}: {self.confianca.value} exige citacao e fonte"
                )

    @property
    def vira_parametro(self) -> bool:
        """`IMPRECISO` é o rótulo que obriga parâmetro em vez de constante."""
        return self.confianca is Confianca.IMPRECISO

    def __str__(self) -> str:
        return f"[{self.confianca.value}] {self.titulo} ({self.secao})"


@dataclass(frozen=True, slots=True)
class ParametroCalibravel:
    """Um limiar que a fonte NÃO fixa, exposto como configuração.

    `valores_na_fonte` é o registro do desacordo: quando tem dois elementos
    (ex.: `(0.70, 0.75)` para "direcional"), o número que o código usa é uma
    escolha declarada entre eles, não uma leitura unívoca — e a regra ligada
    a ele tem de estar rotulada `IMPRECISO` (validado em `regras.py`).
    Tupla vazia significa "a fonte não dá número nenhum".
    """

    nome: str
    """Endereço no código: `"ConfigVelocimetro.janela_ns"`."""

    padrao: object
    """Valor default. Validado contra o dataclass real em `tests/`."""

    valores_na_fonte: tuple[object, ...]
    motivo: str
    regra_id: str
    unidade: str = ""

    def __post_init__(self) -> None:
        if not self.motivo:
            raise CitacaoInvalidaError(
                f"{self.nome}: parametro sem motivo — por que o valor nao vem "
                "da fonte precisa estar escrito"
            )
        if "." not in self.nome:
            raise CitacaoInvalidaError(
                f"{self.nome}: nome deve ser 'ConfigX.campo'"
            )

    @property
    def fonte_diverge(self) -> bool:
        return len(set(self.valores_na_fonte)) >= 2

    @property
    def alvo(self) -> tuple[str, str]:
        """`("ConfigVelocimetro", "janela_ns")`."""
        classe, _, campo = self.nome.rpartition(".")
        return classe, campo
