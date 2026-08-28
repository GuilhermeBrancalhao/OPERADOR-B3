"""Smoke test do VAP (fluxopro/ui/paineis/nexo/ladder.py).

Cobre o retoque visual (26/08/2026, barras em gradiente + marcador de POC):
so precisa desenhar sem excecao, com e sem niveis, com e sem POC.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.core.eventos import WDO_GRID
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.ui.paineis.nexo import ladder
from fluxopro.ui.paineis.nexo.ladder import montar_linhas


def _estado(vap_niveis=(), vap_poc=None, serie=()):
    return EstadoNexo(
        snapshot=None,
        serie=serie,
        grid=WDO_GRID,
        paleta=None,
        maker=None,
        leituras=(),
        largura=200,
        altura=300,
        vap_niveis=vap_niveis,
        vap_poc=vap_poc,
    )


def _desenha_sem_excecao(estado):
    pixmap = QPixmap(200, 300)
    painter = QPainter(pixmap)
    try:
        ladder.desenhar(painter, QRect(0, 0, 200, 300), estado)
    finally:
        painter.end()


def test_desenha_sem_vap(qapp):
    _desenha_sem_excecao(_estado())


def test_desenha_com_niveis_e_poc(qapp):
    niveis = (
        (100000, 500, 300, 200, True),
        (100001, 900, 100, 800, True),
        (100002, 120, 60, 60, False),
        (100003, 750, 700, 50, True),
    )
    estado = _estado(vap_niveis=niveis, vap_poc=100001, serie=((0, 100001, 0.0, 1),))
    _desenha_sem_excecao(estado)


def test_desenha_com_niveis_sem_poc_destacado_visivel(qapp):
    niveis = ((100000, 500, 300, 200, True),)
    estado = _estado(vap_niveis=niveis, vap_poc=999999, serie=((0, 100000, 0.0, 1),))
    _desenha_sem_excecao(estado)


def test_montar_linhas_tick_a_tick_quando_o_perfil_cabe(qapp):
    por_tick = {100_000: (10, 6, 4, True), 100_002: (5, 1, 4, False)}
    linhas, passo = montar_linhas(por_tick, 100_000, 100_002, 100_001, n_linhas=8)
    assert passo == 1
    assert len(linhas) == 8
    # nenhum nivel some, e o ultimo negocio esta na janela
    precos = [linha[0] for linha in linhas]
    assert 100_000 in precos and 100_002 in precos and 100_001 in precos
    assert sum(linha[2] for linha in linhas) == 15


def test_montar_linhas_agrupa_em_vez_de_recortar_perfil_alto(qapp):
    """Defeito de 27/08/2026: perfil mais alto que a regiao perdia niveis
    (inclusive o POC) porque a janela era recortada."""

    por_tick = {100_000 + i: (i + 1, i + 1, 0, i == 199) for i in range(200)}
    linhas, passo = montar_linhas(por_tick, 100_000, 100_199, 100_000, n_linhas=20)
    assert passo == 10
    assert len(linhas) == 20
    # o volume inteiro do perfil continua na tela
    assert sum(linha[2] for linha in linhas) == sum(range(1, 201))
    # e cada linha cobre exatamente `passo` ticks, sem buraco entre elas
    for anterior, atual in zip(linhas, linhas[1:]):
        assert anterior[0] - anterior[1] + 1 == passo
        assert atual[0] == anterior[1] - 1


def test_seletor_de_timeframe_tem_tres_segmentos_sem_sobreposicao(qapp):
    caixas = ladder.retangulos_timeframe(QRect(0, 0, 210, 580))
    assert set(caixas) == {0, 5, 15}
    ordenadas = [caixas[m] for m in (0, 5, 15)]
    for anterior, atual in zip(ordenadas, ordenadas[1:]):
        assert anterior.right() < atual.left()
    assert not ladder.retangulos_timeframe(QRect(0, 0, 40, 580))


def test_seletor_nao_encosta_no_rodape_que_cicla(qapp):
    caixa = QRect(0, 0, 210, 580)
    rodape = ladder.retangulo_rotulo(caixa)
    for segmento in ladder.retangulos_timeframe(caixa).values():
        assert not segmento.intersects(rodape)


def _perfil_de_sessao_com_print_aberrante():
    """Forma real do pregao de 27/08/2026 (WDOU26): 69 niveis colados entre
    10.291 e 10.359 ticks, mais UM print isolado em 5.086 — exatamente o que
    quebrou a aba SESSAO no retrato do pregao inteiro."""

    por_tick = {}
    for i in range(69):
        preco = 10_291 + i
        volume = 500 + i * 37
        por_tick[preco] = (volume, volume // 2, volume - volume // 2, i in (40, 41, 42))
    por_tick[5_086] = (3, 3, 0, False)
    return por_tick


def test_escala_do_vap_vem_do_volume_e_nao_do_print_aberrante(qapp):
    por_tick = _perfil_de_sessao_com_print_aberrante()
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    faixa = ladder.faixa_por_volume(por_tick, poc)
    assert faixa is not None
    tick_min, tick_max, niveis_fora, volume_fora = faixa
    assert (tick_min, tick_max) == (10_291, 10_359)
    assert niveis_fora == 1 and volume_fora == 3


def test_sessao_desenha_barras_dentro_da_faixa_negociada_e_marca_o_poc(qapp):
    """Defeito julgado em 28/08/2026: no modo SESSAO a escada saia de 5.108,0
    a 2.605,5, sem nenhuma barra e sem o POC anunciado no cabecalho."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    tick_min, tick_max, _, _ = ladder.faixa_por_volume(por_tick, poc)
    linhas, passo = montar_linhas(por_tick, tick_min, tick_max, 10_334, n_linhas=36)

    assert passo <= 2, "69 ticks em 36 linhas nao podem virar passo de escala gigante"
    assert any(linha[1] <= poc <= linha[0] for linha in linhas), "POC tem de estar na escada"
    # toda linha cai dentro da faixa negociada (com a folga de uma linha)
    assert linhas[0][0] <= tick_max + passo
    assert linhas[-1][1] >= tick_min - 36 * passo
    # e a maior parte das linhas realmente tem barra (volume > 0)
    com_volume = [linha for linha in linhas if linha[2] > 0]
    assert len(com_volume) >= 30, f"so {len(com_volume)} linhas com barra"


