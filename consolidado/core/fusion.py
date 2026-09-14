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
    PREFIJO_CLAVE_NOMBRE,
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
    clave_cruce_identificacion,
    clave_fusion_estudiante,
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


def _id_normalizado(val) -> str:
    return clave_cruce_identificacion(val) or normalizar_id(val) or ""


def mapa_nombre_unico_a_id(*dfs: pl.DataFrame) -> dict[str, str]:
    """Nombres que aparecen con exactamente una identificación no vacía."""
    por_nombre: dict[str, set[str]] = {}
    for df in dfs:
        if df is None or df.height == 0 or COL_NOMBRE not in df.columns:
            continue
        tiene_id = "Identificación" in df.columns
        for row in df.iter_rows(named=True):
            nkey = _clave_nombre_unico(row.get(COL_NOMBRE))
            if not nkey:
                continue
            nid = _id_normalizado(row.get("Identificación")) if tiene_id else ""
            if nid:
                por_nombre.setdefault(nkey, set()).add(nid)
    return {k: next(iter(v)) for k, v in por_nombre.items() if len(v) == 1}


def completar_identificacion_por_nombre(
    df: pl.DataFrame,
    mapa: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Rellena Identificación vacía cuando el nombre es único y ya tiene ID en otra fila."""
    if df.height == 0 or COL_NOMBRE not in df.columns:
        return df
    if "Identificación" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias("Identificación"))
    if mapa is None:
        mapa = mapa_nombre_unico_a_id(df)
    if not mapa:
        return df
    ids = df["Identificación"].to_list()
    nombres = df[COL_NOMBRE].to_list()
    nuevos: list = []
    for ident, nom in zip(ids, nombres):
        if _id_normalizado(ident):
            nuevos.append(ident)
            continue
        hallado = mapa.get(_clave_nombre_unico(nom) or "")
        nuevos.append(hallado if hallado else ident)
    return df.with_columns(pl.Series("Identificación", nuevos))


def asignar_clave_fusion(df: pl.DataFrame) -> pl.DataFrame:
    """_id_key = identificación; si falta, n: + nombre normalizado."""
    if df.height == 0:
        if "_id_key" in df.columns:
            return df
        return df.with_columns(pl.lit("").cast(pl.Utf8).alias("_id_key"))
    ids = df["Identificación"].to_list() if "Identificación" in df.columns else [None] * df.height
    nombres = df[COL_NOMBRE].to_list() if COL_NOMBRE in df.columns else [None] * df.height
    keys = [clave_fusion_estudiante(i, n) for i, n in zip(ids, nombres)]
    return df.with_columns(pl.Series("_id_key", keys))


def asegurar_identificacion_unica(df: pl.DataFrame) -> pl.DataFrame:
    """Si no hay cédula, usa la llave de nombre (n:…) para no perder la fila en SQL."""
    if df.height == 0 or "Identificación" not in df.columns:
        return df
    df = asignar_clave_fusion(df)
    df = df.with_columns(
        pl.when(
            pl.col("Identificación").is_null()
            | (pl.col("Identificación").cast(pl.Utf8).str.strip_chars() == "")
        )
        .then(pl.col("_id_key"))
        .otherwise(pl.col("Identificación"))
        .alias("Identificación")
    )
    return df.drop("_id_key") if "_id_key" in df.columns else df


def unir_extra_por_id_o_nombre(
    principal: pl.DataFrame,
    extra: pl.DataFrame,
) -> pl.DataFrame:
    """Left join de extra al consolidado por identificación o, si es única, por nombre."""
    data_cols = [
        c
        for c in extra.columns
        if c not in {"_id_key", "_nombre_key", COL_NOMBRE, "Identificación"}
    ]
    if extra.height == 0 or not data_cols:
        return principal
    mapa = mapa_nombre_unico_a_id(principal, extra)
    p = completar_identificacion_por_nombre(principal, mapa)
    extra_work = extra
    if COL_NOMBRE in extra.columns or "Identificación" in extra.columns:
        extra_work = completar_identificacion_por_nombre(extra, mapa)
    p = asignar_clave_fusion(p)
    if "_id_key" not in extra_work.columns or COL_NOMBRE in extra_work.columns:
        extra_work = asignar_clave_fusion(extra_work)
    extra_work = extra_work.filter(pl.col("_id_key") != "")
    if extra_work.height == 0:
        return p.drop("_id_key") if "_id_key" in p.columns else p
    overlap = [c for c in data_cols if c in p.columns]
    joined = p.join(
        extra_work.select(["_id_key", *data_cols]),
        on="_id_key",
        how="left",
        suffix="_extra",
    )
    for c in overlap:
        col_extra = f"{c}_extra"
        if col_extra in joined.columns:
            joined = joined.with_columns(
                pl.coalesce(pl.col(c), pl.col(col_extra)).alias(c)
            ).drop(col_extra)
    return joined.drop("_id_key") if "_id_key" in joined.columns else joined

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
        fila: dict = {
            "_id_key": key,
            "Identificación": _primero_no_vacio(grp["Identificación"].to_list()),
        }
        if _es_nulo(fila["Identificación"]) or str(fila["Identificación"]).strip() == "":
            if key and not str(key).startswith(PREFIJO_CLAVE_NOMBRE):
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

    alineados: list[pl.DataFrame] = []
    for i, df in enumerate(partes):
        tipo = tipos_partes[i] if tipos_partes and i < len(tipos_partes) else ""
        alineados.append(
            alinear_dataframe_salida(df, cols_listado).with_columns(
                pl.lit(tipo).alias("_fuente_tipo"),
            )
        )
    mapa = mapa_nombre_unico_a_id(*alineados)
    bloques: list[pl.DataFrame] = []
    for d in alineados:
        d = completar_identificacion_por_nombre(d, mapa)
        d = asignar_clave_fusion(d)
        d = d.filter(pl.col("_id_key") != "")
        if d.height > 0:
            bloques.append(d)

    listado = _fusionar_bloques_por_id(bloques, cols_listado, omitir_priorizado=True)
    listado = filtrar_filas_con_nombre(listado)

    if priorizados is not None and priorizados.height > 0:
        listado = unir_extra_por_id_o_nombre(listado, priorizados)
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
    if COL_NOMBRE not in cols_horarios_interno:
        cols_horarios_interno.insert(1, COL_NOMBRE)
    bloques_h_raw: list[pl.DataFrame] = []
    for df in horarios_partes:
        if df.height == 0:
            continue
        cols_h = list(cols_horarios_interno)
        if COL_PERIODO_ACTUAL in df.columns and COL_PERIODO_ACTUAL not in cols_h:
            cols_h.append(COL_PERIODO_ACTUAL)
        bloques_h_raw.append(alinear_dataframe_salida(df, cols_h))

    mapa_h = mapa_nombre_unico_a_id(listado, *bloques_h_raw)
    listado = completar_identificacion_por_nombre(listado, mapa_h)
    consolidado = asignar_clave_fusion(listado)

    bloques_h: list[pl.DataFrame] = []
    for d in bloques_h_raw:
        d = completar_identificacion_por_nombre(d, mapa_h)
        d = asignar_clave_fusion(d)
        d = d.filter(pl.col("_id_key") != "")
        if d.height > 0:
            bloques_h.append(d)

    if bloques_h:
        cols_h_fusion = [c for c in cols_horarios_interno if c != COL_NOMBRE]
        if any(COL_PERIODO_ACTUAL in b.columns for b in bloques_h):
            if COL_PERIODO_ACTUAL not in cols_h_fusion:
                cols_h_fusion.append(COL_PERIODO_ACTUAL)
        horarios = _fusionar_bloques_por_id(bloques_h, cols_h_fusion)
        if "_id_key" not in horarios.columns:
            horarios = asignar_clave_fusion(
                completar_identificacion_por_nombre(horarios, mapa_h)
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

    if "_id_key" in consolidado.columns:
        consolidado = consolidado.drop("_id_key")
    columnas_final = [*cols_listado, *cols_materias]
    consolidado = alinear_dataframe_salida(consolidado, columnas_final)
    consolidado = deduplicar_por_nombre(consolidado)
    consolidado = filtrar_filas_consolidado(consolidado)
    return consolidado

