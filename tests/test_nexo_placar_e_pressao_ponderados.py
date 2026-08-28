"""Cobre o achado do operador (27/08/2026): Placar Estatistico e o
indicador 56/44 "players" precisavam de logica mais tecnica, nao so
explicacao. As duas funcoes puras abaixo sao a formula em si — sem
tocar em QPainter, faceis de verificar isoladamente.
"""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap

from fluxopro.ui.paineis.asg import ConfiancaASG, DirecaoASG, LinhaMatrizASG, ProcedenciaASG
from fluxopro.ui.paineis.nexo import estatistica, pressao
from fluxopro.ui.paineis.nexo import EstadoNexo
from fluxopro.core.eventos import WDO_GRID


def _linha(nome, forca, confianca, direcao=None):
    if direcao is None:
        direcao = DirecaoASG.COMPRA if forca > 0 else DirecaoASG.VENDA if forca < 0 else DirecaoASG.NEUTRA
    return (nome, LinhaMatrizASG(
        componente=nome, direcao=direcao, valor="", forca=forca,
        confianca=confianca, procedencia=ProcedenciaASG.DERIVADO,
    ))


def test_placar_ponderado_favorece_leitura_de_alta_confianca():
    leituras = (
        _linha("HORIZONTE", 0.9, ConfiancaASG.ALTA),
        _linha("PULSO", -0.9, ConfiancaASG.BAIXA),
    )
    score = estatistica.placar_ponderado(leituras)
    assert score > 0, "leitura ALTA (+0.9) deve pesar mais que BAIXA (-0.9)"


def test_placar_ponderado_ignora_leitura_indisponivel():
    leituras = (
        _linha("HORIZONTE", 0.9, ConfiancaASG.ALTA),
        _linha("PULSO", -1.0, ConfiancaASG.INDISPONIVEL),
    )
    score = estatistica.placar_ponderado(leituras)
    assert score == 0.9, "confianca INDISPONIVEL tem peso 0 — nao deveria puxar o score"


def test_placar_ponderado_sem_leituras_com_peso_e_zero():
    leituras = (_linha("HORIZONTE", 0.9, ConfiancaASG.INDISPONIVEL),)
    assert estatistica.placar_ponderado(leituras) == 0.0


def test_placar_ponderado_fica_em_menos1_mais1():
    leituras = tuple(_linha(f"L{i}", 1.0, ConfiancaASG.ALTA) for i in range(4))
    assert estatistica.placar_ponderado(leituras) == 1.0


def test_desenha_contagem_sem_excecao(qapp):
    leituras = (
        _linha("HORIZONTE", 0.5, ConfiancaASG.ALTA),
        _linha("PULSO", -0.3, ConfiancaASG.MEDIA),
        _linha("PRESENCA", 0.1, ConfiancaASG.BAIXA),
        _linha("RITMO", 0.0, ConfiancaASG.INDISPONIVEL),
    )
    estado = EstadoNexo(
        snapshot=None, serie=((0, 100000, 0.1, 1),), grid=WDO_GRID, paleta=None,
        maker=None, leituras=leituras, largura=400, altura=150,
    )
    pixmap = QPixmap(400, 150)
    painter = QPainter(pixmap)
    try:
        estatistica.desenhar(painter, QRect(0, 0, 400, 150), estado)
    finally:
        painter.end()


def test_pressao_composta_pesos_somam_um():
    assert abs(pressao.PESO_MAKER_PRESSAO + pressao.PESO_RITMO_PRESSAO - 1.0) < 1e-9


def test_pressao_composta_diverge_do_maker_puro_quando_ritmo_discorda():
    so_maker = pressao.pressao_composta(maker_forca=0.8, ritmo_forca=0.0)
    com_ritmo_contra = pressao.pressao_composta(maker_forca=0.8, ritmo_forca=-1.0)
    assert com_ritmo_contra < so_maker, (
        "ritmo contra deve puxar o score pra baixo — antes de 27/08/2026 "
        "este numero era so o maker, nunca reagia ao ritmo"
    )


