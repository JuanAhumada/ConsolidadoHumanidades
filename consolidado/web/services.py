"""
Servicios de la web: inventario de archivos fuente y generación del consolidado.

No ponga lógica de negocio pesada aquí; delegue a core.pipeline y storage.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    cargar_config,
    carpeta_excels,
    guardar_excel_fuente,
    slot_es_requerido,
)
from consolidado.core.constants import aplicar_config
from consolidado.core.permanencia import cargar_metas
from consolidado.core.pipeline import ejecutar_consolidado, generar_dataframe_consolidado
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import (
    cargar_dataframe_version,
    contar_estudiantes_distintos,
    contar_versiones,
    ultima_version,
    ultima_version_por_id,
)
from consolidado.storage.modificaciones import comparar_versiones, registrar_modificacion
from consolidado.storage.versiones import (
    asegurar_excel_version,
    asegurar_semilla_si_vacia,
    importar_excel_como_version,
)


def base_proyecto() -> Path:
    return PROJECT_ROOT


def cfg_actual() -> dict[str, Any]:
    cfg = cargar_config(PROJECT_ROOT)
    return aplicar_config(cfg, PROJECT_ROOT)


def metas_ruta_grado() -> dict[str, Any]:
    vacio = {"disponible": False, "graduacion": [], "permanencia": []}
    try:
        cfg = cfg_actual()
        return cargar_metas(cfg, PROJECT_ROOT)
    except Exception:
        return vacio


def estado_archivos(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or cfg_actual()
    carpeta = carpeta_excels(cfg, PROJECT_ROOT)
    categorias = cfg.get("categorias_fuente", CATEGORIAS_FUENTE_DEFAULT)
    por_cat: dict[str, list[dict]] = {c: [] for c in ORDEN_CATEGORIAS_FUENTE}
    for slot in cfg.get("archivos_fuente", []):
        cat = slot.get("categoria", "base")
        nombre = slot.get("nombre_guardado", "")
        ruta = carpeta / nombre
        item = {
            **slot,
            "requerido": slot_es_requerido(slot),
            "cargado": ruta.is_file(),
            "ruta": str(ruta) if ruta.is_file() else None,
        }
        por_cat.setdefault(cat, []).append(item)

    docs = []
    for doc in cfg.get("documentos_adicionales", []):
        nombre = doc.get("nombre_guardado", "")
        ruta = carpeta / nombre
        docs.append(
            {
                **doc,
                "cargado": ruta.is_file(),
                "num_columnas": len(doc.get("columnas") or []),
            }
        )

    obligatorios = [s for slots in por_cat.values() for s in slots if s.get("requerido")]
    listos = sum(1 for s in obligatorios if s.get("cargado"))
    return {
        "categorias": [
            {"clave": k, "titulo": categorias.get(k, k.title()), "slots": por_cat.get(k, [])}
            for k in ORDEN_CATEGORIAS_FUENTE
            if por_cat.get(k)
        ],
        "documentos": docs,
        "obligatorios_listos": listos,
        "obligatorios_total": len(obligatorios),
        "listo_generar": listos == len(obligatorios) and len(obligatorios) > 0,
        "num_versiones": contar_versiones(PROJECT_ROOT),
        "num_estudiantes_distintos": contar_estudiantes_distintos(PROJECT_ROOT),
        "ultima": ultima_version(PROJECT_ROOT),
    }


def _id_version(meta: dict[str, Any] | None) -> int | None:
    if not meta or meta.get("id") is None:
        return None
    return int(meta["id"])


def subir_slot(slot_id: str, archivo_nombre: str, contenido: bytes) -> dict[str, Any]:
    cfg = cfg_actual()
    slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("id") == slot_id), None)
    if slot is None:
        raise ValueError(f"No existe el archivo fuente «{slot_id}».")
    carpeta = carpeta_excels(cfg, PROJECT_ROOT)
    carpeta.mkdir(parents=True, exist_ok=True)
    tmp = carpeta / f"_upload_{slot_id}{Path(archivo_nombre).suffix.lower() or '.xlsx'}"
    tmp.write_bytes(contenido)
    try:
        destino = guardar_excel_fuente(tmp, slot, cfg, PROJECT_ROOT)
    finally:
        if tmp.is_file() and tmp.name.startswith("_upload_"):
            try:
                tmp.unlink()
            except OSError:
                pass
    aplicar_config(cfg, PROJECT_ROOT)
    titulo = slot.get("titulo") or slot_id
    registrar_modificacion(
        accion="cargar_archivo",
        resumen=f"Cargó «{titulo}»",
        entidad="archivo",
        identificacion=slot_id,
        detalle={"archivo": archivo_nombre, "destino": str(destino)},
    )
    return {"ok": True, "slot_id": slot_id, "destino": str(destino)}


def parse_fecha(texto: str | None) -> date:
    raw = (texto or "").strip()
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Fecha inválida. Use el formato AAAA-MM-DD.") from exc


def generar(
    *,
    fecha_version: date | None = None,
    notas: str | None = None,
    abrir: bool = True,
) -> dict[str, Any]:
    cfg = cfg_actual()
    asegurar_semilla_si_vacia(PROJECT_ROOT)
    antes = ultima_version_por_id(PROJECT_ROOT)
    consolidado, destino = ejecutar_consolidado(
        cfg,
        base=PROJECT_ROOT,
        abrir=abrir,
        fecha_version=fecha_version,
        notas=notas,
    )
    despues = ultima_version_por_id(PROJECT_ROOT)
    fecha = (fecha_version or date.today()).isoformat()
    registrar_modificacion(
        accion="generar",
        resumen=f"Generó consolidado {fecha} · {consolidado.height} estudiantes",
        entidad="version",
        version_antes=_id_version(antes),
        version_despues=_id_version(despues),
        detalle={"excel": str(destino), "estudiantes": consolidado.height},
    )
    return {
        "ok": True,
        "estudiantes": consolidado.height,
        "excel": str(destino),
        "version": ultima_version(PROJECT_ROOT),
    }


def importar_version(
    excel_origen: Path,
    fecha_version: date,
    notas: str | None = None,
) -> dict[str, Any]:
    antes = ultima_version_por_id(PROJECT_ROOT)
    meta = importar_excel_como_version(
        excel_origen,
        fecha_version=fecha_version,
        notas=notas,
        base=PROJECT_ROOT,
    )
    registrar_modificacion(
        accion="importar",
        resumen=(
            f"Importó Excel como versión {fecha_version.isoformat()}"
            f" · {meta.get('num_estudiantes', 0)} estudiantes"
        ),
        entidad="version",
        version_antes=_id_version(antes),
        version_despues=_id_version(meta),
        detalle={"excel": str(excel_origen), "periodo": meta.get("periodo")},
    )
    return {"ok": True, "version": meta, "estudiantes": meta.get("num_estudiantes", 0)}


def generar_version_historica(
    archivos_por_slot: dict[str, tuple[str, bytes]],
    fecha_version: date,
    notas: str | None = None,
) -> dict[str, Any]:
    """Genera una versión SQL desde fuentes copiadas a una carpeta aislada."""
    cfg = cfg_actual()
    faltan: list[str] = []
    slots = {s.get("id"): s for s in cfg.get("archivos_fuente", [])}
    for slot in cfg.get("archivos_fuente", []):
        if slot_es_requerido(slot) and slot.get("id") not in archivos_por_slot:
            faltan.append(str(slot.get("titulo") or slot.get("id")))
    if faltan:
        raise ValueError(
            "Faltan archivos obligatorios para la versión histórica: " + ", ".join(faltan)
        )
    desconocidos = [sid for sid in archivos_por_slot if sid not in slots]
    if desconocidos:
        raise ValueError("Archivo(s) no reconocidos: " + ", ".join(desconocidos))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta = PROJECT_ROOT / "datos" / "historico" / f"{fecha_version.isoformat()}_{stamp}"
    carpeta.mkdir(parents=True, exist_ok=True)
    for slot_id, (_nombre, contenido) in archivos_por_slot.items():
        slot = slots[slot_id]
        dest_name = slot.get("nombre_guardado") or f"{slot_id}.xlsx"
        (carpeta / dest_name).write_bytes(contenido)

    antes = ultima_version_por_id(PROJECT_ROOT)
    texto_notas = (notas or "").strip() or (
        f"Versión histórica desde fuentes aisladas · {fecha_version.isoformat()}"
    )
    consolidado, destino = ejecutar_consolidado(
        cfg,
        base=PROJECT_ROOT,
        carpeta_fuentes=carpeta,
        abrir=False,
        fecha_version=fecha_version,
        persistir_config=False,
        notas=texto_notas,
    )
    despues = ultima_version_por_id(PROJECT_ROOT)
    registrar_modificacion(
        accion="generar_historico",
        resumen=(
            f"Montó datos antiguos {fecha_version.isoformat()}"
            f" · {consolidado.height} estudiantes"
        ),
        entidad="version",
        version_antes=_id_version(antes),
        version_despues=_id_version(despues),
        detalle={
            "carpeta": str(carpeta),
            "excel": str(destino),
            "slots": list(archivos_por_slot),
        },
    )
    return {
        "ok": True,
        "estudiantes": consolidado.height,
        "excel": str(destino),
        "carpeta": str(carpeta),
        "version": despues,
    }


def excel_de_version(version_id: int) -> Path:
    return asegurar_excel_version(version_id, PROJECT_ROOT)


def df_ultima_version():
    ult = ultima_version(PROJECT_ROOT)
    if not ult:
        cfg = cfg_actual()
        df, _ = generar_dataframe_consolidado(cfg, base=PROJECT_ROOT)
        return df, None
    return cargar_dataframe_version(ult["id"], PROJECT_ROOT), ult


def comparar(version_de: int, version_a: int) -> dict[str, Any]:
    return comparar_versiones(version_de, version_a, base=PROJECT_ROOT)
