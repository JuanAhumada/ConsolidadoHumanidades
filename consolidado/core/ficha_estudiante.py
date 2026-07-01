"""Ficha consolidada de un estudiante para consulta en la interfaz."""

from __future__ import annotations

from pathlib import Path

from consolidado.config.settings import construir_grupos_encabezado, etiqueta_export_columna
from consolidado.core.constants import aplicar_config, es_columna_materia_horario
from consolidado.core.normalizacion import _es_nulo, _es_valor_true, normalizar_id
from consolidado.core.pipeline import generar_dataframe_consolidado


def _formatear_valor_ficha(val) -> str:
    if _es_nulo(val):
        return "—"
    if val is True or _es_valor_true(val):
        return "Sí"
    if val is False:
        return "No"
    texto = str(val).strip()
    return texto if texto else "—"


def construir_secciones_ficha(
    cfg: dict,
    fila: dict,
    *,
    num_materias: int,
) -> list[dict]:
    """Agrupa los datos del estudiante según los títulos del Excel."""
    secciones: list[dict] = []
    for nombre_grupo, columnas in construir_grupos_encabezado(cfg, num_materias):
        campos: list[dict[str, str]] = []
        for col in columnas:
            etiqueta = etiqueta_export_columna(col)
            valor = _formatear_valor_ficha(fila.get(col))
            if valor == "—" and es_columna_materia_horario(col):
                continue
            campos.append({"etiqueta": etiqueta, "valor": valor})
        if campos:
            secciones.append({"titulo": nombre_grupo, "campos": campos})
    return secciones


def obtener_ficha_estudiante(
    cfg: dict,
    base: Path,
    identificacion: str,
) -> dict | None:
    """
    Devuelve la ficha del estudiante o None si no está en el consolidado.
    Incluye nombre, id y secciones con campos etiquetados.
    """
    cfg = aplicar_config(cfg, base)
    id_key = normalizar_id(identificacion)
    if not id_key:
        return None

    consolidado, max_materias = generar_dataframe_consolidado(cfg, base=base)
    if consolidado.height == 0 or "Identificación" not in consolidado.columns:
        return None

    filtrado = consolidado.filter(
        consolidado["Identificación"].map_elements(normalizar_id, return_dtype=str) == id_key
    )
    if filtrado.height == 0:
        return None

    fila = filtrado.row(0, named=True)
    nombre = str(fila.get("Nombre y apellidos") or "").strip()
    return {
        "identificacion": id_key,
        "nombre": nombre,
        "programa": str(fila.get("Programa") or "").strip(),
        "secciones": construir_secciones_ficha(cfg, fila, num_materias=max_materias),
    }
