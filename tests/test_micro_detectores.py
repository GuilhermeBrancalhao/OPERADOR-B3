from __future__ import annotations

from fluxopro.core.eventos import AgressorSide, Side, Trade
from fluxopro.microestrutura.detectores import (
    ConfigAbsorcao,
    ConfigClipInstitucional,
    ConfigEscora,
    ConfigExaustao,
    ConfigIceberg,
    ConfigLiquidezFantasma,
    DetectorAbsorcao,
    DetectorClipInstitucional,
    DetectorEscora,
    DetectorExaustao,
    DetectorIcebergPorRecarga,
    DetectorLiquidezFantasma,
    JANELA_EPISODIO_NS,
    LIMITE_CHAVES_RASTREADAS,
    TipoDeteccao,
    _MapaProcedencia,
)
from fluxopro.microestrutura.eventos_mbo import (
    CONFIANCA_OBSERVADO,
    FonteMicro,
    OrdemEvento,
    TipoEventoOrdem,
)
from fluxopro.microestrutura.livro_mbo import ConfigLivroMBO, LivroMBO


def _trade(ts, price, qty, agressor, symbol="WDOV26"):
    return Trade(
        timestamp_ns=ts, symbol=symbol, price=price, qty=qty,
        side_agressor=agressor, trade_id=f"t{ts}",
    )


# ---------------------------------------------------------------------------
# Absorção
# ---------------------------------------------------------------------------


def test_absorcao_detectada_venda_dominante_sem_preco_cair():
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=0))
    saidas = [det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL)) for i in range(5)]
    disparos = [d for d in saidas if d is not None]
    assert len(disparos) == 1  # um alerta por EPISÓDIO, não um por trade
    resultado = disparos[0]
    assert resultado.tipo is TipoDeteccao.ABSORCAO
    assert resultado.side is Side.BUY  # comprador absorvendo a venda
    assert resultado.confianca == 1.0


def test_absorcao_dispara_no_limiar_exato_de_volume():
    """Fronteira `>=`: 4 x 50 = exatamente `volume_minimo`, tem que disparar.

    Prende a mutação `>=` -> `>` no `volume_minimo` (M28 da crítica R1): com
    `>` o 4º trade devolveria None e nenhum outro trade sobraria para disparar.
    """
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=0))
    saidas = [det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL)) for i in range(4)]
    assert [s is None for s in saidas] == [True, True, True, False]
    assert saidas[3].evidencia["volume_agressao_dominante"] == 200  # no limiar, não acima


def test_absorcao_nao_dispara_um_lote_abaixo_do_limiar():
    """Espelho do teste acima: 200 contra `volume_minimo=201` não pode disparar."""
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=201, deslocamento_maximo_ticks=0))
    saidas = [det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL)) for i in range(4)]
    assert all(s is None for s in saidas)


def test_absorcao_nao_dispara_se_preco_desloca():
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=0))
    resultado = None
    for i in range(5):
        resultado = det.ao_trade(_trade(i * 1000, 5000 + i, 50, AgressorSide.SELL))
    assert resultado is None  # preço se moveu — não é absorção, é continuação


def test_absorcao_nao_dispara_abaixo_do_volume_minimo():
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=1000, deslocamento_maximo_ticks=0))
    resultado = det.ao_trade(_trade(0, 5000, 50, AgressorSide.SELL))
    assert resultado is None


def test_absorcao_nao_reemite_enquanto_o_episodio_dura():
    """Sem dedup o detector re-emite a cada trade (R1 mediu 98,2% do tape)."""
    cfg = ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=0, janela_ns=10_000_000_000)
    det = DetectorAbsorcao("WDOV26", cfg)
    disparos = [
        d
        for i in range(50)
        if (d := det.ao_trade(_trade(i * 1_000_000, 5000, 50, AgressorSide.SELL))) is not None
    ]
    assert len(disparos) == 1


def test_absorcao_rearma_quando_o_preco_desloca():
    """Gatilho 1 de rearme: o deslocamento quebra a condição e encerra o episódio."""
    cfg = ConfigAbsorcao(volume_minimo=100, deslocamento_maximo_ticks=0, janela_ns=3_000)
    det = DetectorAbsorcao("WDOV26", cfg)
    assert det.ao_trade(_trade(0, 5000, 50, AgressorSide.SELL)) is None
    assert det.ao_trade(_trade(1_000, 5000, 50, AgressorSide.SELL)) is not None  # episódio 1
    assert det.ao_trade(_trade(2_000, 5000, 50, AgressorSide.SELL)) is None  # dedup
    # preço desloca (faixa 5000..5001 > 0 tick): episódio 1 encerra e rearma
    assert det.ao_trade(_trade(3_000, 5001, 50, AgressorSide.SELL)) is None
    # janela já só tem trades de 5001 -> novo episódio pode ser alertado
    segundo = det.ao_trade(_trade(6_000, 5001, 50, AgressorSide.SELL))
    assert segundo is not None and segundo.price == 5001  # episódio 2
    assert det.ao_trade(_trade(7_000, 5001, 50, AgressorSide.SELL)) is None  # dedup de novo


def test_absorcao_rearma_quando_a_ancora_sai_da_faixa_com_janela_cheia():
    """Gatilho 2: a âncora sai da faixa SEM a janela esvaziar em nenhum momento."""
    cfg = ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=1, janela_ns=10_000)
    det = DetectorAbsorcao("WDOV26", cfg)
    for ts in (0, 1_000, 2_000):
        assert det.ao_trade(_trade(ts, 5000, 50, AgressorSide.SELL)) is None
    primeiro = det.ao_trade(_trade(3_000, 5000, 50, AgressorSide.SELL))
    assert primeiro is not None and primeiro.price == 5000

    # faixa ainda contém a âncora 5000 -> mesmo episódio, silêncio
    assert det.ao_trade(_trade(11_000, 5001, 50, AgressorSide.SELL)) is None
    assert det.ao_trade(_trade(12_000, 5001, 50, AgressorSide.SELL)) is None
    # os trades de 5000 expiraram; a janela continua com 3 trades (nunca esvaziou)
    assert det.ao_trade(_trade(14_000, 5001, 50, AgressorSide.SELL)) is None  # volume caiu
    assert len(det._janela) == 3
    segundo = det.ao_trade(_trade(15_000, 5001, 50, AgressorSide.SELL))
    assert segundo is not None and segundo.price == 5001  # episódio novo no preço novo


def test_absorcao_rearma_quando_a_janela_esvazia():
    """Gatilho 3: buraco no tape maior que a janela encerra o episódio."""
    cfg = ConfigAbsorcao(volume_minimo=100, deslocamento_maximo_ticks=0, janela_ns=5_000)
    det = DetectorAbsorcao("WDOV26", cfg)
    det.ao_trade(_trade(0, 5000, 50, AgressorSide.SELL))
    assert det.ao_trade(_trade(1_000, 5000, 50, AgressorSide.SELL)) is not None
    # 1 minuto de silêncio: a janela esvazia
    det.ao_trade(_trade(60_000_000_000, 5000, 50, AgressorSide.SELL))
    assert len(det._janela) == 1
    assert det.ao_trade(_trade(60_000_001_000, 5000, 50, AgressorSide.SELL)) is not None


def test_absorcao_janela_expira_por_tempo():
    cfg = ConfigAbsorcao(volume_minimo=1_000_000, deslocamento_maximo_ticks=0, janela_ns=1_200)
    det = DetectorAbsorcao("WDOV26", cfg)
    det.ao_trade(_trade(0, 5000, 50, AgressorSide.SELL))
    det.ao_trade(_trade(500, 5000, 30, AgressorSide.BUY))
    assert (det._volume_sell, det._volume_buy) == (50, 30)
    det.ao_trade(_trade(1_600, 5000, 10, AgressorSide.BUY))  # limite=400: expira só ts=0
    assert (det._volume_sell, det._volume_buy) == (0, 40)
    assert len(det._janela) == 2


def _absorcao_ingenua(cfg: ConfigAbsorcao, tape: list) -> list[tuple[int, int, int, int]]:
    """Referência O(n) por trade — a implementação que a janela deslizante substituiu."""
    janela: list = []
    saidas = []
    for t in tape:
        janela.append(t)
        limite = t.timestamp_ns - cfg.janela_ns
        janela = [x for x in janela if x.timestamp_ns >= limite]
        precos = [x.price for x in janela]
        saidas.append((
            len(janela),
            max(precos) - min(precos),
            sum(x.qty for x in janela if x.side_agressor is AgressorSide.BUY),
            sum(x.qty for x in janela if x.side_agressor is AgressorSide.SELL),
        ))
    return saidas


def test_absorcao_janela_deslizante_bate_com_a_referencia_ingenua():
    """Caixa-branca: max/min monotônicos e contadores incrementais têm que dar
    exatamente o mesmo que varrer a janela inteira, trade a trade."""
    import random

    rng = random.Random(20260821)
    cfg = ConfigAbsorcao(volume_minimo=10**9, deslocamento_maximo_ticks=10**9, janela_ns=50_000)
    tape = []
    ts = 0
    for i in range(400):
        ts += rng.randint(1, 20_000)
        tape.append(_trade(
            ts,
            5000 + rng.randint(0, 4),
            rng.randint(1, 9),
            rng.choice([AgressorSide.BUY, AgressorSide.SELL, AgressorSide.UNKNOWN]),
        ))

    esperado = _absorcao_ingenua(cfg, tape)
    det = DetectorAbsorcao("WDOV26", cfg)
    for trade, (n, desloc, vb, vs) in zip(tape, esperado):
        det.ao_trade(trade)
        obtido = (
            len(det._janela),
            det._max_precos[0][1] - det._min_precos[0][1],
            det._volume_buy,
            det._volume_sell,
        )
        assert obtido == (n, desloc, vb, vs), f"divergiu em ts={trade.timestamp_ns}"
        # memória limitada: as deques monotônicas nunca passam do tamanho da janela
        assert len(det._max_precos) <= len(det._janela)
        assert len(det._min_precos) <= len(det._janela)


