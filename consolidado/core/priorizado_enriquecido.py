"""Procesamiento de archivos de priorizado enriquecido (ajustes y activación de ruta)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl

from consolidado.config.settings import COLUMNAS_PRIORIZADO_ENRIQUECIDO, carpeta_excels
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.columnas import _buscar_columna_por_aliases
from consolidado.core.constants import (
    COL_ACTIVACION_RUTA,
    COL_AJUSTE_RAZONABLE,
    COL_FECHA_ACTIVACION_RUTA,
    COL_FECHA_AJUSTE,
)
from consolidado.core.normalizacion import (
    _es_nulo,
    _es_valor_true,
    _str_celda,
    normalizar_encabezado,
    normalizar_id,
)


def _col_por_palabras(columns: list[str], *palabras: str) -> str | None:
    for col in columns:
        norm = normalizar_encabezado(col)
        if all(p in norm for p in palabras):
            return col
    return None


def formatear_fecha_dd_mm_aa(val) -> str | None:
    """Formato corto dd/mm/aa para fechas de ajuste o activación."""
    if _es_nulo(val):
        return None
    if isinstance(val, datetime):
        d = val.date()
    elif isinstance(val, date):
        d = val
    else:
        texto = _str_celda(val)
        if not texto:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                d = datetime.strptime(texto[:19], fmt).date()
                break
            except ValueError:
                continue
        else:
            return texto if "/" in texto else None
    return f"{d.day:02d}/{d.month:02d}/{str(d.year)[-2:]}"


def _es_si_o_verdadero(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("si", "sí", "true", "1", "verdadero", "x")


def _tiene_ajuste_razonable(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return val
    if _es_valor_true(val):
        return True
    s = str(val).strip().upper()
    return "AJUSTE" in s and "RAZONABLE" in s.replace("Ó", "O")


def _tiene_activacion_ruta(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return val
    if _es_si_o_verdadero(val):
        return True
    s = str(val).strip().upper()
    return "RUTA" in s and ("ACTIV" in s or "ATENCION" in s or "ATENCIÓN" in s)


def _combinar_bool(valores: list) -> bool | None:
    if any(_es_si_o_verdadero(v) or v is True for v in valores if not _es_nulo(v)):
        return True
    if any(not _es_nulo(v) for v in valores):
        return False
    return None


def _combinar_fecha(valores: list) -> str | None:
    fechas = [formatear_fecha_dd_mm_aa(v) for v in valores if not _es_nulo(v)]
    fechas = [f for f in fechas if f]
    return fechas[0] if fechas else None


def _agregar_registro(
    mapa: dict[str, dict],
    id_key: str,
    *,
    ajuste: bool | None = None,
    fecha_ajuste: str | None = None,
    activacion: bool | None = None,
    fecha_activacion: str | None = None,
) -> None:
    if not id_key:
        return
    if id_key not in mapa:
        mapa[id_key] = {
            "_id_key": id_key,
            COL_AJUSTE_RAZONABLE: None,
            COL_FECHA_AJUSTE: None,
            COL_ACTIVACION_RUTA: None,
            COL_FECHA_ACTIVACION_RUTA: None,
            "_ajustes": [],
            "_fechas_ajuste": [],
            "_activaciones": [],
            "_fechas_act": [],
        }
    fila = mapa[id_key]
    if ajuste is not None:
        fila["_ajustes"].append(ajuste)
    if fecha_ajuste:
        fila["_fechas_ajuste"].append(fecha_ajuste)
    if activacion is not None:
        fila["_activaciones"].append(activacion)
    if fecha_activacion:
        fila["_fechas_act"].append(fecha_activacion)


def _finalizar_mapa(mapa: dict[str, dict]) -> pl.DataFrame:
    if not mapa:
        return pl.DataFrame(
            schema={
                "_id_key": pl.Utf8,
                COL_AJUSTE_RAZONABLE: pl.Boolean,
                COL_FECHA_AJUSTE: pl.Utf8,
                COL_ACTIVACION_RUTA: pl.Boolean,
                COL_FECHA_ACTIVACION_RUTA: pl.Utf8,
            }
        )
    filas: list[dict] = []
    for fila in mapa.values():
        filas.append(
            {
                "_id_key": fila["_id_key"],
                COL_AJUSTE_RAZONABLE: _combinar_bool(fila["_ajustes"]),
                COL_FECHA_AJUSTE: _combinar_fecha(fila["_fechas_ajuste"]),
                COL_ACTIVACION_RUTA: _combinar_bool(fila["_activaciones"]),
                COL_FECHA_ACTIVACION_RUTA: _combinar_fecha(fila["_fechas_act"]),
            }
        )
    return pl.DataFrame(filas)


def procesar_archivo_prio_psi(ruta: Path, *, hoja: str | None = None) -> pl.DataFrame:
    df = _leer_hoja_datos(ruta, tipo="bd_prio_psi", hoja=hoja)
    cols = list(df.columns)
    col_id = _buscar_columna_por_aliases(
        cols, ["num identificacion", "identificacion", "identificación", "documento"]
    )
    col_ajuste = _col_por_palabras(cols, "ajuste", "razonable") or _col_por_palabras(
        cols, "ajuste", "recomendacion"
    )
    col_fecha_ajuste = _col_por_palabras(cols, "fecha", "solicitud") or _col_por_palabras(
        cols, "fecha", "ajuste"
    )
    col_activacion = _col_por_palabras(cols, "activacion", "ruta") or _col_por_palabras(
        cols, "activación", "ruta"
    )
    col_fecha_act = _col_por_palabras(cols, "fecha", "activacion") or _col_por_palabras(
        cols, "fecha", "act"
    )
    if not col_id:
        return _finalizar_mapa({})

    mapa: dict[str, dict] = {}
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row[col_id])
        _agregar_registro(
            mapa,
            id_key,
            ajuste=_tiene_ajuste_razonable(row[col_ajuste]) if col_ajuste else None,
            fecha_ajuste=formatear_fecha_dd_mm_aa(row[col_fecha_ajuste])
            if col_fecha_ajuste
            else None,
            activacion=_es_si_o_verdadero(row[col_activacion]) if col_activacion else None,
            fecha_activacion=formatear_fecha_dd_mm_aa(row[col_fecha_act])
            if col_fecha_act
            else None,
        )
    return _finalizar_mapa(mapa)


def procesar_archivo_prio_lic(ruta: Path, *, hoja: str | None = None) -> pl.DataFrame:
    df = _leer_hoja_datos(ruta, tipo="bd_prio_lic", hoja=hoja)
    cols = list(df.columns)
    col_id = _buscar_columna_por_aliases(
        cols, ["identificacion", "identificación", "documento", "cedula", "cédula"]
    )
    col_ajuste = _col_por_palabras(cols, "ajustes", "razonables") or _col_por_palabras(
        cols, "ajuste", "razonable"
    )
    col_activacion = _col_por_palabras(cols, "ruta", "atencion") or _col_por_palabras(
        cols, "ruta", "vida"
    )
    if not col_id:
        return _finalizar_mapa({})

    mapa: dict[str, dict] = {}
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row[col_id])
        ajuste = None
        if col_ajuste:
            ajuste = _tiene_ajuste_razonable(row[col_ajuste]) or _es_si_o_verdadero(row[col_ajuste])
        activacion = None
        if col_activacion:
            activacion = _es_si_o_verdadero(row[col_activacion]) or _tiene_activacion_ruta(
                row[col_activacion]
            )
        _agregar_registro(mapa, id_key, ajuste=ajuste, activacion=activacion)
    return _finalizar_mapa(mapa)


def _fusionar_enriquecidos(dataframes: list[pl.DataFrame]) -> pl.DataFrame:
    if not dataframes:
        return _finalizar_mapa({})
    mapa: dict[str, dict] = {}
    for df in dataframes:
        if df.height == 0:
            continue
        for row in df.iter_rows(named=True):
            id_key = row["_id_key"]
            _agregar_registro(
                mapa,
                id_key,
                ajuste=row.get(COL_AJUSTE_RAZONABLE),
                fecha_ajuste=row.get(COL_FECHA_AJUSTE),
                activacion=row.get(COL_ACTIVACION_RUTA),
                fecha_activacion=row.get(COL_FECHA_ACTIVACION_RUTA),
            )
    return _finalizar_mapa(mapa)


def _cargar_priorizado_enriquecido_cfg(cfg: dict, base: Path) -> pl.DataFrame:
    carpeta = carpeta_excels(cfg, base)
    partes: list[pl.DataFrame] = []
    for tipo, procesador in (
        ("bd_prio_psi", procesar_archivo_prio_psi),
        ("bd_prio_lic", procesar_archivo_prio_lic),
    ):
        slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == tipo), None)
        if not slot:
            continue
        p = carpeta / slot.get("nombre_guardado", "")
        if not p.is_file():
            continue
        try:
            partes.append(procesador(p, hoja=slot.get("hoja")))
        except Exception:
            continue
    return _fusionar_enriquecidos(partes)


def aplicar_priorizado_enriquecido(consolidado: pl.DataFrame, enriquecido: pl.DataFrame) -> pl.DataFrame:
    for col in COLUMNAS_PRIORIZADO_ENRIQUECIDO:
        if col not in consolidado.columns:
            consolidado = consolidado.with_columns(pl.lit(None).alias(col))

    if enriquecido.height == 0:
        return consolidado

    cols_reservadas = [c for c in COLUMNAS_PRIORIZADO_ENRIQUECIDO if c in consolidado.columns]
    base = consolidado.drop(cols_reservadas) if cols_reservadas else consolidado

    resultado = base.with_columns(
        pl.col("Identificación")
        .map_elements(normalizar_id, return_dtype=pl.Utf8)
        .alias("_id_key")
    )
    resultado = resultado.join(enriquecido, on="_id_key", how="left").drop("_id_key")
    for col in COLUMNAS_PRIORIZADO_ENRIQUECIDO:
        if col not in resultado.columns:
            resultado = resultado.with_columns(pl.lit(None).alias(col))
    return resultado
