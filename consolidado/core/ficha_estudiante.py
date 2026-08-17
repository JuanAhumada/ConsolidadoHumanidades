"""Ficha consolidada de un estudiante para consulta en la interfaz."""

from __future__ import annotations

import re
from pathlib import Path

from consolidado.config.settings import construir_grupos_encabezado, etiqueta_export_columna
from consolidado.core.constants import (
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
    aplicar_config,
    es_columna_materia_horario,
)
from consolidado.core.normalizacion import _es_nulo, _es_valor_true, normalizar_id
from consolidado.core.pipeline import generar_dataframe_consolidado
from consolidado.storage.alertas_fuente import aplicar_descartes_a_fila, partir_tipos_alerta
from consolidado.storage.db import obtener_fila_estudiante, obtener_version

_CAMPOS_HERO = frozenset({"Identificación", "Nombre y apellidos", "Programa"})
_COLS_TIPO_ALERTA = frozenset(
    {
        COL_TIPO_ALERTA_INICIAL,
        COL_TIPO_ALERTA_FINAL,
        COL_NUM_ALERTA_INICIAL,
        COL_NUM_ALERTA_FINAL,
    }
)
_PUNTAJES_GRAFICA = [
    ("Ptje Beca", "Beca"),
    ("Ptje Priorizado", "Prio"),
    ("Ptje Repitiendo", "Repitiendo"),
    ("Ptje Reintegro", "Reintegro"),
    ("Ptje Propio", "Propio"),
    ("Ptje Activacion", "Activacion"),
]
_DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")
_DIA_CANON = {
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "miércoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
    "sábado": "Sábado",
    "domingo": "Domingo",
}
_RE_HORARIO = re.compile(
    r"(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
    r"\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})",
    re.IGNORECASE,
)
_RE_MATERIA = re.compile(
    r"^(PRESENCIAL|REMOTO|VIRTUAL|H[IÍ]BRIDO)(?:-(\d+))?\s*[-–]\s*(.+)$",
    re.IGNORECASE,
)


def _formatear_valor_ficha(val) -> str:
    if _es_nulo(val):
        return "—"
    if val is True or _es_valor_true(val):
        return "Sí"
    if val is False:
        return "No"
    texto = str(val).strip()
    return texto if texto else "—"


def _esta_vacio(val) -> bool:
    return _formatear_valor_ficha(val) == "—"


def _numero(val) -> float:
    if _es_nulo(val):
        return 0.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        return float(val)
    texto = str(val).strip().replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _campos_no_vacios(fila: dict, columnas: list[str], *, omitir: set[str] | None = None) -> list[dict[str, str]]:
    omitir = omitir or set()
    campos: list[dict[str, str]] = []
    for col in columnas:
        if col in omitir:
            continue
        valor = _formatear_valor_ficha(fila.get(col))
        if valor == "—":
            continue
        campos.append({"etiqueta": etiqueta_export_columna(col), "valor": valor, "columna": col})
    return campos


def _partir_materia(texto) -> dict[str, str]:
    raw = "" if _es_nulo(texto) else str(texto).strip()
    if not raw:
        return {"modalidad": "", "codigo": "", "nombre": "—"}
    m = _RE_MATERIA.match(raw)
    if m:
        return {
            "modalidad": m.group(1).capitalize(),
            "codigo": m.group(2) or "",
            "nombre": m.group(3).strip(),
        }
    return {"modalidad": "", "codigo": "", "nombre": raw}


def _bloques_horario(texto) -> list[dict[str, str]]:
    if _es_nulo(texto):
        return []
    bloques: list[dict[str, str]] = []
    for m in _RE_HORARIO.finditer(str(texto)):
        dia = _DIA_CANON.get(m.group(1).casefold())
        if not dia:
            continue
        bloques.append({"dia": dia, "inicio": m.group(2), "fin": m.group(3)})
    return bloques


def _puntajes_grafica(fila: dict) -> list[dict]:
    valores = [_numero(fila.get(col)) for col, _ in _PUNTAJES_GRAFICA]
    tope = max([3.0, *valores, 1.0])
    out: list[dict] = []
    for (col, etiqueta), valor in zip(_PUNTAJES_GRAFICA, valores):
        out.append(
            {
                "columna": col,
                "etiqueta": etiqueta,
                "valor": valor,
                "texto": f"{valor:g}",
                "pct": round(min(valor / tope, 1) * 100),
            }
        )
    return out


def _seccion_priorizado(fila: dict, columnas: list[str]) -> dict | None:
    es_prio = fila.get("Priorizado") is True or _es_valor_true(fila.get("Priorizado"))
    campos = _campos_no_vacios(fila, columnas)
    if not es_prio:
        campos = [c for c in campos if c.get("columna") != "Priorizado"]
    if not es_prio and not campos:
        return None
    return {"clave": "priorizado", "titulo": "Priorizado", "tipo": "campos", "campos": campos}


def _seccion_becas(fila: dict, columnas: list[str]) -> dict | None:
    campos = _campos_no_vacios(fila, columnas)
    if not campos:
        return None
    return {"clave": "becas", "titulo": "Becas", "tipo": "campos", "campos": campos}


def _seccion_alertas(fila: dict, columnas: list[str]) -> dict | None:
    inicial = partir_tipos_alerta(fila.get(COL_TIPO_ALERTA_INICIAL))
    final = partir_tipos_alerta(fila.get(COL_TIPO_ALERTA_FINAL))
    campos = _campos_no_vacios(fila, columnas, omitir=_COLS_TIPO_ALERTA)
    if not inicial and not final and not campos:
        return None
    return {
        "clave": "alertas",
        "titulo": "Alertas",
        "tipo": "alertas",
        "inicial": inicial,
        "final": final,
        "campos": campos,
    }


