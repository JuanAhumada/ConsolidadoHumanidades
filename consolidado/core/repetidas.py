from __future__ import annotations

from pathlib import Path

import polars as pl

from consolidado.config.settings import carpeta_excels
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.columnas import _buscar_columna_por_aliases
from consolidado.core.normalizacion import (
    _es_valor_vacio,
    _str_celda,
    normalizar_encabezado,
    normalizar_id,
)
def _normalizar_nombre_materia(texto: str) -> str:
    return normalizar_encabezado(str(texto or ""))

def _es_matricula_repetida(val) -> bool:
    if _es_valor_vacio(val):
        return False
    return "repite" in str(val).strip().lower()

def _extraer_nombre_materia_celda(valor) -> str:
    """Obtiene el nombre de la materia desde la celda del consolidado (p. ej. 'GRUPO - NOMBRE')."""
    s = str(valor).strip()
    if " - " in s:
        return s.rsplit(" - ", 1)[-1].strip()
    return s

def _materia_es_repetida(valor_celda, repetidas: set[str]) -> bool:
    if not repetidas or _es_valor_vacio(valor_celda):
        return False
    norm_celda = _normalizar_nombre_materia(_extraer_nombre_materia_celda(valor_celda))
    if not norm_celda:
        return False
    for rep in repetidas:
        if norm_celda == _normalizar_nombre_materia(rep):
            return True
    return False

def procesar_materias_repetidas(ruta: Path, *, hoja: str | None = None) -> dict[str, set[str]]:
    """Devuelve identificación -> conjunto de nombres de materias que repite."""
    df = _leer_hoja_datos(ruta, tipo="bd_rep", hoja=hoja)
    cols = list(df.columns)
    col_id = _buscar_columna_por_aliases(
        cols,
        ["num identificacion", "cedula", "cédula", "identificacion", "identificación"],
    )
    col_materia = _buscar_columna_por_aliases(cols, ["nom materia", "materia", "asignatura"])
    col_estado = _buscar_columna_por_aliases(
        cols, ["est matricula", "estado matricula", "est_matricula", "estado"]
    )
    if not col_id or not col_materia:
        return {}

    mapa: dict[str, set[str]] = {}
    for row in df.iter_rows(named=True):
        if col_estado and not _es_matricula_repetida(row[col_estado]):
            continue
        key = normalizar_id(row[col_id])
        materia = _str_celda(row[col_materia])
        if not key or not materia:
            continue
        mapa.setdefault(key, set()).add(materia)
    return mapa

def _cargar_materias_repetidas_cfg(
    cfg: dict,
    base: Path,
) -> dict[str, set[str]]:
    carpeta = carpeta_excels(cfg, base)
    slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == "bd_rep"), None)
    if not slot:
        return {}
    p = carpeta / slot.get("nombre_guardado", "")
    if not p.is_file():
        return {}
    try:
        return procesar_materias_repetidas(p, hoja=slot.get("hoja"))
    except Exception:
        return {}

