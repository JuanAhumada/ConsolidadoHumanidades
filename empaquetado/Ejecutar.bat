@echo off
setlocal
cd /d "%~dp0"

if not exist "ConsolidadoHumanidades.exe" (
    echo No esta ConsolidadoHumanidades.exe en esta carpeta.
    pause
    exit /b 1
)

for %%A in ("ConsolidadoHumanidades.exe") do set SIZE=%%~zA
if %SIZE% LSS 1000000 (
    echo.
    echo Este .exe no es el programa real ^(pesa %SIZE% bytes^).
    echo.
    echo El boton "Download ZIP" de GitHub NO trae los binarios.
    echo Esos archivos estan en Git LFS.
    echo.
    echo Opciones:
    echo  1. Clone el repo con Git y ejecute:  git lfs pull
    echo  2. Descargue el paquete del Release en GitHub
    echo     ^(ConsolidadoHumanidades-Windows.zip^)
    echo.
    pause
    exit /b 1
)

if not exist "_internal\" (
    echo Falta la carpeta _internal.
    echo Tiene que extraer la carpeta completa, no solo el .exe.
    pause
    exit /b 1
)

echo Abriendo Consolidado de Humanidades...
start "" "ConsolidadoHumanidades.exe"
endlocal
