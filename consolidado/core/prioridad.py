"""
Puntaje y nivel de prioridad.

Suma componentes (beca, priorizado, repitiendo, reintegro, propio, activación,
ruta de grado) y asigna color de fila. Cambiar pesos o umbrales solo aquí.
"""

from __future__ import annotations

import polars as pl

from consolidado.config.settings import (
    COLORES_PRIORIDAD_DEFAULT,
    COLORES_PRIORIDAD_LEGACY,
    COLUMNAS_RUTA_GRADO,
)
from consolidado.core.constants import (
    COL_ACTIVACION_RUTA,
    COL_ACTIVOS,
    COL_AJUSTE_RAZONABLE,
    COL_DETALLE_PRIORIDAD,
    COL_FUNCIONARIO_BECA,
    COL_NIVEL_PRIORIDAD,
    COL_PTJE_ACTIVACION,
    COL_PTJE_BECA,
    COL_PTJE_PRIORIZADO,
    COL_PTJE_PROPIO,
    COL_PTJE_REINTEGRO,
    COL_PTJE_REPITIENDO,
    COL_PTJE_RUTA,
    COL_PUNTAJE_PRIORIDAD,
    COL_REPITIENDO,
    COL_TOTAL_BECA,
    COLUMNAS_PUNTAJE_COMPONENTES,
    MOTIVO_PRIORIZADO_INTERNO,
    MOTIVO_PRIORIZADO_PROPIO,
)
from consolidado.core.normalizacion import (
    _es_nulo,
    _es_valor_true,
    es_estudiante_activo,
    es_responsable_beca_especial,
    normalizar_encabezado,
    normalizar_id,
    parsear_monto_beca,
)
from consolidado.core.priorizado_enriquecido import (
    VALOR_AJUSTE_RAZONABLE,
    VALOR_RECOMENDACION,
)

PESO_ACTIVACION_RUTA = 20
PESO_PRIORIZADO_PROPIO = 3
PESO_DISCAPACIDAD = 3
PESO_OTRO_GRUPO_PRIORIZADO = 1
PESO_AJUSTE_ADAPTACION = 2
PESO_RECOMENDACION_ADAPTACION = 1

_COLORES_RUNTIME: dict[str, str] = dict(COLORES_PRIORIDAD_DEFAULT)

_OTROS_GRUPOS_PRIORIZADO = (
    "MINORIA RACIAL",
    "LGTBI+",
    "VICTIMA DE CONFLICTO ARMADO",
    "ZONA DE DIFICIL ACCESO",
    "N.A.",
)

METADATA_NIVELES: list[dict] = [
    {"nivel": 5, "nombre": "Crítico", "rango": "≥ 20 (activación)"},
    {"nivel": 4, "nombre": "Muy alto", "rango": "10 – 19"},
    {"nivel": 3, "nombre": "Alto", "rango": "7 – 9"},
    {"nivel": 2, "nombre": "Medio", "rango": "4 – 6"},
    {"nivel": 1, "nombre": "Bajo", "rango": "1 – 3"},
    {"nivel": 0, "nombre": "Sin señal", "rango": "0"},
]

METADATA_COLORES_FILA: list[dict] = [
    {
        "clave": "rojo",
        "etiqueta": "Rojo",
        "nota": "Activación de ruta y/o 2 o más puntajes ≥ 3. Tono según el puntaje más alto.",
    },
    {
        "clave": "morado",
        "etiqueta": "Morado",
        "nota": "Priorizado (o propio) como componente con puntaje más alto.",
    },
    {
        "clave": "naranja",
        "etiqueta": "Naranja",
        "nota": "Beca como componente con puntaje más alto.",
    },
    {
        "clave": "reintegro",
        "etiqueta": "Azul reintegro",
        "nota": "Reintegro como componente con puntaje más alto.",
    },
    {
        "clave": "repitiendo",
        "etiqueta": "Azul repitiendo",
        "nota": "Repitiendo como componente con puntaje más alto (tono distinto al reintegro).",
    },
    {
        "clave": "ruta",
        "etiqueta": "Esmeralda",
        "nota": "Ruta de grado como componente con puntaje más alto.",
    },
    {
        "clave": "amarillo",
        "etiqueta": "Amarillo",
        "nota": "2 o más componentes empatados con puntaje 2.",
    },
    {
        "clave": "verde",
        "etiqueta": "Verde",
        "nota": "2 o más componentes empatados con puntaje 1.",
    },
    {
        "clave": "gris",
        "etiqueta": "Gris",
        "nota": "Solo si la beca (0/NO/Call Center, puntaje ya dividido) es la única señal de la fila.",
    },
]

