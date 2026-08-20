"""
Une listados y horarios por identificación.

bd1 y bd12 se combinan; Periodo actual toma el más reciente (no se concatenan
con "|"). El horario se pega a la izquierda del listado filtrado.
"""
from __future__ import annotations

import polars as pl

from consolidado.config.settings import COLUMNAS_PRIORIZADO
from consolidado.core.columnas import (
    alinear_dataframe_salida,
    formatear_dataframe_salida,
)
from consolidado.core.constants import (
    COL_DATOS_CONTACTO,
    COL_FUNCIONARIO_BECA,
    COL_NOMBRE,
    COL_PERIODO_ACTUAL,
    COL_TELEFONO_CELULAR,
    COL_TOTAL_BECA,
    SALIDA_COLUMNAS_LISTADO,
    columnas_materia_horario,
)
from consolidado.core.normalizacion import (
    _combinar_telefonos,
    _cuenta_tildes,
    _es_nulo,
    _es_valor_vacio,
    _mapa_norm_a_real,
    _nombre_valido,
    _preferir_nombre_con_tildes,
    _clave_nombre_unico,
    _primero_no_vacio,
    _telefono_presente,
    combinar_valores,
    combinar_funcionario_beca,
    normalizar_encabezado,
    normalizar_id,
    normalizar_telefono_celda,
    periodo_mas_reciente,
    programa_es_permitido,
    programa_esta_excluido,
    sumar_montos_beca,
)
def _columna_programa(df: pl.DataFrame) -> str | None:
    nr = _mapa_norm_a_real(list(df.columns))
    return nr.get("programa") or nr.get("nom unidad")

def filtrar_filas_programas_permitidos(df: pl.DataFrame) -> pl.DataFrame:
    col = _columna_programa(df)
    if not col:
        return df.head(0)
    return df.filter(pl.col(col).map_elements(programa_es_permitido, return_dtype=pl.Boolean))

def filtrar_filas_con_nombre(df: pl.DataFrame) -> pl.DataFrame:
    """Excluye filas sin nombre de estudiante."""
    if df.height == 0 or COL_NOMBRE not in df.columns:
        return df
    return df.filter(pl.col(COL_NOMBRE).map_elements(_nombre_valido, return_dtype=pl.Boolean))

def deduplicar_por_nombre(df: pl.DataFrame) -> pl.DataFrame:
    """Si un nombre aparece más de una vez, conserva solo la primera fila."""
    if df.height == 0 or COL_NOMBRE not in df.columns:
        return df
    return (
        df.with_row_index("_orden")
        .with_columns(
            pl.col(COL_NOMBRE)
            .map_elements(_clave_nombre_unico, return_dtype=pl.Utf8)
            .alias("_nombre_key")
        )
        .filter(pl.col("_nombre_key") != "")
        .unique(subset=["_nombre_key"], keep="first")
        .sort("_orden")
        .drop("_orden", "_nombre_key")
    )

def filtrar_filas_programa_excluido(df: pl.DataFrame) -> pl.DataFrame:
    """Excluye programas de la lista de exclusión (p. ej. Psicología Villavicencio)."""
    if df.height == 0 or "Programa" not in df.columns:
        return df
    return df.filter(
        ~pl.col("Programa").map_elements(programa_esta_excluido, return_dtype=pl.Boolean)
    )

def filtrar_filas_con_telefono(df: pl.DataFrame) -> pl.DataFrame:
    """Excluye filas sin teléfono celular válido."""
    if df.height == 0 or COL_TELEFONO_CELULAR not in df.columns:
        return df
    return df.filter(
        pl.col(COL_TELEFONO_CELULAR).map_elements(_telefono_presente, return_dtype=pl.Boolean)
    )

def filtrar_filas_consolidado(df: pl.DataFrame) -> pl.DataFrame:
    """Filtros finales del listado consolidado."""
    df = filtrar_filas_programa_excluido(df)
    df = filtrar_filas_con_telefono(df)
    return df

def _combinar_programa(valores: list) -> str | None:
    """Unifica programa: variantes con/sin tilde quedan en un solo valor."""
    candidatos: list[str] = []
    for v in valores:
        if _es_nulo(v):
            continue
        s = str(v).strip()
        if not s:
            continue
        for parte in s.split("|"):
            p = parte.strip()
            if p:
                candidatos.append(p)
    if not candidatos:
        return None
    mejor_por_clave: dict[str, str] = {}
    for s in candidatos:
        clave = normalizar_encabezado(s)
        if not clave:
            continue
        prev = mejor_por_clave.get(clave)
        if prev is None or _cuenta_tildes(s) > _cuenta_tildes(prev) or (
            _cuenta_tildes(s) == _cuenta_tildes(prev) and len(s) > len(prev)
        ):
            mejor_por_clave[clave] = s
    if not mejor_por_clave:
        return None
    elegidos = list(mejor_por_clave.values())
    permitidos = [p for p in elegidos if programa_es_permitido(p)]
    usar = permitidos or elegidos
    if len(usar) == 1:
        return usar[0]
    return " | ".join(usar)


