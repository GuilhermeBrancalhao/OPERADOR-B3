"""A fiação de `fluxopro/metodologia/` dentro do pipeline vivo.

`tests/test_metodologia.py` prova o comportamento dos componentes e do
`LeitorMetodo` isoladamente. Aqui a pergunta é outra, e é a que estava sem
resposta: **os componentes do método recebem, de fato, o mesmo tape que o
resto da cadeia, e o que eles publicam descreve o mesmo instante que o resto
do produto descreve?**

Até esta rodada a resposta era não — o pacote existia, testado, e nenhum
evento de produção chegava a ele. É o mesmo defeito que
`criticas/nucleo_r2.md:371-372` registrou para `MotorSinais` e `InferidorMBP`
("as peças existiam, testadas, e o pipeline nunca tinha rodado inteiro"), e
por isso estes testes seguem o mesmo molde de `tests/test_app_pipeline.py`:
**todo teste positivo tem um controle que rompe o elo e exige que a mesma
verificação falhe.**

| elo | invariante | controle que o rompe |
|---|---|---|
| tape -> `LeitorMetodo` | `n_trades_metodo == n_trades_bus` | `test_severar_o_elo_do_metodo_derruba_a_verificacao` |
| método -> retrato | `leitura_do_metodo()` não é `None` | idem |
| método × núcleo | extremos e delta batem com `EstadoMercado`/`CumulativeDelta` | `test_sem_metodologia_nao_ha_retrato_nenhum` |
| ordem na faixa 45 | consumidor da saída vê o retrato do trade corrente | `test_a_sonda_entre_o_motor_e_a_contagem_ve_o_retrato_de_agora` |
"""

from __future__ import annotations

import pytest

from fluxopro.app.config import (
    PRIORIDADE_MOTOR,
    PRIORIDADE_SAIDA,
    ConfigOperacao,
    ConfigSimulador,
)
from fluxopro.app.montagem import montar
from fluxopro.app.sessao_fluxo import SessaoFluxo
from fluxopro.core.eventos import AgressorSide, Trade
from fluxopro.metodologia.leitura import (
    ConfigMetodologia,
    FontePlacar,
    LeituraMetodo,
)
from fluxopro.metodologia.linha_azul import ConfigLinhaAzul
from fluxopro.metodologia.placar import ConfigPlacar, Placar
from fluxopro.metodologia.risco import (
    ConfigRisco,
    ModoTamanho,
    QualidadeRegiao,
    ResultadoOperacao,
)

SYMBOL = "WDOV26"
SEED = 42
N_EVENTOS = 2_000


def config(seed: int = SEED, n: int = N_EVENTOS, **kwargs) -> ConfigOperacao:
    base = dict(symbol=SYMBOL, simulador=ConfigSimulador(seed=seed, n_eventos=n))
    base.update(kwargs)
    return ConfigOperacao(**base)  # type: ignore[arg-type]


def rodar(cfg: ConfigOperacao | None = None):
    montagem = montar(cfg if cfg is not None else config())
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    return montagem


def verificar_metodo_ligado(sessao: SessaoFluxo) -> None:
    """As invariantes de "o método recebeu o pregão inteiro".

    Extraída como função para que o teste positivo e o controle usem
    exatamente a mesma verificação — um controle mais fraco não provaria que
    o positivo enxerga a desconexão.
    """
    c = sessao.contadores
    assert c.n_trades_bus > 0, "a fonte nao publicou trade nenhum"
    assert c.n_trades_metodo == c.n_trades_bus, "o metodo nao viu o mesmo tape"

    leitura = sessao.leitura_do_metodo()
    assert leitura is not None, "nenhum retrato do metodo foi publicado"
    assert leitura.sequencia == c.n_trades_bus
    assert leitura.placar.total_fontes == len(sessao.config.metodologia.fontes_placar)


def _severar(barramento, tipo, nome_metodo: str) -> None:
    lista = barramento._assinantes[tipo]
    restantes = [a for a in lista if a.callback.__name__ != nome_metodo]
    assert len(restantes) < len(lista), f"nao havia assinatura {nome_metodo} em {tipo}"
    barramento._assinantes[tipo] = tuple(restantes)


# ---------------------------------------------------------------------------
# O elo, e o controle que o rompe
# ---------------------------------------------------------------------------


