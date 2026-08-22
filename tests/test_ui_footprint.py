"""Footprint, perfil de volume e delta acumulado — a fase 2 da interface.

Sete coisas sao afirmadas aqui, e cada uma existe porque ha um jeito conhecido
de errar:

1. **Procedencia** — o chip de cada painel e DERIVADO de
   `metodologia/regras.py`, nunca digitado. Um `dict` na UI seria uma segunda
   fonte que envelhece em silencio; o teste prova a derivacao mutando o
   registro e exigindo que o rotulo mude junto.
2. **Leitura pura** — o que a tela mostra sai do analytics sem inventar nada, e
   as duas ressalvas que o analytics deixa implicitas (imbalance contra vizinho
   VAZIO, POC empatado) chegam a tela como campos, nao como nota de rodape.
3. **Custo de leitura** — `footprints_fechados` e `historico` constroem uma
   tupla da SESSAO a cada chamada. O teste conta os acessos e exige que o
   caminho de quadro nao os toque.
4. **Eixos compartilhados** — o perfil e o delta usam os eixos do footprint por
   IDENTIDADE DE OBJETO. F5 da referencia e justamente dois eixos de preco
   diferentes lado a lado; a defesa nao e "a formula e a mesma", e "o objeto e
   o mesmo".
5. **Trabalho** — mudar o candle vivo suja UMA coluna, nao a grade. Medido como
   retangulos sujos (determinista) e como razao quadro-cheio/incremental (o
   portao de §6).
6. **Geometria por pixel, com prova por mutacao** — as barras sao lidas do
   backing store e conferidas contra a MESMA funcao que o desenho usa. E cada
   guarda de proporcionalidade e submetido a uma mutacao (um piso plantado) que
   ele tem de reprovar; um guarda que passa com o defeito plantado nao e um
   guarda, e teatro.
7. **Sem cor e canal** — a direcao continua recuperavel com o eixo direcional
   colapsado, e as ressalvas viajam no mesmo portador do veredito.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402

from fluxopro.analytics.delta import ConfigDelta, CumulativeDelta  # noqa: E402
from fluxopro.analytics.footprint import (  # noqa: E402
    ConfigFootprint,
    Footprint,
    FootprintPorTimeframe,
)
from fluxopro.analytics.volume_profile import (  # noqa: E402
    ConfigVolumeProfile,
    VolumeProfile,
)
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import WDO_GRID, AgressorSide, Trade  # noqa: E402
from fluxopro.metodologia.confianca import Confianca, RegraDocumentada  # noqa: E402
from fluxopro.metodologia.regras import REGRAS  # noqa: E402
from fluxopro.ui import formato, tokens  # noqa: E402
from fluxopro.ui.paineis.delta_acumulado import (  # noqa: E402
    CandleDeltaTela,
    LeituraDelta,
    PainelDeltaAcumulado,
    _degrau_1_2_5,
    _incremento_de,
    derivar_delta,
)
from fluxopro.ui.paineis.footprint import (  # noqa: E402
    DEGRAUS_QTY,
    ESCALA_SALDO,
    _MAX_NIVEIS_POR_COLUNA,
    Celula,
    Coluna,
    EixoPreco,
    EixoTempo,
    LeituraFootprint,
    PainelFootprint,
    degrau_qty,
    derivar_footprint,
    procedencia_de_config,
    regras_do_campo,
    texto_que_cabe,
)
from fluxopro.ui.paineis.perfil import (  # noqa: E402
    LeituraPerfil,
    PainelPerfil,
    derivar_perfil,
)

T0 = 1_700_000_000_000_000_000
TF = 60_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)


# ==========================================================================
# Fabricas
# ==========================================================================
def coluna(
    inicio: int = T0,
    niveis: dict[int, tuple[int, int]] | None = None,
    *,
    viva: bool = True,
    sem_lado: int = 0,
    **extra,
) -> Coluna:
    """`{preco: (qty_venda, qty_compra)}` -> `Coluna`, com os totais coerentes."""
    niveis = niveis or {BASE: (10, 20)}
    celulas = tuple(
        (preco, Celula(qty_venda=v, qty_compra=c, qty_sem_lado=0))
        for preco, (v, c) in sorted(niveis.items())
    )
    venda = sum(v for v, _ in niveis.values())
    compra = sum(c for _, c in niveis.values())
    return Coluna(
        inicio_ns=inicio,
        viva=viva,
        niveis=celulas,
        volume_total=venda + compra + sem_lado,
        volume_compra=compra,
        volume_venda=venda,
        volume_sem_lado=sem_lado,
        delta=compra - venda,
        preco_maximo=max(niveis),
        preco_minimo=min(niveis),
        **extra,
    )


def _pronto(painel, largura: int, altura: int):
    painel.resize(largura, altura)
    painel.show()
    painel.ao_redimensionar(largura, altura)
    painel._recriar_backing()
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def footprint(qapp):
    painel = _pronto(PainelFootprint(WDO_GRID, timeframe_ns=TF), 900, 420)
    painel.aplicar(LeituraFootprint(viva=coluna()))
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def eixo() -> EixoPreco:
    e = EixoPreco(tokens.PADRAO.celula_footprint_h)
    e.configurar(24, 25)
    e.recentralizar(BASE, 0.25)
    return e


@pytest.fixture
def perfil(qapp, eixo):
    return _pronto(PainelPerfil(WDO_GRID, eixo), 200, 24 + 25 * eixo.altura_linha)


@pytest.fixture
def delta(qapp):
    eixo_tempo = EixoTempo(tokens.PADRAO.celula_footprint_w)
    eixo_tempo.configurar(90, 12)
    eixo_tempo.timeframe_ns = TF
    return _pronto(PainelDeltaAcumulado(eixo_tempo), 90 + 12 * 46, 200)


def _trade(ns: int, preco: int, qty: int, lado: AgressorSide) -> Trade:
    return Trade(ns, "WDOV26", preco, qty, lado, f"t{ns}")


def _recorte(painel, rect: QRect) -> tuple:
    """Os pixels de um retangulo do backing, como tupla de RGB.

    Nao `bytes(...constBits())`: o `QImage` tem enchimento de linha, e os bytes
    de enchimento nao sao inicializados — duas capturas identicas podiam
    diferir no primeiro byte de cada linha e o teste acusava uma diferenca que
    nao existe em pixel nenhum. Custou uma investigacao; fica escrito."""
    imagem = painel._backing.toImage()
    return tuple(
        imagem.pixelColor(x, y).rgb()
        for y in range(rect.top(), rect.bottom() + 1)
        for x in range(rect.left(), rect.right() + 1)
    )


def _cronometrar(painel) -> float:
    inicio = time.perf_counter()
    painel._quadro()
    return (time.perf_counter() - inicio) * 1000.0


# ==========================================================================
# 1. Procedencia — derivada do registro, provada por mutacao
# ==========================================================================
class TestProcedencia:
    def test_nenhum_conceito_desta_fase_e_regra_do_metodo(self):
        """O achado que o chip publica.

        `metodologia/regras.py` nao tem familia `footprint.*`,
        `volume_profile.*` nem `delta.*`. Footprint, imbalance diagonal, POC,
        area de valor e delta acumulado sao componentes genericos de order
        flow, de origem interna do projeto — e apresenta-los como leitura do
        metodo seria a falha que `regras.py` existe para tornar impossivel."""
        familias = {i.split(".")[0] for i in REGRAS}
        assert "footprint" not in familias
        assert "volume_profile" not in familias
        assert "delta" not in familias

    @pytest.mark.parametrize(
        "tipo", [ConfigFootprint, ConfigVolumeProfile, ConfigDelta]
    )
    def test_o_chip_conta_TODOS_os_botoes_da_configuracao(self, tipo):
        """`k/n` com `n` derivado de `dataclasses.fields`.

        Derivar em vez de listar tem uma consequencia que e o ponto: um botao
        novo entra na conta sozinho, e nao existe nome morto a envelhecer."""
        from dataclasses import fields

        rotulo, cor = procedencia_de_config(tipo)
        assert rotulo.endswith("0/%d" % len(fields(tipo)))
        assert "S/ REGISTRO" in rotulo
        assert cor is tokens.ABSORPTION

    def test_registrar_uma_regra_muda_o_chip_SEM_tocar_na_UI(self):
        """A prova por mutacao de que a derivacao e real.

        Se houvesse um `dict` digitado no painel, esta mutacao passaria
        despercebida — o registro ganharia uma regra e a tela continuaria
        dizendo `S/ REGISTRO`. Como a fonte e o registro, o rotulo muda
        sozinho."""
        campo = "limiar_imbalance"
        qualificado = "ConfigFootprint." + campo
        antes, cor_antes = procedencia_de_config(ConfigFootprint)
        regra = RegraDocumentada(
            id="footprint.imbalance_diagonal",
            titulo="Imbalance diagonal",
            confianca=Confianca.CONFIRMADO,
            secao="teste",
            citacao="a comparacao correta e contra o nivel vizinho",
            fonte="TESTE",
            nota="Vira " + qualificado + ".",
        )
        REGRAS[regra.id] = regra
        regras_do_campo.cache_clear()
        try:
            depois, cor_depois = procedencia_de_config(ConfigFootprint)
            assert regras_do_campo(qualificado) == (regra.id,)
            assert depois != antes
            assert depois.endswith("1/4")
            assert cor_depois is tokens.ABSORPTION  # os outros 3 seguem sem regra
        finally:
            del REGRAS[regra.id]
            regras_do_campo.cache_clear()
        assert procedencia_de_config(ConfigFootprint) == (antes, cor_antes)


# ==========================================================================
# 2. A escada de intensidade e ABSOLUTA
# ==========================================================================
class TestEscadaDeIntensidade:
    def test_e_monotonica_e_satura_nas_pontas(self):
        graus = [degrau_qty(q) for q in (1, 3, 10, 30, 100, 300, 1_000, 3_000)]
        assert graus == sorted(graus)
        assert degrau_qty(0) == -1
        assert degrau_qty(-5) == -1
        assert degrau_qty(10**9) == tokens.N_DEGRAUS_INTENSIDADE - 1
        assert len(DEGRAUS_QTY) == tokens.N_DEGRAUS_INTENSIDADE - 1

    def test_a_mesma_quantidade_da_o_mesmo_degrau_em_candles_diferentes(self, qapp):
        """**A propriedade que separa esta escada de uma catraca.**

        Uma intensidade relativa ao maximo do candle faria a MESMA celula de
        40 lotes sair escura num candle magro e apagada num candle gordo — o
        defeito 4 de `hud.py`, deslocado do comprimento para a saturacao. Aqui
        um candle com 4.000 lotes num nivel e outro com 40 desenham a celula
        de 40 exatamente igual."""
        painel = _pronto(PainelFootprint(WDO_GRID, timeframe_ns=TF), 900, 420)

        def recorte(vizinho: int) -> bytes:
            painel.aplicar(
                LeituraFootprint(viva=coluna(niveis={BASE: (40, 0), BASE + 1: (vizinho, 0)}))
            )
            painel.marcar_tudo_sujo()
            painel._quadro()
            linha = painel.eixo_preco.linha_do_preco(BASE)
            ultimo = len(painel.colunas_visiveis) - 1
            return _recorte(painel, painel.rect_celula(linha, ultimo))

        assert recorte(40) == recorte(4_000)


# ==========================================================================
# 3. Leitura pura — o analytics chega a tela com as ressalvas
# ==========================================================================
class TestLeitura:
    def _footprint_com(self, trades) -> Footprint:
        fp = Footprint(ConfigFootprint())
        for t in trades:
            fp.registrar_trade(t)
        return fp

    def test_imbalance_contra_vizinho_com_volume_e_MEDIDO(self):
        fp = self._footprint_com(
            [
                _trade(T0, BASE, 100, AgressorSide.BUY),
                _trade(T0 + 1, BASE + 1, 10, AgressorSide.SELL),
            ]
        )
        col = derivar_footprint(_FonteFootprint(fp, T0), None).viva
        celula = dict(col.niveis)[BASE]
        assert celula.imbalance == 1
        assert celula.imbalance_medido is True

    def test_imbalance_contra_vizinho_VAZIO_nao_e_medido(self):
        """`analytics/footprint.py` devolve o preco assim mesmo quando o
        vizinho diagonal tem zero do outro lado — razao infinita. Publicar
        isso com a mesma marca de um 3:1 medido e entregar o veredito sem a
        ressalva; o campo existe para que o desenho consiga distinguir."""
        fp = self._footprint_com([_trade(T0, BASE, 100, AgressorSide.BUY)])
        col = derivar_footprint(_FonteFootprint(fp, T0), None).viva
        celula = dict(col.niveis)[BASE]
        assert celula.imbalance == 1
        assert celula.imbalance_medido is False

    def test_o_volume_sem_lado_entra_no_total_e_no_denominador_do_saldo(self):
        """O RLP anonimiza ate 15% do volume de WDO/WIN. Um candle com 40% do
        volume sem agressor divulgado nao pode desenhar saldo de 100%: ele nao
        sabe o lado de 40% do que passou."""
        fp = self._footprint_com(
            [
                _trade(T0, BASE, 60, AgressorSide.BUY),
                _trade(T0 + 1, BASE, 40, AgressorSide.UNKNOWN),
            ]
        )
        col = derivar_footprint(_FonteFootprint(fp, T0), None).viva
        assert col.volume_total == 100
        assert col.volume_sem_lado == 40
        assert col.delta == 60
        assert col.fracao_saldo == pytest.approx(0.6)

    def test_a_coluna_tem_teto_de_niveis(self):
        """Rede contra candle patologico (gap, feed corrompido). A estrutura do
        painel e limitada pelo produto `colunas na tela x niveis do candle`,
        nunca pela sessao."""
        fp = self._footprint_com(
            [_trade(T0 + i, BASE + i, 1, AgressorSide.BUY) for i in range(600)]
        )
        col = derivar_footprint(_FonteFootprint(fp, T0), None).viva
        assert len(col.niveis) == _MAX_NIVEIS_POR_COLUNA

    def test_o_poc_empatado_e_dito(self):
        """`volume_profile.py` desempata pelo preco mais baixo e admite na
        propria docstring que nao ha convencao universal. Um POC escolhido por
        criterio arbitrario nao pode sair com a mesma marca de um POC unico."""
        vp = VolumeProfile()
        vp.registrar_trade(_trade(T0, BASE, 10, AgressorSide.BUY))
        vp.registrar_trade(_trade(T0 + 1, BASE + 1, 10, AgressorSide.SELL))
        leitura = derivar_perfil(vp, (BASE - 5, BASE + 5))
        assert leitura.poc_empatado is True
        vp.registrar_trade(_trade(T0 + 2, BASE, 5, AgressorSide.BUY))
        assert derivar_perfil(vp, (BASE - 5, BASE + 5)).poc_empatado is False

    def test_o_perfil_e_recortado_pela_TELA_e_o_poc_pela_SESSAO(self):
        """Recortar antes de calcular daria um POC da janela em vez do POC da
        sessao — outra coisa, e nao a que o operador pede."""
        vp = VolumeProfile()
        vp.registrar_trade(_trade(T0, BASE + 50, 900, AgressorSide.BUY))
        for i in range(5):
            vp.registrar_trade(_trade(T0 + i + 1, BASE + i, 10, AgressorSide.SELL))
        leitura = derivar_perfil(vp, (BASE - 2, BASE + 2))
        assert leitura.poc == BASE + 50
        assert all(BASE - 2 <= p <= BASE + 2 for p, _ in leitura.niveis)

    def test_o_corte_da_area_de_valor_vem_da_configuracao(self):
        vp = VolumeProfile(config=ConfigVolumeProfile(value_area_pct=0.55))
        vp.registrar_trade(_trade(T0, BASE, 10, AgressorSide.BUY))
        assert derivar_perfil(vp, (BASE - 1, BASE + 1)).pct_area == 0.55


class _FonteFootprint:
    """Duble de `FootprintPorTimeframe` que CONTA acessos ao historico.

    `footprints_fechados` constroi uma tupla da sessao inteira a cada chamada.
    Um painel que a lesse por quadro pagaria O(sessao) a 62 Hz — e o defeito
    seria invisivel numa suite rapida e fatal num pregao de seis horas. O
    contador transforma isso em assercao."""

    def __init__(self, footprint: Footprint, inicio_ns: int, fechados=()) -> None:
        self._atual = footprint
        self._inicio_atual_ns = inicio_ns
        self._fechados = tuple(fechados)
        self.acessos_ao_historico = 0

    @property
    def footprint_atual(self):
        return self._atual

    @property
    def footprints_fechados(self):
        self.acessos_ao_historico += 1
        return self._fechados


class TestCustoDeLeitura:
    def test_derivar_footprint_nao_toca_no_historico_fora_da_virada(self):
        fp = Footprint(ConfigFootprint())
        fp.registrar_trade(_trade(T0, BASE, 10, AgressorSide.BUY))
        fonte = _FonteFootprint(fp, T0)
        for _ in range(500):
            derivar_footprint(fonte, T0)
        assert fonte.acessos_ao_historico == 0

    def test_derivar_footprint_toca_no_historico_UMA_vez_na_virada(self):
        fp = Footprint(ConfigFootprint())
        fp.registrar_trade(_trade(T0 + TF, BASE, 10, AgressorSide.BUY))
        fonte = _FonteFootprint(fp, T0 + TF)
        leitura = derivar_footprint(fonte, T0)
        assert fonte.acessos_ao_historico == 1
        assert leitura.viva is not None
        assert leitura.fechada is None  # historico vazio: nao inventa candle

    def test_derivar_delta_nao_toca_no_historico_fora_da_virada(self):
        bus = Barramento()
        fonte = CumulativeDelta(bus, "WDOV26", ConfigDelta(timeframe_ns=TF))
        bus.publicar(_trade(T0, BASE, 10, AgressorSide.BUY))
        chamadas = {"n": 0}
        original = type(fonte).historico.fget

        def espiao(self):
            chamadas["n"] += 1
            return original(self)

        inicio = fonte.candle_atual.timestamp_inicio_ns
        type(fonte).historico = property(espiao)
        try:
            derivar_delta(fonte, None, 12)  # bootstrap: 1 acesso, legitimo
            for _ in range(500):
                derivar_delta(fonte, inicio, 12)
        finally:
            type(fonte).historico = property(original)
        assert chamadas["n"] == 1


# ==========================================================================
# 4. Eixos compartilhados — por IDENTIDADE, nao por coincidencia
# ==========================================================================
class TestEixosCompartilhados:
    def test_o_perfil_usa_O_MESMO_objeto_de_eixo_do_footprint(self, qapp, footprint):
        painel = PainelPerfil(WDO_GRID, footprint.eixo_preco)
        assert painel.eixo is footprint.eixo_preco

    def test_as_linhas_de_preco_coincidem_pixel_a_pixel(self, qapp, footprint):
        """F5 da referencia e a linha 5 da esquerda nao ter relacao com a linha
        5 da direita. Aqui a linha `k` das duas pecas tem o mesmo `y` e fala do
        mesmo preco, e a defesa e o objeto compartilhado."""
        painel = _pronto(
            PainelPerfil(WDO_GRID, footprint.eixo_preco),
            200,
            footprint.height(),
        )
        for linha in range(footprint.eixo_preco.n_linhas):
            celula = footprint.rect_celula(linha, 0)
            barra = painel.rect_barra(linha)
            assert barra.top() >= celula.top()
            assert barra.bottom() <= celula.bottom()
            assert footprint.eixo_preco.preco_da_linha(linha) == painel.eixo.preco_da_linha(
                linha
            )

    def test_as_colunas_de_tempo_coincidem_pixel_a_pixel(self, qapp, footprint):
        painel = _pronto(
            PainelDeltaAcumulado(footprint.eixo_tempo), footprint.width(), 200
        )
        for indice in range(footprint.eixo_tempo.n_colunas):
            assert (
                painel.rect_coluna_inteira(indice).left()
                == footprint.rect_coluna_inteira(indice).left()
            )

    def test_o_alinhamento_e_CONFERIDO_e_nao_presumido(self, qapp, delta):
        """`CumulativeDelta` recebe o proprio `ConfigDelta.timeframe_ns`, que
        NAO e o `ConfigOperacao.timeframe_ns` do footprint. Os dois batem por
        default e sao calibraveis em separado — um painel que presumisse o
        alinhamento mentiria em silencio no dia em que alguem mexesse num
        deles."""
        _alimentar_delta(delta, [100 * i for i in range(12)], semear=True)
        assert delta.alinhado is True
        for indice, candle in enumerate(delta.colunas_visiveis):
            if candle is not None:
                assert delta.eixo.coluna_do_inicio(candle.inicio_ns) == indice

    def test_timeframe_divergente_acende_o_aviso(self, qapp, delta):
        """Com candle de meio minuto do lado do delta, nenhum carimbo casa com
        a fileira do footprint — e a tela tem de DIZER isso em vez de desenhar
        as barras em colunas que falam de outro instante."""
        delta.eixo.inicios = [T0 + i * TF for i in range(delta.eixo.n_colunas)]
        delta.eixo.versao += 1
        delta.aplicar(
            LeituraDelta(
                viva=CandleDeltaTela(T0 + 3 * (TF // 2) + 1, 10, 10, BASE, viva=True),
                acumulado_sessao=10,
                timeframe_ns=TF // 2,
            )
        )
        assert delta.alinhado is False

    def test_uma_corrida_de_um_quadro_nao_desloca_a_fileira(self, qapp, delta):
        """**O defeito que a colocacao POR CHAVE existe para nao ter.**

        As duas pecas leem objetos VIVOS que a thread da fonte esta mutando,
        entao um candle pode nascer entre o `derivar_footprint` e o
        `derivar_delta` do mesmo quadro. A versao anterior rolava a propria
        fileira ao detectar a virada na sua fonte: uma corrida bastava para
        este painel rolar uma vez a mais e ficar **permanentemente** deslocado
        — deslocamento por corrida nao se corrige sozinho, ele sobrevive a
        todas as viradas seguintes. Aqui o painel recebe o candle novo ANTES de
        o eixo conhece-lo, e a fileira nao anda."""
        _alimentar_delta(delta, [100 * i for i in range(12)], semear=True)
        antes = list(delta.colunas_visiveis)
        n = delta.eixo.n_colunas
        adiantado = CandleDeltaTela(T0 + n * TF, 10, 9_999, BASE, viva=True)
        delta.aplicar(
            LeituraDelta(viva=adiantado, acumulado_sessao=9_999, timeframe_ns=TF)
        )
        assert list(delta.colunas_visiveis) == antes, (
            "o candle adiantado deslocou a fileira em vez de esperar o eixo"
        )
        assert delta.alinhado is True
        delta.eixo.rolar_virada(T0 + (n - 1) * TF)
        delta.eixo.registrar(n - 1, T0 + n * TF)
        delta.aplicar(
            LeituraDelta(viva=adiantado, acumulado_sessao=9_999, timeframe_ns=TF)
        )
        assert delta.colunas_visiveis[n - 1] == adiantado

    def test_a_versao_do_eixo_so_anda_quando_o_valor_muda(self):
        """Sem esta guarda, o footprint bumparia a versao a cada quadro so por
        reafirmar o candle vivo, e todo painel que observa a versao passaria a
        fazer quadro cheio a 62 Hz."""
        eixo = EixoTempo(46)
        eixo.configurar(90, 4)
        antes = eixo.versao
        eixo.registrar(3, T0)
        assert eixo.versao == antes + 1
        for _ in range(100):
            eixo.registrar(3, T0)
        assert eixo.versao == antes + 1


# ==========================================================================
# 5. Trabalho — retangulos sujos e o portao de §6
# ==========================================================================
RAZAO_MINIMA = 5.0
"""O portao de `tests/test_ui_desempenho.py`, aplicado a estes tres paineis.

