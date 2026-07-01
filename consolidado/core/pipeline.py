from __future__ import annotations

from consolidado.paths import PROJECT_ROOT
from pathlib import Path

import polars as pl

from consolidado.config.settings import carpeta_excels, construir_columnas_salida
from consolidado.core.alertas import _aplicar_alertas, _cargar_alertas_cfg
from consolidado.core.alertas_propias import aplicar_alertas_propias
from consolidado.core.archivos import (
    _limpiar_becas_programa_no_permitido,
    _tipo_libro_desde_nombre,
    preparar_archivo,
    procesar_tabla_priorizados_con_recuperacion,
)
from consolidado.core.columnas import alinear_dataframe_salida
from consolidado.core.constants import (
    COLUMNAS_EXCLUIDAS_LISTADO,
    COLUMNAS_PUNTAJE_COMPONENTES,
    COL_REPITIENDO,
    _TIPOS_FUENTE_AUXILIARES,
    aplicar_config,
    columnas_materia_horario,
    es_columna_materia_horario,
    max_materias_en_dataframe,
)
from consolidado.core.documentos import _unir_documentos_adicionales
from consolidado.core.excel_io import (
    abrir_archivo_en_sistema,
    resolver_ruta_salida_consolidado,
)
from consolidado.core.export import guardar_excel_consolidado
from consolidado.core.fusion import fusionar_por_id
from consolidado.core.priorizado_enriquecido import (
    _cargar_priorizado_enriquecido_cfg,
    aplicar_priorizado_enriquecido,
)
from consolidado.core.prioridad import aplicar_prioridad
from consolidado.core.priorizados import (
    aplicar_priorizados_propios,
    cargar_priorizados_internos_psi,
    _unificar_priorizados_propios,
)
from consolidado.core.repetidas import _cargar_materias_repetidas_cfg, _cargar_repitiendo_cfg, aplicar_repitiendo
from consolidado.core.normalizacion import normalizar_id
from consolidado.storage.priorizados import cargar_priorizados_propios
from consolidado.storage.alertas_propias import cargar_alertas_propias


