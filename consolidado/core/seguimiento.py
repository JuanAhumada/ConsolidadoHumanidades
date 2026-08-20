"""
Seguimiento: estudiantes con nivel de prioridad ≥ 1.

Categorías: General (puntaje total), componentes de puntaje y Alertas.
El listado web muestra nombre + puntaje; el check es global (contactados).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from consolidado.core.colores_programa import color_programa, estilo_color
from consolidado.core.constants import (
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
)
from consolidado.core.prioridad import fmt_pts
from consolidado.core.normalizacion import _es_nulo, _es_valor_true, es_estudiante_activo, normalizar_id
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.alertas_fuente import partir_tipos_alerta
from consolidado.storage.alertas_propias import cargar_alertas_propias
from consolidado.storage.contactados import cargar_ids_contactados
from consolidado.storage.db import cargar_dataframe_version, ultima_version

CATEGORIAS_SEGUIMIENTO: tuple[dict[str, str], ...] = (
    {"id": "general", "titulo": "General", "columna": "Puntaje prioridad", "grupo": "general"},
    {"id": "beca", "titulo": "Beca", "columna": "Ptje Beca", "grupo": "puntaje"},
    {"id": "priorizado", "titulo": "Priorizado", "columna": "Ptje Priorizado", "grupo": "puntaje"},
    {"id": "repitiendo", "titulo": "Repitiendo", "columna": "Ptje Repitiendo", "grupo": "puntaje"},
    {"id": "reintegro", "titulo": "Reintegro", "columna": "Ptje Reintegro", "grupo": "puntaje"},
    {"id": "propio", "titulo": "Propio", "columna": "Ptje Propio", "grupo": "puntaje"},
    {"id": "activacion", "titulo": "Activación", "columna": "Ptje Activacion", "grupo": "puntaje"},
    {"id": "ruta", "titulo": "Ruta", "columna": "Ptje Ruta", "grupo": "puntaje"},
    {"id": "alertas", "titulo": "Alertas", "columna": "", "grupo": "alertas"},
)

def _numero(val: Any) -> float:
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


def _entero(val: Any) -> int:
    return int(_numero(val))


def _texto(val: Any) -> str:
    if _es_nulo(val):
        return ""
    if isinstance(val, bool):
        return "Sí" if val else ""
    texto = str(val).strip()
    if texto.lower() in {"none", "nan", "null", "nat", "—"}:
        return ""
    return texto


def categoria_seguimiento(cat_id: str) -> dict[str, str]:
    clave = (cat_id or "general").strip().lower()
    for cat in CATEGORIAS_SEGUIMIENTO:
        if cat["id"] == clave:
            return cat
    return dict(CATEGORIAS_SEGUIMIENTO[0])


def _fila_base(fila: dict[str, Any], ids_contactados: set[str]) -> dict[str, Any] | None:
    ident = normalizar_id(fila.get("Identificación"))
    if not ident:
        return None
    if not es_estudiante_activo(fila.get("Activos")):
        return None
    nivel = _entero(fila.get("Nivel prioridad"))
    if nivel < 1:
        return None
    programa = _texto(fila.get("Programa"))
    color = color_programa(programa)
    puntaje = _numero(fila.get("Puntaje prioridad"))
    alertas_ini = partir_tipos_alerta(fila.get(COL_TIPO_ALERTA_INICIAL))
    alertas_fin = partir_tipos_alerta(fila.get(COL_TIPO_ALERTA_FINAL))
    alerta_propia = _texto(fila.get("Alerta Propia")) or _texto(fila.get("Detalle Propio"))
    n_alertas = (
        len(alertas_ini)
        + len(alertas_fin)
        + (1 if alerta_propia else 0)
        or _entero(fila.get(COL_NUM_ALERTA_INICIAL))
        + _entero(fila.get(COL_NUM_ALERTA_FINAL))
    )
    return {
        "identificacion": ident,
        "nombre": _texto(fila.get("Nombre y apellidos")) or ident,
        "programa": programa,
        "nivel": nivel,
        "puntaje": puntaje,
        "ptje_beca": _numero(fila.get("Ptje Beca")),
        "ptje_priorizado": _numero(fila.get("Ptje Priorizado")),
        "ptje_repitiendo": _numero(fila.get("Ptje Repitiendo")),
        "ptje_reintegro": _numero(fila.get("Ptje Reintegro")),
        "ptje_propio": _numero(fila.get("Ptje Propio")),
        "ptje_activacion": _numero(fila.get("Ptje Activacion")),
        "ptje_ruta": _numero(fila.get("Ptje Ruta")),
        "puntaje_txt": fmt_pts(puntaje),
        "priorizado": _es_valor_true(fila.get("Priorizado")),
        "motivo": _texto(fila.get("Motivo Prio.")),
        "detalle_gprio": _texto(fila.get("Detalle GPrio.")),
        "detalle_prioridad": _texto(fila.get("Detalle prioridad")),
        "telefono": _texto(fila.get("Teléfono celular")),
        "correo_institucional": _texto(fila.get("Correo institucional")),
        "correo_personal": _texto(fila.get("Correo personal")),
        "periodo_ingreso": _texto(fila.get("Periodo ingreso")),
        "periodo_actual": _texto(fila.get("Periodo actual")),
        "reintegros": _texto(fila.get("Reintegros")),
        "tipo_beca": _texto(fila.get("Tipo de beca o crédito")),
        "total_beca": _texto(fila.get("Total beca")),
        "funcionario_beca": _texto(fila.get("Funcionario que tiene a cargo la beca")),
        "repitiendo": _es_valor_true(fila.get("Repitiendo")),
        "alertas_inicial": alertas_ini,
        "alertas_final": alertas_fin,
        "alerta_propia": alerta_propia,
        "num_alertas": n_alertas,
        "contactado": ident in ids_contactados,
        "color": color,
        "estilo": estilo_color(color),
    }


def _puntaje_categoria(item: dict[str, Any], cat: dict[str, str]) -> float:
    cid = cat["id"]
    if cid == "general":
        return float(item["puntaje"])
    if cid == "alertas":
        return float(item["num_alertas"])
    mapa = {
        "beca": "ptje_beca",
        "priorizado": "ptje_priorizado",
        "repitiendo": "ptje_repitiendo",
        "reintegro": "ptje_reintegro",
        "propio": "ptje_propio",
        "activacion": "ptje_activacion",
        "ruta": "ptje_ruta",
    }
    return float(item.get(mapa.get(cid, "puntaje"), 0) or 0)


def _entra_en_categoria(item: dict[str, Any], cat: dict[str, str]) -> bool:
    cid = cat["id"]
    if cid == "general":
        return True
    if cid == "alertas":
        return item["num_alertas"] > 0 or bool(item["alerta_propia"])
    if cid == "priorizado":
        return item["ptje_priorizado"] > 0 or item["priorizado"]
    return _puntaje_categoria(item, cat) > 0


def listar_seguimiento(
    *,
    cat_id: str = "general",
    vista: str = "pendientes",
    programas: list[str] | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Estudiantes de la última versión con nivel ≥ 1, filtrados por categoría."""
    base = base or PROJECT_ROOT
    cat = categoria_seguimiento(cat_id)
    programas_sel = [p.strip() for p in (programas or []) if p and str(p).strip()]
    vacio = {
        "categoria": cat,
        "categorias": [
            {**c, "n": 0, "n_pendientes": 0} for c in CATEGORIAS_SEGUIMIENTO
        ],
        "filas": [],
        "total": 0,
        "visibles": 0,
        "vista": vista,
        "meta": None,
        "programas": [],
        "programas_sel": [],
    }
    ult = ultima_version(base)
    if ult is None:
        return vacio

    df = cargar_dataframe_version(int(ult["id"]), base)
    ids_contactados = cargar_ids_contactados(base)
    propias = {
        normalizar_id(a.get("identificacion")): a
        for a in cargar_alertas_propias(base)
        if normalizar_id(a.get("identificacion"))
    }

    universo: list[dict[str, Any]] = []
    for fila in df.iter_rows(named=True):
        item = _fila_base(fila, ids_contactados)
        if item is None:
            continue
        propia = propias.get(item["identificacion"])
        if propia and not item["alerta_propia"]:
            item["alerta_propia"] = _texto(propia.get("detalle"))
            item["num_alertas"] = int(item["num_alertas"]) + 1
        universo.append(item)

    programas_opciones = sorted({f["programa"] for f in universo if f["programa"]})
    programas_sel = [p for p in programas_sel if p in programas_opciones]
    if programas_sel:
        universo_f = [f for f in universo if f["programa"] in programas_sel]
    else:
        universo_f = universo

    cats_out: list[dict[str, Any]] = []
    for c in CATEGORIAS_SEGUIMIENTO:
        miembros = [f for f in universo_f if _entra_en_categoria(f, c)]
        cats_out.append(
            {
                **c,
                "n": len(miembros),
                "n_pendientes": sum(1 for f in miembros if not f["contactado"]),
            }
        )

    filtradas = [f for f in universo_f if _entra_en_categoria(f, cat)]
    filtradas.sort(
        key=lambda f: (
            -_puntaje_categoria(f, cat),
            -float(f["puntaje"]),
            -int(f["nivel"]),
            f["nombre"].casefold(),
        )
    )
    tope = max((_puntaje_categoria(f, cat) for f in filtradas), default=1.0) or 1.0
    for f in filtradas:
        valor = _puntaje_categoria(f, cat)
        f["puntaje_lista"] = valor
        f["puntaje_txt"] = fmt_pts(valor)
        f["pct"] = round(min(valor / tope, 1.0) * 100) if tope else 0

    if vista != "todos":
        visibles = [f for f in filtradas if not f["contactado"]]
    else:
        visibles = filtradas

    return {
        "categoria": cat,
        "categorias": cats_out,
        "filas": visibles,
        "total": len(filtradas),
        "visibles": len(visibles),
        "vista": "todos" if vista == "todos" else "pendientes",
        "meta": ult,
        "programas": programas_opciones,
        "programas_sel": programas_sel,
    }