def test_o_metodo_recebe_o_mesmo_tape_que_o_resto_da_cadeia():
    montagem = rodar()
    verificar_metodo_ligado(montagem.sessao)


def test_severar_o_elo_do_metodo_derruba_a_verificacao():
    """CONTROLE: desconectar o método precisa ser visível, não silencioso."""
    montagem = montar(config())
    _severar(montagem.barramento, Trade, "_ao_trade_metodo")
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    with pytest.raises(AssertionError):
        verificar_metodo_ligado(montagem.sessao)


def test_sem_metodologia_nao_ha_retrato_nenhum():
    """O estágio é desligável, como os outros quatro — e o custo sai junto."""
    montagem = rodar(config(n=200, ligar_metodologia=False))
    sessao = montagem.sessao
    assert sessao.metodo is None
    assert sessao.leitura_do_metodo() is None
    assert sessao.contadores.n_trades_metodo == 0
    assert sessao.contadores.n_trades_bus > 0
    # e o resto do pipeline continua de pe
    assert sessao.contadores.n_trades_motor == sessao.contadores.n_trades_bus


def test_desligado_o_metodo_nao_assina_o_barramento():
    montagem = montar(config(n=1, ligar_metodologia=False))
    nomes = [a.callback.__name__ for a in montagem.barramento._assinantes[Trade]]
    assert "_ao_trade_metodo" not in nomes


# ---------------------------------------------------------------------------
# O método descreve o MESMO mercado que o núcleo
# ---------------------------------------------------------------------------


def test_os_extremos_do_regime_batem_com_a_sessao_do_estado_mercado():
    """Duas contas independentes do mesmo pregão, feitas por módulos que não
    se conhecem: `RegimeDoDia` acumula máxima/mínima de preço, `Sessao`
    também. Divergirem significaria que um dos dois não recebeu o tape
    inteiro — e é justamente a desconexão que este arquivo persegue."""
    montagem = rodar()
    leitura = montagem.sessao.leitura_do_metodo()
    assert leitura is not None
    assert leitura.estrutura.maxima == montagem.sessao.estado.sessao.high
    assert leitura.estrutura.minima == montagem.sessao.estado.sessao.low
    assert leitura.preco == montagem.sessao.estado.ultimo_trade.price


def test_o_delta_do_metodo_bate_com_o_delta_dos_analytics():
    """`MacroMicro` acumula o delta de agressão por um caminho e
    `CumulativeDelta` por outro. O método não inventa um terceiro número —
    e o velocímetro mede exatamente esse contador."""
    montagem = rodar()
    leitura = montagem.sessao.leitura_do_metodo()
    assert leitura is not None
    assert montagem.sessao.delta is not None
    assert leitura.macro_micro.macro.valor == montagem.sessao.delta.delta_sessao
    assert leitura.velocimetro.valor == montagem.sessao.delta.delta_sessao


def test_o_volume_da_linha_azul_bate_com_o_volume_da_sessao():
    """`volume_nao_atribuido` some da razão, nunca do total — o invariante do
    projeto inteiro, conferido aqui contra o `EstadoMercado`."""
    montagem = rodar()
    leitura = montagem.sessao.leitura_do_metodo()
    assert leitura is not None
    sessao = montagem.sessao.estado.sessao
    assert leitura.linha_azul.volume_comprador == sessao.volume_comprador
    assert leitura.linha_azul.volume_vendedor == sessao.volume_vendedor
    assert leitura.linha_azul.volume_nao_atribuido == sessao.volume_nao_atribuido


# ---------------------------------------------------------------------------
# `placar.meta_leitura` — o Placar continua sem assinar o barramento
# ---------------------------------------------------------------------------


def test_o_placar_nao_assina_o_barramento():
    """CONFIRMADO, `Rwm3uzxZhhc`: *"ele lê os sinais que a SG já lê do
    mercado"*. Quem assina é a `SessaoFluxo`, que monta os votos e os entrega
    — o placar não tem leitura própria do mercado, e ligá-lo ao barramento
    faria dele outro objeto, com o mesmo nome."""
    montagem = montar(config(n=1))
    for assinantes in montagem.barramento._assinantes.values():
        for a in assinantes:
            dono = getattr(a.callback, "__self__", None)
            assert not isinstance(dono, Placar)
    assert montagem.sessao.metodo is not None
    assert isinstance(montagem.sessao.metodo.placar, Placar)