# ---------------------------------------------------------------------------
# Escora
# ---------------------------------------------------------------------------


def test_escora_dispara_apos_n_reposicoes():
    livro = LivroMBO("WDOV26", ConfigLivroMBO(janela_reposicao_ns=10_000_000_000))
    det = DetectorEscora(ConfigEscora(n_reposicoes_minimo=3))
    ts = 0
    resultado = None
    for i in range(4):
        oid = f"o{i}"
        livro.adicionar(oid, Side.BUY, 5000, 100, ts)
        livro.executar(Side.BUY, 5000, 100, ts + 1)
        ts += 2_000_000_000
        resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.ESCORA
    assert resultado.evidencia["n_reposicoes"] >= 3


def test_escora_nao_dispara_com_poucas_reposicoes():
    livro = LivroMBO("WDOV26")
    det = DetectorEscora(ConfigEscora(n_reposicoes_minimo=5))
    livro.adicionar("o1", Side.BUY, 5000, 100, 0)
    resultado = det.verificar(livro, Side.BUY, 5000, 0)
    assert resultado is None


# ---------------------------------------------------------------------------
# Iceberg (via recarga observada — feed MBO real)
# ---------------------------------------------------------------------------


def test_iceberg_por_recarga_detecta_execucao_muito_maior_que_exibido():
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(ConfigIceberg(razao_minima=3.0, volume_executado_minimo=200))
    # ordem exibe 50, mas nunca zera: cada execucao consome 30 (sobram 20 ativos)
    # e a recarga repoe pra 50 antes da proxima rodada — simula o iceberg que
    # so mostra uma fatia pequena por vez, sem nunca esgotar o order_id.
    livro.adicionar("iceberg1", Side.SELL, 5000, 50, 0, fonte=FonteMicro.MBO)
    ts = 1_000_000_000
    resultado = None
    for _ in range(8):
        livro.executar(Side.SELL, 5000, 30, ts)
        livro.recarregar("iceberg1", 30, ts, fonte=FonteMicro.MBO)
        ordem = livro.ordem("iceberg1")
        # o detector dedupe por order_id (dispara uma vez); guarda o primeiro
        # disparo em vez de sobrescrever com o `None` das chamadas seguintes.
        resultado = resultado or det.verificar(ordem, "WDOV26", ts)
        ts += 500_000_000
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.ICEBERG
    assert resultado.confianca == 1.0
    assert resultado.evidencia["n_recargas"] >= 5


def test_iceberg_nao_dispara_sem_recarga_mesmo_com_volume_alto():
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(ConfigIceberg(razao_minima=3.0, volume_executado_minimo=50))
    livro.adicionar("o1", Side.SELL, 5000, 500, 0)
    livro.executar(Side.SELL, 5000, 500, 1)
    ordem = livro.ordem("o1")
    # ordem zerou (nao esta mais em self._ordens ativa, mas objeto ainda tem os dados)
    resultado = det.verificar(ordem, "WDOV26", 1)
    assert resultado is None  # n_recargas == 0 — não é iceberg, é ordem grande única


def _ordem_com_razao_alta_e_zero_recargas(livro: LivroMBO):
    """Monta, pelo caminho público do livro, uma ordem com razão
    executado/exibido acima do limiar e NENHUMA recarga observada.

    É alcançável: `modificar` para cima recria a `Ordem` com `qty_original`
    novo (150) preservando `qty_executada` herdado (500) — razão 3,33 — sem
    tocar em `n_recargas`. Sem esse cenário o teste de "não dispara sem
    recarga" fica redundante, porque o filtro de razão barra antes.
    """
    livro.adicionar("o1", Side.SELL, 5000, 600, 0)
    livro.executar(Side.SELL, 5000, 500, 1)
    livro.modificar("o1", 150, 2)
    ordem = livro.ordem("o1")
    assert ordem.qty_executada / ordem.qty_original >= 3.0 and ordem.n_recargas == 0
    return ordem


def test_iceberg_por_recarga_exige_recarga_mesmo_com_razao_acima_do_limiar():
    """Prende a mutação que remove `n_recargas == 0` da guarda (M30 da R1).

    A recarga observada é a ÚNICA coisa que separa este detector do proxy que
    foi deletado; sem ela, razão alta é só contabilidade de uma ordem que foi
    aumentada depois de executar, não iceberg.
    """
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(ConfigIceberg(razao_minima=3.0, volume_executado_minimo=200))
    ordem = _ordem_com_razao_alta_e_zero_recargas(livro)
    assert det.verificar(ordem, "WDOV26", 3) is None


def test_iceberg_por_recarga_dispara_no_mesmo_cenario_com_uma_recarga():
    """Espelho do teste acima: só a recarga muda, e ela vira o resultado."""
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(ConfigIceberg(razao_minima=3.0, volume_executado_minimo=200))
    ordem = _ordem_com_razao_alta_e_zero_recargas(livro)
    livro.recarregar("o1", 10, 3)
    resultado = det.verificar(livro.ordem("o1"), "WDOV26", 3)
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.ICEBERG
    assert resultado.confianca == 1.0  # feed MBO real: observado, não hipótese
    assert resultado.evidencia["n_recargas"] == 1


def test_detector_iceberg_por_proxy_de_nivel_foi_deletado():
    """O proxy `n_reposicoes * exibido_max / exibido_max` (== n_reposicoes) foi
    removido: media `n_reposicoes` com nome de volume executado e duplicava o
    gatilho do `DetectorEscora`. Este teste impede que ele volte por descuido."""
    import fluxopro.microestrutura.detectores as mod

    assert not hasattr(mod, "DetectorIceberg")


# ---------------------------------------------------------------------------
# Liquidez fantasma
# ---------------------------------------------------------------------------


def test_liquidez_fantasma_detecta_retirada_rapida_perto_do_preco():
    livro = LivroMBO("WDOV26")
    det = DetectorLiquidezFantasma(
        grid_tick_size=0.5, config=ConfigLiquidezFantasma(qty_minima=100, vida_maxima_ns=2_000_000_000, ticks_proximidade=5)
    )
    livro.adicionar("fantasma1", Side.SELL, 5010, 500, 0)
    livro.cancelar("fantasma1", 500_000_000)
    ordem = livro.ordem("fantasma1")
    resultado = det.verificar(ordem, "WDOV26", melhor_preco_oposto=5008)
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.LIQUIDEZ_FANTASMA


def test_liquidez_fantasma_nao_dispara_se_executou_algo():
    livro = LivroMBO("WDOV26")
    det = DetectorLiquidezFantasma(0.5, ConfigLiquidezFantasma(qty_minima=100))
    livro.adicionar("o1", Side.SELL, 5010, 500, 0)
    livro.executar(Side.SELL, 5010, 100, 100)
    livro.cancelar("o1", 500_000_000)
    ordem = livro.ordem("o1")
    resultado = det.verificar(ordem, "WDOV26", 5008)
    assert resultado is None  # executou parte — não é o fenômeno


def test_liquidez_fantasma_nao_dispara_longe_do_preco():
    livro = LivroMBO("WDOV26")
    det = DetectorLiquidezFantasma(0.5, ConfigLiquidezFantasma(qty_minima=100, ticks_proximidade=1))
    livro.adicionar("o1", Side.SELL, 5100, 500, 0)
    livro.cancelar("o1", 500_000_000)
    ordem = livro.ordem("o1")
    resultado = det.verificar(ordem, "WDOV26", melhor_preco_oposto=5008)
    assert resultado is None  # 92 ticks de distância — irrelevante ao mercado atual


# ---------------------------------------------------------------------------
# Exaustão
# ---------------------------------------------------------------------------


def test_exaustao_detecta_volume_decrescente_sem_progresso():
    det = DetectorExaustao("WDOV26", ConfigExaustao(n_trades_janela=6, queda_volume_minima=0.4))
    volumes = [100, 90, 80, 30, 20, 15]  # decrescente, terço inicial vs final: (270 vs 65)
    resultado = None
    for i, v in enumerate(volumes):
        resultado = det.ao_trade(_trade(i * 1000, 5000, v, AgressorSide.BUY))
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.EXAUSTAO
    assert resultado.evidencia["preco_moveu"] is False


def test_exaustao_nao_dispara_se_preco_progride():
    det = DetectorExaustao("WDOV26", ConfigExaustao(n_trades_janela=4, queda_volume_minima=0.3))
    volumes = [100, 60, 40, 20]
    resultado = None
    for i, v in enumerate(volumes):
        resultado = det.ao_trade(_trade(i * 1000, 5000 + i, v, AgressorSide.BUY))
    assert resultado is None  # preço avançou junto — é continuação, não exaustão


def test_exaustao_nao_dispara_com_lado_misto():
    det = DetectorExaustao("WDOV26", ConfigExaustao(n_trades_janela=3, queda_volume_minima=0.1))
    det.ao_trade(_trade(0, 5000, 100, AgressorSide.BUY))
    det.ao_trade(_trade(1, 5000, 50, AgressorSide.SELL))
    resultado = det.ao_trade(_trade(2, 5000, 10, AgressorSide.BUY))
    assert resultado is None


