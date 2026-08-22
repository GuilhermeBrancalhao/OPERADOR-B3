"""Matriz de estado — comportamento, TRABALHO, retencao e as duas paletas.

Quatro coisas se afirmam aqui, e a segunda e a que costuma faltar:

* **Comportamento** — o farol anda com o estagio, a direcao continua legivel
  no texto, o volume sem lado nao some quando zera, e `derivar` nao inventa
  nem esquece estado entre dois sinais.

* **Trabalho** — nao "o pixel saiu certo", e sim **quantos retangulos foram
  sujados**. Um painel pode desenhar a tela perfeita repintando tudo a cada
  trade e nenhum teste de aparencia notaria; a conta de retangulos nota na
  hora. E o mesmo motivo pelo qual `tests/test_ui_desempenho.py` mede a
  RAZAO cheio/incremental em vez de milissegundos: a razao sobrevive a
  troca de maquina, o milissegundo nao.

* **Retencao limitada** — este projeto encontrou oito vezes a estrutura que
  cresce com o estado acumulado. O vetor de deteccoes e indexado por LINHA
  DA TELA; mil deteccoes tem de deixar o mesmo tamanho que uma.

* **Duas paletas** — `PALETA_SEM_COR` colapsa o eixo direcional inteiro numa
  cor so. Se a direcao so existisse na cor, o teste que compara os TEXTOS
  das duas passadas acusaria: sao os mesmos textos, e neles a direcao
  continua escrita.

O espiao de `QPainter` existe porque a alternativa seria comparar imagens, e
comparacao de imagem quebra quando a maquina troca de fonte e passa quando a
logica quebra — o inverso exato do que se quer.

## Geometria — o buraco que a rodada 3 fechou

Ate aqui o espiao via `setPen` e `drawText`, e mais nada. Consequencia
medida: `test_o_eixo_grafa_o_lado_dominante...` afirmava no nome e na
docstring que o EIXO aponta para a compra, e o corpo so conferia dois
textos — **inverter o sentido do cursor desenharia a seta do lado da venda e
os 52 testes continuariam verdes**. Valia para o eixo, para a regua, para as
barras bipolares e para a barra de confianca: nenhuma tinha uma assercao
sequer.

Geometria que nenhum teste ve e geometria que pode inverter em silencio — e
num painel direcional a inversao silenciosa e o defeito mais caro possivel,
porque a tela continua bonita e diz o contrario do que o motor concluiu.

Agora o espiao registra tambem `fillRect` e `drawLine`, e as assercoes de
direcao sao feitas contra o ZERO DESENHADO (a linha de centro que o proprio
painel pinta), nao contra uma coordenada copiada do codigo de producao: se
alguem mover a coluna, o teste continua valendo; se alguem inverter o lado,
ele reprova.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
import dataclasses
import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402

from fluxopro.core.eventos import WDO_GRID, Side  # noqa: E402
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao  # noqa: E402
from fluxopro.microestrutura.eventos_mbo import FonteMicro  # noqa: E402
from fluxopro.metodologia.regras import REGRAS  # noqa: E402
from fluxopro.motor.sinais import (  # noqa: E402
    ConfigMotorSinais,
    EstagioSinal,
    FaixaConviccao,
    Sinal,
)
from fluxopro.ui import formato, tokens  # noqa: E402
from fluxopro.ui.paineis import matriz as mod  # noqa: E402
from fluxopro.ui.paineis.matriz import (  # noqa: E402
    COL_CONF_BARRA,
    ESCALA_MAGNITUDE,
    FRACAO_RARA,
    MAX_SLOTS_DETECCAO,
    procedencia_metodologica,
    ItemDeteccao,
    LeituraMotor,
    PainelMatriz,
    derivar,
    item_de_deteccao,
)

T0 = 1_700_000_000_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)

LARGURA, ALTURA = 560, 820


def leitura(**mudancas) -> LeituraMotor:
    """Uma leitura plausivel de pregao direcional comprador."""
    campos = dict(
        estagio=EstagioSinal.PRE_SINAL,
        direcao=1,
        faixa=FaixaConviccao.DIRECIONAL,
        dominancia=0.724,
        magnitude=9_620,
        magnitude_referencia=11_400.0,
        magnitude_relativa=0.84,
        magnitude_fonte="janela",
        bloqueio="",
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
    campos.update(mudancas)
    return LeituraMotor(**campos)


def deteccao(
    n: int = 0, tipo: TipoDeteccao = TipoDeteccao.ABSORCAO, inferida: bool = False
) -> object:
    """Uma `DeteccaoAnotada` como `SessaoFluxo` a emite, sem importar `app`."""
    bruta = Deteccao(
        timestamp_ns=T0 + n * 1_000_000_000,
        symbol="WDOV26",
        tipo=tipo,
        side=Side.BUY if n % 2 == 0 else Side.SELL,
        price=BASE + (n % 5),
        confianca=0.55 if inferida else 1.0,
    )
    return SimpleNamespace(
        deteccao=bruta,
        fonte=FonteMicro.MBP_INFERIDO if inferida else FonteMicro.MBO,
        confianca_efetiva=bruta.confianca,
        inferida=inferida,
    )


def _pronto(painel, largura: int = LARGURA, altura: int = ALTURA):
    painel.resize(largura, altura)
    painel.show()
    painel.ao_redimensionar(largura, altura)
    painel._recriar_backing()
    painel.marcar_tudo_sujo()
    painel._quadro()
    return painel


@pytest.fixture
def largo(qapp):
    """Painel largo o bastante para a faixa caber COM o limiar junto.

    A plataforma offscreen usa uma fonte de emergencia ~2x mais larga que
    Iosevka/Inter (14 px/caractere contra ~8 medidos na nativa), entao 560 px
    aqui simulam uma janela muito mais estreita do que representam. Medir o
    corte de layout contra a fonte de emergencia do Qt seria medir o Qt.
    """
    painel = _pronto(PainelMatriz(WDO_GRID), 1_180, ALTURA)
    painel.aplicar(leitura(), eventos=[deteccao(i) for i in range(6)])
    painel._quadro()
    return painel


@pytest.fixture
def matriz(qapp):
    painel = _pronto(PainelMatriz(WDO_GRID))
    # Com deteccoes na tela: e o estado em que o painel realmente vive, e
    # medir o quadro cheio com a banda de deteccoes VAZIA mediria um painel
    # que nao existe. Passa de `MIN_AMOSTRAS_RARIDADE` de proposito, para a
    # coluna de fatia estar publicando veredito e nao aquecimento.
    painel.aplicar(leitura(), eventos=[deteccao(i) for i in range(40)])
    painel._quadro()
    return painel


# --------------------------------------------------------------------------
# Espiao de QPainter
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Pintado:
    """Um retangulo preenchido: onde, de que tamanho, de que cor."""

    x: int
    y: int
    largura: int
    altura: int
    cor: str

    @property
    def direita(self) -> int:
        return self.x + self.largura

    @property
    def meio(self) -> int:
        return self.x + self.largura // 2


class PainterEspiao:
    """Encaminha tudo para um `QPainter` real e guarda o que foi desenhado.

    Um proxy Python funciona porque `desenhar` so fala com o painter pela
    interface publica. Comparar TEXTO e a unica forma honesta de afirmar
    "a direcao continua legivel sem cor" — comparar pixel afirmaria outra
    coisa (que o desenho nao mudou), que e justamente o que se espera que
    mude quando a paleta muda.
    """

    def __init__(self, painter: QPainter) -> None:
        self._painter = painter
        self.textos: list[str] = []
        self.pares: list[tuple[str, str]] = []
        self.retangulos: list[Pintado] = []
        self.linhas: list[tuple[int, int, int, int, str]] = []
        self._caneta = ""

    def __getattr__(self, nome):
        return getattr(self._painter, nome)

    def setPen(self, cor):  # noqa: N802
        self._caneta = cor.name() if hasattr(cor, "name") else str(cor)
        return self._painter.setPen(cor)

    def fillRect(self, *args):  # noqa: N802
        if len(args) == 2 and hasattr(args[0], "width"):
            r, cor = args
            self.retangulos.append(
                Pintado(
                    r.x(),
                    r.y(),
                    r.width(),
                    r.height(),
                    cor.name() if hasattr(cor, "name") else str(cor),
                )
            )
        return self._painter.fillRect(*args)

    def drawLine(self, *args):  # noqa: N802
        if len(args) == 4:
            self.linhas.append((args[0], args[1], args[2], args[3], self._caneta))
        return self._painter.drawLine(*args)

    def drawText(self, *args):  # noqa: N802 — assinatura do Qt
        if args and isinstance(args[-1], str):
            self.textos.append(args[-1])
            self.pares.append((self._caneta, args[-1]))
        return self._painter.drawText(*args)


def _textos_de(painel) -> list[str]:
    pixmap = QPixmap(painel.width(), painel.height())
    pixmap.fill(tokens.BG_SURFACE)
    painter = QPainter(pixmap)
    espiao = PainterEspiao(painter)
    try:
        painel.desenhar(espiao, QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return espiao.textos


def _pintura_de(painel) -> PainterEspiao:
    """O espiao inteiro — textos, canetas, retangulos e linhas."""
    pixmap = QPixmap(painel.width(), painel.height())
    pixmap.fill(tokens.BG_SURFACE)
    painter = QPainter(pixmap)
    espiao = PainterEspiao(painter)
    try:
        painel.desenhar(espiao, QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return espiao


def _pares_de(painel) -> list[tuple[str, str]]:
    """(cor da caneta, texto) — para afirmar HIERARQUIA, nao so presenca."""
    pixmap = QPixmap(painel.width(), painel.height())
    pixmap.fill(tokens.BG_SURFACE)
    painter = QPainter(pixmap)
    espiao = PainterEspiao(painter)
    try:
        painel.desenhar(espiao, QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return espiao.pares


# --------------------------------------------------------------------------
# Comportamento
# --------------------------------------------------------------------------
class TestOEstadoQueOMotorDerivou:
    def test_o_farol_mostra_os_cinco_estagios_e_marca_o_corrente(self, matriz):
        """O estagio E a informacao; mostrar so o binario jogaria fora o
        melhor do `motor/sinais.py` (§6, fase 4)."""
        textos = _textos_de(matriz)
        for rotulo in mod.ROTULO_ESTAGIO.values():
            assert rotulo in textos, f"estagio {rotulo} ausente do trilho"

    def test_a_faixa_de_conviccao_carrega_o_proprio_limiar(self, largo):
        """A regua de 10px e a primeira coisa que o canal apaga. Sem o limiar
        dentro do rotulo, `DIRECIONAL` vira adjetivo sem numero."""
        textos = _textos_de(largo)
        assert any(t.startswith("DIRECIONAL ≥70%") for t in textos)
        assert any(t.startswith(formato.MAIS + "72,4%") for t in textos)

    def test_a_faixa_do_corte_disputado_avisa_que_a_fonte_diverge(self, largo):
        """Sai do registro, nao da opiniao do painel:
        `dominancia.limiar_direcional` e IMPRECISO porque um video diz 70% e
        outro 75% para o mesmo conceito."""
        assert "DIRECIONAL ≥70% · FONTE DIVERGE" in _textos_de(largo)

    def test_faixa_sem_divergencia_registrada_nao_inventa_aviso(self, largo):
        """Inventar divergencia onde o registro nao registra e o mesmo pecado
        ao contrario."""
        largo.aplicar(
            leitura(dominancia=0.86, faixa=FaixaConviccao.MAXIMA_CONVICCAO)
        )
        textos = _textos_de(largo)
        assert "CONVICÇÃO MÁXIMA ≥80%" in textos
        assert not any("FONTE DIVERGE" in t for t in textos)

    def test_o_gate_de_magnitude_mostra_valor_limiar_e_veredito(self, matriz):
        """`PASSA` sozinho seria um oraculo. O numero e o limiar vao junto."""
        textos = _textos_de(matriz)
        assert "PASSA" in textos
        assert any("0,84" in t and "gate" in t and "0,60" in t for t in textos)

    def test_bloqueio_de_magnitude_e_dito_com_a_mesma_evidencia(self, matriz):
        matriz.aplicar(leitura(magnitude_relativa=0.31, bloqueio="magnitude_relativa"))
        textos = _textos_de(matriz)
        assert "BLOQUEIA" in textos
        assert "PASSA" not in textos

    def test_magnitude_sem_referencia_e_marcada_como_assumida(self, matriz):
        """Sem referencia o motor ASSUME 1,0 e deixa passar. O `1,00` na tela
        e um default, nao uma medida — e os dois nao podem sair iguais."""
        matriz.aplicar(leitura(magnitude_relativa=1.0, magnitude_referencia=None,
                               magnitude_fonte="nenhuma"))
        textos = _textos_de(matriz)
        # O numero NAO e publicado na forma de medida...
        assert "SEM REFERÊNCIA" in textos
        assert not any(t.startswith("1,00  gate") for t in textos)
        # ...e a ressalva mora DENTRO da palavra do veredito.
        assert "PASSA SEM MEDIR" in textos
        assert "PASSA" not in textos

    def test_as_duas_metades_da_janela_micro_ficam_visiveis(self, matriz):
        """E a comparacao que o motor usa para decidir "virou"; o total
        sozinho esconde exatamente o que produz o estagio."""
        textos = _textos_de(matriz)
        assert any(
            "1ª" in t and "2ª" in t and formato.MENOS + "120" in t and "+340" in t
            for t in textos
        )

    def test_volume_sem_lado_aparece_mesmo_quando_e_zero(self, matriz):
        """RLP nunca escondido. Uma linha que some ensina o olho a nao
        procurar por ela — e ai ela some no dia em que importa."""
        matriz.aplicar(leitura(volume_sem_lado=0, volume_total=25_000))
        textos = _textos_de(matriz)
        assert "S/ LADO" in textos
        assert "0" in textos

    def test_procedencia_da_deteccao_vem_junto_da_confianca(self, matriz):
        matriz.aplicar(eventos=[deteccao(0, inferida=True), deteccao(1, inferida=False)])
        textos = _textos_de(matriz)
        assert "MBP INFERIDO" in textos
        assert "MBO" in textos
        assert "0,55" in textos
        assert "1,00" in textos

    def test_painel_sem_leitura_desenha_a_grade_e_diz_que_esta_vazio(self, qapp):
        """§3.5: a grade aparece. Nunca um retangulo em branco — o operador
        precisa reconhecer o painel antes de ele ter dado."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        textos = _textos_de(painel)
        assert "MATRIZ DE ESTADO" in textos
        assert "SEM DETECÇÕES AINDA" in textos
        assert "NENHUM" in textos


