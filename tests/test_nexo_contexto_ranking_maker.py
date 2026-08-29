"""Cobre o achado de auditoria pos-entrega (28/08/2026, item 24 do documento
"MUDANCAS E IMPLEMENTACOES"): o ranking "1o/2o/3o" do MakerProxy tinha DOIS
defeitos que o portao `asg.leitura_e_coerente` nao pegava, porque o texto e
livre (`LinhaMatrizASG.detalhe`), nunca vira uma leitura formal —

1. Componente com pontuacao exatamente zero podia imprimir "-0%" (a mesma
   familia ja corrigida em EQUILIBRIO/PRESENCA/RITMO, renascida aqui).
2. As tres linhas saiam sempre em cinza neutro, sem cor de direcao — a
   unica parte da superficie sem verde/rosa por lado.
"""

from types import SimpleNamespace

from fluxopro.ui import tema_asg
from fluxopro.ui.paineis.asg import _ranking_componentes_maker
from fluxopro.ui.paineis.nexo.contexto import cor_da_linha_ranking


def _componente(nome, pontuacao, n_evidencias=1):
    return SimpleNamespace(componente=nome, pontuacao=pontuacao, n_evidencias=n_evidencias)


def _maker(componentes):
    return SimpleNamespace(componentes=componentes)


def test_componente_negativo_zero_nao_imprime_menos_zero():
    texto = _ranking_componentes_maker(_maker([_componente("ABSORCAO", -1e-12)]))
    assert "-0%" not in texto
    assert "+0%" in texto


def test_componente_positivo_e_negativo_de_verdade_preservam_sinal():
    texto = _ranking_componentes_maker(
        _maker([_componente("DIVERGENCIA", 0.70), _componente("REPOSICAO", -0.20)])
    )
    linhas = texto.splitlines()
    assert "+70%" in linhas[0]
    assert "-20%" in linhas[1]


def test_ranking_ordena_por_magnitude_absoluta():
    texto = _ranking_componentes_maker(
        _maker([_componente("A", 0.10), _componente("B", -0.90), _componente("C", 0.50)])
    )
    linhas = texto.splitlines()
    assert linhas[0].split()[1] == "B"
    assert linhas[1].split()[1] == "C"
    assert linhas[2].split()[1] == "A"


def test_cor_da_linha_ranking_positiva_e_verde():
    assert cor_da_linha_ranking("1o DIVERGENCIA  +70%  giro 3") == tema_asg.NEXO_VERDE


def test_cor_da_linha_ranking_negativa_e_rosa():
    assert cor_da_linha_ranking("2o REPOSICAO  -20%  giro 5") == tema_asg.NEXO_ROSA


def test_cor_da_linha_ranking_sem_percentual_e_neutra():
    assert cor_da_linha_ranking("linha sem numero nenhum") == tema_asg.NEXO_MUTED


def test_cor_da_linha_ranking_nunca_diverge_do_sinal_impresso():
    """Trava a coerencia: a cor SEMPRE deriva do mesmo numero que a linha
    imprime, para as duas nunca poderem discordar (o defeito da familia).

    Comparacao contra o sinal EXIBIDO (arredondado), nao o bruto: um score
    real que arredonda para "0%" na tela tem de sair neutro na cor tambem —
    e exatamente essa concordancia (bruto negativo, exibicao "+0%", cor
    neutra) que a correcao do arredondamento existe para garantir.
    """

    for pontuacao in (-0.9, -0.3, -0.001, 0.001, 0.3, 0.9):
        texto = _ranking_componentes_maker(_maker([_componente("X", pontuacao)]))
        cor = cor_da_linha_ranking(texto)
        exibido = round(pontuacao * 100)
        esperado = (
            tema_asg.NEXO_CIANO if exibido == 0
            else tema_asg.NEXO_VERDE if exibido > 0
            else tema_asg.NEXO_ROSA
        )
        assert cor == esperado, f"pontuacao={pontuacao} texto={texto!r} cor={cor}"


def test_nenhum_valor_nao_zero_imprime_menos_zero_apos_arredondar():
    """Achado pelo proprio teste da correcao: -0,001 (VENDA real, so que
    pequena) arredondava para "-0%" mesmo com `_sem_zero_negativo` aplicado
    ao bruto — o corte tem de ser no valor JA ARREDONDADO."""

    texto = _ranking_componentes_maker(_maker([_componente("X", -0.001)]))
    assert "-0%" not in texto
    assert "+0%" in texto
