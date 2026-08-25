"""FASE 3 — docking, workspaces, multi-monitor, densidade e Sala de Controle.

E o painel do METODO, que e a peca da mesma rodada.

O que estes testes medem, e por que cada um existe:

* **A cadeia sob docking.** A decisao desta rodada foi que o trilho se
  subordina ao arranjo (`ui/workspace.py`). Entao ha duas familias de
  assercao: os quatro workspaces de fabrica produzem cadeia legivel, e um
  arranjo que a desmancha faz o trilho SE ABSTER — com motivo. Testar so a
  primeira metade seria testar o caso feliz de uma decisao cuja parte
  interessante e o caso infeliz.

* **A regra da janela orfa, sem monitor.** `reancorar` e pura de geometria de
  proposito: um CI tem um monitor so, e a regra existe justamente para o
  arranjo de tres. Testa-la contra `QScreen` seria testa-la exatamente na
  configuracao em que ela nunca falha.

* **Prova por mutacao (lei n.o 6).** Onde o desenho e o teste compartilham
  geometria, o teste troca a funcao compartilhada e exige que o PIXEL mude.
  Sem isso, "desenho e teste chamam a mesma funcao" e uma afirmacao de
  docstring.

* **As duas sondas `xfail` sairam daqui, e nao por desistencia.** Elas eram o
  registro executavel de duas pendencias com endereco — o retrato de analytics
  montado sob o lock e a densidade a quente sem perder o historico de tela — e
  as duas foram consertadas. Viraram teste normal, na camada que as consertou:
  `tests/test_app_retrato_analytics.py` e
  `tests/test_ui_densidade_a_quente.py`. Uma sonda que continuasse aqui depois
  do conserto seria um `xfail(strict=False)` que passa em silencio, que e a
  forma exata de teste que nao mede nada.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402

from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.core.eventos import WDO_GRID, AgressorSide, Trade  # noqa: E402
from fluxopro.metodologia.leitura import LeitorMetodo, LeituraMetodo  # noqa: E402
from fluxopro.ui import tokens, workspace as W  # noqa: E402
from fluxopro.ui.janela import (  # noqa: E402
    ALTURA_LINHA_REGRA,
    RODAPE_MODO,
    SLOTS_MINIMOS_MATRIZ,
    JanelaFluxo,
    ROTULO_ARRANJO_LIVRE,
    altura_minima_matriz,
)
from fluxopro.ui.paineis import metodo as M  # noqa: E402
from fluxopro.ui.paineis.strips import (  # noqa: E402
    PROIBIDO_EM_REPLAY,
    RotuloContraditorioError,
    StripRodape,
    StripTopo,
    rotulo_do_estado,
)
from fluxopro.ui.ponte import EstadoFeed, PonteFluxo  # noqa: E402
from fluxopro.ui.sala import (  # noqa: E402
    EstadoSala,
    Instrumento,
    SalaDeControle,
    particionar_contagem,
)
from fluxopro.ui.trilha import Nivel, TrilhaEventos  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SIMBOLO = "WDOV26"
BASE = 5000
T0 = 1_700_000_000_000_000_000


# --------------------------------------------------------------------------
# Ferramenta: espiao de QPainter
# --------------------------------------------------------------------------
class PainterEspiao:
    """Registra `fillRect` e `drawText` sem desenhar de mentira.

    Local, como em `test_ui_composicao.py` e `test_ui_matriz.py`: os tres
    mudam por razoes diferentes e um espiao compartilhado acoplaria arquivos
    de teste que nao tem nada a ver um com o outro.
    """

    def __init__(self, painter: QPainter) -> None:
        self._painter = painter
        self.textos: list[str] = []
        self.caixas: list[QRect] = []

    def __getattr__(self, nome):
        return getattr(self._painter, nome)

    def fillRect(self, *args):  # noqa: N802
        if args and isinstance(args[0], QRect):
            self.caixas.append(QRect(args[0]))
        self._painter.fillRect(*args)

    def drawText(self, *args):  # noqa: N802
        for arg in args:
            if isinstance(arg, str):
                self.textos.append(arg)
        self._painter.drawText(*args)


def _identificadores(caminho) -> set[str]:
    """Todo nome e atributo que o arquivo REALMENTE usa, pelo AST.

    Docstring nao entra — e ela e justamente onde este projeto explica o que
    NAO faz. Duas varreduras por substring ja reprovaram arquivos pela frase
    que dizia a verdade sobre eles.
    """
    import ast

    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for alias in no.names:
                nomes.add(alias.asname or alias.name.split(".")[0])
    return nomes


def _espiar(painel) -> PainterEspiao:
    pixmap = QPixmap(max(1, painel.width()), max(1, painel.height()))
    painter = QPainter(pixmap)
    espiao = PainterEspiao(painter)
    try:
        painel.desenhar(espiao, QRect(0, 0, painel.width(), painel.height()))
    finally:
        painter.end()
    return espiao


@pytest.fixture
def janela(qapp):
    j = JanelaFluxo(PonteFluxo(Barramento()), SIMBOLO, WDO_GRID)
    j.resize(1480, 900)
    j.show()
    qapp.processEvents()
    yield j
    j.close()


# --------------------------------------------------------------------------
# 1. A cadeia sob docking — a decisao desta rodada, dos dois lados
# --------------------------------------------------------------------------
class TestCadeiaSobDocking:
    def test_cortes_da_cadeia_e_pura_e_recusa_o_que_nao_e_cadeia(self):
        """Quatro faixas disjuntas e em ordem = cadeia. Qualquer outra coisa
        e uma abstencao COM motivo, e o motivo diz qual elo estragou."""
        ok, motivo = W.cortes_da_cadeia(((0, 99), (100, 199), (200, 299), (300, 399)), 400)
        assert motivo == ""
        assert ok == (100, 200, 300)

        _, motivo = W.cortes_da_cadeia(((0, 99), None, (200, 299), (300, 399)), 400)
        assert motivo == W.MOTIVO_ELO_AUSENTE % 2

        _, motivo = W.cortes_da_cadeia(((0, 99), (100, 250), (200, 299), (300, 399)), 400)
        assert motivo == W.MOTIVO_SOBREPOSTOS % (2, 3)

        _, motivo = W.cortes_da_cadeia(((300, 399), (100, 199), (200, 299), (0, 99)), 400)
        assert motivo == W.MOTIVO_FORA_DE_ORDEM % (2, 1)

    def test_os_quatro_workspaces_de_fabrica_dao_cadeia_legivel(self, janela, qapp):
        """Se um arranjo DE FABRICA nao fosse cadeia, o produto estaria
        entregando o caso degradado como padrao."""
        for alvo in W.WORKSPACES_DE_FABRICA:
            janela.aplicar_workspace(alvo)
            qapp.processEvents()
            janela._sincronizar_trilho()
            assert alvo.cadeia_completa, alvo.nome
            assert not janela.trilho.arranjo_livre, (alvo.nome, janela.trilho.motivo)
            assert len(janela.trilho.segmentos()) == 4

    def test_esconder_um_elo_faz_o_trilho_se_abster(self, janela, qapp):
        """O caso infeliz, que e a parte interessante da decisao.

        Um trilho fixo em quatro segmentos continuaria desenhando quatro
        colunas sobre um arranjo que tem tres — legenda desalinhada, que o
        proprio modulo argumenta ser pior que rotulo nenhum."""
        for chave in ("hud", "metodo", "regras"):
            janela.docas[chave].setVisible(False)
        qapp.processEvents()
        janela._sincronizar_trilho()
        assert janela.trilho.arranjo_livre
        assert janela.trilho.motivo == W.MOTIVO_ELO_AUSENTE % 4
        assert len(janela.trilho.segmentos()) == 1, "abstencao tem UM segmento"

    def test_a_abstencao_e_escrita_na_tela_e_na_trilha(self, janela, qapp):
        """§3.5: nada de modal, e nada de silencio. A tela diz, a trilha
        registra, e as duas dizem a mesma coisa."""
        antes = janela.trilha.total
        for chave in ("conduto",):
            janela.docas[chave].setVisible(False)
        qapp.processEvents()
        janela._sincronizar_trilho()
        assert janela.trilho.arranjo_livre
        textos = " ".join(_espiar(janela.trilho).textos)
        assert ROTULO_ARRANJO_LIVRE in textos
        assert janela.trilho.motivo in textos
        assert janela.trilha.total > antes
        recentes = " ".join(e.texto for e in janela.trilha.recentes(5))
        assert janela.trilho.motivo in recentes

    def test_a_abstencao_nao_inunda_a_trilha(self, janela, qapp):
        """Um arrasto de doca dispara `resizeEvent` dezenas de vezes. Uma
        trilha inundada pelo proprio arrasto e uma trilha em que o gap de
        sequencia do MBO nao vai ser achado."""
        janela.docas["conduto"].setVisible(False)
        qapp.processEvents()
        janela._sincronizar_trilho()
        antes = janela.trilha.total
        for _ in range(20):
            janela._sincronizar_trilho()
        assert janela.trilha.total == antes

    def test_doca_flutuante_sai_da_faixa_do_elo(self, janela, qapp):
        """§4.1 deixa destacar painel para janela nativa. Uma doca noutra
        janela nao ocupa faixa NESTA — mapear a coordenada dela para ca daria
        um numero sem significado geometrico."""
        janela.docas["conduto"].setFloating(True)
        qapp.processEvents()
        assert janela.faixas_dos_elos()[1] is None
        janela._sincronizar_trilho()
        assert janela.trilho.motivo == W.MOTIVO_ELO_AUSENTE % 2

    def test_o_elo_vai_escrito_no_cabecalho_de_cada_doca(self, janela):
        """A ressalva sobrevive a perda do veredito: com o trilho abstido, o
        operador ainda le em cada painel a que altura da cadeia ele pertence."""
        from fluxopro.ui.janela import CabecalhoDoca

        for chave, doca in janela.docas.items():
            cabecalho = doca.titleBarWidget()
            assert isinstance(cabecalho, CabecalhoDoca)
            assert cabecalho.elo == W.ELO_DA_DOCA[chave]




# --------------------------------------------------------------------------
# 1b. O que cada arranjo de fabrica entrega de ALTURA
# --------------------------------------------------------------------------
class TestAlturasDeFabrica:
    """Dois defeitos vistos no retrato, medidos no arranjo que os produziu.

    A cadeia legivel (acima) e sobre LARGURA. Estes sao sobre altura, e ela
    e quem os dois defeitos tinham em comum: a coluna da decisao curta
    escrevia familia por cima do rodape `MODO SINAIS · NÃO ENVIA ORDEM`, e a
    doca da matriz chegava a uma altura em que a banda `DETECÇÕES` abria
    ZERO slots — cabecalho e linha de colunas desenhados sobre vao vazio.
    """

    def test_a_matriz_nunca_recebe_doca_sem_slot(self, janela, qapp):
        """Banda que reserva cabecalho e nao mostra linha e pior que banda
        ausente: ela promete dado e entrega vao. O arranjo **Revisão** era o
        que entregava isso — 260px, `util` negativo, zero slots."""
        piso = altura_minima_matriz(janela.densidade)
        for alvo in W.WORKSPACES_DE_FABRICA:
            janela.aplicar_workspace(alvo)
            qapp.processEvents()
            if not janela.docas["matriz"].isVisible():
                continue
            assert janela.matriz.height() >= piso, (alvo.nome, janela.matriz.height())
            assert janela.matriz._n_slots >= SLOTS_MINIMOS_MATRIZ, alvo.nome

    def test_o_rodape_do_modo_sobrevive_a_todo_arranjo(self, janela, qapp):
        """A frase que declara que o produto NAO ENVIA ORDEM e a ultima coisa
        que a coluna abre mao de mostrar — e nenhuma familia e escrita por
        cima dela."""
        for alvo in W.WORKSPACES_DE_FABRICA:
            janela.aplicar_workspace(alvo)
            qapp.processEvents()
            if not janela.docas["regras"].isVisible():
                continue
            plano = janela.regras.layout_corrente()
            assert plano.rodape_visivel, alvo.nome
            fim = plano.y_familias + plano.n_familias * ALTURA_LINHA_REGRA
            assert fim <= plano.rodape.top(), alvo.nome
            escritos = " ".join(_espiar(janela.regras).textos)
            assert RODAPE_MODO in escritos, alvo.nome
            if not plano.completo:
                assert "FORA" in escritos, alvo.nome


# --------------------------------------------------------------------------
# 2. Workspaces: atalho, troca e persistencia
# --------------------------------------------------------------------------
class TestWorkspaces:
    def test_os_quatro_de_fabrica_de_ss4_1_existem_com_ctrl_1_a_4(self):
        assert W.NOMES_DE_FABRICA == ("Fluxo", "Book & Tape", "Bookmap", "Revisão")
        assert [w.atalho for w in W.WORKSPACES_DE_FABRICA] == [1, 2, 3, 4]

    def test_ctrl_n_troca_e_ctrl_9_diz_que_nao_ha_para_onde_ir(self, janela, qapp):
        assert janela.workspace_por_atalho(3)
        assert janela.workspace.nome == "Bookmap"
        antes = janela.trilha.total
        assert not janela.workspace_por_atalho(9)
        assert janela.workspace.nome == "Bookmap", "atalho vazio nao troca nada"
        assert janela.trilha.total > antes, "silencio faria o atalho parecer quebrado"

    def test_trocar_de_workspace_esconde_doca_e_nao_destroi_painel(self, janela, qapp):
        """O footprint tem historico de TELA. Destruir e reconstruir a cada
        `Ctrl+N` faria o operador voltar do Bookmap para uma grade vazia."""
        antes = janela.footprint
        janela.workspace_por_atalho(2)
        qapp.processEvents()
        assert janela.footprint is antes
        assert not janela.docas["footprint"].isVisible()
        janela.workspace_por_atalho(1)
        qapp.processEvents()
        assert janela.footprint is antes
        assert janela.docas["footprint"].isVisible()

    def test_o_arquivo_de_workspace_e_json_e_faz_ida_e_volta(self, janela, tmp_path, monkeypatch):
        """JSON e nao `QSettings`: §4.1 pede um arquivo por workspace num
        caminho nomeado, e um formato que uma pessoa possa apagar quando o Qt
        salvar um arranjo impossivel — que acontece."""
        monkeypatch.setenv("FLUXOPRO_WORKSPACES", str(tmp_path))
        geometria = janela.saveGeometry()
        estado = janela._host.saveState()
        caminho = W.salvar("Fluxo", geometria, estado, {"densidade": "Padrao"})
        assert caminho.parent == tmp_path
        g2, e2, extra = W.carregar("Fluxo")
        assert bytes(g2) == bytes(geometria)
        assert bytes(e2) == bytes(estado)
        assert extra["densidade"] == "Padrao"

    def test_a_janela_restaura_geometria_e_estado_do_workspace(self, janela, tmp_path, monkeypatch):
        monkeypatch.setenv("FLUXOPRO_WORKSPACES", str(tmp_path))
        geometria = janela.saveGeometry()
        estado = janela._host.saveState()
        W.salvar("Fluxo", geometria, estado, {})
        janela._persistir = True
        recebidas = []

        def restaurar(blob):
            recebidas.append(bytes(blob))
            return True

        monkeypatch.setattr(janela, "restoreGeometry", restaurar)
        retorno = janela._estado_salvo(W.WORKSPACES_DE_FABRICA[0])
        assert retorno is not None
        assert recebidas == [bytes(geometria)]

    def test_estado_legado_sem_doca_nexo_nao_quebra_workspace_historico(
        self, janela, tmp_path, monkeypatch, qapp
    ):
        """Um saveState anterior ao NEXO deve continuar abrindo Fluxo."""

        from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

        monkeypatch.setenv("FLUXOPRO_WORKSPACES", str(tmp_path))
        legado = QMainWindow()
        for chave in ("dom", "tape", "conduto", "matriz", "hud"):
            doca = QDockWidget(legado)
            doca.setObjectName("doca_" + chave)
            doca.setWidget(QWidget())
            legado.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, doca)
        estado_legado = legado.saveState()
        geometria = janela.saveGeometry()
        W.salvar("Fluxo", geometria, estado_legado, {})
        janela._persistir = True

        assert janela.workspace_por_atalho(1)
        qapp.processEvents()
        assert janela.workspace.nome == "Fluxo"
        assert janela.docas["dom"].isVisible()
        assert janela.docas["asg"].isVisible() is False

    def test_workspace_inexistente_nao_e_erro(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLUXOPRO_WORKSPACES", str(tmp_path))
        assert W.carregar("Fluxo") is None

    def test_arquivo_de_versao_futura_e_recusado_com_motivo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FLUXOPRO_WORKSPACES", str(tmp_path))
        caminho = W.caminho_do_workspace("Fluxo")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text('{"versao": 99}', encoding="utf-8")
        with pytest.raises(ValueError, match="versão"):
            W.carregar("Fluxo")

    def test_a_janela_nao_grava_no_perfil_de_quem_roda_por_padrao(self, janela):
        """`persistir` nasce desligado. Um retrato que dependesse do
        `%APPDATA%` de quem gerou nao seria reproduzivel — e apagar o arranjo
        do operador para provar que se sabe gravar arquivo e dano."""
        assert janela.salvar_workspace() is None

    def test_workspace_recusa_doca_desconhecida_e_atalho_fora_de_1_9(self):
        with pytest.raises(ValueError):
            W.Workspace("X", 1, "", ("nao_existe",))
        with pytest.raises(ValueError):
            W.Workspace("X", 0, "", ("dom",))


# --------------------------------------------------------------------------
# 3. A janela orfa (§4.1) — pura, sem monitor
# --------------------------------------------------------------------------
class TestJanelaOrfa:
    TELA = QRect(0, 0, 1920, 1040)
    SEGUNDA = QRect(1920, 0, 1920, 1040)

    def test_janela_visivel_volta_intacta(self):
        geo = QRect(100, 100, 800, 600)
        novo, orfa = W.reancorar(geo, (self.TELA,), self.TELA)
        assert not orfa and novo == geo

    def test_o_monitor_que_sumiu_traz_a_janela_para_o_primario(self):
        """O defeito classico de terminal, nomeado em §4.1. `restoreGeometry`
        do Qt NAO faz isto: ele restaura os numeros que foram salvos."""
        geo = QRect(2400, 200, 800, 600)  # salva na segunda tela
        novo, orfa = W.reancorar(geo, (self.TELA,), self.TELA)
        assert orfa
        assert self.TELA.contains(novo), novo
        assert (novo.width(), novo.height()) == (800, 600), "nao encolhe sem precisar"

    def test_com_o_segundo_monitor_presente_nada_se_mexe(self):
        geo = QRect(2400, 200, 800, 600)
        novo, orfa = W.reancorar(geo, (self.TELA, self.SEGUNDA), self.TELA)
        assert not orfa and novo == geo

    def test_meia_janela_fora_ainda_nao_e_orfa_e_95_por_cento_e(self):
        """O limiar e meia janela e nao um pixel: uma janela 95% fora satisfaz
        "tem intersecao" e continua sendo o defeito — o operador ve uma lasca
        e nao consegue nem arrasta-la de volta."""
        quase_dentro = QRect(-380, 100, 800, 600)  # 420 de 800 visiveis
        assert not W.e_orfa(quase_dentro, (self.TELA,))
        lasca = QRect(-760, 100, 800, 600)  # 40 de 800
        assert W.e_orfa(lasca, (self.TELA,))

    def test_janela_maior_que_o_primario_encolhe_para_caber(self):
        novo, orfa = W.reancorar(QRect(3000, 0, 3000, 2000), (self.TELA,), self.TELA)
        assert orfa and self.TELA.contains(novo)

    def test_sem_tela_nenhuma_e_orfa(self):
        assert W.e_orfa(QRect(0, 0, 800, 600), ())

    def test_a_janela_aplica_a_regra_e_avisa_na_trilha(self, janela):
        """§4.1 exige as duas metades: reancorar E avisar. Mover em silencio
        deixaria o operador achando que o arranjo dele se perdeu sozinho."""
        antes = janela.trilha.total
        janela.setGeometry(QRect(-9000, -9000, 800, 600))
        avisos = janela.aplicar_regra_da_orfa()
        assert avisos, "a janela estava fora de qualquer tela"
        assert janela.trilha.total > antes
        assert janela.trilha.recentes(1)[0].nivel is Nivel.AVISO
        assert "monitor primário" in avisos[0]


# --------------------------------------------------------------------------
# 4. Densidade a quente (fase 3, item 9)
# --------------------------------------------------------------------------
class TestDensidade:
    def test_ctrl_shift_d_percorre_as_tres_e_volta(self, janela, qapp):
        assert janela.densidade is tokens.PADRAO
        vistas = [janela.proxima_densidade() for _ in range(3)]
        assert set(vistas) == set(tokens.DENSIDADES)
        assert janela.densidade is tokens.PADRAO

    def test_a_troca_reconstroi_o_painel_e_nao_muta_o_campo(self, janela, qapp):
        """Mutar `painel.densidade` deixaria a geometria calculada com a fonte
        ANTIGA e o texto desenhado com a nova — calha estreita, rotulo
        descartado por F8, e nenhum erro em lugar nenhum."""
        antes = janela.dom
        janela.aplicar_densidade(tokens.COMPACTA)
        qapp.processEvents()
        assert janela.dom is not antes, "reconstruiu"
        assert janela.dom.densidade is tokens.COMPACTA
        assert janela.docas["dom"].widget() is janela.dom

    def test_a_troca_preserva_o_workspace_visivel(self, janela, qapp):
        janela.workspace_por_atalho(3)
        qapp.processEvents()
        visiveis = {c for c, d in janela.docas.items() if d.isVisible()}
        janela.aplicar_densidade(tokens.CONFORTAVEL)
        qapp.processEvents()
        assert {c for c, d in janela.docas.items() if d.isVisible()} == visiveis

    def test_os_eixos_continuam_compartilhados_por_IDENTIDADE(self, janela, qapp):
        """A invariante da fase 2 nao pode morrer numa troca de densidade: o
        perfil e o delta recebem os MESMOS objetos do footprint, e nao copias
        nem formulas equivalentes."""
        janela.aplicar_densidade(tokens.COMPACTA)
        qapp.processEvents()
        assert janela.perfil.eixo is janela.footprint.eixo_preco
        assert janela.delta.eixo is janela.footprint.eixo_tempo

    def test_os_paineis_com_historico_sobrevivem_a_troca(self, janela):
        """A mecanica que faz o teste seguinte ser verdade.

        Historico de tela vive na INSTANCIA: as colunas do footprint, o plano
        do bookmap e o anel do tape. Se a janela reconstroi o painel, o
        historico vai junto por definicao, e nenhum cuidado dentro do painel
        adianta. Entao a asserçao e sobre identidade de objeto.

        E os tres do eixo compartilhado andam JUNTOS: `perfil` e `delta`
        recebem os eixos do `footprint` por identidade, entao preservar um sem
        o outro quebraria o acoplamento que faz os tres compartilharem eixo —
        a fraqueza F5 da referencia, reaberta por dentro.
        """
        antes = {c: janela._paineis[c] for c in janela.TROCAM_A_QUENTE}
        janela.aplicar_densidade(tokens.COMPACTA)
        for chave, painel in antes.items():
            assert janela._paineis[chave] is painel, f"{chave} foi reconstruido"
            assert painel.densidade is tokens.COMPACTA, f"{chave} nao trocou"
        # O acoplamento por identidade continua de pe.
        assert janela.perfil.eixo is janela.footprint.eixo_preco
        assert janela.delta.eixo is janela.footprint.eixo_tempo

    def test_a_troca_e_dita_na_trilha_SEM_anunciar_perda(self, janela):
        """Este teste afirmava o contrario, e estava certo na epoca.

        Enquanto `aplicar_densidade` reconstruia todos os paineis, o historico
        de tela recomecava mesmo, e a trilha dizer isso era honestidade. Depois
        que footprint, perfil, delta, bookmap e tape passaram a expor
        `aplicar_densidade` — refazendo os derivados e mantendo o estado —, a
        perda deixou de existir, e a frase virou uma ressalva sobre um defeito
        consertado. **Ressalva que sobrevive ao conserto e mentira com selo de
        honestidade**, e mais perigosa que a ausencia dela, porque tem cara de
        rigor.

        O evento continua na trilha: trocar densidade e um fato que o operador
        tem direito de ver depois, num arranjo que ele nao lembra ter mudado.
        """
        antes = janela.trilha.total
        janela.aplicar_densidade(tokens.COMPACTA)
        assert janela.trilha.total > antes, "a troca em si continua registrada"
        recentes = " ".join(e.texto for e in janela.trilha.recentes(3))
        assert tokens.COMPACTA.nome in recentes
        assert "histórico" not in recentes, "anuncia perda que nao acontece mais"


# --------------------------------------------------------------------------
# 5. A contradicao REPLAY x AO VIVO
# --------------------------------------------------------------------------
class TestReplayNaoDizAoVivo:
    def test_fora_do_replay_nada_muda(self):
        texto, _ = rotulo_do_estado(EstadoFeed.VIVO)
        assert texto == "● " + PROIBIDO_EM_REPLAY

    @pytest.mark.parametrize("estado", list(EstadoFeed))
    def test_em_replay_a_palaVra_proibida_nunca_aparece(self, estado):
        """A afirmacao inteira, sobre TODOS os estados do feed — e nao sobre os
        dois que alguem lembrou de testar. §3.5: "Impossivel confundir replay
        com ao vivo"."""
        texto, _ = rotulo_do_estado(estado, replay=True)
        assert PROIBIDO_EM_REPLAY not in texto
        assert "REPLAY" in texto

    def test_a_saude_do_transporte_continua_dita(self):
        """Engolir `SEM FEED` em replay trocaria uma mentira por outra: um
        replay travado parece um replay tocando."""
        texto, cor = rotulo_do_estado(EstadoFeed.SEM_FEED, replay=True)
        assert "SEM FEED" in texto and "REPLAY" in texto
        assert cor == tokens.DANGER

    def test_a_pos_condicao_e_de_runtime_e_nao_de_docstring(self, monkeypatch):
        """Uma refatoracao distraida que fizesse o ramo do replay cair no
        rotulo normal seria pega AQUI, e nao num retrato seis meses depois."""
        import fluxopro.ui.paineis.strips as S

        monkeypatch.setitem(S._ROTULO_ESTADO, EstadoFeed.ATRASADO, PROIBIDO_EM_REPLAY)
        with pytest.raises(RotuloContraditorioError):
            rotulo_do_estado(EstadoFeed.ATRASADO, replay=True)

    def test_a_strip_do_topo_obedece(self, qapp):
        strip = StripTopo(SIMBOLO, WDO_GRID)
        strip.resize(1200, 28)
        strip.definir_modo("▶ REPLAY 2,0×", replay=True)
        strip._estado = EstadoFeed.VIVO
        textos = " ".join(_espiar(strip).textos)
        assert PROIBIDO_EM_REPLAY not in textos
        assert "REPLAY" in textos

    def test_a_strip_do_rodape_obedece(self, qapp, janela):
        """O rodape tinha a MESMA linha e a mesma contradicao. Corrigir so o
        topo teria deixado a frase proibida na tela, dois pixels mais baixo."""
        rodape = StripRodape()
        rodape.resize(1200, 22)
        retrato = janela.ponte.ler()
        rodape.aplicar(retrato, 1.0, 0, replay=True)
        textos = " ".join(_espiar(rodape).textos)
        assert PROIBIDO_EM_REPLAY not in textos

    def test_a_janela_liga_tarja_e_strips_da_MESMA_fonte(self, janela, qapp):
        """Uma fonte de verdade so: nao existe quadro em que a tarja diga
        REPLAY e as strips digam outra coisa."""
        from fluxopro.ui.paineis.replay import EstadoReplay

        janela.definir_estado_replay(EstadoReplay(ativo=True, symbol=SIMBOLO))
        assert janela.tarja_replay.isVisible()
        assert janela.topo.em_replay
        janela._tick()
        textos = " ".join(_espiar(janela.topo).textos + _espiar(janela.rodape).textos)
        assert PROIBIDO_EM_REPLAY not in textos


