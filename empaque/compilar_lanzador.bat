@echo off
setlocal
cd /d "%~dp0"

set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
    echo No se encontro el compilador C# de .NET Framework.
    exit /b 1
)

set ICON=
if exist "%~dp0icono.ico" set ICON=/win32icon:"%~dp0icono.ico"

"%CSC%" /nologo /target:winexe /optimize+ /platform:x64 %ICON% /out:"%~dp0Lanzador.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "%~dp0Lanzador.cs"
if errorlevel 1 exit /b 1

copy /Y "%~dp0Lanzador.exe" "%~dp0..\ConsolidadoHumanidades.exe" >nul
echo Lanzador: %~dp0..\ConsolidadoHumanidades.exe
endlocal
