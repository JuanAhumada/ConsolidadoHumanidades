"""
Historial (antes Modificaciones): bitácora y diff entre dos versiones.

comparar_versiones alimenta la pantalla de Historial. registrar_modificacion
se llama desde las rutas web (marcar, generar, usuarios, etc.).
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.core.normalizacion import normalizar_id
from consolidado.storage.db import (
    cargar_dataframe_version,
    conexion,
    inicializar_db,
    obtener_version,
)

_usuario_log: ContextVar[str | None] = ContextVar("usuario_log", default=None)

ETIQUETAS_ACCION = {
    "generar": "Generar consolidado",
    "importar": "Importar Excel",
    "generar_historico": "Versión histórica",
    "cargar_archivo": "Cargar archivo",
    "descartar_alerta": "Descartar alerta",
    "alerta_propia": "Alerta propia",
    "quitar_alerta_propia": "Quitar alerta propia",
    "contactado": "Contactado",
    "priorizado_activo": "Estado priorizado",
    "priorizado_propio": "Priorizado propio",
    "config": "Configuración",
    "usuario": "Usuarios",
}

_COLS_DIFF = (
    "Nombre y apellidos",
    "Programa",
    "Nivel prioridad",
    "Puntaje prioridad",
    "Priorizado",
    "Tipo Alerta inicial",
    "Tipo Alerta final",
    "Alerta Propia",
)


def set_usuario_log(nombre: str | None):
    return _usuario_log.set(nombre)


def reset_usuario_log(token) -> None:
    _usuario_log.reset(token)


def registrar_modificacion(
    *,
    accion: str,
    resumen: str,
    entidad: str | None = None,
    identificacion: str | None = None,
    detalle: dict[str, Any] | None = None,
    version_antes: int | None = None,
    version_despues: int | None = None,
    usuario: str | None = None,
    base: Path | None = None,
) -> None:
    try:
        inicializar_db(base)
        quien = usuario if usuario is not None else _usuario_log.get()
        with conexion(base) as conn:
            conn.execute(
                """
                INSERT INTO modificaciones (
                    creado_en, usuario, accion, entidad, identificacion,
                    resumen, detalle_json, version_antes, version_despues
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    quien,
                    accion,
                    entidad,
                    identificacion,
                    resumen,
                    json.dumps(detalle, ensure_ascii=False) if detalle else None,
                    version_antes,
                    version_despues,
                ),
            )
    except Exception:
        return


def listar_modificaciones(base: Path | None = None, *, limite: int = 200) -> list[dict[str, Any]]:
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT id, creado_en, usuario, accion, entidad, identificacion,
                   resumen, detalle_json, version_antes, version_despues
            FROM modificaciones
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limite, 500)),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw = item.pop("detalle_json", None)
        try:
            item["detalle"] = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            item["detalle"] = None
        item["accion_etiqueta"] = ETIQUETAS_ACCION.get(item.get("accion") or "", item.get("accion") or "")
        out.append(item)
    return out


def _texto(val: Any) -> str:
    if val is None:
        return ""
    texto = str(val).strip()
    if texto.lower() in {"none", "nan", "null", "nat"}:
        return ""
    return texto


def comparar_versiones(
    version_de: int,
    version_a: int,
    *,
    base: Path | None = None,
    limite: int = 150,
) -> dict[str, Any]:
    """Compara dos snapshots: altas, bajas y cambios de campos clave."""
    if int(version_de) == int(version_a):
        raise ValueError("Elija dos versiones distintas para comparar.")
    meta_de = obtener_version(int(version_de), base)
    meta_a = obtener_version(int(version_a), base)
    if meta_de is None or meta_a is None:
        raise ValueError("Una de las versiones no existe.")
    df_de = cargar_dataframe_version(int(version_de), base)
    df_a = cargar_dataframe_version(int(version_a), base)
    if "Identificación" not in df_de.columns or "Identificación" not in df_a.columns:
        raise ValueError("Las versiones no tienen columna de identificación.")

    mapa_de: dict[str, dict] = {}
    for fila in df_de.iter_rows(named=True):
        ident = normalizar_id(fila.get("Identificación"))
        if ident:
            mapa_de[ident] = fila
    mapa_a: dict[str, dict] = {}
    for fila in df_a.iter_rows(named=True):
        ident = normalizar_id(fila.get("Identificación"))
        if ident:
            mapa_a[ident] = fila

    ids_de, ids_a = set(mapa_de), set(mapa_a)
    altas = sorted(ids_a - ids_de)
    bajas = sorted(ids_de - ids_a)
    cambios: list[dict[str, Any]] = []
    for ident in sorted(ids_de & ids_a):
        antes, despues = mapa_de[ident], mapa_a[ident]
        campos: list[dict[str, str]] = []
        for col in _COLS_DIFF:
            va, vb = _texto(antes.get(col)), _texto(despues.get(col))
            if va != vb:
                campos.append({"campo": col, "antes": va or "—", "despues": vb or "—"})
        if campos:
            cambios.append(
                {
                    "identificacion": ident,
                    "nombre": _texto(despues.get("Nombre y apellidos"))
                    or _texto(antes.get("Nombre y apellidos")),
                    "campos": campos,
                }
            )

    return {
        "de": meta_de,
        "a": meta_a,
        "altas": [
            {
                "identificacion": i,
                "nombre": _texto(mapa_a[i].get("Nombre y apellidos")),
            }
            for i in altas[:limite]
        ],
        "bajas": [
            {
                "identificacion": i,
                "nombre": _texto(mapa_de[i].get("Nombre y apellidos")),
            }
            for i in bajas[:limite]
        ],
        "cambios": cambios[:limite],
        "n_altas": len(altas),
        "n_bajas": len(bajas),
        "n_cambios": len(cambios),
        "truncado": len(altas) > limite or len(bajas) > limite or len(cambios) > limite,
    }
