"""Documentos adicionales configurables: se unen por identificación al consolidado."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    carpeta_excels,
)
from consolidado.core.archivos import _elegir_hoja_datos, _leer_hoja_datos
from consolidado.core.columnas import _buscar_columna_por_aliases
from consolidado.core.constants import _ALIASES_RUNTIME, aplicar_config
from consolidado.core.excel_io import _leer_hoja_excel, _nombres_hojas_excel
from consolidado.core.fusion import filtrar_filas_programas_permitidos
from consolidado.core.normalizacion import combinar_valores, normalizar_encabezado, normalizar_id

MUESTRAS_PREVIA = 20
_PISTAS_IDENTIFICACION = (
    "identific",
    "cedula",
    "cédula",
    "documento",
    "num id",
    "nro id",
)


def _texto_celda_preview(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "strftime") and not isinstance(val, (str, int, float, bool)):
        try:
            return val.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            pass
    texto = str(val).strip()
    if texto.lower() in {"none", "null", "nan"}:
        return ""
    if len(texto) > 80:
        return texto[:77] + "…"
    return texto


def sugerir_titulo_documento(nombre_archivo: str) -> str:
    stem = Path(nombre_archivo or "").stem
    texto = re.sub(r"[_\-]+", " ", stem).strip()
    return texto.title() if texto else "Documento extra"


def slug_documento_id(titulo: str, existentes: set[str] | None = None) -> str:
    usados = existentes or set()
    base = re.sub(r"[^a-z0-9]+", "_", (titulo or "").lower()).strip("_") or "doc"
    doc_id = base
    n = 1
    while doc_id in usados:
        doc_id = f"{base}_{n}"
        n += 1
    return doc_id


def categorias_documento(cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = cfg or {}
    cats: list[str] = []
    for g in cfg.get("grupos_salida", []):
        nombre = str(g.get("nombre", "")).strip()
        if nombre and nombre not in cats:
            cats.append(nombre)
    etiquetas = cfg.get("categorias_fuente", CATEGORIAS_FUENTE_DEFAULT)
    for key in ORDEN_CATEGORIAS_FUENTE:
        etiqueta = str(etiquetas.get(key, key.title())).strip()
        if etiqueta and etiqueta not in cats:
            cats.append(etiqueta)
    for doc in cfg.get("documentos_adicionales", []):
        grupo = str(doc.get("grupo_encabezado") or doc.get("titulo") or "").strip()
        if grupo and grupo not in cats:
            cats.append(grupo)
    return cats or ["Extra"]


def aliases_identificacion(cfg: dict[str, Any] | None = None) -> list[str]:
    if not _ALIASES_RUNTIME:
        aplicar_config(cfg)
    if cfg:
        vals = cfg.get("aliases", {}).get("identificacion")
        if isinstance(vals, list) and vals:
            return [str(v) for v in vals if str(v).strip()]
    return list(_ALIASES_RUNTIME.get("identificacion") or [])


def sugerir_columna_identificacion(
    columnas: list[str],
    aliases: list[str] | None = None,
) -> str | None:
    if not columnas:
        return None
    ids = aliases or aliases_identificacion()
    hallada = _buscar_columna_por_aliases(columnas, ids)
    if hallada:
        return hallada
    for col in columnas:
        norma = normalizar_encabezado(col)
        if any(pista in norma for pista in _PISTAS_IDENTIFICACION):
            return col
    return columnas[0]


def vista_previa_excel(
    ruta: Path,
    *,
    hoja: str | None = None,
    n: int = MUESTRAS_PREVIA,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lee un Excel y devuelve columnas + hasta n filas de muestra."""
    hojas = _nombres_hojas_excel(ruta)
    if not hojas:
        raise ValueError(f"El Excel no tiene hojas: {ruta.name}")
    hoja_usada = (hoja or "").strip() or _elegir_hoja_datos(ruta)
    if hoja_usada not in hojas:
        hoja_usada = hojas[0]
    df = _leer_hoja_excel(ruta, hoja_usada)
    columnas = [str(c) for c in df.columns]
    if not columnas:
        raise ValueError(f"La hoja «{hoja_usada}» no tiene columnas.")
    muestra = df.head(max(1, min(n, 50)))
    filas: list[dict[str, str]] = []
    for row in muestra.iter_rows(named=True):
        filas.append({str(k): _texto_celda_preview(v) for k, v in row.items()})
    return {
        "hojas": hojas,
        "hoja": hoja_usada,
        "columnas": columnas,
        "filas": filas,
        "total_filas": int(df.height),
        "pk_sugerida": sugerir_columna_identificacion(
            columnas, aliases_identificacion(cfg)
        ),
    }


def columnas_config_documento(
    seleccion: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normaliza {origen, salida} de las columnas marcadas para usar."""
    out: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in seleccion:
        origen = str(item.get("origen") or "").strip()
        if not origen:
            aliases = item.get("aliases") or []
            if aliases:
                origen = str(aliases[0]).strip()
        salida = str(item.get("salida") or origen).strip()
        if not origen or not salida:
            continue
        if salida in vistos:
            raise ValueError(f"Hay dos columnas con el mismo nombre de salida: «{salida}».")
        vistos.add(salida)
        out.append({"salida": salida, "aliases": [origen]})
    return out


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
