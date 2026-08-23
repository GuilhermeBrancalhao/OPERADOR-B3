import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Qt sem tela. Definido ANTES de qualquer import de PySide6 (o plugin de
# plataforma e escolhido na criacao do QGuiApplication e nao muda depois),
# e com `setdefault` para nao atropelar quem estiver rodando de proposito
# numa tela de verdade.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """`QApplication` unica da sessao de testes.

    Uma so porque o Qt nao suporta duas no mesmo processo, e de escopo de
    sessao porque destruir e recriar a aplicacao entre testes deixa widgets
    orfaos apontando para uma aplicacao morta — que no Qt e falha de
    segmentacao, nao excecao coletavel.

    Pula a suite inteira de UI se PySide6 nao estiver instalado: o nucleo do
    FluxoPro nao depende de Qt, e quebrar 657 testes de dominio porque falta
    uma dependencia de interface seria o teste mentindo sobre o que quebrou.
    """
    pyside = pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")
    aplicacao = pyside.QApplication.instance() or pyside.QApplication([])
    return aplicacao


@pytest.fixture(autouse=True)
def _drenar_qt(request):
    """Depois de cada teste de UI, esvazia a fila do Qt.

    ## O que isto conserta

    `python -m pytest tests/test_ui_*.py` com quatro processos queimando CPU ao
    lado derrubava o processo com `Windows fatal exception: access violation`.
    O teste que caía era sempre o mesmo — `test_a_interface_desenha_sob_carga`
    — e ele passa **6 de 6 vezes quando roda sozinho sob a mesma carga**. Não é
    ele: é o que sobrou dos ~560 testes que rodaram antes.

    ## Por que só aquele teste cai

    Ele é o único da suíte que roda o laço de eventos (`qapp.processEvents()`
    num laço de 2 s). Todos os outros desenham chamando `_quadro()` direto, sem
    nunca despachar evento nenhum. Então a fila do Qt acumula a suíte inteira —
    `DeferredDelete`, eventos de geometria, repinturas de widget que o Python
    já coletou — e o primeiro `processEvents()` que aparecer despacha tudo de
    uma vez, alguns para objetos C++ que não existem mais.

    A contenção não causa o defeito; ela alarga a janela em que ele acontece.
    Um vermelho que só aparece com a máquina ocupada não é "instável": é um
    defeito real com um gatilho raro, e este projeto já pagou caro por tratar
    as duas coisas como a mesma.

    ## Por que aqui e não em cada teste

    `autouse` porque a alternativa é lembrar em cada um dos 560. Só faz
    trabalho se o teste realmente usou Qt (`qapp` na lista de fixtures), então
    os 750 testes de domínio não pagam nada.
    """
    yield
    if "qapp" not in request.fixturenames:
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    app = QCoreApplication.instance()
    if app is None:
        return
    # `DeferredDelete` primeiro: e a fila que segura os widgets mortos. Depois
    # o resto, para que nenhum evento fique apontando para o que acabou de ser
    # destruido.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.sendPostedEvents(None, 0)
    app.processEvents()