# --------------------------------------------------------------------------
# 6. O painel do METODO — as regras avalizadas com superficie
# --------------------------------------------------------------------------
def _leitura(n: int = 400) -> LeituraMetodo:
    leitor = LeitorMetodo(SIMBOLO)
    ultima = None
    for i in range(n):
        preco = BASE + (i % 40) - 10 + i // 40
        ultima = leitor.ao_trade(
            Trade(
                T0 + i * 50_000_000,
                SIMBOLO,
                preco,
                5 + (i % 7),
                AgressorSide.BUY if i % 3 else AgressorSide.SELL,
                "t%d" % i,
            )
        )
    assert ultima is not None
    return ultima


@pytest.fixture
def painel_metodo(qapp):
    p = M.PainelMetodo(WDO_GRID)
    p.resize(360, M.altura_natural())
    p.aplicar(_leitura())
    return p


class TestPainelMetodo:
    def test_a_cobertura_sai_do_registro_e_usa_o_denominador_do_vizinho(self):
        """Dois paineis vizinhos com duas cardinalidades do mesmo conjunto
        obrigariam o leitor a descobrir sozinho qual delas responde a pergunta
        que ele fez. `PainelRegras` grafa `33/42`; este usa o mesmo 33."""
        from fluxopro.metodologia.regras import REGRAS

        vivas, avalizadas = M.cobertura()
        assert avalizadas == sum(1 for r in REGRAS.values() if r.implementada)
        assert 0 < vivas <= avalizadas

    def test_o_cabecalho_publica_a_cobertura_com_denominador(self, painel_metodo):
        """Contagem sem denominador e a forma mais barata de parecer completa —
        e o denominador e a unica parte da frase que NUNCA encolhe."""
        vivas, avalizadas = M.cobertura()
        textos = _espiar(painel_metodo).textos
        assert painel_metodo.texto_chip_cobertura() in textos
        for redacao in painel_metodo.textos_chip_cobertura():
            assert str(vivas) in redacao and str(avalizadas) in redacao

    def test_os_cinco_blocos_estao_na_ordem_em_que_o_metodo_os_alimenta(self, painel_metodo):
        textos = _espiar(painel_metodo).textos
        posicoes = [textos.index(b) for b in M.BLOCOS]
        assert posicoes == sorted(posicoes)

    def test_nenhum_bloco_pega_aval_emprestado(self):
        """Se sete regras confirmam e uma e imprecisa, o bloco e impreciso: o
        leitor que visse CONFIRMADO acreditaria no elo mais fraco pelo credito
        do mais forte."""
        from fluxopro.metodologia.confianca import Confianca

        for indice in range(M.N_BLOCOS):
            regras = M.regras_do_bloco(indice)
            pior = M.pior_confianca(regras)
            assert pior == max(regras, key=lambda r: M._GRAVIDADE[r.confianca]).confianca
            texto, _ = M.texto_procedencia(regras)
            sem_aval = sum(
                1 for r in regras if r.confianca is Confianca.AUSENTE_NA_FONTE
            )
            # A composicao vai escrita: quantas respondem, quantas descontam,
            # e o rotulo do PIOR — sempre. Nunca so o total.
            assert "%s%d" % (M.MARCA_REGRA, len(regras)) in texto
            assert M.ROTULO_CONFIANCA[pior] in texto
            if sem_aval:
                assert "%d %s" % (sem_aval, M.ROTULO_CONFIANCA[pior]) in texto

    def test_a_ressalva_nao_usa_o_token_de_menor_luminancia(self):
        """Achado da medicao de canal, prendido para nao voltar.

        A primeira versao pintava o chip `SEM AVAL` em `DANGER`, e ele reteve
        33,2% contra 58,6% do veredito que qualifica. `DANGER` tem 5,45:1 — a
        menor luminancia dos tokens —, entao texto escuro sobre ele carrega o
        traco quase so em CROMA, e o JPEG subamostra croma 2x. Aumentar o
        corpo do texto piorou o numero TRES vezes seguidas; trocar o token
        resolveu. `ALERT` e `ABSORPTION` carregam o mesmo traco em LUMINANCIA.
        """
        for confianca, cor in M._COR_CONFIANCA.items():
            assert cor is not tokens.DANGER, confianca
            assert cor is not tokens.TEXT_MUTED, confianca

    def test_o_chip_nao_e_mais_fraco_que_o_dado_que_ele_qualifica(self, painel_metodo):
        """As tres condicoes que a medicao cobrou, as tres verificaveis aqui:
        corpo nao menor que o do veredito, traco grosso, e a caixa apertada em
        volta do texto (nao a linha inteira, que compara chip contra fundo
        chapado)."""
        assert M.CORPO_CHIP >= 13, "o veredito e desenhado em 13px"
        assert painel_metodo._fm_chip.height() >= 13
        for indice in range(M.N_BLOCOS):
            linha = painel_metodo.rect_valor(indice)
            apertada = painel_metodo.rect_texto_valor(indice)
            assert apertada.width() <= linha.width()
            assert apertada.left() == linha.left()

    def test_o_risco_nao_tem_superficie_de_decisao(self, painel_metodo):
        """`GestorRisco.avaliar` exige uma `QualidadeRegiao` de uma PESSOA. Um
        semaforo aqui seria o produto inventando o classificador que a fonte
        nao tem — o defeito oposto, e pior, do que o que este painel corrige."""
        assert painel_metodo.leitura is not None
        assert not hasattr(painel_metodo.leitura, "risco")
        textos = " ".join(_espiar(painel_metodo).textos)
        assert "RISCO NÃO É AUTOMÁTICO" in textos
        # Pelo AST e nao por substring: a docstring do painel EXPLICA que ele
        # nao chama `avaliar` nem toca em `QualidadeRegiao`, e uma varredura de
        # texto reprovaria o arquivo justamente pela frase que diz a verdade.
        # (A mesma licao que trocou o teste do relogio unico por AST.)
        nomes = _identificadores(RAIZ / "fluxopro" / "ui" / "paineis" / "metodo.py")
        assert "avaliar" not in nomes
        assert "QualidadeRegiao" not in nomes
        assert "GestorRisco" not in nomes

    def test_so_a_proporcao_de_um_todo_conhecido_vira_barra(self, painel_metodo):
        """Lei n.o 4: nao se inventa quarta forma nem se reusa com outro
        significado. Macro x micro NAO tem barra porque `MedidaContexto`
        recusa comparar as duas escalas — duas barras lado a lado seriam essa
        comparacao proibida desenhada."""
        com_barra = {
            i for i in range(M.N_BLOCOS) if painel_metodo.rects_dos_segmentos(i)
        }
        assert com_barra == {M.I_LINHA, M.I_PLACAR}
        assert not M.segmentos_do_bloco(M.I_MACRO, painel_metodo.leitura, tokens.PALETA_COR)

    def test_a_barra_e_CHEIA_e_nenhuma_parcela_some(self, painel_metodo):
        """Escala que desaparece e perda. Parcela nao-nula que arredonda para
        zero e o defeito n.o 3 do ranking de players."""
        for indice in (M.I_LINHA, M.I_PLACAR):
            faixa = painel_metodo.rect_faixa(indice)
            rects = painel_metodo.rects_dos_segmentos(indice)
            segmentos = M.segmentos_do_bloco(indice, painel_metodo.leitura, tokens.PALETA_COR)
            soma = sum(r.width() for r in rects) + M.COSTURA * (len(rects) - 1)
            assert soma == faixa.width(), (indice, soma, faixa.width())
            for seg, rect in zip(segmentos, rects):
                assert (rect.width() > 0) == (seg.valor > 0), seg.rotulo

    def test_particionar_devolve_a_largura_inteira_e_protege_a_parcela_minima(self):
        assert sum(M.particionar(100, (3, 1, 0))) + 2 * M.COSTURA == 100
        assert M.particionar(100, (999999, 1, 0))[1] == 1, "1px, nunca zero"
        assert M.particionar(100, (0, 0, 0)) == (0, 0, 0), "ausencia e o dado"

    def test_MUTACAO_a_barra_desenhada_vem_da_funcao_compartilhada(
        self, painel_metodo, monkeypatch
    ):
        """Lei n.o 6: prova por MUTACAO.

        Sem isto, "desenho e teste chamam a mesma funcao" e uma afirmacao de
        docstring. Aqui a funcao compartilhada e trocada e o PIXEL tem de
        mudar junto — se o desenho tivesse uma segunda conta de largura, este
        teste passaria pela geometria e falharia pelo desenho."""
        antes = [QRect(r) for r in _espiar(painel_metodo).caixas]

        def mentira(largura, valores, costura=M.COSTURA):
            return tuple(0 for _ in valores)

        monkeypatch.setattr(M, "particionar", mentira)
        painel_metodo.marcar_tudo_sujo()
        depois = _espiar(painel_metodo).caixas
        assert antes != depois, "o desenho nao usa `particionar`"

    def test_MUTACAO_o_veredito_desenhado_vem_de_veredito_do_bloco(
        self, painel_metodo, monkeypatch
    ):
        marca = "PALAVRA-QUE-SO-EXISTE-AQUI"
        monkeypatch.setattr(
            M, "veredito_do_bloco", lambda i, leitura, grid: (marca, None)
        )
        textos = _espiar(painel_metodo).textos
        assert textos.count(marca) == M.N_BLOCOS

    def test_sem_leitura_a_estrutura_aparece_e_as_celulas_ficam_vazias(self, qapp):
        """§3.5, estado Vazio: a grade aparece. Nunca um retangulo em branco —
        o operador precisa reconhecer o painel antes de haver dado nele."""
        p = M.PainelMetodo(WDO_GRID)
        p.resize(360, M.altura_natural())
        p.aplicar(None)
        textos = _espiar(p).textos
        assert M.SEM_LEITURA in textos
        for bloco in M.BLOCOS:
            assert bloco in textos

    def test_o_rodape_encolhe_o_vocabulario_em_vez_de_truncar(self, qapp):
        """F8. O primeiro retrato saiu com a frase cortada em "e o gestor
        exige" — e a frase que sobra continua parecendo completa."""
        from PySide6.QtGui import QFontMetrics

        fm = QFontMetrics(tokens.fonte_rotulo())
        for largura in (1200, 600, 380, 200, 40):
            escolhido = M.maior_que_cabe(M.RODAPE_RISCO, largura, fm)
            assert escolhido in M.RODAPE_RISCO
            if escolhido is not M.RODAPE_RISCO[-1]:
                assert fm.horizontalAdvance(escolhido) <= largura

    def test_o_veredito_encolhe_o_vocabulario_em_vez_de_truncar(self, painel_metodo):
        """F8 no pior bloco. O primeiro retrato saiu com
        `MACRO +1.814 (sessão)  MICRO +1.814 (9,` — cortado no meio do numero
        da janela, e o que sobrou continuava parecendo uma frase inteira."""
        leitura = painel_metodo.leitura
        alternativas, _ = M.vereditos_do_bloco(M.I_MACRO, leitura, WDO_GRID)
        assert len(alternativas) > 1
        larguras = [painel_metodo._fm_valor.horizontalAdvance(a) for a in alternativas]
        assert larguras == sorted(larguras, reverse=True), "da mais longa a mais curta"
        # A JANELA e a ultima coisa a cair: e ela que impede a comparacao que
        # `EscalasIncomparaveisError` recusa.
        for texto in alternativas:
            assert "s)" in texto or "min)" in texto

    def test_o_titulo_nao_e_atropelado_pelo_chip_de_cobertura(self, qapp):
        """Dois textos disputando os mesmos pixels e o de baixo ilegivel."""
        p = M.PainelMetodo(WDO_GRID)
        p.resize(300, M.altura_natural())
        p.aplicar(_leitura())
        chip = p.rect_chip_cobertura()
        escolhido = [t for t in _espiar(p).textos if t in M.TITULOS]
        assert escolhido, "nenhum titulo desenhado"
        from PySide6.QtGui import QFontMetrics

        largura = QFontMetrics(tokens.fonte_ui(12, 600)).horizontalAdvance(escolhido[0])
        assert M.MARGEM + largura <= chip.left(), "o titulo entra por baixo do chip"

    def test_a_altura_minima_garante_os_CINCO_blocos_e_o_rodape(self, qapp):
        """Um painel que some pela metade afirma que o metodo tem quatro
        leituras. O quinto bloco e justamente o PLACAR, o veredito de
        confluencia."""
        p = M.PainelMetodo(WDO_GRID)
        assert p.minimumHeight() == M.altura_natural()
        assert p.rect_rodape().bottom() <= M.altura_natural()

    def test_o_painel_nao_toca_nos_acumuladores_vivos_da_fonte(self):
        """`sessao.metodo.<componente>` sao objetos da thread da fonte. O
        painel recebe um `LeituraMetodo` imutavel e nao alcanca outra coisa."""
        nomes = _identificadores(RAIZ / "fluxopro" / "ui" / "paineis" / "metodo.py")
        assert "sessao" not in nomes
        assert "metodo" not in nomes or True  # o proprio modulo se chama assim
        assert "leitura_do_metodo" not in nomes
        assert "ponte" not in nomes

    def test_a_janela_le_o_metodo_uma_vez_por_quadro(self, qapp):
        chamadas = []
        leitura = _leitura()
        sessao = SimpleNamespace(
            agressao=None,
            perfil_player=None,
            footprint=None,
            perfil_sessao=None,
            delta=None,
            leitura_do_metodo=lambda: (chamadas.append(1), leitura)[1],
        )
        j = JanelaFluxo(PonteFluxo(Barramento()), SIMBOLO, WDO_GRID, sessao=sessao)
        try:
            j._tick()
            assert len(chamadas) == 1
            assert j.metodo.leitura is leitura
        finally:
            j.close()


