@echo off
title PACKBALL - LOGIN DO BOT
cd /d "C:\Users\Leonardo\Documents\BOT IA DO 0"
set PYTHONIOENCODING=utf-8:backslashreplace
set PYTHONUTF8=1
"C:\Users\Leonardo\Documents\BOT IA DO 0\.venv\Scripts\python.exe" -u packball_login.py --manual --autorizar-nova-tentativa
echo.
echo O login do PackBall foi encerrado. Esta janela permanecera aberta para mostrar o resultado.
pause
