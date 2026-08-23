"""HUD de contexto e ranking de players — comportamento, trabalho e canal.

Cinco coisas sao afirmadas aqui:

1. **Comportamento** — o farol reflete o estagio publicado, o placar nunca
   contradiz o farol, e a leitura degrada sem quebrar quando falta evidencia.
2. **Trabalho** — mudar uma pressao suja UMA banda de 36px, nao as sete.
   Medido como retangulos sujos (determinista) e como razao
   quadro-cheio/incremental (o portao de `tests/test_ui_desempenho.py`,
   aplicado a estes paineis).
3. **Cor** — a direcao continua recuperavel com o eixo direcional colapsado,
   e a prova recorta **so a faixa da barra**, nunca o painel inteiro. Um
   teste de painel inteiro passa pelo texto assinado, que ja e outro portador
   — ele nao prova nada sobre a barra, so parece provar.
4. **Canal** — a peca e entregue por captura e transmissao
   (`scripts/transmissao.py`), entao as leituras que importam tem de estar em
   geometria, nao em corpo 10. Aqui isso vira propriedade afirmavel: a barra
   de pressao **nao tem escala** (nao ha o que o canal apague para produzir
   uma comparacao errada), e dois estagios do farol diferem nos pixels do
   proprio farol, nao so no rotulo.
5. **Retencao** — 5.000 corretoras entram, `top_n` ficam.
"""

from __future__ import annotations

import statistics
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtGui import QImage  # noqa: E402

from tests.medicao import Serie  # noqa: E402

from fluxopro.core.eventos import Side  # noqa: E402
from fluxopro.motor.sinais import EstagioSinal, FaixaConviccao, Sinal  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.hud import (  # noqa: E402
    ALTURA_BARRA_PLAYER,
    BANDA_CONDICAO_0,
    BANDA_FAROL,
    BANDA_PRESSAO,
    BANDA_SALDO_DIA,
    N_BANDAS,
    N_CONDICOES,
    ORDEM_ESTAGIOS,
    ROTULO_CURTO,
    ROTULO_LONGO,
    SETA_COMPRA,
    SETA_VENDA,
    TAXA_NEUTRA,
    TOP_N_PADRAO,
    EstadoCondicao,
    LinhaPlayer,
    PainelHUD,
    PainelPlayers,
    contexto_do_sinal,
    players_de_perfil,
    players_de_ranking,
    pressao_da_janela,
    texto_direcional,
    texto_pressao,
)

T0 = 1_700_000_000_000_000_000


def sinal(
    estagio: EstagioSinal,
    direcao: Side | None = Side.BUY,
    **evidencia,
) -> Sinal:
    base = {"dominancia": 0.78, "faixa": FaixaConviccao.DIRECIONAL.value}
    base.update(evidencia)
    return Sinal(T0, "WDOV26", estagio, direcao, base)


def _pronto(painel, largura: int, altura: int):
    painel.resize(largura, altura)
    painel.show()
    painel.ao_redimensionar(largura, altura)
    painel._recriar_backing()
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def hud(qapp):
    return _pronto(PainelHUD(), 320, PainelHUD().altura_natural)


@pytest.fixture
def players(qapp):
    return _pronto(
        PainelPlayers(), 520, 24 + TOP_N_PADRAO * tokens.PADRAO.altura_linha
    )


# ==========================================================================
# 1. Comportamento
# ==========================================================================
class TestFarol:
    def test_o_farol_conhece_todos_os_estagios_do_motor(self):
        """Se alguem acrescentar um estagio ao motor, isto reprova.

        E deliberado que `ORDEM_ESTAGIOS` seja escrita a mao em vez de
        `list(EstagioSinal)`: a ordem de declaracao de um Enum e acidente de
        edicao, e um estagio novo herdando posicao por sorte no farol seria
        exatamente o tipo de erro que ninguem ve na tela."""
        assert set(ORDEM_ESTAGIOS) == set(EstagioSinal)
        assert len(ORDEM_ESTAGIOS) == len(EstagioSinal)
        for estagio in EstagioSinal:
            assert ROTULO_CURTO[estagio]
            assert ROTULO_LONGO[estagio]

    @pytest.mark.parametrize("estagio", list(EstagioSinal))
    def test_todo_estagio_produz_leitura(self, estagio):
        leitura = contexto_do_sinal(sinal(estagio))
        assert leitura.estagio is estagio
        assert len(leitura.condicoes) == N_CONDICOES

    def test_o_placar_nunca_contradiz_o_farol(self):
        """A razao de as condicoes virem do estagio PUBLICADO.

        `evidencia` carrega os booleanos CRUS (pre-histerese) e eles
        discordam do estagio de proposito. Aqui a evidencia grita `3/3` e o
        estagio publicado e `NA_REGIAO`: o placar tem de seguir o farol."""
        leitura = contexto_do_sinal(
            sinal(EstagioSinal.NA_REGIAO, na_regiao=True, micro_virou=True, pre_sinal=True)
        )
        assert leitura.n_satisfeitas == 2
        assert leitura.condicoes[2].estado is EstadoCondicao.NAO

    def test_pre_sinal_marca_a_micro_como_parcial(self):
        """O estado do meio existe porque `PRE_SINAL` existe.

        Colapsar a terceira condicao em booleano apagaria justamente o
        estagio que interessa a quem esta esperando a entrada."""
        leitura = contexto_do_sinal(sinal(EstagioSinal.PRE_SINAL))
        assert leitura.condicoes[2].estado is EstadoCondicao.PARCIAL
        assert leitura.n_satisfeitas == 2

    def test_confirmado_satisfaz_as_tres(self):
        leitura = contexto_do_sinal(sinal(EstagioSinal.CONFIRMADO))
        assert leitura.n_satisfeitas == 3
        assert all(c.estado is EstadoCondicao.SIM for c in leitura.condicoes)

    def test_bloqueio_por_magnitude_e_dito_e_nao_escondido(self):
        """85% de dominancia com farol apagado precisa de explicacao.

        Sem isto o operador ve o percentual alto, o farol em `NENHUM`, e
        conclui que o painel esta quebrado."""
        leitura = contexto_do_sinal(
            sinal(
                EstagioSinal.NENHUM,
                direcao=None,
                dominancia=0.85,
                bloqueio="magnitude_relativa",
                magnitude_relativa=0.31,
            )
        )
        assert "MAGNITUDE" in leitura.condicoes[0].detalhe
        assert "31%" in leitura.condicoes[0].detalhe

    def test_sem_sinal_nao_quebra(self):
        leitura = contexto_do_sinal(None)
        assert leitura.estagio is EstagioSinal.NENHUM
        assert leitura.n_satisfeitas == 0
        assert all(c.detalhe for c in leitura.condicoes)

    def test_evidencia_vazia_degrada_para_travessao(self):
        leitura = contexto_do_sinal(
            Sinal(T0, "WDOV26", EstagioSinal.DIRECAO_CONFIRMADA, Side.SELL, {})
        )
        assert leitura.estagio is EstagioSinal.DIRECAO_CONFIRMADA
        assert leitura.condicoes[1].detalhe == "—"


