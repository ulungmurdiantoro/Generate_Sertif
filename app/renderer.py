from __future__ import annotations

import io
import os
import re
import unicodedata
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Tuple

import pandas as pd
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from .config import get_settings
from .models import TemplateConfig

# ==========================================
# HELPER (porting dari generate_sertifikat.py)
# ==========================================


def clean_filename(text: str) -> str:
    """Buang karakter yang dilarang pada nama file (Windows & POSIX)."""
    return re.sub(r'[\\/*?:"<>|]', "", str(text)).strip()


def unique_name(base: str, used: set) -> str:
    """Nama unik: tambah ' (2)', ' (3)', ... bila bentrok. Memutakhirkan `used`."""
    name = base or "sertifikat"
    candidate = name
    counter = 2
    while candidate.lower() in used:
        candidate = f"{name} ({counter})"
        counter += 1
    used.add(candidate.lower())
    return candidate


def cell_to_str(raw) -> str:
    """Ubah nilai sel Excel/CSV jadi string rapi (mis. 12.0 -> '12')."""
    if raw is None:
        return ""
    try:
        if pd.isna(raw):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    text = (value or "#000000").lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (25, 25, 25)


def resolve_font_path(font_name: str, fonts_dir: str) -> str:
    """Pilih path font pertama yang tersedia: font template -> fallback sistem."""
    candidates: List[str] = []
    if font_name:
        candidates.append(os.path.join(fonts_dir, font_name))
    candidates.extend(get_settings().fallback_font_list)
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "Tidak ada font yang bisa dipakai. Upload font ke template "
        "atau set FALLBACK_FONTS di .env."
    )


_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))

# Excel/Word otomatis mengganti ' dan " jadi tanda kutip "pintar". Banyak font
# dekoratif tidak punya glyph-nya sehingga tercetak kotak/simbol aneh; untuk
# font seperti itu pakai padanan ASCII-nya.
_ASCII_FALLBACK = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "ʼ": "'", "′": "'", "´": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "–": "-", "—": "-", "−": "-",
    "…": "...",
    " ": " ", " ": " ", " ": " ",
}


@lru_cache(maxsize=64)
def _font_codepoints(font_path: str, _mtime: float) -> FrozenSet[int]:
    try:
        with TTFont(font_path, fontNumber=0, lazy=True) as font:
            return frozenset(font.getBestCmap() or {})
    except Exception:  # noqa: BLE001 - font aneh: jangan ubah teks sama sekali
        return frozenset()


def fit_text_to_font(text: str, font_path: str) -> str:
    """Rapikan teks agar tiap karakternya punya glyph di font yang dipakai."""
    text = unicodedata.normalize("NFC", str(text)).translate(_INVISIBLE)
    try:
        codepoints = _font_codepoints(font_path, os.path.getmtime(font_path))
    except OSError:
        return text
    if not codepoints:
        return text
    return "".join(
        ch if ord(ch) in codepoints else _ASCII_FALLBACK.get(ch, ch) for ch in text
    )


def _fitted_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    size_pt: float,
    min_pt: Optional[float],
    max_width_px: Optional[float],
    scale: float,
):
    """Kecilkan font selangkah demi selangkah sampai teks muat di area."""
    size_pt = float(size_pt or 12)
    floor_pt = float(min_pt) if min_pt else size_pt
    floor_pt = min(floor_pt, size_pt)

    while True:
        size_px = max(1, int(round(size_pt * scale)))
        font = ImageFont.truetype(font_path, size_px)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if max_width_px and width > max_width_px and size_pt > floor_pt:
            size_pt -= 1
            continue
        return font, width, bbox


# ==========================================
# RENDER
# ==========================================


def render_pages(
    cfg: TemplateConfig, values: Dict[str, str], template_dir: str
) -> List[Image.Image]:
    """Hasilkan list gambar (1 atau 2 halaman) untuk satu peserta."""
    if not cfg.bg_front:
        raise ValueError("Template belum punya background halaman depan.")

    fonts_dir = os.path.join(template_dir, "fonts")
    page_bg = {1: cfg.bg_front}
    if cfg.bg_back:
        page_bg[2] = cfg.bg_back

    pages: List[Image.Image] = []
    for page_no in sorted(page_bg):
        bg_path = os.path.join(template_dir, page_bg[page_no])
        image = Image.open(bg_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        img_w = image.size[0]
        scale = img_w / float(cfg.canvas_width or img_w)

        for field in cfg.fields:
            if page_no not in field.pages:
                continue
            # Field yang tidak dipetakan ke kolom -> kosong (bukan nilai contoh).
            # Pratinjau mengirim nilai contoh eksplisit lewat `values`.
            text = str(values.get(field.key, "")).strip()
            if not text or text.lower() == "nan":
                continue

            font_path = resolve_font_path(field.font, fonts_dir)
            text = fit_text_to_font(text, font_path)
            max_width_px = field.max_width * scale if field.max_width else None
            font, text_width, bbox = _fitted_font(
                draw, text, font_path, field.font_size,
                field.font_size_min, max_width_px, scale,
            )

            if field.align == "center":
                anchor_x = field.x if field.x is not None else cfg.canvas_width / 2.0
                draw_x = anchor_x * scale - text_width / 2.0
            elif field.align == "right":
                anchor_x = field.x if field.x is not None else cfg.canvas_width
                draw_x = anchor_x * scale - text_width
            else:
                anchor_x = field.x if field.x is not None else 0.0
                draw_x = anchor_x * scale

            draw_x -= bbox[0]  # kompensasi offset kiri glyph
            draw_y = field.y * scale
            draw.text((draw_x, draw_y), text, font=font, fill=hex_to_rgb(field.color))

        pages.append(image)
    return pages


def save_pdf(pages: List[Image.Image], path: str, resolution: float = 150.0) -> None:
    if not pages:
        raise ValueError("Tidak ada halaman untuk disimpan.")
    first, rest = pages[0], pages[1:]
    first.save(
        path, "PDF", resolution=float(resolution or 150.0),
        save_all=True, append_images=rest,
    )


def render_preview_png(
    cfg: TemplateConfig, template_dir: str, page: int = 1, max_width: int = 1400
) -> bytes:
    """Render satu halaman memakai nilai `sample` tiap field -> PNG bytes."""
    values = {f.key: (f.sample or f.label or f.key) for f in cfg.fields}
    pages = render_pages(cfg, values, template_dir)
    index = 0 if page <= 1 else min(page - 1, len(pages) - 1)
    image = pages[index]

    if image.size[0] > max_width:
        ratio = max_width / image.size[0]
        image = image.resize((max_width, int(image.size[1] * ratio)))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
