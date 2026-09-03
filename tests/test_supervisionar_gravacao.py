"""O supervisor que faltava em 24/08/2026: `operar.py` caiu as 13:21 (Ctrl+C
externo) num pregao com fim previsto em 18:30, e nada relancou. O dado ate
ali estava seguro — `Gravador` ja escreve em append e so recusa reabrir um
dia com `.gz` — mas ninguem no nivel de PROCESSO sabia que devia tentar de
novo. `scripts/supervisionar_gravacao.py` fecha essa lacuna.

Os testes aqui nunca sobem um `operar.py` de verdade: `supervisionar()` recebe
`lancar`/`agora`/`dormir` injetados, e cada teste controla o relogio a mao —
mesmo padrao de dublê usado no resto do projeto para nao depender de tempo
real nem de MT5.
"""

from __future__ import annotations

import datetime as dt

from scripts.supervisionar_gravacao import dia_finalizado, supervisionar


def _relogio(inicio: dt.datetime):
    """Devolve (agora, avancar) — um relogio fake que so anda quando mandado."""
    estado = {"agora": inicio}

    def agora() -> dt.datetime:
        return estado["agora"]

    def avancar(segundos: float) -> None:
        estado["agora"] += dt.timedelta(seconds=segundos)

    return agora, avancar


def test_dia_nao_finalizado_nao_reconecta_quando_a_janela_ja_fechou():
    """Fora da janela do pregao, nem tenta — nao existe hora extra."""
    agora, _ = _relogio(dt.datetime(2026, 1, 1, 18, 31))
    fim = dt.datetime(2026, 1, 1, 18, 30)
    chamadas = []

    total = supervisionar(
        fim=fim,
        lancar=lambda d: chamadas.append(d) or (0, 0.0),
        dia_ja_finalizado=lambda: False,
        agora=agora,
        dormir=lambda s: None,
        logar=lambda m: None,
    )

    assert total == 0
    assert chamadas == []


def test_dia_ja_finalizado_nao_reconecta_mesmo_dentro_da_janela():
    """Existe `.gz`: o dia ja fechou numa passada anterior, nao ha o que retomar."""
    agora, _ = _relogio(dt.datetime(2026, 1, 1, 10, 0))
    fim = dt.datetime(2026, 1, 1, 18, 30)
    chamadas = []

    total = supervisionar(
        fim=fim,
        lancar=lambda d: chamadas.append(d) or (0, 0.0),
        dia_ja_finalizado=lambda: True,
        agora=agora,
        dormir=lambda s: None,
        logar=lambda m: None,
    )

    assert total == 0
    assert chamadas == []


def test_reconecta_uma_vez_quando_operar_cai_antes_da_hora():
    """O caso real de 24/08: cai as 13:21 com fim previsto em 18:30 — reconecta."""
    agora, avancar = _relogio(dt.datetime(2026, 1, 1, 9, 0))
    fim = dt.datetime(2026, 1, 1, 9, 5, 0)  # janela de 300s, encurtada p/ o teste
    chamadas = []

    def lancar(duracao_pedida: float):
        chamadas.append(duracao_pedida)
        if len(chamadas) == 1:
            avancar(100.0)  # caiu cedo, com Ctrl+C simulado
            return 1, 100.0
        restante = (fim - agora()).total_seconds()
        avancar(restante)  # dessa vez roda ate o fim de verdade
        return 0, restante

    total = supervisionar(
        fim=fim,
        lancar=lancar,
        dia_ja_finalizado=lambda: False,
        agora=agora,
        dormir=avancar,
        logar=lambda m: None,
        cooldown_s=5.0,
    )

    assert total == 1
    assert len(chamadas) == 2
    # a segunda tentativa pede so o tempo que falta, nao a janela inteira
    assert chamadas[1] < chamadas[0] + 1e-6
    assert chamadas[1] == 200.0 - 5.0  # 300 - 100 rodado - 5 de cooldown


def test_fim_normal_do_dia_nao_conta_como_queda():
    """`operar.py` roda ate o proprio `--duracao` esgotar: fim limpo, zero reconexao."""
    agora, avancar = _relogio(dt.datetime(2026, 1, 1, 9, 0))
    fim = dt.datetime(2026, 1, 1, 9, 5, 0)
    chamadas = []

    def lancar(duracao_pedida: float):
        chamadas.append(duracao_pedida)
        avancar(duracao_pedida)  # roda exatamente o tempo pedido, sem cair cedo
        return 0, duracao_pedida

    total = supervisionar(
        fim=fim,
        lancar=lancar,
        dia_ja_finalizado=lambda: False,
        agora=agora,
        dormir=avancar,
        logar=lambda m: None,
    )

    assert total == 0
    assert len(chamadas) == 1