def test_sessao_com_print_aberrante_desenha_sem_excecao(qapp):
    por_tick = _perfil_de_sessao_com_print_aberrante()
    niveis = tuple((p,) + v for p, v in sorted(por_tick.items()))
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    estado = EstadoNexo(
        snapshot=None,
        serie=((0, 10_334, 0.0, 1),),
        grid=WDO_GRID,
        paleta=None,
        maker=None,
        leituras=(),
        largura=210,
        altura=584,
        vap_niveis=niveis,
        vap_poc=poc,
        vap_val=10_319,
        vap_vah=10_357,
        vap_volume_total=sum(v[0] for v in por_tick.values()),
    )
    pixmap = QPixmap(210, 584)
    painter = QPainter(pixmap)
    try:
        ladder.desenhar(painter, QRect(0, 0, 210, 584), estado)
    finally:
        painter.end()


def test_maxima_e_minima_do_pregao_ficam_na_escala_o_print_distante_nao(qapp):
    """Critica de 28/08/2026: cortar a extremidade do dia faz o VAP deixar de
    ser o mapa do dia. Faixa real medida no tape gravado de 27/08 (WDOU26):
    69 niveis colados, 10.291 (5.145,5) a 10.359 (5.179,5). O print distante
    do cenario de livro (2.543,0) nao pode ditar a escala."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    tick_min, tick_max, _, _ = ladder.faixa_por_volume(por_tick, poc)

    assert tick_min == 10_291, "minima negociada tem de ficar DENTRO da escala"
    assert tick_max == 10_359, "maxima negociada tem de ficar DENTRO da escala"

    linhas, passo = montar_linhas(por_tick, tick_min, tick_max, 10_334, n_linhas=34)
    assert any(linha[1] <= 10_359 <= linha[0] for linha in linhas)
    assert any(linha[1] <= 10_291 <= linha[0] for linha in linhas)
    assert not any(linha[1] <= 5_086 <= linha[0] for linha in linhas)


def test_nivel_fora_da_escala_e_localizavel_pelo_preco(qapp):
    """Contar quantos ficaram de fora nao e "nao esconder": sem o preco o
    nivel e inlocalizavel. `niveis_fora_da_escala` devolve preco e volume,
    do mais proximo da faixa para o mais distante, para a linha de ponta."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    por_tick[10_400] = (11, 5, 6, False)
    abaixo, acima = ladder.niveis_fora_da_escala(por_tick, 10_291, 10_359)

    assert abaixo == ((5_086, 3),)
    assert acima == ((10_400, 11),)
    # nenhum nivel da faixa negociada e classificado como fora
    assert all(preco < 10_291 for preco, _ in abaixo)
    assert all(preco > 10_359 for preco, _ in acima)