# ---------------------------------------------------------------------------
# Clip institucional
# ---------------------------------------------------------------------------


def test_clip_institucional_detecta_regularidade():
    det = DetectorClipInstitucional("WDOV26", ConfigClipInstitucional(n_trades_minimo=5, cv_qty_maximo=0.1, cv_intervalo_maximo=0.1))
    resultado = None
    ts = 0
    for _ in range(5):
        resultado = det.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))  # qty e intervalo fixos
        ts += 1_000_000_000
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.CLIP_INSTITUCIONAL
    assert resultado.evidencia["cv_quantidade"] == 0.0


def test_clip_institucional_nao_dispara_com_tamanhos_irregulares():
    det = DetectorClipInstitucional("WDOV26", ConfigClipInstitucional(n_trades_minimo=5, cv_qty_maximo=0.05))
    resultado = None
    qtys = [10, 500, 20, 900, 5]
    ts = 0
    for q in qtys:
        resultado = det.ao_trade(_trade(ts, 5000, q, AgressorSide.BUY))
        ts += 1_000_000_000
    assert resultado is None


# ===========================================================================
# RETENÇÃO — todo estado retido tem teto
#
# Números medidos na versão ANTERIOR (commit b3e5bc6), com o mesmo roteiro:
#
#   detector                     estrutura                  entraram   retidos
#   DetectorExaustao             trades retidos              200.000   200.000
#   DetectorAbsorcao             trades na janela (5s)       200.000    25.001
#   DetectorClipInstitucional    trades retidos              200.000         5
#   DetectorEscora               chaves de nível              50.000    50.000
#   DetectorIcebergPorRecarga    order_id                     50.000    50.000
#   DetectorLiquidezFantasma     order_id                     50.000  (sem estado)
#
# Os três com retenção == entrada são o vazamento que estes testes prendem.
# ===========================================================================

N_TAPE_LONGO = 200_000
"""O mesmo N da medição da crítica R3. Grande o bastante para que qualquer
estrutura sem poda apareça, pequeno o bastante para rodar em ~1 s."""


def _tape_longo(n=N_TAPE_LONGO, seed=7):
    import random

    rnd = random.Random(seed)
    ts = 0
    for i in range(n):
        ts += 200_000  # 5.000 trades/s — a taxa da barra do projeto
        yield Trade(
            timestamp_ns=ts,
            symbol="WDOV26",
            price=5000 + rnd.randint(-2, 2),
            qty=rnd.randint(1, 20),
            side_agressor=AgressorSide.BUY if rnd.random() < 0.5 else AgressorSide.SELL,
            trade_id=f"t{i}",
        )


def test_exaustao_retem_apenas_a_janela_com_200k_trades():
    """O defeito #1 dos cinco: 200.000 entravam, 200.000 ficavam.

    A janela é `deque(maxlen=n_trades_janela)`; o teto é o da CONFIG, não uma
    constante. Por isso o teste roda com um `n_trades_janela` diferente do
    default: com maxlen fixo em 5 ele passaria por acidente.
    """
    det = DetectorExaustao("WDOV26", ConfigExaustao(n_trades_janela=9))
    for trade in _tape_longo():
        det.ao_trade(trade)
    assert det.n_trades_retidos == 9
    assert det._trades.maxlen == 9


def test_clip_institucional_retem_apenas_a_janela_com_200k_trades():
    """O detector que já fazia certo — e que era o modelo 60 linhas abaixo."""
    det = DetectorClipInstitucional("WDOV26", ConfigClipInstitucional(n_trades_minimo=7))
    for trade in _tape_longo():
        det.ao_trade(trade)
    assert det.n_trades_retidos == 7
    assert det._trades.maxlen == 7


def test_absorcao_retencao_limitada_pela_janela_de_tempo():
    """A retenção da absorção é por TEMPO — o teto é `janela_ns` × taxa do tape.

    Nome citado pela docstring de `DetectorAbsorcao`; existia como promessa e
    não como teste. O tape tem 200.000 trades a 5.000/s; com janela de 1 s o
    teto é ~5.000 e não pode encostar em 200.000.
    """
    det = DetectorAbsorcao(
        "WDOV26", ConfigAbsorcao(volume_minimo=10**9, janela_ns=1_000_000_000)
    )
    for trade in _tape_longo():
        det.ao_trade(trade)
    # 1 s / 200 µs = 5.000 trades + o que acabou de entrar
    assert det.n_trades_retidos <= 5_001
    assert det.n_trades_retidos * 20 < N_TAPE_LONGO, "a janela cresceu com o tape"
    # as deques monotônicas seguem a janela; não são uma terceira cópia do tape
    assert len(det._max_precos) <= det.n_trades_retidos
    assert len(det._min_precos) <= det.n_trades_retidos


def test_absorcao_janela_cresce_com_timestamp_congelado():
    """O LIMITE conhecido, testado como limite — não como se não existisse.

    Um feed defeituoso repetindo o mesmo `time_msc` nunca expira nada, e a
    janela por tempo passa a crescer com a contagem de trades. A docstring de
    `DetectorAbsorcao` registra isso em `PENDENTE(retenção)`; este teste é o
    que impede a pendência de virar folclore — se alguém implementar um teto
    duro por contagem, este teste falha e obriga a atualizar a docstring
    junto.
    """
    det = DetectorAbsorcao("WDOV26", ConfigAbsorcao(volume_minimo=10**9))
    n = 20_000
    for _ in range(n):
        det.ao_trade(_trade(0, 5000, 1, AgressorSide.BUY))  # timestamp CONGELADO
    assert det.n_trades_retidos == n, (
        "se isto mudou, o detector ganhou teto por contagem: atualize a "
        "docstring PENDENTE(retencao) de DetectorAbsorcao"
    )


def _ev(
    order_id="o1",
    side=Side.BUY,
    price=5000,
    confianca=CONFIANCA_OBSERVADO,
    fonte=FonteMicro.MBO,
    tipo=TipoEventoOrdem.NEW,
    ts=0,
):
    return OrdemEvento(
        timestamp_ns=ts,
        symbol="WDOV26",
        tipo=tipo,
        side=side,
        price=price,
        qty=10,
        order_id=order_id,
        fonte=fonte,
        confianca=confianca,
    )


def _escora_no_limiar(n_reposicoes_minimo=3, **cfg):
    """Livro com o nível (BUY, 5000) já acima do limiar de reposições."""
    livro = LivroMBO("WDOV26", ConfigLivroMBO(janela_reposicao_ns=10_000_000_000))
    det = DetectorEscora(ConfigEscora(n_reposicoes_minimo=n_reposicoes_minimo, **cfg))
    ts = 0
    for i in range(n_reposicoes_minimo + 1):
        livro.adicionar(f"o{i}", Side.BUY, 5000, 100, ts)
        livro.executar(Side.BUY, 5000, 100, ts + 1)
        ts += 2_000_000_000
    return livro, det, ts


def test_escora_retem_no_maximo_o_teto_de_niveis():
    """O `set` de `_ja_sinalizado` crescia um item por nível, para sempre.

    50.000 níveis distintos entram na cadeia; o mapa fica no teto.
    """
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=4096))
    for p in range(50_000):
        det.observar(_ev(price=p, fonte=FonteMicro.MBP_INFERIDO, confianca=0.6))
    assert det.n_chaves_rastreadas == 4096


def test_iceberg_retem_no_maximo_o_teto_de_niveis():
    """50.000 níveis distintos entram; o mapa fica no teto.

    Os `order_id` variam junto de propósito: se a chave voltar a ser o
    `order_id`, o teste continua passando aqui — quem pega essa regressão é
    `test_dois_order_id_no_mesmo_nivel_sao_o_mesmo_episodio_no_iceberg`. Este
    aqui prende só a RETENÇÃO, que é o defeito da onda 7 que não pode voltar.
    """
    det = DetectorIcebergPorRecarga(ConfigIceberg(max_ordens_rastreadas=1024))
    for i in range(50_000):
        det.observar(_ev(order_id=f"ice{i}", price=i, tipo=TipoEventoOrdem.TRADE))
    assert det.n_chaves_rastreadas == 1024


def test_liquidez_fantasma_retem_no_maximo_o_teto_de_niveis():
    det = DetectorLiquidezFantasma(
        0.5, ConfigLiquidezFantasma(max_ordens_rastreadas=1024)
    )
    for i in range(50_000):
        det.observar(_ev(order_id=f"f{i}", price=i, tipo=TipoEventoOrdem.CANCEL))
    assert det.n_chaves_rastreadas == 1024


def test_o_teto_de_fabrica_e_o_do_pacote():
    """Prende o default: sem config, o teto é `LIMITE_CHAVES_RASTREADAS`.

    Sem este teste, uma mutação que troque o default por `10**9` (ou por
    `None`) passa despercebida — os testes acima todos passam config
    explícita.
    """
    det = DetectorEscora()
    for p in range(LIMITE_CHAVES_RASTREADAS * 2):
        det.observar(_ev(price=p))
    assert det.n_chaves_rastreadas == LIMITE_CHAVES_RASTREADAS


# ===========================================================================
# PROPAGAÇÃO DE CONFIANÇA — mínimo da cadeia
# ===========================================================================