def test_quem_vota_e_escolha_declarada_de_quem_monta():
    """A ferramenta original soma até cinco fontes; o produto sustenta quatro
    e deixa a escolha visível na configuração, não embutida no código."""
    cfg = config(
        n=300,
        metodologia=ConfigMetodologia(
            fontes_placar=(FontePlacar.ESTRUTURA, FontePlacar.MACRO_MICRO)
        ),
    )
    leitura = rodar(cfg).sessao.leitura_do_metodo()
    assert leitura is not None
    assert leitura.placar.total_fontes == 2
    assert {nome for nome, _ in leitura.votos} == {"estrutura", "macro_micro"}


# ---------------------------------------------------------------------------
# Ordem de entrega — a quarta seta de `app/config.py`
# ---------------------------------------------------------------------------


def _nomes(barramento) -> list[str]:
    return [a.callback.__name__ for a in barramento._assinantes[Trade]]


def _posicoes(barramento) -> dict[str, int]:
    # Vários analytics compartilham o nome `_ao_trade`; o índice guardado é o
    # do ÚLTIMO deles, que é o que interessa às comparações abaixo.
    return {nome: i for i, nome in enumerate(_nomes(barramento))}


def test_o_metodo_entrega_depois_do_motor_e_antes_da_contagem():
    montagem = montar(config(n=10))
    nomes = _nomes(montagem.barramento)
    pos = _posicoes(montagem.barramento)
    assert pos["_ao_trade_motor"] < pos["_ao_trade_metodo"]
    assert pos["_ao_trade_metodo"] < pos["_contar_trade"]
    assert pos["_ao_trade_montar_retrato"] == len(nomes) - 1
    assert nomes.count("_ao_trade_metodo") == 1


def test_a_virada_preserva_a_posicao_do_metodo_na_cadeia():
    """`LeitorMetodo` é zerado no lugar (grupo (a)), não recriado — então nem
    a assinatura nem a posição dele podem mudar na virada."""
    montagem = montar(config(n=10))
    antes = _nomes(montagem.barramento)
    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)
    depois_nomes = _nomes(montagem.barramento)
    depois = _posicoes(montagem.barramento)
    assert len(depois_nomes) == len(antes)
    assert depois["_ao_trade_motor"] < depois["_ao_trade_metodo"]
    assert depois["_ao_trade_metodo"] < depois["_contar_trade"]


def test_a_sonda_entre_o_motor_e_a_contagem_ve_o_retrato_de_agora():
    """O motivo pelo qual a faixa 45 existe.

    Um painel lê `SessaoFluxo` uma vez por quadro e desenha o estágio do
    motor ao lado do placar do método. Se o método entregasse depois da
    contagem — ou fosse consumido antes de rodar —, o retrato visível seria o
    do trade ANTERIOR, e a tela explicaria o motor de agora com o método de
    antes. A sonda entra na faixa da saída e exige que os dois já descrevam o
    mesmo trade.
    """
    montagem = montar(config(n=1))
    sessao = montagem.sessao
    vistos: list[tuple[int, int]] = []

    def sonda(trade: Trade) -> None:
        leitura = sessao.leitura_do_metodo()
        assert leitura is not None
        vistos.append((leitura.timestamp_ns, trade.timestamp_ns))

    montagem.barramento.assinar(Trade, sonda, prioridade=PRIORIDADE_SAIDA)

    for i in range(1, 6):
        montagem.barramento.publicar(
            Trade(i * 1_000_000, SYMBOL, 10_000 + i, 4, AgressorSide.BUY, f"t{i}")
        )
    assert len(vistos) == 5
    assert all(a == b for a, b in vistos), vistos


def test_um_consumidor_antes_da_faixa_45_ainda_nao_ve_o_trade_corrente():
    """CONTROLE do teste acima: a igualdade não é trivial.

    Uma sonda logo antes do método vê o retrato do trade ANTERIOR — é
    exatamente a tela costurada que a faixa 45 evita para quem lê depois.
    """
    montagem = montar(config(n=1))
    sessao = montagem.sessao
    vistos: list[tuple[int, int]] = []

    def sonda(trade: Trade) -> None:
        leitura = sessao.leitura_do_metodo()
        if leitura is not None:
            vistos.append((leitura.timestamp_ns, trade.timestamp_ns))

    montagem.barramento.assinar(Trade, sonda, prioridade=PRIORIDADE_MOTOR)

    for i in range(1, 6):
        montagem.barramento.publicar(
            Trade(i * 1_000_000, SYMBOL, 10_000 + i, 4, AgressorSide.BUY, f"t{i}")
        )
    assert vistos, "a sonda nunca viu retrato — o teste passaria trivialmente"
    assert all(a < b for a, b in vistos), vistos


