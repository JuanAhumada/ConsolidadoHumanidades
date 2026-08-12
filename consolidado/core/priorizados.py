from __future__ import annotations

from pathlib import Path

import polars as pl

from consolidado.config.settings import carpeta_excels
from consolidado.core.archivos import (
    _leer_hoja_datos,
    _preparar_archivo_interno,
    procesar_tabla_priorizados,
)
from consolidado.core.constants import (
    COL_NOMBRE,
    MOTIVO_PRIORIZADO_INTERNO,
    MOTIVO_PRIORIZADO_PROPIO,
    _TIPOS_FUENTE_AUXILIARES,
)
from consolidado.core.excel_io import _leer_hoja_excel, _nombres_hojas_excel
from consolidado.core.priorizado_enriquecido import _col_por_palabras
from consolidado.core.columnas import construir_mapa_columnas
from consolidado.core.fusion import filtrar_filas_con_telefono, filtrar_filas_programa_excluido
from consolidado.core.normalizacion import (
    _mapa_norm_a_real,
    _str_celda,
    combinar_valores,
    normalizar_encabezado,
    normalizar_id,
)
from consolidado.storage.contactados import cargar_ids_contactados
from consolidado.storage.priorizados import cargar_priorizados_propios

_ORIGEN_PRIORIZADO_INTERNO = "Priorizado interno (Psicología)"

_HOJAS_PRIORIZADOS_INTERNOS = (
    "casos priorizados",
    "priorizados internos",
    "priorizado interno",
    "caso priorizado",
)


def _norm_nombre_hoja(nombre: str) -> str:
    return normalizar_encabezado(nombre).replace("_", " ")


def _elegir_hoja_priorizados_internos(ruta: Path) -> str | None:
    """Hoja de casos internos en el Excel de Priorizado Psicología."""
    nombres = _nombres_hojas_excel(ruta)
    for sn in nombres:
        norm = _norm_nombre_hoja(sn)
        if norm in _HOJAS_PRIORIZADOS_INTERNOS:
            return sn
    for sn in nombres:
        norm = _norm_nombre_hoja(sn)
        if any(
            patron in norm
            for patron in ("casos priorizados", "priorizados internos", "priorizado interno")
        ):
            return sn
    return None


def procesar_priorizados_internos_psi(ruta: Path) -> list[dict]:
    """
    Lee la hoja de casos internos del Excel de Psicología.
    Devuelve entradas con motivo PRIORIZADO INTERNO y detalle desde observaciones.
    """
    hoja = _elegir_hoja_priorizados_internos(ruta)
    if not hoja:
        return []

    df = _leer_hoja_excel(ruta, hoja)
    if df.height == 0:
        return []

    cols = list(df.columns)
    m = construir_mapa_columnas(cols)
    if "identificacion" not in m:
        return []

    col_id = m["identificacion"]
    nr = _mapa_norm_a_real(cols)
    col_obs = nr.get(normalizar_encabezado("OBSERVACIONES DE SEGUIMIENTO"))
    if not col_obs:
        col_obs = _col_por_palabras(cols, "observaciones", "seguimiento")

    mapa: dict[str, dict] = {}
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row[col_id])
        if not id_key:
            continue
        detalle = _str_celda(row[col_obs]) if col_obs else ""
        if id_key not in mapa:
            mapa[id_key] = {
                "identificacion": id_key,
                "motivo": MOTIVO_PRIORIZADO_INTERNO,
                "detalle": detalle or None,
            }
            continue
        existente = mapa[id_key]
        existente["detalle"] = combinar_valores(
            [existente.get("detalle"), detalle], separador=" | "
        ) or None

    return list(mapa.values())


def cargar_priorizados_internos_psi(cfg: dict, base: Path) -> list[dict]:
    """Priorizados internos desde la hoja de casos del Excel de Psicología."""
    slot = next(
        (s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == "bd_prio_psi"),
        None,
    )
    if not slot:
        return []
    p = carpeta_excels(cfg, base) / slot.get("nombre_guardado", "")
    if not p.is_file():
        return []
    try:
        return procesar_priorizados_internos_psi(p)
    except Exception:
        return []


def _unificar_priorizados_propios(
    propios_json: list[dict],
    internos_excel: list[dict],
) -> list[dict]:
    mapa: dict[str, dict] = {}
    for p in propios_json:
        key = normalizar_id(p.get("identificacion", ""))
        if key:
            mapa[key] = dict(p)
    for p in internos_excel:
        key = normalizar_id(p.get("identificacion", ""))
        if not key:
            continue
        if key in mapa:
            existente = mapa[key]
            existente["motivo"] = combinar_valores(
                [existente.get("motivo"), p.get("motivo")], separador=", "
            )
            existente["detalle"] = combinar_valores(
                [existente.get("detalle"), p.get("detalle")], separador=" | "
            )
        else:
            mapa[key] = dict(p)
    return list(mapa.values())


