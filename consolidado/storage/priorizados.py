"""Persistencia de priorizados propios (SQLite)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db


def cargar_priorizados_propios(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, nombre, motivo, detalle
            FROM priorizados_propios
            ORDER BY nombre COLLATE NOCASE, identificacion
            """
        ).fetchall()
    return [
        {
            "identificacion": r["identificacion"],
            "nombre": r["nombre"] or "",
            "motivo": r["motivo"] or "",
            "detalle": r["detalle"] or "",
        }
        for r in rows
    ]


def guardar_priorizados_propios(
    items: list[dict[str, Any]],
    base: Path | None = None,
) -> Path:
    """Reemplaza el conjunto completo de priorizados propios."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        conn.execute("DELETE FROM priorizados_propios")
        for item in items:
            ident = str(item.get("identificacion", "")).strip()
            if not ident:
                continue
            conn.execute(
                """
                INSERT INTO priorizados_propios (
                    identificacion, nombre, motivo, detalle,
                    creado_en, actualizado_en
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    str(item.get("nombre") or "") or None,
                    str(item.get("motivo") or "") or None,
                    str(item.get("detalle") or "") or None,
                    ahora,
                    ahora,
                ),
            )
    from consolidado.storage.db import ruta_base_datos

    return ruta_base_datos(base)


def agregar_priorizado_propio(
    entrada: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Añade o actualiza un priorizado propio por identificación."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = str(entrada.get("identificacion", "")).strip()
    if not ident:
        return cargar_priorizados_propios(base)
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        existente = conn.execute(
            "SELECT creado_en FROM priorizados_propios WHERE identificacion = ?",
            (ident,),
        ).fetchone()
        creado = existente["creado_en"] if existente else ahora
        conn.execute(
            """
            INSERT INTO priorizados_propios (
                identificacion, nombre, motivo, detalle, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(identificacion) DO UPDATE SET
                nombre = excluded.nombre,
                motivo = excluded.motivo,
                detalle = excluded.detalle,
                actualizado_en = excluded.actualizado_en
            """,
            (
                ident,
                str(entrada.get("nombre") or "") or None,
                str(entrada.get("motivo") or "") or None,
                str(entrada.get("detalle") or "") or None,
                creado,
                ahora,
            ),
        )
    return cargar_priorizados_propios(base)


def quitar_priorizado_propio(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    id_key = identificacion.strip()
    with conexion(base) as conn:
        conn.execute(
            "DELETE FROM priorizados_propios WHERE identificacion = ?",
            (id_key,),
        )
    return cargar_priorizados_propios(base)
