"""`LeitorMetodo` — os componentes do método ligados ao tape, e o retrato que
a interface lê.

Até aqui `fluxopro/metodologia/` era um pacote **isolado**: 33 regras
implementadas, nove componentes testados, e nenhum deles alimentado por evento
nenhum em produção. A consequência foi medida: a interface dava a maior parte
da sua superfície ao único caminho que o registro **não** avaliza (detectores
genéricos) e nada às regras que ele avaliza, porque não havia leitura viva
para mostrar. O placar de fidelidade lia `0 MÉTODO` e não podia ler outra
coisa. Este módulo é o elo que faltava.

## O que ele liga, e em que ordem

Um único assinante de `Trade` (`SessaoFluxo._ao_trade_metodo`, prioridade
`PRIORIDADE_METODO`) alimenta os cinco componentes **nesta ordem, que é
interna e determinística**:

1. `MacroMicro.ao_trade` — acumula o delta de agressão da sessão e a janela
   curta. É o primeiro porque é ele que produz o contador que o velocímetro
   consome.
2. `Velocimetro.registrar(ts, macro_micro.delta_macro)` — o velocímetro mede
   *momentum de um contador acumulado*, e o contador do método é o delta de
   agressão desde a abertura. Ler `delta_macro` em vez de instanciar um
   terceiro acumulador é o que garante que macro, micro e velocímetro estejam
   falando **do mesmo número** — invariante conferido em
   `tests/test_app_metodologia.py` contra `CumulativeDelta.delta_sessao`, que
   é o mesmo delta calculado por outro caminho, na camada de analytics.
3. `RegimeDoDia.registrar_preco(trade.price, ts)` — preço puro, em ticks.
4. `LinhaAzul.ao_trade` — acumula volume por agressor e detecta o cruzamento
   de 50%.
5. `Placar.registrar(ts, votos)` — **por último**, porque os votos são as
   leituras dos quatro acima. É o que `placar.meta_leitura` (CONFIRMADO)
   exige: *"ele lê os sinais que a SG já lê do mercado"*.

## `Placar` continua não assinando o barramento

A regra `placar.meta_leitura` diz que o placar é meta-leitura e a
consequência declarada em `placar.py` é literal: *"`Placar.registrar` recebe
os votos de fora e não assina o `Barramento`"*. Isso continua verdadeiro — é
o `LeitorMetodo` que assina (por meio da `SessaoFluxo`), monta os votos e os
entrega. Quem vota é **escolha declarada de quem monta**
(`ConfigMetodologia.fontes_placar`), não fatalidade embutida no produto, e
`tests/test_app_metodologia.py` prende que nenhuma instância de `Placar`
aparece na lista de assinantes do barramento.

## O retrato, e por que ele é um objeto só

`fluxopro/ui/ponte.py::Instantaneo` fixou o padrão da casa: a interface roda
noutra thread e **não pode tocar em objeto vivo da thread da fonte**. Ler
campo a campo daria uma tela costurada de dois instantes.

Aqui o problema é pior do que na ponte, porque as cinco leituras não são
escalares independentes — elas **se explicam umas às outras**. Um placar 4×0
comprador ao lado de um velocímetro que já virou não é uma tela imprecisa: é
uma tela que mente sobre a confluência, porque o placar mostrado foi apurado
com o voto do velocímetro de antes. Então:

* as cinco leituras viajam num `LeituraMetodo` **imutável**, montado de uma
  vez sob o lock;
* e o construtor **recusa** um retrato cujas leituras não tenham o mesmo
  `timestamp_ns` (`LeiturasInconsistentesError`). O invariante não é uma
  promessa de docstring que uma refatoração distraída revoga em silêncio; é
  uma exceção em runtime, no molde de `EscalasIncomparaveisError`.

`sessao.agressao` — três escalares soltos lidos direto do objeto vivo, sem
ninguém jamais ter afirmado invariante entre eles — é o precedente que este
módulo existe para não repetir.

`ler()` **não drena** (ao contrário de `PonteFluxo.ler`, que esvazia um
buffer e por isso tem dono único): o que está aqui é estado de NÍVEL, não
fila. Qualquer painel pode chamar, quantas vezes quiser, e todos veem o mesmo
retrato.

## `GestorRisco` fica de fora do caminho automático — de propósito

`risco.gatilho_de_tamanho` é **AUSENTE NA FONTE**: não há volatilidade,
spread nem percentual que separe "região boa" de "região turbulenta", e por
isso `GestorRisco.avaliar` **exige** a `QualidadeRegiao` de quem chama.

Consequência aqui, verificável por ausência: o gestor é instanciado e
exposto (`LeitorMetodo.risco`), mas **não é alimentado por evento nenhum** e
`LeituraMetodo` **não tem campo de risco**. Não existe caminho pelo qual uma
decisão de risco saia deste módulo sem que uma pessoa tenha informado a
qualidade da região e o resultado de uma operação. Inventar um classificador
para preencher aquele argumento seria colocar na boca da fonte uma regra que
ela não tem.

## Estado, e o critério do gravador

*"Qual grandeza limita o `len` disto, e ela para de crescer enquanto o pregão
continua?"* (`fluxopro/gravacao/gravador.py`):

* `_votos` — dicionário **reusado**, `len` fixo em `len(fontes_placar)`,
  montado uma vez no construtor e sobrescrito por trade (nunca recriado, e
  nunca acrescido de chave nova);
* `_ultima` — **um** `LeituraMetodo`, substituído a cada trade, nunca
  enfileirado;
* os cinco componentes respondem a mesma pergunta com constantes de
  configuração (`n_baldes`, `tamanho_topo_magnitude`, `n_baldes_oscilacao`),
  e o `GestorRisco` com o número de operações perdedoras do operador.

Nenhuma coleção deste módulo é indexada por evento. `tests/test_metodologia.py`
mede isso com 1.000 e 20.000 eventos.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, unique

from fluxopro.core.eventos import Side, Trade
from fluxopro.metodologia.confianca import RegraDocumentada
from fluxopro.metodologia.estrutura import _REGRAS as _REGRAS_ESTRUTURA
from fluxopro.metodologia.estrutura import (
    ConfigEstrutura,
    LeituraEstrutural,
    RegimeDoDia,
)
from fluxopro.metodologia.linha_azul import _REGRAS as _REGRAS_LINHA_AZUL
from fluxopro.metodologia.linha_azul import (
    ConfigLinhaAzul,
    LeituraLinhaAzul,
    LinhaAzul,
)
from fluxopro.metodologia.macro_micro import _REGRAS as _REGRAS_MACRO_MICRO
from fluxopro.metodologia.macro_micro import (
    ConfigMacroMicro,
    LeituraMacroMicro,
    MacroMicro,
)
from fluxopro.metodologia.placar import _REGRAS as _REGRAS_PLACAR
from fluxopro.metodologia.placar import (
    ConfigPlacar,
    LeituraPlacar,
    Placar,
    VotoPlacar,
)
from fluxopro.metodologia.risco import ConfigRisco, GestorRisco
from fluxopro.metodologia.velocimetro import _REGRAS as _REGRAS_VELOCIMETRO
from fluxopro.metodologia.velocimetro import (
    ConfigVelocimetro,
    EstadoVelocimetro,
    LeituraVelocimetro,
    Velocimetro,
)


class LeiturasInconsistentesError(ValueError):
    """Um retrato foi montado com leituras de instantes diferentes.

    Mesma família de `EscalasIncomparaveisError`: a restrição que a
    documentação descreveria vira exceção em runtime, para que a violação
    apareça como erro e não como tela plausível.
    """


@unique
class FontePlacar(Enum):
    """Quem pode votar no placar. A escolha de QUAIS votam é de quem monta.

    A ferramenta original soma até cinco fontes; duas delas o produto recusa
    (`sinal_ultra.gatilho` e `placar.fonte_llm`, ver `regras.py`). Estas
    quatro são as que este pacote sustenta com regra registrada.
    """

    ESTRUTURA = "estrutura"
    """Regime do dia (`estrutura.regime`, CONFIRMADO)."""

    VELOCIMETRO = "velocimetro"
    """Sentido do momentum, já filtrado pelo gate do caso WINFUT."""

    LINHA_AZUL = "linha_azul"
    """Lado do preço em relação à linha. **INFERIDO** — ver a nota abaixo."""

    MACRO_MICRO = "macro_micro"
    """Sentido da micro: *"a micro é quem manda no agora"* (CONFIRMADO)."""


FONTES_PADRAO: tuple[FontePlacar, ...] = (
    FontePlacar.ESTRUTURA,
    FontePlacar.VELOCIMETRO,
    FontePlacar.LINHA_AZUL,
    FontePlacar.MACRO_MICRO,
)
"""Os quatro votantes default.

