"""Smoke tests do visor central (fluxopro/ui/paineis/nexo/nucleo.py).

Cobre especificamente o selo do Sinal Ultra (26/08/2026): o visor precisa
desenhar sem excecao e sem estourar a regiao quando `estado.sinal_ultra`
esta ativo, e o rotulo "SINAL CONSULTIVO" precisa virar o rotulo do Ultra
quando ele dispara.
"""

from PySide6.QtCore import QRect
import dataclasses
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.asg.sinal_ultra import ConfigSinalUltra, DirecaoUltra, SinalUltraSnapshot
from fluxopro.ui.paineis.asg import DecisaoASGSnapshot, MatrizASGSnapshot, WorkspaceASGSnapshot
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import nucleo


def _snapshot():
    return WorkspaceASGSnapshot(
        0,
        __import__("fluxopro.ui.paineis.asg", fromlist=["DadosASGSnapshot"]).DadosASGSnapshot(0),
        __import__("fluxopro.ui.paineis.asg", fromlist=["ProcessamentoASGSnapshot"]).ProcessamentoASGSnapshot(0),
        MatrizASGSnapshot(0),
        DecisaoASGSnapshot(0),
        __import__("fluxopro.ui.paineis.asg", fromlist=["TrilhaEvidenciasASGSnapshot"]).TrilhaEvidenciasASGSnapshot(0),
        contexto_bruto=None,
    )


def _estado(sinal_ultra):
    return EstadoNexo(
        snapshot=_snapshot(),
        serie=(),
        grid=None,
        paleta=None,
        maker=None,
        leituras=(),
        largura=400,
        altura=300,
        sinal_ultra=sinal_ultra,
    )


def _desenha_sem_excecao(qapp, sinal_ultra):
    pixmap = QPixmap(400, 300)
    painter = QPainter(pixmap)
    try:
        nucleo.desenhar(painter, QRect(0, 0, 400, 300), _estado(sinal_ultra))
    finally:
        painter.end()


def test_desenha_sem_sinal_ultra(qapp):
    _desenha_sem_excecao(qapp, None)


def test_desenha_com_ultra_compra_ativo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.COMPRA,
        confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=500,
    )
    _desenha_sem_excecao(qapp, snap)


def test_desenha_com_ultra_venda_ativo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.VENDA,
        confluencia_no_instante=DirecaoUltra.VENDA, ligado_desde_ns=500,
    )
    _desenha_sem_excecao(qapp, snap)


def test_ultra_nenhuma_nao_ativa_o_selo(qapp):
    snap = SinalUltraSnapshot(
        timestamp_ns=1_000, direcao=DirecaoUltra.NENHUMA,
        confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=None,
    )
    _desenha_sem_excecao(qapp, snap)


# ==========================================================================
# Painel de CONDICOES do filtro Ultra (28/08/2026)
# ==========================================================================
# O visor tinha dois estados de Ultra (aceso/apagado) e por isso "nunca
# aparecia nada": enquanto o filtro nao disparava — quase sempre, por
# construcao — a regiao nao dizia nada a respeito dele. O que se afirma aqui e
# que o diagnostico exibido e DERIVADO do mesmo estado que alimenta o motor,
# nunca um texto decorativo, e que ele nao inventa condicao atendida.
from fluxopro.analytics.renko import FaseRenko  # noqa: E402
from fluxopro.ui import tema_asg  # noqa: E402
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    DirecaoASG,
    LinhaMatrizASG,
    ProcedenciaASG,
)


class _Tijolo:
    def __init__(self, direcao):
        self.direcao = direcao


def _linha(componente, direcao, valor, forca, confianca, confianca_numerica=None):
    return LinhaMatrizASG(
        componente=componente, direcao=direcao, valor=valor, forca=forca,
        confianca=confianca, procedencia=ProcedenciaASG.DERIVADO,
        detalhe="ESTRUTURA DO DIA", confianca_numerica=confianca_numerica,
    )


def _estado_rico(direcao, fase, tijolos, forca, confianca_maker, regime=None,
                 sinal_ultra=None):
    base = _estado(None)
    return EstadoNexo(
        snapshot=base.snapshot, serie=(), grid=None, paleta=None,
        maker=_linha("MAKERPROXY", direcao, "x", forca, confianca_maker),
        leituras=(), largura=440, altura=430,
        tijolos_renko=tuple(_Tijolo(t) for t in tijolos), fase_renko=fase,
        regime=regime, sinal_ultra=sinal_ultra,
    )


def _condicoes(direcao, fase, tijolos, forca, confianca_maker):
    estado = _estado_rico(direcao, fase, tijolos, forca, confianca_maker)
    return nucleo._condicoes_ultra(estado, direcao)


