"""Ediciones de ficha: ruta de grado y priorizado, por estudiante."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.config.settings import (
    COLUMNAS_PRIORIZADO,
    COLUMNAS_PRIORIZADO_ENRIQUECIDO,
    COLUMNAS_RUTA_GRADO,
)
from consolidado.core.normalizacion import normalizar_id
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db
from consolidado.storage.modificaciones import _usuario_log

COLUMNAS_EDITABLES = frozenset(
    COLUMNAS_PRIORIZADO + COLUMNAS_PRIORIZADO_ENRIQUECIDO + COLUMNAS_RUTA_GRADO
)
GRUPOS_EDITABLES = {
    "priorizado": tuple(COLUMNAS_PRIORIZADO + COLUMNAS_PRIORIZADO_ENRIQUECIDO),
    "ruta": tuple(COLUMNAS_RUTA_GRADO),
}


def clave_campo_edicion(col: str) -> str:
    """Nombre de input HTML seguro (sin %, espacios ni puntos)."""
    return "ed_" + str(col or "").encode("utf-8").hex()


def cargar_ediciones(base: Path | None = None) -> dict[str, dict[str, Any]]:
    """identificacion → {columna: valor}."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, columna, valor
            FROM estudiante_ediciones
            """
        ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        ident = normalizar_id(r["identificacion"])
        col = str(r["columna"] or "").strip()
        if not ident or col not in COLUMNAS_EDITABLES:
            continue
        out.setdefault(ident, {})[col] = r["valor"]
    return out


def overlay_ediciones_fila(
    fila: dict[str, Any],
    ediciones: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ident = normalizar_id(fila.get("Identificación") or fila.get("identificacion"))
    extra = ediciones.get(ident)
    if not extra:
        return fila
    actualizado = dict(fila)
    actualizado.update(extra)
    return actualizado


def aplicar_ediciones_columnas(
    idents: list[str],
    valores_por_columna: dict[str, list[Any]],
    ediciones: dict[str, dict[str, Any]],
) -> dict[str, list[Any]]:
    """Sustituye valores de columnas editables cuando hay overlay para ese id."""
    if not ediciones or not idents:
        return {}
    cambios: dict[str, list[Any]] = {}
    for col, originales in valores_por_columna.items():
        if col not in COLUMNAS_EDITABLES:
            continue
        nuevos = list(originales)
        hubo = False
        for i, ident in enumerate(idents):
            extra = ediciones.get(ident)
            if extra and col in extra:
                nuevos[i] = extra[col]
                hubo = True
        if hubo:
            cambios[col] = nuevos
    return cambios


def guardar_ediciones(
    identificacion: str,
    campos: dict[str, Any],
    *,
    usuario: str | None = None,
    base: Path | None = None,
) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    if not ident:
        return
    ahora = datetime.now().isoformat(timespec="seconds")
    quien = usuario if usuario is not None else _usuario_log.get()
    with conexion(base) as conn:
        for col, val in campos.items():
            columna = str(col or "").strip()
            if columna not in COLUMNAS_EDITABLES:
                continue
            texto = "" if val is None else str(val).strip()
            conn.execute(
                """
                INSERT INTO estudiante_ediciones (
                    identificacion, columna, valor, actualizado_en, usuario
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(identificacion, columna) DO UPDATE SET
                    valor = excluded.valor,
                    actualizado_en = excluded.actualizado_en,
                    usuario = excluded.usuario
                """,
                (ident, columna, texto, ahora, quien),
            )


def borrar_ediciones_grupo(
    identificacion: str,
    grupo: str,
    *,
    base: Path | None = None,
) -> None:
    ident = normalizar_id(identificacion)
    columnas = GRUPOS_EDITABLES.get((grupo or "").strip().lower())
    if not ident or not columnas:
        return
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        conn.executemany(
            "DELETE FROM estudiante_ediciones WHERE identificacion = ? AND columna = ?",
            [(ident, col) for col in columnas],
        )