def test_rotulo_de_linha_agrupada_expressa_a_faixa_e_nao_um_preco_so(qapp):
    """Critica de 28/08/2026: com AGRUPADO 2 TICKS a linha do POC exibia
    `5.166,5 · 134,0k`, mas o tape tem 68.678 em 5.166,5 e 65.368 em 5.166,0.
    Nenhum rotulo de preco unico pode carregar volume de mais de um nivel."""

    assert ladder.rotulo_faixa(WDO_GRID, 10_333, 10_333) == "5.166,5"
    faixa = ladder.rotulo_faixa(WDO_GRID, 10_332, 10_333)
    assert "—" in faixa
    assert faixa.startswith("5.166,0") and faixa.endswith("6,5")


def test_nenhuma_linha_com_volume_de_dois_niveis_tem_rotulo_de_preco_unico(qapp):
    """Invariante geral da escada: se a linha soma mais de um nivel com
    volume, o rotulo TEM de expressar faixa."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    tick_min, tick_max, _, _ = ladder.faixa_por_volume(por_tick, poc)
    # 69 niveis em 36 linhas -> passo 2, que e exatamente o caso do retrato
    # do pregao inteiro ("AGRUPADO 2 TICKS").
    linhas, passo = montar_linhas(por_tick, tick_min, tick_max, 10_334, n_linhas=36)
    assert passo == 2, "esta fixture existe justamente para exercitar o agrupamento"

    for tick_topo, tick_base, volume, _, _, _ in linhas:
        niveis_com_volume = [t for t in range(tick_base, tick_topo + 1) if por_tick.get(t)]
        rotulo = ladder.rotulo_faixa(WDO_GRID, tick_base, tick_topo)
        if len(niveis_com_volume) > 1:
            assert "—" in rotulo, f"linha soma {len(niveis_com_volume)} niveis com rotulo {rotulo!r}"
            assert volume == sum(por_tick[t][0] for t in niveis_com_volume)
        elif tick_base == tick_topo:
            assert "—" not in rotulo


def test_linha_de_fora_da_escala_com_dois_niveis_rotula_a_faixa(qapp):
    """Mesma regra na linha de ponta: o volume ali e a soma dos niveis fora,
    entao o rotulo nao pode ser um preco unico com `+1` colado."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    por_tick[5_087] = (80, 40, 40, False)
    abaixo, _ = ladder.niveis_fora_da_escala(por_tick, 10_291, 10_359)
    precos = [preco for preco, _ in abaixo]
    assert len(precos) == 2
    rotulo = ladder.rotulo_faixa(WDO_GRID, min(precos), max(precos))
    assert "—" in rotulo


