"""
Periodo académico del estudiante desde BD1/BD12 (COD_PERIODO / COD_PENSUM).

sincronizar_periodo_actual_ultima_version solo toca la última versión
(al arrancar la web). No reescribe snapshots viejos.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from consolidado.config.settings import cargar_config, carpeta_excels
from consolidado.core.archivos import _preparar_archivo_interno
from consolidado.core.constants import COL_PERIODO_ACTUAL, aplicar_config
from consolidado.core.normalizacion import formatear_periodo_cod, normalizar_id, periodo_mas_reciente
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db, ultima_version


def _insertar_columna_periodo(columnas: list[str]) -> list[str]:
    if COL_PERIODO_ACTUAL in columnas:
        return columnas
    out = list(columnas)
    if "Periodo ingreso" in out:
        out.insert(out.index("Periodo ingreso") + 1, COL_PERIODO_ACTUAL)
    else:
        out.append(COL_PERIODO_ACTUAL)
    return out


def _acumular_periodos(mapa: dict[str, str], df) -> None:
    if df is None or df.height == 0:
        return
    if "Identificación" not in df.columns or COL_PERIODO_ACTUAL not in df.columns:
        return
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row.get("Identificación"))
        periodo = formatear_periodo_cod(row.get(COL_PERIODO_ACTUAL))
        if not id_key or not periodo:
            continue
        mapa[id_key] = periodo_mas_reciente([mapa.get(id_key), periodo]) or periodo


def mapa_periodos_desde_fuentes(
    cfg: dict[str, Any] | None = None,
    *,
    base: Path | None = None,
) -> dict[str, str]:
    """Identificación → YYYY-N a partir de los Excel actuales de BD1 y BD12."""
    base = base or PROJECT_ROOT
    cfg = aplicar_config(cfg or cargar_config(base), base)
    carpeta = carpeta_excels(cfg, base)
    mapa: dict[str, str] = {}
    for slot in cfg.get("archivos_fuente", []):
        if slot.get("tipo") not in ("bd1", "bd12"):
            continue
        ruta = carpeta / str(slot.get("nombre_guardado") or "")
        if not ruta.is_file():
            continue
        try:
            listado, horarios = _preparar_archivo_interno(
                ruta, tipo=slot.get("tipo"), hoja=slot.get("hoja")
            )
        except Exception:
            continue
        _acumular_periodos(mapa, listado)
        _acumular_periodos(mapa, horarios)
    return mapa


def sincronizar_periodo_actual_ultima_version(
    base: Path | None = None,
) -> dict[str, Any]:
    """
    Escribe Periodo actual en la última versión (fila_json + columna),
    sin tocar snapshots históricos.
    """
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ult = ultima_version(base)
    if ult is None:
        return {"actualizados": 0, "motivo": "sin_version"}
    mapa = mapa_periodos_desde_fuentes(base=base)
    if not mapa:
        return {"actualizados": 0, "motivo": "sin_fuentes", "version_id": ult["id"]}

    version_id = int(ult["id"])
    actualizados = 0
    with conexion(base) as conn:
        filas = conn.execute(
            """
            SELECT identificacion, fila_json
            FROM estudiantes_base
            WHERE version_id = ?
            """,
            (version_id,),
        ).fetchall()
        for row in filas:
            ident = normalizar_id(row["identificacion"])
            periodo = mapa.get(ident)
            if not periodo:
                continue
            try:
                fila = json.loads(row["fila_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                fila = {}
            if not isinstance(fila, dict):
                fila = {}
            if fila.get(COL_PERIODO_ACTUAL) == periodo:
                conn.execute(
                    """
                    UPDATE estudiantes_base
                    SET periodo_actual = ?
                    WHERE version_id = ? AND identificacion = ?
                    """,
                    (periodo, version_id, ident),
                )
                actualizados += 1
                continue
            fila[COL_PERIODO_ACTUAL] = periodo
            conn.execute(
                """
                UPDATE estudiantes_base
                SET periodo_actual = ?, fila_json = ?
                WHERE version_id = ? AND identificacion = ?
                """,
                (periodo, json.dumps(fila, ensure_ascii=False), version_id, ident),
            )
            actualizados += 1

        meta = conn.execute(
            "SELECT columnas_json FROM versiones WHERE id = ?",
            (version_id,),
        ).fetchone()
        if meta:
            try:
                columnas = json.loads(meta["columnas_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                columnas = []
            nuevas = _insertar_columna_periodo(list(columnas) if isinstance(columnas, list) else [])
            if nuevas != columnas:
                conn.execute(
                    "UPDATE versiones SET columnas_json = ? WHERE id = ?",
                    (json.dumps(nuevas, ensure_ascii=False), version_id),
                )
    return {
        "actualizados": actualizados,
        "version_id": version_id,
        "en_fuentes": len(mapa),
    }