def test_pressao_composta_fica_em_menos1_mais1():
    assert pressao.pressao_composta(1.0, 1.0) == 1.0
    assert pressao.pressao_composta(-1.0, -1.0) == -1.0


# --- placar de dois lados (achado "mudancas tao abruptas") -----------------

def test_pesos_por_lado_mostram_discordancia_nos_dois_lados():
    leituras = (
        _linha("HORIZONTE", 0.8, ConfiancaASG.ALTA),
        _linha("RITMO", -0.8, ConfiancaASG.ALTA),
    )
    compra, venda = estatistica.pesos_por_lado(leituras)
    assert compra > 0 and venda > 0, (
        "com leituras opostas os DOIS lados tem conviccao; a formula antiga "
        "(max(0, score)) zerava um deles sempre"
    )


def test_pesos_por_lado_reconciliam_com_o_placar_ponderado():
    leituras = (
        _linha("HORIZONTE", 0.6, ConfiancaASG.ALTA),
        _linha("PULSO", -0.2, ConfiancaASG.MEDIA),
        _linha("PRESENCA", 0.1, ConfiancaASG.BAIXA),
        _linha("RITMO", -0.9, ConfiancaASG.MEDIA),
    )
    compra, venda = estatistica.pesos_por_lado(leituras)
    assert abs((compra - venda) - estatistica.placar_ponderado(leituras)) < 1e-9


def test_pesos_por_lado_nao_saltam_ao_cruzar_o_zero():
    """Passo pequeno na forca => passo pequeno no numero da tela."""
    anterior = None
    for milesimos in range(-30, 31):
        forca = milesimos / 1000.0
        compra, venda = estatistica.pesos_por_lado(
            (_linha("HORIZONTE", forca, ConfiancaASG.ALTA),)
        )
        atual = (compra, venda)
        if anterior is not None:
            salto = max(abs(atual[0] - anterior[0]), abs(atual[1] - anterior[1]))
            assert salto <= 0.002, f"salto de {salto} em forca={forca}"
        anterior = atual


def test_pesos_por_lado_somam_no_maximo_um_e_sobra_e_falta_de_conviccao():
    leituras = (
        _linha("HORIZONTE", 0.2, ConfiancaASG.ALTA),
        _linha("PULSO", 0.0, ConfiancaASG.ALTA),
    )
    compra, venda = estatistica.pesos_por_lado(leituras)
    assert compra + venda <= 1.0
    assert compra + venda < 0.5, "leitura sem forca nao vira conviccao renormalizada"


def test_pesos_por_lado_sem_confianca_e_zero_zero():
    assert estatistica.pesos_por_lado(
        (_linha("HORIZONTE", 1.0, ConfiancaASG.INDISPONIVEL),)
    ) == (0.0, 0.0)


# --- reconciliacao pressao x placar ---------------------------------------

def test_rotulo_coerencia_confirma_diverge_e_neutro():
    assert pressao.rotulo_coerencia(0.5, 0.4) == "CONFIRMA O PLACAR"
    assert pressao.rotulo_coerencia(-0.5, 0.4) == "DIVERGE DO PLACAR"
    assert pressao.rotulo_coerencia(0.01, 0.4) == "NEUTRO VS PLACAR"
    assert pressao.rotulo_coerencia(0.5, -0.01) == "NEUTRO VS PLACAR"


def test_desenha_pressao_com_leituras_divergentes_sem_excecao(qapp):
    leituras = (
        _linha("HORIZONTE", 0.8, ConfiancaASG.ALTA),
        _linha("RITMO", -0.8, ConfiancaASG.ALTA),
    )
    estado = EstadoNexo(
        snapshot=None, serie=((0, 100000, 0.1, 1), (1, 100010, -0.2, 2)), grid=WDO_GRID,
        paleta=None, maker=None, leituras=leituras, largura=520, altura=90,
    )
    pixmap = QPixmap(520, 90)
    painter = QPainter(pixmap)
    try:
        pressao.desenhar(painter, QRect(0, 0, 520, 90), estado)
    finally:
        painter.end()