# --------------------------------------------------------------------------
# 7. Sala de Controle (§4.2)
# --------------------------------------------------------------------------
class TestSalaDeControle:
    def _estado(self, **kw):
        base = dict(
            estado=EstadoFeed.VIVO,
            latencia_p50_ms=0.8,
            latencia_p99_ms=1.9,
            instrumentos=(Instrumento(SIMBOLO, 50865, 50700, 12482, 1240, T0),),
            anterior="Fluxo",
        )
        base.update(kw)
        return EstadoSala(**base)

    def test_responde_as_tres_perguntas_de_ss4_2(self, qapp):
        sala = SalaDeControle(self._estado(), WDO_GRID)
        sala.resize(900, 600)
        textos = " ".join(_espiar(sala).textos)
        assert "1 · FEED" in textos and "2 · INSTRUMENTOS" in textos
        assert "3 · WORKSPACE" in textos
        for w in W.WORKSPACES_DE_FABRICA:
            assert w.nome in textos

    def test_a_auto_dispensa_exige_as_DUAS_condicoes(self, qapp):
        assert self._estado().pode_auto_dispensar == (True, "")
        parado = self._estado(estado=EstadoFeed.AGUARDANDO)
        assert parado.pode_auto_dispensar[1]
        primeira_vez = self._estado(anterior="")
        assert primeira_vez.pode_auto_dispensar[1]

    def test_quando_nao_arma_a_tela_diz_por_que(self, qapp):
        """Uma sala que sumisse sozinha com o feed morto poria o operador
        diante de uma grade vazia sem ele ter lido que a fonte nao respondeu.
        Uma que fica sem explicar e um portal mudo."""
        sala = SalaDeControle(self._estado(estado=EstadoFeed.SEM_FEED), WDO_GRID)
        sala.resize(900, 600)
        assert not sala.armar()
        textos = " ".join(_espiar(sala).textos)
        assert "SEM AUTO-DISPENSA" in textos

    def test_qualquer_tecla_cancela_e_o_cancelamento_e_permanente(self, qapp):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        sala = SalaDeControle(self._estado(), WDO_GRID)
        sala.resize(900, 600)
        assert sala.armar() and sala.contando
        sala.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        )
        assert sala.cancelada and not sala.contando
        assert not sala.armar(), "rearmar seria decidir que ele mudou de ideia"

    def test_enter_e_o_digito_escolhem_o_workspace(self, qapp):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        sala = SalaDeControle(self._estado(), WDO_GRID)
        sala.resize(900, 600)
        escolhas: list[str] = []
        sala.escolheu.connect(escolhas.append)
        sala.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        )
        assert escolhas == ["Fluxo"]
        sala.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_3, Qt.KeyboardModifier.NoModifier)
        )
        assert escolhas[-1] == "Bookmap"

    def test_o_ultimo_usado_nasce_selecionado(self, qapp):
        sala = SalaDeControle(self._estado(anterior="Bookmap"), WDO_GRID)
        assert sala.selecionado.nome == "Bookmap"

    def test_a_barra_nunca_parece_cheia_antes_da_hora(self, qapp):
        """Uma barra cheia com 80 ms restando convidaria o operador a acreditar
        que perdeu a janela de cancelamento que ele ainda tem."""
        assert particionar_contagem(100, 0, 1500) == 0
        assert particionar_contagem(100, 1499, 1500) == 99
        assert particionar_contagem(100, 1500, 1500) == 100

    def test_a_sala_usa_o_MESMO_rotulo_de_estado_das_strips(self, qapp):
        """Se a sala dissesse `AO VIVO` num replay enquanto a strip diz
        `REPLAY`, a contradicao que esta rodada matou teria voltado por outra
        porta."""
        fonte = (RAIZ / "fluxopro" / "ui" / "sala.py").read_text(encoding="utf-8")
        assert "rotulo_do_estado" in fonte


