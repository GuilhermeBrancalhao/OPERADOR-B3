"""Saída em texto: a evidência tem de aparecer, e inferido tem de se ver.

Estes testes são sobre a PROMESSA do produto, não sobre estética: o projeto
inteiro se apoia em "o usuário pode auditar por que algo foi sinalizado", e
uma saída que engolisse a evidência ou que igualasse hipótese a fato tornaria
essa promessa vazia sem quebrar nenhum outro teste.
"""

from __future__ import annotations

import io

from fluxopro.app.config import ConfigOperacao, ConfigSimulador
from fluxopro.app.montagem import montar
from fluxopro.app.saida import (
    ConsoleFluxo,
    formatar_evidencia,
    formatar_hora,
    marca_confianca,
)
from fluxopro.app.sessao_fluxo import DeteccaoAnotada
from fluxopro.core.eventos import WDO_GRID, WIN_GRID, Side
from fluxopro.microestrutura.detectores import Deteccao, TipoDeteccao
from fluxopro.microestrutura.eventos_mbo import FonteMicro
from fluxopro.motor.sinais import EstagioSinal, Sinal

SYMBOL = "WDOV26"


def console(grid=WDO_GRID, **kwargs) -> ConsoleFluxo:
    return ConsoleFluxo(grid, stream=io.StringIO(), **kwargs)


def sinal_confirmado() -> Sinal:
    return Sinal(
        timestamp_ns=12 * 3_600_000_000_000 + 34 * 60_000_000_000 + 56_789_000_000,
        symbol=SYMBOL,
        estagio=EstagioSinal.CONFIRMADO,
        direcao=Side.BUY,
        evidencia={
            "dominancia": 0.8342,
            "faixa": "MAXIMA_CONVICCAO",
            "magnitude": 1240,
            "magnitude_referencia": 1215.0,
            "magnitude_relativa": 1.0205,
            "volume_nao_atribuido": 17,
            "direcao_dominante": "BUY",
            "na_regiao": True,
            "micro_virou": True,
            "pre_sinal": False,
            "delta_micro_primeira_metade": -100,
            "delta_micro_segunda_metade": 40,
            "estagio_bruto": "CONFIRMADO",
            "persistencia_trades": 7,
        },
    )


def deteccao_absorcao(confianca: float = 1.0) -> Deteccao:
    return Deteccao(
        timestamp_ns=9 * 3_600_000_000_000,
        symbol=SYMBOL,
        tipo=TipoDeteccao.ABSORCAO,
        side=Side.BUY,
        price=10_001,
        confianca=confianca,
        evidencia={
            "volume_agressao_dominante": 420,
            "volume_lado_oposto": 180,
            "deslocamento_ticks": 1,
            "n_trades_janela": 97,
        },
    )


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------


def test_formatar_hora_le_como_hora_de_pregao():
    ns = 9 * 3_600_000_000_000 + 5 * 60_000_000_000 + 3_250_000_000
    assert formatar_hora(ns) == "09:05:03.250"


def test_formatar_hora_de_tape_que_comeca_no_zero():
    """O simulador começa em 0 ns; a linha tem de virar tempo decorrido
    legível, e não `1970-01-01`."""
    assert formatar_hora(0) == "00:00:00.000"
    assert formatar_hora(2_466_000_000) == "00:00:02.466"


def test_formatar_evidencia_pula_o_que_nao_existe():
    """Nem todo estágio produz toda evidência — um `NENHUM` bloqueado por
    magnitude nunca avalia região nem micro. Campo ausente é pulado, não
    impresso como vazio."""
    texto = formatar_evidencia(
        {"dominancia": 0.9, "bloqueio": "magnitude_relativa"},
        ("dominancia", "na_regiao", "bloqueio"),
    )
    assert texto == "dom=0.900 bloqueio=magnitude_relativa"


def test_formatar_evidencia_traduz_booleano_para_palavra():
    assert formatar_evidencia({"na_regiao": True}) == "regiao=sim"
    assert formatar_evidencia({"na_regiao": False}) == "regiao=nao"


def test_marca_de_confianca_separa_fato_de_hipotese():
    assert marca_confianca(1.0) == "[OBS]"
    assert marca_confianca(0.85) == "[INF 0.85]"
    # 0.999 arredonda para 1.00 na exibicao, mas NAO pode virar [OBS]: a marca
    # sai do valor, nunca do texto arredondado.
    assert marca_confianca(0.999) == "[INF 1.00]"


# ---------------------------------------------------------------------------
# A linha de sinal
# ---------------------------------------------------------------------------


def test_a_linha_do_sinal_carrega_a_evidencia_das_tres_condicoes():
    """O que o operador precisa para auditar a decisão, na mesma linha:
    dominância (condição 1), magnitude relativa (o gate do caso WINFUT),
    região (condição 2) e as duas metades da micro (condição 3)."""
    c = console()
    c.ao_sinal(sinal_confirmado())
    linha = c.linhas[-1]

    assert "12:34:56.789" in linha
    assert "SINAL" in linha
    assert "CONFIRMADO" in linha
    assert "COMPRA" in linha
    assert "MAXIMA_CONVICCAO" in linha
    assert "dom=0.834" in linha
    assert "mag=1240" in linha
    assert "mag_rel=1.020" in linha  # 1.0205 arredonda para par, como o Python faz
    assert "regiao=sim" in linha
    assert "micro=sim" in linha
    assert "micro_1a=-100" in linha
    assert "micro_2a=40" in linha
    assert "bruto=CONFIRMADO" in linha
    assert "persist=7" in linha
    assert "vol_nao_atrib=17" in linha


