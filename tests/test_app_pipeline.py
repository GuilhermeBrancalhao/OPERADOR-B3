"""O teste de fumaça do produto inteiro: pipeline completo, ponta a ponta.

`criticas/nucleo_r2.md:371-372` registrou que `MotorSinais` e `InferidorMBP`
nunca tinham sido importados por módulo de produção nenhum — as peças estavam
verdes e o sistema jamais rodara inteiro. Estes testes são o contrário disso:
rodam a cadeia completa sobre o simulador com seed fixa e exigem que ela
produza sinais e detecções, sem exceção, de forma determinística.

## Como um elo desligado é detectado

Não basta afirmar "está tudo ligado". Cada teste positivo aqui tem um
**controle** que rompe o elo e exige que a mesma verificação falhe:

| elo | invariante | controle que o rompe |
|---|---|---|
| tape -> todas as peças | contadores por elo iguais | `test_severar_qualquer_elo_derruba_a_verificacao` |
| InferidorMBP -> LivroMBO | `n_ordem_eventos > 0` | `test_sem_microestrutura_nao_nasce_ordem_alguma` |
| LivroMBO -> detectores | detecções ESCORA existem | idem |
| trades -> MotorSinais | `n_sinais_emitidos > 0` | `test_sem_motor_nenhum_sinal_e_emitido` |
| seed -> saída | sequência idêntica | `test_seed_diferente_muda_a_sequencia` |

Sem o controle, um teste de determinismo passaria trivialmente sobre uma
sequência vazia, e um `n_ordem_eventos > 0` não provaria que é o inferidor
quem os produz.
"""

from __future__ import annotations

import io

import pytest

from fluxopro.app.config import ConfigOperacao, ConfigSimulador
from fluxopro.app.montagem import Montagem, montar
from fluxopro.app.saida import ConsoleFluxo
from fluxopro.app.sessao_fluxo import DeteccaoAnotada, SessaoFluxo
from fluxopro.core.eventos import AgressorSide, BookDelta, BookSnapshot, Trade
from fluxopro.microestrutura.detectores import TipoDeteccao
from fluxopro.microestrutura.eventos_mbo import CONFIANCA_OBSERVADO, FonteMicro
from fluxopro.motor.sinais import EstagioSinal, Sinal

SYMBOL = "WDOV26"
SEED = 42
N_EVENTOS = 2_000

# Tipos que SÓ podem existir se o `LivroMBO` tiver sido alimentado pelo
# `InferidorMBP` — nenhum deles lê o tape diretamente.
TIPOS_DE_LIVRO = {
    TipoDeteccao.ESCORA,
    TipoDeteccao.ICEBERG,
    TipoDeteccao.LIQUIDEZ_FANTASMA,
}


def config(seed: int = SEED, n: int = N_EVENTOS, **kwargs) -> ConfigOperacao:
    base = dict(symbol=SYMBOL, simulador=ConfigSimulador(seed=seed, n_eventos=n))
    base.update(kwargs)
    return ConfigOperacao(**base)  # type: ignore[arg-type]


class Coletor:
    def __init__(self) -> None:
        self.sinais: list[Sinal] = []
        self.deteccoes: list[DeteccaoAnotada] = []

    def ao_sinal(self, sinal: Sinal) -> None:
        self.sinais.append(sinal)

    def ao_deteccao(self, anotada: DeteccaoAnotada) -> None:
        self.deteccoes.append(anotada)

    def assinatura(self) -> list[tuple]:
        """Sequência canônica da passada — o que "mesma seed, mesma saída"
        quer dizer. Inclui a EVIDÊNCIA numérica, não só o rótulo: dois
        pipelines podem concordar no estágio e discordar no porquê."""
        itens: list[tuple] = []
        for s in self.sinais:
            itens.append(
                (
                    "S",
                    s.timestamp_ns,
                    s.estagio.value,
                    s.direcao.value if s.direcao else None,
                    round(float(s.evidencia.get("dominancia", 0.0)), 9),
                    s.evidencia.get("magnitude"),
                )
            )
        for d in self.deteccoes:
            itens.append(
                (
                    "D",
                    d.deteccao.timestamp_ns,
                    d.deteccao.tipo.value,
                    d.deteccao.side.value,
                    d.deteccao.price,
                    round(d.confianca_efetiva, 9),
                    tuple(sorted((k, str(v)) for k, v in d.deteccao.evidencia.items())),
                )
            )
        return itens


