@echo off
setlocal
title Consola de Metrologia - Andre

:: 1. Forzar variables de entorno críticas
set KMP_DUPLICATE_LIB_OK=TRUE
set CUDA_MODULE_LOADING=LAZY

:: 2. Priorizar las DLLs locales y del entorno virtual
set PATH=%CD%\MvImport;%CD%\.venv\Scripts;%PATH%

echo ====================================================
echo   INICIANDO SISTEMA DE DETECCION (MODO PORTABLE)
echo ====================================================
echo Directorio actual: %CD%
echo.

:: 3. Ejecución
:: Usamos "python.exe" del venv para asegurar que use TUS librerías
".\.venv\Scripts\python.exe" main.py

:: 4. Captura de errores
if %errorlevel% neq 0 (
    echo.
    echo ########## ERROR DETECTADO ##########
    echo El programa se cerro con el codigo: %errorlevel%
    echo Revisa si faltan dependencias o si el modelo best.pt esta en la raiz.
    pause
) else (
    echo.
    echo Programa finalizado correctamente.
    pause
)