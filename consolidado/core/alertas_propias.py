"""Aplicación de alertas propias al consolidado."""

from __future__ import annotations

import polars as pl

from consolidado.core.constants import COL_ALERTA_PROPIA, COL_DETALLE_PROPIO
from consolidado.core.normalizacion import normalizar_id
from consolidado.storage.alertas_propias import cargar_alertas_propias


def aplicar_alertas_propias(
    consolidado: pl.DataFrame,
    alertas: list[dict] | None = None,
) -> pl.DataFrame:
    if consolidado.height == 0:
        return consolidado

    for col in (COL_ALERTA_PROPIA, COL_DETALLE_PROPIO):
        if col not in consolidado.columns:
            consolidado = consolidado.with_columns(pl.lit(None).alias(col))

    items = alertas if alertas is not None else []
    if not items:
        return consolidado

    mapa = {
        normalizar_id(a.get("identificacion", "")): a
        for a in items
        if normalizar_id(a.get("identificacion", ""))
    }
    if not mapa:
        return consolidado

    alerta_vals = consolidado.get_column(COL_ALERTA_PROPIA).to_list()
    detalle_vals = consolidado.get_column(COL_DETALLE_PROPIO).cast(pl.Utf8).to_list()
    ids = consolidado.get_column("Identificación").to_list()

    for i, id_val in enumerate(ids):
        key = normalizar_id(id_val)
        if key not in mapa:
            continue
        entrada = mapa[key]
        alerta_vals[i] = True
        detalle = entrada.get("detalle")
        if detalle:
            detalle_vals[i] = detalle

    return consolidado.with_columns(
        pl.Series(COL_ALERTA_PROPIA, alerta_vals, dtype=pl.Boolean),
        pl.Series(COL_DETALLE_PROPIO, detalle_vals, dtype=pl.Utf8),
    )


def obtener_lista_alertas_propias_vista(cfg: dict, base) -> list[dict]:
    """Lista de alertas propias para la interfaz."""
    from consolidado.core.priorizados import _mapa_nombres_estudiantes

    id_to_name = _mapa_nombres_estudiantes(cfg, base)
    vista: list[dict] = []
    for entrada in cargar_alertas_propias(base):
        key = normalizar_id(entrada.get("identificacion", ""))
        if not key:
            continue
        vista.append(
            {
                "identificacion": key,
                "nombre": entrada.get("nombre") or id_to_name.get(key, ""),
                "detalle": entrada.get("detalle") or "",
            }
        )
    return vista
