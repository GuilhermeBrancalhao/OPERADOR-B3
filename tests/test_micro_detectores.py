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
    TipoDeteccao,
)
from fluxopro.microestrutura.eventos_mbo import FonteMicro
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
