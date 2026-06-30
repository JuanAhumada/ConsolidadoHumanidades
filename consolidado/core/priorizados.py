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
    MOTIVO_PRIORIZADO_PROPIO,
    _TIPOS_FUENTE_AUXILIARES,
)
from consolidado.core.columnas import construir_mapa_columnas
from consolidado.core.fusion import filtrar_filas_con_telefono, filtrar_filas_programa_excluido
from consolidado.core.normalizacion import (
    _mapa_norm_a_real,
    _str_celda,
    combinar_valores,
    normalizar_id,
)
from consolidado.storage.priorizados import cargar_priorizados_propios


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

    filas: list[dict] = []
    for row in consolidado.iter_rows(named=True):
        fila = dict(row)
        key = normalizar_id(fila.get("Identificación"))
        if key in mapa:
            p = mapa[key]
            fila["Priorizado"] = True
            fila["Motivo Prio."] = p.get("motivo") or MOTIVO_PRIORIZADO_PROPIO
            det = p.get("detalle")
            fila["Detalle GPrio."] = det if det else fila.get("Detalle GPrio.")
        filas.append(fila)
    return pl.DataFrame(filas)

def obtener_lista_priorizados_vista(cfg: dict, base: Path) -> list[dict]:
    """Lista unificada para la interfaz: BD2 + priorizados propios."""
    vista: list[dict] = []
    id_to_name = _mapa_nombres_estudiantes(cfg, base)
    carpeta = carpeta_excels(cfg, base)
    slot_bd2 = next((s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == "bd2"), None)

    if slot_bd2:
        p = carpeta / slot_bd2.get("nombre_guardado", "")
        if p.is_file():
            try:
                prio = procesar_tabla_priorizados(p, tipo="bd2", hoja=slot_bd2.get("hoja"))
                for row in prio.iter_rows(named=True):
                    key = row["_id_key"]
                    vista.append(
                        {
                            "identificacion": key,
                            "nombre": id_to_name.get(key, ""),
                            "motivo": row.get("Motivo Prio.") or "",
                            "detalle": row.get("Detalle GPrio.") or "",
                            "origen": "Grupos priorizados",
                            "es_propio": False,
                        }
                    )
            except Exception:
                pass

    ids_vista = {normalizar_id(v["identificacion"]) for v in vista}
    for p in cargar_priorizados_propios(base):
        key = normalizar_id(p.get("identificacion", ""))
        if not key:
            continue
        nombre = p.get("nombre") or id_to_name.get(key, "")
        entrada = {
            "identificacion": key,
            "nombre": nombre,
            "motivo": p.get("motivo") or MOTIVO_PRIORIZADO_PROPIO,
            "detalle": p.get("detalle") or "",
            "origen": "Priorizado propio",
            "es_propio": True,
        }
        if key in ids_vista:
            for v in vista:
                if normalizar_id(v["identificacion"]) == key:
                    if not v.get("nombre") and nombre:
                        v["nombre"] = nombre
                    v["motivo"] = combinar_valores(
                        [v.get("motivo"), entrada["motivo"]], separador=", "
                    )
                    v["detalle"] = combinar_valores(
                        [v.get("detalle"), entrada["detalle"]], separador=" | "
                    )
                    v["origen"] = combinar_valores(
                        [v.get("origen"), entrada["origen"]], separador=" + "
                    )
                    v["es_propio"] = True
                    break
        else:
            vista.append(entrada)
    for v in vista:
        if not v.get("nombre"):
            key = normalizar_id(v.get("identificacion", ""))
            v["nombre"] = id_to_name.get(key, "")
        v.setdefault("es_propio", v.get("origen") == "Priorizado propio")
    return vista

