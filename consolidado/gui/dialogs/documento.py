"""Diálogo para añadir o editar documentos adicionales."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import consolidado as merge
from consolidado.config.settings import carpeta_excels, guardar_config, guardar_excel_fuente
from consolidado.core.documentos import (
    categorias_documento,
    slug_documento_id,
    sugerir_columna_identificacion,
    sugerir_titulo_documento,
    vista_previa_excel,
)
from consolidado.gui.theme import (
    COLOR_TEXTO,
    COLOR_TEXTO_MUTED,
    FONT_PEQUENA,
    FONT_TEXTO,
    configurar_treeview,
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
        self.filas_map: list[dict] = []
        self._previa: dict | None = None
        self._silenciar_hoja = False

        self.title("Editar documento" if self.modo_edicion else "Añadir documento")
        self.geometry("920x720")
        self.minsize(780, 580)
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self)
        marco.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            marco,
            text=(
                "Abra el Excel: se sugiere un nombre, se muestran unas 20 filas "
                "y elige la clave primaria y las columnas que usará el consolidado."
            ),
            font=FONT_TEXTO,
            text_color=COLOR_TEXTO_MUTED,
            wraplength=860,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(marco, text="Nombre del documento:", anchor="w").grid(
            row=1, column=0, sticky="w"
        )
        self.ent_titulo = ctk.CTkEntry(marco, width=360)
        self.ent_titulo.grid(row=1, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(marco, text="Grupo en el consolidado:", anchor="w").grid(
            row=2, column=0, sticky="w"
        )
        cats = categorias_documento(self.cfg)
        self.combo_categoria = ctk.CTkComboBox(marco, values=cats, width=360)
        self.combo_categoria.grid(row=2, column=1, sticky="ew", pady=4)
        if cats:
            self.combo_categoria.set(cats[0])

        ctk.CTkLabel(
            marco,
            text="O escriba un grupo nuevo:",
            anchor="w",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
        ).grid(row=3, column=0, sticky="w")
        self.ent_categoria_nueva = ctk.CTkEntry(
            marco,
            width=360,
            placeholder_text="Dejar vacío para usar el del desplegable",
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

        self.lbl_archivo = ctk.CTkLabel(
            marco, text="", anchor="w", font=FONT_TEXTO, text_color=COLOR_TEXTO
        )
        self.lbl_archivo.grid(row=5, column=0, columnspan=2, sticky="w")

        ctk.CTkLabel(marco, text="Hoja:", anchor="w").grid(row=6, column=0, sticky="w")
        self.combo_hoja = ctk.CTkComboBox(
            marco, values=[""], width=360, command=lambda _v: self._cambiar_hoja()
        )
        self.combo_hoja.grid(row=6, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(marco, text="Clave primaria:", anchor="w").grid(
            row=7, column=0, sticky="w"
        )
        self.combo_pk = ctk.CTkComboBox(marco, values=[""], width=360)
        self.combo_pk.grid(row=7, column=1, sticky="ew", pady=4)

        ctk.CTkLabel(
            marco,
            text="Previa (hasta 20 filas):",
            anchor="w",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 4))

        marco_prev = ctk.CTkFrame(marco, fg_color="transparent")
        marco_prev.grid(row=9, column=0, columnspan=2, sticky="nsew")
        self.tree_previa = ttk.Treeview(marco_prev, show="headings", height=7)
        sy = ttk.Scrollbar(marco_prev, orient="vertical", command=self.tree_previa.yview)
        sx = ttk.Scrollbar(marco_prev, orient="horizontal", command=self.tree_previa.xview)
        self.tree_previa.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree_previa.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        marco_prev.grid_columnconfigure(0, weight=1)
        marco_prev.grid_rowconfigure(0, weight=1)
        configurar_treeview(self.tree_previa)

        ctk.CTkLabel(
            marco,
            text="Columnas a usar (nombre en consolidado ← columna del Excel):",
            anchor="w",
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 4))

        self.marco_cols = ctk.CTkScrollableFrame(marco, height=180)
        self.marco_cols.grid(row=11, column=0, columnspan=2, sticky="nsew")

        marco_btn = ctk.CTkFrame(marco, fg_color="transparent")
        marco_btn.grid(row=12, column=0, columnspan=2, sticky="e", pady=8)
        ctk.CTkButton(
            marco_btn,
            text="Guardar" if self.modo_edicion else "Guardar documento",
            command=self._guardar,
        ).pack(side="right", padx=4)
        ctk.CTkButton(marco_btn, text="Cancelar", width=90, command=self.destroy).pack(
            side="right"
        )

        marco.grid_columnconfigure(1, weight=1)
        marco.grid_rowconfigure(9, weight=2)
        marco.grid_rowconfigure(11, weight=3)

        if self.modo_edicion and documento:
            self._cargar_documento_existente(documento)
        else:
            self.lbl_archivo.configure(text="Ningún archivo seleccionado · use «Abrir Excel…»")

    def _categoria_elegida(self) -> str:
        nueva = self.ent_categoria_nueva.get().strip()
        if nueva:
            return nueva
        return self.combo_categoria.get().strip() or "Extra"

    def _cargar_documento_existente(self, doc: dict) -> None:
        self.ent_titulo.insert(0, doc.get("titulo", ""))
        grupo = doc.get("grupo_encabezado", "")
        cats = categorias_documento(self.cfg)
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
            self._cargar_previa(guardado, hoja=doc.get("hoja"))
        else:
            self.lbl_archivo.configure(text="Archivo no encontrado en carpeta local")

    def _cargar_previa(self, ruta: Path, hoja: str | None = None) -> None:
        merge.aplicar_config(self.cfg, self.base)
        data = vista_previa_excel(ruta, hoja=hoja, cfg=self.cfg)
        self._silenciar_hoja = True
        try:
            self._previa = data
            self.columnas_origen = list(data.get("columnas") or [])
            hojas = data.get("hojas") or [data.get("hoja") or ""]
            self.combo_hoja.configure(values=hojas or [""])
            if data.get("hoja"):
                self.combo_hoja.set(data["hoja"])
            self.combo_pk.configure(values=self.columnas_origen or [""])
            pk_doc = None
            if self.documento:
                aliases = self.documento.get("columna_identificacion_aliases") or []
                if aliases:
                    pk_doc = aliases[0]
            pk = pk_doc or data.get("pk_sugerida") or sugerir_columna_identificacion(
                self.columnas_origen
            )
            if pk:
                self.combo_pk.set(pk)
            self._pintar_previa(data)
            usados = {}
            if self.documento:
                for col in self.documento.get("columnas") or []:
                    origen = (col.get("aliases") or [""])[0]
                    if origen:
                        usados[origen] = col.get("salida") or origen
            self._rellenar_columnas(usados, pk)
        finally:
            self._silenciar_hoja = False

    def _pintar_previa(self, data: dict) -> None:
        for item in self.tree_previa.get_children():
            self.tree_previa.delete(item)
        cols = list(data.get("columnas") or [])
        self.tree_previa["columns"] = cols
        for col in cols:
            self.tree_previa.heading(col, text=col)
            self.tree_previa.column(col, width=110, stretch=False, anchor="w")
        for fila in data.get("filas") or []:
            self.tree_previa.insert("", "end", values=[fila.get(c, "") for c in cols])

    def _cambiar_hoja(self) -> None:
        if self._silenciar_hoja:
            return
        if not self.ruta_origen or not self.ruta_origen.is_file():
            return
        hoja = self.combo_hoja.get().strip() or None
        try:
            self._cargar_previa(self.ruta_origen, hoja=hoja)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

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
            self._cargar_previa(guardado, hoja=self.documento.get("hoja"))
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
            self.ent_titulo.insert(0, sugerir_titulo_documento(self.ruta_origen.name))
        try:
            self._cargar_previa(self.ruta_origen)
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo leer el Excel:\n{exc}", parent=self)

    def _limpiar_filas(self) -> None:
        for w in self.marco_cols.winfo_children():
            w.destroy()
        self.filas_map.clear()

    def _rellenar_columnas(self, usados: dict[str, str], pk: str | None) -> None:
        self._limpiar_filas()
        hay_usados = bool(usados)
        for col in self.columnas_origen:
            marcada = col in usados if hay_usados else col != pk
            self._anadir_fila_columna(col, usados.get(col, col), marcada)

    def _anadir_fila_columna(self, origen: str, salida: str, marcada: bool) -> None:
        fila = ctk.CTkFrame(self.marco_cols, fg_color="transparent")
        fila.pack(fill="x", pady=3)
        var = ctk.BooleanVar(value=marcada)
        chk = ctk.CTkCheckBox(fila, text="", variable=var, width=28)
        chk.pack(side="left")
        ctk.CTkLabel(fila, text=origen, width=220, anchor="w").pack(side="left", padx=(4, 8))
        ent = ctk.CTkEntry(fila, width=260, placeholder_text="Nombre en consolidado")
        ent.pack(side="left", fill="x", expand=True)
        if salida:
            ent.insert(0, salida)
        self.filas_map.append(
            {"frame": fila, "origen": origen, "entrada": ent, "var": var}
        )

    def _guardar(self) -> None:
        titulo = self.ent_titulo.get().strip()
        grupo = self._categoria_elegida()
        pk = self.combo_pk.get().strip()
        if not titulo or not grupo:
            messagebox.showwarning(
                "Datos incompletos",
                "Indique nombre y grupo del documento.",
                parent=self,
            )
            return
        if not pk:
            messagebox.showwarning(
                "Clave primaria",
                "Elija la columna de identificación (clave primaria).",
                parent=self,
            )
            return

        columnas = []
        for item in self.filas_map:
            if not item["var"].get():
                continue
            salida = item["entrada"].get().strip() or item["origen"]
            origen = item["origen"]
            if salida and origen:
                columnas.append({"salida": salida, "aliases": [origen]})
        if not columnas:
            messagebox.showwarning(
                "Sin columnas",
                "Marque al menos una columna para usar en el consolidado.",
                parent=self,
            )
            return

        hoja = self.combo_hoja.get().strip() or None
        if self.modo_edicion and self.documento:
            doc = self.documento
            doc["titulo"] = titulo
            doc["grupo_encabezado"] = grupo
            doc["categoria"] = grupo
            doc["columnas"] = columnas
            doc["columna_identificacion_aliases"] = [pk]
            doc["hoja"] = hoja
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
            existentes = {d.get("id") for d in self.cfg.get("documentos_adicionales", [])}
            doc_id = slug_documento_id(titulo, existentes)
            nombre_guardado = f"{doc_id}{self.ruta_origen.suffix.lower()}"
            doc = {
                "id": doc_id,
                "titulo": titulo,
                "grupo_encabezado": grupo,
                "categoria": grupo,
                "nombre_guardado": nombre_guardado,
                "hoja": hoja,
                "filtrar_programas": False,
                "columna_identificacion_aliases": [pk],
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
            f"Documento «{titulo}» en «{grupo}» con {len(columnas)} columnas.",
            parent=self.master_app,
        )