def test_todas_as_condicoes_acendem_na_confluencia_completa():
    estado = _estado_rico(
        DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1, 1], 0.9, ConfiancaASG.ALTA,
        sinal_ultra=SinalUltraSnapshot(
            timestamp_ns=0, direcao=DirecaoUltra.COMPRA,
            confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=0,
        ),
    )
    itens = nucleo._condicoes_ultra(estado, DirecaoASG.COMPRA)
    assert [item.atendida for item in itens] == [True, True, True]


def test_ultra_usa_confianca_numerica_do_motor_em_mbp_parcial():
    """A classificação visual MEDIA não pode desligar o ULTRA quando o
    valor bruto atingiu o limiar próprio configurado pelo motor."""
    estado = _estado_rico(
        DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1, 1], 0.9,
        ConfiancaASG.MEDIA,
        sinal_ultra=SinalUltraSnapshot(
            timestamp_ns=0, direcao=DirecaoUltra.NENHUMA,
            confluencia_no_instante=DirecaoUltra.COMPRA, ligado_desde_ns=None,
            config=ConfigSinalUltra(exigir_maker_como_gate=True),
        ),
    )
    estado = dataclasses.replace(
        estado,
        maker=_linha(
            "MAKERPROXY", DirecaoASG.COMPRA, "x", 0.9,
            ConfiancaASG.MEDIA, confianca_numerica=0.60,
        ),
    )
    itens = nucleo._condicoes_ultra(estado, DirecaoASG.COMPRA)
    assert itens[2].atendida is True


def test_sem_decisao_nenhuma_condicao_direcional_acende():
    """AGUARDAR nao e direcao confirmada."""
    itens = _condicoes(DirecaoASG.AGUARDAR, FaseRenko.TENDENCIA, [1, 1], 0.9,
                       ConfiancaASG.ALTA)
    assert itens[0].atendida is False
    assert itens[1].atendida is False


def test_renko_nao_e_gate_mesmo_em_direcao_contraria():
    """Renko contrario continua sendo mostrado no grafico, mas nao bloqueia
    a confluencia oficial do ULTRA."""
    itens = _condicoes(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [-1], 0.9,
                       ConfiancaASG.ALTA)
    assert [item.rotulo for item in itens] == ["DECISAO", "CONTEXTO", "PERSISTENCIA"]
    assert itens[0].atendida and itens[1].atendida
    assert not itens[2].atendida


def test_o_limiar_do_maker_e_LIDO_da_configuracao_do_motor():
    """Nao ha numero redigitado no desenho: o limiar exibido e comparado sai
    de `ConfigSinalUltra`. Mutar a configuracao muda a leitura da tela."""
    limiar = ConfigSinalUltra().forca_maker_minima
    # Sem snapshot do motor no quadro (montagem antiga/teste) a regiao cai no
    # padrao — e ele tem de ser o padrao do MOTOR, nao um numero proprio. O
    # caso COM snapshot, que e o que roda em producao, esta amarrado por
    # mutacao em `test_a_janela_EXIBIDA_sai_do_motor_e_nao_de_um_default_da_UI`.
    assert nucleo._CONFIG_PADRAO.forca_maker_minima == limiar
    strict = SinalUltraSnapshot(
        timestamp_ns=0, direcao=DirecaoUltra.NENHUMA,
        confluencia_no_instante=DirecaoUltra.NENHUMA, ligado_desde_ns=None,
        config=ConfigSinalUltra(exigir_maker_como_gate=True),
    )
    abaixo = nucleo._condicoes_ultra(
        _estado_rico(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1], limiar - 0.01,
                     ConfiancaASG.ALTA, sinal_ultra=strict), DirecaoASG.COMPRA
    )
    acima = nucleo._condicoes_ultra(
        _estado_rico(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1], limiar + 0.01,
                     ConfiancaASG.ALTA, sinal_ultra=strict), DirecaoASG.COMPRA
    )
    assert abaixo[1].atendida is False
    assert acima[1].atendida is True


def test_forca_positiva_nao_atende_a_condicao_de_VENDA():
    """Solidariedade de sinal: sob decisao de VENDA a condicao pede forca
    NEGATIVA. Comparar so a grandeza deixaria um Maker comprador acender a
    lampada de uma confluencia vendedora."""
    itens = nucleo._condicoes_ultra(
        _estado_rico(DirecaoASG.VENDA, FaseRenko.TENDENCIA, [-1], 0.9,
                     ConfiancaASG.ALTA,
                     sinal_ultra=SinalUltraSnapshot(
                         timestamp_ns=0, direcao=DirecaoUltra.NENHUMA,
                         confluencia_no_instante=DirecaoUltra.NENHUMA,
                         ligado_desde_ns=None,
                         config=ConfigSinalUltra(exigir_maker_como_gate=True),
                     )),
        DirecaoASG.VENDA,
    )
    assert itens[1].atendida is False


