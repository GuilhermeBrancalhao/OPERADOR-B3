"""Analise consultiva ao vivo via Claude CLI.

Nenhum teste aqui chama o CLI de verdade: as partes puras (prompt, parser)
sao testadas sozinhas e o motor e exercitado com um executavel FALSO. O
teste que precisava de rede seria lento, caro e nao determinista — e o que
importa provar (nunca bloquear a UI, nunca inventar leitura, respeitar o
intervalo) nao depende do modelo do outro lado.
"""

import time

import pytest

from fluxopro.analytics import analise_claude as ac


# ============================================================ prompt (puro)
def test_prompt_carrega_as_instrucoes_de_formato():
    """As instrucoes viajam DENTRO do prompt, nunca como argumento —
    ver a docstring de `_INSTRUCOES` (o `.CMD` do Windows perde argumento
    com quebra de linha e o CLI sai com codigo 1)."""

    texto = ac.montar_prompt({"instrumento": "WDOU26"})
    assert "CENARIO:" in texto and "LEITURA:" in texto
    assert "NUNCA recomende ordem" in texto


def test_prompt_declara_campo_ausente_em_vez_de_inventar_zero():
    texto = ac.montar_prompt({"instrumento": "WDOU26"})
    assert "sem leitura" in texto
    assert "0,00" not in texto


def test_prompt_leva_os_numeros_da_tela():
    texto = ac.montar_prompt({"instrumento": "WDOU26", "dominancia": "VENDA",
                              "placar": "31% compra / 69% venda"})
    assert "VENDA" in texto and "31% compra / 69% venda" in texto


# ============================================================ parser (puro)
_RESPOSTA_OK = """CENARIO: BAIXA
TITULO: Fluxo vendedor domina
LEITURA: A dominancia aponta venda. O Renko perde forca.
ATENCAO: Sem zona confirmada para arbitrar."""


def test_parser_le_os_quatro_campos():
    a = ac.parsear_resposta(_RESPOSTA_OK)
    assert a is not None
    assert a.cenario == "BAIXA"
    assert a.titulo == "Fluxo vendedor domina"
    assert a.leitura.startswith("A dominancia")
    assert a.atencao.startswith("Sem zona")


def test_parser_tolera_markdown_e_acento_no_rotulo():
    a = ac.parsear_resposta("**CENÁRIO:** ALTA\n- TITULO: teste\nLEITURA: uma frase.")
    assert a is not None and a.cenario == "ALTA" and a.titulo == "teste"


def test_parser_sem_leitura_devolve_none():
    """Analise pela metade nao vai para a tela."""

    assert ac.parsear_resposta("CENARIO: ALTA\nTITULO: so isso") is None
    assert ac.parsear_resposta("") is None
    assert ac.parsear_resposta("conversa fiada sem formato") is None


def test_parser_normaliza_cenario_desconhecido():
    a = ac.parsear_resposta("CENARIO: TALVEZ\nLEITURA: x.")
    assert a is not None and a.cenario == "INDEFINIDO"


# ============================================================ motor
def _cli_falso(tmp_path, saida: str, codigo: int = 0, demora: float = 0.0):
    """Script Python usado como executavel — nunca o `claude` real."""

    script = tmp_path / "cli_falso.py"
    script.write_text(
        "import sys, time\n"
        f"time.sleep({demora})\n"
        "sys.stdin.read()\n"
        f"sys.stdout.write({saida!r})\n"
        f"sys.exit({codigo})\n",
        encoding="utf-8",
    )
    return script


class _MotorScript(ac.MotorAnaliseClaude):
    """Roda o script falso com o proprio interpretador do teste."""

    def __init__(self, script, **kw):
        super().__init__(executavel="python", **kw)
        self._script = script

    def _rodar(self, prompt):
        import subprocess
        self._cli_args = [self._cli, str(self._script)]
        original = self._cli
        try:
            # reaproveita a logica da base trocando so o alvo do subprocess
            resultado = subprocess.run(
                self._cli_args, input=prompt, capture_output=True, text=True,
                timeout=self._timeout_s, encoding="utf-8", errors="replace",
            )
            analise = ac.parsear_resposta(resultado.stdout) if resultado.returncode == 0 else None
            motivo = None if analise else f"cli saiu {resultado.returncode}"
        except Exception as erro:  # noqa: BLE001
            analise, motivo = None, str(erro)
        finally:
            self._cli = original
        with self._lock:
            self._em_voo = False
            if analise is not None:
                self._analise, self._estado, self._motivo = analise, ac.EstadoAnalise.PRONTA, None
            else:
                self._estado, self._motivo = ac.EstadoAnalise.ERRO, motivo


def _esperar(motor, limite_s=20.0):
    fim = time.time() + limite_s
    while time.time() < fim:
        estado, _, _ = motor.ultima()
        if estado in (ac.EstadoAnalise.PRONTA, ac.EstadoAnalise.ERRO):
            return estado
        time.sleep(0.05)
    return None


