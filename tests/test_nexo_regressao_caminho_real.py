"""Regressões da auditoria de 31/08/2026 — os defeitos que 2.050 testes
verdes NÃO pegaram porque nenhum deles passava pelo caminho real do app
(replay, com o painel montado e os motores publicando snapshot).

Cada teste aqui nasceu de um defeito MEDIDO no produto rodando, e não de
uma hipótese: a sonda sobre o replay de 2026-08-28 mostrou 128 de 138
quadros presos em RECOVERING, dominância 100% INDISPONIVEL e 100% das
zonas em NEUTRO com força 0,00.
"""

import pytest

from fluxopro.analytics import suporte_resistencia as sr
from fluxopro.analytics import velocidade_dual as vd


# ====================================================== sequencia por evento
def test_sequencia_repetida_no_mesmo_evento_nao_vira_gap():
    """O painel chama os motores a CADA QUADRO (60 fps), mas o `event_id`
    deriva do timestamp do snapshot, que muda muito mais devagar.

    Antes da correção o contador de sequência subia por quadro: o cache
    devolvia cedo sem registrar a sequência e, no primeiro timestamp novo,
    o motor via um salto de ~20 e declarava GAP. Como cada snapshot novo
    repetia o salto, o motor nunca saía de RECOVERING.
    """

    motor = sr.MotorSuporteResistencia(stream_id="t")
    micro = sr.HorizonteScore(0.5, 1.0, 0, 100)
    macro = sr.HorizonteScore(0.5, 1.0, 0, 100)

    def processar(seq, ts):
        return motor.processar(
            event_id=f"sr-{ts}", sequencia=seq, timestamp_ns=ts, instrumento="WDO",
            tick_size=0.5, agora_ns=ts, micro=micro, macro=macro,
            zonas_candidatas=(), ultimo_preco=10000,
        )

    # 20 quadros sobre o MESMO snapshot: um evento so, sequencia so.
    for _ in range(20):
        processar(1, 1_000)
    # Snapshot novo -> sequencia 2 (nao 21).
    saida = processar(2, 2_000)
    assert saude_de(saida) is not sr.EstadoFeed.GAP
    assert saude_de(saida) is not sr.EstadoFeed.RECOVERING


def saude_de(snapshot):
    return snapshot.saude.estado


def _painel_falso(timestamp_ns):
    """Painel mínimo que reusa os MÉTODOS REAIS de `PainelNexoMercadoASG`
    — mesmo padrão de `_painel_com_volante` em
    `test_nexo_placar_e_pressao_ponderados.py`.

    Este é o teste que faltava: os 2.050 testes verdes cobriam a
    matemática dos motores e o desenho isolado, mas NENHUM exercitava
    `_calcular_sr_snapshot` / `_calcular_dominancia_snapshot`, que é onde
    a sequência era incrementada por quadro.
    """

    from types import SimpleNamespace

    from fluxopro.analytics.dominancia import MotorDominancia
    from fluxopro.analytics.suporte_resistencia import MotorSuporteResistencia
    from fluxopro.core.eventos import WDO_GRID
    from fluxopro.ui.paineis import asg

    class _Falso:
        _calcular_sr_snapshot = asg.PainelNexoMercadoASG._calcular_sr_snapshot
        _calcular_dominancia_snapshot = asg.PainelNexoMercadoASG._calcular_dominancia_snapshot

    falso = _Falso()
    falso.grid = WDO_GRID
    falso._motor_sr = MotorSuporteResistencia(stream_id="t")
    falso._sr_sequencia = 0
    falso._sr_ultimo_ts = -1
    falso._motor_dominancia = MotorDominancia(stream_id="t")
    falso._dominancia_sequencia = 0
    falso._dominancia_ultimo_ts = -1
    falso._snapshot = SimpleNamespace(timestamp_ns=timestamp_ns,
                                      estado_operacional=asg.EstadoASG.REPLAY)
    return falso


def _estado_vazio():
    from fluxopro.ui.paineis.nexo import EstadoNexo

    return EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                      leituras=(), largura=1920, altura=1055)


