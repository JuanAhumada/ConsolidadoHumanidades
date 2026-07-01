from __future__ import annotations

import polars as pl

from consolidado.config.settings import COLUMNAS_PRIORIZADO
from consolidado.core.constants import (
    COL_FECHA_NACIMIENTO,
    COL_NOMBRE,
    COL_TELEFONO_CELULAR,
    FORMATO_FECHA_DMY,
    _ALIASES_RUNTIME,
    aplicar_config,
)
from consolidado.core.normalizacion import (
    _mapa_norm_a_real,
    formatear_fecha_nacimiento,
    normalizar_encabezado,
    normalizar_id,
    normalizar_telefono_celda,
    _entero_o_texto,
)
def construir_mapa_columnas(columns: list[str]) -> dict[str, str]:
    """Devuelve canónico -> nombre real de columna en el DataFrame."""
    norm_to_real: dict[str, str] = {}
    for c in columns:
        k = normalizar_encabezado(c)
        if k and k not in norm_to_real:
            norm_to_real[k] = c

    resultado: dict[str, str] = {}
    if not _ALIASES_RUNTIME:
        aplicar_config()
    for canon, aliases in _ALIASES_RUNTIME.items():
        for alias in aliases:
            key = normalizar_encabezado(alias)
            if key in norm_to_real:
                resultado[canon] = norm_to_real[key]
                break

    if "identificacion" not in resultado:
        for c in columns:
            n = normalizar_encabezado(c)
            if not n:
                continue
            if "docente" in n:
                continue
            if "identific" in n or n == "documento":
                resultado["identificacion"] = c
                break
    return resultado

def _expr_nombre_completo(df: pl.DataFrame, m: dict[str, str], nr: dict[str, str]) -> pl.Expr:
    if "nombre_estudiante" in m:
        col_nom = m["nombre_estudiante"]
        if "apellidos" in nr and "nombres" in nr and nr["nombres"] == col_nom:
            return (
                pl.concat_str(
                    [pl.col(nr["nombres"]).cast(pl.Utf8), pl.col(nr["apellidos"]).cast(pl.Utf8)],
                    separator=" ",
                )
                .str.replace_all(r"\s+", " ")
                .str.strip_chars()
                .alias("Nombre y apellidos")
            )
        return pl.col(col_nom).alias("Nombre y apellidos")
    if "nombres" in nr and "apellidos" in nr:
        return (
            pl.concat_str(
                [pl.col(nr["nombres"]).cast(pl.Utf8), pl.col(nr["apellidos"]).cast(pl.Utf8)],
                separator=" ",
            )
            .str.replace_all(r"\s+", " ")
            .str.strip_chars()
            .alias("Nombre y apellidos")
        )
    return pl.lit(None).alias("Nombre y apellidos")

def _expr_telefono_celular(df: pl.DataFrame, m: dict[str, str], nr: dict[str, str]) -> pl.Expr:
    if "telefono_celular" in m:
        col = m["telefono_celular"]
    else:
        col = None
        for clave in ("tel. celular", "celular", "tel cecular"):
            if clave in nr:
                col = nr[clave]
                break
    if col:
        return (
            pl.col(col)
            .map_elements(lambda v: normalizar_telefono_celda(v), return_dtype=pl.Utf8)
            .alias(COL_TELEFONO_CELULAR)
        )
    return pl.lit(None).alias(COL_TELEFONO_CELULAR)

def _expr_total_beca(df: pl.DataFrame, m: dict[str, str], nr: dict[str, str]) -> pl.Expr:
    """Valor monetario de la beca (columna TOTAL en hoja BECAS Y CRÉDITOS)."""
    if "total" in nr:
        return pl.col(nr["total"]).alias("Total beca")
    if not _ALIASES_RUNTIME:
        aplicar_config()
    col = _buscar_columna_por_aliases(list(df.columns), _ALIASES_RUNTIME.get("total_beca", []))
    if col:
        return pl.col(col).alias("Total beca")
    return pl.lit(None).alias("Total beca")


def _expr_funcionario_beca(df: pl.DataFrame, m: dict[str, str], nr: dict[str, str]) -> pl.Expr:
    if "responsable" in nr:
        return pl.col(nr["responsable"]).alias("Funcionario que tiene a cargo la beca")
    if "funcionario_beca" in m:
        return pl.col(m["funcionario_beca"]).alias("Funcionario que tiene a cargo la beca")
    return pl.lit(None).alias("Funcionario que tiene a cargo la beca")