class TestSemEscala:
    """A catraca do medidor do dia foi removida, e nao aposentada.

    A classe que morava aqui testava `escala_para`: que a escala nao encolhe,
    que sobe em degrau, que o pior preenchimento e 78%. Eram bons testes de
    uma coisa que nao devia existir — a barra do dia mudava de comprimento
    com o saldo PARADO, e nenhum deles reprovava isso porque todos olhavam a
    escada, nunca o par de quadros."""

    def test_o_modulo_nao_tem_mais_escala_nenhuma(self, qapp):
        """Guarda de reincidencia. Quatro vezes o mesmo defeito nasceu de uma
        grandeza sem teto virando comprimento; a quinta comeca por aqui."""
        import fluxopro.ui.paineis.hud as modulo

        assert not hasattr(modulo, "escala_para")
        assert not hasattr(modulo, "DEGRAUS_ESCALA")
        assert not hasattr(PainelHUD(), "_escala_dia")


class TestFormatacaoDirecional:
    def test_comprador_e_vendedor_nao_sao_grafados_igual(self):
        """A falha F2 da referencia, afirmada como propriedade.

        `06_medidores_agressao_a.png` grafa saldo vendedor `(49,10k)` e saldo
        comprador `(42,31k)` — parenteses nos dois, sem sinal, distinguiveis
        so pela cor do fundo."""
        comprador = texto_direcional(42_310)
        vendedor = texto_direcional(-49_100)
        assert comprador != vendedor
        assert SETA_COMPRA in comprador and "+" in comprador
        assert SETA_VENDA in vendedor and "−" in vendedor
        assert "(" not in comprador and "(" not in vendedor

    def test_zero_nao_aponta_para_lado_nenhum(self):
        texto = texto_direcional(0)
        assert SETA_COMPRA not in texto and SETA_VENDA not in texto

    def test_pressao_simetrica_nao_e_grafada_igual(self):
        """Mesmo perigo, outra grandeza: 63% comprador e 63% vendedor sao o
        mesmo numero, e so a seta os separa no texto."""
        compra = texto_pressao(0.63, 1_000)
        venda = texto_pressao(0.37, 1_000)
        assert "63%" in compra and "63%" in venda
        assert compra != venda
        assert SETA_COMPRA in compra and SETA_VENDA in venda

    def test_janela_vazia_e_equilibrio_e_nao_cem_por_cento_vendedor(self):
        """`MedidorAgressao.taxa_compra` devolve 0,0 sem volume. Passar isso
        cru pintaria a barra inteira de vermelho antes do primeiro negocio do
        dia — o painel inventando um lado a partir de divisao por zero."""
        leitura = contexto_do_sinal(
            sinal(EstagioSinal.NENHUM), taxa_compra_janela=0.0, volume_janela=0
        )
        assert leitura.taxa_compra_janela == 0.5
        assert texto_pressao(leitura.taxa_compra_janela, 0) == "· —"


class TestAdaptadores:
    def test_le_o_ranking_de_corretoras_real(self):
        from fluxopro.analytics.brokers import RankingCorretoras
        from fluxopro.core.barramento import Barramento

        bus = Barramento()
        ranking = RankingCorretoras(bus, "WDOV26")
        for i in range(5):
            bus.publicar(_trade(qty=10 * (i + 1), comprador=f"C{i}", vendedor="V"))
        linhas = players_de_ranking(ranking, top_n=3)
        assert len(linhas) == 3
        assert linhas[0].volume_total >= linhas[1].volume_total >= linhas[2].volume_total

    def test_le_o_perfil_de_player_real_com_agressividade(self):
        from fluxopro.microestrutura.perfil_player import PerfilPlayer

        perfil = PerfilPlayer("WDOV26")
        for i in range(4):
            perfil.ao_trade(_trade(qty=5 * (i + 1), comprador=f"C{i}", vendedor="V"))
        linhas = players_de_perfil(perfil, top_n=2)
        assert len(linhas) == 2
        assert linhas[0].nome == "V"  # esteve nos dois lados de tudo
        assert 0.0 <= linhas[0].agressividade <= 1.0

    def test_le_o_medidor_de_agressao_real_sem_contar_rlp_no_denominador(self):
        """O volume RLP nao pertence a nenhum dos dois lados; somar ele ao
        denominador de uma proporcao ENTRE os dois lados encolheria as duas
        fatias sem que nenhuma tivesse mudado."""
        from fluxopro.analytics.agressao import MedidorAgressao
        from fluxopro.core.barramento import Barramento

        bus = Barramento()
        medidor = MedidorAgressao(bus, "WDOV26")
        bus.publicar(_trade(qty=60, lado="BUY"))
        bus.publicar(_trade(qty=40, lado="SELL"))
        bus.publicar(_trade(qty=25, lado="UNKNOWN"))
        taxa, volume = pressao_da_janela(medidor)
        assert volume == 100
        assert taxa == pytest.approx(0.6)


_n_trade = 0


def _trade(qty: int = 10, comprador: str = "C", vendedor: str = "V", lado: str = "BUY"):
    from fluxopro.core.eventos import AgressorSide, Trade

    global _n_trade
    _n_trade += 1
    return Trade(
        timestamp_ns=T0 + _n_trade,
        symbol="WDOV26",
        price=100,
        qty=qty,
        side_agressor=AgressorSide[lado],
        trade_id=f"t{_n_trade}",
        buyer_broker=comprador,
        seller_broker=vendedor,
    )