class TestDerivar:
    def test_sem_sinal_novo_os_campos_do_motor_sao_preservados(self):
        """`SessaoFluxo` emite `Sinal` so na MUDANCA de estagio. Um quadro
        que zerasse a dominancia por falta de sinal mostraria "LATERAL 50%"
        no meio de um pregao direcional."""
        anterior = leitura()
        nova = derivar(None, anterior=anterior)
        assert nova.dominancia == anterior.dominancia
        assert nova.faixa is anterior.faixa
        assert nova.estagio is anterior.estagio

    def test_analytics_sao_lidos_mesmo_sem_sinal_novo(self):
        agressao = SimpleNamespace(
            saldo_agressao=-450,
            taxa_compra=0.31,
            velocidade_trades_por_segundo=lambda: 12.0,
        )
        delta = SimpleNamespace(
            delta_sessao=-7_700,
            volume_nao_atribuido_sessao=2_100,
            volume_total_sessao=48_000,
        )
        nova = derivar(None, agressao, delta, anterior=leitura())
        assert nova.agressao_saldo == -450
        assert nova.delta_sessao == -7_700
        assert nova.volume_sem_lado == 2_100

    def test_bloqueio_nao_e_herdado_do_quadro_anterior(self):
        """Ausente na evidencia significa "nao bloqueou neste trade", nao
        "mantem o bloqueio". Herdar deixaria o gate aceso depois de
        liberado — um falso vermelho e tao caro quanto um falso verde."""
        anterior = leitura(bloqueio="magnitude_relativa")
        sinal = Sinal(
            T0,
            "WDOV26",
            EstagioSinal.DIRECAO_CONFIRMADA,
            Side.BUY,
            {"dominancia": 0.78, "faixa": "DIRECIONAL", "magnitude_relativa": 0.9},
        )
        nova = derivar(sinal, anterior=anterior)
        assert nova.bloqueio == ""

    def test_le_a_evidencia_do_sinal_real_do_motor(self):
        sinal = Sinal(
            T0,
            "WDOV26",
            EstagioSinal.CONFIRMADO,
            Side.SELL,
            {
                "dominancia": 0.83,
                "faixa": "MAXIMA_CONVICCAO",
                "magnitude": 4_200,
                "magnitude_referencia": 5_000.0,
                "magnitude_referencia_fonte": "max_sessao",
                "magnitude_relativa": 0.84,
                "delta_micro_primeira_metade": 90,
                "delta_micro_segunda_metade": -260,
                "na_regiao": True,
                "persistencia_trades": 4,
            },
        )
        nova = derivar(sinal)
        assert nova.estagio is EstagioSinal.CONFIRMADO
        assert nova.direcao == -1
        assert nova.faixa is FaixaConviccao.MAXIMA_CONVICCAO
        assert nova.magnitude_fonte == "max_sessao"
        assert nova.delta_micro == -170

    def test_direcao_publicada_e_direcao_dominante_sao_coisas_diferentes(self):
        """Enquanto a histerese acumula, o motor publica `NENHUM`/`None` e a
        janela ja esta 100% compradora. As duas coisas sao verdade ao mesmo
        tempo: o farol diz "sem direcao", o eixo aponta para a compra."""
        sinal = Sinal(
            T0,
            "WDOV26",
            EstagioSinal.NENHUM,
            None,
            {
                "dominancia": 1.0,
                "faixa": "MAXIMA_CONVICCAO",
                "direcao_dominante": "BUY",
                "persistencia_trades": 1,
            },
        )
        nova = derivar(sinal)
        assert nova.direcao == 0
        assert nova.direcao_dominante == 1
        assert nova.lado_dominancia == 1

    def test_o_eixo_grafa_o_lado_dominante_mesmo_sem_direcao_publicada(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            leitura(
                estagio=EstagioSinal.NENHUM,
                direcao=0,
                direcao_dominante=1,
                dominancia=1.0,
                faixa=FaixaConviccao.MAXIMA_CONVICCAO,
            )
        )
        textos = _textos_de(painel)
        assert formato.MAIS + "100,0% NÃO CONFIRMADO" in textos
        assert any("SEM DIREÇÃO" in t for t in textos)

    def test_deteccao_crua_sem_anotacao_tambem_e_aceita(self):
        bruta = Deteccao(T0, "WDOV26", TipoDeteccao.ESCORA, Side.BUY, BASE, 0.55)
        item = item_de_deteccao(bruta)
        assert isinstance(item, ItemDeteccao)
        assert item.inferida is True  # confianca < 1.0 e o que resta como pista
        assert item_de_deteccao(object()) is None
        assert item_de_deteccao(Sinal(T0, "W", EstagioSinal.NENHUM, None)) is None


