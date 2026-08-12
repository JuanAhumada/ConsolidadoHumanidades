"""Widgets reutilizables — layout tipo aplicación web."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter import Label as TkLabel
from tkinter import Toplevel as TkToplevel
from typing import Callable

import customtkinter as ctk

from consolidado.gui.theme import (
    COLOR_ACENTO,
    COLOR_FALTA,
    COLOR_OK,
    COLOR_OPCIONAL,
    COLOR_TEXTO,
    COLOR_TEXTO_MUTED,
    FONT_GUIA,
    FONT_MARCA,
    FONT_NAV,
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    FONT_TITULO,
    color_fondo_app,
    configurar_treeview,
    estilo_boton_secundario,
    estilo_nav_item,
    estilo_seccion,
    estilo_sidebar,
    estilo_tarjeta_paso,
    normalizar_kwargs_boton,
)


class MarcoDesplazable(ctk.CTkFrame):
    """
    Área con scroll mediante Canvas nativo.
    Evita el difuminado/ghosting de CTkScrollableFrame al desplazarse rápido.
    """

    def __init__(self, master, *, altura: int | None = None, **kwargs) -> None:
        fg = kwargs.pop("fg_color", "transparent")
        super().__init__(master, fg_color=fg, **kwargs)
        if altura is not None:
            self.configure(height=altura)
            self.pack_propagate(False)
        if fg == "transparent":
            self._bg = color_fondo_app()
        elif isinstance(fg, tuple):
            self._bg = fg[1] if ctk.get_appearance_mode() == "Dark" else fg[0]
        else:
            self._bg = str(fg)

        self._canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            bg=self._bg,
        )
        self._scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self._canvas.yview,
        )
        self.inner = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._inner_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        self._enlazar_rueda(self)
        self._enlazar_rueda(self._canvas)
        self._enlazar_rueda(self.inner)

    def _on_inner_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._inner_id, width=event.width)

    def _enlazar_rueda(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_rueda, add="+")
        widget.bind("<Button-4>", self._on_rueda_linux, add="+")
        widget.bind("<Button-5>", self._on_rueda_linux, add="+")

    def enlazar_rueda_recursivo(self) -> None:
        """Vuelve a enlazar la rueda tras añadir widgets dinámicos."""
        self._enlazar_rueda(self.inner)
        for hijo in self.inner.winfo_children():
            self._enlazar_rueda(hijo)
            for nieto in hijo.winfo_children():
                self._enlazar_rueda(nieto)

    def _on_rueda(self, event) -> None:
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_rueda_linux(self, event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(3, "units")

    def actualizar_fondo(self) -> None:
        self._bg = color_fondo_app()
        self._canvas.configure(bg=self._bg)


class IconButton(ctk.CTkButton):
    """Botón cuadrado solo con icono y tooltip al pasar el mouse."""

    def __init__(
        self,
        master,
        *,
        icon: ctk.CTkImage,
        tooltip: str,
        command: Callable[[], None] | None = None,
        width: int = 36,
        **kwargs,
    ) -> None:
        kwargs = normalizar_kwargs_boton(kwargs)
        super().__init__(
            master,
            text="",
            image=icon,
            width=width,
            height=width,
            command=command,
            corner_radius=kwargs.pop("corner_radius", 10),
            **kwargs,
        )
        self._tooltip = tooltip
        self.bind("<Enter>", self._mostrar_tooltip)
        self.bind("<Leave>", self._ocultar_tooltip)
        self.bind("<Destroy>", self._ocultar_tooltip)
        self._tip_win: TkToplevel | None = None

    def set_tooltip(self, texto: str) -> None:
        self._tooltip = texto

    def _mostrar_tooltip(self, _event=None) -> None:
        if self._tip_win is not None:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        x = self.winfo_rootx() + self.winfo_width() // 2
        y = self.winfo_rooty() + self.winfo_height() + 4
        root = self.winfo_toplevel()
        self._tip_win = TkToplevel(root)
        self._tip_win.wm_overrideredirect(True)
        self._tip_win.wm_geometry(f"+{x}+{y}")
        self._tip_win.attributes("-topmost", True)
        TkLabel(
            self._tip_win,
            text=self._tooltip,
            font=FONT_PEQUENA,
            bg="#0f172a",
            fg="#f8fafc",
            padx=8,
            pady=4,
            relief="flat",
            borderwidth=0,
        ).pack()

    def _ocultar_tooltip(self, _event=None) -> None:
        win = self._tip_win
        self._tip_win = None
        if win is None:
            return
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass


class TextoAyuda(ctk.CTkLabel):
    """Texto explicativo bajo títulos de sección."""

    def __init__(self, master, texto: str, **kwargs) -> None:
        super().__init__(
            master,
            text=texto,
            font=FONT_GUIA,
            text_color=COLOR_TEXTO_MUTED,
            anchor="w",
            justify="left",
            wraplength=820,
            **kwargs,
        )


class BotonIconoTexto(ctk.CTkButton):
    """Botón con icono y etiqueta visible."""

    def __init__(
        self,
        master,
        *,
        icon: ctk.CTkImage | None = None,
        texto: str,
        command: Callable[[], None] | None = None,
        width: int | None = None,
        height: int = 36,
        **kwargs,
    ) -> None:
        kwargs = normalizar_kwargs_boton(kwargs)
        super().__init__(
            master,
            text=f"  {texto}" if icon else texto,
            image=icon,
            compound="left" if icon else "center",
            command=command,
            width=width or max(120, len(texto) * 9 + (36 if icon else 0)),
            height=height,
            corner_radius=kwargs.pop("corner_radius", 10),
            **kwargs,
        )


class ContenidoRetractil(ctk.CTkFrame):
    """Bloque con botón para mostrar u ocultar su contenido."""

    def __init__(
        self,
        master,
        *,
        texto_abierto: str,
        texto_cerrado: str,
        icono_abierto: ctk.CTkImage | None = None,
        icono_cerrado: ctk.CTkImage | None = None,
        expandido: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._texto_abierto = texto_abierto
        self._texto_cerrado = texto_cerrado
        self._icono_abierto = icono_abierto
        self._icono_cerrado = icono_cerrado
        self._expandido = expandido

        self.barra = ctk.CTkFrame(self, fg_color="transparent")
        self.barra.pack(fill="x", pady=(0, 6))

        self.btn_toggle = BotonIconoTexto(
            self.barra,
            icon=icono_abierto if expandido else icono_cerrado,
            texto=texto_abierto if expandido else texto_cerrado,
            command=self.alternar,
            **estilo_boton_secundario(),
        )
        self.btn_toggle.pack(side="left")

        self.contenido = ctk.CTkFrame(self, fg_color="transparent")
        if expandido:
            self.contenido.pack(fill="x")

    def alternar(self) -> None:
        self._expandido = not self._expandido
        if self._expandido:
            self.contenido.pack(fill="x")
            self.btn_toggle.configure(
                image=self._icono_abierto,
                text=f"  {self._texto_abierto}",
            )
        else:
            self.contenido.pack_forget()
            self.btn_toggle.configure(
                image=self._icono_cerrado,
                text=f"  {self._texto_cerrado}",
            )

    @property
    def expandido(self) -> bool:
        return self._expandido


class PanelPasos(ctk.CTkFrame):
    """Guía visual de los tres pasos del flujo de trabajo."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._tarjetas: list[ctk.CTkFrame] = []
        self._labels_estado: list[ctk.CTkLabel] = []
        pasos = (
            ("01", "Cargar Excels", "Suba o actualice los archivos fuente."),
            ("02", "Ajustes", "Priorizados y alertas propias."),
            ("03", "Generar", "Excel versionado + registro SQL."),
        )
        for i, (num, titulo, desc) in enumerate(pasos):
            tarjeta = ctk.CTkFrame(self, **estilo_tarjeta_paso())
            tarjeta.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0), pady=0, sticky="nsew")
            self.grid_columnconfigure(i, weight=1)
            self._tarjetas.append(tarjeta)

            cab = ctk.CTkFrame(tarjeta, fg_color="transparent")
            cab.pack(fill="x", padx=14, pady=(14, 4))
            ctk.CTkLabel(
                cab,
                text=num,
                width=28,
                height=28,
                corner_radius=8,
                fg_color=COLOR_ACENTO,
                text_color="white",
                font=("Bahnschrift", 12, "bold"),
            ).pack(side="left")
            ctk.CTkLabel(cab, text=titulo, font=FONT_SUBTITULO, text_color=COLOR_TEXTO).pack(
                side="left", padx=(10, 0)
            )

            ctk.CTkLabel(
                tarjeta,
                text=desc,
                font=FONT_GUIA,
                text_color=COLOR_TEXTO_MUTED,
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(anchor="w", padx=14, pady=(0, 4))

            lbl_estado = ctk.CTkLabel(
                tarjeta,
                text="",
                font=FONT_PEQUENA,
                anchor="w",
            )
            lbl_estado.pack(anchor="w", padx=14, pady=(0, 14))
            self._labels_estado.append(lbl_estado)

    def actualizar(
        self,
        *,
        archivos_obligatorios: str,
        listo_generar: bool,
        ruta_salida: str,
        paso1_listo: bool = False,
    ) -> None:
        self._labels_estado[0].configure(
            text=archivos_obligatorios,
            text_color=COLOR_OK if paso1_listo else COLOR_FALTA,
        )
        self._labels_estado[1].configure(
            text="Puede añadir o quitar entradas manuales",
            text_color=COLOR_TEXTO_MUTED,
        )
        texto_gen = "Listo para generar" if listo_generar else "Complete los archivos obligatorios"
        self._labels_estado[2].configure(
            text=f"{texto_gen}\n{ruta_salida}",
            text_color=COLOR_OK if listo_generar else COLOR_FALTA,
        )
        borde_listo = COLOR_OK if listo_generar else COLOR_ACENTO
        borde_ok = COLOR_OK
        borde_neutro = ("#e2e8f0", "#334155")
        for i, tarjeta in enumerate(self._tarjetas):
            if i == 2 and listo_generar:
                tarjeta.configure(border_color=borde_listo)
            elif i == 0 and paso1_listo:
                tarjeta.configure(border_color=borde_ok)
            else:
                tarjeta.configure(border_color=borde_neutro)


class BarraEstado(ctk.CTkFrame):
    """Resumen compacto del estado de carga (chip tipo web)."""

    def __init__(self, master, **kwargs) -> None:
        kwargs = {**estilo_seccion(), **kwargs}
        super().__init__(master, **kwargs)
        self.lbl_archivos = ctk.CTkLabel(self, text="", font=FONT_TEXTO, anchor="w")
        self.lbl_archivos.pack(side="left", padx=16, pady=12)
        self.lbl_ruta = ctk.CTkLabel(
            self,
            text="",
            font=FONT_PEQUENA,
            text_color=COLOR_TEXTO_MUTED,
            anchor="e",
        )
        self.lbl_ruta.pack(side="right", padx=16, pady=12)

    def actualizar(self, *, archivos: str, ruta: str, listo: bool) -> None:
        self.lbl_archivos.configure(
            text=archivos,
            text_color=COLOR_OK if listo else COLOR_FALTA,
        )
        self.lbl_ruta.configure(text=f"Salida · {ruta}")


class Seccion(ctk.CTkFrame):
    """Tarjeta con título y texto de ayuda opcional."""

    def __init__(self, master, titulo: str, ayuda: str | None = None, **kwargs) -> None:
        kwargs = {**estilo_seccion(), **kwargs}
        super().__init__(master, **kwargs)
        ctk.CTkLabel(
            self,
            text=titulo,
            font=FONT_SUBTITULO,
            text_color=COLOR_TEXTO,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 2))
        if ayuda:
            TextoAyuda(self, ayuda).pack(fill="x", padx=18, pady=(0, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 14))


