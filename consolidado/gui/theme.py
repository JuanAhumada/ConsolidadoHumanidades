"""Apariencia compartida — look tipo aplicación web (CustomTkinter)."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk

from consolidado.gui.icons import limpiar_cache_iconos

# Tipografía institucional (Red Hat Display; Segoe UI si no está instalada).
FONT_MARCA = ("Red Hat Display", 22, "bold")
FONT_TITULO = ("Red Hat Display", 26, "bold")
FONT_SUBTITULO = ("Red Hat Display", 16, "bold")
FONT_TEXTO = ("Red Hat Display", 14)
FONT_PEQUENA = ("Red Hat Display", 12)
FONT_GUIA = ("Red Hat Display", 12)
FONT_NAV = ("Red Hat Display", 14)

# Paleta institucional CUC: Auburn, oro, verde bosque y grises.
COLOR_OK = "#078930"
COLOR_FALTA = "#A3161A"
COLOR_OPCIONAL = "#A5A5A5"
COLOR_ACENTO = "#A3161A"
COLOR_ACENTO_HOVER = "#C41C21"
COLOR_ACENTO_SUAVE = ("#F6E4E5", "#6B0E12")
COLOR_TEXTO = ("#2A2A2A", "#F4F4F4")
COLOR_TEXTO_MUTED = ("#595959", "#A5A5A5")
COLOR_BORDE = ("#CCCCCC", "#595959")
COLOR_SIDEBAR = ("#2A0506", "#2A0506")
COLOR_SIDEBAR_ITEM = ("#6B0E12", "#3D080A")
COLOR_SIDEBAR_ACTIVO = ("#A3161A", "#C41C21")
COLOR_PAGE = ("#F4F4F4", "#2A0506")
COLOR_CARD = ("#ffffff", "#3D080A")
COLOR_TOPBAR = ("#ffffff", "#2A0506")

_COLORES_FONDO = {
    "dark": "#2A0506",
    "light": "#F4F4F4",
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
        "fg_color": ("#ffffff", "#3D080A"),
        "hover_color": ("#F4F4F4", "#6B0E12"),
        "border_width": 1,
        "border_color": COLOR_BORDE,
        "text_color": COLOR_TEXTO,
        "corner_radius": 10,
    }


def estilo_boton_ghost() -> dict:
    return {
        "fg_color": "transparent",
        "hover_color": ("#E8E8E8", "#6B0E12"),
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
        "text_color": ("#CCCCCC", "#A5A5A5"),
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
        segmented_button_fg_color=("#E8E8E8", "#3D080A"),
        segmented_button_selected_color=(COLOR_ACENTO, COLOR_ACENTO),
        segmented_button_selected_hover_color=(COLOR_ACENTO_HOVER, COLOR_ACENTO_HOVER),
        segmented_button_unselected_color=("#F7F7F7", "#2A0506"),
        segmented_button_unselected_hover_color=("#E8E8E8", "#6B0E12"),
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
        bg, fg, field, heading = "#3D080A", "#F4F4F4", "#6B0E12", "#6B0E12"
        select_bg, select_fg = COLOR_ACENTO, "#ffffff"
    else:
        bg, fg, field, heading = "#ffffff", "#2A2A2A", "#F7F7F7", "#F4F4F4"
        select_bg, select_fg = COLOR_ACENTO, "#ffffff"
    style.configure(
        "Consolidado.Treeview",
        background=bg,
        foreground=fg,
        fieldbackground=field,
        rowheight=32,
        borderwidth=0,
        font=("Red Hat Display", 12),
    )
    style.configure(
        "Consolidado.Treeview.Heading",
        background=heading,
        foreground=fg,
        font=("Red Hat Display", 11, "bold"),
        relief="flat",
    )
    style.map(
        "Consolidado.Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )
    tree.configure(style="Consolidado.Treeview")
