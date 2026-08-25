#!/usr/bin/env python
"""Abre o painel grafico do FluxoPro sobre o MESMO pipeline do CLI.

    python scripts/painel.py --fonte simulador --simbolo WDOV26 --seed 42
    python scripts/painel.py --fonte replay --arquivo dados/ --simbolo WDOV26
    python scripts/painel.py --fonte mt5 --simbolo WDOFUT

Reaproveita `scripts/operar.py` inteiro para linha de comando e montagem: os
mesmos limiares de calibracao, a mesma fonte de dados, o mesmo barramento. O
painel e um CONSUMIDOR a mais no barramento, nao um segundo caminho — se ele
mostrasse numero diferente do CLI, um dos dois estaria mentindo.

Modo SINAIS e sempre: este programa nao envia ordem para lugar nenhum — e
isso esta escrito na COLUNA DA DECISAO da tela, nao so aqui.

Tambem e o gerador de retrato da composicao, e de proposito:

    python scripts/painel.py --fonte simulador --seed 11 --taxa-eventos-s 900 \\
        --dominancia-minima 0.525 --magnitude-relativa-minima 0.20 \\
        --retrato design/retrato_composicao.png --duracao 22

Um script de retrato paralelo montaria a janela por conta propria e passaria
a retratar a si mesmo: foi assim que `PainelMatriz` e `PainelHUD` viveram uma
onda inteira sem estar montados no produto. Aqui o PNG e da MESMA janela que
o operador abre, e qualquer divergencia entre o retrato e o produto e um
defeito do produto.

E como este comando aceita calibrar o motor, ele **carimba a calibracao na
imagem** (`ressalva_da_config`). Nao ha caminho para gerar um retrato
calibrado sem a tarja.

A fonte roda numa thread propria porque `fonte.iniciar()` bloqueia ate o fim
do pregao (ver `operar.py`). A thread do Qt nunca toca no dominio: ela le o
retrato que `ui/ponte.py` deixou pronto.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
import threading
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRect, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from fluxopro.app.config import ConfigOperacao, FonteDados  # noqa: E402
from fluxopro.app.montagem import FonteIndisponivelError, montar  # noqa: E402
from fluxopro.app.sessao_fluxo import SessaoFluxo  # noqa: E402
from fluxopro.core.barramento import Barramento  # noqa: E402
from fluxopro.motor.sinais import ConfigMotorSinais  # noqa: E402
from fluxopro.ui import tokens  # noqa: E402
from fluxopro.ui.janela import (  # noqa: E402
    PARAMETROS_EM_VIGOR,
    JanelaFluxo,
    formatar_limiar,
)
from fluxopro.ui.paineis.asg import (  # noqa: E402
    ConfiancaASG,
    ContextoBrutoASGSnapshot,
    DadosASGSnapshot,
    DecisaoASGSnapshot,
    DirecaoASG,
    EstadoASG,
    EtapaProcessamentoASG,
    EvidenciaASG,
    GateDecisaoASG,
    LinhaMatrizASG,
    MatrizASGSnapshot,
    NegocioBrutoASG,
    NivelBrutoASG,
    ProcessamentoASGSnapshot,
    ProcedenciaASG,
    ResultadoGate,
    TrilhaEvidenciasASGSnapshot,
    WorkspaceASGSnapshot,
)
from fluxopro.ui.paineis.replay import EstadoReplay  # noqa: E402
from fluxopro.ui.ponte import Contadores, EstadoFeed, Instantaneo, ItemTape, PonteFluxo  # noqa: E402
from fluxopro.core.eventos import (  # noqa: E402
    AgressorSide,
    BookLevel,
    BookSnapshot,
    Trade,
)
from fluxopro.ui.trilha import TrilhaEventos  # noqa: E402
from fluxopro.ui.workspace import (  # noqa: E402
    NOMES_DE_ENTRADA,
    WORKSPACES_DISPONIVEIS,
    por_nome,
)
from scripts.operar import (  # noqa: E402
    config_de_args,
    construir_parser,
    opcoes_replay_de_args,
)

_logger = logging.getLogger("scripts.painel")

_DENSIDADES = {d.nome.lower(): d for d in tokens.DENSIDADES}

GIL_SWITCH_PADRAO = 0.0005
"""Intervalo de troca de GIL, em segundos, SO neste processo.

Achado que so apareceu rodando o painel sob carga de verdade — nenhum
benchmark isolado o mostrava. A fonte roda numa thread propria, e o
simulador (como o replay em `--velocidade max`) e um produtor **sem espera
nenhuma**: ele nao faz I/O, entao segura o GIL continuamente. Com o padrao
do CPython (5 ms), a thread do Qt esperava ~12 ms para conseguir o GIL a
cada quadro.

O que denunciou foi separar `time.thread_time()` de `time.perf_counter()`:
o custo de CPU do quadro do DOM e **sub-milissegundo**, e os 12 ms eram
espera pura. (Com `time.process_time()` a conta some, porque ele soma a CPU
de TODAS as threads e o produtor entra na medida — cheguei a ler o numero
errado assim antes de trocar o relogio.)

Medido por `bench_ui_carga.py`, 2 s de simulador inundando, 1280x800, com o
pipeline COMPLETO (inclusive `metodologia` ligada):

| troca  | ingestao   | quadros/2s | 
|--------|------------|-----------|
| 5 ms (padrao CPython) | 2.318 ev/s | 16 |
| 1 ms                  | 2.375 ev/s | 17 |
| **0,5 ms**            | **898 ev/s** | **121** |

**Este numero JA envelheceu uma vez, e por isso o benchmark existe.** A
tabela anterior media 1 ms comprando 230 quadros contra 90 do padrao, e a
escolha de 1 ms saiu dali. Depois que `fluxopro/metodologia/` entrou no
caminho quente, o pipeline ficou mais caro por evento, o produtor
desacelerou sozinho, e **1 ms deixou de comprar coisa alguma** — 17 contra
16. So 0,5 ms ainda separa.

