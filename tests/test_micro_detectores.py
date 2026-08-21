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
    resultado = None
    for i in range(5):
        resultado = det.ao_trade(_trade(i * 1000, 5000, 50, AgressorSide.SELL))
    assert resultado is not None
    assert resultado.tipo is TipoDeteccao.ABSORCAO
    assert resultado.side is Side.BUY  # comprador absorvendo a venda
    assert resultado.evidencia["volume_agressao_dominante"] == 250


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
