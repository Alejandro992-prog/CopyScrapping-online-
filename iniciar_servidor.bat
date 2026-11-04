@echo off
title Servidor Garde - Localhost 8000
echo ========================================================
echo   Iniciando Servidor Local Garde (http://localhost:8000)
echo ========================================================
echo.

cd /d "%~dp0"

if exist "C:\Users\aleja\miniconda3\python.exe" (
    "C:\Users\aleja\miniconda3\python.exe" app.py
) else (
    python app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] El servidor se ha detenido con codigo de error %ERRORLEVEL%.
    pause
)
