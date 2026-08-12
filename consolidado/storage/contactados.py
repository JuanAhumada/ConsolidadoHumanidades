"""Persistencia de estado «contactado» en priorizados."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db


def cargar_ids_contactados(base: Path | None = None) -> set[str]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion
            FROM priorizados_contactados
            WHERE contactado = 1
            """
        ).fetchall()
    return {str(r["identificacion"]).strip() for r in rows if r["identificacion"]}


def es_contactado(identificacion: str, base: Path | None = None) -> bool:
    return identificacion.strip() in cargar_ids_contactados(base)


def marcar_contactado(
    identificacion: str,
    *,
    contactado: bool = True,
    base: Path | None = None,
) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = identificacion.strip()
    if not ident:
        return
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        if contactado:
            existente = conn.execute(
                "SELECT contactado_en FROM priorizados_contactados WHERE identificacion = ?",
                (ident,),
            ).fetchone()
            creado = existente["contactado_en"] if existente else ahora
            conn.execute(
                """
                INSERT INTO priorizados_contactados (
                    identificacion, contactado, contactado_en, actualizado_en
                ) VALUES (?, 1, ?, ?)
                ON CONFLICT(identificacion) DO UPDATE SET
                    contactado = 1,
                    actualizado_en = excluded.actualizado_en
                """,
                (ident, creado, ahora),
            )
        else:
            conn.execute(
                "DELETE FROM priorizados_contactados WHERE identificacion = ?",
                (ident,),
            )


def listar_contactados(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, contactado, contactado_en, actualizado_en
            FROM priorizados_contactados
            WHERE contactado = 1
            ORDER BY actualizado_en DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]