def _nombre_desde_fila(row: dict, m: dict[str, str], nr: dict[str, str]) -> str:
    if "nombre_estudiante" in m:
        col_nom = m["nombre_estudiante"]
        if "apellidos" in nr and "nombres" in nr and nr["nombres"] == col_nom:
            return (
                f"{_str_celda(row.get(nr['nombres']))} "
                f"{_str_celda(row.get(nr['apellidos']))}"
            ).strip()
        return _str_celda(row.get(col_nom))
    if "nombres" in nr and "apellidos" in nr:
        partes = [_str_celda(row.get(nr["nombres"]))]
        if "pri apellido" in nr:
            partes.append(_str_celda(row.get(nr["pri apellido"])))
        if "seg apellido" in nr:
            partes.append(_str_celda(row.get(nr["seg apellido"])))
        elif "apellidos" in nr:
            partes.append(_str_celda(row.get(nr["apellidos"])))
        return " ".join(p for p in partes if p).strip()
    if "nombre" in nr:
        partes = [_str_celda(row.get(nr["nombre"]))]
        if "pri apellido" in nr:
            partes.append(_str_celda(row.get(nr["pri apellido"])))
        if "seg apellido" in nr:
            partes.append(_str_celda(row.get(nr["seg apellido"])))
        return " ".join(p for p in partes if p).strip()
    return ""

def _mapa_nombres_estudiantes(cfg: dict, base: Path) -> dict[str, str]:
    """Identificación normalizada -> nombre y apellidos desde las fuentes cargadas."""
    mapa: dict[str, str] = {}
    carpeta = carpeta_excels(cfg, base)
    for slot in cfg.get("archivos_fuente", []):
        tipo = slot.get("tipo", "")
        if tipo in _TIPOS_FUENTE_AUXILIARES:
            continue
        p = carpeta / slot.get("nombre_guardado", "")
        if not p.is_file():
            continue
        try:
            if tipo == "bd2":
                df_raw = _leer_hoja_datos(p, tipo="bd2", hoja=slot.get("hoja"))
            else:
                df_raw, _ = _preparar_archivo_interno(
                    p, tipo=tipo, hoja=slot.get("hoja")
                )
                if COL_NOMBRE in df_raw.columns:
                    for row in df_raw.iter_rows(named=True):
                        key = normalizar_id(row.get("Identificación"))
                        nom = _str_celda(row.get(COL_NOMBRE))
                        if key and nom and (key not in mapa or len(nom) > len(mapa[key])):
                            mapa[key] = nom
                    continue
                df_raw = _leer_hoja_datos(p, tipo=tipo, hoja=slot.get("hoja"))
        except Exception:
            continue
        m = construir_mapa_columnas(list(df_raw.columns))
        nr = _mapa_norm_a_real(list(df_raw.columns))
        if "identificacion" not in m:
            continue
        col_id = m["identificacion"]
        for row in df_raw.iter_rows(named=True):
            key = normalizar_id(row[col_id])
            if not key:
                continue
            nombre = _nombre_desde_fila(row, m, nr)
            if nombre and (key not in mapa or len(nombre) > len(mapa[key])):
                mapa[key] = nombre
    return mapa

def buscar_estudiantes_en_fuentes(
    cfg: dict,
    base: Path,
    termino: str,
    *,
    limite: int = 30,
) -> list[dict]:
    """Busca por cédula o nombre en los archivos fuente (excepto BD priorizados)."""
    termino = termino.strip()
    if not termino:
        return []
    termino_low = termino.lower()
    termino_id = normalizar_id(termino)
    carpeta = carpeta_excels(cfg, base)
    vistos: set[str] = set()
    resultados: list[dict] = []

    for slot in cfg.get("archivos_fuente", []):
        if slot.get("tipo") in ("bd2", *_TIPOS_FUENTE_AUXILIARES):
            continue
        p = carpeta / slot.get("nombre_guardado", "")
        if not p.is_file():
            continue
        try:
            df, _ = _preparar_archivo_interno(
                p, tipo=slot.get("tipo"), hoja=slot.get("hoja")
            )
        except Exception:
            continue
        df = filtrar_filas_programa_excluido(df)
        df = filtrar_filas_con_telefono(df)
        for row in df.iter_rows(named=True):
            id_key = normalizar_id(row.get("Identificación"))
            nombre = str(row.get(COL_NOMBRE) or "")
            if not id_key or id_key in vistos:
                continue
            coincide = False
            if termino_id and (id_key == termino_id or termino_id in id_key):
                coincide = True
            elif termino_low in nombre.lower():
                coincide = True
            if not coincide:
                continue
            vistos.add(id_key)
            resultados.append(
                {
                    "identificacion": id_key,
                    "nombre": nombre,
                    "programa": row.get("Programa"),
                }
            )
            if len(resultados) >= limite:
                return resultados
    return resultados

