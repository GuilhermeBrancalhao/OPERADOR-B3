"""Testes de `fluxopro/metodologia/` — o método dentro do produto.

O que estes testes tentam provar, e o que deliberadamente NÃO fazem:

- Eles afirmam **comportamento observável**: que uma barrigada de 1.000 ticks
  não muda o regime enquanto a mínima segura, que multiplicar todo o fluxo do
  dia por 10 não muda uma única leitura do velocímetro, que N stops em N
  regiões distintas não bloqueiam a região N+1.
- Eles **não** repetem a implementação. Não há teste que confira a fórmula do
  anel de baldes, nem que recalcule `magnitude_relativa` do mesmo jeito que o
  código. Onde a implementação e o teste teriam de dizer a mesma coisa, o
  teste diz uma coisa MAIS FORTE (invariância a escala, em vez de "a razão é
  x/y").
- Três testes afirmam a **disciplina de procedência** em si — que nenhuma
  citação passa de 15 palavras, que `AUSENTE_NA_FONTE` não pode ter citação, e
  que todo default declarado em `regras.PARAMETROS` bate com o default real do
  dataclass. Esse último é o que impede o mapa de auditoria de mentir sem que
  a suíte perceba.
- Um bloco afirma **retenção**, no molde de `tests/test_gravacao_retencao.py`:
  o `len` das coleções de instância tem de responder o mesmo com 1.000 e com
  20.000 eventos. É o critério do docstring de `fluxopro/gravacao/gravador.py`
  ("qual grandeza limita o `len` disto?") virando asserção — sem ele a suíte
  seria incapaz de distinguir a versão O(1) da versão O(eventos).
"""

from __future__ import annotations

import dataclasses

import pytest

from fluxopro.core.eventos import AgressorSide, Candle, Side, Trade
from fluxopro.metodologia import regras as mod_regras
from fluxopro.metodologia.confianca import (
    CitacaoInvalidaError,
    Confianca,
    ParametroCalibravel,
    RegraDocumentada,
)
from fluxopro.metodologia.estrutura import (
    ConfigEstrutura,
    GatilhoEstrutural,
    RegimeDoDia,
    RegimeEstrutural,
)
from fluxopro.metodologia.janela import JanelaMovel
from fluxopro.metodologia.linha_azul import (
    ConfigLinhaAzul,
    ConvencaoLinhaAzul,
    LadoDaLinha,
    LinhaAzul,
)
from fluxopro.metodologia.macro_micro import (
    ConfigMacroMicro,
    Escala,
    EscalasIncomparaveisError,
    MacroMicro,
    MedidaContexto,
    comparar_magnitudes,
)
from fluxopro.metodologia.placar import ConfigPlacar, Placar, VotoPlacar
from fluxopro.metodologia.risco import (
    ConfigRisco,
    GestorRisco,
    ModoTamanho,
    QualidadeRegiao,
    ResultadoOperacao,
    TamanhoNaoConfiguradoError,
)
from fluxopro.metodologia.velocimetro import (
    ConfigVelocimetro,
    EstadoVelocimetro,
    Velocimetro,
)

S = 1_000_000_000  # um segundo em ns
SIMBOLO = "WINV26"


def _trade(ts, price, qty, agressor, symbol=SIMBOLO):
    return Trade(
        timestamp_ns=ts,
        symbol=symbol,
        price=price,
        qty=qty,
        side_agressor=agressor,
        trade_id=f"t{ts}",
    )


# ===========================================================================
# Procedência — a disciplina que dá sentido ao pacote inteiro
# ===========================================================================


def test_toda_regra_publicada_carrega_rotulo_de_confianca():
    """Nenhuma leitura sai deste pacote sem a procedência anexada."""
    leituras = [
        RegimeDoDia().registrar_preco(100, 0),
        Velocimetro().registrar(0, 10),
        Placar().registrar(0, {"macro": VotoPlacar.COMPRA}),
        LinhaAzul(SIMBOLO).ao_trade(_trade(0, 100, 5, AgressorSide.BUY)),
        MacroMicro(SIMBOLO).ao_trade(_trade(0, 100, 5, AgressorSide.BUY)),
        GestorRisco().avaliar(100, QualidadeRegiao.BOA),
    ]
    for leitura in leituras:
        assert leitura.regras, f"{type(leitura).__name__} sem regras anexadas"
        for r in leitura.regras:
            assert isinstance(r, RegraDocumentada)
            assert isinstance(r.confianca, Confianca)
            assert r.secao


def test_ausente_na_fonte_nao_pode_carregar_citacao():
    """Se há citação, a fonte não está ausente — a invariante que dá nome ao
    rótulo. Sem ela, "AUSENTE NA FONTE" viraria só um adjetivo."""
    with pytest.raises(CitacaoInvalidaError):
        RegraDocumentada(
            id="x",
            titulo="x",
            confianca=Confianca.AUSENTE_NA_FONTE,
            secao="s",
            citacao="o autor disse alguma coisa",
            nota="n",
        )
    with pytest.raises(CitacaoInvalidaError):
        RegraDocumentada(
            id="x",
            titulo="x",
            confianca=Confianca.AUSENTE_NA_FONTE,
            secao="s",
        )


