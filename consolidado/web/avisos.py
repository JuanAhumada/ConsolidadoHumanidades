"""Tarjetas de aviso en el .exe (sin consola). Solo se muestran si algo falla."""

from __future__ import annotations

from typing import Literal


def mostrar_tarjeta(
    titulo: str,
    mensaje: str,
    tipo: Literal["error", "aviso"] = "error",
) -> None:
    """Ventana corta, sin terminal. Si Tk no está, no hace nada."""
    try:
        import tkinter as tk
    except Exception:
        return

    acento = "#A3161A" if tipo == "error" else "#C9A227"
    fondo = "#F4F4F4"
    papel = "#ffffff"

    root = tk.Tk()
    root.title(titulo)
    root.configure(bg=fondo)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    marco = tk.Frame(root, bg=fondo, padx=28, pady=24)
    marco.pack(fill="both", expand=True)

    tarjeta = tk.Frame(marco, bg=papel, highlightbackground="#CCCCCC", highlightthickness=1, padx=22, pady=20)
    tarjeta.pack(fill="both", expand=True)

    barra = tk.Frame(tarjeta, bg=acento, height=4)
    barra.pack(fill="x", pady=(0, 14))

    tk.Label(
        tarjeta,
        text=titulo,
        bg=papel,
        fg="#2A2A2A",
        font=("Red Hat Display", 13, "bold"),
        anchor="w",
        justify="left",
    ).pack(fill="x")
    tk.Label(
        tarjeta,
        text=mensaje,
        bg=papel,
        fg="#595959",
        font=("Red Hat Display", 10),
        wraplength=380,
        anchor="w",
        justify="left",
    ).pack(fill="x", pady=(8, 16))

    def cerrar() -> None:
        root.destroy()

    btn = tk.Button(
        tarjeta,
        text="Entendido",
        command=cerrar,
        bg=acento,
        fg="#ffffff",
        activebackground=acento,
        activeforeground="#ffffff",
        relief="flat",
        font=("Red Hat Display", 10, "bold"),
        padx=16,
        pady=6,
        cursor="hand2",
    )
    btn.pack(anchor="e")

    root.update_idletasks()
    w, h = 460, max(220, root.winfo_reqheight())
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.protocol("WM_DELETE_WINDOW", cerrar)
    root.mainloop()