def _combinar_nombre(valores: list) -> str | None:
    """Unifica nombres: un solo valor, el más largo entre equivalentes."""
    candidatos: list[str] = []
    for v in valores:
        if not _nombre_valido(v):
            continue
        s = str(v).strip()
        if s:
            candidatos.append(s)
    if not candidatos:
        return None
    mejor_por_clave: dict[str, str] = {}
    for s in candidatos:
        clave = _clave_nombre_unico(s)
        if not clave:
            continue
        prev = mejor_por_clave.get(clave)
        if prev is None or len(s) > len(prev):
            mejor_por_clave[clave] = s
    if not mejor_por_clave:
        return None
    return max(mejor_por_clave.values(), key=len)

def _valor_contacto_en_grupo(grp: pl.DataFrame, col: str, tipo_fuente: str):
    filas = grp.filter(pl.col("_fuente_tipo") == tipo_fuente)
    if filas.height == 0:
        return None
    for v in filas[col].to_list():
        if _es_valor_vacio(v):
            continue
        if col == COL_TELEFONO_CELULAR:
            return normalizar_telefono_celda(v) or str(v).strip()
        return str(v).strip()
    return None

def _combinar_contacto(grp: pl.DataFrame, col: str) -> str | None:
    """Prioriza contacto de Matriculados activos (bd1); si falta, usa Becas (bd3)."""
    if "_fuente_tipo" not in grp.columns:
        vals = grp[col].to_list()
        if col == COL_TELEFONO_CELULAR:
            merged = _combinar_telefonos(vals)
        else:
            merged = combinar_valores(vals)
        return merged if merged else None
    for tipo in ("bd1", "bd3"):
        v = _valor_contacto_en_grupo(grp, col, tipo)
        if v:
            return v
    vals = grp[col].to_list()
    if col == COL_TELEFONO_CELULAR:
        merged = _combinar_telefonos(vals)
    else:
        merged = combinar_valores(vals)
    return merged if merged else None

def _fusionar_bloques_por_id(
    bloques: list[pl.DataFrame],
    columnas: list[str],
    *,
    omitir_priorizado: bool = False,
) -> pl.DataFrame:
    if not bloques:
        return pl.DataFrame({c: [] for c in columnas})

    todo = pl.concat(bloques, how="diagonal_relaxed")
    filas: list[dict] = []
    for key in todo["_id_key"].unique().sort().to_list():
        grp = todo.filter(pl.col("_id_key") == key)
        fila: dict = {"Identificación": _primero_no_vacio(grp["Identificación"].to_list())}
        if _es_nulo(fila["Identificación"]) or str(fila["Identificación"]).strip() == "":
            fila["Identificación"] = key
        for col in columnas[1:]:
            if omitir_priorizado and col in COLUMNAS_PRIORIZADO:
                continue
            if col == COL_NOMBRE:
                merged = _combinar_nombre(grp[col].to_list())
            elif col == "Programa":
                merged = _combinar_programa(grp[col].to_list())
            elif col in COL_DATOS_CONTACTO:
                merged = _combinar_contacto(grp, col)
            elif col == COL_TOTAL_BECA:
                merged = sumar_montos_beca(grp[col].to_list())
            elif col == COL_FUNCIONARIO_BECA:
                merged = combinar_funcionario_beca(grp[col].to_list())
            elif col == COL_PERIODO_ACTUAL:
                merged = periodo_mas_reciente(grp[col].to_list())
            else:
                vals = grp[col].to_list()
                if col == COL_TELEFONO_CELULAR:
                    merged = _combinar_telefonos(vals)
                else:
                    merged = combinar_valores(vals)
            fila[col] = merged if merged else None
        filas.append(fila)

    return pl.from_dicts(filas, infer_schema_length=None)

