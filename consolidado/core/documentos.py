from __future__ import annotations

from pathlib import Path

import polars as pl

from consolidado.config.settings import carpeta_excels
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.excel_io import _leer_hoja_excel
from consolidado.core.columnas import _buscar_columna_por_aliases
from consolidado.core.constants import _ALIASES_RUNTIME
from consolidado.core.fusion import filtrar_filas_programas_permitidos
from consolidado.core.normalizacion import combinar_valores, normalizar_id
def procesar_documento_adicional(ruta: Path, doc: dict) -> pl.DataFrame:
    """Lee un Excel adicional y devuelve columnas configuradas indexadas por _id_key."""
    hoja = doc.get("hoja")
    if hoja:
        df = _leer_hoja_excel(ruta, hoja)
    else:
        df = _leer_hoja_datos(ruta)

    if doc.get("filtrar_programas"):
        df = filtrar_filas_programas_permitidos(df)

    id_aliases = doc.get("columna_identificacion_aliases") or _ALIASES_RUNTIME.get(
        "identificacion", []
    )
    col_id = _buscar_columna_por_aliases(list(df.columns), id_aliases)
    if not col_id:
        raise ValueError(
            f"{doc.get('titulo', ruta.name)}: no se encontró columna de identificación."
        )

    columnas_doc = doc.get("columnas", [])
    salidas = [c["salida"] for c in columnas_doc if c.get("salida")]
    if not salidas:
        return pl.DataFrame(schema={"_id_key": pl.Utf8})

    registros: list[dict] = []
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row[col_id])
        if not id_key:
            continue
        fila: dict = {"_id_key": id_key}
        for col_def in columnas_doc:
            salida = col_def.get("salida")
            if not salida:
                continue
            aliases = col_def.get("aliases", [])
            src = _buscar_columna_por_aliases(list(df.columns), aliases)
            fila[salida] = row[src] if src else None
        registros.append(fila)

    if not registros:
        return pl.DataFrame(schema={"_id_key": pl.Utf8, **{c: pl.Utf8 for c in salidas}})

    tmp = pl.DataFrame(registros)
    filas: list[dict] = []
    for key in tmp["_id_key"].unique().sort().to_list():
        grp = tmp.filter(pl.col("_id_key") == key)
        fila: dict = {"_id_key": key}
        for col in salidas:
            fila[col] = combinar_valores(grp[col].to_list()) or None
        filas.append(fila)
    return pl.DataFrame(filas)

def _unir_documentos_adicionales(
    consolidado: pl.DataFrame,
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> pl.DataFrame:
    carpeta = Path(carpeta) if carpeta is not None else carpeta_excels(cfg, base)
    resultado = consolidado.with_columns(
        pl.col("Identificación")
        .map_elements(normalizar_id, return_dtype=pl.Utf8)
        .alias("_id_key")
    )
    columnas_extra: list[str] = []
    for doc in cfg.get("documentos_adicionales", []):
        nombre = doc.get("nombre_guardado")
        if not nombre:
            continue
        ruta = carpeta / nombre
        if not ruta.is_file():
            continue
        extra = procesar_documento_adicional(ruta, doc)
        if extra.height == 0:
            continue
        cols = [c for c in extra.columns if c != "_id_key"]
        columnas_extra.extend(c for c in cols if c not in columnas_extra)
        resultado = resultado.join(extra, on="_id_key", how="left")

    resultado = resultado.drop("_id_key")
    if columnas_extra:
        todas = list(resultado.columns)
        for c in columnas_extra:
            if c not in todas:
                resultado = resultado.with_columns(pl.lit(None).alias(c))
    return resultado

