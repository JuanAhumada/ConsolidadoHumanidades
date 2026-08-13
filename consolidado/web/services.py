"""Servicios compartidos de la interfaz web."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    cargar_config,
    carpeta_excels,
    guardar_config,
    guardar_excel_fuente,
    restaurar_config_fabrica,
    slot_es_requerido,
)
from consolidado.core.constants import aplicar_config
from consolidado.core.ficha_estudiante import obtener_ficha_estudiante
from consolidado.core.pipeline import ejecutar_consolidado, generar_dataframe_consolidado
from consolidado.core.priorizados import (
    buscar_estudiantes_en_fuentes,
    obtener_lista_priorizados_vista,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.alertas_propias import (
    agregar_alerta_propia,
    cargar_alertas_propias,
    quitar_alerta_propia,
)
from consolidado.storage.contactados import marcar_contactado
from consolidado.storage.db import (
    cargar_dataframe_version,
    contar_versiones,
    listar_versiones,
    ultima_version,
)
from consolidado.storage.priorizados import (
    agregar_priorizado_propio,
    set_priorizado_activo,
)
from consolidado.storage.versiones import asegurar_semilla_si_vacia


def base_proyecto() -> Path:
    return PROJECT_ROOT


def cfg_actual() -> dict[str, Any]:
    cfg = cargar_config(PROJECT_ROOT)
    return aplicar_config(cfg, PROJECT_ROOT)


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
        "ultima": ultima_version(PROJECT_ROOT),
    }


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
    return {"ok": True, "slot_id": slot_id, "destino": str(destino)}


def generar() -> dict[str, Any]:
    cfg = cfg_actual()
    asegurar_semilla_si_vacia(PROJECT_ROOT)
    consolidado, destino = ejecutar_consolidado(
        cfg, base=PROJECT_ROOT, abrir=True
    )
    return {
        "ok": True,
        "estudiantes": consolidado.height,
        "excel": str(destino),
        "version": ultima_version(PROJECT_ROOT),
    }


def df_ultima_version():
    ult = ultima_version(PROJECT_ROOT)
    if not ult:
        cfg = cfg_actual()
        df, _ = generar_dataframe_consolidado(cfg, base=PROJECT_ROOT)
        return df, None
    return cargar_dataframe_version(ult["id"], PROJECT_ROOT), ult
