"""Marca global: si el estudiante se gradúa este semestre (Sí / No)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.core.normalizacion import normalizar_id
from consolidado.core.prioridad import _periodo_calendario
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db
from consolidado.storage.modificaciones import _usuario_log


def cargar_marcas_gradua(
    *,
    periodo: str | None = None,
    base: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """identificacion → {se_gradua, periodo, actualizado_en, usuario} del periodo dado."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    corte = (periodo or _periodo_calendario()).strip()
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, se_gradua, periodo, actualizado_en, usuario
            FROM estudiante_gradua_semestre
            WHERE periodo = ? OR periodo IS NULL OR periodo = ''
            """,
            (corte,),
        ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        ident = normalizar_id(r["identificacion"])
        if not ident:
            continue
        marca_periodo = str(r["periodo"] or "").strip()
        if marca_periodo and marca_periodo != corte:
            continue
        out[ident] = {
            "se_gradua": bool(r["se_gradua"]),
            "periodo": marca_periodo or corte,
            "actualizado_en": r["actualizado_en"],
            "usuario": r["usuario"] or "",
        }
    return out


def obtener_marca_gradua(
    identificacion: str,
    *,
    periodo: str | None = None,
    base: Path | None = None,
) -> dict[str, Any] | None:
    ident = normalizar_id(identificacion)
    if not ident:
        return None
    return cargar_marcas_gradua(periodo=periodo, base=base).get(ident)


def marcar_gradua(
    identificacion: str,
    *,
    se_gradua: bool,
    periodo: str | None = None,
    usuario: str | None = None,
    base: Path | None = None,
) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    if not ident:
        return
    corte = (periodo or _periodo_calendario()).strip()
    ahora = datetime.now().isoformat(timespec="seconds")
    quien = usuario if usuario is not None else _usuario_log.get()
    with conexion(base) as conn:
        conn.execute(
            """
            INSERT INTO estudiante_gradua_semestre (
                identificacion, se_gradua, periodo, actualizado_en, usuario
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(identificacion) DO UPDATE SET
                se_gradua = excluded.se_gradua,
                periodo = excluded.periodo,
                actualizado_en = excluded.actualizado_en,
                usuario = excluded.usuario
            """,
            (ident, 1 if se_gradua else 0, corte, ahora, quien),
        )
