"""Diálogo: cálculo de prioridad, leyenda de colores y personalización hexadecimal."""

from __future__ import annotations

from tkinter import colorchooser, messagebox
from typing import Callable

import customtkinter as ctk

from consolidado.config.settings import COLORES_PRIORIDAD_DEFAULT, guardar_config
from consolidado.core.prioridad import (
    BLOQUES_PUNTUACION_GUI,
    FORMULA_PUNTAJE_GUI,
    METADATA_COLORES_FILA,
    aplicar_colores_prioridad,
    colores_fila_para_gui,
    colores_prioridad_desde_cfg,
    normalizar_hex_excel,
)
from consolidado.gui.theme import (
    FONT_PEQUENA,
    FONT_SUBTITULO,
    FONT_TEXTO,
    configurar_tabview,
    estilo_boton_secundario,
    normalizar_kwargs_boton,
)


def _chip_color(master, color_hex: str | None) -> ctk.CTkFrame:
    borde = ("gray70", "gray40")
    if color_hex:
        chip = ctk.CTkFrame(
            master,
            width=28,
            height=28,
            fg_color=f"#{color_hex}",
            corner_radius=6,
            border_width=1,
            border_color=borde,
        )
    else:
        chip = ctk.CTkFrame(
            master,
            width=28,
            height=28,
            fg_color="transparent",
            corner_radius=6,
            border_width=1,
            border_color=borde,
        )
    chip.pack_propagate(False)
    return chip


class FilaEditorColor(ctk.CTkFrame):
    """Fila con vista previa, campo hex y botón de paleta del sistema."""

    def __init__(
        self,
        master,
        *,
        titulo: str,
        subtitulo: str,
        clave: str,
        color_inicial: str,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.clave = clave
        self._on_change = on_change

        self.chip = _chip_color(self, color_inicial)
        self.chip.pack(side="left", padx=(0, 10))

        texto = ctk.CTkFrame(self, fg_color="transparent")
        texto.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(texto, text=titulo, font=FONT_TEXTO, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            texto,
            text=subtitulo,
            font=FONT_PEQUENA,
            text_color=("gray45", "gray55"),
            anchor="w",
            justify="left",
            wraplength=360,
        ).pack(anchor="w")

        acciones = ctk.CTkFrame(self, fg_color="transparent")
        acciones.pack(side="right", padx=(8, 0))
        self.var_hex = ctk.StringVar(value=color_inicial)
        self.entry_hex = ctk.CTkEntry(
            acciones,
            textvariable=self.var_hex,
            width=92,
            placeholder_text="RRGGBB",
        )
        self.entry_hex.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            acciones,
            text="Paleta",
            width=72,
            command=self._elegir_paleta,
        ).pack(side="left")
        self.var_hex.trace_add("write", lambda *_: self._actualizar_vista())

    def _actualizar_vista(self) -> None:
        hex_val = normalizar_hex_excel(self.var_hex.get())
        if hex_val:
            self.chip.configure(fg_color=f"#{hex_val}")
            if self.var_hex.get().upper() != hex_val:
                self.var_hex.set(hex_val)
        if self._on_change:
            self._on_change()

    def _elegir_paleta(self) -> None:
        actual = normalizar_hex_excel(self.var_hex.get()) or "FFFFFF"
        elegido = colorchooser.askcolor(
            color=f"#{actual}",
            title=f"Color — {self.clave}",
            parent=self.winfo_toplevel(),
        )[1]
        if elegido:
            self.var_hex.set(elegido.lstrip("#").upper())

    def valor(self) -> str | None:
        return normalizar_hex_excel(self.var_hex.get())

    def establecer(self, color: str) -> None:
        self.var_hex.set(color.upper())


