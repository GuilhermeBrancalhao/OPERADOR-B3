"""Replay: a tarja que não pode morrer, o transporte, e a retenção dos dois.

A tarja de replay é o caso extremo da lei do canal deste projeto — *o canal
preserva o veredito e apaga a ressalva* (`scripts/retencao.py`). Aqui o
"veredito" é a tela inteira de números de pregão e a "ressalva" é a
informação de que nada daquilo está acontecendo agora. Se a ressalva morre, o
espectador de uma transmissão vê um pregão ao vivo que não existe.

Então este arquivo afirma coisas que num painel comum seriam exagero:

* a tarja é da JANELA (largura do hospedeiro, topo, por cima), e continua
  sendo depois de redimensionar;
* ela usa o par de maior contraste da tela e é BLOCO PREENCHIDO, que é a
  forma que a compressão com perdas menos ataca;
* ela **não trunca** — a fonte encolhe até caber;
* ela carrega quatro portadores independentes da mesma ressalva.

E as duas afirmações que valem para qualquer painel da casa: quanto trabalho
um quadro custa (região suja), e que nada aqui cresce com o tempo.
"""

from __future__ import annotations

import dataclasses
from collections import Counter, deque
from datetime import date

import pytest

from fluxopro.ui import tokens
from fluxopro.ui.paineis import replay as rp
from fluxopro.ui.paineis.bookmap import contraste
from fluxopro.ui.paineis.replay import (
    VELOCIDADES,
    ControlesReplay,
    EstadoReplay,
    TarjaReplay,
    estado_de_entrada,
    texto_velocidade,
)
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

_T0 = 1_700_000_000_000_000_000
_S = 1_000_000_000
_SESSAO = EstadoReplay(
    ativo=True,
    symbol="WDOV26",
    data=date(2026, 12, 6),
    inicio_ns=_T0,
    fim_ns=_T0 + 3600 * _S,
    posicao_ns=_T0 + 1800 * _S,
    velocidade=2.0,
)


_CONTAINERS = (list, tuple, set, frozenset, deque, bytearray, bytes)


def _percorrer(obj, caminho: str, vistos: set[int], saida: list) -> None:
    if id(obj) in vistos:
        return
    vistos.add(id(obj))
    if isinstance(obj, (dict,) + _CONTAINERS):
        saida.append((caminho, type(obj).__name__, len(obj)))
    if isinstance(obj, dict):
        for valor in obj.values():
            _percorrer(valor, caminho + "{}", vistos, saida)
    elif isinstance(obj, (list, tuple, set, frozenset, deque)):
        for item in obj:
            _percorrer(item, caminho + "[]", vistos, saida)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for campo in dataclasses.fields(obj):
            _percorrer(getattr(obj, campo.name), caminho + "." + campo.name, vistos, saida)


def _colecoes_retidas(obj) -> Counter:
    saida: list = []
    vistos: set[int] = set()
    for chave, valor in vars(obj).items():
        _percorrer(valor, chave, vistos, saida)
    return Counter(saida)


# Os hospedeiros ficam vivos ate o fim da sessao. Um `QWidget` coletado no
# meio de OUTRO teste leva junto os filhos dele — e o erro aparece na linha
# de quem estava desenhando naquele instante, apontando para o lugar errado.
_VIVOS: list = []


