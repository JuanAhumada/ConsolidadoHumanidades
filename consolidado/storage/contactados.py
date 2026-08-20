"""
Check de Seguimiento (contactado) y bitácora de atenciones.

El check es global por identificación: marcar en una pestaña vale para todas.
Cada marca se guarda con fecha y pestaña para las estadísticas.
No depende de la versión SQL.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
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
    categoria: str = "general",
    base: Path | None = None,
) -> None:
    base = base or PROJECT_ROOT
    inicializar_db(base)
    ident = identificacion.strip()
    if not ident:
        return
    ahora = datetime.now()
    iso = ahora.isoformat(timespec="seconds")
    dia = ahora.date().isoformat()
    cat = (categoria or "general").strip().lower() or "general"
    with conexion(base) as conn:
        if contactado:
            existente = conn.execute(
                "SELECT contactado_en FROM priorizados_contactados WHERE identificacion = ?",
                (ident,),
            ).fetchone()
            creado = existente["contactado_en"] if existente else iso
            conn.execute(
                """
                INSERT INTO priorizados_contactados (
                    identificacion, contactado, contactado_en, actualizado_en
                ) VALUES (?, 1, ?, ?)
                ON CONFLICT(identificacion) DO UPDATE SET
                    contactado = 1,
                    actualizado_en = excluded.actualizado_en
                """,
                (ident, creado, iso),
            )
            conn.execute(
                """
                INSERT INTO seguimiento_atenciones (
                    identificacion, categoria, fecha, creado_en
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(identificacion, categoria, fecha) DO NOTHING
                """,
                (ident, cat, dia, iso),
            )
        else:
            conn.execute(
                "DELETE FROM priorizados_contactados WHERE identificacion = ?",
                (ident,),
            )
            conn.execute(
                """
                DELETE FROM seguimiento_atenciones
                WHERE identificacion = ? AND categoria = ? AND fecha = ?
                """,
                (ident, cat, dia),
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


def estadisticas_atenciones(
    *,
    dias: int = 30,
    base: Path | None = None,
) -> dict[str, Any]:
    """Conteos diarios y por pestaña de las atenciones marcadas."""
    from consolidado.core.seguimiento import CATEGORIAS_SEGUIMIENTO

    base = base or PROJECT_ROOT
    inicializar_db(base)
    titulos = {c["id"]: c["titulo"] for c in CATEGORIAS_SEGUIMIENTO}
    with conexion(base) as conn:
        filas = conn.execute(
            """
            SELECT identificacion, categoria, fecha, creado_en
            FROM seguimiento_atenciones
            ORDER BY fecha DESC, creado_en DESC
            """
        ).fetchall()

    eventos = [dict(r) for r in filas]
    hoy = date.today()
    hoy_txt = hoy.isoformat()
    ventana = max(7, min(int(dias or 30), 180))
    inicio = hoy - timedelta(days=ventana - 1)

    por_dia: dict[str, int] = defaultdict(int)
    por_cat: dict[str, int] = defaultdict(int)
    por_dia_cat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ev in eventos:
        fecha = str(ev.get("fecha") or "")[:10]
        cat = str(ev.get("categoria") or "general")
        if not fecha:
            continue
        por_dia[fecha] += 1
        por_cat[cat] += 1
        por_dia_cat[fecha][cat] += 1

    series = []
    for i in range(ventana):
        d = (inicio + timedelta(days=i)).isoformat()
        series.append({"fecha": d, "n": int(por_dia.get(d, 0))})

    dias_con = [n for n in por_dia.values() if n > 0]
    total = sum(por_dia.values())
    promedio = round(total / len(dias_con), 2) if dias_con else 0.0
    ultima_semana = series[-7:] if len(series) >= 7 else series
    promedio_semana = (
        round(sum(d["n"] for d in ultima_semana) / len(ultima_semana), 2)
        if ultima_semana
        else 0.0
    )

    categorias = []
    for cat in CATEGORIAS_SEGUIMIENTO:
        n = int(por_cat.get(cat["id"], 0))
        categorias.append({"id": cat["id"], "titulo": cat["titulo"], "n": n})
    extra_ids = [k for k in por_cat if k not in titulos]
    for cid in extra_ids:
        categorias.append({"id": cid, "titulo": cid.title(), "n": int(por_cat[cid])})

    recientes = []
    for ev in eventos[:40]:
        cid = str(ev.get("categoria") or "general")
        recientes.append(
            {
                "identificacion": ev.get("identificacion"),
                "categoria": cid,
                "titulo": titulos.get(cid, cid.title()),
                "fecha": str(ev.get("fecha") or "")[:10],
                "creado_en": ev.get("creado_en"),
            }
        )

    return {
        "hoy": int(por_dia.get(hoy_txt, 0)),
        "total": total,
        "dias_con_atencion": len(dias_con),
        "promedio": promedio,
        "promedio_semana": promedio_semana,
        "ventana": ventana,
        "series": series,
        "categorias": categorias,
        "recientes": recientes,
    }
