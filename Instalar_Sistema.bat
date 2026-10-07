@echo off
chcp 65001 >nul
title Instalador Sistema de Facturacion - Barbazul
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Solicitando permisos de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================
echo   Instalador del Sistema de Facturacion - Barbazul
echo   Un solo boton: instala Python y MySQL si faltan, crea la
echo   base de datos, el usuario administrador y los iconos.
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"

echo.
echo Proceso terminado.
pause