# ==========================================================================
# 2. Trabalho — retangulos sujos
# ==========================================================================
class TestTrabalhoDoHUD:
    def test_painel_parado_nao_desenha_nada(self, hud):
        leitura = contexto_do_sinal(sinal(EstagioSinal.NA_REGIAO), saldo_dia=100)
        hud.aplicar(leitura)
        hud._quadro()
        hud.zerar_medicao()
        for _ in range(2_000):
            hud.aplicar(leitura)
            hud._quadro()
        assert hud.quadros_desenhados == 0
        assert hud.quadros_vazios == 2_000

    def test_mudar_a_pressao_da_janela_suja_uma_banda_so(self, hud):
        hud.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.NA_REGIAO), taxa_compra_janela=0.6, volume_janela=500
            )
        )
        hud._quadro()
        hud.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.NA_REGIAO), taxa_compra_janela=0.61, volume_janela=500
            )
        )
        assert hud._sujos == [hud.rect_banda(BANDA_PRESSAO)]

    def test_mudar_o_estagio_suja_o_farol_e_so_as_condicoes_que_mudaram(self, hud):
        hud.aplicar(contexto_do_sinal(sinal(EstagioSinal.NA_REGIAO)))
        hud._quadro()
        hud.aplicar(contexto_do_sinal(sinal(EstagioSinal.PRE_SINAL)))
        # NA_REGIAO -> PRE_SINAL muda so a terceira condicao (NAO -> PARCIAL);
        # as duas primeiras continuam SIM com o mesmo detalhe.
        assert hud._sujos == [
            hud.rect_banda(BANDA_FAROL),
            hud.rect_banda(BANDA_CONDICAO_0 + 2),
        ]

    def test_duas_mudancas_na_mesma_banda_dao_um_retangulo_so(self, hud):
        hud.aplicar(contexto_do_sinal(sinal(EstagioSinal.NENHUM), saldo_dia=10))
        hud._quadro()
        hud.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.NENHUM), saldo_dia=20, volume_nao_atribuido=7
            )
        )
        assert hud._sujos == [hud.rect_banda(BANDA_SALDO_DIA)]

    def test_a_incrementalidade_existe(self, hud):
        """O portao de §6, aplicado a este painel.

        Nao afirma velocidade: afirma que repintar uma banda de 36px e muito
        mais barato que repintar as sete. Um `desenhar` que ignorasse a
        regiao suja deixaria a tela CORRETA e derrubaria esta razao para 1.

        **A margem aqui e menor que a do DOM, e o motivo e estrutural.** O DOM
        marca 13,5x porque tem 40 linhas; este painel tem 7 bandas, entao o
        teto e ~7x antes de qualquer custo fixo. Medido nesta maquina: cheio
        0,74 ms, incremental 0,135 ms, **5,5x** — dos quais ~0,06 ms de
        incremental sao custo fixo de quadro (abrir o `QPainter`, pedir o
        `update`), que nao encolhe. Nao adianta perseguir 13x aqui; o que o
        portao de 5x pega e a perda da incrementalidade, e ela levaria a razao
        para 1, nao para 4.

        Eram 5,7x antes de o medidor do dia perder a barra bidirecional: o
        NUMERADOR encolheu (cinco `drawLine` a menos por quadro cheio), nao o
        denominador. Razao menor por quadro cheio mais barato e melhora, e e
        exatamente o tipo de "regressao" que um portao de razao reporta ao
        contrario — motivo de a margem ser lida junto com os dois tempos.

        **A estatistica e o MINIMO, e nao a mediana**, e isso ja se pagou: com
        mediana, este portao reprovava uma vez em cinco quando outra suite
        rodava em paralelo na mesma maquina. Contencao so ADICIONA tempo,
        entao a menor amostra e a unica que mede o desenho em vez de medir o
        vizinho; a mediana media o ruido para dentro do resultado. Baixar o
        limite para esconder isso teria trocado um portao instavel por um
        portao cego.

        **E o minimo ainda nao bastava**, porque com a maquina ocupada os 60
        quadros cheios podem ser TODOS interrompidos — e ai nem o menor deles
        mede o desenho. `Serie` mede a CPU de cada quadro e o minimo passa a
        ser tirado so dos que rodaram inteiros. Ver `medicao.Serie`."""
        serie_cheio = Serie()
        for i in range(60):
            hud.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NA_REGIAO),
                    taxa_compra_janela=0.40 + i * 0.001,
                    volume_janela=900,
                )
            )
            hud.marcar_tudo_sujo()
            serie_cheio.cronometrar(hud)

        serie_incremental = Serie()
        for i in range(200):
            hud.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NA_REGIAO),
                    taxa_compra_janela=0.30 + i * 0.001,
                    volume_janela=900,
                )
            )
            if not hud.tem_sujeira:
                continue
            serie_incremental.cronometrar(hud)

        # `cauda=False`: a razao le o PISO das duas distribuicoes, nao o pior
        # quadro de nenhuma delas.
        cheio = serie_cheio.limpas("o quadro cheio do HUD", cauda=False)
        incremental = serie_incremental.limpas("o quadro incremental do HUD", cauda=False)
        razao = min(cheio) / max(min(incremental), 1e-9)
        assert razao >= 5.0, (
            f"razao cheio/incremental caiu para {razao:.1f}x "
            f"(cheio {min(cheio):.3f} ms, incremental {min(incremental):.3f} ms)"
        )


class TestTrabalhoDosPlayers:
    def test_mudar_uma_linha_suja_uma_linha(self, players):
        base = tuple(
            LinhaPlayer(f"P{i}", 1_000 - 10 * i, 5 * i) for i in range(TOP_N_PADRAO)
        )
        players.aplicar(base)
        players.marcar_tudo_sujo()
        players._quadro()
        alterada = (base[0], base[1], LinhaPlayer("P2", base[2].volume_total, 90)) + base[3:]
        players.aplicar(alterada)
        assert players._sujos == [players.rect_linha(2)]

    def test_a_incrementalidade_existe(self, players):
        base = [
            LinhaPlayer(f"P{i}", 5_000 - 10 * i, 300 - 5 * i) for i in range(TOP_N_PADRAO)
        ]
        players.aplicar(tuple(base))
        players.marcar_tudo_sujo()
        players._quadro()

        cheio: list[float] = []
        for _ in range(60):
            players.marcar_tudo_sujo()
            cheio.append(_cronometrar(players))

        incremental: list[float] = []
        for i in range(200):
            mudada = list(base)
            mudada[4] = LinhaPlayer("P4", base[4].volume_total, 10 + i)
            players.aplicar(tuple(mudada))
            if not players.tem_sujeira:
                continue
            incremental.append(_cronometrar(players))

        assert incremental
        # MINIMO, pelo mesmo motivo do portao do HUD: contencao de outra
        # suite na mesma maquina so adiciona tempo, entao a menor amostra e a
        # que mede o desenho em vez de medir o vizinho.
        razao = min(cheio) / max(min(incremental), 1e-9)
        assert razao >= 5.0, (
            f"razao dos players caiu para {razao:.1f}x "
            f"(cheio {min(cheio):.3f} ms, incremental {min(incremental):.3f} ms)"
        )