# ---------------------------------------------------------------------------
# Virada de sessão
# ---------------------------------------------------------------------------


def test_a_virada_de_sessao_zera_o_metodo_dentro_do_pipeline():
    montagem = rodar(config(n=500))
    sessao = montagem.sessao
    antes = sessao.leitura_do_metodo()
    assert antes is not None and antes.estrutura.maxima is not None

    sessao.iniciar_nova_sessao(timestamp_ns=10**18)
    assert sessao.leitura_do_metodo() is None

    montagem.barramento.publicar(
        Trade(10**18, SYMBOL, 1, 7, AgressorSide.SELL, "novo")
    )
    depois = sessao.leitura_do_metodo()
    assert depois is not None
    assert depois.sequencia == 1
    assert depois.estrutura.maxima == 1, "a maxima de ontem sobreviveu"
    assert depois.macro_micro.macro.valor == -7
    # os contadores da EXECUÇÃO, ao contrário, não zeram (política declarada
    # em `Contadores`)
    assert sessao.contadores.n_trades_metodo == 501


def test_o_metodo_continua_publicando_depois_da_virada():
    """Simétrico de `test_o_pipeline_continua_inteiro_depois_da_virada`: zerar
    não pode significar emudecer."""
    montagem = rodar(config(n=300))
    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    from fluxopro.app.montagem import criar_fonte

    fonte_2 = criar_fonte(config(seed=99, n=300), montagem.barramento)
    fonte_2.iniciar()
    montagem.sessao.finalizar()

    leitura = montagem.sessao.leitura_do_metodo()
    assert leitura is not None
    assert leitura.sequencia == 300
    assert isinstance(leitura, LeituraMetodo)


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------


def test_a_calibracao_da_metodologia_chega_aos_componentes():
    """Config não é decoração — o objeto configurado é o que a peça recebe."""
    cfg = config(
        n=10,
        metodologia=ConfigMetodologia(
            linha_azul=ConfigLinhaAzul(volume_minimo_ancoragem=999_999),
            placar=ConfigPlacar(diferenca_goleada=2),
            risco=ConfigRisco(contratos_mao_cheia=8),
        ),
    )
    metodo = montar(cfg).sessao.metodo
    assert metodo is not None
    assert metodo.linha_azul.config.volume_minimo_ancoragem == 999_999
    assert metodo.placar.config.diferenca_goleada == 2
    assert metodo.risco.tamanho(ModoTamanho.MEIA_MAO) == 4  # "metade do lote"


def test_config_operacao_nao_redigita_o_default_da_metodologia():
    assert ConfigOperacao().metodologia == ConfigMetodologia()


# ---------------------------------------------------------------------------
# A recusa: risco não é automático
# ---------------------------------------------------------------------------


def test_o_pipeline_nao_alimenta_o_gestor_de_risco():
    """`risco.gatilho_de_tamanho` é AUSENTE NA FONTE: *"o critério é
    qualitativo e depende de julgamento visual combinado"*. Depois de 2.000
    eventos o gestor não sabe de região nenhuma, porque ninguém operou — e o
    retrato publicado não tem campo de risco para a UI ler por engano.
    """
    montagem = rodar()
    metodo = montagem.sessao.metodo
    assert metodo is not None
    assert metodo.risco.regioes_rastreadas == 0
    assert metodo.risco.regioes_bloqueadas == ()

    leitura = montagem.sessao.leitura_do_metodo()
    assert leitura is not None
    assert not hasattr(leitura, "risco")
    assert not hasattr(leitura, "qualidade_regiao")

    # o gestor só passa a saber de algo quando UMA PESSOA registra um desfecho
    metodo.risco.registrar_resultado(10_000, ResultadoOperacao.STOP)
    assert metodo.risco.regioes_rastreadas == 1
    decisao = metodo.risco.avaliar(10_000, QualidadeRegiao.BOA)
    assert decisao.permitida and decisao.modo is ModoTamanho.MAO_CHEIA
