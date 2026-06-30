"""Diálogo para editar aliases, programas y documentos extra."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

import consolidado as merge
from consolidado.config.settings import etiqueta_alias, guardar_config
from consolidado.gui.dialogs.documento import DialogoDocumento
from consolidado.gui.theme import FONT_SUBTITULO, FONT_TEXTO, configurar_treeview


class DialogoCambiarDatos(ctk.CTkToplevel):
    """Editor visual de aliases, programas y documentos extra."""

    def __init__(self, master, cfg: dict, base: Path, callback) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.base = base
        self.callback = callback

        self.title("Cambiar datos de columnas")
        self.geometry("820x560")
        self.minsize(700, 480)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Indique cómo se llaman las columnas en los Excel de origen. "
            "Separe varios sinónimos con comas.",
            font=FONT_TEXTO,
            wraplength=780,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 0))

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

        self._pestana_aliases()
        self._pestana_programas()
        self.lista_excluidos, _ = self._pestana_lista_editable(
            "Programas excluidos",
            "programas_excluidos",
            "Nunca se incluyen (p. ej. sedes o variantes). Aplica a becas y BD 2/3.",
        )
        self._pestana_priorizados()
        self._pestana_documentos()

        marco_btn = ctk.CTkFrame(self, fg_color="transparent")
        marco_btn.pack(fill="x", padx=8, pady=(0, 12))
        ctk.CTkButton(marco_btn, text="Guardar cambios", command=self._guardar).pack(
            side="right", padx=4
        )
        ctk.CTkButton(marco_btn, text="Cancelar", width=90, command=self.destroy).pack(
            side="right"
        )

    def _pestana_aliases(self) -> None:
        marco = self.tabview.add("Columnas de origen")
        contenedor = ctk.CTkFrame(marco, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=4, pady=4)

        cols = ("campo", "sinonimos")
        tree = ttk.Treeview(contenedor, columns=cols, show="headings", height=14)
        tree.heading("campo", text="Campo en el consolidado")
        tree.heading("sinonimos", text="Nombres posibles en el Excel (separados por coma)")
        tree.column("campo", width=220, anchor="w")
        tree.column("sinonimos", width=520, anchor="w")
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(tree)

        self.tree_aliases = tree
        self._filas_alias: dict[str, str] = {}

        for canon in sorted(self.cfg.get("aliases", {}).keys(), key=etiqueta_alias):
            vals = self.cfg["aliases"].get(canon, [])
            texto = ", ".join(vals)
            self._filas_alias[canon] = tree.insert(
                "", tk.END, iid=canon, values=(etiqueta_alias(canon), texto)
            )

        ctk.CTkButton(
            marco,
            text="Editar fila seleccionada",
            command=self._editar_alias_seleccionado,
        ).pack(anchor="w", padx=8, pady=(8, 4))

        tree.bind("<Double-1>", lambda _e: self._editar_alias_seleccionado())

    def _editar_alias_seleccionado(self) -> None:
        sel = self.tree_aliases.selection()
        if not sel:
            messagebox.showinfo("Seleccione", "Elija un campo de la lista.", parent=self)
            return
        canon = sel[0]
        actual = self.tree_aliases.item(canon, "values")[1]

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Editar — {etiqueta_alias(canon)}")
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg,
            text=etiqueta_alias(canon),
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            dlg,
            text="Nombres de columna en el Excel (sinónimos, separados por coma):",
            anchor="w",
        ).pack(anchor="w", padx=12)
        ent = ctk.CTkEntry(dlg, width=500)
        ent.pack(fill="x", padx=12, pady=8)
        ent.insert(0, actual)
        ent.focus_set()

        def ok() -> None:
            texto = ent.get().strip()
            sinonimos = [p.strip() for p in texto.split(",") if p.strip()]
            self.cfg.setdefault("aliases", {})[canon] = sinonimos
            self.tree_aliases.item(
                canon, values=(etiqueta_alias(canon), ", ".join(sinonimos))
            )
            dlg.destroy()

        marco = ctk.CTkFrame(dlg, fg_color="transparent")
        marco.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(marco, text="Aceptar", command=ok).pack(side="right", padx=4)
        ctk.CTkButton(marco, text="Cancelar", width=90, command=dlg.destroy).pack(
            side="right"
        )

    def _pestana_lista_editable(
        self,
        titulo: str,
        clave_cfg: str,
        ayuda: str,
    ) -> tuple[tk.Listbox, tk.StringVar]:
        marco = self.tabview.add(titulo)
        ctk.CTkLabel(marco, text=ayuda, font=FONT_TEXTO, wraplength=740, justify="left").pack(
            anchor="w", padx=8, pady=(8, 8)
        )

        lista = tk.Listbox(marco, height=12, font=("Segoe UI", 10))
        lista.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        for item in self.cfg.get(clave_cfg, []):
            lista.insert(tk.END, item)

        var = tk.StringVar()
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkEntry(fila, textvariable=var, width=360).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )

        def anadir() -> None:
            val = var.get().strip()
            if val and val not in lista.get(0, tk.END):
                lista.insert(tk.END, val)
                var.set("")

        def quitar() -> None:
            sel = lista.curselection()
            if sel:
                lista.delete(sel[0])

        ctk.CTkButton(fila, text="Añadir", width=90, command=anadir).pack(side="left", padx=2)
        ctk.CTkButton(fila, text="Quitar seleccionado", width=140, command=quitar).pack(
            side="left", padx=2
        )
        return lista, var

    def _pestana_programas(self) -> None:
        self.lista_programas, _ = self._pestana_lista_editable(
            "Programas (BD 2 y 3)",
            "programas_permitidos",
            "Solo se incluyen filas de estos programas en Grupos priorizados y Becados.",
        )

    def _pestana_priorizados(self) -> None:
        self.lista_motivos, _ = self._pestana_lista_editable(
            "Motivos priorizado",
            "columnas_motivo_priorizado",
            "Columnas booleanas en BD 2 que indican el motivo de priorización.",
        )

    def _pestana_documentos(self) -> None:
        marco = self.tabview.add("Documentos extra")
        docs = self.cfg.get("documentos_adicionales", [])
        if not docs:
            ctk.CTkLabel(
                marco,
                text="No hay documentos adicionales.\nUse «+ Añadir documento» en la ventana principal.",
                text_color=("gray50", "gray60"),
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)
            return

        ctk.CTkLabel(
            marco,
            text="Seleccione un documento para ver o editar su mapeo:",
            anchor="w",
        ).pack(anchor="w", padx=8, pady=(8, 8))

        titulos = [d.get("titulo", d.get("id", "")) for d in docs]
        self.combo_docs = ctk.CTkComboBox(
            marco,
            values=titulos,
            width=480,
            state="readonly",
            command=lambda _v: self._mostrar_mapa_documento(),
        )
        self.combo_docs.pack(anchor="w", padx=8, pady=(0, 8))
        if titulos:
            self.combo_docs.set(titulos[0])

        self.marco_map_doc = ctk.CTkScrollableFrame(marco, fg_color="transparent")
        self.marco_map_doc.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        ctk.CTkButton(
            marco,
            text="Editar documento completo…",
            command=self._editar_doc_desde_pestana,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        self._mostrar_mapa_documento()

    def _doc_por_titulo(self) -> dict | None:
        titulo = self.combo_docs.get()
        for d in self.cfg.get("documentos_adicionales", []):
            if d.get("titulo", d.get("id", "")) == titulo:
                return d
        return None

    def _mostrar_mapa_documento(self) -> None:
        for w in self.marco_map_doc.winfo_children():
            w.destroy()
        doc = self._doc_por_titulo()
        if not doc:
            return

        ctk.CTkLabel(
            self.marco_map_doc,
            text=f"Grupo en Excel: {doc.get('grupo_encabezado', '')}",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        for col in doc.get("columnas", []):
            salida = col.get("salida", "")
            origen = ", ".join(col.get("aliases", []))
            fila = ctk.CTkFrame(self.marco_map_doc, fg_color="transparent")
            fila.pack(fill="x", pady=2)
            ctk.CTkLabel(fila, text=salida, width=200, anchor="w").pack(side="left")
            ctk.CTkLabel(fila, text="←", text_color=("gray50", "gray60")).pack(
                side="left", padx=4
            )
            ctk.CTkLabel(fila, text=origen, anchor="w").pack(side="left", fill="x", expand=True)

    def _editar_doc_desde_pestana(self) -> None:
        doc = self._doc_por_titulo()
        if doc:
            DialogoDocumento(self.master, self.cfg, self.base, self._refrescar_docs, documento=doc)

    def _refrescar_docs(self) -> None:
        titulos = [d.get("titulo", d.get("id", "")) for d in self.cfg.get("documentos_adicionales", [])]
        self.combo_docs.configure(values=titulos)
        if titulos:
            self.combo_docs.set(titulos[0])
        self._mostrar_mapa_documento()

    def _guardar(self) -> None:
        self.cfg["programas_permitidos"] = list(self.lista_programas.get(0, tk.END))
        self.cfg["programas_excluidos"] = list(self.lista_excluidos.get(0, tk.END))
        self.cfg["columnas_motivo_priorizado"] = list(self.lista_motivos.get(0, tk.END))
        guardar_config(self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self.callback()
        self.destroy()
        messagebox.showinfo("Guardado", "Configuración actualizada.", parent=self.master)
