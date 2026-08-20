"""Ventana principal CustomTkinter. Preferir la web salvo mantenimiento de este cliente."""

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
from consolidado.gui.dialogs import (
    DialogoAlertaPropia,
    DialogoCambiarDatos,
    DialogoConsultaEstudiante,
    DialogoDocumento,
    DialogoInfoPrioridad,
    DialogoPriorizadoPropio,
    DialogoVersiones,
    DialogoVistaPrevia,
)
from consolidado.gui.icons import icono
from consolidado.gui.theme import (
    COLOR_ACENTO,
    COLOR_PAGE,
    COLOR_TEXTO,
    COLOR_TEXTO_MUTED,
    COLOR_TOPBAR,
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    alternar_modo_apariencia,
    configurar_apariencia,
    configurar_treeview,
    estilo_boton_primario,
    estilo_boton_secundario,
    estilo_seccion,
    estilo_tarjeta_paso,
    modo_apariencia_actual,
)
from consolidado.gui.widgets import (
    BarraEstado,
    BotonIconoTexto,
    EncabezadoPagina,
    IconButton,
    MarcoDesplazable,
    PanelPasos,
    Seccion,
    Sidebar,
    TablaAlertasPropias,
    TablaPriorizados,
    fila_archivo,
    limpiar_marco,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.alertas_propias import quitar_alerta_propia
from consolidado.storage.contactados import marcar_contactado
from consolidado.storage.db import ultima_version
from consolidado.storage.priorizados import set_priorizado_activo
from consolidado.storage.versiones import asegurar_semilla_si_vacia


class AppConsolidado(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.base = PROJECT_ROOT
        self.cfg = cargar_config(self.base)
        modo = self.cfg.get("interfaz", {}).get("modo_apariencia", "system")
        configurar_apariencia(modo)
        merge.aplicar_config(self.cfg, self.base)
        self._icon_refs: list[ctk.CTkImage] = []
        self._paginas: dict[str, ctk.CTkFrame] = {}
        self._pagina_activa: str | None = None

        self.title("Consolidado de Humanidades")
        self.geometry("1180x780")
        self.minsize(960, 640)
        self.configure(fg_color=COLOR_PAGE)

        self._construir_ui()
        self._actualizar_lista_archivos()
        self._actualizar_tabla_priorizados()
        self._actualizar_tabla_alertas()
        self._actualizar_ruta_salida()
        self.sidebar.activar("archivos")
        self._mostrar_pagina("archivos")
        self.after(200, self._sembrar_bd_si_hace_falta)

    def _ico(self, nombre: str, size: int = 20, *, color: str | None = None) -> ctk.CTkImage:
        img = icono(nombre, size=size, color=color)
        self._icon_refs.append(img)
        return img

    def _construir_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self)
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        self.sidebar.configurar_navegacion(
            [
                ("archivos", "Archivos", self._ico("folder", color="#e2e8f0")),
                ("priorizados", "Priorizados", self._ico("add_user", color="#e2e8f0")),
                ("alertas", "Alertas", self._ico("info", color="#e2e8f0")),
                ("versiones", "Versiones", self._ico("save", color="#e2e8f0")),
            ],
            self._navegar,
        )

        BotonIconoTexto(
            self.sidebar.pie,
            icon=self._ico("generate", size=18, color="#ffffff"),
            texto="Generar",
            height=42,
            command=self.generar,
            **estilo_boton_primario(),
        ).pack(fill="x", pady=(0, 8))

        fila_pie = ctk.CTkFrame(self.sidebar.pie, fg_color="transparent")
        fila_pie.pack(fill="x")
        self.btn_tema = IconButton(
            fila_pie,
            icon=self._ico_tema_sidebar(),
            tooltip="Modo claro / oscuro",
            fg_color=("#1e293b", "#0f172a"),
            hover_color=("#334155", "#1e293b"),
            command=self._toggle_tema,
        )
        self.btn_tema.pack(side="left")
        BotonIconoTexto(
            fila_pie,
            icon=self._ico("settings", size=16, color="#cbd5e1"),
            texto="Config",
            height=36,
            command=self.cambiar_datos,
            fg_color=("#1e293b", "#0f172a"),
            hover_color=("#334155", "#1e293b"),
            text_color="#cbd5e1",
            border_width=0,
            corner_radius=10,
        ).pack(side="right")

        self.area = ctk.CTkFrame(self, fg_color=COLOR_PAGE, corner_radius=0)
        self.area.grid(row=0, column=1, sticky="nsew")
        self.area.grid_rowconfigure(1, weight=1)
        self.area.grid_columnconfigure(0, weight=1)

        topbar = ctk.CTkFrame(
            self.area,
            fg_color=COLOR_TOPBAR,
            corner_radius=0,
            border_width=0,
            height=64,
        )
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.grid_columnconfigure(0, weight=1)

        self.lbl_ruta_top = ctk.CTkLabel(
            topbar,
            text="",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
            anchor="w",
        )
        self.lbl_ruta_top.grid(row=0, column=0, sticky="w", padx=24, pady=18)

        acciones_top = ctk.CTkFrame(topbar, fg_color="transparent")
        acciones_top.grid(row=0, column=1, sticky="e", padx=20, pady=12)
        BotonIconoTexto(
            acciones_top,
            icon=self._ico("add_user"),
            texto="Consultar estudiante",
            command=self._abrir_consulta_estudiante,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=(0, 8))
        BotonIconoTexto(
            acciones_top,
            icon=self._ico("save"),
            texto="Carpeta salida",
            command=self._elegir_ruta_salida,
            **estilo_boton_secundario(),
        ).pack(side="left")

        self.contenedor_paginas = ctk.CTkFrame(self.area, fg_color="transparent")
        self.contenedor_paginas.grid(row=1, column=0, sticky="nsew", padx=24, pady=20)

        self._construir_pagina_archivos()
        self._construir_pagina_priorizados()
        self._construir_pagina_alertas()
        self._construir_pagina_versiones()

    def _construir_pagina_archivos(self) -> None:
        pagina = ctk.CTkFrame(self.contenedor_paginas, fg_color="transparent")
        self._paginas["archivos"] = pagina

        EncabezadoPagina(
            pagina,
            titulo="Archivos fuente",
            subtitulo=(
                "Cargue los Excels por categoría. Cada generación une matrículas, "
                "priorizados, becas y alertas en un consolidado versionado."
            ),
        ).pack(fill="x", pady=(0, 14))

        self.panel_pasos = PanelPasos(pagina)
        self.panel_pasos.pack(fill="x", pady=(0, 12))

        self.barra_estado = BarraEstado(pagina)
        self.barra_estado.pack(fill="x", pady=(0, 14))

        scroll = MarcoDesplazable(pagina)
        scroll.pack(fill="both", expand=True)
        self.scroll_fuentes = scroll

        self.marco_fuentes = Seccion(
            scroll.inner,
            titulo="Excels por categoría",
            ayuda=(
                "Use «Cargar» la primera vez y «Cambiar» cuando reciba una versión nueva. "
                "Los marcados como obligatorio deben estar listos antes de generar."
            ),
        )
        self.marco_fuentes.pack(fill="x", pady=(0, 12))

        self.marco_filas_fuentes = ctk.CTkFrame(self.marco_fuentes.body, fg_color="transparent")
        self.marco_filas_fuentes.pack(fill="x")

        self.marco_docs = Seccion(
            scroll.inner,
            titulo="Documentos adicionales",
            ayuda="Opcional: otras hojas Excel que se añaden como columnas extra.",
        )
        self.marco_docs.pack(fill="x", pady=(0, 8))
        self.marco_filas_docs = ctk.CTkFrame(self.marco_docs.body, fg_color="transparent")
        self.marco_filas_docs.pack(fill="x")

        BotonIconoTexto(
            self.marco_docs.body,
            icon=self._ico("add"),
            texto="Añadir documento",
            command=self.anadir_documento,
            **estilo_boton_secundario(),
        ).pack(anchor="w", pady=(10, 0))

        self.lbl_resumen = ctk.CTkLabel(
            scroll.inner,
            text="",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
            anchor="w",
        )
        self.lbl_resumen.pack(anchor="w", pady=(8, 4))

    def _construir_pagina_priorizados(self) -> None:
        pagina = ctk.CTkFrame(self.contenedor_paginas, fg_color="transparent")
        self._paginas["priorizados"] = pagina
        self._vista_priorizados = "primer_plano"
        self._filas_priorizados: list[dict] = []

        cab = EncabezadoPagina(
            pagina,
            titulo="Priorizados",
            subtitulo=(
                "Marque «Contactado» para sacarlo del primer plano. "
                "En la vista completa siguen visibles todos."
            ),
        )
        cab.pack(fill="x", pady=(0, 14))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("refresh"),
            texto="Actualizar",
            command=self._actualizar_tabla_priorizados,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("add_user"),
            texto="Añadir propio",
            command=self._abrir_priorizado_propio,
            **estilo_boton_primario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("remove"),
            texto="Desactivar / Activar",
            command=self._alternar_priorizado_propio_seleccionado,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("info"),
            texto="Fórmula",
            command=self._abrir_info_prioridad,
            **estilo_boton_secundario(),
        ).pack(side="left")

        filtros = ctk.CTkFrame(pagina, fg_color="transparent")
        filtros.pack(fill="x", pady=(0, 10))
        self.seg_priorizados = ctk.CTkSegmentedButton(
            filtros,
            values=["Primer plano", "Completo"],
            command=self._cambiar_vista_priorizados,
        )
        self.seg_priorizados.set("Primer plano")
        self.seg_priorizados.pack(side="left")
        self.lbl_conteo_prio = ctk.CTkLabel(
            filtros,
            text="",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
        )
        self.lbl_conteo_prio.pack(side="left", padx=12)

        tarjeta = Seccion(pagina, titulo="Listado", ayuda=None)
        tarjeta.pack(fill="both", expand=True)
        self.tabla_priorizados = TablaPriorizados(
            tarjeta.body,
            on_toggle_contactado=self._on_toggle_contactado,
        )
        self.tabla_priorizados.pack(fill="both", expand=True)

    def _construir_pagina_alertas(self) -> None:
        pagina = ctk.CTkFrame(self.contenedor_paginas, fg_color="transparent")
        self._paginas["alertas"] = pagina

        cab = EncabezadoPagina(
            pagina,
            titulo="Alertas propias",
            subtitulo=(
                "Marcaciones manuales (Alerta Propia / Detalle Propio). "
                "No sustituyen las alertas de los Excels de alertas."
            ),
        )
        cab.pack(fill="x", pady=(0, 14))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("refresh"),
            texto="Actualizar",
            command=self._actualizar_tabla_alertas,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("add"),
            texto="Añadir alerta",
            command=self._abrir_alerta_propia,
            **estilo_boton_primario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("remove"),
            texto="Quitar alerta",
            command=self._quitar_alerta_propia_seleccionada,
            **estilo_boton_secundario(),
        ).pack(side="left")

        tarjeta = Seccion(pagina, titulo="Listado", ayuda=None)
        tarjeta.pack(fill="both", expand=True)
        self.tabla_alertas = TablaAlertasPropias(tarjeta.body)
        self.tabla_alertas.pack(fill="both", expand=True)

    def _construir_pagina_versiones(self) -> None:
        pagina = ctk.CTkFrame(self.contenedor_paginas, fg_color="transparent")
        self._paginas["versiones"] = pagina

        cab = EncabezadoPagina(
            pagina,
            titulo="Historial de versiones",
            subtitulo=(
                "Cada generación queda en SQLite con columnas consultables "
                "y un Excel nombrado por periodo y fecha."
            ),
        )
        cab.pack(fill="x", pady=(0, 14))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("folder"),
            texto="Abrir historial",
            command=self._abrir_versiones,
            **estilo_boton_primario(),
        ).pack(side="left", padx=(0, 6))
        BotonIconoTexto(
            cab.acciones,
            icon=self._ico("generate"),
            texto="Abrir Excel",
            command=self._abrir_excel_ultima,
            **estilo_boton_secundario(),
        ).pack(side="left")

        tarjeta = ctk.CTkFrame(pagina, **estilo_seccion())
        tarjeta.pack(fill="both", expand=True)
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cuerpo.pack(fill="both", expand=True, padx=28, pady=28)
        ctk.CTkLabel(
            cuerpo,
            text="Base de datos unificada",
            font=FONT_SUBTITULO,
            text_color=COLOR_TEXTO,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            cuerpo,
            text=(
                "Las versiones del consolidado, los priorizados propios y las alertas "
                "propias viven en la misma base SQLite. Puede filtrar por periodo, "
                "reabrir el Excel o regenerarlo desde el snapshot guardado."
            ),
            font=FONT_TEXTO,
            text_color=COLOR_TEXTO_MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(8, 18))
        self.lbl_meta_versiones = ctk.CTkLabel(
            cuerpo,
            text="",
            font=FONT_TEXTO,
            text_color=COLOR_ACENTO,
            anchor="w",
        )
        self.lbl_meta_versiones.pack(anchor="w")

    def _navegar(self, clave: str) -> None:
        if clave == "versiones":
            self._mostrar_pagina("versiones")
            self._actualizar_meta_versiones()
            return
        self._mostrar_pagina(clave)

    def _mostrar_pagina(self, clave: str) -> None:
        if self._pagina_activa == clave:
            return
        for k, frame in self._paginas.items():
            if k == clave:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self._pagina_activa = clave

    def _actualizar_meta_versiones(self) -> None:
        from consolidado.storage.db import contar_versiones, listar_versiones, periodo_desde_fecha

        n = contar_versiones(self.base)
        ult = ultima_version(self.base)
        periodos = sorted({v["periodo"] for v in listar_versiones(self.base)}, reverse=True)
        partes = [f"{n} versión(es) guardada(s)", f"periodo actual {periodo_desde_fecha()}"]
        if ult:
            partes.append(f"última: {ult['periodo']} · {ult['fecha_version']}")
        if periodos:
            partes.append(f"periodos: {', '.join(periodos[:4])}")
        self.lbl_meta_versiones.configure(text="  ·  ".join(partes))

    def _ruta_salida_actual(self) -> Path:
        ult = ultima_version(self.base)
        if ult and ult.get("ruta_excel"):
            ruta = Path(ult["ruta_excel"])
            return ruta if ruta.is_absolute() else (self.base / ruta).resolve()
        rel = self.cfg.get("salida", {}).get("ruta", "salida/estudiantes_consolidado.xlsx")
        return (self.base / rel).resolve()

    def _sembrar_bd_si_hace_falta(self) -> None:
        try:
            meta = asegurar_semilla_si_vacia(self.base)
        except Exception as exc:
            messagebox.showwarning(
                "Base de datos",
                f"No se pudo importar el consolidado inicial a SQL:\n{exc}",
            )
            return
        if meta:
            messagebox.showinfo(
                "Registro inicial",
                f"Se importó el consolidado existente como versión {meta['periodo']} "
                f"(fecha {meta['fecha_version']}).\n"
                f"{meta['num_estudiantes']} estudiantes guardados en la base SQL.\n\n"
                f"Excel: {meta.get('ruta_excel') or '—'}",
            )
            self._actualizar_ruta_salida()

    def _abrir_versiones(self) -> None:
        DialogoVersiones(self, self.cfg, self.base)

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
        self.lbl_ruta_top.configure(text=f"Salida · {ruta_corta}")

    def _actualizar_ruta_salida(self) -> None:
        self._actualizar_estado_general()

    def _elegir_ruta_salida(self) -> None:
        actual = self._ruta_salida_actual().parent
        carpeta = filedialog.askdirectory(
            title="Carpeta donde guardar los Excel versionados",
            initialdir=str(actual if actual.exists() else self.base / "salida"),
        )
        if not carpeta:
            return
        destino_dir = Path(carpeta)
        try:
            rel = destino_dir.resolve().relative_to(self.base.resolve())
            self.cfg.setdefault("salida", {})["ruta"] = (rel / "estudiantes_consolidado.xlsx").as_posix()
        except ValueError:
            self.cfg.setdefault("salida", {})["ruta"] = str(
                (destino_dir / "estudiantes_consolidado.xlsx").resolve()
            )
        guardar_config(self.cfg, self.base)
        merge.aplicar_config(self.cfg, self.base)
        self._actualizar_ruta_salida()
        messagebox.showinfo(
            "Carpeta guardada",
            f"Los consolidados se guardarán en:\n{destino_dir}\n\n"
            "Con nombre estudiantes_consolidado_{periodo}_{fecha}.xlsx",
        )

    def _toggle_tema(self) -> None:
        nuevo = alternar_modo_apariencia()
        self.cfg.setdefault("interfaz", {})["modo_apariencia"] = nuevo
        guardar_config(self.cfg, self.base)
        self.configure(fg_color=COLOR_PAGE)
        self.area.configure(fg_color=COLOR_PAGE)
        self.btn_tema.configure(image=self._ico_tema_sidebar())
        configurar_treeview(self.tabla_priorizados.tree)
        configurar_treeview(self.tabla_alertas.tree)
        self.scroll_fuentes.actualizar_fondo()
        estilo = estilo_seccion()
        for marco in (self.marco_fuentes, self.marco_docs):
            marco.configure(**estilo)
        for tarjeta in self.panel_pasos._tarjetas:
            tarjeta.configure(**estilo_tarjeta_paso())
        self._actualizar_lista_archivos()

    def _ruta_guardada(self, nombre: str) -> Path:
        return carpeta_excels(self.cfg, self.base) / nombre

    def _carpeta_excels(self) -> Path:
        return carpeta_excels(self.cfg, self.base)

    def _ico_tema_sidebar(self) -> ctk.CTkImage:
        return self._ico(
            "sun" if modo_apariencia_actual() == "dark" else "moon",
            color="#e2e8f0",
        )

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
                text_color=COLOR_TEXTO,
                anchor="w",
            ).grid(row=fila, column=0, columnspan=3, sticky="w", pady=(12, 6))
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
                text_color=COLOR_TEXTO_MUTED,
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

    def _cambiar_vista_priorizados(self, valor: str) -> None:
        self._vista_priorizados = "completo" if valor == "Completo" else "primer_plano"
        self._refrescar_tabla_priorizados_filtrada()

    def _on_toggle_contactado(self, identificacion: str, contactado: bool) -> None:
        marcar_contactado(identificacion, contactado=contactado, categoria="priorizado", base=self.base)
        for fila in self._filas_priorizados:
            if str(fila.get("identificacion", "")).strip() == identificacion.strip():
                fila["contactado"] = contactado
                break
        if self._vista_priorizados == "primer_plano" and contactado:
            self._refrescar_tabla_priorizados_filtrada()
        else:
            n_total = len(self._filas_priorizados)
            n_visibles = sum(
                1 for f in self._filas_priorizados if not f.get("contactado")
            )
            if self._vista_priorizados == "primer_plano":
                self.lbl_conteo_prio.configure(
                    text=f"{n_visibles} pendientes · {n_total - n_visibles} contactados ocultos"
                )
            else:
                self.lbl_conteo_prio.configure(text=f"{n_total} priorizados (vista completa)")

    def _refrescar_tabla_priorizados_filtrada(self) -> None:
        self.tabla_priorizados.limpiar()
        if self._vista_priorizados == "primer_plano":
            visibles = [
                f
                for f in self._filas_priorizados
                if not f.get("contactado") and f.get("activo", True)
            ]
        else:
            visibles = list(self._filas_priorizados)
        for f in visibles:
            self.tabla_priorizados.insertar_fila(f)
        n_total = len(self._filas_priorizados)
        n_contactados = sum(1 for f in self._filas_priorizados if f.get("contactado"))
        n_inactivos = sum(
            1
            for f in self._filas_priorizados
            if f.get("es_propio") and not f.get("activo", True)
        )
        if self._vista_priorizados == "primer_plano":
            self.lbl_conteo_prio.configure(
                text=(
                    f"{len(visibles)} pendientes · {n_contactados} contactados ocultos"
                    + (f" · {n_inactivos} propios inactivos" if n_inactivos else "")
                )
            )
        else:
            self.lbl_conteo_prio.configure(
                text=(
                    f"{n_total} priorizados · {n_contactados} contactados"
                    + (f" · {n_inactivos} inactivos" if n_inactivos else "")
                )
            )

    def _alternar_priorizado_propio_seleccionado(self) -> None:
        fila = self.tabla_priorizados.fila_seleccionada()
        if not fila:
            messagebox.showwarning(
                "Priorizado propio",
                "Seleccione un priorizado propio en la tabla.",
            )
            return
        origen = fila.get("origen", "")
        if "Priorizado propio" not in origen and not fila.get("es_propio"):
            messagebox.showwarning(
                "Priorizado propio",
                "Solo puede activar o desactivar entradas «Priorizado propio».\n\n"
                "Los que vienen de Excels no se gestionan desde aquí.",
            )
            return
        activo_actual = bool(fila.get("activo", True))
        nuevo = not activo_actual
        accion = "activar" if nuevo else "desactivar"
        if not messagebox.askyesno(
            "Confirmar",
            f"¿{accion.capitalize()} el priorizado propio de "
            f"{fila.get('nombre') or fila['identificacion']}?\n\n"
            + (
                "Quedará guardado en la base, pero no se aplicará al consolidado."
                if not nuevo
                else "Volverá a aplicarse al generar el consolidado."
            ),
        ):
            return
        set_priorizado_activo(fila["identificacion"], activo=nuevo, base=self.base)
        self._actualizar_tabla_priorizados()
        messagebox.showinfo(
            "Listo",
            "Priorizado propio " + ("activado." if nuevo else "desactivado."),
        )

    def _actualizar_tabla_priorizados(self) -> None:
        merge.aplicar_config(self.cfg, self.base)
        try:
            self._filas_priorizados = merge.obtener_lista_priorizados_vista(self.cfg, self.base)
        except Exception as exc:
            messagebox.showerror("Priorizados", f"No se pudo cargar la lista:\n{exc}")
            return
        self._refrescar_tabla_priorizados_filtrada()

    def _abrir_excel_ultima(self) -> None:
        from consolidado.storage.db import ultima_version

        ult = ultima_version(self.base)
        if not ult:
            messagebox.showinfo("Excel", "Aún no hay versiones generadas.")
            return
        ruta_excel = ult.get("ruta_excel")
        if not ruta_excel:
            messagebox.showinfo("Excel", "La última versión no tiene Excel asociado.")
            return
        excel = Path(ruta_excel)
        if not excel.is_absolute():
            excel = self.base / excel
        if not excel.is_file():
            messagebox.showerror("Excel", f"No se encontró el archivo:\n{excel}")
            return
        merge.abrir_archivo_en_sistema(excel, parent=self)

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

    def generar(self) -> None:
        _, _, _, _, faltantes = self._conteo_archivos()
        if faltantes:
            messagebox.showwarning(
                "Faltan archivos obligatorios",
                "Antes de generar, cargue estos archivos en Archivos:\n\n• "
                + "\n• ".join(faltantes),
            )
            self.sidebar.activar("archivos")
            self._mostrar_pagina("archivos")
            return
        try:
            from consolidado.storage.db import periodo_desde_fecha
            from datetime import date

            periodo = periodo_desde_fecha(date.today())
            consolidado, destino = merge.ejecutar_consolidado(
                self.cfg,
                base=self.base,
                abrir=True,
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
            f"Nueva versión guardada en SQL (periodo {periodo}).\n"
            f"{consolidado.height} estudiantes.\n\n"
            f"Excel:\n{destino}\n\nSe abrió el archivo Excel.",
        )

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