def generar_dataframe_consolidado(
    cfg: dict | None = None,
    *,
    base: Path | None = None,
    archivos: list[Path] | None = None,
) -> tuple[pl.DataFrame, int]:
    """Arma el consolidado en memoria (sin guardar Excel)."""
    base = base or PROJECT_ROOT
    cfg = aplicar_config(cfg, base)

    if archivos is None:
        carpeta = carpeta_excels(cfg, base)
        archivos_por_slot: list[tuple[dict, Path]] = []
        for slot in cfg.get("archivos_fuente", []):
            p = carpeta / slot.get("nombre_guardado", "")
            if p.is_file():
                archivos_por_slot.append((slot, p))
        if not any(
            slot.get("tipo") not in _TIPOS_FUENTE_AUXILIARES and slot.get("tipo") != "bd2"
            for slot, _ in archivos_por_slot
        ):
            raise ValueError(
                "No hay archivos cargados. Use «Cargar Excels» en la interfaz "
                f"o copie los libros en {carpeta}."
            )
    else:
        archivos_por_slot = []
        for indice, p in enumerate(archivos):
            slot = (
                cfg["archivos_fuente"][indice]
                if indice < len(cfg.get("archivos_fuente", []))
                else {"tipo": _tipo_libro_desde_nombre(p), "titulo": p.name}
            )
            archivos_por_slot.append((slot, p))

    partes: list[pl.DataFrame] = []
    tipos_partes: list[str] = []
    horarios_partes: list[pl.DataFrame] = []
    priorizados: pl.DataFrame | None = None
    max_materias = 1

    for slot, p in archivos_por_slot:
        etiqueta = slot.get("titulo", p.name)
        tipo = slot.get("tipo") or _tipo_libro_desde_nombre(p)
        hoja = slot.get("hoja")
        if tipo in _TIPOS_FUENTE_AUXILIARES:
            continue
        if tipo == "bd2":
            priorizados, _ = procesar_tabla_priorizados_con_recuperacion(
                p, etiqueta, tipo=tipo, hoja=hoja
            )
            continue
        df_listado, df_horarios, _ = preparar_archivo(
            p, etiqueta, tipo=tipo, hoja=hoja
        )
        max_materias = max(max_materias, max_materias_en_dataframe(df_horarios))
        partes.append(df_listado)
        tipos_partes.append(tipo)
        if df_horarios.height > 0:
            horarios_partes.append(df_horarios)

    columnas_listado = construir_columnas_salida(cfg, 1)
    columnas_listado = [
        c
        for c in columnas_listado
        if not es_columna_materia_horario(c)
        and c not in COLUMNAS_EXCLUIDAS_LISTADO
        and c not in COLUMNAS_PUNTAJE_COMPONENTES
        and c not in ("Puntaje prioridad", "Nivel prioridad", "Detalle prioridad")
        and c != COL_REPITIENDO
    ]
    columnas_materias = columnas_materia_horario(max_materias)
    partes = [alinear_dataframe_salida(df, columnas_listado) for df in partes]

    consolidado = fusionar_por_id(
        partes,
        horarios_partes,
        priorizados=priorizados,
        columnas_listado=columnas_listado,
        columnas_materias=columnas_materias,
        tipos_partes=tipos_partes,
    )
    consolidado = _unir_documentos_adicionales(consolidado, cfg, base)
    consolidado = _limpiar_becas_programa_no_permitido(consolidado)
    consolidado = aplicar_priorizado_enriquecido(
        consolidado, _cargar_priorizado_enriquecido_cfg(cfg, base)
    )
    consolidado = _aplicar_alertas(consolidado, _cargar_alertas_cfg(cfg, base))
    consolidado = aplicar_alertas_propias(consolidado, cargar_alertas_propias(base))

    propios = _unificar_priorizados_propios(
        cargar_priorizados_propios(base),
        cargar_priorizados_internos_psi(cfg, base),
    )
    consolidado = aplicar_priorizados_propios(consolidado, propios)
    consolidado = aplicar_repitiendo(consolidado, _cargar_repitiendo_cfg(cfg, base))
    ids_propios = {
        normalizar_id(p.get("identificacion", ""))
        for p in propios
        if normalizar_id(p.get("identificacion", ""))
    }
    consolidado = aplicar_prioridad(consolidado, ids_propios)
    return consolidado, max_materias


def ejecutar_consolidado(
    cfg: dict | None = None,
    *,
    base: Path | None = None,
    archivos: list[Path] | None = None,
    salida: Path | None = None,
    abrir: bool = True,
    preguntar_sobrescribir: bool = False,
    parent=None,
) -> tuple[pl.DataFrame, Path]:
    """Procesa fuentes guardadas (o rutas indicadas) y genera el Excel consolidado."""
    base = base or PROJECT_ROOT
    cfg = aplicar_config(cfg, base)
    consolidado, max_materias = generar_dataframe_consolidado(cfg, base=base, archivos=archivos)
    materias_repetidas = _cargar_materias_repetidas_cfg(cfg, base)

    if salida is not None:
        destino = salida
    elif preguntar_sobrescribir:
        destino_resuelta = resolver_ruta_salida_consolidado(cfg, base, parent=parent)
        if destino_resuelta is None:
            raise SystemExit("Operación cancelada.")
        destino = destino_resuelta
    else:
        rel_salida = cfg.get("salida", {}).get("ruta", "salida/estudiantes_consolidado.xlsx")
        destino = base / rel_salida
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino = guardar_excel_consolidado(
        consolidado, destino, cfg=cfg, num_materias=max_materias,
        materias_repetidas=materias_repetidas,
    )
    if abrir:
        abrir_archivo_en_sistema(destino, parent=parent)
    return consolidado, destino
