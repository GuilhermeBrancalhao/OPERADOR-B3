"""`JanelaMovel` — variação de um contador acumulado numa janela recente, O(1).

Por que não um `deque` de amostras (o padrão usado em `motor/sinais.py` e nos
detectores): ali a janela precisa saber *quais* trades estão dentro, para
recalcular volume comprador × vendedor. Aqui não — o velocímetro e a micro só
precisam de **uma subtração**: valor do contador agora menos valor do contador
no início da janela. Guardar amostra por amostra para fazer uma subtração é
exatamente a forma do defeito descrito em `fluxopro/gravacao/gravador.py`
("guardava um `int` POR EVENTO, do primeiro ao último do pregão, para no fim
produzir DOIS ESCALARES").

O critério dele, aplicado aqui: **qual grandeza limita o `len` disto, e ela
para de crescer enquanto o pregão continua?** Resposta: `n_baldes`, uma
constante de configuração (default 8). Nenhuma estrutura desta classe é
indexada por evento, por trade nem por duração de sessão — são três listas de
`n_baldes` inteiros, alocadas no `__init__` e nunca redimensionadas.

## Como funciona o anel

A janela é dividida em `n_baldes` baldes de `janela_ns // n_baldes` cada. O
balde de um timestamp é `ts // duracao_balde`, e ele mora no slot
`indice % n_baldes` — quando o índice do slot não bate com o índice global
pedido, aquele balde já morreu e é sobrescrito. Ler o início da janela é
procurar o balde vivo mais antigo entre no máximo `n_baldes` slots: O(1), com
constante pequena.

**Preço da aproximação, declarado:** o *lookback* efetivo oscila entre
`(n_baldes-1)/n_baldes · janela_ns` e `janela_ns` conforme o balde corrente
enche — não é uma janela deslizante exata. `duracao_ns` publica o lookback
real de cada leitura, então quem lê nunca precisa adivinhar qual foi. Com
`n_baldes=8` o erro máximo é 12,5% da janela; aumentar `n_baldes` reduz o erro
e o custo continua constante.

Convenção de valor: o contador alimentado tem de valer **0 no início da
sessão** (é o caso de delta acumulado). `resetar(valor_inicial)` existe para
quem começa em outro ponto.
"""

from __future__ import annotations


class JanelaMovel:
    """Anel de baldes sobre um contador acumulado. Memória O(`n_baldes`)."""

    __slots__ = (
        "_janela_ns",
        "_n",
        "_dur",
        "_idx",
        "_ts",
        "_valor",
        "_bal_idx",
        "_bal_valor",
        "_bal_n",
    )

    def __init__(self, janela_ns: int, n_baldes: int = 8) -> None:
        if janela_ns <= 0:
            raise ValueError("janela_ns deve ser positiva")
        if n_baldes < 2:
            raise ValueError("n_baldes deve ser >= 2 (1 balde nao tem passado)")
        if janela_ns // n_baldes < 1:
            raise ValueError("janela_ns curta demais para n_baldes")

        self._janela_ns = janela_ns
        self._n = n_baldes
        self._dur = janela_ns // n_baldes
        self._idx: int | None = None
        self._ts = 0
        self._valor = 0
        self._bal_idx = [-1] * n_baldes
        self._bal_valor = [0] * n_baldes
        self._bal_n = [0] * n_baldes

    # ------------------------------------------------------------------
    def registrar(self, timestamp_ns: int, valor_acumulado: int) -> None:
        """Anota o valor do contador acumulado no instante `timestamp_ns`.

        Timestamp anterior ao último visto é **grampeado** no balde corrente
        em vez de rejeitado: reordenar dentro de uma janela de segundos não
        muda a leitura, e derrubar o componente por um tick fora de ordem
        seria pior do que a imprecisão que ele causa.
        """
        if timestamp_ns < 0:
            raise ValueError("timestamp_ns nao pode ser negativo")

        idx = timestamp_ns // self._dur
        if self._idx is not None and idx < self._idx:
            idx = self._idx

        slot = idx % self._n
        if self._bal_idx[slot] != idx:
            # Balde novo (ou reciclado): seu valor de abertura e o acumulado
            # ANTES desta amostra — e o contador vale 0 no inicio da sessao.
            self._bal_idx[slot] = idx
            self._bal_valor[slot] = self._valor
            self._bal_n[slot] = 0

        self._idx = idx
        self._ts = max(self._ts, timestamp_ns)
        self._valor = valor_acumulado
        self._bal_n[slot] += 1

    # ------------------------------------------------------------------
    def _slot_mais_antigo(self) -> int | None:
        """Slot do balde vivo mais antigo. O(`n_baldes`), constante."""
        if self._idx is None:
            return None
        primeiro = self._idx - (self._n - 1)
        for k in range(primeiro, self._idx + 1):
            slot = k % self._n
            if self._bal_idx[slot] == k:
                return slot
        return None

    @property
    def valor(self) -> int:
        """Último valor do contador acumulado registrado."""
        return self._valor

    @property
    def variacao(self) -> int:
        """Valor agora menos valor no início da janela. `int`, sempre."""
        slot = self._slot_mais_antigo()
        if slot is None:
            return 0
        return self._valor - self._bal_valor[slot]

    @property
    def duracao_ns(self) -> int:
        """Lookback REAL desta leitura — publique-o junto com `variacao`."""
        slot = self._slot_mais_antigo()
        if slot is None:
            return 0
        return self._ts - self._bal_idx[slot] * self._dur

    @property
    def amostras(self) -> int:
        """Quantas amostras caíram nos baldes vivos."""
        if self._idx is None:
            return 0
        total = 0
        primeiro = self._idx - (self._n - 1)
        for k in range(primeiro, self._idx + 1):
            slot = k % self._n
            if self._bal_idx[slot] == k:
                total += self._bal_n[slot]
        return total

    @property
    def indice_balde(self) -> int | None:
        """Índice global do balde corrente — muda quando a janela rola."""
        return self._idx

    @property
    def janela_ns(self) -> int:
        return self._janela_ns

    @property
    def n_baldes(self) -> int:
        return self._n

    def resetar(self, valor_inicial: int = 0) -> None:
        """Zera o anel. As listas são reaproveitadas, nunca realocadas."""
        self._idx = None
        self._ts = 0
        self._valor = valor_inicial
        for i in range(self._n):
            self._bal_idx[i] = -1
            self._bal_valor[i] = valor_inicial
            self._bal_n[i] = 0