def _seccion_horario(fila: dict, columnas: list[str], num_materias: int) -> dict | None:
    extra = [col for col in columnas if not es_columna_materia_horario(col)]
    campos = _campos_no_vacios(fila, extra)
    filas: list[dict] = []
    por_dia: dict[str, list[dict]] = {d: [] for d in _DIAS_SEMANA}
    sin_dia: list[dict] = []
    for i in range(1, max(num_materias, 1) + 1):
        materia = fila.get(f"Materia {i}")
        horario = fila.get(f"Horario {i}")
        profesor = fila.get(f"Profesor {i}")
        if _esta_vacio(materia) and _esta_vacio(horario) and _esta_vacio(profesor):
            continue
        meta = _partir_materia(materia)
        item = {
            "n": str(i),
            "materia": _formatear_valor_ficha(materia),
            "nombre": meta["nombre"],
            "modalidad": meta["modalidad"],
            "codigo": meta["codigo"],
            "horario": _formatear_valor_ficha(horario),
            "profesor": _formatear_valor_ficha(profesor),
        }
        filas.append(item)
        bloques = _bloques_horario(horario)
        if not bloques:
            sin_dia.append(item)
            continue
        for bloque in bloques:
            por_dia[bloque["dia"]].append({**item, **bloque})
    for dia in por_dia:
        por_dia[dia].sort(key=lambda x: x.get("inicio") or "")
    dias = [d for d in _DIAS_SEMANA if por_dia[d]]
    if not campos and not filas:
        return None
    return {
        "clave": "horario",
        "titulo": "Horario",
        "campos": campos,
        "filas": filas,
        "dias": dias,
        "por_dia": por_dia,
        "sin_dia": sin_dia,
        "n_dias": len(dias) if dias else (1 if filas else 0),
    }


def construir_vista_ficha(cfg: dict, fila: dict, *, num_materias: int) -> dict:
    """Arma el tablero: datos, categorías presentes y horario."""
    grupo_materias = str(cfg.get("grupo_materias", "Materias")).strip().casefold()
    datos: list[dict[str, str]] = []
    categorias: list[dict] = []
    horario = None
    for nombre_grupo, columnas in construir_grupos_encabezado(cfg, num_materias):
        clave = nombre_grupo.strip().casefold()
        if clave == "datos":
            datos = _campos_no_vacios(fila, columnas, omitir=_CAMPOS_HERO)
            continue
        if clave == "puntaje":
            continue
        if clave == "priorizados" or clave == "priorizado":
            sec = _seccion_priorizado(fila, columnas)
            if sec:
                categorias.append(sec)
            continue
        if clave == "becas":
            sec = _seccion_becas(fila, columnas)
            if sec:
                categorias.append(sec)
            continue
        if clave == "alertas":
            sec = _seccion_alertas(fila, columnas)
            if sec:
                categorias.append(sec)
            continue
        if clave == grupo_materias or clave == "materias":
            horario = _seccion_horario(fila, columnas, num_materias)
            continue
        campos = _campos_no_vacios(fila, columnas)
        if campos:
            categorias.append(
                {"clave": clave, "titulo": nombre_grupo, "tipo": "campos", "campos": campos}
            )
    return {
        "datos": datos,
        "categorias": categorias,
        "n_categorias": len(categorias),
        "horario": horario,
        "puntajes": _puntajes_grafica(fila),
    }


def obtener_ficha_estudiante(
    cfg: dict,
    base: Path,
    identificacion: str,
    *,
    version_id: int | None = None,
) -> dict | None:
    """
    Devuelve la ficha del estudiante o None si no está en SQL ni en el consolidado.
    Busca primero por identificación en la base (versión reciente si no se indica).
    """
    cfg = aplicar_config(cfg, base)
    id_key = normalizar_id(identificacion)
    if not id_key:
        return None

    fila = None
    max_materias = 1
    fila_sql = obtener_fila_estudiante(id_key, version_id=version_id, base=base)
    if fila_sql:
        fila = fila_sql
        version_usada = fila_sql.get("_version_id")
        meta = obtener_version(int(version_usada), base) if version_usada else None
        max_materias = int((meta or {}).get("num_materias") or 1)
    else:
        consolidado, max_materias = generar_dataframe_consolidado(cfg, base=base)
        if consolidado.height == 0 or "Identificación" not in consolidado.columns:
            return None
        filtrado = consolidado.filter(
            consolidado["Identificación"].map_elements(normalizar_id, return_dtype=str) == id_key
        )
        if filtrado.height == 0:
            return None
        fila = filtrado.row(0, named=True)
        version_usada = None

    fila = aplicar_descartes_a_fila(fila, id_key, base)
    nombre = str(fila.get("Nombre y apellidos") or "").strip()
    vista = construir_vista_ficha(cfg, fila, num_materias=max_materias)
    nivel = fila.get("Nivel prioridad")
    return {
        "identificacion": id_key,
        "nombre": nombre,
        "programa": str(fila.get("Programa") or "").strip(),
        "periodo_ingreso": _formatear_valor_ficha(fila.get("Periodo ingreso")),
        "nivel_prioridad": None if _esta_vacio(nivel) else str(nivel).strip(),
        "puntaje_prioridad": None
        if _esta_vacio(fila.get("Puntaje prioridad"))
        else _formatear_valor_ficha(fila.get("Puntaje prioridad")),
        "version_id": version_usada,
        **vista,
    }
