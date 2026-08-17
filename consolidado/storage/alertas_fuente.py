"""Alertas provenientes de las bases fuente y descartes persistentes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.core.constants import (
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
)
from consolidado.core.normalizacion import normalizar_id
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db, ultima_version

FASES_ALERTA = ("inicial", "final")


def partir_tipos_alerta(texto: Any) -> list[str]:
    if texto is None:
        return []
    return [p.strip() for p in str(texto).replace("||", "|").split("|") if p.strip()]


def unir_tipos_alerta(tipos: list[str]) -> str | None:
    limpios = [t.strip() for t in tipos if t and t.strip()]
    return " | ".join(limpios) or None


def _col_tipo(fase: str) -> str:
    return COL_TIPO_ALERTA_FINAL if fase == "final" else COL_TIPO_ALERTA_INICIAL


def _col_num(fase: str) -> str:
    return COL_NUM_ALERTA_FINAL if fase == "final" else COL_NUM_ALERTA_INICIAL


def _col_sql_tipo(fase: str) -> str:
    return "tipo_alerta_final" if fase == "final" else "tipo_alerta_inicial"


def _col_sql_num(fase: str) -> str:
    return "num_alerta_final" if fase == "final" else "num_alerta_inicial"


def cargar_alertas_descartadas(base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, fase, tipo, creado_en
            FROM alertas_descartadas
            ORDER BY identificacion, fase, tipo
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _set_descartadas(base: Path | None = None) -> set[tuple[str, str, str]]:
    return {
        (
            normalizar_id(d["identificacion"]),
            str(d["fase"]),
            str(d["tipo"]).strip().casefold(),
        )
        for d in cargar_alertas_descartadas(base)
        if normalizar_id(d["identificacion"]) and str(d.get("tipo") or "").strip()
    }


def _filtrar_tipos(texto: Any, ident: str, fase: str, descartadas: set[tuple[str, str, str]]) -> list[str]:
    ident = normalizar_id(ident)
    quedan: list[str] = []
    for tipo in partir_tipos_alerta(texto):
        clave = (ident, fase, tipo.casefold())
        if clave not in descartadas:
            quedan.append(tipo)
    return quedan


def aplicar_descartes_a_fila(
    fila: dict[str, Any],
    identificacion: str,
    base: Path | None = None,
) -> dict[str, Any]:
    """Quita de una fila (ficha) los tipos de alerta descartados."""
    out = dict(fila)
    ident = normalizar_id(identificacion)
    descartadas = _set_descartadas(base)
    for fase in FASES_ALERTA:
        col_t, col_n = _col_tipo(fase), _col_num(fase)
        quedan = _filtrar_tipos(out.get(col_t), ident, fase, descartadas)
        out[col_t] = unir_tipos_alerta(quedan)
        out[col_n] = len(quedan) if quedan else None
    return out


def aplicar_alertas_descartadas(consolidado, base: Path | None = None):
    """Filtra tipos descartados sobre el dataframe del consolidado."""
    import polars as pl

    if consolidado.height == 0:
        return consolidado
    descartadas = _set_descartadas(base)
    if not descartadas:
        return consolidado
    ids = consolidado.get_column("Identificación").to_list() if "Identificación" in consolidado.columns else []
    exprs = []
    for fase in FASES_ALERTA:
        col_t, col_n = _col_tipo(fase), _col_num(fase)
        if col_t not in consolidado.columns:
            continue
        tipos_orig = consolidado.get_column(col_t).to_list()
        nuevos_t: list[str | None] = []
        nuevos_n: list[int | None] = []
        for i, raw in enumerate(tipos_orig):
            ident = normalizar_id(ids[i] if i < len(ids) else "")
            quedan = _filtrar_tipos(raw, ident, fase, descartadas)
            nuevos_t.append(unir_tipos_alerta(quedan))
            nuevos_n.append(len(quedan) if quedan else None)
        exprs.append(pl.Series(col_t, nuevos_t, dtype=pl.Utf8))
        if col_n in consolidado.columns:
            exprs.append(pl.Series(col_n, nuevos_n, dtype=pl.Int64))
    if not exprs:
        return consolidado
    return consolidado.with_columns(exprs)


def listar_alertas_fuente(base: Path | None = None) -> list[dict[str, Any]]:
    """Estudiantes con alertas vigentes (última versión): un registro por persona."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ult = ultima_version(base)
    if ult is None:
        return []
    version_id = int(ult["id"])
    descartadas = _set_descartadas(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT a.identificacion, b.nombre, a.tipo_alerta_inicial, a.tipo_alerta_final
            FROM estudiantes_alertas a
            LEFT JOIN estudiantes_base b
              ON b.identificacion = a.identificacion AND b.version_id = a.version_id
            WHERE a.version_id = ?
            ORDER BY b.nombre COLLATE NOCASE, a.identificacion
            """,
            (version_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        ident = normalizar_id(row["identificacion"])
        if not ident:
            continue
        inicial = _filtrar_tipos(row["tipo_alerta_inicial"], ident, "inicial", descartadas)
        final = _filtrar_tipos(row["tipo_alerta_final"], ident, "final", descartadas)
        if not inicial and not final:
            continue
        out.append(
            {
                "identificacion": ident,
                "nombre": row["nombre"] or "",
                "inicial": inicial,
                "final": final,
                "num_inicial": len(inicial),
                "num_final": len(final),
                "num_alertas": len(inicial) + len(final),
            }
        )
    return out


def descartar_alerta_fuente(
    identificacion: str,
    fase: str,
    tipo: str,
    base: Path | None = None,
) -> None:
    """Marca un tipo de alerta como viejo/descartado y lo quita de la última versión SQL."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    fase = "final" if str(fase).strip().lower() == "final" else "inicial"
    tipo = str(tipo or "").strip()
    if not ident or not tipo:
        raise ValueError("Faltan identificación o tipo de alerta.")
    ahora = datetime.now().isoformat(timespec="seconds")
    ult = ultima_version(base)
    with conexion(base) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO alertas_descartadas (
                identificacion, fase, tipo, creado_en
            ) VALUES (?, ?, ?, ?)
            """,
            (ident, fase, tipo, ahora),
        )
        if ult is None:
            return
        version_id = int(ult["id"])
        row = conn.execute(
            """
            SELECT tipo_alerta_inicial, tipo_alerta_final,
                   num_alerta_inicial, num_alerta_final, fila_json
            FROM estudiantes_alertas
            WHERE identificacion = ? AND version_id = ?
            """,
            (ident, version_id),
        ).fetchone()
        if row is None:
            return
        col_t, col_n = _col_sql_tipo(fase), _col_sql_num(fase)
        canon_t, canon_n = _col_tipo(fase), _col_num(fase)
        quedan = [
            t for t in partir_tipos_alerta(row[col_t]) if t.casefold() != tipo.casefold()
        ]
        nuevo_t = unir_tipos_alerta(quedan)
        nuevo_n = len(quedan) if quedan else None
        try:
            fila = json.loads(row["fila_json"] or "{}")
        except json.JSONDecodeError:
            fila = {}
        if not isinstance(fila, dict):
            fila = {}
        fila[canon_t] = nuevo_t
        fila[canon_n] = nuevo_n
        conn.execute(
            f"""
            UPDATE estudiantes_alertas
            SET {col_t} = ?, {col_n} = ?, fila_json = ?
            WHERE identificacion = ? AND version_id = ?
            """,
            (nuevo_t, str(nuevo_n) if nuevo_n is not None else None, json.dumps(fila, ensure_ascii=False), ident, version_id),
        )
