"""
Permanencia y ruta de grado.

Cruza estudiantes por documento (cohortes + base general) y lee las hojas de
metas. El left join no crea filas nuevas: solo enriquece al consolidado.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from openpyxl import load_workbook

from consolidado.config.settings import COLUMNAS_RUTA_GRADO, carpeta_excels
from consolidado.core.constants import COL_ACTIVOS
from consolidado.core.normalizacion import (
    _es_nulo,
    formatear_periodo_cod,
    normalizar_encabezado,
    normalizar_id,
    programa_es_permitido,
)

_VACIOS = frozenset({"", "-", "—", "–", ".", "n/a", "na", "none", "nan", "null"})
_ENCABEZADOS_META = frozenset({"programas", "programa"})
_FILAS_TITULO_META = frozenset(
    {
        "programas",
        "programa",
        "proyeccion",
        "proyeccion estimada",
        "graduacion",
        "permanencia",
    }
)

_ALIAS_CAMPOS: dict[str, tuple[str, ...]] = {
    "pct_creditos": (
        "% creditos aprobados",
        "% aprobados",
        "% creditos aprobados.",
    ),
    "estado_opcion": ("estado de opcion de grado",),
    "opcion": ("opcion de grado", "opcion a grado"),
    "estado_ingles": ("estado de ingles",),
    "saber_pro": ("saber pro2", "saber pro"),
    "observaciones": (
        "observacion de seguimiento",
        "observaciones de seguimiento",
        "observaciones",
        "observacion",
    ),
}

_SALIDA = {
    "pct_creditos": COLUMNAS_RUTA_GRADO[0],
    "estado_opcion": COLUMNAS_RUTA_GRADO[1],
    "opcion": COLUMNAS_RUTA_GRADO[2],
    "estado_ingles": COLUMNAS_RUTA_GRADO[3],
    "saber_pro": COLUMNAS_RUTA_GRADO[4],
}

_ALIAS_META = {
    "programa": ("programas", "programa"),
    "periodo_inicio": ("periodo inicio", "periodo de inicio"),
    "poblacion": ("poblacion",),
    "meta_num": ("meta #", "meta n", "meta num"),
    "alcanzado_num": ("# alcanzado", "alcanzado"),
    "faltante_num": ("# faltante", "faltante"),
    "meta_pct": ("meta %",),
    "alcanzado_pct": ("% alcanzado",),
    "faltante_pct": ("% faltante",),
    "estado": ("estado",),
}


def _texto(val: Any) -> str:
    if _es_nulo(val):
        return ""
    return " ".join(str(val).replace("\xa0", " ").replace("\n", " ").split())


def _es_graduado_obs(val: Any) -> bool:
    return "graduado" in _norm(val)


def _es_vacio(val: Any) -> bool:
    t = _texto(val)
    return not t or t.lower() in _VACIOS


def _norm(val: Any) -> str:
    return normalizar_encabezado(_texto(val))


def ruta_archivo_permanencia(
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> Path | None:
    carpeta = Path(carpeta) if carpeta is not None else carpeta_excels(cfg, base)
    for slot in cfg.get("archivos_fuente", []):
        if slot.get("tipo") != "bd_permanencia" and slot.get("id") != "bd_permanencia":
            continue
        p = carpeta / slot.get("nombre_guardado", "")
        if p.is_file():
            return p
    return None


def _hoja_es_cohorte(nombre: str) -> bool:
    return _norm(nombre).startswith("cohorte")


def _hoja_es_base_general(nombre: str) -> bool:
    n = _norm(nombre)
    return "base" in n and "general" in n


def _hoja_es_metas_graduacion(nombre: str) -> bool:
    n = _norm(nombre)
    return "metas" in n and "gradu" in n


def _hoja_es_metas_permanencia(nombre: str) -> bool:
    n = _norm(nombre)
    return "metas" in n and "perman" in n


def _indices_por_aliases(
    headers_norm: list[str],
    aliases: tuple[str, ...],
    usados: set[int],
) -> list[int]:
    encontrados: list[int] = []
    for alias in aliases:
        for i, h in enumerate(headers_norm):
            if i in usados or h != alias:
                continue
            encontrados.append(i)
            usados.add(i)
    return encontrados


def _indice_por_aliases(
    headers_norm: list[str],
    aliases: tuple[str, ...],
    usados: set[int],
) -> int | None:
    hallados = _indices_por_aliases(headers_norm, aliases, usados)
    return hallados[0] if hallados else None


def _mapa_columnas_estudiante(
    headers: list[Any],
    *,
    fallback_ingles: bool,
) -> dict[str, Any]:
    headers_norm = [_norm(h) for h in headers]
    usados: set[int] = set()
    mapa: dict[str, Any] = {}
    idx_doc = _indice_por_aliases(
        headers_norm, ("documento", "identificacion", "num identificacion"), usados
    )
    if idx_doc is None:
        return {}
    usados.add(idx_doc)
    mapa["documento"] = idx_doc
    for clave, aliases in _ALIAS_CAMPOS.items():
        idxs = _indices_por_aliases(headers_norm, aliases, usados)
        if idxs:
            mapa[clave] = idxs
    if fallback_ingles and "estado_ingles" not in mapa:
        idxs = _indices_por_aliases(headers_norm, ("ingles",), usados)
        if idxs:
            mapa["estado_ingles"] = idxs
    return mapa


def _es_encabezado_estudiantes(vals: list[Any]) -> bool:
    norms = [_norm(v) for v in vals if not _es_vacio(v)]
    if "documento" not in norms and "identificacion" not in norms:
        return False
    return any("nombre" in n or n == "programa" for n in norms)


def _numero_pct(val: Any) -> str | None:
    if _es_vacio(val):
        return None
    texto = _texto(val).replace("%", "").replace(",", ".")
    try:
        n = float(texto)
    except ValueError:
        return _texto(val)
    if -1.5 <= n <= 1.5:
        n *= 100
    return f"{n:.1f}%".replace(".0%", "%")


def _texto_campo(val: Any) -> str | None:
    if _es_vacio(val):
        return None
    return _texto(val)


def _valor_de_indices(vals: list[Any], indices: list[int], formatear) -> str | None:
    for i in indices:
        if i >= len(vals):
            continue
        valor = formatear(vals[i])
        if valor:
            return valor
    return None


def _fusionar_valores(destino: dict[str, str | None], origen: dict[str, str | None]) -> None:
    if origen.get("_graduado"):
        destino["_graduado"] = True
    for clave, valor in origen.items():
        if clave == "_graduado":
            continue
        if valor is None or valor == "":
            continue
        destino[clave] = valor


def _filas_estudiante_hoja(ws, *, fallback_ingles: bool) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    mapa: dict[str, Any] | None = None
    vacias = 0
    for row in ws.iter_rows(values_only=True):
        vals = list(row)
        if all(_es_vacio(v) for v in vals):
            if mapa is not None:
                vacias += 1
                if vacias >= 40:
                    break
            continue
        vacias = 0
        if _es_encabezado_estudiantes(vals):
            candidato = _mapa_columnas_estudiante(vals, fallback_ingles=fallback_ingles)
            if candidato:
                mapa = candidato
            continue
        if not mapa:
            continue
        idx_doc = mapa["documento"]
        if idx_doc >= len(vals):
            continue
        key = normalizar_id(vals[idx_doc])
        if not key:
            continue
        fila: dict[str, str | None] = {}
        if "pct_creditos" in mapa:
            fila[_SALIDA["pct_creditos"]] = _valor_de_indices(
                vals, mapa["pct_creditos"], _numero_pct
            )
        if "estado_opcion" in mapa:
            fila[_SALIDA["estado_opcion"]] = _valor_de_indices(
                vals, mapa["estado_opcion"], _texto_campo
            )
        if "opcion" in mapa:
            fila[_SALIDA["opcion"]] = _valor_de_indices(vals, mapa["opcion"], _texto_campo)
        if "estado_ingles" in mapa:
            fila[_SALIDA["estado_ingles"]] = _valor_de_indices(
                vals, mapa["estado_ingles"], _texto_campo
            )
        if "saber_pro" in mapa:
            fila[_SALIDA["saber_pro"]] = _valor_de_indices(
                vals, mapa["saber_pro"], _texto_campo
            )
        if "observaciones" in mapa:
            obs = _valor_de_indices(vals, mapa["observaciones"], _texto_campo)
            if _es_graduado_obs(obs):
                fila["_graduado"] = True
        previo = out.get(key, {})
        _fusionar_valores(previo, fila)
        out[key] = previo
    return out


def leer_estudiantes_permanencia(ruta: Path) -> pl.DataFrame:
    """Devuelve identificación + columnas de ruta de grado, una fila por documento."""
    schema = {
        "_id_key": pl.Utf8,
        **{c: pl.Utf8 for c in COLUMNAS_RUTA_GRADO},
        "_graduado": pl.Boolean,
    }
    if not ruta.is_file():
        return pl.DataFrame(schema=schema)

    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        por_id: dict[str, dict[str, str | None]] = {}
        hojas_base = [n for n in wb.sheetnames if _hoja_es_base_general(n)]
        hojas_cohorte = [n for n in wb.sheetnames if _hoja_es_cohorte(n)]
        for nombre in hojas_base + hojas_cohorte:
            extra = _filas_estudiante_hoja(
                wb[nombre],
                fallback_ingles=_hoja_es_base_general(nombre),
            )
            for key, fila in extra.items():
                previo = por_id.get(key, {})
                _fusionar_valores(previo, fila)
                por_id[key] = previo
    finally:
        wb.close()

    if not por_id:
        return pl.DataFrame(schema=schema)
    filas = []
    for key, data in por_id.items():
        fila = {"_id_key": key}
        for col in COLUMNAS_RUTA_GRADO:
            val = data.get(col)
            fila[col] = str(val) if val is not None else None
        fila["_graduado"] = bool(data.get("_graduado"))
        filas.append(fila)
    return pl.DataFrame(filas, schema=schema)


def aplicar_permanencia(
    consolidado: pl.DataFrame,
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> pl.DataFrame:
    """Left join de ruta de grado; no añade estudiantes que no estén en el consolidado."""
    for col in list(COLUMNAS_RUTA_GRADO) + [COL_ACTIVOS]:
        if col in consolidado.columns:
            consolidado = consolidado.drop(col)

    ruta = ruta_archivo_permanencia(cfg, base, carpeta)
    extra = pl.DataFrame(
        schema={
            "_id_key": pl.Utf8,
            **{c: pl.Utf8 for c in COLUMNAS_RUTA_GRADO},
            "_graduado": pl.Boolean,
        }
    )
    if ruta:
        try:
            extra = leer_estudiantes_permanencia(ruta)
        except Exception:
            extra = pl.DataFrame(
                schema={
                    "_id_key": pl.Utf8,
                    **{c: pl.Utf8 for c in COLUMNAS_RUTA_GRADO},
                    "_graduado": pl.Boolean,
                }
            )

    if extra.height == 0:
        return consolidado.with_columns(
            [pl.lit(None).alias(c) for c in COLUMNAS_RUTA_GRADO]
            + [pl.lit(True).alias(COL_ACTIVOS)]
        )

    resultado = consolidado.with_columns(
        pl.col("Identificación")
        .map_elements(normalizar_id, return_dtype=pl.Utf8)
        .alias("_id_key")
    )
    cols_join = [c for c in extra.columns if c != "_id_key"]
    extra = extra.select(["_id_key"] + cols_join)
    resultado = resultado.join(extra, on="_id_key", how="left").drop("_id_key")
    for col in COLUMNAS_RUTA_GRADO:
        if col not in resultado.columns:
            resultado = resultado.with_columns(pl.lit(None).alias(col))
    if "_graduado" in resultado.columns:
        resultado = resultado.with_columns(
            (~pl.col("_graduado").fill_null(False)).alias(COL_ACTIVOS)
        ).drop("_graduado")
    else:
        resultado = resultado.with_columns(pl.lit(True).alias(COL_ACTIVOS))
    return resultado


def _es_encabezado_metas(vals: list[Any]) -> bool:
    norms = [_norm(v) for v in vals if not _es_vacio(v)]
    if not any(n in _ENCABEZADOS_META for n in norms):
        return False
    return any("meta" in n for n in norms)


def _mapa_columnas_meta(headers: list[Any]) -> dict[str, int]:
    headers_norm = [_norm(h) for h in headers]
    usados: set[int] = set()
    mapa: dict[str, int] = {}
    for clave, aliases in _ALIAS_META.items():
        idx = _indice_por_aliases(headers_norm, aliases, usados)
        if idx is not None:
            usados.add(idx)
            mapa[clave] = idx
    return mapa


def _periodo_en_prefijo(vals: list[Any], idx_programa: int) -> str | None:
    tope = idx_programa if idx_programa > 0 else min(4, len(vals))
    for i in range(tope):
        p = formatear_periodo_cod(vals[i])
        if p:
            return p
    return None


def _formatear_entero(val: Any) -> str:
    if _es_vacio(val):
        return ""
    texto = _texto(val).replace(",", ".")
    try:
        n = float(texto)
    except ValueError:
        return _texto(val)
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"


def _programa_meta_permitido(nombre: str) -> bool:
    n = _norm(nombre)
    if n == "institucional":
        return True
    return programa_es_permitido(nombre)


def _fila_meta_vacia(fila: dict[str, str]) -> bool:
    return not any(
        fila.get(k)
        for k in (
            "poblacion",
            "meta_num",
            "alcanzado_num",
            "meta_pct",
            "alcanzado_pct",
            "estado",
        )
    )


def _bloques_metas_hoja(ws) -> list[dict[str, Any]]:
    por_periodo: dict[str, dict[str, Any]] = {}
    orden: list[str] = []
    mapa: dict[str, int] | None = None
    periodo_actual: str | None = None
    en_proyeccion = False
    vacias = 0

    for row in ws.iter_rows(values_only=True):
        vals = list(row)
        if all(_es_vacio(v) for v in vals):
            if mapa is not None:
                vacias += 1
                if vacias >= 25:
                    break
            continue
        vacias = 0
        joined = " ".join(_norm(v) for v in vals if not _es_vacio(v))
        if "proyec" in joined and not _es_encabezado_metas(vals):
            palabras = [p for p in joined.split() if p]
            if (
                periodo_actual
                and periodo_actual in por_periodo
                and palabras
                and all(p.startswith("proyec") for p in palabras)
            ):
                por_periodo[periodo_actual]["proyeccion"] = True
            en_proyeccion = True
            continue
        if _es_encabezado_metas(vals):
            mapa = _mapa_columnas_meta(vals)
            continue
        if not mapa or "programa" not in mapa:
            continue
        idx_prog = mapa["programa"]
        if idx_prog >= len(vals):
            continue
        periodo_fila = _periodo_en_prefijo(vals, idx_prog)
        if periodo_fila:
            periodo_actual = periodo_fila
        programa = _texto(vals[idx_prog])
        if not programa or _norm(programa) in _FILAS_TITULO_META:
            continue
        if not periodo_actual or not _programa_meta_permitido(programa):
            continue

        def _cel(clave: str) -> Any:
            idx = mapa.get(clave)
            if idx is None or idx >= len(vals):
                return None
            return vals[idx]

        fila = {
            "programa": programa,
            "periodo_inicio": formatear_periodo_cod(_cel("periodo_inicio"))
            or _texto_campo(_cel("periodo_inicio"))
            or "",
            "poblacion": _formatear_entero(_cel("poblacion")),
            "meta_num": _formatear_entero(_cel("meta_num")),
            "alcanzado_num": _formatear_entero(_cel("alcanzado_num")),
            "faltante_num": _formatear_entero(_cel("faltante_num")),
            "meta_pct": _numero_pct(_cel("meta_pct")) or "",
            "alcanzado_pct": _numero_pct(_cel("alcanzado_pct")) or "",
            "faltante_pct": _numero_pct(_cel("faltante_pct")) or "",
            "estado": (_texto_campo(_cel("estado")) or "").upper(),
        }
        estado = fila["estado"]
        fila["cumple"] = True if estado == "CUMPLE" else False if estado == "NO CUMPLE" else None
        if _fila_meta_vacia(fila):
            continue
        bloque = por_periodo.get(periodo_actual)
        if bloque is None:
            bloque = {
                "periodo": periodo_actual,
                "proyeccion": en_proyeccion,
                "filas": [],
            }
            por_periodo[periodo_actual] = bloque
            orden.append(periodo_actual)
        elif en_proyeccion:
            bloque["proyeccion"] = True
        bloque["filas"].append(fila)
    return [por_periodo[p] for p in orden]


def _hoja_es_proyeccion_graduacion(nombre: str) -> bool:
    n = _norm(nombre)
    return n in {"hoja1", "hoja 1"} or n.startswith("proyecc")


def leer_metas(ruta: Path) -> dict[str, Any]:
    vacio = {"disponible": False, "graduacion": [], "permanencia": []}
    if not ruta or not ruta.is_file():
        return vacio

    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        graduacion: list[dict[str, Any]] = []
        permanencia: list[dict[str, Any]] = []
        for nombre in wb.sheetnames:
            if _hoja_es_metas_permanencia(nombre):
                permanencia.extend(_bloques_metas_hoja(wb[nombre]))
            elif _hoja_es_metas_graduacion(nombre) or _hoja_es_proyeccion_graduacion(nombre):
                graduacion.extend(_bloques_metas_hoja(wb[nombre]))
    finally:
        wb.close()

    return {
        "disponible": bool(graduacion or permanencia),
        "graduacion": graduacion,
        "permanencia": permanencia,
    }


def cargar_metas(
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> dict[str, Any]:
    ruta = ruta_archivo_permanencia(cfg, base, carpeta)
    if ruta is None:
        return {"disponible": False, "graduacion": [], "permanencia": []}
    return leer_metas(ruta)
