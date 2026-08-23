"""O instrumento dos portões de orçamento de quadro.

Existe porque três portões desta suíte reprovaram, em sessões diferentes, sem
que nada no produto tivesse mudado: `test_quadro_cheio_cabe_no_orcamento_de_60hz`
(DOM e matriz), `test_o_quadro_incremental_do_footprint_cabe_no_orcamento` e
`test_a_incrementalidade_do_delta_existe`. Reproduzido: com quatro processos
queimando CPU ao lado, o conjunto de UI reprova de 3 a 4 portões por rodada; a
mesma árvore, na máquina quieta, passa 6 de 6.

## O defeito, e por que ele não é "teste instável"

`time.perf_counter()` mede **relógio de parede**. Quando o escalonador tira o
processo do ar no meio de um quadro, o tempo do vizinho entra na conta. O p95
é justamente o percentil que colhe essas retiradas: ele foi escolhido para
capturar o pior quadro do DESENHO e acaba capturando o pior momento da
MÁQUINA.

O projeto já pagou por isso uma vez. `bench_ui_carga.py` nasceu de um teste de
contenção de GIL que media, sem dizer, o peso do pipeline — e a conclusão de
lá vale aqui: *medição de tempo de parede sob contenção não é um portão frouxo,
é um portão que mede outra coisa.*

## Por que não `time.process_time()`

Seria a correção óbvia — tempo de CPU não conta o vizinho. Mas no Windows ele
vem de `GetProcessTimes`, com granularidade de ~15,6 ms, e o quadro que estamos
medindo custa 0,33 ms. O instrumento certo para o vizinho é grosso demais para
o objeto. Ele serve para LOTE (dez mil quadros), não para quadro.

## O que este módulo faz em vez disso

Duas afirmações, e elas dizem coisas diferentes:

* `custo_representativo` — percentil 10. Contenção só **soma** tempo, nunca
  subtrai, então a cauda barata é a estimativa menos contaminada do custo real
  do desenho. Este é o portão que vale em qualquer máquina, e é o que reprova
  se o desenho ficar caro de verdade.
* `p95`, sobre as amostras que `Serie.limpas` deixa passar — a afirmação
  FORTE, de que nem o pior quadro estoura o orçamento. Ela continua valendo, e
  continua sendo verificada, só que apenas onde ela é verificável.

E há uma terceira coisa, que veio depois e é o que torna a segunda afirmável:
o `Vigia` julga a JANELA, e a janela é a granularidade errada para uma
afirmação sobre a CAUDA. Dez retiradas do escalonador num laço de meio segundo
escolhem o p95 sem mover a razão parede/CPU do laço — o portão reprovava
dentro de uma janela que o vigia considerava, com razão, quieta. A régua que
faltava é por QUADRO, e ela existe: ver `Serie` e `_relogio_de_cpu` no fim
deste módulo.

E o `Vigia` mede o intervalo EXATO em que as amostras foram colhidas. A versão
anterior perguntava antes e memoizava, e isso reprovou: contenção é estado do
instante, não da rodada — numa bateria de 6, cinco pularam certo e uma reprovou
4 portões porque a sonda caiu num instante bom e os portões rodaram num ruim.

O que não fizemos: afrouxar o limite. Um limite inflado para caber na pior
máquina passa a aprovar desenho caro na máquina boa, que é o defeito de origem
com outra roupa.
"""

from __future__ import annotations

import statistics
import sys
import time

__all__ = [
    "Serie",
    "Vigia",
    "cronometrar",
    "custo_representativo",
    "p95",
]


def cronometrar(painel) -> float:
    """Um quadro, em milissegundos de relógio de parede."""
    inicio = time.perf_counter()
    painel._quadro()
    return (time.perf_counter() - inicio) * 1000.0


def p95(amostras: list[float]) -> float:
    ordenadas = sorted(amostras)
    return ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * 0.95))]


def custo_representativo(amostras: list[float]) -> float:
    """Percentil 10 — a cauda que a contenção não alcança.

    Não é a média nem a mediana: com quatro vizinhos na CPU a mediana já sobe,
    porque mais da metade dos quadros é interrompida. Não é o mínimo absoluto
    tampouco, que é sensível à granularidade do relógio e a um acerto de cache
    isolado.
    """
    if not amostras:
        raise AssertionError("sem amostras: o portão não mediu nada")
    ordenadas = sorted(amostras)
    return ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * 0.10))]


