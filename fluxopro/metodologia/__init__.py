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
| `leitura` | os cinco acima **ligados ao tape**, e o retrato que a UI lê | — |

`confianca` e `regras` são a infraestrutura: o tipo do rótulo, o registro de
todas as regras (inclusive as recusadas) e `FORA_DO_REGISTRO`, a lista dos
limiares vivos que o registro **não** avaliza.

`leitura` é a fiação: `LeitorMetodo` recebe `Trade` (por meio de
`fluxopro/app/sessao_fluxo.py`, com prioridade `PRIORIDADE_METODO`), alimenta
os cinco componentes e publica um `LeituraMetodo` imutável — as cinco leituras
do **mesmo instante**, num objeto só. `GestorRisco` fica fora desse caminho de
propósito: a API dele exige a `QualidadeRegiao` do operador, porque o gatilho
que separa região boa de turbulenta é AUSENTE NA FONTE.

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
    LimiarNaoRegistrado,
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
from fluxopro.metodologia.leitura import (
    FONTES_PADRAO,
    REGRAS_DO_METODO_VIVO,
    ConfigMetodologia,
    FontePlacar,
    LeiturasInconsistentesError,
    LeitorMetodo,
    LeituraMetodo,
)
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
    FORA_DO_REGISTRO,
    PARAMETROS,
    REGRAS,
    limiar_fora_do_registro,
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
    "FONTES_PADRAO",
    "FORA_DO_REGISTRO",
    "PARAMETROS",
    "REGRAS",
    "REGRAS_DO_METODO_VIVO",
    "CitacaoInvalidaError",
    "Confianca",
    "ConfigEstrutura",
    "ConfigLinhaAzul",
    "ConfigMacroMicro",
    "ConfigMetodologia",
    "ConfigPlacar",
    "ConfigRisco",
    "ConfigVelocimetro",
    "ConvencaoLinhaAzul",
    "Decisao",
    "Escala",
    "EscalasIncomparaveisError",
    "EstadoRegiao",
    "EstadoVelocimetro",
    "FontePlacar",
    "GatilhoEstrutural",
    "GestorRisco",
    "JanelaMovel",
    "LadoDaLinha",
    "LeitorMetodo",
    "LeituraEstrutural",
    "LeituraLinhaAzul",
    "LeituraMacroMicro",
    "LeituraMetodo",
    "LeituraPlacar",
    "LeituraVelocimetro",
    "LeiturasInconsistentesError",
    "LimiarNaoRegistrado",
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
    "limiar_fora_do_registro",
    "nao_implementadas",
    "parametros_de",
    "regra",
    "regras_de",
]
