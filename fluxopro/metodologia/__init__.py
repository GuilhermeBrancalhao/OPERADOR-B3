"""As regras de leitura de fluxo, dentro do produto — com a procedência junto.

Este pacote existe para que o método pare de morar num documento ao lado e
passe a ser computado e exposto por API. A fonte é `pesquisa/metodologia_regras.md`
e `pesquisa/ferramenta_componentes.md`, e o mapa de auditoria
(o que virou código, o que virou parâmetro, o que foi recusado e por quê) é
`pesquisa/regras_no_codigo.md`.

## A disciplina, que é o núcleo do pacote

- **CONFIRMADO vira código.**
- **IMPRECISO vira parâmetro configurável, nunca constante cravada.** Quando a
  fonte dá dois números para a mesma coisa (70% e 75% para "direcional"), isso
  significa que o autor não usa número fixo — e o código reflete isso em vez
  de escolher um e fingir certeza.
- **AUSENTE NA FONTE não é implementado como regra do método.** Um conceito
  equivalente pode existir por ser padrão de order flow, mas então ele é
  componente genérico e é rotulado como tal (precedente: `DetectorExaustao`,
  cujo termo não aparece em nenhum vídeo).
- **Cada regra exposta carrega seu rótulo na API.** Todo `Leitura*` daqui tem
  `regras: tuple[RegraDocumentada, ...]`, e cada `RegraDocumentada` tem
  citação, vídeo, seção e `Confianca`. Um painel que admite que a fonte oscila
  entre 70 e 75 vale mais que um que finge precisão.

## Os componentes

| Módulo | O que é | Origem |
|---|---|---|
| `estrutura` | regime só muda ao perder máxima/mínima do dia | `ferramenta_componentes.md` §8, lição do caso WINFUT |
| `velocimetro` | momentum dos contadores, normalizado por magnitude **e** persistência | §3 e §7 |
| `placar` | confluência entre sinais, com estabilidade × oscilação | §2 |
| `linha_azul` | nível do cruzamento de 50% desde a abertura | `metodologia_regras.md` §3 |
| `macro_micro` | dia inteiro × movimento imediato, em escalas que não se comparam | §6 |
| `risco` | 3 stops por região; mão cheia × mão mínima | §§8-9 |

`confianca` e `regras` são a infraestrutura: o tipo do rótulo e o registro de
todas as regras, inclusive as recusadas.

## Divergência declarada: cor

A fonte codifica direção em **verde/vermelho/amarelo** ("tudo que for vermelho
na SG refere-se à leitura vendedora... tudo que é verde, leitura compradora...
amarelo... indecisão", `vs76O7j_inU`). **Este projeto mantém o próprio eixo**:
azul = compra, vermelho = venda, com verde e âmbar reservados ao segundo canal
(estado do sistema, evento detectado). A decisão é de acessibilidade e está em
`design/direcao_visual.md` §3.1 — verde↔vermelho colapsa em deuteranopia e
protanopia (~8% dos homens); azul↔vermelho não.

As faixas, os limiares e os rótulos vêm do método; a codificação de cor, não.
Consequência prática: **nenhum componente deste pacote emite cor.** Eles emitem
`fluxopro.core.eventos.Side`, e quem pinta decide na camada de UI. A divergência
está registrada aqui e no docstring de `regras.py`, não escondida.

## Preços

Sempre `int` em ticks, nunca float — `regiao_de` e `registrar_preco` recusam
float explicitamente, porque um preço float que passa silenciosamente vira
chave de dicionário errada mais adiante.
"""

from __future__ import annotations

from fluxopro.metodologia.confianca import (
    CitacaoInvalidaError,
    Confianca,
    ParametroCalibravel,
    RegraDocumentada,
)
from fluxopro.metodologia.estrutura import (
    ConfigEstrutura,
    GatilhoEstrutural,
    LeituraEstrutural,
    RegimeDoDia,
    RegimeEstrutural,
)
from fluxopro.metodologia.janela import JanelaMovel
from fluxopro.metodologia.linha_azul import (
    ConfigLinhaAzul,
    ConvencaoLinhaAzul,
    LadoDaLinha,
    LeituraLinhaAzul,
    LinhaAzul,
)
from fluxopro.metodologia.macro_micro import (
    ConfigMacroMicro,
    Escala,
    EscalasIncomparaveisError,
    LeituraMacroMicro,
    MacroMicro,
    MedidaContexto,
    comparar_magnitudes,
)
from fluxopro.metodologia.placar import (
    ConfigPlacar,
    LeituraPlacar,
    Placar,
    VotoPlacar,
)
from fluxopro.metodologia.regras import (
    PARAMETROS,
    REGRAS,
    nao_implementadas,
    parametros_de,
    regra,
    regras_de,
)
from fluxopro.metodologia.risco import (
    ConfigRisco,
    Decisao,
    EstadoRegiao,
    GestorRisco,
    ModoTamanho,
    QualidadeRegiao,
    ResultadoOperacao,
    TamanhoNaoConfiguradoError,
)
from fluxopro.metodologia.velocimetro import (
    ConfigVelocimetro,
    EstadoVelocimetro,
    LeituraVelocimetro,
    Velocimetro,
)

__all__ = [
    "PARAMETROS",
    "REGRAS",
    "CitacaoInvalidaError",
    "ConfigEstrutura",
    "ConfigLinhaAzul",
    "ConfigMacroMicro",
    "ConfigPlacar",
    "ConfigRisco",
    "ConfigVelocimetro",
    "Confianca",
    "ConvencaoLinhaAzul",
    "Decisao",
    "Escala",
    "EscalasIncomparaveisError",
    "EstadoRegiao",
    "EstadoVelocimetro",
    "GatilhoEstrutural",
    "GestorRisco",
    "JanelaMovel",
    "LadoDaLinha",
    "LeituraEstrutural",
    "LeituraLinhaAzul",
    "LeituraMacroMicro",
    "LeituraPlacar",
    "LeituraVelocimetro",
    "LinhaAzul",
    "MacroMicro",
    "MedidaContexto",
    "ModoTamanho",
    "ParametroCalibravel",
    "Placar",
    "QualidadeRegiao",
    "RegimeDoDia",
    "RegimeEstrutural",
    "RegraDocumentada",
    "ResultadoOperacao",
    "TamanhoNaoConfiguradoError",
    "Velocimetro",
    "VotoPlacar",
    "comparar_magnitudes",
    "nao_implementadas",
    "parametros_de",
    "regra",
    "regras_de",
]
