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

import pathlib
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
from tests.medicao import (  # noqa: E402
    Serie,
    Vigia,
    custo_representativo,
    p95,
)

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


def _afirmar_orcamento(serie: Serie, limite_ms: float, o_que: str) -> None:
    """As duas afirmacoes de `tests/medicao.py`, na ordem certa.

    Julga `serie.limpas()`, e nao a serie crua, porque a segunda afirmacao —
    a do p95 — nao e decidivel no nivel da JANELA: o p95 de 200 amostras e o
    decimo quadro mais caro, e dez retiradas do escalonador num laco de meio
    segundo nao movem a razao parede/CPU que o `Vigia` julga. O portao entao
    reprovava dentro de uma janela que o vigia considerava, com razao, quieta.

    O que sai da conta sao os quadros em que o processo NAO ESTAVA RODANDO —
    esses nunca foram medicoes do desenho. O limite e o percentil continuam os
    mesmos, e um quadro caro de verdade queima CPU e permanece na serie. Ver
    `medicao.Serie`.

    Ver a docstring de `tests/medicao.py` para o porque de nao ser um limite
    unico e inflado.
    """
    amostras = serie.limpas(o_que)
    custo = custo_representativo(amostras)
    assert custo < limite_ms, f"{o_que} a {custo:.3f} ms (p10) contra {limite_ms} ms"
    pior = p95(amostras)
    assert pior < limite_ms, f"{o_que} a {pior:.3f} ms p95 contra {limite_ms} ms"


def _cronometrar(painel) -> float:
    inicio = time.perf_counter()
    painel._quadro()
    return (time.perf_counter() - inicio) * 1000.0


# Os lacos dos PORTOES colhem numa `Serie`, e nao numa lista: ela guarda, ao
# lado da parede, a CPU que cada quadro consumiu. E o unico dado que separa
# "o desenho ficou caro" de "o escalonador entrou no meio", e ele nao existe
# no nivel da janela. Ver `medicao.Serie`.


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


