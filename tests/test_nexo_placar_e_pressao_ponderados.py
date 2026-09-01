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


def test_animais_espelham_a_mesma_pressao_sem_criar_segundo_sinal():
    touro_compra, urso_compra = pressao.intensidades_animais(0.8, tem_leitura=True)
    touro_venda, urso_venda = pressao.intensidades_animais(-0.8, tem_leitura=True)
    assert touro_compra > urso_compra
    assert urso_venda > touro_venda
    assert pressao.intensidades_animais(0.0, tem_leitura=True)[0] == pressao.intensidades_animais(0.0, tem_leitura=True)[1]


def test_animais_ficam_neutros_sem_leitura_publicavel():
    assert pressao.intensidades_animais(1.0, tem_leitura=False) == (
        pressao.OPACIDADE_ANIMAL_NEUTRO,
        pressao.OPACIDADE_ANIMAL_NEUTRO,
    )


def test_animais_aprovados_estao_empacotados_e_sem_fundo_opaco(qapp):
    for touro in (True, False):
        sprite = pressao._sprite_animal(touro)
        assert not sprite.isNull(), "A instalação deve incluir os animais aprovados"
        imagem = sprite.toImage()
        cores = [imagem.pixelColor(x, y) for y in range(imagem.height())
                 for x in range(imagem.width())]
        assert any(c.alpha() == 0 for c in cores), "Fundo deve ser transparente"
        assert sum(c.alpha() > 128 for c in cores) > 100, "Animal deve estar visível"
        assert pressao._sprite_animal(touro).cacheKey() == sprite.cacheKey()


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


def _painel_com_volante(valor):
    """Painel falso cujo volante ja acomodou em `valor`.

    O volante e estado puro (posicao + velocidade + periodo), entao para o
    teste basta posicionar o ponteiro e declarar que ele ja andou — nao ha
    Qt nem snapshot envolvidos.
    """

    from fluxopro.ui.paineis import asg

    volante = asg.VolanteGauge()
    volante.valor = valor
    volante._ts_ns = 1

    class _Falso:
        _volante_maker = volante
        _forca_maker_suavizada = asg.PainelNexoMercadoASG._forca_maker_suavizada
        _linha_maker_coerente = asg.PainelNexoMercadoASG._linha_maker_coerente

    return _Falso()


def test_suavizacao_do_maker_nao_desencontra_sinal_de_grandeza():
    """O numero suavizado pode discordar do score cru — mas entao TODAS as
    portas da leitura passam a mostrar o suavizado, nunca uma cada."""
    from fluxopro.ui.paineis import asg

    _Falso = lambda: _painel_com_volante(0.73)  # noqa: E731

    crua = _linha("PRESENCA", -0.33, ConfiancaASG.ALTA, DirecaoASG.VENDA)[1]
    saida = _Falso()._linha_maker_coerente(crua)
    assert saida.forca > 0
    assert saida.direcao is DirecaoASG.COMPRA, (
        "com o volante positivo, a direcao NAO pode continuar VENDA do cru"
    )
    assert asg.leitura_e_coerente(saida)
    assert "SUAV" in saida.valor, "o texto tem de declarar que nao e o cru"


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
    pequeno (`-0% SUAV`) — todas ja pintadas de NEUTRA, so com o sinal errado.
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
    """Maker cru negativo com ponteiro positivo, e o inverso."""
    from fluxopro.ui.paineis import asg

    casos = (
        (-0.33, 0.73, DirecaoASG.COMPRA),
        (0.42, -0.73, DirecaoASG.VENDA),
    )
    for cru, ponteiro, esperada in casos:
        linha_crua = next(l for l in _matriz(maker=cru) if l.componente == "MAKERPROXY")
        saida = _painel_com_volante(ponteiro)._linha_maker_coerente(linha_crua)
        assert saida.direcao is esperada, f"cru {cru} com ponteiro {ponteiro}"
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
    from dataclasses import replace as _replace
    from fluxopro.ui.paineis import asg

    linhas = list(_matriz(**_CENARIOS_NAO_NULOS[0][1]))
    # Envenena as duas leituras que chegam a tela sem recalculo proprio.
    for indice, linha in enumerate(linhas):
        if linha.componente in ("MACRO", "VELOCIMETRO"):
            linhas[indice] = _replace(linha, direcao=DirecaoASG.VENDA
                                      if linha.forca > 0 else DirecaoASG.COMPRA)

    _volante = asg.VolanteGauge()
    _volante.valor = 0.7
    _volante._ts_ns = 1

    class _Falso:
        _volante_maker = _volante
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