def fusionar_por_id(
    partes: list[pl.DataFrame],
    horarios_partes: list[pl.DataFrame],
    priorizados: pl.DataFrame | None = None,
    *,
    columnas_listado: list[str] | None = None,
    columnas_materias: list[str] | None = None,
    tipos_partes: list[str] | None = None,
) -> pl.DataFrame:
    if not partes:
        raise ValueError("No hay archivos para fusionar.")

    cols_listado = columnas_listado or SALIDA_COLUMNAS_LISTADO
    cols_materias = columnas_materias or columnas_materia_horario(1)

    bloques: list[pl.DataFrame] = []
    for i, df in enumerate(partes):
        tipo = tipos_partes[i] if tipos_partes and i < len(tipos_partes) else ""
        d = alinear_dataframe_salida(df, cols_listado).with_columns(
            pl.col("Identificación")
            .map_elements(normalizar_id, return_dtype=pl.Utf8)
            .alias("_id_key"),
            pl.lit(tipo).alias("_fuente_tipo"),
        )
        d = d.filter(pl.col("_id_key") != "")
        if d.height > 0:
            bloques.append(d)

    listado = _fusionar_bloques_por_id(bloques, cols_listado, omitir_priorizado=True)
    listado = filtrar_filas_con_nombre(listado)

    if priorizados is not None and priorizados.height > 0:
        prio = priorizados.with_columns(
            pl.col("_id_key").map_elements(normalizar_id, return_dtype=pl.Utf8).alias("_id_key")
        ).filter(pl.col("_id_key") != "")
        listado = listado.with_columns(
            pl.col("Identificación")
            .map_elements(normalizar_id, return_dtype=pl.Utf8)
            .alias("_id_key")
        )
        listado = listado.join(prio.select(["_id_key", *COLUMNAS_PRIORIZADO]), on="_id_key", how="left")
        listado = listado.drop("_id_key")
    else:
        for col in COLUMNAS_PRIORIZADO:
            if col not in listado.columns:
                listado = listado.with_columns(pl.lit(None).alias(col))

    listado = alinear_dataframe_salida(listado, cols_listado)
    listado = formatear_dataframe_salida(listado)
    listado = listado.sort(
        pl.col("Identificación").map_elements(normalizar_id, return_dtype=pl.Utf8)
    )

    cols_horarios_interno = ["Identificación", *cols_materias]
    bloques_h: list[pl.DataFrame] = []
    for df in horarios_partes:
        if df.height == 0:
            continue
        cols_h = list(cols_horarios_interno)
        if COL_PERIODO_ACTUAL in df.columns and COL_PERIODO_ACTUAL not in cols_h:
            cols_h.append(COL_PERIODO_ACTUAL)
        d = alinear_dataframe_salida(df, cols_h).with_columns(
            pl.col("Identificación")
            .map_elements(normalizar_id, return_dtype=pl.Utf8)
            .alias("_id_key")
        ).filter(pl.col("_id_key") != "")
        if d.height > 0:
            bloques_h.append(d)

    consolidado = listado.with_columns(
        pl.col("Identificación")
        .map_elements(normalizar_id, return_dtype=pl.Utf8)
        .alias("_id_key")
    )

    if bloques_h:
        cols_h_fusion = list(cols_horarios_interno)
        if any(COL_PERIODO_ACTUAL in b.columns for b in bloques_h):
            cols_h_fusion.append(COL_PERIODO_ACTUAL)
        horarios = _fusionar_bloques_por_id(bloques_h, cols_h_fusion)
        horarios = horarios.with_columns(
            pl.col("Identificación")
            .map_elements(normalizar_id, return_dtype=pl.Utf8)
            .alias("_id_key")
        )
        consolidado = consolidado.join(
            horarios.select(["_id_key", *cols_materias]),
            on="_id_key",
            how="left",
        )
        if COL_PERIODO_ACTUAL in horarios.columns:
            consolidado = consolidado.join(
                horarios.select(["_id_key", COL_PERIODO_ACTUAL]).rename(
                    {COL_PERIODO_ACTUAL: "_periodo_h"}
                ),
                on="_id_key",
                how="left",
            )
            consolidado = consolidado.with_columns(
                pl.struct([COL_PERIODO_ACTUAL, "_periodo_h"])
                .map_elements(
                    lambda s: periodo_mas_reciente(
                        [
                            s[COL_PERIODO_ACTUAL] if isinstance(s, dict) else s[0],
                            s["_periodo_h"] if isinstance(s, dict) else s[1],
                        ]
                    ),
                    return_dtype=pl.Utf8,
                )
                .alias(COL_PERIODO_ACTUAL)
            ).drop("_periodo_h")

    consolidado = consolidado.drop("_id_key")
    columnas_final = [*cols_listado, *cols_materias]
    consolidado = alinear_dataframe_salida(consolidado, columnas_final)
    consolidado = deduplicar_por_nombre(consolidado)
    consolidado = filtrar_filas_consolidado(consolidado)
    return consolidado