def test_escora_sobre_livro_inferido_nunca_sai_com_confianca_1():
    """O defeito #2 dos cinco, no caminho de produção (`acompanhar`).

    Livro inteiramente alimentado por eventos `MBP_INFERIDO` — que é o que
    MT5/simulador produzem. Uma detecção ali é hipótese sobre hipótese.
    """
    livro = LivroMBO("WDOV26", ConfigLivroMBO(janela_reposicao_ns=10_000_000_000))
    det = DetectorEscora(ConfigEscora(n_reposicoes_minimo=3))
    det.acompanhar(livro)  # a fiação recomendada — uma linha

    ts = 0
    for i in range(4):
        livro.adicionar(
            f"o{i}", Side.BUY, 5000, 100, ts,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.72,
        )
        livro.executar(
            Side.BUY, 5000, 100, ts + 1,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.55,
        )
        ts += 2_000_000_000

    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == 0.55, "saiu o mínimo da cadeia, não o último"
    assert resultado.confianca < CONFIANCA_OBSERVADO
    assert resultado.evidencia["procedencia"] == "INFERIDA"
    assert resultado.evidencia["fonte"] == FonteMicro.MBP_INFERIDO.value
    assert resultado.evidencia["n_eventos_procedencia"] >= 8


def test_propagacao_usa_o_minimo_e_nao_produto_nem_media():
    """A política, isolada dos três candidatos que ela recusa.

    Três eventos inferidos a 0,60:
      * produto -> 0,216 (pessimismo fabricado: os eventos não são
        independentes, saem todos do mesmo `InferidorMBP`);
      * média   -> 0,60 aqui, mas mascararia um elo fraco no caso misto
        (ver o teste seguinte);
      * mínimo  -> 0,60.
    """
    livro, det, ts = _escora_no_limiar()
    for _ in range(3):
        det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.60))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == 0.60
    assert resultado.confianca != 0.216


def test_um_elo_fraco_nao_e_mascarado_pelos_fortes():
    """Quatro observados (1,0) e um inferido a 0,30 dariam 0,86 na média.

    A detecção inteira depende do elo de 0,30 — a escora só existe se CADA
    reposição aconteceu. O mínimo é a cota superior correta de uma conjunção.
    """
    livro, det, ts = _escora_no_limiar()
    for _ in range(4):
        det.observar(_ev(price=5000))
    det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.30))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == 0.30
    assert resultado.evidencia["procedencia"] == "INFERIDA"


def test_propagacao_e_idempotente():
    """t-norm de Gödel: ver o mesmo fato inferido N vezes não o torna mais certo.

    Contrapositivo do produto: com produto, 10 repetições de 0,80 dariam 0,107.
    """
    livro, det, ts = _escora_no_limiar()
    det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.80))
    uma_vez = det._procedencia.obter((Side.BUY, 5000)).confianca
    for _ in range(9):
        det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.80))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert uma_vez == 0.80
    assert resultado.confianca == uma_vez


def test_propagacao_e_monotona_juntar_observado_nunca_aumenta():
    """Monotonicidade: acrescentar um fato observado nunca SOBE a cadeia.

    É a propriedade que a promessa "nunca apresentar hipótese como fato"
    exige — senão bastaria empilhar eventos observados para "limpar" uma
    inferência ruim.
    """
    livro, det, ts = _escora_no_limiar()
    det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.45))
    for _ in range(20):
        det.observar(_ev(price=5000, confianca=CONFIANCA_OBSERVADO))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == 0.45
    # e a FONTE também é monótona para baixo: um inferido no meio contamina
    assert resultado.evidencia["procedencia"] == "INFERIDA"


def test_a_ordem_de_chegada_nao_muda_o_resultado():
    """Comutatividade — consequência de mínimo + degradação de fonte."""
    confs = [0.9, 0.4, 0.7]
    resultados = []
    for ordem in (confs, list(reversed(confs)), [confs[1], confs[2], confs[0]]):
        livro, det, ts = _escora_no_limiar()
        for c in ordem:
            det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=c))
        resultados.append(det.verificar(livro, Side.BUY, 5000, ts).confianca)
    assert resultados == [0.4, 0.4, 0.4]


def test_cadeia_vazia_declara_desconhecida_em_vez_de_inventar_procedencia():
    """Quem nunca ligou `acompanhar` não deu procedência — e o detector não
    inventa uma. Cai no default do pacote e DECLARA que não há cadeia.

    `fonte` sai `None`, não `"MBO"`: publicar o rótulo de feed observado sobre
    uma cadeia inexistente é o mesmo erro que o `confianca=1.0` fixo era, só
    que escondido no dicionário de auditoria.
    """
    livro, det, ts = _escora_no_limiar()
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == CONFIANCA_OBSERVADO
    assert resultado.evidencia["procedencia"] == "DESCONHECIDA"
    assert resultado.evidencia["n_eventos_procedencia"] == 0
    assert resultado.evidencia["fonte"] is None


def test_cadeia_so_de_observados_declara_observada():
    """O espelho: com feed MBO real, a cadeia existe e diz OBSERVADA."""
    livro, det, ts = _escora_no_limiar()
    for _ in range(3):
        det.observar(_ev(price=5000))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == CONFIANCA_OBSERVADO
    assert resultado.evidencia["procedencia"] == "OBSERVADA"
    assert resultado.evidencia["fonte"] == FonteMicro.MBO.value
    assert resultado.evidencia["n_eventos_procedencia"] == 3


def test_a_cadeia_da_escora_e_por_nivel_nao_global():
    """Chave errada = confiança de outro nível vazando para este."""
    livro, det, ts = _escora_no_limiar()
    det.observar(_ev(price=4999, fonte=FonteMicro.MBP_INFERIDO, confianca=0.10))
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None
    assert resultado.confianca == CONFIANCA_OBSERVADO
    assert resultado.evidencia["procedencia"] == "DESCONHECIDA"


def test_escora_aceita_o_evento_gatilho_pelo_caminho_pull():
    """A outra fiação documentada: `verificar(..., evento=ev)`."""
    livro, det, ts = _escora_no_limiar()
    ev = _ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.62)
    resultado = det.verificar(livro, Side.BUY, 5000, ts, evento=ev)
    assert resultado is not None
    assert resultado.confianca == 0.62
    assert resultado.evidencia["procedencia"] == "INFERIDA"


def _iceberg_pronto(**cfg):
    """Ordem com razão executado/exibido alta e recarga observada."""
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(
        ConfigIceberg(razao_minima=3.0, volume_executado_minimo=200, **cfg)
    )
    livro.adicionar("iceberg1", Side.SELL, 5000, 50, 0)
    ts = 1_000_000_000
    for _ in range(8):
        livro.executar(Side.SELL, 5000, 30, ts)
        livro.recarregar("iceberg1", 30, ts)
        ts += 500_000_000
    return livro, det, ts


def test_iceberg_propaga_a_cadeia_do_nivel():
    """A cadeia junta as recargas e execuções do NÍVEL — que é onde o
    fenômeno mora. Era por `order_id` até a crítica R4 (§A.5)."""
    livro, det, ts = _iceberg_pronto()
    det.observar(
        _ev(order_id="iceberg1", side=Side.SELL, price=5000,
            tipo=TipoEventoOrdem.TRADE,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.5)
    )
    det.observar(
        _ev(order_id="iceberg1", side=Side.SELL, price=5000,
            tipo=TipoEventoOrdem.TRADE, confianca=1.0)
    )
    resultado = det.verificar(livro.ordem("iceberg1"), "WDOV26", ts)
    assert resultado is not None
    assert resultado.confianca == 0.5
    assert resultado.evidencia["procedencia"] == "INFERIDA"
    assert resultado.evidencia["order_id"] == "iceberg1", (
        "o order_id deixou de ser a CHAVE, nao deixou de ser EVIDENCIA"
    )


def test_iceberg_nao_mistura_a_cadeia_de_outro_nivel():
    """Contra-teste da chave: evento de outro nível não empresta confiança."""
    livro, det, ts = _iceberg_pronto()
    det.observar(
        _ev(order_id="outra", side=Side.SELL, price=5001,
            tipo=TipoEventoOrdem.TRADE,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.11)
    )
    resultado = det.verificar(livro.ordem("iceberg1"), "WDOV26", ts)
    assert resultado is not None
    assert resultado.confianca == CONFIANCA_OBSERVADO
    assert resultado.evidencia["procedencia"] == "DESCONHECIDA"


def _fantasma_pronto(**cfg):
    livro = LivroMBO("WDOV26")
    det = DetectorLiquidezFantasma(
        0.5,
        ConfigLiquidezFantasma(
            qty_minima=100, vida_maxima_ns=2_000_000_000, ticks_proximidade=5, **cfg
        ),
    )
    livro.adicionar("fantasma1", Side.SELL, 5010, 500, 0)
    livro.cancelar("fantasma1", 1_000_000_000)
    return livro, det


def test_liquidez_fantasma_propaga_a_cadeia_do_nivel():
    """Em livro inferido, entrada e saída da ordem são as DUAS hipóteses —
    foi cancelamento ou foi execução que não vimos? É essa dúvida que a
    confiança emitida tem de carregar."""
    livro, det = _fantasma_pronto()
    det.observar(
        _ev(order_id="fantasma1", side=Side.SELL, price=5010,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.68)
    )
    det.observar(
        _ev(order_id="fantasma1", side=Side.SELL, price=5010,
            tipo=TipoEventoOrdem.CANCEL,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.55)
    )
    resultado = det.verificar(livro.ordem("fantasma1"), "WDOV26", 5008)
    assert resultado is not None
    assert resultado.confianca == 0.55
    assert resultado.evidencia["procedencia"] == "INFERIDA"


