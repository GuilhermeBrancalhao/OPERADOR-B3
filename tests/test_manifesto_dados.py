"""O manifesto que torna o estudo auditavel sem publicar dado licenciado.

`/dados/` esta no `.gitignore` e tem de continuar: sao 26 MB de tick da B3,
licenciados da corretora. O efeito colateral e que os numeros publicados em
`PROGRESSO.md` — 200.899 negocios em 21/08, exaustao de 76,8% para 55,8%, a
tabela dos 32 pregoes — so eram verificaveis por quem tem os arquivos.

Um resultado que so o autor consegue reproduzir e uma afirmacao, nao uma
medicao.

`dados_manifesto.json` fecha isso pela metade que cabe num repositorio publico:
procedencia e integridade dos INSUMOS. Quem quiser conferir importa os mesmos
pregoes na propria conta, roda `--verificar`, e se os hashes baterem o estudo
inteiro reproduz.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.manifesto_dados import VERSAO_MANIFESTO, construir, verificar

RAIZ = Path(__file__).resolve().parent.parent
MANIFESTO = RAIZ / "dados_manifesto.json"
DADOS = RAIZ / "dados"


def _manifesto() -> dict:
    return json.loads(MANIFESTO.read_text(encoding="utf-8"))


def test_o_manifesto_esta_versionado_no_repositorio():
    """Sem ele, o estudo dos 32 pregoes nao tem como ser auditado por ninguem.

    Este teste nao depende de `dados/`: ele afirma que o ARTEFATO existe e esta
    bem formado. E o unico dos quatro que roda em qualquer clone.
    """
    assert MANIFESTO.exists(), (
        "dados_manifesto.json sumiu — regere com "
        "`python scripts/manifesto_dados.py --arquivo dados/`"
    )
    m = _manifesto()
    assert m["versao_manifesto"] == VERSAO_MANIFESTO
    assert m["n_dias"] > 0
    assert m["n_eventos_total"] > 0
    assert len(m["dias"]) == m["n_dias"]
    assert m["n_eventos_total"] == sum(d["n_eventos_total"] for d in m["dias"])


def test_o_manifesto_nao_carrega_dado_de_mercado():
    """A fronteira de licenciamento, como VARREDURA e nao como intencao.

    O manifesto responde "quais insumos foram usados, e estao integros?" — e
    nao "quanto o mercado andou?". A primeira pergunta cabe num repositorio
    publico; a segunda e o dado da corretora.

    A afirmacao varre TODAS as chaves de TODOS os dias contra uma lista de
    campos permitidos, em vez de conferir os campos que hoje se sabe que
    existem. Campo novo reprova por ser novo — que e a unica forma de a
    fronteira sobreviver a quem acrescentar algo sem pensar nisto aqui.

    `contagens`, `hashes_sha256` e `n_linhas_hasheadas` sao os TRES campos
    chaveados por tipo de evento/nome de arquivo (`Trade`, `BookDelta`,
    `book_deltas.csv`... — de `fluxopro.gravacao.formato.NOMES_ARQUIVO`), nao
    por dado de mercado. Primeiro dia com book de verdade (24/08) expos que
    "BookDelta" e "book_deltas.csv" contem a substring "delta" sem carregar
    um delta — dois falsos positivos, um em cada campo. A varredura de termo
    proibido olha os VALORES desses tres campos (contagem, hash, contagem de
    linha), nunca as chaves — o teste de campos permitidos acima ja cobre a
    forma das chaves.
    """
    permitidos = {
        "symbol",
        "data",
        "schema_versao",
        "contagens",
        "n_eventos_total",
        "inicio_utc",
        "fim_utc",
        "parcial",
        "hashes_sha256",
        "n_linhas_hasheadas",
    }
    proibidos = ("preco", "price", "vwap", "volume", "delta", "poc", "val", "vah")

    for dia in _manifesto()["dias"]:
        extras = set(dia) - permitidos
        assert not extras, (
            f"{dia['symbol']} {dia['data']}: campo(s) fora da lista permitida "
            f"{sorted(extras)} — se e metadado de integridade, acrescente a "
            "lista; se e dado de mercado, ele nao pode ir para o repositorio"
        )
        sem_nomes_de_tipo = dict(dia)
        for campo in ("contagens", "hashes_sha256", "n_linhas_hasheadas"):
            sem_nomes_de_tipo[campo] = sorted(str(v) for v in dia[campo].values())
        cru = json.dumps(sem_nomes_de_tipo, ensure_ascii=False).lower()
        for termo in proibidos:
            assert termo not in cru, (
                f"{dia['symbol']} {dia['data']}: o manifesto menciona {termo!r}"
            )


def test_todo_dia_do_manifesto_tem_hash_e_janela():
    """Contagem sem hash nao prova insumo; hash sem janela nao prova cobertura.

    Os dois juntos sao o que permite a um terceiro dizer "importei o mesmo
    pregao" em vez de "importei um pregao com o mesmo nome".
    """
    for dia in _manifesto()["dias"]:
        assert dia["hashes_sha256"], f"{dia['data']}: sem hash"
        for nome, valor in dia["hashes_sha256"].items():
            assert len(valor) == 64, f"{dia['data']}/{nome}: hash nao e sha256"
            assert dia["n_linhas_hasheadas"][nome] > 0
        assert dia["inicio_utc"] < dia["fim_utc"], f"{dia['data']}: janela invertida"
        assert dia["n_eventos_total"] == sum(dia["contagens"].values())


@pytest.mark.skipif(
    not DADOS.exists(), reason="gravacoes locais ausentes (dados/ e ignorado no git)"
)
def test_o_manifesto_bate_com_o_disco():
    """So roda em quem TEM as gravacoes — e ai vale como portao de verdade.

    O `skipif` e o ponto delicado deste arquivo: num clone limpo este teste nao
    roda, e um teste que nao roda nao protege nada. Por isso ele nao esta
    sozinho — os tres acima afirmam a forma do manifesto sem depender do disco.

    Aqui a afirmacao e a mais forte que existe: o que esta versionado descreve
    o que esta em disco, hash a hash. Se alguem regravar um dia e esquecer de
    regerar o manifesto, este teste reprova nomeando o dia.
    """
    divergencias = verificar(DADOS, _manifesto())
    assert not divergencias, "manifesto e disco divergem:\n" + "\n".join(
        f"  {linha}" for linha in divergencias
    )


@pytest.mark.skipif(
    not DADOS.exists(), reason="gravacoes locais ausentes (dados/ e ignorado no git)"
)
def test_construir_le_o_metadado_e_nao_recalcula_o_hash():
    """Uma fonte de verdade por numero.

    `construir` le o `meta.json`, que ja carrega o hash calculado pelo
    `Gravador` no momento da escrita. Recalcular aqui abriria a porta para um
    manifesto que descreve o arquivo de hoje enquanto o metadado descreve o de
    ontem — duas verdades sobre o mesmo dia, e nenhuma delas identificavel como
    a errada.
    """
    manifesto = construir(DADOS)
    for dia in manifesto["dias"]:
        meta = json.loads(
            (DADOS / dia["symbol"] / dia["data"] / "meta.json").read_text(
                encoding="utf-8"
            )
        )
        assert dia["hashes_sha256"] == meta["hashes_sha256"]
