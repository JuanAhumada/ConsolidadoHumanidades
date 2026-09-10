"""
Estudiantes próximos a grado (ruta de grado + permanencia).

Cercanía: cohorte o periodo de grado en este semestre o los dos siguientes,
créditos altos, o requisitos de grado (opción, inglés, Saber Pro) en curso.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from consolidado.core.colores_programa import color_programa, estilo_color
from consolidado.core.constants import COL_ACTIVOS
from consolidado.core.normalizacion import (
    _es_nulo,
    es_estudiante_activo,
    formatear_periodo_cod,
    normalizar_encabezado,
    normalizar_id,
)
from consolidado.core.prioridad import (
    _clave_semestres,
    _pct_creditos_num,
    _periodo_calendario,
    fmt_pts,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import cargar_dataframe_version, ultima_version
from consolidado.storage.ediciones import cargar_ediciones, overlay_ediciones_fila
from consolidado.storage.graduacion import cargar_marcas_gradua
from consolidado.storage.notas import resumen_notas

_COL_PCT = "% créditos aprobados"
_COL_OPCION = "Estado opción de grado"
_COL_INGLES = "Estado de inglés"
_COL_SABER = "Saber Pro"
_COL_PERIODO_GRADO = "Periodo grado"
_COL_COHORTE = "Cohorte de graduación"
_COL_ESTADO_GRAD = "Estado graduación"

_ESTADOS_AVANCE = frozenset(
    {"finalizado", "matriculado", "pagado", "en curso", "cursando"}
)
_DELTA_SEMESTRES_MAX = 2


def _texto(val: Any) -> str:
    if _es_nulo(val):
        return ""
    if isinstance(val, bool):
        return "Sí" if val else "No"
    texto = str(val).strip()
    if texto.lower() in {"none", "nan", "null", "nat", "—"}:
        return ""
    return texto


def _estado_en_curso(val: Any) -> bool:
    return normalizar_encabezado(val) in _ESTADOS_AVANCE


def motivo_proximidad(fila: dict[str, Any], *, periodo: str | None = None) -> list[str]:
    """Por qué entra en proyección (para la tarjeta)."""
    corte = periodo or _periodo_calendario()
    actual = _clave_semestres(corte)
    motivos: list[str] = []
    destino = _clave_semestres(fila.get(_COL_COHORTE))
    if actual is not None and destino is not None:
        delta = destino - actual
        if delta <= 0:
            motivos.append("Cohorte de graduación en este semestre o anterior")
        elif delta == 1:
            motivos.append("Cohorte de graduación el semestre siguiente")
        elif delta == 2:
            motivos.append("Cohorte de graduación en dos semestres")
    periodo_grado = _clave_semestres(fila.get(_COL_PERIODO_GRADO))
    if actual is not None and periodo_grado is not None:
        dpg = periodo_grado - actual
        if dpg <= 1:
            motivos.append("Periodo de grado cercano")
    pct = _pct_creditos_num(fila.get(_COL_PCT))
    if pct > 90:
        motivos.append("Más del 90 % de créditos")
    elif pct > 70:
        motivos.append("Más del 70 % de créditos")
    if _estado_en_curso(fila.get(_COL_OPCION)):
        motivos.append("Opción de grado en curso o finalizada")
    if _estado_en_curso(fila.get(_COL_INGLES)):
        motivos.append("Inglés en curso o finalizado")
    if _estado_en_curso(fila.get(_COL_SABER)):
        motivos.append("Saber Pro pagado o finalizado")
    return motivos


def es_proximo_a_grado(fila: dict[str, Any], *, periodo: str | None = None) -> bool:
    if not es_estudiante_activo(fila.get(COL_ACTIVOS)):
        return False
    estado = normalizar_encabezado(fila.get(_COL_ESTADO_GRAD))
    if estado in {"graduado", "grado"}:
        return False
    corte = periodo or _periodo_calendario()
    actual = _clave_semestres(corte)
    destino = _clave_semestres(fila.get(_COL_COHORTE))
    if actual is not None and destino is not None and (destino - actual) <= _DELTA_SEMESTRES_MAX:
        return True
    periodo_grado = _clave_semestres(fila.get(_COL_PERIODO_GRADO))
    if actual is not None and periodo_grado is not None and (periodo_grado - actual) <= 1:
        return True
    if _pct_creditos_num(fila.get(_COL_PCT)) > 70:
        return True
    return False


def listar_proyeccion(
    *,
    vista: str = "aun_no",
    programas: list[str] | None = None,
    orden: str = "cohorte",
    base: Path | None = None,
) -> dict[str, Any]:
    """Próximos a grado de la última versión, partidos por «Se gradúa este semestre»."""
    base = base or PROJECT_ROOT
    corte = _periodo_calendario()
    programas_sel = [p.strip() for p in (programas or []) if p and str(p).strip()]
    vacio = {
        "filas": [],
        "total": 0,
        "visibles": 0,
        "n_si": 0,
        "n_aun_no": 0,
        "vista": "si" if vista == "si" else "aun_no",
        "periodo": corte,
        "meta": None,
        "programas": [],
        "programas_sel": [],
        "orden": "pct" if orden == "pct" else "cohorte",
    }
    ult = ultima_version(base)
    if ult is None:
        return vacio

    df = cargar_dataframe_version(int(ult["id"]), base)
    marcas = cargar_marcas_gradua(periodo=corte, base=base)
    notas = resumen_notas(base)
    ediciones = cargar_ediciones(base)
    universo: list[dict[str, Any]] = []
    for fila in df.iter_rows(named=True):
        fila = overlay_ediciones_fila(fila, ediciones)
        if not es_proximo_a_grado(fila, periodo=corte):
            continue
        ident = normalizar_id(fila.get("Identificación"))
        if not ident:
            continue
        programa = _texto(fila.get("Programa"))
        color = color_programa(programa)
        marca = marcas.get(ident)
        se_gradua = None if marca is None else bool(marca["se_gradua"])
        pct = _pct_creditos_num(fila.get(_COL_PCT))
        cohorte_clave = _clave_semestres(fila.get(_COL_COHORTE))
        item = {
            "identificacion": ident,
            "nombre": _texto(fila.get("Nombre y apellidos")) or ident,
            "programa": programa,
            "cohorte": _texto(fila.get(_COL_COHORTE)) or formatear_periodo_cod(fila.get(_COL_COHORTE)) or "—",
            "cohorte_clave": cohorte_clave,
            "periodo_grado": _texto(fila.get(_COL_PERIODO_GRADO)) or "—",
            "pct_creditos": pct,
            "pct_txt": f"{pct:.0f} %" if pct else "—",
            "opcion": _texto(fila.get(_COL_OPCION)) or "—",
            "ingles": _texto(fila.get(_COL_INGLES)) or "—",
            "saber": _texto(fila.get(_COL_SABER)) or "—",
            "motivos": motivo_proximidad(fila, periodo=corte),
            "se_gradua": se_gradua,
            "n_notas": int((notas.get(ident) or {}).get("n") or 0),
            "ultima_nota": (notas.get(ident) or {}).get("ultima") or "",
            "color": color,
            "estilo": estilo_color(color),
            "puntaje_txt": fmt_pts(pct) if pct else "—",
        }
        universo.append(item)

    programas_opciones = sorted({f["programa"] for f in universo if f["programa"]})
    programas_sel = [p for p in programas_sel if p in programas_opciones]
    if programas_sel:
        universo = [f for f in universo if f["programa"] in programas_sel]

    orden_ok = "pct" if orden == "pct" else "cohorte"

    def _clave_orden(f: dict[str, Any]) -> tuple:
        vacio = f.get("cohorte_clave") is None
        clave = int(f["cohorte_clave"] or 0)
        pct = -float(f["pct_creditos"] or 0)
        nombre = (f["nombre"] or "").casefold()
        if orden_ok == "pct":
            return (pct, vacio, clave, nombre)
        return (vacio, clave, pct, nombre)

    universo.sort(key=_clave_orden)
    n_si = sum(1 for f in universo if f["se_gradua"] is True)
    n_aun_no = len(universo) - n_si
    if vista == "si":
        visibles = [f for f in universo if f["se_gradua"] is True]
    else:
        visibles = [f for f in universo if f["se_gradua"] is not True]

    return {
        "filas": visibles,
        "total": len(universo),
        "visibles": len(visibles),
        "n_si": n_si,
        "n_aun_no": n_aun_no,
        "vista": "si" if vista == "si" else "aun_no",
        "periodo": corte,
        "meta": ult,
        "programas": programas_opciones,
        "programas_sel": programas_sel,
        "orden": orden_ok,
    }
