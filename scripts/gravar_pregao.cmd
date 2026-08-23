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
REM Por que --duracao e nao "ate o mercado fechar": o produto nao sabe o
REM calendario da B3 (feriado, leilao estendido, sessao encurtada). Um limite de
REM parede e honesto sobre o que ele sabe — e o Gravador fecha o dia com meta e
REM hash mesmo sendo interrompido.
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
python scripts\operar.py ^
  --fonte mt5 ^
  --simbolo WDOU26 ^
  --gravar dados\ ^
  --duracao 34200 ^
  --status-a-cada 300 >> "%LOG%" 2>&1

echo FIM %date% %time% (codigo %ERRORLEVEL%) >> "%LOG%"
endlocal
