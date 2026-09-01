from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from typing import List

from .config import get_settings
from .models import TemplateConfig, TextField

# Layout folder per template:
#   data/templates/<id>/config.json
#   data/templates/<id>/bg_front.<ext>
#   data/templates/<id>/bg_back.<ext>
#   data/templates/<id>/fonts/<file>.ttf


def _root() -> str:
    return get_settings().templates_dir


def template_dir(template_id: str) -> str:
    return os.path.join(_root(), _safe_id(template_id))


def _config_path(template_id: str) -> str:
    return os.path.join(template_dir(template_id), "config.json")


def fonts_dir(template_id: str) -> str:
    path = os.path.join(template_dir(template_id), "fonts")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_id(template_id: str) -> str:
    tid = re.sub(r"[^A-Za-z0-9_-]", "", template_id or "")
    if not tid:
        raise KeyError("id template tidak valid")
    return tid


def _safe_name(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    return base or "file"


# ----------------------------- CRUD ----------------------------------


def list_templates() -> List[TemplateConfig]:
    root = _root()
    if not os.path.isdir(root):
        return []
    out: List[TemplateConfig] = []
    for name in sorted(os.listdir(root)):
        if os.path.isfile(os.path.join(root, name, "config.json")):
            try:
                out.append(load_template(name))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    return out


def load_template(template_id: str) -> TemplateConfig:
    path = _config_path(template_id)
    if not os.path.isfile(path):
        raise KeyError(template_id)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return TemplateConfig(**data)


def save_template(cfg: TemplateConfig) -> None:
    os.makedirs(template_dir(cfg.id), exist_ok=True)
    with open(_config_path(cfg.id), "w", encoding="utf-8") as handle:
        json.dump(cfg.model_dump(), handle, ensure_ascii=False, indent=2)


def create_template(name: str) -> TemplateConfig:
    template_id = uuid.uuid4().hex[:12]
    cfg = TemplateConfig(
        id=template_id,
        name=(name or "Template Baru").strip() or "Template Baru",
        fields=[
            TextField(
                key="nama", label="Nama Peserta", pages=[1], x=None, y=258,
                align="center", font_size=36, font_size_min=29, max_width=550,
                color="#191919", sample="Nama Peserta Contoh",
            ),
            TextField(
                key="nomor", label="Nomor Sertifikat", pages=[1, 2], x=122, y=75,
                align="left", font_size=12, color="#191919",
                sample="001/SERT/VIII/2026",
            ),
        ],
    )
    save_template(cfg)
    return cfg


def delete_template(template_id: str) -> None:
    shutil.rmtree(template_dir(template_id), ignore_errors=True)


# ----------------------------- aset ---------------------------------


def save_asset(template_id: str, kind: str, filename: str, content: bytes) -> TemplateConfig:
    cfg = load_template(template_id)
    tdir = template_dir(template_id)

    if kind in ("bg_front", "bg_back"):
        ext = os.path.splitext(_safe_name(filename))[1].lower() or ".png"
        target = f"{kind}{ext}"
        for existing in os.listdir(tdir):
            if existing.startswith(kind + "."):
                os.remove(os.path.join(tdir, existing))
        with open(os.path.join(tdir, target), "wb") as handle:
            handle.write(content)
        if kind == "bg_front":
            cfg.bg_front = target
        else:
            cfg.bg_back = target

    elif kind == "font":
        safe = _safe_name(filename)
        with open(os.path.join(fonts_dir(template_id), safe), "wb") as handle:
            handle.write(content)
        if safe not in cfg.fonts:
            cfg.fonts.append(safe)
            cfg.fonts.sort()

    else:
        raise ValueError(f"kind tidak dikenal: {kind}")

    save_template(cfg)
    return cfg


def delete_font(template_id: str, name: str) -> TemplateConfig:
    cfg = load_template(template_id)
    safe = _safe_name(name)
    path = os.path.join(fonts_dir(template_id), safe)
    if os.path.isfile(path):
        os.remove(path)
    cfg.fonts = [f for f in cfg.fonts if f != safe]
    save_template(cfg)
    return cfg
