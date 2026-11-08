@echo off
title Servidor Garde - Localhost 8000
echo ========================================================
echo   Iniciando Servidor Local Garde (http://localhost:8000)
echo ========================================================
echo.

cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ========================================================
echo  IMPORTANTE: Manten esta ventana abierta mientras uses la web.
echo  Si la cierras o pulsas Ctrl+C, el servidor se detendra.
echo ========================================================
echo.

if exist "C:\Users\aleja\miniconda3\python.exe" (
    "C:\Users\aleja\miniconda3\python.exe" app.py
) else (
    python app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [AVISO] El servidor se ha detenido (codigo: %ERRORLEVEL%).
    echo ========================================================
    pause
)