def test_motor_publica_analise_e_nunca_bloqueia(tmp_path):
    """`solicitar` volta na hora: a chamada real mede 14-30 s e a UI
    redesenha a 60 fps."""

    motor = _MotorScript(_cli_falso(tmp_path, _RESPOSTA_OK, demora=0.4))
    inicio = time.monotonic()
    assert motor.solicitar({"instrumento": "WDO"}) is True
    assert time.monotonic() - inicio < 0.2, "solicitar bloqueou a thread chamadora"
    assert _esperar(motor) is ac.EstadoAnalise.PRONTA
    _, analise, _ = motor.ultima()
    assert analise.cenario == "BAIXA"


def test_motor_nao_dispara_duas_vezes_em_voo(tmp_path):
    motor = _MotorScript(_cli_falso(tmp_path, _RESPOSTA_OK, demora=0.6))
    assert motor.solicitar({}) is True
    assert motor.solicitar({}) is False
    _esperar(motor)


def test_motor_respeita_o_intervalo_minimo(tmp_path):
    motor = _MotorScript(_cli_falso(tmp_path, _RESPOSTA_OK), intervalo_s=60.0)
    assert motor.solicitar({}) is True
    _esperar(motor)
    assert motor.solicitar({}) is False, "estourou o piso de intervalo entre chamadas"


def test_motor_marca_erro_mas_preserva_a_analise_anterior(tmp_path):
    """Melhor uma leitura velha COM idade impressa do que tela vazia — mas
    o estado tem de dizer que a ultima tentativa falhou."""

    motor = _MotorScript(_cli_falso(tmp_path, _RESPOSTA_OK), intervalo_s=0.0)
    assert motor.solicitar({}) is True
    assert _esperar(motor) is ac.EstadoAnalise.PRONTA

    motor._script = _cli_falso(tmp_path, "", codigo=1)
    assert motor.solicitar({}) is True
    assert _esperar(motor) is ac.EstadoAnalise.ERRO
    estado, analise, motivo = motor.ultima()
    assert analise is not None, "a analise anterior nao pode sumir da tela"
    assert motivo


def test_motor_sem_cli_nunca_dispara():
    motor = ac.MotorAnaliseClaude(executavel=None)
    motor._cli = None
    assert motor.disponivel() is False
    assert motor.solicitar({}) is False
    estado, analise, _ = motor.ultima()
    assert estado is ac.EstadoAnalise.AUSENTE and analise is None


def test_idade_sem_analise_e_none():
    motor = ac.MotorAnaliseClaude(executavel="python")
    assert motor.idade_s() is None


# ============================================================ mapeamento
def test_dados_do_estado_nao_estoura_com_estado_vazio():
    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")
    from fluxopro.ui.paineis.nexo import EstadoNexo, analise as mapa

    estado = EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                        leituras=(), largura=1920, altura=1055)
    dados = mapa.dados_do_estado(estado)
    assert isinstance(dados, dict)
    # tudo ausente, nada inventado
    assert dados["dominancia"] is None
    assert ac.montar_prompt(dados)


def test_desenhar_analise_sem_pacote_nao_estoura(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage, QPainter

    from fluxopro.ui.paineis.nexo import analise as mapa

    imagem = QImage(400, 120, QImage.Format.Format_ARGB32)
    painter = QPainter(imagem)
    try:
        mapa.desenhar_analise(painter, QRect(0, 0, 400, 120), None)
        mapa.desenhar_analise(painter, QRect(0, 0, 400, 120),
                              (ac.EstadoAnalise.PRONTA, ac.parsear_resposta(_RESPOSTA_OK),
                               None, 12.0))
        mapa.desenhar_analise(painter, QRect(0, 0, 20, 8), None)  # regiao minuscula
    finally:
        painter.end()


def test_gate_recusa_quadro_sem_mercado():
    """A analise nao pode disparar no quadro zero: sem preco e sem
    dominancia o modelo so pode responder "nao ha dados", e essa leitura
    vazia ficaria 90 s na tela ocupando uma chamada paga."""

    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")
    from fluxopro.ui.paineis.nexo import analise as mapa

    assert mapa.dados_suficientes({}) is False
    assert mapa.dados_suficientes({"preco": "5.219,0"}) is False
    assert mapa.dados_suficientes({"preco": "5.219,0", "dominancia": None}) is False
    assert mapa.dados_suficientes({"preco": "5.219,0", "dominancia": "VENDA"}) is True


def test_gate_recusa_estado_nexo_vazio():
    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")
    from fluxopro.ui.paineis.nexo import EstadoNexo, analise as mapa

    vazio = EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                       leituras=(), largura=1920, altura=1055)
    assert mapa.dados_suficientes(mapa.dados_do_estado(vazio)) is False