def test_confianca_media_do_maker_nao_conta_como_alta():
    itens = nucleo._condicoes_ultra(
        _estado_rico(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1], 0.9,
                     ConfiancaASG.MEDIA,
                     sinal_ultra=SinalUltraSnapshot(
                         timestamp_ns=0, direcao=DirecaoUltra.NENHUMA,
                         confluencia_no_instante=DirecaoUltra.NENHUMA,
                         ligado_desde_ns=None,
                         config=ConfigSinalUltra(exigir_maker_como_gate=True),
                     )),
        DirecaoASG.COMPRA,
    )
    assert itens[2].atendida is False


def test_o_cartao_REGIME_nao_tem_cor_propria(qapp):
    """**Um numero, um sinal.**

    O cartao pintava COMPRADOR/VENDEDOR em ciano fixo — a palavra direcional
    mais destacada da tela fora do eixo de cor do quadro, com o mesmo token
    servindo para os dois lados. A cor tem de sair da direcao ja resolvida em
    `EstadoNexo.regime`, entao trocar a direcao (e so ela) tem de trocar a cor.
    """
    vendedor = _linha("REGIME", DirecaoASG.VENDA, "VENDEDOR", -1.0,
                      ConfiancaASG.MEDIA)
    comprador = _linha("REGIME", DirecaoASG.COMPRA, "COMPRADOR", 1.0,
                       ConfiancaASG.MEDIA)
    from fluxopro.ui.paineis import asg as _asg

    assert _asg._cor_nexo_direcao(vendedor.direcao) is tema_asg.NEXO_ROSA
    assert _asg._cor_nexo_direcao(comprador.direcao) is tema_asg.NEXO_VERDE
    assert _asg._cor_nexo_direcao(vendedor.direcao) is not tema_asg.NEXO_CIANO
    # E o desenho completo com regime presente segue sem excecao.
    pixmap = QPixmap(440, 430)
    painter = QPainter(pixmap)
    try:
        nucleo.desenhar(painter, QRect(0, 0, 440, 430),
                        _estado_rico(DirecaoASG.VENDA, FaseRenko.TENDENCIA,
                                     [-1], -0.9, ConfiancaASG.ALTA,
                                     regime=vendedor))
    finally:
        painter.end()


def test_regiao_estreita_nao_desenha_e_nao_estoura(qapp):
    """Abaixo do minimo a regiao SAI, em vez de entregar texto esmagado que o
    operador leria errado."""
    pixmap = QPixmap(200, 200)
    painter = QPainter(pixmap)
    try:
        nucleo.desenhar(painter, QRect(0, 0, 60, 60), _estado(None))
        # e num tamanho intermediario ainda desenha sem excecao
        nucleo.desenhar(painter, QRect(0, 0, 190, 120), _estado(None))
    finally:
        painter.end()


# ==========================================================================
# Janela de histerese OBSERVAVEL (28/08/2026)
# ==========================================================================
# O motor sempre soube ha quanto tempo a confluencia crua estava de pe; o que
# faltava era PUBLICAR. Sem isso a tela nao distinguia "a confluencia fechou
# agora" de "esta fechada ha 4,8s e falta um piscar" — as duas saiam mudas, o
# miolo do "nunca apareceu nada". Aqui se afirma que o campo novo e leitura do
# cronometro que o motor ja mantinha, que ele nao mexeu em quando o Ultra liga,
# e que o numero na tela vem da configuracao DAQUELE motor.
from fluxopro.asg.sinal_ultra import (  # noqa: E402
    ConfigSinalUltra,
    EntradaSinalUltra,
    MotorSinalUltra,
)

_S = 1_000_000_000


def _entrada(ts, direcao=DirecaoUltra.COMPRA, tijolo=1, forca=0.9):
    return EntradaSinalUltra(
        timestamp_ns=ts,
        direcao_decisao_confirmada=direcao,
        fase_renko=FaseRenko.TENDENCIA,
        direcao_renko=(DirecaoUltra.COMPRA if tijolo > 0 else DirecaoUltra.VENDA),
        forca_maker=forca,
        confianca_maker_alta=True,
    )


def test_a_janela_publicada_e_a_de_ARMAR_enquanto_apagado():
    motor = MotorSinalUltra()
    snap = motor.atualizar(_entrada(10 * _S))
    assert snap.direcao is DirecaoUltra.NENHUMA
    assert snap.pendente_desde_ns == 10 * _S
    assert snap.janela_alvo_ns == ConfigSinalUltra().persistencia_minima_ns


