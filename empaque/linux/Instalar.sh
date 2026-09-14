#!/bin/bash
# Primera instalación o reparación del entorno local (Linux).
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
APP="$ROOT/app"

echo "=============================================="
echo " Consolidado de Humanidades — instalación Linux"
echo "=============================================="
echo

if [ ! -d "$APP" ] || [ ! -f "$APP/main.py" ]; then
  echo "No se encontró la carpeta app junto a este instalador."
  echo "Deje Instalar.sh, Abrir.sh y la carpeta app en el mismo sitio."
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
  /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 \
  /usr/local/bin/python3 \
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
  echo "Hace falta Python 3.11 o superior (con venv)."
  echo "Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip python3-tk"
  echo "Fedora: sudo dnf install python3 python3-tkinter"
  echo
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

echo "Python: $PYTHON ($("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
echo "Creando entorno en app/.venv …"
"$PYTHON" -m venv "$APP/.venv"
VENV_PY="$APP/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "No se pudo crear el entorno virtual. Instale python3-venv e inténtelo de nuevo."
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

echo "Instalando dependencias (puede tardar unos minutos)…"
"$VENV_PY" -m pip install -U pip
REQ="$APP/.requirements-linux.txt"
grep -vi pyinstaller "$APP/requirements.txt" > "$REQ"
"$VENV_PY" -m pip install -r "$REQ"
rm -f "$REQ"

chmod +x "$ROOT/Abrir.sh" 2>/dev/null || true
chmod +x "$ROOT/Instalar.sh" 2>/dev/null || true

echo
echo "Instalación lista."
echo "Ejecute ./Abrir.sh para entrar."
echo "Usuario inicial: admin / admin"
echo
read -r -p "Pulse Intro para abrir la aplicación…"
exec /bin/bash "$ROOT/Abrir.sh"