def _cronometrar(painel) -> float:
    inicio = time.perf_counter()
    painel._quadro()
    return (time.perf_counter() - inicio) * 1000.0


# ==========================================================================
# 3. Retencao
# ==========================================================================
class TestRetencao:
    def test_cinco_mil_corretoras_entram_e_top_n_ficam(self, players):
        """Truncar so no desenho deixaria o painel segurando a sessao inteira
        — o defeito de estrutura que cresce, escondido atras de uma tela que
        parece limitada. Este projeto ja o encontrou oito vezes."""
        muitas = tuple(LinhaPlayer(f"P{i}", 10_000 - i, i) for i in range(5_000))
        players.aplicar(muitas)
        assert len(players._linhas) == players.top_n

    def test_o_hud_guarda_uma_leitura_e_nao_um_historico(self, hud):
        for i in range(1_000):
            hud.aplicar(contexto_do_sinal(sinal(EstagioSinal.NA_REGIAO), saldo_dia=i))
        assert hud._leitura.saldo_dia == 999
        assert len(hud._sujos) <= N_BANDAS

    def test_a_sujeira_nunca_passa_do_numero_de_bandas(self, hud):
        hud.aplicar(contexto_do_sinal(sinal(EstagioSinal.NENHUM)))
        hud._quadro()
        hud.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.CONFIRMADO, na_regiao=True, micro_virou=True),
                saldo_dia=5_000,
                taxa_compra_janela=0.2,
                volume_janela=800,
                volume_nao_atribuido=42,
            )
        )
        assert len(hud._sujos) <= N_BANDAS


# ==========================================================================
# 4. As duas paletas e o canal — a direcao sem cor, e a leitura sem texto
# ==========================================================================
def _recorte(painel, rect) -> bytes:
    """Os pixels de um retangulo do backing, byte a byte.

    O `QImage` fica numa variavel COM NOME, e nao numa cadeia de temporarios.
    A versao anterior era `bytes(painel._backing.copy(rect).toImage()
    .constBits())`, e ela lia memoria liberada: `constBits()` devolve uma
    janela para o buffer do `QImage`, o PySide6 nao mantem o dono vivo pela
    janela, e o `QImage` temporario morria antes de `bytes()` terminar de
    copiar. O resultado era um recorte com lixo no meio, de vez em quando —
    medido em 86 de 400 capturas neste mesmo painel, e ZERO nas mesmas 400
    guardando a referencia. Era exatamente disto que os dois testes de
    geometria do canal reprovavam com a maquina ocupada: nao de escala
    reintroduzida, mas do proprio instrumento.

    Tambem descarta o enchimento de fim de linha (`bytesPerLine` e alinhado e
    os bytes de sobra nao sao inicializados) e fixa o formato, para que a
    comparacao seja de pixel e so de pixel."""
    imagem = painel._backing.copy(rect).toImage().convertToFormat(
        QImage.Format.Format_RGB32
    )
    bits = imagem.constBits()
    passo = imagem.bytesPerLine()
    util = imagem.width() * 4
    return b"".join(
        bytes(bits[y * passo : y * passo + util]) for y in range(imagem.height())
    )


_DIRECIONAIS = None


def _cores_direcionais():
    global _DIRECIONAIS
    if _DIRECIONAIS is None:
        _DIRECIONAIS = (
            tokens.BUY.rgb(),
            tokens.SELL.rgb(),
            tokens.TEXT_PRIMARY.rgb(),
        )
    return _DIRECIONAIS


def _contar_direcionais(painel, rect) -> int:
    """Conta pixels do eixo direcional numa faixa — a medicao do critico.

    Le o BACKING STORE, e nao um espiao de chamadas: `fillRect` conta, e a
    geometria vira assercao de pixel. Um duble de `QPainter` diria que o
    codigo chamou `fillRect`, nunca que o retangulo tinha a largura certa."""
    imagem = painel._backing.toImage()
    y = rect.center().y()
    return sum(
        1
        for x in range(rect.left(), rect.right() + 1)
        if imagem.pixelColor(x, y).rgb() in _cores_direcionais()
    )


def _x_costura_banda(painel, indice_banda: int) -> int:
    """Posicao da costura numa banda do `PainelHUD`, em pixels absolutos.

    Mesma tecnica de `_medir_costura`: localiza a faixa de `BG_BASE` dentro
    da trilha, que e o que marca a divisao nas duas paletas."""
    trilha = painel.rect_barra(indice_banda)
    imagem = painel._backing.toImage()
    y = trilha.center().y()
    fundo = tokens.BG_BASE.rgb()
    xs = [
        x
        for x in range(trilha.left(), trilha.right() + 1)
        if imagem.pixelColor(x, y).rgb() == fundo
    ]
    return (xs[0] + xs[-1]) // 2 if xs else -1


def _medir_costura(painel, indice: int) -> int:
    """Desvio da costura em relacao a costura de 50%, em pixels, com sinal.

    Duas escolhas, as duas pagas com um defeito:

    1. Localiza a costura pelo que ela E — a faixa de `BG_BASE` dentro da
       barra — e nao pela troca de cor, porque no modo sem cor os dois
       segmentos tem a mesma cor e a costura e a unica coisa que sobra.
    2. Mede contra `painel.x_costura(TAXA_NEUTRA)`, a MESMA funcao que o
       desenho usa, e nao contra `rect_barra().center().x()`. O centro do
       retangulo e `left + (w-1)//2`; o corte e `left + round(taxa*w)`. Um
       pixel de diferenca, e o guarda anti-piso passava a aceitar justamente
       o piso de 3px que ele existe para reprovar."""
    barra = painel.rect_barra(indice)
    imagem = painel._backing.toImage()
    y = barra.center().y()
    fundo = tokens.BG_BASE.rgb()
    xs = [
        x
        for x in range(barra.left(), barra.right() + 1)
        if imagem.pixelColor(x, y).rgb() == fundo
    ]
    if not xs:
        return 0
    return (xs[0] + xs[-1]) // 2 - painel.x_costura(TAXA_NEUTRA)