class DialogoInfoPrioridad(ctk.CTkToplevel):
    def __init__(self, master, cfg: dict, base, on_guardado: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.cfg = cfg
        self.base = base
        self._on_guardado = on_guardado
        self._editores: dict[str, FilaEditorColor] = {}

        self.title("Prioridad: cálculo y colores")
        self.geometry("820x680")
        self.minsize(640, 520)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Cálculo del puntaje y colores en el consolidado",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(14, 4))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        ctk.CTkLabel(
            scroll,
            text=FORMULA_PUNTAJE_GUI,
            font=FONT_TEXTO,
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 10))

        self._construir_bloques_puntuacion(scroll)
        self._construir_leyenda_colores(scroll)
        self._construir_editores_colores(scroll)

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(
            barra,
            text="Restaurar colores",
            width=130,
            command=self._restaurar_colores,
            **estilo_boton_secundario(),
        ).pack(side="left")
        ctk.CTkButton(barra, text="Guardar colores", width=130, command=self._guardar).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(barra, text="Cerrar", width=90, command=self.destroy).pack(side="right")

    def _construir_bloques_puntuacion(self, master) -> None:
        ctk.CTkLabel(
            master,
            text="Cómo se suman los puntos",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        reglas = ctk.CTkFrame(master, fg_color="transparent")
        reglas.pack(fill="x", pady=(0, 12))
        reglas.grid_columnconfigure(0, weight=1)
        reglas.grid_columnconfigure(1, weight=1)

        for idx, bloque in enumerate(BLOQUES_PUNTUACION_GUI):
            col = idx % 2
            row = idx // 2
            marco = ctk.CTkFrame(reglas, fg_color="transparent")
            marco.grid(row=row, column=col, sticky="nw", padx=(0, 12), pady=(0, 8))
            ctk.CTkLabel(
                marco,
                text=bloque["titulo"],
                font=(FONT_TEXTO[0], FONT_TEXTO[1], "bold"),
                anchor="w",
            ).pack(anchor="w")
            if bloque.get("nota"):
                ctk.CTkLabel(
                    marco,
                    text=bloque["nota"],
                    font=FONT_PEQUENA,
                    text_color=("gray45", "gray55"),
                    anchor="w",
                    justify="left",
                    wraplength=360,
                ).pack(anchor="w", pady=(0, 4))
            for item in bloque["items"]:
                ctk.CTkLabel(
                    marco,
                    text=f"• {item['etiqueta']}: +{item['puntos']}",
                    font=FONT_PEQUENA,
                    anchor="w",
                ).pack(anchor="w")

        ctk.CTkLabel(
            master,
            text=(
                "Niveles de puntaje total: 5 = activación de ruta · 4 = 10–19 · 3 = 7–9 · "
                "2 = 4–6 · 1 = 1–3 · 0 = sin señal. El color de fila sigue las reglas por "
                "componente (ver leyenda abajo)."
            ),
            font=FONT_PEQUENA,
            text_color=("gray45", "gray55"),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))

    def _construir_leyenda_colores(self, master) -> None:
        ctk.CTkLabel(
            master,
            text="Colores aplicados en el Excel",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", pady=(8, 4))
        ctk.CTkLabel(
            master,
            text="Precedencia: rojo → morado/naranja/reintegro/repitiendo/ruta (componente más alto) → "
            "amarillo/verde (empates) → gris (solo beca 0/NO/Call Center sin otra señal). "
            "El tono varía con el puntaje del componente.",
            font=FONT_PEQUENA,
            text_color=("gray45", "gray55"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        self.marco_leyenda = ctk.CTkFrame(master, fg_color=("gray90", "gray20"), corner_radius=8)
        self.marco_leyenda.pack(fill="x", pady=(0, 12))
        self._refrescar_leyenda()

    def _refrescar_leyenda(self) -> None:
        for w in self.marco_leyenda.winfo_children():
            w.destroy()
        inner = ctk.CTkFrame(self.marco_leyenda, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        for item in colores_fila_para_gui():
            fila = ctk.CTkFrame(inner, fg_color="transparent")
            fila.pack(fill="x", pady=2)
            _chip_color(fila, item.get("color")).pack(side="left", padx=(0, 8))
            nota = item.get("nota", "")
            texto = item["etiqueta"] + (f" · {nota}" if nota else "")
            ctk.CTkLabel(fila, text=texto, font=FONT_PEQUENA, anchor="w").pack(side="left")

    def _construir_editores_colores(self, master) -> None:
        ctk.CTkLabel(
            master,
            text="Personalizar colores (hexadecimal)",
            font=FONT_SUBTITULO,
            anchor="w",
        ).pack(anchor="w", pady=(4, 6))
        ctk.CTkLabel(
            master,
            text="Use 6 dígitos hex (RRGGBB) o el botón «Paleta». Los cambios se guardan en la configuración.",
            font=FONT_PEQUENA,
            text_color=("gray45", "gray55"),
            anchor="w",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))

        colores = colores_prioridad_desde_cfg(self.cfg)
        marco_edit = ctk.CTkFrame(master, fg_color="transparent")
        marco_edit.pack(fill="x")

        for meta in METADATA_COLORES_FILA:
            clave = meta["clave"]
            editor = FilaEditorColor(
                marco_edit,
                titulo=meta["etiqueta"],
                subtitulo=meta.get("nota", ""),
                clave=clave,
                color_inicial=colores[clave],
                on_change=self._refrescar_leyenda_desde_editores,
            )
            editor.pack(fill="x", pady=4)
            self._editores[clave] = editor

    def _refrescar_leyenda_desde_editores(self) -> None:
        preview = dict(COLORES_PRIORIDAD_DEFAULT)
        for clave, editor in self._editores.items():
            valor = editor.valor()
            if valor:
                preview[clave] = valor
        aplicar_colores_prioridad({"colores_prioridad": preview})
        self._refrescar_leyenda()

    def _restaurar_colores(self) -> None:
        for clave, color in COLORES_PRIORIDAD_DEFAULT.items():
            editor = self._editores.get(clave)
            if editor:
                editor.establecer(color)
        aplicar_colores_prioridad(self.cfg)
        self._refrescar_leyenda()

    def _guardar(self) -> None:
        nuevos: dict[str, str] = {}
        invalidos: list[str] = []
        for clave in COLORES_PRIORIDAD_DEFAULT:
            editor = self._editores.get(clave)
            if not editor:
                continue
            valor = editor.valor()
            if not valor:
                invalidos.append(clave)
                continue
            nuevos[clave] = valor
        if invalidos:
            messagebox.showerror(
                "Color inválido",
                "Revise estos colores (formato RRGGBB):\n• "
                + "\n• ".join(invalidos),
                parent=self,
            )
            return

        self.cfg["colores_prioridad"] = nuevos
        guardar_config(self.cfg, self.base)
        aplicar_colores_prioridad(self.cfg)
        if self._on_guardado:
            self._on_guardado()
        messagebox.showinfo(
            "Colores guardados",
            "Los colores se aplicarán al generar el consolidado.",
            parent=self,
        )
        self._refrescar_leyenda()

    def destroy(self) -> None:
        aplicar_colores_prioridad(self.cfg)
        super().destroy()
