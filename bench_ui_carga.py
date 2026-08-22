#!/usr/bin/env python
"""Contencao de GIL entre a fonte e a interface — MEDICAO, nao portao.

    python bench_ui_carga.py

Este numero achou um defeito real e por isso existe. Com a fonte rodando numa
thread propria e sem espera nenhuma (simulador, ou replay em `--velocidade
max`), o quadro do DOM saia de sub-milissegundo para **12 ms de PAREDE**. O
que denunciou foi separar `time.thread_time()` de `time.perf_counter()`: o
custo de CPU era sub-ms e os 12 ms eram espera pura. Virou o `--gil-switch`
de `scripts/painel.py`, com a tabela medida no docstring de la.

## Por que MEDICAO e nao portao de CI

Tentei duas vezes transformar isto em teste, e as duas foram instaveis:

1. **Piso absoluto de 5 quadros/s.** Reprovava ao desligar um modulo que nao
   tem nada com a interface — porque, com produtor sem espera, pipeline mais
   LEVE inunda mais forte e a UI fica mais faminta. Medido no mesmo commit:
   tudo ligado 16,5 fps, sem metodologia 2,0, sem microestrutura 1,5. O piso
   media o peso do pipeline e chamava isso de saude da tela.
2. **Razao entre dois intervalos de troca.** Conceitualmente certa — e a
   mesma forma do portao cheio/incremental, que e o instrumento mais
   confiavel do projeto —, mas instavel na pratica: duas medicoes de
   contencao no mesmo processo nao sao independentes. Compartilham cache,
   coletor e escalonador, e a segunda herda o estado da primeira.

Portao que reprova por ordem de execucao ensina todo mundo a ignorar portao.
O que sobrou em `tests/test_ui_desempenho.py` e so o deterministico: sob
carga, a interface desenha pelo menos um quadro. Fluidez e assunto daqui.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402


class Medicao:
    def _quadros_com_intervalo(self, qapp, intervalo: float) -> tuple[int, int]:
        """Roda 2 s do simulador inundando e devolve (quadros, negocios).

        Um so lugar monta o cenario, porque a comparacao entre dois intervalos
        de troca de GIL so vale se as duas medidas vierem do MESMO caminho.
        """
        import sys
        import threading
        import time as _time

        from fluxopro.app.config import ConfigOperacao, ConfigSimulador, FonteDados
        from fluxopro.app.montagem import montar
        from fluxopro.ui.janela import JanelaFluxo
        from fluxopro.ui.ponte import PonteFluxo

        anterior = sys.getswitchinterval()
        sys.setswitchinterval(intervalo)
        config = ConfigOperacao(
            symbol="WDOV26",
            fonte=FonteDados.SIMULADOR,
            simulador=ConfigSimulador(seed=7, n_eventos=10**9, taxa_eventos_s=500.0),
        )
        ref: dict = {}
        montagem = montar(
            config,
            ao_sinal=lambda e: ref["p"].registrar_evento(e),
            ao_deteccao=lambda e: ref["p"].registrar_evento(e),
        )
        ponte = PonteFluxo(montagem.barramento)
        ref["p"] = ponte
        janela = JanelaFluxo(ponte, config.symbol, config.price_grid())
        janela.resize(1280, 800)
        janela.show()

        thread = threading.Thread(target=montagem.fonte.iniciar, daemon=True)
        thread.start()
        try:
            fim = _time.perf_counter() + 2.0
            while _time.perf_counter() < fim:
                qapp.processEvents()
            quadros = janela.dom.quadros_desenhados
            negocios = montagem.sessao.contadores.n_trades_bus
        finally:
            montagem.fonte.parar()
            thread.join(timeout=5.0)
            janela.close()
            montagem.sessao.finalizar()
            sys.setswitchinterval(anterior)
        return quadros, negocios

    def test_o_intervalo_de_troca_de_gil_compra_quadros(self, qapp):
        """O portao virou RAZAO, e a razao e a unica forma honesta aqui.

        A primeira versao deste teste afirmava um piso absoluto de 5 quadros/s
        e era **fragil por um motivo que so apareceu quando o pipeline
        engordou**: com o produtor sem espera nenhuma, quanto MAIS leve o
        pipeline, mais rapido ele inunda e mais faminta fica a UI. Um
        construtor mediu, no mesmo commit: tudo ligado **16,5 fps**, sem
        metodologia **2,0**, sem microestrutura **1,5**. Ou seja, o piso
        absoluto media o peso do pipeline e o chamava de saude da interface —
        e reprovava ao ser desligado um modulo que nao tem nada com a UI.

        A propriedade que realmente importa e a que o `--gil-switch` de
        `scripts/painel.py` existe para comprar: com o intervalo do produto, a
        thread do Qt tem de conseguir **mais quadros** do que com o padrao do
        CPython, sob a mesma carga. Isso e uma RAZAO — sobrevive a trocar de
        maquina, de peso de pipeline e de versao do Qt, porque as duas medidas
        sofrem juntas. E o mesmo principio do portao cheio/incremental, que e o
        instrumento mais confiavel deste arquivo.
        """
        from scripts.painel import GIL_SWITCH_PADRAO

        quadros_produto, negocios = self._quadros_com_intervalo(qapp, GIL_SWITCH_PADRAO)
        quadros_cpython, _ = self._quadros_com_intervalo(qapp, 0.005)

        assert negocios > 0, "a fonte nao produziu nada"
        assert quadros_produto > 0, "a interface nao desenhou um quadro sequer"
        # Medido: ~2,5x. O piso de 1,3 deixa folga para CI compartilhada sem
        # deixar passar a reversao do intervalo, que e o que ele vigia.
        assert quadros_produto >= quadros_cpython * 1.3, (
            f"o intervalo do produto nao compra quadros: {quadros_produto} "
            f"contra {quadros_cpython} do padrao do CPython"
        )


def main() -> int:
    from scripts.painel import GIL_SWITCH_PADRAO

    app = QApplication.instance() or QApplication([])
    m = Medicao()
    print(f"{'intervalo de troca':<24} {'quadros/2s':>11} {'negocios':>10} {'ev/s':>8}")
    for rotulo, intervalo in (
        ("5 ms (padrao CPython)", 0.005),
        (f"{GIL_SWITCH_PADRAO*1000:g} ms (produto)", GIL_SWITCH_PADRAO),
        ("0,5 ms", 0.0005),
    ):
        quadros, negocios = m._quadros_com_intervalo(app, intervalo)
        print(f"{rotulo:<24} {quadros:>11} {negocios:>10} {negocios/2:>8.0f}")
    print()
    print(
        "Fluidez de tela e vazao de ingestao disputam a mesma CPU. Com feed "
        "REAL o produtor e I/O-bound e devolve o GIL sozinho; a disputa so e "
        "severa com produtor sintetico ou replay acelerado."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
