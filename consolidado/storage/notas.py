"""Notas de seguimiento / observaciones de lo que dijo el estudiante."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.core.normalizacion import normalizar_id
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db
from consolidado.storage.modificaciones import _usuario_log


def listar_notas(identificacion: str, base: Path | None = None) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    if not ident:
        return []
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT id, identificacion, nota, creado_en, usuario
            FROM seguimiento_notas
            WHERE identificacion = ?
            ORDER BY creado_en DESC, id DESC
            """,
            (ident,),
        ).fetchall()
    return [dict(r) for r in rows]


def agregar_nota(
    identificacion: str,
    nota: str,
    *,
    usuario: str | None = None,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    texto = (nota or "").strip()
    if not ident or not texto:
        return listar_notas(identificacion, base=base)
    ahora = datetime.now().isoformat(timespec="seconds")
    quien = usuario if usuario is not None else _usuario_log.get()
    with conexion(base) as conn:
        conn.execute(
            """
            INSERT INTO seguimiento_notas (identificacion, nota, creado_en, usuario)
            VALUES (?, ?, ?, ?)
            """,
            (ident, texto, ahora, quien),
        )
    return listar_notas(ident, base=base)


def quitar_nota(nota_id: int, base: Path | None = None) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        conn.execute("DELETE FROM seguimiento_notas WHERE id = ?", (int(nota_id),))


def resumen_notas(base: Path | None = None) -> dict[str, dict[str, Any]]:
    """identificacion → {n, ultima, ultima_en, usuario}."""
    base = base or PROJECT_ROOT
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT identificacion, nota, creado_en, usuario
            FROM seguimiento_notas
            ORDER BY creado_en DESC, id DESC
            """
        ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        ident = normalizar_id(r["identificacion"])
        if not ident:
            continue
        if ident not in out:
            out[ident] = {
                "n": 0,
                "ultima": r["nota"] or "",
                "ultima_en": r["creado_en"],
                "usuario": r["usuario"] or "",
            }
        out[ident]["n"] = int(out[ident]["n"]) + 1
    return out