def _clicar(widget, ponto: QPoint, tipo=QMouseEvent.Type.MouseButtonPress) -> None:
    local = QPointF(ponto)
    evento = QMouseEvent(
        tipo,
        local,
        local,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    if tipo == QMouseEvent.Type.MouseButtonPress:
        widget.mousePressEvent(evento)
    elif tipo == QMouseEvent.Type.MouseMove:
        widget.mouseMoveEvent(evento)
    else:
        widget.mouseReleaseEvent(evento)


# =====================================================================
# 1. O estado
# =====================================================================


def test_progresso_e_busca_sao_inversos():
    for fracao in (0.0, 0.13, 0.5, 0.87, 1.0):
        estado = dataclasses.replace(_SESSAO, posicao_ns=_SESSAO.em(fracao))
        assert estado.progresso == pytest.approx(fracao, abs=1e-9)


def test_progresso_satura_em_vez_de_estourar():
    """Posição fora do intervalo acontece: o `meta.json` pode ter sido
    escrito num checkpoint anterior ao último evento. Saturar é a resposta;
    derrubar o painel de replay por causa disso seria trocar uma barra cheia
    por uma tela preta."""
    antes = dataclasses.replace(_SESSAO, posicao_ns=_SESSAO.inicio_ns - 10 * _S)
    depois = dataclasses.replace(_SESSAO, posicao_ns=_SESSAO.fim_ns + 10 * _S)
    assert antes.progresso == 0.0
    assert depois.progresso == 1.0


def test_gravacao_sem_intervalo_nao_levanta():
    """Meta antigo não tem `hora_inicio_ns`/`hora_fim_ns`. A tarja continua
    correta (a HORA do evento é o que ela mostra) e só a trilha perde a
    informação que nunca existiu."""
    degenerado = EstadoReplay(ativo=True, posicao_ns=_T0)
    assert degenerado.progresso == 0.0
    assert degenerado.em(0.7) == 0


def test_texto_da_tarja_tem_os_quatro_portadores():
    """Glifo, palavra, data do passado e velocidade. O canal teria de comer
    os quatro para o espectador confundir isto com pregão ao vivo."""
    texto = _SESSAO.texto_tarja
    assert texto.startswith(rp.GLIFO_TOCANDO)
    assert "REPLAY" in texto
    assert "06/12" in texto
    assert texto_velocidade(2.0) in texto
    assert "WDOV26" in texto


def test_pausado_muda_glifo_e_acrescenta_a_palavra():
    pausado = dataclasses.replace(_SESSAO, pausado=True)
    assert pausado.texto_tarja.startswith(rp.GLIFO_PAUSADO)
    assert "PAUSADO" in pausado.texto_tarja


def test_velocidade_e_sempre_escrita_com_virgula_e_multiplicacao():
    assert texto_velocidade(0.25) == "0,25×"
    assert texto_velocidade(1.0) == "1,0×"
    assert texto_velocidade(16.0) == "16,0×"


def test_estado_de_entrada_le_o_intervalo_do_proprio_meta():
    entrada = type(
        "EntradaFalsa",
        (),
        {
            "symbol": "WDOV26",
            "data": date(2026, 12, 6),
            "hora_inicio_ns": _T0,
            "hora_fim_ns": _T0 + 600 * _S,
        },
    )()
    estado = estado_de_entrada(entrada, velocidade=4.0)
    assert (estado.inicio_ns, estado.fim_ns) == (_T0, _T0 + 600 * _S)
    assert estado.posicao_ns == _T0 and estado.ativo and estado.velocidade == 4.0


# =====================================================================
# 2. A tarja é da JANELA
# =====================================================================


def _tarja_instalada(qapp, largura=1280, altura=720):
    janela = QWidget()
    janela.resize(largura, altura)
    tarja = TarjaReplay()
    tarja.instalar_em(janela)
    janela.show()
    tarja.definir_estado(_SESSAO)
    _VIVOS.append(janela)
    return janela, tarja


def test_tarja_cobre_a_largura_da_janela_e_fica_no_topo(qapp):
    janela, tarja = _tarja_instalada(qapp)
    assert tarja.geometry().topLeft() == QPoint(0, 0)
    assert tarja.width() == janela.width()
    assert tarja.height() == rp.ALTURA_TARJA


def test_tarja_acompanha_o_redimensionamento_da_janela(qapp):
    """Um workspace que muda de tamanho não pode deixar a tarja pela metade:
    meia tarja é a mesma coisa que meia ressalva."""
    janela, tarja = _tarja_instalada(qapp)
    janela.resize(1920, 900)
    qapp.processEvents()
    assert tarja.width() == 1920


def test_tarja_some_quando_o_replay_termina(qapp):
    janela, tarja = _tarja_instalada(qapp)
    assert tarja.isVisible()
    tarja.definir_estado(EstadoReplay(ativo=False))
    assert not tarja.isVisible()


def test_tarja_e_bloco_chapado_de_alert_com_texto_escuro(qapp):
    """A forma que atravessa o canal: área chapada e o par de maior
    contraste da tela. Texto claro sobre âmbar seria bonito e ilegível
    depois da recompressão."""
    janela, tarja = _tarja_instalada(qapp)
    tarja._quadro()
    imagem = tarja._backing.toImage()
    # Corpo da tarja, longe do texto e abaixo da faixa de 3px.
    amostra = imagem.pixel(tarja.width() - 4, rp.ALTURA_TARJA - 2)
    assert amostra & 0xFFFFFF == tokens.ALERT.rgb() & 0xFFFFFF
    # A faixa literal de §3.5, com borda contra o que estiver por baixo.
    assert imagem.pixel(4, 1) & 0xFFFFFF == tokens.BG_BASE.rgb() & 0xFFFFFF
    assert contraste(tokens.BG_BASE, tokens.ALERT) >= 4.5


def test_tarja_nao_trunca_a_ressalva_ela_encolhe(qapp):
    """Ressalva truncada é o pior modo de falha que existe: a frase que sobra
    continua parecendo completa e o leitor nunca sabe que faltou pedaço."""
    from PySide6.QtGui import QFontMetrics

    texto = _SESSAO.texto_tarja
    for largura in (1920, 1280, 900, 640, 420):
        fonte = rp._maior_que_cabe(texto, largura - 2 * rp.MARGEM)
        cabe = QFontMetrics(fonte).horizontalAdvance(texto) <= largura - 2 * rp.MARGEM
        assert cabe or fonte.pixelSize() == rp.PISO_FONTE
    # Na largura de uma estação de trabalho real, a tarja lê no corpo cheio.
    assert rp._maior_que_cabe(texto, 1280).pixelSize() >= 12


def test_tarja_nao_depende_da_paleta_direcional(qapp):
    """`--alert` é SEGUNDO canal (estado do sistema), não eixo direcional.
    Por isso a tarja é idêntica no modo sem cor — e tem de ser: um operador
    com deuteranopia não pode ser o único a não saber que está em replay."""
    janela, tarja = _tarja_instalada(qapp)
    assert "paleta" not in vars(tarja)


# =====================================================================
# 3. O transporte — geometria compartilhada por desenho, clique e teste
# =====================================================================


@pytest.fixture()
def controles(qapp):
    widget = ControlesReplay()
    widget.resize(720, widget.altura_natural())
    widget.show()
    widget.definir_estado(_SESSAO)
    _VIVOS.append(widget)
    return widget


def test_clicar_no_chip_emite_a_velocidade_daquele_chip(controles):
    """Prova de marco compartilhado: o acerto do clique usa `rect_chip`, que
    é a mesma função que desenha. Mover o chip move o alvo do clique."""
    recebidos: list[float] = []
    controles.velocidade_mudou.connect(recebidos.append)
    for indice, velocidade in enumerate(VELOCIDADES):
        if controles.rect_chip(indice).right() > controles.width():
            break
        _clicar(controles, controles.rect_chip(indice).center())
        assert recebidos[-1] == velocidade


def test_o_chip_da_velocidade_corrente_e_o_preenchido(controles):
    controles._quadro()
    imagem = controles._backing.toImage()
    ativo = VELOCIDADES.index(_SESSAO.velocidade)
    centro = controles.rect_chip(ativo).center()
    canto = controles.rect_chip(ativo).topLeft() + QPoint(1, 1)
    assert imagem.pixel(canto.x(), canto.y()) & 0xFFFFFF == tokens.ALERT.rgb() & 0xFFFFFF
    outro = controles.rect_chip((ativo + 1) % len(VELOCIDADES)).topLeft() + QPoint(1, 1)
    assert imagem.pixel(outro.x(), outro.y()) & 0xFFFFFF == tokens.BG_RAISED.rgb() & 0xFFFFFF
    assert centro.y() == controles.rect_chip(ativo).center().y()


def test_botao_de_pausa_alterna_e_pede_o_valor_oposto(controles):
    recebidos: list[bool] = []
    controles.pausa_alternada.connect(recebidos.append)
    _clicar(controles, controles.rect_pausa().center())
    assert recebidos == [True]
    controles.definir_estado(dataclasses.replace(_SESSAO, pausado=True))
    _clicar(controles, controles.rect_pausa().center())
    assert recebidos == [True, False]


def test_trilha_converte_posicao_em_fracao_e_de_volta(controles):
    for fracao in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = controles.x_do_progresso(fracao)
        assert controles.fracao_em(x) == pytest.approx(fracao, abs=0.01)
    trilha = controles.rect_trilha()
    assert controles.fracao_em(trilha.left() - 500) == 0.0
    assert controles.fracao_em(trilha.right() + 500) == 1.0


def test_arrastar_para_voltar_emite_enquanto_o_dedo_anda(controles):
    """Voltar num replay é busca EXPLORATÓRIA. Soltar para descobrir que
    passou do ponto transforma uma leitura em tentativa e erro."""
    recebidos: list[int] = []
    controles.buscou.connect(recebidos.append)
    trilha = controles.rect_trilha()
    _clicar(controles, QPoint(controles.x_do_progresso(0.8), trilha.center().y()))
    for fracao in (0.6, 0.4, 0.2):
        _clicar(
            controles,
            QPoint(controles.x_do_progresso(fracao), trilha.center().y()),
            QMouseEvent.Type.MouseMove,
        )
    assert len(recebidos) == 4
    assert recebidos == sorted(recebidos, reverse=True)
    # Tolerancia de UM PIXEL de trilha, e nao um numero redondo: a busca
    # nasce de uma coordenada inteira, entao a precisao possivel e
    # exatamente `duracao / largura da trilha`. Pedir mais que isso seria
    # afirmar uma precisao que a geometria nao tem.
    um_pixel_ns = _SESSAO.duracao_ns / controles.rect_trilha().width()
    assert recebidos[-1] == pytest.approx(_SESSAO.em(0.2), abs=um_pixel_ns + 1)


def test_mover_sem_ter_pressionado_nao_busca(controles):
    recebidos: list[int] = []
    controles.buscou.connect(recebidos.append)
    _clicar(
        controles,
        QPoint(controles.x_do_progresso(0.3), controles.rect_trilha().center().y()),
        QMouseEvent.Type.MouseMove,
    )
    assert recebidos == []


def test_a_alca_da_trilha_esta_onde_o_progresso_diz(controles):
    controles._quadro()
    imagem = controles._backing.toImage()
    trilha = controles.rect_trilha()
    corte = controles.x_do_progresso(_SESSAO.progresso)
    meio_y = trilha.center().y()
    assert imagem.pixel(corte + 1, meio_y) & 0xFFFFFF == tokens.TEXT_PRIMARY.rgb() & 0xFFFFFF
    assert imagem.pixel(trilha.left() + 2, meio_y) & 0xFFFFFF == tokens.ALERT.rgb() & 0xFFFFFF
    assert (
        imagem.pixel(trilha.right() - 2, meio_y) & 0xFFFFFF
        == tokens.BG_RAISED.rgb() & 0xFFFFFF
    )


# =====================================================================
# 4. Trabalho por quadro
# =====================================================================


def test_andar_no_tempo_nao_suja_a_linha_das_velocidades(controles):
    controles._quadro()
    controles.definir_estado(
        dataclasses.replace(_SESSAO, posicao_ns=_SESSAO.posicao_ns + 5 * _S)
    )
    assert not controles._tudo_sujo
    sujos = controles._sujos
    assert sujos
    assert all(not r.intersects(controles.rect_linha_velocidade) for r in sujos)


def test_estado_identico_nao_gera_quadro(controles):
    controles._quadro()
    controles.zerar_medicao()
    for _ in range(20):
        controles.definir_estado(_SESSAO)
        controles._quadro()
    assert controles.quadros_desenhados == 0
    assert controles.quadros_vazios == 20


# =====================================================================
# 5. Retenção
# =====================================================================


@pytest.mark.parametrize("alvo", ["tarja", "controles"])
def test_nada_cresce_com_o_tempo_de_replay(qapp, alvo):
    """Cem mil atualizações de posição — um pregão inteiro percorrido — e as
    duas peças guardam exatamente o mesmo tanto que guardavam no primeiro
    quadro. Nenhum histórico de posição, nenhuma trilha de busca."""
    if alvo == "tarja":
        _janela, widget = _tarja_instalada(qapp)
    else:
        widget = ControlesReplay()
        widget.resize(720, widget.altura_natural())
        widget.show()
        widget.definir_estado(_SESSAO)
        _VIVOS.append(widget)

    antes = _colecoes_retidas(widget)
    for k in range(100_000):
        widget.definir_estado(
            dataclasses.replace(
                _SESSAO,
                posicao_ns=_SESSAO.inicio_ns + (k % 3600) * _S,
                velocidade=VELOCIDADES[k % len(VELOCIDADES)],
                pausado=bool(k % 2),
            )
        )
    assert _colecoes_retidas(widget) == antes