# --------------------------------------------------------------------------
# Trabalho — quantos retangulos, nao se o pixel saiu certo
# --------------------------------------------------------------------------
class TestTrabalho:
    def test_leitura_identica_nao_suja_nada(self, matriz):
        matriz.aplicar(leitura())
        assert matriz._sujos == []
        assert matriz.tem_sujeira is False

    def test_painel_parado_nao_desenha_quadro(self, matriz):
        matriz.zerar_medicao()
        for _ in range(2_000):
            matriz.aplicar(leitura())
            matriz._quadro()
        assert matriz.quadros_desenhados == 0
        assert matriz.quadros_vazios == 2_000

    def test_dominancia_suja_uma_banda_so(self, matriz):
        matriz.aplicar(leitura(dominancia=0.81))
        assert len(matriz._sujos) == 1
        assert matriz._tudo_sujo is False
        assert matriz._sujos[0].height() == mod.ALTURA_DOMINANCIA

    def test_agressao_suja_a_banda_de_medidas_so(self, matriz):
        matriz.aplicar(leitura(agressao_saldo=900))
        assert len(matriz._sujos) == 1
        assert matriz._sujos[0] == matriz._bandas[mod.BANDA_MEDIDAS]

    def test_estagio_suja_a_banda_do_farol_so(self, matriz):
        matriz.aplicar(leitura(estagio=EstagioSinal.CONFIRMADO))
        assert len(matriz._sujos) == 1
        assert matriz._sujos[0] == matriz._bandas[mod.BANDA_ESTAGIO]

    def test_deteccao_nova_rola_em_vez_de_repintar(self, matriz):
        """Chega uma deteccao: o backing rola uma linha e sujam-se a faixa
        que entrou e o contador do cabecalho. Duas faixas, nunca a tela."""
        matriz.aplicar(eventos=[deteccao(1)])
        assert matriz._tudo_sujo is False
        assert 1 <= len(matriz._sujos) <= 2
        altura_suja = sum(r.height() for r in matriz._sujos)
        assert altura_suja <= matriz.densidade.altura_linha + mod.ALTURA_ROTULO

    def test_enxurrada_de_deteccoes_colapsa_em_vez_de_rolar_n_vezes(self, matriz):
        """Chegou mais do que cabe: rolar seria mover pixels que vao ser
        todos sobrescritos."""
        matriz.aplicar(eventos=[deteccao(i) for i in range(matriz._n_slots + 5)])
        assert matriz._tudo_sujo is True

    def test_a_incrementalidade_existe_e_e_grande(self, matriz):
        """O teste que sobrevive a troca de maquina.

        Nao afirma velocidade: afirma que redesenhar UMA banda e muito mais
        barato que redesenhar as seis. Se alguem escrever um `desenhar` que
        ignora a regiao suja, a tela continua CORRETA e este reprova."""
        cheio: list[float] = []
        for _ in range(60):
            matriz.marcar_tudo_sujo()
            inicio = time.perf_counter()
            matriz._quadro()
            cheio.append((time.perf_counter() - inicio) * 1000.0)

        incremental: list[float] = []
        for i in range(120):
            matriz.aplicar(leitura(dominancia=0.70 + (i % 25) / 100.0))
            if not matriz.tem_sujeira:
                continue
            inicio = time.perf_counter()
            matriz._quadro()
            incremental.append((time.perf_counter() - inicio) * 1000.0)

        assert incremental, "nenhum quadro incremental foi medido"
        razao = statistics.median(cheio) / statistics.median(incremental)
        assert razao >= 5.0, (
            f"razao cheio/incremental caiu para {razao:.1f}x "
            f"(cheio {statistics.median(cheio):.3f} ms, "
            f"incremental {statistics.median(incremental):.3f} ms)"
        )

    def test_quadro_cheio_cabe_no_orcamento_de_60hz(self, matriz):
        """Quadro cheio acontece em redimensionamento e mudanca de paleta.

        Nao precisa ser barato como o incremental, mas nao pode estourar os
        16 ms — senao arrastar a divisoria da janela engasga a tela.

        Os primeiros quadros sao DESCARTADOS de proposito: o primeiro
        desenho de cada combinacao fonte/tamanho paga a rasterizacao dos
        glifos, e com 40 amostras esse custo unico virava o p95 (medido: 25
        ms no p95 de uma serie cujo p50 era 2,6 ms). Medir o aquecimento
        junto nao mede o painel, mede o cache de fontes do Qt."""
        for _ in range(10):
            matriz.marcar_tudo_sujo()
            matriz._quadro()
        amostras = []
        for _ in range(80):
            matriz.marcar_tudo_sujo()
            inicio = time.perf_counter()
            matriz._quadro()
            amostras.append((time.perf_counter() - inicio) * 1000.0)
        ordenadas = sorted(amostras)
        p95 = ordenadas[min(len(ordenadas) - 1, int(len(ordenadas) * 0.95))]
        assert p95 < 16.0, f"quadro cheio da matriz a {p95:.3f} ms p95"