_COMPONENTES_PUNTAJE = (
    "beca",
    "priorizado",
    "repitiendo",
    "reintegro",
    "propio",
    "activacion",
    "ruta",
)

_COMPONENTE_A_COLOR: dict[str, str] = {
    "priorizado": "morado",
    "propio": "morado",
    "beca": "naranja",
    "repitiendo": "repitiendo",
    "reintegro": "reintegro",
    "activacion": "rojo",
    "ruta": "ruta",
}

_VALOR_MAX_COMPONENTE: dict[str, float] = {
    "beca": 3,
    "priorizado": (
        PESO_DISCAPACIDAD
        + len(_OTROS_GRUPOS_PRIORIZADO) * PESO_OTRO_GRUPO_PRIORIZADO
        + PESO_AJUSTE_ADAPTACION
        + PESO_RECOMENDACION_ADAPTACION
    ),
    "repitiendo": 3,
    "reintegro": 3,
    "propio": PESO_PRIORIZADO_PROPIO,
    "activacion": PESO_ACTIVACION_RUTA,
    "ruta": 4,
}

_COL_PCT_CREDITOS = COLUMNAS_RUTA_GRADO[0]
_COL_ESTADO_OPCION = COLUMNAS_RUTA_GRADO[1]
_COL_ESTADO_INGLES = COLUMNAS_RUTA_GRADO[3]
_COL_SABER_PRO = COLUMNAS_RUTA_GRADO[4]
_ESTADOS_FINALIZADO = frozenset({"finalizado"})
_ESTADOS_MATRICULADO = frozenset({"matriculado"})
_ESTADOS_PAGADO = frozenset({"pagado"})

BLOQUES_PUNTUACION_GUI: list[dict] = [
    {
        "titulo": "Beca",
        "nota": "Según Total beca. Se divide a la mitad si el responsable es 0, NO o Call Center.",
        "items": [
            {"etiqueta": "0 a < 1 millón", "puntos": 1},
            {"etiqueta": "1 a < 5 millones", "puntos": 2},
            {"etiqueta": "≥ 5 millones", "puntos": 3},
        ],
    },
    {
        "titulo": "Priorizado",
        "nota": "Discapacidad +3; otros grupos +1 c/u; ajuste razonable +2; recomendación +1.",
        "items": [
            {"etiqueta": "Discapacidad", "puntos": PESO_DISCAPACIDAD},
            {"etiqueta": "Otro grupo priorizado", "puntos": PESO_OTRO_GRUPO_PRIORIZADO},
            {"etiqueta": "Ajuste razonable (Adaptación)", "puntos": PESO_AJUSTE_ADAPTACION},
            {"etiqueta": "Recomendación (Adaptación)", "puntos": PESO_RECOMENDACION_ADAPTACION},
        ],
    },
    {
        "titulo": "Repitiendo",
        "nota": "Según columna Repitiendo (EST_MATRICULA).",
        "items": [
            {"etiqueta": "5 o más", "puntos": 1},
            {"etiqueta": "1 o 2", "puntos": 2},
            {"etiqueta": "3 o 4", "puntos": 3},
        ],
    },
    {
        "titulo": "Reintegro",
        "nota": None,
        "items": [
            {"etiqueta": "1 reintegro", "puntos": 1},
            {"etiqueta": "2 o más", "puntos": 3},
        ],
    },
    {
        "titulo": "Propio",
        "nota": None,
        "items": [{"etiqueta": "Priorizado propio", "puntos": PESO_PRIORIZADO_PROPIO}],
    },
    {
        "titulo": "Activación",
        "nota": None,
        "items": [{"etiqueta": "Activación de ruta = Sí", "puntos": PESO_ACTIVACION_RUTA}],
    },
    {
        "titulo": "Ruta de grado",
        "nota": "Suma créditos, opción de grado, inglés y Saber Pro. Umbrales estrictos (> 90 % / > 70 %).",
        "items": [
            {"etiqueta": "% créditos aprobados > 90", "puntos": 1},
            {"etiqueta": "% créditos aprobados > 70 y ≤ 90", "puntos": 0.5},
            {"etiqueta": "Opción de grado / inglés Finalizado", "puntos": 1},
            {"etiqueta": "Opción de grado / inglés Matriculado", "puntos": 0.5},
            {"etiqueta": "Saber Pro Finalizado", "puntos": 1},
            {"etiqueta": "Saber Pro Pagado", "puntos": 0.5},
        ],
    },
]