def rodar(cfg: ConfigOperacao | None = None) -> tuple[Montagem, Coletor]:
    cfg = cfg if cfg is not None else config()
    coletor = Coletor()
    montagem = montar(cfg, ao_sinal=coletor.ao_sinal, ao_deteccao=coletor.ao_deteccao)
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    return montagem, coletor


def verificar_cadeia_ligada(sessao: SessaoFluxo, coletor: Coletor) -> None:
    """As invariantes de "o pipeline inteiro rodou".

    Extraída como função para que o teste positivo e o teste-controle usem
    exatamente a mesma verificação — se o controle usasse uma checagem mais
    fraca, ele não provaria que o positivo pega a desconexão.
    """
    c = sessao.contadores
    assert c.n_trades_bus > 0, "a fonte nao publicou trade nenhum"
    # todo elo recebeu o MESMO tape
    assert c.n_trades_perfil_sessao == c.n_trades_bus
    assert c.n_trades_micro == c.n_trades_bus
    assert c.n_trades_motor == c.n_trades_bus
    assert c.n_snapshots_micro == c.n_snapshots_bus
    assert c.n_deltas_micro == c.n_deltas_bus
    # a ponte MBP->MBO produziu ordens, e elas estao marcadas como inferidas
    assert c.n_ordem_eventos > 0, "InferidorMBP nao alimentou o LivroMBO"
    assert c.n_ordem_eventos_inferidos == c.n_ordem_eventos
    # o motor produziu sinal, e chegou a sair de NENHUM em algum momento
    assert c.n_sinais_emitidos > 0, "MotorSinais nao emitiu sinal"
    assert any(s.estagio is not EstagioSinal.NENHUM for s in coletor.sinais)
    # os detectores produziram deteccao, das duas procedencias
    assert c.n_deteccoes > 0, "nenhum detector disparou"
    tipos = {d.deteccao.tipo for d in coletor.deteccoes}
    assert tipos & TIPOS_DE_LIVRO, "nenhuma deteccao veio do LivroMBO"
    assert any(not d.inferida for d in coletor.deteccoes), "nenhuma deteccao do tape"


# ---------------------------------------------------------------------------
# O teste que mais importa
# ---------------------------------------------------------------------------


def test_pipeline_completo_roda_e_produz_sinais_e_deteccoes():
    montagem, coletor = rodar()
    verificar_cadeia_ligada(montagem.sessao, coletor)


def test_mesma_seed_produz_a_mesma_sequencia_exata():
    """Determinismo de ponta a ponta — o teste de fumaça do produto inteiro.

    Compara a sequência canônica inteira (timestamp, estágio, direção,
    dominância, magnitude, evidência de cada detecção), não um resumo: um
    resumo esconderia divergência que se compensa.
    """
    _, primeira = rodar()
    _, segunda = rodar()
    assert primeira.assinatura() == segunda.assinatura()
    assert primeira.assinatura(), "sequencia vazia — o teste passaria trivialmente"


def test_seed_diferente_muda_a_sequencia():
    """CONTROLE do teste acima: prova que a igualdade não é trivial."""
    _, a = rodar(config(seed=SEED))
    _, b = rodar(config(seed=SEED + 1))
    assert a.assinatura() != b.assinatura()


def test_contadores_de_cada_elo_batem_com_o_barramento():
    montagem, _ = rodar()
    c = montagem.sessao.contadores
    assert c.n_trades_bus == N_EVENTOS
    assert c.n_snapshots_bus == N_EVENTOS  # o simulador publica book a cada passo
    assert c.n_eventos_bus == 2 * N_EVENTOS
    assert (
        c.n_trades_perfil_sessao
        == c.n_trades_micro
        == c.n_trades_motor
        == c.n_trades_bus
    )


# ---------------------------------------------------------------------------
# Controles: romper um elo tem de derrubar a verificação
# ---------------------------------------------------------------------------