def _expr_tipo_beca(df: pl.DataFrame, m: dict[str, str], nr: dict[str, str]) -> pl.Expr:
    if "nom concepto" in nr:
        nom = pl.col(nr["nom concepto"]).cast(pl.Utf8)
        if "tipo" in nr:
            tipo = pl.col(nr["tipo"]).cast(pl.Utf8)
            return (
                pl.when(tipo.is_not_null() & (tipo.str.strip_chars() != ""))
                .then(nom + pl.lit(" (") + tipo + pl.lit(")"))
                .otherwise(nom)
                .alias("Tipo de beca o crédito")
            )
        return nom.alias("Tipo de beca o crédito")
    if "tipo_beca_credito" in m:
        return pl.col(m["tipo_beca_credito"]).alias("Tipo de beca o crédito")
    return pl.lit(None).alias("Tipo de beca o crédito")

def _expr_fecha_nacimiento(df: pl.DataFrame, m: dict[str, str], orden: str) -> pl.Expr:
    if "fecha_nacimiento" not in m:
        return pl.lit(None).cast(pl.Utf8).alias(COL_FECHA_NACIMIENTO)
    return (
        pl.col(m["fecha_nacimiento"])
        .map_elements(
            lambda v: formatear_fecha_nacimiento(v, orden),
            return_dtype=pl.Utf8,
        )
        .alias(COL_FECHA_NACIMIENTO)
    )

def renombrar_y_filtrar(
    df: pl.DataFrame,
    *,
    formato_fecha_nacimiento: str = FORMATO_FECHA_DMY,
) -> pl.DataFrame:
    cols = list(df.columns)
    m = construir_mapa_columnas(cols)
    nr = _mapa_norm_a_real(cols)

    if "identificacion" not in m:
        raise ValueError(
            "No se encontró columna de identificación. "
            f"Columnas del archivo: {cols}. "
            "Revisa la hoja usada o amplía la detección en consolidado.core.archivos."
        )

    exprs: list[pl.Expr] = [pl.col(m["identificacion"]).alias("Identificación")]
    exprs.append(_expr_nombre_completo(df, m, nr))
    exprs.append(_expr_telefono_celular(df, m, nr))
    exprs.append(_expr_fecha_nacimiento(df, m, formato_fecha_nacimiento))

    for canon, salida in [
        ("programa", "Programa"),
        ("correo_institucional", "Correo institucional"),
        ("correo_personal", "Correo personal"),
        ("periodo_ingreso", "Periodo ingreso"),
        ("reintegros", "Reintegros"),
        ("lugar_nacimiento", "Lugar de nacimiento"),
        ("lugar_residencia", "Lugar de residencia"),
    ]:
        exprs.append(
            pl.col(m[canon]).alias(salida) if canon in m else pl.lit(None).alias(salida)
        )

    exprs.append(_expr_funcionario_beca(df, m, nr))
    exprs.append(_expr_tipo_beca(df, m, nr))
    exprs.append(_expr_total_beca(df, m, nr))
    for col_prio in COLUMNAS_PRIORIZADO:
        exprs.append(pl.lit(None).alias(col_prio))

    return df.select(exprs)

def formatear_dataframe_salida(df: pl.DataFrame) -> pl.DataFrame:
    exprs: list[pl.Expr] = []
    for col in df.columns:
        if col in ("Identificación", "Periodo ingreso", "Reintegros"):
            exprs.append(
                pl.col(col).map_elements(_entero_o_texto, return_dtype=pl.String).alias(col)
            )
        elif col == COL_TELEFONO_CELULAR:
            exprs.append(
                pl.col(col)
                .map_elements(lambda v: normalizar_telefono_celda(v), return_dtype=pl.Utf8)
                .alias(col)
            )
        elif col == COL_FECHA_NACIMIENTO:
            exprs.append(
                pl.col(col)
                .map_elements(
                    lambda v: formatear_fecha_nacimiento(v, FORMATO_FECHA_DMY),
                    return_dtype=pl.Utf8,
                )
                .alias(col)
            )
        else:
            exprs.append(pl.col(col))
    return df.select(exprs)

def alinear_dataframe_salida(df: pl.DataFrame, columnas: list[str]) -> pl.DataFrame:
    faltantes = [c for c in columnas if c not in df.columns]
    if faltantes:
        df = df.with_columns(pl.lit(None).alias(c) for c in faltantes)
    return df.select(columnas)

def _buscar_columna_por_aliases(columns: list[str], aliases: list[str]) -> str | None:
    nr = _mapa_norm_a_real(columns)
    for alias in aliases:
        key = normalizar_encabezado(alias)
        if key in nr:
            return nr[key]
    return None

