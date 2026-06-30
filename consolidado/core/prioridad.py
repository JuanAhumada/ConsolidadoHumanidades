"""Cálculo de puntaje y nivel de prioridad por estudiante."""

from __future__ import annotations

import polars as pl

from consolidado.config.settings import COLORES_PRIORIDAD_DEFAULT
from consolidado.core.constants import (
    COL_ACTIVACION_RUTA,
    COL_DETALLE_PRIORIDAD,
    COL_FUNCIONARIO_BECA,
    COL_NIVEL_PRIORIDAD,
    COL_PUNTAJE_PRIORIDAD,
    COL_TIPO_BECA,
    MOTIVO_PRIORIZADO_PROPIO,
)
from consolidado.core.normalizacion import (
    _es_funcionario_call_center,
    _es_nulo,
    _es_valor_true,
    normalizar_id,
)

PESO_ACTIVACION_RUTA = 1000
PESO_PRIORIZADO_PROPIO = 120

PESOS_MOTIVO: dict[str, int] = {
    "AJUSTES RAZONABLES": 90,
    "DISCAPACIDAD": 80,
    "VICTIMA DE CONFLICTO ARMADO": 75,
    "LGTBI+": 70,
    "MINORIA RACIAL": 65,
    "ZONA DE DIFICIL ACCESO": 60,
    "N.A.": 20,
}

TOPE_MOTIVOS = 120

PESO_CONVENIO_EMPRESAS = 55
PESO_CONVENIO_COLEGIOS = 50
PESO_CONVENIO_MUNICIPAL = 50
PESO_FUNCIONARIO_ASIGNADO = 30
PESO_OTRA_BECA = 20
PESO_ICETEX = 5

_COLORES_RUNTIME: dict[str, str] = dict(COLORES_PRIORIDAD_DEFAULT)

METADATA_NIVELES: list[dict] = [
    {"nivel": 5, "nombre": "Crítico", "rango": "≥ 1000", "clave": "nivel_5"},
    {"nivel": 4, "nombre": "Muy alto", "rango": "120 – 999", "clave": "nivel_4"},
    {"nivel": 3, "nombre": "Alto", "rango": "70 – 119", "clave": "nivel_3"},
    {"nivel": 2, "nombre": "Medio", "rango": "25 – 69", "clave": "nivel_2"},
    {"nivel": 1, "nombre": "Bajo", "rango": "1 – 24", "clave": "nivel_1"},
    {"nivel": 0, "nombre": "Sin señal", "rango": "0", "clave": None},
]

METADATA_OTROS_COLORES: list[dict] = [
    {
        "clave": "alerta",
        "etiqueta": "Alerta (inicial o final)",
        "nota": "Si no hay activación de ruta.",
    },
    {
        "clave": "call_center",
        "etiqueta": "Funcionario Call Center",
        "nota": "Solo si la fila no tiene otro color de prioridad o alerta.",
    },
]

BLOQUES_PUNTUACION_GUI: list[dict] = [
    {
        "titulo": "Activación de ruta",
        "nota": "Peso dominante en el consolidado.",
        "items": [{"etiqueta": "Activación de ruta = Sí", "puntos": PESO_ACTIVACION_RUTA}],
    },
    {
        "titulo": "Priorizado y motivo",
        "nota": "Solo si está marcado como priorizado. Varios motivos se suman con tope de 120.",
        "items": [
            {"etiqueta": "Priorizado propio", "puntos": PESO_PRIORIZADO_PROPIO},
            {"etiqueta": "Ajustes razonables", "puntos": 90},
            {"etiqueta": "Discapacidad", "puntos": 80},
            {"etiqueta": "Víctima de conflicto armado", "puntos": 75},
            {"etiqueta": "LGTBI+", "puntos": 70},
            {"etiqueta": "Minoría racial", "puntos": 65},
            {"etiqueta": "Zona de difícil acceso", "puntos": 60},
            {"etiqueta": "N.A.", "puntos": 20},
        ],
    },
    {
        "titulo": "Beca",
        "nota": "Se toma la categoría que más puntos aporte (no se suman todas).",
        "items": [
            {"etiqueta": "Convenio empresas", "puntos": PESO_CONVENIO_EMPRESAS},
            {"etiqueta": "Convenio colegios / municipal", "puntos": PESO_CONVENIO_COLEGIOS},
            {"etiqueta": "Funcionario asignado (no Call Center)", "puntos": PESO_FUNCIONARIO_ASIGNADO},
            {"etiqueta": "Otra beca institucional", "puntos": PESO_OTRA_BECA},
            {"etiqueta": "ICETEX / crédito", "puntos": PESO_ICETEX},
            {"etiqueta": "Solo Call Center sin convenio", "puntos": 0},
        ],
    },
    {
        "titulo": "Reintegros",
        "nota": None,
        "items": [
            {"etiqueta": "1 reintegro", "puntos": 15},
            {"etiqueta": "2 reintegros", "puntos": 25},
            {"etiqueta": "3 o más", "puntos": 35},
        ],
    },
]