# --- RITMO: grandeza x manutencao ------------------------------------------

def test_forca_ritmo_desacelerando_vale_menos_que_acelerando():
    from fluxopro.ui.paineis import asg

    acelerando = asg._forca_ritmo_composta(1.0, "ACELERANDO", 1.0)
    desacelerando = asg._forca_ritmo_composta(1.0, "DESACELERANDO", 1.0)
    assert acelerando == 1.0
    assert 0.0 < desacelerando < acelerando, (
        "o ladrilho mostrava +100% com o rotulo DESACELERANDO ao lado"
    )


def test_forca_ritmo_parada_ou_sem_dados_e_zero():
    from fluxopro.ui.paineis import asg

    assert asg._forca_ritmo_composta(1.0, "PARADO", 1.0) == 0.0
    assert asg._forca_ritmo_composta(1.0, "SEM_DADOS", -1.0) == 0.0
    assert asg._forca_ritmo_composta(None, "ACELERANDO", 1.0) == 0.0


def test_forca_ritmo_preserva_o_sinal_da_direcao():
    from fluxopro.ui.paineis import asg

    assert asg._forca_ritmo_composta(1.0, "MANTENDO", -1.0) < 0


# --- INVARIANTE: grandeza e sinal nunca viajam separados -------------------
#
# Reincidencia caçada em 28/08/2026: o mesmo defeito (numero grande de um
# lado, rotulo/cor do outro) foi consertado no RITMO e renasceu na PRESENCA,
# porque a suavizacao do MakerProxy trocava so `forca` e deixava `direcao` e
# `valor` no score cru. Os testes abaixo prendem a regra de forma GENERICA,
# em vez de prender o caso da PRESENCA.

_FORCAS_DE_TESTE = (-1.0, -0.73, -0.33, -0.01, 0.0, 0.01, 0.33, 0.73, 1.0)


def test_linha_com_forca_mantem_forca_direcao_e_valor_no_mesmo_sinal():
    from fluxopro.ui.paineis import asg

    base = _linha("PRESENCA", -0.33, ConfiancaASG.ALTA)[1]
    for forca in _FORCAS_DE_TESTE:
        nova = asg._linha_com_forca(base, forca)
        assert asg.leitura_e_coerente(nova), f"forca={forca} contra direcao={nova.direcao}"
        assert asg.sinal_da_leitura(nova) == (forca > 0) - (forca < 0)
        assert nova.valor.startswith("-") == (forca < 0), (
            "o texto pequeno do contexto tem de carregar o mesmo sinal do numero grande"
        )


def test_todos_os_quatro_consumidores_leem_o_mesmo_sinal():
    """cor · rotulo COMPRA/VENDA · numero impresso · barra do rodape."""
    from fluxopro.ui.paineis import asg
    from fluxopro.ui import tema_asg

    base = _linha("PRESENCA", 0.0, ConfiancaASG.ALTA)[1]
    for forca in _FORCAS_DE_TESTE:
        if forca == 0.0:
            continue
        linha = asg._linha_com_forca(base, forca)
        sinal = asg.sinal_da_leitura(linha)

        # 1. numero grande do ladrilho (estatistica.py imprime linha.forca)
        assert (linha.forca > 0) == (sinal > 0)
        # 2. texto pequeno da lista de contexto (contexto.py imprime linha.valor)
        assert linha.valor.startswith("+") == (sinal > 0)
        # 3. cor / rotulo COMPRA-VENDA (toda regiao usa linha.direcao)
        cor = asg._cor_nexo_direcao(linha.direcao)
        assert cor is (tema_asg.NEXO_VERDE if sinal > 0 else tema_asg.NEXO_ROSA)
        # 4. barra do rodape (pressao.py compoe a partir da mesma forca)
        compra = 50.0 + pressao.pressao_composta(linha.forca, 0.0) * 50.0
        assert (compra > 50.0) == (sinal > 0), (
            "a barra 73/27 nascia deste score com o sinal invertido em "
            "relacao ao medidor logo acima"
        )


