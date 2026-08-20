"""Diálogo para consultar versiones históricas del consolidado en SQL."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from consolidado.config.settings import cargar_config
from consolidado.core.constants import max_materias_en_dataframe
from consolidado.core.excel_io import abrir_archivo_en_sistema
from consolidado.core.export import guardar_excel_consolidado
from consolidado.core.repetidas import _cargar_materias_repetidas_cfg
from consolidado.gui.theme import (
    COLOR_ACENTO,
    COLOR_TEXTO,
    COLOR_TEXTO_MUTED,
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    configurar_treeview,
    estilo_boton_primario,
    estilo_boton_secundario,
    estilo_seccion,
)
from consolidado.storage.db import (
    cargar_dataframe_version,
    listar_versiones,
    obtener_version,
    periodo_desde_fecha,
)


class DialogoVersiones(ctk.CTkToplevel):
    def __init__(self, master, cfg: dict, base: Path) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.base = base
        self.versiones: list[dict] = []

        self.title("Versiones del consolidado")
        self.geometry("860x560")
        self.minsize(700, 460)
        self.transient(master)
        self.grab_set()

        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            marco,
            text="Historial de consolidados",
            font=FONT_SUBTITULO,
            text_color=COLOR_TEXTO,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            marco,
            text=(
                "Cada generación queda en SQLite con campos consultables "
                "(programa, prioridad, beca…). El periodo sigue la fecha de versión "
                "(ene–jun → YYYY-1, jul–dic → YYYY-2)."
            ),
            font=FONT_TEXTO,
            text_color=COLOR_TEXTO_MUTED,
            wraplength=780,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        filtros = ctk.CTkFrame(marco, fg_color="transparent")
        filtros.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(filtros, text="Periodo", font=FONT_TEXTO, text_color=COLOR_TEXTO).pack(
            side="left", padx=(0, 8)
        )
        self.var_periodo = tk.StringVar(value="Todos")
        self.combo_periodo = ctk.CTkComboBox(
            filtros,
            variable=self.var_periodo,
            values=["Todos"],
            width=130,
            corner_radius=10,
            command=lambda _v: self._cargar_lista(),
        )
        self.combo_periodo.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            filtros,
            text="Actualizar",
            width=110,
            height=34,
            command=self._cargar_lista,
            **estilo_boton_secundario(),
        ).pack(side="left")

        self.lbl_estado = ctk.CTkLabel(
            marco,
            text="",
            font=FONT_PEQUENA,
            text_color=COLOR_ACENTO,
            anchor="w",
        )
        self.lbl_estado.pack(anchor="w", pady=(0, 8))

        tarjeta = ctk.CTkFrame(marco, **estilo_seccion())
        tarjeta.pack(fill="both", expand=True)
        marco_tabla = ctk.CTkFrame(tarjeta, fg_color="transparent")
        marco_tabla.pack(fill="both", expand=True, padx=10, pady=10)

        columnas = ("id", "periodo", "fecha", "estudiantes", "creado", "excel")
        self.tree = ttk.Treeview(
            marco_tabla,
            columns=columnas,
            show="headings",
            selectmode="browse",
            height=14,
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("periodo", text="Periodo")
        self.tree.heading("fecha", text="Fecha versión")
        self.tree.heading("estudiantes", text="Estudiantes")
        self.tree.heading("creado", text="Guardado")
        self.tree.heading("excel", text="Excel")
        self.tree.column("id", width=50, anchor="center")
        self.tree.column("periodo", width=80, anchor="center")
        self.tree.column("fecha", width=110, anchor="center")
        self.tree.column("estudiantes", width=90, anchor="center")
        self.tree.column("creado", width=150, anchor="center")
        self.tree.column("excel", width=280, anchor="w")
        scroll = ttk.Scrollbar(marco_tabla, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(self.tree)

        barra = ctk.CTkFrame(marco, fg_color="transparent")
        barra.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            barra,
            text="Abrir Excel",
            width=120,
            height=36,
            command=self._abrir_excel,
            **estilo_boton_primario(),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            barra,
            text="Exportar de nuevo",
            width=150,
            height=36,
            command=self._exportar,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            barra,
            text="Cerrar",
            width=100,
            height=36,
            command=self.destroy,
            **estilo_boton_secundario(),
        ).pack(side="right")

        self._cargar_lista()

    def _version_seleccionada(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        valores = self.tree.item(sel[0], "values")
        if not valores:
            return None
        version_id = int(valores[0])
        return next((v for v in self.versiones if v["id"] == version_id), None)

    def _cargar_lista(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        todas = listar_versiones(self.base)
        periodos = sorted({v["periodo"] for v in todas}, reverse=True)
        valores_combo = ["Todos"] + periodos
        self.combo_periodo.configure(values=valores_combo)
        filtro = self.var_periodo.get()
        if filtro not in valores_combo:
            self.var_periodo.set("Todos")
            filtro = "Todos"

        self.versiones = todas if filtro == "Todos" else [v for v in todas if v["periodo"] == filtro]
        for v in self.versiones:
            excel = Path(v["ruta_excel"]).name if v.get("ruta_excel") else "—"
            self.tree.insert(
                "",
                "end",
                values=(
                    v["id"],
                    v["periodo"],
                    v["fecha_version"],
                    v["num_estudiantes"],
                    v["creado_en"],
                    excel,
                ),
            )
        hoy = periodo_desde_fecha()
        self.lbl_estado.configure(
            text=f"{len(self.versiones)} versión(es) · periodo actual: {hoy}"
        )

    def _abrir_excel(self) -> None:
        v = self._version_seleccionada()
        if not v:
            messagebox.showwarning("Versiones", "Seleccione una versión de la lista.", parent=self)
            return
        ruta_rel = v.get("ruta_excel")
        if not ruta_rel:
            messagebox.showinfo(
                "Sin Excel",
                "Esta versión no tiene archivo Excel asociado.\nUse «Exportar de nuevo».",
                parent=self,
            )
            return
        ruta = Path(ruta_rel)
        if not ruta.is_absolute():
            ruta = self.base / ruta
        if not ruta.is_file():
            messagebox.showwarning(
                "Archivo no encontrado",
                f"No se encontró el Excel:\n{ruta}\n\nPuede regenerarlo con «Exportar de nuevo».",
                parent=self,
            )
            return
        abrir_archivo_en_sistema(ruta, parent=self)

    def _exportar(self) -> None:
        v = self._version_seleccionada()
        if not v:
            messagebox.showwarning("Versiones", "Seleccione una versión de la lista.", parent=self)
            return
        try:
            meta = obtener_version(v["id"], self.base)
            if meta is None:
                raise ValueError("Versión no encontrada en la base de datos.")
            df = cargar_dataframe_version(v["id"], self.base)
            cfg = self.cfg or cargar_config(self.base)
            num_materias = meta.get("num_materias") or max_materias_en_dataframe(df)
            materias_repetidas = _cargar_materias_repetidas_cfg(cfg, self.base)

            carpeta = self.base / "salida"
            carpeta.mkdir(parents=True, exist_ok=True)
            from consolidado.storage.db import nombre_excel_version
            from datetime import date

            fecha = date.fromisoformat(meta["fecha_version"])
            destino = carpeta / nombre_excel_version(meta["periodo"], fecha, sufijo_hora="export")
            destino = guardar_excel_consolidado(
                df,
                destino,
                cfg=cfg,
                num_materias=num_materias,
                materias_repetidas=materias_repetidas,
            )
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Exportado",
            f"Excel regenerado desde la base SQL:\n{destino}",
            parent=self,
        )
        abrir_archivo_en_sistema(destino, parent=self)