def test_linha_de_fora_da_escala_cabe_acima_do_rodape(qapp):
    """A linha de ponta so cumpre o papel dela se estiver VISIVEL: o corpo
    nao pode transbordar a area util e empurra-la para baixo do rodape."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    niveis = tuple((p,) + v for p, v in sorted(por_tick.items()))
    estado = EstadoNexo(
        snapshot=None,
        serie=((0, 10_334, 0.0, 1),),
        grid=WDO_GRID,
        paleta=None,
        maker=None,
        leituras=(),
        largura=211,
        altura=598,
        vap_niveis=niveis,
        vap_poc=max(por_tick, key=lambda p: por_tick[p][0]),
        vap_val=10_319,
        vap_vah=10_357,
        vap_volume_total=sum(v[0] for v in por_tick.values()),
    )
    # Varre varias alturas: o defeito de 28/08/2026 so aparecia quando o
    # arredondamento de `altura` batia certo (no retrato de 1080 a linha caiu
    # POR BAIXO do rodape e sumiu), entao fixar uma altura so nao prende.
    for altura_regiao in range(560, 641):
        _verifica_linha_fora_visivel(estado, altura_regiao)


def _verifica_linha_fora_visivel(estado, altura_regiao):
    rect = QRect(0, 0, 211, altura_regiao)
    chamadas = []
    original = ladder._desenhar_linha_fora

    def espiao(painter, r, e, y, altura, niveis_fora, acima):
        chamadas.append((y, altura))
        return original(painter, r, e, y, altura, niveis_fora, acima)

    ladder._desenhar_linha_fora = espiao
    try:
        pixmap = QPixmap(211, altura_regiao)
        painter = QPainter(pixmap)
        try:
            ladder.desenhar(painter, rect, estado)
        finally:
            painter.end()
    finally:
        ladder._desenhar_linha_fora = original

    assert chamadas, f"nivel fora da escala sem linha propria em altura {altura_regiao}"
    topo_rodape = ladder.retangulo_rotulo(rect).top()
    for y, altura in chamadas:
        assert y + altura <= topo_rodape, (
            f"altura {altura_regiao}: linha de ponta em {y}+{altura} invade o rodape"
        )


def test_rotulo_da_value_area_nao_divide_coordenada_com_o_numero_de_volume(qapp):
    """Critica de 28/08/2026: `VAL`/`VAH` e o numero de volume eram os dois
    alinhados a direita e se destruiam quando a fronteira caia numa linha com
    rotulo numerico (5M, linha 5.164,5). E colisao CONDICIONAL — no 15M as
    bordas calharam em linhas vazias — entao a varredura vai por todas as
    alturas de janela e por VAH e VAL, nao por um caso so."""

    por_tick = _perfil_de_sessao_com_print_aberrante()
    poc = max(por_tick, key=lambda p: por_tick[p][0])
    tick_min, tick_max, _, _ = ladder.faixa_por_volume(por_tick, poc)

    for altura_regiao in range(200, 641, 7):
        rect = QRect(0, 0, 211, altura_regiao)
        topo_corpo = rect.top() + ladder.ALTURA_CABECALHO
        altura_util = ladder.retangulo_rotulo(rect).top() - topo_corpo
        if altura_util < ladder.ALTURA_LINHA_MIN:
            continue
        n_linhas = max(1, altura_util // ladder.ALTURA_LINHA_ALVO)
        altura = max(
            ladder.ALTURA_LINHA_MIN, min(ladder.ALTURA_LINHA_MAX, altura_util // n_linhas)
        )
        linhas, passo = montar_linhas(por_tick, tick_min, tick_max, 10_334, n_linhas)

        largura_preco = max(
            ladder.LARGURA_MIN_LANE_PRECO,
            int(rect.width() * (ladder.FRACAO_LANE_PRECO_AGRUPADO if passo > 1
                                else ladder.FRACAO_LANE_PRECO)),
        )
        x_barra = rect.left() + largura_preco
        largura_barra = rect.width() - largura_preco - 2

        # VAL e VAH varridos por TODOS os ticks da escala, para pegar tambem a
        # fronteira que cai exatamente numa linha com numero.
        for limite in range(tick_min, tick_max + 1):
            for nome_val, nome_vah in ((limite, None), (None, limite)):
                fronteiras = ladder.fronteiras_va(
                    linhas, nome_val, nome_vah, topo_corpo, altura, passo
                )
                for _, y_limite, no_topo in fronteiras:
                    caixa_tag = ladder.retangulo_tag_va(rect, y_limite, no_topo)
                    # Separar as faixas zerando uma delas nao e separar: cada
                    # uma tem de continuar cabendo o proprio texto.
                    assert caixa_tag.width() >= 18, (
                        f"lane do VA com {caixa_tag.width()}px nao cabe 'VAH'"
                    )
                    for indice in range(len(linhas)):
                        y = topo_corpo + indice * altura
                        caixa_num = ladder.retangulo_numero_volume(
                            x_barra, largura_barra, y, altura
                        )
                        assert caixa_num.width() >= 20, (
                            f"faixa do numero de volume com {caixa_num.width()}px"
                        )
                        assert not caixa_tag.intersects(caixa_num), (
                            f"altura {altura_regiao}, limite {limite}: "
                            f"tag VA {caixa_tag} colide com numero {caixa_num}"
                        )
