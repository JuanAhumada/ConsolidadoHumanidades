"""
Servicios de la web: inventario de archivos fuente y generación del consolidado.

No ponga lógica de negocio pesada aquí; delegue a core.pipeline y storage.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
import re
import unicodedata

from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    cargar_config,
    carpeta_excels,
    guardar_excel_fuente,
    slot_es_requerido,
)
from consolidado.core.constants import aplicar_config
from consolidado.core.colores_programa import colores_programas_fijos
from consolidado.core.permanencia import cargar_metas
from consolidado.core.pipeline import ejecutar_consolidado, generar_dataframe_consolidado
from consolidado.core.prioridad import (
    METADATA_NIVELES,
    aplicar_colores_prioridad,
    colores_fila_para_gui,
)
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
    vacio = {
        "disponible": False,
        "graduacion": [],
        "permanencia": [],
        "historico": [],
        "graficas": [],
    }
    try:
        cfg = cfg_actual()
        return cargar_metas(cfg, PROJECT_ROOT)
    except Exception:
        return vacio


def _tinta_sobre_hex(hex_color: str) -> str:
    h = str(hex_color or "").lstrip("#")
    if len(h) != 6:
        return "#0a1628"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#0a1628" if luma >= 155 else "#ffffff"


def leyenda_colores() -> dict[str, Any]:
    cfg = cfg_actual()
    aplicar_colores_prioridad(cfg)
    excel = []
    for item in colores_fila_para_gui():
        hex_raw = str(item.get("color") or "").lstrip("#")
        hex_css = f"#{hex_raw}" if hex_raw else "#BDC3C7"
        excel.append({**item, "hex": hex_css, "ink": _tinta_sobre_hex(hex_css)})
    programas = []
    for item in colores_programas_fijos():
        programas.append({**item, "ink": item.get("ink") or _tinta_sobre_hex(item.get("hex", ""))})
    programas.append(
        {
            "clave": "neutro",
            "hex": "#334155",
            "soft": "#e2e8f0",
            "ink": "#ffffff",
            "corta": "Sin programa",
            "nota": "Gris pizarra si el estudiante no tiene carrera o no está en Humanidades.",
        }
    )
    return {
        "excel": excel,
        "programas": programas,
        "niveles": list(METADATA_NIVELES),
    }


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


def _norm_nombre_archivo(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t.casefold()).strip()


_PISTAS_SLOT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bd12", ("bd12", "bd 12", "matriculad entrenamiento", "activos entrenamiento")),
    ("bd_prio_psi", ("psicolog", "prio psi", "priorizado psic")),
    ("bd_prio_lic", ("prio lic", "licenciatur", "priorizados lic")),
    ("bd_permanencia", ("permanencia", "ruta de grado", "ruta grado")),
    ("bd_graduacion", ("graduacion", "gestion gradu")),
    ("bd_alertas_com_1", ("alertas com 1", "alerta comunicacion inicial", "comunicacion inicial")),
    ("bd_alertas_com_2", ("alertas com 2", "alerta comunicacion final", "comunicacion final")),
    ("bd_alertas_psi_1", ("alertas psi 1", "alerta psicologia inicial", "psicologia inicial")),
    ("bd_alertas_psi_2", ("alertas psi 2", "alerta psicologia final", "psicologia final")),
    ("bd_rep", ("repetid", "asignatura repet")),
    ("bd3", ("beca", "credito", "bd3")),
    ("bd2", ("grupos prioriz", "bd2")),
    ("bd1", ("matriculad", "bd1")),
    ("bd_alertas_com_1", ("alerta comunic", "alertas com")),
    ("bd_alertas_psi_1", ("alerta psic", "alertas psi")),
    ("bd2", ("priorizad",)),
)


def resolver_slot_por_nombre(
    archivo_nombre: str,
    cfg: dict[str, Any] | None = None,
    *,
    ya_usados: set[str] | None = None,
) -> dict[str, Any] | None:
    """Asocia un Excel subido con un slot de archivos_fuente."""
    cfg = cfg or cfg_actual()
    usados = ya_usados or set()
    slots = [s for s in cfg.get("archivos_fuente", []) if s.get("id") not in usados]
    if not slots:
        return None
    nombre = Path(archivo_nombre).name
    stem = Path(nombre).stem
    n_nom = _norm_nombre_archivo(nombre)
    n_stem = _norm_nombre_archivo(stem)
    compact = n_nom.replace(" ", "")

    for slot in slots:
        guardado = str(slot.get("nombre_guardado") or "")
        if not guardado:
            continue
        if _norm_nombre_archivo(guardado) == n_nom:
            return slot
        if _norm_nombre_archivo(Path(guardado).stem) == n_stem:
            return slot

    por_id = {str(s.get("id") or ""): s for s in slots}
    if n_stem.replace(" ", "") in {k.replace("_", "") for k in por_id}:
        for sid, slot in por_id.items():
            if _norm_nombre_archivo(sid).replace(" ", "") == n_stem.replace(" ", ""):
                return slot

    ids = sorted(por_id.keys(), key=len, reverse=True)
    for sid in ids:
        sid_c = _norm_nombre_archivo(sid).replace(" ", "")
        if not sid_c:
            continue
        if compact == sid_c or compact.startswith(sid_c) and not compact[len(sid_c):len(sid_c)+1].isalnum():
            return por_id[sid]
        if f" {sid_c} " in f" {n_nom} " or n_nom.startswith(sid_c + " "):
            return por_id[sid]

    if "matriculad" in n_nom and "entrenamiento" in n_nom and "bd12" in por_id:
        return por_id["bd12"]
    if "prioriz" in n_nom and "entrenamiento" in n_nom and "bd_prio_lic" in por_id:
        return por_id["bd_prio_lic"]

    for sid, pistas in _PISTAS_SLOT:
        slot = por_id.get(sid)
        if slot is None:
            continue
        if any(p in n_nom for p in pistas):
            return slot
    return None


def subir_varios(archivos: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Guarda varios Excel de una vez y deja cada uno en el historial."""
    cfg = cfg_actual()
    ok: list[dict[str, str]] = []
    sin_slot: list[str] = []
    errores: list[str] = []
    usados: set[str] = set()
    for nombre, contenido in archivos:
        if not contenido:
            errores.append(f"«{nombre}» está vacío.")
            continue
        slot = resolver_slot_por_nombre(nombre, cfg, ya_usados=usados)
        if slot is None:
            sin_slot.append(nombre)
            continue
        slot_id = str(slot.get("id") or "")
        try:
            subir_slot(slot_id, nombre, contenido)
        except Exception as exc:
            errores.append(f"«{nombre}»: {exc}")
            continue
        usados.add(slot_id)
        ok.append({"slot_id": slot_id, "titulo": str(slot.get("titulo") or slot_id), "archivo": nombre})
    if ok:
        titulos = ", ".join(x["titulo"] for x in ok)
        registrar_modificacion(
            accion="cargar_archivos",
            resumen=f"Actualizó {len(ok)} archivo{'s' if len(ok) != 1 else ''}: {titulos}",
            entidad="archivo",
            detalle={"archivos": ok, "sin_slot": sin_slot, "errores": errores},
        )
    return {"ok": ok, "sin_slot": sin_slot, "errores": errores}


def subir_lote(archivos: dict[str, tuple[str, bytes]]) -> dict[str, Any]:
    """Carga los Excel ya asignados a cada slot (selección individual)."""
    ok: list[dict[str, str]] = []
    errores: list[str] = []
    for slot_id, (nombre, contenido) in archivos.items():
        try:
            info = subir_slot(slot_id, nombre, contenido)
            ok.append(
                {
                    "slot_id": slot_id,
                    "archivo": nombre,
                    "destino": str(info.get("destino") or ""),
                }
            )
        except Exception as exc:
            errores.append(f"{nombre}: {exc}")
    return {"ok": ok, "errores": errores}


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
