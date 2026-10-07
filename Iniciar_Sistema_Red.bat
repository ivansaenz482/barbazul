@echo off
title Sistema de Facturacion - Barbazul (Servidor de Red)
cd /d "%~dp0"

echo ============================================================
echo   Iniciando Sistema de Facturacion - Barbazul (Modo Red)
echo   Esta computadora actua como SERVIDOR para las demas.
echo ============================================================
echo.

rem Usa el entorno virtual si existe; si no, usa el Python del sistema.
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

start "Servidor Sistema Facturacion (Red)" cmd /k python run_produccion.py

timeout /t 3 /nobreak >nul

start http://127.0.0.1:5010

echo.
echo El sistema se esta abriendo en tu navegador.
echo NO CIERRES la otra ventana negra (el servidor) mientras las demas
echo computadoras del local esten usando el sistema.
echo.
pause