def test_suavizacao_do_maker_nao_desencontra_sinal_de_grandeza():
    """A media movel pode discordar do score cru — mas entao TODAS as portas
    da leitura passam a mostrar a media, nunca uma cada."""
    from collections import deque
    from fluxopro.ui.paineis import asg

    class _Falso:
        _historico_forca_maker = deque([0.9, 0.8, 0.7, 0.75, 0.5], maxlen=5)
        _forca_maker_suavizada = asg.PainelNexoMercadoASG._forca_maker_suavizada
        _linha_maker_coerente = asg.PainelNexoMercadoASG._linha_maker_coerente

    crua = _linha("PRESENCA", -0.33, ConfiancaASG.ALTA, DirecaoASG.VENDA)[1]
    saida = _Falso()._linha_maker_coerente(crua)
    assert saida.forca > 0
    assert saida.direcao is DirecaoASG.COMPRA, (
        "com a media movel positiva, a direcao NAO pode continuar VENDA do cru"
    )
    assert asg.leitura_e_coerente(saida)
    assert "MM5" in saida.valor, "o texto tem de declarar que e media movel"


def test_leitura_e_coerente_reprova_sinais_opostos():
    from fluxopro.ui.paineis import asg

    ruim = _linha("PRESENCA", 0.73, ConfiancaASG.ALTA, DirecaoASG.VENDA)[1]
    assert not asg.leitura_e_coerente(ruim)
    bom = _linha("PRESENCA", 0.73, ConfiancaASG.ALTA, DirecaoASG.COMPRA)[1]
    assert asg.leitura_e_coerente(bom)


def test_forca_ritmo_zero_nao_imprime_menos_zero():
    from fluxopro.ui.paineis import asg

    valor = asg._forca_ritmo_composta(1.0, "PARADO", -1.0)
    assert f"{valor * 100:+.0f}%" == "+0%", "zero nao tem lado"


def test_nenhuma_porta_imprime_menos_zero():
    """A guarda do RITMO era LOCAL; o MakerProxy sobrevivia imprimindo `-0%`.

    No retrato de 28/08 o mesmo zero negativo saia por tres portas ao mesmo
    tempo — mostrador EQUILIBRIO (`-0%`), ladrilho PRESENCA (`-0%`) e texto
    pequeno (`-0% MM5`) — todas ja pintadas de NEUTRA, so com o sinal errado.
    Este teste varre a linha inteira, nao um componente.
    """

    from fluxopro.ui.paineis import asg

    linha = _linha("PRESENCA", 0.42, ConfiancaASG.ALTA, DirecaoASG.COMPRA)[1]

    for entrada in (-0.0, -1e-12, 0.0):
        saida = asg._linha_com_forca(linha, entrada)
        assert saida.direcao is DirecaoASG.NEUTRA
        assert f"{saida.forca * 100:+.0f}%" == "+0%", (
            f"forca {entrada!r} imprimiu sinal num zero")
        assert saida.valor.startswith("+0%"), saida.valor

    # E o contrario: um zero de verdade nao pode engolir uma leitura viva.
    viva = asg._linha_com_forca(linha, -0.004)
    assert viva.direcao is DirecaoASG.VENDA
    assert viva.forca == -0.004


# --- a TERCEIRA porta: o cartao REGIME do visor central --------------------
#
# O defeito da familia renasceu aqui: `nucleo.py` pintava o valor direcional
# do REGIME (COMPRADOR/VENDEDOR) em ciano FIXO, sem eixo de cor. A leitura
# agora atravessa a fronteira inteira e coerente, em `EstadoNexo.regime`,
# para que quem desenha so consuma a cor da direcao.

