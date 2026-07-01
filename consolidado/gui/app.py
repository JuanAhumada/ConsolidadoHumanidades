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
    DialogoAlertaPropia,
    DialogoCambiarDatos,
    DialogoConsultaEstudiante,
    DialogoDocumento,
    DialogoInfoPrioridad,
    DialogoPriorizadoPropio,
    DialogoVistaPrevia,
)
from consolidado.gui.icons import icono
from consolidado.gui.theme import (
    COLOR_ACENTO,
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    FONT_TITULO,
    alternar_modo_apariencia,
    configurar_apariencia,
    configurar_treeview,
    estilo_boton_secundario,
    estilo_seccion,
    estilo_tarjeta_paso,
    modo_apariencia_actual,
)
from consolidado.gui.widgets import (
    BarraEstado,
    BotonIconoTexto,
    ContenidoRetractil,
    IconButton,
    MarcoDesplazable,
    PanelPasos,
    Seccion,
    TablaAlertasPropias,
    TablaPriorizados,
    fila_archivo,
    limpiar_marco,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.alertas_propias import quitar_alerta_propia
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

        self.title("Consolidado de Humanidades")
        self.geometry("980x800")
        self.minsize(760, 640)

        self._construir_ui()
        self._actualizar_lista_archivos()
        self._actualizar_tabla_priorizados()
        self._actualizar_tabla_alertas()
        self._actualizar_ruta_salida()

    def _ico(self, nombre: str, size: int = 20) -> ctk.CTkImage:
        img = icono(nombre, size=size)
        self._icon_refs.append(img)
        return img

    def _construir_ui(self) -> None:
        contenedor = ctk.CTkFrame(self, fg_color="transparent")
        contenedor.pack(fill="both", expand=True, padx=16, pady=16)

        encabezado = ctk.CTkFrame(contenedor, fg_color="transparent")
        encabezado.pack(fill="x", pady=(0, 8))

        titulos = ctk.CTkFrame(encabezado, fg_color="transparent")
        titulos.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            titulos,
            text="Consolidado de Humanidades",
            font=FONT_TITULO,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            titulos,
            text="Una sola herramienta para unir matrículas, priorizados, becas y alertas en un Excel final.",
            font=FONT_TEXTO,
            text_color=("gray45", "gray60"),
            anchor="w",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        acciones = ctk.CTkFrame(encabezado, fg_color="transparent")
        acciones.pack(side="right")

        BotonIconoTexto(
            acciones,
            icon=self._ico("save"),
            texto="Ruta de salida",
            fg_color="transparent",
            border_width=1,
            command=self._elegir_ruta_salida,
        ).pack(side="left", padx=(0, 6))

        self.btn_tema = IconButton(
            acciones,
            icon=self._ico_tema(),
            tooltip="Modo claro / oscuro",
            command=self._toggle_tema,
        )
        self.btn_tema.pack(side="left", padx=(0, 8))

        self.btn_generar = BotonIconoTexto(
            acciones,
            icon=self._ico("generate", size=22),
            texto="Generar consolidado",
            height=40,
            width=200,
            font=("Segoe UI", 14, "bold"),
            fg_color=COLOR_ACENTO,
            hover_color="#36719f",
            command=self.generar,
        )
        self.btn_generar.pack(side="left")

        self.panel_pasos = PanelPasos(contenedor)
        self.panel_pasos.pack(fill="x", pady=(0, 10))

        self.barra_estado = BarraEstado(contenedor)
        self.barra_estado.pack(fill="x", pady=(0, 10))

        self.marco_principal = ctk.CTkFrame(contenedor, fg_color="transparent")
        self.marco_principal.pack(fill="both", expand=True, pady=(0, 8))

        self.marco_fuentes = Seccion(
            self.marco_principal,
            titulo="Paso 1 · Archivos fuente",
            ayuda=(
                "Cada Excel se guarda por separado en datos/entrada. "
                "Use «Cargar» la primera vez y «Cambiar» cuando reciba una versión nueva. "
                "Los marcados como obligatorio deben estar listos antes de generar."
            ),
        )
        self.marco_fuentes.pack(fill="x", pady=(0, 8))

        self.retractil_fuentes = ContenidoRetractil(
            self.marco_fuentes.body,
            texto_abierto="Ocultar lista de archivos",
            texto_cerrado="Mostrar lista de archivos",
            icono_abierto=self._ico("folder_open"),
            icono_cerrado=self._ico("folder"),
        )
        self.retractil_fuentes.pack(fill="x")

        self.scroll_fuentes = MarcoDesplazable(self.retractil_fuentes.contenido, altura=340)
        self.scroll_fuentes.pack(fill="x", pady=(0, 4))

        self.marco_filas_fuentes = ctk.CTkFrame(self.scroll_fuentes.inner, fg_color="transparent")
        self.marco_filas_fuentes.pack(fill="x")
        self.marco_filas_fuentes.grid_columnconfigure(1, weight=1)

        self.marco_docs = Seccion(
            self.retractil_fuentes.contenido,
            titulo="Documentos adicionales",
            ayuda="Opcional: otras hojas Excel que se añaden como columnas extra al consolidado.",
        )
        self.marco_docs.pack(fill="x", pady=(8, 0))
        self.marco_filas_docs = ctk.CTkFrame(self.marco_docs.body, fg_color="transparent")
        self.marco_filas_docs.pack(fill="x")

        barra_docs = ctk.CTkFrame(self.marco_docs.body, fg_color="transparent")
        barra_docs.pack(fill="x", pady=(8, 0))
        BotonIconoTexto(
            barra_docs,
            icon=self._ico("add"),
            texto="Añadir documento",
            command=self.anadir_documento,
        ).pack(side="left")

        self.marco_prio = Seccion(
            self.marco_principal,
            titulo="Paso 2 · Priorizados",
            ayuda=(
                "Vista de todos los estudiantes marcados como priorizados. "
                "Algunos vienen de los Excels (grupos, Psicología internos); "
                "otros los puede añadir usted con «Añadir priorizado propio»."
            ),
        )
        self.marco_prio.pack(fill="x", pady=(0, 8))

        self.retractil_prio = ContenidoRetractil(
            self.marco_prio.body,
            texto_abierto="Ocultar priorizados",
            texto_cerrado="Mostrar priorizados",
            icono_abierto=self._ico("folder_open"),
            icono_cerrado=self._ico("folder"),
            expandido=False,
        )
        self.retractil_prio.pack(fill="x")

        barra_prio = ctk.CTkFrame(self.retractil_prio.contenido, fg_color="transparent")
        barra_prio.pack(fill="x", pady=(0, 6))
        BotonIconoTexto(
            barra_prio,
            icon=self._ico("refresh"),
            texto="Actualizar",
            fg_color="transparent",
            border_width=1,
            command=self._actualizar_tabla_priorizados,
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            barra_prio,
            icon=self._ico("add_user"),
            texto="Añadir priorizado propio",
            command=self._abrir_priorizado_propio,
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            barra_prio,
            icon=self._ico("remove"),
            texto="Quitar propio",
            fg_color="transparent",
            border_width=1,
            command=self._quitar_priorizado_propio_seleccionado,
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            barra_prio,
            icon=self._ico("info"),
            texto="Cómo se calcula la prioridad",
            fg_color="transparent",
            border_width=1,
            command=self._abrir_info_prioridad,
        ).pack(side="right")

        self.tabla_priorizados = TablaPriorizados(self.retractil_prio.contenido)
        self.tabla_priorizados.pack(fill="x", expand=False)

        self.marco_alertas = Seccion(
            self.marco_principal,
            titulo="Alertas propias",
            ayuda=(
                "Marcaciones manuales que se suman al consolidado "
                "(columnas Alerta Propia y Detalle Propio). "
                "No sustituyen las alertas que vienen de los Excels de alertas."
            ),
        )
        self.marco_alertas.pack(fill="x", pady=(0, 8))

        self.retractil_alertas = ContenidoRetractil(
            self.marco_alertas.body,
            texto_abierto="Ocultar alertas propias",
            texto_cerrado="Mostrar alertas propias",
            icono_abierto=self._ico("folder_open"),
            icono_cerrado=self._ico("folder"),
            expandido=False,
        )
        self.retractil_alertas.pack(fill="x")

        barra_alertas = ctk.CTkFrame(self.retractil_alertas.contenido, fg_color="transparent")
        barra_alertas.pack(fill="x", pady=(0, 6))
        BotonIconoTexto(
            barra_alertas,
            icon=self._ico("refresh"),
            texto="Actualizar",
            fg_color="transparent",
            border_width=1,
            command=self._actualizar_tabla_alertas,
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            barra_alertas,
            icon=self._ico("add"),
            texto="Añadir alerta",
            command=self._abrir_alerta_propia,
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            barra_alertas,
            icon=self._ico("remove"),
            texto="Quitar alerta",
            fg_color="transparent",
            border_width=1,
            command=self._quitar_alerta_propia_seleccionada,
        ).pack(side="left")

        self.tabla_alertas = TablaAlertasPropias(self.retractil_alertas.contenido)
        self.tabla_alertas.pack(fill="x", expand=False)

        pie = ctk.CTkFrame(contenedor, fg_color="transparent")
        pie.pack(fill="x")
        BotonIconoTexto(
            pie,
            icon=self._ico("add_user"),
            texto="Consultar estudiante",
            command=self._abrir_consulta_estudiante,
        ).pack(side="left", padx=(0, 8))
        BotonIconoTexto(
            pie,
            icon=self._ico("settings"),
            texto="Configurar columnas y aliases",
            command=self.cambiar_datos,
            **estilo_boton_secundario(),
        ).pack(side="left")
        self.lbl_resumen = ctk.CTkLabel(
            pie,
            text="",
            font=FONT_PEQUENA,
            text_color=("gray50", "gray60"),
        )
        self.lbl_resumen.pack(side="right")

    def _ruta_salida_actual(self) -> Path:
        rel = self.cfg.get("salida", {}).get("ruta", "salida/estudiantes_consolidado.xlsx")
        return (self.base / rel).resolve()

    def _conteo_archivos(self) -> tuple[int, int, int, int, list[str]]:
        slots = self.cfg.get("archivos_fuente", [])
        obligatorios = [s for s in slots if slot_es_requerido(s)]
        cargados_oblig = sum(
            1
            for s in obligatorios
            if self._ruta_guardada(s.get("nombre_guardado", "")).is_file()
        )
        cargados_total = sum(
            1
            for s in slots
            if self._ruta_guardada(s.get("nombre_guardado", "")).is_file()
        )
        faltantes = [
            s.get("titulo", s.get("id", ""))
            for s in obligatorios
            if not self._ruta_guardada(s.get("nombre_guardado", "")).is_file()
        ]
        return cargados_oblig, len(obligatorios), cargados_total, len(slots), faltantes

    def _actualizar_estado_general(self) -> None:
        cargados_oblig, total_oblig, cargados_all, total_all, faltantes = self._conteo_archivos()
        listo = cargados_oblig == total_oblig and total_oblig > 0
        ruta = self._ruta_salida_actual()
        ruta_corta = ruta.name if len(str(ruta)) > 48 else str(ruta)

        texto_oblig = f"{cargados_oblig}/{total_oblig} obligatorios listos"
        if faltantes:
            texto_oblig += f" · faltan {len(faltantes)}"

        self.barra_estado.actualizar(
            archivos=texto_oblig,
            ruta=ruta_corta,
            listo=listo,
        )
        self.panel_pasos.actualizar(
            archivos_obligatorios=texto_oblig,
            listo_generar=listo,
            ruta_salida=ruta.name,
            paso1_listo=cargados_oblig == total_oblig and total_oblig > 0,
        )
        self.lbl_resumen.configure(
            text=f"{cargados_all}/{total_all} archivos fuente cargados (incluye opcionales)"
        )

    def _actualizar_ruta_salida(self) -> None:
        self._actualizar_estado_general()

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

    def _toggle_tema(self) -> None:
        nuevo = alternar_modo_apariencia()
        self.cfg.setdefault("interfaz", {})["modo_apariencia"] = nuevo
        guardar_config(self.cfg, self.base)
        self.btn_tema.configure(image=self._ico_tema())
        configurar_treeview(self.tabla_priorizados.tree)
        configurar_treeview(self.tabla_alertas.tree)
        self.scroll_fuentes.actualizar_fondo()
        estilo = estilo_seccion()
        for marco in (
            self.marco_fuentes,
            self.marco_prio,
            self.marco_alertas,
            self.marco_docs,
        ):
            marco.configure(**estilo)
        for tarjeta in self.panel_pasos._tarjetas:
            tarjeta.configure(**estilo_tarjeta_paso())

    def _ruta_guardada(self, nombre: str) -> Path:
        return carpeta_excels(self.cfg, self.base) / nombre

    def _carpeta_excels(self) -> Path:
        return carpeta_excels(self.cfg, self.base)

    def _ico_tema(self) -> ctk.CTkImage:
        return self._ico("sun" if modo_apariencia_actual() == "dark" else "moon")

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
                text="No hay documentos adicionales. Use «Añadir documento» para agregar uno.",
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

        self._actualizar_estado_general()
        self.scroll_fuentes.enlazar_rueda_recursivo()

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

    def _actualizar_tabla_alertas(self) -> None:
        merge.aplicar_config(self.cfg, self.base)
        self.tabla_alertas.limpiar()
        try:
            filas = merge.obtener_lista_alertas_propias_vista(self.cfg, self.base)
        except Exception as exc:
            messagebox.showerror("Alertas propias", f"No se pudo cargar la lista:\n{exc}")
            return
        for f in filas:
            self.tabla_alertas.insertar_fila(f)

    def _abrir_alerta_propia(self) -> None:
        DialogoAlertaPropia(self, self.cfg, self.base, self._actualizar_tabla_alertas)

    def _quitar_alerta_propia_seleccionada(self) -> None:
        fila = self.tabla_alertas.fila_seleccionada()
        if not fila:
            messagebox.showwarning(
                "Quitar alerta",
                "Seleccione un estudiante en la tabla de alertas propias.",
            )
            return
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Quitar la alerta propia de {fila.get('nombre') or fila['identificacion']}?",
        ):
            return
        quitar_alerta_propia(fila["identificacion"], self.base)
        self._actualizar_tabla_alertas()
        messagebox.showinfo("Listo", "Alerta propia eliminada.")

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
                "Solo puede quitar entradas marcadas como «Priorizado propio».\n\n"
                "Los que vienen de Excels (grupos priorizados, Psicología internos, etc.) "
                "no se eliminan desde aquí; actualice el archivo fuente correspondiente.",
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
        _, _, _, _, faltantes = self._conteo_archivos()
        if faltantes:
            messagebox.showwarning(
                "Faltan archivos obligatorios",
                "Antes de generar, cargue estos archivos en el Paso 1:\n\n• "
                + "\n• ".join(faltantes),
            )
            return
        try:
            _, destino = merge.ejecutar_consolidado(
                self.cfg,
                base=self.base,
                abrir=False,
                preguntar_sobrescribir=True,
                parent=self,
            )
        except SystemExit:
            return
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._actualizar_ruta_salida()
        messagebox.showinfo(
            "Consolidado generado",
            f"El archivo se guardó correctamente:\n{destino}\n\nSe abrirá en Excel.",
        )
        merge.abrir_archivo_en_sistema(destino, parent=self)

    def _abrir_consulta_estudiante(self) -> None:
        DialogoConsultaEstudiante(self, self.cfg, self.base)

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
