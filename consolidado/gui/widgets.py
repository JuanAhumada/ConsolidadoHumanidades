"""Widgets reutilizables para la interfaz."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import ttk
from tkinter import Label as TkLabel
from tkinter import Toplevel as TkToplevel
from typing import Callable

import customtkinter as ctk

from consolidado.gui.theme import FONT_PEQUENA, FONT_SUBTITULO, FONT_TEXTO, configurar_treeview


class IconButton(ctk.CTkButton):
    """Botón cuadrado solo con icono y tooltip al pasar el mouse."""

    def __init__(
        self,
        master,
        *,
        icon: ctk.CTkImage,
        tooltip: str,
        command: Callable[[], None] | None = None,
        width: int = 36,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            text="",
            image=icon,
            width=width,
            height=width,
            command=command,
            **kwargs,
        )
        self._tooltip = tooltip
        self.bind("<Enter>", self._mostrar_tooltip)
        self.bind("<Leave>", self._ocultar_tooltip)
        self.bind("<Destroy>", self._ocultar_tooltip)
        self._tip_win: TkToplevel | None = None

    def set_tooltip(self, texto: str) -> None:
        self._tooltip = texto

    def _mostrar_tooltip(self, _event=None) -> None:
        if self._tip_win is not None:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        x = self.winfo_rootx() + self.winfo_width() // 2
        y = self.winfo_rooty() + self.winfo_height() + 4
        root = self.winfo_toplevel()
        self._tip_win = TkToplevel(root)
        self._tip_win.wm_overrideredirect(True)
        self._tip_win.wm_geometry(f"+{x}+{y}")
        self._tip_win.attributes("-topmost", True)
        TkLabel(
            self._tip_win,
            text=self._tooltip,
            font=FONT_PEQUENA,
            bg="#d9d9d9",
            fg="#1a1a1a",
            padx=6,
            pady=3,
            relief="solid",
            borderwidth=1,
        ).pack()

    def _ocultar_tooltip(self, _event=None) -> None:
        win = self._tip_win
        self._tip_win = None
        if win is None:
            return
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass


class Seccion(ctk.CTkFrame):
    """Marco con título, equivalente a LabelFrame."""

    def __init__(self, master, titulo: str, **kwargs) -> None:
        super().__init__(master, **kwargs)
        ctk.CTkLabel(
            self,
            text=titulo,
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))


class TablaPriorizados(ctk.CTkFrame):
    """Treeview embebido con scroll."""

    COLUMNAS = ("identificacion", "nombre", "motivo", "detalle", "origen")

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.tree = ttk.Treeview(
            self,
            columns=self.COLUMNAS,
            show="headings",
            height=8,
        )
        self.tree.heading("identificacion", text="Identificación")
        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("motivo", text="Motivo")
        self.tree.heading("detalle", text="Detalle")
        self.tree.heading("origen", text="Origen")
        self.tree.column("identificacion", width=110, anchor="w")
        self.tree.column("nombre", width=180, anchor="w")
        self.tree.column("motivo", width=140, anchor="w")
        self.tree.column("detalle", width=160, anchor="w")
        self.tree.column("origen", width=130, anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(self.tree)

    def limpiar(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insertar_fila(self, fila: dict) -> None:
        self.tree.insert(
            "",
            "end",
            values=(
                fila.get("identificacion", ""),
                fila.get("nombre", ""),
                fila.get("motivo", ""),
                fila.get("detalle", ""),
                fila.get("origen", ""),
            ),
        )

    def fila_seleccionada(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        valores = self.tree.item(sel[0], "values")
        if not valores:
            return None
        return {
            "identificacion": valores[0],
            "nombre": valores[1],
            "motivo": valores[2],
            "detalle": valores[3],
            "origen": valores[4],
        }


def texto_estado_archivo(ruta: Path) -> tuple[str, str]:
    if ruta.is_file():
        fecha = datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        return ("cargado", f"Cargado · {fecha}")
    return ("pendiente", "Sin cargar")


def limpiar_marco(marco: ctk.CTkFrame) -> None:
    for w in marco.winfo_children():
        w.destroy()


def fila_archivo(
    marco: ctk.CTkFrame,
    fila: int,
    titulo: str,
    nombre_guardado: str,
    carpeta: Path,
    on_cargar: Callable[[], None],
    on_editar: Callable[[], None] | None = None,
    extra_btn: str | None = None,
    on_vista_previa: Callable[[], None] | None = None,
    opcional: bool = False,
) -> None:
    estado, texto_estado = texto_estado_archivo(carpeta / nombre_guardado)
    color = "#2ecc71" if estado == "cargado" else "#888888"
    titulo_mostrar = f"{titulo} (opcional)" if opcional else titulo

    ctk.CTkLabel(marco, text="●", text_color=color, font=FONT_TEXTO).grid(
        row=fila, column=0, padx=(0, 8), pady=6, sticky="w"
    )
    info = ctk.CTkFrame(marco, fg_color="transparent")
    info.grid(row=fila, column=1, sticky="ew", pady=6)
    ctk.CTkLabel(info, text=titulo_mostrar, font=FONT_TEXTO, anchor="w").pack(anchor="w")
    ctk.CTkLabel(
        info,
        text=texto_estado,
        font=FONT_PEQUENA,
        text_color=("gray50", "gray60"),
        anchor="w",
    ).pack(anchor="w")

    acciones = ctk.CTkFrame(marco, fg_color="transparent")
    acciones.grid(row=fila, column=2, padx=(12, 0), pady=6, sticky="e")
    etiqueta_btn = "Cambiar" if estado == "cargado" else "Cargar"
    ctk.CTkButton(acciones, text=etiqueta_btn, width=90, command=on_cargar).pack(
        side="left", padx=4
    )
    if on_vista_previa:
        ctk.CTkButton(
            acciones,
            text="Vista previa",
            width=100,
            fg_color="transparent",
            border_width=1,
            command=on_vista_previa,
        ).pack(side="left", padx=4)
    if on_editar and extra_btn:
        ctk.CTkButton(
            acciones,
            text=extra_btn,
            width=120,
            fg_color="transparent",
            border_width=1,
            command=on_editar,
        ).pack(side="left", padx=4)

    marco.grid_columnconfigure(1, weight=1)