def test_confirmado_sem_citacao_e_recusado():
    """CONFIRMADO sem citação seria opinião com cara de evidência."""
    with pytest.raises(CitacaoInvalidaError):
        RegraDocumentada(
            id="x", titulo="x", confianca=Confianca.CONFIRMADO, secao="s"
        )


def test_citacao_longa_demais_e_recusada():
    with pytest.raises(CitacaoInvalidaError):
        RegraDocumentada(
            id="x",
            titulo="x",
            confianca=Confianca.CONFIRMADO,
            secao="s",
            fonte="v",
            citacao=" ".join(["palavra"] * 16),
        )


def test_registro_inteiro_respeita_o_teto_de_citacao():
    for r in mod_regras.REGRAS.values():
        assert len(r.citacao.split()) <= 15, r.id


def test_fonte_que_diverge_obriga_rotulo_impreciso():
    """Dois números para a mesma coisa é a definição operacional de IMPRECISO.

    Este é o teste que impede alguém de cravar 70% (ou 75%) como CONFIRMADO e
    ainda assim listar os dois valores no mapa de auditoria.
    """
    for p in mod_regras.PARAMETROS:
        if p.fonte_diverge:
            assert mod_regras.REGRAS[p.regra_id].confianca is Confianca.IMPRECISO

    # E a validacao do registro pega quem tentar o contrario.
    intruso = ParametroCalibravel(
        nome="ConfigX.y",
        padrao=1,
        valores_na_fonte=(1, 2),
        motivo="dois numeros na fonte",
        regra_id="dominancia.faixas",  # CONFIRMADO — nao pode
    )
    original = mod_regras.PARAMETROS
    mod_regras.PARAMETROS = original + (intruso,)
    try:
        with pytest.raises(CitacaoInvalidaError):
            mod_regras._validar()
    finally:
        mod_regras.PARAMETROS = original


def test_parametro_pendurado_em_regra_recusada_e_barrado():
    """Regra com `implementada=False` e parâmetro de configuração vivo são
    afirmações contraditórias sobre o mesmo id."""
    intruso = ParametroCalibravel(
        nome="ConfigX.z",
        padrao=1,
        valores_na_fonte=(),
        motivo="teste",
        regra_id="maker.formula",  # implementada=False
    )
    original = mod_regras.PARAMETROS
    mod_regras.PARAMETROS = original + (intruso,)
    try:
        with pytest.raises(CitacaoInvalidaError):
            mod_regras._validar()
    finally:
        mod_regras.PARAMETROS = original


def test_defaults_declarados_batem_com_os_defaults_reais():
    """O mapa de auditoria só serve se não puder mentir sem quebrar a suíte.

    `regras.PARAMETROS` diz "o default de ConfigRisco.stops_maximos_por_regiao
    é 3". Se alguém trocar o dataclass e esquecer o registro, o produto passa a
    afirmar uma coisa e fazer outra — e é exatamente isso que este teste pega.
    """
    classes = {
        "ConfigEstrutura": ConfigEstrutura,
        "ConfigVelocimetro": ConfigVelocimetro,
        "ConfigPlacar": ConfigPlacar,
        "ConfigMacroMicro": ConfigMacroMicro,
        "ConfigRisco": ConfigRisco,
        "ConfigLinhaAzul": ConfigLinhaAzul,
    }
    vistos = 0
    for p in mod_regras.PARAMETROS:
        nome_classe, campo = p.alvo
        cls = classes.get(nome_classe)
        if cls is None:
            continue
        vistos += 1
        real = getattr(cls(), campo)
        esperado = p.padrao
        if hasattr(real, "value"):  # enums viajam pelo .value no registro
            real = real.value
        assert real == esperado, f"{p.nome}: registro diz {esperado}, codigo diz {real}"
    assert vistos == len(mod_regras.PARAMETROS)


def test_regras_recusadas_ficam_registradas_com_o_motivo():
    """Recusar não é omitir: cada recusa tem id, seção e nota auditáveis."""
    recusadas = {r.id for r in mod_regras.nao_implementadas()}
    assert {
        "exaustao.conceito",
        "sinal_ultra.gatilho",
        "maker.formula",
        "alvo.formula",
        "horarios.tabela",
        "escora.formula",
        "risco.limite_diario_agregado",
        "risco.gatilho_de_tamanho",
    } <= recusadas
    for r in mod_regras.nao_implementadas():
        assert r.nota, r.id


# ===========================================================================
# Regime estrutural — a lição do caso WINFUT
# ===========================================================================


def _regime(**kw):
    return RegimeDoDia(ConfigEstrutura(**kw)) if kw else RegimeDoDia()


def test_barrigada_que_nao_perde_a_minima_e_ruido_nao_reversao():
    """"candle vendedor... acha que o mercado tá fritando" — o mercado sobe,
    devolve 1.000 ticks, e continua estruturalmente comprador."""
    r = _regime(usar_abertura=False)
    r.registrar_preco(100_000, 0)
    r.registrar_preco(102_000, 1 * S)  # rompe a maxima: comprador
    leitura = r.registrar_preco(101_000, 2 * S)  # barrigada de 1.000 ticks

    assert leitura.regime is RegimeEstrutural.COMPRADOR
    assert leitura.gatilho is GatilhoEstrutural.NENHUM
    assert leitura.ruido is True
    assert leitura.mudou_de_regime is False


