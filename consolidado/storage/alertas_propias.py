"""Alertas propias (global por identificación). Se mezclan al generar y en la ficha."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db


def cargar_alertas_propias(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, nombre, detalle
            FROM alertas_propias
            ORDER BY nombre COLLATE NOCASE, identificacion
            """
        ).fetchall()
    return [
        {
            "identificacion": r["identificacion"],
            "nombre": r["nombre"] or "",
            "detalle": r["detalle"] or "",
        }
        for r in rows
    ]


def guardar_alertas_propias(
    items: list[dict[str, Any]],
    base: Path | None = None,
) -> Path:
    """Reemplaza el conjunto completo de alertas propias."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        conn.execute("DELETE FROM alertas_propias")
        for item in items:
            ident = str(item.get("identificacion", "")).strip()
            detalle = str(item.get("detalle") or "").strip()
            if not ident or not detalle:
                continue
            conn.execute(
                """
                INSERT INTO alertas_propias (
                    identificacion, nombre, detalle, creado_en, actualizado_en
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    str(item.get("nombre") or "") or None,
                    detalle,
                    ahora,
                    ahora,
                ),
            )
    from consolidado.storage.db import ruta_base_datos

    return ruta_base_datos(base)


def agregar_alerta_propia(
    entrada: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Añade o actualiza una alerta propia por identificación."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = str(entrada.get("identificacion", "")).strip()
    detalle = str(entrada.get("detalle") or "").strip()
    if not ident or not detalle:
        return cargar_alertas_propias(base)
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        existente = conn.execute(
            "SELECT creado_en FROM alertas_propias WHERE identificacion = ?",
            (ident,),
        ).fetchone()
        creado = existente["creado_en"] if existente else ahora
        conn.execute(
            """
            INSERT INTO alertas_propias (
                identificacion, nombre, detalle, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(identificacion) DO UPDATE SET
                nombre = excluded.nombre,
                detalle = excluded.detalle,
                actualizado_en = excluded.actualizado_en
            """,
            (
                ident,
                str(entrada.get("nombre") or "") or None,
                detalle,
                creado,
                ahora,
            ),
        )
    return cargar_alertas_propias(base)


def quitar_alerta_propia(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    id_key = identificacion.strip()
    with conexion(base) as conn:
        conn.execute(
            "DELETE FROM alertas_propias WHERE identificacion = ?",
            (id_key,),
        )
    return cargar_alertas_propias(base)