def _severar(barramento, tipo, nome_metodo: str) -> None:
    """Remove do barramento a assinatura de um método — simula o elo desligado."""
    lista = barramento._assinantes[tipo]
    restantes = [a for a in lista if a.callback.__name__ != nome_metodo]
    assert len(restantes) < len(lista), f"nao havia assinatura {nome_metodo} em {tipo}"
    barramento._assinantes[tipo] = restantes


@pytest.mark.parametrize(
    "tipo, metodo",
    [
        (Trade, "_ao_trade_micro"),
        (BookSnapshot, "_ao_snapshot_micro"),
        (Trade, "_ao_trade_motor"),
        (Trade, "_ao_trade_perfil_sessao"),
        (Trade, "_ao_trade_detectores_tape"),
    ],
)
def test_severar_qualquer_elo_derruba_a_verificacao(tipo, metodo):
    """O teste sobre os testes: desconectar QUALQUER peça precisa ser visível.

    Se algum destes parâmetros passasse sem levantar `AssertionError`, seria
    prova de que `verificar_cadeia_ligada` é cega àquele elo — e o teste
    positivo estaria dando uma garantia que não tem.
    """
    coletor = Coletor()
    montagem = montar(config(), ao_sinal=coletor.ao_sinal, ao_deteccao=coletor.ao_deteccao)
    _severar(montagem.barramento, tipo, metodo)
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    with pytest.raises(AssertionError):
        verificar_cadeia_ligada(montagem.sessao, coletor)


def test_severar_o_ouvinte_do_livro_apaga_as_deteccoes_de_livro():
    """O elo `LivroMBO -> detectores` não passa pelo barramento (é
    `assinar_evento`), então precisa do seu próprio controle."""
    coletor = Coletor()
    montagem = montar(config(), ao_sinal=coletor.ao_sinal, ao_deteccao=coletor.ao_deteccao)
    assert montagem.sessao.livro is not None
    montagem.sessao.livro._ouvintes.clear()
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()

    assert montagem.sessao.contadores.n_ordem_eventos == 0
    tipos = {d.deteccao.tipo for d in coletor.deteccoes}
    assert not (tipos & TIPOS_DE_LIVRO)
    with pytest.raises(AssertionError):
        verificar_cadeia_ligada(montagem.sessao, coletor)


def test_sem_microestrutura_nao_nasce_ordem_alguma():
    montagem, coletor = rodar(config(ligar_microestrutura=False))
    assert montagem.sessao.contadores.n_ordem_eventos == 0
    assert not ({d.deteccao.tipo for d in coletor.deteccoes} & TIPOS_DE_LIVRO)
    # e o resto do pipeline continua funcionando — desligar não é quebrar
    assert montagem.sessao.contadores.n_sinais_emitidos > 0


def test_sem_motor_nenhum_sinal_e_emitido():
    montagem, coletor = rodar(config(ligar_motor=False))
    assert montagem.sessao.contadores.n_sinais_emitidos == 0
    assert coletor.sinais == []
    assert montagem.sessao.contadores.n_deteccoes > 0


def test_sem_detectores_de_tape_sobram_so_as_deteccoes_inferidas():
    montagem, coletor = rodar(config(ligar_detectores_tape=False))
    assert coletor.deteccoes, "as deteccoes de livro deveriam continuar"
    assert all(d.inferida for d in coletor.deteccoes)


# ---------------------------------------------------------------------------
# Observado × inferido
# ---------------------------------------------------------------------------


def test_deteccao_vinda_do_livro_sintetico_nunca_sai_como_observada():
    """A virtude declarada do projeto, verificada na saída.

    Em fonte simulador/MT5 o `LivroMBO` é inteiramente montado pelo
    `InferidorMBP`; nenhuma detecção sobre ele é fato. `detectores.py` emite
    `confianca=1.0` fixo, então a propagação é feita na fronteira (ver
    `sessao_fluxo.DeteccaoAnotada`) — este teste é o que garante que ela não
    some numa refatoração.
    """
    _, coletor = rodar()
    de_livro = [d for d in coletor.deteccoes if d.deteccao.tipo in TIPOS_DE_LIVRO]
    assert de_livro
    for d in de_livro:
        assert d.fonte is FonteMicro.MBP_INFERIDO
        assert d.confianca_efetiva < CONFIANCA_OBSERVADO
        assert d.inferida
        # e o número não é arbitrário: é a confiança do evento que a disparou
        assert 0.0 < d.confianca_efetiva <= 1.0