FORMULA_PUNTAJE_GUI = (
    "Puntaje prioridad = Beca + Priorizado + Repitiendo + Reintegro + Propio + Activación + Ruta"
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
    for legacy, nueva in COLORES_PRIORIDAD_LEGACY.items():
        if normalizar_hex_excel(personalizados.get(nueva)):
            continue
        normalizado = normalizar_hex_excel(personalizados.get(legacy))
        if normalizado:
            colores[nueva] = normalizado
    azul_legacy = normalizar_hex_excel(personalizados.get("azul"))
    if azul_legacy:
        if not normalizar_hex_excel(personalizados.get("reintegro")):
            colores["reintegro"] = azul_legacy
        if not normalizar_hex_excel(personalizados.get("repitiendo")):
            colores["repitiendo"] = azul_legacy
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
    return list(METADATA_NIVELES)


def colores_fila_para_gui() -> list[dict]:
    colores = colores_prioridad_efectivos()
    return [
        {
            **meta,
            "color": colores.get(meta["clave"]),
        }
        for meta in METADATA_COLORES_FILA
    ]


def _hex_a_rgb(hex_color: str) -> tuple[int, int, int]:
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def _rgb_a_hex(r: int, g: int, b: int) -> str:
    return f"{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def _mezclar_hex(hex_a: str, hex_b: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _hex_a_rgb(hex_a)
    br, bg, bb = _hex_a_rgb(hex_b)
    return _rgb_a_hex(
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )


def _tono_color(base_hex: str, valor: int, valor_max: int) -> str:
    """Mayor puntaje → tono más intenso; menor → más claro."""
    if valor <= 0 or valor_max <= 0:
        return base_hex
    ratio = min(max(valor / valor_max, 0.0), 1.0)
    claro = _mezclar_hex("FFFFFF", base_hex, 0.35)
    if ratio >= 1.0:
        return _mezclar_hex(base_hex, "000000", 0.12)
    if valor_max == 1:
        return claro
    return _mezclar_hex(claro, base_hex, ratio)


def _numero_componente(val) -> float:
    if _es_nulo(val):
        return 0.0
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return 0.0


def _puntajes_componentes_fila(row: dict) -> dict[str, float]:
    return {
        "beca": _numero_componente(row.get(COL_PTJE_BECA)),
        "priorizado": _numero_componente(row.get(COL_PTJE_PRIORIZADO)),
        "repitiendo": _numero_componente(row.get(COL_PTJE_REPITIENDO)),
        "reintegro": _numero_componente(row.get(COL_PTJE_REINTEGRO)),
        "propio": _numero_componente(row.get(COL_PTJE_PROPIO)),
        "activacion": _numero_componente(row.get(COL_PTJE_ACTIVACION)),
        "ruta": _numero_componente(row.get(COL_PTJE_RUTA)),
    }


def _beca_especial_fila(row: dict, puntajes: dict[str, float]) -> bool:
    return puntajes["beca"] > 0 and _funcionario_reduce_beca(row.get(COL_FUNCIONARIO_BECA))


def _solo_beca_especial(puntajes: dict[str, float], row: dict) -> bool:
    if not _beca_especial_fila(row, puntajes):
        return False
    return not any(puntajes[nombre] > 0 for nombre in _COMPONENTES_PUNTAJE if nombre != "beca")


def _puntajes_para_color(puntajes: dict[str, float], row: dict) -> dict[str, float]:
    """Excluye beca 0/NO/Call Center de la competencia si hay otra señal."""
    ajustados = dict(puntajes)
    if _beca_especial_fila(row, puntajes) and not _solo_beca_especial(puntajes, row):
        ajustados["beca"] = 0
    return ajustados


def _componentes_en_maximo(puntajes: dict[str, float]) -> list[str]:
    maximo = max(puntajes.values(), default=0)
    if maximo <= 0:
        return []
    return [nombre for nombre in _COMPONENTES_PUNTAJE if puntajes[nombre] == maximo]


def color_call_center_excel() -> str:
    return colores_prioridad_efectivos()["gris"]


def _es_priorizado(val) -> bool:
    return val is True or _es_valor_true(val)


def color_excel_fila(row: dict) -> str | None:
    """
    Color de fondo de la fila en el Excel consolidado según componentes de puntaje.
    """
    colores = colores_prioridad_efectivos()
    puntajes = _puntajes_componentes_fila(row)
    valores = list(puntajes.values())
    if not any(valores):
        return None

    if _solo_beca_especial(puntajes, row):
        return _tono_color(
            colores["gris"],
            puntajes["beca"],
            _VALOR_MAX_COMPONENTE["beca"],
        )

    puntajes_color = _puntajes_para_color(puntajes, row)
    valores_color = list(puntajes_color.values())
    if not any(valores_color):
        return None

    activacion = _es_priorizado(row.get(COL_ACTIVACION_RUTA)) or puntajes_color["activacion"] > 0
    cantidad_ge_3 = sum(1 for valor in valores if valor >= 3)

    if activacion or cantidad_ge_3 >= 2:
        valor_tono = puntajes_color["activacion"] if activacion else max(
            (valor for valor in valores if valor >= 3),
            default=3,
        )
        max_tono = PESO_ACTIVACION_RUTA if activacion else 3
        return _tono_color(colores["rojo"], valor_tono, max_tono)

    ganadores = _componentes_en_maximo(puntajes_color)
    maximo = max(valores_color)

    if len(ganadores) >= 2 and maximo == 2:
        return _tono_color(colores["amarillo"], 2, 3)
    if len(ganadores) >= 2 and maximo == 1:
        return _tono_color(colores["verde"], 1, 3)

    if len(ganadores) != 1:
        return None

    componente = ganadores[0]
    valor = puntajes_color[componente]
    clave_color = _COMPONENTE_A_COLOR.get(componente)
    if not clave_color:
        return None
    return _tono_color(
        colores[clave_color],
        valor,
        _VALOR_MAX_COMPONENTE.get(componente, 3),
    )


def _es_priorizado_propio(motivo, id_key: str, ids_propios: set[str]) -> bool:
    if id_key and id_key in ids_propios:
        return True
    if _es_nulo(motivo):
        return False
    texto = str(motivo).lower()
    return (
        MOTIVO_PRIORIZADO_PROPIO.lower() in texto
        or MOTIVO_PRIORIZADO_INTERNO.lower() in texto
    )


def _parsear_monto_beca(val) -> float | None:
    return parsear_monto_beca(val)


def _funcionario_reduce_beca(funcionario) -> bool:
    return es_responsable_beca_especial(funcionario)


def _puntos_beca(total, funcionario) -> int:
    monto = _parsear_monto_beca(total)
    if monto is None:
        return 0
    if monto < 1_000_000:
        puntos = 1
    elif monto < 5_000_000:
        puntos = 2
    else:
        puntos = 3
    if _funcionario_reduce_beca(funcionario):
        puntos = round(puntos / 2)
    return puntos


def _puntos_priorizado(motivo, adaptacion, es_priorizado_fila: bool) -> int:
    puntos = 0
    if es_priorizado_fila:
        texto = str(motivo or "").upper()
        if "DISCAPACIDAD" in texto:
            puntos += PESO_DISCAPACIDAD
        for grupo in _OTROS_GRUPOS_PRIORIZADO:
            if grupo in texto:
                puntos += PESO_OTRO_GRUPO_PRIORIZADO
    adaptacion_txt = str(adaptacion or "")
    if VALOR_AJUSTE_RAZONABLE in adaptacion_txt:
        puntos += PESO_AJUSTE_ADAPTACION
    if VALOR_RECOMENDACION in adaptacion_txt:
        puntos += PESO_RECOMENDACION_ADAPTACION
    return puntos


def _puntos_repitiendo(val) -> int:
    if _es_nulo(val):
        return 0
    try:
        n = int(val)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    if n >= 5:
        return 1
    if n in (1, 2):
        return 2
    if n in (3, 4):
        return 3
    return 0


def _puntos_reintegro(val) -> int:
    if _es_nulo(val):
        return 0
    try:
        n = int(float(str(val).strip()))
    except ValueError:
        return 0
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return 3


def _puntos_propio(es_propio: bool) -> int:
    return PESO_PRIORIZADO_PROPIO if es_propio else 0


def _puntos_activacion(val) -> int:
    return PESO_ACTIVACION_RUTA if _es_priorizado(val) else 0


def fmt_pts(n: float | int) -> str:
    """1 → '1'; 0.5 → '0.5'; 1.5 → '1.5'."""
    valor = float(n)
    if abs(valor - round(valor)) < 1e-9:
        return str(int(round(valor)))
    return f"{valor:.1f}"


def _pct_creditos_num(val) -> float:
    if _es_nulo(val):
        return 0.0
    if isinstance(val, bool):
        return 0.0
    if isinstance(val, (int, float)):
        n = float(val)
        if -1.5 <= n <= 1.5:
            n *= 100
        return n
    texto = str(val).strip().replace("%", "").replace(",", ".")
    texto = " ".join(texto.split())
    try:
        n = float(texto)
    except ValueError:
        return 0.0
    if -1.5 <= n <= 1.5:
        n *= 100
    return n


def _puntos_pct_creditos(val) -> float:
    pct = _pct_creditos_num(val)
    if pct > 90:
        return 1.0
    if pct > 70:
        return 0.5
    return 0.0


def _puntos_estado_ruta(val, *, uno: frozenset[str], medio: frozenset[str]) -> float:
    if _es_nulo(val):
        return 0.0
    estado = normalizar_encabezado(val)
    if estado in uno:
        return 1.0
    if estado in medio:
        return 0.5
    return 0.0


def _puntos_ruta(row: dict) -> float:
    return (
        _puntos_pct_creditos(row.get(_COL_PCT_CREDITOS))
        + _puntos_estado_ruta(
            row.get(_COL_ESTADO_OPCION),
            uno=_ESTADOS_FINALIZADO,
            medio=_ESTADOS_MATRICULADO,
        )
        + _puntos_estado_ruta(
            row.get(_COL_ESTADO_INGLES),
            uno=_ESTADOS_FINALIZADO,
            medio=_ESTADOS_MATRICULADO,
        )
        + _puntos_estado_ruta(
            row.get(_COL_SABER_PRO),
            uno=_ESTADOS_FINALIZADO,
            medio=_ESTADOS_PAGADO,
        )
    )


def _nivel_desde_puntaje(puntaje: float, ptje_activacion: int) -> int:
    if ptje_activacion >= PESO_ACTIVACION_RUTA:
        return 5
    if puntaje >= 10:
        return 4
    if puntaje >= 7:
        return 3
    if puntaje >= 4:
        return 2
    if puntaje >= 1:
        return 1
    return 0


def _detalle_componentes(
    ptje_beca: int,
    ptje_prio: int,
    ptje_rep: int,
    ptje_reint: int,
    ptje_propio: int,
    ptje_act: int,
    ptje_ruta: float,
) -> str:
    partes: list[str] = []
    if ptje_beca:
        partes.append(f"Beca={fmt_pts(ptje_beca)}")
    if ptje_prio:
        partes.append(f"Priorizado={fmt_pts(ptje_prio)}")
    if ptje_rep:
        partes.append(f"Repitiendo={fmt_pts(ptje_rep)}")
    if ptje_reint:
        partes.append(f"Reintegro={fmt_pts(ptje_reint)}")
    if ptje_propio:
        partes.append(f"Propio={fmt_pts(ptje_propio)}")
    if ptje_act:
        partes.append(f"Activación={fmt_pts(ptje_act)}")
    if ptje_ruta:
        partes.append(f"Ruta={fmt_pts(ptje_ruta)}")
    return "; ".join(partes)


def _prioridad_nula(*, detalle: str | None = None) -> dict:
    return {
        COL_PTJE_BECA: 0,
        COL_PTJE_PRIORIZADO: 0,
        COL_PTJE_REPITIENDO: 0,
        COL_PTJE_REINTEGRO: 0,
        COL_PTJE_PROPIO: 0,
        COL_PTJE_ACTIVACION: 0,
        COL_PTJE_RUTA: 0.0,
        COL_PUNTAJE_PRIORIDAD: 0,
        COL_NIVEL_PRIORIDAD: 0,
        COL_DETALLE_PRIORIDAD: detalle,
    }


def _calcular_prioridad_fila(row: dict, ids_propios: set[str]) -> dict:
    if not es_estudiante_activo(row.get(COL_ACTIVOS)):
        return _prioridad_nula(detalle="Graduado")

    id_key = normalizar_id(row.get("Identificación"))
    motivo = row.get("Motivo Prio.")
    es_propio = _es_priorizado_propio(motivo, id_key, ids_propios)
    es_priorizado_fila = _es_priorizado(row.get("Priorizado")) or es_propio

    ptje_beca = _puntos_beca(row.get(COL_TOTAL_BECA), row.get(COL_FUNCIONARIO_BECA))
    ptje_prio = _puntos_priorizado(
        motivo, row.get(COL_AJUSTE_RAZONABLE), es_priorizado_fila
    )
    ptje_rep = _puntos_repitiendo(row.get(COL_REPITIENDO))
    ptje_reint = _puntos_reintegro(row.get("Reintegros"))
    ptje_propio = _puntos_propio(es_propio)
    ptje_act = _puntos_activacion(row.get(COL_ACTIVACION_RUTA))
    ptje_ruta = _puntos_ruta(row)

    puntaje = (
        ptje_beca + ptje_prio + ptje_rep + ptje_reint + ptje_propio + ptje_act + ptje_ruta
    )
    detalle = _detalle_componentes(
        ptje_beca, ptje_prio, ptje_rep, ptje_reint, ptje_propio, ptje_act, ptje_ruta
    )

    return {
        COL_PTJE_BECA: ptje_beca,
        COL_PTJE_PRIORIZADO: ptje_prio,
        COL_PTJE_REPITIENDO: ptje_rep,
        COL_PTJE_REINTEGRO: ptje_reint,
        COL_PTJE_PROPIO: ptje_propio,
        COL_PTJE_ACTIVACION: ptje_act,
        COL_PTJE_RUTA: ptje_ruta,
        COL_PUNTAJE_PRIORIDAD: puntaje,
        COL_NIVEL_PRIORIDAD: _nivel_desde_puntaje(puntaje, ptje_act),
        COL_DETALLE_PRIORIDAD: detalle or None,
    }


def aplicar_prioridad(
    consolidado: pl.DataFrame,
    ids_propios: set[str] | None = None,
) -> pl.DataFrame:
    """Añade componentes de puntaje, puntaje total, nivel y detalle a cada fila."""
    if consolidado.height == 0:
        return consolidado

    ids = ids_propios or set()
    componentes: dict[str, list] = {col: [] for col in COLUMNAS_PUNTAJE_COMPONENTES}
    puntajes: list[float] = []
    niveles: list[int] = []
    detalles: list[str | None] = []

    for row in consolidado.iter_rows(named=True):
        calc = _calcular_prioridad_fila(row, ids)
        for col in COLUMNAS_PUNTAJE_COMPONENTES:
            componentes[col].append(calc[col])
        puntajes.append(calc[COL_PUNTAJE_PRIORIDAD])
        niveles.append(calc[COL_NIVEL_PRIORIDAD])
        detalles.append(calc[COL_DETALLE_PRIORIDAD])

    columnas_nuevas = [
        pl.Series(
            col,
            vals,
            dtype=pl.Float64 if col == COL_PTJE_RUTA else pl.Int32,
        ).alias(col)
        for col, vals in componentes.items()
    ]
    columnas_nuevas.extend(
        [
            pl.Series(COL_PUNTAJE_PRIORIDAD, puntajes, dtype=pl.Float64),
            pl.Series(COL_NIVEL_PRIORIDAD, niveles, dtype=pl.Int8),
            pl.Series(COL_DETALLE_PRIORIDAD, detalles, dtype=pl.Utf8),
        ]
    )
    cols_reemplazar = [c for c, _ in zip(
        list(COLUMNAS_PUNTAJE_COMPONENTES)
        + [COL_PUNTAJE_PRIORIDAD, COL_NIVEL_PRIORIDAD, COL_DETALLE_PRIORIDAD],
        columnas_nuevas,
    ) if c in consolidado.columns]
    base = consolidado.drop(cols_reemplazar) if cols_reemplazar else consolidado
    return base.with_columns(columnas_nuevas)