def test_painel_nao_avanca_sequencia_enquanto_o_snapshot_nao_muda():
    """60 quadros sobre o MESMO snapshot têm de consumir UMA sequência.

    Medido no app real antes da correção: a sequência subia por quadro e o
    motor acusava GAP a cada snapshot novo, prendendo 128 de 138 quadros
    em RECOVERING e deixando a dominância 100% INDISPONIVEL.
    """

    painel = _painel_falso(1_000_000)
    estado = _estado_vazio()
    for _ in range(60):
        painel._calcular_sr_snapshot(estado)
        painel._calcular_dominancia_snapshot(estado)
    assert painel._sr_sequencia == 1
    assert painel._dominancia_sequencia == 1


def test_painel_avanca_uma_sequencia_por_snapshot_novo():
    painel = _painel_falso(1_000_000)
    estado = _estado_vazio()
    for indice in range(5):
        painel._snapshot.timestamp_ns = 1_000_000 * (indice + 1)
        for _ in range(12):  # varios quadros sobre cada snapshot
            painel._calcular_sr_snapshot(estado)
            painel._calcular_dominancia_snapshot(estado)
    assert painel._sr_sequencia == 5
    assert painel._dominancia_sequencia == 5


def test_painel_em_replay_nao_entra_em_recovering():
    """A consequência visível do defeito: com a sequência saltando, o selo
    do painel ficava escrito RECOVERING o pregão inteiro."""

    from fluxopro.analytics.dominancia import EstadoDominancia

    painel = _painel_falso(1_000_000)
    estado = _estado_vazio()
    vistos = set()
    for indice in range(40):
        painel._snapshot.timestamp_ns = 1_000_000 * (indice + 1)
        for _ in range(8):
            sr_snap = painel._calcular_sr_snapshot(estado)
            dom_snap = painel._calcular_dominancia_snapshot(estado)
        vistos.add(sr_snap.saude.estado)
        vistos.add(dom_snap.saude.estado)
    assert sr.EstadoFeed.RECOVERING not in vistos
    assert sr.EstadoFeed.GAP not in vistos
    assert EstadoDominancia is not None  # import usado como guarda de contrato


def test_modo_replay_percorre_o_caminho_de_sucesso_dos_dois_motores():
    """Guarda contra o `EstadoFeed.REPLAY` (membro inexistente) que
    estourava em TODO quadro de replay: o ramo `modo == "REPLAY"` não era
    exercitado por nenhum teste, e é justamente o modo que o operador usa.
    """

    painel = _painel_falso(1_000_000)
    estado = _estado_vazio()
    painel._snapshot.timestamp_ns = 2_000_000
    assert painel._calcular_sr_snapshot(estado) is not None
    assert painel._calcular_dominancia_snapshot(estado) is not None


# ============================================================ forca de zona
def test_forca_de_zona_usa_magnitude_e_nao_sinal():
    """Zona defendida por VENDEDORES (reposição negativa) é uma zona
    FORTE, não uma zona fraca: quem dá o lado é o contexto.

    Com R entrando assinado, a força de toda zona ficava em 0,00-0,22
    contra o limiar de 0,55 — nenhuma zona era confirmada no pregão
    inteiro, medido no replay real.
    """

    forca_compradora = sr.calcular_forca_zona(0.8, 0.6, 0.4, toques=5)
    forca_vendedora = sr.calcular_forca_zona(-0.8, -0.6, -0.4, toques=5)
    assert forca_vendedora == pytest.approx(forca_compradora)
    assert forca_vendedora >= sr.LIMIAR_FORCA_ZONA


def test_reposicao_negativa_nao_derruba_a_forca_abaixo_dos_toques():
    """Piso: com 5+ testes contados, a contribuição de toques (0,20)
    não pode ser cancelada por um componente negativo."""

    assert sr.calcular_forca_zona(-1.0, 0.0, 0.0, toques=5) >= 0.20


# =================================================== divergencia x contragiro
def test_divergencia_e_maxima_quando_horizontes_se_opoem():
    """`contragiro` mede a separação das pontas DESENHADAS na cena
    contra-rotativa, e por isso vale ~0 justamente na oposição máxima. Ele
    era impresso na tela sob o rótulo "CONTRA-GIRO": com micro +1,00 e
    macro -1,00 o painel mostrava `+0,0°`, que o operador lê como
    "horizontes alinhados" no pior momento possível."""

    oposto, _ = vd.divergencia_horizontes(1.0, -1.0)
    junto, _ = vd.divergencia_horizontes(1.0, 1.0)
    assert abs(oposto) > abs(junto)
    assert junto == pytest.approx(0.0)
    assert abs(oposto) == pytest.approx(vd.AMPLITUDE_ARCO_GRAUS)
    # E o contragiro (layout) continua com o comportamento invertido, de
    # proposito — este teste existe para que ninguem volte a imprimi-lo.
    assert abs(vd.contragiro(1.0, -1.0)[0]) < abs(vd.contragiro(1.0, 1.0)[0])


