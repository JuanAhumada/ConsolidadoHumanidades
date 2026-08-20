@echo off
setlocal
cd /d "%~dp0"

set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
    echo No se encontro el compilador C# de .NET Framework.
    exit /b 1
)

"%CSC%" /nologo /target:winexe /optimize+ /platform:x64 /out:"%~dp0Lanzador.exe" /reference:System.Windows.Forms.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "%~dp0Lanzador.cs"
if errorlevel 1 exit /b 1

copy /Y "%~dp0Lanzador.exe" "%~dp0..\ConsolidadoHumanidades.exe" >nul
echo Lanzador: %~dp0..\ConsolidadoHumanidades.exe
endlocal