def _ranking_do_retrato() -> tuple[LinhaPlayer, ...]:
    """A distribuicao real de `design/retrato_hud.png`: volume 54,0k..2,9k
    (19x) e saldo +8,2k..-37 (**222x**). E contra estes numeros que a versao
    com piso desenhava vinte barras de exatamente 3px."""
    dados = (
        ("SIM 01", 54_000, 8_200), ("SIM 02", 37_700, -5_500),
        ("SIM 03", 20_900, -2_600), ("SIM 04", 15_900, 414),
        ("SIM 05", 12_700, -403), ("SIM 06", 11_100, -80),
        ("SIM 07", 9_000, 25), ("SIM 08", 8_000, -420),
        ("SIM 09", 6_500, -303), ("SIM 10", 5_900, -68),
        ("SIM 11", 5_800, -251), ("SIM 12", 5_400, 195),
        ("SIM 13", 4_600, 110), ("SIM 15", 4_500, -37),
        ("SIM 16", 4_300, 35), ("SIM 14", 4_300, -384),
        ("SIM 17", 4_100, 416), ("SIM 18", 3_200, 447),
        ("SIM 20", 3_100, 43), ("SIM 19", 2_900, 145),
    )
    return tuple(LinhaPlayer(n, v, s) for n, v, s in dados)


def _render_recorte(painel, aplicar, rect) -> bytes:
    aplicar(painel)
    painel.marcar_tudo_sujo()
    painel._quadro()
    return _recorte(painel, rect)


class TestSemCor:
    @pytest.mark.parametrize("paleta", [tokens.PALETA_COR, tokens.PALETA_SEM_COR])
    def test_desenha_nas_duas_paletas(self, qapp, paleta):
        hud = _pronto(PainelHUD(paleta=paleta), 320, PainelHUD().altura_natural)
        hud.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.CONFIRMADO, na_regiao=True, micro_virou=True),
                saldo_dia=-12_000,
                taxa_compra_janela=0.7,
                volume_janela=3_400,
                volume_nao_atribuido=900,
            )
        )
        hud.marcar_tudo_sujo()
        hud._quadro()
        assert hud.quadros_desenhados >= 1

    def test_a_barra_do_saldo_do_dia_carrega_a_direcao_SEM_cor(self, qapp):
        """A prova central deste painel, e ela recorta SO a barra.

        Com `PALETA_SEM_COR` as duas cores do eixo direcional sao a MESMA
        cor, e o recorte exclui a linha de rotulo — onde mora o `+`/`−`, que
        e outro portador. Se estes dois quadros ficarem iguais, a direcao
        esta vivendo so no matiz e no texto, que e a falha do Profit Pro."""
        painel = _pronto(
            PainelHUD(paleta=tokens.PALETA_SEM_COR), 320, PainelHUD().altura_natural
        )
        faixa = painel.rect_barra(BANDA_SALDO_DIA)

        def dia(comprado: int, vendido: int):
            return lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    saldo_dia=comprado - vendido,
                    volume_comprador_dia=comprado,
                    volume_vendedor_dia=vendido,
                )
            )

        # Mesma magnitude de saldo, lados opostos. Desde que o medidor perdeu
        # a catraca, quem carrega a direcao e a POSICAO DA COSTURA, e este
        # teste passou a valer tambem como prova de que a barra existe: com
        # `volume_dia` zerado ela fica vazia nos dois casos e o teste reprova,
        # que foi exatamente o que aconteceu quando a forma mudou.
        comprador = _render_recorte(painel, dia(71_155, 28_845), faixa)
        vendedor = _render_recorte(painel, dia(28_845, 71_155), faixa)
        assert comprador != vendedor, (
            "saldo comprador e vendedor de mesma magnitude renderizaram a MESMA "
            "barra sem cor — a direcao esta vivendo so no matiz"
        )

    def test_a_barra_de_pressao_carrega_a_direcao_SEM_cor(self, qapp):
        """Idem para a barra particionada: e a costura que muda de lado."""
        painel = _pronto(
            PainelHUD(paleta=tokens.PALETA_SEM_COR), 320, PainelHUD().altura_natural
        )
        faixa = painel.rect_barra(BANDA_PRESSAO)
        compra = _render_recorte(
            painel,
            lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    taxa_compra_janela=0.63,
                    volume_janela=1_000,
                )
            ),
            faixa,
        )
        venda = _render_recorte(
            painel,
            lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    taxa_compra_janela=0.37,
                    volume_janela=1_000,
                )
            ),
            faixa,
        )
        assert compra != venda

    def test_o_ranking_distingue_comprador_de_vendedor_SEM_cor(self, qapp):
        """O teste que antes passava pelo motivo errado.

        A versao anterior comparava os pixels do painel INTEIRO, entao
        `▲ +600` contra `▼ −600` no texto ja bastava para passar — ele nao
        provava nada sobre a barra, so parecia provar. Agora o recorte e a
        **barra de saldo** e nada mais, pela geometria que o proprio painel
        usa para desenhar (`rect_barra_saldo`), nao por uma conta paralela
        que pode divergir."""
        painel = _pronto(
            PainelPlayers(paleta=tokens.PALETA_SEM_COR), 520, 24 + TOP_N_PADRAO * 18
        )
        faixa = painel.rect_barra(0)
        comprador = _render_recorte(
            painel, lambda p: p.aplicar((LinhaPlayer("ACME", 1_000, 600),)), faixa
        )
        vendedor = _render_recorte(
            painel, lambda p: p.aplicar((LinhaPlayer("ACME", 1_000, -600),)), faixa
        )
        assert comprador != vendedor

    def test_a_ultima_linha_do_ranking_e_tao_legivel_quanto_a_primeira(self, qapp):
        """A correcao da cauda, como propriedade.

        O mesmo defeito apareceu DUAS vezes nesta peca e este teste fecha as
        duas: (a) a direcao vivia no preenchimento de uma trilha cujo
        comprimento era o volume, e na vigesima linha sobravam ~10px; (b)
        depois, numa barra de saldo com escala compartilhada, onde o topo com
        `+5.000` punha a escala em 5.000 e a cauda com `+400` virava um pixel.

        Aqui o topo tem 500x o volume da cauda E 12x o saldo dela, que e o
        cenario que quebrava as duas versoes."""
        painel = _pronto(
            PainelPlayers(paleta=tokens.PALETA_SEM_COR), 520, 24 + TOP_N_PADRAO * 18
        )

        def com_saldo(ultimo: int) -> tuple[LinhaPlayer, ...]:
            linhas = [LinhaPlayer("TOPO", 500_000, 5_000)]
            linhas += [LinhaPlayer(f"P{i}", 2_000 - i, 0) for i in range(1, 19)]
            linhas.append(LinhaPlayer("CAUDA", 1_000, ultimo))
            return tuple(linhas)

        assert painel.rect_barra(19).width() == painel.rect_barra(0).width()
        faixa = painel.rect_barra(19)
        # Desequilibrio de 2,6% — o que um player equilibrado de verdade
        # mostra. A cauda tem 1/500 do volume do topo, que e o caso em que a
        # versao de asas arredondava a barra inteira para zero.
        comprador = _render_recorte(painel, lambda p: p.aplicar(com_saldo(26)), faixa)
        vendedor = _render_recorte(painel, lambda p: p.aplicar(com_saldo(-26)), faixa)
        assert comprador != vendedor

    def test_a_paleta_sem_cor_realmente_colapsa_o_eixo(self):
        """Guarda dos testes acima: se as duas cores fossem diferentes, os
        quadros diferirem nao provaria nada."""
        assert tokens.PALETA_SEM_COR.direcional(1) == tokens.PALETA_SEM_COR.direcional(-1)


