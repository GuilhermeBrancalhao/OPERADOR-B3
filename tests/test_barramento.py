from __future__ import annotations

from dataclasses import dataclass

from fluxopro.core.barramento import Barramento


@dataclass(frozen=True, slots=True)
class _EventoTeste:
    valor: int


@dataclass(frozen=True, slots=True)
class _OutroEvento:
    valor: int


def test_ordem_por_prioridade_e_inscricao() -> None:
    barramento = Barramento()
    chamadas: list[str] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append("baixa_1"), prioridade=10)
    barramento.assinar(_EventoTeste, lambda e: chamadas.append("alta"), prioridade=0)
    barramento.assinar(_EventoTeste, lambda e: chamadas.append("baixa_2"), prioridade=10)

    barramento.publicar(_EventoTeste(valor=1))

    assert chamadas == ["alta", "baixa_1", "baixa_2"]


def test_apenas_assinantes_do_tipo_exato_sao_chamados() -> None:
    barramento = Barramento()
    chamadas: list[int] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append(e.valor))
    barramento.publicar(_OutroEvento(valor=99))

    assert chamadas == []


def test_publicar_sem_assinantes_nao_falha() -> None:
    barramento = Barramento()
    barramento.publicar(_EventoTeste(valor=1))


def test_mesma_prioridade_multiplos_tipos_independentes() -> None:
    barramento = Barramento()
    chamadas: list[str] = []

    barramento.assinar(_EventoTeste, lambda e: chamadas.append(f"teste:{e.valor}"))
    barramento.assinar(_OutroEvento, lambda e: chamadas.append(f"outro:{e.valor}"))

    barramento.publicar(_EventoTeste(valor=1))
    barramento.publicar(_OutroEvento(valor=2))

    assert chamadas == ["teste:1", "outro:2"]