`LINHA_AZUL` entra apesar de `linha_azul.lado` ser **INFERIDO**, e isso é
escolha declarada, não descuido: o rótulo viaja na leitura
(`LeituraLinhaAzul.confianca_lado`) e a fonte do voto viaja no placar
(`LeituraPlacar.fontes`), então um painel pode mostrar o 4×0 **e** dizer que
um dos quatro votos é inferência. Quem discordar tira a fonte da configuração
— é uma linha, e o placar continua coerente com três votantes (a `goleada`
passa a exigir 4 de 3, ou seja, deixa de ocorrer; ver `diferenca_goleada`).
"""


@dataclass(frozen=True, slots=True)
class ConfigMetodologia:
    """Config das seis peças do método, por composição.

    Mesma disciplina de `app/config.py`: **nenhum limiar é redigitado aqui**.
    Cada campo guarda a dataclass original do módulo dono, de modo que um
    default novo lá aparece aqui sem edição.
    """

    estrutura: ConfigEstrutura = field(default_factory=ConfigEstrutura)
    velocimetro: ConfigVelocimetro = field(default_factory=ConfigVelocimetro)
    linha_azul: ConfigLinhaAzul = field(default_factory=ConfigLinhaAzul)
    macro_micro: ConfigMacroMicro = field(default_factory=ConfigMacroMicro)
    placar: ConfigPlacar = field(default_factory=ConfigPlacar)
    risco: ConfigRisco = field(default_factory=ConfigRisco)

    fontes_placar: tuple[FontePlacar, ...] = FONTES_PADRAO
    """Quem vota. Tupla vazia é recusada: um placar sem votante nenhum
    publicaria "0 a 0" para sempre, que é pior que não publicar nada."""

    def __post_init__(self) -> None:
        if not self.fontes_placar:
            raise ValueError(
                "fontes_placar vazia: o Placar e meta-leitura e precisa de "
                "pelo menos uma fonte para somar"
            )
        if len(set(self.fontes_placar)) != len(self.fontes_placar):
            raise ValueError("fontes_placar com fonte repetida (voto em dobro)")


@dataclass(frozen=True, slots=True)
class LeituraMetodo:
    """As cinco leituras do método **do mesmo instante**, num objeto só.

    O construtor recusa leituras de instantes diferentes — ver
    `LeiturasInconsistentesError` e a docstring do módulo.
    """

    timestamp_ns: int
    preco: int
    sequencia: int
    """Quantos retratos já foram publicados nesta sessão. Serve para a UI
    saber se o que ela está vendo mudou desde o último quadro sem comparar
    campo a campo."""

    estrutura: LeituraEstrutural
    velocimetro: LeituraVelocimetro
    linha_azul: LeituraLinhaAzul
    macro_micro: LeituraMacroMicro
    placar: LeituraPlacar
    votos: tuple[tuple[str, VotoPlacar], ...]
    """Os votos que produziram ESTE placar, com o nome da fonte. É o que
    permite a um painel explicar um 3×1 em vez de só exibi-lo."""

    def __post_init__(self) -> None:
        for nome in ("estrutura", "velocimetro", "linha_azul", "macro_micro", "placar"):
            leitura = getattr(self, nome)
            if leitura.timestamp_ns != self.timestamp_ns:
                raise LeiturasInconsistentesError(
                    f"{nome} carimbada em {leitura.timestamp_ns}, retrato em "
                    f"{self.timestamp_ns}: um retrato costurado de dois "
                    "instantes explicaria o placar com o voto errado"
                )

    @property
    def regras(self) -> tuple[RegraDocumentada, ...]:
        """União das regras das cinco leituras, sem repetição.

        Constante do módulo (cada componente pendura uma tupla fixa), então
        isto não custa nada por quadro."""
        return REGRAS_DO_METODO_VIVO

    @property
    def lado_placar(self) -> Side | None:
        """Atalho para o que a tela mostra maior. Continua sendo `Side`, nunca
        cor — ver a divergência declarada em `regras.py`."""
        return self.placar.lado


def _votar_estrutura(leitura: LeituraEstrutural) -> VotoPlacar:
    return _voto_de(leitura.lado)


def _votar_velocimetro(leitura: LeituraVelocimetro) -> VotoPlacar:
    """`PARADO`/`SEM_DADOS` votam NEUTRO — é o gate do caso WINFUT votando.

    Nenhum limiar novo é introduzido aqui: quem decidiu que aquele repique não
    era força foi o próprio velocímetro, com a magnitude relativa dele. Este
    voto só não desfaz a decisão.
    """
    if leitura.estado in (EstadoVelocimetro.SEM_DADOS, EstadoVelocimetro.PARADO):
        return VotoPlacar.NEUTRO
    return _voto_de(leitura.sentido)


def _votar_linha_azul(leitura: LeituraLinhaAzul) -> VotoPlacar:
    """A leitura é INFERIDA e o rótulo viaja em `LeituraLinhaAzul`."""
    return _voto_de(leitura.lado.leitura_inferida)


def _votar_macro_micro(leitura: LeituraMacroMicro) -> VotoPlacar:
    """`comanda` é a micro — CONFIRMADO, e é comparação de SENTIDO.

    Nada aqui compara magnitude de macro com magnitude de micro; fazer isso
    levantaria `EscalasIncomparaveisError`, que é o ponto do módulo.
    """
    return _voto_de(leitura.comanda)


def _voto_de(lado: Side | None) -> VotoPlacar:
    if lado is Side.BUY:
        return VotoPlacar.COMPRA
    if lado is Side.SELL:
        return VotoPlacar.VENDA
    return VotoPlacar.NEUTRO


class LeitorMetodo:
    """Os cinco componentes do método alimentados pelo mesmo trade.

    Não assina o `Barramento` por conta própria: quem assina é
    `SessaoFluxo`, com prioridade explícita
    (`app/config.py::PRIORIDADE_METODO`). É a mesma política de
    `MotorSinais` e do perfil de sessão, e é o que permite à virada de
    sessão zerar este objeto **sem** desassinar e reassinar nada.

    ## O que a interface pode tocar, e o que não pode

    * `ler()` — **sim.** Devolve um retrato imutável. É a única leitura que
      atravessa a fronteira de thread com segurança.
    * `risco` — **sim.** O `GestorRisco` não é tocado por evento nenhum; ele
      só responde a `avaliar` / `registrar_resultado`, que vêm do operador.
      Na prática é objeto exclusivo da thread de quem opera.
    * `estrutura`, `velocimetro`, `linha_azul`, `macro_micro`, `placar` —
      **não.** São os acumuladores vivos, escritos pela thread da FONTE a
      cada trade. Ler `linha_azul.nivel` direto daqui é o defeito que
      `LeituraMetodo` existe para tornar desnecessário: o retrato traz o
      mesmo número, carimbado com o instante em que ele valia. Ficam
      públicos para teste e para diagnóstico, não para desenho.
    """

    __slots__ = (
        "config",
        "estrutura",
        "velocimetro",
        "linha_azul",
        "macro_micro",
        "placar",
        "risco",
        "_symbol",
        "_fontes",
        "_votos",
        "_lock",
        "_ultima",
        "_sequencia",
    )

    def __init__(self, symbol: str, config: ConfigMetodologia | None = None) -> None:
        self.config = config if config is not None else ConfigMetodologia()
        cfg = self.config
        self._symbol = symbol

        self.estrutura = RegimeDoDia(cfg.estrutura)
        self.velocimetro = Velocimetro(cfg.velocimetro)
        self.linha_azul = LinhaAzul(symbol, cfg.linha_azul)
        self.macro_micro = MacroMicro(symbol, cfg.macro_micro)
        self.placar = Placar(cfg.placar)
        self.risco = GestorRisco(cfg.risco)
        """**Não é alimentado por evento.** Ver a docstring do módulo."""

        self._fontes = cfg.fontes_placar
        # Dicionario REUSADO: as chaves sao criadas uma vez e so os valores
        # mudam. `len` fixo em `len(fontes_placar)` por construcao — nenhuma
        # chave nova entra depois daqui.
        self._votos: dict[str, VotoPlacar] = {
            f.value: VotoPlacar.NEUTRO for f in self._fontes
        }

        self._lock = threading.Lock()
        self._ultima: LeituraMetodo | None = None
        self._sequencia = 0

    # ------------------------------------------------------------------
    # entrada — roda na thread da FONTE
    # ------------------------------------------------------------------
    def ao_trade(self, trade: Trade) -> LeituraMetodo | None:
        """Alimenta os cinco componentes e publica o retrato do instante.

        Devolve o retrato publicado (ou `None` para trade de outro símbolo),
        para quem alimenta em teste não precisar chamar `ler()` em seguida.
        """
        if trade.symbol != self._symbol:
            return None

        ts = trade.timestamp_ns

        # A ordem abaixo e interna e importa: o velocimetro consome o contador
        # que o macro_micro acabou de atualizar, e o placar consome as quatro
        # leituras. Ver a docstring do modulo.
        macro_micro = self.macro_micro.ao_trade(trade)
        velocimetro = self.velocimetro.registrar(ts, self.macro_micro.delta_macro)
        estrutura = self.estrutura.registrar_preco(trade.price, ts)
        linha_azul = self.linha_azul.ao_trade(trade)

        votos = self._votos
        for fonte in self._fontes:
            if fonte is FontePlacar.ESTRUTURA:
                votos[fonte.value] = _votar_estrutura(estrutura)
            elif fonte is FontePlacar.VELOCIMETRO:
                votos[fonte.value] = _votar_velocimetro(velocimetro)
            elif fonte is FontePlacar.LINHA_AZUL:
                votos[fonte.value] = _votar_linha_azul(linha_azul)
            else:
                votos[fonte.value] = _votar_macro_micro(macro_micro)

        placar = self.placar.registrar(ts, votos)

        with self._lock:
            self._sequencia += 1
            retrato = LeituraMetodo(
                timestamp_ns=ts,
                preco=trade.price,
                sequencia=self._sequencia,
                estrutura=estrutura,
                velocimetro=velocimetro,
                linha_azul=linha_azul,
                macro_micro=macro_micro,
                placar=placar,
                votos=tuple(votos.items()),
            )
            self._ultima = retrato
        return retrato

    # ------------------------------------------------------------------
    # saída — roda na thread de quem desenha
    # ------------------------------------------------------------------
    def ler(self) -> LeituraMetodo | None:
        """O último retrato consistente. `None` antes do primeiro trade.

        **Não drena.** Ao contrário de `PonteFluxo.ler`, que esvazia um buffer
        e por isso tem dono único, aqui o que existe é estado de nível:
        qualquer painel pode chamar, quantas vezes quiser, e todos veem o
        mesmo objeto.
        """
        with self._lock:
            return self._ultima

    @property
    def leituras_publicadas(self) -> int:
        with self._lock:
            return self._sequencia

    # ------------------------------------------------------------------
    def iniciar_nova_sessao(self, timestamp_ns: int | None = None) -> None:
        """Virada de pregão — política explícita de `core/estado_mercado.py`.

        Zera os seis componentes (cada um sabe o que "do dia" significa para
        si) **e o retrato publicado**: um painel que continuasse mostrando o
        placar de ontem enquanto o pregão de hoje não teve trade nenhum seria
        exatamente o defeito que a virada existe para fechar.

        `sequencia` também volta a zero — ela conta retratos DA SESSÃO, ao
        contrário de `SessaoFluxo.Contadores`, que conta da execução. As duas
        escolhas são deliberadas e opostas: os contadores da sessão de fluxo
        medem quanto o processo trabalhou; esta sequência responde "o que
        estou vendo é do pregão de hoje?".
        """
        self.estrutura.iniciar_nova_sessao(timestamp_ns)
        self.velocimetro.iniciar_nova_sessao()
        self.linha_azul.iniciar_nova_sessao()
        self.macro_micro.iniciar_nova_sessao()
        self.placar.iniciar_nova_sessao()
        self.risco.iniciar_nova_sessao()
        for chave in self._votos:
            self._votos[chave] = VotoPlacar.NEUTRO
        with self._lock:
            self._ultima = None
            self._sequencia = 0


def _uniao_das_regras() -> tuple[RegraDocumentada, ...]:
    """Montada uma vez, no import: cada componente pendura uma tupla FIXA.

    Deriva das tuplas dos próprios componentes em vez de repetir a lista de
    ids aqui — uma segunda lista escrita à mão seria uma segunda fonte de
    procedência, que envelhece em silêncio quando um componente ganha regra
    nova. É o mesmo argumento que fez `regras_do_campo` ler o registro em vez
    de um `dict` digitado.
    """
    vistas: dict[str, RegraDocumentada] = {}
    for tupla in (
        _REGRAS_ESTRUTURA,
        _REGRAS_VELOCIMETRO,
        _REGRAS_LINHA_AZUL,
        _REGRAS_MACRO_MICRO,
        _REGRAS_PLACAR,
    ):
        for r in tupla:
            vistas[r.id] = r
    return tuple(vistas[i] for i in sorted(vistas))


REGRAS_DO_METODO_VIVO: tuple[RegraDocumentada, ...] = _uniao_das_regras()
"""As regras que respondem por um `LeituraMetodo`, sem repetição.

É o conjunto que um painel pode listar ao lado do retrato para dizer, com
citação e rótulo, de onde vem cada coisa que está na tela. Note que ele NÃO
inclui as regras de `risco` — o gestor não entra no retrato, porque não é
alimentado automaticamente.
"""