def test_acompanhar_alimenta_a_cadeia_de_ponta_a_ponta():
    """`acompanhar` é a fiação anunciada como recomendada — e tem de bastar
    sozinha, sem o chamador repassar evento nenhum."""
    livro = LivroMBO("WDOV26")
    det = DetectorLiquidezFantasma(
        0.5,
        ConfigLiquidezFantasma(
            qty_minima=100, vida_maxima_ns=2_000_000_000, ticks_proximidade=5
        ),
    )
    det.acompanhar(livro)
    livro.adicionar(
        "fantasma1", Side.SELL, 5010, 500, 0,
        fonte=FonteMicro.MBP_INFERIDO, confianca=0.80,
    )
    livro.cancelar(
        "fantasma1", 1_000_000_000,
        fonte=FonteMicro.MBP_INFERIDO, confianca=0.51,
    )
    resultado = det.verificar(livro.ordem("fantasma1"), "WDOV26", 5008)
    assert resultado is not None
    assert resultado.confianca == 0.51
    assert resultado.evidencia["n_eventos_procedencia"] == 2


def test_liquidez_fantasma_nao_reemite_para_a_mesma_ordem():
    """Uma ordem some UMA vez. O objeto continua acessível pelo livro, então
    sem dedup cada consulta re-emitia o mesmo alerta. (A chave é o nível, e
    isso cobre a mesma ordem com folga — ver os testes de episódio.)"""
    livro, det = _fantasma_pronto()
    ordem = livro.ordem("fantasma1")
    assert det.verificar(ordem, "WDOV26", 5008) is not None
    assert det.verificar(ordem, "WDOV26", 5008) is None
    assert det.verificar(ordem, "WDOV26", 5008) is None


# ===========================================================================
# DEDUP POR EPISÓDIO — Exaustão
# ===========================================================================

CFG_EXAUSTAO = ConfigExaustao(n_trades_janela=5, queda_volume_minima=0.4)
"""terço = 5//3 = 1, então a queda compara o 1º com o 5º trade da janela."""


def _episodio_de_exaustao(det, ts=0, price=5000, lado=AgressorSide.SELL, qtys=None):
    """Alimenta 5 trades no mesmo preço e lado, com o volume caindo no fim."""
    qtys = qtys if qtys is not None else [100, 100, 100, 100, 40]
    saidas = []
    for q in qtys:
        saidas.append(det.ao_trade(_trade(ts, price, q, lado)))
        ts += 1_000_000
    return saidas, ts


def test_exaustao_nao_reemite_no_mesmo_episodio():
    """O defeito #4 dos cinco: disparava 2-3 vezes no mesmo preço em 30 ms."""
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    disparos = [s for s in saidas if s is not None]
    assert len(disparos) == 1
    # o episódio continua: cada trade novo mantém a condição
    for _ in range(3):
        assert det.ao_trade(_trade(ts, 5000, 40, AgressorSide.SELL)) is None
        ts += 1_000_000


def test_exaustao_queda_abaixo_do_limiar_nao_rearma():
    """A fronteira documentada, do lado que NÃO rearma.

    Volume voltando a subir afrouxa a condição, mas não encerra o episódio —
    mesmo critério da absorção. Se afrouxar rearmasse, um tape oscilando em
    volume produziria um alerta a cada oscilação, que é o defeito original com
    outro nome.
    """
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    assert len([s for s in saidas if s is not None]) == 1

    # volume plano: `queda` cai abaixo do limiar, sem trocar lado nem preço
    for _ in range(5):
        assert det.ao_trade(_trade(ts, 5000, 100, AgressorSide.SELL)) is None
        ts += 1_000_000
    # e quando a queda volta, continua sendo o MESMO episódio
    for q in (100, 100, 100, 40):
        resultado = det.ao_trade(_trade(ts, 5000, q, AgressorSide.SELL))
        ts += 1_000_000
        assert resultado is None, "queda abaixo do limiar nao pode ter rearmado"


def test_exaustao_rearma_quando_a_continuidade_de_lado_quebra():
    """Gatilho 1: entrou trade de outro lado — a premissa deixou de existir."""
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    assert len([s for s in saidas if s is not None]) == 1

    det.ao_trade(_trade(ts, 5000, 10, AgressorSide.BUY))  # quebra a continuidade
    ts += 1_000_000
    saidas2, _ = _episodio_de_exaustao(det, ts)
    assert len([s for s in saidas2 if s is not None]) == 1, "nao rearmou"


def test_exaustao_rearma_quando_o_preco_progride_e_volta():
    """Gatilho 2: o preço andou dentro da janela — a condição quebrou.

    O retorno ao MESMO preço-âncora é de propósito: se o rearme do gatilho 2
    for removido, o gatilho 3 (âncora nova) não cobre este caso e o detector
    fica mudo para sempre naquele preço.
    """
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    assert len([s for s in saidas if s is not None]) == 1

    det.ao_trade(_trade(ts, 5001, 10, AgressorSide.SELL))  # preço progrediu
    ts += 1_000_000
    saidas2, _ = _episodio_de_exaustao(det, ts, price=5000)  # volta ao MESMO preço
    assert len([s for s in saidas2 if s is not None]) == 1, "nao rearmou"


def test_exaustao_emite_de_novo_em_ancora_nova():
    """Gatilho 3: exaustão em outro preço é fenômeno novo, não repetição."""
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    primeiro = [s for s in saidas if s is not None][0]
    saidas2, _ = _episodio_de_exaustao(det, ts, price=5002)
    segundo = [s for s in saidas2 if s is not None]
    assert len(segundo) == 1
    assert primeiro.price == 5000 and segundo[0].price == 5002


def test_exaustao_emite_de_novo_em_lado_novo():
    """Mesma âncora de preço, lado invertido: episódio novo."""
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det, lado=AgressorSide.SELL)
    primeiro = [s for s in saidas if s is not None][0]
    saidas2, _ = _episodio_de_exaustao(det, ts, lado=AgressorSide.BUY)
    segundo = [s for s in saidas2 if s is not None]
    assert len(segundo) == 1
    assert primeiro.side is not segundo[0].side


# ===========================================================================
# `_MapaProcedencia`: expiração por TEMPO + teto SORTEADO — o conserto do
# penhasco que a crítica R4 (§A.5) mediu
# ===========================================================================
#
# A onda 7 pôs teto rígido de 4.096 chaves com despejo FIFO. A R4 mediu a
# consequência sob rotação cíclica e ela é um PAREDÃO, não uma degradação:
#
#     4.096 chaves em rotação -> 0,0% de re-emissão indevida
#     5.000 chaves em rotação -> 100,0%
#
# Mais: Iceberg e Fantasma chaveavam por `order_id`, que em modo MBP é
# sintético e nasce a ~65.000/s — 4.096 chaves eram 63 ms de memória contra um
# fenômeno que dura segundos. Os testes abaixo prendem as DUAS respostas: a
# chave virou `(side, price)` nos três detectores, e o teto por contagem virou
# expiração por tempo com sorteio no excedente.


def _taxa_reemissao(n_chaves, limite, voltas=3, janela_ns=JANELA_EPISODIO_NS, passo_ns=1):
    """Rotação estrita em ciclo: a mesma sequência de chaves, `voltas` vezes.

    Devolve `(% de re-emissão INDEVIDA, tamanho final do mapa)`. Indevida =
    revisita DENTRO da janela de episódio que o mapa não reconheceu. Com
    `passo_ns=1` o ciclo inteiro cabe folgadamente na janela, então tudo que
    for esquecido aqui é esquecimento do TETO, não da expiração — é o eixo que
    o penhasco mora.

    A primeira volta é a de aquecimento e não conta: nela toda chave é nova
    por definição.
    """
    mapa = _MapaProcedencia(limite, janela_ns)
    ts = 0
    reemitidas = visitas = 0
    for volta in range(voltas):
        for k in range(n_chaves):
            ts += passo_ns
            conhecida = mapa.obter(k) is not None
            if volta:
                visitas += 1
                if not conhecida:
                    reemitidas += 1
            mapa.de(k, ts)
    return 100.0 * reemitidas / max(1, visitas), len(mapa)


#: Limite DECLARADO de re-emissão indevida na rotação adversarial de 50.000
#: chaves com a configuração de fábrica. É 1% e não 0% de propósito: o número
#: que se promete é um teto de comportamento, não a ausência de mecanismo.
TETO_REEMISSAO_ADVERSARIAL_PCT = 1.0


def test_rotacao_adversarial_de_50000_chaves_fica_no_limite_declarado():
    """O ataque do §A.5, no tamanho que a R4 usou para levar a dedup a 100%.

    50.000 chaves distintas tocadas em ciclo, três voltas. Com o teto de 4.096
    da onda 7 isto media 100,0% de re-emissão indevida — a dedup virava peneira
    inteira. Com a configuração de fábrica atual tem de ficar sob
    `TETO_REEMISSAO_ADVERSARIAL_PCT`.
    """
    taxa, tamanho = _taxa_reemissao(50_000, LIMITE_CHAVES_RASTREADAS)
    assert taxa <= TETO_REEMISSAO_ADVERSARIAL_PCT, f"{taxa:.1f}% de re-emissao indevida"
    assert tamanho <= LIMITE_CHAVES_RASTREADAS


