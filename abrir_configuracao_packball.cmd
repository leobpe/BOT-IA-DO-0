@echo off
title PACKBALL - CONFIGURAR SCANNER E COLUNAS
cd /d "C:\Users\Leonardo\Documents\BOT IA DO 0"
set PYTHONIOENCODING=utf-8:backslashreplace
set PYTHONUTF8=1
"C:\Users\Leonardo\Documents\BOT IA DO 0\.venv\Scripts\python.exe" -u packball_login.py --abrir-sessao
echo.
echo A configuracao do PackBall foi encerrada. Esta janela permanecera aberta para mostrar o resultado.
pause
