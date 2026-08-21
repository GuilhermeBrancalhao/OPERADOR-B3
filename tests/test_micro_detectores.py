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
    LIMITE_CHAVES_RASTREADAS,
    TipoDeteccao,
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


def test_iceberg_retem_no_maximo_o_teto_de_ordens():
    det = DetectorIcebergPorRecarga(ConfigIceberg(max_ordens_rastreadas=1024))
    for i in range(50_000):
        det.observar(_ev(order_id=f"ice{i}", tipo=TipoEventoOrdem.TRADE))
    assert det.n_chaves_rastreadas == 1024


def test_liquidez_fantasma_retem_no_maximo_o_teto_de_ordens():
    det = DetectorLiquidezFantasma(
        0.5, ConfigLiquidezFantasma(max_ordens_rastreadas=1024)
    )
    for i in range(50_000):
        det.observar(_ev(order_id=f"f{i}", tipo=TipoEventoOrdem.CANCEL))
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


def test_iceberg_propaga_a_cadeia_por_order_id():
    livro, det, ts = _iceberg_pronto()
    det.observar(
        _ev(order_id="iceberg1", tipo=TipoEventoOrdem.TRADE,
            fonte=FonteMicro.MBP_INFERIDO, confianca=0.5)
    )
    det.observar(_ev(order_id="iceberg1", tipo=TipoEventoOrdem.TRADE, confianca=1.0))
    resultado = det.verificar(livro.ordem("iceberg1"), "WDOV26", ts)
    assert resultado is not None
    assert resultado.confianca == 0.5
    assert resultado.evidencia["procedencia"] == "INFERIDA"


def test_iceberg_nao_mistura_a_cadeia_de_outra_ordem():
    livro, det, ts = _iceberg_pronto()
    det.observar(
        _ev(order_id="outra", tipo=TipoEventoOrdem.TRADE,
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


def test_liquidez_fantasma_propaga_a_cadeia_por_order_id():
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
    sem dedup por `order_id` cada consulta re-emitia o mesmo alerta."""
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
# TETO FIFO do `_MapaProcedencia` — testado como CONTRATO
# ===========================================================================


def test_teto_despeja_a_chave_mais_antiga():
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=3))
    for p in (1, 2, 3):
        det.observar(_ev(price=p))
    det.observar(_ev(price=4))
    assert det.n_chaves_rastreadas == 3
    assert det._procedencia.obter((Side.BUY, 1)) is None, "a mais antiga tinha de sair"
    for p in (2, 3, 4):
        assert det._procedencia.obter((Side.BUY, p)) is not None


def test_chave_realimentada_sobrevive_ao_despejo():
    """O despejo é pela menos recentemente ALIMENTADA, não pela mais velha
    em absoluto: `observar` renova a posição da chave na fila."""
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=3))
    for p in (1, 2, 3):
        det.observar(_ev(price=p))
    det.observar(_ev(price=1))  # o mercado voltou a mexer no nível 1
    det.observar(_ev(price=4))
    assert det._procedencia.obter((Side.BUY, 1)) is not None
    assert det._procedencia.obter((Side.BUY, 2)) is None, "a 2 era a mais fria"


def test_consulta_nao_renova_a_chave():
    """`obter`/`esta_sinalizado` LEEM sem renovar — o que mantém uma chave viva
    é o mercado mexer nela, não o detector perguntar por ela.

    Se a consulta renovasse, um `verificar` em laço sobre uma chave morta a
    seguraria no mapa indefinidamente e o teto deixaria de refletir o que
    ainda está acontecendo.
    """
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=2))
    det.observar(_ev(price=1))
    det.observar(_ev(price=2))
    for _ in range(50):
        det.esta_sinalizado((Side.BUY, 1))  # consulta em laço
    det.observar(_ev(price=3))
    assert det._procedencia.obter((Side.BUY, 1)) is None


def test_chave_despejada_pode_voltar_a_emitir():
    """O CONTRATO do teto, testado como contrato e não como bug.

    Memória limitada vale mais que dedup perfeito sobre uma chave que o
    mercado esqueceu: a chave despejada é a menos recentemente alimentada.
    O preço é uma re-emissão possível — declarado aqui para que ninguém o
    descubra em produção achando que é defeito.
    """
    livro, det, ts = _escora_no_limiar(max_niveis_rastreados=2)
    assert det.verificar(livro, Side.BUY, 5000, ts) is not None
    assert det.verificar(livro, Side.BUY, 5000, ts) is None, "dedup nao pegou"
    assert det.esta_sinalizado((Side.BUY, 5000))

    # o pregão anda: duas chaves novas empurram (BUY, 5000) para fora
    det.observar(_ev(price=1))
    det.observar(_ev(price=2))
    assert not det.esta_sinalizado((Side.BUY, 5000)), "a chave nao foi despejada"

    assert det.verificar(livro, Side.BUY, 5000, ts) is not None, (
        "chave despejada tem de poder emitir de novo — e o dedup volta a valer"
    )
    assert det.verificar(livro, Side.BUY, 5000, ts) is None


def test_teto_de_um_e_valido_e_nao_divide_por_zero():
    """Fronteira baixa: `limite=0` é normalizado para 1, não para "sem teto"."""
    det = DetectorEscora(ConfigEscora(max_niveis_rastreados=0))
    for p in range(100):
        det.observar(_ev(price=p))
    assert det.n_chaves_rastreadas == 1


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
