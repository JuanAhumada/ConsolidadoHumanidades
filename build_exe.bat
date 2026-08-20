@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -q -U pip
python -m pip install -q -r requirements.txt

echo.
echo Generando ejecutable...
pyinstaller --noconfirm --clean ConsolidadoHumanidades.spec

if errorlevel 1 (
    echo Error al generar el .exe
    exit /b 1
)

set DIST=dist\ConsolidadoHumanidades
copy /Y config.json "%DIST%\config.json" >nul
copy /Y config_fabrica.json "%DIST%\config_fabrica.json" >nul
if not exist "%DIST%\datos\entrada" mkdir "%DIST%\datos\entrada"
if not exist "%DIST%\salida" mkdir "%DIST%\salida"
if not exist "%DIST%\datos\entrada\.gitkeep" type nul > "%DIST%\datos\entrada\.gitkeep"
if not exist "%DIST%\salida\.gitkeep" type nul > "%DIST%\salida\.gitkeep"
copy /Y LEEME_EXE.txt "%DIST%\LEEME.txt" >nul
copy /Y empaquetado\Ejecutar.bat "%DIST%\Ejecutar.bat" >nul
copy /Y empaquetado\SI_NO_ABRE.txt "%DIST%\SI_NO_ABRE.txt" >nul

echo.
echo Listo: %DIST%\ConsolidadoHumanidades.exe
echo Distribuya la carpeta completa dist\ConsolidadoHumanidades
endlocal