class TestCanal:
    """As leituras que importam tem de estar em geometria, nao em corpo 10.

    O canal desta peca e captura + transmissao (`scripts/transmissao.py`):
    reescala e quantizacao com perdas. Texto de 10px e a primeira coisa a
    morrer. Estes testes nao simulam o codec — afirmam as PROPRIEDADES que
    tornam a peca imune ao que o codec faz.
    """

    def test_a_barra_de_pressao_nao_tem_escala(self, qapp):
        """A correcao da maior lacuna da rodada 1, como propriedade.

        Antes eram dois medidores bidirecionais com escalas independentes
        (2.500 e 1.200 lotes) e a escala escrita em corpo 10 ao lado. Depois
        do canal o rotulo sumia e sobravam duas barras de comprimento quase
        igual sobre escalas que diferiam 2,1x — o leitor concluia que as duas
        pressoes eram iguais.

        A correcao nao foi engordar o rotulo: foi tirar do segundo medidor a
        escala que ele nao precisava ter. Aqui isso e afirmado do jeito mais
        direto — a MESMA proporcao produz os MESMOS pixels de barra,
        qualquer que seja o volume por tras dela. Sem escala nao ha nada que
        o canal possa apagar para produzir uma comparacao errada."""
        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        faixa = painel.rect_barra(BANDA_PRESSAO)
        pequeno = _render_recorte(
            painel,
            lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    taxa_compra_janela=0.63,
                    volume_janela=120,
                )
            ),
            faixa,
        )
        enorme = _render_recorte(
            painel,
            lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    taxa_compra_janela=0.63,
                    volume_janela=980_000,
                )
            ),
            faixa,
        )
        assert pequeno == enorme

    def test_costuras_distintas_para_players_distintos(self, qapp):
        """**O teste que faltava, e que teria reprovado a rodada 2.**

        A versao com piso de 3px passava em tudo que existia: as barras
        EXISTIAM, tinham o lado certo e sobreviviam sem cor. So que dezenove
        das vinte tinham exatamente a mesma largura, contra 222x de intervalo
        de saldo. "Existe" nao e "e proporcional", e nenhum teste afirmava a
        segunda coisa — por isso o defeito atravessou uma rodada inteira.

        A medicao e a mesma que o critico fez no PNG: ler os pixels da barra
        e localizar onde ela se parte. A distribuicao e a do proprio retrato,
        e o resultado medido hoje e
        `[16, -16, -13, 3, -3, -1, 0, -6, -5, -1, -5, 4, 3, -1, 1, -10, 11,
        15, 2, 5]` px de desvio — quinze valores distintos onde a rodada 2
        tinha um."""
        painel = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        ranking = _ranking_do_retrato()
        painel.aplicar(ranking)
        painel.marcar_tudo_sujo()
        painel._quadro()
        desvios = [_medir_costura(painel, i) for i in range(len(ranking))]

        # 1. Nao colapsam. A rodada 2 media exatamente {3} nas vinte linhas.
        assert len(set(desvios)) >= 10, f"costuras colapsadas em {sorted(set(desvios))}"
        # 2. O lado da costura concorda com o sinal do saldo, linha a linha.
        for linha, desvio in zip(ranking, desvios):
            if abs(linha.taxa_compra - 0.5) > 0.005:
                assert (desvio > 0) == (linha.saldo_liquido > 0), linha.nome
        # 3. **A assercao principal: o desvio E a proporcao, linha a linha.**
        # A expectativa vem dos DADOS (`(taxa - 0,5) x largura`), nao da
        # aritmetica do produto — senao um piso escondido dentro de
        # `x_costura` passaria. Qualquer piso, raiz ou log quebra isto na
        # primeira linha quase equilibrada: SIM 07 tem vies de +0,3%, espera
        # 0px, e um piso de 3px entrega 3.
        largura = painel.rect_barra(0).width()
        for linha, medido in zip(ranking, desvios):
            esperado = (linha.taxa_compra - TAXA_NEUTRA) * largura
            assert abs(medido - esperado) <= 1, (linha.nome, medido, esperado)

        # 4. E a propriedade anti-piso tambem na forma agregada, que e como o
        # critico a mediu: o maior desvio e muitas vezes o menor nao nulo.
        absolutos = sorted(abs(d) for d in desvios if d)
        assert absolutos[-1] >= 10, absolutos
        assert absolutos[-1] >= 8 * absolutos[0], absolutos

    def test_a_costura_e_proporcional_a_parcela(self, qapp):
        """Proporcionalidade de verdade.

        Um piso, uma raiz quadrada ou um log passariam num teste de
        monotonicidade. So este pega: dobrar o desequilibrio dobra o desvio."""
        painel = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        painel.aplicar(
            (
                LinhaPlayer("A", 10_000, 4_000),  # 70/30 -> +20% do centro
                LinhaPlayer("B", 10_000, 2_000),  # 60/40 -> +10%
                LinhaPlayer("C", 10_000, 1_000),  # 55/45 -> +5%
            )
        )
        painel.marcar_tudo_sujo()
        painel._quadro()
        desvios = [_medir_costura(painel, i) for i in range(3)]
        assert desvios[1] == pytest.approx(desvios[0] / 2, abs=1)
        assert desvios[2] == pytest.approx(desvios[0] / 4, abs=1)

    def test_o_volume_nao_toca_mais_na_geometria(self, qapp):
        """A correcao da rodada 3, afirmada onde ela mora.

        Volume de corretora varre ~500x (`09_tape_reading_b.png`: 10,23% a
        0,02%). Enquanto ele fosse comprimento, a cauda arredondava para zero
        e a linha sumia. Agora ele e numero, e a prova e esta: **as mesmas
        proporcoes com volumes 500x diferentes desenham a MESMA barra.**"""
        painel = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        faixa = painel.rect_barra(0)
        grande = _render_recorte(
            painel, lambda p: p.aplicar((LinhaPlayer("GRANDE", 500_000, 100_000),)), faixa
        )
        minusculo = _render_recorte(
            painel, lambda p: p.aplicar((LinhaPlayer("MINI", 1_000, 200),)), faixa
        )
        assert grande == minusculo

    def test_o_painel_nao_tem_escala_nenhuma(self, qapp):
        """A ausencia que e o resultado.

        Tres versoes deste painel tiveram escala, e as tres tiveram o mesmo
        defeito. A unica grandeza que sobrou na geometria e limitada por
        natureza, entao nao ha catraca, nao ha degrau e nao ha rotulo de
        escala para o canal apagar."""
        painel = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        assert not [a for a in vars(painel) if "escala" in a]
        # E a largura da barra e a mesma na primeira e na vigesima linha.
        assert painel.rect_barra(0).width() == painel.rect_barra(19).width()

    def test_saldo_marginal_deixa_a_costura_na_espinha(self, qapp):
        """O caso degenerado sobre o qual a versao com piso mentia.

        `+25` sobre 9.000 negociados e um player equilibrado, e a barra tem
        de dizer isso. Com piso, ele desenhava o MESMO traco de 3px que um
        saldo de `+8,2k` — dois players opostos, um pixel identico."""
        painel = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        painel.aplicar(
            (LinhaPlayer("GRANDE", 9_000, 8_200), LinhaPlayer("NEUTRO", 9_000, 25))
        )
        painel.marcar_tudo_sujo()
        painel._quadro()
        assert abs(_medir_costura(painel, 1)) <= 1, "player neutro saiu torto"
        assert _medir_costura(painel, 0) >= 40, "player comprador saiu centrado"

    def test_o_mesmo_saldo_desenha_a_mesma_barra_depois_de_um_pico(self, qapp):
        """**O par TEMPORAL — o guarda que nao existia, e o defeito era este.**

        Todo teste desta peca comparava dois quadros lado a lado. Este compara
        o quadro de agora com a lembranca de um quadro anterior, que e como o
        operador realmente le uma tela ao vivo, e e a unica comparacao que
        pegava a catraca. Medido no codigo antigo:

            saldo +2.200, escala  2.500  ->  133 px
            um pico de 9.000 leva a escala a 10.000, e ela FICA
            saldo +2.200, escala 10.000  ->   33 px   (4,0x menor)

        Nenhum teste reprovava isso, porque nenhum renderizava a MESMA leitura
        duas vezes com um pico no meio."""
        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        faixa = painel.rect_barra(BANDA_SALDO_DIA)

        def dia(comprado: int, vendido: int):
            return lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    saldo_dia=comprado - vendido,
                    volume_comprador_dia=comprado,
                    volume_vendedor_dia=vendido,
                )
            )

        antes = _render_recorte(painel, dia(6_100, 3_900), faixa)
        _render_recorte(painel, dia(54_500, 45_500), faixa)  # o pico
        depois = _render_recorte(painel, dia(6_100, 3_900), faixa)
        assert antes == depois, (
            "a mesma leitura do dia desenhou barras diferentes depois de um "
            "pico — ha um eixo movel de volta no medidor"
        )

    def test_nenhuma_barra_do_produto_encolhe_quando_a_magnitude_cresce(self, qapp):
        """A propriedade que sobra depois de removida a ultima escala.

        Vale para as TRES barras do produto de uma vez: mesma proporcao com
        magnitude 10x maior tem de desenhar exatamente os mesmos pixels. Se
        alguem reintroduzir escala em qualquer uma delas, esta reprova."""
        hud = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)

        def leitura(fator: int):
            return lambda p: p.aplicar(
                contexto_do_sinal(
                    sinal(EstagioSinal.NENHUM),
                    saldo_dia=2_000 * fator,
                    volume_comprador_dia=6_000 * fator,
                    volume_vendedor_dia=4_000 * fator,
                    taxa_compra_janela=0.6,
                    volume_janela=1_000 * fator,
                )
            )

        for banda in (BANDA_SALDO_DIA, BANDA_PRESSAO):
            faixa = hud.rect_barra(banda)
            assert _render_recorte(hud, leitura(1), faixa) == _render_recorte(
                hud, leitura(10), faixa
            ), f"a barra da banda {banda} mudou de tamanho com a magnitude"

        players = _pronto(PainelPlayers(), 520, 24 + TOP_N_PADRAO * 18)
        faixa = players.rect_barra(0)
        pequeno = _render_recorte(
            players, lambda p: p.aplicar((LinhaPlayer("P", 1_000, 200),)), faixa
        )
        grande = _render_recorte(
            players, lambda p: p.aplicar((LinhaPlayer("G", 500_000, 100_000),)), faixa
        )
        assert pequeno == grande, "a barra do ranking mudou de tamanho com o volume"

    def test_as_duas_barras_do_hud_estao_no_mesmo_eixo(self, qapp):
        """O inverso do defeito da rodada 1, afirmado de proposito.

        A peca comecou com duas barras parecidas sobre escalas que diferiam
        2,1x — parecidas e INCOMPARAVEIS, que e a mentira grafica original.
        Hoje elas continuam parecidas, e agora sao comparaveis: mesma
        proporcao desenha a mesma costura nas duas, entao ler uma contra a
        outra ("no pregao 53%, nos ultimos 5 s 71%") da a resposta certa.

        Um critico pode achar que duas barras iguais sao um cheiro. Sao — mas
        so quando escondem eixos diferentes. Este teste e a prova de que nao
        escondem, e por isso ele afirma a IGUALDADE, e nao a diferenca; a
        versao anterior afirmava que as duas eram diferentes e passava por
        acidente, porque a banda do dia estava vazia por falta de dado."""
        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        painel.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.NENHUM),
                saldo_dia=2_000,
                volume_comprador_dia=6_000,
                volume_vendedor_dia=4_000,
                taxa_compra_janela=0.6,
                volume_janela=1_000,
            )
        )
        painel.marcar_tudo_sujo()
        painel._quadro()
        # Mesma taxa (0,6) nas duas bandas -> mesma costura, ao pixel.
        assert _x_costura_banda(painel, BANDA_SALDO_DIA) == _x_costura_banda(
            painel, BANDA_PRESSAO
        )

        painel.aplicar(
            contexto_do_sinal(
                sinal(EstagioSinal.NENHUM),
                saldo_dia=2_000,
                volume_comprador_dia=6_000,
                volume_vendedor_dia=4_000,
                taxa_compra_janela=0.3,
                volume_janela=1_000,
            )
        )
        painel.marcar_tudo_sujo()
        painel._quadro()
        # E taxas diferentes tem de dar costuras diferentes, senao o teste
        # acima estaria comparando duas bandas que nem olham o proprio dado.
        assert _x_costura_banda(painel, BANDA_SALDO_DIA) != _x_costura_banda(
            painel, BANDA_PRESSAO
        )

    def test_dois_estagios_do_farol_diferem_nos_pixels_do_farol(self, qapp):
        """O achado 2 do critico, fechado.

        Com todos os segmentos acesos na mesma cor, `CONFIRMADO` virava um
        bloco roxo unico e `PRE_SINAL` um bloco ambar unico; distinguir os
        dois dependia de contar cinco blocos contra quatro por cima de vaos
        de 4px que a reescala do canal come. O recorte aqui e a BANDA DO
        FAROL — o rotulo `CONFIRMADO — ENTRADA` esta dentro dela, entao o
        teste sozinho ainda passaria pelo texto; por isso ele vem em par com
        `test_os_segmentos_acesos_mudam_de_cor_com_o_estagio`, que olha o
        pixel do segmento e nada mais."""
        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        faixa = painel.rect_banda(BANDA_FAROL)
        pre = _render_recorte(
            painel, lambda p: p.aplicar(contexto_do_sinal(sinal(EstagioSinal.PRE_SINAL))), faixa
        )
        conf = _render_recorte(
            painel, lambda p: p.aplicar(contexto_do_sinal(sinal(EstagioSinal.CONFIRMADO))), faixa
        )
        assert pre != conf

    @pytest.mark.parametrize(
        "estagio", [e for e in ORDEM_ESTAGIOS if e is not EstagioSinal.NENHUM]
    )
    def test_os_segmentos_acesos_mudam_de_cor_com_o_estagio(self, qapp, estagio):
        """Cada segmento na cor do PROPRIO estagio, nao todos na do corrente.

        Consequencia verificavel: o pixel do SEGUNDO segmento (o de
        `DIRECAO_CONFIRMADA`) tem a mesma cor em todo estagio que ja passou
        por ele, e o pixel do segmento CORRENTE tem a cor daquele estagio.
        Com uma cor unica para todos, o segundo segmento mudaria de cor toda
        vez que o farol avancasse — e ai a cor nao diria estagio nenhum."""
        from fluxopro.ui.paineis.hud import cor_do_estagio

        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        painel.aplicar(contexto_do_sinal(sinal(estagio)))
        painel.marcar_tudo_sujo()
        painel._quadro()
        imagem = painel._backing.toImage()
        banda = painel.rect_banda(BANDA_FAROL)
        indice = ORDEM_ESTAGIOS.index(estagio)
        for i in (1, indice):
            seg = painel.rect_segmento(banda, i)
            pixel = imagem.pixelColor(seg.center().x(), seg.center().y())
            esperada = cor_do_estagio(ORDEM_ESTAGIOS[i])
            assert pixel.rgb() == esperada.rgb(), (
                f"segmento {i} em {estagio.value}: {pixel.name()} "
                f"!= {esperada.name()}"
            )

    def test_o_segmento_corrente_e_mais_alto_que_os_outros(self, qapp):
        """Portador GEOMETRICO do "voce esta aqui".

        Cor atravessa o canal bem, mas cor sozinha nao diz qual segmento e o
        ponteiro quando varios estao acesos. Quatro pixels de diferenca de
        altura sobrevivem a reescala de 0,72; um rotulo de 9px, nao."""
        painel = _pronto(PainelHUD(), 320, PainelHUD().altura_natural)
        painel.aplicar(contexto_do_sinal(sinal(EstagioSinal.NA_REGIAO)))
        banda = painel.rect_banda(BANDA_FAROL)
        corrente = painel.rect_segmento(banda, ORDEM_ESTAGIOS.index(EstagioSinal.NA_REGIAO))
        outro = painel.rect_segmento(banda, 0)
        assert corrente.height() > outro.height() + 2


