"""QA independente NEXO AI: contratos observaveis, sem alterar implementacao.

Fixtures tipadas sao entradas sinteticas rotuladas, nunca evidencia de pregao.
Decisoes direcionais sao calculadas pelo MotorDecisaoASG de verdade. Integracao
usa a fabrica REAL de scripts.painel, QTest e eventos no barramento. Nenhum
teste apenas chama o callback F6/F7 para fingir que o teclado funcionou.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPlainTextEdit

from fluxopro.analytics.renko import FaseRenko
from fluxopro.asg import (EstadoMaker, LeituraASG, MakerProxySnapshot,
                         MotorDecisaoASG, ProcedenciaASG as ProcedenciaMotor,
                         RegiaoOperacional)
from fluxopro.asg.sinal_ultra import (ConfigSinalUltra, DirecaoUltra,
                                      EntradaSinalUltra, MotorSinalUltra)
from fluxopro.core.eventos import AgressorSide, Side, Trade, WDO_GRID
from fluxopro.ui import tokens
from fluxopro.ui.paineis import nexo
from fluxopro.ui.paineis.asg import (
    ConfiancaASG, ContextoBrutoASGSnapshot, DadosASGSnapshot,
    DecisaoASGSnapshot, DirecaoASG, EstadoASG, LinhaMatrizASG,
    MatrizASGSnapshot, NivelBrutoASG, PainelNexoMercadoASG,
    ProcessamentoASGSnapshot, ProcedenciaASG, TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.nexo import assistente, candles
from fluxopro.ui.workspace import WORKSPACES_DE_FABRICA
from scripts.auditar_nexo_ai import (
    ROTULO, enriquecer_historia, fechar_cenario, identidade_dados,
    parar_timers, quadro_painel, render_painel, tecla_real,
)
from scripts.painel import montar_cenario_controlado_asg

S = 1_000_000_000
TS = 100 * S


def linha(nome, forca, confianca=ConfiancaASG.ALTA):
    return LinhaMatrizASG(nome, DirecaoASG.COMPRA if forca > 0 else DirecaoASG.VENDA,
                          f"{forca:+.2f}", forca, confianca, ProcedenciaASG.DERIVADO,
                          evidencias=7, detalhe=ROTULO)


def decisao_do_motor(lado=Side.BUY, ts=TS):
    sinal = 1 if lado is Side.BUY else -1
    maker = MakerProxySnapshot(
        timestamp_ns=ts, symbol="WDOV26",
        estado=EstadoMaker.COMPRADOR if sinal > 0 else EstadoMaker.VENDEDOR,
        direcao=lado, pontuacao=sinal * .8, confianca=.9, cobertura=.9,
        persistencia=1., componentes=(), procedencia=ProcedenciaMotor.OBSERVADA,
        percent=sinal * 80., persistence_ns=3 * S,
        source="SIMULADOR", book_kind="MBO", feed_quality=1., stability=.9)
    leitura = LeituraASG.do_maker(maker, provenance=(ROTULO,))
    regiao = RegiaoOperacional("WDOV26", ts, 9998, 10002, nome=ROTULO,
                               confianca=.9, procedencia=ProcedenciaMotor.OBSERVADA,
                               invalidacao_ticks=9998 if sinal > 0 else 10002)
    decisao = MotorDecisaoASG().avaliar(leitura, regiao, 10000)
    assert decisao.confirmacao, "Precondicao: o motor real deve confirmar a entrada controlada"
    return DecisaoASGSnapshot.de_decisao(decisao)


def estado_controlado(*, lado=Side.BUY, operacional=EstadoASG.AO_VIVO,
                      book=True, linhas=None, ts=TS):
    saudavel = operacional in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
    sinal = 1 if lado is Side.BUY else -1
    if linhas is None:
        linhas = (linha("MACRO", sinal * .9), linha("MICRO", sinal * .3),
                  linha("MAKERPROXY", sinal * .8))
    decisao = (replace(decisao_do_motor(lado, ts), estado=operacional) if saudavel else
               DecisaoASGSnapshot(ts, estado=operacional))
    # Retencao de linhas antigas em erro e deliberada: a UI deve suprimi-las.
    snapshot = WorkspaceASGSnapshot(
        ts, DadosASGSnapshot(ts, estado=operacional, fonte=ROTULO, detalhe=ROTULO,
                            confianca=ConfiancaASG.ALTA),
        ProcessamentoASGSnapshot(ts, estado=operacional, versao="qa-controlled-v1"),
        MatrizASGSnapshot(ts, estado=operacional, linhas=linhas, cobertura="2/2"),
        decisao, TrilhaEvidenciasASGSnapshot(ts, estado=operacional),
        contexto_bruto=ContextoBrutoASGSnapshot(
            ts, estado=operacional,
            bids=(NivelBrutoASG(9999, 100, 3),) if book else (),
            asks=(NivelBrutoASG(10001, 100, 3),) if book else ()))
    return nexo.EstadoNexo(
        snapshot=snapshot, serie=((ts - S, 9999, sinal * .2, 10), (ts, 10000, sinal * .6, 20)),
        grid=WDO_GRID, paleta=tokens.PALETA_COR,
        maker=next((l for l in linhas if l.componente == "MAKERPROXY"), None),
        leituras=(), largura=1480, altura=800,
        serie_forca_ai=((ts - S, sinal * .2), (ts, sinal * .6)))


def ultra_pendente(ts=TS, janela=12 * S, decorrido=3 * S):
    motor = MotorSinalUltra(ConfigSinalUltra(persistencia_minima_ns=janela))
    entrada = EntradaSinalUltra(ts - decorrido, DirecaoUltra.COMPRA, FaseRenko.TENDENCIA,
                                DirecaoUltra.COMPRA, .9, True)
    motor.atualizar(entrada)
    return motor.atualizar(replace(entrada, timestamp_ns=ts))


def imagem(estado, rect=QRect(13, 17, 380, 790), clip=None):
    img = QImage(rect.right() + 19, rect.bottom() + 23, QImage.Format.Format_ARGB32)
    img.fill(QColor("#fe00fd"))
    painter = QPainter(img)
    try:
        if clip is not None:
            painter.setClipRect(clip)
        assistente.desenhar(painter, rect, estado)
    finally:
        painter.end()
    return img


@pytest.mark.parametrize("operacional", [EstadoASG.AGUARDANDO, EstadoASG.ATRASADO,
                                        EstadoASG.ERRO, EstadoASG.SEM_BOOK])
def test_degradacao_suprime_forca_historico_e_confirmacao_mesmo_com_residuos(operacional):
    estado = replace(estado_controlado(operacional=operacional), sinal_ultra=ultra_pendente())
    m = assistente.compor(estado)
    assert not m.saudavel
    assert m.titulo not in ("COMPRA", "VENDA")
    assert m.fase == "CONFIRMAÇÃO BLOQUEADA"
    assert not any(c[2] for c in m.condicoes)
    assert m.progresso is None and m.nivel_confianca is None
    assert m.forca is None and m.maker is None and not m.historico
    assert not m.divergente


def test_primeiro_quadro_sem_dados_nao_inventa_zero_ou_cinquenta_porcento(qapp):
    painel = PainelNexoMercadoASG()
    try:
        m = assistente.compor(painel._estado_nexo())
        assert m.titulo == "SEM DADOS"
        assert m.forca is None and m.maker is None and m.progresso is None
        assert m.nivel_confianca is None and m.historico == ()
    finally:
        painel.close()
        painel.deleteLater()


@pytest.mark.parametrize("operacional", [EstadoASG.AO_VIVO, EstadoASG.REPLAY])
@pytest.mark.parametrize("lado_ausente", ["bids", "asks", "ambos", "contexto"])
def test_feed_saudavel_sem_livro_completo_nao_confirma(operacional, lado_ausente):
    e = estado_controlado(operacional=operacional)
    contexto = e.snapshot.contexto_bruto
    if lado_ausente == "contexto":
        contexto = None
    else:
        campos = {k: () for k in ("bids", "asks") if lado_ausente in (k, "ambos")}
        contexto = replace(contexto, **campos)
    m = assistente.compor(replace(e, snapshot=replace(e.snapshot, contexto_bruto=contexto),
                                 sinal_ultra=ultra_pendente()))
    assert m.estado_feed == "SEM BOOK" and not m.saudavel
    assert m.titulo == "SEM BOOK" and not any(c[2] for c in m.condicoes)
    assert m.forca is None and m.maker is None and m.progresso is None


@pytest.mark.parametrize("lado,titulo,forca", [(Side.BUY, "COMPRA", .6), (Side.SELL, "VENDA", -.6)])
def test_compra_e_venda_publicadas_pelo_motor_chegam_ao_card(lado, titulo, forca):
    e = estado_controlado(lado=lado)
    m = assistente.compor(e)
    assert m.titulo == titulo
    assert m.forca == pytest.approx(forca)  # .9 + .3; Maker .8 NAO participa
    assert m.maker == pytest.approx(.8 if lado is Side.BUY else -.8)
    assert m.motivo == e.snapshot.decisao.motivo
    assert m.procedencia == e.snapshot.decisao.procedencia.value
    assert m.formula == "qa-controlled-v1"


@pytest.mark.parametrize("maker,divergente", [(-.9, True), (.9, False), (0., False)])
def test_divergencia_e_observada_sem_promover_maker_a_forca(maker, divergente):
    e = estado_controlado(linhas=(linha("MACRO", .9), linha("MICRO", .3), linha("MAKERPROXY", maker)))
    m = assistente.compor(e)
    assert m.forca == pytest.approx(.6)
    assert m.maker == pytest.approx(maker) and m.divergente is divergente
    assert m.titulo == "COMPRA"  # alerta auxiliar nao reescreve a decisao principal


@pytest.mark.parametrize("invalido", [float("nan"), float("inf"), float("-inf"), True])
def test_forca_invalida_nao_contamina_media(invalido):
    e = estado_controlado(linhas=(linha("MACRO", .3), linha("MICRO", invalido)))
    m = assistente.compor(e)
    assert math.isfinite(m.forca) and m.forca == pytest.approx(.3)


def test_maker_sozinho_nao_vira_forca_nem_historico():
    e = estado_controlado(linhas=(linha("MAKERPROXY", .9),
                                  linha("MACRO", .7, ConfiancaASG.INDISPONIVEL)))
    m = assistente.compor(e)
    assert m.forca is None and m.historico == () and m.janela_s is None
    assert m.maker == .9


@pytest.mark.parametrize("conf,nivel,rotulo", [(ConfiancaASG.ALTA, 3, "ALTA"),
                                             (ConfiancaASG.MEDIA, 2, "MEDIA"),
                                             (ConfiancaASG.BAIXA, 1, "BAIXA"),
                                             (ConfiancaASG.INDISPONIVEL, None, "SEM DADOS")])
def test_confianca_enum_e_nivel_na_pintura_nunca_probabilidade(qapp, monkeypatch, conf, nivel, rotulo):
    e = estado_controlado()
    e = replace(e, snapshot=replace(e.snapshot, decisao=replace(e.snapshot.decisao, confianca=conf)))
    rect = QRect(13, 17, 380, 790)
    card = assistente.retangulos_internos(rect)["confianca"]
    textos = []
    original = assistente._texto

    def observar(p, r, texto, *args, **kwargs):
        if card.contains(r.center()):
            textos.append(texto)
        return original(p, r, texto, *args, **kwargs)

    monkeypatch.setattr(assistente, "_texto", observar)
    imagem(e, rect)
    assert rotulo in textos
    assert (f"{nivel}/3" if nivel else "—") in textos
    assert not any("%" in texto for texto in textos)
    assert assistente.compor(e).nivel_confianca == nivel
    assert "nível, não probabilidade" in assistente.texto_auditoria(e)


def test_progresso_usa_timestamp_e_janela_da_instancia_do_motor():
    e = replace(estado_controlado(), sinal_ultra=ultra_pendente(janela=12 * S, decorrido=3 * S))
    assert assistente.compor(e).progresso == .25  # nao .6 de um default de 5 s
    assert assistente.compor(e) == assistente.compor(e)
    with pytest.raises(FrozenInstanceError):
        assistente.compor(e).progresso = 1


@pytest.mark.parametrize("defasagem", [-S, S])
def test_ultra_de_outro_timestamp_nao_publica_progresso(defasagem):
    e = replace(estado_controlado(), sinal_ultra=ultra_pendente(ts=TS + defasagem))
    assert assistente.compor(e).progresso is None


def test_ultra_de_outro_timestamp_nao_publica_fase_confirmando():
    e = replace(estado_controlado(), sinal_ultra=ultra_pendente(ts=TS - S))
    assert assistente.compor(e).fase not in ("CONFIRMANDO", "FILTRO ATIVO"), (
        "Fase de confirmacao de snapshot antigo esta visivel como corrente")


def test_historico_nao_antecipa_timestamp_e_janela_reflete_amostras_usadas():
    e = replace(estado_controlado(), serie_forca_ai=((TS - 4*S, -.2),
                                                   (TS - 2*S, float("nan")),
                                                   (TS, .7), (TS + S, -1.)))
    m = assistente.compor(e)
    assert m.historico == (-.2, .7) and m.janela_s == 4.


def test_sem_confluencia_pendente_zero_nao_mostra_cem_porcento():
    motor = MotorSinalUltra()
    ultra = motor.atualizar(EntradaSinalUltra(
        TS, DirecaoUltra.NENHUMA, FaseRenko.TENDENCIA,
        DirecaoUltra.NENHUMA, .9, True))
    assert ultra.pendente_desde_ns == 0
    e = replace(estado_controlado(), sinal_ultra=ultra)
    m = assistente.compor(e)
    assert m.fase == "SEM CONFLUÊNCIA"
    assert m.progresso is None, "SEM_SINAL com pendente0 fabricou 100%"


def test_historico_ai_nao_reutiliza_serie_legada():
    e = replace(estado_controlado(), serie_forca_ai=())
    assert e.serie  # o legado tem dados; nao sao a mesma formula
    assert assistente.compor(e).historico == ()


def test_procedencia_expoe_valores_exatos_e_historico_recalculavel():
    e = estado_controlado(linhas=(linha("MACRO", .123456789),
                                 linha("MICRO", .3), linha("MAKERPROXY", -.87654321)))
    e = replace(e, serie_forca_ai=((TS-S, .123456789), (TS, .2117283945)))
    texto = assistente.texto_auditoria(e)
    assert repr(assistente.compor(e).forca) in texto
    for l in e.snapshot.matriz.linhas:
        assert f"força={l.forca!r}" in texto
    for ts, valor in e.serie_forca_ai:
        assert f"{ts} | {valor!r}" in texto


def test_historico_48_congelado_dedup_e_formula_consistente(qapp):
    painel = PainelNexoMercadoASG()
    try:
        for i in range(60):
            valor = .1 + i / 100
            e = estado_controlado(ts=TS + i*S, linhas=(linha("MACRO", valor),
                linha("MICRO", .3), linha("MAKERPROXY", -.99),
                linha("REGIME", 1., ConfiancaASG.INDISPONIVEL)))
            painel.aplicar(e.snapshot)
            m = assistente.compor(painel._estado_nexo())
            assert m.forca == pytest.approx((valor + .3) / 2)
            assert m.historico[-1] == pytest.approx(m.forca)
        congelado = painel._estado_nexo()
        assert isinstance(congelado.serie_forca_ai, tuple)
        assert len(congelado.serie_forca_ai) == 48
        assert congelado.serie_forca_ai[0][0] == TS + 12*S
        copia = congelado.serie_forca_ai
        painel.aplicar(e.snapshot)
        assert painel._estado_nexo().serie_forca_ai == copia
        painel.aplicar(estado_controlado(ts=TS + 60*S).snapshot)
        assert congelado.serie_forca_ai == copia  # retrato anterior nao acompanha deque
        assert len(painel._estado_nexo().serie_forca_ai) == 48
        painel.aplicar(estado_controlado(ts=TS + 61*S, operacional=EstadoASG.ERRO).snapshot)
        assert painel._estado_nexo().serie_forca_ai == ()
        painel.aplicar(estado_controlado(ts=TS + 62*S).snapshot)
        assert len(painel._estado_nexo().serie_forca_ai) == 1
        painel.aplicar(estado_controlado(ts=TS + 10*S).snapshot)
        regressivo = painel._estado_nexo().serie_forca_ai
        assert len(regressivo) <= 1
        assert all(ts <= TS + 10*S for ts, _ in regressivo)
    finally:
        painel.close()
        painel.deleteLater()


def test_ultra_so_e_avaliado_depois_do_mercado_do_quadro(qapp, monkeypatch):
    """O filtro precisa enxergar o Renko alimentado pelo Instantaneo atual.

    A janela hidrata o snapshot ASG e, em seguida, distribui o mesmo retrato
    bruto aos agregadores de mercado. Avaliar entre essas duas etapas deixa o
    ULTRA sempre um quadro atrasado; alimentar o contexto duas vezes também
    distorce candles/VAP. O teste observa a ordem real, sem fabricar um
    snapshot Ultra pronto.
    """

    painel = PainelNexoMercadoASG()
    chamadas = []
    original = PainelNexoMercadoASG._atualizar_sinal_ultra

    def observar(self, timestamp_ns):
        chamadas.append((timestamp_ns, len(self._renko.tijolos)))
        original(self, timestamp_ns)

    monkeypatch.setattr(PainelNexoMercadoASG, "_atualizar_sinal_ultra", observar)
    try:
        ts = TS + 10 * S
        snapshot = estado_controlado(ts=ts).snapshot
        painel.aplicar(snapshot, alimentar_contexto=False)
        assert chamadas == []

        negocios = tuple(
            SimpleNamespace(
                timestamp_ns=ts + indice * 1_000_000,
                price=10000 + indice * 4,
                qty=1,
                aggressor=1,
                agressor=1,
            )
            for indice in range(5)
        )
        painel.aplicar_mercado(
            SimpleNamespace(
                novos_trades=negocios,
                ultimo_preco=negocios[-1].price,
                ultimo_evento_ns=negocios[-1].timestamp_ns,
            )
        )

        assert chamadas[-1][0] == ts
        assert chamadas[-1][1] > 0, "ULTRA foi avaliado antes do Renko atual"
        assert painel.total_itens() == len(negocios)
    finally:
        painel.close()
        painel.deleteLater()


@pytest.mark.parametrize("tamanho", [(280, 510), (380, 790), (490, 950)])
def test_render_deterministico_e_fora_do_recorte_intacto(qapp, tamanho):
    e = replace(estado_controlado(), sinal_ultra=ultra_pendente())
    rect = QRect(13, 17, *tamanho)
    primeira = imagem(e, rect)
    assert primeira == imagem(e, rect)
    sentinela = QColor("#fe00fd")
    for faixa in (QRect(0, 0, primeira.width(), rect.top()),
                  QRect(0, rect.bottom() + 1, primeira.width(), 22),
                  QRect(0, rect.top(), rect.left(), rect.height()),
                  QRect(rect.right() + 1, rect.top(), 18, rect.height())):
        esperado = QImage(faixa.size(), QImage.Format.Format_ARGB32)
        esperado.fill(sentinela)
        assert primeira.copy(faixa) == esperado
    clip = rect.adjusted(21, 31, -19, -23)
    parcial = imagem(e, rect, clip)
    assert parcial.copy(clip) == primeira.copy(clip)
    fora = QRect(rect.left(), rect.top(), rect.width(), 30)
    esperado = QImage(fora.size(), QImage.Format.Format_ARGB32)
    esperado.fill(sentinela)
    assert parcial.copy(fora) == esperado  # respeita clip do chamador


def test_tres_cards_mudam_pixels_com_suas_leituras_reais(qapp):
    rect = QRect(13, 17, 380, 790)
    caixas = assistente.retangulos_internos(rect)
    a = estado_controlado(lado=Side.BUY)
    b = estado_controlado(lado=Side.SELL)
    b = replace(b, snapshot=replace(b.snapshot, decisao=replace(b.snapshot.decisao, confianca=ConfiancaASG.BAIXA)))
    ia, ib = imagem(a, rect), imagem(b, rect)
    for nome in ("estado", "confianca", "fluxo"):
        assert ia.copy(caixas[nome]) != ib.copy(caixas[nome]), f"Card {nome} nao reage ao snapshot"


@pytest.mark.parametrize("quadro", [QRect(0, 0, 1280, 570), QRect(11, 23, 1480, 740),
                                   QRect(0, 0, 1920, 960)])
def test_caixas_direitas_iguais_ao_contrato_original(quadro):
    # Baseline independente do mapa retornado pela implementacao candidata:
    # escrito a mao de proposito, para o teste nao se comparar consigo mesmo.
    #
    # ATUALIZADO DUAS VEZES, sempre com o print na frente do operador:
    #
    #   31/08/2026 — "AMPLIE A AREA DO GRAFICO DE RENKO (...) preciso ver um
    #   periodo maior": `forca` de 0,22 para 0,34.
    #
    #   01/09/2026 — "ABRA MAIS O GRAFICO RENKO, PARA EU CONSEGUIR VER MELHOR
    #   ALVOS": `forca` de 0,34 para 0,52, `candles` comecando em 0,53. Junto
    #   com o teto de escala em `forca.FATORES_DECLARAVEIS`, porque so
    #   aumentar a altura COMPRIMIA os alvos (mais altura com o mesmo fator =
    #   mais faixa de preco na tela) — ver a nota longa la.
    #
    # O que este teste vigia NAO mudou nas duas vezes, e e por isso que ele
    # falhou de proposito nas duas: a coluna direita tem de ser IDENTICA nos
    # dois layouts e o assistente nao pode invadir nenhuma das tres caixas.
    # A baseline e escrita a mao para o teste nao se comparar consigo mesmo.
    original = {"forca": (.63, 0., 1., .52), "candles": (.63, .53, .98, .85),
                "pressao": (.63, .86, 1., 1.)}
    caixas = assistente.caixas_integradas(quadro)
    for nome, (x0, y0, x1, y1) in original.items():
        esperado = QRect(quadro.x() + round(quadro.width()*x0), quadro.y() + round(quadro.height()*y0),
                         round(quadro.width()*x1)-round(quadro.width()*x0),
                         round(quadro.height()*y1)-round(quadro.height()*y0))
        assert caixas[nome] == esperado
        assert not caixas["assistente"].intersects(caixas[nome])
    internos = assistente.retangulos_internos(caixas["assistente"])
    for nome, r in internos.items():
        assert caixas["assistente"].contains(r), nome
    sequencia = ("nucleo", "estado", "confianca", "fluxo", "detalhes")
    for antes, depois in zip(sequencia, sequencia[1:]):
        assert internos[antes].bottom() < internos[depois].top()
    assert internos["nucleo"].height() > internos["estado"].height()


@pytest.fixture
def cenario(qapp, monkeypatch):
    monkeypatch.delenv("FLUXOPRO_NEXO_AI", raising=False)
    janela, sessao, manifesto = montar_cenario_controlado_asg(EstadoASG.AO_VIVO, largura=1480, altura=900)
    parar_timers(janela)
    try:
        yield janela, sessao, manifesto
    finally:
        fechar_cenario(janela, sessao)


def test_ai_default_e_f6_teclado_abre_procedencia_congelada(cenario, qapp):
    janela, sessao, _ = cenario
    painel = janela.asg.nexo
    assert painel._nexo_ai_ativo
    ts_antigo = painel._snapshot.timestamp_ns
    tecla_real(janela, painel, Qt.Key.Key_F6)
    dialogo = painel._dialogo_nexo_ai
    assert isinstance(dialogo, QDialog) and dialogo.isVisible()
    editor = dialogo.findChild(QPlainTextEdit, "nexo_ai_auditoria")
    assert editor.isReadOnly()
    texto = editor.toPlainText()
    assert str(ts_antigo) in texto and "SNAPSHOT CONGELADO" in texto
    assert "Procedência:" in texto and "MATRIZ:" in texto and "EVIDÊNCIAS:" in texto
    sessao.barramento.publicar(Trade(ts_antigo + S, janela.simbolo, 10003, 45,
                                    AgressorSide.BUY, "QA-F6-NAO-E2E"))
    janela._tick()
    qapp.processEvents()
    assert painel._snapshot.timestamp_ns > ts_antigo
    assert editor.toPlainText() == texto, "Dialogo aberto mudou com o feed"
    dialogo.close()
    tecla_real(janela, painel, Qt.Key.Key_F6)
    assert painel._dialogo_nexo_ai is dialogo
    assert str(painel._snapshot.timestamp_ns) in editor.toPlainText()
    assert editor.toPlainText() != texto


def test_f6_area_clicavel_abre_dialogo_real(cenario, qapp):
    janela, _, _ = cenario
    painel = janela.asg.nexo
    central = assistente.caixas_integradas(quadro_painel(painel))["assistente"]
    pos = assistente.retangulos_internos(central)["detalhes"].center()
    QTest.mouseClick(painel, Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()
    assert painel._dialogo_nexo_ai is not None and painel._dialogo_nexo_ai.isVisible()


def test_tooltip_dos_raios_usa_regiao_real_do_compositor(cenario, qapp, monkeypatch):
    from PySide6.QtWidgets import QToolTip
    janela, _, _ = cenario
    painel = janela.asg.nexo
    regiao = assistente.caixas_integradas(quadro_painel(painel))["estatistica"]
    pos = regiao.topRight()
    pos.setX(pos.x() - 10)
    pos.setY(pos.y() + 35)
    textos = []
    monkeypatch.setattr(QToolTip, "showText", lambda *args: textos.append(args[1]))
    QTest.mouseMove(painel, pos)
    qapp.processEvents()
    assert textos and "Pilhas separadas" in textos[-1]


def test_f7_preserva_objetos_candles_renko_snapshot_e_pixels_direitos(
        cenario, qapp, monkeypatch):
    # RELOGIO CONGELADO — este teste compara PIXELS do painel inteiro antes e
    # depois de F7, e a regiao da analise desenha "HA n S", cuja fonte e
    # `MotorAnaliseClaude.idade_s` -> `time.monotonic()`. Se a execucao cruza
    # a virada de um segundo entre os dois renders, o texto muda e a
    # comparacao falha por uma variavel que nao tem nada a ver com F7.
    #
    # Foi assim que ele falhou tres vezes em 02-03/09/2026, sempre com CPU
    # disputada (app aberto, sondas de replay), e sempre passando com a
    # maquina livre. Provado desligando o motor de analise: com
    # `FLUXOPRO_ANALISE_IA=0` passa sob a mesma carga.
    #
    # Congelar a idade nao enfraquece o teste: o que ele afirma e que F7 nao
    # altera pixel: manter constante o que F7 nao controla e o que torna a
    # afirmacao mensuravel.
    from fluxopro.analytics.analise_claude import MotorAnaliseClaude

    monkeypatch.setattr(MotorAnaliseClaude, "idade_s", lambda self, agora_s=None: 12.0)

    janela, sessao, _ = cenario
    historia = enriquecer_historia(janela, sessao)
    painel = janela.asg.nexo
    assert historia["end_ns"] - historia["start_ns"] >= 6 * 3600 * S
    assert len(painel._candles_m15.candles_fechados) >= 70
    assert len(painel._candles_15m.candles_fechados) >= 23
    assert len(painel._renko.tijolos) > 10
    antes = identidade_dados(painel)
    ai = render_painel(painel)
    tecla_real(janela, painel, Qt.Key.Key_F7)
    assert not painel._nexo_ai_ativo
    classico = render_painel(painel)
    assert identidade_dados(painel) == antes
    for nome in ("forca", "candles", "pressao"):
        r = nexo.retangulos(quadro_painel(painel))[nome]
        assert ai.copy(r) == classico.copy(r), f"Pixels de {nome} mudaram com F7"
    tecla_real(janela, painel, Qt.Key.Key_F7)
    assert painel._nexo_ai_ativo and identidade_dados(painel) == antes
    assert render_painel(painel) == ai


def test_candles_continuam_editaveis_pelo_mouse_com_ai(cenario, qapp):
    janela, _, _ = cenario
    painel = janela.asg.nexo
    ids = (id(painel._candles_m15), id(painel._candles_15m), id(painel._renko))
    caixa = painel._retangulo_candles()
    barra = QRect(caixa.left(), caixa.top() + 14, caixa.width(), candles.ALTURA_BARRA_CONTROLES)
    pos = candles.retangulos_controles(barra)["timeframe"].center()
    for esperado in (15, 5):
        QTest.mouseClick(painel, Qt.MouseButton.LeftButton, pos=pos)
        qapp.processEvents()
        assert painel._timeframe_candles_min == esperado
    assert ids == (id(painel._candles_m15), id(painel._candles_15m), id(painel._renko))
    assert painel._nexo_ai_ativo


def test_painel_oculto_nao_desenha_novos_quadros_com_eventos_no_bus(cenario, qapp):
    janela, sessao, _ = cenario
    painel = janela.asg.nexo
    painel.iniciar_relogio()
    assert janela.workspace_por_atalho(1)
    qapp.processEvents()
    assert not painel.isVisible() and not painel._timer.isActive()
    contador = painel._quadros_desenhados
    ts = painel._snapshot.timestamp_ns
    for i in range(3):
        sessao.barramento.publicar(Trade(ts + (i + 1)*S, janela.simbolo, 10005 + i,
                                        10, AgressorSide.BUY, f"QA-HIDDEN-{i}"))
        janela._tick()
    QTest.qWait(100)
    assert painel._quadros_desenhados == contador
    assert janela.workspace_por_atalho(5)
    qapp.processEvents()
    assert painel.isVisible() and painel._snapshot.timestamp_ns > ts
    # O showEvent rearma um QTimer de 16ms: processEvents nao espera o
    # vencimento desse timer. Aguardar seu ciclo testa a retomada real.
    QTest.qWait(50)
    assert painel._quadros_desenhados > contador


def test_workspaces_legados_preservam_docas_e_instancias(cenario, qapp):
    janela, _, _ = cenario
    paineis = tuple(id(p) for p in janela.paineis)
    for workspace in WORKSPACES_DE_FABRICA:
        assert janela.workspace_por_atalho(workspace.atalho)
        qapp.processEvents()
        assert janela.workspace is workspace
        assert {k for k, d in janela.docas.items() if d.isVisible()} == set(workspace.docas)
        assert tuple(id(p) for p in janela.paineis) == paineis
    assert janela.workspace_por_atalho(5)
    qapp.processEvents()
    assert janela.asg.nexo.isVisible() and janela.asg.nexo._nexo_ai_ativo


@pytest.mark.parametrize("estado", [EstadoASG.ATRASADO, EstadoASG.SEM_BOOK, EstadoASG.ERRO])
def test_degradacao_no_caminho_real_ate_modelo_do_card(qapp, estado):
    janela, sessao, _ = montar_cenario_controlado_asg(estado, largura=1280, altura=720)
    try:
        parar_timers(janela)
        m = assistente.compor(janela.asg.nexo._estado_nexo())
        assert janela.asg.nexo._snapshot.estado_operacional is estado
        assert not m.saudavel and not any(c[2] for c in m.condicoes)
        assert m.forca is None and m.maker is None and m.progresso is None
    finally:
        fechar_cenario(janela, sessao)


# ===== RENKO e FILHA de DECISAO: Renko e contexto, nao gate
def test_renko_nao_aparece_como_gate_da_decisao():
    """Mesmo sem direcao, somente os gates reais aparecem no diagnostico."""
    from fluxopro.ui.paineis.nexo import nucleo as _nucleo

    estado = estado_controlado(lado=Side.BUY)
    estado = replace(estado, snapshot=replace(
        estado.snapshot, decisao=replace(estado.snapshot.decisao,
                                         direcao=DirecaoASG.AGUARDAR)))
    cond = _nucleo._condicoes_ultra(estado, DirecaoASG.AGUARDAR)
    # 02/09/2026: DECISAO e CONTEXTO sairam do painel (eram o mesmo booleano
    # e ficavam acesas 100,00% do tempo). Sem direcao, elas voltam como a
    # UNICA linha BASE — que e quando de fato informam alguma coisa.
    assert [item.rotulo for item in cond] == ["BASE", "PERSISTENCIA"]
    assert not cond[0].atendida


def test_renko_contrario_nao_bloqueia_confluencia():
    """Renko contrario continua sendo contexto e nao bloqueia o filtro."""
    from fluxopro.ui.paineis.nexo import nucleo as _nucleo

    estado = estado_controlado(lado=Side.BUY)
    cond = _nucleo._condicoes_ultra(estado, DirecaoASG.COMPRA)
    # Base satisfeita: sobra so o que varia. O Renko contrario nao acrescenta
    # linha nenhuma, que e exatamente o ponto — ele nao e gate.
    assert [item.rotulo for item in cond] == ["PERSISTENCIA"]
    assert not cond[0].atendida  # persistencia ainda e o gate restante


def test_o_painel_so_mostra_o_que_VARIA_e_a_base_aparece_quando_falha():
    """MEDIDO EM TEMPO DE MERCADO (426,3 min do replay de 31/08):
    `DECISAO` e `CONTEXTO` acesas 100,00% do tempo, e ambas eram o MESMO
    booleano. Condicao sempre verdadeira nao discrimina nada.

    Elas nao foram apagadas: voltam como uma unica linha BASE quando deixam
    de estar satisfeitas — que e quando viram informacao. Sumir com elas por
    completo trocaria um painel que nao ensina nada por um painel cego.

    Os dois layouts leem a MESMA funcao pura, entao o modelo do layout novo
    tem de propagar isso, senao a mudanca para na fronteira.
    """

    base_ok = estado_controlado(lado=Side.BUY)
    assert [c[0] for c in assistente.compor(base_ok).condicoes] == ["PERSISTENCIA"]

    sem_direcao = replace(base_ok, snapshot=replace(
        base_ok.snapshot, decisao=replace(base_ok.snapshot.decisao,
                                          direcao=DirecaoASG.AGUARDAR)))
    m = assistente.compor(sem_direcao)
    assert [c[0] for c in m.condicoes] == ["BASE", "PERSISTENCIA"]
    assert m.condicoes[0][2] is False, "BASE apareceu, mas marcada como atendida"
