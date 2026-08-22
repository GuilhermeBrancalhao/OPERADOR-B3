"""`scripts/operar.py` — o CLI, testado como programa e não como biblioteca.

Um CLI só está pronto quando roda de ponta a ponta: parseia argumento, monta o
pipeline, imprime, encerra e devolve código de saída. Aqui `main()` é chamado
com `argv` de verdade e a saída é capturada.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import time as hora_do_dia
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_CLI = RAIZ / "scripts" / "operar.py"


def _carregar_cli():
    """Importa `scripts/operar.py` por caminho — `scripts/` não é um pacote,
    e transformá-lo em um só para o teste mudaria a forma de invocar o CLI."""
    spec = importlib.util.spec_from_file_location("operar_cli", CAMINHO_CLI)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["operar_cli"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


operar = _carregar_cli()


# ---------------------------------------------------------------------------
# Parsing e tradução para ConfigOperacao
# ---------------------------------------------------------------------------


def test_defaults_do_cli_nao_sobrescrevem_os_defaults_do_motor():
    """Sem `--dominancia-minima`, a config tem de sair IGUAL ao default do
    módulo — não uma cópia do número que envelheceria em silêncio."""
    from fluxopro.motor.sinais import ConfigMotorSinais

    args = operar.construir_parser().parse_args(["--simbolo", "WDOV26"])
    cfg = operar.config_de_args(args)
    assert cfg.motor == ConfigMotorSinais()


def test_flags_de_calibracao_chegam_na_config():
    args = operar.construir_parser().parse_args(
        [
            "--simbolo", "WDOV26",
            "--dominancia-minima", "0.75",
            "--janela-dominancia-s", "30",
            "--janela-micro-s", "5",
            "--magnitude-relativa-minima", "0.3",
        ]
    )
    cfg = operar.config_de_args(args)
    assert cfg.motor.dominancia_minima == 0.75
    assert cfg.motor.janela_dominancia_ns == 30_000_000_000
    assert cfg.motor.janela_micro_ns == 5_000_000_000
    assert cfg.motor.magnitude_relativa_minima == 0.3


def test_n_eventos_zero_significa_sem_limite():
    """O `SimuladorWDO` exige um `n` finito; "sem limite" no CLI vira um
    número grande que só termina por Ctrl+C ou `--duracao`."""
    args = operar.construir_parser().parse_args([])
    cfg = operar.config_de_args(args)
    assert cfg.simulador.n_eventos == operar._N_EVENTOS_SEM_LIMITE


def test_estagios_podem_ser_desligados_pela_linha_de_comando():
    args = operar.construir_parser().parse_args(["--sem-microestrutura", "--sem-motor"])
    cfg = operar.config_de_args(args)
    assert cfg.ligar_microestrutura is False
    assert cfg.ligar_motor is False
    assert cfg.ligar_analytics is True


@pytest.mark.parametrize(
    "texto, esperado",
    [("09:00", hora_do_dia(9, 0)), ("10:30:15", hora_do_dia(10, 30, 15))],
)
def test_hora_aceita_os_dois_formatos(texto, esperado):
    assert operar._hora(texto) == esperado


def test_hora_invalida_e_recusada():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        operar._hora("nove horas")


def test_opcoes_de_replay_chegam_TODAS_da_linha_de_comando():
    """Cada campo de `OpcoesReplay` vem de uma flag distinta, e um repasse
    trocado (ou trocado por um literal) some com a opção em silêncio — o
    recorte pedido vira o dia inteiro, ou a verificação de integridade sai do
    ar sem ninguém pedir. Os valores abaixo são todos diferentes entre si de
    propósito: qualquer permutação quebra pelo menos uma asserção.
    """
    from datetime import date

    args = operar.construir_parser().parse_args(
        [
            "--arquivo", "dados",
            "--arquivo-deltas", "deltas.csv",
            "--data", "2026-08-20",
            "--de", "09:15",
            "--ate", "10:45",
            "--velocidade", "7",
        ]
    )
    op = operar.opcoes_replay_de_args(args)
    assert op.caminho == Path("dados")
    assert op.caminho_deltas == Path("deltas.csv")
    assert op.data == date(2026, 8, 20)
    assert op.de == hora_do_dia(9, 15)
    assert op.ate == hora_do_dia(10, 45)
    assert op.velocidade == 7.0


def test_verificacao_de_integridade_e_ligada_por_padrao_e_so_o_usuario_desliga():
    """A verificação de hash é a única defesa contra gravação corrompida
    (`criticas/nucleo_r4.md` Y07 a desligava em silêncio e a suíte ficava
    verde). As duas direções: sem a flag ela está LIGADA; com a flag, e só
    com ela, desligada."""
    padrao = operar.opcoes_replay_de_args(
        operar.construir_parser().parse_args(["--arquivo", "dados"])
    )
    assert padrao.verificar_hash is True

    pedido = operar.opcoes_replay_de_args(
        operar.construir_parser().parse_args(
            ["--arquivo", "dados", "--sem-verificar-hash"]
        )
    )
    assert pedido.verificar_hash is False


def test_velocidade_aceita_max_e_numero_e_recusa_o_resto():
    import argparse

    assert operar._velocidade("max") == "max"
    assert operar._velocidade("10") == 10.0
    with pytest.raises(argparse.ArgumentTypeError):
        operar._velocidade("0")
    with pytest.raises(argparse.ArgumentTypeError):
        operar._velocidade("-1")


# ---------------------------------------------------------------------------
# Execução de verdade
# ---------------------------------------------------------------------------


def test_rodar_com_simulador_imprime_resumo_e_sai_zero(capsys):
    codigo = operar.main(
        [
            "--fonte", "simulador",
            "--simbolo", "WDOV26",
            "--seed", "42",
            "--n-eventos", "1500",
            "--status-a-cada", "0",
        ]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "FLUXO PRO" in saida
    assert "RESUMO DA SESSAO" in saida
    assert "eventos processados : 3000" in saida
    assert "SINAL" in saida
    assert "DETECCAO" in saida
    assert "ordens (MBP->MBO)" in saida
    # observado x inferido visivel na saida do programa, nao so na API
    assert "[OBS]" in saida
    assert "[INF" in saida


def _saida_deterministica(texto: str) -> list[str]:
    """Descarta as linhas que dependem do relógio de PAREDE.

    Só duas linhas do resumo variam entre execuções idênticas: a que mostra o
    tempo de parede/vazão e a de log. Recortá-las é honesto — o que se está
    afirmando é que a MESMA SEED produz o mesmo conteúdo de mercado, não que o
    computador leva sempre o mesmo tempo. O que sobra inclui todos os SINAL,
    todos os DETECCAO e todos os contadores.
    """
    return [
        linha
        for linha in texto.splitlines()
        if "ev/s" not in linha and "parede" not in linha
    ]


def test_a_saida_do_cli_e_deterministica_para_a_mesma_seed(capsys):
    argv = ["--seed", "7", "--n-eventos", "800", "--status-a-cada", "0", "--simbolo", "WDOV26"]
    operar.main(argv)
    primeira = _saida_deterministica(capsys.readouterr().out)
    operar.main(argv)
    segunda = _saida_deterministica(capsys.readouterr().out)
    assert primeira == segunda
    assert any("DETECCAO" in linha for linha in primeira)
    assert any("SINAL" in linha for linha in primeira)


def test_seed_diferente_muda_a_saida_do_cli(capsys):
    """CONTROLE: sem isto, o teste acima passaria com saída constante vazia."""
    base = ["--n-eventos", "800", "--status-a-cada", "0", "--simbolo", "WDOV26"]
    operar.main(base + ["--seed", "7"])
    a = _saida_deterministica(capsys.readouterr().out)
    operar.main(base + ["--seed", "8"])
    b = _saida_deterministica(capsys.readouterr().out)
    assert a != b


def test_gravar_liga_o_gravador_no_mesmo_pipeline(tmp_path: Path, capsys):
    """`--gravar` no MESMO barramento: o que foi analisado e o que foi
    gravado são, por construção, o mesmo conjunto de eventos."""
    saida = tmp_path / "gravacao"
    codigo = operar.main(
        [
            "--simbolo", "WDOV26",
            "--seed", "3",
            "--n-eventos", "400",
            "--status-a-cada", "0",
            "--gravar", str(saida),
        ]
    )
    assert codigo == 0
    capsys.readouterr()

    from fluxopro.gravacao.catalogo import Catalogo

    catalogo = Catalogo(saida)
    entradas = catalogo.escanear()
    assert entradas
    entrada = entradas[0]
    assert entrada.symbol == "WDOV26"
    assert entrada.contagens.get("Trade") == 400
    assert entrada.contagens.get("BookSnapshot") == 400
    # e a gravacao esta integra — e' ela que vira base de replay
    assert all(catalogo.verificar_integridade(entrada).values())


def test_fonte_de_replay_ausente_devolve_codigo_2(capsys):
    """Falha de fonte não é crash: é código de saída 2 e mensagem legível."""
    codigo = operar.main(["--fonte", "replay", "--simbolo", "WDOV26"])
    assert codigo == 2


def test_replay_de_csv_pelo_cli(tmp_path: Path, capsys):
    caminho = tmp_path / "trades.csv"
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id"])
        for i in range(40):
            w.writerow([i * 1_000_000_000, "WDOV26", 10_000 + (i % 3), 5, "BUY", f"t{i}"])

    codigo = operar.main(
        [
            "--fonte", "replay",
            "--arquivo", str(caminho),
            "--simbolo", "WDOV26",
            "--status-a-cada", "0",
        ]
    )
    assert codigo == 0
    assert "eventos processados : 40" in capsys.readouterr().out


def test_passada_com_zero_eventos_avisa_em_vez_de_ficar_calada(
    tmp_path: Path, caplog, capsys
):
    """`criticas/nucleo_r5.md` §B.2: o recorte `--de/--ate` é lido em UTC, e o
    exemplo publicado no cabeçalho do próprio script pedia a abertura do WDO
    em horário de Brasília — uma janela inteira antes do tape. O replay
    devolvia zero eventos "sem erro, sem aviso, sem log".

    Este teste não decide o fuso (isso é de `gravacao/catalogo.py`). Ele
    prende a outra metade: uma passada que não processou nada tem de DIZER
    isso, e dizer o suficiente para o dono desconfiar do recorte.
    """
    import logging

    caminho = tmp_path / "trades.csv"
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id"])
        # tape de OUTRO símbolo: o pipeline não conta nada para WDOV26
        for i in range(5):
            w.writerow([i * 1_000_000_000, "XXXX", 10_000, 5, "BUY", f"t{i}"])

    with caplog.at_level(logging.WARNING):
        codigo = operar.main(
            ["--fonte", "replay", "--arquivo", str(caminho),
             "--simbolo", "WDOV26", "--status-a-cada", "0"]
        )

    assert codigo == 0
    # o cenário de fato produziu uma passada vazia (senão o teste não testa nada)
    assert "eventos processados : 0" in capsys.readouterr().out

    avisos = "\n".join(r.getMessage() for r in caplog.records)
    assert "NENHUM evento" in avisos
    assert "UTC" in avisos, "o aviso nao aponta o suspeito mais provavel (o fuso)"


def test_passada_com_eventos_nao_avisa(tmp_path: Path, caplog):
    """CONTROLE: o aviso não pode virar ruído em toda execução normal."""
    import logging

    caminho = tmp_path / "trades.csv"
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id"])
        for i in range(5):
            w.writerow([i * 1_000_000_000, "WDOV26", 10_000, 5, "BUY", f"t{i}"])

    with caplog.at_level(logging.WARNING):
        codigo = operar.main(
            ["--fonte", "replay", "--arquivo", str(caminho),
             "--simbolo", "WDOV26", "--status-a-cada", "0"]
        )

    assert codigo == 0
    assert "NENHUM evento" not in "\n".join(r.getMessage() for r in caplog.records)


def test_duracao_encerra_sozinha(capsys):
    """`--duracao` tem de parar um simulador "sem limite" — é o caminho que o
    dono usa para dar uma olhada de 60s sem ficar com o terminal preso."""
    codigo = operar.main(
        ["--simbolo", "WDOV26", "--duracao", "0.4", "--status-a-cada", "0"]
    )
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "RESUMO DA SESSAO" in saida
    assert "eventos processados : 0" not in saida