def _medir_dom(dom) -> tuple[Serie, Serie, Vigia]:
    """Devolve tambem o VIGIA do intervalo. Ver `tests/medicao.py`: quem julga
    se a medicao vale e o proprio intervalo em que ela foi colhida, nao uma
    sonda avulsa disparada em outro instante."""
    with Vigia() as vigia:
        cheio = Serie()
        for _ in range(N_AMOSTRAS // 2):
            dom.marcar_tudo_sujo()
            cheio.cronometrar(dom)

        incremental = Serie()
        base = _livro()
        bids = list(base.bids)
        for i in range(N_AMOSTRAS):
            # UM nivel muda, e abaixo do degrau de escala corrente para nao
            # disparar reescala (que e um quadro cheio legitimo).
            bids[3] = BookLevel(bids[3].price, 100 + (i % 97), 2)
            dom.aplicar(BookSnapshot(T0 + i, "WDOV26", tuple(bids), base.asks), BASE)
            if not dom.tem_sujeira:
                continue
            incremental.cronometrar(dom)
    return cheio, incremental, vigia


def _rolagem_do_tape(tape) -> Serie:
    rolagem = Serie()
    for i in range(N_AMOSTRAS):
        tape.aplicar(
            (ItemTape(T0 + i, BASE + (i % 5), 10 + i % 50, 1 if i % 2 else -1),)
        )
        if not tape.tem_sujeira:
            continue
        rolagem.cronometrar(tape)
    return rolagem


class TestPortaoDoDOM:
    def test_p95_incremental_abaixo_do_limite(self, dom):
        # `serie.limpas` ja reprova com "nao mediu nada" se a serie vier
        # vazia, entao nao ha o que conferir antes.
        _afirmar_orcamento(
            _medir_dom(dom)[1], LIMITE_P95_MS, "quadro incremental do DOM"
        )

    def test_a_incrementalidade_ainda_existe(self, dom):
        """O teste que sobrevive a troca de maquina.

        Nao afirma velocidade nenhuma: afirma que redesenhar UMA linha e
        muito mais barato que redesenhar quarenta. Se alguem escrever um
        `desenhar` que ignora a regiao suja, a tela continua CORRETA, o
        limite absoluto pode continuar passando numa maquina rapida, e este
        aqui reprova.
        """
        serie_cheio, serie_incremental, vigia = _medir_dom(dom)
        vigia.exigir_quieta("a razao do DOM")
        # A razao compara MEDIANAS, que a cauda nao move — aqui a serie crua
        # serve, e filtrar so um dos lados compararia dois recortes diferentes.
        cheio, incremental = serie_cheio.parede, serie_incremental.parede
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
        _afirmar_orcamento(_medir_dom(dom)[0], 16.0, "quadro cheio do DOM")


class TestPortaoDoTape:
    def test_rolagem_abaixo_do_limite_e_muito_mais_barata_que_o_cheio(self, tape):
        with Vigia() as vigia:
            serie_cheio = Serie()
            for _ in range(N_AMOSTRAS // 2):
                tape.aplicar((ItemTape(T0, BASE, 10, 1),))
                tape.marcar_tudo_sujo()
                serie_cheio.cronometrar(tape)
            serie_rolagem = _rolagem_do_tape(tape)

        _afirmar_orcamento(serie_rolagem, LIMITE_P95_MS, "rolagem do tape")
        vigia.exigir_quieta("a razao do tape")
        # Medianas dos dois lados, da MESMA janela: ver a nota em
        # `test_a_incrementalidade_ainda_existe`.
        cheio, rolagem = serie_cheio.parede, serie_rolagem.parede
        razao = statistics.median(cheio) / statistics.median(rolagem)
        assert razao >= RAZAO_MINIMA, f"razao do tape caiu para {razao:.1f}x"


class TestSobCarga:
    """O que sobrou aqui depois de duas tentativas instaveis minhas.

    A medicao original — quadros por segundo da UI com a fonte inundando numa
    thread propria — ACHOU um defeito real: o quadro do DOM saia de
    sub-milissegundo para 12 ms de PAREDE, e era espera de GIL, nao trabalho.
    Isso virou o `--gil-switch` de `scripts/painel.py`, com tabela medida.

    Mas ela nunca virou um PORTAO honesto. A primeira versao afirmava um piso
    absoluto de 5 quadros/s e reprovava ao desligar um modulo que nao tem nada
    com a UI: com produtor sem espera, pipeline mais LEVE inunda mais forte e
    a interface fica mais faminta (medido: tudo ligado 16,5 fps, sem
    metodologia 2,0). A segunda virou razao entre dois intervalos de troca —
    conceitualmente certa, e ainda assim instavel, porque duas medicoes de
    contencao de GIL no mesmo processo nao sao independentes: compartilham
    cache, coletor e escalonador.

    Portao que reprova por ordem de execucao ensina todo mundo a ignorar
    portao. A medicao continua existindo, com o raciocinio inteiro, em
    `bench_ui_carga.py` — que e onde este projeto ja guarda numero que informa
    sem julgar. Aqui fica so o que e deterministico: sob carga, a interface
    desenha. Nao afirma fluidez, e nao finge afirmar.
    """

    def test_a_interface_desenha_sob_carga(self):
        """Roda em PROCESSO PROPRIO. A terceira coisa que este teste me ensinou.

        Ele e o unico da suite que roda o laco de eventos de verdade
        (`processEvents` num laco de 2 s); todos os outros desenham chamando
        `_quadro()` direto. Como a `QApplication` e de escopo de sessao, o
        primeiro `processEvents()` da suite despacha, de uma vez, tudo o que os
        testes anteriores deixaram na fila do Qt.

        Medido: com quatro processos queimando CPU ao lado, rodar
        `test_ui_composicao.py` antes deste derruba o processo com `Windows
        fatal exception: access violation`, 5 de 6 rodadas. Sozinho sob a mesma
        carga, ele passa 6 de 6 — bissectado ate o par de arquivos. Nao e
        instabilidade dele: e acoplamento a `QApplication` compartilhada.

        Drenar a fila entre os testes (`conftest.py::_drenar_qt`) reduziu o
        acumulo mas nao fechou o buraco, porque nao ha como saber o que cada
        widget de cada teste ainda tem pendente. O que fecha e nao compartilhar
        estado: processo novo, `QApplication` nova, fila vazia.

        E o mesmo movimento que tirou a medicao de GIL desta suite para
        `bench_ui_carga.py`, pelo mesmo motivo — quando o resultado depende do
        que rodou antes, o portao nao esta medindo o produto.
        """
        import json
        import subprocess
        import sys

        resultado = subprocess.run(
            [sys.executable, "-c", _CENARIO_SOB_CARGA],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_RAIZ),
        )
        assert resultado.returncode == 0, (
            f"o cenario caiu (codigo {resultado.returncode})" + chr(10)
            + f"stdout: {resultado.stdout[-2000:]}" + chr(10)
            + f"stderr: {resultado.stderr[-2000:]}"
        )
        medido = json.loads(resultado.stdout.strip().splitlines()[-1])
        assert medido["negocios"] > 0, "a fonte nao produziu nada"
        # Zero quadros em 2 s de carga e morte por inanicao, e isso NAO depende
        # de maquina nem de ordem. Qualquer numero acima de zero e assunto do
        # benchmark, nao do portao.
        assert medido["quadros"] > 0, "a interface nao desenhou um quadro sequer sob carga"


_RAIZ = pathlib.Path(__file__).resolve().parent.parent

_CENARIO_SOB_CARGA = """
import json, os, sys, threading, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())

from PySide6.QtWidgets import QApplication

from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados
from fluxopro.app.montagem import montar
from fluxopro.ui.janela import JanelaFluxo
from fluxopro.ui.ponte import PonteFluxo
from scripts.painel import GIL_SWITCH_PADRAO

sys.setswitchinterval(GIL_SWITCH_PADRAO)
app = QApplication.instance() or QApplication([])
config = ConfigOperacao(
    symbol="WDOV26",
    fonte=FonteDados.SIMULADOR,
    simulador=ConfigSimulador(seed=7, n_eventos=10**9, taxa_eventos_s=500.0),
)
ref = {}
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
    fim = time.perf_counter() + 2.0
    while time.perf_counter() < fim:
        app.processEvents()
    quadros = janela.dom.quadros_desenhados
    negocios = montagem.sessao.contadores.n_trades_bus
finally:
    montagem.fonte.parar()
    thread.join(timeout=5.0)
    janela.close()
    montagem.sessao.finalizar()
print(json.dumps({"quadros": quadros, "negocios": negocios}))
"""


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

    def _medir(self, matriz) -> tuple[Serie, Serie, Vigia]:
        cheio = Serie()
        # Ver a nota de resolucao em `tests/medicao.py::Vigia.CPU_MINIMA_S`:
        # com um quarto destas amostras o laco nao gastava CPU suficiente para
        # o vigia poder julgar se a maquina estava entregando CPU.
        with Vigia() as vigia:
            for _ in range(N_AMOSTRAS):
                matriz.marcar_tudo_sujo()
                cheio.cronometrar(matriz)

            incremental = Serie()
            for i in range(N_AMOSTRAS * 4):
                # So a dominancia muda: uma banda de 40px, nao as sete.
                matriz.aplicar(self._leitura(0.70 + (i % 25) / 100.0))
                if not matriz.tem_sujeira:
                    continue
                incremental.cronometrar(matriz)
        return cheio, incremental, vigia

    def test_p95_incremental_abaixo_do_limite(self, matriz):
        _afirmar_orcamento(
            self._medir(matriz)[1],
            LIMITE_P95_MS,
            "quadro incremental da matriz",
        )

    def test_a_incrementalidade_ainda_existe(self, matriz):
        serie_cheio, serie_incremental, vigia = self._medir(matriz)
        vigia.exigir_quieta("a razao da matriz")
        # Medianas dos dois lados, da MESMA janela: ver a nota em
        # `TestPortaoDoDOM.test_a_incrementalidade_ainda_existe`.
        cheio, incremental = serie_cheio.parede, serie_incremental.parede
        razao = statistics.median(cheio) / statistics.median(incremental)
        assert razao >= RAZAO_MINIMA, (
            f"razao cheio/incremental da matriz caiu para {razao:.1f}x "
            f"(cheio {statistics.median(cheio):.3f} ms, "
            f"incremental {statistics.median(incremental):.3f} ms)"
        )

    def test_quadro_cheio_cabe_no_orcamento_de_60hz(self, matriz):
        _afirmar_orcamento(self._medir(matriz)[0], 16.0, "quadro cheio da matriz")

    def test_painel_parado_nao_desenha_nada(self, matriz):
        matriz.zerar_medicao()
        for _ in range(5_000):
            matriz._quadro()
        assert matriz.quadros_desenhados == 0
        assert matriz.quadros_vazios == 5_000