def test_regime_so_vira_quando_perde_a_minima_do_dia():
    r = _regime(usar_abertura=False)
    r.registrar_preco(100_000, 0)
    r.registrar_preco(102_000, 1 * S)
    assert r.regime is RegimeEstrutural.COMPRADOR

    # Volta ate 1 tick ACIMA da minima: ainda nao perdeu nada.
    quase = r.registrar_preco(100_001, 2 * S)
    assert quase.regime is RegimeEstrutural.COMPRADOR
    assert quase.distancia_minima_ticks == 1

    perdeu = r.registrar_preco(99_999, 3 * S)
    assert perdeu.gatilho is GatilhoEstrutural.PERDEU_MINIMA
    assert perdeu.regime is RegimeEstrutural.VENDEDOR
    assert perdeu.lado is Side.SELL
    assert perdeu.mudou_de_regime is True


def test_cruzar_a_regiao_de_abertura_tambem_muda_o_regime():
    """§6.2: "perde a mínima do dia (ou a região de abertura)"."""
    r = _regime()
    r.registrar_preco(100_000, 0)
    r.registrar_preco(101_000, 1 * S)
    assert r.regime is RegimeEstrutural.COMPRADOR

    leitura = r.registrar_preco(99_900, 2 * S)
    assert leitura.gatilho is GatilhoEstrutural.PERDEU_MINIMA  # tambem e nova minima
    r2 = _regime(margem_abertura_ticks=50)
    r2.registrar_preco(100_000, 0)
    r2.registrar_preco(99_000, 1 * S)  # perde minima -> vendedor
    r2.registrar_preco(101_000, 2 * S)  # rompe maxima -> comprador
    volta = r2.registrar_preco(99_500, 3 * S)  # dentro do range, abaixo do open
    assert volta.gatilho is GatilhoEstrutural.CRUZOU_ABERTURA
    assert volta.regime is RegimeEstrutural.VENDEDOR


def test_margem_ticks_e_parametro_e_muda_o_veredito():
    """O limiar não é constante: com tolerância, o mesmo tape não vira."""
    frouxo = _regime(margem_ticks=100, usar_abertura=False)
    frouxo.registrar_preco(100_000, 0)
    frouxo.registrar_preco(102_000, 1 * S)
    quase = frouxo.registrar_preco(99_950, 2 * S)
    assert quase.regime is RegimeEstrutural.COMPRADOR

    apertado = _regime(margem_ticks=0, usar_abertura=False)
    apertado.registrar_preco(100_000, 0)
    apertado.registrar_preco(102_000, 1 * S)
    assert (
        apertado.registrar_preco(99_950, 2 * S).regime is RegimeEstrutural.VENDEDOR
    )