class Vigia:
    """Vigia a contenção **durante** a medição, e não antes dela.

    A primeira versão sondava a máquina uma vez e memoizava. Falhou: numa
    bateria de 6 rodadas do conjunto de UI com quatro processos queimando CPU,
    5 rodadas pularam corretamente e **1 reprovou 4 portões** — a sonda tinha
    caído num instante em que o processo estava recebendo CPU, e os portões
    rodaram noutro em que não estava.

    A contenção não é um estado da rodada, é um estado do instante. Perguntar
    antes responde sobre o instante errado. Este vigia mede o intervalo exato
    em que as amostras foram colhidas: se o relógio de parede do laço andou
    muito mais que o tempo de CPU do processo, o laço mediu o escalonador.

    De brinde, sai de graça — o laço já dura segundos, muito acima da
    granularidade de 15,6 ms de `process_time` no Windows que obrigava a sonda
    avulsa a queimar 350 ms de trabalho só para ter resolução.
    """

    def __init__(self) -> None:
        self._cpu0 = 0.0
        self._parede0 = 0.0
        self.parede = 0.0
        self.cpu = 0.0

    def __enter__(self) -> "Vigia":
        self._cpu0 = time.process_time()
        self._parede0 = time.perf_counter()
        return self

    def __exit__(self, *_exc) -> None:
        self.cpu = time.process_time() - self._cpu0
        self.parede = time.perf_counter() - self._parede0

    CPU_MINIMA_S = 0.30
    """Abaixo disto o vigia NÃO responde — e isso é um erro, não um `skip`.

    `process_time` no Windows anda de 15,6 ms em 15,6 ms. Num laço que gasta
    60 ms de CPU (200 quadros de 0,3 ms, que era o tamanho do laço do DOM),
    são 4 passos de régua: 25% de erro de quantização contra um limiar de 25%.

    Medido numa máquina LIMPA, com o vigia instrumentado: os três portões do
    DOM deram razão 1,294, 1,319 e 1,413 e foram **pulados**. Não havia
    contenção nenhuma — era a régua. Um instrumento que pula teste bom é pior
    que instrumento nenhum, porque o verde continua verde e ninguém procura.

    Por isso a falta de resolução falha em vez de pular: quem escrever um
    portão novo com laço curto demais descobre na hora, com o número na mão,
    em vez de ganhar um `skip` silencioso que ninguém lê.
    """

    LIMITE_PAREDE_SOBRE_CPU = 1.60
    LIMITE_LACO_LIMPO = 1.20
    """DOIS limiares, porque um só não separa — isto foi medido, não escolhido.

    Com resolução suficiente, os doze portões desta suíte deram:

    | máquina | razão parede/CPU |
    |---|---|
    | limpa | 0,975 · 0,999 · 1,013 · 1,029 · 1,062 · 1,063 · 1,073 · 1,103 · 1,205 · 1,254 · **1,506** |
    | com 4 vizinhos na CPU | **1,125** · 1,654 · 1,701 · 1,724 · 1,769 · 1,885 · 1,891 · 2,052 · 2,055 · 2,183 · 2,308 · 2,432 |

    As caudas se cruzam. Não existe corte que aprove todo laço limpo e reprove
    todo laço contendido, e fingir que existe é escolher em qual dos dois erros
    cair sem dizer.

    A saída é graduar a resposta em vez de graduar o limiar:

    * acima de `LIMITE_PAREDE_SOBRE_CPU` (1,60) o intervalo é contenção
      declarada — nada é afirmado, o teste pula com o número no motivo;
    * abaixo de `LIMITE_LACO_LIMPO` (1,20) o laço é limpo — vale a afirmação
      FORTE, de que nem o pior quadro (p95) estoura;
    * na faixa do meio vale só a afirmação robusta (p10), que é a que sobrevive
      a contenção leve. É onde cai o `1,125` contendido da tabela, e é
      exatamente o caso que derrubou este portão antes: contenção fraca demais
      para ser detectada, forte o bastante para inflar UM quadro.
    """

    @property
    def quieta(self) -> bool:
        if self.cpu <= 0.0 or self.parede <= 0.0:
            return False
        return (self.parede / self.cpu) < self.LIMITE_PAREDE_SOBRE_CPU

    @property
    def limpa(self) -> bool:
        """O laço rodou sem disputa nenhuma? Ver `LIMITE_LACO_LIMPO`."""
        if self.cpu <= 0.0 or self.parede <= 0.0:
            return False
        return (self.parede / self.cpu) < self.LIMITE_LACO_LIMPO

    def exigir_quieta(self, o_que: str) -> None:
        """Pula quando o intervalo medido não recebeu a CPU que pediu.

        Antes disso, **falha** se o intervalo foi curto demais para ser
        julgado. Ver `CPU_MINIMA_S`.
        """
        import pytest

        assert self.cpu >= self.CPU_MINIMA_S, (
            f"{o_que}: o laco gastou {self.cpu * 1000:.0f} ms de CPU, abaixo dos "
            f"{self.CPU_MINIMA_S * 1000:.0f} ms que `process_time` precisa para ter "
            "resolucao nesta plataforma. Aumente o numero de amostras — nao "
            "afrouxe o vigia."
        )
        if not self.quieta:
            pytest.skip(
                f"maquina sob contencao durante a medicao "
                f"({self.parede / self.cpu:.2f}x de parede sobre CPU) — "
                f"{o_que} mede o escalonador, nao o desenho"
            )


