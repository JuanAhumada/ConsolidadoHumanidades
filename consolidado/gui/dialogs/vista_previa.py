"""Diálogo de vista previa: columnas del Excel guardado → consolidado."""

from __future__ import annotations

from pathlib import Path
from tkinter import ttk

import customtkinter as ctk

from consolidado.config.settings import slot_es_requerido
from consolidado.core.vista_previa import obtener_vista_previa_slot
from consolidado.gui.theme import FONT_PEQUENA, FONT_TEXTO, configurar_treeview


class DialogoVistaPrevia(ctk.CTkToplevel):
    def __init__(self, master, slot: dict, cfg: dict, base: Path) -> None:
        super().__init__(master)
        self.title(f"Vista previa — {slot.get('titulo', '')}")
        self.geometry("720x480")
        self.minsize(560, 360)
        self.transient(master)
        self.grab_set()

        requerido = slot_es_requerido(slot)
        opcional = " · opcional" if not requerido else ""
        ctk.CTkLabel(
            self,
            text=(
                f"Archivo guardado: {slot.get('nombre_guardado', '')}{opcional}\n"
                "Columnas del Excel de origen que alimentan el consolidado "
                "(nombres finales de salida)."
            ),
            font=FONT_TEXTO,
            wraplength=680,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        cols = ("columna_salida", "origen", "ejemplo")
        tree = ttk.Treeview(marco, columns=cols, show="headings", height=14)
        tree.heading("columna_salida", text="Columna en consolidado")
        tree.heading("origen", text="Columna en archivo guardado")
        tree.heading("ejemplo", text="Ejemplo")
        tree.column("columna_salida", width=200, anchor="w")
        tree.column("origen", width=260, anchor="w")
        tree.column("ejemplo", width=200, anchor="w")
        scroll = ttk.Scrollbar(marco, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(tree)

        filas, error = obtener_vista_previa_slot(slot, cfg, base)
        if error:
            ctk.CTkLabel(
                self,
                text=error,
                text_color=("#c0392b", "#e74c3c"),
                font=FONT_PEQUENA,
                wraplength=680,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 8))
        else:
            for f in filas:
                tree.insert(
                    "",
                    "end",
                    values=(f.get("columna_salida", ""), f.get("origen", ""), f.get("ejemplo", "")),
                )

        ctk.CTkButton(self, text="Cerrar", width=90, command=self.destroy).pack(pady=(0, 12))