def _matriz_com_regime(nome_regime):
    from fluxopro.ui.paineis import asg

    leitura = {
        "macro": {"macro": {"valor": 100}},
        "micro": {"micro": {"valor": 10}},
        "linha_azul": {"fracao_compradora": 0.5, "nivel": 10, "lado": "SEM_LINHA"},
        "regime": {"regime": nome_regime},
        "velocimetro": {"estado": "PARADO", "sentido": None, "magnitude_relativa": 0.0},
    }
    return asg._linhas_da_matriz_asg(leitura, None, asg.EstadoASG.AO_VIVO)


def test_regime_carrega_direcao_e_forca_no_mesmo_sinal():
    from fluxopro.ui.paineis import asg
    from fluxopro.ui import tema_asg

    esperado = {
        "COMPRADOR": (DirecaoASG.COMPRA, tema_asg.NEXO_VERDE),
        "VENDEDOR": (DirecaoASG.VENDA, tema_asg.NEXO_ROSA),
    }
    for nome, (direcao, cor) in esperado.items():
        regime = next(l for l in _matriz_com_regime(nome) if l.componente == "REGIME")
        assert regime.direcao is direcao
        assert asg.leitura_e_coerente(regime), f"{nome}: palavra e sinal em desacordo"
        # A porta que faltava: a COR que o cartao central deve usar sai da
        # mesma direcao, nunca de um token fixo.
        assert asg._cor_nexo_direcao(regime.direcao) is cor
        assert asg.sinal_da_leitura(regime) == (1 if direcao is DirecaoASG.COMPRA else -1)


def test_estado_nexo_expoe_regime_coerente_para_quem_desenha():
    """O painel so publica a linha REGIME se ela for coerente."""
    from fluxopro.ui.paineis import asg

    class _Falso:
        _linha_regime = asg.PainelNexoMercadoASG._linha_regime

        class _snapshot:
            class matriz:
                linhas = _matriz_com_regime("VENDEDOR")

    regime = _Falso()._linha_regime()
    assert regime is not None
    assert regime.direcao is DirecaoASG.VENDA
    assert asg.leitura_e_coerente(regime)


def test_regime_incoerente_nao_atravessa_a_fronteira():
    from fluxopro.ui.paineis import asg

    envenenada = LinhaMatrizASG(
        componente="REGIME", direcao=DirecaoASG.COMPRA, valor="COMPRADOR",
        forca=-1.0, confianca=ConfiancaASG.MEDIA, procedencia=ProcedenciaASG.DERIVADO,
    )

    class _Falso:
        _linha_regime = asg.PainelNexoMercadoASG._linha_regime

        class _snapshot:
            class matriz:
                linhas = (envenenada,)

    assert _Falso()._linha_regime() is None, (
        "palavra e sinal em desacordo nao podem chegar a tela"
    )


class _MakerFalso:
    """`maker` minimo aceito por `_linhas_da_matriz_asg`."""

    def __init__(self, pontuacao, confianca=0.8):
        self.pontuacao = pontuacao
        self.confianca = confianca
        self.componentes = ()
        self.evidence = ()
        self.persistence_ns = 0
        self.procedencia = ""


def _matriz(regime="COMPRADOR", fracao=0.5, lado_linha="SEM_LINHA",
            vel_estado="PARADO", vel_sentido=None, vel_mag=0.0,
            macro=100, micro=10, maker=0.0):
    from fluxopro.ui.paineis import asg

    leitura = {
        "macro": {"macro": {"valor": macro}},
        "micro": {"micro": {"valor": micro}},
        "linha_azul": {"fracao_compradora": fracao, "nivel": 10, "lado": lado_linha},
        "regime": {"regime": regime},
        "velocimetro": {
            "estado": vel_estado, "sentido": vel_sentido, "magnitude_relativa": vel_mag,
        },
    }
    return asg._linhas_da_matriz_asg(leitura, _MakerFalso(maker), asg.EstadoASG.AO_VIVO)