# --------------------------------------------------------------------------
# Retencao limitada por construcao
# --------------------------------------------------------------------------
class TestRetencao:
    def test_mil_deteccoes_deixam_o_mesmo_tamanho_que_uma(self, matriz):
        for i in range(1_000):
            matriz.aplicar(eventos=[deteccao(i)])
            matriz._quadro()
        assert len(matriz._deteccoes) == matriz._n_slots
        # O CONTADOR cresce (6 da fixture + 1.000); a ESTRUTURA nao.
        assert matriz.n_deteccoes == 1_040

    def test_a_estrutura_e_indexada_por_linha_de_tela(self, matriz):
        assert matriz._n_slots == len(matriz.deteccoes_visiveis)
        assert matriz._n_slots <= MAX_SLOTS_DETECCAO

    def test_janela_gigante_nao_passa_do_teto_de_slots(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID), 900, 4_000)
        assert painel._n_slots == MAX_SLOTS_DETECCAO
        assert len(painel._deteccoes) == MAX_SLOTS_DETECCAO

    def test_encolher_a_janela_descarta_o_excedente(self, matriz):
        for i in range(30):
            matriz.aplicar(eventos=[deteccao(i)])
        cheio = matriz._n_slots
        matriz.resize(LARGURA, 420)
        matriz.ao_redimensionar(LARGURA, 420)
        assert matriz._n_slots < cheio
        assert len(matriz._deteccoes) == matriz._n_slots

    def test_janela_baixa_demais_nao_quebra_nem_guarda_nada(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID), 400, 250)
        painel.aplicar(leitura(), eventos=[deteccao(1)])
        painel._quadro()
        assert painel._n_slots == len(painel._deteccoes)
        assert painel._n_slots >= 0

    def test_a_mais_nova_fica_no_topo(self, matriz):
        matriz.aplicar(eventos=[deteccao(1, TipoDeteccao.ESCORA)])
        matriz.aplicar(eventos=[deteccao(2, TipoDeteccao.ICEBERG)])
        assert matriz.deteccoes_visiveis[0].rotulo == "ICEBERG"
        assert matriz.deteccoes_visiveis[1].rotulo == "ESCORA"


