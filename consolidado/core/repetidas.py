"""Materias repetidas (bd_rep): marcan celdas de horario, no filas nuevas."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from consolidado.config.settings import carpeta_excels
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.columnas import (
    _buscar_columna_por_aliases,
    aliases_identificacion_efectivos,
    aliases_para_slot,
    usando_aliases,
)
from consolidado.core.constants import COL_REPITIENDO
from consolidado.core.normalizacion import (
    _es_valor_vacio,
    _str_celda,
    normalizar_encabezado,
    normalizar_id,
)

_ORDINALES_REPITE: dict[str, int] = {
    "primera": 1,
    "primero": 1,
    "segunda": 2,
    "segundo": 2,
    "tercera": 3,
    "tercero": 3,
    "cuarta": 4,
    "cuarto": 4,
    "quinta": 5,
    "quinto": 5,
    "sexta": 6,
    "sexto": 6,
    "septima": 7,
    "septimo": 7,
    "octava": 8,
    "octavo": 8,
    "novena": 9,
    "noveno": 9,
    "decima": 10,
    "decimo": 10,
}


def _normalizar_texto_est_matricula(val) -> str:
    texto = str(val or "").strip().lower()
    return texto.translate(str.maketrans("áéíóúü", "aeiouu"))


def valor_est_matricula(val) -> int | None:
    """Convierte EST_MATRICULA a valor numérico (0=Matriculado, 1=Repite, etc.)."""
    if _es_valor_vacio(val):
        return None
    s = _normalizar_texto_est_matricula(val)
    if s in ("matriculado", "matricula"):
        return 0
    if s == "repite":
        return 1
    if "repite por" in s or "repite la" in s:
        m_num = re.search(r"repite\s+por\s+(\d+)", s)
        if m_num:
            return int(m_num.group(1))
        for palabra, numero in _ORDINALES_REPITE.items():
            if palabra in s:
                return numero
    if "repite" in s:
        return 1
    try:
        n = int(float(str(val).strip()))
        if n >= 0:
            return n
    except ValueError:
        pass
    return None
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
        aliases_identificacion_efectivos(
            ["num identificacion", "cedula", "cédula", "identificacion", "identificación"]
        ),
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


def procesar_detalle_repitencia(ruta: Path, *, hoja: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Identificación → asignaturas que repite, con el máximo de EST_MATRICULA por materia."""
    df = _leer_hoja_datos(ruta, tipo="bd_rep", hoja=hoja)
    cols = list(df.columns)
    col_id = _buscar_columna_por_aliases(
        cols,
        aliases_identificacion_efectivos(
            ["num identificacion", "cedula", "cédula", "identificacion", "identificación"]
        ),
    )
    col_materia = _buscar_columna_por_aliases(cols, ["nom materia", "materia", "asignatura"])
    col_estado = _buscar_columna_por_aliases(
        cols, ["est matricula", "estado matricula", "est_matricula", "estado"]
    )
    if not col_id or not col_materia or not col_estado:
        return {}

    mejor: dict[str, dict[str, dict[str, Any]]] = {}
    for row in df.iter_rows(named=True):
        key = normalizar_id(row[col_id])
        materia = _str_celda(row[col_materia])
        veces = valor_est_matricula(row[col_estado])
        if not key or not materia or not veces:
            continue
        norm = _normalizar_nombre_materia(materia)
        if not norm:
            continue
        prev = mejor.setdefault(key, {}).get(norm)
        if prev is None or int(veces) > int(prev["veces"]):
            mejor[key][norm] = {"materia": materia, "veces": int(veces)}

    out: dict[str, list[dict[str, Any]]] = {}
    for key, materias in mejor.items():
        filas = list(materias.values())
        filas.sort(key=lambda item: (-int(item["veces"]), str(item["materia"])))
        out[key] = filas
    return out


_CACHE_DETALLE: dict[tuple[str, int, str], dict[str, list[dict[str, Any]]]] = {}