def test_deteccao_vinda_do_tape_sai_como_observada():
    _, coletor = rodar()
    do_tape = [d for d in coletor.deteccoes if d.deteccao.tipo not in TIPOS_DE_LIVRO]
    assert do_tape
    for d in do_tape:
        assert d.fonte is FonteMicro.MBO
        assert d.confianca_efetiva == CONFIANCA_OBSERVADO
        assert not d.inferida


def test_toda_deteccao_carrega_evidencia_nao_vazia():
    """Sem evidência, a promessa de auditoria não vale nada."""
    _, coletor = rodar()
    for d in coletor.deteccoes:
        assert d.deteccao.evidencia, f"{d.deteccao.tipo} sem evidencia"


def test_todo_sinal_carrega_a_evidencia_da_condicao_1():
    _, coletor = rodar()
    for s in coletor.sinais:
        assert "dominancia" in s.evidencia
        assert "magnitude_relativa" in s.evidencia
        assert "estagio_bruto" in s.evidencia


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------


def test_virada_de_sessao_zera_acumuladores_e_a_distribuicao_do_motor():
    """`MotorSinais` não expõe `iniciar_nova_sessao` e carrega o reservoir da
    magnitude do PRÓPRIO DIA. A montagem o recria — este teste prende esse
    comportamento (ver `SessaoFluxo.iniciar_nova_sessao`)."""
    montagem, _ = rodar()
    sessao = montagem.sessao
    assert sessao.estado.sessao.volume_total > 0
    assert sessao.perfil_sessao.volume_total > 0
    motor_antigo = sessao.motor

    sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    assert sessao.estado.sessao.volume_total == 0
    assert sessao.estado.sessao.high is None
    assert sessao.perfil_sessao.volume_total == 0
    assert sessao.delta is not None and sessao.delta.delta_sessao == 0
    assert sessao.vwap is not None and sessao.vwap.vwap_sessao() == 0.0
    assert sessao.agressao is not None and sessao.agressao.volume_total_janela == 0
    assert sessao.motor is not motor_antigo
    assert sessao.motor is not None
    assert sessao.motor.estagio_atual is EstagioSinal.NENHUM
    # e o motor novo lê o perfil NOVO, não o da sessão que acabou
    assert sessao.motor._vp is sessao.perfil_sessao
    # o histórico fechado sobrevive (mesma política do núcleo)
    assert sessao.estado.candles_fechados


def test_virada_de_sessao_zera_a_calibracao_do_gate_winfut():
    """O achado de `criticas/nucleo_r3.md` §C.4, fechado na camada de app.

    O crítico mediu o percentil de magnitude do `MotorSinais` sobrevivendo
    intacto a um salto de 24h no timestamp — o gate do caso WINFUT ficava
    calibrado por um dia que já tinha acabado. Aqui a virada tem de zerar a
    amostra, não só o estágio.
    """
    montagem, _ = rodar()
    motor = montagem.sessao.motor
    assert motor is not None
    assert len(motor._reservatorio) > 0

    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    novo = montagem.sessao.motor
    assert novo is not None and novo is not motor
    assert novo._reservatorio == []
    assert novo._n_visto == 0