def test_a_curva_de_reemissao_nao_tem_penhasco():
    """De 1.000 a 50.000 chaves, o degrau entre pontos vizinhos é limitado.

    A assinatura do defeito não era a taxa alta — era o SALTO: 0% num ponto e
    100% no ponto seguinte. Um pregão agitado atravessa esse salto sem aviso.
    Aqui a curva é medida no mesmo eixo com um teto PEQUENO (512), para que a
    faixa inteira fique acima do teto e a política de excedente seja de fato
    exercida; com o teto de fábrica os 50.000 nem chegam a pressionar.

    Duas asserções, e as duas importam:

    * nenhum degrau maior que `DEGRAU_MAXIMO_PCT` entre pontos vizinhos — é a
      definição operacional de "não é penhasco";
    * logo acima do teto a dedup ainda FUNCIONA (o FIFO já entregava 100% ali).
    """
    degrau_maximo_pct = 45.0
    limite = 512
    pontos = [400, 512, 560, 640, 768, 1024, 1536, 2048, 4096, 8192, 20_000, 50_000]
    curva = [(n, _taxa_reemissao(n, limite)[0]) for n in pontos]

    for (n_ant, t_ant), (n, t) in zip(curva, curva[1:]):
        assert t - t_ant <= degrau_maximo_pct, (
            f"penhasco entre {n_ant} ({t_ant:.1f}%) e {n} ({t:.1f}%) — "
            f"a curva inteira: {curva}"
        )
    logo_acima = dict(curva)[560]
    assert logo_acima < 40.0, (
        f"logo acima do teto a dedup ja desabou ({logo_acima:.1f}%) — "
        "e esse era exatamente o ponto em que o FIFO entregava 100%"
    )
    assert curva[0][1] == 0.0, "abaixo do teto a dedup tem de ser perfeita"


def test_o_despejo_nao_e_deterministico_na_ordem_das_chaves():
    """A raiz do penhasco: com FIFO a vítima é sempre a PRÓXIMA a ser
    revisitada, então uma varredura cíclica nunca acerta nada.

    O teste não pede uma vítima específica — pede que a varredura cíclica não
    seja aniquilada. Se alguém trocar o sorteio por qualquer critério ligado à
    posição na fila (FIFO, LRU estrito), esta asserção cai junto.
    """
    taxa, _ = _taxa_reemissao(1024, 512)
    assert taxa < 95.0, f"{taxa:.1f}%: a varredura ciclica voltou a ser aniquilada"


def test_chave_parada_alem_da_janela_expira_e_a_reemissao_e_correta():
    """Expiração por TEMPO: a chave que o mercado esqueceu sai, e a
    re-emissão dela não é defeito — é episódio novo."""
    mapa = _MapaProcedencia(limite=1024, janela_episodio_ns=1_000_000_000)
    proc = mapa.de((Side.BUY, 5000), 0)
    proc.sinalizado = True
    assert mapa.obter((Side.BUY, 5000)) is not None

    mapa.de((Side.SELL, 1), 1_000_000_000)  # dentro da janela: ainda viva
    assert mapa.obter((Side.BUY, 5000)) is not None

    mapa.de((Side.SELL, 2), 1_000_000_001)  # um nanossegundo além
    assert mapa.obter((Side.BUY, 5000)) is None, "a chave parada tinha de expirar"
    # e ao voltar, volta ZERADA: cadeia nova, direito de emitir de volta
    proc2 = mapa.de((Side.BUY, 5000), 1_000_000_002)
    assert proc2.sinalizado is False
    assert proc2.n_eventos == 0


def test_episodio_expirado_reinicia_a_entrada_no_lugar():
    """Expirar não é despejar: a entrada continua no mapa, zerada.

    Este teste existe porque o irmão dele (`..._expira_e_a_reemissao_e_correta`)
    NÃO exercita `_Procedencia.reiniciar` — lá a varredura já tinha tirado a
    chave, e o que voltava era uma entrada nova. A auto-mutação mostrou isso:
    "`reiniciar` não solta o `sinalizado`" sobrevivia à suíte inteira. Aqui a
    chave é realimentada sem nenhuma inserção no meio, então nenhuma varredura
    roda e o caminho testado é o de reinício no lugar.

    As quatro grandezas são verificadas uma a uma de propósito: um episódio
    novo que herdasse a mordaça ficaria MUDO, e um que herdasse a cadeia
    publicaria como evidência deste episódio eventos do anterior.
    """
    mapa = _MapaProcedencia(limite=16, janela_episodio_ns=1_000)
    proc = mapa.somar("a", 0.42, FonteMicro.MBP_INFERIDO, 0)
    proc.sinalizado = True

    proc2 = mapa.de("a", 5_000)  # mesma chave, muito além da janela
    assert proc2 is proc, "era para reiniciar no lugar, não trocar a entrada"
    assert proc2.sinalizado is False, "o episódio novo herdou a mordaça do antigo"
    assert proc2.n_eventos == 0, "a cadeia do episódio anterior vazou para o novo"
    assert proc2.confianca == CONFIANCA_OBSERVADO
    assert proc2.fonte is FonteMicro.MBO


def test_a_fronteira_da_janela_e_estrita():
    """Exatamente `janela_episodio_ns` parado ainda está DENTRO do episódio.

    Fronteira `>` e não `>=`: sem isto o limiar configurado significa uma
    coisa na config e outra no código, e a diferença aparece justamente no
    caso de borda que ninguém repara.

    A fronteira é verificada nos DOIS caminhos, porque ela está escrita duas
    vezes: em `_expirado` (leitura) e inline em `de` (escrita, onde decide se
    a cadeia é reiniciada). A auto-mutação provou que são independentes —
    trocar só a de escrita por `>=` sobrevivia à leitura testada.
    """
    mapa = _MapaProcedencia(limite=16, janela_episodio_ns=1_000)
    mapa.de("a", 0)
    mapa.avancar(1_000)
    assert mapa.obter("a") is not None, "no limiar exato a chave ainda vive"
    mapa.avancar(1_001)
    assert mapa.obter("a") is None

    # caminho de ESCRITA: no limiar exato a cadeia NÃO pode ser reiniciada
    mapa2 = _MapaProcedencia(limite=16, janela_episodio_ns=1_000)
    mapa2.somar("a", 0.4, FonteMicro.MBP_INFERIDO, 0)
    proc = mapa2.somar("a", 1.0, FonteMicro.MBO, 1_000)
    assert proc.n_eventos == 2, "no limiar exato a cadeia foi reiniciada cedo demais"
    assert proc.confianca == 0.4
    proc2 = mapa2.somar("a", 1.0, FonteMicro.MBO, 2_001)  # um ns além
    assert proc2.n_eventos == 1, "passada a janela, a cadeia tem de recomecar"


def test_chave_realimentada_atravessa_a_janela():
    """O outro lado do mesmo contrato: quem é tocado não expira nunca.

    É o caso que o penhasco quebrava — a chave de um episódio VIVO tem de
    sobreviver a qualquer volume de chaves novas passando ao lado.
    """
    janela = 1_000_000_000
    mapa = _MapaProcedencia(limite=1024, janela_episodio_ns=janela)
    ts = 0
    for i in range(50):
        ts += janela // 2
        mapa.de((Side.BUY, 5000), ts)  # o mercado mexe no nível
        mapa.de((Side.SELL, i), ts)  # e cinquenta chaves novas passam
    assert mapa.obter((Side.BUY, 5000)) is not None
    assert mapa.obter((Side.SELL, 0)) is None, "a chave fria tinha de ter saido"


def test_consulta_nao_renova_a_chave():
    """`obter`/`esta_sinalizado` LEEM sem renovar o relógio da chave.

    O que mantém uma chave viva é o mercado mexer nela, não o detector
    perguntar por ela — se a consulta renovasse, um `verificar` em laço sobre
    um nível morto o seguraria vivo indefinidamente e a janela deixaria de
    refletir o que ainda está acontecendo.
    """
    janela = 1_000_000_000
    det = DetectorEscora(ConfigEscora(janela_episodio_ns=janela))
    det.observar(_ev(price=1, ts=0))
    for _ in range(50):
        det.esta_sinalizado((Side.BUY, 1))  # consulta em laço, não renova
    det.observar(_ev(price=2, ts=janela + 1))
    assert det._procedencia.obter((Side.BUY, 1)) is None


def test_o_relogio_do_mapa_nao_anda_para_tras():
    """Feed que reordena ou remenda gap entrega evento com timestamp ATRASADO.

    Se o relógio da dedup andasse para trás, episódios já encerrados
    ressuscitariam e o mapa voltaria a barrar alertas legítimos.
    """
    mapa = _MapaProcedencia(limite=16, janela_episodio_ns=1_000)
    mapa.de("a", 10_000)
    mapa.de("b", 5_000)  # evento atrasado
    assert mapa.agora_ns == 10_000


def test_a_varredura_incremental_encolhe_o_mapa_quando_o_mercado_esfria():
    """Retenção: expirada não é só "lida como ausente", ela SAI da memória.

    Sem a varredura o mapa ficaria cheio de cadáveres até o teto — correto na
    semântica e vazamento na prática, que é a forma exata do defeito que esta
    estrutura existe para não ter.
    """
    janela = 1_000_000_000
    mapa = _MapaProcedencia(limite=100_000, janela_episodio_ns=janela)
    for i in range(20_000):
        mapa.de(("frio", i), i)
    assert len(mapa) == 20_000
    # o pregão anda muito além da janela, com poucas chaves novas
    ts = 10 * janela
    for i in range(20_000):
        mapa.de(("quente", i % 50), ts + i)
    assert len(mapa) < 2_000, f"os cadaveres ficaram: {len(mapa)}"


