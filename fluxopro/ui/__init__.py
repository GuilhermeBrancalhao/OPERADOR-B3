"""Camada de interface do FluxoPro — PySide6 + pyqtgraph.

A decisao de stack esta em `design/direcao_visual.md` §2, com numeros
medidos. O achado que manda na arquitetura desta pasta NAO e o toolkit:
e a estrategia de desenho. O mesmo footprint em Qt vai de 13,3 fps
(repintando o quadro inteiro) para 560 fps (repintura incremental) —
fator 40. O gargalo e atravessar a fronteira Python<->C++ milhares de
vezes por quadro; 7.200 chamadas a uma funcao VAZIA ja custam 1,04 ms.

Por isso `base/painel_denso.py` e pre-requisito, nao otimizacao: nenhum
painel denso repinta o quadro inteiro por tick.

Importar este pacote NAO exige `QApplication` viva — `tokens` e `formato`
sao puros o suficiente para rodar em teste sem tela. Os paineis, sim,
precisam de aplicacao Qt (use `QT_QPA_PLATFORM=offscreen` em CI).
"""