def test_circuito_desiste_apos_quedas_rapidas_seguidas():
    """MT5 fechado o dia inteiro: reconectar a cada 20s pra sempre e ruido, nao ajuda."""
    agora, avancar = _relogio(dt.datetime(2026, 1, 1, 9, 0))
    fim = dt.datetime(2026, 1, 1, 18, 30)  # janela grande — quem para e o circuito
    chamadas = []
    avisos_de_desistencia = []

    def lancar(_duracao_pedida: float):
        chamadas.append(1)
        avancar(2.0)  # morre quase instantaneo toda vez (fonte indisponivel)
        return 2, 2.0

    def logar(msg: str) -> None:
        if "desistindo" in msg:
            avisos_de_desistencia.append(msg)

    total = supervisionar(
        fim=fim,
        lancar=lancar,
        dia_ja_finalizado=lambda: False,
        agora=agora,
        dormir=avancar,
        logar=logar,
        cooldown_s=1.0,
        limiar_queda_rapida_s=60.0,
        max_quedas_rapidas=3,
    )

    assert total == 3
    assert len(chamadas) == 3
    assert len(avisos_de_desistencia) == 1


def test_rodada_longa_reseta_o_contador_de_quedas_rapidas():
    """Uma queda isolada apos rodar bastante NAO deve herdar o contador de outra.

    Sequencia: queda rapida, rodada longa (que tambem cai, mas devagar —
    reseta), queda rapida, queda rapida. Com `max_quedas_rapidas=2`, so as
    duas rapidas SEGUIDAS do final devem acionar o circuito — se o contador
    nao resetasse depois da rodada longa, o circuito pararia uma chamada
    antes (na 3a, nao na 4a), porque a queda da 1a chamada ainda contaria.
    """
    agora, avancar = _relogio(dt.datetime(2026, 1, 1, 9, 0))
    fim = dt.datetime(2026, 1, 1, 18, 30)
    duracoes = [30.0, 200.0, 30.0, 30.0]  # 2a rodada >= limiar de 60s
    chamadas = []

    def lancar(_duracao_pedida: float):
        d = duracoes[len(chamadas)]
        chamadas.append(d)
        avancar(d)
        return 1, d

    total = supervisionar(
        fim=fim,
        lancar=lancar,
        dia_ja_finalizado=lambda: False,
        agora=agora,
        dormir=avancar,
        logar=lambda m: None,
        cooldown_s=1.0,
        limiar_queda_rapida_s=60.0,
        max_quedas_rapidas=2,
    )

    assert len(chamadas) == 4, "sem o reset, o circuito desistiria na 3a chamada"
    assert total == 4


def test_dia_finalizado_le_o_mesmo_marcador_que_o_gravador_escreve(tmp_path):
    """`dia_finalizado()` tem de concordar com `Gravador._dia_ja_finalizado`:
    a presenca de `trades.csv.gz` — nao o `meta.json`, nao o `.csv` cru."""
    base = tmp_path
    dia = dt.date(2026, 8, 24)
    pasta = base / "WDOU26" / "2026-08-24"
    pasta.mkdir(parents=True)

    assert dia_finalizado(base, "WDOU26", dia) is False

    (pasta / "trades.csv").write_text("cabecalho\n", encoding="utf-8")
    assert dia_finalizado(base, "WDOU26", dia) is False, "csv cru nao e finalizacao"

    (pasta / "trades.csv.gz").write_bytes(b"\x1f\x8b")
    assert dia_finalizado(base, "WDOU26", dia) is True


# ==================================================================== 03/09/2026
# DOIS PREGOES PERDIDOS COM A TAREFA REPORTANDO SUCESSO:
#   02/09 — `mt5.initialize()` falhou as 09:00:03; o processo ficou vivo ate
#           as 18:30 por causa de um `threading.Timer` nao-daemon, e o
#           supervisor viu "fim normal do dia" com 0 reconexoes;
#   01/09 — MT5 conectou e entregou 1 negocio o dia INTEIRO; nada caiu, nada
#           reclamou, e o arquivo do dia saiu sem `trades.csv.gz`.
#
# O supervisor so olhava para o CODIGO DE SAIDA. Estes testes cobrem as duas
# coisas que passaram a olhar para o RESULTADO.
import gzip

from scripts.supervisionar_gravacao import (  # noqa: E402
    caminho_trades, fluxo_parado, negocios_gravados,
)

_CABECALHO = "timestamp_ns,symbol,price,qty,side_agressor,trade_id\n"


def _gravar(base, symbol, dia, linhas, *, fechado=False):
    pasta = base / symbol / dia.isoformat()
    pasta.mkdir(parents=True, exist_ok=True)
    conteudo = _CABECALHO + "".join(
        f"{i},{symbol},10000,1,BUY,t{i}\n" for i in range(linhas)
    )
    alvo = pasta / "trades.csv"
    if fechado:
        with gzip.open(alvo.with_suffix(".csv.gz"), "wt", encoding="utf-8") as fh:
            fh.write(conteudo)
    else:
        alvo.write_text(conteudo, encoding="utf-8")


