"""Diálogo para añadir o editar documentos adicionales."""

from __future__ import annotations

import re
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import consolidado as merge
from consolidado.config.settings import carpeta_excels, guardar_config, guardar_excel_fuente
from consolidado.gui.theme import FONT_TEXTO


class DialogoDocumento(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        cfg: dict,
        base: Path,
        callback,
        *,
        documento: dict | None = None,
    ) -> None:
        super().__init__(master)
        self.master_app = master
        self.cfg = cfg
        self.base = base
        self.callback = callback
        self.documento = documento
        self.modo_edicion = documento is not None
        self.ruta_origen: Path | None = None
        self.columnas_origen: list[str] = []
        self.filas_map: list[tuple[ctk.CTkEntry, ctk.CTkComboBox]] = []

        self.title("Editar documento" if self.modo_edicion else "Añadir documento")
        self.geometry("680x560")
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self)
        marco.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(marco, text="Título del documento:", anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.ent_titulo = ctk.CTkEntry(marco, width=320)
        self.ent_titulo.grid(row=0, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(marco, text="Encabezado principal (grupo):", anchor="w").grid(
            row=1, column=0, sticky="w"
        )
        self.ent_grupo = ctk.CTkEntry(marco, width=320)
        self.ent_grupo.grid(row=1, column=1, sticky="ew", pady=4)

        fila_arch = ctk.CTkFrame(marco, fg_color="transparent")
        fila_arch.grid(row=2, column=0, columnspan=2, sticky="w", pady=8)
        ctk.CTkButton(fila_arch, text="Seleccionar Excel…", command=self._elegir_excel).pack(
            side="left"
        )
        if self.modo_edicion:
            ctk.CTkButton(
                fila_arch,
                text="Recargar archivo guardado",
                command=self._recargar_desde_guardado,
            ).pack(side="left", padx=8)

        self.lbl_archivo = ctk.CTkLabel(marco, text="", anchor="w", font=FONT_TEXTO)
        self.lbl_archivo.grid(row=3, column=0, columnspan=2, sticky="w")

        ctk.CTkLabel(
            marco,
            text="Columna en consolidado → columna en el Excel:",
            anchor="w",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 4))

        self.marco_cols = ctk.CTkScrollableFrame(marco, height=220)
        self.marco_cols.grid(row=5, column=0, columnspan=2, sticky="nsew")

        ctk.CTkButton(marco, text="+ Añadir columna", command=self._anadir_fila_columna).grid(
            row=6, column=0, sticky="w", pady=8
        )

        marco_btn = ctk.CTkFrame(marco, fg_color="transparent")
        marco_btn.grid(row=7, column=0, columnspan=2, sticky="e", pady=8)
        ctk.CTkButton(
            marco_btn,
            text="Guardar" if self.modo_edicion else "Guardar documento",
            command=self._guardar,
        ).pack(side="right", padx=4)
        ctk.CTkButton(marco_btn, text="Cancelar", width=90, command=self.destroy).pack(
            side="right"
        )

        marco.grid_columnconfigure(1, weight=1)
        marco.grid_rowconfigure(5, weight=1)

        if self.modo_edicion and documento:
            self._cargar_documento_existente(documento)
        else:
            self.lbl_archivo.configure(text="Ningún archivo seleccionado")
            self._anadir_fila_columna()

    def _cargar_documento_existente(self, doc: dict) -> None:
        self.ent_titulo.insert(0, doc.get("titulo", ""))
        self.ent_grupo.insert(0, doc.get("grupo_encabezado", ""))
        nombre = doc.get("nombre_guardado", "")
        guardado = carpeta_excels(self.cfg, self.base) / nombre
        if guardado.is_file():
            self.ruta_origen = guardado
            self.lbl_archivo.configure(text=f"Archivo guardado: {guardado.name}")
            self._leer_columnas_desde(guardado)
        else:
            self.lbl_archivo.configure(text="Archivo no encontrado en carpeta local")
        for col in doc.get("columnas", []):
            self._anadir_fila_columna(col.get("salida", ""), (col.get("aliases") or [""])[0])

    def _leer_columnas_desde(self, ruta: Path) -> None:
        merge.aplicar_config(self.cfg, self.base)
        hoja = self.documento.get("hoja") if self.documento else None
        if hoja:
            df = merge._leer_hoja_excel(ruta, hoja)
        else:
            df = merge._leer_hoja_datos(ruta)
        self.columnas_origen = list(df.columns)
        for _, combo in self.filas_map:
            combo.configure(values=self.columnas_origen or [""])

    def _recargar_desde_guardado(self) -> None:
        if not self.documento:
            return
        nombre = self.documento.get("nombre_guardado", "")
        guardado = carpeta_excels(self.cfg, self.base) / nombre
        if not guardado.is_file():
            messagebox.showwarning(
                "Sin archivo",
                "Primero cargue el Excel desde la ventana principal.",
                parent=self,
            )
            return
        self.ruta_origen = guardado
        self.lbl_archivo.configure(text=f"Archivo guardado: {guardado.name}")
        try:
            self._leer_columnas_desde(guardado)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _elegir_excel(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Excel del documento",
            filetypes=[("Libro Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")],
        )
        if not ruta:
            return
        self.ruta_origen = Path(ruta)
        self.lbl_archivo.configure(text=str(self.ruta_origen))
        try:
            self._leer_columnas_desde(self.ruta_origen)
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo leer el Excel:\n{exc}", parent=self)

    def _anadir_fila_columna(self, salida: str = "", origen: str = "") -> None:
        fila = len(self.filas_map)
        ctk.CTkLabel(self.marco_cols, text="Consolidado:").grid(
            row=fila, column=0, sticky="w", pady=2
        )
        ent = ctk.CTkEntry(self.marco_cols, width=200)
        ent.grid(row=fila, column=1, sticky="ew", padx=4, pady=2)
        if salida:
            ent.insert(0, salida)
        ctk.CTkLabel(self.marco_cols, text="Excel:").grid(
            row=fila, column=2, sticky="w", padx=(8, 0)
        )
        combo = ctk.CTkComboBox(
            self.marco_cols,
            values=self.columnas_origen or [""],
            width=200,
        )
        combo.grid(row=fila, column=3, sticky="ew", padx=4, pady=2)
        if origen:
            combo.set(origen)
        self.filas_map.append((ent, combo))

    def _slug_id(self, texto: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")
        return s or "doc"

    def _guardar(self) -> None:
        titulo = self.ent_titulo.get().strip()
        grupo = self.ent_grupo.get().strip()
        if not titulo or not grupo:
            messagebox.showwarning(
                "Datos incompletos",
                "Indique título y encabezado del grupo.",
                parent=self,
            )
            return

        columnas = []
        for ent, combo in self.filas_map:
            salida = ent.get().strip()
            origen = combo.get().strip()
            if salida and origen:
                columnas.append({"salida": salida, "aliases": [origen]})
        if not columnas:
            messagebox.showwarning(
                "Sin columnas",
                "Defina al menos una columna mapeada.",
                parent=self,
            )
            return

        if self.modo_edicion and self.documento:
            doc = self.documento
            doc["titulo"] = titulo
            doc["grupo_encabezado"] = grupo
            doc["columnas"] = columnas
            if self.ruta_origen and self.ruta_origen.is_file():
                origen_guardado = carpeta_excels(self.cfg, self.base) / doc.get(
                    "nombre_guardado", ""
                )
                if self.ruta_origen.resolve() != origen_guardado.resolve():
                    guardar_excel_fuente(
                        self.ruta_origen,
                        {"nombre_guardado": doc["nombre_guardado"]},
                        self.cfg,
                        self.base,
                    )
        else:
            if not self.ruta_origen or not self.ruta_origen.is_file():
                messagebox.showwarning("Falta archivo", "Seleccione un Excel.", parent=self)
                return
            doc_id = self._slug_id(titulo)
            existentes = {d.get("id") for d in self.cfg.get("documentos_adicionales", [])}
            n = 1
            while doc_id in existentes:
                doc_id = f"{self._slug_id(titulo)}_{n}"
                n += 1
            nombre_guardado = f"{doc_id}{self.ruta_origen.suffix.lower()}"
            doc = {
                "id": doc_id,
                "titulo": titulo,
                "grupo_encabezado": grupo,
                "nombre_guardado": nombre_guardado,
                "hoja": None,
                "filtrar_programas": False,
                "columnas": columnas,
            }
            guardar_excel_fuente(
                self.ruta_origen, {"nombre_guardado": nombre_guardado}, self.cfg, self.base
            )
            self.cfg.setdefault("documentos_adicionales", []).append(doc)

        guardar_config(self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self.callback()
        self.destroy()
        messagebox.showinfo(
            "Guardado",
            f"Documento «{titulo}» guardado con {len(columnas)} columnas.",
            parent=self.master_app,
        )
