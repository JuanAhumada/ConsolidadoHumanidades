"""Apariencia compartida de CustomTkinter y estilos para widgets ttk."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk

from consolidado.gui.icons import limpiar_cache_iconos

FONT_TITULO = ("Segoe UI", 20, "bold")
FONT_SUBTITULO = ("Segoe UI", 14, "bold")
FONT_TEXTO = ("Segoe UI", 13)
FONT_PEQUENA = ("Segoe UI", 12)
FONT_GUIA = ("Segoe UI", 11)

COLOR_OK = "#2ecc71"
COLOR_FALTA = "#e74c3c"
COLOR_OPCIONAL = "#95a5a6"
COLOR_ACENTO = "#3b8ed0"

_COLORES_FONDO = {
    "dark": "#2b2b2b",
    "light": "#dbdbdb",
}


def es_modo_oscuro() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def color_fondo_app() -> str:
    """Color de fondo principal según el tema activo."""
    return _COLORES_FONDO["dark" if es_modo_oscuro() else "light"]


def estilo_boton_secundario() -> dict:
    """Botón visible en modo claro y oscuro (sustituye fg_color='transparent')."""
    return {
        "fg_color": ("#e3e3e3", "#343638"),
        "hover_color": ("#cfcfcf", "#4a4d50"),
        "border_width": 1,
        "border_color": ("#a8a8a8", "#565b5e"),
        "text_color": ("#1a1a1a", "#dce4ee"),
    }


def estilo_seccion() -> dict:
    return {
        "fg_color": ("#ececec", "#2b2b2b"),
        "border_width": 1,
        "border_color": ("#c8c8c8", "#3f3f3f"),
        "corner_radius": 6,
    }


def estilo_tarjeta_paso() -> dict:
    return {
        "border_width": 1,
        "corner_radius": 8,
        "fg_color": ("#f4f4f4", "#333333"),
        "border_color": ("#b8b8b8", "#4a4a4a"),
    }


def configurar_tabview(tabview: ctk.CTkTabview) -> None:
    """Pestañas legibles en modo claro y oscuro."""
    tabview.configure(
        segmented_button_fg_color=("#d9d9d9", "#2b2b2b"),
        segmented_button_selected_color=(COLOR_ACENTO, COLOR_ACENTO),
        segmented_button_selected_hover_color=("#2f6fad", "#2f6fad"),
        segmented_button_unselected_color=("#e8e8e8", "#343638"),
        segmented_button_unselected_hover_color=("#d0d0d0", "#404040"),
        text_color=("#1a1a1a", "#dce4ee"),
    )


def normalizar_kwargs_boton(kwargs: dict) -> dict:
    """Convierte botones transparentes en secundarios visibles."""
    if kwargs.get("fg_color") == "transparent":
        copia = dict(kwargs)
        copia.pop("fg_color", None)
        copia.pop("hover_color", None)
        copia.pop("border_width", None)
        copia.pop("border_color", None)
        copia.pop("text_color", None)
        copia.update(estilo_boton_secundario())
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
    ctk.set_default_color_theme("blue")
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
        bg, fg, field, heading = "#2b2b2b", "#dce4ee", "#343638", "#3f3f3f"
        select_bg, select_fg = "#1f538d", "#ffffff"
    else:
        bg, fg, field, heading = "#ffffff", "#1a1a1a", "#f9f9fa", "#ebebeb"
        select_bg, select_fg = "#3b8ed0", "#ffffff"
    style.configure(
        "Consolidado.Treeview",
        background=bg,
        foreground=fg,
        fieldbackground=field,
        rowheight=28,
        borderwidth=0,
    )
    style.configure(
        "Consolidado.Treeview.Heading",
        background=heading,
        foreground=fg,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
    )
    style.map(
        "Consolidado.Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )
    tree.configure(style="Consolidado.Treeview")