def detalle_repitencia_estudiante(
    identificacion: str,
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> list[dict[str, Any]]:
    """Asignaturas que repite este estudiante, leídas de NOTAS X CORTE (o bd_rep)."""
    ident = normalizar_id(identificacion)
    if not ident:
        return []
    origen: tuple[Path, str] | None = _notas_de_matriculados(cfg, base, carpeta)
    if origen is None:
        slot, ruta = _ruta_slot(cfg, base, carpeta, "bd_rep")
        if slot is None or ruta is None:
            return []
        origen = (ruta, str(slot.get("hoja") or ""))
    ruta, hoja = origen
    try:
        marca = ruta.stat().st_mtime_ns
    except OSError:
        return []
    clave = (str(ruta.resolve()), marca, hoja)
    mapa = _CACHE_DETALLE.get(clave)
    if mapa is None:
        try:
            mapa = procesar_detalle_repitencia(ruta, hoja=hoja or None)
        except Exception:
            mapa = {}
        _CACHE_DETALLE.clear()
        _CACHE_DETALLE[clave] = mapa
    return list(mapa.get(ident) or [])


def procesar_repitiendo_estudiantes(ruta: Path, *, hoja: str | None = None) -> dict[str, int]:
    """Devuelve identificación -> máximo valor numérico de EST_MATRICULA."""
    df = _leer_hoja_datos(ruta, tipo="bd_rep", hoja=hoja)
    cols = list(df.columns)
    col_id = _buscar_columna_por_aliases(
        cols,
        aliases_identificacion_efectivos(
            ["num identificacion", "cedula", "cédula", "identificacion", "identificación"]
        ),
    )
    col_estado = _buscar_columna_por_aliases(
        cols, ["est matricula", "estado matricula", "est_matricula", "estado"]
    )
    if not col_id or not col_estado:
        return {}

    mapa: dict[str, int] = {}
    for row in df.iter_rows(named=True):
        key = normalizar_id(row[col_id])
        if not key:
            continue
        valor = valor_est_matricula(row[col_estado])
        if valor is None:
            continue
        if key not in mapa or valor > mapa[key]:
            mapa[key] = valor
    return mapa


def aplicar_repitiendo(
    consolidado: pl.DataFrame,
    repitiendo: dict[str, int],
) -> pl.DataFrame:
    if consolidado.height == 0:
        return consolidado
    if COL_REPITIENDO not in consolidado.columns:
        consolidado = consolidado.with_columns(pl.lit(None).alias(COL_REPITIENDO))

    valores: list[int | None] = []
    for row in consolidado.iter_rows(named=True):
        key = normalizar_id(row.get("Identificación"))
        if key and key in repitiendo:
            valores.append(repitiendo[key])
        else:
            valores.append(None)
    return consolidado.with_columns(pl.Series(COL_REPITIENDO, valores, dtype=pl.Int32))


def _ruta_slot(cfg: dict, base: Path, carpeta: Path | None, tipo: str) -> tuple[dict | None, Path | None]:
    carpeta = Path(carpeta) if carpeta is not None else carpeta_excels(cfg, base)
    slot = next((s for s in cfg.get("archivos_fuente", []) if s.get("tipo") == tipo), None)
    if not slot:
        return None, None
    p = carpeta / slot.get("nombre_guardado", "")
    if not p.is_file():
        return slot, None
    return slot, p


def _notas_de_matriculados(cfg: dict, base: Path, carpeta: Path | None) -> tuple[Path, str] | None:
    """Hoja NOTAS X CORTE de bd1, si el libro la trae."""
    from consolidado.core.archivos import _nombre_hoja_notas_corte

    _slot, ruta = _ruta_slot(cfg, base, carpeta, "bd1")
    if ruta is None:
        return None
    hoja = _nombre_hoja_notas_corte(ruta)
    if not hoja:
        return None
    return ruta, hoja


def _cargar_repitiendo_cfg(
    cfg: dict, base: Path, carpeta: Path | None = None
) -> dict[str, int]:
    """Repitiendo sale de NOTAS X CORTE de matriculados; si no hay, del libro bd_rep."""
    notas = _notas_de_matriculados(cfg, base, carpeta)
    if notas:
        ruta, hoja = notas
        try:
            mapa = procesar_repitiendo_estudiantes(ruta, hoja=hoja)
        except Exception:
            mapa = {}
        if mapa:
            return mapa
    slot, ruta = _ruta_slot(cfg, base, carpeta, "bd_rep")
    if slot is None or ruta is None:
        return {}
    try:
        with usando_aliases(aliases_para_slot(slot)):
            return procesar_repitiendo_estudiantes(ruta, hoja=slot.get("hoja"))
    except Exception:
        return {}


def _cargar_materias_repetidas_cfg(
    cfg: dict,
    base: Path,
    carpeta: Path | None = None,
) -> dict[str, set[str]]:
    """Asignaturas que repite: misma hoja de notas de bd1, o bd_rep si no existe."""
    notas = _notas_de_matriculados(cfg, base, carpeta)
    if notas:
        ruta, hoja = notas
        try:
            mapa = procesar_materias_repetidas(ruta, hoja=hoja)
        except Exception:
            mapa = {}
        if mapa:
            return mapa
    slot, ruta = _ruta_slot(cfg, base, carpeta, "bd_rep")
    if slot is None or ruta is None:
        return {}
    try:
        with usando_aliases(aliases_para_slot(slot)):
            return procesar_materias_repetidas(ruta, hoja=slot.get("hoja"))
    except Exception:
        return {}

