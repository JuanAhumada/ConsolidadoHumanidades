"""Estudiantes creados a mano por el administrador (sobreviven al generar)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from consolidado.core.columnas import alinear_dataframe_salida
from consolidado.core.constants import COL_ACTIVOS
from consolidado.core.normalizacion import clave_cruce_identificacion, normalizar_id
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import (
    _insertar_estudiante_categorias,
    conexion,
    inicializar_db,
    obtener_fila_estudiante,
    obtener_version,
    ultima_version,
)
from consolidado.storage.modificaciones import _usuario_log


def listar_estudiantes_manuales(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, nombre, programa, periodo_ingreso, telefono,
                   correo_institucional, correo_personal, fila_json, creado_en, usuario
            FROM estudiantes_manuales
            ORDER BY nombre COLLATE NOCASE, identificacion
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _texto_o_vacio(val: Any) -> str | None:
    if val is None:
        return None
    texto = str(val).strip()
    return texto or None


def crear_estudiante_manual(
    *,
    valores: dict[str, Any],
    usuario: str | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Guarda un estudiante nuevo y lo mete en la última versión, si existe."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    valores = {str(k).strip(): v for k, v in (valores or {}).items() if str(k).strip()}
    identificacion = valores.get("Identificación") or ""
    ident = clave_cruce_identificacion(identificacion) or normalizar_id(identificacion)
    ident_norm = normalizar_id(identificacion)
    nombre = (valores.get("Nombre y apellidos") or "").strip()
    if not ident:
        raise ValueError("Indique la identificación.")
    if not nombre:
        raise ValueError("Indique el nombre y apellidos.")
    if obtener_fila_estudiante(ident, base=base) or (
        ident_norm and ident_norm != ident and obtener_fila_estudiante(ident_norm, base=base)
    ):
        raise ValueError(f"Ya existe un estudiante con identificación {ident}.")

    ult = ultima_version(base)
    meta = obtener_version(int(ult["id"]), base) if ult else None
    columnas = list((meta or {}).get("columnas") or [])
    orden = list(columnas)
    for col in valores:
        if col not in orden:
            orden.append(col)
    if "Identificación" not in orden:
        orden.insert(0, "Identificación")
    fila: dict[str, Any] = {col: _texto_o_vacio(valores.get(col)) for col in orden}
    fila["Identificación"] = ident
    fila["Nombre y apellidos"] = nombre
    if not fila.get(COL_ACTIVOS):
        fila[COL_ACTIVOS] = "Sí"
    ahora = datetime.now().isoformat(timespec="seconds")
    quien = (usuario or "").strip() or _usuario_log.get()
    with conexion(base) as conn:
        existe = conn.execute(
            "SELECT 1 FROM estudiantes_manuales WHERE identificacion = ?",
            (ident,),
        ).fetchone()
        if existe:
            raise ValueError(f"Ya se había creado el estudiante {ident}.")
        conn.execute(
            """
            INSERT INTO estudiantes_manuales (
                identificacion, nombre, programa, periodo_ingreso, telefono,
                correo_institucional, correo_personal, fila_json, creado_en, usuario
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ident,
                nombre,
                fila.get("Programa"),
                fila.get("Periodo ingreso"),
                fila.get("Teléfono celular"),
                fila.get("Correo institucional"),
                fila.get("Correo personal"),
                json.dumps(fila, ensure_ascii=False),
                ahora,
                quien,
            ),
        )
        if ult is not None:
            vid = int(ult["id"])
            _insertar_estudiante_categorias(conn, vid, fila)
            conn.execute(
                """
                UPDATE versiones
                SET num_estudiantes = (
                    SELECT COUNT(*) FROM estudiantes_base WHERE version_id = ?
                )
                WHERE id = ?
                """,
                (vid, vid),
            )
    return {"identificacion": ident, "nombre": nombre, "en_version": ult is not None}


def aplicar_estudiantes_manuales(df: pl.DataFrame, base: Path | None = None) -> pl.DataFrame:
    """Añade al consolidado a quienes se crearon a mano y no vinieron en los Excel."""
    registros = listar_estudiantes_manuales(base)
    if not registros:
        return df
    presentes: set[str] = set()
    if df.height and "Identificación" in df.columns:
        for v in df["Identificación"].to_list():
            cruce = clave_cruce_identificacion(v)
            norm = normalizar_id(v)
            if cruce:
                presentes.add(cruce)
            if norm:
                presentes.add(norm)
    nuevos: list[dict[str, Any]] = []
    for rec in registros:
        ident = clave_cruce_identificacion(rec.get("identificacion")) or str(
            rec.get("identificacion") or ""
        )
        if not ident or ident in presentes:
            continue
        try:
            fila = json.loads(rec.get("fila_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            fila = {}
        if not isinstance(fila, dict):
            fila = {}
        fila["Identificación"] = ident
        if rec.get("nombre"):
            fila.setdefault("Nombre y apellidos", rec["nombre"])
        fila.setdefault(COL_ACTIVOS, "Sí")
        nuevos.append(fila)
        presentes.add(ident)
    if not nuevos:
        return df
    columnas = list(df.columns) if df.columns else sorted({k for f in nuevos for k in f})
    extra = alinear_dataframe_salida(pl.from_dicts(nuevos, infer_schema_length=None), columnas)
    if df.height == 0:
        return extra
    return pl.concat([df, extra], how="diagonal_relaxed")