# Cada cenario exercita os SEIS componentes com estado NAO-NULO — o defeito
# da rodada 3 era exatamente este: a varredura antiga rodava sobre uma
# fixture em que MAKERPROXY, LINHA AZUL e VELOCIMETRO saiam com forca 0,0 e
# direcao NEUTRA, e a assercao era vazia para metade da matriz (inclusive
# para o MakerProxy, a origem da familia).
_CENARIOS_NAO_NULOS = (
    ("tudo comprador", dict(regime="COMPRADOR", fracao=0.8, lado_linha="ACIMA",
                            vel_estado="ACELERANDO", vel_sentido="COMPRA", vel_mag=0.9,
                            macro=900, micro=60, maker=0.7)),
    ("tudo vendedor", dict(regime="VENDEDOR", fracao=0.2, lado_linha="ABAIXO",
                           vel_estado="ACELERANDO", vel_sentido="VENDA", vel_mag=0.9,
                           macro=-900, micro=-60, maker=-0.7)),
    ("cruzado", dict(regime="COMPRADOR", fracao=0.2, lado_linha="ABAIXO",
                     vel_estado="DESACELERANDO", vel_sentido="VENDA", vel_mag=0.6,
                     macro=900, micro=-60, maker=-0.4)),
    ("cruzado inverso", dict(regime="VENDEDOR", fracao=0.9, lado_linha="ACIMA",
                             vel_estado="MANTENDO", vel_sentido="COMPRA", vel_mag=0.5,
                             macro=-900, micro=60, maker=0.4)),
    ("virou", dict(regime="INDEFINIDO", fracao=0.6, lado_linha="ACIMA",
                   vel_estado="VIROU", vel_sentido="VENDA", vel_mag=0.8,
                   macro=5, micro=-1, maker=-0.05)),
)

_COMPONENTES_DIRECIONAIS = ("MACRO", "MICRO", "LINHA AZUL", "REGIME",
                            "MAKERPROXY", "VELOCIMETRO")


def test_varredura_exercita_todo_componente_com_estado_nao_nulo():
    """Guarda da guarda: prova que a varredura NAO esta fora do cenario.

    Um invariante que so ve forca 0,0 nao prova nada. Este teste exige que
    cada um dos seis componentes apareca com forca != 0 em pelo menos um
    cenario — se alguem enfraquecer as fixtures, ele cai antes de o
    invariante virar decorativo.
    """
    from fluxopro.ui.paineis import asg

    vistos_nao_nulos = set()
    for _, kwargs in _CENARIOS_NAO_NULOS:
        for linha in _matriz(**kwargs):
            if linha.forca != 0.0:
                vistos_nao_nulos.add(linha.componente)
    faltando = set(_COMPONENTES_DIRECIONAIS) - vistos_nao_nulos
    assert not faltando, f"componentes nunca exercitados com forca != 0: {faltando}"
    assert asg is not None


def test_toda_leitura_direcional_e_coerente_em_todo_cenario():
    """A varredura de verdade: seis componentes x cinco cenarios nao-nulos."""
    from fluxopro.ui.paineis import asg

    for nome_cenario, kwargs in _CENARIOS_NAO_NULOS:
        for linha in _matriz(**kwargs):
            coerida = asg._coerir_leitura(linha)
            assert asg.leitura_e_coerente(coerida), (
                f"{nome_cenario} · {linha.componente}: forca {coerida.forca} "
                f"contra direcao {coerida.direcao}"
            )
            assert asg.sinal_da_leitura(coerida) == (
                (coerida.forca > 0) - (coerida.forca < 0)
            ), f"{nome_cenario} · {linha.componente}: sinal do rotulo != sinal do numero"


def test_o_invariante_REPROVA_o_bug_historico_do_makerproxy():
    """A combinacao exata que originou a familia: media movel de um sinal,
    cru do outro. Se este teste passar a aprovar, o invariante quebrou."""
    from dataclasses import replace as _replace
    from fluxopro.ui.paineis import asg

    crua = next(l for l in _matriz(maker=-0.33) if l.componente == "MAKERPROXY")
    assert crua.direcao is DirecaoASG.VENDA

    # O bug literal de 27/08: trocar SO a forca, deixando direcao/valor no cru.
    envenenada = _replace(crua, forca=0.73)
    assert not asg.leitura_e_coerente(envenenada), (
        "o invariante TEM de reprovar +73% pintado com a direcao VENDA do cru"
    )

    # E o portao de producao conserta em vez de deixar passar.
    corrigida = asg._coerir_leitura(envenenada)
    assert corrigida.direcao is DirecaoASG.COMPRA
    assert asg.leitura_e_coerente(corrigida)


