"""Tema do workspace ASG-like, derivado dos tokens visuais do FluxoPro.

O modulo e pequeno de proposito: ele nomeia papeis da nova superficie sem
criar uma segunda identidade visual.  Todas as cores-base continuam vindo de
``ui.tokens`` e sao alocadas uma unica vez no import, como nos demais paineis
QPainter do projeto.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from fluxopro.ui import tokens

# Superficies
FUNDO = tokens.BG_BASE
PAINEL = tokens.BG_SURFACE
CABECALHO = tokens.BG_RAISED
BORDA = tokens.BORDER
BORDA_FORTE = tokens.BORDER_STRONG

# Identidade das cinco areas. Cor e apenas o segundo canal: cada area tambem
# tem titulo e numero de etapa pintados pelo componente.
DADOS = tokens.VWAP
PROCESSAMENTO = tokens.ABSORPTION
MATRIZ = tokens.SIGNAL
DECISAO = tokens.OK_FORTE
EVIDENCIAS = tokens.NEUTRAL_FORTE

# Chips usam texto escuro sobre fundos de luminancia alta, o mesmo criterio
# medido nos paineis ``metodo`` e ``matriz``.
CHIP_TEXTO = tokens.BG_BASE
CONFIANCA_ALTA = tokens.OK_FORTE
CONFIANCA_MEDIA = tokens.ALERT
CONFIANCA_BAIXA = tokens.ABSORPTION
CONFIANCA_INDISPONIVEL = tokens.NEUTRAL_FORTE

ESTADO_AGUARDANDO = tokens.NEUTRAL_FORTE
ESTADO_DESCONHECIDO = tokens.NEUTRAL_FORTE
ESTADO_AO_VIVO = tokens.OK_FORTE
ESTADO_ATRASADO = tokens.ALERT
ESTADO_SEM_BOOK = tokens.ABSORPTION
ESTADO_ERRO = tokens.DANGER
ESTADO_REPLAY = tokens.POC

# Paleta da superficie NEXO. A referencia fornecida usa preto quase absoluto,
# verde/rosa neon e linhas muito finas. Esta e uma identidade propria, sem
# reutilizar logotipo, avatar ou ativo visual de terceiros.
#
# Round 3 (coerencia-vies-e-identidade): o auditor encontrou ``NEXO_VERDE``
# pintando DUAS coisas ao mesmo tempo em consumidores deste modulo — leitura
# de alta (candle de alta, chip de compra, lado comprador da pressao — legit
# em ``candles.py``/``forca.py``/``pressao.py``/``estatistica.py``, que
# consomem esta constante por import direto) E cromo estrutural decorativo
# (anel/moldura/coluna/eixo — o antigo comentario deste bloco chamava isso de
# "cromo decorativo da marca", e ERA esse o papel duplo que fazia verde
# aparecer sem significado unico: o operador nao consegue saber, so pelo
# hue, se um elemento verde e "alta" ou e so a cor da casca do produto).
#
# Contrato revisado, dai em diante:
# - ``NEXO_VERDE``/``NEXO_ROSA`` ficam RESERVADOS para leitura direcional
#   (alta/baixa) nos paineis que optam pelo eixo neon em vez do eixo
#   acessivel (ver abaixo). Nenhum consumidor novo pode usa-los para
#   borda/moldura/anel/coluna/eixo/rotulo — para cromo estrutural, os tokens
#   corretos ja existem neste modulo: ``NEXO_GRADE`` (linha/grade),
#   ``NEXO_MUTED``/``NEXO_TEXTO`` (rotulo/legenda), ``BORDA``/``BORDA_FORTE``
#   (moldura de painel). Nao inventar um cinza literal novo.
# - ``NEXO_AMARELO`` continua fora do eixo direcional (e leitura de ESTADO —
#   replay/atencao — nao de lado).
# - Peso comparavel entre os dois lados foi conferido em HSL (nao so "parece
#   saturado"): ``NEXO_VERDE`` #26F58A = H149 L55,5% S91,2%; ``NEXO_ROSA``
#   #FF3F68 = H347 L62,4% S100%. O lado venda ja iguala ou supera o lado
#   compra em luminancia e saturacao — se um consumidor especifico parecer
#   "mais fraco" no quadro renderizado, a causa e alpha/espessura escolhida
#   NAQUELE consumidor, nao o token em si.
# - GAP CONHECIDO, aberto: ao contrario de ``tokens.BUY``/``tokens.SELL``
#   (resolvidos so via ``tokens.Paleta``/``estado.paleta``, o unico caminho
#   que colapsa em ``--sem-cor`` via ``tokens.PALETA_SEM_COR``),
#   ``NEXO_VERDE``/``NEXO_ROSA`` sao ``QColor`` estaticos alocados uma vez no
#   import (§ do topo deste arquivo) e NAO colapsam sozinhos em
#   ``--sem-cor``. Qualquer consumidor que os use para ler direcao tem que
#   decidir a cor por ``estado.paleta`` (como ``paineis.nexo.vies.cor_vies``
#   ja faz) e nunca por ``tema_asg.NEXO_VERDE``/``NEXO_ROSA`` direto — do
#   contrario o vies daquele painel sobrevive ao modo sem cor por engano.
#   Migrar cada consumidor exige editar o arquivo dele; este modulo so pode
#   documentar o contrato, nao fazer cumprir por fora dos seus dois arquivos.
#
# Fora de escopo desta parte (arquivos que este builder nao possui, achados
# so por import de ``tema_asg.NEXO_VERDE``/``NEXO_ROSA``/``NEXO_AMARELO``,
# sem ler o corpo de nenhum deles): ``nucleo.py`` (aneis de contador
# 2184/703), ``ladder.py`` (moldura dos chips da escada), ``niveis.py``
# (coluna de preco/tick a esquerda), ``grafico.py``/``cockpit.py`` (moldura
# de painel e eixo), ``banner.py`` (chip ALERTA e faixa ALGORITHMIC
# STANDBY — o auditor quer estes em ambar de estado, nao cinza metalico;
# nenhum destes dois nomes aparece nas constantes de ESTADO deste modulo,
# entao o token que eles realmente pintam so se descobre lendo o arquivo,
# fora do escopo desta parte). Repintar cada um exige trocar, NAQUELE
# arquivo, a referencia a ``NEXO_VERDE``/cinza fixo pelo token neutro (ou
# ``tokens.ALERT`` no caso do banner) — reportado como pendente.
NEXO_FUNDO = QColor("#030609")
# Superficies translucidas: o fundo nativo continua sendo uma unica camada
# por baixo de todos os modulos. O alpha e intencional e nao altera texto,
# linhas ou dados; apenas permite que o wallpaper seja percebido atraves dos
# paineis sem criar margens ou divisorias extras.
NEXO_PAINEL = QColor(7, 12, 18, 12)
NEXO_PAINEL_ALTO = QColor(11, 17, 24, 22)
NEXO_GRADE = QColor("#17232C")
NEXO_CIANO = QColor("#53D5E8")
NEXO_VERDE = QColor("#26F58A")
NEXO_ROSA = QColor("#FF3F68")
NEXO_AMARELO = QColor("#F5D547")
NEXO_TEXTO = QColor("#DCE9EC")
NEXO_MUTED = QColor("#6F858D")


def _com_alpha(cor: QColor, alpha: int) -> QColor:
    copia = QColor(cor)
    copia.setAlpha(alpha)
    return copia


# Faixas do eixo de ESTADO/cromo (ao vivo, replay, moldura da marca) — NAO
# usar para tingir fundo de leitura compra/venda: para isso o par coerente e
# ``FUNDO_COMPRA``/``FUNDO_VENDA`` logo abaixo, que ja deriva do MESMO
# ``tokens.BUY``/``tokens.SELL`` usado no resto do produto (e por isso
# colapsa junto em ``--sem-cor``; estas nao colapsam, porque nao carregam
# direcao).
NEXO_VERDE_FAIXA = _com_alpha(NEXO_VERDE, 34)
NEXO_ROSA_FAIXA = _com_alpha(NEXO_ROSA, 34)
NEXO_CIANO_FAIXA = _com_alpha(NEXO_CIANO, 28)


# Disco/anel do bloco de IDENTIDADE (``paineis.nexo.vies.desenhar``). Cromo
# neutro de proposito, NAO ciano e NAO amarelo.
#
# Round 2 encontrou os dois hues do NEXO carregando 3+ papeis cada ao mesmo
# tempo: ciano ja e "ULT/preco" (``NEXO_CIANO`` acima, consumido por
# ``niveis.py``/``candles.py``) e "ticker" em outras regioes do quadro, e
# amarelo ja e "AGUARDAR/estado" (``tokens.ALERT``, quase indistinguivel a
# olho de ``NEXO_AMARELO``) e "nivel/media" (consumido por ``candles.py``/
# ``ladder.py``). Um disco de marca ciano ou amarelo seria um QUARTO papel
# para o mesmo canal de cor — exatamente o defeito que o auditor apontou
# (cor sem significado unico). A marca em si e decorativa e nao carrega
# leitura de direcao (quem carrega e o triangulo central, resolvido por
# ``cor_vies``); por isso ela usa tons neutros que ja existem no eixo de
# texto/estrutura (``NEXO_TEXTO``/``NEXO_MUTED``), sem inventar um terceiro
# eixo cromatico.
NEXO_IDENTIDADE_ANEL = _com_alpha(NEXO_TEXTO, 150)
NEXO_IDENTIDADE_NUCLEO = NEXO_MUTED


# Pre-alocados: construir QColor dentro de uma linha quente de QPainter custa
# uma travessia Python/C++ por celula.
#
# Este e o par canonico de fundo tingido para a leitura de direcao em toda a
# superficie NEXO — mesma matiz (``tokens.BUY``/``tokens.SELL``) e mesmo
# alpha (38) que qualquer regiao deve usar ao sinalizar compra/venda de
# fundo, para o quadro inteiro manter uma unica curva de saturacao no eixo
# direcional em vez de cada regiao inventar o proprio par.
FUNDO_COMPRA = _com_alpha(tokens.BUY, 38)
FUNDO_VENDA = _com_alpha(tokens.SELL, 38)
FUNDO_ALERTA = _com_alpha(tokens.ALERT, 28)
FUNDO_ERRO = _com_alpha(tokens.DANGER, 30)
FUNDO_NEUTRO = _com_alpha(tokens.NEUTRAL, 22)


__all__ = [
    "BORDA",
    "BORDA_FORTE",
    "CABECALHO",
    "CHIP_TEXTO",
    "CONFIANCA_ALTA",
    "CONFIANCA_BAIXA",
    "CONFIANCA_INDISPONIVEL",
    "CONFIANCA_MEDIA",
    "DADOS",
    "DECISAO",
    "ESTADO_AGUARDANDO",
    "ESTADO_AO_VIVO",
    "ESTADO_ATRASADO",
    "ESTADO_DESCONHECIDO",
    "ESTADO_ERRO",
    "ESTADO_REPLAY",
    "ESTADO_SEM_BOOK",
    "EVIDENCIAS",
    "FUNDO",
    "FUNDO_ALERTA",
    "FUNDO_COMPRA",
    "FUNDO_ERRO",
    "FUNDO_NEUTRO",
    "FUNDO_VENDA",
    "MATRIZ",
    "NEXO_AMARELO",
    "NEXO_CIANO",
    "NEXO_CIANO_FAIXA",
    "NEXO_FUNDO",
    "NEXO_GRADE",
    "NEXO_IDENTIDADE_ANEL",
    "NEXO_IDENTIDADE_NUCLEO",
    "NEXO_MUTED",
    "NEXO_PAINEL",
    "NEXO_PAINEL_ALTO",
    "NEXO_ROSA",
    "NEXO_ROSA_FAIXA",
    "NEXO_TEXTO",
    "NEXO_VERDE",
    "NEXO_VERDE_FAIXA",
    "PAINEL",
    "PROCESSAMENTO",
]
