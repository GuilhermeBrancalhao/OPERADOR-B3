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
