@echo off
title BOT PACKBALL - CONFIGURAR JANELA OPERACIONAL
cd /d "C:\Users\Leonardo\Documents\BOT IA DO 0"
set PYTHONIOENCODING=utf-8:backslashreplace
set PYTHONUTF8=1
"C:\Users\Leonardo\Documents\BOT IA DO 0\.venv\Scripts\python.exe" -u monitor_ao_vivo.py --configurar-packball
echo.
echo A configuracao da janela operacional terminou. Esta janela permanecera aberta para mostrar o resultado.
pause
