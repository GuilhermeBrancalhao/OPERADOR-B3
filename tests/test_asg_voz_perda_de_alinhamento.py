"""Cobre o achado de auditoria pos-entrega (28/08/2026): "a voz nao anuncia a
perda de alinhamento do Ultra". `_atualizar_sinal_ultra` so falava em
TRANSICAO DE DIRECAO (armou/encerrou); o selo podia continuar aceso do mesmo
lado enquanto a confluencia crua ja tinha quebrado (fase SEGURANDO em
`nexo.vies.fase_do_filtro`) sem que o locutor dissesse nada — o visor central
e o OPERADOR IA ja mostravam isso na tela, so a voz ficava muda.

O motor real (`MotorSinalUltra`) ja tem testes proprios (`test_asg_sinal_ultra.py`);
aqui o motor e SUBSTITUIDO por um dublê que devolve snapshots pre-roteirizados,
para testar so o GATILHO de voz em `asg.py`, isolado da histerese real.
"""

from fluxopro.asg.sinal_ultra import DirecaoUltra, SinalUltraSnapshot
from fluxopro.audio.voz import (
    texto_para_perda_de_alinhamento,
    texto_para_realinhamento,
    texto_para_transicao_ultra,
)
from fluxopro.ui.paineis.asg import PainelNexoMercadoASG


class _MotorDublê:
    """Devolve, em ordem, os snapshots que o teste roteirizou — nunca
    calcula histerese de verdade. `entrada` e ignorada de proposito."""

    def __init__(self, snapshots):
        self._fila = list(snapshots)

    def atualizar(self, entrada):
        return self._fila.pop(0)


def _snapshot(ts, direcao, confluencia):
    ligado_desde = 0 if direcao is not DirecaoUltra.NENHUMA else None
    return SinalUltraSnapshot(ts, direcao, confluencia, ligado_desde)


class _Locutor:
    def __init__(self):
        self.falas: list[str] = []

    def falar(self, texto):
        if texto is not None:
            self.falas.append(texto)


def _painel_com_roteiro(snapshots):
    painel = PainelNexoMercadoASG()
    painel._sinal_ultra = _MotorDublê(snapshots)
    painel._locutor = _Locutor()
    return painel


def test_perda_de_alinhamento_e_anunciada_sem_mudar_de_direcao(qapp):
    """ARMADO (confluencia concorda) -> SEGURANDO (confluencia quebrou, mas
    o selo continua COMPRA) tem de falar a frase de perda, nao ficar mudo."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.COMPRA, DirecaoUltra.COMPRA),   # ARMADO
        _snapshot(2, DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),  # SEGURANDO
    ])

    painel._atualizar_sinal_ultra(1)
    assert painel._locutor.falas == [
        texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA)
    ]

    painel._atualizar_sinal_ultra(2)
    assert painel._locutor.falas[-1] == texto_para_perda_de_alinhamento(DirecaoUltra.COMPRA)
    assert len(painel._locutor.falas) == 2


def test_realinhamento_e_anunciado_depois_de_segurando(qapp):
    """SEGURANDO -> ARMADO de novo (confluencia voltou a concordar, mesma
    direcao o tempo todo) tem de falar o realinhamento."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.VENDA, DirecaoUltra.VENDA),    # ARMADO
        _snapshot(2, DirecaoUltra.VENDA, DirecaoUltra.NENHUMA),  # SEGURANDO
        _snapshot(3, DirecaoUltra.VENDA, DirecaoUltra.VENDA),    # ARMADO de novo
    ])

    painel._atualizar_sinal_ultra(1)
    painel._atualizar_sinal_ultra(2)
    painel._atualizar_sinal_ultra(3)

    assert painel._locutor.falas[-1] == texto_para_realinhamento(DirecaoUltra.VENDA)
    assert len(painel._locutor.falas) == 3


def test_desarme_por_histerese_nao_dobra_com_perda_de_alinhamento(qapp):
    """SEGURANDO -> NENHUMA (a histerese finalmente desarma) tem de falar
    SO o encerramento, nunca o encerramento E a perda juntos no mesmo
    instante — sao o mesmo evento contado uma vez."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.COMPRA, DirecaoUltra.COMPRA),   # ARMADO
        _snapshot(2, DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),  # SEGURANDO
        _snapshot(3, DirecaoUltra.NENHUMA, DirecaoUltra.NENHUMA), # desarmou
    ])

    for ts in (1, 2, 3):
        painel._atualizar_sinal_ultra(ts)

    assert painel._locutor.falas == [
        texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA),
        texto_para_perda_de_alinhamento(DirecaoUltra.COMPRA),
        texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),
    ]


def test_armar_direto_nunca_fala_perda_de_alinhamento_junto(qapp):
    """NENHUMA -> ARMADO no mesmo quadro (primeiro sinal do dia) tem de
    falar so o anuncio de armado — a fase tambem mudou (AUSENTE/SEM_SINAL
    -> ARMADO), mas a transicao de DIRECAO manda, sem narrar a fase
    separadamente na mesma virada."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.COMPRA, DirecaoUltra.COMPRA),
    ])

    painel._atualizar_sinal_ultra(1)

    assert painel._locutor.falas == [
        texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA)
    ]


def test_reversao_direta_de_lado_nao_anuncia_perda_de_alinhamento(qapp):
    """COMPRA armado -> VENDA armado direto (reversao) e transicao de
    DIRECAO — fala so a reversao, nunca uma "perda de alinhamento" da
    compra que esta saindo."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.COMPRA, DirecaoUltra.COMPRA),
        _snapshot(2, DirecaoUltra.VENDA, DirecaoUltra.VENDA),
    ])

    painel._atualizar_sinal_ultra(1)
    painel._atualizar_sinal_ultra(2)

    assert painel._locutor.falas == [
        texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA),
        texto_para_transicao_ultra(DirecaoUltra.COMPRA, DirecaoUltra.VENDA),
    ]


def test_permanecer_em_segurando_nao_repete_o_aviso_a_cada_quadro(qapp):
    """A fase nao mudou entre os dois quadros (continua SEGURANDO) —
    repetir o aviso a cada snapshot seria ruido, nao anuncio."""

    painel = _painel_com_roteiro([
        _snapshot(1, DirecaoUltra.COMPRA, DirecaoUltra.COMPRA),
        _snapshot(2, DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),
        _snapshot(3, DirecaoUltra.COMPRA, DirecaoUltra.NENHUMA),
    ])

    for ts in (1, 2, 3):
        painel._atualizar_sinal_ultra(ts)

    assert painel._locutor.falas == [
        texto_para_transicao_ultra(DirecaoUltra.NENHUMA, DirecaoUltra.COMPRA),
        texto_para_perda_de_alinhamento(DirecaoUltra.COMPRA),
    ]