# --------------------------------------------------------------------------
# A regua por QUADRO — o que faltava para o p95 ser afirmavel
# --------------------------------------------------------------------------
def _relogio_de_cpu():
    """Devolve uma funcao que le a CPU gasta por ESTA thread, com resolucao
    de quadro — ou `None` se a plataforma nao tiver como.

    No Windows e `QueryThreadCycleTime`, que conta CICLOS do processador e nao
    tiques de 15,6 ms: e o mesmo dado que `GetThreadTimes` nao consegue dar, e
    e por causa dessa falta de resolucao que a docstring do modulo descartou o
    tempo de CPU como instrumento de quadro. `process_time` de fato nao serve;
    o contador de ciclos serve.

    Fora do Windows, `time.thread_time_ns` ja tem resolucao de nanossegundo.

    Ciclos nao viram milissegundos aqui, e nao precisam: o uso e uma RAZAO
    contra a mediana da propria serie (ver `Serie.limpas`), entao a frequencia
    do processador se cancela.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            thread = ctypes.c_void_p(kernel32.GetCurrentThread())
            contador = ctypes.c_ulonglong()
            ponteiro = ctypes.byref(contador)
            consultar = kernel32.QueryThreadCycleTime

            def agora() -> int:
                if not consultar(thread, ponteiro):
                    raise OSError("QueryThreadCycleTime falhou")
                return contador.value

            agora()  # falha aqui, na importacao, e nao no meio de um portao
            return agora
        except Exception:
            return None
    return time.thread_time_ns


RELOGIO_DE_CPU = _relogio_de_cpu()

RAZAO_MINIMA_DE_LIMPEZA = 0.75
"""Abaixo disto o quadro foi INTERROMPIDO, e nao medido.

A razao e `(cpu/parede)` do quadro dividida pela mediana da serie: 1,0 e o
quadro que rodou do inicio ao fim sem sair do processador.

Medido nesta maquina com um vizinho queimando CPU, 200 amostras de um laco de
3,5 ms: os quadros limpos ficaram entre 0,44 e 1,09 com mediana 1,00, e os
CINCO mais lentos — 10,9 a 25,2 ms de parede — deram 0,166, 0,199, 0,267,
0,276 e 0,363. Nao ha ambiguidade: sao duas populacoes separadas por uma
ordem de grandeza, e 0,75 cai no vazio entre elas.
"""

FRACAO_MINIMA_LIMPA = 0.95
"""Abaixo disto a serie nao tem o que afirmar sobre a CAUDA, e o portao pula.

Descartar o quadro interrompido conserta o caso que motivou tudo isto — a
maquina quieta com uma ou duas retiradas isoladas no laco —, mas nao conserta
a maquina que esta REALMENTE ocupada: ali o quadro que sobrevive ao filtro
tambem custa mais caro, porque disputa cache e frequencia com o vizinho. Isso
o contador de ciclos nao ve, e nenhum instrumento dentro do processo ve.

A propria fracao limpa e o melhor sinal disponivel de que a maquina estava
entregando a CPU, e ela e MUITO mais fina que a razao parede/CPU da janela.
Medido, quatro corridas do portao do footprint (limite de 4 ms, laco de 800
quadros) nesta maquina com dois trabalhos pesados do usuario ao lado:

    fracao limpa   p95 BRUTO   p95 FILTRADO
        0,647       11,015          —
        0,887        6,688          —
        0,986        3,172        3,172   <- passa ate sem filtro
        0,966 (matriz, limite 16)  12,197 <- passa

