from __future__ import annotations

import os
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_fallback_fonts() -> str:
    """Cari font sistem yang umum ada, dipakai kalau template belum punya font."""
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    else:  # linux / docker
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    return ",".join(p for p in candidates if os.path.exists(p))


class Settings(BaseSettings):
    app_name: str = "Generator Sertifikat"
    data_dir: str = "./data"

    max_upload_mb: int = 300
    max_rows: int = 5000
    render_workers: int = 4
    job_retention_min: int = 120

    # Basic Auth opsional. Kosongkan keduanya untuk menonaktifkan.
    basic_auth_user: str | None = None
    basic_auth_pass: str | None = None

    # Font fallback tambahan (path absolut, dipisah koma). Kosong = deteksi otomatis.
    fallback_fonts: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def fallback_font_list(self) -> list[str]:
        raw = self.fallback_fonts.strip() or _detect_fallback_fonts()
        return [p.strip() for p in raw.split(",") if p.strip()]

    @property
    def templates_dir(self) -> str:
        return os.path.join(self.data_dir, "templates")

    @property
    def tmp_dir(self) -> str:
        return os.path.join(self.data_dir, "tmp")

    @property
    def output_dir(self) -> str:
        return os.path.join(self.data_dir, "output")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for directory in (settings.templates_dir, settings.tmp_dir, settings.output_dir):
        os.makedirs(directory, exist_ok=True)
    return settings