def test_o_cronometro_publicado_anda_com_a_confluencia():
    """O numero que a barra de confirmacao divide: `ts - pendente_desde_ns`."""
    motor = MotorSinalUltra()
    motor.atualizar(_entrada(10 * _S))
    snap = motor.atualizar(_entrada(13 * _S))
    assert snap.timestamp_ns - snap.pendente_desde_ns == 3 * _S
    assert snap.direcao is DirecaoUltra.NENHUMA  # 3s < 5s: ainda nao ligou


def test_ligado_e_estavel_nao_tem_janela_pendente():
    """`0` significa "nao ha transicao correndo" — e a barra some, em vez de
    ficar parada em 100% fingindo que algo ainda esta sendo contado."""
    motor = MotorSinalUltra()
    motor.atualizar(_entrada(0))
    snap = motor.atualizar(_entrada(6 * _S))
    assert snap.direcao is DirecaoUltra.COMPRA
    assert snap.janela_alvo_ns == 0


def test_aceso_com_confluencia_QUEBRADA_publica_a_janela_de_desligar():
    """A metade assimetrica da histerese: quem escolhe qual janela vale e o
    motor, nunca a regiao que desenha."""
    motor = MotorSinalUltra()
    motor.atualizar(_entrada(0))
    motor.atualizar(_entrada(6 * _S))
    snap = motor.atualizar(_entrada(7 * _S, direcao=DirecaoUltra.NENHUMA))
    assert snap.direcao is DirecaoUltra.COMPRA  # histerese segurando
    assert snap.janela_alvo_ns == ConfigSinalUltra().tempo_para_desligar_ns
    assert snap.pendente_desde_ns == 7 * _S


def test_publicar_a_janela_NAO_mudou_quando_o_ultra_liga_ou_desliga():
    """**A condicao que o coordenador impos.**

    O campo e observabilidade, nao semantica: a serie de estados de uma
    passada completa (liga apos 5s, segura 8s, so entao desliga) tem de ser
    exatamente a mesma de antes."""
    motor = MotorSinalUltra()
    ligou_em = None
    desligou_em = None
    for segundo in range(0, 30):
        alvo = DirecaoUltra.COMPRA if segundo < 10 else DirecaoUltra.NENHUMA
        snap = motor.atualizar(_entrada(segundo * _S, direcao=alvo))
        if ligou_em is None and snap.direcao is DirecaoUltra.COMPRA:
            ligou_em = segundo
        if ligou_em is not None and desligou_em is None and snap.direcao is DirecaoUltra.NENHUMA:
            desligou_em = segundo
    assert ligou_em == 5      # persistencia_minima_ns
    assert desligou_em == 18  # quebrou em 10, + tempo_para_desligar_ns


def test_a_janela_EXIBIDA_sai_do_motor_e_nao_de_um_default_da_UI():
    """**A prova por mutacao, estendida ao campo novo.**

    Se a regiao construisse a propria `ConfigSinalUltra`, um motor com janela
    customizada continuaria desenhando "5,0 S" e a tela mentiria em silencio.
    Como o numero vem de `SinalUltraSnapshot`, mudar a configuracao DO MOTOR
    muda a leitura."""
    custom = ConfigSinalUltra(persistencia_minima_ns=12 * _S,
                              forca_maker_minima=0.8,
                              exigir_maker_como_gate=True)
    motor = MotorSinalUltra(custom)
    snap = motor.atualizar(_entrada(0))
    assert snap.janela_alvo_ns == 12 * _S
    assert snap.config is custom
    assert snap.config.forca_maker_minima == 0.8
    # E o limiar do painel de condicoes segue esse mesmo objeto: com 0,8 uma
    # forca de 0,7 deixa de atender, embora atendesse sob o padrao de 0,5.
    estado = _estado_rico(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1], 0.7,
                          ConfiancaASG.ALTA)
    estado_custom = dataclasses.replace(estado, sinal_ultra=snap)
    assert nucleo._condicoes_ultra(estado, DirecaoASG.COMPRA)[1].atendida is True
    assert nucleo._condicoes_ultra(estado_custom, DirecaoASG.COMPRA)[1].atendida is False


def test_desenha_a_barra_de_confirmacao_sem_excecao(qapp):
    motor = MotorSinalUltra()
    motor.atualizar(_entrada(0))
    snap = motor.atualizar(_entrada(3 * _S))
    estado = dataclasses.replace(
        _estado_rico(DirecaoASG.COMPRA, FaseRenko.TENDENCIA, [1], 0.9,
                     ConfiancaASG.ALTA),
        sinal_ultra=snap,
    )
    pixmap = QPixmap(440, 430)
    painter = QPainter(pixmap)
    try:
        nucleo.desenhar(painter, QRect(0, 0, 440, 430), estado)
    finally:
        painter.end()
