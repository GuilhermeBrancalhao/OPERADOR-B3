"""Montagem: configuração única, ordem de entrega no barramento e fontes.

A ordem de entrega é testada por INSPEÇÃO da lista de assinantes *e* por
comportamento. Só a inspeção não bastaria — ela prende a ordem de registro,
não a consequência dela; só o comportamento também não, porque um pipeline
pode dar o mesmo resultado por acaso num tape específico.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import replace
from datetime import time as hora_do_dia
from pathlib import Path

import pytest

from fluxopro.analytics.agressao import ConfigAgressao
from fluxopro.analytics.brokers import ConfigRankingCorretoras
from fluxopro.analytics.delta import ConfigDelta
from fluxopro.analytics.footprint import ConfigFootprint
from fluxopro.analytics.volume_profile import ConfigVolumeProfile
from fluxopro.analytics.vwap import ConfigVWAP
from fluxopro.app.config import (
    PRIORIDADE_MOTOR,
    ConfigOperacao,
    ConfigSimulador,
    FonteDados,
    grid_para_simbolo,
)
from fluxopro.app.montagem import (
    FonteIndisponivelError,
    OpcoesReplay,
    criar_fonte,
    montar,
)
from fluxopro.core.barramento import Barramento
from fluxopro.core.eventos import WDO_GRID, WIN_GRID, AgressorSide, Trade
from fluxopro.dados.leitor_gravacao import AdaptadorLeitorGravacao
from fluxopro.dados.replay import AdaptadorReplay
from fluxopro.dados.simulador import SimuladorWDO
from fluxopro.dados.qualidade import BookKind, FeedState
from fluxopro.gravacao.catalogo import Catalogo
from fluxopro.metodologia.leitura import ConfigMetodologia
from fluxopro.microestrutura.detectores import (
    ConfigAbsorcao,
    ConfigClipInstitucional,
    ConfigEscora,
    ConfigExaustao,
    ConfigIceberg,
    ConfigLiquidezFantasma,
)
from fluxopro.microestrutura.inferencia_mbp import ConfigInferenciaMBP
from fluxopro.microestrutura.livro_mbo import ConfigLivroMBO
from fluxopro.motor.sinais import ConfigMotorSinais

SYMBOL = "WDOV26"


def config_curta(**kwargs) -> ConfigOperacao:
    base = dict(
        symbol=SYMBOL,
        simulador=ConfigSimulador(seed=42, n_eventos=300),
    )
    base.update(kwargs)
    return ConfigOperacao(**base)  # type: ignore[arg-type]


def test_montagem_vincula_monitor_ao_ciclo_fisico_mt5_sem_fingir_conexao():
    montagem = montar(
        config_curta(fonte=FonteDados.MT5, ligar_feed_quality=True)
    )

    assert montagem.sessao.feed_monitor is not None
    assert montagem.fonte._feed_monitor is montagem.sessao.feed_monitor
    snap = montagem.sessao.feed_monitor.snapshot()
    assert snap.state is FeedState.STOPPED
    assert snap.book_kind is BookKind.NONE


def test_montagem_preserva_prontidao_das_fontes_locais():
    montagem = montar(config_curta(ligar_feed_quality=True))

    assert montagem.sessao.feed_monitor is not None
    assert montagem.sessao.feed_monitor.snapshot().state is FeedState.CONNECTED


def donos(barramento, tipo) -> list[tuple[str, str]]:
    """(classe, método) de cada assinante, na ordem em que serão chamados."""
    saida = []
    for assinatura in barramento._assinantes[tipo]:
        cb = assinatura.callback
        dono = getattr(cb, "__self__", None)
        saida.append((type(dono).__name__ if dono is not None else "-", cb.__name__))
    return saida


# ---------------------------------------------------------------------------
# Ordem de entrega
# ---------------------------------------------------------------------------


def test_ordem_de_entrega_no_barramento_para_trade():
    """Prende a cadeia inteira: núcleo -> analytics -> perfil de sessão ->
    microestrutura -> motor -> método -> contagem.

    Este teste existe porque a ordem das quatro primeiras peças NÃO pode ser
    declarada por prioridade: `EstadoMercado` e os analytics assinam a si
    mesmos no construtor sem parâmetro de prioridade (ver `app/config.py`,
    "LIMITAÇÃO REAL"). A única alavanca é a ordem de construção — e ordem de
    construção implícita é exatamente o tipo de invariante que se perde numa
    refatoração distraída. Aqui ela vira teste.
    """
    montagem = montar(config_curta())
    assert donos(montagem.barramento, Trade) == [
        # Antes de TODO acumulador: o carimbo de qual thread esta publicando,
        # que e o que decide se montar o retrato de analytics inline e seguro
        # (`SessaoFluxo.retrato_de_analytics`). Carimbar depois deixaria uma
        # janela em que o primeiro trade ja mutou o perfil.
        ("SessaoFluxo", "_ao_trade_marca_thread"),
        ("EstadoMercado", "_ao_trade"),
        ("VolumeProfilePorPeriodo", "_ao_trade"),
        ("FootprintPorTimeframe", "_ao_trade"),
        ("CumulativeDelta", "_ao_trade"),
        ("MedidorAgressao", "_ao_trade"),
        ("VWAP", "_ao_trade"),
        ("RankingCorretoras", "_ao_trade"),
        ("SessaoFluxo", "_ao_trade_perfil_sessao"),
        ("SessaoFluxo", "_ao_trade_micro"),
        ("SessaoFluxo", "_ao_trade_detectores_tape"),
        ("SessaoFluxo", "_ao_trade_perfil_player"),
        ("SessaoFluxo", "_ao_trade_motor"),
        ("SessaoFluxo", "_ao_trade_metodo"),
        ("SessaoFluxo", "_contar_trade"),
        # Depois da contagem: o retrato de analytics so pode ser congelado
        # quando "processado" ja quer dizer processado.
        ("SessaoFluxo", "_ao_trade_montar_retrato"),
    ]


def test_o_perfil_de_sessao_ja_inclui_o_trade_quando_o_motor_roda():
    """A seta load-bearing da condição 2, provada por comportamento.

    Se o motor rodasse antes do perfil, `_na_regiao` responderia sobre o
    mercado de um trade atrás. A sonda entra logo antes do motor (prioridade
    `PRIORIDADE_MOTOR - 1`) e exige que o volume do trade corrente JÁ esteja
    no perfil que o motor vai ler.
    """
    montagem = montar(config_curta())
    sessao = montagem.sessao
    visto: list[tuple[int, int]] = []

    def sonda(trade: Trade) -> None:
        visto.append((sessao.perfil_sessao.volume_total, trade.qty))

    montagem.barramento.assinar(Trade, sonda, prioridade=PRIORIDADE_MOTOR - 1)

    acumulado = 0
    for i, qty in enumerate((5, 7, 3), start=1):
        acumulado += qty
        montagem.barramento.publicar(
            Trade(i * 1_000_000, SYMBOL, 10_000, qty, AgressorSide.BUY, f"t{i}")
        )
        assert visto[-1] == (acumulado, qty)


def test_o_livro_ja_foi_alimentado_quando_o_motor_roda():
    """A segunda seta load-bearing: `InferidorMBP` (prioridade MICRO) roda
    antes do motor (prioridade MOTOR), então o livro que qualquer consumidor
    a jusante lê é o do evento corrente, não o do anterior."""
    montagem = montar(config_curta())
    ordem = [nome for _, nome in donos(montagem.barramento, Trade)]
    assert ordem.index("_ao_trade_micro") < ordem.index("_ao_trade_motor")


# ---------------------------------------------------------------------------
# ConfigOperacao
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, classe",
    [
        ("volume_profile", ConfigVolumeProfile),
        ("footprint", ConfigFootprint),
        ("delta", ConfigDelta),
        ("agressao", ConfigAgressao),
        ("vwap", ConfigVWAP),
        ("brokers", ConfigRankingCorretoras),
        ("livro", ConfigLivroMBO),
        ("inferencia", ConfigInferenciaMBP),
        ("absorcao", ConfigAbsorcao),
        ("escora", ConfigEscora),
        ("iceberg", ConfigIceberg),
        ("liquidez_fantasma", ConfigLiquidezFantasma),
        ("exaustao", ConfigExaustao),
        ("clip_institucional", ConfigClipInstitucional),
        ("motor", ConfigMotorSinais),
        ("metodologia", ConfigMetodologia),
    ],
)
def test_config_operacao_nao_redigita_nenhum_default(campo, classe):
    """Cada sub-config tem de ser IGUAL ao default do módulo dono.

    Se alguém "documentasse" um limiar copiando o número para cá, o default do
    módulo poderia mudar e a montagem continuaria operando com o valor velho —
    em silêncio. Isto é a trava contra isso.
    """
    assert getattr(ConfigOperacao(), campo) == classe()


def test_config_operacao_e_sobrescrivel_em_qualquer_nivel():
    cfg = ConfigOperacao(
        symbol="WINZ26",
        motor=ConfigMotorSinais(dominancia_minima=0.75, janela_dominancia_ns=3_000_000_000),
    )
    assert cfg.motor.dominancia_minima == 0.75
    # o que não foi tocado continua vindo do módulo dono
    assert cfg.motor.magnitude_relativa_minima == ConfigMotorSinais().magnitude_relativa_minima
    assert cfg.price_grid() == WIN_GRID


def test_a_calibracao_chega_de_fato_aos_componentes():
    """Config não é decoração: o objeto configurado é o que a peça recebe."""
    cfg = config_curta(
        motor=ConfigMotorSinais(dominancia_minima=0.9),
        absorcao=ConfigAbsorcao(volume_minimo=7),
        livro=ConfigLivroMBO(janela_reposicao_ns=123),
        inferencia=ConfigInferenciaMBP(janela_reconciliacao_ns=456),
    )
    sessao = montar(cfg).sessao
    assert sessao.motor is not None and sessao.motor.config.dominancia_minima == 0.9
    assert sessao.det_absorcao is not None and sessao.det_absorcao.config.volume_minimo == 7
    assert sessao.livro is not None and sessao.livro.config.janela_reposicao_ns == 123
    assert sessao.inferidor is not None
    assert sessao.inferidor.config.janela_reconciliacao_ns == 456


def test_grid_deriva_do_simbolo_e_pode_ser_forcado():
    assert grid_para_simbolo("WDOV26") == WDO_GRID
    assert grid_para_simbolo("winz26") == WIN_GRID
    assert ConfigOperacao(symbol="WINZ26").price_grid() == WIN_GRID
    assert ConfigOperacao(symbol="WINZ26", grid=WDO_GRID).price_grid() == WDO_GRID


def test_estagios_desligados_nao_instanciam_a_peca():
    sessao = montar(
        config_curta(
            ligar_analytics=False,
            ligar_microestrutura=False,
            ligar_detectores_tape=False,
            ligar_motor=False,
            ligar_metodologia=False,
        )
    ).sessao
    assert sessao.volume_profile is None
    assert sessao.vwap is None
    assert sessao.livro is None
    assert sessao.inferidor is None
    assert sessao.det_absorcao is None
    assert sessao.motor is None
    assert sessao.metodo is None
    # o que NÃO é opcional continua de pé
    assert sessao.estado is not None
    assert sessao.perfil_sessao is not None


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------


def test_simulador_roda_sem_mt5_instalado():
    """O requisito do dono: ver o sistema funcionando hoje, sem corretora.

    A checagem é sobre `sys.modules`: montar a fonte de simulador não pode ter
    importado o pacote `MetaTrader5` nem sequer indiretamente — é isso que faz
    o produto abrir numa máquina sem terminal instalado.
    """
    montagem = montar(config_curta())
    assert isinstance(montagem.fonte, SimuladorWDO)
    assert "MetaTrader5" not in sys.modules
    montagem.fonte.iniciar()
    assert montagem.sessao.contadores.n_trades_bus == 300


def test_simulador_respeita_tick_size_do_simbolo():
    """WIN tem tick 5.0; passar o grid errado deslocaria todo o preço."""
    montagem = montar(
        ConfigOperacao(symbol="WINZ26", simulador=ConfigSimulador(n_eventos=50))
    )
    montagem.fonte.iniciar()
    ultimo = montagem.sessao.estado.ultimo_trade
    assert ultimo is not None
    # preco_inicial 5000.0 / tick 5.0 = 1000 ticks (e nao 10.000 do grid do WDO)
    assert abs(ultimo.price - 1000) < 200


def _escrever_csv_trades(caminho: Path, n: int = 5) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        w = csv.writer(arq)
        w.writerow(
            ["timestamp_ns", "symbol", "price", "qty", "side_agressor", "trade_id"]
        )
        for i in range(n):
            w.writerow([i * 1_000_000, SYMBOL, 10_000 + i, 5, "BUY", f"t{i}"])


def test_replay_de_csv(tmp_path: Path):
    caminho = tmp_path / "trades.csv"
    _escrever_csv_trades(caminho)
    montagem = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=caminho),
    )
    assert isinstance(montagem.fonte, AdaptadorReplay)
    montagem.fonte.iniciar()
    assert montagem.sessao.contadores.n_trades_bus == 5


def test_recorte_de_horario_em_csv_falha_fechado(tmp_path: Path):
    """O CSV do núcleo não tem índice de tempo. Aceitar `--de/--ate` e
    entregar o arquivo inteiro seria mentir sobre o recorte."""
    caminho = tmp_path / "trades.csv"
    _escrever_csv_trades(caminho)
    with pytest.raises(FonteIndisponivelError, match="recorte de horario"):
        montar(
            config_curta(fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=caminho, de=hora_do_dia(9, 0)),
        )


def test_replay_sem_caminho_e_erro_explicito():
    with pytest.raises(FonteIndisponivelError, match="caminho"):
        montar(config_curta(fonte=FonteDados.REPLAY))


def test_replay_de_caminho_inexistente_e_erro_explicito(tmp_path: Path):
    with pytest.raises(FonteIndisponivelError, match="inexistente"):
        montar(
            config_curta(fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=tmp_path / "nao_existe"),
        )


def test_replay_de_gravacao_encontra_o_dia_e_o_recorte(tmp_path: Path):
    """Fecha o ciclo com o `Gravador`: grava com o pipeline ligado, relê a
    gravação pelo catálogo (com verificação de hash) e confere o recorte."""
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    montagem = montar(config_curta(simulador=ConfigSimulador(seed=1, n_eventos=200)))
    gravador = Gravador(montagem.barramento, gravacao)
    gravador.iniciar()
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    gravador.parar()

    lido = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao),
    )
    assert isinstance(lido.fonte, AdaptadorLeitorGravacao)
    lido.fonte.iniciar()
    assert lido.sessao.contadores.n_trades_bus == 200
    assert lido.sessao.contadores.n_snapshots_bus == 200


def test_replay_de_gravacao_sem_o_simbolo_diz_o_que_existe(tmp_path: Path):
    """A mensagem tem de dizer O QUE EXISTE, não só repetir o que foi pedido.

    Este teste já existia e passava **pelo motivo errado**: achado por mutação
    (`MM2` desta onda). Removendo o filtro por símbolo, `disponiveis` fica com
    as gravações de OUTRO símbolo, o fluxo segue até `consultar_intervalo`,
    que devolve `None`, e a mensagem que sai é a de "dia não gravado" — que
    também contém a string `OUTRO`. O `match="OUTRO"` passava nas duas
    implementações.

    A asserção que distingue é a lista de símbolos gravados: só o ramo certo
    a produz, e é ela que diz ao dono "voce pediu OUTRO, o que existe é
    WDOV26" em vez de "OUTRO nao tem gravacao nesse dia" — que sugeriria
    tentar outro dia para um símbolo que nunca foi gravado.
    """
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    montagem = montar(config_curta(simulador=ConfigSimulador(n_eventos=20)))
    gravador = Gravador(montagem.barramento, gravacao)
    gravador.iniciar()
    montagem.fonte.iniciar()
    gravador.parar()

    with pytest.raises(FonteIndisponivelError) as erro:
        montar(
            config_curta(symbol="OUTRO", fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=gravacao),
        )

    mensagem = str(erro.value)
    assert "OUTRO" in mensagem
    assert "simbolos gravados" in mensagem, (
        "a mensagem nao lista o que existe: o filtro por simbolo nao rodou e "
        "o erro veio do ramo de 'dia nao gravado'"
    )
    assert SYMBOL in mensagem, "a mensagem nao diz qual simbolo esta gravado"


def test_gravacao_de_outro_simbolo_nao_e_reproduzida_no_lugar_do_pedido(
    tmp_path: Path,
):
    """A consequência silenciosa que a mensagem esconde, presa por
    comportamento: se o filtro por símbolo caísse, a montagem poderia entregar
    o tape do símbolo ERRADO. Num produto cuja saída inteira é "quem está
    fazendo o quê neste instrumento", reproduzir WDO achando que é WIN é o
    tipo de erro que não se percebe olhando a tela.
    """
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    montagem = montar(config_curta(simulador=ConfigSimulador(n_eventos=20)))
    gravador = Gravador(montagem.barramento, gravacao)
    gravador.iniciar()
    montagem.fonte.iniciar()
    gravador.parar()

    # o dia gravado É o dia do tape de WDOV26; pedir OUTRO símbolo nesse mesmo
    # dia não pode devolver uma fonte — tem de falhar.
    entradas = Catalogo(gravacao).escanear()
    assert entradas, "a gravacao de apoio ficou vazia"
    dia_gravado = entradas[0].data

    with pytest.raises(FonteIndisponivelError):
        montar(
            config_curta(symbol="OUTRO", fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=gravacao, data=dia_gravado),
        )


def test_fonte_desconhecida_e_erro():
    cfg = config_curta()
    quebrada = replace(cfg, fonte="nao_e_uma_fonte")  # type: ignore[arg-type]
    from fluxopro.core.barramento import Barramento

    with pytest.raises(FonteIndisponivelError):
        criar_fonte(quebrada, Barramento())


# ---------------------------------------------------------------------------
# A ordem de construção dentro de `montar` (`criticas/nucleo_r4.md` Y04)
#
# A docstring de `montar` diz, com todas as letras, que trocar as duas linhas
# — construir a fonte antes da sessão — "é uma corrida que só não estoura
# porque `iniciar()` ainda não foi chamado, e 'só não estoura porque ninguém
# chamou ainda' não é invariante". A mutação Y04 faz exatamente a troca e
# sobreviveu a duas rodadas: nenhuma fonte de produção publica no construtor
# HOJE, então a corrida é latente.
#
# O teste abaixo não espera que uma fonte de produção passe a publicar no
# construtor. Ele faz o que a docstring descreve: injeta uma fonte QUE
# PUBLICA no construtor e exige que a sessão já esteja ouvindo. É a diferença
# entre "não estoura porque ninguém tentou" e "não estoura".
# ---------------------------------------------------------------------------


def test_a_sessao_ja_ouve_o_que_a_fonte_publica_no_construtor(monkeypatch):
    trade = Trade(
        timestamp_ns=1,
        symbol=SYMBOL,
        price=10_000,
        qty=3,
        side_agressor=AgressorSide.BUY,
        trade_id="no-construtor",
        buyer_broker="XP",
        seller_broker="BTG",
    )

    class FontePublicaNoConstrutor(SimuladorWDO):
        def __init__(self, barramento, **kwargs):
            super().__init__(barramento, **kwargs)
            barramento.publicar(trade)

    monkeypatch.setattr(
        "fluxopro.app.montagem.SimuladorWDO", FontePublicaNoConstrutor
    )
    montagem = montar(config_curta())

    assert montagem.sessao.contadores.n_trades_bus == 1, (
        "o evento publicado na construcao da fonte se perdeu: a fonte foi "
        "construida ANTES da sessao assinar o barramento"
    )
    assert montagem.sessao.estado.ultimo_trade is not None
    assert montagem.sessao.estado.ultimo_trade.trade_id == "no-construtor"


def test_a_montagem_devolve_a_sessao_ja_ligada_ao_mesmo_barramento():
    """O contrato de `montar`: quem chama só precisa de `fonte.iniciar()`.
    Se a sessão fosse construída sobre outro barramento, tudo continuaria
    verde nos testes que só olham a fonte — e nada seria processado."""
    montagem = montar(config_curta())
    assert montagem.sessao.barramento is montagem.barramento
    assert montagem.fonte._barramento is montagem.barramento


# ---------------------------------------------------------------------------
# Escolha do dia e verificação de integridade
# (`criticas/nucleo_r4.md` Y06 e Y07 — as duas vivas desde a R4)
# ---------------------------------------------------------------------------


def _gravar_dois_dias(tmp_path: Path) -> Path:
    """Grava DOIS dias do mesmo símbolo, com contagens diferentes.

    O `Gravador` bucketiza por data do `timestamp_ns`, então basta publicar
    tape com timestamps em dias distintos. As contagens são diferentes de
    propósito: é assim que o teste distingue QUAL dia foi escolhido sem
    depender de nenhum detalhe interno do catálogo.
    """
    from fluxopro.gravacao.gravador import Gravador

    gravacao = tmp_path / "dados"
    barramento = Barramento()
    gravador = Gravador(barramento, gravacao)
    gravador.iniciar()

    dia_antigo_ns = 1_600_000_000 * 10**9  # 2020-09-13
    dia_novo_ns = dia_antigo_ns + 86_400 * 10**9  # o dia seguinte
    for base, n in ((dia_antigo_ns, 3), (dia_novo_ns, 7)):
        for i in range(n):
            barramento.publicar(
                Trade(
                    timestamp_ns=base + i * 1_000_000,
                    symbol=SYMBOL,
                    price=10_000 + i,
                    qty=1,
                    side_agressor=AgressorSide.BUY,
                    trade_id=f"t{base}-{i}",
                    buyer_broker="XP",
                    seller_broker="BTG",
                )
            )
    gravador.parar()
    return gravacao


def test_replay_de_gravacao_escolhe_o_dia_MAIS_RECENTE(tmp_path: Path):
    """`--data` ausente significa "o último pregão gravado", não "o primeiro".

    Y06 troca `max` por `min` e sobreviveu porque toda a suíte de gravação
    operava sobre UM dia só — com um dia só, `max` e `min` são o mesmo. O
    teste distingue pela CONTAGEM (3 no dia antigo, 7 no recente), não pela
    data: assim ele mede a consequência ("o replay rodou sobre o dia errado")
    e não a expressão que a produz.

    Combinado com `X18` (o catálogo não limpa o índice ao reescanear), Y06 é
    o caminho para o replay rodar sobre um dia que já não existe no disco — e
    esta é a única fonte de dado histórico que o produto tem.
    """
    gravacao = _gravar_dois_dias(tmp_path)

    lido = montar(
        config_curta(fonte=FonteDados.REPLAY), replay=OpcoesReplay(caminho=gravacao)
    )
    lido.fonte.iniciar()

    assert lido.sessao.contadores.n_trades_bus == 7, (
        "a montagem escolheu o dia MAIS ANTIGO da gravacao"
    )


def test_replay_de_gravacao_respeita_a_data_pedida(tmp_path: Path):
    """A outra direção: com `--data` explícita, o dia antigo tem de ser
    alcançável. Sem isto, "escolhe sempre o mais recente" passaria no teste
    acima e quebraria o caso de uso real."""
    from datetime import datetime, timezone

    gravacao = _gravar_dois_dias(tmp_path)
    dia_antigo = datetime.fromtimestamp(1_600_000_000, tz=timezone.utc).date()

    lido = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao, data=dia_antigo),
    )
    lido.fonte.iniciar()

    assert lido.sessao.contadores.n_trades_bus == 3


def _corromper_um_arquivo_de_dados(gravacao: Path) -> Path:
    """Edita uma linha de dado de um dos CSVs gravados, mantendo o arquivo
    perfeitamente legível. Só o hash denuncia."""
    candidatos = sorted(gravacao.rglob("trades.csv*"))
    assert candidatos, f"nenhum trades.csv em {gravacao}"
    alvo = candidatos[-1]
    if alvo.suffix == ".gz":
        import gzip

        texto = gzip.decompress(alvo.read_bytes()).decode("utf-8")
        linhas = texto.splitlines(keepends=True)
        linhas[1] = linhas[1].replace(",1,", ",999,", 1)
        alvo.write_bytes(gzip.compress("".join(linhas).encode("utf-8")))
    else:
        linhas = alvo.read_text(encoding="utf-8").splitlines(keepends=True)
        linhas[1] = linhas[1].replace(",1,", ",999,", 1)
        alvo.write_text("".join(linhas), encoding="utf-8")
    return alvo


def test_montagem_reprova_gravacao_corrompida(tmp_path: Path):
    """Y07 desliga a verificação de hash em silêncio e a suíte fica verde.

    O sha256 por arquivo é a única defesa contra gravação corrompida — a
    docstring de `Catalogo.verificar_integridade` gasta quinze linhas
    explicando que não existe fonte externa de histórico de book para
    WDO/WIN. O teste corrompe um arquivo SEM torná-lo ilegível (troca uma
    quantidade), que é o caso que só o hash pega.
    """
    from fluxopro.dados.leitor_gravacao import IntegridadeInvalidaError

    gravacao = _gravar_dois_dias(tmp_path)
    _corromper_um_arquivo_de_dados(gravacao)

    with pytest.raises(IntegridadeInvalidaError):
        montar(
            config_curta(fonte=FonteDados.REPLAY),
            replay=OpcoesReplay(caminho=gravacao),
        )


def test_sem_verificar_hash_e_uma_escolha_do_usuario_e_funciona(tmp_path: Path):
    """A outra direção, e ela importa tanto quanto: uma verificação que
    ignorasse `verificar_hash=False` (mutação inversa de Y07) transformaria a
    flag de diagnóstico em enfeite, e o dono não teria como abrir uma
    gravação parcialmente corrompida para ver o que sobrou."""
    gravacao = _gravar_dois_dias(tmp_path)
    _corromper_um_arquivo_de_dados(gravacao)

    lido = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao, verificar_hash=False),
    )
    lido.fonte.iniciar()
    assert lido.sessao.contadores.n_trades_bus == 7


def test_a_flag_de_hash_chega_ao_adaptador_nas_duas_posicoes(tmp_path: Path):
    """Prende o repasse em si, e não só o efeito: é o parâmetro que Y07
    substitui por um literal `False`."""
    gravacao = _gravar_dois_dias(tmp_path)

    ligado = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao, verificar_hash=True),
    ).fonte
    desligado = montar(
        config_curta(fonte=FonteDados.REPLAY),
        replay=OpcoesReplay(caminho=gravacao, verificar_hash=False),
    ).fonte

    assert isinstance(ligado, AdaptadorLeitorGravacao)
    assert isinstance(desligado, AdaptadorLeitorGravacao)
    assert ligado._verificar_hash is True
    assert desligado._verificar_hash is False