# ==========================================================================
# 5. Layout que degrada — F8
# ==========================================================================
class TestColunaQueSai:
    def test_coluna_de_agressividade_some_em_painel_estreito(self, qapp):
        """F8: rotulo de coluna nunca trunca. Se nao cabe, a coluna sai —
        nunca `Agressiv…`. E entre espremer a barra e perder uma coluna
        secundaria, perde-se a coluna."""
        estreito = _pronto(PainelPlayers(), 420, 200)
        largo = _pronto(PainelPlayers(), 560, 200)
        assert not estreito.mostra_agressividade
        assert largo.mostra_agressividade

    def test_a_barra_nunca_fica_negativa_no_painel_minimo(self, qapp):
        estreito = _pronto(PainelPlayers(), 220, 200)
        assert estreito.rect_barra(0).width() >= 8

    def test_painel_sem_players_desenha_a_grade_e_nao_um_retangulo_branco(self, players):
        players.aplicar(())
        players.marcar_tudo_sujo()
        players._quadro()
        assert players.quadros_desenhados >= 1

    def test_a_altura_e_fixa_e_igual_a_soma_das_bandas(self, hud):
        """A faixa nao estica: as bandas sao a altura, e a altura sao as
        bandas. Se as duas contas discordarem, uma banda desenha fora do
        backing e o pixel de fora fica com o valor ANTIGO."""
        soma = sum(hud.rect_banda(i).height() for i in range(N_BANDAS))
        assert soma == hud.altura_natural == hud.height()
