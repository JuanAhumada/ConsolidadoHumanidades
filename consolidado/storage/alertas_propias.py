"""Persistencia de alertas propias (JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT

ALERTAS_PROPIAS_FILENAME = "alertas_propias.json"
CARPETA_DATOS = "datos"


def ruta_alertas_propias(base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    return base / CARPETA_DATOS / ALERTAS_PROPIAS_FILENAME


def cargar_alertas_propias(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    path = ruta_alertas_propias(base)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return list(data.get("alertas_propias", []))


def guardar_alertas_propias(
    items: list[dict[str, Any]],
    base: Path | None = None,
) -> Path:
    base = base or PROJECT_ROOT
    path = ruta_alertas_propias(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"alertas_propias": items}, f, ensure_ascii=False, indent=2)
    return path


def agregar_alerta_propia(
    entrada: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Añade o actualiza una alerta propia por identificación."""
    base = base or PROJECT_ROOT
    items = cargar_alertas_propias(base)
    id_nuevo = str(entrada.get("identificacion", "")).strip()
    filtrados = [i for i in items if str(i.get("identificacion", "")).strip() != id_nuevo]
    filtrados.append(entrada)
    guardar_alertas_propias(filtrados, base)
    return filtrados


def quitar_alerta_propia(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    id_key = identificacion.strip()
    items = [
        i for i in cargar_alertas_propias(base)
        if str(i.get("identificacion", "")).strip() != id_key
    ]
    guardar_alertas_propias(items, base)
    return items
