"""Diálogo para consultar la ficha consolidada de un estudiante."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import consolidado as merge
from consolidado.core.ficha_estudiante import obtener_ficha_estudiante
from consolidado.gui.theme import FONT_PEQUENA, FONT_SUBTITULO, FONT_TEXTO, estilo_boton_secundario
from consolidado.gui.widgets import MarcoDesplazable


class DialogoConsultaEstudiante(ctk.CTkToplevel):
    def __init__(self, master, cfg: dict, base: Path) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.base = base
        self.resultados: list[dict] = []

        self.title("Consultar estudiante")
        self.geometry("720x640")
        self.minsize(560, 480)
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self)
        marco.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            marco,
            text="Busque por cédula o nombre para ver todos los datos consolidados del estudiante.",
            font=FONT_TEXTO,
            wraplength=660,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        fila_bus = ctk.CTkFrame(marco, fg_color="transparent")
        fila_bus.pack(fill="x", pady=(0, 8))
        self.var_busqueda = tk.StringVar()
        ctk.CTkEntry(
            fila_bus,
            textvariable=self.var_busqueda,
            placeholder_text="Cédula o nombre",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(fila_bus, text="Buscar", width=90, command=self._buscar).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkButton(
            fila_bus,
            text="Ver ficha",
            width=100,
            command=self._ver_ficha,
        ).pack(side="left")

        self.lista = tk.Listbox(marco, height=5, font=("Segoe UI", 11))
        self.lista.pack(fill="x", pady=(0, 10))
        self.lista.bind("<Double-1>", lambda _e: self._ver_ficha())

        self.lbl_estado = ctk.CTkLabel(
            marco,
            text="Seleccione un estudiante y pulse «Ver ficha».",
            font=FONT_PEQUENA,
            text_color=("gray45", "gray60"),
            anchor="w",
        )
        self.lbl_estado.pack(anchor="w", pady=(0, 6))

        self.scroll_ficha = MarcoDesplazable(marco, altura=420)
        self.scroll_ficha.pack(fill="both", expand=True)
        self.marco_ficha = self.scroll_ficha.inner

        barra = ctk.CTkFrame(marco, fg_color="transparent")
        barra.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(
            barra,
            text="Cerrar",
            width=90,
            command=self.destroy,
            **estilo_boton_secundario(),
        ).pack(side="right")

    def _buscar(self) -> None:
        termino = self.var_busqueda.get().strip()
        if not termino:
            messagebox.showwarning("Buscar", "Escriba una cédula o un nombre.", parent=self)
            return
        merge.aplicar_config(self.cfg, self.base)
        try:
            self.resultados = merge.buscar_estudiantes_en_fuentes(self.cfg, self.base, termino)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.lista.delete(0, tk.END)
        if not self.resultados:
            self.lista.insert(tk.END, "(Sin resultados)")
            self.lbl_estado.configure(text="No se encontraron estudiantes.")
            self._limpiar_ficha()
            return
        for r in self.resultados:
            texto = f"{r['identificacion']} — {r['nombre']}"
            if r.get("programa"):
                texto += f" ({r['programa']})"
            self.lista.insert(tk.END, texto)
        self.lbl_estado.configure(text="Seleccione un estudiante y pulse «Ver ficha».")
        if len(self.resultados) == 1:
            self.lista.selection_set(0)
            self._ver_ficha()

    def _estudiante_seleccionado(self) -> dict | None:
        sel = self.lista.curselection()
        if not sel or not self.resultados:
            return None
        idx = sel[0]
        if idx >= len(self.resultados):
            return None
        return self.resultados[idx]

    def _limpiar_ficha(self) -> None:
        for w in self.marco_ficha.winfo_children():
            w.destroy()

    def _ver_ficha(self) -> None:
        est = self._estudiante_seleccionado()
        if not est:
            messagebox.showwarning(
                "Seleccione",
                "Elija un estudiante de la lista o búsquelo primero.",
                parent=self,
            )
            return

        self.lbl_estado.configure(text="Generando ficha consolidada…")
        self.update_idletasks()
        try:
            ficha = obtener_ficha_estudiante(self.cfg, self.base, est["identificacion"])
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            self.lbl_estado.configure(text="No se pudo generar la ficha.")
            return

        self._limpiar_ficha()
        if not ficha:
            self.lbl_estado.configure(
                text="El estudiante no aparece en el consolidado con los archivos actuales."
            )
            ctk.CTkLabel(
                self.marco_ficha,
                text="No hay datos consolidados para esta identificación.",
                text_color=("gray45", "gray60"),
            ).pack(anchor="w", padx=4, pady=8)
            return

        cab = ctk.CTkFrame(self.marco_ficha, fg_color=("gray92", "gray22"), corner_radius=8)
        cab.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            cab,
            text=ficha.get("nombre") or "(Sin nombre)",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(10, 2))
        meta = f"ID: {ficha['identificacion']}"
        if ficha.get("programa"):
            meta += f"  ·  {ficha['programa']}"
        ctk.CTkLabel(
            cab,
            text=meta,
            font=FONT_PEQUENA,
            text_color=("gray40", "gray60"),
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        for seccion in ficha.get("secciones", []):
            bloque = ctk.CTkFrame(self.marco_ficha, fg_color="transparent")
            bloque.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(
                bloque,
                text=seccion["titulo"],
                font=FONT_SUBTITULO,
                anchor="w",
            ).pack(anchor="w", padx=2, pady=(0, 4))

            grid = ctk.CTkFrame(bloque, fg_color=("gray95", "gray18"), corner_radius=6)
            grid.pack(fill="x")
            grid.grid_columnconfigure(1, weight=1)

            for i, campo in enumerate(seccion.get("campos", [])):
                ctk.CTkLabel(
                    grid,
                    text=campo["etiqueta"],
                    font=FONT_PEQUENA,
                    text_color=("gray35", "gray65"),
                    anchor="w",
                ).grid(row=i, column=0, sticky="nw", padx=(10, 12), pady=4)
                ctk.CTkLabel(
                    grid,
                    text=campo["valor"],
                    font=FONT_TEXTO,
                    anchor="w",
                    justify="left",
                    wraplength=480,
                ).grid(row=i, column=1, sticky="ew", padx=(0, 10), pady=4)

        self.lbl_estado.configure(text="Ficha actualizada con los archivos cargados.")
        self.scroll_ficha.enlazar_rueda_recursivo()
