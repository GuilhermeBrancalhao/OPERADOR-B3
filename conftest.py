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