def test_a_varredura_da_insercao_segura_um_fluxo_so_de_chaves_novas():
    """O caso em que a varredura amortizada NUNCA roda: nenhuma chave é
    realimentada, então o caminho quente (onde ela mora) nunca é executado.

    É o regime de rotatividade máxima — exatamente o que o `order_id`
    sintético produzia, e o motivo de a varredura existir também na inserção.
    Sem ela o mapa sobe até o teto e fica lá, cheio de chaves que o mercado
    esqueceu há muito: correto na semântica (`obter` devolve None) e
    vazamento na prática.
    """
    janela = 1_000_000
    mapa = _MapaProcedencia(limite=50_000, janela_episodio_ns=janela)
    ts = 0
    for i in range(100_000):
        ts += 1_000  # ~1.000 chaves cabem na janela a qualquer momento
        mapa.de(i, ts)
    assert len(mapa) < 5_000, f"o mapa subiu ate o teto e ficou: {len(mapa)}"


def test_a_virada_zera_o_relogio_da_dedup():
    """A virada de sessão tem de zerar o RELÓGIO junto com as chaves.

    Sem isso o dia 2 nasce com o relógio do dia 1, e a janela do dia 2 passa a
    medir contra um instante que não existe mais. Num backtest que reprocessa
    dias em qualquer ordem — que é o caso de uso declarado do reset no lugar —
    isso deixa a dedup ou permanentemente muda ou permanentemente aberta.
    """
    janela = 1_000
    det = DetectorEscora(ConfigEscora(janela_episodio_ns=janela))
    det.observar(_ev(price=1, ts=10**12))  # dia 1, relógio alto

    det.iniciar_nova_sessao()

    assert det._procedencia.agora_ns == 0
    det.observar(_ev(price=1, ts=0))  # dia 2 recomeça do zero
    det.observar(_ev(price=2, ts=janela + 1))
    assert det._procedencia.obter((Side.BUY, 1)) is None, (
        "o relogio do dia 1 sobreviveu a virada: a janela do dia 2 nao mede nada"
    )


def test_teto_e_respeitado_mesmo_com_a_janela_inteira_viva():
    """Backstop: nem que TODAS as chaves estejam vivas o mapa passa do teto."""
    mapa = _MapaProcedencia(limite=1_000, janela_episodio_ns=JANELA_EPISODIO_NS)
    for i in range(50_000):
        mapa.de(i, i)  # passo de 1 ns: nada expira
    assert len(mapa) == 1_000


def test_teto_de_um_e_valido_e_nao_divide_por_zero():
    """Fronteira baixa: `limite=0` é normalizado para 1, não para "sem teto"."""
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=0))
    for p in range(100):
        det.observar(_ev(price=p))
    assert det.n_chaves_rastreadas == 1


def test_janela_zero_e_valida_e_significa_sem_memoria_entre_eventos():
    """Fronteira baixa da janela: 0 ns é "sem dedup", não "dedup infinito".

    Prende a mutação que troca `max(0, ...)` por um default silencioso: com
    janela 0 qualquer avanço do relógio já expira, e o detector volta a emitir
    a cada evento — comportamento ruim, mas DECLARADO, e o oposto do modo de
    falha perigoso (dedup que nunca solta).
    """
    mapa = _MapaProcedencia(limite=16, janela_episodio_ns=0)
    mapa.de("a", 0).sinalizado = True
    assert mapa.obter("a") is not None  # o relógio não andou
    mapa.de("b", 1)
    assert mapa.obter("a") is None


# ---------------------------------------------------------------------------
# A chave é `(side, price)` nos TRÊS detectores de livro
# ---------------------------------------------------------------------------


def test_dois_order_id_no_mesmo_nivel_sao_o_mesmo_episodio_no_iceberg():
    """O coração do §A.5: em modo MBP o `order_id` é sintético e reciclado a
    ~65.000/s. Dois ids diferentes no MESMO nível dentro da janela são o mesmo
    episódio de iceberg, e valem um alerta só."""
    livro, det, ts = _iceberg_pronto()
    ordem = livro.ordem("iceberg1")
    assert det.verificar(ordem, "WDOV26", ts) is not None

    # a ponte inventa um id novo para a MESMA liquidez, no mesmo nível
    livro2 = LivroMBO("WDOV26")
    livro2.adicionar("iceberg1_reciclado", ordem.side, ordem.price, 50, ts)
    ts2 = ts + 1_000_000_000
    for _ in range(8):
        livro2.executar(ordem.side, ordem.price, 30, ts2)
        livro2.recarregar("iceberg1_reciclado", 30, ts2)
        ts2 += 100_000_000
    outra = livro2.ordem("iceberg1_reciclado")
    assert outra.order_id != ordem.order_id
    assert (outra.side, outra.price) == (ordem.side, ordem.price)

    assert det.verificar(outra, "WDOV26", ts2) is None, (
        "id sintetico novo no mesmo nivel, dentro da janela: episodio novo? nao e"
    )


def test_dois_order_id_no_mesmo_nivel_sao_o_mesmo_episodio_no_fantasma():
    """Mesmo contrato no Fantasma: liquidez grande que aparece e some dez
    vezes em 5000,5 é UM fenômeno, e a ponte MBP entrega dez ids."""
    livro, det = _fantasma_pronto()
    assert det.verificar(livro.ordem("fantasma1"), "WDOV26", 5008) is not None

    emitidas = 0
    ts = 1_000_000_000
    for i in range(10):
        ts += 100_000_000
        livro.adicionar(f"fantasma_reciclado{i}", Side.SELL, 5010, 500, ts)
        ts += 100_000_000
        livro.cancelar(f"fantasma_reciclado{i}", ts)
        if det.verificar(livro.ordem(f"fantasma_reciclado{i}"), "WDOV26", 5008):
            emitidas += 1
    assert emitidas == 0, f"{emitidas} alertas para o mesmo episodio de nivel"


def test_nivel_diferente_continua_sendo_episodio_diferente():
    """O contra-teste da chave por nível: se `_chave_do_evento` colapsasse
    tudo numa constante, o teste acima passaria e o detector ficaria mudo."""
    livro, det = _fantasma_pronto()
    assert det.verificar(livro.ordem("fantasma1"), "WDOV26", 5008) is not None
    livro.adicionar("outro_nivel", Side.SELL, 5011, 500, 1_100_000_000)
    livro.cancelar("outro_nivel", 1_200_000_000)
    assert det.verificar(livro.ordem("outro_nivel"), "WDOV26", 5008) is not None


def test_o_mesmo_nivel_volta_a_emitir_depois_da_janela():
    """A janela é o rearme: meia hora depois, o mesmo nível é outro episódio.

    Sem isto o dedup por nível seria uma mordaça permanente — o defeito §C.4
    da R3 de volta, só que com outra chave.
    """
    janela = 1_000_000_000
    livro, det = _fantasma_pronto(janela_episodio_ns=janela)
    assert det.verificar(livro.ordem("fantasma1"), "WDOV26", 5008) is not None
    ts = 1_000_000_000 + 10 * janela
    livro.adicionar("depois", Side.SELL, 5010, 500, ts)
    livro.cancelar("depois", ts + 100_000_000)
    assert det.verificar(livro.ordem("depois"), "WDOV26", 5008) is not None


def test_o_mesmo_nivel_volta_a_emitir_no_iceberg_depois_da_janela():
    """Gêmeo do teste do Fantasma, para o Iceberg — e ele não é redundante.

    A auto-mutação mostrou por quê: apagar o `avancar(timestamp_ns)` do
    `DetectorIcebergPorRecarga` sobrevivia à suíte inteira, porque só o
    Fantasma tinha um teste que atravessa a janela. Sem o `avancar`, o dedup é
    lido com o relógio do evento ANTERIOR e um nível sinalizado meia hora
    antes segue mudo até que outra chave qualquer faça o relógio andar.
    """
    janela = 1_000_000_000
    livro, det, ts = _iceberg_pronto(janela_episodio_ns=janela)
    assert det.verificar(livro.ordem("iceberg1"), "WDOV26", ts) is not None

    ts_depois = ts + 10 * janela
    livro.executar(Side.SELL, 5000, 30, ts_depois)
    livro.recarregar("iceberg1", 30, ts_depois)
    assert det.verificar(livro.ordem("iceberg1"), "WDOV26", ts_depois) is not None, (
        "meia hora depois, o mesmo nivel e outro episodio"
    )


