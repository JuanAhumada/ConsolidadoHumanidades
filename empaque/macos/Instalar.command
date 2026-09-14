#!/bin/bash
# Primera instalación o reparación del entorno local (macOS).
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
APP="$ROOT/app"

echo "=============================================="
echo " Consolidado de Humanidades — instalación Mac"
echo "=============================================="
echo

if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$ROOT" 2>/dev/null || true
fi

if [ ! -d "$APP" ] || [ ! -f "$APP/main.py" ]; then
  echo "No se encontró la carpeta app junto a este instalador."
  echo "Deje Instalar.command, la aplicación y la carpeta app en el mismo sitio."
  echo
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

es_python_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

PYTHON=""
for c in \
  python3.13 python3.12 python3.11 \
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
  /usr/local/bin/python3 \
  /opt/homebrew/bin/python3 \
  python3
do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
    if es_python_ok "$c"; then
      PYTHON="$c"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Hace falta Python 3.11 o superior."
  echo "Descárguelo en https://www.python.org/downloads/macos/ e instálelo."
  echo "Luego vuelva a abrir Instalar."
  echo
  if command -v open >/dev/null 2>&1; then
    open "https://www.python.org/downloads/macos/" 2>/dev/null || true
  fi
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

echo "Python: $PYTHON ($("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
echo "Creando entorno en app/.venv …"
"$PYTHON" -m venv "$APP/.venv"
VENV_PY="$APP/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "No se pudo crear el entorno virtual."
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

echo "Instalando dependencias (puede tardar unos minutos)…"
"$VENV_PY" -m pip install -U pip
REQ="$APP/.requirements-mac.txt"
grep -vi pyinstaller "$APP/requirements.txt" > "$REQ"
"$VENV_PY" -m pip install -r "$REQ"
rm -f "$REQ"

chmod +x "$ROOT/Abrir.command" 2>/dev/null || true
LAUNCHER="$ROOT/Consolidado Humanidades.app/Contents/MacOS/ConsolidadoHumanidades"
if [ -f "$LAUNCHER" ]; then
  chmod +x "$LAUNCHER"
fi

echo
echo "Instalación lista."
echo "Abra «Consolidado Humanidades» o Abrir.command para entrar."
echo "Usuario inicial: admin / admin"
echo
read -r -p "Pulse Intro para abrir la aplicación…"
if [ -d "$ROOT/Consolidado Humanidades.app" ]; then
  open "$ROOT/Consolidado Humanidades.app"
else
  /bin/bash "$ROOT/Abrir.command"
fi
