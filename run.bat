@echo off
title pivot-x-sentinel -- bot + API
cd /d "%~dp0"

echo ============================================================
echo   pivot-x-sentinel -- arrancando bot + API local
echo   symbol/perfil/magic los define api/app.py (defaults) o
echo   lo que se mande via POST /start desde el panel.
echo   Panel: abrir panel/index.html o pegarle a http://127.0.0.1:8000
echo   Para parar: Ctrl+C en esta ventana.
echo ============================================================
echo.

"C:\Users\Chicho\AppData\Local\Programs\Python\Python310\python.exe" -m uvicorn api.app:app --host 127.0.0.1 --port 8000

echo.
echo ============================================================
echo   El proceso termino (Ctrl+C, crash, o cierre). Revisar arriba.
echo ============================================================
pause