def test_preco_float_e_recusado():
    """Preço é sempre int em ticks — um float que passa vira chave errada."""
    with pytest.raises(TypeError):
        _regime().registrar_preco(100_000.5, 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        GestorRisco().regiao_de(100.5)  # type: ignore[arg-type]


def test_virada_de_sessao_esquece_maxima_e_minima_do_dia_anterior():
    r = _regime()
    r.registrar_preco(100_000, 0)
    r.registrar_preco(105_000, 1 * S)
    r.iniciar_nova_sessao()
    assert r.regime is RegimeEstrutural.INDEFINIDO
    assert r.maxima is None

    leitura = r.registrar_preco(90_000, 10 * S)
    assert leitura.abertura == 90_000
    assert leitura.regime is RegimeEstrutural.INDEFINIDO


def test_candle_ohlc_alimenta_o_regime():
    r = _regime(usar_abertura=False)
    r.registrar_preco(100_000, 0)
    leitura = r.registrar_candle(
        Candle(
            timestamp_ns=1 * S,
            open=100_000,
            high=101_000,
            low=99_000,
            close=100_500,
            volume=10,
            delta=2,
        )
    )
    # O→H→L→C: rompe a maxima, depois perde a minima. O ultimo gatilho manda.
    assert leitura.regime is RegimeEstrutural.VENDEDOR
    assert r.maxima == 101_000 and r.minima == 99_000


# ===========================================================================
# Velocímetro
# ===========================================================================


def _rodar_velocimetro(passos, cfg=None):
    """`passos` = [(ts, valor_acumulado)]. Devolve as leituras."""
    v = Velocimetro(cfg)
    return [v.registrar(ts, valor) for ts, valor in passos]


def _tape_winfut(escala=1):
    """Sessão em que o fluxo vendedor domina, seguida de um repique comprador
    de magnitude muito menor — a forma do dia narrado em §7."""
    passos = []
    valor = 0
    ts = 0
    for _ in range(40):  # pernas vendedoras grandes
        for _ in range(4):
            ts += 4 * S
            valor -= 500 * escala
            passos.append((ts, valor))
        for _ in range(2):
            ts += 4 * S
            valor += 300 * escala
            passos.append((ts, valor))
    for _ in range(4):  # repique comprador pequeno
        ts += 4 * S
        valor += 60 * escala
        passos.append((ts, valor))
    return passos


def test_repique_pequeno_nao_e_lido_como_forca(  # caso WINFUT, eixo (a)
):
    """Um contador que sobe, mas com magnitude irrisória perto do histórico do
    próprio dia, é PARADO — não "acelerando comprador"."""
    cfg = ConfigVelocimetro(janela_ns=16 * S, n_baldes=4)
    leituras = _rodar_velocimetro(_tape_winfut(), cfg)
    final = leituras[-1]

    assert final.sentido is Side.BUY  # a leitura ingenua compraria
    assert final.estado is EstadoVelocimetro.PARADO

    # E o MESMO tape, nas pernas vendedoras (magnitude compativel com o dia),
    # nao e lido como parado — o que separa as duas leituras e a magnitude
    # relativa, nao o sinal.
    vendedoras = [
        l
        for l in leituras[20:-8]
        if l.sentido is Side.SELL and l.magnitude_relativa is not None
    ]
    assert vendedoras
    assert any(l.estado is not EstadoVelocimetro.PARADO for l in vendedoras)
    assert max(l.magnitude_relativa for l in vendedoras) > (
        final.magnitude_relativa or 0.0
    ) * 3


def test_leitura_e_invariante_a_escala():
    """`velocimetro.escala_fixa` é AUSENTE NA FONTE — não existe "acima de 250
    é forte". Multiplicar o dia inteiro por 10 não pode mudar uma leitura.

    Este é o teste que impede alguém de reintroduzir um limiar absoluto: uma
    constante de magnitude no código quebraria esta igualdade na hora.
    """
    cfg = ConfigVelocimetro(janela_ns=16 * S, n_baldes=4)
    base = [l.estado for l in _rodar_velocimetro(_tape_winfut(1), cfg)]
    dez = [l.estado for l in _rodar_velocimetro(_tape_winfut(10), cfg)]
    mil = [l.estado for l in _rodar_velocimetro(_tape_winfut(1000), cfg)]
    assert base == dez == mil
    assert EstadoVelocimetro.ACELERANDO in base  # a sequencia nao e degenerada


def test_persistencia_separa_forte_e_breve_de_moderado_e_longo():
    """Eixo (b): o tempo de permanência é campo próprio, não some no estado."""
    cfg = ConfigVelocimetro(janela_ns=16 * S, n_baldes=4)
    v = Velocimetro(cfg)
    valor = 0
    ultima = None
    for i in range(1, 21):  # comprador sustentado
        valor += 100
        ultima = v.registrar(i * 4 * S, valor)
    assert ultima is not None
    assert ultima.sentido is Side.BUY
    persistencia_longa = ultima.persistencia_ns
    assert persistencia_longa > 0

    # Inverte: a persistencia zera e o estado vira VIROU.
    valor -= 4000
    virada = v.registrar(21 * 4 * S, valor)
    assert virada.sentido is Side.SELL
    assert virada.estado is EstadoVelocimetro.VIROU
    assert virada.persistencia_ns == 0
    assert virada.persistencia_ns < persistencia_longa


def test_leitura_publica_a_janela_real_que_usou():
    """A janela de baldes é aproximada; quem lê nunca precisa adivinhar."""
    cfg = ConfigVelocimetro(janela_ns=16 * S, n_baldes=4)
    leituras = _rodar_velocimetro([(i * 4 * S, i * 10) for i in range(1, 20)], cfg)
    ultima = leituras[-1]
    assert 0 < ultima.duracao_janela_ns <= cfg.janela_ns
    assert ultima.amostras_janela >= 1


def test_virada_de_sessao_esquece_a_referencia_de_magnitude():
    """Medir o repique de hoje contra o pico de ontem é o erro do caso WINFUT
    com um dia de atraso."""
    cfg = ConfigVelocimetro(janela_ns=16 * S, n_baldes=4)
    v = Velocimetro(cfg)
    valor = 0
    for i in range(1, 60):
        valor -= 500
        v.registrar(i * 4 * S, valor)
    assert v.registrar(60 * 4 * S, valor - 500).referencia_magnitude is not None

    v.iniciar_nova_sessao()
    primeira = v.registrar(0, 0)
    assert primeira.referencia_magnitude is None
    assert primeira.estado is EstadoVelocimetro.SEM_DADOS


# ===========================================================================
# Placar estatístico
# ===========================================================================


def _votos(compra=0, venda=0, neutro=0):
    v = {}
    for i in range(compra):
        v[f"c{i}"] = VotoPlacar.COMPRA
    for i in range(venda):
        v[f"v{i}"] = VotoPlacar.VENDA
    for i in range(neutro):
        v[f"n{i}"] = VotoPlacar.NEUTRO
    return v


def test_placar_conta_e_nomeia_a_goleada():
    p = Placar(ConfigPlacar(aquecimento_ns=0, estabilidade_minima_ns=0))
    leitura = p.registrar(0, _votos(compra=4))
    assert (leitura.compra, leitura.venda) == (4, 0)
    assert leitura.placar == "4 a 0"
    assert leitura.lado is Side.BUY
    assert leitura.goleada is True

    magro = p.registrar(S, _votos(compra=3, venda=1))
    assert magro.placar == "3 a 1"
    assert magro.goleada is False


def test_limiar_de_goleada_e_parametro_porque_a_fonte_da_dois_numeros():
    cfg4 = ConfigPlacar(diferenca_goleada=4, aquecimento_ns=0)
    cfg5 = ConfigPlacar(diferenca_goleada=5, aquecimento_ns=0)
    votos = _votos(compra=4)
    assert Placar(cfg4).registrar(0, votos).goleada is True
    assert Placar(cfg5).registrar(0, votos).goleada is False


def test_placar_estavel_e_placar_oscilando_sao_leituras_diferentes():
    """"aguardar se de fato existe uma confluência mais estável"."""
    cfg = ConfigPlacar(
        aquecimento_ns=0,
        estabilidade_minima_ns=10 * S,
        janela_oscilacao_ns=60 * S,
        oscilacoes_para_instavel=3,
    )

    parado = Placar(cfg)
    ultima = None
    for i in range(0, 40, 2):
        ultima = parado.registrar(i * S, _votos(compra=4))
    assert ultima is not None
    assert ultima.estavel is True
    assert ultima.oscilando is False
    assert ultima.operavel is True

    inquieto = Placar(cfg)
    ultima = None
    for i in range(0, 40, 2):
        placar = _votos(compra=4) if i % 4 == 0 else _votos(venda=4)
        ultima = inquieto.registrar(i * S, placar)
    assert ultima is not None
    assert ultima.oscilando is True
    assert ultima.estavel is False
    assert ultima.operavel is False


def test_aquecimento_impede_leitura_operavel_nos_primeiros_minutos():
    cfg = ConfigPlacar(aquecimento_ns=60 * S, estabilidade_minima_ns=0)
    p = Placar(cfg)
    cedo = p.registrar(0, _votos(compra=4))
    assert cedo.em_aquecimento is True
    assert cedo.operavel is False

    tarde = p.registrar(120 * S, _votos(compra=4))
    assert tarde.em_aquecimento is False
    assert tarde.operavel is True


def test_virada_de_goleada_levanta_alerta_de_reversao():
    cfg = ConfigPlacar(aquecimento_ns=0, estabilidade_minima_ns=0)
    p = Placar(cfg)
    p.registrar(0, _votos(compra=4))
    virou = p.registrar(S, _votos(venda=4))
    assert virou.virou is True
    assert virou.alerta_reversao is True
    assert virou.lado is Side.SELL

    empate = p.registrar(2 * S, _votos(compra=2, venda=2))
    assert empate.lado is None
    assert empate.virou is True


def test_placar_nao_le_o_mercado_sozinho():
    """"ele lê os sinais que a SG já lê do mercado" — meta-leitura. Sem votos,
    não há lado, por mais fluxo que exista no mundo."""
    p = Placar(ConfigPlacar(aquecimento_ns=0, estabilidade_minima_ns=0))
    vazio = p.registrar(0, {})
    assert vazio.lado is None
    assert vazio.total_fontes == 0
    assert vazio.operavel is False


# ===========================================================================
# Linha Azul
# ===========================================================================


def test_linha_azul_e_o_preco_do_cruzamento_de_50_por_cento():
    la = LinhaAzul(SIMBOLO)
    la.ao_trade(_trade(0, 100_000, 10, AgressorSide.BUY))
    assert la.nivel is None  # 100% comprador: nao cruzou nada ainda

    leitura = la.ao_trade(_trade(S, 100_500, 20, AgressorSide.SELL))
    assert leitura.cruzou_agora is True
    assert leitura.nivel == 100_500
    assert leitura.nivel_timestamp_ns == S


def test_convencao_de_plotagem_e_escolha_declarada_e_muda_o_nivel():
    """O IMPRECISO da fonte (mudou entre versões) vira parâmetro visível.

    O mesmo tape produz níveis diferentes sob as duas convenções — é isso que
    torna a escolha uma decisão, e não um detalhe escondido.
    """
    tape = [
        _trade(0, 100_000, 10, AgressorSide.BUY),
        _trade(1 * S, 100_500, 20, AgressorSide.SELL),  # cruza para baixo
        _trade(2 * S, 101_000, 30, AgressorSide.BUY),  # cruza para cima
    ]

    ultimo = LinhaAzul(SIMBOLO, ConfigLinhaAzul())
    primeiro = LinhaAzul(
        SIMBOLO, ConfigLinhaAzul(convencao=ConvencaoLinhaAzul.PRIMEIRO_CRUZAMENTO)
    )
    for t in tape:
        u = ultimo.ao_trade(t)
        p = primeiro.ao_trade(t)

    assert u.nivel == 101_000
    assert p.nivel == 100_500
    assert u.convencao is ConvencaoLinhaAzul.ULTIMO_CRUZAMENTO
    assert p.convencao is ConvencaoLinhaAzul.PRIMEIRO_CRUZAMENTO


def test_volume_minimo_de_ancoragem_adia_o_nascimento_da_linha():
    """A versão que "não plota mais na abertura", sem inventar o número dela."""
    cfg = ConfigLinhaAzul(volume_minimo_ancoragem=1_000)
    la = LinhaAzul(SIMBOLO, cfg)
    la.ao_trade(_trade(0, 100_000, 10, AgressorSide.BUY))
    cedo = la.ao_trade(_trade(S, 100_500, 20, AgressorSide.SELL))
    assert cedo.nivel is None
    assert cedo.lado is LadoDaLinha.SEM_LINHA

    la.ao_trade(_trade(2 * S, 100_600, 2_000, AgressorSide.BUY))
    tarde = la.ao_trade(_trade(3 * S, 100_700, 4_000, AgressorSide.SELL))
    assert tarde.nivel == 100_700


def test_lado_da_linha_sai_rotulado_inferido():
    """"Abaixo vende, acima compra" não é verbalizado pelo autor — a API
    publica a leitura E o rótulo, para nenhum painel promovê-la a confirmada."""
    la = LinhaAzul(SIMBOLO)
    la.ao_trade(_trade(0, 100_000, 10, AgressorSide.BUY))
    la.ao_trade(_trade(S, 100_500, 20, AgressorSide.SELL))

    acima = la.leitura(2 * S, 101_000)
    assert acima.lado is LadoDaLinha.ACIMA
    assert acima.lado.leitura_inferida is Side.BUY
    assert acima.confianca_lado is Confianca.INFERIDO
    assert acima.distancia_ticks == 500

    abaixo = la.leitura(3 * S, 100_000)
    assert abaixo.lado is LadoDaLinha.ABAIXO
    assert abaixo.lado.leitura_inferida is Side.SELL
    assert abaixo.distancia_ticks == -500


def test_volume_sem_agressor_fica_fora_da_razao_e_dentro_do_total():
    la = LinhaAzul(SIMBOLO)
    la.ao_trade(_trade(0, 100_000, 10, AgressorSide.BUY))
    la.ao_trade(_trade(S, 100_000, 10, AgressorSide.SELL))
    leitura = la.ao_trade(_trade(2 * S, 100_000, 500, AgressorSide.UNKNOWN))

    assert leitura.fracao_compradora == pytest.approx(0.5)
    assert leitura.volume_nao_atribuido == 500
    assert la.volume_total == 520


def test_linha_azul_reseta_na_virada_de_sessao():
    la = LinhaAzul(SIMBOLO)
    la.ao_trade(_trade(0, 100_000, 10, AgressorSide.BUY))
    la.ao_trade(_trade(S, 100_500, 20, AgressorSide.SELL))
    assert la.nivel is not None

    la.iniciar_nova_sessao()
    assert la.nivel is None
    assert la.volume_total == 0


# ===========================================================================
# Macro × micro
# ===========================================================================


def test_comparar_macro_com_micro_levanta_erro():
    """A regra de exibição da fonte virando comportamento em runtime."""
    macro = MedidaContexto(Escala.MACRO, 900, 0, 100)
    micro = MedidaContexto(Escala.MICRO, 900, 15 * S, 10)

    for operacao in (
        lambda: macro < micro,
        lambda: macro > micro,
        lambda: macro == micro,
        lambda: macro - micro,
        lambda: macro / micro,
        lambda: comparar_magnitudes(macro, micro),
    ):
        with pytest.raises(EscalasIncomparaveisError):
            operacao()


def test_comparacao_dentro_da_mesma_escala_funciona_normalmente():
    a = MedidaContexto(Escala.MACRO, 900, 0, 100)
    b = MedidaContexto(Escala.MACRO, 1_925, 0, 100)
    assert a < b
    assert comparar_magnitudes(b, a) == 1
    assert a == MedidaContexto(Escala.MACRO, 900, 0, 100)


def test_comparar_medida_com_numero_cru_tambem_e_recusado():
    """Comparar com um `int` perderia justamente a escala."""
    with pytest.raises(EscalasIncomparaveisError):
        MedidaContexto(Escala.MICRO, 10, 15 * S, 3) < 900  # noqa: B015


def test_micro_manda_no_agora_e_a_contra_tendencia_e_so_uma_flag():
    """Micro vendedora dentro de um dia comprador: a leitura diz quem comanda
    e sinaliza contra-tendência, mas não bloqueia nada."""
    mm = MacroMicro(SIMBOLO, ConfigMacroMicro(janela_micro_ns=8 * S, n_baldes=4))
    for i in range(1, 30):  # macro compradora forte
        mm.ao_trade(_trade(i * S, 100_000, 100, AgressorSide.BUY))
    for i in range(30, 40):  # micro vendedora recente
        mm.ao_trade(_trade(i * S, 100_000, 50, AgressorSide.SELL))

    leitura = mm.leitura(40 * S)
    assert leitura.macro.sentido is Side.BUY
    assert leitura.micro.sentido is Side.SELL
    assert leitura.comanda is Side.SELL
    assert leitura.contra_tendencia is True
    assert leitura.alinhados is False
    assert leitura.comparavel_por_magnitude is False


def test_a_janela_da_micro_viaja_na_leitura():
    """AUSENTE NA FONTE: nenhum painel pode mostrar "a micro" sem poder dizer
    de que janela está falando."""
    mm = MacroMicro(SIMBOLO, ConfigMacroMicro(janela_micro_ns=8 * S, n_baldes=4))
    for i in range(1, 20):
        mm.ao_trade(_trade(i * S, 100_000, 10, AgressorSide.BUY))
    leitura = mm.leitura(20 * S)
    assert leitura.macro.janela_ns == 0  # 0 = desde a abertura
    assert 0 < leitura.micro.janela_ns <= 8 * S


def test_macro_reseta_na_virada_de_sessao():
    mm = MacroMicro(SIMBOLO)
    mm.ao_trade(_trade(0, 100_000, 100, AgressorSide.BUY))
    assert mm.delta_macro == 100
    mm.iniciar_nova_sessao()
    assert mm.delta_macro == 0
    assert mm.leitura(S).micro.valor == 0


# ===========================================================================
# Gestão de risco
# ===========================================================================


def _gestor(**kw):
    return GestorRisco(ConfigRisco(**kw))


def test_tres_stops_seguidos_abandonam_a_regiao_no_dia():
    g = _gestor(tamanho_regiao_ticks=100)
    preco = 100_000
    assert g.permite_entrada(preco) is True
    for _ in range(2):
        g.registrar_resultado(preco, ResultadoOperacao.STOP)
    assert g.permite_entrada(preco) is True

    estado = g.registrar_resultado(preco, ResultadoOperacao.STOP)
    assert estado.stops_seguidos == 3
    assert estado.bloqueada is True
    assert g.permite_entrada(preco) is False
    assert g.avaliar(preco, QualidadeRegiao.BOA).permitida is False
    # Preco vizinho, MESMA regiao: tambem bloqueado.
    assert g.permite_entrada(preco + 50) is False


def test_ganho_zera_os_stops_seguidos():
    """A fonte diz "três stops SEGUIDOS" — um ganho no meio quebra a sequência."""
    g = _gestor(tamanho_regiao_ticks=100)
    preco = 100_000
    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    g.registrar_resultado(preco, ResultadoOperacao.GANHO)
    assert g.estado_regiao(preco).stops_seguidos == 0

    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    assert g.permite_entrada(preco) is True


def test_nao_existe_limite_diario_agregado():
    """`risco.limite_diario_agregado` é AUSENTE NA FONTE, e a ausência é
    verificável: dez regiões arrasadas não fecham a décima primeira."""
    g = _gestor(tamanho_regiao_ticks=100)
    for r in range(10):
        preco = 100_000 + r * 1_000
        for _ in range(3):
            g.registrar_resultado(preco, ResultadoOperacao.STOP)
        assert g.permite_entrada(preco) is False

    novo = 100_000 + 50_000
    assert g.permite_entrada(novo) is True
    assert g.avaliar(novo, QualidadeRegiao.BOA).permitida is True
    assert len(g.regioes_bloqueadas) == 10


def test_limite_de_stops_e_parametro():
    g = _gestor(tamanho_regiao_ticks=100, stops_maximos_por_regiao=2)
    preco = 100_000
    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    assert g.permite_entrada(preco) is True
    g.registrar_resultado(preco, ResultadoOperacao.STOP)
    assert g.permite_entrada(preco) is False


def test_o_gatilho_de_tamanho_vem_do_operador_nao_do_sistema():
    """"Região boa" × "turbulenta" é AUSENTE NA FONTE: `avaliar` exige o
    julgamento, e não há caminho que o dispense."""
    g = _gestor(contratos_mao_cheia=20, contratos_mao_minima=5)
    assert g.avaliar(100_000, QualidadeRegiao.BOA).modo is ModoTamanho.MAO_CHEIA
    assert (
        g.avaliar(100_000, QualidadeRegiao.TURBULENTA).modo is ModoTamanho.MAO_MINIMA
    )
    assert g.avaliar(100_000, QualidadeRegiao.INCERTA).modo is ModoTamanho.MEIA_MAO

    with pytest.raises(TypeError):
        g.avaliar(100_000)  # type: ignore[call-arg]


def test_tamanho_recusa_responder_sem_o_lote_do_operador():
    """20/10/5 são o lote pessoal do autor, não regra — o produto não os
    assume por conta própria."""
    g = _gestor()
    with pytest.raises(TamanhoNaoConfiguradoError):
        g.tamanho(ModoTamanho.MAO_CHEIA)
    decisao = g.avaliar(100_000, QualidadeRegiao.BOA)
    assert decisao.permitida is True
    assert decisao.contratos is None


def test_meia_mao_e_derivada_de_metade_do_lote():
    g = _gestor(contratos_mao_cheia=20, contratos_mao_minima=5)
    assert g.tamanho(ModoTamanho.MEIA_MAO) == 10

    explicito = _gestor(contratos_mao_cheia=20, contratos_meia_mao=7)
    assert explicito.tamanho(ModoTamanho.MEIA_MAO) == 7


def test_virada_de_sessao_libera_as_regioes():
    g = _gestor(tamanho_regiao_ticks=100)
    for _ in range(3):
        g.registrar_resultado(100_000, ResultadoOperacao.STOP)
    assert g.permite_entrada(100_000) is False
    g.iniciar_nova_sessao()
    assert g.permite_entrada(100_000) is True
    assert g.regioes_rastreadas == 0


# ===========================================================================
# Retenção — o critério do docstring de gravacao/gravador.py
# ===========================================================================

_TIPOS_COLECAO = (list, dict, set, frozenset, tuple, bytearray)


def _colecoes_de(obj) -> dict[str, int]:
    """`len` de toda coleção de instância, por nome de atributo.

    Desce um nível em objetos aninhados deste pacote (`JanelaMovel` dentro do
    `Velocimetro`), porque o defeito costuma morar no componente interno.
    """
    tamanhos: dict[str, int] = {}
    nomes = getattr(type(obj), "__slots__", None) or []
    if not nomes and hasattr(obj, "__dict__"):
        nomes = list(vars(obj))
    for nome in nomes:
        try:
            valor = getattr(obj, nome)
        except AttributeError:
            continue
        if isinstance(valor, _TIPOS_COLECAO):
            tamanhos[nome] = len(valor)
        elif type(valor).__module__.startswith("fluxopro.metodologia"):
            for sub, n in _colecoes_de(valor).items():
                tamanhos[f"{nome}.{sub}"] = n
    return tamanhos


@pytest.mark.parametrize("n_pequeno,n_grande", [(1_000, 20_000)])
def test_nenhuma_estrutura_cresce_com_o_numero_de_eventos(n_pequeno, n_grande):
    """20× mais eventos, o mesmo `len` em toda coleção de instância.

    É a asserção que distingue O(1) de O(eventos) — a auditoria R5 provou que,
    sem ela, uma suíte inteira pode ser incapaz de notar a diferença. Cada
    componente abaixo respondeu a pergunta "qual grandeza limita o `len` disto?"
    com uma constante de configuração; aqui isso vira medida.
    """

    def medir(n):
        estrutura = RegimeDoDia()
        velocimetro = Velocimetro(ConfigVelocimetro(janela_ns=16 * S, n_baldes=4))
        placar = Placar(ConfigPlacar(janela_oscilacao_ns=60 * S))
        linha = LinhaAzul(SIMBOLO)
        macro_micro = MacroMicro(SIMBOLO, ConfigMacroMicro(janela_micro_ns=8 * S))
        risco = GestorRisco()

        acumulado = 0
        for i in range(1, n + 1):
            ts = i * S
            preco = 100_000 + (i % 977) - 488
            lado = AgressorSide.BUY if i % 3 else AgressorSide.SELL
            acumulado += 10 if lado is AgressorSide.BUY else -10

            estrutura.registrar_preco(preco, ts)
            velocimetro.registrar(ts, acumulado)
            placar.registrar(ts, _votos(compra=i % 5, venda=(i * 7) % 5))
            linha.ao_trade(_trade(ts, preco, 10, lado))
            macro_micro.ao_trade(_trade(ts, preco, 10, lado))
            # Mercado rodando NAO cria estado de risco: so operacao registrada.
            risco.permite_entrada(preco)

        return {
            "estrutura": _colecoes_de(estrutura),
            "velocimetro": _colecoes_de(velocimetro),
            "placar": _colecoes_de(placar),
            "linha_azul": _colecoes_de(linha),
            "macro_micro": _colecoes_de(macro_micro),
            "risco": _colecoes_de(risco),
        }

    pequeno = medir(n_pequeno)
    grande = medir(n_grande)
    assert pequeno == grande, (
        "alguma colecao cresceu com o numero de eventos:\n"
        f"  {n_pequeno} eventos: {pequeno}\n"
        f"  {n_grande} eventos: {grande}"
    )
    assert grande["risco"]["_regioes"] == 0


def test_risco_so_guarda_regiao_com_stop_em_aberto():
    """`len(_regioes)` é limitado por operações PERDEDORAS do operador, não por
    preços vistos nem por ganhos — e ganho devolve a entrada ao pool."""
    g = _gestor(tamanho_regiao_ticks=100)
    for i in range(500):
        g.estado_regiao(100_000 + i * 100)
        g.permite_entrada(100_000 + i * 100)
    assert g.regioes_rastreadas == 0

    for i in range(50):
        g.registrar_resultado(100_000 + i * 100, ResultadoOperacao.STOP)
    assert g.regioes_rastreadas == 50

    for i in range(50):
        g.registrar_resultado(100_000 + i * 100, ResultadoOperacao.GANHO)
    assert g.regioes_rastreadas == 0


def test_janela_movel_tem_len_fixo_e_publica_o_lookback():
    """A janela é aproximada de propósito; o preço disso é declarado, e o
    tamanho do anel não depende de quantas amostras entraram."""
    j = JanelaMovel(janela_ns=8 * S, n_baldes=4)
    for i in range(1, 10_001):
        j.registrar(i * S // 10, i)
    assert _colecoes_de(j) == {"_bal_idx": 4, "_bal_valor": 4, "_bal_n": 4}
    assert 0 < j.duracao_ns <= 8 * S
    assert j.variacao > 0


def test_janela_movel_recusa_configuracao_impossivel():
    with pytest.raises(ValueError):
        JanelaMovel(janela_ns=0)
    with pytest.raises(ValueError):
        JanelaMovel(janela_ns=8 * S, n_baldes=1)


def test_dataclasses_de_leitura_sao_imutaveis():
    """Leitura publicada não é rascunho — quem recebe não reescreve a
    evidência (mesmo padrão de `Sinal` em `motor/sinais.py`)."""
    leitura = RegimeDoDia().registrar_preco(100, 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        leitura.regime = RegimeEstrutural.VENDEDOR  # type: ignore[misc]
