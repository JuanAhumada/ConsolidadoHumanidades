"""Overrides de metas de graduación (no pisan el Excel de Permanencia)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db
from consolidado.storage.modificaciones import _usuario_log


def _clave(periodo: str, programa: str) -> tuple[str, str]:
    return (str(periodo or "").strip(), str(programa or "").strip())


def cargar_overrides(base: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT periodo, programa, meta_num, meta_pct, actualizado_en, usuario
            FROM metas_grado_override
            """
        ).fetchall()
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        out[_clave(r["periodo"], r["programa"])] = dict(r)
    return out


def guardar_overrides(
    periodo: str,
    filas: list[dict[str, Any]],
    *,
    usuario: str | None = None,
    base: Path | None = None,
) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    periodo = str(periodo or "").strip()
    if not periodo:
        raise ValueError("Indique el periodo de las metas.")
    ahora = datetime.now().isoformat(timespec="seconds")
    quien = usuario if usuario is not None else _usuario_log.get()
    with conexion(base) as conn:
        for fila in filas:
            programa = str(fila.get("programa") or "").strip()
            if not programa:
                continue
            meta_num = str(fila.get("meta_num") or "").strip() or None
            meta_pct = str(fila.get("meta_pct") or "").strip() or None
            conn.execute(
                """
                INSERT INTO metas_grado_override
                    (periodo, programa, meta_num, meta_pct, actualizado_en, usuario)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(periodo, programa) DO UPDATE SET
                    meta_num = excluded.meta_num,
                    meta_pct = excluded.meta_pct,
                    actualizado_en = excluded.actualizado_en,
                    usuario = excluded.usuario
                """,
                (periodo, programa, meta_num, meta_pct, ahora, quien),
            )


def _numero(texto: Any) -> float | None:
    if texto is None:
        return None
    s = str(texto).strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def aplicar_overrides_metas(metas: dict[str, Any], base: Path | None = None) -> dict[str, Any]:
    """Pisa Meta # y Meta % de graduación con los valores editados."""
    overrides = cargar_overrides(base)
    if not overrides or not metas:
        return metas
    for bloque in metas.get("graduacion") or []:
        periodo = str(bloque.get("periodo") or "").strip()
        for fila in bloque.get("filas") or []:
            ov = overrides.get(_clave(periodo, fila.get("programa") or ""))
            if not ov:
                continue
            if ov.get("meta_num"):
                fila["meta_num"] = ov["meta_num"]
            if ov.get("meta_pct"):
                fila["meta_pct"] = ov["meta_pct"]
            fila["editada"] = True
            meta_n = _numero(fila.get("meta_num"))
            alc_n = _numero(fila.get("alcanzado_num"))
            if meta_n is not None and alc_n is not None:
                falt = meta_n - alc_n
                fila["faltante_num"] = str(int(falt)) if falt == int(falt) else f"{falt:.1f}"
                fila["cumple"] = alc_n >= meta_n
                fila["estado"] = "CUMPLE" if fila["cumple"] else "NO CUMPLE"
            meta_p = _numero(fila.get("meta_pct"))
            alc_p = _numero(fila.get("alcanzado_pct"))
            if meta_p is not None and alc_p is not None:
                falt_p = meta_p - alc_p
                fila["faltante_pct"] = f"{falt_p:.1f}%".replace(".0%", "%")
    from consolidado.core.permanencia import asignar_graficas_metas

    return asignar_graficas_metas(metas)
