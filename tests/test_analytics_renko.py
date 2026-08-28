from __future__ import annotations

from fluxopro.analytics.renko import ConfigRenko, FaseRenko, Renko
from fluxopro.core.eventos import WDO_GRID, WIN_GRID


def test_tamanho_do_tijolo_converte_pontos_para_ticks_do_grid():
    renko_wdo = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    assert renko_wdo.tamanho_tijolo_ticks == 8  # 4 pontos / 0,5 pt por tick

    # WIN tem tick de 5 pontos: 4 pontos pedidos nao cabem em 1 tick inteiro,
    # e o agregador nunca produz tijolo de tamanho zero.
    renko_win = Renko(WIN_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    assert renko_win.tamanho_tijolo_ticks == 1


def test_nenhum_tijolo_ate_deslocar_o_tamanho_completo():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))  # 8 ticks
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_004)  # desloca 4 ticks, nao fecha tijolo (precisa 8)
    assert renko.tijolos == ()


def test_um_tijolo_fecha_exatamente_no_deslocamento_configurado():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))  # 8 ticks
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)
    tijolos = renko.tijolos
    assert len(tijolos) == 1
    assert tijolos[0].abertura == 100_000
    assert tijolos[0].fechamento == 100_008
    assert tijolos[0].direcao == 1


def test_reversao_exige_o_dobro_do_tamanho_do_tijolo():
    """Um tijolo de alta so reverte quando o preco cai o tamanho inteiro
    a partir do FECHAMENTO do ultimo tijolo — nao a partir do pico."""
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))  # 8 ticks
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)  # 1 tijolo de alta, ancora = 100_008
    renko.registrar(2, 100_001)  # cai 7 ticks, nao fecha reversao (precisa 8)
    assert len(renko.tijolos) == 1
    renko.registrar(3, 100_000)  # cai 8 ticks a partir da ancora -> fecha
    tijolos = renko.tijolos
    assert len(tijolos) == 2
    assert tijolos[1].direcao == -1
    assert tijolos[1].abertura == 100_008
    assert tijolos[1].fechamento == 100_000


def test_movimento_grande_de_uma_vez_fecha_varios_tijolos():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))  # 8 ticks
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_000 + 8 * 5)  # 5 tijolos de alta de uma vez
    tijolos = renko.tijolos
    assert len(tijolos) == 5
    assert all(t.direcao == 1 for t in tijolos)
    assert tijolos[-1].fechamento == 100_000 + 8 * 5


def test_fase_indefinida_com_menos_de_dois_tijolos():
    renko = Renko(WDO_GRID)
    assert renko.fase is FaseRenko.INDEFINIDA
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)
    assert renko.fase is FaseRenko.INDEFINIDA  # so 1 tijolo fechado


def test_fase_tendencia_com_tijolos_seguidos_na_mesma_direcao():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0, tijolos_para_tendencia=3))
    preco = 100_000
    renko.registrar(0, preco)
    for i in range(1, 4):
        preco += 8
        renko.registrar(i, preco)  # 3 tijolos de alta seguidos
    assert renko.fase is FaseRenko.TENDENCIA


def test_fase_possivel_inversao_apos_sequencia_que_vira():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0, tijolos_para_tendencia=3))
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)  # tijolo 1: alta
    renko.registrar(2, 100_016)  # tijolo 2: alta (sequencia de 2 na mesma direcao)
    renko.registrar(3, 100_008)  # tijolo 3: baixa -> inverte a sequencia anterior
    assert renko.fase is FaseRenko.POSSIVEL_INVERSAO


def test_fase_perdendo_forca_em_alternancia_simples():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0, tijolos_para_tendencia=3))
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)  # alta
    renko.registrar(2, 100_000)  # baixa (so 1 tijolo antes, nao caracteriza inversao de sequencia)
    assert renko.fase is FaseRenko.PERDENDO_FORCA


def test_alvos_nenhum_antes_do_primeiro_tijolo():
    renko = Renko(WDO_GRID)
    assert renko.alvos() is None