def test_a_linha_do_sinal_mostra_o_bloqueio_quando_ha_um():
    """Um `NENHUM` por magnitude relativa não é o mesmo que um `NENHUM` por
    falta de dominância — a linha tem de dizer qual dos dois foi."""
    c = console(mostrar_estagio_nenhum=True)
    c.ao_sinal(
        Sinal(
            timestamp_ns=0,
            symbol=SYMBOL,
            estagio=EstagioSinal.NENHUM,
            direcao=None,
            evidencia={
                "dominancia": 0.91,
                "faixa": "MAXIMA_CONVICCAO",
                "magnitude": 30,
                "magnitude_relativa": 0.12,
                "bloqueio": "magnitude_relativa",
                "estagio_bruto": "NENHUM",
            },
        )
    )
    linha = c.linhas[-1]
    assert "bloqueio=magnitude_relativa" in linha
    assert "dom=0.910" in linha


def test_estagio_nenhum_e_omitido_por_padrao():
    c = console()
    c.ao_sinal(Sinal(0, SYMBOL, EstagioSinal.NENHUM, None, {"faixa": "LATERAL"}))
    assert c.linhas == []


# ---------------------------------------------------------------------------
# A linha de detecção
# ---------------------------------------------------------------------------


def test_a_linha_da_deteccao_observada_traz_evidencia_e_marca_obs():
    c = console()
    c.ao_deteccao(DeteccaoAnotada(deteccao_absorcao(), FonteMicro.MBO, 1.0))
    linha = c.linhas[-1]
    assert "ABSORCAO" in linha
    assert "[OBS]" in linha
    assert "vol_dom=420" in linha
    assert "vol_oposto=180" in linha
    assert "desloc_t=1" in linha
    assert "n_janela=97" in linha


def test_a_linha_da_deteccao_inferida_e_visivelmente_diferente():
    c = console()
    c.ao_deteccao(
        DeteccaoAnotada(deteccao_absorcao(), FonteMicro.MBP_INFERIDO, 0.85)
    )
    assert "[INF 0.85]" in c.linhas[-1]
    assert "[OBS]" not in c.linhas[-1]


def test_o_preco_sai_na_grade_do_instrumento_e_nao_em_ticks():
    """10.001 ticks de WDO são 5000,5 — imprimir o inteiro seria ilegível
    para quem opera, e enganoso para quem compara com a tela da corretora."""
    c = console(WDO_GRID)
    c.ao_deteccao(DeteccaoAnotada(deteccao_absorcao(), FonteMicro.MBO, 1.0))
    assert "@5000.5" in c.linhas[-1]

    c_win = console(WIN_GRID)
    c_win.ao_deteccao(DeteccaoAnotada(deteccao_absorcao(), FonteMicro.MBO, 1.0))
    assert "@50005" in c_win.linhas[-1]


def test_deteccao_sem_preco_nao_quebra_a_linha():
    c = console()
    det = Deteccao(0, SYMBOL, TipoDeteccao.EXAUSTAO, Side.SELL, None, 1.0, {"x": 1})
    c.ao_deteccao(DeteccaoAnotada(det, FonteMicro.MBO, 1.0))
    assert "@-" in c.linhas[-1]


# ---------------------------------------------------------------------------
# Contadores e resumo
# ---------------------------------------------------------------------------


def _sessao_rodada():
    cfg = ConfigOperacao(
        symbol=SYMBOL, simulador=ConfigSimulador(seed=42, n_eventos=800)
    )
    c = ConsoleFluxo(cfg.price_grid(), stream=io.StringIO())
    montagem = montar(cfg, ao_sinal=c.ao_sinal, ao_deteccao=c.ao_deteccao)
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    return montagem.sessao, c


def test_linha_de_status_traz_os_contadores_ao_vivo():
    sessao, c = _sessao_rodada()
    linha = c.linha_status(sessao)
    assert "eventos=1600" in linha
    assert "ev/s" in linha
    assert "ordens_inferidas=" in linha
    assert "sinais=" in linha
    assert "deteccoes=" in linha


def test_resumo_quebra_sinais_por_estagio_e_deteccoes_por_tipo():
    sessao, c = _sessao_rodada()
    c.resumo(sessao)
    texto = "\n".join(c.linhas)
    assert "RESUMO DA SESSAO" in texto
    assert "eventos processados : 1600" in texto
    for estagio, n in sessao.contadores.sinais_por_estagio.items():
        assert f"{estagio.value:<22} {n}" in texto
    for tipo, n in sessao.contadores.deteccoes_por_tipo.items():
        assert f"{tipo.value:<22} {n}" in texto
    assert "ordens (MBP->MBO)" in texto
    assert "mercado" in texto
    assert "perfil de sessao" in texto
    assert "motor (final)" in texto


def test_cabecalho_declara_os_estagios_ligados():
    cfg = ConfigOperacao(
        symbol=SYMBOL,
        simulador=ConfigSimulador(n_eventos=10),
        ligar_microestrutura=False,
    )
    c = ConsoleFluxo(cfg.price_grid(), stream=io.StringIO())
    c.cabecalho(montar(cfg).sessao)
    cabecalho = c.linhas[0]
    assert "simbolo=WDOV26" in cabecalho
    assert "fonte=simulador" in cabecalho
    assert "analytics" in cabecalho
    assert "microestrutura" not in cabecalho


def test_resumo_de_sessao_vazia_nao_quebra():
    cfg = ConfigOperacao(symbol=SYMBOL, simulador=ConfigSimulador(n_eventos=0))
    c = ConsoleFluxo(cfg.price_grid(), stream=io.StringIO())
    sessao = montar(cfg).sessao
    c.resumo(sessao)
    assert "eventos processados : 0" in "\n".join(c.linhas)