class EncabezadoPagina(ctk.CTkFrame):
    """Cabecera de página estilo web: título + subtítulo + acciones."""

    def __init__(
        self,
        master,
        *,
        titulo: str,
        subtitulo: str = "",
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        textos = ctk.CTkFrame(self, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            textos,
            text=titulo,
            font=FONT_TITULO,
            text_color=COLOR_TEXTO,
            anchor="w",
        ).pack(anchor="w")
        if subtitulo:
            ctk.CTkLabel(
                textos,
                text=subtitulo,
                font=FONT_TEXTO,
                text_color=COLOR_TEXTO_MUTED,
                anchor="w",
                wraplength=640,
                justify="left",
            ).pack(anchor="w", pady=(4, 0))
        self.acciones = ctk.CTkFrame(self, fg_color="transparent")
        self.acciones.pack(side="right", padx=(12, 0))


class Sidebar(ctk.CTkFrame):
    """Barra lateral de navegación tipo web app."""

    def __init__(self, master, **kwargs) -> None:
        kwargs = {**estilo_sidebar(), **kwargs}
        super().__init__(master, width=232, **kwargs)
        self.pack_propagate(False)
        self._items: dict[str, ctk.CTkButton] = {}
        self._activo: str | None = None
        self._on_nav: Callable[[str], None] | None = None

        marca = ctk.CTkFrame(self, fg_color="transparent")
        marca.pack(fill="x", padx=18, pady=(22, 18))
        ctk.CTkLabel(
            marca,
            text="Humanidades",
            font=FONT_MARCA,
            text_color="#f8fafc",
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            marca,
            text="Consolidado académico",
            font=FONT_PEQUENA,
            text_color="#94a3b8",
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        self.nav = ctk.CTkFrame(self, fg_color="transparent")
        self.nav.pack(fill="x", padx=12, pady=(8, 0))

        self.pie = ctk.CTkFrame(self, fg_color="transparent")
        self.pie.pack(side="bottom", fill="x", padx=12, pady=16)

    def configurar_navegacion(
        self,
        items: list[tuple[str, str, ctk.CTkImage | None]],
        on_nav: Callable[[str], None],
    ) -> None:
        self._on_nav = on_nav
        for clave, etiqueta, icon in items:
            btn = ctk.CTkButton(
                self.nav,
                text=f"  {etiqueta}",
                image=icon,
                compound="left",
                font=FONT_NAV,
                command=lambda c=clave: self._click(c),
                **estilo_nav_item(activo=False),
            )
            btn.pack(fill="x", pady=3)
            self._items[clave] = btn

    def _click(self, clave: str) -> None:
        self.activar(clave)
        if self._on_nav:
            self._on_nav(clave)

    def activar(self, clave: str) -> None:
        self._activo = clave
        for k, btn in self._items.items():
            btn.configure(**estilo_nav_item(activo=(k == clave)))


class TablaPriorizados(ctk.CTkFrame):
    """Treeview de priorizados con columna Contactado (checkbox)."""

    COLUMNAS = ("contactado", "identificacion", "nombre", "motivo", "detalle", "origen")
    _CHECK_ON = "☑"
    _CHECK_OFF = "☐"

    def __init__(
        self,
        master,
        *,
        on_toggle_contactado: Callable[[str, bool], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_toggle = on_toggle_contactado
        self._por_item: dict[str, dict] = {}
        self.tree = ttk.Treeview(
            self,
            columns=self.COLUMNAS,
            show="headings",
            height=12,
        )
        self.tree.heading("contactado", text="Contactado")
        self.tree.heading("identificacion", text="Identificación")
        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("motivo", text="Motivo")
        self.tree.heading("detalle", text="Detalle")
        self.tree.heading("origen", text="Origen")
        self.tree.column("contactado", width=88, anchor="center")
        self.tree.column("identificacion", width=110, anchor="w")
        self.tree.column("nombre", width=180, anchor="w")
        self.tree.column("motivo", width=140, anchor="w")
        self.tree.column("detalle", width=160, anchor="w")
        self.tree.column("origen", width=130, anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(self.tree)
        self.tree.bind("<Button-1>", self._on_click, add="+")

    def limpiar(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._por_item.clear()

    def insertar_fila(self, fila: dict) -> None:
        contactado = bool(fila.get("contactado"))
        item = self.tree.insert(
            "",
            "end",
            values=(
                self._CHECK_ON if contactado else self._CHECK_OFF,
                fila.get("identificacion", ""),
                fila.get("nombre", ""),
                fila.get("motivo", ""),
                fila.get("detalle", ""),
                fila.get("origen", ""),
            ),
            tags=("contactado",) if contactado else (),
        )
        self._por_item[item] = {
            "identificacion": fila.get("identificacion", ""),
            "nombre": fila.get("nombre", ""),
            "motivo": fila.get("motivo", ""),
            "detalle": fila.get("detalle", ""),
            "origen": fila.get("origen", ""),
            "contactado": contactado,
            "es_propio": bool(fila.get("es_propio")),
        }
        self.tree.tag_configure("contactado", foreground="#64748b")

    def _on_click(self, event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return None
        item = self.tree.identify_row(event.y)
        if not item or item not in self._por_item:
            return "break"
        datos = self._por_item[item]
        nuevo = not datos["contactado"]
        datos["contactado"] = nuevo
        vals = list(self.tree.item(item, "values"))
        vals[0] = self._CHECK_ON if nuevo else self._CHECK_OFF
        self.tree.item(item, values=vals, tags=("contactado",) if nuevo else ())
        if self._on_toggle:
            self._on_toggle(str(datos["identificacion"]), nuevo)
        return "break"

    def fila_seleccionada(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return dict(self._por_item.get(sel[0]) or {})


class TablaAlertasPropias(ctk.CTkFrame):
    """Treeview de alertas propias."""

    COLUMNAS = ("identificacion", "nombre", "detalle")

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.tree = ttk.Treeview(
            self,
            columns=self.COLUMNAS,
            show="headings",
            height=12,
        )
        self.tree.heading("identificacion", text="Identificación")
        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("detalle", text="Detalle Propio")
        self.tree.column("identificacion", width=110, anchor="w")
        self.tree.column("nombre", width=200, anchor="w")
        self.tree.column("detalle", width=280, anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        configurar_treeview(self.tree)

    def limpiar(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insertar_fila(self, fila: dict) -> None:
        self.tree.insert(
            "",
            "end",
            values=(
                fila.get("identificacion", ""),
                fila.get("nombre", ""),
                fila.get("detalle", ""),
            ),
        )

    def fila_seleccionada(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        valores = self.tree.item(sel[0], "values")
        if not valores:
            return None
        return {
            "identificacion": valores[0],
            "nombre": valores[1],
            "detalle": valores[2],
        }


def texto_estado_archivo(ruta: Path, *, requerido: bool = True) -> tuple[str, str, str]:
    if ruta.is_file():
        fecha = datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        return ("cargado", f"Cargado · {fecha}", COLOR_OK)
    if requerido:
        return ("falta", "Falta cargar · obligatorio", COLOR_FALTA)
    return ("pendiente", "Sin cargar · opcional", COLOR_OPCIONAL)


def limpiar_marco(marco: ctk.CTkFrame) -> None:
    for w in marco.winfo_children():
        w.destroy()


def fila_archivo(
    marco: ctk.CTkFrame,
    fila: int,
    titulo: str,
    nombre_guardado: str,
    carpeta: Path,
    on_cargar: Callable[[], None],
    on_editar: Callable[[], None] | None = None,
    extra_btn: str | None = None,
    on_vista_previa: Callable[[], None] | None = None,
    opcional: bool = False,
) -> None:
    requerido = not opcional
    estado, texto_estado, color = texto_estado_archivo(
        carpeta / nombre_guardado, requerido=requerido
    )
    titulo_mostrar = titulo
    sufijo = " · opcional" if opcional else " · obligatorio"

    tarjeta = ctk.CTkFrame(
        marco,
        fg_color=("#f8fafc", "#1e293b"),
        border_width=1,
        border_color=("#e2e8f0", "#334155"),
        corner_radius=12,
    )
    tarjeta.grid(row=fila, column=0, columnspan=3, sticky="ew", pady=4)
    marco.grid_columnconfigure(0, weight=1)

    interior = ctk.CTkFrame(tarjeta, fg_color="transparent")
    interior.pack(fill="x", padx=12, pady=10)
    interior.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(interior, text="●", text_color=color, font=FONT_TEXTO).grid(
        row=0, column=0, padx=(0, 10), sticky="w"
    )
    info = ctk.CTkFrame(interior, fg_color="transparent")
    info.grid(row=0, column=1, sticky="ew")
    ctk.CTkLabel(
        info,
        text=f"{titulo_mostrar}{sufijo}",
        font=FONT_TEXTO,
        text_color=COLOR_TEXTO,
        anchor="w",
    ).pack(anchor="w")
    ctk.CTkLabel(
        info,
        text=texto_estado,
        font=FONT_PEQUENA,
        text_color=color if estado != "cargado" else COLOR_TEXTO_MUTED,
        anchor="w",
    ).pack(anchor="w")

    acciones = ctk.CTkFrame(interior, fg_color="transparent")
    acciones.grid(row=0, column=2, padx=(12, 0), sticky="e")
    etiqueta_btn = "Cambiar" if estado == "cargado" else "Cargar"
    ctk.CTkButton(
        acciones,
        text=etiqueta_btn,
        width=90,
        height=32,
        command=on_cargar,
        **estilo_boton_secundario(),
    ).pack(side="left", padx=3)
    if on_vista_previa:
        ctk.CTkButton(
            acciones,
            text="Vista previa",
            width=100,
            height=32,
            command=on_vista_previa,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=3)
    if on_editar and extra_btn:
        ctk.CTkButton(
            acciones,
            text=extra_btn,
            width=120,
            height=32,
            command=on_editar,
            **estilo_boton_secundario(),
        ).pack(side="left", padx=3)