E um dial, nao uma correcao: fluidez de tela e vazao de ingestao disputam a
mesma CPU, e o ponto de equilibrio se move quando o pipeline muda de peso.
Com feed REAL o produtor e I/O-bound (o MT5 dorme entre consultas) e devolve
o GIL sozinho — a disputa so e severa com produtor sintetico ou replay
acelerado, que e justamente quando o operador esta olhando a tela. 898 ev/s
de INUNDACAO sintetica nao e o teto de ingestao de um feed real.

Rode `python bench_ui_carga.py` depois de mexer no caminho quente. Nao ha
teste vigiando isto: duas tentativas de transformar a medicao em portao de
CI sairam instaveis, e o motivo esta escrito no benchmark.

Fica aqui e nao no nucleo de proposito: `scripts/operar.py` e headless e
existe para vazao, entao mexer no relogio do interpretador dele seria
cobrar um preco por um beneficio que ele nao usa."""


TITULO_SIMULADOR = "DADOS DE SIMULADOR — NÃO É PREGÃO"
TITULO_CALIBRADO = "MOTOR CALIBRADO — ESTA TELA NÃO USA OS CORTES DE PRODUÇÃO"
TITULO_AMBOS = "DADOS DE SIMULADOR E MOTOR CALIBRADO — NÃO É PREGÃO"

_T0_EVIDENCIA_ASG = 1_777_200_000_000_000_000


def quadro_evidencia_asg(estado: EstadoASG) -> WorkspaceASGSnapshot:
    """Fixture sintetica e rotulada para retratos de estados do produto.

    Nao percorre fonte, ponte ou sessao e, portanto, nao e evidencia e2e.
    Serve para exercitar a composicao completa da janela com uma fixture
    deterministica e declarada na propria imagem.
    """

    t = _T0_EVIDENCIA_ASG
    saudavel = estado in {EstadoASG.AO_VIVO, EstadoASG.REPLAY}
    procedencia = (
        ProcedenciaASG.REPLAY
        if estado is EstadoASG.REPLAY
        else ProcedenciaASG.DERIVADO
    )
    confianca = ConfiancaASG.ALTA if saudavel else ConfiancaASG.INDISPONIVEL
    dados = DadosASGSnapshot(
        timestamp_ns=t,
        estado=estado,
        fonte="REPLAY" if estado is EstadoASG.REPLAY else "MT5",
        sequencia=184_221,
        atraso_ms=8.4 if saudavel else 3_250.0,
        trades_s=146.0,
        niveis_book=0 if estado is EstadoASG.SEM_BOOK else 20,
        gaps=0,
        anomalias=0 if saudavel else 1,
        descartados=0,
        confianca=confianca,
        procedencia=procedencia,
        detalhe=f"CENARIO CONGELADO DE EVIDENCIA · {estado.value}",
    )
    nomes_etapas = ("AGRESSAO", "DELTA", "ABSORCAO", "REPOSICAO", "CLIPS")
    processamento = ProcessamentoASGSnapshot(
        timestamp_ns=t,
        estado=estado,
        versao="maker-proxy-v1",
        etapas=tuple(
            EtapaProcessamentoASG(
                nome,
                "ATIVO" if saudavel else "BLOQUEADO",
                0.4 + indice / 10,
                confianca,
                procedencia,
                "evidencia sintetica de interface",
            )
            for indice, nome in enumerate(nomes_etapas)
        ),
    )
    componentes = (
        ("MACRO", DirecaoASG.COMPRA, "+2"),
        ("MICRO", DirecaoASG.COMPRA, "+3"),
        ("LINHA AZUL", DirecaoASG.COMPRA, "5.086t"),
        ("REGIME", DirecaoASG.NEUTRA, "ROTACAO"),
        ("MAKERPROXY", DirecaoASG.COMPRA, "+42%"),
        ("VELOCIMETRO", DirecaoASG.COMPRA, "+0,68"),
    )
    matriz = MatrizASGSnapshot(
        timestamp_ns=t,
        estado=estado,
        linhas=tuple(
            LinhaMatrizASG(
                nome,
                direcao,
                valor,
                0.68 if direcao is DirecaoASG.COMPRA else 0.0,
                confianca,
                procedencia,
                4,
                "proxy independente",
            )
            for nome, direcao, valor in componentes
        ),
        cobertura="100%" if saudavel else "BLOQUEADA",
    )
    gate_resultado = ResultadoGate.PASSA if saudavel else ResultadoGate.BLOQUEIA
    decisao = DecisaoASGSnapshot(
        timestamp_ns=t,
        estado=estado,
        direcao=DirecaoASG.COMPRA if saudavel else DirecaoASG.AGUARDAR,
        titulo="CONFIRMACAO A1" if saudavel else "SEM DECISAO",
        motivo=(
            "regiao valida · fluxo confirmado"
            if saudavel
            else f"bloqueado pelo estado {estado.value}"
        ),
        confianca=confianca,
        procedencia=procedencia,
        gates=(
            GateDecisaoASG("REGIAO", gate_resultado, "5.084-5.086"),
            GateDecisaoASG("FEED", gate_resultado, estado.value),
            GateDecisaoASG("MAKER", gate_resultado, "+42%"),
        ),
        stop="5.082t" if saudavel else "—",
        alvo_1="5.088t" if saudavel else "—",
        alvo_2="5.090t" if saudavel else "—",
        alvo_3="5.092t" if saudavel else "—",
    )
    itens = tuple(
        EvidenciaASG(
            t - indice * 100_000_000,
            "BOOK" if indice % 2 else "TAPE",
            evento,
            leitura,
            confianca,
            procedencia,
            estado,
        )
        for indice, (evento, leitura) in enumerate(
            (("ABSORCAO", "+18 lotes"), ("REPOSICAO", "+22 lotes"),
             ("DELTA", "+340"), ("CLIP", "12 negocios"))
        )
    )
    evidencias = TrilhaEvidenciasASGSnapshot(t, estado, itens, len(itens), len(itens))
    contexto = ContextoBrutoASGSnapshot(
        timestamp_ns=t,
        estado=estado,
        bids=tuple(NivelBrutoASG(5_086 - indice, 360 - indice * 32, 4 + indice)
                   for indice in range(6)),
        asks=tuple(NivelBrutoASG(5_087 + indice, 332 - indice * 27, 3 + indice)
                   for indice in range(6)),
        negocios=tuple(NegocioBrutoASG(t - indice * 75_000_000, 5_086 + (indice % 2),
                                        8 + indice * 3, 1 if indice % 3 else -1)
                        for indice in range(8)),
        ultimo_preco=5_086,
        detalhe=f"FIXTURE SINTETICA · {estado.value} · MESMO QUADRO",
    )
    return WorkspaceASGSnapshot(
        t, dados, processamento, matriz, decisao, evidencias, estado, contexto
    )


def instantaneo_fixture_asg(estado: EstadoASG) -> Instantaneo:
    """Retrato global correspondente a ``quadro_evidencia_asg``.

    Mantem topo, rodape, faixa e contexto bruto coerentes com a fixture ASG;
    o uso e estritamente de captura visual, nunca de fonte de negociacao.
    """

    feed = {
        EstadoASG.AO_VIVO: EstadoFeed.VIVO,
        EstadoASG.ATRASADO: EstadoFeed.ATRASADO,
        EstadoASG.SEM_BOOK: EstadoFeed.SEM_BOOK,
        EstadoASG.ERRO: EstadoFeed.ERRO,
        EstadoASG.REPLAY: EstadoFeed.VIVO,
    }[estado]
    livro = (
        None
        if estado in {EstadoASG.SEM_BOOK, EstadoASG.ERRO}
        else BookSnapshot(
            _T0_EVIDENCIA_ASG,
            "WDOV26",
            tuple(BookLevel(5_086 - indice, 360 - indice * 32, 4 + indice)
                  for indice in range(6)),
            tuple(BookLevel(5_087 + indice, 332 - indice * 27, 3 + indice)
                  for indice in range(6)),
        )
    )
    return Instantaneo(
        estado=feed,
        ultimo_preco=5_086,
        primeiro_preco=5_074,
        volume_sessao=18_420,
        delta_sessao=340,
        volume_nao_atribuido=0,
        ultimo_evento_ns=_T0_EVIDENCIA_ASG,
        atraso_s=3.3 if estado is EstadoASG.ATRASADO else 0.0,
        contadores=Contadores(trades=184_221, snapshots=612, deltas=4_812),
        novos_trades=tuple(
            ItemTape(_T0_EVIDENCIA_ASG - indice * 75_000_000, 5_086 + (indice % 2),
                     8 + indice * 3, 1 if indice % 3 else -1)
            for indice in range(8)
        ),
        livro=livro,
    )


def aplicar_fixture_asg(janela: JanelaFluxo, estado: EstadoASG) -> None:
    """Aplica a fixture em todas as regioes globais da janela visivel."""

    replay = estado is EstadoASG.REPLAY
    janela.definir_estado_replay(
        EstadoReplay(
            ativo=replay,
            symbol=janela.simbolo,
            data=date(2026, 4, 26),
            inicio_ns=_T0_EVIDENCIA_ASG - 1_800_000_000_000,
            fim_ns=_T0_EVIDENCIA_ASG + 1_800_000_000_000,
            posicao_ns=_T0_EVIDENCIA_ASG,
            velocidade=2.0,
        )
    )
    instantaneo = instantaneo_fixture_asg(estado)
    janela.topo.definir_modo(f"FIXTURE SINTETICA · {estado.value}", replay=replay)
    janela.asg.aplicar(quadro_evidencia_asg(estado))
    janela.asg.aplicar_mercado(instantaneo)
    janela._aplicar_estado_global(instantaneo, estado)


def montar_cenario_controlado_asg(
    estado: EstadoASG,
    *,
    largura: int,
    altura: int,
    paleta=tokens.PALETA_COR,
    densidade=tokens.PADRAO,
    tela_cheia: bool = False,
) -> tuple[JanelaFluxo, SessaoFluxo, dict[str, object]]:
    """Monta evidencia de integracao controlada, explicitamente nao E2E.

    O caminho exercitado e real: eventos de dominio -> ``Barramento`` ->
    ``SessaoFluxo`` e ``PonteFluxo`` -> ``JanelaFluxo._tick`` -> janela
    inteira. A borda de corretora/MT5 e substituida por eventos sinteticos
    deterministas, portanto a evidencia NAO e chamada de end-to-end.
    """

    fonte = (
        FonteDados.REPLAY
        if estado is EstadoASG.REPLAY
        else FonteDados.MT5
        if estado in {EstadoASG.SEM_BOOK, EstadoASG.ERRO}
        else FonteDados.SIMULADOR
    )
    config = ConfigOperacao(
        symbol="WDOV26",
        fonte=fonte,
        # O timestamp sintetico representa relogio de mercado, nao parede.
        # Comparar com o calendario da maquina transformaria SEM BOOK em
        # ATRASADO por construcao e provaria o cenario errado.
        feed_quality=dataclasses.replace(
            ConfigOperacao().feed_quality, latency_comparable=False
        ),
        ligar_analytics=False,
        ligar_microestrutura=False,
        ligar_detectores_tape=False,
        ligar_feed_quality=True,
        ligar_maker_proxy=True,
        ligar_leitura_asg=True,
    )
    barramento = Barramento()
    sessao = SessaoFluxo(barramento, config)
    ponte = PonteFluxo(barramento)
    assert sessao.feed_monitor is not None
    sessao.feed_monitor.connected(
        "cenario controlado sintetico; adaptador externo nao exercitado"
    )
    asg = por_nome("OPERADOR B3")
    assert asg is not None
    janela = JanelaFluxo(
        ponte,
        simbolo=config.symbol,
        grid=config.price_grid(),
        modo="CONTROLADO · SINTETICO · NAO E2E",
        paleta=paleta,
        densidade=densidade,
        sessao=sessao,
        ressalva=(
            "CENARIO CONTROLADO — NAO E PREGAO NEM E2E",
            "eventos sinteticos no Barramento · Sessao/Ponte/tick reais · sem adaptador externo",
        ),
        config=config,
        em_replay=estado is EstadoASG.REPLAY,
        workspace=asg,
        persistir=False,
        trilha=TrilhaEventos(),
    )
    janela.resize(largura, altura)
    janela.showFullScreen() if tela_cheia else janela.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    janela.asg.layout().activate()

    janela.definir_estado_replay(
        EstadoReplay(
            ativo=estado is EstadoASG.REPLAY,
            symbol=config.symbol,
            data=date(2026, 4, 26),
            inicio_ns=_T0_EVIDENCIA_ASG,
            fim_ns=_T0_EVIDENCIA_ASG + 6_000_000_000,
            posicao_ns=_T0_EVIDENCIA_ASG + 5_000_000_000,
            velocidade=2.0,
        )
    )

    ultimo_ts = _T0_EVIDENCIA_ASG
    publicar_book = estado is not EstadoASG.SEM_BOOK
    colunas_bookmap = janela.asg.bookmap.geometria.n_cols
    passos = (
        max(48, min(120, colunas_bookmap + 8))
        if publicar_book else 48
    )
    for passo in range(passos):
        ultimo_ts = _T0_EVIDENCIA_ASG + passo * 250_000_000
        preco = 10_000 + (passo % 5) - 2
        if publicar_book:
            bids = tuple(
                BookLevel(preco - nivel - 1, 90 + ((passo + nivel * 7) % 11) * 18, 2 + nivel)
                for nivel in range(10)
            )
            asks = tuple(
                BookLevel(preco + nivel + 1, 84 + ((passo * 3 + nivel * 5) % 13) * 16, 2 + nivel)
                for nivel in range(10)
            )
            barramento.publicar(BookSnapshot(ultimo_ts, config.symbol, bids, asks))
        for negocio in range(3):
            lado = AgressorSide.BUY if (passo + negocio) % 3 else AgressorSide.SELL
            barramento.publicar(
                Trade(
                    timestamp_ns=ultimo_ts + negocio,
                    symbol=config.symbol,
                    price=preco + (1 if lado is AgressorSide.BUY else -1),
                    qty=8 + ((passo * 5 + negocio * 11) % 90),
                    side_agressor=lado,
                    trade_id=f"r6-{estado.name}-{passo}-{negocio}",
                )
            )
        janela._tick()

    if estado is EstadoASG.ATRASADO:
        sessao.feed_monitor.disconnected("cenario controlado: transporte atrasado")
    elif estado is EstadoASG.ERRO:
        sessao.feed_monitor.failed("cenario controlado: falha declarada da fonte")
    if estado in {EstadoASG.ATRASADO, EstadoASG.ERRO}:
        ultimo_ts += 250_000_000
        barramento.publicar(
            Trade(
                ultimo_ts,
                config.symbol,
                10_000,
                21,
                AgressorSide.BUY,
                f"r6-{estado.name}-transicao",
            )
        )
        janela._tick()

    if app is not None:
        app.processEvents()
    for painel in janela.paineis:
        painel._quadro()

    snapshot = janela.asg._snapshot
    assert snapshot is not None
    rotulos_matriz = {
        "MACRO", "MICRO", "LINHA AZUL", "REGIME", "MAKERPROXY", "VELOCIMETRO",
    }
    manifesto = {
        "classification": "controlled_synthetic_integration_not_end_to_end",
        "end_to_end": False,
        "external_adapter_exercised": False,
        "path_exercised": [
            "Barramento",
            "SessaoFluxo",
            "PonteFluxo",
            "JanelaFluxo._tick",
            "window_grab",
        ],
        "state_requested": estado.value,
        "state_asg": snapshot.estado_operacional.value,
        "state_top": janela.topo._estado_operacional[0],
        "state_footer": janela.rodape._texto_esquerda,
        "replay_banner": janela.tarja_replay.isVisible(),
        "workspace": janela.workspace.nome,
        "resolution": [janela.width(), janela.height()],
        "market_timestamp_ns": snapshot.timestamp_ns,
        "trades_session": sessao.contadores.n_trades_bus,
        "books_session": sessao.contadores.n_snapshots_bus,
        "real_context_panels": [
            type(janela.asg.dom).__name__,
            type(janela.asg.tape).__name__,
            type(janela.asg.bookmap).__name__,
        ],
        "tape_rows_retained": len(janela.asg.tape._linhas),
        "bookmap_columns_available": janela.asg.bookmap.geometria.n_cols,
        "bookmap_columns_closed": janela.asg.bookmap._colunas_fechadas,
        "missing_matrix_labels": sorted(
            rotulos_matriz - set(janela.asg.matriz.textos_visiveis())
        ),
        "decision_visible": janela.asg.decisao.isVisible(),
        "no_orders_banner": "CONSULTIVO · SEM ENVIO DE ORDENS"
        in janela.asg.decisao.textos_visiveis(),
        "orders": "not_available_in_ui",
    }
    return janela, sessao, manifesto


def ressalva_da_config(config: ConfigOperacao) -> tuple[str, str]:
    """`(titulo, detalhe)` do carimbo, DERIVADO da configuracao.

    A regra do projeto: toda calibracao ou dado fabricado que altere o que a
    tela afirma tem de estar carimbado NA IMAGEM, legivel depois da
    degradacao — porque o PNG circula sozinho e, sozinho, ele afirmaria com
    os cortes de calibracao uma coisa que nao e verdade com os de producao.

    Nenhum numero e redigitado aqui: os limiares vem de
    `ConfigMotorSinais()`, campo a campo, comparados com o que este processo
    esta usando. Quem recalibrar o motor de producao ve a tarja passar a
    dizer o corte novo sem que ninguem lembre dela. Se nada foi calibrado e a
    fonte e real, a funcao devolve `("", "")` e a janela nao desenha faixa
    nenhuma — carimbo permanente vira moldura e para de ser lido.
    """
    padrao = ConfigMotorSinais()
    # O nome do limiar sai do mesmo dicionario que a coluna de regras usa
    # para rotular a linha — carimbo e painel nomeando o mesmo botao de dois
    # jeitos e o leitor conferindo dois numeros que ele nao sabe se sao o
    # mesmo.
    rotulos = {campo: rotulo.lower() for campo, rotulo in PARAMETROS_EM_VIGOR}
    trocas = [
        "%s %s em vez de %s"
        % (
            rotulos.get(campo.name, campo.name.replace("_", " ")),
            formatar_limiar(campo.name, getattr(config.motor, campo.name)),
            formatar_limiar(campo.name, getattr(padrao, campo.name)),
        )
        for campo in dataclasses.fields(ConfigMotorSinais)
        if getattr(config.motor, campo.name) != getattr(padrao, campo.name)
    ]
    fabricado = config.fonte is FonteDados.SIMULADOR
    if not trocas and not fabricado:
        return ("", "")

    if trocas and fabricado:
        titulo = TITULO_AMBOS
    elif trocas:
        titulo = TITULO_CALIBRADO
    else:
        titulo = TITULO_SIMULADOR

    partes = []
    if fabricado:
        partes.append(
            "passeio aleatório de `dados/simulador.py`, seed %d · nenhum byte "
            "de mercado real" % config.simulador.seed
        )
    if trocas:
        partes.append(" · ".join(trocas))
        # Afirmacao VERIFICAVEL, e nao a contrafactual "com os cortes de
        # producao esta sessao leria outro estagio": essa nao foi medida, e
        # uma tarja que existe para nao afirmar demais nao pode ser o lugar
        # onde se afirma o que nao se rodou. O leitor confere os dois numeros
        # na propria tela, lado a lado.
        partes.append("os cortes de produção estão na coluna MÉTODO, ao lado de cada limiar")
    return (titulo, "  ·  ".join(partes))


def _parser():
    p = construir_parser()
    g = p.add_argument_group("painel")
    g.add_argument(
        "--densidade",
        choices=sorted(_DENSIDADES),
        default="padrao",
        help="altura de linha da grade (§3.4)",
    )
    g.add_argument(
        "--sem-cor",
        action="store_true",
        dest="sem_cor",
        help=(
            "desliga o eixo direcional de cor; a direcao passa a viver so no "
            "sinal explicito e na posicao. E o modo de acessibilidade, e "
            "tambem o teste de que a tela nao depende de cor para ser lida."
        ),
    )
    g.add_argument(
        "--filtro-tape",
        type=int,
        default=0,
        dest="filtro_tape",
        help="lote minimo exibido no tape (0 = tudo)",
    )
    g.add_argument(
        "--retrato",
        help=(
            "salva um PNG da tela inteira ao fim de --duracao e encerra. E a "
            "MESMA janela do produto, montada pelo mesmo caminho: um gerador "
            "de retrato paralelo retrataria a si mesmo."
        ),
    )
    g.add_argument(
        "--workspace",
        choices=list(NOMES_DE_ENTRADA),
        default="OPERADOR B3",
        help=(
            "arranjo inicial (OPERADOR B3 por padrao; Ctrl+1..9 troca a quente)."
        ),
    )
    g.add_argument(
        "--retrato-workspaces",
        action="store_true",
        dest="retrato_workspaces",
        help=(
            "com --retrato, gera UM PNG por workspace de fabrica, sufixando o "
            "nome do arquivo. E a evidencia da fase 3: quatro arranjos, quatro "
            "imagens, todas da MESMA janela do produto."
        ),
    )
    g.add_argument(
        "--retrato-estados-asg",
        action="store_true",
        dest="retrato_estados_asg",
        help=(
            "com --retrato, captura integracao controlada e rotulada (nao E2E) "
            "via Barramento/Sessao/Ponte/tick em AO VIVO, ATRASADO, SEM BOOK, "
            "ERRO e REPLAY"
        ),
    )
    g.add_argument(
        "--persistir-workspace",
        action="store_true",
        dest="persistir",
        help=(
            "grava geometria e arranjo em %%APPDATA%%/FluxoPro/workspaces ao "
            "fechar, e le de la ao trocar de workspace (§4.1). Desligado por "
            "padrao: um retrato nunca deve depender do perfil de quem roda."
        ),
    )
    g.add_argument(
        "--caixas-retencao",
        action="store_true",
        dest="caixas_retencao",
        help=(
            "imprime as caixas de `scripts/retencao.py` derivadas da GEOMETRIA "
            "DOS PROPRIOS PAINEIS, ja mapeadas para a janela. Caixa medida a "
            "mao no PNG e uma das fontes de ruido que aquele script nomeia."
        ),
    )
    g.add_argument(
        "--tela-cheia",
        action="store_true",
        dest="tela_cheia",
        help="sem barra de titulo (V5): a tela e consumida por captura",
    )
    g.add_argument(
        "--largura", type=int, default=1480, help="largura da janela (default 1480)"
    )
    g.add_argument(
        "--altura", type=int, default=900, help="altura da janela (default 900)"
    )
    g.add_argument(
        "--gil-switch",
        type=float,
        default=GIL_SWITCH_PADRAO,
        dest="gil_switch",
        help=(
            f"intervalo de troca de GIL em segundos (default {GIL_SWITCH_PADRAO}). "
            "Menor = tela mais fluida e ingestao mais lenta; ver o modulo."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.retrato_workspaces and args.retrato_estados_asg:
        parser.error("use apenas um entre --retrato-workspaces e --retrato-estados-asg")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = config_de_args(args)
    if por_nome(args.workspace) is not None and por_nome(args.workspace).nome_exibicao == "OPERADOR B3":
        config = dataclasses.replace(
            config,
            ligar_feed_quality=True,
            ligar_maker_proxy=True,
            ligar_leitura_asg=True,
        )
    if args.gil_switch > 0:
        sys.setswitchinterval(args.gil_switch)

    if args.retrato is not None:
        # ESCALA FIXA PARA O RETRATO — antes de existir `QApplication`, que e
        # quando o Qt le isto.
        #
        # Sem esta linha o retrato sai no fator do monitor em que a janela
        # abriu: a MESMA linha de comando gerou 1850x1143 numa passada e
        # 1480x914 na seguinte, nesta mesma maquina. Duas consequencias, e a
        # segunda e a grave:
        #
        # 1. a evidencia do projeto muda de tamanho sozinha, e um retrato
        #    regenerado parece uma mudanca de layout quando e so a tela;
        # 2. `--caixas-retencao` multiplica pelo `devicePixelRatio`, entao as
        #    caixas de uma passada a 125% recortam coordenadas que nao
        #    existem numa imagem gerada a 100%. Foi o que aconteceu: um par
        #    mediu 0,3 pp de margem contra pixel fora da imagem e depois
        #    10,6 pp de violacao real. O portao nao estava frouxo — estava
        #    medindo outro lugar.
        #
        # Com dpr travado em 1, pixel logico e pixel de imagem sao o mesmo, e
        # a caixa vale em qualquer maquina.
        os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
        os.environ.setdefault("QT_SCALE_FACTOR", "1")

    aplicacao = QApplication(sys.argv[:1])

    ponte: PonteFluxo | None = None

    try:
        montagem = montar(
            config,
            # Lambda, e nao `ponte.registrar_evento`, porque a `SessaoFluxo`
            # precisa dos callbacks no construtor e a ponte precisa do
            # barramento que `montar` cria — o no se desfaz adiando a busca
            # do metodo para a hora da chamada, que so acontece depois de
            # `iniciar()`. A alternativa (construir o barramento aqui e
            # passar pronto) poria a ponte a assinar ANTES da sessao, e a
            # ordem de prioridade do barramento e declarada e testada la.
            ao_sinal=lambda evento: ponte.registrar_evento(evento),
            ao_deteccao=lambda evento: ponte.registrar_evento(evento),
            replay=opcoes_replay_de_args(args),
        )
    except FonteIndisponivelError as erro:
        _logger.error("nao foi possivel abrir a fonte: %s", erro)
        return 2

    # A ponte assina ANTES de a fonte comecar. `montar` nao chamou
    # `iniciar()` ainda, e o docstring dele explica por que isso importa: o
    # simulador publica a partir de `iniciar()`, e quem assinar depois perde
    # o que ja passou.
    ponte = PonteFluxo(montagem.barramento)

    modo = ""
    em_replay = config.fonte is FonteDados.REPLAY
    if config.fonte is FonteDados.SIMULADOR:
        modo = "SIMULADOR"
    elif em_replay:
        velocidade = args.velocidade
        modo = "▶ REPLAY " + ("máx" if velocidade == "max" else f"{velocidade}×")

    parando = threading.Event()

    def _parar() -> None:
        if parando.is_set():
            return
        parando.set()
        montagem.fonte.parar()

    ressalva = ressalva_da_config(config)
    janela = JanelaFluxo(
        ponte,
        simbolo=config.symbol,
        grid=config.price_grid(),
        modo=modo,
        paleta=tokens.PALETA_SEM_COR if args.sem_cor else tokens.PALETA_COR,
        densidade=_DENSIDADES[args.densidade],
        ao_fechar=_parar,
        # O motor vai junto por duas razoes: a regua da matriz desenha os
        # cortes DESTE motor (regua que mente sobre o corte e pior que regua
        # nenhuma) e a coluna de regras mostra o limiar EM VIGOR ao lado do
        # de producao.
        config_motor=config.motor,
        # A sessao entra so para o que o `Instantaneo` nao carrega: a janela
        # de agressao e o perfil de players. Delta, volume e nao-atribuido
        # continuam vindo do retrato, montado sob o lock.
        sessao=montagem.sessao,
        ressalva=ressalva,
        # A configuracao INTEIRA, e nao so o motor: o footprint precisa do
        # `timeframe_ns` e do `ConfigFootprint`, o perfil do
        # `ConfigVolumeProfile` e o delta do `ConfigDelta`. Passar so o motor
        # faria os tres nascerem com defaults que nao sao os desta sessao — e o
        # painel de delta acenderia `EIXOS ≠` contra uma divergencia que este
        # processo mesmo teria criado.
        config=config,
        # O flag do replay e EXPLICITO. E o que mata a contradicao que o
        # construtor do replay achou: com ele, `StripTopo` e `StripRodape`
        # param de grafar `● AO VIVO` sob a tarja `▶ REPLAY`.
        em_replay=em_replay,
        workspace=por_nome(args.workspace),
        persistir=args.persistir,
        trilha=TrilhaEventos(),
    )
    janela.tape.definir_filtro(args.filtro_tape)
    janela.resize(args.largura, args.altura)
    if args.tela_cheia:
        janela.showFullScreen()
    else:
        janela.show()
    if ressalva[0]:
        _logger.info("carimbo na imagem: %s | %s", *ressalva)

    if args.retrato:
        duracao = args.duracao if args.duracao else 8.0

        def _salvar(caminho: Path, *, atualizar_dados: bool = True) -> None:
            # Fecha um quadro completo antes de copiar os pixels: os relogios
            # de desenho sao assincronos e o backing poderia estar um quadro
            # atras.
            if atualizar_dados:
                janela.desenhar_agora()
            else:
                # A fixture ja aplicou o snapshot global; ainda precisamos
                # fechar os backings dos tres paineis brutos reais, que nao
                # pertencem a ``paineis`` por tambem servirem ao layout.
                for painel in janela.asg.todos_paineis:
                    painel._quadro()
            caminho.parent.mkdir(parents=True, exist_ok=True)
            janela.grab().save(str(caminho))
            if args.caixas_retencao:
                _imprimir_caixas()
            _logger.info(
                "retrato %s | %dx%d | workspace %s | trilho %s",
                caminho,
                janela.width(),
                janela.height(),
                janela.workspace.nome,
                "ARRANJO LIVRE: " + janela.trilho.motivo
                if janela.trilho.arranjo_livre
                else "cadeia em 4 colunas",
            )

        def _capturar_workspaces() -> None:
            base = Path(args.retrato)
            for ws in WORKSPACES_DISPONIVEIS:
                janela.aplicar_workspace(ws)
                janela.resize(args.largura, args.altura)
                aplicacao.processEvents()
                janela._sincronizar_trilho()
                # ASCII de proposito: `revisão` vira `revisao`. Nome de
                # arquivo com acento viaja mal entre shell, git e navegador, e
                # o retrato existe justamente para circular.
                seguro = ws.nome.lower().replace(" & ", "_").replace(" ", "_")
                seguro = (
                    unicodedata.normalize("NFKD", seguro)
                    .encode("ascii", "ignore")
                    .decode("ascii")
                )
                seguro = "".join(c for c in seguro if c.isalnum() or c == "_")
                _salvar(base.with_name(base.stem + "_" + seguro + base.suffix))
            janela.close()

        def _capturar_estados_asg() -> None:
            base = Path(args.retrato)
            base.parent.mkdir(parents=True, exist_ok=True)
            janela._relogio.stop()
            manifestos: list[dict[str, object]] = []
            for estado in (
                EstadoASG.AO_VIVO,
                EstadoASG.ATRASADO,
                EstadoASG.SEM_BOOK,
                EstadoASG.ERRO,
                EstadoASG.REPLAY,
            ):
                cenario, sessao_cenario, manifesto = montar_cenario_controlado_asg(
                    estado,
                    largura=args.largura,
                    altura=args.altura,
                    paleta=tokens.PALETA_SEM_COR if args.sem_cor else tokens.PALETA_COR,
                    densidade=_DENSIDADES[args.densidade],
                    tela_cheia=args.tela_cheia,
                )
                try:
                    cenario.asg.tape.definir_filtro(args.filtro_tape)
                    aplicacao.processEvents()
                    seguro = estado.name.lower()
                    caminho = base.with_name(base.stem + "_" + seguro + base.suffix)
                    cenario.grab().save(str(caminho))
                    manifesto["file"] = caminho.name
                    manifestos.append(manifesto)
                    _logger.info(
                        "retrato controlado NAO E2E %s | %dx%d | %s -> %s",
                        caminho,
                        cenario.width(),
                        cenario.height(),
                        " -> ".join(manifesto["path_exercised"]),
                        manifesto["state_footer"],
                    )
                finally:
                    timestamp = (
                        cenario.asg._snapshot.timestamp_ns
                        if cenario.asg._snapshot is not None else None
                    )
                    cenario.close()
                    sessao_cenario.finalizar(timestamp)
            manifesto_path = base.with_name(base.stem + "_manifest.json")
            manifesto_path.write_text(
                json.dumps(
                    {
                        "classification": "controlled_synthetic_integration_not_end_to_end",
                        "captures": manifestos,
                    },
                    ensure_ascii=False,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            janela.close()

        def _imprimir_caixas() -> None:
            """As caixas do canal, do mesmo `QRect` que o desenho usou.

            Os PARES sao o portao: `--par RESSALVA=VEREDITO` sai com codigo 1
            quando a ressalva retem menos traco que o veredito que ela
            qualifica. Nenhuma coordenada e digitada aqui.
            """
            metodo = janela.metodo

            # O retrato sai em PIXEL DE IMAGEM, e a geometria do Qt esta em
            # pixel LOGICO: num monitor a 125% os dois diferem, e uma caixa
            # publicada em coordenada logica mede o pedaco errado da imagem —
            # o portao passa a reprovar (ou aprovar) uma regiao que ninguem
            # escolheu. Multiplicar pelo `devicePixelRatio` da janela e o que
            # faz a medicao valer em qualquer maquina.
            dpr = janela.devicePixelRatioF()

            def caixa(nome, widget, rect):
                canto = widget.mapTo(janela, rect.topLeft())
                return '"%s:%d,%d,%d,%d"' % (
                    nome,
                    round(canto.x() * dpr),
                    round(canto.y() * dpr),
                    round(rect.width() * dpr),
                    round(rect.height() * dpr),
                )

            from fluxopro.ui.paineis.metodo import I_PLACAR, I_REGIME

            partes = [
                caixa("proc_regime", metodo, metodo.rect_chip_procedencia(I_REGIME)),
                caixa("veredito_regime", metodo, metodo.rect_texto_valor(I_REGIME)),
                caixa("proc_placar", metodo, metodo.rect_chip_procedencia(I_PLACAR)),
                caixa("veredito_placar", metodo, metodo.rect_texto_valor(I_PLACAR)),
                caixa("cobertura", metodo, metodo.rect_chip_cobertura()),
                caixa("trilho_elo1", janela.trilho, janela.trilho.rect_rotulo(0)),
            ]
            # O par do HUD. Entrou depois do resto: a lei do canal foi
            # verificada ali por ARITMETICA de contraste (corpo >= corpo,
            # razao >= razao) e nunca por MEDICAO de traco na imagem — e
            # contraste calculado e uma previsao do que a reescala faz, nao
            # uma observacao dela. Os textos vem do painel, nao daqui, para
            # que a caixa siga o numero que estiver na tela.
            hud = janela.hud
            texto_qual, texto_ver = hud.textos_da_pressao()
            if texto_qual:
                partes.append(
                    caixa("denom_pressao", hud, hud.rect_qualificador_da_pressao(texto_qual))
                )
                partes.append(
                    caixa("veredito_pressao", hud, hud.rect_veredito_da_pressao(texto_ver))
                )
                pares_hud = " --par denom_pressao=veredito_pressao"
            else:
                pares_hud = ""
            # A coluna do registro entrou no portao na rodada da composicao
            # curta: quando a coluna nao cabe inteira, a linha do CORTE e a
            # ressalva daquele painel — ela e que diz que a lista na tela nao
            # e a lista toda. Se ela retiver menos traco que o rodape que
            # qualifica, o canal entrega uma lista aparentemente completa,
            # que e o defeito de origem com outra roupa.
            from fluxopro.ui.janela import ALTURA_LINHA_REGRA, MARGEM

            regras = janela.regras
            plano = regras.layout_corrente()
            pares_extra = ""
            if plano.rodape_visivel:
                partes.append(
                    caixa(
                        "rodape_modo",
                        regras,
                        QRect(0, plano.rodape.top() + 4, regras.width(), 18),
                    )
                )
                if plano.y_corte >= 0:
                    partes.append(
                        caixa(
                            "corte_regras",
                            regras,
                            QRect(
                                MARGEM,
                                plano.y_corte,
                                regras.width() - 2 * MARGEM,
                                ALTURA_LINHA_REGRA,
                            ),
                        )
                    )
                    pares_extra = " --par corte_regras=rodape_modo"
            print("caixas para scripts/retencao.py:")
            print("  " + " ".join("--caixa " + c for c in partes))
            print(
                "  --par proc_regime=veredito_regime "
                "--par proc_placar=veredito_placar "
                "--par cobertura=trilho_elo1" + pares_extra + pares_hud
            )

        def _capturar() -> None:
            # Fecha um quadro completo antes de copiar os pixels: os relogios
            # de desenho sao assincronos e o backing poderia estar um quadro
            # atras.
            janela.desenhar_agora()
            caminho = Path(args.retrato)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            janela.grab().save(str(caminho))
            if args.caixas_retencao:
                _imprimir_caixas()
            _logger.info(
                "retrato %s | %dx%d | %d negocios | %d deteccoes | %d sinais",
                caminho,
                janela.width(),
                janela.height(),
                montagem.sessao.contadores.n_trades_bus,
                janela._n_deteccoes,
                janela._n_sinais,
            )
            janela.close()

        QTimer.singleShot(
            int(duracao * 1000),
            _capturar_estados_asg
            if args.retrato_estados_asg
            else _capturar_workspaces
            if args.retrato_workspaces
            else _capturar,
        )
    elif args.duracao:
        # `--duracao` vem do parser de `operar.py`. Honra-la aqui e o que
        # impede a flag de existir na ajuda e nao fazer nada — e e o que
        # torna possivel rodar o painel sem ninguem olhando (fumaca, CI,
        # gravacao automatica). `QTimer` e nao `threading.Timer`: fechar
        # janela e operacao da thread do Qt.
        QTimer.singleShot(int(args.duracao * 1000), janela.close)

    def _rodar_fonte() -> None:
        try:
            montagem.fonte.iniciar()
        except Exception:  # noqa: BLE001 — a UI precisa saber, nao morrer
            _logger.exception("falha na fonte de dados")
        finally:
            ponte.marcar_encerrado()

    thread = threading.Thread(target=_rodar_fonte, name="fonte", daemon=True)
    thread.start()

    codigo = aplicacao.exec()
    _parar()
    thread.join(timeout=5.0)
    montagem.sessao.finalizar()

    # Resumo na saida, pelo mesmo motivo que `operar.py` avisa quando
    # processou zero eventos: uma passada que nao mostrou nada e um
    # resultado suspeito, nao um resultado. O p95 do quadro entra junto
    # porque saude da interface e informacao da sessao, nao curiosidade.
    contadores = montagem.sessao.contadores
    _logger.info(
        "encerrado: %d negocios, %d snapshots, %d deltas | quadro DOM p95 %.3f ms "
        "(%d desenhados, %d ociosos) | tape p95 %.3f ms",
        contadores.n_trades_bus,
        contadores.n_snapshots_bus,
        contadores.n_deltas_bus,
        janela.dom.p95_ms(),
        janela.dom.quadros_desenhados,
        janela.dom.quadros_vazios,
        janela.tape.p95_ms(),
    )
    if contadores.n_trades_bus == 0:
        _logger.warning(
            "NENHUM negocio chegou a tela. Se a fonte e replay com --de/--ate, "
            "note que o recorte e interpretado em UTC: a abertura do WDO "
            "(09:00 de Brasilia) e 12:00 UTC."
        )
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
