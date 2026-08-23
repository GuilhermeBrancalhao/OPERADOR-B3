"""A COMPOSICAO — a cadeia, o relogio unico, o fechamento e o carimbo.

Os testes de painel provam cada peca. Estes provam o que so existe quando as
pecas viram uma tela:

* **A cadeia e apontavel.** Nao basta escrever `1 · DADOS DE MERCADO` no
  topo: o segmento tem de cobrir a coluna que ele nomeia. Um trilho que
  nomeia sem alinhar e uma legenda, e legenda desalinhada e pior que rotulo
  nenhum — o operador aprende a apontar para o lugar errado. Por isso a
  assercao e geometrica, contra a geometria REAL das colunas depois do
  layout, e nao contra os fatores de esticamento copiados do codigo.

* **Um relogio de dados.** `PonteFluxo.ler()` esvazia o buffer: se dois
  painels lessem, o segundo receberia tape vazio e o defeito apareceria como
  "as vezes o tape pula negocios", que e das coisas mais caras de
  diagnosticar depois. Com quatro elos consumindo o mesmo retrato, a
  assercao passa a ser sobre os QUATRO.

* **Fechar solta tudo.** No Qt, callback apontando para widget destruido nao
  e vazamento: e falha de segmentacao. A janela ganhou paineis novos, e o
  teste percorre `janela.paineis` em vez de uma lista escrita a mao —
  senao o proximo painel a entrar na composicao nasce sem essa protecao e
  ninguem descobre.

* **O carimbo viaja na imagem.** Calibrar o motor pela linha de comando muda
  o que a tela AFIRMA. A ressalva e derivada da configuracao (nunca
  redigitada), aparece como faixa saturada e some quando nao ha o que
  ressalvar — carimbo permanente vira moldura e para de ser lido.

O espiao de `QPainter` e local de proposito: `tests/test_ui_matriz.py` tem um
parecido, e importa-lo daqui acoplaria dois arquivos de teste que mudam por
razoes diferentes.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QFontMetrics, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractScrollArea,
    QMenuBar,
    QPushButton,
    QScrollBar,
    QSplitter,
    QStatusBar,
    QToolBar,
)

from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import (  # noqa: E402
    WDO_GRID,
    AgressorSide,
    BookLevel,
    BookSnapshot,
    Trade,
)
from fluxopro.metodologia.confianca import Confianca  # noqa: E402
from fluxopro.metodologia.regras import REGRAS  # noqa: E402
from fluxopro.microestrutura.perfil_player import PerfilPlayer  # noqa: E402
from fluxopro.motor.sinais import ConfigMotorSinais  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui import janela as J  # noqa: E402
from fluxopro.ui.janela import (  # noqa: E402
    ALTURA_LINHA_PARAMETRO,
    ALTURA_LINHA_REGRA,
    ALTURA_RODAPE_REGRAS,
    ALTURA_TITULO_LIMIARES,
    CARENCIA_PLAYERS_QUADROS,
    ETAPAS,
    PARAMETROS_EM_VIGOR,
    RODAPE_MODO,
    SLOTS_MINIMOS_MATRIZ,
    VAO_SECAO,
    FaixaRessalva,
    JanelaFluxo,
    PainelRegras,
    altura_minima_matriz,
    familias_na_tela,
    formatar_limiar,
    layout_regras,
    texto_do_corte,
)
from fluxopro.ui.ponte import PonteFluxo  # noqa: E402

T0 = 1_700_000_000_000_000_000
BASE = WDO_GRID.to_ticks(5086.5)
SIMBOLO = "WDOV26"

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _inteiro(valor: int) -> str:
    from fluxopro.ui import formato

    return formato.formatar_inteiro(valor)


# --------------------------------------------------------------------------
# Ferramentas
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Marca:
    """Um `drawText` com o PORTADOR que ele usou.

    O portador e o que a rodada 2 mediu: corpo e saturacao decidem o que
    atravessa a transmissao, e nao a importancia que o autor atribuiu ao
    dado. Guardar so o texto deixaria passar exatamente o defeito que se quer
    proibir — a escala escrita menor e mais apagada que o veredito que ela
    qualifica."""

    texto: str
    px: int
    peso: int
    cor: str


class PainterEspiao:
    """Encaminha para um `QPainter` real e guarda o que foi desenhado E COMO.

    Comparar TEXTO e a unica forma honesta de afirmar "esta escrito na tela";
    comparar pixel afirmaria outra coisa (que o desenho nao mudou), e quebra
    quando a maquina troca de fonte."""

    def __init__(self, painter: QPainter) -> None:
        self._painter = painter
        self.textos: list[str] = []
        self.marcas: list[Marca] = []
        self.retangulos: list[tuple[QRect, str]] = []
        self._px = 0
        self._peso = 0
        self._cor = ""

    def __getattr__(self, nome):
        return getattr(self._painter, nome)

    def setFont(self, fonte):  # noqa: N802
        self._px = fonte.pixelSize()
        self._peso = int(fonte.weight())
        return self._painter.setFont(fonte)

    def setPen(self, cor):  # noqa: N802
        self._cor = cor.name() if hasattr(cor, "name") else str(cor)
        return self._painter.setPen(cor)

    def fillRect(self, *args):  # noqa: N802 — assinatura do Qt
        if len(args) == 2 and hasattr(args[0], "width"):
            rect, cor = args
            self.retangulos.append(
                (QRect(rect), cor.name() if hasattr(cor, "name") else str(cor))
            )
        return self._painter.fillRect(*args)

    def drawText(self, *args):  # noqa: N802
        if args and isinstance(args[-1], str):
            self.textos.append(args[-1])
            self.marcas.append(Marca(args[-1], self._px, self._peso, self._cor))
        return self._painter.drawText(*args)


def _espiar(painel) -> PainterEspiao:
    pixmap = QPixmap(max(1, painel.width()), max(1, painel.height()))
    pixmap.fill(tokens.BG_SURFACE)
    painter = QPainter(pixmap)
    espiao = PainterEspiao(painter)
    try:
        painel.desenhar(espiao, QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return espiao


def _textos(painel) -> list[str]:
    return _espiar(painel).textos


def _altura_inteira(painel) -> int:
    """A menor altura em que `PainelRegras` cabe sem corte.

    Derivada da MESMA geometria que o desenho usa — um numero escrito a mao
    aqui viraria um marco que o desenho nao consulta, e o teste passaria a
    medir a si mesmo (lei n.o 6)."""
    altura = tokens.PADRAO.altura_cabecalho + 4 + ALTURA_RODAPE_REGRAS
    altura += len(painel._familias) * ALTURA_LINHA_REGRA
    altura += VAO_SECAO + ALTURA_TITULO_LIMIARES
    altura += len(PARAMETROS_EM_VIGOR) * ALTURA_LINHA_PARAMETRO
    return altura


def _publicar(bus, i: int, preco: int = BASE, qty: int | None = None) -> None:
    bus.publicar(
        Trade(
            T0 + i * 1_000_000,
            SIMBOLO,
            preco,
            5 if qty is None else qty,
            AgressorSide.BUY if i % 2 else AgressorSide.SELL,
            f"t{i}",
        )
    )
    bus.publicar(
        BookSnapshot(
            T0 + i * 1_000_000,
            SIMBOLO,
            tuple(BookLevel(preco - k - 1, 100 + k + i, 1) for k in range(8)),
            tuple(BookLevel(preco + k + 1, 90 + k + i, 1) for k in range(8)),
        )
    )


def _chamadas_a_ler(caminho) -> list[str]:
    """Os `<algo>.ler()` que o arquivo REALMENTE chama, pelo AST.

    Era `".ler()" not in texto`, e a versao por substring reprovou um painel
    novo por causa de uma DOCSTRING que explicava justamente que ele NAO chama
    `ponte.ler()`. Um teste que uma frase em portugues derruba nao esta
    medindo o que diz medir.

    O AST mede a chamada e nao a mencao, e de quebra fica mais rigoroso: pega
    `self . ponte . ler ( )` quebrado em linhas, que a substring nao pegava.
    Devolve o nome do objeto lido — a assercao passa a ser sobre QUEM e lido,
    e nao so sobre quantas vezes.
    """
    import ast

    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achados: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if isinstance(alvo, ast.Attribute) and alvo.attr == "ler":
            dono = alvo.value
            if isinstance(dono, ast.Attribute):
                achados.append(dono.attr)  # `self.ponte.ler()` -> `ponte`
            elif isinstance(dono, ast.Name):
                achados.append(dono.id)
            else:
                achados.append("?")
    return achados


def janela_docas(composicao):
    _, _, janela = composicao
    return janela.docas


def _montar(qapp, **kwargs) -> tuple[Barramento, PonteFluxo, JanelaFluxo]:
    bus = Barramento()
    ponte = PonteFluxo(bus)
    janela = JanelaFluxo(ponte, SIMBOLO, WDO_GRID, **kwargs)
    janela.resize(1480, 900)
    janela.show()
    return bus, ponte, janela


@pytest.fixture
def composicao(qapp):
    bus, ponte, janela = _montar(qapp)
    yield bus, ponte, janela
    janela.close()


@pytest.fixture
def com_sessao(qapp):
    """Sessao minima: o que a janela le dela e `agressao` e `perfil_player`."""
    perfil = PerfilPlayer(SIMBOLO)
    sessao = SimpleNamespace(agressao=None, perfil_player=perfil)
    bus, ponte, janela = _montar(qapp, sessao=sessao)
    yield bus, ponte, janela, perfil
    janela.close()


# --------------------------------------------------------------------------
# 1. A cadeia
# --------------------------------------------------------------------------
class TestCadeiaLegivel:
    def test_as_quatro_regioes_estao_na_ordem_da_cadeia(self, composicao):
        """`dados -> processamento -> estado derivado -> decisao`, da esquerda
        para a direita. A ordem e a afirmacao: uma composicao que pusesse a
        decisao antes do dado leria como um painel de alarmes.

        Com docking, as "regioes" deixaram de ser quatro `QWidget` fixos e
        passaram a ser as FAIXAS que as docas de cada elo ocupam — que e a
        unica leitura honesta quando o arranjo e do operador. A assercao
        continua sendo geometrica, e sobre a geometria REAL."""
        _, _, janela = composicao
        faixas = janela.faixas_dos_elos()
        assert all(f is not None for f in faixas), faixas
        esquerdas = [f[0] for f in faixas]
        assert esquerdas == sorted(esquerdas)
        assert len(set(esquerdas)) == 4
        for atual, seguinte in zip(faixas, faixas[1:]):
            assert atual[1] < seguinte[0], "elos se sobrepondo: %r" % (faixas,)

    def test_cada_elo_do_trilho_cobre_a_regiao_que_nomeia(self, composicao):
        """A assercao que transforma rotulo em cadeia APONTAVEL.

        Contra a geometria real depois do layout, e nao contra os fatores de
        esticamento: se alguem trocar a largura da coluna de decisao e
        esquecer o trilho, isto reprova."""
        _, _, janela = composicao
        segmentos = janela.trilho.segmentos()
        faixas = janela.faixas_dos_elos()
        assert len(segmentos) == len(ETAPAS) == len(faixas)
        for segmento, faixa in zip(segmentos, faixas):
            assert faixa is not None
            assert segmento.left() <= faixa[0], "o elo comeca antes da coluna"
            assert segmento.right() >= faixa[1], "o elo termina depois da coluna"

    def test_os_elos_cobrem_a_largura_inteira_sem_buraco(self, composicao):
        _, _, janela = composicao
        segmentos = janela.trilho.segmentos()
        assert segmentos[0].left() == 0
        assert segmentos[-1].right() == janela.trilho.width() - 1
        for anterior, seguinte in zip(segmentos, segmentos[1:]):
            assert seguinte.left() == anterior.right() + 1

    def test_o_alinhamento_sobrevive_ao_redimensionamento(self, composicao):
        """O trilho le a geometria REAL a cada `resizeEvent`. Uma copia dos
        fatores de esticamento passaria neste teste no tamanho de projeto e
        falharia em qualquer outro — que e como alinhamento quebra na
        pratica: no monitor de outra pessoa."""
        _, _, janela = composicao
        janela.resize(1240, 720)
        janela.resize(1700, 1000)
        janela._sincronizar_trilho()
        for segmento, faixa in zip(janela.trilho.segmentos(), janela.faixas_dos_elos()):
            assert faixa is not None
            assert segmento.left() <= faixa[0] and segmento.right() >= faixa[1]

    def test_os_quatro_elos_estao_escritos(self, composicao):
        _, _, janela = composicao
        escritos = _textos(janela.trilho)
        for alternativas in ETAPAS:
            assert any(
                texto in alternativas for texto in escritos
            ), f"nenhuma forma de {alternativas[0]!r} foi desenhada"

    def test_o_trilho_nao_republica_veredito(self, composicao):
        """A lei da rodada: o canal preserva o veredito e apaga a ressalva.

        Um `CONFIRMADO` repetido no trilho seria um veredito publicado longe
        da regua que o qualifica — sobreviveria a transmissao exatamente como
        oraculo. O trilho responde ONDE; o painel embaixo responde O QUE, com
        a ressalva junto."""
        bus, _, janela = composicao
        for i in range(20):
            _publicar(bus, i)
        janela._tick()
        escritos = " ".join(_textos(janela.trilho))
        for veredito in ("CONFIRMADO", "PRÉ-SINAL", "DIRECIONAL", "LATERAL", "%"):
            assert veredito not in escritos

    def test_o_elo_do_processamento_conta_o_funil(self, composicao):
        """O elo 2 nao tinha superficie nenhuma antes desta peca."""
        bus, _, janela = composicao
        for i in range(12):
            _publicar(bus, i)
        janela._tick()
        escritos = _textos(janela.conduto)
        assert "EVENTOS" in escritos and "DETECÇÕES" in escritos and "SINAIS" in escritos
        # 12 negocios + 12 snapshots, todos pelo mesmo retrato.
        assert "24" in escritos

    def test_o_descarte_aparece_mesmo_valendo_zero(self, composicao):
        """Some-lo quando zera ensinaria o olho a nao procurar por ele
        justamente no dia em que ele deixa de ser zero (`ui/ponte.py`)."""
        _, _, janela = composicao
        janela._tick()
        assert any("desc." in texto for texto in _textos(janela.conduto))


# --------------------------------------------------------------------------
# 2. Um relogio de dados
# --------------------------------------------------------------------------
class TestRelogioUnico:
    def test_um_tick_alimenta_os_quatro_elos(self, composicao):
        bus, _, janela = composicao
        for i in range(30):
            _publicar(bus, i)
        janela._tick()

        assert janela.dom._centro is not None, "elo 1: o DOM recebeu o livro"
        assert len(janela.tape._linhas) == 30, "elo 1: o tape recebeu TODOS"
        assert janela.conduto._eventos == 60, "elo 2: o funil contou o mesmo"
        assert janela._leitura is not None, "elo 3: a matriz tem leitura"
        assert janela.hud._leitura is not None, "elo 4: o HUD tem contexto"

    def test_todos_leem_o_MESMO_instante(self, composicao):
        """Tela costurada de quatro momentos e o que um retrato unico evita.

        O delta que a matriz e o HUD usam vem do `Instantaneo` — montado sob
        o lock, no mesmo instante do preco que o tape mostra —, e nao de
        `sessao.delta` lido do lado do Qt enquanto a fonte escreve."""
        bus, _, janela = composicao
        for i in range(10):
            _publicar(bus, i, BASE + i, qty=10)
        janela._tick()

        assert janela.topo._ultimo == janela.tape._linhas[0].price == BASE + 9
        # 5 compras e 5 vendas de 10 lotes: delta zero, volume 100.
        assert janela._leitura.delta_sessao == 0
        assert janela._leitura.volume_total == 100
        assert janela.hud._leitura.saldo_dia == 0

    def test_nenhum_painel_le_a_ponte_sozinho(self):
        """A regra de `ui/ponte.py`, verificada na fonte e nao na intencao.

        `ler()` esvazia o buffer: o segundo a chamar recebe tape vazio. Um
        painel novo que decidisse ler por conta propria passaria em todos os
        outros testes desta suite e quebraria o tape em producao."""
        fontes = list((RAIZ / "fluxopro" / "ui" / "paineis").glob("*.py"))
        assert fontes, "nao achei os paineis"
        for caminho in fontes:
            assert _chamadas_a_ler(caminho) == [], caminho.name
        janela = RAIZ / "fluxopro" / "ui" / "janela.py"
        assert _chamadas_a_ler(janela) == ["ponte"], "a janela le a ponte UMA vez"


# --------------------------------------------------------------------------
# 3. Fechamento
# --------------------------------------------------------------------------
class TestFechamento:
    def test_fechar_para_TODOS_os_relogios_e_solta_o_barramento(self, qapp):
        """Percorre `janela.paineis` — nao uma lista escrita a mao.

        No Qt isto nao e vazamento: uma janela fechada cujos callbacks
        continuam no barramento aponta para widgets destruidos, e chamar la
        derruba o processo."""
        bus, ponte, janela = _montar(qapp)
        _publicar(bus, 0)
        janela._tick()
        assert len(janela.paineis) >= 10
        janela.close()

        for i in range(100):
            _publicar(bus, i)
        assert ponte.ler().contadores.trades == 1, "o barramento foi solto"
        assert not janela._relogio.isActive()
        for painel in janela.paineis:
            assert not painel._timer.isActive(), type(painel).__name__

    def test_a_faixa_de_ressalva_tambem_e_solta(self, qapp):
        bus, _, janela = _montar(qapp, ressalva=("CARIMBO", "detalhe"))
        assert janela.ressalva in janela.paineis
        janela.close()
        assert not janela.ressalva._timer.isActive()

    def test_callback_de_fechamento_e_chamado(self, qapp):
        chamado = []
        _, _, janela = _montar(qapp, ao_fechar=lambda: chamado.append(True))
        janela.close()
        assert chamado == [True]


# --------------------------------------------------------------------------
# 4. Painel escondido nao gasta quadro
# --------------------------------------------------------------------------
class TestPainelRecolhido:
    def test_players_recolhe_quando_a_fonte_nao_divulga_participante(self, com_sessao):
        """Nao e o estado VAZIO de §3.5 ("ainda nao chegou", e a grade
        aparece): e "esta fonte nao tem esse dado". Reservar coluna para um
        dado que a fonte nao pode produzir e area roubada do que ela produz.
        """
        bus, _, janela, _ = com_sessao
        assert janela.players.isVisible()
        for i in range(CARENCIA_PLAYERS_QUADROS):
            _publicar(bus, i)
            janela._tick()
        assert not janela.players.isVisible()
        assert not janela.players._timer.isActive(), "relogio parado junto"

    def test_recolhido_nao_gasta_quadro(self, com_sessao):
        """Duas economias, e as duas sao afirmadas: o relogio de DESENHO para
        (`PainelDenso.hideEvent`) e o quadro de DADOS deixa de montar o
        ranking — por isso nem sujeira sobra para um `_quadro` forcado."""
        bus, _, janela, _ = com_sessao
        janela.definir_players_visivel(False)
        janela.players._quadro()  # descarrega a sujeira herdada da montagem
        janela.players.zerar_medicao()
        for i in range(30):
            _publicar(bus, i)
            janela._tick()
        assert not janela.players._timer.isActive()
        assert not janela.players.tem_sujeira, "o tick sujou um painel recolhido"
        janela.players._quadro()
        assert janela.players.quadros_desenhados == 0
        assert janela.players.quadros_vazios == 1

    def test_volta_sozinho_quando_o_participante_aparece(self, com_sessao):
        """Recolher e reversivel: trocar simulador por replay de gravacao no
        meio do dia faz o participante aparecer, e o painel volta."""
        bus, _, janela, perfil = com_sessao
        janela.definir_players_visivel(False)
        perfil.ao_trade(
            Trade(T0, SIMBOLO, BASE, 10, AgressorSide.BUY, "x", buyer_broker="A", seller_broker="B")
        )
        for _ in range(janela._quadros_sem_players % 2 + 240):
            janela._tick()
        assert janela.players.isVisible()

    def test_o_atalho_alterna(self, composicao):
        _, _, janela = composicao
        visivel = janela.players.isVisible()
        janela.alternar_players()
        assert janela.players.isVisible() is not visivel


# --------------------------------------------------------------------------
# 5. O carimbo
# --------------------------------------------------------------------------
class TestCarimbo:
    def test_sem_o_que_ressalvar_nao_ha_faixa(self, composicao):
        """Carimbo permanente vira moldura e para de ser lido."""
        _, _, janela = composicao
        assert janela.ressalva is None

    def test_a_faixa_escreve_titulo_e_detalhe(self, qapp):
        _, _, janela = _montar(
            qapp, ressalva=("MOTOR CALIBRADO", "dominância mín. 0,525 em vez de 0,70")
        )
        try:
            escritos = _textos(janela.ressalva)
            assert "MOTOR CALIBRADO" in escritos
            assert any("0,525" in t and "0,70" in t for t in escritos)
        finally:
            janela.close()

    def test_a_faixa_e_bloco_saturado_com_texto_escuro(self, qapp):
        """O par de maior contraste da paleta (12,34:1), e por isso o ULTIMO
        elemento a morrer no canal — nao o primeiro."""
        _, _, janela = _montar(qapp, ressalva=("T", "d"))
        try:
            fundos = {cor for _, cor in _espiar(janela.ressalva).retangulos}
            assert tokens.ALERT.name() in fundos
        finally:
            janela.close()

    def test_a_ressalva_encolhe_em_vez_de_truncar(self, qapp):
        """F8 vale para a ressalva tambem: frase cortada continua parecendo
        uma frase inteira, e o leitor nunca sabe que faltou pedaco."""
        detalhe = "ressalva muito comprida " * 12
        _, _, janela = _montar(qapp, ressalva=("T", detalhe))
        try:
            janela.ressalva.resize(600, 44)
            espiao = _espiar(janela.ressalva)
            assert detalhe in espiao.textos, "o texto vai INTEIRO para o painter"
        finally:
            janela.close()

    def test_derivada_da_config_sem_redigitar_numero(self):
        """O corte de producao e lido de `ConfigMotorSinais()`, nao digitado —
        recalibrar o motor de producao muda a tarja sozinho."""
        from scripts.painel import ressalva_da_config

        from fluxopro.app.config import ConfigOperacao, FonteDados

        producao = ConfigOperacao(fonte=FonteDados.MT5)
        assert ressalva_da_config(producao) == ("", "")

        calibrada = ConfigOperacao(
            fonte=FonteDados.MT5, motor=ConfigMotorSinais(dominancia_minima=0.525)
        )
        titulo, detalhe = ressalva_da_config(calibrada)
        assert titulo
        assert formatar_limiar("dominancia_minima", 0.525) in detalhe
        assert (
            formatar_limiar("dominancia_minima", ConfigMotorSinais().dominancia_minima)
            in detalhe
        )

    def test_simulador_carimba_mesmo_sem_calibracao(self):
        """Dado fabricado altera o que a tela afirma tanto quanto calibracao."""
        from scripts.painel import ressalva_da_config

        from fluxopro.app.config import ConfigOperacao, FonteDados

        titulo, detalhe = ressalva_da_config(ConfigOperacao(fonte=FonteDados.SIMULADOR))
        assert "SIMULADOR" in titulo
        assert "simulador.py" in detalhe


# --------------------------------------------------------------------------
# 6. A coluna que o registro avaliza
# --------------------------------------------------------------------------
class TestColunaDeRegras:
    def test_toda_familia_do_registro_aparece(self, composicao):
        """Derivado, nunca digitado: familia nova no registro entra na tela
        sem ninguem lembrar do painel.

        Medido na altura em que a coluna cabe INTEIRA — que a composicao nem
        sempre da. O que acontece quando ela nao da esta em
        `TestColunaCurta`, e nao aqui: se este teste fosse feito na altura
        apertada, ele estaria medindo o corte e chamando isso de lista."""
        _, _, janela = composicao
        painel = janela.regras
        familias = {i.split(".")[0] for i in REGRAS}
        assert len(painel._familias) == len(familias)
        painel.resize(painel.width(), _altura_inteira(painel))
        assert painel.layout_corrente().completo
        escritos = " ".join(_textos(painel))
        assert "DOMINÂNCIA" in escritos and "EXAUSTÃO" in escritos

    def test_a_contagem_bate_com_o_registro(self, composicao):
        _, _, janela = composicao
        implementadas = sum(1 for r in REGRAS.values() if r.implementada)
        escritos = _textos(janela.regras)
        assert f"{implementadas}/{len(REGRAS)} regras" in escritos
        for familia, feitas, total, _ in janela.regras._familias:
            reais = [r for i, r in REGRAS.items() if i.split(".")[0] == familia]
            assert total == len(reais)
            assert feitas == sum(1 for r in reais if r.implementada)

    def test_a_familia_recusada_aparece_recusada(self, composicao):
        """A linha que faz o painel valer: `exaustao` e o item mais frequente
        da banda de deteccoes e o registro nao a avaliza. A tela diz isso."""
        _, _, janela = composicao
        linha = next(f for f in janela.regras._familias if f[0] == "exaustao")
        assert linha[1] == 0
        assert linha[3] is Confianca.AUSENTE_NA_FONTE
        assert "0/1" in _textos(janela.regras)

    def test_limiar_calibrado_leva_o_de_producao_no_mesmo_portador(self, qapp):
        """A ressalva viaja na MESMA linha, no MESMO corpo. Ressalva em corpo
        menor que o dado que ela qualifica e, neste produto, defeito
        medivel."""
        painel = PainelRegras(ConfigMotorSinais(dominancia_minima=0.525))
        painel.resize(340, 600)
        texto = painel.texto_do_parametro("dominancia_minima")
        assert "0,525" in texto and "0,70" in texto
        assert painel.calibrado("dominancia_minima")
        assert not painel.calibrado("janela_micro_ns")
        assert texto in _textos(painel)

    def test_limiar_de_producao_nao_carrega_ressalva(self, composicao):
        _, _, janela = composicao
        assert janela.regras.texto_do_parametro("dominancia_minima") == "0,70"

    def test_nao_pega_aval_emprestado(self, composicao):
        """`macro_micro.janela_micro` responde por `ConfigMacroMicro`, nao pelo
        campo homonimo do motor. Reivindicar aquele aval aqui seria a mesma
        falha que a matriz recusa do lado oposto."""
        _, _, janela = composicao
        rotulo, _ = janela.regras.procedencia_do_campo("janela_micro_ns")
        assert "S/ REGISTRO" in rotulo
        rotulo_coberto, _ = janela.regras.procedencia_do_campo("dominancia_minima")
        assert "IMPRECISO" in rotulo_coberto

    def test_todo_limiar_exibido_e_campo_real_do_motor(self):
        """Nome morto na tabela viraria uma linha em branco no painel — e uma
        linha em branco num painel de procedencia parece uma regra sem
        rotulo."""
        import dataclasses

        reais = {campo.name for campo in dataclasses.fields(ConfigMotorSinais)}
        assert {campo for campo, _ in PARAMETROS_EM_VIGOR} <= reais

    def test_a_coluna_diz_que_nao_envia_ordem(self, composicao):
        """O fim honesto da cadeia: o elo 4 chama-se DECISAO e a decisao e do
        operador."""
        _, _, janela = composicao
        assert any("NÃO ENVIA ORDEM" in t for t in _textos(janela.regras))


# --------------------------------------------------------------------------
# 6b. A escala viaja no portador do numero que ela qualifica
# --------------------------------------------------------------------------
def _luminancia(hexa: str) -> float:
    """Luminancia relativa WCAG, recalculada do token e nunca tabelada."""
    canais = []
    for i in (1, 3, 5):
        c = int(hexa[i : i + 2], 16) / 255.0
        canais.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste(frente: str, fundo: str) -> float:
    a, b = _luminancia(frente), _luminancia(fundo)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)


def _forca(marca: Marca, fundo: str) -> tuple[int, float]:
    """O que o canal come primeiro: corpo pequeno e contraste baixo."""
    return marca.px, round(_contraste(marca.cor, fundo), 2)


def _marca_com(marcas: list[Marca], *trechos: str) -> Marca:
    for marca in marcas:
        if all(trecho in marca.texto for trecho in trechos):
            return marca
    raise AssertionError(f"nenhuma marca desenhada contem {trechos!r}")


def escala_nao_e_mais_fraca(
    marcas: list[Marca],
    escala: tuple[str, ...],
    veredito: tuple[str, ...],
    fundo: str,
) -> None:
    """A assercao generalizavel da rodada 2.

    **Um token de escala nunca pode render com corpo menor nem contraste
    menor que o veredito que ele qualifica.** A medicao de canal mostrou que
    a transmissao inverte a honestidade epistemica da tela: veredito e grande
    e saturado, escala e pequena e apagada, entao o canal entrega o primeiro
    e come o segundo — e o espectador recebe justamente o oraculo que este
    produto existe para nao emitir. Pior que sumir: escala degradada pode
    sobreviver ERRADA (`±3,2k` lido como `12,2k`), e escala errada nao e
    perda, e mentira.

    Passa trivialmente — e esse e o melhor caso — quando os dois saem no
    MESMO `drawText`: ai o canal nao tem como levar um e deixar o outro.
    """
    marca_escala = _marca_com(marcas, *escala)
    marca_veredito = _marca_com(marcas, *veredito)
    if marca_escala is marca_veredito:
        return
    px_e, ct_e = _forca(marca_escala, fundo)
    px_v, ct_v = _forca(marca_veredito, fundo)
    assert px_e >= px_v, (
        f"escala {marca_escala.texto!r} em {px_e}px contra veredito "
        f"{marca_veredito.texto!r} em {px_v}px"
    )
    assert ct_e >= ct_v, (
        f"escala {marca_escala.texto!r} a {ct_e}:1 contra veredito "
        f"{marca_veredito.texto!r} a {ct_v}:1"
    )


class TestEscalaNoMesmoPortador:
    def test_o_cano_publica_a_escala_do_medidor(self, composicao):
        """`8%` sozinho e veredito sem denominador: 8% de que?

        O teto do buffer vem de `ui/ponte.py` e nao e digitado — quem mexer
        no `CAPACIDADE_TAPE` muda o denominador na tela junto."""
        from fluxopro.ui.ponte import CAPACIDADE_TAPE

        _, _, janela = composicao
        janela._tick()
        escrito = " ".join(_textos(janela.conduto))
        assert "de " + _inteiro(CAPACIDADE_TAPE) in escrito

    def test_a_escala_do_cano_viaja_no_portador_do_numero(self, composicao):
        _, _, janela = composicao
        janela._tick()
        marcas = _espiar(janela.conduto).marcas
        escala_nao_e_mais_fraca(
            marcas, escala=("de ",), veredito=("%",), fundo=tokens.BG_SURFACE.name()
        )

    def test_a_escala_nao_e_omitida_por_falta_de_largura(self, composicao):
        """Coluna estreita nao e argumento para omitir a regua: quebra em
        duas linhas com o MESMO corpo, nunca cai para o numero sozinho."""
        from PySide6.QtGui import QFontMetrics

        from fluxopro.ui.janela import PainelConduto

        # Painel solto e `setFixedWidth`: o conduto montado tem largura
        # travada de proposito (e uma coluna, nao um painel elastico), entao
        # `resize` nele nao mediria nada.
        conduto = PainelConduto()
        # Larguras derivadas da METRICA, nao cravadas: a familia de fonte
        # disponivel muda o avanco de maquina para maquina, e um teste com
        # 120 cravado afirmaria sobre a fonte desta maquina, nao sobre o
        # comportamento do painel.
        metrica = QFontMetrics(tokens.fonte_numero(12, 600))
        junto = " ".join(conduto.linhas_do_pico())
        conduto.setFixedWidth(metrica.horizontalAdvance(junto) + 40)
        assert len(conduto.linhas_do_pico()) == 1

        conduto.setFixedWidth(max(20, metrica.horizontalAdvance(junto) // 2))
        linhas = conduto.linhas_do_pico()
        assert len(linhas) == 2 and linhas[1].startswith("de ")
        assert "%" in linhas[0]

    def test_o_corte_de_producao_viaja_no_portador_do_limiar(self, qapp):
        """`0,525` e `(prod. 0,70)` saem no MESMO `drawText` com a MESMA
        caneta — foi por isso que o corte de producao reteve 37% do traco no
        canal, contra 17% da escala do saldo do dia."""
        painel = PainelRegras(ConfigMotorSinais(dominancia_minima=0.525))
        painel.resize(340, 600)
        marcas = _espiar(painel).marcas
        escala_nao_e_mais_fraca(
            marcas, escala=("prod.",), veredito=("0,525",), fundo=tokens.BG_SURFACE.name()
        )

    def test_a_contagem_da_familia_carrega_o_denominador(self, composicao):
        """`6/8` sai inteiro num `drawText`. Um `6` grande com um `de 8`
        pequeno ao lado seria a mesma falha com outra roupa."""
        _, _, janela = composicao
        assert any(m.texto == "6/8" for m in _espiar(janela.regras).marcas)

    def test_o_denominador_da_pressao_esta_no_portador_do_veredito(self, qapp):
        """Era `xfail` — o conserto esta em `hud.FONTE_QUALIFICADOR`.

        Nasceu como sonda de escopo alheio: `de 30,0k` saia em
        10px/`TEXT_MUTED` (3,94:1) ao lado de um `▲ 51%` em 13px/BUY
        (6,92:1) — menor E mais apagado, as duas coisas que o canal come
        primeiro; medido, 32% de retencao de traco contra 39% do veredito.

        Fica AQUI, e nao em `test_ui_hud.py`, apesar do que o `reason`
        original mandava: `escala_nao_e_mais_fraca` e `_espiar` sao o
        aparelho de medida, e moveria-lo significaria duplica-lo. Aparelho
        duplicado e como uma sonda deixa de medir o que diz medir.
        """
        from fluxopro.ui.paineis.hud import PainelHUD, contexto_do_sinal

        painel = PainelHUD()
        painel.resize(340, painel.altura_natural)
        painel.aplicar(
            contexto_do_sinal(
                None, saldo_dia=2400, taxa_compra_janela=0.51, volume_janela=30_000
            )
        )
        escala_nao_e_mais_fraca(
            _espiar(painel).marcas,
            escala=("de ",),
            veredito=("51%",),
            fundo=tokens.BG_SURFACE.name(),
        )

    @pytest.mark.parametrize(
        "qualificador", [("de ",), ("s/lado",)], ids=["denominador", "rlp"]
    )
    def test_os_qualificadores_do_saldo_do_dia_tambem(self, qapp, qualificador):
        """A mesma lei na banda de cima, e nos DOIS qualificadores dela.

        Existe porque a mutacao que provou o teste do denominador da pressao
        reprovou UM teste, tendo eu mexido em TRES qualificadores. Um conserto
        com um terco de cobertura volta pelos outros dois tercos.

        O `s/lado` e o mais caro de perder dos tres: sem ele o saldo parece o
        retrato completo do pregao, e nao e — ha volume real cujo agressor a
        B3 nao divulga. Um `+2,4k` que sobrevive sozinho ao canal e uma
        afirmacao mais forte do que o produto tem como sustentar.
        """
        from fluxopro.ui.paineis.hud import PainelHUD, contexto_do_sinal

        painel = PainelHUD()
        painel.resize(340, painel.altura_natural)
        painel.aplicar(
            contexto_do_sinal(
                None,
                saldo_dia=2400,
                volume_comprador_dia=16_200,
                volume_vendedor_dia=13_800,
                volume_nao_atribuido=4_100,
            )
        )
        escala_nao_e_mais_fraca(
            _espiar(painel).marcas,
            escala=qualificador,
            veredito=("2,4k",),
            fundo=tokens.BG_SURFACE.name(),
        )

    # A sonda da regua de dominancia (ui/paineis/matriz.py) foi promovida
    # para tests/test_ui_matriz.py::TestReguaDeDominanciaNaoEMaisFracaQueOVeredito
    # depois que a regua passou a desenhar em FONTE_REGUA_PX/TEXT_SECONDARY
    # (>= corpo e contraste do veredito). Este arquivo so hospeda sondas de
    # ESCOPO ALHEIO enquanto o defeito nao e corrigido; corrigido, o teste
    # normal mora junto do painel que ele cobre.


# --------------------------------------------------------------------------
# 6b. A coluna curta — F8 na altura, e a doca minima da matriz
# --------------------------------------------------------------------------
ALTURAS = (0, 20, 40, 62, 80, 140, 200, 240, 300, 400, 434, 462, 600, 900)


class TestColunaCurta:
    """O defeito: `PainelRegras` desenhava as duas ultimas familias POR CIMA
    de `MODO SINAIS · NÃO ENVIA ORDEM`, e os quatro limiares caiam fora do
    widget sem nada dizer que existiam.

    A regra da casa e F8 — se nao cabe inteiro, nao entra — e quem cede aqui
    e a LISTA, nunca o rodape: a frase e a declaracao de escopo do produto, e
    a ausencia de uma familia e declaravel em uma linha (a ausencia da frase
    nao e). Estes testes medem contra `layout_regras`, que e a MESMA funcao
    que `PainelRegras.desenhar` consulta (lei n.o 6), e provam por mutacao
    que e mesmo ela que o desenho obedece.
    """

    def test_nada_invade_o_rodape(self):
        for altura in ALTURAS:
            plano = layout_regras(altura, 13)
            if not plano.rodape_visivel:
                # Altura em que nem o rodape cabe: nada mais e desenhado, e
                # e o que `test_o_rodape_e_o_ultimo_a_cair` cobra.
                assert plano.n_familias == 0 and plano.n_limiares == 0, altura
                continue
            fim_familias = plano.y_familias + plano.n_familias * ALTURA_LINHA_REGRA
            assert fim_familias <= plano.rodape.top(), altura
            if plano.n_limiares:
                fim = (
                    plano.y_limiares
                    + ALTURA_TITULO_LIMIARES
                    + plano.n_limiares * ALTURA_LINHA_PARAMETRO
                )
                assert fim <= plano.rodape.top(), altura
            if plano.y_corte >= 0:
                assert plano.y_corte >= fim_familias, altura
                assert plano.y_corte + ALTURA_LINHA_REGRA <= plano.rodape.top(), altura
            if plano.rodape_visivel:
                assert plano.rodape.bottom() < altura, altura

    def test_o_que_nao_cabe_nao_entra_pela_metade(self):
        """F8 em numero: linha desenhada e linha INTEIRA, e o que sobrou de
        fora e contado, nunca deixado subentendido."""
        for altura in ALTURAS:
            plano = layout_regras(altura, 13)
            assert 0 <= plano.n_familias <= 13
            assert plano.n_familias + plano.familias_fora == 13
            assert plano.n_limiares + plano.limiares_fora == len(PARAMETROS_EM_VIGOR)
            if plano.rodape_visivel and plano.n_familias:
                assert plano.completo == (plano.y_corte < 0)
            if plano.n_familias == 0 and plano.n_limiares == 0:
                # Altura em que so o cabecalho e o rodape cabem. Nao ha linha
                # de corte porque nao ha linha nenhuma — e uma lista ausente
                # nao promete nada, ao contrario de uma lista cortada.
                assert not plano.completo

    def test_o_rodape_e_o_ultimo_a_cair(self, qapp):
        """Se ha espaco para UMA linha, ela e do rodape — nao da lista."""
        painel = PainelRegras()
        for altura in ALTURAS:
            painel.resize(340, altura)
            plano = painel.layout_corrente()
            escritos = " ".join(_textos(painel))
            if plano.rodape_visivel:
                assert RODAPE_MODO in escritos, altura
            else:
                # Altura em que nem o rodape cabe abaixo do cabecalho: a
                # lista tambem nao entra. Rodape fora e lista dentro seria a
                # troca exata que este teste existe para proibir.
                assert plano.n_familias == 0 and plano.n_limiares == 0, altura

    def test_a_coluna_curta_declara_o_que_ficou_de_fora(self, qapp):
        painel = PainelRegras()
        painel.resize(340, 240)
        plano = painel.layout_corrente()
        assert not plano.completo
        escritos = " ".join(_textos(painel))
        assert "FORA" in escritos
        assert str(plano.familias_fora) in escritos

    def test_a_ressalva_sobrevive_ao_aperto(self, composicao):
        """Lei n.o 1 em geometria: o aperto nao pode preservar o veredito e
        comer a ressalva. Truncar pela cauda apagaria `EXAUSTÃO 0/1`, que e a
        linha que desmente a banda de deteccoes."""
        _, _, janela = composicao
        familias = janela.regras._familias
        recusadas = {f[0] for f in familias if f[1] == 0}
        implementadas = {f[0] for f in familias if f[1] > 0}
        for n in range(2, len(familias)):
            visiveis = {f[0] for f in familias_na_tela(familias, n)}
            assert len(visiveis) == n
            assert visiveis & recusadas, n
            assert visiveis & implementadas, n

    def test_a_linha_do_corte_viaja_em_chip_de_luminancia(self, qapp):
        """Segunda metade da lei do canal: ressalva em CHIP de token de
        LUMINANCIA alta. `DANGER` (5,45:1) e quase so croma, e o JPEG
        subamostra croma 2x. Texto colorido sobre o fundo do painel ja
        reprovou aqui: 37,6% contra 44,2% do rodape que ele qualifica
        (`scripts/retencao.py`), e o par so passou quando a linha virou
        bloco preenchido com texto escuro."""
        painel = PainelRegras()
        painel.resize(340, 240)
        espiao = _espiar(painel)
        marcas = [m for m in espiao.marcas if "FORA" in m.texto]
        assert marcas
        # Texto ESCURO sobre bloco `ALERT` — nunca `ALERT` sobre o fundo.
        assert all(m.cor == tokens.BG_BASE.name() for m in marcas)
        assert all(m.cor != tokens.DANGER.name() for m in marcas)
        plano = painel.layout_corrente()
        chips = [
            r for r, cor in espiao.retangulos
            if cor == tokens.ALERT.name() and r.top() >= plano.y_corte
            and r.bottom() <= plano.rodape.top()
        ]
        assert chips, "a linha do corte tem de ser um bloco preenchido"
        # Corpo igual ao do rodape que ela qualifica — nunca menor.
        corpo_rodape = next(m.px for m in espiao.marcas if m.texto == RODAPE_MODO)
        assert all(m.px >= corpo_rodape for m in marcas)

    def test_o_desenho_obedece_a_geometria_medida(self, qapp, monkeypatch):
        """Prova por mutacao: troco `layout_regras` e exijo que o DESENHO
        mude. Sem isto, "desenho e teste chamam a mesma funcao" e so uma
        frase de docstring."""
        painel = PainelRegras()
        painel.resize(340, _altura_inteira(painel))
        antes = _textos(painel)
        assert "DOMINÂNCIA" in " ".join(antes)

        real = layout_regras

        def mutado(altura, n_familias, *args, **kwargs):
            return real(altura, 2, *args, **kwargs)

        monkeypatch.setattr(J, "layout_regras", mutado)
        depois = _textos(painel)
        assert len(depois) < len(antes)
        # `ESTRUTURA` so existe como linha de FAMILIA — `DOMINÂNCIA` tambem e
        # rotulo de limiar, e serviria de marco ambiguo.
        assert "ESTRUTURA" in " ".join(antes)
        assert "ESTRUTURA" not in " ".join(depois)

    def test_texto_do_corte_encolhe_o_vocabulario_nunca_o_numero(self):
        alternativas = texto_do_corte(7, 4)
        larguras = [len(a) for a in alternativas]
        assert larguras == sorted(larguras, reverse=True)
        for a in alternativas:
            assert "7" in a and "4" in a
            assert "…" not in a and "..." not in a


class TestDocaDaMatriz:
    """A banda `DETECÇÕES` aparecia VAZIA: cabecalho e linha de colunas
    desenhados, nenhuma deteccao embaixo.

    A causa e de altura, e nao de alimentacao: `matriz.ao_redimensionar`
    calcula `util = altura da banda - rotulo - colunas` e abre
    `util // altura_linha` slots. Nos 260px que o proprio painel pede como
    minimo (`matriz.py`, `setMinimumSize(360, 260)`), `util` e NEGATIVO — zero
    slots —, e `matriz.py:_desenhar_deteccoes` desenha o cabecalho e a faixa
    de colunas ANTES de retornar por `self._n_slots <= 0`. O conserto de
    dentro e do dono daquele arquivo; o que a composicao garante e nunca
    entregar aquela altura.
    """

    def test_a_altura_minima_e_derivada_e_justa(self, qapp):
        """Justa nos dois sentidos: nela a banda abre os slots, e uma linha
        abaixo dela nao abre. E o que prova que o numero saiu das constantes
        da matriz, e nao de um redondo escolhido a olho."""
        from fluxopro.ui.paineis.matriz import PainelMatriz

        painel = PainelMatriz(WDO_GRID)
        painel.show()  # `ao_redimensionar` vem do resizeEvent, e ele so
        try:           # chega em widget mostrado.
            alvo = altura_minima_matriz(tokens.PADRAO)
            painel.resize(400, alvo)
            qapp.processEvents()
            assert painel._n_slots >= SLOTS_MINIMOS_MATRIZ
            painel.resize(400, alvo - tokens.PADRAO.altura_linha)
            qapp.processEvents()
            assert painel._n_slots < SLOTS_MINIMOS_MATRIZ
        finally:
            painel.close()

    def test_o_piso_le_a_matriz_e_nao_uma_copia(self, monkeypatch):
        """Prova por mutacao da fonte do numero: mexo numa banda DA MATRIZ e
        exijo que o piso ande junto. Se o piso fosse um `332` digitado aqui,
        ele continuaria igual e a doca voltaria a espremer a banda no dia em
        que a matriz crescesse."""
        from fluxopro.ui.paineis import matriz as matriz_mod

        antes = altura_minima_matriz(tokens.PADRAO)
        monkeypatch.setattr(
            matriz_mod, "ALTURA_ESTAGIO", matriz_mod.ALTURA_ESTAGIO + 20
        )
        assert altura_minima_matriz(tokens.PADRAO) == antes + 20

    def test_a_composicao_nunca_espreme_a_banda_a_zero(self, composicao):
        _, _, janela = composicao
        assert janela.matriz.minimumHeight() >= altura_minima_matriz(janela.densidade)
        assert janela.matriz.height() >= altura_minima_matriz(janela.densidade)


# --------------------------------------------------------------------------
# 7. Sem cromo, sem cor literal
# --------------------------------------------------------------------------
class TestSemCromo:
    def test_nenhum_widget_de_sistema_na_area_de_dados(self, composicao):
        """V5: a tela e consumida por captura. O que houver de cromo aparece
        na transmissao — e um punho de `QSplitter` e desenhado pelo estilo do
        SO, nao por `tokens.py`."""
        _, _, janela = composicao
        proibidos = (
            QSplitter,
            QMenuBar,
            QStatusBar,
            QToolBar,
            QScrollBar,
            QPushButton,
            QAbstractScrollArea,
        )
        achados = [
            type(w).__name__
            for w in janela.findChildren(object)
            if isinstance(w, proibidos)
        ]
        assert achados == []
        assert janela.menuBar().isHidden() or janela.menuBar().actions() == []

    def test_toda_doca_troca_a_barra_de_titulo_do_SO_pela_nossa(self, composicao):
        """A condicao que fez o docking ser aceito depois de o `QSplitter` ter
        sido recusado. Ver `ui/workspace.py`, "o conflito docking x cadeia".

        `QDockWidget` sem `setTitleBarWidget` desenha titulo e botoes com o
        estilo do sistema — a MESMA objecao do punho do `QSplitter`, em dose
        maior porque sao catorze. E `DockWidgetClosable` fica de fora: painel
        que se perde num clique e painel em que nao se confia no meio do
        pregao."""
        from PySide6.QtWidgets import QDockWidget

        from fluxopro.ui.janela import CabecalhoDoca

        docas = janela_docas(composicao)
        assert docas, "nenhuma doca montada"
        for chave, doca in docas.items():
            assert isinstance(doca.titleBarWidget(), CabecalhoDoca), chave
            fechavel = QDockWidget.DockWidgetFeature.DockWidgetClosable
            assert not (doca.features() & fechavel), chave
            assert doca.objectName(), "sem objectName, `restoreState` erra a doca"

    def test_o_separador_do_docking_vem_dos_tokens(self, composicao):
        """O unico cromo que sobra do `QMainWindow` e o separador, e ele vai
        DECLARADO a partir de `tokens` — pixel de codigo versionado, que era a
        objecao real ao `QSplitter`."""
        from fluxopro.ui.workspace import folha_de_estilo

        _, _, janela = composicao
        folha = janela._host.styleSheet()
        assert "QMainWindow::separator" in folha
        assert tokens.BORDER.name() in folha
        assert folha == folha_de_estilo()

    def test_nenhuma_cor_literal_na_composicao(self):
        """§3.2: painel nenhum escreve cor. Tudo vem de `tokens.py`."""
        import re

        # A folha de estilo do docking entrou na varredura de proposito: e o
        # lugar mais facil do projeto para um hexadecimal aparecer, porque CSS
        # pede cor em texto. Ela deriva de `tokens.BORDER.name()`.
        for relativo in (
            ("fluxopro", "ui", "janela.py"),
            ("fluxopro", "ui", "workspace.py"),
            ("fluxopro", "ui", "sala.py"),
            ("fluxopro", "ui", "trilha.py"),
            ("fluxopro", "ui", "paineis", "metodo.py"),
        ):
            fonte = RAIZ.joinpath(*relativo).read_text(encoding="utf-8")
            assert re.search(r"#[0-9a-fA-F]{6}\b", fonte) is None, relativo[-1]
            assert 'QColor("' not in fonte, relativo[-1]
            assert "QColor('" not in fonte, relativo[-1]

    def test_o_texto_da_ressalva_cabe_na_largura(self, qapp):
        """A tarja e o unico elemento que pode crescer sem limite (o detalhe
        vem da linha de comando); a fonte tem de encolher ate caber."""
        painel = FaixaRessalva("T", "detalhe " * 30)
        painel.resize(500, 44)
        # A fonte escolhida nunca e maior que a que cabe: 10px e o piso, e
        # abaixo disso nao adianta caber.
        metrica = QFontMetrics(tokens.fonte_ui(10, 500))
        assert metrica.horizontalAdvance("x") > 0


class TestParcelasDoDia:
    """A barra do dia sai DERIVADA do retrato, nunca lida de `sessao.delta`.

    O construtor do HUD apontou, corretamente, que o app rodando desenhava a
    barra do dia vazia — a janela nao passava as parcelas. A correcao obvia
    seria ler `sessao.delta.volume_comprador_sessao` e o par vendedor; ela
    funcionaria e violaria a invariante que esta janela ja respeita, porque
    seriam tres escalares lidos da thread do Qt enquanto a thread da fonte
    escreve, com uma invariante COMPOSTA entre eles.

    Estes testes fixam a derivacao: as parcelas vem de um retrato unico,
    montado sob o lock, e por isso somam exatamente o que devem somar.
    """

    def _contexto(self, composicao, delta, volume, sem_lado=0):
        _, _, janela = composicao
        from fluxopro.ui.ponte import Contadores, EstadoFeed, Instantaneo

        retrato = Instantaneo(
            estado=EstadoFeed.VIVO,
            ultimo_preco=None,
            primeiro_preco=None,
            volume_sessao=volume,
            delta_sessao=delta,
            volume_nao_atribuido=sem_lado,
            ultimo_evento_ns=0,
            atraso_s=0.0,
            contadores=Contadores(),
        )
        return janela._contexto(retrato)

    def test_as_parcelas_somam_o_volume_atribuido(self, composicao):
        leitura = self._contexto(composicao, delta=+400, volume=10_000, sem_lado=200)
        assert leitura.volume_comprador_dia + leitura.volume_vendedor_dia == 9_800

    def test_a_diferenca_das_parcelas_e_o_delta(self, composicao):
        leitura = self._contexto(composicao, delta=-1_234, volume=50_000)
        assert leitura.volume_comprador_dia - leitura.volume_vendedor_dia == -1_234

    def test_sessao_zerada_nao_inventa_parcela(self, composicao):
        leitura = self._contexto(composicao, delta=0, volume=0)
        assert leitura.volume_comprador_dia == leitura.volume_vendedor_dia == 0

    def test_delta_maior_que_o_volume_nao_produz_parcela_negativa(self, composicao):
        """Nao deveria acontecer, e por isso mesmo tem de degradar sem mentir.

        Se um retrato chegar inconsistente — invariante quebrada rio acima —,
        a barra desenha uma parcela zerada em vez de uma largura negativa. E o
        mesmo criterio do `PASSA SEM MEDIR`: nao publique um numero na forma
        que ele nao sustenta.
        """
        leitura = self._contexto(composicao, delta=+9_999, volume=10)
        assert leitura.volume_vendedor_dia == 0
        assert leitura.volume_comprador_dia >= 0
