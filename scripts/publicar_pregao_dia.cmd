@echo off
REM ============================================================================
REM Publica no git (via Git LFS) os dados reais do pregao do dia, depois que
REM o Gravador ja fechou o dia (arquivos .gz gerados por `_dia_ja_finalizado`).
REM
REM Chamado pelo Agendador do Windows as 18:45 (15 min depois do fim da
REM gravacao, 18:30), seg-sex, so como reforco -- a gravacao pode terminar
REM atrasada em dia de leilao estendido.
REM ============================================================================

setlocal
set RAIZ=%~dp0..
set LOGDIR=%RAIZ%\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do set HOJE=%%c-%%b-%%a
set LOG=%LOGDIR%\publicar_%HOJE%.log

echo ============================================ >> "%LOG%"
echo INICIO %date% %time% >> "%LOG%"

cd /d "%RAIZ%"

git add dados\ dados_manifesto.json >> "%LOG%" 2>&1
git diff --cached --quiet
if %ERRORLEVEL%==0 (
    echo Nada novo para publicar hoje. >> "%LOG%"
) else (
    git commit -m "Dados reais do pregao %HOJE% (WDOU26)" >> "%LOG%" 2>&1
    git push origin main >> "%LOG%" 2>&1
)

echo FIM %date% %time% (codigo %ERRORLEVEL%) >> "%LOG%"
endlocal