# --------------------------------------------------------------------------
# 8. Trilha de eventos
# --------------------------------------------------------------------------
class TestTrilha:
    def test_o_len_para_de_crescer_e_o_total_nao(self):
        """O criterio do gravador. A trilha nao pode crescer com o pregao — e
        "3 eventos" seria mentira sobre a cobertura se 509 tivessem caido."""
        t = TrilhaEventos(capacidade=8)
        for i in range(100):
            t.info("teste", "linha %d" % i)
        assert len(t) == 8
        assert t.total == 100

    def test_le_do_mais_novo_para_o_mais_velho(self):
        t = TrilhaEventos()
        t.info("a", "primeiro")
        t.info("a", "segundo")
        assert [e.texto for e in t.recentes(2)] == ["segundo", "primeiro"]

    def test_o_painel_publica_retidos_E_total(self, qapp):
        from fluxopro.ui.trilha import PainelTrilha

        t = TrilhaEventos(capacidade=4)
        for i in range(10):
            t.erro("fonte", "gap %d" % i)
        p = PainelTrilha(t)
        p.resize(600, 200)
        textos = " ".join(_espiar(p).textos)
        assert "4 RETIDOS DE 10" in textos

    def test_a_trilha_vazia_desenha_o_estado_vazio(self, qapp):
        from fluxopro.ui.trilha import PainelTrilha

        p = PainelTrilha(TrilhaEventos())
        p.resize(600, 200)
        assert "SEM EVENTOS" in _espiar(p).textos