# ---------------------------------------------------------------------------
# Volante do termometro de agressao (P8) — o pedido do operador era "igual um
# contragiro de carro que acelera e desacelera gradualmente", e extremos "so
# quando existe agressoes muito grandes em relacao ao periodo, constantemente".
# Cada teste abaixo prende UMA dessas propriedades. Todos rodam sem Qt: o
# volante e estado puro.
# ---------------------------------------------------------------------------


def _serie_no_volante(pares):
    """`pares` = [(segundos, score cru)] -> leitura do mostrador."""
    from fluxopro.ui.paineis import asg

    volante = asg.VolanteGauge()
    return [volante.avancar(cru, round(s * 1_000_000_000)) for s, cru in pares]


def test_volante_respeita_o_teto_de_taxa_mesmo_em_rajada():
    """O defeito que a media movel de 5 amostras NAO cobria.

    MM5 limita o passo por AMOSTRA; se cinco snapshots chegam em 200 ms
    (medido: o menor intervalo real entre snapshots foi 0,28 s), o mostrador
    ainda atravessa 0,4 de escala em 0,2 s. O volante limita por SEGUNDO.
    """
    from fluxopro.ui.paineis import asg

    passo = 0.05  # 50 ms entre snapshots: rajada
    pares = [(i * passo, 1.0) for i in range(1, 200)]
    saida = _serie_no_volante(pares)
    for anterior, atual in zip(saida, saida[1:]):
        taxa = abs(atual - anterior) / passo
        assert taxa <= asg.TAXA_MAX_VOLANTE_POR_SEGUNDO + 1e-9, (
            f"ponteiro girou a {taxa:.3f}/s, acima do teto de contragiro"
        )


def test_volante_leva_no_minimo_a_travessia_declarada_de_ponta_a_ponta():
    """Do zero ao fundo de escala nao pode acontecer em um quadro."""
    from fluxopro.ui.paineis import asg

    # Periodo calmo primeiro (senao o proprio +1,0 vira a "agressao tipica"
    # do periodo e nunca e fundo de escala — ver o teste do periodo abaixo).
    # Ruido de sinal alternado: a zona morta prende o ponteiro no zero, que
    # e de onde a travessia tem de partir para o teste medir a travessia.
    calmo = [(i * 0.25, 0.02 if i % 2 else -0.02) for i in range(1, 200)]
    pares = calmo + [(50.0 + i * 0.25, 1.0) for i in range(1, 400)]
    saida = _serie_no_volante(pares)
    # A rampa comeca no ULTIMO snapshot calmo: e dele que sai o dt do
    # primeiro passo em direcao ao novo alvo.
    inicio = pares[len(calmo) - 1][0]
    tempo_ate_90 = next(pares[i][0] for i, v in enumerate(saida) if v >= 0.9) - inicio
    minimo = 0.9 / asg.TAXA_MAX_VOLANTE_POR_SEGUNDO
    assert tempo_ate_90 >= minimo, (
        f"chegou a 90% da escala em {tempo_ate_90:.1f}s de agressao "
        f"sustentada; o teto de taxa "
        f"exige pelo menos {minimo:.1f}s de agressao sustentada"
    )


def test_volante_desacelera_ao_chegar_no_alvo():
    """'acelera E DESACELERA gradualmente': perto do alvo o passo encolhe.

    Um limitador de taxa puro chega em velocidade de cruzeiro e para em
    degrau; este nao.
    """
    pares = [(i * 0.25, 1.0) for i in range(1, 400)]
    saida = _serie_no_volante(pares)
    passos = [abs(b - a) for a, b in zip(saida, saida[1:])]
    maior = max(passos)
    indice = passos.index(maior)
    finais = passos[-8:]
    assert max(finais) < maior / 2, (
        "o ponteiro chegou ao alvo sem desacelerar (passo final ~ passo de "
        f"cruzeiro {maior:.4f} do indice {indice})"
    )


def test_volante_nao_troca_de_lado_em_cima_de_epsilon():
    """A zona morta com histerese: sem ela `_direcao_de_score` vira a COR do
    mostrador a partir de 1e-9, e o termometro pisca."""
    pares = []
    for i in range(1, 300):
        pares.append((i * 0.5, 0.04 if i % 2 else -0.04))
    saida = _serie_no_volante(pares)
    assert all(v == 0.0 for v in saida), (
        "ruido em torno do zero tirou o mostrador do EQUILIBRIO"
    )


