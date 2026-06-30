"""Persistencia de priorizados propios (JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT

PRIORIZADOS_PROPIOS_FILENAME = "priorizados_propios.json"
CARPETA_DATOS = "datos"


def ruta_priorizados_propios(base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    return base / CARPETA_DATOS / PRIORIZADOS_PROPIOS_FILENAME


def cargar_priorizados_propios(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    path = ruta_priorizados_propios(base)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return list(data.get("priorizados_propios", []))


def guardar_priorizados_propios(
    items: list[dict[str, Any]],
    base: Path | None = None,
) -> Path:
    base = base or PROJECT_ROOT
    path = ruta_priorizados_propios(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"priorizados_propios": items}, f, ensure_ascii=False, indent=2)
    return path


def agregar_priorizado_propio(
    entrada: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Añade o actualiza un priorizado propio por identificación."""
    base = base or PROJECT_ROOT
    items = cargar_priorizados_propios(base)
    id_nuevo = str(entrada.get("identificacion", "")).strip()
    filtrados = [i for i in items if str(i.get("identificacion", "")).strip() != id_nuevo]
    filtrados.append(entrada)
    guardar_priorizados_propios(filtrados, base)
    return filtrados


def quitar_priorizado_propio(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    id_key = identificacion.strip()
    items = [
        i for i in cargar_priorizados_propios(base)
        if str(i.get("identificacion", "")).strip() != id_key
    ]
    guardar_priorizados_propios(items, base)
    return items
