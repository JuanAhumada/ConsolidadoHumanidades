"""
Priorizados propios (marca interna, global por identificación).

No es el puntaje de BD grupos priorizados; ese viene de bd2 en el pipeline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db, ruta_base_datos


def cargar_priorizados_propios(
    base: Path | None = None,
    *,
    solo_activos: bool = True,
) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        if solo_activos:
            rows = conn.execute(
                """
                SELECT identificacion, nombre, motivo, detalle, activo
                FROM priorizados_propios
                WHERE activo = 1
                ORDER BY nombre COLLATE NOCASE, identificacion
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT identificacion, nombre, motivo, detalle, activo
                FROM priorizados_propios
                ORDER BY activo DESC, nombre COLLATE NOCASE, identificacion
                """
            ).fetchall()
    return [
        {
            "identificacion": r["identificacion"],
            "nombre": r["nombre"] or "",
            "motivo": r["motivo"] or "",
            "detalle": r["detalle"] or "",
            "activo": bool(r["activo"]) if r["activo"] is not None else True,
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
            activo = 0 if item.get("activo") is False else 1
            conn.execute(
                """
                INSERT INTO priorizados_propios (
                    identificacion, nombre, motivo, detalle, activo,
                    creado_en, actualizado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    str(item.get("nombre") or "") or None,
                    str(item.get("motivo") or "") or None,
                    str(item.get("detalle") or "") or None,
                    activo,
                    ahora,
                    ahora,
                ),
            )
    return ruta_base_datos(base)


def agregar_priorizado_propio(
    entrada: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Añade o actualiza un priorizado propio por identificación (queda activo)."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = str(entrada.get("identificacion", "")).strip()
    if not ident:
        return cargar_priorizados_propios(base, solo_activos=False)
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
                identificacion, nombre, motivo, detalle, activo,
                creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(identificacion) DO UPDATE SET
                nombre = excluded.nombre,
                motivo = excluded.motivo,
                detalle = excluded.detalle,
                activo = 1,
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
    return cargar_priorizados_propios(base, solo_activos=False)


def set_priorizado_activo(
    identificacion: str,
    *,
    activo: bool,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Activa o desactiva un priorizado propio sin borrarlo."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    id_key = identificacion.strip()
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        conn.execute(
            """
            UPDATE priorizados_propios
            SET activo = ?, actualizado_en = ?
            WHERE identificacion = ?
            """,
            (1 if activo else 0, ahora, id_key),
        )
    return cargar_priorizados_propios(base, solo_activos=False)


def quitar_priorizado_propio(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    """Desactiva el priorizado propio (compatibilidad: ya no lo borra)."""
    return set_priorizado_activo(identificacion, activo=False, base=base)


def eliminar_priorizado_propio(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    """Borra definitivamente un priorizado propio de la base."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    id_key = identificacion.strip()
    with conexion(base) as conn:
        conn.execute(
            "DELETE FROM priorizados_propios WHERE identificacion = ?",
            (id_key,),
        )
    return cargar_priorizados_propios(base, solo_activos=False)
