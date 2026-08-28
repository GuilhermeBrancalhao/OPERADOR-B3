@echo off
REM Retrato do painel OPERADOR B3 pelo PIPELINE COMPLETO (livro, microestrutura,
REM detectores de tape, motor) com dados REAIS do pregao de 27/08.
REM
REM Uso:  capturar.cmd <caminho_saida.png>
REM
REM `--de 12:00` e a ABERTURA do WDO em UTC (09:00 de Brasilia). O valor
REM anterior (13:00) as vezes devolvia "0 negocios" dependendo do recorte, e um
REM retrato vazio faz o critico julgar a fixture em vez do produto.
REM
REM 120s de parede cobrem ~11 min de tape (o replay anda a ~5x o tempo real):
REM suficiente para as regioes de LIVRO (decisao, banner, maker, evidencias),
REM que e o que esta fixture existe para mostrar. Para candle/Renko/VAP com o
REM pregao inteiro use `capturar_sessao.py`, que carrega os 158 mil negocios.
cd /d "%~dp0.."
python scripts\painel.py ^
  --fonte replay --arquivo dados --data 2026-08-27 --de 12:00 ^
  --sem-verificar-hash --workspace "OPERADOR B3" --simbolo WDOU26 ^
  --retrato "%~1" --duracao 120 --largura 1920 --altura 1080