# --------------------------------------------------------------------------
# As duas paletas
# --------------------------------------------------------------------------
class TestSemCor:
    def test_desenha_nas_duas_paletas_sem_quebrar(self, qapp):
        for paleta in (tokens.PALETA_COR, tokens.PALETA_SEM_COR):
            painel = _pronto(PainelMatriz(WDO_GRID, paleta=paleta))
            painel.aplicar(leitura(), eventos=[deteccao(1), deteccao(2, inferida=True)])
            painel._quadro()
            assert painel.quadros_desenhados >= 1

    def test_o_texto_e_identico_nas_duas_paletas(self, qapp):
        """Se a direcao vivesse na cor, os textos seriam iguais e a tela sem
        cor perderia a informacao. Sao iguais **e** a direcao esta escrita
        neles: e essa a prova, nao a igualdade sozinha."""
        saidas = []
        for paleta in (tokens.PALETA_COR, tokens.PALETA_SEM_COR):
            painel = _pronto(PainelMatriz(WDO_GRID, paleta=paleta))
            painel.aplicar(leitura(), eventos=[deteccao(1), deteccao(3)])
            saidas.append(_textos_de(painel))
        assert saidas[0] == saidas[1]

    def test_a_direcao_e_recuperavel_do_texto_sozinho(self, qapp):
        """Os polos do eixo (`« VENDA` / `COMPRA »`) sao rotulos FIXOS e nao
        contam como evidencia de direcao: eles aparecem iguais nos dois
        sentidos. A primeira versao deste teste era satisfeita por eles —
        rodar com `direcao=-1` passava do mesmo jeito."""
        vivos = {"« VENDA", "COMPRA »"}

        def _direcionais(paleta, **mudancas):
            painel = _pronto(PainelMatriz(WDO_GRID, paleta=paleta))
            painel.aplicar(leitura(**mudancas))
            return [t for t in _textos_de(painel) if t not in vivos]

        compra = _direcionais(tokens.PALETA_SEM_COR)
        assert any("COMPRA" in t for t in compra)
        assert not any("VENDA" in t for t in compra)
        assert any(t.startswith(formato.MAIS) for t in compra)
        assert any(mod.SETA_COMPRA in t for t in compra)

        venda = _direcionais(
            tokens.PALETA_SEM_COR, direcao=-1, direcao_dominante=-1,
            delta_sessao=-9_300, agressao_saldo=-800,
        )
        assert any("VENDA" in t for t in venda)
        assert not any("COMPRA" in t for t in venda)
        assert any(t.startswith(formato.MENOS) for t in venda)
        assert any(mod.SETA_VENDA in t for t in venda)

    def test_direcao_vendedora_sai_com_menos_tipografico(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID, paleta=tokens.PALETA_SEM_COR))
        painel.aplicar(leitura(direcao=-1, delta_sessao=-9_300))
        textos = _textos_de(painel)
        assert any("VENDA" in t and mod.SETA_VENDA in t for t in textos)
        assert formato.MENOS + "9.300" in textos
        # E nunca parenteses no lugar do sinal — a falha F2 do Profit.
        assert not any(t.startswith("(") for t in textos)

    def test_empate_nao_ganha_sinal_de_compra(self, qapp):
        """`+50,0%` sugeriria compra marginal onde ha empate."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            leitura(direcao=0, dominancia=0.5, faixa=FaixaConviccao.LATERAL)
        )
        textos = _textos_de(painel)
        assert any(t.startswith("50,0%") for t in textos)
        assert not any(t.startswith(formato.MAIS + "50,0%") for t in textos)


class TestTokens:
    def test_o_painel_nao_escreve_cor_literal(self):
        """§3.2: nenhum painel escreve cor literal, jamais. Um `QColor(...)`
        no corpo do painel escaparia do modo sem cor e do teste de contraste
        de uma vez so."""
        import inspect
        import re

        for linha in inspect.getsource(mod).splitlines():
            codigo = linha.split("#")[0]
            assert "QColor(" not in codigo, f"cor construida no painel: {linha!r}"
            assert not re.search(r"#[0-9A-Fa-f]{6}\b", linha), (
                f"hex literal no painel: {linha!r}"
            )


# --------------------------------------------------------------------------
# Procedencia da REGRA — a lacuna da rodada 1
# --------------------------------------------------------------------------
class TestProcedenciaMetodologica:
    """De onde veio a REGRA, e nao so de onde veio o dado.

    O painel gastava uma coluna inteira, um token ambar e tres paragrafos de
    docstring distinguindo MBO observado de MBP inferido — procedencia do
    DADO — e zero pixel dizendo que `metodologia/regras.py` classifica
    `exaustao.conceito` como AUSENTE_NA_FONTE e `implementada=False`. O
    operador lia "o motor concluiu, pelo metodo, exaustao" vinte e duas vezes
    quando a resposta honesta e "um detector generico interno disparou".
    """

    def test_sai_do_registro_e_nao_de_um_mapa_na_ui(self):
        """Derivado da familia de ids. Um `dict` escrito aqui seria uma
        segunda fonte de procedencia, que envelhece em silencio."""
        assert procedencia_metodologica("EXAUSTAO") == (False, "exaustao.conceito")
        assert procedencia_metodologica("ESCORA") == (False, "escora.formula")
        # Sem entrada no registro: "uma regra ausente do registro e uma regra
        # que o produto nao sustenta" (docstring de regras.py).
        assert procedencia_metodologica("ABSORCAO") == (False, "")
        assert procedencia_metodologica("ICEBERG") == (False, "")
        assert procedencia_metodologica("CLIP_INSTITUCIONAL") == (False, "")

    def test_o_ramo_positivo_existe_e_e_o_registro_que_o_liga(self):
        """`linha_azul.*` tem regra implementada — nenhum detector usa essa
        familia hoje, e e por isso que o placar da banda le zero. No dia em
        que o pacote implementar `absorcao.*`, o painel muda sozinho."""
        do_metodo, regra_id = procedencia_metodologica("LINHA_AZUL")
        assert do_metodo is True
        assert regra_id.startswith("linha_azul.")

    def test_a_linha_carrega_o_chip_e_o_tipo_fica_subordinado(self, matriz):
        matriz.aplicar(eventos=[deteccao(9, TipoDeteccao.EXAUSTAO)])
        pares = _pares_de(matriz)
        assert "GENÉRICO" in [t for _, t in pares]
        # O nome do tipo NAO sai em text-primary quando a regra e generica:
        # o veredito nunca pode ser mais forte que a sua ressalva.
        canetas = {c for c, t in pares if t == "EXAUSTÃO"}
        assert canetas == {tokens.TEXT_SECONDARY.name()}
        # E o chip e texto ESCURO sobre bloco cheio — a forma que sobrevive
        # ao canal, ao contrario de legenda apagada de 10px.
        assert {c for c, t in pares if t == "GENÉRICO"} == {tokens.BG_BASE.name()}

    def test_o_placar_da_banda_diz_quantas_sao_do_metodo(self, matriz):
        textos = _textos_de(matriz)
        assert "0 MÉTODO · 40 GENÉRICAS" in textos
        assert not any("na sessão" in t for t in textos)
        assert matriz.n_deteccoes_do_metodo == 0

    def test_as_duas_procedencias_sao_independentes(self, matriz):
        """Dado observado com regra generica e o caso mais comum, e era
        justamente o que a tela pintava como veredito do metodo."""
        item = item_de_deteccao(deteccao(0, inferida=False))
        assert item.inferida is False and item.do_metodo is False
        item2 = item_de_deteccao(deteccao(1, TipoDeteccao.ESCORA, inferida=True))
        assert item2.inferida is True and item2.do_metodo is False
        assert item2.regra_id == "escora.formula"


# --------------------------------------------------------------------------
# A lei do canal: ressalva no mesmo portador do numero
# --------------------------------------------------------------------------
class TestRessalvaNoMesmoPortador:
    """Medido nesta rodada: a transmissao PRESERVA o veredito e APAGA a
    ressalva, porque veredito e grande e saturado e ressalva e pequena e
    apagada. No retrato degradado sobreviveram `PASSA`, `+100,0%` e `NENHUM`;
    morreram `sem referência · valor assumido` e a regua de limiares.

    A regra que passa a valer: **se um numero tem ressalva, a ressalva viaja
    no mesmo portador do numero — mesma banda, mesmo corpo, mesma saturacao —
    ou o numero nao e publicado naquela forma.**

    O jeito de testar isso nao e olhar pixel: e afirmar que o numero e a
    ressalva saem no MESMO `drawText`, com a MESMA caneta. Assim nenhuma
    reescala, nenhuma quantizacao e nenhum recorte de coluna consegue
    entregar um sem o outro.
    """

    def test_dominancia_nao_confirmada_nunca_sai_sozinha(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            leitura(direcao=0, direcao_dominante=1, dominancia=1.0,
                    faixa=FaixaConviccao.MAXIMA_CONVICCAO, volume_sem_lado=0)
        )
        textos = _textos_de(painel)
        assert formato.MAIS + "100,0%" not in textos  # nunca a seco
        assert formato.MAIS + "100,0% NÃO CONFIRMADO" in textos

    def test_numero_e_ressalva_saem_com_a_mesma_caneta(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(direcao=0, direcao_dominante=1, dominancia=1.0))
        pares = _pares_de(painel)
        alvo = [(c, t) for c, t in pares if "NÃO CONFIRMADO" in t]
        assert len(alvo) == 1
        caneta, texto = alvo[0]
        assert texto.startswith(formato.MAIS + "100,0%")
        assert caneta == tokens.BUY.name()

    def test_rlp_relevante_qualifica_o_percentual_no_mesmo_texto(self, qapp):
        """Percentual calculado sobre 92% do tape nao e percentual do tape."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(volume_sem_lado=2_000, volume_total=25_000))
        textos = _textos_de(painel)
        assert formato.MAIS + "72,4% · 8% S/ LADO" in textos

    def test_rlp_desprezivel_nao_polui_a_leitura(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(volume_sem_lado=10, volume_total=25_000))
        assert formato.MAIS + "72,4%" in _textos_de(painel)

    def test_uma_ressalva_de_cada_vez(self, qapp):
        """Duas ressalvas competindo empurrariam uma para fora da coluna, e
        ressalva que nao cabe e ressalva que nao protege."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            leitura(direcao=0, direcao_dominante=1, dominancia=0.9,
                    volume_sem_lado=5_000, volume_total=25_000)
        )
        alvo = [t for t in _textos_de(painel) if t.startswith(formato.MAIS + "90,0%")]
        assert alvo == [formato.MAIS + "90,0% NÃO CONFIRMADO"]

    def test_veredito_de_magnitude_carrega_a_ressalva_na_propria_palavra(self, matriz):
        matriz.aplicar(leitura(magnitude_referencia=None, magnitude_fonte="nenhuma"))
        textos = _textos_de(matriz)
        assert "PASSA SEM MEDIR" in textos
        # `PASSA` sozinho nao existe nesse estado: nao ha como o canal
        # entregar o veredito limpo.
        assert "PASSA" not in textos
        assert "SEM REFERÊNCIA" in textos

    def test_com_referencia_o_veredito_volta_a_ser_limpo(self, matriz):
        textos = _textos_de(matriz)
        assert "PASSA" in textos
        assert "PASSA SEM MEDIR" not in textos
        assert "SEM REFERÊNCIA" not in textos

    def test_faixa_so_entra_se_couber_com_o_limiar_junto(self, qapp):
        """Meia faixa (`DIRECIONAL` sem o `≥70%`) seria a ressalva morrendo
        por falta de espaco. Entao ou entra inteira, ou nao entra."""
        estreito = _pronto(PainelMatriz(WDO_GRID), 380, 700)
        estreito.aplicar(leitura())
        textos = _textos_de(estreito)
        assert not any(t == "DIRECIONAL" for t in textos)
        for t in textos:
            if t.startswith("DIRECIONAL"):
                assert "≥70%" in t


# --------------------------------------------------------------------------
# Geometria — o que nenhum teste via
# --------------------------------------------------------------------------
def _cursor_do_eixo(painel) -> Pintado:
    """O cursor de 3px em `--text-primary` dentro do eixo de dominancia."""
    eixo = painel._eixo_dominancia()
    achados = [
        r
        for r in _pintura_de(painel).retangulos
        if r.largura == 3 and r.altura == eixo.height() and r.cor == tokens.TEXT_PRIMARY.name()
    ]
    assert len(achados) == 1, f"esperava um cursor, achei {len(achados)}"
    return achados[0]


def _zero_do_eixo(painel) -> int:
    """A linha de centro que o proprio painel desenha — o zero DESENHADO.

    Comparar contra ela, e nao contra uma coordenada copiada do codigo de
    producao, e o que faz o teste sobreviver a uma mudanca de layout e ainda
    assim reprovar uma inversao de lado.
    """
    eixo = painel._eixo_dominancia()
    centros = [
        r
        for r in _pintura_de(painel).retangulos
        if r.largura == 1 and r.altura == eixo.height() and r.cor == tokens.BORDER_STRONG.name()
    ]
    assert len(centros) == 1
    return centros[0].x


class TestGeometriaDoEixo:
    def test_o_cursor_fica_a_direita_do_zero_na_compra(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(direcao=1, direcao_dominante=1, dominancia=0.9))
        assert _cursor_do_eixo(painel).x > _zero_do_eixo(painel)

    def test_o_cursor_fica_a_esquerda_do_zero_na_venda(self, qapp):
        """Inverter o sinal de `sentido` em `_desenhar_eixo_dominancia`
        desenharia o cursor do lado errado e, ate a rodada 3, os testes
        continuariam todos verdes."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(direcao=-1, direcao_dominante=-1, dominancia=0.9))
        assert _cursor_do_eixo(painel).x < _zero_do_eixo(painel)

    def test_dominancia_maior_afasta_mais_o_cursor_do_zero(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(direcao=1, direcao_dominante=1, dominancia=0.6))
        perto = _cursor_do_eixo(painel).x - _zero_do_eixo(painel)
        painel.aplicar(leitura(direcao=1, direcao_dominante=1, dominancia=0.95))
        longe = _cursor_do_eixo(painel).x - _zero_do_eixo(painel)
        assert 0 < perto < longe

    def test_empate_deixa_o_cursor_no_zero(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            leitura(direcao=0, direcao_dominante=0, dominancia=0.5,
                    faixa=FaixaConviccao.LATERAL)
        )
        assert abs(_cursor_do_eixo(painel).x + 1 - _zero_do_eixo(painel)) <= 1

    def test_o_eixo_e_simetrico_nos_dois_sentidos(self, qapp):
        """Os dois lados partem do MESMO centro com o MESMO alcance — e a
        unica comparacao honesta, e o que §1/F5 cobra da referencia."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(direcao=1, direcao_dominante=1, dominancia=0.85))
        direita = _cursor_do_eixo(painel).x - _zero_do_eixo(painel)
        painel.aplicar(leitura(direcao=-1, direcao_dominante=-1, dominancia=0.85))
        esquerda = _zero_do_eixo(painel).__sub__(_cursor_do_eixo(painel).x)
        assert abs(direita - esquerda) <= 2


class TestGeometriaDasMedidas:
    def _barra_e_zero(self, painel, cor):
        pintura = _pintura_de(painel)
        banda = painel._bandas[mod.BANDA_MEDIDAS]
        na_banda = [r for r in pintura.retangulos if banda.top() <= r.y <= banda.bottom()]
        zeros = [r for r in na_banda if r.largura == 1 and r.cor == tokens.BORDER_STRONG.name()]
        barras = [r for r in na_banda if r.cor == cor and r.largura > 1]
        assert zeros and barras, "nao achei zero desenhado ou barra"
        return barras[0], zeros[0].x

    def test_delta_positivo_cresce_para_a_direita_do_zero(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(delta_sessao=1_500, delta_micro_antigo=0,
                               delta_micro_recente=0, agressao_saldo=0))
        cores = {c.name() for c in tokens.RAMPA_COMPRA}
        pintura = _pintura_de(painel)
        banda = painel._bandas[mod.BANDA_MEDIDAS]
        na_banda = [r for r in pintura.retangulos if banda.top() <= r.y <= banda.bottom()]
        zero = [r for r in na_banda if r.largura == 1 and r.cor == tokens.BORDER_STRONG.name()][0]
        barras = [r for r in na_banda if r.cor in cores and r.largura > 1]
        assert barras, "nenhuma barra compradora desenhada"
        assert all(b.x >= zero.x for b in barras)

    def test_delta_negativo_cresce_para_a_esquerda_do_zero(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(leitura(delta_sessao=-1_500, delta_micro_antigo=0,
                               delta_micro_recente=0, agressao_saldo=0))
        cores = {c.name() for c in tokens.RAMPA_VENDA}
        pintura = _pintura_de(painel)
        banda = painel._bandas[mod.BANDA_MEDIDAS]
        na_banda = [r for r in pintura.retangulos if banda.top() <= r.y <= banda.bottom()]
        zero = [r for r in na_banda if r.largura == 1 and r.cor == tokens.BORDER_STRONG.name()][0]
        barras = [r for r in na_banda if r.cor in cores and r.largura > 1]
        assert barras, "nenhuma barra vendedora desenhada"
        assert all(b.direita <= zero.x + 1 for b in barras)

    def test_sem_cor_a_posicao_continua_dizendo_o_lado(self, qapp):
        """No modo sem cor as duas rampas colapsam. Se a POSICAO nao
        carregasse o lado, a tela perderia a direcao — que e a propriedade
        que `PALETA_SEM_COR` existe para testar."""
        cores = {c.name() for c in tokens.RAMPA_NEUTRA}
        lados = {}
        for nome, valor in (("compra", 1_500), ("venda", -1_500)):
            painel = _pronto(PainelMatriz(WDO_GRID, paleta=tokens.PALETA_SEM_COR))
            painel.aplicar(leitura(delta_sessao=valor, delta_micro_antigo=0,
                                   delta_micro_recente=0, agressao_saldo=0))
            pintura = _pintura_de(painel)
            banda = painel._bandas[mod.BANDA_MEDIDAS]
            na_banda = [r for r in pintura.retangulos if banda.top() <= r.y <= banda.bottom()]
            zero = [r for r in na_banda
                    if r.largura == 1 and r.cor == tokens.BORDER_STRONG.name()][0]
            barras = [r for r in na_banda if r.cor in cores and r.largura > 1]
            assert barras
            lados[nome] = (barras[0], zero.x)
        assert lados["compra"][0].x >= lados["compra"][1]
        assert lados["venda"][0].direita <= lados["venda"][1] + 1


class TestGeometriaDaMagnitude:
    def _barra_e_gate(self, painel):
        pintura = _pintura_de(painel)
        banda = painel._bandas[mod.BANDA_MAGNITUDE]
        na_banda = [r for r in pintura.retangulos if banda.top() <= r.y <= banda.bottom()]
        trilhos = [r for r in na_banda if r.cor == tokens.BG_RAISED.name() and r.altura == 10]
        gates = [r for r in na_banda if r.largura == 1 and r.cor == tokens.ALERT.name()]
        assert len(trilhos) == 1 and len(gates) == 1
        return trilhos[0], gates[0]

    def test_a_marca_do_gate_fica_na_fracao_declarada(self, matriz):
        trilho, gate = self._barra_e_gate(matriz)
        esperado = trilho.x + int(
            matriz.config.magnitude_relativa_minima / ESCALA_MAGNITUDE * trilho.largura
        )
        assert abs(gate.x - esperado) <= 1

    def test_o_preenchimento_cresce_com_a_magnitude(self, qapp):
        larguras = []
        for valor in (0.4, 1.2):
            painel = _pronto(PainelMatriz(WDO_GRID))
            painel.aplicar(leitura(magnitude_relativa=valor, magnitude_referencia=10_000.0))
            pintura = _pintura_de(painel)
            banda = painel._bandas[mod.BANDA_MAGNITUDE]
            cores = {c.name() for c in tokens.RAMPA_COMPRA}
            preenchidos = [
                r for r in pintura.retangulos
                if banda.top() <= r.y <= banda.bottom() and r.cor in cores
            ]
            assert preenchidos
            larguras.append(max(r.largura for r in preenchidos))
        assert larguras[0] < larguras[1]

    def test_sem_referencia_a_calha_fica_vazia(self, matriz):
        """A ressalva tambem e GEOMETRICA: nao ha barra para o canal
        preservar, so a calha e a marca do gate."""
        matriz.aplicar(leitura(magnitude_referencia=None, magnitude_fonte="nenhuma"))
        pintura = _pintura_de(matriz)
        banda = matriz._bandas[mod.BANDA_MAGNITUDE]
        cores = {c.name() for c in tokens.RAMPA_COMPRA} | {c.name() for c in tokens.RAMPA_VENDA}
        assert not [
            r for r in pintura.retangulos
            if banda.top() <= r.y <= banda.bottom() and r.cor in cores
        ]


class TestGeometriaDasDeteccoes:
    def test_a_barra_de_confianca_varia_com_a_confianca(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(eventos=[deteccao(0, inferida=True), deteccao(1, inferida=False)])
        pintura = _pintura_de(painel)
        barras = [
            r for r in pintura.retangulos
            if r.x == COL_CONF_BARRA
            and r.cor in {tokens.ALERT.name(), tokens.NEUTRAL.name()}
        ]
        assert len(barras) == 2
        # 0,55 e 1,00 nao podem sair com a MESMA largura — era exatamente o
        # que o critico mediu: 32px identicos em todas as linhas.
        assert len({b.largura for b in barras}) == 2
        assert max(b.largura for b in barras) == 32

    def test_a_regua_de_excecao_marca_so_a_linha_rara(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            eventos=[deteccao(i, TipoDeteccao.EXAUSTAO) for i in range(60)]
            + [deteccao(99, TipoDeteccao.CLIP_INSTITUCIONAL)]
        )
        pintura = _pintura_de(painel)
        reguas = [
            r for r in pintura.retangulos
            if r.x == 0 and r.largura == 3 and r.cor == tokens.ABSORPTION.name()
        ]
        assert len(reguas) == 1, f"esperava uma regua de excecao, achei {len(reguas)}"
        # E ela esta na PRIMEIRA linha, que e onde a rara entrou.
        assert reguas[0].y == painel._area_slots.top()

    def test_sem_excecao_nenhuma_linha_e_marcada(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(eventos=[deteccao(i, TipoDeteccao.EXAUSTAO) for i in range(60)])
        pintura = _pintura_de(painel)
        assert not [
            r for r in pintura.retangulos
            if r.x == 0 and r.largura == 3 and r.cor == tokens.ABSORPTION.name()
        ]

    def test_a_raridade_e_congelada_na_chegada(self, qapp):
        """Recalcular faria a tela reescrever o passado — e obrigaria a
        repintar a banda inteira a cada evento, matando o `rolar()`."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            eventos=[deteccao(i, TipoDeteccao.ESCORA) for i in range(mod.MIN_AMOSTRAS_RARIDADE)]
        )
        marco = painel.deteccoes_visiveis[0]
        assert marco.fracao_tipo == 1.0
        painel.aplicar(eventos=[deteccao(i, TipoDeteccao.EXAUSTAO) for i in range(9)])
        assert painel.deteccoes_visiveis[9] is marco
        assert marco.fracao_tipo == 1.0
        # E as que chegaram depois carimbaram a fatia do SEU instante.
        recente = painel.deteccoes_visiveis[0]
        assert recente.fracao_tipo == 9 / (mod.MIN_AMOSTRAS_RARIDADE + 9)

    def test_a_contagem_por_tipo_e_limitada_pelo_numero_de_TIPOS(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        for i in range(2_000):
            painel.aplicar(eventos=[deteccao(i, TipoDeteccao.EXAUSTAO)])
        assert len(painel._por_tipo) == 1
        painel.aplicar(eventos=[deteccao(1, TipoDeteccao.ESCORA)])
        assert len(painel._por_tipo) == 2


class TestCabecalhoDeColuna:
    def test_toda_coluna_tem_rotulo(self, largo):
        textos = _textos_de(largo)
        for _, rotulo in mod.ROTULOS_COLUNA:
            assert rotulo in textos, f"coluna sem rotulo: {rotulo}"

    def test_rotulo_que_nao_cabe_SAI_em_vez_de_truncar(self, qapp):
        """F8: `Qtd Co…`, `Classifi…`, `22:rrelevant`. Coluna truncada e pior
        que coluna ausente — a primeira mente, a segunda so falta."""
        estreito = _pronto(PainelMatriz(WDO_GRID), 380, 460)
        estreito.aplicar(leitura(), eventos=[deteccao(1)])
        textos = _textos_de(estreito)
        assert "REGRA" in textos
        assert "FATIA À CHEGADA" not in textos
        for t in textos:
            assert "…" not in t

    def test_o_rotulo_diz_que_a_fatia_e_do_INSTANTE(self, largo):
        """`NA SESSÃO` seria lido como "agora" e a coluna mistura epocas de
        proposito — cada linha carrega a fatia que existia quando ela
        chegou."""
        assert "FATIA À CHEGADA" in _textos_de(largo)

    def test_a_ordenacao_e_declarada(self, largo):
        """"Mais recente no topo" e convencao, nao fato evidente: o tape usa
        essa, o livro nao."""
        assert "HORA ▼" in _textos_de(largo)

    def test_os_rotulos_usam_as_MESMAS_colunas_que_as_linhas(self):
        """Se cabecalho e linha calculassem posicao por conta propria, a
        primeira mudanca de largura desalinharia rotulo e dado — a forma mais
        barata de mentir numa tabela."""
        xs = [x for x, _ in mod.ROTULOS_COLUNA]
        assert xs == sorted(xs)
        assert mod.COL_REGRA in xs and mod.COL_RARIDADE in xs


class TestProporcaoDaSuperficie:
    """A banda ocupava 60% da tela — e era a unica cuja procedencia o
    registro nao avaliza."""

    def test_o_teto_de_slots_caiu(self):
        assert MAX_SLOTS_DETECCAO == 10

    def test_a_banda_nao_domina_mais_a_superficie(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID), 620, 460)
        banda = painel._bandas[mod.BANDA_DETECCOES]
        assert banda.height() / painel.height() < 0.5

    def test_janela_gigante_nao_estica_a_banda_alem_do_teto(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID), 900, 4_000)
        assert painel._n_slots == MAX_SLOTS_DETECCAO