def test_conta_negocios_do_arquivo_AO_VIVO_e_do_FECHADO(tmp_path):
    """A vigia le durante o pregao (`.csv`) e o portao le depois de fechado
    (`.csv.gz`) — a mesma contagem tem de valer nos dois."""
    dia = dt.date(2026, 9, 3)
    _gravar(tmp_path, "WDOU26", dia, 7)
    assert negocios_gravados(tmp_path, "WDOU26", dia) == 7

    _gravar(tmp_path, "WDOX26", dia, 4, fechado=True)
    assert negocios_gravados(tmp_path, "WDOX26", dia) == 4


def test_dia_sem_arquivo_e_dia_so_com_cabecalho_contam_ZERO(tmp_path):
    """O caso de 02/09 (pasta nem existiu) e o caso de arquivo aberto e nunca
    preenchido tem de dar o MESMO veredito: zero."""
    dia = dt.date(2026, 9, 3)
    assert negocios_gravados(tmp_path, "WDOU26", dia) == 0

    pasta = tmp_path / "WDOU26" / dia.isoformat()
    pasta.mkdir(parents=True)
    (pasta / "trades.csv").write_text(_CABECALHO, encoding="utf-8")
    assert negocios_gravados(tmp_path, "WDOU26", dia) == 0


def test_caminho_trades_aponta_para_o_csv_do_dia(tmp_path):
    dia = dt.date(2026, 9, 3)
    assert caminho_trades(tmp_path, "WDOU26", dia).name == "trades.csv"
    assert caminho_trades(tmp_path, "WDOU26", dia).parent.name == "2026-09-03"


# ------------------------------------------------------------------ vigia
def test_fluxo_parado_so_dispara_com_a_JANELA_CHEIA_de_observacao():
    """Um pregao tem minutos legitimamente sem negocio (leilao, abertura
    lenta). Derrubar a fonte por causa disso trocaria um problema por outro,
    entao a vigia exige a janela inteira sem crescimento."""
    # 5 min parados, paciencia de 10 min: ainda NAO
    amostras = [(0.0, 100), (120.0, 100), (300.0, 100)]
    assert fluxo_parado(amostras, paciencia_s=600) is False
    # 10 min parados: dispara
    amostras += [(660.0, 100)]
    assert fluxo_parado(amostras, paciencia_s=600) is True


def test_fluxo_que_CRESCEU_na_janela_nao_dispara():
    """O caso normal: negocio chegando. Um unico negocio novo dentro da janela
    ja prova que a fonte esta viva."""
    amostras = [(0.0, 100), (300.0, 100), (660.0, 101)]
    assert fluxo_parado(amostras, paciencia_s=600) is False


def test_vigia_nao_opina_com_uma_amostra_so():
    """Sem duas leituras nao existe 'nao cresceu' — so existe 'nao sei'."""
    assert fluxo_parado([], paciencia_s=600) is False
    assert fluxo_parado([(0.0, 0)], paciencia_s=600) is False


def test_fluxo_zerado_desde_o_inicio_dispara_igual():
    """O caso de 01/09: a contagem nunca saiu do lugar. Zero parado e tao
    morto quanto cem parado."""
    amostras = [(0.0, 0), (300.0, 0), (660.0, 0)]
    assert fluxo_parado(amostras, paciencia_s=600) is True


# ------------------------------------------------- portao de fim de dia
def test_main_FALHA_quando_o_dia_fecha_com_zero_negocios(tmp_path, monkeypatch, capsys):
    """CRITERIO DO OPERADOR (03/09/2026): "falha se zero negocios".

    Ate aqui `main` devolvia 0 SEMPRE — e foi por isso que a tarefa
    `FluxoPro-GravarPregao` marcou resultado 0 em 01/09 e 02/09 sem ter
    gravado pregao nenhum. Um dia sem um unico negocio nao e um dia gravado, e
    a unica forma de isso aparecer para quem nao esta olhando o log e a rotina
    FALHAR.
    """
    import scripts.supervisionar_gravacao as sup

    monkeypatch.setattr(sup, "supervisionar", lambda **k: 0)
    monkeypatch.setattr(sup, "_lancar_de_verdade", lambda **k: (lambda d: (0, 0.0)))

    codigo = sup.main(["--simbolo", "WDOU26", "--gravar", str(tmp_path)])
    assert codigo != 0, "dia sem negocio nenhum saiu como SUCESSO"
    saida = capsys.readouterr().out
    assert "ZERO negocios" in saida
    assert "MetaTrader 5" in saida, "a mensagem tem de dizer onde olhar"


def test_main_passa_quando_houve_negocio(tmp_path, monkeypatch, capsys):
    """O outro lado: um dia gravado de verdade nao pode falhar, senao a
    rotina vira alarme constante e o operador para de olhar."""
    import scripts.supervisionar_gravacao as sup

    monkeypatch.setattr(sup, "supervisionar", lambda **k: 0)
    monkeypatch.setattr(sup, "_lancar_de_verdade", lambda **k: (lambda d: (0, 0.0)))
    _gravar(tmp_path, "WDOU26", dt.date.today(), 1234)

    assert sup.main(["--simbolo", "WDOU26", "--gravar", str(tmp_path)]) == 0
    assert "1234 negocios gravados" in capsys.readouterr().out