def test_virada_de_sessao_reabre_os_niveis_ja_sinalizados():
    """Segundo achado da §C.4: o dedup de `DetectorEscora` /
    `DetectorIcebergPorRecarga` nunca era limpo, então um nível sinalizado no
    dia 1 ficaria MUDO para sempre.

    A intenção do teste não mudou; a API do detector, sim. O `set` de
    `_ja_sinalizado` — que crescia um item por nível ao longo do pregão e é o
    defeito #4 dos cinco — virou o `_MapaProcedencia` com teto, lido por
    `n_chaves_rastreadas` / `esta_sinalizado`. O que continua sendo verificado
    é exatamente o mesmo: no dia 1 há nível sinalizado, e depois da virada não
    há mais nenhum.
    """
    montagem, coletor = rodar()
    escora = montagem.sessao.det_escora
    assert escora is not None
    assert escora.n_chaves_rastreadas > 0, "o tape deveria ter alimentado a escora"
    de_escora = [
        d for d in coletor.deteccoes if d.deteccao.tipo is TipoDeteccao.ESCORA
    ]
    assert de_escora, "o tape deveria ter sinalizado algum nivel"
    # NOTA (conserto do §A.5 da R4): a pré-condição "o nível que emitiu ainda
    # está marcado no fim do tape" deixou de ser verdade por construção. O
    # dedup passou a expirar por TEMPO (`JANELA_EPISODIO_NS`, 30 s) e este tape
    # sintético cobre ~386 s de pregão — um nível que emitiu no primeiro minuto
    # e depois ficou quieto SAI do dedup, e sair é o comportamento correto.
    # A intenção do teste (dia 1 tem estado, a virada limpa o estado) segue
    # presa por `n_chaves_rastreadas > 0` acima e pelas asserções abaixo; o
    # contrato "nível sinalizado fica marcado, virada devolve o direito de
    # emitir" está preso de forma determinística em
    # `tests/test_micro_detectores.py::test_virada_reabre_o_dedup_dos_detectores_de_livro`.

    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    nova = montagem.sessao.det_escora
    assert nova is not None and nova is not escora
    assert nova.n_chaves_rastreadas == 0
    for d in de_escora:
        assert not nova.esta_sinalizado((d.deteccao.side, d.deteccao.price))
    # e o reset no lugar (sem trocar a instância) faz a mesma coisa — é o
    # caminho de quem segura a referência do detector, ver `detectores.py`
    escora.iniciar_nova_sessao()
    assert escora.n_chaves_rastreadas == 0


def test_virada_de_sessao_recria_o_livro_reconstruido():
    """O `LivroMBO` acumula histórico POR NÍVEL cuja definição é "desde que
    este nível nasceu" (`n_reposicoes`, `qty_exibida_max`). Levar isso para o
    dia seguinte faria a primeira ordem do pregão parecer a terceira reposição
    de uma escora de ontem."""
    montagem, _ = rodar()
    sessao = montagem.sessao
    livro_antigo = sessao.livro
    inferidor_antigo = sessao.inferidor
    assert livro_antigo is not None and inferidor_antigo is not None

    sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    assert sessao.livro is not livro_antigo
    assert sessao.inferidor is not inferidor_antigo
    # e o livro novo está religado: o inferidor novo aponta para ele, e os
    # eventos dele voltam a chegar nos detectores
    assert sessao.inferidor.livro is sessao.livro
    assert sessao.livro._ouvintes, "o livro novo ficou sem ouvinte — elo perdido"


def test_o_pipeline_continua_inteiro_depois_da_virada():
    """A virada não pode ser um lugar onde o wiring se perde em silêncio:
    depois dela, rodar mais tape tem de produzir tudo de novo."""
    coletor_1 = Coletor()
    montagem = montar(config(), ao_sinal=coletor_1.ao_sinal, ao_deteccao=coletor_1.ao_deteccao)
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    verificar_cadeia_ligada(montagem.sessao, coletor_1)

    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)

    # segunda sessão no MESMO processo, mesmo barramento, fonte nova
    coletor_2 = Coletor()
    montagem.sessao._ao_sinal = coletor_2.ao_sinal
    montagem.sessao._ao_deteccao = coletor_2.ao_deteccao
    from fluxopro.app.montagem import criar_fonte

    fonte_2 = criar_fonte(
        config(seed=99, n=N_EVENTOS), montagem.barramento
    )
    fonte_2.iniciar()
    montagem.sessao.finalizar()

    assert coletor_2.sinais, "o motor parou de emitir depois da virada"
    assert coletor_2.deteccoes, "os detectores pararam depois da virada"
    tipos = {d.deteccao.tipo for d in coletor_2.deteccoes}
    assert tipos & TIPOS_DE_LIVRO, "a ponte MBP->MBO nao voltou depois da virada"


