"""Apariencia compartida de CustomTkinter y estilos para widgets ttk."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk

from consolidado.gui.icons import limpiar_cache_iconos

FONT_TITULO = ("Segoe UI", 18, "bold")
FONT_SUBTITULO = ("Segoe UI", 14, "bold")
FONT_TEXTO = ("Segoe UI", 13)
FONT_PEQUENA = ("Segoe UI", 12)


def configurar_apariencia(modo: str | None = None) -> None:
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