def test_episodio_longo_de_iceberg_sob_carga_emite_uma_vez_so():
    """O cenário operacional do §A.5, medido: um iceberg que recarrega por
    **5 segundos** enquanto **65.000 ordens sintéticas por segundo** passam.

    Com a chave por `order_id` e teto de 4.096, 4.096 chaves cobriam 63 ms:
    entre duas recargas da mesma ordem passavam dezenas de milhares de ids
    novos, a chave era despejada, e cada recarga virava episódio novo —
    ~300 alertas para um fenômeno. Aqui tem de sair UM.

    O ruído usa `order_id` distinto a cada evento (é o que o `InferidorMBP`
    faz) e preços dentro de uma banda realista de ±200 ticks. A asserção sobre
    `n_chaves_rastreadas` é a prova do mecanismo: 325.000 ids sintéticos
    colapsam na população de NÍVEIS, que é o que o fenômeno tem.
    """
    livro = LivroMBO("WDOV26")
    det = DetectorIcebergPorRecarga(
        ConfigIceberg(razao_minima=3.0, volume_executado_minimo=200)
    )
    det.acompanhar(livro)
    livro.adicionar("iceberg1", Side.SELL, 5000, 50, 0)

    ordens_por_segundo = 65_000
    segundos = 5
    recargas_por_segundo = 2
    ruido_por_recarga = ordens_por_segundo // recargas_por_segundo
    passo_ns = 1_000_000_000 // recargas_por_segundo

    emitidas = []
    ts = 0
    for _ in range(segundos * recargas_por_segundo):
        for j in range(ruido_por_recarga):
            ts += passo_ns // ruido_por_recarga
            det.observar(
                _ev(
                    order_id=f"sint{ts}_{j}",
                    side=Side.BUY if j % 2 else Side.SELL,
                    price=4800 + (j % 401),
                    ts=ts,
                    fonte=FonteMicro.MBP_INFERIDO,
                    confianca=0.6,
                )
            )
        livro.executar(Side.SELL, 5000, 30, ts)
        livro.recarregar("iceberg1", 30, ts)
        saida = det.verificar(livro.ordem("iceberg1"), "WDOV26", ts)
        if saida is not None:
            emitidas.append(saida)

    assert len(emitidas) == 1, f"{len(emitidas)} alertas para UM iceberg de 5s"
    assert det.n_chaves_rastreadas < 1_500, (
        f"{det.n_chaves_rastreadas} chaves para ~800 niveis: a chave voltou a "
        "ser o id sintetico"
    )


def test_o_iceberg_atravessa_carga_de_ordens_sinteticas_sem_perder_a_chave():
    """Retenção do episódio, o eixo que a R4 mediu em MILISSEGUNDOS.

    4.096 chaves contra 65.000 `order_id`/s davam 63 ms de memória. Aqui a
    chave do episódio tem de continuar viva depois de 325.000 eventos
    sintéticos — o número que o `bench_app.py` projeta para 5 segundos de tape
    na barra de 10.000 ev/s.
    """
    det = DetectorLiquidezFantasma(0.5)
    det.observar(_ev(order_id="o1", side=Side.SELL, price=5000, ts=0))
    ts = 0
    for j in range(325_000):
        ts += 15_384  # ~65.000/s
        det.observar(
            _ev(order_id=f"s{j}", side=Side.BUY, price=4800 + (j % 401), ts=ts)
        )
    assert det._procedencia.obter((Side.SELL, 5000)) is not None, (
        "a chave do episodio nao sobreviveu a 5s de ordens sinteticas"
    )
    assert det.n_chaves_rastreadas <= LIMITE_CHAVES_RASTREADAS


# ===========================================================================
# VIRADA DE SESSÃO
# ===========================================================================


def test_virada_reabre_o_dedup_dos_detectores_de_livro():
    """`criticas/nucleo_r3.md` §C.4: um nível sinalizado no dia 1 ficava mudo
    para sempre. Aqui a virada devolve o direito de emitir."""
    livro, det, ts = _escora_no_limiar()
    det.observar(_ev(price=5000, fonte=FonteMicro.MBP_INFERIDO, confianca=0.4))
    assert det.verificar(livro, Side.BUY, 5000, ts) is not None
    assert det.verificar(livro, Side.BUY, 5000, ts) is None
    assert det.n_chaves_rastreadas > 0

    det.iniciar_nova_sessao()

    assert det.n_chaves_rastreadas == 0
    resultado = det.verificar(livro, Side.BUY, 5000, ts)
    assert resultado is not None, "o nivel ficou mudo depois da virada"
    # e a cadeia do dia anterior não sobreviveu junto com o dedup
    assert resultado.evidencia["procedencia"] == "DESCONHECIDA"


def test_virada_zera_a_janela_dos_detectores_de_tape():
    """Sem isso o primeiro trade do dia 2 entra numa janela com o último do
    dia 1 — e uma "exaustão" atravessa o fechamento."""
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    saidas, ts = _episodio_de_exaustao(det)
    assert len([s for s in saidas if s is not None]) == 1
    assert det.n_trades_retidos == 5

    det.iniciar_nova_sessao()

    assert det.n_trades_retidos == 0
    saidas2, _ = _episodio_de_exaustao(det, ts)
    assert len([s for s in saidas2 if s is not None]) == 1, "dedup nao rearmou"


def test_virada_zera_a_janela_e_os_contadores_da_absorcao():
    det = DetectorAbsorcao(
        "WDOV26", ConfigAbsorcao(volume_minimo=200, deslocamento_maximo_ticks=0)
    )
    for i in range(5):
        det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL))
    assert det.n_trades_retidos == 5
    assert det._volume_sell > 0

    det.iniciar_nova_sessao()

    assert det.n_trades_retidos == 0
    assert (det._volume_sell, det._volume_buy) == (0, 0)
    assert det._ja_sinalizado is None
    assert not det._max_precos and not det._min_precos
    # e o detector volta a funcionar do zero
    saidas = [det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL)) for i in range(5)]
    assert len([s for s in saidas if s is not None]) == 1


def test_virada_zera_a_janela_do_clip():
    det = DetectorClipInstitucional(
        "WDOV26",
        ConfigClipInstitucional(n_trades_minimo=5, cv_qty_maximo=0.1, cv_intervalo_maximo=0.1),
    )
    ts = 0
    for _ in range(5):
        det.ao_trade(_trade(ts, 5000, 100, AgressorSide.BUY))
        ts += 1_000_000_000
    assert det.n_trades_retidos == 5
    assert det._ja_sinalizado_janela

    det.iniciar_nova_sessao()

    assert det.n_trades_retidos == 0
    assert not det._ja_sinalizado_janela


def test_todo_detector_expoe_a_virada_de_sessao():
    """Prende a promessa da docstring do módulo: TODO detector tem reset.

    Um detector novo sem `iniciar_nova_sessao` volta a ser um componente que
    carrega o dia anterior — a família de defeito da §C.4, que já custou três
    auditorias.
    """
    import inspect

    import fluxopro.microestrutura.detectores as mod

    detectores = [
        obj
        for nome, obj in vars(mod).items()
        if inspect.isclass(obj) and nome.startswith("Detector")
    ]
    assert len(detectores) == 6
    for cls in detectores:
        assert callable(getattr(cls, "iniciar_nova_sessao", None)), cls.__name__


def test_exaustao_gatilho_3_dispara_com_a_janela_de_pontas_iguais():
    """O gatilho 3 NÃO é redundante com os gatilhos 1 e 2 — e este é o caso.

    Achado da auto-mutação: trocar a comparação de âncora por `if False:`
    sobrevivia a todos os outros testes de exaustão, porque neles a mudança de
    âncora sempre passava antes por "lado misto" (gatilho 1) ou "preço
    progrediu" (gatilho 2), que já rearmavam. Um fuzz de 23.308 emissões
    mostrou 914 em que não passava.

    O motivo é uma sutileza do gatilho 2: `progrediu` compara `janela[0]` com
    `janela[-1]`, as PONTAS da janela — não o intervalo. Um tape que sai de
    5002, passa por 5003 no meio e volta a 5002 nas pontas tem `progrediu ==
    False`, e a âncora pode migrar de 5002 para 5003 sem nunca acionar o
    gatilho 2.

    Sequência abaixo, toda SELL, `n_trades_janela=5` (terço = 1, então a queda
    compara o 1º com o 5º trade da janela):

        t5 -> janela [5000,5002,5003,5002,5002]: pontas 5000/5002 -> rearma
        t6 -> janela [5002,5003,5002,5002,5002]: pontas iguais, queda 0,8
              -> EMITE em 5002
        t7 -> janela [5003,5002,5002,5002,5003]: pontas iguais, queda 0,5
              -> âncora 5002 != 5003, GATILHO 3 -> EMITE em 5003
    """
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    tape = [(5000, 10), (5002, 100), (5003, 40), (5002, 100),
            (5002, 40), (5002, 20), (5003, 20)]
    saidas = []
    for i, (p, q) in enumerate(tape):
        saidas.append(det.ao_trade(_trade(i * 1_000_000, p, q, AgressorSide.SELL)))

    emitidos = [(i, s.price) for i, s in enumerate(saidas) if s is not None]
    assert emitidos == [(5, 5002), (6, 5003)], (
        "o gatilho 3 (ancora nova) tem de emitir mesmo sem gatilho 1 nem 2 "
        f"terem rearmado; saiu {emitidos}"
    )


def test_exaustao_pontas_iguais_com_a_mesma_ancora_continua_mudo():
    """CONTROLE do teste acima: só a MUDANÇA de âncora reabre.

    Mesmo formato de janela (pontas iguais, meio oscilando), mas o preço-âncora
    não muda — e aí o dedup tem de continuar segurando. Sem este controle, o
    teste anterior passaria também com o dedup inteiro removido.
    """
    det = DetectorExaustao("WDOV26", CFG_EXAUSTAO)
    tape = [(5000, 10), (5002, 100), (5003, 40), (5002, 100),
            (5002, 40), (5002, 20), (5002, 20)]
    saidas = []
    for i, (p, q) in enumerate(tape):
        saidas.append(det.ao_trade(_trade(i * 1_000_000, p, q, AgressorSide.SELL)))
    emitidos = [(i, s.price) for i, s in enumerate(saidas) if s is not None]
    assert emitidos == [(5, 5002)], f"mesma ancora nao pode reemitir; saiu {emitidos}"