def test_suavizacao_contra_cru_nos_dois_sentidos():
    """Maker cru negativo com media positiva, e o inverso."""
    from collections import deque
    from fluxopro.ui.paineis import asg

    def _painel(historico):
        class _Falso:
            _historico_forca_maker = deque(historico, maxlen=5)
            _forca_maker_suavizada = asg.PainelNexoMercadoASG._forca_maker_suavizada
            _linha_maker_coerente = asg.PainelNexoMercadoASG._linha_maker_coerente
        return _Falso()

    casos = (
        (-0.33, [0.9, 0.8, 0.7, 0.75, 0.5], DirecaoASG.COMPRA),
        (0.42, [-0.9, -0.8, -0.7, -0.75, -0.5], DirecaoASG.VENDA),
    )
    for cru, historico, esperada in casos:
        linha_crua = next(l for l in _matriz(maker=cru) if l.componente == "MAKERPROXY")
        saida = _painel(historico)._linha_maker_coerente(linha_crua)
        assert saida.direcao is esperada, f"cru {cru} com media {historico[0]}"
        assert asg.leitura_e_coerente(saida)
        assert saida.valor.startswith("+") == (esperada is DirecaoASG.COMPRA)


def test_forca_zero_com_direcao_declarada_e_incoerente():
    """Zero nao tem lado — e por isso nao pode ser pintado de verde.

    Caso real: VELOCIMETRO PARADO com `sentido` definido produzia um
    ladrilho verde escrito "+0%".
    """
    from fluxopro.ui.paineis import asg

    parada = LinhaMatrizASG(
        componente="VELOCIMETRO", direcao=DirecaoASG.COMPRA, valor="PARADO",
        forca=0.0, confianca=ConfiancaASG.MEDIA, procedencia=ProcedenciaASG.DERIVADO,
    )
    assert not asg.leitura_e_coerente(parada)
    assert asg._coerir_leitura(parada).direcao is DirecaoASG.NEUTRA


def test_o_portao_vale_para_as_QUATRO_leituras_que_vao_a_tela():
    """Ate a rodada 3 o gate existia em UM ponto so (o REGIME) e
    HORIZONTE/PULSO/PRESENCA/RITMO desenhavam sem passar por ele."""
    from collections import deque
    from dataclasses import replace as _replace
    from fluxopro.ui.paineis import asg

    linhas = list(_matriz(**_CENARIOS_NAO_NULOS[0][1]))
    # Envenena as duas leituras que chegam a tela sem recalculo proprio.
    for indice, linha in enumerate(linhas):
        if linha.componente in ("MACRO", "VELOCIMETRO"):
            linhas[indice] = _replace(linha, direcao=DirecaoASG.VENDA
                                      if linha.forca > 0 else DirecaoASG.COMPRA)

    class _Falso:
        _historico_forca_maker = deque([0.7], maxlen=5)
        _forca_maker_suavizada = asg.PainelNexoMercadoASG._forca_maker_suavizada
        _linha_maker_coerente = asg.PainelNexoMercadoASG._linha_maker_coerente
        _linhas_contexto_nexo = asg.PainelNexoMercadoASG._linhas_contexto_nexo

        class _snapshot:
            class matriz:
                pass

    _Falso._snapshot.matriz.linhas = tuple(linhas)
    leituras = _Falso()._linhas_contexto_nexo()

    assert {nome for nome, _ in leituras} == {"HORIZONTE", "PULSO", "PRESENCA", "RITMO"}
    for nome, linha in leituras:
        assert asg.leitura_e_coerente(linha), (
            f"{nome} chegou a tela com forca {linha.forca} e direcao {linha.direcao}"
        )
