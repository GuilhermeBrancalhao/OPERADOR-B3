"""Console OPERADOR IA (fluxopro/ui/paineis/nexo/vies.py).

Quatro coisas sao afirmadas aqui, e cada uma existe porque ha um jeito
conhecido de errar:

1. **A regiao le o Sinal Ultra.** O defeito relatado pelo operador era
   "nunca apareceu nada": o bloco desenhava o mesmo disco com o Ultra armado
   ou nao, porque nao tocava em `estado.sinal_ultra`. Os testes fixam que os
   estados possiveis produzem leituras DIFERENTES, e que "motor ausente"
   nunca e confundido com "sem sinal" — sao coisas distintas e dizer uma
   pela outra e mentir sobre o estado.
2. **A regiao nao reimprime o mecanismo.** Por decisao de coordenacao de
   28/08/2026 as condicoes do filtro sao do visor central; uma versao
   intermediaria desta regiao desenhou um placar proprio e as duas passaram
   a dizer a mesma coisa no mesmo quadro. O teste reprova o retorno do
   placar e qualquer valor medido copiado pra ca.
3. **Tela e audio saem da MESMA funcao.** Se a faixa de narracao redigir
   frase propria, o operador ouve uma coisa e le outra, e nada acusa.
4. **A leitura nunca vira conselho de execucao.** O produto e consultivo e
   nao envia ordem; o teste varre o vocabulario de execucao em TODOS os
   estados possiveis — incluindo a frase narrada — e nao so no caminho
   feliz.

O smoke de desenho continua cobrindo as quatro direcoes sem tela real.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 nao instalado")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QPainter, QPixmap  # noqa: E402

from fluxopro.analytics.renko import FaseRenko  # noqa: E402
from fluxopro.asg.sinal_ultra import DirecaoUltra, SinalUltraSnapshot  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    LinhaMatrizASG,
    MatrizASGSnapshot,
    ProcedenciaASG,
    ProcessamentoASGSnapshot,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.nexo import EstadoNexo, vies  # noqa: E402

TS = 1_000_000_000_000


class _TijoloFake:
    """So a `direcao` — e o unico campo que `vies._direcao_do_renko` le."""

    def __init__(self, direcao: int) -> None:
        self.direcao = direcao


def _snapshot(direcao, timestamp_ns=0):
    return WorkspaceASGSnapshot(
        timestamp_ns,
        DadosASGSnapshot(timestamp_ns, estado=EstadoASG.AO_VIVO),
        ProcessamentoASGSnapshot(timestamp_ns, estado=EstadoASG.AO_VIVO),
        MatrizASGSnapshot(timestamp_ns, estado=EstadoASG.AO_VIVO),
        DecisaoASGSnapshot(timestamp_ns, estado=EstadoASG.AO_VIVO, direcao=direcao),
        TrilhaEvidenciasASGSnapshot(timestamp_ns, estado=EstadoASG.AO_VIVO),
        contexto_bruto=None,
    )


def _maker(forca, confianca=ConfiancaASG.ALTA):
    return LinhaMatrizASG(
        "MAKERPROXY",
        DirecaoASG.COMPRA if forca >= 0 else DirecaoASG.VENDA,
        f"{forca:+.0%}",
        forca,
        confianca,
        list(ProcedenciaASG)[0],
    )


def _estado(direcao=DirecaoASG.AGUARDAR, **campos):
    padrao = dict(
        snapshot=_snapshot(direcao, campos.pop("timestamp_ns", 0)),
        serie=(),
        grid=None,
        paleta=tokens.PALETA_COR,
        maker=None,
        leituras=(),
        largura=384,
        altura=410,
    )
    padrao.update(campos)
    return EstadoNexo(**padrao)


def _estado_armado(direcao_ultra=DirecaoUltra.COMPRA):
    compra = direcao_ultra is DirecaoUltra.COMPRA
    return _estado(
        direcao=DirecaoASG.COMPRA if compra else DirecaoASG.VENDA,
        timestamp_ns=TS,
        maker=_maker(0.72 if compra else -0.72),
        tijolos_renko=(_TijoloFake(1 if compra else -1),),
        fase_renko=FaseRenko.TENDENCIA,
        sinal_ultra=SinalUltraSnapshot(
            TS, direcao_ultra, direcao_ultra, TS - 42_000_000_000
        ),
    )


def _estado_segurando(direcao_ultra=DirecaoUltra.COMPRA):
    """Selo aceso, confluencia crua JA quebrada — o filtro se sustenta so
    pela histerese."""

    compra = direcao_ultra is DirecaoUltra.COMPRA
    return _estado(
        direcao=DirecaoASG.COMPRA if compra else DirecaoASG.VENDA,
        timestamp_ns=TS,
        tijolos_renko=(_TijoloFake(1 if compra else -1),),
        fase_renko=FaseRenko.INDEFINIDA,
        sinal_ultra=SinalUltraSnapshot(
            TS, direcao_ultra, DirecaoUltra.NENHUMA, TS - 42_000_000_000
        ),
    )


def _todos_os_estados():
    return (
        _estado(),
        _estado(sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                               DirecaoUltra.NENHUMA, None)),
        _estado(direcao=DirecaoASG.COMPRA, timestamp_ns=TS,
                sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                               DirecaoUltra.COMPRA, None)),
        _estado_armado(DirecaoUltra.COMPRA),
        _estado_armado(DirecaoUltra.VENDA),
        _estado_segurando(DirecaoUltra.COMPRA),
    )


# --------------------------------------------------------------------------
# 1. A regiao le o Sinal Ultra
# --------------------------------------------------------------------------


def test_selo_armado_mostra_direcao_e_tempo_decorrido():
    titulo, sub, _ = vies._texto_selo(_estado_armado(DirecaoUltra.VENDA))
    assert "ULTRA VENDA ARMADO" in titulo
    # 42s entre `ligado_desde_ns` e o timestamp do quadro.
    assert "42S" in sub


def test_selo_distingue_confirmando_de_armado():
    """Confluencia crua presente mas ainda no debounce nao pode aparecer
    como armada — sao estados diferentes do motor."""

    estado = _estado(
        direcao=DirecaoASG.COMPRA,
        timestamp_ns=TS,
        sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                       DirecaoUltra.COMPRA, None),
    )
    titulo, _, _ = vies._texto_selo(estado)
    assert titulo == "CONFIRMANDO COMPRA"


def test_motor_ausente_nao_e_o_mesmo_que_sem_sinal():
    ausente, _, _ = vies._texto_selo(_estado())
    sem_sinal, _, _ = vies._texto_selo(
        _estado(sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                               DirecaoUltra.NENHUMA, None))
    )
    assert ausente == "MOTOR AUSENTE"
    assert sem_sinal == "SEM SINAL ULTRA"
    assert ausente != sem_sinal


def test_os_tres_estados_produzem_leituras_diferentes():
    """O defeito relatado era a regiao mostrar a mesma coisa sempre."""

    textos = {
        " ".join(vies.leitura_do_sinal(estado)) for estado in _todos_os_estados()
    }
    assert len(textos) == len(_todos_os_estados())


# --------------------------------------------------------------------------
# 2. A regiao nao reimprime o mecanismo — isso e do visor central
# --------------------------------------------------------------------------


def test_nao_expoe_mais_placar_de_portoes():
    """Decisao de coordenacao de 28/08/2026: as condicoes do filtro sao do
    visor central (`nexo/nucleo.py`). Duas regioes desenhando o mesmo
    diagnostico no mesmo quadro e pior que qualquer uma sozinha."""

    assert not hasattr(vies, "portoes")
    assert not hasattr(vies, "Portao")


def test_leitura_nao_reimprime_valor_medido_de_condicao():
    """Um numero medido repetido em duas regioes e uma segunda fonte que
    diverge em silencio; a frase aponta para o visor em vez de copiar."""

    for estado in _todos_os_estados():
        texto = " ".join(vies.leitura_do_sinal(estado) + vies.observar_agora(estado))
        # Nenhuma medida do MakerProxy/limiar vaza pra ca.
        assert "0.50" not in texto
        assert "0.72" not in texto
        assert "%" not in texto


def test_sem_alinhamento_aponta_para_o_visor_central():
    estado = _estado(sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                                    DirecaoUltra.NENHUMA, None))
    texto = " ".join(vies.observar_agora(estado)).lower()
    assert "visor central" in texto


def test_janela_de_confirmacao_vem_da_config_do_motor():
    """O unico numero que esta regiao exibe nao pode ser digitado."""

    from fluxopro.asg.sinal_ultra import ConfigSinalUltra

    estado = _estado(direcao=DirecaoASG.COMPRA, timestamp_ns=TS,
                     sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                                    DirecaoUltra.COMPRA, None))
    texto = " ".join(vies.leitura_do_sinal(estado))
    segundos = ConfigSinalUltra().persistencia_minima_ns / 1e9
    assert f"{segundos:.0f}s" in texto


# --------------------------------------------------------------------------
# 3. Narracao: a tela e o audio saem da MESMA funcao
# --------------------------------------------------------------------------


def test_narracao_e_identica_a_frase_do_locutor():
    """Se a tela redigir a frase por conta propria, o operador ouve uma
    coisa e le outra — e ninguem percebe."""

    from fluxopro.audio.voz import texto_para_transicao_ultra

    for direcao in (DirecaoUltra.COMPRA, DirecaoUltra.VENDA):
        estado = _estado_armado(direcao)
        assert vies.texto_narrado(estado) == texto_para_transicao_ultra(
            DirecaoUltra.NENHUMA, direcao
        )


def test_sem_filtro_armado_nao_ha_frase_narrada():
    """O locutor so fala em transicao: sem anuncio, a regiao devolve None
    em vez de inventar uma fala que nunca saiu."""

    assert vies.texto_narrado(_estado()) is None
    assert vies.texto_narrado(
        _estado(sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.NENHUMA,
                                               DirecaoUltra.NENHUMA, None))
    ) is None


def test_desenhar_narracao_nunca_sobe_thread_de_audio():
    """A regiao le o TEXTO da voz; nao pode instanciar locutor nenhum."""

    import threading

    antes = threading.active_count()
    for estado in _todos_os_estados():
        vies.texto_narrado(estado)
    assert threading.active_count() == antes


# --------------------------------------------------------------------------
# 4. LEITURA nunca vira conselho de execucao
# --------------------------------------------------------------------------

_VOCABULARIO_DE_EXECUCAO = (
    "compre", "venda agora", "entre", "entrada em", "alvo", "stop",
    "take profit", "posicao", "lote", "contrato", "ordem de", "opere",
    "operar agora", "recomend",
)


def test_leitura_nunca_recomenda_execucao():
    for estado in _todos_os_estados():
        texto = " ".join(
            vies.leitura_do_sinal(estado)
            + vies.observar_agora(estado)
            + (vies.texto_narrado(estado) or "",)
        ).lower()
        for termo in _VOCABULARIO_DE_EXECUCAO:
            assert termo not in texto, (termo, texto)


def test_leitura_armada_diz_o_que_desfaz_o_alinhamento():
    estado = _estado_armado()
    texto = " ".join(vies.observar_agora(estado)).lower()
    assert "desfaz" in texto


# --------------------------------------------------------------------------
# Smoke de desenho — sem tela real (offscreen via `qapp`)
# --------------------------------------------------------------------------


def _desenha_sem_excecao(estado, largura=384, altura=410):
    pixmap = QPixmap(largura, altura)
    painter = QPainter(pixmap)
    try:
        vies.desenhar(painter, QRect(0, 0, largura, altura), estado)
    finally:
        painter.end()


@pytest.mark.parametrize(
    "direcao",
    [DirecaoASG.COMPRA, DirecaoASG.VENDA, DirecaoASG.AGUARDAR, DirecaoASG.NEUTRA],
)
def test_desenha_cada_direcao(qapp, direcao):
    _desenha_sem_excecao(_estado(direcao=direcao))


def test_desenha_armado(qapp):
    _desenha_sem_excecao(_estado_armado())


def test_desenha_em_modo_compacto(qapp):
    """Abaixo do tamanho minimo do console a regiao cai para avatar+vies em
    vez de desenhar um console cortado por cima de si mesmo."""

    _desenha_sem_excecao(_estado_armado(), largura=160, altura=180)


def test_regiao_minuscula_nao_desenha_nada(qapp):
    _desenha_sem_excecao(_estado(), largura=60, altura=60)


# --------------------------------------------------------------------------
# 5. SEGURANDO — selo aceso que NAO afirma alinhamento
# --------------------------------------------------------------------------


def test_segurando_nao_e_confundido_com_armado():
    """O achado da rodada: com o selo aceso e a confluencia quebrada, o
    visor ao lado imprimia 'SEGURANDO' enquanto esta regiao afirmava, sem
    ressalva, que as fontes estavam alinhadas."""

    assert vies.fase_do_filtro(_estado_armado()) == vies.ARMADO
    assert vies.fase_do_filtro(_estado_segurando()) == vies.SEGURANDO


def test_leitura_em_segurando_nega_o_alinhamento():
    texto = " ".join(vies.leitura_do_sinal(_estado_segurando())).lower()
    assert "histerese" in texto
    assert "ja nao concordam" in texto
    # E jamais afirma o contrario.
    assert "estao alinhadas ao mesmo tempo" not in texto


def test_selo_em_segurando_nao_usa_a_cor_do_lado():
    """Aceso-com-alinhamento e aceso-por-histerese nao podem ter a mesma
    aparencia; era isso que fazia a regiao parecer confirmar o que caiu."""

    titulo, sub, cor = vies._texto_selo(_estado_segurando())
    assert "SEGURANDO" in titulo
    assert "SEM ALINHAMENTO" in sub
    assert cor == tokens.ALERT
    assert cor != tokens.PALETA_COR.compra


def test_narracao_em_segurando_pede_destaque_de_aviso():
    """CORRIGIDO em 28/08/2026: antes, `narracao_desatualizada` sinalizava
    que a frase mostrada em SEGURANDO era a de ARMADO reciclada (mentira).
    Agora a frase e propria de SEGURANDO e ja e o aviso — a faixa continua
    pedindo destaque, so que por importancia, nao por estar velha."""

    assert vies.narracao_desatualizada(_estado_segurando())
    assert not vies.narracao_desatualizada(_estado_armado())


def test_a_voz_afirma_alinhamento_apenas_quando_ele_existe():
    """Amarra o texto falado ao estado: a unica frase que afirma
    concordancia das fontes so pode aparecer em ARMADO."""

    frase_armado = vies.texto_narrado(_estado_armado())
    assert "concordam" in frase_armado.lower()
    # CORRIGIDO em 28/08/2026 ("a voz nao anuncia a perda de alinhamento"):
    # em SEGURANDO o locutor fala uma frase PROPRIA (nao mais a de ARMADO
    # reciclada) que NEGA o alinhamento em vez de afirma-lo.
    frase_segurando = vies.texto_narrado(_estado_segurando())
    assert "ja nao concordam" in frase_segurando.lower()
    assert frase_segurando != frase_armado


def test_tempo_aceso_nao_e_inventado_sem_base():
    """Sem `ligado_desde_ns` ou sem timestamp do quadro, nao ha o que medir."""

    sem_base = _estado(
        direcao=DirecaoASG.COMPRA,
        sinal_ultra=SinalUltraSnapshot(TS, DirecaoUltra.COMPRA,
                                       DirecaoUltra.COMPRA, None),
    )
    assert vies._tempo_aceso(sem_base) is None
    assert vies._tempo_aceso(_estado_armado()) == "HA 42S"


# --------------------------------------------------------------------------
# 6. O mapa de composicao — o vao que o contrato negava
# --------------------------------------------------------------------------


def test_o_par_do_centro_se_encosta_sem_vao_nem_sobreposicao():
    """O contrato de composicao afirmava "de borda a borda, sem vao" e havia
    ~440x216 px sem dono entre o visor e o OPERADOR IA."""

    from fluxopro.ui.paineis.nexo import REGIOES

    nucleo = REGIOES["nucleo"]
    vies_rect = REGIOES["vies"]
    assert nucleo[3] == vies_rect[1], "as duas regioes do par precisam encostar"
    assert (nucleo[0], nucleo[2]) == (vies_rect[0], vies_rect[2]), (
        "o par precisa dividir a MESMA coluna, senao a fronteira e um degrau"
    )
    assert vies_rect[3] == 1.00


def test_a_coluna_central_nao_tem_area_sem_dono_abaixo_do_visor():
    from fluxopro.ui.paineis.nexo import REGIOES

    passo = 0.002
    y = REGIOES["nucleo"][1]
    while y < 1.0:
        x = 0.40
        while x < 0.63:
            assert any(
                rx0 <= x < rx1 and ry0 <= y < ry1
                for (rx0, ry0, rx1, ry1) in REGIOES.values()
            ), f"celula sem dono em x={x:.3f} y={y:.3f}"
            x += passo
        y += passo


def test_todo_vao_remanescente_esta_declarado():
    """O defeito nao foi so o vao: foi o contrato AFIRMAR que nao havia vao.
    O que sobra fica enumerado e travado aqui — um vao NOVO reprova."""

    from fluxopro.ui.paineis.nexo import REGIOES, VAOS_SEM_DONO

    def coberto(mapa, x, y):
        return any(x0 <= x < x1 and y0 <= y < y1 for (x0, y0, x1, y1) in mapa)

    declarados = [faixa for _, faixa in VAOS_SEM_DONO]
    passo = 0.004
    y = 0.0
    while y < 1.0:
        x = 0.0
        while x < 1.0:
            if not coberto(REGIOES.values(), x, y):
                assert coberto(declarados, x, y), (
                    f"vao NAO declarado em x={x:.3f} y={y:.3f} — "
                    "acrescente a VAOS_SEM_DONO ou de dono a faixa"
                )
            x += passo
        y += passo


def test_nenhuma_regiao_se_sobrepoe_a_outra():
    from fluxopro.ui.paineis.nexo import REGIOES

    itens = list(REGIOES.items())
    for i, (nome_a, a) in enumerate(itens):
        for nome_b, b in itens[i + 1:]:
            if nome_a in {"niveis"} or nome_b in {"niveis"}:
                # `niveis` avanca 0,01 sobre as vizinhas de proposito — e o
                # encaixe do material de referencia, ver ORDEM_DESENHO.
                continue
            sobrepoe = (a[0] < b[2] and b[0] < a[2]
                        and a[1] < b[3] and b[1] < a[3])
            assert not sobrepoe, f"{nome_a} e {nome_b} se sobrepoem"
