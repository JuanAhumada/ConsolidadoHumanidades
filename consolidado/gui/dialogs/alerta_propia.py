"""Diálogo para buscar y gestionar alertas propias."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import consolidado as merge
from consolidado.gui.theme import FONT_TEXTO
from consolidado.storage.alertas_propias import agregar_alerta_propia, quitar_alerta_propia


class DialogoAlertaPropia(ctk.CTkToplevel):
    def __init__(self, master, cfg: dict, base: Path, callback) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.base = base
        self.callback = callback
        self.resultados: list[dict] = []

        self.title("Alerta propia")
        self.geometry("640x480")
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self)
        marco.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            marco,
            text="Busque por cédula o nombre. La alerta quedará guardada y se marcará "
            "en el consolidado al generar.",
            font=FONT_TEXTO,
            wraplength=580,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        fila_bus = ctk.CTkFrame(marco, fg_color="transparent")
        fila_bus.pack(fill="x", pady=(0, 8))
        self.var_busqueda = tk.StringVar()
        ctk.CTkEntry(fila_bus, textvariable=self.var_busqueda, placeholder_text="Cédula o nombre").pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(fila_bus, text="Buscar", width=90, command=self._buscar).pack(side="left")

        self.lista = tk.Listbox(marco, height=10, font=("Segoe UI", 11))
        self.lista.pack(fill="both", expand=True, pady=(0, 10))

        ctk.CTkLabel(marco, text="Detalle de la alerta:", anchor="w").pack(anchor="w")
        self.ent_detalle = ctk.CTkEntry(marco)
        self.ent_detalle.pack(fill="x", pady=(2, 8))

        barra = ctk.CTkFrame(marco, fg_color="transparent")
        barra.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(barra, text="Cerrar", width=90, command=self.destroy).pack(side="right", padx=4)
        ctk.CTkButton(barra, text="Quitar alerta", width=110, command=self._quitar).pack(side="right", padx=4)
        ctk.CTkButton(barra, text="Añadir seleccionado", width=140, command=self._anadir).pack(
            side="right", padx=4
        )

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
            return
        for r in self.resultados:
            texto = f"{r['identificacion']} — {r['nombre']}"
            if r.get("programa"):
                texto += f" ({r['programa']})"
            self.lista.insert(tk.END, texto)

    def _estudiante_seleccionado(self) -> dict | None:
        sel = self.lista.curselection()
        if not sel or not self.resultados:
            return None
        idx = sel[0]
        if idx >= len(self.resultados):
            return None
        return self.resultados[idx]

    def _anadir(self) -> None:
        est = self._estudiante_seleccionado()
        if not est:
            messagebox.showwarning("Seleccione", "Elija un estudiante de la lista.", parent=self)
            return
        detalle = self.ent_detalle.get().strip()
        if not detalle:
            messagebox.showwarning("Detalle", "Escriba una descripción para la alerta.", parent=self)
            return
        agregar_alerta_propia(
            {
                "identificacion": est["identificacion"],
                "nombre": est.get("nombre", ""),
                "detalle": detalle,
            },
            self.base,
        )
        self.callback()
        messagebox.showinfo(
            "Guardado",
            f"Alerta propia guardada para «{est.get('nombre', est['identificacion'])}».",
            parent=self,
        )

    def _quitar(self) -> None:
        est = self._estudiante_seleccionado()
        if not est:
            messagebox.showwarning("Seleccione", "Elija un estudiante de la lista.", parent=self)
            return
        quitar_alerta_propia(est["identificacion"], self.base)
        self.callback()
        messagebox.showinfo("Quitado", "Alerta propia eliminada.", parent=self)
