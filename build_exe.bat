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

echo Generando icono del instalador...
python -c "from pathlib import Path; from PIL import Image; p=Path('consolidado/web/static/favicon.png'); Image.open(p).convert('RGBA').save('empaque/icono.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
if errorlevel 1 (
    echo No se pudo generar empaque\icono.ico
    exit /b 1
)

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
set PAQ_INICIAL=
if exist "empaque\paquete_inicial.zip" set PAQ_INICIAL=empaque\paquete_inicial.zip
if "%PAQ_INICIAL%"=="" if exist "ArchivosPrueba2026-1.zip" set PAQ_INICIAL=ArchivosPrueba2026-1.zip
if not "%PAQ_INICIAL%"=="" copy /Y "%PAQ_INICIAL%" "%DIST%\paquete_inicial.zip" >nul

call "%~dp0empaque\compilar_lanzador.bat"
if errorlevel 1 (
    echo Error al compilar el lanzador
    exit /b 1
)

echo.
echo Empaquetando ZIP para usuarios...
for /f "usebackq delims=" %%i in (`python -c "from consolidado.version import APP_VERSION; print(APP_VERSION)"`) do set APPVER=%%i
if "%APPVER%"=="" set APPVER=dev
echo %APPVER%> "%DIST%\VERSION.txt"
if not exist "release" mkdir release
if exist "release\ConsolidadoHumanidades-Windows.zip" del /F /Q "release\ConsolidadoHumanidades-Windows.zip"
del /F /Q "release\ConsolidadoHumanidades-*-Windows.zip" 2>nul
if exist "release\_zip_stage" rmdir /S /Q "release\_zip_stage"
mkdir "release\_zip_stage"
copy /Y empaque\Lanzador.exe "release\_zip_stage\ConsolidadoHumanidades.exe" >nul
xcopy /E /I /Q /Y "%DIST%" "release\_zip_stage\ConsolidadoHumanidades" >nul
if exist "%DIST%\paquete_inicial.zip" (
    copy /Y "%DIST%\paquete_inicial.zip" "release\_zip_stage\Archivos iniciales.zip" >nul
    if exist "release\_zip_stage\ConsolidadoHumanidades\paquete_inicial.zip" del /F /Q "release\_zip_stage\ConsolidadoHumanidades\paquete_inicial.zip"
    if exist "release\_zip_stage\ConsolidadoHumanidades\ArchivosPrueba2026-1.zip" del /F /Q "release\_zip_stage\ConsolidadoHumanidades\ArchivosPrueba2026-1.zip"
)
if exist "release\_zip_stage\Archivos iniciales.zip" (
    tar.exe -a -c -f "release\ConsolidadoHumanidades-Windows.zip" -C "release\_zip_stage" ConsolidadoHumanidades.exe "Archivos iniciales.zip" ConsolidadoHumanidades
) else (
    tar.exe -a -c -f "release\ConsolidadoHumanidades-Windows.zip" -C "release\_zip_stage" ConsolidadoHumanidades.exe ConsolidadoHumanidades
)
rmdir /S /Q "release\_zip_stage"

echo.
echo Listo: %DIST%\ConsolidadoHumanidades.exe
echo Version: v%APPVER%
echo ZIP: release\ConsolidadoHumanidades-Windows.zip
echo No hace falta publicar a git: el ZIP queda en release\
endlocal
