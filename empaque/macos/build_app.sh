#!/bin/bash
# Compila un .app nativo con PyInstaller. Hay que ejecutarlo EN un Mac.
# Desde Windows use armar_paquete.py (instalador local con Python).
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Este script solo corre en macOS."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/pyinstaller --noconfirm --clean ConsolidadoHumanidades.spec
echo "Salida: dist/ConsolidadoHumanidades"
echo "En Mac el usuario habitual debe usar el ZIP de armar_paquete.py, no este binario."