def aplicar_priorizados_propios(
    consolidado: pl.DataFrame,
    propios: list[dict],
) -> pl.DataFrame:
    """Marca en el consolidado los estudiantes de la lista propia persistente."""
    if not propios or consolidado.height == 0:
        return consolidado

    mapa = {
        normalizar_id(p.get("identificacion", "")): p
        for p in propios
        if normalizar_id(p.get("identificacion", ""))
    }
    if not mapa:
        return consolidado

    if "Priorizado" in consolidado.columns:
        priorizado_vals = consolidado.get_column("Priorizado").to_list()
    else:
        priorizado_vals = [None] * consolidado.height
    motivo_vals = (
        consolidado.get_column("Motivo Prio.").cast(pl.Utf8).to_list()
        if "Motivo Prio." in consolidado.columns
        else [None] * consolidado.height
    )
    detalle_vals = (
        consolidado.get_column("Detalle GPrio.").cast(pl.Utf8).to_list()
        if "Detalle GPrio." in consolidado.columns
        else [None] * consolidado.height
    )
    ids = consolidado.get_column("Identificación").to_list()

    for i, id_val in enumerate(ids):
        key = normalizar_id(id_val)
        if key not in mapa:
            continue
        p = mapa[key]
        priorizado_vals[i] = True
        motivo_vals[i] = p.get("motivo") or MOTIVO_PRIORIZADO_PROPIO
        det = p.get("detalle")
        if det:
            detalle_vals[i] = det

    return consolidado.with_columns(
        pl.Series("Priorizado", priorizado_vals, dtype=pl.Boolean),
        pl.Series("Motivo Prio.", motivo_vals, dtype=pl.Utf8),
        pl.Series("Detalle GPrio.", detalle_vals, dtype=pl.Utf8),
    )

def _fusionar_entrada_vista(vista: list[dict], ids_vista: set[str], entrada: dict) -> None:
    key = normalizar_id(entrada.get("identificacion", ""))
    if not key:
        return
    if key in ids_vista:
        for v in vista:
            if normalizar_id(v.get("identificacion", "")) != key:
                continue
            if not v.get("nombre") and entrada.get("nombre"):
                v["nombre"] = entrada["nombre"]
            v["motivo"] = combinar_valores(
                [v.get("motivo"), entrada.get("motivo")], separador=", "
            )
            v["detalle"] = combinar_valores(
                [v.get("detalle"), entrada.get("detalle")], separador=" | "
            )
            v["origen"] = combinar_valores(
                [v.get("origen"), entrada.get("origen")], separador=" + "
            )
            if entrada.get("es_propio"):
                v["es_propio"] = True
            break
        return
    ids_vista.add(key)
    vista.append(entrada)


def obtener_lista_priorizados_vista(cfg: dict, base: Path) -> list[dict]:
    """Lista unificada para la interfaz: BD2 + internos Psicología + priorizados propios."""
    vista: list[dict] = []
    ids_vista: set[str] = set()
    id_to_name = _mapa_nombres_estudiantes(cfg, base)
    ids_contactados = cargar_ids_contactados(base)
    carpeta = carpeta_excels(cfg, base)
    slot_bd2 = next((s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == "bd2"), None)

    if slot_bd2:
        p = carpeta / slot_bd2.get("nombre_guardado", "")
        if p.is_file():
            try:
                prio = procesar_tabla_priorizados(p, tipo="bd2", hoja=slot_bd2.get("hoja"))
                for row in prio.iter_rows(named=True):
                    key = row["_id_key"]
                    _fusionar_entrada_vista(
                        vista,
                        ids_vista,
                        {
                            "identificacion": key,
                            "nombre": id_to_name.get(key, ""),
                            "motivo": row.get("Motivo Prio.") or "",
                            "detalle": row.get("Detalle GPrio.") or "",
                            "origen": "Grupos priorizados",
                            "es_propio": False,
                        },
                    )
            except Exception:
                pass

    slot_psi = next(
        (s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == "bd_prio_psi"),
        None,
    )
    if slot_psi:
        p_psi = carpeta / slot_psi.get("nombre_guardado", "")
        if p_psi.is_file():
            try:
                for p in procesar_priorizados_internos_psi(p_psi):
                    key = normalizar_id(p.get("identificacion", ""))
                    if not key:
                        continue
                    _fusionar_entrada_vista(
                        vista,
                        ids_vista,
                        {
                            "identificacion": key,
                            "nombre": id_to_name.get(key, ""),
                            "motivo": p.get("motivo") or MOTIVO_PRIORIZADO_INTERNO,
                            "detalle": p.get("detalle") or "",
                            "origen": _ORIGEN_PRIORIZADO_INTERNO,
                            "es_propio": False,
                        },
                    )
            except Exception:
                pass

    for p in cargar_priorizados_propios(base):
        key = normalizar_id(p.get("identificacion", ""))
        if not key:
            continue
        _fusionar_entrada_vista(
            vista,
            ids_vista,
            {
                "identificacion": key,
                "nombre": p.get("nombre") or id_to_name.get(key, ""),
                "motivo": p.get("motivo") or MOTIVO_PRIORIZADO_PROPIO,
                "detalle": p.get("detalle") or "",
                "origen": "Priorizado propio",
                "es_propio": True,
            },
        )

    for v in vista:
        if not v.get("nombre"):
            key = normalizar_id(v.get("identificacion", ""))
            v["nombre"] = id_to_name.get(key, "")
        v.setdefault("es_propio", v.get("origen") == "Priorizado propio")
        key = normalizar_id(v.get("identificacion", ""))
        v["contactado"] = key in ids_contactados
    return vista

