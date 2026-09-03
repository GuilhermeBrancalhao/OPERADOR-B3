@echo off
REM ============================================================================
REM Grava o pregao AO VIVO do MT5 — tape E livro.
REM
REM Chamado pelo Agendador de Tarefas do Windows (tarefa "FluxoPro-GravarPregao",
REM segunda a sexta as 09:00). Roda sozinho ate o fim da sessao.
REM
REM PRE-REQUISITO QUE ESTE SCRIPT NAO CONSEGUE GARANTIR:
REM   o terminal MetaTrader 5 precisa estar ABERTO e LOGADO. Uma tarefa agendada
REM   nao digita senha, e o `initialize()` sem terminal devolve
REM   "IPC initialize failed". Por isso o log abaixo e a primeira coisa a
REM   conferir se um dia o arquivo do dia nao aparecer.
REM
REM Por que --fim e nao "ate o mercado fechar": o produto nao sabe o
REM calendario da B3 (feriado, leilao estendido, sessao encurtada). Um horario
REM de parede e honesto sobre o que ele sabe — e o Gravador fecha o dia com
REM meta e hash mesmo sendo interrompido.
REM
REM 24/08/2026: `operar.py` chamado direto morreu as 13:21 (Ctrl+C externo,
REM terminal MT5 continuou de pe) com fim previsto em 18:30 — quase 5h de
REM pregao sem ninguem gravando, e nada relancou sozinho. Por isso agora quem
REM roda aqui e `supervisionar_gravacao.py`, que reconecta `operar.py`
REM enquanto a janela nao fecha e o dia nao esta finalizado (retomar e seguro:
REM `Gravador` escreve em append e so recusa reabrir dia com `.gz`). Ver o
REM docstring de `scripts/supervisionar_gravacao.py` para o circuito de
REM seguranca contra MT5 fechado/deslogado o dia inteiro.
REM ============================================================================

setlocal
set RAIZ=%~dp0..
set LOGDIR=%RAIZ%\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do set HOJE=%%c-%%b-%%a
set LOG=%LOGDIR%\pregao_%HOJE%.log

echo ============================================ >> "%LOG%"
echo INICIO %date% %time% >> "%LOG%"

cd /d "%RAIZ%"
python scripts\supervisionar_gravacao.py ^
  --simbolo WDOU26 ^
  --gravar dados\ ^
  --fim 18:30 ^
  --status-a-cada 300 >> "%LOG%" 2>&1

set CODIGO=%ERRORLEVEL%

echo FIM %date% %time% (codigo %CODIGO%) >> "%LOG%"

REM PROPAGA O CODIGO (03/09/2026). Ate aqui o .cmd so ESCREVIA o codigo no
REM log: como o ultimo comando do lote era um `echo`, que sempre devolve 0, a
REM tarefa do Windows marcava sucesso mesmo com o supervisor falhando. Foi
REM assim que 01/09 e 02/09 apareceram como "resultado 0" sem ter gravado
REM pregao nenhum. Sem este `exit /b`, o portao de zero negocios existiria e
REM nao seria visto por ninguem.
endlocal & exit /b %CODIGO%
