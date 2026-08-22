"""Portao de desempenho da interface — `design/direcao_visual.md` §6, fase 0.5.

O documento pede um teste de CI que **falhe acima de 4 ms p95**, com a
justificativa certa: "o numero ja e conhecido, entao o regresso vira erro e
nao descoberta tardia".

Aqui ele vem em duas formas, porque uma sozinha nao basta:

* **Limite absoluto (4 ms p95).** Pega maquina lenta e regressao grosseira.
  Sozinho, e fragil: numa maquina rapida ele passaria mesmo se alguem
  removesse a repintura incremental inteira.

* **RAZAO quadro-cheio / quadro-incremental.** Essa e a de verdade. Ela nao
  mede velocidade, mede se a fundacao ainda esta funcionando — e sobrevive a
  trocar de maquina, de sistema e de versao do Qt, porque as duas medidas
  sofrem juntas. Se alguem escrever um `desenhar` que ignora a regiao suja e
  repinta tudo, a razao vai a 1 e o teste reprova em qualquer hardware.

Numeros medidos nesta maquina quando o portao foi escrito (Windows 11,
Python 3.14, PySide6 6.11.2, plataforma offscreen):

| painel | quadro cheio p50 | incremental p50 | razao |
|---|---|---|---|
| DOM 40 niveis @420x760 | 4,413 ms | 0,327 ms | **13,5x** |
| Tape @380x760          | 5,407 ms | 0,163 ms | **33,3x** |

E o quadro ocioso custa **1,00 us** — o `if` que retorna sem abrir
`QPainter`. Os limiares abaixo ficam BEM abaixo do medido de proposito: um
portao que passa raspando vira ruido de CI e ensina todo mundo a ignora-lo.
"""

from __future__ import annotations

import statistics
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from fluxopro.core.eventos import WDO_GRID, BookLevel, BookSnapshot  # noqa: E402
from fluxopro.motor.sinais import EstagioSinal, FaixaConviccao  # noqa: E402
from fluxopro.ui.paineis.dom import PainelDOM  # noqa: E402
from fluxopro.ui.paineis.matriz import LeituraMotor, PainelMatriz  # noqa: E402
from fluxopro.ui.paineis.tape import PainelTape  # noqa: E402
from fluxopro.ui.ponte import ItemTape  # noqa: E402

T0 = 1_700_000_000_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)

LIMITE_P95_MS = 4.0
"""O numero de §6. Medido hoje: 0,391 ms no DOM — 10x de folga."""

RAZAO_MINIMA = 5.0
"""Medido: 13,5x no DOM, 33,3x no tape. Reprovar abaixo de 5x deixa margem
para uma maquina com cache pequeno ou um Qt mais lento sem deixar passar a
perda da incrementalidade, que levaria a razao para perto de 1."""

N_AMOSTRAS = 200


def _livro(offset: int = 0, n: int = 20) -> BookSnapshot:
    return BookSnapshot(
        T0 + offset,
        "WDOV26",
        tuple(BookLevel(BASE - k - 1, 100 + 13 * k, 1 + k % 4) for k in range(n)),
        tuple(BookLevel(BASE + k + 1, 90 + 11 * k, 1 + k % 3) for k in range(n)),
    )


def _p95(amostras: list[float]) -> float:
    ordenadas = sorted(amostras)
    return ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * 0.95))]


def _cronometrar(painel) -> float:
    inicio = time.perf_counter()
    painel._quadro()
    return (time.perf_counter() - inicio) * 1000.0


@pytest.fixture
def dom(qapp):
    painel = PainelDOM(WDO_GRID)
    painel.resize(420, 760)
    painel.show()
    painel.ao_redimensionar(420, 760)
    painel._recriar_backing()
    painel.aplicar(_livro(), BASE)
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def tape(qapp):
    painel = PainelTape(WDO_GRID)
    painel.resize(380, 760)
    painel.show()
    painel.ao_redimensionar(380, 760)
    painel._recriar_backing()
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


