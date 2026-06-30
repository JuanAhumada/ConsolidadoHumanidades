"""Iconos simples para botones de la interfaz."""

from __future__ import annotations

import math

import customtkinter as ctk
from PIL import Image, ImageDraw

_CACHE: dict[tuple[str, int, str], ctk.CTkImage] = {}


def _fg(mode: str) -> str:
    return "#dce4ee" if mode == "Dark" else "#1a1a1a"


def _dibujar(nombre: str, size: int, fg: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, size // 8)

    if nombre == "generate":
        d.polygon(
            [(pad + size * 0.28, pad), (pad + size * 0.28, size - pad), (size - pad, size // 2)],
            fill=fg,
        )
    elif nombre == "folder":
        d.rectangle([pad, pad + size * 0.22, size - pad, size - pad], outline=fg, width=2)
        d.rectangle([pad, pad + size * 0.38, size * 0.52, pad + size * 0.58], fill=fg)
    elif nombre == "folder_open":
        d.rectangle([pad, pad + size * 0.3, size - pad, size - pad], outline=fg, width=2)
        d.polygon(
            [(pad, pad + size * 0.45), (size * 0.45, pad + size * 0.45), (size * 0.55, pad + size * 0.28), (size - pad, pad + size * 0.28), (size - pad, pad + size * 0.45)],
            outline=fg,
            width=2,
        )
    elif nombre == "save":
        d.rectangle([pad + 1, pad + 1, size - pad - 1, size - pad - 1], outline=fg, width=2)
        d.rectangle([size * 0.34, pad + 1, size * 0.66, size * 0.34], fill=fg)
        d.rectangle([pad + 3, size * 0.52, size - pad - 3, size - pad - 2], fill=fg)
    elif nombre == "refresh":
        d.arc([pad, pad, size - pad, size - pad], start=30, end=300, fill=fg, width=2)
        d.polygon(
            [(size - pad - 2, pad + size * 0.22), (size - pad - 2, pad + size * 0.42), (size - pad - 8, pad + size * 0.32)],
            fill=fg,
        )
    elif nombre == "add_user":
        d.ellipse([size * 0.32, pad + 1, size * 0.68, size * 0.38], outline=fg, width=2)
        d.arc([pad + 1, size * 0.42, size - pad - 1, size - pad], start=20, end=160, fill=fg, width=2)
    elif nombre == "remove":
        d.line([pad + 2, size // 2, size - pad - 2, size // 2], fill=fg, width=3)
    elif nombre == "settings":
        cx, cy = size // 2, size // 2
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=fg)
        for i in range(8):
            a = i * math.pi / 4
            r1, r2 = size // 4, size // 3
            d.line(
                [cx + math.cos(a) * r1, cy + math.sin(a) * r1, cx + math.cos(a) * r2, cy + math.sin(a) * r2],
                fill=fg,
                width=2,
            )
    elif nombre == "add":
        d.line([size // 2, pad + 2, size // 2, size - pad - 2], fill=fg, width=2)
        d.line([pad + 2, size // 2, size - pad - 2, size // 2], fill=fg, width=2)
    elif nombre == "sun":
        cx, cy = size // 2, size // 2
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=fg)
        for i in range(8):
            a = i * math.pi / 4
            d.line(
                [cx + math.cos(a) * 7, cy + math.sin(a) * 7, cx + math.cos(a) * 10, cy + math.sin(a) * 10],
                fill=fg,
                width=2,
            )
    elif nombre == "moon":
        d.arc([pad + 2, pad + 2, size - pad - 2, size - pad - 2], start=60, end=300, fill=fg, width=2)
    elif nombre == "info":
        cx, cy = size // 2, size // 2
        r = size // 2 - pad
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fg, width=2)
        d.rectangle([cx - 1, cy - r // 2, cx + 1, cy - 1], fill=fg)
        d.ellipse([cx - 2, cy + r // 3, cx + 2, cy + r // 3 + 4], fill=fg)
    else:
        d.ellipse([pad, pad, size - pad, size - pad], outline=fg, width=2)

    return img


def icono(nombre: str, size: int = 22) -> ctk.CTkImage:
    mode = ctk.get_appearance_mode()
    key = (nombre, size, mode)
    if key not in _CACHE:
        px = size * 2
        fg = _fg(mode)
        pil = _dibujar(nombre, px, fg)
        _CACHE[key] = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
    return _CACHE[key]


def limpiar_cache_iconos() -> None:
    _CACHE.clear()