# ================================================= nucleo: direcao de mercado
def _estado_nucleo(dom_estado, risco=0.0, fase=None):
    from types import SimpleNamespace

    from fluxopro.ui.paineis.nexo import EstadoNexo

    return EstadoNexo(snapshot=None, serie=(), grid=None, paleta=None, maker=None,
                      leituras=(), largura=1920, altura=1055,
                      risco_volatilidade=risco, fase_renko=fase,
                      dominancia_snapshot=SimpleNamespace(estado=dom_estado))


def test_nucleo_mostra_direcao_do_mercado_sem_decisao_do_filtro():
    """Pedido do operador: "mostra a direção do mercado mesmo que sem
    ultra". Até 31/08/2026 o núcleo lia `decisao.direcao` e escrevia
    "SEM DECISAO" com o mercado claramente direcional — porque a decisão
    do FILTRO era AGUARDAR, que é outra pergunta."""

    from fluxopro.analytics.dominancia import EstadoDominancia
    from fluxopro.ui.paineis import asg
    from fluxopro.ui.paineis.nexo import nucleo

    aguardar = asg.DirecaoASG.AGUARDAR
    assert nucleo.leitura_do_nucleo(_estado_nucleo(EstadoDominancia.VENDA),
                                    aguardar) == nucleo.GLIFO_MERCADO_VENDA
    assert nucleo.leitura_do_nucleo(_estado_nucleo(EstadoDominancia.COMPRA),
                                    aguardar) == nucleo.GLIFO_MERCADO_COMPRA
    assert nucleo.leitura_do_nucleo(_estado_nucleo(EstadoDominancia.BALANCEADO),
                                    aguardar) == nucleo.GLIFO_NEUTRA


def test_nucleo_avisa_alta_volatilidade_sem_direcional():
    """A outra metade do pedido: "avisar momentos de alta volatilidade que
    o mercado esta sem direcional". Antes isto só olhava inversão de
    Renko, que é parente da volatilidade mas não é ela."""

    from fluxopro.analytics.dominancia import EstadoDominancia
    from fluxopro.ui.paineis import asg
    from fluxopro.ui.paineis.nexo import nucleo

    aguardar = asg.DirecaoASG.AGUARDAR
    alta = _estado_nucleo(EstadoDominancia.VENDA, risco=0.85)
    calma = _estado_nucleo(EstadoDominancia.VENDA, risco=0.20)
    assert nucleo.leitura_do_nucleo(alta, aguardar) == nucleo.GLIFO_ALTO_RISCO
    assert nucleo.leitura_do_nucleo(calma, aguardar) == nucleo.GLIFO_MERCADO_VENDA


def test_rotulo_do_nucleo_nunca_discorda_do_glifo():
    """Rótulo e glifo discordando é o padrão de defeito que mais se
    repetiu neste projeto — "MERCADO COMPRADOR" tem de ter rótulo próprio,
    e não herdar o título da decisão (que diria "SEM DECISAO")."""

    from fluxopro.ui.paineis.nexo import nucleo

    for glifo in (nucleo.GLIFO_MERCADO_COMPRA, nucleo.GLIFO_MERCADO_VENDA,
                  nucleo.GLIFO_NEUTRA, nucleo.GLIFO_ALTO_RISCO):
        assert glifo in nucleo._ROTULO_LEITURA
        assert nucleo._ROTULO_LEITURA[glifo].strip()


def test_divergencia_e_monotonica_em_toda_a_faixa():
    """Sem `wrap180`: divergência é grandeza linear. Com wrap, a diferença
    MÁXIMA (-2,0) dava +82° enquanto -1,0 dava -139° — magnitude menor e
    sinal trocado no pior caso."""

    anterior = None
    for passo in range(-20, 21):
        atual, _ = vd.divergencia_horizontes(0.0, passo / 20)
        if anterior is not None:
            assert atual > anterior
        anterior = atual
