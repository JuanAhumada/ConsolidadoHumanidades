"""Ventana principal de la interfaz gráfica (CustomTkinter)."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import consolidado as merge
from consolidado.config.settings import (
    CATEGORIAS_FUENTE_DEFAULT,
    ORDEN_CATEGORIAS_FUENTE,
    cargar_config,
    carpeta_excels,
    guardar_config,
    guardar_excel_fuente,
    slot_es_requerido,
)
from consolidado.core.excel_io import elegir_guardar_consolidado
from consolidado.gui.dialogs import (
    DialogoCambiarDatos,
    DialogoDocumento,
    DialogoInfoPrioridad,
    DialogoPriorizadoPropio,
    DialogoVistaPrevia,
)
from consolidado.gui.icons import icono
from consolidado.gui.theme import (
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    FONT_TITULO,
    alternar_modo_apariencia,
    configurar_apariencia,
    configurar_treeview,
    modo_apariencia_actual,
)
from consolidado.gui.widgets import (
    IconButton,
    Seccion,
    TablaPriorizados,
    fila_archivo,
    limpiar_marco,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.priorizados import quitar_priorizado_propio


class AppConsolidado(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.base = PROJECT_ROOT
        self.cfg = cargar_config(self.base)
        modo = self.cfg.get("interfaz", {}).get("modo_apariencia", "system")
        configurar_apariencia(modo)
        merge.aplicar_config(self.cfg, self.base)
        self._icon_refs: list[ctk.CTkImage] = []

        self.title("Gestion de Humanidades")
        self.geometry("900x720")
        self.minsize(720, 600)

        self._construir_ui()
        self._actualizar_lista_archivos()
        self._actualizar_tabla_priorizados()
        self._actualizar_ruta_salida()

    def _ico(self, nombre: str, size: int = 22) -> ctk.CTkImage:
        img = icono(nombre, size=size)
        self._icon_refs.append(img)
        return img

    def _construir_ui(self) -> None:
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=16, pady=16)

        encabezado = ctk.CTkFrame(contenedor, fg_color="transparent")
        encabezado.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            encabezado,
            text="Consolidado de Humanidades",
            font=FONT_TITULO,
        ).pack(side="left")

        acciones = ctk.CTkFrame(encabezado, fg_color="transparent")
        acciones.pack(side="right")

        IconButton(
            acciones,
            icon=self._ico("save"),
            tooltip="Elegir ruta del archivo final",
            command=self._elegir_ruta_salida,
        ).pack(side="left", padx=(0, 6))

        self.btn_tema = IconButton(
            acciones,
            icon=self._ico_tema(),
            tooltip="Alternar modo claro / oscuro",
            command=self._toggle_tema,
        )
        self.btn_tema.pack(side="left", padx=(0, 6))

        IconButton(
            acciones,
            icon=self._ico("generate", size=24),
            tooltip="Generar consolidado",
            width=40,
            command=self.generar,
        ).pack(side="left")

        ctk.CTkLabel(
            contenedor,
            text="Cada archivo se guarda por separado. Use «Cargar» o «Cambiar» solo en el que necesite actualizar.",
            font=FONT_TEXTO,
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self.lbl_ruta_salida = ctk.CTkLabel(
            contenedor,
            text="",
            font=FONT_PEQUENA,
            text_color=("gray45", "gray55"),
            anchor="w",
            wraplength=860,
            justify="left",
        )
        self.lbl_ruta_salida.pack(anchor="w", pady=(0, 10))

        barra_fuentes = ctk.CTkFrame(contenedor, fg_color="transparent")
        barra_fuentes.pack(fill="x", pady=(0, 4))

        self.btn_toggle_fuentes = IconButton(
            barra_fuentes,
            icon=self._ico("folder"),
            tooltip="Mostrar archivos fuente",
            fg_color="transparent",
            border_width=1,
            command=self._toggle_fuentes,
        )
        self.btn_toggle_fuentes.pack(side="left")
        ctk.CTkLabel(
            barra_fuentes,
            text="Archivos fuente y documentos adicionales",
            font=FONT_PEQUENA,
            text_color=("gray50", "gray60"),
        ).pack(side="left", padx=(8, 0))

        self.area_scroll = ctk.CTkScrollableFrame(contenedor, fg_color="transparent")
        self.area_scroll.pack(fill="both", expand=True, pady=(0, 8))

        self.marco_fuentes = Seccion(self.area_scroll, titulo="Archivos fuente")
        self.marco_filas_fuentes = ctk.CTkFrame(self.marco_fuentes.body, fg_color="transparent")
        self.marco_filas_fuentes.pack(fill="x")
        self.marco_filas_fuentes.grid_columnconfigure(1, weight=1)

        self.marco_docs = Seccion(self.marco_fuentes.body, titulo="Documentos adicionales")
        self.marco_docs.pack(fill="x", pady=(12, 0))
        self.marco_filas_docs = ctk.CTkFrame(self.marco_docs.body, fg_color="transparent")
        self.marco_filas_docs.pack(fill="x")

        barra_docs = ctk.CTkFrame(self.marco_docs.body, fg_color="transparent")
        barra_docs.pack(fill="x", pady=(8, 0))
        IconButton(
            barra_docs,
            icon=self._ico("add"),
            tooltip="Añadir documento",
            command=self.anadir_documento,
        ).pack(side="left")

        self.marco_prio = Seccion(self.area_scroll, titulo="Priorizados")
        self.marco_prio.pack(fill="x", pady=(0, 8))

        barra_prio = ctk.CTkFrame(self.marco_prio.body, fg_color="transparent")
        barra_prio.pack(fill="x", pady=(0, 6))
        IconButton(
            barra_prio,
            icon=self._ico("refresh"),
            tooltip="Actualizar lista",
            command=self._actualizar_tabla_priorizados,
        ).pack(side="left", padx=(0, 6))
        IconButton(
            barra_prio,
            icon=self._ico("add_user"),
            tooltip="Priorizado propio",
            command=self._abrir_priorizado_propio,
        ).pack(side="left", padx=(0, 6))
        IconButton(
            barra_prio,
            icon=self._ico("remove"),
            tooltip="Quitar priorizado propio",
            command=self._quitar_priorizado_propio_seleccionado,
        ).pack(side="left")

        IconButton(
            barra_prio,
            icon=self._ico("info"),
            tooltip="Información: cálculo de prioridad y colores",
            command=self._abrir_info_prioridad,
        ).pack(side="right")

        self.tabla_priorizados = TablaPriorizados(self.marco_prio.body)
        self.tabla_priorizados.pack(fill="x", expand=False)

        pie = ctk.CTkFrame(contenedor, fg_color="transparent")
        pie.pack(fill="x")
        IconButton(
            pie,
            icon=self._ico("settings"),
            tooltip="Cambiar datos de columnas",
            command=self.cambiar_datos,
        ).pack(side="left")
        self.lbl_resumen = ctk.CTkLabel(
            pie,
            text="",
            font=FONT_TEXTO,
            text_color=("gray50", "gray60"),
        )
        self.lbl_resumen.pack(side="right")

    def _ruta_salida_actual(self) -> Path:
        rel = self.cfg.get("salida", {}).get("ruta", "salida/estudiantes_consolidado.xlsx")
        return (self.base / rel).resolve()

    def _actualizar_ruta_salida(self) -> None:
        ruta = self._ruta_salida_actual()
        self.lbl_ruta_salida.configure(text=f"Archivo final: {ruta}")

    def _elegir_ruta_salida(self) -> None:
        elegida = elegir_guardar_consolidado(self._ruta_salida_actual())
        if elegida is None:
            return
        try:
            rel = elegida.resolve().relative_to(self.base.resolve())
            self.cfg.setdefault("salida", {})["ruta"] = rel.as_posix()
        except ValueError:
            self.cfg.setdefault("salida", {})["ruta"] = str(elegida.resolve())
        guardar_config(self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self._actualizar_ruta_salida()
        messagebox.showinfo("Ruta guardada", f"El consolidado se guardará en:\n{elegida}")

    def _toggle_fuentes(self) -> None:
        if self.marco_fuentes.winfo_ismapped():
            self.marco_fuentes.pack_forget()
            self.btn_toggle_fuentes.configure(image=self._ico("folder"))
            self.btn_toggle_fuentes.set_tooltip("Mostrar archivos fuente")
        else:
            self.marco_fuentes.pack(fill="x", pady=(0, 8), before=self.marco_prio)
            self.btn_toggle_fuentes.configure(image=self._ico("folder_open"))
            self.btn_toggle_fuentes.set_tooltip("Ocultar archivos fuente")

    def _ruta_guardada(self, nombre: str) -> Path:
        return carpeta_excels(self.cfg, self.base) / nombre

    def _carpeta_excels(self) -> Path:
        return carpeta_excels(self.cfg, self.base)

    def _ico_tema(self) -> ctk.CTkImage:
        return self._ico("sun" if modo_apariencia_actual() == "dark" else "moon")

    def _toggle_tema(self) -> None:
        nuevo = alternar_modo_apariencia()
        self.cfg.setdefault("interfaz", {})["modo_apariencia"] = nuevo
        guardar_config(self.cfg, self.base)
        self.btn_tema.configure(image=self._ico_tema())
        configurar_treeview(self.tabla_priorizados.tree)

    def _actualizar_lista_archivos(self) -> None:
        carpeta = self._carpeta_excels()
        limpiar_marco(self.marco_filas_fuentes)

        categorias = self.cfg.get("categorias_fuente", CATEGORIAS_FUENTE_DEFAULT)
        slots_por_cat: dict[str, list[dict]] = {c: [] for c in ORDEN_CATEGORIAS_FUENTE}
        for slot in self.cfg.get("archivos_fuente", []):
            cat = slot.get("categoria", "base")
            slots_por_cat.setdefault(cat, []).append(slot)

        fila = 0
        for cat_key in ORDEN_CATEGORIAS_FUENTE:
            slots = slots_por_cat.get(cat_key, [])
            if not slots:
                continue
            titulo_cat = categorias.get(cat_key, cat_key.title())
            ctk.CTkLabel(
                self.marco_filas_fuentes,
                text=titulo_cat,
                font=FONT_SUBTITULO,
                anchor="w",
            ).grid(row=fila, column=0, columnspan=3, sticky="w", pady=(10, 4))
            fila += 1
            for slot in slots:
                nombre = slot.get("nombre_guardado", "")
                fila_archivo(
                    self.marco_filas_fuentes,
                    fila,
                    slot.get("titulo", slot.get("id", "Archivo")),
                    nombre,
                    carpeta,
                    on_cargar=lambda s=slot: self._cargar_slot(s),
                    on_vista_previa=lambda s=slot: self._vista_previa_slot(s),
                    opcional=not slot_es_requerido(slot),
                )
                fila += 1

        limpiar_marco(self.marco_filas_docs)
        docs = self.cfg.get("documentos_adicionales", [])
        if not docs:
            ctk.CTkLabel(
                self.marco_filas_docs,
                text="No hay documentos adicionales. Use el botón + para añadir uno.",
                text_color=("gray50", "gray60"),
            ).pack(anchor="w")
        else:
            for i, doc in enumerate(docs):
                nombre = doc.get("nombre_guardado", "")
                fila_archivo(
                    self.marco_filas_docs,
                    i,
                    doc.get("titulo", doc.get("grupo_encabezado", "Documento")),
                    nombre,
                    carpeta,
                    on_cargar=lambda d=doc: self._cargar_documento(d),
                    on_editar=lambda d=doc: self._editar_documento(d),
                    extra_btn="Editar columnas",
                )

        cargados = sum(
            1
            for s in self.cfg.get("archivos_fuente", [])
            if self._ruta_guardada(s.get("nombre_guardado", "")).is_file()
        )
        total = len(self.cfg.get("archivos_fuente", []))
        self.lbl_resumen.configure(text=f"{cargados}/{total} archivos fuente listos")

    def _abrir_info_prioridad(self) -> None:
        DialogoInfoPrioridad(self, self.cfg, self.base, self._on_config_guardada)

    def _vista_previa_slot(self, slot: dict) -> None:
        DialogoVistaPrevia(self, slot, self.cfg, self.base)

    def _elegir_excel(self, titulo: str, nombre_actual: str) -> Path | None:
        carpeta = self._carpeta_excels()
        actual = self._ruta_guardada(nombre_actual)
        ruta = filedialog.askopenfilename(
            title=titulo,
            filetypes=[
                ("Libro Excel", "*.xlsx *.xlsm *.xls"),
                ("Todos", "*.*"),
            ],
            initialdir=str(actual.parent if actual.parent.exists() else carpeta),
        )
        return Path(ruta) if ruta else None

    def _cargar_slot(self, slot: dict) -> None:
        accion = (
            "Cambiar"
            if self._ruta_guardada(slot.get("nombre_guardado", "")).is_file()
            else "Cargar"
        )
        ruta = self._elegir_excel(
            f"{accion} — {slot.get('titulo', '')}", slot.get("nombre_guardado", "")
        )
        if not ruta:
            return
        guardar_excel_fuente(ruta, slot, self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self._actualizar_lista_archivos()
        messagebox.showinfo("Listo", f"«{slot.get('titulo', '')}» actualizado.")

    def _cargar_documento(self, doc: dict) -> None:
        nombre = doc.get("nombre_guardado", "")
        accion = "Cambiar" if self._ruta_guardada(nombre).is_file() else "Cargar"
        ruta = self._elegir_excel(f"{accion} — {doc.get('titulo', '')}", nombre)
        if not ruta:
            return
        guardar_excel_fuente(ruta, {"nombre_guardado": nombre}, self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self._actualizar_lista_archivos()
        messagebox.showinfo("Listo", f"«{doc.get('titulo', '')}» actualizado.")

    def _editar_documento(self, doc: dict) -> None:
        DialogoDocumento(self, self.cfg, self.base, self._actualizar_lista_archivos, documento=doc)

    def _on_documento_guardado(self) -> None:
        self._actualizar_lista_archivos()

    def _actualizar_tabla_priorizados(self) -> None:
        merge.aplicar_config(self.cfg, self.base)
        self.tabla_priorizados.limpiar()
        try:
            filas = merge.obtener_lista_priorizados_vista(self.cfg, self.base)
        except Exception as exc:
            messagebox.showerror("Priorizados", f"No se pudo cargar la lista:\n{exc}")
            return
        for f in filas:
            self.tabla_priorizados.insertar_fila(f)

    def _abrir_priorizado_propio(self) -> None:
        DialogoPriorizadoPropio(self, self.cfg, self.base, self._actualizar_tabla_priorizados)

    def _quitar_priorizado_propio_seleccionado(self) -> None:
        fila = self.tabla_priorizados.fila_seleccionada()
        if not fila:
            messagebox.showwarning(
                "Quitar priorizado",
                "Seleccione un estudiante en la tabla de priorizados.",
            )
            return
        origen = fila.get("origen", "")
        if "Priorizado propio" not in origen:
            messagebox.showwarning(
                "Quitar priorizado",
                "Solo puede quitar entradas marcadas como «Priorizado propio».\n"
                "Los de Grupos priorizados provienen del Excel y no se eliminan aquí.",
            )
            return
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Quitar el priorizado propio de {fila.get('nombre') or fila['identificacion']}?",
        ):
            return
        quitar_priorizado_propio(fila["identificacion"], self.base)
        self._actualizar_tabla_priorizados()
        messagebox.showinfo("Listo", "Priorizado propio eliminado.")

    def generar(self) -> None:
        faltantes = [
            s.get("titulo", s.get("id", ""))
            for s in self.cfg.get("archivos_fuente", [])
            if slot_es_requerido(s)
            and not self._ruta_guardada(s.get("nombre_guardado", "")).is_file()
        ]
        if faltantes:
            messagebox.showwarning(
                "Faltan archivos",
                "Aún no están cargados:\n• " + "\n• ".join(faltantes),
            )
            return
        try:
            _, destino = merge.ejecutar_consolidado(
                self.cfg,
                base=self.base,
                abrir=True,
                preguntar_sobrescribir=True,
                parent=self,
            )
        except SystemExit:
            return
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._actualizar_ruta_salida()
        messagebox.showinfo("Listo", f"Consolidado generado:\n{destino}")

    def cambiar_datos(self) -> None:
        DialogoCambiarDatos(self, self.cfg, self.base, self._on_config_guardada)

    def _on_config_guardada(self) -> None:
        merge.aplicar_config(self.cfg, self.base)
        self._actualizar_lista_archivos()
        self._actualizar_ruta_salida()

    def anadir_documento(self) -> None:
        DialogoDocumento(self, self.cfg, self.base, self._on_documento_guardado)


def main() -> None:
    from consolidado.config.settings import cargar_config
    from consolidado.paths import PROJECT_ROOT

    cfg = cargar_config(PROJECT_ROOT)
    modo = cfg.get("interfaz", {}).get("modo_apariencia", "system")
    configurar_apariencia(modo)
    app = AppConsolidado()
    app.mainloop()