def test_componentes_sem_reset_estao_declarados():
    """O único que esta camada NÃO consegue resetar por troca de instância
    está nomeado no código, não escondido — `Barramento` não tem
    `desassinar`, então trocar a instância dobraria a contagem.
    `RankingCorretoras` ganhou `iniciar_nova_sessao()` (fluxopro/analytics/
    brokers.py) e saiu desta lista: não precisa mais de troca de instância,
    é zerado igual aos demais do grupo (a)."""
    assert SessaoFluxo.SEM_RESET_POSSIVEL == ("FootprintPorTimeframe",)
    montagem = montar(config(n=10))
    for nome in SessaoFluxo.SEM_RESET_POSSIVEL:
        peca = {
            "FootprintPorTimeframe": montagem.sessao.footprint,
        }[nome]
        assert peca is not None
        assert not hasattr(peca, "iniciar_nova_sessao")
        assert not hasattr(peca, "nova_sessao")
    assert not hasattr(montagem.barramento, "desassinar")

    assert hasattr(montagem.sessao.brokers, "iniciar_nova_sessao")


def test_iniciar_nova_sessao_zera_o_ranking_de_corretoras():
    """`RankingCorretoras` mistura sessões desde a fábrica (`janela_ns=None`
    acumula para sempre) — a virada de dia tem de zerá-lo de verdade.
    `SimuladorWDO` não preenche `buyer_broker`/`seller_broker`, então
    publica-se um trade sintético direto no barramento da sessão para
    popular o ranking antes da virada."""
    montagem = montar(config(n=1))
    brokers = montagem.sessao.brokers
    assert brokers is not None

    montagem.barramento.publicar(
        Trade(
            timestamp_ns=1,
            symbol=SYMBOL,
            price=100,
            qty=10,
            side_agressor=AgressorSide.BUY,
            trade_id="sintetico-1",
            buyer_broker="XP",
            seller_broker="BTG",
        )
    )
    assert brokers.ranking_por_volume() != []
    instancia_antes = montagem.sessao.brokers

    montagem.sessao.iniciar_nova_sessao()

    assert brokers.ranking_por_volume() == []
    # a instância não trocou (é o mesmo objeto, só o estado interno zerou) --
    # RankingCorretoras saiu de SEM_RESET_POSSIVEL porque nao precisa mais
    # de troca de instancia.
    assert montagem.sessao.brokers is instancia_antes


def test_finalizar_drena_o_inferidor():
    """Sem o drain, quedas de quantidade do fim do replay ficariam pendentes
    para sempre — nunca virariam cancelamento inferido."""
    coletor = Coletor()
    montagem = montar(config(), ao_deteccao=coletor.ao_deteccao)
    montagem.fonte.iniciar()
    inferidor = montagem.sessao.inferidor
    assert inferidor is not None
    antes = len(inferidor._pendentes)
    montagem.sessao.finalizar()
    assert len(inferidor._pendentes) == 0
    assert antes >= 0  # o valor exato depende do tape; o que importa e' zerar


def test_a_sessao_ignora_evento_de_outro_simbolo():
    montagem = montar(config(n=10))
    montagem.fonte.iniciar()
    antes = montagem.sessao.contadores.n_trades_bus
    from fluxopro.core.eventos import AgressorSide

    montagem.barramento.publicar(
        Trade(10**12, "OUTRO", 1, 1, AgressorSide.BUY, "x")
    )
    assert montagem.sessao.contadores.n_trades_bus == antes


def test_taxa_de_eventos_e_positiva_e_congela_no_finalizar():
    montagem, _ = rodar(config(n=500))
    taxa = montagem.sessao.taxa_eventos_s()
    assert taxa > 0
    assert montagem.sessao.taxa_eventos_s() == taxa  # congelada por finalizar()


# ---------------------------------------------------------------------------
# A saída, no pipeline de verdade
# ---------------------------------------------------------------------------


