from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from consolidado.config.settings import COLUMNAS_ALERTAS, carpeta_excels
from consolidado.core.archivos import _elegir_hoja_datos
from consolidado.core.excel_io import _leer_hoja_excel
from consolidado.core.columnas import _buscar_columna_por_aliases
from consolidado.core.constants import (
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
)
from consolidado.core.normalizacion import (
    _es_nulo,
    combinar_valores,
    normalizar_encabezado,
    normalizar_id,
)


def _columnas_por_fase(fase: str) -> tuple[str, str]:
    if fase == "final":
        return COL_NUM_ALERTA_FINAL, COL_TIPO_ALERTA_FINAL
    return COL_NUM_ALERTA_INICIAL, COL_TIPO_ALERTA_INICIAL


def _columna_num_alertas(columns: list[str]) -> str | None:
    for col in columns:
        norm = normalizar_encabezado(col)
        norm_limpio = re.sub(r"[^a-z0-9 ]", "", norm).strip()
        if norm_limpio in ("n alertas", "num alertas", "no alertas"):
            return col
        if norm_limpio.startswith("n") and "alertas" in norm_limpio:
            return col
    return None


def _es_alerta_activa(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return int(val) == 1
    s = str(val).strip().lower()
    if s in ("1", "1.0", "true", "si", "sí"):
        return True
    try:
        return int(float(s)) == 1
    except ValueError:
        return False


def _parsear_num_alertas(val) -> int | None:
    if _es_nulo(val):
        return None
    try:
        return int(float(str(val).strip()))
    except ValueError:
        return None


def procesar_archivo_alertas(
    ruta: Path,
    *,
    hoja: str | None = None,
    fase: str = "inicial",
) -> pl.DataFrame:
    """Lee un Excel de alertas y devuelve columnas según fase (inicial/final)."""
    col_num, col_tipo = _columnas_por_fase(fase)
    nombre_hoja = hoja or _elegir_hoja_datos(ruta, tipo="bd_alertas_com")
    df = _leer_hoja_excel(ruta, nombre_hoja)
    cols = list(df.columns)
    col_cedula = _buscar_columna_por_aliases(
        cols, ["cedula", "cédula", "identificacion", "identificación", "documento"]
    )
    col_num_src = _columna_num_alertas(cols)
    schema = {"_id_key": pl.Utf8, col_num: pl.Int64, col_tipo: pl.Utf8}
    if not col_cedula or not col_num_src:
        return pl.DataFrame(schema=schema)

    idx_num = cols.index(col_num_src)
    cols_tipos = cols[idx_num + 1 :]
    registros: list[dict] = []
    for row in df.iter_rows(named=True):
        key = normalizar_id(row[col_cedula])
        if not key:
            continue
        tipos = [str(col).strip() for col in cols_tipos if _es_alerta_activa(row[col])]
        num = _parsear_num_alertas(row[col_num_src])
        registros.append(
            {
                "_id_key": key,
                col_num: num,
                col_tipo: " | ".join(tipos) if tipos else None,
            }
        )

    if not registros:
        return pl.DataFrame(schema=schema)

    tmp = pl.DataFrame(registros)
    filas: list[dict] = []
    for key in tmp["_id_key"].unique().sort().to_list():
        grp = tmp.filter(pl.col("_id_key") == key)
        nums = [n for n in grp[col_num].to_list() if n is not None]
        num_total = sum(nums) if nums else None
        tipos = combinar_valores(grp[col_tipo].to_list(), separador=" | ")
        filas.append({"_id_key": key, col_num: num_total, col_tipo: tipos or None})
    return pl.DataFrame(filas)


def _fusionar_alertas_fase(dataframes: list[pl.DataFrame], fase: str) -> pl.DataFrame:
    col_num, col_tipo = _columnas_por_fase(fase)
    schema = {"_id_key": pl.Utf8, col_num: pl.Int64, col_tipo: pl.Utf8}
    if not dataframes:
        return pl.DataFrame(schema=schema)
    todo = pl.concat(dataframes, how="diagonal_relaxed")
    filas: list[dict] = []
    for key in todo["_id_key"].unique().sort().to_list():
        grp = todo.filter(pl.col("_id_key") == key)
        nums = [n for n in grp[col_num].to_list() if n is not None]
        num_total = sum(nums) if nums else None
        tipos = combinar_valores(grp[col_tipo].to_list(), separador=" | ")
        filas.append({"_id_key": key, col_num: num_total, col_tipo: tipos or None})
    return pl.DataFrame(filas)


def _aplicar_alertas(consolidado: pl.DataFrame, alertas: pl.DataFrame) -> pl.DataFrame:
    for col in COLUMNAS_ALERTAS:
        if col not in consolidado.columns:
            consolidado = consolidado.with_columns(pl.lit(None).alias(col))

    if alertas.height == 0:
        return consolidado

    cols_reservadas = [c for c in COLUMNAS_ALERTAS if c in consolidado.columns]
    base = consolidado.drop(cols_reservadas) if cols_reservadas else consolidado
    for col in (f"{c}_right" for c in COLUMNAS_ALERTAS):
        if col in base.columns:
            base = base.drop(col)

    resultado = base.with_columns(
        pl.col("Identificación")
        .map_elements(normalizar_id, return_dtype=pl.Utf8)
        .alias("_id_key")
    )
    resultado = resultado.join(alertas, on="_id_key", how="left").drop("_id_key")
    for col in COLUMNAS_ALERTAS:
        if col not in resultado.columns:
            resultado = resultado.with_columns(pl.lit(None).alias(col))
    return resultado


def _cargar_alertas_cfg(
    cfg: dict, base: Path, carpeta: Path | None = None
) -> pl.DataFrame:
    carpeta = Path(carpeta) if carpeta is not None else carpeta_excels(cfg, base)
    por_fase: dict[str, list[pl.DataFrame]] = {"inicial": [], "final": []}
    for slot in cfg.get("archivos_fuente", []):
        tipo = slot.get("tipo")
        if tipo not in ("bd_alertas_com", "bd_alertas_psi"):
            continue
        fase = slot.get("fase", "inicial")
        if fase not in por_fase:
            fase = "inicial"
        p = carpeta / slot.get("nombre_guardado", "")
        if not p.is_file():
            continue
        try:
            por_fase[fase].append(
                procesar_archivo_alertas(p, hoja=slot.get("hoja"), fase=fase)
            )
        except Exception:
            continue

    inicial = _fusionar_alertas_fase(por_fase["inicial"], "inicial")
    final = _fusionar_alertas_fase(por_fase["final"], "final")

    if inicial.height == 0 and final.height == 0:
        return pl.DataFrame(
            schema={
                "_id_key": pl.Utf8,
                COL_NUM_ALERTA_INICIAL: pl.Int64,
                COL_TIPO_ALERTA_INICIAL: pl.Utf8,
                COL_NUM_ALERTA_FINAL: pl.Int64,
                COL_TIPO_ALERTA_FINAL: pl.Utf8,
            }
        )

    if inicial.height == 0:
        return final
    if final.height == 0:
        return inicial
    return inicial.join(final, on="_id_key", how="outer")