class TestProcedenciaDasBandas:
    """A procedencia de uma banda e DERIVADA, e o que a UI declara sao os
    botoes do motor — nunca ids de regra.

    A versao anterior tinha `REGRAS_DA_BANDA`, um `dict` banda -> regra
    digitado a mao e constrangido por um unico teste que era tautologia sobre
    um literal. Trocar a regra do farol por `risco.mao_cheia` — tamanho de
    posicao — deixava a suite inteira verde, e o farol exibia chip verde
    `§ CONFIRMADO` enquanto a banda MEDIDAS, movida pelo MESMO
    `janela_micro_ns`, exibia ambar. Duas bandas, o mesmo parametro sem
    fonte, chips contraditorios na mesma tela.

    Os testes desta classe existem para que essa classe de erro nao volte a
    ser expressavel.
    """

    def _pior(self, painel, banda: int) -> str:
        return painel._procedencia_de(mod.CAMPOS_DA_BANDA[banda])[0]

    def test_a_ui_nao_escreve_id_de_regra_nenhum(self):
        """O invariante que a rodada anterior violou por 370 linhas."""
        import inspect

        fonte = inspect.getsource(mod)
        for identificador in REGRAS:
            for linha in fonte.splitlines():
                codigo = linha.split("#")[0]
                if '"""' in linha or linha.strip().startswith("*"):
                    continue
                assert f'"{identificador}"' not in codigo, (
                    f"id de regra digitado na UI: {linha.strip()!r}"
                )

    def test_todo_campo_declarado_e_campo_real_do_motor(self):
        reais = {f.name for f in dataclasses.fields(ConfigMotorSinais)}
        for banda, campos in mod.CAMPOS_DA_BANDA.items():
            assert campos, f"banda {banda} sem parametro"
            assert set(campos) <= reais, f"banda {banda}: nome inexistente"

    def test_nome_inventado_derruba_o_import(self):
        original = dict(mod.CAMPOS_DA_BANDA)
        mod.CAMPOS_DA_BANDA[mod.BANDA_MEDIDAS] = ("nao_existe",)
        try:
            with pytest.raises(ValueError):
                mod._validar_campos()
        finally:
            mod.CAMPOS_DA_BANDA.clear()
            mod.CAMPOS_DA_BANDA.update(original)

    def test_os_campos_declarados_sao_EXATAMENTE_os_que_o_motor_le(self):
        """Lido de `motor/sinais.py` com `ast`, e nao copiado.

        Botao novo no motor sem procedencia na tela reprova; nome morto na
        tela reprova. E o que impede a declaracao de envelhecer em silencio —
        que foi o defeito exato da versao anterior.
        """
        import ast

        arvore = ast.parse(
            pathlib.Path("fluxopro/motor/sinais.py").read_text(encoding="utf-8")
        )
        lidos = set()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Attribute):
                continue
            base = no.value
            if isinstance(base, ast.Name) and base.id == "cfg":
                lidos.add(no.attr)
            elif (
                isinstance(base, ast.Attribute)
                and base.attr == "config"
                and isinstance(base.value, ast.Name)
                and base.value.id == "self"
            ):
                lidos.add(no.attr)
        reais = {f.name for f in dataclasses.fields(ConfigMotorSinais)}
        lidos &= reais
        declarados = set()
        for campos in mod.CAMPOS_DA_BANDA.values():
            declarados |= set(campos)
        assert declarados == lidos, (
            f"so na tela: {sorted(declarados - lidos)}; "
            f"so no motor: {sorted(lidos - declarados)}"
        )

    def test_o_farol_engloba_todas_as_outras_bandas(self, largo):
        """O estagio E a confluencia: qualquer botao que mova outra banda move
        o farol tambem. Por isso o conjunto dele e superconjunto."""
        farol = set(mod.CAMPOS_DA_BANDA[mod.BANDA_ESTAGIO])
        for banda, campos in mod.CAMPOS_DA_BANDA.items():
            assert set(campos) <= farol, f"banda {banda} tem botao fora do farol"

    def test_o_farol_nunca_afirma_mais_que_qualquer_outra_banda(self, largo):
        """**O teste que teria pego o defeito.**

        O farol exibia `§ CONFIRMADO` verde logo acima de um `§ S/ FONTE`
        ambar movido pelo mesmo parametro. Como o conjunto do farol e
        superconjunto, a gravidade dele tem de ser >= a de todas — e no canal
        degradado, onde o que sobrevive e o chip grande e saturado, isso e a
        diferenca entre uma auditoria e um selo falso.
        """
        def gravidade(banda):
            campos = mod.CAMPOS_DA_BANDA[banda]
            pior = mod.Confianca.CONFIRMADO
            for campo in campos:
                ids = mod.regras_do_campo(campo)
                if not ids:
                    return 99
                for i in ids:
                    c = REGRAS[i].confianca
                    if mod._GRAVIDADE[c] > mod._GRAVIDADE[pior]:
                        pior = c
            return mod._GRAVIDADE[pior]

        farol = gravidade(mod.BANDA_ESTAGIO)
        for banda in mod.CAMPOS_DA_BANDA:
            assert farol >= gravidade(banda)

    def test_a_regra_vem_do_registro_pelo_nome_QUALIFICADO(self):
        """`janela_micro_ns` existe em `ConfigMotorSinais` e em
        `ConfigMacroMicro`. Casar pelo nome curto faria a tela reivindicar um
        aval que `macro_micro.janela_micro` deu a OUTRO componente."""
        assert mod.regras_do_campo("dominancia_minima") == (
            "dominancia.limiar_direcional",
        )
        assert mod.regras_do_campo("janela_micro_ns") == ()
        assert mod.regras_do_campo("magnitude_relativa_minima") == ()

    def test_a_dominancia_declara_o_corte_disputado(self, largo):
        """Tirar `dominancia_minima` da dominancia — a mutacao analoga a que
        derrubou a versao anterior — muda o chip, porque ele e derivado."""
        assert "dominancia_minima" in mod.CAMPOS_DA_BANDA[mod.BANDA_DOMINANCIA]
        assert self._pior(largo, mod.BANDA_DOMINANCIA).endswith(" 1/5")
        sem = tuple(
            c for c in mod.CAMPOS_DA_BANDA[mod.BANDA_DOMINANCIA] if c != "dominancia_minima"
        )
        assert largo._procedencia_de(sem)[0].endswith(" 0/4")

    def test_o_chip_publica_a_COBERTURA_junto_com_a_confianca(self, largo):
        """Duas grandezas numa string so: separa-las deixaria o canal entregar
        uma sem a outra — a lei da rodada 2 aplicada a auditoria."""
        textos = _textos_de(largo)
        assert "§ S/ REGISTRO 1/20" in textos   # farol
        assert "§ S/ REGISTRO 1/5" in textos    # dominancia
        assert "§ S/ REGISTRO 0/7" in textos    # magnitude
        assert "§ S/ REGISTRO 0/2" in textos    # medidas

    def test_nenhuma_banda_do_motor_afirma_CONFIRMADO_hoje(self, largo):
        """Com o registro atual, `dominancia_minima` e o UNICO botao de
        `ConfigMotorSinais` coberto. Verde nesta tela seria mentira."""
        for banda in mod.CAMPOS_DA_BANDA:
            assert "CONFIRMADO" not in self._pior(largo, banda)

    def test_a_marca_separa_procedencia_de_estagio(self, largo):
        """`CONFIRMADO` e o ultimo ESTAGIO do motor E o rotulo de maior
        confianca do registro; os dois apareciam na mesma banda."""
        textos = _textos_de(largo)
        assert "CONFIRMADO" in textos                      # o estagio, no trilho
        assert textos.count("CONFIRMADO") == 1
        assert any(t.startswith(mod.MARCA_REGRA) for t in textos)

    def test_o_gate_de_magnitude_nao_toma_emprestado_aval_alheio(self, largo):
        """`velocimetro.normalizacao_winfut` e CONFIRMADO e trata do mesmo
        fenomeno — mas e outro componente, com outro default (0,25 contra
        0,60). O registro nao liga o 0,60 a regra nenhuma, e a tela diz isso
        em vez de emprestar o aval."""
        assert "magnitude_relativa_minima" in mod.CAMPOS_DA_BANDA[mod.BANDA_MAGNITUDE]
        assert mod.regras_do_campo("magnitude_relativa_minima") == ()
        assert self._pior(largo, mod.BANDA_MAGNITUDE) == "§ S/ REGISTRO 0/7"