def _medir_dom(dom) -> tuple[list[float], list[float]]:
    cheio: list[float] = []
    for _ in range(N_AMOSTRAS // 2):
        dom.marcar_tudo_sujo()
        cheio.append(_cronometrar(dom))

    incremental: list[float] = []
    base = _livro()
    bids = list(base.bids)
    for i in range(N_AMOSTRAS):
        # UM nivel muda, e abaixo do degrau de escala corrente para nao
        # disparar reescala (que e um quadro cheio legitimo).
        bids[3] = BookLevel(bids[3].price, 100 + (i % 97), 2)
        dom.aplicar(BookSnapshot(T0 + i, "WDOV26", tuple(bids), base.asks), BASE)
        if not dom.tem_sujeira:
            continue
        incremental.append(_cronometrar(dom))
    return cheio, incremental


class TestPortaoDoDOM:
    def test_p95_incremental_abaixo_do_limite(self, dom):
        _, incremental = _medir_dom(dom)
        assert incremental, "nenhum quadro incremental foi medido"
        p95 = _p95(incremental)
        assert p95 < LIMITE_P95_MS, f"quadro incremental do DOM a {p95:.3f} ms p95"

    def test_a_incrementalidade_ainda_existe(self, dom):
        """O teste que sobrevive a troca de maquina.

        Nao afirma velocidade nenhuma: afirma que redesenhar UMA linha e
        muito mais barato que redesenhar quarenta. Se alguem escrever um
        `desenhar` que ignora a regiao suja, a tela continua CORRETA, o
        limite absoluto pode continuar passando numa maquina rapida, e este
        aqui reprova.
        """
        cheio, incremental = _medir_dom(dom)
        razao = statistics.median(cheio) / statistics.median(incremental)
        assert razao >= RAZAO_MINIMA, (
            f"razao cheio/incremental caiu para {razao:.1f}x "
            f"(cheio {statistics.median(cheio):.3f} ms, "
            f"incremental {statistics.median(incremental):.3f} ms)"
        )

    def test_quadro_cheio_cabe_no_orcamento_de_60hz(self, dom):
        """Quadro cheio acontece em redimensionamento e reescala.

        Nao precisa ser barato como o incremental, mas nao pode estourar os
        16 ms — senao arrastar a divisoria da janela engasga a tela.
        """
        cheio, _ = _medir_dom(dom)
        assert _p95(cheio) < 16.0


class TestPortaoDoTape:
    def test_rolagem_abaixo_do_limite_e_muito_mais_barata_que_o_cheio(self, tape):
        cheio: list[float] = []
        for _ in range(N_AMOSTRAS // 2):
            tape.aplicar((ItemTape(T0, BASE, 10, 1),))
            tape.marcar_tudo_sujo()
            cheio.append(_cronometrar(tape))

        rolagem: list[float] = []
        for i in range(N_AMOSTRAS):
            tape.aplicar((ItemTape(T0 + i, BASE + (i % 5), 10 + i % 50, 1 if i % 2 else -1),))
            if not tape.tem_sujeira:
                continue
            rolagem.append(_cronometrar(tape))

        p95 = _p95(rolagem)
        assert p95 < LIMITE_P95_MS, f"rolagem do tape a {p95:.3f} ms p95"
        razao = statistics.median(cheio) / statistics.median(rolagem)
        assert razao >= RAZAO_MINIMA, f"razao do tape caiu para {razao:.1f}x"


class TestSobCarga:
    """O teste que os benchmarks isolados nao fazem — e que achou o defeito.

    Todos os numeros acima sao medidos com o painel sozinho no processo.
    Com a fonte rodando na thread dela, o quadro do DOM saiu de
    sub-milissegundo para **12 ms de parede**, e a tela caiu para 15 fps.
    Nao era trabalho: era espera de GIL contra um produtor que nunca faz
    I/O. A licao do proprio `PROGRESSO.md` — "medir o CONJUNTO, nao cada fix
    isolado" — vale para a interface igual.

    Este teste nao afirma fluidez, que depende da maquina. Afirma que a
    interface **nao morre de fome**: se alguem devolver o intervalo de troca
    ao padrao, ou puser trabalho pesado no caminho da fonte, os quadros
    despencam e isto reprova.
    """

    def test_o_painel_nao_e_starvado_pela_thread_da_fonte(self, qapp):
        import sys
        import threading
        import time as _time

        from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados
        from fluxopro.app.montagem import montar
        from fluxopro.ui.janela import JanelaFluxo
        from fluxopro.ui.ponte import PonteFluxo
        from scripts.painel import GIL_SWITCH_PADRAO

        anterior = sys.getswitchinterval()
        sys.setswitchinterval(GIL_SWITCH_PADRAO)
        config = ConfigOperacao(
            symbol="WDOV26",
            fonte=FonteDados.SIMULADOR,
            simulador=ConfigSimulador(seed=7, n_eventos=10**9, taxa_eventos_s=500.0),
        )
        ref: dict = {}
        montagem = montar(
            config,
            ao_sinal=lambda e: ref["p"].registrar_evento(e),
            ao_deteccao=lambda e: ref["p"].registrar_evento(e),
        )
        ponte = PonteFluxo(montagem.barramento)
        ref["p"] = ponte
        janela = JanelaFluxo(ponte, config.symbol, config.price_grid())
        janela.resize(1280, 800)
        janela.show()

        thread = threading.Thread(target=montagem.fonte.iniciar, daemon=True)
        thread.start()
        try:
            fim = _time.perf_counter() + 2.0
            while _time.perf_counter() < fim:
                qapp.processEvents()
            segundos = 2.0
            quadros = janela.dom.quadros_desenhados
            fps = quadros / segundos
        finally:
            montagem.fonte.parar()
            thread.join(timeout=5.0)
            janela.close()
            montagem.sessao.finalizar()
            sys.setswitchinterval(anterior)

        assert montagem.sessao.contadores.n_trades_bus > 0, "a fonte nao produziu nada"
        # Medido nesta maquina: ~35 fps. O piso de 5 da 7x de folga — largo o
        # bastante para CI compartilhada, apertado o bastante para acusar os
        # 15 fps do padrao de 5 ms com dois paineis disputando.
        assert fps >= 5.0, f"painel starvado: {fps:.1f} quadros/s sob carga"


class TestQuadroOcioso:
    def test_painel_parado_nao_desenha_nada(self, dom):
        """A propriedade mais barata e mais importante do `PainelDenso`.

        Num terminal com oito paineis abertos e seis sem novidade, e a maior
        parte do custo de UI que simplesmente nao acontece. Medida como
        TRABALHO (quadros desenhados), nao como tempo: tempo varia com a
        maquina, zero e zero em qualquer uma.
        """
        dom.aplicar(_livro(), BASE)
        dom._quadro()
        dom.zerar_medicao()
        for _ in range(5_000):
            dom._quadro()
        assert dom.quadros_desenhados == 0
        assert dom.quadros_vazios == 5_000

    def test_custo_do_quadro_ocioso_e_desprezivel(self, dom):
        dom.aplicar(_livro(), BASE)
        dom._quadro()
        inicio = time.perf_counter()
        for _ in range(10_000):
            dom._quadro()
        por_quadro_us = (time.perf_counter() - inicio) * 1e6 / 10_000
        # Medido: 1,00 us. 50 us de teto e folga de 50x — o suficiente para
        # nao piscar em CI compartilhada e ainda assim acusar se alguem
        # colocar trabalho antes da checagem de sujeira.
        assert por_quadro_us < 50.0, f"{por_quadro_us:.1f} us por quadro ocioso"


class TestPortaoDaMatriz:
    """O portao vigiava DOM e tape, e a matriz nao aparecia em linha nenhuma
    deste arquivo — metade do comando que se rodava nao exercitava a peca.

    A matriz e o caso em que a incrementalidade e mais facil de perder: ela
    le a evidencia de TODO trade, entao um `desenhar` que ignore a regiao
    suja repintaria as sete bandas a cada tick sem que a tela ficasse errada.
    E o modo de falha que so a RAZAO acusa.
    """

    @staticmethod
    def _leitura(dominancia: float) -> LeituraMotor:
        return LeituraMotor(
            estagio=EstagioSinal.PRE_SINAL,
            direcao=1,
            direcao_dominante=1,
            faixa=FaixaConviccao.DIRECIONAL,
            dominancia=dominancia,
            magnitude=9_620,
            magnitude_referencia=11_400.0,
            magnitude_relativa=0.84,
            magnitude_fonte="janela",
            na_regiao=True,
            persistencia_trades=3,
            delta_sessao=12_480,
            delta_micro_antigo=-120,
            delta_micro_recente=340,
            agressao_saldo=820,
            agressao_taxa_compra=0.62,
            agressao_trades_s=41.0,
            volume_sem_lado=1_204,
            volume_total=25_000,
        )

    @pytest.fixture
    def matriz(self, qapp):
        painel = PainelMatriz(WDO_GRID)
        painel.resize(620, 460)
        painel.show()
        painel.ao_redimensionar(620, 460)
        painel._recriar_backing()
        painel.aplicar(self._leitura(0.72))
        painel.marcar_tudo_sujo()
        painel._quadro()
        # Aquecimento: o primeiro desenho de cada par fonte/tamanho paga a
        # rasterizacao dos glifos, e com poucas amostras esse custo unico
        # vira o p95 de uma serie cujo p50 e uma ordem de grandeza menor.
        for _ in range(10):
            painel.marcar_tudo_sujo()
            painel._quadro()
        return painel

    def _medir(self, matriz):
        cheio: list[float] = []
        for _ in range(N_AMOSTRAS // 4):
            matriz.marcar_tudo_sujo()
            cheio.append(_cronometrar(matriz))

        incremental: list[float] = []
        for i in range(N_AMOSTRAS):
            # So a dominancia muda: uma banda de 40px, nao as sete.
            matriz.aplicar(self._leitura(0.70 + (i % 25) / 100.0))
            if not matriz.tem_sujeira:
                continue
            incremental.append(_cronometrar(matriz))
        return cheio, incremental

    def test_p95_incremental_abaixo_do_limite(self, matriz):
        _, incremental = self._medir(matriz)
        assert incremental, "nenhum quadro incremental foi medido"
        p95 = _p95(incremental)
        assert p95 < LIMITE_P95_MS, f"quadro incremental da matriz a {p95:.3f} ms p95"

    def test_a_incrementalidade_ainda_existe(self, matriz):
        cheio, incremental = self._medir(matriz)
        razao = statistics.median(cheio) / statistics.median(incremental)
        assert razao >= RAZAO_MINIMA, (
            f"razao cheio/incremental da matriz caiu para {razao:.1f}x "
            f"(cheio {statistics.median(cheio):.3f} ms, "
            f"incremental {statistics.median(incremental):.3f} ms)"
        )

    def test_quadro_cheio_cabe_no_orcamento_de_60hz(self, matriz):
        cheio, _ = self._medir(matriz)
        assert _p95(cheio) < 16.0

    def test_painel_parado_nao_desenha_nada(self, matriz):
        matriz.zerar_medicao()
        for _ in range(5_000):
            matriz._quadro()
        assert matriz.quadros_desenhados == 0
        assert matriz.quadros_vazios == 5_000
