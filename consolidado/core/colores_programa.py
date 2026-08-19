"""
Color de acento por programa (ficha, listas, gráficas).

Psicología índigo, Comunicación terracota, Licenciatura azul.
estilo_color() escribe variables CSS --accent* en el inline style de la fila.
"""

from __future__ import annotations

import hashlib
from typing import Any

from consolidado.core.normalizacion import normalizar_encabezado

_FIJOS: dict[str, dict[str, str]] = {
    "psicologia": {
        "clave": "psicologia",
        "hex": "#4f46e5",
        "bright": "#6366f1",
        "soft": "#e0e7ff",
        "ink": "#312e81",
        "glow": "rgba(79, 70, 229, 0.30)",
        "corta": "Psicología",
    },
    "comunicacion social y medios digitales": {
        "clave": "comunicacion",
        "hex": "#c2410c",
        "bright": "#ea580c",
        "soft": "#ffedd5",
        "ink": "#7c2d12",
        "glow": "rgba(194, 65, 12, 0.30)",
        "corta": "Comunicación",
    },
    "licenciatura en educacion basica primaria": {
        "clave": "licenciatura",
        "hex": "#0369a1",
        "bright": "#0284c7",
        "soft": "#e0f2fe",
        "ink": "#0c4a6e",
        "glow": "rgba(3, 105, 161, 0.30)",
        "corta": "Licenciatura",
    },
}

_PALETA: tuple[dict[str, str], ...] = (
    {
        "clave": "vino",
        "hex": "#9f1239",
        "bright": "#e11d48",
        "soft": "#ffe4e6",
        "ink": "#881337",
        "glow": "rgba(159, 18, 57, 0.30)",
    },
    {
        "clave": "uva",
        "hex": "#6d28d9",
        "bright": "#8b5cf6",
        "soft": "#ede9fe",
        "ink": "#4c1d95",
        "glow": "rgba(109, 40, 217, 0.30)",
    },
    {
        "clave": "ocre",
        "hex": "#b45309",
        "bright": "#d97706",
        "soft": "#fef3c7",
        "ink": "#78350f",
        "glow": "rgba(180, 83, 9, 0.30)",
    },
    {
        "clave": "azul",
        "hex": "#1d4ed8",
        "bright": "#3b82f6",
        "soft": "#dbeafe",
        "ink": "#1e3a8a",
        "glow": "rgba(29, 78, 216, 0.30)",
    },
    {
        "clave": "esmeralda",
        "hex": "#0f766e",
        "bright": "#14b8a6",
        "soft": "#ccfbf1",
        "ink": "#134e4a",
        "glow": "rgba(15, 118, 110, 0.30)",
    },
)

_NEUTRO: dict[str, str] = {
    "clave": "neutro",
    "hex": "#334155",
    "bright": "#64748b",
    "soft": "#e2e8f0",
    "ink": "#1e293b",
    "glow": "rgba(51, 65, 85, 0.28)",
    "corta": "Sin programa",
}


def color_programa(programa: Any) -> dict[str, str]:
    """Devuelve un dict de color para el programa (hex, bright, soft, ink, glow)."""
    texto = str(programa or "").strip()
    if not texto or texto in {"—", "-"}:
        return dict(_NEUTRO)
    clave = normalizar_encabezado(texto)
    if clave in _FIJOS:
        out = dict(_FIJOS[clave])
        out.setdefault("corta", texto)
        return out
    indice = int(hashlib.md5(clave.encode("utf-8")).hexdigest(), 16) % len(_PALETA)
    out = dict(_PALETA[indice])
    out["corta"] = texto
    return out


def estilo_color(color: dict[str, str]) -> str:
    """Variables CSS para sustituir el verde de acento."""
    return (
        f"--accent: {color['hex']};"
        f"--accent-bright: {color['bright']};"
        f"--accent-soft: {color['soft']};"
        f"--accent-glow: {color['glow']};"
        f"--accent-ink: {color.get('ink') or color['hex']};"
    )


def colores_para_etiquetas(labels: list[str]) -> list[str]:
    return [color_programa(lab)["hex"] for lab in labels]


def colores_programas_fijos() -> list[dict[str, str]]:
    """Paleta fija de carreras de Humanidades, para la leyenda."""
    return [dict(item) for item in _FIJOS.values()]