def test_volante_exige_agressao_grande_PARA_O_PERIODO_para_o_fundo_de_escala():
    """Mesmo score cru, dois periodos diferentes, leituras diferentes.

    Em um periodo que ja vinha entregando +1,0 o tempo todo, um +1,0 nao e
    extremo nenhum — e o que o operador escreveu com todas as letras.
    """
    from fluxopro.ui.paineis import asg

    calmo = asg.VolanteGauge()
    agitado = asg.VolanteGauge()
    t = 0
    for _ in range(60):
        t += 1_000_000_000
        calmo.avancar(0.1, t)
        agitado.avancar(1.0, t)
    # Agora o MESMO pico de +1,0, sustentado, nos dois.
    for _ in range(60):
        t += 1_000_000_000
        calmo.avancar(1.0, t)
        agitado.avancar(1.0, t)
    assert calmo.valor > agitado.valor, (
        f"periodo calmo leu {calmo.valor:.2f} e periodo ja saturado leu "
        f"{agitado.valor:.2f}; o mesmo +1,0 tem de valer MAIS onde e raro"
    )
    assert agitado.valor <= 1.0 / asg.Z_EXTREMO_VOLANTE + 1e-6, (
        "pressao cravada o periodo inteiro nao pode ler como extremo"
    )


def test_volante_nao_avanca_no_caminho_de_pintura():
    """`_forca_maker_suavizada` e LEITURA. Pintar o mesmo quadro duas vezes
    tem de dar o mesmo numero — quem integra o tempo e `aplicar`."""
    from fluxopro.ui.paineis import asg

    painel = _painel_com_volante(0.42)
    primeira = painel._forca_maker_suavizada(-0.9)
    segunda = painel._forca_maker_suavizada(-0.9)
    assert primeira == segunda == 0.42


def test_volante_sem_snapshot_ainda_mostra_o_cru():
    """Antes do primeiro timestamp nao ha leitura propria — e ai o painel
    nao pode inventar zero no lugar do dado."""
    from fluxopro.ui.paineis import asg

    class _Falso:
        _volante_maker = asg.VolanteGauge()
        _forca_maker_suavizada = asg.PainelNexoMercadoASG._forca_maker_suavizada

    assert _Falso()._forca_maker_suavizada(-0.73) == -0.73


def test_represamento_conta_so_enquanto_o_ponteiro_esta_preso_no_equilibrio():
    """`segundos_represado` mede UM estado especifico: mostrador em
    EQUILIBRIO tendo agressao de um lado so para mostrar.

    Existe para o custo do volante ir a tela. Se ele contasse tambem o
    tempo em que o ponteiro esta parado no lado ANTERIOR, o aviso da tela
    estaria medindo outra coisa que nao a que ele diz medir.
    """
    from fluxopro.ui.paineis import asg

    volante = asg.VolanteGauge()
    t = 0
    # 60 s de fluxo fraco de um lado so: alvo existe, mas nao vence a zona
    # morta contra o proprio periodo.
    for _ in range(60):
        t += 1_000_000_000
        volante.avancar(0.10 if t % 2_000_000_000 else 0.08, t)
    assert volante.valor == 0.0, "o ponteiro devia estar preso no EQUILIBRIO"
    assert volante.segundos_represado(t) > 0.0, (
        "ha agressao de um lado so e o mostrador esta em zero: isso e "
        "represamento e tem de ser contado"
    )
    # Agressao forte: solta o ponteiro e zera o contador.
    for _ in range(40):
        t += 1_000_000_000
        volante.avancar(1.0, t)
    assert volante.valor > 0.0
    assert volante.segundos_represado(t) == 0.0, (
        "com o ponteiro solto nao ha represamento a declarar"
    )


def test_represamento_nao_conta_antes_de_haver_agressao():
    """Mercado parado nao e represamento — e mercado parado."""
    from fluxopro.ui.paineis import asg

    volante = asg.VolanteGauge()
    t = 0
    for _ in range(60):
        t += 1_000_000_000
        volante.avancar(0.0, t)
    assert volante.segundos_represado(t) == 0.0


def test_rotulo_da_regiao_so_avisa_acima_do_limiar_medido():
    """O aviso na tela e o custo declarado; ele nao pode aparecer no
    comportamento NORMAL do mostrador (p90 de 4,5 s no regime forte)."""
    from fluxopro.ui.paineis.nexo import contexto

    limiar = contexto.SEGUNDOS_PARA_AVISAR_REPRESAMENTO
    assert contexto.rotulo_regiao(0.0) == contexto.ROTULO_REGIAO
    assert contexto.rotulo_regiao(limiar - 0.1) == contexto.ROTULO_REGIAO
    aviso = contexto.rotulo_regiao(limiar + 0.5)
    assert aviso.startswith(contexto.ROTULO_REGIAO)
    assert "AGRESSAO FRACA" in aviso
    assert contexto.rotulo_regiao(226.0).endswith("3M46S"), (
        "o tempo represado tem de ser legivel como tempo, nao como float"
    )