Nao afirma velocidade: afirma que redesenhar UMA coluna e muito mais barato
que redesenhar a grade. Um `desenhar` que ignorasse a regiao suja deixaria a
tela CORRETA e derrubaria esta razao para 1."""


LIMITE_P95_MS = 4.0
"""O numero de §6, fase 0, item 5: o CI reprova acima de 4 ms p95 no quadro
incremental do footprint. §2 mediu 3,17 ms p95 no caminho incremental
(backing store + repinta so a coluna corrente); medido aqui, numa grade de
22 colunas x 31 niveis a 1160x520, **1,73 ms p95**. O regresso vira erro, e
nao descoberta tardia."""


class TestOrcamentoDeQuadro:
    def test_o_quadro_incremental_do_footprint_cabe_no_orcamento(self, qapp):
        """A grade do retrato, no tamanho do retrato.

        A medicao que importa nao e a do painel pequeno do resto do arquivo:
        e a de uma tela cheia, porque e nela que a regiao suja tem mais o que
        poupar e mais o que perder."""
        painel = _pronto(PainelFootprint(WDO_GRID, timeframe_ns=TF), 1160, 520)
        n = painel.eixo_tempo.n_colunas
        painel.eixo_preco.recentralizar(BASE, 0.25)
        cheia = {BASE + k: (100 + k, 200 - k) for k in range(-15, 16)}
        painel._colunas = [
            coluna(inicio=T0 + i * TF, niveis=cheia, viva=False) for i in range(n)
        ]
        for _ in range(6):
            painel.marcar_tudo_sujo()
            painel._quadro()
        amostras: list[float] = []
        for i in range(200):
            painel._colunas[n - 1] = coluna(
                inicio=T0 + (n - 1) * TF,
                niveis={p: (v, c + i % 37) for p, (v, c) in cheia.items()},
                viva=True,
            )
            painel.marcar_sujo(painel.rect_coluna_inteira(n - 1))
            amostras.append(_cronometrar(painel))
        p95 = sorted(amostras)[int(len(amostras) * 0.95)]
        assert p95 < LIMITE_P95_MS, f"quadro incremental do footprint a {p95:.3f} ms p95"


class TestTrabalho:
    def test_o_footprint_parado_nao_desenha_nada(self, footprint):
        leitura = LeituraFootprint(viva=coluna())
        footprint.aplicar(leitura)
        footprint._quadro()
        footprint.zerar_medicao()
        for _ in range(2_000):
            footprint.aplicar(leitura)
            footprint._quadro()
        assert footprint.quadros_desenhados == 0
        assert footprint.quadros_vazios == 2_000

    def test_mudar_o_candle_vivo_suja_UMA_coluna(self, footprint):
        footprint.aplicar(LeituraFootprint(viva=coluna(niveis={BASE: (10, 20)})))
        footprint._quadro()
        footprint.aplicar(LeituraFootprint(viva=coluna(niveis={BASE: (10, 21)})))
        ultimo = len(footprint.colunas_visiveis) - 1
        assert footprint._sujos == [footprint.rect_coluna_inteira(ultimo)]

    def test_a_virada_rola_e_suja_duas_faixas(self, footprint):
        """Candle novo nasce a direita e o backing rola uma coluna (§2, Achado
        1). Duas faixas sujas: a que perdeu a marca de vivo e a que entrou."""
        footprint.aplicar(LeituraFootprint(viva=coluna(inicio=T0)))
        footprint._quadro()
        footprint.aplicar(
            LeituraFootprint(
                fechada=coluna(inicio=T0, viva=False), viva=coluna(inicio=T0 + TF)
            )
        )
        assert 0 < len(footprint._sujos) <= 3
        n = len(footprint.colunas_visiveis)
        assert footprint.colunas_visiveis[n - 2].inicio_ns == T0
        assert footprint.colunas_visiveis[n - 1].inicio_ns == T0 + TF
        assert footprint.colunas_visiveis[n - 2].viva is False

    def test_a_virada_nao_rola_duas_vezes(self, footprint):
        """`aplicar` recebe a fechada E a viva no MESMO quadro. Se as duas
        rolassem, um candle sairia da tela por passada e a grade andaria o
        dobro do que o tempo andou."""
        footprint.aplicar(LeituraFootprint(viva=coluna(inicio=T0)))
        footprint._quadro()
        antes = footprint.eixo_tempo.inicios[0]
        footprint.aplicar(
            LeituraFootprint(
                fechada=coluna(inicio=T0, viva=False), viva=coluna(inicio=T0 + TF)
            )
        )
        assert footprint.eixo_tempo.inicios[-2] == T0
        assert footprint.eixo_tempo.inicios[-1] == T0 + TF
        assert antes != footprint.eixo_tempo.inicios[0] or antes is None

    def test_a_incrementalidade_do_footprint_existe(self, footprint):
        cheio: list[float] = []
        for i in range(40):
            footprint.aplicar(LeituraFootprint(viva=coluna(niveis={BASE: (10, 20 + i)})))
            footprint.marcar_tudo_sujo()
            cheio.append(_cronometrar(footprint))
        incremental: list[float] = []
        for i in range(200):
            footprint.aplicar(LeituraFootprint(viva=coluna(niveis={BASE: (10, 300 + i)})))
            if not footprint.tem_sujeira:
                continue
            incremental.append(_cronometrar(footprint))
        assert incremental
        # MINIMO, e nao mediana: contencao de outra suite na mesma maquina so
        # ADICIONA tempo, entao a menor amostra e a unica que mede o desenho
        # em vez de medir o vizinho.
        razao = min(cheio) / max(min(incremental), 1e-9)
        assert razao >= RAZAO_MINIMA, (
            f"razao cheio/incremental do footprint caiu para {razao:.1f}x "
            f"(cheio {min(cheio):.3f} ms, incremental {min(incremental):.3f} ms)"
        )

    def test_a_incrementalidade_do_perfil_existe(self, qapp):
        """O caso em que ela e mais facil de perder: a barra e normalizada pelo
        POC, entao todo negocio no nivel do POC mexe no denominador de TODAS as
        barras. Comparando volumes, a resposta seria "tudo mudou" quase todo
        quadro; o painel compara PIXEL."""
        eixo_alto = EixoPreco(tokens.PADRAO.celula_footprint_h)
        eixo_alto.configurar(24, 45)
        eixo_alto.recentralizar(BASE, 0.25)
        perfil = _pronto(
            PainelPerfil(WDO_GRID, eixo_alto), 240, 24 + 45 * eixo_alto.altura_linha
        )
        base = _leitura_perfil({BASE + k: 1_000 - 10 * k for k in range(-20, 21)})
        perfil.aplicar(base)
        perfil.marcar_tudo_sujo()
        perfil._quadro()

        cheio: list[float] = []
        for _ in range(40):
            perfil.marcar_tudo_sujo()
            cheio.append(_cronometrar(perfil))
        incremental: list[float] = []
        for i in range(200):
            niveis = {BASE + k: 1_000 - 10 * k for k in range(-20, 21)}
            niveis[BASE + 7] = 300 + i
            perfil.aplicar(_leitura_perfil(niveis))
            if not perfil.tem_sujeira:
                continue
            incremental.append(_cronometrar(perfil))
        assert incremental
        razao = min(cheio) / max(min(incremental), 1e-9)
        assert razao >= RAZAO_MINIMA, (
            f"razao do perfil caiu para {razao:.1f}x "
            f"(cheio {min(cheio):.3f} ms, incremental {min(incremental):.3f} ms)"
        )

    def test_o_poc_crescendo_sem_mover_pixel_nao_suja_nada(self, perfil):
        """A consequencia de comparar o que se DESENHA em vez do que se recebe.

        O POC cresce alguns lotes por negocio; as barras encolhem uma fracao de
        pixel e nenhuma muda de largura inteira. Sujar tudo aqui seria correto e
        seria o fim da incrementalidade deste painel."""
        niveis = {BASE + k: 5_000 - 100 * k for k in range(-8, 9)}
        perfil.aplicar(_leitura_perfil(niveis))
        perfil.marcar_tudo_sujo()
        perfil._quadro()
        assert not perfil.tem_sujeira
        maiores = dict(niveis)
        maiores[BASE - 8] += 1
        perfil.aplicar(_leitura_perfil(maiores))
        # UMA linha: a do POC, cujo NUMERO de lotes mudou. Nenhuma barra mudou
        # de largura inteira, entao nenhuma outra linha e repintada.
        linha_poc = perfil.eixo.linha_do_preco(BASE - 8)
        assert perfil._sujos == [
            QRect(0, perfil.eixo.y_da_linha(linha_poc), perfil.width(), perfil.eixo.altura_linha)
        ]

    def test_a_incrementalidade_do_delta_existe(self, qapp):
        # Trinta colunas, que e a ordem de grandeza de uma tela real de
        # footprint. O teto da razao e o numero de colunas: num painel de doze
        # o custo fixo do quadro (abrir o `QPainter`, repintar a faixa do
        # numero, redesenhar a grade) domina os dois lados e a razao nao chega
        # a 5x nem com a incrementalidade perfeita. Medir num painel pequeno
        # seria medir o custo fixo, nao a propriedade.
        eixo_largo = EixoTempo(tokens.PADRAO.celula_footprint_w)
        eixo_largo.configurar(90, 30)
        eixo_largo.timeframe_ns = TF
        delta = _pronto(PainelDeltaAcumulado(eixo_largo), 90 + 30 * 46, 240)
        _alimentar_delta(delta, [100 * i for i in range(30)], semear=True)
        delta.marcar_tudo_sujo()
        delta._quadro()
        cheio: list[float] = []
        for _ in range(40):
            delta.marcar_tudo_sujo()
            cheio.append(_cronometrar(delta))
        incremental: list[float] = []
        for i in range(200):
            valores = [100 * k for k in range(30)]
            valores[-1] = 400 + i
            delta.aplicar(_leitura_delta(valores, semear=True))
            if not delta.tem_sujeira:
                continue
            incremental.append(_cronometrar(delta))
        assert incremental
        razao = min(cheio) / max(min(incremental), 1e-9)
        assert razao >= RAZAO_MINIMA, (
            f"razao do delta caiu para {razao:.1f}x "
            f"(cheio {min(cheio):.3f} ms, incremental {min(incremental):.3f} ms)"
        )


def _leitura_perfil(niveis: dict[int, int], **extra) -> LeituraPerfil:
    total = sum(niveis.values())
    poc = max(niveis, key=lambda p: (niveis[p], -p))
    return LeituraPerfil(
        niveis=tuple(sorted(niveis.items())),
        poc=poc,
        volume_poc=niveis[poc],
        val=extra.pop("val", min(niveis)),
        vah=extra.pop("vah", max(niveis)),
        pct_area=0.70,
        volume_total=total,
        **extra,
    )


def _alimentar_delta(painel, acumulados: list[int], desde: int = 0, **extra) -> LeituraDelta:
    """Registra as chaves no eixo (papel do FOOTPRINT) e aplica a leitura.

    O painel de delta nao mantem uma fileira propria: ele se posiciona pela
    chave de tempo que o footprint escreveu em `EixoTempo.inicios`. Um teste
    que aplicasse a leitura sem preencher o eixo estaria medindo um painel sem
    eixo — que e um estado que a janela nunca produz."""
    n = painel.eixo.n_colunas
    painel.eixo.inicios = [T0 + (desde + i) * TF for i in range(n)]
    painel.eixo.versao += 1
    leitura = _leitura_delta(acumulados[:n], desde=desde, **extra)
    painel.aplicar(leitura)
    return leitura


def _leitura_delta(acumulados: list[int], desde: int = 0, **extra) -> LeituraDelta:
    historico = tuple(
        CandleDeltaTela(T0 + (desde + i) * TF, 10, valor, BASE)
        for i, valor in enumerate(acumulados[:-1])
    )
    viva = CandleDeltaTela(
        T0 + (desde + len(acumulados) - 1) * TF, 10, acumulados[-1], BASE, viva=True
    )
    return LeituraDelta(
        viva=viva,
        historico=historico if extra.pop("semear", False) else (),
        acumulado_sessao=acumulados[-1],
        timeframe_ns=TF,
        **extra,
    )


# ==========================================================================
# 6. Geometria por pixel, com prova por mutacao
# ==========================================================================
def _ponta_do_saldo(painel: PainelFootprint, indice: int) -> int:
    """Onde a barra de saldo termina, LIDO DO BACKING.

    Le pixel, e nao chamada: um duble de `QPainter` diria que o codigo chamou
    `fillRect`, nunca que o retangulo tinha a largura certa."""
    barra = painel.rect_barra_saldo(indice)
    imagem = painel._backing.toImage()
    y = barra.center().y()
    ignorar = (tokens.BG_RAISED.rgb(), tokens.BORDER_STRONG.rgb())
    xs = [
        x
        for x in range(barra.left(), barra.right() + 1)
        if imagem.pixelColor(x, y).rgb() not in ignorar
    ]
    zero = painel.x_zero_saldo(indice)
    if not xs:
        return zero
    return max(xs) if xs[0] > zero else min(xs)


def _larguras_do_perfil(painel: PainelPerfil) -> list[int]:
    imagem = painel._backing.toImage()
    saida = []
    for linha in range(painel.eixo.n_linhas):
        barra = painel.rect_barra(linha)
        # Uma linha ACIMA do centro: o marcador de POC/VAH/VAL mora no centro
        # da linha e contaminaria a medida da barra.
        y = barra.top() + 1
        n = 0
        for x in range(barra.left(), barra.right() + 1):
            if imagem.pixelColor(x, y).rgb() in _rgbs_neutros():
                n += 1
        saida.append(n)
    return saida


_NEUTROS = None


def _rgbs_neutros():
    global _NEUTROS
    if _NEUTROS is None:
        _NEUTROS = {cor.rgb() for cor in tokens.RAMPA_NEUTRA}
    return _NEUTROS


class TestGeometriaDoSaldo:
    def _colunas_com(self, painel, fracoes: list[float]) -> None:
        for indice, fracao in enumerate(fracoes):
            volume = 10_000
            delta_lotes = int(round(fracao * volume))
            painel._colunas[indice] = Coluna(
                inicio_ns=T0 + indice * TF,
                viva=False,
                niveis=(),
                volume_total=volume,
                volume_compra=(volume + delta_lotes) // 2,
                volume_venda=(volume - delta_lotes) // 2,
                volume_sem_lado=0,
                delta=delta_lotes,
            )
        painel.marcar_tudo_sujo()
        painel._quadro()

    def test_a_ponta_do_saldo_e_proporcional_a_fracao(self, footprint):
        """Proporcionalidade de verdade: dobrar o desequilibrio dobra o desvio.

        Um piso, uma raiz quadrada ou um log passariam num teste de
        monotonicidade. So este pega."""
        fracoes = [0.08, 0.04, 0.02, 0.005, 0.001, 0.0, -0.001, -0.005, -0.02, -0.08]
        self._colunas_com(footprint, fracoes)
        zeros = [footprint.x_zero_saldo(i) for i in range(len(fracoes))]
        medidos = [
            _ponta_do_saldo(footprint, i) - zeros[i] for i in range(len(fracoes))
        ]
        # A meia largura sai da PROPRIA funcao de geometria, no fundo de
        # escala — nunca de uma conta paralela sobre o retangulo, que foi o
        # erro que deixou o guarda do ranking de players aceitar um piso.
        meia = footprint.x_ponta_saldo(0, ESCALA_SALDO) - zeros[0]
        for i, fracao in enumerate(fracoes):
            esperado = int(round(fracao / ESCALA_SALDO * meia))
            assert abs(medidos[i] - esperado) <= 1, (fracao, medidos[i], esperado)
        # E o lado sai do SINAL, com o zero desenhado como marco.
        assert medidos[0] > 0 and medidos[-1] < 0
        assert medidos[5] == 0

    def test_o_guarda_de_proporcionalidade_REPROVA_um_piso(self, footprint):
        """**A prova por mutacao.**

        Um guarda que passa com o defeito plantado nao e um guarda, e teatro.
        Aqui o piso de 3px — exatamente o defeito que atravessou uma rodada
        inteira no ranking de players — e plantado na funcao de geometria que
        desenho e teste COMPARTILHAM, e a assercao acima tem de reprovar."""
        original = PainelFootprint.x_ponta_saldo

        def com_piso(self, coluna, fracao):
            x = original(self, coluna, fracao)
            zero = self.x_zero_saldo(coluna)
            if fracao > 0:
                return max(x, zero + 3)
            if fracao < 0:
                return min(x, zero - 3)
            return x

        PainelFootprint.x_ponta_saldo = com_piso
        try:
            with pytest.raises(AssertionError):
                self.test_a_ponta_do_saldo_e_proporcional_a_fracao(footprint)
        finally:
            PainelFootprint.x_ponta_saldo = original

    def test_saldo_acima_do_fundo_de_escala_satura_COM_marca(self, footprint):
        """Saturar em silencio faria um candle a 12% e outro a 60% sairem com o
        mesmo pixel e nada na tela denunciaria."""
        self._colunas_com(footprint, [ESCALA_SALDO * 3, ESCALA_SALDO / 2])
        barra = footprint.rect_barra_saldo(0)
        saturada_em = footprint.x_ponta_saldo(0, ESCALA_SALDO)
        assert saturada_em <= barra.right(), "a ponta saturada caiu FORA da barra"
        assert _ponta_do_saldo(footprint, 0) == saturada_em
        imagem = footprint._backing.toImage()
        y = barra.center().y()
        ambar = tokens.ABSORPTION.rgb()
        saturada = any(
            imagem.pixelColor(x, y).rgb() == ambar
            for x in range(barra.left(), barra.right() + 1)
        )
        assert saturada
        barra_normal = footprint.rect_barra_saldo(1)
        assert not any(
            imagem.pixelColor(x, barra_normal.center().y()).rgb() == ambar
            for x in range(barra_normal.left(), barra_normal.right() + 1)
        )


class TestGeometriaDoVolume:
    def test_a_barra_de_volume_e_sempre_cheia_e_o_sem_lado_esta_sempre_la(
        self, footprint
    ):
        """Particionada = proporcao, e proporcao tem eixo absoluto: 0..100%.
        Nao ha escala, entao nao ha escala para o canal apagar nem para o
        leitor comparar errado com a barra do vizinho.

        E a fatia sem lado e desenhada mesmo em ZERO — uma faixa que some
        ensina o olho a nao procurar por ela justamente no dia em que 15% do
        volume nao tem agressor divulgado."""
        col = coluna(niveis={BASE: (300, 600)}, sem_lado=100)
        footprint.aplicar(LeituraFootprint(viva=col))
        footprint.marcar_tudo_sujo()
        footprint._quadro()
        indice = len(footprint.colunas_visiveis) - 1
        barra = footprint.rect_barra_volume(indice)
        assert footprint.x_costura_volume(indice, 0.0) == barra.left()
        assert footprint.x_costura_volume(indice, 1.0) == barra.right() + 1
        imagem = footprint._backing.toImage()
        y = barra.center().y()
        vazios = [
            x
            for x in range(barra.left(), barra.right() + 1)
            if imagem.pixelColor(x, y).rgb() == tokens.BG_RAISED.rgb()
        ]
        assert not vazios, "a barra particionada tem de estar SEMPRE cheia"
        # A segunda costura fica onde o sem-lado comeca — e ela existe.
        fim_atribuido = footprint.x_costura_volume(indice, 900 / 1_000)
        assert imagem.pixelColor(fim_atribuido, y).rgb() == tokens.BG_BASE.rgb()

    def test_o_mesmo_saldo_com_volumes_muito_diferentes_desenha_a_mesma_barra(
        self, footprint
    ):
        """A ausencia de escala, afirmada onde ela mora. Volume de candle varre
        ordens de magnitude; enquanto ele nao tocar na geometria, a barra de um
        candle de 500 lotes e a de um de 500.000 sao a mesma."""
        def recorte(escala: int) -> bytes:
            col = coluna(niveis={BASE: (300 * escala, 600 * escala)}, sem_lado=100 * escala)
            footprint.aplicar(LeituraFootprint(viva=col))
            footprint.marcar_tudo_sujo()
            footprint._quadro()
            indice = len(footprint.colunas_visiveis) - 1
            return _recorte(footprint, footprint.rect_barra_volume(indice))

        assert recorte(1) == recorte(1_000)


class TestGeometriaDoPerfil:
    def test_a_barra_do_poc_e_cheia_e_as_outras_sao_proporcionais_a_ela(self, perfil):
        """O fundo de escala nao e escolhido: e o POC, que por definicao e o
        maximo. Nao ha catraca a subir e nao ha rotulo de escala para o canal
        apagar — a propria barra cheia e a legenda do eixo."""
        niveis = {BASE + k: 100 * (10 - abs(k)) for k in range(-6, 7)}
        # As linhas do POC, do VAL e do VAH carregam marcador e rotulo; a
        # medida sai delas.
        leitura = _leitura_perfil(niveis, val=BASE - 6, vah=BASE + 6)
        perfil.aplicar(leitura)
        perfil.marcar_tudo_sujo()
        perfil._quadro()
        medidos = _larguras_do_perfil(perfil)
        util = perfil.largura_util
        # As linhas do POC, do VAL e do VAH carregam marcador e rotulo POR
        # CIMA da barra; medi-las seria medir o rotulo. A proporcionalidade e
        # afirmada nas outras, e e ela que amarra `largura_da_barra` ao pixel.
        marcadas = {
            perfil.eixo.linha_do_preco(p)
            for p in (leitura.poc, leitura.val, leitura.vah)
        }
        conferidas = 0
        for preco, volume in niveis.items():
            linha = perfil.eixo.linha_do_preco(preco)
            if linha is None or linha in marcadas:
                continue
            esperado = int(volume / leitura.volume_poc * util)
            assert abs(medidos[linha] - esperado) <= 1, (preco, medidos[linha], esperado)
            conferidas += 1
        assert conferidas >= 8
        # E a barra do POC e a escala: cheia por definicao, sempre.
        assert perfil.largura_da_barra(leitura.volume_poc) == util

    def test_nao_ha_piso_e_o_nivel_raso_arredonda_para_zero(self, perfil):
        """**Aqui zero e informacao, nao perda.**

        Nos players, comprimento zero significava "este player sumiu da tela" —
        falso, ele existe. Aqui significa "praticamente nada foi negociado
        neste preco", que e a definicao de um LVN. Um piso apagaria justamente
        a distincao entre o nivel vazio e o nivel raso."""
        niveis = {BASE: 100_000, BASE + 1: 1, BASE + 2: 2}
        perfil.aplicar(_leitura_perfil(niveis, val=BASE, vah=BASE))
        perfil.marcar_tudo_sujo()
        perfil._quadro()
        medidos = _larguras_do_perfil(perfil)
        assert medidos[perfil.eixo.linha_do_preco(BASE + 1)] == 0
        assert medidos[perfil.eixo.linha_do_preco(BASE + 2)] == 0
        assert perfil.largura_da_barra(1) == 0

    def test_o_guarda_do_perfil_REPROVA_um_piso(self, perfil):
        """A mesma prova por mutacao: com piso de 3px plantado na geometria
        compartilhada, o guarda de proporcionalidade tem de reprovar."""
        original = PainelPerfil.largura_da_barra

        def com_piso(self, volume):
            largura = original(self, volume)
            return max(largura, 3) if volume > 0 else largura

        PainelPerfil.largura_da_barra = com_piso
        try:
            with pytest.raises(AssertionError):
                self.test_nao_ha_piso_e_o_nivel_raso_arredonda_para_zero(perfil)
        finally:
            PainelPerfil.largura_da_barra = original


class TestGeometriaDoDelta:
    def test_o_zero_esta_sempre_no_eixo_e_no_meio(self, delta):
        # semeado para que as colunas existam

        """A terceira falha de `05_cumulative_delta_b.png`: um eixo de
        `-1,04M` a `-1,51M`, sem o zero. Sem o zero desenhado, a altura de uma
        barra bidirecional deixa de significar qualquer coisa."""
        _alimentar_delta(delta, [9_000 + 100 * i for i in range(12)], semear=True)
        delta.marcar_tudo_sujo()
        delta._quadro()
        plot = delta.area_plot
        assert plot.top() < delta.y_zero() < plot.bottom()
        assert delta.y_de(delta.escala) < delta.y_zero() < delta.y_de(-delta.escala)
        # Simetrico: o mesmo valor com sinais opostos fica a mesma distancia.
        acima = delta.y_zero() - delta.y_de(1_000)
        abaixo = delta.y_de(-1_000) - delta.y_zero()
        assert acima == abaixo

    def test_a_barra_vai_do_zero_ate_o_acumulado(self, delta):
        _alimentar_delta(
            delta, [0, 500, 1_000, -1_000, 2_000, -2_000] + [0] * 6, semear=True
        )
        delta.marcar_tudo_sujo()
        delta._quadro()
        for indice, candle in enumerate(delta.colunas_visiveis):
            if candle is None:
                continue
            barra = delta.rect_barra(indice)
            y = delta.y_de(candle.acumulado)
            assert barra.top() == min(delta.y_zero(), y)
            assert barra.height() == abs(y - delta.y_zero())

    def test_a_escala_e_1_2_5_com_histerese(self, delta):
        # Cada passada usa candles NOVOS (`desde`), senao o anel guardaria os
        # antigos e o pico nunca desceria — o teste estaria medindo a memoria
        # do anel, nao a histerese.
        _alimentar_delta(delta, [1_800] * 12, desde=0, semear=True)
        assert delta.escala == _degrau_1_2_5(1_800) == 2_000
        # Cresce na hora...
        _alimentar_delta(delta, [4_500] * 12, desde=100, semear=True)
        assert delta.escala == 5_000
        # ...e nao encolhe por pouco: sem histerese o painel repintaria inteiro
        # toda vez que o pico oscilasse entre dois degraus vizinhos.
        _alimentar_delta(delta, [2_600] * 12, desde=200, semear=True)
        assert delta.escala == 5_000
        _alimentar_delta(delta, [100] * 12, desde=300, semear=True)
        assert delta.escala == 100

    def test_o_numero_de_linhas_de_grade_denuncia_a_mudanca_de_escala(self, delta):
        """**A peca que substitui o rotulo de 10px.**

        O defeito 4 de `hud.py` foi um `±2,5k` em corpo 10 sendo o unico
        portador do fundo de escala: o canal apagava o rotulo e o leitor
        comparava comprimentos sobre eixos diferentes sem saber. Aqui o
        incremento e sempre redondo, entao quando a escala muda o NUMERO DE
        LINHAS na tela muda — e contar linhas nao depende de ler nada."""
        assert _incremento_de(1_000) == 500
        assert _incremento_de(2_000) == 1_000
        assert _incremento_de(5_000) == 1_000
        assert _incremento_de(1) == 1
        for escala in (1, 2, 5, 10, 100, 200, 500, 1_000, 2_000, 5_000, 10_000):
            incremento = _incremento_de(escala)
            assert incremento >= 1
            assert escala % incremento == 0
            mantissa = incremento
            while mantissa % 10 == 0 and mantissa > 1:
                mantissa //= 10
            assert mantissa in (1, 5), (escala, incremento)


# ==========================================================================
# 7. Sem cor e canal
# ==========================================================================
class TestSemCor:
    def test_a_celula_distingue_compra_de_venda_SEM_cor(self, qapp):
        """Com `PALETA_SEM_COR` as duas cores do eixo direcional sao a MESMA
        cor. O que resta e a POSICAO — coluna esquerda e agressao vendedora,
        coluna direita e compradora — e o recorte prova que ela basta."""
        painel = _pronto(
            PainelFootprint(WDO_GRID, paleta=tokens.PALETA_SEM_COR, timeframe_ns=TF),
            900,
            420,
        )

        def recorte(venda: int, compra: int) -> bytes:
            painel.aplicar(LeituraFootprint(viva=coluna(niveis={BASE: (venda, compra)})))
            painel.marcar_tudo_sujo()
            painel._quadro()
            linha = painel.eixo_preco.linha_do_preco(BASE)
            ultimo = len(painel.colunas_visiveis) - 1
            return _recorte(painel, painel.rect_celula(linha, ultimo))

        assert recorte(120, 0) != recorte(0, 120)

    def test_a_barra_de_saldo_carrega_a_direcao_SEM_cor(self, qapp):
        """O recorte exclui a linha do numero, onde mora o `+`/`−`, que e outro
        portador. Se estes dois quadros ficarem iguais, a direcao esta vivendo
        so no matiz e no texto — que e a falha F2 da referencia."""
        painel = _pronto(
            PainelFootprint(WDO_GRID, paleta=tokens.PALETA_SEM_COR, timeframe_ns=TF),
            900,
            420,
        )
        indice = painel.eixo_tempo.n_colunas - 1

        def recorte(delta_lotes: int) -> bytes:
            painel._colunas[indice] = Coluna(
                inicio_ns=T0,
                viva=False,
                niveis=(),
                volume_total=10_000,
                volume_compra=(10_000 + delta_lotes) // 2,
                volume_venda=(10_000 - delta_lotes) // 2,
                volume_sem_lado=0,
                delta=delta_lotes,
            )
            painel.marcar_tudo_sujo()
            painel._quadro()
            return _recorte(painel, painel.rect_barra_saldo(indice))

        assert recorte(500) != recorte(-500)

    def test_a_paleta_sem_cor_realmente_colapsa_o_eixo(self):
        """Guarda dos dois testes acima: se as cores fossem diferentes, os
        quadros diferirem nao provaria nada."""
        assert tokens.PALETA_SEM_COR.direcional(1) == tokens.PALETA_SEM_COR.direcional(-1)

    def test_os_tres_paineis_desenham_nas_duas_paletas(self, qapp, eixo):
        for paleta in (tokens.PALETA_COR, tokens.PALETA_SEM_COR):
            fp = _pronto(
                PainelFootprint(WDO_GRID, paleta=paleta, timeframe_ns=TF), 900, 420
            )
            fp.aplicar(LeituraFootprint(viva=coluna(sem_lado=50)))
            pf = _pronto(PainelPerfil(WDO_GRID, fp.eixo_preco, paleta=paleta), 200, 420)
            pf.aplicar(_leitura_perfil({BASE + k: 100 + k for k in range(-3, 4)}))
            dl = _pronto(
                PainelDeltaAcumulado(fp.eixo_tempo, paleta=paleta), 900, 200
            )
            _alimentar_delta(dl, [100 * i - 400 for i in range(12)], semear=True)
            for painel in (fp, pf, dl):
                painel.marcar_tudo_sujo()
                painel._quadro()
                assert painel.quadros_desenhados >= 1


class TestCanal:
    def test_o_acumulado_e_a_ressalva_saem_na_MESMA_string(self, delta):
        """A lei do canal na forma mais direta que ela tem.

        `CumulativeDelta` ignora o volume cujo agressor a B3 nao divulga: um
        delta calculado sobre 88% do tape nao e o delta do tape. A ressalva nao
        e um campo ao lado do numero — ela E o final da mesma string, num
        `drawText` so, com uma fonte so, e por isso nenhuma reescala, nenhuma
        quantizacao e nenhum recorte de coluna consegue entregar o numero sem
        ela."""
        delta.aplicar(
            LeituraDelta(
                acumulado_sessao=12_480,
                volume_total=100_000,
                volume_sem_lado=12_000,
                timeframe_ns=TF,
            )
        )
        texto = delta.texto_acumulado()
        assert texto.startswith(formato.MAIS + "12.480")
        assert "12% S/ LADO" in texto
        # Abaixo de 1% a ressalva nao entra: custaria mais atencao do que
        # corrige, e o numero exato continua no perfil.
        delta.aplicar(
            LeituraDelta(
                acumulado_sessao=-12_480,
                volume_total=100_000,
                volume_sem_lado=500,
                timeframe_ns=TF,
            )
        )
        assert delta.texto_acumulado() == formato.MENOS + "12.480"

    def test_o_imbalance_sem_razao_usa_a_mesma_forma_com_outra_cor(self, qapp):
        """Mesma espessura, mesmo lugar, mesmo retangulo sujo: se o canal comer
        uma marca, come as duas juntas — que e a unica garantia que a lei do
        canal aceita. O que muda e o matiz, e ambar e o vocabulario que este
        projeto ja usa para "o produto nao conseguiu medir isto"."""
        painel = _pronto(PainelFootprint(WDO_GRID, timeframe_ns=TF), 900, 420)
        painel.aplicar(LeituraFootprint(viva=coluna()))  # ancora o eixo de preco

        def marca(medido: bool) -> tuple[int, set[int]]:
            celula = Celula(
                qty_venda=0,
                qty_compra=100,
                qty_sem_lado=0,
                imbalance=1,
                imbalance_medido=medido,
            )
            col = Coluna(
                inicio_ns=T0,
                viva=False,
                niveis=((BASE, celula),),
                volume_total=100,
                volume_compra=100,
                volume_venda=0,
                volume_sem_lado=0,
                delta=100,
                preco_maximo=BASE,
                preco_minimo=BASE,
            )
            indice = painel.eixo_tempo.n_colunas - 1
            painel._colunas[indice] = col
            painel.marcar_tudo_sujo()
            painel._quadro()
            linha = painel.eixo_preco.linha_do_preco(BASE)
            rect = painel.rect_celula(linha, indice)
            imagem = painel._backing.toImage()
            y = rect.center().y()
            alvo = tokens.ABSORPTION.rgb() if not medido else tokens.BUY.rgb()
            xs = {
                x
                for x in range(rect.left(), rect.right() + 1)
                if imagem.pixelColor(x, y).rgb() == alvo
            }
            return len(xs), xs

        largura_medido, onde_medido = marca(True)
        largura_nao, onde_nao = marca(False)
        assert largura_medido == largura_nao == 2
        assert onde_medido == onde_nao

    def test_o_poc_empatado_usa_a_mesma_marca_em_ambar(self, perfil):
        niveis = {BASE: 100, BASE + 1: 100, BASE + 2: 10}

        def cor_da_marca(empatado: bool) -> set[int]:
            perfil.aplicar(_leitura_perfil(niveis, poc_empatado=empatado))
            perfil.marcar_tudo_sujo()
            perfil._quadro()
            linha = perfil.eixo.linha_do_preco(perfil.leitura.poc)
            y = perfil.eixo.y_da_linha(linha) + perfil.eixo.altura_linha // 2
            imagem = perfil._backing.toImage()
            return {imagem.pixelColor(x, y).rgb() for x in range(0, perfil.width())}

        assert tokens.POC.rgb() in cor_da_marca(False)
        assert tokens.ABSORPTION.rgb() in cor_da_marca(True)

    def test_numero_que_nao_cabe_e_abreviado_e_NUNCA_truncado(self, footprint):
        """`1.216` cortado pela largura da celula em `1.2` nao e um numero
        menor: e um numero **errado**, e o leitor nao tem como saber que faltou
        pedaco. A unidade abreviada e pior que a unidade fixa; e ela e MUITO
        melhor que o corte silencioso."""
        fm = footprint._fm_celula
        largura_curta = fm.horizontalAdvance("1,2k")
        assert texto_que_cabe(fm, largura_curta, "1.216", "1,2k") == "1,2k"
        largura_longa = fm.horizontalAdvance("1.216")
        assert texto_que_cabe(fm, largura_longa, "1.216", "1,2k") == "1.216"
        assert texto_que_cabe(fm, 1, "1.216", "1,2k") == ""


# ==========================================================================
# 8. Retencao — nada cresce com a sessao
# ==========================================================================
class TestRetencao:
    def test_o_footprint_guarda_slots_de_tela_e_nao_historico(self, footprint):
        n = footprint.eixo_tempo.n_colunas
        for i in range(500):
            footprint.aplicar(
                LeituraFootprint(
                    fechada=coluna(inicio=T0 + i * TF, viva=False),
                    viva=coluna(inicio=T0 + (i + 1) * TF),
                )
            )
        assert len(footprint.colunas_visiveis) == n
        assert len(footprint.eixo_tempo.inicios) == n

    def test_o_delta_guarda_slots_de_tela_e_nao_historico(self, delta):
        n = delta.eixo.n_colunas
        for i in range(500):
            delta.eixo.rolar_virada(T0 + i * TF)
            delta.eixo.registrar(n - 1, T0 + (i + 1) * TF)
            delta.aplicar(
                LeituraDelta(
                    fechada=CandleDeltaTela(T0 + i * TF, 5, 5 * i, BASE),
                    viva=CandleDeltaTela(T0 + (i + 1) * TF, 5, 5 * i, BASE, viva=True),
                    acumulado_sessao=5 * i,
                    timeframe_ns=TF,
                )
            )
        assert len(delta.colunas_visiveis) == n
        # `n + 1`: o "mais um" e a folga para o candle que ja nasceu deste lado
        # e que o footprint ainda nao registrou no eixo. Continua sendo teto de
        # TELA — 500 candles entraram, treze ficaram.
        assert len(delta._recentes) <= n + 1

    def test_o_perfil_guarda_uma_linha_por_LINHA_DA_TELA(self, perfil):
        """Indexar por preco faria a estrutura crescer com a amplitude do dia —
        a forma exata do defeito que este projeto ja encontrou oito vezes."""
        perfil.aplicar(_leitura_perfil({BASE + k: 10 + k for k in range(-5, 6)}))
        assert len(perfil._render) == perfil.eixo.n_linhas
        perfil.aplicar(_leitura_perfil({BASE + k: 10 for k in range(-200, 200)}))
        assert len(perfil._render) == perfil.eixo.n_linhas

    def test_encolher_a_janela_DESCARTA_o_excedente(self, footprint):
        footprint.aplicar(LeituraFootprint(viva=coluna()))
        antes = footprint.eixo_tempo.n_colunas
        footprint.resize(300, 420)
        footprint.ao_redimensionar(300, 420)
        assert footprint.eixo_tempo.n_colunas < antes
        assert len(footprint.colunas_visiveis) == footprint.eixo_tempo.n_colunas


# ==========================================================================
# 9. O pipeline inteiro, com analytics de verdade
# ==========================================================================
class TestPipelineReal:
    def test_as_tres_pecas_leem_o_analytics_vivo_e_ficam_alinhadas(self, qapp):
        """O teste que prova a COMPOSICAO, e nao tres paineis que sabem
        desenhar sozinhos."""
        bus = Barramento()
        fpt = FootprintPorTimeframe(bus, "WDOV26", TF)
        cd = CumulativeDelta(bus, "WDOV26", ConfigDelta(timeframe_ns=TF))
        vp = VolumeProfile()

        painel = _pronto(PainelFootprint(WDO_GRID, timeframe_ns=TF), 900, 420)
        lateral = _pronto(PainelPerfil(WDO_GRID, painel.eixo_preco), 200, 420)
        inferior = _pronto(PainelDeltaAcumulado(painel.eixo_tempo), 900, 200)

        ns = T0
        for candle in range(8):
            for k in range(40):
                ns += TF // 50
                lado = AgressorSide.BUY if k % 3 else AgressorSide.SELL
                trade = _trade(ns, BASE + (k % 5) - 2, 10 + k, lado)
                bus.publicar(trade)
                vp.registrar_trade(trade)
            painel.aplicar(
                derivar_footprint(
                    fpt, painel.inicio_vivo_ns, painel.eixo_tempo.n_colunas
                )
            )
            lateral.aplicar(derivar_perfil(vp, painel.faixa_visivel))
            inferior.aplicar(
                derivar_delta(cd, inferior.inicio_vivo_ns, painel.eixo_tempo.n_colunas)
            )
            painel._quadro()
            lateral._quadro()
            inferior._quadro()

        assert inferior.alinhado is True
        preenchidas = [c for c in painel.colunas_visiveis if c is not None]
        assert len(preenchidas) >= 2
        assert sum(1 for c in preenchidas if c.viva) == 1
        assert lateral.leitura.poc is not None
        assert inferior.escala >= 1
        # E o eixo de preco e literalmente o mesmo objeto nas duas pecas.
        assert lateral.eixo is painel.eixo_preco


class TestGeometriaCompartilhada:
    """`x_zero_saldo`, `x_ponta_saldo`, `largura_da_barra` e `y_de` sao usadas
    pelo DESENHO e pelo TESTE.

    A razao esta escrita em sangue no ranking de players: a primeira versao do
    guarda media o desvio contra `rect.center().x()` — `left + (w-1)//2` — que
    e um marco que o desenho nao usa. O off-by-one de um pixel fazia a assercao
    anti-piso passar raspando, e o guarda deixava passar exatamente o piso que
    ja existia no produto."""

    def test_o_zero_do_saldo_e_o_pixel_que_o_desenho_pinta(self, footprint):
        self_colunas = footprint._colunas
        indice = len(self_colunas) - 1
        self_colunas[indice] = Coluna(
            inicio_ns=T0,
            viva=False,
            niveis=(),
            volume_total=1_000,
            volume_compra=500,
            volume_venda=500,
            volume_sem_lado=0,
            delta=0,
        )
        footprint.marcar_tudo_sujo()
        footprint._quadro()
        barra = footprint.rect_barra_saldo(indice)
        imagem = footprint._backing.toImage()
        y = barra.center().y()
        xs = [
            x
            for x in range(barra.left(), barra.right() + 1)
            if imagem.pixelColor(x, y).rgb() == tokens.BORDER_STRONG.rgb()
        ]
        assert xs == [footprint.x_zero_saldo(indice)]

    def test_a_largura_util_do_perfil_e_a_que_o_desenho_usa(self, perfil):
        perfil.aplicar(_leitura_perfil({BASE: 100}))
        assert perfil.largura_da_barra(100) == perfil.largura_util
        assert perfil.rect_barra(0).width() == perfil.largura_util