class TestAquecimentoDaFatia:
    """`fatia = n/total` faz a PRIMEIRA deteccao sair 100%.

    Nenhuma das cinco primeiras conseguia cruzar `FRACAO_RARA = 0,20`, entao
    um `CLIP_INSTITUCIONAL` isolado na abertura — o evento mais raro que a
    tela pode receber — aparecia como a coisa mais comum do painel.
    """

    def test_antes_da_amostra_minima_a_fatia_nao_e_publicada(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(eventos=[deteccao(0, TipoDeteccao.CLIP_INSTITUCIONAL)])
        assert painel.deteccoes_visiveis[0].fracao_tipo < 0.0
        assert "—" in _textos_de(painel)
        assert not any(t.endswith("%") and t[0].isdigit() for t in _textos_de(painel)
                       if t.rstrip("%").isdigit())

    def test_no_aquecimento_ninguem_e_marcado_como_excecao(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(eventos=[deteccao(0, TipoDeteccao.CLIP_INSTITUCIONAL)])
        pintura = _pintura_de(painel)
        assert not [
            r for r in pintura.retangulos
            if r.x == 0 and r.largura == 3 and r.cor == tokens.ABSORPTION.name()
        ]

    def test_depois_da_amostra_minima_a_fatia_volta(self, qapp):
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            eventos=[deteccao(i, TipoDeteccao.EXAUSTAO)
                     for i in range(mod.MIN_AMOSTRAS_RARIDADE)]
        )
        assert painel.deteccoes_visiveis[0].fracao_tipo == 1.0

    def test_so_a_linha_rara_ganha_tinta(self, qapp):
        """A primeira versao pintava a barra proporcional a fatia: a linha com
        MAIS tinta era a do tipo mais COMUM, e a excecao ficava com o tracinho
        mais curto — o oposto do que a coluna existe para fazer."""
        painel = _pronto(PainelMatriz(WDO_GRID))
        painel.aplicar(
            eventos=[deteccao(i, TipoDeteccao.EXAUSTAO) for i in range(60)]
            + [deteccao(99, TipoDeteccao.CLIP_INSTITUCIONAL)]
        )
        pintura = _pintura_de(painel)
        preenchidos = [
            r for r in pintura.retangulos
            if r.x == mod.COL_RARIDADE and r.cor == tokens.ABSORPTION.name()
        ]
        assert len(preenchidos) == 1