O corte em 0,95 cai no vazio entre as duas populacoes: acima dele o laco
mediu o desenho, abaixo dele mediu o escalonador. Numa maquina quieta a
fracao fica em ~1,0 e o portao roda sempre.

E o portao continua reprovando o que ele existe para reprovar: um desenho que
ficou caro QUEIMA CPU enquanto e caro, entao a fracao limpa nao se mexe e o
p95 sobe. So o vermelho que nao era do desenho e que deixou de aparecer.
"""


class Serie:
    """Amostras de quadro com o custo de CPU de CADA quadro ao lado.

    ## O que este objeto conserta

    O `Vigia` julga a JANELA inteira, e a janela e a granularidade errada para
    o p95. O p95 de 200 amostras e o decimo quadro mais caro; dez retiradas do
    escalonador num laco de meio segundo somam ~150 ms, que diluidos na janela
    nao chegam nem perto do 1,10x que o vigia exige. O portao entao reprovava
    dentro de uma janela que o vigia considerava — com razao — quieta. Nenhuma
    verificacao no nivel da janela podia salva-lo: a informacao que falta nao
    esta na janela, esta no quadro.

    ## O que ele NAO faz

    Nao afrouxa o limite, nao troca o percentil e nao repete a medicao ate dar
    verde. Ele descarta as amostras em que o processo NAO ESTAVA RODANDO —
    que nunca foram medicoes do desenho, e sim do escalonador do sistema.

    Um quadro caro de verdade **queima CPU** enquanto e caro: a razao dele
    fica em 1,0 e ele fica na serie. Por isso a afirmacao continua inteira, e
    uma regressao de desenho continua reprovando na maquina limpa e na
    ocupada.
    """

    def __init__(self) -> None:
        self.pares: list[tuple[float, int]] = []

    def cronometrar(self, painel) -> float:
        """Um quadro. Devolve a parede em ms e guarda o par (parede, cpu)."""
        return self.medir(painel._quadro)

    def medir(self, acao) -> float:
        relogio = RELOGIO_DE_CPU
        cpu0 = relogio() if relogio else 0
        inicio = time.perf_counter()
        acao()
        parede = (time.perf_counter() - inicio) * 1000.0
        cpu = (relogio() - cpu0) if relogio else 0
        self.pares.append((parede, cpu))
        return parede

    def __len__(self) -> int:
        return len(self.pares)

    @property
    def parede(self) -> list[float]:
        """Todas as amostras, como estavam antes. Para as afirmacoes de RAZAO,
        que comparam medianas e ja sao robustas a cauda."""
        return [parede for parede, _ in self.pares]

    def limpas(self, o_que: str, cauda: bool = True) -> list[float]:
        """As amostras em que o quadro teve o processador o tempo todo.

        Pula o teste — nao reprova — quando sobra pouco: ali a maquina nao
        deixou o portao medir, e um portao que mede outra coisa nao tem o que
        afirmar. Ver `FRACAO_MINIMA_LIMPA`.

        `cauda=False` para quem so vai usar o PISO da distribuicao — um portao
        de razao que compara `min` com `min`, por exemplo. Esse portao nao
        afirma nada sobre o pior quadro, entao nao precisa que a maioria dos
        quadros tenha rodado limpa: basta que ALGUNS tenham, e o menor deles ja
        e a melhor estimativa do custo do desenho. Exigir a fracao ali trocaria
        um portao que funciona por um `skip` sem motivo.
        """
        import pytest

        if not self.pares:
            raise AssertionError(f"sem amostras: {o_que} nao mediu nada")
        if RELOGIO_DE_CPU is None:  # pragma: no cover — plataforma sem relogio
            return self.parede
        taxas = [cpu / parede for parede, cpu in self.pares if parede > 0]
        mediana = statistics.median(taxas)
        if mediana <= 0:  # pragma: no cover — contador parado
            return self.parede
        limpas = [
            parede
            for parede, cpu in self.pares
            if parede > 0 and (cpu / parede) / mediana >= RAZAO_MINIMA_DE_LIMPEZA
        ]
        fracao = len(limpas) / len(self.pares)
        if fracao < (FRACAO_MINIMA_LIMPA if cauda else 0.0) or not limpas:
            pytest.skip(
                f"maquina sob contencao durante a medicao "
                f"(so {fracao:.0%} dos quadros rodaram sem serem interrompidos) — "
                f"{o_que} mede o escalonador, nao o desenho"
            )
        return limpas
