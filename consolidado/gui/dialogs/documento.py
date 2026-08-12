"""Diálogo para añadir o editar documentos adicionales."""

from __future__ import annotations

import re
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import consolidado as merge
from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    carpeta_excels,
    guardar_config,
    guardar_excel_fuente,
)
from consolidado.core.archivos import _leer_hoja_datos
from consolidado.core.excel_io import _leer_hoja_excel
from consolidado.gui.theme import (
    COLOR_TEXTO,
    COLOR_TEXTO_MUTED,
    FONT_PEQUENA,
    FONT_TEXTO,
    estilo_boton_secundario,
)


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
        self.geometry("760x640")
        self.minsize(680, 520)
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self)
        marco.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            marco,
            text=(
                "Abra el Excel, elija la categoría del consolidado y asigne "
                "a mano el nombre de cada columna nueva."
            ),
            font=FONT_TEXTO,
            text_color=COLOR_TEXTO_MUTED,
            wraplength=700,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(marco, text="Título del documento:", anchor="w").grid(
            row=1, column=0, sticky="w"
        )
        self.ent_titulo = ctk.CTkEntry(marco, width=340)
        self.ent_titulo.grid(row=1, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(marco, text="Categoría en el consolidado:", anchor="w").grid(
            row=2, column=0, sticky="w"
        )
        cats = self._categorias_disponibles()
        self.combo_categoria = ctk.CTkComboBox(
            marco,
            values=cats,
            width=340,
        )
        self.combo_categoria.grid(row=2, column=1, sticky="ew", pady=4)
        if cats:
            self.combo_categoria.set(cats[0])

        ctk.CTkLabel(
            marco,
            text="O escriba una categoría nueva:",
            anchor="w",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
        ).grid(row=3, column=0, sticky="w")
        self.ent_categoria_nueva = ctk.CTkEntry(
            marco,
            width=340,
            placeholder_text="Dejar vacío para usar la del desplegable",
        )
        self.ent_categoria_nueva.grid(row=3, column=1, sticky="ew", pady=4)

        fila_arch = ctk.CTkFrame(marco, fg_color="transparent")
        fila_arch.grid(row=4, column=0, columnspan=2, sticky="ew", pady=8)
        ctk.CTkButton(
            fila_arch,
            text="Abrir Excel…",
            command=self._elegir_excel,
            **estilo_boton_secundario(),
        ).pack(side="left")
        if self.modo_edicion:
            ctk.CTkButton(
                fila_arch,
                text="Recargar archivo guardado",
                command=self._recargar_desde_guardado,
                **estilo_boton_secundario(),
            ).pack(side="left", padx=8)
        ctk.CTkButton(
            fila_arch,
            text="Usar columnas del Excel",
            command=self._rellenar_desde_excel,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=8)

        self.lbl_archivo = ctk.CTkLabel(
            marco, text="", anchor="w", font=FONT_TEXTO, text_color=COLOR_TEXTO
        )
        self.lbl_archivo.grid(row=5, column=0, columnspan=2, sticky="w")

        ctk.CTkLabel(
            marco,
            text="Nombre en consolidado (editable)  →  columna del Excel:",
            anchor="w",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 4))

        self.marco_cols = ctk.CTkScrollableFrame(marco, height=260)
        self.marco_cols.grid(row=7, column=0, columnspan=2, sticky="nsew")

        ctk.CTkButton(marco, text="+ Añadir columna", command=self._anadir_fila_columna).grid(
            row=8, column=0, sticky="w", pady=8
        )

        marco_btn = ctk.CTkFrame(marco, fg_color="transparent")
        marco_btn.grid(row=9, column=0, columnspan=2, sticky="e", pady=8)
        ctk.CTkButton(
            marco_btn,
            text="Guardar" if self.modo_edicion else "Guardar documento",
            command=self._guardar,
        ).pack(side="right", padx=4)
        ctk.CTkButton(marco_btn, text="Cancelar", width=90, command=self.destroy).pack(
            side="right"
        )

        marco.grid_columnconfigure(1, weight=1)
        marco.grid_rowconfigure(7, weight=1)

        if self.modo_edicion and documento:
            self._cargar_documento_existente(documento)
        else:
            self.lbl_archivo.configure(text="Ningún archivo seleccionado · use «Abrir Excel…»")
            self._anadir_fila_columna()

    def _categorias_disponibles(self) -> list[str]:
        cats: list[str] = []
        for g in self.cfg.get("grupos_salida", []):
            nombre = g.get("nombre", "").strip()
            if nombre and nombre not in cats:
                cats.append(nombre)
        etiquetas = self.cfg.get("categorias_fuente", CATEGORIAS_FUENTE_DEFAULT)
        for key in ORDEN_CATEGORIAS_FUENTE:
            etiqueta = etiquetas.get(key, key.title())
            if etiqueta not in cats:
                cats.append(etiqueta)
        for doc in self.cfg.get("documentos_adicionales", []):
            g = (doc.get("grupo_encabezado") or doc.get("titulo") or "").strip()
            if g and g not in cats:
                cats.append(g)
        return cats or ["Extra"]

    def _categoria_elegida(self) -> str:
        nueva = self.ent_categoria_nueva.get().strip()
        if nueva:
            return nueva
        return self.combo_categoria.get().strip() or "Extra"

    def _cargar_documento_existente(self, doc: dict) -> None:
        self.ent_titulo.insert(0, doc.get("titulo", ""))
        grupo = doc.get("grupo_encabezado", "")
        cats = self._categorias_disponibles()
        if grupo and grupo not in cats:
            cats = [grupo] + cats
            self.combo_categoria.configure(values=cats)
        if grupo:
            self.combo_categoria.set(grupo)
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
            df = _leer_hoja_excel(ruta, hoja)
        else:
            df = _leer_hoja_datos(ruta)
        self.columnas_origen = list(df.columns)
        for _, combo in self.filas_map:
            actual = combo.get()
            combo.configure(values=self.columnas_origen or [""])
            if actual in self.columnas_origen:
                combo.set(actual)

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
        if not self.ent_titulo.get().strip():
            self.ent_titulo.insert(0, self.ruta_origen.stem.replace("_", " ").title())
        try:
            self._leer_columnas_desde(self.ruta_origen)
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo leer el Excel:\n{exc}", parent=self)
            return
        if not self.modo_edicion and len(self.filas_map) <= 1:
            # Si solo hay una fila vacía, ofrecer rellenar desde el Excel
            unica = self.filas_map[0] if self.filas_map else None
            if unica and not unica[0].get().strip():
                if messagebox.askyesno(
                    "Columnas del Excel",
                    "¿Cargar las columnas del archivo para que pueda "
                    "renombrarlas a mano en el consolidado?",
                    parent=self,
                ):
                    self._rellenar_desde_excel()

    def _limpiar_filas(self) -> None:
        for w in self.marco_cols.winfo_children():
            w.destroy()
        self.filas_map.clear()

    def _rellenar_desde_excel(self) -> None:
        if not self.columnas_origen:
            messagebox.showwarning(
                "Sin columnas",
                "Abra primero un Excel para ver sus columnas.",
                parent=self,
            )
            return
        self._limpiar_filas()
        for col in self.columnas_origen:
            # Saltar posibles columnas de identificación: el usuario puede quitarlas
            self._anadir_fila_columna(salida=col, origen=col)

    def _anadir_fila_columna(self, salida: str = "", origen: str = "") -> None:
        fila = len(self.filas_map)
        ctk.CTkLabel(self.marco_cols, text="Nombre columna:").grid(
            row=fila, column=0, sticky="w", pady=2
        )
        ent = ctk.CTkEntry(self.marco_cols, width=220, placeholder_text="Nombre en consolidado")
        ent.grid(row=fila, column=1, sticky="ew", padx=4, pady=2)
        if salida:
            ent.insert(0, salida)
        ctk.CTkLabel(self.marco_cols, text="Del Excel:").grid(
            row=fila, column=2, sticky="w", padx=(8, 0)
        )
        combo = ctk.CTkComboBox(
            self.marco_cols,
            values=self.columnas_origen or [""],
            width=220,
            command=lambda val, e=ent: self._sugerir_nombre(e, val),
        )
        combo.grid(row=fila, column=3, sticky="ew", padx=4, pady=2)
        if origen:
            combo.set(origen)
        elif self.columnas_origen:
            combo.set(self.columnas_origen[0])
        self.filas_map.append((ent, combo))
        self.marco_cols.grid_columnconfigure(1, weight=1)
        self.marco_cols.grid_columnconfigure(3, weight=1)

    def _sugerir_nombre(self, entry: ctk.CTkEntry, valor: str) -> None:
        if entry.get().strip():
            return
        if valor:
            entry.insert(0, valor)

    def _slug_id(self, texto: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")
        return s or "doc"

    def _guardar(self) -> None:
        titulo = self.ent_titulo.get().strip()
        grupo = self._categoria_elegida()
        if not titulo or not grupo:
            messagebox.showwarning(
                "Datos incompletos",
                "Indique título y categoría del documento.",
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
                "Defina al menos una columna con nombre y origen del Excel.",
                parent=self,
            )
            return

        if self.modo_edicion and self.documento:
            doc = self.documento
            doc["titulo"] = titulo
            doc["grupo_encabezado"] = grupo
            doc["categoria"] = grupo
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
                "categoria": grupo,
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
            f"Documento «{titulo}» en categoría «{grupo}» "
            f"con {len(columnas)} columnas.",
            parent=self.master_app,
        )