def test_o_console_imprime_tudo_o_que_a_sessao_produziu():
    buffer = io.StringIO()
    cfg = config()
    console = ConsoleFluxo(cfg.price_grid(), stream=buffer)
    montagem = montar(cfg, ao_sinal=console.ao_sinal, ao_deteccao=console.ao_deteccao)
    console.cabecalho(montagem.sessao)
    montagem.fonte.iniciar()
    montagem.sessao.finalizar()
    console.resumo(montagem.sessao)

    texto = buffer.getvalue()
    c = montagem.sessao.contadores
    assert "FLUXO PRO" in texto
    assert "RESUMO DA SESSAO" in texto
    assert f"eventos processados : {c.n_eventos_bus}" in texto
    assert "SINAL" in texto and "DETECCAO" in texto
    assert "[OBS]" in texto and "[INF" in texto


# ---------------------------------------------------------------------------
# A fronteira observado × inferido, depois que a propagação passou a ser real
# ---------------------------------------------------------------------------


def test_a_deteccao_de_livro_carrega_a_cadeia_inteira_e_nao_so_o_gatilho():
    """`SessaoFluxo._ligar_livro` tem de assinar os detectores ANTES de
    `_ao_ordem_evento` — senão o mecanismo de procedência existe e fica inerte.

    O modo de falha é silencioso: sem `acompanhar`, todo `verificar` roda sobre
    cadeia vazia, as detecções saem `DESCONHECIDA` com confiança 1,0, e nenhum
    outro teste desta suíte reclama (a fronteira ainda capa pelo gatilho). Por
    isso a asserção é sobre a EVIDÊNCIA, não só sobre o número.
    """
    _, coletor = rodar()
    de_livro = [d for d in coletor.deteccoes if d.deteccao.tipo in TIPOS_DE_LIVRO]
    assert de_livro
    for d in de_livro:
        ev = d.deteccao.evidencia
        assert ev["procedencia"] == "INFERIDA", ev
        assert ev["fonte"] == FonteMicro.MBP_INFERIDO.value
        assert ev["n_eventos_procedencia"] >= 1, ev
        assert d.deteccao.confianca < CONFIANCA_OBSERVADO
    # A asserção forte é sobre o CONJUNTO, e não sobre cada detecção. Sem
    # `acompanhar`, TODA cadeia teria no máximo o evento gatilho (comprimento
    # 1) e este máximo seria 1 — é isso que prende a fiação. Exigir > 1 de cada
    # detecção deixou de ser válido depois que o dedup passou a expirar por
    # tempo (§A.5 da R4): uma cadeia começa do zero a cada episódio novo, então
    # a primeira detecção de um episódio pode legitimamente ter um evento só.
    assert max(d.deteccao.evidencia["n_eventos_procedencia"] for d in de_livro) > 1, (
        "nenhuma cadeia passou de 1 evento: os detectores nao estao seguindo o livro"
    )


def test_a_fronteira_nao_penaliza_a_mesma_incerteza_duas_vezes():
    """`confianca_efetiva` é `min`, não produto — com a cadeia viva, o produto
    cobraria a incerteza do gatilho uma segunda vez.

    Números explícitos: cadeia 0,55 e gatilho 0,55 (o gatilho JÁ está na
    cadeia, porque `_ligar_livro` assina os detectores primeiro). `min` dá
    0,55; produto daria 0,3025 e transformaria detecção legítima em ruído.
    """
    from fluxopro.microestrutura.detectores import Deteccao
    from fluxopro.core.eventos import Side

    montagem, coletor = rodar()
    sessao = montagem.sessao
    coletadas: list[DeteccaoAnotada] = []
    sessao._ao_deteccao = coletadas.append

    deteccao = Deteccao(
        timestamp_ns=1,
        symbol=sessao.config.symbol,
        tipo=TipoDeteccao.ESCORA,
        side=Side.BUY,
        price=5000,
        confianca=0.55,
        evidencia={"procedencia": "INFERIDA"},
    )
    sessao._emitir_deteccao(deteccao, FonteMicro.MBP_INFERIDO, 0.55)
    assert coletadas[-1].confianca_efetiva == 0.55
    assert coletadas[-1].confianca_efetiva != pytest.approx(0.3025)

    # e continua sendo COTA: detector sem cadeia (1,0) é capado pelo gatilho
    sem_cadeia = Deteccao(
        timestamp_ns=2,
        symbol=sessao.config.symbol,
        tipo=TipoDeteccao.ESCORA,
        side=Side.BUY,
        price=5000,
        confianca=CONFIANCA_OBSERVADO,
        evidencia={"procedencia": "DESCONHECIDA"},
    )
    sessao._emitir_deteccao(sem_cadeia, FonteMicro.MBP_INFERIDO, 0.4)
    assert coletadas[-1].confianca_efetiva == 0.4
    assert coletadas[-1].inferida

    # detecção de tape: gatilho observado, nada é rebaixado
    sessao._emitir_deteccao(sem_cadeia, FonteMicro.MBO, CONFIANCA_OBSERVADO)
    assert coletadas[-1].confianca_efetiva == CONFIANCA_OBSERVADO
    assert not coletadas[-1].inferida