FORMULA_PUNTAJE_GUI = (
    "Puntaje prioridad = Activación de ruta + Motivos priorizado + Beca + Reintegros"
)


def normalizar_hex_excel(val) -> str | None:
    if _es_nulo(val):
        return None
    texto = str(val).strip().lstrip("#").upper()
    if len(texto) == 6 and all(c in "0123456789ABCDEF" for c in texto):
        return texto
    return None


def colores_prioridad_desde_cfg(cfg: dict | None = None) -> dict[str, str]:
    colores = dict(COLORES_PRIORIDAD_DEFAULT)
    if not cfg:
        return colores
    personalizados = cfg.get("colores_prioridad") or {}
    for clave in colores:
        normalizado = normalizar_hex_excel(personalizados.get(clave))
        if normalizado:
            colores[clave] = normalizado
    return colores


def aplicar_colores_prioridad(cfg: dict | None = None) -> dict[str, str]:
    global _COLORES_RUNTIME
    _COLORES_RUNTIME = colores_prioridad_desde_cfg(cfg)
    return _COLORES_RUNTIME


def colores_prioridad_efectivos() -> dict[str, str]:
    if not _COLORES_RUNTIME:
        return colores_prioridad_desde_cfg()
    return dict(_COLORES_RUNTIME)


def niveles_prioridad_para_gui() -> list[dict]:
    colores = colores_prioridad_efectivos()
    filas: list[dict] = []
    for meta in METADATA_NIVELES:
        clave = meta.get("clave")
        filas.append(
            {
                **meta,
                "color": colores.get(clave) if clave else None,
            }
        )
    return filas


def otros_colores_para_gui() -> list[dict]:
    colores = colores_prioridad_efectivos()
    return [
        {
            **meta,
            "color": colores.get(meta["clave"]),
        }
        for meta in METADATA_OTROS_COLORES
    ]


def color_nivel_excel(nivel: int) -> str | None:
    if nivel <= 0:
        return None
    return colores_prioridad_efectivos().get(f"nivel_{nivel}")


def color_call_center_excel() -> str:
    return colores_prioridad_efectivos()["call_center"]


def _es_priorizado(val) -> bool:
    return val is True or _es_valor_true(val)


def _tiene_alerta_fila(row: dict) -> bool:
    for col in (
        "Num Alerta inicial",
        "Tipo Alerta inicial",
        "Num Alerta final",
        "Tipo Alerta final",
    ):
        val = row.get(col)
        if _es_nulo(val):
            continue
        if col.startswith("Num"):
            try:
                if int(float(str(val).strip())) > 0:
                    return True
            except ValueError:
                pass
        elif str(val).strip():
            return True
    return False


def color_excel_fila(row: dict) -> str | None:
    """
    Color de fondo de la fila en el Excel consolidado.
    Prioridad: activación > alerta > nivel de prioridad.
    """
    colores = colores_prioridad_efectivos()
    if _es_priorizado(row.get(COL_ACTIVACION_RUTA)):
        return colores["nivel_5"]
    if _tiene_alerta_fila(row):
        return colores["alerta"]
    nivel = row.get(COL_NIVEL_PRIORIDAD)
    if not _es_nulo(nivel):
        try:
            n = int(nivel)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            return color_nivel_excel(n)
    return None


def _es_priorizado_propio(motivo, id_key: str, ids_propios: set[str]) -> bool:
    if id_key and id_key in ids_propios:
        return True
    if _es_nulo(motivo):
        return False
    return MOTIVO_PRIORIZADO_PROPIO.lower() in str(motivo).lower()


def _nivel_desde_puntaje(puntaje: int) -> int:
    if puntaje >= PESO_ACTIVACION_RUTA:
        return 5
    if puntaje >= PESO_PRIORIZADO_PROPIO:
        return 4
    if puntaje >= 70:
        return 3
    if puntaje >= 25:
        return 2
    if puntaje >= 1:
        return 1
    return 0


