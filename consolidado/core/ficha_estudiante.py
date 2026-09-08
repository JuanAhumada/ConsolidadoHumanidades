"""
Ficha de un estudiante para la web.

Lee SQL (última versión o la pedida). El badge del horario usa Periodo actual
del alumno; si falta, el periodo de la versión.
El grupo Puntaje no se lista: va como gráfica en el sidebar.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from consolidado.config.settings import (
    COLUMNAS_PRIORIZADO,
    COLUMNAS_PRIORIZADO_ENRIQUECIDO,
    COLUMNAS_RUTA_GRADO,
    COLUMNAS_MOTIVO_PRIO_DEFAULT,
    construir_grupos_encabezado,
    etiqueta_export_columna,
)
from consolidado.core.constants import (
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_PERIODO_ACTUAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
    COL_TOTAL_BECA,
    aplicar_config,
    es_columna_materia_horario,
)
from consolidado.core.normalizacion import (
    _es_nulo,
    _es_valor_true,
    es_estudiante_activo,
    formatear_monto_beca_vista,
    formatear_periodo_cod,
    normalizar_id,
)
from consolidado.core.prioridad import fmt_pts
from consolidado.core.colores_programa import color_programa, estilo_color
from consolidado.core.pipeline import generar_dataframe_consolidado
from consolidado.core.proyeccion_grado import es_proximo_a_grado
from consolidado.storage.alertas_fuente import aplicar_descartes_a_fila, partir_tipos_alerta
from consolidado.storage.db import (
    obtener_fila_estudiante,
    obtener_version,
    periodo_desde_fecha,
    ultima_version,
)
from consolidado.storage.ediciones import clave_campo_edicion, cargar_ediciones, overlay_ediciones_fila
from consolidado.storage.graduacion import obtener_marca_gradua
from consolidado.storage.notas import listar_notas

_CAMPOS_ACADEMICO = (
    "Activos",
    "Periodo ingreso",
    "Reintegros",
    "Repitiendo",
)
_CAMPOS_ACADEMICO_SET = frozenset(_CAMPOS_ACADEMICO)
_COLS_PRIORIZADO = list(COLUMNAS_PRIORIZADO) + list(COLUMNAS_PRIORIZADO_ENRIQUECIDO)
_COLS_SI_NO = frozenset({"Priorizado", "Activacion de ruta"})
_COLS_FECHA = frozenset({"Fecha adaptacion", "Fecha activacion de ruta"})
_COLS_NUMERO = frozenset({"% créditos aprobados"})
_ESTADOS_RUTA = ("", "Finalizado", "Matriculado", "Pendiente", "No aplica")
_ESTADOS_SABER = ("", "Finalizado", "Pagado", "Pendiente", "No aplica")
_ESTADOS_GRAD = ("", "ACTIVO", "GRADUADO", "EN TRÁMITE", "NO APLICA")
_SELECT_ESTADOS = {
    "Estado opción de grado": _ESTADOS_RUTA,
    "Estado de inglés": _ESTADOS_RUTA,
    "Saber Pro": _ESTADOS_SABER,
    "Estado graduación": _ESTADOS_GRAD,
}
_CAMPOS_HERO = frozenset(
    {
        "Identificación",
        "Nombre y apellidos",
        "Programa",
    }
)
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
    ("Ptje Ruta", "Grado"),
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
        if col == COL_TOTAL_BECA:
            monto = formatear_monto_beca_vista(fila.get(col))
            if monto:
                valor = monto
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


def _formatear_academico(col: str, val) -> str:
    if col == "Activos":
        return "Sí" if es_estudiante_activo(val) else "No"
    if col in {"Reintegros", "Repitiendo"}:
        if _es_nulo(val) or val is False:
            return "0" if col == "Reintegros" else "—"
        if isinstance(val, bool):
            return "Sí" if val else "No"
        texto = str(val).strip()
        if not texto:
            return "—"
        try:
            n = float(texto.replace(",", "."))
            if abs(n - round(n)) < 1e-9:
                return str(int(round(n)))
            return str(n)
        except ValueError:
            return texto
    return _formatear_valor_ficha(val)


def _seccion_academico(fila: dict, extras: list[str] | None = None) -> dict:
    etiquetas = (
        ("Activos", "Activo"),
        ("Periodo ingreso", "Periodo de Ingreso"),
        ("Reintegros", "Reintegros"),
        ("Repitiendo", "Repitiendo"),
    )
    campos: list[dict[str, str]] = []
    for col, etiqueta in etiquetas:
        campos.append(
            {
                "etiqueta": etiqueta,
                "valor": _formatear_academico(col, fila.get(col)),
                "columna": col,
            }
        )
    for extra in extras or []:
        if extra in _CAMPOS_ACADEMICO_SET:
            continue
        valor = _formatear_valor_ficha(fila.get(extra))
        if valor == "—":
            continue
        campos.append(
            {
                "etiqueta": etiqueta_export_columna(extra),
                "valor": valor,
                "columna": extra,
            }
        )
    return {
        "clave": "academico",
        "titulo": "Académico",
        "tipo": "campos",
        "campos": campos,
    }


def _valor_crudo(val) -> str:
    if _es_nulo(val) or val is False:
        if val is False:
            return "No"
        return ""
    if val is True:
        return "Sí"
    return str(val).strip()


def _opciones_con_actual(opciones: tuple[str, ...] | list[str], actual: str) -> list[str]:
    out = list(opciones)
    if actual and actual not in out:
        out.append(actual)
    return out


def _campo_edicion(fila: dict, col: str, cfg: dict) -> dict[str, Any]:
    raw = _valor_crudo(fila.get(col))
    campo: dict[str, Any] = {
        "etiqueta": etiqueta_export_columna(col),
        "valor": _formatear_valor_ficha(fila.get(col)) if col not in _COLS_SI_NO else (
            "Sí" if _es_valor_true(fila.get(col)) else ("No" if not _es_nulo(fila.get(col)) else "—")
        ),
        "valor_raw": raw,
        "columna": col,
        "name_key": clave_campo_edicion(col),
        "input": "text",
        "opciones": [],
    }
    if col in _COLS_SI_NO:
        campo["input"] = "si_no"
        campo["valor_raw"] = "Sí" if _es_valor_true(fila.get(col)) else ("No" if not _es_nulo(fila.get(col)) else "")
        campo["opciones"] = ["", "Sí", "No"]
    elif col == "Motivo Prio.":
        motivos = [""] + [
            str(m)
            for m in (cfg.get("columnas_motivo_priorizado") or COLUMNAS_MOTIVO_PRIO_DEFAULT)
            if str(m).strip()
        ]
        campo["input"] = "select"
        campo["opciones"] = _opciones_con_actual(motivos, raw)
    elif col in _SELECT_ESTADOS:
        campo["input"] = "select"
        campo["opciones"] = _opciones_con_actual(_SELECT_ESTADOS[col], raw)
    elif col in _COLS_FECHA:
        campo["input"] = "date"
        campo["valor_raw"] = raw[:10] if raw else ""
    elif col in _COLS_NUMERO:
        campo["input"] = "number"
    return campo


def _seccion_editable(
    fila: dict,
    cfg: dict,
    *,
    clave: str,
    titulo: str,
    columnas: list[str],
    extras: list[str] | None = None,
) -> dict:
    campos = [_campo_edicion(fila, col, cfg) for col in columnas]
    extras_vista = _campos_no_vacios(fila, extras or [], omitir=set(columnas))
    return {
        "clave": clave,
        "titulo": titulo,
        "tipo": "campos",
        "editable": True,
        "grupo_edicion": "priorizado" if clave == "priorizado" else "ruta",
        "campos": campos,
        "extras": extras_vista,
    }


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
    extra = [
        col
        for col in columnas
        if not es_columna_materia_horario(col) and col not in _CAMPOS_ACADEMICO_SET
    ]
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
    """Arma el tablero: datos, categorías (académico / priorizado / ruta abajo) y horario."""
    grupo_materias = str(cfg.get("grupo_materias", "Materias")).strip().casefold()
    datos: list[dict[str, str]] = []
    otras: list[dict] = []
    otras_idx: dict[str, int] = {}
    horario = None
    extras_acad: list[str] = []
    extras_prio: list[str] = []
    extras_ruta: list[str] = []
    for nombre_grupo, columnas in construir_grupos_encabezado(cfg, num_materias):
        clave = nombre_grupo.strip().casefold()
        if clave == "datos":
            datos = _campos_no_vacios(
                fila, columnas, omitir=_CAMPOS_HERO | _CAMPOS_ACADEMICO_SET
            )
            continue
        if clave == "puntaje":
            continue
        if clave in {"academico", "académico"}:
            extras_acad.extend(c for c in columnas if c not in extras_acad)
            continue
        if clave in {"priorizados", "priorizado"}:
            extras_prio.extend(
                c for c in columnas if c not in _COLS_PRIORIZADO and c not in extras_prio
            )
            continue
        if clave in {"ruta de grado", "ruta"}:
            extras_ruta.extend(
                c
                for c in columnas
                if c not in COLUMNAS_RUTA_GRADO and c not in extras_ruta
            )
            continue
        if clave == "becas":
            sec = _seccion_becas(fila, columnas)
            if sec:
                otras.append(sec)
            continue
        if clave == "alertas":
            sec = _seccion_alertas(fila, columnas)
            if sec:
                otras.append(sec)
            continue
        if clave == grupo_materias or clave == "materias":
            horario = _seccion_horario(fila, columnas, num_materias)
            continue
        campos = _campos_no_vacios(fila, columnas)
        if not campos:
            continue
        if clave in otras_idx:
            dest = otras[otras_idx[clave]]["campos"]
            vistos = {c["columna"] for c in dest}
            dest.extend(c for c in campos if c["columna"] not in vistos)
            continue
        otras_idx[clave] = len(otras)
        otras.append(
            {"clave": clave, "titulo": nombre_grupo, "tipo": "campos", "campos": campos}
        )
    categorias = [
        _seccion_academico(fila, extras_acad),
        _seccion_editable(
            fila,
            cfg,
            clave="priorizado",
            titulo="Priorizado",
            columnas=_COLS_PRIORIZADO,
            extras=extras_prio,
        ),
        _seccion_editable(
            fila,
            cfg,
            clave="ruta",
            titulo="Ruta de grado",
            columnas=list(COLUMNAS_RUTA_GRADO),
            extras=extras_ruta,
        ),
        *otras,
    ]
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
    meta = None
    version_usada = None
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
    fila = overlay_ediciones_fila(fila, cargar_ediciones(base))
    nombre = str(fila.get("Nombre y apellidos") or "").strip()
    programa = str(fila.get("Programa") or "").strip()
    color = color_programa(programa)
    vista = construir_vista_ficha(cfg, fila, num_materias=max_materias)
    periodo_est = formatear_periodo_cod(fila.get(COL_PERIODO_ACTUAL))
    periodo = periodo_est or ""
    if not periodo and meta:
        periodo = str(meta.get("periodo") or "").strip()
    if not periodo:
        ult = ultima_version(base)
        periodo = str((ult or {}).get("periodo") or periodo_desde_fecha())
    if vista.get("horario"):
        vista["horario"]["periodo"] = periodo
    nivel = fila.get("Nivel prioridad")
    marca = obtener_marca_gradua(id_key, base=base)
    return {
        "identificacion": id_key,
        "nombre": nombre,
        "programa": programa,
        "periodo_ingreso": _formatear_valor_ficha(fila.get("Periodo ingreso")),
        "telefono": _formatear_valor_ficha(fila.get("Teléfono celular")),
        "correo_institucional": _formatear_valor_ficha(fila.get("Correo institucional")),
        "correo_personal": _formatear_valor_ficha(fila.get("Correo personal")),
        "periodo_grado": _formatear_valor_ficha(fila.get("Periodo grado")),
        "cohorte_graduacion": _formatear_valor_ficha(fila.get("Cohorte de graduación")),
        "estado_graduacion": _formatear_valor_ficha(fila.get("Estado graduación")),
        "periodo": periodo,
        "nivel_prioridad": None if _esta_vacio(nivel) else str(nivel).strip(),
        "puntaje_prioridad": None
        if _esta_vacio(fila.get("Puntaje prioridad"))
        else fmt_pts(_numero(fila.get("Puntaje prioridad"))),
        "version_id": version_usada,
        "color": color,
        "estilo": estilo_color(color),
        "proximo_grado": es_proximo_a_grado(fila),
        "se_gradua": None if marca is None else bool(marca.get("se_gradua")),
        "gradua_en": (marca or {}).get("actualizado_en") or "",
        "gradua_por": (marca or {}).get("usuario") or "",
        "notas": listar_notas(id_key, base=base),
        **vista,
    }
