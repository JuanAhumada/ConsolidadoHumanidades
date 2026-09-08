"""
Servicios de la web: inventario de archivos fuente y generación del consolidado.

No ponga lógica de negocio pesada aquí; delegue a core.pipeline y storage.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
import re
import tempfile
import unicodedata

from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    cargar_config,
    carpeta_excels,
    construir_columnas_salida,
    etiqueta_alias,
    guardar_config,
    guardar_excel_fuente,
    slot_es_requerido,
)
from consolidado.core.constants import aplicar_config
from consolidado.core.colores_programa import colores_programas_fijos
from consolidado.core.permanencia import cargar_metas
from consolidado.core.pipeline import ejecutar_consolidado, generar_dataframe_consolidado
from consolidado.core.charts import (
    columna_excluida_grafica,
    es_columna_materia_grafica,
    programas_disponibles,
)
from consolidado.core.columnas import aliases_para_slot, construir_mapa_columnas, usando_aliases
from consolidado.core.vista_previa import campos_editables_tipo
from consolidado.core.documentos import (
    CATEGORIAS_FICHA,
    categorias_documento,
    columnas_config_documento,
    slug_documento_id,
    sugerir_titulo_documento,
    vista_previa_excel,
    canonizar_grupo_encabezado,
    etiqueta_grupo_ficha,
)
from consolidado.core.prioridad import (
    BLOQUES_PUNTUACION_GUI,
    FORMULA_PUNTAJE_GUI,
    METADATA_COLORES_FILA,
    METADATA_NIVELES,
    aplicar_colores_prioridad,
    colores_fila_para_gui,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import (
    cargar_dataframe_version,
    contar_estudiantes_distintos,
    contar_versiones,
    listar_versiones,
    obtener_version,
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
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return "#0a1628"
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#0a1628" if luma >= 155 else "#ffffff"


def leyenda_colores() -> dict[str, Any]:
    vacio: dict[str, Any] = {"excel": [], "programas": [], "niveles": []}
    try:
        cfg = cfg_actual()
        aplicar_colores_prioridad(cfg)
        excel = []
        for item in colores_fila_para_gui():
            hex_raw = str(item.get("color") or "").lstrip("#")
            hex_css = f"#{hex_raw}" if hex_raw else "#BDC3C7"
            excel.append({**item, "hex": hex_css, "ink": _tinta_sobre_hex(hex_css)})
        programas = []
        for item in colores_programas_fijos():
            programas.append(
                {**item, "ink": item.get("ink") or _tinta_sobre_hex(item.get("hex", ""))}
            )
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
                "grupo_etiqueta": etiqueta_grupo_ficha(
                    doc.get("grupo_encabezado") or doc.get("categoria") or ""
                ),
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
    ("bd_alertas_com_2", ("alertas com 2", "alertas 2 comunic", "alerta comunicacion final", "comunicacion final")),
    ("bd_alertas_psi_2", ("alertas psi 2", "alertas 2 psic", "alerta psicologia final", "psicologia final")),
    ("bd_alertas_com_1", ("alertas com 1", "alertas 1 comunic", "alerta comunicacion inicial", "comunicacion inicial")),
    ("bd_alertas_psi_1", ("alertas psi 1", "alertas 1 psic", "alerta psicologia inicial", "psicologia inicial")),
    ("bd12", ("bd12", "bd 12", "bd 1.2", "bd 1 2", "matriculad entrenamiento", "activos entrenamiento")),
    ("bd_prio_psi", ("prio psi", "priorizado psic", "enriquecido")),
    ("bd_prio_lic", ("prio lic", "priorizados lic", "licen comun")),
    ("bd_permanencia", ("permanencia", "ruta de grado", "ruta grado")),
    ("bd_graduacion", ("graduacion", "gestion gradu")),
    ("bd_rep", ("repetid", "asignatura repet")),
    ("bd3", ("beca", "credito", "bd3")),
    ("bd2", ("grupos prioriz", "bd2")),
    ("bd1", ("matriculad", "matriclad", "bd 1 ", "bd1")),
    ("bd_alertas_com_1", ("alerta comunic", "alertas com")),
    ("bd_alertas_psi_1", ("alerta psic", "alertas psi")),
    ("bd_prio_psi", ("psicolog",)),
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


def extraer_excels_de_zip(contenido: bytes) -> list[tuple[str, bytes]]:
    """Saca los Excel de un ZIP (incluye carpetas internas)."""
    import io
    import zipfile

    if not contenido:
        raise ValueError("El ZIP está vacío.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as exc:
        raise ValueError("Ese archivo no es un ZIP válido.") from exc
    lote: list[tuple[str, bytes]] = []
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            nombre = Path(info.filename).name
            if not nombre or nombre.startswith(".") or nombre.startswith("~"):
                continue
            if Path(nombre).suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                continue
            lote.append((nombre, zf.read(info)))
    if not lote:
        raise ValueError("El ZIP no trae ningún Excel.")
    return lote


NOMBRES_PAQUETE_INICIAL = (
    "Archivos iniciales.zip",
    "paquete_inicial.zip",
    "ArchivosPrueba2026-1.zip",
)


def rutas_paquete_inicial() -> list[Path]:
    """Dónde puede estar el paquete de fuentes para el primer consolidado.

    En el ZIP de Windows el archivo visible va en la raíz (junto al lanzador);
    el .exe corre desde la subcarpeta ``ConsolidadoHumanidades/``.
    """
    carpetas = [PROJECT_ROOT, PROJECT_ROOT / "empaque", PROJECT_ROOT.parent]
    vistos: set[Path] = set()
    hallados: list[Path] = []
    for nombre in NOMBRES_PAQUETE_INICIAL:
        for carpeta in carpetas:
            ruta = carpeta / nombre
            try:
                clave = ruta.resolve()
            except OSError:
                clave = ruta
            if clave in vistos:
                continue
            vistos.add(clave)
            if ruta.is_file():
                hallados.append(ruta)
    return hallados


def hay_paquete_inicial() -> dict[str, Any] | None:
    rutas = rutas_paquete_inicial()
    if not rutas:
        return None
    p = rutas[0]
    return {"ruta": str(p), "nombre": p.name, "bytes": p.stat().st_size}


def importar_paquete_fuentes(
    contenido: bytes,
    *,
    nombre_zip: str = "paquete.zip",
) -> dict[str, Any]:
    """Carga un ZIP de Excel fuente como configuración inicial (Data)."""
    lote = extraer_excels_de_zip(contenido)
    resultado = subir_varios(lote)
    resultado["zip"] = nombre_zip
    resultado["encontrados"] = len(lote)
    return resultado


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


def _ext_excel(nombre: str) -> str:
    suf = Path(nombre or "").suffix.lower()
    if suf not in {".xlsx", ".xlsm", ".xls"}:
        raise ValueError("Use un Excel (.xlsx, .xlsm o .xls).")
    return suf


def _escribir_tmp_excel(contenido: bytes, nombre: str) -> Path:
    if not contenido:
        raise ValueError("Archivo vacío.")
    suf = _ext_excel(nombre)
    with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
        tmp.write(contenido)
        return Path(tmp.name)


def previsualizar_excel_bytes(
    contenido: bytes,
    nombre: str,
    *,
    hoja: str | None = None,
) -> dict[str, Any]:
    cfg = cfg_actual()
    ruta = _escribir_tmp_excel(contenido, nombre)
    try:
        data = vista_previa_excel(ruta, hoja=hoja, cfg=cfg)
    finally:
        try:
            ruta.unlink()
        except OSError:
            pass
    data["nombre_archivo"] = Path(nombre).name
    data["titulo_sugerido"] = sugerir_titulo_documento(nombre)
    data["categorias"] = categorias_documento(cfg)
    data["categorias_fijas"] = [etiqueta for etiqueta, _ in CATEGORIAS_FICHA]
    return data


def previsualizar_documento_guardado(
    doc_id: str,
    *,
    hoja: str | None = None,
) -> dict[str, Any]:
    cfg = cfg_actual()
    doc = next((d for d in cfg.get("documentos_adicionales", []) if d.get("id") == doc_id), None)
    if doc is None:
        raise ValueError(f"No existe el documento «{doc_id}».")
    nombre = doc.get("nombre_guardado") or ""
    ruta = carpeta_excels(cfg, PROJECT_ROOT) / nombre
    if not ruta.is_file():
        raise ValueError("El Excel de este documento no está en la carpeta de entrada.")
    data = vista_previa_excel(ruta, hoja=hoja or doc.get("hoja"), cfg=cfg)
    usados = {
        (c.get("aliases") or [""])[0]: c.get("salida") or (c.get("aliases") or [""])[0]
        for c in doc.get("columnas") or []
        if (c.get("aliases") or [""])[0]
    }
    data["nombre_archivo"] = nombre
    data["titulo_sugerido"] = doc.get("titulo") or sugerir_titulo_documento(nombre)
    data["categorias"] = categorias_documento(cfg)
    data["categorias_fijas"] = [etiqueta for etiqueta, _ in CATEGORIAS_FICHA]
    data["documento"] = {
        "id": doc.get("id"),
        "titulo": doc.get("titulo"),
        "grupo_encabezado": doc.get("grupo_encabezado") or doc.get("categoria") or "",
        "grupo_etiqueta": etiqueta_grupo_ficha(
            doc.get("grupo_encabezado") or doc.get("categoria") or ""
        ),
        "hoja": doc.get("hoja") or data.get("hoja"),
        "pk": (doc.get("columna_identificacion_aliases") or [data.get("pk_sugerida")])[0],
        "columnas_usadas": usados,
    }
    return data


def guardar_documento_adicional(
    *,
    titulo: str,
    grupo: str,
    pk: str,
    columnas: list[dict[str, Any]],
    hoja: str | None = None,
    contenido: bytes | None = None,
    nombre_archivo: str = "",
    doc_id: str | None = None,
) -> dict[str, Any]:
    cfg = cfg_actual()
    titulo = (titulo or "").strip()
    grupo = canonizar_grupo_encabezado((grupo or "").strip() or "Extra")
    pk = (pk or "").strip()
    if not titulo:
        raise ValueError("Indique un nombre para el documento.")
    if not pk:
        raise ValueError("Elija la columna de identificación (llave foránea al consolidado).")
    cols = columnas_config_documento(columnas, pk=pk)
    if not cols:
        raise ValueError("Marque al menos una columna de datos (la identificación solo sirve de llave).")

    docs = list(cfg.get("documentos_adicionales") or [])
    if doc_id:
        doc = next((d for d in docs if d.get("id") == doc_id), None)
        if doc is None:
            raise ValueError(f"No existe el documento «{doc_id}».")
        doc["titulo"] = titulo
        doc["grupo_encabezado"] = grupo
        doc["categoria"] = grupo
        doc["columnas"] = cols
        doc["columna_identificacion_aliases"] = [pk]
        if hoja:
            doc["hoja"] = hoja
        if contenido:
            suf = _ext_excel(nombre_archivo or doc.get("nombre_guardado") or "archivo.xlsx")
            nombre_guardado = doc.get("nombre_guardado") or f"{doc_id}{suf}"
            if Path(nombre_guardado).suffix.lower() != suf:
                nombre_guardado = f"{Path(nombre_guardado).stem}{suf}"
            doc["nombre_guardado"] = nombre_guardado
            carpeta = carpeta_excels(cfg, PROJECT_ROOT)
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / nombre_guardado).write_bytes(contenido)
        cfg["documentos_adicionales"] = docs
        guardar_config(cfg, PROJECT_ROOT)
        aplicar_config(cfg, PROJECT_ROOT)
        registrar_modificacion(
            accion="documento",
            resumen=f"Actualizó documento adicional «{titulo}»",
            entidad="documento",
            identificacion=str(doc.get("id")),
        )
        return {"ok": True, "id": doc.get("id"), "titulo": titulo}

    if not contenido:
        raise ValueError("Seleccione un Excel para el documento nuevo.")
    suf = _ext_excel(nombre_archivo or "archivo.xlsx")
    existentes = {str(d.get("id") or "") for d in docs}
    nuevo_id = slug_documento_id(titulo, existentes)
    nombre_guardado = f"{nuevo_id}{suf}"
    carpeta = carpeta_excels(cfg, PROJECT_ROOT)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre_guardado).write_bytes(contenido)
    doc = {
        "id": nuevo_id,
        "titulo": titulo,
        "grupo_encabezado": grupo,
        "categoria": grupo,
        "nombre_guardado": nombre_guardado,
        "hoja": hoja or None,
        "filtrar_programas": False,
        "columna_identificacion_aliases": [pk],
        "columnas": cols,
    }
    docs.append(doc)
    cfg["documentos_adicionales"] = docs
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="documento",
        resumen=f"Añadió documento adicional «{titulo}»",
        entidad="documento",
        identificacion=nuevo_id,
    )
    return {"ok": True, "id": nuevo_id, "titulo": titulo}


def eliminar_documento_adicional(doc_id: str) -> dict[str, Any]:
    cfg = cfg_actual()
    docs = list(cfg.get("documentos_adicionales") or [])
    doc = next((d for d in docs if d.get("id") == doc_id), None)
    if doc is None:
        raise ValueError(f"No existe el documento «{doc_id}».")
    cfg["documentos_adicionales"] = [d for d in docs if d.get("id") != doc_id]
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    nombre = doc.get("nombre_guardado") or ""
    ruta = carpeta_excels(cfg, PROJECT_ROOT) / nombre
    if nombre and ruta.is_file():
        try:
            ruta.unlink()
        except OSError:
            pass
    registrar_modificacion(
        accion="documento",
        resumen=f"Eliminó documento adicional «{doc.get('titulo') or doc_id}»",
        entidad="documento",
        identificacion=doc_id,
    )
    return {"ok": True, "id": doc_id}


def aliases_para_editar() -> list[dict[str, str]]:
    cfg = cfg_actual()
    aliases = cfg.get("aliases") or {}
    filas = []
    for canon in sorted(aliases.keys(), key=etiqueta_alias):
        vals = aliases.get(canon) or []
        filas.append(
            {
                "canon": canon,
                "etiqueta": etiqueta_alias(canon),
                "sinonimos": ", ".join(str(v) for v in vals if str(v).strip()),
            }
        )
    return filas


def guardar_aliases(pares: dict[str, str]) -> None:
    cfg = cargar_config(PROJECT_ROOT)
    aliases = dict(cfg.get("aliases") or {})
    for canon, texto in pares.items():
        if canon not in aliases:
            continue
        sinonimos = [p.strip() for p in str(texto).split(",") if p.strip()]
        aliases[canon] = sinonimos
    cfg["aliases"] = aliases
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen="Actualizó los encabezados de origen (aliases)",
        entidad="config",
    )


def definicion_puntajes() -> dict[str, Any]:
    cfg = cfg_actual()
    info = cfg.get("info_puntajes") or {}
    return {
        "formula": FORMULA_PUNTAJE_GUI,
        "bloques": BLOQUES_PUNTUACION_GUI,
        "niveles": list(METADATA_NIVELES),
        "colores": list(METADATA_COLORES_FILA),
        "notas": str(info.get("notas") or ""),
    }


def guardar_notas_puntajes(notas: str) -> None:
    cfg = cargar_config(PROJECT_ROOT)
    actual = dict(cfg.get("info_puntajes") or {})
    actual["notas"] = (notas or "").strip()
    cfg["info_puntajes"] = actual
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen="Actualizó la información de puntajes",
        entidad="config",
    )


def programas_ultima_version() -> list[str]:
    df, _ = df_ultima_version()
    return programas_disponibles(df)


def listar_fuentes_para_mapa() -> list[dict[str, Any]]:
    cfg = cfg_actual()
    carpeta = carpeta_excels(cfg, PROJECT_ROOT)
    categorias = cfg.get("categorias_fuente", CATEGORIAS_FUENTE_DEFAULT)
    items: list[dict[str, Any]] = []
    for slot in cfg.get("archivos_fuente", []):
        nombre = slot.get("nombre_guardado") or ""
        items.append(
            {
                "kind": "slot",
                "id": slot.get("id"),
                "titulo": slot.get("titulo") or slot.get("id"),
                "grupo": categorias.get(slot.get("categoria"), slot.get("categoria") or "Fuente"),
                "cargado": (carpeta / nombre).is_file() if nombre else False,
            }
        )
    for doc in cfg.get("documentos_adicionales", []):
        nombre = doc.get("nombre_guardado") or ""
        items.append(
            {
                "kind": "doc",
                "id": doc.get("id"),
                "titulo": doc.get("titulo") or doc.get("id"),
                "grupo": etiqueta_grupo_ficha(
                    doc.get("grupo_encabezado") or doc.get("categoria") or "Extra"
                ),
                "cargado": (carpeta / nombre).is_file() if nombre else False,
            }
        )
    return items


def previsualizar_slot_fuente(slot_id: str, *, hoja: str | None = None) -> dict[str, Any]:
    cfg = cfg_actual()
    slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("id") == slot_id), None)
    if slot is None:
        raise ValueError(f"No existe el archivo fuente «{slot_id}».")
    nombre = slot.get("nombre_guardado") or ""
    ruta = carpeta_excels(cfg, PROJECT_ROOT) / nombre
    if not ruta.is_file():
        raise ValueError("Aún no hay un Excel cargado para este archivo. Cárguelo primero en Data.")
    hoja_usar = (hoja or "").strip() or slot.get("hoja")
    data = vista_previa_excel(ruta, hoja=hoja_usar, cfg=cfg)
    data["nombre_archivo"] = nombre
    with usando_aliases(aliases_para_slot(slot)):
        detectado = construir_mapa_columnas(data.get("columnas") or [])
    guardados = slot.get("aliases") or {}
    mapeo = []
    for canon in campos_editables_tipo(str(slot.get("tipo") or "")):
        origen_guardado = ""
        if isinstance(guardados.get(canon), list) and guardados[canon]:
            origen_guardado = str(guardados[canon][0])
        elif isinstance(guardados.get(canon), str):
            origen_guardado = guardados[canon]
        mapeo.append(
            {
                "canon": canon,
                "salida": etiqueta_alias(canon),
                "origen": origen_guardado or detectado.get(canon) or "",
            }
        )
    data["kind"] = "slot"
    data["slot"] = {
        "id": slot.get("id"),
        "titulo": slot.get("titulo"),
        "tipo": slot.get("tipo"),
        "hoja": slot.get("hoja") or data.get("hoja"),
    }
    data["mapeo"] = mapeo
    data["categorias"] = []
    return data


def guardar_mapeo_slot(
    slot_id: str,
    *,
    hoja: str | None,
    mapeo: list[dict[str, Any]],
) -> dict[str, Any]:
    cfg = cargar_config(PROJECT_ROOT)
    slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("id") == slot_id), None)
    if slot is None:
        raise ValueError(f"No existe el archivo fuente «{slot_id}».")
    aliases: dict[str, list[str]] = {}
    for item in mapeo:
        canon = str(item.get("canon") or "").strip()
        origen = str(item.get("origen") or "").strip()
        if canon and origen:
            aliases[canon] = [origen]
    slot["aliases"] = aliases
    if hoja is not None:
        texto = str(hoja).strip()
        slot["hoja"] = texto or None
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen=f"Actualizó el mapeo de «{slot.get('titulo') or slot_id}»",
        entidad="archivo",
        identificacion=slot_id,
    )
    return {"ok": True, "id": slot_id, "titulo": slot.get("titulo")}


def columnas_config_graficas() -> list[dict[str, Any]]:
    cfg = cfg_actual()
    df, _ = df_ultima_version()
    if df is not None:
        todas = [str(c) for c in df.columns if not es_columna_materia_grafica(str(c))]
    else:
        todas = [
            c
            for c in construir_columnas_salida(cfg, 1)
            if not es_columna_materia_grafica(c)
        ]
    guardadas = cfg.get("columnas_graficas")
    if isinstance(guardadas, list):
        activas = {str(c).strip() for c in guardadas if str(c).strip()}
    else:
        activas = {c for c in todas if not columna_excluida_grafica(c)}
    return [{"nombre": c, "activa": c in activas} for c in todas]


def _etiqueta_version(meta: dict[str, Any]) -> str:
    partes = []
    if meta.get("periodo"):
        partes.append(str(meta["periodo"]))
    if meta.get("fecha_version"):
        partes.append(str(meta["fecha_version"]))
    n = meta.get("num_estudiantes")
    if n is not None:
        partes.append(f"{n} estudiantes")
    etiqueta = " · ".join(partes) if partes else f"Versión {meta.get('id')}"
    return f"#{meta.get('id')} · {etiqueta}"


def listar_versiones_parcializado() -> list[dict[str, Any]]:
    items = []
    for v in listar_versiones(PROJECT_ROOT):
        items.append({**v, "etiqueta": _etiqueta_version(v)})
    return items


def datos_parcializado(version_id: int | None = None) -> dict[str, Any]:
    versiones = listar_versiones_parcializado()
    if not versiones:
        raise ValueError("Aún no hay un consolidado. Genere una versión primero.")
    if version_id is None:
        version_id = int(versiones[0]["id"])
    meta = obtener_version(version_id, PROJECT_ROOT)
    if meta is None:
        raise ValueError(f"No existe la versión #{version_id}.")
    df = cargar_dataframe_version(version_id, PROJECT_ROOT)
    cfg = cfg_actual()
    from consolidado.core.parcializado import (
        COLUMNAS_BASICAS,
        conteos_por_programa,
        grupos_columnas_version,
    )

    columnas = [str(c) for c in df.columns]
    basicas = [c for c in COLUMNAS_BASICAS if c in columnas]
    return {
        "version": {**meta, "etiqueta": _etiqueta_version(meta)},
        "columnas": columnas,
        "basicas": basicas,
        "grupos": grupos_columnas_version(df, cfg),
        "programas": conteos_por_programa(df),
        "filas": df.height,
    }


def conteo_parcializado(version_id: int, programas: list[str] | None = None) -> int:
    from consolidado.core.charts import filtrar_df_por_carreras

    df = cargar_dataframe_version(version_id, PROJECT_ROOT)
    return filtrar_df_por_carreras(df, programas).height


def excel_parcializado(
    version_id: int,
    *,
    columnas: list[str],
    programas: list[str] | None,
) -> tuple[bytes, str]:
    from consolidado.core.parcializado import excel_parcializado_bytes, nombre_excel_parcializado

    meta = obtener_version(version_id, PROJECT_ROOT)
    if meta is None:
        raise ValueError(f"No existe la versión #{version_id}.")
    df = cargar_dataframe_version(version_id, PROJECT_ROOT)
    elegidas = [p for p in (programas or []) if str(p).strip()]
    contenido = excel_parcializado_bytes(
        df,
        columnas=columnas,
        programas=elegidas or None,
        meta=meta,
    )
    nombre = nombre_excel_parcializado(
        periodo=meta.get("periodo"),
        fecha_version=meta.get("fecha_version"),
        programas=elegidas or None,
    )
    n_filas = conteo_parcializado(version_id, elegidas or None)
    registrar_modificacion(
        accion="parcializado",
        resumen=(
            f"Descargó Excel parcializado de la versión #{version_id} "
            f"({len(columnas)} columnas, {n_filas} filas"
            + (f", {len(elegidas)} carrera(s)" if elegidas else ", todas las carreras")
            + ")"
        ),
        entidad="version",
        identificacion=str(version_id),
        version_despues=version_id,
    )
    return contenido, nombre
