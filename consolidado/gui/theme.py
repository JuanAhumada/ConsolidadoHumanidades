"""Apariencia compartida — look tipo aplicación web (CustomTkinter)."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk

from consolidado.gui.icons import limpiar_cache_iconos

# Tipografía con jerarquía clara (Calibri / Bahnschrift en Windows).
FONT_MARCA = ("Bahnschrift", 22, "bold")
FONT_TITULO = ("Bahnschrift", 26, "bold")
FONT_SUBTITULO = ("Calibri", 16, "bold")
FONT_TEXTO = ("Calibri", 14)
FONT_PEQUENA = ("Calibri", 12)
FONT_GUIA = ("Calibri", 12)
FONT_NAV = ("Calibri", 14)

# Paleta institucional (teal sobre slate claro) — evita púrpuras genéricos.
COLOR_OK = "#0d9f6e"
COLOR_FALTA = "#e11d48"
COLOR_OPCIONAL = "#64748b"
COLOR_ACENTO = "#0f766e"
COLOR_ACENTO_HOVER = "#0d9488"
COLOR_ACENTO_SUAVE = ("#ccfbf1", "#134e4a")
COLOR_TEXTO = ("#0f172a", "#e2e8f0")
COLOR_TEXTO_MUTED = ("#64748b", "#94a3b8")
COLOR_BORDE = ("#e2e8f0", "#334155")
COLOR_SIDEBAR = ("#0f172a", "#020617")
COLOR_SIDEBAR_ITEM = ("#1e293b", "#0f172a")
COLOR_SIDEBAR_ACTIVO = ("#0f766e", "#0d9488")
COLOR_PAGE = ("#f1f5f9", "#0b1220")
COLOR_CARD = ("#ffffff", "#111827")
COLOR_TOPBAR = ("#ffffff", "#0f172a")

_COLORES_FONDO = {
    "dark": "#0b1220",
    "light": "#f1f5f9",
}


def es_modo_oscuro() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def color_fondo_app() -> str:
    """Color de fondo principal según el tema activo."""
    return _COLORES_FONDO["dark" if es_modo_oscuro() else "light"]


def estilo_boton_primario() -> dict:
    return {
        "fg_color": COLOR_ACENTO,
        "hover_color": COLOR_ACENTO_HOVER,
        "text_color": "#ffffff",
        "corner_radius": 10,
        "border_width": 0,
    }


def estilo_boton_secundario() -> dict:
    """Botón outline visible en claro y oscuro."""
    return {
        "fg_color": ("#ffffff", "#1e293b"),
        "hover_color": ("#f1f5f9", "#334155"),
        "border_width": 1,
        "border_color": COLOR_BORDE,
        "text_color": COLOR_TEXTO,
        "corner_radius": 10,
    }


def estilo_boton_ghost() -> dict:
    return {
        "fg_color": "transparent",
        "hover_color": ("#e2e8f0", "#1e293b"),
        "border_width": 0,
        "text_color": COLOR_TEXTO_MUTED,
        "corner_radius": 10,
    }


def estilo_seccion() -> dict:
    return {
        "fg_color": COLOR_CARD,
        "border_width": 1,
        "border_color": COLOR_BORDE,
        "corner_radius": 16,
    }


def estilo_tarjeta_paso() -> dict:
    return {
        "border_width": 1,
        "corner_radius": 14,
        "fg_color": COLOR_CARD,
        "border_color": COLOR_BORDE,
    }


def estilo_sidebar() -> dict:
    return {
        "fg_color": COLOR_SIDEBAR,
        "corner_radius": 0,
    }


def estilo_nav_item(*, activo: bool = False) -> dict:
    if activo:
        return {
            "fg_color": COLOR_SIDEBAR_ACTIVO,
            "hover_color": COLOR_ACENTO_HOVER,
            "text_color": "#ffffff",
            "corner_radius": 12,
            "anchor": "w",
            "height": 42,
        }
    return {
        "fg_color": "transparent",
        "hover_color": COLOR_SIDEBAR_ITEM,
        "text_color": ("#cbd5e1", "#94a3b8"),
        "corner_radius": 12,
        "anchor": "w",
        "height": 42,
    }


def configurar_tabview(tabview: ctk.CTkTabview) -> None:
    """Pestañas legibles en modo claro y oscuro.

    Debe llamarse después de añadir al menos una pestaña; si no hay,
    CTkTabview lanza KeyError al reubicar la pestaña actual.
    """
    if not getattr(tabview, "_tab_dict", None):
        return
    tabview.configure(
        segmented_button_fg_color=("#e2e8f0", "#1e293b"),
        segmented_button_selected_color=(COLOR_ACENTO, COLOR_ACENTO),
        segmented_button_selected_hover_color=(COLOR_ACENTO_HOVER, COLOR_ACENTO_HOVER),
        segmented_button_unselected_color=("#f8fafc", "#111827"),
        segmented_button_unselected_hover_color=("#e2e8f0", "#334155"),
        text_color=COLOR_TEXTO,
    )


def normalizar_kwargs_boton(kwargs: dict) -> dict:
    """Convierte botones transparentes en secundarios visibles."""
    if kwargs.get("fg_color") == "transparent" and kwargs.get("border_width", 0):
        copia = dict(kwargs)
        copia.pop("fg_color", None)
        copia.pop("hover_color", None)
        copia.pop("border_width", None)
        copia.pop("border_color", None)
        copia.pop("text_color", None)
        copia.update(estilo_boton_secundario())
        return copia
    if kwargs.get("fg_color") == "transparent":
        copia = dict(kwargs)
        for k in ("fg_color", "hover_color", "border_width", "border_color", "text_color"):
            copia.pop(k, None)
        copia.update(estilo_boton_ghost())
        return copia
    return kwargs


def configurar_dpi_windows() -> None:
    """Mejora nitidez en pantallas con escalado alto (Windows)."""
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def configurar_apariencia(modo: str | None = None) -> None:
    configurar_dpi_windows()
    if modo == "dark":
        ctk.set_appearance_mode("Dark")
    elif modo == "light":
        ctk.set_appearance_mode("Light")
    else:
        ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("green")
    limpiar_cache_iconos()


def alternar_modo_apariencia() -> str:
    """Alterna entre claro y oscuro. Devuelve 'light' o 'dark'."""
    actual = ctk.get_appearance_mode()
    nuevo = "Light" if actual == "Dark" else "Dark"
    ctk.set_appearance_mode(nuevo)
    limpiar_cache_iconos()
    return nuevo.lower()


def modo_apariencia_actual() -> str:
    return ctk.get_appearance_mode().lower()


def configurar_treeview(tree: ttk.Treeview) -> None:
    """Adapta Treeview al tema claro/oscuro de CustomTkinter."""
    style = ttk.Style()
    style.theme_use("clam")
    if ctk.get_appearance_mode() == "Dark":
        bg, fg, field, heading = "#111827", "#e2e8f0", "#1e293b", "#1e293b"
        select_bg, select_fg = COLOR_ACENTO, "#ffffff"
    else:
        bg, fg, field, heading = "#ffffff", "#0f172a", "#f8fafc", "#f1f5f9"
        select_bg, select_fg = COLOR_ACENTO, "#ffffff"
    style.configure(
        "Consolidado.Treeview",
        background=bg,
        foreground=fg,
        fieldbackground=field,
        rowheight=32,
        borderwidth=0,
        font=("Calibri", 12),
    )
    style.configure(
        "Consolidado.Treeview.Heading",
        background=heading,
        foreground=fg,
        font=("Calibri", 11, "bold"),
        relief="flat",
    )
    style.map(
        "Consolidado.Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )
    tree.configure(style="Consolidado.Treeview")
