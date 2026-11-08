@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Servidor Garde - Localhost 8000
echo ========================================================
echo   Iniciando Servidor Local Garde (http://localhost:8000)
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Comprobar si hay un proceso huerfano en el puerto 8000 y liberarlo si es necesario
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo [AVISO] Se detecto una instancia previa en el puerto 8000 (PID: %%a).
    echo Liberando el puerto para evitar conflictos de conexion...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

:: 2. Localizar ejecutable de Python
set "PYTHON_EXE="
if exist "C:\Users\aleja\miniconda3\python.exe" (
    set "PYTHON_EXE=C:\Users\aleja\miniconda3\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR CRITICO] No se encontro ninguna instalacion de Python en el sistema.
    echo Asegurate de tener Python o Miniconda instalado y en el PATH.
    pause
    exit /b 1
)

echo Usando Python: %PYTHON_EXE%
echo.
echo ========================================================
echo  IMPORTANTE: Mantén esta ventana abierta mientras uses la web.
echo  Si la cierras o pulsas Ctrl+C, el servidor se apagara y
echo  la pagina web mostrara el error "Failed to fetch".
echo ========================================================
echo.

"%PYTHON_EXE%" app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [AVISO] El servidor se ha detenido (codigo de salida: %ERRORLEVEL%).
    echo Si lo detuviste intencionadamente con Ctrl+C, es normal.
    echo Si fue un error inesperado, revisa las lineas superiores.
    echo ========================================================
    pause
)