def test_a_confianca_publicada_e_a_do_detector_quando_a_cadeia_esta_viva():
    """Fecha o ciclo: com a fiação certa, a fronteira não altera mais o número
    do detector — a cadeia dele já contém o gatilho."""
    _, coletor = rodar()
    de_livro = [d for d in coletor.deteccoes if d.deteccao.tipo in TIPOS_DE_LIVRO]
    assert de_livro
    for d in de_livro:
        assert d.confianca_efetiva == d.deteccao.confianca


def _ordem_dos_ouvintes(sessao: SessaoFluxo) -> tuple[int, list[int]]:
    """Posição de `_ao_ordem_evento` e dos `observar` dos 3 detectores."""
    ouvintes = sessao.livro._ouvintes
    pos_verificar = -1
    pos_observar = []
    for i, cb in enumerate(ouvintes):
        dono = getattr(cb, "__self__", None)
        nome = getattr(cb, "__name__", "")
        if dono is sessao and nome == "_ao_ordem_evento":
            pos_verificar = i
        elif nome == "observar" and dono in (
            sessao.det_escora, sessao.det_iceberg, sessao.det_liquidez_fantasma
        ):
            pos_observar.append(i)
    return pos_verificar, pos_observar


def test_os_detectores_assinam_o_livro_antes_do_verificar():
    """A ordem de assinatura é contrato, não acaso — ver `_ligar_livro`.

    `LivroMBO._emitir` percorre `_ouvintes` na ordem de registro. Se
    `_ao_ordem_evento` for registrado antes dos detectores, cada `verificar`
    roda sobre a cadeia SEM o evento gatilho: a procedência fica sempre um
    evento atrasada.

    Este teste é ESTRUTURAL de propósito, e a honestidade sobre o porquê
    importa: a auto-mutação mostrou que inverter a ordem não quebra nenhuma
    asserção de valor, porque a fronteira (`min(detector, gatilho)` em
    `_emitir_deteccao`) resgata o número — o gatilho continua capando por fora.
    Ou seja, o dano é invisível no resultado e real na evidência
    (`n_eventos_procedencia`, e a confiança de uma ordem cujo primeiro evento
    JÁ é o gatilho). Defeito que só aparece na evidência precisa de um teste
    que olhe a estrutura.
    """
    montagem, _ = rodar()
    sessao = montagem.sessao
    pos_verificar, pos_observar = _ordem_dos_ouvintes(sessao)
    assert len(pos_observar) == 3, f"os 3 detectores de livro tem de assinar: {pos_observar}"
    assert pos_verificar > max(pos_observar), (
        f"_ao_ordem_evento (pos {pos_verificar}) assinou antes de um detector "
        f"(pos {pos_observar}): a cadeia fica um evento atrasada"
    )


def test_a_virada_de_sessao_religa_o_livro_na_mesma_ordem():
    """A virada usa a MESMA função de fiação — senão os dois caminhos divergem
    e o dia 2 roda com uma ordem de assinatura que ninguém testou."""
    montagem, _ = rodar()
    montagem.sessao.iniciar_nova_sessao(timestamp_ns=10**18)
    pos_verificar, pos_observar = _ordem_dos_ouvintes(montagem.sessao)
    assert len(pos_observar) == 3
    assert pos_verificar > max(pos_observar)
