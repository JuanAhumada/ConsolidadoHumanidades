#!/bin/bash
# Arranque diario después de Instalar.command.
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
APP="$ROOT/app"
VENV_PY="$APP/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "Todavía no está instalado. Abra primero Instalar.command."
  echo
  read -r -p "Pulse Intro para cerrar…"
  exit 1
fi

export CONSOLIDADO_LOCAL=1
export PYTHONUNBUFFERED=1
cd "$APP" || exit 1
exec "$VENV_PY" main.py