def _puntos_motivos(motivo, es_propio: bool) -> tuple[int, list[str]]:
    partes: list[str] = []
    total = 0
    if not _es_nulo(motivo):
        texto = str(motivo).upper()
        for clave, peso in PESOS_MOTIVO.items():
            if clave in texto:
                total += peso
                partes.append(clave if clave == "LGTBI+" else clave.title())
    if es_propio:
        total = max(total, PESO_PRIORIZADO_PROPIO)
        if "Priorizado propio" not in partes:
            partes.append("Priorizado propio")
    return min(total, TOPE_MOTIVOS), partes


def _puntos_beca(tipo, funcionario) -> tuple[int, list[str]]:
    if _es_nulo(tipo) and _es_nulo(funcionario):
        return 0, []

    tipo_l = str(tipo or "").lower()
    candidatos: list[tuple[int, str]] = []

    if any(p in tipo_l for p in ("conv.empresas", "conven.empresas", "conv empresas")):
        candidatos.append((PESO_CONVENIO_EMPRESAS, "Convenio empresas"))
    if any(p in tipo_l for p in ("conven.colegios", "conven colegios")):
        candidatos.append((PESO_CONVENIO_COLEGIOS, "Convenio colegios"))
    if "atlantico" in tipo_l or "municip" in tipo_l:
        candidatos.append((PESO_CONVENIO_MUNICIPAL, "Convenio municipal"))

    if not _es_nulo(funcionario) and not _es_funcionario_call_center(funcionario):
        candidatos.append((PESO_FUNCIONARIO_ASIGNADO, "Funcionario asignado"))

    if "icetex" in tipo_l or "estrella" in tipo_l:
        candidatos.append((PESO_ICETEX, "ICETEX / crédito"))

    if tipo_l.strip() and not candidatos:
        candidatos.append((PESO_OTRA_BECA, "Beca institucional"))

    if not candidatos:
        return 0, []

    peso, etiqueta = max(candidatos, key=lambda item: item[0])
    return peso, [etiqueta]


def _puntos_reintegro(val) -> tuple[int, str | None]:
    if _es_nulo(val):
        return 0, None
    try:
        n = int(float(str(val).strip()))
    except ValueError:
        return 0, None
    if n <= 0:
        return 0, None
    if n == 1:
        return 15, "Reintegro×1"
    if n == 2:
        return 25, "Reintegro×2"
    return 35, f"Reintegro×{n}"


def _calcular_prioridad_fila(row: dict, ids_propios: set[str]) -> tuple[int, int, str]:
    detalle: list[str] = []
    puntaje = 0

    id_key = normalizar_id(row.get("Identificación"))
    motivo = row.get("Motivo Prio.")
    es_propio = _es_priorizado_propio(motivo, id_key, ids_propios)

    if _es_priorizado(row.get(COL_ACTIVACION_RUTA)):
        puntaje += PESO_ACTIVACION_RUTA
        detalle.append("Activación de ruta")

    if _es_priorizado(row.get("Priorizado")) or es_propio:
        pts, partes = _puntos_motivos(motivo, es_propio)
        puntaje += pts
        detalle.extend(partes)

    pts_beca, partes_beca = _puntos_beca(
        row.get(COL_TIPO_BECA),
        row.get(COL_FUNCIONARIO_BECA),
    )
    puntaje += pts_beca
    detalle.extend(partes_beca)

    pts_reint, etiqueta_reint = _puntos_reintegro(row.get("Reintegros"))
    puntaje += pts_reint
    if etiqueta_reint:
        detalle.append(etiqueta_reint)

    return puntaje, _nivel_desde_puntaje(puntaje), "; ".join(detalle)


def aplicar_prioridad(
    consolidado: pl.DataFrame,
    ids_propios: set[str] | None = None,
) -> pl.DataFrame:
    """Añade puntaje, nivel y detalle de prioridad a cada fila."""
    if consolidado.height == 0:
        return consolidado

    ids = ids_propios or set()
    puntajes: list[int] = []
    niveles: list[int] = []
    detalles: list[str | None] = []
    for row in consolidado.iter_rows(named=True):
        puntaje, nivel, detalle = _calcular_prioridad_fila(row, ids)
        puntajes.append(puntaje)
        niveles.append(nivel)
        detalles.append(detalle or None)

    return consolidado.with_columns(
        pl.Series(COL_PUNTAJE_PRIORIDAD, puntajes, dtype=pl.Int32),
        pl.Series(COL_NIVEL_PRIORIDAD, niveles, dtype=pl.Int8),
        pl.Series(COL_DETALLE_PRIORIDAD, detalles, dtype=pl.Utf8),
    )
