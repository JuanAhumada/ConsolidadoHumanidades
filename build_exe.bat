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

call "%~dp0empaquetado\compilar_lanzador.bat"
if errorlevel 1 (
    echo Error al compilar el lanzador
    exit /b 1
)
copy /Y empaquetado\Lanzador.exe "%DIST%\..\..\ConsolidadoHumanidades.exe" >nul 2>nul

echo.
echo Empaquetando ZIP para usuarios...
if not exist "release" mkdir release
if exist "release\ConsolidadoHumanidades-Windows.zip" del /F /Q "release\ConsolidadoHumanidades-Windows.zip"
if exist "release\_zip_stage" rmdir /S /Q "release\_zip_stage"
mkdir "release\_zip_stage"
copy /Y empaquetado\Lanzador.exe "release\_zip_stage\ConsolidadoHumanidades.exe" >nul
xcopy /E /I /Q /Y "%DIST%" "release\_zip_stage\ConsolidadoHumanidades" >nul
tar.exe -a -c -f "release\ConsolidadoHumanidades-Windows.zip" -C "release\_zip_stage" ConsolidadoHumanidades.exe ConsolidadoHumanidades
rmdir /S /Q "release\_zip_stage"

echo.
echo Listo: %DIST%\ConsolidadoHumanidades.exe
echo Distribuya la carpeta completa dist\ConsolidadoHumanidades
endlocal
