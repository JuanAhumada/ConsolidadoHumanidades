"""Vista previa de columnas origen → consolidado para cada archivo fuente."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from consolidado.config.settings import (
    ALIAS_ETIQUETAS,
    COLUMNAS_ALERTAS,
    COLUMNAS_PRIORIZADO,
    COLUMNAS_PRIORIZADO_ENRIQUECIDO,
    carpeta_excels,
)
from consolidado.core.alertas import _columna_num_alertas
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.columnas import construir_mapa_columnas
from consolidado.core.constants import (
    COL_ACTIVACION_RUTA,
    COL_AJUSTE_RAZONABLE,
    COL_FECHA_ACTIVACION_RUTA,
    COL_FECHA_AJUSTE,
    COL_NUM_ALERTA_FINAL,
    COL_NUM_ALERTA_INICIAL,
    COL_TIPO_ALERTA_FINAL,
    COL_TIPO_ALERTA_INICIAL,
)
from consolidado.core.normalizacion import _es_nulo, _mapa_norm_a_real, _str_celda, normalizar_encabezado
from consolidado.core.priorizado_enriquecido import _col_por_palabras

_CANON_A_SALIDA: dict[str, str] = {
    "identificacion": "Identificación",
    "nombre_estudiante": "Nombre y apellidos",
    "fecha_nacimiento": "Fecha de nacimiento",
    "telefono_celular": "Teléfono celular",
    "programa": "Programa",
    "correo_institucional": "Correo institucional",
    "correo_personal": "Correo personal",
    "periodo_ingreso": "Periodo ingreso",
    "reintegros": "Reintegros",
    "lugar_nacimiento": "Lugar de nacimiento",
    "lugar_residencia": "Lugar de residencia",
    "tipo_beca_credito": "Tipo de beca o crédito",
    "funcionario_beca": "Funcionario que tiene a cargo la beca",
}


def _ejemplo_celda(df: pl.DataFrame, col: str | None) -> str:
    if not col or col not in df.columns:
        return ""
    for val in df[col].head(5).to_list():
        if not _es_nulo(val) and str(val).strip():
            texto = _str_celda(val)
            return texto[:80] + ("…" if len(texto) > 80 else "")
    return ""


def _fila_mapa(columna_salida: str, origen: str, ejemplo: str = "") -> dict[str, str]:
    return {
        "columna_salida": columna_salida,
        "origen": origen or "(no detectada)",
        "ejemplo": ejemplo,
    }


def _mapa_listado(df: pl.DataFrame) -> list[dict[str, str]]:
    cols = list(df.columns)
    m = construir_mapa_columnas(cols)
    nr = _mapa_norm_a_real(cols)
    filas: list[dict[str, str]] = []

    for canon, salida in _CANON_A_SALIDA.items():
        if canon == "nombre_estudiante":
            if canon in m:
                col = m[canon]
                if "apellidos" in nr and "nombres" in nr and nr["nombres"] == col:
                    origen = f"{nr['nombres']} + {nr['apellidos']}"
                else:
                    origen = col
                filas.append(_fila_mapa(salida, origen, _ejemplo_celda(df, col)))
            elif "nombres" in nr and "apellidos" in nr:
                origen = f"{nr['nombres']} + {nr['apellidos']}"
                ej = _ejemplo_celda(df, nr["nombres"])
                filas.append(_fila_mapa(salida, origen, ej))
            else:
                filas.append(_fila_mapa(salida, "", ""))
            continue
        if canon in m:
            col = m[canon]
            filas.append(_fila_mapa(salida, col, _ejemplo_celda(df, col)))
        else:
            filas.append(_fila_mapa(salida, "", ""))
    return filas


def _mapa_priorizados_bd2(df: pl.DataFrame) -> list[dict[str, str]]:
    cols = list(df.columns)
    m = construir_mapa_columnas(cols)
    col_id = m.get("identificacion", "")
    filas = [
        _fila_mapa("Priorizado", "(siempre verdadero si aparece)", "Sí"),
        _fila_mapa(
            "Motivo Prio.",
            "Columnas DISCAPACIDAD, MINORIA RACIAL, LGTBI+, etc.",
            "",
        ),
        _fila_mapa(
            "Detalle GPrio.",
            "TIPO DE DISCAPACIDAD + DETALLE GRUPO PRIORIZADO",
            "",
        ),
    ]
    if col_id:
        filas.insert(0, _fila_mapa("Identificación (clave)", col_id, _ejemplo_celda(df, col_id)))
    return filas


def _mapa_prio_enriquecido(df: pl.DataFrame, tipo: str) -> list[dict[str, str]]:
    cols = list(df.columns)
    col_id = _col_por_palabras(cols, "identificacion") or _col_por_palabras(cols, "num", "identificacion")
    if not col_id:
        col_id = construir_mapa_columnas(cols).get("identificacion", "")

    if tipo == "bd_prio_psi":
        defs = [
            (COL_AJUSTE_RAZONABLE, ["ajuste", "razonable"], ["ajuste", "recomendacion"]),
            (COL_FECHA_AJUSTE, ["fecha", "solicitud"], ["fecha", "ajuste"]),
            (COL_ACTIVACION_RUTA, ["activacion", "ruta"], ["activación", "ruta"]),
            (COL_FECHA_ACTIVACION_RUTA, ["fecha", "activacion"], ["fecha", "act"]),
        ]
    else:
        defs = [
            (COL_AJUSTE_RAZONABLE, ["ajustes", "razonables"], ["ajuste", "razonable"]),
            (COL_ACTIVACION_RUTA, ["ruta", "atencion"], ["ruta", "vida"]),
            (COL_FECHA_AJUSTE, [], []),
            (COL_FECHA_ACTIVACION_RUTA, [], []),
        ]

    filas: list[dict[str, str]] = []
    if col_id:
        filas.append(_fila_mapa("Identificación (clave)", col_id, _ejemplo_celda(df, col_id)))
    for salida, palabras_a, palabras_b in defs:
        col = _col_por_palabras(cols, *palabras_a) if palabras_a else None
        if not col and palabras_b:
            col = _col_por_palabras(cols, *palabras_b)
        filas.append(_fila_mapa(salida, col or "", _ejemplo_celda(df, col) if col else ""))
    return filas


def _mapa_alertas(df: pl.DataFrame, fase: str) -> list[dict[str, str]]:
    cols = list(df.columns)
    col_cedula = None
    for alias in ("cedula", "cédula", "identificacion", "identificación", "documento"):
        for c in cols:
            if normalizar_encabezado(c) == normalizar_encabezado(alias):
                col_cedula = c
                break
        if col_cedula:
            break
    col_num = _columna_num_alertas(cols)
    if fase == "final":
        col_num_salida, col_tipo_salida = COL_NUM_ALERTA_FINAL, COL_TIPO_ALERTA_FINAL
    else:
        col_num_salida, col_tipo_salida = COL_NUM_ALERTA_INICIAL, COL_TIPO_ALERTA_INICIAL

    filas: list[dict[str, str]] = []
    if col_cedula:
        filas.append(_fila_mapa("Identificación (clave)", col_cedula, _ejemplo_celda(df, col_cedula)))
    filas.append(
        _fila_mapa(col_num_salida, col_num or "", _ejemplo_celda(df, col_num) if col_num else "")
    )
    origen_tipos = "(columnas con valor 1 después de Nº Alertas)" if col_num else ""
    filas.append(_fila_mapa(col_tipo_salida, origen_tipos, ""))
    for c in COLUMNAS_ALERTAS:
        if c not in (col_num_salida, col_tipo_salida):
            filas.append(_fila_mapa(c, "(vacío si no hay archivo final)", ""))
    return filas


def obtener_vista_previa_slot(slot: dict, cfg: dict, base: Path) -> tuple[list[dict[str, str]], str | None]:
    """
    Devuelve filas {columna_salida, origen, ejemplo} y mensaje de error si aplica.
    """
    carpeta = carpeta_excels(cfg, base)
    p = carpeta / slot.get("nombre_guardado", "")
    if not p.is_file():
        return [], "Aún no hay archivo cargado. Use «Cargar» primero."

    tipo = slot.get("tipo", "")
    hoja = slot.get("hoja")
    try:
        df = _leer_hoja_datos(p, tipo=tipo, hoja=hoja)
    except Exception as exc:
        return [], str(exc)

    if df.height == 0:
        return [], "El archivo no tiene filas en la hoja seleccionada."

    if tipo in ("bd1", "bd12", "bd3"):
        return _mapa_listado(df), None
    if tipo == "bd2":
        return _mapa_priorizados_bd2(df), None
    if tipo in ("bd_prio_psi", "bd_prio_lic"):
        return _mapa_prio_enriquecido(df, tipo), None
    if tipo in ("bd_alertas_com", "bd_alertas_psi"):
        return _mapa_alertas(df, slot.get("fase", "inicial")), None
    if tipo == "bd_rep":
        return [
            _fila_mapa(
                "(sin columnas en consolidado)",
                "Identificación + materia repetida",
                "Marca en negrita/subrayado las materias repetidas",
            )
        ], None
    return [], f"Tipo de archivo no soportado para vista previa: {tipo}"