def test_alvos_sao_simetricos_e_ancorados_no_ultimo_fechamento():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)
    alvos = renko.alvos()
    assert alvos is not None
    ancora = 100_008
    passo = alvos.positivos[0] - ancora
    assert passo > 0
    assert alvos.positivos == (ancora + passo, ancora + passo * 2, ancora + passo * 3)
    assert alvos.negativos == (ancora - passo, ancora - passo * 2, ancora - passo * 3)


def test_pior_preco_para_comprar_e_vender_bate_com_a1_de_cada_lado():
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_008)
    alvos = renko.alvos()
    assert alvos is not None
    assert alvos.pior_preco_para_venda() == alvos.positivos[0]
    assert alvos.pior_preco_para_compra() == alvos.negativos[0]


def test_retencao_nao_cresce_sem_teto_em_20_mil_eventos():
    """Mesmo criterio de retencao do resto do projeto: 1.000 e 20.000
    eventos precisam produzir o MESMO tamanho de colecao alcancavel."""
    config = ConfigRenko(tamanho_tijolo_pontos=4.0, maxlen_tijolos=50)

    def _rodar(n_eventos: int) -> int:
        renko = Renko(WDO_GRID, config)
        preco = 100_000
        for i in range(n_eventos):
            preco += 8  # sempre fecha exatamente 1 tijolo de alta por evento
            renko.registrar(i, preco)
        return len(renko.tijolos)

    tamanho_1k = _rodar(1_000)
    tamanho_20k = _rodar(20_000)
    assert tamanho_1k <= config.maxlen_tijolos
    assert tamanho_20k <= config.maxlen_tijolos
    assert tamanho_20k == tamanho_1k


def test_aquecimento_destrava_tijolo_maior_que_a_amplitude_do_dia():
    """Defeito de 28/08/2026: impasse de partida.

    O tamanho de partida (4 pontos = 8 ticks no WDO) era maior que TODA a
    amplitude da sessao real de 27/08 na janela capturada (2,5 pontos = 5
    ticks). Nenhum tijolo fechava; e como a recalibragem dinamica so rodava
    ao FECHAR um tijolo, ela nunca rodava. Resultado: a maior regiao do
    painel ficava literalmente vazia com 519 negocios carregados.
    """
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    assert renko.tamanho_tijolo_ticks == 8  # semente, antes de qualquer preco

    # 200 negocios oscilando dentro de uma faixa de 5 ticks — exatamente o
    # regime do pregao capturado.
    base = 100_000
    for i in range(200):
        renko.registrar(i, base + (i % 6))

    assert renko.tamanho_tijolo_ticks < 8, "o aquecimento tem de encolher o tijolo"
    assert renko.tijolos, "com 200 negocios reais a regiao nao pode ficar vazia"


def test_piso_do_tijolo_e_um_tick_do_papel_nao_um_numero_de_pontos():
    """O piso vive em TICKS: em papel de tick fino, piso em pontos era maior
    que a amplitude inteira e zerava o Renko."""
    renko = Renko(WDO_GRID, ConfigRenko(tamanho_tijolo_pontos=4.0))
    for i in range(200):
        renko.registrar(i, 100_000 + (i % 3))
    assert renko.tamanho_tijolo_ticks == 1


def test_aquecimento_para_assim_que_o_primeiro_tijolo_fecha():
    """Depois do primeiro fechamento vale so a recalibragem por tijolos —
    mudar o tamanho a cada negocio quebraria a leitura da fase no meio do
    movimento."""
    config = ConfigRenko(tamanho_tijolo_pontos=1.0, recalibrar_a_cada_tijolos=10_000)
    renko = Renko(WDO_GRID, config)
    renko.registrar(0, 100_000)
    renko.registrar(1, 100_002)  # fecha tijolo (1 ponto = 2 ticks)
    tam = renko.tamanho_tijolo_ticks
    for i in range(2, 400):
        renko.registrar(i, 100_002 + (i % 2))
    assert renko.tamanho_tijolo_ticks == tam
